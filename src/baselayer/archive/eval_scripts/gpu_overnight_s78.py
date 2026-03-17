"""
GPU Overnight Runner S78 — Local Qwen experiments (FREE, parallel with API scripts)

Phases:
  1. TEMPORAL QUARTER PREDICTION — Train on each quarter, predict others (Qwen briefs)
  2. BIDIRECTIONAL ACCUMULATION — Q1, Q1+Q2, Q1+Q2+Q3, all -> predict Q4 (and reverse)
  3. IDENTITY SUBTYPE CROSS-PREDICTION — Each fact_type predicts all others (Qwen briefs)
  4. PREDICATE QUALITY EXTENDED — 3 rounds per predicate group (reduce variance from S77)
  5. BRIEF LENGTH SWEEP — 500, 1000, 2000, 3500 char briefs via Qwen
  6. VOICE REPLICATION — Generate all 5 voices via Qwen, compare to Sonnet results
  7. MARKS CROSS-SUBJECT — Run temporal + subtype experiments on Marks (if data exists)

All Qwen via Ollama. All scoring via local embeddings. $0 cost.
"""

import sys
import os
import json
import time
import sqlite3
import random
from pathlib import Path
import re
import requests
import traceback
import numpy as np
from datetime import datetime
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_HOME = os.path.join(str(Path.home()), "Anthropic")
FRANKLIN_DB = os.path.join(_HOME, "subjects", "franklin_memory", "data", "database", "memory.db")
MARKS_DB = os.path.join(_HOME, "marks_memory", "data", "database", "memory.db")
OUTPUT_DIR = os.path.join(_HOME, "memory_system", "docs", "eval", "gpu_overnight_s78")
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")


