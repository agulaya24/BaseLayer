"""
The model backlog BACKFILLS the model from the facts: existing corpora are backfilled with
known models where possible (design decision 2026-09-29).

Done work with no model recorded (a conversation logged before the ledger, or a ledger row
settled before the ledger recorded the model) takes its model from the `extraction_model` stamp
on the facts it stored, at read time. Nothing is rewritten.

- every stored fact carries one model: that model (it leaves the backlog when it is the
  configured one);
- the facts carry more than one model, or some carry one and some carry none: MIXED, listed
  with each model's fact count, never resolved to one of them (an acknowledgement covers that
  exact mix, so a changed mix resurfaces);
- no fact carries a stamp (no facts, every stamp empty, or no `extraction_model` column):
  `unknown`.

Read-only: the backfill works on a `mode=ro` connection and writes nothing. No API calls.
"""

import json
import sqlite3

from tests.test_chunk_ledger import (  # noqa: F401  (env is a fixture)
    _cli, _drop_ledger, _extract_clean, _forbid_calls, _rows)
from tests.test_chunk_ledger_backlog import MODEL_A, MODEL_B, _table, _use_model
from tests.test_failed_chunks import CONV, env  # noqa: F401


def _sql(env, sql, args=()):
    c = env.get_db()
    c.execute(sql, args)
    c.commit()
    c.close()


def _backlog(env, configured):
    from baselayer import chunk_ledger as cl
    c = env.get_db()
    try:
        return cl.model_backlog(c, configured)
    finally:
        c.close()


def _notice(env, configured):
    from baselayer import chunk_ledger as cl
    c = env.get_db()
    try:
        return cl.backlog_notice(c, configured)
    finally:
        c.close()


def _fact_ids(env):
    c = env.get_db()
    ids = [r[0] for r in c.execute("SELECT id FROM memory_facts ORDER BY object_text")]
    c.close()
    return ids


def _pre_ledger(env, monkeypatch):
    """A corpus extracted before the ledger, with MODEL_A stamped on its four facts."""
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    _drop_ledger(env)


# ---------------------------------------------------------------------------
# pre-ledger conversations
# ---------------------------------------------------------------------------

def test_a_pre_ledger_conversation_stamped_with_the_configured_model_leaves_the_backlog(
        env, monkeypatch, capsys):
    _pre_ledger(env, monkeypatch)
    assert _backlog(env, MODEL_A) == []
    assert _notice(env, MODEL_A) is None
    guard = _forbid_calls(env, monkeypatch)
    capsys.readouterr()
    env.ef.run_extraction()
    assert guard.calls == 0 and "Model backlog" not in capsys.readouterr().out
    assert _rows(env) == []                                # nothing was written for it


def test_a_pre_ledger_conversation_stamped_with_another_model_is_known(
        env, monkeypatch, capsys):
    _pre_ledger(env, monkeypatch)
    items = _backlog(env, MODEL_B)
    assert len(items) == 1
    it = items[0]
    assert it["conversation_id"] == CONV and it["model"] == MODEL_A
    assert it["model_source"] == "facts" and it["models"] == {MODEL_A: 4}
    notice = _notice(env, MODEL_B)
    assert "1 known" in notice and "0 mixed" in notice and "0 unknown" in notice
    _use_model(env, monkeypatch, MODEL_B)
    capsys.readouterr()
    _cli(env, monkeypatch, "chunks", "list", "--backlog")
    out = capsys.readouterr().out
    assert CONV in out and MODEL_A in out and "facts" in out
    _cli(env, monkeypatch, "chunks", "ack-model", "--all")
    assert [a["model"] for a in _table(env, "extraction_model_acks")] == [MODEL_A]
    assert _rows(env) == []


def test_facts_of_two_models_are_mixed_never_one_of_them(env, monkeypatch):
    _pre_ledger(env, monkeypatch)
    _sql(env, "UPDATE memory_facts SET extraction_model = ? WHERE id = ?",
         (MODEL_B, _fact_ids(env)[0]))
    for configured in (MODEL_A, MODEL_B):                 # the majority is not picked either
        items = _backlog(env, configured)
        assert len(items) == 1, configured
        it = items[0]
        assert it["model"] == f"mixed({MODEL_A},{MODEL_B})"
        assert it["models"] == {MODEL_A: 3, MODEL_B: 1}
        assert it["model_source"] == "facts"
        assert "1 mixed" in _notice(env, configured)


def test_a_partly_stamped_conversation_is_mixed_with_the_unstamped_count(env, monkeypatch):
    _pre_ledger(env, monkeypatch)
    _sql(env, "UPDATE memory_facts SET extraction_model = NULL WHERE id = ?",
         (_fact_ids(env)[0],))
    items = _backlog(env, MODEL_A)
    assert len(items) == 1
    assert items[0]["model"] == f"mixed({MODEL_A},unstamped)"
    assert items[0]["models"] == {MODEL_A: 3, "unstamped": 1}


def test_a_conversation_with_no_stamp_or_no_facts_is_unknown(env, monkeypatch):
    _pre_ledger(env, monkeypatch)
    _sql(env, "UPDATE memory_facts SET extraction_model = ''")
    items = _backlog(env, MODEL_A)
    assert [i["model"] for i in items] == ["unknown"]
    assert items[0]["model_source"] == "none"
    _sql(env, "DELETE FROM memory_facts")
    items = _backlog(env, MODEL_A)
    assert [i["model"] for i in items] == ["unknown"]
    notice = _notice(env, MODEL_A)
    assert "0 known" in notice and "1 unknown" in notice


