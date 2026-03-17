"""
Phase 4: Post-Extraction Fact Scoring (D-015, D-022)

Runs AFTER extract_facts.py completes. Three jobs:

1. Significance scoring — wire up D-015 recurrence + depth signals to each fact
2. Edge pruning — remove stale fact_relationships pointing to superseded facts
3. Sentiment pass — tag relationship-category facts with sentiment (separate LLM call)

Session 55 (Plan 3): Temporal recurrence dedup — 24-hour windowing so that
20 mentions in one day count as 1 recurrence, not 20. Stores both raw and
windowed recurrence counts for backwards compatibility.

Run: python score_facts.py                # All three jobs
     python score_facts.py --score-only   # Just significance scoring
     python score_facts.py --prune-only   # Just edge pruning
     python score_facts.py --sentiment    # Just sentiment pass (needs Ollama)
     python score_facts.py --stats        # Show scoring statistics
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import math
import re
import argparse
import requests

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

# ---------------------------------------------------------------------------
# Shared config — single source of truth (config.py)
# ---------------------------------------------------------------------------
from config import (
    DATABASE_FILE, OLLAMA_URL, LLM_MODEL,
    RECURRENCE_FLOOR_HIGH, RECURRENCE_FLOOR_MID,
    RECURRENCE_FLOOR_HIGH_SCORE, RECURRENCE_FLOOR_MID_SCORE,
    RECURRENCE_MIN_SPAN_DAYS,
    RECURRENCE_NORMALIZATION_CEILING, RECURRENCE_WINDOW_HOURS,
    get_db,
)


# ---------------------------------------------------------------------------
# Schema migration: add windowed_recurrence column
# ---------------------------------------------------------------------------

def _ensure_windowed_recurrence_column(conn):
    """Session 55 (Plan 3): Add windowed_recurrence column if missing.
    Stores the temporally deduped recurrence count (24-hour windows).
    Safe to call repeatedly — silently skips if column already exists."""
    try:
        conn.execute("ALTER TABLE memory_facts ADD COLUMN windowed_recurrence INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists


# ---------------------------------------------------------------------------
# Significance Scoring
# ---------------------------------------------------------------------------

def get_fact_keywords(fact_text: str) -> list[str]:
    """Extract meaningful keywords from a fact for recurrence search.
    Strips common/short words, deduplicates, and returns 2-4 key terms."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "has", "have", "had",
        "user", "they", "their", "them", "this", "that", "with", "from",
        "for", "and", "but", "not", "very", "also", "been", "being",
        "about", "into", "some", "than", "more", "most", "other",
        "what", "when", "where", "which", "who", "how", "all", "each",
        "does", "did", "will", "would", "could", "should", "may", "might",
        "can", "using", "used", "uses", "like", "likes", "interested",
        "in", "on", "at", "to", "of", "by", "as", "or", "if", "so",
        # Additional stop words — common short/generic words that inflate recurrence
        "just", "get", "got", "its", "one", "two", "way", "new", "own",
        "now", "still", "well", "back", "even", "much", "many", "made",
        "make", "over", "such", "take", "only", "come", "good", "give",
        "going", "want", "wants", "need", "needs", "think", "things",
        "thing", "really", "know", "said", "says", "work", "working",
        "works", "see", "time", "first", "last", "long", "great", "little",
        "right", "look", "day", "set", "try", "ask", "put", "keep",
        "let", "say", "help", "start", "started", "seems", "seem",
        # Temporal/positional words that co-occur in unrelated conversations
        "out", "off", "end", "times", "week", "weeks", "year", "years",
        "month", "months", "per", "down", "after", "before", "through",
        "around", "between", "under", "during", "away", "both", "same",
        "another", "since", "there", "here", "went", "done", "found",
        "able", "part", "feel", "feels", "tend", "tends", "often",
        "usually", "currently", "likely", "early", "late", "rather",
        "quite", "already", "enough", "taking", "having", "being",
        "doing", "coming", "getting", "making", "looking", "trying",
    }

    # Tokenize and filter
    words = re.findall(r'\b[a-zA-Z]{3,}\b', fact_text.lower())
    keywords = [w for w in words if w not in stop_words]

    # Deduplicate while preserving order, then sort by length (more specific first)
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    unique.sort(key=len, reverse=True)
    return unique[:4] if unique else []


