# Code Review + Refactor + Documentation Scan Plan

**Target audience:** Sonnet agent running autonomously in Claude Code.
**Estimated total time:** ~3 hours across 5 phases.
**Commit after each phase.**

---

## Context

- **Project:** Base Layer — personal AI memory system that extracts facts from conversation history, builds a compressed behavioral model, and injects it into AI conversations.
- **Project root:** `C:\Users\Aarik\Anthropic\memory_system\`
- **Pipeline:** 4 steps (Import → Extract → Author → Compose), simplified from 14 in S79. Ablation proved 10 of 14 steps were ceremonial.
- **Stats:** 47 predicates, 414 tests, 76 decisions (D-001 to D-076), 25 CLI subcommands, 16 DB tables.
- **Active scripts:** `scripts/` directory. Archived/dead code in `scripts/archive/`.
- **Key config:** `scripts/config.py` (single source of truth for constants).
- **CLI entry:** `scripts/cli.py` — `baselayer` command with 25 subcommands including `run`.
- **Test suite:** `tests/` directory, run with `python -m pytest tests/ -v` from project root.

### Active Pipeline Scripts (do NOT modify prompts in these without explicit approval)
| Script | Step |
|---|---|
| `scripts/import_conversations.py` | Step 1: Import |
| `scripts/extract_facts.py` | Step 2: Extract |
| `scripts/author_layers.py` | Step 3: Author Layers |
| `scripts/agent_pipeline.py` | Step 4: Compose |

### Supporting Active Scripts
| Script | Purpose |
|---|---|
| `scripts/cli.py` | CLI entry point |
| `scripts/config.py` | Shared constants |
| `scripts/mcp_server.py` | MCP server for serving briefs |
| `scripts/api_client.py` | Centralized API singleton + retry |
| `scripts/run_eval.py` | Eval runner |
| `scripts/run_validation_study.py` | Validation study runner |
| `scripts/verify_provenance.py` | Vector provenance + claim verification |
| `scripts/provenance_eval.py` | Mechanical provenance evaluation |

### Removed Pipeline Steps (should NOT be referenced in active code paths)
These steps were proven ceremonial by S79 ablation and removed from the active pipeline:
- **Embed** (vector embedding of facts)
- **Score** / `score_facts.py`
- **Classify** / `classify_facts_haiku.py`
- **Tier** / `reclassify_tiers.py`
- **Contradictions** detection
- **Consolidate** facts
- **Anchors extraction** (separate from author anchors layer)
- **Collective review** (removed from author step)
- **Assemble** / `assemble_brief.py`

---

## Phase 1: Code Inventory (~30 min)

### 1.1 Map Active vs Archived Scripts
- List all `.py` files in `scripts/` (non-recursively) — these are active.
- List all `.py` files in `scripts/archive/` — these are archived.
- Confirm every archived script has been moved out of `scripts/` root. Flag any that exist in both locations.

### 1.2 Dead Imports in Active Code
For each active script in `scripts/` (root level only), check for imports referencing:
- `score_facts` or `score`-related modules
- `classify_facts_haiku` or classification modules
- `reclassify_tiers` or tiering modules
- `assemble_brief` or assembly modules
- Any module that lives in `scripts/archive/`
- Any function/class that no longer exists in its source module

Record every dead import with file path and line number.

### 1.3 Hardcoded Paths
Search all active scripts for hardcoded paths (strings containing `C:\Users`, `C:/Users`, or absolute paths not sourced from `config.py`). Acceptable exceptions:
- Test fixtures
- CLI `--help` examples
- Comments/docstrings referencing documentation

Flag all others — these should come from `config.py` or be relative to project root.

### 1.4 References to Removed Steps
Search active scripts for string references to removed pipeline concepts:
- `score`, `scoring`, `score_facts`
- `classify`, `classification`, `classify_facts`
- `tier`, `tiering`, `reclassify`
- `contradict`, `contradiction`
- `consolidat` (catches consolidate/consolidation)
- `collective_review`, `collective review`
- `assemble_brief`, `assemble`

Distinguish between:
- **Active references** (code that calls or depends on these) — these are bugs, flag for removal.
- **Passive references** (comments, docstrings, decision references like D-030) — note but do not flag as bugs.
- **Config references** — check Phase 1.5.

### 1.5 Stale Constants in config.py
Read `scripts/config.py` in full. Identify:
- Constants marked as archived/deprecated but still imported by active code.
- Constants related to removed steps (scoring weights, tier thresholds, classification categories) that are no longer used anywhere.
- Constants that should exist but are missing (check what the 4 active pipeline scripts actually reference).

---

## Phase 2: Test Audit (~30 min)

### 2.1 Run Full Test Suite
```bash
cd C:\Users\Aarik\Anthropic\memory_system && python -m pytest tests/ -v 2>&1
```
Record: total tests, passed, failed, errors, skipped. If any fail, note which and why — do NOT fix test failures in this phase, only inventory them.

### 2.2 Identify Tests for Archived Code
Find test files or test functions that test:
- `score_facts.py` or scoring logic
- `classify_facts_haiku.py` or classification logic
- `reclassify_tiers.py` or tiering logic
- `assemble_brief.py` or assembly logic
- Contradiction detection
- Consolidation
- Collective review
- Any other removed pipeline step

These tests may still pass (if the archived code still exists) but they test dead code paths. List them.

### 2.3 Coverage on Active Pipeline
For each of the 4 active pipeline scripts, check whether dedicated tests exist:
- `import_conversations.py` — look for `test_import*` or `test_conversation*`
- `extract_facts.py` — look for `test_extract*`
- `author_layers.py` — look for `test_author*`
- `agent_pipeline.py` — look for `test_agent*` or `test_pipeline*` or `test_compose*`

Note any active pipeline script with zero or minimal test coverage.

### 2.4 Tests Referencing Removed Features
Search test files for imports or assertions referencing removed features (same terms as Phase 1.4). These tests may need updating even if they pass.

---

## Phase 3: Documentation Scan (~20 min)

### 3.1 Audit docs/ for Accuracy
Read each file in `docs/core/` and check:
- Does `ARCHITECTURE.md` describe the current 4-step pipeline or the old 14-step?
- Does `PROJECT_OVERVIEW.md` match current state?
- Does `PROGRESS.md` have an entry for S79 (ablation) and S80 (V4 compose)?
- Are any docs referencing steps/features that no longer exist as if they are current?

Do NOT read every doc exhaustively — scan headers and key sections for stale references.

### 3.2 Check CLAUDE.md
Read `C:\Users\Aarik\Anthropic\CLAUDE.md`. Verify:
- Pipeline description matches current 4-step reality.
- Script table is accurate (no removed scripts listed as active).
- "DO NOT" section is current.
- Session number and state description are current.

Flag inaccuracies but do NOT modify CLAUDE.md — that is Aarik's responsibility.

### 3.3 Docstrings in Active Scripts
For each active pipeline script, check the module-level docstring and key function docstrings:
- Do they describe the current behavior?
- Do they reference removed steps or features?
- Are parameter descriptions accurate?

### 3.4 Decision References
Search active code for `D-0` pattern (decision references like D-030, D-041, etc.). For each reference found, verify:
- The referenced decision is still accurate per current pipeline.
- The code implementing the decision still matches the decision's intent.
- Flag any decision references that are outdated.

---

## Phase 4: Refactor Execution (~1-2 hours)

**IMPORTANT:** This phase makes code changes. Follow rules strictly.

### 4.1 Remove Dead Imports
Using findings from Phase 1.2, remove all dead imports from active scripts. For each removal:
- Verify the import is truly unused (grep for the imported name in the file).
- Remove the import line.
- Record the change.

### 4.2 Clean Up config.py
Using findings from Phase 1.5:
- Add clear section headers: `# === ACTIVE PIPELINE CONSTANTS ===` and `# === ARCHIVED (unused, kept for reference) ===`
- Move archived constants to the archived section if not already separated.
- Do NOT delete constants — just reorganize and label.

