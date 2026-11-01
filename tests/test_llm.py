"""docgen/llm.py (the Claude call wrapper and the job's token ledger) and docgen/wait.py, against a fake `claude`. Spends nothing.
Run: .venv/bin/python tests/test_llm.py"""
import json, os, stat, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from docgen import llm

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

tmp = tempfile.mkdtemp(); os.chdir(tmp)

# Prices: Sonnet 5.5 is $2 in, $10 out, $0.20 cache read; cache writes 1.25x (5 m) and 2x (1 h) input.
t = llm.tokens({"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 10_000_000,
                "cache_creation_input_tokens": 300_000, "cache_creation": {"ephemeral_1h_input_tokens": 100_000}})
check("usage flattened, 1 h writes split out", t == {"input": 1_000_000, "output": 100_000, "cache_read": 10_000_000, "cache_write_5m": 200_000, "cache_write_1h": 100_000}, t)
check("usd from list prices (Sonnet 5.5 cache reads at $0.10)", abs(llm.usd("claude-sonnet-5-5", t) - (2 + 1 + 1 + 0.5 + 0.4)) < 1e-9, llm.usd("claude-sonnet-5-5", t))
check("unknown model priced as Sonnet", llm.usd("claude-new-thing", t) == llm.usd("claude-sonnet-5-5", t))

# The producer's stream: calls streamed in several lines (same id), a thinking progress event, a half-written line, then the
# run's result line, then a resumed run whose result line carries the session's running totals.
def ev(i, text="", w=0): return json.dumps({"type": "assistant", "message": {"id": f"m{i}", "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 100, "output_tokens": 2, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": w}}})
def res(cum_out, cost, sid="s1"): return json.dumps({"type": "result", "session_id": sid, "num_turns": 3, "total_cost_usd": cost, "modelUsage": {
    "claude-sonnet-5-5": {"inputTokens": 300, "outputTokens": cum_out, "cacheReadInputTokens": 3000, "cacheCreationInputTokens": 500, "costUSD": cost - 0.01},
    "claude-haiku-5-5": {"inputTokens": 50, "outputTokens": 5, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "costUSD": 0.01}},
    "usage": {"cache_creation": {"ephemeral_1h_input_tokens": 400}}})
think = json.dumps({"type": "system", "subtype": "thinking_tokens", "estimated_tokens_delta": 150})
open("runner.jsonl", "w").write("\n".join([ev(1, "x" * 400), ev(1, "y" * 400), think, ev(2, "z" * 80, w=20_000), json.dumps({"type": "user", "usage": "x"})]) + "\n" + ev(3)[:30])
tot = llm.Meter(tmp).poll(); p = tot["by_step"]["producer"]
check("live: one call per message id, output estimated from the text written and the thinking events", p["calls"] == 2 and p["input"] == 200
      and p["output"] == 100 + 100 + 150 + 20 and p["cache_write_5m"] == 20_000 and not p["exact"], p)
with open("runner.jsonl", "a") as f: f.write(ev(3)[30:] + "\n" + res(900, 0.50) + "\n")
tot = llm.Meter(tmp).poll(); p = tot["by_step"]["producer"]
check("result line: exact session totals replace the estimate, Haiku included, 1-hour writes split out", p["exact"] and p["output"] == 905 and p["input"] == 350
      and p["cache_write_1h"] == 400 and p["cache_write_5m"] == 100 and abs(p["usd"] - 0.50) < 1e-9 and p["calls"] == 3, p)
with open("runner.jsonl", "a") as f: f.write(ev(4, "w" * 40) + "\n")
tot = llm.Meter(tmp).poll()
check("a resumed run counts on top of the session until its own result line", tot["by_step"]["producer"]["calls"] == 4 and tot["usd"] > 0.50, tot["by_step"]["producer"])
with open("runner.jsonl", "a") as f: f.write(res(1500, 0.80) + "\n")
llm.log_call("analyst/qa", "claude-sonnet-5-5", {"usage": {"input_tokens": 7, "output_tokens": 3}, "total_cost_usd": 0.5, "num_turns": 4})
tot = llm.Meter(tmp).poll(); p = tot["by_step"]["producer"]
check("the resumed run's result line is the session's running total, not added to the first", abs(p["usd"] - 0.80) < 1e-9 and p["output"] == 1505
      and p["calls"] == 4 and abs(tot["usd"] - 1.30) < 1e-9 and tot["by_step"]["analyst/qa"]["usd"] == 0.5, tot)
