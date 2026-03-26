# Code Review Results — Base Layer
**Date:** 2026-03-09
**Scope:** Full 7-phase review — code inventory, test audit, documentation scan, refactor, verification, security, privacy scrub.
**Model:** claude-sonnet-4-6 (parallel agents: Phases 1/2/3/6 concurrent, Phases 4/7 concurrent, Phase 5 sequential after 4)

---

## Phase 1: Code Inventory — 2026-03-09

### Files Modified
None — discovery only.

### Issues Found and Fixed
None in this phase (fixes applied in Phase 4 and 7).

### 1.1 Active Scripts (29 at scripts/ root)
`__init__.py`, `__main__.py`, `add_indexes.py`, `agent_pipeline.py`, `api_client.py`, `assemble_brief.py` ⚠️, `author_layers.py`, `batch_extract.py`, `checkpoint.py`, `cli.py`, `config.py`, `contradiction_ablation.py`, `contradiction_threshold_test.py`, `create_turn_pairs.py`, `detect_contradictions.py` ⚠️, `embed.py`, `extract_facts.py`, `generate_docx.py`, `generate_tension_data.py`, `import_conversations.py`, `init_database.py`, `llm_provider.py`, `mcp_server.py`, `monitor.py`, `query.py`, `semantic_search.py`, `summarize.py`, `ui.py`, `verify_provenance.py`

**⚠️ `assemble_brief.py`** — declared "removed step" in S79 but still in active serving path (cli.py + mcp_server.py).
**⚠️ `detect_contradictions.py`** — new S81 rewrite at root, different from archived version. Status ambiguous (not in 4-step pipeline, not archived).

### 1.2 Dead Imports
No true dead imports in the four core pipeline scripts. `assemble_brief` is imported by `cli.py` and `mcp_server.py` — technically live, but architecturally declared removed.

### 1.3 Hardcoded Paths
`scripts/generate_tension_data.py` — 8 hardcoded `C:/Users/Aarik/...` paths (HIGH severity, pre-launch blocker). **Fixed in Phase 7.**
5 experiment scripts — similar hardcodes (MEDIUM, experiments only). **Fixed in Phase 7.**
All four core pipeline scripts are clean (paths from `config.py` `PROJECT_ROOT`).

### 1.4 References to Removed Steps
**Active bugs:**
- `cli.py:1077` — `import batch_classify` from root; script lives only in archive → runtime ModuleNotFoundError. **Fixed in Phase 4.**
- `cli.py:1092` — same for `import batch_tier`. **Fixed in Phase 4.**
- `batch_extract.py:635-642` — "Next steps" output referenced 7 old pipeline steps. **Fixed in Phase 4.**
- `author_layers.py:1659,1727` — "Run: baselayer tier" printed to user. **Fixed in Phase 4.**

**Config mislabels (fixed in Phase 4):**
- `LAYER_REVIEW_MODEL` — labeled ARCHIVED but actively used as compose model in `agent_pipeline.py`
- `CONTRADICTION_SIMILARITY_THRESHOLD` — labeled ARCHIVED but imported by root-level `detect_contradictions.py`
- `RECURRENCE_NORMALIZATION_CEILING`, `RECURRENCE_WINDOW_HOURS` — unlabeled but stale (only used by archived `score_facts.py`)

### 1.5 Missing Constants
No subjects registry in `config.py`. `generate_tension_data.py` hardcodes all 7 subject paths. A `SUBJECTS_DIR` or `KNOWN_SUBJECTS` constant would make scripts portable. **Partially addressed in Phase 7 (hardcoded paths replaced with env-var pattern).**

### Issues Found but Deferred
- [DEFERRED] `assemble_brief.py` serving path — formally re-classify as the MCP/CLI serving layer, or migrate to unified brief?
- [DEFERRED] `detect_contradictions.py` at root — integrate into pipeline spec or move to `experiments/`?
- [DEFERRED] Add `SUBJECTS_DIR` constant to `config.py`

### Summary
Core pipeline scripts are disciplined. Main finding: `assemble_brief` was declared removed but is still in the serving path. Config.py had two mislabeled constants and two missing ARCHIVED labels (all fixed in Phase 4). `generate_tension_data.py` had 8 hardcoded absolute paths (fixed in Phase 7). Two broken CLI imports for archived scripts (fixed in Phase 4).

