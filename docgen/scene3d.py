"""A 3D scene for the documentary (Three.js in Remotion, software GL, no GPU): bars3d, globe or network3d.

python3 -m docgen scene3d <id> --kind bars3d|globe|network3d --spec spec.json [--data data/x.json] [--seconds 8] [--size 1920x1080]
        [--scene <n> | --words build/words/s<n>.json] [--start X] [--end X] [--max-points 10]
python3 -m docgen scene3d <id> --kind ... --spec spec.json [--data ...] --plan (--scene <n> | --narration "<text>")
Writes <assets>/ltx_scene3d_<id>.mp4 (the animation, then it holds the last frame) and <assets>/scene3d_<id>.png (the last frame). Use it as
  {"n": 14, "asset": "scene3d_<id>", "kind": "animated", "narration": "...", "note": "[3D: bars3d]"}
Hold the scene at least 8 s so the narration can read it. Rare: one or two moments the verdict or origin hangs on.

Spec (same JSON as infogen's docs/SCENES.md): title, kicker, camera ("orbit"|"push_in"|"rise"|"still"|{az,el,dist} as [from, to] pairs), and
  bars3d     items: [{label, color, highlight, cue, at}]   unit, prefix, decimals, max.  The VALUES come from --data (a file made by `docgen data`):
             each point's x is the label, y the value; the data's source is printed on the scene. A "value" in the spec is refused.
  globe      focus [lon, lat], spin, highlight [country | {country, color}], pins [{lon, lat, label, color}], arcs [{from: [lon, lat], to: [lon, lat], color}]
  network3d  nodes [{id, label, size, color}], links [{from, to, color}]
A globe or network3d that states a fact (a route, a connection) is flagged "verify": mark it so in the script like a quote or stat overlay.
--plan has Claude Opus design the camera and timing (env DOCGEN_ANIM_MODEL); it may set camera, focus, spin and per item cue, at, color, highlight; never a number,
label or source. Items appear on a narration word (cue) when word timings exist (--scene/--words), else at `at` seconds, else evenly."""
import hashlib, json, os, re, subprocess, sys
from .common import ASSETS, load_script, mkdirs
from .overlay import _remotion

KINDS = {"bars3d", "globe", "network3d"}
PRESETS = {"orbit", "push_in", "rise", "still"}
MODEL = os.environ.get("DOCGEN_ANIM_MODEL", "claude-opus-5-5")
ALLOWED = {"camera", "focus", "spin"}                 # scene fields the planner may set
ITEM_ALLOWED = {"cue", "at", "color", "highlight"}    # per item
LISTS = {"bars3d": ["items"], "globe": ["pins", "arcs"], "network3d": ["nodes", "links"]}
MIN_SECONDS = 8

def camera_ok(c):
    if isinstance(c, str): return c in PRESETS
    if not isinstance(c, dict): return False
    return all(k in ("az", "el", "dist") and isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v) for k, v in c.items())

def check(kind, s):
    """Errors in one 3D scene's spec (empty list when fine). For bars3d the items are the built ones, values included."""
    err = []
    if kind not in KINDS: return [f"kind must be one of {sorted(KINDS)}"]
    if "camera" in s and not camera_ok(s["camera"]): err.append(f"camera must be one of {sorted(PRESETS)} or {{az, el, dist}} with [from, to] numbers")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if kind == "bars3d":
        if not 1 <= len(s.get("items", [])) <= 10: err.append("bars3d wants 1 to 10 items")
        for i in s.get("items", []):
            if not num(i.get("value")): err.append(f"item {i.get('label')!r}: value must be a number")
    if kind == "globe":
        if not (s.get("pins") or s.get("arcs") or s.get("highlight")): err.append("globe needs pins, arcs or highlight")
        for p in s.get("pins", []):
            if not (num(p.get("lon")) and num(p.get("lat")) and -180 <= p["lon"] <= 180 and -90 <= p["lat"] <= 90): err.append(f"pin {p.get('label')!r}: lon -180..180 and lat -90..90 numbers")
        for a in s.get("arcs", []):
            for e in ("from", "to"):
                v = a.get(e)
                if not (isinstance(v, list) and len(v) == 2 and all(num(x) for x in v)): err.append(f"arc {e} must be [lon, lat]")
        if "focus" in s and not (isinstance(s["focus"], list) and len(s["focus"]) == 2 and all(num(x) for x in s["focus"])): err.append("focus must be [lon, lat]")
        if "spin" in s and not num(s["spin"]): err.append("spin must be a number")
    if kind == "network3d":
        ids = [n.get("id") or n.get("label") for n in s.get("nodes", [])]
        if not 2 <= len(ids) <= 14: err.append("network3d wants 2 to 14 nodes")
        if len(set(ids)) != len(ids): err.append("node ids must be unique")
        for l in s.get("links", []):
            if l.get("from") not in ids or l.get("to") not in ids: err.append(f"link {l.get('from')!r} -> {l.get('to')!r} names a node that does not exist")
    for lst in LISTS[kind]:
        for it in s.get(lst, []):
            if "at" in it and not num(it["at"]): err.append(f"{lst}: at must be seconds (a number)")
            if "cue" in it and not isinstance(it["cue"], str): err.append(f"{lst}: cue must be text")
    return err

