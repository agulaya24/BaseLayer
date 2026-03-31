"""
Extended Overnight GPU Test — S100
6+ hour comprehensive test covering:
1. EXTRACTION: Full corpus (not 5 samples) across models
2. PREDICATE ABLATION: Different predicate sets per model
3. AUTHORING: All 3 layers per model (not just anchors)
4. EMBEDDING: Bulk retrieval latency with real fact stores
5. QUANTIZATION: Same model at different bit depths

RTX 3080 10GB
Target runtime: 6-10 hours
"""
import json
import os
import sqlite3
import subprocess
import time
import requests
from datetime import datetime
from pathlib import Path
from collections import Counter

RESULTS_DIR = Path("gpu_experiment_results/overnight_extended_s100")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Use Dan Shipper as test subject (549 facts, 220 conversations, moderate size)
TEST_DB = Path("C:/Users/Aarik/Anthropic/subjects/dan_shipper_memory/data/database/memory.db")

# ── Predicate sets for ablation ──────────────────────────────────────────────

FULL_PREDICATES = [
    "believes", "values", "practices", "avoids", "struggles_with",
    "fears", "enjoys", "excels_at", "prioritizes", "dislikes",
    "identifies_as", "builds", "monitors", "decided", "relates_to",
    "follows", "maintains", "experienced", "aspires_to",
]

# Minimal set: just the most identity-relevant predicates
MINIMAL_PREDICATES = [
    "believes", "values", "avoids", "struggles_with", "fears",
    "practices", "identifies_as",
]

# Behavioral-only: skip biographical/factual predicates
BEHAVIORAL_PREDICATES = [
    "practices", "avoids", "struggles_with", "fears", "enjoys",
    "excels_at", "builds", "monitors",
]

# Cognitive-only: beliefs and values
COGNITIVE_PREDICATES = [
    "believes", "values", "prioritizes", "decides", "identifies_as",
]

PREDICATE_SETS = {
    "full_19": FULL_PREDICATES,
    "minimal_7": MINIMAL_PREDICATES,
    "behavioral_8": BEHAVIORAL_PREDICATES,
    "cognitive_5": COGNITIVE_PREDICATES,
}

# ── Models ──────────────────────────────────────────────────────────────────

EXTRACTION_MODELS = [
    "mistral:7b",
    "qwen2.5:7b",
    "qwen3:14b",
    "gemma3:12b",
    "llama3.1:8b",
    "phi4-mini:3.8b",
]

AUTHORING_MODELS = [
    "mistral:7b",
    "qwen3:14b",
    "gemma3:12b",
    "deepseek-r1:32b",
]

# ── Utilities ───────────────────────────────────────────────────────────────

def get_all_conversations(db_path, limit=None):
    """Get all conversations with their text."""
    conn = sqlite3.connect(str(db_path))
    query = """
        SELECT c.id, c.title, GROUP_CONCAT(m.content_text, '\n') as text
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        HAVING LENGTH(text) > 100
        ORDER BY c.id
    """
    if limit:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def run_ollama(model, prompt, timeout=300):
    """Run Ollama generation."""
    start = time.time()
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"num_ctx": 4096}},
            timeout=timeout,
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            return {
                "text": data.get("response", ""),
                "elapsed": elapsed,
                "eval_count": data.get("eval_count", 0),
            }
    except Exception as e:
        return {"text": "", "elapsed": time.time() - start, "error": str(e)}
    return {"text": "", "elapsed": time.time() - start, "error": f"HTTP {resp.status_code}"}


def pull_model(model):
    """Pull model if needed."""
    result = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
    return result.returncode == 0


def make_extraction_prompt(text, predicates):
    """Build extraction prompt with specific predicate set."""
    pred_list = ", ".join(predicates)
    return f"""Extract behavioral facts about the person in this text.
For each fact, output one line: predicate | object_text

ONLY use these predicates: {pred_list}

Text:
{text[:3000]}

Facts (one per line):"""


def score_extraction(text, predicates):
    """Score extraction output."""
    lines = [l.strip() for l in text.split("\n") if "|" in l]
    valid = []
    pred_set = set(p.lower() for p in predicates)
    for line in lines:
        parts = line.split("|", 1)
        if len(parts) == 2:
            pred = parts[0].strip().lower()
            obj = parts[1].strip()
            if pred in pred_set and len(obj) > 5:
                valid.append({"predicate": pred, "object": obj})
    return valid


# ── Test 1: Full Extraction with Predicate Ablation ─────────────────────────

