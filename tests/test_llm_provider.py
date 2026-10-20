"""
Tests for llm_provider.py — provider detection, model resolution,
cost estimation, and provider info.

All tests run without API keys or external services.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock



# ============================================================
# DETECT_PROVIDER
# ============================================================

class TestDetectProvider:
    """Test auto-detection of API provider from model name."""

    def test_claude_models(self):
        from baselayer.llm_provider import detect_provider
        assert detect_provider("claude-haiku-4-5-20251001") == "anthropic"
        assert detect_provider("claude-sonnet-4-20250514") == "anthropic"
        assert detect_provider("claude-opus-4-20250514") == "anthropic"
        assert detect_provider("claude-opus-4-6") == "anthropic"

    def test_gpt_models(self):
        from baselayer.llm_provider import detect_provider
        assert detect_provider("gpt-4o") == "openai"
        assert detect_provider("gpt-4o-mini") == "openai"
        assert detect_provider("gpt-4.1") == "openai"
        assert detect_provider("gpt-4.1-mini") == "openai"

    def test_o1_o3_models(self):
        from baselayer.llm_provider import detect_provider
        assert detect_provider("o1-preview") == "openai"
        assert detect_provider("o3-mini") == "openai"

    def test_gemini_models(self):
        from baselayer.llm_provider import detect_provider
        assert detect_provider("gemini-2.0-flash") == "google"
        assert detect_provider("gemini-2.0-pro") == "google"
        assert detect_provider("gemini-2.5-pro-preview-05-06") == "google"

    def test_ollama_models(self):
        from baselayer.llm_provider import detect_provider
        assert detect_provider("ollama:qwen2.5:14b") == "ollama"
        assert detect_provider("ollama:llama3") == "ollama"

    def test_unknown_model_raises(self):
        from baselayer.llm_provider import detect_provider
        with pytest.raises(ValueError, match="Cannot detect provider"):
            detect_provider("unknown-model-v1")

    def test_empty_string_raises(self):
        from baselayer.llm_provider import detect_provider
        with pytest.raises(ValueError):
            detect_provider("")

    def test_partial_prefix_no_match(self):
        from baselayer.llm_provider import detect_provider
        with pytest.raises(ValueError):
            detect_provider("claud-3")  # missing 'e'


# ============================================================
# _RESOLVE_MODEL
# ============================================================

class TestResolveModel:
    """Test model resolution from explicit model or role."""

    def test_explicit_model_takes_priority(self):
        from baselayer.llm_provider import _resolve_model
        result = _resolve_model(model="gpt-4o", role="extraction")
        assert result == "gpt-4o"

    def test_role_lookup(self):
        from baselayer.llm_provider import _resolve_model
        result = _resolve_model(role="extraction")
        assert result.startswith("claude-")

    def test_unknown_role_raises(self):
        from baselayer.llm_provider import _resolve_model
        with pytest.raises(ValueError, match="Unknown pipeline role"):
            _resolve_model(role="nonexistent_role")

    def test_neither_model_nor_role_raises(self):
        from baselayer.llm_provider import _resolve_model
        with pytest.raises(ValueError, match="Must specify either"):
            _resolve_model()

    def test_all_valid_roles(self):
        from baselayer.llm_provider import _resolve_model
        from baselayer.config import LLM_PROVIDER_CONFIG
        for role in LLM_PROVIDER_CONFIG:
            result = _resolve_model(role=role)
            assert isinstance(result, str) and len(result) > 0


# ============================================================
# ESTIMATE_COST
# ============================================================

class TestEstimateCost:
    """estimate_cost prices from config.SPEND_RATES_BY_MODEL, the one dated rate table the spend
    ceiling uses. It used to read its own undated 2025-05 table (Haiku 4.5 at $0.80/$4.00
    against config's $1/$5) and returned $0.00 for any model missing from it, including the
    current default extraction model. A silent $0 is the defect; an unpriced model is None."""

    def test_matches_the_dated_spend_table(self):
        from baselayer.config import spend_rates_for
        from baselayer.llm_provider import estimate_cost
        for model in ("claude-haiku-4-5-20251001", "claude-haiku-4-5", "claude-haiku-5-5"):
            r = spend_rates_for(model)       # 50K input: under Haiku 5.5's long-prompt tier
            assert estimate_cost(model, 50_000, 1_000_000) == pytest.approx(
                0.05 * r["input"] + r["output"]), model

    def test_long_prompt_tier_applies(self):
        from baselayer.config import spend_rates_for
        from baselayer.llm_provider import estimate_cost
        long = spend_rates_for("claude-haiku-5-5")["long"]
        assert estimate_cost("claude-haiku-5-5", 200_000, 0) == pytest.approx(
            0.2 * long["input"])

    def test_current_default_extraction_model_is_priced(self):
        from baselayer.config import EXTRACTION_API_MODEL
        from baselayer.llm_provider import estimate_cost
        cost = estimate_cost(EXTRACTION_API_MODEL, 1_000_000, 1_000_000)
        assert cost is not None and cost > 0

    def test_a_model_with_no_dated_rate_is_none_not_zero(self):
        from baselayer.llm_provider import estimate_cost
        for model in ("claude-sonnet-4-20250514", "gpt-4o", "gemini-2.0-flash"):
            assert estimate_cost(model, 1_000_000, 1_000_000) is None, model

    def test_local_ollama_model_costs_nothing(self):
        from baselayer.llm_provider import estimate_cost
        assert estimate_cost("ollama:qwen2.5", 10000, 5000) == 0.0

    def test_zero_tokens(self):
        from baselayer.llm_provider import estimate_cost
        assert estimate_cost("claude-haiku-4-5-20251001", 0, 0) == 0.0

    def test_small_token_count(self):
        from baselayer.config import spend_rates_for
        from baselayer.llm_provider import estimate_cost
        r = spend_rates_for("claude-haiku-4-5")
        expected = (100 / 1e6) * r["input"] + (50 / 1e6) * r["output"]
        assert estimate_cost("claude-haiku-4-5-20251001", 100, 50) == pytest.approx(expected)


# ============================================================
# GET_PROVIDER_INFO
# ============================================================

class TestGetProviderInfo:
    """Test provider metadata retrieval."""

    def test_anthropic_provider_info(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(model="claude-haiku-4-5-20251001")
        assert info["provider"] == "anthropic"
        assert info["model"] == "claude-haiku-4-5-20251001"
        assert info["requires_api_key"] is True
        assert "ANTHROPIC_API_KEY" in info["api_key_env_vars"]

    def test_openai_provider_info(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(model="gpt-4o")
        assert info["provider"] == "openai"
        assert info["requires_api_key"] is True
        assert "OPENAI_API_KEY" in info["api_key_env_vars"]

    def test_google_provider_info(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(model="gemini-2.0-flash")
        assert info["provider"] == "google"
        assert info["requires_api_key"] is True
        assert "GOOGLE_API_KEY" in info["api_key_env_vars"] or \
               "GEMINI_API_KEY" in info["api_key_env_vars"]

    def test_ollama_provider_info(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(model="ollama:qwen2.5")
        assert info["provider"] == "ollama"
        assert info["requires_api_key"] is False
        assert info["api_key_env_vars"] == []

    def test_role_based_lookup(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(role="extraction")
        assert info["provider"] == "anthropic"
        assert "model" in info

    def test_package_installed_flag(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(model="claude-haiku-4-5-20251001")
        assert isinstance(info["package_installed"], bool)

    def test_api_key_set_flag(self):
        from baselayer.llm_provider import get_provider_info
        info = get_provider_info(model="claude-haiku-4-5-20251001")
        assert isinstance(info["api_key_set"], bool)


# ============================================================
# PRICING TABLE
# ============================================================

class TestPricing:
    """The undated PRICING table is gone; there is one rate table (config.SPEND_RATES_BY_MODEL)."""

    def test_no_second_rate_table(self):
        import baselayer.llm_provider as lp
        assert not hasattr(lp, "PRICING")

