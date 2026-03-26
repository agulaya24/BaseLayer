#!/usr/bin/env python3
"""
Overnight GPU experiments — Batch 2: remaining 5 models.
Run: python overnight_gpu_batch2.py

Tests gemma2:9b, mistral:7b, llama3.2:3b, phi4-mini:3.8b, sam860/LFM2:350m
on extraction, classification, and authoring using Franklin as test subject.
Sequential to avoid GPU throttling.
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

# Import shared functions from the original script
import sys
sys.path.insert(0, str(Path(__file__).parent))
from overnight_gpu_experiments import (
    get_franklin_conversations,
    get_franklin_facts as get_haiku_baseline_facts,
    run_extraction_experiment,
    run_classification_experiment,
    run_authoring_experiment,
)


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 60)
    print(f"GPU BATCH 2 — {timestamp}")
    print("=" * 60)
    print("Models: gemma2:9b, mistral:7b, llama3.2:3b, phi4-mini:3.8b, LFM2:350m")
    print(f"Subject: Franklin (public example)")
    print(f"Database: {FRANKLIN_DB}")

    print("\nLoading data...")
    conversations = get_franklin_conversations(5)
    print(f"  {len(conversations)} conversations loaded")

    baseline_facts = get_haiku_baseline_facts()
    print(f"  {len(baseline_facts)} baseline facts loaded")

    fact_pairs = []
    for i in range(min(30, len(baseline_facts) - 1)):
        fact_pairs.append({
            "fact_a": baseline_facts[i]["fact_text"],
            "fact_b": baseline_facts[i + 1]["fact_text"],
        })

    all_results = []

    # Models to test
    extraction_models = ["gemma2:9b", "mistral:7b", "llama3.2:3b", "phi4-mini:3.8b", "sam860/LFM2:350m"]
    classification_models = ["gemma2:9b", "mistral:7b", "llama3.2:3b"]
    authoring_models = ["gemma2:9b", "mistral:7b"]

    # Extraction
    for model in extraction_models:
        print(f"\n{'='*40}")
        print(f"EXTRACTION: {model}")
        print(f"{'='*40}")
        try:
            result = run_extraction_experiment(model, conversations)
            all_results.append(result)
            print(f"  Result: {result.get('total_facts', '?')} facts, {result.get('avg_seconds', '?')}s avg")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"model": model, "experiment": "extraction", "error": str(e)})

    # Classification
    for model in classification_models:
        print(f"\n{'='*40}")
        print(f"CLASSIFICATION: {model}")
        print(f"{'='*40}")
        try:
            result = run_classification_experiment(model, fact_pairs)
            all_results.append(result)
            v = result.get("verdicts", {})
            print(f"  Result: {v.get('TENSION',0)}T {v.get('CONTRADICTION',0)}C {v.get('CONSISTENT',0)}S")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"model": model, "experiment": "classification", "error": str(e)})

    # Authoring (only larger models)
    for model in authoring_models:
        print(f"\n{'='*40}")
        print(f"AUTHORING: {model}")
        print(f"{'='*40}")
        try:
            result = run_authoring_experiment(model, baseline_facts)
            all_results.append(result)
            print(f"  Result: {result.get('axioms_generated', '?')} axioms in {result.get('elapsed_seconds', '?')}s")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"model": model, "experiment": "authoring", "error": str(e)})

    # Save results
    output_file = RESULTS_DIR / f"batch2_results_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # Summary
    print("\n" + "=" * 60)
    print("BATCH 2 SUMMARY")
    print("=" * 60)
    for r in all_results:
        if "error" in r:
            print(f"  {r['model']} ({r['experiment']}): ERROR")
        elif r["experiment"] == "extraction":
            print(f"  {r['model']} (extraction): {r['total_facts']} facts, {r['avg_seconds']}s avg, {r['parse_success_rate']*100:.0f}% parse")
        elif r["experiment"] == "classification":
            v = r["verdicts"]
            print(f"  {r['model']} (classification): {v.get('TENSION',0)}T {v.get('CONTRADICTION',0)}C {v.get('CONSISTENT',0)}S {v.get('UNKNOWN',0)}?")
        elif r["experiment"] == "authoring":
            print(f"  {r['model']} (authoring): {r['axioms_generated']} axioms in {r['elapsed_seconds']}s")

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
