# OneClick Tuning

Kunden laden ihr Original hoch. Die Seite liefert **nur bei einem 100-%-Treffer** in eurem Archiv
und zeigt **nur die Optionen, die es für diesen Treffer gibt** (liegt im Ordner nur Stage 1, gibt es nur Stage 1).
Ohne Treffer entsteht kein Auftrag. Herunterladen kann der Kunde erst nach eurer Freigabe (Telegram oder Admin-Bereich).
**Checksummen werden nicht korrigiert** (Flash-Tool / WinOLS).

## Was ist ein 100-%-Treffer?
1. **Original identisch:** Das File ist Byte für Byte gleich wie ein Original im Archiv.
2. **Alle Tuning-Stellen identisch:** Gleiche Dateigröße, gleiche Software-/Teilenummer (falls lesbar), und an
   **jeder** Stelle, die euer Tuning ändert (plus 16 Bytes davor und danach), steht exakt dasselbe wie im
   Archiv-Original – an derselben Adresse. Es wird nichts gesucht oder verschoben. Unterschiede gibt es dann nur
   an Stellen, die das Tuning gar nicht anfasst (z. B. Fahrgestellnummer); die bleiben vom Kunden-File erhalten.

Wer nur Variante 1 will: Admin-Bereich → Einstellungen → „Nur komplett identische Originale“.

## Mehrere Lösungen auf einmal
Der Kunde kann mehrere angebotene Lösungen ankreuzen (z. B. Stage 1 + Start/Stopp + Pops & Bangs) und bekommt
**ein** File mit allen Änderungen. Jede Lösung ist für sich zu 100 % geprüft. Ändern zwei Lösungen dieselbe Stelle
unterschiedlich, lehnt die Seite die Kombination ab („nicht möglich“) – einzeln geht dann weiterhin.
„Original (Rückrüsten)“ ist nie kombinierbar. Kombinationen werden nicht ins Archiv gelernt.

## Original zurück (Rückrüsten)
Lädt ein Kunde ein **getuntes** File hoch, das nach denselben 100-%-Regeln zu einem Tuning-File im Archiv passt,
wird ihm **„Original (Rückrüsten)“** angeboten. Nach deiner Freigabe bekommt er das Original: bei identischem File
dein Archiv-Original, sonst sein File mit den Original-Werten an allen Tuning-Stellen (z. B. FIN bleibt seine).
Dafür musst du nichts extra hochladen – Original und Tuning-File im Archiv reichen.

**Nur ein Original im Archiv (ohne Tuning-File):** Lädt ein Kunde ein *fremdes* Tuning-File hoch, wird
„Original (Rückrüsten)“ auch dann angeboten, wenn gleiche Dateigröße, **gleiche Bosch-Softwarenummer** (muss lesbar
sein), passende Teile-/Hardwarenummer und höchstens 5 % abweichende Bytes vorliegen. Der Kunde bekommt dann dein
Archiv-Original. Das ist **kein** Byte-für-Byte-Nachweis: In Telegram und im Admin-Bereich steht deshalb
„⚠️ Treffer über Softwarenummer – bitte prüfen“. Mit „Nur komplett identische Originale“ ist dieser Weg aus.

## Archiv – neue Files hochladen
Im Admin-Bereich unter **Archiv**:
- **Neues Fahrzeug hinzufügen:** Name eintragen, Original und Tuning-File(s) auswählen (Stage 1, Stage 2,
  Start/Stopp, Vmax, Pops & Bangs, Launch – was es gibt) → Speichern. Ab sofort bekommen Kunden mit diesem
  Original einen Treffer.
- **Option nachreichen:** einen vorhandenen Namen wählen, dasselbe Original und nur die neue Option auswählen
  → die bisherigen Optionen bleiben erhalten.
- **Viele auf einmal:** ZIP mit einem Ordner pro Fahrzeug hochladen.
- **Eigene Lösungen** (z. B. Drallklappen, Abgasklappe, Kickdown, Hardcut): auf der Archiv-Seite unter „Lösungen“
  anlegen. Sie erscheinen dann beim Fahrzeug-Formular und werden beim ZIP-Import am Dateinamen erkannt
  (`Golf7_Drallklappen.bin`). Abschaltungen der Abgasreinigung (DPF, AGR, AdBlue/SCR, Kat, Lambda) werden nicht unterstützt.

Aufbau im Archiv-Ordner auf dem Server:

```
archiv/
  golf7_20tdi_03L906018JL/
    Golf7_ORI.bin
    Golf7_Stage1.bin
    Golf7_StartStop.bin   (optional, weitere Optionen)
```

