"""
The chunk ledger's three standing decisions (design decision 2026-09-29):

1. A MODEL CHANGE never re-runs anything. Every ledger row records the extraction model that
   settled it (work with no recorded model takes it from its facts' stamps, or reads `unknown`
   when none carries one: test_chunk_ledger_backfill.py); the input
   hash stays model-free. Done work made by another model is a running BACKLOG: listed by
   `baselayer chunks list --backlog`, announced in one line at the end of a run, acknowledged
   (recorded with a timestamp) by `baselayer chunks ack-model`, and re-extracted only by a
   separate, deliberate action.
2. Only CONTENT failures count toward quarantine (a truncated, unparseable or refused reply,
   the API rejecting the input). ACCESS failures (network, timeout, 429, 5xx, overloaded,
   auth, a batch result that expired or was canceled) leave the chunk failed and retryable,
   with the error, and do not add an attempt.
3. Naming an already extracted conversation (--conversation / conv_ids) re-extracts nothing:
   it prints why and records a REVIEW backlog entry (conversation, requested at, reason),
   listed by `baselayer chunks list --reviews`.

No API calls: fake clients only; a call where none is allowed raises.
"""

import json
import types

import anthropic
import httpx
import pytest

from tests.test_chunk_ledger import (  # noqa: F401  (env, benv are fixtures)
    FailsOn, _cli, _drop_ledger, _extract_clean, _forbid_calls, _rows, _snapshot)
from tests.test_failed_chunks import (  # noqa: F401
    ALL4, CONV, LLM, SENT, _batch_results, _log, _objects, _setup, _submit, benv, env)
from tests.test_turn_extraction import _fact
from tests.test_api_usage_record import _usage

MODEL_A = "claude-model-a"
MODEL_B = "claude-model-b"


