"""
Overnight GPU/CPU Test Battery — S100
Tests local model viability for extraction, authoring, and serving.

Run: python scripts/overnight_gpu_cpu_test.py
Estimated time: 6-10 hours
Estimated cost: $0 (all local) + ~$1 for API baseline comparisons

Tests:
1. EXTRACTION: 7 models x 3 quantization levels x 1 subject = 21 runs
2. AUTHORING: 5 models x 3 layers x 1 subject = 15 runs
3. SERVING: Embedding models for activation matching latency
4. CPU vs GPU: Same models on CPU-only to measure speed difference
"""
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path("gpu_experiment_results/overnight_s100")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Test subject: Dan Shipper (549 facts, moderate corpus, good baseline)
TEST_SUBJECT = Path(os.environ.get(
    "TEST_SUBJECT_DIR",
    "C:/Users/Aarik/Anthropic/subjects/dan_shipper_memory"
))
TEST_DB = TEST_SUBJECT / "data" / "database" / "memory.db"

# 5 sample conversations for extraction testing
SAMPLE_CONVOS = 5

# ── Models to test ──────────────────────────────────────────────────────────

EXTRACTION_MODELS = [
    # (model_name, quantization, description)
    ("mistral:7b", "default", "Best extractor from S83 overnight"),
    ("mistral:7b-q4_0", "q4", "4-bit quantized"),
    ("mistral:7b-q2_K", "q2", "2-bit quantized"),
    ("qwen2.5:7b", "default", "Current default"),
    ("qwen2.5:7b-q4_0", "q4", "4-bit quantized"),
    ("llama3.1:8b", "default", "Meta baseline"),
    ("llama3.1:8b-q4_0", "q4", "4-bit quantized"),
    ("phi4-mini:3.8b", "default", "Smallest model"),
    ("gemma2:9b", "default", "Google baseline"),
]

AUTHORING_MODELS = [
    ("mistral:7b", "default", "Best extractor — can it author?"),
    ("qwen2.5:14b", "default", "Larger model"),
    ("llama3.1:8b", "default", "Meta baseline"),
    ("deepseek-r1:14b", "default", "Reasoning model"),
    ("phi4:14b", "default", "Microsoft"),
]

EMBEDDING_MODELS = [
    ("nomic-embed-text", "Nomic — 137M params"),
    ("mxbai-embed-large", "Mixed Bread — 335M params"),
    ("all-minilm", "Sentence Transformers — 33M params"),
]


# ── Utilities ───────────────────────────────────────────────────────────────

def check_ollama():
    """Verify Ollama is running."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def pull_model(model_name):
    """Pull a model if not already available."""
    print(f"    Pulling {model_name}...", end=" ", flush=True)
    result = subprocess.run(
        ["ollama", "pull", model_name],
        capture_output=True, text=True, timeout=600
    )
    if result.returncode == 0:
        print("OK")
    else:
        print(f"FAIL: {result.stderr[:80]}")
    return result.returncode == 0


def get_sample_conversations(db_path, n=5):
    """Get N sample conversation texts for extraction testing."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT c.id, c.title, GROUP_CONCAT(m.content_text, '\n')
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY LENGTH(GROUP_CONCAT(m.content_text, '\n')) DESC
        LIMIT ?
    """, (n,)).fetchall()
    conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def run_ollama_generate(model, prompt, timeout=300):
    """Run a single Ollama generation and return text + timing."""
    import requests
    start = time.time()
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            return {
                "text": data.get("response", ""),
                "elapsed": elapsed,
                "eval_count": data.get("eval_count", 0),
                "eval_duration": data.get("eval_duration", 0),
                "prompt_eval_count": data.get("prompt_eval_count", 0),
            }
    except Exception as e:
        elapsed = time.time() - start
        return {"text": "", "elapsed": elapsed, "error": str(e)}
    return {"text": "", "elapsed": time.time() - start, "error": f"HTTP {resp.status_code}"}


# ── Test 1: Extraction ──────────────────────────────────────────────────────

def test_extraction(conversations):
    """Test extraction quality and speed across models."""
    print("\n" + "=" * 60)
    print("TEST 1: EXTRACTION — How well can local models extract facts?")
    print("=" * 60)

    # Simple extraction prompt (matches pipeline format)
    EXTRACT_PROMPT = """Extract behavioral facts from this text about a person.
For each fact, output one line in this format:
predicate | object_text

Use ONLY these predicates: believes, values, practices, avoids, struggles_with, fears, enjoys, excels_at, prioritizes, dislikes, identifies_as, builds, monitors

Text:
{text}

