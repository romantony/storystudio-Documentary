"""Cinematic thumbnails for the long video (16:9, 1280x720) and every Short (9:16, 1080x1920), after the StoryStudio
thumbnail guidelines: one dominant subject, 1-3 supporting elements, a contextual background, oversized dimensional
headline, dramatic light, mobile readability. Pictures come from Nano Banana 2.1 on KIE (docgen/kie.py, KIE_API_KEY);
the headline is typeset exactly by the Remotion "Cover" template as a transparent PNG and composited on top
(text_mode "overlay", the default) or, with text_mode "model", drawn by the image model and checked by the Thumbnail
Analyst. The same design as infogen's thumbnails.

1. Plan (Claude writes thumb/plan.json), then check it:   python3 -m docgen thumbnail check
   { "preset": "cinematic_infographic",
     "targets": [
       {"id": "long", "aspect": "16:9", "text": "12,941 TONS", "lines": ["12,941", "TONS"], "emphasis": 0,
        "story": "one sentence: the conflict, achievement, mystery or statistic the picture tells in one second",
        "subject": "a Douglas C-54 Skymaster banking low over Tempelhof, nose toward the camera",
        "secondary": ["ground crew unloading coal sacks", "Berlin children on a rubble heap watching"],
        "background": "1948 Tempelhof apron and a bombed-out Berlin skyline",
        "lighting": "late-afternoon key light from the left, volumetric haze",
        "placement": "top", "colors": ["golden_yellow", "metallic_white"], "accent": "red",
        "refs": ["https://upload.wikimedia.org/.../C-54_Skymaster.jpg"],
        "accuracy": ["C-54 Skymaster: four radial engines, tricycle gear, single tall fin"]},
       {"id": "a_spark", "aspect": "9:16", ...}, ... ] }
   One target "long" (16:9) and one per Short id (9:16). `refs`: up to 6 public image URLs (archive or stock pictures
   from the research) sent as image inputs, so real people, machines and places look right. `accuracy`: the visual
   facts the picture must respect. Optional top-level "era" ("Berlin, 1948-49") is added to every prompt.
   `placement` (16:9): top | center | left | right; 9:16 always uses the upper band.
2. Generate the candidates (thumbnail.candidates per target, default 3; resumable):
   python3 -m docgen thumbnail generate [--only long,a_spark] [--more 2]
   -> thumb/candidates/<target>_<n>.png (the picture) and <target>_<n>.jpg (at the target size, headline set)
3. Score them: python3 -m docgen analyst thumbnail  (the Thumbnail Analyst; review/thumbnail.json)
4. Pick: python3 -m docgen thumbnail select [--accept-best]
   Weighted score (readability 25, storytelling 25, subject 20, composition 15, colour 10, technical 5). A candidate
   must have the exact text and no accuracy error; the best at 80 or more wins. Below 80, revise the plan for that
   target and `generate --only <id> --more 3`, then score again; --accept-best takes the best passing one anyway.
   -> thumb/thumbnail.jpg and shorts/<id>/thumb/thumbnail.jpg (JPEG under 2 MB), thumb/selection.json
5. Put each Short's thumbnail into the Short as a cover frame (YouTube Shorts take their thumbnail from a frame):
   python3 -m docgen thumbnail cover --short <id> [--seconds 1] [--at end|start]"""
import glob, json, os, re, shutil, subprocess, sys
from PIL import Image
from . import kie
from .common import mkdirs
REMOTION = os.environ.get("DOCGEN_REMOTION") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "remotion")

