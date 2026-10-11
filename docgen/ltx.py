"""ComfyUI Cloud LTX image-to-video (up to 10 s, with speech and ambience from the prompt)."""
import json, mimetypes, os, time, urllib.parse, urllib.request, uuid
from .common import key
BASE = "https://cloud.comfy.org"
WF = os.path.join(os.path.dirname(__file__), "workflows", "ltx_i2v.json")

def req(path, data=None, headers=None):
    h = {"X-API-Key": key("COMFY_API_KEY")}; h.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=h), timeout=180)

def upload(path):
    b = uuid.uuid4().hex; name = os.path.basename(path)
    body = (f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: {mimetypes.guess_type(name)[0] or "image/png"}\r\n\r\n').encode() \
        + open(path, "rb").read() + (f'\r\n--{b}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{b}--\r\n').encode()
    return json.loads(req("/api/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={b}"}).read())["name"]

def submit(image, prompt, w=1280, h=720, secs=5, fps=25, seed=None, tag="ltx"):
    j = json.load(open(WF)); P = j["prompt"]
    P["269"]["inputs"]["image"] = upload(image)
    P["75"]["inputs"]["filename_prefix"] = f"video/{tag}"
    P["320:319"]["inputs"]["value"] = prompt
    P["320:312"]["inputs"]["value"] = w; P["320:299"]["inputs"]["value"] = h
    P["320:300"]["inputs"]["value"] = fps; P["320:301"]["inputs"]["value"] = min(int(secs), 10)
    if seed is not None: P["320:277"]["inputs"]["noise_seed"] = seed
    j["extra_data"] = {"api_key_comfy_org": key("COMFY_API_KEY")}
    return json.loads(req("/api/prompt", json.dumps(j).encode(), {"Content-Type": "application/json"}).read())["prompt_id"]

def poll(pid):
    """'done' | 'failed' | 'running'"""
    try: st = json.loads(req(f"/api/job/{pid}/status").read()).get("status")
    except Exception: return "running"
    return "done" if st in ("completed", "success") else "failed" if st in ("failed", "error", "cancelled") else "running"

def fetch(pid, out):
    h = json.loads(req(f"/api/history_v2/{pid}").read())
    outs = h.get("outputs") or h.get(pid, {}).get("outputs", {})
    for o in outs.values():
        for k in ("images", "videos", "gifs"):
            for f in o.get(k, []):
                if f["filename"].endswith((".mp4", ".webm", ".mov")):
                    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
                    open(out, "wb").write(req("/api/view?" + q).read()); return out
    raise RuntimeError("no video in ComfyUI output")
