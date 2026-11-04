#!/usr/bin/env python3
"""Erzeugt die Sounds für die Chiptuning-Firma per Klangsynthese.

Aufruf:  python3 tools/make_sounds.py
Ergebnis: roblox/sounds/*.ogg  (in Roblox hochladen, IDs in Config.lua eintragen)

Alle Schleifen (Motor, Turbo, Reifen, Hydraulik, Umgebung) sind nahtlos:
Sie enthalten eine ganze Zahl von Perioden und werden kreisförmig gefiltert.
Benötigt: numpy, scipy, ffmpeg (mit libvorbis).
"""
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100
OUT = Path(__file__).resolve().parent.parent / "sounds"
rng = np.random.default_rng(2002)


# ---------------------------------------------------------------- Hilfen
def circ_filter(x, sos):
    """Filtert x so, als wäre es endlos wiederholt (für nahtlose Schleifen)."""
    n = len(x)
    y = signal.sosfilt(sos, np.tile(x, 3))
    return y[n:2 * n]


def bp(lo, hi, order=2):
    return signal.butter(order, [lo, hi], btype="bandpass", fs=SR, output="sos")


def lp(f, order=2):
    return signal.butter(order, f, btype="lowpass", fs=SR, output="sos")


def hp(f, order=2):
    return signal.butter(order, f, btype="highpass", fs=SR, output="sos")


def peak(f, q=4.0):
    b, a = signal.iirpeak(f, q, fs=SR)
    return signal.tf2sos(b, a)


def normalize(x, level=0.89):
    m = np.max(np.abs(x))
    return x * (level / m) if m > 0 else x


def fade(x, ms_in=5, ms_out=30):
    n_in = int(SR * ms_in / 1000)
    n_out = int(SR * ms_out / 1000)
    x = x.copy()
    if n_in:
        x[:n_in] *= np.linspace(0, 1, n_in)
    if n_out:
        x[-n_out:] *= np.linspace(1, 0, n_out)
    return x


def save(name, x):
    OUT.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "x.wav"
        wavfile.write(wav, SR, (x * 32767).astype(np.int16))
        target = OUT / f"{name}.ogg"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "6", str(target)],
            check=True,
        )
    print(f"{target.name}: {len(x) / SR:.2f} s")


# ---------------------------------------------------------------- Motor
def engine(f_fire, dur, drive, bright, rough):
    """Viertakt-Vierzylinder: f_fire = Zündungen pro Sekunde."""
    n = int(SR * dur)
    pulses = int(round(f_fire * dur))
    period = n / pulses
    x = np.zeros(n)
    plen = int(SR * 0.02)
    t = np.arange(plen) / SR
    # Verbrennungsstoß: kurzer Knall mit Abklingen
    shape = np.exp(-t / 0.0035) * (1 - np.exp(-t / 0.0004))
    cyl = np.array([1.0, 0.86, 0.95, 0.8])  # leicht ungleiche Zylinder
    for k in range(pulses):
        pos = k * period + rng.normal(0, period * 0.012 * rough)
        amp = cyl[k % 4] * rng.uniform(0.9, 1.1)
        burst = shape * (0.6 + 0.4 * rng.standard_normal(plen)) * amp
        start = int(pos) % n
        idx = (start + np.arange(plen)) % n
        x[idx] += burst
    # Grundton und Oberton (ganzzahlige Perioden -> nahtlos)
    tt = np.arange(n) / SR
    body = 0.55 * np.sin(2 * np.pi * f_fire * tt) + 0.25 * np.sin(2 * np.pi * 2 * f_fire * tt + 0.7)
    body += 0.12 * np.sin(2 * np.pi * 0.5 * f_fire * tt + 1.3) * rough  # Nockenwellen-Wummern
    x = circ_filter(x, lp(bright)) * 1.4 + body * 0.35
    # Auspuff-Resonanzen
    x = circ_filter(x, peak(2 * f_fire, 3)) * 0.6 + x
    x = circ_filter(x, peak(170, 2.5)) * 0.4 + x
    # Grollen
    rumble = circ_filter(rng.standard_normal(n), lp(260)) * 0.25
    x = x + rumble
    x = circ_filter(x, hp(28))
    x = np.tanh(normalize(x, 1.0) * drive)
    return normalize(x, 0.85)


# ---------------------------------------------------------------- Turbo
def turbo(dur):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    f = 3200
    vib = 0.004 * np.sin(2 * np.pi * 3 * tt)  # 6 Perioden in 2 s -> nahtlos
    phase = 2 * np.pi * f * tt + 2 * np.pi * f * np.cumsum(vib) / SR * 0
    whine = np.sin(phase) * 0.5 + np.sin(2 * phase) * 0.12 + np.sin(1.5 * phase) * 0.05
    air = circ_filter(rng.standard_normal(n), bp(2200, 7000)) * 0.35
    x = whine * (1 + 0.15 * np.sin(2 * np.pi * 5 * tt)) + air
    return normalize(x, 0.7)


