"""
`baselayer chunks retry <legacy block id>` no longer re-extracts a whole migrated conversation
(design decision 2026-09-29). It records a review-backlog entry (conversation id, block id, requested
at, reason), exactly like naming a finished conversation, and re-extracts nothing. It is
NON-BLOCKING: the other named chunks are still requeued, the next run proceeds with them, the
exit code is unaffected, and the conversation's existing facts stay in use. One line says it
was recorded for review.

No API calls: fake clients only.
"""

import pytest

from tests.test_chunk_ledger import (  # noqa: F401  (env is a fixture)
    _cli, _pre_ledger_failed_row, _rows)
from tests.test_chunk_ledger_backlog import _table
from tests.test_failed_chunks import ALL4, CONV, LLM, _objects, env  # noqa: F401


def _migrated(env, monkeypatch):
    """A conversation migrated from extraction_chunks_failed: one failed chunk (Entry 0) and
    the legacy block `*` (done) carrying the other three facts."""
    from baselayer import chunk_ledger as cl
    _pre_ledger_failed_row(env, monkeypatch, env.ef.chunk_key([f"{CONV}:0", f"{CONV}:1"]))
    c = env.get_db()
    c.execute("DELETE FROM memory_facts WHERE object_text = ?", (ALL4[0],))
    c.execute("UPDATE extraction_log SET facts_extracted = 3")
    c.commit()
    assert cl.ensure_ledger(c) == 1
    c.close()
    rows = {r["chunk_key"]: r for r in _rows(env)}
    legacy = rows.pop(cl.LEGACY_KEY)
    (failed,) = rows.values()
    assert legacy["status"] == "done" and failed["status"] == "failed"
    return legacy, failed


def test_retrying_the_legacy_block_records_a_review_and_re_extracts_nothing(
        env, monkeypatch, capsys):
    legacy, failed = _migrated(env, monkeypatch)
    capsys.readouterr()
    try:
        _cli(env, monkeypatch, "chunks", "retry", legacy["block_id"][:10], failed["block_id"],
             "--reason", "prompt changed")
    except SystemExit as e:                                # exit code unaffected
        assert not e.code, e.code
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if "recorded for review" in l]
    assert len(lines) == 1 and CONV in lines[0]
    rows = {r["block_id"]: r for r in _rows(env)}
    assert rows[legacy["block_id"]]["status"] == "done"   # not requeued
    assert rows[failed["block_id"]]["status"] == "pending"  # the other chunk still is
    revs = _table(env, "extraction_review_requests")
    assert len(revs) == 1
    r = revs[0]
    assert r["conversation_id"] == CONV and r["block_id"] == legacy["block_id"]
    assert r["requested_at"] and r["reason"] == "prompt changed"
    assert r["via"] == "chunks retry"

    # the run proceeds: only the requeued chunk is called, the legacy facts stay in use
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert len(llm.prompts) == 1 and "Entry 0" in llm.prompts[0]
    assert _objects(env) == ALL4
    assert {r["status"] for r in _rows(env)} == {"done"}

    capsys.readouterr()
    _cli(env, monkeypatch, "chunks", "list", "--review")
    out = capsys.readouterr().out
    assert CONV in out and legacy["block_id"] in out and "prompt changed" in out


def test_retrying_only_the_legacy_block_is_not_an_error(env, monkeypatch, capsys):
    legacy, failed = _migrated(env, monkeypatch)
    capsys.readouterr()
    _cli(env, monkeypatch, "chunks", "retry", legacy["block_id"])   # no reason: allowed
    out = capsys.readouterr().out
    assert "recorded for review" in out
    assert [r["block_id"] for r in _table(env, "extraction_review_requests")] == [
        legacy["block_id"]]
    assert {r["block_id"]: r["status"] for r in _rows(env)} == {
        legacy["block_id"]: "done", failed["block_id"]: "failed"}


def test_an_older_review_table_gains_the_block_id_column(env):
    from baselayer import chunk_ledger as cl
    c = env.get_db()
    c.execute("CREATE TABLE extraction_review_requests (conversation_id TEXT NOT NULL, "
              "requested_at REAL NOT NULL, reason TEXT, via TEXT)")
    c.execute("INSERT INTO extraction_review_requests VALUES ('c0', 1.0, 'old', 'conv_id')")
    c.commit()
    assert cl.list_reviews(c)[0]["block_id"] is None       # read without migrating
    cl.ensure_ledger(c)
    cols = {r[1] for r in c.execute("PRAGMA table_info(extraction_review_requests)")}
    assert "block_id" in cols
    cl.record_review(c, "c1", reason="r", via="chunks retry", block_id="b1")
    c.commit()
    got = [(r["conversation_id"], r["block_id"]) for r in cl.list_reviews(c)]
    c.close()
    assert got == [("c0", None), ("c1", "b1")]


@pytest.mark.parametrize("status", ["failed", "quarantined"])
def test_requeue_still_moves_failed_and_quarantined_rows(env, monkeypatch, status):
    from baselayer import chunk_ledger as cl
    legacy, failed = _migrated(env, monkeypatch)
    c = env.get_db()
    c.execute("UPDATE extraction_chunks SET status = ? WHERE block_id = ?",
              (status, failed["block_id"]))
    assert cl.requeue(c, block_ids=[failed["block_id"], legacy["block_id"]]) == 1
    c.commit()
    c.close()
