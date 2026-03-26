"""
GPU Overnight Runner S83 — Extended benchmarks on all subjects

Runs:
  A. Original S78 phases 1-7 on Franklin + Marks (Qwen via Ollama, $0)
  B. Paul Graham phases (all 272 facts, untiered — uses all facts)
  C. Bavani phases (61 identity-tier facts)
  D. SRS (Signal Retention Score) on Paul Graham + Bavani briefs (Haiku API, ~$1)
  E. Compression Ratio (CR) on Paul Graham + Bavani (mechanical, $0)
  F. Brief quality scoring on all V4 briefs (local embeddings, $0)

Total cost: ~$1 (Haiku calls for SRS only). All else is local GPU.
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
PAUL_GRAHAM_DB = os.path.join(_HOME, "subjects", "paul_graham", "data", "database", "memory.db")
BAVANI_DB = os.path.join(_HOME, "subjects", "bavani_memory", "data", "database", "memory.db")

PAUL_GRAHAM_BRIEF = os.path.join(_HOME, "subjects", "paul_graham", "data", "identity_layers", "brief_v4.md")
BAVANI_BRIEF = os.path.join(_HOME, "subjects", "bavani_memory", "data", "identity_layers", "brief_v4.md")
FRANKLIN_BRIEF = os.path.join(_HOME, "subjects", "franklin_memory", "data", "identity_layers", "brief_v4.md")
MARKS_BRIEF = os.path.join(_HOME, "marks_memory", "data", "identity_layers", "brief_v4.md")

OUTPUT_DIR = os.path.join(_HOME, "memory_system", "docs", "eval", "gpu_overnight_s83")
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(OUTPUT_DIR, "run_log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


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


def load_facts(db_path, identity_only=True):
    """Load facts from a subject's database."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    if identity_only:
        query = """
            SELECT id, fact_text, fact_type, knowledge_tier, predicate,
                   commitment_depth, recurrence_count
            FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
            ORDER BY id
        """
    else:
        query = """
            SELECT id, fact_text, fact_type, knowledge_tier, predicate,
                   commitment_depth, recurrence_count
            FROM memory_facts WHERE superseded_by IS NULL
            ORDER BY id
        """
    rows = conn.execute(query).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2] or "unclassified",
             "knowledge_tier": r[3] or "untiered", "predicate": r[4] or "unknown",
             "commitment_depth": r[5], "recurrence_count": r[6]} for r in rows]


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


# ============================================================
# PHASE A: V4 BRIEF QUALITY — Score all existing V4 briefs
# ============================================================
def phase_a_brief_quality():
    log("\n" + "=" * 70)
    log("PHASE A: V4 BRIEF QUALITY SCORING (all subjects)")
    log("=" * 70)

    subjects = {
        "franklin": (FRANKLIN_DB, FRANKLIN_BRIEF, True),
        "marks": (MARKS_DB, MARKS_BRIEF, True),
        "paul_graham": (PAUL_GRAHAM_DB, PAUL_GRAHAM_BRIEF, False),
        # Bavani excluded — private subject
    }

    results = {}
    for name, (db_path, brief_path, identity_only) in subjects.items():
        if not os.path.exists(brief_path):
            log(f"  {name}: no brief found at {brief_path}")
            continue

        with open(brief_path, "r", encoding="utf-8") as f:
            brief_text = f.read()

        facts = load_facts(db_path, identity_only=identity_only)
        if not facts:
            # Fallback: try all facts
            facts = load_facts(db_path, identity_only=False)

        if not facts:
            log(f"  {name}: no facts found")
            continue

        scores = score_brief(brief_text, facts)

        # Compression ratio
        fact_chars = sum(len(f["fact_text"]) for f in facts)
        cr = round(1 - len(brief_text) / max(fact_chars, 1), 4) if fact_chars > 0 else 0

        results[name] = {
            "scores": scores,
            "fact_count": len(facts),
            "brief_chars": len(brief_text),
            "total_fact_chars": fact_chars,
            "compression_ratio": cr,
        }
        log(f"  {name}: composite={scores['composite']:.1f}  m1={scores['m1_coverage']:.3f}  "
            f"pred={scores['prediction_rate']:.1%}  chars={scores['chars']}  CR={cr:.2%}  "
            f"facts={len(facts)}")

    return results


