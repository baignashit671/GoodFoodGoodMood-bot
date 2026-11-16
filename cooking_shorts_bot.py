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
  4. VISUALS  your own clips (assets/clips) -> Pexels / Pixabay stock video ->
              free AI food photos (Pollinations, Cloudflare Workers AI) ->
              public-domain photos (Wikimedia Commons) -> branded card;
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

VERSION = "1.5.1"

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
STICKER_DIR = ROOT / "assets" / "stickers"
USE_STICKERS = os.getenv("USE_STICKERS", "true").lower() == "true"
STICKERS = ("fire", "yum", "heart_eyes", "drool", "chef", "sparkles", "hundred", "tea", "curry", "chili",
            "thumbs_up", "clap", "point_down", "bell", "heart", "star_struck")
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
    "GEMINI_MODELS", "gemini-flash-latest,gemini-flash-lite-latest").split(",") if m.strip()]
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()   # optional: faster, no watermark
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()                 # optional: Cloudflare Workers AI
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "").strip()
USE_WIKIMEDIA = os.getenv("USE_WIKIMEDIA", "true").lower() == "true"
CLIPS_DIR = ROOT / "assets" / "clips"
# Order of visual sources per scene (first one that delivers wins).
VISUAL_ORDER = [x.strip() for x in os.getenv(
    "VISUAL_ORDER", "own,pexels,pixabay,pollinations,cloudflare,wikimedia").split(",") if x.strip()]
HTTP_UA = "GoodFoodShortsBot/1.3 (https://www.youtube.com/@GoodFoodGoodMoodRecipies; automated recipe shorts)"
USE_AI_IMAGES = os.getenv("USE_AI_IMAGES", "true").lower() == "true"
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.16"))
SFX_VOLUME = float(os.getenv("SFX_VOLUME", "0.22"))
PUBLISH_AT_IST_HOUR = os.getenv("PUBLISH_AT_IST_HOUR", "19")     # "off" = publish now
YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "26")     # 26 = Howto & Style
PLAYLIST_ID = os.getenv("PLAYLIST_ID", "").strip()
RECIPE_OVERRIDE = os.getenv("RECIPE_OVERRIDE", "").strip()
AUTO_PLAYLISTS = os.getenv("AUTO_PLAYLISTS", "true").lower() == "true"   # one playlist per recipe category
POST_FIRST_COMMENT = os.getenv("POST_FIRST_COMMENT", "true").lower() == "true"
SET_THUMBNAIL = os.getenv("SET_THUMBNAIL", "true").lower() == "true"
MUSIC_MOODS = ("upbeat", "desi", "lofi", "festive", "chill")
CATEGORY_PLAYLISTS = {
    "breakfast": "Indian Breakfast Recipes", "street-food": "Indian Street Food Recipes",
    "sweet": "Indian Sweets & Desserts", "drink": "Chai, Lassi & Indian Drinks",
    "south-indian": "South Indian Recipes", "gujarati": "Gujarati Recipes",
    "non-veg": "Non-Veg Indian Recipes", "indo-chinese": "Indo-Chinese Recipes",
    "snack": "Indian Snacks Recipes", "rice": "Rice, Pulao & Biryani Recipes", "dal": "Dal Recipes",
    "sabzi": "Sabzi Recipes", "bread": "Roti, Paratha & Puri Recipes", "chutney": "Chutney & Pickle Recipes",
    "side": "Raita & Salad Recipes", "main": "Indian Main Course Recipes", "fasting": "Vrat / Fasting Recipes",
}

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


def pick_recipe(channel_titles=None) -> dict:
    """Next recipe not uploaded yet. 'Uploaded' = in upload_log.json OR its name appears in the title of one
    of the channel's recent uploads (so a wiped/overwritten log can never cause a repeat)."""
    recipes = (yaml.safe_load(RECIPES_FILE.read_text(encoding="utf-8")) or {}).get("recipes", [])
    titles = " || ".join(t.lower() for t in (channel_titles or []))
    if RECIPE_OVERRIDE:
        for r in recipes:
            if r["name"].lower() == RECIPE_OVERRIDE.lower():
                return r
        return {"name": RECIPE_OVERRIDE, "category": "main"}
    done = {e.get("recipe", "").lower() for e in load_log() if not e.get("test_mode")}
    for r in recipes:
        if r["name"].lower() not in done and r["name"].lower() not in titles:
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
- 'sticker': one animated emoji sticker for the scene, one of: fire, yum, heart_eyes, drool, chef, sparkles,
  hundred, tea, curry, chili, thumbs_up, clap, point_down, bell, heart, star_struck, none.
  Hook -> drool/fire/star_struck, pro tip -> sparkles/hundred, spicy step -> chili, last scene -> bell. Vary them.
- LOOP: Shorts replay automatically. Make the LAST 'say' line end with a short phrase that flows naturally back
  into the hook's first words, so the replay feels seamless and people watch it again.

