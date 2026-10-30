#!/usr/bin/env python3
"""
OneClick Tuning - Webseite

Start:
    python app.py admin <name>     Admin anlegen (fragt nach Passwort)
    python app.py telegram-id      Chat-ID fuer Telegram herausfinden
    python app.py telegram-test    Testnachricht an Telegram senden
    python app.py                  Server starten (http://localhost:5000, Admin unter /login)

Kunden arbeiten auf der Startseite (web/kunde.html), die ueber /api/... mit
diesem Server spricht: Original hochladen -> 100-%-Treffer im Archiv -> nur die verfuegbaren
Loesungen werden angeboten -> Auftrag -> Download erst nach Freigabe durch den Admin
(Telegram-Knopf oder Admin-Bereich). Nichts Passendes: Anfrage (Ticket) mit Fahrzeugdaten.
"""

import getpass
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path, PurePosixPath

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

import oneclick

BASE = Path(__file__).resolve().parent
AUFTRAEGE = BASE / "auftraege"
BENUTZER_DATEI = BASE / "benutzer.json"
CONFIG_DATEI = BASE / "config.json"
SECRET_DATEI = BASE / ".secret_key"
KUNDENSEITE = BASE / "web" / "kunde.html"



class OptionNamen(dict):
    """Anzeigenamen der Loesungen. Kombinationen ('stage1+startstopp') werden zu
    'Stage 1 + Start/Stopp aus'; unbekannte (z. B. geloeschte) zeigen ihren Schluessel."""
    def __missing__(self, key):
        if key and "+" in key:
            return " + ".join(self[k] for k in key.split("+"))
        return key


def option_namen() -> OptionNamen:
    return OptionNamen({**oneclick.optionen(), oneclick.ORIGINAL: oneclick.ORIGINAL_NAME})


# ENTWURF: hochgeladen, Kunde waehlt noch die Option; danach entscheidet der Admin
STATUS_TEXT = {
    "ENTWURF": "Option wählen",
    "WARTET": "Wartet auf Freigabe",
    "FREIGEGEBEN": "Freigegeben",
    "ABGELEHNT": "Abgelehnt",
}
# art: wie der 100-%-Treffer zustande kam
ART_TEXT = {
    "identisch": "File identisch mit Archiv",
    "gleiche Stellen": "Alle Tuning-Stellen identisch",
    "softwarenummer": "Treffer über Softwarenummer – bitte prüfen",
    "eigenes File": "Eigenes File",
    "anfrage": "Anfrage – File muss bearbeitet werden",
}
# Fahrzeugdaten einer Anfrage: (Feld, Bezeichnung, Pflicht)
FAHRZEUG_FELDER = [("marke", "Marke", True), ("modell", "Modell", True), ("baujahr", "Baujahr", True),
                   ("motor", "Motor / Leistung", True), ("motorcode", "Motorcode", False),
                   ("getriebe", "Getriebe", False)]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
if not SECRET_DATEI.exists():
    SECRET_DATEI.write_text(secrets.token_hex(32))
app.secret_key = SECRET_DATEI.read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

sperre = threading.Lock()
index_sperre = threading.Lock()
telegram_chats = {}   # zuletzt gesehene Chats (fuer die Einrichtung im Admin-Bereich)
versuche = {}         # (art, ip) -> Zeitstempel, gegen Passwort-Raten und Upload-Flut


# ---------------------------------------------------------------------------
# Daten
# ---------------------------------------------------------------------------

def lade_config() -> dict:
    return json.loads(CONFIG_DATEI.read_text()) if CONFIG_DATEI.exists() else {}


