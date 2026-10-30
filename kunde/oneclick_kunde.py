#!/usr/bin/env python3
"""
OneClick Tuning - Windows-Programm fuer Kunden

Spricht ueber die Schnittstelle /api/... mit dem Server (gleiche Regeln wie die Webseite):
Original auswaehlen -> verfuegbare Loesungen -> Auftrag senden -> nach Freigabe herunterladen.

Nur Python-Standardbibliothek (tkinter), damit die .exe klein bleibt.
Bauen (unter Windows):  pyinstaller --onefile --windowed --name OneClick-Tuning kunde/oneclick_kunde.py
"""

import json
import os
import queue
import sys
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

STANDARD_SERVER = os.environ.get("ONECLICK_SERVER", "https://oneclicksoulution.gh-mapping.de")
VERSION = "1.0"
NACHFRAGE_MS = 10_000   # Status offener Auftraege alle 10 s abfragen

# Farben wie auf der Webseite
BG, KARTE, RAND, TEXT, LEISE = "#000000", "#141416", "#2c2c30", "#f5f5f7", "#a1a1a6"
AKZENT, OK, WARN, BLAU = "#ff375f", "#30d158", "#ffd60a", "#0a84ff"
STATUS_FARBE = {"ENTWURF": BLAU, "WARTET": WARN, "FREIGEGEBEN": OK, "ABGELEHNT": AKZENT}


def datenordner() -> Path:
    basis = os.environ.get("APPDATA") or str(Path.home() / ".config")
    ordner = Path(basis) / "OneClickTuning"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


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
        name = dateiname.replace('"', "")
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
# Oberflaeche
# ---------------------------------------------------------------------------

