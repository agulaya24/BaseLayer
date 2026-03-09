"""
Backfill fact_class (event/state) for existing unclassified facts.

Phase 1 of temporal processing — one-time operation.
Heuristic pass handles clear categories, exports ambiguous facts for Opus review.

Run: python backfill_fact_class.py --heuristic       # Apply safe heuristic rules
     python backfill_fact_class.py --import-opus FILE # Import Opus classifications
     python backfill_fact_class.py --stats            # Show classification progress
     python backfill_fact_class.py --export-batch N   # Export batch N for Opus review
     python backfill_fact_class.py --export-all       # Export all unclassified for Opus
"""

import contextlib
import sys
import io
import sqlite3
import json
import argparse
import re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import DATABASE_FILE, PROJECT_ROOT

BATCH_SIZE = 200  # Facts per Opus batch
EXPORT_DIR = PROJECT_ROOT / "data" / "backfill"


# ---------------------------------------------------------------------------
# Heuristic Classification Rules
# ---------------------------------------------------------------------------

# Categories that are definitionally states (mutable conditions)
STATE_CATEGORIES = {
    "habit", "preference", "opinion", "goal", "negative_trait",
    "interest", "value", "skill", "project", "relationship", "unknown"
}

# Keywords strongly indicating events (immutable anchors)
EVENT_KEYWORDS = [
    r"\bfounded\b", r"\bco-founded\b", r"\bmarried\b", r"\bgot married\b",
    r"\bgraduated\b", r"\bborn\b", r"\bdied\b", r"\bpassed away\b",
    r"\blost (a|his|her|their) (parent|father|mother|brother|sister|friend|job|company)",
    r"\bshipped\b", r"\blaunched\b", r"\bdeployed\b",
    r"\bwon\b", r"\bachieved\b", r"\bcompleted\b",
    r"\braised \$", r"\bsold (the|his|her|their)\b",
    r"\bmoved (to|from)\b", r"\bimmigrated\b", r"\bemigrated\b",
    r"\bhired\b", r"\bfired\b", r"\blaid off\b", r"\bquit\b", r"\bresigned\b",
    r"\bstarted (a|the|his|her|their) (company|business|startup|fund|firm)\b",
    r"\bran out of (money|funding|runway)\b",
    r"\bhad a wedding\b", r"\bwedding celebration\b",
]
EVENT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in EVENT_KEYWORDS]

# Keywords strongly indicating states (mutable conditions)
STATE_KEYWORDS = [
    r"\bcurrently\b", r"\bis (building|working on|developing|creating)\b",
    r"\blives in\b", r"\bbased in\b", r"\bresides in\b",
    r"\bworks at\b", r"\bworks for\b", r"\bemployed at\b",
    r"\buses\b", r"\bprefers\b", r"\bfavors\b",
    r"\bwakes (up )?at\b", r"\bsleeps\b",
    r"\btrades\b", r"\bis trading\b",
    r"\bdrives (a|an)\b", r"\bowns (a|an)\b",
    r"\bis interested in\b", r"\bis learning\b",
    r"\bis planning\b", r"\bwants to\b",
]
STATE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in STATE_KEYWORDS]


def classify_heuristic(fact_text, category, temporal_state, intent):
    """
    Classify a fact as event/state using safe heuristic rules.
    Returns (class, confidence) or (None, None) if ambiguous.

    Only classifies when confidence is high. Ambiguous cases
    are left for Opus review.
    """
    # Rule 1: Categories that are definitionally states
    if category in STATE_CATEGORIES:
        return "state", "high"

    # Rule 2: Historical intent → likely event
    if intent == "historical" and temporal_state == "past":
        return "event", "high"

    # Rule 3: Keyword-based event detection
    for pattern in EVENT_PATTERNS:
        if pattern.search(fact_text):
            return "event", "medium"

    # Rule 4: Keyword-based state detection
    for pattern in STATE_PATTERNS:
        if pattern.search(fact_text):
            return "state", "medium"

    # Rule 5: Category + temporal heuristics
    if category == "biography" and temporal_state == "past":
        return "event", "medium"

    # Can't classify with confidence
    return None, None


