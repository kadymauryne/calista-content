#!/usr/bin/env python3
"""Identité audio de Calista, version 2 : thème afro festif, très percussif (100 % original).

Inspiré du rythme enregistré par Kady (environ 129 BPM, frappes à contretemps sur les
pas 2, 4, 10, 13 et 14 de la mesure). 128 BPM, 8 mesures (environ 16 s).
Percussions : kick, caisse claire avec roulements, djembé (basse, tone, slap), talking drum,
congas, cloche (agogo), shaker, crash. Mélodie : guitare pincée façon soukous
(synthèse Karplus-Strong) + basse. Fin : signature « Ca-lis-ta ».

Usage : python3 theme_calista.py sortie.wav
"""
import sys
import wave

import numpy as np
from scipy.signal import lfilter

SR = 44100
BPM = 128
STEP = 60 / BPM / 4
BARS = 8
LEN = int(SR * STEP * 16 * BARS) + int(1.2 * SR)
rng = np.random.default_rng(11)


def tt(n):
    return np.arange(n) / SR


def env(n, attack=0.002, decay=0.2):
    x = tt(n)
    return np.minimum(1, x / attack) * np.exp(-x / decay)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def place(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def noise(n):
    return rng.standard_normal(n)


def hp(x):
    return np.diff(np.concatenate([[0], x]))


# ---------- Percussions ----------
def kick():
    n = int(0.32 * SR)
    f = 48 + 110 * np.exp(-tt(n) / 0.025)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.13)
    click = hp(noise(n)) * env(n, 0.0003, 0.004) * 0.6
    return np.tanh(1.8 * (body + click))


def snare(gain_tone=1.0):
    n = int(0.22 * SR)
    tone = np.sin(2 * np.pi * 196 * tt(n))                    # Sol * env(n, 0.001, 0.05) * gain_tone
    sn = hp(noise(n)) * env(n, 0.001, 0.07)
    return 0.6 * tone + 0.7 * sn


def djembe(kind):
    if kind == "basse":
        n = int(0.35 * SR)
        f = 65.4 * (1 + 0.4 * np.exp(-tt(n) / 0.02))             # Do grave
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.12)
                + 0.1 * noise(n) * env(n, 0.001, 0.01))
    if kind == "tone":
        n = int(0.25 * SR)
        f = 261.6 * (1 + 0.15 * np.exp(-tt(n) / 0.015))          # Do
        ph = 2 * np.pi * np.cumsum(f) / SR
        return ((np.sin(ph) + 0.35 * np.sin(1.5 * ph)) * env(n, 0.001, 0.07)
                + 0.15 * noise(n) * env(n, 0.001, 0.008))
    n = int(0.18 * SR)                                     # slap : claquant et aigu
    ring = np.sin(2 * np.pi * 523.3 * tt(n))                  # Do aigu * env(n, 0.0005, 0.03)
    return 0.6 * ring + 0.9 * hp(noise(n)) * env(n, 0.0005, 0.02)


def talking_drum(up=True):
    n = int(0.4 * SR)
    x = tt(n)
    curve = 130.8 + (65.2 if up else -32.8) * (1 - np.exp(-x / 0.06))   # Do -> Sol / Do -> Sol grave
    ph = 2 * np.pi * np.cumsum(curve) / SR
    return (np.sin(ph) + 0.3 * np.sin(2 * ph)) * env(n, 0.002, 0.16)


def conga(high=True):
    n = int(0.22 * SR)
    f0 = 392 if high else 261.6                              # Sol / Do
    f = f0 * (1 + 0.1 * np.exp(-tt(n) / 0.01))
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.08)
            + 0.08 * noise(n) * env(n, 0.001, 0.005))


def cowbell():
    n = int(0.25 * SR)
    x = tt(n)
    sq = np.sign(np.sin(2 * np.pi * 523.3 * x)) + np.sign(np.sin(2 * np.pi * 784 * x))   # Do + Sol
    return lfilter([1, -0.6], [1], sq) * env(n, 0.0005, 0.06) * 0.35


def shaker():
    n = int(0.06 * SR)
    return hp(hp(noise(n))) * env(n, 0.006, 0.015) * 0.2


def crash():
    n = int(1.6 * SR)
    return hp(hp(noise(n))) * env(n, 0.001, 0.6) * 0.25


# ---------- Instruments mélodiques ----------
def guitar(midi, dur=0.5, bright=0.5):
    """Corde pincée (Karplus-Strong) : son de guitare soukous."""
    n = int(dur * SR)
    N = max(2, int(round(SR / hz(midi) - 0.5)))
    burst = np.zeros(n)
    k = min(N, n)
    exc = lfilter([1 - bright], [1, -bright], rng.uniform(-1, 1, k))
    burst[:k] = exc - exc.mean()
    g = 0.996
    a = np.zeros(N + 2)
    a[0] = 1
    a[N] = -g * 0.5
    a[N + 1] = -g * 0.5
    y = lfilter([1], a, burst)
    y = lfilter([1, -1], [1, -0.995], y)              # supprime la composante continue
    return y * env(n, 0.001, dur * 0.6) * 3.5


