"""The Thumbnail Analyst: an independent review of the thumbnail candidates against a rubric that improves after every
run (the same design as infogen's analysts).

python3 -m docgen analyst thumbnail [--verify]
    Runs the analyst as its own Claude session with read-only tools on thumb/plan.json and every candidate in
    thumb/candidates/. It scores each candidate (see docgen/thumbnail.py), scores every rubric criterion
    (pass | fail | na), lists findings (must_fix | should_fix | suggestion) and proposes new guidelines. Writes
    review/thumbnail.json and review/thumbnail.md. The first pass records the result in the rubric; --verify records
    nothing.

python3 -m docgen rubric show [thumbnail]

Rubric: <DOCGEN_RUBRICS_DIR>/thumbnail.json (default <DOCGEN_RUNS_DIR>/_rubrics, on the shared volume), seeded from
rubrics/thumbnail.json in the app. Scored criteria count their checks and failures, new guidelines become criteria, and
over MAX_ACTIVE the most-checked never-failed ones are retired; every change goes to <dir>/history.jsonl, under a lock.

DOCGEN_ANALYST_CMD replaces the claude command (tests); it gets the prompt on stdin and prints the reply."""
import fcntl, json, os, re, shutil, subprocess, sys, time
from contextlib import contextmanager
from .common import mkdirs
APP = os.environ.get("DOCGEN_APP") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROLES = {"thumbnail": "Thumbnail Analyst"}
SEVERITIES = ("must_fix", "should_fix", "suggestion")
MAX_ACTIVE = 40
RETIRE_AFTER = 10   # checks without a single failure before a criterion may be retired
INPUTS = {("thumbnail", "video"): ["request.json", "thumb/plan.json", "thumb/candidates/*.jpg"]}   # images: read each one

def rubrics_dir():
    # inside the runs volume, which outlives the container; pruning only touches the job folders in index.json
    return os.environ.get("DOCGEN_RUBRICS_DIR") or os.path.join(os.environ.get("DOCGEN_RUNS_DIR", "/data/runs"), "_rubrics")

def rubric_name(role, kind): return "thumbnail"

