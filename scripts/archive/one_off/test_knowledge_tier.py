"""
Knowledge Tier Classification — Model Comparison Test

Tests 4 local LLMs on classifying facts into knowledge tiers (D-039):
  T1 (identity):    Facts about who the person IS — biography, relationships, values, patterns
  T2 (situational): Current mutable conditions — active projects, dispositions, domain states
  T3 (context):     Task/conversation artifacts — one-off tasks, product lookups, specific trades

Run: python test_knowledge_tier.py --sample     # Generate 200-fact sample
     python test_knowledge_tier.py --test        # Run all 4 models on sample
     python test_knowledge_tier.py --test --model qwen2.5:14b  # Run single model
     python test_knowledge_tier.py --results     # Compare model outputs
"""

import contextlib
import sys
import io
import sqlite3
import json
import argparse
import time
import requests
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import DATABASE_FILE, PROJECT_ROOT

SAMPLE_FILE = PROJECT_ROOT / "data" / "backfill" / "tier_test_sample.json"
RESULTS_DIR = PROJECT_ROOT / "data" / "backfill"
OLLAMA_URL = "http://localhost:11434/api/generate"

MODELS = [
    "qwen2.5:14b",
    "qwen3:14b",
    "phi4:14b",
    "gemma2:9b",
]

TIER_PROMPT_V1 = """You are classifying facts about a person into knowledge tiers for a memory system.

Each fact must be classified into exactly ONE tier:

**IDENTITY** — Facts about who this person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences, skills, formative experiences. These would appear in a 500-word biography. They are stable over months/years.
Examples:
- "Married to Jordan" → identity
- "Founded TechCo" → identity
- "Values discipline and consistency in trading" → identity
- "Has an project car" → identity
- "Tends to overtrade when emotional" → identity

**SITUATIONAL** — Current mutable conditions that are true NOW but may change. Active projects, ongoing dispositions, domain-specific states. These persist for weeks/months and are worth tracking for contradiction detection.
Examples:
- "Is building a personal AI memory system" → situational
- "Is bearish on tech sector" → situational
- "Currently improving trading discipline" → situational
- "Lives in Portland" → situational (could move)
- "Works at [company]" → situational

**CONTEXT** — Task or conversation artifacts. Things the person was doing in ONE specific conversation. One-off tasks, product lookups, specific trade positions, resume customizations, debugging sessions. These describe what happened in a conversation, not who the person is.
Examples:
- "Seeking to personalize resume for Demand.io" → context
- "Considering GDX LEAPS at $100-110 strike" → context
- "Converting a JSON file to CSV format" → context
- "Looking for coffee mats for their espresso machine" → context
- "Is following up with Anuj from SparkHQ" → context

Classify the following fact. Respond with ONLY the tier name: identity, situational, or context

Fact: {fact_text}
Category: {category}
Temporal state: {temporal_state}

Tier:"""

TIER_PROMPT = """You are classifying facts about a person into knowledge tiers for a memory system.

CRITICAL RULES before classifying:
1. If the fact is about someone OTHER than the primary user, classify as context.
2. Apply the "single conversation test": would this fact make sense to someone who never saw the conversation it came from? If NOT, it is context.
3. "The user was doing X in a conversation" is NOT the same as "the user is the kind of person who does X." Doing something once is context. Doing something as a pattern is identity.
4. When in doubt between situational and context, choose context.

**IDENTITY** — Who this person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences, proven skills, formative experiences. Would appear in a 500-word biography. Stable over months/years.
Examples:
- "Married to Jordan" → identity
- "Founded TechCo" → identity
- "Values discipline and consistency in trading" → identity
- "Has an project car" → identity
- "Tends to overtrade when emotional" → identity
- "Interested in intraday trading strategies" → identity (durable interest pattern)

**SITUATIONAL** — Current mutable conditions true NOW, persisting weeks/months. Active projects, ongoing dispositions, living situation, employment. Must be a DURABLE current state, not a one-off activity.
Examples:
- "Is building a personal AI memory system" → situational (multi-month project)
- "Is bearish on tech sector" → situational (market outlook persists)
- "Lives in Portland" → situational (could move)
- "Works at [company]" → situational
- "Is concerned about AI tool limitations" → situational (ongoing opinion)

**CONTEXT** — Conversation artifacts. One-off tasks, specific lookups, single-conversation activities, third-party observations, specific trade setups, report creation, product research. If it describes what happened in ONE conversation, it is context.
Examples:
- "Seeking to personalize resume for Demand.io" → context
- "Considering GDX LEAPS at $100-110 strike" → context
- "Converting a JSON file to CSV format" → context
- "Is using 200 SMA and 50 SMA in their trading" → context (specific indicator config)
- "Is preparing to discuss Sully.ai business model" → context (one-off meeting prep)
- "Is considering skills relevant to legacy modernization" → context (browsing a job listing)
- "User's parent understands trading risks" → context (third-party fact)
- "The cats drink a lot of water" → context (trivial observation)

Classify the following fact. Respond with ONLY the tier name: identity, situational, or context

Fact: {fact_text}
Category: {category}
Temporal state: {temporal_state}

Tier:"""


