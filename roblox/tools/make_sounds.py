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


def main():
    save("motor_tief", engine(40, 2.0, drive=1.6, bright=1400, rough=1.0))
    save("motor_hoch", engine(140, 2.0, drive=2.6, bright=4200, rough=0.6))
    save("turbo", turbo(2.0))
    save("abblasen", blowoff())
    save("fehlzuendung", backfire())
    save("reifen", screech(2.0))
    save("hydraulik", hydraulic(2.0))
    save("umgebung", ambience(24.0))
    save("hupe", horn())


if __name__ == "__main__":
    main()
