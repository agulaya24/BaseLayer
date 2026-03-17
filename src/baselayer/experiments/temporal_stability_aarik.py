"""
Temporal Stability Rerun — Aarik's GPT Conversations (D-079)

Tests whether temporal stability findings from Franklin (autobiography)
and Marks (investment memos) hold on linear conversation data.

Key question: Do patterns from 2023 conversations predict 2025-2026
behavior as well as vice versa?

Differences from Franklin study:
  - Linear conversations (not static document)
  - 3-year span with accelerating usage
  - Heavily skewed: Q1=121, Q2=231, Q3=617, Q4=1592 identity facts
  - Real temporal drift possible (interests, skills, life changes)

Experiments:
  1. Temporal direction: early→late vs late→early vs random
  2. Quarter prediction: each Q predicts others
  3. Accumulation: Q1→Q4 vs Q4→Q1 (bidirectional)
  4. Cross-type prediction (behavioral vs biographical vs positional)

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/temporal_stability_aarik.py
"""

import sys
import os
import json
import random
import re
import numpy as np
import sqlite3
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

AARIK_DB = "C:/Users/Aarik/Anthropic/memory_system_v4/data/database/memory.db"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "temporal_stability_aarik")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")


def load_facts_with_timestamps():
    """Load identity-tier facts with conversation timestamps for true temporal ordering."""
    conn = sqlite3.connect(AARIK_DB)
    rows = conn.execute("""
        SELECT f.id, f.fact_text, f.fact_type, f.knowledge_tier, f.predicate, f.object_text,
               c.created_at as conv_timestamp
        FROM memory_facts f
        JOIN conversations c ON f.source_conversation_id = c.id
        WHERE f.superseded_by IS NULL AND f.knowledge_tier = 'identity'
        AND c.created_at IS NOT NULL
        ORDER BY c.created_at
    """).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
             "predicate": r[4], "object_text": r[5], "timestamp": r[6]} for r in rows]


def embed_texts(texts):
    if not texts:
        return np.array([])
    vecs = EMBED_MODEL.encode(texts, show_progress_bar=False)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def score_brief(brief_text, held_out_facts):
    if not brief_text or not held_out_facts:
        return {"composite": 0, "prediction_rate": 0}
    brief_vec = embed_texts([brief_text])[0]
    fact_vecs = embed_texts([f["fact_text"] for f in held_out_facts])
    sims = [float(np.dot(brief_vec, fv)) for fv in fact_vecs]
    m1 = float(np.mean(sims))
    m2 = sum(1 for s in sims if s > 0.45) / len(sims)

    text_lower = brief_text.lower()
    patterns = [r'\bwhen\b.*\b(he|they|this person)\b', r'\bif\b.*\b(he|they)\b',
                r'\btend[s]?\s+to\b', r'\bwill\s+(likely|often|always)\b',
                r'\bdefault[s]?\s+to\b', r'\brather\s+than\b', r'\bnever\b',
                r'\balways\b', r'\bfailure\s+mode\b', r'\bblind\s+spot\b']
    m3 = sum(len(re.findall(p, text_lower)) for p in patterns) / max(len(brief_text)/1000, 1)

    composite = round(m1 * 40 + m2 * 25 + min(m3/10, 1) * 15 + 10, 2)
    return {"m1_coverage": round(m1, 4), "prediction_rate": round(m2, 4),
            "m3_pattern_density": round(m3, 2), "composite": composite,
            "chars": len(brief_text)}


BRIEF_SYSTEM = """You generate behavioral briefs from structured facts about a person.
The brief is injected into an AI's system prompt so it understands this person.
RULES:
- Use they/them pronouns. Refer to subject as "this person" or "they."
- Structure as annotated guide with section headers and "When X, do Y" patterns.
- Target: 1500-2500 characters. Dense, specific, actionable.
- Do NOT name the person."""


def generate_brief(facts, label):
    fact_lines = "\n".join([f"- [{f.get('predicate', '?')}] {f['fact_text']}" for f in facts])
    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=BRIEF_SYSTEM,
            messages=[{"role": "user", "content": f"Generate a behavioral brief from these {len(facts)} facts:\n\n{fact_lines}"}],
            max_tokens=2048, temperature=0.3,
            caller=f"temporal_aarik_{label}",
        )
        return resp.content[0].text
    except Exception as e:
        log(f"  ERROR [{label}]: {e}")
        return None


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_condition(train_facts, test_facts, label):
    """Generate brief from train_facts, score against test_facts."""
    log(f"  {label}: {len(train_facts)} train -> {len(test_facts)} test")
    brief = generate_brief(train_facts, label)
    if not brief:
        return {"label": label, "error": "generation failed"}
    scores = score_brief(brief, test_facts)
    log(f"    composite={scores['composite']:.1f}  m1={scores['m1_coverage']:.3f}  pred={scores['prediction_rate']:.1%}")
    return {"label": label, "train_count": len(train_facts), "test_count": len(test_facts),
            "scores": scores, "brief_preview": brief[:200]}


