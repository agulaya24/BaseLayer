"""
A turn-contract chunk whose extraction call fails (an API error after retries, a refusal, an
unparseable or schema-invalid reply, a part that truncates again after re-chunking) is
recorded as FAILED, never as done:

- the good chunks of the conversation are still stored;
- the failed chunk is written to `extraction_chunks_failed` (in the same transaction), and on
  the batch path its custom_id is not marked in `extraction_chunks_done`;
- the run reports the true error count and exits non-zero, after its run record (and batch
  state) are written;
- the next run, and `--process --resume`, retry ONLY the failed chunk.

Sequential and batch turn paths. No API calls: fake clients only.
"""

import json
import re
import types

import pytest

from tests.test_api_usage_record import _usage
from tests.test_turn_batch_extract import _result, _state, benv  # noqa: F401
from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    CONV, V, _fact, _facts, _records, _seed, env)

SENT = "I keep a written log of every decision I make at work and read it back on Fridays"
TURNS = []
for i in range(4):
    TURNS.append((2 * i, "subject", "own_typed", "user", f"Entry {i}. " + (SENT + ". ") * 3))
    TURNS.append((2 * i + 1, "assistant", "assistant", "assistant", "Understood."))


def _caps(*a, **k):
    return {"max_facts": 40, "input_char_budget": 400}


def _facts_for(prompt):
    al = re.findall(r"\[(S\d+) \| SUBJECT, typed\]\n(Entry \d)", prompt)
    return [_fact(f"logs decisions {e}", [(a, e + ". " + SENT[:30])],
                  predicate="practices", category="habit") for a, e in al]


class LLM:
    """call_llm fake: returns the facts grounded in the prompt's subject turns, or None for
    the call numbers listed in `fail`."""

    def __init__(self, fail=()):
        self.prompts, self.fail = [], set(fail)

    def __call__(self, prompt, schema=None, retries=None, max_tokens=None):
        self.prompts.append(prompt)
        if len(self.prompts) in self.fail:
            return None
        return {"facts": _facts_for(prompt)}


def _setup(env, monkeypatch):
    _seed(env, turns=TURNS)
    c = env.get_db()
    c.execute("INSERT INTO import_state (conversation_id, source, needs_extraction, imported_at, "
              "status, turn_contract_version) VALUES (?,?,?,?,?,?)",
              (CONV, "chatgpt", 1, 50.0, "new", V))
    c.commit()
    c.close()
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "_get_extraction_caps", _caps)


def _failed_rows(env):
    c = env.get_db()
    try:
        rows = [dict(r) for r in c.execute("SELECT * FROM extraction_chunks_failed")]
    except Exception:
        rows = []
    c.close()
    return rows


def _log(env):
    c = env.get_db()
    r = c.execute("SELECT facts_extracted FROM extraction_log WHERE conversation_id = ?",
                  (CONV,)).fetchone()
    sel = [x[0] for x in env.ef._turn_conversations_to_process(c)]
    c.close()
    return (r[0] if r else None), sel


def _objects(env):
    return sorted(f["object_text"] for f in _facts(env))


ALL4 = [f"logs decisions Entry {i}" for i in range(4)]


# ---------------------------------------------------------------------------
# sequential
# ---------------------------------------------------------------------------

def test_sequential_failed_chunk_is_recorded_and_the_run_exits_nonzero(env, monkeypatch, capsys):
    _setup(env, monkeypatch)
    llm = LLM(fail={1})
    monkeypatch.setattr(env.ef, "call_llm", llm)
    with pytest.raises(SystemExit) as ei:
        env.ef.run_extraction()
    assert ei.value.code == 1
    assert len(llm.prompts) == 4
    assert _objects(env) == ALL4[1:]                    # the good chunks are stored
    rows = _failed_rows(env)
    assert len(rows) == 1 and rows[0]["conversation_id"] == CONV
    assert rows[0]["path"] == "sequential" and rows[0]["attempts"] == 1
    logged, sel = _log(env)
    assert logged == 3 and sel == [CONV]                # selected again for the retry
    rec = _records(env)[-1]                             # written before the exit
    assert rec["counts"]["chunks_failed"] == 1
    assert rec["counts"]["chunks_failed_open"] == 1
    assert [f["conversation_id"] for f in rec["failed_chunks"]] == [CONV]
    out = capsys.readouterr().out
    assert "Errors: 1" in out


def test_the_next_run_retries_only_the_failed_chunk(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", LLM(fail={1}))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    llm = LLM()
    monkeypatch.setattr(env.ef, "call_llm", llm)
    env.ef.run_extraction()                             # exits normally: nothing failed
    assert len(llm.prompts) == 1 and "Entry 0" in llm.prompts[0]
    assert _objects(env) == ALL4
    assert _failed_rows(env) == []
    logged, sel = _log(env)
    assert logged == 4 and sel == []                    # summed, not replaced
    rec = _records(env)[-1]
    assert rec["counts"]["chunks_retried"] == 1 and rec["counts"]["chunks_recovered"] == 1


def test_a_chunk_that_fails_again_keeps_its_row_and_counts_the_attempt(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", LLM(fail={1}))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    monkeypatch.setattr(env.ef, "call_llm", LLM(fail={1}))
    with pytest.raises(SystemExit) as ei:
        env.ef.run_extraction()
    assert ei.value.code == 1
    rows = _failed_rows(env)
    assert len(rows) == 1 and rows[0]["attempts"] == 2
    assert _objects(env) == ALL4[1:]


def test_an_api_error_after_retries_is_a_failed_chunk(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 40, "input_char_budget": 100000})

    class Boom:
        n = 0

        def create(self, **kw):
            Boom.n += 1
            raise ConnectionError("simulated network outage")

    monkeypatch.setattr(env.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(env.ef, "_get_anthropic_client",
                        lambda: types.SimpleNamespace(messages=Boom()))
    with pytest.raises(SystemExit) as ei:
        env.ef.run_extraction()
    assert ei.value.code == 1 and Boom.n >= 1
    assert len(_failed_rows(env)) == 1
    logged, sel = _log(env)
    assert logged == 0 and sel == [CONV]


def test_a_part_that_truncates_again_is_retried_at_a_smaller_budget(env, monkeypatch):
    from tests.test_rechunk_on_max_tokens import Scripted, _client
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 40, "input_char_budget": 1600})
    _client(monkeypatch, env.ef, Scripted(truncate_again=True))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    rows = _failed_rows(env)
    assert len(rows) == 1 and rows[0]["reason"] == "max_tokens"
    assert rows[0]["input_char_budget"] == 800 and rows[0]["turns_upto"] > 0
    stored = _objects(env)
    assert stored and stored != ALL4                    # the other part is stored
    msgs = Scripted()
    msgs.calls.append("earlier")                        # this run's calls do not truncate
    _client(monkeypatch, env.ef, msgs)
    env.ef.run_extraction()
    assert len(msgs.calls) == 2                         # one call: the failed part only
    assert _objects(env) == ALL4 and _failed_rows(env) == []


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------

