"""The separate fact-validation pass (Decoded Economy playbook, "Fact-validation workflow" steps 3-4).

python3 -m docgen factcheck [--verify]
    Runs the Fact Checker as its own Claude session, never the one that wrote the script, with read-only tools plus WebSearch
    and WebFetch. It reads request.json, research/fact_sheet.md, script/script.json and every shorts/<id>/script.json, extracts
    every factual claim (a name, number, date, quotation or causal statement, including the ones in overlays) and checks each
    against a primary source (FRED, BLS, EIA, IMF, central banks, court or regulator filings, the original document).
    Writes review/claims.json and review/claims.md. --verify is the second pass after the producer's fixes: it writes
    review/claims_verify.json and says which earlier findings are resolved.

review/claims.json:
{ "summary": "...", "claims": [ {"id": "c01", "where": "script scene 7 | short a_spark seg 2 | overlay scene 9", "claim": "...",
    "number": "...", "date": "...", "verdict": "supported | unsupported | disputed | hedge", "source_name": "...", "source_url": "https://...",
    "evidence": "what the source says, one or two sentences", "fix": "the corrected or hedged wording; empty when supported"} ] }
The producer cuts or hedges every unsupported claim, labels every disputed one as disputed in the narration, and rebuilds.
`metadata` puts the supported claims' sources into the description.

DOCGEN_ANALYST_CMD replaces the claude command (tests); it gets the prompt on stdin and prints the reply."""
import glob, json, os, sys
from .analysts import APP, ask, parse
from .common import mkdirs
VERDICTS = ("supported", "unsupported", "disputed", "hedge")

def files():
    return [p for p in ["request.json", "research/fact_sheet.md", "script/script.json"] + sorted(glob.glob("shorts/*/script.json")) if os.path.exists(p)]

def prompt(fs, verify):
    previous = ""
    if verify and os.path.exists("review/claims.json"):
        previous = ("\n\nThis is a second pass after the producer's fixes. Your first pass found:\n" + open("review/claims.json").read()
                    + "\nCheck the script again from scratch, then say for each earlier unsupported, disputed or hedge claim whether it is now resolved.")
    return (open(os.path.join(APP, "prompts", "factcheck.md")).read()
            + "\n\n## This review\n\nFiles to review, in the current folder (read every one of them in full):\n" + "\n".join(f"- {f}" for f in fs) + previous)

def report_md(res):
    L = ["# Fact check", "", res.get("summary", ""), "", "| # | Where | Claim | Verdict | Source | Fix |", "| --- | --- | --- | --- | --- | --- |"]
    for c in res["claims"]:
        src = f"[{c.get('source_name') or 'source'}]({c['source_url']})" if c.get("source_url") else ""
        L.append(f"| {c.get('id', '')} | {c.get('where', '')} | {c.get('claim', '')} | {c.get('verdict', '')} | {src} | {c.get('fix', '')} |")
    return "\n".join(L) + "\n"

def main(cmd, argv):
    verify = "--verify" in argv
    req = json.load(open("request.json")) if os.path.exists("request.json") else {}
    fs = files()
    if "script/script.json" not in fs: sys.exit("Fact Checker: no script yet")
    reply = ask(prompt(fs, verify), "research", req.get("model", "claude-sonnet-5-5"))
    res = parse(reply)
    if res is None or not isinstance(res.get("claims"), list): sys.exit(f"Fact Checker: the reply was not a JSON report:\n{reply[-1500:]}")
    res["claims"] = [c for c in res["claims"] if isinstance(c, dict) and c.get("verdict") in VERDICTS]
    mkdirs("review"); out = "review/claims_verify" if verify else "review/claims"
    json.dump(res, open(out + ".json", "w"), indent=1, ensure_ascii=False); open(out + ".md", "w").write(report_md(res))
    count = {v: sum(1 for c in res["claims"] if c["verdict"] == v) for v in VERDICTS}
    print(json.dumps({"report": out + ".md", "claims": len(res["claims"]), **count, "summary": res.get("summary", "")}, indent=1))