def call_qwen(prompt, max_retries=3):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 2048},
    }
    for attempt in range(max_retries):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            log(f"  Qwen attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
    return None


def load_identity_facts(db_path):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, predicate,
               commitment_depth, recurrence_count
        FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        ORDER BY id
    """).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
             "predicate": r[4], "commitment_depth": r[5], "recurrence_count": r[6]} for r in rows]


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

    tokens = len(brief_text) // 4
    efficiency = m1 / max(tokens, 1) * 1000

    composite = round(m1 * 40 + m2 * 25 + min(m3/10, 1) * 15 + 10, 2)
    return {"m1_coverage": round(m1, 4), "prediction_rate": round(m2, 4),
            "m3_pattern_density": round(m3, 2), "composite": composite,
            "chars": len(brief_text), "efficiency": round(efficiency, 4)}


def generate_qwen_brief(facts, target_chars=2000, label=""):
    fact_lines = "\n".join([f"- [{f.get('predicate', '?')}] {f['fact_text']}" for f in facts[:80]])
    prompt = f"""Generate a behavioral brief (~{target_chars} characters) from these facts about a person.
The brief will be injected into an AI's system prompt.

RULES:
- Use he/him pronouns. Refer to subject as "this person."
- Structure with section headers and "When X, do Y" patterns.
- Every sentence must change AI behavior. No filler.
- Do NOT name the person.
- Target: approximately {target_chars} characters.

FACTS ({len(facts)} total):
{fact_lines}

BEHAVIORAL BRIEF:"""

    return call_qwen(prompt)


def run_condition(train_facts, test_facts, label, target_chars=2000):
    log(f"  {label}: {len(train_facts)} train -> {len(test_facts)} test")
    brief = generate_qwen_brief(train_facts, target_chars, label)
    if not brief:
        return {"label": label, "error": "generation failed"}
    scores = score_brief(brief, test_facts)
    log(f"    composite={scores['composite']:.1f}  m1={scores['m1_coverage']:.3f}  pred={scores['prediction_rate']:.1%}  chars={scores['chars']}")
    return {"label": label, "train_count": len(train_facts), "test_count": len(test_facts),
            "scores": scores, "brief_preview": brief[:200]}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# PHASE 1: TEMPORAL QUARTER PREDICTION
# ============================================================
def phase1_temporal_quarters(facts):
    log("\n" + "=" * 70)
    log("PHASE 1: TEMPORAL QUARTER PREDICTION")
    log("=" * 70)

    sorted_facts = sorted(facts, key=lambda f: f["id"])
    q_size = len(sorted_facts) // 4
    quarters = {
        "Q1": sorted_facts[:q_size],
        "Q2": sorted_facts[q_size:2*q_size],
        "Q3": sorted_facts[2*q_size:3*q_size],
        "Q4": sorted_facts[3*q_size:],
    }

    results = []
    # Each quarter predicts all others
    for qname, qfacts in quarters.items():
        other = [f for f in sorted_facts if f not in qfacts]
        r = run_condition(qfacts, other, f"{qname}_predicts_rest")
        results.append(r)

    return results


# ============================================================
# PHASE 2: BIDIRECTIONAL ACCUMULATION
# ============================================================
def phase2_accumulation(facts):
    log("\n" + "=" * 70)
    log("PHASE 2: BIDIRECTIONAL TEMPORAL ACCUMULATION")
    log("=" * 70)

    sorted_facts = sorted(facts, key=lambda f: f["id"])
    q_size = len(sorted_facts) // 4
    Q1 = sorted_facts[:q_size]
    Q2 = sorted_facts[q_size:2*q_size]
    Q3 = sorted_facts[2*q_size:3*q_size]
    Q4 = sorted_facts[3*q_size:]

    results = {"forward": [], "reverse": []}

    # Forward: accumulate from early, test on Q4
    test_ids = {f["id"] for f in Q4}
    for label, train in [("Q1", Q1), ("Q1+Q2", Q1+Q2), ("Q1+Q2+Q3", Q1+Q2+Q3)]:
        clean = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean, Q4, f"fwd_{label}->Q4")
        results["forward"].append(r)

    # Reverse: accumulate from late, test on Q1
    test_ids = {f["id"] for f in Q1}
    for label, train in [("Q4", Q4), ("Q4+Q3", Q4+Q3), ("Q4+Q3+Q2", Q4+Q3+Q2)]:
        clean = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean, Q1, f"rev_{label}->Q1")
        results["reverse"].append(r)

    return results


# ============================================================
# PHASE 3: IDENTITY SUBTYPE CROSS-PREDICTION
# ============================================================
def phase3_subtype_cross(facts):
    log("\n" + "=" * 70)
    log("PHASE 3: IDENTITY SUBTYPE CROSS-PREDICTION")
    log("=" * 70)

    by_type = {}
    for f in facts:
        by_type.setdefault(f.get("fact_type", "?"), []).append(f)

    results = []
    for ft, ft_facts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(ft_facts) < 5:
            continue
        other = [f for f in facts if f.get("fact_type") != ft]
        if len(other) < 5:
            continue
        r = run_condition(ft_facts, other, f"{ft}_predicts_others")
        r["fact_type"] = ft
        r["count"] = len(ft_facts)
        results.append(r)

    return results


# ============================================================
# PHASE 4: PREDICATE QUALITY EXTENDED (3 rounds per group)
# ============================================================
def phase4_predicate_extended(facts):
    log("\n" + "=" * 70)
    log("PHASE 4: PREDICATE QUALITY — 3 ROUNDS PER GROUP (reduce variance)")
    log("=" * 70)

    groups = {
        "epistemic": ["believes", "values", "prioritizes", "avoids", "struggles_with"],
        "capability": ["practices", "excels_at", "demonstrates"],
        "experiential": ["experienced", "achieved", "founded", "contributed_to"],
        "preference": ["prefers", "interested_in", "enjoys", "dislikes"],
        "relational": ["friends_with", "mentored_by", "admires", "advocates", "advocated_for"],
    }

    results = {}
    for gname, preds in groups.items():
        gfacts = [f for f in facts if f.get("predicate") in preds]
        if len(gfacts) < 3:
            log(f"  Skipping {gname}: only {len(gfacts)} facts")
            continue

        other = [f for f in facts if f not in gfacts]
        rounds = []
        for round_num in range(3):
            # Shuffle held-out facts for variance measurement
            random.seed(42 + round_num * 17)
            other_shuf = other[:]
            random.shuffle(other_shuf)
            test_set = other_shuf[:len(other_shuf)//2]
            r = run_condition(gfacts, test_set, f"{gname}_r{round_num+1}")
            rounds.append(r)

        composites = [r.get("scores", {}).get("composite", 0) for r in rounds if "scores" in r]
        avg = np.mean(composites) if composites else 0
        std = np.std(composites) if len(composites) > 1 else 0
        results[gname] = {
            "rounds": rounds,
            "avg_composite": round(float(avg), 2),
            "std_composite": round(float(std), 2),
            "fact_count": len(gfacts),
        }
        log(f"  {gname}: avg={avg:.1f} +/- {std:.1f} ({len(gfacts)} facts)")

    return results


# ============================================================
# PHASE 5: BRIEF LENGTH SWEEP (Qwen)
# ============================================================
def phase5_length_sweep(facts):
    log("\n" + "=" * 70)
    log("PHASE 5: BRIEF LENGTH SWEEP (Qwen)")
    log("=" * 70)

    results = []
    for target in [500, 1000, 1500, 2000, 2500, 3500]:
        brief = generate_qwen_brief(facts, target, f"len_{target}")
        if not brief:
            results.append({"target": target, "error": "generation failed"})
            continue
        scores = score_brief(brief, facts)
        log(f"  target={target}  actual={scores['chars']}  composite={scores['composite']:.1f}  eff={scores['efficiency']:.3f}")
        results.append({"target": target, "scores": scores})

    return results


# ============================================================
# PHASE 6: VOICE REPLICATION (Qwen versions of all 5 voices)
# ============================================================
def phase6_voice_replication(facts):
    log("\n" + "=" * 70)
    log("PHASE 6: VOICE REPLICATION — Qwen versions of all 5 voices")
    log("=" * 70)

    voices = {
        "core_dominant": "Write as operational guidance briefing a colleague. No headers. Weave axioms and predictions together. Use they/them.",
        "pure_directive": "Write as direct AI instructions. Every sentence is imperative: 'Do X', 'Never Y', 'When Z, respond with W'. Use he/him.",
        "pure_narrative": "Write as a psychologist's case study. Third-person analytical. 'He tends to...', 'His reasoning pattern involves...'",
        "annotated_guide": "Write with clear section headers (REASONING PATTERNS, DECISION-MAKING, FAILURE MODES, ENGAGEMENT RULES). Under each, use 'When [trigger], [behavior]' format.",
        "compressed_telegram": "Maximum compression. Telegram style. Key:value pairs and short phrases. No full sentences. Just the essential patterns.",
    }

    fact_lines = "\n".join([f"- [{f.get('predicate', '?')}] {f['fact_text']}" for f in facts[:80]])
    results = {}

    for vname, instruction in voices.items():
        prompt = f"""Generate a behavioral brief (~2000 characters) from these facts.
{instruction}
Do NOT name the person. Target: 2000 characters.

FACTS:
{fact_lines}

BRIEF:"""

        brief = call_qwen(prompt)
        if not brief:
            results[vname] = {"error": "generation failed"}
            continue

        scores = score_brief(brief, facts)
        results[vname] = {"scores": scores, "brief_preview": brief[:200]}
        log(f"  {vname}: composite={scores['composite']:.1f}  chars={scores['chars']}  eff={scores['efficiency']:.3f}")

        # Save brief
        with open(os.path.join(OUTPUT_DIR, f"voice_{vname}_qwen.md"), "w", encoding="utf-8") as f:
            f.write(brief)

    return results


# ============================================================
# PHASE 7: MARKS CROSS-SUBJECT (if data exists)
# ============================================================
def phase7_marks_cross_subject():
    log("\n" + "=" * 70)
    log("PHASE 7: MARKS CROSS-SUBJECT VALIDATION")
    log("=" * 70)

    facts = load_identity_facts(MARKS_DB)
    if not facts:
        log("  No Marks data found")
        return {"error": "no marks data"}

    log(f"  Marks identity-tier facts: {len(facts)}")
    results = {}

    # Temporal quarters
    sorted_facts = sorted(facts, key=lambda f: f["id"])
    q_size = len(sorted_facts) // 4
    if q_size >= 5:
        quarters = {
            "Q1": sorted_facts[:q_size],
            "Q2": sorted_facts[q_size:2*q_size],
            "Q3": sorted_facts[2*q_size:3*q_size],
            "Q4": sorted_facts[3*q_size:],
        }

        temporal = []
        for qname, qfacts in quarters.items():
            other = [f for f in sorted_facts if f not in qfacts]
            r = run_condition(qfacts, other, f"marks_{qname}_predicts_rest")
            temporal.append(r)
        results["temporal_quarters"] = temporal

    # Subtype cross-prediction
    by_type = {}
    for f in facts:
        by_type.setdefault(f.get("fact_type", "?"), []).append(f)

    subtype = []
    for ft, ft_facts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(ft_facts) < 5:
            continue
        other = [f for f in facts if f.get("fact_type") != ft]
        if len(other) < 5:
            continue
        r = run_condition(ft_facts, other, f"marks_{ft}_cross")
        subtype.append(r)
    results["subtype_cross"] = subtype

    # Compression saturation
    random.seed(42)
    shuf = facts[:]
    random.shuffle(shuf)
    compression = []
    for pct in [10, 20, 50]:
        n = max(3, int(len(facts) * pct / 100))
        r = run_condition(shuf[:n], shuf[n:], f"marks_split_{pct}pct")
        r["split_pct"] = pct
        compression.append(r)
    results["compression"] = compression

    return results


# ============================================================
# MAIN
# ============================================================
def main():
    log("=" * 70)
    log("GPU OVERNIGHT RUNNER — SESSION 78")
    log(f"Model: {MODEL} via Ollama")
    log(f"Cost: $0 (all local)")
    log("=" * 70)

    # Check Ollama
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        log(f"Ollama models: {models}")
        if not any(MODEL.split(":")[0] in m for m in models):
            log(f"WARNING: {MODEL} not found in Ollama")
    except Exception as e:
        log(f"WARNING: Ollama not responding: {e}")
        log("Continuing anyway — will fail on first Qwen call if not available")

    franklin_facts = load_identity_facts(FRANKLIN_DB)
    log(f"Franklin identity-tier facts: {len(franklin_facts)}")

    results = {"meta": {"started": datetime.now().isoformat(), "model": MODEL,
                        "franklin_facts": len(franklin_facts)},
               "phases": {}}

    phases = [
        ("1_temporal_quarters", lambda: phase1_temporal_quarters(franklin_facts)),
        ("2_accumulation", lambda: phase2_accumulation(franklin_facts)),
        ("3_subtype_cross", lambda: phase3_subtype_cross(franklin_facts)),
        ("4_predicate_extended", lambda: phase4_predicate_extended(franklin_facts)),
        ("5_length_sweep", lambda: phase5_length_sweep(franklin_facts)),
        ("6_voice_replication", lambda: phase6_voice_replication(franklin_facts)),
        ("7_marks_cross_subject", lambda: phase7_marks_cross_subject()),
    ]

    for pname, pfn in phases:
        log(f"\n{'#' * 70}")
        log(f"STARTING PHASE: {pname}")
        log(f"{'#' * 70}")
        phase_start = time.time()
        try:
            results["phases"][pname] = pfn()
            elapsed = time.time() - phase_start
            log(f"  Phase {pname} complete in {elapsed/60:.1f} min")
        except Exception as e:
            elapsed = time.time() - phase_start
            log(f"  Phase {pname} FAILED after {elapsed/60:.1f} min: {e}")
            log(traceback.format_exc())
            results["phases"][pname] = {"error": str(e)}

    results["meta"]["completed"] = datetime.now().isoformat()
    path = os.path.join(OUTPUT_DIR, "gpu_s78_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nAll results saved: {path}")


if __name__ == "__main__":
    main()