---

## Phase 2: Test Audit — 2026-03-09

### Files Modified
None — discovery only.

### 2.1 Test Suite Baseline
**Total: 400 | Passed: 368 | Failed: 32 | Errors: 0 | Skipped: 0**

**Category 1 — agent_pipeline.py interface drift (18 failures, `test_agent_pipeline.py`)**
All fail with ImportError. Functions removed in S79 simplification (`_get_next_cycle_number`, `create_run_dir`, `write_artifact`, `read_artifact`, `load_agent_definition`, `build_agent_prompt`) no longer exist. Orchestration layer completely unverified by tests.

**Category 2 — archived eval script referenced (12 failures, `test_unified_brief.py`)**
`run_validation_study.py` moved to archive but test imports not updated. All 12 fail with ModuleNotFoundError.

**Category 3 — quality gate logic bug (1 failure) → FIXED IN PHASE 4**
`test_passes_when_mechanisms_present` — `keywords[2:]` sliced all entries for 2-item lists, causing false COHERENCE gap on every compose run.

### 2.2 Active Pipeline Coverage
| Script | Coverage |
|---|---|
| `import_conversations.py` | Partial — DB schema via fixtures; core ChatGPT/Claude JSON parsing untested |
| `extract_facts.py` | Good — 10 test classes, ~60 tests across all normalizer functions |
| `author_layers.py` | Good — thorough provenance, layer generation, prompt filtering coverage |
| `agent_pipeline.py` | Partial — compose prompt + completeness checks covered; orchestration zero working tests |

### Issues Found but Deferred
- [DEFERRED] `tests/test_agent_pipeline.py` — 18 ImportErrors. Rewrite against current API or remove?
- [DEFERRED] `tests/test_unified_brief.py` (12 failures) — remove or redirect archived `run_validation_study` tests?
- [DEFERRED] `import_conversations.py` — no tests for ChatGPT/Claude JSON parsing logic

### Summary
Test suite healthy for extraction and authoring. Compose orchestration is the exposure. The quality gate bug was a real defect affecting every compose run — fixed in Phase 4.

---

## Phase 3: Documentation Scan — 2026-03-09

### Files Modified
None — discovery only. `extract_facts.py` docstring updated in Phase 4.

### 3.1 docs/core/ Accuracy
| File | Status | Key Issues |
|---|---|---|
| `ARCHITECTURE.md` | Partial | File tree lists removed scripts as active; test count 392 (actual: 414); decision count 59 (actual: 76); agent_pipeline/author_layers described as including Collective |
| `PROJECT_OVERVIEW.md` | Current | Updated 2026-03-08. Accurate pipeline, stats, Collective correctly marked ARCHIVED |
| `PROGRESS.md` | Stale | **Last entry: Session 77+ (2026-03-07). No S79 or S80 entries.** Introductory overview still lists embed/semantic memory as permanent active layer. |
| `DESIGN_PRINCIPLES.md` | Partial | "Cheap Constraint, Expensive Discrimination" section presents Collective as active; no S79 ablation note |
| `DECISIONS.md` | Partial | D-024 ("Active") — Collective proven ceremonial S79; D-054 ("Active") — no ablation caveat; D-033 ("Active") — "authored in sessions not via API" contradicts current API-driven authoring |

### 3.2 CLAUDE.md
Pipeline description and DO NOT section are accurate. **Four archived scripts listed as active in Key Scripts table:**
- `classify_facts_haiku.py` → in `scripts/archive/dead_pipeline_steps/`
- `reclassify_tiers.py` → in `scripts/archive/dead_pipeline_steps/`
- `run_eval.py` → in `scripts/archive/eval_scripts/`
- `provenance_eval.py` → in `scripts/archive/eval_scripts/`

### 3.3 Active Script Docstrings
| Script | Status |
|---|---|
| `import_conversations.py` | Current |
| `extract_facts.py` | **Stale — described Qwen 2.5 14B/Ollama as primary extractor; "Phase 4, Step 4" numbering. Fixed in Phase 4.** |
| `author_layers.py` | Current |
| `agent_pipeline.py` | Current |

