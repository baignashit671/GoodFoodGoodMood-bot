#!/usr/bin/env python3
"""
GoodFoodGoodMood — daily Indian cooking YouTube Shorts bot (v1.0.0)
Channel: https://www.youtube.com/@GoodFoodGoodMoodRecipies

One run = one vertical Short (1080x1920, ~40-58 s), fully automatic:

  1. RECIPE   next un-uploaded dish from recipes.yaml (or RECIPE_OVERRIDE)
  2. SCRIPT   Gemini writes a punchy recipe script as JSON (hook -> steps -> CTA)
              in Hindi (CONTENT_LANG=hi, default) or English (CONTENT_LANG=en)
  3. VOICE    free Microsoft edge-tts voice, one clip per scene, with
              word-level timestamps for the captions
  4. VISUALS  real cooking footage from Pexels (free API, portrait videos);
              fallback: AI food photo (Pollinations, free) with Ken Burns
              motion; last resort: a branded text card
  5. SOUND    background music (your files in assets/music/, otherwise a
              built-in synthesized lo-fi loop) ducked under the voice, plus
              sizzle / chop / whoosh sound effects
  6. CAPTIONS word-by-word highlighted captions burned into the video
              (+ the same captions uploaded as a YouTube .srt track)
  7. UPLOAD   YouTube Data API: #shorts title, full recipe in the description,
              tags, scheduled publish time (publishAt), channel guard

Usage:
    python cooking_shorts_bot.py            # normal daily run
    python cooking_shorts_bot.py --test     # build the video, do NOT upload
    python cooking_shorts_bot.py --demo     # offline smoke test: no API keys,
                                            # no network, beep "voice", cards
"""

import asyncio
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import requests
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VERSION = "1.0.0"

# ----------------------------------------------------------------------------
# CONFIG (all overridable from the workflow env)
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "output"
LOG_FILE = ROOT / "upload_log.json"
RECIPES_FILE = ROOT / os.getenv("RECIPES_FILE", "recipes.yaml")
FONT_DIR = ROOT / "assets" / "fonts"
MUSIC_DIR = ROOT / "assets" / "music"
FONT_BOLD = FONT_DIR / "Hind-Bold.ttf"
FONT_SEMI = FONT_DIR / "Hind-SemiBold.ttf"
FONT_NAME = "Hind"  # family name inside the .ttf (used by libass)

IST = ZoneInfo("Asia/Kolkata")
W, H, FPS = 1080, 1920, 30

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "GoodFoodGoodMood")
EXPECTED_CHANNEL_HANDLE = os.getenv("EXPECTED_CHANNEL_HANDLE", "goodfoodgoodmoodrecipies").lower().lstrip("@")
CONTENT_LANG = os.getenv("CONTENT_LANG", "hi").lower()          # hi | en
TTS_VOICE = os.getenv("TTS_VOICE", "") or (
    "hi-IN-SwaraNeural" if CONTENT_LANG == "hi" else "en-IN-NeerjaExpressiveNeural")
TTS_FALLBACK_VOICE = "hi-IN-MadhurNeural" if CONTENT_LANG == "hi" else "en-IN-NeerjaNeural"
TTS_RATE = os.getenv("TTS_RATE", "+8%")
MAX_SECONDS = float(os.getenv("MAX_SECONDS", "58"))
SCENE_GAP = 0.18                     # silence between scenes (s)
GEMINI_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_MODELS", "gemini-flash-latest,gemini-flash-lite-latest,gemini-pro-latest").split(",") if m.strip()]
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
USE_AI_IMAGES = os.getenv("USE_AI_IMAGES", "true").lower() == "true"
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.16"))
SFX_VOLUME = float(os.getenv("SFX_VOLUME", "0.22"))
PUBLISH_AT_IST_HOUR = os.getenv("PUBLISH_AT_IST_HOUR", "19")     # "off" = publish now
YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "26")     # 26 = Howto & Style
PLAYLIST_ID = os.getenv("PLAYLIST_ID", "").strip()
RECIPE_OVERRIDE = os.getenv("RECIPE_OVERRIDE", "").strip()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",   # caption upload
]

# Brand colours
SAFFRON = (255, 153, 51)
CREAM = (255, 244, 225)
DEEP = (60, 20, 10)

ARGS = set(sys.argv[1:])
TEST_MODE = "--test" in ARGS or os.getenv("TEST_MODE", "").lower() == "true"
DEMO = "--demo" in ARGS
if DEMO:
    TEST_MODE = True


def log(msg):
    print(f"[{datetime.now(IST):%H:%M:%S}] {msg}", flush=True)


def run(cmd, timeout=900):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))[:300]}\n{r.stderr[-2000:]}")
    return r.stdout