def run_heuristic_pass(dry_run=False):
    """Apply safe heuristic rules to classify obvious facts."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        rows = conn.execute("""
            SELECT id, fact_text, category, temporal_state, intent
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND (fact_class IS NULL OR fact_class = 'unclassified')
        """).fetchall()

        stats = {"event": 0, "state": 0, "skipped": 0, "high": 0, "medium": 0}
        updates = []

        for fact_id, fact_text, category, temporal_state, intent in rows:
            fc, confidence = classify_heuristic(
                fact_text, category or "unknown",
                temporal_state or "unknown", intent or "does"
            )
            if fc:
                stats[fc] += 1
                stats[confidence] += 1
                updates.append((fc, fact_id))
            else:
                stats["skipped"] += 1

        print(f"Heuristic classification results:")
        print(f"  Events:  {stats['event']}")
        print(f"  States:  {stats['state']}")
        print(f"  Skipped: {stats['skipped']} (need Opus review)")
        print(f"  Confidence: {stats['high']} high, {stats['medium']} medium")

        if not dry_run and updates:
            with conn:
                for fc, fact_id in updates:
                    conn.execute(
                        "UPDATE memory_facts SET fact_class = ? WHERE id = ?",
                        (fc, fact_id)
                    )
            print(f"\nApplied {len(updates)} classifications to database.")
        elif dry_run:
            print(f"\n[DRY RUN] Would apply {len(updates)} classifications.")

    return stats


def export_for_opus(batch_num=None):
    """Export unclassified facts for Opus review in batches."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        rows = conn.execute("""
            SELECT id, fact_text, category, temporal_state, intent
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND (fact_class IS NULL OR fact_class = 'unclassified')
            ORDER BY category, fact_text
        """).fetchall()

        if not rows:
            print("No unclassified facts remaining.")
            return

        total = len(rows)
        num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Total unclassified: {total} ({num_batches} batches of {BATCH_SIZE})")

        if batch_num is not None:
            # Export single batch
            start = batch_num * BATCH_SIZE
            end = min(start + BATCH_SIZE, total)
            batch_rows = rows[start:end]
            if not batch_rows:
                print(f"Batch {batch_num} is empty (only {num_batches} batches exist).")
                return

            batch_data = [
                {"id": r[0], "fact": r[1], "category": r[2],
                 "temporal": r[3], "intent": r[4]}
                for r in batch_rows
            ]

            outfile = EXPORT_DIR / f"opus_batch_{batch_num}.json"
            with open(outfile, "w", encoding="utf-8") as f:
                json.dump(batch_data, f, indent=2, ensure_ascii=False)
            print(f"Exported batch {batch_num}: {len(batch_data)} facts -> {outfile}")
        else:
            # Export all batches
            for i in range(num_batches):
                start = i * BATCH_SIZE
                end = min(start + BATCH_SIZE, total)
                batch_rows = rows[start:end]

                batch_data = [
                    {"id": r[0], "fact": r[1], "category": r[2],
                     "temporal": r[3], "intent": r[4]}
                    for r in batch_rows
                ]

                outfile = EXPORT_DIR / f"opus_batch_{i}.json"
                with open(outfile, "w", encoding="utf-8") as f:
                    json.dump(batch_data, f, indent=2, ensure_ascii=False)

            print(f"Exported {num_batches} batches to {EXPORT_DIR}/")


def import_opus_results(filepath):
    """Import Opus classification results from a JSON file.

    Expected format: list of {"id": "...", "fact_class": "event"|"state"}
    or: {"classifications": [{"id": "...", "fact_class": "event"|"state"}]}
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both flat list and wrapped formats
    if isinstance(data, dict):
        data = data.get("classifications", data.get("results", []))

    if not isinstance(data, list):
        print(f"ERROR: Expected a list, got {type(data)}")
        return

    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        applied = 0
        errors = 0

        for item in data:
            fact_id = item.get("id")
            fact_class = item.get("fact_class", "").strip().lower()

            if not fact_id or fact_class not in ("event", "state"):
                errors += 1
                continue

            conn.execute(
                "UPDATE memory_facts SET fact_class = ? WHERE id = ?",
                (fact_class, fact_id)
            )
            applied += 1

        conn.commit()

    print(f"Imported: {applied} classifications applied, {errors} errors/skipped")


def show_stats():
    """Show current fact_class distribution."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        total_active = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]

        rows = conn.execute("""
            SELECT COALESCE(fact_class, 'unclassified') as fc, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY fc
            ORDER BY cnt DESC
        """).fetchall()

        print(f"Fact Classification Status ({total_active} active facts):")
        print()
        for fc, cnt in rows:
            pct = cnt / total_active * 100
            bar = "#" * int(pct / 2)
            print(f"  {fc:<15} {cnt:>5} ({pct:5.1f}%) {bar}")

        # Breakdown of unclassified by category
        unclassified = conn.execute("""
            SELECT category, COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL AND (fact_class IS NULL OR fact_class = 'unclassified')
            GROUP BY category ORDER BY COUNT(*) DESC
        """).fetchall()

        if unclassified:
            print(f"\nUnclassified by category:")
            for cat, cnt in unclassified:
                print(f"  {cat:<15} {cnt:>5}")


def main():
    parser = argparse.ArgumentParser(description="Backfill fact_class for existing facts")
    parser.add_argument("--heuristic", action="store_true",
                        help="Apply safe heuristic classification rules")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview heuristic results without writing to DB")
    parser.add_argument("--export-all", action="store_true",
                        help="Export all unclassified facts for Opus review")
    parser.add_argument("--export-batch", type=int, metavar="N",
                        help="Export a specific batch for Opus review")
    parser.add_argument("--import-opus", type=str, metavar="FILE",
                        help="Import Opus classification results from JSON file")
    parser.add_argument("--stats", action="store_true",
                        help="Show classification progress")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.heuristic:
        run_heuristic_pass(dry_run=args.dry_run)
    elif args.export_all:
        export_for_opus()
    elif args.export_batch is not None:
        export_for_opus(batch_num=args.export_batch)
    elif args.import_opus:
        import_opus_results(args.import_opus)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
