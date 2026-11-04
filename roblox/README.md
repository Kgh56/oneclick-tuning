# Chiptuning-Firma (Roblox)

Ein Tycoon-Spiel für Roblox: Jeder Spieler bekommt eine eigene Werkstatt. Kunden fahren mit ihren Autos vor, und du tunst sie per Minispiel am Laptop. Mit dem verdienten Geld baust du deine Firma aus.

## So spielt es sich
- **Große Welt:** Werkstattstraße mit 6 Werkstätten, Läden, Bäumen und Laternen. Dazu eine **Teststrecke** (Oval mit Tribüne, Curbs und Flutlicht), eine Landstraße als großer Rundkurs, ein See und Berge am Rand. Tag und Nacht wechseln sich ab, ein Tag dauert 24 Minuten.
- **Action:**
  - **Stuntpark** im Innenfeld der Teststrecke: drei Sprungschanzen (Mega-Schanze über einen Bus) und Kicker
  - **Slalom** mit Zeitmessung und Strafsekunden für jede Pylone
  - **Blitzer** auf der Landstraße und der Werkstattstraße
  - **Rekordtafeln** am Spawn und im Stuntpark, mit Bestenliste über alle Server und Geld für persönliche Rekorde
  - **12 goldene Schraubenschlüssel** auf der Karte versteckt (je 1.000 €, alle zusammen +25.000 €)
- **Fahr-Extras:** Nitro (N), Hupe (H), Launch Control (Shift halten + W im Stand), **Pop & Bang** als Upgrade und Kundenwunsch, Brems- und Blinklichter
- **Echter Verkehr:** Ampeln an den Kreuzungen, Abstand zum Vordermann, Bremsen und Anfahren, langsamer in Kurven, Blinker, Bremslichter und Neigung der Karosserie. Hält auch vor dir an.
- **Echte Avatare:** Fußgänger, Fahrer, Kunden und Zuschauer sehen aus wie du und deine Roblox-Freunde (Reserve: bekannte Roblox-Konten). Sie laufen mit denselben Animationen wie dein eigener Charakter.
- **Leben in der Stadt:** Verkehr mit Fahrern auf allen Straßen (Rechtsverkehr, hält vor dir an), Fußgänger auf den Gehwegen und am See, jubelnde Zuschauer auf der Tribüne, geparkte Autos im Fahrerlager. Alle Autos haben drehende und lenkende Räder.
- **Landschaft:** Hügel, Wiesen, Felder mit Zaun, Büsche, Felsen, Blumen, Bänke, Bushaltestellen und Verkehrsschilder.
- **Kunden** fahren mit ihrem Auto von der Straße auf deine Hebebühne, steigen aus und warten daneben. Über dem Auto steht, welches Modell es ist und welche Stage der Kunde will.
- **Tunen:** Zum Auto gehen und **[E]** drücken. Die Bühne fährt hoch, und du spielst drei von vier zufällig gemischten Minispielen:
  - **Zündzeitpunkt:** Nadel im grünen Bereich stoppen
  - **Ladedruck halten:** Taste halten und den Druck in der wandernden Zone halten
  - **Fehlercodes löschen:** aufleuchtende Codes merken und nachdrücken (Tasten 1–4)
  - **Prüfstandslauf:** bei grünen Schaltblitzen hochschalten
- **Probefahrt:** Nach dem Tunen kannst du das Kundenauto mit der neuen Leistung auf der Teststrecke fahren. Es gibt eine Rundenzeit und Trinkgeld, wenn du mindestens 15 Sekunden fährst.
- **Firmenwagen:** Mit dem Knopf „🚗 Auto“ steht dein Firmenwagen neben der Halle, und du fährst damit durch die ganze Welt. Mit Stage-2-/Stage-3-Software wird er stärker.
- **Fahren:** W/S oder Pfeiltasten für Gas und Bremse, A/D zum Lenken, Leertaste oder „Aussteigen“ zum Aussteigen. Gamepad und Handy funktionieren auch. Mehr PS bedeuten mehr Beschleunigung und Höchstgeschwindigkeit.
- **Bezahlung** hängt ab von der Stage, vom Auto, von deinem Ergebnis und von deinem **Ruf**. Saubere Arbeit bringt Ruf. Mit mehr Ruf kommen teurere Autos, bis hin zum V12-Supersportler.
- **Upgrades** kaufst du am Laptop vorne links oder über den „Shop“-Knopf:

| Upgrade | Wirkung |
|---|---|
| 2./3./4. Hebebühne | mehrere Kunden gleichzeitig |
| Stage-2-/Stage-3-Software | größere Aufträge, mehr Geld, stärkerer Firmenwagen |
| Profi-Laptop | breitere grüne Zone |
| Werbung | Kunden kommen doppelt so oft |
| Leistungsprüfstand | +25 % Bezahlung, die Autos fahren auf die Rolle |
| Azubi | tunt wartende Autos automatisch |

- Geld, Ruf und Upgrades werden **gespeichert** (DataStore).

## Ins Spiel bringen

### Schnellweg: Place-Datei öffnen
1. **Roblox Studio** installieren: https://create.roblox.com → „Start Creating“.
2. `ChiptuningFirma.rbxlx` aus diesem Ordner herunterladen (auf GitHub die Datei öffnen und auf „Download raw file“ klicken).
3. Die Datei in Roblox Studio öffnen (*File → Open from File*).
4. Oben auf **Play** klicken (F5). Die Welt mit Straße und Werkstatt baut sich beim Start automatisch auf. Im Bearbeitungsmodus ist die Fläche deshalb leer, das ist normal.

### Veröffentlichen
1. In Studio: *File → Publish to Roblox*, Namen und Beschreibung eingeben.
2. *Home → Game Settings*:
   - **Security** → „Enable Studio Access to API Services“ einschalten. Sonst wird beim Testen in Studio nichts gespeichert.
   - **Places → Server Size** auf **6** stellen (es gibt 6 Werkstätten pro Server).
3. Auf https://create.roblox.com/dashboard/creations beim Spiel ein Icon und Thumbnails hochladen und die Sichtbarkeit auf **Public** stellen.

### Für Fortgeschrittene: Rojo
Der Code liegt in `src/`, und `default.project.json` ist ein Rojo-Projekt. Mit dem Rojo-Plugin in Studio und `rojo serve` im Ordner `roblox/` werden Änderungen live ins Spiel übertragen.

Ohne Rojo baust du die Place-Datei neu mit:

```
python3 build_place.py
```

## Robux-Shop (Geld verdienen)
Im Spiel gibt es einen Robux-Tab im Shop (Knopf „💎 Robux“ links):

| Artikel | Art | Wirkung | Preisvorschlag |
|---|---|---|---|
| 💰 Doppeltes Geld | Game Pass | jeder Auftrag zahlt doppelt | 199 R$ |
| ⭐ VIP-Werkstatt | Game Pass | goldenes Schild, VIP-Titel, +10 % Geld | 149 R$ |
| 🚀 Turbo-Kundschaft | Game Pass | Kunden kommen doppelt so schnell | 99 R$ |
| Geldpaket S | Developer Product | +5.000 € im Spiel | 49 R$ |
| Geldpaket L | Developer Product | +25.000 € im Spiel | 149 R$ |

### Einrichten
1. Das Spiel veröffentlichen (siehe oben).
2. Auf https://create.roblox.com/dashboard/creations dein Spiel öffnen und links **Monetization** wählen.
3. Unter **Passes** die drei Game Passes anlegen: jeweils Bild, Name und Beschreibung, dann unter *Sales* „Item for Sale“ einschalten und einen Preis setzen.
4. Unter **Developer Products** die zwei Geldpakete anlegen, ebenfalls mit Preis.
5. Die Zahlen-**IDs** der Artikel kopieren (sie stehen in der Liste oder in der Adresszeile) und in `src/shared/Config.lua` bei `Config.GamePasses` bzw. `Config.Products` jeweils hinter `Id =` eintragen.
6. In Studio den geänderten Code übernehmen und neu veröffentlichen. Den Preis liest das Spiel automatisch aus dem Creator Hub.

Solange `Id = 0` steht, zeigt der Knopf „Bald verfügbar“. Käufe in Studio sind Testkäufe und kosten keine echten Robux.

Gekaufte Game Passes werden bei jedem Betreten des Spiels von Roblox abgefragt. Geldpakete werden sofort gutgeschrieben und gespeichert. Jeder Kauf wird nur einmal gutgeschrieben, auch wenn Roblox ihn erneut meldet.

