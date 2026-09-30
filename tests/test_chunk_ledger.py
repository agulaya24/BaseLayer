"""
The chunk ledger (`extraction_chunks`): on the turn-contract paths, sequential and batch, every
chunk is its own checkpointed row (pending, done, failed, quarantined, split).

- A corpus extracted before the ledger existed has no rows. Its logged conversations count as
  done: no entry point (a run, --conv-id, --process --resume, an incremental submit) calls the
  model for them. These guards were written first and proven able to fail by a mutation that
  drops the pre-ledger read rule (the code before the ledger could not reach the hazard).
- Done chunks are never called again; a conversation re-runs only its chunks that are not done;
  a chunk whose input changed runs again.
- A chunk that fails its two retries is quarantined, a chunk that cannot be rebuilt is
  quarantined at once, and neither is retried automatically.
- extraction_log holds the sum of facts_stored over the done rows.
- `baselayer run` refuses to author over quarantined chunks without --accept-gaps, and the
  accepted gaps are stamped into each layer.

No API calls: fake clients only; a call where none is allowed raises.
"""

import json
import re
import types

import pytest

from tests.test_failed_chunks import (  # noqa: F401  (env, benv are fixtures)
    ALL4, CONV, LLM, SENT, _batch_results, _done, _log, _objects, _setup, _submit, benv, env)
from tests.test_turn_batch_extract import _state
from tests.test_turn_extraction import _fact


def _rows(env):
    c = env.get_db()
    try:
        return [dict(r) for r in c.execute(
            "SELECT * FROM extraction_chunks ORDER BY created_at, chunk_key")]
    except Exception:
        return []
    finally:
        c.close()