s = llm.summary(tmp)
check("summary for the status object", s["usd_estimate"] == 1.3 and s["by_step"]["producer"]["exact"] and set(s["by_step"]) == {"producer", "analyst/qa"}, s)

# run(): the flags it passes, the log line, and a stop at the USD cap.
bin_ = os.path.join(tmp, "bin"); os.makedirs(bin_)
fake = os.path.join(bin_, "claude")
open(fake, "w").write("#!" + sys.executable + "\nimport json, os, sys\njson.dump(sys.argv[1:], open(os.environ['ARGS_OUT'], 'w'))\n"
                      "print(json.dumps({'type': 'result', 'subtype': os.environ.get('SUB', 'success'), 'result': 'hello' if os.environ.get('SUB') is None else '',"
                      " 'total_cost_usd': 0.25, 'num_turns': 2, 'usage': {'input_tokens': 10, 'output_tokens': 5}}))\n")
os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
os.environ["PATH"] = bin_ + os.pathsep + os.environ["PATH"]; os.environ["ARGS_OUT"] = os.path.join(tmp, "args.json")
open(llm.CALLS, "w").close()
r = llm.run("prompt", "claude-sonnet-5-5", "analyst/research", tools="Read Glob WebSearch", max_turns=40, max_usd=5)
a = json.load(open(os.environ["ARGS_OUT"]))
check("run: reply text returned", r == "hello", r)
check("run: only the named tools are loaded and allowed, with the USD cap and the shared prefix", a[a.index("--tools") + 1] == "Read,Glob,WebSearch"
      and a[a.index("--allowedTools") + 1:a.index("--allowedTools") + 4] == ["Read", "Glob", "WebSearch"] and a[a.index("--max-budget-usd") + 1] == "5"
      and "--exclude-dynamic-system-prompt-sections" in a, a)
rec = json.loads(open(llm.CALLS).read().splitlines()[-1])
check("run: session logged with its reported cost", rec["step"] == "analyst/research" and rec["usd"] == 0.25 and rec["input"] == 10, rec)
os.environ["ENABLE_PROMPT_CACHING_1H"] = "1"
src = open(fake).read().replace("json.dump(sys.argv[1:]", "json.dump(sys.argv[1:] + ['ENV1H=' + os.environ.get('ENABLE_PROMPT_CACHING_1H', '')]"); open(fake, "w").write(src)
llm.run("p", "claude-opus-5-5", "scene3d", tools="", max_turns=2, effort="medium")
a = json.load(open(os.environ["ARGS_OUT"]))
check("run: effort passed; the producer's 1-hour cache setting is not inherited", a[a.index("--effort") + 1] == "medium" and a[-1] == "ENV1H=", a)
check("run: no tools means no tool definitions at all", a[a.index("--tools") + 1] == "" and "--allowedTools" not in a and "--max-budget-usd" not in a, a)
os.environ["SUB"] = "error_max_budget_usd"
try: llm.run("p", "claude-sonnet-5-5", "analyst/qa", max_usd=1); check("run: stop at the cap raises", False)
except RuntimeError as e: check("run: stop at the cap raises", "cap" in str(e), e)
del os.environ["SUB"]

# wait: ready, exited (the background job died without writing its file), waiting (timeout).
W = [sys.executable, "-m", "docgen", "wait"]; env = dict(os.environ, PYTHONPATH=ROOT)
bg = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1); open('done.json', 'w').write('{}')"])
t0 = time.time(); p = subprocess.run(W + ["done.json", "--pid", str(bg.pid)], capture_output=True, text=True, env=env)
check("wait: returns when the file appears", p.returncode == 0 and json.loads(p.stdout)["result"] == "ready" and time.time() - t0 < 10, p.stdout + p.stderr)
bg = subprocess.Popen([sys.executable, "-c", "pass"]); bg.wait()
p = subprocess.run(W + ["never.json", "--pid", str(bg.pid)], capture_output=True, text=True, env=env)
check("wait: says so when the process exited without the file", p.returncode == 1 and json.loads(p.stdout)["result"] == "exited", p.stdout + p.stderr)
p = subprocess.run(W + ["never.json", "--timeout", "1"], capture_output=True, text=True, env=env)
check("wait: times out with 'waiting'", p.returncode == 2 and json.loads(p.stdout)["missing"] == ["never.json"], p.stdout + p.stderr)

print("\nALL PASSED" if not fails else f"\n{fails} FAILED"); sys.exit(1 if fails else 0)
