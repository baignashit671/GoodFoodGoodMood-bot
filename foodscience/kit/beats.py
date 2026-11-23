"""Original, royalty-free music beds in the styles that trend on food / facts Shorts. Made entirely in code (numpy).
  python tools/beats.py <project> <preset> [--bpm N] [--seed N]
Writes <project>/data/beat.wav, as long as data/lines.json's duration. Use it in script.json: "music": "data/beat.wav"
(optionally "music_db": -21 for a louder bed; default -24).

Presets
  desi-lofi      tabla-style groove + tanpura drone + plucked sitar-like melody + vinyl crackle (cosy kitchen, chai, spices)
  chill-lofi     soft kick/snare, swung hats, warm electric-piano 7th chords, crackle (calm "did you know" facts)
  phonk          drift-phonk style: 808 slides, cowbell riff, fast hats (shock facts, spicy, "don't do this")
  bollywood-pop  dhol/bhangra-style rhythm + bright synth stabs (festive, sweets, party food)
  suspense-pluck staccato pizzicato + ticking clock (myth-busting, "what happens if", countdowns)
Every bed opens with a hit on beat one (no fade-in) so the hook lands on sound, and ends with a short fade.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100
ap = argparse.ArgumentParser(); ap.add_argument('project'); ap.add_argument('preset'); ap.add_argument('--bpm', type=float); ap.add_argument('--seed', type=int, default=7)
a = ap.parse_args()
P = Path(a.project); DUR = json.loads((P / 'data/lines.json').read_text())['duration'] + 0.5
N = int(DUR * SR); rng = np.random.default_rng(a.seed)


def tt(d): return np.arange(int(d * SR)) / SR
def env(n, att=0.003, dec=6.0):
    t = np.arange(n) / SR; return np.minimum(1, t / max(att, 1e-4)) * np.exp(-t * dec)
def lp(x, f, o=2): b, aa = signal.butter(o, min(f, SR / 2 - 100) / (SR / 2), 'low'); return signal.lfilter(b, aa, x)
def hp(x, f, o=2): b, aa = signal.butter(o, f / (SR / 2), 'high'); return signal.lfilter(b, aa, x)
def bp(x, f0, f1, o=2): b, aa = signal.butter(o, [f0 / (SR / 2), f1 / (SR / 2)], 'band'); return signal.lfilter(b, aa, x)
def add(x, s, at):
    i = int(at * SR); n = min(len(s), len(x) - i)
    if n > 0 and i >= 0: x[i:i + n] += s[:n]
def nf(m): return 440 * 2 ** ((m - 69) / 12)

# ── instruments ──
def kick(d=0.35, f0=150, f1=45, drive=1.0):
    t = tt(d); ph = 2 * np.pi * np.cumsum(f1 + (f0 - f1) * np.exp(-t * 30)) / SR; return np.tanh(np.sin(ph) * env(len(t), 0.001, 9) * drive * 2) * 0.9
def snare(d=0.25, tone=190):
    t = tt(d); n = bp(rng.standard_normal(len(t)), 1500, 8000) * env(len(t), 0.001, 18); b = np.sin(2 * np.pi * tone * t) * env(len(t), 0.001, 25); return n * 0.7 + b * 0.5
def hat(d=0.06, open_=False):
    t = tt(0.22 if open_ else d); return hp(rng.standard_normal(len(t)), 7000) * env(len(t), 0.0005, 12 if open_ else 60) * 0.35
def clap():
    t = tt(0.2); n = bp(rng.standard_normal(len(t)), 900, 5000); e = sum(env(len(t), 0.0005, 70) * (np.arange(len(t)) >= int(k * 0.011 * SR)) for k in range(3)) + env(len(t), 0.001, 14) * 0.6; return n * e * 0.5
def tabla(kind):
    """dha (bass bayan + ringing dayan), na (ringing rim), tin (soft), ge (low bayan with pitch bend), ka (dry slap)"""
    t = tt(0.5)
    ring = lambda f, dec, g: (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.01 * t) + 0.25 * np.sin(2 * np.pi * f * 2.98 * t)) * env(len(t), 0.001, dec) * g
    bay = lambda g: np.sin(2 * np.pi * np.cumsum(70 + 60 * np.exp(-t * 6)) / SR) * env(len(t), 0.002, 6) * g
    slap = bp(rng.standard_normal(len(t)), 800, 4000) * env(len(t), 0.0005, 80)
    if kind == 'dha': return ring(330, 9, 0.5) + bay(0.9) + slap * 0.3
    if kind == 'na': return ring(330, 11, 0.7) + slap * 0.4
    if kind == 'tin': return ring(330, 16, 0.35) + slap * 0.15
    if kind == 'ge': return bay(1.0)
    return slap * 0.6 + ring(500, 40, 0.1)  # ka
def dhol(kind):
    t = tt(0.45)
    if kind == 'dagga': return np.tanh(np.sin(2 * np.pi * np.cumsum(60 + 90 * np.exp(-t * 18)) / SR) * env(len(t), 0.001, 7) * 2.5) * 0.9
    return (bp(rng.standard_normal(len(t)), 1200, 6000) * env(len(t), 0.0005, 45) + np.sin(2 * np.pi * 420 * t) * env(len(t), 0.001, 30) * 0.4) * 0.8  # tilli
def pluck(f, d=0.9, bright=1.0):
    """Karplus-Strong plucked string (sitar-ish with a buzzy bridge when bright > 1)"""
    n = int(d * SR); per = max(2, int(SR / f)); buf = rng.uniform(-1, 1, per); out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % per]; buf[i % per] = 0.5 * (buf[i % per] + buf[(i + 1) % per]) * 0.996
    if bright > 1: out = np.tanh(out * bright) + 0.15 * np.sign(out) * np.abs(out) ** 0.5
    return out * env(n, 0.001, 2.5)
def ep(freqs, d):
    """warm electric piano chord"""
    t = tt(d); x = sum((np.sin(2 * np.pi * f * t + 0.6 * np.sin(2 * np.pi * f * 1.0 * t) * np.exp(-t * 3)) * np.exp(-t * 1.6)) for f in freqs)
    return x * np.minimum(1, t / 0.01) * 0.18
def bass808(f, d, glide_to=None):
    t = tt(d); fr = np.full(len(t), f) if glide_to is None else f + (glide_to - f) * np.clip((t - d * 0.5) / (d * 0.3), 0, 1)
    return np.tanh(np.sin(2 * np.pi * np.cumsum(fr) / SR) * 2.2) * np.minimum(1, t / 0.005) * np.exp(-t * 1.2) * 0.8
def cowbell(f, d=0.25):
    t = tt(d); x = np.sign(np.sin(2 * np.pi * f * t)) + np.sign(np.sin(2 * np.pi * f * 1.48 * t)); return bp(x, 500, 4000) * env(len(t), 0.001, 12) * 0.35
def pizz(f):
    t = tt(0.35); return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sin(6 * np.pi * f * t)) * env(len(t), 0.002, 14) * 0.5
def drone(fs, gain=0.12):
    t = np.arange(N) / SR; x = np.zeros(N)
    for f in fs:
        for h, g in [(1, 1), (2, 0.5), (3, 0.33), (4, 0.25), (5, 0.18)]: x += np.sin(2 * np.pi * f * h * t + 0.3 * np.sin(2 * np.pi * 0.13 * h * t)) * g
    return lp(x, 2500) * gain / len(fs)
def crackle(g=0.05):
    x = np.zeros(N); idx = rng.integers(0, N, int(DUR * 35)); x[idx] = rng.uniform(-1, 1, len(idx)); return lp(hp(x, 1500), 7000) * g + lp(rng.standard_normal(N), 400) * 0.004

# ── presets ──
def desi_lofi(bpm=86):
    b = 60 / bpm; x = np.zeros(N); x += drone([nf(50), nf(57)], 0.10)                  # tanpura Sa + Pa (D, A)
    bol = ['dha', 'ge', 'na', 'tin', 'na', 'ka', 'dha', 'na', 'dha', 'ge', 'na', 'tin', 'na', 'ka', 'dha', 'ge']
    scale = [62, 63, 66, 67, 69, 70, 73, 74]                                              # D bhairav-ish flavour
    mel = [0, 2, 3, 4, 3, 2, 1, 0, 4, 5, 7, 5, 4, 3, 2, 0]
    for k in range(int(DUR / (b / 2)) + 1):
        at = k * b / 2 + (0.035 if k % 2 else 0)                                          # swing
        add(x, tabla(bol[k % 16]) * 0.55, at)
        if k % 4 == 0 and (k // 16) % 2 == 0: add(x, pluck(nf(scale[mel[(k // 4) % 16]]), 1.0, 1.6) * 0.35, at)
        if k % 8 == 0: add(x, kick(0.3, 110, 45) * 0.45, at)
    return lp(x + crackle(), 6500)
def chill_lofi(bpm=80):
    b = 60 / bpm; x = np.zeros(N); chords = [[57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 65], [52, 55, 59, 62]]
    for bar in range(int(DUR / (4 * b)) + 1):
        st = bar * 4 * b; add(x, ep([nf(m) for m in chords[bar % 4]], 4 * b), st); add(x, np.sin(2 * np.pi * nf(chords[bar % 4][0] - 12) * tt(4 * b)) * np.exp(-tt(4 * b) * 0.8) * 0.25, st)
        for q in range(4):
            add(x, kick(0.3, 120, 48) * 0.6, st + q * b) if q in (0, 2) else add(x, snare() * 0.35, st + q * b)
            for e in range(2): add(x, hat() * (0.5 if e else 0.8), st + q * b + e * b / 2 + (0.04 if e else 0))
    return lp(x + crackle(0.06), 5500)
def phonk(bpm=128):
    b = 60 / bpm; x = np.zeros(N); riff = [72, 72, 75, 72, 70, 72, 67, 70]; bassn = [36, 36, 39, 34]
    for bar in range(int(DUR / (4 * b)) + 1):
        st = bar * 4 * b; root = bassn[bar % 4]
        add(x, bass808(nf(root), 4 * b * 0.95, nf(root - 5) if bar % 4 == 3 else None) * 0.7, st)
        for q in range(4):
            if q in (0, 2) or (q == 3 and bar % 2): add(x, kick(0.3, 160, 45, 1.5) * 0.8, st + q * b + (b / 2 if q == 3 else 0))
            if q in (1, 3): add(x, clap() * 0.7, st + q * b)
        for s in range(16):
            add(x, hat(0.04) * (0.6 if s % 2 else 0.9), st + s * b / 4)
            if s % 2 == 0: add(x, cowbell(nf(riff[(s // 2) % 8])) * 0.8, st + s * b / 4)
    return np.tanh(x * 1.3)
def bollywood_pop(bpm=104):
    b = 60 / bpm; x = np.zeros(N); pat = ['dagga', 'tilli', 'tilli', 'dagga', 'tilli', 'dagga', 'tilli', 'tilli']
    chords = [[62, 66, 69], [67, 71, 74], [69, 73, 76], [64, 67, 71]]
    for bar in range(int(DUR / (4 * b)) + 1):
        st = bar * 4 * b
        for e in range(8): add(x, dhol(pat[e]) * 0.6, st + e * b / 2)
        for q in range(4): add(x, kick(0.25, 140, 50) * 0.5, st + q * b)
        for s in (0.5, 1.5, 2.5, 3.5):
            t = tt(0.18); stab = sum(np.sign(np.sin(2 * np.pi * nf(m) * t)) for m in chords[bar % 4]) * env(len(t), 0.002, 14) * 0.08; add(x, lp(stab, 3500), st + s * b)
    return x
def suspense_pluck(bpm=118):
    b = 60 / bpm; x = np.zeros(N); seq = [57, 60, 57, 64, 57, 60, 63, 62]
    x += drone([nf(33)], 0.08)
    for k in range(int(DUR / (b / 2)) + 1):
        at = k * b / 2; add(x, pizz(nf(seq[k % 8])) * 0.6, at)
        add(x, (np.sin(2 * np.pi * (1800 if k % 2 else 1400) * tt(0.03)) * env(int(0.03 * SR), 0.0005, 120)) * 0.15, at)   # tick-tock
        if k % 4 == 0: add(x, kick(0.3, 100, 40) * 0.5, at)
    return x

PRESETS = {'desi-lofi': desi_lofi, 'chill-lofi': chill_lofi, 'phonk': phonk, 'bollywood-pop': bollywood_pop, 'suspense-pluck': suspense_pluck}
if a.preset not in PRESETS: sys.exit(f'unknown preset {a.preset}; choose one of {list(PRESETS)}')
fn = PRESETS[a.preset]; x = fn(a.bpm) if a.bpm else fn()
x = x[:N]; x = x / (np.abs(x).max() + 1e-9) * 0.9
fo = int(1.0 * SR); x[-fo:] *= np.linspace(1, 0, fo)
(P / 'data').mkdir(exist_ok=True)
wavfile.write(P / 'data/beat.wav', SR, (np.stack([x, x], 1) * 32767).astype(np.int16))
print(f'data/beat.wav: {a.preset}, {DUR:.1f} s. In script.json set "music": "data/beat.wav"')
