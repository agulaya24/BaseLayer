"""
Overnight Local Model Evaluation — Session 87

Chains:
  Phase A: Pipeline step viability (extract/author/compose) on LFM2 + Qwen 7B
  Phase B: Extraction quality comparison (local vs Haiku baseline on Franklin)
  Phase C: Brief quality scoring on all 12 V5 briefs (local embeddings, $0)
  Phase D: Behavioral differentiation — same 5 questions, 5 subjects, measure response divergence

Total estimated cost: $0 (all local)
Total estimated time: 3-6 hours depending on GPU load

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/overnight_local_models.py            # All phases
    python experiments/overnight_local_models.py --phase A  # One phase
    python experiments/overnight_local_models.py --dry-run
"""

import json
import os
import sys
import time
import argparse
import requests
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
RESULTS_DIR = Path(__file__).parent / "overnight_results"
SUBJECTS_DIR = Path("C:/Users/Aarik/Anthropic/subjects")
V4_DIR = Path("C:/Users/Aarik/Anthropic/memory_system_v4")

# Models for each phase (ordered: best quality first, fallback to smaller)
PIPELINE_MODELS = ["qwen2.5:7b", "sam860/LFM2:2.6b", "sam860/LFM2:350m"]
REASONING_MODELS = ["deepseek-r1:7b", "qwen2.5:7b"]

# All 12 subjects with V5 briefs
ALL_SUBJECTS = [
    ("franklin",      SUBJECTS_DIR / "franklin_memory"),
    ("buffett",       SUBJECTS_DIR / "buffett_memory"),
    ("aarik",         V4_DIR),
    ("douglass",      SUBJECTS_DIR / "douglass_memory"),
    ("marks",         SUBJECTS_DIR / "marks_memory"),
    ("bavani",        SUBJECTS_DIR / "bavani_memory"),
    ("patent",        SUBJECTS_DIR / "patent_memory"),
    ("lesswrong",     SUBJECTS_DIR / "lesswrong_clt"),
    ("baselayer_meta",SUBJECTS_DIR / "baselayer_meta"),
    ("paul_graham",   SUBJECTS_DIR / "paul_graham"),
    ("roosevelt",     SUBJECTS_DIR / "roosevelt_memory"),
    ("wollstonecraft",SUBJECTS_DIR / "wollstonecraft_memory"),
]

# Five differentiation questions — same question sent with each subject's brief
DIFF_QUESTIONS = [
    "How should I approach a difficult negotiation where I have less leverage?",
    "What's your instinct when you see a crowded trade everyone agrees on?",
    "Someone challenges one of your core beliefs publicly. What do you do?",
    "You have limited time and three important tasks. How do you decide?",
    "What do you think makes someone worth listening to?",
]

# Subjects to use for differentiation test (most distinct archetypes)
DIFF_SUBJECTS = ["franklin", "douglass", "buffett", "wollstonecraft", "roosevelt"]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def check_models():
    """Return list of models that are actually installed."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        installed = [m["name"] for m in resp.json().get("models", [])]
        return installed
    except Exception:
        return []


def is_model_available(model, installed):
    base = model.split(":")[0]
    return any(model == m or base in m for m in installed)


def call_ollama(model, prompt, max_tokens=1500, temperature=0.0):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    start = time.time()
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start
        return {
            "text": data.get("response", "").strip(),
            "time": round(elapsed, 1),
            "tokens_out": data.get("eval_count", 0),
            "ok": True,
        }
    except Exception as e:
        return {"text": "", "time": 0, "tokens_out": 0, "ok": False, "error": str(e)}


def get_embedding(text):
    """Local sentence-transformer embedding."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vec = model.encode([text])[0]
        return vec.tolist()
    except Exception:
        return None


def cosine_sim(a, b):
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb > 0 else 0.0