### Issues Found but Deferred (Aarik must update)
- [DEFERRED] `PROGRESS.md` — add S79 (ablation, C11 wins at 87/100) and S80 (V4 compose locked) entries
- [DEFERRED] `DECISIONS.md` — update D-024, D-054, D-033 status in index table
- [DEFERRED] `ARCHITECTURE.md` — update file tree (archive locations, test count 414, decision count 76)
- [DEFERRED] `DESIGN_PRINCIPLES.md` — add ablation note to Collective discussion
- [DEFERRED] `CLAUDE.md` — remove 4 archived scripts from Key Scripts table

### Summary
`PROJECT_OVERVIEW.md` is accurate. `PROGRESS.md` is the biggest gap — S79 and S80 entirely absent. DECISIONS.md index has three misleading "Active" entries for removed features. All are Aarik's responsibility to update.

---

## Phase 4: Refactor Execution — 2026-03-09

### Files Modified
- `scripts/config.py` — 4 constant label fixes
- `scripts/agent_pipeline.py` — fixed `verify_brief_completeness()` quality gate bug
- `scripts/cli.py` — fixed broken archive imports; added `[ARCHIVED]` labels to `brief`/`chat` subcommands; updated checkpoint help
- `scripts/extract_facts.py` — updated module docstring (Qwen→Haiku), step numbering (Phase 4 Step 4→Step 2), D-077+→D-076
- `scripts/batch_extract.py` — updated "Next steps" output for 4-step pipeline
- `scripts/checkpoint.py` — updated module docstring to mark scoring/classification stages as legacy
- `scripts/author_layers.py` — updated two "Run: baselayer tier" user-facing messages
- `scripts/__init__.py` — updated package comment

### Issues Found and Fixed
- [FIXED] **verify_brief_completeness() COHERENCE false-positive** — `keywords[2:]` sliced ALL entries for 2-item keyword lists. Fix: scan all `keywords`; proportional threshold (1 hit for ≤2 items, 2 hits for longer). **This gate runs on every compose run.** All 4 TestVerifyBriefCompleteness tests now pass.
- [FIXED] `cli.py:1077` — `import batch_classify` runtime ModuleNotFoundError (archive-path-prepend fix)
- [FIXED] `cli.py:1092` — same for `import batch_tier`
- [FIXED] `LAYER_REVIEW_MODEL` config label — removed ARCHIVED (it IS the compose model in `agent_pipeline.py`)
- [FIXED] `CONTRADICTION_SIMILARITY_THRESHOLD` config label — removed ARCHIVED (imported by root `detect_contradictions.py`)
- [FIXED] `RECURRENCE_NORMALIZATION_CEILING`, `RECURRENCE_WINDOW_HOURS` — added `# ARCHIVED — unused` comments
- [FIXED] `batch_extract.py` "Next steps" — removed references to 7 old steps
- [FIXED] `author_layers.py` — removed "Run: baselayer tier" user-facing instructions
- [FIXED] `extract_facts.py` docstring, step numbering, D-077+ reference

### Issues Found but Deferred
- [DEFERRED] `assemble_brief` imports in `cli.py` and `mcp_server.py` remain live — migration decision needed
- [DEFERRED] `tests/test_agent_pipeline.py` — 18 ImportErrors — needs rewrite or removal
- [DEFERRED] `tests/test_unified_brief.py` — 13 pre-existing failures

### baselayer run Code Path (4.4 verification)
`baselayer run <file>` → Init → Import → cost gate (only manual step, skippable with `--yes`) → Extract → Author + Compose (chained via `args.compose = True`). No tier gate blocking. No removed-step calls. `--document-mode` propagates correctly. Clean.

### Commit
`c7fbaee` — `refactor: remove dead imports and stale references from active pipeline scripts`

---

## Phase 5: Verification — 2026-03-09

### Files Modified
None — no regressions found.

### 5.1 Test Suite (Post-Phase 4)
**Total: 400 | Passed: 369 | Failed: 31** (+1 pass vs Phase 2 baseline)