### 4.3 Update CLI Help Text
Read `scripts/cli.py`. Check each subcommand's help text:
- Remove or update references to removed pipeline steps.
- Ensure `baselayer run` help text describes the current 4-step flow.
- Ensure subcommands for removed steps are clearly marked as archived/deprecated if they still exist.

### 4.4 Verify `baselayer run` End-to-End
This is a read-only verification — trace the code path of `baselayer run` in `cli.py`:
- Does it call the 4 steps in order?
- Are there any gates or manual intervention points that would block autonomous execution?
- Does it handle errors and provide clear output?
- Note: the author_layers.py tier gate was previously blocking — verify it is fixed.

Do NOT actually run the pipeline (it costs API money). Just trace the code.

### 4.5 Clean Up Removed Feature References
Using findings from Phase 1.4, for active code references to removed steps:
- If the reference is in a code path (function call, conditional, variable), remove or update it.
- If the reference is in a comment explaining history, leave it.
- If uncertain, leave it and flag for human decision.

### 4.6 Commit
Stage and commit all Phase 4 changes with message: `refactor: remove dead imports and stale references from active pipeline scripts`

---

## Phase 5: Verification (~15 min)

### 5.1 Re-run Test Suite
```bash
cd C:\Users\Aarik\Anthropic\memory_system && python -m pytest tests/ -v 2>&1
```
Compare results to Phase 2.1. No test that previously passed should now fail. If any new failures, revert the causing change and flag it.

