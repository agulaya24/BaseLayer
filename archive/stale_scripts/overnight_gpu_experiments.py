#!/usr/bin/env python3
"""
Overnight GPU experiments — local model evaluation for pipeline steps.
Run: python overnight_gpu_experiments.py

Tests extraction, classification, and authoring quality of local models
against API baselines (Haiku/Sonnet) using Franklin as the test subject.
"""

import json
import os
import re
import sqlite3
import time
import requests
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
RESULTS_DIR = Path("gpu_experiment_results")
RESULTS_DIR.mkdir(exist_ok=True)

FRANKLIN_DIR = Path("C:/Users/Aarik/Anthropic/subjects/franklin_memory")
FRANKLIN_DB = FRANKLIN_DIR / "data" / "database" / "memory.db"


def ollama_generate(model: str, prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """Call Ollama API and return response text."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 8192},
    }
    if system:
        payload["system"] = system

    start = time.time()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start
        return data.get("response", ""), elapsed
    except Exception as e:
        return f"ERROR: {e}", time.time() - start


def get_franklin_conversations(limit=5):
    """Get first N Franklin conversations with messages."""
    conn = sqlite3.connect(str(FRANKLIN_DB))
    conn.row_factory = sqlite3.Row
    convs = conn.execute(
        "SELECT id, title FROM conversations ORDER BY id LIMIT ?", (limit,)
    ).fetchall()

    results = []
    for conv in convs:
        msgs = conn.execute(
            "SELECT role, content_text as content FROM messages WHERE conversation_id = ? ORDER BY sequence_order",
            (conv["id"],)
        ).fetchall()
        text = "\n".join(f"{m['role']}: {m['content']}" for m in msgs if m["content"])
        results.append({"id": conv["id"], "title": conv["title"], "text": text[:4000]})

    conn.close()
    return results


def get_franklin_facts(limit=50):
    """Get Franklin facts for classification testing."""
    conn = sqlite3.connect(str(FRANKLIN_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT fact_text, predicate, category FROM memory_facts ORDER BY confidence DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_haiku_baseline_facts():
    """Get existing Haiku-extracted facts as baseline."""
    conn = sqlite3.connect(str(FRANKLIN_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT fact_text, predicate, knowledge_tier, category, confidence
        FROM memory_facts
        WHERE predicate IS NOT NULL
        ORDER BY confidence DESC
        LIMIT 100
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# EXPERIMENT 1: EXTRACTION
# ============================================================

EXTRACTION_PROMPT = """Extract behavioral facts from this text about a person.
For each fact, output a JSON object with:
- subject: who the fact is about
- predicate: one of [believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with, prioritizes, identifies_as, experienced, decided, builds, founded, aspires_to, prefers]
- object: what the fact states
- confidence: 0.0-1.0

Output ONLY a JSON array of facts. No explanation.

TEXT:
{text}
"""

def run_extraction_experiment(model: str, conversations: list) -> dict:
    """Run extraction on conversations and measure quality."""
    print(f"\n  Extraction with {model}...")
    results = []

    for conv in conversations:
        prompt = EXTRACTION_PROMPT.format(text=conv["text"][:3000])
        response, elapsed = ollama_generate(model, prompt)

        # Try to parse JSON
        facts = []
        try:
            # Find JSON array in response
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                facts = json.loads(match.group())
        except json.JSONDecodeError:
            pass

        valid_facts = [f for f in facts if isinstance(f, dict) and "predicate" in f and "object" in f]

        results.append({
            "conversation": conv["title"],
            "facts_extracted": len(valid_facts),
            "parse_success": len(facts) > 0,
            "elapsed_seconds": round(elapsed, 1),
            "sample_facts": valid_facts[:3],
        })
        print(f"    {conv['title'][:40]}: {len(valid_facts)} facts in {elapsed:.1f}s")

    return {
        "model": model,
        "experiment": "extraction",
        "total_facts": sum(r["facts_extracted"] for r in results),
        "avg_per_conversation": round(sum(r["facts_extracted"] for r in results) / max(len(results), 1), 1),
        "parse_success_rate": round(sum(1 for r in results if r["parse_success"]) / max(len(results), 1), 2),
        "avg_seconds": round(sum(r["elapsed_seconds"] for r in results) / max(len(results), 1), 1),
        "details": results,
    }


# ============================================================
# EXPERIMENT 2: TENSION CLASSIFICATION
# ============================================================

CLASSIFICATION_PROMPT = """Given two behavioral facts about the same person, classify their relationship.

Fact A: {fact_a}
Fact B: {fact_b}

Classify as one of:
- CONSISTENT: facts are compatible
- TENSION: facts pull in different directions but can coexist
- CONTRADICTION: facts directly conflict

Output ONLY a JSON object with:
- verdict: CONSISTENT, TENSION, or CONTRADICTION
- reasoning: one sentence explaining why

JSON:"""

def run_classification_experiment(model: str, fact_pairs: list) -> dict:
    """Run tension classification and compare to Haiku baseline."""
    print(f"\n  Classification with {model}...")
    results = []

    for pair in fact_pairs[:30]:
        prompt = CLASSIFICATION_PROMPT.format(fact_a=pair["fact_a"], fact_b=pair["fact_b"])
        response, elapsed = ollama_generate(model, prompt, temperature=0.1)

        verdict = "UNKNOWN"
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                verdict = data.get("verdict", "UNKNOWN")
        except json.JSONDecodeError:
            # Try to find verdict keyword
            for v in ["CONTRADICTION", "TENSION", "CONSISTENT"]:
                if v in response.upper():
                    verdict = v
                    break

        results.append({
            "fact_a": pair["fact_a"][:80],
            "fact_b": pair["fact_b"][:80],
            "verdict": verdict,
            "elapsed": round(elapsed, 1),
        })

    verdicts = [r["verdict"] for r in results]
    return {
        "model": model,
        "experiment": "classification",
        "total_pairs": len(results),
        "verdicts": {
            "CONSISTENT": verdicts.count("CONSISTENT"),
            "TENSION": verdicts.count("TENSION"),
            "CONTRADICTION": verdicts.count("CONTRADICTION"),
            "UNKNOWN": verdicts.count("UNKNOWN"),
        },
        "avg_seconds": round(sum(r["elapsed"] for r in results) / max(len(results), 1), 1),
        "details": results,
    }


# ============================================================
# EXPERIMENT 3: AUTHORING (ANCHORS)
# ============================================================

AUTHORING_PROMPT = """You are analyzing behavioral facts extracted from a person's writing.
Synthesize these facts into 3-5 "epistemic axioms" — foundational beliefs this person reasons FROM.

Each axiom should have:
- id: A1, A2, etc.
- name: SHORT ALL-CAPS NAME (2-3 words)
- description: 1-2 sentences explaining the belief
- activeWhen: when this axiom becomes relevant

Facts:
{facts}

Output as a JSON array of axioms. No explanation."""

def run_authoring_experiment(model: str, facts: list) -> dict:
    """Run anchor authoring and evaluate quality."""
    print(f"\n  Authoring with {model}...")

    facts_text = "\n".join(f"- {f['fact_text']}" for f in facts[:60])
    prompt = AUTHORING_PROMPT.format(facts=facts_text)

    response, elapsed = ollama_generate(model, prompt, temperature=0.4)

    axioms = []
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            axioms = json.loads(match.group())
    except json.JSONDecodeError:
        pass

    valid = [a for a in axioms if isinstance(a, dict) and "name" in a]

    return {
        "model": model,
        "experiment": "authoring",
        "axioms_generated": len(valid),
        "elapsed_seconds": round(elapsed, 1),
        "axioms": valid,
        "raw_response_length": len(response),
    }


# ============================================================
# MAIN
# ============================================================

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 60)
    print(f"OVERNIGHT GPU EXPERIMENTS — {timestamp}")
    print("=" * 60)
    print(f"Subject: Franklin (public example)")
    print(f"Database: {FRANKLIN_DB}")

    # Load data
    print("\nLoading data...")
    conversations = get_franklin_conversations(5)
    print(f"  {len(conversations)} conversations loaded")

    baseline_facts = get_haiku_baseline_facts()
    print(f"  {len(baseline_facts)} baseline facts loaded")

    # Build fact pairs for classification
    fact_pairs = []
    for i in range(min(30, len(baseline_facts) - 1)):
        fact_pairs.append({
            "fact_a": baseline_facts[i]["fact_text"],
            "fact_b": baseline_facts[i + 1]["fact_text"],
        })

    all_results = []

    # Experiment 1: Extraction with multiple models
    models_extraction = ["qwen2.5:14b", "phi4:14b", "qwen2.5:7b", "sam860/LFM2:2.6b"]
    for model in models_extraction:
        try:
            result = run_extraction_experiment(model, conversations)
            all_results.append(result)
        except Exception as e:
            print(f"  ERROR with {model}: {e}")
            all_results.append({"model": model, "experiment": "extraction", "error": str(e)})

    # Experiment 2: Classification
    models_classify = ["qwen2.5:14b", "phi4:14b"]
    for model in models_classify:
        try:
            result = run_classification_experiment(model, fact_pairs)
            all_results.append(result)
        except Exception as e:
            print(f"  ERROR with {model}: {e}")
            all_results.append({"model": model, "experiment": "classification", "error": str(e)})

    # Experiment 3: Authoring
    models_author = ["qwen2.5:14b", "phi4:14b", "deepseek-r1:14b"]
    for model in models_author:
        try:
            result = run_authoring_experiment(model, baseline_facts)
            all_results.append(result)
        except Exception as e:
            print(f"  ERROR with {model}: {e}")
            all_results.append({"model": model, "experiment": "authoring", "error": str(e)})

    # Save results
    output_file = RESULTS_DIR / f"results_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in all_results:
        if "error" in r:
            print(f"  {r['model']} ({r['experiment']}): ERROR — {r['error']}")
        elif r["experiment"] == "extraction":
            print(f"  {r['model']} (extraction): {r['total_facts']} facts, {r['avg_seconds']}s avg, {r['parse_success_rate']*100:.0f}% parse")
        elif r["experiment"] == "classification":
            v = r["verdicts"]
            print(f"  {r['model']} (classification): {v.get('TENSION',0)}T {v.get('CONTRADICTION',0)}C {v.get('CONSISTENT',0)}S {v.get('UNKNOWN',0)}? — {r['avg_seconds']}s avg")
        elif r["experiment"] == "authoring":
            print(f"  {r['model']} (authoring): {r['axioms_generated']} axioms in {r['elapsed_seconds']}s")

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
