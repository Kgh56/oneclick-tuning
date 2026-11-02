#!/usr/bin/env python3
"""
OneClick Solutions - Windows-Programm fuer Kunden

Ein eigenes Programmfenster (ohne Browser-Leisten, mit eigener Titelleiste) fuer das Kunden-Portal.
Die Oberflaeche kommt live vom Server (web/kunde.html) - Design-Updates sind damit sofort bei allen
Kunden, ohne neue .exe. Das Programm selbst liefert nur:
  - das Fenster (Minimieren / Maximieren / Schliessen ueber die Knoepfe oben rechts in der Oberflaeche)
  - "Speichern unter ..." fuer heruntergeladene Files
  - Auto-Update der .exe (version.json neben der .exe auf GitHub)
  - eine Seite "Keine Verbindung", wenn der Server nicht erreichbar ist

Unter Windows nutzt pywebview Microsoft Edge WebView2 (in Windows 10/11 enthalten).
Bauen macht GitHub automatisch: .github/workflows/windows-programm.yml
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SERVER = os.environ.get("ONECLICK_SERVER", "https://oneclicksoulution.gh-mapping.de").rstrip("/")
UPDATE_URL = os.environ.get("ONECLICK_UPDATE_URL", "https://github.com/Kgh56/oneclick-tuning/releases/download/programm")
PROGRAMM_NAME = "OneClick Solutions"
EXE_NAME = "OneClick-Solutions.exe"
# pywebview erlaubt im Filternamen nur Buchstaben, Ziffern und Leerzeichen (sonst bricht der Dialog still ab)
DATEI_TYPEN = ("ECU Datei (*.bin)", "Alle Dateien (*.*)")


def paket_ordner() -> Path:
    # In der .exe liegt version.txt im entpackten Ordner (sys._MEIPASS), sonst neben dieser Datei
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def build_nummer() -> int:
    """Fortlaufende Build-Nummer (schreibt GitHub beim Bauen in version.txt); 0 = Entwicklungsstand."""
    try:
        return int((paket_ordner() / "version.txt").read_text().strip())
    except (OSError, ValueError):
        return 0


VERSION = f"3.{build_nummer()}"
# Mit dieser Kennung laesst der Server das Programm auf die Kundenseite (Browser bekommen die Download-Seite)
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 "
              f"Safari/537.36 Edg/130.0.0.0 OneClickProgramm/{VERSION}")


def datenordner() -> Path:
    """Hier merkt sich das Fenster seine Daten (u. a. 'Meine Auftraege') - bleibt auch nach Updates."""
    basis = os.environ.get("APPDATA") or str(Path.home() / ".config")
    ordner = Path(basis) / "OneClick-Tuning"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def holen(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Auto-Update der .exe
# ---------------------------------------------------------------------------

class Updater:
    def __init__(self, basis_url: str = UPDATE_URL, exe: Path = None, holen=holen, eigene: int = None):
        self.basis_url = basis_url.rstrip("/")
        self.exe = Path(exe or sys.executable)
        self.holen = holen
        self.eigene = build_nummer() if eigene is None else eigene

    @property
    def alte_exe(self) -> Path:
        return self.exe.with_name(self.exe.stem + ".alt.exe")

    def pruefen(self):
        """Infos zur neuen Version ({"version", "sha256", "groesse"}) oder None, wenn aktuell."""
        info = json.loads(self.holen(f"{self.basis_url}/version.json?t={int(time.time())}", 10))
        return info if int(info["version"]) > self.eigene else None

    def installieren(self, info: dict) -> Path:
        daten = self.holen(f"{self.basis_url}/{EXE_NAME}", 300)
        if hashlib.sha256(daten).hexdigest() != info["sha256"] or len(daten) < 1024 * 1024:
            raise RuntimeError("Der Download ist beschädigt.")
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
        try:
            self.alte_exe.unlink(missing_ok=True)
        except OSError:
            pass

    def neu_starten(self):
        umgebung = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(self.exe)], cwd=str(self.exe.parent), env=umgebung, close_fds=True, creationflags=flags)


# ---------------------------------------------------------------------------
# Bruecke: diese Funktionen ruft die Oberflaeche ueber window.pywebview.api auf
# ---------------------------------------------------------------------------

def dateiname_aus(kopf: str, standard: str = "file.bin") -> str:
    """Dateiname aus dem Content-Disposition-Kopf, ohne Pfad und ohne verbotene Zeichen."""
    m = re.search(r"filename\*=UTF-8''([^;]+)", kopf or "", re.I) or re.search(r'filename="?([^";]+)"?', kopf or "", re.I)
    name = urllib.parse.unquote(m.group(1)) if m else standard
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", Path(name).name).strip(" .")
    return name or standard


class Bruecke:
    def __init__(self):
        self._fenster = None
        self._gross = False

    def version(self):
        return VERSION

    def minimieren(self):
        self._fenster.minimize()

    def maximieren(self):
        if self._gross:
            self._fenster.restore()
        else:
            self._fenster.maximize()
        self._gross = not self._gross

    def schliessen(self):
        self._fenster.destroy()

    def neu_laden(self):
        self._fenster.load_url(SERVER + "/")

    # --- Update-Knopf in der Oberflaeche ---
    def update_pruefen(self):
        """{"version": "3.15", "neu": 16 oder None}. Im Entwicklungsstand (keine .exe) gibt es kein Programm-Update."""
        if not getattr(sys, "frozen", False):
            return {"version": VERSION, "neu": None}
        try:
            info = Updater().pruefen()
        except Exception:
            return {"version": VERSION, "fehler": "Update-Server gerade nicht erreichbar. Bitte später nochmal versuchen."}
        return {"version": VERSION, "neu": int(info["version"]) if info else None}

    def update_installieren(self):
        """Neue .exe laden, pruefen (SHA-256), gegen die laufende tauschen und neu starten."""
        if not getattr(sys, "frozen", False):
            return {"fehler": "Nur im installierten Programm möglich."}
        try:
            u = Updater()
            info = u.pruefen()
            if not info:
                return {"aktuell": True}
            u.installieren(info)
            u.neu_starten()
        except Exception as e:
            return {"fehler": f"Update fehlgeschlagen: {e}"}
        threading.Timer(0.8, self._fenster.destroy).start()   # Antwort noch an die Oberflaeche, dann schliessen
        return {"ok": True}

    def speichern(self, url: str):
        """File vom Server holen und ueber 'Speichern unter ...' ablegen. Nur Adressen unseres Servers."""
        if not url.startswith(SERVER + "/api/auftrag/"):
            return {"fehler": "Ungültige Adresse."}
        import webview
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                daten, name = r.read(), dateiname_aus(r.headers.get("Content-Disposition", ""))
        except urllib.error.HTTPError as e:
            try:
                text = json.loads(e.read()).get("fehler")
            except Exception:
                text = None
            return {"fehler": text or f"Server-Fehler ({e.code})."}
        except (urllib.error.URLError, OSError):
            return {"fehler": "Keine Verbindung zum Server. Bitte Internetverbindung prüfen."}
        ziel = self._fenster.create_file_dialog(webview.SAVE_DIALOG, directory=str(Path.home() / "Downloads"),
                                               save_filename=name, file_types=DATEI_TYPEN)
        if not ziel:
            return {"abgebrochen": True}
        pfad = Path(ziel if isinstance(ziel, str) else ziel[0])
        pfad.write_bytes(daten)
        return {"pfad": str(pfad), "app": True}


OFFLINE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#0d0f14;color:#e8ecf4;font:15px/1.5 "Segoe UI",system-ui,sans-serif}
.k{max-width:460px;padding:34px 38px;border-radius:16px;background:#171a21;border:1px solid #262b36;text-align:center}
h1{font-size:21px;margin:0 0 8px}p{color:#8b93a5;margin:0 0 22px}
button{border:1px solid #4d92ff;border-radius:10px;padding:11px 22px;font:inherit;font-weight:700;color:#fff;cursor:pointer;
background:linear-gradient(180deg,#3b86ff,#1f5fe0)}</style></head><body><div class="k">
<h1>Keine Verbindung</h1><p>Der OneClick-Solutions-Server ist gerade nicht erreichbar. Bitte Internetverbindung prüfen.</p>
<button onclick="pywebview.api.neu_laden()">Erneut versuchen</button></div></body></html>"""


