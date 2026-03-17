"""
Periodic tier reclassification via Sonnet — generalized promotion/reclassification.

Selects facts by source tier and/or source model, batches through Sonnet for
reclassification. Supports promotion-only mode (only upgrade tiers) or full
reclassification (allow up/down). Tracks provenance via tiered_by='sonnet'.

Pre-filters (guards) skip facts unlikely to promote, saving API cost:
  - subject != 'user' → skip (third-party facts stay at context)
  - fact_class = 'event' + promoting to identity → skip
  - temporal_state = 'past' + promoting to identity → skip
  - tiered_by = 'opus' → skip (don't override Opus judgment)

Run: python reclassify_tiers.py --source-tier context --limit 200       # Promote context candidates
     python reclassify_tiers.py --source-tier situational               # Promote situational candidates
     python reclassify_tiers.py --source-tier context --direction any   # Full reclassification
     python reclassify_tiers.py --source-tier all --source-model qwen   # Reclassify all Qwen-tiered
     python reclassify_tiers.py --stats                                  # Show distribution
     python reclassify_tiers.py --source-tier context --dry-run         # Preview without writing
"""

import contextlib
import sys
import io
import json
import time
import argparse

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

from config import DATABASE_FILE, RECLASSIFY_MODEL, RECLASSIFY_BATCH_SIZE, get_db

VALID_TIERS = {"identity", "situational", "context"}
TIER_RANK = {"untiered": -1, "context": 0, "situational": 1, "identity": 2}

# Tiers that can be targeted
VALID_SOURCE_TIERS = {"context", "situational", "identity", "all"}
VALID_SOURCE_MODELS = {"qwen", "sonnet", "opus", "all"}
VALID_DIRECTIONS = {"promote", "any"}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

RECLASSIFY_PROMPT = """You are classifying facts about a person into knowledge tiers for a memory system.

CRITICAL RULES:
1. If the fact is about someone OTHER than the primary user, classify as context.
2. Apply the "single conversation test": would this fact make sense to someone who never saw the conversation it came from? If NOT, it is context.
3. "The user was doing X in a conversation" is NOT the same as "the user is the kind of person who does X." Doing something once is context. Doing something as a pattern is identity.
4. When in doubt between situational and context, choose context.
5. When in doubt between identity and situational, choose situational.

**IDENTITY** — Who this person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences, proven skills, formative experiences. Would appear in a 500-word biography. Stable over months/years.
Examples: "Values work-life balance", "Founded a startup", "Values discipline in trading", "Has a project car", "Tends to overtrade when emotional"

**SITUATIONAL** — Current mutable conditions true NOW, persisting weeks/months. Active projects, ongoing dispositions, living situation, employment.
Examples: "Is building a personal AI memory system", "Is bearish on tech sector", "Lives in Portland", "Works at [company]"

**CONTEXT** — Conversation artifacts. One-off tasks, specific lookups, single-conversation activities, third-party observations, specific trade setups, product research. If it describes what happened in ONE conversation, it is context.
Examples: "Seeking to personalize resume for Demand.io", "Considering GDX LEAPS", "Converting JSON to CSV", "Jason McCann led the Snap-on project", "Uses almond milk in cake mix"

For each fact below, respond with ONLY a JSON array of tier classifications in order.
Example response: ["context", "identity", "situational", "context", "identity"]

Facts to classify:
"""

PROMOTION_PROMPT_TEMPLATE = """You are reviewing facts about a person for possible tier PROMOTION in a memory system.

Each fact below is currently classified as **{current_tier}**. You should ONLY promote a fact if you are confident it belongs in a higher tier. When in doubt, keep the current tier.

Tier definitions (from lowest to highest):
- **CONTEXT** — Conversation artifacts. One-off tasks, specific lookups, single-conversation activities, third-party observations, specific trade setups. If it describes what happened in ONE conversation, it is context.
- **SITUATIONAL** — Current mutable conditions true NOW, persisting weeks/months. Active projects, ongoing dispositions, living situation, employment.
- **IDENTITY** — Who this person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences, proven skills, formative experiences. Would appear in a 500-word biography. Stable over months/years.

CRITICAL RULES:
1. If the fact is about someone OTHER than the primary user → keep as context.
2. "The user was doing X" once is NOT identity. Patterns are identity.
3. Bias toward keeping the current tier. Only promote when clearly warranted.
4. If promoting from context: situational is the most likely promotion target, not identity.
5. If promoting from situational to identity: the fact must be a durable biographical anchor, not just a current project.

For each fact, respond with ONLY a JSON array of tier classifications in order.
Example: ["{current_tier}", "{target_tier}", "{current_tier}"]

Facts (currently {current_tier}):
"""