TARGET = {"16:9": (1280, 720), "9:16": (1080, 1920)}
WEIGHTS = {"readability": 25, "storytelling": 25, "subject": 20, "composition": 15, "color": 10, "technical": 5}
PASS = 80
MAX_BYTES = 2_000_000   # YouTube's limit for a custom thumbnail
FILLS = {   # headline colours: gradient top / mid / bottom and the extrusion
    "golden_yellow": ("#FFF6C2", "#FFD23F", "#E09A00", "#3A2400"), "gold": ("#FFF1B8", "#F5C542", "#B8860B", "#3A2600"),
    "metallic_white": ("#FFFFFF", "#E9EEF3", "#AEB8C2", "#1C232B"), "metallic_silver": ("#F4F7FA", "#C9D1D9", "#7D8894", "#1A1F25"),
    "red": ("#FF8A80", "#E8291C", "#9E1209", "#2A0402"), "electric_blue": ("#C9F3FF", "#38C8FF", "#0A6FD6", "#04203F"),
    "orange": ("#FFE0B0", "#FF9F1C", "#D96500", "#3A1A00"), "yellow": ("#FFFBC2", "#FFE83F", "#E0B400", "#3A3000"),
}
ACCENTS = {"red": "#D7261E", "orange": "#F26B0F", "blue": "#1E6FD9", "gold": "#E0A100", "none": None}
PRESETS = {
    "cinematic_infographic": {"use": "documentary, education, engineering", "family": "documentary", "colors": ["golden_yellow", "metallic_white"], "accent": "red",
        "look": "Premium cinematic 3D illustration with a professional documentary infographic aesthetic; bold statistics made visible through scale",
        "light": "strong directional key light, volumetric atmosphere, subtle rim light"},
    "epic_historical": {"use": "history, battles, empires", "family": "documentary", "colors": ["gold", "metallic_white"], "accent": "red",
        "look": "High-end cinematic historical illustration, premium 3D animated documentary; dramatic conflict, heroic scale, period-accurate detail",
        "light": "epic golden-hour light, dust and haze, deep shadows"},
    "superhero_showdown": {"use": "hero vs villain stories", "family": "superhero", "colors": ["gold", "red"], "accent": "blue",
        "look": "Premium cinematic 3D animated superhero film; epic action, hero and opposing threat, contrasting elemental energy",
        "light": "dynamic action lighting, glowing elemental effects, strong rim light"},
    "mystery_discovery": {"use": "science, unexplained phenomena", "family": "documentary", "colors": ["metallic_white", "yellow"], "accent": "red",
        "look": "Cinematic suspense illustration; one striking focal object or phenomenon, a sense of the unknown",
        "light": "low-key light, a single strong glow on the focal object, atmospheric mist"},
    "economic_explainer": {"use": "economy, finance, geopolitics", "family": "documentary", "colors": ["golden_yellow", "metallic_white"], "accent": "red",
        "look": "Premium cinematic 3D explainer illustration; recognizable financial symbols, maps and infrastructure",
        "light": "clean dramatic studio-style key light, crisp reflections"},
}
VARIATION = ["a dramatic low-angle hero view", "a wide establishing view that shows the scale", "a close, intense view of the subject"]
PLAN, STATE, SEL = "thumb/plan.json", "thumb/state.json", "thumb/selection.json"

def request():
    r = json.load(open("request.json")) if os.path.exists("request.json") else {}
    t = {"style": "auto", "candidates": 3, "text": None, "text_mode": "overlay", "shorts": True, "shorts_cover": True, **(r.get("thumbnail") or {})}
    return r, t

def short_ids(): return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("shorts/*/script.json"))

def norm(s): return re.sub(r"\s+", " ", s.strip()).upper()