def _apply_temporal_windowing(conv_timestamps: list[float]) -> int:
    """Session 55 (Plan 3): Apply 24-hour temporal windowing to conversation timestamps.

    Groups conversations into temporal windows of RECURRENCE_WINDOW_HOURS.
    Within each window, count as 1 recurrence regardless of how many
    conversations mention the topic. This prevents frequency inflation from
    same-day multi-conversation bursts (e.g., 20 trading conversations in
    one day should count as 1 windowed recurrence, not 20).

    Args:
        conv_timestamps: List of conversation created_at timestamps (unix epoch).

    Returns:
        Number of distinct temporal windows (windowed recurrence count).
    """
    if not conv_timestamps:
        return 0

    # Sort timestamps
    sorted_ts = sorted(conv_timestamps)

    # Window size in seconds
    window_seconds = RECURRENCE_WINDOW_HOURS * 3600

    # Count windows: each time a conversation falls outside the current window,
    # start a new window
    windows = 1
    window_start = sorted_ts[0]

    for ts in sorted_ts[1:]:
        if ts - window_start >= window_seconds:
            windows += 1
            window_start = ts

    return windows


def compute_fact_significance(conn, fact_id: str, fact_text: str,
                              source_conv_id: str) -> dict:
    """Compute significance score for a single fact using D-015 signals.

    Session 55 (Plan 3): Now computes both raw recurrence (for backwards
    compatibility) and windowed recurrence (for scoring). The windowed
    recurrence uses 24-hour temporal dedup to prevent frequency inflation.
    """

    keywords = get_fact_keywords(fact_text)
    if not keywords:
        return {
            "significance_score": 0,
            "recurrence_count": 0,
            "windowed_recurrence": 0,
            "depth_score": 0,
            "recurrence_span_days": 0,
            "significance_type": "unknown",
        }

    # Build 2+ co-occurrence query (AND logic across conversation)
    # For each keyword, check if ANY message in the conversation contains it.
    # Count how many distinct keywords appear, require 2+ (or 1 if only 1 keyword).
    min_co_occur = min(2, len(keywords))
    # Dynamic SQL from internal data — not user-controlled
    # Each term: 1 if keyword appears in any message in the conversation, else 0
    # LIKE values are passed via parameter binding (like_params)
    presence_exprs = " + ".join(
        ["MIN(1, SUM(CASE WHEN LOWER(m.content_text) LIKE ? THEN 1 ELSE 0 END))"
         for _ in keywords]
    )
    like_params = ["%{}%".format(kw) for kw in keywords]

    # Count conversations where 2+ keywords appear anywhere across user messages
    # Dynamic SQL: presence_exprs built from internal keyword count.
    # min_co_occur is parameterized via ? binding (integer from internal logic).
    like_params.append(min_co_occur)
    rows = conn.execute("""
        SELECT m.conversation_id,
               COUNT(*) as user_turns,
               AVG(LENGTH(m.content_text)) as avg_msg_length
        FROM messages m
        WHERE m.role = 'user'
        GROUP BY m.conversation_id
        HAVING (""" + presence_exprs + """) >= ?
    """, like_params).fetchall()

    if not rows:
        return {
            "significance_score": 0,
            "recurrence_count": 0,
            "windowed_recurrence": 0,
            "depth_score": 0,
            "recurrence_span_days": 0,
            "significance_type": "episodic",
        }

    # Raw recurrence = number of conversations (backwards compat)
    raw_recurrence = len(rows)
    total_turns = sum(r[1] for r in rows)
    avg_turns = total_turns / raw_recurrence if raw_recurrence > 0 else 0
    deep_convos = sum(1 for r in rows if r[1] >= 4)

    # Date span — only from conversations that passed 2+ co-occurrence filter
    conv_ids = [r[0] for r in rows]
    if conv_ids:
        placeholders = ",".join(["?"] * len(conv_ids))
        date_row = conn.execute(
            "SELECT MIN(c.created_at), MAX(c.created_at)"
            " FROM conversations c"
            " WHERE c.id IN (" + placeholders + ")",
            conv_ids
        ).fetchone()
    else:
        date_row = (None, None)

    first_ts = date_row[0]
    last_ts = date_row[1]
    span_days = int((last_ts - first_ts) / 86400) if first_ts and last_ts else 0

    # Session 55 (Plan 3): Temporal windowing — get conversation timestamps
    # and apply 24-hour dedup to compute windowed recurrence
    if conv_ids:
        placeholders = ",".join(["?"] * len(conv_ids))
        ts_rows = conn.execute(
            "SELECT c.created_at FROM conversations c"
            " WHERE c.id IN (" + placeholders + ")"
            " ORDER BY c.created_at",
            conv_ids
        ).fetchall()
        conv_timestamps = [r[0] for r in ts_rows if r[0] is not None]
    else:
        conv_timestamps = []

    windowed_recurrence = _apply_temporal_windowing(conv_timestamps)

    # Depth score (0-10 scale, matching surprise_scoring.py)
    turns_score = min(avg_turns / 4, 1.0) * 10
    depth_ratio = deep_convos / raw_recurrence if raw_recurrence > 0 else 0
    depth_component = depth_ratio * 10
    depth_score = turns_score * 0.50 + depth_component * 0.50
    depth_score = round(depth_score, 2)

    # Session 55 (Plan 3): Use windowed recurrence for scoring normalization.
    # Normalization ceiling lowered from 300 to 150 because windowed counts
    # are roughly half of raw counts after temporal dedup.
    if windowed_recurrence > 0:
        recurrence_normalized = min(
            math.log(windowed_recurrence + 1) / math.log(RECURRENCE_NORMALIZATION_CEILING) * 10,
            10
        )
    else:
        recurrence_normalized = 0

    # Weighted significance score
    weighted_score = (
        0.40 * (depth_score) +
        0.60 * recurrence_normalized
    )

    # Apply recurrence floor (D-015)
    # Session 55 (Plan 3): Floor thresholds now use windowed recurrence
    # (30/18 instead of 50/30, proportional to temporal dedup reduction)
    floor = 0
    if windowed_recurrence >= RECURRENCE_FLOOR_HIGH and span_days >= RECURRENCE_MIN_SPAN_DAYS:
        floor = RECURRENCE_FLOOR_HIGH_SCORE
    elif windowed_recurrence >= RECURRENCE_FLOOR_MID and span_days >= RECURRENCE_MIN_SPAN_DAYS:
        floor = RECURRENCE_FLOOR_MID_SCORE

    final_score = round(max(floor, weighted_score), 2)
    final_score = min(final_score, 10)

    # Classify significance type
    # Session 55 (Plan 3): Thresholds adjusted for windowed recurrence
    if depth_ratio >= 0.15 and avg_turns >= 2.0:
        sig_type = "depth"
    elif windowed_recurrence >= 18 and span_days >= 180:
        sig_type = "identity"
    elif windowed_recurrence >= 6:
        sig_type = "recurring"
    else:
        sig_type = "episodic"

    return {
        "significance_score": final_score,
        "recurrence_count": raw_recurrence,
        "windowed_recurrence": windowed_recurrence,
        "depth_score": depth_score,
        "recurrence_span_days": span_days,
        "significance_type": sig_type,
    }