# ---------------------------------------------------------------------------
# Candidate Selection
# ---------------------------------------------------------------------------

def get_candidates(source_tier, source_model, direction, limit=None, primary_subject=None):
    """Fetch candidate facts for reclassification with pre-filters applied."""
    with contextlib.closing(get_db()) as conn:
        conditions = ["superseded_by IS NULL", "knowledge_tier IS NOT NULL"]

        params = []

        # Source tier filter
        if source_tier != "all":
            conditions.append("knowledge_tier = ?")
            params.append(source_tier)

        # Source model filter
        if source_model != "all":
            conditions.append("tiered_by = ?")
            params.append(source_model)

        # Guard: never override Opus judgment
        conditions.append("(tiered_by != 'opus' OR tiered_by IS NULL)")

        # Guard: skip third-party facts for promotion
        # For document corpora, primary_subject replaces 'user'
        if direction == "promote":
            subject_name = primary_subject or "user"
            conditions.append("subject = ?")
            params.append(subject_name)

        # Safety: WHERE clause is built from a fixed set of parameterized conditions,
        # not from user input. All dynamic values go through ? placeholders.
        where = " AND ".join(conditions)
        query = f"""
            SELECT mf.id, mf.fact_text, mf.category, mf.temporal_state,
                   mf.knowledge_tier, mf.subject, mf.fact_class,
                   COALESCE(c.source, '') as conv_source
            FROM memory_facts mf
            LEFT JOIN conversations c ON mf.source_conversation_id = c.id
            WHERE {where}
            ORDER BY mf.id
        """
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
    return rows


def apply_promotion_guards(facts, source_tier, direction):
    """Apply additional per-fact guards for promotion mode.
    Returns (eligible, skipped) tuples."""
    if direction != "promote":
        return facts, []

    # Sources where past-tense is expected (autobiographies, journals, text imports)
    # For these sources, past-tense facts are still identity-defining
    past_exempt_sources = ("text_file", "journal")

    eligible = []
    skipped = []

    for fact in facts:
        fid, text, cat, temporal, current_tier, subject, fact_class, conv_source = fact

        # Guard: events can't promote to identity (immutable anchors, not patterns)
        if fact_class == "event" and current_tier == "context":
            skipped.append((fact, "event_skip"))
            continue

        # Guard: past-state facts don't promote to identity
        # Exception: text_file and journal sources where past tense IS the content
        if temporal == "past" and current_tier in ("context", "situational"):
            if conv_source not in past_exempt_sources:
                skipped.append((fact, "past_skip"))
                continue

        eligible.append(fact)

    return eligible, skipped


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def build_prompt(facts, source_tier, direction):
    """Build the appropriate prompt based on direction."""
    if direction == "promote" and source_tier != "all":
        # Promotion-aware prompt: more conservative
        target = "situational" if source_tier == "context" else "identity"
        prompt = PROMOTION_PROMPT_TEMPLATE.format(
            current_tier=source_tier,
            target_tier=target,
        )
    else:
        prompt = RECLASSIFY_PROMPT

    fact_lines = []
    for i, fact in enumerate(facts, 1):
        fid, text, cat, temporal, current_tier, subject, fact_class = fact[:7]
        fact_lines.append(f"{i}. [{cat or 'unknown'}] {text}")

    return prompt + "<facts>\n" + "\n".join(fact_lines) + "\n</facts>"