class Programm:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.speicher = Speicher()
        self.api = Api(self.speicher.daten["server"])
        self.entwurf = None          # aktueller Auftrag in der Auswahl
        self.auswahl = {}            # key -> BooleanVar
        self.original_key = "original"
        self.aufgaben = queue.Queue()   # Hintergrund-Threads -> Fenster (Tkinter ist nicht threadsicher)

        root.title("OneClick Tuning")
        root.geometry("860x700")
        root.minsize(720, 600)
        root.configure(bg=BG)
        self.stil()
        self.aufbau()
        self.liste_zeigen()
        self.root.after(50, self.aufgaben_abarbeiten)
        threading.Thread(target=self.info_laden, daemon=True).start()
        self.root.after(1500, self.offene_pruefen)

    def im_fenster(self, funktion, *args):
        """Aus einem Hintergrund-Thread aufrufen: fuehrt funktion im Fenster-Thread aus."""
        self.aufgaben.put((funktion, args))

    def aufgaben_abarbeiten(self):
        try:
            while True:
                funktion, args = self.aufgaben.get_nowait()
                funktion(*args)
        except queue.Empty:
            pass
        self.root.after(50, self.aufgaben_abarbeiten)

    # --- Aussehen -----------------------------------------------------------
    def stil(self):
        s = ttk.Style()
        s.theme_use("clam")
        schrift = ("Segoe UI", 10)
        s.configure(".", background=BG, foreground=TEXT, font=schrift, bordercolor=RAND)
        s.configure("Karte.TFrame", background=KARTE)
        s.configure("Karte.TLabel", background=KARTE, foreground=TEXT)
        s.configure("Leise.TLabel", background=KARTE, foreground=LEISE)
        s.configure("Titel.TLabel", background=KARTE, foreground=TEXT, font=("Segoe UI Semibold", 15))
        s.configure("Logo.TLabel", background=BG, foreground=AKZENT, font=("Segoe UI Semibold", 17))
        s.configure("Kopf.TLabel", background=BG, foreground=LEISE)
        s.configure("Haupt.TButton", background=AKZENT, foreground="#ffffff", borderwidth=0, padding=(18, 9),
                    font=("Segoe UI Semibold", 10))
        s.map("Haupt.TButton", background=[("disabled", "#5a2a35"), ("active", "#ff5a7a")],
              foreground=[("disabled", "#c9a0aa")])
        s.configure("Grau.TButton", background="#2a2a2e", foreground=TEXT, borderwidth=0, padding=(14, 8))
        s.map("Grau.TButton", background=[("active", "#3a3a40"), ("disabled", "#1c1c1f")],
              foreground=[("disabled", "#5c5c60")])
        s.configure("Gruen.TButton", background=OK, foreground="#00210a", borderwidth=0, padding=(14, 8),
                    font=("Segoe UI Semibold", 10))
        s.map("Gruen.TButton", background=[("active", "#4be070"), ("disabled", "#1f3a26")],
              foreground=[("disabled", "#557a5f")])
        s.configure("Option.TCheckbutton", background=KARTE, foreground=TEXT, font=("Segoe UI Semibold", 11),
                    indicatorbackground="#1c1c1f", indicatorforeground=AKZENT, padding=6)
        s.map("Option.TCheckbutton", background=[("active", KARTE)],
              indicatorbackground=[("selected", "#1c1c1f")])
        s.configure("TEntry", fieldbackground="#1c1c1f", foreground=TEXT, insertcolor=TEXT, bordercolor=RAND,
                    lightcolor=RAND, darkcolor=RAND, padding=7)
        s.configure("Treeview", background=KARTE, fieldbackground=KARTE, foreground=TEXT, rowheight=30,
                    borderwidth=0, font=schrift, bordercolor=KARTE, lightcolor=KARTE, darkcolor=KARTE)
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])   # ohne hellen Rahmen
        s.configure("Treeview.Heading", background=KARTE, foreground=LEISE, borderwidth=0, relief="flat",
                    font=("Segoe UI", 9))
        s.map("Treeview", background=[("selected", "#2b2b30")], foreground=[("selected", TEXT)])
        s.map("Treeview.Heading", background=[("active", KARTE)])
        s.configure("TProgressbar", background=AKZENT, troughcolor="#1c1c1f", bordercolor=KARTE,
                    lightcolor=AKZENT, darkcolor=AKZENT)

    def karte(self, eltern) -> ttk.Frame:
        rahmen = tk.Frame(eltern, bg=RAND, padx=1, pady=1)
        innen = ttk.Frame(rahmen, style="Karte.TFrame", padding=20)
        innen.pack(fill="both", expand=True)
        return rahmen, innen

    def aufbau(self):
        kopf = tk.Frame(self.root, bg=BG, padx=24, pady=14)
        kopf.pack(fill="x")
        self.logo = ttk.Label(kopf, text="OneClick Tuning", style="Logo.TLabel")
        self.logo.pack(side="left")
        ttk.Button(kopf, text="Einstellungen", style="Grau.TButton", command=self.einstellungen).pack(side="right")

        haupt = tk.Frame(self.root, bg=BG, padx=24)
        haupt.pack(fill="both", expand=True)

        # Karte 1: hochladen bzw. Loesungen waehlen
        rahmen, self.oben = self.karte(haupt)
        rahmen.pack(fill="x", pady=(0, 16))
        self.upload_zeigen()

        # Karte 2: Meine Auftraege
        rahmen, unten = self.karte(haupt)
        rahmen.pack(fill="both", expand=True, pady=(0, 20))
        zeile = ttk.Frame(unten, style="Karte.TFrame")
        zeile.pack(fill="x")
        ttk.Label(zeile, text="Meine Aufträge", style="Titel.TLabel").pack(side="left")
        self.laden_knopf = ttk.Button(zeile, text="⬇  Herunterladen", style="Gruen.TButton",
                                      command=self.herunterladen, state="disabled")
        self.laden_knopf.pack(side="right")
        self.entfernen_knopf = ttk.Button(zeile, text="Aus Liste entfernen", style="Grau.TButton",
                                          command=self.entfernen, state="disabled")
        self.entfernen_knopf.pack(side="right", padx=8)

        spalten = ("zeit", "datei", "loesung", "status")
        self.liste = ttk.Treeview(unten, columns=spalten, show="headings", selectmode="browse", height=7)
        for key, titel, breite in (("zeit", "DATUM", 130), ("datei", "DATEI", 220),
                                   ("loesung", "LÖSUNG", 220), ("status", "STATUS", 170)):
            self.liste.heading(key, text=titel, anchor="w")
            self.liste.column(key, width=breite, anchor="w")
        for status, farbe in STATUS_FARBE.items():
            self.liste.tag_configure(status, foreground=farbe)
        self.liste.pack(fill="both", expand=True, pady=(12, 6))
        self.liste.bind("<<TreeviewSelect>>", lambda e: self.auswahl_geaendert())
        self.liste.bind("<Double-1>", lambda e: self.herunterladen())
        self.hinweis = ttk.Label(unten, text="", style="Leise.TLabel", wraplength=760, justify="left")
        self.hinweis.pack(fill="x")

    def leeren(self):
        for w in self.oben.winfo_children():
            w.destroy()

    # --- Schritt 1: Datei waehlen -------------------------------------------
    def upload_zeigen(self, meldung: str = ""):
        self.leeren()
        self.entwurf = None
        ttk.Label(self.oben, text="Original hochladen", style="Titel.TLabel").pack(anchor="w")
        ttk.Label(self.oben, text="Wir prüfen sofort, welche Lösungen es für dein File gibt. "
                                  "Nach unserer Freigabe kannst du das fertige File herunterladen.",
                  style="Leise.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(4, 14))
        self.datei_knopf = ttk.Button(self.oben, text="Datei auswählen …", style="Haupt.TButton",
                                      command=self.datei_waehlen)
        self.datei_knopf.pack(anchor="w")
        self.fortschritt = ttk.Progressbar(self.oben, mode="indeterminate", length=260)
        self.meldung = ttk.Label(self.oben, text=meldung, style="Leise.TLabel", wraplength=760, justify="left")
        self.meldung.pack(anchor="w", pady=(12, 0))
        if meldung:
            self.meldung.configure(foreground=WARN)

    def datei_waehlen(self):
        pfad = filedialog.askopenfilename(title="Originaldatei auswählen",
                                          filetypes=[("ECU-Files", "*.bin *.ori *.org *.mod"), ("Alle Dateien", "*.*")])
        if not pfad:
            return
        try:
            inhalt = Path(pfad).read_bytes()
        except OSError as e:
            messagebox.showerror("Fehler", f"Die Datei konnte nicht gelesen werden:\n{e}")
            return
        if len(inhalt) > 16 * 1024 * 1024:
            messagebox.showerror("Zu groß", "Die Datei ist größer als 16 MB.")
            return
        self.datei_knopf.configure(state="disabled", text="Wird geprüft …")
        self.meldung.configure(text=Path(pfad).name, foreground=LEISE)
        self.fortschritt.pack(anchor="w", pady=(12, 0))
        self.fortschritt.start(12)
        threading.Thread(target=self._pruefen, args=(Path(pfad).name, inhalt), daemon=True).start()

    def _pruefen(self, name: str, inhalt: bytes):
        try:
            a = self.api.pruefen(name, inhalt)
            self.im_fenster(self.loesungen_zeigen, a)
        except Fehler as e:
            self.im_fenster(self.upload_zeigen, str(e))

    # --- Schritt 2: Loesungen waehlen -----------------------------------------
    def loesungen_zeigen(self, a: dict):
        self.leeren()
        self.entwurf = a
        ttk.Label(self.oben, text=a["datei"], style="Titel.TLabel").pack(anchor="w")
        ttk.Label(self.oben, text=f"ECU: {a['ecu']}     Software: {a['software']}",
                  style="Leise.TLabel").pack(anchor="w", pady=(2, 12))
        mehrere = len(a["angebot"]) > 1
        ttk.Label(self.oben, text="Für dein File haben wir folgende Lösungen" +
                  (" – eine oder mehrere wählen:" if mehrere else ":"), style="Karte.TLabel").pack(anchor="w")
        feld = ttk.Frame(self.oben, style="Karte.TFrame")
        feld.pack(anchor="w", pady=(6, 10))
        self.auswahl = {}
        for i, o in enumerate(a["angebot"]):
            var = tk.BooleanVar(value=(i == 0))
            self.auswahl[o["key"]] = var
            ttk.Checkbutton(feld, text=o["name"], variable=var, style="Option.TCheckbutton",
                            command=lambda k=o["key"]: self.option_geklickt(k)).grid(
                row=i // 3, column=i % 3, sticky="w", padx=(0, 26), pady=2)
        zeile = ttk.Frame(self.oben, style="Karte.TFrame")
        zeile.pack(fill="x", pady=(4, 0))
        ttk.Label(zeile, text="Name / Firma / Telefon (optional):", style="Leise.TLabel").pack(side="left")
        self.kontakt = ttk.Entry(zeile, width=40)
        self.kontakt.insert(0, self.speicher.daten.get("kontakt", ""))
        self.kontakt.pack(side="left", padx=10, fill="x", expand=True)
        knoepfe = ttk.Frame(self.oben, style="Karte.TFrame")
        knoepfe.pack(anchor="w", pady=(14, 0))
        self.senden_knopf = ttk.Button(knoepfe, text="Auftrag senden", style="Haupt.TButton", command=self.senden)
        self.senden_knopf.pack(side="left")
        ttk.Button(knoepfe, text="Abbrechen", style="Grau.TButton",
                   command=lambda: self.upload_zeigen()).pack(side="left", padx=10)
        self.meldung = ttk.Label(self.oben, text="Checksumme bitte beim Schreiben vom Flash-Tool korrigieren lassen.",
                                 style="Leise.TLabel", wraplength=760, justify="left")
        self.meldung.pack(anchor="w", pady=(12, 0))

    def option_geklickt(self, key: str):
        # "Original (Rueckruesten)" laesst sich nicht kombinieren
        if self.auswahl[key].get():
            for k, var in self.auswahl.items():
                if k != key and (key == self.original_key or k == self.original_key):
                    var.set(False)
        self.senden_knopf.configure(state="normal" if any(v.get() for v in self.auswahl.values()) else "disabled")

    def senden(self):
        gewaehlt = [k for k, v in self.auswahl.items() if v.get()]
        if not gewaehlt:
            return
        kontakt = self.kontakt.get().strip()
        self.speicher.daten["kontakt"] = kontakt
        self.senden_knopf.configure(state="disabled", text="Wird gesendet …")
        threading.Thread(target=self._senden, args=(self.entwurf["id"], gewaehlt, kontakt), daemon=True).start()

    def _senden(self, aid: str, gewaehlt: list, kontakt: str):
        try:
            a = self.api.bestellen(aid, gewaehlt, kontakt)
            self.im_fenster(self._gesendet, a)
        except Fehler as e:
            self.im_fenster(self._senden_fehler, str(e))

    def _gesendet(self, a: dict):
        self.speicher.auftrag_merken(a)
        self.liste_zeigen(markieren=a["id"])
        self.upload_zeigen()
        self.meldung.configure(text=f"✓ Auftrag „{a['option_name']}“ gesendet. Du bekommst Bescheid, sobald er "
                                    "freigegeben ist – das Programm kann dafür offen bleiben.", foreground=OK)

    def _senden_fehler(self, text: str):
        self.senden_knopf.configure(state="normal", text="Auftrag senden")
        self.meldung.configure(text=text, foreground=WARN)

    # --- Meine Auftraege ------------------------------------------------------
    def liste_zeigen(self, markieren: str = None):
        self.liste.delete(*self.liste.get_children())
        for a in self.speicher.daten["auftraege"]:
            try:
                zeit = datetime.fromisoformat(a["zeit"]).strftime("%d.%m.%Y %H:%M")
            except Exception:
                zeit = a.get("zeit", "")
            self.liste.insert("", "end", iid=a["id"], tags=(a.get("status", ""),),
                              values=(zeit, a.get("datei", ""), a.get("option_name") or "–", a.get("status_text", "")))
        if markieren and self.liste.exists(markieren):
            self.liste.selection_set(markieren)
            self.liste.see(markieren)
        self.auswahl_geaendert()

    def gewaehlter_auftrag(self):
        sel = self.liste.selection()
        return next((a for a in self.speicher.daten["auftraege"] if sel and a["id"] == sel[0]), None)

    def auswahl_geaendert(self):
        a = self.gewaehlter_auftrag()
        self.laden_knopf.configure(state="normal" if a and a.get("status") == "FREIGEGEBEN" else "disabled")
        self.entfernen_knopf.configure(state="normal" if a else "disabled")
        if not a:
            self.hinweis.configure(text="", foreground=LEISE)
        elif a.get("status") == "ABGELEHNT":
            self.hinweis.configure(text="Abgelehnt" + (f": {a['grund']}" if a.get("grund") else "") +
                                   ". Bei Fragen melde dich gerne bei uns.", foreground=AKZENT)
        elif a.get("status") == "WARTET":
            self.hinweis.configure(text="Wartet auf unsere Freigabe. Der Status wird automatisch aktualisiert.",
                                   foreground=WARN)
        elif a.get("status") == "FREIGEGEBEN":
            self.hinweis.configure(text="Freigegeben – mit „Herunterladen“ oder Doppelklick speichern. "
                                        "Checksumme beim Schreiben vom Flash-Tool korrigieren lassen.", foreground=OK)
        else:
            self.hinweis.configure(text="", foreground=LEISE)

    def offene_pruefen(self):
        offen = [a["id"] for a in self.speicher.daten["auftraege"] if a.get("status") == "WARTET"]
        if offen:
            threading.Thread(target=self._offene_pruefen, args=(offen,), daemon=True).start()
        self.root.after(NACHFRAGE_MS, self.offene_pruefen)

    def _offene_pruefen(self, ids: list):
        neu = []
        for aid in ids:
            try:
                neu.append(self.api.status(aid))
            except Fehler:
                pass
        if neu:
            self.im_fenster(self._status_neu, neu)

    def _status_neu(self, neu: list):
        geaendert = []
        for a in neu:
            alt = next((x for x in self.speicher.daten["auftraege"] if x["id"] == a["id"]), None)
            if alt and alt.get("status") != a["status"]:
                geaendert.append(a)
            self.speicher.auftrag_merken(a)
        if not geaendert:
            return
        sel = self.liste.selection()
        self.liste_zeigen(markieren=geaendert[0]["id"] if not sel else sel[0])
        self.root.bell()
        for a in geaendert:
            if a["status"] == "FREIGEGEBEN":
                messagebox.showinfo("Freigegeben", f"„{a['option_name']}“ für {a['datei']} ist freigegeben.\n\n"
                                                   "Du kannst das File jetzt herunterladen.")
            elif a["status"] == "ABGELEHNT":
                messagebox.showwarning("Abgelehnt", f"Der Auftrag für {a['datei']} wurde abgelehnt." +
                                       (f"\n\nGrund: {a['grund']}" if a.get("grund") else ""))

    def herunterladen(self):
        a = self.gewaehlter_auftrag()
        if not a or a.get("status") != "FREIGEGEBEN":
            return
        vorschlag = f"{Path(a['datei']).stem}_{(a.get('option') or 'file').replace('+', '_')}.bin"
        ziel = filedialog.asksaveasfilename(title="File speichern", initialfile=vorschlag, defaultextension=".bin",
                                            filetypes=[("ECU-File", "*.bin"), ("Alle Dateien", "*.*")])
        if not ziel:
            return
        self.laden_knopf.configure(state="disabled", text="Wird geladen …")
        threading.Thread(target=self._herunterladen, args=(a["id"], ziel), daemon=True).start()

    def _herunterladen(self, aid: str, ziel: str):
        try:
            Path(ziel).write_bytes(self.api.herunterladen(aid))
            self.im_fenster(lambda: messagebox.showinfo(
                "Gespeichert", f"Gespeichert unter:\n{ziel}\n\nChecksumme beim Schreiben vom Flash-Tool korrigieren lassen."))
        except (Fehler, OSError) as e:
            self.im_fenster(messagebox.showerror, "Fehler", str(e))
        finally:
            self.im_fenster(lambda: (self.laden_knopf.configure(text="⬇  Herunterladen"), self.auswahl_geaendert()))

    def entfernen(self):
        a = self.gewaehlter_auftrag()
        if a and messagebox.askyesno("Entfernen", f"„{a['datei']}“ aus der Liste entfernen?\n"
                                                  "(Auf dem Server bleibt der Auftrag erhalten.)"):
            self.speicher.daten["auftraege"] = [x for x in self.speicher.daten["auftraege"] if x["id"] != a["id"]]
            self.speicher.speichern()
            self.liste_zeigen()

    # --- Sonstiges -------------------------------------------------------------
    def info_laden(self):
        try:
            info = self.api.info()
            self.original_key = info.get("original", "original")
            self.im_fenster(lambda: (self.logo.configure(text=info["firma"]), self.root.title(info["firma"])))
        except Fehler:
            pass

    def einstellungen(self):
        neu = simpledialog.askstring("Einstellungen", "Adresse des Servers:", parent=self.root,
                                        initialvalue=self.speicher.daten["server"])
        if neu and neu.strip():
            neu = neu.strip().rstrip("/")
            if not neu.startswith(("https://", "http://")):
                neu = "https://" + neu
            self.speicher.daten["server"] = neu
            self.speicher.speichern()
            self.api = Api(neu)
            threading.Thread(target=self.info_laden, daemon=True).start()


def main():
    root = tk.Tk()
    if sys.platform == "win32":
        try:   # scharfe Schrift auf Bildschirmen mit Skalierung
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    Programm(root)
    root.mainloop()


if __name__ == "__main__":
    main()
