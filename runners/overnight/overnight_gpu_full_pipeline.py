#!/usr/bin/env python3
"""
Overnight GPU Full Pipeline Test — Can local models replace API for the ENTIRE pipeline?

Previous test (S83): Extraction works locally. Authoring failed on all 7 models.
This test: Prompt optimization + larger context + temperature sweeps + full compose.

Goal: Find the cheapest local configuration that produces usable identity models.

Tests:
  1. EXTRACTION — top 3 models (mistral:7b, phi4:14b, gemma2:9b) on 10 convos
  2. AUTHORING — all 3 layers with optimized prompts (chain-of-thought, few-shot, structured)
  3. COMPOSE — unified brief generation from authored layers
  4. QUALITY — compare local output vs API output side-by-side

Subject: Kevin Kelly (known baseline, 76 Haiku facts)

Run: python overnight_gpu_full_pipeline.py
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
RESULTS_DIR = Path("gpu_experiment_results/full_pipeline")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Use Kevin Kelly as test subject (known baseline)
KK_DIR = Path("C:/Users/Aarik/Anthropic/subjects/kevin_kelly_memory")
KK_DB = KK_DIR / "data" / "database" / "memory.db"

# Also test on Franklin for cross-subject validation
FRANKLIN_DIR = Path("C:/Users/Aarik/Anthropic/subjects/franklin_memory")
FRANKLIN_DB = FRANKLIN_DIR / "data" / "database" / "memory.db"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Models to test — S97: added 27b/32b large models
EXTRACTION_MODELS = ["mistral:7b", "gemma2:27b", "qwen2.5:32b"]
AUTHORING_MODELS = ["phi4:14b", "qwen2.5:14b", "deepseek-r1:14b", "gemma2:27b", "deepseek-r1:32b", "qwen2.5:32b"]
COMPOSE_MODELS = ["phi4:14b", "qwen2.5:14b", "deepseek-r1:14b", "gemma2:27b", "deepseek-r1:32b", "qwen2.5:32b"]


def ollama_generate(model, prompt, system="", temperature=0.3, num_ctx=8192):
    """Call Ollama API."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    if system:
        payload["system"] = system

    start = time.time()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start
        return data.get("response", ""), elapsed
    except Exception as e:
        return f"ERROR: {e}", time.time() - start


def get_conversations(db_path, limit=10):
    """Get conversations with full text."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    convs = conn.execute(
        "SELECT id, title FROM conversations ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    results = []
    for conv in convs:
        msgs = conn.execute(
            "SELECT role, content_text as content FROM messages WHERE conversation_id = ? ORDER BY sequence_order",
            (conv["id"],),
        ).fetchall()
        text = "\n".join(f"{m['content']}" for m in msgs if m["content"])
        results.append({"id": conv["id"], "title": conv["title"], "text": text})
    conn.close()
    return results


def get_facts(db_path, limit=200):
    """Get existing facts."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT fact_text, predicate, object_text, knowledge_tier, category, confidence "
        "FROM memory_facts WHERE predicate IS NOT NULL ORDER BY confidence DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log(msg, f=None):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if f:
        f.write(line + "\n")
        f.flush()


# ============================================================
# EXPERIMENT 1: EXTRACTION with optimized prompts
# ============================================================

# Original prompt (baseline)
EXTRACT_V1 = """Extract behavioral facts from this text about a person.
For each fact, output a JSON object with:
- subject: who the fact is about
- predicate: one of [believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with, prioritizes, identifies_as, experienced, decided, builds, founded, aspires_to, prefers]
- object: what the fact states
- confidence: 0.0-1.0

Output ONLY a JSON array of facts. No explanation.

TEXT:
{text}"""

# Optimized prompt — constrained predicates, examples, document mode
EXTRACT_V2 = """You are extracting behavioral identity facts from a document written by or about a person.

RULES:
1. Each fact must use EXACTLY one predicate from this list:
   believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with,
   prioritizes, identifies_as, experienced, decided, builds, founded, aspires_to,
   prefers, follows, monitors, maintains, hates, dislikes, loves
2. Extract IMPLICIT worldview, not just stated opinions
3. Focus on behavioral patterns, not biographical events
4. Confidence: 0.9+ for explicit statements, 0.6-0.8 for strong inference, 0.3-0.5 for weak inference

OUTPUT: JSON array only. Each item: {{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.0-1.0}}

DOCUMENT:
{text}"""