class NoCall:
    """A model client that must never be reached."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **k):
        self.calls += 1
        raise AssertionError("a model call was made where none is allowed")


def _forbid_calls(env, monkeypatch):
    guard = NoCall()
    monkeypatch.setattr(env.ef, "call_llm", guard)
    monkeypatch.setattr(env.ef, "_get_anthropic_client",
                        lambda: types.SimpleNamespace(messages=types.SimpleNamespace(
                            create=guard)))
    return guard


def _snapshot(env):
    c = env.get_db()
    facts = sorted(r[0] for r in c.execute("SELECT id FROM memory_facts"))
    log = sorted(tuple(r) for r in c.execute(
        "SELECT conversation_id, facts_extracted FROM extraction_log"))
    c.close()
    return facts, log


def _drop_ledger(env):
    """What a corpus extracted before the ledger looks like: facts and extraction_log, no
    chunk rows."""
    c = env.get_db()
    c.execute("DROP TABLE IF EXISTS extraction_chunks")
    c.commit()
    c.close()


def _extract_clean(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", LLM())
    env.ef.run_extraction()
    assert _objects(env) == ALL4


# ---------------------------------------------------------------------------
# BLOCKING HAZARD: a pre-ledger corpus makes zero calls on every entry point
# ---------------------------------------------------------------------------

def test_pre_ledger_corpus_sequential_run_makes_no_call(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    _drop_ledger(env)
    before = _snapshot(env)
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction()                               # exits normally
    assert guard.calls == 0 and _snapshot(env) == before


def test_pre_ledger_conversation_named_by_conv_id_makes_no_call(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    _drop_ledger(env)
    before = _snapshot(env)
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction(conv_id=CONV)
    env.ef.run_extraction(conv_ids=[CONV])
    assert guard.calls == 0 and _snapshot(env) == before
    assert _rows(env) == []                               # nothing written for it either


def _batch_extract_with_a_truncation(benv, monkeypatch):
    """A processed batch whose results include a max_tokens stop: reprocessing any result
    of it would make a synchronous call."""
    ids = _submit(benv, monkeypatch)
    good = _batch_results(benv)

    def results(_ids):
        out = good(_ids)
        out[1].result.message.stop_reason = "max_tokens"
        return out
    benv.batches.results_for = results
    monkeypatch.setattr(benv.ef, "call_llm", PartsLLM())
    benv.be.run_process()
    return ids


class PartsLLM(LLM):
    """Like LLM, and also grounds a fact in the first part of a subject turn that a re-chunk
    at half the budget split into parts."""

    def __call__(self, prompt, schema=None, retries=None, max_tokens=None):
        self.prompts.append(prompt)
        al = re.findall(r"\[(S\d+) \| SUBJECT, typed(?:, part 1 of \d+)?\]\n(Entry \d)",
                        prompt)
        return {"facts": [_fact(f"logs decisions {e}", [(a, e + ". " + SENT[:30])],
                                predicate="practices", category="habit") for a, e in al]}


def test_pre_ledger_corpus_batch_resume_makes_no_call(benv, monkeypatch):
    ids = _batch_extract_with_a_truncation(benv, monkeypatch)
    assert _done(benv) == set(ids)
    _drop_ledger(benv)
    before = _snapshot(benv)
    guard = _forbid_calls(benv, monkeypatch)
    benv.be.run_process(resume=True)                      # exits normally
    assert guard.calls == 0 and _snapshot(benv) == before


def test_pre_ledger_corpus_incremental_submit_sends_nothing(benv, monkeypatch):
    _batch_extract_with_a_truncation(benv, monkeypatch)
    _drop_ledger(benv)
    before = _snapshot(benv)
    guard = _forbid_calls(benv, monkeypatch)
    sent = []
    benv.batches.create = lambda requests: sent.append(requests) or types.SimpleNamespace(
        id="batch-2")
    benv.be.run_submit(skip_extracted=True, turn_contract=True)
    assert sent == [] and guard.calls == 0 and _snapshot(benv) == before


# ---------------------------------------------------------------------------
# every chunk is a row; the logged count is the sum of the done rows
# ---------------------------------------------------------------------------

def test_every_chunk_is_a_done_row_and_the_log_is_their_sum(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    rows = _rows(env)
    assert len(rows) == 4 and {r["status"] for r in rows} == {"done"}
    assert all(r["input_hash"] and r["attempts"] == 1 for r in rows)
    assert [r["facts_stored"] for r in rows] == [1, 1, 1, 1]
    logged, sel = _log(env)
    assert logged == sum(r["facts_stored"] for r in rows) == 4 and sel == []


def test_batch_chunks_are_rows_and_a_split_keeps_its_parts(benv, monkeypatch):
    _batch_extract_with_a_truncation(benv, monkeypatch)
    rows = _rows(benv)
    split = [r for r in rows if r["status"] == "split"]
    assert len(split) == 1
    parts = [r for r in rows if r["parent_id"] == split[0]["block_id"]]
    assert parts and {r["status"] for r in parts} == {"done"}
    assert all(r["input_char_budget"] == split[0]["input_char_budget"] // 2 for r in parts)
    assert {r["status"] for r in rows} == {"done", "split"}
    assert _objects(benv) == ALL4
    logged, _sel = _log(benv)
    assert logged == sum(r["facts_stored"] for r in rows if r["status"] == "done")


# ---------------------------------------------------------------------------
# done chunks are never re-run; changed input is
# ---------------------------------------------------------------------------

def test_done_chunks_are_never_called_again(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    before = _snapshot(env)
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction(conv_id=CONV)                   # explicitly named: still nothing
    assert guard.calls == 0 and _snapshot(env) == before


class Interrupt(BaseException):
    """Stands in for anything that kills a run mid-conversation (the spend ceiling, a crash)."""


def test_an_interrupted_conversation_resumes_at_its_first_unsettled_chunk(env, monkeypatch):
    _setup(env, monkeypatch)
    llm = LLM()

    def dies_on_third(prompt, **kw):
        if len(llm.prompts) == 2:
            raise Interrupt()
        return llm(prompt, **kw)
    monkeypatch.setattr(env.ef, "call_llm", dies_on_third)
    with pytest.raises(Interrupt):
        env.ef.run_extraction()
    assert _objects(env) == ALL4[:2]                      # chunks 1 and 2 were checkpointed
    assert [r["status"] for r in _rows(env)] == ["done", "done", "pending", "pending"]
    llm2 = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm2)
    env.ef.run_extraction()
    assert [p.count("Entry") for p in llm2.prompts] and len(llm2.prompts) == 2
    assert "Entry 2" in llm2.prompts[0] and "Entry 3" in llm2.prompts[1]
    assert _objects(env) == ALL4
    logged, sel = _log(env)
    assert logged == 4 and sel == []


def test_a_chunk_whose_input_changed_runs_again_alone(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    c = env.get_db()
    c.execute("UPDATE turns SET text = ? WHERE turn_id = ?",
              ("Entry 3. " + (SENT + ". ") * 2 + "And on Mondays.", f"{CONV}:6"))
    c.commit()
    c.close()
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction(conv_id=CONV)
    assert len(llm.prompts) == 1 and "And on Mondays" in llm.prompts[0]
    rows = _rows(env)
    assert len(rows) == 4 and {r["status"] for r in rows} == {"done"}


# ---------------------------------------------------------------------------
# quarantine
# ---------------------------------------------------------------------------

class FailsOn(LLM):
    """Returns None (an unusable reply) for every prompt whose citable BODY shows `text` (an
    earlier turn shown as context does not count)."""

    def __init__(self, text):
        super().__init__()
        self.text = text

    def __call__(self, prompt, schema=None, retries=None, max_tokens=None):
        if f"| SUBJECT, typed]\n{self.text}" in prompt:
            self.prompts.append(prompt)
            return None
        return super().__call__(prompt, schema, retries, max_tokens)


def test_a_chunk_that_fails_its_two_retries_is_quarantined(env, monkeypatch, capsys):
    _setup(env, monkeypatch)
    for run in (1, 2):
        monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
        with pytest.raises(SystemExit) as ei:
            env.ef.run_extraction()
        assert ei.value.code == 1
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    env.ef.run_extraction()                               # third failure: quarantined, exit 0
    q = [r for r in _rows(env) if r["status"] == "quarantined"]
    assert len(q) == 1 and q[0]["attempts"] == 3
    assert "unusable_response" in q[0]["last_error"]
    assert "QUARANTINED" in capsys.readouterr().out
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction()                               # not retried automatically
    assert guard.calls == 0
    logged, sel = _log(env)
    assert logged == 3 and sel == []


def _pre_ledger_failed_row(env, monkeypatch, chunk_key, reason="unusable_response"):
    """A corpus written by the failed-chunks code (bef3733): the old table, no ledger."""
    _extract_clean(env, monkeypatch)
    _drop_ledger(env)
    c = env.get_db()
    c.execute("""CREATE TABLE extraction_chunks_failed (
        conversation_id TEXT NOT NULL, chunk_key TEXT NOT NULL,
        input_char_budget INTEGER NOT NULL, turns_upto INTEGER NOT NULL, plan TEXT NOT NULL,
        path TEXT NOT NULL, reason TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
        batch_id TEXT, recorded_at REAL NOT NULL,
        PRIMARY KEY (conversation_id, chunk_key, input_char_budget, turns_upto))""")
    c.execute("INSERT INTO extraction_chunks_failed VALUES (?,?,?,?,?,?,?,?,?,?)",
              (CONV, chunk_key, 400, 0, json.dumps({"fact_count_mode": "capped"}),
               "sequential", reason, 1, None, 1.0))
    c.commit()
    c.close()


def test_a_chunk_that_cannot_be_rebuilt_is_quarantined_at_once(env, monkeypatch):
    _pre_ledger_failed_row(env, monkeypatch, json.dumps([f"{CONV}:99"]))
    before = _snapshot(env)
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction()                               # exits normally: nothing open
    assert guard.calls == 0 and _snapshot(env)[0] == before[0]
    q = [r for r in _rows(env) if r["status"] == "quarantined"]
    assert len(q) == 1 and q[0]["last_error"] == "not_reproducible"


def test_migration_keeps_the_logged_count_and_retries_only_the_failed_chunk(env, monkeypatch):
    # chunk 1's body is the first subject turn and its reply, in the old key format
    _pre_ledger_failed_row(env, monkeypatch, env.ef.chunk_key([f"{CONV}:0", f"{CONV}:1"]))
    c = env.get_db()
    c.execute("DELETE FROM memory_facts WHERE object_text = ?", (ALL4[0],))
    c.execute("UPDATE extraction_log SET facts_extracted = 3")
    c.commit()
    c.close()
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert len(llm.prompts) == 1 and "Entry 0" in llm.prompts[0]
    rows = {r["chunk_key"]: r for r in _rows(env)}
    assert rows["*"]["status"] == "done" and rows["*"]["facts_stored"] == 3   # the legacy block
    assert {r["status"] for r in rows.values()} == {"done"}
    logged, sel = _log(env)
    assert logged == 4 and sel == []
    assert _objects(env) == ALL4
    c = env.get_db()
    old = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'extraction_chunks_failed'")
    assert old.fetchone() is None
    c.close()


def test_a_not_reproducible_row_migrates_straight_to_quarantine(env):
    from baselayer import chunk_ledger as cl
    c = env.get_db()
    c.execute("CREATE TABLE extraction_chunks_failed (conversation_id TEXT, chunk_key TEXT, "
              "input_char_budget INTEGER, turns_upto INTEGER, plan TEXT, path TEXT, "
              "reason TEXT, attempts INTEGER, batch_id TEXT, recorded_at REAL)")
    c.execute("INSERT INTO extraction_chunks_failed VALUES (?,?,?,?,?,?,?,?,?,?)",
              ("c1", '["c1:0"]', 400, 0, "{}", "sequential", "not_reproducible", 2, None, 1.0))
    c.commit()
    assert cl.ensure_ledger(c) == 1
    r = cl.list_rows(c)
    assert [(x["status"], x["last_error"], x["attempts"]) for x in r] == [
        ("quarantined", "not_reproducible", 2)]
    c.close()


# ---------------------------------------------------------------------------
# the logged count: summed, never replaced (the --conv-id / --conv-ids bug)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["conv_id", "conv_ids"])
def test_naming_a_conversation_with_a_failed_chunk_retries_it_and_sums_the_count(
        env, monkeypatch, how):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction(**({"conv_id": CONV} if how == "conv_id" else {"conv_ids": [CONV]}))
    assert len(llm.prompts) == 1 and "Entry 0" in llm.prompts[0]
    logged, _sel = _log(env)
    assert logged == 4 and _objects(env) == ALL4


# ---------------------------------------------------------------------------
# reset, batch identity, the CLI and the authoring gate
# ---------------------------------------------------------------------------

def test_reset_clears_the_ledger_so_the_next_run_extracts_everything(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    monkeypatch.setattr("sys.argv", ["extract_facts.py", "--reset"])
    env.ef.main()
    assert _rows(env) == []
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert len(llm.prompts) == 4 and _objects(env) == ALL4


def test_a_log_reset_that_did_not_know_the_ledger_is_not_trusted(env, monkeypatch):
    """An older build's --reset (or a hand-cleared log) empties extraction_log and the facts
    but leaves the ledger: done rows without a log row are stale, so everything runs again."""
    _extract_clean(env, monkeypatch)
    c = env.get_db()
    c.execute("DELETE FROM extraction_log")
    c.execute("DELETE FROM memory_facts")
    c.commit()
    c.close()
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert len(llm.prompts) == 4 and _objects(env) == ALL4


def test_batch_results_settle_under_the_identity_they_were_submitted_with(benv, monkeypatch):
    ids = _submit(benv, monkeypatch)
    # the prompt changes between submit and process (an entity map edit, say) ...
    monkeypatch.setattr(benv.ef, "_get_known_entities_for_prompt", lambda: "Known: Sam (friend)")
    # ... and the change reaches every chunk's input hash (else this test proves nothing)
    submitted = {m["ledger"]["block_id"]: m["ledger"]["input_hash"]
                 for m in _state(benv)["chunk_map"].values()}
    c = benv.get_db()
    turns = benv.ef._tc.load_turns(c, CONV)
    now = {w.block_id: w.input_hash for w in benv.ef.plan_ledger_work(
        c, CONV, "Migration plan", turns, "chatgpt", project_session=False, fresh=True).work}
    c.close()
    assert set(now) == set(submitted) and all(now[b] != submitted[b] for b in now)
    benv.batches.results_for = _batch_results(benv)
    guard = _forbid_calls(benv, monkeypatch)
    benv.be.run_process()
    assert guard.calls == 0 and _objects(benv) == ALL4
    rows = _rows(benv)
    assert {r["block_id"]: r["input_hash"] for r in rows} == submitted
    assert len(ids) == len(rows) == 4 and {r["status"] for r in rows} == {"done"}


def test_a_batch_state_written_before_the_ledger_resumes_one_chunk_once(benv, monkeypatch):
    """bef3733 state: the failed result unconsumed, no ledger identity in chunk_map, the chunk
    in extraction_chunks_failed under the old key with the batch id. --resume calls it once,
    under one row, and nothing calls it again."""
    ids = _submit(benv, monkeypatch)
    benv.batches.results_for = _batch_results(benv, bad=ids[0])
    with pytest.raises(SystemExit):
        benv.be.run_process()
    path = benv.root / "data" / "database" / "batch_state.json"
    st = json.loads(path.read_text("utf-8"))
    for m in st["chunk_map"].values():
        m.pop("ledger")
    path.write_text(json.dumps(st), encoding="utf-8")
    c = benv.get_db()
    c.execute("DELETE FROM extraction_chunks_done WHERE custom_id = ?", (ids[0],))
    c.execute("DROP TABLE extraction_chunks")
    c.execute("""CREATE TABLE extraction_chunks_failed (
        conversation_id TEXT NOT NULL, chunk_key TEXT NOT NULL,
        input_char_budget INTEGER NOT NULL, turns_upto INTEGER NOT NULL, plan TEXT NOT NULL,
        path TEXT NOT NULL, reason TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
        batch_id TEXT, recorded_at REAL NOT NULL,
        PRIMARY KEY (conversation_id, chunk_key, input_char_budget, turns_upto))""")
    c.execute("INSERT INTO extraction_chunks_failed VALUES (?,?,?,?,?,?,?,?,?,?)",
              (CONV, benv.ef.chunk_key([f"{CONV}:0", f"{CONV}:1"]), 400, 0,
               json.dumps({"fact_count_mode": "capped"}), "batch", "errored", 1, "batch-1",
               1.0))
    c.commit()
    c.close()
    llm = LLM()
    monkeypatch.setattr(benv.ef, "call_llm", llm)
    benv.be.run_process(resume=True)                      # exits normally
    assert len(llm.prompts) == 1 and "Entry 0" in llm.prompts[0]
    chunk_rows = [r for r in _rows(benv) if r["chunk_key"] != "*"]
    assert [r["status"] for r in chunk_rows] == ["done"]
    assert _objects(benv) == ALL4
    guard = _forbid_calls(benv, monkeypatch)
    benv.ef.run_extraction()
    assert guard.calls == 0


def _cli(env, monkeypatch, *argv):
    import baselayer.cli as cli
    monkeypatch.setattr("sys.argv", ["baselayer", *argv])
    cli.main()


def test_chunks_cli_lists_requeues_and_quarantines(env, monkeypatch, capsys):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    failed = [r for r in _rows(env) if r["status"] == "failed"][0]
    capsys.readouterr()
    _cli(env, monkeypatch, "chunks", "list", "--status", "open")
    out = capsys.readouterr().out
    assert failed["block_id"] in out and "failed 1" in out and "done 3" in out

    _cli(env, monkeypatch, "chunks", "quarantine", failed["block_id"][:8], "--reason", "refusal")
    r = [x for x in _rows(env) if x["block_id"] == failed["block_id"]][0]
    assert r["status"] == "quarantined" and r["last_error"] == "manual: refusal"
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction()                               # exits normally, calls nothing
    assert guard.calls == 0

    _cli(env, monkeypatch, "chunks", "retry", failed["block_id"])
    r = [x for x in _rows(env) if x["block_id"] == failed["block_id"]][0]
    assert r["status"] == "pending" and r["attempts"] == 0
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert len(llm.prompts) == 1 and _objects(env) == ALL4


def _quarantined_corpus(env, monkeypatch):
    _setup(env, monkeypatch)
    for _ in range(3):
        monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
        try:
            env.ef.run_extraction()
        except SystemExit:
            pass
    assert [r["status"] for r in _rows(env)].count("quarantined") == 1


def test_run_refuses_to_author_over_quarantined_chunks_without_accept_gaps(env, monkeypatch):
    import baselayer.cli as cli
    _quarantined_corpus(env, monkeypatch)
    with pytest.raises(SystemExit) as ei:
        cli._coverage_gate(types.SimpleNamespace(accept_gaps=False))
    assert ei.value.code == 1
    import baselayer.author_layers as al
    monkeypatch.setattr(al, "COVERAGE_GAPS_ACCEPTED", False)
    cli._coverage_gate(types.SimpleNamespace(accept_gaps=True))    # passes
    assert al.COVERAGE_GAPS_ACCEPTED is True


def test_run_stops_before_authoring_and_the_accepted_gaps_are_stamped(env, monkeypatch, tmp_path):
    import baselayer.cli as cli
    import baselayer.author_layers as al
    _quarantined_corpus(env, monkeypatch)
    calls = []
    f = tmp_path / "export.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr("baselayer.config.database_initialized", lambda: True)
    monkeypatch.setattr(cli, "cmd_estimate", lambda a: None)
    monkeypatch.setattr(cli, "cmd_extract", lambda a: calls.append("extract"))
    monkeypatch.setattr(cli, "cmd_author", lambda a: calls.append("author"))
    monkeypatch.setattr(cli, "_run_traceability", lambda: calls.append("trace"))
    monkeypatch.setattr("baselayer.config.DATABASE_FILE", env.db)
    args = types.SimpleNamespace(file=str(f), yes=True, document_mode=False, limit=None,
                                 accept_gaps=False)
    with pytest.raises(SystemExit):
        cli.cmd_run(args)
    assert calls == ["extract"]                           # stopped before authoring

    calls.clear()
    monkeypatch.setattr(al, "COVERAGE_GAPS_ACCEPTED", False)
    args.accept_gaps = True
    cli.cmd_run(args)
    assert calls == ["extract", "author", "trace"]
    # the layer written under that acceptance points to a gaps manifest beside it, which
    # states the gaps (design decision 2026-09-29: stated, but not inside the spec text)
    monkeypatch.setattr(al, "get_db", env.get_db)
    monkeypatch.setattr(al, "IDENTITY_LAYERS_DIR", tmp_path / "layers")
    out = tmp_path / "layers" / "core.md"
    al.store_layer("CORE", "**M1 - Direct.** Answers first.", out)
    head = out.read_text(encoding="utf-8").split("## Injectable Block")[0]
    q = [r for r in _rows(env) if r["status"] == "quarantined"][0]
    assert q["block_id"] not in head and CONV not in head
    assert "coverage_gaps_accepted: true" in head and "coverage_gaps_count: 1" in head
    name = [l for l in head.splitlines()
            if l.startswith("coverage_gaps_manifest:")][0].split()[1]
    m = json.loads((out.parent / name).read_text(encoding="utf-8"))
    assert m["accepted"] is True and [g["block_id"] for g in m["gaps"]] == [q["block_id"]]
    assert m["gaps"][0]["conversation_id"] == CONV
    assert "unusable_response" in m["gaps"][0]["last_error"]