def check(plan, req=None, thumb=None, shorts=None):
    """(errors, warnings) for thumb/plan.json."""
    req, thumb = (req, thumb) if thumb is not None else request()
    shorts = short_ids() if shorts is None else shorts
    err, warn = [], []
    want_style = thumb.get("style", "cinematic_infographic")
    if plan.get("preset") not in PRESETS: err.append(f"preset: one of {', '.join(PRESETS)}")
    elif want_style != "auto" and plan["preset"] != want_style: err.append(f"preset: the request sets {want_style}")
    targets = plan.get("targets") if isinstance(plan.get("targets"), list) else []
    ids = [t.get("id") for t in targets if isinstance(t, dict)]
    need = ["long"] + (shorts if thumb.get("shorts", True) else [])
    for i in need:
        if i not in ids: err.append(f"targets: no target {i!r} ({'the long video' if i == 'long' else 'a Short'})")
    for i in set(ids) - set(need): err.append(f"targets: {i!r} is neither 'long' nor a Short id ({', '.join(shorts) or 'no Shorts'})")
    for t in targets:
        if not isinstance(t, dict): err.append("targets: each must be an object"); continue
        lab = f"target {t.get('id')}"
        want = "16:9" if t.get("id") == "long" else "9:16"
        if t.get("aspect") != want: err.append(f"{lab}: aspect must be {want}")
        text, lines = str(t.get("text", "")).strip(), t.get("lines")
        if not text: err.append(f"{lab}: needs the headline \"text\"")
        elif len(text.split()) > 6 or len(text) > 32: err.append(f"{lab}: \"{text}\" is too long; 2 to 5 words read in one second")
        elif len(text.split()) > 5: warn.append(f"{lab}: {len(text.split())} words; 2 to 5 read best")
        if t.get("id") == "long" and thumb.get("text") and norm(text) != norm(thumb["text"]): err.append(f"{lab}: the request fixes the text as \"{thumb['text']}\"")
        if not (isinstance(lines, list) and 1 <= len(lines) <= 3 and all(isinstance(l, str) and l.strip() for l in lines)): err.append(f"{lab}: lines must be 1 to 3 non-empty strings")
        elif norm(" ".join(lines)) != norm(text): err.append(f"{lab}: lines {lines} do not spell the text \"{text}\" exactly")
        elif not (isinstance(t.get("emphasis", 0), int) and 0 <= t.get("emphasis", 0) < len(lines)): err.append(f"{lab}: emphasis must be a line index")
        for k in ("story", "subject", "background"):
            if not str(t.get(k, "")).strip(): err.append(f"{lab}: needs \"{k}\"")
        if len(t.get("secondary") or []) > 3: err.append(f"{lab}: at most 3 secondary elements (one clear story, no clutter)")
        if t.get("placement", "top") not in ("top", "center", "left", "right"): err.append(f"{lab}: placement top, center, left or right")
        for c in t.get("colors") or []:
            if c not in FILLS: err.append(f"{lab}: colour {c!r} is not one of {', '.join(FILLS)}")
        if t.get("accent") is not None and t.get("accent") not in ACCENTS: err.append(f"{lab}: accent one of {', '.join(ACCENTS)}")
        refs = t.get("refs") or []
        if len(refs) > 6: err.append(f"{lab}: at most 6 refs")
        for r in refs:
            if not str(r).startswith(("https://", "http://")): err.append(f"{lab}: ref {r!r} must be a public image URL")
        if not isinstance(t.get("accuracy", []), list): err.append(f"{lab}: accuracy must be a list of visual facts")
    if thumb.get("text_mode") not in ("overlay", "model"): err.append('thumbnail.text_mode must be "overlay" or "model"')
    return err, warn

