#!/usr/bin/env python3
"""
OneClick Tuning - Webseite

Start:
    python app.py admin <name>     Admin anlegen (fragt nach Passwort)
    python app.py telegram-id      Chat-ID fuer Telegram herausfinden
    python app.py telegram-test    Testnachricht an Telegram senden
    python app.py whatsapp-test    Test-Vorlage an WhatsApp senden
    python app.py                  Server starten (http://localhost:5000, Admin unter /login)

Kunden brauchen kein Login: Original hochladen -> die Seite sucht einen 100-%-Treffer im
Archiv und zeigt nur die Optionen an, die es dafuer gibt. Ohne Treffer entsteht kein Auftrag.
Der Kunde kann das File erst herunterladen, wenn der Admin den Auftrag bestaetigt hat
(per Telegram- oder WhatsApp-Knopf oder im Admin-Bereich). Bis dahin wartet die Seite des
Kunden und aktualisiert sich selbst.
"""

import getpass
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
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

OPTION_NAMEN = {
    "stage1": "Stage 1",
    "stage2": "Stage 2",
    "startstopp": "Start/Stopp aus",
    "vmax": "Vmax offen",
    "popsbangs": "Pops & Bangs",
    "launch": "Launch Control",
}
# ENTWURF: hochgeladen, Kunde waehlt noch die Option; danach entscheidet der Admin
STATUS_TEXT = {
    "ENTWURF": "Option wählen",
    "WARTET": "Wartet auf Freigabe",
    "FREIGEGEBEN": "Freigegeben",
    "ABGELEHNT": "Abgelehnt",
}
# art: wie der 100-%-Treffer zustande kam
ART_TEXT = {
    "identisch": "Original identisch",
    "gleiche Stellen": "Alle Tuning-Stellen identisch",
    "eigenes File": "Eigenes File",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
if not SECRET_DATEI.exists():
    SECRET_DATEI.write_text(secrets.token_hex(32))
app.secret_key = SECRET_DATEI.read_text().strip()
app.permanent_session_lifetime = timedelta(days=365)
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


def speichere_config(aenderungen: dict):
    cfg = lade_config()
    cfg.update(aenderungen)
    CONFIG_DATEI.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def lade_benutzer() -> dict:
    return json.loads(BENUTZER_DATEI.read_text()) if BENUTZER_DATEI.exists() else {}


def speichere_auftrag(auftrag: dict):
    (AUFTRAEGE / auftrag["id"] / "auftrag.json").write_text(json.dumps(auftrag, indent=2, ensure_ascii=False))


def finde_auftrag(aid: str):
    if not aid.isalnum():
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
    liste = [json.loads(p.read_text()) for p in AUFTRAEGE.glob("*/auftrag.json")]
    return sorted(liste, key=lambda a: a["zeit"], reverse=True)


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
    a = {k: html.escape(v) if isinstance(v, str) else v for k, v in a.items()}
    zeilen = [
        f"🔧 <b>Neuer Auftrag: {OPTION_NAMEN[a['option']]}</b>",
        f"Datei: {a['datei']}",
        f"ECU: {a['ecu']}",
        f"Software: {a['software']}",
        f"Kontakt: {a['kunde']}",
        f"Treffer: 100 % – {ART_TEXT.get(a['art'], a['art'])}",
        f"Quelle: {a['quelle'] or '–'}",
    ]
    if a["status"] == "FREIGEGEBEN":
        zeilen.append("\n✅ <b>FREIGEGEBEN</b>")
    elif a["status"] == "ABGELEHNT":
        zeilen.append("\n❌ <b>ABGELEHNT</b>" + (f": {a['grund']}" if a.get("grund") else ""))
    return "\n".join(zeilen)


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


def telegram_aktualisieren(auftrag: dict):
    """Nachricht nach einer Entscheidung anpassen (Knoepfe weg, Ergebnis rein)."""
    chat = lade_config().get("telegram_chat_id")
    if chat and auftrag.get("tg_nachricht"):
        telegram_api("editMessageText", {"chat_id": chat, "message_id": auftrag["tg_nachricht"],
                                         "text": telegram_text(auftrag), "parse_mode": "HTML",
                                         "reply_markup": telegram_knoepfe(auftrag)})


def telegram_schleife():
    """Wartet auf Knopfdruecke in Telegram (Long Polling, kein oeffentlicher Server noetig)."""
    offset = None
    while True:
        cfg = lade_config()
        antwort = telegram_api("getUpdates", {"timeout": 30, "offset": offset,
                                              "allowed_updates": ["callback_query", "message"]}, timeout=40)
        if not antwort or not antwort.get("ok"):
            time.sleep(5)
            continue
        for update in antwort["result"]:
            offset = update["update_id"] + 1
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


# ---------------------------------------------------------------------------
# WhatsApp (Business Platform / Cloud API von Meta)
# ---------------------------------------------------------------------------

def whatsapp_api(daten: dict):
    cfg = lade_config()
    if not (cfg.get("whatsapp_token") and cfg.get("whatsapp_phone_id")):
        return None
    version = cfg.get("whatsapp_api_version", "v23.0")
    req = urllib.request.Request(
        f"https://graph.facebook.com/{version}/{cfg['whatsapp_phone_id']}/messages",
        data=json.dumps({"messaging_product": "whatsapp", **daten}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['whatsapp_token']}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"WhatsApp-Fehler: {e.code} {e.read().decode(errors='ignore')}", file=sys.stderr)
    except Exception as e:  # Benachrichtigung darf den Upload nie blockieren
        print(f"WhatsApp-Fehler: {e}", file=sys.stderr)
    return None


def whatsapp_empfaenger() -> list:
    eintrag = lade_config().get("whatsapp_empfaenger", [])
    liste = [eintrag] if isinstance(eintrag, str) else eintrag
    return [n.lstrip("+").replace(" ", "") for n in liste if n]


def wa_wert(text: str) -> str:
    # Vorlagen-Variablen duerfen keine Zeilenumbrueche/Tabs und nicht leer sein
    text = " ".join(str(text).split())
    return text[:200] or "-"


def whatsapp_melden(auftrag: dict):
    cfg = lade_config()
    werte = [OPTION_NAMEN[auftrag["option"]], auftrag["datei"], auftrag["ecu"], auftrag["kunde"],
             f"100 % – {ART_TEXT.get(auftrag['art'], auftrag['art'])}"]
    for nummer in whatsapp_empfaenger():
        whatsapp_api({
            "to": nummer,
            "type": "template",
            "template": {
                "name": cfg.get("whatsapp_vorlage", "neuer_auftrag"),
                "language": {"code": cfg.get("whatsapp_sprache", "de")},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": wa_wert(w)} for w in werte]},
                    {"type": "button", "sub_type": "quick_reply", "index": "0",
                     "parameters": [{"type": "payload", "payload": f"ok:{auftrag['id']}"}]},
                    {"type": "button", "sub_type": "quick_reply", "index": "1",
                     "parameters": [{"type": "payload", "payload": f"nein:{auftrag['id']}"}]},
                ],
            },
        })


