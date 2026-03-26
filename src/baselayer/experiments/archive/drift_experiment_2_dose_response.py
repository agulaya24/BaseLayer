"""
Drift Experiment 2: Dose-Response Curve

Tests whether behavioral drift is linear or sigmoidal as facts accumulate.
Injects 0, 1, 2, 3, 5 facts cumulatively into the axiom-format brief
and measures Specificity Ratio at each dose.

Key question: Do axioms compound, saturate, or phase-transition?

Usage:
  python drift_experiment_2_dose_response.py --ollama qwen2.5:7b           # Recommended (SR 2.55 in E1)
  python drift_experiment_2_dose_response.py --model claude-sonnet-4-20250514  # API
  python drift_experiment_2_dose_response.py --max-tokens 200              # Higher budget
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import embed_texts

# Import shared components from E1
from drift_experiment_1 import (
    BRIEFS,
    PROBES,
    SYSTEM_PROMPT,
    AXIOM_EXTRACTION_PROMPT,
    call_model,
    run_probes,
    extract_axioms,
    compute_probe_delta,
    compute_axiom_delta,
    inject_fact,
)

# ---------------------------------------------------------------------------
# DOSE FACTS — 5 facts targeting different dimensions, injected cumulatively
# ---------------------------------------------------------------------------

# Ordered for cumulative injection. Each adds a new behavioral lesson.
# Facts 1-2 target architecture (same dimension, tests compounding)
# Fact 3 targets debugging (new dimension, tests cross-dimension interaction)
# Facts 4-5 target architecture again (tests saturation)

DOSE_FACTS = [
    {
        "id": "D1-MICROSERVICE",
        "fact": "This person's team spent 2 months building a microservice architecture that should have been a single module with 3 functions. They now viscerally resist architectural complexity and will argue against any abstraction that isn't proven necessary by current production load.",
        "target_dimension": "architecture",
        "dose": 1,
    },
    {
        "id": "D2-PREMATURE-SCALE",
        "fact": "This person built a distributed cache with Redis Cluster for an app serving 200 requests/day. The infrastructure cost more to maintain than the app itself. They now refuse to design for scale that doesn't exist yet — prove the bottleneck with production data first.",
        "target_dimension": "architecture",
        "dose": 2,
    },
    {
        "id": "D3-SILENT-FAILURE",
        "fact": "This person's production system silently dropped 10% of events for a week because an error was caught and logged but not propagated. They now insist that every error path must either retry, escalate, or fail loudly — never silently continue.",
        "target_dimension": "debugging",
        "dose": 3,
    },
    {
        "id": "D4-ABSTRACTION-TAX",
        "fact": "This person inherited a codebase with 47 interfaces for 12 concrete implementations. Every change required updating 4 files. They now treat every abstraction as a tax — if it doesn't save effort across at least 3 call sites TODAY, delete it.",
        "target_dimension": "architecture",
        "dose": 4,
    },
    {
        "id": "D5-FRAMEWORK-LOCK",
        "fact": "This person's team adopted a cutting-edge ORM that was abandoned 8 months later. The migration cost more than the original build. They now choose technology based on maintenance ecosystem (contributors, releases, corporate backing) not features.",
        "target_dimension": "tradeoff",
        "dose": 5,
    },
    {
        "id": "D6-CONFIG-HELL",
        "fact": "This person spent a week debugging a production outage caused by a YAML config file where a boolean was parsed as a string. They now require all configuration to be validated through typed schemas at startup — the app crashes immediately if config is invalid, rather than failing mysteriously at runtime.",
        "target_dimension": "debugging",
        "dose": 6,
    },
    {
        "id": "D7-MONOLITH-SPLIT",
        "fact": "This person watched a team split a working monolith into 6 services 'for scalability' at 500 users. Deployment went from 1 command to 6, debugging required distributed tracing, and latency tripled from network hops. They now argue that monoliths are correct until you can prove a specific component needs independent scaling.",
        "target_dimension": "architecture",
        "dose": 7,
    },
    {
        "id": "D8-DRY-TRAP",
        "fact": "This person merged two 'similar' functions into one parameterized function with 8 boolean flags. Every bug fix in one caller's path broke the other. They now prefer explicit duplication over premature DRY — copy-paste is safer than wrong abstraction.",
        "target_dimension": "refactoring",
        "dose": 8,
    },
    {
        "id": "D9-PERF-GUESS",
        "fact": "This person spent 3 weeks optimizing a database query that turned out to account for 0.2% of total latency. The actual bottleneck was a synchronous HTTP call in a loop. They now refuse to optimize anything without profiler data showing it's in the top 3 hotspots.",
        "target_dimension": "tradeoff",
        "dose": 9,
    },
    {
        "id": "D10-MAGIC-MIDDLEWARE",
        "fact": "This person inherited an Express app with 14 middleware layers that mutated the request object. No one knew what state the request was in by the time it reached the handler. They now require that middleware be pure — read request, write response headers, but never mutate shared state.",
        "target_dimension": "architecture",
        "dose": 10,
    },
    {
        "id": "D11-TEST-MOCK",
        "fact": "This person's mocked tests passed for 6 months while the actual database schema had drifted. The first integration test caught 23 bugs. They now require at least one integration test per endpoint that hits the real database — mocks are for unit tests only.",
        "target_dimension": "debugging",
        "dose": 11,
    },
    {
        "id": "D12-CLEVER-CODE",
        "fact": "This person found a one-liner regex that replaced 40 lines of parsing logic. It worked perfectly until an edge case crashed production. The regex was undebuggable. They now ban 'clever' solutions — if a junior engineer can't understand it in 30 seconds, rewrite it as boring explicit code.",
        "target_dimension": "refactoring",
        "dose": 12,
    },
    {
        "id": "D13-ASYNC-EVERYWHERE",
        "fact": "This person made every function async 'for future-proofing.' The codebase became riddled with unnecessary awaits, promise chains, and race conditions in code that was purely synchronous. They now only use async at actual I/O boundaries — never speculatively.",
        "target_dimension": "architecture",
        "dose": 13,
    },
    {
        "id": "D14-LOG-FLOOD",
        "fact": "This person's logging was so verbose that the log aggregator cost more than the application infrastructure. When an actual incident occurred, the signal was buried in noise. They now enforce structured logging with severity levels — ERROR means wake someone up, WARN means investigate tomorrow, INFO means never page.",
        "target_dimension": "debugging",
        "dose": 14,
    },
    {
        "id": "D15-DEPENDENCY-BLOAT",
        "fact": "This person's project had 847 npm dependencies for a CRUD app. A single transitive dependency update broke the build for 2 days. They now audit every new dependency against three criteria: does it save more than 100 lines of code, is it actively maintained (commits in last 3 months), and does it have fewer than 5 transitive dependencies?",
        "target_dimension": "tradeoff",
        "dose": 15,
    },
]

# Dose levels to test
DOSE_LEVELS = [0, 1, 2, 3, 5, 8, 12, 15]


def run_dose_condition(model, use_ollama, base_brief, dose_level, max_tokens, t0_responses=None, t0_axioms=None):
    """Run one dose level. Returns results dict.

    If t0_responses/t0_axioms are provided, reuses them (dose=0 baseline).
    """
    facts_to_inject = DOSE_FACTS[:dose_level]
    fact_ids = [f["id"] for f in facts_to_inject]

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"  DOSE LEVEL: {dose_level} facts ({', '.join(fact_ids) if fact_ids else 'baseline'})", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)

    # Build injected brief
    brief = base_brief
    for fact in facts_to_inject:
        brief = inject_fact(brief, fact["fact"])

    result = {
        "dose": dose_level,
        "facts_injected": fact_ids,
        "brief_chars": len(brief),
    }

    # Run probes
    if dose_level == 0 and t0_responses is not None:
        print(f"  Reusing T0 baseline...", file=sys.stderr)
        responses = t0_responses
        axioms = t0_axioms
    else:
        start = time.time()
        responses = run_probes(brief, model, use_ollama, label=f"D{dose_level}", max_tokens=max_tokens)
        result["elapsed"] = round(time.time() - start, 1)

        print(f"  Extracting axioms...", file=sys.stderr)
        axioms = extract_axioms(responses, model, use_ollama)

    result["responses"] = responses
    result["axioms"] = axioms
    result["axiom_count"] = len(axioms)

    print(f"  Axioms extracted: {len(axioms)}", file=sys.stderr)
    for ax in axioms:
        if not ax.get("parse_error"):
            print(f"    - {ax.get('axiom', '???')[:80]}", file=sys.stderr)

    return result


def compute_dose_metrics(baseline, dose_results):
    """Compute drift metrics for each dose relative to baseline."""
    t0_responses = baseline["responses"]
    t0_axioms = baseline["axioms"]

    metrics = []
    for dose_result in dose_results:
        dose = dose_result["dose"]
        if dose == 0:
            metrics.append({
                "dose": 0,
                "probe_deltas": {pid: 0.0 for pid in PROBES},
                "axiom_delta": 0.0,
                "specificity_ratios": {},
            })
            continue

        # Probe deltas vs baseline
        probe_deltas = compute_probe_delta(t0_responses, dose_result["responses"])
        axiom_delta = compute_axiom_delta(t0_axioms, dose_result["axioms"])

        # Compute specificity ratio for each target dimension in the injected facts
        # At dose N, the target dimensions are determined by which facts were injected
        facts_injected = DOSE_FACTS[:dose]
        target_dims = set(f["target_dimension"] for f in facts_injected)

        specificity_ratios = {}
        if probe_deltas:
            for target in target_dims:
                target_d = probe_deltas.get(target, 0)
                others = [v for k, v in probe_deltas.items() if k not in target_dims]
                other_mean = round(sum(others) / len(others), 4) if others else 0
                sr = round(target_d / other_mean, 2) if other_mean > 0 else float('inf')
                specificity_ratios[target] = sr

        m = {
            "dose": dose,
            "probe_deltas": probe_deltas or {},
            "axiom_delta": axiom_delta.get("axiom_delta", 0) if isinstance(axiom_delta, dict) else 0,
            "specificity_ratios": specificity_ratios,
            "total_drift": sum((probe_deltas or {}).values()),
            "target_drift": sum(
                (probe_deltas or {}).get(dim, 0) for dim in target_dims
            ),
            "non_target_drift": sum(
                v for k, v in (probe_deltas or {}).items()
                if k not in target_dims
            ),
        }
        metrics.append(m)

    return metrics


def print_dose_summary(metrics):
    """Print dose-response curve to stderr."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"DOSE-RESPONSE CURVE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    print(f"\n{'Dose':<6} {'Total Drift':<13} {'Target':<10} {'Non-Target':<12} {'SR (arch)':<10} {'Axiom Δ':<10}", file=sys.stderr)
    print(f"{'-'*60}", file=sys.stderr)

    for m in metrics:
        dose = m["dose"]
        total = f"{m.get('total_drift', 0):.4f}"
        target = f"{m.get('target_drift', 0):.4f}"
        nontarget = f"{m.get('non_target_drift', 0):.4f}"
        sr_arch = m.get("specificity_ratios", {}).get("architecture", "—")
        if isinstance(sr_arch, float):
            sr_arch = f"{sr_arch:.2f}"
        axiom_d = f"{m.get('axiom_delta', 0):.4f}"

        print(f"{dose:<6} {total:<13} {target:<10} {nontarget:<12} {sr_arch:<10} {axiom_d:<10}", file=sys.stderr)

    # Detect curve shape
    totals = [m.get("total_drift", 0) for m in metrics]
    if len(totals) >= 3:
        diffs = [totals[i+1] - totals[i] for i in range(len(totals)-1)]

        # Check for phase transition: small diffs early, then large jump
        if len(diffs) >= 3:
            early_avg = sum(diffs[:2]) / 2
            late_avg = sum(diffs[2:]) / len(diffs[2:])

            if late_avg > early_avg * 2:
                print(f"\n  PATTERN: SIGMOIDAL — drift accelerates after dose {metrics[2]['dose']}", file=sys.stderr)
                print(f"  Early avg increment: {early_avg:.4f}, Late avg: {late_avg:.4f}", file=sys.stderr)
            elif all(d > 0 for d in diffs) and max(diffs) < min(diffs) * 3:
                print(f"\n  PATTERN: LINEAR — drift increases steadily", file=sys.stderr)
            elif diffs[-1] < diffs[0] * 0.5:
                print(f"\n  PATTERN: SATURATION — drift plateaus", file=sys.stderr)
            else:
                print(f"\n  PATTERN: IRREGULAR — no clear curve shape", file=sys.stderr)

    # Per-dimension breakdown
    print(f"\n  Per-dimension probe deltas by dose:", file=sys.stderr)
    print(f"  {'Dose':<6}", end="", file=sys.stderr)
    for pid in sorted(PROBES.keys()):
        print(f" {pid[:8]:<10}", end="", file=sys.stderr)
    print(file=sys.stderr)

    for m in metrics:
        print(f"  {m['dose']:<6}", end="", file=sys.stderr)
        for pid in sorted(PROBES.keys()):
            val = m.get("probe_deltas", {}).get(pid, 0)
            print(f" {val:.4f}   ", end="", file=sys.stderr)
        print(file=sys.stderr)


