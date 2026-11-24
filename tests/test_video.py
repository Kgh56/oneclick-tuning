"""Tests fuer den Video-Bereich (Claude schneidet Videos). Alles in temporaeren Ordnern."""

import os
import re
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as A   # noqa: E402
from test_oneclick import Basis   # noqa: E402


class VideoTests(Basis):
    def setUp(self):
        super().setUp()
        self.alt = (A.VIDEOS, A.VIDEO_TEIL, A.VIDEO_RESERVE)
        A.VIDEOS = Path(self.tmp.name) / "videos"
        A.VIDEO_TEIL, A.VIDEO_RESERVE = 1000, 0
        self.admin = self.anmelden()

    def tearDown(self):
        A.VIDEOS, A.VIDEO_TEIL, A.VIDEO_RESERVE = self.alt
        super().tearDown()

    def anmelden(self):
        c = A.app.test_client()
        c.get("/")
        with c.session_transaction() as s:
            c.csrf = s["csrf"]
        c.post("/login", data={"name": "chef", "pw": "Geheim123", "csrf": c.csrf})
        with c.session_transaction() as s:
            c.csrf = s["csrf"]
        return c

    def schluessel(self) -> str:
        r = self.admin.post("/admin/video/schluessel", data={"csrf": self.admin.csrf, "aktion": "neu"})
        return re.search(r"video_[A-Za-z0-9_-]{20,}", r.get_data(as_text=True)).group(0)

    def claude(self, schluessel):
        c = A.app.test_client()
        c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {schluessel}"
        return c

    @staticmethod
    def laden(c, url) -> bytes:
        r = c.get(url)
        daten = r.data
        r.close()
        return daten

    def neu(self, clips, wunsch="Actionfilm"):
        import json
        return self.admin.post("/admin/video/neu", data={"csrf": self.admin.csrf, "wunsch": wunsch,
                                                         "dateien": json.dumps(clips)})

    def stueck(self, vid, nr, start, daten):
        import io
        return self.admin.post(f"/admin/video/{vid}/clip/{nr}", content_type="multipart/form-data",
                               data={"csrf": self.admin.csrf, "start": str(start), "teil": (io.BytesIO(daten), "teil")})

    def hochladen(self, vid, nr, daten, ab=0):
        for start in range(ab, len(daten), A.VIDEO_TEIL):
            r = self.stueck(vid, nr, start, daten[start:start + A.VIDEO_TEIL])
            self.assertEqual(r.status_code, 200, r.json)
        return r

    def abgeben(self, c, vid, daten, name="actionfilm.mp4"):
        for start in range(0, len(daten), A.VIDEO_TEIL):
            r = c.post(f"/api/video/{vid}/ergebnis?start={start}&gesamt={len(daten)}&name={name}",
                       data=daten[start:start + A.VIDEO_TEIL], content_type="application/octet-stream")
            self.assertEqual(r.status_code, 200, r.json)
        return r

    def test_ganzer_ablauf(self):
        clip1, clip2 = os.urandom(2500), os.urandom(1500)
        # Reihenfolge so, wie die Seite sie schickt (nach Namen sortiert)
        auswahl = [{"name": "DJI_0001.MP4", "groesse": len(clip1)}, {"name": "DJI_0002.MP4", "groesse": len(clip2)}]
        r = self.neu(auswahl)
        self.assertEqual(r.status_code, 200)
        vid = r.json["id"]
        self.assertEqual(self.stueck(vid, 1, 0, clip1[:1000]).json["start"], 1000)
        # Falscher Startpunkt: nichts wird angehaengt, Antwort nennt den richtigen
        r = self.stueck(vid, 1, 0, clip1[:1000])
        self.assertEqual((r.status_code, r.json["start"]), (409, 1000))
        # Upload abgebrochen, dieselben Videos nochmal gewaehlt: es geht weiter
        r = self.neu(auswahl, wunsch="")
        self.assertEqual((r.json["id"], r.json["weiter"], r.json["clips"][0]["start"]), (vid, True, 1000))
        self.assertEqual(A.video_info(vid)["wunsch"], "Actionfilm")   # leerer Wunsch ueberschreibt nichts
        self.hochladen(vid, 1, clip1, ab=1000)
        self.assertEqual(A.video_info(vid)["status"], "upload")
        self.hochladen(vid, 2, clip2)
        self.assertEqual(A.video_info(vid)["status"], "wartet")
        self.assertEqual((A.VIDEOS / vid / "clip_1.mp4").read_bytes(), clip1)

        # Claude: ohne Schluessel kein Zugriff, auch nicht als angemeldeter Admin ohne Schluessel
        self.assertEqual(A.app.test_client().get("/api/video").status_code, 401)
        self.assertEqual(self.claude("video_falsch").get("/api/video").status_code, 401)
        claude = self.claude(self.schluessel())
        liste = claude.get("/api/video").json["videos"]
        self.assertEqual([(v["id"], v["status"], v["wunsch"]) for v in liste], [(vid, "wartet", "Actionfilm")])
        self.assertEqual([c["name"] for c in liste[0]["clips"]], ["DJI_0001.MP4", "DJI_0002.MP4"])
        self.assertEqual(self.laden(claude, f"/api/video/{vid}/clip/2"), clip2)
        self.assertEqual(A.video_info(vid)["status"], "arbeit")

        film = os.urandom(3300)
        self.telegram.clear()
        A.speichere_config({"telegram_chat_id": "1", "basis_url": "https://test.example"})
        r = self.abgeben(claude, vid, film)
        self.assertTrue(r.json["fertig"])
        self.assertEqual(A.video_info(vid)["status"], "fertig")
        for _ in range(50):   # Telegram laeuft im Hintergrund
            if self.telegram:
                break
            time.sleep(0.02)
        self.assertIn("https://test.example/admin/video", self.telegram[0][1]["text"])
        self.assertNotIn("DJI", self.telegram[0][1]["text"])   # keine Dateinamen an Telegram

        seite = self.admin.get("/admin/video").get_data(as_text=True)
        self.assertIn("Fertiges Video herunterladen", seite)
        link = re.search(r'href="(/admin/video/[0-9a-f]{32}/ergebnis\?dl=[^"]+)"', seite).group(1)
        self.assertIsNone(A.video_info(vid).get("abgeholt"))
        d = self.admin.get(link)
        self.assertEqual(d.data, film)
        self.assertIn("actionfilm.mp4", d.headers["Content-Disposition"])
        d.close()
        abgeholt = A.video_info(vid)["abgeholt"]
        # Mac-Admin-App laedt ohne Cookie, nur mit dem signierten Link
        self.assertEqual(self.laden(A.app.test_client(), link), film)

        # Neue Version im selben Vorgang (z. B. "mehr Zeitlupe"): wieder herunterladbar, Frist beginnt neu
        film2 = os.urandom(1200)
        self.abgeben(claude, vid, film2, name="actionfilm_v2.mp4")
        self.assertIsNone(A.video_info(vid).get("abgeholt"))
        self.assertEqual(self.laden(self.admin, f"/admin/video/{vid}/ergebnis"), film2)
        self.assertEqual(sorted(p.name for p in (A.VIDEOS / vid).iterdir()),
                         ["clip_1.mp4", "clip_2.mp4", "ergebnis.mp4", "info.json"])

        # 1 Stunde nach dem Herunterladen automatisch weg
        abgeholt = A.video_info(vid)["abgeholt"]
        self.assertEqual(A.videos_aufraeumen(jetzt=abgeholt + 3500), 0)
        self.assertEqual(A.videos_aufraeumen(jetzt=abgeholt + 3700), 1)
        self.assertFalse((A.VIDEOS / vid).exists())
        self.assertEqual(claude.get("/api/video").json["videos"], [])
        # Neue Version, obwohl der alte Vorgang weg ist
        neu = claude.post("/api/video/neu", json={"wunsch": "Version 3"}).json
        self.assertEqual(neu["status"], "arbeit")
        self.abgeben(claude, neu["id"], film)
        self.assertEqual(self.laden(self.admin, f"/admin/video/{neu['id']}/ergebnis"), film)

    def test_fristen(self):
        r = self.neu([{"name": "a.mov", "groesse": 10}])
        haengt = r.json["id"]
        r = self.neu([{"name": "b.mp4", "groesse": 10}])
        wartet = r.json["id"]
        self.hochladen(wartet, 1, b"0123456789")
        jetzt = time.time()
        self.assertEqual(A.videos_aufraeumen(jetzt=jetzt + 23 * 3600), 0)
        self.assertEqual(A.videos_aufraeumen(jetzt=jetzt + 25 * 3600), 1)   # Upload haengt seit 24 h
        self.assertFalse((A.VIDEOS / haengt).exists())
        self.assertTrue((A.VIDEOS / wartet / "clip_1.mp4").exists())
        self.assertEqual(A.videos_aufraeumen(jetzt=jetzt + 71 * 3600), 0)
        self.assertEqual(A.videos_aufraeumen(jetzt=jetzt + 73 * 3600), 1)   # spaetestens nach 3 Tagen
        self.assertEqual(list(A.VIDEOS.iterdir()), [])

    def test_loeschen_nur_im_videoordner(self):
        """Das automatische Loeschen darf nie etwas ausserhalb von videos/ treffen (CLAUDE.md)."""
        tmp = Path(self.tmp.name)
        archiv_datei = next(p for p in Path(A.oneclick.ARCHIV).rglob("*") if p.is_file())
        archiv_vorher = archiv_datei.read_bytes()
        (tmp / "sicherungen").mkdir(exist_ok=True)
        (tmp / "sicherungen" / "stand.zip").write_bytes(b"sicherung")
        r = self.neu([{"name": "a.mp4", "groesse": 5}])
        self.hochladen(r.json["id"], 1, b"abcde")
        # Fremdes in videos/: ein Ordner mit anderem Namen, eine Datei und ein Link mit gueltigem Namen aufs Archiv
        (A.VIDEOS / "fremd").mkdir()
        (A.VIDEOS / "fremd" / "x.txt").write_text("bleibt")
        (A.VIDEOS / "notiz.txt").write_text("bleibt")
        link = A.VIDEOS / ("b" * 32)
        link.symlink_to(A.oneclick.ARCHIV, target_is_directory=True)
        alt = time.time() - 10 * 86400
        for p in (A.VIDEOS / "fremd", A.VIDEOS / "notiz.txt"):
            os.utime(p, (alt, alt))

        self.assertEqual(A.videos_aufraeumen(jetzt=time.time() + 30 * 86400), 1)
        self.assertEqual(archiv_datei.read_bytes(), archiv_vorher)
        self.assertEqual((tmp / "sicherungen" / "stand.zip").read_bytes(), b"sicherung")
        self.assertEqual((A.VIDEOS / "fremd" / "x.txt").read_text(), "bleibt")
        self.assertEqual((A.VIDEOS / "notiz.txt").read_text(), "bleibt")
        self.assertTrue(link.is_symlink())
        for falsch in ("../archiv", "", "b" * 32, "..", str(A.oneclick.ARCHIV)):
            with self.assertRaises(ValueError):
                A.video_loeschen(falsch)
        self.assertEqual(archiv_datei.read_bytes(), archiv_vorher)
        # Ordner ohne info.json (z. B. halb angelegt) mit gueltigem Namen: nach 24 h weg
        halb = A.VIDEOS / ("c" * 32)
        halb.mkdir()
        self.assertEqual(A.videos_aufraeumen(), 0)
        os.utime(halb, (alt, alt))
        self.assertEqual(A.videos_aufraeumen(), 1)

    def test_admin_knopf_loeschen(self):
        vid = self.neu([{"name": "a.mp4", "groesse": 5}]).json["id"]
        self.assertEqual(self.admin.post(f"/admin/video/{vid}/loeschen", data={}).status_code, 400)   # ohne CSRF
        self.assertTrue((A.VIDEOS / vid).exists())
        self.admin.post(f"/admin/video/{vid}/loeschen", data={"csrf": self.admin.csrf})
        self.assertFalse((A.VIDEOS / vid).exists())

    def test_platz_und_grenzen(self):
        A.VIDEO_RESERVE = 10 ** 18
        r = self.neu([{"name": "a.mp4", "groesse": 100}])
        self.assertEqual(r.status_code, 507)
        self.assertFalse(A.VIDEOS.exists() and any(A.VIDEOS.iterdir()))
        A.VIDEO_RESERVE = 0
        self.assertEqual(self.neu([]).status_code, 400)
        self.assertEqual(self.neu([{"name": "a.mp4", "groesse": 0}]).status_code, 400)
        self.assertEqual(self.neu([{"name": "a.mp4", "groesse": A.VIDEO_MAX + 1}]).status_code, 400)
        vid = self.neu([{"name": "../../archiv/x.mp4", "groesse": 1500}]).json["id"]
        self.assertEqual(A.video_info(vid)["clips"][0]["name"], "x.mp4")
        self.assertEqual(self.stueck(vid, 1, 0, b"x" * (A.VIDEO_TEIL + 1)).status_code, 400)   # Stueck zu gross
        self.assertEqual(self.stueck(vid, 1, 0, b"x" * 1000).status_code, 200)
        self.assertEqual(self.stueck(vid, 1, 1000, b"x" * 600).status_code, 400)   # ueber die Dateigroesse hinaus
        self.assertEqual(self.stueck(vid, 9, 0, b"x").status_code, 404)

    def test_zugang(self):
        self.assertEqual(A.app.test_client().get("/admin/video").status_code, 302)
        self.assertEqual(A.app.test_client().post("/admin/video/neu").status_code, 400)   # ohne CSRF/Anmeldung
        s1 = self.schluessel()
        self.assertNotIn(s1, str(A.lade_config()))   # gespeichert wird nur der Hash
        self.assertEqual(self.claude(s1).get("/api/video").status_code, 200)
        s2 = self.schluessel()
        self.assertEqual(self.claude(s1).get("/api/video").status_code, 401)   # alter Schluessel gilt nicht mehr
        self.assertEqual(self.claude(s2).get("/api/video").status_code, 200)
        self.admin.post("/admin/video/schluessel", data={"csrf": self.admin.csrf, "aktion": "aus"})
        self.assertEqual(self.claude(s2).get("/api/video").status_code, 401)
        self.assertEqual(self.claude("").get("/api/video").status_code, 401)   # gesperrt: auch leer nicht
        for _ in range(20):
            self.claude("video_raten").get("/api/video")
        self.assertEqual(self.claude("video_raten").get("/api/video").status_code, 429)
        # Die Kunden-Schnittstelle bleibt fuer Browser gesperrt
        self.assertEqual(self.claude(s2).get("/api/info", headers={"User-Agent": "Mozilla/5.0"}).status_code, 403)

    def test_seite_und_daten_geschuetzt(self):
        self.assertEqual(self.admin.get("/admin/video").status_code, 200)
        self.assertIn("videos", A.GESCHUETZTE_DATEN)
        gitignore = (Path(A.__file__).parent / ".gitignore").read_text().split()
        self.assertIn("videos/", gitignore)


if __name__ == "__main__":
    unittest.main()
