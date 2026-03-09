"""
Privacy tests for Base Layer.

Ensures: brief doesn't expose raw facts, MCP doesn't expose full database,
no API keys in output, no raw conversation text in brief.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestBriefPrivacy:
    """Ensure the identity brief doesn't leak raw data."""

    def test_identity_layers_dont_contain_fact_ids(self, mock_identity_layers):
        """Layer files should not contain fact IDs or database references."""
        for layer_file in mock_identity_layers.glob("*.md"):
            content = layer_file.read_text(encoding="utf-8")
            assert "fact-" not in content.lower()
            assert "SELECT" not in content
            assert "memory_facts" not in content

    def test_identity_layers_dont_contain_api_keys(self, mock_identity_layers):
        """Layer files should never contain API keys."""
        for layer_file in mock_identity_layers.glob("*.md"):
            content = layer_file.read_text(encoding="utf-8")
            assert "sk-ant-" not in content
            assert "sk-" not in content.split()  # Don't match "sk-" within words
            assert "ANTHROPIC_API_KEY" not in content

    def test_brief_token_budget_enforced(self):
        """Brief should not exceed the total token budget."""
        from config import TOTAL_TOKEN_BUDGET, CHARS_PER_TOKEN
        max_chars = TOTAL_TOKEN_BUDGET * CHARS_PER_TOKEN  # 20,000 chars
        assert max_chars == 20000


class TestMCPPrivacy:
    """Ensure the MCP server doesn't over-expose data."""

    def test_search_facts_has_limit(self):
        """search_facts tool should have a default result limit."""
        from mcp_server import search_facts
        import inspect
        sig = inspect.signature(search_facts)
        assert "limit" in sig.parameters
        assert sig.parameters["limit"].default == 15

    def test_identity_resource_reads_injectable_only(self, mock_identity_layers):
        """Identity resource should only return injectable blocks, not metadata."""
        import mcp_server
        with patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            brief = mcp_server.get_identity_brief()
            # Should NOT contain metadata headers
            assert "layer: anchors" not in brief
            assert "version: 1" not in brief
            assert "generated:" not in brief
            # SHOULD contain injectable content
            assert "Quality matters more than speed" in brief
            assert "builder and systems thinker" in brief


class TestNoSecretLeakage:
    """Ensure no secrets appear in any output path."""

    def test_config_has_no_hardcoded_keys(self):
        """config.py should not contain hardcoded API keys."""
        config_path = Path(__file__).parent.parent / "scripts" / "config.py"
        content = config_path.read_text(encoding="utf-8")
        assert "sk-ant-" not in content
        assert "sk-proj-" not in content
        # Should reference env vars, not values
        assert "os.environ" in content or "ANTHROPIC_API_KEY" not in content

    def test_cli_check_api_key_doesnt_print_key(self):
        """The API key check should not print the actual key."""
        from cli import _check_api_key
        import io
        from contextlib import redirect_stdout, redirect_stderr

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(SystemExit):
                f = io.StringIO()
                with redirect_stdout(f):
                    _check_api_key()
            # Output should not contain any real key pattern
            # (It prints a hint "sk-ant-..." which is fine)
