#!/usr/bin/env python3
"""
S98: Local model extraction quality comparison.

Extracts facts from 20 of Aarik's conversations using local models (Ollama)
and compares against Haiku API extraction. Measures: fact count, predicate
diversity, confidence distribution, and extraction quality.

Models tested:
- qwen2.5:32b (largest Qwen)
- deepseek-r1:32b (largest DeepSeek)
- gemma2:27b (largest Gemma)
- mistral:7b (best performer from S95 overnight test)
- Haiku API (baseline)

Usage:
    python runners/overnight_local_vs_api.py              # Run all models
    python runners/overnight_local_vs_api.py --only qwen  # Single model
    python runners/overnight_local_vs_api.py --count 10   # Fewer conversations
"""

import argparse
import json
import os
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DB_PATH = Path("C:/Users/Aarik/Anthropic/memory_system_v4/data/database/memory.db")
RESULTS_DIR = Path(__file__).parent.parent / "gpu_experiment_results" / "local_vs_api"

MODELS = {
    "qwen2.5:32b": {"backend": "ollama"},
    "qwen3:14b": {"backend": "ollama"},
    "gemma3:12b": {"backend": "ollama"},
    "deepseek-r1:32b": {"backend": "ollama"},
    "gemma2:27b": {"backend": "ollama"},
    "mistral:7b": {"backend": "ollama"},
    "phi4:14b": {"backend": "ollama"},
    "haiku": {"backend": "anthropic"},
}

# Prompt variations to test
PROMPT_VARIANTS = {
    "standard": None,  # Uses build_extraction_prompt() as-is
    "simplified": """Extract personal facts about the speaker from this conversation.
For each fact, provide: subject, predicate (one of: values, believes, practices, avoids, prefers, enjoys, dislikes, experiences, maintains, builds, studies, struggles_with), object (the specific claim), confidence (0-1), and category (one of: value, skill, interest, preference, habit, goal, biography, opinion, relationship, negative_trait, project).

Conversation title: {title}

{text}

Respond with ONLY valid JSON: {{"facts": [{{"subject": "user", "predicate": "...", "object": "...", "confidence": 0.8, "category": "..."}}]}}""",
}


def get_sample_conversations(count=20):
    """Get a representative sample of conversations with good message count."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT c.id, c.title, c.message_count, c.source
        FROM conversations c
        JOIN extraction_log e ON c.id = e.conversation_id
        WHERE c.message_count >= 5 AND c.message_count <= 30
        ORDER BY RANDOM()
        LIMIT ?
    """, (count,)).fetchall()

    conversations = []
    for r in rows:
        messages = conn.execute("""
            SELECT role, content_text as text FROM messages
            WHERE conversation_id = ? ORDER BY created_at
        """, (r["id"],)).fetchall()
        conversations.append({
            "id": r["id"],
            "title": r["title"],
            "message_count": r["message_count"],
            "source": r["source"],
            "messages": [{"role": m["role"], "text": m["text"] or ""} for m in messages],
        })
    conn.close()
    return conversations


def extract_with_model(conv, model_name, backend, prompt_variant="standard"):
    """Extract facts from a conversation using the specified model."""
    from baselayer.extract_facts import (
        build_extraction_prompt, EXTRACT_SCHEMA,
        validate_structured_response,
    )

    # Build conversation text
    conv_text = ""
    for msg in conv["messages"]:
        role = msg["role"].capitalize()
        text = msg["text"][:1500]
        conv_text += f"{role}: {text}\n"
        if len(conv_text) > 12000:
            break

    if prompt_variant == "simplified" and PROMPT_VARIANTS.get("simplified"):
        full_prompt = PROMPT_VARIANTS["simplified"].format(title=conv["title"], text=conv_text)
    else:
        prompt = build_extraction_prompt(conv["title"], conv_text)
        json_instruction = f"Respond with ONLY valid JSON matching this schema. No explanation, no markdown fences.\nSchema: {json.dumps(EXTRACT_SCHEMA, indent=2)}\n\n"
        full_prompt = json_instruction + prompt

    start = time.time()

    if backend == "ollama":
        import requests
        try:
            resp = requests.post("http://localhost:11434/api/generate", json={
                "model": model_name,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 2000},
            }, timeout=120)
            result_text = resp.json().get("response", "")
        except Exception as e:
            return {"error": str(e), "time": time.time() - start, "facts": []}

    elif backend == "anthropic":
        from baselayer.api_client import get_anthropic_client
        client = get_anthropic_client()
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                temperature=0.1,
                messages=[{"role": "user", "content": full_prompt}],
            )
            result_text = resp.content[0].text
        except Exception as e:
            return {"error": str(e), "time": time.time() - start, "facts": []}

    elapsed = time.time() - start

    # Parse JSON response
    try:
        # Strip markdown fences if present
        text = result_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text)
        facts = data.get("facts", [])
    except (json.JSONDecodeError, KeyError):
        return {"error": "JSON parse failed", "time": elapsed, "facts": [], "raw": result_text[:500]}

    # Validate
    validated = []
    for f in facts:
        v = validate_structured_response(f)
        if v:
            validated.append(v)

    return {"facts": validated, "time": elapsed, "raw_count": len(facts)}


