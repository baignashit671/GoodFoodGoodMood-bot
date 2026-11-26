"""Desi Toon Short builder: AI comic-illustration scenes (free Pollinations / Flux) + Hindi edge-tts voice +
Roman Hinglish word-synced captions + a cream title banner with a flip-clock step counter + Ken Burns motion
+ original music bed. Runs in GitHub Actions (.github/workflows/publish-toon.yml).

  python toon/build.py <job.json> <out_dir> [--demo]

job.json (written by the daily Claude scheduled task, see toon/README.md):
{
  "slug": "aloo-paratha",
  "voice": "hi-IN-SwaraNeural", "rate": "+10%",
  "music": "desi-lofi",
  "character": "<fixed character sheet, pasted into every image prompt that shows her>",
  "style": "<fixed art-style suffix>",
  "scenes": [
    {"say": "<Devanagari Hindi line>", "caps": "Roman *HINGLISH | words *HERE",
     "image": "<what we see>", "didi": true,
     "banner": "ALOO PARATHA", "step": "1", "move": "zoom_in"}
  ],
  "metadata": {"title": ..., "description": ..., "tags": [...], "category_id": "26", "privacy": "public",
               "language": "hi", "topic": ..., "style": "desi-toon", "music": ...},
  "dry_run": false
}
caps: one caption word per spoken word, split into chunks with "|"; *word = the yellow word of that chunk.
move: zoom_in | zoom_out | pan_left | pan_right | pan_up | pan_down (default alternates).
"""
import argparse, asyncio, json, math, os, random, shutil, subprocess, sys, time, urllib.parse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
SR = 44100
GAP = 0.12                      # silence between lines (one cut per line)
ROOT = Path(__file__).resolve().parent.parent
FONT = str(ROOT / "foodscience/kit/fonts/Hind-Bold.ttf")
BEATS = ROOT / "foodscience/kit/beats.py"
CAP_Y = 1400                    # caption centre (caption zone 1250-1550)
BANNER_Y = 150                  # banner top (below the Shorts top UI)

DEFAULT_STYLE = ("2D digital comic illustration, Indian webtoon style, clean bold black ink outlines, soft cel shading, "
                 "warm golden afternoon light, rich saturated colours, detailed Indian background, expressive faces, "
                 "cinematic composition, vertical 9:16 frame, no text, no letters, no watermark, no logo")
NEG = "text, letters, words, caption, watermark, logo, signature, extra fingers, deformed hands, blurry, photo, 3d render"


def log(*a):
    print("[toon]", *a, flush=True)


# ── voice ──────────────────────────────────────────────────────────────────────
async def _tts(text, voice, rate, mp3):
    import edge_tts
    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append((s, s + ch["duration"] / 1e7))
    return words


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def voice_lines(job, work, demo):
    voice, rate = job.get("voice", "hi-IN-SwaraNeural"), job.get("rate", "+8%")
    out = []
    for i, sc in enumerate(job["scenes"]):
        mp3 = work / f"v{i:02d}.mp3"
        if demo:
            n = len(sc["say"].split()); d = 0.33 * n + 0.2
            t = np.arange(int(d * SR)) / SR
            arr = (0.12 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32)
            bounds = []
        else:
            for v in (voice, "hi-IN-SwaraNeural", "hi-IN-MadhurNeural"):
                try:
                    bounds = asyncio.run(_tts(sc["say"], v, rate, mp3))
                    if mp3.exists() and mp3.stat().st_size > 1000:
                        break
                except Exception as e:
                    log("tts", v, "failed:", e); time.sleep(3)
            else:
                sys.exit("edge-tts failed for every voice")
            arr = decode(mp3)
        out.append((arr, bounds))
    return out


# ── captions ───────────────────────────────────────────────────────────────────
def parse_caps(caps):
    """'Kadhai mein *DO | chammach *TEL' -> [[('Kadhai',0),('mein',0),('DO',1)], [...]]"""
    chunks = []
    for c in caps.split("|"):
        ws = [(w[1:], 1) if w.startswith("*") else (w, 0) for w in c.split()]
        if ws:
            chunks.append(ws)
    return chunks