def prompt(t, preset, era_, mode, variant=0, n_variants=3):
    """The image prompt for one candidate, from the master templates."""
    P = PRESETS[preset]; portrait = t["aspect"] == "9:16"
    era = f" Everything historically and visually accurate for {era_}; nothing anachronistic." if era_ else ""
    details = "; ".join(str(a) for a in t.get("accuracy") or [])
    if portrait:
        layout = ("Vertical 9:16 composition. Keep the band between 10% and 35% from the top clear for a large headline. Put the dominant "
                  "storytelling in the middle 30-75% of the height and supporting context and depth in the lower part. Keep every essential "
                  "subject well away from the outer edges.")
    else:
        area = {"top": "the top 40% of the image", "center": "the middle band of the image", "left": "the left half", "right": "the right half"}[t.get("placement", "top")]
        layout = (f"Wide 16:9 composition. Keep {area} clear for a large headline. Place the dominant subject in the opposite part of the frame, "
                  "occupying 35-50% of the visual storytelling area. Keep the bottom-right corner free of anything essential.")
    if mode == "overlay":
        text = "Do not render any text, letters, numbers, captions, signs, logos or watermarks anywhere in the image."
    else:
        cols = " and ".join(c.replace("_", " ") for c in (t.get("colors") or P["colors"]))
        text = (f'Render the EXACT headline "{t["text"]}" (lines: {" / ".join(t["lines"])}) and nothing else: enormous premium cinematic 3D lettering, '
                f"heavy condensed display font, dramatic extrusion, thick black outlines, deep drop shadows, {cols} metallic finish, "
                "the emphasised line larger. Do not change, misspell, duplicate or add any words, numbers or punctuation. No other text anywhere.")
    secondary = "; ".join(t.get("secondary") or [])
    return "\n".join(filter(None, [
        f"Create an ultra-premium, high-impact cinematic YouTube {'Shorts ' if portrait else ''}thumbnail picture. {P['look']}.",
        f"STORY: {t['story']}",
        f"HERO SUBJECT: {t['subject']}. Sharp focus, high detail, dynamic perspective, cinematic rim lighting, strong separation from the background.",
        f"SUPPORTING ELEMENTS (smaller, less prominent): {secondary}." if secondary else None,
        f"BACKGROUND: {t['background']}. Atmospheric perspective, layered depth, kept subordinate to the subject.",
        f"ACCURATE DETAILS: {details}." if details else None,
        f"LIGHTING: {t.get('lighting') or P['light']}. High dynamic range look, rich shadows with preserved detail.",
        "COLOUR: bold cinematic contrast, vibrant but controlled saturation, complementary warm and cool colours, clear subject-background separation.",
        "EFFECTS: only physically motivated haze, particles, motion blur on secondary moving objects, subtle depth of field. No unnecessary explosions or lens flares.",
        f"CAMERA: {VARIATION[variant % len(VARIATION)]}." if n_variants > 1 else None,
        f"LAYOUT: {layout}",
        "MOBILE: large recognisable shapes, at most 2-3 primary focal elements, minimal fine detail in critical areas.",
        ("REFERENCE IMAGES: keep the people, vehicles and places as they look in the reference images (faces, costumes, shapes, proportions), "
         "redrawn in this cinematic style." if t.get("refs") else None),
        f"TEXT: {text}",
        f"Avoid: distorted faces, malformed hands, duplicated subjects, clutter, borders, cropped subjects, low contrast, watermarks.{era}",
    ]))

def fill_specs(t, preset):
    names = t.get("colors") or PRESETS[preset]["colors"]
    out = []
    for i in range(len(t["lines"])):
        n = names[0] if i == t.get("emphasis", 0) else (names[1] if len(names) > 1 else names[0])
        a, b, c, d = FILLS[n]; out.append({"top": a, "mid": b, "bottom": c, "extrude": d})
    return out

def to_jpeg(src, out, size):
    """Cover-crop to the target size and save as a JPEG under YouTube's 2 MB limit."""
    im = Image.open(src).convert("RGB"); W, H = size
    s = max(W / im.width, H / im.height); im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - W) // 2, (im.height - H) // 2; im = im.crop((l, t, l + W, t + H))
    for q in (92, 88, 84, 80, 75):
        im.save(out, "JPEG", quality=q, optimize=True)
        if os.path.getsize(out) <= MAX_BYTES: return out
    return out

def headline(props, out):
    """The headline as a transparent PNG, rendered by the Remotion Cover template."""
    pj = out + ".props.json"; json.dump(props, open(pj, "w"))
    if not os.path.isdir(os.path.join(REMOTION, "bundle")):
        subprocess.run(["npx", "remotion", "bundle", "src/index.ts", "--out-dir", "bundle", "--log=error"], cwd=REMOTION, check=True)
    r = subprocess.run(["npx", "remotion", "still", "bundle", "Cover", os.path.abspath(out), f"--props={os.path.abspath(pj)}", "--image-format=png", "--log=error"],
                       cwd=REMOTION, capture_output=True, text=True)
    os.remove(pj)
    if r.returncode: sys.exit("thumbnail: Remotion failed\n" + (r.stdout + r.stderr)[-1500:])
    return out