def test_a_corpus_without_the_stamp_column_reads_unknown_and_is_not_altered(
        env, monkeypatch):
    _pre_ledger(env, monkeypatch)
    c = env.get_db()
    c.execute("CREATE TABLE mf AS SELECT id, fact_text, source_conversation_id, "
              "superseded_by FROM memory_facts")
    c.execute("DROP TABLE memory_facts")
    c.execute("ALTER TABLE mf RENAME TO memory_facts")
    c.commit()
    c.close()
    items = _backlog(env, MODEL_A)
    assert [i["model"] for i in items] == ["unknown"]
    c = env.get_db()
    cols = {r[1] for r in c.execute("PRAGMA table_info(memory_facts)")}
    c.close()
    assert "extraction_model" not in cols


def test_superseded_facts_still_count_toward_the_model(env, monkeypatch):
    _pre_ledger(env, monkeypatch)
    ids = _fact_ids(env)
    _sql(env, "UPDATE memory_facts SET extraction_model = ?, superseded_by = ? WHERE id = ?",
         (MODEL_B, ids[1], ids[0]))
    assert _backlog(env, MODEL_A)[0]["models"] == {MODEL_A: 3, MODEL_B: 1}


def test_an_acknowledged_mix_resurfaces_when_the_mix_changes(env, monkeypatch, capsys):
    _pre_ledger(env, monkeypatch)
    ids = _fact_ids(env)
    _sql(env, "UPDATE memory_facts SET extraction_model = ? WHERE id = ?", (MODEL_B, ids[0]))
    _cli(env, monkeypatch, "chunks", "ack-model", "--all")
    assert _backlog(env, MODEL_A)[0]["acknowledged_at"]
    _sql(env, "UPDATE memory_facts SET extraction_model = ? WHERE id = ?",
         ("claude-model-c", ids[1]))
    it = _backlog(env, MODEL_A)[0]
    assert it["model"] == f"mixed({MODEL_A},{MODEL_B},claude-model-c)"
    assert it["acknowledged_at"] is None


def test_the_backfill_reads_a_read_only_connection_and_writes_nothing(env, monkeypatch):
    from baselayer import chunk_ledger as cl
    _pre_ledger(env, monkeypatch)
    before = env.db.read_bytes()
    c = sqlite3.connect(f"file:{env.db.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        items = cl.model_backlog(c, MODEL_B)
        notice = cl.backlog_notice(c, MODEL_B)
    finally:
        c.close()
    assert [i["model"] for i in items] == [MODEL_A] and "1 known" in notice
    assert env.db.read_bytes() == before


# ---------------------------------------------------------------------------
# ledger rows settled before the ledger recorded the model
# ---------------------------------------------------------------------------

def test_an_unknown_ledger_row_takes_the_model_of_its_own_chunk_facts(env, monkeypatch):
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    _sql(env, "UPDATE extraction_chunks SET model = 'unknown'")
    assert _backlog(env, MODEL_A) == []                    # every chunk's facts say MODEL_A
    # one chunk's fact says MODEL_B: only that chunk is in the backlog
    rows = [r for r in _rows(env) if r["status"] == "done"]
    turn = json.loads(rows[0]["chunk_key"])[0][0]
    _sql(env, "UPDATE memory_facts SET extraction_model = ? WHERE source_turn_id = ?",
         (MODEL_B, turn))
    items = _backlog(env, MODEL_A)
    assert [(i["block_id"], i["model"], i["model_source"]) for i in items] == [
        (rows[0]["block_id"], MODEL_B, "facts")]
    # a row with a recorded model keeps it: the facts are not consulted
    _sql(env, "UPDATE extraction_chunks SET model = ? WHERE block_id = ?",
         (MODEL_A, rows[0]["block_id"]))
    assert _backlog(env, MODEL_A) == []


def test_the_legacy_block_takes_the_facts_no_other_chunk_covers(env, monkeypatch):
    from baselayer import chunk_ledger as cl
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    rows = [r for r in _rows(env) if r["status"] == "done"]
    # keep one chunk (recorded as MODEL_B); the rest of the conversation becomes the
    # pre-ledger legacy block, as the migration from extraction_chunks_failed writes it
    keep = rows[0]
    _sql(env, "DELETE FROM extraction_chunks WHERE block_id != ?", (keep["block_id"],))
    turn = json.loads(keep["chunk_key"])[0][0]
    _sql(env, "UPDATE memory_facts SET extraction_model = ? WHERE source_turn_id = ?",
         (MODEL_B, turn))
    _sql(env, "UPDATE extraction_chunks SET model = ? WHERE block_id = ?",
         (MODEL_B, keep["block_id"]))
    legacy = cl.block_id(CONV, cl.LEGACY_KEY, 0, 0)
    _sql(env, "INSERT INTO extraction_chunks (conversation_id, chunk_key, input_char_budget, "
              "turns_upto, block_id, path, status, attempts, facts_stored, created_at, "
              "updated_at, model) VALUES (?, '*', 0, 0, ?, 'legacy', 'done', 1, 3, 1, 1, "
              "'unknown')", (CONV, legacy))
    items = {i["block_id"]: i for i in _backlog(env, MODEL_A)}
    assert set(items) == {keep["block_id"]}                # the legacy block is MODEL_A
    assert items[keep["block_id"]]["model_source"] == "ledger"
    items = {i["block_id"]: i for i in _backlog(env, MODEL_B)}
    assert items[legacy]["model"] == MODEL_A and items[legacy]["models"] == {MODEL_A: 3}
