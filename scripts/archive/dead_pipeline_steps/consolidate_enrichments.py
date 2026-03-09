"""
Enrichment Consolidation — Merge near-duplicate facts identified by Opus judgment.

72% of Opus-judged similar-fact pairs are "enrichments" (near-duplicates).
This script clusters enrichment pairs, selects a canonical fact per cluster,
and supersedes the rest. Optionally merges text via Sonnet for identity clusters.

Critical: naive transitive closure produces mega-clusters (300+ facts all
connected through shared trading themes). We cap cluster size and skip
mega-clusters — enrichment is NOT transitive.

Algorithm:
  1. Load enrichment pairs from judgment batch files
  2. Build clusters via union-find (transitive closure)
  3. Route by cluster size:
     - Size 2: direct canonical selection (mechanical, no API)
     - Size 3-15: canonical selection + optional Sonnet text merge
     - Size 16+: skip, log for manual review
  4. Select canonical: highest tier → longest text → highest significance → highest confidence
  5. Sonnet merge (--merge flag, identity-tier clusters only): synthesize one fact
  6. Supersede non-canonical facts via superseded_by
  7. Re-embed any facts whose text was updated

Run: python consolidate_enrichments.py --analyze           # Cluster stats only
     python consolidate_enrichments.py --dry-run            # Preview decisions
     python consolidate_enrichments.py --apply              # Execute (no text merge)
     python consolidate_enrichments.py --apply --merge      # Execute + Sonnet text merge
     python consolidate_enrichments.py --stats              # Post-consolidation stats
     python consolidate_enrichments.py --dry-run --max-size 5 --limit 20  # Small subset
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import argparse
from pathlib import Path
from collections import defaultdict

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

from config import (
    DATABASE_FILE, PROJECT_ROOT, VECTORS_DIR,
    CONSOLIDATION_MAX_CLUSTER_SIZE, RECLASSIFY_MODEL,
    get_db,
)

JUDGMENT_DIR = PROJECT_ROOT / "data" / "contradictions"

TIER_RANK = {"context": 0, "situational": 1, "identity": 2}


# ---------------------------------------------------------------------------
# Step 1: Load enrichment pairs from judgment batch files
# ---------------------------------------------------------------------------

def load_enrichment_pairs():
    """Load all enrichment pairs from Opus judgment batch files."""
    pairs = []
    files_read = 0

    for jfile in sorted(JUDGMENT_DIR.glob("judgment_batch_*.json")):
        with open(jfile, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            data = data.get("judgments", data.get("results", []))

        if not isinstance(data, list):
            print(f"  WARNING: Skipping {jfile.name}: expected a list, got {type(data)}")
            continue

        for item in data:
            if not isinstance(item, dict):
                continue
            judgment = item.get("judgment", "").strip().lower()
            if judgment not in ("contradiction", "enrichment", "coexistent", "ambiguous"):
                continue
            if judgment == "enrichment":
                fact_a_id = item.get("fact_a_id")
                fact_b_id = item.get("fact_b_id")
                if not isinstance(fact_a_id, str) or not isinstance(fact_b_id, str):
                    continue
                pairs.append({
                    "fact_a_id": fact_a_id,
                    "fact_b_id": fact_b_id,
                    "fact_a_tier": item.get("fact_a_tier", "").strip().lower(),
                    "fact_b_tier": item.get("fact_b_tier", "").strip().lower(),
                    "reasoning": item.get("reasoning", ""),
                })
        files_read += 1

    print(f"  Loaded {len(pairs)} enrichment pairs from {files_read} judgment files")
    return pairs


# ---------------------------------------------------------------------------
# Step 2: Union-find clustering
# ---------------------------------------------------------------------------

class UnionFind:
    """Disjoint set / union-find for clustering fact IDs."""

    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # path compression
        return self.parent[x]

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # union by rank
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

    def clusters(self):
        """Return dict of {root: [members]}."""
        groups = defaultdict(list)
        for x in self.parent:
            groups[self.find(x)].append(x)
        return dict(groups)


def build_clusters(pairs):
    """Build clusters from enrichment pairs via union-find."""
    uf = UnionFind()
    for pair in pairs:
        uf.union(pair["fact_a_id"], pair["fact_b_id"])
    return uf.clusters()


# ---------------------------------------------------------------------------
# Step 3: Load fact details from SQLite
# ---------------------------------------------------------------------------

def load_fact_details(conn, fact_ids):
    """Load fact details for a set of fact IDs. Returns {id: dict}."""
    if not fact_ids:
        return {}

    # Safe placeholder construction: placeholders is only '?,?,?' — values go through binding
    placeholders = ','.join(['?'] * len(fact_ids))
    rows = conn.execute(
        "SELECT id, fact_text, category, confidence, significance_score,"
        "       knowledge_tier, tiered_by, superseded_by, subject,"
        "       temporal_state, fact_class, created_at"
        " FROM memory_facts"
        " WHERE id IN (" + placeholders + ")",
        list(fact_ids)
    ).fetchall()

    facts = {}
    for row in rows:
        facts[row[0]] = {
            "id": row[0],
            "text": row[1],
            "category": row[2] or "unknown",
            "confidence": row[3] or 0,
            "significance": row[4] or 0,
            "knowledge_tier": row[5] or "context",
            "tiered_by": row[6] or "unknown",
            "superseded_by": row[7],
            "subject": row[8] or "user",
            "temporal_state": row[9] or "unknown",
            "fact_class": row[10] or "state",
            "created_at": row[11],
        }
    return facts


# ---------------------------------------------------------------------------
# Step 4: Canonical selection
# ---------------------------------------------------------------------------

def select_canonical(cluster_facts):
    """Select canonical fact from a cluster.

    Priority: Opus-tiered > highest tier > longest text > highest significance > highest confidence.
    Returns (canonical, victims).
    """
    def score(fact):
        # Opus-tiered facts get massive bonus — they should always be canonical
        opus_bonus = 1000 if fact["tiered_by"] == "opus" else 0
        tier_score = TIER_RANK.get(fact["knowledge_tier"], 0) * 100
        length_score = len(fact["text"])  # more detail = better canonical
        sig_score = (fact["significance"] or 0) * 10
        conf_score = (fact["confidence"] or 0) * 10
        return opus_bonus + tier_score + length_score + sig_score + conf_score

    ranked = sorted(cluster_facts, key=score, reverse=True)
    return ranked[0], ranked[1:]


# ---------------------------------------------------------------------------
# Step 5: Sonnet text merge (optional)
# ---------------------------------------------------------------------------

MERGE_PROMPT = """You are merging near-duplicate facts about a person into one comprehensive fact.