Return ONLY JSON with this exact shape:
{{
  "title": "catchy YouTube title, max 70 chars, include the dish name, no hashtags",
  "hook_overlay": "2-5 word big on-screen text for scene 1",
  "scenes": [
    {{"say": "...", "label": "...", "pexels_query": "...", "image_prompt": "...", "sfx": "none", "sticker": "yum"}}
  ],
  "ingredients": ["quantity + ingredient", "..."],
  "steps": ["short method step", "..."],
  "description": "2-3 line intro for the YouTube description (no hashtags)",
  "tags": ["12-18 search tags, mix English + Hinglish, e.g. '{recipe['name'].lower()} recipe'"],
  "hashtags": ["#shorts", "#indianfood", "... 5-8 total"],
  "music_mood": "one of: upbeat, desi, lofi, festive, chill (what fits this dish's vibe)",
  "seo": {{
    "primary_keyword": "the exact phrase people type in YouTube search, e.g. '{recipe['name'].lower()} recipe'",
    "title_en": "SEARCH title, max 70 chars, STARTS with the primary keyword, then a benefit/hook, e.g. 'Masala Chai Recipe | Tapri Style Kadak Chai in 5 Min'",
    "title_hi": "same title in Hindi (Devanagari), max 70 chars, include the dish name",
    "description_hook": "first 2 description lines, max 150 chars, natural sentence containing the primary keyword + 1 secondary keyword",
    "description_hi": "2-line Hindi (Devanagari) summary for Hindi viewers",
    "secondary_keywords": ["6-10 related search phrases people really search: hinglish + english, e.g. 'chai kaise banaye', 'adrak wali chai'"],
    "thumbnail_text": "2-4 word BIG thumbnail text in the video's language, emotional/curiosity, e.g. 'TAPRI WALI CHAI' or 'असली स्वाद का राज'"
  }}
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
        if s.get("sticker") not in STICKERS:
            s["sticker"] = "none"
    d["scenes"] = scenes
    if not d.get("title"):
        raise ValueError("missing title")
    d.setdefault("hook_overlay", "")
    for k in ("ingredients", "steps", "tags", "hashtags"):
        d[k] = [str(x).strip() for x in (d.get(k) or []) if str(x).strip()]
    d.setdefault("description", "")
    if d.get("music_mood") not in MUSIC_MOODS:
        d["music_mood"] = "desi"
    seo = d.get("seo") if isinstance(d.get("seo"), dict) else {}
    seo.setdefault("primary_keyword", "")
    seo.setdefault("title_en", d["title"])
    seo.setdefault("title_hi", "")
    seo.setdefault("description_hook", d.get("description", ""))
    seo.setdefault("description_hi", "")
    seo["secondary_keywords"] = [str(x).strip() for x in (seo.get("secondary_keywords") or []) if str(x).strip()]
    seo.setdefault("thumbnail_text", d.get("hook_overlay", ""))
    d["seo"] = seo
    return d


_SKIP_MODEL_WORDS = ("image", "tts", "audio", "live", "embedding", "vision", "thinking-exp", "learnlm", "gemma")


def _candidate_models(client) -> list:
    """Configured models first, then every other *flash* model this API key can use
    (asked from the API itself, so retired / renamed models never break the run)."""
    models = list(GEMINI_MODELS)
    try:
        found = []
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            if "flash" not in name or any(w in name for w in _SKIP_MODEL_WORDS):
                continue
            if actions and "generateContent" not in actions:
                continue
            found.append(name)
        # newest-looking first: "latest" aliases, then higher version numbers, preview last
        found.sort(key=lambda n: ("latest" not in n, "preview" in n or "exp" in n,
                                  [-int(x) for x in re.findall(r"\d+", n)[:2]]))
        models += [n for n in found if n not in models]
    except Exception as e:
        log(f"  could not list Gemini models ({str(e)[:120]}) - using GEMINI_MODELS only")
    return models


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
    models = _candidate_models(client)
    log(f"Gemini models to try: {', '.join(models[:8])}")
    deadline = time.time() + float(os.getenv("GEMINI_MAX_WAIT_MIN", "20")) * 60
    last = None
    # Two passes over the list: a 503 "high demand" spike usually clears within minutes.
    for rnd in (1, 2):
        for model in models:
            for attempt in (1, 2, 3):
                if time.time() > deadline:
                    raise SystemExit(f"Gemini still unavailable after the wait budget, no video this run. Last: {last}")
                try:
                    log(f"Gemini: {model} (round {rnd}, attempt {attempt})")
                    resp = client.models.generate_content(model=model, contents=_prompt(recipe), config=cfg)
                    text = (resp.text or "").strip()
                    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
                    data = _validate_script(json.loads(text))
                    data["_model"] = model
                    return data
                except Exception as e:
                    last = e
                    msg = str(e)
                    log(f"  failed: {msg[:160]}")
                    if "404" in msg[:20] or "NOT_FOUND" in msg or "limit: 0" in msg:
                        break                                   # model not usable on this key -> next model
                    if "429" in msg[:20] or "RESOURCE_EXHAUSTED" in msg:
                        break                                   # quota for this model used up -> next model
                    if "503" in msg[:20] or "UNAVAILABLE" in msg or "overloaded" in msg.lower():
                        time.sleep(min(15 * attempt * rnd, 60))  # overloaded -> back off and retry
                        continue
                    time.sleep(3)                               # bad JSON etc. -> quick retry
        if rnd == 1:
            log("  all models failed once - waiting 90 s before the second round")
            time.sleep(90)
    # No generic offline script on purpose: a weak video hurts a cooking channel more than a skipped day.
    raise SystemExit(f"All Gemini models failed, no video this run. Last error: {last}")


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


_used_pixabay = set()


PIXABAY_CACHE = ROOT / "cache" / "pixabay"


def _pixabay_search(query: str):
    """Pixabay API rule: search responses must be cached for 24 h. Cached on disk
    (persisted between runs by actions/cache in the workflow)."""
    import hashlib
    PIXABAY_CACHE.mkdir(parents=True, exist_ok=True)
    f = PIXABAY_CACHE / (hashlib.sha1(query.lower().strip().encode()).hexdigest() + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < 24 * 3600:
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    r = _http_get("https://pixabay.com/api/videos/",
                  params={"key": PIXABAY_API_KEY, "q": query[:100], "safesearch": "true",
                          "video_type": "film", "per_page": 30, "order": "popular"})
    if not r or r.status_code != 200:
        if r is not None:
            log(f"  pixabay HTTP {r.status_code}: {r.text[:120]}")
        return None
    data = r.json()
    f.write_text(json.dumps(data), encoding="utf-8")
    # drop entries older than 24 h so the cache never grows unbounded
    for old in PIXABAY_CACHE.glob("*.json"):
        if time.time() - old.stat().st_mtime > 24 * 3600:
            old.unlink(missing_ok=True)
    return data


def pixabay_video(query: str, min_dur: float, dest: Path) -> bool:
    """Pixabay stock video (free key, instant signup). Most clips are landscape;
    render_scene() center-crops them to 9:16, so portrait / higher-res clips are preferred."""
    if not PIXABAY_API_KEY or DEMO:
        return False
    data = _pixabay_search(query)
    if data is None:
        return False
    hits = [h for h in data.get("hits", []) if h["id"] not in _used_pixabay]

    def best(h):
        vs = [v for v in (h.get("videos") or {}).values() if v.get("url") and v.get("width")]
        # want at least ~1080 px on the short side after the 9:16 crop; avoid 4K downloads
        vs = [v for v in vs if min(v["width"], v["height"]) >= 720 and max(v["width"], v["height"]) <= 2600]
        vs.sort(key=lambda v: (v["height"] < v["width"], abs(max(v["width"], v["height"]) - 1920)))
        return vs[0] if vs else None

    cands = [(h, best(h)) for h in hits]
    cands = [(h, v) for h, v in cands if v]
    cands.sort(key=lambda hv: (hv[1]["height"] < hv[1]["width"],      # portrait first
                               hv[0].get("duration", 0) < min_dur,     # long enough
                               random.random()))
    for h, v in cands[:6]:
        dl = _http_get(v["url"], timeout=180)
        if dl and dl.status_code == 200 and len(dl.content) > 50_000:
            dest.write_bytes(dl.content)
            _used_pixabay.add(h["id"])
            return True
    return False


_STOP = {"the", "a", "an", "and", "of", "in", "on", "with", "for", "to", "indian", "food", "recipe", "style"}
_used_clips = set()


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z]+", text.lower()) if len(t) > 2 and t not in _STOP}


def own_clip(query: str, recipe: dict, dest: Path) -> bool:
    """Your own footage: assets/clips/<keywords>.mp4 (e.g. 'onion-frying-pan.mp4', 'masala-chai-pour.mp4').
    Best match by filename keywords vs. the scene query + dish name; never reused in the same video."""
    if not CLIPS_DIR.exists():
        return False
    want = _tokens(query) | _tokens(recipe["name"])
    best, score = None, 0
    for f in CLIPS_DIR.rglob("*"):
        if f.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm") or f in _used_clips:
            continue
        sc = len(want & _tokens(f.stem.replace("-", " ").replace("_", " ")))
        if sc > score:
            best, score = f, sc
    if best:
        shutil.copy(best, dest)
        _used_clips.add(best)
        return True
    return False


def _food_prompt(prompt: str) -> str:
    return (f"{prompt}, Indian home kitchen, food photography, photorealistic, appetizing, "
            f"natural window light, shallow depth of field, vertical composition, no text, no watermark")


def _valid_image(dest: Path) -> bool:
    try:
        with Image.open(dest) as im:
            im.verify()
        with Image.open(dest) as im:
            return min(im.size) >= 512
    except Exception:
        return False


_last_pollinations = [0.0]


def pollinations_image(prompt: str, dest: Path, seed: int) -> bool:
    """Free, no signup. Anonymous use is throttled (~1 request / 15 s), so calls are spaced out;
    a free POLLINATIONS_API_KEY (enter.pollinations.ai) removes the throttle."""
    if not USE_AI_IMAGES or DEMO:
        return False
    if not POLLINATIONS_API_KEY:
        wait = 16 - (time.time() - _last_pollinations[0])
        if wait > 0:
            time.sleep(wait)
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(_food_prompt(prompt)) +
           f"?width=1080&height=1920&nologo=true&seed={seed}&model=flux")
    headers = {"User-Agent": HTTP_UA}
    if POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"
    r = _http_get(url, timeout=180, headers=headers)
    _last_pollinations[0] = time.time()
    if r and r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        dest.write_bytes(r.content)
        return _valid_image(dest)
    return False


def cloudflare_image(prompt: str, dest: Path, seed: int) -> bool:
    """Cloudflare Workers AI free daily allowance, FLUX.1 schnell. Needs CF_ACCOUNT_ID + CF_API_TOKEN."""
    if not (CF_ACCOUNT_ID and CF_API_TOKEN) or not USE_AI_IMAGES or DEMO:
        return False
    import base64
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell",
            headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
            json={"prompt": _food_prompt(prompt), "steps": 8, "seed": seed}, timeout=120)
        if r.status_code != 200:
            log(f"  cloudflare HTTP {r.status_code}: {r.text[:120]}")
            return False
        img = (r.json().get("result") or {}).get("image")
        if not img:
            return False
        dest.write_bytes(base64.b64decode(img))
        return _valid_image(dest)
    except Exception as e:
        log(f"  cloudflare failed: {e}")
        return False