def blowoff():
    dur = 0.75
    n = int(SR * dur)
    tt = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # Filter wandert von hell zu dunkel ("Pschhh")
    out = np.zeros(n)
    seg = 512
    for i in range(0, n, seg):
        frac = i / n
        lo = 1800 - 1100 * frac
        hi = 9000 - 5000 * frac
        sos = bp(max(lo, 300), hi, 2)
        out[i:i + seg] = signal.sosfilt(sos, noise[i:i + seg])
    env = (1 - np.exp(-tt / 0.008)) * np.exp(-tt / 0.22)
    flutter = 1 + 0.25 * np.sin(2 * np.pi * 28 * tt) * np.exp(-tt / 0.3)
    return normalize(fade(out * env * flutter, 2, 60), 0.85)


def backfire():
    dur = 0.9
    n = int(SR * dur)
    x = np.zeros(n)
    t = 0.02
    while t < dur - 0.12:
        start = int(t * SR)
        plen = int(SR * 0.09)
        tt = np.arange(plen) / SR
        crack = rng.standard_normal(plen) * np.exp(-tt / 0.006)
        thump = np.sin(2 * np.pi * rng.uniform(60, 95) * tt) * np.exp(-tt / 0.03)
        pop = signal.sosfilt(lp(3500), crack) * 1.2 + thump * 0.9
        x[start:start + plen] += pop * rng.uniform(0.6, 1.0)
        t += rng.uniform(0.07, 0.16)
    x = np.tanh(normalize(x, 1.0) * 2.2)
    return normalize(fade(x, 1, 40), 0.9)


# ---------------------------------------------------------------- Reifen
def screech(dur):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    noise = circ_filter(rng.standard_normal(n), bp(900, 3200))
    tone = np.sin(2 * np.pi * 1650 * tt + 0.8 * np.sin(2 * np.pi * 7 * tt))
    tone2 = np.sin(2 * np.pi * 2310 * tt + 0.5 * np.sin(2 * np.pi * 11 * tt))
    x = noise * 0.6 + tone * 0.35 + tone2 * 0.18
    x *= 1 + 0.2 * np.sin(2 * np.pi * 4 * tt)
    return normalize(x, 0.75)


# ---------------------------------------------------------------- Werkstatt
def hydraulic(dur):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    hum = sum(np.sin(2 * np.pi * 100 * k * tt) / k for k in range(1, 7))
    flow = circ_filter(rng.standard_normal(n), bp(300, 1500)) * 0.5
    x = hum * 0.5 + flow
    x *= 1 + 0.08 * np.sin(2 * np.pi * 2 * tt)
    return normalize(x, 0.6)


# ---------------------------------------------------------------- Umgebung
def ambience(dur):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    # Wind: rosa-ähnliches Rauschen mit langsamer Lautstärkewelle
    wind = circ_filter(rng.standard_normal(n), lp(500))
    wind = circ_filter(wind, hp(40))
    wind *= 0.6 + 0.4 * np.sin(2 * np.pi * (1 / dur) * 2 * tt) ** 2
    x = normalize(wind, 0.25)
    # Vögel: kurze Tonfolgen, kreisförmig eingefügt
    for _ in range(int(dur * 0.9)):
        start = rng.integers(0, n)
        notes = rng.integers(2, 6)
        f0 = rng.uniform(2600, 4800)
        pos = start
        for _ in range(notes):
            ln = int(SR * rng.uniform(0.05, 0.12))
            t = np.arange(ln) / SR
            sweep = f0 * (1 + rng.uniform(-0.25, 0.25) * t / t[-1])
            chirp = np.sin(2 * np.pi * np.cumsum(sweep) / SR) * np.sin(np.pi * t / t[-1]) ** 2
            idx = (pos + np.arange(ln)) % n
            x[idx] += chirp * rng.uniform(0.05, 0.12)
            pos += ln + int(SR * rng.uniform(0.03, 0.09))
    return normalize(x, 0.6)


def horn():
    dur = 0.75
    n = int(SR * dur)
    tt = np.arange(n) / SR
    x = np.zeros(n)
    for f in (410.0, 505.0):  # Zweiklang wie eine Autohupe
        ph = 2 * np.pi * f * tt
        x += np.tanh(3 * np.sin(ph)) * 0.5 + 0.15 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
    x = signal.sosfilt(bp(250, 3500), x)
    env = np.minimum(1, tt / 0.015) * np.minimum(1, (dur - tt) / 0.06)
    return normalize(x * env, 0.85)


