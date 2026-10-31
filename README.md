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

## Lose Dateien sortieren (Archiv → Sortieren)
ZIP mit losen Dateien ohne Ordner und ohne „ori“/„stage1“ im Namen? Beim ZIP-Import **„Alle Dateien selbst zuordnen“**
anhaken. Dateien, die der normale Import nicht zuordnen kann, landen ebenfalls dort statt übersprungen zu werden.

- Die Seite gruppiert automatisch nach Inhalt: gleiche Größe und überwiegend gleiche 4-KB-Blöcke = gleiches Fahrzeug
  (ein Tuning-File unterscheidet sich vom Original nur in wenigen Blöcken, fremde Files fast komplett).
- Vorschläge: Original (schon im Archiv, laut Dateiname oder bei 3+ Files die „Mitte“ der Gruppe), Lösung laut
  Dateiname, „schon im Archiv“ → Ignorieren, „Passt zum Archiv-Eintrag …“ für Tuning-Files zu vorhandenen Originalen.
- Pro Datei wählen, was sie ist: Original, eine oder **mehrere Lösungen** (z. B. Stage 1 + Pops & Bangs in einem File –
  wird im Archiv als `stage1+popsbangs.bin` gespeichert und Kunden als eigene Lösung angeboten, Preis = Summe der Teile)
  oder Ignorieren. Fahrzeugname eingeben, „Ins Archiv übernehmen“.
- **Mehrere Autos in einer Gruppe** (gleiche Software): jedes Original als „Original“ markieren und benennen. Jedes
  Tuning-File kommt automatisch zu dem Original, dem es am ähnlichsten ist; pro Auto wird ein Archiv-Eintrag angelegt.
- **„Automatisch zuordnen“** übernimmt alle Gruppen, bei denen nichts geraten werden muss: Original schon im Archiv,
  „ori“ im Dateinamen oder eindeutig am Inhalt erkennbar (ab 3 Files) bzw. Tuning-Files zu einem Archiv-Original –
  und die Lösung steht im Dateinamen (stage1/st1, stage2, pops, vmax, launch, start/stop, eigene Lösungen, auch
  kombiniert wie „stage1_pops“). Dateien, die schon im Archiv sind, werden aufgeräumt. Der Rest bleibt mit Grund stehen
  („Original nicht sicher erkennbar“ / „Lösung nicht aus dem Dateinamen erkennbar“). Namen ohne Buchstaben (z. B.
  „1001.bin“) werden durch Steuergerät + Software ersetzt.
- Files, deren Name eine Abschaltung der Abgasreinigung nennt (DPF, AGR/EGR, AdBlue/SCR, NOx, Lambda, Kat …), werden
  nicht übernommen: Der ZIP-Import überspringt sie (mit Meldung), schon liegende werden in „Sortieren“ ausgeblendet
  (Löschen nur per Knopf „Endgültig löschen“) und beim Übernehmen ignoriert, und das
  restliche Fahrzeug (Original, Stage 1 …) wird normal zugeordnet.
- Fehler beim Übernehmen löschen nichts: Dateien bleiben unter „Sortieren“, bis sie übernommen oder verworfen werden.
  Dateien lassen sich in andere Gruppen verschieben und zum Prüfen herunterladen. Doppelte werden erkannt.

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

**Kunden arbeiten auf der Startseite der Domain** (siehe „Kundenseite“ unten), ohne Login und ohne Installation.

Auf der Seite: Original auswählen → nur die gefundenen Lösungen werden angezeigt → eine oder mehrere wählen,
optional Name/Telefon → „Auftrag senden“. **Erst nach deiner Freigabe** kann der Kunde herunterladen;
die Seite fragt den Status selbst ab und meldet sich.

**Du bekommst eine Meldung:**
- **Telegram** aufs Handy, mit Knöpfen ✅ Bestätigen / ❌ Ablehnen direkt in der Nachricht
- **Admin-Bereich** (`/login`): Ton + Browser-Benachrichtigung bei neuen Aufträgen,
  Bestätigen/Ablehnen direkt in der Liste, oder eigenes File hochladen (= freigeben, optional ins Archiv lernen)

## Anfragen (Tickets)
Kein Treffer im Archiv – oder der Kunde braucht etwas, das nicht angeboten wird? Dann klickt er auf der Seite
**„Anfrage stellen“**:

1. Pflicht: **Marke, Modell, Baujahr, Motor/Leistung** (optional Motorcode, Getriebe, Nachricht, Kontakt) und
   mindestens eine gewünschte Lösung (Stage 1, Pops & Bangs, eigene Lösungen …).
2. Das Original liegt dabei schon auf dem Server (wird beim Prüfen gespeichert, nicht abgeschickte Entwürfe
   werden nach 1 Tag gelöscht).