def time_chunks(chunks, bounds, dur, spoken_n):
    """Start/end of every chunk on the line's own clock. Word index -> edge-tts boundary when counts match,
    else spread by character weight."""
    n = sum(len(c) for c in chunks)
    if bounds and len(bounds) == n:
        starts = [b[0] for b in bounds]
    else:
        flat = [w for c in chunks for w, _ in c]
        wt = [len(w) + 2 for w in flat]; tot = sum(wt) or 1
        usable = max(dur - 0.1, 0.2); t = 0.03; starts = []
        for x in wt:
            starts.append(t); t += usable * x / tot
    res, k = [], 0
    for c in chunks:
        res.append(starts[k]); k += len(c)
    ends = res[1:] + [dur]
    return list(zip(res, ends))


# ── images ─────────────────────────────────────────────────────────────────────
def scene_prompt(job, sc):
    parts = [sc["image"]]
    if sc.get("didi", False) and job.get("character"):
        parts.append(job["character"])
    parts.append(job.get("style") or DEFAULT_STYLE)
    return ", ".join(parts)


def valid(p):
    try:
        with Image.open(p) as im:
            return im.size[0] >= 512 and im.size[1] >= 512
    except Exception:
        return False


def pollinations(prompt, dest, seed, key):
    import requests
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) +
           f"?width=1080&height=1920&seed={seed}&model=flux&nologo=true&enhance=false&negative_prompt=" + urllib.parse.quote(NEG))
    hdr = {"User-Agent": "GoodFoodGoodMood-toon/1.0"}
    if key:
        hdr["Authorization"] = f"Bearer {key}"
    try:
        r = requests.get(url, headers=hdr, timeout=240)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            dest.write_bytes(r.content)
            return valid(dest)
        log("pollinations", r.status_code, r.text[:200])
        import re
        m = re.search(r"[Rr]etry after (\d+)\s*s", r.text)
        if m: time.sleep(int(m.group(1)) + 3)
    except Exception as e:
        log("pollinations error", e)
    return False


def cloudflare(prompt, dest, seed):
    acc, tok = os.getenv("CF_ACCOUNT_ID", ""), os.getenv("CF_API_TOKEN", "")
    if not (acc and tok):
        return False
    import base64, requests
    try:
        r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                          headers={"Authorization": f"Bearer {tok}"}, json={"prompt": prompt[:2000], "steps": 8, "seed": seed}, timeout=120)
        img = r.json().get("result", {}).get("image")
        if img:
            dest.write_bytes(base64.b64decode(img)); return valid(dest)
    except Exception as e:
        log("cloudflare error", e)
    return False


def demo_image(i, dest):
    rnd = random.Random(i)
    im = Image.new("RGB", (W, H), tuple(rnd.randint(80, 200) for _ in range(3)))
    d = ImageDraw.Draw(im)
    for _ in range(30):
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(30, 220)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(rnd.randint(0, 255) for _ in range(3)), outline="black", width=8)
    d.text((80, 900), f"SCENE {i + 1}", font=ImageFont.truetype(FONT, 140), fill="white", stroke_width=8, stroke_fill="black")
    im.save(dest)
    return True


def get_images(job, job_dir, work, demo):
    key = os.getenv("POLLINATIONS_API_KEY", "").strip()
    base = int(job.get("seed", 4242)); last = 0.0; paths = []
    for i, sc in enumerate(job["scenes"]):
        dest = work / f"img{i:02d}.jpg"
        own = job_dir / "images" / f"{i:02d}.jpg"           # optional hand-picked image in the branch
        if own.exists() and valid(own):
            shutil.copy(own, dest); paths.append(dest); continue
        if demo:
            demo_image(i, dest); paths.append(dest); continue
        prompt = scene_prompt(job, sc); ok = False
        for attempt in range(6):
            if not key:   # anonymous free tier: 1 image / 45 s per IP
                wait = 48 - (time.time() - last)
                if wait > 0: time.sleep(wait)
            seed = base + i * 17 + attempt * 1000
            ok = pollinations(prompt, dest, seed, key); last = time.time()
            if ok: break
            if cloudflare(prompt, dest, seed): ok = True; break
            time.sleep(5)
        if not ok:
            sys.exit(f"image for scene {i + 1} failed on every provider; not publishing a broken video")
        log(f"image {i + 1}/{len(job['scenes'])} ok")
        paths.append(dest)
    return paths


def cover(path):
    im = Image.open(path).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
    l, t = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((l, t, l + W, t + H))