def benachrichtigen(auftrag: dict):
    telegram_melden(auftrag)
    whatsapp_melden(auftrag)


@app.route("/whatsapp/webhook", methods=["GET"])
def whatsapp_verifizieren():
    """Einmalige Pruefung durch Meta beim Einrichten des Webhooks."""
    token = lade_config().get("whatsapp_verify_token")
    if token and request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == token:
        return request.args.get("hub.challenge", "")
    abort(403)


@app.route("/whatsapp/webhook", methods=["POST"])
def whatsapp_webhook():
    """Knopfdruecke (Bestaetigen/Ablehnen) aus WhatsApp."""
    geheim = lade_config().get("whatsapp_app_secret", "")
    signatur = request.headers.get("X-Hub-Signature-256", "")
    erwartet = "sha256=" + hmac.new(geheim.encode(), request.get_data(), hashlib.sha256).hexdigest()
    if not geheim or not hmac.compare_digest(signatur, erwartet):
        abort(403)

    erlaubt = set(whatsapp_empfaenger())
    daten = request.get_json(silent=True) or {}
    for eintrag in daten.get("entry", []):
        for aenderung in eintrag.get("changes", []):
            for msg in aenderung.get("value", {}).get("messages", []):
                if msg.get("type") == "button":
                    payload = msg.get("button", {}).get("payload", "")
                elif msg.get("type") == "interactive":
                    payload = msg.get("interactive", {}).get("button_reply", {}).get("id", "")
                else:
                    continue
                absender = msg.get("from", "")
                if absender not in erlaubt:
                    continue
                aktion, _, aid = payload.partition(":")
                if aktion not in ("ok", "nein"):
                    continue
                text = entscheide(aid, aktion == "ok", wer=f"WhatsApp: +{absender}")
                auftrag = finde_auftrag(aid)
                if auftrag:
                    text = f"{auftrag['datei']} ({OPTION_NAMEN[auftrag['option']]}): {text}"
                whatsapp_api({"to": absender, "type": "text", "text": {"body": text}})
    return "ok"


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
    if request.path == "/whatsapp/webhook":
        return  # Meta signiert seine Anfragen selbst (siehe whatsapp_webhook)
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
    meine = session.get("auftraege", [])
    eigene = [a for a in alle_auftraege() if a["id"] in meine and a["status"] != "ENTWURF"]
    return render_template("start.html", auftraege=eigene)


