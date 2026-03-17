"""
Predicate & Fact Type Quality Ablation — Mechanical Scoring
============================================================
Finds which facts and predicates produce the best brief output.
ALL scoring is mechanical — no LLM-as-judge.

Metrics:
  M1: EMBEDDING COVERAGE — avg cosine similarity of brief embedding to held-out fact embeddings
  M2: CROSS-PREDICTION — % of held-out facts whose embedding is within top-K nearest to brief
  M3: PATTERN DENSITY — count of actionable patterns per 1000 chars (regex-based)
  M4: SPECIFICITY — ratio of unique n-grams vs common English n-grams
  M5: EFFICIENCY — M1 score / token count (coverage per token)

Experiments:
  1. Fact type isolation (biographical, behavioral, positional, preference)
  2. Predicate group isolation (epistemic, behavioral, experiential, relational, preference)
  3. Individual predicate isolation (values, believes, practices, excels_at, etc.)
  4. Additive value (epistemic base + one group at a time)
  5. Optimal combinations
  6. Baseline comparison (production brief)

Subject: Franklin (135 identity-tier facts)
Cost: ~$1-2 total (Sonnet brief generation only, all scoring is local/free)
"""

import sys
import os
import json
import time
import sqlite3
import random
import re
import numpy as np
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
FRANKLIN_DB = os.path.join(_HOME, "subjects", "franklin_memory", "data", "database", "memory.db")
FRANKLIN_BRIEF = os.path.join(_HOME, "subjects", "franklin_memory", "data", "identity_layers", "brief_v4.md")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "predicate_ablation")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load embedding model once
print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Embedding model ready.")


# ============================================================
# DATA
# ============================================================

def load_facts():
    conn = sqlite3.connect(FRANKLIN_DB)
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, commitment_depth,
               predicate, object_text, subject
        FROM memory_facts
        WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        ORDER BY id
    """).fetchall()
    conn.close()
    return [
        {"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
         "commitment_depth": r[4], "predicate": r[5], "object_text": r[6], "subject": r[7]}
        for r in rows
    ]


def load_baseline_brief():
    if not os.path.exists(FRANKLIN_BRIEF):
        return None
    with open(FRANKLIN_BRIEF, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()
    return text.replace("## Injectable Block\n\n", "").replace("## Injectable Block\n", "")


# ============================================================
# BRIEF GENERATION (Sonnet — only LLM call)
# ============================================================

BRIEF_GEN_SYSTEM = """You generate behavioral briefs from structured facts about a person.
The brief is injected into an AI's system prompt so it understands this person.

RULES:
- Every sentence must change how an AI responds. No filler.
- Use he/him pronouns. Refer to subject as "this person" or "he."
- Focus on behavioral patterns, reasoning tendencies, decision-making, failure modes.
- Structure: ANCHORS (axioms) → CORE (operations) → PREDICTIONS (trigger→behavior).
- Target: 1500-2500 characters. Dense, specific, actionable.
- Do NOT name the person."""


def generate_brief(facts, condition_name):
    fact_lines = "\n".join([f"- [{f['predicate']}] {f['fact_text']}" for f in facts])
    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=BRIEF_GEN_SYSTEM,
            messages=[{"role": "user", "content": f"Generate a behavioral brief from these {len(facts)} facts:\n\n{fact_lines}"}],
            max_tokens=2048, temperature=0.3,
            caller=f"pred_ablation_{condition_name}",
        )
        return resp.content[0].text
    except Exception as e:
        log(f"  Brief gen failed for {condition_name}: {e}")
        return None


# ============================================================
# MECHANICAL SCORING
# ============================================================

def embed_texts(texts):
    """Embed a list of texts, return normalized vectors."""
    if not texts:
        return np.array([])
    vecs = EMBED_MODEL.encode(texts, show_progress_bar=False)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def cosine_sim(a, b):
    """Cosine similarity between two vectors."""
    return float(np.dot(a, b))


def m1_embedding_coverage(brief_text, held_out_facts):
    """M1: Average cosine similarity of brief to each held-out fact.
    Higher = brief captures more of the information in held-out facts."""
    if not held_out_facts or not brief_text:
        return 0.0

    # Embed brief as one document
    brief_vec = embed_texts([brief_text])[0]

    # Embed each held-out fact
    fact_texts = [f["fact_text"] for f in held_out_facts]
    fact_vecs = embed_texts(fact_texts)

    # Average similarity
    sims = [cosine_sim(brief_vec, fv) for fv in fact_vecs]
    return round(float(np.mean(sims)), 4)


def m2_cross_prediction(brief_text, held_out_facts, threshold=0.45):
    """M2: % of held-out facts with cosine similarity > threshold to the brief.
    Binary: either the brief semantically covers this fact or it doesn't."""
    if not held_out_facts or not brief_text:
        return 0.0

    brief_vec = embed_texts([brief_text])[0]
    fact_texts = [f["fact_text"] for f in held_out_facts]
    fact_vecs = embed_texts(fact_texts)

    hits = sum(1 for fv in fact_vecs if cosine_sim(brief_vec, fv) > threshold)
    return round(hits / len(held_out_facts), 4)


