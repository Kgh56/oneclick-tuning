# ST. AGNES – Horror-Spiel (Unity 6, URP)

Ego-Horror in einer verlassenen Psychiatrie. Finde 3 Sicherungen, bring sie zum
Notstromtor – und lass dich nicht von **Patient 17** erwischen.

Alles (Level, Texturen, Sounds, Monster) wird per Code erzeugt. Es gibt keine
Bild- oder Audiodateien, nur C#-Skripte.

## Einrichten (ca. 5 Minuten)

1. **Unity Hub** → *New Project* → Template **"Universal 3D"** (Unity 6 / 6000.x).
2. Den Ordner `Assets/HorrorClinic` aus diesem Repo in den `Assets`-Ordner
   des neuen Projekts kopieren.
3. Warten, bis Unity fertig kompiliert hat.
4. Eine beliebige Szene öffnen (z. B. `SampleScene`) → **Play** drücken.

Das Spiel startet von selbst. Es entfernt die Standard-Kamera und das Licht der
Szene und baut die Klinik neu auf.

> Falls eine Meldung zum Input System kommt: *Edit → Project Settings → Player →
> Active Input Handling* auf **"Input System Package (New)"** oder **"Both"** stellen.

### Für die beste Grafik
- *Game*-Fenster auf **Full HD** stellen, nicht "Free Aspect".
- *Edit → Project Settings → Quality* → **High Fidelity** bzw. **PC** wählen.
- Kopfhörer aufsetzen.

### Als .exe bauen
*File → Build Profiles → Windows* → Szene hinzufügen → **Build**.
Falls Objekte danach pink sind: *Project Settings → Graphics → Always Included
Shaders* um `Universal Render Pipeline/Lit` ergänzen.

## Steuerung
| Taste | Aktion |
|---|---|
| WASD | laufen |
| Shift | rennen (laut!) |
| Strg / C | ducken (leise, schwerer zu sehen) |
| F | Taschenlampe (er sieht das Licht) |
| E | benutzen / Notizen lesen |
| ESC | Pause |
| R | Neustart nach Tod/Sieg |

## Was drin ist
- **Grafik:** URP mit Bloom, Filmkorn, chromatischer Aberration, Linsenverzerrung,
  Vignette, Split-Toning, ACES, Motion Blur und Nebel. Alle Effekte werden
  stärker, je näher das Monster ist. Dazu prozedurale PBR-Texturen mit
  Normal-Maps (dreckige Fliesen, abblätternde Farbe, Wasserflecken, Blut) und
  eine Taschenlampe mit Lichtmuster und weichen Schatten.
- **Monster-KI:** Patrouille → hört Geräusche (Rennen, Sicherungen) → sucht → jagt.
  Wegfindung per A* auf dem Raster, Kopfzucken, Lampen flackern in seiner Nähe,
  am Ende ein Jumpscare.
- **Audio:** Drone-Atmosphäre, Herzschlag (wird mit der Angst schneller),
  Flüstern, Knarren, Schreie, Sirene. Alles wird synthetisch erzeugt.
- **Story:** 5 Notizen über Patient 17.

## Dateien
| Skript | Zweck |
|---|---|
| `GameManager.cs` | Bootstrap, Ablauf, HUD, Jumpscare, Sieg/Tod |
| `ClinicBuilder.cs` | Level aus ASCII-Karte, Requisiten, Lichter, A*-Pfadsuche |
| `PlayerController.cs` | Ego-Steuerung, Taschenlampe, Ausdauer, Kopfwippen |
| `Monster.cs` | Patient 17: Körper, Animation, KI |
| `HorrorFX.cs` | Post-Processing, gesteuert über die Angst |
| `Interactables.cs` | Flackerlicht, Sicherungen, Batterien, Notizen, Tor |
| `ProcTex.cs` / `ProcAudio.cs` | erzeugen Texturen und Sounds |

Die Karte lässt sich in `ClinicBuilder.Map` bearbeiten:
`#` Wand, `.` Boden, `D` Tür, `B` Bett, `W` Rollstuhl, `F` Sicherung,
`A` Batterie, `N` Notiz, `E` Tor, `P` Spieler, `M` Monster.
