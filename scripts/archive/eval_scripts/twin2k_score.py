"""
Twin-2K-500 Scorer (v2)

Exact reimplementation of the Digital-Twin-Simulation MAD accuracy methodology:
  - Column ranges from get_default_column_ranges()
  - QID-to-task mapping (17 tasks) from get_default_qid_to_task()
  - Decile normalization for anchoring questions (Q164/Q166/Q168/Q170)
  - Aggregation: per-respondent → per-task mean → mean across respondents
  - Ground truth = wave 1-3 answers (from wave4_Q_w13A.json)

Usage:
    python twin2k_score.py                         # Score all available results
    python twin2k_score.py --condition C1           # Score one condition
    python twin2k_score.py --condition C1 --model gpt-4.1-mini
    python twin2k_score.py --breakdown              # Per-task breakdown
    python twin2k_score.py --export results.json    # Export to JSON
"""

import argparse
import json
import os
import sys
import numpy as np
from pathlib import Path
from collections import defaultdict

SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))
RESULTS_DIR = SUBJECTS_DIR / "results"

# Published baselines (Toubia et al. 2025)
PUBLISHED = {
    "random": 59.17,
    "persona_summary": 68.02,
    "fine_tuned": 69.61,
    "full_persona": 71.72,
    "human_ceiling": 81.72,
}

# ---------------------------------------------------------------------------
# Column ranges — from their get_default_column_ranges()
# Values are (min, max) tuples
# ---------------------------------------------------------------------------

def get_column_ranges():
    """Manual min/max for each scoring column. Matches their code exactly."""
    r = {}

    # False consensus (self) — Matrix 1-5
    r.update({f"FALSE CONS. SELF _{i}": (1, 5) for i in range(1, 11)})
    # Actually RowsID is [1,2,3,4,5,6,7,10,11,12]
    # But the range definition uses 1-10, matching their code
    # Their code: {f"FALSE CONS. SELF _{i}": (1, 5) for i in range(1, 11)}
    # Note: this includes _8 and _9 which aren't used by any participant
    # but the range is defined for all 1-10

    # False consensus (others) — Slider 0-100
    others_ids = [1, 2, 3, 4, 5, 6, 7, 10, 11, 12]
    r.update({f"FALSE CONS. OTHERS _{i}": (0, 100) for i in others_ids})

    # Base-rate / "Form A"
    r["Q156_1"] = (0, 100)
    r["FORM A _1"] = (0, 100)

    # 5-point questions (range 1-6)
    codes_5_6 = ["157", "158"] + [f"160_{i}" for i in (1, 2, 3)] + [f"159_{i}" for i in (1, 2, 3)]
    r.update({f"Q{c}": (1, 6) for c in codes_5_6})

    # Outcome bias (range 1-7)
    for c in ("161", "162"):
        r[f"Q{c}"] = (1, 7)

    # Anchoring & adjustment (range 1-10) — these get decile-normalized
    for c in ("164", "166", "168", "170"):
        r[f"Q{c}"] = (1, 10)

    # Less-is-more & siblings (range 1-5 or 1-6)
    for c in ("171", "172", "173", "174", "175", "176"):
        r[f"Q{c}"] = (1, 5)
    for c in ("177", "178", "179"):
        r[f"Q{c}"] = (1, 6)

    # Sunk cost fallacy (0-20)
    r["Q181"] = (0, 20)
    r["Q182"] = (0, 20)

    # Absolute vs relative savings (1-2)
    for c in ("183", "184"):
        r[f"Q{c}"] = (1, 2)

    # Allais (1-10) — wait, their code says Q189-191 are WTA/WTP, Q192-193 are Allais
    # But column ranges: Q189-191 = (1,10), Q192-193 = (1,2)
    for c in ("189", "190", "191"):
        r[f"Q{c}"] = (1, 10)

    # Myside bias (1-2) — Q192, Q193 in their ranges
    for c in ("192", "193"):
        r[f"Q{c}"] = (1, 2)

    # WTA/WTP (1-6) — Q194, Q195 in their ranges
    for c in ("194", "195"):
        r[f"Q{c}"] = (1, 6)

    # Prob matching vs max (1-2)
    r.update({f"Q198_{i}": (1, 2) for i in range(1, 11)})
    r.update({f"Q203_{i}": (1, 2) for i in range(1, 7)})

    # Non-separability (1-7)
    r.update({f"NONSEPARABILTY BENE _{i}": (1, 7) for i in range(1, 5)})
    r.update({f"NONSEPARABILITY RIS _{i}": (1, 7) for i in range(1, 5)})

    # Omission bias & denominator neglect
    r["OMISSION BIAS "] = (1, 4)
    r["DENOMINATOR NEGLECT "] = (1, 2)

    # Pricing (1-2)
    r.update({f"{i}_Q295": (1, 2) for i in range(1, 41)})

    return r


