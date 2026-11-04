"""Tests fuer die Mac-App "OneClick Admin" (ohne Fenster - das testet der Build auf dem Mac)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "admin_app"))
import oneclick_admin as O   # noqa: E402


class AdminAppTests(unittest.TestCase):
    def test_kennung(self):
        self.assertIn("OneClickAdmin/", O.USER_AGENT)          # Server zeigt daran das App-Design
        self.assertNotIn("OneClickProgramm/", O.USER_AGENT)    # nicht mit dem Kundenprogramm verwechseln

    def test_mitteilungstext_sicher(self):
        # Anfuehrungszeichen/Backslashes duerfen das AppleScript nicht aufbrechen
        self.assertEqual(O.applescript_text('Ticket "#1"\\x'), 'Ticket \\"#1\\"\\\\x')
        self.assertEqual(O.applescript_text("a\nb"), "a b")
        self.assertEqual(len(O.applescript_text("x" * 999)), 200)


if __name__ == "__main__":
    unittest.main()