Erkannt werden Namen mit „ori/original“ bzw. „stage1/st1“, „stage2“, „startstop“, „vmax“, „pops“, „launch“.
Liegen genau zwei Dateien im Ordner und eine ist das Original, gilt die andere als Stage 1.
Original und Tuning-File müssen gleich groß sein (gleiche Leseart).

## Kommandozeile (optional)
```
python oneclick.py index                 # Archiv einlesen
python oneclick.py info    kunde.bin     # ECU / Softwarenummern anzeigen
python oneclick.py pruefen kunde.bin     # 100-%-Treffer suchen, Files für alle gefundenen Optionen erzeugen
python oneclick.py lernen  ori.bin stage1.bin --name passat_b8_04L906026
```

---

# Server einrichten (Strato / Hetzner, Ubuntu 24.04 oder 26.04)

1. **Domain auf den Server zeigen lassen:** Beim Domain-Anbieter für z. B. `files.deine-firma.de`
   einen **A-Eintrag** mit der IP-Adresse des Servers anlegen.
2. **Auf den Server verbinden:** Unter Windows die **PowerShell** öffnen und eingeben
   (IP und Passwort stehen in der Strato-Mail / im Strato-Kundenbereich):
   ```
   ssh root@DEINE-SERVER-IP
   ```
   Beim ersten Mal mit `yes` bestätigen, dann das Passwort eingeben (man sieht beim Tippen nichts, das ist normal).
3. **Installation starten** – diese eine Zeile einfügen (Rechtsklick fügt ein) und Enter:
   ```
   curl -fsSL https://raw.githubusercontent.com/Kgh56/oneclick-tuning/main/install.sh | bash
   ```
   Das Skript fragt nach Domain, Admin-Name und Admin-Passwort. Nach ein paar Minuten steht da **„Fertig!“**.
4. Im Browser `https://deine-domain/login` öffnen → anmelden → alles Weitere im Admin-Bereich:
   - **Einstellungen:** Firmenname, **Impressum und Datenschutz** (Pflicht für Firmen-Webseiten), Telegram-Bot
   - **Archiv:** eure Files als ZIP hochladen

Falls Strato im Kundenbereich eine eigene Firewall hat: Ports **80** und **443** freigeben.

**Später aktualisieren:** Admin-Bereich → Einstellungen → „Nach Updates suchen“ → „Update installieren“.
Die Seite startet ein paar Sekunden neu; Archiv, Aufträge und Einstellungen bleiben erhalten.
(Alternativ per `ssh` verbinden und `oneclick-update` eingeben.)
**Backup:** täglich automatisch nach `/var/backups/oneclick/` (14 Tage). Zusätzlich im Admin-Bereich unter
Archiv → „Archiv als ZIP herunterladen“ ab und zu eine Kopie auf den PC holen.

---

# Ablauf

**Kunden arbeiten nur mit dem Windows-Programm** (siehe unten). Die Startseite der Domain zeigt nur noch den
Download des Programms sowie Impressum und Datenschutz. Hochladen/Bestellen im Browser gibt es nicht mehr.

Im Programm: Original auswählen → nur die gefundenen Lösungen werden angezeigt → eine oder mehrere wählen,
optional Name/Telefon → „Auftrag senden“. **Erst nach deiner Freigabe** kann der Kunde herunterladen;
das Programm fragt den Status selbst ab und meldet sich.

**Du bekommst eine Meldung:**
- **Telegram** aufs Handy, mit Knöpfen ✅ Bestätigen / ❌ Ablehnen direkt in der Nachricht
- **Admin-Bereich** (`/login`): Ton + Browser-Benachrichtigung bei neuen Aufträgen,
  Bestätigen/Ablehnen direkt in der Liste, oder eigenes File hochladen (= freigeben, optional ins Archiv lernen)

## Anfragen (Tickets)
Kein Treffer im Archiv – oder der Kunde braucht etwas, das nicht angeboten wird? Dann klickt er im Programm
**„Anfrage stellen“**:

1. Pflicht: **Marke, Modell, Baujahr, Motor/Leistung** (optional Motorcode, Getriebe, Nachricht, Kontakt) und
   mindestens eine gewünschte Lösung (Stage 1, Pops & Bangs, eigene Lösungen …).
2. Das Original liegt dabei schon auf dem Server (wird beim Prüfen gespeichert, nicht abgeschickte Entwürfe
   werden nach 1 Tag gelöscht).
3. Du bekommst in **Telegram** die Anfrage mit allen Fahrzeugdaten und **das Original direkt als Datei**
   (Knopf „Ablehnen“ + Link in den Admin-Bereich). Im Admin-Bereich steht sie unter „Offene Anfragen“.
4. File bearbeiten → im Admin-Bereich bei der Anfrage **„Hochladen & an Kunden schicken“** (optional mit
   Archivname, dann bekommt der nächste Kunde mit dem File es automatisch). Oder **ablehnen** mit Grund.
