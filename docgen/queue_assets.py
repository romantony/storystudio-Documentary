"""Queue every generated asset from one file, resumably. Paid jobs are never submitted twice: job ids are kept in
build/queue_state.json and finished files are skipped.

python3 -m docgen queue assets.json [--only images,bgm,voices,talking,ltx]

assets.json:
{ "project_id": "wars_e7",
  "images":  [{"id": "reporter", "prompt": "...", "aspect": "9:16"}],
  "bgm":     [{"id": "bgm_long", "prompt": "...", "seconds": 120}],
  "voices":  [{"id": "tts_reporter", "voice": "am_michael", "lang": "a", "text": "...", "speed": 0.95}],
  "talking": [{"id": "itk_reporter", "image": "reporter", "voice": "tts_reporter", "prompt": "..."}],
  "ltx":     [{"id": "ltx_sumter", "image": "sumter", "prompt": "...", "w": 1280, "h": 720, "secs": 5}] }
Outputs land in the asset dir as <id>.png | .mp3 | .wav | .mp4. "talking" needs image and voice ids from this same file
(InfiniteTalk takes URLs, which only exist for assets generated here). "ltx" takes an asset id or a local path."""
import json, os, sys, time
from . import ltx, rp
from .common import ASSETS, find_image, mkdirs
STATE = "build/queue_state.json"

def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    spec = json.load(open(argv[0]))
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else {"images", "bgm", "voices", "talking", "ltx"}
    mkdirs(ASSETS, "build")
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    save = lambda: json.dump(st, open(STATE, "w"), indent=1)
    pid = spec.get("project_id") or os.path.basename(os.getcwd())
    path = lambda i, ext: f"{ASSETS}/{i}.{ext}"
    failed = []

    def fin(i, res, ext, urlkeys):
        e = st[i]
        if "error" in res: e["error"] = res["error"]; failed.append(i); save(); print("FAIL", i, res["error"], flush=True); return
        url = next((res[k] for k in urlkeys if isinstance(res.get(k), str) and res[k].startswith("http")), None) \
            or next((v for v in res.values() if isinstance(v, str) and v.startswith("http")), None)
        if not url: e["error"] = "no url in output"; failed.append(i); save(); print("FAIL", i, "no url", flush=True); return
        rp.download(url, path(i, ext)); e["url"] = url; e["file"] = path(i, ext); e.pop("error", None); save(); print("done", i, flush=True)

    # stage 1: everything with no dependencies
    s1 = []
    if "images" in only: s1.append((spec.get("images", []), "png", ["image_url"], lambda it: ("qwen", {"model": "qwen", "prompt": it["prompt"], "aspect_ratio": it.get("aspect", "16:9"), "project_id": pid, "frame_id": it["id"]})))
    if "bgm" in only: s1.append((spec.get("bgm", []), "mp3", ["audio"], lambda it: ("bgm", {"mode": "bgm", "prompt": it["prompt"], "duration_s": it.get("seconds", 50), "steps": 20, "guidance": 7.0, "project_id": pid, "frame_id": it["id"]})))
    if "voices" in only: s1.append((spec.get("voices", []), "wav", ["audio"], lambda it: ("flux", {"mode": "tts", "engine": "kokoro", "text": it["text"], "voice": it.get("voice", "am_michael"), "speed": it.get("speed", 0.95), "lang_code": it.get("lang", "a"), "project_id": pid, "frame_id": it["id"]})))
    # submit all of stage 1 before waiting on any of it, so cold endpoints warm up in parallel
    jobs1 = []
    for items, ext, urlkeys, build in s1:
        for it in items:
            i = it["id"]
            if os.path.exists(path(i, ext)) and st.get(i, {}).get("file"): print("skip", i); continue
            if not st.get(i, {}).get("job") or st[i].get("error"):
                ep, inp = build(it); st[i] = {"ep": ep, "job": rp.submit(ep, inp)}; save(); print("queued", i, flush=True)
            jobs1.append((i, ext, urlkeys))
    res1 = rp.wait({i: (st[i]["ep"], st[i]["job"]) for i, _, _ in jobs1})
    for i, ext, urlkeys in jobs1: fin(i, res1[i], ext, urlkeys)

    # stage 2: talking clips (need URLs from stage 1) and LTX clips, queued together
    tjobs, ljobs = {}, {}
    if "talking" in only:
        for it in spec.get("talking", []):
            i = it["id"]
            if os.path.exists(path(i, "mp4")) and st.get(i, {}).get("file"): print("skip", i); continue
            if not st.get(i, {}).get("job") or st[i].get("error"):
                iu, au = st.get(it["image"], {}).get("url"), st.get(it["voice"], {}).get("url")
                if not iu or not au: failed.append(i); print("FAIL", i, "image or voice id has no URL in queue_state (generate both in this file)"); continue
                st[i] = {"ep": "itk", "job": rp.submit("itk", {"prompt": it.get("prompt", "a person speaking calmly to the camera, subtle natural head movement"), "image": iu, "audio": au, "resolution": it.get("resolution", "480p"), "enable_safety_checker": True})}
                save(); print("queued", i, flush=True)
            tjobs[i] = ("itk", st[i]["job"])
    if "ltx" in only:
        for it in spec.get("ltx", []):
            i = it["id"]
            if os.path.exists(path(i, "mp4")) and st.get(i, {}).get("file"): print("skip", i); continue
            if not st.get(i, {}).get("job") or st[i].get("error"):
                img = find_image(it["image"])
                if not img: failed.append(i); print("FAIL", i, "image not found:", it["image"]); continue
                st[i] = {"ep": "ltx", "job": ltx.submit(img, it["prompt"], w=it.get("w", 1280), h=it.get("h", 720), secs=it.get("secs", 5), tag=f"{pid}_{i}")}
                save(); print("queued", i, flush=True)
            ljobs[i] = st[i]["job"]
    t0 = time.time(); pending = dict(ljobs)
    while pending and time.time() - t0 < 2400:
        for i, job in list(pending.items()):
            s = ltx.poll(job)
            if s == "done":
                try: ltx.fetch(job, path(i, "mp4")); st[i]["file"] = path(i, "mp4"); st[i].pop("error", None); print("done", i, flush=True)
                except Exception as e: st[i]["error"] = str(e)[:200]; failed.append(i); print("FAIL", i, e, flush=True)
                save(); del pending[i]
            elif s == "failed": st[i]["error"] = "comfy job failed"; failed.append(i); save(); del pending[i]; print("FAIL", i, flush=True)
        if pending: time.sleep(10)
    for i in pending: st[i]["error"] = "timeout"; failed.append(i)
    save()
    for i, res in rp.wait(tjobs, every=10, limit=3000).items(): fin(i, res, "mp4", ["video_url", "video"])
    print(json.dumps({"failed": failed, "files": sorted(e["file"] for e in st.values() if e.get("file"))}))
    if failed: sys.exit(1)
