# Phase 2: Test Audit — 2026-03-09

## 2.1 Test Suite Results
Total: 400 | Passed: 368 | Failed: 32 | Errors: 0 | Skipped: 0

### Failed Tests

**test_agent_pipeline.py — 18 failures — ImportError: functions removed from agent_pipeline.py**
- `TestCycleNumbering::test_first_cycle_no_runs_dir` — cannot import `_get_next_cycle_number`
- `TestCycleNumbering::test_first_cycle_empty_runs_dir` — cannot import `_get_next_cycle_number`
- `TestCycleNumbering::test_increments_from_existing` — cannot import `_get_next_cycle_number`
- `TestCycleNumbering::test_ignores_non_cycle_dirs` — cannot import `_get_next_cycle_number`
- `TestCreateRunDir::test_creates_directory` — cannot import `create_run_dir`
- `TestCreateRunDir::test_creates_manifest` — cannot import `create_run_dir`
- `TestCreateRunDir::test_directory_name_format` — cannot import `create_run_dir`
- `TestArtifactIO::test_write_artifact` — cannot import `write_artifact`
- `TestArtifactIO::test_write_artifact_with_header` — cannot import `write_artifact`
- `TestArtifactIO::test_read_artifact` — cannot import `read_artifact`
- `TestArtifactIO::test_read_artifact_missing` — cannot import `read_artifact`
- `TestArtifactIO::test_read_step_artifacts` — cannot import `read_step_artifacts`
- `TestArtifactIO::test_read_step_artifacts_partial` — cannot import `read_step_artifacts`
- `TestLoadAgentDefinition::test_loads_existing_definition` — cannot import `load_agent_definition`
- `TestLoadAgentDefinition::test_missing_definition_raises` — cannot import `load_agent_definition`
- `TestBuildAgentPrompt::test_includes_all_sections` — cannot import `build_agent_prompt`
- `TestBuildAgentPrompt::test_includes_fix_directives` — cannot import `build_agent_prompt`
- `TestBuildAgentPrompt::test_no_fix_directives_section_when_none` — cannot import `build_agent_prompt`

**test_unified_brief.py — 13 failures — two distinct root causes**

ModuleNotFoundError: `scripts.run_validation_study` does not exist (archived to `scripts/archive/eval_scripts/`):
- `TestManifestIncludesStep7::test_manifest_has_unified_brief_step` — imports `create_run_dir` from `agent_pipeline` (same as above)
- `TestAblationC2AP::test_ablation_layers_has_c2ap` — imports `ABLATION_LAYERS` from `run_validation_study`
- `TestAblationC2AP::test_condition_prompts_has_c2ap` — imports `CONDITION_PROMPTS` from `run_validation_study`
- `TestAblationC2AP::test_public_figure_conditions_has_c2ap` — imports `PUBLIC_FIGURE_CONDITIONS` from `run_validation_study`
- `TestCMCondition::test_condition_prompts_has_cm` — imports `CONDITION_PROMPTS` from `run_validation_study`
- `TestCMCondition::test_cm_system_prompt_requires_file` — imports `get_system_prompt`, `EVAL_DIR` from `run_validation_study`
- `TestCMCondition::test_cm_system_prompt_loads_file` — imports `get_system_prompt` from `run_validation_study`
- `TestJudgePanelConsensus::test_load_single_model` — imports `_load_all_judge_results` from `run_validation_study`
- `TestJudgePanelConsensus::test_consensus_averages_scores` — imports `_load_all_judge_results` from `run_validation_study`
- `TestJudgePanelConsensus::test_flags_disagreements` — imports `_load_all_judge_results` from `run_validation_study`
- `TestJudgePanelConsensus::test_legacy_fallback` — imports `_load_all_judge_results` from `run_validation_study`
- `TestAnachronismCheck::test_public_figure_prompt_has_anachronism_check` — imports `JUDGE_PUBLIC_FIGURE_PROMPT` from `run_validation_study`
- `TestAnachronismCheck::test_anachronism_field_in_json_format` — imports `JUDGE_PUBLIC_FIGURE_PROMPT` from `run_validation_study`

Logic failure in active code:
- `TestVerifyBriefCompleteness::test_passes_when_mechanisms_present` — `verify_brief_completeness` returns 1 gap when 0 expected; COHERENCE axiom check fails despite keywords "coherence" and "internal consistency" appearing in brief (bug in keyword matching logic in `agent_pipeline.py::verify_brief_completeness`)

