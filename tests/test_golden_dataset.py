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
        content = BRIEF_REFERENCE.read_text(encoding="utf-8")
        assert len(content) > 500, f"Brief reference too short: {len(content)} chars"

    def test_identity_model_reference_exists(self):
        assert IDENTITY_MODEL_REFERENCE.exists(), "Golden identity model reference missing"
        content = IDENTITY_MODEL_REFERENCE.read_text(encoding="utf-8")
        assert len(content) > 2000, f"Identity model reference too short: {len(content)} chars"

    def test_reference_has_required_sections(self):
        content = IDENTITY_MODEL_REFERENCE.read_text(encoding="utf-8")
        assert "## Injectable Block" in content or "## Operational Guide" in content, \
            "Identity model missing required section headers"


class TestGoldenDatasetRegression:
    """Compare current identity model against frozen reference.

    These tests catch unintended changes from pipeline modifications.
    If a test fails, it means the pipeline produced significantly different output —
    investigate whether the change is intentional before updating the reference.
    """

    @pytest.mark.skipif(
        not AARIK_LAYERS_DIR.exists(),
        reason="Aarik's identity layers not available"
    )
    def test_brief_stability(self):
        """Brief should not change >15% from reference without intentional cause."""
        reference = BRIEF_REFERENCE.read_text(encoding="utf-8")
        current_path = AARIK_LAYERS_DIR / "brief_v5_clean.md"
        if not current_path.exists():
            pytest.skip("Current brief not available")

        current = current_path.read_text(encoding="utf-8")
        diff_pct = _word_diff_pct(reference, current)
        assert diff_pct < 0.15, (
            f"Brief changed {diff_pct:.1%} from reference (threshold: 15%). "
            f"If intentional, update tests/golden/brief_reference.md"
        )

    @pytest.mark.skipif(
        not AARIK_LAYERS_DIR.exists(),
        reason="Aarik's identity layers not available"
    )
    def test_identity_model_stability(self):
        """Identity model should not change >15% from reference without intentional cause."""
        reference = IDENTITY_MODEL_REFERENCE.read_text(encoding="utf-8")
        current_path = AARIK_LAYERS_DIR / "identity_model.md"
        if not current_path.exists():
            pytest.skip("Current identity model not available")

        current = current_path.read_text(encoding="utf-8")
        diff_pct = _word_diff_pct(reference, current)
        assert diff_pct < 0.15, (
            f"Identity model changed {diff_pct:.1%} from reference (threshold: 15%). "
            f"If intentional, update tests/golden/identity_model_reference.md"
        )

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
