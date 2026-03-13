#!/usr/bin/env python3
"""Analyze axiom benchmark results: McNemar's test, subgroup analysis, final report."""
import json
import glob
import os
import sys
from datetime import datetime
from math import comb
from pathlib import Path

# Directory containing this script (data/swebench/)
_SWEBENCH_DIR = Path(__file__).parent

# External OpenHands benchmarks directory.
# Override with OPENHANDS_BENCHMARKS_DIR env var when running on a different machine.
# Default assumes WSL path; set env var for Windows-native or other layouts.
_OPENHANDS_DIR = Path(os.environ.get(
    "OPENHANDS_BENCHMARKS_DIR",
    "/home/agulaya/openhands-benchmarks"
))


def load_eval_results(eval_dir):
    """Load evaluation results from output.report.json file."""
    # Try both naming conventions
    for name in ["output.report.json", "report.json"]:
        report_path = os.path.join(eval_dir, name)
        if os.path.exists(report_path):
            with open(report_path) as f:
                return json.load(f)
    return None


def find_output_dir(base_dir, note_pattern):
    """Find the output directory matching a note pattern."""
    pattern = os.path.join(base_dir, "princeton-nlp__SWE-bench_Verified-test", "anthropic", f"*{note_pattern}*")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def get_resolved_ids(report):
    """Get set of resolved instance IDs from a report."""
    if not report:
        return set()
    return set(report.get("resolved_ids", []))


def mcnemar_test(c0_resolved, cx_resolved, all_ids):
    """Run McNemar's test comparing two conditions."""
    a = len(c0_resolved & cx_resolved)
    b = len(c0_resolved - cx_resolved)  # C0 solved, CX didn't
    c = len(cx_resolved - c0_resolved)  # CX solved, C0 didn't
    d = len(all_ids - c0_resolved - cx_resolved)

    n = b + c  # discordant pairs
    if n == 0:
        return {"a": a, "b": b, "c": c, "d": d, "n_discordant": 0,
                "chi2": 0, "p_value": 1.0, "significant_005": False, "significant_0025": False}

    # McNemar's chi-squared (with continuity correction)
    chi2 = (abs(b - c) - 1) ** 2 / n if n > 0 else 0

    # Exact binomial p-value (two-sided)
    larger = max(b, c)
    p_one = sum(comb(n, k) * (0.5 ** n) for k in range(larger, n + 1))
    p_value = min(2 * p_one, 1.0)

    return {
        "a": a, "b": b, "c": c, "d": d,
        "n_discordant": n,
        "chi2": round(chi2, 4),
        "p_value": round(p_value, 6),
        "significant_005": p_value < 0.05,
        "significant_0025": p_value < 0.025
    }


