"""
Turn-contract extraction on the BATCH path (run_submit / run_process), with a
fake Batches client. The batch path must enforce the same gate as the
sequential path, or it is a bypass. No API calls; nothing written outside
tmp_path.
"""

import json
import sys
import types

import pytest

from tests.test_turn_extraction import (  # shared synthetic corpus and fakes
    CONV, TURN_FACTS, LEGACY_FACTS, TURNS, V, FakeClient, FakeCollection, FakeST,
    _facts, _records, _seed, _stamp_a_gated_fact, env,  # noqa: F401  (env is a fixture)
)


def _block(kind, **kw):
    return types.SimpleNamespace(type=kind, **kw)


def _result(custom_id, facts, *, thinking_first=True, rtype="succeeded", stop="end_turn"):
    blocks = [_block("text", text=json.dumps({"facts": facts}))]
    if thinking_first:
        blocks.insert(0, _block("thinking", thinking="considering"))
    msg = types.SimpleNamespace(content=blocks, stop_reason=stop)
    return types.SimpleNamespace(custom_id=custom_id,
                                 result=types.SimpleNamespace(type=rtype, message=msg))


class FakeBatches:
    def __init__(self):
        self.submitted = None
        self.results_for = None      # callable(custom_ids) -> list of results
        self.fail_downloads = 0

    def create(self, requests):
        self.submitted = requests
        return types.SimpleNamespace(id="batch-1")

    def retrieve(self, batch_id):
        n = len(self.submitted or [])
        return types.SimpleNamespace(
            processing_status="ended",
            request_counts=types.SimpleNamespace(succeeded=n, errored=0, canceled=0,
                                                 expired=0, processing=0))

    def results(self, batch_id):
        if self.fail_downloads:
            self.fail_downloads -= 1
            raise RuntimeError("peer closed connection without sending complete message body")
        return iter(self.results_for([r["custom_id"] for r in self.submitted]))


class FakeChromaClient(FakeClient):
    def delete_collection(self, name):
        FakeClient.collection = None

    def get_or_create_collection(self, name, metadata=None):
        if FakeClient.collection is None:
            FakeClient.collection = FakeCollection()
        return FakeClient.collection


@pytest.fixture
def benv(env, monkeypatch):
    import baselayer.batch_extract as be
    import baselayer.api_client as api_client
    batches = FakeBatches()
    client = types.SimpleNamespace(messages=types.SimpleNamespace(batches=batches))
    monkeypatch.setattr(be, "get_db", env.get_db)
    monkeypatch.setattr(be, "_get_anthropic_client", lambda: client)
    monkeypatch.setattr(api_client, "get_embedding_model", lambda: FakeST("x"))
    monkeypatch.setitem(sys.modules, "chromadb",
                        types.SimpleNamespace(PersistentClient=FakeChromaClient))
    env.be, env.batches = be, batches
    return env


def _state(benv):
    return json.loads((benv.root / "data" / "database" / "batch_state.json").read_text("utf-8"))


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------

def test_turn_submit_builds_turn_prompts_and_keeps_no_text_in_state(benv, monkeypatch):
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()
    reqs = benv.batches.submitted
    assert len(reqs) == 1 and reqs[0]["custom_id"] == CONV
    content = reqs[0]["params"]["messages"][0]["content"]
    assert "[S2 | SUBJECT, typed]" in content and "[ASSISTANT | not citable]" in content
    assert "evidence_spans" in content                     # the turn schema, not the legacy one
    # default fact_count_mode `coverage`: no count in the prompt, and the output budget is
    # sized from the chunk's citable characters (the capped budget: the test below)
    assert "Extract up to" not in content
    citable = sum(len(t[4]) for t in TURNS if t[2] in ("own_typed", "own_dictated"))
    assert reqs[0]["params"]["max_tokens"] == benv.ef.turn_output_budget(citable)

    state = _state(benv)
    assert state["mode"] == "turn" and state["turn_contract_version"] == V
    assert state["stamps"]["general"]["code_path"] == "src/baselayer/extract_facts.py"
    meta = state["chunk_map"][CONV]
    assert [row[0] for row in meta["manifest"]["citable"]] == [f"{CONV}:0", f"{CONV}:2", f"{CONV}:5"]
    dumped = json.dumps(state)
    for _o, _sp, _vc, _role, text in TURNS:              # ids and offsets, never words
        assert text not in dumped