_used_wiki = set()


def wikimedia_image(query: str, dest: Path) -> bool:
    """Real photos from Wikimedia Commons, no key. ONLY public-domain / CC0 files are used,
    so no attribution or share-alike obligations end up in the video."""
    if not USE_WIKIMEDIA or DEMO:
        return False
    r = _http_get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": HTTP_UA}, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 40,
        "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": 1600})
    if not r or r.status_code != 200:
        return False
    pages = (r.json().get("query") or {}).get("pages", {}).values()
    ok = []
    for pg in pages:
        ii = (pg.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName", {}).get("value", "") + " " +
               meta.get("License", {}).get("value", "")).lower()
        if not ("public domain" in lic or "cc0" in lic or lic.strip() in ("pd", "pd pd")):
            continue
        if ii.get("height", 0) < 900 or ii.get("width", 0) < 900 or pg["pageid"] in _used_wiki:
            continue
        ok.append((pg, ii))
    random.shuffle(ok)
    for pg, ii in ok[:4]:
        dl = _http_get(ii.get("thumburl") or ii["url"], timeout=120, headers={"User-Agent": HTTP_UA})
        if dl and dl.status_code == 200:
            dest.write_bytes(dl.content)
            if _valid_image(dest):
                _used_wiki.add(pg["pageid"])
                return True
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
    """Render one silent 1080x1920 clip of exactly `dur` seconds. Returns the source used.
    Sources are tried in VISUAL_ORDER; video sources get trimmed/cropped, image sources get Ken Burns."""
    vdir = WORK / "visuals"
    vdir.mkdir(parents=True, exist_ok=True)
    grade = "eq=saturation=1.12:contrast=1.04,vignette=PI/5"
    common = ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", "-t", f"{dur:.3f}"]
    q0 = scene["pexels_query"]
    queries = list(dict.fromkeys(q for q in [q0, " ".join(q0.split()[-2:]),
                                             f"{recipe['name']} indian food", "indian cooking"] if q.strip()))
    seed = abs(hash(scene["image_prompt"])) % 100000
    vid, img = vdir / f"s{i:02d}.mp4", vdir / f"s{i:02d}.jpg"

    def render_video(tag):
        sdur = ffprobe_duration(vid)
        ss = rnd_offset(sdur, dur)
        speed = 1.0 if sdur >= dur else max(sdur / dur, 0.5)   # slow down short clips a bit
        # punch-in: each cut starts 10 % zoomed and settles in 0.35 s (adds energy, keeps eyes on screen)
        vf = (f"setpts=PTS/{speed:.3f},scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},fps={FPS},{grade},"
              f"scale=w='trunc({W}*(1+0.10*max(0,1-t/0.35))/2)*2':h=-2:eval=frame,crop={W}:{H},setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={dur:.2f}")
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ss:.2f}", "-i", str(vid), "-vf", vf, *common, str(out)])
        return tag

    def render_image(tag, card=False):
        frames = max(int(dur * FPS), 1)
        z = "min(1+0.0009*on,1.15)" if i % 2 == 0 else "max(1.15-0.0009*on,1.0)"
        vf = (f"scale={int(W * 1.6)}:{int(H * 1.6)}:force_original_aspect_ratio=increase,"
              f"crop={int(W * 1.6)}:{int(H * 1.6)},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
              f"{'null' if card else grade},setsar=1")
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(img), "-vf", vf, *common, str(out)])
        return tag

    for src in VISUAL_ORDER:
        try:
            if src == "own":
                if own_clip(q0, recipe, vid):
                    return render_video("own")
            elif src in ("pexels", "pixabay"):
                fn = pexels_video if src == "pexels" else pixabay_video
                if (src == "pexels" and not PEXELS_API_KEY) or (src == "pixabay" and not PIXABAY_API_KEY):
                    continue
                for q in queries:
                    if fn(q, dur, vid):
                        return render_video(f"{src}:{q}")
            elif src == "pollinations":
                if pollinations_image(scene["image_prompt"], img, seed):
                    return render_image("ai_image")
            elif src == "cloudflare":
                if cloudflare_image(scene["image_prompt"], img, seed):
                    return render_image("ai_image")
            elif src == "wikimedia":
                for q in (q0, recipe["name"]):
                    if wikimedia_image(q, img):
                        return render_image(f"wikimedia:{q}")
        except Exception as e:
            log(f"  {src} failed for scene {i + 1}: {str(e)[:200]}")
    text_card(recipe["name"], scene.get("label") or CHANNEL_NAME, img, seed=i)
    return render_image("card", card=True)


