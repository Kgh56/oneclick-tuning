#!/usr/bin/env python3
"""
OneClick Tuning - Webseite

Start:
    python app.py admin <name>     Admin anlegen (fragt nach Passwort)
    python app.py telegram-id      Chat-ID fuer Telegram herausfinden
    python app.py telegram-test    Testnachricht an Telegram senden
    python app.py whatsapp-test    Test-Vorlage an WhatsApp senden
    python app.py                  Server starten (http://localhost:5000, Admin unter /login)

Kunden brauchen kein Login: Original hochladen, Option waehlen. Das File wird sofort
automatisch erstellt, der Kunde kann es aber erst herunterladen, wenn der Admin den
Auftrag bestaetigt hat (per Telegram- oder WhatsApp-Knopf oder im Admin-Bereich). Bis dahin wartet
die Seite des Kunden und aktualisiert sich selbst.
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
EXPORT = BASE / "export"   # Kopien fuer WinOLS, wird per Syncthing auf den PC gespiegelt

OPTION_NAMEN = {
    "stage1": "Stage 1",
    "stage2": "Stage 2",
    "startstopp": "Start/Stopp aus",
    "vmax": "Vmax offen",
    "popsbangs": "Pops & Bangs",
    "launch": "Launch Control",
}
# status: Entscheidung des Admins; automatik: Ergebnis der automatischen Erstellung
STATUS_TEXT = {
    "WARTET": "Wartet auf Freigabe",
    "FREIGEGEBEN": "Freigegeben",
    "ABGELEHNT": "Abgelehnt",
}
AUTOMATIK_TEXT = {
    "AUTOMATISCH": "Automatisch",
    "PRUEFEN": "Teilweise",
    "MANUELL": "Kein File",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
if not SECRET_DATEI.exists():
    SECRET_DATEI.write_text(secrets.token_hex(32))
app.secret_key = SECRET_DATEI.read_text().strip()
app.permanent_session_lifetime = timedelta(days=365)

sperre = threading.Lock()
index_sperre = threading.Lock()
telegram_chats = {}   # zuletzt gesehene Chats (fuer die Einrichtung im Admin-Bereich)


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
        f"Automatik: {AUTOMATIK_TEXT[a['automatik']]} ({a['sicherheit']} %)",
        f"Quelle: {a['quelle'] or '–'}",
    ]
    if a["status"] == "FREIGEGEBEN":
        zeilen.append("\n✅ <b>FREIGEGEBEN</b>")
    elif a["status"] == "ABGELEHNT":
        zeilen.append("\n❌ <b>ABGELEHNT</b>" + (f": {a['grund']}" if a.get("grund") else ""))
    elif a["automatik"] == "MANUELL":
        zeilen.append("\n⚠️ Kein automatisches File. Fertige Datei im Admin-Bereich hochladen.")
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
             f"{AUTOMATIK_TEXT[auftrag['automatik']]} ({auftrag['sicherheit']} %)"]
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


@app.before_request
def upload_limit():
    if request.path == "/admin/archiv/import" and session.get("admin"):
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
        name = request.form.get("name", "").strip()
        b = lade_benutzer().get(name)
        if b and b.get("rolle") == "admin" and check_password_hash(b["pw"], request.form.get("pw", "")):
            session["benutzer"], session["admin"] = name, True
            return redirect(url_for("admin"))
        flash("Benutzername oder Passwort falsch.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("benutzer", None)
    session.pop("admin", None)
    return redirect(url_for("login"))


@app.route("/")
def start():
    meine = session.get("auftraege", [])
    eigene = [a for a in alle_auftraege() if a["id"] in meine]
    return render_template("start.html", auftraege=eigene)


@app.route("/auftrag", methods=["POST"])
def auftrag_neu():
    datei = request.files.get("datei")
    option = request.form.get("option", "stage1")
    if not datei or not datei.filename:
        flash("Bitte eine Originaldatei auswählen.")
        return redirect(url_for("start"))
    if option not in OPTION_NAMEN:
        abort(400)
    daten = datei.read()
    if len(daten) < 1024:
        flash("Die Datei ist zu klein für ein ECU-File.")
        return redirect(url_for("start"))

    erg = oneclick.tune(daten, option)
    aid = uuid.uuid4().hex
    ordner = AUFTRAEGE / aid
    ordner.mkdir(parents=True)
    (ordner / "ori.bin").write_bytes(daten)
    if erg["ergebnis"] is not None:
        (ordner / "ergebnis.bin").write_bytes(erg["ergebnis"])

    auftrag = {
        "id": aid,
        "kunde": request.form.get("kontakt", "").strip()[:100] or "–",
        "datei": Path(datei.filename).name,
        "option": option,
        "status": "WARTET",
        "automatik": erg["status"],
        "sicherheit": round(erg["sicherheit"], 1),
        "quelle": erg["quelle"],
        "ecu": ", ".join(erg["info"]["ecu"]) or "?",
        "software": ", ".join(erg["info"]["bosch_sw"] + erg["info"]["vag_teilenr"]) or "?",
        "zeit": datetime.now().isoformat(timespec="seconds"),
        "bericht": erg["bericht"],
    }
    speichere_auftrag(auftrag)
    exportieren(auftrag, "ORI", daten)
    if erg["ergebnis"] is not None:
        exportieren(auftrag, "AUTO", erg["ergebnis"])
    threading.Thread(target=benachrichtigen, args=(auftrag,), daemon=True).start()

    # Browser merkt sich die letzten 50 eigenen Auftraege
    session.permanent = True
    session["auftraege"] = ([aid] + session.get("auftraege", []))[:50]
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
    if auftrag["status"] != "FREIGEGEBEN" and not session.get("admin"):
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
    alle = alle_auftraege()
    wartend = [a for a in alle if a["status"] == "WARTET"]
    for a in wartend:
        a["hat_file"] = hat_file(a["id"])
    return render_template("admin.html", wartend=wartend, alle=alle[:100],
                           archiv=len(oneclick.lade_index()["eintraege"]),
                           auto=sum(a["automatik"] == "AUTOMATISCH" for a in alle),
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
        auftrag["eigenes_file"] = True
        speichere_auftrag(auftrag)
    exportieren(auftrag, "FERTIG", daten)
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
# Export fuer WinOLS, Aufraeumen, Archiv beobachten
# ---------------------------------------------------------------------------

def sicherer_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")[:120] or "unbenannt"


def exportieren(auftrag: dict, art: str, daten: bytes):
    """Lesbar benannte Kopie in export/ ablegen (z. B. fuer WinOLS auf dem PC)."""
    teile = [auftrag["zeit"][:16].replace("T", "_").replace(":", ""), auftrag["ecu"].split(",")[0],
             auftrag["software"].split(",")[0], auftrag["option"], Path(auftrag["datei"]).stem,
             auftrag["id"][:6], art]
    try:
        EXPORT.mkdir(exist_ok=True)
        (EXPORT / (sicherer_name("_".join(teile)) + ".bin")).write_bytes(daten)
    except OSError as e:
        print(f"Export-Fehler: {e}", file=sys.stderr)


def aufraeumen() -> int:
    """Alte, erledigte Auftraege und Export-Kopien loeschen. Das Archiv bleibt unangetastet."""
    tage = int(lade_config().get("aufbewahrung_tage", 90) or 0)
    if tage <= 0:
        return 0
    grenze = datetime.now() - timedelta(days=tage)
    geloescht = 0
    for a in alle_auftraege():
        if a["status"] != "WARTET" and datetime.fromisoformat(a["zeit"]) < grenze:
            shutil.rmtree(AUFTRAEGE / a["id"], ignore_errors=True)
            geloescht += 1
    if EXPORT.exists():
        for f in EXPORT.iterdir():
            if f.is_file() and f.stat().st_mtime < grenze.timestamp():
                f.unlink(missing_ok=True)
    return geloescht


def archiv_signatur() -> list:
    if not oneclick.ARCHIV.exists():
        return []
    sig = []
    for p in oneclick.ARCHIV.rglob("*"):
        rel = p.relative_to(oneclick.ARCHIV)
        if p.is_file() and not any(t.startswith(".") for t in rel.parts):
            st = p.stat()
            sig.append((str(rel), st.st_size, int(st.st_mtime)))
    return sorted(sig)


def hintergrund():
    """Index neu bauen, wenn sich das Archiv aendert (z. B. per Syncthing), und taeglich aufraeumen."""
    letzte = archiv_signatur()
    letzte_reinigung = 0.0
    while True:
        time.sleep(30)
        try:
            sig = archiv_signatur()
            if sig != letzte:
                time.sleep(15)   # warten, bis Uebertragungen fertig sind
                if archiv_signatur() == sig:
                    with index_sperre:
                        oneclick.baue_index()
                    letzte = sig
            if time.time() - letzte_reinigung > 6 * 3600:
                n = aufraeumen()
                if n:
                    print(f"Aufgeräumt: {n} alte Aufträge gelöscht.")
                letzte_reinigung = time.time()
        except Exception as e:  # Hintergrund darf nie sterben
            print(f"Hintergrund-Fehler: {e}", file=sys.stderr)


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
                "basis_url": request.form.get("basis_url", "").strip(),
                "telegram_token": request.form.get("telegram_token", "").strip(),
                "telegram_chat_id": request.form.get("telegram_chat_id", "").strip(),
                "aufbewahrung_tage": tage,
            })
            flash("Gespeichert.")
        elif aktion == "chat":
            speichere_config({"telegram_chat_id": request.form.get("chat_id", "")})
            flash("Chat übernommen. Jetzt „Telegram testen“ drücken.")
        elif aktion == "test":
            cfg = lade_config()
            ok = telegram_api("sendMessage", {"chat_id": cfg.get("telegram_chat_id"),
                                              "text": "✅ OneClick Tuning ist verbunden."})
            flash("Testnachricht gesendet." if ok and ok.get("ok")
                  else "Senden fehlgeschlagen. Token und Chat-ID prüfen.")
        elif aktion == "aufraeumen":
            flash(f"{aufraeumen()} alte Aufträge gelöscht.")
        return redirect(url_for("einstellungen"))
    return render_template("einstellungen.html", cfg=lade_config(), chats=dict(telegram_chats))


# ---------------------------------------------------------------------------
# Admin: WinOLS-Sync (Syncthing)
# ---------------------------------------------------------------------------

SYNC_ORDNER = {
    "oneclick-archiv": ("Tuning-Archiv", oneclick.ARCHIV, "sendreceive"),
    "oneclick-auftraege": ("Tuning-Auftraege", EXPORT, "sendonly"),
}
GERAETE_ID = re.compile(r"^[A-Z2-7]{7}(-[A-Z2-7]{7}){7}$")


def st_api(methode: str, pfad: str, daten=None):
    cfg = lade_config()
    if not cfg.get("syncthing_api_key"):
        raise RuntimeError("Syncthing ist nicht eingerichtet (syncthing_api_key fehlt).")
    req = urllib.request.Request(
        cfg.get("syncthing_url", "http://127.0.0.1:8384") + pfad, method=methode,
        data=None if daten is None else json.dumps(daten).encode(),
        headers={"X-API-Key": cfg["syncthing_api_key"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        inhalt = r.read()
    return json.loads(inhalt) if inhalt.strip() else {}


def sync_pc_hinzufuegen(pc_id: str, pc_name: str):
    if pc_id not in [d["deviceID"] for d in st_api("GET", "/rest/config/devices")]:
        geraet = st_api("GET", "/rest/config/defaults/device")
        geraet.update(deviceID=pc_id, name=pc_name)
        st_api("PUT", f"/rest/config/devices/{pc_id}", geraet)
    for fid, (label, pfad, typ) in SYNC_ORDNER.items():
        pfad.mkdir(exist_ok=True)
        try:
            ordner = st_api("GET", f"/rest/config/folders/{fid}")
        except urllib.error.HTTPError:
            ordner = st_api("GET", "/rest/config/defaults/folder")
            ordner.update(id=fid, label=label, path=str(pfad), type=typ, devices=[])
        if pc_id not in [d["deviceID"] for d in ordner.get("devices", [])]:
            ordner.setdefault("devices", []).append({"deviceID": pc_id})
        st_api("PUT", f"/rest/config/folders/{fid}", ordner)


def sync_pc_entfernen(pc_id: str):
    for fid in SYNC_ORDNER:
        try:
            ordner = st_api("GET", f"/rest/config/folders/{fid}")
        except urllib.error.HTTPError:
            continue
        ordner["devices"] = [d for d in ordner.get("devices", []) if d["deviceID"] != pc_id]
        st_api("PUT", f"/rest/config/folders/{fid}", ordner)
    st_api("DELETE", f"/rest/config/devices/{pc_id}")


@app.route("/admin/winols", methods=["GET", "POST"])
@admin_noetig
def winols_sync():
    if request.method == "POST":
        pc_id = request.form.get("pc_id", "").strip().upper()
        try:
            if request.form.get("aktion") == "entfernen":
                sync_pc_entfernen(pc_id)
                flash("PC entfernt.")
            elif not GERAETE_ID.match(pc_id):
                flash("Das sieht nicht wie eine Syncthing-Geräte-ID aus (8 Blöcke à 7 Zeichen).")
            else:
                sync_pc_hinzufuegen(pc_id, request.form.get("pc_name", "").strip() or "Werkstatt-PC")
                flash("PC hinzugefügt. Jetzt in Syncthing auf dem PC die Anfragen annehmen.")
        except Exception as e:
            flash(f"Fehler: {e}")
        return redirect(url_for("winols_sync"))

    status, fehler = {"server_id": None, "pcs": []}, None
    try:
        eigene = st_api("GET", "/rest/system/status")["myID"]
        verbindungen = st_api("GET", "/rest/system/connections").get("connections", {})
        status["server_id"] = eigene
        for d in st_api("GET", "/rest/config/devices"):
            if d["deviceID"] != eigene:
                status["pcs"].append({"id": d["deviceID"], "name": d.get("name") or "?",
                                      "verbunden": verbindungen.get(d["deviceID"], {}).get("connected", False)})
    except Exception as e:
        fehler = str(e)
    return render_template("winols.html", status=status, fehler=fehler)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = {
"basis.html": """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OneClick Tuning</title>
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
input[type=text],input[type=password],input[type=number]{width:100%;padding:10px 12px;border-radius:8px;
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
.s-WARTET,.a-PRUEFEN{background:#e0a52622;color:var(--warn)}
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
</style></head><body>
<header><div class="logo">ONE<span>CLICK</span> TUNING</div>
<nav><a href="{{ url_for('start') }}">Upload</a>
{% if session.admin %}<a href="{{ url_for('admin') }}">Aufträge</a>
<a href="{{ url_for('admin_archiv') }}">Archiv</a><a href="{{ url_for('winols_sync') }}">WinOLS-Sync</a>
<a href="{{ url_for('einstellungen') }}">Einstellungen</a>
<a href="{{ url_for('logout') }}">Abmelden</a>{% endif %}</nav></header>
<main>
{% for m in get_flashed_messages() %}<div class="meldung">{{ m }}</div>{% endfor %}
{% block inhalt %}{% endblock %}
</main></body></html>""",

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
<form method="post" action="{{ url_for('auftrag_neu') }}" enctype="multipart/form-data" id="f">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<label class="drop" id="drop"><input type="file" name="datei" id="datei">
<div id="dropText"><b>Originaldatei hierher ziehen</b><br>oder klicken zum Auswählen (.bin, .ori, max. 16 MB)</div></label>
<div class="optionen">
{% for key, name in optionen.items() %}
<label><input type="radio" name="option" value="{{ key }}" {{ 'checked' if loop.first }}><span>{{ name }}</span></label>
{% endfor %}</div>
<input type="text" name="kontakt" placeholder="Name / Firma / Telefon (optional, falls wir dich erreichen müssen)">
<button class="btn" id="los">Auftrag senden</button>
<div class="hinweis">Jeder Auftrag wird von uns kurz freigegeben, danach kannst du das File herunterladen.
Checksumme bitte beim Schreiben vom Flash-Tool korrigieren lassen.</div>
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
document.getElementById('f').addEventListener('submit',()=>{const b=document.getElementById('los');b.textContent='Wird gesendet …';b.disabled=true});
</script>
{% endblock %}""",

"auftrag.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte">
<h1>{{ optionen[a.option] }} · {{ a.datei }}</h1>
<p><span class="status s-{{ a.status }}">{{ status_text[a.status] }}</span>
<span class="leise">&nbsp; {{ a.zeit[:16].replace('T',' ') }}</span></p>
<table><tr><th>ECU</th><td>{{ a.ecu }}</td></tr><tr><th>Software</th><td>{{ a.software }}</td></tr>
{% if session.admin %}<tr><th>Kontakt</th><td>{{ a.kunde }}</td></tr>
<tr><th>Automatik</th><td><span class="status a-{{ a.automatik }}">{{ automatik_text[a.automatik] }}</span> {{ a.sicherheit }} %{% if a.eigenes_file %} · eigenes File hochgeladen{% endif %}</td></tr>
<tr><th>Quelle</th><td>{{ a.quelle or '–' }}</td></tr>
{% if a.entschieden %}<tr><th>Entschieden</th><td>{{ a.entschieden[:16].replace('T',' ') }} von {{ a.entschieden_von }}</td></tr>{% endif %}
{% endif %}</table><br>

{% if a.status == 'FREIGEGEBEN' %}
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

{% if session.admin %}
<div class="karte"><h2>Admin</h2>
<p><a href="{{ url_for('original', aid=a.id) }}">Original herunterladen</a>
{% if hat_file %} · <a href="{{ url_for('download', aid=a.id) }}">Erstelltes File herunterladen (zum Prüfen)</a>{% endif %}</p>
{% if a.status == 'WARTET' %}
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">
{% if hat_file %}<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="ok">
<button class="btn gruen">✓ Bestätigen</button></form>
{% else %}<p class="leise">Kein automatisches File, bitte unten die fertige Datei hochladen oder ablehnen.</p>{% endif %}
</div>
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" style="margin-bottom:22px">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="nein">
<input type="text" name="grund" placeholder="Grund für die Ablehnung (optional, sieht der Kunde)">
<button class="btn">✕ Ablehnen</button></form>
<form method="post" action="{{ url_for('fertig_hochladen', aid=a.id) }}" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<p><b>Oder eigenes File hochladen und freigeben</b> (ohne Checksumme ist ok)</p>
<p><input type="file" name="datei"></p>
<input type="text" name="archiv_name" placeholder="Archivname, z. B. golf7_20tdi_03L906018JL (leer = nicht ins Archiv)">
<button class="btn grau">Hochladen &amp; freigeben</button></form>
{% endif %}
<h2 style="margin-top:22px">Bericht</h2><pre>{{ a.bericht | join('\\n') }}</pre></div>
{% endif %}
{% endblock %}""",

"admin.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="raster" style="margin-bottom:22px">
<div class="karte"><div class="leise">Warten auf Freigabe</div><div class="zahl">{{ wartend|length }}</div></div>
<div class="karte"><div class="leise">Automatisch erstellt</div><div class="zahl">{{ auto }}</div></div>
<div class="karte"><div class="leise">Files im Archiv</div><div class="zahl">{{ archiv }}</div>
<form method="post" action="{{ url_for('index_neu') }}"><input type="hidden" name="csrf" value="{{ session.csrf }}">
<button class="btn grau klein" style="margin-top:6px">Neu einlesen</button></form></div>
</div>
<div class="karte"><h2>Warten auf Freigabe</h2>
<p class="hinweis" style="margin-top:-6px">Telegram: {{ 'aktiv' if telegram else 'nicht eingerichtet' }} · WhatsApp: {{ 'aktiv' if whatsapp else 'nicht eingerichtet' }} ·
Diese Seite meldet neue Aufträge mit Ton. <a href="#" id="benachrichtigung">Browser-Benachrichtigungen erlauben</a></p>
{% if wartend %}<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>ECU</th><th>Automatik</th><th></th></tr>
{% for a in wartend %}<tr><td>{{ a.zeit[8:10] }}.{{ a.zeit[5:7] }}. {{ a.zeit[11:16] }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td>{{ a.ecu }}</td><td><span class="status a-{{ a.automatik }}">{{ a.sicherheit }} %</span></td>
<td>{% if a.hat_file %}<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="ok">
<input type="hidden" name="zurueck" value="{{ url_for('admin') }}"><button class="btn gruen klein">✓ Bestätigen</button></form>{% endif %}
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="nein">
<input type="hidden" name="zurueck" value="{{ url_for('admin') }}"><button class="btn klein">✕ Ablehnen</button></form></td></tr>
{% endfor %}</table></div>{% else %}<p class="leise">Nichts offen.</p>{% endif %}</div>
<div class="karte"><h2>Alle Aufträge</h2>
<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>Automatik</th><th>Status</th></tr>
{% for a in alle %}<tr><td>{{ a.zeit[:16].replace('T',' ') }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td><span class="status a-{{ a.automatik }}">{{ a.sicherheit }} %</span></td>
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
<div class="karte"><h1>Archiv</h1>
<p class="leise">Je mehr Original/Tuning-Paare im Archiv liegen, desto mehr Aufträge werden automatisch erstellt.</p>
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
</script>
{% endblock %}""",

"einstellungen.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>Einstellungen</h1>
<form method="post"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="speichern">
<label class="feld">Adresse der Seite</label>
<input type="text" name="basis_url" value="{{ cfg.basis_url or '' }}" placeholder="https://files.deine-firma.de">
<label class="feld">Telegram-Bot-Token (von @BotFather)</label>
<input type="password" name="telegram_token" value="{{ cfg.telegram_token or '' }}" placeholder="123456789:ABC…" autocomplete="off">
<label class="feld">Telegram-Chat-ID</label>
<input type="text" name="telegram_chat_id" value="{{ cfg.telegram_chat_id or '' }}" placeholder="wird unten automatisch gefunden">
<label class="feld">Erledigte Kundenaufträge automatisch löschen nach … Tagen (0 = nie). Das Archiv bleibt immer erhalten.</label>
<input type="number" name="aufbewahrung_tage" min="0" value="{{ cfg.get('aufbewahrung_tage', 90) }}">
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

<div class="karte"><h2>Aufräumen</h2>
<p class="leise">Läuft automatisch alle 6 Stunden. Wartende Aufträge werden nie gelöscht.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="aufraeumen">
<button class="btn grau">Jetzt aufräumen</button></form></div>
{% endblock %}""",

"winols.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>WinOLS-Sync</h1>
<p>Alle Kunden-Originale (und erstellte Files) landen automatisch in einem Ordner auf deinem PC, den du in WinOLS öffnen kannst.
Dein Archiv wird in beide Richtungen abgeglichen: Neue Fahrzeug-Ordner, die du auf dem PC ins Archiv legst, werden auf dem Server automatisch gelernt.</p>
{% if fehler %}<div class="meldung">Syncthing auf dem Server ist nicht erreichbar: {{ fehler }}</div>{% else %}
<ol>
<li><b>Syncthing auf dem PC installieren:</b> <a href="https://syncthing.net/downloads/" target="_blank" rel="noopener">syncthing.net/downloads</a> → für Windows „Syncthing Windows Setup“ nehmen. Danach öffnet sich Syncthing im Browser.</li>
<li>In Syncthing auf dem PC: <b>Aktionen → ID anzeigen</b> → die lange ID kopieren und unten eintragen.</li>
<li>Kurz warten, dann erscheinen in Syncthing auf dem PC Anfragen: <b>„Gerät hinzufügen“</b> → annehmen, danach <b>„Tuning-Archiv“</b> und <b>„Tuning-Auftraege“</b> → annehmen und einen Ordner wählen, z. B. <code>C:\\Tuning\\Archiv</code> und <code>C:\\Tuning\\Auftraege</code>.
Beim Ordner „Tuning-Auftraege“ unter „Erweitert“ den Typ <b>„Nur empfangen“</b> wählen.</li>
</ol>
<p class="leise">Server-ID (falls Syncthing danach fragt): <code>{{ status.server_id }}</code></p>
<form method="post" style="margin-top:14px"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="hinzufuegen">
<label class="feld">Geräte-ID deines PCs</label><input type="text" name="pc_id" placeholder="XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX">
<label class="feld">Name (frei wählbar)</label><input type="text" name="pc_name" placeholder="Werkstatt-PC">
<button class="btn">PC hinzufügen</button></form>{% endif %}</div>
{% if status.pcs %}<div class="karte"><h2>Verbundene PCs</h2><div class="tabelle"><table><tr><th>Name</th><th>Status</th><th>ID</th><th></th></tr>
{% for pc in status.pcs %}<tr><td>{{ pc.name }}</td><td><span class="status {{ 's-FREIGEGEBEN' if pc.verbunden else 's-WARTET' }}">{{ 'verbunden' if pc.verbunden else 'nicht verbunden' }}</span></td>
<td class="leise">{{ pc.id[:15] }}…</td><td><form method="post" class="inline" onsubmit="return confirm('PC entfernen?')"><input type="hidden" name="csrf" value="{{ session.csrf }}">
<input type="hidden" name="aktion" value="entfernen"><input type="hidden" name="pc_id" value="{{ pc.id }}"><button class="btn grau klein">Entfernen</button></form></td></tr>
{% endfor %}</table></div></div>{% endif %}
{% endblock %}""",
}
app.jinja_loader = DictLoader(TEMPLATES)


@app.context_processor
def globale():
    return {"optionen": OPTION_NAMEN, "status_text": STATUS_TEXT, "automatik_text": AUTOMATIK_TEXT}


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
                         "kunde": "Testkunde", "automatik": "AUTOMATISCH", "sicherheit": 100.0})
        print("Gesendet (Fehler würden oben stehen).")
    else:
        AUFTRAEGE.mkdir(exist_ok=True)
        EXPORT.mkdir(exist_ok=True)
        threading.Thread(target=telegram_schleife, daemon=True).start()
        threading.Thread(target=hintergrund, daemon=True).start()
        host = os.environ.get("ONECLICK_HOST", "0.0.0.0")
        try:
            from waitress import serve
            print(f"Server läuft auf http://{host}:5000")
            serve(app, host=host, port=5000, max_request_body_size=4 * 1024 * 1024 * 1024,
                  trusted_proxy="127.0.0.1", trusted_proxy_headers="x-forwarded-proto x-forwarded-for x-forwarded-host")
        except ImportError:
            app.run(host="0.0.0.0", port=5000)
