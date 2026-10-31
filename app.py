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
import hmac
import io
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
import urllib.parse
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
EINGANG = BASE / "eingang"   # lose Dateien aus ZIP-Importen, die der Admin selbst zuordnet
EIGENE = BASE / "eigene"   # Admin: eigene Files kostenlos durch das Archiv schicken (24 h)
BENUTZER_DATEI = BASE / "benutzer.json"
CONFIG_DATEI = BASE / "config.json"
SECRET_DATEI = BASE / ".secret_key"
KUNDENSEITE = BASE / "web" / "kunde.html"
RECHTSTEXTE = BASE / "web" / "rechtstexte"   # Standardtexte, wenn unter Einstellungen nichts eingetragen ist
RECHTLICHES = {"impressum": "Impressum", "datenschutz": "Datenschutz", "agb": "AGB",
               "widerruf": "Widerrufsbelehrung", "haftung": "Hinweise zu Einsatz und Haftung"}
STANDARD_WHATSAPP = "4915568540674"   # Support nach dem Download (Admin -> Einstellungen)



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
eingang_sperre = threading.Lock()
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


def entscheide(aid: str, freigeben: bool, grund: str = "", wer: str = "", preis: int = None) -> str:
    """Auftrag freigeben oder ablehnen. Wird von Webseite und Telegram genutzt.
    preis (Cent): anderer Preis fuer genau diesen Auftrag (sonst der beim Bestellen berechnete)."""
    with sperre:
        auftrag = finde_auftrag(aid)
        if auftrag is None:
            return "Auftrag nicht gefunden."
        if auftrag["status"] != "WARTET":
            return f"Auftrag ist schon {STATUS_TEXT[auftrag['status']].lower()}."
        if freigeben and not hat_file(aid):
            return "Kein File vorhanden. Erst die fertige Datei hochladen."
        auftrag["status"] = "FREIGEGEBEN" if freigeben else "ABGELEHNT"
        if freigeben and preis is not None:
            auftrag["preis"] = preis
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


# Datenschutz: Telegram (ausserhalb der EU) bekommt keine personenbezogenen Daten - keinen Dateinamen,
# keine Kontaktangabe, keine Nachricht des Kunden und keine Datei. Details nur im Admin-Bereich.
def telegram_text(a: dict) -> str:
    if a.get("typ") == "anfrage":
        return telegram_text_anfrage(a)
    a = {k: html.escape(v) if isinstance(v, str) else v for k, v in a.items()}
    zeilen = [
        f"🔧 <b>Neuer Auftrag: {html.escape(option_namen()[a['option']])}</b>",
        f"ECU: {a['ecu']}",
        f"Software: {a['software']}",
        (f"Treffer: ⚠️ {ART_TEXT['softwarenummer']}" if a.get("art") == "softwarenummer"
         else f"Treffer: 100 % – {ART_TEXT.get(a['art'], a['art'])}"),
        f"Quelle: {a['quelle'] or '–'}",
    ]
    if zahlung_aktiv() and a.get("preis"):
        zeilen.append(f"Preis: {euro(a['preis'])}")
    if a["status"] == "WARTET" and not lade_config().get("basis_url", "").startswith("https://"):
        zeilen.append("\nDetails im Admin-Bereich.")
    if a["status"] == "FREIGEGEBEN":
        zeilen.append("\n✅ <b>FREIGEGEBEN</b>" + zahlung_zeile(a))
    elif a["status"] == "ABGELEHNT":
        zeilen.append("\n❌ <b>ABGELEHNT</b>" + (f": {a['grund']}" if a.get("grund") else ""))
    return "\n".join(zeilen)


def zahlung_zeile(a: dict) -> str:
    if a.get("bezahlt"):
        return f"\n💶 <b>BEZAHLT</b> ({euro(a.get('betrag') or a.get('preis') or 0)})"
    if zahlung_offen(a):
        return f"\n⏳ Zahlung offen ({euro(a['preis'])})"
    return ""


def telegram_text_anfrage(a: dict) -> str:
    e = lambda x: html.escape(str(x or "–"))
    fz = a.get("fahrzeug") or {}
    fahrzeug = " ".join(x for x in (fz.get("marke"), fz.get("modell"), fz.get("baujahr"), fz.get("motor")) if x)
    zeilen = [f"📩 <b>Neue Anfrage: {e(option_namen()[a['option']])}</b>",
              f"Fahrzeug: {e(fahrzeug)}", f"ECU: {e(a['ecu'])}", f"Software: {e(a['software'])}"]
    if a["status"] == "WARTET":
        zeilen.append("\nOriginal und alle Angaben im Admin-Bereich. Fertiges File dort hochladen – "
                      "dann bekommt der Kunde es automatisch auf der Seite.")
    elif a["status"] == "FREIGEGEBEN":
        zeilen.append("\n✅ <b>FERTIG – an den Kunden geschickt</b>" + zahlung_zeile(a))
    elif a["status"] == "ABGELEHNT":
        zeilen.append("\n❌ <b>ABGELEHNT</b>" + (f": {e(a['grund'])}" if a.get("grund") else ""))
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
    if request.path.startswith("/api/") or request.path == "/stripe/webhook":
        return  # API: keine Cookies (Zugriff ueber die geheime Auftragsnummer); Stripe signiert selbst
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
    return rechtsseite("impressum")


def rechtstext(art: str) -> str:
    """Eigener Text aus den Einstellungen, sonst der mitgelieferte Standardtext."""
    eigen = (lade_config().get(art) or "").strip()
    if eigen:
        return eigen
    pfad = RECHTSTEXTE / f"{art}.txt"
    text = pfad.read_text(encoding="utf-8") if pfad.exists() else ""
    tage = int(lade_config().get("aufbewahrung_tage", 90) or 0)
    return text.replace("{AUFBEWAHRUNG}", f"nach {tage} Tagen" if tage else "nicht")


def rechtsseite(art: str):
    return render_template("text.html", titel=RECHTLICHES[art], text=rechtstext(art))


@app.route("/datenschutz")
def datenschutz():
    return rechtsseite("datenschutz")


@app.route("/agb")
def agb():
    return rechtsseite("agb")


@app.route("/widerruf")
def widerruf():
    return rechtsseite("widerruf")


@app.route("/haftung")
def haftung():
    return rechtsseite("haftung")


@app.template_filter("rechtstext")
def rechtstext_html(text: str):
    """Einfache Formatierung: Zeilen mit '## ' werden Ueberschriften, Links werden klickbar."""
    from markupsafe import Markup, escape
    teile = []
    for zeile in (text or "").split("\n"):
        if zeile.startswith("## "):
            teile.append(f"<h3>{escape(zeile[3:].strip())}</h3>")
        else:
            z = str(escape(zeile))
            z = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', z)
            teile.append(z + "\n")
    return Markup("".join(teile))


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
                    for opt, l in sorted(loesungen.items(), key=lambda t: oneclick.reihen_index(t[0]))},
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
                       preis=preis_von(wunsch),
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
        auftrag.update(option="+".join(auswahl), status="WARTET", preis=preis_von(auswahl),
                       kunde=kontakt.strip()[:100] or "–",
                       quelle=", ".join(dict.fromkeys(angebot[o]["quelle"] for o in auswahl)),
                       art=art,
                       zeit=datetime.now().isoformat(timespec="seconds"))
        speichere_auftrag(auftrag)
    threading.Thread(target=benachrichtigen, args=(auftrag,), daemon=True).start()
    return auftrag


# ---------------------------------------------------------------------------
# Bezahlen mit Stripe: erst Freigabe, dann Zahlung, dann Download
# ---------------------------------------------------------------------------

STRIPE_API = "https://api.stripe.com/v1"
ZUSTIMMUNG_TEXT = ("Ich habe die AGB und die Hinweise zu Einsatz und Haftung gelesen und akzeptiere sie. "
                   "Ich verlange ausdrücklich, dass ihr vor Ablauf der Widerrufsfrist mit der Ausführung beginnt. "
                   "Mir ist bekannt, dass ich mit Beginn der Ausführung mein Widerrufsrecht verliere.")
_stripe_zuletzt = {}   # Auftrag -> Zeitpunkt der letzten Nachfrage bei Stripe (nicht oefter als alle 5 s)


def zahlung_aktiv() -> bool:
    return bool(lade_config().get("stripe_key"))


def preise() -> dict:
    """Feste Preise pro Loesung in Cent (Admin -> Archiv -> Lösungen)."""
    roh = lade_config().get("preise") or {}
    return {k: v for k, v in roh.items() if isinstance(v, int) and v > 0}


def preis_von(optionen) -> int:
    p = preise()
    return sum(p.get(teil, 0) for o in optionen for teil in o.split("+"))