# ---------------------------------------------------------------------------
# QID-to-task mapping — from their get_default_qid_to_task()
# ---------------------------------------------------------------------------

def get_qid_to_task():
    """Map column names to task names (17 tasks). Matches their code exactly.
    Returns dict with UPPERCASE keys."""
    m = {}
    m.update({f"False Cons. self _{i}": "false consensus" for i in range(1, 11)})
    m.update({f"False cons. others _{i}": "false consensus"
              for i in [1, 2, 3, 4, 5, 6, 7, 10, 11, 12]})
    m["Q156_1"] = "base rate"
    m["Form A _1"] = "base rate"
    m["Q157"] = "framing problem"
    m["Q158"] = "framing problem"
    m.update({f"Q160_{i}": "conjunction problem (Linda)" for i in [1, 2, 3]})
    m.update({f"Q159_{i}": "conjunction problem (Linda)" for i in [1, 2, 3]})
    m["Q161"] = "outcome bias"
    m["Q162"] = "outcome bias"
    m["Q164"] = "anchoring and adjustment"
    m["Q166"] = "anchoring and adjustment"
    m["Q168"] = "anchoring and adjustment"
    m["Q170"] = "anchoring and adjustment"
    m.update({f"Q17{i}": "less is more" for i in range(1, 10)})
    m["Q181"] = "sunk cost fallacy"
    m["Q182"] = "sunk cost fallacy"
    m["Q183"] = "absolute vs. relative savings"
    m["Q184"] = "absolute vs. relative savings"
    m["Q189"] = "WTA/WTP-Thaler"
    m["Q190"] = "WTA/WTP-Thaler"
    m["Q191"] = "WTA/WTP-Thaler"
    m["Q192"] = "Allais"
    m["Q193"] = "Allais"
    m["Q194"] = "myside"
    m["Q195"] = "myside"
    m.update({f"Q198_{i}": "prob matching vs. max" for i in range(1, 11)})
    m.update({f"Q203_{i}": "prob matching vs. max" for i in range(1, 7)})
    m.update({f"nonseparabilty bene _{i}": "non-separability of risks and benefits"
              for i in range(1, 5)})
    m.update({f"nonseparability ris _{i}": "non-separability of risks and benefits"
              for i in range(1, 5)})
    m["Omission bias "] = "omission"
    m["Denominator neglect "] = "denominator neglect"
    m.update({f"{i}_Q295": "pricing" for i in range(1, 41)})

    # Uppercase all keys (their code does this)
    return {k.upper(): v for k, v in m.items()}


# ---------------------------------------------------------------------------
# Decile normalization — for anchoring questions
# ---------------------------------------------------------------------------

