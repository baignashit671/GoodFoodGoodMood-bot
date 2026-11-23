# Daily Hindi food-science Shorts (3D)

A daily Claude scheduled task makes one Hindi "food science" Short (why / what-happens-if / myth-vs-fact about food,
in the Deep Dive 3D style of the faceless-shorts skill) and pushes it to a branch `cook/<date>-<slug>`.
`.github/workflows/publish-foodscience.yml` uploads it to **@GoodFoodGoodMoodRecipies** with the repo's existing
`GOOGLE_CREDENTIALS` secret (no new secret needed), logs it here and deletes the branch.

The old recipe bot (`cooking_shorts_bot.py`, `daily_shorts.yml`) is switched off; it only runs if started by hand.

| path | what |
|---|---|
| `_published.md` | topic log (written by the workflow; never repeat a topic) |
| `results/<name>.json` | YouTube link of every upload |
| `stats/latest.json` | channel numbers + views/hour of every Short on the channel (refreshed twice a day by `channel-stats.yml`) |
| `SCHEDULED_TASK_PROMPT.md` | the exact prompt the daily Claude scheduled task runs |
| `kit/apply.sh` | turns a fresh faceless-shorts project into a Hindi one: Devanagari captions (Hind font, SIL OFL), Hindi Kokoro voice (hm_omega), Devanagari-safe word timing, no fade-in |
| `kit/beats.py` | original royalty-free "trending-style" music beds: desi-lofi, chill-lofi, phonk, bollywood-pop, suspense-pluck |
| `kit/food.js` | 3D food props: onion, chili, tomato, kadai, tawa, plate, bowl, knife, glass, cup, spoon, steam, chopped pieces |
| `../scripts/` | `upload_youtube.py` (channel-guarded upload), `channel_stats.py`, `align.py` |

## Why no copyrighted "trending sounds"
Trending songs are copyrighted: an automatic upload with them gets claimed, muted or blocked, and the YouTube API
can't attach the in-app Shorts sounds. The beds in `kit/beats.py` copy the *style* of what trends with original music
made in code, so every upload is safe and monetisable. To add a real trending sound, open the video in the YouTube app.

## If uploads fail with invalid_grant
The token expired or was revoked: run `python reauth_youtube.py client_secret_XXXX.json` on your PC, sign in with the
cooking channel's account, and paste the printed JSON into the `GOOGLE_CREDENTIALS` secret.