def run_experiment(args):
    use_ollama = args.ollama is not None
    model = args.ollama if use_ollama else args.model
    max_tokens = args.max_tokens

    output_dir = Path(os.path.dirname(__file__)) / "drift_results"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_tag = model.replace(":", "_").replace("/", "_")

    # Use axiom format (proven best in E1)
    base_brief = BRIEFS["axioms"]

    print(f"\nDRIFT EXPERIMENT 2: DOSE-RESPONSE", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)
    print(f"Brief format: axioms (proven best in E1)", file=sys.stderr)
    print(f"Dose levels: {DOSE_LEVELS}", file=sys.stderr)
    print(f"Max tokens: {max_tokens}", file=sys.stderr)
    print(f"Facts: {[f['id'] for f in DOSE_FACTS]}", file=sys.stderr)

    # Run baseline (dose=0) first
    baseline = run_dose_condition(model, use_ollama, base_brief, 0, max_tokens)

    # Run each dose level
    all_doses = [baseline]
    for dose in DOSE_LEVELS[1:]:  # Skip 0, already done
        dose_result = run_dose_condition(
            model, use_ollama, base_brief, dose, max_tokens,
            t0_responses=baseline["responses"],
            t0_axioms=baseline["axioms"],
        )
        all_doses.append(dose_result)

    # Compute metrics
    metrics = compute_dose_metrics(baseline, all_doses)

    # Print summary
    print_dose_summary(metrics)

    # Save
    results = {
        "experiment": "drift_experiment_2_dose_response",
        "timestamp": timestamp,
        "model": model,
        "backend": "ollama" if use_ollama else "anthropic",
        "max_tokens": max_tokens,
        "brief_format": "axioms",
        "dose_levels": DOSE_LEVELS,
        "facts": [{"id": f["id"], "fact": f["fact"], "target": f["target_dimension"]} for f in DOSE_FACTS],
        "doses": [],
        "metrics": metrics,
    }

    for dose_result in all_doses:
        # Strip full responses for file size (keep response text only)
        slim = {
            "dose": dose_result["dose"],
            "facts_injected": dose_result["facts_injected"],
            "brief_chars": dose_result["brief_chars"],
            "axiom_count": dose_result["axiom_count"],
            "axioms": dose_result["axioms"],
            "responses": {
                pid: {
                    "response": data["response"],
                    "tokens_out": data["tokens_out"],
                    "elapsed": data.get("elapsed", 0),
                }
                for pid, data in dose_result["responses"].items()
            },
        }
        if "elapsed" in dose_result:
            slim["elapsed"] = dose_result["elapsed"]
        results["doses"].append(slim)

    outfile = output_dir / f"drift_exp2_dose_{model_tag}_{timestamp}.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to {outfile}", file=sys.stderr)
    return results


def main():
    parser = argparse.ArgumentParser(description="Drift Experiment 2: Dose-Response Curve")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model")
    parser.add_argument("--ollama", type=str, default=None, help="Ollama model name (e.g. qwen2.5:7b)")
    parser.add_argument("--max-tokens", type=int, default=200, help="Max output tokens per probe")
    args = parser.parse_args()
    run_experiment(args)


if __name__ == "__main__":
    main()
