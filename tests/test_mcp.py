"""
MCP server tests for Base Layer.

Tests: server init, identity resource, recall_memories tool,
search_facts tool, get_stats tool, graceful handling of missing data.
"""

import pytest
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock


import baselayer.mcp_server as mcp_server


class TestMCPServerInit:
    """Test MCP server initialization."""

    def test_server_module_has_expected_functions(self):
        """MCP server module should expose expected functions."""
        assert callable(mcp_server.get_identity_brief)
        assert callable(mcp_server.search_facts)
        assert callable(mcp_server.get_stats)


class TestIdentityResource:
    """Test the memory://identity resource."""

    def test_returns_content_when_layers_exist(self, mock_identity_layers, tmp_path):
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            assert len(brief) > 0
            assert "Quality matters more than speed" in brief

    def test_returns_fallback_when_no_layers(self, tmp_path):
        empty_dir = tmp_path / "empty_layers"
        empty_dir.mkdir()
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", empty_dir / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", empty_dir / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", empty_dir / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            assert "No identity layers found" in brief

    def test_extracts_injectable_block_only(self, mock_identity_layers):
        """Should extract content below '## Injectable Block' marker."""
        with patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            # Should NOT contain metadata
            assert "layer: anchors" not in brief
            assert "version: 1" not in brief


class TestSearchFactsTool:
    """Test the search_facts MCP tool."""

    def test_search_returns_results(self, populated_db):
        conn, db_path = populated_db
        with patch.object(mcp_server, "DATABASE_FILE", db_path), \
             patch.object(mcp_server, "get_db", lambda: (lambda c: (setattr(c, 'row_factory', sqlite3.Row), c)[1])(sqlite3.connect(str(db_path)))):
            result = mcp_server.search_facts("quality")
            assert "quality" in result.lower() or "Found" in result

    def test_search_no_results(self, populated_db):
        conn, db_path = populated_db
        with patch.object(mcp_server, "DATABASE_FILE", db_path), \
             patch.object(mcp_server, "get_db", lambda: (lambda c: (setattr(c, 'row_factory', sqlite3.Row), c)[1])(sqlite3.connect(str(db_path)))):
            result = mcp_server.search_facts("xyznonexistent")
            assert "No facts found" in result

    def test_search_missing_db(self, tmp_path):
        fake_db = tmp_path / "nonexistent.db"
        with patch.object(mcp_server, "DATABASE_FILE", fake_db):
            result = mcp_server.search_facts("anything")
            assert "No memory database" in result


class TestGetStatsTool:
    """Test the get_stats MCP tool."""

    def test_stats_returns_counts(self, populated_db):
        conn, db_path = populated_db
        with patch.object(mcp_server, "DATABASE_FILE", db_path), \
             patch.object(mcp_server, "get_db", lambda: (lambda c: (setattr(c, 'row_factory', sqlite3.Row), c)[1])(sqlite3.connect(str(db_path)))):
            result = mcp_server.get_stats()
            assert "Conversations:" in result
            assert "Active facts:" in result
            assert "3" in result  # 3 conversations

    def test_stats_missing_db(self, tmp_path):
        fake_db = tmp_path / "nonexistent.db"
        with patch.object(mcp_server, "DATABASE_FILE", fake_db):
            result = mcp_server.get_stats()
            assert "No memory database" in result
