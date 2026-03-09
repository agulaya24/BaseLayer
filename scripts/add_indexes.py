"""
Add performance indexes to existing database (Session 41).

Safe to run multiple times — uses CREATE INDEX IF NOT EXISTS.
Run once: python scripts/add_indexes.py
"""

import contextlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DATABASE_FILE


def main():
    with contextlib.closing(sqlite3.connect(str(DATABASE_FILE))) as conn:
        # Check current indexes
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        print(f"Existing indexes: {len(existing)}")
        for idx in existing:
            print(f"  {idx[0]}")

        print("\nAdding performance indexes...")

        indexes = [
            ("idx_facts_active", "CREATE INDEX IF NOT EXISTS idx_facts_active ON memory_facts(superseded_by) WHERE superseded_by IS NULL"),
            ("idx_facts_scope", "CREATE INDEX IF NOT EXISTS idx_facts_scope ON memory_facts(scope) WHERE superseded_by IS NULL"),
            ("idx_facts_tier", "CREATE INDEX IF NOT EXISTS idx_facts_tier ON memory_facts(knowledge_tier) WHERE superseded_by IS NULL"),
            ("idx_msg_conversation", "CREATE INDEX IF NOT EXISTS idx_msg_conversation ON messages(conversation_id)"),
            ("idx_msg_role", "CREATE INDEX IF NOT EXISTS idx_msg_role ON messages(role)"),
            ("idx_facts_source_conv", "CREATE INDEX IF NOT EXISTS idx_facts_source_conv ON memory_facts(source_conversation_id)"),
            ("idx_summary_conv", "CREATE INDEX IF NOT EXISTS idx_summary_conv ON conversation_summaries(conversation_id)"),
            ("idx_rel_fact1", "CREATE INDEX IF NOT EXISTS idx_rel_fact1 ON fact_relationships(fact_id_1)"),
            ("idx_rel_fact2", "CREATE INDEX IF NOT EXISTS idx_rel_fact2 ON fact_relationships(fact_id_2)"),
            ("idx_cluster_fact", "CREATE INDEX IF NOT EXISTS idx_cluster_fact ON fact_cluster_assignments(fact_id)"),
            ("idx_extraction_conv", "CREATE INDEX IF NOT EXISTS idx_extraction_conv ON extraction_log(conversation_id)"),
        ]

        for name, sql in indexes:
            conn.execute(sql)
            print(f"  + {name}")

        # Run ANALYZE to update query planner statistics
        print("\nRunning ANALYZE...")
        conn.execute("ANALYZE")
        conn.commit()

        # Verify
        final = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        print(f"\nTotal indexes after: {len(final)}")

    print("Done.")


if __name__ == "__main__":
    main()
