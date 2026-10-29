#!/usr/bin/env python3
"""
OneClick Tuning - Kern

Lernt aus einem Archiv von ORI/Tuning-Paaren und ueberträgt die Aenderungen
automatisch auf neue Originaldateien.

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
    python oneclick.py index                      Archiv einlesen
    python oneclick.py info   <datei.bin>         Datei erkennen (ECU, Softwarenummern)
    python oneclick.py tune   <datei.bin> [-o stage1] [--ausgabe ordner]
    python oneclick.py lernen <ori.bin> <mod.bin> --name <ordner> [-o stage1]

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

# Angebotene Optionen (Dateiname im Archivordner = <option>.bin)
OPTIONEN = ["stage1", "stage2", "startstopp", "vmax", "popsbangs", "launch"]

MERGE_LUECKE = 8      # Aenderungen mit kleinerem Abstand werden zu einem Block zusammengefasst
KONTEXT = 16          # Bytes vor/nach einem Block fuer die Mustersuche
CHUNK = 256           # Blockgroesse fuer den Aehnlichkeitsvergleich
MAX_KANDIDATEN = 5    # So viele aehnliche Archiv-Files werden fuer die Uebertragung probiert
MIN_SICHERHEIT = 100.0  # Ab dieser Sicherheit (%) wird automatisch ausgeliefert

ECU_MUSTER = re.compile(
    rb"(EDC1[67][A-Z]{1,2}\d{1,2}|MEDC?1[67]\.\d+(?:\.\d+)?|MEVD1[67]\.\d+(?:\.\d+)?"
    rb"|MG1[A-Z]{2}\d{3}|MD1[A-Z]{2}\d{3}|SID\d{3}|SIMOS\s?\d+(?:\.\d+)?|PCR2\.1|DCM\d\.\d+)"
)
BOSCH_SW = re.compile(rb"1037\d{6}")
BOSCH_HW = re.compile(rb"0281\d{6}|0261\d{6}")
VAG_TEILENR = re.compile(rb"0\d[A-Z]9\d{5}[A-Z]{0,2}")


# ---------------------------------------------------------------------------
# Erkennung
# ---------------------------------------------------------------------------

def erkenne(daten: bytes) -> dict:
    def finde(muster):
        return sorted({m.decode("ascii", "ignore") for m in muster.findall(daten)})

    return {
        "groesse": len(daten),
        "sha256": hashlib.sha256(daten).hexdigest(),
        "ecu": finde(ECU_MUSTER),
        "bosch_sw": finde(BOSCH_SW),
        "bosch_hw": finde(BOSCH_HW),
        "vag_teilenr": finde(VAG_TEILENR),
    }


def chunk_hashes(daten: bytes) -> set:
    return {
        hashlib.blake2b(daten[i:i + CHUNK], digest_size=8).digest()
        for i in range(0, len(daten) - CHUNK + 1, CHUNK)
    }


def aehnlichkeit(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


# ---------------------------------------------------------------------------
# Unterschiede ORI -> MOD
# ---------------------------------------------------------------------------

def finde_bloecke(ori: bytes, mod: bytes) -> list:
    """Zusammenhaengende geaenderte Bereiche als (offset, laenge)."""
    if len(ori) != len(mod):
        raise ValueError("ORI und MOD haben unterschiedliche Groessen")
    bloecke = []
    start = ende = None
    for i, (a, b) in enumerate(zip(ori, mod)):
        if a != b:
            if start is None:
                start = i
            elif i - ende > MERGE_LUECKE:
                bloecke.append((start, ende - start + 1))
                start = i
            ende = i
    if start is not None:
        bloecke.append((start, ende - start + 1))
    return bloecke


def finde_eindeutig(daten: bytes, muster: bytes) -> int:
    """Position, wenn das Muster genau einmal vorkommt, sonst -1."""
    pos = daten.find(muster)
    if pos < 0 or daten.find(muster, pos + 1) >= 0:
        return -1
    return pos


def uebertrage(neu: bytes, ori: bytes, mod: bytes) -> tuple:
    """Ueberträgt die Aenderungen ORI->MOD auf NEU. Gibt (ergebnis, bericht) zurueck."""
    ergebnis = bytearray(neu)
    bloecke = finde_bloecke(ori, mod)
    gesamt = sum(l for _, l in bloecke)
    uebertragen = 0
    versatz = 0          # zuletzt gefundene Verschiebung, wird zuerst probiert
    belegt = []
    details = []

    for off, laenge in bloecke:
        ori_block = ori[off:off + laenge]
        vor = ori[max(0, off - KONTEXT):off]
        nach = ori[off + laenge:off + laenge + KONTEXT]
        muster = vor + ori_block + nach

        ziel = -1
        methode = None
        # 1) gleiche Position bzw. bekannter Versatz
        for d in dict.fromkeys((0, versatz)):
            p = off + d - len(vor)
            if p >= 0 and neu[p:p + len(muster)] == muster:
                ziel, methode = off + d, "Position" if d == 0 else "Versatz"
                break
        # 2) Mustersuche mit Kontext
        if ziel < 0:
            p = finde_eindeutig(neu, muster)
            if p >= 0:
                ziel, methode = p + len(vor), "Suche"
        # 3) Mustersuche ohne Kontext (nur bei ausreichend langen Bloecken)
        if ziel < 0 and laenge >= 32:
            p = finde_eindeutig(neu, ori_block)
            if p >= 0:
                ziel, methode = p, "Suche (ohne Kontext)"

        if ziel >= 0 and not any(ziel < e and ziel + laenge > s for s, e in belegt):
            ergebnis[ziel:ziel + laenge] = mod[off:off + laenge]
            belegt.append((ziel, ziel + laenge))
            uebertragen += laenge
            versatz = ziel - off
            details.append((off, ziel, laenge, methode))
        else:
            details.append((off, None, laenge, "NICHT GEFUNDEN"))

    sicherheit = 100.0 * uebertragen / gesamt if gesamt else 0.0
    return bytes(ergebnis), {
        "bloecke": len(bloecke),
        "bytes_gesamt": gesamt,
        "bytes_uebertragen": uebertragen,
        "sicherheit": sicherheit,
        "details": details,
    }


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


def ist_ecu_datei(name: str) -> bool:
    # Versteckte Dateien, Syncthing-Temp- und Konfliktdateien ignorieren
    if name.startswith(".") or name.startswith("~") or ".sync-conflict" in name:
        return False
    return Path(name).suffix.lower() in ENDUNGEN


def klassifiziere(namen: list) -> tuple:
    """Ordnet Dateinamen zu: (ori-Name oder None, {option: name})."""
    namen = [n for n in namen if ist_ecu_datei(n)]
    ori = next((n for n in namen if Path(n).stem.lower() == "ori"), None) \
        or next((n for n in namen if MUSTER_ORI.search(Path(n).stem.lower())), None) \
        or next((n for n in namen if Path(n).suffix.lower() in (".ori", ".org")), None)
    optionen = {}
    for n in namen:
        if n == ori:
            continue
        stamm = Path(n).stem.lower()
        for opt, muster in MUSTER_OPTION.items():
            if (stamm == opt or muster.search(stamm)) and opt not in optionen:
                optionen[opt] = n
                break
    rest = [n for n in namen if n != ori and n not in optionen.values()]
    if ori and not optionen and len(rest) == 1:
        optionen["stage1"] = rest[0]
    return ori, optionen


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
            optionen[opt] = {"datei": name, "bloecke": len(bloecke), "bytes": sum(l for _, l in bloecke)}
        if not optionen:
            print(f"  ! {ordner.name}: keine Options-Datei erkannt")
            continue
        info = erkenne(ori)
        eintraege.append({"name": ordner.name, "ori_datei": ori_name, **info, "optionen": optionen})
        print(f"  + {ordner.name}: {', '.join(optionen)} | ECU {', '.join(info['ecu']) or '?'}")

    index = {"eintraege": eintraege, "zeit": time.time()}
    tmp = INDEX_DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    tmp.replace(INDEX_DATEI)
    print(f"{len(eintraege)} Eintraege im Index.")
    return index


def lade_index() -> dict:
    if not INDEX_DATEI.exists():
        return baue_index()
    return json.loads(INDEX_DATEI.read_text())


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

def cmd_info(args):
    info = erkenne(Path(args.datei).read_bytes())
    for k, v in info.items():
        print(f"{k:12}: {', '.join(v) if isinstance(v, list) else v}")


def cmd_index(args):
    baue_index()


def lerne(ori: bytes, mod: bytes, name: str, option: str = "stage1") -> Path:
    """Neues ORI/Mod-Paar ins Archiv aufnehmen und Index neu bauen."""
    if option not in OPTIONEN:
        raise ValueError(f"Unbekannte Option '{option}'. Erlaubt: {', '.join(OPTIONEN)}")
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


def tune(neu: bytes, option: str = "stage1", min_sicherheit: float = MIN_SICHERHEIT) -> dict:
    """Option auf ein Original anwenden.

    Rueckgabe: status (AUTOMATISCH / PRUEFEN / MANUELL), sicherheit, quelle,
    ergebnis (bytes oder None), info, bericht (Textzeilen).
    """
    if option not in OPTIONEN:
        raise ValueError(f"Unbekannte Option '{option}'. Erlaubt: {', '.join(OPTIONEN)}")
    info = erkenne(neu)
    kandidaten = [e for e in lade_index()["eintraege"] if option in e["optionen"]]
    bericht = [f"Option     : {option}",
               f"ECU        : {', '.join(info['ecu']) or '?'}",
               f"Software   : {', '.join(info['bosch_sw'] + info['vag_teilenr']) or '?'}"]
    erg = {"status": "MANUELL", "sicherheit": 0.0, "quelle": None, "ergebnis": None,
           "info": info, "bericht": bericht}

    # 1) Identisches Original im Archiv
    treffer = next((e for e in kandidaten if e["sha256"] == info["sha256"]), None)
    if treffer:
        erg.update(status="AUTOMATISCH", sicherheit=100.0, quelle=treffer["name"],
                   ergebnis=archiv_datei(treffer, option).read_bytes())
        rep = None
    else:
        # 2) Aehnlichste Archiv-Files suchen und Uebertragung probieren
        neu_hashes = chunk_hashes(neu)
        bewertet = []
        for e in kandidaten:
            ori = archiv_datei(e).read_bytes()
            score = aehnlichkeit(neu_hashes, chunk_hashes(ori))
            gleiche_sw = bool(set(e["bosch_sw"] + e["vag_teilenr"]) & set(info["bosch_sw"] + info["vag_teilenr"]))
            gleiche_ecu = bool(set(e["ecu"]) & set(info["ecu"]))
            gleiche_groesse = e["groesse"] == info["groesse"]
            # Blockvergleich versagt bei verschobenen Daten, daher zaehlen Erkennungsmerkmale mit.
            # Ob ein Kandidat wirklich passt, entscheidet danach die Mustersuche.
            gesamt = score + 0.3 * gleiche_sw + 0.2 * gleiche_ecu + 0.1 * gleiche_groesse
            bewertet.append((gesamt, score, e))
        bewertet.sort(key=lambda t: t[0], reverse=True)

        bestes = None
        for gesamt, score, e in bewertet[:MAX_KANDIDATEN]:
            if gesamt < 0.05:
                continue
            ori = archiv_datei(e).read_bytes()
            mod = archiv_datei(e, option).read_bytes()
            daten, rep = uebertrage(neu, ori, mod)
            bericht.append(f"  Kandidat {e['name']}: Aehnlichkeit {score*100:.1f} %, "
                           f"uebertragen {rep['sicherheit']:.1f} %")
            if bestes is None or rep["sicherheit"] > bestes[1]["sicherheit"]:
                bestes = (daten, rep, e)
            if rep["sicherheit"] >= 100.0:
                break

        if bestes is None or bestes[1]["bytes_uebertragen"] == 0:
            bericht.append("Status     : MANUELL - kein passendes File im Archiv")
            return erg
        daten, rep, treffer = bestes
        erg.update(status="AUTOMATISCH" if rep["sicherheit"] >= min_sicherheit else "PRUEFEN",
                   sicherheit=rep["sicherheit"], quelle=treffer["name"], ergebnis=daten)

    bericht += [f"Quelle     : {erg['quelle']}",
                f"Sicherheit : {erg['sicherheit']:.1f} %",
                f"Status     : {erg['status']}",
                "Checksumme : NICHT korrigiert -> Flash-Tool / WinOLS"]
    if rep:
        bericht.append(f"Bloecke    : {rep['bloecke']}, Bytes {rep['bytes_uebertragen']}/{rep['bytes_gesamt']}")
        for off, z, laenge, methode in rep["details"]:
            zt = f"0x{z:06X}" if z is not None else "   ---  "
            bericht.append(f"   0x{off:06X} -> {zt}  {laenge:5d} Bytes  {methode}")
    return erg


def cmd_lernen(args):
    try:
        ziel = lerne(Path(args.ori).read_bytes(), Path(args.mod).read_bytes(), args.name, args.option)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Gespeichert in {ziel}")


def cmd_tune(args):
    pfad = Path(args.datei)
    try:
        erg = tune(pfad.read_bytes(), args.option, args.min_sicherheit)
    except ValueError as e:
        sys.exit(str(e))

    ausgabe = Path(args.ausgabe or pfad.parent)
    ausgabe.mkdir(parents=True, exist_ok=True)
    bericht = [f"Datei      : {pfad.name}"] + erg["bericht"]
    if erg["ergebnis"] is not None:
        endung = "" if erg["status"] == "AUTOMATISCH" else "_PRUEFEN"
        ziel = ausgabe / f"{pfad.stem}_{args.option}{endung}.bin"
        ziel.write_bytes(erg["ergebnis"])
        bericht.append(f"Ausgabe    : {ziel}")
    text = "\n".join(bericht)
    print(text)
    (ausgabe / f"{pfad.stem}_{args.option}_bericht.txt").write_text(text + "\n")
    return {"AUTOMATISCH": 0, "PRUEFEN": 1, "MANUELL": 2}[erg["status"]]


def main():
    p = argparse.ArgumentParser(description="OneClick Tuning")
    sub = p.add_subparsers(dest="befehl", required=True)

    sub.add_parser("index", help="Archiv einlesen").set_defaults(func=cmd_index)

    s = sub.add_parser("info", help="Datei erkennen")
    s.add_argument("datei")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("tune", help="Option auf Original anwenden")
    s.add_argument("datei")
    s.add_argument("-o", "--option", default="stage1")
    s.add_argument("--ausgabe", help="Ausgabeordner (Standard: neben der Datei)")
    s.add_argument("--min-sicherheit", type=float, default=MIN_SICHERHEIT)
    s.set_defaults(func=cmd_tune)

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
