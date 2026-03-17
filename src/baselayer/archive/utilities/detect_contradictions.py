"""
Contradiction Detection — Simplified Pipeline (S81)

Finds contradictions and tensions in extracted facts using embedding similarity
+ Haiku classification. Each finding traces back to source conversations.

Pipeline integration:
  - Runs after extraction, before authoring
  - Feeds tensions into PREDICTIONS layer (false positive guards)
  - Results stored in contradictions table with full provenance

Usage:
  baselayer contradictions                    # Scan all facts, show results
  baselayer contradictions --save             # Scan and save to DB
  baselayer contradictions --show             # Show previously saved results
  baselayer contradictions --backend ollama   # Use local Qwen instead of Haiku

Design:
  1. Embed all active facts with sentence-transformers (no ChromaDB needed)
  2. Find candidate pairs: same/related predicates + cosine sim > threshold
  3. Classify with Haiku (or Qwen): CONTRADICTION, TENSION, CONSISTENT
  4. Store with provenance: source_conversation_id for both facts
"""

import contextlib
import json
import sqlite3
import sys
import os
import time
import argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    PROJECT_ROOT, DATABASE_FILE,
    EXTRACTION_BACKEND, EXTRACTION_API_MODEL,
    CONTRADICTION_SIMILARITY_THRESHOLD,
    get_db,
)


# Predicate pairs that are natural tension candidates
TENSION_PREDICATE_PAIRS = {
    ("believes", "avoids"), ("values", "dislikes"), ("practices", "avoids"),
    ("enjoys", "dislikes"), ("enjoys", "fears"), ("aspires_to", "fears"),
    ("maintains", "struggles_with"), ("prefers", "avoids"),
    ("loves", "hates"), ("values", "struggles_with"),
    ("prioritizes", "avoids"), ("believes", "struggles_with"),
    ("excels_at", "struggles_with"), ("practices", "fears"),
}


def _ensure_contradictions_table(conn):
    """Create contradictions table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contradictions (
            id TEXT PRIMARY KEY,
            fact_a_id TEXT NOT NULL,
            fact_b_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            reasoning TEXT,
            confidence REAL,
            similarity REAL,
            fact_a_text TEXT,
            fact_b_text TEXT,
            fact_a_source TEXT,
            fact_b_source TEXT,
            fact_a_predicate TEXT,
            fact_b_predicate TEXT,
            created_at REAL DEFAULT (unixepoch()),
            FOREIGN KEY (fact_a_id) REFERENCES memory_facts(id),
            FOREIGN KEY (fact_b_id) REFERENCES memory_facts(id)
        )
    """)
    conn.commit()


def load_facts(conn):
    """Load all active facts with their predicates and source info."""
    rows = conn.execute("""
        SELECT f.id, f.fact_text, f.predicate, f.object_text,
               f.source_conversation_id, f.confidence, f.category,
               c.title as source_title
        FROM memory_facts f
        LEFT JOIN conversations c ON f.source_conversation_id = c.id
        WHERE f.superseded_by IS NULL
        ORDER BY f.created_at
    """).fetchall()
    return [dict(r) for r in rows]


def embed_facts(facts):
    """Embed fact texts using sentence-transformers (on-the-fly, no ChromaDB)."""
    from api_client import get_embedding_model
    model = get_embedding_model()
    if model is None:
        raise ImportError("Could not load embedding model")

    texts = [f["fact_text"] for f in facts]
    embeddings = model.encode(texts, show_progress_bar=False, batch_size=64)
    return np.array(embeddings, dtype=np.float32)


