"""Tests fuer das Programm (ohne Fenster - das testen die Builds auf Windows und Mac)."""
import hashlib
import json
import sys
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
import oneclick_programm as P   # noqa: E402


class ProgrammTests(unittest.TestCase):
    def test_dateiname_aus_kopf(self):
        self.assertEqual(P.dateiname_aus('attachment; filename="Golf_stage1.bin"'), "Golf_stage1.bin")
        self.assertEqual(P.dateiname_aus("attachment; filename*=UTF-8''G%C3%B6lf%20st1.bin"), "Gölf st1.bin")
        self.assertEqual(P.dateiname_aus('attachment; filename="../../Windows/evil.bin"'), "evil.bin")
        self.assertEqual(P.dateiname_aus('attachment; filename="a:b*?.bin"'), "a_b_.bin")
        self.assertEqual(P.dateiname_aus(""), "file.bin")

    def test_name_und_kennung(self):
        self.assertEqual(P.PROGRAMM_NAME, "OneClick Solutions")
        self.assertEqual(P.EXE_NAME, "OneClick-Solutions.exe")
        self.assertIn("OneClickProgramm/", P.USER_AGENT)   # sonst laesst der Server das Programm nicht rein

    def test_update_knopf_ohne_exe(self):
        b = P.Bruecke()
        self.assertEqual(b.update_pruefen(), {"version": P.VERSION, "neu": None})   # Entwicklungsstand: kein Programm-Update
        self.assertIn("fehler", b.update_installieren())

    def test_speichern_nur_eigener_server(self):
        b = P.Bruecke()
        self.assertIn("fehler", b.speichern("https://boese.example/api/auftrag/x/download"))
        self.assertIn("fehler", b.speichern(P.SERVER + "/admin/archiv.zip"))

    def test_update(self):
        neu = b"MZ" + b"x" * (2 * 1024 * 1024)
        info = {"version": 7, "sha256": hashlib.sha256(neu).hexdigest(), "groesse": len(neu)}
        abrufe = []

        def holen(url, timeout=0):
            abrufe.append(url)
            return json.dumps(info).encode() if "version.json" in url else neu

        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "OneClick-Tuning.exe"
            exe.write_bytes(b"alt")
            self.assertIsNone(P.Updater(exe=exe, holen=holen, eigene=7).pruefen())   # aktuell
            u = P.Updater(exe=exe, holen=holen, eigene=6)
            self.assertEqual(u.pruefen()["version"], 7)
            u.installieren(info)
            self.assertEqual(exe.read_bytes(), neu)
            self.assertEqual(u.alte_exe.read_bytes(), b"alt")
            u.aufraeumen()
            self.assertFalse(u.alte_exe.exists())
            kaputt = dict(info, sha256="0" * 64)
            exe.write_bytes(b"alt")
            with self.assertRaises(RuntimeError):
                u.installieren(kaputt)
            self.assertEqual(exe.read_bytes(), b"alt")   # alte Version bleibt


    def test_mac_update(self):
        def app_zip(inhalt: bytes) -> bytes:
            puffer = io.BytesIO()
            with zipfile.ZipFile(puffer, "w") as z:
                z.writestr("OneClick Solutions.app/Contents/MacOS/OneClick-Solutions", inhalt)
                z.writestr("OneClick Solutions.app/Contents/Info.plist", "<plist/>")
                z.writestr("OneClick Solutions.app/Contents/Resources/gross.bin", b"x" * (2 * 1024 * 1024))
            return puffer.getvalue()

        neu = app_zip(b"NEU")
        info = {"version": 9, "sha256": hashlib.sha256(neu).hexdigest(), "groesse": len(neu)}
        abrufe = []

        def holen(url, timeout=0):
            abrufe.append(url)
            return json.dumps(info).encode() if P.MAC_VERSION in url else neu

        with tempfile.TemporaryDirectory() as d:
            app = Path(d) / "OneClick Solutions.app"
            (app / "Contents" / "MacOS").mkdir(parents=True)
            programm = app / "Contents" / "MacOS" / "OneClick-Solutions"
            programm.write_bytes(b"ALT")
            u = P.MacUpdater(app=app, holen=holen, eigene=8)
            self.assertEqual(u.pruefen()["version"], 9)
            self.assertTrue(abrufe[0].split("?")[0].endswith("/version-mac.json"))   # eigene Versionsdatei fuer den Mac
            u.installieren(info)
            self.assertTrue(abrufe[-1].endswith("/OneClick-Solutions-Mac.zip"))
            self.assertEqual(programm.read_bytes(), b"NEU")
            self.assertEqual((u.alte_app / "Contents" / "MacOS" / "OneClick-Solutions").read_bytes(), b"ALT")
            self.assertFalse((Path(d) / ".oneclick-update").exists())   # Zwischenordner aufgeraeumt
            u.aufraeumen()
            self.assertFalse(u.alte_app.exists())
            # beschaedigter Download: alte Version bleibt
            with self.assertRaises(RuntimeError):
                u.installieren(dict(info, sha256="0" * 64))
            self.assertEqual(programm.read_bytes(), b"NEU")
            # direkt aus "Downloads" gestartet (macOS verschiebt es dann in einen Schreibschutz-Ordner): klare Meldung
            fremd = P.MacUpdater(app=Path(d) / "AppTranslocation" / "x" / "OneClick Solutions.app", holen=holen, eigene=8)
            fremd.app = Path("/private/var/folders/AppTranslocation/ABC/d/OneClick Solutions.app")
            with self.assertRaises(RuntimeError) as e:
                fremd.installieren(info)
            self.assertIn("Programme", str(e.exception))

    def test_plattform(self):
        self.assertEqual(P.Bruecke().plattform(), "mac" if P.MAC else "windows")
        self.assertIn("Macintosh" if P.MAC else "Windows", P.USER_AGENT)


if __name__ == "__main__":
    unittest.main()
