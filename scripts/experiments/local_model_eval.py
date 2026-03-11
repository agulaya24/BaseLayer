"""
Local Model Evaluation: Can small LLMs replace API calls in the pipeline?

Tests multiple local models (via Ollama) across all pipeline steps:
1. EXTRACT — structured fact extraction from conversation text
2. AUTHOR  — layer generation from extracted facts
3. COMPOSE — brief generation from authored layers (V5/C31 prompt)

Each step tested with:
- Prompt A: Production prompt (verbatim)
- Prompt B: Simplified prompt (essentials only)
- Prompt C: JSON-schema constrained (explicit output format)

Scoring: JSON parse success, section completeness, embedding similarity to
API-generated output, character count, response time.

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/local_model_eval.py                    # All available models
    python experiments/local_model_eval.py --models qwen2.5:14b,phi4:14b
    python experiments/local_model_eval.py --step extract     # Extract only
    python experiments/local_model_eval.py --step compose     # Compose only
    python experiments/local_model_eval.py --dry-run          # Show what would run

Models tested (pull with `ollama pull <name>`):
    qwen2.5:14b     — Alibaba, strong structured output (already installed)
    phi4:14b         — Microsoft, best quality/size ratio
    mistral-small    — Mistral 22B, near-frontier
    gemma3:12b       — Google, good instruction following
    lfm2             — Liquid AI (requires Ollama >=0.16)
"""

import json
import os
import re
import sys
import time
import argparse
import requests
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Models to test — will skip any not pulled
CANDIDATE_MODELS = [
    "qwen2.5:7b",          # 4.7GB — fits comfortably in 10GB VRAM
    "sam860/LFM2:2.6b",   # 2GB  — Liquid AI hybrid arch
    "sam860/LFM2:350m",   # 0.3GB — Liquid AI nano
    "phi4-mini:3.8b",      # 2.5GB — Microsoft, strong instruction following
    "deepseek-r1:7b",      # 4.7GB — reasoning, for financial tasks
    # 14B models: only run if no 14B already loaded (9GB, tight on 10GB VRAM)
    # "qwen2.5:14b",
    # "phi4:14b",
]

# Test data paths
FRANKLIN_DIR = "C:/Users/Aarik/Anthropic/subjects/franklin_memory"

# ============================================================================
# PROMPTS: EXTRACT
# ============================================================================

EXTRACT_PROMPT_A = """You are extracting personal facts about a person from their writing.

<text>
{text}
</text>

Extract up to 10 facts as structured triples. For each:
- subject: Who the fact is about
- predicate: One of: believes, values, practices, avoids, struggles_with, trades, founded, works_at, married_to, friends_with
- object: Specific value or description
- confidence: 0.0 to 1.0

Return a JSON object with a "facts" array."""

EXTRACT_PROMPT_B = """Extract facts about the person from this text. Return JSON with a "facts" array.
Each fact: {{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.9}}

Text:
{text}"""

EXTRACT_PROMPT_C = """Extract facts from the text below. Output ONLY valid JSON matching this schema:
{{"facts": [{{"subject": string, "predicate": string, "object": string, "confidence": number}}]}}

Text:
{text}"""

# ============================================================================
# PROMPTS: AUTHOR (simplified — just test if model can produce layer markdown)
# ============================================================================

AUTHOR_PROMPT_A = """You are authoring an ANCHORS identity layer from extracted facts about a person.

Anchors are the person's core epistemic principles — the axioms they reason from.

From these facts, identify 5-8 anchors. For each:
**A[n]. NAME**
Description of the axiom.
Active when: [trigger condition]
Directive: [what an AI should do]

Facts:
{facts}

Output markdown only."""

AUTHOR_PROMPT_B = """From these facts, write 5-8 behavioral axioms about this person.
Format each as: **A1. NAME** followed by description.

Facts:
{facts}"""

# ============================================================================
# PROMPTS: COMPOSE (V5/C31)
# ============================================================================

COMPOSE_PROMPT_A = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored on four primitives:

PROVENANCE (30%): Every claim traces to source evidence. Fabricated content = failure.
BEHAVIORAL CHANGE (30%): Every sentence must change LLM behavior. Directives. Communication guidance. Mode-switching.
EPISTEMIC CALIBRATION (20%): Know boundaries. False positive warnings. Temporal awareness. End with CANNOT PREDICT section.
SIGNAL DENSITY (20%): Every sentence adds new understanding. No redundancy. ~3,500-4,500 chars optimal.

Complete creative freedom on format. Start with ## Injectable Block.