def find_candidate_pairs(facts, embeddings, threshold=0.45):
    """Find fact pairs that might contradict using embedding similarity + predicate heuristics.

    Two-pass strategy (S81 threshold variation test):
      Pass 1 (cross-category): Different predicate categories, base threshold 0.45
      Pass 2 (tension pairs): Known tension predicate pairs, threshold 0.40
    This captures both high-similarity obvious tensions AND structurally
    interesting cross-category ones that pure similarity misses.
    """
    n = len(facts)
    if n == 0:
        return []

    tension_pair_threshold = 0.40  # Lower for known tension predicate pairs

    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    sim_matrix = normalized @ normalized.T

    # Extract upper triangle pairs above minimum threshold
    min_threshold = min(threshold, tension_pair_threshold)
    tri_i, tri_j = np.triu_indices(n, k=1)
    sims = sim_matrix[tri_i, tri_j]
    mask = sims >= min_threshold
    above_i = tri_i[mask]
    above_j = tri_j[mask]
    above_sims = sims[mask]

    candidates = []
    seen = set()

    for idx in range(len(above_i)):
        i, j = int(above_i[idx]), int(above_j[idx])
        fi, fj = facts[i], facts[j]
        sim = float(above_sims[idx])

        pred_a = fi.get("predicate", "")
        pred_b = fj.get("predicate", "")
        cat_a = fi.get("category", "")
        cat_b = fj.get("category", "")

        pred_pair = (pred_a, pred_b)
        is_tension_pair = pred_pair in TENSION_PREDICATE_PAIRS or pred_pair[::-1] in TENSION_PREDICATE_PAIRS
        is_same_pred = pred_a == pred_b and pred_a
        is_cross_category = cat_a != cat_b

        # Two-pass selection logic
        selected = False
        reason = ""

        # Pass 1: Tension predicate pairs at lower threshold
        if is_tension_pair and sim >= tension_pair_threshold:
            selected = True
            reason = "tension_pair"
        # Pass 2: Cross-category pairs at base threshold
        elif is_cross_category and sim >= threshold:
            selected = True
            reason = "cross_category"
        # Pass 3: Same predicate at base threshold (e.g., "believes X" vs "believes not-X")
        elif is_same_pred and sim >= threshold:
            selected = True
            reason = "same_predicate"
        # Pass 4: High similarity regardless of category
        elif sim >= 0.65:
            selected = True
            reason = "high_similarity"

        if not selected:
            continue

        pair_key = (fi["id"], fj["id"])
        if pair_key in seen:
            continue
        seen.add(pair_key)

        candidates.append({
            "fact_a": fi,
            "fact_b": fj,
            "similarity": round(sim, 4),
            "is_tension_pair": is_tension_pair,
            "is_same_predicate": is_same_pred,
            "is_cross_category": is_cross_category,
            "selection_reason": reason,
        })

    # Sort: tension pairs first, then cross-category, then by similarity
    candidates.sort(key=lambda x: (
        -x["is_tension_pair"],
        -x.get("is_cross_category", False),
        -x["similarity"],
    ))
    return candidates


def classify_pair_haiku(fact_a_text, fact_b_text, pred_a, pred_b):
    """Classify a fact pair using Haiku API via api_client.call_api."""
    from api_client import call_api

    prompt = f"""Classify the relationship between these two facts about the same person.

Fact A ({pred_a}): {fact_a_text}
Fact B ({pred_b}): {fact_b_text}

Categories:
- CONTRADICTION: Cannot both be true simultaneously. Direct logical conflict.
- TENSION: In apparent conflict but psychologically coherent. Shows internal complexity.
  Example: "believes climate change is urgent" + "drives gas-guzzler daily" = TENSION
- CONSISTENT: Compatible or complementary. No conflict.

Most pairs are CONSISTENT. True contradictions are rare. Tensions reveal identity complexity.
A person valuing X in one domain and enjoying non-X in another is normal, not a tension.

Return ONLY a JSON object:
{{"verdict": "CONTRADICTION|TENSION|CONSISTENT", "reasoning": "one sentence", "confidence": 0.0-1.0}}"""

    try:
        response = call_api(
            model=EXTRACTION_API_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
            caller="contradiction_classify",
        )
        text = response.content[0].text.strip()
        if text.startswith("{"):
            return json.loads(text)
        import re
        match = re.search(r'\{[^}]+\}', text)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, AttributeError, Exception) as e:
        pass

    return {"verdict": "CONSISTENT", "reasoning": "parse_error", "confidence": 0.0}


