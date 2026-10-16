#!/usr/bin/env python3
"""Identité audio de Calista : un court thème afro-pop synthétisé (100 % original).

112 BPM, 8 mesures (environ 17 s), progression La mineur - Fa - Do - Sol.
Instruments : kick, clap, rim en tresillo (3-3-2), shaker, log drum, marimba, nappe douce,
et une signature de 3 notes au marimba sur la dernière mesure.

Usage : python3 theme_calista.py sortie.wav
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 112
STEP = 60 / BPM / 4          # durée d'une double-croche
BARS = 8
LEN = int(SR * STEP * 16 * BARS) + SR  # +1 s de queue
rng = np.random.default_rng(7)


def t(n):
    return np.arange(n) / SR


def env(n, attack=0.003, decay=0.2):
    x = t(n)
    a = np.minimum(1, x / attack)
    return a * np.exp(-x / decay)


def place(buf, sig, at, gain=1.0):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def note_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def kick():
    n = int(0.35 * SR)
    f = 45 + 75 * np.exp(-t(n) / 0.04)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(n, 0.001, 0.14)


def clap():
    n = int(0.18 * SR)
    noise = rng.standard_normal(n)
    noise = np.diff(np.concatenate([[0], noise]))          # passe-haut grossier
    e = env(n, 0.001, 0.05)
    for d in (0.010, 0.020):                                 # petits rebonds du clap
        k = int(d * SR)
        e[k:] += 0.6 * env(n - k, 0.001, 0.04)
    return noise * e * 0.5


def rim():
    n = int(0.06 * SR)
    return (np.sin(2 * np.pi * 1700 * t(n)) + 0.4 * rng.standard_normal(n)) * env(n, 0.0005, 0.012)


def shaker():
    n = int(0.07 * SR)
    noise = rng.standard_normal(n)
    noise = np.diff(np.concatenate([[0], np.diff(np.concatenate([[0], noise]))]))
    return noise * env(n, 0.004, 0.02) * 0.25


def log_drum(midi):
    n = int(0.45 * SR)
    f0 = note_hz(midi)
    f = f0 * (1 + 0.35 * np.exp(-t(n) / 0.03))               # petite glissade typique
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) + 0.25 * np.sin(2 * ph)
    return np.tanh(1.6 * s) * env(n, 0.002, 0.22)


def marimba(midi, decay=0.35):
    n = int(0.9 * SR)
    f = note_hz(midi)
    x = t(n)
    s = (np.sin(2 * np.pi * f * x) + 0.25 * np.sin(2 * np.pi * 4 * f * x) * np.exp(-x / 0.05)
         + 0.1 * np.sin(2 * np.pi * 10 * f * x) * np.exp(-x / 0.01))
    return s * env(n, 0.002, decay)


def pad(midis, dur):
    n = int(dur * SR)
    x = t(n)
    s = np.zeros(n)
    for m in midis:
        f = note_hz(m)
        for det in (-0.12, 0.12):
            s += np.sin(2 * np.pi * f * (1 + det / 100) * x)
    a = np.minimum(1, x / 0.25) * np.minimum(1, (dur - x) / 0.3)
    return s * a / (2 * len(midis))


# Accords (La mineur - Fa - Do - Sol), en notes MIDI
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
ROOTS = [45, 41, 48, 43]                      # log drum, une octave en dessous
# Motif de marimba (pentatonique), 16 pas par mesure, None = silence
MOTIFS = [
    [76, None, None, 72, None, None, 74, None, 76, None, 79, None, None, 76, None, None],
    [72, None, None, 69, None, None, 72, None, 74, None, None, 72, None, None, 69, None],
]
SIGNATURE = [(0, 76), (3, 79), (6, 84)]      # « Ca-lis-ta » : mi - sol - do aigu


def render():
    mix = np.zeros(LEN)
    drums = np.zeros(LEN)
    k, c, r, sh = kick(), clap(), rim(), shaker()
    for bar in range(BARS):
        b0 = bar * 16 * STEP
        chord = bar % 4
        last = bar == BARS - 1
        for step in range(16):
            at = b0 + step * STEP + (0.012 if step % 2 else 0)   # léger swing
            if step in (0, 7, 8, 14) and not (last and step > 8):
                place(drums, k, at, 0.7)
            if step in (4, 12):
                place(drums, c, at, 0.55)
            if step in (0, 3, 6, 10, 13):                        # tresillo 3-3-2 + relance
                place(drums, r, at, 0.25)
            place(drums, sh, at, 0.6 if step % 2 else 0.35)
            if step in (0, 3, 6, 10) and not last:
                place(mix, log_drum(ROOTS[chord]), at, 0.4)
        place(mix, pad(CHORDS[chord], 16 * STEP), b0, 0.3)
        if last:
            for step, m in SIGNATURE:
                place(mix, marimba(m, 0.6), b0 + step * STEP, 1.0)
        elif bar >= 2:
            for step, m in enumerate(MOTIFS[bar % 2]):
                if m is not None:
                    place(mix, marimba(m), b0 + step * STEP + (0.012 if step % 2 else 0), 0.7)
    out = mix + drums
    out = np.tanh(1.3 * out)                                    # compression douce
    out /= np.max(np.abs(out)) / 0.6                            # environ -4.5 dB (marge pour l AAC)
    fade = int(0.8 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def main(path):
    audio = render()
    stereo = np.stack([audio, np.roll(audio, 12)], axis=1)     # léger élargissement
    data = (stereo * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "theme_calista.wav")
