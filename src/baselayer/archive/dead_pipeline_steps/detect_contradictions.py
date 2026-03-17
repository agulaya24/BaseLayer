"""
Contradiction Detection Pipeline — Phase 2 of Temporal Processing

Detects contradictions among state-facts using MiniLM similarity filtering
followed by Opus judgment in Claude Code sessions.

Pipeline (per TEMPORAL_PROCESSING_REVIEW.md, D-038):
  1. Load all active state-facts + embeddings from SQLite + ChromaDB
  2. Compute pairwise cosine similarity for state-facts
  3. Filter pairs above threshold (0.50) — candidate contradictions
  4. Export candidate pairs for Opus judgment
  5. Import Opus judgments and execute (confidence adjust, superseded_by, temporal_state)

Run: python detect_contradictions.py --scan          # Run MiniLM filtering, show stats
     python detect_contradictions.py --export        # Export candidate pairs for Opus judgment
     python detect_contradictions.py --import-opus FILE  # Import Opus judgments
     python detect_contradictions.py --stats         # Show current contradiction status
"""

import contextlib
import sys
import io
import json
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

from config import (
    PROJECT_ROOT, VECTORS_DIR,
    CONTRADICTION_SIMILARITY_THRESHOLD, EMBEDDING_MODEL,
    get_db,
)

EXPORT_DIR = PROJECT_ROOT / "data" / "contradictions"
BATCH_SIZE = 50  # Pairs per Opus batch


# ---------------------------------------------------------------------------
# Step 1: Load state-facts with embeddings
# ---------------------------------------------------------------------------

def load_state_facts(fact_class_filter='state'):
    """Load all active facts from SQLite and their embeddings from ChromaDB.

    Args:
        fact_class_filter: 'state' (default), 'all' (any fact_class), or specific class name.
    """
    import chromadb

    with contextlib.closing(get_db()) as conn:
        if fact_class_filter == 'all':
            rows = conn.execute("""
                SELECT id, fact_text, category, confidence, significance_score,
                       temporal_state, subject, created_at, fact_class, knowledge_tier
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND (knowledge_tier IS NULL OR knowledge_tier != 'context')
                ORDER BY created_at
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, fact_text, category, confidence, significance_score,
                       temporal_state, subject, created_at, fact_class, knowledge_tier
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND fact_class = ?
                  AND (knowledge_tier IS NULL OR knowledge_tier != 'context')
                ORDER BY created_at
            """, (fact_class_filter,)).fetchall()

        fact_map = {}
        for row in rows:
            fact_map[row[0]] = {
                "id": row[0],
                "text": row[1],
                "category": row[2] or "unknown",
                "confidence": row[3] or 0,
                "significance": row[4] or 0,
                "temporal_state": row[5] or "unknown",
                "subject": row[6] or "user",
                "created_at": row[7],
                "fact_class": row[8],
                "knowledge_tier": row[9] or "untiered",
            }

    # Get embeddings from ChromaDB
    client = chromadb.PersistentClient(path=str(VECTORS_DIR))
    try:
        collection = client.get_collection("memory_facts")
    except (ValueError, RuntimeError):
        print("ERROR: No memory_facts collection in ChromaDB.")
        return [], np.array([])

    result = collection.get(include=["embeddings"])
    chroma_ids = result["ids"]
    embeddings = result["embeddings"]

    # Match ChromaDB entries to our state-facts
    matched_facts = []
    matched_embeddings = []

    for i, cid in enumerate(chroma_ids):
        if cid in fact_map:
            matched_facts.append(fact_map[cid])
            matched_embeddings.append(embeddings[i])

    if matched_embeddings:
        emb_matrix = np.array(matched_embeddings, dtype=np.float32)
    else:
        emb_matrix = np.array([])

    print(f"  Active state-facts in SQLite: {len(fact_map)}")
    print(f"  State-facts with embeddings: {len(matched_facts)}")
    print(f"  State-facts without embeddings: {len(fact_map) - len(matched_facts)}")

    return matched_facts, emb_matrix


