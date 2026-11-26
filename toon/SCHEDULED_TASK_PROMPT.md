# Daily Desi Toon Recipe Short — scheduled task prompt
Schedule: daily 19:41 IST (`CRON_TZ=Asia/Kolkata 41 19 * * *`). Paste everything below the line as the task prompt.

---
Make and publish today's "Desi Toon" Hindi RECIPE YouTube Short for the GoodFoodGoodMood cooking channel (@GoodFoodGoodMoodRecipies). Style: the viral Indian cartoon-explainer Reel look — 2D comic/webtoon AI illustrations, a cream title banner with a red rim at the top, a flip-clock step counter (1, 2, 3…), Hindi voice, Roman Hinglish word-synced captions, Ken Burns motion. Host: Didi drawn as a 2D cartoon. This is an unattended scheduled run: NEVER ask the user anything; decide everything yourself. Do the steps in order. If a step fails and you can't fix it, stop, do NOT publish, and report (step 7). You only write the script; GitHub Actions makes the images, voice and video.

## Fixed facts (validated 2026-11-26, do not re-discover)
- Repo: baignashit671/GoodFoodGoodMood-bot. If an add_repo tool exists, attach it (owner "baignashit671", repo "GoodFoodGoodMood-bot", access "push"). If already checked out in the working directory use that; otherwise `git clone --depth 1 https://github.com/baignashit671/GoodFoodGoodMood-bot ~/gfgm` (10-min timeout). Call it REPO. `git fetch -q --depth=20 origin main && git checkout -q -B main origin/main` before reading.
- READ IN FULL: REPO/toon/README.md (pipeline + job.json rules) and REPO/toon/example_job.json (a complete, working job: copy its structure, "character", voice, rate). REPO/toon/build.py is the builder (don't change it in this task).
- Pipeline (two phases, one branch `toon/<name>`): (1) push the branch with `toon_job/job.json` → workflow `publish-toon.yml` generates images (free Pollinations Flux, ~1 image / 45 s, so 8-25 min), voice, captions, music, renders, and commits `toon_build/` (MP4, metadata.json, probe.txt, review/sheet.jpg, review/sNN_*.jpg one frame per scene) + `toon_job/images/NN.jpg` back to the branch. Nothing is uploaded. (2) after review, push an empty `toon_job/APPROVED` → the workflow uploads to the cooking channel (guarded, existing GOOGLE_CREDENTIALS secret), writes `toon/results/<name>.json` (with "url") and the line in `foodscience/_published.md` on main, and deletes the branch.
- GitHub from this workspace: pushing toon/* branches works (`git -c push.negotiate=true push`); never push to main. Run status via REST only: `gh api "repos/baignashit671/GoodFoodGoodMood-bot/actions/runs?branch=toon/<name>"`; logs `gh api repos/baignashit671/GoodFoodGoodMood-bot/actions/jobs/<job_id>/logs`. Artifact downloads and GraphQL are blocked; read the build by fetching the branch: `git fetch -q --depth=2 origin toon/<name> && git checkout -q -B review FETCH_HEAD`.
- Shared topic log with the daily 3D Didi Short: foodscience/_published.md (never repeat a dish in it); also skip dishes in REPO/upload_log.json ("recipe"). foodscience/stats/latest.json has views/hour of every Short on the channel.

## 1. Pick the dish
First dish in REPO/recipes.yaml not in upload_log.json and not in foodscience/_published.md. If stats clearly favour a category or a festival this week makes a queued dish timely (web-search), pick that and say why. Verify real quantities/times for 2-3 servings with 2+ reliable recipe sources.

## 2. Write toon_job/job.json
Follow toon/README.md. 25-45 s total (about 70-120 Hindi words), 9-14 scenes, one line per scene (1.5-3.5 s each).
- Structure: HOOK (scene 1: the most mouth-watering finished dish with Didi, hook line ≤ 8 words, banner = dish name, no step) → INGREDIENTS (1-2 scenes, top-down flat lay, banner like "5 CHEEZEIN") → STEPS (one scene per step: banner = the action + quantity/time in Roman caps, e.g. "2 TBSP TEL", "5 MINUTE", and "step": "1".."N") → SERVE + CTA ("aisi recipes ke liye subscribe karo!", last line loops to the hook).
- "say": warm, simple everyday Hindi in Devanagari, like an elder sister; numbers as words. "caps": the same words in Roman Hinglish, EXACTLY one caption word per spoken word, chunks of 1-3 words split with |, one *YELLOW word per chunk.
- "image" (the most important part — images come from a free model that follows simple prompts best): ONE concrete picture per scene, subject first, under 30 words: who/what + one action + framing (close-up / top-down / medium shot) + setting ("in a cosy Indian home kitchen"). Name the exact utensils and food colours (steel kadai, tawa, pressure cooker, golden-brown parathas…). Set "didi": true only when Didi is in the shot (her character sheet from example_job.json is added automatically; copy "character" unchanged). Never ask for text, and never describe her clothes yourself. Food-only close-ups are often the best shots.
- "move": vary zoom_in / pan_left / zoom_out / pan_up / pan_right / pan_down, never the same twice in a row.
- "music": a beats preset (desi-lofi homely/breakfast, chill-lofi calm, phonk spicy/street food, bollywood-pop sweets/festive); web-search what audio style trends on Indian recipe Reels this week. "seed": any integer.
- "metadata": title in Roman Hinglish "<Dish> Recipe | <hook> #shorts" (≤ 60 chars); description: hook line with "<dish> recipe", "Ingredients:" with quantities, "Method:" numbered short steps, "Roz ek nayi recipe ke liye Subscribe karein!", then #shorts #recipe #indianfood + 1-2 dish hashtags; 10-12 tags; "category_id": "26", "privacy": "public", "language": "hi", "topic": "<Dish> recipe", "style": "desi-toon", "music": the preset.
- Check: valid JSON; every scene has say/caps/image; caption-word count == spoken-word count per scene.

## 3. Build
name = `<YYYY-MM-DD>-<slug>`. In REPO: `git checkout -B toon/<name> origin/main`, write toon_job/job.json, commit only toon_job/, `git -c push.negotiate=true push -u origin toon/<name>`. Poll every 60-120 s (up to 60 min) with REST until the run is completed; on failure read the job log, fix job.json if it's the cause and push again (max 2 times), else report.

## 4. Review (never publish a frame you haven't looked at)
Fetch the branch. Read toon_build/probe.txt (1080x1920, audio, 20-58 s) and LOOK at review/sheet.jpg and EVERY review/sNN_*.jpg. A scene FAILS if: the picture doesn't show what the line says (wrong food/action); it is photo-realistic instead of a cartoon; Didi is not in a saree (pink expected; other saree colours acceptable; a dress/top/sleeveless/western outfit is not) or looks indecent; deformed hands/faces that stand out; any text/letters/watermark in the image; the banner, counter or caption covers a face. To fix: delete toon_job/images/NN.jpg for each failing scene (NN = scene number − 1, two digits), rewrite that scene's "image" prompt (simpler; or a food-only close-up without Didi) and change "seed", delete toon_build/, commit and push → only those images are re-made. Up to 3 review rounds. If after 3 rounds it is still not good, do NOT publish: report what was wrong.

## 5. Publish
When every frame passes: `touch toon_job/APPROVED`, commit, push. Poll every 60 s (up to 20 min) for `git fetch -q --depth=5 origin main && git show origin/main:toon/results/<name>.json` → its "url". If the upload step fails with invalid_grant/missing secret, report that the user must run reauth_youtube.py and update GOOGLE_CREDENTIALS.

## 6. Log
Nothing to do: the workflow appended the line to foodscience/_published.md. Confirm it.

## 7. Report
SendUserMessage in simple Hinglish: dish, title, YouTube link, music preset and why, how many scenes needed re-rolls and why, and the stats takeaway. On failure: which step and why, and that nothing was published. Also a PushNotification with title + link (or the failure).
