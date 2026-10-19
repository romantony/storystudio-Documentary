"""KIE (api.kie.ai) image generation with Nano Banana 2.1: create a task, poll it, download the result. Key: KIE_API_KEY.
Reference images must be public URLs (up to 10). Env: KIE_BASE (default https://api.kie.ai), KIE_MODEL (nano-banana-2-1)."""
import json, os, time, urllib.error, urllib.parse, urllib.request
from .common import key

BASE = os.environ.get("KIE_BASE", "https://api.kie.ai").rstrip("/")
MODEL = os.environ.get("KIE_MODEL", "nano-banana-2-1")
ASPECTS = ("1:1", "2:3", "3:2", "1:4", "4:1", "3:4", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "auto")
RETRY = (429, 500, 502, 503, 504)

def available(): return bool(os.environ.get("KIE_API_KEY"))

def call(path, body=None, tries=4):
    for n in range(tries):
        req = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None,
                                     {"Authorization": f"Bearer {key('KIE_API_KEY')}", "Content-Type": "application/json", "User-Agent": "docgen/1.0"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code in RETRY and n < tries - 1: time.sleep(5 * (n + 1)); continue
            raise RuntimeError(f"KIE {path}: HTTP {e.code} {e.read()[:300]!r}")
        if r.get("code") in RETRY and n < tries - 1: time.sleep(5 * (n + 1)); continue
        if r.get("code") != 200: raise RuntimeError(f"KIE {path}: {r.get('code')} {r.get('msg')}")
        return r["data"]
    raise RuntimeError(f"KIE {path}: no answer")

def submit(prompt, image_urls=(), aspect="16:9", resolution="2K", fmt="png"):
    """A new generation task; returns its taskId."""
    if aspect not in ASPECTS: raise ValueError(f"aspect {aspect!r} is not one of {ASPECTS}")
    inp = {"prompt": prompt[:20000], "aspect_ratio": aspect, "resolution": resolution, "output_format": fmt}
    if image_urls: inp["image_input"] = list(image_urls)[:10]
    return call("/api/v1/jobs/createTask", {"model": MODEL, "input": inp})["taskId"]

def status(task):
    """('waiting' | 'success' | 'fail', result URLs, failure message)."""
    d = call("/api/v1/jobs/recordInfo?" + urllib.parse.urlencode({"taskId": task}))
    st = d.get("state")
    urls = (json.loads(d.get("resultJson") or "{}").get("resultUrls") or []) if st == "success" else []
    return st, urls, d.get("failMsg") or d.get("failCode")

def wait(tasks, every=5, limit=900):
    """{name: taskId} -> {name: {"url": ...} | {"error": ...}}."""
    out, t0 = {}, time.time()
    while len(out) < len(tasks) and time.time() - t0 < limit:
        for n, t in tasks.items():
            if n in out: continue
            try: st, urls, msg = status(t)
            except Exception as e: st, urls, msg = "waiting", [], str(e)
            if st == "success": out[n] = {"url": urls[0]} if urls else {"error": "no result URL"}
            elif st == "fail": out[n] = {"error": str(msg)[:300]}
        if len(out) < len(tasks): time.sleep(every)
    for n in tasks: out.setdefault(n, {"error": "timeout waiting for KIE"})
    return out

def download(url, path):
    open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "docgen/1.0"}), timeout=300).read())
