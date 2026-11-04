#!/usr/bin/env python3
"""Hörprobe: mischt die Sounds so, wie das Spiel es beim Fahren tut
(Drehzahl, Gangwechsel, Turbo, Abblasen, Fehlzündung). Ergebnis: sounds/hoerprobe.mp3"""
import subprocess, tempfile
from pathlib import Path
import numpy as np
from scipy.io import wavfile

SR = 44100
D = Path(__file__).resolve().parent.parent / "sounds"


def load(name):
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp) / "x.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(D / f"{name}.ogg"), str(w)], check=True)
        sr, x = wavfile.read(w)
    return x.astype(float) / 32768


def loop_player(x, speed):
    """Spielt Schleife x mit wechselnder Abspielgeschwindigkeit (pro Sample)."""
    pos = np.cumsum(speed) % len(x)
    i = pos.astype(int)
    f = pos - i
    return x[i] * (1 - f) + x[(i + 1) % len(x)] * f


low, high, turbo = load("motor_tief"), load("motor_hoch"), load("turbo")
blow, bang = load("abblasen"), load("fehlzuendung")

dur = 14.0
n = int(SR * dur)
t = np.arange(n) / SR
rpm = np.full(n, 900.0)
load_ = np.full(n, 0.2)
events = []
# 0-2 s Leerlauf, 2-3.5 s Gasstoß im Stand, 4-12 s Beschleunigung mit 4 Gängen, dann Gas weg
rev = (t > 2) & (t < 3.5)
rpm[rev] = 900 + 4800 * np.sin(np.pi * (t[rev] - 2) / 1.5) ** 0.7
load_[rev] = 1
events.append(("blow", 3.3))
gear_t = [4.0, 5.6, 7.6, 10.0, 12.5]
for g in range(4):
    a, b = gear_t[g], gear_t[g + 1]
    m = (t >= a) & (t < b)
    start = 2200 if g == 0 else 4300
    rpm[m] = start + (6900 - start) * ((t[m] - a) / (b - a)) ** 0.85
    load_[m] = 1
    if g > 0:
        events.append(("blow", a - 0.05))
off = t >= 12.5
rpm[off] = 900 + 5800 * np.exp(-(t[off] - 12.5) / 0.6)
load_[off] = 0.15
events.append(("blow", 12.5))
events.append(("bang", 12.6))

# Drehzahl glätten (wie im Spiel)
k = int(SR * 0.04)
rpm = np.convolve(rpm, np.ones(k) / k, mode="same")
mix = np.clip((rpm - 2500) / 2500, 0, 1)
base = 0.35 + 0.65 * load_
out = loop_player(low, rpm / 1200) * (base * (1 - mix) * 0.9 + 0.08)
out += loop_player(high, rpm / 4200) * base * mix * 0.9
out += loop_player(turbo, 0.6 + rpm / 7000) * load_ * np.clip((rpm - 2000) / 3000, 0, 1) * 0.3
for kind, at in events:
    s = blow if kind == "blow" else bang
    i = int(at * SR)
    out[i:i + len(s)] += s[: len(out) - i] * (0.5 if kind == "blow" else 0.8)
out = out / np.max(np.abs(out)) * 0.9
with tempfile.TemporaryDirectory() as tmp:
    w = Path(tmp) / "x.wav"
    wavfile.write(w, SR, (out * 32767).astype(np.int16))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(w), "-b:a", "160k", str(D / "hoerprobe.mp3")], check=True)
print("hoerprobe.mp3 geschrieben")