These facts all describe the same thing with different details. Combine them into ONE fact that preserves ALL specific details (names, numbers, colors, dates, etc.) from every version. Keep it concise — one sentence if possible, two maximum.

Do NOT add any interpretation or new information. Just merge what's there.

Facts to merge:
{fact_list}

Respond with ONLY the merged fact text, nothing else."""


def merge_cluster_text(client, cluster_facts):
    """Use Sonnet to merge cluster facts into one comprehensive text."""
    fact_list = "\n".join(
        f"- {f['text']}" for f in cluster_facts
    )
    prompt = MERGE_PROMPT.format(fact_list=fact_list)

    try:
        response = client.messages.create(
            model=RECLASSIFY_MODEL,
            max_tokens=200,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        merged = response.content[0].text.strip()
        # Sanity: merged text shouldn't be dramatically shorter or longer
        min_len = min(len(f["text"]) for f in cluster_facts)
        max_len = sum(len(f["text"]) for f in cluster_facts)
        if len(merged) < min_len * 0.5:
            print(f"    [WARN] Merged text suspiciously short ({len(merged)} chars), keeping original")
            return None
        if len(merged) > max_len:
            print(f"    [WARN] Merged text longer than all inputs combined, keeping original")
            return None
        return merged
    except Exception as e:
        print(f"    [ERR] Sonnet merge failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 6: Re-embed updated facts
# ---------------------------------------------------------------------------

def reembed_facts(fact_ids):
    """Re-embed facts whose text was updated. Uses centralized embedding singleton."""
    if not fact_ids:
        return

    from api_client import get_embedding_model
    import chromadb

    print(f"\n  Re-embedding {len(fact_ids)} updated facts...")

    model = get_embedding_model()
    if model is None:
        print("  WARNING: Embedding model not available, skipping re-embedding.")
        return

    with contextlib.closing(get_db()) as conn:
        client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        collection = client.get_or_create_collection(
            "memory_facts",
            metadata={"hnsw:space": "cosine"}
        )

        for fid in fact_ids:
            row = conn.execute(
                "SELECT fact_text FROM memory_facts WHERE id = ?", (fid,)
            ).fetchone()
            if row:
                embedding = model.encode(row[0]).tolist()
                collection.upsert(ids=[fid], embeddings=[embedding])

        print(f"  Re-embedded {len(fact_ids)} facts in ChromaDB")


# ---------------------------------------------------------------------------
# Analysis mode
# ---------------------------------------------------------------------------

def run_analyze(max_cluster_size):
    """Show cluster statistics without making any changes."""
    print("=" * 60)
    print("Enrichment Consolidation — Analysis")
    print("=" * 60)

    pairs = load_enrichment_pairs()
    if not pairs:
        print("No enrichment pairs found.")
        return

    raw_clusters = build_clusters(pairs)
    print(f"  Total clusters (union-find): {len(raw_clusters)}")

    # Load fact details to check superseded status
    all_ids = set()
    for members in raw_clusters.values():
        all_ids.update(members)
    print(f"  Unique facts in enrichment pairs: {len(all_ids)}")

    with contextlib.closing(get_db()) as conn:
        facts = load_fact_details(conn, all_ids)

        # Filter out clusters with already-superseded facts
        valid_clusters = {}
        skipped_superseded = 0
        for root, members in raw_clusters.items():
            active_members = [m for m in members if m in facts and facts[m]["superseded_by"] is None]
            if len(active_members) >= 2:
                valid_clusters[root] = active_members
            else:
                skipped_superseded += len(members) - len(active_members)

        print(f"  Clusters with 2+ active facts: {len(valid_clusters)}")
        if skipped_superseded > 0:
            print(f"  Facts already superseded (removed from clusters): {skipped_superseded}")

        # Size distribution
        sizes = [len(m) for m in valid_clusters.values()]
        size_dist = defaultdict(int)
        for s in sizes:
            if s > max_cluster_size:
                size_dist[f"{max_cluster_size + 1}+ (SKIP)"] += 1
            else:
                size_dist[s] += 1

        print(f"\n  Cluster size distribution:")
        for size_key in sorted(size_dist.keys(), key=lambda x: x if isinstance(x, int) else 999):
            count = size_dist[size_key]
            if isinstance(size_key, int):
                victims = count * (size_key - 1)
                print(f"    Size {size_key:>3}: {count:>4} clusters, {victims:>4} facts to supersede")
            else:
                mega_facts = sum(s for s in sizes if s > max_cluster_size)
                print(f"    Size {size_key}: {count:>4} clusters, {mega_facts:>4} facts (SKIPPED)")

        # Actionable clusters (size <= max)
        actionable = {r: m for r, m in valid_clusters.items() if len(m) <= max_cluster_size}
        skipped_mega = {r: m for r, m in valid_clusters.items() if len(m) > max_cluster_size}

        total_victims = sum(len(m) - 1 for m in actionable.values())
        print(f"\n  Actionable clusters (size 2-{max_cluster_size}): {len(actionable)}")
        print(f"  Facts to supersede: {total_victims}")
        print(f"  Mega-clusters skipped: {len(skipped_mega)}")

        # Tier breakdown of actionable facts
        tier_counts = defaultdict(int)
        for members in actionable.values():
            for fid in members:
                if fid in facts:
                    tier_counts[facts[fid]["knowledge_tier"]] += 1

        print(f"\n  Tier breakdown of actionable facts:")
        for tier in ["identity", "situational", "context"]:
            print(f"    {tier:<15} {tier_counts.get(tier, 0)}")

        # Identity clusters (merge candidates)
        identity_clusters = 0
        for root, members in actionable.items():
            if any(facts.get(m, {}).get("knowledge_tier") == "identity" for m in members):
                identity_clusters += 1
        print(f"\n  Identity-tier clusters (merge candidates): {identity_clusters}")

        # Show mega-clusters
        if skipped_mega:
            print(f"\n  Mega-clusters (size > {max_cluster_size}):")
            for root, members in sorted(skipped_mega.items(), key=lambda x: -len(x[1])):
                sample_facts = [facts[m]["text"][:60] for m in members[:3] if m in facts]
                print(f"    Size {len(members):>4}: {' | '.join(sample_facts)}...")


# ---------------------------------------------------------------------------
# Dry-run / Apply mode
# ---------------------------------------------------------------------------

def run_consolidation(dry_run=True, merge=False, max_cluster_size=None, limit=None):
    """Run consolidation: select canonicals, optionally merge, supersede victims."""
    if max_cluster_size is None:
        max_cluster_size = CONSOLIDATION_MAX_CLUSTER_SIZE

    mode = "DRY RUN" if dry_run else "APPLY"
    print("=" * 60)
    print(f"Enrichment Consolidation — {mode}")
    if merge:
        print("  Sonnet text merge: ENABLED (identity clusters)")
    print("=" * 60)

    pairs = load_enrichment_pairs()
    if not pairs:
        print("No enrichment pairs found.")
        return

    raw_clusters = build_clusters(pairs)

    # Load all fact details
    all_ids = set()
    for members in raw_clusters.values():
        all_ids.update(members)

    with contextlib.closing(get_db()) as conn:
        facts = load_fact_details(conn, all_ids)

        # Filter: keep only clusters with 2+ active (non-superseded) facts
        valid_clusters = {}
        for root, members in raw_clusters.items():
            active = [m for m in members if m in facts and facts[m]["superseded_by"] is None]
            if len(active) >= 2:
                valid_clusters[root] = active

        # Filter by size: skip mega-clusters
        actionable = {r: m for r, m in valid_clusters.items() if len(m) <= max_cluster_size}

        # Sort by size (process small first)
        sorted_clusters = sorted(actionable.items(), key=lambda x: len(x[1]))

        if limit:
            sorted_clusters = sorted_clusters[:limit]

        total_clusters = len(sorted_clusters)
        total_victims = sum(len(m) - 1 for _, m in sorted_clusters)

        print(f"\n  Processing {total_clusters} clusters ({total_victims} facts to supersede)")
        if limit:
            print(f"  (Limited to first {limit} clusters)")

        # Initialize Sonnet client if merging
        client = None
        if merge and not dry_run:
            from api_client import get_anthropic_client
            client = get_anthropic_client()

        results = {
            "clusters_processed": 0,
            "facts_superseded": 0,
            "facts_merged": 0,
            "facts_reembedded": [],
            "opus_protected": 0,
            "tier_upgrades": 0,
        }
        decisions = []  # For logging

        for root, members in sorted_clusters:
            cluster_facts = [facts[m] for m in members if m in facts]
            if len(cluster_facts) < 2:
                continue

            canonical, victims = select_canonical(cluster_facts)

            # Determine highest tier in cluster — canonical inherits it
            highest_tier = max(
                (TIER_RANK.get(f["knowledge_tier"], 0) for f in cluster_facts),
                default=0
            )
            highest_tier_name = {v: k for k, v in TIER_RANK.items()}[highest_tier]
            tier_upgraded = highest_tier_name != canonical["knowledge_tier"]

            # Opus guard: don't supersede Opus-tiered facts in favor of non-Opus-tiered canonical.
            # If canonical is also Opus-tiered, it's safe to supersede other Opus facts.
            if canonical["tiered_by"] != "opus":
                opus_victims = [v for v in victims if v["tiered_by"] == "opus"]
                if opus_victims:
                    results["opus_protected"] += len(opus_victims)
                    continue

            # Optional Sonnet merge for identity clusters with 3+ members
            merged_text = None
            merge_candidate = (merge and highest_tier_name == "identity"
                               and len(cluster_facts) >= 3)
            if merge_candidate and not dry_run and client:
                merged_text = merge_cluster_text(client, cluster_facts)
                if merged_text:
                    results["facts_merged"] += 1

            decision = {
                "cluster_size": len(cluster_facts),
                "canonical_id": canonical["id"],
                "canonical_text": canonical["text"],
                "canonical_tier": canonical["knowledge_tier"],
                "highest_tier": highest_tier_name,
                "tier_upgraded": tier_upgraded,
                "merged_text": merged_text,
                "merge_candidate": merge_candidate,
                "victims": [(v["id"], v["text"][:80]) for v in victims],
            }
            decisions.append(decision)

            if not dry_run:
                now = time.time()

                # Supersede victims
                for victim in victims:
                    conn.execute("""
                        UPDATE memory_facts
                        SET superseded_by = ?, updated_at = ?
                        WHERE id = ? AND superseded_by IS NULL
                    """, (canonical["id"], now, victim["id"]))
                    results["facts_superseded"] += 1

                # Upgrade canonical tier if cluster had higher-tier members
                if tier_upgraded:
                    conn.execute("""
                        UPDATE memory_facts
                        SET knowledge_tier = ?, updated_at = ?
                        WHERE id = ?
                    """, (highest_tier_name, now, canonical["id"]))
                    results["tier_upgrades"] += 1

                # Update canonical text if merged
                if merged_text:
                    conn.execute("""
                        UPDATE memory_facts
                        SET fact_text = ?, updated_at = ?,
                            predicate = NULL, object_text = NULL, qualifier = NULL
                        WHERE id = ?
                    """, (merged_text, now, canonical["id"]))
                    results["facts_reembedded"].append(canonical["id"])

            results["clusters_processed"] += 1

            # Progress
            if results["clusters_processed"] % 50 == 0 or results["clusters_processed"] == total_clusters:
                print(f"  [{results['clusters_processed']}/{total_clusters}] "
                      f"superseded={results['facts_superseded']} "
                      f"merged={results['facts_merged']} "
                      f"tier_upgrades={results['tier_upgrades']}")

        if not dry_run:
            conn.commit()
            print("Running database maintenance...")
            conn.execute("ANALYZE")

        # Print decisions
        print(f"\n{'='*60}")
        print(f"{'PREVIEW' if dry_run else 'RESULTS'}")
        print(f"{'='*60}")
        actual_victims = sum(len(d["victims"]) for d in decisions)
        merge_candidates = sum(1 for d in decisions if d.get("merge_candidate"))
        print(f"  Clusters processed: {results['clusters_processed']}")
        print(f"  Facts to supersede: {actual_victims}")
        if merge:
            print(f"  Merge candidates: {merge_candidates} (identity clusters, size 3+)")
            print(f"  Facts merged (Sonnet): {results['facts_merged']}")
        print(f"  Tier upgrades: {results['tier_upgrades'] if not dry_run else sum(1 for d in decisions if d['tier_upgraded'])}")
        if results["opus_protected"]:
            print(f"  Opus-protected skips: {results['opus_protected']}")

        # Show sample decisions
        sample_count = min(30, len(decisions))
        print(f"\n  Sample decisions (first {sample_count}):")
        for d in decisions[:sample_count]:
            tier_arrow = f" ({d['canonical_tier']}→{d['highest_tier']})" if d["tier_upgraded"] else ""
            merge_tag = " [MERGED]" if d["merged_text"] else (" [MERGE CANDIDATE]" if d.get("merge_candidate") and dry_run else "")
            print(f"\n  Cluster (size {d['cluster_size']}){tier_arrow}{merge_tag}:")
            if d["merged_text"]:
                print(f"    MERGED: {d['merged_text'][:100]}")
            else:
                print(f"    KEEP:   {d['canonical_text'][:100]}")
            for vid, vtext in d["victims"]:
                print(f"    DROP:   {vtext}")

        if dry_run:
            print(f"\n  [DRY RUN] No database changes made.")
            print(f"  Run with --apply to supersede {total_victims} facts.")
        else:
            # Re-embed merged facts
            if results["facts_reembedded"]:
                reembed_facts(results["facts_reembedded"])

            # Show post-consolidation count
            remaining = conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchone()[0]
            print(f"\n  Active facts remaining: {remaining}")


# ---------------------------------------------------------------------------
# Mega-cluster reduction via Sonnet sub-theme grouping
# ---------------------------------------------------------------------------

REDUCE_PROMPT = """You are consolidating redundant facts about a person. Many are near-duplicates saying the same thing in different words.

