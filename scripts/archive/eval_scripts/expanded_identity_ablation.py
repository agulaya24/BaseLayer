"""
Expanded Identity-Tier Ablation — Deep dive into identity fact subtypes + temporal experiments.

Tests:
  1. Identity fact subtype isolation (behavioral-identity, biographical-identity, etc.)
  2. Predicate clusters within identity tier (epistemic vs capability vs experiential)
  3. Temporal windows (quarters of autobiography) — which quarter predicts best?
  4. Bidirectional temporal: train on Q1 -> predict Q4, train on Q4 -> predict Q1, etc.
  5. Temporal accumulation: Q1 only, Q1+Q2, Q1+Q2+Q3, all — when does compression saturate?
  6. High-commitment vs low-commitment identity facts

Subject: Franklin (identity-tier facts)
Cost: ~$3-5 (Sonnet brief gen, mechanical scoring)
"""

import sys
import os
import json
import random
import re
import numpy as np
from datetime import datetime
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
FRANKLIN_DB = os.path.join(_HOME, "subjects", "franklin_memory", "data", "database", "memory.db")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "expanded_ablation")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")

import sqlite3


def load_identity_facts():
    conn = sqlite3.connect(FRANKLIN_DB)
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, commitment_depth,
               predicate, object_text, recurrence_count, depth_score
        FROM memory_facts
        WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        ORDER BY id
    """).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
             "commitment_depth": r[4], "predicate": r[5], "object_text": r[6],
             "recurrence_count": r[7], "depth_score": r[8]} for r in rows]


def embed_texts(texts):
    if not texts: return np.array([])
    vecs = EMBED_MODEL.encode(texts, show_progress_bar=False)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def score_brief(brief_text, held_out_facts):
    if not brief_text or not held_out_facts:
        return {"composite": 0, "prediction_rate": 0, "m1_coverage": 0}
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
            "m3_pattern_density": round(m3, 2), "composite": composite, "chars": len(brief_text)}


BRIEF_SYSTEM = """You generate behavioral briefs from structured facts about a person.
The brief is injected into an AI's system prompt so it understands this person.
RULES:
- Use he/him pronouns. Refer to subject as "this person" or "he."
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
            caller=f"exp_ablation_{label}",
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
    log(f"  {label}: {len(train_facts)} train -> {len(test_facts)} test")
    brief = generate_brief(train_facts, label)
    if not brief:
        return {"label": label, "error": "generation failed"}
    scores = score_brief(brief, test_facts)
    log(f"    composite={scores['composite']:.1f}  m1={scores['m1_coverage']:.3f}  pred={scores['prediction_rate']:.1%}")
    return {"label": label, "train_count": len(train_facts), "test_count": len(test_facts),
            "scores": scores, "brief_preview": brief[:200]}