def compose(t, preset, mode, pic, out):
    W, H = TARGET[t["aspect"]]
    if mode == "model": return to_jpeg(pic, out, (W, H))
    bg = os.path.join(os.path.dirname(out), "bg", os.path.basename(out)); mkdirs(os.path.dirname(bg)); to_jpeg(pic, bg, (W, H))
    acc = t.get("accent", PRESETS[preset]["accent"])
    props = {"width": W, "height": H, "fps": 30, "seconds": 1, "lines": t["lines"], "emphasis": t.get("emphasis", 0), "placement": t.get("placement", "top"),
             "fills": fill_specs(t, preset), "accent": {"color": ACCENTS[acc], "kind": "underline"} if ACCENTS.get(acc) else None}
    text = headline(props, bg[:-4] + "_text.png")
    im = Image.open(bg).convert("RGBA"); im.alpha_composite(Image.open(text).convert("RGBA").resize((W, H)))
    tmp = out + ".png"; im.convert("RGB").save(tmp); to_jpeg(tmp, out, (W, H)); os.remove(tmp)
    return out

def generate(argv):
    req, thumb = request(); plan = json.load(open(PLAN))
    err, warn = check(plan, req, thumb)
    if err: sys.exit("thumb/plan.json has errors (run thumbnail check):\n" + "\n".join(err))
    if not kie.available(): sys.exit("KIE_API_KEY is not set: no cinematic thumbnails. Fall back to `thumb` (see the runbook) and say so in a warning.")
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    more = int(argv[argv.index("--more") + 1]) if "--more" in argv else 0
    mode = thumb["text_mode"]
    mkdirs("thumb/candidates"); state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    save = lambda: json.dump(state, open(STATE, "w"), indent=1)
    tasks = {}
    for t in plan["targets"]:
        if only and t["id"] not in only: continue
        have = sorted(int(m.group(1)) for p in glob.glob(f"thumb/candidates/{t['id']}_*.png") if (m := re.search(r"_(\d+)\.png$", p)))
        count = max(have, default=0) + more if more else max(int(thumb.get("candidates", 3)), max(have, default=0))
        for n in range(1, count + 1):
            name = f"{t['id']}_{n}"
            if os.path.exists(f"thumb/candidates/{name}.png"): continue
            if state.get(name, {}).get("task") and not state[name].get("error"): tasks[name] = state[name]["task"]; continue   # queued by an earlier run
            p = prompt(t, plan["preset"], plan.get("era"), mode, n - 1, count)
            refs = list(t.get("refs") or [])
            state[name] = {"task": kie.submit(p, refs, t["aspect"], thumb.get("resolution", "2K"), "png"), "prompt": p, "refs": refs, "target": t["id"]}
            save(); tasks[name] = state[name]["task"]; print("queued", name, flush=True)
    failed = []
    for name, res in kie.wait(tasks).items():
        if res.get("error"): state[name]["error"] = res["error"]; failed.append(name); print("FAIL", name, res["error"], flush=True); continue
        kie.download(res["url"], f"thumb/candidates/{name}.png"); state[name].update(url=res["url"]); state[name].pop("error", None); print("done", name, flush=True)
    save()
    by = {t["id"]: t for t in plan["targets"]}
    for png in sorted(glob.glob("thumb/candidates/*.png")):
        name = os.path.basename(png)[:-4]; tid = name.rsplit("_", 1)[0]; jpg = png[:-4] + ".jpg"
        if tid in by and (not only or tid in only) and not os.path.exists(jpg): compose(by[tid], plan["preset"], mode, png, jpg)
    made = sorted(glob.glob("thumb/candidates/*.jpg"))
    print(json.dumps({"candidates": made, "failed": failed, "images_generated": len(tasks) - len(failed), "warnings": warn}, indent=1))
    if failed: sys.exit(1)

def total(scores): return round(sum(WEIGHTS[k] * max(0, min(100, float(scores.get(k, 0)))) / 100 for k in WEIGHTS), 1)

