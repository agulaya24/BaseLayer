"""
Tests for unified brief composition, storage, MCP preference, and fallback.
Also tests eval upgrades: C2-AP ablation, CM condition, judge panel consensus.

All tests run without API keys or external services.
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ============================================================
# UNIFIED BRIEF — COMPOSITION PROMPT
# ============================================================

class TestCompositionPrompt:
    """Verify the composition prompt encodes the 3 eval-derived properties."""

    def test_prompt_has_concrete_mechanisms(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "CONCRETE AUTOBIOGRAPHICAL MECHANISMS" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_has_inner_tensions(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "CHARACTERISTIC INNER TENSIONS" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_has_pragmatic_framing(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "PRAGMATIC FRAMING" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_has_anti_anachronism(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "ANTI-ANACHRONISM" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_has_placeholders(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "{anchors}" in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "{core}" in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "{predictions}" in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "{facts}" in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "{fact_count}" in UNIFIED_BRIEF_COMPOSITION_PROMPT


# ============================================================
# UNIFIED BRIEF — STORE FORMAT
# ============================================================

class TestStoreUnifiedBrief:
    """Verify store_unified_brief writes correct format."""

    def test_writes_yaml_header(self, tmp_path):
        from scripts.agent_pipeline import store_unified_brief, UNIFIED_BRIEF_FILE

        with patch("scripts.agent_pipeline.UNIFIED_BRIEF_FILE", tmp_path / "brief_v4.md"), \
             patch("scripts.agent_pipeline.IDENTITY_LAYERS_DIR", tmp_path):
            store_unified_brief(None, "Test brief content here.")
            content = (tmp_path / "brief_v4.md").read_text(encoding="utf-8")

        assert "---" in content
        assert "layer: unified_brief" in content
        assert "## Injectable Block" in content
        assert "Test brief content here." in content

    def test_writes_with_run_dir(self, tmp_path):
        from scripts.agent_pipeline import store_unified_brief

        run_dir = tmp_path / "runs" / "cycle_001"
        run_dir.mkdir(parents=True)

        with patch("scripts.agent_pipeline.UNIFIED_BRIEF_FILE", tmp_path / "brief_v4.md"), \
             patch("scripts.agent_pipeline.IDENTITY_LAYERS_DIR", tmp_path):
            store_unified_brief(run_dir, "Brief with run info.")
            content = (tmp_path / "brief_v4.md").read_text(encoding="utf-8")

        assert "run: cycle_001" in content


# ============================================================
# MCP — UNIFIED BRIEF PREFERENCE
# ============================================================

class TestMCPUnifiedBriefPreference:
    """Verify MCP serves unified brief when available, falls back to layers."""

    def test_prefers_unified_brief(self, tmp_path):
        import mcp_server

        # Create unified brief
        brief_file = tmp_path / "brief_v4.md"
        brief_file.write_text(
            "---\nlayer: unified_brief\n---\n\n## Injectable Block\n\nUnified narrative here.",
            encoding="utf-8",
        )
        # Create layer files too
        anchors = tmp_path / "anchors_v4.md"
        anchors.write_text("---\n---\n\n## Injectable Block\n\nAnchors layer.", encoding="utf-8")

        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", brief_file), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", anchors), \
             patch.object(mcp_server, "CORE_LAYER_FILE", tmp_path / "core_v4.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", tmp_path / "predictions_v4.md"):
            result = mcp_server.get_identity_brief()

        assert "Unified narrative here." in result
        assert "NEVER" in result and "quote, reference, or name them" in result  # Usage preamble included

    def test_falls_back_to_layers(self, tmp_path, mock_identity_layers):
        import mcp_server

        # No unified brief file
        no_brief = tmp_path / "nonexistent_brief.md"

        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", no_brief), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            result = mcp_server.get_identity_brief()

        assert "Quality matters more than speed" in result

    def test_falls_back_when_brief_empty(self, tmp_path, mock_identity_layers):
        import mcp_server

        # Create brief with empty injectable block
        brief_file = tmp_path / "brief_v4.md"
        brief_file.write_text("---\nlayer: unified_brief\n---\n\n## Injectable Block\n\n", encoding="utf-8")

        with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", brief_file), \
             patch.object(mcp_server, "ANCHORS_LAYER_FILE", mock_identity_layers / "anchors_v3.md"), \
             patch.object(mcp_server, "CORE_LAYER_FILE", mock_identity_layers / "core_v3.md"), \
             patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", mock_identity_layers / "predictions_v3.md"):
            result = mcp_server.get_identity_brief()

        # Should fall back to layers since brief is empty
        assert "Quality matters more than speed" in result


# ============================================================
# MANIFEST — STEP 7
# ============================================================

class TestManifestIncludesStep7:
    """Verify create_run_dir manifest includes Step 7."""

    def test_manifest_has_unified_brief_step(self, tmp_path):
        from scripts.agent_pipeline import create_run_dir
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", tmp_path / "runs"):
            run_dir = create_run_dir()

        manifest = (run_dir / "00_manifest.md").read_text(encoding="utf-8")
        assert "07_unified_brief.md" in manifest
        assert "Unified Brief" in manifest


# ============================================================
# CONFIG — UNIFIED_BRIEF_FILE
# ============================================================

class TestConfigUnifiedBrief:
    """Verify UNIFIED_BRIEF_FILE is defined in config."""

    def test_constant_exists(self):
        from scripts.config import UNIFIED_BRIEF_FILE
        assert "brief_v4.md" in str(UNIFIED_BRIEF_FILE)

    def test_constant_in_identity_layers_dir(self):
        from scripts.config import UNIFIED_BRIEF_FILE, IDENTITY_LAYERS_DIR
        assert UNIFIED_BRIEF_FILE.parent == IDENTITY_LAYERS_DIR


# ============================================================
# EVAL — C2-AP ABLATION
# ============================================================

class TestAblationC2AP:
    """Verify C2-AP (anchors + predictions) ablation is wired in."""

    def test_ablation_layers_has_c2ap(self):
        from scripts.run_validation_study import ABLATION_LAYERS
        assert "C2-AP" in ABLATION_LAYERS
        assert ABLATION_LAYERS["C2-AP"] == ["anchors", "predictions"]

    def test_condition_prompts_has_c2ap(self):
        from scripts.run_validation_study import CONDITION_PROMPTS
        assert "C2-AP" in CONDITION_PROMPTS

    def test_public_figure_conditions_has_c2ap(self):
        from scripts.run_validation_study import PUBLIC_FIGURE_CONDITIONS
        assert "C2-AP" in PUBLIC_FIGURE_CONDITIONS


# ============================================================
# EVAL — CM CONDITION
# ============================================================

class TestCMCondition:
    """Verify Claude Memory condition is wired in."""

    def test_condition_prompts_has_cm(self):
        from scripts.run_validation_study import CONDITION_PROMPTS
        assert "CM" in CONDITION_PROMPTS

    def test_cm_system_prompt_requires_file(self, tmp_path):
        from scripts.run_validation_study import get_system_prompt, EVAL_DIR

        with patch("scripts.run_validation_study.EVAL_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="claude_memories.txt"):
                get_system_prompt("CM", {"fact_categories": []})

    def test_cm_system_prompt_loads_file(self, tmp_path):
        from scripts.run_validation_study import get_system_prompt

        cm_file = tmp_path / "claude_memories.txt"
        cm_file.write_text("Likes coffee\nWorks in AI\nValues honesty", encoding="utf-8")

        with patch("scripts.run_validation_study.EVAL_DIR", tmp_path):
            result = get_system_prompt("CM", {"fact_categories": []})

        assert "<userMemories>" in result
        assert "Likes coffee" in result
        assert "</userMemories>" in result


# ============================================================
# EVAL — JUDGE PANEL CONSENSUS
# ============================================================

class TestJudgePanelConsensus:
    """Verify multi-judge loading and consensus math."""

    def test_load_single_model(self, tmp_path):
        from scripts.run_validation_study import _load_all_judge_results

        judge_dir = tmp_path / "judge"
        judge_dir.mkdir()

        data = {
            "C1_P1": {
                "prompt_id": "P1",
                "scores": {"recognition": {"score": 3, "justification": "ok"}},
                "judge_model": "claude-opus-4-20250514",
            }
        }
        (judge_dir / "judge_ratings_opus.json").write_text(
            json.dumps(data), encoding="utf-8")

        with patch("scripts.run_validation_study.JUDGE_DIR", judge_dir):
            consensus, per_model = _load_all_judge_results()

        assert "opus" in per_model
        assert "C1_P1" in consensus
        assert consensus["C1_P1"]["scores"]["recognition"]["score"] == 3

    def test_consensus_averages_scores(self, tmp_path):
        from scripts.run_validation_study import _load_all_judge_results

        judge_dir = tmp_path / "judge"
        judge_dir.mkdir()

        opus_data = {
            "C1_P1": {
                "prompt_id": "P1",
                "scores": {"recognition": {"score": 4, "justification": "good"}},
                "judge_model": "opus",
            }
        }
        sonnet_data = {
            "C1_P1": {
                "prompt_id": "P1",
                "scores": {"recognition": {"score": 2, "justification": "ok"}},
                "judge_model": "sonnet",
            }
        }
        (judge_dir / "judge_ratings_opus.json").write_text(
            json.dumps(opus_data), encoding="utf-8")
        (judge_dir / "judge_ratings_sonnet.json").write_text(
            json.dumps(sonnet_data), encoding="utf-8")

        with patch("scripts.run_validation_study.JUDGE_DIR", judge_dir):
            consensus, per_model = _load_all_judge_results()

        assert len(per_model) == 2
        # Average of 4 and 2 = 3.0
        assert consensus["C1_P1"]["scores"]["recognition"]["score"] == 3.0

    def test_flags_disagreements(self, tmp_path):
        from scripts.run_validation_study import _load_all_judge_results

        judge_dir = tmp_path / "judge"
        judge_dir.mkdir()

        opus_data = {
            "C1_P1": {
                "prompt_id": "P1",
                "scores": {"recognition": {"score": 5, "justification": "great"}},
                "judge_model": "opus",
            }
        }
        sonnet_data = {
            "C1_P1": {
                "prompt_id": "P1",
                "scores": {"recognition": {"score": 2, "justification": "bad"}},
                "judge_model": "sonnet",
            }
        }
        (judge_dir / "judge_ratings_opus.json").write_text(
            json.dumps(opus_data), encoding="utf-8")
        (judge_dir / "judge_ratings_sonnet.json").write_text(
            json.dumps(sonnet_data), encoding="utf-8")

        with patch("scripts.run_validation_study.JUDGE_DIR", judge_dir):
            consensus, _ = _load_all_judge_results()

        # 5 - 2 = 3 spread > 1 point threshold
        assert len(consensus["C1_P1"]["disagreements"]) == 1
        assert consensus["C1_P1"]["disagreements"][0]["spread"] == 3

    def test_legacy_fallback(self, tmp_path):
        from scripts.run_validation_study import _load_all_judge_results

        judge_dir = tmp_path / "judge"
        judge_dir.mkdir()

        legacy_data = {
            "C1_P1": {
                "prompt_id": "P1",
                "scores": {"recognition": {"score": 3, "justification": "ok"}},
            }
        }
        (judge_dir / "judge_ratings.json").write_text(
            json.dumps(legacy_data), encoding="utf-8")

        with patch("scripts.run_validation_study.JUDGE_DIR", judge_dir):
            consensus, per_model = _load_all_judge_results()

        assert "legacy" in per_model
        assert "C1_P1" in consensus


# ============================================================
# EVAL — ANACHRONISM CHECK IN JUDGE PROMPT
# ============================================================

class TestAnachronismCheck:
    """Verify anachronism check is in the public figure judge prompt."""

    def test_public_figure_prompt_has_anachronism_check(self):
        from scripts.run_validation_study import JUDGE_PUBLIC_FIGURE_PROMPT
        assert "ANACHRONISM CHECK" in JUDGE_PUBLIC_FIGURE_PROMPT
        assert "anachronism_check" in JUDGE_PUBLIC_FIGURE_PROMPT

    def test_anachronism_field_in_json_format(self):
        from scripts.run_validation_study import JUDGE_PUBLIC_FIGURE_PROMPT
        assert '"result": "PASS or FAIL"' in JUDGE_PUBLIC_FIGURE_PROMPT


# ============================================================
# ANTI-ANACHRONISM IN PREDICTIONS PROMPTS
# ============================================================

class TestAntiAnachronismInPrompts:
    """Verify anti-anachronism text in PREDICTIONS prompts."""

    def test_predictions_prompt_has_anti_anachronism(self):
        from scripts.author_layers import PREDICTIONS_PROMPT
        assert "ANTI-ANACHRONISM" in PREDICTIONS_PROMPT

    def test_single_domain_prompt_has_anti_anachronism(self):
        from scripts.author_layers import PREDICTIONS_SINGLE_DOMAIN_PROMPT
        assert "ANTI-ANACHRONISM" in PREDICTIONS_SINGLE_DOMAIN_PROMPT


# ============================================================
# BRIEF COMPLETENESS VERIFICATION (Quality Gate)
# ============================================================

class TestExtractRequiredTerms:
    """Verify extract_required_terms parses source layers correctly."""

    def test_extracts_axiom_mechanisms(self):
        from scripts.agent_pipeline import extract_required_terms
        layers = {
            "anchors": "**COHERENCE**\nSome text\n**INTEGRITY**\nMore text\n**OWNERSHIP**\n",
            "core": "",
            "predictions": "",
        }
        result = extract_required_terms(layers)
        mechanisms = result.get("axiom_mechanisms", [])
        names = [t[0] for t in mechanisms]
        assert "COHERENCE" in names
        assert "INTEGRITY" in names
        assert "OWNERSHIP" in names
        # Each entry should have mechanism keywords
        for name, keywords, desc in mechanisms:
            assert len(keywords) > 0

    def test_extracts_contested_marker(self):
        from scripts.agent_pipeline import extract_required_terms
        layers = {
            "anchors": "**SIGNAL-PROCESSING** [CONTESTED]\n[THIN DATA] warning\n",
            "core": "",
            "predictions": "",
        }
        result = extract_required_terms(layers)
        marker_terms = [t[0] for t in result.get("markers", [])]
        assert "CONTESTED" in marker_terms
        assert "THIN DATA" in marker_terms

    def test_extracts_core_context_modes(self):
        from scripts.agent_pipeline import extract_required_terms
        layers = {
            "anchors": "",
            "core": "**Trading Context:** He trades.\n**Creative/Hobby Context:** Cooking and gaming.\n**Personal/Family Context:** Navigate carefully.",
            "predictions": "",
        }
        result = extract_required_terms(layers)
        kw_terms = [t[0] for t in result.get("core_keywords", [])]
        assert "trading" in kw_terms
        assert "creative/hobby" in kw_terms
        assert "personal/family" in kw_terms

    def test_extracts_prediction_names(self):
        from scripts.agent_pipeline import extract_required_terms
        layers = {
            "anchors": "",
            "core": "",
            "predictions": "## 1. ANALYSIS-PARALYSIS SPIRAL\ntext\n## 2. PERFECTIONISM-TO-INACTION\ntext\n",
        }
        result = extract_required_terms(layers)
        names = [t[0] for t in result.get("prediction_names", [])]
        assert "ANALYSIS-PARALYSIS SPIRAL" in names
        assert "PERFECTIONISM-TO-INACTION" in names

    def test_returns_empty_for_empty_layers(self):
        from scripts.agent_pipeline import extract_required_terms
        result = extract_required_terms({"anchors": "", "core": "", "predictions": ""})
        assert isinstance(result, dict)


class TestVerifyBriefCompleteness:
    """Verify the quality gate catches missing terms."""

    def test_detects_missing_axiom_mechanism(self):
        from scripts.agent_pipeline import verify_brief_completeness
        required = {
            "axiom_mechanisms": [
                ("COHERENCE", ["coherence", "internal consistency"], "Axiom 'COHERENCE' mechanism must be represented"),
                ("REASONING-UPDATE", ["reasoning-update", "reasoning update"], "Axiom 'REASONING-UPDATE' mechanism must be represented"),
            ]
        }
        brief = "His need for coherence drives everything."
        gaps = verify_brief_completeness(brief, required)
        assert len(gaps) == 1
        assert "REASONING-UPDATE" in gaps[0]

    def test_passes_when_mechanisms_present(self):
        from scripts.agent_pipeline import verify_brief_completeness
        required = {
            "axiom_mechanisms": [
                ("COHERENCE", ["coherence", "internal consistency"], "test"),
                ("INTEGRITY", ["integrity", "follow-through"], "test"),
            ],
            "core_keywords": [("cooking", "test"), ("gaming", "test")],
        }
        brief = "His need for internal consistency and integrity shape everything. He enjoys cooking and gaming."
        gaps = verify_brief_completeness(brief, required)
        assert len(gaps) == 0

    def test_detects_missing_marker(self):
        from scripts.agent_pipeline import verify_brief_completeness
        required = {"markers": [("CONTESTED", "[CONTESTED] must appear")]}
        brief = "The axiom is debatable but we did not flag it."
        gaps = verify_brief_completeness(brief, required)
        assert len(gaps) == 1

    def test_detects_missing_context_mode(self):
        from scripts.agent_pipeline import verify_brief_completeness
        required = {"core_keywords": [("creative/hobby", "CORE context mode: 'Creative/Hobby'")]}
        brief = "He works in trading and startups."
        gaps = verify_brief_completeness(brief, required)
        assert len(gaps) == 1
        assert "Creative/Hobby" in gaps[0]


class TestCompositionPromptCompleteness:
    """Verify the updated composition prompt enforces completeness."""

    def test_prompt_requires_completeness(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "COMPLETENESS" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_no_token_limit(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "3,000-5,000 tokens" not in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_no_density_over_completeness(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "Density over completeness" not in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_has_no_self_reference(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "NO SELF-REFERENCE" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_requires_axiom_mechanisms(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "axiom" in UNIFIED_BRIEF_COMPOSITION_PROMPT.lower()
        assert "MECHANISM" in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "ANTI-ENUMERATION" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_requires_directives(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "Directives" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_requires_false_positives(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "False positive warnings" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_requires_context_modes(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "Context modes" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_requires_contested_markers(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "[CONTESTED]" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_requires_thin_data(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "[THIN DATA]" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_has_anti_hallucination_constraint(self):
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "ANTI-HALLUCINATION" in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "Do NOT invent" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_no_user_specific_pattern_names(self):
        """Composition prompt must not contain user-specific pattern examples."""
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "SIGNAL-PROCESSING" not in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "FRUSTRATION-TO-EXISTENTIAL" not in UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "ANALYSIS-PARALYSIS" not in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_conditional_completeness(self):
        """Completeness requirements should be conditional on source content."""
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "IF AND ONLY IF they exist" in UNIFIED_BRIEF_COMPOSITION_PROMPT

    def test_prompt_handles_missing_predictions(self):
        """Prompt should handle missing PREDICTIONS layer gracefully."""
        from scripts.agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT
        assert "no PREDICTIONS layer" in UNIFIED_BRIEF_COMPOSITION_PROMPT.lower() or \
               "If no PREDICTIONS layer exists" in UNIFIED_BRIEF_COMPOSITION_PROMPT


class TestPromptContaminationCheck:
    """Verify deterministic contamination check catches verbatim prompt examples."""

    def test_detects_legacy_contamination(self):
        from scripts.author_layers import check_prompt_contamination
        text = "If your response contains internal inconsistency, flag it before they find it — they will detect it and trust you less for not catching it first."
        found = check_prompt_contamination(text)
        assert len(found) >= 1
        assert any("detect it and trust you less" in p for p in found)

    def test_detects_current_example_contamination(self):
        from scripts.author_layers import check_prompt_contamination
        text = "Before proposing a plan, audit it for resource waste because Alex will reject anything that allocates effort without measurable return."
        found = check_prompt_contamination(text)
        assert len(found) >= 1

    def test_passes_clean_output(self):
        from scripts.author_layers import check_prompt_contamination
        text = "When systems lack internal alignment, surface the contradiction directly rather than working around it. Mismatches between stated intent and observable action require immediate attention."
        found = check_prompt_contamination(text)
        assert len(found) == 0

    def test_case_insensitive(self):
        from scripts.author_layers import check_prompt_contamination
        text = "They Will Detect It And Trust You Less For Not Catching It First."
        found = check_prompt_contamination(text)
        assert len(found) >= 1

    def test_detects_emotion_example(self):
        from scripts.author_layers import check_prompt_contamination
        text = "When they present emotional reactions, reflect the reaction back as data — name the pattern, locate it in context, treat the signal as input to analysis rather than the conclusion."
        found = check_prompt_contamination(text)
        assert len(found) >= 1


class TestParseClaimsFromLayer:
    """Verify claim parsing from layer structure (for vector provenance generation)."""

    def test_parses_anchors_claims(self):
        from scripts.verify_provenance import parse_claims_from_layer
        text = """