def generate_sample():
    """Generate a stratified sample of 200 facts for testing."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        # Get all active facts
        rows = conn.execute("""
            SELECT id, fact_text, category, temporal_state, fact_class,
                   significance_score, recurrence_count
            FROM memory_facts
            WHERE superseded_by IS NULL
            ORDER BY RANDOM()
        """).fetchall()

    # Sample across categories to get diversity
    sample = []
    category_counts = {}
    target = 200

    for row in rows:
        if len(sample) >= target:
            break
        cat = row[2] or "unknown"
        # Cap per category to ensure diversity
        cat_count = category_counts.get(cat, 0)
        max_per_cat = max(10, target // 8)
        if cat_count >= max_per_cat:
            continue

        sample.append({
            "id": row[0],
            "fact_text": row[1],
            "category": cat,
            "temporal_state": row[3] or "unknown",
            "fact_class": row[4] or "unclassified",
            "significance": row[5],
            "recurrence": row[6],
        })
        category_counts[cat] = cat_count + 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_FILE, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2, ensure_ascii=False)

    print(f"Generated sample of {len(sample)} facts -> {SAMPLE_FILE}")
    print(f"Category distribution:")
    for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<15} {cnt}")

    return sample


OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"

def call_ollama(model, prompt, timeout=120):
    """Call Ollama with a prompt, return response text."""
    try:
        options = {"temperature": 0.1, "num_predict": 20}

        # Qwen 3 uses thinking mode by default — use chat API with larger token budget
        if "qwen3" in model:
            options["num_predict"] = 500  # budget for internal thinking + answer
            resp = requests.post(OLLAMA_CHAT_URL, json={
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": options
            }, timeout=timeout)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "").strip().lower()
            # Strip thinking tags if present (Qwen 3 sometimes leaks them)
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()
            if "<think>" in content:
                content = content.split("<think>")[0].strip()
            return content
        else:
            resp = requests.post(OLLAMA_URL, json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": options
            }, timeout=timeout)
            resp.raise_for_status()
            return resp.json().get("response", "").strip().lower()
    except Exception as e:
        return f"ERROR: {e}"


def parse_tier(response):
    """Extract tier from model response."""
    resp = response.strip().lower()
    # Handle various response formats
    if resp.startswith("identity"):
        return "identity"
    if resp.startswith("situational"):
        return "situational"
    if resp.startswith("context"):
        return "context"
    # Check if contained anywhere
    if "identity" in resp and "situational" not in resp and "context" not in resp:
        return "identity"
    if "situational" in resp and "identity" not in resp and "context" not in resp:
        return "situational"
    if "context" in resp and "identity" not in resp and "situational" not in resp:
        return "context"
    return f"unparsed:{resp[:50]}"


def run_model_test(model, sample):
    """Run a single model on the sample and save results."""
    print(f"\n{'='*60}")
    print(f"Testing model: {model}")
    print(f"{'='*60}")

    results = []
    tier_counts = {"identity": 0, "situational": 0, "context": 0, "unparsed": 0}
    errors = 0
    start_time = time.time()

    for i, fact in enumerate(sample):
        prompt = TIER_PROMPT.format(
            fact_text=fact["fact_text"],
            category=fact["category"],
            temporal_state=fact["temporal_state"],
        )

        raw_response = call_ollama(model, prompt)

        if raw_response.startswith("ERROR:"):
            tier = "error"
            errors += 1
        else:
            tier = parse_tier(raw_response)

        if tier.startswith("unparsed"):
            tier_counts["unparsed"] += 1
        elif tier != "error":
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        results.append({
            "id": fact["id"],
            "fact_text": fact["fact_text"],
            "category": fact["category"],
            "raw_response": raw_response,
            "tier": tier,
        })

        if (i + 1) % 25 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (len(sample) - i - 1) / rate
            print(f"  {i+1}/{len(sample)} — {rate:.1f} facts/sec — ~{remaining:.0f}s remaining")

    elapsed = time.time() - start_time
    model_safe = model.replace(":", "_").replace(".", "_")
    outfile = RESULTS_DIR / f"tier_test_{model_safe}.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n  Results for {model}:")
    print(f"  Time: {elapsed:.1f}s ({len(sample)/elapsed:.1f} facts/sec)")
    print(f"  Identity:    {tier_counts['identity']:>4} ({tier_counts['identity']/len(sample)*100:.1f}%)")
    print(f"  Situational: {tier_counts['situational']:>4} ({tier_counts['situational']/len(sample)*100:.1f}%)")
    print(f"  Context:     {tier_counts['context']:>4} ({tier_counts['context']/len(sample)*100:.1f}%)")
    print(f"  Unparsed:    {tier_counts['unparsed']:>4}")
    print(f"  Errors:      {errors}")
    print(f"  Saved: {outfile}")

    return results


def compare_results():
    """Compare outputs from all models."""
    print(f"\n{'='*60}")
    print(f"Model Comparison — Knowledge Tier Classification")
    print(f"{'='*60}\n")

    # Load all results
    model_results = {}
    for model in MODELS:
        model_safe = model.replace(":", "_").replace(".", "_")
        filepath = RESULTS_DIR / f"tier_test_{model_safe}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                model_results[model] = json.load(f)

    if not model_results:
        print("No results found. Run --test first.")
        return

    # Tier distribution per model
    print("Tier Distribution:")
    print(f"  {'Model':<20} {'Identity':>10} {'Situational':>12} {'Context':>10} {'Unparsed':>10}")
    print(f"  {'-'*62}")

    for model, results in model_results.items():
        counts = {"identity": 0, "situational": 0, "context": 0, "unparsed": 0}
        for r in results:
            tier = r["tier"]
            if tier in counts:
                counts[tier] += 1
            elif tier.startswith("unparsed") or tier == "error":
                counts["unparsed"] += 1

        total = len(results)
        print(f"  {model:<20} {counts['identity']:>5} ({counts['identity']/total*100:4.0f}%)"
              f" {counts['situational']:>5} ({counts['situational']/total*100:4.0f}%)"
              f" {counts['context']:>5} ({counts['context']/total*100:4.0f}%)"
              f" {counts['unparsed']:>5}")

    # Agreement analysis
    if len(model_results) >= 2:
        models = list(model_results.keys())
        n = len(list(model_results.values())[0])

        print(f"\nPairwise Agreement:")
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                m1, m2 = models[i], models[j]
                agree = 0
                for k in range(n):
                    t1 = model_results[m1][k]["tier"]
                    t2 = model_results[m2][k]["tier"]
                    if t1 == t2:
                        agree += 1
                print(f"  {m1:<20} vs {m2:<20}: {agree}/{n} ({agree/n*100:.1f}%)")

    # Unanimous agreement
    if len(model_results) >= 2:
        models = list(model_results.keys())
        n = len(list(model_results.values())[0])
        unanimous = 0
        for k in range(n):
            tiers = set()
            for model in models:
                tiers.add(model_results[model][k]["tier"])
            if len(tiers) == 1:
                unanimous += 1
        print(f"\n  Unanimous agreement (all models): {unanimous}/{n} ({unanimous/n*100:.1f}%)")

    # Show disagreements (first 20)
    if len(model_results) >= 2:
        models = list(model_results.keys())
        n = len(list(model_results.values())[0])
        print(f"\nDisagreements (first 20):")
        shown = 0
        for k in range(n):
            tiers = {}
            for model in models:
                tiers[model] = model_results[model][k]["tier"]
            if len(set(tiers.values())) > 1:
                fact_text = list(model_results.values())[0][k]["fact_text"][:80]
                print(f"  [{k}] {fact_text}")
                for model, tier in tiers.items():
                    print(f"       {model:<20} → {tier}")
                shown += 1
                if shown >= 20:
                    break


def main():
    parser = argparse.ArgumentParser(description="Knowledge tier classification model comparison")
    parser.add_argument("--sample", action="store_true",
                        help="Generate 200-fact stratified sample")
    parser.add_argument("--test", action="store_true",
                        help="Run models on sample")
    parser.add_argument("--model", type=str, default=None,
                        help="Run only this model (e.g. qwen2.5:14b)")
    parser.add_argument("--results", action="store_true",
                        help="Compare model outputs")

    args = parser.parse_args()

    if args.sample:
        generate_sample()
    elif args.test:
        # Load sample
        if not SAMPLE_FILE.exists():
            print("No sample found. Run --sample first.")
            return
        with open(SAMPLE_FILE, "r", encoding="utf-8") as f:
            sample = json.load(f)
        print(f"Loaded {len(sample)} facts from sample")

        if args.model:
            run_model_test(args.model, sample)
        else:
            for model in MODELS:
                run_model_test(model, sample)
    elif args.results:
        compare_results()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
