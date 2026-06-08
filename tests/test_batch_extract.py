"""
Tests for batch_extract.py — batch state persistence, conversation text building,
and helper functions.

All tests run without API keys or external services.
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock



# ============================================================
# _LOAD_BATCH_STATE / _SAVE_BATCH_STATE
# ============================================================

class TestBatchStatePersistence:
    """Test batch state load/save to JSON file."""

    def test_load_nonexistent_returns_none(self, tmp_path):
        from baselayer.batch_extract import _load_batch_state
        fake_path = tmp_path / "nonexistent.json"
        with patch("baselayer.batch_extract._get_batch_state_file", return_value=fake_path):
            result = _load_batch_state()
        assert result is None

    def test_save_creates_file(self, tmp_path):
        from baselayer.batch_extract import _save_batch_state
        state_file = tmp_path / "data" / "database" / "batch_state.json"
        with patch("baselayer.batch_extract._get_batch_state_file", return_value=state_file):
            _save_batch_state({"batch_id": "test-123", "status": "submitted"})
        assert state_file.exists()

    def test_save_creates_parent_dirs(self, tmp_path):
        from baselayer.batch_extract import _save_batch_state
        state_file = tmp_path / "deep" / "nested" / "dir" / "state.json"
        with patch("baselayer.batch_extract._get_batch_state_file", return_value=state_file):
            _save_batch_state({"batch_id": "test-456"})
        assert state_file.exists()

    def test_roundtrip(self, tmp_path):
        from baselayer.batch_extract import _load_batch_state, _save_batch_state
        state_file = tmp_path / "state.json"
        original = {
            "batch_id": "batch-abc",
            "status": "submitted",
            "total_requests": 100,
            "conversation_ids": ["c1", "c2", "c3"],
        }
        with patch("baselayer.batch_extract._get_batch_state_file", return_value=state_file):
            _save_batch_state(original)
            loaded = _load_batch_state()
        assert loaded == original

    def test_save_overwrites_existing(self, tmp_path):
        from baselayer.batch_extract import _load_batch_state, _save_batch_state
        state_file = tmp_path / "state.json"
        with patch("baselayer.batch_extract._get_batch_state_file", return_value=state_file):
            _save_batch_state({"batch_id": "old", "status": "submitted"})
            _save_batch_state({"batch_id": "new", "status": "completed"})
            loaded = _load_batch_state()
        assert loaded["batch_id"] == "new"
        assert loaded["status"] == "completed"

    def test_save_pretty_prints(self, tmp_path):
        from baselayer.batch_extract import _save_batch_state
        state_file = tmp_path / "state.json"
        with patch("baselayer.batch_extract._get_batch_state_file", return_value=state_file):
            _save_batch_state({"batch_id": "test"})
        content = state_file.read_text(encoding="utf-8")
        # Pretty-printed JSON should have newlines
        assert "\n" in content


# ============================================================
# _BUILD_CONV_TEXT
# ============================================================

class TestBuildConvText:
    """Test conversation text building from messages."""

    def test_basic_building(self):
        from baselayer.batch_extract import _build_conv_text
        messages = [
            {"role": "user", "text": "Hello, how are you?"},
            {"role": "assistant", "text": "I'm doing well!"},
        ]
        result = _build_conv_text(messages)
        assert "User: Hello, how are you?" in result
        assert "Assistant: I'm doing well!" in result

    def test_role_capitalized(self):
        from baselayer.batch_extract import _build_conv_text
        messages = [{"role": "user", "text": "Hi"}]
        result = _build_conv_text(messages)
        assert result.startswith("User:")

    def test_preserves_long_messages(self):
        """2026-05-17: per-message [:1500] cap removed.
        Callers chunk via _build_chunk_requests / _chunk_text_for_extraction."""
        from baselayer.batch_extract import _build_conv_text
        long_text = "x" * 3000
        messages = [{"role": "user", "text": long_text}]
        result = _build_conv_text(messages)
        # Full message content survives; no per-message truncation.
        assert long_text in result

    def test_preserves_total_length(self):
        """2026-05-17: 12K hard-break removed.
        Long totals get chunked by _build_chunk_requests, not silently truncated."""
        from baselayer.batch_extract import _build_conv_text
        messages = [{"role": "user", "text": "x" * 1000} for _ in range(20)]
        result = _build_conv_text(messages)
        assert "[conversation continues...]" not in result
        # All 20 user messages present.
        assert result.count("User: ") == 20

    def test_empty_messages(self):
        from baselayer.batch_extract import _build_conv_text
        result = _build_conv_text([])
        assert result == ""

    def test_single_message(self):
        from baselayer.batch_extract import _build_conv_text
        messages = [{"role": "user", "text": "Just one message"}]
        result = _build_conv_text(messages)
        assert "User: Just one message" in result


# ============================================================
# CONSTANTS
# ============================================================

class TestBatchConstants:
    """Test batch extraction constants are sensible."""

    def test_batch_state_file_path(self):
        from baselayer.batch_extract import BATCH_STATE_FILE
        assert "batch_state.json" in str(BATCH_STATE_FILE)

    def test_batch_max_tokens(self):
        from baselayer.batch_extract import BATCH_MAX_TOKENS
        assert BATCH_MAX_TOKENS > 0
        # 2026-05-19: raised from 2000 to 8000. A 50-fact chunk needs ~6000
        # output tokens; the old 2000/4096 ceilings truncated JSON responses.
        # Upper bound is Haiku 4.5's 8192 max-output cap.
        assert BATCH_MAX_TOKENS <= 8192

    def test_batch_temperature(self):
        from baselayer.batch_extract import BATCH_TEMPERATURE
        assert 0 <= BATCH_TEMPERATURE <= 1.0
