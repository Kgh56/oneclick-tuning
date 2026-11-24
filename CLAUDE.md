# Regeln für dieses Projekt (OneClick Solutions / GH-MAPPING)

## Oberste Regel: Daten auf dem Server niemals löschen

Die Files auf dem Server (Archiv mit Original- und Stage-Files usw.) dürfen **niemals** gelöscht, überschrieben
oder verändert werden – egal was passiert. Löschen darf nur die Inhaberin selbst, über die Knöpfe im Admin-Bereich.

Das heißt für jede Arbeit an diesem Projekt:

- Keine Befehle auf dem Server ausführen oder vorschlagen, die Daten löschen oder überschreiben
  (`rm`, `git clean`, Ordner ersetzen, Archiv neu aufbauen o. Ä.) – auch nicht „zum Aufräumen“ oder „zum Testen“.
- Keinen Code einbauen, der Dateien im Archiv (`archiv/`) oder in `sicherungen/` automatisch löscht.
  Löschen im Archiv nur auf ausdrücklichen Knopfdruck im Admin (mit Bestätigung).
- Datendateien und -ordner nie ins Repository aufnehmen (siehe `.gitignore` und `GESCHUETZTE_DATEN` in `app.py`).
  Das Update bricht ab, falls doch einmal eine Datendatei im Repository liegt – diese Sicherung nicht entfernen.
- Tests nur mit temporären Testordnern, nie mit echten Server-Daten.

## Einzige Ausnahme: Video-Zwischenlager `videos/`

Auf ausdrücklichen Wunsch der Inhaberin (24.11.2026) gibt es im Admin den Bereich „Video“: Sie lädt Clips hoch, Claude
schneidet sie und legt das fertige Video wieder ab. Damit der Server nicht voll läuft, leert der Server `videos/`
**selbst und automatisch**: 1 Stunde nach dem Herunterladen des fertigen Videos, spätestens nach 3 Tagen, abgebrochene
Uploads nach 24 Stunden.

- Die Ausnahme gilt **nur** für Vorgangsordner direkt in `videos/` (32 Hex-Zeichen, kein Link). `video_loeschen` in
  `app.py` prüft das; diese Prüfung und ihre Tests (`tests/test_video.py`) nicht lockern.
- Alle anderen Regeln oben gelten unverändert. Claude löscht auch in `videos/` nichts von Hand; die Schnittstelle hat
  keinen Löschbefehl.
- Zugriff für Claude: Schlüssel aus Admin → Video → „Zugang für Claude“, als Netzwerk-Secret der Claude-Umgebung
  (`Authorization: Bearer …`, nie in den Chat). Werkzeug: `werkzeuge/video.py` (`liste`, `holen <id> <ordner>`,
  `abgeben <id|neu> <datei>`). Clips und Zwischenstände nur im Scratchpad, nie ins Repository.
