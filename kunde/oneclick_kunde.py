#!/usr/bin/env python3
"""
OneClick Tuning - Windows-Programm fuer Kunden

Oberflaeche: kunde/ui.html (HTML/CSS/JS) in einem eigenen Fenster ueber pywebview
(unter Windows: Microsoft Edge WebView2, in Windows 10/11 enthalten).
Diese Datei: Verbindung zum Server (/api/...) und die Bruecke, die die Oberflaeche aufruft.

Bauen (unter Windows, macht GitHub automatisch, siehe .github/workflows/windows-programm.yml):
    pip install pywebview pyinstaller
    pyinstaller --onefile --windowed --name OneClick-Tuning --add-data "kunde/ui.html;." \
                --add-data "kunde/version.txt;." kunde/oneclick_kunde.py

Auto-Update: Beim Start wird version.json neben der .exe auf GitHub abgefragt. Ist die Build-Nummer
groesser als die eigene, wird die neue .exe geladen, per SHA-256 geprueft, gegen die laufende
getauscht (Windows erlaubt das Umbenennen einer laufenden .exe) und neu gestartet.
"""

import base64
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path

STANDARD_SERVER = os.environ.get("ONECLICK_SERVER", "https://oneclicksoulution.gh-mapping.de")
WHATSAPP_URL = "https://wa.me/4915568540674"
UPDATE_URL = os.environ.get("ONECLICK_UPDATE_URL", "https://github.com/Kgh56/oneclick-tuning/releases/download/programm")
MAX_GROESSE = 16 * 1024 * 1024
# Filter fuer den Speichern-Dialog. pywebview erlaubt im Namen nur Buchstaben, Ziffern und Leerzeichen
# (z. B. kein Bindestrich) - sonst bricht der Dialog ohne Meldung ab. Wird im Selbsttest geprueft.
DATEI_TYPEN = ("ECU Datei (*.bin)", "Alle Dateien (*.*)")


def paket_ordner() -> Path:
    # In der .exe liegen ui.html/version.txt im entpackten Ordner (sys._MEIPASS), sonst neben dieser Datei
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def build_nummer() -> int:
    """Fortlaufende Build-Nummer (schreibt GitHub beim Bauen in version.txt); 0 = Entwicklungsstand."""
    try:
        return int((paket_ordner() / "version.txt").read_text().strip())
    except (OSError, ValueError):
        return 0


VERSION = f"2.{build_nummer()}"


def datenordner() -> Path:
    basis = os.environ.get("APPDATA") or str(Path.home() / ".config")
    ordner = Path(basis) / "OneClickTuning"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def protokoll(text: str):
    """Fehler in %APPDATA%\\OneClickTuning\\fehler.log schreiben (zum Nachsehen bei Problemen)."""
    try:
        with open(datenordner() / "fehler.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {VERSION} {text}\n")
    except OSError:
        pass


def sicher(methode):
    """Bruecken-Methode absichern: jeder unerwartete Fehler wird zur Meldung in der Oberflaeche,
    statt dass der Knopf einfach nichts tut."""
    @functools.wraps(methode)
    def huelle(*args, **kwargs):
        try:
            return methode(*args, **kwargs)
        except Exception as e:
            protokoll(f"{methode.__name__}: {traceback.format_exc()}")
            return {"fehler": f"Unerwarteter Fehler: {e}"}
    return huelle