def rnd_offset(src_dur, need):
    slack = src_dur - need - 0.2
    return random.uniform(0.2, slack) if slack > 0.4 else 0.0


# ----------------------------------------------------------------------------
# 5. SOUND (music + SFX, mixed in numpy)
# ----------------------------------------------------------------------------
_MOOD = {   # bpm, chord roots (Hz), arp/pad level, percussion style
    "lofi":    (86,  [146.83, 123.47, 98.00, 110.00], "kick"),
    "chill":   (78,  [130.81, 110.00, 87.31, 98.00],  "soft"),
    "upbeat":  (112, [146.83, 164.81, 123.47, 110.00], "kick"),
    "desi":    (100, [146.83, 130.81, 116.54, 130.81], "tabla"),
    "festive": (120, [146.83, 164.81, 146.83, 110.00], "tabla"),
}


def _tabla(kind, sr, rnd):
    """Very small physical-ish tabla: 'dha' = bayan boom + dayan ring, 'na'/'tin' = dayan ring only."""
    ln = int(0.35 * sr)
    t = np.arange(ln) / sr
    ring_f = 380 if kind == "na" else 520
    ring = 0.6 * np.sin(2 * np.pi * ring_f * t) * np.exp(-t * (18 if kind == "na" else 26))
    ring += 0.15 * rnd.standard_normal(ln) * np.exp(-t * 120)          # finger slap
    if kind == "dha":
        bend = 70 + 45 * np.exp(-t * 9)                                   # pitch-bending bayan
        ring += 0.9 * np.sin(2 * np.pi * np.cumsum(bend) / sr) * np.exp(-t * 6)
    return ring.astype(np.float32)


def synth_music(seconds: float, sr=44100, seed=None, mood="lofi") -> np.ndarray:
    """Royalty-free-by-construction loop in the scene's mood: pad chords + plucked arpeggio + percussion
    (soft kick/shaker, or a tabla theka for 'desi'/'festive')."""
    rnd = np.random.default_rng(seed)
    bpm, roots, perc = _MOOD.get(mood, _MOOD["lofi"])
    beat = 60 / bpm
    n = int(seconds * sr)
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float32)
    chords = [[1, 1.26, 1.5], [1, 1.19, 1.5], [1, 1.26, 1.5], [1, 1.26, 1.5]]
    theka = ["dha", "na", "na", "dha", "dha", "na", "tin", "na"]
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
        for k in range(8):                                   # plucked arpeggio, eighth notes
            a0 = s0 + int(k * beat / 2 * sr)
            if a0 >= n:
                break
            ln = min(int(0.5 * sr), n - a0)
            ta = np.arange(ln) / sr
            f = root * 2 * ch[[0, 1, 2, 1, 0, 2, 1, 2][k]]
            pl = np.sin(2 * np.pi * f * ta) + 0.4 * np.sin(2 * np.pi * 2 * f * ta)
            out[a0:a0 + ln] += 0.05 * np.exp(-ta * 7) * pl
            if perc == "tabla":
                hit = _tabla(theka[k], sr, rnd)
                ln2 = min(len(hit), n - a0)
                out[a0:a0 + ln2] += 0.22 * hit[:ln2]
        if perc in ("kick", "soft"):
            for k in range(4):
                k0 = s0 + int(k * beat * sr)
                if k0 >= n:
                    break
                if k % 2 == 0 or (perc == "kick" and bpm > 100):
                    ln = min(int(0.25 * sr), n - k0)
                    tk = np.arange(ln) / sr
                    amp = 0.18 if perc == "kick" else 0.09
                    out[k0:k0 + ln] += amp * np.exp(-tk * 18) * np.sin(2 * np.pi * (55 + 60 * np.exp(-tk * 30)) * tk)
                h0 = k0 + int(beat / 2 * sr)
                if h0 < n:
                    ln = min(int(0.06 * sr), n - h0)
                    out[h0:h0 + ln] += 0.025 * rnd.standard_normal(ln) * np.exp(-np.arange(ln) / sr * 60)
    out = np.convolve(out, np.ones(6) / 6, mode="same").astype(np.float32)
    return out / (np.abs(out).max() + 1e-6) * 0.8


