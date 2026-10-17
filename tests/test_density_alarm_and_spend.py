"""
The turn path no longer halts or trims on a fact count. A dense conversation is REPORTED:
the run record's `density` block gives facts per 1K citable characters per conversation,
with the run's own p50/p90/p99/max and the ten densest conversations. Nothing is trimmed.

The runaway guard is spend: BASELAYER_SPEND_CEILING_USD refuses any call whose measured
spend so far plus that call's worst case (prompt at 3.5 chars per token, plus max_tokens)
would pass the ceiling. It stops the run (a SystemExit, which no per-conversation
handler catches) and the run record is still written.
"""

import json
import types

import pytest

from tests.test_api_usage_record import _usage
from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    _fact, _facts, _records, _seed, env)


def _conv_turn(text):
    return [(0, "subject", "own_typed", "user", text)]


NORMAL = "I plan the week on Sunday evening and keep it to three priorities."
RUNAWAY = "I paste my own notes back in. " * 4


def _llm(per_conv):
    """Returns n facts for a prompt, n chosen by which text the prompt carries."""
    def call(prompt, schema=None, retries=None, max_tokens=None):
        n, span = next((n, s) for key, (n, s) in per_conv.items() if key in prompt)
        return {"facts": [_fact(f"fact {i} {span[:10]}", [("S1", span)],
                                predicate="practices", category="habit") for i in range(n)]}
    return call


def test_a_runaway_conversation_is_reported_first_not_halted(env, monkeypatch):
    for i in range(3):
        _seed(env, conv=f"normal-{i}", turns=_conv_turn(NORMAL + f" Week {i}."))
    _seed(env, conv="runaway", turns=_conv_turn(RUNAWAY))
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "none")
    monkeypatch.setattr(env.ef, "call_llm", _llm({
        "Week": (2, "I plan the week on Sunday evening"),
        "paste my own": (60, "I paste my own notes back in."),
    }))
    env.ef.run_extraction()                     # no SystemExit
    rec = _records(env)[-1]
    d = rec["density"]
    assert d["conversations"] == 4
    assert d["top10"][0]["conversation_id"] == "runaway"
    assert d["top10"][0]["facts"] == 60
    assert d["max"] == d["top10"][0]["facts_per_1k_citable"]
    assert d["p50"] <= d["p90"] <= d["p99"] <= d["max"]
    assert "over_conversation_cap" not in rec["post_gate_drops"]
    assert not any("coverage gate halted" in n for n in rec["notes"])
    assert rec["counts"]["facts_after_validation"] == 6 + 60      # nothing trimmed


def test_capped_mode_no_longer_halts_or_trims_a_conversation(env, monkeypatch):
    """Capped mode keeps its per-chunk truncation (what its prompt promised) and loses the
    conversation-level halt and confidence-sort trim, like `none`."""
    _seed(env, conv="c", turns=[(i, "subject", "own_typed", "user", f"{NORMAL} Week {i}.")
                                for i in range(6)])
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "0")
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 2, "input_char_budget": 250})
    monkeypatch.setattr(env.ef, "call_llm", _llm({"Week": (2, "I plan the week on Sunday evening")}))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["chunks_called"] >= 3
    assert rec["counts"]["facts_after_validation"] == 2 * rec["counts"]["chunks_called"]
    assert "over_conversation_cap" not in rec["post_gate_drops"]
    assert rec["density"]["top10"][0]["conversation_id"] == "c"


class _Msgs:
    def __init__(self):
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        blk = types.SimpleNamespace(type="text", text=json.dumps({"facts": []}))
        return types.SimpleNamespace(content=[blk], stop_reason="end_turn",
                                     usage=_usage(i=1000, o=200, cr=0, cw=0))


def test_the_spend_ceiling_stops_the_run_before_the_call_that_would_pass_it(env, monkeypatch):
    for i in range(6):
        _seed(env, conv=f"c-{i}", turns=_conv_turn(NORMAL + f" Week {i}."))
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    msgs = _Msgs()
    monkeypatch.setattr(env.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(env.ef, "_get_anthropic_client", lambda: types.SimpleNamespace(messages=msgs))
    # each call costs $0.002 measured; worst case per call is about $0.011 (2,000 max_tokens)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "0.02")
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    rec = _records(env)[-1]                   # still written
    spent = rec["api_usage"]["totals"]["input_tokens"] / 1e6 + \
        rec["api_usage"]["totals"]["output_tokens"] * 5 / 1e6
    assert 1 <= msgs.calls < 6
    assert spent <= 0.02
    assert any("spend ceiling" in n for n in rec["notes"])
    assert rec["settings"]["spend_ceiling_usd"] == 0.02


def test_no_ceiling_set_means_no_refusal(env, monkeypatch):
    for i in range(3):
        _seed(env, conv=f"c-{i}", turns=_conv_turn(NORMAL + f" Week {i}."))
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    msgs = _Msgs()
    monkeypatch.setattr(env.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(env.ef, "_get_anthropic_client", lambda: types.SimpleNamespace(messages=msgs))
    env.ef.run_extraction()
    assert msgs.calls == 3