@contextmanager
def locked():
    d = rubrics_dir(); mkdirs(d)
    with open(os.path.join(d, ".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try: yield d
        finally: fcntl.flock(f, fcntl.LOCK_UN)

def load(name):
    """The live rubric, created from the app's seed the first time."""
    p = os.path.join(rubrics_dir(), f"{name}.json")
    if not os.path.exists(p):
        with locked():
            if not os.path.exists(p): shutil.copy(os.path.join(APP, "rubrics", f"{name}.json"), p)
    return json.load(open(p))

def words(s): return set(re.findall(r"[a-z0-9]+", s.lower())) - {"the", "a", "an", "of", "and", "or", "to", "in", "is", "are", "be", "with", "for", "on", "every", "each"}

def similar(a, b):
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6

def record(name, result, job):
    """Count the scores and add the new guidelines to the live rubric, under the lock. Returns the ids added."""
    with locked() as d:
        p = os.path.join(d, f"{name}.json"); r = json.load(open(p))
        by = {c["id"]: c for c in r["criteria"]}
        for s in result.get("scores", []):
            c = by.get(s.get("id"))
            if not c or s.get("result") not in ("pass", "fail"): continue
            c["checked"] += 1
            if s["result"] == "fail": c["failed"] += 1; c["last_failed"] = job
        added = []
        prefix = re.match(r"[A-Z]+", r["criteria"][0]["id"]).group(0) if r["criteria"] else name[0].upper()
        n = max([int(re.sub(r"\D", "", c["id"]) or 0) for c in r["criteria"]] + [0])
        for g in result.get("new_guidelines", []):
            check = str(g.get("check", "")).strip()
            if not check or any(similar(check, c["check"]) for c in r["criteria"]): continue
            n += 1; cid = f"{prefix}{n:02d}"
            r["criteria"].append({"id": cid, "area": str(g.get("area", "general"))[:40], "check": check[:400], "why": str(g.get("why", ""))[:300], "weight": 1,
                                  "status": "active", "source": job, "added": time.strftime("%Y-%m-%d"), "checked": 0, "failed": 0, "last_failed": None})
            added.append(cid)
        active = [c for c in r["criteria"] if c["status"] == "active"]
        stale = sorted((c for c in active if c["failed"] == 0 and c["checked"] >= RETIRE_AFTER), key=lambda c: (-c["checked"], c["added"]))
        retired = [c["id"] for c in stale[:max(0, len(active) - MAX_ACTIVE)]]
        for c in r["criteria"]:
            if c["id"] in retired: c["status"] = "retired"
        r["version"] += 1; r["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = p + ".tmp"; json.dump(r, open(tmp, "w"), indent=1, ensure_ascii=False); os.replace(tmp, p)
        fails = [s["id"] for s in result.get("scores", []) if s.get("result") == "fail"]
        with open(os.path.join(d, "history.jsonl"), "a") as h:
            h.write(json.dumps({"at": r["updated_at"], "job": job, "rubric": name, "version": r["version"], "failed": fails, "added": added, "retired": retired}) + "\n")
        return added, r["version"]

def gather(role, kind):
    import glob
    files = [p for pat in INPUTS.get((role, kind)) or INPUTS[(role, "video")] for p in sorted(glob.glob(pat))]
    return files

def prompt(role, kind, rubric, files, verify):
    crit = [c for c in rubric["criteria"] if c["status"] == "active"]
    lines = "\n".join(f"- {c['id']} [{c['area']}, weight {c['weight']}]: {c['check']} (why: {c['why']})" for c in crit)
    previous = ""
    if verify and os.path.exists(f"review/{role}.json"):
        previous = ("\n\nThis is a second pass after the producer's fixes. Your first pass found:\n" + open(f"review/{role}.json").read()
                    + "\nSay for each must_fix and should_fix whether it is now resolved.")
    return (open(os.path.join(APP, "prompts", f"analyst_{role}.md")).read()
            + f"\n\n## This review\n\nRequest kind: {kind}. Rubric: {rubric['title']} (version {rubric['version']}).\n\nCriteria:\n{lines}\n\n"
            f"Files to review, in the current folder (read every one of them in full):\n" + "\n".join(f"- {f}" for f in files) + previous)

def ask(text, role, model):
    """The analyst's reply text: a fresh Claude session with read-only tools."""
    cmd = os.environ.get("DOCGEN_ANALYST_CMD")
    if cmd: return subprocess.run(cmd, shell=True, input=text, capture_output=True, text=True, timeout=1800).stdout
    tools = "Read Glob Grep" + (" WebSearch WebFetch" if role == "research" else "")
    out = subprocess.run(["claude", "-p", text, "--model", model, "--output-format", "json", "--max-turns", "40", "--allowedTools", *tools.split()],
                         capture_output=True, text=True, timeout=1800)
    try: return json.loads(out.stdout).get("result", "")
    except Exception: return out.stdout

def parse(reply):
    """The JSON object in the reply (bare, or in a ```json fence)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S)
    for s in ([m.group(1)] if m else []) + [reply[reply.find("{"):reply.rfind("}") + 1]]:
        try:
            d = json.loads(s)
            if isinstance(d, dict): return d
        except Exception: pass
    return None

def report_md(role, res, name, version):
    L = [f"# {ROLES[role]}: {name} rubric v{version}", "", res.get("summary", ""), ""]
    for sev in SEVERITIES:
        fs = [f for f in res.get("findings", []) if f.get("severity") == sev]
        if fs: L += [f"## {sev.replace('_', ' ')} ({len(fs)})", ""] + [f"- **{f.get('where', '')}**: {f.get('issue', '')} Fix: {f.get('fix', '')}" for f in fs] + [""]
    fails = [s for s in res.get("scores", []) if s.get("result") == "fail"]
    if fails: L += ["## Criteria failed", ""] + [f"- {s['id']}: {s.get('note', '')}" for s in fails] + [""]
    if res.get("new_guidelines"): L += ["## Proposed guidelines", ""] + [f"- [{g.get('area', '')}] {g.get('check', '')}" for g in res["new_guidelines"]] + [""]
    return "\n".join(L)

def main(cmd, argv):
    if cmd == "rubric":
        if not argv or argv[0] != "show": sys.exit(__doc__)
        for name in argv[1:] or ["thumbnail"]:
            r = load(name); print(f"# {r['title']} (v{r['version']})")
            for c in r["criteria"]:
                if c["status"] == "active": print(f"- {c['id']} [{c['area']}] {c['check']}" + (f"  (failed {c['failed']} of {c['checked']})" if c["checked"] else ""))
            print()
        return
    if not argv or argv[0] not in ROLES: sys.exit(__doc__)
    role = argv[0]; verify = "--verify" in argv
    req = json.load(open("request.json")) if os.path.exists("request.json") else {}
    kind = req.get("kind", "video"); name = rubric_name(role, kind); rubric = load(name)
    files = gather(role, kind)
    if not files: sys.exit(f"{ROLES[role]}: nothing to review yet")
    reply = ask(prompt(role, kind, rubric, files, verify), role, req.get("model", "claude-sonnet-5-5"))
    res = parse(reply)
    if res is None: sys.exit(f"{ROLES[role]}: the reply was not a JSON report:\n{reply[-1500:]}")
    res = {"role": role, "rubric": name, "rubric_version": rubric["version"], "verify": verify, **res}
    res["findings"] = [f for f in res.get("findings", []) if isinstance(f, dict) and f.get("severity") in SEVERITIES]
    mkdirs("review")
    out = f"review/{role}_verify" if verify else f"review/{role}"
    added, version = ([], rubric["version"]) if verify else record(name, res, req.get("request_id") or os.path.basename(os.getcwd()))
    res["guidelines_added"] = added
    json.dump(res, open(out + ".json", "w"), indent=1, ensure_ascii=False); open(out + ".md", "w").write(report_md(role, res, name, version))
    count = {s: sum(1 for f in res["findings"] if f["severity"] == s) for s in SEVERITIES}
    fails = sum(1 for s in res.get("scores", []) if s.get("result") == "fail")
    print(json.dumps({"analyst": ROLES[role], "rubric": name, "rubric_version": version, "report": out + ".md", "findings": count,
                      "criteria_failed": fails, "guidelines_added": added, "summary": res.get("summary", "")}, indent=1))