def _batch_results(benv, bad=None, kind="errored"):
    """Results built from each submitted prompt; custom_id `bad` fails as `kind`."""
    def results(ids):
        out = []
        for req in benv.batches.submitted:
            cid = req["custom_id"]
            r = _result(cid, _facts_for(req["params"]["messages"][0]["content"]))
            r.result.message.usage = _usage()
            if cid == bad:
                if kind == "errored":
                    r.result.type = "errored"
                elif kind == "garbage":
                    r.result.message.content[-1].text = "not json at all {"
                elif kind == "not_a_list":
                    r.result.message.content[-1].text = json.dumps({"facts": "none"})
            out.append(r)
        return out
    return results


def _submit(benv, monkeypatch):
    _setup(benv, monkeypatch)
    benv.be.run_submit()
    ids = [r["custom_id"] for r in benv.batches.submitted]
    assert len(ids) == 4
    return ids


def _done(benv):
    c = benv.get_db()
    d = {r[0] for r in c.execute("SELECT custom_id FROM extraction_chunks_done")}
    c.close()
    return d


@pytest.mark.parametrize("kind", ["errored", "garbage", "not_a_list"])
def test_batch_failed_result_is_recorded_not_marked_done_and_exits_nonzero(benv, monkeypatch,
                                                                         kind):
    ids = _submit(benv, monkeypatch)
    benv.batches.results_for = _batch_results(benv, bad=ids[0], kind=kind)
    with pytest.raises(SystemExit) as ei:
        benv.be.run_process()
    assert ei.value.code == 1
    assert _done(benv) == set(ids[1:])                  # the failed custom_id is not done
    rows = _failed_rows(benv)
    assert len(rows) == 1 and rows[0]["path"] == "batch"
    assert _objects(benv) == ALL4[1:]
    st = _state(benv)                                   # saved before the exit
    assert st["status"] == "completed" and st["errors"] == 1
    logged, sel = _log(benv)
    assert logged == 3 and sel == [CONV]


def test_batch_resume_retries_only_the_failed_chunk(benv, monkeypatch):
    ids = _submit(benv, monkeypatch)
    benv.batches.results_for = _batch_results(benv, bad=ids[0])
    with pytest.raises(SystemExit):
        benv.be.run_process()
    llm = LLM()
    monkeypatch.setattr(benv.ef, "call_llm", llm)
    benv.be.run_process(resume=True)                    # exits normally
    assert len(llm.prompts) == 1 and "Entry 0" in llm.prompts[0]
    assert _objects(benv) == ALL4 and _failed_rows(benv) == []
    logged, _sel = _log(benv)
    assert logged == 4
    assert _state(benv)["errors"] == 0


def test_a_fresh_process_clears_the_failure_table(benv, monkeypatch):
    ids = _submit(benv, monkeypatch)
    benv.batches.results_for = _batch_results(benv, bad=ids[0])
    with pytest.raises(SystemExit):
        benv.be.run_process()
    benv.batches.results_for = _batch_results(benv)
    benv.be.run_process()
    assert _failed_rows(benv) == [] and _objects(benv) == ALL4


def test_incremental_submit_resubmits_only_the_failed_chunk(benv, monkeypatch):
    ids = _submit(benv, monkeypatch)
    benv.batches.results_for = _batch_results(benv, bad=ids[0])
    with pytest.raises(SystemExit):
        benv.be.run_process()
    first_create = benv.batches.create
    benv.batches.create = lambda requests: (first_create(requests),
                                            types.SimpleNamespace(id="batch-2"))[1]
    benv.be.run_submit(skip_extracted=True, turn_contract=True)
    reqs = benv.batches.submitted
    assert len(reqs) == 1 and "Entry 0" in reqs[0]["params"]["messages"][0]["content"]
    benv.batches.results_for = _batch_results(benv)
    benv.be.run_process(resume=True)
    assert _objects(benv) == ALL4 and _failed_rows(benv) == []
    logged, _sel = _log(benv)
    assert logged == 4


def test_a_batch_with_no_successful_result_exits_nonzero(benv, monkeypatch):
    _submit(benv, monkeypatch)
    benv.batches.retrieve = lambda bid: types.SimpleNamespace(
        processing_status="ended",
        request_counts=types.SimpleNamespace(succeeded=0, errored=4, canceled=0, expired=0,
                                             processing=0))
    with pytest.raises(SystemExit) as ei:
        benv.be.run_process()
    assert ei.value.code == 1
