"""
Phase 4: Fact Deduplication & Merge Pass

Finds semantically similar facts and merges them by keeping the best
version and superseding the rest.

Strategy:
1. Load all active facts + their embeddings from ChromaDB
2. For each fact, find others with cosine similarity > threshold
3. Group into clusters of near-duplicates
4. For each cluster, keep the "best" fact (highest confidence, best category)
5. Supersede the rest, pointing them to the survivor

Run: python dedup_facts.py              # Preview mode (no changes)
     python dedup_facts.py --apply      # Actually merge duplicates
     python dedup_facts.py --threshold 0.92  # Adjust similarity cutoff
"""

import contextlib
import sys
import io
import sqlite3
import time
import argparse
import numpy as np
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import DATABASE_FILE, VECTORS_DIR

# Default threshold — 0.92 is conservative (very similar facts only)
DEFAULT_THRESHOLD = 0.92

# Category quality ranking (prefer more specific categories)
CATEGORY_RANK = {
    "biography": 10,
    "relationship": 9,
    "skill": 8,
    "habit": 8,
    "negative_trait": 8,
    "preference": 7,
    "value": 7,
    "opinion": 7,
    "goal": 6,
    "interest": 5,
    "project": 4,
    "unknown": 0,
}


def load_facts_with_embeddings(conn):
    """Load all active facts and their embeddings from ChromaDB."""
    import chromadb

    # Get active facts from SQLite
    facts = conn.execute("""
        SELECT id, fact_text, category, confidence, significance_score,
               source_conversation_id, subject, temporal_state
        FROM memory_facts
        WHERE superseded_by IS NULL
          AND source != 'user_correction'
        ORDER BY created_at
    """).fetchall()

    fact_map = {}
    for row in facts:
        fact_map[row[0]] = {
            "id": row[0],
            "text": row[1],
            "category": row[2],
            "confidence": row[3] or 0,
            "significance": row[4] or 0,
            "source_conv": row[5],
            "subject": row[6] or "user",
            "temporal": row[7] or "unknown",
        }

    # Get embeddings from ChromaDB
    client = chromadb.PersistentClient(path=str(VECTORS_DIR))
    try:
        collection = client.get_collection("memory_facts")
    except Exception:
        print("ERROR: No memory_facts collection in ChromaDB.")
        return {}, np.array([]), []

    # Get all embeddings
    result = collection.get(include=["embeddings"])
    chroma_ids = result["ids"]
    embeddings = result["embeddings"]

    # Match ChromaDB entries to our active facts
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

    print(f"  Active facts in SQLite: {len(fact_map)}")
    print(f"  Facts with embeddings: {len(matched_facts)}")
    print(f"  Facts without embeddings (will skip): {len(fact_map) - len(matched_facts)}")

    return fact_map, emb_matrix, matched_facts


def should_merge(fact_a, fact_b):
    """Extra checks beyond embedding similarity to prevent bad merges."""
    # Don't merge facts about different subjects
    if fact_a["subject"] != fact_b["subject"]:
        return False

    # Don't merge current vs past facts
    ta = fact_a.get("temporal", "unknown")
    tb = fact_b.get("temporal", "unknown")
    if ta != tb and ta != "unknown" and tb != "unknown":
        return False

    return True


def find_duplicate_clusters(facts, embeddings, threshold):
    """Find clusters of semantically similar facts."""
    n = len(facts)
    if n == 0:
        return []

    # Normalize embeddings for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero
    normed = embeddings / norms

    # Find pairs above threshold using batched matrix multiplication
    # Process in chunks to avoid memory issues with 4500x4500 matrix
    CHUNK = 500
    merged = set()  # Track which facts are already in a cluster
    clusters = []

    print(f"\n  Computing similarity ({n} facts, threshold={threshold})...")

    for start in range(0, n, CHUNK):
        end = min(start + CHUNK, n)
        # Similarity of this chunk against ALL facts
        sim_block = normed[start:end] @ normed.T  # shape: (chunk_size, n)

        for local_i in range(end - start):
            global_i = start + local_i
            if global_i in merged:
                continue

            # Find all facts similar to this one
            sims = sim_block[local_i]
            similar_indices = np.where(sims > threshold)[0]

            # Filter out self, already-merged, and those that fail merge checks
            similar_indices = [j for j in similar_indices
                               if j != global_i and j not in merged
                               and should_merge(facts[global_i], facts[j])]

            if not similar_indices:
                continue

            # Build cluster: this fact + all similar ones
            cluster_indices = [global_i] + similar_indices
            cluster = [facts[idx] for idx in cluster_indices]
            similarities = [float(sims[j]) for j in similar_indices]

            clusters.append({
                "facts": cluster,
                "similarities": similarities,
                "indices": cluster_indices,
            })

            # Mark all as merged so they don't form new clusters
            for idx in cluster_indices:
                merged.add(idx)

        if end % 1000 == 0 or end == n:
            print(f"    Processed {end}/{n} facts, {len(clusters)} clusters found")

    return clusters