## Sounds
Motor, Turbo, Abblasventil, Fehlzündung, Reifen, Hydraulik und Umgebung werden mit `tools/make_sounds.py` per Klangsynthese erzeugt. Die Dateien liegen in `sounds/`. `sounds/hoerprobe.mp3` zeigt, wie das im Spiel klingt (Leerlauf, Gasstoß, Beschleunigen mit Gangwechseln, Gas weg).

| Datei | Eintrag in `Config.Sounds` |
|---|---|
| `motor_tief.ogg` | `MotorTief` |
| `motor_hoch.ogg` | `MotorHoch` |
| `turbo.ogg` | `Turbo` |
| `abblasen.ogg` | `Abblasen` |
| `fehlzuendung.ogg` | `Fehlzuendung` |
| `reifen.ogg` | `Reifen` |
| `hydraulik.ogg` | `Hydraulik` |
| `umgebung.ogg` | `Umgebung` |
| `hupe.ogg` | `Hupe` |

So kommen sie ins Spiel:
1. Auf https://create.roblox.com/dashboard/creations links **Development Items → Audio** öffnen, dann **Upload Asset** und die 9 Dateien hochladen. In Studio geht es auch über *View → Asset Manager → Bulk Import*.
2. Die Prüfung durch Roblox abwarten (meist wenige Minuten).
3. Die Zahlen-IDs in `src/shared/Config.lua` bei `Config.Sounds` eintragen, z. B. `MotorTief = "1234567890",`.

Leere Einträge sind stumm. Das Spiel funktioniert auch ohne Sounds.

## Testen
- In **Roblox Studio** startest du automatisch mit 1.000.000 € (`Config.StudioMoney`).
- Als **Besitzer des Spiels** (und in Studio) siehst du links lila Knöpfe: **+100.000 €** und **+50 Ruf**. Mit Ruf schaltest du die teureren Kundenautos frei.
- Weitere Tester trägst du in `Config.AdminUserIds` ein.
- Achtung: Ist in Studio der API-Zugriff an, wird das Testgeld auch im echten Spiel gespeichert.

## Dateien
| Datei | Ort in Roblox | Inhalt |
|---|---|---|
| `src/shared/Config.lua` | ReplicatedStorage › ModuleScript | Preise, Autos, Upgrades, Fahrwerte, Verkehr, Balancing |
| `src/shared/Cars.lua` | ReplicatedStorage › ModuleScript | Automodelle (5 Karosserieformen, fahrbar und verankert) |
| `src/shared/Npc.lua` | ReplicatedStorage › ModuleScript | Personen (Fahrer, Kunden, Fußgänger) |
| `src/shared/Paths.lua` | ReplicatedStorage › ModuleScript | Fahrspuren und Fußwege |
| `src/shared/Util.lua` | ReplicatedStorage › ModuleScript | Bau-Helfer |
| `src/shared/EngineSound.lua` | ReplicatedStorage › ModuleScript | Motorsound mit Getriebe und Drehzahl |
| `src/server/GameServer.server.lua` | ServerScriptService › Script | Werkstätten, Kunden, Hebebühnen, Geld, Fahren, Shop, Speichern |
| `src/server/World.lua` | ServerScriptService › ModuleScript | Gelände, Licht, Straßen, Teststrecke, Natur, Gebäude |
| `src/client/ChiptuningClient.client.lua` | StarterPlayerScripts › LocalScript | Oberfläche, Tuning-Minispiel, Shop |
| `src/client/DriveClient.client.lua` | StarterPlayerScripts › LocalScript | Fahrphysik, Tacho, Rundenzeit |
| `src/client/LifeClient.client.lua` | StarterPlayerScripts › LocalScript | Verkehr, Fußgänger, Räder- und Personen-Animation |

Balancing wie Preise, Bezahlung, Kundentempo oder Fahrwerte änderst du in `Config.lua`.

Die Place-Datei schaltet **Streaming** ein (Workspace → StreamingEnabled): Jeder Spieler lädt nur seine Umgebung, das hält das Spiel auf der großen Karte flüssig.

Die Beleuchtung steht in der Place-Datei auf **Future**. Falls sie beim Öffnen anders ist: Explorer → Lighting → Technology → Future.
