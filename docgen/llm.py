"""Every Claude call docgen makes, and what it costs. The producer session is started by the API server (api/server.py); the analysts
and the 3D planner call run() below. Nothing else starts a Claude session.

run(): one fresh `claude -p` session, with only the tools it needs loaded (--tools, so the unused tool definitions are not resent on
  every turn), the per-machine part of the system prompt moved out of it (so jobs share the cached prefix), a USD cap of its own
  (--max-budget-usd: a fresh session, so the cap is unambiguous), and its token usage appended to llm_calls.jsonl in the run folder.

Meter: the job's token and USD ledger, kept in llm_usage.json. It reads the producer's stream (runner.jsonl) and llm_calls.jsonl
  incrementally, so it can run every second. The server stops a job whose figure passes DOCGEN_MAX_LLM_USD: a runaway loop costs
  the cap, not the account balance.
  - Exact: each run of the producer ends with a `result` line carrying Claude Code's own totals for the SESSION (all models, the
    Haiku it uses for web fetches included, and its list-price cost). A resumed session's totals include its earlier runs, so the
    latest result line per session is the producer's figure, never a sum of them.
  - Live, between result lines: the per-call usage lines. Their input and cache counts are exact, but their output count is taken
    before the call finishes, so output is estimated from the text and tool input written (4 characters a token) plus the
    `thinking_tokens` progress events. Good enough for the cap; replaced by the exact figure at the run's end.

USD figures are list prices (standard tier); the Console is the bill.

Env: DOCGEN_MAX_LLM_USD (15; 0 = no cap) per explainer job and DOCGEN_MAX_LLM_USD_DOCUMENTARY (30) per documentary job, all
     sessions together. DOCGEN_ANALYST_MAX_USD (2: the Thumbnail Analyst, the Fact Checker) and DOCGEN_SCENE3D_MAX_USD (2) per session.
     DOCGEN_CLAUDE_TOOLS: the producer's built-in tools (Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch); --tools does not limit
     MCP tools, so the Storyblocks tools stay available through the MCP config and --allowedTools.
     The producer runs with the 1-hour prompt cache (ENABLE_PROMPT_CACHING_1H, set by the server): its long commands (asset queues,
     the assemble, thumbnail generation) outlast the 5-minute cache, and each expiry rewrites the whole context (infogen measured
     806K of 988K written tokens from such rewrites on 2026-11-01; docs in storystudio-infographics/docs/CLAUDE_TOKEN_COST.md).
     The short analyst and planner sessions keep the 5-minute cache, which costs less to write."""
import json, os, subprocess, time

USAGE, CALLS = "llm_usage.json", "llm_calls.jsonl"
PRODUCER_TOOLS = os.environ.get("DOCGEN_CLAUDE_TOOLS", "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch")
COMMON = ["--exclude-dynamic-system-prompt-sections"]   # cwd, env and git status go into the first user message instead

# $ per million tokens: input, output, cache read. Cache writes are 1.25x input (5 minutes) and 2x input (1 hour). Only used for the
# live estimate between result lines. Sonnet 5.5's cache read rate is the one Claude Code charged on 2026-11-01 ($0.10).
PRICES = {"claude-fable-5-1": (10, 50, 0.25), "claude-fable-5": (10, 50, 0.25), "claude-opus-5-5": (4, 20, 0.20), "claude-opus-5": (5, 25, 0.50),
          "claude-opus-4-8": (5, 25, 0.50), "claude-sonnet-5-5": (2, 10, 0.10), "claude-sonnet-5": (2, 10, 0.20), "claude-sonnet-4-6": (3, 15, 0.30),
          "claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-haiku-4-5": (1, 5, 0.10)}
KEYS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")

def max_job_usd(fmt="explainer"):
    if fmt == "documentary": return float(os.environ.get("DOCGEN_MAX_LLM_USD_DOCUMENTARY", "30") or 0)
    return float(os.environ.get("DOCGEN_MAX_LLM_USD", "15") or 0)

def tokens(u):
    """A Messages API usage object as flat counts."""
    u = u or {}; cw = u.get("cache_creation") or {}
    w1h = cw.get("ephemeral_1h_input_tokens", 0) or 0
    w = u.get("cache_creation_input_tokens", 0) or 0
    return {"input": u.get("input_tokens", 0) or 0, "output": u.get("output_tokens", 0) or 0, "cache_read": u.get("cache_read_input_tokens", 0) or 0,
            "cache_write_5m": max(w - w1h, 0), "cache_write_1h": w1h}

