"""Animated text overlays, rendered by Remotion (templates in /app/remotion) to transparent clips and composited by ffmpeg.

In a script: add "overlay" to a scene (script/script.json) or a segment (shorts/<id>/script.json). One object or a list:
  {"type": "lower_third", "title": "Abraham Lincoln", "subtitle": "16th President", "at": 0.8, "seconds": 4.5}
  {"type": "stamp", "text": "Gettysburg, July 1863"}
  {"type": "title", "title": "The Road to War", "subtitle": "1850 to 1861"}
  {"type": "quote", "text": "A house divided against itself cannot stand.", "attribution": "Abraham Lincoln, 1858"}
  {"type": "stat", "value": "620,000", "label": "soldiers dead"}
"at" is seconds after the scene starts (default 0.8), "seconds" how long it stays (default 4.5, shortened to fit the scene).
"zone" is "top" or "bottom"; leave it out and the builder picks the side the captions do not use.
The builders (assemble, short) render and place these themselves. Captions are drawn on top of overlays.

By hand, from the run folder:
  python3 -m docgen overlay --type lower_third --title "..." [--subtitle "..."] --out build/x.mov [--size 1920x1080] [--seconds 4.5] [--zone bottom]
  python3 -m docgen overlay --type stamp --text "..." --onto in.mp4 --out out.mp4 [--at 1.0]     text on a video
  python3 -m docgen overlay --type title --title "..." --onto in.jpg --out out.png               text on an image
Rendering one overlay takes about 20 to 60 seconds. Clips are cached in build/overlays by content."""
import hashlib, json, os, subprocess, sys
REMOTION = os.environ.get("DOCGEN_REMOTION") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "remotion")
FIELDS = {"lower_third": ("title",), "stamp": ("text",), "title": ("title",), "quote": ("text",), "stat": ("value",)}
TEXT_KEYS = ("title", "subtitle", "text", "attribution", "value", "label", "accent")
AT, SECONDS, MIN_SECONDS = 0.8, 4.5, 1.8

def _props(spec, W, H, fps, seconds, zone):
    t = spec.get("type") or spec.get("template")
    if t not in FIELDS: sys.exit(f"overlay: unknown type {t!r} (use one of {', '.join(FIELDS)})")
    for k in FIELDS[t]:
        if not spec.get(k): sys.exit(f"overlay {t}: missing \"{k}\"")
    p = {"template": t, "zone": spec.get("zone") or zone, "width": W, "height": H, "fps": fps, "seconds": round(seconds, 2)}
    p.update({k: str(spec[k]) for k in TEXT_KEYS if spec.get(k)})
    return p

def _remotion(args):
    if not os.path.isdir(os.path.join(REMOTION, "node_modules")): sys.exit(f"overlay: Remotion is not installed in {REMOTION} (run npm ci there)")
    if not os.path.isdir(os.path.join(REMOTION, "bundle")):
        subprocess.run(["npx", "remotion", "bundle", "src/index.ts", "--out-dir", "bundle", "--log=error"], cwd=REMOTION, check=True)
    r = subprocess.run(["npx", "remotion"] + args + ["--log=error"], cwd=REMOTION, capture_output=True, text=True)
    if r.returncode: sys.exit("overlay: Remotion failed\n" + (r.stdout + r.stderr)[-1500:])

def render(spec, W, H, fps=30, seconds=SECONDS, zone="bottom", outdir="build/overlays", out=None):
    """Render one overlay to a transparent ProRes 4444 clip and return its path. Cached by content."""
    p = _props(spec, W, H, fps, seconds, zone); os.makedirs(outdir, exist_ok=True)
    key = hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]
    out = out or f"{outdir}/{p['template']}_{key}.mov"
    if os.path.exists(out) and os.path.getsize(out) > 0 and out.startswith(outdir): return out
    pf = os.path.abspath(f"{outdir}/{key}.json"); json.dump(p, open(pf, "w"))
    _remotion(["render", "bundle", "Overlay", os.path.abspath(out), f"--props={pf}", "--codec=prores", "--prores-profile=4444",
               "--pixel-format=yuva444p10le", "--image-format=png"])
    return out

