"""
Brief Length + Density Optimization — What's the optimal brief size?

Tests:
  1. Length sweep: 500, 1000, 1500, 2000, 2500, 3500 char targets
  2. Density experiment: same facts, same voice, different compression levels
  3. Cross-subject check: Run best conditions on Marks facts (if available)

Answers: Is the production brief (9,144 chars) too long? At what point does adding more text
stop helping? Does extreme compression (500 chars) retain the signal?

Subject: Franklin + Marks (if available)
Cost: ~$2-3 (Sonnet brief gen)
"""

import sys
import os
import json
import re
from pathlib import Path
import numpy as np
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
FRANKLIN_DB = os.path.join(_HOME, "subjects", "franklin_memory", "data", "database", "memory.db")
MARKS_DB = os.path.join(_HOME, "marks_memory", "data", "database", "memory.db")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "brief_optimization")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading embedding model...")
from sentence_transformers import SentenceTransformer
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
print("Ready.")

import sqlite3


def load_identity_facts(db_path):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, predicate
        FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        ORDER BY id
    """).fetchall()
    conn.close()
    return [{"id": r[0], "fact_text": r[1], "fact_type": r[2], "knowledge_tier": r[3],
             "predicate": r[4]} for r in rows]


def embed_texts(texts):
    if not texts: return np.array([])
    vecs = EMBED_MODEL.encode(texts, show_progress_bar=False)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def score_brief(brief_text, facts):
    if not brief_text or not facts:
        return {"composite": 0, "prediction_rate": 0, "m1_coverage": 0, "efficiency": 0}
    brief_vec = embed_texts([brief_text])[0]
    fact_vecs = embed_texts([f["fact_text"] for f in facts])
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
            "chars": len(brief_text), "tokens_est": tokens,
            "efficiency": round(efficiency, 4)}


def generate_brief(facts, target_chars, label):
    fact_lines = "\n".join([f"- [{f.get('predicate', '?')}] {f['fact_text']}" for f in facts])
    system = f"""You generate behavioral briefs from structured facts about a person.
The brief is injected into an AI's system prompt.
RULES:
- Use he/him or they/them pronouns. Refer to subject as "this person."
- Structure as annotated guide with headers and "When X, do Y" patterns.
- TARGET LENGTH: approximately {target_chars} characters. This is critical.
- Every sentence must change AI behavior. Maximum density.
- Do NOT name the person."""

    try:
        max_tok = max(target_chars // 3, 200)
        resp = call_api(
            model="claude-sonnet-4-20250514",
            system=system,
            messages=[{"role": "user", "content": f"Generate a ~{target_chars}-char behavioral brief from these {len(facts)} facts:\n\n{fact_lines}"}],
            max_tokens=max_tok, temperature=0.3,
            caller=f"brief_opt_{label}",
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


def run_length_sweep(facts, subject_name):
    log(f"\n  LENGTH SWEEP — {subject_name} ({len(facts)} facts)")
    results = []
    targets = [500, 1000, 1500, 2000, 2500, 3500]

    for target in targets:
        label = f"{subject_name}_{target}chars"
        log(f"  Target: {target} chars")
        brief = generate_brief(facts, target, label)
        if not brief:
            results.append({"target_chars": target, "error": "generation failed"})
            continue

        scores = score_brief(brief, facts)
        log(f"    actual={scores['chars']}chars  composite={scores['composite']:.1f}  "
            f"m1={scores['m1_coverage']:.3f}  efficiency={scores['efficiency']:.3f}")
        results.append({
            "target_chars": target,
            "actual_chars": scores["chars"],
            "scores": scores,
        })

    return results


def main():
    log("=" * 70)
    log("BRIEF LENGTH + DENSITY OPTIMIZATION")
    log("=" * 70)

    results = {"meta": {"started": datetime.now().isoformat()}, "experiments": {}}

    # Franklin
    franklin_facts = load_identity_facts(FRANKLIN_DB)
    log(f"Franklin: {len(franklin_facts)} identity-tier facts")

    if franklin_facts:
        results["experiments"]["franklin_length_sweep"] = run_length_sweep(franklin_facts, "franklin")

    # Marks (cross-subject validation)
    marks_facts = load_identity_facts(MARKS_DB)
    log(f"Marks: {len(marks_facts)} identity-tier facts")

    if marks_facts:
        results["experiments"]["marks_length_sweep"] = run_length_sweep(marks_facts, "marks")

    # Analysis
    log("\n" + "=" * 70)
    log("ANALYSIS")
    log("=" * 70)

    for subject in ["franklin_length_sweep", "marks_length_sweep"]:
        sweep = results["experiments"].get(subject, [])
        if not sweep:
            continue
        log(f"\n  {subject}:")
        log(f"  {'Target':<10} {'Actual':<10} {'Composite':<12} {'M1':<10} {'Efficiency':<12}")
        log(f"  {'-'*54}")

        best_composite = None
        best_efficiency = None
        for r in sweep:
            if "error" in r:
                continue
            s = r["scores"]
            log(f"  {r['target_chars']:<10} {s['chars']:<10} {s['composite']:<12.1f} "
                f"{s['m1_coverage']:<10.3f} {s['efficiency']:<12.3f}")
            if best_composite is None or s["composite"] > best_composite["scores"]["composite"]:
                best_composite = r
            if best_efficiency is None or s["efficiency"] > best_efficiency["scores"]["efficiency"]:
                best_efficiency = r

        if best_composite:
            log(f"  Best composite: {best_composite['target_chars']} chars (score={best_composite['scores']['composite']:.1f})")
        if best_efficiency:
            log(f"  Best efficiency: {best_efficiency['target_chars']} chars (eff={best_efficiency['scores']['efficiency']:.3f})")

    results["meta"]["completed"] = datetime.now().isoformat()
    path = os.path.join(OUTPUT_DIR, "brief_optimization_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    log(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