Facts (one per line, predicate | object):"""

    results = []

    for model, quant, desc in EXTRACTION_MODELS:
        print(f"\n  Model: {model} ({desc})")

        # Pull model
        if not pull_model(model):
            results.append({"model": model, "quant": quant, "error": "pull failed"})
            continue

        model_results = {"model": model, "quant": quant, "desc": desc, "conversations": []}

        for conv_id, title, text in conversations[:SAMPLE_CONVOS]:
            # Truncate long texts
            truncated = text[:3000] if text else ""
            prompt = EXTRACT_PROMPT.replace("{text}", truncated)

            print(f"    '{title[:40]}...' ", end="", flush=True)
            result = run_ollama_generate(model, prompt, timeout=300)

            if result.get("error"):
                print(f"ERROR: {result['error'][:50]}")
                model_results["conversations"].append({
                    "title": title, "error": result["error"],
                })
                continue

            # Count extracted facts
            lines = [l.strip() for l in result["text"].split("\n") if "|" in l]
            valid_predicates = {"believes", "values", "practices", "avoids", "struggles_with",
                                "fears", "enjoys", "excels_at", "prioritizes", "dislikes",
                                "identifies_as", "builds", "monitors"}
            valid_facts = []
            for line in lines:
                parts = line.split("|", 1)
                if len(parts) == 2 and parts[0].strip().lower() in valid_predicates:
                    valid_facts.append({"predicate": parts[0].strip(), "object": parts[1].strip()})

            print(f"{len(valid_facts)} facts, {result['elapsed']:.1f}s")
            model_results["conversations"].append({
                "title": title,
                "facts_extracted": len(valid_facts),
                "facts": valid_facts[:10],  # Store sample
                "total_lines": len(lines),
                "elapsed": result["elapsed"],
                "tokens": result.get("eval_count", 0),
            })

        # Summary for this model
        total_facts = sum(c.get("facts_extracted", 0) for c in model_results["conversations"])
        total_time = sum(c.get("elapsed", 0) for c in model_results["conversations"])
        model_results["summary"] = {
            "total_facts": total_facts,
            "total_time": total_time,
            "avg_facts_per_conv": total_facts / max(len(model_results["conversations"]), 1),
            "avg_time_per_conv": total_time / max(len(model_results["conversations"]), 1),
        }
        print(f"    TOTAL: {total_facts} facts in {total_time:.1f}s")
        results.append(model_results)

    return results


# ── Test 2: Authoring ───────────────────────────────────────────────────────

def test_authoring():
    """Test if local models can author identity layers."""
    print("\n" + "=" * 60)
    print("TEST 2: AUTHORING — Can local models write identity layers?")
    print("=" * 60)

    # Get a sample of facts from the test subject
    conn = sqlite3.connect(str(TEST_DB))
    facts = conn.execute("""
        SELECT fact_text FROM memory_facts
        WHERE superseded_by IS NULL
        ORDER BY recurrence_count DESC
        LIMIT 50
    """).fetchall()
    conn.close()

    facts_text = "\n".join(f"- {f[0]}" for f in facts)

    AUTHOR_PROMPT = """You are authoring epistemic anchors for a person's identity model.
These are axioms — beliefs this person reasons FROM, not ABOUT.

For each axiom:
- Name in 1-2 UPPERCASE words
- 1-3 sentences fusing description with directive
- "Active when:" trigger

Write 6-8 axioms. Domain-agnostic: how they reason, not what they reason about.

Facts:
{facts}