def m3_pattern_density(brief_text):
    """M3: Count of actionable patterns per 1000 chars.
    Patterns: trigger→behavior, when/if conditionals, explicit predictions."""
    if not brief_text:
        return 0.0

    patterns = [
        r'\bwhen\b.*\b(he|they|this person)\b',     # when...he...
        r'\bif\b.*\b(he|they|this person)\b',        # if...he...
        r'\btrigger\b',                               # explicit trigger word
        r'\btend[s]?\s+to\b',                         # tends to
        r'\bwill\s+(likely|often|always|typically)\b', # will likely
        r'\bexpect\b',                                 # expect
        r'\bpredict\b',                                # predict
        r'\bdefault[s]?\s+to\b',                       # defaults to
        r'\brather\s+than\b',                          # rather than (preference)
        r'\bnever\b',                                  # never (strong behavioral)
        r'\balways\b',                                 # always (strong behavioral)
        r'\bfailure\s+mode\b',                         # failure mode
        r'\bblind\s+spot\b',                           # blind spot
        r'\baxiom\b',                                  # axiom
    ]

    count = 0
    text_lower = brief_text.lower()
    for pat in patterns:
        count += len(re.findall(pat, text_lower))

    chars = max(len(brief_text), 1)
    return round(count / (chars / 1000), 2)


def m4_specificity(brief_text):
    """M4: Ratio of uncommon bigrams to total bigrams.
    Generic briefs reuse common phrases. Specific briefs have unique constructions."""
    if not brief_text:
        return 0.0

    # Common/generic bigrams that could describe anyone
    generic = {
        "this person", "he is", "they are", "tends to", "in order",
        "as well", "such as", "for example", "in the", "of the",
        "to the", "and the", "is a", "with a", "has a", "on the",
        "at the", "it is", "that the", "from the", "by the",
    }

    words = re.findall(r'\b\w+\b', brief_text.lower())
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    if not bigrams:
        return 0.0

    generic_count = sum(1 for b in bigrams if b in generic)
    return round(1 - (generic_count / len(bigrams)), 4)


def m5_efficiency(m1_score, brief_text):
    """M5: Coverage per token. M1 / estimated token count * 1000."""
    if not brief_text:
        return 0.0
    tokens_est = len(brief_text) // 4
    if tokens_est == 0:
        return 0.0
    return round(m1_score / tokens_est * 1000, 4)


def score_brief(brief_text, held_out_facts):
    """Run all mechanical metrics on a brief."""
    m1 = m1_embedding_coverage(brief_text, held_out_facts)
    m2 = m2_cross_prediction(brief_text, held_out_facts)
    m3 = m3_pattern_density(brief_text)
    m4 = m4_specificity(brief_text)
    m5 = m5_efficiency(m1, brief_text)

    # Composite: weighted sum normalized to 0-100
    # M1 (0-1) weight 40, M2 (0-1) weight 25, M3 (0-20ish) weight 15, M4 (0-1) weight 10, M5 weight 10
    composite = (
        m1 * 40 +
        m2 * 25 +
        min(m3 / 10, 1) * 15 +  # cap pattern density contribution
        m4 * 10 +
        min(m5 / 2, 1) * 10     # cap efficiency contribution
    )

    return {
        "m1_embedding_coverage": m1,
        "m2_cross_prediction": m2,
        "m3_pattern_density": m3,
        "m4_specificity": m4,
        "m5_efficiency": m5,
        "composite": round(composite, 2),
    }