def pick_survivor(cluster_facts):
    """Pick the best fact to keep from a cluster. Returns (survivor, victims)."""
    def score(fact):
        cat_score = CATEGORY_RANK.get(fact["category"], 3)
        conf_score = fact["confidence"] * 10
        sig_score = fact["significance"]
        # Prefer shorter, more specific facts (less filler)
        length_penalty = max(0, (len(fact["text"]) - 80) / 200)
        return cat_score + conf_score + sig_score - length_penalty

    ranked = sorted(cluster_facts, key=score, reverse=True)
    return ranked[0], ranked[1:]


def preview_clusters(clusters, max_show=30):
    """Show duplicate clusters for review."""
    print(f"\n{'='*60}")
    print(f"Found {len(clusters)} duplicate clusters")
    total_victims = sum(len(c["facts"]) - 1 for c in clusters)
    print(f"Total facts to supersede: {total_victims}")
    print(f"{'='*60}")

    # Sort by cluster size (biggest first)
    sorted_clusters = sorted(clusters, key=lambda c: len(c["facts"]), reverse=True)

    for i, cluster in enumerate(sorted_clusters[:max_show]):
        survivor, victims = pick_survivor(cluster["facts"])
        print(f"\n--- Cluster {i+1} ({len(cluster['facts'])} facts) ---")
        print(f"  KEEP: [{survivor['category']:<14} {survivor['confidence']:.2f}] {survivor['text'][:90]}")
        for v in victims:
            print(f"  DROP: [{v['category']:<14} {v['confidence']:.2f}] {v['text'][:90]}")

    if len(sorted_clusters) > max_show:
        remaining = len(sorted_clusters) - max_show
        print(f"\n  ... and {remaining} more clusters")


def apply_merges(conn, clusters):
    """Actually supersede duplicate facts."""
    total_merged = 0

    for cluster in clusters:
        survivor, victims = pick_survivor(cluster["facts"])

        for victim in victims:
            conn.execute("""
                UPDATE memory_facts
                SET superseded_by = ?, updated_at = ?
                WHERE id = ? AND superseded_by IS NULL
            """, (survivor["id"], time.time(), victim["id"]))
            total_merged += 1

    conn.commit()
    return total_merged


def main():
    parser = argparse.ArgumentParser(description="Deduplicate semantically similar facts")
    parser.add_argument("--apply", action="store_true",
                        help="Actually merge duplicates (default is preview only)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Cosine similarity threshold (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--show", type=int, default=30,
                        help="Number of clusters to show in preview")

    args = parser.parse_args()

    print("=" * 60)
    print("Fact Deduplication & Merge Pass")
    print("=" * 60)

    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        # Load facts + embeddings
        print("\nLoading facts and embeddings...")
        fact_map, embeddings, facts = load_facts_with_embeddings(conn)

        if len(facts) == 0:
            print("No facts with embeddings found.")
            return

        # Find clusters
        start_time = time.time()
        clusters = find_duplicate_clusters(facts, embeddings, args.threshold)
        elapsed = time.time() - start_time
        print(f"  Clustering done in {elapsed:.1f}s")

        if not clusters:
            print("\nNo duplicate clusters found at this threshold.")
            return

        # Preview
        preview_clusters(clusters, max_show=args.show)

        if args.apply:
            print(f"\n{'='*60}")
            print("APPLYING MERGES...")
            merged = apply_merges(conn, clusters)
            remaining = conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchone()[0]
            print(f"Superseded {merged} duplicate facts")
            print(f"Active facts remaining: {remaining}")
        else:
            total_victims = sum(len(c["facts"]) - 1 for c in clusters)
            print(f"\n{'='*60}")
            print(f"PREVIEW MODE — no changes made")
            print(f"Run with --apply to supersede {total_victims} duplicate facts")
            print(f"Adjust threshold with --threshold (higher = stricter, fewer merges)")


if __name__ == "__main__":
    main()