def select(argv):
    plan = json.load(open(PLAN)); review = json.load(open("review/thumbnail.json"))
    accept = "--accept-best" in argv
    by_target = {}
    for c in review.get("candidates", []):
        f = c.get("file", ""); name = os.path.basename(f)[:-4]; tid = c.get("target") or name.rsplit("_", 1)[0]
        if not os.path.exists(f): continue
        ok = c.get("text_exact") is True and c.get("accurate") is not False
        by_target.setdefault(tid, []).append({"file": f, "total": total(c.get("scores", {})), "ok": ok, "issues": c.get("issues", [])})
    out, redo = {}, []
    for t in plan["targets"]:
        cands = sorted(by_target.get(t["id"], []), key=lambda c: -c["total"])
        good = [c for c in cands if c["ok"]]
        best = good[0] if good else None
        if not best or (best["total"] < PASS and not accept): redo.append({"target": t["id"], "best": best["total"] if best else None,
                                                                            "issues": (best or (cands[0] if cands else {})).get("issues", [])}); continue
        dest = "thumb/thumbnail.jpg" if t["id"] == "long" else f"shorts/{t['id']}/thumb/thumbnail.jpg"
        mkdirs(os.path.dirname(dest)); shutil.copy(best["file"], dest)
        out[t["id"]] = {"file": dest, "from": best["file"], "total": best["total"], "below_pass": best["total"] < PASS,
                        "alternatives": [{"file": c["file"], "total": c["total"]} for c in good[1:3]]}
    json.dump({"selected": out, "redo": redo}, open(SEL, "w"), indent=1)
    print(json.dumps({"selected": out, "redo": redo}, indent=1))
    if redo: sys.exit(1)

def cover(argv):
    sid = argv[argv.index("--short") + 1]; secs = float(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else 1.0
    at = argv[argv.index("--at") + 1] if "--at" in argv else "end"
    video = f"shorts/{sid}/out/{sid}.mp4"; still = f"shorts/{sid}/thumb/thumbnail.jpg"; mark = f"shorts/{sid}/thumb/cover.json"
    for p in (video, still):
        if not os.path.exists(p): sys.exit(f"missing {p}")
    if os.path.exists(mark): sys.exit(f"{sid}: the cover frame is already in the Short ({json.load(open(mark))})")
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate,codec_type:format=duration", "-of", "json", video]))
    v = next(s for s in probe["streams"] if s["codec_type"] == "video"); dur = float(probe["format"]["duration"])
    W, H, fps = v["width"], v["height"], v["r_frame_rate"]
    tmp = video[:-4] + ".cover.mp4"
    img = f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},format=yuv420p,setsar=1[c]"
    main = f"[0:v]fps={fps},format=yuv420p,setsar=1[m]"
    order = "[c][s][m][0:a]" if at == "start" else "[m][0:a][c][s]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-loop", "1", "-t", str(secs), "-i", still, "-f", "lavfi", "-t", str(secs), "-i", "anullsrc=r=48000:cl=stereo",
                    "-filter_complex", f"{img};{main};[2:a]aresample=48000[s];[0:a]aresample=48000[a0];" + order.replace("[0:a]", "[a0]") + "concat=n=2:v=1:a=1[v][a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, video)
    info = {"at": at, "seconds": secs, "cover_frame_at": 0.0 if at == "start" else round(dur, 2), "original_seconds": round(dur, 2)}
    json.dump(info, open(mark, "w")); print(json.dumps({"short": sid, **info}))

def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    sub = argv[0]
    if sub == "check":
        err, warn = check(json.load(open(PLAN)))
        print(json.dumps({"errors": err, "warnings": warn}, indent=1))
        if err: sys.exit(1)
    elif sub == "generate": generate(argv[1:])
    elif sub == "select": select(argv[1:])
    elif sub == "cover": cover(argv[1:])
    elif sub == "presets": print(json.dumps({k: {"use": v["use"], "colors": v["colors"], "accent": v["accent"]} for k, v in PRESETS.items()}, indent=1))
    else: sys.exit(__doc__)