### Full pytest Summary
```
========================== short test summary info ===========================
FAILED tests/test_agent_pipeline.py::TestCycleNumbering::test_first_cycle_no_runs_dir
FAILED tests/test_agent_pipeline.py::TestCycleNumbering::test_first_cycle_empty_runs_dir
FAILED tests/test_agent_pipeline.py::TestCycleNumbering::test_increments_from_existing
FAILED tests/test_agent_pipeline.py::TestCycleNumbering::test_ignores_non_cycle_dirs
FAILED tests/test_agent_pipeline.py::TestCreateRunDir::test_creates_directory
FAILED tests/test_agent_pipeline.py::TestCreateRunDir::test_creates_manifest
FAILED tests/test_agent_pipeline.py::TestCreateRunDir::test_directory_name_format
FAILED tests/test_agent_pipeline.py::TestArtifactIO::test_write_artifact
FAILED tests/test_agent_pipeline.py::TestArtifactIO::test_write_artifact_with_header
FAILED tests/test_agent_pipeline.py::TestArtifactIO::test_read_artifact
FAILED tests/test_agent_pipeline.py::TestArtifactIO::test_read_artifact_missing
FAILED tests/test_agent_pipeline.py::TestArtifactIO::test_read_step_artifacts
FAILED tests/test_agent_pipeline.py::TestArtifactIO::test_read_step_artifacts_partial
FAILED tests/test_agent_pipeline.py::TestLoadAgentDefinition::test_loads_existing_definition
FAILED tests/test_agent_pipeline.py::TestLoadAgentDefinition::test_missing_definition_raises
FAILED tests/test_agent_pipeline.py::TestBuildAgentPrompt::test_includes_all_sections
FAILED tests/test_agent_pipeline.py::TestBuildAgentPrompt::test_includes_fix_directives
FAILED tests/test_agent_pipeline.py::TestBuildAgentPrompt::test_no_fix_directives_section_when_none
FAILED tests/test_unified_brief.py::TestManifestIncludesStep7::test_manifest_has_unified_brief_step
FAILED tests/test_unified_brief.py::TestAblationC2AP::test_ablation_layers_has_c2ap
FAILED tests/test_unified_brief.py::TestAblationC2AP::test_condition_prompts_has_c2ap
FAILED tests/test_unified_brief.py::TestAblationC2AP::test_public_figure_conditions_has_c2ap
FAILED tests/test_unified_brief.py::TestCMCondition::test_condition_prompts_has_cm
FAILED tests/test_unified_brief.py::TestCMCondition::test_cm_system_prompt_requires_file
FAILED tests/test_unified_brief.py::TestCMCondition::test_cm_system_prompt_loads_file
FAILED tests/test_unified_brief.py::TestJudgePanelConsensus::test_load_single_model
FAILED tests/test_unified_brief.py::TestJudgePanelConsensus::test_consensus_averages_scores
FAILED tests/test_unified_brief.py::TestJudgePanelConsensus::test_flags_disagreements
FAILED tests/test_unified_brief.py::TestJudgePanelConsensus::test_legacy_fallback
FAILED tests/test_unified_brief.py::TestAnachronismCheck::test_public_figure_prompt_has_anachronism_check
FAILED tests/test_unified_brief.py::TestAnachronismCheck::test_anachronism_field_in_json_format
FAILED tests/test_unified_brief.py::TestVerifyBriefCompleteness::test_passes_when_mechanisms_present
======================= 32 failed, 368 passed in 9.42s ========================
```

---

## 2.2 Tests for Archived/Removed Code

| Test File | What Removed Step It Tests | Still Passing |
|---|---|---|
| `tests/test_unified_brief.py` — `TestAblationC2AP`, `TestCMCondition`, `TestJudgePanelConsensus`, `TestAnachronismCheck` (12 tests) | `run_validation_study.py` — archived eval script (ablation conditions, judge panel, prompts) | No — all 12 fail with ModuleNotFoundError |
| `tests/test_mcp_extended.py::TestRecallMemories::test_no_results` | `assemble_brief.py` — archived assembly step (still exists on disk, patched in test) | Yes — passes (assemble_brief.py has not been deleted, test uses `patch`) |

Note: No test files directly import from `score_facts.py`, `classify_facts_haiku.py`, `reclassify_tiers.py`, `detect_contradictions.py`, or `consolidate_enrichments.py`. Those archived scripts have no corresponding test coverage at all — their tests were never written or were deleted. The `test_unit.py::test_tier_breakdown` test queries the `knowledge_tier` DB column but does not import or exercise any tiering script; it tests the DB schema fixture only.

---

## 2.3 Active Pipeline Coverage