# Chain-of-thought extraction
EXTRACT_V3 = """Read this document carefully. First identify the author's core beliefs, values, and behavioral patterns.
Then extract each as a structured fact.

Step 1: What does this person believe deeply? What do they value? What do they avoid?
Step 2: For each insight, create a fact with predicate from: [believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with, prioritizes, identifies_as, aspires_to, prefers, follows, maintains, loves, hates]

Output your analysis, then a JSON array of facts at the end between ```json and ``` markers.

DOCUMENT:
{text}"""


def run_extraction_test(model, conversations, prompt_template, prompt_name, logfile):
    """Run extraction with a specific prompt template."""
    log(f"  Extraction: {model} / {prompt_name}", logfile)
    results = []
    total_facts = 0

    for conv in conversations:
        text = conv["text"][:4000]
        prompt = prompt_template.format(text=text)
        response, elapsed = ollama_generate(model, prompt, num_ctx=8192)

        facts = []
        try:
            # Try JSON array
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                facts = json.loads(match.group())
            # Try ```json block
            elif "```json" in response:
                match = re.search(r'```json\s*(.*?)```', response, re.DOTALL)
                if match:
                    facts = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

        valid = [f for f in facts if isinstance(f, dict) and "predicate" in f and "object" in f]
        total_facts += len(valid)
        results.append({
            "title": conv["title"][:50],
            "facts": len(valid),
            "elapsed": round(elapsed, 1),
            "sample": valid[:2],
        })
        log(f"    {conv['title'][:40]}: {len(valid)} facts, {elapsed:.1f}s", logfile)

    return {
        "model": model,
        "prompt": prompt_name,
        "total_facts": total_facts,
        "avg_facts": round(total_facts / max(len(conversations), 1), 1),
        "avg_seconds": round(sum(r["elapsed"] for r in results) / max(len(results), 1), 1),
        "details": results,
    }


# ============================================================
# EXPERIMENT 2: AUTHORING with optimized prompts
# ============================================================

ANCHORS_PROMPT_V1 = """You are synthesizing behavioral facts into epistemic axioms — the foundational beliefs a person reasons FROM, not conclusions they reach.

FACTS:
{facts}

Generate 5-8 axioms. Each axiom:
- id: A1, A2, etc.
- name: SHORT ALL-CAPS NAME (2-4 words)
- description: 2-3 sentences. What this person believes at a fundamental level.
- activeWhen: When this axiom becomes the dominant lens (1 sentence)
- provenance: Which fact numbers support this (e.g., [1, 5, 12])

Express axioms as what this person GRAVITATES TOWARD, not what they reject.
Only use rejection framing when facts explicitly use avoidance predicates.

Output as a JSON array."""

ANCHORS_PROMPT_V2 = """# Task: Epistemic Axiom Synthesis

You have behavioral facts about a person. Synthesize them into 5-8 foundational axioms — beliefs so deep they function as cognitive infrastructure.

## What makes a good axiom:
- It explains MULTIPLE facts (not just one)
- It's predictive (you could guess this person's stance on new topics)
- It captures HOW they think, not WHAT they think about
- It's specific to THIS person (not generic wisdom)

## Facts:
{facts}

## Output format (JSON array):
```json
[
  {{
    "id": "A1",
    "name": "SHORT ALL-CAPS NAME",
    "description": "2-3 sentences describing the foundational belief.",
    "activeWhen": "When this axiom dominates their reasoning.",
    "provenance": [1, 5, 12]
  }}
]
```

Think carefully about which facts cluster together before generating axioms."""

CORE_PROMPT = """# Task: Context Mode Synthesis

Given these behavioral facts, identify 4-6 "context modes" — distinct operational states this person enters depending on the situation.

A context mode answers: "When this person is in situation X, they reliably do Y."

## Facts:
{facts}

## Output format (JSON array):
```json
[
  {{
    "id": "C1",
    "name": "SHORT ALL-CAPS NAME",
    "description": "2-3 sentences describing this operational mode.",
    "triggers": "What activates this mode.",
    "behaviors": "Observable behaviors when in this mode.",
    "provenance": [3, 7, 15]
  }}
]
```"""