@app.route("/pruefen", methods=["POST"])
def pruefen():
    """Schritt 1: Original hochladen, 100-%-Treffer suchen, verfuegbare Optionen anbieten."""
    if zu_viele("upload", 30, 3600):
        flash("Zu viele Uploads in kurzer Zeit. Bitte später nochmal versuchen.")
        return redirect(url_for("start"))
    merken("upload")
    datei = request.files.get("datei")
    if not datei or not datei.filename:
        flash("Bitte eine Originaldatei auswählen.")
        return redirect(url_for("start"))
    daten = datei.read()
    if len(daten) < 1024:
        flash("Die Datei ist zu klein für ein ECU-File.")
        return redirect(url_for("start"))

    info, loesungen = oneclick.finde_loesungen(daten, bool(lade_config().get("nur_identisch")))
    ecu = ", ".join(info["ecu"]) or "?"
    software = ", ".join(info["bosch_sw"] + info["vag_teilenr"]) or "?"
    if not loesungen:
        flash(f"Für dieses File haben wir leider noch keine Lösung (ECU: {ecu}, Software: {software}). "
              "Melde dich gerne bei uns.")
        return redirect(url_for("start"))

    aid = uuid.uuid4().hex
    ordner = AUFTRAEGE / aid
    ordner.mkdir(parents=True)
    (ordner / "ori.bin").write_bytes(daten)
    for opt, l in loesungen.items():
        (ordner / f"loesung_{opt}.bin").write_bytes(l["daten"])
    auftrag = {
        "id": aid,
        "kunde": "–",
        "datei": Path(datei.filename).name,
        "option": None,
        "status": "ENTWURF",
        "angebot": {opt: {"quelle": l["quelle"], "art": l["art"]}
                    for opt, l in sorted(loesungen.items(), key=lambda t: list(OPTION_NAMEN).index(t[0]))},
        "ecu": ecu,
        "software": software,
        "zeit": datetime.now().isoformat(timespec="seconds"),
    }
    speichere_auftrag(auftrag)
    session.permanent = True
    session["auftraege"] = ([aid] + session.get("auftraege", []))[:50]
    return redirect(url_for("auftrag_ansicht", aid=aid))


@app.route("/auftrag/<aid>/bestellen", methods=["POST"])
def bestellen(aid):
    """Schritt 2: Kunde waehlt eine der angebotenen Optionen -> wartet auf Freigabe."""
    option = request.form.get("option", "")
    with sperre:
        auftrag = lade_auftrag(aid)
        if auftrag["status"] != "ENTWURF":
            return redirect(url_for("auftrag_ansicht", aid=aid))
        if option not in auftrag["angebot"]:
            flash("Bitte eine der angezeigten Optionen wählen.")
            return redirect(url_for("auftrag_ansicht", aid=aid))
        ordner = AUFTRAEGE / aid
        (ordner / f"loesung_{option}.bin").replace(ordner / "ergebnis.bin")
        for rest in ordner.glob("loesung_*.bin"):
            rest.unlink()
        auftrag.update(option=option, status="WARTET",
                       kunde=request.form.get("kontakt", "").strip()[:100] or "–",
                       quelle=auftrag["angebot"][option]["quelle"], art=auftrag["angebot"][option]["art"],
                       zeit=datetime.now().isoformat(timespec="seconds"))
        speichere_auftrag(auftrag)
    threading.Thread(target=benachrichtigen, args=(auftrag,), daemon=True).start()
    return redirect(url_for("auftrag_ansicht", aid=aid))


