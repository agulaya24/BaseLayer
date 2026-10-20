"""Model ids, rate tables and sampling parameters must not go stale silently.

Findings from the 2026-10-20 model watch, each pinned here:

1. Four live calls (author_layers x2, agent_pipeline x2) passed `temperature=` straight to
   `messages.create`, bypassing the filter `api_client.call_api` applies. Every 5-generation
   model (and Opus 4.7 / 4.8) returns a 400 on any temperature, so setting
   BASELAYER_LLM_AUTHORING or BASELAYER_LLM_REVIEW to one broke authoring and compose.
2. `config._LATEST_MODELS` named Sonnet 4.6 and Opus 4.6 as the newest, so
   `check_model_freshness()` could never flag the 4.6 defaults.
3. The distillation table (`spend.py`) and the verify-spec table (`verification/pricing.py`)
   were dated 2026-06-24 and had no Sonnet 5.5 row; the verify-spec CLI aliases priced
   older models; `llm_provider` carried a third, undated table (removed in d222d9c).
4. `RECLASSIFY_MODEL` named a retired model and nothing read it.

Rates below are the Claude API pricing page as captured on 2026-10-20 (USD per million
tokens, base input / output). When the page changes, update spend.py and this capture
together.
"""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "baselayer"

PAGE_2026_10_20 = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
HAIKU_5_5 = {"short": (0.10, 0.50), "long": (0.50, 2.50), "threshold": 100_000}
RETIRED = ("claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-opus-4-1",
           "claude-3-")


# ---------------------------------------------------------------------------------- 1
def _live_sources():
    skip = {"experiments", "archive"}
    return [p for p in SRC.rglob("*.py") if not (skip & set(p.relative_to(SRC).parts))]


def test_no_live_messages_call_sends_a_literal_temperature():
    """Call-site check: a create/stream call must take temperature through the per-model
    filter (`**extraction_sampling_kwargs(model, t)` or `api_client.call_api`), never as a
    keyword, because the filter is what keeps a 5-generation model from returning a 400."""
    offenders = []
    for p in _live_sources():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("create", "stream")
                    and any(k.arg in ("temperature", "top_p", "top_k") for k in node.keywords)):
                offenders.append("%s:%d" % (p.relative_to(SRC), node.lineno))
    assert offenders == []


def test_sampling_filter_drops_temperature_for_5_generation_models():
    from baselayer.config import extraction_sampling_kwargs
    assert extraction_sampling_kwargs("claude-sonnet-5", 0) == {}
    assert extraction_sampling_kwargs("claude-opus-5-5", 0.1) == {}
    assert extraction_sampling_kwargs("claude-sonnet-4-6", 0) == {"temperature": 0}


# ---------------------------------------------------------------------------------- 2
def test_latest_models_follow_the_rate_tables():
    from baselayer import config
    assert config._LATEST_MODELS["opus"] == "claude-opus-5-5"
    assert config._LATEST_MODELS["sonnet"] == "claude-sonnet-5-5"
    assert config._LATEST_MODELS["haiku"] == "claude-haiku-5-5"


def test_freshness_check_flags_a_4_6_default(monkeypatch, capsys):
    from baselayer import config
    monkeypatch.setitem(config.LLM_PROVIDER_CONFIG, "authoring", "claude-sonnet-4-6")
    assert config.check_model_freshness() is False
    assert "claude-sonnet-4-6" in capsys.readouterr().out


def test_freshness_check_passes_when_every_role_is_newest(monkeypatch):
    from baselayer import config
    for role in list(config.LLM_PROVIDER_CONFIG):
        fam = next((f for f in config._LATEST_MODELS
                    if f in config.LLM_PROVIDER_CONFIG[role].lower()), None)
        if fam:
            monkeypatch.setitem(config.LLM_PROVIDER_CONFIG, role, config._LATEST_MODELS[fam])
    assert config.check_model_freshness() is True


def test_a_dated_snapshot_id_is_not_flagged_against_its_own_alias(monkeypatch):
    from baselayer import config
    for role in list(config.LLM_PROVIDER_CONFIG):
        monkeypatch.setitem(config.LLM_PROVIDER_CONFIG, role, "ollama:qwen2.5")
    monkeypatch.setitem(config.LLM_PROVIDER_CONFIG, "extraction", "claude-haiku-5-5-20261001")
    assert config.check_model_freshness() is True


# ---------------------------------------------------------------------------------- 3
def test_distillation_rates_match_the_page_capture():
    from baselayer.distillation import spend
    assert spend.RATES_AS_OF == "2026-10-20"
    for model, rate in PAGE_2026_10_20.items():
        assert spend.RATES_PER_MTOK[model] == rate, model
    # Haiku 5.5 is priced by prompt length; a flat table holds its upper (long-prompt) card,
    # so an estimate or ceiling can over-count it and never under-count it.
    assert spend.RATES_PER_MTOK["claude-haiku-5-5"] == HAIKU_5_5["long"]


def test_extraction_rates_match_the_page_capture():
    from baselayer.config import spend_rates_for, spend_rates_tier
    h4 = spend_rates_for("claude-haiku-4-5-20251001")
    assert (h4["input"], h4["output"]) == PAGE_2026_10_20["claude-haiku-4-5"]
    h5 = spend_rates_for("claude-haiku-5-5")
    assert (h5["input"], h5["output"]) == HAIKU_5_5["short"]
    lng = spend_rates_tier(h5, HAIKU_5_5["threshold"] + 1)
    assert (lng["input"], lng["output"]) == HAIKU_5_5["long"]


def test_verify_spec_prices_from_the_one_distillation_table():
    from baselayer.distillation import spend
    from baselayer.verification import pricing
    assert pricing.PRICES == spend.RATES_PER_MTOK
    assert pricing.PRICES_AS_OF == spend.RATES_AS_OF
    from baselayer import config
    # A CLI alias is priced as the newest model of its family, the conservative reading of
    # an alias whose target the CLI chooses.
    for alias in ("opus", "sonnet", "haiku"):
        assert pricing.resolve(alias) == config._LATEST_MODELS[alias]


# ---------------------------------------------------------------------------------- 4
def test_no_config_setting_names_a_retired_model():
    from baselayer import config
    bad = {k: v for k, v in vars(config).items()
           if k.isupper() and isinstance(v, str) and v.startswith(RETIRED)}
    assert bad == {}
