"""One run of a job as an ECS task, for a Step Functions state machine (ecs:runTask.waitForTaskToken). Replaces the API server
on ECS: each task starts the Claude run or resumes it after a checkpoint, follows it to the end of that run, and reports back.
python3 -m api.task

Env (set as container overrides by the state machine, like the other StoryStudio ECS tasks):
  PAYLOAD_JSON         start:  {"request": <the request, same body as POST /v1/documentaries>}
                       resume: {"job_id": "<from the previous task's output>", "response": {"checkpoint_id", "action": "approve"|"revise"|"abort", "instructions"}}
  DOCGEN_TASK_TOKEN   the Step Functions task token ($$.Task.Token); without it the result is only printed (local tests)
Plus everything the server reads (DOCGEN_RUNS_DIR on the shared EFS volume, DOCGEN_CALLBACK_SECRET, API keys, ...).

Task output (SendTaskSuccess): the status object of GET /v1/documentaries/{id}. Its `state` is `awaiting_input` (with `awaiting`),
`succeeded` or `cancelled`. A failed job ends with SendTaskFailure: error = the error code, cause = the error object as JSON.
Signed webhooks are sent exactly as by the server; the task waits for their delivery (with retries) before it exits."""
import fcntl, json, os, re, sys, threading, time, uuid
from contextlib import contextmanager

os.environ.setdefault("DOCGEN_API_TOKEN", "unused-in-task-mode")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from api import server as V
from docgen import status as S

TOKEN = os.environ.get("DOCGEN_TASK_TOKEN", "")
try: PAYLOAD = json.loads(os.environ.get("PAYLOAD_JSON") or "{}")
except ValueError: PAYLOAD = {"invalid": True}
HOOK_DRAIN_S = float(os.environ.get("DOCGEN_HOOK_DRAIN_S", "600"))