def test_turn_submit_refuses_missing_turns_before_spending(benv, monkeypatch):
    _seed(benv)
    _seed(benv, with_turns=False, conv="conv-no-turns")
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    with pytest.raises(benv.ef.TurnContractViolation, match="no rows in the turn table"):
        benv.be.run_submit()
    assert benv.batches.submitted is None


def test_legacy_submit_refuses_a_turn_contract_corpus(benv):
    _seed(benv)
    _stamp_a_gated_fact(benv)
    with pytest.raises(benv.ef.TurnContractViolation, match="--turn-contract"):
        benv.be.run_submit()
    assert benv.batches.submitted is None


# ---------------------------------------------------------------------------
# process: the gate is enforced here too
# ---------------------------------------------------------------------------

def _submit_turn(benv, monkeypatch, facts=TURN_FACTS):
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()
    benv.batches.results_for = lambda ids: [_result(i, facts) for i in ids]


def test_turn_process_gates_and_stores_grounded_facts_only(benv, monkeypatch):
    _submit_turn(benv, monkeypatch)
    monkeypatch.delenv("BASELAYER_TURN_CONTRACT")   # process follows the batch's own mode
    benv.be.run_process()
    facts = _facts(benv)
    assert sorted(f["object_text"] for f in facts) == [
        "delegating execution once a deadline is set", "short emails to vendors"]
    for f in facts:
        assert f["turn_contract_version"] == V and f["source_turn_id"]
        assert all(set(s) == {"turn_id", "span", "evidence_kind"}
                   for s in json.loads(f["evidence_spans"]))
    rec = _records(benv)[-1]
    assert rec["mode"] == "turn-batch"
    assert rec["gate_rejections"] == {"no_grounding": 1, "no_turn": 0,
                                      "not_own_voice": 1, "span_not_found": 1, "span_length": 0, "self_object": 0}
    assert FakeClient.collection.queries and all(
        w == {"$and": [{"turn_contract_version": V}, {"grounding": "prose"}]} for w in FakeClient.collection.queries)


def test_turn_process_mutation_without_gate_lets_assistant_fact_through(benv, monkeypatch):
    import baselayer.turn_contract as tc
    _submit_turn(benv, monkeypatch)

    def accept_all(raw, chunk, referent=None):
        g = tc.GateResult(candidates=len(raw))
        for f in raw:
            g.accepted.append(dict(f, source_turn_id="x", voice_class="x", inferred=False,
                                   evidence_spans=f.get("evidence_spans") or []))
        return g

    monkeypatch.setattr(tc, "gate_facts", accept_all)
    benv.be.run_process()
    assert any("polish" in f["object_text"] for f in _facts(benv))


def test_turn_process_raising_gate_propagates_and_commits_nothing(benv, monkeypatch):
    import baselayer.turn_contract as tc
    _submit_turn(benv, monkeypatch)

    def broken(raw, chunk, referent=None):
        raise RuntimeError("gate broke")

    monkeypatch.setattr(tc, "gate_facts", broken)
    with pytest.raises(RuntimeError, match="gate broke"):
        benv.be.run_process()
    assert _facts(benv) == []
    assert any("aborted" in n for n in _records(benv)[-1]["notes"])


def test_turn_process_refuses_legacy_facts_and_does_not_wipe_them(benv, monkeypatch):
    _submit_turn(benv, monkeypatch)
    c = benv.get_db()
    c.execute("INSERT INTO memory_facts (id, fact_text) VALUES ('old', 'user values legacy things')")
    c.commit()
    c.close()
    with pytest.raises(benv.ef.TurnContractViolation):
        benv.be.run_process()
    assert [f["id"] for f in _facts(benv)] == ["old"]   # refused BEFORE the reset branch