def still(spec, W, H, zone, out):
    """One fully shown frame as a transparent PNG, for text on an image."""
    p = _props(spec, W, H, 30, 4, zone); pf = os.path.abspath(out + ".json"); json.dump(p, open(pf, "w"))
    _remotion(["still", "bundle", "Overlay", os.path.abspath(out), f"--props={pf}", "--frame=75", "--image-format=png"]); os.remove(pf)
    return out

def place(specs, start, length, W, H, fps, zone, outdir, label):
    """Render the overlays of one scene. Returns [(clip, absolute start time)] for caption_cmd."""
    if not specs: return []
    out = []
    for spec in (specs if isinstance(specs, list) else [specs]):
        at = float(spec.get("at", AT)); secs = min(float(spec.get("seconds", SECONDS)), length - at - 0.3)
        if secs < MIN_SECONDS:
            print(f"overlay skipped in {label}: only {max(secs, 0):.1f} s available (needs {MIN_SECONDS})"); continue
        out.append((render(spec, W, H, fps, secs, zone, outdir), round(start + at, 3)))
    return out

def caption_cmd(base, ass, out, placed=(), audio=True):
    """The ffmpeg command that burns the captions into base. With overlays, they are composited first, under the captions."""
    enc = "-c:v libx264 -crf 20 -preset veryfast -pix_fmt yuv420p" + (" -c:a copy" if audio else "")
    if not placed: return f"ffmpeg -y -loglevel error -i {base} -vf \"ass={ass}\" {enc} {out}"
    ins = " ".join(f"-i {f}" for f, _ in placed); fc = []; cur = "0:v"
    for k, (_, t) in enumerate(placed, 1):
        fc.append(f"[{k}:v]setpts=PTS+{t}/TB[o{k}]"); fc.append(f"[{cur}][o{k}]overlay=eof_action=pass[v{k}]"); cur = f"v{k}"
    fc.append(f"[{cur}]ass={ass}[v]")
    return f"ffmpeg -y -loglevel error -i {base} {ins} -filter_complex \"{';'.join(fc)}\" -map \"[v]\"" + (" -map 0:a" if audio else "") + f" {enc} {out}"

def main(cmd, argv):
    if "--type" not in argv or "--out" not in argv: sys.exit(__doc__)
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    spec = {"type": arg("--type")}; spec.update({k: arg("--" + k) for k in TEXT_KEYS if arg("--" + k)})
    out = arg("--out"); onto = arg("--onto"); zone = arg("--zone", "bottom"); secs = float(arg("--seconds", SECONDS))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if not onto:
        W, H = (int(x) for x in arg("--size", "1920x1080").split("x"))
        print(render(spec, W, H, 30, secs, zone, out=out)); return
    if onto.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        from PIL import Image
        im = Image.open(onto).convert("RGBA"); tmp = out + ".overlay.png"
        still(spec, im.width, im.height, zone, tmp)
        res = Image.alpha_composite(im, Image.open(tmp).convert("RGBA")); os.remove(tmp)
        (res if out.lower().endswith(".png") else res.convert("RGB")).save(out, quality=95); print(out); return
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0", onto], text=True).split()
    W, H = (int(x) for x in probe[0].split(",")[:2]); length = float(probe[1]); at = float(arg("--at", AT))
    secs = min(secs, length - at - 0.1)
    if secs < 1: sys.exit(f"overlay: {onto} is too short for an overlay at {at} s")
    clip = render(spec, W, H, 30, secs, zone)
    has_audio = bool(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", onto], text=True).strip())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", onto, "-i", clip, "-filter_complex", f"[1:v]setpts=PTS+{at}/TB[o];[0:v][o]overlay=eof_action=pass[v]",
                    "-map", "[v]"] + (["-map", "0:a", "-c:a", "copy"] if has_audio else []) + ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", out], check=True)
    print(out)