def load_brief(subject_dir):
    """Load V5 clean brief."""
    layers_dir = Path(subject_dir) / "data" / "identity_layers"
    for fname in ["brief_v5_clean.md", "brief_v5.md", "brief_v4.md"]:
        p = layers_dir / fname
        if p.exists():
            text = p.read_text(encoding="utf-8")
            # Strip frontmatter
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    text = text[end + 3:].strip()
            # Strip ## Injectable Block header
            if text.startswith("## Injectable Block"):
                text = text[len("## Injectable Block"):].strip()
            return text
    return None


# ============================================================================
# PHASE A: Pipeline step viability
# ============================================================================

def phase_a(installed, dry_run=False):
    log("=== PHASE A: Pipeline Step Viability ===")

    models = [m for m in PIPELINE_MODELS if is_model_available(m, installed)]
    if not models:
        log("  No pipeline models available. Pull: ollama pull qwen2.5:7b")
        return {}

    # Load sample text from Franklin
    import sqlite3
    db_path = SUBJECTS_DIR / "franklin_memory" / "data" / "database" / "memory.db"
    sample_text = "Benjamin Franklin valued industry and frugality. He practiced the Socratic method of questioning. He founded the Pennsylvania Gazette and Poor Richard's Almanac. He believed collective benefit should guide every decision."
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("""
            SELECT GROUP_CONCAT(fact_text, '. ')
            FROM memory_facts WHERE knowledge_tier='identity' LIMIT 10
        """).fetchone()
        conn.close()
        if row and row[0]:
            sample_text = row[0][:2000]

    results = {"models": {}}

    extract_prompt = f"""Extract facts about this person as JSON. Return: {{"facts": [{{"predicate": "...", "object": "...", "confidence": 0.9}}]}}

Text: {sample_text[:1000]}"""

    author_prompt = f"""Write 3 behavioral axioms about this person as markdown:
**A1. NAME** — description. Active when: X. Directive: Y.

Facts: {sample_text[:500]}"""

    brief_layers = load_brief(SUBJECTS_DIR / "franklin_memory") or "No layers found"
    compose_prompt = f"""Write a 500-word behavioral brief about this person. Start with ## Injectable Block. Include directives and a CANNOT PREDICT section.

{brief_layers[:3000]}"""

    for model in models:
        log(f"  Model: {model}")
        results["models"][model] = {}

        for step, prompt, max_tok in [
            ("extract", extract_prompt, 800),
            ("author", author_prompt, 600),
            ("compose", compose_prompt, 1200),
        ]:
            if dry_run:
                log(f"    [DRY] {step}")
                continue
            r = call_ollama(model, prompt, max_tokens=max_tok)
            score = {}
            if step == "extract":
                import re
                try:
                    m = re.search(r'\{.*\}', r["text"], re.DOTALL)
                    parsed = json.loads(m.group()) if m else {}
                    score["json_ok"] = bool(parsed.get("facts"))
                    score["fact_count"] = len(parsed.get("facts", []))
                except Exception:
                    score["json_ok"] = False
                    score["fact_count"] = 0
            elif step == "author":
                score["has_axioms"] = "**A" in r["text"]
                score["has_directive"] = "directive" in r["text"].lower()
            elif step == "compose":
                score["has_injectable"] = "injectable block" in r["text"].lower()
                score["has_cannot"] = "cannot predict" in r["text"].lower()
                score["chars"] = len(r["text"])

            log(f"    {step}: {r['time']}s, {r['tokens_out']} tok -> {score}")
            results["models"][model][step] = {**r, "score": score}

    return results


# ============================================================================
# PHASE B: Extraction quality vs Haiku baseline
# ============================================================================