def run_significance_scoring():
    """Score all active facts with significance metrics.

    Session 55 (Plan 3): Now stores both recurrence_count (raw, backwards compat)
    and windowed_recurrence (24-hour deduped, used for scoring).
    """
    print("=" * 60)
    print("Significance Scoring (D-015 wire-up)")
    print(f"Temporal dedup: {RECURRENCE_WINDOW_HOURS}h window, "
          f"ceiling {RECURRENCE_NORMALIZATION_CEILING}")
    print("=" * 60)

    with contextlib.closing(get_db()) as conn:
        # Session 55 (Plan 3): Ensure windowed_recurrence column exists
        _ensure_windowed_recurrence_column(conn)

        # Get all active facts that haven't been scored yet (or re-score all)
        facts = conn.execute("""
            SELECT id, fact_text, source_conversation_id
            FROM memory_facts
            WHERE superseded_by IS NULL
            ORDER BY created_at
        """).fetchall()

        total = len(facts)
        print(f"\nScoring {total} active facts...")

        start_time = time.time()
        scored = 0
        errors = 0

        for i, (fact_id, fact_text, conv_id) in enumerate(facts):
            try:
                result = compute_fact_significance(conn, fact_id, fact_text, conv_id)

                conn.execute("""
                    UPDATE memory_facts
                    SET significance_score = ?,
                        recurrence_count = ?,
                        windowed_recurrence = ?,
                        depth_score = ?,
                        recurrence_span_days = ?,
                        significance_type = ?
                    WHERE id = ?
                """, (
                    result["significance_score"],
                    result["recurrence_count"],
                    result["windowed_recurrence"],
                    result["depth_score"],
                    result["recurrence_span_days"],
                    result["significance_type"],
                    fact_id,
                ))
                scored += 1
            except Exception as e:
                print(f"  [ERROR] Failed to score fact {fact_id}: {e}")
                errors += 1

            if (i + 1) % 100 == 0 or i == total - 1:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"  [{i+1}/{total}] {rate:.0f} facts/sec")

        conn.commit()

        elapsed = time.time() - start_time
        print(f"\nScored {scored} facts in {elapsed:.1f}s")
        if errors:
            print(f"  ({errors} errors — those facts were skipped)")

        # Session 55 (Plan 3): Show windowed vs raw recurrence comparison
        try:
            comparison = conn.execute("""
                SELECT
                    AVG(recurrence_count) as avg_raw,
                    AVG(windowed_recurrence) as avg_windowed,
                    MAX(recurrence_count) as max_raw,
                    MAX(windowed_recurrence) as max_windowed
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND recurrence_count > 0
            """).fetchone()
            if comparison and comparison[0]:
                print(f"\nTemporal dedup comparison:")
                print(f"  Avg raw recurrence:      {comparison[0]:.1f}")
                print(f"  Avg windowed recurrence:  {comparison[1]:.1f}")
                print(f"  Max raw recurrence:      {comparison[2]}")
                print(f"  Max windowed recurrence:  {comparison[3]}")
                if comparison[0] > 0:
                    reduction = (1 - comparison[1] / comparison[0]) * 100
                    print(f"  Reduction:               {reduction:.0f}%")
        except Exception:
            pass  # windowed_recurrence column might not exist yet