def test_turn_process_counts_unusable_responses(benv, monkeypatch):
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()
    benv.batches.results_for = lambda ids: [_result(i, [], stop="max_tokens") for i in ids]
    # A batch max_tokens stop is re-chunked synchronously (test_rechunk_on_max_tokens). The
    # synchronous part is faked to truncate too, so no real client is ever built here.
    trunc = types.SimpleNamespace(create=lambda **kw: _result("x", [], stop="max_tokens").result.message)
    monkeypatch.setattr(benv.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(benv.ef, "_get_anthropic_client", lambda: types.SimpleNamespace(messages=trunc))
    benv.be.run_process()
    rec = _records(benv)[-1]
    assert rec["response_failures"] == {"max_tokens": 1}
    assert rec["counts"]["chunks_failed"] == 1
    assert rec["counts"]["rechunked_on_max_tokens"] == 1


def test_download_retries_a_dropped_stream(benv, monkeypatch):
    _submit_turn(benv, monkeypatch)
    benv.batches.fail_downloads = 2
    monkeypatch.setattr(benv.be.time, "sleep", lambda s: None)
    benv.be.run_process()
    assert len(_facts(benv)) == 2


def test_legacy_batch_path_still_runs_ungated(benv):
    _seed(benv, with_turns=False)
    benv.be.run_submit()
    benv.batches.results_for = lambda ids: [_result(i, LEGACY_FACTS) for i in ids]
    benv.be.run_process()
    facts = _facts(benv)
    assert [f["object_text"] for f in facts] == ["speed over polish"]
    assert facts[0]["turn_contract_version"] is None and facts[0]["extraction_model"]


# ---------------------------------------------------------------------------
# turn-mode defaults on the batch path, with BASELAYER_TURN_CONTRACT UNSET
# ---------------------------------------------------------------------------

SHORT_TURNS = [(0, "subject", "own_typed", "user", "I review every invoice myself before paying it."),
               (1, "subject", "own_typed", "user", "And I never sign contracts on a Friday.")]


def test_batch_turn_mode_from_the_argument_applies_turn_defaults_and_resets(benv, monkeypatch):
    """A batch's mode can come from `run_submit(turn_contract=True)` or from its state
    file, with the env var unset. The turn-mode defaults must still apply (dynamic cap
    on; no minimum message count), and must NOT outlive the call: a later legacy run
    in the same process keeps the legacy default."""
    import math
    from baselayer.config import CHARS_PER_FACT, MIN_MESSAGES_FOR_EXTRACTION
    monkeypatch.delenv("BASELAYER_TURN_CONTRACT", raising=False)
    monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
    # the dynamic cap shows in the request only through the capped budget
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    assert len(SHORT_TURNS) < MIN_MESSAGES_FOR_EXTRACTION
    _seed(benv, turns=SHORT_TURNS)
    benv.be.run_submit(turn_contract=True)
    reqs = benv.batches.submitted
    assert reqs and reqs[0]["custom_id"] == CONV                 # short conversation kept
    chars = sum(len(t[4]) for t in SHORT_TURNS)
    assert reqs[0]["params"]["max_tokens"] == max(2000, math.ceil(chars / CHARS_PER_FACT) * 180 + 2000)
    assert _state(benv)["settings"]["dynamic_cap"] is True
    assert benv.ef._dynamic_cap_enabled() is False               # reset on return

    fact = {"subject": "user", "predicate": "practices", "object": "reviews invoices personally",
            "category": "habit", "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn": "S1", "span": "I review every invoice myself"}]}
    benv.batches.results_for = lambda ids: [_result(i, [fact]) for i in ids]
    benv.be.run_process()                                         # mode from the state file
    assert [f["object_text"] for f in _facts(benv)] == ["reviews invoices personally"]
    assert benv.ef._dynamic_cap_enabled() is False


# ---------------------------------------------------------------------------
# incremental batch: grown sessions come back, the rest do not, nothing is wiped
# ---------------------------------------------------------------------------

_NO_CITABLE = [(0, "subject", "harness_prompt", "user", "Run the nightly report job now please."),
               (1, "assistant", "assistant", "assistant", "Report job started.")]


def _seed_incremental(benv):
    """grown: extracted at t=100, re-imported by the importer at t=200 (it grew).
    done: extracted at t=100, imported at t=50, mark cleared. new: never extracted.
    harness: never extracted, nothing citable. Returns the ids."""
    ids = {"grown": "conv-grown", "done": "conv-done", "new": "conv-new",
           "harness": "conv-harness"}
    for k in ("grown", "done", "new"):
        _seed(benv, conv=ids[k])
    _seed(benv, conv=ids["harness"], turns=_NO_CITABLE)
    c = benv.get_db()
    for k, needs, imported in (("grown", 1, 200.0), ("done", 0, 50.0), ("new", 1, 50.0),
                               ("harness", 1, 50.0)):
        c.execute("INSERT INTO import_state (conversation_id, source, needs_extraction, "
                  "imported_at, status, turn_contract_version) VALUES (?,?,?,?,?,?)",
                  (ids[k], "chatgpt", needs, imported, "grown" if k == "grown" else "new", V))
    for k in ("grown", "done"):
        c.execute("INSERT INTO extraction_log (conversation_id, facts_extracted, processed_at) "
                  "VALUES (?, 1, 100.0)", (ids[k],))
    c.commit()
    c.close()
    return ids


def _parents(benv):
    return {m["parent_conv_id"] for m in _state(benv)["chunk_map"].values()}


