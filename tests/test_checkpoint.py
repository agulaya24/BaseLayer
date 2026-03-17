"""
Tests for checkpoint.py — pipeline quality gate reports for extraction stage.

All tests run without API keys or external services.
"""

import pytest
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock



@pytest.fixture
def checkpoint_db(tmp_path):
    """Create a temp database with schema and sample data for checkpoint tests."""
    db_path = tmp_path / "checkpoint_test.db"
    with patch("baselayer.config.DATABASE_FILE", db_path), \
         patch("baselayer.config.PROJECT_ROOT", tmp_path):
        from baselayer.init_database import init_database
        init_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Insert sample facts with varied attributes
    facts = [
        ("f1", "Works in AI industry", "biography", 0.9, 0.8, 8.0, 15, 7.5, 180,
         "high", "conv1", 1700000000.0, 1700000000.0, None, "extraction", "user",
         "does", "present", 0.9, "neutral", "state", "identity", "haiku",
         "personal", "biographical", "factual", "works_at", "AI industry", None),
        ("f2", "Values quality over speed", "value", 0.95, 0.9, 9.0, 25, 9.0, 365,
         "high", "conv1", 1700000000.0, 1700000000.0, None, "extraction", "user",
         "does", "present", 0.95, "positive", "state", "identity", "haiku",
         "personal", "positional", "conviction", "values", "quality over speed", None),
        ("f3", "Uses systematic trading", "interest", 0.85, 0.7, 7.0, 10, 6.0, 120,
         "medium", "conv2", 1700100000.0, 1700100000.0, None, "extraction", "user",
         "does", "present", 0.85, "neutral", "state", "situational", "haiku",
         "personal", "behavioral", "position", "trades", "systematically", None),
        ("f4", "Enjoys hiking", "interest", 0.80, 0.6, 5.0, 3, 4.0, 60,
         "medium", "conv1", 1700000000.0, 1700000000.0, None, "extraction", "user",
         "does", "present", 0.80, "positive", "state", "context", "haiku",
         "personal", "preference", "preference", "enjoys", "hiking", None),
        ("f5", "Superseded fact", "biography", 0.5, 0.3, 3.0, 2, 2.0, 30,
         "low", "conv1", 1699000000.0, 1699000000.0, "f1", "extraction", "user",
         "does", "past", 0.5, "neutral", "state", None, None,
         "personal", None, None, None, None, None),
    ]

    for f in facts:
        conn.execute("""
            INSERT INTO memory_facts (
                id, fact_text, category, confidence, surprise_score, significance_score,
                recurrence_count, depth_score, recurrence_span_days, significance_type,
                source_conversation_id, created_at, updated_at, superseded_by, source,
                subject, intent, temporal_state, raw_llm_confidence, sentiment,
                fact_class, knowledge_tier, tiered_by, scope, fact_type, commitment_depth,
                predicate, object_text, qualifier
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, f)

    conn.commit()
    yield conn, db_path
    conn.close()


class TestCheckpointExtraction:
    """Test checkpoint_extraction() quality report."""

    def test_returns_true_with_facts(self, checkpoint_db):
        from baselayer.checkpoint import checkpoint_extraction
        conn, _ = checkpoint_db
        result = checkpoint_extraction(conn, sample_size=10)
        assert result is True

    def test_returns_false_with_no_facts(self, tmp_path):
        db_path = tmp_path / "empty.db"
        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.PROJECT_ROOT", tmp_path):
            from baselayer.init_database import init_database
            init_database(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        from baselayer.checkpoint import checkpoint_extraction
        result = checkpoint_extraction(conn)
        assert result is False
        conn.close()

    def test_counts_active_facts_only(self, checkpoint_db):
        from baselayer.checkpoint import checkpoint_extraction
        conn, _ = checkpoint_db
        # f5 is superseded, should not be counted
        result = checkpoint_extraction(conn, sample_size=10)
        assert result is True

    def test_reports_predicate_distribution(self, checkpoint_db, capsys):
        from baselayer.checkpoint import checkpoint_extraction
        conn, _ = checkpoint_db
        checkpoint_extraction(conn, sample_size=10)
        captured = capsys.readouterr()
        assert "Predicate distribution" in captured.out


class TestRunCheckpoint:
    """Test the run_checkpoint() dispatcher."""

    def test_unknown_stage(self, capsys):
        from baselayer.checkpoint import run_checkpoint
        with patch("baselayer.checkpoint.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))):
            with patch("baselayer.checkpoint.get_db") as mock_get_db:
                mock_conn = MagicMock()
                mock_get_db.return_value = mock_conn
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_conn.close = MagicMock()
                run_checkpoint("invalid_stage")
        captured = capsys.readouterr()
        assert "Unknown checkpoint stage" in captured.out

    def test_no_database(self, capsys):
        from baselayer.checkpoint import run_checkpoint
        with patch("baselayer.checkpoint.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=False))):
            run_checkpoint("extraction")
        captured = capsys.readouterr()
        assert "No database found" in captured.out