def _most_energetic(arr: np.ndarray, need: int, sr: int) -> np.ndarray:
    """Start the track at its liveliest part (the 'drop'), not at a slow intro."""
    if len(arr) <= need + sr:
        return arr
    win = sr // 2
    rms = np.sqrt(np.convolve(arr ** 2, np.ones(win) / win, mode="valid")[::win])
    span = max(need // win, 1)
    if len(rms) <= span:
        return arr
    csum = np.concatenate([[0], np.cumsum(rms)])
    means = (csum[span:] - csum[:-span]) / span
    skip = int(len(means) * 0.08)                       # never start in the first ~8 %
    best = skip + int(np.argmax(means[skip:])) if len(means) > skip else 0
    start = max(best * win - sr // 2, 0)                # half a second of run-up
    return arr[start:]


def load_music(seconds: float, sr=44100, mood="lofi") -> tuple:
    exts = (".mp3", ".wav", ".m4a", ".ogg")
    files = []
    if MUSIC_DIR.exists():
        for folder in (MUSIC_DIR / mood, MUSIC_DIR):        # mood folder first, then the root folder
            files = sorted(p for p in folder.glob("*") if p.suffix.lower() in exts) if folder.exists() else []
            if files:
                break
        if not files:
            files = sorted(p for p in MUSIC_DIR.rglob("*") if p.suffix.lower() in exts)
    need = int(seconds * sr)
    if files:
        f = random.choice(files)
        arr = _decode_to_array(f, sr)
        if len(arr) > sr:
            arr = _most_energetic(arr, need, sr)
            reps = int(math.ceil(need / len(arr)))
            arr = np.tile(arr, reps)[:need]
            arr = arr / (np.abs(arr).max() + 1e-6) * 0.8
            return arr, f"{f.parent.name}/{f.name}"
    return synth_music(seconds, sr, mood=mood), f"synth-{mood}"


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


def mix_audio(voice: np.ndarray, sr: int, scenes: list, timing: list, dest: Path, mood="lofi") -> str:
    n = len(voice)
    music, music_name = load_music(n / sr + 1, sr, mood)
    music = music[:n]
    # duck music under the voice (envelope follower)
    env = np.convolve(np.abs(voice), np.ones(int(0.12 * sr)) / int(0.12 * sr), mode="same")
    duck = np.where(env > 0.01, 0.5, 1.0)
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
    music_name = mix_audio(voice, sr, script["scenes"], timing, audio, script.get("music_mood", "lofi"))

    log("Captions + final encode ...")
    ass = WORK / "captions.ass"
    build_ass(script, words, timing, ass)
    srt = OUT / f"{slug}.srt"
    build_srt(words, srt)
    final = OUT / f"{slug}.mp4"
    ass_arg = ass.as_posix().replace(":", r"\:")
    fonts_arg = FONT_DIR.as_posix().replace(":", r"\:")
    inputs, graph = sticker_graph(script["scenes"], timing)
    graph += f"[vs]subtitles='{ass_arg}':fontsdir='{fonts_arg}'[vout]"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(audio), *inputs,
         "-filter_complex", graph,
         "-map", "[vout]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(final)], timeout=1800)
    dur = ffprobe_duration(final)
    log(f"  done: {final.name} ({dur:.1f}s, {final.stat().st_size / 1e6:.1f} MB)")
    thumb = OUT / f"{slug}-thumbnail.jpg"
    try:
        build_thumbnail(script, recipe, clips, timing, thumb)
        log(f"  thumbnail: {thumb.name}")
    except Exception as e:
        log(f"  thumbnail skipped: {e}")
        thumb = None
    return {"video": final, "srt": srt, "duration": round(dur, 1), "sources": sources, "music": music_name,
            "thumbnail": thumb}


def sticker_graph(scenes: list, timing: list) -> tuple:
    """Animated emoji stickers: pop in with an overshoot, bob gently, alternate sides.
    Returns (extra ffmpeg inputs, filter_complex prefix ending in [vs])."""
    total = timing[-1]["start"] + timing[-1]["dur"]
    inputs, parts, last, idx = [], [], "0:v", 2
    if USE_STICKERS:
        for i, (sc, tm) in enumerate(zip(scenes, timing)):
            png = STICKER_DIR / f"{sc.get('sticker', 'none')}.png"
            if sc.get("sticker") in (None, "none") or not png.exists():
                continue
            a = tm["start"] + 0.3
            b = tm["start"] + tm["dur"] - 0.15
            if b - a < 0.6:
                continue
            size = 250 if i else 300
            # first scene: under the hook text; others: alternate top-right / top-left below the step label
            cx, cy = (540, 1130) if i == 0 else ((850, 520) if i % 2 else (230, 520))
            inputs += ["-loop", "1", "-t", f"{total:.2f}", "-i", str(png)]
            k = f"(t-{a:.2f})/0.25"
            parts.append(
                # rotate BEFORE the animated scale: rotate locks its output size on the first frame
                f"[{idx}:v]format=rgba,rotate='0.12*sin(2*PI*0.8*t)':c=none:ow=rotw(0.2):oh=roth(0.2),"
                f"scale=w='if(lt(t,{a:.2f}),2,trunc({size}*min(1,{k})*(1+0.18*sin(min(1,{k})*PI))/2)*2)'"
                f":h=-2:eval=frame[s{idx}]")
            parts.append(
                f"[{last}][s{idx}]overlay=x='{cx}-w/2':y='{cy}-h/2+14*sin(2*PI*1.1*t)':"
                f"enable='between(t,{a:.2f},{b:.2f})'[o{idx}]")
            last = f"o{idx}"
            idx += 1
    parts.append(f"[{last}]null[vs]")
    return inputs, ";".join(parts) + ";"


def _best_frame(clips: list, timing: list, dest: Path):
    """Pick the most colourful / sharp frame among the first scenes (food close-ups win)."""
    best, best_score = None, -1
    for i, (c, tm) in enumerate(list(zip(clips, timing))[:4]):
        for frac in (0.35, 0.7):
            f = WORK / f"thumbcand{i}_{int(frac * 100)}.jpg"
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{tm['dur'] * frac:.2f}", "-i", str(c),
                 "-frames:v", "1", "-q:v", "2", str(f)])
            im = Image.open(f).convert("RGB").resize((270, 480))
            a = np.asarray(im).astype(np.float32)
            sat = (a.max(axis=2) - a.min(axis=2)).mean()
            sharp = np.abs(np.diff(a.mean(axis=2), axis=1)).mean()
            score = sat + 2 * sharp
            if score > best_score:
                best, best_score = f, score
    shutil.copy(best, dest)


