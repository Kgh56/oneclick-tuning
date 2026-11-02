#!/usr/bin/env python3
"""Checksummen-Korrektur ohne fremde DLLs.

Erkannt werden Summen-Bloecke, wie Bosch sie z. B. im ME7 als "Multipoint-Checksummen" ablegt:
Tabelleneintraege aus 4 x 32 Bit  [Start-Adresse, End-Adresse, Summe, ~Summe]. Die Summe ist die
Summe aller 16-Bit-Woerter von Start bis Ende.

Sicherheitsprinzip: Es wird nichts geraten. Ein Eintrag zaehlt nur, wenn die Summe im ORIGINAL
exakt nachgerechnet werden kann (Byte-Reihenfolge, Adress-Basis und Bereichsende werden dabei
ermittelt). Korrigiert wird nur, wenn
  - alle Aenderungen im bearbeiteten File innerhalb der geprueften Bereiche liegen und
  - die Tabelle selbst (Start/Ende) nicht veraendert wurde.
Ob es fuer ein Steuergeraet weitere, hier unbekannte Checksummen gibt, zeigt der Archiv-Test
(archiv_test): Er rechnet die von WinOLS korrigierten Files im Archiv nach.
"""
from __future__ import annotations

import array
import sys

BASEN = (0x800000, 0x0, 0x80000000, 0xA0000000)   # moegliche Adress-Basen (C167: 0x800000)
MIN_BEREICH = 0x20


def _woerter32(daten: bytes, versatz: int, endian: str) -> array.array:
    """32-Bit-Woerter ab 'versatz' (Schritt 4)."""
    n = (len(daten) - versatz) // 4
    a = array.array("I", daten[versatz:versatz + n * 4])
    if (endian == ">") == (sys.byteorder == "little"):
        a.byteswap()
    return a


def summe16(daten: bytes, start: int, ende: int, endian: str) -> int:
    """Summe der 16-Bit-Woerter in daten[start:ende] (32 Bit, Ueberlauf wird abgeschnitten)."""
    a = array.array("H", daten[start:ende])
    if (endian == ">") == (sys.byteorder == "little"):
        a.byteswap()
    return sum(a) & 0xFFFFFFFF


def finde_summen(daten: bytes) -> list[dict]:
    """Alle Summen-Bloecke, die sich im File exakt nachrechnen lassen."""
    gefunden = []
    laenge = len(daten)
    for endian in ("<", ">"):
        for versatz in (0, 2):
            w = _woerter32(daten, versatz, endian)
            for k in range(len(w) - 3):
                s = w[k + 2]
                if s ^ w[k + 3] != 0xFFFFFFFF or s == 0 or s == 0xFFFFFFFF:
                    continue
                a, e = w[k], w[k + 1]
                if a >= e or a & 1:
                    continue
                pos = versatz + 4 * k
                for basis in BASEN:
                    if not (basis <= a and e - basis < laenge):
                        continue
                    start = a - basis
                    for ende in (e - basis + 1, e - basis):   # Ende einschliesslich (ueblich) oder ausschliesslich
                        if ende - start < MIN_BEREICH or (ende - start) & 1:
                            continue
                        if summe16(daten, start, ende, endian) == s:
                            gefunden.append({"pos": pos, "start": start, "ende": ende, "endian": endian, "basis": basis})
                            break
                    else:
                        continue
                    break
    # Doppelte (gleiche Stelle) entfernen; Tabelleneintraege duerfen sich nicht ueberlappen
    gefunden.sort(key=lambda b: b["pos"])
    eindeutig = []
    for b in gefunden:
        if eindeutig and b["pos"] < eindeutig[-1]["pos"] + 16:
            continue
        eindeutig.append(b)
    return eindeutig


def summen_stellen(bloecke: list[dict]) -> list[tuple[int, int]]:
    """Bytes, die beim Korrigieren geschrieben werden (Summe + ~Summe), als (Start, Ende)."""
    return [(b["pos"] + 8, b["pos"] + 16) for b in bloecke]


def _schreibe(puffer: bytearray, b: dict):
    s = summe16(puffer, b["start"], b["ende"], b["endian"])
    fmt = "little" if b["endian"] == "<" else "big"
    puffer[b["pos"] + 8:b["pos"] + 12] = s.to_bytes(4, fmt)
    puffer[b["pos"] + 12:b["pos"] + 16] = (s ^ 0xFFFFFFFF).to_bytes(4, fmt)


def pruefe(daten: bytes, bloecke: list[dict]) -> list[bool]:
    """Stimmt jede Summe im File?"""
    erg = []
    for b in bloecke:
        fmt = "little" if b["endian"] == "<" else "big"
        s = int.from_bytes(daten[b["pos"] + 8:b["pos"] + 12], fmt)
        n = int.from_bytes(daten[b["pos"] + 12:b["pos"] + 16], fmt)
        erg.append(s ^ n == 0xFFFFFFFF and summe16(daten, b["start"], b["ende"], b["endian"]) == s)
    return erg


