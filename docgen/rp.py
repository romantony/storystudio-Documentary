"""RunPod serverless: queue with /run, poll /status. Endpoints can be cold, so always queue and wait."""
import json, os, time, urllib.request
from .common import key
EP = {"bgm": os.environ.get("RUNPOD_EP_BGM", "6apg6j7suzuezw"), "mm": os.environ.get("RUNPOD_EP_MMAUDIO", "nzkcsef9t2iv7s"),
      "qwen": os.environ.get("RUNPOD_EP_QWEN", "e165se4r3eo5hp"), "flux": os.environ.get("RUNPOD_EP_FLUX", "rnqxi6c0mlq517"),
      "itk": os.environ.get("RUNPOD_EP_INFINITETALK", "infinitetalk")}
def call(url, body=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {"Authorization": f"Bearer {key('RUNPOD_API_KEY')}", "Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
    return json.load(urllib.request.urlopen(req, timeout=120))
def submit(ep, inp): return call(f"https://api.runpod.ai/v2/{EP.get(ep, ep)}/run", {"input": inp})["id"]
def status(ep, jid): return call(f"https://api.runpod.ai/v2/{EP.get(ep, ep)}/status/{jid}")
def wait(jobs, every=5, limit=3600, on_done=None):
    """jobs: {name: (ep, id)} -> {name: output}. Failed or timed-out jobs map to {'error': ...}."""
    out, t0 = {}, time.time()
    while len(out) < len(jobs) and time.time() - t0 < limit:
        for n, (ep, jid) in jobs.items():
            if n in out: continue
            try: s = status(ep, jid)
            except Exception as e: s = {"status": "UNKNOWN", "error": str(e)}
            if s["status"] == "COMPLETED": out[n] = s.get("output") or {}
            elif s["status"] in ("FAILED", "CANCELLED", "TIMED_OUT"): out[n] = {"error": str(s.get("error"))[:300]}
            if n in out and on_done: on_done(n, out[n])
        if len(out) < len(jobs): time.sleep(every)
    for n in jobs:
        out.setdefault(n, {"error": "timeout waiting for RunPod"})
    return out
def download(url, path):
    open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=300).read())