def ffprobe_duration(path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


# ----------------------------------------------------------------------------
# 1. RECIPE PICK + LOG
# ----------------------------------------------------------------------------
def load_log() -> list:
    if not LOG_FILE.exists():
        return []
    try:
        data = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_log_entry(entry: dict):
    data = load_log()
    data.append(entry)
    LOG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def pick_recipe() -> dict:
    recipes = (yaml.safe_load(RECIPES_FILE.read_text(encoding="utf-8")) or {}).get("recipes", [])
    if RECIPE_OVERRIDE:
        for r in recipes:
            if r["name"].lower() == RECIPE_OVERRIDE.lower():
                return r
        return {"name": RECIPE_OVERRIDE, "category": "main"}
    done = {e.get("recipe", "").lower() for e in load_log() if not e.get("test_mode")}
    for r in recipes:
        if r["name"].lower() not in done:
            return r
    # Every recipe used once: start a second round with a "style" twist.
    r = dict(recipes[datetime.now(IST).timetuple().tm_yday % len(recipes)])
    r["twist"] = random.choice(["restaurant style", "dhaba style", "quick 10-minute version",
                                "healthy version", "street style", "grandma style"])
    return r


# ----------------------------------------------------------------------------
# 2. SCRIPT (Gemini, JSON)
# ----------------------------------------------------------------------------
def _prompt(recipe: dict) -> str:
    dish = recipe["name"] + (f" ({recipe['twist']})" if recipe.get("twist") else "")
    if CONTENT_LANG == "hi":
        lang_rule = ("Write every 'say' line in natural spoken HINDI, Devanagari script, the way a warm "
                     "Indian home cook talks on Instagram Reels (common English food words like 'oil', "
                     "'paneer', 'mixer', 'medium flame' are fine, write them in Devanagari). "
                     "Write 'label', 'title', 'description', 'ingredients' and 'steps' in simple Hinglish "
                     "(Roman script) so they are searchable.")
        words = "110-135 Hindi words in total across all 'say' lines"
    else:
        lang_rule = ("Write everything in simple, friendly Indian English, the way a warm home cook talks "
                     "on Instagram Reels.")
        words = "105-130 words in total across all 'say' lines"
    return f"""You write scripts for "{CHANNEL_NAME}", an Indian cooking YouTube Shorts channel
(tagline: "Good food = Good mood!"). Today's dish: {dish} (category: {recipe.get('category', 'main')}).

Write a 45-55 second vertical Short that teaches the REAL recipe fast. {lang_rule}

Rules:
- Scene 1 is a scroll-stopping HOOK (max 12 words): a promise, secret tip or surprising claim. No "hello friends", no channel intro.
- Then 5-7 cooking scenes, one clear action each, with real quantities (cup / tbsp / tsp / grams) and flame level.
- Include one genuine pro tip that makes this version better than average.
- Last scene: a 1-line serving suggestion + "follow for a new recipe every day".
- Total spoken length: {words}. Short sentences. No emojis in 'say'.
- 'pexels_query': 2-4 plain ENGLISH words for searching stock cooking videos of exactly that action
  (e.g. "frying onions pan", "adding spices curry", "kneading dough", "pouring tea cup"). Concrete and visual.
- 'image_prompt': ENGLISH prompt for a photorealistic overhead/close-up food photo of that scene, Indian kitchen, natural light.
- 'sfx': one of "sizzle", "chop", "pour", "none" — the sound that fits the scene.
- 'label': 1-4 word on-screen step label, e.g. "Step 2: Tadka", "Pro Tip", "Serve hot".

Return ONLY JSON with this exact shape:
{{
  "title": "catchy YouTube title, max 70 chars, include the dish name, no hashtags",
  "hook_overlay": "2-5 word big on-screen text for scene 1",
  "scenes": [
    {{"say": "...", "label": "...", "pexels_query": "...", "image_prompt": "...", "sfx": "none"}}
  ],
  "ingredients": ["quantity + ingredient", "..."],
  "steps": ["short method step", "..."],
  "description": "2-3 line intro for the YouTube description (no hashtags)",
  "tags": ["12-18 search tags, mix English + Hinglish, e.g. '{recipe['name'].lower()} recipe'"],
  "hashtags": ["#shorts", "#indianfood", "... 5-8 total"]
}}"""


def _validate_script(d: dict) -> dict:
    scenes = [s for s in d.get("scenes", []) if isinstance(s, dict) and str(s.get("say", "")).strip()]
    if not (5 <= len(scenes) <= 12):
        raise ValueError(f"expected 5-12 scenes, got {len(scenes)}")
    for s in scenes:
        s["say"] = re.sub(r"\s+", " ", str(s["say"])).strip()
        s.setdefault("label", "")
        s.setdefault("pexels_query", "indian cooking")
        s.setdefault("image_prompt", "indian food close up")
        if s.get("sfx") not in ("sizzle", "chop", "pour", "none"):
            s["sfx"] = "none"
    d["scenes"] = scenes
    if not d.get("title"):
        raise ValueError("missing title")
    d.setdefault("hook_overlay", "")
    for k in ("ingredients", "steps", "tags", "hashtags"):
        d[k] = [str(x).strip() for x in (d.get(k) or []) if str(x).strip()]
    d.setdefault("description", "")
    return d


def generate_script(recipe: dict) -> dict:
    if DEMO:
        return _validate_script(DEMO_SCRIPT)
    from google import genai
    from google.genai import types
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=key, http_options={"timeout": 120_000})
    cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9)
    last = None
    for model in GEMINI_MODELS:
        for attempt in (1, 2):
            try:
                log(f"Gemini: {model} (attempt {attempt})")
                resp = client.models.generate_content(model=model, contents=_prompt(recipe), config=cfg)
                text = (resp.text or "").strip()
                text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
                data = _validate_script(json.loads(text))
                data["_model"] = model
                return data
            except Exception as e:
                last = e
                log(f"  failed: {str(e)[:200]}")
                time.sleep(4 * attempt)
    # No generic offline script on purpose: a weak video hurts a cooking channel more than a skipped day.
    raise SystemExit(f"All Gemini models failed, no video today. Last error: {last}")