# ============================================================
# PHASE B: PAUL GRAHAM — temporal, subtype, compression, length
# ============================================================
def phase_b_paul_graham():
    log("\n" + "=" * 70)
    log("PHASE B: PAUL GRAHAM EXPERIMENTS (272 untiered facts)")
    log("=" * 70)

    facts = load_facts(PAUL_GRAHAM_DB, identity_only=False)
    if len(facts) < 10:
        log(f"  Only {len(facts)} facts — skipping")
        return {"error": f"insufficient facts: {len(facts)}"}

    log(f"  Loaded {len(facts)} facts")
    results = {}

    # B1: Temporal quarters
    log("\n  --- B1: Temporal Quarter Prediction ---")
    sorted_facts = sorted(facts, key=lambda f: f["id"])
    q_size = len(sorted_facts) // 4
    quarters = {
        "Q1": sorted_facts[:q_size],
        "Q2": sorted_facts[q_size:2*q_size],
        "Q3": sorted_facts[2*q_size:3*q_size],
        "Q4": sorted_facts[3*q_size:],
    }

    temporal = []
    for qname, qfacts in quarters.items():
        other = [f for f in sorted_facts if f not in qfacts]
        r = run_condition(qfacts, other, f"pg_{qname}_predicts_rest")
        temporal.append(r)
    results["temporal_quarters"] = temporal

    # B2: Bidirectional accumulation
    log("\n  --- B2: Bidirectional Accumulation ---")
    Q1, Q2, Q3, Q4 = quarters["Q1"], quarters["Q2"], quarters["Q3"], quarters["Q4"]
    accumulation = {"forward": [], "reverse": []}

    test_ids = {f["id"] for f in Q4}
    for label, train in [("Q1", Q1), ("Q1+Q2", Q1+Q2), ("Q1+Q2+Q3", Q1+Q2+Q3)]:
        clean = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean, Q4, f"pg_fwd_{label}->Q4")
        accumulation["forward"].append(r)

    test_ids = {f["id"] for f in Q1}
    for label, train in [("Q4", Q4), ("Q4+Q3", Q4+Q3), ("Q4+Q3+Q2", Q4+Q3+Q2)]:
        clean = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean, Q1, f"pg_rev_{label}->Q1")
        accumulation["reverse"].append(r)
    results["accumulation"] = accumulation

    # B3: Compression saturation
    log("\n  --- B3: Compression Saturation ---")
    random.seed(42)
    shuf = facts[:]
    random.shuffle(shuf)
    compression = []
    for pct in [10, 20, 30, 50, 75]:
        n = max(3, int(len(facts) * pct / 100))
        r = run_condition(shuf[:n], shuf[n:], f"pg_split_{pct}pct")
        r["split_pct"] = pct
        compression.append(r)
    results["compression"] = compression

    # B4: Brief length sweep
    log("\n  --- B4: Brief Length Sweep ---")
    length_sweep = []
    for target in [500, 1000, 1500, 2000, 2500, 3500]:
        brief = generate_qwen_brief(facts, target, f"pg_len_{target}")
        if not brief:
            length_sweep.append({"target": target, "error": "generation failed"})
            continue
        scores = score_brief(brief, facts)
        log(f"    target={target}  actual={scores['chars']}  composite={scores['composite']:.1f}")
        length_sweep.append({"target": target, "scores": scores})
    results["length_sweep"] = length_sweep

    return results


