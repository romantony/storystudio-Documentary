"""Stand-in for the Claude Code run, for testing the API without spending money. Walks the stages and writes status.json
exactly as the real toolkit does. DOCGEN_MOCK_STEP_S sets the pause between stages; a topic containing 'FAIL' fails."""
import atexit, json, os, sys, time
from docgen import status as S
mode = sys.argv[1]; step = float(os.environ.get("DOCGEN_MOCK_STEP_S", "0.5"))
req = json.load(open("request.json")); chk = req["review_mode"] == "checkpoints"
print(json.dumps({"type": "system", "subtype": "init", "session_id": "mock-session-1"}), flush=True)
N = [0]
def call():
    """One API call's usage line, as Claude Code streams it (a topic containing 'BUDGET' makes every call cost about $20)."""
    N[0] += 1; big = "BUDGET" in req["topic"]
    u = {"input_tokens": 10_000_000 if big else 1000, "output_tokens": 200, "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 0}
    print(json.dumps({"type": "assistant", "message": {"id": f"msg_{mode}_{N[0]}", "model": req["model"], "usage": u}}), flush=True)
def result():
    """The run's closing `result` line, with the session's totals so far (a resumed session's include its earlier runs)."""
    tot = json.load(open(".mock_session.json")) if os.path.exists(".mock_session.json") else {"calls": 0}
    tot["calls"] += N[0]; json.dump(tot, open(".mock_session.json", "w"))
    k = tot["calls"]; big = "BUDGET" in req["topic"]
    print(json.dumps({"type": "result", "subtype": "success", "session_id": "mock-session-1", "num_turns": N[0], "total_cost_usd": 0.01 * k,
                      "modelUsage": {req["model"]: {"inputTokens": k * (10_000_000 if big else 1000), "outputTokens": 900 * k, "cacheReadInputTokens": 5000 * k,
                                                    "cacheCreationInputTokens": 0, "costUSD": 0.01 * k}}}), flush=True)
atexit.register(result)
def go(stages):
    for st, msg in stages:
        call(); S.update(stage=st, message=msg); time.sleep(step)
first = [("setup", "Folders created."), ("script", "Scripts written.")]
rest = [("assets_queued", "Assets queued."), ("assets_ready", "Assets ready."), ("narration", "Narration done."), ("timings", "Timings done."),
        ("build_long", "Long video built."), ("build_shorts", "Shorts built."), ("metadata", "Metadata written.")]
def final():
    os.makedirs("out", exist_ok=True); open("out/mock.mp4", "wb").write(b"0" * 1000)
    S.update(stage="upload_outputs", message="Outputs listed.", output=["long_video=out/mock.mp4"], warn=["No audio has been listened to"]); time.sleep(step)
    S.update(state="succeeded", message="Done.")
if mode == "start":
    go(first)
    if "FAIL" in req["topic"]: S.update(state="failed", error_code="generation_failed", message="mock failure"); sys.exit(0)
    if chk: S.update(await_id="cp_script", question="Approve the scripts, or send changes?", review=["request.json"]); sys.exit(0)
    go(rest)
    final()
else:
    st = S.read(); cp = (json.load(open("response_cp_script.json")) if os.path.exists("response_cp_script.json") else {})
    if os.path.exists("response_cp_final.json"): final(); sys.exit(0)
    if cp.get("action") == "revise" and not os.path.exists(".revised"):
        open(".revised", "w").write("1"); S.update(stage="script", message="Scripts revised."); time.sleep(step)
        S.update(await_id="cp_script", question="Approve the revised scripts?", review=["request.json"]); sys.exit(0)
    go(rest)
    S.update(await_id="cp_final", question="Approve the final outputs?", review=["out/mock.mp4"])
