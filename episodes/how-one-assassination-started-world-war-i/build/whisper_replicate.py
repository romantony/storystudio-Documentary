import base64, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
TOK = os.environ["REPLICATE_API_TOKEN"]; VER = "3ab86df6c8f5"
def api(url, body=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None,
        {"User-Agent": "curl/8.5.0", "Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))
def full_ver():
    d = api("https://api.replicate.com/v1/models/vaibhavs10/incredibly-fast-whisper")
    return d["latest_version"]["id"]
V = full_ver()
def run(n):
    out = f"build/words/s{n}.json"
    if os.path.exists(out): return n, "cached"
    data = "data:audio/wav;base64," + base64.b64encode(open(f"audio/s{n}.clean.wav", "rb").read()).decode()
    p = api("https://api.replicate.com/v1/predictions", {"version": V, "input": {"audio": data, "timestamp": "word", "task": "transcribe", "language": "english", "batch_size": 24}})
    while p["status"] in ("starting", "processing"):
        time.sleep(2); p = api(p["urls"]["get"])
    if p["status"] != "succeeded": return n, "FAILED " + str(p.get("error"))[:200]
    json.dump(p["output"], open(out, "w")); return n, "ok"
with ThreadPoolExecutor(4) as ex:
    for n, s in ex.map(run, range(1, 27)): print(n, s, flush=True)