# ---------------------------------------------------------------------------
# Step 2: Compute pairwise similarity and filter candidates
# ---------------------------------------------------------------------------

def find_candidate_pairs(facts, embeddings, threshold):
    """Compute pairwise cosine similarity and return pairs above threshold."""
    n = len(facts)
    if n == 0:
        return []

    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # avoid division by zero
    normalized = embeddings / norms

    # Compute similarity matrix
    print(f"\n  Computing pairwise similarity for {n} state-facts...")
    similarity_matrix = np.dot(normalized, normalized.T)

    # Find pairs above threshold using vectorized extraction (upper triangle only)
    # np.where on the upper triangle is O(n²) in space but fast in C, avoiding slow Python loops
    tri_i, tri_j = np.triu_indices(n, k=1)
    sims = similarity_matrix[tri_i, tri_j]
    mask = sims >= threshold
    above_i = tri_i[mask]
    above_j = tri_j[mask]
    above_sims = sims[mask]

    candidates = []
    for idx in range(len(above_i)):
        i, j = int(above_i[idx]), int(above_j[idx])
        # Skip pairs about different subjects
        if facts[i]["subject"] != facts[j]["subject"]:
            continue
        candidates.append({
            "fact_a_id": facts[i]["id"],
            "fact_a_text": facts[i]["text"],
            "fact_a_category": facts[i]["category"],
            "fact_a_temporal": facts[i]["temporal_state"],
            "fact_a_created": facts[i]["created_at"],
            "fact_a_tier": facts[i].get("knowledge_tier", "untiered"),
            "fact_b_id": facts[j]["id"],
            "fact_b_text": facts[j]["text"],
            "fact_b_category": facts[j]["category"],
            "fact_b_temporal": facts[j]["temporal_state"],
            "fact_b_created": facts[j]["created_at"],
            "fact_b_tier": facts[j].get("knowledge_tier", "untiered"),
            "similarity": round(float(above_sims[idx]), 4),
        })

    return candidates


# ---------------------------------------------------------------------------
# Step 3: Scan — run MiniLM filtering and report
# ---------------------------------------------------------------------------

def run_scan(threshold=None, fact_class_filter='state'):
    """Run MiniLM similarity scan on facts, report candidate pairs."""
    if threshold is None:
        threshold = CONTRADICTION_SIMILARITY_THRESHOLD

    print(f"Contradiction Detection — MiniLM Similarity Scan")
    print(f"  Threshold: {threshold}")
    print(f"  Fact class filter: {fact_class_filter}")
    print()

    facts, embeddings = load_state_facts(fact_class_filter=fact_class_filter)

    if len(facts) == 0:
        print("No state-facts with embeddings found.")
        return []

    candidates = find_candidate_pairs(facts, embeddings, threshold)

    print(f"\n  Candidate pairs above {threshold}: {len(candidates)}")

    if candidates:
        # Distribution by similarity band
        bands = {"0.90+": 0, "0.80-0.89": 0, "0.70-0.79": 0, "0.60-0.69": 0, "0.50-0.59": 0}
        for c in candidates:
            s = c["similarity"]
            if s >= 0.90:
                bands["0.90+"] += 1
            elif s >= 0.80:
                bands["0.80-0.89"] += 1
            elif s >= 0.70:
                bands["0.70-0.79"] += 1
            elif s >= 0.60:
                bands["0.60-0.69"] += 1
            else:
                bands["0.50-0.59"] += 1

        print(f"\n  Similarity distribution:")
        for band, count in bands.items():
            bar = "#" * min(count, 80)
            print(f"    {band}: {count:>5}  {bar}")

        # Category distribution
        cat_counts = {}
        for c in candidates:
            cat_a = c["fact_a_category"]
            cat_b = c["fact_b_category"]
            key = f"{cat_a}" if cat_a == cat_b else f"{cat_a}/{cat_b}"
            cat_counts[key] = cat_counts.get(key, 0) + 1

        print(f"\n  Category distribution:")
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:15]:
            print(f"    {cat:<25} {count:>5}")

        # Token estimate for Opus judgment
        # ~200 tokens per pair (prompt + response) based on backfill data
        est_tokens = len(candidates) * 250
        print(f"\n  Estimated Opus token cost: ~{est_tokens:,} tokens ({len(candidates)} pairs x ~250 tokens/pair)")

        # Show top 10 highest-similarity pairs
        top = sorted(candidates, key=lambda x: -x["similarity"])[:10]
        print(f"\n  Top 10 highest-similarity pairs:")
        for i, c in enumerate(top):
            print(f"    {i+1}. [{c['similarity']:.3f}] {c['fact_a_category']}")
            print(f"       A: {c['fact_a_text'][:100]}")
            print(f"       B: {c['fact_b_text'][:100]}")
            print()

    return candidates