def classify_batch(client, facts, source_tier, direction):
    """Classify a batch of facts using Sonnet. Returns list of tiers.

    Uses centralized api_client for retry and logging. The client parameter
    is kept for interface compatibility but is no longer used directly.
    """
    from api_client import call_api

    prompt = build_prompt(facts, source_tier, direction)

    try:
        response = call_api(
            model=RECLASSIFY_MODEL,
            max_tokens=20 * len(facts) + 50,  # proportional to batch size + margin
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            caller="reclassify_tiers",
        )
        raw = response.content[0].text.strip()

        tiers = json.loads(raw)
        if not isinstance(tiers, list) or len(tiers) != len(facts):
            print(f"  [WARN] Expected {len(facts)} tiers, got {len(tiers) if isinstance(tiers, list) else 'non-list'}: [{len(raw)} chars, parse failed]")
            return None

        result = []
        for t in tiers:
            t = t.strip().lower()
            if t in VALID_TIERS:
                result.append(t)
            else:
                print(f"  [WARN] Invalid tier '{t}' in response")
                return None
        return result

    except json.JSONDecodeError:
        print(f"  [ERR] Failed to parse JSON: [{len(raw)} chars, parse failed]")
        return None
    except Exception as e:
        print(f"  [ERR] API error: {e}")
        return None


