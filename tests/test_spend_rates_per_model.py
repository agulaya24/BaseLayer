"""The extraction spend ceiling prices each call at its own model's published rates.

Before this, config.SPEND_RATES_PER_MTOK was one Haiku 4.5 table ($1 / $5 per MTok), so a
Haiku 5.5 run ($0.10 / $0.50 for prompts up to 100K tokens) was over-counted about 10x: safe,
but it would stop a large run early. A model with no rate in the table is refused when a
ceiling is set, rather than priced at another model's rates.

Fake usage entries only; no API calls.
"""
import pytest


def _entry(model=None, i=0, o=0, cr=0, cw=0, batch=False, requested=None):
    return {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
            "cache_creation_input_tokens": cw, "model": model, "requested_model": requested,
            "batch": batch, "purpose": "extract"}


def test_a_haiku_55_call_is_priced_at_haiku_55_rates():
    import baselayer.extract_facts as ef
    usd = ef.measured_spend_usd([_entry("claude-haiku-5-5", i=1_000_000 // 20, o=1_000_000 // 20)])
    # 50K in at $0.10 + 50K out at $0.50 per MTok
    assert usd == pytest.approx(0.005 + 0.025)


def test_a_dated_id_and_its_alias_share_one_row():
    import baselayer.extract_facts as ef
    a = ef.measured_spend_usd([_entry("claude-haiku-4-5-20251001", i=10_000, o=10_000)])
    b = ef.measured_spend_usd([_entry("claude-haiku-4-5", i=10_000, o=10_000)])
    assert a == b == pytest.approx(0.01 + 0.05)


def test_haiku_55_over_100k_prompt_tokens_pays_the_long_prompt_rate_on_the_whole_call():
    import baselayer.extract_facts as ef
    # 90K input + 20K cache read = 110K prompt tokens: over the threshold
    usd = ef.measured_spend_usd([_entry("claude-haiku-5-5", i=90_000, cr=20_000, o=10_000)])
    assert usd == pytest.approx((90_000 * 0.50 + 20_000 * 0.05 + 10_000 * 2.50) / 1e6)
    under = ef.measured_spend_usd([_entry("claude-haiku-5-5", i=90_000, o=10_000)])
    assert under == pytest.approx((90_000 * 0.10 + 10_000 * 0.50) / 1e6)


def test_a_batch_entry_is_priced_at_half():
    import baselayer.extract_facts as ef
    seq = ef.measured_spend_usd([_entry("claude-haiku-5-5", i=40_000, o=40_000)])
    bat = ef.measured_spend_usd([_entry("claude-haiku-5-5", i=40_000, o=40_000, batch=True)])
    assert bat == pytest.approx(seq / 2)


def test_an_entry_without_a_reply_model_is_priced_at_the_requested_model():
    import baselayer.extract_facts as ef
    usd = ef.measured_spend_usd([_entry(None, i=10_000, o=10_000, requested="claude-haiku-5-5")])
    assert usd == pytest.approx((10_000 * 0.10 + 10_000 * 0.50) / 1e6)


def test_the_worst_case_check_uses_the_configured_models_rates(monkeypatch):
    import baselayer.extract_facts as ef
    ef.reset_usage()
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "0.002")
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    # 2,000 max_tokens at $0.50 per MTok is $0.001: under the ceiling on Haiku 5.5
    ef.check_spend_ceiling(prompt_chars=1000, max_tokens=2000)
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-4-5-20251001")
    with pytest.raises(ef.SpendCeilingExceeded):        # $0.01 on Haiku 4.5
        ef.check_spend_ceiling(prompt_chars=1000, max_tokens=2000)


def test_a_model_with_no_rate_is_refused_when_a_ceiling_is_set(monkeypatch):
    import baselayer.extract_facts as ef
    ef.reset_usage()
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "100")
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-unpriced-9")
    with pytest.raises(ef.SpendCeilingExceeded, match="no published rate"):
        ef.check_spend_ceiling(prompt_chars=10, max_tokens=10)
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD")
    ef.check_spend_ceiling(prompt_chars=10, max_tokens=10)   # no ceiling: nothing to price


def test_the_rate_table_carries_its_source_and_date():
    from baselayer import config
    assert config.SPEND_RATES_AS_OF == "2026-10-19"
    assert "platform.claude.com" in config.SPEND_RATES_SOURCE
    assert config.spend_rates_for("claude-haiku-5-5")["input"] == 0.10
    assert config.spend_rates_for("claude-haiku-4-5-20251001")["output"] == 5.0
    assert config.spend_rates_for("claude-unpriced-9") is None