def bass(midi, dur):
    n = int(dur * SR)
    x = tt(n)
    f = hz(midi)
    s = np.sin(2 * np.pi * f * x) + 0.3 * np.sin(4 * np.pi * f * x)
    return np.tanh(1.5 * s) * np.minimum(1, x / 0.005) * np.exp(-x / (dur * 0.7))


# Do - Fa - Sol - Fa (I - IV - V - IV) : couleur joyeuse, typique highlife/soukous
CHORDS = [[60, 64, 67], [65, 69, 72], [67, 71, 74], [65, 69, 72]]
BASS = [36, 41, 43, 41]
# Riff de guitare (16 pas) : arpèges rapides, une octave au-dessus des accords
RIFF = [0, None, 2, 1, None, 2, 0, None, 1, 2, None, 0, 2, None, 1, 2]
SIGNATURE = [(0, 76), (3, 79), (6, 84)]          # « Ca-lis-ta » : mi - sol - do aigu


def render(stems=False):
    drums = np.zeros(LEN)
    music = np.zeros(LEN)
    K, SN, SNg = kick(), snare(), snare(0.3)
    DB, DT, DS = djembe("basse"), djembe("tone"), djembe("slap")
    TU, TD = talking_drum(True), talking_drum(False)
    CH, CL = conga(True), conga(False)
    CB, SH, CR = cowbell(), shaker(), crash()
    for bar in range(BARS):
        b0 = bar * 16 * STEP
        c = bar % 4
        last = bar == BARS - 1
        fill = bar % 2 == 1                      # roulement toutes les 2 mesures
        for s in range(16):
            at = b0 + s * STEP + (0.008 if s % 2 else 0)
            # Kick : 4 temps + relance (le « boum » de Kady en fin de mesure)
            if s in (0, 4, 8, 12, 14) and not (last and s > 6):
                place(drums, K, at, 0.75)
            # Caisse claire sur 2 et 4, roulement en fin de mesure impaire
            if s in (4, 12):
                place(drums, SN, at, 0.6)
            if fill and s >= 12 and not last:
                for r in range(2):
                    place(drums, SNg, at + r * STEP / 2, 0.25 + 0.1 * (s - 12))
            # Motif de Kady au djembé : slaps à contretemps, basse en fin de mesure
            if s in (2, 10, 13):
                place(drums, DS, at, 0.55)
            if s in (6, 9):
                place(drums, DT, at, 0.35)
            if s == 15:
                place(drums, DB, at, 0.6)
            # Talking drum : questions-réponses
            if s == 7:
                place(drums, TU, at, 0.35)
            if s == 15 and bar % 2 == 0:
                place(drums, TD, at, 0.3)
            # Congas sur les contretemps
            if s in (3, 11):
                place(drums, CH, at, 0.35)
            if s in (5, 14):
                place(drums, CL, at, 0.3)
            # Cloche (agogo)
            if s in (0, 3, 6, 8, 10, 12, 14):
                place(drums, CB, at, 0.5 if s in (0, 8) else 0.3)
            place(drums, SH, at, 0.55 if s % 2 else 0.3)
            # Basse syncopée
            if s in (0, 3, 6, 10) and not last:
                place(music, bass(BASS[c] if s != 6 else BASS[c] + 12, STEP * 3), at, 0.35)
            # Guitare soukous (à partir de la mesure 2)
            if bar >= 1 and not last and RIFF[s] is not None:
                note = CHORDS[c][RIFF[s]] + 12
                place(music, guitar(note, 0.35), at, 0.85)
                if s % 4 == 0:
                    place(music, guitar(CHORDS[c][(RIFF[s] + 1) % 3] + 12, 0.35), at + 0.004, 0.4)
        if bar in (0, 4):
            place(drums, CR, b0, 0.8)
        if last:
            place(drums, CR, b0, 1.0)
            place(drums, K, b0, 1.0)
            for s, m in SIGNATURE:
                place(music, guitar(m, 0.9, 0.3), b0 + s * STEP, 0.6)
                place(music, guitar(m - 12, 0.9, 0.3), b0 + s * STEP + 0.006, 0.3)
            for s in (0, 3, 6):
                place(drums, DS, b0 + s * STEP, 0.6)
    if stems:
        return drums, music
    out = 1.0 * drums + 0.85 * music
    out = np.tanh(1.4 * out)
    out /= np.max(np.abs(out)) / 0.5
    fade = int(0.6 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def main(path):
    audio = render()
    stereo = np.stack([audio, np.roll(audio, 15)], axis=1)
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "theme_calista.wav")
