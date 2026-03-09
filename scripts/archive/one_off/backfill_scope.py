"""
Backfill scope on existing facts (D-044, D-048).

Sets scope based on source_conversation_id → conversations.source → SCOPE_SOURCE_MAPPING.
Existing facts likely have scope=NULL because store_fact() wasn't setting it before D-048.

Run once: python scripts/backfill_scope.py
"""

import contextlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DATABASE_FILE, SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE


def main():
    with contextlib.closing(sqlite3.connect(str(DATABASE_FILE))) as conn:
        # Show current state
        rows = conn.execute("""
            SELECT COALESCE(scope, 'NULL') as s, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY s ORDER BY cnt DESC
        """).fetchall()
        print("Current scope distribution (active facts):")
        for s, cnt in rows:
            print(f"  {s:<15} {cnt:>5}")

        # Count facts needing backfill
        null_count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE scope IS NULL"
        ).fetchone()[0]

        if null_count == 0:
            print("\nAll facts already have scope set. Nothing to do.")
            return

        print(f"\n{null_count} facts have NULL scope. Backfilling...")

        # Update scope based on conversation source
        with conn:
            for source, scope in SCOPE_SOURCE_MAPPING.items():
                updated = conn.execute("""
                    UPDATE memory_facts
                    SET scope = ?
                    WHERE scope IS NULL
                      AND source_conversation_id IN (
                          SELECT id FROM conversations WHERE source = ?
                      )
                """, (scope, source)).rowcount
                if updated > 0:
                    print(f"  {source} -> {scope}: {updated} facts")

            # Set default scope for any remaining NULL (e.g., text_file, journal, unknown source)
            remaining = conn.execute("""
                UPDATE memory_facts
                SET scope = ?
                WHERE scope IS NULL
            """, (DEFAULT_SCOPE,)).rowcount
            if remaining > 0:
                print(f"  (other sources) -> {DEFAULT_SCOPE}: {remaining} facts")

        # Show updated state
        rows = conn.execute("""
            SELECT COALESCE(scope, 'NULL') as s, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY s ORDER BY cnt DESC
        """).fetchall()
        print("\nUpdated scope distribution (active facts):")
        for s, cnt in rows:
            print(f"  {s:<15} {cnt:>5}")

        print("\nDone.")


if __name__ == "__main__":
    main()