def _use_model(env, monkeypatch, name):
    import baselayer.batch_extract as be
    monkeypatch.setattr(env.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(env.ef, "EXTRACTION_API_MODEL", name)
    monkeypatch.setattr(be, "EXTRACTION_API_MODEL", name, raising=False)


def _table(env, name):
    c = env.get_db()
    try:
        return [dict(r) for r in c.execute(f"SELECT * FROM {name}")]
    except Exception:
        return []
    finally:
        c.close()


# ---------------------------------------------------------------------------
# 1. the model: recorded on every row, a change is a backlog, never a re-run
# ---------------------------------------------------------------------------

def test_every_row_records_the_model_that_extracted_it(env, monkeypatch):
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    rows = _rows(env)
    assert len(rows) == 4 and {r["model"] for r in rows} == {MODEL_A}


def test_a_batch_row_records_the_model_it_was_submitted_with(benv, monkeypatch):
    _use_model(benv, monkeypatch, MODEL_A)
    _submit(benv, monkeypatch)
    _use_model(benv, monkeypatch, MODEL_B)            # config changes before --process
    benv.batches.results_for = _batch_results(benv)
    benv.be.run_process()
    rows = _rows(benv)
    assert len(rows) == 4 and {r["model"] for r in rows} == {MODEL_A}


def test_a_model_change_reruns_nothing_and_becomes_an_acknowledgeable_backlog(
        env, monkeypatch, capsys):
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    before = _snapshot(env)
    _use_model(env, monkeypatch, MODEL_B)
    guard = _forbid_calls(env, monkeypatch)
    capsys.readouterr()
    env.ef.run_extraction()                               # exits normally
    assert guard.calls == 0 and _snapshot(env) == before
    out = capsys.readouterr().out
    notice = [l for l in out.splitlines() if "Model backlog" in l]
    assert len(notice) == 1 and "4 done" in notice[0] and MODEL_B in notice[0]
    assert "4 not acknowledged" in notice[0]
    assert {r["model"] for r in _rows(env)} == {MODEL_A}  # nothing was rewritten
    # a done conversation is only re-planned when named: its done chunks still hold
    env.ef.run_extraction(conv_id=CONV)
    assert guard.calls == 0 and _snapshot(env) == before
    capsys.readouterr()

    _cli(env, monkeypatch, "chunks", "list", "--backlog")
    out = capsys.readouterr().out
    assert all(r["block_id"] in out for r in _rows(env)) and MODEL_A in out

    _cli(env, monkeypatch, "chunks", "ack-model", "--all", "--note", "seen, not yet")
    acks = _table(env, "extraction_model_acks")
    assert len(acks) == 4 and {a["configured_model"] for a in acks} == {MODEL_B}
    assert all(a["acknowledged_at"] and a["model"] == MODEL_A for a in acks)
    assert {a["note"] for a in acks} == {"seen, not yet"}

    capsys.readouterr()
    env.ef.run_extraction()
    assert guard.calls == 0 and _snapshot(env) == before
    notice = [l for l in capsys.readouterr().out.splitlines() if "Model backlog" in l]
    assert len(notice) == 1 and "0 not acknowledged" in notice[0]
    _cli(env, monkeypatch, "chunks", "list", "--backlog")
    assert "acknowledged" in capsys.readouterr().out

    # a second model change resurfaces it: the acknowledgement was for MODEL_B
    _use_model(env, monkeypatch, "claude-model-c")
    capsys.readouterr()
    env.ef.run_extraction()
    notice = [l for l in capsys.readouterr().out.splitlines() if "Model backlog" in l]
    assert "4 not acknowledged" in notice[0]
    assert guard.calls == 0


def test_no_backlog_notice_when_the_model_is_unchanged(env, monkeypatch, capsys):
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    guard = _forbid_calls(env, monkeypatch)
    capsys.readouterr()
    env.ef.run_extraction()
    assert guard.calls == 0 and "Model backlog" not in capsys.readouterr().out


def test_pre_ledger_conversations_are_backlog_of_unknown_model_without_writing_rows(
        env, monkeypatch, capsys):
    _use_model(env, monkeypatch, MODEL_A)
    _extract_clean(env, monkeypatch)
    _drop_ledger(env)
    # facts with no model stamp: nothing to backfill from (test_chunk_ledger_backfill.py has
    # the stamped cases)
    c = env.get_db()
    c.execute("UPDATE memory_facts SET extraction_model = NULL")
    c.commit()
    c.close()
    capsys.readouterr()
    _cli(env, monkeypatch, "chunks", "list", "--backlog")
    out = capsys.readouterr().out
    assert CONV in out and "unknown" in out
    assert _rows(env) == []                               # a listing writes nothing
    guard = _forbid_calls(env, monkeypatch)
    env.ef.run_extraction()
    assert guard.calls == 0
    notice = [l for l in capsys.readouterr().out.splitlines() if "Model backlog" in l]
    assert len(notice) == 1 and "1 unknown" in notice[0]
    _cli(env, monkeypatch, "chunks", "ack-model", "--all")
    assert [a["model"] for a in _table(env, "extraction_model_acks")] == ["unknown"]
    assert _rows(env) == []                               # still no ledger row for it


def test_an_older_ledger_without_the_new_columns_is_read_and_then_migrated(env, monkeypatch):
    from baselayer import chunk_ledger as cl
    _extract_clean(env, monkeypatch)
    old_cols = ("conversation_id, chunk_key, input_char_budget, turns_upto, block_id, "
                "parent_id, input_hash, plan, path, status, attempts, last_error, "
                "facts_stored, batch_id, created_at, updated_at")
    c = env.get_db()
    c.execute(f"CREATE TABLE old_ledger AS SELECT {old_cols} FROM extraction_chunks")
    c.execute("DROP TABLE extraction_chunks")
    c.execute("ALTER TABLE old_ledger RENAME TO extraction_chunks")
    c.commit()
    # the readers the authoring gate uses work on it, and write nothing
    assert cl.status_counts(c)["done"] == 4 and cl.coverage_gaps(c) == []
    assert len(cl.list_rows(c)) == 4
    assert "model" not in {r[1] for r in c.execute("PRAGMA table_info(extraction_chunks)")}
    cl.ensure_ledger(c)
    assert {r["model"] for r in cl.list_rows(c)} == {"unknown"}
    c.close()


def test_the_input_hash_does_not_cover_the_model(env, monkeypatch):
    _setup(env, monkeypatch)
    c = env.get_db()
    turns = env.ef._tc.load_turns(c, CONV)
    c.close()
    base = env.ef.turn_extraction_plan(turns, "chatgpt")
    ch = [x for x in env.ef.build_turn_chunks(turns, "chatgpt", base["input_char_budget"])
          if x.has_citable][0]
    _use_model(env, monkeypatch, MODEL_A)
    a = env.ef.chunk_input_hash("t", ch, base, False)
    _use_model(env, monkeypatch, MODEL_B)
    assert env.ef.chunk_input_hash("t", ch, base, False) == a


# ---------------------------------------------------------------------------
# 2. access failures never count toward quarantine; content failures do
# ---------------------------------------------------------------------------

_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status(cls, code):
    return cls(message=f"status {code}", response=httpx.Response(code, request=_REQ), body=None)


ACCESS = {
    "connection": lambda: anthropic.APIConnectionError(request=_REQ),
    "timeout": lambda: anthropic.APITimeoutError(request=_REQ),
    "429": lambda: _status(anthropic.RateLimitError, 429),
    "500": lambda: _status(anthropic.InternalServerError, 500),
    "529_overloaded": lambda: _status(anthropic.APIStatusError, 529),
    "401_auth": lambda: _status(anthropic.AuthenticationError, 401),
    "builtin_connection": lambda: ConnectionError("simulated network outage"),
}


class Raises:
    """Anthropic messages fake: every call raises `make()`."""

    def __init__(self, make):
        self.make, self.n = make, 0

    def create(self, **kw):
        self.n += 1
        raise self.make()


def _client(env, monkeypatch, msgs):
    monkeypatch.setattr(env.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(env.ef, "_get_anthropic_client",
                        lambda: types.SimpleNamespace(messages=msgs))


@pytest.mark.parametrize("kind", sorted(ACCESS))
def test_an_outage_never_quarantines_a_chunk(env, monkeypatch, kind):
    _setup(env, monkeypatch)
    for _ in range(4):                                    # more runs than the attempt limit
        msgs = Raises(ACCESS[kind])
        _client(env, monkeypatch, msgs)
        with pytest.raises(SystemExit) as ei:
            env.ef.run_extraction()
        assert ei.value.code == 1 and msgs.n >= 1
    rows = _rows(env)
    assert "quarantined" not in {r["status"] for r in rows}
    failed = [r for r in rows if r["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["attempts"] == 0 and failed[0]["access_errors"] == 4
    assert failed[0]["last_error"].startswith("access:")
    llm = LLM()                                           # the outage ends
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert _objects(env) == ALL4 and {r["status"] for r in _rows(env)} == {"done"}


def test_the_api_rejecting_the_input_counts_toward_quarantine(env, monkeypatch):
    _setup(env, monkeypatch)
    for run in range(3):
        _client(env, monkeypatch, Raises(lambda: _status(anthropic.BadRequestError, 400)))
        try:
            env.ef.run_extraction()
        except SystemExit:
            pass
    q = [r for r in _rows(env) if r["status"] == "quarantined"]
    assert len(q) == 1 and q[0]["attempts"] == 3 and q[0]["access_errors"] == 0


def test_an_unusable_reply_still_counts_toward_quarantine(env, monkeypatch):
    """Guard for the other side: a refused or unparseable reply (call_llm -> None) is content
    and still quarantines after three attempts."""
    _setup(env, monkeypatch)
    for _ in range(3):
        monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
        try:
            env.ef.run_extraction()
        except SystemExit:
            pass
    q = [r for r in _rows(env) if r["status"] == "quarantined"]
    assert len(q) == 1 and q[0]["attempts"] == 3 and q[0]["access_errors"] == 0


def test_a_reply_that_is_not_an_object_is_content_not_access(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", lambda *a, **k: ["not", "an", "object"])
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    failed = [r for r in _rows(env) if r["status"] == "failed"]
    assert failed and all(r["attempts"] == 1 and r["access_errors"] == 0 for r in failed)


class TruncateThenDown:
    """First call stops on max_tokens; every later call (the re-chunked parts) hits an
    outage."""

    def __init__(self):
        self.n = 0

    def create(self, **kw):
        self.n += 1
        if self.n == 1:
            blk = types.SimpleNamespace(type="text", text=json.dumps({"facts": []}))
            return types.SimpleNamespace(content=[blk], stop_reason="max_tokens",
                                         usage=_usage())
        raise anthropic.APIConnectionError(request=_REQ)


def test_an_outage_during_a_rechunk_leaves_its_parts_retryable(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 40, "input_char_budget": 1600})
    _client(env, monkeypatch, TruncateThenDown())
    with pytest.raises(SystemExit) as ei:                 # recorded, not a crash
        env.ef.run_extraction()
    assert ei.value.code == 1
    rows = _rows(env)
    split = [r for r in rows if r["status"] == "split"]
    parts = [r for r in rows if split and r["parent_id"] == split[0]["block_id"]]
    assert len(split) == 1 and parts
    assert {r["status"] for r in parts} == {"failed"}
    assert all(r["last_error"].startswith("access:") and r["access_errors"] == 1
               for r in parts)
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()
    assert _objects(env) == ALL4


def _errored(benv, bad, rtype, etype=None):
    good = _batch_results(benv)

    def results(ids):
        out = good(ids)
        for r in out:
            if r.custom_id == bad:
                r.result.type = rtype
                if etype:
                    r.result.error = types.SimpleNamespace(
                        type="error", error=types.SimpleNamespace(type=etype, message="x"))
        return out
    return results


@pytest.mark.parametrize("rtype,etype,counted", [
    ("errored", "overloaded_error", False),
    ("errored", "api_error", False),
    ("errored", "rate_limit_error", False),
    ("expired", None, False),
    ("canceled", None, False),
    ("errored", "invalid_request_error", True),
])
def test_batch_access_failures_do_not_count(benv, monkeypatch, rtype, etype, counted):
    ids = _submit(benv, monkeypatch)
    benv.batches.results_for = _errored(benv, ids[0], rtype, etype)
    with pytest.raises(SystemExit):
        benv.be.run_process()
    failed = [r for r in _rows(benv) if r["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["attempts"] == (1 if counted else 0)
    assert failed[0]["access_errors"] == (0 if counted else 1)
    assert failed[0]["last_error"].startswith("access:") is (not counted)
    llm = LLM()                                           # --resume retries it, once
    monkeypatch.setattr(benv.ef, "call_llm", llm)
    benv.be.run_process(resume=True)
    assert len(llm.prompts) == 1 and _objects(benv) == ALL4


# ---------------------------------------------------------------------------
# 3. naming a finished conversation: flagged for review, never re-extracted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pre_ledger", [False, True])
@pytest.mark.parametrize("how", ["conv_id", "conv_ids"])
def test_naming_a_finished_conversation_records_a_review_entry_and_calls_nothing(
        env, monkeypatch, capsys, how, pre_ledger):
    _extract_clean(env, monkeypatch)
    if pre_ledger:
        _drop_ledger(env)
    before = _snapshot(env)
    rows_before = _rows(env)
    guard = _forbid_calls(env, monkeypatch)
    capsys.readouterr()
    named = {"conv_id": CONV} if how == "conv_id" else {"conv_ids": [CONV]}
    env.ef.run_extraction(review_reason="facts look wrong", **named)
    assert guard.calls == 0 and _snapshot(env) == before and _rows(env) == rows_before
    out = capsys.readouterr().out
    assert "not re-extracted" in out and CONV in out
    rev = _table(env, "extraction_review_requests")
    assert len(rev) == 1 and rev[0]["conversation_id"] == CONV
    assert rev[0]["reason"] == "facts look wrong" and rev[0]["requested_at"] > 0
    _cli(env, monkeypatch, "chunks", "list", "--reviews")
    out = capsys.readouterr().out
    assert CONV in out and "facts look wrong" in out


def test_the_reason_flag_reaches_the_review_entry(env, monkeypatch):
    _extract_clean(env, monkeypatch)
    guard = _forbid_calls(env, monkeypatch)
    monkeypatch.setattr("sys.argv", ["extract_facts.py", "--conversation", CONV,
                                     "--reason", "boundary looks off"])
    env.ef.main()
    assert guard.calls == 0
    assert [r["reason"] for r in _table(env, "extraction_review_requests")] == [
        "boundary looks off"]


def test_naming_an_unfinished_conversation_runs_it_and_records_no_review(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction(conv_id=CONV)
    assert len(llm.prompts) == 1 and _objects(env) == ALL4
    assert _table(env, "extraction_review_requests") == []
