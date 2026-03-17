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
    """Test cost estimation from model and token counts."""

    def test_known_model_haiku(self):
        from baselayer.llm_provider import estimate_cost
        # Haiku: $0.80/MTok input, $4.00/MTok output
        cost = estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        assert abs(cost - 4.80) < 0.01

    def test_known_model_sonnet(self):
        from baselayer.llm_provider import estimate_cost
        # Sonnet: $3.00/MTok input, $15.00/MTok output
        cost = estimate_cost("claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        assert abs(cost - 18.00) < 0.01

    def test_known_model_opus(self):
        from baselayer.llm_provider import estimate_cost
        # Opus: $15.00/MTok input, $75.00/MTok output
        cost = estimate_cost("claude-opus-4-20250514", 1_000_000, 1_000_000)
        assert abs(cost - 90.00) < 0.01

    def test_unknown_model_returns_zero(self):
        from baselayer.llm_provider import estimate_cost
        cost = estimate_cost("ollama:qwen2.5", 10000, 5000)
        assert cost == 0.0

    def test_zero_tokens(self):
        from baselayer.llm_provider import estimate_cost
        cost = estimate_cost("claude-haiku-4-5-20251001", 0, 0)
        assert cost == 0.0

    def test_small_token_count(self):
        from baselayer.llm_provider import estimate_cost
        # 100 input tokens, 50 output tokens at Haiku rates
        cost = estimate_cost("claude-haiku-4-5-20251001", 100, 50)
        expected = (100 / 1e6) * 0.80 + (50 / 1e6) * 4.00
        assert abs(cost - expected) < 0.0001

    def test_openai_model(self):
        from baselayer.llm_provider import estimate_cost
        cost = estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost > 0

    def test_gemini_model(self):
        from baselayer.llm_provider import estimate_cost
        cost = estimate_cost("gemini-2.0-flash", 1_000_000, 1_000_000)
        assert cost > 0


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
    """Test the PRICING reference table structure."""

    def test_all_entries_have_input_and_output(self):
        from baselayer.llm_provider import PRICING
        for model, rates in PRICING.items():
            assert "input" in rates, f"Missing input rate for {model}"
            assert "output" in rates, f"Missing output rate for {model}"
            assert rates["input"] > 0, f"Zero input rate for {model}"
            assert rates["output"] > 0, f"Zero output rate for {model}"

    def test_haiku_is_cheapest_anthropic(self):
        from baselayer.llm_provider import PRICING
        haiku = PRICING["claude-haiku-4-5-20251001"]
        sonnet = PRICING["claude-sonnet-4-20250514"]
        assert haiku["input"] < sonnet["input"]
        assert haiku["output"] < sonnet["output"]