Write the axioms now.""".replace("{facts}", facts_text)

    results = []

    for model, quant, desc in AUTHORING_MODELS:
        print(f"\n  Model: {model} ({desc})")
        if not pull_model(model):
            results.append({"model": model, "error": "pull failed"})
            continue

        print(f"    Authoring anchors...", end=" ", flush=True)
        result = run_ollama_generate(model, AUTHOR_PROMPT, timeout=600)

        if result.get("error"):
            print(f"ERROR: {result['error'][:50]}")
            results.append({"model": model, "error": result["error"]})
            continue

        # Check quality
        text = result["text"]
        words = len(text.split())
        has_axioms = len([l for l in text.split("\n") if "ACTIVE WHEN" in l.upper() or "Active when" in l])
        has_uppercase = len([l for l in text.split("\n") if any(w.isupper() and len(w) > 2 for w in l.split())])

        print(f"{words}w, {has_axioms} triggers, {result['elapsed']:.1f}s")
        results.append({
            "model": model, "desc": desc,
            "words": words,
            "axiom_triggers": has_axioms,
            "uppercase_names": has_uppercase,
            "elapsed": result["elapsed"],
            "sample": text[:500],
        })

    return results


# ── Test 3: Embedding / Serving ─────────────────────────────────────────────

def test_embedding():
    """Test embedding models for activation matching speed."""
    print("\n" + "=" * 60)
    print("TEST 3: EMBEDDING — Activation matching latency")
    print("=" * 60)

    test_queries = [
        "I'm struggling with a decision about my career",
        "Can you help me analyze this market data?",
        "I had a fight with my partner about our finances",
        "What's the best approach to build this feature?",
        "I'm feeling burned out and don't know what to do",
    ]

    results = []

    for model, desc in EMBEDDING_MODELS:
        print(f"\n  Model: {model} ({desc})")
        if not pull_model(model):
            results.append({"model": model, "error": "pull failed"})
            continue

        import requests
        timings = []
        for query in test_queries:
            start = time.time()
            try:
                resp = requests.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": model, "prompt": query},
                    timeout=30,
                )
                elapsed = (time.time() - start) * 1000  # ms
                if resp.status_code == 200:
                    dims = len(resp.json().get("embedding", []))
                    timings.append(elapsed)
                    print(f"    {query[:40]}... {elapsed:.0f}ms ({dims}d)")
            except Exception as e:
                print(f"    ERROR: {e}")

        if timings:
            results.append({
                "model": model, "desc": desc,
                "avg_ms": sum(timings) / len(timings),
                "min_ms": min(timings),
                "max_ms": max(timings),
                "dimensions": dims,
            })

    return results


# ── Test 4: CPU vs GPU ──────────────────────────────────────────────────────

def test_cpu_vs_gpu():
    """Compare CPU-only vs GPU inference speed."""
    print("\n" + "=" * 60)
    print("TEST 4: CPU vs GPU — Speed comparison")
    print("=" * 60)

    # Use a single model and single prompt
    model = "mistral:7b"
    prompt = "Extract 5 behavioral facts from this text about a person who values honesty, struggles with procrastination, and believes in continuous learning. They practice daily journaling and avoid confrontation.\n\nFacts:"

    results = {}

    # GPU run (default)
    print(f"\n  GPU ({model})...", end=" ", flush=True)
    gpu_result = run_ollama_generate(model, prompt, timeout=120)
    if not gpu_result.get("error"):
        print(f"{gpu_result['elapsed']:.1f}s, {gpu_result.get('eval_count', 0)} tokens")
        results["gpu"] = gpu_result
    else:
        print(f"ERROR: {gpu_result.get('error', '')[:50]}")

    # CPU run — set CUDA_VISIBLE_DEVICES="" to force CPU
    print(f"  CPU ({model})...", end=" ", flush=True)
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""
    try:
        # Need to use ollama with CPU-only — this depends on ollama config
        # For now, just note that CPU testing requires ollama restart with no GPU
        print("SKIP (requires ollama restart with CUDA_VISIBLE_DEVICES='')")
        results["cpu"] = {"note": "Requires ollama restart without GPU access"}
    except Exception as e:
        print(f"ERROR: {e}")

    return results


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"Overnight GPU/CPU Test Battery — S100")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Test subject: {TEST_SUBJECT.name}")
    print(f"Results dir: {RESULTS_DIR}")

    if not check_ollama():
        print("ERROR: Ollama is not running. Start with: ollama serve")
        return

    # Get sample conversations
    conversations = get_sample_conversations(TEST_DB, SAMPLE_CONVOS)
    print(f"Sample conversations: {len(conversations)}")

    all_results = {
        "started": datetime.now().isoformat(),
        "test_subject": str(TEST_SUBJECT),
        "sample_conversations": len(conversations),
    }

    # Run tests
    all_results["extraction"] = test_extraction(conversations)
    all_results["authoring"] = test_authoring()
    all_results["embedding"] = test_embedding()
    all_results["cpu_vs_gpu"] = test_cpu_vs_gpu()

    all_results["completed"] = datetime.now().isoformat()

    # Save results
    results_file = RESULTS_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved to: {results_file}")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    print("\nExtraction (facts per conversation, time):")
    for r in all_results.get("extraction", []):
        if "summary" in r:
            s = r["summary"]
            print(f"  {r['model']:25s} {s['avg_facts_per_conv']:.1f} facts/conv  {s['avg_time_per_conv']:.1f}s/conv")

    print("\nAuthoring (quality indicators):")
    for r in all_results.get("authoring", []):
        if "words" in r:
            print(f"  {r['model']:25s} {r['words']}w  {r['axiom_triggers']} triggers  {r['elapsed']:.1f}s")

    print("\nEmbedding (latency):")
    for r in all_results.get("embedding", []):
        if "avg_ms" in r:
            print(f"  {r['model']:25s} {r['avg_ms']:.0f}ms avg  ({r['dimensions']}d)")


if __name__ == "__main__":
    main()