def usd(model, t):
    base = next((p for k, p in PRICES.items() if (model or "").startswith(k)), PRICES["claude-sonnet-5-5"])
    i, o, r = base
    return (t["input"] * i + t["output"] * o + t["cache_read"] * r + t["cache_write_5m"] * i * 1.25 + t["cache_write_1h"] * i * 2) / 1e6

def log_call(step, model, res, cwd="."):
    """Append one finished session (the JSON of `claude -p --output-format json`) to llm_calls.jsonl."""
    t = tokens(res.get("usage"))
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "step": step, "model": model, **t,
           "usd": res["total_cost_usd"] if isinstance(res.get("total_cost_usd"), (int, float)) else round(usd(model, t), 4),
           "turns": res.get("num_turns"), "subtype": res.get("subtype")}
    with open(os.path.join(cwd, CALLS), "a") as f: f.write(json.dumps(rec) + "\n")
    return rec

def run(text, model, step, tools="", max_turns=40, max_usd=None, timeout=1800, effort=None):
    """The reply text of one fresh session. `tools`: space- or comma-separated built-in tool names, "" for none. `effort`: low,
    medium, high, xhigh or max (None = the model's default). Raises RuntimeError when the session stopped at its USD cap or its
    turn limit without replying."""
    names = [x for x in tools.replace(",", " ").split() if x]
    cmd = ["claude", "-p", text, "--model", model, "--output-format", "json", "--max-turns", str(max_turns), "--tools", ",".join(names), *COMMON]
    if names: cmd += ["--allowedTools", *names]
    if max_usd: cmd += ["--max-budget-usd", str(max_usd)]
    if effort: cmd += ["--effort", effort]
    env = {k: v for k, v in os.environ.items() if k != "ENABLE_PROMPT_CACHING_1H"}   # inherited from the producer; a short session gains nothing from it
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    try: res = json.loads(out.stdout)
    except Exception: return out.stdout
    if not isinstance(res, dict): return out.stdout
    try: log_call(step, model, res)
    except Exception: pass                                  # the ledger must never fail the work
    sub = res.get("subtype") or ""
    if sub == "error_max_budget_usd": raise RuntimeError(f"{step}: stopped at its ${max_usd} cap before replying")
    if sub == "error_max_turns" and not res.get("result"): raise RuntimeError(f"{step}: stopped at {max_turns} turns before replying")
    return res.get("result", "")