# ---------------------------------------------------------------------------
# Step 4: Export candidate pairs for Opus judgment
# ---------------------------------------------------------------------------

def export_for_opus(candidates=None, threshold=None):
    """Export candidate pairs for Opus judgment in batches."""
    if candidates is None:
        if threshold is None:
            threshold = CONTRADICTION_SIMILARITY_THRESHOLD
        print("Running scan to generate candidates...")
        facts, embeddings = load_state_facts()
        candidates = find_candidate_pairs(facts, embeddings, threshold)

    if not candidates:
        print("No candidate pairs to export.")
        return

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Sort by similarity descending (highest first = most likely contradictions)
    candidates.sort(key=lambda x: -x["similarity"])

    total = len(candidates)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(num_batches):
        start = i * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = candidates[start:end]

        outfile = EXPORT_DIR / f"contradiction_batch_{i}.json"
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)

    print(f"\nExported {total} candidate pairs in {num_batches} batches to {EXPORT_DIR}/")
    print(f"Each batch: ~{BATCH_SIZE} pairs for Opus judgment")
    return num_batches


# ---------------------------------------------------------------------------
# Step 5: Import Opus judgments and execute
# ---------------------------------------------------------------------------

def import_opus_judgments(filepath):
    """Import Opus contradiction judgments and execute database operations.

    Expected format: list of {
        "fact_a_id": "...",
        "fact_b_id": "...",
        "judgment": "contradiction" | "enrichment" | "coexistent" | "ambiguous",
        "reasoning": "...",        # optional
        "newer_fact": "a" | "b"    # required for contradictions — which fact is newer/current
    }
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = data.get("judgments", data.get("results", []))

    if not isinstance(data, list):
        print(f"ERROR: Expected a list, got {type(data)}")
        return

    VALID_JUDGMENTS = {"contradiction", "enrichment", "coexistent", "ambiguous"}

    with contextlib.closing(get_db()) as conn:
        stats = {"contradiction": 0, "enrichment": 0, "coexistent": 0, "ambiguous": 0,
                 "errors": 0, "tiers_applied": 0}

        with conn:
            for item in data:
                # Validate required keys exist and types are correct
                if not isinstance(item, dict):
                    stats["errors"] += 1
                    continue

                judgment = item.get("judgment", "").strip().lower()
                fact_a_id = item.get("fact_a_id")
                fact_b_id = item.get("fact_b_id")

                if not fact_a_id or not isinstance(fact_a_id, str):
                    stats["errors"] += 1
                    continue
                if not fact_b_id or not isinstance(fact_b_id, str):
                    stats["errors"] += 1
                    continue

                if judgment not in VALID_JUDGMENTS:
                    stats["errors"] += 1
                    continue

                stats[judgment] += 1

                # Apply Opus tier side-channel annotations if present
                for fid, tier_key in [(fact_a_id, "fact_a_tier"), (fact_b_id, "fact_b_tier")]:
                    tier = item.get(tier_key, "").strip().lower()
                    if tier in ("identity", "situational", "context"):
                        cur = conn.execute("""
                            UPDATE memory_facts SET knowledge_tier = ?, tiered_by = 'opus'
                            WHERE id = ? AND (knowledge_tier IS NULL OR knowledge_tier = 'untiered')
                        """, (tier, fid))
                        stats["tiers_applied"] += cur.rowcount

                if judgment == "contradiction":
                    newer = item.get("newer_fact", "b")  # default: b is newer
                    if newer == "a":
                        old_id, new_id = fact_b_id, fact_a_id
                    else:
                        old_id, new_id = fact_a_id, fact_b_id

                    # Supersede the older fact
                    conn.execute("""
                        UPDATE memory_facts
                        SET superseded_by = ?,
                            temporal_state = 'past',
                            confidence = MAX(confidence * 0.3, 0.1)
                        WHERE id = ? AND superseded_by IS NULL
                    """, (new_id, old_id))

                elif judgment == "ambiguous":
                    # Queue for probing (future: probe_queue table)
                    # For now, log it
                    pass

    print(f"\nImported judgments:")
    print(f"  Contradictions: {stats['contradiction']} (older facts superseded)")
    print(f"  Enrichments:    {stats['enrichment']} (no action needed)")
    print(f"  Coexistent:     {stats['coexistent']} (no action needed)")
    print(f"  Ambiguous:      {stats['ambiguous']} (probe candidates)")
    print(f"  Tiers applied:  {stats['tiers_applied']} (Opus side-channel, tiered_by=opus)")
    print(f"  Errors:         {stats['errors']}")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def show_stats():
    """Show current contradiction detection status."""
    with contextlib.closing(get_db()) as conn:
        # Fact class distribution
        rows = conn.execute("""
            SELECT fact_class, COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY fact_class ORDER BY COUNT(*) DESC
        """).fetchall()

        total = sum(r[1] for r in rows)
        print(f"Active Facts by Class ({total} total):")
        for fc, cnt in rows:
            pct = cnt / total * 100 if total > 0 else 0
            print(f"  {fc or 'NULL':<15} {cnt:>5} ({pct:5.1f}%)")

        # Superseded facts (contradictions resolved)
        superseded = conn.execute("""
            SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NOT NULL
        """).fetchone()[0]
        print(f"\nSuperseded facts (contradictions resolved): {superseded}")

        # Temporal state distribution for state-facts
        temporal = conn.execute("""
            SELECT temporal_state, COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL AND fact_class = 'state'
            GROUP BY temporal_state ORDER BY COUNT(*) DESC
        """).fetchall()

        if temporal:
            print(f"\nState-facts by temporal_state:")
            for ts, cnt in temporal:
                print(f"  {ts or 'NULL':<15} {cnt:>5}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Contradiction detection pipeline")
    parser.add_argument("--scan", action="store_true",
                        help="Run MiniLM similarity scan, show candidate pairs and stats")
    parser.add_argument("--threshold", type=float, default=None,
                        help=f"Override similarity threshold (default: {CONTRADICTION_SIMILARITY_THRESHOLD})")
    parser.add_argument("--export", action="store_true",
                        help="Export candidate pairs for Opus judgment")
    parser.add_argument("--import-opus", type=str, metavar="FILE",
                        help="Import Opus judgment results from JSON file")
    parser.add_argument("--stats", action="store_true",
                        help="Show contradiction detection status")
    parser.add_argument("--fact-class", type=str, default="state",
                        help="Fact class to scan: 'state' (default), 'all', or specific class name (e.g. 'unclassified')")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.scan:
        run_scan(threshold=args.threshold, fact_class_filter=args.fact_class)
    elif args.export:
        facts, embeddings = load_state_facts(fact_class_filter=args.fact_class)
        candidates = find_candidate_pairs(facts, embeddings,
                                          args.threshold or CONTRADICTION_SIMILARITY_THRESHOLD)
        print(f"\n  Total candidate pairs: {len(candidates)}")
        export_for_opus(candidates)
    elif args.import_opus:
        # Validate file path resolves within project data directory
        import_path = Path(args.import_opus).resolve()
        data_dir = (PROJECT_ROOT / "data").resolve()
        if not str(import_path).startswith(str(data_dir)):
            print(f"ERROR: File must be within project data directory: {data_dir}")
            return
        import_opus_judgments(args.import_opus)
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
