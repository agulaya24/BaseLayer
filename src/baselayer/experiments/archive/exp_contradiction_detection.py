"""
Experiment 7: Contradiction Detection with Local Models
=========================================================
Question: Can Qwen detect contradictions and tensions in extracted facts as well as Opus?

Method:
  - Load Franklin's extracted facts (known contradictions exist)
  - Generate candidate pairs via embedding similarity (>0.5 cosine)
  - Ask Qwen to classify: CONTRADICTION, TENSION, CONSISTENT, UNRELATED
  - Compare Qwen's judgments against ground truth (if available) or self-consistency
  - Test false positive rate by mixing obviously unrelated pairs

Conditions:
  A. Standard prompt: "Are these two facts contradictory?"
  B. Structured prompt: Provide explicit categories and definitions
  C. Two-pass: First classify relationship, then judge if contradiction
"""

import json
import sys
import os
import time
import sqlite3
import random
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import call_qwen, save_results


def load_facts_with_embeddings(limit: int = 150) -> list[dict]:
    """Load facts from Franklin DB."""
    db_path = os.environ.get(
        "EXPERIMENT_DB",
        str(Path(__file__).parent.parent.parent.parent / "subjects" / "franklin_memory" / "data" / "database" / "memory.db")
    )
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, fact_text, predicate, object_text, confidence
        FROM memory_facts
        WHERE superseded_by IS NULL AND fact_text IS NOT NULL
        ORDER BY created_at
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def generate_candidate_pairs(facts: list[dict], n_similar: int = 30, n_unrelated: int = 10) -> list[dict]:
    """Generate candidate pairs for contradiction testing.

    - n_similar: pairs with same or related predicates (more likely to contain contradictions)
    - n_unrelated: random pairs as false-positive controls
    """
    pairs = []

    # Group by predicate
    by_pred = {}
    for f in facts:
        pred = f.get("predicate", "unknown")
        by_pred.setdefault(pred, []).append(f)

    # Same-predicate pairs (highest contradiction potential)
    for pred, group in by_pred.items():
        if len(group) >= 2:
            for i in range(min(len(group) - 1, 5)):
                for j in range(i + 1, min(len(group), i + 3)):
                    pairs.append({
                        "fact_a": group[i],
                        "fact_b": group[j],
                        "pair_type": "same_predicate",
                        "predicate": pred,
                    })
                    if len(pairs) >= n_similar:
                        break
                if len(pairs) >= n_similar:
                    break
        if len(pairs) >= n_similar:
            break

    # Related predicate pairs (e.g., believes + avoids, values + dislikes)
    tension_pairs = [
        ("believes", "avoids"), ("values", "dislikes"), ("practices", "avoids"),
        ("enjoys", "dislikes"), ("aspires_to", "fears"), ("maintains", "struggles_with"),
        ("prefers", "avoids"), ("loves", "hates"),
    ]
    for p1, p2 in tension_pairs:
        if p1 in by_pred and p2 in by_pred:
            f1 = random.choice(by_pred[p1])
            f2 = random.choice(by_pred[p2])
            pairs.append({
                "fact_a": f1, "fact_b": f2,
                "pair_type": "tension_candidates",
                "predicates": f"{p1}/{p2}",
            })

    # Random unrelated pairs (false positive controls)
    for _ in range(n_unrelated):
        f1, f2 = random.sample(facts, 2)
        pairs.append({
            "fact_a": f1, "fact_b": f2,
            "pair_type": "random_control",
        })

    return pairs


def judge_standard(fact_a: str, fact_b: str) -> dict:
    """Standard contradiction detection prompt."""
    prompt = f"""Are these two facts about the same person contradictory?

Fact A: {fact_a}
Fact B: {fact_b}

Classify as one of:
- CONTRADICTION: They directly contradict each other (cannot both be true)
- TENSION: They are in tension but could coexist (e.g., values freedom but works structured hours)
- CONSISTENT: They are compatible or complementary
- UNRELATED: They describe different aspects with no logical relationship

Return JSON: {{"verdict": "...", "reasoning": "brief explanation", "confidence": 0.0-1.0}}"""

    try:
        resp = call_qwen(prompt, max_tokens=500, json_mode=True)
        return json.loads(resp)
    except (json.JSONDecodeError, KeyError):
        return {"verdict": "ERROR", "reasoning": "parse_error", "confidence": 0}