def main():
    log("=" * 70)
    log("EXPANDED IDENTITY-TIER ABLATION + TEMPORAL EXPERIMENTS")
    log("=" * 70)

    facts = load_identity_facts()
    log(f"Identity-tier facts: {len(facts)}")

    # Distribution info
    by_type = {}
    by_pred = {}
    by_commit = {}
    for f in facts:
        by_type.setdefault(f.get("fact_type", "?"), []).append(f)
        by_pred.setdefault(f.get("predicate", "?"), []).append(f)
        cd = f.get("commitment_depth", "?")
        by_commit.setdefault(cd, []).append(f)

    log(f"Types: {', '.join(f'{k}={len(v)}' for k,v in sorted(by_type.items(), key=lambda x: -len(x[1])))}")
    log(f"Commitment depths: {', '.join(f'{k}={len(v)}' for k,v in sorted(by_commit.items(), key=lambda x: -len(x[1])))}")
    log(f"Unique predicates: {len(by_pred)}")

    results = {"meta": {"started": datetime.now().isoformat(), "total_facts": len(facts),
                        "type_dist": {k: len(v) for k, v in by_type.items()},
                        "commit_dist": {str(k): len(v) for k, v in by_commit.items()}},
               "experiments": {}}

    # ========================================
    # EXP 1: IDENTITY FACT SUBTYPE ISOLATION
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 1: IDENTITY FACT SUBTYPE ISOLATION")
    log("=" * 70)
    exp1 = []
    for ft, ft_facts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(ft_facts) < 5:
            log(f"  Skipping {ft}: only {len(ft_facts)} facts")
            continue
        other = [f for f in facts if f.get("fact_type") != ft]
        r = run_condition(ft_facts, other, f"subtype_{ft}")
        r["fact_type"] = ft
        r["pct_of_total"] = round(len(ft_facts) / len(facts) * 100, 1)
        exp1.append(r)
    results["experiments"]["1_subtype_isolation"] = exp1

    # ========================================
    # EXP 2: PREDICATE CLUSTERS WITHIN IDENTITY TIER
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 2: PREDICATE CLUSTERS (epistemic vs capability vs experiential)")
    log("=" * 70)
    exp2 = []

    clusters = {
        "epistemic": ["believes", "values", "prioritizes"],
        "capability": ["practices", "excels_at", "demonstrates"],
        "experiential": ["experienced", "achieved", "founded", "contributed_to"],
        "avoidance": ["avoids", "struggles_with", "dislikes"],
        "relational": ["friends_with", "mentored_by", "admires", "collaborates_with", "advocates", "advocated_for"],
        "preference": ["prefers", "interested_in", "enjoys"],
    }

    for cname, preds in clusters.items():
        cfacts = [f for f in facts if f.get("predicate") in preds]
        if len(cfacts) < 3:
            log(f"  Skipping {cname}: only {len(cfacts)} facts")
            continue
        other = [f for f in facts if f not in cfacts]
        r = run_condition(cfacts, other, f"cluster_{cname}")
        r["predicates"] = preds
        r["predicate_counts"] = {p: sum(1 for f in cfacts if f.get("predicate") == p) for p in preds}
        exp2.append(r)
    results["experiments"]["2_predicate_clusters"] = exp2

    # ========================================
    # EXP 3: TEMPORAL WINDOWS (4 quarters)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 3: TEMPORAL WINDOWS — Which quarter predicts best?")
    log("=" * 70)
    exp3 = []

    sorted_facts = sorted(facts, key=lambda f: f["id"])
    q_size = len(sorted_facts) // 4
    quarters = {
        "Q1_early": sorted_facts[:q_size],
        "Q2_mid_early": sorted_facts[q_size:2*q_size],
        "Q3_mid_late": sorted_facts[2*q_size:3*q_size],
        "Q4_late": sorted_facts[3*q_size:],
    }

    for qname, qfacts in quarters.items():
        other = [f for f in sorted_facts if f not in qfacts]
        r = run_condition(qfacts, other, f"quarter_{qname}")
        r["quarter"] = qname
        r["id_range"] = f"{qfacts[0]['id']}-{qfacts[-1]['id']}"
        exp3.append(r)
    results["experiments"]["3_temporal_windows"] = exp3

    # ========================================
    # EXP 4: BIDIRECTIONAL TEMPORAL PAIRS
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 4: BIDIRECTIONAL TEMPORAL — Q1->Q4 vs Q4->Q1 etc.")
    log("=" * 70)
    exp4 = []

    pairs = [
        ("Q1->Q4", quarters["Q1_early"], quarters["Q4_late"]),
        ("Q4->Q1", quarters["Q4_late"], quarters["Q1_early"]),
        ("Q1->Q3", quarters["Q1_early"], quarters["Q3_mid_late"]),
        ("Q3->Q1", quarters["Q3_mid_late"], quarters["Q1_early"]),
        ("Q2->Q4", quarters["Q2_mid_early"], quarters["Q4_late"]),
        ("Q4->Q2", quarters["Q4_late"], quarters["Q2_mid_early"]),
    ]

    for label, train, test in pairs:
        r = run_condition(train, test, f"bidir_{label}")
        exp4.append(r)

    results["experiments"]["4_bidirectional_temporal"] = exp4

    # ========================================
    # EXP 5: TEMPORAL ACCUMULATION
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 5: TEMPORAL ACCUMULATION — When does compression saturate?")
    log("=" * 70)
    exp5 = []

    # Always test against Q4
    test_set = quarters["Q4_late"]

    accumulations = [
        ("Q1_only", quarters["Q1_early"]),
        ("Q1+Q2", quarters["Q1_early"] + quarters["Q2_mid_early"]),
        ("Q1+Q2+Q3", quarters["Q1_early"] + quarters["Q2_mid_early"] + quarters["Q3_mid_late"]),
        ("all_quarters", sorted_facts),
    ]

    for label, train in accumulations:
        # Remove test facts from train
        test_ids = {f["id"] for f in test_set}
        clean_train = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean_train, test_set, f"accum_{label}")
        r["train_quarters"] = label
        exp5.append(r)

    results["experiments"]["5_temporal_accumulation"] = exp5

    # ========================================
    # EXP 6: COMMITMENT DEPTH
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 6: COMMITMENT DEPTH — High vs Low commitment facts")
    log("=" * 70)
    exp6 = []

    # Sort by commitment depth
    with_depth = [f for f in facts if f.get("commitment_depth") is not None]
    if with_depth:
        # Try numeric first
        try:
            depth_sorted = sorted(with_depth, key=lambda f: float(f["commitment_depth"]), reverse=True)
            mid = len(depth_sorted) // 2
            high_commit = depth_sorted[:mid]
            low_commit = depth_sorted[mid:]
        except (ValueError, TypeError):
            # Non-numeric — group by string value
            unique_depths = sorted(set(f["commitment_depth"] for f in with_depth))
            log(f"  Commitment depth values: {unique_depths}")
            if len(unique_depths) >= 2:
                mid_idx = len(unique_depths) // 2
                high_vals = set(unique_depths[mid_idx:])
                low_vals = set(unique_depths[:mid_idx])
                high_commit = [f for f in with_depth if f["commitment_depth"] in high_vals]
                low_commit = [f for f in with_depth if f["commitment_depth"] in low_vals]
            else:
                high_commit = with_depth[:len(with_depth)//2]
                low_commit = with_depth[len(with_depth)//2:]

        random.seed(42)
        test_pool = facts[:]
        random.shuffle(test_pool)
        test_set_6 = test_pool[:len(test_pool)//3]
        high_clean = [f for f in high_commit if f not in test_set_6]
        low_clean = [f for f in low_commit if f not in test_set_6]

        if high_clean and low_clean:
            r_high = run_condition(high_clean, test_set_6, "high_commitment")
            r_high["depth_range"] = "high"
            exp6.append(r_high)

            r_low = run_condition(low_clean, test_set_6, "low_commitment")
            r_low["depth_range"] = "low"
            exp6.append(r_low)
    else:
        log("  No commitment_depth data available")

    results["experiments"]["6_commitment_depth"] = exp6

    # ========================================
    # ANALYSIS
    # ========================================
    log("\n" + "=" * 70)
    log("ANALYSIS SUMMARY")
    log("=" * 70)

    for ename, edata in results["experiments"].items():
        if not edata:
            continue
        valid = [x for x in edata if "scores" in x]
        if not valid:
            continue
        best = max(valid, key=lambda x: x["scores"].get("composite", 0))
        worst = min(valid, key=lambda x: x["scores"].get("composite", 0))
        log(f"\n  {ename}:")
        log(f"    Best:  {best['label']} (composite={best['scores']['composite']:.1f}, pred={best['scores']['prediction_rate']:.1%})")
        log(f"    Worst: {worst['label']} (composite={worst['scores']['composite']:.1f}, pred={worst['scores']['prediction_rate']:.1%})")

    # Temporal direction check
    if len(exp4) >= 2:
        log("\n  BIDIRECTIONAL TEMPORAL PAIRS:")
        for i in range(0, len(exp4), 2):
            if i+1 < len(exp4):
                fwd = exp4[i]
                bwd = exp4[i+1]
                fwd_pred = fwd.get("scores", {}).get("prediction_rate", 0)
                bwd_pred = bwd.get("scores", {}).get("prediction_rate", 0)
                diff = abs(fwd_pred - bwd_pred)
                log(f"    {fwd['label']}: {fwd_pred:.1%} vs {bwd['label']}: {bwd_pred:.1%} (diff={diff:.1%})")

    # Accumulation curve
    if exp5:
        log("\n  TEMPORAL ACCUMULATION CURVE:")
        for r in exp5:
            pred = r.get("scores", {}).get("prediction_rate", 0)
            log(f"    {r['label']}: train={r['train_count']}, pred={pred:.1%}")

    results["meta"]["completed"] = datetime.now().isoformat()
    path = os.path.join(OUTPUT_DIR, "expanded_ablation_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