# ============================================================
# EXPERIMENT RUNNER
# ============================================================

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_condition(train_facts, all_facts, condition_name):
    """Generate brief from train_facts, score against held-out facts."""
    held_out = [f for f in all_facts if f not in train_facts]

    log(f"  {condition_name}: {len(train_facts)} train, {len(held_out)} held-out")

    brief = generate_brief(train_facts, condition_name)
    if not brief:
        return {"condition": condition_name, "error": "generation failed"}

    scores = score_brief(brief, held_out)

    # Distribution info
    pred_dist = Counter(f.get("predicate", "?") for f in train_facts)
    type_dist = Counter(f.get("fact_type", "?") for f in train_facts)

    result = {
        "condition": condition_name,
        "train_count": len(train_facts),
        "held_out_count": len(held_out),
        "brief_chars": len(brief),
        "brief_tokens_est": len(brief) // 4,
        "scores": scores,
        "composite": scores["composite"],
        "predicate_dist": dict(pred_dist.most_common()),
        "type_dist": dict(type_dist),
        "brief_preview": brief[:200],
    }

    log(f"    composite={scores['composite']:.1f}  m1={scores['m1_embedding_coverage']:.3f}  m2={scores['m2_cross_prediction']:.1%}  m3={scores['m3_pattern_density']:.1f}  chars={len(brief)}")
    return result


def run_baseline(brief_text, all_facts):
    """Score an existing brief (no generation needed)."""
    scores = score_brief(brief_text, all_facts)
    return {
        "condition": "production_baseline",
        "train_count": len(all_facts),
        "held_out_count": 0,
        "brief_chars": len(brief_text),
        "brief_tokens_est": len(brief_text) // 4,
        "scores": scores,
        "composite": scores["composite"],
        "brief_preview": brief_text[:200],
    }