def phase_b(installed, dry_run=False):
    log("=== PHASE B: Extraction Quality (local vs API baseline) ===")

    models = [m for m in PIPELINE_MODELS if is_model_available(m, installed)]
    if not models:
        log("  Skipping — no pipeline models available")
        return {}

    # Load Franklin facts as ground truth
    import sqlite3
    db_path = SUBJECTS_DIR / "franklin_memory" / "data" / "database" / "memory.db"
    if not db_path.exists():
        log("  Franklin DB not found")
        return {}

    conn = sqlite3.connect(str(db_path))
    # Get 5 sample conversations
    convos = conn.execute("""
        SELECT c.title, GROUP_CONCAT(m.content_text, '\n') as text
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        WHERE m.content_text IS NOT NULL AND LENGTH(m.content_text) > 100
        GROUP BY c.id
        ORDER BY c.created_at
        LIMIT 5
    """).fetchall()
    # Get API-extracted facts as baseline
    api_facts = conn.execute("""
        SELECT predicate, object_text FROM memory_facts
        WHERE knowledge_tier = 'identity'
        ORDER BY confidence DESC LIMIT 20
    """).fetchall()
    conn.close()

    api_fact_text = " ".join(f"{f[0]}: {f[1]}" for f in api_facts)

    results = {"models": {}}

    extract_prompt_template = """Extract behavioral facts about this person as JSON.
Return: {{"facts": [{{"predicate": "string", "object": "string", "confidence": 0.9}}]}}
Use predicates like: believes, values, practices, avoids, founded, married_to.

Text:
{text}"""

    for model in models:
        log(f"  Model: {model}")
        results["models"][model] = {"convos_tested": 0, "avg_facts": 0, "json_success_rate": 0, "similarity_to_api": 0}

        total_facts = 0
        json_ok = 0
        sims = []

        for title, text in convos:
            if dry_run:
                log(f"    [DRY] {title[:40]}")
                continue
            prompt = extract_prompt_template.format(text=text[:2000])
            r = call_ollama(model, prompt, max_tokens=1000)
            if not r["ok"]:
                continue

            import re
            try:
                m = re.search(r'\{.*\}', r["text"], re.DOTALL)
                parsed = json.loads(m.group()) if m else {}
                facts = parsed.get("facts", [])
                total_facts += len(facts)
                json_ok += 1

                # Embedding similarity to API baseline
                local_text = " ".join(f"{f.get('predicate','')}: {f.get('object','')}" for f in facts)
                if local_text and api_fact_text:
                    a = get_embedding(local_text)
                    b = get_embedding(api_fact_text)
                    if a and b:
                        sims.append(cosine_sim(a, b))
            except Exception:
                pass

        n = len(convos)
        results["models"][model] = {
            "convos_tested": n,
            "avg_facts_per_convo": round(total_facts / max(json_ok, 1), 1),
            "json_success_rate": round(json_ok / max(n, 1), 2),
            "avg_similarity_to_api": round(sum(sims) / len(sims), 3) if sims else 0,
        }
        log(f"    {results['models'][model]}")

    return results


# ============================================================================
# PHASE C: Brief quality scoring on all V5 briefs
# ============================================================================

def phase_c(dry_run=False):
    log("=== PHASE C: V5 Brief Quality Scoring (all 12 subjects) ===")

    results = []

    for name, subject_dir in ALL_SUBJECTS:
        brief = load_brief(subject_dir)
        if not brief:
            log(f"  SKIP {name}: no brief found")
            continue

        # Mechanical scoring
        import re
        score = {
            "subject": name,
            "chars": len(brief),
            "has_injectable": "injectable block" in brief.lower(),
            "has_cannot_predict": "cannot predict" in brief.lower(),
            "bold_sections": len(re.findall(r'\*\*[A-Z][A-Z ]+\*\*', brief)),
            "false_positive_refs": len(re.findall(r'(?:false positive|not active|not always)', brief, re.IGNORECASE)),
            "temporal_refs": len(re.findall(r'(?:temporal|situational|stable|evolv)', brief, re.IGNORECASE)),
        }

        # Embed and compare to layers (coverage proxy)
        layers_dir = Path(subject_dir) / "data" / "identity_layers"
        layer_text = ""
        for fname in ["anchors_v4.md", "core_v4.md", "predictions_v4.md"]:
            p = layers_dir / fname
            if p.exists():
                layer_text += p.read_text(encoding="utf-8")

        if not dry_run and layer_text:
            a = get_embedding(brief[:3000])
            b = get_embedding(layer_text[:3000])
            if a and b:
                score["coverage_sim"] = round(cosine_sim(a, b), 3)

        log(f"  {name}: chars={score['chars']}, sections={score['bold_sections']}, fp={score['false_positive_refs']}, cannot_predict={score['has_cannot_predict']}")
        results.append(score)

    return results


