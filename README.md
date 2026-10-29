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

## Archiv – neue Files hochladen
Im Admin-Bereich unter **Archiv**:
- **Neues Fahrzeug hinzufügen:** Name eintragen, Original und Tuning-File(s) auswählen (Stage 1, Stage 2,
  Start/Stopp, Vmax, Pops & Bangs, Launch – was es gibt) → Speichern. Ab sofort bekommen Kunden mit diesem
  Original einen Treffer.
- **Option nachreichen:** einen vorhandenen Namen wählen, dasselbe Original und nur die neue Option auswählen
  → die bisherigen Optionen bleiben erhalten.
- **Viele auf einmal:** ZIP mit einem Ordner pro Fahrzeug hochladen.

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

**Später aktualisieren:** per `ssh` verbinden und `oneclick-update` eingeben.
**Backup:** täglich automatisch nach `/var/backups/oneclick/` (14 Tage). Zusätzlich im Admin-Bereich unter
Archiv → „Archiv als ZIP herunterladen“ ab und zu eine Kopie auf den PC holen.

---

# Webseite

**Kunden brauchen kein Login:** Original hochladen → „File prüfen“ → nur die gefundenen Optionen werden angezeigt →
Option wählen, optional Name/Telefon → „Auftrag senden“. **Erst nach deiner Freigabe** kann der Kunde herunterladen.
Bis dahin zeigt seine Seite „Wartet auf Freigabe“ und aktualisiert sich alle 5 Sekunden selbst.
Wird abgelehnt, sieht der Kunde das (mit Grund, falls angegeben).

**Du bekommst eine Meldung:**
- **Telegram** aufs Handy, mit Knöpfen ✅ Bestätigen / ❌ Ablehnen direkt in der Nachricht
- **Admin-Bereich** (`/login`, nicht im Menü verlinkt): Ton + Browser-Benachrichtigung bei neuen Aufträgen,
  Bestätigen/Ablehnen direkt in der Liste, oder eigenes File hochladen (= freigeben, optional ins Archiv lernen)

Kein 100-%-Treffer? Dann sieht der Kunde „Für dieses File haben wir leider noch keine Lösung“, es entsteht kein Auftrag.
Vor dem Bestätigen kannst du im Admin-Bereich auch ein eigenes File hochladen, das dann stattdessen ausgeliefert wird.

## Admin-Bereich
| Seite | Was |
|---|---|
| **Aufträge** | Wartende Aufträge bestätigen/ablehnen, alle Aufträge |
| **Archiv** | Fahrzeug einzeln hinzufügen oder Option nachreichen, ZIP-Import, Einträge löschen, Archiv als ZIP sichern |
| **Einstellungen** | Firmenname, Impressum, Datenschutz, Telegram, „nur identische Originale“, automatisches Löschen alter Aufträge (Standard 90 Tage), Admin-Passwort ändern |

## Telegram einrichten (im Admin-Bereich → Einstellungen)
1. In Telegram **@BotFather** öffnen → `/newbot` → Namen vergeben → **Token** in den Einstellungen eintragen → Speichern.
2. Dem neuen Bot in Telegram etwas schreiben (z. B. „hallo“). Für mehrere Leute: Bot in eine Gruppe holen.
3. Einstellungen neu laden → Chat erscheint → „übernehmen“ → „Telegram testen“.

Nur Knopfdrücke aus diesem Chat werden angenommen.

## WhatsApp (optional, statt oder zusätzlich zu Telegram)
Die normale WhatsApp-Business-**App** hat keine Schnittstelle. Benötigt wird die **WhatsApp Business Platform
(Cloud API)** von Meta. Mit „Coexistence“ kann deine bestehende Business-Nummer dabei in der App weiterlaufen.
Die Meldung geht *von* der Business-Nummer *an* eine andere Nummer (z. B. dein privates WhatsApp).

1. **Meta-App anlegen:** developers.facebook.com → „App erstellen“ → Typ *Business* → Produkt **WhatsApp** hinzufügen.
2. **Nummer verbinden** (Coexistence per QR-Code aus der Business-App, sonst über einen Anbieter wie 360dialog
   oder mit einer zweiten Nummer) → **Phone-Number-ID** → `whatsapp_phone_id`.
3. **Dauerhafter Token:** business.facebook.com → Einstellungen → Systemnutzer → Token mit
   `whatsapp_business_messaging` → `whatsapp_token`.
4. **Vorlage** (WhatsApp Manager → Nachrichtenvorlagen), muss von Meta genehmigt werden:
   Name `neuer_auftrag`, Kategorie **Utility**, Sprache **Deutsch (de)**, Text:
   ```
   Neuer Tuning-Auftrag: {{1}}
   Datei: {{2}}
   ECU: {{3}}
   Kontakt: {{4}}
   Automatik: {{5}}
   ```
   Schaltflächen: **Schnellantwort** „Bestätigen“ (1.) und „Ablehnen“ (2.), genau in dieser Reihenfolge.
5. **Webhook:** Callback-URL `https://deine-seite.de/whatsapp/webhook`, Verify-Token = `whatsapp_verify_token`,
   Feld **messages** abonnieren, App-Geheimcode → `whatsapp_app_secret`.
6. `whatsapp_empfaenger`: deine Nummer(n) mit Ländervorwahl, z. B. `["4917612345678"]`.
7. Werte in `config.json` auf dem Server eintragen (Vorlage: `config.example.json`), `python app.py whatsapp-test`.

Kosten: Meta berechnet Vorlagen-Nachrichten pro Stück (wenige Cent; aktuelle Preise bei Meta prüfen).

---

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
