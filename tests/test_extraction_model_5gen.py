"""Extraction on a 5-generation model (Haiku 5.5 test, 2026-10-19).

Measured live before this fix (one unbilled call, respec-run 10af499): a sequential extraction
call on claude-haiku-5-5 returns 400 "`temperature` is deprecated for this model", and
call_anthropic swallows it into None with no usage entry and no counted failure. Four defects:

1. BASELAYER_LLM_EXTRACTION, the documented per-role override, never reached extraction:
   config.EXTRACTION_API_MODEL was a hard-coded literal.
2. The sequential call sends temperature=0.1 and the batch request carries BATCH_TEMPERATURE;
   Haiku 5.5 (and every model that removed sampling parameters) rejects both with a 400.
3. The run record stamped the CONFIGURED model on every usage entry, never the reply's
   `model`, so "the record says Haiku 5.5" only echoed the setting.
4. Effort could not be set explicitly (Haiku 5.5 defaults to medium).

Fake clients only; no API calls.
"""
import importlib
import json
from types import SimpleNamespace

import pytest

FACTS = {"facts": []}


class _FakeMessages:
    def __init__(self, model_reply="claude-haiku-5-5"):
        self.kwargs = []
        self.model_reply = model_reply

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        return SimpleNamespace(
            model=self.model_reply, stop_reason="end_turn",
            content=[SimpleNamespace(type="thinking", thinking="", signature="s"),
                     SimpleNamespace(type="text", text=json.dumps(FACTS))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def _install(monkeypatch, model, reply_model=None):
    import baselayer.extract_facts as ef
    msgs = _FakeMessages(reply_model or model)
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", model)
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: SimpleNamespace(messages=msgs))
    return ef, msgs


def test_extraction_model_honours_the_role_override(monkeypatch):
    import baselayer.config as config
    monkeypatch.setenv("BASELAYER_LLM_EXTRACTION", "claude-haiku-5-5")
    try:
        importlib.reload(config)
        assert config.EXTRACTION_API_MODEL == "claude-haiku-5-5"
    finally:
        monkeypatch.delenv("BASELAYER_LLM_EXTRACTION")
        importlib.reload(config)
    assert config.EXTRACTION_API_MODEL == "claude-haiku-5-5"   # the default (2026-10-19)


def test_the_default_extraction_model_is_haiku_55_in_every_reader(monkeypatch):
    """Aarik 2026-10-19: extraction moves to claude-haiku-5-5 at effort medium. The role table
    (llm_provider, freshness check) and the extraction constant name the same model."""
    import baselayer.config as config
    monkeypatch.delenv("BASELAYER_LLM_EXTRACTION", raising=False)
    importlib.reload(config)
    assert config.EXTRACTION_API_MODEL == "claude-haiku-5-5"
    assert config.LLM_PROVIDER_CONFIG["extraction"] == config.EXTRACTION_API_MODEL
    assert config._LATEST_MODELS["haiku"] == "claude-haiku-5-5"
    assert config.DEFAULT_EXTRACTION_EFFORT == "medium"


def test_effort_medium_is_sent_by_default_and_can_be_turned_off(monkeypatch):
    monkeypatch.delenv("BASELAYER_EXTRACTION_EFFORT", raising=False)
    ef, msgs = _install(monkeypatch, "claude-haiku-5-5")
    ef.call_anthropic("p", retries=0)
    assert msgs.kwargs[0]["output_config"] == {"effort": "medium"}
    monkeypatch.setenv("BASELAYER_EXTRACTION_EFFORT", "")       # empty: the model's own default
    ef, msgs = _install(monkeypatch, "claude-haiku-5-5")
    ef.call_anthropic("p", retries=0)
    assert "output_config" not in msgs.kwargs[0]


def test_a_batch_request_on_the_default_model_carries_effort_and_no_temperature(monkeypatch):
    from baselayer import batch_extract as be
    monkeypatch.delenv("BASELAYER_EXTRACTION_EFFORT", raising=False)
    r = be._build_request_for_conv("c1", "p", "claude-haiku-5-5", 100, be.BATCH_TEMPERATURE, "J\n")
    assert "temperature" not in r["params"]
    assert r["params"]["output_config"] == {"effort": "medium"}


def test_the_run_settings_record_model_and_effort(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.delenv("BASELAYER_EXTRACTION_EFFORT", raising=False)
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    s = ef.turn_run_settings()
    assert s["extraction_effort"] == "medium"
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-4-5-20251001")
    assert ef.turn_run_settings()["extraction_effort"] is None    # Haiku 4.5 takes no effort


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-sonnet-5",
                                   "claude-opus-5-5", "claude-opus-4-8", "claude-fable-5-1"])
