"""
Unit tests for Base Layer core modules.

Tests config constants, database init, and authoring helpers.
All tests run without API keys or external services.
"""

import pytest
import sqlite3
import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ============================================================
# CONFIG TESTS
# ============================================================

class TestConfig:
    """Test that config.py defines all required constants."""

    def test_paths_defined(self):
        from config import PROJECT_ROOT, DATABASE_FILE, VECTORS_DIR
        assert PROJECT_ROOT is not None
        assert DATABASE_FILE is not None
        assert VECTORS_DIR is not None

    def test_token_budgets(self):
        from config import (
            IDENTITY_TOKEN_BUDGET, THEME_TOKEN_BUDGET,
            EPISODE_TOKEN_BUDGET, TOTAL_TOKEN_BUDGET, CHARS_PER_TOKEN,
        )
        assert IDENTITY_TOKEN_BUDGET == 3500
        assert THEME_TOKEN_BUDGET == 800
        assert EPISODE_TOKEN_BUDGET == 600
        assert TOTAL_TOKEN_BUDGET == 5000
        assert CHARS_PER_TOKEN == 4

    def test_valid_categories(self):
        from config import VALID_CATEGORIES
        required = {"preference", "biography", "project", "relationship",
                    "interest", "skill", "value", "habit", "opinion",
                    "goal", "negative_trait"}
        assert VALID_CATEGORIES == required

    def test_valid_fact_types(self):
        from config import VALID_FACT_TYPES
        required = {"biographical", "behavioral", "positional", "preference", "unclassified"}
        assert VALID_FACT_TYPES == required

    def test_valid_commitment_depths(self):
        from config import VALID_COMMITMENT_DEPTHS
        required = {"factual", "preference", "position", "conviction", "unclassified"}
        assert VALID_COMMITMENT_DEPTHS == required

    def test_valid_fact_classes(self):
        from config import VALID_FACT_CLASSES
        assert VALID_FACT_CLASSES == {"event", "state", "unclassified"}

    def test_extraction_settings(self):
        from config import (
            SIMILARITY_THRESHOLD, MIN_FACT_LENGTH,
            MAX_FACTS_PER_CONVERSATION, MIN_MESSAGES_FOR_EXTRACTION,
        )
        assert 0 < SIMILARITY_THRESHOLD <= 1.0
        assert MIN_FACT_LENGTH > 0
        assert MAX_FACTS_PER_CONVERSATION > 0
        assert MIN_MESSAGES_FOR_EXTRACTION > 0

    def test_identity_layer_paths(self):
        from config import (
            IDENTITY_LAYERS_DIR, ANCHORS_LAYER_FILE,
            CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
        )
        assert ANCHORS_LAYER_FILE.name == "anchors_v4.md"
        assert CORE_LAYER_FILE.name == "core_v4.md"
        assert PREDICTIONS_LAYER_FILE.name == "predictions_v4.md"
        assert ANCHORS_LAYER_FILE.parent == IDENTITY_LAYERS_DIR

    def test_scope_source_mapping(self):
        from config import SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE
        assert SCOPE_SOURCE_MAPPING["chatgpt"] == "personal"
        assert SCOPE_SOURCE_MAPPING["claude_web"] == "personal"
        assert SCOPE_SOURCE_MAPPING["claude_code"] == "project"
        assert DEFAULT_SCOPE == "personal"

    def test_project_root_respects_env_var(self, tmp_path):
        with patch.dict(os.environ, {"MEMORY_SYSTEM_ROOT": str(tmp_path)}):
            # Re-import to trigger resolution
            from config import _resolve_project_root
            root = _resolve_project_root()
            assert root == tmp_path


# ============================================================
# DATABASE INIT TESTS
# ============================================================

