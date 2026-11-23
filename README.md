# GoodFoodGoodMood — Daily Indian Cooking Shorts Bot

> **Nov 2026 update:** the daily recipe bot below is switched OFF (manual runs only). The channel now gets one
> Hindi recipe Short a day ("Didi ki Recipe", 3D, female host) from a Claude scheduled task: see [`foodscience/README.md`](foodscience/README.md).


Fully automatic daily YouTube Short for **[@GoodFoodGoodMoodRecipies](https://www.youtube.com/@GoodFoodGoodMoodRecipies)**,
built and uploaded by GitHub Actions. Same idea as `devops-genius-zone-bot`, rebuilt for vertical cooking Shorts.

## What every Short contains

| Part | How |
|---|---|
| Recipe | Next dish from `recipes.yaml` (195 Indian recipes queued, no repeats) |
| Script | Gemini writes hook → 5-7 steps with real quantities → pro tip → serve + CTA (JSON) |
| Voice | Free Microsoft neural voice via edge-tts — `hi-IN-SwaraNeural` (Hindi) or `en-IN-NeerjaExpressiveNeural` |
| Visuals | Per scene, first that works: **your own clips** (`assets/clips/`) → Pexels / **Pixabay** stock video → free AI food photo (**Pollinations**, optional **Cloudflare Workers AI**) → public-domain photo (**Wikimedia Commons**, CC0/PD only) → branded card |
| Sound | Background music (your tracks in `assets/music/` or built-in lo-fi loop), auto-ducked under the voice + sizzle / chop / pour / whoosh SFX |
| Captions | Word-by-word highlighted captions burned in (Hind font, Hindi + English), step label pill, big hook text; the same captions uploaded as a YouTube caption track |
| Thumbnail | Best (most colourful/sharp) food frame + huge 2-4 word text + dish pill, set via API after processing (channel must be phone-verified: youtube.com/verify) |
| Animation | Animated emoji stickers (pop + bob + tilt), punch-in zoom on every cut, loop-friendly last line for rewatches |
| Music | Mood per recipe (`upbeat / desi / lofi / festive / chill`) picked by Gemini; your tracks from `assets/music/<mood>/`, started at their most energetic part; built-in tabla/lo-fi loops as fallback |
| SEO | Keyword-first English title + Hindi title localization, keyword-rich first 2 lines, full recipe, "you searched for" phrases, ≤12 hashtags, ≤500-char tags, auto category playlist, first comment, captions track |
| Upload | Category Howto & Style, audio language Hindi, scheduled public at **7 PM IST**, channel guard |

Format: 1080×1920, 30 fps, ~40–58 s, loudness-normalised to -14 LUFS.

## Setup (one time, ~20 min)

### 1. Create the repo
New GitHub repo (e.g. `goodfood-shorts-bot`) → upload **all** files from this folder, keeping the
structure (`.github/workflows/`, `assets/fonts/`, `assets/music/`).
Hidden folder tip for the web UI: drag the whole unzipped folder into "Upload files" — `.github` comes along.

### 2. API keys (all free)
| Secret name | Where to get it |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey — the same key as the DevOps bot works |
| `PIXABAY_API_KEY` | Free account at pixabay.com → open https://pixabay.com/api/docs/ while logged in → copy the key shown under `key` |
| `PEXELS_API_KEY` *(optional)* | Only if you already have one — Pexels has paused new API keys |
| `GOOGLE_CREDENTIALS` | Step 3 below |
| `POLLINATIONS_API_KEY` *(optional)* | Free at https://enter.pollinations.ai — removes the anonymous throttle/watermark |
| `CF_ACCOUNT_ID` + `CF_API_TOKEN` *(optional)* | Free Cloudflare account → Workers AI → API token with *Workers AI* permission; daily free FLUX images |
| `COOKING_PLAYLIST_ID` *(optional)* | Playlist ID (`PL...`) to auto-add every Short to |

Repo → **Settings → Secrets and variables → Actions → New repository secret**.

### 3. YouTube token for the cooking channel
On your Windows PC:
```bat
pip install google-auth-oauthlib
python reauth_youtube.py C:\path\to\client_secret_XXXX.json
```
* You can reuse the **same** OAuth client (`client_secret_*.json`) as the DevOps bot.
* In the browser choose the **GoodFoodGoodMood** channel (not DevOps Genius Zone / personal) and tick every permission.
* Paste the printed JSON into the `GOOGLE_CREDENTIALS` secret.
* The bot checks the channel handle before every upload and stops if it's the wrong channel.
* If the OAuth consent screen is still in **Testing**, refresh tokens expire after 7 days — publish the app (In production) like the DevOps one.

### 4. First run (test)
Actions → **Daily Cooking Short** → Run workflow → `test_mode = true` → download the MP4 from the run's
**Artifacts** and watch it. Happy? Run once with `test_mode = false`, then let the daily cron take over.

## Daily schedule
* Job runs ~09:53 IST (backup ~13:43 IST; skipped automatically if the day's Short already exists).
* Video is uploaded as private + `publishAt` → goes public at **19:00 IST**.
  Change with `PUBLISH_AT_IST_HOUR` in the workflow (`off` = publish immediately).

## Customising
| Want | Change |
|---|---|
| English instead of Hindi | workflow input `lang = en` or set `CONTENT_LANG: "en"` |
| Male Hindi voice | `TTS_VOICE: "hi-IN-MadhurNeural"` in the workflow env |
| Your own music | drop `.mp3` files into `assets/music/` |
| Your own footage | drop clips named by keywords into `assets/clips/` (e.g. `onion-frying-pan.mp4`) — used first |
| Change visual priority | `VISUAL_ORDER` in the workflow (e.g. `own,pixabay,wikimedia,pollinations`) |
| Different dish order | edit `recipes.yaml` (top = next) |
| One specific dish today | Run workflow → `recipe = Pav Bhaji` |
| No AI images (stock footage only) | `USE_AI_IMAGES: "false"` |

## Files
```
cooking_shorts_bot.py          the bot
recipes.yaml                   recipe queue
upload_log.json                what was uploaded - created & committed by the workflow. NEVER overwrite it
                               when you upload new bot files (zips don't contain it on purpose)
reauth_youtube.py              one-time YouTube token (run on your PC)
assets/fonts/Hind-*.ttf        Devanagari + Latin caption font (SIL OFL)
assets/music/                  optional background tracks
assets/clips/                  optional own cooking clips (used first)
.github/workflows/daily_shorts.yml
```

Local smoke test without any keys: `python cooking_shorts_bot.py --demo` (needs FFmpeg) → `output/`.