def main():
    base_dir = str(_OPENHANDS_DIR / "eval_outputs")

    # Load problem list
    with open(_OPENHANDS_DIR / "selected_django_30.txt") as f:
        all_ids = set(line.strip() for line in f if line.strip())

    # Load axiom relevance ratings
    ratings_path = _SWEBENCH_DIR / "axiom_relevance_ratings.json"
    ratings = {}
    if os.path.exists(ratings_path):
        with open(ratings_path) as f:
            data = json.load(f)
            for r in data["ratings"]:
                ratings[r["instance_id"]] = r["relevance_score"]

    high_relevance = {iid for iid, score in ratings.items() if score >= 3}
    low_relevance = {iid for iid, score in ratings.items() if score < 3}

    # Find all condition results
    conditions_to_find = {
        "hard_C0": ["phase_a_hard_C0", "hard_C0"],
        "hard_C1": ["hard_C1"],
        "hard_C2": ["hard_C2"],
        "hard_C3": ["hard_C3"],
        "hard_C4": ["hard_C4"],
        "hard_C5": ["hard_C5"],
        "hard_C7": ["hard_C7"],
    }

    results = {}
    for cond, names in conditions_to_find.items():
        out_dir = None
        for name in names:
            out_dir = find_output_dir(base_dir, name)
            if out_dir:
                break

        if out_dir:
            report = load_eval_results(out_dir)
            if report:
                resolved = get_resolved_ids(report)
                results[cond] = {
                    "dir": out_dir,
                    "resolved": resolved,
                    "solve_rate": len(resolved) / len(all_ids),
                    "n_solved": len(resolved),
                    "n_total": len(all_ids)
                }
                print(f"{cond}: {len(resolved)}/{len(all_ids)} = {len(resolved)/len(all_ids)*100:.1f}%")
            else:
                print(f"{cond}: found dir but no report.json at {out_dir}")
        else:
            print(f"{cond}: output directory not found")

    c0_key = "hard_C0"
    if c0_key not in results:
        print("ERROR: C0 baseline not found!")
        sys.exit(1)

    c0_resolved = results[c0_key]["resolved"]

    print("\n" + "=" * 60)
    print("STATISTICAL ANALYSIS")
    print("=" * 60)

    analysis = {"timestamp": datetime.now().isoformat(), "conditions": {}, "mcnemar": {}, "subgroup": {}}

    # Overall results
    for cond, data in sorted(results.items()):
        analysis["conditions"][cond] = {
            "n_solved": data["n_solved"],
            "n_total": data["n_total"],
            "solve_rate": round(data["solve_rate"], 4)
        }

    # McNemar tests vs C0
    for cond, data in sorted(results.items()):
        if cond == c0_key:
            continue
        test = mcnemar_test(c0_resolved, data["resolved"], all_ids)
        analysis["mcnemar"][f"{cond}_vs_C0"] = test
        sig = "***" if test["significant_005"] else ""
        print(f"\n{cond} vs C0: chi2={test['chi2']}, p={test['p_value']}{sig}")
        print(f"  C0 only: {test['b']}, {cond} only: {test['c']}, both: {test['a']}, neither: {test['d']}")

    # C2 vs C4 (format test)
    if "hard_C2" in results and "hard_C4" in results:
        test = mcnemar_test(results["hard_C2"]["resolved"], results["hard_C4"]["resolved"], all_ids)
        analysis["mcnemar"]["C2_vs_C4"] = test
        print(f"\nC2 vs C4 (format): chi2={test['chi2']}, p={test['p_value']}")

    # C2 vs C3 (domain specificity)
    if "hard_C2" in results and "hard_C3" in results:
        test = mcnemar_test(results["hard_C2"]["resolved"], results["hard_C3"]["resolved"], all_ids)
        analysis["mcnemar"]["C2_vs_C3"] = test
        print(f"C2 vs C3 (domain): chi2={test['chi2']}, p={test['p_value']}")

    # Subgroup analysis
    print("\n" + "=" * 60)
    print(f"SUBGROUP: HIGH-RELEVANCE PROBLEMS (score >= 3, N={len(high_relevance)})")
    print("=" * 60)

    for cond, data in sorted(results.items()):
        hr_solved = data["resolved"] & high_relevance
        hr_total = high_relevance & all_ids
        rate = len(hr_solved) / len(hr_total) if hr_total else 0
        lr_solved_n = len(data["resolved"] & low_relevance)
        lr_total_n = len(low_relevance & all_ids)
        lr_rate = lr_solved_n / lr_total_n if lr_total_n else 0
        analysis["subgroup"][cond] = {
            "high_rel_solved": len(hr_solved),
            "high_rel_total": len(hr_total),
            "high_rel_rate": round(rate, 4),
            "low_rel_solved": lr_solved_n,
            "low_rel_total": lr_total_n,
            "low_rel_rate": round(lr_rate, 4),
        }
        print(f"{cond}: high-rel {len(hr_solved)}/{len(hr_total)} ({rate*100:.1f}%), low-rel {lr_solved_n}/{lr_total_n} ({lr_rate*100:.1f}%)")

    # McNemar on high-relevance subgroup
    if "hard_C2" in results:
        c0_hr = c0_resolved & high_relevance
        c2_hr = results["hard_C2"]["resolved"] & high_relevance
        test = mcnemar_test(c0_hr, c2_hr, high_relevance & all_ids)
        analysis["mcnemar"]["C2_vs_C0_high_relevance"] = test
        print(f"\nC2 vs C0 (high-relevance only): chi2={test['chi2']}, p={test['p_value']}")

    # Per-instance comparison: C2 vs C0
    print("\n" + "=" * 60)
    print("PER-INSTANCE: C2 vs C0")
    print("=" * 60)

    if "hard_C2" in results:
        c2_resolved = results["hard_C2"]["resolved"]
        per_instance = []
        for iid in sorted(all_ids):
            c0_pass = iid in c0_resolved
            c2_pass = iid in c2_resolved
            rel = ratings.get(iid, "?")
            status = "both" if c0_pass and c2_pass else "c0_only" if c0_pass else "c2_only" if c2_pass else "neither"
            per_instance.append({"instance_id": iid, "c0": c0_pass, "c2": c2_pass, "relevance": rel, "status": status})
            marker = "<--" if status in ("c2_only", "c0_only") else ""
            print(f"  {iid}: C0={'PASS' if c0_pass else 'FAIL'} C2={'PASS' if c2_pass else 'FAIL'} rel={rel} {marker}")
        analysis["per_instance_c2_vs_c0"] = per_instance

    # Save analysis JSON
    out_path = _OPENHANDS_DIR / "axiom_study_results.json"
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    # Generate markdown report
    report_path = _SWEBENCH_DIR / "AXIOM_STUDY_REPORT.md"
    desc_map = {
        "hard_C0": "Bare baseline",
        "hard_C1": "Generic expert prompt",
        "hard_C2": "5 Django axioms (TREATMENT)",
        "hard_C3": "Wrong-domain (sklearn) axioms",
        "hard_C4": "Same info, flat bullets",
        "hard_C5": "C1 + C2 stacked",
        "hard_C7": "Raw Django design docs"
    }
    hyp_map = {
        "hard_C1_vs_C0": "H4 (exploratory)",
        "hard_C2_vs_C0": "H1 (PRIMARY, a=0.05)",
        "hard_C3_vs_C0": "-",
        "hard_C4_vs_C0": "-",
        "hard_C5_vs_C0": "H5 (exploratory)",
        "hard_C7_vs_C0": "H6 (exploratory)",
        "C2_vs_C4": "H2 (secondary, a=0.025)",
        "C2_vs_C3": "H3 (secondary, a=0.025)",
        "C2_vs_C0_high_relevance": "Subgroup (pre-registered)"
    }

    with open(report_path, "w") as f:
        f.write("# Axiom Benchmark Study - Phase B Results\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("**Model:** Haiku 4.5 (reasoning_effort: none, temp=0)\n")
        f.write("**Framework:** OpenHands (100 max iterations, Docker workspace)\n")
        f.write("**Problems:** 30 hard Django problems from SWE-Bench Verified\n\n")

        f.write("## Overall Results\n\n")
        f.write("| Condition | Description | Solved | Rate |\n")
        f.write("|-----------|-------------|--------|------|\n")
        for cond in ["hard_C0", "hard_C1", "hard_C2", "hard_C3", "hard_C4", "hard_C5", "hard_C7"]:
            if cond in analysis["conditions"]:
                d = analysis["conditions"][cond]
                f.write(f"| {cond} | {desc_map.get(cond, '')} | {d['n_solved']}/{d['n_total']} | {d['solve_rate']*100:.1f}% |\n")

        f.write("\n## Hypothesis Tests (McNemar's)\n\n")
        f.write("| Comparison | Hypothesis | Discordant | chi2 | p-value | Significant? |\n")
        f.write("|------------|-----------|------------|------|---------|-------------|\n")
        for comp, test in analysis["mcnemar"].items():
            sig = "YES" if test.get("significant_005") else "no"
            f.write(f"| {comp} | {hyp_map.get(comp, '')} | {test['n_discordant']} | {test['chi2']} | {test['p_value']} | {sig} |\n")

        f.write("\n## Subgroup Analysis (Axiom Relevance >= 3)\n\n")
        f.write("| Condition | High-Rel Solved | High-Rel Rate | Low-Rel Solved | Low-Rel Rate |\n")
        f.write("|-----------|----------------|---------------|----------------|-------------|\n")
        for cond in ["hard_C0", "hard_C1", "hard_C2", "hard_C3", "hard_C4", "hard_C5", "hard_C7"]:
            if cond in analysis["subgroup"]:
                s = analysis["subgroup"][cond]
                hr_rate = s["high_rel_rate"] * 100
                lr_rate = s["low_rel_rate"] * 100
                f.write(f"| {cond} | {s['high_rel_solved']}/{s['high_rel_total']} | {hr_rate:.1f}% | {s['low_rel_solved']}/{s['low_rel_total']} | {lr_rate:.1f}% |\n")

        f.write("\n## Per-Instance: C2 vs C0\n\n")
        if "per_instance_c2_vs_c0" in analysis:
            f.write("| Instance | C0 | C2 | Relevance | Note |\n")
            f.write("|----------|----|----|-----------|------|\n")
            for pi in analysis["per_instance_c2_vs_c0"]:
                c0 = "PASS" if pi["c0"] else "FAIL"
                c2 = "PASS" if pi["c2"] else "FAIL"
                note = "C2 gain" if pi["status"] == "c2_only" else "C0 loss" if pi["status"] == "c0_only" else ""
                f.write(f"| {pi['instance_id']} | {c0} | {c2} | {pi['relevance']} | {note} |\n")

        f.write("\n## Interpretation\n\n")

        if "hard_C2_vs_C0" in analysis["mcnemar"]:
            h1 = analysis["mcnemar"]["hard_C2_vs_C0"]
            c2_rate = analysis["conditions"].get("hard_C2", {}).get("solve_rate", 0)
            c0_rate = analysis["conditions"].get("hard_C0", {}).get("solve_rate", 0)
            diff = (c2_rate - c0_rate) * 100

            if h1["significant_005"]:
                if diff > 0:
                    f.write(f"**H1 SUPPORTED:** C2 (Django axioms) significantly outperforms C0 (baseline) by {diff:+.1f}pp (p={h1['p_value']}).\n\n")
                else:
                    f.write(f"**H1 REVERSED:** C0 significantly outperforms C2 by {-diff:.1f}pp (p={h1['p_value']}). Axioms HURT performance.\n\n")
            else:
                f.write(f"**H1 NOT SUPPORTED:** No significant difference between C2 and C0 (p={h1['p_value']}, diff={diff:+.1f}pp). Null result.\n\n")

        if "C2_vs_C0_high_relevance" in analysis["mcnemar"]:
            sub = analysis["mcnemar"]["C2_vs_C0_high_relevance"]
            if sub["significant_005"]:
                f.write(f"**Subgroup significant:** C2 vs C0 on high-relevance problems (p={sub['p_value']}). Axioms work when relevant.\n\n")
            else:
                f.write(f"**Subgroup not significant:** C2 vs C0 on high-relevance problems (p={sub['p_value']}).\n\n")

        if "C2_vs_C4" in analysis["mcnemar"]:
            fmt = analysis["mcnemar"]["C2_vs_C4"]
            f.write(f"**Format test (H2):** C2 vs C4 p={fmt['p_value']}. {'Format matters.' if fmt['significant_0025'] else 'No format effect detected.'}\n\n")

        if "C2_vs_C3" in analysis["mcnemar"]:
            dom = analysis["mcnemar"]["C2_vs_C3"]
            f.write(f"**Domain specificity (H3):** C2 vs C3 p={dom['p_value']}. {'Domain-specific axioms win.' if dom['significant_0025'] else 'No domain specificity detected.'}\n\n")

        f.write("---\n\n")
        f.write("*Auto-generated by analyze_results.py. Review raw data in axiom_study_results.json.*\n")

    print(f"Report saved to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
