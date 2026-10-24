"""3D scene spec check, data requirement, cue timing and the Opus planner merge (docgen/scene3d.py). Spends nothing (the planner is mocked).
A render smoke test runs only when Remotion and its browser are installed. Run: python3 tests/test_scene3d.py"""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from docgen import scene3d as S
def check(name, ok, info=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {info}"))
    if not ok: sys.exit(1)

bars = {"items": [{"label": "USA", "value": 916}, {"label": "China", "value": 296}]}
check("a good bars3d passes", S.check("bars3d", bars) == [])
check("bars3d with a text value is an error", S.check("bars3d", {"items": [{"label": "A", "value": "lots"}]}) != [])
check("camera preset ok, unknown rejected", S.check("bars3d", {**bars, "camera": "push_in"}) == [] and S.check("bars3d", {**bars, "camera": "spin_wildly"}) != [])
check("custom camera needs [from, to] pairs", S.check("bars3d", {**bars, "camera": {"az": [0, 20], "el": [10, 30]}}) == [] and S.check("bars3d", {**bars, "camera": {"az": [0]}}) != [])
check("globe needs something to show", S.check("globe", {}) != [])
check("globe lat out of range", S.check("globe", {"pins": [{"lon": 10, "lat": 120}]}) != [])
check("network link to a missing node", S.check("network3d", {"nodes": [{"id": "a"}, {"id": "b"}], "links": [{"from": "a", "to": "z"}]}) != [])

# the planner may set camera, cues and colours; it cannot touch values, and a list of the wrong length is ignored
plan = {"camera": "rise", "items": [{"cue": "America", "highlight": True, "value": 1}, {"cue": "China", "label": "Hacked"}], "title": "x", "source": "me"}
out, notes = S.merge("bars3d", bars, plan)
check("camera and cues applied", out["camera"] == "rise" and out["items"][0]["cue"] == "America" and out["items"][0]["highlight"] is True, out)
check("values, labels, title and source untouched", out["items"][0]["value"] == 916 and out["items"][1]["label"] == "China" and "title" not in out and "source" not in out, out)
out, notes = S.merge("bars3d", bars, {"items": [{"cue": "x"}]})
check("wrong list length ignored with a note", "cue" not in out["items"][0] and notes, (out, notes))
check("a bad planner camera is caught by the check", S.check("bars3d", S.merge("bars3d", bars, {"camera": {"az": "wide"}})[0]) != [])
check("parse reads a fenced reply", S.parse("sure\n```json\n{\"camera\": \"orbit\"}\n```") == {"camera": "orbit"})

# values come from the data file only
data = {"source": "SIPRI", "url": "https://x", "points": [{"x": "USA", "y": 916}, {"x": "China", "y": 296}]}
items = S.bars_from_data({"items": [{"label": "USA", "highlight": True}]}, data)
check("bar values come from the data, the spec only styles", [i["value"] for i in items] == [916, 296] and items[0]["highlight"] is True, items)
r = subprocess.run([sys.executable, "-c", "from docgen import scene3d as S; S.bars_from_data({'items': [{'label': 'USA', 'value': 5}]}, " + repr(data) + ")"], cwd=ROOT, capture_output=True, text=True)
check("a value typed into the spec is refused", r.returncode != 0 and "come from --data" in r.stderr, r.stderr)

# cues -> seconds
words = [{"text": " America", "timestamp": [1.0, 1.4]}, {"text": " spends", "timestamp": [1.4, 1.8]}, {"text": " China,", "timestamp": [3.2, 3.6]}]
b, miss = S.beats_for("bars3d", {"items": [{"cue": "America"}, {"cue": "china"}, {"cue": "Mars"}]}, words)
check("cues become word times, in order", b == [1.0, 3.2, None] and miss == ["Mars"], (b, miss))
check("at seconds without word timings", S.beats_for("globe", {"pins": [{"at": 2}], "arcs": [{"at": 5.5}]})[0] == [2.0, 5.5])
check("no cues, no beats", S.beats_for("globe", {"pins": [{}]})[0] is None)

# the command: bars3d needs a data file; the planner end to end with the model mocked
d = tempfile.mkdtemp(); run = lambda *a, **env: subprocess.run([sys.executable, "-m", "docgen", "scene3d", *a], cwd=d, env={**os.environ, "PYTHONPATH": ROOT, **env}, capture_output=True, text=True)
json.dump({"items": [{"label": "USA"}]}, open(f"{d}/spec.json", "w")); json.dump(data, open(f"{d}/data.json", "w"))
r = run("t", "--kind", "bars3d", "--spec", "spec.json")
check("bars3d without --data is refused", r.returncode != 0 and "--data" in r.stderr, r.stderr)
reply = f"{d}/reply.txt"; open(reply, "w").write("```json\n" + json.dumps({"camera": {"az": [-10, 10], "el": [15, 30], "dist": [1.2, 0.9]}, "items": [{"cue": "America"}, {"cue": "China", "value": 1}]}) + "\n```")
r = run("t", "--kind", "bars3d", "--spec", "spec.json", "--data", "data.json", "--plan", "--narration", "America spends more than China.", DOCGEN_SCENE3D_CMD=f"cat {reply}")
got = json.load(open(f"{d}/spec.json"))
check("--plan writes camera and cues into the spec, never values", r.returncode == 0 and got["camera"]["el"] == [15, 30] and got["items"][1]["cue"] == "China" and all("value" not in i for i in got["items"]), (r.stdout, r.stderr, got))
open(reply, "w").write("```json\n{\"camera\": \"nonsense\"}\n```")
r = run("t", "--kind", "bars3d", "--spec", "spec.json", "--data", "data.json", "--plan", "--narration", "x", DOCGEN_SCENE3D_CMD=f"cat {reply}")
check("a bad plan is rejected and the spec left alone", r.returncode != 0 and json.load(open(f"{d}/spec.json")) == got, (r.stdout, r.stderr))

# render smoke test (skipped without Remotion's browser)
rem = os.path.join(ROOT, "remotion")
if os.path.isdir(f"{rem}/node_modules/.remotion"):
    json.dump({"title": "T", "items": [{"label": "USA"}]}, open(f"{d}/spec.json", "w"))
    r = run("smoke", "--kind", "bars3d", "--spec", "spec.json", "--data", "data.json", "--seconds", "8", "--size", "480x270", DOCGEN_ASSET_DIR=f"{d}/assets")
    check("render smoke test writes a clip and a still", r.returncode == 0 and os.path.getsize(f"{d}/assets/ltx_scene3d_smoke.mp4") > 0 and os.path.getsize(f"{d}/assets/scene3d_smoke.png") > 0, r.stderr[-500:])
else: print("skip render smoke test (Remotion browser not installed)")
print("all passed")