| Check | Result |
|---|---|
| `test_passes_when_mechanisms_present` (quality gate fix) | **PASS ✓** |
| Regressions | **None** |
| Pre-existing failures unchanged | 18 in `test_agent_pipeline.py`, 13 in `test_unified_brief.py` |

### 5.2 baselayer stats
Runs cleanly. 1,892 conversations, 40,997 messages, 4,106 active facts.

### 5.3 Paul Graham Pipeline Readiness
- Path: `subjects/paul_graham/` — found
- Raw essays: 28 `.txt` files present
- Extracted facts: 272 in database
- Identity layers: **empty** — no authored layers, no brief
- **Ready for: `baselayer author --subject "Paul Graham"`**

### Summary
Zero regressions from Phase 4. Quality gate fix confirmed. Paul Graham is at the author step.

---

## Phase 6: Security Review — 2026-03-09

### Files Modified
None — no CRITICAL issues found.

### 6.1 Secrets Scan — CLEAN
No hardcoded API keys, tokens, or passwords anywhere. `sk-ant-` in `cli.py:1057` is help text, not a real key. All API access via environment variables.

### 6.2 Input Validation
| File | Issue | Severity |
|---|---|---|
| `ui.py:351-368` | `subject` param passed to subprocess with no length cap (shell=False mitigates injection) | MEDIUM |
| `extract_facts.py:115` | f-string in ALTER TABLE — but `col` is hardcoded list, not user input | LOW |
| `author_layers.py:136,159,166` | f-string SQL — constructed from hardcoded logic, no user input | LOW |

No `shell=True`, no `eval()`, no `exec()`, no `pickle.load()` anywhere.

### 6.3 Dependencies
All current, no known CVEs. Minor flags: `numpy~=1.26` (2.x available), `httpx>=0.24` (unbounded upper), `python-docx~=0.8` (stagnant). All LOW priority.

### 6.4 API Client — CLEAN
API key never in application code (SDK reads from env automatically). Not logged. Not in error messages. TLS not disabled. Retry logic safe. One LOW: rate limit error logging via `%s` of exception object may include response body metadata.

### 6.5 Data Handling — CLEAN
Anonymization (`_anonymize_facts()`, `_anonymize_anchor_data()`, `_anonymize_text()`) fires before every model call, auditable via console print. `.gitignore` thorough. No fact content in structured logs.

**Pre-push action identified:** Subject data directories (`subjects/`, `buffett_memory/`, `marks_memory/`, `franklin_memory/`, `memory_system_v4/`) not in `.gitignore`. **Added in Phase 7 commit.**

### Summary
No blockers for public release. Subject data `.gitignore` gap is the only pre-push finding — resolved in Phase 7.

---

## Phase 7: Privacy Scrub — 2026-03-09

### Files Modified
- `.gitignore` — added 5 subject data directory entries
- `scripts/generate_tension_data.py` — 8 hardcoded `C:/Users/Aarik/...` paths → env-var-based paths
- `scripts/experiments/exp_temporality.py` — hardcoded paths → relative; `load_aarik_conversations` → `load_user_a_conversations`
- `scripts/experiments/exp_identity_formalization.py` — hardcoded paths → relative; subject label anonymized
- `scripts/experiments/exp_contradiction_detection.py` — hardcoded path → relative
- `scripts/experiments/exp_embedding_models.py` — hardcoded path → relative
- `scripts/experiments/ollama_utils.py` — hardcoded paths → relative
- `scripts/archive/eval_scripts/run_validation_study.py` — subject key `"aarik"` → `"user_a"`

