"""End-to-end test of the ECS task runner (api/task.py) with the mock runner, as a Step Functions state machine would drive it:
one task per run, the job folder shared between tasks, results through SendTaskSuccess/Failure/Heartbeat to a local fake of the
Step Functions API, webhooks to a local receiver. Spends nothing. Run: .venv/bin/python tests/test_task.py"""
import hashlib, hmac, http.server, json, os, shutil, subprocess, sys, tempfile, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET, HOOK, SFN, S3 = "hook-secret", 18091, 18092, 18093
got, bad_sig, sfn_calls, s3_puts = [], [], [], []
class Hook(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        (got if hmac.compare_digest(sig, self.headers.get("X-Docgen-Signature", "")) else bad_sig).append(json.loads(raw))
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
class Sfn(http.server.BaseHTTPRequestHandler):
    """Speaks just enough of the Step Functions JSON protocol for SendTaskSuccess, SendTaskFailure and SendTaskHeartbeat."""
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        sfn_calls.append((self.headers.get("X-Amz-Target", "").split(".")[-1], json.loads(raw)))
        self.send_response(200); self.send_header("Content-Type", "application/x-amz-json-1.0"); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass
class FakeS3(http.server.BaseHTTPRequestHandler):
    """Accepts PutObject and records the path."""
    def do_PUT(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0)); s3_puts.append(self.path)
        self.send_response(200); self.send_header("ETag", '"x"'); self.end_headers()
    def log_message(self, *a): pass
for port, h in ((HOOK, Hook), (SFN, Sfn), (S3, FakeS3)): threading.Thread(target=http.server.HTTPServer(("127.0.0.1", port), h).serve_forever, daemon=True).start()
runs = tempfile.mkdtemp()
env = dict(os.environ, DOCGEN_CALLBACK_SECRET=SECRET, DOCGEN_RUNS_DIR=runs, DOCGEN_RUNNER="mock", DOCGEN_APP=ROOT, DOCGEN_HEARTBEAT_S="0.5",
           DOCGEN_MOCK_STEP_S="0.3", DOCGEN_ALLOW_HTTP_CALLBACK="1", GEMINI_API_KEY="x", RUNPOD_API_KEY="x", COMFY_API_KEY="x",
           AWS_ENDPOINT_URL_SFN=f"http://127.0.0.1:{SFN}", AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test", AWS_DEFAULT_REGION="us-east-1",
           DOCGEN_OUTPUT_BUCKET="test-bucket", DOCGEN_OUTPUT_BASE_URL="https://cdn.example", DOCGEN_S3_ENDPOINT=f"http://127.0.0.1:{S3}")
env.pop("DOCGEN_API_TOKEN", None)
def task(token=None, **kv):
    """One ECS task. Returns (exit code, the reported result)."""
    e = dict(env, PAYLOAD_JSON=json.dumps({"request": kv["request"]} if "request" in kv else {"job_id": kv["job_id"], "response": kv["response"]}))
    if token: e["DOCGEN_TASK_TOKEN"] = token
    p = subprocess.run([sys.executable, "-m", "api.task"], cwd=ROOT, env=e, capture_output=True, text=True, timeout=120)
    lines = [l for l in p.stdout.splitlines() if l.startswith('{"ok"')]
    return p.returncode, (json.loads(lines[-1]) if lines else {"stdout": p.stdout, "stderr": p.stderr[-2000:]})
ok = 0
def check(name, cond, info=""):
    global ok
    if not cond: print("FAIL", name, info); shutil.rmtree(runs); sys.exit(1)
    ok += 1; print("ok  ", name)