# ============================================================================
# PHASE D: Behavioral differentiation
# ============================================================================

def phase_d(installed, dry_run=False):
    log("=== PHASE D: Behavioral Differentiation Test ===")

    models = [m for m in PIPELINE_MODELS if is_model_available(m, installed)]
    if not models:
        log("  No models available")
        return {}

    model = models[0]  # Use best available
    log(f"  Using model: {model}")

    results = {"model": model, "questions": {}}

    for q in DIFF_QUESTIONS:
        log(f"\n  Q: {q[:60]}...")
        results["questions"][q] = {}
        responses = {}

        for subj_name in DIFF_SUBJECTS:
            subject_dir = next((d for n, d in ALL_SUBJECTS if n == subj_name), None)
            if not subject_dir:
                continue
            brief = load_brief(subject_dir)
            if not brief:
                continue

            prompt = f"""{brief[:2000]}

---

Question: {q}

Answer in 2-3 sentences in this person's voice and reasoning style."""

            if dry_run:
                log(f"    [DRY] {subj_name}")
                responses[subj_name] = "DRY RUN"
                continue

            r = call_ollama(model, prompt, max_tokens=300, temperature=0.3)
            responses[subj_name] = r["text"]
            log(f"    {subj_name}: {r['time']}s — {r['text'][:80]}...")

        # Measure pairwise divergence between responses
        if not dry_run and len(responses) > 1:
            names = list(responses.keys())
            embeddings = {n: get_embedding(t) for n, t in responses.items() if t}
            pairs = []
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    a, b = embeddings.get(names[i]), embeddings.get(names[j])
                    if a and b:
                        sim = cosine_sim(a, b)
                        pairs.append({"pair": f"{names[i]}-{names[j]}", "similarity": round(sim, 3)})

            avg_sim = sum(p["similarity"] for p in pairs) / len(pairs) if pairs else 0
            divergence = round(1 - avg_sim, 3)
            log(f"  Avg divergence: {divergence} (1=fully different, 0=identical)")
            results["questions"][q] = {
                "responses": responses,
                "pairwise": pairs,
                "avg_divergence": divergence,
            }
        else:
            results["questions"][q] = {"responses": responses}

    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["A", "B", "C", "D"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log(f"OVERNIGHT LOCAL MODEL EVAL — {timestamp}")
    log(f"Results dir: {RESULTS_DIR}")

    installed = check_models()
    log(f"Installed models: {installed}")

    phases = [args.phase] if args.phase else ["A", "B", "C", "D"]
    all_results = {"timestamp": timestamp, "installed_models": installed}

    for phase in phases:
        t0 = time.time()
        if phase == "A":
            all_results["phase_A"] = phase_a(installed, args.dry_run)
        elif phase == "B":
            all_results["phase_B"] = phase_b(installed, args.dry_run)
        elif phase == "C":
            all_results["phase_C"] = phase_c(args.dry_run)
        elif phase == "D":
            all_results["phase_D"] = phase_d(installed, args.dry_run)
        elapsed = round(time.time() - t0, 1)
        log(f"Phase {phase} done in {elapsed}s")

    out = RESULTS_DIR / f"overnight_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    log(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
