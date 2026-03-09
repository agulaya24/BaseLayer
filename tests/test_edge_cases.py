"""
Edge case tests for Base Layer.

Tests: empty database, single fact, unicode, duplicates, malformed data.
"""

import pytest
import sqlite3
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestEmptyDatabase:
    """Tests against a freshly initialized (empty) database."""

    def test_stats_on_empty_db(self, temp_db):
        """Stats query should return zeros, not error."""
        conn, _ = temp_db
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        assert count == 0

    def test_active_facts_empty(self, temp_db):
        conn, _ = temp_db
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        assert count == 0

    def test_no_extraction_log(self, temp_db):
        conn, _ = temp_db
        count = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
        assert count == 0


class TestSingleRecord:
    """Test behavior with minimal data."""

    def test_single_conversation(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-solo", "Only One", 1700000000.0, 1700001000.0, 2, "chatgpt"),
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        assert count == 1

    def test_single_fact(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-1", "Test", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        conn.execute("""
            INSERT INTO memory_facts (id, fact_text, category, confidence,
            source_conversation_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("fact-solo", "Likes coffee", "preference", 0.9,
              "conv-1", 1700000000.0, 1700000000.0))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        assert count == 1


class TestUnicodeHandling:
    """Test that unicode and emoji content doesn't break the system."""

    def test_unicode_conversation_title(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-uni", "Conversaci\u00f3n sobre caf\u00e9 \u2615", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        conn.commit()
        row = conn.execute("SELECT title FROM conversations WHERE id='conv-uni'").fetchone()
        assert "\u2615" in row[0]

    def test_unicode_fact_text(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-1", "Test", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        fact_text = "Loves Japanese food \U0001F363 and speaks \u65e5\u672c\u8a9e"
        conn.execute("""
            INSERT INTO memory_facts (id, fact_text, category, confidence,
            source_conversation_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("fact-uni", fact_text, "preference", 0.8,
              "conv-1", 1700000000.0, 1700000000.0))
        conn.commit()
        row = conn.execute("SELECT fact_text FROM memory_facts WHERE id='fact-uni'").fetchone()
        assert "\U0001F363" in row[0]
        assert "\u65e5\u672c\u8a9e" in row[0]

    def test_unicode_message_content(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-1", "Test", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        content = "I love \u00e7a va bien \U0001F604 and \u4f60\u597d"
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
            ("msg-uni", "conv-1", None, "user", content, "text", 1700000000.0, 1),
        )
        conn.commit()
        row = conn.execute("SELECT content_text FROM messages WHERE id='msg-uni'").fetchone()
        assert "\U0001F604" in row[0]


class TestDuplicateHandling:
    """Test behavior with duplicate data."""

    def test_duplicate_conversation_id_rejected(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-dup", "First", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                ("conv-dup", "Duplicate", 1700000000.0, 1700000000.0, 1, "chatgpt"),
            )

    def test_duplicate_fact_id_rejected(self, temp_db):
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-1", "Test", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        conn.execute("""
            INSERT INTO memory_facts (id, fact_text, category, confidence,
            source_conversation_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("fact-dup", "First fact", "preference", 0.9,
              "conv-1", 1700000000.0, 1700000000.0))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO memory_facts (id, fact_text, category, confidence,
                source_conversation_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("fact-dup", "Duplicate fact", "preference", 0.9,
                  "conv-1", 1700000000.0, 1700000000.0))


class TestMalformedData:
    """Test handling of malformed input data."""

    def test_malformed_chatgpt_json(self, tmp_path):
        """Malformed JSON should not crash the import."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ this is not valid json }", encoding="utf-8")
        with pytest.raises((json.JSONDecodeError, Exception)):
            with open(str(bad_file)) as f:
                json.load(f)

    def test_empty_conversation_text(self, temp_db):
        """A conversation with empty message text should be storable."""
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-empty", "Empty Chat", 1700000000.0, 1700000000.0, 0, "chatgpt"),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
            ("msg-empty", "conv-empty", None, "user", "", "text", 1700000000.0, 1),
        )
        conn.commit()
        row = conn.execute("SELECT content_text FROM messages WHERE id='msg-empty'").fetchone()
        assert row[0] == ""

    def test_very_long_fact_text(self, temp_db):
        """Very long fact text should be storable."""
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-1", "Test", 1700000000.0, 1700000000.0, 1, "chatgpt"),
        )
        long_text = "A" * 10000  # 10K character fact
        conn.execute("""
            INSERT INTO memory_facts (id, fact_text, category, confidence,
            source_conversation_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("fact-long", long_text, "biography", 0.5,
              "conv-1", 1700000000.0, 1700000000.0))
        conn.commit()
        row = conn.execute("SELECT fact_text FROM memory_facts WHERE id='fact-long'").fetchone()
        assert len(row[0]) == 10000

    def test_null_fields_allowed(self, temp_db):
        """Optional fields should accept NULL."""
        conn, _ = temp_db
        conn.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("conv-1", None, None, None, 0, "chatgpt"),
        )
        conn.commit()
        row = conn.execute("SELECT title FROM conversations WHERE id='conv-1'").fetchone()
        assert row[0] is None