def sfn():
    import boto3
    return boto3.client("stepfunctions", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

def report(ok, out):
    print(json.dumps({"ok": ok, "result": out}), flush=True)
    if not TOKEN: return
    if ok: sfn().send_task_success(taskToken=TOKEN, output=json.dumps(out))
    else:
        err = out.get("error") or {}
        sfn().send_task_failure(taskToken=TOKEN, error=str(err.get("code", "internal"))[:256], cause=json.dumps(out)[:32000])

def heartbeat(stop):
    """Lets the state machine use HeartbeatSeconds, so a task that dies without reporting (out of memory, stopped) is noticed."""
    while TOKEN and not stop.wait(V.HEARTBEAT):
        try: sfn().send_task_heartbeat(taskToken=TOKEN)
        except Exception as e: print("heartbeat failed:", e, flush=True)

@contextmanager
def index_lock():
    """index.json is shared by every task on the volume; tasks can run in parallel."""
    with open(os.path.join(V.RUNS, ".index.lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)

def fail_early(code, message, job=None):
    report(False, {"job_id": job, "state": "failed", "error": {"code": code, "stage": "setup", "message": message, "retryable": False}})
    sys.exit(1)

def start():
    try: req = V.Req(**PAYLOAD["request"])
    except Exception as e: fail_early("invalid_request", str(e)[:2000])
    c = V.checks()
    if not V.ready(c, need_stock=req.visuals.stock): fail_early("not_ready", json.dumps(c))
    with index_lock():
        idx = V.index()
        if req.request_id in idx: fail_early("duplicate_request", f"request_id {req.request_id} already has job {idx[req.request_id]}", idx[req.request_id])
        j = "dg_" + uuid.uuid4().hex[:12]; os.makedirs(V.jdir(j))
        idx[req.request_id] = j; V.jwrite("", "index.json", idx)
    r = req.model_dump(); r["output"]["prefix"] = r["output"]["prefix"] or f"docgen/{req.request_id}/"
    V.jwrite(j, "request.json", r)
    V.jwrite(j, "job.json", {"job_id": j, "request_id": req.request_id, "request": r, "created_at": S.now(), "deadline": time.time() + req.limits.max_runtime_minutes * 60})
    V.jwrite(j, "state.json", {"state": "running", "seq": 0})
    S.update(os.path.join(V.jdir(j), "status.json"), stage="setup", message="Job accepted.")
    V.emit(j, "job.accepted")
    V.spawn(j, V.start_prompt(r))
    return j

def resume():
    j = str(PAYLOAD.get("job_id", ""))
    if not re.fullmatch(r"dg_[0-9a-f]{12}", j) or not os.path.isdir(V.jdir(j)): fail_early("not_found", f"no job {j!r}", j or None)
    try: r = V.Respond(**PAYLOAD["response"])
    except Exception as e: fail_early("invalid_request", str(e)[:2000], j)
    st = V.jread(j, "state.json", {}); a = S.read(os.path.join(V.jdir(j), "status.json"))
    if st.get("state") != "awaiting_input": fail_early("not_awaiting_input", f"job is {st.get('state')}", j)
    cp = (a.get("awaiting") or {}).get("checkpoint_id")
    if r.checkpoint_id != cp: fail_early("wrong_checkpoint", f"expected {cp}", j)
    if r.action == "abort": V.finish(j, "cancelled"); return j, False
    # The runtime limit counts from this run, not from job creation: the reviewer's time at the checkpoint is not the job's.
    job = V.jread(j, "job.json"); job["deadline"] = time.time() + job["request"]["limits"]["max_runtime_minutes"] * 60; V.jwrite(j, "job.json", job)
    V.jwrite(j, f"response_{cp}.json", r.model_dump())
    S.update(os.path.join(V.jdir(j), "status.json"), state="running", message=f"Checkpoint {cp}: {r.action}.")
    text = (f"The reviewer answered checkpoint {cp}: {r.action.upper()}." + (f" Their instructions: {r.instructions}" if r.instructions else "") +
            " The answer is also in response_" + cp + ".json. " + ("Continue with the next stage." if r.action == "approve" else "Apply the changes, then raise the same checkpoint again."))
    V.spawn(j, text, resume=True); V.emit(j, "status.updated")
    return j, True

def upload_review(j):
    """At a checkpoint, copy the files the reviewer is asked to look at (awaiting.review_files, inside the run folder) to the
    output bucket under <prefix>review/<checkpoint>/ and list them as awaiting.review_urls: the run folder is on EFS, out of the
    reviewer's reach. A failed upload becomes a warning; the checkpoint is raised either way."""
    sp = os.path.join(V.jdir(j), "status.json"); a = S.read(sp); aw = a.get("awaiting") or {}
    bucket = os.environ.get("DOCGEN_OUTPUT_BUCKET"); base = (os.environ.get("DOCGEN_OUTPUT_BASE_URL") or "").rstrip("/")
    if not aw.get("review_files") or not bucket: return False
    import boto3
    from urllib.parse import quote
    from docgen.upload import TYPES
    s3 = boto3.client("s3", endpoint_url=os.environ.get("DOCGEN_S3_ENDPOINT") or None)
    prefix = V.jread(j, "request.json", {}).get("output", {}).get("prefix") or f"docgen/{j}/"
    root = os.path.realpath(V.jdir(j)); urls, failed = [], []
    for rel in aw["review_files"]:
        p = os.path.realpath(os.path.join(root, rel))
        if not p.startswith(root + os.sep) or not os.path.isfile(p): failed.append(f"{rel} (missing)"); continue
        k = f"{prefix.strip('/')}/review/{aw['checkpoint_id']}/{os.path.relpath(p, root)}"
        try: s3.upload_file(p, bucket, k, ExtraArgs={"ContentType": TYPES.get(os.path.splitext(p)[1].lower(), "application/octet-stream")})
        except Exception as e: failed.append(f"{rel} ({type(e).__name__})"); continue
        urls.append({"path": rel, "bucket": bucket, "key": k, **({"url": base + "/" + quote(k)} if base else {})})
    a = S.read(sp); a["awaiting"]["review_urls"] = urls; S.write(a, sp)
    if failed: S.update(sp, warn=["Review files not uploaded: " + ", ".join(failed)])
    return True

def upload_missing_outputs(j):
    """On success, upload every registered output that has no url yet. The Claude run is told to register its outputs and then
    run `upload`; done in the other order, the outputs stay in the run folder with no url and the caller gets a finished job with
    nothing to show (first seen 2026-10-18, the Berlin Airlift job). Failures become warnings, exactly as in `upload`."""
    a = S.read(os.path.join(V.jdir(j), "status.json"))
    if not os.environ.get("DOCGEN_OUTPUT_BUCKET") or all(o.get("url") or o.get("key") for o in a.get("outputs", [])): return False
    from docgen import upload
    prefix = V.jread(j, "request.json", {}).get("output", {}).get("prefix") or f"docgen/{j}/"
    cwd = os.getcwd(); os.chdir(V.jdir(j))   # output paths in status.json are relative to the run folder
    try: upload.main("upload", ["--prefix", prefix])
    except SystemExit: pass                  # upload exits 1 after recording what failed as a warning
    finally: os.chdir(cwd)
    return True

def drain_hooks():
    t = threading.Thread(target=V.HOOKS.join, daemon=True); t.start(); t.join(HOOK_DRAIN_S)
    if t.is_alive(): print("webhooks still undelivered after", HOOK_DRAIN_S, "s", flush=True)

def main():
    stop = threading.Event(); threading.Thread(target=heartbeat, args=(stop,), daemon=True).start()
    if "request" not in PAYLOAD and "job_id" not in PAYLOAD: fail_early("invalid_request", "PAYLOAD_JSON needs a request (start) or a job_id and response (resume)")
    j, running = (start(), True) if "request" in PAYLOAD else resume()
    if running: V.watch(j)
    if V.jread(j, "state.json", {}).get("state") == "awaiting_input" and upload_review(j): V.emit(j, "status.updated")
    # No webhook for this: job.succeeded stays the last event; the URLs reach the caller in the task output below.
    if V.jread(j, "state.json", {}).get("state") == "succeeded": upload_missing_outputs(j)
    drain_hooks(); stop.set()
    out = V.public(j); ok = out["state"] != "failed"
    report(ok, out)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