# ============================================================
# PHASE C: BAVANI — temporal, compression, length
# ============================================================
def phase_c_bavani():
    log("\n" + "=" * 70)
    log("PHASE C: BAVANI EXPERIMENTS (identity-tier facts)")
    log("=" * 70)

    facts = load_facts(BAVANI_DB, identity_only=True)
    if len(facts) < 10:
        # Fallback to all facts
        facts = load_facts(BAVANI_DB, identity_only=False)

    if len(facts) < 10:
        log(f"  Only {len(facts)} facts — skipping")
        return {"error": f"insufficient facts: {len(facts)}"}

    log(f"  Loaded {len(facts)} facts")
    results = {}

    # C1: Compression saturation
    log("\n  --- C1: Compression Saturation ---")
    random.seed(42)
    shuf = facts[:]
    random.shuffle(shuf)
    compression = []
    for pct in [20, 50, 75]:
        n = max(3, int(len(facts) * pct / 100))
        r = run_condition(shuf[:n], shuf[n:], f"bavani_split_{pct}pct")
        r["split_pct"] = pct
        compression.append(r)
    results["compression"] = compression

    # C2: Brief length sweep
    log("\n  --- C2: Brief Length Sweep ---")
    length_sweep = []
    for target in [500, 1000, 2000, 3000]:
        brief = generate_qwen_brief(facts, target, f"bavani_len_{target}")
        if not brief:
            length_sweep.append({"target": target, "error": "generation failed"})
            continue
        scores = score_brief(brief, facts)
        log(f"    target={target}  actual={scores['chars']}  composite={scores['composite']:.1f}")
        length_sweep.append({"target": target, "scores": scores})
    results["length_sweep"] = length_sweep

    return results


