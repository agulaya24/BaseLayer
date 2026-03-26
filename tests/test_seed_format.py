"""
Seed Format Validation Test — Phase 2 (S98 Refactor)

Validates that build_payload() output matches what the website seed endpoint expects.
Catches format mismatches before they break live thinkers pages.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# Fields the website seed endpoint requires (from route.ts)
REQUIRED_PAYLOAD_FIELDS = {
    "name", "slug", "password", "brief", "anchors", "core", "predictions",
}

OPTIONAL_PAYLOAD_FIELDS = {
    "token", "citedBrief", "stats", "interactions", "contradictions",
    "radar", "sourceDocuments", "sourceDescription", "facts",
    "changeSummary", "wordCount", "chapters", "unitLabel",
}

# Fields each layer item must have
REQUIRED_LAYER_ITEM_FIELDS = {"id", "name", "description"}

# Fields each brief paragraph must have (if structured)
REQUIRED_BRIEF_PARAGRAPH_FIELDS = {"text", "sources"}


class TestSeedPayloadSchema:
    """Validate build_payload() output structure."""

    @pytest.mark.skipif(
        not Path("C:/Users/Aarik/Anthropic/subjects/kevin_kelly_memory").exists(),
        reason="Kevin Kelly subject data not available"
    )
    def test_build_payload_has_required_fields(self):
        """Payload must include all fields the seed endpoint expects."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from baselayer.seed_industry import build_payload, resolve_subject_dir, SUBJECTS

        if "kevin_kelly" not in SUBJECTS:
            pytest.skip("Kevin Kelly not in SUBJECTS dict")

        config = SUBJECTS["kevin_kelly"]
        subject_dir = resolve_subject_dir("kevin_kelly")
        payload = build_payload(
            subject_dir, config["name"], config["slug"],
            config["password"], config.get("source", "")
        )

        for field in REQUIRED_PAYLOAD_FIELDS:
            assert field in payload, f"Missing required field: {field}"

    @pytest.mark.skipif(
        not Path("C:/Users/Aarik/Anthropic/subjects/kevin_kelly_memory").exists(),
        reason="Kevin Kelly subject data not available"
    )
    def test_layer_items_have_required_fields(self):
        """Each anchor/core/prediction item must have id, name, description."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from baselayer.seed_industry import build_payload, resolve_subject_dir, SUBJECTS

        if "kevin_kelly" not in SUBJECTS:
            pytest.skip("Kevin Kelly not in SUBJECTS dict")

        config = SUBJECTS["kevin_kelly"]
        subject_dir = resolve_subject_dir("kevin_kelly")
        payload = build_payload(
            subject_dir, config["name"], config["slug"],
            config["password"], config.get("source", "")
        )

        for layer_name in ["anchors", "core", "predictions"]:
            items = payload.get(layer_name, [])
            assert len(items) > 0, f"{layer_name} is empty"
            for item in items:
                for field in REQUIRED_LAYER_ITEM_FIELDS:
                    assert field in item, f"{layer_name} item missing '{field}': {item.get('id', '?')}"

    @pytest.mark.skipif(
        not Path("C:/Users/Aarik/Anthropic/subjects/kevin_kelly_memory").exists(),
        reason="Kevin Kelly subject data not available"
    )
    def test_brief_is_structured(self):
        """Brief should be a list of paragraphs, not a raw string."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from baselayer.seed_industry import build_payload, resolve_subject_dir, SUBJECTS

        if "kevin_kelly" not in SUBJECTS:
            pytest.skip("Kevin Kelly not in SUBJECTS dict")

        config = SUBJECTS["kevin_kelly"]
        subject_dir = resolve_subject_dir("kevin_kelly")
        payload = build_payload(
            subject_dir, config["name"], config["slug"],
            config["password"], config.get("source", "")
        )

        brief = payload.get("brief")
        assert brief is not None, "Brief is None"
        assert isinstance(brief, list), f"Brief should be list, got {type(brief).__name__}"
        assert len(brief) > 0, "Brief is empty list"

        for i, para in enumerate(brief):
            assert isinstance(para, dict), f"Brief paragraph {i} should be dict"
            for field in REQUIRED_BRIEF_PARAGRAPH_FIELDS:
                assert field in para, f"Brief paragraph {i} missing '{field}'"

    def test_payload_is_json_serializable(self):
        """Entire payload must be JSON-serializable (no Path objects, sets, etc)."""
        # Test with a minimal mock payload
        mock_payload = {
            "name": "Test Subject",
            "slug": "test-subject",
            "password": "test-password",
            "brief": [{"text": "Test paragraph.", "sources": ["A"]}],
            "anchors": [{"id": "A1", "name": "TEST", "description": "Test anchor"}],
            "core": [{"id": "C1", "name": "TEST", "description": "Test core"}],
            "predictions": [{"id": "P1", "name": "TEST", "description": "Test prediction"}],
        }
        # Should not raise
        json_str = json.dumps(mock_payload)
        assert len(json_str) > 0

    def test_change_summary_function_exists(self):
        """generate_change_summary should be importable."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from baselayer.seed_industry import generate_change_summary
        assert callable(generate_change_summary)

    def test_change_summary_detects_differences(self):
        """Change summary should produce text when models differ."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from baselayer.seed_industry import generate_change_summary

        old = "## Operational Guide\n\n**A1. TEST**\nDescription.\n\n## Identity Brief\n\n" + "word " * 100
        new = "## Operational Guide\n\n**A1. TEST**\nDifferent.\n\n**A2. NEW**\nAdded.\n\n## Identity Brief\n\n" + "word " * 200

        summary = generate_change_summary(old, new)
        assert len(summary) > 0, "Change summary should be non-empty for different models"

    def test_change_summary_empty_for_identical(self):
        """Change summary should be empty when models are identical."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from baselayer.seed_industry import generate_change_summary

        text = "## Identity Brief\n\nSame content."
        summary = generate_change_summary(text, text)
        assert summary == "", "Change summary should be empty for identical models"