3. Du bekommst in **Telegram** einen kurzen Hinweis (gewünschte Lösung, Fahrzeug, ECU, Software; Knopf
   „Ablehnen“ + Link in den Admin-Bereich). Original, Kontakt und Nachricht gibt es nur im Admin-Bereich unter
   „Offene Anfragen“ – aus Datenschutzgründen geht nichts Persönliches und keine Datei an Telegram.
4. File bearbeiten → im Admin-Bereich bei der Anfrage **„Hochladen & an Kunden schicken“** (optional mit
   Archivname, dann bekommt der nächste Kunde mit dem File es automatisch). Oder **ablehnen** mit Grund.
5. Die Seite des Kunden meldet sich automatisch: „Dein File ist fertig!“ → Herunterladen.

## Hilfe nach dem Download (WhatsApp)
Bei freigegebenen/bezahlten Aufträgen zeigt die Kundenseite neben „Herunterladen“ den Knopf **„Problem?“** (und nach dem
Download in der Meldung). Er öffnet WhatsApp mit vorausgefüllter Nachricht: Kurz-Nr. des Auftrags, Datei, Lösung,
Steuergerät, Software – der Kunde schreibt nur noch das Problem dazu. Die volle Auftragsnummer (= Download-Zugang) wird
nicht mitgeschickt. Im Admin-Bereich unter „Alle Aufträge“ findet die **Suche** den Auftrag über die Kurz-Nr.
Nummer: Admin → Einstellungen („WhatsApp-Nummer für Kunden mit Problemen“, leer = Knopf aus).

## Bezahlen mit Stripe
Ablauf: Kunde wählt Lösungen (Preise werden angezeigt, mehrere werden addiert) → Auftrag → **du gibst frei** →
Kunde klickt „Jetzt bezahlen“, bestätigt den Hinweis zum Widerrufsrecht und bezahlt auf der Stripe-Bezahlseite →
Stripe meldet die Zahlung (Webhook, zusätzlich fragt der Server selbst nach) → **Download wird freigeschaltet**.
Vorher liefert der Download nur „Bitte zuerst bezahlen“. Stripe schickt dem Kunden die Rechnung per E-Mail.

Einrichten (Admin → Einstellungen → „Bezahlen mit Stripe“):
1. Stripe → Entwickler → API-Schlüssel → geheimen Schlüssel (`sk_live_…`, zum Ausprobieren `sk_test_…`) eintragen.
2. Stripe → Entwickler → Webhooks → Endpunkt `https://deine-seite.de/stripe/webhook` mit den Ereignissen
   `checkout.session.completed` und `checkout.session.async_payment_succeeded` → Signaturgeheimnis (`whsec_…`) eintragen.
3. „Stripe testen“. Zahlungsarten (Karte, Apple Pay, PayPal, Klarna …) stellst du in Stripe ein.
4. Admin → Archiv → **Preise** eintragen. Ohne Preis = kostenlos. Beim Freigeben kannst du den Preis für einen
   einzelnen Auftrag ändern, bei Anfragen trägst du ihn beim Hochladen des fertigen Files ein.

Ohne Stripe-Schlüssel ist Bezahlen aus und alles läuft wie vorher. Die Schlüssel werden nie angezeigt.
Im Testmodus (`sk_test_…`) mit der Testkarte 4242 4242 4242 4242, beliebiges Datum in der Zukunft, beliebige Prüfziffer.

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

# Kundenseite
Kunden arbeiten direkt im Browser auf der Startseite der Domain (`web/kunde.html`, spricht über `/api/...` mit
dem Server) – am PC und am Handy, ohne Installation.

- **Ablauf:** Datei hineinziehen oder auswählen → Analyse → verfügbare Lösungen wählen → Auftrag senden →
  die Seite fragt den Status selbst ab und meldet die Freigabe (mit Ton und Konfetti) → Herunterladen.
- **Meine Aufträge** merkt sich der Browser (localStorage) – der Kunde kann die Seite schließen und später
  wiederkommen. Zugriff auf einen Auftrag gibt es nur über seine geheime 32-stellige Nummer.
- Große Bildschirme: Begrüßung, Kennzahlen, „So funktioniert's“, animierter Netzwerk-Hintergrund, Lichtschein, der der Maus folgt.
- Unten: Impressum und Datenschutz (im Admin-Bereich unter Einstellungen pflegen).

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

Daten liegen neben `app.py`: `archiv/`, `auftraege/`, `config.json`, `benutzer.json`
(alle in `.gitignore`, kommen nie ins Repository). `config.json` enthält Zugangsdaten – nicht weitergeben.