# ============================================================
# PHASE D: ORIGINAL S78 PHASES 1-7 (Franklin + Marks)
# ============================================================
def phase_d_franklin_original():
    log("\n" + "=" * 70)
    log("PHASE D: ORIGINAL S78 PHASES ON FRANKLIN + MARKS")
    log("=" * 70)

    franklin_facts = load_facts(FRANKLIN_DB, identity_only=True)
    log(f"  Franklin identity-tier facts: {len(franklin_facts)}")

    results = {}

    if len(franklin_facts) < 10:
        log("  Insufficient Franklin facts, skipping")
        return {"error": "insufficient facts"}

    # D1: Temporal quarters
    log("\n  --- D1: Temporal Quarter Prediction ---")
    sorted_facts = sorted(franklin_facts, key=lambda f: f["id"])
    q_size = len(sorted_facts) // 4
    quarters = {
        "Q1": sorted_facts[:q_size],
        "Q2": sorted_facts[q_size:2*q_size],
        "Q3": sorted_facts[2*q_size:3*q_size],
        "Q4": sorted_facts[3*q_size:],
    }
    temporal = []
    for qname, qfacts in quarters.items():
        other = [f for f in sorted_facts if f not in qfacts]
        r = run_condition(qfacts, other, f"franklin_{qname}_predicts_rest")
        temporal.append(r)
    results["temporal_quarters"] = temporal

    # D2: Bidirectional accumulation
    log("\n  --- D2: Bidirectional Accumulation ---")
    Q1, Q2, Q3, Q4 = quarters["Q1"], quarters["Q2"], quarters["Q3"], quarters["Q4"]
    accumulation = {"forward": [], "reverse": []}
    test_ids = {f["id"] for f in Q4}
    for label, train in [("Q1", Q1), ("Q1+Q2", Q1+Q2), ("Q1+Q2+Q3", Q1+Q2+Q3)]:
        clean = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean, Q4, f"franklin_fwd_{label}->Q4")
        accumulation["forward"].append(r)
    test_ids = {f["id"] for f in Q1}
    for label, train in [("Q4", Q4), ("Q4+Q3", Q4+Q3), ("Q4+Q3+Q2", Q4+Q3+Q2)]:
        clean = [f for f in train if f["id"] not in test_ids]
        r = run_condition(clean, Q1, f"franklin_rev_{label}->Q1")
        accumulation["reverse"].append(r)
    results["accumulation"] = accumulation

    # D3: Subtype cross-prediction
    log("\n  --- D3: Subtype Cross-Prediction ---")
    by_type = {}
    for f in franklin_facts:
        by_type.setdefault(f.get("fact_type", "?"), []).append(f)
    subtype = []
    for ft, ft_facts in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(ft_facts) < 5:
            continue
        other = [f for f in franklin_facts if f.get("fact_type") != ft]
        if len(other) < 5:
            continue
        r = run_condition(ft_facts, other, f"franklin_{ft}_predicts_others")
        subtype.append(r)
    results["subtype_cross"] = subtype

    # D4: Predicate quality (3 rounds)
    log("\n  --- D4: Predicate Quality Extended ---")
    groups = {
        "epistemic": ["believes", "values", "prioritizes", "avoids", "struggles_with"],
        "capability": ["practices", "excels_at", "demonstrates"],
        "experiential": ["experienced", "achieved", "founded", "contributed_to"],
        "preference": ["prefers", "interested_in", "enjoys", "dislikes"],
    }
    pred_results = {}
    for gname, preds in groups.items():
        gfacts = [f for f in franklin_facts if f.get("predicate") in preds]
        if len(gfacts) < 3:
            continue
        other = [f for f in franklin_facts if f not in gfacts]
        rounds = []
        for round_num in range(3):
            random.seed(42 + round_num * 17)
            other_shuf = other[:]
            random.shuffle(other_shuf)
            test_set = other_shuf[:len(other_shuf)//2]
            r = run_condition(gfacts, test_set, f"franklin_{gname}_r{round_num+1}")
            rounds.append(r)
        composites = [r.get("scores", {}).get("composite", 0) for r in rounds if "scores" in r]
        avg = float(np.mean(composites)) if composites else 0
        std = float(np.std(composites)) if len(composites) > 1 else 0
        pred_results[gname] = {"rounds": rounds, "avg_composite": round(avg, 2),
                               "std_composite": round(std, 2), "fact_count": len(gfacts)}
        log(f"    {gname}: avg={avg:.1f} +/- {std:.1f} ({len(gfacts)} facts)")
    results["predicate_quality"] = pred_results

    # D5: Brief length sweep
    log("\n  --- D5: Brief Length Sweep ---")
    length_sweep = []
    for target in [500, 1000, 2000, 3500]:
        brief = generate_qwen_brief(franklin_facts, target, f"franklin_len_{target}")
        if not brief:
            length_sweep.append({"target": target, "error": "generation failed"})
            continue
        scores = score_brief(brief, franklin_facts)
        log(f"    target={target}  actual={scores['chars']}  composite={scores['composite']:.1f}")
        length_sweep.append({"target": target, "scores": scores})
    results["length_sweep"] = length_sweep

    # D6: Voice replication
    log("\n  --- D6: Voice Replication ---")
    voices = {
        "core_dominant": "Write as operational guidance briefing a colleague. No headers. Weave axioms and predictions together.",
        "pure_directive": "Write as direct AI instructions. Every sentence is imperative: 'Do X', 'Never Y', 'When Z, respond with W'.",
        "annotated_guide": "Write with clear section headers. Under each, use 'When [trigger], [behavior]' format.",
        "compressed_telegram": "Maximum compression. Key:value pairs and short phrases. No full sentences.",
    }
    fact_lines = "\n".join([f"- [{f.get('predicate', '?')}] {f['fact_text']}" for f in franklin_facts[:80]])
    voice_results = {}
    for vname, instruction in voices.items():
        prompt = f"""Generate a behavioral brief (~2000 characters) from these facts.
{instruction}
Do NOT name the person. Target: 2000 characters.

FACTS:
{fact_lines}

BRIEF:"""
        brief = call_qwen(prompt)
        if not brief:
            voice_results[vname] = {"error": "generation failed"}
            continue
        scores = score_brief(brief, franklin_facts)
        voice_results[vname] = {"scores": scores, "brief_preview": brief[:200]}
        log(f"    {vname}: composite={scores['composite']:.1f}  chars={scores['chars']}")
        with open(os.path.join(OUTPUT_DIR, f"voice_{vname}_qwen.md"), "w", encoding="utf-8") as f:
            f.write(brief)
    results["voice_replication"] = voice_results

    # D7: Marks cross-subject
    log("\n  --- D7: Marks Cross-Subject ---")
    marks_facts = load_facts(MARKS_DB, identity_only=True)
    if len(marks_facts) >= 10:
        log(f"  Marks identity-tier facts: {len(marks_facts)}")
        marks_results = {}

        sorted_mf = sorted(marks_facts, key=lambda f: f["id"])
        q_size = len(sorted_mf) // 4
        if q_size >= 5:
            mquarters = {
                "Q1": sorted_mf[:q_size], "Q2": sorted_mf[q_size:2*q_size],
                "Q3": sorted_mf[2*q_size:3*q_size], "Q4": sorted_mf[3*q_size:],
            }
            marks_temporal = []
            for qname, qfacts in mquarters.items():
                other = [f for f in sorted_mf if f not in qfacts]
                r = run_condition(qfacts, other, f"marks_{qname}_predicts_rest")
                marks_temporal.append(r)
            marks_results["temporal_quarters"] = marks_temporal

        random.seed(42)
        shuf = marks_facts[:]
        random.shuffle(shuf)
        marks_compression = []
        for pct in [10, 20, 50]:
            n = max(3, int(len(marks_facts) * pct / 100))
            r = run_condition(shuf[:n], shuf[n:], f"marks_split_{pct}pct")
            r["split_pct"] = pct
            marks_compression.append(r)
        marks_results["compression"] = marks_compression

        results["marks_cross_subject"] = marks_results
    else:
        log("  No Marks data found")
        results["marks_cross_subject"] = {"error": "no marks data"}

    return results


# ============================================================
# MAIN
# ============================================================
def main():
    log("=" * 70)
    log("GPU OVERNIGHT RUNNER — SESSION 83")
    log(f"Model: {MODEL} via Ollama")
    log(f"Started: {datetime.now().isoformat()}")
    log("=" * 70)

    # Check Ollama
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        log(f"Ollama models: {models}")
    except Exception as e:
        log(f"WARNING: Ollama not responding: {e}")

    results = {
        "meta": {
            "started": datetime.now().isoformat(),
            "model": MODEL,
            "script": "gpu_overnight_s83.py",
        },
        "phases": {}
    }

    phases = [
        ("A_brief_quality", phase_a_brief_quality),
        ("B_paul_graham", phase_b_paul_graham),
        # Bavani excluded — private subject, not for benchmarking
        ("D_franklin_marks_original", phase_d_franklin_original),
    ]

    for pname, pfn in phases:
        log(f"\n{'#' * 70}")
        log(f"Starting {pname}")
        log(f"{'#' * 70}")
        try:
            results["phases"][pname] = pfn()
        except Exception as e:
            log(f"PHASE {pname} FAILED: {e}")
            log(traceback.format_exc())
            results["phases"][pname] = {"error": str(e)}

        # Save after each phase
        with open(os.path.join(OUTPUT_DIR, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        log(f"Checkpoint saved after {pname}")

    results["meta"]["finished"] = datetime.now().isoformat()
    with open(os.path.join(OUTPUT_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    log("\n" + "=" * 70)
    log("ALL PHASES COMPLETE")
    log(f"Results: {os.path.join(OUTPUT_DIR, 'results.json')}")
    log("=" * 70)


if __name__ == "__main__":
    main()