# ── overlays ───────────────────────────────────────────────────────────────────
_fonts = {}
def font(sz):
    if sz not in _fonts: _fonts[sz] = ImageFont.truetype(FONT, sz)
    return _fonts[sz]


def banner_img(text):
    """Cream rounded plaque with a deep-red rim and brass rivets, bold dark text (1-2 lines)."""
    text = text.upper(); f = font(96)
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.getlength(t) > 820 and cur: lines.append(cur); cur = w
        else: cur = t
    lines.append(cur)
    if len(lines) > 2: f = font(76)
    lh = int(f.size * 1.08); bw = int(max(f.getlength(l) for l in lines)) + 150; bh = lh * len(lines) + 70
    im = Image.new("RGBA", (bw + 40, bh + 40), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([24, 30, bw + 24, bh + 30], 60, fill=(0, 0, 0, 90))              # drop shadow
    d.rounded_rectangle([14, 14, bw + 14, bh + 14], 60, fill=(122, 38, 36), outline=(60, 18, 16), width=6)
    d.rounded_rectangle([30, 30, bw - 2, bh - 2], 48, fill=(248, 232, 205))
    for cx in (62, bw - 34):
        cy = bh // 2 + 14; d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(196, 140, 70), outline=(90, 50, 20), width=4)
    y = 14 + (bh - lh * len(lines)) // 2 - 6
    for l in lines:
        x = 14 + (bw - f.getlength(l)) // 2
        d.text((x, y), l, font=f, fill=(42, 30, 28)); y += lh
    return im


def counter_img(txt, squash=1.0):
    """Flip-clock tile with a glowing amber digit."""
    tw, th = 220, 250
    im = Image.new("RGBA", (tw + 30, th + 30), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([18, 22, tw + 18, th + 22], 34, fill=(0, 0, 0, 110))
    d.rounded_rectangle([8, 8, tw + 8, th + 8], 34, fill=(122, 100, 78), outline=(70, 55, 40), width=6)
    d.rounded_rectangle([26, 26, tw - 10, th - 10], 24, fill=(26, 28, 32))
    f = font(170 if len(txt) < 2 else 120)
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0)); g = ImageDraw.Draw(glow)
    x = 8 + (tw - f.getlength(txt)) / 2; y = 8 + th / 2 - f.size * 0.62
    g.text((x, y), txt, font=f, fill=(255, 190, 90, 255)); glow = glow.filter(ImageFilter.GaussianBlur(10))
    im.alpha_composite(glow); d = ImageDraw.Draw(im)
    d.text((x, y), txt, font=f, fill=(255, 236, 200))
    d.line([30, 8 + th // 2, tw - 14, 8 + th // 2], fill=(10, 10, 12), width=5)        # the flip seam
    if squash < 0.999:
        im = im.resize((im.width, max(2, int(im.height * squash))), Image.BICUBIC)
    return im


def caption_img(words, pop):
    f = font(int(96 * pop)); sp = f.getlength(" ")
    total = sum(f.getlength(w) for w, _ in words) + sp * (len(words) - 1)
    if total > 980:
        f = font(int(96 * pop * 980 / total)); sp = f.getlength(" ")
        total = sum(f.getlength(w) for w, _ in words) + sp * (len(words) - 1)
    im = Image.new("RGBA", (int(total) + 60, int(f.size * 1.6)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x = 30
    for w, y in words:
        d.text((x, 10), w, font=f, fill=(255, 214, 10) if y else (255, 255, 255), stroke_width=max(6, f.size // 9), stroke_fill=(0, 0, 0))
        x += f.getlength(w) + sp
    return im


# ── motion ─────────────────────────────────────────────────────────────────────
MOVES = ["zoom_in", "pan_left", "zoom_out", "pan_up", "pan_right", "zoom_in", "pan_down"]


def ease(u):
    return 0.5 - 0.5 * math.cos(math.pi * min(max(u, 0), 1))


def kb_frame(big, move, u, punch):
    """big = image at 1.18x. Returns a 1080x1920 crop for progress u (0..1); punch = short zoom kick at the cut."""
    u = ease(u); zmin, zmax = 1.0, 1.15
    z = {"zoom_in": zmin + (zmax - zmin) * u, "zoom_out": zmax - (zmax - zmin) * u}.get(move, 1.08)
    z *= 1 + 0.04 * punch
    cw, ch = W * 1.18 / z, H * 1.18 / z
    fx, fy = 0.5, 0.5
    if move == "pan_left": fx = 0.75 - 0.5 * u
    if move == "pan_right": fx = 0.25 + 0.5 * u
    if move == "pan_up": fy = 0.75 - 0.5 * u
    if move == "pan_down": fy = 0.25 + 0.5 * u
    l = (big.width - cw) * fx; t = (big.height - ch) * fy
    return big.transform((W, H), Image.EXTENT, (l, t, l + cw, t + ch), Image.BILINEAR)


# ── sound ──────────────────────────────────────────────────────────────────────
def sfx(kind):
    t = np.arange(int(0.35 * SR)) / SR
    if kind == "whoosh":
        n = np.random.default_rng(3).standard_normal(len(t)) * np.sin(np.pi * t / t[-1]) ** 2
        return (np.convolve(n, np.ones(40) / 40, "same") * 0.18).astype(np.float32)
    if kind == "ding":
        return (0.16 * np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 9) + 0.08 * np.sin(2 * np.pi * 1980 * t) * np.exp(-t * 12)).astype(np.float32)
    return (0.25 * np.sin(2 * np.pi * (300 + 500 * np.exp(-t * 30)) * t) * np.exp(-t * 25)).astype(np.float32)   # pop


def music_bed(preset, dur, work):
    proj = work / "beat"; (proj / "data").mkdir(parents=True, exist_ok=True)
    (proj / "data/lines.json").write_text(json.dumps({"duration": dur}))
    try:
        subprocess.run([sys.executable, str(BEATS), str(proj), preset], check=True, timeout=300)
        return decode(proj / "data/beat.wav")
    except Exception as e:
        log("music failed, continuing without it:", e); return None


# ── build ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("out"); ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    job_path = Path(a.job); job = json.loads(job_path.read_text(encoding="utf-8")); job_dir = job_path.parent
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); work = out / "_work"; work.mkdir(exist_ok=True)
    scenes = job["scenes"]
    for i, sc in enumerate(scenes):
        for k in ("say", "caps", "image"):
            if not sc.get(k): sys.exit(f"scene {i + 1}: '{k}' missing")
        n_spoken, n_caps = len(sc["say"].replace("।", " ").split()), sum(len(c) for c in parse_caps(sc["caps"]))
        if n_spoken != n_caps: log(f"WARN scene {i + 1}: {n_spoken} spoken words vs {n_caps} caption words (timing falls back to spread)")

    # 1 voice + timeline
    vl = voice_lines(job, work, a.demo)
    timeline, cur, pieces, cues = [], 0.0, [], []
    for i, ((arr, bounds), sc) in enumerate(zip(vl, scenes)):
        dur = len(arr) / SR
        chunks = parse_caps(sc["caps"]); ct = time_chunks(chunks, bounds, dur, len(sc["say"].split()))
        seg = dur + GAP + (0.45 if i == len(scenes) - 1 else 0)
        timeline.append({"start": cur, "dur": seg, "chunks": [(cur + s, cur + e, c) for (s, e), c in zip(ct, chunks)]})
        pieces += [arr, np.zeros(int((seg - dur) * SR), np.float32)]
        if i: cues.append((cur, "whoosh"))
        if sc.get("step") and (i == 0 or sc.get("step") != scenes[i - 1].get("step")): cues.append((cur + 0.05, "ding"))
        if sc.get("banner") and (i == 0 or sc.get("banner") != scenes[i - 1].get("banner")): cues.append((cur, "pop"))
        cur += seg
    total = cur; log(f"narration {total:.1f}s, {len(scenes)} scenes")
    if total > 59: log("WARN longer than 59 s")

    # 2 audio mix
    voice = np.concatenate(pieces); mix = voice.copy()
    for t0, k in cues:
        s = sfx(k); i0 = int(t0 * SR); n = min(len(s), len(mix) - i0)
        if n > 0: mix[i0:i0 + n] += s[:n]
    bed = music_bed(job.get("music", "desi-lofi"), total, work)
    if bed is not None:
        bed = np.resize(bed, len(mix)) if len(bed) < len(mix) else bed[:len(mix)]
        env = np.abs(voice); env = np.convolve(env, np.ones(4410) / 4410, "same"); duck = 1 - 0.45 * np.clip(env * 8, 0, 1)
        mix += bed * (10 ** (job.get("music_db", -22) / 20)) * 2.2 * duck
        fade = int(0.6 * SR); mix[-fade:] *= np.linspace(1, 0, fade)
    mix = mix / max(1e-6, np.abs(mix).max()) * 0.89
    wav = work / "mix.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", str(wav)], input=mix.astype(np.float32).tobytes(), check=True)

    # 3 images
    imgs = get_images(job, job_dir, work, a.demo)
    bigs = [cover(p).resize((int(W * 1.18), int(H * 1.18)), Image.LANCZOS) for p in imgs]

    # 4 frames -> ffmpeg
    slug = job.get("slug", "toon"); mp4 = out / f"{slug}.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    banners, counters = {}, {}
    review = out / "review"; review.mkdir(exist_ok=True); sheet = []
    nframes = int(total * FPS)
    for fi in range(nframes):
        t = fi / FPS
        si = max(k for k, tl in enumerate(timeline) if tl["start"] <= t + 1e-6)
        tl, sc = timeline[si], scenes[si]
        u = (t - tl["start"]) / tl["dur"]; lt = t - tl["start"]
        move = sc.get("move") or MOVES[si % len(MOVES)]
        punch = max(0, 1 - lt / 0.18) if si else 0
        fr = kb_frame(bigs[si], move, u, punch).convert("RGBA")
        # banner (pops in when it changes)
        bt = sc.get("banner")
        if bt:
            if bt not in banners: banners[bt] = banner_img(bt)
            b = banners[bt]; fresh = si == 0 or scenes[si - 1].get("banner") != bt
            s = 1.0 if (not fresh or si == 0) else min(1, 0.6 + 0.4 * ease(lt / 0.22)) * (1 + 0.06 * math.sin(min(lt / 0.3, 1) * math.pi))
            bb = b if s == 1.0 else b.resize((int(b.width * s), int(b.height * s)), Image.BICUBIC)
            fr.alpha_composite(bb, ((W - bb.width) // 2, BANNER_Y + (b.height - bb.height) // 2))
            by = BANNER_Y + b.height
        else:
            by = BANNER_Y
        # step counter (flips when the number changes)
        st = sc.get("step")
        if st:
            fresh = si > 0 and scenes[si - 1].get("step") != st
            sq = 1.0
            if fresh and lt < 0.24:
                sq = abs(math.cos(math.pi * lt / 0.24)); txt = scenes[si - 1].get("step") or st if lt < 0.12 else st
            else:
                txt = st
            c = counter_img(txt, max(sq, 0.04))
            fr.alpha_composite(c, ((W - c.width) // 2, by + 10 + (counter_img(txt).height - c.height) // 2))
        # caption
        for s0, e0, words in tl["chunks"]:
            if s0 <= t < e0 or (t >= e0 and (s0, e0, words) == tl["chunks"][-1]):
                pop = 1 + 0.12 * max(0, 1 - (t - s0) / 0.12)
                ci = caption_img(words, pop)
                fr.alpha_composite(ci, ((W - ci.width) // 2, CAP_Y - ci.height // 2))
                break
        rgb = fr.convert("RGB")
        ff.stdin.write(rgb.tobytes())
        if fi % (FPS // 2) == 0: sheet.append((t, rgb.resize((216, 384))))
        if fi in (0, int(nframes / 2)): rgb.save(review / f"frame_{t:05.1f}.jpg", quality=88)
    ff.stdin.close(); ff.wait()
    if ff.returncode: sys.exit("ffmpeg failed")

    # 5 contact sheet for QA + metadata
    cols = 10; rows = math.ceil(len(sheet) / cols); cs = Image.new("RGB", (cols * 216, rows * 404), "black"); dd = ImageDraw.Draw(cs)
    for k, (t, im) in enumerate(sheet):
        x, y = (k % cols) * 216, (k // cols) * 404; cs.paste(im, (x, y)); dd.text((x + 4, y + 386), f"{t:.1f}s", fill="white", font=font(16))
    cs.save(review / "sheet.jpg", quality=85)
    meta = dict(job.get("metadata", {})); meta.setdefault("style", "desi-toon"); meta.setdefault("language", "hi")
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    log(f"done: {mp4} ({total:.1f}s, {mp4.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
