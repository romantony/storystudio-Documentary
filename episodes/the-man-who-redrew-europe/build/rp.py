"""RunPod helpers: key is parsed from the playbook doc (never printed). Jobs are queued with /run and polled with /status."""
import json, os, re, sys, time, urllib.request
DOC = "/home/roman-antony/local-gen-documentary/docs/CLAUDE_SESSION_STOCK_DOCUMENTARY_PROMPTS.md"
KEY = re.search(r"rpa_[A-Za-z0-9_-]+", open(DOC).read()).group(0)
EP = {"bgm": "6apg6j7suzuezw", "mm": "nzkcsef9t2iv7s", "qwen": "e165se4r3eo5hp", "flux": "rnqxi6c0mlq517", "itk": "infinitetalk"}
def call(url, body=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
    return json.load(urllib.request.urlopen(req, timeout=120))
def submit(ep, inp):
    return call(f"https://api.runpod.ai/v2/{EP.get(ep, ep)}/run", {"input": inp})["id"]
def status(ep, jid):
    return call(f"https://api.runpod.ai/v2/{EP.get(ep, ep)}/status/{jid}")
def wait(jobs, every=5, limit=3600):
    """jobs: {name: (ep, id)} -> {name: output}; raises nothing, failed jobs map to {'error': ...}"""
    out, t0 = {}, time.time()
    while len(out) < len(jobs) and time.time() - t0 < limit:
        for n, (ep, jid) in jobs.items():
            if n in out: continue
            s = status(ep, jid)
            if s["status"] == "COMPLETED": out[n] = s["output"]
            elif s["status"] in ("FAILED", "CANCELLED", "TIMED_OUT"): out[n] = {"error": str(s.get("error"))[:300]}
        time.sleep(every)
    return out