def assign_decile(value, thresholds):
    """Assign a value to its decile (1-10) based on thresholds."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    for i, t in enumerate(thresholds):
        if value <= t:
            return i + 1
    return 10


def compute_decile_thresholds(all_gt_values):
    """Compute decile thresholds from ground truth values across all participants.
    Returns thresholds array (9 values for 10 deciles).
    """
    values = [v for v in all_gt_values if v is not None]
    if not values:
        return None
    return np.percentile(values, np.arange(10, 100, 10))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def load_prediction_file(filepath):
    """Load a v2 prediction file and return its column data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def find_prediction_files(condition=None, model=None):
    """Find all v2 prediction files."""
    if not RESULTS_DIR.exists():
        return {}
    files = {}
    for pdir in sorted(RESULTS_DIR.iterdir()):
        if not pdir.is_dir() or not pdir.name.startswith("participant_"):
            continue
        pid = int(pdir.name.split("_")[1])
        for f in pdir.iterdir():
            if not f.name.startswith("predictions_") or not f.name.endswith(".json"):
                continue
            parts = f.stem.split("_", 2)
            if len(parts) < 2:
                continue
            file_condition = parts[1]
            file_model = parts[2] if len(parts) > 2 else "unknown"
            if condition and file_condition != condition:
                continue
            if model and model not in file_model:
                continue
            files[pid] = f
    return files


