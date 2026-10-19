"""Cinematic thumbnails (docgen/thumbnail.py, docgen/kie.py): plan checks, prompts, generation against a fake KIE, the
headline composite, scoring and selection, and the Shorts cover frame. Spends nothing (needs ffmpeg).
Run: .venv/bin/python tests/test_thumbnail.py"""
import http.server, json, os, subprocess, sys, tempfile, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PORT = 18094
os.environ["KIE_BASE"] = f"http://127.0.0.1:{PORT}"; os.environ["KIE_API_KEY"] = "test-key"
from PIL import Image
from docgen import analysts as A, kie, thumbnail as T

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

# ---- a fake KIE: createTask, recordInfo (waiting once, then success), and the image itself ----
tmp = tempfile.mkdtemp(); created, polls = [], {}
Image.new("RGB", (1376, 768), (40, 70, 110)).save(os.path.join(tmp, "result.png"))
class K(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, obj, code=200, raw=None, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(raw if raw is not None else json.dumps(obj).encode())
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer test-key": return self.send({"code": 401, "msg": "bad key"})
        created.append(body); self.send({"code": 200, "msg": "success", "data": {"taskId": f"t{len(created)}"}})
    def do_GET(self):
        if self.path.startswith("/img/"): return self.send(None, raw=open(os.path.join(tmp, "result.png"), "rb").read(), ctype="image/png")
        tid = self.path.split("taskId=")[1]; polls[tid] = polls.get(tid, 0) + 1
        state = "waiting" if polls[tid] < 2 else "success"
        self.send({"code": 200, "msg": "success", "data": {"taskId": tid, "state": state, "resultJson": json.dumps({"resultUrls": [f"http://127.0.0.1:{PORT}/img/{tid}.png"]}) if state == "success" else None}})
threading.Thread(target=http.server.HTTPServer(("127.0.0.1", PORT), K).serve_forever, daemon=True).start()

# ---- kie client ----
tid = kie.submit("a plane", ["https://cdn/c54.png"], "9:16", "2K", "png")
res = kie.wait({"x": tid}, every=0.05)
check("kie: task created with the model, prompt, refs, aspect, resolution", created[-1]["model"] == "nano-banana-2-1" and created[-1]["input"]["image_input"] == ["https://cdn/c54.png"]
      and (created[-1]["input"]["aspect_ratio"], created[-1]["input"]["resolution"], created[-1]["input"]["output_format"]) == ("9:16", "2K", "png"), created[-1])
check("kie: waits through 'waiting' to the result URL", res["x"]["url"].endswith(f"/img/{tid}.png") and polls[tid] == 2, (res, polls))
try: kie.submit("x", aspect="7:5"); bad = False
except ValueError: bad = True
check("kie: unknown aspect refused", bad)

# ---- plan checks ----
REQ = {"request_id": "j1", "model": "m", "thumbnail": {"style": "cinematic_infographic", "candidates": 2, "text_mode": "overlay"}}
WIKI = "https://upload.wikimedia.org/c54.jpg"
TH = {**T.request()[1], **REQ["thumbnail"]}
tgt = lambda i, aspect, **k: {"id": i, "aspect": aspect, "text": "12,941 TONS", "lines": ["12,941", "TONS"], "emphasis": 0, "story": "the airlift's record day",
                              "subject": "a C-54 banking low over Tempelhof", "secondary": ["ground crew", "children"], "background": "1948 Berlin",
                              "placement": "top", "colors": ["golden_yellow", "metallic_white"], "accent": "red", "refs": [WIKI],
                              "accuracy": ["C-54 Skymaster: four radial propeller engines, single tall tail fin"], **k}
PLAN = {"preset": "cinematic_infographic", "era": "Berlin, 1948-49", "targets": [tgt("long", "16:9"), tgt("a_hook", "9:16", text="90 DAYS", lines=["90", "DAYS"])]}
check("plan: valid", T.check(PLAN, REQ, TH, ["a_hook"]) == ([], []), T.check(PLAN, REQ, TH, ["a_hook"]))
bad = json.loads(json.dumps(PLAN))
bad["preset"] = "epic_historical"; bad["targets"][0].update(lines=["12,914", "TONS"], colors=["neon"], secondary=["a", "b", "c", "d"], refs=["c54"])
bad["targets"][1].update(aspect="16:9", text="THE ENTIRE CITY OF BERLIN FED BY AIR")
err, warn = T.check(bad, REQ, TH, ["a_hook", "b_stat"])
for name, needle in [("preset fixed by the request", "the request sets cinematic_infographic"), ("lines must spell the text", "do not spell the text"),
                     ("unknown colour", "colour 'neon'"), ("at most 3 secondary", "at most 3 secondary"), ("a Short needs 9:16", "aspect must be 9:16"),
                     ("headline too long", "too long"), ("every Short gets a target", "no target 'b_stat'"), ("refs are public URLs", "must be a public image URL")]:
    check(f"plan catches: {name}", any(needle in e for e in err), err)
check("plan: the request's fixed text binds the long target", any("fixes the text" in e for e in T.check(PLAN, REQ, {**TH, "text": "90 DAYS"}, ["a_hook"])[0]))
check("plan: auto (doc-gen's default) lets the plan choose any preset", T.request()[1]["style"] == "auto"
      and T.check({**PLAN, "preset": "epic_historical"}, REQ, {**TH, "style": "auto"}, ["a_hook"])[0] == [])

# ---- prompts ----
p_long = T.prompt(PLAN["targets"][0], "cinematic_infographic", "Berlin, 1948-49", "overlay", 0, 3)
p_short = T.prompt(PLAN["targets"][1], "cinematic_infographic", "Berlin, 1948-49", "overlay", 1, 3)
p_model = T.prompt(PLAN["targets"][0], "cinematic_infographic", "Berlin, 1948-49", "model")
check("prompt: overlay asks for no text at all and keeps the headline area clear", "Do not render any text" in p_long and "Keep the top 40% of the image clear" in p_long
      and "12,941" not in p_long, p_long[-600:])
check("prompt: subject, supporting elements, background, accuracy, era, refs", "C-54 banking low" in p_long and "ground crew; children" in p_long and "four radial propeller engines" in p_long
      and "accurate for Berlin, 1948-49" in p_long and "REFERENCE IMAGES" in p_long)
check("prompt: 9:16 uses the 10-35% band, the middle for the story, clear edges", "between 10% and 35% from the top" in p_short and "middle 30-75%" in p_short and "outer edges" in p_short)
check("prompt: 16:9 keeps the bottom-right corner free", "bottom-right corner free" in p_long)
check("prompt: candidates vary the camera", "low-angle" in p_long and "wide establishing" in p_short)
check("prompt: model mode asks for the exact text and nothing else", 'EXACT headline "12,941 TONS"' in p_model and "Do not change, misspell" in p_model)

# ---- generate, end to end (Remotion replaced by a stand-in that writes the JPEG) ----
run = os.path.join(tmp, "run"); os.makedirs(f"{run}/shorts/a_hook"); os.makedirs(f"{run}/thumb"); os.chdir(run)
json.dump(REQ, open("request.json", "w")); json.dump(PLAN, open(T.PLAN, "w")); json.dump({}, open("shorts/a_hook/script.json", "w"))
renders = []
def fake_headline(props, out):   # Remotion stand-in: a transparent PNG with an opaque band where the headline goes
    renders.append({"props": props, "out": out}); im = Image.new("RGBA", (props["width"], props["height"]), (0, 0, 0, 0))
    for y in range(80, 200):
        for x in range(200, 400): im.putpixel((x, y), (255, 210, 60, 255))
    im.save(out); return out
T.headline = fake_headline; kie.wait.__defaults__ = (0.05, 60)
created.clear()
try: T.generate([]); code = 0
except SystemExit as e: code = e.code
files = sorted(os.listdir("thumb/candidates"))
check("generate: 2 candidates per target, pictures and set thumbnails", code in (0, None) and files == ["a_hook_1.jpg", "a_hook_1.png", "a_hook_2.jpg", "a_hook_2.png", "bg", "long_1.jpg", "long_1.png", "long_2.jpg", "long_2.png"], (code, files))
check("generate: 4 KIE tasks, the ref URL as image input, Shorts at 9:16", len(created) == 4 and all(c["input"]["image_input"] == [WIKI] for c in created)
      and sorted(c["input"]["aspect_ratio"] for c in created) == ["16:9", "16:9", "9:16", "9:16"], [c["input"]["aspect_ratio"] for c in created])
r0 = next(r for r in renders if "long_1" in r["out"])["props"]
check("compose: the exact lines, emphasis gold, accent red, target sizes", r0["lines"] == ["12,941", "TONS"] and r0["fills"][0]["mid"] == "#FFD23F" and r0["fills"][1]["mid"] == "#E9EEF3"
      and r0["accent"]["color"] == "#D7261E" and (r0["width"], r0["height"]) == (1280, 720)
      and next(r for r in renders if "a_hook_1" in r["out"])["props"]["height"] == 1920, r0)
c1 = Image.open("thumb/candidates/long_1.jpg").convert("RGB")
check("compose: the headline composited over the picture, the picture elsewhere", c1.size == (1280, 720) and c1.getpixel((300, 140))[0] > 230 and c1.getpixel((900, 600))[2] > 90,
      (c1.getpixel((300, 140)), c1.getpixel((900, 600))))
n = len(created); T.generate([])
check("generate again: nothing resubmitted", len(created) == n, len(created) - n)
T.generate(["--only", "long", "--more", "1"])
check("generate --more: one new candidate for that target only", os.path.exists("thumb/candidates/long_3.jpg") and len(created) == n + 1 and not os.path.exists("thumb/candidates/a_hook_3.png"))

# ---- the Thumbnail Analyst sees the candidates, not the backgrounds ----
files = A.gather("thumbnail", "video")
check("analyst: thumbnail rubric, plan and every candidate image, no backgrounds", A.rubric_name("thumbnail", "video") == "thumbnail" and "thumb/plan.json" in files
      and "thumb/candidates/long_3.jpg" in files and not any("/bg/" in f for f in files), files)
os.environ["DOCGEN_RUBRICS_DIR"] = os.path.join(tmp, "rubrics")
check("analyst: the doc-gen rubric seeds from the app", A.load("thumbnail")["criteria"][0]["id"] == "T01" and "documentary" in A.load("thumbnail")["title"])

# ---- select ----
sc = lambda r, s=None: {k: s or r for k in T.WEIGHTS}
review = {"candidates": [
    {"file": "thumb/candidates/long_1.jpg", "target": "long", "text_exact": True, "accurate": True, "scores": sc(85)},
    {"file": "thumb/candidates/long_2.jpg", "target": "long", "text_exact": False, "accurate": True, "scores": sc(98)},   # best score but misspelled
    {"file": "thumb/candidates/long_3.jpg", "target": "long", "text_exact": True, "accurate": True, "scores": sc(91)},
    {"file": "thumb/candidates/a_hook_1.jpg", "target": "a_hook", "text_exact": True, "accurate": True, "scores": sc(70)},
    {"file": "thumb/candidates/a_hook_2.jpg", "target": "a_hook", "text_exact": True, "accurate": False, "scores": sc(95)}]}   # anachronism
os.makedirs("review", exist_ok=True); json.dump(review, open("review/thumbnail.json", "w"))
check("score: weighted 25/25/20/15/10/5", T.total({"readability": 100, "storytelling": 80, "subject": 60, "composition": 40, "color": 20, "technical": 0}) == 25 + 20 + 12 + 6 + 2)
try: T.select([]); code = 0
except SystemExit as e: code = e.code
sel = json.load(open(T.SEL))
check("select: best exact-text, accurate candidate wins; the misspelled one never does", sel["selected"]["long"]["from"].endswith("long_3.jpg") and os.path.exists("thumb/thumbnail.jpg"), sel)
check("select: a target below 80 is sent back for another round", code == 1 and sel["redo"][0]["target"] == "a_hook" and sel["redo"][0]["best"] == 70, sel["redo"])
T.select(["--accept-best"])
sel = json.load(open(T.SEL))
check("select --accept-best: takes it, marked below the bar", sel["selected"]["a_hook"]["below_pass"] and os.path.exists("shorts/a_hook/thumb/thumbnail.jpg"), sel)

# ---- cover frame in the Short ----
os.makedirs("shorts/a_hook/out")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:r=30:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "shorts/a_hook/out/a_hook.mp4"], check=True)
Image.new("RGB", (1080, 1920), (250, 250, 250)).save("shorts/a_hook/thumb/thumbnail.jpg")
T.cover(["--short", "a_hook", "--seconds", "1"])
dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "shorts/a_hook/out/a_hook.mp4"]))
last = subprocess.check_output(["ffmpeg", "-v", "error", "-sseof", "-0.1", "-i", "shorts/a_hook/out/a_hook.mp4", "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
info = json.load(open("shorts/a_hook/thumb/cover.json"))
check("cover: the Short is 1 s longer and ends on the thumbnail", abs(dur - 3.0) < 0.15 and last[0] > 200 and abs(info["cover_frame_at"] - 2.0) < 0.15, (dur, last[0], info))
try: T.cover(["--short", "a_hook"]); again = False
except SystemExit: again = True
check("cover: never inserted twice", again)

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
