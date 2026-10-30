#!/usr/bin/env python3
"""
OneClick Tuning - Windows-Programm fuer Kunden

Oberflaeche: kunde/ui.html (HTML/CSS/JS) in einem eigenen Fenster ueber pywebview
(unter Windows: Microsoft Edge WebView2, in Windows 10/11 enthalten).
Diese Datei: Verbindung zum Server (/api/...) und die Bruecke, die die Oberflaeche aufruft.

Bauen (unter Windows):
    pip install pywebview pyinstaller
    pyinstaller --onefile --windowed --name OneClick-Tuning --add-data "kunde/ui.html;." kunde/oneclick_kunde.py
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

STANDARD_SERVER = os.environ.get("ONECLICK_SERVER", "https://oneclicksoulution.gh-mapping.de")
VERSION = "2.0"
MAX_GROESSE = 16 * 1024 * 1024


def datenordner() -> Path:
    basis = os.environ.get("APPDATA") or str(Path.home() / ".config")
    ordner = Path(basis) / "OneClickTuning"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def ui_datei() -> Path:
    # In der .exe liegt ui.html im entpackten Ordner (sys._MEIPASS), sonst neben dieser Datei
    basis = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return basis / "ui.html"


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
    def __init__(self, speicher: Speicher = None):
        self._speicher = speicher or Speicher()
        self._api = Api(self._speicher.daten["server"])
        self._fenster = None   # wird nach dem Erstellen des Fensters gesetzt

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

    def bestellen(self, aid: str, optionen: list, kontakt: str) -> dict:
        self._speicher.daten["kontakt"] = (kontakt or "").strip()
        try:
            a = self._api.bestellen(aid, list(optionen), self._speicher.daten["kontakt"])
        except Fehler as e:
            self._speicher.speichern()
            return {"fehler": str(e)}
        self._speicher.auftrag_merken(a)
        return {"auftrag": a, "auftraege": self._speicher.daten["auftraege"]}

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

    def herunterladen(self, aid: str, ziel: str = None) -> dict:
        a = next((x for x in self._speicher.daten["auftraege"] if x["id"] == aid), None)
        if not a:
            return {"fehler": "Auftrag nicht gefunden."}
        if ziel is None:   # Speichern-Dialog von Windows
            import webview
            vorschlag = f"{Path(a['datei']).stem}_{(a.get('option') or 'file').replace('+', '_')}.bin"
            auswahl = self._fenster.create_file_dialog(webview.SAVE_DIALOG, save_filename=vorschlag,
                                                       file_types=("ECU-File (*.bin)", "Alle Dateien (*.*)"))
            if not auswahl:
                return {"abgebrochen": True}
            ziel = auswahl if isinstance(auswahl, str) else auswahl[0]
        try:
            Path(ziel).write_bytes(self._api.herunterladen(aid))
        except (Fehler, OSError) as e:
            return {"fehler": str(e)}
        return {"pfad": str(ziel)}

    def entfernen(self, aid: str) -> dict:
        self._speicher.daten["auftraege"] = [x for x in self._speicher.daten["auftraege"] if x["id"] != aid]
        self._speicher.speichern()
        return {"auftraege": self._speicher.daten["auftraege"]}

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
    import time
    geladen = fenster.events.loaded.wait(90)
    time.sleep(4)
    try:
        erg = fenster.evaluate_js("JSON.stringify({ui: !!document.querySelector('#zone'), "
                                  "api: !!(window.pywebview && window.pywebview.api), "
                                  "intro_weg: document.querySelector('#intro').classList.contains('weg')})")
    except Exception as e:
        erg = json.dumps({"fehler": str(e)})
    Path(ergebnis_datei).write_text(erg if geladen else '{"fehler": "Seite nicht geladen"}', encoding="utf-8")
    fenster.destroy()


def main():
    import webview
    bruecke = Bruecke()
    fenster = webview.create_window("OneClick Tuning", url=ui_datei().as_uri(), js_api=bruecke,
                                    width=1120, height=780, min_size=(820, 620), background_color="#000000")
    bruecke._fenster = fenster
    test = os.environ.get("ONECLICK_SELBSTTEST")
    if test:
        webview.start(selbsttest, (fenster, test))
    else:
        webview.start(debug=bool(os.environ.get("ONECLICK_DEBUG")))


if __name__ == "__main__":
    main()