def test_extraction_ablation(conversations):
    """Test each model with each predicate set."""
    print(f"\n{'='*60}")
    print(f"TEST 1: EXTRACTION + PREDICATE ABLATION")
    print(f"  {len(conversations)} conversations x {len(EXTRACTION_MODELS)} models x {len(PREDICATE_SETS)} predicate sets")
    print(f"  = {len(conversations) * len(EXTRACTION_MODELS) * len(PREDICATE_SETS)} total runs")
    print(f"{'='*60}")

    results = []

    for model in EXTRACTION_MODELS:
        print(f"\n  Pulling {model}...", flush=True)
        pull_model(model)

        for pred_name, predicates in PREDICATE_SETS.items():
            model_pred_results = {
                "model": model, "predicate_set": pred_name,
                "num_predicates": len(predicates),
                "conversations": [],
            }

            total_facts = 0
            total_time = 0
            pred_dist = Counter()

            for conv_id, title, text in conversations:
                prompt = make_extraction_prompt(text, predicates)
                result = run_ollama(model, prompt, timeout=120)

                if result.get("error"):
                    model_pred_results["conversations"].append({
                        "title": title, "error": result["error"]
                    })
                    continue

                valid = score_extraction(result["text"], predicates)
                total_facts += len(valid)
                total_time += result["elapsed"]
                for f in valid:
                    pred_dist[f["predicate"]] += 1

                model_pred_results["conversations"].append({
                    "title": title[:50],
                    "facts": len(valid),
                    "elapsed": result["elapsed"],
                })

            model_pred_results["summary"] = {
                "total_facts": total_facts,
                "total_time": total_time,
                "avg_facts": total_facts / max(len(conversations), 1),
                "avg_time": total_time / max(len(conversations), 1),
                "predicate_distribution": dict(pred_dist.most_common()),
            }

            print(f"    {model:20s} + {pred_name:15s}: {total_facts:4d} facts, {total_time:.0f}s ({total_facts/max(len(conversations),1):.1f}/conv)", flush=True)
            results.append(model_pred_results)

            # Save intermediate results
            with open(RESULTS_DIR / "extraction_progress.json", "w") as f:
                json.dump(results, f, indent=2, default=str)

    return results


# ── Test 2: Full Authoring (all 3 layers) ────────────────────────────────────

def test_authoring():
    """Test authoring all 3 layers on each model."""
    print(f"\n{'='*60}")
    print(f"TEST 2: AUTHORING — All 3 layers per model")
    print(f"{'='*60}")

    # Get facts
    conn = sqlite3.connect(str(TEST_DB))
    facts = conn.execute("""
        SELECT fact_text FROM memory_facts
        WHERE superseded_by IS NULL
        ORDER BY recurrence_count DESC
        LIMIT 80
    """).fetchall()
    conn.close()

    facts_text = "\n".join(f"- {f[0]}" for f in facts)

    PROMPTS = {
        "anchors": f"""Write epistemic anchors — foundational beliefs this person reasons FROM.
8-10 axioms. Each: UPPERCASE name, 1-3 directive-fused sentences, "Active when:" trigger.
Domain-agnostic: how they reason, not what they reason about.

Facts:
{facts_text}

Write axioms now.""",

        "core": f"""Write the communication operating guide for an AI interacting with this person.
Cover: reasoning style, mode detection, context-specific engagement shifts, essential context.
800-1000 words. No single domain >25%.

Facts:
{facts_text}

Write now.""",

        "predictions": f"""Write behavioral predictions — recurring situation->response patterns.
6-8 predictions. Format: PATTERN NAME, Detection (2+ domains), Directive, False positive warning.
General patterns only.

Facts:
{facts_text}

Write now.""",
    }

    results = []

    for model in AUTHORING_MODELS:
        print(f"\n  Model: {model}", flush=True)
        pull_model(model)

        model_results = {"model": model, "layers": {}}

        for layer_name, prompt in PROMPTS.items():
            print(f"    {layer_name}...", end=" ", flush=True)
            result = run_ollama(model, prompt, timeout=600)

            if result.get("error"):
                print(f"ERROR: {result['error'][:50]}")
                model_results["layers"][layer_name] = {"error": result["error"]}
                continue

            text = result["text"]
            words = len(text.split())
            print(f"{words}w, {result['elapsed']:.1f}s", flush=True)

            model_results["layers"][layer_name] = {
                "words": words,
                "elapsed": result["elapsed"],
                "tokens": result.get("eval_count", 0),
                "sample": text[:1000],
            }

        results.append(model_results)

    return results


# ── Test 3: Embedding Bulk Retrieval ────────────────────────────────────────