def euro(cent: int) -> str:
    text = f"{(cent or 0) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def cent_aus(text: str) -> int:
    """'249', '249,00', '1.249,50 €' -> Cent."""
    t = str(text).replace("€", "").replace(" ", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        wert = round(float(t) * 100)
    except ValueError:
        raise ValueError(f"„{text}“ ist kein gültiger Preis.")
    if wert < 0 or wert > 10_000_000:
        raise ValueError(f"„{text}“ ist kein gültiger Preis.")
    return wert


def zahlung_offen(a: dict) -> bool:
    return (a.get("status") == "FREIGEGEBEN" and (a.get("preis") or 0) > 0 and not a.get("bezahlt")
            and zahlung_aktiv())


def stripe_anfrage(methode: str, pfad: str, felder: list = None) -> dict:
    schluessel = lade_config().get("stripe_key", "")
    daten = urllib.parse.urlencode(felder).encode() if felder is not None else None
    req = urllib.request.Request(STRIPE_API + pfad, data=daten, method=methode,
                                 headers={"Authorization": f"Bearer {schluessel}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            text = json.loads(e.read())["error"]["message"]
        except Exception:
            text = f"HTTP {e.code}"
        raise RuntimeError(f"Stripe: {text}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Stripe nicht erreichbar: {e}")


def basis_adresse() -> str:
    basis = lade_config().get("basis_url", "").rstrip("/")
    return basis if basis.startswith(("https://", "http://")) else request.host_url.rstrip("/")


def bezahlen_starten(aid: str, zustimmung: bool) -> str:
    """Stripe-Bezahlseite fuer einen freigegebenen Auftrag -> URL."""
    auftrag = finde_auftrag(aid)
    if auftrag is None:
        raise Abgelehnt("Auftrag nicht gefunden.")
    if not zahlung_offen(auftrag):
        raise Abgelehnt("Für diesen Auftrag ist nichts zu bezahlen.")
    if not zustimmung:
        raise Abgelehnt("Bitte bestätige vorher den Hinweis zum Widerrufsrecht.")
    if zu_viele("bezahlen", 20, 3600):
        raise Abgelehnt("Zu viele Versuche. Bitte später nochmal.")
    merken("bezahlen")
    try:
        if auftrag.get("stripe_session"):   # noch offene Bezahlseite weiterverwenden
            s = stripe_anfrage("GET", f"/checkout/sessions/{auftrag['stripe_session']}")
            if s.get("payment_status") == "paid":
                zahlung_verbuchen(s)
                raise Abgelehnt("Schon bezahlt – du kannst jetzt herunterladen.")
            if s.get("status") == "open" and s.get("amount_total") == auftrag["preis"]:
                return s["url"]
        basis = basis_adresse()
        name = option_namen()[auftrag["option"]]
        s = stripe_anfrage("POST", "/checkout/sessions", [
            ("mode", "payment"),
            ("locale", "de"),
            ("success_url", f"{basis}/?bezahlt={aid}"),
            ("cancel_url", f"{basis}/?abgebrochen={aid}"),
            ("client_reference_id", aid),
            ("metadata[auftrag]", aid),
            ("payment_intent_data[metadata][auftrag]", aid),
            ("line_items[0][quantity]", "1"),
            ("line_items[0][price_data][currency]", "eur"),
            ("line_items[0][price_data][unit_amount]", str(auftrag["preis"])),
            ("line_items[0][price_data][product_data][name]", name),
            ("line_items[0][price_data][product_data][description]", f"ECU-File · Auftrag {aid[:8]}"),
            ("invoice_creation[enabled]", "true"),   # Rechnung per E-Mail von Stripe
        ])
    except RuntimeError as e:
        print(f"Bezahlen fehlgeschlagen ({aid}): {e}", file=sys.stderr)
        raise Abgelehnt("Die Bezahlseite ist gerade nicht erreichbar. Bitte gleich nochmal versuchen.")
    with sperre:
        aktuell = finde_auftrag(aid)
        aktuell.update(stripe_session=s["id"], zustimmung=datetime.now().isoformat(timespec="seconds"),
                       zustimmung_text=ZUSTIMMUNG_TEXT)
        speichere_auftrag(aktuell)
    return s["url"]


def zahlung_verbuchen(s: dict) -> bool:
    """Stripe-Checkout-Session (bezahlt) dem Auftrag gutschreiben. Prueft Betrag und Waehrung."""
    aid = (s.get("metadata") or {}).get("auftrag") or s.get("client_reference_id") or ""
    if s.get("payment_status") != "paid":
        return False
    with sperre:
        auftrag = finde_auftrag(aid)
        if auftrag is None or auftrag.get("bezahlt"):
            return False
        if s.get("currency") != "eur" or s.get("amount_total") != auftrag.get("preis"):
            print(f"Zahlung passt nicht zum Auftrag {aid}: {s.get('amount_total')} {s.get('currency')}", file=sys.stderr)
            return False
        auftrag.update(bezahlt=True, bezahlt_am=datetime.now().isoformat(timespec="seconds"),
                       betrag=s["amount_total"], zahlung_id=s.get("payment_intent") or s.get("id"),
                       stripe_session=s.get("id"))
        speichere_auftrag(auftrag)
    def melden():
        chat = lade_config().get("telegram_chat_id")
        if chat:
            telegram_api("sendMessage", {"chat_id": chat, "parse_mode": "HTML", "text":
                         f"💶 <b>Bezahlt:</b> {html.escape(option_namen()[auftrag['option']])} – {euro(auftrag['betrag'])}"})
        telegram_aktualisieren(auftrag)
    threading.Thread(target=melden, daemon=True).start()
    return True


def stripe_pruefen(auftrag: dict) -> dict:
    """Bei Stripe nachfragen, ob die Bezahlseite eines Auftrags bezahlt wurde (falls der Webhook fehlt)."""
    sid = auftrag.get("stripe_session")
    if not sid or time.time() - _stripe_zuletzt.get(auftrag["id"], 0) < 5:
        return auftrag
    _stripe_zuletzt[auftrag["id"]] = time.time()
    if len(_stripe_zuletzt) > 5000:
        _stripe_zuletzt.clear()
    try:
        zahlung_verbuchen(stripe_anfrage("GET", f"/checkout/sessions/{sid}"))
    except RuntimeError as e:
        print(f"Stripe-Prüfung ({auftrag['id']}): {e}", file=sys.stderr)
    return finde_auftrag(auftrag["id"]) or auftrag


def stripe_signatur_ok(inhalt: bytes, kopf: str, geheim: str, toleranz: int = 300) -> bool:
    teile = [x.split("=", 1) for x in kopf.split(",") if "=" in x]
    zeit = next((v for k, v in teile if k == "t"), "")
    signaturen = [v for k, v in teile if k == "v1"]
    try:
        if not signaturen or abs(time.time() - int(zeit)) > toleranz:
            return False
    except ValueError:
        return False
    erwartet = hmac.new(geheim.encode(), zeit.encode() + b"." + inhalt, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(erwartet, s) for s in signaturen)


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    geheim = lade_config().get("stripe_webhook_secret", "")
    if not geheim or not stripe_signatur_ok(request.get_data(), request.headers.get("Stripe-Signature", ""), geheim):
        abort(400)
    ereignis = request.get_json(silent=True) or {}
    if ereignis.get("type") in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        zahlung_verbuchen((ereignis.get("data") or {}).get("object") or {})
    return jsonify(ok=True)


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
        "preis": a.get("preis", 0) if zahlung_aktiv() else 0,
        "preis_text": euro(a["preis"]) if zahlung_aktiv() and a.get("preis") else "",
        "zahlung": "bezahlt" if a.get("bezahlt") else "offen" if zahlung_offen(a) else None,
    }


@app.route("/api/info")
def api_info():
    namen = option_namen()
    return jsonify(firma=lade_config().get("firmenname") or "OneClick Tuning", api=1,
                   original=oneclick.ORIGINAL,
                   optionen=[{"key": o, "name": namen[o]} for o in oneclick.optionen()],   # fuer Anfragen
                   fahrzeug_felder=[{"key": f, "name": n, "pflicht": p} for f, n, p in FAHRZEUG_FELDER],
                   zahlung_aktiv=zahlung_aktiv(), preise=preise() if zahlung_aktiv() else {},
                   support_whatsapp=lade_config().get("support_whatsapp", STANDARD_WHATSAPP))


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
    auftrag = lade_auftrag(aid)
    if zahlung_offen(auftrag):   # falls die Meldung von Stripe (Webhook) noch fehlt: selbst nachfragen
        auftrag = stripe_pruefen(auftrag)
    return jsonify(api_auftrag(auftrag))


@app.route("/api/auftrag/<aid>/bezahlen", methods=["POST"])
def api_bezahlen(aid):
    daten = request.get_json(silent=True)
    daten = daten if isinstance(daten, dict) else {}
    try:
        return jsonify(url=bezahlen_starten(aid, daten.get("zustimmung") is True))
    except Abgelehnt as e:
        return jsonify(fehler=str(e)), 422


@app.route("/auftrag/<aid>")
@admin_noetig
def auftrag_ansicht(aid):
    return render_template("auftrag.html", a=lade_auftrag(aid), hat_file=hat_file(aid),
                           fahrzeug_felder=FAHRZEUG_FELDER, zahlung=zahlung_aktiv(), euro=euro,
                           stripe_key=lade_config().get("stripe_key", ""))


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
    if not session.get("admin") and zahlung_offen(auftrag):
        auftrag = stripe_pruefen(auftrag)
        if zahlung_offen(auftrag):
            return jsonify(fehler="Bitte zuerst bezahlen – danach kannst du das File herunterladen."), 402
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
                           zahlung=zahlung_aktiv(), euro=euro,
                           bezahlt=sum(a.get("betrag") or 0 for a in alle if a.get("bezahlt")))


@app.route("/admin/suche")
@admin_noetig
def auftrag_suche():
    """Auftrag ueber die Kurz-Nummer finden (der Kunde schickt sie per WhatsApp)."""
    q = re.sub(r"[^0-9a-f]", "", request.args.get("q", "").lower())
    if len(q) < 4:
        flash("Bitte mindestens die ersten 4 Zeichen der Auftrags-Nr. eingeben.")
        return redirect(url_for("admin"))
    treffer = [a for a in alle_auftraege() if a["id"].startswith(q) and a["status"] != "ENTWURF"]
    if len(treffer) == 1:
        return redirect(url_for("auftrag_ansicht", aid=treffer[0]["id"]))
    flash("Kein Auftrag mit dieser Nummer gefunden (vielleicht schon gelöscht)." if not treffer
          else f"{len(treffer)} Aufträge passen – bitte mehr Zeichen eingeben.")
    return redirect(url_for("admin"))


@app.route("/admin/wartend")
@admin_noetig
def admin_wartend():
    return jsonify(ids=[a["id"] for a in alle_auftraege() if a["status"] == "WARTET"])


@app.route("/admin/auftrag/<aid>/entscheiden", methods=["POST"])
@admin_noetig
def admin_entscheiden(aid):
    freigeben = request.form.get("aktion") == "ok"
    try:
        preis = cent_aus(request.form["preis"]) if request.form.get("preis", "").strip() else None
    except ValueError as e:
        flash(str(e))
        return redirect(url_for("auftrag_ansicht", aid=aid))
    flash(entscheide(aid, freigeben, request.form.get("grund", ""), wer=session["benutzer"], preis=preis))
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
    try:
        preis = cent_aus(request.form["preis"]) if request.form.get("preis", "").strip() else None
    except ValueError as e:
        flash(str(e))
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
    meldung = entscheide(aid, True, wer=session["benutzer"], preis=preis)

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


def archiv_speichern(name: str, ori: bytes, mods: dict, ersetzen: bool = True, index: bool = True) -> dict:
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
    if index:
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


# ---------------------------------------------------------------------------
# Sortieren: lose Dateien selbst zu Fahrzeugen zuordnen
# ---------------------------------------------------------------------------

BLOCK = 4096
AEHNLICH = 0.5   # Anteil gleicher (nicht leerer) 4-KB-Bloecke, ab dem zwei Files zum selben Fahrzeug gehoeren


def block_abdruck(daten: bytes) -> list:
    """Pro 4-KB-Block ein Hash; leere Bloecke (nur ein Bytewert, z. B. FF) zaehlen nicht."""
    aus, daten = [], bytes(daten)
    for i in range(0, len(daten), BLOCK):
        x = daten[i:i + BLOCK]
        aus.append(None if x.count(x[:1]) == len(x) else hash(x))
    return aus


def aehnlichkeit(a: list, b: list) -> float:
    """0..1: wie viele inhaltliche Bloecke gleich sind (Original vs. Tuning meist > 0,8, fremde Files ~0)."""
    if len(a) != len(b):
        return 0.0
    zaehl = sum(1 for x in a if x is not None)
    if not zaehl:
        return 1.0 if a == b else 0.0
    return sum(1 for x, y in zip(a, b) if x is not None and x == y) / zaehl


def gruppieren(abdruecke: list) -> list:
    """Dateien mit gleicher Groesse und aehnlichem Inhalt in Gruppen -> Gruppennummer je Datei."""
    eltern = list(range(len(abdruecke)))
    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i
    nach_groesse = {}
    for i, a in enumerate(abdruecke):
        nach_groesse.setdefault(len(a), []).append(i)
    for liste in nach_groesse.values():
        for n, i in enumerate(liste):
            for j in liste[n + 1:]:
                if wurzel(i) != wurzel(j) and aehnlichkeit(abdruecke[i], abdruecke[j]) >= AEHNLICH:
                    eltern[wurzel(j)] = wurzel(i)
    nummern, aus = {}, []
    for i in range(len(abdruecke)):
        aus.append(nummern.setdefault(wurzel(i), len(nummern) + 1))
    return aus


def stapel_datei(sid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", sid):
        abort(404)
    return EINGANG / sid / "stapel.json"


def lade_stapel(sid: str) -> dict:
    pfad = stapel_datei(sid)
    if not pfad.exists():
        abort(404)
    return json.loads(pfad.read_text())


def alle_stapel() -> list:
    if not EINGANG.exists():
        return []
    liste = []
    for p in EINGANG.glob("*/stapel.json"):
        try:
            liste.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return sorted(liste, key=lambda s: s["zeit"])


def sichtbar(d: dict) -> bool:
    """Files mit Abgas-Abschaltung im Namen werden in 'Sortieren' ausgeblendet (sie werden nie uebernommen)."""
    return not oneclick.abgas_datei(d["name"])


def eingang_anzahl() -> int:
    return sum(1 for s in alle_stapel() for d in s["dateien"] if sichtbar(d))


_abdruck_cache, _auswertung_cache = {}, {}


def archiv_abdruck(pfad: Path) -> list:
    """Abdruck einer Archiv-Datei, zwischengespeichert bis sich die Datei aendert."""
    schluessel = (str(pfad), pfad.stat().st_mtime_ns)
    if schluessel not in _abdruck_cache:
        if len(_abdruck_cache) > 3000:
            _abdruck_cache.clear()
        _abdruck_cache[schluessel] = block_abdruck(pfad.read_bytes())
    return _abdruck_cache[schluessel]


def gruppe_auswerten(stapel: dict, gid: int):
    """Wie _gruppe_auswerten, aber zwischengespeichert bis sich Gruppe oder Archiv aendern."""
    index = oneclick.lade_index()
    schluessel = (stapel["id"], gid, tuple(sorted(d["id"] for d in stapel["dateien"] if d["gruppe"] == gid)), index.get("zeit"))
    if schluessel not in _auswertung_cache:
        if len(_auswertung_cache) > 2000:
            _auswertung_cache.clear()
        _auswertung_cache[schluessel] = _gruppe_auswerten(stapel, gid)
    return json.loads(json.dumps(_auswertung_cache[schluessel]))   # Kopie


def _gruppe_auswerten(stapel: dict, gid: int):
    """Vorschlaege fuer eine Gruppe: Original, Rollen, Name, passender Archiv-Eintrag, Abweichungen."""
    ordner = EINGANG / stapel["id"]
    dateien = [d for d in stapel["dateien"] if d["gruppe"] == gid]
    inhalt = {d["id"]: (ordner / f"{d['id']}.bin").read_bytes() for d in dateien}
    abdruck = {k: block_abdruck(v) for k, v in inhalt.items()}
    oris, mods_bekannt = archiv_kennt()
    for d in dateien:
        d["bekannt"] = oris.get(d["sha"]) and f"Original von „{oris[d['sha']]}“" \
            or (d["sha"] in mods_bekannt and "{} bei „{}“".format(option_namen()[mods_bekannt[d['sha']][1]], mods_bekannt[d['sha']][0])) or ""
    # Original: 1. schon im Archiv als Original, 2. Dateiname, 3. "Mitte" der Gruppe (ab 3 Files)
    ori_name, rollen = oneclick.klassifiziere([d["name"] for d in dateien])
    for d in dateien:
        d["abgas"] = oneclick.abgas_datei(d["name"])
    kandidaten = [d for d in dateien if not d["abgas"]]
    ori = next((d for d in kandidaten if d["sha"] in oris), None)
    ori_grund = "archiv" if ori else None
    if ori is None:
        ori = next((d for d in kandidaten if d["name"] == ori_name), None)
        ori_grund = "name" if ori else None
    if ori is None and len(dateien) >= 3 and kandidaten:
        # "Mitte" der Gruppe: das File, das allen anderen am aehnlichsten ist (auch Abgas-Files zaehlen als Vergleich,
        # koennen aber selbst kein Original sein)
        summen = sorted(((sum(aehnlichkeit(abdruck[d["id"]], abdruck[x["id"]]) for x in dateien if x is not d), n)
                         for n, d in enumerate(dateien)), reverse=True)
        mitte = dateien[summen[0][1]]
        if not mitte["abgas"]:
            ori = mitte
            # eindeutig nur, wenn das "mittlere" File klar aehnlicher zu allen anderen ist als das zweitbeste
            ori_grund = "mitte" if summen[0][0] - summen[1][0] >= 0.03 * (len(dateien) - 1) else "mitte-unsicher"
    # Passt die Gruppe zu einem Original im Archiv?
    archiv = None
    if ori is None or ori["sha"] not in oris:
        probe = abdruck[(ori or dateien[0])["id"]]
        info = oneclick.erkenne(inhalt[(ori or dateien[0])["id"]])
        nummern = set(info["bosch_sw"] + info["vag_teilenr"])
        for e in oneclick.lade_index()["eintraege"]:
            andere = set(e.get("bosch_sw", []) + e.get("vag_teilenr", []))
            if e["groesse"] == len(inhalt[dateien[0]["id"]]) and not (nummern and andere and not nummern & andere):
                a = aehnlichkeit(probe, archiv_abdruck(oneclick.archiv_datei(e)))
                if a >= AEHNLICH and (archiv is None or a > archiv[1]):
                    archiv = (e["name"], a)
    namen_rolle = {n: k for k, n in rollen.items()}
    for d in dateien:
        if d["abgas"] or (d["bekannt"] and not (ori and d is ori)):
            d["vorschlag"] = "ignorieren"
        elif ori and d is ori:
            d["vorschlag"] = oneclick.ORIGINAL
        else:
            d["vorschlag"] = namen_rolle.get(d["name"], "")
        bezug = abdruck[ori["id"]] if ori else None
        d["abweichung"] = None if bezug is None or d is ori else round((1 - aehnlichkeit(abdruck[d["id"]], bezug)) * 100, 1)
        d["name_vorschlag"] = sicherer_name(Path(d["name"]).stem)
        d["loesung_name"] = oneclick.loesung_aus_name(d["name"]) if not (ori and d is ori) else None
    gemeinsam = os.path.commonprefix([Path(d["name"]).stem for d in dateien]).strip(" _-.")
    ohne_namen = f"{dateien[0]['ecu'].split(',')[0]}_{dateien[0]['software'].split(',')[0]}".replace("?", "unbekannt")
    vorschlag = gemeinsam if len(gemeinsam) >= 4 else Path((ori or dateien[0])["name"]).stem
    if len(re.findall(r"[A-Za-z]", vorschlag)) < 3:   # "1001.bin" sagt nichts -> Steuergeraet + Software
        vorschlag = ohne_namen
    name = archiv[0] if archiv else oris.get(ori["sha"]) if ori and ori["sha"] in oris else vorschlag
    return {"id": gid, "dateien": dateien, "name": sicherer_name(name), "archiv": archiv[0] if archiv else None,
            "ori_id": ori["id"] if ori else None, "ori_grund": ori_grund,
            "groesse": len(inhalt[dateien[0]["id"]]), "ecu": dateien[0]["ecu"], "software": dateien[0]["software"]}


def eingang_anlegen(dateien: list, quelle: str) -> dict:
    """Lose Dateien [(name, inhalt)] als Stapel zum Sortieren ablegen und automatisch gruppieren.
    inhalt darf auch eine Funktion sein, die die Bytes erst liefert: so liegt beim ZIP-Import
    immer nur eine Datei im Arbeitsspeicher, egal wie gross das ZIP ist."""
    oris, mods = archiv_kennt()
    sid = uuid.uuid4().hex
    ordner = EINGANG / sid
    ordner.mkdir(parents=True)
    eintraege, abdruecke = [], []
    for name, daten in dateien:
        if len(eintraege) >= 3000:
            break
        daten = daten() if callable(daten) else daten
        if len(daten) < 1024:
            continue
        fid = uuid.uuid4().hex[:12]
        (ordner / f"{fid}.bin").write_bytes(daten)
        info = oneclick.erkenne(daten)
        abdruecke.append(block_abdruck(daten))
        eintraege.append({"id": fid, "name": PurePosixPath(name).name[:150], "groesse": len(daten), "sha": sha(daten),
                          "ecu": ", ".join(info["ecu"]) or "?",
                          "software": ", ".join(info["bosch_sw"] + info["vag_teilenr"]) or "?"})
        del daten
    for e, gid in zip(eintraege, gruppieren(abdruecke)):
        e["gruppe"] = gid
    stapel = {"id": sid, "quelle": PurePosixPath(quelle or "ZIP").name[:120],
              "zeit": datetime.now().isoformat(timespec="seconds"), "dateien": eintraege}
    json_speichern(ordner / "stapel.json", stapel)
    bekannt = sum(1 for e in eintraege if e["sha"] in oris or e["sha"] in mods)
    return {"id": sid, "dateien": len(eintraege), "gruppen": len({e["gruppe"] for e in eintraege}), "bekannt": bekannt}


def rolle_lesen(wert: str) -> str:
    """Formularwert -> 'original' | 'ignorieren' | Loesung | Kombination ('stage1+popsbangs') | ''."""
    teile = [x for x in (wert or "").split(",") if x]
    if not teile:
        return ""
    if teile in (["original"], [oneclick.ORIGINAL]):
        return oneclick.ORIGINAL
    if teile == ["ignorieren"]:
        return "ignorieren"
    unbekannt = [x for x in teile if x not in oneclick.optionen()]
    if unbekannt or len(teile) != len(set(teile)):
        raise Abgelehnt("Unbekannte Auswahl bei einer Datei. Bitte Seite neu laden.")
    return oneclick.kombi_schluessel(teile)


def gruppe_uebernehmen(sid: str, gid: int, name: str, rollen: dict, namen_ori: dict = None, index: bool = True,
                       zu: dict = None) -> list:
    """Rollen {Datei-ID: Formularwert} pruefen und ins Archiv uebernehmen.
    Mehrere Originale = mehrere Fahrzeuge: jedes Tuning-File kommt zum Original, dem es am aehnlichsten ist.
    Ein File kann mehrere Loesungen enthalten (z. B. Stage 1 + Pops & Bangs)."""
    stapel = lade_stapel(sid)
    dateien = {d["id"]: d for d in stapel["dateien"] if d["gruppe"] == gid}
    if not dateien:
        raise Abgelehnt("Diese Gruppe gibt es nicht mehr.")
    ordner = EINGANG / sid
    lesen = lambda f: (ordner / f"{f}.bin").read_bytes()
    rolle = {f: "ignorieren" if not sichtbar(dateien[f]) and not rollen.get(f) else rolle_lesen(rollen.get(f, ""))
             for f in dateien}
    abgas = [dateien[f]["name"] for f, r in rolle.items() if r != "ignorieren" and oneclick.abgas_datei(dateien[f]["name"])]
    if abgas:
        raise Abgelehnt(f"{', '.join(abgas[:3])}: laut Dateiname mit Abschaltung der Abgasreinigung – solche Files werden "
                        "nicht übernommen. Bitte auf „Ignorieren“ lassen.")
    offen = [dateien[f]["name"] for f, r in rolle.items() if not r]
    if offen:
        raise Abgelehnt(f"Bitte für jede Datei auswählen, was sie ist (oder „Ignorieren“): {', '.join(offen[:5])}")
    namen = option_namen()
    namen_ori = namen_ori or {}
    ori_ids = [f for f, r in rolle.items() if r == oneclick.ORIGINAL]
    tuning = [f for f, r in rolle.items() if r not in (oneclick.ORIGINAL, "ignorieren")]

    # Fahrzeuge bilden: {Name: (Original-Inhalt, [Tuning-IDs])}
    fahrzeuge = {}
    if ori_ids:
        abdruck = {f: block_abdruck(lesen(f)) for f in ori_ids + tuning}
        zuordnung = {o: [] for o in ori_ids}
        zu = zu or {}
        for f in tuning:
            if zu.get(f) in ori_ids:   # vom Admin festgelegt: "gehoert zu Original ..."
                zuordnung[zu[f]].append(f)
                continue
            bester = max(ori_ids, key=lambda o: aehnlichkeit(abdruck[f], abdruck[o]))
            if aehnlichkeit(abdruck[f], abdruck[bester]) < AEHNLICH:
                raise Abgelehnt(f"{dateien[f]['name']} passt zu keinem der markierten Originale. "
                                "Bitte in eine andere Gruppe verschieben oder auf „Ignorieren“ stellen.")
            zuordnung[bester].append(f)
        for o in ori_ids:
            n = sicherer_name(namen_ori.get(o) or (name if len(ori_ids) == 1 else ""))
            if n == "unbenannt":
                raise Abgelehnt(f"Bitte einen Namen für das Fahrzeug mit Original {dateien[o]['name']} eingeben.")
            if n in fahrzeuge:
                raise Abgelehnt(f"Der Name „{n}“ ist zweimal vergeben. Jedes Fahrzeug braucht einen eigenen Namen.")
            inhalt = lesen(o)
            frei = freier_archivname(n, inhalt)   # Name schon mit anderem Original belegt -> _2, _3 ...
            while frei in fahrzeuge:
                frei = freier_archivname(f"{frei}_x", inhalt)
            fahrzeuge[frei] = (inhalt, zuordnung[o])
    elif tuning:   # Original liegt schon im Archiv (nur Tuning-Files in der Gruppe)
        n = sicherer_name(name or "")
        e = next((e for e in oneclick.lade_index()["eintraege"] if e["name"] == n), None)
        if e is None:
            raise Abgelehnt("Kein Original markiert. Entweder eine Datei als Original wählen oder als Name "
                            "einen vorhandenen Archiv-Eintrag angeben, zu dem diese Tuning-Files gehören.")
        fahrzeuge[n] = (oneclick.archiv_datei(e).read_bytes(), tuning)

    # Pruefen, bevor irgendetwas gespeichert wird
    plan = []
    for n, (ori, ids) in fahrzeuge.items():
        mods = {}
        for f in ids:
            r, d = rolle[f], lesen(f)
            if r in mods:
                raise Abgelehnt(f"„{namen[r]}“ ist bei „{n}“ zweimal ausgewählt ({dateien[f]['name']}). "
                                "Gehören die Files zu verschiedenen Autos: jedes Original als „Original“ markieren und "
                                "bei den Tuning-Files unter „gehört zu“ das richtige Original wählen.")
            if len(d) != len(ori):
                raise Abgelehnt(f"{dateien[f]['name']}: andere Dateigröße als das Original.")
            if d == ori:
                raise Abgelehnt(f"{dateien[f]['name']}: ist identisch mit dem Original.")
            mods[r] = d
        plan.append((n, ori, mods))

    meldungen = []
    for n, ori, mods in plan:
        with index_sperre:
            meldungen += archiv_meldungen(archiv_speichern(n, ori, mods, index=index))
    with eingang_sperre:   # erledigte Dateien (auch ignorierte) aus dem Stapel entfernen
        stapel = lade_stapel(sid)
        stapel["dateien"] = [d for d in stapel["dateien"] if d["id"] not in dateien]
        for f in dateien:
            (ordner / f"{f}.bin").unlink(missing_ok=True)
        stapel_sichern(stapel)
    return meldungen or ["Nichts übernommen – alle Dateien standen auf „Ignorieren“."]


def auto_plan(g: dict):
    """Kann die Gruppe ohne Raten zugeordnet werden? -> (rollen, name, namen_ori) oder Begruendung (str)."""
    rollen, namen_ori = {}, {}
    ori_sicher = g["ori_id"] and g["ori_grund"] in ("archiv", "name", "mitte")
    for d in g["dateien"]:
        if d["vorschlag"] == "ignorieren":
            rollen[d["id"]] = "ignorieren"
        elif d["id"] == g["ori_id"] and ori_sicher:
            rollen[d["id"]] = oneclick.ORIGINAL
            namen_ori[d["id"]] = g["name"]
        elif d["loesung_name"]:
            rollen[d["id"]] = d["loesung_name"].replace("+", ",")
        elif d["id"] == g["ori_id"] or (not g["ori_id"] and len(g["dateien"]) <= 2 and not g["archiv"]):
            return "Original nicht sicher erkennbar"
        else:
            return "Lösung nicht aus dem Dateinamen erkennbar"
    if oneclick.ORIGINAL not in rollen.values() and any(r != "ignorieren" for r in rollen.values()) and not g["archiv"]:
        return "Original nicht sicher erkennbar"
    return rollen, g["name"], namen_ori


def freier_archivname(name: str, ori: bytes = None) -> str:
    """Name, unter dem nichts anderes liegt (sonst _2, _3 ...). Gleiches Original = gleicher Eintrag."""
    basis, n = name, 2
    while (oneclick.ARCHIV / name).exists():
        vorhanden, _ = oneclick.klassifiziere([p.name for p in (oneclick.ARCHIV / name).iterdir() if p.is_file()])
        if ori is not None and vorhanden and (oneclick.ARCHIV / name / vorhanden).read_bytes() == ori:
            break
        name, n = f"{basis}_{n}", n + 1
    return name


def stapel_sichern(stapel: dict):
    """Speichern; ein leerer Stapel wird komplett geloescht."""
    ordner = EINGANG / stapel["id"]
    if stapel["dateien"]:
        json_speichern(ordner / "stapel.json", stapel)
    else:
        shutil.rmtree(ordner, ignore_errors=True)


def importiere_zip(stream, alles_sortieren: bool = False, quelle: str = "ZIP") -> list:
    """ZIP ins Archiv. Was sich nicht automatisch zuordnen laesst (oder alles, wenn alles_sortieren),
    landet unter Archiv -> Sortieren, wo der Admin Original / Stage 1 / ... selbst festlegt."""
    meldungen, ok, ergaenzt, doppelt, abgas = [], 0, 0, 0, 0
    zum_sortieren = []   # (Dateiname, ZipInfo) -> spaeter Ergebnis von eingang_anlegen
    with zipfile.ZipFile(stream) as z:
        gruppen = {}
        for info in z.infolist():
            pfad = PurePosixPath(info.filename.replace("\\", "/"))
            if info.is_dir() or any(t.startswith(".") or t == "__MACOSX" for t in pfad.parts):
                continue
            if not oneclick.ist_ecu_datei(pfad.name) or info.file_size > 32 * 1024 * 1024:
                continue
            if oneclick.abgas_datei(pfad.name):
                abgas += 1
                continue
            ordner = str(pfad.parent)
            schluessel = ordner if ordner not in ("", ".") else flache_gruppe(pfad.name)
            gruppen.setdefault(schluessel, []).append(info)

        for schluessel, infos in sorted(gruppen.items()):
            namen = {PurePosixPath(i.filename).name: i for i in infos}
            ori_name, optionen = oneclick.klassifiziere(list(namen))
            if alles_sortieren or not ori_name:
                zum_sortieren += [(PurePosixPath(i.filename).name, i) for i in infos]
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
        if zum_sortieren:   # noch im with-Block: Dateien werden einzeln aus dem ZIP gelesen
            zum_sortieren = eingang_anlegen([(n, lambda i=i: z.read(i)) for n, i in zum_sortieren], quelle)
    with index_sperre:
        oneclick.baue_index()
    if abgas:
        meldungen.append(f"{abgas} Datei(en) mit Abschaltung der Abgasreinigung im Namen (DPF, AGR/EGR, AdBlue/SCR, NOx, "
                         "Lambda, Kat …) wurden nicht übernommen.")
    if zum_sortieren:
        erg = zum_sortieren
        meldungen.insert(0, f"{erg['dateien']} Datei(en) in {erg['gruppen']} Gruppe(n) warten unter „Sortieren“ darauf, "
                            "dass du Original, Stage 1 usw. zuordnest."
                            + (f" {erg['bekannt']} davon sind schon im Archiv." if erg["bekannt"] else ""))
        if alles_sortieren:
            return meldungen
    zeile = f"{ok} Fahrzeug(e) neu ins Archiv übernommen."
    if ergaenzt:
        zeile += f" {ergaenzt} vorhandene(s) ergänzt."
    if doppelt:
        zeile += f" {doppelt} waren schon komplett im Archiv und wurden übersprungen."
    return [zeile] + meldungen


@app.route("/admin/eigenes-file", methods=["GET", "POST"])
@admin_noetig
def eigenes_file():
    """Admin laedt selbst ein File hoch und bekommt die Treffer aus dem Archiv kostenlos -
    ohne Auftrag, ohne Zahlung, ohne Telegram."""
    if request.method == "GET":
        return render_template("eigenes.html", e=None)
    datei = request.files.get("datei")
    if not datei or not datei.filename:
        flash("Bitte ein File auswählen.")
        return redirect(url_for("eigenes_file"))
    daten = datei.read()
    if len(daten) < 1024:
        flash("Die Datei ist zu klein für ein ECU-File.")
        return redirect(url_for("eigenes_file"))
    jetzt = time.time()
    if EIGENE.exists():   # alte Vorgaenge (> 24 h) wegraeumen
        for alt in EIGENE.iterdir():
            if alt.is_dir() and jetzt - alt.stat().st_mtime > 86400:
                shutil.rmtree(alt, ignore_errors=True)
    info, loesungen = oneclick.finde_loesungen(daten, bool(lade_config().get("nur_identisch")))
    eid = uuid.uuid4().hex
    ordner = EIGENE / eid
    ordner.mkdir(parents=True)
    (ordner / "ori.bin").write_bytes(daten)
    for opt, l in loesungen.items():
        (ordner / f"loesung_{opt}.bin").write_bytes(l["daten"])
    e = {"id": eid, "datei": PurePosixPath(datei.filename.replace("\\", "/")).name[:150] or "datei.bin",
         "ecu": ", ".join(info["ecu"]) or "?", "software": ", ".join(info["bosch_sw"] + info["vag_teilenr"]) or "?",
         "angebot": {opt: {"quelle": l["quelle"], "art": l["art"]}
                     for opt, l in sorted(loesungen.items(), key=lambda t: oneclick.reihen_index(t[0]))}}
    json_speichern(ordner / "info.json", e)
    return render_template("eigenes.html", e=e, namen=option_namen())


@app.route("/admin/eigenes-file/<eid>", methods=["POST"])
@admin_noetig
def eigenes_file_download(eid):
    if not re.fullmatch(r"[0-9a-f]{32}", eid) or not (EIGENE / eid / "info.json").exists():
        flash("Das File ist nicht mehr da (älter als 24 Stunden). Bitte nochmal hochladen.")
        return redirect(url_for("eigenes_file"))
    ordner = EIGENE / eid
    e = json.loads((ordner / "info.json").read_text())
    auswahl = [o for o in e["angebot"] if o in request.form.getlist("option")]
    if not auswahl:
        flash("Bitte mindestens eine Lösung auswählen.")
        return render_template("eigenes.html", e=e, namen=option_namen())
    if oneclick.ORIGINAL in auswahl and len(auswahl) > 1:
        flash(f"„{oneclick.ORIGINAL_NAME}“ kann nicht mit anderen Lösungen kombiniert werden.")
        return render_template("eigenes.html", e=e, namen=option_namen())
    if len(auswahl) == 1:
        daten = (ordner / f"loesung_{auswahl[0]}.bin").read_bytes()
    else:
        daten = oneclick.kombiniere((ordner / "ori.bin").read_bytes(),
                                    [(ordner / f"loesung_{o}.bin").read_bytes() for o in auswahl])
        if daten is None:
            flash("Diese Kombination geht nicht, weil sich die Lösungen überschneiden. Bitte anders wählen.")
            return render_template("eigenes.html", e=e, namen=option_namen())
    return send_file(io.BytesIO(daten), as_attachment=True, mimetype="application/octet-stream",
                     download_name=f"{Path(e['datei']).stem}_{'+'.join(auswahl)}.bin")


@app.route("/admin/archiv")
@admin_noetig
def admin_archiv():
    eintraege = oneclick.lade_index()["eintraege"]
    zaehler = {}
    for e in eintraege:
        zaehler.setdefault(e.get("ori_sha256"), []).append(e["name"])
    doppelt = {n: [x for x in namen if x != n] for namen in zaehler.values() if len(namen) > 1 for n in namen}
    return render_template("archiv.html", eintraege=eintraege, doppelt=doppelt, preise=preise(),
                           zahlung=zahlung_aktiv(), euro=euro,
                           eigene=oneclick.eigene_optionen(), archiv_optionen=oneclick.optionen())


@app.route("/admin/loesungen", methods=["POST"])
@admin_noetig
def loesungen_verwalten():
    if request.form.get("aktion") == "preise":
        neu, fehler = {}, []
        for key in [*oneclick.optionen(), oneclick.ORIGINAL]:
            wert = request.form.get(f"preis_{key}", "").strip()
            if wert:
                try:
                    neu[key] = cent_aus(wert)
                except ValueError as e:
                    fehler.append(f"{option_namen()[key]}: {e}")
        if fehler:
            for f in fehler:
                flash(f"Nicht gespeichert – {f}")
        else:
            speichere_config({"preise": neu})
            flash("Preise gespeichert.")
        return redirect(url_for("admin_archiv") + "#preise")
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
        meldungen = importiere_zip(datei.stream, request.form.get("sortieren") == "1", datei.filename)
    except zipfile.BadZipFile:
        meldungen = ["Die Datei ist keine gültige ZIP-Datei."]
    for m in meldungen[:30]:
        flash(m)
    if len(meldungen) > 30:
        flash(f"… und {len(meldungen) - 30} weitere Meldungen.")
    return redirect(url_for("sortieren") if eingang_anzahl() else url_for("admin_archiv"))


@app.route("/admin/sortieren")
@admin_noetig
def sortieren():
    stapel, ausgeblendet = [], 0
    for s in alle_stapel():
        ausgeblendet += sum(1 for d in s["dateien"] if not sichtbar(d))
        gids = sorted({d["gruppe"] for d in s["dateien"] if sichtbar(d)})
        if not gids:
            continue
        gruppen = [gruppe_auswerten(s, gid) for gid in gids]
        for g in gruppen:
            plan = auto_plan(g)
            g["auto"] = plan if isinstance(plan, str) else "kann automatisch übernommen werden"
        stapel.append({**s, "gruppen": gruppen, "sichtbar": sum(1 for d in s["dateien"] if sichtbar(d))})
    return render_template("sortieren.html", stapel=stapel, ausgeblendet=ausgeblendet, archiv_optionen=oneclick.optionen(),
                           archiv_namen=[e["name"] for e in oneclick.lade_index()["eintraege"]])


@app.route("/admin/sortieren/abgas-loeschen", methods=["POST"])
@admin_noetig
def abgas_loeschen():
    """Die ausgeblendeten Abgas-Files endgueltig loeschen (nur auf Knopfdruck)."""
    weg = 0
    with eingang_sperre:
        for s in alle_stapel():
            raus = [d for d in s["dateien"] if not sichtbar(d)]
            for d in raus:
                (EINGANG / s["id"] / f"{d['id']}.bin").unlink(missing_ok=True)
            if raus:
                s["dateien"] = [d for d in s["dateien"] if sichtbar(d)]
                stapel_sichern(s)
                weg += len(raus)
    flash(f"{weg} ausgeblendete Datei(en) gelöscht.")
    return redirect(url_for("sortieren"))


@app.route("/admin/sortieren/automatisch", methods=["POST"])
@admin_noetig
def sortieren_automatisch():
    """Alle Gruppen uebernehmen, die sich ohne Raten zuordnen lassen. Der Rest bleibt fuer den Admin."""
    gruppen = fahrzeuge = 0
    offen = {}
    for s in alle_stapel():
        for gid in sorted({d["gruppe"] for d in s["dateien"] if sichtbar(d)}):
            try:
                stapel = lade_stapel(s["id"])
            except Exception:
                continue
            if not any(d["gruppe"] == gid for d in stapel["dateien"]):
                continue
            g = gruppe_auswerten(stapel, gid)
            plan = auto_plan(g)
            if isinstance(plan, str):
                offen[plan] = offen.get(plan, 0) + 1
                continue
            rollen, name, namen_ori = plan
            ori_id = next((f for f, r in rollen.items() if r == oneclick.ORIGINAL), None)
            ori = (EINGANG / s["id"] / f"{ori_id}.bin").read_bytes() if ori_id else None
            if ori_id:
                namen_ori[ori_id] = freier_archivname(sicherer_name(name), ori)
            try:
                meldungen = gruppe_uebernehmen(s["id"], gid, name, rollen, namen_ori, index=False)
                gruppen += 1
                fahrzeuge += sum(1 for m in meldungen if "angelegt" in m or "ergänzt" in m)
            except Abgelehnt as e:
                offen[f"Prüfung: {e}"[:90]] = offen.get(f"Prüfung: {e}"[:90], 0) + 1
    with index_sperre:
        oneclick.baue_index()
    flash(f"Automatisch erledigt: {gruppen} Gruppe(n), {fahrzeuge} Fahrzeug(e) neu angelegt oder ergänzt "
          "(Gruppen nur mit schon vorhandenen Files wurden aufgeräumt).")
    if offen:
        flash(f"{sum(offen.values())} Gruppe(n) brauchen dich: " +
              ", ".join(f"{n}× {grund}" for grund, n in sorted(offen.items(), key=lambda x: -x[1])) + ".")
    return redirect(url_for("sortieren"))


@app.route("/admin/sortieren/<sid>/<int:gid>", methods=["POST"])
@admin_noetig
def sortieren_gruppe(sid, gid):
    aktion = request.form.get("aktion", "")
    anker = url_for("sortieren")
    if aktion == "uebernehmen":
        rollen = {k[6:]: v for k, v in request.form.items() if k.startswith("rolle_")}
        namen_ori = {k[5:]: v for k, v in request.form.items() if k.startswith("name_")}
        zu = {k[3:]: v for k, v in request.form.items() if k.startswith("zu_") and v}
        try:
            for m in gruppe_uebernehmen(sid, gid, request.form.get("name", ""), rollen, namen_ori, zu=zu):
                flash(m)
        except Abgelehnt as e:
            flash(f"Gruppe {gid}: {e}")
            anker += f"#g-{sid}-{gid}"
    elif aktion in ("verschieben", "verwerfen"):
        with eingang_sperre:
            stapel = lade_stapel(sid)
            if aktion == "verwerfen":
                weg = {d["id"] for d in stapel["dateien"] if d["gruppe"] == gid}
                stapel["dateien"] = [d for d in stapel["dateien"] if d["id"] not in weg]
                for f in weg:
                    (EINGANG / sid / f"{f}.bin").unlink(missing_ok=True)
                flash(f"Gruppe {gid} verworfen ({len(weg)} Datei(en) gelöscht).")
            else:
                neue = max((d["gruppe"] for d in stapel["dateien"]), default=0) + 1
                for d in stapel["dateien"]:
                    ziel = request.form.get(f"ziel_{d['id']}", "")
                    if d["gruppe"] == gid and ziel and ziel != str(gid):
                        d["gruppe"] = neue if ziel == "neu" else int(ziel) if ziel.isdigit() else d["gruppe"]
                anker += f"#g-{sid}-{gid}"
            stapel_sichern(stapel)
    return redirect(anker)


@app.route("/admin/sortieren/<sid>/datei/<fid>")
@admin_noetig
def sortieren_datei(sid, fid):
    stapel = lade_stapel(sid)
    d = next((d for d in stapel["dateien"] if d["id"] == fid), None)
    if d is None:
        abort(404)
    return send_file(EINGANG / sid / f"{fid}.bin", as_attachment=True, download_name=d["name"])


@app.route("/admin/sortieren/<sid>/verwerfen", methods=["POST"])
@admin_noetig
def stapel_verwerfen(sid):
    lade_stapel(sid)
    shutil.rmtree(EINGANG / sid, ignore_errors=True)
    flash("Stapel verworfen, alle Dateien darin gelöscht.")
    return redirect(url_for("sortieren"))


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
                "agb": request.form.get("agb", "").strip()[:50000],
                "widerruf": request.form.get("widerruf", "").strip()[:20000],
                "haftung": request.form.get("haftung", "").strip()[:20000],
                "datenschutz": request.form.get("datenschutz", "").strip()[:50000],
                "basis_url": request.form.get("basis_url", "").strip(),
                "telegram_token": request.form.get("telegram_token", "").strip(),
                "telegram_chat_id": request.form.get("telegram_chat_id", "").strip(),
                "aufbewahrung_tage": tage,
                "nur_identisch": request.form.get("nur_identisch") == "1",
                "support_whatsapp": re.sub(r"[^0-9]", "", request.form.get("support_whatsapp", ""))[:20],
            })
            flash("Gespeichert.")
        elif aktion == "stripe":
            aenderung = {}
            schluessel = request.form.get("stripe_key", "").strip()
            geheim = request.form.get("stripe_webhook_secret", "").strip()
            if schluessel and not schluessel.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
                flash("Der Stripe-Schlüssel muss mit sk_live_ oder sk_test_ (bzw. rk_…) anfangen.")
            elif geheim and not geheim.startswith("whsec_"):
                flash("Das Webhook-Geheimnis muss mit whsec_ anfangen.")
            else:
                if schluessel:
                    aenderung["stripe_key"] = schluessel
                if geheim:
                    aenderung["stripe_webhook_secret"] = geheim
                speichere_config(aenderung)
                flash("Stripe gespeichert. Jetzt „Stripe testen“ drücken." if aenderung else "Nichts geändert.")
        elif aktion == "stripe_test":
            try:
                stripe_anfrage("GET", "/balance")
                modus = "TESTMODUS (keine echten Zahlungen)" if "_test_" in lade_config().get("stripe_key", "") else "LIVE"
                flash(f"Verbindung zu Stripe klappt – {modus}.")
            except RuntimeError as e:
                flash(f"Stripe-Test fehlgeschlagen: {e}")
        elif aktion == "stripe_aus":
            cfg = lade_config()
            cfg.pop("stripe_key", None)
            cfg.pop("stripe_webhook_secret", None)
            json_speichern(CONFIG_DATEI, cfg)
            flash("Stripe entfernt – Bezahlen ist aus, Downloads sind wieder ohne Zahlung möglich.")
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
    return render_template("einstellungen.html", cfg=lade_config(), chats=dict(telegram_chats), standard_whatsapp=STANDARD_WHATSAPP,
                           rechtliches=RECHTLICHES,
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
--ok:#30d158;--warn:#ffd60a;--blau:#0a84ff;--verlauf:linear-gradient(135deg,var(--akzent),var(--akzent2));--breite:1100px}
@media (min-width:1500px){:root{--breite:1280px}}
@media (min-width:1900px){:root{--breite:1480px}}
@media (min-width:2200px){html{zoom:1.3}}
@media (min-width:2500px){html{zoom:1.45}}
@media (min-width:3000px){html{zoom:1.6}}
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
padding:12px max(16px,calc((100% - var(--breite))/2));background:rgba(0,0,0,.6);
-webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid var(--rand)}
.logo{font-weight:700;font-size:19px;letter-spacing:-.02em}
.logo span{background:var(--verlauf);-webkit-background-clip:text;background-clip:text;color:transparent}
nav{display:flex;flex-wrap:wrap;gap:4px 20px}nav a{color:var(--leise);text-decoration:none;font-size:13.5px;transition:color .2s}nav a:hover{color:var(--text)}
main{max-width:calc(var(--breite) + 32px);margin:0 auto;padding:36px 16px}
.karte{background:var(--glas);border:1px solid var(--rand);border-radius:22px;padding:28px;margin-bottom:22px;
-webkit-backdrop-filter:blur(30px);backdrop-filter:blur(30px);box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 20px 60px rgba(0,0,0,.35)}
h1{font-size:30px;line-height:1.15;font-weight:700;letter-spacing:-.03em;margin:0 0 18px;overflow-wrap:anywhere}
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
tr>th:first-child+td{white-space:normal;overflow-wrap:anywhere}
/* Listen: lange Dateinamen umbrechen statt die Knoepfe aus dem Bild zu schieben */
.liste-tab td{white-space:normal}
.liste-tab td a{overflow-wrap:anywhere;word-break:break-word}
.liste-tab td:first-child,.liste-tab td:last-child,.liste-tab .status{white-space:nowrap}
td a{overflow-wrap:anywhere}
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
footer{max-width:calc(var(--breite) + 32px);margin:0 auto;padding:10px 16px 40px;font-size:12.5px;color:#6e6e73}
footer{display:flex;flex-wrap:wrap;gap:6px 18px}footer a{color:#6e6e73;text-decoration:none}footer a:hover{color:var(--text)}
@media (max-width:600px){.karte{padding:20px;border-radius:18px}main{padding:22px 14px}h1{font-size:25px}.hero{padding:16px 0 20px}}
/* Handy: Menue in einer Zeile (wischbar), Kacheln 2x2, Listen als Karten mit Beschriftung */
@media (max-width:720px){
header{flex-direction:column;align-items:stretch;gap:6px;padding:10px 14px}
header>*{min-width:0;max-width:100%}
nav{flex-wrap:nowrap;overflow-x:auto;gap:14px;padding-bottom:2px;scrollbar-width:none}nav::-webkit-scrollbar{display:none}
nav a{white-space:nowrap;font-size:13.5px;padding:4px 0}
.raster{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.raster .karte{padding:16px;margin:0}.zahl{font-size:32px}
.liste-tab,.liste-tab tbody,.liste-tab tr,.liste-tab td{display:block;width:100%}
.liste-tab tr:first-child{display:none}
.liste-tab tr{border:1px solid var(--rand);border-radius:14px;padding:6px 12px;margin-bottom:10px;background:rgba(255,255,255,.025)}
.liste-tab td{display:flex;justify-content:space-between;align-items:center;gap:14px;white-space:normal;text-align:right;
padding:8px 0;border-bottom:1px solid var(--rand);overflow-wrap:anywhere}
.liste-tab tr td:last-child{border-bottom:0}
.liste-tab td::before{content:attr(data-label);flex:none;color:var(--leise);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;text-align:left}
.liste-tab td[data-label=""]::before{display:none}
.liste-tab td .status,.liste-tab td .btn{flex:none;white-space:nowrap}
.liste-tab td:has(.rollen){display:block;text-align:left}
.liste-tab td:has(.rollen)::before{display:block;margin-bottom:8px}
.rollen{max-width:none!important}
.liste-tab td[data-label=""]{justify-content:flex-end;flex-wrap:wrap}
.tabelle{overflow:visible}
table:not(.liste-tab) th{white-space:normal;padding-left:0}
}
</style></head><body>
<header><div class="logo">{% set w = firma.split(' ', 1) %}<span>{{ w[0] }}</span>{% if w|length > 1 %} {{ w[1] }}{% endif %}</div>
<nav>{% if session.admin %}<a href="{{ url_for('start') }}">Startseite</a>
<a href="{{ url_for('admin') }}">Aufträge</a>
<a href="{{ url_for('admin_archiv') }}">Archiv</a>
<a href="{{ url_for('eigenes_file') }}">Eigenes File</a>
{% if zu_sortieren %}<a href="{{ url_for('sortieren') }}">Sortieren ({{ zu_sortieren }})</a>{% endif %}
<a href="{{ url_for('einstellungen') }}">Einstellungen</a>
<a href="{{ url_for('logout') }}">Abmelden</a>{% endif %}</nav></header>
<main>
{% for m in get_flashed_messages() %}<div class="meldung">{{ m }}</div>{% endfor %}
{% block inhalt %}{% endblock %}
</main>
<footer><a href="{{ url_for('impressum') }}">Impressum</a><a href="{{ url_for('datenschutz') }}">Datenschutz</a><a href="{{ url_for('agb') }}">AGB</a><a href="{{ url_for('widerruf') }}">Widerruf</a><a href="{{ url_for('haftung') }}">Haftung</a></footer>
<script>
// Tabellen mit Kopfzeile = Listen: am Handy als Karten, jede Zelle bekommt ihre Spaltenueberschrift
document.querySelectorAll('table').forEach(function(t){
  var kopf=t.rows[0]; if(!kopf||kopf.cells.length<2) return;
  for(var i=0;i<kopf.cells.length;i++) if(kopf.cells[i].tagName!=='TH') return;
  t.classList.add('liste-tab');
  for(var r=1;r<t.rows.length;r++) for(var c=0;c<t.rows[r].cells.length;c++)
    t.rows[r].cells[c].setAttribute('data-label',(kopf.cells[c]||{}).textContent||'');
});
</script>
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
{% if text %}<div class="rechtstext" style="white-space:pre-line">{{ text|rechtstext }}</div>
<style>.rechtstext h3{font-size:17px;margin:14px 0 2px;white-space:normal}.rechtstext a{overflow-wrap:anywhere}</style>
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
<table><tr><th>Auftrags-Nr.</th><td><code>{{ a.id[:8] }}</code> <span class="leise">(steht in WhatsApp-Nachrichten des Kunden)</span></td></tr>
{% if a.typ == 'anfrage' %}{% for feld, titel, _ in fahrzeug_felder %}<tr><th>{{ titel }}</th><td>{{ a.fahrzeug.get(feld) or '–' }}</td></tr>{% endfor %}
<tr><th>Gewünscht</th><td><b>{{ optionen[a.option] }}</b></td></tr>
{% if a.nachricht %}<tr><th>Nachricht</th><td style="white-space:pre-wrap">{{ a.nachricht }}</td></tr>{% endif %}{% endif %}
<tr><th>ECU</th><td>{{ a.ecu }}</td></tr><tr><th>Software</th><td>{{ a.software }}</td></tr>
<tr><th>Kontakt</th><td>{{ a.kunde }}</td></tr>
{% if a.art and a.typ != 'anfrage' %}<tr><th>Treffer</th><td>{% if a.art == 'softwarenummer' %}<span class="status s-WARTET">Prüfen</span>{% else %}<span class="status a-AUTOMATISCH">100 %</span>{% endif %} {{ art_text.get(a.art, a.art) }}</td></tr>{% endif %}
{% if a.typ != 'anfrage' %}<tr><th>Quelle</th><td>{{ a.quelle or '–' }}</td></tr>{% endif %}
{% if zahlung or a.bezahlt %}<tr><th>Preis</th><td>{{ euro(a.preis or 0) if a.preis else 'kostenlos' }}</td></tr>
<tr><th>Zahlung</th><td>{% if a.bezahlt %}<span class="status s-FREIGEGEBEN">bezahlt</span> {{ euro(a.betrag or 0) }} am {{ a.bezahlt_am[:16].replace('T',' ') }}
{% if a.zahlung_id %}<a class="leise" href="https://dashboard.stripe.com/{{ 'test/' if '_test_' in (stripe_key or '') }}payments/{{ a.zahlung_id }}" target="_blank" rel="noopener">bei Stripe ansehen</a>{% endif %}
{% elif a.status == 'FREIGEGEBEN' and a.preis %}<span class="status s-WARTET">offen</span> – der Kunde kann jetzt bezahlen
{% elif a.status == 'WARTET' and a.preis %}<span class="leise">nach der Freigabe</span>{% else %}–{% endif %}</td></tr>{% endif %}
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
{% if zahlung %}<label class="feld" style="margin-top:12px">Preis in € (bezahlt der Kunde, bevor er herunterladen kann)</label>
<input type="text" name="preis" inputmode="decimal" value="{{ ((a.preis or 0) / 100)|round(2)|string|replace('.', ',') }}">{% endif %}
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
<form method="post" action="{{ url_for('admin_entscheiden', aid=a.id) }}" class="inline" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="ok">
{% if zahlung %}<label class="leise" style="display:flex;gap:8px;align-items:center;font-size:14px">Preis
<input type="text" name="preis" inputmode="decimal" value="{{ ((a.preis or 0) / 100)|round(2)|string|replace('.', ',') }}" style="width:110px;margin:0"> €</label>{% endif %}
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
{% if zahlung %}<label class="feld">Preis in € für diesen Auftrag</label>
<input type="text" name="preis" inputmode="decimal" value="{{ ((a.preis or 0) / 100)|round(2)|string|replace('.', ',') }}">{% endif %}
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
{% if zahlung %}<div class="karte"><div class="leise">Bezahlt (gesamt)</div><div class="zahl" style="font-size:32px">{{ euro(bezahlt) }}</div></div>{% endif %}
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
<form method="get" action="{{ url_for('auftrag_suche') }}" style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
<input type="text" name="q" placeholder="Auftrags-Nr. aus WhatsApp, z. B. 3f9a1c2e" style="flex:1;min-width:200px;margin:0" autocomplete="off">
<button class="btn grau">Suchen</button></form>
<div class="tabelle"><table><tr><th>Datum</th><th>Kontakt</th><th>Datei</th><th>Option</th><th>Quelle</th><th>Status</th>{% if zahlung %}<th>Zahlung</th>{% endif %}</tr>
{% for a in alle %}<tr><td>{{ a.zeit[:16].replace('T',' ') }}</td><td>{{ a.kunde }}</td>
<td><a href="{{ url_for('auftrag_ansicht', aid=a.id) }}">{{ a.datei }}</a></td><td>{{ optionen[a.option] }}</td>
<td class="leise">{% if a.typ == 'anfrage' %}📩 Anfrage{% else %}{{ a.quelle or '–' }}{% endif %}</td>
<td><span class="status s-{{ a.status }}">{{ status_text[a.status] }}</span></td>
{% if zahlung %}<td>{% if a.bezahlt %}<span class="status s-FREIGEGEBEN">{{ euro(a.betrag or 0) }} ✓</span>
{% elif a.preis and a.status == 'FREIGEGEBEN' %}<span class="status s-WARTET">{{ euro(a.preis) }} offen</span>
{% elif a.preis and a.status == 'WARTET' %}<span class="leise">{{ euro(a.preis) }}</span>{% else %}–{% endif %}</td>{% endif %}</tr>
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
{% if zu_sortieren %}<div class="karte" style="border-color:rgba(255,214,10,.4)"><h2>{{ zu_sortieren }} Datei(en) warten aufs Sortieren</h2>
<p class="leise" style="margin-top:-6px">Lege fest, was Original, Stage 1 usw. ist – dann kommen sie ins Archiv.</p>
<a class="btn" href="{{ url_for('sortieren') }}">Jetzt sortieren</a></div>{% endif %}
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
<label style="display:flex;gap:10px;align-items:flex-start;margin-top:16px;cursor:pointer">
<input type="checkbox" name="sortieren" value="1" style="margin-top:3px">
<span><b>Alle Dateien selbst zuordnen</b><br><span class="leise" style="font-size:13px">Für ZIPs mit losen Dateien ohne Ordner und ohne
„ori“/„stage1“ im Namen: Die Seite sortiert ähnliche Files in Gruppen, du legst unter „Sortieren“ fest, was Original, Stage 1 usw. ist.</span></span></label>
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
<form method="post" action="{{ url_for('loesungen_verwalten') }}" id="preise" style="margin-top:22px">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="preise">
<h2 style="margin-top:8px">Preise</h2>
{% if not zahlung %}<p class="leise" style="margin-top:-6px">Bezahlen ist noch aus. Erst unter Einstellungen → Stripe den Schlüssel eintragen,
dann gelten diese Preise.</p>{% endif %}
<div class="dateien">
{% for key, titel in archiv_optionen.items() %}<label class="datei" style="cursor:default"><span>{{ titel }}</span>
<input type="text" name="preis_{{ key }}" inputmode="decimal" placeholder="Preis in €" value="{{ (preise[key] / 100)|round(2)|string|replace('.', ',') if key in preise else '' }}" style="margin:0">
{% if zahlung and key not in preise %}<span class="status s-ABGELEHNT" style="align-self:flex-start">kein Preis = kostenlos</span>{% endif %}</label>{% endfor %}
<label class="datei" style="cursor:default"><span>{{ optionen[original] }}</span>
<input type="text" name="preis_{{ original }}" inputmode="decimal" placeholder="Preis in €" value="{{ (preise[original] / 100)|round(2)|string|replace('.', ',') if original in preise else '' }}" style="margin:0">
{% if zahlung and original not in preise %}<span class="status s-ABGELEHNT" style="align-self:flex-start">kein Preis = kostenlos</span>{% endif %}</label>
</div>
<button class="btn">Preise speichern</button>
<div class="hinweis">Bei mehreren Lösungen werden die Preise addiert. Bezahlt wird erst nach deiner Freigabe.
Für einzelne Aufträge kannst du den Preis beim Freigeben ändern.</div></form>
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

"eigenes.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>Eigenes File</h1>
<p class="leise">Für dich selbst: File hochladen, passende Lösung aus dem Archiv wählen und kostenlos herunterladen.
Es wird kein Auftrag angelegt, nichts bezahlt und keine Nachricht verschickt.</p>
<form method="post" action="{{ url_for('eigenes_file') }}" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
<label class="drop"><input type="file" name="datei" required onchange="this.form.submit()">
<div><b>File hierher ziehen</b><br>oder klicken zum Auswählen</div></label>
</form></div>
{% if e %}<div class="karte"><h2 style="overflow-wrap:anywhere">{{ e.datei }}</h2>
<p class="leise" style="margin-top:-6px">ECU: {{ e.ecu }} · Software: {{ e.software }}</p>
{% if e.angebot %}<form method="post" action="{{ url_for('eigenes_file_download', eid=e.id) }}">
<input type="hidden" name="csrf" value="{{ session.csrf }}">
{% for opt, a in e.angebot.items() %}<label style="display:flex;gap:10px;align-items:flex-start;margin:10px 0;cursor:pointer">
<input type="checkbox" name="option" value="{{ opt }}" style="margin-top:3px"{{ ' checked' if loop.length == 1 }}>
<span><b>{{ namen[opt] }}</b><br><span class="leise" style="font-size:13px;overflow-wrap:anywhere">aus {{ a.quelle }} · {{ a.art }}</span></span></label>{% endfor %}
<button class="btn">Kostenlos herunterladen</button>
<div class="hinweis">Mehrere Häkchen = Lösungen werden in einem File kombiniert (wie beim Kunden). Das File bleibt 24 Stunden hier.</div>
</form>{% else %}<p>Für dieses File gibt es im Archiv noch keine passende Lösung.</p>{% endif %}
</div>{% endif %}
{% endblock %}""",
"sortieren.html": """{% extends "basis.html" %}{% block inhalt %}
<div class="karte"><h1>Sortieren</h1>
<p class="leise" style="margin-top:-6px">Ähnliche Files (gleiche Größe, weitgehend gleicher Inhalt) sind schon zu Gruppen zusammengefasst –
meist ein Fahrzeug pro Gruppe. Wähle pro Datei, was sie ist, gib dem Fahrzeug einen Namen und übernimm es ins Archiv.
„Abweichung“ zeigt, wie viel sich eine Datei vom vorgeschlagenen Original unterscheidet (Tuning-Files meist unter 20 %, fremde Files fast 100 %).</p>
{% if ausgeblendet %}<p class="meldung" style="margin:0 0 14px">{{ ausgeblendet }} Datei(en) mit Abschaltung der Abgasreinigung im Namen
(DPF, AdBlue, EGR, NOx, Lambda …) sind ausgeblendet – sie werden nicht übernommen und liegen nur noch auf dem Server.
<form method="post" action="{{ url_for('abgas_loeschen') }}" class="inline" onsubmit="return confirm('Diese ausgeblendeten Dateien endgültig löschen?')">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><button class="btn grau klein" style="margin-left:6px">Endgültig löschen</button></form></p>{% endif %}
{% if not stapel %}<p>Gerade gibt es nichts zu sortieren. Neue Dateien kommen über Archiv → ZIP-Import.</p>
{% else %}<form method="post" action="{{ url_for('sortieren_automatisch') }}" style="margin-top:14px"
 onsubmit="var b=this.querySelector('button');b.textContent='Läuft … (bei vielen Dateien bis zu ein paar Minuten)';b.disabled=true">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><button class="btn gruen">Automatisch zuordnen</button></form>
<p class="hinweis">Übernimmt alle Gruppen, bei denen nichts geraten werden muss: Original schon im Archiv, „ori“ im Namen oder eindeutig
am Inhalt erkennbar – und die Lösung steht im Dateinamen (z. B. stage1, pops, vmax, eigene Lösungen). Dateien, die schon im Archiv sind,
werden aufgeräumt. Alles andere bleibt hier stehen, mit dem Grund dazu.</p>{% endif %}</div>
{% for s in stapel %}
<div class="karte" style="padding-bottom:12px"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
<h2 style="margin:0">{{ s.quelle }} <span class="leise" style="font-weight:400;font-size:14px">· {{ s.zeit[:16].replace('T', ' ') }} · {{ s.sichtbar }} Dateien in {{ s.gruppen|length }} Gruppen</span></h2>
<form method="post" action="{{ url_for('stapel_verwerfen', sid=s.id) }}" class="inline" onsubmit="return confirm('Alle Dateien dieses Stapels löschen?')">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><button class="btn grau klein">Ganzen Stapel verwerfen</button></form></div></div>
{% for g in s.gruppen %}
<div class="karte" id="g-{{ s.id }}-{{ g.id }}">
<form method="post" action="{{ url_for('sortieren_gruppe', sid=s.id, gid=g.id) }}">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="uebernehmen">
<h2>Gruppe {{ g.id }} {% if g.auto.startswith('kann') %}<span class="status s-FREIGEGEBEN" style="font-size:12px;vertical-align:3px">automatisch möglich</span>
{% else %}<span class="status s-WARTET" style="font-size:12px;vertical-align:3px" title="Warum nicht automatisch">{{ g.auto }}</span>{% endif %}
<span class="leise" style="font-weight:400;font-size:14px">· {{ g.dateien|rejectattr('abgas')|list|length }} Datei(en) · {{ (g.groesse / 1024)|round|int }} KB · ECU {{ g.ecu }} · Software {{ g.software }}</span></h2>
{% if g.archiv %}<p class="meldung" style="margin-top:0">Passt zum Archiv-Eintrag <b>{{ g.archiv }}</b>. Ohne eigenes Original in der Gruppe
werden die Tuning-Files dort ergänzt.</p>{% endif %}
<label class="feld">Name, wenn kein Original in der Gruppe ist (dann werden die Tuning-Files bei diesem Archiv-Eintrag ergänzt)</label>
<input type="text" name="name" value="{{ g.name }}" list="archivnamen" autocomplete="off">
<p class="hinweis" style="margin-top:-4px">Pro Datei auswählen, was sie ist – <b>auch mehreres</b> (z. B. Stage 1 + Pops &amp; Bangs in einem File).
Sind es <b>mehrere Autos</b>: jedes Original als „Original“ markieren und benennen. Bei den Tuning-Files erscheint dann
„gehört zu“ – dort das richtige Original wählen (oder auf „automatisch“ lassen, dann nimmt die Seite das ähnlichste).</p>
<div class="tabelle"><table><tr><th>Datei</th><th>ECU / Software</th><th>Abweichung</th><th>Was ist das?</th><th>Gruppe</th></tr>
{% for d in g.dateien if not d.abgas %}<tr><td><a href="{{ url_for('sortieren_datei', sid=s.id, fid=d.id) }}" title="Zum Prüfen herunterladen">{{ d.name }}</a>
{% if d.bekannt %}<br><span class="status s-ENTWURF">schon im Archiv: {{ d.bekannt }}</span>{% endif %}
{% if d.abgas %}<br><span class="status s-ABGELEHNT">Abgasreinigung – wird nicht übernommen</span>{% endif %}</td>
<td class="leise">{{ d.ecu }}<br>{{ d.software }}</td>
<td>{% if d.abweichung is none %}{% if d.vorschlag == original %}<span class="status s-FREIGEGEBEN">Original?</span>{% else %}–{% endif %}{% else %}{{ d.abweichung|string|replace('.', ',') }} %{% endif %}</td>
<td>{% if d.abgas %}<input type="hidden" name="rolle_{{ d.id }}" value="ignorieren"><span class="leise">Ignoriert</span>
{% else %}<div class="rollen" data-feld="rolle_{{ d.id }}">
<input type="hidden" name="rolle_{{ d.id }}" value="{{ d.vorschlag }}">
<button type="button" class="chip ori" data-w="{{ original }}">Original</button>
{% for key, titel in archiv_optionen.items() %}<button type="button" class="chip" data-w="{{ key }}">{{ titel }}</button>{% endfor %}
<button type="button" class="chip weg" data-w="ignorieren">Ignorieren</button>
<input type="text" class="ori-name" name="name_{{ d.id }}" placeholder="Name dieses Fahrzeugs"
 value="{{ g.name if d.vorschlag == original else d.name_vorschlag }}" autocomplete="off" list="archivnamen">
<label class="zu-wahl">gehört zu <select name="zu_{{ d.id }}" class="zu" data-datei="{{ d.name }}"><option value="">automatisch (ähnlichstes Original)</option></select></label></div>{% endif %}</td>
<td><select name="ziel_{{ d.id }}" class="ziel" title="In eine andere Gruppe verschieben">
{% for g2 in s.gruppen %}<option value="{{ g2.id }}" {{ 'selected' if g2.id == g.id }}>{{ g2.id }}</option>{% endfor %}<option value="neu">neue Gruppe</option></select></td></tr>
{% endfor %}</table></div>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
<button class="btn">Ins Archiv übernehmen</button>
<button class="btn grau" name="aktion" value="verwerfen" onclick="return confirm('Diese Gruppe löschen? Die Dateien werden nicht übernommen.')">Gruppe verwerfen</button></div>
</form></div>
{% endfor %}{% endfor %}
<datalist id="archivnamen">{% for n in archiv_namen %}<option value="{{ n }}">{% endfor %}</datalist>
<style>select{font:inherit;color:var(--text);background:rgba(255,255,255,.06);border:1px solid var(--rand);border-radius:10px;padding:8px 10px;max-width:100%}
select option{background:#1c1c1e}
.rollen{display:flex;flex-wrap:wrap;gap:6px;max-width:520px}
.rollen .chip{font:inherit;font-size:12.5px;font-weight:600;padding:5px 11px;border-radius:99px;cursor:pointer;color:var(--leise);
background:rgba(255,255,255,.05);border:1px solid var(--rand2);transition:all .15s}
.rollen .chip:hover{color:var(--text);border-color:var(--leise)}
.rollen .chip.an{color:#fff;background:var(--verlauf);border-color:transparent}
.rollen .chip.ori.an{background:linear-gradient(135deg,#30d158,#0fb5a3)}
.rollen .chip.weg.an{background:#48484a}
.rollen .ori-name{display:none;margin:4px 0 0;flex-basis:100%;padding:8px 12px;font-size:14px}
.rollen.ist-ori .ori-name{display:block}
.rollen .zu-wahl{display:none;flex-basis:100%;margin-top:4px;font-size:13px;color:var(--leise);align-items:center;gap:8px}
.rollen.zeige-zu .zu-wahl{display:flex}
.rollen .zu-wahl select{flex:1;min-width:0;font-size:13px;padding:6px 8px}
td:has(.rollen){white-space:normal}</style>
<script>
// Gruppe aendern = sofort verschieben
document.querySelectorAll('select.ziel').forEach(function(s){s.addEventListener('change',function(){
  var f=s.form; f.querySelector('input[name=aktion]').value='verschieben'; f.submit();});});
// Auswahl pro Datei: Original ODER Ignorieren ODER eine/mehrere Loesungen (z. B. Stage 1 + Pops & Bangs)
document.querySelectorAll('.rollen').forEach(function(box){
  var feld=box.querySelector('input[type=hidden]'), chips=box.querySelectorAll('.chip');
  function malen(){
    var werte=feld.value?feld.value.split(','):[];
    chips.forEach(function(c){c.classList.toggle('an',werte.indexOf(c.dataset.w)>=0);});
    box.classList.toggle('ist-ori',werte[0]==='{{ original }}');
  }
  chips.forEach(function(c){c.addEventListener('click',function(){
    var w=c.dataset.w, werte=feld.value?feld.value.split(','):[];
    if(w==='{{ original }}'||w==='ignorieren') werte=(werte.length===1&&werte[0]===w)?[]:[w];
    else{
      werte=werte.filter(function(x){return x!=='{{ original }}'&&x!=='ignorieren';});
      var i=werte.indexOf(w); if(i>=0) werte.splice(i,1); else werte.push(w);
    }
    feld.value=werte.join(','); malen(); zuAuffrischen(box.closest('form'));
  });});
  malen();
});
// "gehört zu": bei 2+ Originalen in einer Gruppe kann jedes Tuning-File seinem Original zugewiesen werden
function zuAuffrischen(form){
  var boxen=[].slice.call(form.querySelectorAll('.rollen'));
  var oris=boxen.filter(function(b){return b.classList.contains('ist-ori');}).map(function(b){
    var fid=b.dataset.feld.slice(6), n=b.querySelector('.ori-name');
    return {fid:fid, name:(n&&n.value)||fid};});
  boxen.forEach(function(b){
    var feld=b.querySelector('input[type=hidden]'), sel=b.querySelector('select.zu');
    if(!sel) return;
    var tuning=feld.value && feld.value!=='{{ original }}' && feld.value!=='ignorieren';
    b.classList.toggle('zeige-zu', tuning && oris.length>=2);
    var alt=sel.value; sel.length=1;
    oris.forEach(function(o){var op=document.createElement('option');op.value=o.fid;op.textContent=o.name;sel.appendChild(op);});
    sel.value=oris.some(function(o){return o.fid===alt;})?alt:'';
  });
}
document.querySelectorAll('form[action*="/admin/sortieren/"]').forEach(function(f){
  if(!f.querySelector('.rollen')) return;
  zuAuffrischen(f);
  f.querySelectorAll('.ori-name').forEach(function(i){i.addEventListener('input',function(){zuAuffrischen(f);});});
});
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
<label class="feld">WhatsApp-Nummer für Kunden mit Problemen nach dem Download (mit Ländervorwahl, z. B. 4915568540674; leer = Knopf aus)</label>
<input type="text" name="support_whatsapp" inputmode="numeric" value="{{ cfg.get('support_whatsapp', standard_whatsapp) }}" placeholder="4915568540674">
<label class="feld">Erledigte Kundenaufträge automatisch löschen nach … Tagen (0 = nie). Das Archiv bleibt immer erhalten.</label>
<input type="number" name="aufbewahrung_tage" min="0" value="{{ cfg.get('aufbewahrung_tage', 90) }}">
<label style="display:flex;gap:10px;align-items:flex-start;margin:4px 0 16px;cursor:pointer">
<input type="checkbox" name="nur_identisch" value="1" {{ 'checked' if cfg.nur_identisch }} style="margin-top:4px">
<span><b>Nur komplett identische Originale</b><br><span class="leise" style="font-size:13px">Aus: Treffer auch, wenn das File an allen Stellen,
die euer Tuning ändert, exakt gleich ist (z. B. andere Fahrgestellnummer). An: nur wenn das ganze File Byte für Byte gleich ist.</span></span></label>
<div class="hinweis" style="margin:4px 0 12px"><b>Rechtstexte:</b> Feld leer lassen = mitgelieferter Standardtext (passt zu dieser Seite
und wird bei Updates aktuell gehalten). Nur ausfüllen, wenn du einen eigenen Text (z. B. vom Anwalt) verwenden willst.
Ansehen: {% for art, titel in rechtliches.items() %}<a href="{{ url_for(art) }}" target="_blank">{{ titel }}</a>{{ ' · ' if not loop.last }}{% endfor %}</div>
<label class="feld">Impressum</label>
<textarea name="impressum" placeholder="leer = Standardtext">{{ cfg.impressum or '' }}</textarea>
<label class="feld">Datenschutzerklärung</label>
<textarea name="datenschutz" placeholder="leer = Standardtext">{{ cfg.datenschutz or '' }}</textarea>
<label class="feld">AGB</label>
<textarea name="agb" placeholder="leer = Standardtext">{{ cfg.agb or '' }}</textarea>
<label class="feld">Widerrufsbelehrung (mit Muster-Widerrufsformular)</label>
<textarea name="widerruf" placeholder="leer = Standardtext">{{ cfg.widerruf or '' }}</textarea>
<label class="feld">Hinweise zu Einsatz und Haftung</label>
<textarea name="haftung" placeholder="leer = Standardtext">{{ cfg.haftung or '' }}</textarea>
<button class="btn">Speichern</button></form></div>

<div class="karte" id="stripe"><h2>Bezahlen mit Stripe</h2>
<p class="leise" style="margin-top:-6px">Status: {% if cfg.stripe_key %}<span class="status s-FREIGEGEBEN">aktiv{{ ' – Testmodus' if '_test_' in cfg.stripe_key }}</span>
{% else %}<span class="status s-ENTWURF">aus</span> – ohne Schlüssel können Kunden nach der Freigabe kostenlos herunterladen{% endif %}</p>
<form method="post"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="stripe">
<label class="feld">Geheimer Schlüssel (Stripe → Entwickler → API-Schlüssel, fängt mit sk_live_ an; zum Ausprobieren sk_test_)</label>
<input type="password" name="stripe_key" autocomplete="off" placeholder="{{ 'gespeichert ✓ – leer lassen zum Behalten' if cfg.stripe_key else 'sk_live_…' }}">
<label class="feld">Webhook-Geheimnis (whsec_…, siehe Schritt 2)</label>
<input type="password" name="stripe_webhook_secret" autocomplete="off" placeholder="{{ 'gespeichert ✓ – leer lassen zum Behalten' if cfg.stripe_webhook_secret else 'whsec_…' }}">
<button class="btn">Speichern</button></form>
<ol style="margin-top:18px">
<li>In Stripe: <b>Entwickler → API-Schlüssel</b> → „Geheimer Schlüssel“ kopieren und oben eintragen.</li>
<li>In Stripe: <b>Entwickler → Webhooks → Endpunkt hinzufügen</b>: URL <code>{{ (cfg.basis_url or 'https://deine-seite.de').rstrip('/') }}/stripe/webhook</code>,
Ereignisse <code>checkout.session.completed</code> und <code>checkout.session.async_payment_succeeded</code> → „Signaturgeheimnis“ (whsec_…) oben eintragen.</li>
<li>Unter <b>Einstellungen → Zahlungsmethoden</b> in Stripe auswählen, was Kunden nutzen dürfen (Karte, Apple Pay, PayPal, Klarna …).</li>
<li>Unter Archiv → <b>Preise</b> die Preise eintragen.</li>
</ol>
<form method="post" class="inline"><input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="stripe_test">
<button class="btn gruen">Stripe testen</button></form>
{% if cfg.stripe_key %}<form method="post" class="inline" onsubmit="return confirm('Stripe wirklich entfernen? Danach ist Bezahlen aus.')">
<input type="hidden" name="csrf" value="{{ session.csrf }}"><input type="hidden" name="aktion" value="stripe_aus">
<button class="btn grau">Stripe entfernen</button></form>{% endif %}
<div class="hinweis">Die Schlüssel werden nur hier auf deinem Server gespeichert und nicht angezeigt. Bitte nirgendwo sonst weitergeben.
Ablauf: Kunde bestellt → du gibst frei → Kunde bezahlt bei Stripe → Download wird automatisch freigeschaltet. Stripe schickt dem Kunden eine Rechnung per E-Mail.</div></div>

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
            "firma": lade_config().get("firmenname") or "OneClick Tuning",
            "zu_sortieren": eingang_anzahl() if session.get("admin") else 0}


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
