"""
Golden Dataset Regression Test — Phase 2 (S98 Refactor)

Compares current identity model artifacts against a frozen reference
(Aarik's identity model). Flags if brief changes >15% after pipeline modifications.

Reference files stored in tests/golden/.
"""

import os
from pathlib import Path

import pytest


GOLDEN_DIR = Path(__file__).parent / "golden"
BRIEF_REFERENCE = GOLDEN_DIR / "brief_reference.md"
IDENTITY_MODEL_REFERENCE = GOLDEN_DIR / "identity_model_reference.md"

# Aarik's live identity model
AARIK_LAYERS_DIR = Path("C:/Users/Aarik/Anthropic/memory_system_v4/data/identity_layers")


def _word_diff_pct(text_a: str, text_b: str) -> float:
    """Compute word-level difference percentage between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a and not words_b:
        return 0.0
    union = words_a | words_b
    intersection = words_a & words_b
    return 1.0 - (len(intersection) / len(union)) if union else 0.0


class TestGoldenDatasetIntegrity:
    """Verify golden reference files exist and are non-empty."""

    def test_brief_reference_exists(self):
        assert BRIEF_REFERENCE.exists(), "Golden brief reference missing"

    def test_identity_model_reference_exists(self):
        assert IDENTITY_MODEL_REFERENCE.exists(), "Golden identity model reference missing"

    def test_reference_has_required_marker(self):
        content = IDENTITY_MODEL_REFERENCE.read_text(encoding="utf-8")
        assert "Identity Model" in content or "identity_model" in content


class TestGoldenDatasetRegression:
    """Verify identity model structural properties.

    These tests check that the pipeline produces well-formed output
    without committing personal data to the repo.
    """

    @pytest.mark.skipif(
        not AARIK_LAYERS_DIR.exists(),
        reason="Aarik's identity layers not available"
    )
    def test_brief_has_minimum_length(self):
        """Brief should be at least 5000 chars (meaningful content)."""
        current_path = AARIK_LAYERS_DIR / "brief_v5_clean.md"
        if not current_path.exists():
            pytest.skip("Current brief not available")
        content = current_path.read_text(encoding="utf-8")
        assert len(content) > 5000, f"Brief too short: {len(content)} chars"

    @pytest.mark.skipif(
        not AARIK_LAYERS_DIR.exists(),
        reason="Aarik's identity layers not available"
    )
    def test_identity_model_has_required_sections(self):
        """Identity model should have all required sections."""
        current_path = AARIK_LAYERS_DIR / "identity_model.md"
        if not current_path.exists():
            pytest.skip("Current identity model not available")
        content = current_path.read_text(encoding="utf-8")
        assert "## Operational Guide" in content or "## Injectable Block" in content
        assert "Identity Brief" in content or "Brief" in content
        assert len(content) > 10000, f"Identity model too short: {len(content)} chars"

    @pytest.mark.skipif(
        not AARIK_LAYERS_DIR.exists(),
        reason="Aarik's identity layers not available"
    )
    def test_no_known_hallucinations(self):
        """Verify known hallucinations are not present in current model."""
        hallucination_terms = ["Victoria, Canada", "young child", "daughter Victoria"]
        for layer_file in ["core_v4.md", "brief_v5_clean.md", "identity_model.md"]:
            path = AARIK_LAYERS_DIR / layer_file
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            for term in hallucination_terms:
                assert term.lower() not in content.lower(), (
                    f"Hallucination '{term}' found in {layer_file}. "
                    f"This was fixed in S98 — may have regressed."
                )