def classify_pair_ollama(fact_a_text, fact_b_text, pred_a, pred_b):
    """Classify a fact pair using local Qwen via Ollama."""
    import requests

    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

    prompt = f"""Classify the relationship between these two facts about the same person.

Fact A ({pred_a}): {fact_a_text}
Fact B ({pred_b}): {fact_b_text}

Categories:
- CONTRADICTION: Cannot both be true simultaneously.
- TENSION: In apparent conflict but psychologically coherent.
- CONSISTENT: Compatible or complementary.

Return ONLY JSON: {{"verdict": "CONTRADICTION|TENSION|CONSISTENT", "reasoning": "one sentence", "confidence": 0.0-1.0}}"""

    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "format": "json", "options": {"temperature": 0, "num_predict": 200}},
            timeout=120,
        )
        resp.raise_for_status()
        text = resp.json()["response"].strip()
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, requests.RequestException):
        return {"verdict": "CONSISTENT", "reasoning": "parse_error", "confidence": 0.0}


def run_scan(backend="anthropic", max_pairs=50, threshold=0.45, save=False):
    """Run full contradiction scan: embed → find candidates → classify → report."""
    with contextlib.closing(get_db()) as conn:
        _ensure_contradictions_table(conn)

        # Load and embed
        print("Loading facts...")
        facts = load_facts(conn)
        if len(facts) < 2:
            print(f"Only {len(facts)} facts — need at least 2 for contradiction detection.")
            return []

        print(f"  {len(facts)} active facts")
        print("Embedding facts...")
        embeddings = embed_facts(facts)
        print(f"  Embedded {len(embeddings)} facts ({embeddings.shape[1]}d)")

        # Find candidates
        print(f"Finding candidate pairs (threshold={threshold})...")
        candidates = find_candidate_pairs(facts, embeddings, threshold)
        print(f"  {len(candidates)} candidate pairs")
        if not candidates:
            print("No candidate pairs found above threshold.")
            return []

        # Classify top candidates
        classify_fn = classify_pair_ollama if backend == "ollama" else classify_pair_haiku
        classify_count = min(len(candidates), max_pairs)
        print(f"Classifying top {classify_count} pairs with {backend}...")

        results = []
        contradictions = 0
        tensions = 0

        for i, pair in enumerate(candidates[:classify_count]):
            fa = pair["fact_a"]
            fb = pair["fact_b"]
            pred_a = fa.get("predicate", "unknown")
            pred_b = fb.get("predicate", "unknown")

            result = classify_fn(fa["fact_text"], fb["fact_text"], pred_a, pred_b)
            verdict = result.get("verdict", "CONSISTENT")

            if verdict == "CONTRADICTION":
                contradictions += 1
                marker = "[!!]"
            elif verdict == "TENSION":
                tensions += 1
                marker = "[~~]"
            else:
                marker = "[OK]"

            sel_reason = pair.get("selection_reason", "?")
            print(f"  {i+1}/{classify_count} {marker} {verdict} "
                  f"(sim={pair['similarity']:.2f}, {sel_reason}) "
                  f"{pred_a}: {fa['fact_text'][:40]}... vs "
                  f"{pred_b}: {fb['fact_text'][:40]}...")

            finding = {
                "fact_a_id": fa["id"],
                "fact_b_id": fb["id"],
                "fact_a_text": fa["fact_text"],
                "fact_b_text": fb["fact_text"],
                "fact_a_predicate": pred_a,
                "fact_b_predicate": pred_b,
                "fact_a_source": fa.get("source_conversation_id"),
                "fact_b_source": fb.get("source_conversation_id"),
                "fact_a_source_title": fa.get("source_title", ""),
                "fact_b_source_title": fb.get("source_title", ""),
                "similarity": pair["similarity"],
                "selection_reason": pair.get("selection_reason", ""),
                "verdict": verdict,
                "reasoning": result.get("reasoning", ""),
                "confidence": result.get("confidence", 0.0),
            }
            results.append(finding)

            # Save to DB
            if save and verdict in ("CONTRADICTION", "TENSION"):
                import uuid
                conn.execute("""
                    INSERT OR REPLACE INTO contradictions
                    (id, fact_a_id, fact_b_id, verdict, reasoning, confidence,
                     similarity, fact_a_text, fact_b_text, fact_a_source, fact_b_source,
                     fact_a_predicate, fact_b_predicate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), fa["id"], fb["id"],
                    verdict, result.get("reasoning", ""),
                    result.get("confidence", 0.0), pair["similarity"],
                    fa["fact_text"], fb["fact_text"],
                    fa.get("source_conversation_id"), fb.get("source_conversation_id"),
                    pred_a, pred_b,
                ))
                conn.commit()

        # Summary
        print()
        print("=" * 60)
        print(f"RESULTS: {contradictions} contradictions, {tensions} tensions, "
              f"{classify_count - contradictions - tensions} consistent")
        print("=" * 60)

        if contradictions + tensions > 0:
            print()
            print("CONTRADICTIONS + TENSIONS:")
            for r in results:
                if r["verdict"] in ("CONTRADICTION", "TENSION"):
                    print(f"  [{r['verdict']}] (sim={r['similarity']:.2f}, conf={r['confidence']:.1f})")
                    print(f"    A ({r['fact_a_predicate']}): {r['fact_a_text'][:100]}")
                    print(f"      Source: {r['fact_a_source_title'][:60] if r['fact_a_source_title'] else r['fact_a_source'] or 'unknown'}")
                    print(f"    B ({r['fact_b_predicate']}): {r['fact_b_text'][:100]}")
                    print(f"      Source: {r['fact_b_source_title'][:60] if r['fact_b_source_title'] else r['fact_b_source'] or 'unknown'}")
                    print(f"    Reasoning: {r['reasoning']}")
                    print()

        if save:
            print(f"Saved {contradictions + tensions} findings to contradictions table.")

        return results


def show_saved(conn):
    """Show previously saved contradiction/tension findings."""
    _ensure_contradictions_table(conn)
    rows = conn.execute("""
        SELECT verdict, fact_a_text, fact_b_text, fact_a_predicate, fact_b_predicate,
               reasoning, confidence, similarity, fact_a_source, fact_b_source
        FROM contradictions
        ORDER BY
          CASE verdict WHEN 'CONTRADICTION' THEN 1 WHEN 'TENSION' THEN 2 ELSE 3 END,
          confidence DESC
    """).fetchall()

    if not rows:
        print("No saved contradictions/tensions. Run: baselayer contradictions --save")
        return

    print(f"Saved findings: {len(rows)}")
    for r in rows:
        r = dict(r)
        print(f"  [{r['verdict']}] (sim={r['similarity']:.2f}, conf={r['confidence']:.1f})")
        print(f"    A ({r['fact_a_predicate']}): {r['fact_a_text'][:100]}")
        print(f"    B ({r['fact_b_predicate']}): {r['fact_b_text'][:100]}")
        print(f"    Reasoning: {r['reasoning']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Contradiction Detection")
    parser.add_argument("--save", action="store_true", help="Save findings to database")
    parser.add_argument("--show", action="store_true", help="Show previously saved findings")
    parser.add_argument("--backend", choices=["anthropic", "ollama"], default=None,
                        help="LLM backend for classification")
    parser.add_argument("--max-pairs", type=int, default=50, help="Max pairs to classify")
    parser.add_argument("--threshold", type=float, default=0.45, help="Base similarity threshold (tension pairs use 0.40)")
    args = parser.parse_args()

    if args.show:
        with contextlib.closing(get_db()) as conn:
            show_saved(conn)
        return

    backend = args.backend or EXTRACTION_BACKEND
    run_scan(
        backend=backend,
        max_pairs=args.max_pairs,
        threshold=args.threshold,
        save=args.save,
    )


if __name__ == "__main__":
    main()