def main():
    log("=" * 70)
    log("PREDICATE & FACT TYPE QUALITY ABLATION — MECHANICAL SCORING")
    log("=" * 70)

    all_facts = load_facts()
    baseline_brief = load_baseline_brief()
    log(f"Loaded {len(all_facts)} identity-tier facts")

    by_type = {}
    by_predicate = {}
    for f in all_facts:
        by_type.setdefault(f.get("fact_type", "?"), []).append(f)
        by_predicate.setdefault(f.get("predicate", "?"), []).append(f)

    log(f"Types: {', '.join(f'{k}={len(v)}' for k,v in sorted(by_type.items(), key=lambda x: -len(x[1])))}")
    log(f"Predicates: {len(by_predicate)} unique")

    results = {
        "meta": {"subject": "franklin", "total_facts": len(all_facts), "started": datetime.now().isoformat()},
        "experiments": {},
    }

    # ========================================
    # EXP 0: BASELINE (production brief, no generation cost)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 0: BASELINE — Production brief")
    log("=" * 70)
    if baseline_brief:
        baseline_result = run_baseline(baseline_brief, all_facts)
        log(f"  -> Production: composite={baseline_result['composite']:.1f}, {len(baseline_brief)} chars")
        results["experiments"]["0_baseline"] = baseline_result
    else:
        log("  No baseline brief found")
        results["experiments"]["0_baseline"] = {"error": "no brief"}

    # ========================================
    # EXP 1: FACT TYPE ISOLATION
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 1: FACT TYPE ISOLATION")
    log("=" * 70)
    exp1 = []
    for ft, ft_facts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(ft_facts) < 5:
            log(f"  Skipping {ft}: {len(ft_facts)} facts")
            continue
        r = run_condition(ft_facts, all_facts, f"type_{ft}")
        exp1.append(r)
    results["experiments"]["1_fact_type"] = exp1

    # ========================================
    # EXP 2: PREDICATE GROUP ISOLATION
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 2: PREDICATE GROUP ISOLATION")
    log("=" * 70)
    exp2 = []

    groups = {
        "epistemic": ["believes", "values", "prioritizes", "avoids", "struggles_with"],
        "capability": ["practices", "excels_at", "demonstrates"],
        "experiential": ["experienced", "achieved", "founded", "contributed_to", "developed", "builds"],
        "relational": ["friends_with", "mentored_by", "collaborates_with", "conflicts_with",
                       "married_to", "admires", "opposes", "advocates", "advocated_for"],
        "preference": ["prefers", "interested_in", "enjoys", "dislikes"],
        "identity_markers": ["identifies_as", "works_at", "manages", "owns", "aspires_to"],
    }

    for gname, preds in groups.items():
        gfacts = [f for f in all_facts if f.get("predicate") in preds]
        if len(gfacts) < 3:
            log(f"  Skipping {gname}: {len(gfacts)} facts")
            continue
        r = run_condition(gfacts, all_facts, f"group_{gname}")
        exp2.append(r)
    results["experiments"]["2_predicate_group"] = exp2

    # ========================================
    # EXP 3: INDIVIDUAL PREDICATE (5+ facts only)
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 3: INDIVIDUAL PREDICATE ISOLATION")
    log("=" * 70)
    exp3 = []
    for pred, pfacts in sorted(by_predicate.items(), key=lambda x: -len(x[1])):
        if len(pfacts) < 5:
            continue
        r = run_condition(pfacts, all_facts, f"pred_{pred}")
        exp3.append(r)
    results["experiments"]["3_individual_predicate"] = exp3

    # ========================================
    # EXP 4: ADDITIVE VALUE
    # Start with epistemic, add one group
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 4: ADDITIVE VALUE")
    log("=" * 70)
    exp4 = []

    base_preds = ["believes", "values", "prioritizes", "avoids", "struggles_with"]
    base_facts = [f for f in all_facts if f.get("predicate") in base_preds]
    base_r = run_condition(base_facts, all_facts, "base_epistemic")
    exp4.append(base_r)
    base_composite = base_r.get("composite", 0)

    add_groups = {
        "+capability": ["practices", "excels_at", "demonstrates"],
        "+experiential": ["experienced", "achieved", "founded", "builds"],
        "+relational": ["friends_with", "mentored_by", "admires", "opposes", "advocates", "advocated_for"],
        "+preference": ["prefers", "interested_in", "enjoys", "dislikes"],
        "+identity": ["identifies_as", "works_at", "aspires_to"],
    }

    for gname, preds in add_groups.items():
        added = [f for f in all_facts if f.get("predicate") in preds]
        if not added:
            continue
        combined = base_facts + added
        r = run_condition(combined, all_facts, f"additive_{gname}")
        delta = r.get("composite", 0) - base_composite
        r["delta_from_base"] = round(delta, 2)
        exp4.append(r)
        log(f"    delta from base: {'+' if delta >= 0 else ''}{delta:.1f}")
    results["experiments"]["4_additive"] = exp4

    # ========================================
    # EXP 5: OPTIMAL COMBINATIONS
    # ========================================
    log("\n" + "=" * 70)
    log("EXP 5: OPTIMAL COMBINATIONS")
    log("=" * 70)
    exp5 = []

    combos = {
        "epistemic+capability": base_preds + ["practices", "excels_at", "demonstrates"],
        "epistemic+capability+preference": base_preds + ["practices", "excels_at", "demonstrates", "prefers", "dislikes"],
        "top6_by_count": ["values", "practices", "excels_at", "believes", "founded", "prioritizes"],
        "all_behavioral_type": None,  # all facts with fact_type=behavioral
        "no_biographical": None,      # exclude biographical
        "all_identity": None,         # all 135 facts
    }

    for cname, preds in combos.items():
        if cname == "all_behavioral_type":
            cfacts = by_type.get("behavioral", [])
        elif cname == "no_biographical":
            cfacts = [f for f in all_facts if f.get("fact_type") != "biographical"]
        elif cname == "all_identity":
            cfacts = all_facts
        else:
            cfacts = [f for f in all_facts if f.get("predicate") in preds]

        if len(cfacts) < 3:
            continue
        r = run_condition(cfacts, all_facts, f"combo_{cname}")
        exp5.append(r)
    results["experiments"]["5_combinations"] = exp5

    # ========================================
    # ANALYSIS
    # ========================================
    log("\n" + "=" * 70)
    log("ANALYSIS — ALL CONDITIONS RANKED")
    log("=" * 70)

    all_conds = []
    for ename, edata in results["experiments"].items():
        if isinstance(edata, list):
            all_conds.extend([c for c in edata if "composite" in c])
        elif isinstance(edata, dict) and "composite" in edata:
            all_conds.append(edata)

    ranked = sorted(all_conds, key=lambda x: x.get("composite", 0), reverse=True)

    log(f"\n{'Rank':<5} {'Condition':<45} {'Composite':<10} {'M1(cov)':<10} {'M2(pred)':<10} {'M3(patt)':<10} {'Facts':<6} {'Chars':<6}")
    log("-" * 102)
    for i, c in enumerate(ranked):
        s = c.get("scores", {})
        log(f"{i+1:<5} {c['condition']:<45} {c.get('composite', 0):<10.1f} {s.get('m1_embedding_coverage', 0):<10.3f} {s.get('m2_cross_prediction', 0):<10.3f} {s.get('m3_pattern_density', 0):<10.1f} {c.get('train_count', '?'):<6} {c.get('brief_chars', '?'):<6}")

    # Best per experiment
    log("\nBEST PER EXPERIMENT:")
    for ename, edata in results["experiments"].items():
        if isinstance(edata, list) and edata:
            valid = [c for c in edata if "composite" in c]
            if valid:
                best = max(valid, key=lambda x: x["composite"])
                log(f"  {ename}: {best['condition']} (composite={best['composite']:.1f})")
        elif isinstance(edata, dict) and "composite" in edata:
            log(f"  {ename}: {edata['condition']} (composite={edata['composite']:.1f})")

    # Key findings
    log("\nKEY FINDINGS:")
    if exp1:
        best_type = max(exp1, key=lambda x: x.get("composite", 0))
        worst_type = min(exp1, key=lambda x: x.get("composite", 0))
        log(f"  Best fact type: {best_type['condition']} ({best_type.get('composite', 0):.1f})")
        log(f"  Worst fact type: {worst_type['condition']} ({worst_type.get('composite', 0):.1f})")

    if exp2:
        best_group = max(exp2, key=lambda x: x.get("composite", 0))
        worst_group = min(exp2, key=lambda x: x.get("composite", 0))
        log(f"  Best predicate group: {best_group['condition']} ({best_group.get('composite', 0):.1f})")
        log(f"  Worst predicate group: {worst_group['condition']} ({worst_group.get('composite', 0):.1f})")

    if exp3:
        best_pred = max(exp3, key=lambda x: x.get("composite", 0))
        worst_pred = min(exp3, key=lambda x: x.get("composite", 0))
        log(f"  Best single predicate: {best_pred['condition']} ({best_pred.get('composite', 0):.1f})")
        log(f"  Worst single predicate: {worst_pred['condition']} ({worst_pred.get('composite', 0):.1f})")

    if exp4 and len(exp4) > 1:
        log("\n  ADDITIVE DELTAS (from epistemic base):")
        for c in exp4[1:]:
            d = c.get("delta_from_base", 0)
            log(f"    {c['condition']}: {'+' if d >= 0 else ''}{d:.1f}")

    results["meta"]["completed"] = datetime.now().isoformat()
    results["rankings"] = [
        {"rank": i+1, "condition": c["condition"], "composite": c.get("composite", 0),
         "m1": c.get("scores", {}).get("m1_embedding_coverage", 0),
         "facts": c.get("train_count", 0)}
        for i, c in enumerate(ranked)
    ]

    path = os.path.join(OUTPUT_DIR, "ablation_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nResults saved: {path}")

    return results


if __name__ == "__main__":
    main()