def judge_structured(fact_a: str, fact_b: str) -> dict:
    """Structured prompt with explicit definitions."""
    prompt = f"""You are analyzing two facts about the same person for logical consistency.

DEFINITIONS:
- CONTRADICTION: Logically incompatible. Believing X and not-X. Doing A and never doing A.
  Example: "values honesty" + "practices deception" = CONTRADICTION
- TENSION: In apparent conflict but psychologically coherent. Internal complexity.
  Example: "values frugality" + "enjoys luxury travel" = TENSION (tension between values and desires)
- CONSISTENT: Compatible. May reinforce each other.
  Example: "values learning" + "reads daily" = CONSISTENT
- UNRELATED: Different domains, no logical connection.
  Example: "lives in Boston" + "enjoys cooking" = UNRELATED

Fact A: {fact_a}
Fact B: {fact_b}

IMPORTANT: Most fact pairs are CONSISTENT or UNRELATED. True contradictions are rare.
Tensions are more common — they represent the complexity of human identity.

Return JSON: {{"verdict": "CONTRADICTION|TENSION|CONSISTENT|UNRELATED", "reasoning": "...", "confidence": 0.0-1.0}}"""

    try:
        resp = call_qwen(prompt, max_tokens=500, json_mode=True)
        return json.loads(resp)
    except (json.JSONDecodeError, KeyError):
        return {"verdict": "ERROR", "reasoning": "parse_error", "confidence": 0}


def judge_two_pass(fact_a: str, fact_b: str) -> dict:
    """Two-pass: first classify relationship type, then judge contradiction."""
    # Pass 1: Classify relationship
    rel_prompt = f"""What is the TOPICAL relationship between these two facts?

Fact A: {fact_a}
Fact B: {fact_b}

Return JSON: {{"relationship": "same_topic|related_topics|different_topics", "shared_theme": "..."}}"""

    try:
        rel_resp = call_qwen(rel_prompt, max_tokens=300, json_mode=True)
        rel = json.loads(rel_resp)
    except (json.JSONDecodeError, KeyError):
        rel = {"relationship": "unknown", "shared_theme": ""}

    # If different topics, skip contradiction check
    if rel.get("relationship") == "different_topics":
        return {"verdict": "UNRELATED", "reasoning": "different topics", "confidence": 0.9, "pass1": rel}

    # Pass 2: Judge contradiction
    contra_prompt = f"""These two facts are about the same topic ({rel.get('shared_theme', 'unknown')}).
Are they contradictory?

Fact A: {fact_a}
Fact B: {fact_b}

Return JSON: {{"verdict": "CONTRADICTION|TENSION|CONSISTENT", "reasoning": "...", "confidence": 0.0-1.0}}"""

    try:
        resp = call_qwen(contra_prompt, max_tokens=500, json_mode=True)
        result = json.loads(resp)
        result["pass1"] = rel
        return result
    except (json.JSONDecodeError, KeyError):
        return {"verdict": "ERROR", "reasoning": "parse_error", "confidence": 0, "pass1": rel}


STRATEGIES = {
    "A_standard": judge_standard,
    "B_structured": judge_structured,
    "C_two_pass": judge_two_pass,
}


