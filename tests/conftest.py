"""
Shared pytest fixtures for Base Layer test suite.

Provides: temp databases, mock facts, mock conversations, mock API responses.
All tests run without API keys or external services.
"""

import pytest
import sqlite3
import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary initialized database, return (connection, path)."""
    db_path = tmp_path / "test_memory.db"

    # Patch config to use temp path
    with patch("config.DATABASE_FILE", db_path), \
         patch("config.PROJECT_ROOT", tmp_path):
        from init_database import init_database
        tables = init_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn, db_path
    conn.close()


@pytest.fixture
def populated_db(temp_db):
    """Database with sample conversations, messages, and facts."""
    conn, db_path = temp_db

    # Insert sample conversations
    conversations = [
        ("conv-001", "Career Discussion", 1700000000.0, 1700001000.0, 10, "chatgpt"),
        ("conv-002", "Trading Strategy", 1700100000.0, 1700101000.0, 8, "chatgpt"),
        ("conv-003", "Journal Entry", 1700200000.0, 1700201000.0, 4, "text"),
    ]
    conn.executemany(
        "INSERT INTO conversations VALUES (?,?,?,?,?,?)", conversations
    )

    # Insert sample messages
    messages = [
        ("msg-001", "conv-001", None, "user", "I work in AI and love building things", "text", 1700000000.0, 1),
        ("msg-002", "conv-001", "msg-001", "assistant", "That sounds interesting!", "text", 1700000001.0, 2),
        ("msg-003", "conv-001", "msg-002", "user", "I value quality over speed always", "text", 1700000002.0, 3),
        ("msg-004", "conv-002", None, "user", "My trading approach is systematic", "text", 1700100000.0, 1),
        ("msg-005", "conv-002", "msg-004", "assistant", "Tell me more about your system", "text", 1700100001.0, 2),
    ]
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)", messages
    )

    # Insert sample facts
    facts = [
        ("fact-001", "Works in AI industry", "biography", 0.9, 0.8, 8.0, 15, 7.5, 180,
         "high", "conv-001", 1700000000.0, 1700000000.0, None, "extraction", "user",
         "does", "present", 0.9, "neutral", "state", "identity", "haiku",
         "personal", "biographical", "factual"),
        ("fact-002", "Values quality over speed in all work", "value", 0.95, 0.9, 9.0, 25, 9.0, 365,
         "high", "conv-001", 1700000000.0, 1700000000.0, None, "extraction", "user",
         "does", "present", 0.95, "positive", "state", "identity", "haiku",
         "personal", "positional", "conviction"),
        ("fact-003", "Uses systematic approach to trading", "interest", 0.85, 0.7, 7.0, 10, 6.0, 120,
         "medium", "conv-002", 1700100000.0, 1700100000.0, None, "extraction", "user",
         "does", "present", 0.85, "neutral", "state", "situational", "haiku",
         "personal", "behavioral", "position"),
        ("fact-004", "Superseded old fact", "biography", 0.5, 0.3, 3.0, 2, 2.0, 30,
         "low", "conv-001", 1699000000.0, 1699000000.0, "fact-001", "extraction", "user",
         "does", "past", 0.5, "neutral", "state", None, None,
         "personal", "biographical", "factual"),
    ]
    for f in facts:
        conn.execute("""
            INSERT INTO memory_facts (
                id, fact_text, category, confidence, surprise_score, significance_score,
                recurrence_count, depth_score, recurrence_span_days, significance_type,
                source_conversation_id, created_at, updated_at, superseded_by, source,
                subject, intent, temporal_state, raw_llm_confidence, sentiment,
                fact_class, knowledge_tier, tiered_by, scope, fact_type, commitment_depth
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, f)

    # Insert extraction log
    conn.execute("INSERT INTO extraction_log VALUES ('conv-001', 2, 1700000000.0)")
    conn.execute("INSERT INTO extraction_log VALUES ('conv-002', 1, 1700100000.0)")

    conn.commit()
    yield conn, db_path


@pytest.fixture
def mock_anthropic():
    """Mock the Anthropic API client.

    Patches both the anthropic.Anthropic constructor and resets the
    api_client singleton so the mock is used for all API calls.
    """
    import scripts.api_client as api_client_mod

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"facts": []}')]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_client.messages.create.return_value = mock_response

    # Reset singleton so the mock takes effect
    old_client = api_client_mod._anthropic_client
    api_client_mod._anthropic_client = mock_client
    try:
        with patch("anthropic.Anthropic", return_value=mock_client):
            yield mock_client
    finally:
        api_client_mod._anthropic_client = old_client


@pytest.fixture
def sample_chatgpt_export(tmp_path):
    """Create a sample ChatGPT JSON export file."""
    data = [
        {
            "id": "chatgpt-conv-001",
            "title": "Test Conversation",
            "create_time": 1700000000.0,
            "update_time": 1700001000.0,
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "parent": None,
                    "children": ["node-2"],
                    "message": {
                        "id": "msg-1",
                        "author": {"role": "user"},
                        "content": {"parts": ["Hello, I work as a software engineer"]},
                        "create_time": 1700000000.0,
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "children": [],
                    "message": {
                        "id": "msg-2",
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Nice to meet you!"]},
                        "create_time": 1700000001.0,
                    },
                },
            },
        }
    ]
    export_file = tmp_path / "conversations.json"
    export_file.write_text(json.dumps(data), encoding="utf-8")
    return export_file


@pytest.fixture
def sample_text_file(tmp_path):
    """Create a sample text file for journal import."""
    text = """January 15, 2024
Today I reflected on my values. I believe deeply in authenticity
and honest communication. I struggle with patience sometimes
but I'm working on it. My relationship with my partner is the
most important thing in my life.
"""
    text_file = tmp_path / "journal.txt"
    text_file.write_text(text, encoding="utf-8")
    return text_file


@pytest.fixture
def mock_identity_layers(tmp_path):
    """Create mock identity layer files."""
    layers_dir = tmp_path / "data" / "identity_layers"
    layers_dir.mkdir(parents=True, exist_ok=True)

    anchors = """---
layer: anchors
version: 1
generated: 2024-01-01
---

## Injectable Block

You reason FROM these commitments — they are not up for debate:
- Quality matters more than speed
- Honesty is non-negotiable
"""
    core = """---
layer: core
version: 1
generated: 2024-01-01
---

## Injectable Block

A builder and systems thinker who works in AI. Values depth over breadth.
Married to Jordan. Founded a startup.
"""
    predictions = """---
layer: predictions
version: 1
generated: 2024-01-01
---

## Injectable Block

When presented with a shortcut that sacrifices quality, will reject it.
Under pressure, defaults to systematic analysis over intuition.
"""
    (layers_dir / "anchors_v3.md").write_text(anchors, encoding="utf-8")
    (layers_dir / "core_v3.md").write_text(core, encoding="utf-8")
    (layers_dir / "predictions_v3.md").write_text(predictions, encoding="utf-8")

    return layers_dir
