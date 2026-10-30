"""
Automatische Tests. Ausfuehren im Projektordner:

    python -m unittest discover tests

Arbeiten komplett in einem temporaeren Ordner, echte Daten werden nicht angefasst.
"""

import io
import json
import os
import random
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as A          # noqa: E402
import oneclick          # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

GROESSE = 512 * 1024


def zufall(n: int, seed: int) -> bytearray:
    return bytearray(random.Random(seed).randbytes(n))


class Basis(unittest.TestCase):
    """Legt fuer jeden Test ein frisches Archiv in einem temporaeren Ordner an."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        oneclick.ARCHIV, oneclick.INDEX_DATEI = d / "archiv", d / "index.json"
        oneclick.OPTIONEN_DATEI = d / "optionen.json"
        A.AUFTRAEGE, A.BENUTZER_DATEI, A.CONFIG_DATEI = d / "auftraege", d / "benutzer.json", d / "config.json"
        A.AUFTRAEGE.mkdir()
        A.versuche.clear()
        self.telegram = []
        A.telegram_api = lambda m, daten, timeout=15: self.telegram.append((m, daten)) or {
            "ok": True, "result": {"message_id": 1}}
        A.BENUTZER_DATEI.write_text(json.dumps({"chef": {"pw": generate_password_hash("Geheim123"), "rolle": "admin"}}))

        # Golf: Original mit Softwarenummer, Stage 1 (viele Aenderungen) und Start/Stopp
        self.golf = zufall(GROESSE, 1)
        self.golf[0x100:0x120] = b"EDC17C46  1037541778 03L906018JL"
        self.stage1 = bytearray(self.golf)
        self.stellen = []
        rnd = random.Random(5)
        for _ in range(20):
            off, laenge = rnd.randrange(0x8000, GROESSE - 0x400), rnd.randrange(2, 200)
            self.stellen.append((off, laenge))
            for i in range(laenge):
                self.stage1[off + i] ^= 0x5A
        self.startstopp = bytearray(self.golf)
        self.startstopp[0x7000:0x7004] = b"\0\0\0\0"
        self.ablegen("Golf7", {"Golf7_ORI.bin": self.golf, "Golf7_Stage1.bin": self.stage1,
                               "Golf7_StartStop.bin": self.startstopp})
        # BMW: nur Stage 1
        self.bmw = zufall(GROESSE, 2)
        self.bmw_st1 = bytearray(self.bmw)
        self.bmw_st1[0x9000:0x9010] = bytes(16)
        self.ablegen("BMW", {"ori.bin": self.bmw, "stage1.bin": self.bmw_st1})
        oneclick.baue_index()

    def tearDown(self):
        self.tmp.cleanup()

    def ablegen(self, name, dateien):
        ordner = oneclick.ARCHIV / name
        ordner.mkdir(parents=True)
        for n, d in dateien.items():
            (ordner / n).write_bytes(bytes(d))

    def mit_fin(self):
        """Golf-Original mit anderer Fahrgestellnummer (weit weg von allen Tuning-Stellen)."""
        v = bytearray(self.golf)
        v[0x200:0x211] = b"WVWZZZAUZHW123456"
        return v


class KernTests(Basis):
    def test_identisch_alle_optionen(self):
        _, l = oneclick.finde_loesungen(bytes(self.golf))
        self.assertEqual(set(l), {"stage1", "startstopp"})
        self.assertEqual(l["stage1"]["daten"], bytes(self.stage1))
        self.assertEqual(l["stage1"]["art"], "identisch")

    def test_nur_vorhandene_optionen(self):
        _, l = oneclick.finde_loesungen(bytes(self.bmw))
        self.assertEqual(set(l), {"stage1"})

    def test_andere_fin_gleiche_stellen(self):
        v = self.mit_fin()
        _, l = oneclick.finde_loesungen(bytes(v))
        erwartet = bytearray(v)
        for off, laenge in self.stellen:
            erwartet[off:off + laenge] = self.stage1[off:off + laenge]
        self.assertEqual(l["stage1"]["daten"], bytes(erwartet))
        self.assertEqual(l["stage1"]["art"], "gleiche Stellen")

    def test_nur_identisch_schaltet_gleiche_stellen_ab(self):
        _, l = oneclick.finde_loesungen(bytes(self.mit_fin()), nur_identisch=True)
        self.assertEqual(l, {})

    def test_ein_byte_im_kennfeld_anders(self):
        v = self.mit_fin()
        off, _ = self.stellen[3]
        v[off] ^= 1
        _, l = oneclick.finde_loesungen(bytes(v))
        self.assertNotIn("stage1", l)
        self.assertIn("startstopp", l)   # Start/Stopp-Stelle ist unberuehrt

    def test_ein_byte_neben_kennfeld_anders(self):
        v = self.mit_fin()
        off, _ = self.stellen[3]
        v[off - 5] ^= 1
        _, l = oneclick.finde_loesungen(bytes(v))
        self.assertNotIn("stage1", l)

    def test_andere_softwarenummer(self):
        v = self.mit_fin()
        v[0x10A:0x114] = b"1037999999"
        _, l = oneclick.finde_loesungen(bytes(v))
        self.assertEqual(l, {})

    def test_verschoben_kein_treffer(self):
        v = bytearray(self.golf)
        v[0x4000:0x4000] = b"x" * 64
        _, l = oneclick.finde_loesungen(bytes(v[:GROESSE]))
        self.assertEqual(l, {})

    def test_fremd_und_andere_groesse(self):
        self.assertEqual(oneclick.finde_loesungen(bytes(zufall(GROESSE, 9)))[1], {})
        self.assertEqual(oneclick.finde_loesungen(bytes(self.golf[:1000]))[1], {})

    def test_rueckruesten_identisch(self):
        _, l = oneclick.finde_loesungen(bytes(self.stage1))
        self.assertIn("original", l)
        self.assertEqual(l["original"]["daten"], bytes(self.golf))
        self.assertEqual(l["original"]["art"], "identisch")

    def test_rueckruesten_andere_fin(self):
        v = bytearray(self.stage1)
        v[0x200:0x211] = b"WVWZZZAUZHW123456"
        _, l = oneclick.finde_loesungen(bytes(v))
        erwartet = bytearray(v)
        for off, laenge in self.stellen:
            erwartet[off:off + laenge] = self.golf[off:off + laenge]
        self.assertEqual(l["original"]["daten"], bytes(erwartet))   # FIN bleibt vom Kunden
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(v), nur_identisch=True)[1])

    def test_rueckruesten_fremdes_tuning(self):
        v = bytearray(self.stage1)
        off, _ = self.stellen[2]
        v[off] ^= 1   # anderes Tuning an einer Stage-1-Stelle
        l = oneclick.finde_loesungen(bytes(v))[1]
        # kein 100-%-Treffer mehr, nur noch ueber die Softwarenummer (Admin prueft)
        self.assertEqual(l["original"]["art"], "softwarenummer")
        self.assertEqual(l["original"]["daten"], bytes(self.golf))

    def test_original_kein_rueckruesten(self):
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(self.golf))[1])

    def test_kombiniere(self):
        basis = bytes(10)
        a, b = bytearray(basis), bytearray(basis)
        a[1], b[5] = 7, 9
        self.assertEqual(oneclick.kombiniere(basis, [bytes(a), bytes(b)]), bytes([0, 7, 0, 0, 0, 9, 0, 0, 0, 0]))
        b[1] = 7   # gleiche Aenderung an gleicher Stelle ist ok
        self.assertIsNotNone(oneclick.kombiniere(basis, [bytes(a), bytes(b)]))
        b[1] = 8   # unterschiedlich -> nicht kombinierbar
        self.assertIsNone(oneclick.kombiniere(basis, [bytes(a), bytes(b)]))

    def nur_original_ablegen(self):
        """Archiv-Eintrag ohne Tuning-File: nur das Original (mit Softwarenummer)."""
        self.mazda = zufall(GROESSE, 31)
        self.mazda[0x100:0x120] = b"EDC17CP42 1037399999 0281099999 "
        self.ablegen("Mazda_nur_ORI", {"Mazda_ORI.bin": self.mazda})
        oneclick.baue_index()

    def fremdes_tuning(self, basis, anzahl=3000):
        mod = bytearray(basis)
        rnd = random.Random(77)
        for _ in range(anzahl):
            mod[rnd.randrange(0x10000, GROESSE)] ^= 0x33
        return mod

    def test_rueckruesten_ueber_softwarenummer(self):
        self.nur_original_ablegen()
        _, l = oneclick.finde_loesungen(bytes(self.fremdes_tuning(self.mazda)))
        self.assertEqual(set(l), {"original"})
        self.assertEqual(l["original"]["art"], "softwarenummer")
        self.assertEqual(l["original"]["daten"], bytes(self.mazda))

    def test_rueckruesten_softwarenummer_grenzen(self):
        self.nur_original_ablegen()
        # Original selbst hochgeladen -> nichts zurueckzuruesten
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(self.mazda))[1])
        # zu viel veraendert (> 5 %) -> kein Angebot
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(self.fremdes_tuning(self.mazda, 60000)))[1])
        # andere Softwarenummer -> kein Angebot
        v = self.fremdes_tuning(self.mazda)
        v[0x10A:0x114] = b"1037888888"
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(v))[1])
        # Softwarenummer nicht lesbar -> kein Angebot
        v = self.fremdes_tuning(self.mazda)
        v[0x10A:0x114] = bytes(10)
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(v))[1])
        # Einstellung "nur identisch" schaltet es ab
        self.assertNotIn("original", oneclick.finde_loesungen(bytes(self.fremdes_tuning(self.mazda)), nur_identisch=True)[1])

    def test_dateinamen_erkennung(self):
        k = oneclick.klassifiziere
        self.assertEqual(k(["Golf_ORI.bin", "Golf_Stage1.bin"]), ("Golf_ORI.bin", {"stage1": "Golf_Stage1.bin"}))
        self.assertEqual(k(["a.ori", "a_mod.bin"]), ("a.ori", {"stage1": "a_mod.bin"}))
        self.assertEqual(k(["x original.bin", "x st2.bin", "x vmax.bin"])[1], {"stage2": "x st2.bin", "vmax": "x vmax.bin"})
        self.assertEqual(k(["eins.bin", "zwei.bin"]), (None, {}))
        self.assertEqual(k(["ori.bin", ".tmp.bin", "x.sync-conflict.bin"]), ("ori.bin", {}))


class WebTests(Basis):
    def setUp(self):
        super().setUp()
        self.kunde = self.client()

    def client(self):
        c = A.app.test_client()
        c.get("/")
        with c.session_transaction() as s:
            c.csrf = s["csrf"]
        return c

    def admin(self):
        c = self.client()
        c.post("/login", data={"name": "chef", "pw": "Geheim123", "csrf": c.csrf})
        with c.session_transaction() as s:
            c.csrf = s["csrf"]
        return c

    # --- Kunde = Windows-Programm (Schnittstelle /api/...) ---
    def hochladen(self, daten, name="kunde.bin"):
        r = self.kunde.post("/api/pruefen", data={"datei": (io.BytesIO(bytes(daten)), name)},
                            content_type="multipart/form-data")
        return r.json["id"] if r.status_code == 200 else None

    def angebot(self, aid):
        """{schluessel: Anzeigename} der Loesungen, die das Programm anzeigt."""
        return {o["key"]: o["name"] for o in self.kunde.get(f"/api/auftrag/{aid}").json["angebot"]}

    def laden(self, aid):
        return self.kunde.get(f"/api/auftrag/{aid}/download")

    def auftrag(self, aid):
        return json.loads((A.AUFTRAEGE / aid / "auftrag.json").read_text())

    def test_ablauf_komplett(self):
        aid = self.hochladen(self.golf)
        self.assertEqual(list(self.angebot(aid)), ["stage1", "startstopp"])
        self.assertEqual(self.laden(aid).status_code, 403)
        self.assertEqual(self.telegram, [])   # Meldung erst nach dem Bestellen

        self.bestellen(aid, "startstopp")
        self.assertEqual(self.auftrag(aid)["status"], "WARTET")
        self.assertEqual(self.laden(aid).status_code, 403)

        A.entscheide(aid, True, wer="test")
        d = self.laden(aid)
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.data, bytes(self.startstopp))

    def test_rueckruesten_im_web(self):
        aid = self.hochladen(self.bmw_st1, "bmw_stage1.bin")
        self.assertEqual(self.angebot(aid), {"original": "Original (Rückrüsten)"})
        self.bestellen(aid, "original")
        self.assertEqual(self.laden(aid).status_code, 403)
        A.entscheide(aid, True)
        self.assertEqual(self.laden(aid).data, bytes(self.bmw))
        # Im Archiv-Formular gibt es kein Upload-Feld fuer "Original (Rueckruesten)"
        self.assertNotIn('name="original"', self.admin().get("/admin/archiv").text)

    def test_alter_index_wird_neu_gebaut(self):
        alt = json.loads(oneclick.INDEX_DATEI.read_text())
        del alt["version"]
        oneclick.INDEX_DATEI.write_text(json.dumps(alt))
        self.assertIn("original", oneclick.finde_loesungen(bytes(self.stage1))[1])

    def bestellen(self, aid, *optionen, kontakt=""):
        """Gibt die Antwort als Text zurueck (Fehlermeldung oder Auftrag)."""
        r = self.kunde.post(f"/api/auftrag/{aid}/bestellen", json={"optionen": list(optionen), "kontakt": kontakt})
        return json.dumps(r.json, ensure_ascii=False)

    def test_kombination_stage1_startstopp(self):
        A.speichere_config({"telegram_chat_id": "1"})
        aid = self.hochladen(self.golf)
        self.bestellen(aid, "stage1", "startstopp")
        a = self.auftrag(aid)
        self.assertEqual((a["status"], a["option"]), ("WARTET", "stage1+startstopp"))
        import time
        time.sleep(0.3)
        self.assertTrue(any("Stage 1 + Start/Stopp aus" in d["text"] for m, d in self.telegram if m == "sendMessage"))
        A.entscheide(aid, True)
        erwartet = bytearray(self.stage1)
        erwartet[0x7000:0x7004] = self.startstopp[0x7000:0x7004]
        self.assertEqual(self.laden(aid).data, bytes(erwartet))
        self.assertIn("Stage 1 + Start/Stopp aus", self.admin().get("/admin").text)

    def test_kombination_mit_ueberschneidung_abgelehnt(self):
        # Vmax aendert ein Byte, das auch Stage 1 aendert, aber anders
        vmax = bytearray(self.golf)
        off, _ = self.stellen[0]
        vmax[off] = (self.stage1[off] + 1) % 256
        self.fahrzeug(self.admin(), "Golf7", self.golf, vmax=vmax)
        aid = self.hochladen(self.golf)
        self.assertIn("nicht möglich", self.bestellen(aid, "stage1", "vmax"))
        self.assertEqual(self.auftrag(aid)["status"], "ENTWURF")
        self.bestellen(aid, "stage1")   # einzeln geht weiterhin
        self.assertEqual(self.auftrag(aid)["option"], "stage1")

    def test_original_nicht_kombinierbar(self):
        aid = self.hochladen(self.stage1, "golf_stage1.bin")
        self.assertIn("nicht mit anderen Lösungen kombiniert", self.bestellen(aid, "original", "startstopp"))
        self.assertEqual(self.auftrag(aid)["status"], "ENTWURF")

    def test_nur_original_im_web(self):
        A.speichere_config({"telegram_chat_id": "1"})
        a = self.admin()
        mazda = zufall(GROESSE, 32)
        mazda[0x100:0x120] = b"EDC17CP42 1037311111 0281011111 "
        self.assertIn("reines Original", self.fahrzeug(a, "Mazda6", mazda))
        self.assertIn("nur Original", a.get("/admin/archiv").text)
        fremd = bytearray(mazda)
        fremd[0x20000:0x20400] = bytes(1024)
        aid = self.hochladen(fremd, "mazda_mod.bin")
        self.assertIn("original", self.angebot(aid))
        self.bestellen(aid, "original")
        import time
        time.sleep(0.3)
        self.assertTrue(any("über Softwarenummer" in d["text"] for m, d in self.telegram if m == "sendMessage"))
        self.assertIn("Prüfen", a.get(f"/auftrag/{aid}").text)
        A.entscheide(aid, True)
        self.assertEqual(self.laden(aid).data, bytes(mazda))

    def test_bmw_nur_stage1(self):
        aid = self.hochladen(self.bmw)
        self.assertEqual(list(self.angebot(aid)), ["stage1"])

    def test_nicht_angebotene_option_abgelehnt(self):
        aid = self.hochladen(self.bmw)
        self.bestellen(aid, "startstopp")
        self.assertEqual(self.auftrag(aid)["status"], "ENTWURF")
        self.bestellen(aid)   # nichts gewaehlt
        self.assertEqual(self.auftrag(aid)["status"], "ENTWURF")

    def test_kein_treffer_kein_auftrag(self):
        self.assertIsNone(self.hochladen(zufall(GROESSE, 7)))
        self.assertEqual(list(A.AUFTRAEGE.iterdir()), [])

    def test_ablehnen_mit_grund(self):
        aid = self.hochladen(self.golf)
        self.bestellen(aid, "stage1")
        a = self.admin()
        a.post(f"/admin/auftrag/{aid}/entscheiden", data={"csrf": a.csrf, "aktion": "nein", "grund": "Test-Grund"})
        self.assertEqual(self.kunde.get(f"/api/auftrag/{aid}").json["grund"], "Test-Grund")
        self.assertEqual(self.laden(aid).status_code, 403)

    def test_doppelte_entscheidung_aendert_nichts(self):
        aid = self.hochladen(self.golf)
        self.bestellen(aid, "stage1")
        self.assertEqual(A.entscheide(aid, True, wer="x"), "Freigegeben.")
        self.assertIn("schon", A.entscheide(aid, False, wer="x"))

    def test_admin_seiten_geschuetzt(self):
        for pfad in ["/admin", "/admin/archiv", "/admin/einstellungen"]:
            self.assertEqual(self.kunde.get(pfad).status_code, 302, pfad)
        a = self.admin()
        for pfad in ["/admin", "/admin/archiv", "/admin/einstellungen"]:
            self.assertEqual(a.get(pfad).status_code, 200, pfad)

    def test_csrf(self):
        self.assertEqual(A.app.test_client().post("/login", data={"name": "chef", "pw": "Geheim123"}).status_code, 400)

    def test_keine_kunden_webseite_mehr(self):
        start = self.client().get("/").text
        self.assertIn("Windows-Programm herunterladen", start)
        self.assertNotIn('name="datei"', start)
        c = self.client()
        self.assertEqual(c.post("/pruefen", data={"csrf": c.csrf}).status_code, 404)
        aid = self.hochladen(self.golf)
        self.assertEqual(self.client().get(f"/auftrag/{aid}").status_code, 302)   # nur Admin
        self.assertEqual(self.admin().get(f"/auftrag/{aid}").status_code, 200)

    def test_login_sperre(self):
        c = self.client()
        for _ in range(5):
            c.post("/login", data={"name": "chef", "pw": "falsch", "csrf": c.csrf})
        r = c.post("/login", data={"name": "chef", "pw": "Geheim123", "csrf": c.csrf})
        self.assertIn("Zu viele Fehlversuche", r.text)
        with c.session_transaction() as s:
            self.assertFalse(s.get("admin"))

    def test_passwort_aendern(self):
        a = self.admin()
        a.post("/admin/einstellungen", data={"csrf": a.csrf, "aktion": "passwort", "alt": "Geheim123",
                                             "neu": "NeuesPW99", "neu2": "NeuesPW99"})
        c = self.client()
        c.post("/login", data={"name": "chef", "pw": "NeuesPW99", "csrf": c.csrf})
        self.assertEqual(c.get("/admin").status_code, 200)

    def test_firmenname_und_impressum(self):
        a = self.admin()
        a.post("/admin/einstellungen", data={"csrf": a.csrf, "aktion": "speichern", "firmenname": "Müller Tuning",
                                             "impressum": "Müller GmbH\nHauptstr. 1", "aufbewahrung_tage": "90"})
        self.assertIn("Müller", self.kunde.get("/").text)
        self.assertIn("Hauptstr. 1", self.kunde.get("/impressum").text)

    def test_zip_import(self):
        a = self.admin()
        puffer = io.BytesIO()
        neu = zufall(GROESSE, 3)
        mod = bytearray(neu)
        mod[0x5000] ^= 0xFF
        with zipfile.ZipFile(puffer, "w") as z:
            z.writestr("Export/Audi A4/a4_ORI.bin", bytes(neu))
            z.writestr("Export/Audi A4/a4_Stage1.bin", bytes(mod))
            z.writestr("../../boese/ori.bin", b"x")
        puffer.seek(0)
        a.post("/admin/archiv/import", data={"csrf": a.csrf, "zip": (puffer, "files.zip")},
               content_type="multipart/form-data")
        self.assertTrue((oneclick.ARCHIV / "Audi-A4" / "stage1.bin").exists())
        self.assertIsNotNone(self.hochladen(neu))

    def fahrzeug(self, a, name, ori, **mods):
        daten = {"csrf": a.csrf, "name": name, "ori": (io.BytesIO(bytes(ori)), "o.bin")}
        for opt, d in mods.items():
            daten[opt] = (io.BytesIO(bytes(d)), f"{opt}.bin")
        r = a.post("/admin/archiv/neu", data=daten, content_type="multipart/form-data", follow_redirects=True)
        return r.text

    def test_fahrzeug_ohne_zip_anlegen(self):
        a = self.admin()
        neu = zufall(GROESSE, 11)
        st1 = bytearray(neu)
        st1[0x6000:0x6008] = bytes(8)
        self.assertIn("angelegt", self.fahrzeug(a, "Passat B8", neu, stage1=st1))
        aid = self.hochladen(neu)
        self.assertIn("stage1", self.angebot(aid))

    def test_option_zu_vorhandenem_fahrzeug(self):
        a = self.admin()
        vmax = bytearray(self.golf)
        vmax[0x7100:0x7102] = b"\xff\xff"
        self.assertIn("ergänzt", self.fahrzeug(a, "Golf7", self.golf, vmax=vmax))
        _, l = oneclick.finde_loesungen(bytes(self.golf))
        self.assertEqual(set(l), {"stage1", "startstopp", "vmax"})   # vorhandene Optionen bleiben
        self.assertEqual(l["stage1"]["daten"], bytes(self.stage1))

    def test_fahrzeug_fehler_werden_abgewiesen(self):
        a = self.admin()
        anders = zufall(GROESSE, 12)
        st1 = bytearray(anders)
        st1[0x6000] ^= 1
        self.assertIn("anderen Original", self.fahrzeug(a, "Golf7", anders, stage1=st1))
        self.assertIn("andere Dateigröße", self.fahrzeug(a, "Neu", anders, stage1=st1[:1000]))
        self.assertIn("identisch mit dem Original", self.fahrzeug(a, "Neu", anders, stage1=anders))
        self.assertFalse((oneclick.ARCHIV / "Neu").exists())

    def loesung(self, a, aktion="neu", **daten):
        r = a.post("/admin/loesungen", data={"csrf": a.csrf, "aktion": aktion, **daten}, follow_redirects=True)
        return r.text

    def test_eigene_loesung_komplett(self):
        A.speichere_config({"telegram_chat_id": "1"})
        a = self.admin()
        self.assertIn("angelegt", self.loesung(a, name="Drallklappen"))
        self.assertIn("Drallklappen", a.get("/admin/archiv").text)
        # Fahrzeug mit Stage 1 + Drallklappen anlegen
        neu = zufall(GROESSE, 21)
        st1, drall = bytearray(neu), bytearray(neu)
        st1[0x6000:0x6004] = bytes(4)
        drall[0x6100:0x6102] = b"\x01\x01"
        self.assertIn("Drallklappen", self.fahrzeug(a, "Audi_A6", neu, stage1=st1, drallklappen=drall))
        # Kunde sieht beide, waehlt Drallklappen
        aid = self.hochladen(neu)
        self.assertEqual(self.angebot(aid)["drallklappen"], "Drallklappen")
        self.bestellen(aid, "drallklappen")
        import time
        time.sleep(0.3)
        texte = [d["text"] for m, d in self.telegram if m == "sendMessage"]
        self.assertTrue(any("Neuer Auftrag: Drallklappen" in t for t in texte))
        A.entscheide(aid, True)
        self.assertEqual(self.laden(aid).data, bytes(drall))
        # Benutzte Loesung kann nicht geloescht werden
        self.assertIn("noch im Archiv benutzt", self.loesung(a, "loeschen", key="drallklappen"))

    def test_eigene_loesung_gesperrt_und_doppelt(self):
        a = self.admin()
        for name in ["DPF Off", "AGR aus", "AdBlue off", "Kat aus", "Lambda off"]:
            self.assertIn("nicht unterstützt", self.loesung(a, name=name), name)
        self.assertIn("gibt es schon", self.loesung(a, name="Stage 1"))
        self.assertIn("gibt es schon", self.loesung(a, name="Original"))
        self.loesung(a, name="Kickdown")
        self.assertIn("gibt es schon", self.loesung(a, name="kickdown"))
        self.assertIn("gelöscht", self.loesung(a, "loeschen", key="kickdown"))
        self.assertIn("Feste Lösungen", self.loesung(a, "loeschen", key="stage1"))
        self.assertEqual(set(oneclick.eigene_optionen()), set())

    def test_eigene_loesung_im_zip(self):
        a = self.admin()
        self.loesung(a, name="Drallklappen")
        neu = zufall(GROESSE, 22)
        drall = bytearray(neu)
        drall[0x7000] ^= 1
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as z:
            z.writestr("Golf8/Golf8_ORI.bin", bytes(neu))
            z.writestr("Golf8/Golf8_Drallklappen.bin", bytes(drall))
        puffer.seek(0)
        a.post("/admin/archiv/import", data={"csrf": a.csrf, "zip": (puffer, "f.zip")}, content_type="multipart/form-data")
        _, l = oneclick.finde_loesungen(bytes(neu))
        self.assertEqual(set(l), {"drallklappen"})

    def test_aufraeumen(self):
        alt = (datetime.now() - timedelta(days=100)).isoformat(timespec="seconds")
        entwurf = self.hochladen(self.golf)
        erledigt = self.hochladen(self.golf)
        self.bestellen(erledigt, "stage1")
        A.entscheide(erledigt, True)
        wartet = self.hochladen(self.golf)
        self.bestellen(wartet, "stage1")
        for aid in (entwurf, erledigt, wartet):
            a = self.auftrag(aid)
            a["zeit"] = alt
            A.speichere_auftrag(a)
        A.aufraeumen()
        self.assertFalse((A.AUFTRAEGE / entwurf).exists())
        self.assertFalse((A.AUFTRAEGE / erledigt).exists())
        self.assertTrue((A.AUFTRAEGE / wartet).exists())   # wartende nie loeschen


class ApiTests(Basis):
    """Schnittstelle fuer das Windows-Programm."""

    def setUp(self):
        super().setUp()
        self.c = A.app.test_client()   # ohne Cookies / CSRF, wie das Programm

    def pruefen(self, daten, name="kunde.bin"):
        return self.c.post("/api/pruefen", data={"datei": (io.BytesIO(bytes(daten)), name)},
                           content_type="multipart/form-data")

    def test_programm_link(self):
        self.assertIn("releases/download/programm/OneClick-Tuning.exe", A.app.test_client().get("/").text)
        A.speichere_config({"programm_url": ""})
        self.assertNotIn("Windows-Programm", A.app.test_client().get("/").text)

    def test_info(self):
        j = self.c.get("/api/info").json
        self.assertEqual(j["firma"], "OneClick Tuning")
        self.assertEqual(j["original"], "original")

    def test_ablauf(self):
        A.speichere_config({"telegram_chat_id": "1"})
        r = self.pruefen(self.golf)
        self.assertEqual(r.status_code, 200)
        j = r.json
        self.assertEqual(j["status"], "ENTWURF")
        self.assertEqual([o["key"] for o in j["angebot"]], ["stage1", "startstopp"])
        self.assertEqual(j["ecu"], "EDC17C46")
        aid = j["id"]
        self.assertEqual(self.c.get(f"/api/auftrag/{aid}/download").status_code, 403)
        r = self.c.post(f"/api/auftrag/{aid}/bestellen", json={"optionen": ["stage1", "startstopp"], "kontakt": "Werkstatt X"})
        self.assertEqual(r.json["status"], "WARTET")
        self.assertEqual(r.json["option_name"], "Stage 1 + Start/Stopp aus")
        self.assertEqual(self.c.get(f"/api/auftrag/{aid}/download").status_code, 403)
        A.entscheide(aid, True)
        self.assertEqual(self.c.get(f"/api/auftrag/{aid}").json["status"], "FREIGEGEBEN")
        d = self.c.get(f"/api/auftrag/{aid}/download")
        self.assertEqual(d.status_code, 200)
        erwartet = bytearray(self.stage1)
        erwartet[0x7000:0x7004] = self.startstopp[0x7000:0x7004]
        self.assertEqual(d.data, bytes(erwartet))

    def test_fehler(self):
        r = self.pruefen(zufall(GROESSE, 8))
        self.assertEqual(r.status_code, 422)
        self.assertIn("keine Lösung", r.json["fehler"])
        aid = self.pruefen(self.golf).json["id"]
        r = self.c.post(f"/api/auftrag/{aid}/bestellen", json={"optionen": ["vmax"]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.c.get("/api/auftrag/gibtsnicht").status_code, 404)

    def test_abgelehnt_mit_grund(self):
        aid = self.pruefen(self.bmw).json["id"]
        self.c.post(f"/api/auftrag/{aid}/bestellen", json={"optionen": ["stage1"]})
        A.entscheide(aid, False, grund="Software unbekannt")
        j = self.c.get(f"/api/auftrag/{aid}").json
        self.assertEqual((j["status"], j["grund"]), ("ABGELEHNT", "Software unbekannt"))


class ProgrammTests(Basis):
    """Bruecke des Windows-Programms (kunde/oneclick_kunde.py) gegen einen echten, laufenden Server."""

    def setUp(self):
        super().setUp()
        import threading
        from werkzeug.serving import make_server
        self.server = make_server("127.0.0.1", 0, A.app, threaded=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        os.environ["APPDATA"] = str(Path(self.tmp.name) / "appdata")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kunde"))
        import oneclick_kunde as K
        self.K = K
        speicher = K.Speicher()
        speicher.daten["server"] = f"http://127.0.0.1:{self.server.server_port}"
        self.b = K.Bruecke(speicher)

    def tearDown(self):
        self.server.shutdown()
        super().tearDown()

    def b64(self, daten):
        import base64
        return base64.b64encode(bytes(daten)).decode()

    def test_kompletter_ablauf(self):
        d = self.b.start()
        self.assertEqual((d["firma"], d["auftraege"]), ("OneClick Tuning", []))
        a = self.b.pruefen("golf.bin", self.b64(self.golf))
        self.assertEqual([o["key"] for o in a["angebot"]], ["stage1", "startstopp"])
        erg = self.b.bestellen(a["id"], ["stage1", "startstopp"], " Werkstatt X ")
        self.assertEqual(erg["auftrag"]["status"], "WARTET")
        self.assertEqual(len(erg["auftraege"]), 1)
        self.assertEqual(self.b.aktualisieren()["geaendert"], [])
        A.entscheide(a["id"], True)
        neu = self.b.aktualisieren()
        self.assertEqual([x["status"] for x in neu["geaendert"]], ["FREIGEGEBEN"])
        self.assertEqual(self.b.aktualisieren()["geaendert"], [])   # nur einmal melden
        ziel = Path(self.tmp.name) / "fertig.bin"
        self.assertEqual(self.b.herunterladen(a["id"], str(ziel)), {"pfad": str(ziel)})
        erwartet = bytearray(self.stage1)
        erwartet[0x7000:0x7004] = self.startstopp[0x7000:0x7004]
        self.assertEqual(ziel.read_bytes(), bytes(erwartet))
        # Gespeichert: neue Bruecke (= Programm neu gestartet) kennt Auftrag und Kontakt
        b2 = self.K.Bruecke()
        b2._api = self.b._api
        d2 = b2.start()
        self.assertEqual((d2["kontakt"], d2["auftraege"][0]["status"]), ("Werkstatt X", "FREIGEGEBEN"))
        self.assertEqual(self.b.entfernen(a["id"])["auftraege"], [])

    def test_fehler_kommen_als_text(self):
        self.assertIn("keine Lösung", self.b.pruefen("x.bin", self.b64(zufall(GROESSE, 5)))["fehler"])
        self.assertIn("nicht gelesen", self.b.pruefen("x.bin", "kein base64!!")["fehler"])
        a = self.b.pruefen("golf.bin", self.b64(self.golf))
        self.assertIn("fehler", self.b.bestellen(a["id"], ["vmax"], ""))
        self.assertIn("fehler", self.b.herunterladen("gibtsnicht", "x"))

    def freigegebener_auftrag(self):
        a = self.b.pruefen("golf.bin", self.b64(self.golf))
        self.b.bestellen(a["id"], ["stage1"], "")
        A.entscheide(a["id"], True)
        self.b.aktualisieren()
        return a["id"]

    def test_herunterladen_mit_speichern_dialog(self):
        """Der Fall 'Kunde klickt Herunterladen und nichts passiert' - inkl. aller Ausweichwege."""
        aid = self.freigegebener_auftrag()
        home = Path(self.tmp.name) / "home"
        (home / "Downloads").mkdir(parents=True)
        alt_home = os.environ.get("HOME")
        self.addCleanup(lambda: os.environ.__setitem__("HOME", alt_home) if alt_home else os.environ.pop("HOME", None))
        os.environ["HOME"] = str(home)
        aufrufe = []

        class Fenster:
            antwort = None

            def create_file_dialog(self, art, directory="", save_filename="", file_types=()):
                aufrufe.append((save_filename, file_types))
                if isinstance(self.antwort, Exception):
                    raise self.antwort
                return self.antwort
        self.b._fenster = f = Fenster()

        # Dialog: Kunde waehlt einen Ort
        f.antwort = str(home / "gewaehlt.bin")
        self.assertEqual(self.b.herunterladen(aid), {"pfad": f.antwort})
        self.assertEqual(Path(f.antwort).read_bytes(), self.stage1)
        self.assertEqual(aufrufe[0], ("golf_stage1.bin", self.K.DATEI_TYPEN))
        # Dialog abgebrochen
        f.antwort = None
        self.assertEqual(self.b.herunterladen(aid), {"abgebrochen": True})
        # Dialog geht kaputt -> landet trotzdem in Downloads (zweimal: nichts wird ueberschrieben)
        f.antwort = ValueError("kaputt")
        self.assertEqual(self.b.herunterladen(aid), {"pfad": str(home / "Downloads" / "golf_stage1.bin")})
        self.assertEqual(self.b.herunterladen(aid), {"pfad": str(home / "Downloads" / "golf_stage1 (2).bin")})
        # Gewaehlter Ordner nicht beschreibbar -> Downloads
        f.antwort = str(home / "gibtsnicht" / "x.bin")
        self.assertEqual(self.b.herunterladen(aid)["pfad"], str(home / "Downloads" / "golf_stage1 (3).bin"))
        # Unerwarteter Fehler -> Meldung statt "passiert nix", und steht im Fehlerprotokoll
        f.antwort = 12345
        self.assertIn("Unerwarteter Fehler", self.b.herunterladen(aid)["fehler"])
        self.assertIn("herunterladen", (self.K.datenordner() / "fehler.log").read_text(encoding="utf-8"))

    def test_dateifilter_passen_zu_pywebview(self):
        try:
            from webview.util import parse_file_type
        except Exception:
            self.skipTest("pywebview nicht installiert (wird beim Bauen im Selbsttest geprueft)")
        for typ in self.K.DATEI_TYPEN:
            parse_file_type(typ)
        self.assertEqual(self.K.dateiname_sauber('a:b?"c.bin'), "a_b__c.bin")

    def test_server_offline_und_wechseln(self):
        d = self.b.server_setzen("127.0.0.1:1")   # ohne http:// -> https://, nicht erreichbar
        self.assertTrue(d["server"].startswith("https://"))
        self.assertIn("Keine Verbindung", d["verbindung"])
        d = self.b.server_setzen(f"http://127.0.0.1:{self.server.server_port}/")
        self.assertNotIn("verbindung", d)


class ProgrammUpdateTests(unittest.TestCase):
    """Auto-Update des Windows-Programms (ohne echtes Windows: Dateien in einem Testordner)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPDATA"] = str(Path(self.tmp.name) / "appdata")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kunde"))
        import oneclick_kunde as K
        self.K = K
        self.exe = Path(self.tmp.name) / "OneClick-Tuning.exe"
        self.exe.write_bytes(b"ALTE VERSION")
        self.neu = random.Random(1).randbytes(2 * 1024 * 1024)
        import hashlib
        self.info = {"version": 7, "sha256": hashlib.sha256(self.neu).hexdigest(), "groesse": len(self.neu)}
        self.abrufe = []

    def tearDown(self):
        self.tmp.cleanup()

    def holen(self, url, timeout=0):
        self.abrufe.append(url.rsplit("/", 1)[1])
        return json.dumps(self.info).encode() if url.endswith("version.json") else self.neu

    def updater(self, eigene=5):
        return self.K.Updater("https://beispiel.test/programm", self.exe, self.holen, eigene)

    def test_neue_version_wird_erkannt(self):
        self.assertEqual(self.updater(5).pruefen()["version"], 7)
        self.assertIsNone(self.updater(7).pruefen())
        self.assertIsNone(self.updater(9).pruefen())

    def test_installieren_tauscht_exe(self):
        u = self.updater()
        u.installieren(u.pruefen())
        self.assertEqual(self.exe.read_bytes(), self.neu)
        self.assertEqual(u.alte_exe.read_bytes(), b"ALTE VERSION")
        u.aufraeumen()
        self.assertFalse(u.alte_exe.exists())

    def test_beschaedigter_download_wird_nicht_installiert(self):
        self.info["sha256"] = "0" * 64
        u = self.updater()
        with self.assertRaises(RuntimeError):
            u.installieren(u.pruefen())
        self.assertEqual(self.exe.read_bytes(), b"ALTE VERSION")

    def test_schreibfehler_stellt_alte_version_wieder_her(self):
        from unittest import mock
        u = self.updater()
        info = u.pruefen()
        with mock.patch.object(Path, "write_bytes", side_effect=PermissionError("schreibgeschuetzt")):
            with self.assertRaises(PermissionError):
                u.installieren(info)
        self.assertEqual(self.exe.read_bytes(), b"ALTE VERSION")
        self.assertFalse(u.alte_exe.exists())

    def test_bruecke(self):
        from unittest import mock
        b = self.K.Bruecke(updater=self.updater())
        b._beenden = lambda: None
        d = b.update_pruefen()
        self.assertEqual((d["neu"], d["version"]), (True, "2.7"))
        with mock.patch.object(self.K.Updater, "neu_starten") as start:
            self.assertEqual(b.update_installieren(), {"ok": True})
            start.assert_called_once()
        self.assertEqual(self.exe.read_bytes(), self.neu)
        # ohne Updater (Entwicklung / Selbsttest): nie updaten
        self.assertEqual(self.K.Bruecke().update_pruefen(), {"neu": False})

    def test_offline_kein_absturz(self):
        def offline(url, timeout=0):
            raise OSError("kein Internet")
        b = self.K.Bruecke(updater=self.K.Updater("https://x", self.exe, offline, 1))
        self.assertFalse(b.update_pruefen()["neu"])


