"""
Data integrity tests for Base Layer.

Tests: schema validation, foreign keys, supersession chains, token budget compliance.
"""

import pytest
import sqlite3
import sys
from pathlib import Path



EXPECTED_TABLES = [
    "brief_assembly_log",
    "claim_verification",
    "conversation_summaries",
    "conversations",
    "epistemic_anchors",
    "extraction_log",
    "fact_cluster_assignments",
    "fact_relationships",
    "identity_blocks",
    "layer_claim_provenance",
    "memory_facts",
    "messages",
    "schema_version",
    "subjects",
    "topic_scores",
    "turn_pairs",
    "user_corrections",
]


class TestSchemaValidation:
    """Validate the SQLite schema matches expectations."""

    def test_all_tables_exist(self, temp_db):
        conn, _ = temp_db
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
        ).fetchall()
        table_names = sorted([t[0] for t in tables])
        # Filter out FTS virtual tables which may vary by SQLite build
        core_tables = sorted([t for t in table_names if not t.startswith("memory_facts_fts")])
        assert core_tables == sorted(EXPECTED_TABLES)

    def test_conversations_columns(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(conversations)").fetchall()
        cols = {row[1]: row[2] for row in info}  # name -> type
        assert "id" in cols
        assert "title" in cols
        assert "created_at" in cols
        assert "source" in cols
        assert "message_count" in cols

    def test_messages_columns(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(messages)").fetchall()
        cols = {row[1] for row in info}
        required = {"id", "conversation_id", "role", "content_text", "created_at", "sequence_order"}
        assert required.issubset(cols)

    def test_memory_facts_columns(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(memory_facts)").fetchall()
        cols = {row[1] for row in info}
        required = {
            "id", "fact_text", "category", "confidence", "surprise_score",
            "significance_score", "recurrence_count", "depth_score",
            "source_conversation_id", "created_at", "superseded_by",
            "fact_class", "knowledge_tier", "scope", "fact_type",
            "commitment_depth", "subject", "intent", "temporal_state",
        }
        assert required.issubset(cols), f"Missing: {required - cols}"

    def test_epistemic_anchors_columns(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(epistemic_anchors)").fetchall()
        cols = {row[1] for row in info}
        required = {"id", "anchor_number", "anchor_text", "status", "source_fact_ids"}
        assert required.issubset(cols)

    def test_user_corrections_columns(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(user_corrections)").fetchall()
        cols = {row[1] for row in info}
        required = {"id", "correction_type", "original_fact_id", "corrected_fact_text"}
        assert required.issubset(cols)

    def test_extraction_log_columns(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(extraction_log)").fetchall()
        cols = {row[1] for row in info}
        assert {"conversation_id", "facts_extracted", "processed_at"}.issubset(cols)


class TestForeignKeys:
    """Test referential integrity constraints."""

    def test_messages_reference_conversations(self, populated_db):
        conn, _ = populated_db
        # All message conversation_ids should exist in conversations
        orphans = conn.execute("""
            SELECT m.id FROM messages m
            LEFT JOIN conversations c ON m.conversation_id = c.id
            WHERE c.id IS NULL
        """).fetchall()
        assert len(orphans) == 0, f"Orphaned messages: {[o[0] for o in orphans]}"

    def test_facts_reference_conversations(self, populated_db):
        conn, _ = populated_db
        orphans = conn.execute("""
            SELECT mf.id FROM memory_facts mf
            LEFT JOIN conversations c ON mf.source_conversation_id = c.id
            WHERE c.id IS NULL AND mf.source_conversation_id IS NOT NULL
        """).fetchall()
        assert len(orphans) == 0, f"Orphaned facts: {[o[0] for o in orphans]}"


class TestSupersessionChains:
    """Validate supersession chain integrity."""

    def test_no_circular_supersession(self, populated_db):
        """No fact should supersede itself or create a cycle."""
        conn, _ = populated_db
        facts = conn.execute(
            "SELECT id, superseded_by FROM memory_facts WHERE superseded_by IS NOT NULL"
        ).fetchall()

        for fact_id, superseded_by in facts:
            assert fact_id != superseded_by, f"Self-supersession: {fact_id}"
            # Check for 2-step cycles
            next_sup = conn.execute(
                "SELECT superseded_by FROM memory_facts WHERE id = ?",
                (superseded_by,)
            ).fetchone()
            if next_sup and next_sup[0]:
                assert next_sup[0] != fact_id, f"Cycle: {fact_id} -> {superseded_by} -> {fact_id}"

    def test_superseded_by_references_existing_fact(self, populated_db):
        """superseded_by should point to an existing fact."""
        conn, _ = populated_db
        broken = conn.execute("""
            SELECT mf.id, mf.superseded_by FROM memory_facts mf
            LEFT JOIN memory_facts target ON mf.superseded_by = target.id
            WHERE mf.superseded_by IS NOT NULL AND target.id IS NULL
        """).fetchall()
        assert len(broken) == 0, f"Broken supersession refs: {broken}"

    def test_active_facts_have_no_supersession(self, populated_db):
        """Active facts should have superseded_by = NULL."""
        conn, _ = populated_db
        active = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        assert active > 0


class TestTokenBudgetCompliance:
    """Verify token budget constants are consistent."""

    def test_total_equals_sum_of_parts(self):
        from baselayer.config import (
            IDENTITY_TOKEN_BUDGET, THEME_TOKEN_BUDGET,
            EPISODE_TOKEN_BUDGET, TOTAL_TOKEN_BUDGET,
        )
        # Total should be >= sum (allows some overhead)
        part_sum = IDENTITY_TOKEN_BUDGET + THEME_TOKEN_BUDGET + EPISODE_TOKEN_BUDGET
        assert TOTAL_TOKEN_BUDGET >= part_sum - 100  # Allow 100 token slack
        assert TOTAL_TOKEN_BUDGET <= part_sum + 200  # But not wildly more

    def test_identity_budget_is_largest(self):
        from baselayer.config import IDENTITY_TOKEN_BUDGET, THEME_TOKEN_BUDGET, EPISODE_TOKEN_BUDGET
        assert IDENTITY_TOKEN_BUDGET > THEME_TOKEN_BUDGET
        assert IDENTITY_TOKEN_BUDGET > EPISODE_TOKEN_BUDGET

    def test_budgets_are_reasonable(self):
        from baselayer.config import TOTAL_TOKEN_BUDGET
        # Should be between 1K and 10K tokens
        assert 1000 <= TOTAL_TOKEN_BUDGET <= 10000


class TestDataConsistency:
    """Test data consistency in populated database."""

    def test_fact_categories_are_valid(self, populated_db):
        from baselayer.config import VALID_CATEGORIES
        conn, _ = populated_db
        categories = conn.execute(
            "SELECT DISTINCT category FROM memory_facts WHERE category IS NOT NULL"
        ).fetchall()
        for (cat,) in categories:
            assert cat in VALID_CATEGORIES, f"Invalid category: {cat}"

    def test_fact_types_are_valid(self, populated_db):
        from baselayer.config import VALID_FACT_TYPES
        conn, _ = populated_db
        types = conn.execute(
            "SELECT DISTINCT fact_type FROM memory_facts WHERE fact_type IS NOT NULL"
        ).fetchall()
        for (ft,) in types:
            assert ft in VALID_FACT_TYPES, f"Invalid fact_type: {ft}"

    def test_commitment_depths_are_valid(self, populated_db):
        from baselayer.config import VALID_COMMITMENT_DEPTHS
        conn, _ = populated_db
        depths = conn.execute(
            "SELECT DISTINCT commitment_depth FROM memory_facts WHERE commitment_depth IS NOT NULL"
        ).fetchall()
        for (cd,) in depths:
            assert cd in VALID_COMMITMENT_DEPTHS, f"Invalid commitment_depth: {cd}"

    def test_fact_classes_are_valid(self, populated_db):
        from baselayer.config import VALID_FACT_CLASSES
        conn, _ = populated_db
        classes = conn.execute(
            "SELECT DISTINCT fact_class FROM memory_facts WHERE fact_class IS NOT NULL"
        ).fetchall()
        for (fc,) in classes:
            assert fc in VALID_FACT_CLASSES, f"Invalid fact_class: {fc}"