# ---------------------------------------------------------------- data (bars3d)
def thin(points, n):
    if len(points) <= n: return points
    step = (len(points) - 1) / (n - 1); return [points[round(i * step)] for i in range(n)]

def bars_from_data(spec, d, lo=None, hi=None, max_points=10):
    """Items for bars3d: label and value from the data file; the spec's items only style them (matched by label, else by position)."""
    if any("value" in i for i in spec.get("items", [])): sys.exit("scene3d: bars3d values come from --data, not from the spec (remove 'value' from items)")
    pts = d["points"]
    if lo: pts = [p for p in pts if str(p["x"])[:len(lo)] >= lo]
    if hi: pts = [p for p in pts if str(p["x"])[:len(hi)] <= hi]
    if not pts: sys.exit("scene3d: no data points in the range")
    pts = thin(pts, min(max_points, 10)); styles = spec.get("items", [])
    by_label = {str(i.get("label")): i for i in styles if i.get("label") is not None}
    items = []
    for k, p in enumerate(pts):
        st = by_label.get(str(p["x"])) or (styles[k] if k < len(styles) and "label" not in styles[k] else {})
        items.append({**{a: b for a, b in st.items() if a != "label"}, "label": str(p["x"]), "value": p["y"]})
    return items

# ---------------------------------------------------------------- planner
def prompt(narration, scene):
    doc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "scene3d.md")).read()
    return doc + "\n\n## This scene\n\nNarration:\n" + (narration or "(none)") + "\n\nScene JSON:\n" + json.dumps(scene, indent=1) + "\n"

def ask(text, model=None):
    cmd = os.environ.get("DOCGEN_SCENE3D_CMD")
    if cmd: return subprocess.run(cmd, shell=True, input=text, capture_output=True, text=True, timeout=900).stdout
    out = subprocess.run(["claude", "-p", text, "--model", model or MODEL, "--output-format", "json", "--max-turns", "2", "--allowedTools", ""], capture_output=True, text=True, timeout=900)
    try: return json.loads(out.stdout).get("result", "")
    except Exception: return out.stdout

def parse(reply):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S)
    for x in ([m.group(1)] if m else []) + [reply[reply.find("{"):reply.rfind("}") + 1]]:
        try:
            d = json.loads(x)
            if isinstance(d, dict): return d
        except Exception: pass
    return None

def merge(kind, s, plan):
    """The scene with the planner's allowed fields applied. Lists are matched by position and must keep their length; anything else is ignored."""
    out = json.loads(json.dumps(s)); notes = []
    for k in ALLOWED:
        if k in plan: out[k] = plan[k]
    for lst in LISTS[kind]:
        got = plan.get(lst)
        if got is None: continue
        if not isinstance(got, list) or len(got) != len(out.get(lst, [])):
            notes.append(f"{lst}: ignored (needs {len(out.get(lst, []))} entries, got {len(got) if isinstance(got, list) else 'none'})"); continue
        for item, g in zip(out[lst], got):
            if isinstance(g, dict):
                for k in ITEM_ALLOWED:
                    if k in g and g[k] is not None: item[k] = g[k]
    return out, notes

# ---------------------------------------------------------------- cues -> beats
def _norm(w): return re.sub(r"[^a-z0-9]", "", w.lower())

def beats_for(kind, s, words=None):
    """Seconds at which each item appears, in the order the template reveals them. cue (needs word timings) > at > None (spread evenly)."""
    chunks = [(_norm(c["text"]), c["timestamp"][0]) for c in (words or []) if c.get("timestamp") and c["timestamp"][0] is not None and _norm(c["text"])]
    pos = 0; out = []; missed = []
    for lst in LISTS[kind]:
        for it in s.get(lst, []):
            t = None; cue = [_norm(w) for w in str(it.get("cue", "")).split() if _norm(w)]
            if cue and chunks:
                for i in range(pos, len(chunks) - len(cue) + 1):
                    if all(chunks[i + k][0] == cue[k] for k in range(len(cue))): t = chunks[i][1]; pos = i; break
                if t is None: missed.append(it.get("cue"))
            if t is None and isinstance(it.get("at"), (int, float)): t = float(it["at"])
            out.append(round(t, 2) if t is not None else None)
    return (out if any(b is not None for b in out) else None), missed

