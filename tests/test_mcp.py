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
    """Test the memory://identity resource (partial-serving design since 0.3.0).

    The resource serves CORE plus a manifest of available tools. The other
    layers (ANCHORS, PREDICTIONS) and the unified brief are NOT in the
    always-loaded payload; they are accessible via tools.
    """

    def test_returns_core_and_manifest_when_layers_exist(self, mock_identity_layers, tmp_path):
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            assert len(brief) > 0
            # CORE content is in the resource
            assert "A builder and systems thinker" in brief
            # ANCHORS content is NOT in the resource (now behind get_anchors tool)
            assert "Quality matters more than speed" not in brief
            # PREDICTIONS content is NOT in the resource (now behind get_predictions tool)
            assert "rejects shortcuts that sacrifice quality" not in brief.lower()
            # Manifest signal IS present (with interpretation-vs-recall framing)
            assert "interpretation-heavy" in brief.lower()
            assert "get_anchors" in brief
            assert "get_predictions" in brief
            assert "get_brief" in brief
            # Self-aware caveat IS present
            assert "not" in brief.lower() and "substitute for the user" in brief.lower()

    def test_returns_fallback_when_no_core_layer(self, tmp_path):
        empty_dir = tmp_path / "empty_layers"
        empty_dir.mkdir()
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", empty_dir / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", empty_dir / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", empty_dir / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            assert "No specification layers found" in brief

    def test_extracts_injectable_block_only_for_core(self, mock_identity_layers, tmp_path):
        """Should extract content below '## Injectable Block' marker for CORE."""
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            # Should NOT contain CORE metadata frontmatter
            assert "layer: core" not in brief
            assert "version: 1" not in brief


class TestSpecificationTools:
    """Test the partial-serving tools added in 0.3.0: get_anchors, get_predictions, get_brief."""

    def test_get_anchors_returns_anchors_block(self, mock_identity_layers):
        with patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"):
            result = mcp_server.get_anchors("test reason")
            assert "Quality matters more than speed" in result
            # Should not contain frontmatter
            assert "layer: anchors" not in result

    def test_get_anchors_missing_file(self, tmp_path):
        with patch.object(mcp_server, "ANCHORS_LAYER_FILE", tmp_path / "nonexistent.md"):
            result = mcp_server.get_anchors("test reason")
            assert "ANCHORS layer is not present" in result
            assert "baselayer author --layer anchors" in result

    def test_get_predictions_returns_predictions_block(self, mock_identity_layers):
        with patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            result = mcp_server.get_predictions("test reason")
            assert "shortcut" in result.lower() or "systematic analysis" in result
            assert "layer: predictions" not in result

    def test_get_predictions_missing_file(self, tmp_path):
        with patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", tmp_path / "nonexistent.md"):
            result = mcp_server.get_predictions("test reason")
            assert "PREDICTIONS layer is not present" in result
            assert "baselayer author --layer predictions" in result

    def test_get_brief_returns_brief_content(self, tmp_path):
        brief_file = tmp_path / "brief_v5_clean.md"
        brief_content = """---
layer: brief
---

## Injectable Block

This is the unified narrative specification of the user. They are a careful
systems thinker who values rigor and reproducibility above all.
"""
        brief_file.write_text(brief_content, encoding="utf-8")
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", brief_file), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"):
            result = mcp_server.get_brief("test reason")
            assert "unified narrative specification" in result
            assert "layer: brief" not in result

    def test_get_brief_missing_file(self, tmp_path):
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"):
            result = mcp_server.get_brief("test reason")
            assert "Unified brief is not present" in result
            assert "baselayer compose" in result


class TestServingToggle:
    """Verify the in-session enable/disable toggle for spec serving."""

    def test_default_is_enabled(self, tmp_path):
        """Missing state file should mean enabled."""
        with patch.object(mcp_server, "SERVING_STATE_FILE", tmp_path / "nonexistent_state"):
            assert mcp_server._is_serving_enabled() is True

    def test_zero_disables(self, tmp_path):
        state = tmp_path / "serving_enabled"
        state.write_text("0", encoding="utf-8")
        with patch.object(mcp_server, "SERVING_STATE_FILE", state):
            assert mcp_server._is_serving_enabled() is False

    def test_one_enables(self, tmp_path):
        state = tmp_path / "serving_enabled"
        state.write_text("1", encoding="utf-8")
        with patch.object(mcp_server, "SERVING_STATE_FILE", state):
            assert mcp_server._is_serving_enabled() is True

    def test_resource_returns_disabled_message_when_disabled(self, mock_identity_layers, tmp_path):
        state = tmp_path / "serving_enabled"
        state.write_text("0", encoding="utf-8")
        with patch.object(mcp_server, "SERVING_STATE_FILE", state), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"):
            result = mcp_server.get_specification()
            assert "disabled" in result.lower()
            assert "baselayer serve enable" in result
            # CORE content should NOT leak through
            assert "builder and systems thinker" not in result

    def test_get_anchors_returns_disabled_message(self, mock_identity_layers, tmp_path):
        state = tmp_path / "serving_enabled"
        state.write_text("0", encoding="utf-8")
        with patch.object(mcp_server, "SERVING_STATE_FILE", state), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"):
            result = mcp_server.get_anchors("test reason")
            assert "disabled" in result.lower()
            assert "Quality matters more than speed" not in result

    def test_get_predictions_returns_disabled_message(self, mock_identity_layers, tmp_path):
        state = tmp_path / "serving_enabled"
        state.write_text("0", encoding="utf-8")
        with patch.object(mcp_server, "SERVING_STATE_FILE", state), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            result = mcp_server.get_predictions("test reason")
            assert "disabled" in result.lower()

    def test_get_brief_returns_disabled_message(self, tmp_path):
        state = tmp_path / "serving_enabled"
        state.write_text("0", encoding="utf-8")
        brief_file = tmp_path / "brief_v5_clean.md"
        brief_file.write_text("## Injectable Block\n\nReal brief content here.", encoding="utf-8")
        with patch.object(mcp_server, "SERVING_STATE_FILE", state), \
             patch.object(mcp_server, "UNIFIED_BRIEF_FILE", brief_file):
            result = mcp_server.get_brief("test reason")
            assert "disabled" in result.lower()
            assert "Real brief content here" not in result


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


class TestSpecificationResourceAlias:
    """Test that memory://specification is canonical and memory://identity is a working alias."""

    def test_specification_resource_is_canonical_with_identity_alias(self, mock_identity_layers, tmp_path):
        """memory://specification is the canonical resource. memory://identity is a deprecated alias
        that returns the same content. Both URIs must be registered and return identical output.
        """
        import asyncio

        # Both resource URIs should be registered on the MCP server
        resources = asyncio.run(mcp_server.mcp.list_resources())
        uris = {str(r.uri) for r in resources}
        assert "memory://specification" in uris, "Canonical resource memory://specification not registered"
        assert "memory://identity" in uris, "Compat alias memory://identity not registered"

        # The canonical handler and the alias handler should both be callable
        assert callable(mcp_server.get_specification)
        assert callable(mcp_server.get_identity_brief)

        # And they should return identical content when invoked against the same fixture
        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "nonexistent_brief.md"), \
             patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "nonexistent_cited.md"), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            canonical = mcp_server.get_specification()
            alias = mcp_server.get_identity_brief()

        assert len(canonical) > 0
        assert canonical == alias, "Alias memory://identity must return same content as memory://specification"
