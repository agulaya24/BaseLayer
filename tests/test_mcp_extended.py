"""
Tests for mcp_server.py — _escape_like(), trace_claim(), recall_memories(),
search_facts(), and get_stats().

All tests run without API keys or external services.
"""

import pytest
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock



# ============================================================
# _ESCAPE_LIKE
# ============================================================

class TestEscapeLike:
    """Test SQL LIKE metacharacter escaping."""

    def test_no_metacharacters(self):
        from baselayer.mcp_server import _escape_like
        assert _escape_like("hello world") == "hello world"

    def test_escapes_percent(self):
        from baselayer.mcp_server import _escape_like
        assert _escape_like("100%") == "100\\%"

    def test_escapes_underscore(self):
        from baselayer.mcp_server import _escape_like
        assert _escape_like("user_name") == "user\\_name"

    def test_escapes_backslash(self):
        from baselayer.mcp_server import _escape_like
        assert _escape_like("path\\to") == "path\\\\to"

    def test_escapes_all_metacharacters(self):
        from baselayer.mcp_server import _escape_like
        result = _escape_like("50%_off\\deal")
        assert result == "50\\%\\_off\\\\deal"

    def test_empty_string(self):
        from baselayer.mcp_server import _escape_like
        assert _escape_like("") == ""

    def test_multiple_occurrences(self):
        from baselayer.mcp_server import _escape_like
        assert _escape_like("a%b%c") == "a\\%b\\%c"

    def test_backslash_escaped_first(self):
        """Backslash must be escaped before % and _ to avoid double-escaping."""
        from baselayer.mcp_server import _escape_like
        # If % were escaped first, "\\%" would become "\\\\%", then backslash
        # escape would make it "\\\\\\\\%". Correct order: \\ first.
        result = _escape_like("\\%")
        assert result == "\\\\\\%"


# ============================================================
# TRACE_CLAIM
# ============================================================

class TestTraceClaim:
    """Test the trace_claim MCP tool."""

    @pytest.fixture
    def trace_db(self, tmp_path):
        """Database with provenance and fact data for tracing."""
        db_path = tmp_path / "trace_test.db"
        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.PROJECT_ROOT", tmp_path):
            from baselayer.init_database import init_database
            init_database(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Insert a fact
        conn.execute("""
            INSERT INTO memory_facts (
                id, fact_text, category, confidence, recurrence_count,
                source_conversation_id, created_at, updated_at, source,
                subject, knowledge_tier, fact_type, predicate, object_text
            ) VALUES (
                'fact-001', 'Works in AI industry', 'biography', 0.9, 15,
                'conv-001', 1700000000.0, 1700000000.0, 'extraction',
                'user', 'identity', 'biographical', 'works_at', 'AI industry'
            )
        """)

        # Insert a conversation
        conn.execute("""
            INSERT INTO conversations (id, title, created_at, updated_at, message_count, source)
            VALUES ('conv-001', 'Career Discussion', 1700000000.0, 1700001000.0, 10, 'chatgpt')
        """)

        # Insert provenance
        conn.execute("""
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
                created_at REAL
            )
        """)
        conn.execute("""
            INSERT INTO layer_claim_provenance
            (layer_name, claim_id, claim_text, fact_id, link_method, rank_in_claim,
             layer_version, cycle_id, created_at)
            VALUES ('ANCHORS', 'A1', 'COHERENCE', 'fact-001', 'authoring', 1,
                    'v3', 'gen1', 1700000000.0)
        """)
        conn.commit()
        yield conn, db_path
        conn.close()

    def test_trace_existing_claim(self, trace_db):
        from baselayer.mcp_server import trace_claim
        conn, db_path = trace_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = trace_claim("A1")
        assert "COHERENCE" in result
        assert "Works in AI industry" in result
        assert "Career Discussion" in result

    def test_trace_nonexistent_claim(self, trace_db):
        from baselayer.mcp_server import trace_claim
        conn, db_path = trace_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = trace_claim("Z99")
        assert "No provenance found" in result

    def test_trace_case_insensitive(self, trace_db):
        from baselayer.mcp_server import trace_claim
        conn, db_path = trace_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = trace_claim("a1")
        assert "COHERENCE" in result

    def test_trace_no_database(self):
        from baselayer.mcp_server import trace_claim
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=False))):
            result = trace_claim("A1")
        assert "No memory database found" in result


# ============================================================
# SEARCH_FACTS
# ============================================================

class TestSearchFacts:
    """Test the search_facts MCP tool."""

    @pytest.fixture
    def search_db(self, tmp_path):
        db_path = tmp_path / "search_test.db"
        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.PROJECT_ROOT", tmp_path):
            from baselayer.init_database import init_database
            init_database(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        for i, (text, tier) in enumerate([
            ("Works in AI industry", "identity"),
            ("Values quality over speed", "identity"),
            ("Checked weather today", "context"),
        ]):
            conn.execute("""
                INSERT INTO memory_facts (
                    id, fact_text, category, confidence, recurrence_count,
                    created_at, updated_at, source, subject,
                    knowledge_tier, fact_type, commitment_depth
                ) VALUES (?, ?, 'biography', 0.9, 10,
                    1700000000.0, 1700000000.0, 'extraction', 'user',
                    ?, 'biographical', 'factual')
            """, (f"f-{i}", text, tier))
        conn.commit()
        yield conn, db_path
        conn.close()

    def test_finds_matching_facts(self, search_db):
        from baselayer.mcp_server import search_facts
        conn, db_path = search_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = search_facts("AI")
        assert "AI industry" in result
        assert "Found" in result

    def test_no_matches(self, search_db):
        from baselayer.mcp_server import search_facts
        conn, db_path = search_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = search_facts("cryptocurrency")
        assert "No facts found" in result

    def test_respects_limit(self, search_db):
        from baselayer.mcp_server import search_facts
        conn, db_path = search_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = search_facts("a", limit=1)
        # Should find at most 1 result
        lines = [l for l in result.split("\n") if l.strip().startswith("[")]
        assert len(lines) <= 1


# ============================================================
# GET_STATS
# ============================================================

class TestGetStats:
    """Test the get_stats MCP tool."""

    def test_returns_statistics(self, populated_db):
        from baselayer.mcp_server import get_stats
        conn, db_path = populated_db
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=conn):
                result = get_stats()
        assert "Conversations" in result
        assert "Messages" in result
        assert "Active facts" in result

    def test_no_database(self):
        from baselayer.mcp_server import get_stats
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=False))):
            result = get_stats()
        assert "No memory database found" in result


# ============================================================
# RECALL_MEMORIES
# ============================================================

class TestRecallMemories:
    """Test the recall_memories MCP tool."""

    def test_no_database(self):
        from baselayer.mcp_server import recall_memories
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=False))):
            result = recall_memories("career history")
        assert "No memory database found" in result

    def test_no_results(self):
        from baselayer.mcp_server import recall_memories
        mock_conn = MagicMock()
        with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.mcp_server.get_db", return_value=mock_conn):
                with patch("baselayer.mcp_server._get_embed_model", return_value=None):
                    with patch("baselayer.mcp_server._get_chroma_client", return_value=MagicMock()):
                        # get_theme_block and get_episode_block are imported
                        # inside recall_memories from assemble_brief
                        with patch("baselayer.assemble_brief.get_theme_block",
                                   return_value=("", [])):
                            with patch("baselayer.assemble_brief.get_episode_block",
                                       return_value=""):
                                result = recall_memories("nonexistent topic")
        assert "No relevant memories found" in result