def unterschiede(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Geaenderte Bereiche als (Start, Ende), ohne Zusammenfassen."""
    erg, i, n = [], 0, min(len(a), len(b))
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            erg.append((i, j))
            i = j
        else:
            i += 1
    return erg


def _ueberlappt(x: tuple[int, int], y: tuple[int, int]) -> bool:
    return x[0] < y[1] and y[0] < x[1]


class NichtMoeglich(Exception):
    """Checksumme kann (sicher) nicht automatisch korrigiert werden."""


def korrigiere(ori: bytes, mod: bytes, bloecke: list[dict] | None = None) -> dict:
    """Checksummen im bearbeiteten File neu berechnen. Wirft NichtMoeglich mit Begruendung."""
    if len(ori) != len(mod):
        raise NichtMoeglich("Original und bearbeitetes File sind unterschiedlich groß.")
    if ori == mod:
        raise NichtMoeglich("Das bearbeitete File ist identisch mit dem Original.")
    bloecke = finde_summen(ori) if bloecke is None else bloecke
    if not bloecke:
        raise NichtMoeglich("Im Original wurde keine Checksumme gefunden, die wir sicher nachrechnen können.")
    tabelle = [(b["pos"], b["pos"] + 8) for b in bloecke]               # Start/Ende-Felder
    stellen = summen_stellen(bloecke)
    for st in stellen:                                                   # kein Kreisbezug
        if any(_ueberlappt(st, (b["start"], b["ende"])) for b in bloecke):
            raise NichtMoeglich("Diese Checksummen-Art wird noch nicht unterstützt.")
    aenderungen = unterschiede(ori, mod)
    for u in aenderungen:
        if any(_ueberlappt(u, t) for t in tabelle):
            raise NichtMoeglich("Im bearbeiteten File wurde die Checksummen-Tabelle verändert.")
    bereiche = [(b["start"], b["ende"]) for b in bloecke]
    for u in aenderungen:
        if all(_ueberlappt(u, st) for st in stellen if _ueberlappt(u, st)) and any(_ueberlappt(u, st) for st in stellen):
            continue                                                     # nur alte Summe geaendert
        for i in range(u[0], u[1]):
            if not any(s <= i < e for s, e in bereiche) and not any(s <= i < e for s, e in stellen):
                raise NichtMoeglich(f"Es gibt Änderungen außerhalb der geprüften Bereiche (bei 0x{i:X}). "
                                    "Dafür können wir die Checksumme nicht sicher berechnen.")
    neu = bytearray(mod)
    for b in bloecke:
        _schreibe(neu, b)
    if not all(pruefe(bytes(neu), bloecke)):
        raise NichtMoeglich("Die Prüfung nach dem Korrigieren ist fehlgeschlagen.")
    geaendert = sum(1 for st in stellen if bytes(neu[st[0]:st[1]]) != mod[st[0]:st[1]])
    return {"daten": bytes(neu), "bloecke": len(bloecke), "korrigiert": geaendert}


def archiv_pruefung(ori: bytes, mod: bytes, bloecke: list[dict] | None = None) -> dict:
    """Ein von WinOLS korrigiertes Archiv-File nachrechnen.

    gleich:      unsere Korrektur ergibt exakt dieselben Bytes wie WinOLS
    unbekannt:   kleine Aenderungen (<= 8 Byte) ausserhalb bekannter Summen - koennten weitere
                 Checksummen sein (oder winzige Kennfeld-/Schalter-Aenderungen)
    """
    bloecke = finde_summen(ori) if bloecke is None else bloecke
    erg = {"bloecke": len(bloecke), "gleich": False, "fehler": "", "unbekannt": [], "summen_geaendert": 0}
    if not bloecke:
        erg["fehler"] = "keine Checksumme erkannt"
        return erg
    stellen = summen_stellen(bloecke)
    erg["unbekannt"] = [f"0x{s:X} ({e - s} B)" for s, e in unterschiede(ori, mod)
                        if e - s <= 8 and not any(_ueberlappt((s, e), st) for st in stellen)][:20]
    roh = bytearray(mod)                                   # WinOLS-Summen zuruecksetzen ...
    for s, e in stellen:
        roh[s:e] = ori[s:e]
    try:
        k = korrigiere(ori, bytes(roh), bloecke)           # ... und selbst rechnen
    except NichtMoeglich as e:
        erg["fehler"] = str(e)
        return erg
    erg["gleich"] = k["daten"] == mod
    erg["summen_geaendert"] = k["korrigiert"]
    if not erg["gleich"]:
        erg["fehler"] = "Ergebnis weicht von WinOLS ab"
    return erg


if __name__ == "__main__":   # python3 checksumme.py ORI [MOD]
    o = open(sys.argv[1], "rb").read()
    bl = finde_summen(o)
    print(f"{len(bl)} Summen-Bloecke gefunden")
    for b in bl:
        print(f"  Tabelle 0x{b['pos']:X}: 0x{b['start']:X}-0x{b['ende']:X} {b['endian']} Basis 0x{b['basis']:X}")
    if len(sys.argv) > 2:
        print(archiv_pruefung(o, open(sys.argv[2], "rb").read(), bl))
