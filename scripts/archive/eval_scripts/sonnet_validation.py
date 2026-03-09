"""
Sonnet Validation — Parallel validation of key Qwen overnight findings.
Uses Sonnet for brief generation AND mechanical scoring to verify Qwen results aren't Qwen-specific.

Tests (smaller, focused):
  1. Compression saturation: 10%, 20%, 50% splits (does 20% still peak?)
  2. Temporal direction: early->late vs late->early (still no direction effect?)
  3. Cross-type prediction: biographical vs behavioral vs positional (biographical still best?)
  4. Tier comparison: identity-only vs all-tiers (identity still 2.5x better?)

Subject: Franklin
Cost: ~$2-3 (Sonnet brief gen, mechanical scoring)
"""

import sys
import os
import json
import random
import re
import numpy as np
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
FRANKLIN_DB = os.path.join(_HOME, "subjects", "franklin_memory", "data", "database", "memory.db")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "sonnet_validation")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")

import sqlite3


def load_all_facts():
    """Load ALL facts (not just identity-tier) for cross-tier comparison."""
    conn = sqlite3.connect(FRANKLIN_DB)
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, predicate, object_text
        FROM memory_facts WHERE superseded_by IS NULL
        ORDER BY id
    """).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
             "predicate": r[4], "object_text": r[5]} for r in rows]


def embed_texts(texts):
    if not texts: return np.array([])
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
- Use he/him pronouns. Refer to subject as "this person" or "he."
- Structure as annotated guide with section headers and "When X, do Y" patterns.
- Target: 1500-2500 characters. Dense, specific, actionable.
- Do NOT name the person."""


def generate_brief_sonnet(facts, label):
    fact_lines = "\n".join([f"- [{f.get('predicate', '?')}] {f['fact_text']}" for f in facts])
    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=BRIEF_SYSTEM,
            messages=[{"role": "user", "content": f"Generate a behavioral brief from these {len(facts)} facts:\n\n{fact_lines}"}],
            max_tokens=2048, temperature=0.3,
            caller=f"sonnet_val_{label}",
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
    brief = generate_brief_sonnet(train_facts, label)
    if not brief:
        return {"label": label, "error": "generation failed"}
    scores = score_brief(brief, test_facts)
    log(f"    composite={scores['composite']:.1f}  m1={scores['m1_coverage']:.3f}  pred={scores['prediction_rate']:.1%}")
    return {"label": label, "train_count": len(train_facts), "test_count": len(test_facts),
            "scores": scores, "brief_preview": brief[:200]}