### 5.2 Run `baselayer stats`
```bash
cd C:\Users\Aarik\Anthropic\memory_system && python scripts/cli.py stats
```
Verify it runs without errors and outputs sensible data.

### 5.3 Verify Paul Graham Pipeline Readiness
Check that Paul Graham data exists and is ready for author + compose:
- Check `subjects/paul_graham/` or equivalent path for extracted facts.
- Do NOT run the pipeline — just confirm the data is in place and the path is configured.

### 5.4 Final Commit
If any verification-phase fixes were needed, commit them separately: `fix: resolve issues found during review verification`

---

## Phase 6: Security Review (~20 min)

### 6.1 Secrets Scan
Search all active scripts and config files for:
- Hardcoded API keys, tokens, or secrets (patterns: `sk-ant-`, `sk-`, `api_key`, `token`, `secret`)
- Credentials in environment variable defaults that contain actual values
- Database connection strings with passwords
- Any file that looks like it contains credentials (`.env`, `credentials.*`, `*.key`)

### 6.2 Input Validation
For each script that accepts user input (CLI args, file paths, API responses):
- Check for command injection via `subprocess` or `os.system` calls with user-controlled strings
- Check for path traversal (user-provided file paths not validated)
- Check for SQL injection (string interpolation in SQL queries vs parameterized queries)
- Check for unsafe deserialization (`pickle.load`, `eval`, `exec` on user data)

### 6.3 Dependency Audit
- List all direct dependencies from `pyproject.toml` or `requirements.txt`
- Flag any that are: pinned to very old versions, known-vulnerable, or unnecessary
- Check for unused imports of external packages

### 6.4 API Client Security
Read `scripts/api_client.py` and check:
- API key handling (loaded from env, never logged, never in error messages)
- Request/response logging (does it log sensitive content?)
- Retry logic (does it leak info on failure?)
- TLS/SSL verification (not disabled)

### 6.5 Data Handling
- Check that user conversation data is never logged in cleartext
- Check that the anonymization layer in `author_layers.py` actually works (subject names → "this person")
- Check that database files are in `.gitignore`
- Check that ChromaDB vector data is in `.gitignore`

Record all findings. Flag severity: CRITICAL (must fix before push), HIGH (should fix), MEDIUM (nice to fix), LOW (informational).

---

## Phase 7: Privacy Scrub (~30 min)

**Reference:** `GIT_PUSH_PREP.md` in project root — full spec with line numbers.

### 7.1 Python File Scrub
Apply all changes from GIT_PUSH_PREP.md Stream 1, sections 1c through 1j:

**`scripts/run_validation_study.py`** (1c): Generalize all biographical specifics in eval prompts:
- "CRO roles at Series B companies" → "leadership roles at growth-stage companies"
- "My partner wants to move... gym, trading setup" → "My partner wants to relocate... home office, workout space"
- "31-year-old day trader who talks to AI about his feelings" → "a person who uses AI for both professional analysis and personal reflection"
- "tweaked my back deadlifting" → "tweaked my back exercising"
- "pathological about building a system so AI understands you" → "deeply invested in building a system for AI personalization"
- "keep trading and building Base Layer, take a CRO role... find a cofounder" → "keep my current projects, take a leadership role at another company, or find a cofounder"
- "AI memory system, content business, trading, family time" → "a tech project, a content business, a side pursuit, family time"

**`scripts/run_eval.py`** (1c): Same pattern — generalize all biographical specifics.

**`scripts/assemble_brief.py`** (1d): Replace TEST_CASES with generic examples.