| Script | Test Coverage | Test Files / Functions |
|---|---|---|
| `import_conversations.py` | partial | `tests/test_unit.py` (DB schema + import round-trip via conftest fixtures), `tests/test_edge_cases.py` (malformed input, unicode, duplicates), `tests/test_cli.py::TestCLIInit`, `tests/test_cli.py::test_import_nonexistent_file`. No dedicated `test_import_conversations.py`. Core parsing logic (ChatGPT/Claude JSON formats, directory walk) has no unit tests. |
| `extract_facts.py` | good | `tests/test_extract_normalizers.py` (10 test classes, ~60 tests covering all normalizer functions: category, subject, intent, temporal, fact_class, knowledge_tier, predicate, reconstruct_fact_text, extraction caps, compute_confidence, predicate_to_intent), `tests/test_batch_extract.py` (batch state + conv text builder), `tests/test_unit.py` (extraction log), `tests/test_checkpoint.py` (post-extraction checkpoint). |
| `author_layers.py` | good | `tests/test_author_provenance.py` (large file — format_facts_for_prompt, parse_provenance_from_layer, store_provenance, cap_by_domain, cap_by_category, apply_exclusion_filter, _format_facts_as_document_blocks, _parse_citation_provenance, _adapt_prompt_for_citations, _format_anchors_as_document_blocks), `tests/test_unified_brief.py` (PREDICTIONS_PROMPT, PREDICTIONS_SINGLE_DOMAIN_PROMPT, check_prompt_contamination, check_provenance_coverage). |
| `agent_pipeline.py` | partial | `tests/test_agent_pipeline.py` — 18 of 18 tests FAIL because the functions they target (`_get_next_cycle_number`, `create_run_dir`, `write_artifact`, `read_artifact`, `read_step_artifacts`, `load_agent_definition`, `build_agent_prompt`) no longer exist in the current `agent_pipeline.py`. `tests/test_unified_brief.py` covers `UNIFIED_BRIEF_COMPOSITION_PROMPT`, `store_unified_brief`, `extract_required_terms`, `verify_brief_completeness`, `verify_brief_faithfulness` — these tests mostly pass (1 logic failure noted above). Effective coverage of the compose step's core logic is moderate; the run-dir / artifact orchestration layer is completely untested. |

---

## 2.4 Tests Referencing Removed Features

| Test File:Line | Reference | Context |
|---|---|---|
| `test_unified_brief.py:184` | `from scripts.run_validation_study import ABLATION_LAYERS` | Tests that ablation condition C2AP exists — script archived |
| `test_unified_brief.py:189` | `from scripts.run_validation_study import CONDITION_PROMPTS` | Tests that C2AP appears in condition prompts — script archived |
| `test_unified_brief.py:193` | `from scripts.run_validation_study import PUBLIC_FIGURE_CONDITIONS` | Tests public figure conditions — script archived |
| `test_unified_brief.py:205` | `from scripts.run_validation_study import CONDITION_PROMPTS` | CM condition check — script archived |
| `test_unified_brief.py:209` | `from scripts.run_validation_study import get_system_prompt, EVAL_DIR` | CM system prompt file loading — script archived |
| `test_unified_brief.py:216` | `from scripts.run_validation_study import get_system_prompt` | CM system prompt loading — script archived |
| `test_unified_brief.py:237` | `from scripts.run_validation_study import _load_all_judge_results` | Judge panel consensus (load single model) — script archived |
| `test_unified_brief.py:260` | `from scripts.run_validation_study import _load_all_judge_results` | Judge panel consensus (averages scores) — script archived |
| `test_unified_brief.py:292` | `from scripts.run_validation_study import _load_all_judge_results` | Judge panel disagreement flagging — script archived |
| `test_unified_brief.py:324` | `from scripts.run_validation_study import _load_all_judge_results` | Legacy fallback — script archived |
| `test_unified_brief.py:353` | `from scripts.run_validation_study import JUDGE_PUBLIC_FIGURE_PROMPT` | Anachronism check in judge prompt — script archived |
| `test_unified_brief.py:358` | `from scripts.run_validation_study import JUDGE_PUBLIC_FIGURE_PROMPT` | Anachronism JSON field check — script archived |
| `test_mcp_extended.py:269` | `patch("scripts.assemble_brief.get_theme_block", ...)` | recall_memories test patches assemble_brief functions — assemble_brief still on disk, test passes |

---

## Summary

The test suite has 400 tests: 368 pass, 32 fail. Failures fall into three distinct categories.

**Category 1 — agent_pipeline.py interface drift (18 failures).** `test_agent_pipeline.py` was written against an older, more complex version of `agent_pipeline.py` that exposed cycle-numbering, run-directory management, and agent-prompt-building as importable functions. After the S79 pipeline simplification, those functions were removed or restructured. All 18 tests in this file fail with ImportError. The compose step does have coverage through `test_unified_brief.py` (prompt content, brief storage, term extraction, completeness checks), but the orchestration layer itself is now completely unverified by tests.

**Category 2 — archived eval script referenced from active test file (12 failures).** `test_unified_brief.py` contains a block of tests for `run_validation_study.py` (ablation conditions, judge panel consensus, anachronism prompts). That script was moved to `scripts/archive/eval_scripts/` but the tests were not removed or updated. All 12 fail with ModuleNotFoundError.

**Category 3 — logic regression in verify_brief_completeness (1 failure).** `test_unified_brief.py::TestVerifyBriefCompleteness::test_passes_when_mechanisms_present` fails with an assertion error. The function returns a gap for the COHERENCE axiom even though both required keywords ("coherence", "internal consistency") appear in the test brief. This is a bug in the keyword matching logic inside `verify_brief_completeness` in `scripts/agent_pipeline.py`, not a test misconfiguration.

The overall health of the suite is good for the extraction and authoring layers — `extract_facts.py` and `author_layers.py` have thorough, passing unit tests. Import coverage is adequate at the DB schema level but thin on the actual file-parsing logic. The compose step (`agent_pipeline.py`) is the most exposed: its orchestration functions have no working tests, and it has one confirmed logic bug in the quality gate.
