"""MCP `trace_claim` shows the person's own quoted words (evidence spans) behind each linked fact
when the fact carries them, at most three per fact, and still works on a database whose
memory_facts table has no evidence_spans column (legacy extraction). No model calls.
"""
import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

PROV = """CREATE TABLE layer_claim_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT, layer_name TEXT NOT NULL, claim_id TEXT NOT NULL,
    claim_text TEXT, fact_id TEXT, link_method TEXT, similarity_score REAL, rank_in_claim INTEGER,
    layer_version TEXT, cycle_id TEXT, created_at REAL)"""


def _db(tmp_path, with_spans):
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    conn.row_factory = sqlite3.Row
    cols = ("id TEXT PRIMARY KEY, fact_text TEXT, fact_type TEXT, knowledge_tier TEXT, "
            "recurrence_count INTEGER, source_conversation_id TEXT, predicate TEXT, object_text TEXT")
    conn.execute(f"CREATE TABLE memory_facts ({cols}{', evidence_spans TEXT' if with_spans else ''})")
    conn.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT, created_at REAL)")
    conn.execute(PROV)
    conn.execute("INSERT INTO conversations VALUES ('c1', 'Planning chat', 1.0)")
    facts = [("f1", "They write the plan before the code.", 1), ("f2", "They keep a dated backup.", 5),
             ("f3", "They ask for two options.", 0)]
    for rank, (fid, text, n_spans) in enumerate(facts, 1):
        spans = [{"turn_id": f"t-{fid}-{i}", "span": f"{fid} own words number {i}",
                  "evidence_kind": "own_typed"} for i in range(n_spans)]
        vals = [fid, text, "?", "identity", 2, "c1", "prefers", "x"]
        if with_spans:
            vals.append(json.dumps(spans) if n_spans else None)
        conn.execute(f"INSERT INTO memory_facts VALUES ({','.join('?' * len(vals))})", vals)
        conn.execute("INSERT INTO layer_claim_provenance (layer_name, claim_id, claim_text, fact_id, "
                     "link_method, rank_in_claim) VALUES ('ANCHORS', 'A1', 'PLAN FIRST', ?, 'authoring', ?)",
                     (fid, rank))
    conn.commit()
    return conn


def _trace(conn, claim="A1"):
    from baselayer.mcp_server import trace_claim
    with patch("baselayer.mcp_server.DATABASE_FILE", MagicMock(exists=MagicMock(return_value=True))), \
         patch("baselayer.mcp_server.get_db", return_value=conn):
        return trace_claim(claim)


def test_spans_are_shown_with_turn_ids(tmp_path):
    out = _trace(_db(tmp_path, with_spans=True))
    assert 'words: "f1 own words number 0" (turn t-f1-0)' in out
    assert "Planning chat" in out


def test_at_most_three_spans_per_fact(tmp_path):
    out = _trace(_db(tmp_path, with_spans=True))
    shown = [l for l in out.splitlines() if "f2 own words" in l]
    assert len(shown) == 3
    assert "2 more evidence span(s)" in out


def test_fact_without_spans_shows_none(tmp_path):
    out = _trace(_db(tmp_path, with_spans=True))
    block = out.split("They ask for two options.")[1]
    assert "words:" not in block


def test_legacy_database_without_the_column_still_traces(tmp_path):
    out = _trace(_db(tmp_path, with_spans=False))
    assert "PLAN FIRST" in out and "They write the plan before the code." in out
    assert "words:" not in out


def test_unreadable_span_data_is_skipped(tmp_path):
    conn = _db(tmp_path, with_spans=True)
    conn.execute("UPDATE memory_facts SET evidence_spans = 'not json' WHERE id = 'f1'")
    conn.commit()
    out = _trace(conn)
    assert "They write the plan before the code." in out


def test_a_forgotten_fact_is_not_served(tmp_path):
    """`baselayer forget` sets superseded_by = 'user_forget' and leaves the claim's provenance
    rows in place until the layers are regenerated. trace_claim used to hand the forgotten
    fact's text, its quoted words and its source title to the model anyway. AUDN history
    (a fact superseded by a newer one) is not hidden: only what the user forgot."""
    conn = _db(tmp_path, with_spans=True)
    conn.execute("ALTER TABLE memory_facts ADD COLUMN superseded_by TEXT")
    conn.execute("UPDATE memory_facts SET superseded_by = 'user_forget' WHERE id = 'f2'")
    conn.execute("UPDATE memory_facts SET superseded_by = 'f9' WHERE id = 'f3'")
    conn.commit()
    out = _trace(conn)
    assert "dated backup" not in out and "f2 own words" not in out
    assert "hidden: forgotten by the user" in out
    assert "They ask for two options." in out          # superseded by AUDN: still shown
    assert "They write the plan before the code." in out
