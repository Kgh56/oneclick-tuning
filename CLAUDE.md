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
