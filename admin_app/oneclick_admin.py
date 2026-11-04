#!/usr/bin/env python3
"""
OneClick Admin - Mac-App fuer den Betreiber (nicht fuer Kunden).

Ein eigenes Fenster fuer den Admin-Bereich des Servers, im Design des Kundenprogramms.
Die App enthaelt keine Daten und keine Passwoerter: Anmeldung wie im Browser mit Passwort und
Code aus der Authenticator-App. Der Server erkennt die App an der Kennung "OneClickAdmin/" und
zeigt dann das App-Design (Seitenleiste). Neue Auftraege/Ticket-Antworten kommen als Mac-Mitteilung.

Bauen macht GitHub automatisch: .github/workflows/mac-admin.yml
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SERVER = os.environ.get("ONECLICK_SERVER", "https://oneclicksoulution.gh-mapping.de").rstrip("/")
NAME = "OneClick Admin"


def build_nummer() -> int:
    try:
        ordner = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return int((ordner / "version.txt").read_text().strip())
    except (OSError, ValueError):
        return 0


VERSION = f"1.{build_nummer()}"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
              f"Version/17.0 Safari/605.1.15 OneClickAdmin/{VERSION}")


def datenordner() -> Path:
    ordner = Path.home() / "Library" / "Application Support" / "OneClick-Admin"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def applescript_text(text: str) -> str:
    """Text sicher in ein AppleScript einsetzen (Anfuehrungszeichen/Backslashes maskieren, kurz halten)."""
    text = str(text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return text[:200]


class Bruecke:
    def __init__(self):
        self._fenster = None

    def version(self):
        return VERSION

    def melden(self, titel: str, text: str = ""):
        """Mac-Mitteilung (oben rechts), z. B. bei neuen Auftraegen. Funktioniert auch im Hintergrund."""
        if sys.platform != "darwin":
            return False
        skript = f'display notification "{applescript_text(text)}" with title "{applescript_text(titel)}" sound name "Glass"'
        try:
            subprocess.run(["osascript", "-e", skript], timeout=5, check=False, capture_output=True)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def neu_laden(self):
        self._fenster.load_url(SERVER + "/admin")


OFFLINE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#060b18;color:#e8eefc;font:15px/1.5 -apple-system,system-ui,sans-serif}
.k{max-width:460px;padding:34px 38px;border-radius:18px;background:#111827;border:1px solid rgba(110,150,255,.2);text-align:center}
h1{font-size:21px;margin:0 0 8px}p{color:#8d9bb8;margin:0 0 22px}
button{border:1px solid #6ea2ff;border-radius:12px;padding:11px 22px;font:inherit;font-weight:700;color:#fff;cursor:pointer;
background:linear-gradient(180deg,#3d86ff,#1d5fe6)}</style></head><body><div class="k">
<h1>Keine Verbindung</h1><p>Der Server ist gerade nicht erreichbar. Bitte Internetverbindung prüfen.</p>
<button onclick="pywebview.api.neu_laden()">Erneut versuchen</button></div></body></html>"""


def server_erreichbar() -> bool:
    try:
        req = urllib.request.Request(SERVER + "/login", headers={"User-Agent": USER_AGENT})
        urllib.request.urlopen(req, timeout=8).read(1)
        return True
    except Exception:
        return False


def selbsttest(fenster, ergebnis_datei: str):
    """Fuer den Build auf GitHub: Fenster offen, Bruecke erreichbar, Kennung gesetzt."""
    erg = {"ui": False, "api": False}
    try:
        for _ in range(60):
            if fenster.evaluate_js("document.readyState") == "complete":
                erg["ui"] = True
                break
            time.sleep(1)
        for _ in range(60):
            if fenster.evaluate_js("!!(window.pywebview && window.pywebview.api && window.pywebview.api.melden)"):
                erg["api"] = True
                break
            time.sleep(1)
        erg["kennung"] = "OneClickAdmin/" in str(fenster.evaluate_js("navigator.userAgent"))
        erg["version"] = VERSION
    finally:
        Path(ergebnis_datei).write_text(json.dumps(erg))
        fenster.destroy()


def main():
    import webview
    test = os.environ.get("ONECLICK_SELBSTTEST")
    bruecke = Bruecke()
    if test:
        start = {"html": "<!doctype html><html><body>Selbsttest</body></html>"}
    elif server_erreichbar():
        start = {"url": SERVER + "/admin"}
    else:
        start = {"html": OFFLINE}
    fenster = webview.create_window(NAME, js_api=bruecke, width=1440, height=900, min_size=(1100, 700),
                                    background_color="#060b18", **start)
    bruecke._fenster = fenster
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # z. B. Stripe-Dashboard im Browser
    webview.settings["ALLOW_DOWNLOADS"] = True                  # Originale, Archiv-ZIP, Ticket-Dateien speichern
    if test:
        webview.start(selbsttest, (fenster, test), private_mode=False, storage_path=str(datenordner()), user_agent=USER_AGENT)
    else:
        webview.start(private_mode=False, storage_path=str(datenordner()), user_agent=USER_AGENT)


if __name__ == "__main__":
    main()