@app.route("/auftrag/<aid>")
def auftrag_ansicht(aid):
    return render_template("auftrag.html", a=lade_auftrag(aid), hat_file=hat_file(aid))


@app.route("/auftrag/<aid>/status")
def auftrag_status(aid):
    return jsonify(status=lade_auftrag(aid)["status"])


@app.route("/auftrag/<aid>/download")
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
                           telegram=bool(lade_config().get("telegram_chat_id")),
                           whatsapp=bool(whatsapp_empfaenger() and lade_config().get("whatsapp_token")))


@app.route("/admin/wartend")
@admin_noetig
def admin_wartend():
    return jsonify(ids=[a["id"] for a in alle_auftraege() if a["status"] == "WARTET"])


@app.route("/admin/auftrag/<aid>/entscheiden", methods=["POST"])
@admin_noetig
def admin_entscheiden(aid):
    freigeben = request.form.get("aktion") == "ok"
    flash(entscheide(aid, freigeben, request.form.get("grund", ""), wer=session["benutzer"]))
    return redirect(request.form.get("zurueck") or url_for("auftrag_ansicht", aid=aid))


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


def importiere_zip(stream) -> list:
    meldungen, ok = [], 0
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
            if not ori_name or not optionen:
                meldungen.append(f"Übersprungen: {schluessel} (Original oder Tuning-File nicht erkannt: {', '.join(namen)})")
                continue
            ori = z.read(namen[ori_name])
            passend = {opt: z.read(namen[n]) for opt, n in optionen.items()}
            passend = {opt: d for opt, d in passend.items() if len(d) == len(ori)}
            if not passend:
                meldungen.append(f"Übersprungen: {schluessel} (Dateigrößen passen nicht zusammen)")
                continue
            basis = sicherer_name(PurePosixPath(schluessel).name)
            ziel, nr = oneclick.ARCHIV / basis, 2
            while ziel.exists():
                ziel, nr = oneclick.ARCHIV / f"{basis}_{nr}", nr + 1
            ziel.mkdir(parents=True)
            (ziel / "ori.bin").write_bytes(ori)
            for opt, d in passend.items():
                (ziel / f"{opt}.bin").write_bytes(d)
            ok += 1
    with index_sperre:
        oneclick.baue_index()
    return [f"{ok} Fahrzeug(e) ins Archiv übernommen."] + meldungen


