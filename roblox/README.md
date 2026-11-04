# Chiptuning-Firma (Roblox)

Ein Tycoon-Spiel für Roblox: Jeder Spieler bekommt eine eigene Werkstatt. Kunden fahren mit ihren Autos vor, und du tunst sie per Minispiel am Laptop. Mit dem verdienten Geld baust du deine Firma aus.

## So spielt es sich
- **Große Welt:** Werkstattstraße mit 6 Werkstätten, Läden, Bäumen und Laternen. Dazu eine **Teststrecke** (Oval mit Tribüne, Curbs und Flutlicht), eine Landstraße als großer Rundkurs, ein See und Berge am Rand. Tag und Nacht wechseln sich ab, ein Tag dauert 24 Minuten.
- **Kunden** fahren von der Straße auf deine Hebebühne. Über dem Auto steht, welches Modell es ist und welche Stage der Kunde will.
- **Tunen:** Zum Auto gehen und **[E]** drücken. Dann stimmst du drei Kennfelder ab (Zündzeitpunkt, Ladedruck, Einspritzmenge): Die Nadel läuft hin und her, und du stoppst sie mit der **Leertaste** oder dem Knopf.
  - Grün = perfekt, Gelb = okay, Rot = der Motor klopft
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

## Dateien
| Datei | Ort in Roblox | Inhalt |
|---|---|---|
| `src/shared/Config.lua` | ReplicatedStorage › ModuleScript „Config“ | Preise, Autos, Upgrades, Fahrwerte, Balancing |
| `src/server/GameServer.server.lua` | ServerScriptService › Script | Werkstätten, Kunden, Geld, Fahren, Shop, Speichern |
| `src/server/World.lua` | ServerScriptService › ModuleScript | Gelände, Licht, Straßen, Teststrecke, Bäume, Gebäude |
| `src/server/Cars.lua` | ServerScriptService › ModuleScript | Automodelle (Ausstellung und fahrbar) |
| `src/server/Util.lua` | ServerScriptService › ModuleScript | Bau-Helfer |
| `src/client/ChiptuningClient.client.lua` | StarterPlayerScripts › LocalScript | Oberfläche, Tuning-Minispiel, Shop |
| `src/client/DriveClient.client.lua` | StarterPlayerScripts › LocalScript | Fahrphysik, Tacho, Rundenzeit |

Balancing wie Preise, Bezahlung, Kundentempo oder Fahrwerte änderst du in `Config.lua`.

Die Beleuchtung steht in der Place-Datei auf **Future**. Falls sie beim Öffnen anders ist: Explorer → Lighting → Technology → Future.
