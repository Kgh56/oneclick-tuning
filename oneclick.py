#!/usr/bin/env python3
"""
OneClick Tuning - Kern

Sucht zu einem Kunden-Original einen 100-%-Treffer im Archiv von ORI/Tuning-Paaren:
  - identisch: das Original ist Byte fuer Byte gleich, oder
  - gleiche Stellen: gleiche Groesse und an jeder Stelle, die das Tuning aendert
    (plus 16 Bytes davor/danach), exakt gleich - an derselben Adresse, ohne Suche.
Es gibt keine Uebertragung auf "aehnliche" Softwarestaende.

Archiv-Aufbau (ein Ordner pro Fahrzeug/Softwarestand):
    archiv/
      golf7_20tdi_03L906018JL/
        ori.bin
        stage1.bin
        startstopp.bin      (optional, weitere Optionen)

Die Dateinamen duerfen auch anders lauten (z. B. "Golf7_ORI.bin" und "Golf7_Stage1.bin"),
siehe klassifiziere(). Liegen genau zwei Dateien im Ordner und eine ist das Original,
gilt die andere als Stage 1.

Befehle:
    python oneclick.py index                       Archiv einlesen
    python oneclick.py info    <datei.bin>         Datei erkennen (ECU, Softwarenummern)
    python oneclick.py pruefen <datei.bin> [--ausgabe ordner] [--nur-identisch]
    python oneclick.py lernen  <ori.bin> <mod.bin> --name <ordner> [-o stage1]

Hinweis: Checksummen werden NICHT korrigiert -> Flash-Tool / WinOLS.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIV = BASE / "archiv"
INDEX_DATEI = BASE / "index.json"
OPTIONEN_DATEI = BASE / "optionen.json"   # selbst angelegte Loesungen (z. B. Drallklappen)

# Feste Loesungen (Dateiname im Archivordner = <schluessel>.bin)
STANDARD_OPTIONEN = {
    "stage1": "Stage 1",
    "stage2": "Stage 2",
    "startstopp": "Start/Stopp aus",
    "vmax": "Vmax offen",
    "popsbangs": "Pops & Bangs",
    "launch": "Launch Control",
}
# Rueckruesten: Kunde laedt ein getuntes File hoch und bekommt das Original zurueck
ORIGINAL = "original"
ORIGINAL_NAME = "Original (Rückrüsten)"
INDEX_VERSION = 6
MAX_ABWEICHUNG = 0.05   # Rueckruesten ueber Softwarenummer: hoechstens 5 % der Bytes duerfen abweichen

# Abschaltungen der Abgasreinigung werden nicht unterstuetzt
GESPERRT = re.compile(
    r"dpf|adblue|ad[\s_-]*blue|partikel|harnstoff|katalysator|lambda|abgasr(ü|ue)ckf|nox"
    r"|(^|[^a-z0-9])(egr|agr|scr|fap|kat|o2|opf|gpf)([^a-z0-9]|$)"
)

MERGE_LUECKE = 8      # Aenderungen mit kleinerem Abstand werden zu einem Block zusammengefasst
KONTEXT = 16          # Bytes vor/nach jeder Aenderung, die zusaetzlich identisch sein muessen

# Steuergeraete-Bezeichnungen, wie sie im File stehen (oft mit "_", z. B. "EDC17_C46", "MED17_5_2")
ECU_MUSTER = re.compile(
    rb"(?<![A-Z0-9])("
    rb"EDC1[5-7][_ ]?[A-Z]{1,3}\d{1,2}"                          # Bosch Diesel: EDC15C2, EDC16U31, EDC17C46, EDC17CP14
    rb"|(?:MEVD|MEV|MED|ME)[_ ]?(?:7|9|17)(?:[._]\d{1,2}){1,3}"   # Bosch Benzin: ME7.5, MED9.1, MED17.5.2, MEVD17.2.9
    rb"|M[GD]1[_ ]?[A-Z]{2}\d{3}"                                # Bosch MG1CS011, MD1CS004
    rb"|SID[_ ]?\d{3}|SIMOS[_ ]?\d{1,2}(?:[._]\d{1,2}){0,2}|PCR[_ ]?2[._]1|EMS[_ ]?\d{4}"   # Siemens/Continental
    rb"|DC[MU][_ ]?\d{1,2}[._]\d{1,2}"                           # Delphi DCM3.5, DCM6.2
    rb"|IAW[_ ]?\d{1,2}[A-Z]{1,3}|MJD[_ ]?\d[A-Z0-9]{1,4}"       # Magneti Marelli
    rb")(?![A-Z0-9])"
)
BOSCH_SW = re.compile(rb"(?<!\d)1037\d{6}(?!\d)")
BOSCH_HW = re.compile(rb"(?<!\d)02[68]1\d{6}(?!\d)")
# VAG-Teilenummern von Steuergeraeten: xxx 906/907/927 xxx (z. B. 03L906018JL, 8V0906259, 0AM927769)
VAG_TEILENR = re.compile(rb"(?<![A-Z0-9])[0-9][A-Z0-9]{2}9(?:06|07|27)\d{3}[A-Z]{0,3}(?![A-Z0-9])")


def ecu_name(roh: str) -> str:
    """Einheitliche Schreibweise: 'EDC17_C46' -> 'EDC17C46', 'MED17_5_2' -> 'MED17.5.2'."""
    roh = roh.replace(" ", "")
    if roh.startswith(("EDC", "MG1", "MD1", "SID", "EMS", "IAW", "MJD")):
        return roh.replace("_", "")
    return roh.replace("_", ".")


# ---------------------------------------------------------------------------
# Erkennung
# ---------------------------------------------------------------------------

def erkenne(daten: bytes) -> dict:
    def finde(muster):
        return sorted({m.decode("ascii", "ignore") for m in muster.findall(daten)})

    return {
        "groesse": len(daten),
        "sha256": hashlib.sha256(daten).hexdigest(),
        "ecu": sorted({ecu_name(m.decode("ascii", "ignore")) for m in ECU_MUSTER.findall(daten)}),
        "bosch_sw": finde(BOSCH_SW),
        "bosch_hw": finde(BOSCH_HW),
        "vag_teilenr": finde(VAG_TEILENR),
    }


# ---------------------------------------------------------------------------
# Unterschiede ORI -> MOD und 100-%-Pruefung
# ---------------------------------------------------------------------------

def finde_bloecke(ori: bytes, mod: bytes) -> list:
    """Zusammenhaengende geaenderte Bereiche als [offset, laenge]."""
    if len(ori) != len(mod):
        raise ValueError("ORI und MOD haben unterschiedliche Groessen")
    bloecke = []
    start = ende = None
    schritt = 4096
    for basis in range(0, len(ori), schritt):
        if ori[basis:basis + schritt] == mod[basis:basis + schritt]:
            continue   # schnell ueber unveraenderte Bereiche springen
        for i in range(basis, min(basis + schritt, len(ori))):
            if ori[i] != mod[i]:
                if start is None:
                    start = i
                elif i - ende > MERGE_LUECKE:
                    bloecke.append([start, ende - start + 1])
                    start = i
                ende = i
    if start is not None:
        bloecke.append([start, ende - start + 1])
    return bloecke


def gleiche_stellen(neu: bytes, ori: bytes, mod: bytes, bloecke: list):
    """Ergebnis-File, wenn NEU an jeder geaenderten Stelle (plus Umgebung) exakt dem ORI gleicht.

    Gleiche Dateigroesse, gleiche Adressen, keine Suche. Sonst None.
    """
    if len(neu) != len(ori) or not bloecke:
        return None
    for off, laenge in bloecke:
        von, bis = max(0, off - KONTEXT), off + laenge + KONTEXT
        if neu[von:bis] != ori[von:bis]:
            return None
    ergebnis = bytearray(neu)
    for off, laenge in bloecke:
        ergebnis[off:off + laenge] = mod[off:off + laenge]
    return bytes(ergebnis)


def finde_loesungen(neu: bytes, nur_identisch: bool = False) -> tuple:
    """Alle Optionen, fuer die es einen 100-%-Treffer im Archiv gibt.

    Zusaetzlich ORIGINAL, wenn NEU ein getuntes File aus dem Archiv ist (Rueckruesten).
    Rueckgabe: (info, {option: {"daten": bytes, "quelle": name, "art": "identisch" | "gleiche Stellen"}})
    """
    info = erkenne(neu)

    def nummern_passen(e: dict) -> bool:
        # Sind Softwarenummern bzw. Teilenummern in beiden Files lesbar, muessen sie uebereinstimmen
        for feld in ("bosch_sw", "vag_teilenr"):
            a, b = set(info[feld]), set(e[feld])
            if a and b and a != b:
                return False
        return True

    kandidaten = [e for e in lade_index()["eintraege"] if e["groesse"] == len(neu)]
    kandidaten.sort(key=lambda e: e["sha256"] != info["sha256"])   # identische zuerst
    loesungen = {}
    for e in kandidaten:
        identisch = e["sha256"] == info["sha256"]
        if not identisch and (nur_identisch or not nummern_passen(e)):
            continue
        offen = [o for o in e["optionen"] if o not in loesungen]
        if not offen:
            continue
        ori = None if identisch else archiv_datei(e).read_bytes()
        for opt in offen:
            mod = archiv_datei(e, opt).read_bytes()
            daten = mod if identisch else gleiche_stellen(neu, ori, mod, e["optionen"][opt]["bloecke"])
            if daten is not None:
                loesungen[opt] = {"daten": daten, "quelle": e["name"],
                                  "art": "identisch" if identisch else "gleiche Stellen"}

    # Rueckruesten: passt NEU zu einem Tuning-File im Archiv? Dann gibt es das Original.
    # Gleiche Regeln, nur mit vertauschten Rollen (Tuning-File <-> Original).
    treffer = [(e, opt, d) for e in kandidaten for opt, d in e["optionen"].items()]
    treffer.sort(key=lambda t: t[2].get("sha256") != info["sha256"])   # identische zuerst
    for e, opt, d in treffer:
        identisch = d.get("sha256") == info["sha256"]
        if not identisch and (nur_identisch or not nummern_passen(e)):
            continue
        ori = archiv_datei(e).read_bytes()
        daten = ori if identisch else gleiche_stellen(neu, archiv_datei(e, opt).read_bytes(), ori, d["bloecke"])
        if daten is not None:
            loesungen[ORIGINAL] = {"daten": daten, "quelle": e["name"],
                                   "art": "identisch" if identisch else "gleiche Stellen"}
            break

    # Rueckruesten ueber die Softwarenummer: fremdes Tuning-File, im Archiv liegt (nur) das Original.
    # Kein Byte-fuer-Byte-Nachweis moeglich -> eigene Art, der Admin prueft vor der Freigabe.
    if ORIGINAL not in loesungen and not nur_identisch and info["bosch_sw"]:
        for e in kandidaten:
            if e["sha256"] == info["sha256"] or set(e["bosch_sw"]) != set(info["bosch_sw"]):
                continue
            if not nummern_passen(e) or (info["bosch_hw"] and e["bosch_hw"] and set(info["bosch_hw"]) != set(e["bosch_hw"])):
                continue
            ori = archiv_datei(e).read_bytes()
            if abweichende_bytes(neu, ori, int(len(ori) * MAX_ABWEICHUNG)) is not None:
                loesungen[ORIGINAL] = {"daten": ori, "quelle": e["name"], "art": "softwarenummer"}
                break
    return info, loesungen


def abweichende_bytes(a: bytes, b: bytes, grenze: int):
    """Anzahl unterschiedlicher Bytes (gleiche Laenge), oder None sobald mehr als grenze."""
    anzahl, schritt = 0, 4096
    for basis in range(0, len(a), schritt):
        x, y = a[basis:basis + schritt], b[basis:basis + schritt]
        if x != y:
            anzahl += sum(1 for p, q in zip(x, y) if p != q)
            if anzahl > grenze:
                return None
    return anzahl


def kombiniere(basis: bytes, dateien: list):
    """Mehrere fertige Files (gleiche Basis) zu einem zusammenfuehren.

    Uebernimmt jede Aenderung gegenueber der Basis. Aendern zwei Files dasselbe Byte
    unterschiedlich, ist die Kombination nicht sicher -> None.
    """
    ergebnis = bytearray(basis)
    gesetzt = bytearray(len(basis))
    for daten in dateien:
        if len(daten) != len(basis):
            return None
        for off, laenge in finde_bloecke(basis, daten):
            for i in range(off, off + laenge):
                if daten[i] != basis[i]:
                    if gesetzt[i] and ergebnis[i] != daten[i]:
                        return None
                    ergebnis[i] = daten[i]
                    gesetzt[i] = 1
    return bytes(ergebnis)


# ---------------------------------------------------------------------------
# Archiv / Index
# ---------------------------------------------------------------------------

ENDUNGEN = {".bin", ".ori", ".mod", ".org", ""}
MUSTER_ORI = re.compile(r"(^|[^a-z])(ori|orig|original|org)([^a-z]|$)")
MUSTER_OPTION = {
    "stage1": re.compile(r"stage[\s_-]*1|(^|[^a-z])st(g|age)?[\s_-]*1([^0-9]|$)|stufe[\s_-]*1"),
    "stage2": re.compile(r"stage[\s_-]*2|(^|[^a-z])st(g|age)?[\s_-]*2([^0-9]|$)|stufe[\s_-]*2"),
    "startstopp": re.compile(r"start[\s_-]*stop"),
    "vmax": re.compile(r"vmax|v[\s_-]max"),
    "popsbangs": re.compile(r"pops|bang|crackle|burble"),
    "launch": re.compile(r"launch"),
}


def schluessel(name: str) -> str:
    """'Drallklappen aus' -> 'drallklappenaus' (fuer Dateinamen und Vergleiche)."""
    name = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        name = name.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", name)


def eigene_optionen() -> dict:
    return json.loads(OPTIONEN_DATEI.read_text()) if OPTIONEN_DATEI.exists() else {}


def optionen() -> dict:
    """Alle Loesungen: {schluessel: Anzeigename}, feste zuerst."""
    return {**STANDARD_OPTIONEN, **eigene_optionen()}


def option_anlegen(name: str) -> str:
    name = " ".join(name.split())[:40]
    key = schluessel(name)[:30]
    if not key:
        raise ValueError("Bitte einen Namen eingeben.")
    if GESPERRT.search(name.lower()) or GESPERRT.search(key):
        raise ValueError("Lösungen, die die Abgasreinigung abschalten (DPF, AGR, AdBlue/SCR, Kat, Lambda …), "
                         "werden nicht unterstützt.")
    if key in ("ori", ORIGINAL) or MUSTER_ORI.search(key) or key in optionen():
        raise ValueError(f"„{name}“ gibt es schon oder der Name ist nicht erlaubt.")
    eigene = eigene_optionen()
    eigene[key] = name
    tmp = OPTIONEN_DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(eigene, indent=2, ensure_ascii=False))
    tmp.replace(OPTIONEN_DATEI)
    return key


def option_loeschen(key: str):
    eigene = eigene_optionen()
    if key not in eigene:
        raise ValueError("Feste Lösungen können nicht gelöscht werden.")
    benutzt = [e["name"] for e in lade_index()["eintraege"] if key in e["optionen"]]
    if benutzt:
        raise ValueError(f"„{eigene[key]}“ wird noch im Archiv benutzt ({', '.join(benutzt[:5])}). "
                         "Erst dort die Fahrzeuge löschen.")
    del eigene[key]
    tmp = OPTIONEN_DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(eigene, indent=2, ensure_ascii=False))
    tmp.replace(OPTIONEN_DATEI)


def ist_ecu_datei(name: str) -> bool:
    # Versteckte Dateien, Temp- und Konfliktdateien ignorieren
    if name.startswith(".") or name.startswith("~") or ".sync-conflict" in name:
        return False
    return Path(name).suffix.lower() in ENDUNGEN


def klassifiziere(namen: list) -> tuple:
    """Ordnet Dateinamen zu: (ori-Name oder None, {option: name})."""
    namen = [n for n in namen if ist_ecu_datei(n)]
    ori = next((n for n in namen if Path(n).stem.lower() == "ori"), None) \
        or next((n for n in namen if MUSTER_ORI.search(Path(n).stem.lower())), None) \
        or next((n for n in namen if Path(n).suffix.lower() in (".ori", ".org")), None)
    # Eigene Loesungen zuerst pruefen (spezifischer, z. B. "Stage 1 Plus")
    eigene = sorted(eigene_optionen(), key=len, reverse=True)
    gefunden = {}
    for n in namen:
        if n == ori:
            continue
        stamm = Path(n).stem.lower()
        key = next((k for k in eigene if k in schluessel(stamm) and k not in gefunden), None)
        if key is None:
            key = next((opt for opt, muster in MUSTER_OPTION.items()
                        if (stamm == opt or muster.search(stamm)) and opt not in gefunden), None)
        if key:
            gefunden[key] = n
    rest = [n for n in namen if n != ori and n not in gefunden.values()]
    if ori and not gefunden and len(rest) == 1:
        gefunden["stage1"] = rest[0]
    return ori, gefunden


def archiv_datei(eintrag: dict, option: str = None) -> Path:
    """Pfad der ORI- (option=None) oder Options-Datei eines Index-Eintrags."""
    name = eintrag["ori_datei"] if option is None else eintrag["optionen"][option]["datei"]
    return ARCHIV / eintrag["name"] / name


def baue_index() -> dict:
    eintraege = []
    if not ARCHIV.exists():
        ARCHIV.mkdir(parents=True)
    for ordner in sorted(p for p in ARCHIV.iterdir() if p.is_dir() and not p.name.startswith(".")):
        ori_name, gefunden = klassifiziere([p.name for p in ordner.iterdir() if p.is_file()])
        if not ori_name:
            print(f"  ! {ordner.name}: kein Original erkannt, uebersprungen")
            continue
        ori = (ordner / ori_name).read_bytes()
        optionen = {}
        for opt, name in gefunden.items():
            mod = (ordner / name).read_bytes()
            if len(mod) != len(ori):
                print(f"  ! {ordner.name}/{name}: andere Groesse als {ori_name}, uebersprungen")
                continue
            bloecke = finde_bloecke(ori, mod)
            if not bloecke:
                print(f"  ! {ordner.name}/{name}: identisch mit dem Original, uebersprungen")
                continue
            optionen[opt] = {"datei": name, "bloecke": bloecke, "sha256": hashlib.sha256(mod).hexdigest()}
        info = erkenne(ori)   # ohne Tuning-File: nur Original (fuer Rueckruesten ueber Softwarenummer)
        eintraege.append({"name": ordner.name, "ori_datei": ori_name, "ori_sha256": hashlib.sha256(ori).hexdigest(),
                          **info, "optionen": optionen})
        print(f"  + {ordner.name}: {', '.join(optionen) or 'nur Original'} | ECU {', '.join(info['ecu']) or '?'}")

    index = {"version": INDEX_VERSION, "eintraege": eintraege, "zeit": time.time()}
    tmp = INDEX_DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False))
    tmp.replace(INDEX_DATEI)
    print(f"{len(eintraege)} Eintraege im Index.")
    return index


def lade_index() -> dict:
    if not INDEX_DATEI.exists():
        return baue_index()
    index = json.loads(INDEX_DATEI.read_text())
    if index.get("version") != INDEX_VERSION:   # nach einem Update einmal neu einlesen
        return baue_index()
    return index


def lerne(ori: bytes, mod: bytes, name: str, option: str = "stage1") -> Path:
    """Neues ORI/Mod-Paar ins Archiv aufnehmen und Index neu bauen."""
    if option not in optionen():
        raise ValueError(f"Unbekannte Option '{option}'. Erlaubt: {', '.join(optionen())}")
    if len(ori) != len(mod):
        raise ValueError("ORI und Mod-Datei haben unterschiedliche Groessen")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ValueError("Name darf nur Buchstaben, Ziffern, . _ - enthalten")
    ziel = ARCHIV / name
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "ori.bin").write_bytes(ori)
    (ziel / f"{option}.bin").write_bytes(mod)
    baue_index()
    return ziel


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

def cmd_info(args):
    info = erkenne(Path(args.datei).read_bytes())
    for k, v in info.items():
        print(f"{k:12}: {', '.join(v) if isinstance(v, list) else v}")


def cmd_index(args):
    baue_index()


def cmd_pruefen(args):
    pfad = Path(args.datei)
    info, loesungen = finde_loesungen(pfad.read_bytes(), args.nur_identisch)
    print(f"ECU      : {', '.join(info['ecu']) or '?'}")
    print(f"Software : {', '.join(info['bosch_sw'] + info['vag_teilenr']) or '?'}")
    if not loesungen:
        print("Kein 100-%-Treffer im Archiv.")
        return 2
    ausgabe = Path(args.ausgabe or pfad.parent)
    ausgabe.mkdir(parents=True, exist_ok=True)
    for opt, l in loesungen.items():
        ziel = ausgabe / f"{pfad.stem}_{opt}.bin"
        ziel.write_bytes(l["daten"])
        print(f"{opt:10} <- {l['quelle']} ({l['art']}) -> {ziel}")
    print("Checksumme: NICHT korrigiert -> Flash-Tool / WinOLS")
    return 0


def cmd_lernen(args):
    try:
        ziel = lerne(Path(args.ori).read_bytes(), Path(args.mod).read_bytes(), args.name, args.option)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Gespeichert in {ziel}")


def main():
    p = argparse.ArgumentParser(description="OneClick Tuning")
    sub = p.add_subparsers(dest="befehl", required=True)

    sub.add_parser("index", help="Archiv einlesen").set_defaults(func=cmd_index)

    s = sub.add_parser("info", help="Datei erkennen")
    s.add_argument("datei")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("pruefen", help="100-%%-Treffer suchen und Files fuer alle gefundenen Optionen erzeugen")
    s.add_argument("datei")
    s.add_argument("--ausgabe", help="Ausgabeordner (Standard: neben der Datei)")
    s.add_argument("--nur-identisch", action="store_true", help="Nur komplett identische Originale")
    s.set_defaults(func=cmd_pruefen)

    s = sub.add_parser("lernen", help="Neues Paar ins Archiv aufnehmen")
    s.add_argument("ori")
    s.add_argument("mod")
    s.add_argument("--name", required=True)
    s.add_argument("-o", "--option", default="stage1")
    s.set_defaults(func=cmd_lernen)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