**`scripts/archive/_check_status.py`** (1e): Replace personal correction terms or delete the file (it's archived).

**`scripts/test_contradiction.py`** (1f): "Jordan has eczema-related dry skin" → "Jordan has chronic back pain"

**`scripts/test_contradiction_detection.py`** (1f): "Alex founded TechCo, which was accepted into Techstars" → "Alex founded TechCo, which was accepted into an accelerator"

**`scripts/cli.py`** (1j): Replace `__import__('time').time()` with proper import.

**`tests/test_unified_brief.py`** (1i): Rename `test_prompt_no_aarik_specific_pattern_names` → `test_prompt_no_user_specific_pattern_names`

### 7.2 Gitignore Updates
Add to `.gitignore`:
```
gtm/
data/database/
data/vectors/
```
Verify `gtm/` directory is not tracked. Verify database and vector files are not tracked.

### 7.3 Docs Anonymization
For ALL docs listed in GIT_PUSH_PREP.md section 1h:
- Replace "Aarik" → "the developer" or "User A"
- Replace "Bavani" → "User C" or "Subject B"
- Replace "Roman Gushel" → "User B"
- Remove all `C:\Users\Aarik\` paths (replace with relative paths or `<project_root>/`)
- Replace "agulaya24/baselayer" → just "baselayer"

Files to scrub (from GIT_PUSH_PREP.md):
- `docs/core/PROJECT_OVERVIEW.md`
- `docs/core/DECISIONS.md`
- `docs/core/ARCHITECTURE.md`
- `docs/eval/BCB_FRAMEWORK.md`
- `docs/eval/EVAL_FRAMEWORK.md`
- `docs/eval/TRUE_BLIND_EVAL_FRAMEWORK.md`
- `docs/eval/CROSS_PROVIDER_IDENTITY_EVAL.md`
- `docs/reviews/CONTAMINATION_REVIEW.md`
- `docs/reviews/README_REVIEW_S57.md`
- `docs/reviews/SECURITY_CODE_AUDIT_S55.md`
- `docs/plans/MULTI_PROVIDER_PLAN.md`
- `docs/plans/WEB_SERVICE_SECURITY_THREAT_MODEL.md`
- `docs/plans/PROVENANCE_TRACE_ARCHITECTURE.md`
- `docs/plans/PIPELINE_UPGRADES_POST_FRANKLIN.md`
- `docs/plans/EXTRACTION_CAP_SCALING_REVIEW.md`
- `docs/plans/TEMPORAL_RECURRENCE_DEDUP_PLAN.md`
- `docs/research/VOICE_RESEARCH.md`

### 7.4 Verification
After all scrubs:
```bash
grep -r "Aarik" --include="*.py" scripts/ tests/    # should return 0
grep -r "Bavani" --include="*.py" --include="*.md" .  # should return 0
grep -r "C:\\\\Users\\\\Aarik" --include="*.md" docs/  # should return 0
```

### 7.5 Commit
Stage and commit: `privacy: scrub PII from scripts and docs for public release`

---

## Rules — Read Before Starting

1. **Do NOT modify prompts** in `author_layers.py` or `agent_pipeline.py` without explicit approval from Aarik. These are locked (V4 compose prompt, S80).
2. **Do NOT modify the scoring algorithm** without re-running scores on all subjects.
3. **Do NOT re-extract facts** without clearing both SQLite AND ChromaDB.
4. **Do NOT delete files.** If a file appears dead, move it to `scripts/archive/` (for scripts) or `docs/archive/` (for docs).
5. **Do NOT modify CLAUDE.md or MEMORY.md.** Flag inaccuracies for Aarik.
6. **Commit at the end of each phase.** Use descriptive commit messages prefixed with the phase.
7. **When uncertain, defer.** Add the item to the "deferred" section of REVIEW_RESULTS.md for human decision.
8. **Do NOT run API-calling pipeline steps.** They cost money. Code tracing and test runs only.

---

## Output

After each phase, append results to `docs/REVIEW_RESULTS.md` in this format:

```markdown
## Phase N: [Name] — [Date]

### Files Modified
- `path/to/file.py` — description of change

### Issues Found and Fixed
- [FIXED] Description of issue and fix applied

### Issues Found but Deferred
- [DEFERRED] Description — reason it needs human decision

### Summary
Brief paragraph on overall findings.
```

When all 5 phases are complete, add a final summary section:

```markdown
## Final Summary
- Total issues found: X
- Fixed: Y
- Deferred: Z
- Test results: before (P pass / F fail) → after (P pass / F fail)
- Active scripts audited: N
- Archived references cleaned: N
```
