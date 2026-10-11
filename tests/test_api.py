"""End-to-end test of the API contract with the mock runner. Spends nothing. Run: .venv/bin/python tests/test_api.py"""
import hashlib, hmac, http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN, SECRET, PORT, HOOK = "test-token", "hook-secret", 18080, 18081
got, bad_sig = [], []
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        (got if hmac.compare_digest(sig, self.headers.get("X-Docgen-Signature", "")) else bad_sig).append(json.loads(raw))
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=http.server.HTTPServer(("127.0.0.1", HOOK), H).serve_forever, daemon=True).start()
runs = tempfile.mkdtemp()
env = dict(os.environ, DOCGEN_API_TOKEN=TOKEN, DOCGEN_CALLBACK_SECRET=SECRET, DOCGEN_RUNS_DIR=runs, DOCGEN_RUNNER="mock", DOCGEN_APP=ROOT, DOCGEN_HEARTBEAT_S="1",
           DOCGEN_MOCK_STEP_S="0.3", DOCGEN_ALLOW_HTTP_CALLBACK="1", GEMINI_API_KEY="x", RUNPOD_API_KEY="x", COMFY_API_KEY="x", DOCGEN_ORIGIN_SECRET="cf-secret")
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--port", str(PORT), "--log-level", "warning"], cwd=ROOT, env=env)
def call(method, path, body=None, token=TOKEN, origin="cf-secret"):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode() if body is not None else None,
                                 {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Origin-Verify": origin}, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10); return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
def wait_state(j, want, t=30):
    t0 = time.time()
    while time.time() - t0 < t:
        s = call("GET", f"/v1/documentaries/{j}")[1]
        if s["state"] in want: return s
        time.sleep(0.2)
    raise AssertionError(f"timeout waiting for {want}, last {s['state']} {s['stage']}")
ok = 0
def check(name, cond, info=""):
    global ok
    if not cond: print("FAIL", name, info); srv.terminate(); shutil.rmtree(runs); sys.exit(1)
    ok += 1; print("ok  ", name)
try:
    for _ in range(50):
        try:
            if call("GET", "/v1/health")[0] == 200: break
        except Exception: time.sleep(0.2)
    c, h = call("GET", "/v1/health"); check("health ready", c == 200 and h["ready"] and not h["busy"], h)
    check("401 bad token", call("GET", "/v1/health", token="nope")[0] == 401)
    check("403 without CloudFront origin header", call("GET", "/v1/health", origin="")[0] == 403)
    base = {"topic": "Test topic", "synopsis": "A test.", "callback": {"url": f"http://127.0.0.1:{HOOK}/hook"}}
    c, b = call("POST", "/v1/documentaries", dict(base, request_id="r1", long={"target_seconds": 5}))
    check("400 validation names the field", c == 400 and b["error"]["field"] == "long.target_seconds", b)
    c, b = call("POST", "/v1/documentaries", {"topic": "x"}); check("400 missing required", c == 400, b)
    c, b = call("POST", "/v1/documentaries", dict(base, request_id="r1")); check("202 accepted", c == 202 and b["job_id"].startswith("dg_"), b); j = b["job_id"]
    c, b2 = call("POST", "/v1/documentaries", dict(base, request_id="r1")); check("200 idempotent replay", c == 200 and b2["job_id"] == j, b2)
    c, b3 = call("POST", "/v1/documentaries", dict(base, request_id="r2")); check("409 busy", c == 409 and b3["error"]["current_job_id"] == j, b3)
    s = wait_state(j, ["awaiting_input"]); check("checkpoint cp_script", s["awaiting"]["checkpoint_id"] == "cp_script" and s["stage"] == "script", s)
    check("409 wrong checkpoint", call("POST", f"/v1/documentaries/{j}/respond", {"checkpoint_id": "cp_final", "action": "approve"})[0] == 409)
    call("POST", f"/v1/documentaries/{j}/respond", {"checkpoint_id": "cp_script", "action": "revise", "instructions": "shorter"})
    time.sleep(0.5); s = wait_state(j, ["awaiting_input"]); check("revise raises cp_script again", s["awaiting"]["checkpoint_id"] == "cp_script" and "revised" in s["awaiting"]["question"], s)
    call("POST", f"/v1/documentaries/{j}/respond", {"checkpoint_id": "cp_script", "action": "approve"})
    time.sleep(0.5); s = wait_state(j, ["awaiting_input"]); check("checkpoint cp_final", s["awaiting"]["checkpoint_id"] == "cp_final" and s["stage"] == "metadata", s)
    call("POST", f"/v1/documentaries/{j}/respond", {"checkpoint_id": "cp_final", "action": "approve"})
    s = wait_state(j, ["succeeded", "failed"]); check("succeeded", s["state"] == "succeeded" and s["progress"] == 1.0 and s["stage"] == "done" and s["outputs"][0]["kind"] == "long_video", s)
    check("stages_done complete", set(s["stages_done"]) >= {"setup", "script", "assets_queued", "assets_ready", "narration", "timings", "build_long", "build_shorts", "metadata", "upload_outputs"}, s["stages_done"])
    time.sleep(1.5)
    mine = [e for e in got if e["job_id"] == j]; ev = [e for e in mine if e["event"] != "job.heartbeat"]; seqs = [e["seq"] for e in ev]
    check("webhooks signed", len(mine) > 10 and not bad_sig, (len(mine), len(bad_sig)))
    check("webhook seq strictly increasing from 1", sorted(seqs) == list(range(1, len(seqs) + 1)), seqs)
    kinds = [e["event"] for e in sorted(ev, key=lambda e: e["seq"])]
    check("event order", kinds[0] == "job.accepted" and kinds[-1] == "job.succeeded" and kinds.count("checkpoint.awaiting_input") == 3 and "stage.started" in kinds, kinds)
    check("heartbeats sent", any(e["event"] == "job.heartbeat" for e in mine))
    c, e = call("GET", f"/v1/documentaries/{j}/events?after_seq=5"); check("events endpoint", c == 200 and e["events"][0]["seq"] == 6 and len(e["events"]) == len(seqs) - 5, len(e["events"]))
    r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/documentaries/{j}/files/out/mock.mp4", headers={"Authorization": f"Bearer {TOKEN}", "X-Origin-Verify": "cf-secret"})); check("file download", len(r.read()) == 1000)
    check("no path traversal", call("GET", f"/v1/documentaries/{j}/files/..%2Findex.json")[0] == 404 and call("GET", f"/v1/documentaries/{j}/files/../index.json")[0] in (404, 400))
    c, b = call("POST", "/v1/documentaries", dict(base, request_id="r2", review_mode="auto")); check("second job after first ends", c == 202, b)
    s = wait_state(b["job_id"], ["succeeded", "failed"]); check("auto mode runs without checkpoints", s["state"] == "succeeded" and not any(x["event"] == "checkpoint.awaiting_input" for x in got if x["job_id"] == b["job_id"]), s)
    c, b = call("POST", "/v1/documentaries", dict(base, request_id="r3", topic="FAIL please")); s = wait_state(b["job_id"], ["succeeded", "failed"])
    check("failure reported with error code", s["state"] == "failed" and s["error"]["code"] == "generation_failed", s)
    c, b = call("POST", "/v1/documentaries", dict(base, request_id="r4", review_mode="auto")); time.sleep(0.6)
    c, s = call("POST", f"/v1/documentaries/{b['job_id']}/cancel"); check("cancel", s["state"] == "cancelled", s)
    time.sleep(1.0); check("cancelled job stays cancelled and frees the slot", call("GET", f"/v1/documentaries/{b['job_id']}")[1]["state"] == "cancelled" and not call("GET", "/v1/health")[1]["busy"])
    check("health reports idle_seconds", "idle_seconds" in call("GET", "/v1/health")[1])
    print(f"\nALL {ok} CHECKS PASSED")
finally:
    srv.terminate(); shutil.rmtree(runs, ignore_errors=True)