@app.route("/admin/archiv")
@admin_noetig
def admin_archiv():
    return render_template("archiv.html", eintraege=oneclick.lade_index()["eintraege"])


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
    mods = {opt: request.files[opt].read() for opt in oneclick.OPTIONEN
            if request.files.get(opt) and request.files[opt].filename}
    if not mods:
        flash("Bitte mindestens ein Tuning-File auswählen (z. B. Stage 1).")
        return redirect(url_for("admin_archiv"))
    fehler = [f"{OPTION_NAMEN[opt]}: andere Dateigröße als das Original." if len(d) != len(ori)
              else f"{OPTION_NAMEN[opt]}: ist identisch mit dem Original." for opt, d in mods.items()
              if len(d) != len(ori) or d == ori]
    if fehler:
        for f in fehler:
            flash(f"Nicht gespeichert – {f}")
        return redirect(url_for("admin_archiv"))

    name = sicherer_name(eingabe)
    ziel = oneclick.ARCHIV / name
    with index_sperre:
        if ziel.exists():
            ori_name, vorhanden = oneclick.klassifiziere([p.name for p in ziel.iterdir() if p.is_file()])
            if ori_name and (ziel / ori_name).read_bytes() != ori:
                flash(f"„{name}“ gibt es schon mit einem anderen Original. Bitte einen anderen Namen wählen.")
                return redirect(url_for("admin_archiv"))
            # Vorhandene Dateien eindeutig benennen, damit nichts verwechselt wird
            if ori_name and ori_name != "ori.bin":
                (ziel / ori_name).rename(ziel / "ori.bin")
            for opt, n in vorhanden.items():
                if n != f"{opt}.bin":
                    (ziel / n).rename(ziel / f"{opt}.bin")
            neu = False
        else:
            ziel.mkdir(parents=True)
            neu = True
        (ziel / "ori.bin").write_bytes(ori)
        for opt, d in mods.items():
            (ziel / f"{opt}.bin").write_bytes(d)
        oneclick.baue_index()
    liste = ", ".join(OPTION_NAMEN[o] for o in mods)
    flash(f"„{name}“ angelegt mit {liste}." if neu else f"„{name}“ ergänzt: {liste}.")
    return redirect(url_for("admin_archiv"))


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
                BENUTZER_DATEI.write_text(json.dumps(benutzer, indent=2))
                flash("Passwort geändert.")
        return redirect(url_for("einstellungen"))
    return render_template("einstellungen.html", cfg=lade_config(), chats=dict(telegram_chats))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = {
"basis.html": """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ firma }}</title>
<style>
:root{--bg:#0f1115;--karte:#181b22;--rand:#2a2f3a;--text:#e8eaf0;--leise:#9aa1b2;
--akzent:#e3342f;--ok:#2fb36d;--warn:#e0a526;--blau:#3b82f6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--text)}header{display:flex;align-items:center;justify-content:space-between;
padding:14px 24px;border-bottom:1px solid var(--rand);flex-wrap:wrap;gap:8px}
.logo{font-weight:800;letter-spacing:.5px;font-size:18px}.logo span{color:var(--akzent)}
nav{display:flex;flex-wrap:wrap;gap:6px 18px}nav a{color:var(--leise);text-decoration:none}nav a:hover{color:var(--text)}
main{max-width:1100px;margin:0 auto;padding:28px 16px}
.karte{background:var(--karte);border:1px solid var(--rand);border-radius:12px;padding:22px;margin-bottom:22px}
h1{font-size:22px;margin:0 0 16px}h2{font-size:17px;margin:0 0 14px}
.btn{display:inline-block;background:var(--akzent);color:#fff;border:0;border-radius:8px;
padding:11px 20px;font-weight:600;font-size:15px;cursor:pointer;text-decoration:none}
.btn.grau{background:#2e3440}.btn.gruen{background:var(--ok)}.btn.klein{padding:6px 12px;font-size:13px}
input[type=text],input[type=password],input[type=number],textarea{width:100%;font-family:inherit;padding:10px 12px;border-radius:8px;
border:1px solid var(--rand);background:#0f1115;color:var(--text);font-size:15px;margin-bottom:12px}
.drop{display:block;border:2px dashed var(--rand);border-radius:12px;padding:30px;text-align:center;
color:var(--leise);cursor:pointer;margin-bottom:18px;transition:.15s}
.drop.aktiv,.drop:hover{border-color:var(--akzent);color:var(--text)}
.drop input{display:none}.drop b{color:var(--text)}
.optionen{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:18px}
.optionen label{border:1px solid var(--rand);border-radius:10px;padding:14px;cursor:pointer;
text-align:center;font-weight:600}
.optionen input{display:none}.optionen input:checked+span{color:var(--akzent)}
.optionen label:has(input:checked){border-color:var(--akzent);background:#e3342f14}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px 8px;white-space:nowrap;
border-bottom:1px solid var(--rand);font-size:14px}th{color:var(--leise);font-weight:500}
.tabelle{overflow-x:auto}
.status{display:inline-block;padding:2px 10px;border-radius:99px;font-size:13px;font-weight:600}
.s-FREIGEGEBEN,.a-AUTOMATISCH{background:#2fb36d22;color:var(--ok)}
.s-ENTWURF{background:#3b82f622;color:var(--blau)}
.s-WARTET{background:#e0a52622;color:var(--warn)}
.s-ABGELEHNT,.a-MANUELL{background:#e3342f22;color:#ff6b66}
.meldung{background:#3b82f61a;border:1px solid #3b82f655;padding:10px 14px;border-radius:8px;margin-bottom:18px}
.leise{color:var(--leise)}pre{background:#0b0d11;border:1px solid var(--rand);border-radius:8px;
padding:12px;overflow-x:auto;font-size:12.5px;max-height:360px}
.raster{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.zahl{font-size:28px;font-weight:800}.hinweis{font-size:13px;color:var(--leise);margin-top:10px}
.warten{display:flex;align-items:center;gap:14px;padding:16px;border-radius:10px;background:#e0a52614;border:1px solid #e0a52644}
.kreis{width:22px;height:22px;border:3px solid #e0a52655;border-top-color:var(--warn);border-radius:50%;animation:dreh 1s linear infinite;flex:none}
@keyframes dreh{to{transform:rotate(360deg)}}
.inline{display:inline}
label.feld{display:block;font-size:13px;color:var(--leise);margin-bottom:4px}
code{background:#0b0d11;border:1px solid var(--rand);border-radius:6px;padding:2px 6px;font-size:13px;word-break:break-all}
ol li{margin-bottom:8px}
textarea{min-height:140px;resize:vertical}
.dateien{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:16px}
label.datei{display:flex;flex-direction:column;gap:6px;border:1px dashed var(--rand);border-radius:10px;padding:12px;cursor:pointer;font-size:14px;font-weight:600;min-width:0}
label.datei.pflicht{border-color:#e3342f88}
label.datei.gewaehlt{border-style:solid;border-color:var(--ok);background:#2fb36d10}
label.datei input{font-size:12px;color:var(--leise);max-width:100%}
footer{max-width:1100px;margin:0 auto;padding:10px 16px 30px;font-size:13px;color:var(--leise)}
footer a{color:var(--leise);margin-right:16px}
</style></head><body>
<header><div class="logo">{% set w = firma.split(' ', 1) %}<span>{{ w[0] }}</span>{% if w|length > 1 %} {{ w[1] }}{% endif %}</div>
<nav><a href="{{ url_for('start') }}">Upload</a>
{% if session.admin %}<a href="{{ url_for('admin') }}">Aufträge</a>
<a href="{{ url_for('admin_archiv') }}">Archiv</a>
<a href="{{ url_for('einstellungen') }}">Einstellungen</a>
<a href="{{ url_for('logout') }}">Abmelden</a>{% endif %}</nav></header>
<main>
{% for m in get_flashed_messages() %}<div class="meldung">{{ m }}</div>{% endfor %}
{% block inhalt %}{% endblock %}
</main>
<footer><a href="{{ url_for('impressum') }}">Impressum</a><a href="{{ url_for('datenschutz') }}">Datenschutz</a></footer>
</body></html>""",

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

"start.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte">
<h1>Original hochladen</h1>
<form method="post" action="{{ url_for('pruefen') }}" enctype="multipart/form-data" id="f">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<label class="drop" id="drop"><input type="file" name="datei" id="datei">
<div id="dropText"><b>Originaldatei hierher ziehen</b><br>oder klicken zum Auswählen (.bin, .ori, max. 16 MB)</div></label>
<button class="btn" id="los">File prüfen</button>
<div class="hinweis">Wir prüfen sofort, welche Lösungen es für dein File gibt. Danach wählst du aus,
und nach unserer Freigabe kannst du das File herunterladen.</div>
</form></div>

<div class="karte"><h2>Meine Aufträge <span class="leise" style="font-weight:400;font-size:13px">(in diesem Browser)</span></h2>
{% if auftraege %}<div class="tabelle"><table><tr><th>Datum</th><th>Datei</th><th>Option</th><th>ECU</th><th>Status</th><th></th></tr>
{% for a in auftraege %}<tr><td>{{ a.zeit[:16].replace('T',' ') }}</td><td>{{ a.datei }}</td>
<td>{{ optionen[a.option] }}</td><td>{{ a.ecu }}</td>
<td><span class="status s-{{ a.status }}">{{ status_text[a.status] }}</span></td>
<td>{% if a.status == 'FREIGEGEBEN' %}<a href="{{ url_for('download', aid=a.id) }}">Download</a>{% else %}<a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">Details</a>{% endif %}</td></tr>
{% endfor %}</table></div>{% else %}<p class="leise">Noch keine Aufträge.</p>{% endif %}</div>
<script>
const d=document.getElementById('drop'),i=document.getElementById('datei'),t=document.getElementById('dropText');
const zeig=()=>{if(i.files.length)t.innerHTML='<b>'+i.files[0].name+'</b><br>'+(i.files[0].size/1024).toFixed(0)+' KB'};
i.addEventListener('change',zeig);
['dragover','dragenter'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();d.classList.add('aktiv')}));
['dragleave','drop'].forEach(e=>d.addEventListener(e,()=>d.classList.remove('aktiv')));
d.addEventListener('drop',ev=>{ev.preventDefault();i.files=ev.dataTransfer.files;zeig()});
document.getElementById('f').addEventListener('submit',()=>{const b=document.getElementById('los');b.textContent='Wird geprüft …';b.disabled=true});
</script>
{% endblock %}""",

"auftrag.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte">
<h1>{% if a.option %}{{ optionen[a.option] }} · {% endif %}{{ a.datei }}</h1>
<p><span class="status s-{{ a.status }}">{{ status_text[a.status] }}</span>
<span class="leise">&nbsp; {{ a.zeit[:16].replace('T',' ') }}</span></p>
<table><tr><th>ECU</th><td>{{ a.ecu }}</td></tr><tr><th>Software</th><td>{{ a.software }}</td></tr>
{% if session.admin %}<tr><th>Kontakt</th><td>{{ a.kunde }}</td></tr>
{% if a.art %}<tr><th>Treffer</th><td><span class="status a-AUTOMATISCH">100 %</span> {{ art_text.get(a.art, a.art) }}</td></tr>{% endif %}
<tr><th>Quelle</th><td>{{ a.quelle or '–' }}</td></tr>
{% if a.entschieden %}<tr><th>Entschieden</th><td>{{ a.entschieden[:16].replace('T',' ') }} von {{ a.entschieden_von }}</td></tr>{% endif %}
{% endif %}</table><br>

{% if a.status == 'ENTWURF' %}
<p><b>Für dein File haben wir folgende Lösungen:</b></p>
<form method="post" action="{{ url_for('bestellen', aid=a.id) }}" id="b">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<div class="optionen">
{% for opt in a.angebot %}
<label><input type="radio" name="option" value="{{ opt }}" {{ 'checked' if loop.first }}><span>{{ optionen[opt] }}</span></label>
{% endfor %}</div>
<input type="text" name="kontakt" placeholder="Name / Firma / Telefon (optional, falls wir dich erreichen müssen)">
<button class="btn" id="senden">Auftrag senden</button>
<div class="hinweis">Nach dem Senden geben wir deinen Auftrag kurz frei, danach kannst du das File herunterladen.
Checksumme bitte beim Schreiben vom Flash-Tool korrigieren lassen.</div></form>
<script>document.getElementById('b').addEventListener('submit',()=>{const x=document.getElementById('senden');x.textContent='Wird gesendet …';x.disabled=true});</script>
{% elif a.status == 'FREIGEGEBEN' %}
<a class="btn gruen" href="{{ url_for('download', aid=a.id) }}">File herunterladen</a>
<div class="hinweis">Checksumme beim Schreiben vom Flash-Tool korrigieren lassen.</div>
{% elif a.status == 'ABGELEHNT' %}
<p><b>Dieser Auftrag wurde abgelehnt.</b>{% if a.grund %}<br>Grund: {{ a.grund }}{% endif %}</p>
<p class="leise">Bei Fragen melde dich gerne bei uns.</p>
{% else %}
<div class="warten"><div class="kreis"></div><div><b>Wartet auf Freigabe</b><br>
<span class="leise">Wir prüfen deinen Auftrag. Diese Seite aktualisiert sich automatisch, sobald du das File herunterladen kannst.</span></div></div>
<div class="meldung" style="margin-top:14px">Du kannst die Seite auch schließen. Mit diesem Link kommst du später wieder hierher:<br>
<b style="word-break:break-all">{{ request.url }}</b></div>
<script>
setInterval(()=>fetch('{{ url_for('auftrag_status', aid=a.id) }}').then(r=>r.json())
  .then(j=>{if(j.status!=='WARTET')location.reload()}).catch(()=>{}),5000);
</script>
{% endif %}
</div>

{% if session.admin and a.status != 'ENTWURF' %}
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
<div class="karte"><div class="leise">Warten auf Freigabe</div><div class="zahl">{{ wartend|length }}</div></div>
<div class="karte"><div class="leise">Freigegeben</div><div class="zahl">{{ freigegeben }}</div></div>
<div class="karte"><div class="leise">Files im Archiv</div><div class="zahl">{{ archiv }}</div>
<form method="post" action="{{ url_for('index_neu') }}"><input type="hidden" name="csrf" value="{{ session.csrf }}">
<button class="btn grau klein" style="margin-top:6px">Neu einlesen</button></form></div>
</div>
<div class="karte"><h2>Warten auf Freigabe</h2>
<p class="hinweis" style="margin-top:-6px">Telegram: {{ 'aktiv' if telegram else 'nicht eingerichtet' }} · WhatsApp: {{ 'aktiv' if whatsapp else 'nicht eingerichtet' }} ·
Diese Seite meldet neue Aufträge mit Ton. <a href="#" id="benachrichtigung">Browser-Benachrichtigungen erlauben</a></p>
{% if wartend %}<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>ECU</th><th>Treffer</th><th></th></tr>
{% for a in wartend %}<tr><td>{{ a.zeit[8:10] }}.{{ a.zeit[5:7] }}. {{ a.zeit[11:16] }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td>{{ a.ecu }}</td><td class="leise">{{ art_text.get(a.art, a.art) }}</td>
<td><form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="ok">
<input type="hidden" name="zurueck" value="{{ url_for('admin') }}"><button class="btn gruen klein">✓ Bestätigen</button></form>
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="nein">
<input type="hidden" name="zurueck" value="{{ url_for('admin') }}"><button class="btn klein">✕ Ablehnen</button></form></td></tr>
{% endfor %}</table></div>{% else %}<p class="leise">Nichts offen.</p>{% endif %}</div>
<div class="karte"><h2>Alle Aufträge</h2>
<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>Quelle</th><th>Status</th></tr>
{% for a in alle %}<tr><td>{{ a.zeit[:16].replace('T',' ') }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td class="leise">{{ a.quelle or '–' }}</td>
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
{% for key, titel in optionen.items() %}<label class="datei"><span>{{ titel }}</span><input type="file" name="{{ key }}"></label>{% endfor %}
</div>
<button class="btn" id="nlos">Speichern</button>
<div class="hinweis">Original und mindestens ein Tuning-File auswählen, die übrigen Felder leer lassen. Alle Files müssen gleich groß sein (gleiche Leseart).</div>
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
<div class="karte"><h2>{{ eintraege|length }} Einträge</h2>
{% if eintraege %}<div class="tabelle"><table><tr><th>Name</th><th>ECU</th><th>Software</th><th>Optionen</th><th>Größe</th><th></th></tr>
{% for e in eintraege %}<tr><td>{{ e.name }}</td><td>{{ e.ecu|join(', ') or '?' }}</td>
<td>{{ (e.bosch_sw + e.vag_teilenr)|join(', ') or '?' }}</td>
<td>{% for o in e.optionen %}{{ optionen[o] }}{{ ', ' if not loop.last }}{% endfor %}</td>
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
document.querySelectorAll('label.datei input').forEach(x=>x.addEventListener('change',()=>
  x.parentElement.classList.toggle('gewaehlt',x.files.length>0)));
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
    return {"optionen": OPTION_NAMEN, "status_text": STATUS_TEXT, "art_text": ART_TEXT,
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
    BENUTZER_DATEI.write_text(json.dumps(benutzer, indent=2))
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
    elif befehl == "whatsapp-test":
        if not whatsapp_empfaenger():
            sys.exit("whatsapp_empfaenger fehlt in config.json")
        whatsapp_melden({"id": "test", "option": "stage1", "datei": "test.bin", "ecu": "EDC17C46",
                         "kunde": "Testkunde", "art": "identisch"})
        print("Gesendet (Fehler würden oben stehen).")
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