PREDICTIONS_PROMPT = """# Task: Behavioral Prediction Synthesis

Given these behavioral facts, generate 4-6 falsifiable predictions about how this person would respond to novel situations.

Each prediction must be:
- Specific enough to be wrong
- Grounded in 2+ facts
- About behavior, not opinions

## Facts:
{facts}

## Output format (JSON array):
```json
[
  {{
    "id": "P1",
    "name": "SHORT ALL-CAPS NAME",
    "scenario": "A specific situation this person might face.",
    "prediction": "What they would do and why.",
    "confidence": 0.7,
    "provenance": [2, 8, 14]
  }}
]
```"""

COMPOSE_PROMPT = """# Task: Identity Brief Composition

You have three layers of behavioral analysis for a person:
- AXIOMS: Their foundational beliefs
- CONTEXT MODES: How they operate in different situations
- PREDICTIONS: How they'd respond to novel scenarios

Compose a unified narrative brief (800-1200 words) that:
1. Opens with the single most defining characteristic
2. Weaves axioms, modes, and predictions into a coherent portrait
3. Uses specific language (not generic)
4. Never references the analysis process — describe WHO this person is
5. Writes in third person

## AXIOMS:
{anchors}

## CONTEXT MODES:
{core}

## PREDICTIONS:
{predictions}

Write the brief now. No preamble, no headers, just the narrative."""


def run_authoring_test(model, facts, prompt_template, layer_name, logfile, temperature=0.4, num_ctx=8192):
    """Run a single authoring layer."""
    log(f"  Authoring {layer_name}: {model}", logfile)

    facts_text = "\n".join(f"{i+1}. [{f['predicate']}] {f['fact_text']}" for i, f in enumerate(facts[:80]))
    prompt = prompt_template.format(facts=facts_text)

    response, elapsed = ollama_generate(model, prompt, temperature=temperature, num_ctx=num_ctx)

    # Try to parse
    items = []
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            items = json.loads(match.group())
        elif "```json" in response:
            match = re.search(r'```json\s*(.*?)```', response, re.DOTALL)
            if match:
                items = json.loads(match.group(1))
    except json.JSONDecodeError:
        pass

    valid = [x for x in items if isinstance(x, dict) and ("name" in x or "id" in x)]

    return {
        "model": model,
        "layer": layer_name,
        "items_generated": len(valid),
        "parse_success": len(valid) > 0,
        "elapsed": round(elapsed, 1),
        "raw_length": len(response),
        "items": valid,
        "raw_response": response[:2000],
    }


def run_compose_test(model, anchors, core, predictions, logfile, temperature=0.5, num_ctx=16384):
    """Run brief composition."""
    log(f"  Compose: {model}", logfile)

    anchors_text = json.dumps(anchors, indent=2)[:3000]
    core_text = json.dumps(core, indent=2)[:3000]
    preds_text = json.dumps(predictions, indent=2)[:3000]

    prompt = COMPOSE_PROMPT.format(anchors=anchors_text, core=core_text, predictions=preds_text)

    response, elapsed = ollama_generate(model, prompt, temperature=temperature, num_ctx=num_ctx)

    word_count = len(response.split())

    return {
        "model": model,
        "word_count": word_count,
        "elapsed": round(elapsed, 1),
        "brief": response[:5000],
        "usable": word_count >= 300 and not response.startswith("ERROR"),
    }


# ============================================================
# MAIN
# ============================================================