def main():
    log("=" * 70)
    log("SONNET VALIDATION — Verify Qwen Findings with Sonnet")
    log("=" * 70)

    all_facts = load_all_facts()
    identity_facts = [f for f in all_facts if f["knowledge_tier"] == "identity"]
    log(f"Total facts: {len(all_facts)}, Identity-tier: {len(identity_facts)}")

    results = {"meta": {"started": datetime.now().isoformat(), "model": "claude-sonnet-4-20250514",
                        "total_facts": len(all_facts), "identity_facts": len(identity_facts)},
               "experiments": {}}

    # ========================================
    # EXP 1: COMPRESSION SATURATION (Qwen found: peak at 20%)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 1: COMPRESSION SATURATION — Does 20% still peak with Sonnet?")
    log("=" * 70)
    exp1 = []
    random.seed(42)
    shuffled = identity_facts[:]
    random.shuffle(shuffled)

    for pct in [10, 20, 50]:
        n = max(3, int(len(identity_facts) * pct / 100))
        train = shuffled[:n]
        test = shuffled[n:]
        r = run_condition(train, test, f"split_{pct}pct")
        r["split_pct"] = pct
        exp1.append(r)
    results["experiments"]["1_compression_saturation"] = exp1

    # ========================================
    # EXP 2: TEMPORAL DIRECTION (Qwen found: no direction effect)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 2: TEMPORAL DIRECTION — Early->Late vs Late->Early")
    log("=" * 70)
    exp2 = []

    # Sort by ID as proxy for temporal order (extraction order ~ autobiography order)
    sorted_facts = sorted(identity_facts, key=lambda f: f["id"])
    mid = len(sorted_facts) // 2
    early = sorted_facts[:mid]
    late = sorted_facts[mid:]

    r1 = run_condition(early, late, "early_to_late")
    exp2.append(r1)
    r2 = run_condition(late, early, "late_to_early")
    exp2.append(r2)

    # Middle -> edges
    q1 = len(sorted_facts) // 4
    q3 = 3 * len(sorted_facts) // 4
    middle = sorted_facts[q1:q3]
    edges = sorted_facts[:q1] + sorted_facts[q3:]
    r3 = run_condition(middle, edges, "middle_to_edges")
    exp2.append(r3)

    # Random baseline (for comparison)
    random.seed(99)
    rand_shuf = identity_facts[:]
    random.shuffle(rand_shuf)
    r4 = run_condition(rand_shuf[:mid], rand_shuf[mid:], "random_baseline")
    exp2.append(r4)

    results["experiments"]["2_temporal_direction"] = exp2

    # ========================================
    # EXP 3: CROSS-TYPE PREDICTION (Qwen found: biographical best at 26.7%)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 3: CROSS-TYPE PREDICTION — Which fact types predict others?")
    log("=" * 70)
    exp3 = []

    by_type = {}
    for f in identity_facts:
        by_type.setdefault(f.get("fact_type", "?"), []).append(f)

    for ft, ft_facts in by_type.items():
        if len(ft_facts) < 5:
            continue
        other_facts = [f for f in identity_facts if f.get("fact_type") != ft]
        if len(other_facts) < 5:
            continue
        r = run_condition(ft_facts, other_facts, f"type_{ft}_predicts_others")
        exp3.append(r)

    # All types baseline
    random.seed(77)
    all_shuf = identity_facts[:]
    random.shuffle(all_shuf)
    r_all = run_condition(all_shuf[:len(all_shuf)//2], all_shuf[len(all_shuf)//2:], "all_types_baseline")
    exp3.append(r_all)
    results["experiments"]["3_cross_type"] = exp3

    # ========================================
    # EXP 4: TIER COMPARISON (Qwen found: identity-only 2.5x better than all-tiers)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 4: TIER COMPARISON — Identity-only vs All Tiers")
    log("=" * 70)
    exp4 = []

    by_tier = {}
    for f in all_facts:
        by_tier.setdefault(f.get("knowledge_tier", "?"), []).append(f)

    log(f"  Tiers: {', '.join(f'{k}={len(v)}' for k,v in by_tier.items())}")

    # Identity-only -> predict random held-out identity facts
    random.seed(55)
    id_shuf = identity_facts[:]
    random.shuffle(id_shuf)
    id_train = id_shuf[:len(id_shuf)//2]
    id_test = id_shuf[len(id_shuf)//2:]

    r_id = run_condition(id_train, id_test, "identity_only")
    exp4.append(r_id)

    # All tiers -> predict same held-out identity facts
    non_id = [f for f in all_facts if f["knowledge_tier"] != "identity"]
    random.shuffle(non_id)
    # Same number of train facts, but from all tiers
    all_tier_train = non_id[:len(id_train)] if len(non_id) >= len(id_train) else non_id
    r_all = run_condition(all_tier_train, id_test, "non_identity_tiers")
    exp4.append(r_all)

    # Mixed: identity + some context/situational
    mixed_train = id_train[:len(id_train)//2] + non_id[:len(id_train)//2]
    r_mix = run_condition(mixed_train, id_test, "mixed_tiers")
    exp4.append(r_mix)

    results["experiments"]["4_tier_comparison"] = exp4

    # ========================================
    # SUMMARY
    # ========================================
    log("\n" + "=" * 70)
    log("SUMMARY — Qwen vs Sonnet Comparison")
    log("=" * 70)

    qwen_findings = {
        "compression_peak": "20%",
        "temporal_direction": "no effect (early=late=random)",
        "best_cross_type": "biographical (26.7%)",
        "tier_winner": "identity-only (2.5x better)",
    }

    # Check compression
    if exp1:
        best_split = max(exp1, key=lambda x: x.get("scores", {}).get("prediction_rate", 0))
        log(f"  Compression peak: {best_split.get('split_pct', '?')}% (Qwen: 20%)")

    # Check temporal
    if len(exp2) >= 2:
        e2l = exp2[0].get("scores", {}).get("prediction_rate", 0)
        l2e = exp2[1].get("scores", {}).get("prediction_rate", 0)
        diff = abs(e2l - l2e)
        log(f"  Temporal: early->late={e2l:.1%}, late->early={l2e:.1%}, diff={diff:.1%} (Qwen: ~0%)")

    # Check cross-type
    if exp3:
        valid = [x for x in exp3 if "type_" in x.get("label", "")]
        if valid:
            best_type = max(valid, key=lambda x: x.get("scores", {}).get("prediction_rate", 0))
            log(f"  Best cross-type: {best_type['label']} pred={best_type['scores']['prediction_rate']:.1%} (Qwen: biographical 26.7%)")

    # Check tier
    if exp4:
        for r in exp4:
            log(f"  Tier {r['label']}: pred={r.get('scores', {}).get('prediction_rate', 0):.1%}")

    results["meta"]["completed"] = datetime.now().isoformat()
    results["meta"]["qwen_comparison"] = qwen_findings

    path = os.path.join(OUTPUT_DIR, "sonnet_validation_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
