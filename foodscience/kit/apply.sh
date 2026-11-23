#!/usr/bin/env bash
# Turn a fresh faceless-shorts project (made with new_video.sh) into a GoodFoodGoodMood Hindi project:
#   bash foodscience/kit/apply.sh <project>
# - Devanagari captions/pills: Hind (SIL OFL) is registered as part of the 'Inter' family for Devanagari code points,
#   so every caption, pill and label keeps working with no code change.
# - Word matching (Wd, captions) keeps Devanagari letters instead of stripping them.
# - tools/voice.py: the skill's Kokoro narrator, with Hindi voices (hm_omega, hm_psi, hf_alpha, hf_beta) spoken
#   with lang 'hi' and the danda (।) closing a sentence.
# - tools/align.py: word timing that weighs Devanagari words by their letters.
# - tools/beats.py: original trending-style music beds (royalty-free, made in code).
# - src/core/food.js: food props in the Deep Dive clay look.
# - src/core/cook.js: cook() = Didi, the channel's Indian woman host in a saree; desiKitchen(scene) = gas stove, masala dabba, tiles, lota.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$KIT/../.." && pwd)"
P="$(cd "${1:?usage: apply.sh <project>}" && pwd)"
SKILL="${SKILL:-$(ls -d /root/.claude/skills/synced/*/faceless-shorts 2>/dev/null | head -1)}"
[ -f "$SKILL/scripts/voice.py" ] || { echo "faceless-shorts skill not found (set SKILL=...)"; exit 1; }

cp "$KIT/fonts/Hind-Bold.ttf" "$KIT/fonts/Hind-SemiBold.ttf" "$P/fonts/"

python3 - "$P" <<'PY'
import re, sys, pathlib
P = pathlib.Path(sys.argv[1])
def patch(f, old, new, count=1):
    p = P / f; s = p.read_text()
    if new in s: return
    assert old in s, f'{f}: pattern not found: {old[:60]}'
    p.write_text(s.replace(old, new, count))
DEV = "unicode-range: U+0900-097F, U+1CD0-1CFF, U+200C-200D, U+20B9, U+A8E0-A8FF"
patch('index.html', "src: url('fonts/Inter-ExtraBold.otf'); }",
      "src: url('fonts/Inter-ExtraBold.otf'); }\n"
      f"@font-face {{ font-family: 'Inter'; font-weight: 900; src: url('fonts/Hind-Bold.ttf'); {DEV}; }}\n"
      f"@font-face {{ font-family: 'Inter'; font-weight: 800; src: url('fonts/Hind-SemiBold.ttf'); {DEV}; }}")
patch('src/main.js', "await document.fonts.load('800 100px Inter');",
      "await document.fonts.load('800 100px Inter'); await document.fonts.load('900 100px Inter', 'कखग'); await document.fonts.load('800 100px Inter', 'कखग');")
for f in ['src/core/timing.js', 'src/core/captions.js']:
    p = P / f; s = p.read_text(); s2 = s.replace("/[^a-z0-9']+/g", "/[^\\p{L}\\p{M}\\p{N}']+/gu"); p.write_text(s2)
    assert "\\p{L}" in s2, f
patch('src/main.js', "const fade = Math.min(clamp(t / 0.25), clamp((T.dur - t) / 0.4));",
      "const fade = clamp((T.dur - t) / 0.4);   // no fade-in: the hook frame is on screen from frame one")
patch('src/main.js', "  drawCaption(t);\n}", "  drawCaption(Math.max(t, 0.16));   // first caption visible from frame one\n}")
# Roman (Hinglish) captions for Devanagari narration: with "capsByIndex": true in script.json, each line's "caps" are
# written in Roman letters with exactly one caption word per spoken (Devanagari) word, and chunks are timed by word index.
patch('src/core/captions.js', "let idx = j === 0 ? 0 :", "let idx = script.capsByIndex ? Math.min(ws.length - 1, acc) : j === 0 ? 0 :")
patch('tools/mix.py', "db(-24 if voice is not None else -20)", "db(float(script.get('music_db', -24)) if voice is not None else -20)")
print('patched index.html, main.js, timing.js, captions.js (+capsByIndex), mix.py')
PY

sed -e "s/lang = 'en-gb' if voice.startswith('b') else 'en-us'/lang = 'hi' if voice.startswith('h') else ('en-gb' if voice.startswith('b') else 'en-us')/" \
    -e "s/\[\.?!\]\[\"\\\\')\]\*\\$/[.?!।][\"\\\\')]*\$/" \
    "$SKILL/scripts/voice.py" > "$P/tools/voice.py"
grep -q "lang = 'hi'" "$P/tools/voice.py" || { echo "voice.py patch failed"; exit 1; }
grep -q "।" "$P/tools/voice.py" || { echo "voice.py danda patch failed"; exit 1; }
sed -e 's/\[\^A-Za-z0-9\]/[\\W_]/g' "$REPO/scripts/align.py" > "$P/tools/align.py"
cp "$KIT/beats.py" "$P/tools/beats.py"
cp "$KIT/food.js" "$P/src/core/food.js"
cp "$KIT/cook.js" "$P/src/core/cook.js"
echo "cooking kit applied to $P"
echo "next: \$SKILL/scripts/py tools/voice.py . && \$SKILL/scripts/py tools/align.py . && \$SKILL/scripts/py tools/beats.py . <preset>"
