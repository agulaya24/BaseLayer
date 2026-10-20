"""The extraction model follows the path (decision of 2026-10-19).

Turn-contract extraction, sequential and batch, defaults to claude-haiku-5-5 at effort medium:
that is where the same-sample comparisons were run. The legacy path (`baselayer extract`
without --turn-contract, and so `baselayer run`) stays on claude-haiku-4-5 until a legacy
comparison is done: on its first live test, given a published autobiography as a text file,
Haiku 5.5 would not credit the writing to the person (3 facts against Haiku 4.5's 24), while on
unrecognisable first-person prose the two matched. BASELAYER_LLM_EXTRACTION, when set, is the
model on BOTH paths.

Fake clients only; no API calls.
"""
import importlib
import json
import types

import pytest

from tests.test_turn_batch_extract import _result, benv  # noqa: F401
from tests.test_turn_extraction import TURN_FACTS, _seed, env  # noqa: F401

H45, H55 = "claude-haiku-4-5-20251001", "claude-haiku-5-5"


def test_config_defaults_per_path_and_the_override_reaches_both(monkeypatch):
    import baselayer.config as config
    monkeypatch.delenv("BASELAYER_LLM_EXTRACTION", raising=False)
    importlib.reload(config)
    try:
        assert config.EXTRACTION_API_MODEL == H55                 # turn path
        assert config.LEGACY_EXTRACTION_API_MODEL == H45          # legacy path
        monkeypatch.setenv("BASELAYER_LLM_EXTRACTION", "claude-sonnet-5-5")
        importlib.reload(config)
        assert config.EXTRACTION_API_MODEL == config.LEGACY_EXTRACTION_API_MODEL == "claude-sonnet-5-5"
    finally:
        monkeypatch.delenv("BASELAYER_LLM_EXTRACTION", raising=False)
        importlib.reload(config)


class _Msgs:
    def __init__(self, payload):
        self.calls, self.payload = [], payload

    def create(self, **kw):
        self.calls.append(kw)
        blk = types.SimpleNamespace(type="text", text=json.dumps(self.payload))
        return types.SimpleNamespace(model=kw["model"], content=[blk], stop_reason="end_turn",
                                     usage=types.SimpleNamespace(input_tokens=10, output_tokens=5))


def _client(monkeypatch, ef, msgs):
    monkeypatch.setattr(ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: types.SimpleNamespace(messages=msgs))


def _pin_defaults(monkeypatch, ef):
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", H55)
    monkeypatch.setattr(ef, "LEGACY_EXTRACTION_API_MODEL", H45, raising=False)


def test_a_legacy_sequential_run_calls_haiku_45(env, monkeypatch):
    _seed(env)
    _pin_defaults(monkeypatch, env.ef)
    msgs = _Msgs({"facts": []})
    _client(monkeypatch, env.ef, msgs)
    env.ef.run_extraction()
    assert msgs.calls and {c["model"] for c in msgs.calls} == {H45}
    assert all(c["temperature"] == 0.1 and "output_config" not in c for c in msgs.calls)
    assert env.ef.active_extraction_model() == H55          # reset after the run


def test_a_turn_sequential_run_calls_haiku_55(env, monkeypatch):
    _seed(env)
    _pin_defaults(monkeypatch, env.ef)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    msgs = _Msgs({"facts": []})
    _client(monkeypatch, env.ef, msgs)
    env.ef.run_extraction()
    assert msgs.calls and {c["model"] for c in msgs.calls} == {H55}
    assert all("temperature" not in c for c in msgs.calls)


def test_a_legacy_batch_requests_haiku_45_and_a_turn_batch_haiku_55(benv, monkeypatch):
    _seed(benv, with_turns=False)
    _pin_defaults(monkeypatch, benv.ef)
    import baselayer.batch_extract as be
    benv.be.run_submit()
    legacy = benv.batches.submitted[-1]["params"]
    assert legacy["model"] == H45 and legacy["temperature"] == 0.1
    assert json.loads((benv.root / "data" / "database" / "batch_state.json")
                      .read_text("utf-8"))["model"] == H45
    assert benv.ef.active_extraction_model() == H55          # reset after submit
    assert be is benv.be


def test_a_turn_batch_requests_haiku_55(benv, monkeypatch):
    _seed(benv)
    _pin_defaults(monkeypatch, benv.ef)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()
    p = benv.batches.submitted[-1]["params"]
    assert p["model"] == H55 and "temperature" not in p
    assert p["output_config"] == {"effort": "medium"}