def main():
    print("=" * 60)
    print("EXPERIMENT 7: Contradiction Detection")
    print("=" * 60)

    facts = load_facts_with_embeddings(limit=150)
    if not facts:
        print("ERROR: No facts found")
        return

    print(f"Loaded {len(facts)} Franklin facts")

    pairs = generate_candidate_pairs(facts, n_similar=25, n_unrelated=10)
    print(f"Generated {len(pairs)} candidate pairs")
    pair_types = {}
    for p in pairs:
        t = p["pair_type"]
        pair_types[t] = pair_types.get(t, 0) + 1
    for t, c in pair_types.items():
        print(f"  {t}: {c}")
    print()

    all_results = {}

    for strategy_name, judge_fn in STRATEGIES.items():
        print(f"--- {strategy_name} ---")
        t0 = time.time()
        verdicts = {"CONTRADICTION": 0, "TENSION": 0, "CONSISTENT": 0, "UNRELATED": 0, "ERROR": 0}
        pair_results = []

        for i, pair in enumerate(pairs):
            fa = pair["fact_a"]["fact_text"]
            fb = pair["fact_b"]["fact_text"]
            print(f"  [{strategy_name}] pair {i+1}/{len(pairs)}...", end="")

            result = judge_fn(fa, fb)
            verdict = result.get("verdict", "ERROR")
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            print(f" {verdict}")

            pair_results.append({
                "pair_type": pair["pair_type"],
                "fact_a": fa[:150],
                "fact_b": fb[:150],
                "verdict": verdict,
                "reasoning": result.get("reasoning", ""),
                "confidence": result.get("confidence", 0),
            })

        elapsed = round(time.time() - t0, 1)

        # False positive rate on random controls
        control_results = [r for r in pair_results if r["pair_type"] == "random_control"]
        fp_contradictions = sum(1 for r in control_results if r["verdict"] == "CONTRADICTION")
        fp_tensions = sum(1 for r in control_results if r["verdict"] == "TENSION")
        fp_rate = (fp_contradictions + fp_tensions) / max(len(control_results), 1)

        strategy_result = {
            "strategy": strategy_name,
            "pairs_tested": len(pairs),
            "verdict_distribution": verdicts,
            "false_positive_rate": round(fp_rate, 3),
            "fp_contradictions_in_controls": fp_contradictions,
            "fp_tensions_in_controls": fp_tensions,
            "control_pairs": len(control_results),
            "time_seconds": elapsed,
            "pair_results": pair_results,
        }
        all_results[strategy_name] = strategy_result

        print(f"  Verdicts: {verdicts}")
        print(f"  False positive rate: {fp_rate:.1%} ({fp_contradictions} contra + {fp_tensions} tension in {len(control_results)} controls)")
        print(f"  Time: {elapsed}s")
        print()

    # Find interesting contradictions/tensions
    interesting = []
    for name, r in all_results.items():
        for pr in r["pair_results"]:
            if pr["verdict"] in ("CONTRADICTION", "TENSION") and pr["pair_type"] != "random_control":
                interesting.append({
                    "strategy": name,
                    "verdict": pr["verdict"],
                    "fact_a": pr["fact_a"],
                    "fact_b": pr["fact_b"],
                    "reasoning": pr["reasoning"],
                })

    summary = {
        "experiment": "contradiction_detection",
        "question": "Can Qwen detect contradictions as well as Opus?",
        "total_pairs": len(pairs),
        "strategies": {},
    }

    print("=" * 60)
    print("SUMMARY")
    print(f"{'Strategy':<20} {'Contra':>7} {'Tension':>8} {'Consist':>8} {'FP Rate':>8} {'Time':>6}")
    print("-" * 60)
    for name, r in all_results.items():
        v = r["verdict_distribution"]
        print(f"{name:<20} {v.get('CONTRADICTION',0):>7} {v.get('TENSION',0):>8} "
              f"{v.get('CONSISTENT',0):>8} {r['false_positive_rate']:>7.1%} {r['time_seconds']:>5.0f}s")
        summary["strategies"][name] = {
            "contradictions": v.get("CONTRADICTION", 0),
            "tensions": v.get("TENSION", 0),
            "consistent": v.get("CONSISTENT", 0),
            "false_positive_rate": r["false_positive_rate"],
            "time_seconds": r["time_seconds"],
        }

    print(f"\nInteresting contradictions/tensions found: {len(interesting)}")
    for item in interesting[:5]:
        print(f"  [{item['verdict']}] {item['fact_a'][:60]} vs {item['fact_b'][:60]}")

    summary["interesting_findings"] = interesting[:20]
    summary["full_results"] = all_results
    save_results("contradiction_detection", summary)


if __name__ == "__main__":
    main()