def score_condition(condition, model=None, show_breakdown=False):
    """Score all predictions for a given condition.
    Returns the aggregated MAD accuracy result.
    """
    files = find_prediction_files(condition=condition, model=model)
    if not files:
        return None

    column_ranges = get_column_ranges()
    qid_to_task = get_qid_to_task()

    # Collect all data
    all_pred_columns = {}  # {pid: {col: val}}
    all_gt_columns = {}
    all_wave4_columns = {}

    for pid, filepath in sorted(files.items()):
        data = load_prediction_file(filepath)
        pred_cols = data.get("pred_columns", {})
        gt_cols = data.get("gt_columns", {})
        wave4_cols = data.get("wave4_columns", {})

        if not pred_cols:
            print(f"  WARNING: No pred_columns in {filepath.name} — old format?")
            continue

        # Uppercase all column keys
        all_pred_columns[pid] = {k.upper(): v for k, v in pred_cols.items()}
        all_gt_columns[pid] = {k.upper(): v for k, v in gt_cols.items()}
        all_wave4_columns[pid] = {k.upper(): v for k, v in wave4_cols.items()}

    if not all_pred_columns:
        return None

    n_participants = len(all_pred_columns)

    # Decile normalization for anchoring questions
    decile_cols_164 = ["Q164", "Q166"]
    decile_cols_168 = ["Q168", "Q170"]

    # Collect all GT values for decile computation
    gt_164_vals = []
    gt_168_vals = []
    for pid, gt in all_gt_columns.items():
        for col in decile_cols_164:
            v = gt.get(col)
            if v is not None:
                try:
                    gt_164_vals.append(float(v))
                except (ValueError, TypeError):
                    pass
        for col in decile_cols_168:
            v = gt.get(col)
            if v is not None:
                try:
                    gt_168_vals.append(float(v))
                except (ValueError, TypeError):
                    pass

    thresh_164 = compute_decile_thresholds(gt_164_vals) if gt_164_vals else None
    thresh_168 = compute_decile_thresholds(gt_168_vals) if gt_168_vals else None

    # Apply decile normalization
    for pid in all_pred_columns:
        for col_set, thresh in [(decile_cols_164, thresh_164), (decile_cols_168, thresh_168)]:
            if thresh is None:
                continue
            for col in col_set:
                for dataset in [all_pred_columns[pid], all_gt_columns[pid], all_wave4_columns.get(pid, {})]:
                    v = dataset.get(col)
                    if v is not None:
                        try:
                            dataset[col] = assign_decile(float(v), thresh)
                        except (ValueError, TypeError):
                            pass

    # Uppercase column ranges
    col_ranges_upper = {k.upper(): v for k, v in column_ranges.items()}

    # Compute per-respondent, per-task MAD accuracy
    # Aggregation: per-respondent → per-task mean → mean across respondents
    respondent_accuracies = []
    respondent_wave4_accuracies = []
    task_details = defaultdict(lambda: {"pred_diffs": [], "wave4_diffs": [], "n": 0})

    for pid in sorted(all_pred_columns.keys()):
        pred = all_pred_columns[pid]
        gt = all_gt_columns[pid]
        wave4 = all_wave4_columns.get(pid, {})

        # For this respondent, compute per-task mean MAD
        task_diffs_pred = defaultdict(list)
        task_diffs_wave4 = defaultdict(list)

        for col in pred:
            col_upper = col.upper() if col != col.upper() else col
            if col_upper not in col_ranges_upper:
                continue
            task = qid_to_task.get(col_upper)
            if not task:
                continue
            gt_val = gt.get(col_upper)
            if gt_val is None:
                continue

            mn, mx = col_ranges_upper[col_upper]
            r = mx - mn
            if r == 0:
                continue

            pred_val = pred.get(col_upper)
            if pred_val is not None:
                try:
                    diff = abs(float(pred_val) - float(gt_val)) / r
                    task_diffs_pred[task].append(diff)
                    task_details[task]["pred_diffs"].append(diff)
                except (ValueError, TypeError):
                    pass

            wave4_val = wave4.get(col_upper)
            if wave4_val is not None:
                try:
                    diff = abs(float(wave4_val) - float(gt_val)) / r
                    task_diffs_wave4[task].append(diff)
                    task_details[task]["wave4_diffs"].append(diff)
                except (ValueError, TypeError):
                    pass

        # Per-task means for this respondent
        if task_diffs_pred:
            task_means = [np.mean(diffs) for diffs in task_diffs_pred.values()]
            respondent_acc = 1 - np.mean(task_means)
            respondent_accuracies.append(respondent_acc)

        if task_diffs_wave4:
            task_means = [np.mean(diffs) for diffs in task_diffs_wave4.values()]
            respondent_wave4_accuracies.append(1 - np.mean(task_means))

    # Generate random baseline
    rng = np.random.default_rng(42)
    respondent_random_accuracies = []
    for pid in sorted(all_pred_columns.keys()):
        gt = all_gt_columns[pid]
        task_diffs_rand = defaultdict(list)
        for col in gt:
            col_upper = col.upper() if col != col.upper() else col
            if col_upper not in col_ranges_upper:
                continue
            task = qid_to_task.get(col_upper)
            if not task:
                continue
            gt_val = gt.get(col_upper)
            if gt_val is None:
                continue
            mn, mx = col_ranges_upper[col_upper]
            r = mx - mn
            if r == 0:
                continue
            try:
                rand_val = rng.integers(int(mn), int(mx) + 1)
                diff = abs(rand_val - float(gt_val)) / r
                task_diffs_rand[task].append(diff)
            except (ValueError, TypeError):
                pass
        if task_diffs_rand:
            task_means = [np.mean(diffs) for diffs in task_diffs_rand.values()]
            respondent_random_accuracies.append(1 - np.mean(task_means))

    # Aggregate
    result = {
        "condition": condition,
        "n_participants": n_participants,
    }

    if respondent_accuracies:
        arr = np.array(respondent_accuracies)
        result["llm_accuracy"] = float(arr.mean() * 100)
        result["llm_std"] = float(arr.std() * 100)
        result["llm_se"] = float((arr.std() / np.sqrt(len(arr))) * 100)
        result["respondent_accuracies"] = respondent_accuracies

    if respondent_wave4_accuracies:
        arr = np.array(respondent_wave4_accuracies)
        result["wave4_accuracy"] = float(arr.mean() * 100)
        result["wave4_std"] = float(arr.std() * 100)

    if respondent_random_accuracies:
        arr = np.array(respondent_random_accuracies)
        result["random_accuracy"] = float(arr.mean() * 100)
        result["random_std"] = float(arr.std() * 100)

    # Per-task breakdown
    if show_breakdown:
        task_breakdown = {}
        for task, data in sorted(task_details.items()):
            pred_diffs = data["pred_diffs"]
            wave4_diffs = data["wave4_diffs"]
            entry = {"n_observations": len(pred_diffs)}
            if pred_diffs:
                entry["llm_accuracy"] = float((1 - np.mean(pred_diffs)) * 100)
            if wave4_diffs:
                entry["wave4_accuracy"] = float((1 - np.mean(wave4_diffs)) * 100)
            task_breakdown[task] = entry
        result["per_task"] = task_breakdown

    return result


