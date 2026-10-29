# OneClick Tuning – Kern

Überträgt Stage 1 (und weitere Optionen) aus eurem Archiv automatisch auf neue Originaldateien.
Benötigt nur Python 3, keine Zusatzpakete. **Checksummen werden nicht korrigiert** (Flash-Tool / WinOLS).

## 1. Archiv anlegen
Pro Fahrzeug/Softwarestand ein Ordner unter `archiv/`:

```
archiv/
  golf7_20tdi_03L906018JL/
    ori.bin
    stage1.bin
    startstopp.bin   (optional)
```

Erlaubte Optionsnamen: `stage1`, `stage2`, `startstopp`, `vmax`, `popsbangs`, `launch`.
ORI und Mod-Datei müssen gleich groß sein (gleiche Leseart).

```
python oneclick.py index
```

## 2. Neues Original tunen
```
python oneclick.py tune kunde.bin                 # Stage 1
python oneclick.py tune kunde.bin -o startstopp
```

| Status        | Bedeutung                                                     | Ausgabe                       |
|---------------|---------------------------------------------------------------|-------------------------------|
| AUTOMATISCH   | Identisches Original oder alle Änderungen eindeutig gefunden  | `kunde_stage1.bin`            |
| PRUEFEN       | Nur ein Teil der Änderungen gefunden                          | `kunde_stage1_PRUEFEN.bin`    |
| MANUELL       | Nichts Passendes im Archiv                                    | nur Bericht                   |

Zu jedem Lauf wird ein Bericht `kunde_stage1_bericht.txt` geschrieben (Quelle, Sicherheit, jeder Block mit Adresse).

## 3. Archiv erweitern
Nach manueller Bearbeitung das Paar aufnehmen, damit es beim nächsten Mal automatisch geht:
```
python oneclick.py lernen kunde.bin kunde_stage1_fertig.bin --name passat_b8_04L906026
```

## Datei erkennen
```
python oneclick.py info kunde.bin
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
   - **Einstellungen:** Telegram-Bot eintragen und testen
   - **Archiv:** eure Files als ZIP hochladen
   - **WinOLS-Sync:** PC verbinden

Falls Strato im Kundenbereich eine eigene Firewall hat: Ports **80, 443** (Webseite) und **22000** (WinOLS-Sync) freigeben.

**Später aktualisieren:** per `ssh` verbinden und `oneclick-update` eingeben.
**Backup:** täglich automatisch nach `/var/backups/oneclick/` (14 Tage). Zusätzlich im Admin-Bereich unter
Archiv → „Archiv als ZIP herunterladen“ ab und zu eine Kopie auf den PC holen.

---

# Webseite

**Kunden brauchen kein Login:** Original hochladen → Option klicken → optional Name/Telefon → „Auftrag senden“.
Das File wird sofort automatisch erstellt, aber **erst nach deiner Freigabe** kann der Kunde es herunterladen.
Bis dahin zeigt seine Seite „Wartet auf Freigabe“ und aktualisiert sich alle 5 Sekunden selbst.
Wird abgelehnt, sieht der Kunde das (mit Grund, falls angegeben).

**Du bekommst eine Meldung:**
- **Telegram** aufs Handy, mit Knöpfen ✅ Bestätigen / ❌ Ablehnen direkt in der Nachricht
- **Admin-Bereich** (`/login`, nicht im Menü verlinkt): Ton + Browser-Benachrichtigung bei neuen Aufträgen,
  Bestätigen/Ablehnen direkt in der Liste, oder eigenes File hochladen (= freigeben, optional ins Archiv lernen)

Kein automatisches File (Software unbekannt)? Dann gibt es nur „Ablehnen“ – oder du lädst im Admin-Bereich
dein fertiges File hoch.

## Admin-Bereich
| Seite | Was |
|---|---|
| **Aufträge** | Wartende Aufträge bestätigen/ablehnen, alle Aufträge |
| **Archiv** | ZIP mit Original/Tuning-Paaren importieren, Einträge löschen, Archiv als ZIP sichern |
| **WinOLS-Sync** | PC per Syncthing verbinden (Anleitung steht auf der Seite) |
| **Einstellungen** | Telegram, Adresse der Seite, automatisches Löschen alter Aufträge (Standard 90 Tage) |

## Telegram einrichten (im Admin-Bereich → Einstellungen)
1. In Telegram **@BotFather** öffnen → `/newbot` → Namen vergeben → **Token** in den Einstellungen eintragen → Speichern.
2. Dem neuen Bot in Telegram etwas schreiben (z. B. „hallo“). Für mehrere Leute: Bot in eine Gruppe holen.
3. Einstellungen neu laden → Chat erscheint → „übernehmen“ → „Telegram testen“.

Nur Knopfdrücke aus diesem Chat werden angenommen.

## WinOLS-Sync
Auf dem PC entstehen zwei Ordner, die sich automatisch mit dem Server abgleichen:
- **Tuning-Auftraege** (nur empfangen): jedes Kunden-Original als `Datum_ECU_Software_Option_Datei_Nr_ORI.bin`,
  dazu `_AUTO.bin` (automatisch erstellt) bzw. `_FERTIG.bin` (von dir hochgeladen). Direkt in WinOLS importieren.
- **Tuning-Archiv** (beide Richtungen): dein Archiv. Neuen Ordner mit Original + Tuning-File hineinlegen
  → der Server lernt ihn nach ca. 1 Minute automatisch.

Alte Auftrags-Dateien werden nach der eingestellten Zeit auch auf dem PC entfernt – das Archiv nie.

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

# Lokal testen (ohne Server)
```
pip install -r requirements.txt
python app.py admin chef        # Admin anlegen
python app.py                   # http://localhost:5000
```

Daten liegen neben dem Programm: `archiv/`, `auftraege/`, `export/`, `config.json`, `benutzer.json`
(alle in `.gitignore`, kommen nie ins Repository). `config.json` enthält Zugangsdaten – nicht weitergeben.
