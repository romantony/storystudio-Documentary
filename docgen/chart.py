"""A data chart for a scene, drawn in code from a file made by `docgen data` (Remotion template "Chart").

python3 -m docgen chart <id> --data data/fred_CPIAUCSL.json [--kind line|bar] --title "Prices since the gold window closed"
        [--subtitle "..."] [--unit %] [--start 1971] [--end 1980] [--highlight 1971-08 --label "Nixon closes the gold window"]
        [--max-points 40] [--seconds 8] [--size 1920x1080]
Writes <assets>/ltx_chart_<id>.mp4 (the line draws in, then holds) and <assets>/chart_<id>.png (the last frame). Use it in the script as
  {"n": 14, "asset": "chart_<id>", "kind": "animated", "narration": "...", "note": "[CHART: <dataset>]"}
The builder plays the clip, then crossfades to the still. Hold the scene as long as the narration reads the chart (the clip is
--seconds long, default 8). The source is printed on the chart; put its `url` in the description (the Fact Checker's sources do).
A chart is a factual claim: say in the script what it shows, and the Fact Checker checks the numbers against the source."""
import json, os, subprocess, sys
from .common import ASSETS, mkdirs
from .overlay import _remotion

def thin(points, n):
    if len(points) <= n: return points
    step = (len(points) - 1) / (n - 1); return [points[round(i * step)] for i in range(n)]

def main(cmd, argv):
    if len(argv) < 1 or "--data" not in argv or "--title" not in argv: sys.exit(__doc__)
    cid = argv[0]; arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    d = json.load(open(arg("--data"))); pts = d["points"]
    lo, hi = arg("--start"), arg("--end")
    if lo: pts = [p for p in pts if str(p["x"])[:len(lo)] >= lo]
    if hi: pts = [p for p in pts if str(p["x"])[:len(hi)] <= hi]
    hl = arg("--highlight")
    if hl and not any(p["x"] == hl for p in pts): sys.exit(f"chart: --highlight {hl!r} is not an x value of the data (first {pts[0]['x']}, last {pts[-1]['x']})")
    if len(pts) < 2: sys.exit("chart: fewer than two points in the range")
    kind = arg("--kind", "line"); keep = thin(pts, int(arg("--max-points", 40 if kind == "line" else 14)))
    if hl and not any(p["x"] == hl for p in keep): keep = sorted(keep + [p for p in pts if p["x"] == hl], key=lambda p: pts.index(p))
    W, H = (int(x) for x in arg("--size", "1920x1080").split("x")); secs = float(arg("--seconds", 8))
    props = {"kind": kind, "width": W, "height": H, "fps": 30, "seconds": secs, "title": arg("--title"), "subtitle": arg("--subtitle"), "source": d["source"] + (f", {d['series_id']}" if d.get("series_id") else ""),
             "unit": arg("--unit", ""), "points": [{"x": str(p["x"]), "y": p["y"]} for p in keep], "drawS": min(5, secs - 2),
             **({"highlight": {"x": hl, "label": arg("--label", "")}} if hl else {})}
    mkdirs(ASSETS, "build/charts"); pf = os.path.abspath(f"build/charts/{cid}.json"); json.dump(props, open(pf, "w"))
    mp4, png = f"{ASSETS}/ltx_chart_{cid}.mp4", f"{ASSETS}/chart_{cid}.png"
    _remotion(["render", "bundle", "Chart", os.path.abspath(mp4), f"--props={pf}", "--codec=h264", "--pixel-format=yuv420p"])
    _remotion(["still", "bundle", "Chart", os.path.abspath(png), f"--props={pf}", f"--frame={int(secs * 30) - 1}", "--image-format=png"])
    print(json.dumps({"clip": mp4, "still": png, "points": len(keep), "source_url": d.get("url", "")}))