class UpdateTests(unittest.TestCase):
    """Update-Knopf mit echten Git-Repositories in einem temporaeren Ordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.origin, self.server, self.entwickler = d / "origin.git", d / "server", d / "entwickler"
        self.git("init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git("clone", "-q", str(self.origin), str(self.entwickler))
        (self.entwickler / "requirements.txt").write_text("")
        (self.entwickler / ".gitignore").write_text("archiv/\n")
        (self.entwickler / "app.py").write_text("# Version 1\n")
        self.commit(self.entwickler, "Version 1")
        self.git("clone", "-q", str(self.origin), str(self.server))
        (self.server / "archiv").mkdir()
        (self.server / "archiv" / "kunde.bin").write_bytes(b"wichtig")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None):
        import subprocess
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                       capture_output=True)

    def commit(self, ordner, text):
        self.git("add", "-A", cwd=ordner)
        self.git("commit", "-q", "-m", text, cwd=ordner)
        self.git("push", "-q", "origin", "main", cwd=ordner)

    def test_update_finden_und_installieren(self):
        self.assertEqual(A.update_pruefen(self.server), [])
        (self.entwickler / "app.py").write_text("# Version 2\n")
        self.commit(self.entwickler, "Neue Funktion")
        neu = A.update_pruefen(self.server)
        self.assertEqual([titel for _, titel in neu], ["Neue Funktion"])
        A.update_installieren(self.server)
        self.assertEqual((self.server / "app.py").read_text(), "# Version 2\n")
        self.assertEqual(A.version(self.server)["titel"], "Neue Funktion")
        self.assertEqual(A.update_pruefen(self.server), [])
        self.assertEqual((self.server / "archiv" / "kunde.bin").read_bytes(), b"wichtig")   # Daten bleiben

    def test_ohne_git_keine_version(self):
        self.assertEqual(A.version(Path(self.tmp.name)), {})


if __name__ == "__main__":
    unittest.main()
