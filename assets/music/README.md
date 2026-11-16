# Background music (optional)

Gemini picks a mood for every recipe: `upbeat`, `desi`, `lofi`, `festive`, `chill`.
Put royalty-free tracks in matching sub-folders (any of them can be empty):

    assets/music/desi/      tabla, sitar, Indian acoustic
    assets/music/upbeat/    happy pop / funk
    assets/music/lofi/      chill lo-fi beats
    assets/music/festive/   dhol, bhangra, celebration
    assets/music/chill/     soft acoustic

The bot picks a track from the mood folder (else from this folder, else any sub-folder), starts it at its
most energetic part (skipping slow intros), loops/trims it and ducks it under the voice.

Safe sources: YouTube Studio -> Audio Library (filter "Attribution not required"), Pixabay Music.
Do NOT add downloaded film/trending songs: music added outside YouTube's Shorts editor gets standard
Content ID claims (revenue to the label, or the Short gets blocked).

No files at all? The bot uses its built-in synthesized loops (tabla theka for desi/festive, lo-fi for the rest).