def run_comparison(conversations, models_to_run):
    """Run extraction comparison across models x prompt variants."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = {}
    for model_name, config in models_to_run.items():
        for variant_name in PROMPT_VARIANTS:
            run_key = f"{model_name}|{variant_name}"
            print(f"\n{'='*60}")
            print(f"  Model: {model_name} | Prompt: {variant_name}")
            print(f"{'='*60}")

            model_results = []
            total_facts = 0
            total_time = 0
            errors = 0
            all_predicates = Counter()

            for i, conv in enumerate(conversations):
                print(f"  [{i+1}/{len(conversations)}] {conv['title'][:50]}...", end=" ", flush=True)
                result = extract_with_model(conv, model_name, config["backend"], variant_name)

                if result.get("error"):
                    print(f"ERROR: {result['error'][:50]}")
                    errors += 1
                else:
                    n_facts = len(result["facts"])
                    total_facts += n_facts
                    total_time += result["time"]
                    for f in result["facts"]:
                        all_predicates[f.get("predicate", "unknown")] += 1
                    print(f"{n_facts} facts ({result['time']:.1f}s)")

                model_results.append({
                    "conv_id": conv["id"],
                    "conv_title": conv["title"],
                    "facts": result["facts"],
                    "time": result["time"],
                    "error": result.get("error"),
                })

            results[run_key] = {
                "model": model_name,
                "prompt_variant": variant_name,
                "total_facts": total_facts,
                "total_time": total_time,
                "avg_facts_per_conv": total_facts / max(len(conversations) - errors, 1),
                "avg_time_per_conv": total_time / max(len(conversations) - errors, 1),
                "errors": errors,
                "predicate_distribution": dict(all_predicates.most_common(20)),
                "distinct_predicates": len(all_predicates),
                "conversations": model_results,
            }

            print(f"\n  Summary: {total_facts} facts, {total_time:.0f}s total, "
                  f"{total_facts / max(len(conversations) - errors, 1):.1f} avg/conv, "
                  f"{len(all_predicates)} distinct predicates, {errors} errors")

    # Save results
    output_file = RESULTS_DIR / f"comparison_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {output_file}")

    # Print comparison table
    print(f"\n{'='*60}")
    print(f"  COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'Model':25s} {'Facts':>6s} {'Avg/Conv':>8s} {'Time':>6s} {'Preds':>6s} {'Errors':>6s}")
    print("-" * 65)
    for model_name, r in sorted(results.items(), key=lambda x: x[1]["total_facts"], reverse=True):
        print(f"{model_name:25s} {r['total_facts']:6d} {r['avg_facts_per_conv']:8.1f} "
              f"{r['total_time']:6.0f}s {r['distinct_predicates']:6d} {r['errors']:6d}")


def main():
    parser = argparse.ArgumentParser(description="Local vs API extraction comparison")
    parser.add_argument("--only", type=str, help="Run only models matching this string")
    parser.add_argument("--count", type=int, default=20, help="Number of conversations (default: 20)")
    args = parser.parse_args()

    print(f"Loading {args.count} sample conversations from Aarik's DB...")
    conversations = get_sample_conversations(args.count)
    print(f"  Got {len(conversations)} conversations")

    models_to_run = MODELS
    if args.only:
        models_to_run = {k: v for k, v in MODELS.items() if args.only.lower() in k.lower()}
        print(f"  Running {len(models_to_run)} models matching '{args.only}'")

    if not models_to_run:
        print("No models matched.")
        return

    run_comparison(conversations, models_to_run)


if __name__ == "__main__":
    main()
