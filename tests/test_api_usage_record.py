"""API token usage is MEASURED and recorded, so a full run can be priced from a pilot.

Every extraction call's usage (input, output, cache read, cache write) lands in the per-run
record, per call and as totals, on the sequential path (through call_anthropic, extraction
and AUDN calls alike) and on the batch path (from each result's message). No API calls: the
client is a fake that returns scripted usage.
"""
import json
import types

import pytest

from baselayer import turn_contract as tc
from tests.test_turn_batch_extract import FakeBatches, _result, _state  # noqa: F401
from tests.test_turn_batch_extract import benv  # noqa: F401  (fixture)
from tests.test_turn_extraction import (  # noqa: F401
    CONV, LEGACY_FACTS, TURN_FACTS, _records, _seed, env)


def _usage(i=1000, o=200, cr=50, cw=10):
    return types.SimpleNamespace(input_tokens=i, output_tokens=o, cache_read_input_tokens=cr,
                                 cache_creation_input_tokens=cw)


class FakeMessages:
    def __init__(self, facts):
        self.facts = facts
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        blk = types.SimpleNamespace(type="text", text=json.dumps({"facts": self.facts}))
        return types.SimpleNamespace(content=[blk], stop_reason="end_turn", usage=_usage())


def _fake_client(monkeypatch, ef, facts):
    msgs = FakeMessages(facts)
    monkeypatch.setattr(ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(ef, "_get_anthropic_client",
                        lambda: types.SimpleNamespace(messages=msgs))
    return msgs


def test_usage_entry_reads_every_field_and_tolerates_missing_ones():
    e = tc.usage_entry(_usage(), purpose="extract")
    assert e == {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 50,
                 "cache_creation_input_tokens": 10, "purpose": "extract"}
    thin = tc.usage_entry(types.SimpleNamespace(input_tokens=5, output_tokens=None))
    assert thin["output_tokens"] == 0 and thin["cache_read_input_tokens"] == 0
    assert tc.usage_totals([e, thin])["input_tokens"] == 1005
    assert tc.usage_totals([e, thin])["calls"] == 2


def test_sequential_turn_run_records_measured_usage_per_call_and_total(env, monkeypatch, capsys):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    msgs = _fake_client(monkeypatch, env.ef, TURN_FACTS)
    env.ef.run_extraction()
    rec = _records(env)[-1]
    u = rec["api_usage"]
    assert msgs.calls >= 1
    assert u["totals"]["calls"] == msgs.calls == len(u["calls"])
    assert u["totals"]["input_tokens"] == 1000 * msgs.calls
    assert u["totals"]["output_tokens"] == 200 * msgs.calls
    assert u["totals"]["cache_read_input_tokens"] == 50 * msgs.calls
    assert u["totals"]["cache_creation_input_tokens"] == 10 * msgs.calls
    first = u["calls"][0]
    assert first["conversation_id"] == CONV and first["purpose"] == "extract"
    assert first["model"] and first["batch"] is False
    out = capsys.readouterr().out
    assert "API usage" in out and "%d input" % (1000 * msgs.calls) in out.replace(",", "")


def test_legacy_sequential_run_prints_measured_usage(env, monkeypatch, capsys):
    _seed(env, with_turns=False)
    msgs = _fake_client(monkeypatch, env.ef, LEGACY_FACTS)
    env.ef.run_extraction()
    out = capsys.readouterr().out.replace(",", "")
    assert msgs.calls >= 1 and "API usage" in out
    assert "%d input" % (1000 * msgs.calls) in out


def test_a_billed_but_unusable_response_is_still_counted(env, monkeypatch):
    """A truncated response is billed. It must be in the totals even though it is discarded."""
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    msgs = _fake_client(monkeypatch, env.ef, TURN_FACTS)
    orig = msgs.create

    def truncated(**kw):
        r = orig(**kw)
        r.stop_reason = "max_tokens"
        return r
    msgs.create = truncated
    with pytest.raises(SystemExit):      # every part truncates: a failed chunk fails the run
        env.ef.run_extraction()
    u = _records(env)[-1]["api_usage"]
    assert u["totals"]["calls"] == msgs.calls >= 1


def test_batch_run_records_usage_from_each_result(benv, monkeypatch):
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()

    def results(ids):
        out = []
        for i in ids:
            r = _result(i, TURN_FACTS)
            r.result.message.usage = _usage(i=3000, o=400, cr=0, cw=0)
            out.append(r)
        return out
    benv.batches.results_for = results
    benv.be.run_process()
    rec = _records(benv)[-1]
    u = rec["api_usage"]
    batch_calls = [c for c in u["calls"] if c["batch"]]
    assert len(batch_calls) == 1
    assert batch_calls[0]["input_tokens"] == 3000 and batch_calls[0]["output_tokens"] == 400
    assert batch_calls[0]["conversation_id"] == CONV and batch_calls[0]["custom_id"] == CONV
    assert u["totals"]["batch"]["input_tokens"] == 3000
    assert _state(benv)["api_usage_totals"]["input_tokens"] >= 3000


def test_a_response_without_usage_is_counted_and_marked_not_dropped():
    e = tc.usage_entry(None, purpose="extract")
    t = tc.usage_totals([e, tc.usage_entry(_usage())])
    assert t["calls"] == 2 and t["calls_without_usage"] == 1 and t["input_tokens"] == 1000
    assert "reported NO usage" in tc.usage_line(t)