def test_incremental_turn_submit_selects_grown_and_new_only(benv, monkeypatch):
    ids = _seed_incremental(benv)
    benv.be.run_submit(skip_extracted=True, turn_contract=True)
    assert _parents(benv) == {ids["grown"], ids["new"]}
    st = _state(benv)
    assert st["incremental"] is True
    assert st["grown_conversations"] == [ids["grown"]]


def test_full_turn_submit_is_not_incremental(benv, monkeypatch):
    _seed(benv)
    benv.be.run_submit(turn_contract=True)
    assert _state(benv)["incremental"] is False


def test_incremental_batch_refuses_the_resetting_process(benv, monkeypatch):
    """--process wipes every extracted fact and the whole extraction_log before storing.
    After an incremental submit that would destroy every conversation not in the batch."""
    ids = _seed_incremental(benv)
    benv.be.run_submit(skip_extracted=True, turn_contract=True)
    benv.batches.results_for = lambda cids: [_result(i, TURN_FACTS) for i in cids]
    with pytest.raises(SystemExit, match="--resume"):
        benv.be.run_process(resume=False)
    c = benv.get_db()
    logged = {r[0] for r in c.execute("SELECT conversation_id FROM extraction_log")}
    c.close()
    assert logged == {ids["grown"], ids["done"]}          # nothing was reset


def test_incremental_batch_processes_with_resume_and_clears_the_grown_mark(benv, monkeypatch):
    ids = _seed_incremental(benv)
    benv.be.run_submit(skip_extracted=True, turn_contract=True)
    benv.batches.results_for = lambda cids: [_result(i, TURN_FACTS) for i in cids]
    benv.be.run_process(resume=True)
    c = benv.get_db()
    needs = dict(c.execute("SELECT conversation_id, needs_extraction FROM import_state"))
    logged = dict(c.execute("SELECT conversation_id, processed_at FROM extraction_log"))
    c.close()
    assert needs[ids["grown"]] == 0 and needs[ids["new"]] == 0
    assert logged[ids["grown"]] > 100.0                   # re-extracted, not the old row
    assert logged[ids["done"]] == 100.0                   # untouched
    assert {f["source_conversation_id"] for f in _facts(benv)} >= {ids["grown"], ids["new"]}


def test_batch_cli_can_submit_incrementally_and_resume(benv, monkeypatch):
    """The module CLI had no way to ask for an incremental submit; --incremental is it."""
    ids = _seed_incremental(benv)
    monkeypatch.setattr(sys, "argv", ["batch_extract", "--submit", "--incremental",
                                      "--turn-contract"])
    benv.be.main()
    assert _state(benv)["incremental"] is True and _parents(benv) == {ids["grown"], ids["new"]}
    benv.batches.results_for = lambda cids: [_result(i, TURN_FACTS) for i in cids]
    monkeypatch.setattr(sys, "argv", ["batch_extract", "--process"])
    with pytest.raises(SystemExit, match="--resume"):
        benv.be.main()
    monkeypatch.setattr(sys, "argv", ["batch_extract", "--resume"])
    benv.be.main()
    assert _state(benv)["status"] == "completed"


def test_baselayer_batch_extract_incremental_flag_reaches_submit(benv, monkeypatch):
    import argparse
    import baselayer.cli as cli
    seen = {}
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr(benv.be, "run_submit", lambda **kw: seen.update(kw))
    cli.cmd_batch_extract(argparse.Namespace(submit=True, status=False, process=False,
                                             resume=False, incremental=True,
                                             turn_contract=True))
    assert seen == {"skip_extracted": True, "turn_contract": True}


def test_turn_process_refuses_an_unmapped_result_before_the_reset(benv, monkeypatch):
    """A result the chunk map cannot place is refused BEFORE the reset: the mode guards
    run before it so nothing is silently wiped, and this check needs only the results."""
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()
    _stamp_a_gated_fact(benv)                     # corpus from an earlier turn run
    p = benv.root / "data" / "database" / "batch_state.json"
    st = json.loads(p.read_text("utf-8"))
    st["chunk_map"] = {}                          # hand-edited or partly written state
    p.write_text(json.dumps(st), "utf-8")
    benv.batches.results_for = lambda ids: [_result(i, TURN_FACTS) for i in ids]
    with pytest.raises(benv.ef.TurnContractViolation, match="no chunk_map entry"):
        benv.be.run_process()
    assert [f["id"] for f in _facts(benv)] == ["gated"]   # nothing was reset