def json_speichern(pfad: Path, daten):
    """Erst komplett in eine Temp-Datei schreiben, dann in einem Schritt austauschen.
    So liest niemand (z. B. die Statusabfrage) eine halb geschriebene Datei."""
    tmp = pfad.with_name(f".{pfad.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(daten, indent=2, ensure_ascii=False))
    os.replace(tmp, pfad)


def speichere_config(aenderungen: dict):
    cfg = lade_config()
    cfg.update(aenderungen)
    json_speichern(CONFIG_DATEI, cfg)


def lade_benutzer() -> dict:
    return json.loads(BENUTZER_DATEI.read_text()) if BENUTZER_DATEI.exists() else {}


def speichere_auftrag(auftrag: dict):
    json_speichern(AUFTRAEGE / auftrag["id"] / "auftrag.json", auftrag)


def finde_auftrag(aid: str):
    if not re.fullmatch(r"[0-9a-f]{32}", aid):   # Auftragsnummern sind immer uuid4().hex
        return None
    pfad = AUFTRAEGE / aid / "auftrag.json"
    return json.loads(pfad.read_text()) if pfad.exists() else None


def lade_auftrag(aid: str) -> dict:
    auftrag = finde_auftrag(aid)
    if auftrag is None:
        abort(404)
    return auftrag


def alle_auftraege() -> list:
    if not AUFTRAEGE.exists():
        return []
    liste = []
    for p in AUFTRAEGE.glob("*/auftrag.json"):
        try:
            liste.append(json.loads(p.read_text()))
        except (OSError, ValueError):   # gerade geloescht/kaputt: diese eine Datei ueberspringen
            continue
    return sorted(liste, key=lambda a: a.get("zeit", ""), reverse=True)


def hat_file(aid: str) -> bool:
    return (AUFTRAEGE / aid / "ergebnis.bin").exists()


def entscheide(aid: str, freigeben: bool, grund: str = "", wer: str = "") -> str:
    """Auftrag freigeben oder ablehnen. Wird von Webseite und Telegram genutzt."""
    with sperre:
        auftrag = finde_auftrag(aid)
        if auftrag is None:
            return "Auftrag nicht gefunden."
        if auftrag["status"] != "WARTET":
            return f"Auftrag ist schon {STATUS_TEXT[auftrag['status']].lower()}."
        if freigeben and not hat_file(aid):
            return "Kein File vorhanden. Erst die fertige Datei hochladen."
        auftrag["status"] = "FREIGEGEBEN" if freigeben else "ABGELEHNT"
        auftrag["grund"] = grund.strip()[:300]
        auftrag["entschieden"] = datetime.now().isoformat(timespec="seconds")
        auftrag["entschieden_von"] = wer
        speichere_auftrag(auftrag)
    telegram_aktualisieren(auftrag)
    return "Freigegeben." if freigeben else "Abgelehnt."


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def telegram_api(methode: str, daten: dict, timeout: int = 15):
    token = lade_config().get("telegram_token")
    if not token:
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{methode}",
        data=json.dumps(daten).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:  # Benachrichtigung darf den Upload nie blockieren
        print(f"Telegram-Fehler ({methode}): {e}", file=sys.stderr)
        return None


def telegram_text(a: dict) -> str:
    if a.get("typ") == "anfrage":
        return telegram_text_anfrage(a)
    a = {k: html.escape(v) if isinstance(v, str) else v for k, v in a.items()}
    zeilen = [
        f"🔧 <b>Neuer Auftrag: {html.escape(option_namen()[a['option']])}</b>",
        f"Datei: {a['datei']}",
        f"ECU: {a['ecu']}",
        f"Software: {a['software']}",
        f"Kontakt: {a['kunde']}",
        (f"Treffer: ⚠️ {ART_TEXT['softwarenummer']}" if a.get("art") == "softwarenummer"
         else f"Treffer: 100 % – {ART_TEXT.get(a['art'], a['art'])}"),
        f"Quelle: {a['quelle'] or '–'}",
    ]
    if a["status"] == "FREIGEGEBEN":
        zeilen.append("\n✅ <b>FREIGEGEBEN</b>")
    elif a["status"] == "ABGELEHNT":
        zeilen.append("\n❌ <b>ABGELEHNT</b>" + (f": {a['grund']}" if a.get("grund") else ""))
    return "\n".join(zeilen)


def telegram_text_anfrage(a: dict) -> str:
    e = lambda x: html.escape(str(x or "–"))
    fz = a.get("fahrzeug") or {}
    zeilen = [f"📩 <b>Neue Anfrage: {e(option_namen()[a['option']])}</b>",
              *(f"{titel}: {e(fz.get(feld))}" for feld, titel, _ in FAHRZEUG_FELDER),
              f"ECU: {e(a['ecu'])}", f"Software: {e(a['software'])}", f"Datei: {e(a['datei'])}",
              f"Kontakt: {e(a['kunde'])}"]
    if a.get("nachricht"):
        zeilen.append(f"Nachricht: {e(a['nachricht'])}")
    if a["status"] == "WARTET":
        zeilen.append("\nOriginal kommt gleich als Datei. Fertiges File im Admin-Bereich hochladen – "
                      "dann bekommt der Kunde es automatisch auf der Seite.")
    elif a["status"] == "FREIGEGEBEN":
        zeilen.append("\n✅ <b>FERTIG – an den Kunden geschickt</b>")
    elif a["status"] == "ABGELEHNT":
        zeilen.append("\n❌ <b>ABGELEHNT</b>" + (f": {e(a['grund'])}" if a.get("grund") else ""))
    return "\n".join(zeilen)


def telegram_datei(chat, pfad: Path, name: str, antwort_auf=None):
    """Datei an Telegram schicken (multipart, bis 50 MB)."""
    token = lade_config().get("telegram_token")
    if not token:
        return None
    grenze = uuid.uuid4().hex
    teile = [("chat_id", str(chat))] + ([("reply_to_message_id", str(antwort_auf))] if antwort_auf else [])
    koerper = b"".join(f'--{grenze}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                       for k, v in teile)
    sauber = re.sub(r'["\r\n\\]', "_", name)
    koerper += (f'--{grenze}\r\nContent-Disposition: form-data; name="document"; filename="{sauber}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + pfad.read_bytes() + f"\r\n--{grenze}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendDocument", data=koerper,
                                 headers={"Content-Type": f"multipart/form-data; boundary={grenze}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except Exception as ex:   # Benachrichtigung darf nie etwas blockieren
        print(f"Telegram-Fehler (sendDocument): {ex}", file=sys.stderr)
        return None


def telegram_knoepfe(a: dict) -> dict:
    zeile = []
    if a["status"] == "WARTET":
        if hat_file(a["id"]):
            zeile.append({"text": "✅ Bestätigen", "callback_data": f"ok:{a['id']}"})
        zeile.append({"text": "❌ Ablehnen", "callback_data": f"nein:{a['id']}"})
    knoepfe = [zeile] if zeile else []
    basis = lade_config().get("basis_url", "")
    if basis.startswith("https://"):
        knoepfe.append([{"text": "Im Admin-Bereich öffnen", "url": f"{basis.rstrip('/')}/auftrag/{a['id']}"}])
    return {"inline_keyboard": knoepfe}


def telegram_melden(auftrag: dict):
    chat = lade_config().get("telegram_chat_id")
    if not chat:
        return
    antwort = telegram_api("sendMessage", {"chat_id": chat, "text": telegram_text(auftrag),
                                           "parse_mode": "HTML", "reply_markup": telegram_knoepfe(auftrag)})
    if antwort and antwort.get("ok"):
        with sperre:
            aktuell = finde_auftrag(auftrag["id"])
            aktuell["tg_nachricht"] = antwort["result"]["message_id"]
            speichere_auftrag(aktuell)
        if auftrag.get("typ") == "anfrage":   # Original gleich mitschicken -> direkt bearbeiten
            telegram_datei(chat, AUFTRAEGE / auftrag["id"] / "ori.bin", auftrag["datei"],
                           antwort["result"]["message_id"])


def telegram_aktualisieren(auftrag: dict):
    """Nachricht nach einer Entscheidung anpassen (Knoepfe weg, Ergebnis rein)."""
    chat = lade_config().get("telegram_chat_id")
    if chat and auftrag.get("tg_nachricht"):
        telegram_api("editMessageText", {"chat_id": chat, "message_id": auftrag["tg_nachricht"],
                                         "text": telegram_text(auftrag), "parse_mode": "HTML",
                                         "reply_markup": telegram_knoepfe(auftrag)})


def telegram_schleife():
    """Wartet auf Knopfdruecke in Telegram (Long Polling, kein oeffentlicher Server noetig).
    Darf nie aufhoeren: jeder Fehler wird gemeldet, danach geht es weiter."""
    offset = [None]
    while True:
        try:
            telegram_runde(offset)
        except Exception as e:
            print(f"Telegram-Schleife: {e!r}", file=sys.stderr)
            time.sleep(5)


def telegram_runde(offset: list):
    """Ein Abruf bei Telegram und alle Knopfdruecke darin verarbeiten."""
    cfg = lade_config()
    antwort = telegram_api("getUpdates", {"timeout": 30, "offset": offset[0],
                                          "allowed_updates": ["callback_query", "message"]}, timeout=40)
    if not antwort or not antwort.get("ok"):
        time.sleep(5)
        return
    for update in antwort["result"]:
        offset[0] = update["update_id"] + 1   # vorher setzen: ein kaputtes Update wird nicht endlos wiederholt
        nachricht = update.get("message")
        if nachricht:
            chat = nachricht.get("chat", {})
            telegram_chats[str(chat.get("id"))] = chat.get("title") or chat.get("first_name") or "?"
            if not cfg.get("telegram_chat_id"):
                telegram_api("sendMessage", {"chat_id": chat.get("id"),
                                             "text": "Hallo! Im Admin-Bereich unter Einstellungen kannst du diesen Chat jetzt übernehmen."})
            continue
        cb = update.get("callback_query")
        if not cb:
            continue
        # Nur Knopfdruecke aus dem eingestellten Chat zaehlen
        if str(cb.get("message", {}).get("chat", {}).get("id")) != str(cfg.get("telegram_chat_id")):
            telegram_api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "Nicht erlaubt."})
            continue
        aktion, _, aid = cb.get("data", "").partition(":")
        wer = "Telegram: " + cb.get("from", {}).get("first_name", "?")
        text = entscheide(aid, aktion == "ok", wer=wer) if aktion in ("ok", "nein") else "Unbekannt."
        telegram_api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": text})


def benachrichtigen(auftrag: dict):
    telegram_melden(auftrag)


# ---------------------------------------------------------------------------
# Login / Sicherheit
# ---------------------------------------------------------------------------

def admin_noetig(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def zu_viele(art: str, limit: int, sekunden: int) -> bool:
    jetzt = time.time()
    schluessel = (art, request.remote_addr or "?")
    liste = [t for t in versuche.get(schluessel, []) if jetzt - t < sekunden]
    versuche[schluessel] = liste
    return len(liste) >= limit


def merken(art: str):
    if len(versuche) > 10000:   # Speicher begrenzen
        versuche.clear()
    versuche.setdefault((art, request.remote_addr or "?"), []).append(time.time())


@app.after_request
def sicherheits_header(antwort):
    antwort.headers.setdefault("X-Content-Type-Options", "nosniff")
    antwort.headers.setdefault("X-Frame-Options", "DENY")
    antwort.headers.setdefault("Referrer-Policy", "same-origin")
    return antwort


@app.before_request
def upload_limit():
    if request.path in ("/admin/archiv/import", "/admin/archiv/neu") and session.get("admin"):
        request.max_content_length = 4 * 1024 * 1024 * 1024


@app.before_request
def csrf_pruefen():
    if request.path.startswith("/api/"):
        return  # die API nutzt keine Cookies (Zugriff ueber die geheime Auftragsnummer)
    session.setdefault("csrf", secrets.token_hex(16))
    if request.method == "POST" and request.form.get("csrf") != session["csrf"]:
        abort(400)


# ---------------------------------------------------------------------------
# Seiten fuer Kunden
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if zu_viele("login", 5, 15 * 60):
            flash("Zu viele Fehlversuche. Bitte 15 Minuten warten.")
            return render_template("login.html")
        name = request.form.get("name", "").strip()
        b = lade_benutzer().get(name)
        if b and b.get("rolle") == "admin" and check_password_hash(b["pw"], request.form.get("pw", "")):
            session.clear()
            session["benutzer"], session["admin"] = name, True
            session["csrf"] = secrets.token_hex(16)
            return redirect(url_for("admin"))
        merken("login")
        flash("Benutzername oder Passwort falsch.")
    return render_template("login.html")


@app.route("/impressum")
def impressum():
    return render_template("text.html", titel="Impressum", text=lade_config().get("impressum", ""))


@app.route("/datenschutz")
def datenschutz():
    return render_template("text.html", titel="Datenschutz", text=lade_config().get("datenschutz", ""))


@app.route("/logout")
def logout():
    session.pop("benutzer", None)
    session.pop("admin", None)
    return redirect(url_for("login"))


@app.route("/")
def start():
    """Kundenseite: Original hochladen, Loesungen waehlen, Anfragen, Herunterladen (alles ueber /api/...)."""
    seite = KUNDENSEITE.read_text(encoding="utf-8")
    name = html.escape(lade_config().get("firmenname") or "OneClick Tuning")
    seite = seite.replace("<title>OneClick Tuning</title>", f"<title>{name}</title>", 1)
    antwort = app.response_class(seite, mimetype="text/html")
    antwort.headers["Cache-Control"] = "no-cache"   # nach einem Update sofort die neue Seite
    return antwort


class Abgelehnt(Exception):
    """Fehler mit einer Meldung fuer den Kunden (Admin: flash, Kundenseite: JSON)."""


class KeineLoesung(Abgelehnt):
    """Nichts Passendes im Archiv. Das Original ist trotzdem gespeichert (Entwurf), damit der Kunde
    dazu eine Anfrage stellen kann."""
    def __init__(self, text: str, auftrag: dict):
        super().__init__(text)
        self.auftrag = auftrag


def entwurf_anlegen(daten: bytes, dateiname: str) -> dict:
    """Schritt 1: Original pruefen, 100-%-Treffer suchen, Entwurf mit den verfuegbaren Loesungen anlegen."""
    if zu_viele("upload", 30, 3600):
        raise Abgelehnt("Zu viele Uploads in kurzer Zeit. Bitte später nochmal versuchen.")
    merken("upload")
    if len(daten) < 1024:
        raise Abgelehnt("Die Datei ist zu klein für ein ECU-File.")

    info, loesungen = oneclick.finde_loesungen(daten, bool(lade_config().get("nur_identisch")))
    ecu = ", ".join(info["ecu"]) or "?"
    software = ", ".join(info["bosch_sw"] + info["vag_teilenr"]) or "?"
    aid = uuid.uuid4().hex
    ordner = AUFTRAEGE / aid
    ordner.mkdir(parents=True)
    reihenfolge = [*oneclick.optionen(), oneclick.ORIGINAL]
    (ordner / "ori.bin").write_bytes(daten)
    for opt, l in loesungen.items():
        (ordner / f"loesung_{opt}.bin").write_bytes(l["daten"])
    auftrag = {
        "id": aid,
        "kunde": "–",
        "datei": Path(dateiname).name or "datei.bin",
        "option": None,
        "status": "ENTWURF",
        "angebot": {opt: {"quelle": l["quelle"], "art": l["art"]}
                    for opt, l in sorted(loesungen.items(), key=lambda t: reihenfolge.index(t[0]))},
        "ecu": ecu,
        "software": software,
        "zeit": datetime.now().isoformat(timespec="seconds"),
    }
    speichere_auftrag(auftrag)
    if not loesungen:
        raise KeineLoesung(f"Für dieses File haben wir leider noch keine Lösung (ECU: {ecu}, Software: {software}). "
                           "Stell uns einfach eine Anfrage – wir machen dir das File.", auftrag)
    return auftrag


def anfrage_abschicken(aid: str, fahrzeug: dict, wunsch: list, nachricht: str, kontakt: str) -> dict:
    """Ticket: Kunde bittet um ein File, das es im Archiv noch nicht gibt. Das Original liegt schon auf
    dem Server (vom Pruefen). Der Admin laedt spaeter das fertige File hoch oder lehnt ab."""
    fz = {}
    for feld, titel, pflicht in FAHRZEUG_FELDER:
        wert = " ".join(str(fahrzeug.get(feld) or "").split())[:80]
        if pflicht and not wert:
            raise Abgelehnt(f"Bitte „{titel}“ angeben.")
        fz[feld] = wert
    erlaubt = oneclick.optionen()
    wunsch = [o for o in erlaubt if o in wunsch]   # Reihenfolge wie im Archiv, nur bekannte Loesungen
    if not wunsch:
        raise Abgelehnt("Bitte mindestens eine gewünschte Lösung auswählen.")
    with sperre:
        auftrag = finde_auftrag(aid)
        if auftrag is None:
            raise Abgelehnt("Das File ist nicht mehr auf dem Server. Bitte nochmal hochladen.")
        if auftrag["status"] != "ENTWURF":
            return auftrag   # schon abgeschickt (z. B. Doppelklick)
        if zu_viele("anfrage", 10, 3600):
            raise Abgelehnt("Zu viele Anfragen in kurzer Zeit. Bitte später nochmal versuchen.")
        merken("anfrage")
        ordner = AUFTRAEGE / aid
        for rest in ordner.glob("loesung_*.bin"):
            rest.unlink()
        auftrag.update(typ="anfrage", option="+".join(wunsch), status="WARTET", art="anfrage", quelle="",
                       fahrzeug=fz, nachricht=str(nachricht or "").strip()[:1000],
                       kunde=str(kontakt or "").strip()[:100] or "–", angebot={},
                       zeit=datetime.now().isoformat(timespec="seconds"))
        speichere_auftrag(auftrag)
    threading.Thread(target=benachrichtigen, args=(auftrag,), daemon=True).start()
    return auftrag


def fahrzeug_text(a: dict) -> str:
    fz = a.get("fahrzeug") or {}
    teile = [fz.get("marke"), fz.get("modell"), fz.get("baujahr"), fz.get("motor")]
    return " · ".join(x for x in teile if x)


def auftrag_abschicken(aid: str, gewaehlt: set, kontakt: str) -> dict:
    """Schritt 2: eine oder mehrere der angebotenen Loesungen -> wartet auf Freigabe."""
    with sperre:
        auftrag = finde_auftrag(aid)
        if auftrag is None:
            raise Abgelehnt("Auftrag nicht gefunden.")
        if auftrag["status"] != "ENTWURF":
            return auftrag   # schon abgeschickt (z. B. Doppelklick)
        angebot = auftrag["angebot"]
        auswahl = [o for o in angebot if o in gewaehlt]   # Reihenfolge wie angeboten
        if not auswahl or len(auswahl) != len(gewaehlt):
            raise Abgelehnt("Bitte eine oder mehrere der angezeigten Lösungen wählen.")
        if oneclick.ORIGINAL in auswahl and len(auswahl) > 1:
            raise Abgelehnt(f"„{oneclick.ORIGINAL_NAME}“ kann nicht mit anderen Lösungen kombiniert werden.")
        ordner = AUFTRAEGE / aid
        if len(auswahl) == 1:
            (ordner / f"loesung_{auswahl[0]}.bin").replace(ordner / "ergebnis.bin")
        else:
            daten = oneclick.kombiniere((ordner / "ori.bin").read_bytes(),
                                        [(ordner / f"loesung_{o}.bin").read_bytes() for o in auswahl])
            if daten is None:
                raise Abgelehnt(f"Die Kombination {option_namen()['+'.join(auswahl)]} ist leider nicht möglich, "
                                "weil sich die Lösungen gegenseitig überschneiden. Bitte anders wählen.")
            (ordner / "ergebnis.bin").write_bytes(daten)
        for rest in ordner.glob("loesung_*.bin"):
            rest.unlink()
        arten = {angebot[o]["art"] for o in auswahl}
        art = ("softwarenummer" if "softwarenummer" in arten
               else "identisch" if arten == {"identisch"} else "gleiche Stellen")
        auftrag.update(option="+".join(auswahl), status="WARTET",
                       kunde=kontakt.strip()[:100] or "–",
                       quelle=", ".join(dict.fromkeys(angebot[o]["quelle"] for o in auswahl)),
                       art=art,
                       zeit=datetime.now().isoformat(timespec="seconds"))
        speichere_auftrag(auftrag)
    threading.Thread(target=benachrichtigen, args=(auftrag,), daemon=True).start()
    return auftrag


# ---------------------------------------------------------------------------
# Schnittstelle fuer die Kundenseite (JSON, ohne Cookies)
# ---------------------------------------------------------------------------

def api_auftrag(a: dict) -> dict:
    namen = option_namen()
    return {
        "id": a["id"], "datei": a["datei"], "ecu": a["ecu"], "software": a["software"],
        "zeit": a["zeit"], "status": a["status"], "status_text": STATUS_TEXT[a["status"]],
        "option": a.get("option"), "option_name": namen[a["option"]] if a.get("option") else None,
        "angebot": [{"key": o, "name": namen[o]} for o in a.get("angebot", {})] if a["status"] == "ENTWURF" else [],
        "grund": a.get("grund", ""),
        "typ": a.get("typ", "auftrag"), "fahrzeug": fahrzeug_text(a),
    }


@app.route("/api/info")
def api_info():
    namen = option_namen()
    return jsonify(firma=lade_config().get("firmenname") or "OneClick Tuning", api=1,
                   original=oneclick.ORIGINAL,
                   optionen=[{"key": o, "name": namen[o]} for o in oneclick.optionen()],   # fuer Anfragen
                   fahrzeug_felder=[{"key": f, "name": n, "pflicht": p} for f, n, p in FAHRZEUG_FELDER])


@app.route("/api/pruefen", methods=["POST"])
def api_pruefen():
    datei = request.files.get("datei")
    if not datei or not datei.filename:
        return jsonify(fehler="Bitte eine Originaldatei auswählen."), 400
    try:
        return jsonify(api_auftrag(entwurf_anlegen(datei.read(), datei.filename)))
    except KeineLoesung as e:   # Anfrage moeglich: Entwurf-Nummer mitschicken
        return jsonify(fehler=str(e), anfrage=True, **api_auftrag(e.auftrag)), 422
    except Abgelehnt as e:
        return jsonify(fehler=str(e)), 422


@app.route("/api/auftrag/<aid>/bestellen", methods=["POST"])
def api_bestellen(aid):
    daten = request.get_json(silent=True)
    daten = daten if isinstance(daten, dict) else {}
    optionen = daten.get("optionen")
    optionen = {str(o) for o in optionen} if isinstance(optionen, list) else set()
    try:
        auftrag = auftrag_abschicken(aid, optionen, str(daten.get("kontakt") or ""))
    except Abgelehnt as e:
        return jsonify(fehler=str(e)), 422
    return jsonify(api_auftrag(auftrag))


@app.route("/api/auftrag/<aid>/anfrage", methods=["POST"])
def api_anfrage(aid):
    daten = request.get_json(silent=True)
    daten = daten if isinstance(daten, dict) else {}
    fahrzeug = daten.get("fahrzeug") if isinstance(daten.get("fahrzeug"), dict) else {}
    wunsch = [str(o) for o in daten.get("wunsch")] if isinstance(daten.get("wunsch"), list) else []
    try:
        auftrag = anfrage_abschicken(aid, fahrzeug, wunsch, str(daten.get("nachricht") or ""),
                                     str(daten.get("kontakt") or ""))
    except Abgelehnt as e:
        return jsonify(fehler=str(e)), 422
    return jsonify(api_auftrag(auftrag))


@app.route("/api/auftrag/<aid>")
def api_auftrag_status(aid):
    return jsonify(api_auftrag(lade_auftrag(aid)))


@app.route("/auftrag/<aid>")
@admin_noetig
def auftrag_ansicht(aid):
    return render_template("auftrag.html", a=lade_auftrag(aid), hat_file=hat_file(aid),
                           fahrzeug_felder=FAHRZEUG_FELDER)


@app.route("/auftrag/<aid>/status")
@admin_noetig
def auftrag_status(aid):
    return jsonify(status=lade_auftrag(aid)["status"])


@app.route("/auftrag/<aid>/download")
@app.route("/api/auftrag/<aid>/download")
def download(aid):
    auftrag = lade_auftrag(aid)
    if auftrag["status"] != "FREIGEGEBEN" and not (session.get("admin") and auftrag["status"] != "ENTWURF"):
        abort(403)
    if not hat_file(aid):
        abort(404)
    stamm = Path(auftrag["datei"]).stem
    return send_file(AUFTRAEGE / aid / "ergebnis.bin", as_attachment=True,
                     download_name=f"{stamm}_{auftrag['option']}.bin")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route("/auftrag/<aid>/original")
@admin_noetig
def original(aid):
    auftrag = lade_auftrag(aid)
    return send_file(AUFTRAEGE / aid / "ori.bin", as_attachment=True, download_name=auftrag["datei"])


@app.route("/admin")
@admin_noetig
def admin():
    alle = [a for a in alle_auftraege() if a["status"] != "ENTWURF"]
    wartend = [a for a in alle if a["status"] == "WARTET"]
    return render_template("admin.html", wartend=wartend, alle=alle[:100],
                           archiv=len(oneclick.lade_index()["eintraege"]),
                           freigegeben=sum(a["status"] == "FREIGEGEBEN" for a in alle),
                           telegram=bool(lade_config().get("telegram_chat_id")))


@app.route("/admin/wartend")
@admin_noetig
def admin_wartend():
    return jsonify(ids=[a["id"] for a in alle_auftraege() if a["status"] == "WARTET"])


@app.route("/admin/auftrag/<aid>/entscheiden", methods=["POST"])
@admin_noetig
def admin_entscheiden(aid):
    freigeben = request.form.get("aktion") == "ok"
    flash(entscheide(aid, freigeben, request.form.get("grund", ""), wer=session["benutzer"]))
    zurueck = request.form.get("zurueck", "")
    if not (zurueck.startswith("/") and not zurueck.startswith("//")):   # nur Seiten dieses Servers
        zurueck = url_for("auftrag_ansicht", aid=aid)
    return redirect(zurueck)


@app.route("/admin/auftrag/<aid>/fertig", methods=["POST"])
@admin_noetig
def fertig_hochladen(aid):
    """Selbst bearbeitetes File hochladen und freigeben, optional ins Archiv uebernehmen."""
    lade_auftrag(aid)
    datei = request.files.get("datei")
    if not datei or not datei.filename:
        flash("Bitte die fertige Datei auswählen.")
        return redirect(url_for("auftrag_ansicht", aid=aid))
    daten = datei.read()
    ori = (AUFTRAEGE / aid / "ori.bin").read_bytes()
    if len(daten) != len(ori):
        flash("Die fertige Datei hat eine andere Größe als das Original.")
        return redirect(url_for("auftrag_ansicht", aid=aid))

    with sperre:
        auftrag = lade_auftrag(aid)
        if auftrag["status"] != "WARTET":
            flash(f"Auftrag ist schon {STATUS_TEXT[auftrag['status']].lower()}.")
            return redirect(url_for("auftrag_ansicht", aid=aid))
        (AUFTRAEGE / aid / "ergebnis.bin").write_bytes(daten)
        auftrag["art"] = "eigenes File"
        speichere_auftrag(auftrag)
    meldung = entscheide(aid, True, wer=session["benutzer"])

    name = request.form.get("archiv_name", "").strip()
    if name:
        try:
            if "+" in auftrag["option"]:
                raise ValueError("Kombinationen werden nicht ins Archiv übernommen, nur einzelne Lösungen.")
            with index_sperre:
                oneclick.lerne(ori, daten, name, auftrag["option"])
            meldung += f" Als '{name}' ins Archiv übernommen."
        except ValueError as e:
            meldung += f" Nicht ins Archiv übernommen: {e}"
    flash(meldung)
    return redirect(url_for("auftrag_ansicht", aid=aid))


@app.route("/admin/index", methods=["POST"])
@admin_noetig
def index_neu():
    with index_sperre:
        oneclick.baue_index()
    flash("Archiv neu eingelesen.")
    return redirect(url_for("admin"))


# ---------------------------------------------------------------------------
# Aufraeumen
# ---------------------------------------------------------------------------

def sicherer_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")[:120] or "unbenannt"


def aufraeumen() -> int:
    """Alte, erledigte Auftraege und nicht abgeschlossene Entwuerfe loeschen. Das Archiv bleibt unangetastet."""
    tage = int(lade_config().get("aufbewahrung_tage", 90) or 0) or 36500   # 0 = nie
    grenze = datetime.now() - timedelta(days=tage)
    entwurf_grenze = datetime.now() - timedelta(days=1)
    geloescht = 0
    for a in alle_auftraege():
        zeit = datetime.fromisoformat(a["zeit"])
        if (a["status"] == "ENTWURF" and zeit < entwurf_grenze) or \
                (a["status"] not in ("WARTET", "ENTWURF") and zeit < grenze):
            shutil.rmtree(AUFTRAEGE / a["id"], ignore_errors=True)
            geloescht += 1
    return geloescht


def hintergrund():
    """Alle 6 Stunden aufraeumen."""
    while True:
        try:
            n = aufraeumen()
            if n:
                print(f"Aufgeräumt: {n} alte Aufträge gelöscht.")
        except Exception as e:  # Hintergrund darf nie sterben
            print(f"Hintergrund-Fehler: {e}", file=sys.stderr)
        time.sleep(6 * 3600)


# ---------------------------------------------------------------------------
# Admin: Archiv
# ---------------------------------------------------------------------------

def flache_gruppe(name: str) -> str:
    """Gruppenschluessel fuer Dateien ohne Ordner: 'Golf7_ORI.bin' und 'Golf7_Stage1.bin' -> 'golf7'."""
    stamm = Path(name).stem.lower()
    for muster in [oneclick.MUSTER_ORI, *oneclick.MUSTER_OPTION.values(), re.compile(r"mod|tuned|tuning")]:
        stamm = muster.sub(" ", stamm)
    return re.sub(r"[\s_.-]+", "_", stamm).strip("_") or "datei"


def sha(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def archiv_kennt() -> tuple:
    """Fingerabdruecke im Archiv: ({sha Original: Name}, {sha Tuning-File: (Name, Option)})."""
    oris, mods = {}, {}
    for e in oneclick.lade_index()["eintraege"]:
        oris.setdefault(e.get("ori_sha256"), e["name"])
        for opt, o in e["optionen"].items():
            mods.setdefault(o["sha256"], (e["name"], opt))
    oris.pop(None, None)
    return oris, mods


def ordner_vereinheitlichen(ziel: Path) -> dict:
    """Dateien eines Archiv-Ordners eindeutig benennen (ori.bin, stage1.bin ...) -> {Option: Pfad}."""
    ori_name, vorhanden = oneclick.klassifiziere([p.name for p in ziel.iterdir() if p.is_file()])
    if ori_name and ori_name != "ori.bin":
        (ziel / ori_name).rename(ziel / "ori.bin")
    for opt, n in vorhanden.items():
        if n != f"{opt}.bin":
            (ziel / n).rename(ziel / f"{opt}.bin")
    return {opt: ziel / f"{opt}.bin" for opt in vorhanden}


def archiv_speichern(name: str, ori: bytes, mods: dict, ersetzen: bool = True) -> dict:
    """Fahrzeug anlegen oder ergaenzen und dabei Doppelte erkennen (Aufrufer haelt index_sperre).
    Ist das Original schon im Archiv (auch unter anderem Namen), wird dort ergaenzt statt doppelt angelegt.
    -> {"name", "neu", "vorhanden_als", "gespeichert", "ersetzt", "gleich", "anderswo", "konflikt"}"""
    oris, mod_shas = archiv_kennt()
    erg = {"name": name, "neu": False, "vorhanden_als": None, "gespeichert": [], "ersetzt": [],
           "gleich": [], "anderswo": {}, "konflikt": []}
    bekannt = oris.get(sha(ori))
    if bekannt:
        erg["vorhanden_als"] = bekannt if bekannt != name else None
        name = erg["name"] = bekannt
    ziel = oneclick.ARCHIV / name
    if ziel.exists() and not bekannt:
        ori_name, _ = oneclick.klassifiziere([p.name for p in ziel.iterdir() if p.is_file()])
        if ori_name:
            raise Abgelehnt(f"„{name}“ gibt es schon mit einem anderen Original. Bitte einen anderen Namen wählen.")
    vorhanden = ordner_vereinheitlichen(ziel) if ziel.exists() else {}
    for opt, d in mods.items():
        if opt in vorhanden and vorhanden[opt].read_bytes() == d:
            erg["gleich"].append(opt)
        elif sha(d) in mod_shas and mod_shas[sha(d)][0] != name:
            erg["anderswo"][opt] = mod_shas[sha(d)]   # gleiches Tuning-File bei anderem Original: Verwechslung?
        elif opt in vorhanden and not ersetzen:
            erg["konflikt"].append(opt)
        else:
            (erg["ersetzt"] if opt in vorhanden else erg["gespeichert"]).append(opt)
    if not ziel.exists():
        ziel.mkdir(parents=True)
        erg["neu"] = True
    if not (ziel / "ori.bin").exists():
        (ziel / "ori.bin").write_bytes(ori)
    for opt in erg["gespeichert"] + erg["ersetzt"]:
        (ziel / f"{opt}.bin").write_bytes(mods[opt])
    oneclick.baue_index()
    return erg


def archiv_meldungen(erg: dict, quelle: str = "") -> list:
    namen = option_namen()
    liste = lambda opts: ", ".join(namen[o] for o in opts)
    vor = f"{quelle}: " if quelle else ""
    m = []
    if erg["vorhanden_als"]:
        m.append(f"{vor}Dieses Original ist schon im Archiv als „{erg['vorhanden_als']}“ – kein doppeltes Fahrzeug angelegt.")
    if erg["gespeichert"]:
        m.append(f"„{erg['name']}“ {'angelegt mit' if erg['neu'] else 'ergänzt:'} {liste(erg['gespeichert'])}.")
    elif erg["neu"]:
        m.append(f"„{erg['name']}“ als reines Original angelegt (für Rückrüsten über die Softwarenummer).")
    if erg["ersetzt"]:
        m.append(f"„{erg['name']}“: {liste(erg['ersetzt'])} durch die neue Datei ersetzt.")
    if erg["gleich"]:
        m.append(f"„{erg['name']}“: {liste(erg['gleich'])} schon genau so vorhanden – übersprungen.")
    for opt, (n, o) in erg["anderswo"].items():
        m.append(f"Nicht gespeichert – {namen[opt]}: genau dieses File liegt schon bei „{n}“ ({namen[o]}). "
                 "Falsches Original ausgewählt?")
    if erg["konflikt"]:
        m.append(f"„{erg['name']}“: {liste(erg['konflikt'])} gibt es schon mit anderem Inhalt – nicht überschrieben.")
    if not m:
        m.append(f"„{erg['name']}“: alles schon vorhanden, nichts geändert.")
    return m


def importiere_zip(stream) -> list:
    meldungen, ok, ergaenzt, doppelt = [], 0, 0, 0
    with zipfile.ZipFile(stream) as z:
        gruppen = {}
        for info in z.infolist():
            pfad = PurePosixPath(info.filename.replace("\\", "/"))
            if info.is_dir() or any(t.startswith(".") or t == "__MACOSX" for t in pfad.parts):
                continue
            if not oneclick.ist_ecu_datei(pfad.name) or info.file_size > 32 * 1024 * 1024:
                continue
            ordner = str(pfad.parent)
            schluessel = ordner if ordner not in ("", ".") else flache_gruppe(pfad.name)
            gruppen.setdefault(schluessel, []).append(info)

        for schluessel, infos in sorted(gruppen.items()):
            namen = {PurePosixPath(i.filename).name: i for i in infos}
            ori_name, optionen = oneclick.klassifiziere(list(namen))
            if not ori_name:
                meldungen.append(f"Übersprungen: {schluessel} (kein Original erkannt: {', '.join(namen)})")
                continue
            ori = z.read(namen[ori_name])
            passend = {opt: z.read(namen[n]) for opt, n in optionen.items()}
            passend = {opt: d for opt, d in passend.items() if len(d) == len(ori)}
            if optionen and not passend:
                meldungen.append(f"Übersprungen: {schluessel} (Dateigrößen passen nicht zusammen)")
                continue
            basis = sicherer_name(PurePosixPath(schluessel).name)
            with index_sperre:
                if sha(ori) not in archiv_kennt()[0]:   # gleicher Name, anderes Original -> neuer Name
                    name, nr = basis, 2
                    while (oneclick.ARCHIV / name).exists():
                        name, nr = f"{basis}_{nr}", nr + 1
                else:
                    name = basis
                erg = archiv_speichern(name, ori, passend, ersetzen=False)
            if erg["neu"]:
                ok += 1
            elif erg["gespeichert"]:
                ergaenzt += 1
            else:
                doppelt += 1
            if not erg["neu"] or erg["anderswo"]:
                meldungen += [x for x in archiv_meldungen(erg, schluessel) if "nichts geändert" not in x]
    with index_sperre:
        oneclick.baue_index()
    zeile = f"{ok} Fahrzeug(e) neu ins Archiv übernommen."
    if ergaenzt:
        zeile += f" {ergaenzt} vorhandene(s) ergänzt."
    if doppelt:
        zeile += f" {doppelt} waren schon komplett im Archiv und wurden übersprungen."
    return [zeile] + meldungen


@app.route("/admin/archiv")
@admin_noetig
def admin_archiv():
    eintraege = oneclick.lade_index()["eintraege"]
    zaehler = {}
    for e in eintraege:
        zaehler.setdefault(e.get("ori_sha256"), []).append(e["name"])
    doppelt = {n: [x for x in namen if x != n] for namen in zaehler.values() if len(namen) > 1 for n in namen}
    return render_template("archiv.html", eintraege=eintraege, doppelt=doppelt,
                           eigene=oneclick.eigene_optionen(), archiv_optionen=oneclick.optionen())


@app.route("/admin/loesungen", methods=["POST"])
@admin_noetig
def loesungen_verwalten():
    try:
        with index_sperre:
            if request.form.get("aktion") == "loeschen":
                name = oneclick.eigene_optionen().get(request.form.get("key", ""), "")
                oneclick.option_loeschen(request.form.get("key", ""))
                flash(f"Lösung „{name}“ gelöscht.")
            else:
                key = oneclick.option_anlegen(request.form.get("name", ""))
                flash(f"Lösung „{oneclick.optionen()[key]}“ angelegt. Du kannst sie jetzt bei Fahrzeugen hochladen.")
    except ValueError as e:
        flash(str(e))
    return redirect(url_for("admin_archiv"))


@app.route("/admin/archiv/neu", methods=["POST"])
@admin_noetig
def archiv_neu():
    """Ein Fahrzeug ohne ZIP anlegen, oder einem vorhandenen weitere Optionen hinzufuegen."""
    eingabe = request.form.get("name", "").strip()
    datei = request.files.get("ori")
    if not eingabe:
        flash("Bitte einen Namen für das Fahrzeug eingeben.")
        return redirect(url_for("admin_archiv"))
    if not datei or not datei.filename:
        flash("Bitte das Original auswählen.")
        return redirect(url_for("admin_archiv"))
    ori = datei.read()
    namen = option_namen()
    mods = {opt: request.files[opt].read() for opt in oneclick.optionen()
            if request.files.get(opt) and request.files[opt].filename}
    fehler = [f"{namen[opt]}: andere Dateigröße als das Original." if len(d) != len(ori)
              else f"{namen[opt]}: ist identisch mit dem Original." for opt, d in mods.items()
              if len(d) != len(ori) or d == ori]
    if fehler:
        for f in fehler:
            flash(f"Nicht gespeichert – {f}")
        return redirect(url_for("admin_archiv"))

    try:
        with index_sperre:
            erg = archiv_speichern(sicherer_name(eingabe), ori, mods)
    except Abgelehnt as e:
        flash(str(e))
        return redirect(url_for("admin_archiv"))
    for m in archiv_meldungen(erg):
        flash(m)
    return redirect(url_for("admin_archiv"))


@app.route("/admin/archiv/kennt", methods=["POST"])
@admin_noetig
def archiv_kennt_api():
    """Fuer den Hinweis direkt nach der Dateiauswahl: sind diese Files schon im Archiv?"""
    oris, mods = archiv_kennt()
    namen = option_namen()
    eintraege = {e["name"]: e for e in oneclick.lade_index()["eintraege"]}
    antwort = {"ori": None, "mods": {}}
    name = oris.get(request.form.get("ori", ""))
    if name:
        antwort["ori"] = {"name": name, "optionen": [namen[o] for o in oneclick.optionen()
                                                     if o in eintraege[name]["optionen"]]}
    for s in request.form.get("mods", "").split(",")[:50]:
        if s in mods:
            n, o = mods[s]
            antwort["mods"][s] = {"name": n, "option": namen[o]}
    return jsonify(antwort)


@app.route("/admin/archiv/import", methods=["POST"])
@admin_noetig
def archiv_import():
    datei = request.files.get("zip")
    if not datei or not datei.filename.lower().endswith(".zip"):
        flash("Bitte eine ZIP-Datei auswählen.")
        return redirect(url_for("admin_archiv"))
    try:
        meldungen = importiere_zip(datei.stream)
    except zipfile.BadZipFile:
        meldungen = ["Die Datei ist keine gültige ZIP-Datei."]
    for m in meldungen[:30]:
        flash(m)
    if len(meldungen) > 30:
        flash(f"… und {len(meldungen) - 30} weitere Meldungen.")
    return redirect(url_for("admin_archiv"))


@app.route("/admin/archiv/<name>/loeschen", methods=["POST"])
@admin_noetig
def archiv_loeschen(name):
    ziel = oneclick.ARCHIV / name
    if name != sicherer_name(name) or not ziel.is_dir():
        abort(404)
    shutil.rmtree(ziel)
    with index_sperre:
        oneclick.baue_index()
    flash(f"'{name}' aus dem Archiv gelöscht.")
    return redirect(url_for("admin_archiv"))


@app.route("/admin/archiv.zip")
@admin_noetig
def archiv_backup():
    tmp = BASE / ".archiv_backup.zip"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(oneclick.ARCHIV.rglob("*")):
            rel = p.relative_to(oneclick.ARCHIV)
            if p.is_file() and not any(t.startswith(".") for t in rel.parts):
                z.write(p, str(rel))
    return send_file(tmp, as_attachment=True,
                     download_name=f"tuning-archiv_{datetime.now():%Y-%m-%d}.zip")


# ---------------------------------------------------------------------------
# Admin: Update von GitHub
# ---------------------------------------------------------------------------

def git(*args, ordner: Path = None, timeout: int = 60) -> str:
    erg = subprocess.run(["git", "-C", str(ordner or BASE), *args], capture_output=True, text=True, timeout=timeout)
    if erg.returncode != 0:
        raise RuntimeError(erg.stderr.strip() or erg.stdout.strip() or "git-Fehler")
    return erg.stdout.strip()


def version(ordner: Path = None) -> dict:
    """Installierte Version (ohne Netzwerk)."""
    if not ((ordner or BASE) / ".git").exists():
        return {}
    stand = git("log", "-1", "--format=%h|%cd|%s", "--date=format:%d.%m.%Y %H:%M", ordner=ordner)
    kurz, datum, titel = stand.split("|", 2)
    return {"kurz": kurz, "datum": datum, "titel": titel}


def update_pruefen(ordner: Path = None) -> list:
    """Holt den Stand von GitHub und liefert die neuen Aenderungen (leer = aktuell)."""
    zweig = git("rev-parse", "--abbrev-ref", "HEAD", ordner=ordner)
    git("fetch", "-q", "origin", zweig, ordner=ordner)
    neu = git("log", f"HEAD..origin/{zweig}", "--format=%cd|%s", "--date=format:%d.%m.%Y", ordner=ordner)
    return [zeile.split("|", 1) for zeile in neu.splitlines() if zeile]


def update_installieren(ordner: Path = None):
    """Neue Version uebernehmen. Daten (Archiv, Auftraege, Einstellungen) sind nicht im Repository."""
    zweig = git("rev-parse", "--abbrev-ref", "HEAD", ordner=ordner)
    git("fetch", "-q", "origin", zweig, ordner=ordner)
    git("reset", "-q", "--hard", f"origin/{zweig}", ordner=ordner)
    erg = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r",
                          str((ordner or BASE) / "requirements.txt")], capture_output=True, text=True, timeout=300)
    if erg.returncode != 0:
        raise RuntimeError(f"Pakete konnten nicht installiert werden: {erg.stderr.strip()[-300:]}")


def als_dienst() -> bool:
    # systemd setzt INVOCATION_ID und startet das Programm nach dem Beenden neu (Restart=always)
    return bool(os.environ.get("INVOCATION_ID"))


def neustarten():
    time.sleep(1.5)   # Antwort an den Browser noch rausschicken
    os._exit(0)


# ---------------------------------------------------------------------------
# Admin: Einstellungen
# ---------------------------------------------------------------------------

@app.route("/admin/einstellungen", methods=["GET", "POST"])
@admin_noetig
def einstellungen():
    if request.method == "POST":
        aktion = request.form.get("aktion")
        if aktion == "speichern":
            try:
                tage = max(0, int(request.form.get("aufbewahrung_tage", "90") or 0))
            except ValueError:
                tage = 90
            speichere_config({
                "firmenname": request.form.get("firmenname", "").strip()[:60],
                "impressum": request.form.get("impressum", "").strip()[:20000],
                "datenschutz": request.form.get("datenschutz", "").strip()[:50000],
                "basis_url": request.form.get("basis_url", "").strip(),
                "telegram_token": request.form.get("telegram_token", "").strip(),
                "telegram_chat_id": request.form.get("telegram_chat_id", "").strip(),
                "aufbewahrung_tage": tage,
                "nur_identisch": request.form.get("nur_identisch") == "1",
            })
            flash("Gespeichert.")
        elif aktion == "chat":
            speichere_config({"telegram_chat_id": request.form.get("chat_id", "")})
            flash("Chat übernommen. Jetzt „Telegram testen“ drücken.")
        elif aktion == "test":
            cfg = lade_config()
            ok = telegram_api("sendMessage", {"chat_id": cfg.get("telegram_chat_id"),
                                              "text": f"✅ {cfg.get('firmenname') or 'OneClick Tuning'} ist verbunden."})
            flash("Testnachricht gesendet." if ok and ok.get("ok")
                  else "Senden fehlgeschlagen. Token und Chat-ID prüfen.")
        elif aktion == "aufraeumen":
            flash(f"{aufraeumen()} alte Aufträge gelöscht.")
        elif aktion == "update_pruefen":
            try:
                session["update_liste"] = update_pruefen()
                if not session["update_liste"]:
                    flash("Du hast schon die neueste Version.")
            except Exception as e:
                flash(f"Update-Prüfung fehlgeschlagen: {e}")
        elif aktion == "update":
            try:
                update_installieren()
            except Exception as e:
                flash(f"Update fehlgeschlagen: {e}")
                return redirect(url_for("einstellungen"))
            session.pop("update_liste", None)
            if als_dienst():
                threading.Thread(target=neustarten, daemon=True).start()
                return render_template("neustart.html")
            flash("Update installiert. Bitte den Server neu starten, damit es aktiv wird.")
        elif aktion == "passwort":
            benutzer = lade_benutzer()
            ich = benutzer.get(session["benutzer"])
            neu = request.form.get("neu", "")
            if not ich or not check_password_hash(ich["pw"], request.form.get("alt", "")):
                flash("Das aktuelle Passwort stimmt nicht.")
            elif len(neu) < 8:
                flash("Das neue Passwort muss mindestens 8 Zeichen haben.")
            elif neu != request.form.get("neu2", ""):
                flash("Die beiden neuen Passwörter sind nicht gleich.")
            else:
                ich["pw"] = generate_password_hash(neu)
                json_speichern(BENUTZER_DATEI, benutzer)
                flash("Passwort geändert.")
        return redirect(url_for("einstellungen"))
    try:
        v = version()
    except Exception:
        v = {}
    return render_template("einstellungen.html", cfg=lade_config(), chats=dict(telegram_chats),
                           version=v, update_liste=session.get("update_liste"))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = {
"basis.html": """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ firma }}</title>
<meta name="theme-color" content="#000000">
<link rel="icon" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI+PGRlZnM+PGxpbmVhckdyYWRpZW50IGlkPSJsZyIgeDE9IjAiIHkxPSIwIiB4Mj0iMSIgeTI9IjEiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iI2ZmMmQ1NSIvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2ZmOWYwYSIvPjwvbGluZWFyR3JhZGllbnQ+PC9kZWZzPjxyZWN0IHg9IjIiIHk9IjIiIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgcng9IjE0IiBmaWxsPSJ1cmwoI2xnKSIvPjxyZWN0IHg9IjQiIHk9IjQiIHdpZHRoPSI1NiIgaGVpZ2h0PSI1NiIgcng9IjEyIiBmaWxsPSIjMGIwYjBmIi8+PGcgZmlsbD0idXJsKCNsZykiPjxyZWN0IHg9IjE5LjAiIHk9IjExIiB3aWR0aD0iMy4yIiBoZWlnaHQ9IjgiIHJ4PSIxIi8+PHJlY3QgeD0iMTkuMCIgeT0iNDUiIHdpZHRoPSIzLjIiIGhlaWdodD0iOCIgcng9IjEiLz48cmVjdCB4PSIxMSIgeT0iMTkuMCIgd2lkdGg9IjgiIGhlaWdodD0iMy4yIiByeD0iMSIvPjxyZWN0IHg9IjQ1IiB5PSIxOS4wIiB3aWR0aD0iOCIgaGVpZ2h0PSIzLjIiIHJ4PSIxIi8+PHJlY3QgeD0iMjUuOSIgeT0iMTEiIHdpZHRoPSIzLjIiIGhlaWdodD0iOCIgcng9IjEiLz48cmVjdCB4PSIyNS45IiB5PSI0NSIgd2lkdGg9IjMuMiIgaGVpZ2h0PSI4IiByeD0iMSIvPjxyZWN0IHg9IjExIiB5PSIyNS45IiB3aWR0aD0iOCIgaGVpZ2h0PSIzLjIiIHJ4PSIxIi8+PHJlY3QgeD0iNDUiIHk9IjI1LjkiIHdpZHRoPSI4IiBoZWlnaHQ9IjMuMiIgcng9IjEiLz48cmVjdCB4PSIzMi44IiB5PSIxMSIgd2lkdGg9IjMuMiIgaGVpZ2h0PSI4IiByeD0iMSIvPjxyZWN0IHg9IjMyLjgiIHk9IjQ1IiB3aWR0aD0iMy4yIiBoZWlnaHQ9IjgiIHJ4PSIxIi8+PHJlY3QgeD0iMTEiIHk9IjMyLjgiIHdpZHRoPSI4IiBoZWlnaHQ9IjMuMiIgcng9IjEiLz48cmVjdCB4PSI0NSIgeT0iMzIuOCIgd2lkdGg9IjgiIGhlaWdodD0iMy4yIiByeD0iMSIvPjxyZWN0IHg9IjM5LjY5OTk5OTk5OTk5OTk5NiIgeT0iMTEiIHdpZHRoPSIzLjIiIGhlaWdodD0iOCIgcng9IjEiLz48cmVjdCB4PSIzOS42OTk5OTk5OTk5OTk5OTYiIHk9IjQ1IiB3aWR0aD0iMy4yIiBoZWlnaHQ9IjgiIHJ4PSIxIi8+PHJlY3QgeD0iMTEiIHk9IjM5LjY5OTk5OTk5OTk5OTk5NiIgd2lkdGg9IjgiIGhlaWdodD0iMy4yIiByeD0iMSIvPjxyZWN0IHg9IjQ1IiB5PSIzOS42OTk5OTk5OTk5OTk5OTYiIHdpZHRoPSI4IiBoZWlnaHQ9IjMuMiIgcng9IjEiLz48L2c+PHJlY3QgeD0iMTYuNCIgeT0iMTYuNCIgd2lkdGg9IjMxLjIiIGhlaWdodD0iMzEuMiIgcng9IjQuNCIgZmlsbD0idXJsKCNsZykiLz48cmVjdCB4PSIxNy45IiB5PSIxNy45IiB3aWR0aD0iMjguMiIgaGVpZ2h0PSIyOC4yIiByeD0iMy4zIiBmaWxsPSIjMWMxYzIyIi8+PHBhdGggZD0iTTM0LjIgMTkuMiAyNC45IDMyLjdIMzAuOUwyOC41IDQzLjEgMzguNSAyOC43SDMyLjVMMzUgMTkuMloiIGZpbGw9IiNmZmY0ZGMiLz48L3N2Zz4=">
<style>
:root{--bg:#000;--glas:rgba(255,255,255,.045);--glas2:rgba(255,255,255,.075);--rand:rgba(255,255,255,.09);
--rand2:rgba(255,255,255,.16);--text:#f5f5f7;--leise:#a1a1a6;--akzent:#ff375f;--akzent2:#ff9f0a;
--ok:#30d158;--warn:#ffd60a;--blau:#0a84ff;--verlauf:linear-gradient(135deg,var(--akzent),var(--akzent2))}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;color-scheme:dark}
input[type=file]{font-family:inherit;font-size:12.5px;color:var(--leise)}
input[type=file]::file-selector-button{font:inherit;font-weight:600;color:var(--text);background:rgba(255,255,255,.1);
border:1px solid var(--rand2);border-radius:980px;padding:6px 14px;margin-right:10px;cursor:pointer;transition:background .2s}
input[type=file]::file-selector-button:hover{background:rgba(255,255,255,.18)}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue",system-ui,"Segoe UI",Roboto,sans-serif;
-webkit-font-smoothing:antialiased;letter-spacing:-.01em;
background-image:radial-gradient(900px 500px at 15% -10%,rgba(255,55,95,.16),transparent 60%),
radial-gradient(800px 500px at 100% 0%,rgba(10,132,255,.13),transparent 60%),
radial-gradient(700px 600px at 50% 120%,rgba(255,159,10,.07),transparent 60%);background-attachment:fixed}
::selection{background:rgba(255,55,95,.35)}
a{color:var(--text)}
header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;
padding:12px max(16px,calc((100% - 1100px)/2));background:rgba(0,0,0,.6);
-webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid var(--rand)}
.logo{font-weight:700;font-size:19px;letter-spacing:-.02em}
.logo span{background:var(--verlauf);-webkit-background-clip:text;background-clip:text;color:transparent}
nav{display:flex;flex-wrap:wrap;gap:4px 20px}nav a{color:var(--leise);text-decoration:none;font-size:13.5px;transition:color .2s}nav a:hover{color:var(--text)}
main{max-width:1100px;margin:0 auto;padding:36px 16px}
.karte{background:var(--glas);border:1px solid var(--rand);border-radius:22px;padding:28px;margin-bottom:22px;
-webkit-backdrop-filter:blur(30px);backdrop-filter:blur(30px);box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 20px 60px rgba(0,0,0,.35)}
h1{font-size:30px;line-height:1.15;font-weight:700;letter-spacing:-.03em;margin:0 0 18px}
h2{font-size:19px;font-weight:600;letter-spacing:-.02em;margin:0 0 14px}
.hero{text-align:center;padding:34px 0 30px}
.hero h1{font-size:clamp(38px,7vw,64px);letter-spacing:-.045em;margin:0 0 14px}
.hero h1 span{background:var(--verlauf);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{font-size:clamp(16px,2.2vw,21px);color:var(--leise);max-width:620px;margin:0 auto}
.btn{display:inline-block;background:var(--verlauf);color:#fff;border:0;border-radius:980px;padding:12px 26px;
font-family:inherit;font-weight:600;font-size:15px;line-height:1.2;letter-spacing:-.01em;cursor:pointer;text-decoration:none;
box-shadow:0 8px 30px rgba(255,55,95,.35);transition:transform .15s,box-shadow .2s,opacity .2s}
.btn:hover{transform:translateY(-1px);box-shadow:0 12px 36px rgba(255,55,95,.45)}.btn:active{transform:scale(.98)}
.btn:disabled{opacity:.6;cursor:default;transform:none}
.btn.grau{background:var(--glas2);border:1px solid var(--rand2);box-shadow:none}.btn.grau:hover{background:rgba(255,255,255,.12)}
.btn.gruen{background:linear-gradient(135deg,#30d158,#0fb5a3);box-shadow:0 8px 30px rgba(48,209,88,.3)}
.btn.klein{padding:7px 14px;font-size:13px;box-shadow:none}
input[type=text],input[type=password],input[type=number],textarea{width:100%;font-family:inherit;padding:12px 14px;border-radius:12px;
border:1px solid var(--rand);background:rgba(255,255,255,.06);color:var(--text);font-size:15px;margin-bottom:12px;transition:border-color .2s,box-shadow .2s}
input:focus,textarea:focus{outline:none;border-color:var(--blau);box-shadow:0 0 0 4px rgba(10,132,255,.25)}
input::placeholder,textarea::placeholder{color:#6e6e73}
input[type=checkbox]{accent-color:var(--akzent);width:18px;height:18px}
.drop{position:relative;display:block;border-radius:20px;padding:48px 24px;text-align:center;color:var(--leise);cursor:pointer;margin-bottom:20px;
background:rgba(255,255,255,.03);border:1.5px dashed var(--rand2);transition:all .25s}
.drop::before{content:"↑";font-weight:700;display:block;margin:0 auto 12px;width:56px;height:56px;line-height:56px;border-radius:50%;font-size:22px;color:#fff;
background:var(--verlauf);box-shadow:0 10px 30px rgba(255,55,95,.4)}
.drop.aktiv,.drop:hover{border-color:var(--akzent);background:rgba(255,55,95,.06);color:var(--text);box-shadow:0 0 0 6px rgba(255,55,95,.08)}
.drop input{display:none}.drop b{color:var(--text);font-size:17px;font-weight:600}
.optionen{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.optionen label{border:1px solid var(--rand);border-radius:16px;padding:18px 14px;cursor:pointer;text-align:center;font-weight:600;
background:rgba(255,255,255,.03);transition:all .2s}
.optionen label:hover{border-color:var(--rand2);transform:translateY(-1px)}
.optionen input{display:none}
.optionen label:has(input:checked){border-color:transparent;background:linear-gradient(var(--bg),var(--bg)) padding-box,var(--verlauf) border-box;
border:1.5px solid transparent;box-shadow:0 10px 30px rgba(255,55,95,.25)}
.optionen input:checked+span{background:var(--verlauf);-webkit-background-clip:text;background-clip:text;color:transparent}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 10px;white-space:nowrap;border-bottom:1px solid var(--rand);font-size:14px}
th{color:var(--leise);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em}tr:last-child td{border-bottom:0}
.tabelle{overflow-x:auto}
.status{display:inline-block;padding:3px 11px;border-radius:99px;font-size:12.5px;font-weight:600}
.s-FREIGEGEBEN,.a-AUTOMATISCH{background:rgba(48,209,88,.15);color:var(--ok)}
.s-ENTWURF{background:rgba(10,132,255,.16);color:#64b5ff}
.s-WARTET{background:rgba(255,214,10,.13);color:var(--warn)}
.s-ABGELEHNT,.a-MANUELL{background:rgba(255,55,95,.15);color:#ff6482}
.meldung{background:rgba(10,132,255,.12);border:1px solid rgba(10,132,255,.35);padding:12px 16px;border-radius:14px;margin-bottom:20px;
-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px)}
.leise{color:var(--leise)}
pre{background:rgba(0,0,0,.4);border:1px solid var(--rand);border-radius:12px;padding:12px;overflow-x:auto;font-size:12.5px;max-height:360px}
.raster{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.zahl{font-size:42px;font-weight:700;letter-spacing:-.04em;background:linear-gradient(180deg,#fff,#a1a1a6);
-webkit-background-clip:text;background-clip:text;color:transparent}
.hinweis{font-size:13px;color:var(--leise);margin-top:12px}
.warten{display:flex;align-items:center;gap:16px;padding:18px;border-radius:16px;background:rgba(255,214,10,.07);border:1px solid rgba(255,214,10,.25)}
.kreis{width:24px;height:24px;border:3px solid rgba(255,214,10,.25);border-top-color:var(--warn);border-radius:50%;animation:dreh .9s linear infinite;flex:none}
@keyframes dreh{to{transform:rotate(360deg)}}
@keyframes rein{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
main>*{animation:rein .5s ease both}main>*:nth-child(2){animation-delay:.06s}main>*:nth-child(3){animation-delay:.12s}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
.inline{display:inline}
label.feld{display:block;font-size:13px;color:var(--leise);margin-bottom:6px}
code{background:rgba(255,255,255,.08);border-radius:7px;padding:2px 7px;font:12.5px ui-monospace,"SF Mono",Menlo,Consolas,monospace;word-break:break-all}
ol li{margin-bottom:8px}
textarea{min-height:140px;resize:vertical}
.dateien{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:18px}
label.datei{display:flex;flex-direction:column;gap:8px;border:1px dashed var(--rand2);border-radius:16px;padding:14px;cursor:pointer;font-size:14px;font-weight:600;
min-width:0;background:rgba(255,255,255,.03);transition:all .2s}
label.datei.pflicht{border-color:rgba(255,55,95,.55)}
label.datei.gewaehlt{border-style:solid;border-color:var(--ok);background:rgba(48,209,88,.08)}
label.datei input{font-size:12px;color:var(--leise);max-width:100%}
footer{max-width:1100px;margin:0 auto;padding:10px 16px 40px;font-size:12.5px;color:#6e6e73}
footer a{color:#6e6e73;margin-right:18px;text-decoration:none}footer a:hover{color:var(--text)}
@media (max-width:600px){.karte{padding:20px;border-radius:18px}main{padding:22px 14px}h1{font-size:25px}.hero{padding:16px 0 20px}}
</style></head><body>
<header><div class="logo">{% set w = firma.split(' ', 1) %}<span>{{ w[0] }}</span>{% if w|length > 1 %} {{ w[1] }}{% endif %}</div>
<nav>{% if session.admin %}<a href="{{ url_for('start') }}">Startseite</a>
<a href="{{ url_for('admin') }}">Aufträge</a>
<a href="{{ url_for('admin_archiv') }}">Archiv</a>
<a href="{{ url_for('einstellungen') }}">Einstellungen</a>
<a href="{{ url_for('logout') }}">Abmelden</a>{% endif %}</nav></header>
<main>
{% for m in get_flashed_messages() %}<div class="meldung">{{ m }}</div>{% endfor %}
{% block inhalt %}{% endblock %}
</main>
<footer><a href="{{ url_for('impressum') }}">Impressum</a><a href="{{ url_for('datenschutz') }}">Datenschutz</a></footer>
</body></html>""",

"neustart.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>Update wird installiert …</h1>
<div class="warten"><div class="kreis"></div><div><b>Die Seite startet neu.</b><br>
<span class="leise">Das dauert nur ein paar Sekunden, danach geht es automatisch weiter.</span></div></div></div>
<script>
setTimeout(function warte(){fetch('{{ url_for('login') }}',{cache:'no-store'})
  .then(r=>{if(r.ok)location.href='{{ url_for('einstellungen') }}';else setTimeout(warte,1500)})
  .catch(()=>setTimeout(warte,1500))},4000);
</script>
{% endblock %}""",

"text.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>{{ titel }}</h1>
{% if text %}<div style="white-space:pre-line">{{ text }}</div>
{% else %}<p class="leise">Noch nicht eingetragen.{% if session.admin %} → Einstellungen{% endif %}</p>{% endif %}</div>
{% endblock %}""",

"login.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte" style="max-width:380px;margin:40px auto">
<h1>Admin-Anmeldung</h1>
<form method="post"><input type="hidden" name="csrf" value="{{ session.csrf }}">
<input type="text" name="name" placeholder="Benutzername" autofocus>
<input type="password" name="pw" placeholder="Passwort">
<button class="btn" style="width:100%">Anmelden</button></form></div>
{% endblock %}""",

"auftrag.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte">
<h1>{% if a.typ == 'anfrage' %}📩 Anfrage: {% endif %}{% if a.option %}{{ optionen[a.option] }} · {% endif %}{{ a.datei }}</h1>
<p><span class="status s-{{ a.status }}">{{ status_text[a.status] }}</span>
<span class="leise">&nbsp; {{ a.zeit[:16].replace('T',' ') }}</span></p>
<table>{% if a.typ == 'anfrage' %}{% for feld, titel, _ in fahrzeug_felder %}<tr><th>{{ titel }}</th><td>{{ a.fahrzeug.get(feld) or '–' }}</td></tr>{% endfor %}
<tr><th>Gewünscht</th><td><b>{{ optionen[a.option] }}</b></td></tr>
{% if a.nachricht %}<tr><th>Nachricht</th><td style="white-space:pre-wrap">{{ a.nachricht }}</td></tr>{% endif %}{% endif %}
<tr><th>ECU</th><td>{{ a.ecu }}</td></tr><tr><th>Software</th><td>{{ a.software }}</td></tr>
<tr><th>Kontakt</th><td>{{ a.kunde }}</td></tr>
{% if a.art and a.typ != 'anfrage' %}<tr><th>Treffer</th><td>{% if a.art == 'softwarenummer' %}<span class="status s-WARTET">Prüfen</span>{% else %}<span class="status a-AUTOMATISCH">100 %</span>{% endif %} {{ art_text.get(a.art, a.art) }}</td></tr>{% endif %}
{% if a.typ != 'anfrage' %}<tr><th>Quelle</th><td>{{ a.quelle or '–' }}</td></tr>{% endif %}
{% if a.entschieden %}<tr><th>Entschieden</th><td>{{ a.entschieden[:16].replace('T',' ') }} von {{ a.entschieden_von }}</td></tr>{% endif %}
</table><br>

{% if a.status == 'ENTWURF' %}
<p class="leise">Der Kunde hat das File geprüft, aber noch keinen Auftrag abgeschickt.</p>
{% elif a.status == 'ABGELEHNT' and a.grund %}
<p>Grund der Ablehnung (sieht der Kunde): {{ a.grund }}</p>
{% endif %}
</div>

{% if session.admin and a.typ == 'anfrage' and a.status == 'WARTET' %}
<div class="karte"><h2>Anfrage bearbeiten</h2>
<p class="leise" style="margin-top:-6px">1. Original herunterladen und bearbeiten · 2. Fertiges File hier hochladen –
der Kunde bekommt es sofort automatisch auf der Seite angezeigt.</p>
<p><a class="btn" href="{{ url_for('original', aid=a.id) }}">⬇ Original herunterladen</a></p>
<form method="post" action="{{ url_for('fertig_hochladen', aid=a.id) }}" enctype="multipart/form-data" style="margin-top:18px">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<p><b>Fertiges File</b> (gleiche Größe wie das Original, Checksumme macht das Flash-Tool)</p>
<p><input type="file" name="datei"></p>
<input type="text" name="archiv_name" placeholder="Archivname, z. B. golf7_20tdi_03L906018JL (leer = nicht ins Archiv)">
<div class="hinweis">Mit Archivname landet das Paar im Archiv – der nächste Kunde mit diesem File bekommt es dann sofort automatisch
(nur bei einer einzelnen Lösung, nicht bei Kombinationen).</div>
<button class="btn gruen" style="margin-top:10px">Hochladen &amp; an Kunden schicken</button></form>
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" style="margin-top:26px">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="nein">
<p><b>Oder ablehnen</b></p>
<input type="text" name="grund" placeholder="Grund (sieht der Kunde), z. B. Software nicht unterstützt">
<button class="btn grau">✕ Anfrage ablehnen</button></form>
</div>
{% elif session.admin and a.status != 'ENTWURF' %}
<div class="karte"><h2>Admin</h2>
<p><a href="{{ url_for('original', aid=a.id) }}">Original herunterladen</a>
{% if hat_file %} · <a href="{{ url_for('download', aid=a.id) }}">Erstelltes File herunterladen (zum Prüfen)</a>{% endif %}</p>
{% if a.status == 'WARTET' %}
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="ok">
<button class="btn gruen">✓ Bestätigen</button></form>
</div>
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" style="margin-bottom:22px">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="nein">
<input type="text" name="grund" placeholder="Grund für die Ablehnung (optional, sieht der Kunde)">
<button class="btn">✕ Ablehnen</button></form>
<form method="post" action="{{ url_for('fertig_hochladen', aid=a.id) }}" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<p><b>Oder stattdessen eigenes File hochladen und freigeben</b> (ohne Checksumme ist ok)</p>
<p><input type="file" name="datei"></p>
<input type="text" name="archiv_name" placeholder="Archivname, z. B. golf7_20tdi_03L906018JL (leer = nicht ins Archiv)">
<button class="btn grau">Hochladen &amp; freigeben</button></form>
{% endif %}
</div>
{% endif %}
{% endblock %}""",

"admin.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="raster" style="margin-bottom:22px">
<div class="karte"><div class="leise">Warten auf Freigabe</div><div class="zahl">{{ wartend|rejectattr('typ', 'equalto', 'anfrage')|list|length }}</div></div>
<div class="karte"><div class="leise">Offene Anfragen</div><div class="zahl">{{ wartend|selectattr('typ', 'equalto', 'anfrage')|list|length }}</div></div>
<div class="karte"><div class="leise">Freigegeben</div><div class="zahl">{{ freigegeben }}</div></div>
<div class="karte"><div class="leise">Files im Archiv</div><div class="zahl">{{ archiv }}</div>
<form method="post" action="{{ url_for('index_neu') }}"><input type="hidden" name="csrf" value="{{ session.csrf }}">
<button class="btn grau klein" style="margin-top:6px">Neu einlesen</button></form></div>
</div>
<div class="karte"><h2>Warten auf Freigabe</h2>
<p class="hinweis" style="margin-top:-6px">Telegram: {{ 'aktiv' if telegram else 'nicht eingerichtet' }} ·
Diese Seite meldet neue Aufträge mit Ton. <a href="#" id="benachrichtigung">Browser-Benachrichtigungen erlauben</a></p>
{% if wartend %}<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>ECU</th><th>Treffer</th><th></th></tr>
{% for a in wartend %}<tr><td>{{ a.zeit[8:10] }}.{{ a.zeit[5:7] }}. {{ a.zeit[11:16] }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td>{{ a.ecu }}</td><td class="leise">{% if a.typ == 'anfrage' %}<span class="status s-WARTET">📩 Anfrage</span>
{{ a.fahrzeug.marke }} {{ a.fahrzeug.modell }}{% else %}{{ art_text.get(a.art, a.art) }}{% endif %}</td>
<td>{% if a.typ == 'anfrage' %}<a class="btn klein" href="{{ url_for('auftrag_ansicht', aid=a.id) }}">Bearbeiten</a>{% else %}<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="ok">
<input type="hidden" name="zurueck" value="{{ url_for('admin') }}"><button class="btn gruen klein">✓ Bestätigen</button></form>
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="nein">
<input type="hidden" name="zurueck" value="{{ url_for('admin') }}"><button class="btn klein">✕ Ablehnen</button></form>{% endif %}</td></tr>
{% endfor %}</table></div>{% else %}<p class="leise">Nichts offen.</p>{% endif %}</div>
<div class="karte"><h2>Alle Aufträge</h2>
<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>Quelle</th><th>Status</th></tr>
{% for a in alle %}<tr><td>{{ a.zeit[:16].replace('T',' ') }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td class="leise">{% if a.typ == 'anfrage' %}📩 Anfrage{% else %}{{ a.quelle or '–' }}{% endif %}</td>
<td><span class="status s-{{ a.status }}">{{ status_text[a.status] }}</span></td></tr>
{% endfor %}</table></div></div>
<script>
let bekannt=new Set({{ wartend|map(attribute='id')|list|tojson }});
document.getElementById('benachrichtigung').onclick=e=>{e.preventDefault();if(window.Notification)Notification.requestPermission()};
function ton(){try{const c=new AudioContext(),o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);
o.frequency.value=880;g.gain.value=.2;o.start();setTimeout(()=>{o.frequency.value=1175},150);setTimeout(()=>o.stop(),350)}catch(e){}}
setInterval(()=>fetch('{{ url_for('admin_wartend') }}').then(r=>r.json()).then(j=>{
  const neu=j.ids.filter(i=>!bekannt.has(i));
  if(neu.length){ton();if(window.Notification&&Notification.permission==='granted')new Notification('Neuer Tuning-Auftrag',{body:neu.length+' Auftrag/Aufträge warten auf Freigabe'});
    setTimeout(()=>location.reload(),600)}
  else if(j.ids.length!==bekannt.size)location.reload();
}).catch(()=>{}),8000);
</script>
{% endblock %}""",

"archiv.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>Neues Fahrzeug hinzufügen</h1>
<p class="leise">Je mehr Original/Tuning-Paare im Archiv liegen, desto mehr Kunden bekommen sofort einen Treffer.</p>
<form method="post" action="{{ url_for('archiv_neu') }}" enctype="multipart/form-data" id="nf">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<label class="feld">Name (z. B. Golf7_2.0TDI_03L906018JL). Einen vorhandenen Namen wählen, um dort weitere Optionen hinzuzufügen.</label>
<input type="text" name="name" list="namen" autocomplete="off">
<datalist id="namen">{% for e in eintraege %}<option value="{{ e.name }}">{% endfor %}</datalist>
<div class="dateien">
<label class="datei pflicht"><span>Original *</span><input type="file" name="ori"></label>
{% for key, titel in archiv_optionen.items() %}<label class="datei"><span>{{ titel }}</span><input type="file" name="{{ key }}"></label>{% endfor %}
</div>
<div id="kennt" class="hinweis" style="display:none;padding:12px 14px;border-radius:12px;border:1px solid;line-height:1.6;border-color:rgba(255,159,10,.5);background:rgba(255,159,10,.08);color:#ffd28a"></div>
<button class="btn" id="nlos">Speichern</button>
<div class="hinweis">Original und die vorhandenen Tuning-Files auswählen, die übrigen Felder leer lassen. Alle Files müssen gleich groß sein (gleiche Leseart).
Nur ein Original ohne Tuning-File geht auch: Dann bekommen Kunden mit einem fremden Tuning-File derselben Software „Original (Rückrüsten)“ angeboten.</div>
</form></div>

<div class="karte"><h2>Viele Fahrzeuge auf einmal (ZIP)</h2>
<form method="post" action="{{ url_for('archiv_import') }}" enctype="multipart/form-data" id="zf">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<label class="drop" id="drop"><input type="file" name="zip" id="zip" accept=".zip">
<div id="dropText"><b>ZIP-Datei mit euren Files hierher ziehen</b><br>oder klicken zum Auswählen</div></label>
<button class="btn" id="los">ZIP importieren</button>
<a class="btn grau" href="{{ url_for('archiv_backup') }}">Archiv als ZIP herunterladen (Backup)</a>
</form>
<div class="hinweis"><b>So soll die ZIP aussehen:</b> pro Fahrzeug ein Ordner mit Original und Tuning-File, z. B.
<code>Golf7_2.0TDI/Golf7_ORI.bin</code> + <code>Golf7_2.0TDI/Golf7_Stage1.bin</code>.
Erkannt werden Namen mit „ori/original“ bzw. „stage1/st1/stage2/vmax/startstop/pops/launch“.
Liegen genau zwei Dateien im Ordner, gilt die nicht-Original-Datei als Stage 1.
Ohne Ordner geht auch: <code>Golf7_ORI.bin</code> + <code>Golf7_Stage1.bin</code> (gleicher Namensanfang).</div>
</div>
<div class="karte"><h2>Lösungen</h2>
<p class="leise" style="margin-top:-6px">Diese Lösungen kannst du bei Fahrzeugen hochladen. Kunden sehen nur die, die es für ihr File gibt.</p>
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">
{% for key, name in archiv_optionen.items() %}
<span class="status s-ENTWURF" style="display:inline-flex;align-items:center;gap:8px">{{ name }}
{% if key in eigene %}<form method="post" action="{{ url_for('loesungen_verwalten') }}" class="inline" onsubmit="return confirm('Lösung „{{ name }}“ löschen?')">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="loeschen"><input type="hidden" name="key" value="{{ key }}">
<button title="Löschen" style="background:none;border:0;color:inherit;cursor:pointer;font-size:15px;padding:0">✕</button></form>{% endif %}</span>
{% endfor %}</div>
<form method="post" action="{{ url_for('loesungen_verwalten') }}" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="neu">
<input type="text" name="name" placeholder="Neue Lösung, z. B. Drallklappen" maxlength="40" style="flex:1;min-width:220px">
<button class="btn grau">Lösung anlegen</button></form>
<div class="hinweis">„Original (Rückrüsten)“ gibt es automatisch: Lädt ein Kunde ein getuntes File hoch, das zu einem Tuning-File im Archiv passt, kann er das Original bekommen.
Beim ZIP-Import erkennt die Seite eigene Lösungen am Dateinamen, z. B. <code>Golf7_Drallklappen.bin</code>.
Abschaltungen der Abgasreinigung (DPF, AGR, AdBlue/SCR, Kat, Lambda) werden nicht unterstützt.</div></div>

<div class="karte"><h2>{{ eintraege|length }} Einträge</h2>
{% if doppelt %}<p class="leise">Mit „doppelt“ markierte Einträge haben dasselbe Original. Am besten die Lösungen in einem Eintrag sammeln
(dort hochladen) und den anderen löschen.</p>{% endif %}
{% if eintraege %}<div class="tabelle"><table><tr><th>Name</th><th>ECU</th><th>Software</th><th>Optionen</th><th>Größe</th><th></th></tr>
{% for e in eintraege %}<tr><td>{{ e.name }}{% if e.name in doppelt %}
<span class="status s-WARTET" title="Gleiches Original wie: {{ doppelt[e.name]|join(', ') }}">doppelt: {{ doppelt[e.name]|join(', ') }}</span>{% endif %}</td><td>{{ e.ecu|join(', ') or '?' }}</td>
<td>{{ (e.bosch_sw + e.vag_teilenr)|join(', ') or '?' }}</td>
<td>{% for o in e.optionen %}{{ optionen[o] }}{{ ', ' if not loop.last }}{% else %}<span class="leise">nur Original</span>{% endfor %}</td>
<td>{{ (e.groesse / 1024)|round|int }} KB</td>
<td><form method="post" action="{{ url_for('archiv_loeschen', name=e.name) }}" class="inline" onsubmit="return confirm('{{ e.name }} wirklich löschen?')">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><button class="btn grau klein">Löschen</button></form></td></tr>
{% endfor %}</table></div>{% else %}<p class="leise">Noch leer.</p>{% endif %}</div>
<script>
const d=document.getElementById('drop'),i=document.getElementById('zip'),t=document.getElementById('dropText');
const zeig=()=>{if(i.files.length)t.innerHTML='<b>'+i.files[0].name+'</b><br>'+(i.files[0].size/1048576).toFixed(1)+' MB'};
i.addEventListener('change',zeig);
['dragover','dragenter'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();d.classList.add('aktiv')}));
['dragleave','drop'].forEach(e=>d.addEventListener(e,()=>d.classList.remove('aktiv')));
d.addEventListener('drop',ev=>{ev.preventDefault();i.files=ev.dataTransfer.files;zeig()});
document.getElementById('zf').addEventListener('submit',()=>{const b=document.getElementById('los');b.textContent='Wird hochgeladen … (kann dauern)';b.disabled=true});
document.getElementById('nf').addEventListener('submit',()=>{const b=document.getElementById('nlos');b.textContent='Wird gespeichert …';b.disabled=true});
document.querySelectorAll('label.datei input').forEach(x=>x.addEventListener('change',()=>{
  x.parentElement.classList.toggle('gewaehlt',x.files.length>0); kennt();}));
// Schon im Archiv? Fingerabdruck (SHA-256) im Browser berechnen, nur der wird an den Server geschickt
const hash=async f=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',await f.arrayBuffer()))].map(b=>b.toString(16).padStart(2,'0')).join('');
async function kennt(){
  const box=document.getElementById('kennt'); if(!window.crypto||!crypto.subtle) return;
  const felder=[...document.querySelectorAll('#nf input[type=file]')].filter(x=>x.files.length);
  if(!felder.length){box.style.display='none';return}
  const sh={}; for(const x of felder) sh[x.name]=await hash(x.files[0]);
  const titel=x=>x.closest('label').querySelector('span').textContent.replace(' *','');
  const fd=new FormData(); fd.append('csrf','{{ session.csrf }}'); fd.append('ori',sh.ori||'');
  fd.append('mods',felder.filter(x=>x.name!=='ori').map(x=>sh[x.name]).join(','));
  let a; try{a=await (await fetch('{{ url_for('archiv_kennt_api') }}',{method:'POST',body:fd})).json()}catch(e){return}
  const z=[], esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  if(a.ori){z.push(`⚠️ Dieses Original ist schon im Archiv als <b>${esc(a.ori.name)}</b> (${esc(a.ori.optionen.join(', ')||'nur Original')}). `+
    'Beim Speichern wird dort ergänzt – es entsteht kein doppeltes Fahrzeug.');
    const n=document.querySelector('#nf input[name=name]'); n.value=a.ori.name;}
  for(const x of felder){const m=x.name!=='ori'&&a.mods[sh[x.name]];
    if(m) z.push(`⚠️ ${esc(titel(x))}: genau dieses File liegt schon bei <b>${esc(m.name)}</b> (${esc(m.option)}).`);}
  box.innerHTML=z.join('<br>'); box.style.display=z.length?'block':'none';
}
</script>
{% endblock %}""",

"einstellungen.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>Einstellungen</h1>
<form method="post"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="speichern">
<label class="feld">Firmenname (oben links und im Browser-Tab; das erste Wort wird rot)</label>
<input type="text" name="firmenname" value="{{ cfg.firmenname or '' }}" placeholder="OneClick Tuning">
<label class="feld">Adresse der Seite</label>
<input type="text" name="basis_url" value="{{ cfg.basis_url or '' }}" placeholder="https://files.deine-firma.de">
<label class="feld">Telegram-Bot-Token (von @BotFather)</label>
<input type="password" name="telegram_token" value="{{ cfg.telegram_token or '' }}" placeholder="123456789:ABC…" autocomplete="off">
<label class="feld">Telegram-Chat-ID</label>
<input type="text" name="telegram_chat_id" value="{{ cfg.telegram_chat_id or '' }}" placeholder="wird unten automatisch gefunden">
<label class="feld">Erledigte Kundenaufträge automatisch löschen nach … Tagen (0 = nie). Das Archiv bleibt immer erhalten.</label>
<input type="number" name="aufbewahrung_tage" min="0" value="{{ cfg.get('aufbewahrung_tage', 90) }}">
<label style="display:flex;gap:10px;align-items:flex-start;margin:4px 0 16px;cursor:pointer">
<input type="checkbox" name="nur_identisch" value="1" {{ 'checked' if cfg.nur_identisch }} style="margin-top:4px">
<span><b>Nur komplett identische Originale</b><br><span class="leise" style="font-size:13px">Aus: Treffer auch, wenn das File an allen Stellen,
die euer Tuning ändert, exakt gleich ist (z. B. andere Fahrgestellnummer). An: nur wenn das ganze File Byte für Byte gleich ist.</span></span></label>
<label class="feld">Impressum (Pflicht für Firmen-Webseiten: Name, Anschrift, Kontakt, ggf. USt-ID / Handelsregister)</label>
<textarea name="impressum" placeholder="Firma GmbH&#10;Musterstraße 1&#10;12345 Musterstadt&#10;…">{{ cfg.impressum or '' }}</textarea>
<label class="feld">Datenschutzerklärung (z. B. mit einem Generator erstellen oder vom Anwalt; die Seite speichert hochgeladene Files und die optionale Kontaktangabe)</label>
<textarea name="datenschutz">{{ cfg.datenschutz or '' }}</textarea>
<button class="btn">Speichern</button></form></div>

<div class="karte"><h2>Telegram einrichten</h2>
<ol>
<li>In Telegram <b>@BotFather</b> öffnen → <code>/newbot</code> → Namen vergeben → Token oben eintragen → Speichern.</li>
<li>Deinem neuen Bot in Telegram irgendetwas schreiben, z. B. „hallo“. (Für mehrere Leute: Bot in eine Gruppe holen und dort schreiben.)</li>
<li>Diese Seite neu laden. Der Chat erscheint hier, dann auf „Übernehmen“ klicken:</li>
</ol>
{% if chats %}{% for cid, name in chats.items() %}
<form method="post" class="inline"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="chat">
<input type="hidden" name="chat_id" value="{{ cid }}"><button class="btn grau klein">{{ name }} ({{ cid }}) übernehmen</button></form>
{% endfor %}{% else %}<p class="leise">Noch keine Nachricht an den Bot gesehen{{ '' if cfg.telegram_token else ' (erst Token eintragen)' }}.</p>{% endif %}
<form method="post" style="margin-top:16px"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="test">
<button class="btn gruen">Telegram testen</button></form></div>

<div class="karte"><h2>Update</h2>
{% if version %}<p>Installiert: <b>{{ version.datum }}</b> <span class="leise">– {{ version.titel }} ({{ version.kurz }})</span></p>
{% if update_liste %}<div class="meldung"><b>{{ update_liste|length }} neue Änderung(en) verfügbar:</b>
<ul style="margin:6px 0 0;padding-left:20px">{% for datum, titel in update_liste %}<li>{{ titel }} <span class="leise">({{ datum }})</span></li>{% endfor %}</ul></div>
<form method="post" class="inline" onsubmit="this.querySelector('button').textContent='Wird installiert …';this.querySelector('button').disabled=true">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="update">
<button class="btn gruen">Update installieren</button></form>
{% endif %}
<form method="post" class="inline"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="update_pruefen">
<button class="btn grau">Nach Updates suchen</button></form>
<div class="hinweis">Archiv, Aufträge und Einstellungen bleiben beim Update erhalten. Die Seite ist dabei ein paar Sekunden nicht erreichbar.</div>
{% else %}<p class="leise">Updates per Knopf gibt es nur auf dem Server (Installation über das Installations-Skript).</p>{% endif %}
</div>

<div class="karte"><h2>Passwort ändern</h2>
<form method="post" style="max-width:420px"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="passwort">
<input type="password" name="alt" placeholder="Aktuelles Passwort" autocomplete="current-password">
<input type="password" name="neu" placeholder="Neues Passwort (mind. 8 Zeichen)" autocomplete="new-password">
<input type="password" name="neu2" placeholder="Neues Passwort wiederholen" autocomplete="new-password">
<button class="btn grau">Passwort ändern</button></form></div>

<div class="karte"><h2>Aufräumen</h2>
<p class="leise">Läuft automatisch alle 6 Stunden. Wartende Aufträge werden nie gelöscht.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="aufraeumen">
<button class="btn grau">Jetzt aufräumen</button></form></div>
{% endblock %}""",

}
app.jinja_loader = DictLoader(TEMPLATES)


@app.context_processor
def globale():
    return {"optionen": option_namen(), "status_text": STATUS_TEXT, "art_text": ART_TEXT, "original": oneclick.ORIGINAL,
            "firma": lade_config().get("firmenname") or "OneClick Tuning"}


# ---------------------------------------------------------------------------
# Kommandozeile
# ---------------------------------------------------------------------------

def admin_anlegen(name: str):
    pw = getpass.getpass(f"Passwort für {name}: ")
    if len(pw) < 8:
        sys.exit("Passwort muss mindestens 8 Zeichen haben.")
    benutzer = lade_benutzer()
    benutzer[name] = {"pw": generate_password_hash(pw), "rolle": "admin"}
    json_speichern(BENUTZER_DATEI, benutzer)
    print(f"Admin '{name}' gespeichert.")


def telegram_id():
    antwort = telegram_api("getUpdates", {"timeout": 0})
    if not antwort or not antwort.get("ok"):
        sys.exit("Kein Zugriff. Stimmt telegram_token in config.json?")
    chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("title") or u["message"]["chat"].get("first_name")
             for u in antwort["result"] if "message" in u}
    if not chats:
        sys.exit("Keine Nachricht gefunden. Schreib dem Bot zuerst irgendwas in Telegram und starte das hier nochmal.")
    for cid, name in chats.items():
        print(f"Chat-ID {cid}  ({name})")
    print('-> in config.json bei "telegram_chat_id" eintragen.')


if __name__ == "__main__":
    befehl = sys.argv[1] if len(sys.argv) > 1 else ""
    if befehl == "admin" and len(sys.argv) >= 3:
        admin_anlegen(sys.argv[2])
    elif befehl == "telegram-id":
        telegram_id()
    elif befehl == "telegram-test":
        cfg = lade_config()
        ok = telegram_api("sendMessage", {"chat_id": cfg.get("telegram_chat_id"), "text": "✅ OneClick Tuning ist verbunden."})
        print("Gesendet." if ok and ok.get("ok") else f"Fehler: {ok}")
    else:
        AUFTRAEGE.mkdir(exist_ok=True)
        threading.Thread(target=telegram_schleife, daemon=True).start()
        threading.Thread(target=hintergrund, daemon=True).start()
        host = os.environ.get("ONECLICK_HOST", "0.0.0.0")
        app.config["SESSION_COOKIE_SECURE"] = lade_config().get("basis_url", "").startswith("https://")
        try:
            from waitress import serve
            print(f"Server läuft auf http://{host}:5000")
            serve(app, host=host, port=5000, max_request_body_size=4 * 1024 * 1024 * 1024,
                  trusted_proxy="127.0.0.1", trusted_proxy_headers="x-forwarded-proto x-forwarded-for x-forwarded-host")
        except ImportError:
            app.run(host="0.0.0.0", port=5000)
