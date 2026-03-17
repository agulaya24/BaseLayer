"""
Backfill Knowledge Tier — Qwen 2.5 14B pass on untiered facts

Classifies the ~2,259 untiered facts into identity/situational/context
using the V2 tier classification prompt (D-039).

Run: python backfill_knowledge_tier.py           # Process all untiered facts
     python backfill_knowledge_tier.py --dry-run  # Preview without writing
     python backfill_knowledge_tier.py --limit 50  # Process first 50 only
     python backfill_knowledge_tier.py --stats     # Show current tier distribution
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import argparse
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import DATABASE_FILE, OLLAMA_URL, LLM_MODEL

TIER_PROMPT = """You are classifying facts about a person into knowledge tiers for a memory system.

CRITICAL RULES before classifying:
1. If the fact is about someone OTHER than the primary user, classify as context.
2. Apply the "single conversation test": would this fact make sense to someone who never saw the conversation it came from? If NOT, it is context.
3. "The user was doing X in a conversation" is NOT the same as "the user is the kind of person who does X." Doing something once is context. Doing something as a pattern is identity.
4. When in doubt between situational and context, choose context.

**IDENTITY** — Who this person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences, proven skills, formative experiences. Would appear in a 500-word biography. Stable over months/years.
Examples:
- "Values work-life balance" → identity
- "Founded a startup" → identity
- "Values discipline and consistency in trading" → identity
- "Has a project car" → identity
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
- "User's parent understands trading risks" → context (third-party fact)
- "The cats drink a lot of water" → context (trivial observation)

Classify the following fact. Respond with ONLY the tier name: identity, situational, or context

Fact: {fact_text}
Category: {category}
Temporal state: {temporal_state}

Tier:"""

VALID_TIERS = {"identity", "situational", "context"}


def classify_fact(fact_text: str, category: str, temporal_state: str) -> str:
    """Classify a single fact using Qwen 2.5 14B."""
    prompt = TIER_PROMPT.format(
        fact_text=fact_text,
        category=category or "unknown",
        temporal_state=temporal_state or "unknown",
    )

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 20, "temperature": 0.1},
        }, timeout=30)
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip().lower()

        # Extract tier from response (may have extra text)
        for tier in VALID_TIERS:
            if tier in raw:
                return tier
        return "untiered"
    except Exception as e:
        print(f"  [ERR] {e}")
        return "untiered"


def get_untiered_facts(limit=None):
    """Fetch all untiered active facts."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        query = """
            SELECT id, fact_text, category, temporal_state
            FROM memory_facts
            WHERE superseded_by IS NULL
            AND (knowledge_tier IS NULL OR knowledge_tier = 'untiered')
            ORDER BY id
        """
        params = ()
        if limit:
            query += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(query, params).fetchall()
    return rows


def show_stats():
    """Show current tier distribution."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        rows = conn.execute("""
            SELECT COALESCE(knowledge_tier, 'untiered') as kt, COUNT(*)
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY kt
            ORDER BY COUNT(*) DESC
        """).fetchall()
        total = sum(r[1] for r in rows)
        print(f"\nKnowledge Tier Distribution ({total} active facts):")
        print("-" * 45)
        for tier, count in rows:
            pct = count / total * 100
            print(f"  {tier:12s}  {count:5d}  ({pct:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Backfill knowledge tiers via Qwen 2.5")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--limit", type=int, help="Process only first N facts")
    parser.add_argument("--stats", action="store_true", help="Show tier distribution and exit")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    facts = get_untiered_facts(limit=args.limit)
    print(f"Found {len(facts)} untiered facts to classify")

    if not facts:
        print("Nothing to do.")
        show_stats()
        return

    results = {"identity": 0, "situational": 0, "context": 0, "untiered": 0}
    updates = []
    start = time.time()

    for i, (fact_id, fact_text, category, temporal_state) in enumerate(facts):
        tier = classify_fact(fact_text, category, temporal_state)
        results[tier] += 1
        if tier != "untiered":
            updates.append((tier, fact_id))

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            remaining = (len(facts) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(facts)}] "
                  f"identity={results['identity']} situational={results['situational']} "
                  f"context={results['context']} untiered={results['untiered']} "
                  f"({rate:.1f} facts/s, ~{remaining:.0f}s remaining)")

    elapsed = time.time() - start
    print(f"\nClassification complete in {elapsed:.1f}s ({len(facts)/elapsed:.1f} facts/s)")
    print(f"Results: identity={results['identity']} situational={results['situational']} "
          f"context={results['context']} untiered={results['untiered']}")

    if args.dry_run:
        print("\n[DRY RUN] No database changes made.")
    else:
        with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
            with conn:
                conn.executemany(
                    "UPDATE memory_facts SET knowledge_tier = ?, tiered_by = 'qwen' WHERE id = ?",
                    updates
                )
            print(f"\nUpdated {len(updates)} facts in database (tiered_by=qwen).")

    show_stats()


if __name__ == "__main__":
    main()