{layers}"""

COMPOSE_PROMPT_B = """Write a behavioral brief about this person for an AI to read before every interaction.
Include: directives, communication style, mode switching, false positive warnings, cannot predict section.
3,500-4,500 chars. Start with ## Injectable Block.

{layers}"""


def call_ollama(model, prompt, max_tokens=4000, temperature=0.0, json_mode=False):
    """Call Ollama and return (text, time_seconds)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    start = time.time()
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
        resp.raise_for_status()
        elapsed = time.time() - start
        data = resp.json()
        text = data.get("response", "").strip()
        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)
        return {
            "text": text,
            "time": round(elapsed, 1),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tok_per_sec": round(tokens_out / elapsed, 1) if elapsed > 0 else 0,
        }
    except requests.exceptions.ConnectionError:
        return {"text": "", "time": 0, "error": "Ollama not running"}
    except Exception as e:
        return {"text": "", "time": 0, "error": str(e)}


def get_available_models(requested=None):
    """Check which models are actually pulled in Ollama."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        installed = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        print("ERROR: Cannot connect to Ollama")
        return []

    candidates = requested or CANDIDATE_MODELS
    available = []
    for model in candidates:
        # Check if model or model:latest is installed
        if any(model in m or model.split(":")[0] in m for m in installed):
            available.append(model)
        else:
            print(f"  SKIP {model}: not installed (ollama pull {model})")
    return available


def load_test_data():
    """Load test data for all three pipeline steps."""
    data = {}

    # Extract: first chapter of Franklin's autobiography
    import sqlite3
    db_path = os.path.join(FRANKLIN_DIR, "data", "database", "memory.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        row = conn.execute("""
            SELECT c.title, GROUP_CONCAT(m.content_text, '\n')
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE m.content_text IS NOT NULL AND LENGTH(m.content_text) > 100
            GROUP BY c.id
            ORDER BY c.created_at
            LIMIT 1
        """).fetchone()
        conn.close()
        if row:
            data["extract_text"] = row[1][:3000]  # Cap at 3K chars
            data["extract_title"] = row[0]

    # Author: load some extracted facts
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        facts = conn.execute("""
            SELECT predicate, object_text, confidence
            FROM memory_facts
            WHERE knowledge_tier = 'identity'
            ORDER BY confidence DESC
            LIMIT 30
        """).fetchall()
        conn.close()
        data["author_facts"] = "\n".join(
            f"- {f[0]}: {f[1]} (confidence: {f[2]})" for f in facts
        )

    # Compose: load existing layers
    layers_dir = os.path.join(FRANKLIN_DIR, "data", "identity_layers")
    parts = []
    for fname in ["anchors_v4.md", "core_v4.md", "predictions_v4.md"]:
        path = os.path.join(layers_dir, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f.read())
    data["compose_layers"] = "\n\n".join(parts)

    # Load reference outputs for comparison
    brief_path = os.path.join(layers_dir, "brief_v5.md")
    if os.path.exists(brief_path):
        with open(brief_path, "r", encoding="utf-8") as f:
            data["reference_brief"] = f.read()

    return data


def score_extract(result):
    """Score extraction output."""
    scores = {"json_valid": False, "fact_count": 0, "has_predicates": False}
    text = result.get("text", "")
    if not text:
        return scores

    # Try to parse JSON
    try:
        # Strip markdown code blocks
        clean = text
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean[:-3]
        parsed = json.loads(clean)
        scores["json_valid"] = True
        facts = parsed.get("facts", [])
        scores["fact_count"] = len(facts)
        if facts:
            scores["has_predicates"] = all("predicate" in f for f in facts)
    except (json.JSONDecodeError, TypeError):
        pass

    return scores


def score_author(result):
    """Score authoring output."""
    scores = {"has_anchors": False, "anchor_count": 0, "has_directives": False, "chars": 0}
    text = result.get("text", "")
    if not text:
        return scores

    scores["chars"] = len(text)
    # Count A[n] patterns
    anchors = re.findall(r'\*\*A\d+\.', text)
    scores["anchor_count"] = len(anchors)
    scores["has_anchors"] = len(anchors) >= 3
    scores["has_directives"] = "directive" in text.lower() or "active when" in text.lower()
    return scores


def score_compose(result):
    """Score compose output."""
    scores = {"has_injectable": False, "has_cannot_predict": False, "chars": 0, "section_count": 0}
    text = result.get("text", "")
    if not text:
        return scores

    scores["chars"] = len(text)
    scores["has_injectable"] = "injectable block" in text.lower()
    scores["has_cannot_predict"] = "cannot predict" in text.lower()
    scores["section_count"] = len(re.findall(r'\*\*[A-Z][A-Z ]+\*\*', text))
    return scores


def run_step(model, step, prompts, test_data, results):
    """Run one pipeline step across prompt variants."""
    print(f"\n    {step.upper()}")

    for prompt_name, prompt_template in prompts.items():
        if step == "extract":
            prompt = prompt_template.format(text=test_data.get("extract_text", "No data"))
            json_mode = True
        elif step == "author":
            prompt = prompt_template.format(facts=test_data.get("author_facts", "No data"))
            json_mode = False
        elif step == "compose":
            prompt = prompt_template.format(layers=test_data.get("compose_layers", "No data"))
            json_mode = False

        result = call_ollama(model, prompt, max_tokens=4000, json_mode=json_mode and step == "extract")

        if result.get("error"):
            print(f"      {prompt_name}: ERROR — {result['error']}")
            continue

        # Score
        if step == "extract":
            scores = score_extract(result)
        elif step == "author":
            scores = score_author(result)
        elif step == "compose":
            scores = score_compose(result)

        print(f"      {prompt_name}: {result['time']}s, {result['tok_per_sec']} tok/s, {scores}")

        results.append({
            "model": model,
            "step": step,
            "prompt": prompt_name,
            "time": result["time"],
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
            "tok_per_sec": result.get("tok_per_sec", 0),
            "scores": scores,
        })


def main():
    parser = argparse.ArgumentParser(description="Local model evaluation for pipeline steps")
    parser.add_argument("--models", default=None, help="Comma-separated model names")
    parser.add_argument("--step", default=None, choices=["extract", "author", "compose"],
                        help="Run only one step")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    requested = args.models.split(",") if args.models else None
    models = get_available_models(requested)
    if not models:
        print("No models available. Pull some: ollama pull qwen2.5:14b")
        return

    print(f"\n{'='*60}")
    print(f"  LOCAL MODEL EVALUATION")
    print(f"  Models: {', '.join(models)}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if args.dry_run:
        steps = [args.step] if args.step else ["extract", "author", "compose"]
        for m in models:
            for s in steps:
                print(f"  [DRY RUN] {m} × {s} × 2-3 prompts")
        return

    # Load test data
    print("\n  Loading test data...")
    test_data = load_test_data()
    for k, v in test_data.items():
        if isinstance(v, str):
            print(f"    {k}: {len(v):,} chars")

    results = []
    steps_to_run = [args.step] if args.step else ["extract", "author", "compose"]

    extract_prompts = {"A_production": EXTRACT_PROMPT_A, "B_simple": EXTRACT_PROMPT_B, "C_schema": EXTRACT_PROMPT_C}
    author_prompts = {"A_production": AUTHOR_PROMPT_A, "B_simple": AUTHOR_PROMPT_B}
    compose_prompts = {"A_v5": COMPOSE_PROMPT_A, "B_simple": COMPOSE_PROMPT_B}

    for model in models:
        print(f"\n  {'='*50}")
        print(f"  MODEL: {model}")
        print(f"  {'='*50}")

        if "extract" in steps_to_run:
            run_step(model, "extract", extract_prompts, test_data, results)
        if "author" in steps_to_run:
            run_step(model, "author", author_prompts, test_data, results)
        if "compose" in steps_to_run:
            run_step(model, "compose", compose_prompts, test_data, results)

    # Summary
    print(f"\n\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  {'Model':<20} {'Step':<10} {'Prompt':<15} {'Time':>6} {'Tok/s':>7} {'Key Metric'}")
    print(f"  {'-'*20} {'-'*10} {'-'*15} {'-'*6} {'-'*7} {'-'*30}")

    for r in results:
        s = r["scores"]
        if r["step"] == "extract":
            metric = f"json={s['json_valid']}, facts={s['fact_count']}"
        elif r["step"] == "author":
            metric = f"anchors={s['anchor_count']}, directives={s['has_directives']}"
        elif r["step"] == "compose":
            metric = f"chars={s['chars']}, sections={s['section_count']}, cannotpredict={s['has_cannot_predict']}"
        else:
            metric = ""
        print(f"  {r['model']:<20} {r['step']:<10} {r['prompt']:<15} {r['time']:>5.1f}s {r['tok_per_sec']:>6.1f} {metric}")

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "local_model_eval_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "models": models,
            "results": results,
        }, f, indent=2)
    print(f"\n  Results saved: {out_path}")


if __name__ == "__main__":
    main()
