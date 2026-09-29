"""
Output budget in fact_count_mode `none`: sized from the chunk's citable characters, not
from a fact count. max_tokens = clamp(TURN_OUTPUT_TOKENS_FLOOR,
ceil(TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR x citable chars), EXTRACTION_MAX_OUTPUT_TOKENS).
Every extraction call's usage entry carries its chunk's citable characters, so the
per-char constant can be re-derived from each run's own record.
"""

import math

import pytest

from tests.test_api_usage_record import _fake_client, _usage  # noqa: F401
from tests.test_fact_count_mode import LONG
from tests.test_turn_batch_extract import _result, _state, benv  # noqa: F401
from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    CONV, TURN_FACTS, TURNS as BASE_TURNS, _records, _seed, env)

LONG_TURNS = [(0, "subject", "own_typed", "user", LONG),
              (1, "assistant", "assistant", "assistant", "Noted.")]


def _expected(citable):
    from baselayer.config import (EXTRACTION_MAX_OUTPUT_TOKENS, TURN_OUTPUT_TOKENS_FLOOR,
                                  TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR)
    return min(EXTRACTION_MAX_OUTPUT_TOKENS,
               max(TURN_OUTPUT_TOKENS_FLOOR,
                   math.ceil(TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR * citable)))


def test_budget_function_clamps():
    import baselayer.extract_facts as ef
    from baselayer.config import EXTRACTION_MAX_OUTPUT_TOKENS, TURN_OUTPUT_TOKENS_FLOOR
    assert ef.turn_output_budget(0) == TURN_OUTPUT_TOKENS_FLOOR
    assert ef.turn_output_budget(10 ** 7) == EXTRACTION_MAX_OUTPUT_TOKENS
    assert ef.turn_output_budget(1260) == _expected(1260) > TURN_OUTPUT_TOKENS_FLOOR


def test_none_mode_sizes_max_tokens_from_citable_chars(env, monkeypatch):
    _seed(env, turns=LONG_TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "none")
    seen = []

    def call(prompt, schema=None, retries=None, max_tokens=None):
        seen.append(max_tokens)
        return {"facts": []}
    monkeypatch.setattr(env.ef, "call_llm", call)
    env.ef.run_extraction()
    assert seen == [_expected(len(LONG))]
    s = _records(env)[-1]["settings"]
    assert s["output_tokens_per_citable_char"] and s["output_tokens_floor"] == 2000


def test_usage_entries_carry_citable_chars(env, monkeypatch):
    _seed(env, turns=LONG_TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    _fake_client(monkeypatch, env.ef, [])
    env.ef.run_extraction()
    calls = _records(env)[-1]["api_usage"]["calls"]
    ext = [c for c in calls if c["purpose"] == "extract"]
    assert ext and ext[0]["citable_chars"] == len(LONG) and ext[0]["chunk"] == 1


def test_batch_none_mode_budget_and_usage_carry_citable_chars(benv, monkeypatch):
    _seed(benv, turns=LONG_TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "none")
    benv.be.run_submit()
    req = benv.batches.submitted[0]
    assert req["params"]["max_tokens"] == _expected(len(LONG))
    assert "up to" not in req["params"]["messages"][0]["content"]

    def results(ids):
        out = []
        for i in ids:
            r = _result(i, [])
            r.result.message.usage = _usage()
            out.append(r)
        return out
    benv.batches.results_for = results
    benv.be.run_process()
    batch_calls = [c for c in _records(benv)[-1]["api_usage"]["calls"] if c["batch"]]
    assert batch_calls[0]["citable_chars"] == len(LONG)