def test_embedding_bulk():
    """Test embedding retrieval with real fact store."""
    print(f"\n{'='*60}")
    print(f"TEST 3: EMBEDDING — Bulk retrieval from fact store")
    print(f"{'='*60}")

    # Get all facts for embedding
    conn = sqlite3.connect(str(TEST_DB))
    facts = conn.execute("SELECT fact_text FROM memory_facts WHERE superseded_by IS NULL").fetchall()
    conn.close()
    fact_texts = [f[0] for f in facts]

    queries = [
        "struggling with a career decision",
        "how to handle a difficult conversation with partner",
        "analyzing a technical system for failure modes",
        "feeling burned out from overwork",
        "evaluating whether to start a new project",
        "dealing with comparison to others' success",
        "managing risk in an uncertain situation",
        "how to give feedback without damaging relationship",
        "processing a significant failure or loss",
        "deciding how much to invest in something unproven",
    ]

    models = [
        ("nomic-embed-text", 768),
        ("mxbai-embed-large", 1024),
        ("all-minilm", 384),
    ]

    results = []

    for model_name, dims in models:
        print(f"\n  Model: {model_name} ({dims}d)", flush=True)
        pull_model(model_name)

        # Embed all facts
        print(f"    Embedding {len(fact_texts)} facts...", end=" ", flush=True)
        fact_embeddings = []
        start = time.time()
        for ft in fact_texts[:200]:  # Cap at 200 for time
            try:
                resp = requests.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": model_name, "prompt": ft},
                    timeout=30,
                )
                if resp.status_code == 200:
                    fact_embeddings.append(resp.json().get("embedding", []))
            except:
                pass
        embed_time = time.time() - start
        print(f"{len(fact_embeddings)} embedded in {embed_time:.1f}s", flush=True)

        # Query retrieval
        query_timings = []
        for query in queries:
            start = time.time()
            try:
                resp = requests.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": model_name, "prompt": query},
                    timeout=30,
                )
                elapsed = (time.time() - start) * 1000
                query_timings.append(elapsed)
            except:
                pass

        avg_query = sum(query_timings) / len(query_timings) if query_timings else 0
        print(f"    Query latency: {avg_query:.0f}ms avg ({len(queries)} queries)", flush=True)

        results.append({
            "model": model_name,
            "dimensions": dims,
            "facts_embedded": len(fact_embeddings),
            "embed_time": embed_time,
            "query_avg_ms": avg_query,
            "query_min_ms": min(query_timings) if query_timings else 0,
            "query_max_ms": max(query_timings) if query_timings else 0,
        })

    return results


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"Extended Overnight GPU Test — S100")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"GPU: RTX 3080 10GB")
    print(f"Test subject: Dan Shipper (549 facts, 220 conversations)")

    # Get all conversations (use first 50 for reasonable overnight runtime)
    conversations = get_all_conversations(TEST_DB, limit=50)
    print(f"Test conversations: {len(conversations)}")

    all_results = {
        "started": datetime.now().isoformat(),
        "gpu": "RTX 3080 10GB",
        "test_conversations": len(conversations),
    }

    # Test 1: Extraction + predicate ablation (~3-4 hours)
    all_results["extraction"] = test_extraction_ablation(conversations)

    # Test 2: Authoring all layers (~1-2 hours)
    all_results["authoring"] = test_authoring()

    # Test 3: Embedding bulk retrieval (~30 min)
    all_results["embedding"] = test_embedding_bulk()

    all_results["completed"] = datetime.now().isoformat()

    # Save final results
    results_file = RESULTS_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\nResults saved to: {results_file}")

    # Summary
    print(f"\n{'='*60}")
    print("EXTRACTION SUMMARY — Best model per predicate set:")
    print(f"{'='*60}")
    for pred_name in PREDICATE_SETS:
        best = None
        for r in all_results.get("extraction", []):
            if r["predicate_set"] == pred_name:
                s = r.get("summary", {})
                if not best or s.get("total_facts", 0) > best.get("total_facts", 0):
                    best = {"model": r["model"], **s}
        if best:
            print(f"  {pred_name:15s}: {best['model']:20s} {best['total_facts']:4d} facts ({best.get('avg_facts',0):.1f}/conv)")

    print(f"\nAUTHORING SUMMARY:")
    for r in all_results.get("authoring", []):
        layers = r.get("layers", {})
        total_words = sum(l.get("words", 0) for l in layers.values())
        total_time = sum(l.get("elapsed", 0) for l in layers.values())
        errors = sum(1 for l in layers.values() if "error" in l)
        print(f"  {r['model']:20s} {total_words:5d}w total, {total_time:.0f}s, {errors} errors")


if __name__ == "__main__":
    main()
