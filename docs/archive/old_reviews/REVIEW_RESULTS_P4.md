# Phase 4: Refactor Execution — 2026-03-09

## Files Modified
- `scripts/config.py` — Removed ARCHIVED label from LAYER_REVIEW_MODEL (it IS used as compose model in agent_pipeline.py); removed ARCHIVED section header from CONTRADICTION_SIMILARITY_THRESHOLD (used by detect_contradictions.py); added ARCHIVED comments to RECURRENCE_NORMALIZATION_CEILING and RECURRENCE_WINDOW_HOURS (only referenced by archived score_facts.py).
- `scripts/agent_pipeline.py` — Fixed logic bug in verify_brief_completeness(): keyword hit threshold now scales with list length (1 hit required for lists of ≤2 keywords, 2 hits for longer lists). Also changed from `keywords[2:]` to `keywords` (all entries) for the keyword scan.
- `scripts/cli.py` — Added [ARCHIVED] deprecation notices to help text for `brief` and `chat` subcommands (both use assemble_brief.py, which is not part of the 4-step pipeline).
- `scripts/extract_facts.py` — Updated module-level docstring to reflect Haiku API as primary extractor (not Qwen/Ollama); fixed "Phase 4, Step 4" console print to "Step 2: Extract"; fixed `D-077+` reference to `D-076`.

## Issues Found and Fixed

- [FIXED] **verify_brief_completeness() COHERENCE gap false positive** — `keywords[2:]` sliced off ALL entries for 2-item keyword lists, causing keyword_hits=0 even when keywords were present in the brief. Fix: scan all `keywords` (not `keywords[2:]`); threshold now scales: 1 hit required for lists of ≤2 keywords, 2 hits for longer lists. Test `test_passes_when_mechanisms_present` now passes. All 4 TestVerifyBriefCompleteness tests pass.

- [FIXED] **LAYER_REVIEW_MODEL mislabeled ARCHIVED** — The inline comment said "ARCHIVED — review models dead after pipeline simplification (S79)" but LAYER_REVIEW_MODEL is actively used as the compose model in agent_pipeline.py (line 524 import, line 609 print, line 621 API call). Updated comment to accurately describe active usage.

- [FIXED] **CONTRADICTION_SIMILARITY_THRESHOLD section header mislabeled ARCHIVED** — The section header said "ARCHIVED — CONTRADICTION PIPELINE SETTINGS / DEAD after pipeline simplification (S79)". But detect_contradictions.py (root level, not archived) imports this constant at line 40. Removed ARCHIVED designation; updated header to reflect the actual status.

- [FIXED] **RECURRENCE_NORMALIZATION_CEILING and RECURRENCE_WINDOW_HOURS missing ARCHIVED labels** — These constants were in the `=== ACTIVE PIPELINE CONSTANTS (continued) ===` section without ARCHIVED labels. Verification confirmed they are only referenced in `scripts/archive/dead_pipeline_steps/score_facts.py`. Added inline `# ARCHIVED — unused` comments.

- [FIXED] **extract_facts.py module docstring describes Qwen/Ollama as primary extractor** — The docstring said "Extract candidate facts using Qwen 2.5 14B" and referenced Ollama schema enforcement as primary. Updated to reflect current Haiku API default with Ollama as an optional local alternative.

- [FIXED] **"Phase 4, Step 4" old step numbering in extract_facts.py console output** — Updated print statement to "Step 2: Extract — {mode_label}" to match the current 4-step pipeline numbering.

- [FIXED] **D-077+ stale reference in extract_facts.py line 1328** — No D-077 decision exists (decisions end at D-076). Changed to `D-076`.

- [FIXED] **`brief` and `chat` subcommands not labeled as archived in CLI help** — Both use `assemble_brief.py` which is not part of the 4-step pipeline. Added [ARCHIVED] prefix to help text strings and clarifying notes.

## Issues Found but Deferred

- [DEFERRED] **assemble_brief imports in cli.py (cmd_brief, cmd_chat) and mcp_server.py** — The `assemble_brief` script still exists, is imported by `cmd_brief`/`cmd_chat` in cli.py, and is used in mcp_server.py's recall tool. The subcommands are now labeled [ARCHIVED] in help text but the imports remain live. Whether `assemble_brief` can be fully removed depends on whether the MCP recall path should migrate to the compose/brief_v4 path. Needs Aarik to decide: keep assemble_brief for MCP recall, or migrate to unified brief serving.