**A1. COHERENCE**
If your response contains internal inconsistency, flag it before presenting.
Active when: they point out contradictions.

**A2. INTEGRITY**
Don't validate intentions without examining follow-through.
Active when: they describe someone saying one thing but doing another.
"""
        claims = parse_claims_from_layer("ANCHORS", text)
        assert len(claims) == 2
        assert claims[0]["claim_id"] == "A1"
        assert "inconsistency" in claims[0]["claim_text"]
        assert claims[1]["claim_id"] == "A2"

    def test_parses_predictions_claims(self):
        from scripts.verify_provenance import parse_claims_from_layer
        text = """
**P1. CONFIRMATION-BEFORE-COMMITMENT**: When facing uncertain situations → waits for multiple confirming signals
Detection: Trading (waits for range breaks); Professional (clarifies goals)
Directive: Present multiple supporting data points.

**P2. STRUCTURE-OVER-SPONTANEITY**: When presented with open-ended situations → imposes systematic frameworks
Detection: Trading (uses fixed dollar loss limits); Personal (prioritizes control)
Directive: Lead with systematic approaches.
"""
        claims = parse_claims_from_layer("PREDICTIONS", text)
        assert len(claims) == 2
        assert claims[0]["claim_id"] == "P1"
        assert claims[1]["claim_id"] == "P2"
        assert "confirming signals" in claims[0]["claim_text"]

    def test_skips_short_claims(self):
        from scripts.verify_provenance import parse_claims_from_layer
        text = "**A1. SHORT**\nOk.\n\n**A2. REAL**\nThis is a real claim with enough text to matter for provenance."
        claims = parse_claims_from_layer("ANCHORS", text)
        assert len(claims) == 1
        assert claims[0]["claim_id"] == "A2"

    def test_handles_core_sections(self):
        from scripts.verify_provenance import parse_claims_from_layer
        text = """