# ---------------------------------------------------------------- Effekte
def tone(f, dur, decay, harmonics=(1.0,), detune=0.0):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    x = np.zeros(n)
    for k, a in enumerate(harmonics, start=1):
        x += a * np.sin(2 * np.pi * f * k * (1 + detune * k) * tt)
    return x * np.exp(-tt / decay)


def place(dst, src, at):
    i = int(at * SR)
    end = min(len(dst), i + len(src))
    dst[i:end] += src[: end - i]


def cash():
    x = np.zeros(int(SR * 0.9))
    click = rng.standard_normal(int(SR * 0.01)) * np.exp(-np.arange(int(SR * 0.01)) / (SR * 0.002))
    place(x, click * 0.6, 0)
    place(x, tone(2093, 0.8, 0.18, (1, 0.4, 0.2)), 0.02)
    place(x, tone(2637, 0.7, 0.16, (1, 0.35, 0.15)), 0.12)
    return normalize(fade(x, 1, 40), 0.8)


def levelup():
    x = np.zeros(int(SR * 1.3))
    for i, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        place(x, tone(f, 0.6, 0.25, (1, 0.5, 0.25, 0.12)), i * 0.11)
    place(x, tone(1567.98, 0.8, 0.35, (1, 0.3)) * 0.6, 0.45)
    return normalize(fade(x, 1, 60), 0.8)


def click():
    x = np.zeros(int(SR * 0.06))
    place(x, tone(1800, 0.05, 0.008, (1, 0.3)), 0)
    return normalize(fade(x, 0.5, 10), 0.6)


def beep(f, dur):
    x = tone(f, dur, 10, (1, 0.25, 0.1))
    return normalize(fade(x, 3, 30), 0.7)


def crowd(dur):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    x = np.zeros(n)
    for _ in range(40):
        f = rng.uniform(250, 900)
        voice = signal.sosfilt(bp(f * 0.8, f * 1.6), rng.standard_normal(n))
        env = np.clip(np.sin(np.pi * np.clip((tt - rng.uniform(0, 0.4)) / rng.uniform(1.5, dur), 0, 1)), 0, 1)
        x += voice * env * rng.uniform(0.3, 1)
    swell = np.minimum(1, tt / 0.3) * np.minimum(1, (dur - tt) / 1.2)
    return normalize(fade(x * swell, 10, 200), 0.75)


def workshop(dur):
    n = int(SR * dur)
    tt = np.arange(n) / SR
    hum = circ_filter(rng.standard_normal(n), lp(300)) * 0.25 + 0.05 * np.sin(2 * np.pi * 50 * tt)
    x = normalize(hum, 0.15)
    # Schlagschrauber-Salven und Metallklänge, kreisförmig verteilt
    for _ in range(5):
        start = rng.integers(0, n)
        ln = int(SR * rng.uniform(0.4, 0.9))
        t = np.arange(ln) / SR
        rat = signal.sosfilt(bp(400, 3000), rng.standard_normal(ln)) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 28 * t)))
        idx = (start + np.arange(ln)) % n
        x[idx] += rat * 0.18
    for _ in range(9):
        start = rng.integers(0, n)
        f = rng.uniform(900, 3000)
        clank = tone(f, 0.5, 0.06, (1, 0.6, 0.3), detune=0.003) + tone(f * 1.48, 0.5, 0.04) * 0.5
        idx = (start + np.arange(len(clank))) % n
        x[idx] += clank * 0.08
    return normalize(x, 0.5)


def door():
    x = np.zeros(int(SR * 0.45))
    place(x, tone(85, 0.4, 0.06, (1, 0.5)), 0)
    place(x, signal.sosfilt(lp(1500), rng.standard_normal(int(SR * 0.05))) * np.exp(-np.arange(int(SR * 0.05)) / (SR * 0.01)), 0)
    place(x, tone(2400, 0.05, 0.01) * 0.3, 0.02)
    return normalize(fade(x, 1, 40), 0.85)


def crash():
    n = int(SR * 0.9)
    tt = np.arange(n) / SR
    noise = signal.sosfilt(lp(2500), rng.standard_normal(n)) * np.exp(-tt / 0.08)
    thump = np.sin(2 * np.pi * 60 * tt) * np.exp(-tt / 0.12)
    ring = (tone(740, 0.9, 0.25, (1, 0.5), detune=0.01) + tone(1130, 0.9, 0.2)) * 0.25
    x = np.tanh((noise * 1.2 + thump + ring[:n]) * 1.5)
    return normalize(fade(x, 1, 60), 0.9)