# ---------------------------------------------------------------------------
# Edge Pruning
# ---------------------------------------------------------------------------

def run_edge_pruning():
    """Remove fact_relationships edges that point to superseded facts."""
    print("=" * 60)
    print("Edge Pruning (stale relationship cleanup)")
    print("=" * 60)

    with contextlib.closing(get_db()) as conn:
        # Count stale edges before
        stale_1 = conn.execute("""
            SELECT COUNT(*) FROM fact_relationships
            WHERE fact_id_1 IN (SELECT id FROM memory_facts WHERE superseded_by IS NOT NULL)
        """).fetchone()[0]

        stale_2 = conn.execute("""
            SELECT COUNT(*) FROM fact_relationships
            WHERE fact_id_2 IN (SELECT id FROM memory_facts WHERE superseded_by IS NOT NULL)
        """).fetchone()[0]

        total_before = conn.execute("SELECT COUNT(*) FROM fact_relationships").fetchone()[0]
        print(f"\nTotal edges: {total_before}")
        print(f"Stale edges (fact_id_1 superseded): {stale_1}")
        print(f"Stale edges (fact_id_2 superseded): {stale_2}")

        # Delete stale edges
        with conn:
            deleted_1 = conn.execute("""
                DELETE FROM fact_relationships
                WHERE fact_id_1 IN (SELECT id FROM memory_facts WHERE superseded_by IS NOT NULL)
            """).rowcount

            deleted_2 = conn.execute("""
                DELETE FROM fact_relationships
                WHERE fact_id_2 IN (SELECT id FROM memory_facts WHERE superseded_by IS NOT NULL)
            """).rowcount

        total_after = conn.execute("SELECT COUNT(*) FROM fact_relationships").fetchone()[0]

        print(f"\nPruned {deleted_1 + deleted_2} stale edges")
        print(f"Remaining edges: {total_after}")