def empty():
    return {"usd": 0.0, "input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "calls": 0, "by_step": {}}

def zero(): return {"usd": 0.0, "calls": 0, **{k: 0 for k in KEYS}}

def add(tot, t, cost, calls=1):
    for k in KEYS: tot[k] += t.get(k, 0)
    tot["usd"] = round(tot["usd"] + cost, 6); tot["calls"] += calls

def from_result(ev):
    """A producer `result` line as session totals: every model in modelUsage, with Claude Code's own cost."""
    t = zero(); mu = ev.get("modelUsage") or {}
    for m in mu.values():
        add(t, {"input": m.get("inputTokens", 0) or 0, "output": m.get("outputTokens", 0) or 0, "cache_read": m.get("cacheReadInputTokens", 0) or 0,
                "cache_write_5m": m.get("cacheCreationInputTokens", 0) or 0}, m.get("costUSD", 0) or 0, calls=0)
    cw = (ev.get("usage") or {}).get("cache_creation") or {}
    if cw.get("ephemeral_1h_input_tokens") and mu:          # the per-model split has no 5m/1h detail; the session usage does
        h = min(cw["ephemeral_1h_input_tokens"], t["cache_write_5m"]); t["cache_write_1h"] = h; t["cache_write_5m"] -= h
    if not mu: t["usd"] = ev.get("total_cost_usd") or 0.0
    t["turns"] = ev.get("num_turns"); return t

class Meter:
    """The job's ledger. poll() folds in what was appended to runner.jsonl and llm_calls.jsonl since the last poll and saves it."""
    def __init__(self, run_dir):
        self.dir = run_dir; self.path = os.path.join(run_dir, USAGE)
        try: st = json.load(open(self.path))
        except Exception: st = {}
        self.off = st.get("offsets") or {}
        self.sessions = st.get("sessions") or {}          # producer session id -> totals from its latest result line
        self.live = st.get("live") or zero()              # producer calls since the latest result line (estimate)
        self.steps = st.get("steps") or {}                # analysts and planners, from llm_calls.jsonl
        self.seen = {}                                    # message id -> counts already added to live
    def lines(self, name):
        p = os.path.join(self.dir, name)
        try:
            with open(p, "rb") as f:
                f.seek(self.off.get(name, 0)); data = f.read()
        except FileNotFoundError: return []
        end = data.rfind(b"\n") + 1                       # a half-written last line waits for the next poll
        self.off[name] = self.off.get(name, 0) + end
        return data[:end].decode("utf-8", "replace").splitlines()
    def live_add(self, model, t, calls):
        add(self.live, t, usd(model, {k: t.get(k, 0) for k in KEYS}), calls)
    def poll(self):
        for line in self.lines("runner.jsonl"):
            if '"usage"' not in line and '"thinking_tokens"' not in line and '"result"' not in line: continue
            try: ev = json.loads(line)
            except ValueError: continue
            typ = ev.get("type")
            if typ == "result":
                sid = ev.get("session_id") or "?"; t = from_result(ev)
                t["calls"] = self.sessions.get(sid, {}).get("calls", 0) + self.live["calls"]   # API calls: the result line has turns, not calls
                self.sessions[sid] = t; self.live = zero(); self.seen = {}
            elif typ == "system" and ev.get("subtype") == "thinking_tokens":
                self.live_add("claude-sonnet-5-5", {"output": ev.get("estimated_tokens_delta", 0) or 0}, 0)
            elif typ == "assistant" and isinstance(ev.get("message"), dict) and ev["message"].get("usage"):
                m = ev["message"]; t = tokens(m["usage"])
                written = sum(len(b.get("text") or "") + len(json.dumps(b.get("input"))) if b.get("type") == "tool_use" else len(b.get("text") or "")
                              for b in m.get("content") or [] if isinstance(b, dict))
                t["output"] = max(t["output"], 0); est = written // 4
                prev = self.seen.get(m.get("id"))
                if prev is None:
                    self.live_add(m.get("model"), {**t, "output": max(t["output"], est)}, 1); self.seen[m.get("id")] = {**t, "output": max(t["output"], est)}
                else:                                     # the same call again (one line per content block): add what grew
                    new = {**{k: max(t[k], prev[k]) for k in KEYS if k != "output"}, "output": prev["output"] + est}
                    self.live_add(m.get("model"), {k: max(new[k] - prev[k], 0) for k in KEYS}, 0); self.seen[m["id"]] = new
        for line in self.lines(CALLS):
            try: r = json.loads(line)
            except ValueError: continue
            add(self.steps.setdefault(r.get("step", "other"), zero()), {k: r.get(k, 0) or 0 for k in KEYS}, r.get("usd", 0) or 0)
        tmp = self.path + ".tmp"
        json.dump({"total": self.total(), "offsets": self.off, "sessions": self.sessions, "live": self.live, "steps": self.steps}, open(tmp, "w"), indent=1); os.replace(tmp, self.path)
        return self.total()
    def total(self):
        prod = zero()
        for t in self.sessions.values(): add(prod, t, t["usd"], t.get("calls", 0))
        add(prod, self.live, self.live["usd"], self.live["calls"])
        prod["exact"] = not self.live["calls"]
        tot = empty(); tot["by_step"]["producer"] = prod
        for name, t in [("producer", prod)] + sorted(self.steps.items()):
            add(tot, t, t["usd"], t.get("calls", 0))
            if name != "producer": tot["by_step"][name] = dict(t)
        return tot

def summary(run_dir):
    """The ledger as saved, for the status object: totals, and per step (cache writes 5-minute and 1-hour together)."""
    try: t = json.load(open(os.path.join(run_dir, USAGE)))["total"]
    except Exception: return None
    step = lambda s: {"usd": round(s["usd"], 4), "input": s["input"], "output": s["output"], "cache_read": s["cache_read"],
                      "cache_write": s["cache_write_5m"] + s["cache_write_1h"], "calls": s["calls"], **({"exact": s["exact"]} if "exact" in s else {})}
    return {"usd_estimate": round(t["usd"], 2), "calls": t["calls"], "input": t["input"], "output": t["output"], "cache_read": t["cache_read"],
            "cache_write": t["cache_write_5m"] + t["cache_write_1h"], "cache_write_1h": t["cache_write_1h"], "by_step": {k: step(v) for k, v in t["by_step"].items()}}