def enforce_direction(old_tier, new_tier, direction):
    """If direction='promote', only allow upward changes. Otherwise allow any."""
    if direction == "promote":
        if TIER_RANK.get(new_tier, 0) <= TIER_RANK.get(old_tier, 0):
            return old_tier  # Keep current tier (no demotion allowed)
    return new_tier


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def show_stats():
    """Show provenance x tier distribution."""
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT COALESCE(tiered_by, 'none') as tb, knowledge_tier, COUNT(*)
            FROM memory_facts
            WHERE superseded_by IS NULL
            AND knowledge_tier IS NOT NULL
            GROUP BY tb, knowledge_tier
            ORDER BY tb, knowledge_tier
        """).fetchall()

        print("\nProvenance x Tier (active facts):")
        print("-" * 45)
        current_tb = None
        for tb, kt, c in rows:
            if tb != current_tb:
                if current_tb is not None:
                    print()
                current_tb = tb
            print(f"  {tb:<12} {kt:<15} {c}")

        # Totals per tier
        totals = conn.execute("""
            SELECT knowledge_tier, COUNT(*)
            FROM memory_facts
            WHERE superseded_by IS NULL AND knowledge_tier IS NOT NULL
            GROUP BY knowledge_tier
            ORDER BY knowledge_tier
        """).fetchall()

        total_all = sum(c for _, c in totals)
        print(f"\n{'Totals:':<28}")
        for kt, c in totals:
            pct = c / total_all * 100 if total_all > 0 else 0
            print(f"  {'TOTAL':<12} {kt:<15} {c} ({pct:.1f}%)")
        print(f"  {'TOTAL':<12} {'all':<15} {total_all}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Periodic tier reclassification via Sonnet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reclassify_tiers.py --source-tier context --limit 200       # Promote context candidates
  python reclassify_tiers.py --source-tier situational               # Promote situational candidates
  python reclassify_tiers.py --source-tier context --direction any   # Full reclassification
  python reclassify_tiers.py --source-tier all --source-model qwen   # Reclassify all Qwen-tiered
  python reclassify_tiers.py --stats                                  # Show distribution
""",
    )
    parser.add_argument("--source-tier", choices=["context", "situational", "identity", "all"],
                        default="context", help="Which tier to reclassify (default: context)")
    parser.add_argument("--source-model", choices=["qwen", "sonnet", "opus", "all"],
                        default="all", help="Which tiered_by to target (default: all)")
    parser.add_argument("--direction", choices=["promote", "any"],
                        default="promote", help="'promote' only upgrades tiers; 'any' allows up/down (default: promote)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--limit", type=int, help="Process only first N candidates")
    parser.add_argument("--stats", action="store_true", help="Show provenance distribution and exit")
    parser.add_argument("--subject", type=str, default=None,
                        help="Primary subject name for document corpora (default: 'user'). "
                             "Facts with this subject are eligible for promotion.")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Note: --source-model opus would be blocked by the opus guard in get_candidates,
    # so it effectively returns nothing. That's correct — we never reclassify Opus-tiered facts.
    if args.source_model == "opus":
        print("Opus-tiered facts are protected from reclassification. Nothing to do.")
        show_stats()
        return

    # Auto-initialize: set untiered facts to 'context' so promotion can work.
    # New pipelines produce 'untiered' facts — the tier step expects 'context' as baseline.
    with contextlib.closing(get_db()) as conn:
        untiered_count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE knowledge_tier = 'untiered' AND superseded_by IS NULL"
        ).fetchone()[0]
        if untiered_count > 0:
            conn.execute(
                "UPDATE memory_facts SET knowledge_tier = 'context' WHERE knowledge_tier = 'untiered' AND superseded_by IS NULL"
            )
            conn.commit()
            print(f"Initialized {untiered_count} untiered facts to 'context' tier.")

    from api_client import get_anthropic_client
    client = get_anthropic_client()

    # Fetch candidates
    raw_candidates = get_candidates(args.source_tier, args.source_model, args.direction, args.limit,
                                     primary_subject=args.subject)
    print(f"Found {len(raw_candidates)} raw candidates "
          f"(source_tier={args.source_tier}, source_model={args.source_model}, direction={args.direction})")

    # Apply per-fact promotion guards
    candidates, skipped = apply_promotion_guards(raw_candidates, args.source_tier, args.direction)
    if skipped:
        skip_reasons = {}
        for _, reason in skipped:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        print(f"Pre-filtered: {len(skipped)} skipped ({skip_reasons}), {len(candidates)} eligible")

    if not candidates:
        print("Nothing to do.")
        show_stats()
        return

    results = {"promoted": 0, "kept": 0, "demoted": 0, "errors": 0}
    changes = []   # (fact_id, old_tier, new_tier, fact_text) for logging
    updates = []   # (new_tier, 'sonnet', fact_id) for DB update
    start = time.time()

    for batch_start in range(0, len(candidates), RECLASSIFY_BATCH_SIZE):
        batch = candidates[batch_start:batch_start + RECLASSIFY_BATCH_SIZE]
        tiers = classify_batch(client, batch, args.source_tier, args.direction)

        if tiers is None:
            results["errors"] += len(batch)
            # Retry individually on batch failure
            for fact in batch:
                single_tier = classify_batch(client, [fact], args.source_tier, args.direction)
                if single_tier:
                    new_tier = enforce_direction(fact[4], single_tier[0], args.direction)
                    results["errors"] -= 1
                    updates.append((new_tier, "sonnet", fact[0]))
                    _record_change(fact, new_tier, results, changes)
        else:
            for fact, raw_tier in zip(batch, tiers):
                new_tier = enforce_direction(fact[4], raw_tier, args.direction)
                updates.append((new_tier, "sonnet", fact[0]))
                _record_change(fact, new_tier, results, changes)

        # Rate limiting between batches to avoid API throttling
        time.sleep(0.3)

        processed = min(batch_start + RECLASSIFY_BATCH_SIZE, len(candidates))
        if processed % 50 == 0 or processed == len(candidates):
            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = (len(candidates) - processed) / rate if rate > 0 else 0
            print(f"  [{processed}/{len(candidates)}] "
                  f"promoted={results['promoted']} kept={results['kept']} "
                  f"demoted={results['demoted']} errors={results['errors']} "
                  f"({rate:.1f} facts/s, ~{remaining:.0f}s remaining)")

    elapsed = time.time() - start
    print(f"\nReclassification complete in {elapsed:.1f}s")
    print(f"Results: {results['promoted']} promoted, {results['kept']} kept, "
          f"{results['demoted']} demoted, {results['errors']} errors")

    # Show sample changes
    actual_changes = [(fid, old, new, text) for fid, old, new, text in changes if old != new]
    if actual_changes:
        print(f"\nSample changes (first 20 of {len(actual_changes)}):")
        for fid, old, new, text in actual_changes[:20]:
            arrow = "^" if TIER_RANK[new] > TIER_RANK[old] else "v"
            print(f"  {arrow} {old} -> {new}: {text[:80]}")

    if args.dry_run:
        print("\n[DRY RUN] No database changes made.")
    else:
        with contextlib.closing(get_db()) as conn:
            with conn:
                conn.executemany(
                    "UPDATE memory_facts SET knowledge_tier = ?, tiered_by = ? WHERE id = ?",
                    updates
                )
            print(f"\nUpdated {len(updates)} facts in database (tiered_by=sonnet).")

    show_stats()


def _record_change(fact, new_tier, results, changes):
    """Record a tier change in results counters and changes list."""
    fid, text, cat, temporal, old_tier, subject, fact_class = fact[:7]
    if TIER_RANK.get(new_tier, 0) > TIER_RANK.get(old_tier, 0):
        results["promoted"] += 1
    elif new_tier == old_tier:
        results["kept"] += 1
    else:
        results["demoted"] += 1
    changes.append((fid, old_tier, new_tier, text))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