# ----------------------------------------------------------------------------
# 3. VOICE (edge-tts, word timestamps)
# ----------------------------------------------------------------------------
async def _edge_tts(text: str, voice: str, rate: str, mp3: Path) -> list:
    import edge_tts
    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                st = chunk["offset"] / 1e7
                words.append({"w": chunk["text"], "s": st, "e": st + chunk["duration"] / 1e7})
    return words


def _even_word_times(text: str, dur: float) -> list:
    """Fallback timing when the voice gives no word boundaries: split by character weight."""
    toks = text.split()
    weights = [len(t) + 2 for t in toks]
    total = sum(weights) or 1
    t, out, usable = 0.05, [], max(dur - 0.1, 0.1)
    for tok, wgt in zip(toks, weights):
        d = usable * wgt / total
        out.append({"w": tok, "s": t, "e": t + d})
        t += d
    return out


def _decode_to_array(path: Path, sr=44100) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1",
                          "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def synth_voice(scenes: list, rate: str) -> tuple:
    """Returns (voice_array, sr, scene_timing[], words[]) — all times on the final timeline."""
    sr = 44100
    clips_dir = WORK / "voice"
    clips_dir.mkdir(parents=True, exist_ok=True)
    pieces, timing, all_words, cursor = [], [], [], 0.0
    for i, sc in enumerate(scenes):
        mp3 = clips_dir / f"s{i:02d}.mp3"
        words = []
        if DEMO:
            n = len(sc["say"].split())
            dur = 0.36 * n + 0.2
            t = np.arange(int(dur * sr)) / sr
            arr = 0.15 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)
            arr = arr.astype(np.float32)
        else:
            for voice in (TTS_VOICE, TTS_FALLBACK_VOICE):
                try:
                    words = asyncio.run(_edge_tts(sc["say"], voice, rate, mp3))
                    if mp3.exists() and mp3.stat().st_size > 1000:
                        break
                except Exception as e:
                    log(f"  edge-tts {voice} failed: {e}")
                    time.sleep(3)
            else:
                raise SystemExit("edge-tts failed for every voice")
            arr = _decode_to_array(mp3, sr)
        dur = len(arr) / sr
        if not words:
            words = _even_word_times(sc["say"], dur)
        for w in words:
            all_words.append({"w": w["w"], "s": cursor + w["s"], "e": cursor + w["e"], "scene": i})
        seg_len = dur + SCENE_GAP
        timing.append({"start": cursor, "dur": seg_len})
        pieces.append(arr)
        pieces.append(np.zeros(int(SCENE_GAP * sr), dtype=np.float32))
        cursor += seg_len
    # small tail so the last word isn't clipped by the end card
    pieces.append(np.zeros(int(0.5 * sr), dtype=np.float32))
    timing[-1]["dur"] += 0.5
    return np.concatenate(pieces), sr, timing, all_words


# ----------------------------------------------------------------------------
# 4. VISUALS
# ----------------------------------------------------------------------------
_used_pexels = set()


def _http_get(url, **kw):
    kw.setdefault("timeout", 60)
    for attempt in range(3):
        try:
            r = requests.get(url, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(3 * (attempt + 1))
                continue
            return r
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
    return None


def pexels_video(query: str, min_dur: float, dest: Path) -> bool:
    if not PEXELS_API_KEY or DEMO:
        return False
    r = _http_get("https://api.pexels.com/videos/search",
                  headers={"Authorization": PEXELS_API_KEY},
                  params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 20})
    if not r or r.status_code != 200:
        return False
    vids = [v for v in r.json().get("videos", []) if v["id"] not in _used_pexels]
    # prefer clips long enough for the scene
    vids.sort(key=lambda v: (v.get("duration", 0) < min_dur, random.random()))
    for v in vids[:6]:
        files = [f for f in v.get("video_files", [])
                 if f.get("height") and f.get("width") and f["height"] >= f["width"]
                 and 960 <= f["height"] <= 2560 and f.get("file_type") == "video/mp4"]
        if not files:
            continue
        files.sort(key=lambda f: abs(f["height"] - 1920))
        dl = _http_get(files[0]["link"], timeout=180)
        if dl and dl.status_code == 200 and len(dl.content) > 50_000:
            dest.write_bytes(dl.content)
            _used_pexels.add(v["id"])
            return True
    return False


def ai_image(prompt: str, dest: Path, seed: int) -> bool:
    if not USE_AI_IMAGES or DEMO:
        return False
    full = (f"{prompt}, Indian home kitchen, food photography, photorealistic, appetizing, "
            f"natural window light, shallow depth of field, vertical composition, no text, no watermark")
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(full) +
           f"?width=1080&height=1920&nologo=true&seed={seed}&model=flux")
    r = _http_get(url, timeout=180)
    if r and r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        dest.write_bytes(r.content)
        try:
            Image.open(dest).verify()
            return True
        except Exception:
            return False
    return False