def build_thumbnail(script: dict, recipe: dict, clips: list, timing: list, dest: Path):
    """1080x1920 Shorts thumbnail: best food frame + huge 2-4 word text + dish name + brand."""
    base = WORK / "thumb_base.jpg"
    _best_frame(clips, timing, base)
    img = Image.open(base).convert("RGB").resize((W, H))
    img = Image.fromarray(np.clip(np.asarray(img).astype(np.float32) * 1.06 + 4, 0, 255).astype(np.uint8))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(H):   # dark gradients top + bottom so text always reads
        a = int(max(0, 150 - y * 0.35)) if y < 450 else int(max(0, (y - 1150) * 0.32))
        d.line([(0, y), (W, y)], fill=(0, 0, 0, min(a, 190)))
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    d = ImageDraw.Draw(img)
    text = (script["seo"].get("thumbnail_text") or script.get("hook_overlay") or recipe["name"]).strip()
    if CONTENT_LANG == "en" or re.fullmatch(r"[\x00-\x7F]+", text):
        text = text.upper()
    words, lines, cur = text.split(), [], ""
    size = 150
    f = _font(size)
    while True:
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) > W - 140 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
        if len(lines) <= 3 or size <= 90:
            break
        size -= 12
        f = _font(size)
    y = 1270
    for i, ln in enumerate(lines[:3]):
        fill = (255, 214, 0) if i % 2 == 0 else (255, 255, 255)
        d.text((W / 2, y), ln, font=f, fill=fill, anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
        y += int(size * 1.08)
    name_f = _font(70)
    pill = recipe["name"]
    tw = d.textlength(pill, font=name_f)
    d.rounded_rectangle((W / 2 - tw / 2 - 40, 180, W / 2 + tw / 2 + 40, 300), 60, fill=SAFFRON)
    d.text((W / 2, 240), pill, font=name_f, fill=(40, 12, 6), anchor="mm")
    d.text((W / 2, H - 120), CHANNEL_NAME, font=_font(46, False), fill=CREAM, anchor="mm",
           stroke_width=3, stroke_fill=(0, 0, 0))
    img.convert("RGB").save(dest, "JPEG", quality=88, optimize=True)
    q = 88
    while dest.stat().st_size > 1_900_000 and q > 50:      # API limit is 2 MB
        q -= 8
        img.convert("RGB").save(dest, "JPEG", quality=q, optimize=True)


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


def recent_upload_titles(yt, limit=200) -> list:
    """Titles of the channel's latest uploads (1 quota unit per 50)."""
    try:
        ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
        pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        titles, token = [], None
        while len(titles) < limit:
            r = yt.playlistItems().list(part="snippet", playlistId=pl, maxResults=50, pageToken=token).execute()
            titles += [it["snippet"]["title"] for it in r.get("items", [])]
            token = r.get("nextPageToken")
            if not token:
                break
        return titles
    except Exception as e:
        log(f"  could not read channel uploads ({str(e)[:120]}) - using upload_log.json only")
        return []


def compute_publish_at():
    if PUBLISH_AT_IST_HOUR.lower() == "off":
        return None
    now = datetime.now(IST)
    slot = now.replace(hour=int(PUBLISH_AT_IST_HOUR), minute=0, second=0, microsecond=0)
    if slot - now < timedelta(minutes=20):
        return None          # too late for today's slot -> publish immediately
    return slot.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("<", "").replace(">", "")).strip()


def _fit_title(t: str, limit=100) -> str:
    t = _clean(t)
    suffix = " #shorts"
    if "#shorts" in t.lower():
        return t[:limit]
    return (t[: limit - len(suffix)].rstrip(" |-") + suffix)


def build_metadata(script: dict, recipe: dict, sources: list, playlist_url: str = "") -> dict:
    """Full SEO: keyword-first title, keyword-rich first 2 lines, full recipe, related searches,
    <=15 hashtags (YouTube ignores ALL hashtags if there are more), <=500 chars of tags,
    and a Hindi title/description localization."""
    seo = script["seo"]
    kw = _clean(seo.get("primary_keyword") or f"{recipe['name']} recipe")
    title_en = _clean(seo.get("title_en") or script["title"])
    if kw and kw.lower() not in title_en.lower():           # search keyword must be in the title
        title_en = f"{kw.title()} | {title_en}"
    title = _fit_title(title_en)
    title_hi = _fit_title(seo["title_hi"]) if seo.get("title_hi") else ""

    tags_h = []
    for h in ["#shorts", "#" + re.sub(r"[^a-z0-9]", "", recipe["name"].lower()), "#indianfood"] + script["hashtags"]:
        h = "#" + re.sub(r"[^\w]", "", h.lstrip("#"), flags=re.U)
        if len(h) > 2 and h.lower() not in [x.lower() for x in tags_h]:
            tags_h.append(h)
    tags_h = tags_h[:12]

    names = {"pexels": "Pexels", "pixabay": "Pixabay", "wikimedia": "Wikimedia Commons (public domain)"}
    stock = sorted({names[s.split(":")[0]] for s in sources if s.split(":")[0] in names})
    related = [k for k in seo["secondary_keywords"] if k.lower() != kw.lower()][:10]

    d = [_clean(seo.get("description_hook")) or _clean(script.get("description")),
         f"Full {kw} below 👇 Save this Short and try it today!", ""]
    if seo.get("description_hi"):
        d += [_clean(seo["description_hi"]), ""]
    d += ["🛒 INGREDIENTS"] + [f"• {x}" for x in script["ingredients"]] + [""]
    d += ["👩‍🍳 METHOD"] + [f"{i}. {x}" for i, x in enumerate(script["steps"], 1)] + [""]
    if related:
        d += ["🔎 You searched for: " + " | ".join([kw] + related), ""]
    if playlist_url:
        d += [f"▶️ More {CATEGORY_PLAYLISTS.get(recipe.get('category'), 'recipes')}: {playlist_url}"]
    d += [f"🔔 Subscribe to {CHANNEL_NAME} for a new Indian recipe every day!", "Good food = Good mood! 😋", ""]
    if stock:
        d.append("Stock visuals: " + ", ".join(stock) + ".")
    if "ai_image" in sources:
        d.append("Some food visuals are AI-generated.")
    d += ["", " ".join(tags_h)]
    description = "\n".join(d).replace("<", "").replace(">", "")[:4900]

    tags, total = [], 0
    pool = ([kw, recipe["name"], f"{recipe['name']} recipe", f"{recipe['name']} recipe in hindi"] + related +
            script["tags"] + [f"how to make {recipe['name'].lower()}", "indian recipe", "indian food",
                              "recipe in hindi", "shorts", CHANNEL_NAME])
    for t in pool:
        t = _clean(t.replace("#", ""))[:60]
        cost = len(t) + (2 if " " in t else 0) + 1
        if t and t.lower() not in [x.lower() for x in tags] and total + cost <= 480:
            tags.append(t)
            total += cost

    localizations = {}
    if title_hi:
        localizations["hi"] = {"title": title_hi,
                               "description": (_clean(seo.get("description_hi")) + "\n\n" + description)[:4900]}
    return {"title": title, "description": description, "tags": tags, "localizations": localizations,
            "primary_keyword": kw}


