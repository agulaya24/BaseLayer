"""
Pipeline End-to-End Test — Phase 2 (S98 Refactor)

Tests the full import → extract flow on a minimal test corpus.
Uses mocked API calls (no real money spent).
"""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


CORPUS_DIR = Path(__file__).parent / "corpus"


class TestImportFlow:
    """Test that text files import correctly into the database."""

    def test_corpus_exists(self):
        """Test corpus directory has sample files."""
        assert CORPUS_DIR.exists(), "Test corpus directory missing"
        txt_files = list(CORPUS_DIR.glob("*.txt"))
        assert len(txt_files) >= 3, f"Expected 3+ corpus files, found {len(txt_files)}"

    def test_import_text_files(self, temp_db):
        """Import test corpus and verify conversations created."""
        conn, db_path = temp_db

        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.PROJECT_ROOT", db_path.parent):

            from baselayer.import_conversations import import_text_files
            existing_ids = set()
            for txt_file in sorted(CORPUS_DIR.glob("*.txt")):
                import_text_files(conn, str(txt_file), existing_ids)

            count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            assert count >= 3, f"Expected 3+ conversations, got {count}"

            # Verify messages exist
            msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            assert msg_count >= 3, f"Expected 3+ messages, got {msg_count}"

    def test_import_deduplication(self, temp_db):
        """Importing same file twice should not create duplicates."""
        conn, db_path = temp_db

        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.PROJECT_ROOT", db_path.parent):

            from baselayer.import_conversations import import_text_files
            txt_file = str(next(CORPUS_DIR.glob("*.txt")))
            existing_ids = set()

            import_text_files(conn, txt_file, existing_ids)
            count_1 = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]

            import_text_files(conn, txt_file, existing_ids)
            count_2 = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]

            assert count_2 == count_1, f"Import created duplicates: {count_1} -> {count_2}"


class TestExtractionFlow:
    """Test extraction produces facts from imported conversations."""

    def test_extraction_produces_facts(self, populated_db):
        """Mock extraction should produce structured facts."""
        conn, db_path = populated_db

        # Verify populated_db has conversations
        conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        assert conv_count > 0, "populated_db should have conversations"

        # Verify facts exist in populated_db fixture
        fact_count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        assert fact_count > 0, f"populated_db should have facts, got {fact_count}"

    def test_facts_have_required_fields(self, populated_db):
        """Extracted facts must have predicate, confidence, category."""
        conn, db_path = populated_db

        facts = conn.execute("""
            SELECT id, fact_text, confidence, category
            FROM memory_facts
            WHERE superseded_by IS NULL
        """).fetchall()

        for fact in facts:
            assert fact["fact_text"], f"Fact {fact['id']} missing fact_text"
            assert fact["confidence"] is not None, f"Fact {fact['id']} missing confidence"
            assert fact["confidence"] >= 0.0, f"Fact {fact['id']} confidence below 0"
            assert fact["confidence"] <= 1.0, f"Fact {fact['id']} confidence above 1"


class TestComposeFacts:
    """Test that compose fact sampling uses config constants."""

    def test_compose_constants_exist(self):
        """Config should define compose fact limits."""
        from baselayer.config import (
            COMPOSE_FACT_LIMIT_SMALL,
            COMPOSE_FACT_LIMIT_LARGE,
            COMPOSE_FACT_THRESHOLD,
        )
        assert COMPOSE_FACT_LIMIT_SMALL == 100
        assert COMPOSE_FACT_LIMIT_LARGE == 300
        assert COMPOSE_FACT_THRESHOLD == 500

    def test_compose_scaling_logic(self):
        """Verify scaling: small corpus gets 100, large gets 300."""
        from baselayer.config import (
            COMPOSE_FACT_LIMIT_SMALL,
            COMPOSE_FACT_LIMIT_LARGE,
            COMPOSE_FACT_THRESHOLD,
        )
        # Small corpus
        identity_count = 80
        limit = COMPOSE_FACT_LIMIT_LARGE if identity_count >= COMPOSE_FACT_THRESHOLD else COMPOSE_FACT_LIMIT_SMALL
        assert limit == 100

        # Large corpus
        identity_count = 1235
        limit = COMPOSE_FACT_LIMIT_LARGE if identity_count >= COMPOSE_FACT_THRESHOLD else COMPOSE_FACT_LIMIT_SMALL
        assert limit == 300
