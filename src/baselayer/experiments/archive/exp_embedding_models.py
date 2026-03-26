"""
Experiment 3: Embedding Model Comparison
=========================================
Question: Does a better embedding model improve AUDN dedup quality and fact retrieval?

Method:
  - Load existing Franklin facts from DB
  - Embed with 4 models: MiniLM-L6 (current), MiniLM-L12, mpnet-base, bge-small
  - For each model: compute pairwise similarities, measure dedup precision
  - Compare: similarity distributions, near-duplicate detection, clustering

Note: This is CPU-bound (no Ollama needed). Runs fast even without GPU for embeddings.
      sentence-transformers will auto-use GPU if available.
"""

import json
import sys
import os
import time
import sqlite3
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import save_results

MODELS_TO_TEST = [
    ("all-MiniLM-L6-v2", 384),      # Current production model
    ("all-MiniLM-L12-v2", 384),      # Larger MiniLM
    ("all-mpnet-base-v2", 768),      # MPNet (higher quality, larger)
    ("BAAI/bge-small-en-v1.5", 384), # BGE small
]


def load_franklin_facts(limit: int = 200) -> list[str]:
    """Load fact texts from Franklin DB."""
    db_path = os.environ.get(
        "EXPERIMENT_DB",
        str(Path(__file__).parent.parent.parent.parent / "subjects" / "franklin_memory" / "data" / "database" / "memory.db")
    )
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT fact_text FROM memory_facts WHERE superseded_by IS NULL ORDER BY created_at LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def compute_similarity_stats(embeddings: np.ndarray) -> dict:
    """Compute pairwise cosine similarity statistics."""
    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms

    # Pairwise cosine similarity (upper triangle only)
    sim_matrix = normalized @ normalized.T
    n = len(sim_matrix)
    upper_tri_indices = np.triu_indices(n, k=1)
    similarities = sim_matrix[upper_tri_indices]

    # Near-duplicates at various thresholds
    thresholds = [0.80, 0.85, 0.90, 0.95]
    near_dupes = {}
    for t in thresholds:
        count = int(np.sum(similarities >= t))
        near_dupes[f"pairs_above_{t}"] = count

    return {
        "mean_similarity": float(np.mean(similarities)),
        "median_similarity": float(np.median(similarities)),
        "std_similarity": float(np.std(similarities)),
        "min_similarity": float(np.min(similarities)),
        "max_similarity": float(np.max(similarities)),
        "near_duplicates": near_dupes,
        "total_pairs": len(similarities),
    }


def find_top_duplicates(facts: list[str], embeddings: np.ndarray, top_k: int = 10) -> list[dict]:
    """Find the most similar fact pairs."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    sim_matrix = normalized @ normalized.T

    n = len(sim_matrix)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((sim_matrix[i, j], i, j))

    pairs.sort(reverse=True)
    top_pairs = []
    for sim, i, j in pairs[:top_k]:
        top_pairs.append({
            "similarity": round(float(sim), 4),
            "fact_a": facts[i][:200],
            "fact_b": facts[j][:200],
        })
    return top_pairs


def main():
    print("=" * 60)
    print("EXPERIMENT 3: Embedding Model Comparison")
    print("=" * 60)

    facts = load_franklin_facts(limit=200)
    if not facts:
        print("ERROR: No facts found")
        return

    print(f"Loaded {len(facts)} Franklin facts")
    print()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed")
        print("  pip install sentence-transformers")
        return

    results = {}

    for model_name, expected_dim in MODELS_TO_TEST:
        print(f"--- {model_name} (dim={expected_dim}) ---")
        t0 = time.time()

        try:
            model = SentenceTransformer(model_name)
            embeddings = model.encode(facts, show_progress_bar=False, batch_size=32)
            embeddings = np.array(embeddings)

            load_time = time.time() - t0
            actual_dim = embeddings.shape[1]

            stats = compute_similarity_stats(embeddings)
            top_dupes = find_top_duplicates(facts, embeddings, top_k=5)

            result = {
                "model": model_name,
                "dimension": actual_dim,
                "facts_embedded": len(facts),
                "time_seconds": round(time.time() - t0, 1),
                "load_time_seconds": round(load_time, 1),
                "similarity_stats": stats,
                "top_similar_pairs": top_dupes,
            }
            results[model_name] = result

            print(f"  Dim: {actual_dim}, Time: {result['time_seconds']}s")
            print(f"  Mean sim: {stats['mean_similarity']:.3f}, "
                  f"Median: {stats['median_similarity']:.3f}")
            print(f"  Near-dupes (>0.90): {stats['near_duplicates']['pairs_above_0.9']}, "
                  f"(>0.85): {stats['near_duplicates']['pairs_above_0.85']}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results[model_name] = {"model": model_name, "error": str(e)}

        print()

    # Summary
    summary = {
        "experiment": "embedding_models",
        "question": "Does a better embedding model improve AUDN dedup quality?",
        "facts_tested": len(facts),
        "models_tested": len(MODELS_TO_TEST),
        "comparison": {},
    }

    print("=" * 60)
    print("SUMMARY")
    print(f"{'Model':<30} {'Dim':>4} {'MeanSim':>8} {'>0.85':>6} {'>0.90':>6} {'Time':>6}")
    print("-" * 68)
    for name, r in results.items():
        if "error" in r:
            print(f"{name:<30} ERROR: {r['error'][:40]}")
            continue
        s = r["similarity_stats"]
        print(f"{name:<30} {r['dimension']:>4} {s['mean_similarity']:>8.3f} "
              f"{s['near_duplicates']['pairs_above_0.85']:>6} "
              f"{s['near_duplicates']['pairs_above_0.9']:>6} "
              f"{r['time_seconds']:>5.1f}s")
        summary["comparison"][name] = {
            "dimension": r["dimension"],
            "mean_similarity": s["mean_similarity"],
            "near_dupes_85": s["near_duplicates"]["pairs_above_0.85"],
            "near_dupes_90": s["near_duplicates"]["pairs_above_0.9"],
            "time_seconds": r["time_seconds"],
        }
    print("=" * 60)

    summary["full_results"] = results
    save_results("embedding_models", summary)


if __name__ == "__main__":
    main()
