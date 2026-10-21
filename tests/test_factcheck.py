"""The fact-check command with a stand-in for Claude, and the source table in the description. Spends nothing. Run: python3 tests/test_factcheck.py"""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def check(name, ok, info=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {info}"))
    if not ok: sys.exit(1)
d = tempfile.mkdtemp(); os.makedirs(f"{d}/script"); os.makedirs(f"{d}/research")
json.dump({"model": "x"}, open(f"{d}/request.json", "w")); json.dump({"scenes": []}, open(f"{d}/script/script.json", "w")); open(f"{d}/research/fact_sheet.md", "w").write("x")
reply = json.dumps({"summary": "2 claims", "claims": [
    {"id": "c01", "where": "script scene 1", "claim": "Nixon closed the gold window in August 1971", "verdict": "supported", "source_name": "Nixon address", "source_url": "https://example.org/a"},
    {"id": "c02", "where": "script scene 2", "claim": "Prices fell 90%", "verdict": "unsupported", "fix": "Say prices rose"},
    {"id": "c03", "verdict": "bogus"}]})
env = dict(os.environ, PYTHONPATH=ROOT, DOCGEN_APP=ROOT, DOCGEN_ANALYST_CMD=f"echo '{reply}'")
r = subprocess.run([sys.executable, "-m", "docgen", "factcheck"], cwd=d, env=env, capture_output=True, text=True)
check("factcheck runs", r.returncode == 0, r.stderr + r.stdout)
c = json.load(open(f"{d}/review/claims.json"))["claims"]
check("claims with an unknown verdict are dropped", [x["id"] for x in c] == ["c01", "c02"], c)
md = open(f"{d}/review/claims.md").read()
check("report is a table with the source and the fix", "[Nixon address](https://example.org/a)" in md and "Say prices rose" in md, md)
check("summary counts printed", json.loads(r.stdout)["supported"] == 1 and json.loads(r.stdout)["unsupported"] == 1, r.stdout)
r = subprocess.run([sys.executable, "-m", "docgen", "factcheck", "--verify"], cwd=d, env=env, capture_output=True, text=True)
check("--verify writes its own report", r.returncode == 0 and os.path.exists(f"{d}/review/claims_verify.json"), r.stderr)
print("\nALL CHECKS PASSED")