# ---------------------------------------------------------------- command
def main(cmd, argv):
    if not argv or argv[0].startswith("--") or "--kind" not in argv or "--spec" not in argv: sys.exit(__doc__)
    sid = argv[0]; arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    kind = arg("--kind"); spec_path = arg("--spec")
    if kind not in KINDS: sys.exit(f"scene3d: --kind must be one of {sorted(KINDS)}")
    spec = json.load(open(spec_path)); source = spec.get("source", ""); source_url = ""
    if kind == "bars3d":
        if not arg("--data"): sys.exit("scene3d: bars3d needs --data data/<file>.json (made by `docgen data`); numbers are never typed in")
        d = json.load(open(arg("--data"))); source = d["source"] + (f", {d['series_id']}" if d.get("series_id") else ""); source_url = d.get("url", "")
        spec = {**spec, "items": bars_from_data(spec, d, arg("--start"), arg("--end"), int(arg("--max-points", 10)))}
    elif arg("--data"): sys.exit("scene3d: --data is for bars3d only")
    err = check(kind, spec)
    if err: sys.exit("scene3d: spec rejected: " + "; ".join(err))
    narration = arg("--narration")
    if arg("--scene") and not narration:
        sc = next((x for x in load_script()["scenes"] if x.get("n") == int(arg("--scene"))), None)
        if not sc: sys.exit(f"scene3d: no scene {arg('--scene')} in script/script.json")
        narration = sc.get("narration", "")
    if "--plan" in argv:
        if not narration: sys.exit("scene3d: --plan needs --narration or --scene")
        brief = {k: v for k, v in spec.items() if k != "source"}
        plan = parse(ask(prompt(narration, brief), os.environ.get("DOCGEN_ANIM_MODEL", MODEL)))
        if not plan: sys.exit("scene3d: the planner returned no JSON")
        new, notes = merge(kind, spec, plan); err = check(kind, new)
        if err: sys.exit("scene3d: planner output rejected: " + "; ".join(err))
        saved = json.load(open(spec_path)); saved = {**saved, **{k: new[k] for k in ALLOWED if k in new}}
        for lst in LISTS[kind]:      # write the plan back; bars3d keeps no values in the spec, they come from the data on every render
            if lst in new: saved[lst] = [{k: v for k, v in it.items() if k != "value"} if kind == "bars3d" else it for it in new[lst]]
        json.dump(saved, open(spec_path, "w"), indent=1, ensure_ascii=False)
        print(json.dumps({"planned": spec_path, "model": MODEL, "camera": new.get("camera"), "notes": notes})); return
    words = None
    wf = arg("--words") or (f"build/words/s{arg('--scene')}.json" if arg("--scene") else None)
    if wf and os.path.exists(wf): words = json.load(open(wf)).get("chunks")
    beats, missed = beats_for(kind, spec, words)
    if missed: print(f"scene3d: cues not found in the narration (spread evenly): {missed}", file=sys.stderr)
    W, H = (int(x) for x in arg("--size", "1920x1080").split("x")); secs = max(float(arg("--seconds", MIN_SECONDS)), MIN_SECONDS)
    props = {"kind": kind, "width": W, "height": H, "fps": 30, "seconds": secs, "source": source, **{k: v for k, v in spec.items() if k not in ("cue", "source")},
             **({"beats": beats} if beats else {})}
    key = hashlib.sha1(json.dumps(props, sort_keys=True).encode()).hexdigest()[:12]
    mkdirs(ASSETS, "build/scene3d"); pf = os.path.abspath(f"build/scene3d/{sid}.json"); stamp = f"build/scene3d/{sid}.hash"
    mp4, png = f"{ASSETS}/ltx_scene3d_{sid}.mp4", f"{ASSETS}/scene3d_{sid}.png"
    out = {"clip": mp4, "still": png, "kind": kind, "source_url": source_url, **({"verify": True} if kind != "bars3d" else {})}
    if os.path.exists(mp4) and os.path.exists(png) and os.path.exists(stamp) and open(stamp).read() == key: print(json.dumps({**out, "cached": True})); return
    json.dump(props, open(pf, "w"))
    gl = ["--gl=swangle"]       # WebGL in software: the instance has no GPU
    _remotion(["render", "bundle", "Scene3D", os.path.abspath(mp4), f"--props={pf}", "--codec=h264", "--crf=18", "--pixel-format=yuv420p"] + gl)
    _remotion(["still", "bundle", "Scene3D", os.path.abspath(png), f"--props={pf}", f"--frame={int(secs * 30) - 1}", "--image-format=png"] + gl)
    open(stamp, "w").write(key); print(json.dumps(out))