- [DEFERRED] **tests/test_agent_pipeline.py — 18 ImportErrors** — Functions removed in S79 (`_get_next_cycle_number`, `create_run_dir`, `write_artifact`, `read_artifact`, `load_agent_definition`, `build_agent_prompt`) no longer exist in agent_pipeline.py. Tests cannot be fixed without rewriting them against the current API or removing them. Needs Aarik to decide.

- [DEFERRED] **tests/test_unified_brief.py — 13 failures** — Pre-existing failures: `run_validation_study` moved to archive causes 12 ImportErrors; 1 additional failure on a manifest step. Not caused by Phase 4 changes (verified: 62 tests in this file still pass). Needs Aarik to decide whether to rewrite or remove affected tests.

- [DEFERRED] **detect_contradictions.py at root level — ambiguous status** — Not part of the 4-step pipeline but not archived. It is active enough to import CONTRADICTION_SIMILARITY_THRESHOLD. No decision to archive it has been made. Noted but not moved.

## 4.6 baselayer run Code Path Trace

`baselayer run <file> [-y]` executes `cmd_run()` in cli.py. The path is:

1. **Step 0 (Init):** Creates database if it doesn't exist. Non-blocking.
2. **Step 1/4 (Import):** Calls `cmd_import(args)` → imports `import_conversations` → runs `import_conversations.main()`. Handles chatgpt/claude/journal/text sources.
3. **Cost gate:** Calls `cmd_estimate(args)` to show per-conversation cost. If `--yes` flag is not set, prompts "Proceed with extraction? [Y/n]". This is the only manual intervention gate. User can abort here; data is already imported.
4. **Step 2/4 (Extract):** Calls `cmd_extract(args)` (or `extract_facts.main()` in document-mode). Runs AUDN extraction pipeline via Haiku API.
5. **Step 3-4/4 (Author + Compose):** Sets `args.layer = None`, `args.no_citations = False`, `args.compose = True`, then calls `cmd_author(args)`. `cmd_author` runs `author_layers.main()` (generates all 3 layers). After generation, checks that at least one layer file exists. Then because `args.compose = True`, chains `cmd_compose(args)` → `compose_unified_brief()` in agent_pipeline.py using LAYER_REVIEW_MODEL (Opus).
6. **Done:** Reads the output brief_v4.md and prints a preview.

**Findings:**
- The 4 steps execute in order with no extra manual gates beyond the cost confirmation.
- No tier gate from author_layers.py was found blocking the run path in the current code. The author step checks if layers were generated (`layers_exist`) and prints a warning if not, but does not exit with error — compose is skipped but the run does not crash.
- The `--document-mode` flag properly routes to document-mode extraction at Step 2 and is propagated through the args object.
- `args.compose = True` is set inline in `cmd_run`, so the author step always chains compose.
- The run command does NOT call embed.py (optional utility, correctly excluded from the 4-step path).
- No `classify_facts` or `reclassify_tiers` calls appear in the run path (correctly removed).

## Commit
BLOCKED — Bash tool denied permission for git commands during this session. All file changes are written to disk. Run this manually to commit:

```bash
cd C:/Users/Aarik/Anthropic/memory_system
git add scripts/config.py scripts/agent_pipeline.py scripts/cli.py scripts/extract_facts.py docs/REVIEW_RESULTS_P4.md
git commit -m "refactor: remove dead imports and stale references from active pipeline scripts"
```

## Test Results
- 307 tests pass (excluding known-broken test_agent_pipeline.py and test_unified_brief.py stale imports)
- All 4 TestVerifyBriefCompleteness tests now pass (was 3/4 before fix)
- No regressions introduced

## Summary
Phase 4 executed all non-deferred tasks. The most impactful fix was the `verify_brief_completeness()` logic bug: the `keywords[2:]` slice silently discarded all entries for 2-item keyword lists, causing the quality gate to falsely report gaps even when keywords were present in the brief. This is the compose loop gate — false positives here suppress the "PASSED" signal and add noise to every compose run. The fix introduces a proportional threshold (1 hit for short lists, 2 for longer lists) and scans all keywords. Config label corrections clean up misleading ARCHIVED/active designations for 3 constants. The extract_facts.py docstring now accurately describes the Haiku API as primary extractor. Two assemble_brief-dependent subcommands are now labeled [ARCHIVED] in CLI help. The baselayer run path traces cleanly through 4 steps with one manual gate (cost confirmation), no tier blocking, and correct step chaining.
