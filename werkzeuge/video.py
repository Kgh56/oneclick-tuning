#!/usr/bin/env python3
"""
Fuer Claude: Videos aus dem Admin-Bereich "Video" holen und das fertige Video dort abgeben.

    python3 werkzeuge/video.py --server https://<admin-domain> liste
    python3 werkzeuge/video.py --server https://<admin-domain> holen <id> <zielordner>
    python3 werkzeuge/video.py --server https://<admin-domain> abgeben <id|neu> <datei> [--wunsch "..."]

Statt --server geht auch die Umgebungsvariable ONECLICK_SERVER. Der Schluessel (Admin -> Video -> "Zugang fuer Claude")
wird normalerweise vom Netzwerk-Proxy der Claude-Umgebung eingesetzt; zum lokalen Testen VIDEO_SCHLUESSEL setzen.
Loeschen kann dieses Werkzeug nichts - das macht der Server selbst (siehe CLAUDE.md).
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TEIL = 8 * 1024 * 1024   # wie VIDEO_TEIL in app.py


def anfrage(server: str, pfad: str, daten: bytes = None, kopf: dict = None, methode: str = None):
    kopf = {"User-Agent": "video-werkzeug", **(kopf or {})}
    if os.environ.get("VIDEO_SCHLUESSEL"):
        kopf["Authorization"] = "Bearer " + os.environ["VIDEO_SCHLUESSEL"]
    return urllib.request.Request(server.rstrip("/") + pfad, data=daten, headers=kopf, method=methode)


def json_antwort(req) -> tuple:
    """(HTTP-Status, JSON). Status 0 = keine Verbindung."""
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"fehler": f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError) as e:
        return 0, {"fehler": str(e)}


def alle(server: str) -> list:
    status, d = json_antwort(anfrage(server, "/api/video"))
    if status != 200:
        sys.exit(f"Liste nicht abrufbar ({status}): {d.get('fehler')}")
    return d["videos"]


def liste(server: str, als_json: bool = False):
    videos = alle(server)
    if als_json:
        print(json.dumps(videos, ensure_ascii=False, indent=1))
        return
    if not videos:
        print("Keine Videos.")
    for v in videos:
        clips = ", ".join(f"{c['nr']}: {c['name']} ({c['groesse'] / 1024 ** 2:.0f} MB"
                          + ("" if c["fertig"] else f", erst {c.get('hochgeladen', 0) * 100 // c['groesse']} % da") + ")"
                          for c in v["clips"]) or "keine Clips"
        print(f"{v['id']}  {v['status']:7}  {v['zeit']}  löscht {v['loescht_um']}\n"
              f"    Wunsch: {v['wunsch'] or '-'}\n    Clips: {clips}"
              + (f"\n    Fertig: {v['ergebnis']['name']}{' (heruntergeladen)' if v['abgeholt'] else ''}" if v["ergebnis"] else ""))


def holen(server: str, vid: str, ziel: Path):
    v = next((v for v in alle(server) if v["id"] == vid), None)
    if not v:
        sys.exit(f"Vorgang {vid} nicht gefunden.")
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "wunsch.txt").write_text(v["wunsch"] + "\n")
    for c in v["clips"]:
        if not c["fertig"]:
            print(f"Clip {c['nr']} ist noch nicht fertig hochgeladen, übersprungen.")
            continue
        datei = ziel / f"{c['nr']:02d}_{re.sub(r'[^A-Za-z0-9._-]+', '_', c['name'])}"
        for versuch in range(12):
            ist = datei.stat().st_size if datei.exists() else 0
            if ist == c["groesse"]:
                break
            kopf = {"Range": f"bytes={ist}-"} if ist else {}
            try:
                with urllib.request.urlopen(anfrage(server, f"/api/video/{vid}/clip/{c['nr']}", kopf=kopf), timeout=180) as r, \
                        open(datei, "ab" if ist and r.status == 206 else "wb") as f:
                    while block := r.read(1 << 20):
                        f.write(block)
            except (urllib.error.URLError, OSError) as e:
                print(f"Clip {c['nr']}: {e} - neuer Versuch", file=sys.stderr)
                time.sleep(min(30, 2 * (versuch + 1)))
        else:
            sys.exit(f"Clip {c['nr']} konnte nicht vollständig geladen werden.")
        print(f"{datei}  ({c['groesse'] / 1024 ** 2:.0f} MB)")
    print(f"Wunsch: {v['wunsch'] or '-'}")


def abgeben(server: str, vid: str, datei: Path, wunsch: str = ""):
    if not datei.is_file() or datei.stat().st_size == 0:
        sys.exit(f"{datei} fehlt oder ist leer - nichts abgegeben.")
    if vid == "neu":
        status, d = json_antwort(anfrage(server, "/api/video/neu", json.dumps({"wunsch": wunsch}).encode(),
                                         {"Content-Type": "application/json"}, "POST"))
        if status != 200:
            sys.exit(f"Neuer Vorgang ging nicht ({status}): {d.get('fehler')}")
        vid = d["id"]
    gesamt, start, fehler, gemeldet = datei.stat().st_size, 0, 0, -1
    name = urllib.parse.quote(datei.name)
    with open(datei, "rb") as f:
        while start < gesamt:
            f.seek(start)
            stueck = f.read(TEIL)
            status, d = json_antwort(anfrage(server, f"/api/video/{vid}/ergebnis?start={start}&gesamt={gesamt}&name={name}",
                                             stueck, {"Content-Type": "application/octet-stream"}, "POST"))
            if status in (200, 409) and isinstance(d.get("start"), int) and (status == 200 or d["start"] != start):
                start, fehler = d["start"], 0
                if start * 10 // gesamt != gemeldet:
                    gemeldet = start * 10 // gesamt
                    print(f"{start * 100 // gesamt} %")
                continue
            if status in (0, 429) or status >= 500 and status != 507:
                fehler += 1
                if fehler > 10:
                    sys.exit(f"Abgabe abgebrochen: {d.get('fehler')}")
                time.sleep(min(60, 3 * fehler))
                continue
            sys.exit(f"Abgabe abgelehnt ({status}): {d.get('fehler')}")
    # Gegenprobe beim Server: liegt das fertige Video wirklich in voller Groesse dort?
    v = next((v for v in alle(server) if v["id"] == vid), None)
    if not v or v["status"] != "fertig" or (v["ergebnis"] or {}).get("groesse") != gesamt:
        sys.exit(f"Abgabe nicht bestätigt: {json.dumps(v, ensure_ascii=False)}")
    print(f"Fertig abgegeben: Vorgang {vid} ({gesamt / 1024 ** 2:.1f} MB), wird gelöscht spätestens {v['loescht_um']}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default=os.environ.get("ONECLICK_SERVER"))
    p.add_argument("befehl", choices=("liste", "holen", "abgeben"))
    p.add_argument("id", nargs="?")
    p.add_argument("pfad", nargs="?")
    p.add_argument("--wunsch", default="")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    if not a.server:
        p.error("--server fehlt (oder ONECLICK_SERVER setzen)")
    if a.befehl == "liste":
        liste(a.server, a.json)
    elif not a.id or not a.pfad:
        p.error(f"{a.befehl} braucht <id> und <pfad>")
    elif a.befehl == "holen":
        holen(a.server, a.id, Path(a.pfad))
    else:
        abgeben(a.server, a.id, Path(a.pfad), a.wunsch)


if __name__ == "__main__":
    main()
