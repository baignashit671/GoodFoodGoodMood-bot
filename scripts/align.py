"""Word timing without Whisper: spread each line's words across its exact voice span (data/lines.json from voice.py),
weighted by letters, and snap comma / full-stop pauses to the real silences found in data/narration.wav.
  python tools/align.py .
"""
import json, re, sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile

P = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
L = json.loads((P / 'data/lines.json').read_text())
sr, x = wavfile.read(P / 'data/narration.wav'); x = x.astype(np.float64) / 32768
hop = int(0.01 * sr); n = len(x) // hop
rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)); quiet = rms < 0.02 * np.abs(x).max()
pauses, st = [], None
for f, q in enumerate(quiet):
    if q and st is None: st = f
    if (not q or f == n - 1) and st is not None:
        if (f - st) >= 7: pauses.append((st * 0.01, f * 0.01))
        st = None

words = []
for ln in L['lines']:
    toks = ln['text'].split(); a, b = ln['start'], ln['end']
    # split the line into phrases at commas; place each phrase boundary on the nearest real pause
    phrases, cur = [], []
    for w in toks:
        cur.append(w)
        if re.search(r'[,;:]$', w): phrases.append(cur); cur = []
    if cur: phrases.append(cur)
    wt = lambda ws: sum(len(re.sub(r'[^A-Za-z0-9]', '', w)) + 2.5 for w in ws)
    total = sum(wt(p) for p in phrases); spans, t = [], a
    inner = [p for p in pauses if a + 0.1 < p[0] and p[1] < b - 0.1]
    for k, ph in enumerate(phrases):
        if k == len(phrases) - 1: spans.append((t, b)); break
        guess = t + (b - a) * wt(ph) / total
        near = [p for p in inner if abs((p[0] + p[1]) / 2 - guess) < 0.5 and p[0] > t]
        if near: p = min(near, key=lambda p: abs((p[0] + p[1]) / 2 - guess)); spans.append((t, p[0])); t = p[1]
        else: spans.append((t, guess)); t = guess + 0.12
    for ph, (s, e) in zip(phrases, spans):
        tw = wt(ph); c = s
        for w in ph:
            d = (e - s) * (len(re.sub(r'[^A-Za-z0-9]', '', w)) + 2.5) / tw
            words.append({'w': w, 'line': ln['i'], 's': round(c, 3), 'e': round(c + d * 0.92, 3)}); c += d
(P / 'data/words.json').write_text(json.dumps(words, indent=1))
print(f'{len(words)} words aligned, {len(pauses)} pauses found')