def dateiname_sauber(name: str) -> str:
    """Zeichen entfernen, die Windows in Dateinamen nicht erlaubt."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "file"


def freier_pfad(ordner: Path, name: str) -> Path:
    """name im ordner, bei Bedarf mit (2), (3) ... damit nichts ueberschrieben wird."""
    ziel = ordner / name
    n = 2
    while ziel.exists():
        ziel = ordner / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return ziel


def downloads_ordner() -> Path:
    ordner = Path.home() / "Downloads"
    return ordner if ordner.is_dir() else Path.home()


def ui_datei() -> Path:
    return paket_ordner() / "ui.html"


# ---------------------------------------------------------------------------
# Auto-Update
# ---------------------------------------------------------------------------

def herunterladen_url(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"OneClick-Programm/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


class Updater:
    def __init__(self, basis_url: str = UPDATE_URL, exe: Path = None, holen=herunterladen_url, eigene: int = None):
        self.basis_url = basis_url.rstrip("/")
        self.exe = Path(exe or sys.executable)
        self.holen = holen
        self.eigene = build_nummer() if eigene is None else eigene

    @property
    def alte_exe(self) -> Path:
        return self.exe.with_name(self.exe.stem + ".alt.exe")

    def pruefen(self):
        """Infos zur neuen Version ({"version", "sha256", "groesse"}) oder None, wenn aktuell."""
        info = json.loads(self.holen(f"{self.basis_url}/version.json", 20))
        return info if int(info["version"]) > self.eigene else None

    def installieren(self, info: dict) -> Path:
        daten = self.holen(f"{self.basis_url}/OneClick-Tuning.exe", 300)
        if hashlib.sha256(daten).hexdigest() != info["sha256"] or len(daten) < 1024 * 1024:
            raise RuntimeError("Der Download ist beschädigt. Bitte später nochmal versuchen.")
        # Laufende .exe beiseite schieben (Umbenennen geht unter Windows), neue an ihren Platz schreiben
        self.alte_exe.unlink(missing_ok=True)
        self.exe.rename(self.alte_exe)
        try:
            self.exe.write_bytes(daten)
        except OSError:
            self.alte_exe.rename(self.exe)   # zurueck, alte Version laeuft weiter
            raise
        return self.exe

    def aufraeumen(self):
        """Beim naechsten Start die beiseite geschobene alte Version loeschen."""
        try:
            self.alte_exe.unlink(missing_ok=True)
        except OSError:
            pass

    def neu_starten(self):
        # Eigene Umgebung zuruecksetzen, damit die neue .exe sauber als eigenes Programm startet
        umgebung = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(self.exe)], cwd=str(self.exe.parent), env=umgebung, close_fds=True, creationflags=flags)


# ---------------------------------------------------------------------------
# Verbindung zum Server
# ---------------------------------------------------------------------------

class Fehler(Exception):
    pass


class Api:
    def __init__(self, server: str):
        self.server = server.rstrip("/")

    def _anfrage(self, methode: str, pfad: str, daten: bytes = None, typ: str = None, timeout: int = 60):
        req = urllib.request.Request(self.server + pfad, data=daten, method=methode,
                                     headers={"User-Agent": f"OneClick-Programm/{VERSION}",
                                              **({"Content-Type": typ} if typ else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            try:
                text = json.loads(e.read()).get("fehler")
            except Exception:
                text = None
            if e.code == 403 and not text:
                text = "Das File ist noch nicht freigegeben."
            if e.code == 404 and not text:
                text = "Auftrag nicht gefunden (vielleicht schon gelöscht)."
            raise Fehler(text or f"Server-Fehler ({e.code}).")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise Fehler("Keine Verbindung zum Server. Bitte Internetverbindung prüfen.")

    def _json(self, *args, **kwargs) -> dict:
        return json.loads(self._anfrage(*args, **kwargs))

    def info(self) -> dict:
        return self._json("GET", "/api/info", timeout=15)

    def pruefen(self, dateiname: str, inhalt: bytes) -> dict:
        grenze = uuid.uuid4().hex
        name = dateiname.replace('"', "").replace("\r", "").replace("\n", "")
        koerper = (f'--{grenze}\r\nContent-Disposition: form-data; name="datei"; filename="{name}"\r\n'
                   f"Content-Type: application/octet-stream\r\n\r\n").encode() + inhalt + f"\r\n--{grenze}--\r\n".encode()
        return self._json("POST", "/api/pruefen", koerper, f"multipart/form-data; boundary={grenze}", timeout=180)

    def bestellen(self, aid: str, optionen: list, kontakt: str) -> dict:
        daten = json.dumps({"optionen": optionen, "kontakt": kontakt}).encode()
        return self._json("POST", f"/api/auftrag/{aid}/bestellen", daten, "application/json")

    def status(self, aid: str) -> dict:
        return self._json("GET", f"/api/auftrag/{aid}", timeout=20)

    def herunterladen(self, aid: str) -> bytes:
        return self._anfrage("GET", f"/api/auftrag/{aid}/download", timeout=180)


# ---------------------------------------------------------------------------
# Gespeicherte Einstellungen und Auftraege (pro Windows-Benutzer)
# ---------------------------------------------------------------------------

class Speicher:
    def __init__(self):
        self.datei = datenordner() / "daten.json"
        try:
            self.daten = json.loads(self.datei.read_text(encoding="utf-8"))
        except Exception:
            self.daten = {}
        self.daten.setdefault("server", STANDARD_SERVER)
        self.daten.setdefault("kontakt", "")
        self.daten.setdefault("auftraege", [])

    def speichern(self):
        tmp = self.datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.daten, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.datei)

    def auftrag_merken(self, a: dict):
        liste = [x for x in self.daten["auftraege"] if x["id"] != a["id"]]
        alt = next((x for x in self.daten["auftraege"] if x["id"] == a["id"]), {})
        eintrag = {**alt, **{k: a.get(k) for k in ("id", "datei", "zeit", "status", "status_text",
                                                    "option", "option_name", "grund", "ecu", "software")}}
        self.daten["auftraege"] = ([eintrag] + liste)[:200]
        self.speichern()


# ---------------------------------------------------------------------------
# Bruecke: diese Methoden ruft die Oberflaeche (ui.html) ueber window.pywebview.api auf.
# Fehler werden als {"fehler": text} zurueckgegeben, damit die Oberflaeche sie anzeigen kann.
# ---------------------------------------------------------------------------

class Bruecke:
    def __init__(self, speicher: Speicher = None, updater: Updater = None):
        self._speicher = speicher or Speicher()
        self._api = Api(self._speicher.daten["server"])
        self._fenster = None   # wird nach dem Erstellen des Fensters gesetzt
        # Auto-Update nur in der fertigen .exe (nicht beim Entwickeln und nicht im Selbsttest)
        aktiv = getattr(sys, "frozen", False) and not os.environ.get("ONECLICK_SELBSTTEST")
        self._updater = updater or (Updater() if aktiv else None)
        self._update_info = None
        if self._updater:
            self._updater.aufraeumen()

    @sicher
    def start(self) -> dict:
        d = self._speicher.daten
        ergebnis = {"server": d["server"], "kontakt": d["kontakt"], "auftraege": d["auftraege"],
                    "firma": None, "original": "original", "version": VERSION}
        try:
            info = self._api.info()
            ergebnis.update(firma=info.get("firma"), original=info.get("original", "original"))
        except Fehler as e:
            ergebnis["verbindung"] = str(e)
        return ergebnis

    @sicher
    def pruefen(self, dateiname: str, inhalt_base64: str) -> dict:
        try:
            inhalt = base64.b64decode(inhalt_base64)
        except Exception:
            return {"fehler": "Die Datei konnte nicht gelesen werden."}
        if len(inhalt) > MAX_GROESSE:
            return {"fehler": "Die Datei ist größer als 16 MB."}
        try:
            return self._api.pruefen(dateiname, inhalt)
        except Fehler as e:
            return {"fehler": str(e)}

    @sicher
    def bestellen(self, aid: str, optionen: list, kontakt: str) -> dict:
        self._speicher.daten["kontakt"] = (kontakt or "").strip()
        try:
            a = self._api.bestellen(aid, list(optionen), self._speicher.daten["kontakt"])
        except Fehler as e:
            self._speicher.speichern()
            return {"fehler": str(e)}
        self._speicher.auftrag_merken(a)
        return {"auftrag": a, "auftraege": self._speicher.daten["auftraege"]}

    @sicher
    def aktualisieren(self) -> dict:
        """Status aller wartenden Auftraege abfragen. 'geaendert' = neu freigegeben/abgelehnt."""
        geaendert = []
        for alt in [a for a in self._speicher.daten["auftraege"] if a.get("status") == "WARTET"]:
            try:
                neu = self._api.status(alt["id"])
            except Fehler:
                continue
            if neu["status"] != alt.get("status"):
                geaendert.append(neu)
            self._speicher.auftrag_merken(neu)
        return {"auftraege": self._speicher.daten["auftraege"], "geaendert": geaendert}

    @sicher
    def herunterladen(self, aid: str, ziel: str = None) -> dict:
        a = next((x for x in self._speicher.daten["auftraege"] if x["id"] == aid), None)
        if not a:
            return {"fehler": "Auftrag nicht gefunden."}
        # Erst laden, dann fragen wohin: so sieht der Kunde sofort, wenn es noch nicht freigegeben ist
        try:
            daten = self._api.herunterladen(aid)
        except Fehler as e:
            return {"fehler": str(e)}
        if not daten:
            return {"fehler": "Der Server hat eine leere Datei geschickt. Bitte melde dich bei uns."}
        vorschlag = dateiname_sauber(f"{Path(a.get('datei') or 'file').stem}_"
                                     f"{(a.get('option') or 'file').replace('+', '_')}.bin")
        if ziel is None:
            ziel = self._speicherort(vorschlag)
            if ziel is None:
                return {"abgebrochen": True}
        ziel = Path(ziel)
        try:
            ziel.write_bytes(daten)
        except OSError as e:
            # z. B. keine Schreibrechte im gewaehlten Ordner -> in "Downloads" ausweichen
            protokoll(f"herunterladen: {ziel}: {e}")
            ziel = freier_pfad(downloads_ordner(), vorschlag)
            ziel.write_bytes(daten)
        return {"pfad": str(ziel)}

    def _speicherort(self, vorschlag: str):
        """Speichern-Dialog von Windows. Klappt der nicht, direkt in den Downloads-Ordner."""
        try:
            import webview
            auswahl = self._fenster.create_file_dialog(webview.SAVE_DIALOG, directory=str(downloads_ordner()),
                                                       save_filename=vorschlag, file_types=DATEI_TYPEN)
        except Exception:
            protokoll(f"Speichern-Dialog: {traceback.format_exc()}")
            return freier_pfad(downloads_ordner(), vorschlag)
        if not auswahl:
            return None
        return auswahl if isinstance(auswahl, str) else auswahl[0]

    @sicher
    def ordner_zeigen(self, pfad: str) -> dict:
        """Explorer oeffnen und die gespeicherte Datei markieren."""
        if os.name == "nt" and Path(pfad).exists():
            subprocess.Popen(["explorer", "/select,", str(Path(pfad))])
        return {}

    @sicher
    def update_pruefen(self) -> dict:
        if not self._updater:
            return {"neu": False}
        try:
            self._update_info = self._updater.pruefen()
        except Exception as e:   # kein Internet, GitHub nicht erreichbar ... -> einfach weiter
            return {"neu": False, "fehler": str(e)}
        if not self._update_info:
            return {"neu": False}
        return {"neu": True, "version": f"2.{self._update_info['version']}", "aktuell": VERSION}

    @sicher
    def update_installieren(self) -> dict:
        if not (self._updater and self._update_info):
            return {"fehler": "Kein Update vorhanden."}
        try:
            self._updater.installieren(self._update_info)
            self._updater.neu_starten()
        except PermissionError:
            return {"fehler": "Keine Schreibrechte im Programm-Ordner. Bitte die neue Version von unserer Seite herunterladen."}
        except Exception as e:
            return {"fehler": f"Update fehlgeschlagen: {e}"}
        threading.Thread(target=self._beenden, daemon=True).start()
        return {"ok": True}

    def _beenden(self):
        time.sleep(1.2)   # Oberflaeche zeigt kurz "Startet neu"
        try:
            if self._fenster:
                self._fenster.destroy()
        finally:
            os._exit(0)

    @sicher
    def vollbild(self) -> dict:
        if self._fenster:
            self._fenster.toggle_fullscreen()
        return {}

    @sicher
    def whatsapp(self) -> dict:
        import webbrowser
        webbrowser.open(WHATSAPP_URL)
        return {}

    @sicher
    def entfernen(self, aid: str) -> dict:
        self._speicher.daten["auftraege"] = [x for x in self._speicher.daten["auftraege"] if x["id"] != aid]
        self._speicher.speichern()
        return {"auftraege": self._speicher.daten["auftraege"]}

    @sicher
    def server_setzen(self, adresse: str) -> dict:
        adresse = (adresse or "").strip().rstrip("/")
        if not adresse:
            return {"fehler": "Bitte eine Adresse eingeben."}
        if not adresse.startswith(("https://", "http://")):
            adresse = "https://" + adresse
        self._speicher.daten["server"] = adresse
        self._speicher.speichern()
        self._api = Api(adresse)
        return self.start()


def selbsttest(fenster, ergebnis_datei: str):
    """Fuer den automatischen Test beim Bauen: Fenster oeffnen, pruefen ob Oberflaeche und
    Bruecke laufen, Ergebnis in eine Datei schreiben, Fenster schliessen."""
    geladen = fenster.events.loaded.wait(90)
    time.sleep(4)
    try:
        from webview.util import parse_file_type
        for typ in DATEI_TYPEN:   # wirft ValueError, wenn pywebview den Filter nicht akzeptiert
            parse_file_type(typ)
        erg = fenster.evaluate_js("JSON.stringify({ui: !!document.querySelector('#zone'), dialog: true, "
                                  "api: !!(window.pywebview && window.pywebview.api), "
                                  "intro_weg: document.querySelector('#intro').classList.contains('weg')})")
    except Exception as e:
        erg = json.dumps({"fehler": str(e)})
    Path(ergebnis_datei).write_text(erg if geladen else '{"fehler": "Seite nicht geladen"}', encoding="utf-8")
    fenster.destroy()


def dunkle_titelleiste(fenster):
    """Macht die Windows-Titelleiste schwarz (Windows 10: Dunkelmodus, Windows 11 zusätzlich Farbe)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = fenster.native.Handle.ToInt32()
        dwm = ctypes.windll.dwmapi
        for attribut, wert in ((20, 1), (19, 1), (35, 0x000000), (36, 0xFFFFFF), (34, 0x000000)):
            # 20/19 = Dunkelmodus (neu/alt), 35 = Leistenfarbe, 36 = Schriftfarbe, 34 = Rahmenfarbe
            v = ctypes.c_int(wert)
            dwm.DwmSetWindowAttribute(hwnd, attribut, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def main():
    import webview
    bruecke = Bruecke()
    fenster = webview.create_window("OneClick Tuning", url=ui_datei().as_uri(), js_api=bruecke,
                                    width=1280, height=820, min_size=(820, 620), background_color="#000000",
                                    maximized=True)
    bruecke._fenster = fenster
    fenster.events.shown += lambda: dunkle_titelleiste(fenster)
    test = os.environ.get("ONECLICK_SELBSTTEST")
    if test:
        webview.start(selbsttest, (fenster, test))
    else:
        webview.start(debug=bool(os.environ.get("ONECLICK_DEBUG")))


if __name__ == "__main__":
    main()