def wrench_pickup():
    x = np.zeros(int(SR * 0.9))
    for i, f in enumerate((1318.5, 1760, 2093, 2637)):
        place(x, tone(f, 0.5, 0.15, (1, 0.3)), i * 0.06)
    return normalize(fade(x, 1, 50), 0.7)


def camera_flash():
    x = np.zeros(int(SR * 0.7))
    shutter = signal.sosfilt(bp(1500, 6000), rng.standard_normal(int(SR * 0.03))) * np.exp(-np.arange(int(SR * 0.03)) / (SR * 0.006))
    place(x, shutter, 0)
    place(x, shutter * 0.7, 0.05)
    t = np.arange(int(SR * 0.5)) / SR
    whine = np.sin(2 * np.pi * np.cumsum(3000 + 4000 * t) / SR) * np.exp(-t / 0.2) * 0.25
    place(x, whine, 0.08)
    return normalize(fade(x, 1, 40), 0.75)


def impact_wrench():
    n = int(SR * 1.1)
    tt = np.arange(n) / SR
    motor = signal.sosfilt(bp(300, 4000), rng.standard_normal(n))
    hammer = 0.55 + 0.45 * np.sign(np.sin(2 * np.pi * 26 * tt))
    whirr = np.sin(2 * np.pi * 420 * tt) * 0.3
    x = (motor * hammer + whirr) * np.minimum(1, tt / 0.03) * np.minimum(1, (1.1 - tt) / 0.1)
    return normalize(x, 0.75)


# Reihenfolge und Art (Schleife?) der Sounds in der Sammeldatei
SPRITE = [
    ("MotorTief", "motor_tief", True),
    ("MotorHoch", "motor_hoch", True),
    ("Turbo", "turbo", True),
    ("Reifen", "reifen", True),
    ("Hydraulik", "hydraulik", True),
    ("Umgebung", "umgebung", True),
    ("Werkstatt", "werkstatt", True),
    ("Abblasen", "abblasen", False),
    ("Fehlzuendung", "fehlzuendung", False),
    ("Hupe", "hupe", False),
    ("Kasse", "kasse", False),
    ("LevelUp", "levelup", False),
    ("Klick", "klick", False),
    ("PiepKurz", "piep_kurz", False),
    ("PiepLang", "piep_lang", False),
    ("Jubel", "jubel", False),
    ("Tuer", "tuer", False),
    ("Aufprall", "aufprall", False),
    ("Schluessel", "schluessel", False),
    ("Blitzer", "blitzer", False),
    ("Schlagschrauber", "schlagschrauber", False),
]


def build_sprite(sounds):
    """Hängt alle Sounds mit kurzer Pause aneinander und schreibt die Inhaltsliste."""
    gap = np.zeros(int(SR * 0.3))
    parts = []
    table = []
    t = 0.3
    parts.append(gap)
    for key, name, looped in SPRITE:
        x = np.clip(sounds[name], -1, 1)
        parts.append(x)
        table.append((key, round(t, 4), round(len(x) / SR, 4), looped))
        t += len(x) / SR
        parts.append(gap)
        t += len(gap) / SR
    save("alle_sounds", np.concatenate(parts))
    lines = ["\t%s = { %s, %s, %s }," % (k, a, b, "true" if l else "false") for k, a, b, l in table]
    lua = "\n".join(lines)
    (OUT / "alle_sounds_liste.lua").write_text("-- Start (s), Länge (s), Schleife\n" + lua + "\n", encoding="utf-8")
    return lua


def main():
    sounds = {
        "motor_tief": engine(40, 2.0, drive=1.6, bright=1400, rough=1.0),
        "motor_hoch": engine(140, 2.0, drive=2.6, bright=4200, rough=0.6),
        "turbo": turbo(2.0),
        "abblasen": blowoff(),
        "fehlzuendung": backfire(),
        "reifen": screech(2.0),
        "hydraulik": hydraulic(2.0),
        "umgebung": ambience(24.0),
        "hupe": horn(),
        "kasse": cash(),
        "levelup": levelup(),
        "klick": click(),
        "piep_kurz": beep(880, 0.25),
        "piep_lang": beep(1320, 0.7),
        "jubel": crowd(4.0),
        "werkstatt": workshop(12.0),
        "tuer": door(),
        "aufprall": crash(),
        "schluessel": wrench_pickup(),
        "blitzer": camera_flash(),
        "schlagschrauber": impact_wrench(),
    }
    for name, x in sounds.items():
        save(name, x)
    lua = build_sprite(sounds)
    print(lua)


if __name__ == "__main__":
    main()
