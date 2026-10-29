"""
Automatische Tests. Ausfuehren im Projektordner:

    python -m unittest discover tests

Arbeiten komplett in einem temporaeren Ordner, echte Daten werden nicht angefasst.
"""

import io
import json
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

    def hochladen(self, daten, name="kunde.bin"):
        r = self.kunde.post("/pruefen", data={"csrf": self.kunde.csrf, "datei": (io.BytesIO(bytes(daten)), name)},
                            content_type="multipart/form-data")
        ort = r.headers.get("Location", "")
        return ort.rsplit("/", 1)[1] if "/auftrag/" in ort else None

    def auftrag(self, aid):
        return json.loads((A.AUFTRAEGE / aid / "auftrag.json").read_text())

    def test_ablauf_komplett(self):
        aid = self.hochladen(self.golf)
        seite = self.kunde.get(f"/auftrag/{aid}").text
        self.assertIn('value="stage1"', seite)
        self.assertIn('value="startstopp"', seite)
        self.assertNotIn('value="vmax"', seite)
        self.assertEqual(self.kunde.get(f"/auftrag/{aid}/download").status_code, 403)
        self.assertEqual(self.telegram, [])   # Meldung erst nach dem Bestellen

        self.kunde.post(f"/auftrag/{aid}/bestellen", data={"csrf": self.kunde.csrf, "option": "startstopp"})
        self.assertEqual(self.auftrag(aid)["status"], "WARTET")
        self.assertEqual(self.kunde.get(f"/auftrag/{aid}/download").status_code, 403)

        A.entscheide(aid, True, wer="test")
        d = self.kunde.get(f"/auftrag/{aid}/download")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.data, bytes(self.startstopp))

    def test_bmw_nur_stage1(self):
        aid = self.hochladen(self.bmw)
        seite = self.kunde.get(f"/auftrag/{aid}").text
        self.assertIn('value="stage1"', seite)
        self.assertNotIn('value="startstopp"', seite)

    def test_nicht_angebotene_option_abgelehnt(self):
        aid = self.hochladen(self.bmw)
        self.kunde.post(f"/auftrag/{aid}/bestellen", data={"csrf": self.kunde.csrf, "option": "startstopp"})
        self.assertEqual(self.auftrag(aid)["status"], "ENTWURF")

    def test_kein_treffer_kein_auftrag(self):
        self.assertIsNone(self.hochladen(zufall(GROESSE, 7)))
        self.assertEqual(list(A.AUFTRAEGE.iterdir()), [])

    def test_ablehnen_mit_grund(self):
        aid = self.hochladen(self.golf)
        self.kunde.post(f"/auftrag/{aid}/bestellen", data={"csrf": self.kunde.csrf, "option": "stage1"})
        a = self.admin()
        a.post(f"/admin/auftrag/{aid}/entscheiden", data={"csrf": a.csrf, "aktion": "nein", "grund": "Test-Grund"})
        self.assertIn("Test-Grund", self.kunde.get(f"/auftrag/{aid}").text)
        self.assertEqual(self.kunde.get(f"/auftrag/{aid}/download").status_code, 403)

    def test_doppelte_entscheidung_aendert_nichts(self):
        aid = self.hochladen(self.golf)
        self.kunde.post(f"/auftrag/{aid}/bestellen", data={"csrf": self.kunde.csrf, "option": "stage1"})
        self.assertEqual(A.entscheide(aid, True, wer="x"), "Freigegeben.")
        self.assertIn("schon", A.entscheide(aid, False, wer="x"))

    def test_admin_seiten_geschuetzt(self):
        for pfad in ["/admin", "/admin/archiv", "/admin/einstellungen"]:
            self.assertEqual(self.kunde.get(pfad).status_code, 302, pfad)
        a = self.admin()
        for pfad in ["/admin", "/admin/archiv", "/admin/einstellungen"]:
            self.assertEqual(a.get(pfad).status_code, 200, pfad)

    def test_csrf(self):
        self.assertEqual(A.app.test_client().post("/pruefen").status_code, 400)

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
        self.assertIn('value="stage1"', self.kunde.get(f"/auftrag/{aid}").text)

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
        self.assertIn("mindestens ein Tuning-File", self.fahrzeug(a, "Neu", anders))
        self.assertFalse((oneclick.ARCHIV / "Neu").exists())

    def test_aufraeumen(self):
        alt = (datetime.now() - timedelta(days=100)).isoformat(timespec="seconds")
        entwurf = self.hochladen(self.golf)
        erledigt = self.hochladen(self.golf)
        self.kunde.post(f"/auftrag/{erledigt}/bestellen", data={"csrf": self.kunde.csrf, "option": "stage1"})
        A.entscheide(erledigt, True)
        wartet = self.hochladen(self.golf)
        self.kunde.post(f"/auftrag/{wartet}/bestellen", data={"csrf": self.kunde.csrf, "option": "stage1"})
        for aid in (entwurf, erledigt, wartet):
            a = self.auftrag(aid)
            a["zeit"] = alt
            A.speichere_auftrag(a)
        A.aufraeumen()
        self.assertFalse((A.AUFTRAEGE / entwurf).exists())
        self.assertFalse((A.AUFTRAEGE / erledigt).exists())
        self.assertTrue((A.AUFTRAEGE / wartet).exists())   # wartende nie loeschen


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
