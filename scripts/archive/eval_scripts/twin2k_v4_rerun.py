"""
Twin-2K V4 Compose Rerun — N=10 benchmark with updated compose prompt.

Steps:
1. Recompose briefs for participants 0-9 using current V4 compose prompt
2. Run C1 (no context) and C2 (new brief) predictions on GPT-4.1-mini
3. Score and compare to N=100 baseline

Saves new results to results_v4_rerun/ to avoid overwriting N=100 data.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

# Add memory_system/scripts and archive to path for imports
SCRIPTS_DIR = Path(__file__).parent
ARCHIVE_DIR = SCRIPTS_DIR / "archive" / "eval_scripts"
sys.path.insert(0, str(ARCHIVE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))
RESULTS_DIR = SUBJECTS_DIR / "results_v4_rerun"
BRIEFS_DIR = SUBJECTS_DIR / "briefs_v4_rerun"

PARTICIPANTS = list(range(10))

# Import prediction and scoring machinery
from twin2k_predict import (
    build_question_text, build_prompt, call_model,
    parse_response_json, map_predictions_to_columns,
    extract_ground_truth_columns
)
from twin2k_score import (
    get_column_ranges, get_qid_to_task, compute_decile_thresholds,
    assign_decile
)

# Import the compose prompt from agent_pipeline
sys.path.insert(0, str(SCRIPTS_DIR))
from agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT


def read_layers(participant_dir):
    """Read the 3 layer files for a participant."""
    layers_dir = participant_dir / "data" / "identity_layers"
    layer_texts = {}
    for name, filename in [("anchors", "anchors_v4.md"),
                           ("core", "core_v4.md"),
                           ("predictions", "predictions_v4.md")]:
        path = layers_dir / filename
        if path.exists():
            content = path.read_text(encoding="utf-8")
            marker = "## Injectable Block"
            idx = content.find(marker)
            if idx >= 0:
                layer_texts[name] = content[idx + len(marker):].strip()
            else:
                sep = content.find("\n---\n")
                layer_texts[name] = content[sep + 5:].strip() if sep >= 0 else content.strip()
    return layer_texts


def read_identity_facts(participant_dir):
    """Read identity-tier facts from participant's SQLite DB."""
    db_path = participant_dir / "data" / "database" / "memory.db"
    if not db_path.exists():
        return "", 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, category, recurrence_count
        FROM memory_facts
        WHERE superseded_by IS NULL
          AND knowledge_tier = 'identity'
        ORDER BY recurrence_count DESC
        LIMIT 100
    """).fetchall()

    fact_count = len(rows)
    lines = []
    for r in rows:
        ftype = r["fact_type"] or "?"
        cat = r["category"] or "?"
        lines.append(f"- [{cat}/{ftype}] {r['fact_text']}")

    conn.close()
    return "\n".join(lines), fact_count


def compose_brief(participant_id, participant_dir):
    """Compose a brief using the current V4 prompt."""
    layer_texts = read_layers(participant_dir)
    if not any(layer_texts.get(k) for k in ("anchors", "core", "predictions")):
        print(f"  P{participant_id}: No layers found, skipping")
        return None

    facts_text, fact_count = read_identity_facts(participant_dir)

    prompt = UNIFIED_BRIEF_COMPOSITION_PROMPT.replace(
        "{anchors}", layer_texts.get("anchors", "(no anchors layer)")
    ).replace(
        "{core}", layer_texts.get("core", "(no core layer)")
    ).replace(
        "{predictions}", layer_texts.get("predictions", "(no predictions layer)")
    ).replace(
        "{facts}", facts_text
    ).replace(
        "{fact_count}", str(fact_count)
    )

    print(f"  P{participant_id}: Composing brief ({len(layer_texts)} layers, {fact_count} facts)...")

    import anthropic
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        brief_text = response.content[0].text
        cost = (response.usage.input_tokens * 3 + response.usage.output_tokens * 15) / 1_000_000
        print(f"  P{participant_id}: Brief composed ({len(brief_text)} chars, ${cost:.3f})")
        return brief_text
    except Exception as e:
        print(f"  P{participant_id}: Composition failed: {e}")
        return None


def run_predictions(participant_id, condition, brief_text=None, model_name="gpt-4.1-mini"):
    """Run predictions for one participant under one condition."""
    pdir = SUBJECTS_DIR / f"participant_{participant_id}"

    gt_file = pdir / "wave4_Q_w13A.json"
    if not gt_file.exists():
        print(f"  ERROR: No wave4_Q_w13A.json for participant {participant_id}")
        return None

    with open(gt_file, 'r', encoding='utf-8') as f:
        wave4_data = json.load(f)

    question_text, question_metadata = build_question_text(wave4_data)
    n_questions = len(question_metadata)

    prompt = build_prompt(condition, question_text, brief_text=brief_text)
    print(f"  P{participant_id}/{condition}: {n_questions} Qs, {len(prompt):,} chars prompt")

    t0 = time.time()
    response_text = call_model(prompt, model_name, max_tokens=8000)
    elapsed = time.time() - t0
    print(f"  P{participant_id}/{condition}: Response {len(response_text):,} chars in {elapsed:.1f}s")

    parsed = parse_response_json(response_text)
    if parsed is None:
        print(f"  P{participant_id}/{condition}: PARSE ERROR")
        return {
            "participant_id": participant_id,
            "condition": condition,
            "model": model_name,
            "raw_response": response_text,
            "parse_error": True,
            "n_questions": n_questions,
        }

    n_parsed = sum(1 for k in parsed if k.startswith("Q"))
    print(f"  P{participant_id}/{condition}: Parsed {n_parsed}/{n_questions}")

    pred_columns = map_predictions_to_columns(parsed, question_metadata)
    gt_columns = extract_ground_truth_columns(wave4_data)

    wave4_qa_file = pdir / "wave4_QA.json"
    wave4_columns = {}
    if wave4_qa_file.exists():
        with open(wave4_qa_file, 'r', encoding='utf-8') as f:
            wave4_qa_data = json.load(f)
        wave4_columns = extract_ground_truth_columns(wave4_qa_data)

    return {
        "participant_id": participant_id,
        "condition": condition,
        "model": model_name,
        "n_questions": n_questions,
        "n_parsed": n_parsed,
        "raw_response": response_text,
        "parsed_json": parsed,
        "pred_columns": pred_columns,
        "gt_columns": gt_columns,
        "wave4_columns": wave4_columns,
        "question_metadata": {k: {"qid": v["qid"], "q_type": v["q_type"],
                                   "block_name": v["block_name"]}
                              for k, v in question_metadata.items()},
    }


def save_result(result, participant_id, condition, model_name):
    """Save prediction result."""
    rdir = RESULTS_DIR / f"participant_{participant_id}"
    rdir.mkdir(parents=True, exist_ok=True)
    filename = f"predictions_{condition}_{model_name}.json"
    out_file = rdir / filename
    save_data = {k: v for k, v in result.items() if k != "question_metadata"}
    save_data["question_metadata"] = result.get("question_metadata", {})
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)
    return out_file


def score_all(model_filter=None):
    """Score all predictions in the v4 rerun results directory."""
    if not RESULTS_DIR.exists():
        print("No results directory found")
        return {}

    column_ranges = get_column_ranges()
    qid_to_task = get_qid_to_task()

    condition_data = defaultdict(lambda: {"pred": {}, "gt": {}, "wave4": {}})

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
            cond = parts[1]
            file_model = parts[2] if len(parts) > 2 else "unknown"
            if model_filter and model_filter not in file_model:
                continue

            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)

            pred_cols = data.get("pred_columns", {})
            gt_cols = data.get("gt_columns", {})
            wave4_cols = data.get("wave4_columns", {})

            condition_data[cond]["pred"][pid] = {k.upper(): v for k, v in pred_cols.items()}
            condition_data[cond]["gt"][pid] = {k.upper(): v for k, v in gt_cols.items()}
            condition_data[cond]["wave4"][pid] = {k.upper(): v for k, v in wave4_cols.items()}

    col_ranges_upper = {k.upper(): v for k, v in column_ranges.items()}
    results = {}

    for cond in ["C1", "C2"]:
        if cond not in condition_data:
            continue

        all_pred = condition_data[cond]["pred"]
        all_gt = condition_data[cond]["gt"]
        all_wave4 = condition_data[cond]["wave4"]

        if not all_pred:
            continue

        n_participants = len(all_pred)

        # Decile normalization for anchoring
        decile_cols_164 = ["Q164", "Q166"]
        decile_cols_168 = ["Q168", "Q170"]
        gt_164_vals, gt_168_vals = [], []
        for pid, gt in all_gt.items():
            for col in decile_cols_164:
                v = gt.get(col)
                if v is not None:
                    try: gt_164_vals.append(float(v))
                    except: pass
            for col in decile_cols_168:
                v = gt.get(col)
                if v is not None:
                    try: gt_168_vals.append(float(v))
                    except: pass

        thresh_164 = compute_decile_thresholds(gt_164_vals) if gt_164_vals else None
        thresh_168 = compute_decile_thresholds(gt_168_vals) if gt_168_vals else None

        for pid in all_pred:
            for col_set, thresh in [(decile_cols_164, thresh_164), (decile_cols_168, thresh_168)]:
                if thresh is None:
                    continue
                for col in col_set:
                    for dataset in [all_pred[pid], all_gt[pid], all_wave4.get(pid, {})]:
                        v = dataset.get(col)
                        if v is not None:
                            try: dataset[col] = assign_decile(float(v), thresh)
                            except: pass

        respondent_accuracies = []
        for pid in sorted(all_pred.keys()):
            pred = all_pred[pid]
            gt = all_gt[pid]
            task_diffs = defaultdict(list)
            for col in pred:
                if col not in col_ranges_upper:
                    continue
                task = qid_to_task.get(col)
                if not task:
                    continue
                gt_val = gt.get(col)
                if gt_val is None:
                    continue
                mn, mx = col_ranges_upper[col]
                r = mx - mn
                if r == 0:
                    continue
                try:
                    diff = abs(float(pred[col]) - float(gt_val)) / r
                    task_diffs[task].append(diff)
                except:
                    pass
            if task_diffs:
                task_means = [np.mean(diffs) for diffs in task_diffs.values()]
                respondent_accuracies.append(1 - np.mean(task_means))

        arr = np.array(respondent_accuracies)
        results[cond] = {
            "n_participants": n_participants,
            "accuracy": float(arr.mean() * 100),
            "std": float(arr.std() * 100),
            "se": float((arr.std() / np.sqrt(len(arr))) * 100),
            "respondent_accuracies": [float(x) for x in respondent_accuracies],
        }

    return results


def print_report(results):
    """Print comparison report."""
    print("\n" + "=" * 70)
    print("TWIN-2K V4 RERUN RESULTS (N=10, GPT-4.1-mini)")
    print("=" * 70)

    print(f"\n{'Condition':<30} {'Accuracy':>10} {'SE':>8} {'SD':>8} {'N':>5}")
    print("-" * 65)

    for cond in ["C1", "C2"]:
        if cond not in results:
            continue
        r = results[cond]
        label = {"C1": "C1 (no context)", "C2": "C2 (V4 brief)"}[cond]
        print(f"{label:<30} {r['accuracy']:>9.2f}% {r['se']:>7.2f} {r['std']:>7.2f} {r['n_participants']:>5}")

    # Delta
    if "C1" in results and "C2" in results:
        delta = results["C2"]["accuracy"] - results["C1"]["accuracy"]
        print(f"\n  C2 - C1 delta: {delta:+.2f}%")

        # Paired t-test
        from scipy import stats as sp_stats
        arr_c1 = np.array(results["C1"]["respondent_accuracies"])
        arr_c2 = np.array(results["C2"]["respondent_accuracies"])
        if len(arr_c1) == len(arr_c2) and len(arr_c1) > 1:
            diff = arr_c2 - arr_c1
            t_stat, p_val = sp_stats.ttest_rel(arr_c2, arr_c1)
            cohen_d = diff.mean() / diff.std() if diff.std() > 0 else float('inf')
            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
            print(f"  Paired t-test: t={t_stat:.3f}, p={p_val:.4f} {sig}")
            print(f"  Cohen's d: {cohen_d:.3f}")
            try:
                w_stat, w_p = sp_stats.wilcoxon(diff, alternative='two-sided')
                print(f"  Wilcoxon: W={w_stat:.1f}, p={w_p:.4f}")
            except:
                print("  Wilcoxon: insufficient data")

    # Comparison to N=100 baseline
    print(f"\n{'Comparison to N=100 baseline (same participants 0-9):'}")
    print(f"  N=100 overall: C1=69.90%, C2=71.83%, delta=+1.93%, p=0.008")
    print(f"  Published baselines: random=59.17%, summary=68.02%, full=71.72%")

    # Per-participant breakdown
    if "C1" in results and "C2" in results:
        print(f"\n{'Per-participant breakdown:'}")
        print(f"  {'PID':<6} {'C1':>10} {'C2':>10} {'Delta':>10}")
        print("  " + "-" * 38)
        for i, (c1, c2) in enumerate(zip(results["C1"]["respondent_accuracies"],
                                          results["C2"]["respondent_accuracies"])):
            d = c2 - c1
            print(f"  P{i:<5} {c1*100:>9.2f}% {c2*100:>9.2f}% {d*100:>+9.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Twin-2K V4 Compose Rerun (N=10)")
    parser.add_argument("--step", choices=["compose", "predict", "score", "all"],
                        default="all", help="Which step to run")
    parser.add_argument("--skip-compose", action="store_true",
                        help="Skip compose step (use existing briefs)")
    parser.add_argument("--model", default="gpt-4.1-mini",
                        help="Prediction model")
    args = parser.parse_args()

    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # STEP 1: Compose briefs
    # ============================================================
    if args.step in ("compose", "all") and not args.skip_compose:
        print("\n" + "=" * 50)
        print("STEP 1: Composing briefs with V4 prompt")
        print("=" * 50)

        total_cost = 0
        for pid in PARTICIPANTS:
            pdir = SUBJECTS_DIR / f"participant_{pid}"
            brief = compose_brief(pid, pdir)
            if brief:
                out_file = BRIEFS_DIR / f"participant_{pid}_brief_v4.md"
                out_file.write_text(brief, encoding="utf-8")
                print(f"  Saved: {out_file} ({len(brief)} chars)")

        print(f"\n  All briefs composed.")

    # ============================================================
    # STEP 2: Run predictions
    # ============================================================
    if args.step in ("predict", "all"):
        print("\n" + "=" * 50)
        print("STEP 2: Running predictions (C1 + C2)")
        print("=" * 50)

        for pid in PARTICIPANTS:
            # C1: no context
            print(f"\n--- Participant {pid}, C1 ---")
            result_c1 = run_predictions(pid, "C1", model_name=args.model)
            if result_c1 and not result_c1.get("parse_error"):
                save_result(result_c1, pid, "C1", args.model)

            # C2: with new V4 brief
            brief_file = BRIEFS_DIR / f"participant_{pid}_brief_v4.md"
            if not brief_file.exists():
                print(f"  P{pid}: No V4 brief found, skipping C2")
                continue
            brief_text = brief_file.read_text(encoding="utf-8")
            print(f"\n--- Participant {pid}, C2 (V4 brief, {len(brief_text)} chars) ---")
            result_c2 = run_predictions(pid, "C2", brief_text=brief_text,
                                        model_name=args.model)
            if result_c2 and not result_c2.get("parse_error"):
                save_result(result_c2, pid, "C2", args.model)

        print(f"\n  All predictions complete.")

    # ============================================================
    # STEP 3: Score
    # ============================================================
    if args.step in ("score", "all"):
        print("\n" + "=" * 50)
        print("STEP 3: Scoring")
        print("=" * 50)

        results = score_all(model_filter=args.model)
        if results:
            print_report(results)

            # Save results
            out_file = RESULTS_DIR / "v4_rerun_results.json"
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            print(f"\n  Results saved to {out_file}")
        else:
            print("  No results to score.")


if __name__ == "__main__":
    main()