def _font(size, bold=True):
    try:
        return ImageFont.truetype(str(FONT_BOLD if bold else FONT_SEMI), size)
    except Exception:
        return ImageFont.load_default()


def text_card(title: str, sub: str, dest: Path, seed=0):
    """Branded fallback frame: warm gradient + spice dots + dish name."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H))
    top, bot = np.array((255, 183, 77)), np.array((178, 34, 34))
    grad = np.linspace(0, 1, H)[:, None]
    arr = (top * (1 - grad) + bot * grad)[:, None, :].repeat(W, axis=1)
    img = Image.fromarray(arr.astype(np.uint8)[:, :, :3].reshape(H, W, 3))
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(160):
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(4, 22)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 240, 200, rnd.randint(20, 70)))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((80, 640, W - 80, 1280), 48, fill=(40, 12, 6, 170))
    f1, f2 = _font(92), _font(54, False)
    lines, cur = [], ""
    for wd in title.split():
        test = (cur + " " + wd).strip()
        if d.textlength(test, font=f1) > W - 240 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = test
    lines.append(cur)
    y = 960 - len(lines) * 55 - 30
    for ln in lines[:3]:
        d.text((W / 2, y), ln, font=f1, fill=CREAM, anchor="mm")
        y += 110
    d.text((W / 2, y + 20), sub, font=f2, fill=SAFFRON, anchor="mm")
    img.save(dest, quality=92)


def render_scene(i: int, scene: dict, dur: float, recipe: dict, out: Path) -> str:
    """Render one silent 1080x1920 clip of exactly `dur` seconds. Returns the source used."""
    vdir = WORK / "visuals"
    vdir.mkdir(parents=True, exist_ok=True)
    grade = "eq=saturation=1.12:contrast=1.04,vignette=PI/5"
    common = ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", "-t", f"{dur:.3f}"]

    # (a) real stock footage
    queries = [scene["pexels_query"], " ".join(scene["pexels_query"].split()[-2:]),
               f"{recipe['name']} indian food", "indian cooking"]
    for q in dict.fromkeys(q for q in queries if q.strip()):
        src = vdir / f"s{i:02d}.mp4"
        if pexels_video(q, dur, src):
            try:
                sdur = ffprobe_duration(src)
                ss = rnd_offset(sdur, dur)
                speed = 1.0 if sdur >= dur else max(sdur / dur, 0.5)   # slow down short clips a bit
                vf = (f"setpts=PTS/{speed:.3f},scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H},fps={FPS},{grade},setsar=1,"
                      f"tpad=stop_mode=clone:stop_duration={dur:.2f}")
                run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ss:.2f}", "-i", str(src),
                     "-vf", vf, *common, str(out)])
                return f"pexels:{q}"
            except Exception as e:
                log(f"  pexels clip render failed: {e}")

    # (b) AI food photo, (c) branded card — both get slow Ken Burns motion
    img = vdir / f"s{i:02d}.jpg"
    source = "ai_image"
    if not ai_image(scene["image_prompt"], img, seed=hash(scene["image_prompt"]) % 100000):
        text_card(recipe["name"], scene.get("label") or CHANNEL_NAME, img, seed=i)
        source = "card"
    frames = max(int(dur * FPS), 1)
    zin = i % 2 == 0
    z = f"min(1+0.0009*on,1.15)" if zin else f"max(1.15-0.0009*on,1.0)"
    vf = (f"scale={int(W * 1.6)}:{int(H * 1.6)}:force_original_aspect_ratio=increase,"
          f"crop={int(W * 1.6)}:{int(H * 1.6)},"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
          f"{grade if source != 'card' else 'null'},setsar=1")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(img), "-vf", vf, *common, str(out)])
    return source


def rnd_offset(src_dur, need):
    slack = src_dur - need - 0.2
    return random.uniform(0.2, slack) if slack > 0.4 else 0.0


# ----------------------------------------------------------------------------
# 5. SOUND (music + SFX, mixed in numpy)
# ----------------------------------------------------------------------------
def synth_music(seconds: float, sr=44100, seed=None) -> np.ndarray:
    """Warm lo-fi loop: soft pad chords + plucked arpeggio + gentle shaker. Royalty-free by construction."""
    rnd = np.random.default_rng(seed)
    bpm = 88
    beat = 60 / bpm
    n = int(seconds * sr)
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float32)
    # I - vi - IV - V in D major-ish, one chord per bar (4 beats)
    roots = [146.83, 123.47, 98.00, 110.00]
    chords = [[1, 1.26, 1.5], [1, 1.19, 1.5], [1, 1.26, 1.5], [1, 1.26, 1.5]]
    bar = 4 * beat
    for b in range(int(seconds / bar) + 1):
        root, ch = roots[b % 4], chords[b % 4]
        s0, s1 = int(b * bar * sr), min(int((b + 1) * bar * sr), n)
        if s0 >= n:
            break
        tt = t[s0:s1] - b * bar
        env = np.minimum(tt / 0.6, 1) * np.minimum((bar - tt) / 0.4, 1)
        pad = sum(np.sin(2 * np.pi * root * r * tt) + 0.3 * np.sin(2 * np.pi * root * r * 2 * tt) for r in ch)
        out[s0:s1] += 0.06 * env * pad
        # arpeggio: 8 eighth notes per bar
        for k in range(8):
            a0 = s0 + int(k * beat / 2 * sr)
            if a0 >= n:
                break
            ln = min(int(0.5 * sr), n - a0)
            ta = np.arange(ln) / sr
            f = root * 2 * ch[[0, 1, 2, 1, 0, 2, 1, 2][k]]
            pl = np.sin(2 * np.pi * f * ta) + 0.4 * np.sin(2 * np.pi * 2 * f * ta)
            out[a0:a0 + ln] += 0.05 * np.exp(-ta * 7) * pl
        # soft kick on 1 and 3, shaker on off-beats
        for k in range(4):
            k0 = s0 + int(k * beat * sr)
            if k0 >= n:
                break
            if k % 2 == 0:
                ln = min(int(0.25 * sr), n - k0)
                tk = np.arange(ln) / sr
                out[k0:k0 + ln] += 0.18 * np.exp(-tk * 18) * np.sin(2 * np.pi * (55 + 60 * np.exp(-tk * 30)) * tk)
            h0 = k0 + int(beat / 2 * sr)
            if h0 < n:
                ln = min(int(0.06 * sr), n - h0)
                out[h0:h0 + ln] += 0.025 * rnd.standard_normal(ln) * np.exp(-np.arange(ln) / sr * 60)
    # gentle low-pass (moving average) for the lo-fi feel
    k = np.ones(6) / 6
    out = np.convolve(out, k, mode="same").astype(np.float32)
    return out / (np.abs(out).max() + 1e-6) * 0.8


def load_music(seconds: float, sr=44100) -> tuple:
    files = sorted([p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]) \
        if MUSIC_DIR.exists() else []
    if files:
        f = random.choice(files)
        arr = _decode_to_array(f, sr)
        if len(arr) > sr:
            reps = int(math.ceil(seconds * sr / len(arr)))
            arr = np.tile(arr, reps)[: int(seconds * sr)]
            arr = arr / (np.abs(arr).max() + 1e-6) * 0.8
            return arr, f.name
    return synth_music(seconds, sr), "synth-lofi"


def sfx(kind: str, seconds: float, sr=44100, seed=0) -> np.ndarray:
    rnd = np.random.default_rng(seed)
    n = int(seconds * sr)
    if kind == "sizzle":
        noise = rnd.standard_normal(n).astype(np.float32)
        hp = noise - np.convolve(noise, np.ones(4) / 4, mode="same")       # crude high-pass = hiss
        crackle = np.zeros(n, dtype=np.float32)
        for p in rnd.integers(0, n, size=int(seconds * 45)):
            ln = min(int(0.004 * sr), n - p)
            crackle[p:p + ln] += rnd.uniform(0.3, 1.0) * np.exp(-np.arange(ln) / (0.0008 * sr))
        mod = 0.75 + 0.25 * np.sin(2 * np.pi * 0.7 * np.arange(n) / sr)
        out = 0.35 * hp * mod + 0.5 * crackle
    elif kind == "chop":
        out = np.zeros(n, dtype=np.float32)
        step = 0.32
        for k in range(int(seconds / step)):
            p = int((k * step + rnd.uniform(-0.03, 0.03)) * sr)
            if p < 0 or p >= n:
                continue
            ln = min(int(0.05 * sr), n - p)
            tt = np.arange(ln) / sr
            out[p:p + ln] += np.exp(-tt * 90) * (np.sin(2 * np.pi * 180 * tt) + 0.6 * rnd.standard_normal(ln))
    elif kind == "pour":
        noise = rnd.standard_normal(n).astype(np.float32)
        lp = np.convolve(noise, np.ones(30) / 30, mode="same")
        bub = np.sin(2 * np.pi * (300 + 150 * np.sin(2 * np.pi * 9 * np.arange(n) / sr)) * np.arange(n) / sr)
        out = 2.5 * lp + 0.08 * bub * (rnd.random(n) > 0.6)
    elif kind == "whoosh":
        noise = rnd.standard_normal(n).astype(np.float32)
        env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
        out = np.convolve(noise, np.ones(12) / 12, mode="same") * env * 1.6
    else:
        return np.zeros(n, dtype=np.float32)
    fade = min(int(0.15 * sr), n // 2)
    if fade:
        out[:fade] *= np.linspace(0, 1, fade)
        out[-fade:] *= np.linspace(1, 0, fade)
    return (out / (np.abs(out).max() + 1e-6)).astype(np.float32)


def mix_audio(voice: np.ndarray, sr: int, scenes: list, timing: list, dest: Path) -> str:
    n = len(voice)
    music, music_name = load_music(n / sr + 1, sr)
    music = music[:n]
    # duck music under the voice (envelope follower)
    env = np.convolve(np.abs(voice), np.ones(int(0.12 * sr)) / int(0.12 * sr), mode="same")
    duck = np.where(env > 0.01, 0.45, 1.0)
    duck = np.convolve(duck, np.ones(int(0.25 * sr)) / int(0.25 * sr), mode="same")
    mix = voice * 1.0 + music * MUSIC_VOLUME * duck
    fx = np.zeros(n, dtype=np.float32)
    for i, (sc, tm) in enumerate(zip(scenes, timing)):
        s0 = int(tm["start"] * sr)
        if sc.get("sfx") in ("sizzle", "chop", "pour"):
            clip = sfx(sc["sfx"], tm["dur"], sr, seed=i)
            fx[s0:s0 + len(clip)] += clip[: n - s0] * (0.55 if sc["sfx"] == "sizzle" else 0.7)
        if i > 0:   # whoosh on every cut
            w = sfx("whoosh", 0.35, sr, seed=100 + i)
            w0 = max(s0 - int(0.17 * sr), 0)
            fx[w0:w0 + len(w)] += w[: n - w0] * 0.5
    mix = mix + fx * SFX_VOLUME
    # music fade in/out + soft limiter
    f = int(0.4 * sr)
    mix[:f] *= np.linspace(0.3, 1, f)
    mix[-f:] *= np.linspace(1, 0, f)
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    wav = dest.with_suffix(".raw")
    wav.write_bytes(pcm.tobytes())
    run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(wav),
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
         str(dest)])
    wav.unlink(missing_ok=True)
    return music_name


# ----------------------------------------------------------------------------
# 6. CAPTIONS (ASS burned in + SRT upload)
# ----------------------------------------------------------------------------
def _ass_t(t: float) -> str:
    t = max(t, 0)
    h, m = int(t // 3600), int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _clean_word(w: str) -> str:
    return w.strip()


def group_words(words: list, max_words=3, max_chars=18) -> list:
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["scene"] != cur[-1]["scene"]
                    or sum(len(x["w"]) + 1 for x in cur) + len(w["w"]) > max_chars
                    or w["s"] - cur[-1]["e"] > 0.45):
            groups.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[।.!?,]$", w["w"]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(script: dict, words: list, timing: list, dest: Path):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT_NAME},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,2,90,90,560,1
Style: Label,{FONT_NAME},64,&H00FFFFFF,&H00FFFFFF,&H003399FF,&H00000000,-1,0,0,0,100,100,0,0,3,20,0,8,90,90,230,1
Style: Hook,{FONT_NAME},118,&H0033CCFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,9,4,5,80,80,0,1
Style: Brand,{FONT_NAME},44,&H00E1F4FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,1,0,1,4,2,8,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    total = timing[-1]["start"] + timing[-1]["dur"]
    # brand tag for the whole video
    ev.append(f"Dialogue: 0,{_ass_t(0)},{_ass_t(total)},Brand,,0,0,0,,{_esc(CHANNEL_NAME)}")
    # hook overlay on scene 1 (pop in)
    if script.get("hook_overlay"):
        hk = _esc(script["hook_overlay"].upper() if CONTENT_LANG == "en" else script["hook_overlay"])
        ev.append(f"Dialogue: 2,{_ass_t(0.05)},{_ass_t(timing[0]['dur'] - 0.1)},Hook,,0,0,0,,"
                  r"{\pos(540,820)\fscx60\fscy60\t(0,180,\fscx108\fscy108)\t(180,300,\fscx100\fscy100)\fad(0,150)}" + hk)
    # step labels (top pill)
    for i, (sc, tm) in enumerate(zip(script["scenes"], timing)):
        if i == 0 or not sc.get("label"):
            continue
        ev.append(f"Dialogue: 1,{_ass_t(tm['start'] + 0.05)},{_ass_t(tm['start'] + tm['dur'] - 0.05)},Label,,0,0,0,,"
                  r"{\fad(150,100)}" + _esc(sc["label"]))
    # word-by-word captions: active word yellow + slightly bigger
    groups = group_words(words)
    for gi, g in enumerate(groups):
        g_end = g[-1]["e"] + 0.12
        if gi + 1 < len(groups):                 # never overlap the next group (libass would stack them)
            g_end = min(g_end, groups[gi + 1][0]["s"])
        for k, w in enumerate(g):
            st = w["s"]
            en = g[k + 1]["s"] if k + 1 < len(g) else g_end
            parts = []
            for j, x in enumerate(g):
                txt = _esc(_clean_word(x["w"]))
                if CONTENT_LANG == "en":
                    txt = txt.upper()
                if j == k:
                    parts.append(r"{\c&H00D7FF&\fscx112\fscy112}" + txt + r"{\c&HFFFFFF&\fscx100\fscy100}")
                else:
                    parts.append(txt)
            pop = r"{\fscx85\fscy85\t(0,90,\fscx100\fscy100)}" if k == 0 else ""
            ev.append(f"Dialogue: 3,{_ass_t(st)},{_ass_t(en)},Cap,,0,0,0,,{pop}" + " ".join(parts))
    dest.write_text(header + "\n".join(ev) + "\n", encoding="utf-8")


def _srt_t(t):
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def build_srt(words: list, dest: Path):
    lines = []
    for i, g in enumerate(group_words(words, max_words=6, max_chars=36), 1):
        lines += [str(i), f"{_srt_t(g[0]['s'])} --> {_srt_t(g[-1]['e'] + 0.1)}",
                  " ".join(x["w"] for x in g), ""]
    dest.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------------
# 7. ASSEMBLE
# ----------------------------------------------------------------------------
def build_video(script: dict, recipe: dict, slug: str) -> dict:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    OUT.mkdir(exist_ok=True)

    log("Voice ...")
    voice, sr, timing, words = synth_voice(script["scenes"], TTS_RATE)
    total = len(voice) / sr
    if total > MAX_SECONDS and not DEMO:
        log(f"  {total:.1f}s is over {MAX_SECONDS}s — re-voicing faster")
        voice, sr, timing, words = synth_voice(script["scenes"], "+22%")
        total = len(voice) / sr
    log(f"  narration {total:.1f}s, {len(words)} words")

    log("Visuals ...")
    clips, sources = [], []
    for i, (sc, tm) in enumerate(zip(script["scenes"], timing)):
        out = WORK / f"clip{i:02d}.mp4"
        src = render_scene(i, sc, tm["dur"], recipe, out)
        log(f"  scene {i + 1}/{len(timing)} {tm['dur']:.1f}s <- {src}")
        clips.append(out)
        sources.append(src)

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    silent = WORK / "silent.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(silent)])

    log("Sound ...")
    audio = WORK / "mix.m4a"
    music_name = mix_audio(voice, sr, script["scenes"], timing, audio)

    log("Captions + final encode ...")
    ass = WORK / "captions.ass"
    build_ass(script, words, timing, ass)
    srt = OUT / f"{slug}.srt"
    build_srt(words, srt)
    final = OUT / f"{slug}.mp4"
    ass_arg = ass.as_posix().replace(":", r"\:")
    fonts_arg = FONT_DIR.as_posix().replace(":", r"\:")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(audio),
         "-vf", f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'",
         "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(final)], timeout=1800)
    dur = ffprobe_duration(final)
    log(f"  done: {final.name} ({dur:.1f}s, {final.stat().st_size / 1e6:.1f} MB)")
    return {"video": final, "srt": srt, "duration": round(dur, 1), "sources": sources, "music": music_name}


# ----------------------------------------------------------------------------
# 8. YOUTUBE
# ----------------------------------------------------------------------------
def youtube_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(ROOT / "token.json"), SCOPES)
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def channel_guard(yt):
    items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    if not items:
        raise SystemExit("No YouTube channel on this token.")
    sn = items[0]["snippet"]
    handle = (sn.get("customUrl") or "").lower().lstrip("@")
    log(f"Uploading as: {sn['title']} (@{handle})")
    if EXPECTED_CHANNEL_HANDLE and handle != EXPECTED_CHANNEL_HANDLE:
        raise SystemExit(f"Channel guard: token belongs to @{handle}, expected @{EXPECTED_CHANNEL_HANDLE}. "
                         "Re-run reauth_youtube.py and pick the cooking channel.")


def compute_publish_at():
    if PUBLISH_AT_IST_HOUR.lower() == "off":
        return None
    now = datetime.now(IST)
    slot = now.replace(hour=int(PUBLISH_AT_IST_HOUR), minute=0, second=0, microsecond=0)
    if slot - now < timedelta(minutes=20):
        return None          # too late for today's slot -> publish immediately
    return slot.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_metadata(script: dict, recipe: dict, sources: list) -> tuple:
    title = re.sub(r"\s+", " ", script["title"]).strip().replace("<", "").replace(">", "")
    title = (title[:88] + " #shorts") if "#shorts" not in title.lower() else title[:100]
    tags_h = [h if h.startswith("#") else "#" + h for h in script["hashtags"]]
    if "#shorts" not in [h.lower() for h in tags_h]:
        tags_h.insert(0, "#shorts")
    desc = [script.get("description", "").strip(), "",
            "🛒 INGREDIENTS"] + [f"• {x}" for x in script["ingredients"]] + ["",
            "👩‍🍳 METHOD"] + [f"{i}. {x}" for i, x in enumerate(script["steps"], 1)] + ["",
            f"🔔 Subscribe to {CHANNEL_NAME} for a new Indian recipe every day!", "Good food = Good mood! 😋", ""]
    if any(s.startswith("pexels") for s in sources):
        desc.append("Video clips: Pexels.")
    if "ai_image" in sources:
        desc.append("Some food visuals are AI-generated.")
    desc += ["", " ".join(tags_h[:10])]
    description = "\n".join(desc)[:4900].replace("<", "").replace(">", "")
    tags, total = [], 0
    for t in script["tags"] + [recipe["name"], f"{recipe['name']} recipe", "indian recipe", "shorts"]:
        t = t.replace("#", "").replace("<", "").replace(">", "").strip()[:60]
        cost = len(t) + (2 if " " in t else 0) + 1
        if t and t.lower() not in [x.lower() for x in tags] and total + cost <= 480:
            tags.append(t)
            total += cost
    return title, description, tags


def upload(yt, video: Path, title, desc, tags, synthetic: bool) -> str:
    from googleapiclient.http import MediaFileUpload
    publish_at = compute_publish_at()
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": YOUTUBE_CATEGORY_ID,
                    "defaultLanguage": CONTENT_LANG, "defaultAudioLanguage": CONTENT_LANG},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": synthetic, "embeddable": True},
    }
    if publish_at:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at
        log(f"Scheduled public at {publish_at} (UTC)")
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    resp, tries = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                log(f"  upload {int(status.progress() * 100)}%")
        except Exception as e:
            tries += 1
            if tries > 5:
                raise
            log(f"  upload retry {tries}: {e}")
            time.sleep(5 * tries)
    return resp["id"]


def upload_captions(yt, vid, srt: Path):
    from googleapiclient.http import MediaFileUpload
    try:
        yt.captions().insert(part="snippet", body={"snippet": {
            "videoId": vid, "language": CONTENT_LANG,
            "name": "Hindi" if CONTENT_LANG == "hi" else "English", "isDraft": False}},
            media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
        log("  captions uploaded")
    except Exception as e:
        log(f"  captions upload skipped: {e}")


def add_to_playlist(yt, vid):
    if not PLAYLIST_ID:
        return
    try:
        yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": PLAYLIST_ID, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        log("  added to playlist")
    except Exception as e:
        log(f"  playlist skipped: {e}")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    log(f"{CHANNEL_NAME} Shorts bot v{VERSION} | lang={CONTENT_LANG} voice={TTS_VOICE} "
        f"| test={TEST_MODE} demo={DEMO}")
    if not FONT_BOLD.exists():
        raise SystemExit(f"Missing font {FONT_BOLD}")
    recipe = pick_recipe()
    log(f"Recipe: {recipe['name']}" + (f" ({recipe['twist']})" if recipe.get("twist") else ""))
    yt = None
    if not TEST_MODE:
        yt = youtube_service()
        channel_guard(yt)              # fail BEFORE spending time on a video for the wrong channel

    script = generate_script(recipe)
    log(f"Title: {script['title']}  ({len(script['scenes'])} scenes, model={script.get('_model', 'demo')})")
    slug = datetime.now(IST).strftime("%Y-%m-%d") + "-" + re.sub(r"[^a-z0-9]+", "-", recipe["name"].lower()).strip("-")
    (OUT).mkdir(exist_ok=True)
    (OUT / f"{slug}.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    res = build_video(script, recipe, slug)
    title, desc, tags = build_metadata(script, recipe, res["sources"])
    (OUT / f"{slug}-description.txt").write_text(f"{title}\n\n{desc}\n\nTAGS: {', '.join(tags)}", encoding="utf-8")

    entry = {"date": datetime.now(IST).date().isoformat(), "recipe": recipe["name"], "title": title,
             "duration": res["duration"], "visuals": res["sources"], "music": res["music"],
             "voice": TTS_VOICE, "lang": CONTENT_LANG, "model": script.get("_model"),
             "test_mode": TEST_MODE, "bot_version": VERSION}
    if TEST_MODE:
        log("TEST MODE: not uploading. Files are in output/.")
        if not DEMO:
            save_log_entry(entry)
        return

    synthetic = "ai_image" in res["sources"]
    vid = upload(yt, res["video"], title, desc, tags, synthetic)
    log(f"Uploaded: https://youtube.com/shorts/{vid}")
    upload_captions(yt, vid, res["srt"])
    add_to_playlist(yt, vid)
    entry["video_id"] = vid
    save_log_entry(entry)


DEMO_SCRIPT = {
    "title": "Street Style Masala Chai in 5 Minutes",
    "hook_overlay": "Tapri wali chai ka secret",
    "scenes": [
        {"say": "Tapri jaisi kadak masala chai ka asli secret aaj bata rahi hoon.", "label": "", "sfx": "none",
         "pexels_query": "masala chai cup", "image_prompt": "masala chai in glass"},
        {"say": "Ek pan mein dedh cup paani daalo aur medium flame par garam karo.", "label": "Step 1: Paani",
         "sfx": "pour", "pexels_query": "pouring water pan", "image_prompt": "water in steel pan"},
        {"say": "Adrak ko kootkar daalo, saath mein do elaichi aur ek chhota tukda dalchini.",
         "label": "Step 2: Masala", "sfx": "chop", "pexels_query": "crushing ginger mortar",
         "image_prompt": "crushed ginger cardamom"},
        {"say": "Do chammach chai patti daalo aur do minute tak achhe se ubaalo.", "label": "Step 3: Patti",
         "sfx": "sizzle", "pexels_query": "boiling tea pot", "image_prompt": "boiling tea leaves"},
        {"say": "Pro tip: doodh daalne se pehle chai ko gehra rang lene do, tabhi kadak banegi.",
         "label": "Pro Tip", "sfx": "none", "pexels_query": "dark tea boiling",
         "image_prompt": "dark tea decoction"},
        {"say": "Ab ek cup doodh aur swaad anusaar cheeni daalo, teen baar ubaal aane do.",
         "label": "Step 4: Doodh", "sfx": "pour", "pexels_query": "pouring milk tea",
         "image_prompt": "milk pouring into tea"},
        {"say": "Chhaan kar garam garam parle-g ke saath serve karo. Roz nayi recipe ke liye follow karo!",
         "label": "Serve hot", "sfx": "none", "pexels_query": "tea biscuits",
         "image_prompt": "chai with biscuits"},
    ],
    "ingredients": ["1.5 cup water", "1 cup milk", "2 tsp tea leaves", "1 inch ginger", "2 cardamom",
                    "small cinnamon stick", "sugar to taste"],
    "steps": ["Boil water", "Add crushed ginger and spices", "Add tea leaves, boil 2 min",
              "Add milk and sugar, boil 3 times", "Strain and serve"],
    "description": "Kadak tapri style masala chai at home in 5 minutes.",
    "tags": ["masala chai", "chai recipe", "tapri chai", "indian tea"],
    "hashtags": ["#shorts", "#masalachai", "#indianfood", "#chai"],
}

if __name__ == "__main__":
    main()