**M1. COMMUNICATION APPROACH**
They prioritize understanding why systems work over following them blindly.
Deliver information directly and efficiently with no fluff.

**C1. TRADING CONTEXT**
Extreme ownership mindset with rigorous risk management through fixed limits.
"""
        claims = parse_claims_from_layer("CORE", text)
        assert len(claims) == 2
        assert claims[0]["claim_id"] == "M1"
        assert claims[1]["claim_id"] == "C1"


class TestProvenanceCoverageCheck:
    """Verify provenance coverage check flags low/empty citation results."""

    def test_good_coverage(self):
        from scripts.author_layers import check_provenance_coverage
        text = "**A1. COHERENCE**\nLong claim text here about coherence.\n\n**A2. INTEGRITY**\nLong claim about integrity alignment."
        prov = [
            {"claim_id": "A1_cite", "claim_text": "coherence...", "fact_ids": ["f1"]},
            {"claim_id": "A2_cite", "claim_text": "integrity...", "fact_ids": ["f2"]},
        ]
        result = check_provenance_coverage(text, prov, "ANCHORS", input_count=9)
        assert result["status"] == "GOOD"
        assert result["citations_returned"] == 2

    def test_empty_coverage(self):
        from scripts.author_layers import check_provenance_coverage
        text = "**A1. COHERENCE**\nBig paragraph about coherence axiom and how it works in practice."
        prov = []
        result = check_provenance_coverage(text, prov, "ANCHORS", input_count=9)
        assert result["status"] == "EMPTY"
        assert result["citations_returned"] == 0

    def test_none_provenance(self):
        from scripts.author_layers import check_provenance_coverage
        result = check_provenance_coverage("text", None, "ANCHORS")
        assert result["status"] == "EMPTY"

    def test_low_coverage(self):
        from scripts.author_layers import check_provenance_coverage
        # 10 bold sections but only 1 citation = 10%
        text = "\n\n".join([f"**A{i}. NAME{i}**\n{'X' * 100}" for i in range(10)])
        prov = [{"claim_id": "A1_cite", "claim_text": "...", "fact_ids": ["f1"]}]
        result = check_provenance_coverage(text, prov, "CORE", input_count=50)
        assert result["status"] == "LOW"


class TestVerifyBriefFaithfulness:
    """Verify the anti-hallucination gate catches fabricated content."""

    def test_detects_hallucinated_pattern(self):
        from scripts.agent_pipeline import verify_brief_faithfulness
        brief = "He exhibits the SIGNAL-PROCESSING pattern when analyzing data."
        layers = {"anchors": "**REASON-PRIMACY**\nHe reasons.", "core": "", "predictions": ""}
        warnings = verify_brief_faithfulness(brief, layers)
        hallucinated = [w for w in warnings if "SIGNAL-PROCESSING" in w]
        assert len(hallucinated) > 0

    def test_passes_when_pattern_in_source(self):
        from scripts.agent_pipeline import verify_brief_faithfulness
        brief = "The REASON-PRIMACY axiom drives his thinking."
        layers = {"anchors": "**REASON-PRIMACY**\nHe values reason.", "core": "", "predictions": ""}
        warnings = verify_brief_faithfulness(brief, layers)
        hallucinated_patterns = [w for w in warnings if "HALLUCINATED PATTERN" in w]
        assert len(hallucinated_patterns) == 0

    def test_detects_hallucinated_technical_term(self):
        from scripts.agent_pipeline import verify_brief_faithfulness
        brief = "He has an appreciation for the E46 M3 car and its engineering."
        layers = {"anchors": "**COURAGE**\nHe is brave.", "core": "", "predictions": ""}
        warnings = verify_brief_faithfulness(brief, layers)
        # Should flag E46 as not in source
        e46_warnings = [w for w in warnings if "E46" in w]
        assert len(e46_warnings) > 0

    def test_clean_brief_passes(self):
        from scripts.agent_pipeline import verify_brief_faithfulness
        brief = "He values REASON-PRIMACY above all. His COURAGE guides his actions."
        layers = {
            "anchors": "**REASON-PRIMACY**\nValues reason.\n**COURAGE**\nActs bravely.",
            "core": "",
            "predictions": "",
        }
        warnings = verify_brief_faithfulness(brief, layers)
        hallucinated = [w for w in warnings if "HALLUCINATED" in w]
        assert len(hallucinated) == 0

    def test_ignores_lexicon_ids(self):
        from scripts.agent_pipeline import verify_brief_faithfulness
        brief = "A1. REASON guides him. P1. COURAGE pattern."
        layers = {"anchors": "**REASON**\ntext", "core": "", "predictions": ""}
        warnings = verify_brief_faithfulness(brief, layers)
        # A1, P1 are format labels, should not be flagged
        id_warnings = [w for w in warnings if "'A1'" in w or "'P1'" in w]
        assert len(id_warnings) == 0


# ============================================================
# CHROMADB DISTANCE CONVERSION
# ============================================================

class TestChromaDBDistToSimilarity:
    """Test the L2 distance → cosine similarity conversion."""

    def test_zero_distance(self):
        from scripts.config import chromadb_dist_to_similarity
        assert chromadb_dist_to_similarity(0) == 1.0

    def test_typical_l2_distance(self):
        from scripts.config import chromadb_dist_to_similarity
        # L2 = 1.0 on normalized vectors → cos_sim = 1 - 0.5 = 0.5
        sim = chromadb_dist_to_similarity(1.0)
        assert abs(sim - 0.5) < 0.01

    def test_high_l2_distance(self):
        from scripts.config import chromadb_dist_to_similarity
        # L2 = sqrt(2) → cos_sim = 1 - 1 = 0 (orthogonal)
        sim = chromadb_dist_to_similarity(1.414)
        assert sim < 0.01

    def test_very_high_distance_clamps_to_zero(self):
        from scripts.config import chromadb_dist_to_similarity
        sim = chromadb_dist_to_similarity(2.0)
        assert sim == 0.0

    def test_small_l2_distance(self):
        from scripts.config import chromadb_dist_to_similarity
        # L2 = 0.5 → cos_sim = 1 - 0.125 = 0.875
        sim = chromadb_dist_to_similarity(0.5)
        assert abs(sim - 0.875) < 0.01


# ============================================================
# VECTOR PROVENANCE — CLAIM PARSING WITH DIRECTIVE STRIPPING
# ============================================================

class TestClaimParsingDirectiveStrip:
    """Verify that Directive: and False positive lines are excluded from claims."""

    def test_strips_directive_lines(self):
        from scripts.verify_provenance import parse_claims_from_layer
        layer_text = """**P1. TEST-PATTERN**: When triggered
Detection: Shows up in trading and cooking
Directive: Tell the AI to do something specific
provenance: [F-001, F-002]"""
        claims = parse_claims_from_layer("PREDICTIONS", layer_text)
        assert len(claims) == 1
        assert "Directive" not in claims[0]["claim_text"]
        assert "Detection" in claims[0]["claim_text"]

    def test_strips_false_positive_lines(self):
        from scripts.verify_provenance import parse_claims_from_layer
        layer_text = """**P1. TEST-PATTERN**: When triggered
Detection: Shows up in multiple domains
False positive warning: Do not apply when X
Directive: Do Y"""
        claims = parse_claims_from_layer("PREDICTIONS", layer_text)
        assert len(claims) == 1
        assert "False positive" not in claims[0]["claim_text"]
        assert "Directive" not in claims[0]["claim_text"]
