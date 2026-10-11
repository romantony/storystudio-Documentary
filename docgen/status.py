"""status.json in the run folder: the single source of job status. The API server watches this file.
python3 -m docgen status --stage build_long --message "..." [--done script] [--next "..."] [--warn "..."]
       [--await cp_script --question "..." --review script/script.json] [--state succeeded|failed --error-code X]
       [--output long_video=out/x.mp4] [--cost ltx_clips=12]"""
import argparse, json, os, time
PATH = "status.json"
STAGES = ["setup", "script", "assets_queued", "assets_ready", "narration", "timings", "build_long", "build_shorts", "metadata", "upload_outputs", "done"]
WEIGHT = {"setup": 0.02, "script": 0.08, "assets_queued": 0.05, "assets_ready": 0.25, "narration": 0.08, "timings": 0.04,
          "build_long": 0.25, "build_shorts": 0.12, "metadata": 0.06, "upload_outputs": 0.05, "done": 0.0}

def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def read(path=PATH):
    try: return json.load(open(path))
    except Exception: return {}

def write(st, path=PATH):
    st["updated_at"] = now()
    tmp = path + ".tmp"; json.dump(st, open(tmp, "w"), indent=1); os.replace(tmp, path)   # atomic for the watcher
    return st

def update(path=PATH, **kw):
    st = read(path)
    st.setdefault("state", "running"); st.setdefault("stages_done", []); st.setdefault("warnings", [])
    st.setdefault("outputs", []); st.setdefault("costs", {}); st.setdefault("next_steps", []); st.setdefault("awaiting", None); st.setdefault("error", None)
    if kw.get("stage") and kw["stage"] != st.get("stage"):
        if st.get("stage") and st["stage"] not in st["stages_done"]: st["stages_done"].append(st["stage"])
        st["stage"] = kw["stage"]; st["stage_started_at"] = now()
    for d in kw.get("done") or []:
        if d not in st["stages_done"]: st["stages_done"].append(d)
    if kw.get("message") is not None: st["message"] = kw["message"]
    if kw.get("next") is not None: st["next_steps"] = kw["next"]
    for w in kw.get("warn") or []:
        if w not in st["warnings"]: st["warnings"].append(w)
    for o in kw.get("output") or []:
        kind, p = o.split("=", 1)
        ent = {"kind": kind, "path": p}
        if os.path.exists(p): ent["bytes"] = os.path.getsize(p)
        st["outputs"] = [x for x in st["outputs"] if x.get("path") != p] + [ent]
    for c in kw.get("cost") or []:
        k, v = c.split("=", 1); st["costs"][k] = st["costs"].get(k, 0) + float(v) if "." in v else st["costs"].get(k, 0) + int(v)
    if kw.get("await_id"):
        st["state"] = "awaiting_input"
        st["awaiting"] = {"checkpoint_id": kw["await_id"], "question": kw.get("question") or "", "review_files": kw.get("review") or []}
    elif kw.get("state"):
        st["state"] = kw["state"]; st["awaiting"] = None
    elif kw.get("stage") or kw.get("message") is not None:
        if st["state"] == "awaiting_input": st["state"] = "running"; st["awaiting"] = None
    if kw.get("error_code"):
        st["error"] = {"code": kw["error_code"], "stage": st.get("stage"), "message": kw.get("message") or "", "retryable": bool(kw.get("retryable"))}
    if st["state"] == "succeeded":
        if st.get("stage") and st["stage"] not in st["stages_done"]: st["stages_done"].append(st["stage"])
        st["stage"] = "done"
    done = sum(WEIGHT.get(s, 0) for s in set(st["stages_done"]))
    st["progress"] = 1.0 if st["state"] == "succeeded" else round(min(done, 0.99), 2)
    return write(st, path)

def main(cmd, argv):
    ap = argparse.ArgumentParser(prog="docgen status")
    ap.add_argument("--stage", choices=STAGES); ap.add_argument("--message"); ap.add_argument("--done", action="append")
    ap.add_argument("--next", action="append"); ap.add_argument("--warn", action="append"); ap.add_argument("--output", action="append")
    ap.add_argument("--cost", action="append"); ap.add_argument("--await", dest="await_id"); ap.add_argument("--question")
    ap.add_argument("--review", action="append"); ap.add_argument("--state", choices=["running", "succeeded", "failed"])
    ap.add_argument("--error-code"); ap.add_argument("--retryable", action="store_true"); ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    if a.show: print(json.dumps(read(), indent=1)); return
    st = update(**vars(a)); print(st["state"], st.get("stage"), st["progress"])