def print_results(condition_results, show_breakdown=False):
    """Print formatted results table."""
    print("\n" + "=" * 70)
    print("TWIN-2K-500 RESULTS (MAD Accuracy, task-level aggregation)")
    print("=" * 70)

    header = f"{'Condition':<25} {'LLM Acc':>10} {'  SE':>7} {'  SD':>7} {'Random':>10} {'Wave4 TR':>10} {'N':>5}"
    print(header)
    print("-" * 80)

    for condition in ["C1", "C2", "C3", "C4", "C5"]:
        if condition not in condition_results:
            continue
        r = condition_results[condition]
        label = {
            "C1": "C1 (no context)",
            "C2": "C2 (Base Layer brief)",
            "C3": "C3 (full dump)",
            "C4": "C4 (brief+full)",
            "C5": "C5 (persona summary)",
        }[condition]
        llm = f"{r.get('llm_accuracy', 0):.2f}%"
        se = f"±{r.get('llm_se', 0):.2f}" if 'llm_se' in r else ""
        sd = f"({r.get('llm_std', 0):.2f})" if 'llm_std' in r else ""
        rand = f"{r.get('random_accuracy', 0):.2f}%"
        wave4 = f"{r.get('wave4_accuracy', 0):.2f}%" if 'wave4_accuracy' in r else "N/A"
        n = r.get('n_participants', 0)
        print(f"{label:<25} {llm:>10} {se:>7} {sd:>7} {rand:>10} {wave4:>10} {n:>5}")

    # 95% confidence intervals
    print(f"\n{'95% Confidence Intervals:'}")
    for condition in ["C1", "C2", "C3", "C4", "C5"]:
        if condition not in condition_results:
            continue
        r = condition_results[condition]
        acc = r.get('llm_accuracy', 0)
        se = r.get('llm_se', 0)
        label = {"C1": "C1", "C2": "C2 (brief)", "C3": "C3 (full)", "C4": "C4 (brief+full)", "C5": "C5 (summary)"}[condition]
        print(f"  {label}: [{acc - 1.96*se:.2f}%, {acc + 1.96*se:.2f}%]")

    print(f"\n{'Published baselines (GPT-4.1-mini, 2058 participants):'}")
    print(f"  {'Random:':<35} {PUBLISHED['random']:>6.2f}%")
    print(f"  {'Persona summary:':<35} {PUBLISHED['persona_summary']:>6.2f}%")
    print(f"  {'Fine-tuned (500 samples):':<35} {PUBLISHED['fine_tuned']:>6.2f}%")
    print(f"  {'Full persona text (~130K chars):':<35} {PUBLISHED['full_persona']:>6.2f}%")
    print(f"  {'Human test-retest ceiling:':<35} {PUBLISHED['human_ceiling']:>6.2f}%")

    # Delta analysis
    for cond in ["C2", "C5", "C3", "C1"]:
        if cond in condition_results:
            acc = condition_results[cond].get("llm_accuracy", 0)
            label = {"C1": "C1", "C2": "C2 (brief)", "C3": "C3 (full dump)", "C4": "C4 (brief+full)", "C5": "C5 (summary)"}[cond]
            print(f"\n{'Delta analysis (' + label + '):'}")
            print(f"  vs Published random:    {acc - PUBLISHED['random']:>+.2f}%")
            print(f"  vs Published summary:   {acc - PUBLISHED['persona_summary']:>+.2f}%")
            print(f"  vs Published full:      {acc - PUBLISHED['full_persona']:>+.2f}%")
            print(f"  vs Published ceiling:   {acc - PUBLISHED['human_ceiling']:>+.2f}%")

    # Paired statistical tests (C2 vs C1, C2 vs C3)
    if len(condition_results) > 1:
        from scipy import stats as sp_stats
        print(f"\n{'Paired Statistical Tests:'}")
        for pair in [("C1", "C2"), ("C1", "C5"), ("C2", "C5"), ("C2", "C3"), ("C1", "C3"), ("C3", "C4")]:
            c_a, c_b = pair
            if c_a not in condition_results or c_b not in condition_results:
                continue
            arr_a = np.array(condition_results[c_a].get("respondent_accuracies", []))
            arr_b = np.array(condition_results[c_b].get("respondent_accuracies", []))
            if len(arr_a) == 0 or len(arr_b) == 0 or len(arr_a) != len(arr_b):
                continue
            diff = arr_b - arr_a
            t_stat, p_val = sp_stats.ttest_rel(arr_b, arr_a)
            w_stat, w_p = sp_stats.wilcoxon(diff, alternative='two-sided')
            cohen_d = diff.mean() / diff.std() if diff.std() > 0 else float('inf')
            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
            label_a = {"C1": "C1", "C2": "C2 (brief)", "C3": "C3 (full)", "C4": "C4 (brief+full)", "C5": "C5 (summary)"}[c_a]
            label_b = {"C1": "C1", "C2": "C2 (brief)", "C3": "C3 (full)", "C4": "C4 (brief+full)", "C5": "C5 (summary)"}[c_b]
            print(f"  {label_a} -> {label_b}:")
            print(f"    Mean diff: {diff.mean()*100:+.2f}%  (paired t={t_stat:.3f}, p={p_val:.4f} {sig})")
            print(f"    Wilcoxon: W={w_stat:.1f}, p={w_p:.4f}")
            print(f"    Cohen's d: {cohen_d:.3f}")

    # Per-task breakdown
    if show_breakdown:
        for cond in ["C1", "C2", "C5", "C3"]:
            if cond not in condition_results:
                continue
            per_task = condition_results[cond].get("per_task", {})
            if not per_task:
                continue
            print(f"\n{'Per-task breakdown (' + cond + '):'}")
            print(f"  {'Task':<45} {'LLM Acc':>10} {'Wave4 TR':>10} {'N':>6}")
            print("  " + "-" * 73)
            for task, data in sorted(per_task.items(), key=lambda x: -x[1].get("llm_accuracy", 0)):
                llm = f"{data.get('llm_accuracy', 0):.2f}%"
                w4 = f"{data.get('wave4_accuracy', 0):.2f}%" if 'wave4_accuracy' in data else "N/A"
                n = data.get("n_observations", 0)
                print(f"  {task:<45} {llm:>10} {w4:>10} {n:>6}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Score Twin-2K-500 predictions (v2)")
    parser.add_argument("--condition", choices=["C1", "C2", "C3", "C4", "C5"],
                        help="Score one condition")
    parser.add_argument("--model", type=str, help="Filter by model name")
    parser.add_argument("--breakdown", action="store_true",
                        help="Show per-task breakdown")
    parser.add_argument("--export", type=str, help="Export results to JSON")
    args = parser.parse_args()

    if not RESULTS_DIR.exists():
        print(f"ERROR: No results directory at {RESULTS_DIR}")
        print("Run twin2k_predict.py first.")
        sys.exit(1)

    condition_results = {}

    for condition in ["C1", "C2", "C3", "C4", "C5"]:
        if args.condition and args.condition != condition:
            continue
        result = score_condition(condition, model=args.model,
                                 show_breakdown=args.breakdown)
        if result:
            condition_results[condition] = result

    if not condition_results:
        print("No predictions found to score.")
        print(f"Looking in: {RESULTS_DIR}")
        sys.exit(1)

    print_results(condition_results, show_breakdown=args.breakdown)

    if args.export:
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(condition_results, f, indent=2)
        print(f"Results exported to {args.export}")


if __name__ == "__main__":
    main()