5. Das Programm des Kunden meldet sich automatisch: „Dein File ist fertig!“ → Herunterladen.

## Admin-Bereich
| Seite | Was |
|---|---|
| **Aufträge** | Wartende Aufträge bestätigen/ablehnen, alle Aufträge |
| **Archiv** | Fahrzeug einzeln hinzufügen oder Option nachreichen, eigene Lösungen anlegen, ZIP-Import, Einträge löschen, Archiv als ZIP sichern |
| **Einstellungen** | Firmenname, Impressum, Datenschutz, Telegram, „nur identische Originale“, automatisches Löschen alter Aufträge (Standard 90 Tage), Admin-Passwort ändern, **Update installieren** |

## Telegram einrichten (im Admin-Bereich → Einstellungen)
1. In Telegram **@BotFather** öffnen → `/newbot` → Namen vergeben → **Token** in den Einstellungen eintragen → Speichern.
2. Dem neuen Bot in Telegram etwas schreiben (z. B. „hallo“). Für mehrere Leute: Bot in eine Gruppe holen.
3. Einstellungen neu laden → Chat erscheint → „übernehmen“ → „Telegram testen“.

Nur Knopfdrücke aus diesem Chat werden angenommen.

---

# Windows-Programm für Kunden
Kunden arbeiten mit dem Windows-Programm. Es besteht aus `kunde/oneclick_kunde.py` (Verbindung zum Server über
`/api/...`) und `kunde/ui.html` (Oberfläche mit Animationen, angezeigt über Microsoft Edge WebView2, das in
Windows 10/11 enthalten ist).

- **Download für Kunden:** Knopf auf der Startseite bzw.
  `https://github.com/Kgh56/oneclick-tuning/releases/download/programm/OneClick-Tuning.exe`
- **Bauen:** automatisch bei jeder Änderung im Ordner `kunde/` (GitHub Actions auf Windows). Nach dem Bauen wird
  die .exe zur Probe gestartet (Selbsttest); nur wenn Oberfläche und Verbindung laufen, wird sie veröffentlicht.
- **Fenster:** startet maximiert; **F11** schaltet echtes Vollbild ein/aus. Auf großen Bildschirmen mit Begrüßung,
  Kennzahlen, „So funktioniert's“, animiertem Netzwerk-Hintergrund und Lichtschein, der der Maus folgt.
- **Ablauf im Programm:** Datei hineinziehen oder auswählen → Analyse → verfügbare Lösungen wählen → Auftrag senden →
  das Programm fragt den Status selbst ab und meldet die Freigabe (mit Ton und Konfetti) → Herunterladen.
- **Auto-Update:** Beim Öffnen prüft das Programm, ob es eine neuere Version gibt (Datei `version.json` neben der .exe
  auf GitHub, mit fortlaufender Build-Nummer und SHA-256-Prüfsumme). Wenn ja: herunterladen, Prüfsumme prüfen,
  laufende .exe austauschen, neu starten. Klappt das nicht (z. B. keine Schreibrechte), läuft die alte Version weiter.
- **Server-Adresse** ist fest eingestellt und kann im Programm über das Zahnrad geändert werden.
- Das Programm ist **nicht signiert**: Windows zeigt beim ersten Start „Der Computer wurde durch Windows geschützt“
  → „Weitere Informationen“ → „Trotzdem ausführen“. Ohne Warnung geht es nur mit einem Code-Signatur-Zertifikat (kostenpflichtig).

# Sicherheit
- Admin-Login wird nach 5 Fehlversuchen für 15 Minuten gesperrt, Kunden-Uploads sind auf 30 pro Stunde begrenzt.
- Alle Formulare sind gegen Fremd-Absendungen (CSRF) geschützt, Cookies nur über HTTPS.
- Webseite und interne Dienste lauschen nur lokal, nach außen nur HTTPS über Caddy. Firewall: nur 22, 80, 443.

# Automatische Tests
```
python -m unittest discover tests
```
Prüft u. a. alle Treffer-Regeln (identisch, gleiche Stellen, 1 Byte anders, andere Softwarenummer, verschoben),
den kompletten Kunden-Ablauf, Freigabe/Ablehnung, Login-Sperre, ZIP-Import und Aufräumen.

# Lokal testen (ohne Server)
```
pip install -r requirements.txt
python app.py admin chef        # Admin anlegen
python app.py                   # http://localhost:5000
```

Daten liegen neben dem Programm: `archiv/`, `auftraege/`, `config.json`, `benutzer.json`
(alle in `.gitignore`, kommen nie ins Repository). `config.json` enthält Zugangsdaten – nicht weitergeben.