def server_erreichbar() -> bool:
    try:
        holen(SERVER + "/api/info", 8)
        return True
    except Exception:
        return False


def selbsttest(fenster, ergebnis_datei: str):
    """Fuer den Build auf GitHub: Fenster offen, Bruecke erreichbar, Speichern-Funktion vorhanden."""
    erg = {"ui": False, "api": False, "speichern": False}
    try:
        for _ in range(60):
            if fenster.evaluate_js("document.readyState") == "complete":
                erg["ui"] = True
                break
            time.sleep(1)
        for _ in range(60):
            if fenster.evaluate_js("!!(window.pywebview && window.pywebview.api && window.pywebview.api.version)"):
                erg["api"] = True
                break
            time.sleep(1)
        erg["speichern"] = bool(fenster.evaluate_js("typeof window.pywebview.api.speichern === 'function'"))
        erg["kennung"] = "OneClickProgramm/" in str(fenster.evaluate_js("navigator.userAgent"))
        erg["update"] = bool(fenster.evaluate_js("typeof window.pywebview.api.update_pruefen === 'function'"))
        erg["version"] = VERSION
    finally:
        Path(ergebnis_datei).write_text(json.dumps(erg))
        fenster.destroy()


def main():
    import webview
    test = os.environ.get("ONECLICK_SELBSTTEST")
    updater = Updater()
    if getattr(sys, "frozen", False) and not test:
        updater.aufraeumen()
        try:
            info = updater.pruefen()
            if info:
                updater.installieren(info)
                updater.neu_starten()
                return
        except Exception:
            pass   # ohne Update weiter - beim naechsten Start nochmal
    bruecke = Bruecke()
    if test:
        start = {"html": "<!doctype html><html><body>Selbsttest</body></html>"}
    elif server_erreichbar():
        start = {"url": SERVER + "/"}
    else:
        start = {"html": OFFLINE}
    fenster = webview.create_window(PROGRAMM_NAME, js_api=bruecke, width=1440, height=900, min_size=(1100, 700),
                                    frameless=True, easy_drag=False, background_color="#0d0f14", **start)
    bruecke._fenster = fenster
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    # private_mode=False + eigener Ordner: "Meine Auftraege" bleiben nach dem Schliessen erhalten
    if test:
        webview.start(selbsttest, (fenster, test), private_mode=False, storage_path=str(datenordner()), user_agent=USER_AGENT)
    else:
        webview.start(private_mode=False, storage_path=str(datenordner()), user_agent=USER_AGENT,
                      debug=bool(os.environ.get("ONECLICK_DEBUG")))


if __name__ == "__main__":
    main()