try:
    base = {"topic": "Test topic", "synopsis": "A test.", "callback": {"url": f"http://127.0.0.1:{HOOK}/hook"}}
    rc, r = task(request=dict(base, request_id="t1", long={"target_seconds": 5}))
    check("invalid request fails the task", rc == 1 and not r["ok"] and r["result"]["error"]["code"] == "invalid_request", r)

    rc, r = task("tok-1", request=dict(base, request_id="t1", long={"format": "documentary", "target_seconds": 900}))
    s = r["result"]; j = s["job_id"]
    check("start task stops at cp_script", rc == 0 and r["ok"] and j.startswith("dg_") and s["state"] == "awaiting_input" and s["awaiting"]["checkpoint_id"] == "cp_script", r)
    succ = [c for n, c in sfn_calls if n == "SendTaskSuccess"]
    check("SendTaskSuccess carries the token and the status object", succ and succ[-1]["taskToken"] == "tok-1" and json.loads(succ[-1]["output"])["job_id"] == j, sfn_calls)
    check("task heartbeats sent", any(n == "SendTaskHeartbeat" and c["taskToken"] == "tok-1" for n, c in sfn_calls), sfn_calls)
    ru = s["awaiting"].get("review_urls") or []
    check("review files uploaded and listed at the checkpoint", ru and ru[0]["url"] == "https://cdn.example/docgen/t1/review/cp_script/request.json"
          and any(p.endswith("/docgen/t1/review/cp_script/request.json") for p in s3_puts), (ru, s3_puts))
    check("documentary limits applied", json.load(open(os.path.join(runs, j, "job.json")))["request"]["limits"]["max_runtime_minutes"] == 240)

    rc, r = task(request=dict(base, request_id="t1"))
    check("duplicate request_id refused", rc == 1 and r["result"]["error"]["code"] == "duplicate_request" and r["result"]["job_id"] == j, r)
    rc, r = task(job_id=j, response={"checkpoint_id": "cp_final", "action": "approve"})
    check("wrong checkpoint refused", rc == 1 and r["result"]["error"]["code"] == "wrong_checkpoint", r)
    rc, r = task(job_id="dg_000000000000", response={"checkpoint_id": "cp_script", "action": "approve"})
    check("unknown job refused", rc == 1 and r["result"]["error"]["code"] == "not_found", r)

    rc, r = task(job_id=j, response={"checkpoint_id": "cp_script", "action": "revise", "instructions": "shorter"})
    check("revise raises cp_script again", rc == 0 and r["result"]["awaiting"]["checkpoint_id"] == "cp_script" and "revised" in r["result"]["awaiting"]["question"], r)
    check("reviewer's answer saved", json.load(open(os.path.join(runs, j, "response_cp_script.json")))["instructions"] == "shorter")
    jb = json.load(open(os.path.join(runs, j, "job.json"))); jb["deadline"] = 0; json.dump(jb, open(os.path.join(runs, j, "job.json"), "w"))
    rc, r = task(job_id=j, response={"checkpoint_id": "cp_script", "action": "approve"})
    check("resume after a long review is not timed out; stops at cp_final", rc == 0 and r["result"]["awaiting"]["checkpoint_id"] == "cp_final", r)
    rc, r = task("tok-3", job_id=j, response={"checkpoint_id": "cp_final", "action": "approve"})
    s = r["result"]
    check("succeeded with outputs", rc == 0 and s["state"] == "succeeded" and s["outputs"][0]["kind"] == "long_video", r)
    check("outputs the run registered but never uploaded are uploaded before reporting",
          s["outputs"][0].get("url") == "https://cdn.example/docgen/t1/out/mock.mp4" and any(p.endswith("/docgen/t1/out/mock.mp4") for p in s3_puts), (s["outputs"], s3_puts))

    ev = sorted((e for e in got if e["job_id"] == j), key=lambda e: e["seq"])
    seqs = [e["seq"] for e in ev if e["event"] != "job.heartbeat"]
    check("webhooks signed and delivered before each task exited", not bad_sig and ev[-1]["event"] == "job.succeeded", [e["event"] for e in ev])
    check("webhook seq continues across tasks", seqs == sorted(set(seqs)) and seqs[0] == 1, seqs)
    check("checkpoint webhooks sent", sum(e["event"] == "checkpoint.awaiting_input" for e in ev) == 3, [e["event"] for e in ev])

    rc, r = task(request=dict(base, request_id="t2", review_mode="auto"))
    check("auto mode runs to the end in one task", rc == 0 and r["result"]["state"] == "succeeded" and r["result"]["outputs"][0].get("url"), r)
    rc, r = task("tok-f", request=dict(base, request_id="t3", topic="FAIL please"))
    fail = [c for n, c in sfn_calls if n == "SendTaskFailure" and c["taskToken"] == "tok-f"]
    check("failure reported with SendTaskFailure and the error code", rc == 1 and not r["ok"] and fail and fail[-1]["error"] == "generation_failed", (r, fail))
    rc, r = task(request=dict(base, request_id="t4"))
    rc, r = task(job_id=r["result"]["job_id"], response={"checkpoint_id": "cp_script", "action": "abort"})
    check("abort cancels without a run", rc == 0 and r["result"]["state"] == "cancelled", r)

    e2 = dict(env); env.update(GEMINI_API_KEY="")
    rc, r = task(request=dict(base, request_id="t5")); env.clear(); env.update(e2)
    check("not ready without keys", rc == 1 and r["result"]["error"]["code"] == "not_ready", r)
    print(f"\nALL {ok} CHECKS PASSED")
finally:
    shutil.rmtree(runs, ignore_errors=True)