class TestInitDatabase:
    """Test database initialization creates all required tables."""

    def test_creates_all_tables(self, temp_db):
        conn, db_path = temp_db
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]

        # Core tables that MUST exist (excludes FTS virtual tables which may vary)
        expected_core = [
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
            "topic_scores",
            "turn_pairs",
            "user_corrections",
        ]
        # Filter out FTS virtual tables (memory_facts_fts*) from actual tables
        core_tables = [t for t in table_names if not t.startswith("memory_facts_fts")]
        assert sorted(core_tables) == sorted(expected_core), f"Missing tables: {set(expected_core) - set(core_tables)}"

    def test_conversations_table_schema(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(conversations)").fetchall()
        columns = {row[1] for row in info}
        assert "id" in columns
        assert "title" in columns
        assert "source" in columns
        assert "message_count" in columns

    def test_memory_facts_table_schema(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(memory_facts)").fetchall()
        columns = {row[1] for row in info}
        required = {
            "id", "fact_text", "category", "confidence", "superseded_by",
            "fact_type", "commitment_depth", "knowledge_tier", "scope",
            "fact_class", "recurrence_count", "depth_score",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_idempotent_init(self, tmp_path):
        """Running init twice should not error or duplicate tables."""
        db_path = tmp_path / "test.db"
        from init_database import init_database
        tables1 = init_database(db_path)
        tables2 = init_database(db_path)
        assert tables1 == tables2

    def test_epistemic_anchors_schema(self, temp_db):
        conn, _ = temp_db
        info = conn.execute("PRAGMA table_info(epistemic_anchors)").fetchall()
        columns = {row[1] for row in info}
        assert "anchor_text" in columns
        assert "status" in columns
        assert "source_fact_ids" in columns


# ============================================================
# DATA RETRIEVAL TESTS (using populated_db)
# ============================================================

class TestPopulatedDB:
    """Test queries against populated database."""

    def test_active_facts_count(self, populated_db):
        conn, _ = populated_db
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        assert count == 3  # fact-004 is superseded

    def test_superseded_facts_count(self, populated_db):
        conn, _ = populated_db
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NOT NULL"
        ).fetchone()[0]
        assert count == 1

    def test_conversations_count(self, populated_db):
        conn, _ = populated_db
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        assert count == 3

    def test_tier_breakdown(self, populated_db):
        conn, _ = populated_db
        tiers = conn.execute("""
            SELECT knowledge_tier, COUNT(*) as cnt
            FROM memory_facts WHERE superseded_by IS NULL
            GROUP BY knowledge_tier
        """).fetchall()
        tier_dict = {t["knowledge_tier"]: t["cnt"] for t in tiers}
        assert tier_dict.get("identity") == 2
        assert tier_dict.get("situational") == 1

    def test_extraction_log(self, populated_db):
        conn, _ = populated_db
        extracted = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
        assert extracted == 2


# ============================================================
# AUTHORING TESTS
# ============================================================

class TestAuthoringHelpers:
    """Test authoring helper functions that remain in the simplified pipeline."""

    def test_domain_cap_config_exists(self):
        """Domain balance config must exist (D-055)."""
        from config import AUTHORING_MAX_DOMAIN_PERCENT, AUTHORING_DOMAIN_KEYWORDS
        assert 0 < AUTHORING_MAX_DOMAIN_PERCENT <= 50
        assert isinstance(AUTHORING_DOMAIN_KEYWORDS, dict)
        assert "trading" in AUTHORING_DOMAIN_KEYWORDS

    def test_domain_cap_function_exists(self):
        """cap_by_domain must be importable and callable."""
        from author_layers import cap_by_domain
        result = cap_by_domain([])
        assert result == []

    def test_domain_cap_reduces_over_represented(self):
        """Domain cap should reduce facts when a domain exceeds threshold."""
        from author_layers import cap_by_domain
        facts = [{"fact_text": f"trading setup {i}", "category": "skill"} for i in range(20)]
        facts += [{"fact_text": "enjoys hiking regularly", "category": "habit"}]
        # 20 trading + 1 non-trading = 21 total. 25% of 21 = 5.
        result = cap_by_domain(facts, max_percent=25)
        trading_count = sum(1 for f in result if "trading" in f["fact_text"])
        assert trading_count <= 6  # 25% of 21 rounded up
