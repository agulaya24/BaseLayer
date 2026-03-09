"""
Tests for agent_pipeline.py — cycle numbering, run directory management,
artifact I/O, agent definitions, and prompt construction.

All tests run without API keys or external services.
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ============================================================
# CYCLE NUMBERING
# ============================================================

class TestCycleNumbering:
    """Test cycle number determination from existing run directories."""

    def test_first_cycle_no_runs_dir(self, tmp_path):
        from scripts.agent_pipeline import _get_next_cycle_number
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", tmp_path / "nonexistent"):
            result = _get_next_cycle_number()
        assert result == 1

    def test_first_cycle_empty_runs_dir(self, tmp_path):
        from scripts.agent_pipeline import _get_next_cycle_number
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", runs_dir):
            result = _get_next_cycle_number()
        assert result == 1

    def test_increments_from_existing(self, tmp_path):
        from scripts.agent_pipeline import _get_next_cycle_number
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        (runs_dir / "cycle_001_20260101_120000").mkdir()
        (runs_dir / "cycle_002_20260102_120000").mkdir()
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", runs_dir):
            result = _get_next_cycle_number()
        assert result == 3

    def test_ignores_non_cycle_dirs(self, tmp_path):
        from scripts.agent_pipeline import _get_next_cycle_number
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        (runs_dir / "cycle_005_20260101_120000").mkdir()
        (runs_dir / "other_directory").mkdir()
        (runs_dir / "notes.txt").write_text("ignore me")
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", runs_dir):
            result = _get_next_cycle_number()
        assert result == 6


# ============================================================
# RUN DIRECTORY MANAGEMENT
# ============================================================

class TestCreateRunDir:
    """Test run directory creation and manifest writing."""

    def test_creates_directory(self, tmp_path):
        from scripts.agent_pipeline import create_run_dir
        runs_dir = tmp_path / "runs"
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", runs_dir):
            run_dir = create_run_dir()
        assert run_dir.exists()
        assert run_dir.is_dir()

    def test_creates_manifest(self, tmp_path):
        from scripts.agent_pipeline import create_run_dir
        runs_dir = tmp_path / "runs"
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", runs_dir):
            run_dir = create_run_dir()
        manifest = run_dir / "00_manifest.md"
        assert manifest.exists()
        content = manifest.read_text(encoding="utf-8")
        assert "Cycle" in content
        assert "D-054" in content

    def test_directory_name_format(self, tmp_path):
        from scripts.agent_pipeline import create_run_dir
        runs_dir = tmp_path / "runs"
        with patch("scripts.agent_pipeline.AGENT_RUNS_DIR", runs_dir):
            run_dir = create_run_dir()
        assert run_dir.name.startswith("cycle_001_")


# ============================================================
# ARTIFACT I/O
# ============================================================

class TestArtifactIO:
    """Test artifact writing and reading."""

    def test_write_artifact(self, tmp_path):
        from scripts.agent_pipeline import write_artifact
        filepath = write_artifact(tmp_path, "test.md", "Hello world")
        assert filepath.exists()
        assert filepath.read_text(encoding="utf-8") == "Hello world"

    def test_write_artifact_with_header(self, tmp_path):
        from scripts.agent_pipeline import write_artifact
        filepath = write_artifact(tmp_path, "test.md", "Content",
                                  header={"step": "1", "layer": "anchors"})
        content = filepath.read_text(encoding="utf-8")
        assert "<!-- step: 1 -->" in content
        assert "<!-- layer: anchors -->" in content
        assert "Content" in content

    def test_read_artifact(self, tmp_path):
        from scripts.agent_pipeline import read_artifact
        (tmp_path / "test.md").write_text("Test content", encoding="utf-8")
        result = read_artifact(tmp_path, "test.md")
        assert result == "Test content"

    def test_read_artifact_missing(self, tmp_path):
        from scripts.agent_pipeline import read_artifact
        result = read_artifact(tmp_path, "nonexistent.md")
        assert result is None

    def test_read_step_artifacts(self, tmp_path):
        from scripts.agent_pipeline import read_step_artifacts
        (tmp_path / "02_agent_anchors.md").write_text("Anchors", encoding="utf-8")
        (tmp_path / "02_agent_core.md").write_text("Core", encoding="utf-8")
        result = read_step_artifacts(tmp_path, "02_agent")
        assert "anchors" in result
        assert "core" in result
        assert result["anchors"] == "Anchors"

    def test_read_step_artifacts_partial(self, tmp_path):
        from scripts.agent_pipeline import read_step_artifacts
        (tmp_path / "02_agent_anchors.md").write_text("Anchors", encoding="utf-8")
        result = read_step_artifacts(tmp_path, "02_agent")
        assert "anchors" in result
        assert "core" not in result
        assert "predictions" not in result


# ============================================================
# AGENT DEFINITIONS
# ============================================================

class TestLoadAgentDefinition:
    """Test loading agent definitions from agents/ directory."""

    def test_loads_existing_definition(self, tmp_path):
        from scripts.agent_pipeline import load_agent_definition
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "anchors_agent.md").write_text(
            "# Anchors Agent\nYou are the anchors agent.", encoding="utf-8")
        with patch("scripts.agent_pipeline.AGENT_DEFINITIONS_DIR", agents_dir):
            result = load_agent_definition("anchors_agent")
        assert "Anchors Agent" in result

    def test_missing_definition_raises(self, tmp_path):
        from scripts.agent_pipeline import load_agent_definition
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        with patch("scripts.agent_pipeline.AGENT_DEFINITIONS_DIR", agents_dir):
            with pytest.raises(FileNotFoundError):
                load_agent_definition("nonexistent_agent")


# ============================================================
# BUILD_AGENT_PROMPT
# ============================================================

class TestBuildAgentPrompt:
    """Test agent prompt construction with D-053 contamination rules."""

    def test_includes_all_sections(self):
        from scripts.agent_pipeline import build_agent_prompt
        result = build_agent_prompt(
            layer_name="anchors",
            agent_definition="Agent definition text",
            sonnet_output="Sonnet output text",
            facts_text="Formatted facts",
        )
        assert "Agent definition text" in result
        assert "Sonnet output text" in result
        assert "Formatted facts" in result
        assert "Instructions" in result

    def test_includes_fix_directives(self):
        from scripts.agent_pipeline import build_agent_prompt
        result = build_agent_prompt(
            layer_name="core",
            agent_definition="Def",
            sonnet_output="Output",
            facts_text="Facts",
            fix_directives=["Fix issue A", "Fix issue B"],
        )
        assert "Fix Directives" in result
        assert "Fix issue A" in result
        assert "Fix issue B" in result

    def test_no_fix_directives_section_when_none(self):
        from scripts.agent_pipeline import build_agent_prompt
        result = build_agent_prompt(
            layer_name="predictions",
            agent_definition="Def",
            sonnet_output="Output",
            facts_text="Facts",
        )
        assert "Fix Directives" not in result


