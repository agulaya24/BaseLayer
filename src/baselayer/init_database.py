"""
Initialize a clean memory system database.

Creates all tables needed by the pipeline. Used for:
  - New user data isolation (multi-user support)
  - Fresh re-extraction runs
  - Multi-user deployments

Usage:
  python init_database.py                          # Initialize default DB
  MEMORY_SYSTEM_ROOT=/path/to/root python init_database.py  # Initialize isolated DB
"""

import contextlib
import sqlite3
import sys
import os
import stat

from baselayer.config import DATABASE_FILE, PROJECT_ROOT


def _set_restrictive_permissions(path):
    """Set restrictive directory permissions (owner-only). No-op on Windows."""
    try:
        os.chmod(str(path), stat.S_IRWXU)  # 0o700: rwx for owner only
    except (OSError, NotImplementedError):
        pass  # Windows or unsupported filesystem — skip silently


def init_database(db_path=None):
    if db_path is None:
        db_path = DATABASE_FILE

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _set_restrictive_permissions(db_path.parent)

    with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript("""
            -- Core conversation storage
            CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at REAL,
            updated_at REAL,
            message_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'chatgpt'
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            parent_id TEXT,
            role TEXT,
            content_text TEXT,
            content_type TEXT,
            created_at REAL,
            sequence_order INTEGER,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            summary TEXT,
            created_at REAL,
            model_used TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        -- Fact storage
        CREATE TABLE IF NOT EXISTS memory_facts (
            id TEXT PRIMARY KEY,
            fact_text TEXT NOT NULL,
            category TEXT,
            confidence REAL,
            surprise_score REAL,
            significance_score REAL,
            recurrence_count INTEGER DEFAULT 0,
            depth_score REAL DEFAULT 0,
            recurrence_span_days INTEGER DEFAULT 0,
            significance_type TEXT,
            source_conversation_id TEXT,
            created_at REAL,
            updated_at REAL,
            superseded_by TEXT,
            source TEXT DEFAULT 'extraction',
            subject TEXT DEFAULT 'user',
            intent TEXT DEFAULT 'does',
            temporal_state TEXT DEFAULT 'unknown',
            raw_llm_confidence REAL,
            sentiment TEXT,
            fact_class TEXT DEFAULT 'unclassified',
            knowledge_tier TEXT,
            tiered_by TEXT,
            scope TEXT,
            windowed_recurrence INTEGER DEFAULT 0,
            fact_type TEXT DEFAULT 'unclassified',
            commitment_depth TEXT DEFAULT 'unclassified',
            predicate TEXT,
            object_text TEXT,
            qualifier TEXT,
            FOREIGN KEY (source_conversation_id) REFERENCES conversations(id)
        );

        -- Fact relationships (co-occurrence)
        CREATE TABLE IF NOT EXISTS fact_relationships (
            fact_id_1 TEXT,
            fact_id_2 TEXT,
            co_occurrence_count INTEGER DEFAULT 1,
            source_conversation_id TEXT,
            PRIMARY KEY (fact_id_1, fact_id_2)
        );

        -- Fact cluster assignments (D-026)
        CREATE TABLE IF NOT EXISTS fact_cluster_assignments (
            fact_id TEXT NOT NULL,
            cluster_key TEXT NOT NULL,
            similarity REAL,
            assigned_at REAL,
            PRIMARY KEY (fact_id, cluster_key),
            FOREIGN KEY (fact_id) REFERENCES memory_facts(id)
        );

        -- Epistemic anchors
        CREATE TABLE IF NOT EXISTS epistemic_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_number INTEGER NOT NULL,
            anchor_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            formulation_version INTEGER DEFAULT 1,
            original_text TEXT,
            review_notes TEXT,
            session_confirmed INTEGER,
            source_fact_ids TEXT,
            layer TEXT DEFAULT 'core',
            created_at REAL,
            superseded_by INTEGER,
            updated_at REAL,
            FOREIGN KEY (superseded_by) REFERENCES epistemic_anchors(id)
        );

        -- Identity blocks (legacy single-block + new three-layer)
        CREATE TABLE IF NOT EXISTS identity_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_text TEXT NOT NULL,
            token_count INTEGER,
            fact_ids TEXT,
            created_at REAL,
            approved INTEGER DEFAULT 0,
            notes TEXT
        );

        -- Brief assembly log
        CREATE TABLE IF NOT EXISTS brief_assembly_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT,
            identity_tokens INTEGER,
            theme_tokens INTEGER,
            episode_tokens INTEGER,
            total_tokens INTEGER,
            facts_used INTEGER,
            episodes_used INTEGER,
            assembly_time_ms REAL,
            created_at REAL
        );

        -- Extraction tracking
        CREATE TABLE IF NOT EXISTS extraction_log (
            conversation_id TEXT PRIMARY KEY,
            facts_extracted INTEGER,
            processed_at REAL
        );

        -- User corrections
        CREATE TABLE IF NOT EXISTS user_corrections (
            id TEXT PRIMARY KEY,
            correction_type TEXT NOT NULL,
            original_fact_id TEXT,
            original_fact_text TEXT,
            corrected_fact_text TEXT,
            corrected_category TEXT,
            corrected_subject TEXT,
            annotation TEXT,
            match_patterns TEXT,
            created_at REAL NOT NULL,
            notes TEXT
        );

        -- Turn pairs (Phase 4)
        CREATE TABLE IF NOT EXISTS turn_pairs (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            user_message_id TEXT,
            assistant_message_id TEXT,
            user_text TEXT,
            assistant_text TEXT,
            combined_text TEXT,
            pair_order INTEGER,
            created_at REAL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        -- Topic scores
        CREATE TABLE IF NOT EXISTS topic_scores (
            topic TEXT PRIMARY KEY,
            keywords TEXT,
            recurrence INTEGER,
            depth_score REAL,
            span_days INTEGER,
            significance_type TEXT,
            recurrence_floor INTEGER,
            novelty_score REAL,
            weighted_score REAL,
            llm_score REAL,
            final_score REAL,
            category TEXT,
            reasoning TEXT,
            computed_at REAL
        );

        -- Provenance: links layer claims to supporting facts (S56)
        CREATE TABLE IF NOT EXISTS layer_claim_provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            layer_name TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            claim_text TEXT,
            fact_id TEXT,
            link_method TEXT DEFAULT 'authoring',
            similarity_score REAL,
            rank_in_claim INTEGER,
            layer_version TEXT,
            cycle_id TEXT,
            created_at REAL,
            FOREIGN KEY (fact_id) REFERENCES memory_facts(id)
        );

        -- Claim verification: binary verification questions per claim (S57)
        CREATE TABLE IF NOT EXISTS claim_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL,
            layer_name TEXT NOT NULL,
            verification_type TEXT NOT NULL,
            question TEXT NOT NULL,
            result INTEGER,
            evidence TEXT,
            verified_at REAL,
            layer_version TEXT,
            cycle_id TEXT
        );
        """)

        # FTS5 full-text search on fact_text (Session 57 — C11)
        # Enables fast keyword search via MATCH instead of LIKE '%query%'
        # content= syncs with memory_facts; triggers keep index up to date.
        # Note: memory_facts uses TEXT primary keys, but FTS5 content_rowid
        # requires integer rowids. SQLite auto-assigns integer rowids to all
        # tables (accessible via the implicit "rowid" column), so we use that.
        try:
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts USING fts5(
                    fact_text,
                    content='memory_facts',
                    content_rowid='rowid'
                );

                -- Triggers to keep FTS5 index in sync with memory_facts
                CREATE TRIGGER IF NOT EXISTS memory_facts_ai AFTER INSERT ON memory_facts BEGIN
                    INSERT INTO memory_facts_fts(rowid, fact_text) VALUES (new.rowid, new.fact_text);
                END;

                CREATE TRIGGER IF NOT EXISTS memory_facts_ad AFTER DELETE ON memory_facts BEGIN
                    INSERT INTO memory_facts_fts(memory_facts_fts, rowid, fact_text) VALUES('delete', old.rowid, old.fact_text);
                END;

                CREATE TRIGGER IF NOT EXISTS memory_facts_au AFTER UPDATE ON memory_facts BEGIN
                    INSERT INTO memory_facts_fts(memory_facts_fts, rowid, fact_text) VALUES('delete', old.rowid, old.fact_text);
                    INSERT INTO memory_facts_fts(rowid, fact_text) VALUES (new.rowid, new.fact_text);
                END;
            """)
        except sqlite3.OperationalError:
            pass  # FTS5 not available in this SQLite build — skip gracefully

        # Performance indexes (added Session 41)
        conn.executescript("""
            -- Active facts (most common query pattern across all scripts)
            CREATE INDEX IF NOT EXISTS idx_facts_active
                ON memory_facts(superseded_by) WHERE superseded_by IS NULL;

            -- Scope filtering (D-048 scoped extraction + authoring)
            CREATE INDEX IF NOT EXISTS idx_facts_scope
                ON memory_facts(scope) WHERE superseded_by IS NULL;

            -- Knowledge tier queries (author_layers.py, reclassify_tiers.py)
            CREATE INDEX IF NOT EXISTS idx_facts_tier
                ON memory_facts(knowledge_tier) WHERE superseded_by IS NULL;

            -- Foreign key: messages by conversation (used everywhere)
            CREATE INDEX IF NOT EXISTS idx_msg_conversation
                ON messages(conversation_id);

            -- Message role filtering (stats, extraction)
            CREATE INDEX IF NOT EXISTS idx_msg_role
                ON messages(role);

            -- Foreign key: facts by source conversation (episode retrieval, extraction)
            CREATE INDEX IF NOT EXISTS idx_facts_source_conv
                ON memory_facts(source_conversation_id);

            -- Conversation summaries by conversation_id (episode retrieval)
            CREATE INDEX IF NOT EXISTS idx_summary_conv
                ON conversation_summaries(conversation_id);

            -- Fact relationships (associative boost in assemble_brief.py)
            CREATE INDEX IF NOT EXISTS idx_rel_fact1
                ON fact_relationships(fact_id_1);
            CREATE INDEX IF NOT EXISTS idx_rel_fact2
                ON fact_relationships(fact_id_2);

            -- Cluster assignments by fact (retrieval)
            CREATE INDEX IF NOT EXISTS idx_cluster_fact
                ON fact_cluster_assignments(fact_id);

            -- Extraction log lookup
            CREATE INDEX IF NOT EXISTS idx_extraction_conv
                ON extraction_log(conversation_id);

            -- Provenance: claim lookup and fact lookup (S56)
            CREATE INDEX IF NOT EXISTS idx_provenance_claim
                ON layer_claim_provenance(layer_name, claim_id);
            CREATE INDEX IF NOT EXISTS idx_provenance_fact
                ON layer_claim_provenance(fact_id);

            -- Claim verification: claim lookup (S57)
            CREATE INDEX IF NOT EXISTS idx_verification_claim
                ON claim_verification(layer_name, claim_id);
        """)

        conn.commit()

        # Verify — exclude sqlite internals and FTS5 shadow tables
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [
            t[0] for t in tables
            if t[0] != 'sqlite_sequence'
            and not t[0].startswith('memory_facts_fts_')  # FTS5 shadow tables
        ]
    return table_names


def main():
    print(f"Initializing database at: {DATABASE_FILE}")
    print(f"Project root: {PROJECT_ROOT}")
    tables = init_database()
    print(f"\nCreated {len(tables)} tables:")
    for t in tables:
        print(f"  - {t}")
    print("\nDone.")


if __name__ == "__main__":
    main()