def test_sequential_call_sends_no_sampling_params_where_the_model_rejects_them(monkeypatch, model):
    ef, msgs = _install(monkeypatch, model)
    assert ef.call_anthropic("p", retries=0) == FACTS
    sent = msgs.kwargs[0]
    assert not {"temperature", "top_p", "top_k"} & set(sent), sent.keys()


def test_haiku_45_keeps_its_production_temperature(monkeypatch):
    monkeypatch.delenv("BASELAYER_EXTRACTION_EFFORT", raising=False)
    ef, msgs = _install(monkeypatch, "claude-haiku-4-5-20251001")
    ef.call_anthropic("p", retries=0)
    assert msgs.kwargs[0]["temperature"] == 0.1
    assert "output_config" not in msgs.kwargs[0]


def test_batch_request_sends_no_temperature_on_a_5_generation_model():
    from baselayer import batch_extract as be
    r = be._build_request_for_conv("c1", "p", "claude-haiku-5-5", 100, be.BATCH_TEMPERATURE, "J\n")
    assert "temperature" not in r["params"]
    r45 = be._build_request_for_conv("c1", "p", "claude-haiku-4-5-20251001", 100,
                                     be.BATCH_TEMPERATURE, "J\n")
    assert r45["params"]["temperature"] == 0.1


def test_usage_entry_records_the_model_that_answered(monkeypatch):
    ef, _ = _install(monkeypatch, "claude-haiku-5-5", reply_model="claude-haiku-5-5")
    before = len(ef.usage_calls())
    ef.call_anthropic("p", retries=0)
    entry = ef.usage_calls()[before]
    assert entry["model"] == "claude-haiku-5-5"
    assert entry["stop_reason"] == "end_turn"
    assert entry["thinking_blocks"] == 1
    # a reply from a different model than configured is visible, not overwritten
    ef, _ = _install(monkeypatch, "claude-haiku-5-5", reply_model="claude-other")
    ef.call_anthropic("p", retries=0)
    assert ef.usage_calls()[-1]["model"] == "claude-other"
    assert ef.usage_calls()[-1]["requested_model"] == "claude-haiku-5-5"


def test_a_refusal_is_recorded_with_its_category(monkeypatch):
    import baselayer.extract_facts as ef

    class Refusing:
        def create(self, **kw):
            return SimpleNamespace(model="claude-haiku-5-5", stop_reason="refusal", content=[],
                                   stop_details=SimpleNamespace(category="cyber"),
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=0))
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: SimpleNamespace(messages=Refusing()))
    assert ef.call_anthropic("p", retries=0) is None
    e = ef.usage_calls()[-1]
    assert (e["stop_reason"], e["refusal_category"]) == ("refusal", "cyber")


def test_effort_is_sent_explicitly_when_set_on_a_5_generation_model(monkeypatch):
    monkeypatch.setenv("BASELAYER_EXTRACTION_EFFORT", "medium")
    ef, msgs = _install(monkeypatch, "claude-haiku-5-5")
    ef.call_anthropic("p", retries=0)
    assert msgs.kwargs[0]["output_config"] == {"effort": "medium"}
    ef, msgs = _install(monkeypatch, "claude-haiku-4-5-20251001")   # effort 400s on Haiku 4.5
    ef.call_anthropic("p", retries=0)
    assert "output_config" not in msgs.kwargs[0]


def test_estimate_prices_the_default_model_at_the_spend_table_rates():
    """`baselayer estimate` prices the configured model; before, its table had no Haiku 5.5
    row, so the default would have printed no cost."""
    from baselayer import cli, config
    for model in (config.DEFAULT_EXTRACTION_MODEL, "claude-haiku-4-5-20251001"):
        rates = config.spend_rates_for(model)
        assert cli._estimate_rate(model) == (rates["input"], rates["output"])
    assert cli._estimate_rate_source("claude-haiku-5-5")[2] == config.SPEND_RATES_AS_OF
