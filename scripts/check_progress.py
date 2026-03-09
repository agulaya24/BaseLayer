"""
Quick status check — run this anytime to see overnight pipeline results.
Usage: python scripts/check_progress.py
"""

import contextlib
import sqlite3
from datetime import datetime

from config import DATABASE_FILE, PROJECT_ROOT

LOG_FILE = PROJECT_ROOT / "data" / "overnight_run.log"


def main():
    print("=" * 60)
    print("OVERNIGHT RUN STATUS CHECK")
    print("=" * 60)

    # Check log file
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        print(f"\nLog file: {len(lines)} lines")
        print("Last 5 log entries:")
        for line in lines[-5:]:
            print(f"  {line}")
    else:
        print("\nNo log file found (pipeline may not have started)")

    # Check database
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        # Summaries
        try:
            count = conn.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()[0]
            total_convos = conn.execute("SELECT COUNT(*) FROM conversations WHERE message_count >= 3").fetchone()[0]
            print(f"\nSummaries: {count}/{total_convos} conversations")
        except sqlite3.OperationalError:
            print("\nSummaries: table not created yet")

        # Topic scores
        try:
            count = conn.execute("SELECT COUNT(*) FROM topic_scores").fetchone()[0]
            print(f"Topic scores: {count} topics scored")
            if count > 0:
                rows = conn.execute("SELECT topic, final_score, significance_type FROM topic_scores ORDER BY final_score DESC").fetchall()
                for topic, score, sig_type in rows:
                    print(f"  {topic}: {score}/10 ({sig_type})")
        except sqlite3.OperationalError:
            print("Topic scores: table not created yet")

        # Facts
        try:
            total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
            print(f"Facts: {total} total ({active} active)")

            # By category
            categories = conn.execute("""
                SELECT category, COUNT(*) as cnt FROM memory_facts
                WHERE superseded_by IS NULL GROUP BY category ORDER BY cnt DESC
            """).fetchall()
            if categories:
                print("  By category:")
                for cat, cnt in categories:
                    print(f"    {cat or 'unknown':<15} {cnt}")
        except sqlite3.OperationalError:
            print("Facts: table not created yet")

        # Extraction progress
        try:
            processed = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
            total_convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            print(f"Extraction progress: {processed}/{total_convos} conversations")
        except sqlite3.OperationalError:
            print("Extraction log: table not created yet")

        # Relationships
        try:
            rels = conn.execute("SELECT COUNT(*) FROM fact_relationships").fetchone()[0]
            print(f"Fact relationships: {rels} co-occurrence edges")
        except sqlite3.OperationalError:
            pass

    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