def split_quarters(facts):
    """Split temporally-ordered facts into 4 equal quarters."""
    n = len(facts)
    q_size = n // 4
    return [
        facts[:q_size],
        facts[q_size:2*q_size],
        facts[2*q_size:3*q_size],
        facts[3*q_size:],
    ]


def main():
    log("=" * 70)
    log("TEMPORAL STABILITY RERUN — Aarik's GPT Conversations")
    log("Testing: Do S78 findings hold on linear conversation data?")
    log("=" * 70)

    all_facts = load_facts_with_timestamps()
    log(f"Loaded: {len(all_facts)} identity-tier facts with timestamps")

    ts_start = datetime.fromtimestamp(all_facts[0]["timestamp"]).strftime("%Y-%m-%d")
    ts_end = datetime.fromtimestamp(all_facts[-1]["timestamp"]).strftime("%Y-%m-%d")
    log(f"Date range: {ts_start} to {ts_end}")

    quarters = split_quarters(all_facts)
    for i, q in enumerate(quarters):
        d1 = datetime.fromtimestamp(q[0]["timestamp"]).strftime("%Y-%m")
        d2 = datetime.fromtimestamp(q[-1]["timestamp"]).strftime("%Y-%m")
        log(f"  Q{i+1}: {len(q)} facts ({d1} to {d2})")

    results = {
        "meta": {
            "started": datetime.now().isoformat(),
            "model": "claude-sonnet-4-20250514",
            "subject": "aarik",
            "source": "GPT conversations (linear)",
            "total_facts": len(all_facts),
            "date_range": f"{ts_start} to {ts_end}",
            "quarter_sizes": [len(q) for q in quarters],
        },
        "experiments": {},
    }

    # ========================================
    # EXP 1: TEMPORAL DIRECTION
    # Franklin finding: no direction effect (<2% difference)
    # Hypothesis: conversation data may show direction effect (real temporal drift)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 1: TEMPORAL DIRECTION — Early->Late vs Late->Early")
    log("=" * 70)
    exp1 = []

    mid = len(all_facts) // 2
    early = all_facts[:mid]
    late = all_facts[mid:]

    r1 = run_condition(early, late, "early_to_late")
    exp1.append(r1)
    r2 = run_condition(late, early, "late_to_early")
    exp1.append(r2)

    # Middle -> edges
    q1_end = len(all_facts) // 4
    q3_start = 3 * len(all_facts) // 4
    middle = all_facts[q1_end:q3_start]
    edges = all_facts[:q1_end] + all_facts[q3_start:]
    r3 = run_condition(middle, edges, "middle_to_edges")
    exp1.append(r3)

    # Random baseline
    random.seed(42)
    rand_shuf = all_facts[:]
    random.shuffle(rand_shuf)
    r4 = run_condition(rand_shuf[:mid], rand_shuf[mid:], "random_baseline")
    exp1.append(r4)

    results["experiments"]["1_temporal_direction"] = exp1

    # ========================================
    # EXP 2: QUARTER PREDICTION
    # Franklin finding: Q1 (23.01) > Q2 (21.24) > Q3 (19.4) ~ Q4 (20.82)
    # Hypothesis: Q4 may be stronger predictor (more data, mature patterns)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 2: QUARTER PREDICTION — Each Q predicts remaining")
    log("=" * 70)
    exp2 = []

    for i in range(4):
        train = quarters[i]
        test = [f for j, q in enumerate(quarters) for f in q if j != i]
        r = run_condition(train, test, f"Q{i+1}_predicts_rest")
        r["quarter"] = i + 1
        exp2.append(r)

    results["experiments"]["2_quarter_prediction"] = exp2

    # ========================================
    # EXP 3: BIDIRECTIONAL ACCUMULATION
    # Franklin finding: Q1 alone outperforms Q1+Q2+Q3 for predicting Q4
    # Hypothesis: may not hold for conversation data (cumulative context helps)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 3: ACCUMULATION — Does adding more temporal data help?")
    log("=" * 70)
    exp3 = []

    # Forward accumulation: predict Q4
    for n_q in range(1, 4):
        train = [f for i in range(n_q) for f in quarters[i]]
        test = quarters[3]
        r = run_condition(train, test, f"Q1..Q{n_q}_predicts_Q4")
        exp3.append(r)

    # Reverse accumulation: predict Q1
    for n_q in range(1, 4):
        train = [f for i in range(4-n_q, 4) for f in quarters[i]]
        test = quarters[0]
        r = run_condition(train, test, f"Q{5-n_q}..Q4_predicts_Q1")
        exp3.append(r)

    results["experiments"]["3_accumulation"] = exp3

    # ========================================
    # EXP 4: CROSS-TYPE PREDICTION
    # S78 finding: behavioral facts are strongest predictors
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 4: CROSS-TYPE — Which fact types predict best?")
    log("=" * 70)
    exp4 = []

    by_type = {}
    for f in all_facts:
        by_type.setdefault(f.get("fact_type", "unknown"), []).append(f)

    log(f"  Fact types: {', '.join(f'{k}={len(v)}' for k,v in by_type.items())}")

    for ft, ft_facts in by_type.items():
        if len(ft_facts) < 10:
            continue
        other_facts = [f for f in all_facts if f.get("fact_type") != ft]
        if len(other_facts) < 10:
            continue
        r = run_condition(ft_facts, other_facts, f"type_{ft}_predicts_others")
        exp4.append(r)

    results["experiments"]["4_cross_type"] = exp4

    # ========================================
    # SUMMARY
    # ========================================
    log("\n" + "=" * 70)
    log("SUMMARY — Aarik (Conversations) vs Franklin (Autobiography)")
    log("=" * 70)

    franklin_ref = {
        "temporal_direction": {"early_to_late": 20.25, "late_to_early": 22.0, "random": 19.93},
        "quarter_prediction": {"Q1": 23.01, "Q2": 21.24, "Q3": 19.4, "Q4": 20.82},
        "finding": "No significant direction effect. Later predicts earlier slightly better.",
    }

    log("\n  FRANKLIN (autobiography, Sonnet):")
    log(f"    early->late: {franklin_ref['temporal_direction']['early_to_late']}")
    log(f"    late->early: {franklin_ref['temporal_direction']['late_to_early']}")
    log(f"    random: {franklin_ref['temporal_direction']['random']}")

    log("\n  AARIK (conversations, Sonnet):")
    if exp1:
        for r in exp1:
            comp = r.get("scores", {}).get("composite", 0)
            log(f"    {r['label']}: {comp:.1f}")

    if exp1 and len(exp1) >= 2:
        e2l = exp1[0].get("scores", {}).get("composite", 0)
        l2e = exp1[1].get("scores", {}).get("composite", 0)
        diff = abs(e2l - l2e)
        log(f"\n  Direction effect: {diff:.1f} composite points")
        if diff < 3:
            log("  CONFIRMED: No significant temporal direction effect (< 3 pts)")
        else:
            log(f"  DIVERGENCE: {diff:.1f} pts > 3 threshold. Conversation data shows temporal drift.")
            if l2e > e2l:
                log("  Later patterns predict earlier behavior better (consistent with Franklin)")
            else:
                log("  NOVEL: Earlier patterns predict later behavior better (opposite of Franklin)")

    if exp3:
        log("\n  ACCUMULATION (forward, predicting Q4):")
        fwd = [r for r in exp3 if "predicts_Q4" in r["label"]]
        for r in fwd:
            comp = r.get("scores", {}).get("composite", 0)
            log(f"    {r['label']}: {comp:.1f}")

        if len(fwd) >= 3:
            q1_only = fwd[0].get("scores", {}).get("composite", 0)
            q123 = fwd[2].get("scores", {}).get("composite", 0)
            if q1_only > q123:
                log("  CONFIRMED: Q1 alone outperforms Q1+Q2+Q3 (more data hurts)")
            else:
                log("  DIVERGENCE: Q1+Q2+Q3 outperforms Q1 alone (accumulation helps for conversations)")

    results["franklin_reference"] = franklin_ref

    # Save results
    results_path = os.path.join(OUTPUT_DIR, "temporal_stability_aarik_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    log(f"\nResults saved: {results_path}")


if __name__ == "__main__":
    main()
