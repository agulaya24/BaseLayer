"""Dated price table and the estimate printed before any model step runs.

Rates are first-party API list prices per million tokens, taken from the Anthropic
model table as cached on 2026-06-24 (claude-api skill). They are DATED, not
authoritative: re-check before quoting a number to anyone. Cache reads are 0.1x
input. For `claude -p` the estimate is COUNTERFACTUAL (what the calls would cost at
API rates); the subscription run itself bills nothing.

Each `claude -p` call also carries the CLI's own system prompt, measured on this
project at about 26K-30K tokens (mostly cache reads). That overhead is added per
call on the CLI route and is the reason a small prompt is not a cheap call.
"""
from __future__ import annotations

PRICES_AS_OF = "2026-06-24"
PRICES = {  # model: (input, output) USD per million tokens
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
ALIASES = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}
CACHE_READ_FACTOR = 0.10
CLI_OVERHEAD_TOKENS = 28_000
CHARS_PER_TOKEN = 3.5
# Output per call is dominated by thinking and varies by model and task. 6K is the
# default assumption; a prototype run on sonnet measured about $0.079 per call
# counterfactual, which this assumption reproduces within about 20%.
DEFAULT_OUTPUT_TOKENS = 6_000


def resolve(model: str) -> str:
    return ALIASES.get(model, model)


def estimate(tasks_by_kind: dict[str, list[dict]], model: str, route: str,
             output_tokens: int = DEFAULT_OUTPUT_TOKENS, phase2_bound: int = 0, phase2_expected: int = 0,
             phase2_mean_chars: int = 6000) -> dict:
    m = resolve(model)
    if m not in PRICES:
        return {"model": m, "error": f"no dated price for {m!r}; known: {sorted(PRICES)}"}
    pin, pout = PRICES[m]
    rows, total_calls, total = [], 0, 0.0

    def cost(n_calls, chars):
        tin = chars / CHARS_PER_TOKEN
        c = tin * pin / 1e6 + n_calls * output_tokens * pout / 1e6
        if route == "cli":
            c += n_calls * CLI_OVERHEAD_TOKENS * pin * CACHE_READ_FACTOR / 1e6
        return c
    for kind, ts in tasks_by_kind.items():
        chars = sum(len(t["prompt"]) for t in ts)
        c = cost(len(ts), chars)
        rows.append({"kind": kind, "calls": len(ts), "prompt_chars": chars, "usd": round(c, 2)})
        total_calls += len(ts)
        total += c
    p2 = cost(phase2_bound, phase2_bound * phase2_mean_chars) if phase2_bound else 0.0
    p2e = cost(phase2_expected, phase2_expected * phase2_mean_chars) if phase2_expected else 0.0
    rows.append({"kind": "adjudicate (phase 2, expected)", "calls": phase2_expected, "prompt_chars": phase2_expected * phase2_mean_chars,
                 "usd": round(p2e, 2), "note": "about one pair per claim, as the prototype observed on two specs"})
    rows.append({"kind": "adjudicate (phase 2, upper bound)", "calls": phase2_bound, "prompt_chars": phase2_bound * phase2_mean_chars,
                 "usd": round(p2, 2), "note": "every cited fact judged contradicts; depends on phase 1, so a bound, not a count"})
    return {"model": m, "route": route, "prices_as_of": PRICES_AS_OF, "rates_usd_per_mtok": {"input": pin, "output": pout},
            "assumed_output_tokens_per_call": output_tokens,
            "cli_overhead_tokens_per_call": CLI_OVERHEAD_TOKENS if route == "cli" else 0,
            "rows": rows, "phase1_calls": total_calls, "phase1_usd": round(total, 2),
            "total_expected_usd": round(total + p2e, 2), "total_upper_usd": round(total + p2, 2),
            "billing": ("counterfactual only: claude -p on the subscription bills nothing" if route == "cli"
                        else "API credits: this is real spend")}


def format_estimate(e: dict) -> str:
    if "error" in e:
        return f"price estimate unavailable: {e['error']}"
    lines = [f"Model-judged steps, estimate ({e['model']}, route {e['route']}, prices as of {e['prices_as_of']}; {e['billing']}):"]
    for r in e["rows"]:
        lines.append(f"  {r['kind']:<36} {r['calls']:>5} calls  ~${r['usd']:.2f}")
    lines.append(f"  phase 1: {e['phase1_calls']} calls ~${e['phase1_usd']:.2f}; with expected phase 2 ~${e['total_expected_usd']:.2f}; "
                 f"with the phase-2 upper bound ~${e['total_upper_usd']:.2f}")
    lines.append(f"  assumes {e['assumed_output_tokens_per_call']} output tokens per call"
                 + (f" and {e['cli_overhead_tokens_per_call']} CLI system-prompt tokens per call" if e["cli_overhead_tokens_per_call"] else ""))
    return "\n".join(lines)