# ---------------------------------------------------------------------------
# Sentiment Pass
# ---------------------------------------------------------------------------

def add_sentiment_column():
    """Add sentiment column to memory_facts if it doesn't exist."""
    with contextlib.closing(get_db()) as conn:
        try:
            conn.execute("ALTER TABLE memory_facts ADD COLUMN sentiment TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Already exists


def score_sentiment(fact_text: str) -> dict:
    """Ask Qwen for sentiment on a relationship fact."""
    prompt = f"""Given this fact about a person in the user's life: "{fact_text}"
What is the sentiment? Respond with JSON: {{"sentiment": "positive/negative/neutral/mixed", "note": "brief explanation"}}"""

    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200},
        "format": {
            "type": "object",
            "properties": {
                "sentiment": {"type": "string"},
                "note": {"type": "string"}
            },
            "required": ["sentiment", "note"]
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json().get("response", "").strip()
        result = json.loads(raw)
        # Normalize sentiment
        sent = result.get("sentiment", "neutral").lower().strip()
        if sent in ("positive", "negative", "neutral", "mixed"):
            return {"sentiment": sent, "note": result.get("note", "")}
        return {"sentiment": "neutral", "note": result.get("note", "")}
    except Exception as e:
        return {"sentiment": "neutral", "note": f"error: {e}"}


def run_sentiment_pass():
    """Tag relationship-category facts with sentiment."""
    print("=" * 60)
    print("Sentiment Pass (relationship facts)")
    print("=" * 60)

    add_sentiment_column()

    with contextlib.closing(get_db()) as conn:
        # Get relationship facts that don't have sentiment yet
        facts = conn.execute("""
            SELECT id, fact_text
            FROM memory_facts
            WHERE category = 'relationship'
              AND superseded_by IS NULL
              AND (sentiment IS NULL OR sentiment = '')
            ORDER BY confidence DESC
        """).fetchall()

        total = len(facts)
        print(f"\n{total} relationship facts to score for sentiment")

        if total == 0:
            return

        start_time = time.time()
        scored = 0

        for i, (fact_id, fact_text) in enumerate(facts):
            result = score_sentiment(fact_text)

            conn.execute("""
                UPDATE memory_facts SET sentiment = ? WHERE id = ?
            """, (result["sentiment"], fact_id))
            scored += 1

            if (i + 1) % 10 == 0 or i == total - 1:
                elapsed = time.time() - start_time
                print(f"  [{i+1}/{total}] {result['sentiment']}: {fact_text[:60]}...")

        conn.commit()

        # Show distribution
        dist = conn.execute("""
            SELECT sentiment, COUNT(*) FROM memory_facts
            WHERE category = 'relationship' AND superseded_by IS NULL AND sentiment IS NOT NULL
            GROUP BY sentiment ORDER BY COUNT(*) DESC
        """).fetchall()

        print(f"\nSentiment distribution:")
        for sent, count in dist:
            print(f"  {sent:<10} {count:>5}")

        print(f"\nScored {scored} facts in {time.time() - start_time:.1f}s")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def show_stats():
    """Show scoring statistics."""
    with contextlib.closing(get_db()) as conn:
        print("=" * 60)
        print("Fact Scoring Statistics")
        print("=" * 60)

        # Significance distribution
        print("\nSignificance score distribution:")
        for bucket_label, low, high in [
            ("High (7+)", 7, 11),
            ("Medium (4-7)", 4, 7),
            ("Low (1-4)", 1, 4),
            ("Unscored (0)", 0, 0.01),
        ]:
            count = conn.execute("""
                SELECT COUNT(*) FROM memory_facts
                WHERE superseded_by IS NULL
                  AND significance_score >= ? AND significance_score < ?
            """, (low, high)).fetchone()[0]
            print(f"  {bucket_label:<20} {count:>5}")

        # Significance type distribution
        print("\nSignificance type:")
        types = conn.execute("""
            SELECT COALESCE(significance_type, 'unscored'), COUNT(*)
            FROM memory_facts WHERE superseded_by IS NULL
            GROUP BY significance_type ORDER BY COUNT(*) DESC
        """).fetchall()
        for sig_type, count in types:
            print(f"  {sig_type:<20} {count:>5}")

        # Top facts by significance
        print("\nTop 10 facts by significance:")
        top = conn.execute("""
            SELECT fact_text, significance_score, recurrence_count, significance_type
            FROM memory_facts
            WHERE superseded_by IS NULL AND significance_score > 0
            ORDER BY significance_score DESC
            LIMIT 10
        """).fetchall()
        for fact, score, recurrence, sig_type in top:
            print(f"  [{score:>5.1f} | {recurrence:>3}x | {(sig_type or 'unscored'):<10}] {fact[:70]}")

        # Session 55 (Plan 3): Windowed recurrence comparison
        try:
            print("\nRecurrence comparison (raw vs windowed):")
            top_windowed = conn.execute("""
                SELECT fact_text, recurrence_count, windowed_recurrence
                FROM memory_facts
                WHERE superseded_by IS NULL AND recurrence_count > 0
                ORDER BY recurrence_count DESC
                LIMIT 5
            """).fetchall()
            for fact, raw_rec, win_rec in top_windowed:
                win_rec = win_rec or 0
                print(f"  [{raw_rec:>3} raw -> {win_rec:>3} windowed] {fact[:60]}")
        except sqlite3.OperationalError:
            pass  # windowed_recurrence column doesn't exist yet

        # Sentiment distribution (if available)
        try:
            sent_dist = conn.execute("""
                SELECT sentiment, COUNT(*) FROM memory_facts
                WHERE category = 'relationship' AND superseded_by IS NULL AND sentiment IS NOT NULL
                GROUP BY sentiment ORDER BY COUNT(*) DESC
            """).fetchall()
            if sent_dist:
                print("\nRelationship sentiment:")
                for sent, count in sent_dist:
                    print(f"  {sent:<10} {count:>5}")
        except sqlite3.OperationalError:
            pass  # sentiment column doesn't exist yet


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Post-extraction fact scoring (D-015, D-022)")
    parser.add_argument("--score-only", action="store_true", help="Run significance scoring only")
    parser.add_argument("--prune-only", action="store_true", help="Run edge pruning only")
    parser.add_argument("--sentiment", action="store_true", help="Run sentiment pass only (needs Ollama)")
    parser.add_argument("--stats", action="store_true", help="Show scoring statistics")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.score_only:
        run_significance_scoring()
    elif args.prune_only:
        run_edge_pruning()
    elif args.sentiment:
        run_sentiment_pass()
    else:
        # Run all three jobs in sequence
        run_significance_scoring()
        print()
        run_edge_pruning()
        print()
        print("Note: Sentiment pass requires Ollama. Run separately with --sentiment")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