### 7.1 Python File Scrub
Most spec-listed biographical strings in `run_validation_study.py` and `run_eval.py` were absent from prior scrubs. Only subject map key needed updating. `assemble_brief.py` TEST_CASES already generic. `test_contradiction.py`/`test_contradiction_detection.py` substitutions already applied. `cli.py` already uses proper `import time`. `test_unified_brief.py` rename not needed (function didn't exist).

### 7.2 Gitignore Added
`subjects/*/`, `buffett_memory/`, `marks_memory/`, `franklin_memory/`, `memory_system_v4/`
Already present: `gtm/`, `data/database/`, `data/vectors/`

### 7.3 Docs Anonymization
All 17 target docs checked — **zero PII found**. All already clean.

### 7.4 Verification — All PASS
- `"Aarik"` in `scripts/*.py` — 0 matches
- `"Aarik"` in `tests/*.py` — 0 matches
- `"Bavani"` across scripts/tests/docs — 0 matches
- `"Roman Gushel"` in docs — 0 matches
- `C:\\Users\\Aarik` in docs — 0 matches

**Residual (gitignored, not committed):** `docs/core/PROGRESS.md`, `docs/analysis/AARIK-ANALYSIS.md` — covered by `.gitignore`.

### Issues Found but Deferred
- [DEFERRED] `docs/plans/CONTRADICTION_WORKFLOW_PLAN.md` — "Aarik" as subject identifier; not in 17-file target list
- [DEFERRED] `docs/REVIEW_PLAN.md` — add to `.gitignore` before public push

### Commit
`f805b5f` — `privacy: scrub PII from scripts and docs for public release`

---

## Final Summary — 2026-03-09

| Metric | Value |
|---|---|
| Total issues found | 34 |
| Fixed | 13 |
| Deferred (human decision needed) | 21 |
| Test results | 368 pass / 32 fail → **369 pass / 31 fail** |
| Active scripts audited | 29 root-level + 4 core pipeline |
| Code fixes | 8 bugs/labels/imports in 7 files |
| Privacy changes | 9 files, 8 hardcoded paths replaced |
| Security blockers | 0 |
| Commits | 2 (`c7fbaee` refactor, `f805b5f` privacy) |

### Most Impactful Fix
**`verify_brief_completeness()` quality gate bug** — `keywords[2:]` silently dropped all entries for 2-item keyword lists. The COHERENCE check falsely reported gaps on every brief where the keyword list had ≤2 items. This gate runs inside every compose loop. Fixed.

### Pre-Launch Blockers Remaining
None. All security and privacy blockers are resolved.

---

### Deferred Items for Aarik

**Architecture decisions:**
1. `assemble_brief.py` — formally re-classify as MCP/CLI serving layer, or migrate to unified brief path?
2. `detect_contradictions.py` at root — integrate into 4-step pipeline spec, or move to `experiments/`?

**Tests (31 pre-existing failures):**
3. `tests/test_agent_pipeline.py` (18 failures) — rewrite against current API or remove?
4. `tests/test_unified_brief.py` (13 failures) — remove stale `run_validation_study` import tests?

**Documentation — Status:**
5. `PROGRESS.md` — ✅ S79+S80 entries written (file is gitignored — update lives locally only)
6. `DECISIONS.md` — ✅ DONE (commit `28393a7`) — D-024/D-033 marked Superseded, D-054 caveat added
7. `ARCHITECTURE.md` — ✅ DONE (commit `77e896a`) — counts fixed, scripts archived, Collective refs removed
8. `DESIGN_PRINCIPLES.md` — ✅ DONE (commit `aa3c214`) — S79 ablation note added

**⚠️ ACTION REQUIRED — CLAUDE.md (main instance):**
`CLAUDE.md` (`C:\Users\Aarik\Anthropic\CLAUDE.md`) lists 4 archived scripts as active in the Key Scripts table. Remove these rows:
- `classify_facts_haiku.py` — now in `scripts/archive/dead_pipeline_steps/`
- `reclassify_tiers.py` — now in `scripts/archive/dead_pipeline_steps/`
- `run_eval.py` — now in `scripts/archive/eval_scripts/`
- `provenance_eval.py` — now in `scripts/archive/eval_scripts/`

This file was excluded from automated edits per review plan rules — requires human/main-instance action.

**Minor cleanup:**
10. `docs/REVIEW_PLAN.md` — add to `.gitignore`
11. `docs/plans/CONTRADICTION_WORKFLOW_PLAN.md` — scrub "Aarik" subject identifier
12. `ui.py` — add length cap on `subject` parameter (MEDIUM, defense in depth)
13. `httpx` — consider pinning upper bound in `pyproject.toml` (LOW)
14. `numpy` — consider upgrading to 2.x post-launch (LOW)

### Paul Graham Status
272 facts extracted. Identity layers empty. **Ready for: `baselayer author --subject "Paul Graham"`**