def main():
    logpath = RESULTS_DIR / f"overnight_{TIMESTAMP}.log"
    logfile = open(logpath, "w", encoding="utf-8")

    log(f"{'='*60}", logfile)
    log(f"OVERNIGHT GPU FULL PIPELINE TEST", logfile)
    log(f"Started: {datetime.now().isoformat()}", logfile)
    log(f"{'='*60}", logfile)

    # Load data
    log("\nLoading test data...", logfile)

    kk_convos = get_conversations(KK_DB, limit=10)
    log(f"  Kevin Kelly: {len(kk_convos)} conversations", logfile)

    kk_facts = get_facts(KK_DB)
    log(f"  Kevin Kelly: {len(kk_facts)} existing facts (Haiku baseline)", logfile)

    franklin_facts = get_facts(FRANKLIN_DB)
    log(f"  Franklin: {len(franklin_facts)} existing facts", logfile)

    all_results = {
        "timestamp": TIMESTAMP,
        "extraction": [],
        "authoring": [],
        "compose": [],
        "full_pipeline": [],
    }

    # ── Phase 1: Extraction prompt optimization ──
    log(f"\n{'='*60}", logfile)
    log("PHASE 1: EXTRACTION PROMPT OPTIMIZATION", logfile)
    log(f"{'='*60}", logfile)

    prompts = [
        (EXTRACT_V1, "v1_baseline"),
        (EXTRACT_V2, "v2_constrained"),
        (EXTRACT_V3, "v3_chain_of_thought"),
    ]

    for model in EXTRACTION_MODELS:
        for prompt_template, prompt_name in prompts:
            result = run_extraction_test(model, kk_convos[:5], prompt_template, prompt_name, logfile)
            all_results["extraction"].append(result)
            log(f"  -> {model}/{prompt_name}: {result['total_facts']} facts, {result['avg_seconds']}s avg", logfile)

    # ── Phase 2: Authoring with optimized prompts ──
    log(f"\n{'='*60}", logfile)
    log("PHASE 2: AUTHORING (ALL 3 LAYERS)", logfile)
    log(f"{'='*60}", logfile)

    for model in AUTHORING_MODELS:
        log(f"\n  Model: {model}", logfile)

        # Test both anchor prompts
        for prompt, name in [(ANCHORS_PROMPT_V1, "anchors_v1"), (ANCHORS_PROMPT_V2, "anchors_v2")]:
            result = run_authoring_test(model, kk_facts, prompt, name, logfile, num_ctx=16384)
            all_results["authoring"].append(result)
            log(f"  -> {name}: {result['items_generated']} items, parse={result['parse_success']}, {result['elapsed']}s", logfile)

        # Core modes
        result = run_authoring_test(model, kk_facts, CORE_PROMPT, "core", logfile, num_ctx=16384)
        all_results["authoring"].append(result)
        log(f"  -> core: {result['items_generated']} items, parse={result['parse_success']}, {result['elapsed']}s", logfile)

        # Predictions
        result = run_authoring_test(model, kk_facts, PREDICTIONS_PROMPT, "predictions", logfile, num_ctx=16384)
        all_results["authoring"].append(result)
        log(f"  -> predictions: {result['items_generated']} items, parse={result['parse_success']}, {result['elapsed']}s", logfile)

    # ── Phase 3: Compose (brief generation) ──
    log(f"\n{'='*60}", logfile)
    log("PHASE 3: COMPOSE (BRIEF GENERATION)", logfile)
    log(f"{'='*60}", logfile)

    # Use the best authoring results for compose input
    # Find best anchors, core, predictions from Phase 2
    best_layers = {}
    for layer_type in ["anchors_v2", "core", "predictions"]:
        candidates = [r for r in all_results["authoring"] if r["layer"] == layer_type and r["parse_success"]]
        if candidates:
            best = max(candidates, key=lambda r: r["items_generated"])
            best_layers[layer_type] = best["items"]
            log(f"  Best {layer_type}: {best['model']} ({best['items_generated']} items)", logfile)

    if all(k in best_layers for k in ["anchors_v2", "core", "predictions"]):
        for model in COMPOSE_MODELS:
            result = run_compose_test(
                model,
                best_layers["anchors_v2"],
                best_layers["core"],
                best_layers["predictions"],
                logfile,
                num_ctx=16384,
            )
            all_results["compose"].append(result)
            log(f"  -> {model}: {result['word_count']} words, usable={result['usable']}, {result['elapsed']}s", logfile)
    else:
        log("  SKIPPED: No successful authoring to compose from.", logfile)

    # ── Phase 4: Full pipeline (best model, end-to-end) ──
    log(f"\n{'='*60}", logfile)
    log("PHASE 4: FULL PIPELINE END-TO-END", logfile)
    log(f"{'='*60}", logfile)

    # Run the best extraction model, then author, then compose — all local
    best_extract = max(
        all_results["extraction"],
        key=lambda r: r["total_facts"],
    )
    best_model = best_extract["model"]
    log(f"  Best extractor: {best_model} ({best_extract['total_facts']} facts)", logfile)

    # Extract on Franklin (different subject for validation)
    log(f"\n  Running full pipeline on Franklin with {best_model}...", logfile)
    franklin_convos = get_conversations(FRANKLIN_DB, limit=10)

    extract_result = run_extraction_test(best_model, franklin_convos[:10], EXTRACT_V2, "v2_constrained", logfile)

    # Collect extracted facts for authoring
    extracted_facts = []
    for detail in extract_result["details"]:
        for fact in detail.get("sample", []):
            extracted_facts.append({"fact_text": fact.get("object", ""), "predicate": fact.get("predicate", "")})

    if len(extracted_facts) >= 10:
        # Author all 3 layers
        best_author_model = "phi4:14b"  # likely best for authoring
        anchors = run_authoring_test(best_author_model, extracted_facts, ANCHORS_PROMPT_V2, "anchors", logfile, num_ctx=16384)
        core = run_authoring_test(best_author_model, extracted_facts, CORE_PROMPT, "core", logfile, num_ctx=16384)
        preds = run_authoring_test(best_author_model, extracted_facts, PREDICTIONS_PROMPT, "predictions", logfile, num_ctx=16384)

        # Compose
        if anchors["parse_success"] and core["parse_success"] and preds["parse_success"]:
            compose = run_compose_test(best_author_model, anchors["items"], core["items"], preds["items"], logfile, num_ctx=16384)
            all_results["full_pipeline"].append({
                "extract_model": best_model,
                "author_model": best_author_model,
                "facts_extracted": extract_result["total_facts"],
                "anchors": anchors["items_generated"],
                "core": core["items_generated"],
                "predictions": preds["items_generated"],
                "brief_words": compose["word_count"],
                "brief_usable": compose["usable"],
                "brief_preview": compose["brief"][:1000],
                "total_time": extract_result["avg_seconds"] * len(franklin_convos) + anchors["elapsed"] + core["elapsed"] + preds["elapsed"] + compose["elapsed"],
            })
            log(f"\n  FULL PIPELINE RESULT:", logfile)
            log(f"    Facts: {extract_result['total_facts']}", logfile)
            log(f"    Anchors: {anchors['items_generated']}", logfile)
            log(f"    Core: {core['items_generated']}", logfile)
            log(f"    Predictions: {preds['items_generated']}", logfile)
            log(f"    Brief: {compose['word_count']} words, usable={compose['usable']}", logfile)
        else:
            log("  Authoring failed — cannot compose.", logfile)
    else:
        log(f"  Only {len(extracted_facts)} facts extracted — not enough to author.", logfile)

    # ── Save results ──
    results_path = RESULTS_DIR / f"results_{TIMESTAMP}.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    log(f"\n{'='*60}", logfile)
    log("SUMMARY", logfile)
    log(f"{'='*60}", logfile)

    log("\nExtraction (facts per 5 convos):", logfile)
    for r in sorted(all_results["extraction"], key=lambda x: -x["total_facts"]):
        log(f"  {r['model']:20s} {r['prompt']:20s} {r['total_facts']:3d} facts  {r['avg_seconds']:5.1f}s", logfile)

    log("\nAuthoring:", logfile)
    for r in all_results["authoring"]:
        status = "OK" if r["parse_success"] else "FAIL"
        log(f"  {r['model']:20s} {r['layer']:20s} {r['items_generated']:2d} items  {status:4s}  {r['elapsed']:5.1f}s", logfile)

    log("\nCompose:", logfile)
    for r in all_results["compose"]:
        status = "OK" if r["usable"] else "FAIL"
        log(f"  {r['model']:20s} {r['word_count']:4d} words  {status:4s}  {r['elapsed']:5.1f}s", logfile)

    if all_results["full_pipeline"]:
        log("\nFull Pipeline:", logfile)
        for r in all_results["full_pipeline"]:
            log(f"  Extract: {r['extract_model']} ({r['facts_extracted']} facts)", logfile)
            log(f"  Author:  {r['author_model']} (A:{r['anchors']} C:{r['core']} P:{r['predictions']})", logfile)
            log(f"  Brief:   {r['brief_words']} words, usable={r['brief_usable']}", logfile)

    log(f"\nCompleted: {datetime.now().isoformat()}", logfile)
    log(f"Results: {results_path}", logfile)
    logfile.close()

    print(f"\nDone. Results at {results_path}")
    print(f"Log at {logpath}")


if __name__ == "__main__":
    main()
