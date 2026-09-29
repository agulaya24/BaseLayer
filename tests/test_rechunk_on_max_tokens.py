"""
A chunk whose response stops on max_tokens is re-chunked at half the input budget and each
part retried once, on the sequential and the batch path. Counted as
`rechunked_on_max_tokens`, listed per chunk in the run record's `rechunked`; a part that
truncates again is counted as a failed chunk and listed, never dropped silently.
"""

import json
import re
import types

from tests.test_api_usage_record import _usage
from tests.test_turn_batch_extract import _result, benv  # noqa: F401
from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    _fact, _facts, _records, _seed, env)

SENT = "I keep a written log of every decision I make at work and read it back on Fridays"
TURNS = []
for i in range(4):
    TURNS.append((2 * i, "subject", "own_typed", "user", f"Entry {i}. " + (SENT + ". ") * 3))
    TURNS.append((2 * i + 1, "assistant", "assistant", "assistant", "Understood."))


def _caps(*a, **k):
    return {"max_facts": 40, "input_char_budget": 1600}


class Scripted:
    """Anthropic messages fake: the first call (the whole chunk) stops on max_tokens;
    later calls return one fact grounded in each subject turn shown, unless
    `truncate_again` says the part should truncate too."""

    def __init__(self, truncate_again=False):
        self.calls = []
        self.truncate_again = truncate_again

    def create(self, **kw):
        prompt = kw["messages"][0]["content"]
        self.calls.append(kw)
        aliases = re.findall(r"\[(S\d+) \| SUBJECT, typed\]\n(Entry \d)", prompt)
        stop = "end_turn"
        if len(self.calls) == 1 or (self.truncate_again and len(self.calls) == 2):
            stop = "max_tokens"
        facts = [_fact(f"logs decisions {e}", [(a, e + ". " + SENT[:30])],
                       predicate="practices", category="habit") for a, e in aliases]
        blk = types.SimpleNamespace(type="text", text=json.dumps({"facts": facts}))
        return types.SimpleNamespace(content=[blk], stop_reason=stop, usage=_usage())


def _client(monkeypatch, ef, msgs):
    monkeypatch.setattr(ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: types.SimpleNamespace(messages=msgs))


def test_sequential_truncation_is_rechunked_not_lost(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "_get_extraction_caps", _caps)
    msgs = Scripted()
    _client(monkeypatch, env.ef, msgs)
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["rechunked_on_max_tokens"] == 1
    assert rec["counts"].get("chunks_failed", 0) == 0
    assert "max_tokens" not in rec["response_failures"]
    assert len(rec["rechunked"]) == 1 and rec["rechunked"][0]["parts"] >= 2
    assert rec["rechunked"][0]["still_truncated"] == 0
    # every subject turn is covered by some part, so all four facts arrive
    assert sorted(f["object_text"] for f in _facts(env)) == [f"logs decisions Entry {i}"
                                                             for i in range(4)]
    ext = [c for c in rec["api_usage"]["calls"] if c["purpose"] == "extract"]
    assert len(ext) == len(msgs.calls) == 1 + rec["rechunked"][0]["parts"]


def test_a_part_that_truncates_again_is_counted_and_listed(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "_get_extraction_caps", _caps)
    _client(monkeypatch, env.ef, Scripted(truncate_again=True))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["rechunked_on_max_tokens"] == 1
    assert rec["rechunked"][0]["still_truncated"] == 1
    assert rec["counts"]["chunks_failed"] == 1
    assert rec["response_failures"]["max_tokens"] == 1
    assert "max_tokens_after_rechunk" in rec["suspect"]
    assert len(_facts(env)) >= 1          # the other part still stored its facts


def test_batch_truncation_is_rechunked_synchronously(benv, monkeypatch):
    _seed(benv, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(benv.ef, "_get_extraction_caps", _caps)
    benv.be.run_submit()
    assert len(benv.batches.submitted) == 1

    def results(ids):
        out = []
        for i in ids:
            r = _result(i, [], stop="max_tokens")
            r.result.message.usage = _usage()
            out.append(r)
        return out
    benv.batches.results_for = results
    msgs = Scripted()
    msgs.calls.append("the batch call")      # so the synchronous parts are not truncated
    _client(monkeypatch, benv.ef, msgs)
    benv.be.run_process()
    rec = _records(benv)[-1]
    assert rec["counts"]["rechunked_on_max_tokens"] == 1
    assert rec["rechunked"][0]["path"] == "batch"
    assert sorted(f["object_text"] for f in _facts(benv)) == [f"logs decisions Entry {i}"
                                                              for i in range(4)]