def ensure_playlist(yt, recipe: dict) -> str:
    """Find (or create) the public playlist for this recipe's category. Returns playlist id."""
    if PLAYLIST_ID:
        return PLAYLIST_ID
    if not AUTO_PLAYLISTS:
        return ""
    name = CATEGORY_PLAYLISTS.get(recipe.get("category", ""), "Indian Recipes")
    try:
        token = None
        while True:
            r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
            for it in r.get("items", []):
                if it["snippet"]["title"].strip().lower() == name.lower():
                    return it["id"]
            token = r.get("nextPageToken")
            if not token:
                break
        pl = yt.playlists().insert(part="snippet,status", body={
            "snippet": {"title": name, "defaultLanguage": "en",
                        "description": f"{name} by {CHANNEL_NAME} - quick, easy Indian recipes as Shorts. "
                                       f"New recipe every day!"},
            "status": {"privacyStatus": "public"}}).execute()
        log(f"  created playlist: {name}")
        return pl["id"]
    except Exception as e:
        log(f"  playlist lookup skipped: {e}")
        return ""


def upload(yt, video: Path, meta: dict, synthetic: bool) -> str:
    from googleapiclient.http import MediaFileUpload
    publish_at = compute_publish_at()
    body = {
        # Title/description are written in English/Hinglish (what people type in search) -> defaultLanguage en;
        # the spoken audio is CONTENT_LANG; the Hindi title/description go in as a localization.
        "snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                    "categoryId": YOUTUBE_CATEGORY_ID, "defaultLanguage": "en",
                    "defaultAudioLanguage": CONTENT_LANG},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": synthetic, "embeddable": True},
    }
    if publish_at:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at
        log(f"Scheduled public at {publish_at} (UTC)")
    parts = "snippet,status"
    if meta.get("localizations"):
        body["localizations"] = meta["localizations"]
        parts += ",localizations"
    req = yt.videos().insert(part=parts, body=body,
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


def add_to_playlist(yt, vid, playlist_id):
    if not playlist_id:
        return
    try:
        yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        log("  added to playlist")
    except Exception as e:
        log(f"  playlist skipped: {e}")


def set_thumbnail(yt, vid, thumb):
    """Shorts accept API thumbnails only after YouTube has processed the video -> wait for it first.
    Needs a phone-verified channel (youtube.com/verify)."""
    if not (SET_THUMBNAIL and thumb and Path(thumb).exists()):
        return
    from googleapiclient.http import MediaFileUpload
    for _ in range(24):                                     # up to ~8 min
        try:
            it = yt.videos().list(part="processingDetails", id=vid).execute().get("items", [])
            st = it[0]["processingDetails"].get("processingStatus") if it else ""
            if st in ("succeeded", "terminated", "failed"):
                break
        except Exception:
            pass
        time.sleep(20)
    for attempt in (1, 2, 3):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg")).execute()
            log("  thumbnail set")
            return
        except Exception as e:
            msg = str(e)
            if "403" in msg[:30] or "forbidden" in msg.lower():
                log("  thumbnail not allowed - verify the channel by phone at https://www.youtube.com/verify "
                    "(custom thumbnails need it). Video is fine.")
                return
            log(f"  thumbnail retry {attempt}: {msg[:150]}")
            time.sleep(30)


def comment_text(script, recipe) -> str:
    ing = ", ".join(script["ingredients"][:8])
    return (f"📌 {recipe['name']} ingredients: {ing}\n\n"
            f"Aapko kaunsi recipe next chahiye? Comment karo! 👇\nWhich recipe should we make next? 😋")[:9000]


def _post_comment(yt, vid, text) -> bool:
    try:
        yt.commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": vid, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
        return True
    except Exception as e:
        log(f"  comment on {vid} not posted yet: {str(e)[:120]}")
        return False


def post_pending_comments(yt):
    """YouTube refuses comments on private/scheduled videos, so the recipe comment is posted on a LATER run,
    once that Short is public. Pin it once in YouTube Studio if you like (the API cannot pin)."""
    if not POST_FIRST_COMMENT:
        return
    logs = load_log()
    changed = False
    for e in logs[-7:]:
        if e.get("test_mode") or not e.get("video_id") or e.get("comment_posted") or not e.get("comment_text"):
            continue
        try:
            it = yt.videos().list(part="status", id=e["video_id"]).execute().get("items", [])
        except Exception:
            continue
        if not it or it[0]["status"].get("privacyStatus") != "public":
            continue
        if _post_comment(yt, e["video_id"], e["comment_text"]):
            e["comment_posted"] = True
            changed = True
            log(f"  recipe comment posted on {e['video_id']}")
    if changed:
        LOG_FILE.write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    log(f"{CHANNEL_NAME} Shorts bot v{VERSION} | lang={CONTENT_LANG} voice={TTS_VOICE} "
        f"| test={TEST_MODE} demo={DEMO}")
    if not FONT_BOLD.exists():
        raise SystemExit(f"Missing font {FONT_BOLD}")
    yt, titles = None, []
    if not TEST_MODE:
        yt = youtube_service()
        channel_guard(yt)              # fail BEFORE spending time on a video for the wrong channel
        titles = recent_upload_titles(yt)
        post_pending_comments(yt)      # yesterday's Short is public now -> its recipe comment goes up
    recipe = pick_recipe(titles)
    log(f"Recipe: {recipe['name']}" + (f" ({recipe['twist']})" if recipe.get("twist") else ""))

    script = generate_script(recipe)
    log(f"Title: {script['title']}  ({len(script['scenes'])} scenes, model={script.get('_model', 'demo')})")
    slug = datetime.now(IST).strftime("%Y-%m-%d") + "-" + re.sub(r"[^a-z0-9]+", "-", recipe["name"].lower()).strip("-")
    (OUT).mkdir(exist_ok=True)
    (OUT / f"{slug}.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    res = build_video(script, recipe, slug)
    playlist_id = ensure_playlist(yt, recipe) if yt else ""
    pl_url = f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id else ""
    meta = build_metadata(script, recipe, res["sources"], pl_url)
    title = meta["title"]
    (OUT / f"{slug}-seo.txt").write_text(
        f"TITLE: {title}\nHINDI TITLE: {meta['localizations'].get('hi', {}).get('title', '-')}\n"
        f"PRIMARY KEYWORD: {meta['primary_keyword']}\n\n{meta['description']}\n\n"
        f"TAGS ({sum(len(t) for t in meta['tags'])} chars): {', '.join(meta['tags'])}", encoding="utf-8")

    entry = {"date": datetime.now(IST).date().isoformat(), "recipe": recipe["name"], "title": title,
             "duration": res["duration"], "visuals": res["sources"], "music": res["music"],
             "voice": TTS_VOICE, "lang": CONTENT_LANG, "model": script.get("_model"),
             "music_mood": script.get("music_mood"), "primary_keyword": meta["primary_keyword"],
             "test_mode": TEST_MODE, "bot_version": VERSION}
    if TEST_MODE:
        log("TEST MODE: not uploading. Files are in output/.")
        if not DEMO:
            save_log_entry(entry)
        return

    synthetic = "ai_image" in res["sources"]
    vid = upload(yt, res["video"], meta, synthetic)
    log(f"Uploaded: https://youtube.com/shorts/{vid}")
    upload_captions(yt, vid, res["srt"])
    add_to_playlist(yt, vid, playlist_id)
    set_thumbnail(yt, vid, res.get("thumbnail"))
    entry["video_id"] = vid
    entry["comment_text"] = comment_text(script, recipe)
    if not compute_publish_at():                       # already public -> comment right away
        entry["comment_posted"] = _post_comment(yt, vid, entry["comment_text"])
    save_log_entry(entry)


DEMO_SCRIPT = {
    "title": "Street Style Masala Chai in 5 Minutes",
    "hook_overlay": "Tapri wali chai ka secret",
    "scenes": [
        {"say": "Tapri jaisi kadak masala chai ka asli secret aaj bata rahi hoon.", "label": "", "sticker": "drool", "sfx": "none",
         "pexels_query": "masala chai cup", "image_prompt": "masala chai in glass"},
        {"say": "Ek pan mein dedh cup paani daalo aur medium flame par garam karo.", "label": "Step 1: Paani",
         "sticker": "tea", "sfx": "pour", "pexels_query": "pouring water pan", "image_prompt": "water in steel pan"},
        {"say": "Adrak ko kootkar daalo, saath mein do elaichi aur ek chhota tukda dalchini.",
         "label": "Step 2: Masala", "sticker": "chef", "sfx": "chop", "pexels_query": "crushing ginger mortar",
         "image_prompt": "crushed ginger cardamom"},
        {"say": "Do chammach chai patti daalo aur do minute tak achhe se ubaalo.", "label": "Step 3: Patti",
         "sticker": "fire", "sfx": "sizzle", "pexels_query": "boiling tea pot", "image_prompt": "boiling tea leaves"},
        {"say": "Pro tip: doodh daalne se pehle chai ko gehra rang lene do, tabhi kadak banegi.",
         "label": "Pro Tip", "sticker": "sparkles", "sfx": "none", "pexels_query": "dark tea boiling",
         "image_prompt": "dark tea decoction"},
        {"say": "Ab ek cup doodh aur swaad anusaar cheeni daalo, teen baar ubaal aane do.",
         "label": "Step 4: Doodh", "sticker": "heart_eyes", "sfx": "pour", "pexels_query": "pouring milk tea",
         "image_prompt": "milk pouring into tea"},
        {"say": "Chhaan kar garam garam parle-g ke saath serve karo. Roz nayi recipe ke liye follow karo!",
         "label": "Serve hot", "sticker": "bell", "sfx": "none", "pexels_query": "tea biscuits",
         "image_prompt": "chai with biscuits"},
    ],
    "ingredients": ["1.5 cup water", "1 cup milk", "2 tsp tea leaves", "1 inch ginger", "2 cardamom",
                    "small cinnamon stick", "sugar to taste"],
    "steps": ["Boil water", "Add crushed ginger and spices", "Add tea leaves, boil 2 min",
              "Add milk and sugar, boil 3 times", "Strain and serve"],
    "description": "Kadak tapri style masala chai at home in 5 minutes.",
    "tags": ["masala chai", "chai recipe", "tapri chai", "indian tea"],
    "hashtags": ["#shorts", "#masalachai", "#indianfood", "#chai"],
    "music_mood": "desi",
    "seo": {"primary_keyword": "masala chai recipe",
            "title_en": "Masala Chai Recipe | Tapri Style Kadak Chai in 5 Min",
            "title_hi": "मसाला चाय रेसिपी | टपरी जैसी कड़क चाय 5 मिनट में",
            "description_hook": "Easy masala chai recipe at home - tapri style kadak adrak wali chai in just 5 minutes.",
            "description_hi": "घर पर टपरी जैसी कड़क मसाला चाय बनाने का आसान तरीका।",
            "secondary_keywords": ["chai kaise banaye", "adrak wali chai", "tapri chai", "indian tea recipe",
                                   "kadak chai", "masala tea"],
            "thumbnail_text": "टपरी वाली कड़क चाय"},
}

if __name__ == "__main__":
    main()