Group ALL {count} facts into distinct themes. For each theme:
- Pick the ONE best fact: most specific, comprehensive, well-written
- List all other facts in that theme as "others" (they will be superseded)

Target approximately {target} themes. Be aggressive — merge overlapping themes.

Return ONLY valid JSON array:
[
  {{"theme": "short name", "keep": <number>, "others": [<numbers>]}},
  ...
]

CRITICAL: Every fact number (1 through {count}) MUST appear exactly once — either as a "keep" or in an "others" list. Do not skip any fact.

Facts:
{fact_list}"""


def reduce_mega_cluster(dry_run=True, cluster_rank=0):
    """Use Sonnet to reduce a mega-cluster via sub-theme grouping.

    cluster_rank: 0 = largest, 1 = second largest, etc.
    """
    import re
    from api_client import get_anthropic_client

    mode = "DRY RUN" if dry_run else "APPLY"
    print("=" * 60)
    print(f"Mega-Cluster Reduction via Sonnet — {mode}")
    print("=" * 60)

    # Find mega-clusters
    pairs = load_enrichment_pairs()
    raw_clusters = build_clusters(pairs)

    # Load all fact details to filter by active
    all_cluster_ids = set()
    for members in raw_clusters.values():
        all_cluster_ids.update(members)
    with contextlib.closing(get_db()) as conn_temp:
        all_facts = load_fact_details(conn_temp, all_cluster_ids)

    # Rank clusters by active size
    ranked = []
    for root, members in raw_clusters.items():
        active = [m for m in members if m in all_facts and all_facts[m]["superseded_by"] is None]
        if len(active) >= 2:
            sample = all_facts[active[0]]["text"][:50] if active[0] in all_facts else "?"
            ranked.append((root, active, sample))
    ranked.sort(key=lambda x: -len(x[1]))

    print(f"\n  Mega-clusters by size:")
    for i, (_, members, sample) in enumerate(ranked[:10]):
        marker = " <-- TARGET" if i == cluster_rank else ""
        print(f"    [{i}] {len(members):>4} facts: {sample}...{marker}")

    if cluster_rank >= len(ranked):
        print(f"\n  [ERR] Cluster rank {cluster_rank} out of range (only {len(ranked)} clusters)")
        return

    _, largest, _ = ranked[cluster_rank]

    # Load fact details
    with contextlib.closing(get_db()) as conn:
        facts = load_fact_details(conn, set(largest))

        # Filter to active
        active = {fid: f for fid, f in facts.items() if f["superseded_by"] is None}

        # Split by tier
        identity_facts = [(fid, f) for fid, f in active.items()
                          if f["knowledge_tier"] == "identity"]
        situational_facts = [(fid, f) for fid, f in active.items()
                             if f["knowledge_tier"] == "situational"]
        context_facts = [(fid, f) for fid, f in active.items()
                         if f["knowledge_tier"] == "context"]

        print(f"\n  Mega-cluster: {len(active)} active facts")
        print(f"    Identity:    {len(identity_facts)}")
        print(f"    Situational: {len(situational_facts)}")
        print(f"    Context:     {len(context_facts)} (skipped)")
        print(f"\n  NOTE: Sonnet API calls required (~$0.10-0.20)")

        client = get_anthropic_client()
        total_superseded = 0

        # Process identity facts
        if identity_facts:
            print(f"\n{'='*60}")
            print(f"Identity tier ({len(identity_facts)} facts → target ~10-12 themes)")
            print(f"{'='*60}")
            superseded = process_tier_reduction(
                client, conn, identity_facts, target_themes=12, dry_run=dry_run
            )
            total_superseded += superseded

        # Process situational facts
        if situational_facts:
            print(f"\n{'='*60}")
            print(f"Situational tier ({len(situational_facts)} facts → target ~20-25 themes)")
            print(f"{'='*60}")
            superseded = process_tier_reduction(
                client, conn, situational_facts, target_themes=22, dry_run=dry_run
            )
            total_superseded += superseded

        if not dry_run:
            conn.commit()

        # Summary
        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"  Facts superseded: {total_superseded}")
        print(f"  Cluster reduced: {len(active)} → ~{len(active) - total_superseded}")

        if dry_run:
            print(f"\n  [DRY RUN] No database changes made.")
            print(f"  Run with --reduce-mega --apply to execute.")
        else:
            active_count = conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchone()[0]
            print(f"\n  Total active facts: {active_count}")


def process_tier_reduction(client, conn, facts_list, target_themes, dry_run):
    """Send facts to Sonnet for theme grouping, return supersession count."""
    import re

    # Build numbered fact list
    fact_index = {}  # number -> (fact_id, fact_dict)
    fact_lines = []
    for i, (fid, f) in enumerate(facts_list, 1):
        fact_index[i] = (fid, f)
        fact_lines.append(f"{i}. {f['text']}")

    fact_list_str = "\n".join(fact_lines)

    prompt = REDUCE_PROMPT.format(
        count=len(facts_list),
        target=target_themes,
        fact_list=fact_list_str,
    )

    # Call Sonnet
    print(f"  Calling Sonnet ({len(facts_list)} facts, target {target_themes} themes)...")
    try:
        response = client.messages.create(
            model=RECLASSIFY_MODEL,
            max_tokens=8000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        themes = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            themes = json.loads(match.group())
        else:
            print(f"  [ERR] Failed to parse Sonnet response")
            print(f"  Raw: {raw[:500]}")
            return 0
    except Exception as e:
        print(f"  [ERR] Sonnet call failed: {e}")
        return 0

    # Validate: every fact number must appear exactly once
    seen = set()
    keepers = set()
    supersede_map = {}  # victim_number -> keeper_number

    for theme in themes:
        keep = theme["keep"]
        others = theme.get("others", [])

        keepers.add(keep)
        seen.add(keep)

        for other in others:
            if other in seen:
                print(f"  [WARN] Fact {other} appears in multiple themes, skipping duplicate")
                continue
            seen.add(other)
            supersede_map[other] = keep

    # Check for orphans
    all_numbers = set(range(1, len(facts_list) + 1))
    orphans = all_numbers - seen
    if orphans:
        print(f"  [WARN] {len(orphans)} facts not assigned by Sonnet — keeping them")
        keepers.update(orphans)

    print(f"\n  Sonnet grouped into {len(themes)} themes")
    print(f"  Keeping: {len(keepers)} facts")
    print(f"  Superseding: {len(supersede_map)} facts")

    # Show themes
    for theme in themes:
        keep_num = theme["keep"]
        if keep_num not in fact_index:
            print(f"  [WARN] Keep #{keep_num} out of range, skipping theme")
            continue
        keep_fid, keep_fact = fact_index[keep_num]
        others = theme.get("others", [])
        print(f"\n  [{theme['theme']}] keep #{keep_num} ({len(others)} superseded)")
        print(f"    KEEP: {keep_fact['text'][:120]}")
        for o in others[:3]:
            if o in fact_index:
                print(f"    DROP: {fact_index[o][1]['text'][:80]}")
        if len(others) > 3:
            print(f"    ... and {len(others) - 3} more")

    # Apply supersessions
    superseded_count = 0
    if not dry_run:
        now = time.time()
        for victim_num, keeper_num in supersede_map.items():
            if victim_num not in fact_index or keeper_num not in fact_index:
                continue
            victim_fid = fact_index[victim_num][0]
            keeper_fid = fact_index[keeper_num][0]
            conn.execute("""
                UPDATE memory_facts
                SET superseded_by = ?, updated_at = ?
                WHERE id = ? AND superseded_by IS NULL
            """, (keeper_fid, now, victim_fid))
            superseded_count += 1
    else:
        superseded_count = len(supersede_map)

    return superseded_count


# ---------------------------------------------------------------------------
# Stats mode
# ---------------------------------------------------------------------------

def show_stats():
    """Show pre/post consolidation statistics."""
    with contextlib.closing(get_db()) as conn:
        active = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        superseded = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NOT NULL"
        ).fetchone()[0]
        total = active + superseded

        print("=" * 60)
        print("Fact Statistics")
        print("=" * 60)
        print(f"  Total facts:      {total}")
        print(f"  Active facts:     {active}")
        print(f"  Superseded facts: {superseded}")

        # Tier distribution (active only)
        tiers = conn.execute("""
            SELECT COALESCE(knowledge_tier, 'untiered'), COUNT(*)
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY knowledge_tier
            ORDER BY COUNT(*) DESC
        """).fetchall()

        print(f"\n  Tier distribution (active):")
        for tier, count in tiers:
            pct = count / active * 100 if active > 0 else 0
            print(f"    {tier:<15} {count:>5} ({pct:.1f}%)")

        # Provenance x tier
        provenance = conn.execute("""
            SELECT COALESCE(tiered_by, 'none'), knowledge_tier, COUNT(*)
            FROM memory_facts
            WHERE superseded_by IS NULL AND knowledge_tier IS NOT NULL
            GROUP BY tiered_by, knowledge_tier
            ORDER BY tiered_by, knowledge_tier
        """).fetchall()

        if provenance:
            print(f"\n  Provenance x Tier:")
            current_tb = None
            for tb, kt, c in provenance:
                if tb != current_tb:
                    current_tb = tb
                print(f"    {tb:<12} {kt:<15} {c}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Consolidate enrichment pairs — merge near-duplicate facts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python consolidate_enrichments.py --analyze                  # Cluster stats only
  python consolidate_enrichments.py --dry-run                  # Preview decisions
  python consolidate_enrichments.py --dry-run --max-size 5     # Preview small clusters only
  python consolidate_enrichments.py --apply                    # Execute (no text merge)
  python consolidate_enrichments.py --apply --merge            # Execute + Sonnet text merge
  python consolidate_enrichments.py --apply --limit 20         # Execute first 20 clusters
  python consolidate_enrichments.py --reduce-mega              # Sonnet sub-theme reduction (dry-run)
  python consolidate_enrichments.py --reduce-mega --apply      # Sonnet sub-theme reduction (execute)
  python consolidate_enrichments.py --stats                    # Post-consolidation stats
""",
    )
    parser.add_argument("--analyze", action="store_true",
                        help="Show cluster statistics without making changes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview consolidation decisions without applying")
    parser.add_argument("--apply", action="store_true",
                        help="Apply consolidation (supersede non-canonical facts)")
    parser.add_argument("--merge", action="store_true",
                        help="Enable Sonnet text merge for identity clusters (requires --apply)")
    parser.add_argument("--reduce-mega", action="store_true",
                        help="Use Sonnet to reduce a mega-cluster via sub-theme grouping")
    parser.add_argument("--cluster-rank", type=int, default=0,
                        help="Which mega-cluster to reduce: 0=largest, 1=second, etc. (default: 0)")
    parser.add_argument("--stats", action="store_true",
                        help="Show post-consolidation statistics")
    parser.add_argument("--max-size", type=int, default=CONSOLIDATION_MAX_CLUSTER_SIZE,
                        help=f"Max cluster size to process (default: {CONSOLIDATION_MAX_CLUSTER_SIZE})")
    parser.add_argument("--limit", type=int,
                        help="Process only first N clusters (smallest first)")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.reduce_mega:
        reduce_mega_cluster(dry_run=not args.apply, cluster_rank=args.cluster_rank)
    elif args.analyze:
        run_analyze(args.max_size)
    elif args.dry_run:
        run_consolidation(dry_run=True, merge=args.merge,
                          max_cluster_size=args.max_size, limit=args.limit)
    elif args.apply:
        run_consolidation(dry_run=False, merge=args.merge,
                          max_cluster_size=args.max_size, limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
