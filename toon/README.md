# Desi Toon Shorts (AI comic-illustration recipe Shorts)

The look of the viral Indian "cartoon explainer" Reels: 2D webtoon-style AI illustrations with bold ink outlines, a cream
title banner with a red rim, a flip-clock step counter (1, 2, 3...), Hindi voice, Roman Hinglish word-synced captions,
Ken Burns motion on every shot and an original music bed. Host: Didi drawn as a 2D cartoon (same identity as the 3D Didi).

**How it runs.** The daily Claude scheduled task writes only the script (`job.json`) and pushes a branch
`toon/<YYYY-MM-DD>-<slug>` made from `main` that adds `toon_job/job.json`. `.github/workflows/publish-toon.yml` then does
everything heavy on GitHub's free runner: images from Pollinations (Flux, free, no key: 1 image every ~45 s, so ~6-10 min for a Short) → edge-tts Hindi voice
(`hi-IN-SwaraNeural`) → captions → banner/counter → music (`foodscience/kit/beats.py`) → MP4 (`toon/build.py`) → upload with
`scripts/upload_youtube.py` (guarded to the cooking channel) → `toon/results/<name>.json` + a line in
`foodscience/_published.md` (shared topic log) → deletes the branch. The MP4 and a review contact sheet are also kept as a
run artifact for 7 days. `"dry_run": true` in job.json builds without uploading.

Optional secrets: `POLLINATIONS_API_KEY` (free at enter.pollinations.ai; removes the ~15 s throttle and watermark risk),
`CF_ACCOUNT_ID` + `CF_API_TOKEN` (Cloudflare Workers AI Flux fallback). None are required.

## job.json
See `example_job.json` (masala chai). Rules:
- `character`: Didi's fixed character sheet, pasted into every prompt of a scene with `"didi": true`. Never change it.
- `style`: fixed art-style suffix (keep the one in the example).
- One scene = one line = one cut (1.5-3 s). `say` = Devanagari Hindi; `caps` = the same words in Roman Hinglish, exactly one
  caption word per spoken word, chunks of 1-3 words split with `|`, one `*YELLOW` word per chunk.
- `image`: what we see, concrete (subject, action, framing: close-up / top-down / wide). Never ask for text in the image.
- `banner`: the top plaque (dish name, ingredient + quantity, "3 MINUTE"); `step`: the counter digit (omit = no counter).
- `move`: zoom_in / zoom_out / pan_left / pan_right / pan_up / pan_down.
- `metadata`: title, description, tags, category_id "26", privacy, language "hi", topic, style "desi-toon", music.

Local test without network: `python toon/build.py toon/example_job.json /tmp/out --demo`.
