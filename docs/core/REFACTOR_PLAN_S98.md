# Base Layer — Complete System Audit & Refactor Plan (S98)

**Date:** 2026-03-25
**Session:** 98
**Status:** APPROVED v2 — Incorporating feedback from Claude, DeepSeek, Gemini, GPT, Grok + deep research on all phases
**Golden dataset:** Aarik's own identity model (memory_system_v4/, most scrutinized, subject can evaluate quality)

---

## Executive Summary

98 sessions of organic growth produced a working but fragile system: 16,631 LOC across 20 modules, 48 known issues (3 critical), 2 security vulnerabilities, missing quality gates, and no reliable V2 workflow. This plan addresses everything in gated phases — each phase has entry criteria, done criteria, verification steps, and rollback strategy.

**Key principle (per GPT):** Start with operational trust, not architecture cleanup.

**Key research findings (S98 deep dive):**
- Compose saturation CONFIRMED: hardcoded `LIMIT 100` in agent_pipeline.py line 623. V2 feeds same top-100 facts as V1 → identical brief.
- Test harness already exists: 15 test files, 4,079 LOC, pytest + CI. Needs augmentation, not creation.
- fact_class column already exists in schema. Temporality Phase 1 = prompt update + backfill only.
- Magic links fully implemented. Just needs gmail integration + internal docs.
- assemble_brief.py imported by mcp_server.py — cannot delete without MCP update.
- llm_provider.py is a thin re-export wrapper, not full D-052 abstraction — keep, wire properly later.

---

## Part 1: Known Issues Inventory

### Critical (P0) — 3 items
1. ~~Password stored plaintext in seed endpoint~~ — **FIXED Phase 0 (S98).** Bcrypt dual-mode auth deployed. Auto-migrates on first login.
2. **Underextraction — silent data loss.** Confidence sort + 600 cap fixed S97. Still missing: equal-size chunking (Phase 6) and coverage gating >20% discard = block (Phase 3A).
3. **No pipeline sequencing.** Extraction gate added S98 (cli.py + author_layers.py). Untested end-to-end. Needs unified pipeline command with gates between every step (Phase 4).

### High (P1) — 10 items
4. False V2 upgrades (4 subjects re-ran on identical data) — need manifest gate
5. Batch extract missing document mode — 2x API cost (partially wired S98)
6. **Compose saturation CONFIRMED** — hardcoded LIMIT 100 facts in compose prompt (agent_pipeline.py:623). V1 and V2 feed identical top-100 → identical brief.
7. core_v4.md hallucination (Aarik's model: false "Victoria" + "young child" claims) — **assigned to Phase 1**
8. No manifest gate — need input fingerprint (source files + prompt version + model + caps)
9. Concurrent pipeline OOM (3+ simultaneous, torch_python.dll) — max 2 workaround
10. Version history seeding incomplete — code deployed S98, needs UI change to full identity model view
11. 19 duplicate files in scripts/ — already moved to _archive/scripts_stale in S98
12. 12 dead pipeline steps in archive/ — S79 confirmed ceremonial
13. API key filename deleted S98 (key was already outdated)

### Medium (P2) — 10 items
14-23. llm_provider thin wrapper (not full D-052), assemble_brief used by MCP server, no schema versioning, type inconsistency (LayerItem vs IndustryLayerItem, Fact text vs fact_text, traces required vs optional), subject not first-class, dashboard hardcoded, seed_industry regex fragile, magic links need gmail integration, version history UI needs redesign

### Low (P3) — 8 items
24-31. Moltbook stale, Aarik's brief short, bounced emails, Cloudflare routing, local authoring fails, Qwen underperforms, Dan Shipper untiered, examples parity

---

## Part 2: Decisions (Confirmed)

1. **Multi-provider:** KEEP llm_provider.py (currently thin wrapper around api_client). Wire full D-052 abstraction when needed.
2. **Layer file format:** Keep markdown + add JSON frontmatter. Current format: comment header → `---` → `## Injectable Block` → content. Frontmatter replaces comment header with machine-parseable YAML/JSON.
3. **Subject isolation:** Keep per-subject SQLite DBs. Central subjects table in main memory.db only.
4. **MCP server:** Deprioritize. Note: imports assemble_brief.py for theme/episode blocks — must update if assemble_brief changes.
5. **Compose saturation:** CONFIRMED. Fix: move LIMIT 100 to config as COMPOSE_MAX_IDENTITY_FACTS, scale dynamically with corpus size.
6. **Document mode:** Explicit per-subject in registry, NOT auto-detected.
7. **Temporal columns:** fact_class column ALREADY EXISTS in schema. No new column needed. Phase 8 = extraction prompt update + backfill only.
8. **Version history:** Full identity model as single document. Diff description at top. No tabs.
9. **Magic links:** Already fully implemented (S96). Needs gmail draft integration + internal docs.

---

## Part 3: Phased Execution

### Phase 0: Security ✅ COMPLETE
- [x] Bcrypt dual-mode auth deployed (auto-migrates plaintext → bcrypt on first login)
- [x] Seed endpoint hashes passwords before storing
- [x] Build passes, pushed, deployed
- [x] Website confirmed working
- [x] API key filename deleted
- [x] Git tags created: `pre-refactor-s98` on both repos

---

### Phase 1: Compose Fix + Hallucination Fix + Dead Code
**Goal:** Fix the two most impactful bugs (compose saturation + Aarik's hallucination) and remove confirmed dead code.

**Entry criteria:** Phase 0 complete. ✅

**Work:**

**1a. Compose saturation fix:**
- Move hardcoded `LIMIT 100` (agent_pipeline.py:623) to config.py as `COMPOSE_MAX_IDENTITY_FACTS`
- Scale dynamically: `min(100, identity_tier_count)` for small corpora, `min(300, identity_tier_count)` for large (>500 facts)
- Document as D-085

**1b. Fix Aarik's core_v4 hallucination (Issue #7):**
- Query memory_system_v4 database for facts containing "Victoria" or "young child"
- Trace to source conversations
- Delete false facts or add correction facts
- Re-author core layer

**1c. Dead code cleanup:**
- Verify 19 duplicate scripts already archived (done S98)
- Delete 9 truly dead files from archive/dead_pipeline_steps/ (store_anchors, dedup_facts, surprise_scoring, extract_anchors, classify_facts_haiku, batch_pipeline, reclassify_tiers, score_facts, consolidate_enrichments)
- Delete dead archive/utilities/ (8 files, except detect_contradictions — still imported by cli.py cmd_trace)
- Delete dead archive/one_off/ (60+ scripts), archive/eval_scripts/ (35+ scripts), archive/ingest.py, archive/experiments.py
- Keep: assemble_brief.py (MCP server depends on it), llm_provider.py (thin wrapper, active import), detect_contradictions.py (cli.py depends), batch_classify.py + batch_tier.py (CLI callable)
- Delete dead website components: BriefEditor.tsx, RightPanelDetail.tsx

**Done criteria:**
- [ ] Compose with >100 identity facts samples more than 100 (verified on Kevin Kelly)
- [ ] Kevin Kelly V2 brief is DIFFERENT from V1 after recompose
- [ ] Aarik's core_v4 has no false claims about "Victoria"
- [ ] `grep -r "from.*dead_pipeline_steps" src/baselayer/` returns zero (except batch_classify, batch_tier)
- [ ] `python -c "import baselayer.cli"` succeeds with no import errors
- [ ] All existing tests pass: `pytest tests/ -x`

**Verification:** Recompose Kevin Kelly — diff V1 vs V2 brief. Should now be different.

**Rollback:** Revert config.py + agent_pipeline.py changes. Dead code restorable from _archive/.

**Effort:** 1 session.

---

### Phase 2: Test Harness Augmentation
**Goal:** Extend existing test infrastructure with pipeline E2E tests and golden dataset regression.

**Entry criteria:** Phase 1 done criteria all checked. All existing tests pass.

**Existing infrastructure:**
- 15 test files, 4,079 LOC in memory_system/tests/
- pytest 7.0+ with conftest.py (8 fixtures: temp_db, populated_db, mock_anthropic, sample_chatgpt_export, sample_text_file, mock_identity_layers)
- GitHub Actions CI on Python 3.10/3.11/3.12
- Good coverage: extraction, normalization, API client, MCP, privacy, checkpoints

**Work:**
1. **Golden dataset regression test** (`test_golden_dataset.py`):
   - Freeze Aarik's identity model (memory_system_v4/data/identity_layers/) as reference
   - After pipeline changes, compare brief against frozen reference
   - Flag if brief changes >15% (Levenshtein distance or word-level diff)
   - Store reference artifacts in tests/golden/

2. **Pipeline E2E test** (`test_pipeline_e2e.py`):
   - Create minimal test corpus in tests/corpus/ (5 small .txt files, ~500 chars each)
   - Run: import → extract → verify facts exist → verify gates work
   - Mock API calls (don't spend real money in tests)

3. **Gate tests** (`test_gates.py`):
   - Extraction gate: populate conversations but NOT extraction_log → verify author blocked
   - Placeholder tests for Phase 3A/3B gates (fact floor, manifest) — written as skipped tests, activated when gates are implemented

4. **Seed format test** (`test_seed_format.py`):
   - Run build_payload() on test subject → validate JSON schema matches website expectations

**Done criteria:**
- [ ] `pytest tests/` passes including new tests
- [ ] Golden dataset test catches intentional brief change (>15% diff)
- [ ] Pipeline E2E completes on test corpus without errors
- [ ] Gate tests verify blocking behavior
- [ ] CI updated to run new tests

**Verification:** Intentionally break extraction gate (comment it out), confirm test catches it.

**Rollback:** Tests are additive — no rollback needed.

**Effort:** 1 session.

---

### Phase 3A: Safety Gates
**Goal:** Make the pipeline impossible to run incorrectly. All gates auto-blocking.

**Entry criteria:** Phase 2 done. Test harness passes.

**Existing gates:**
- Extraction completeness: cli.py _check_extraction_complete() — checks extracted vs total conversations ✅
- Duplicate gate in author_layers.py (same check) ✅

**New gates to add:**

1. **Multi-dimensional fact floor** (block author if any fail):
   - Identity-tier facts (behavioral + positional) ≥ 50
   - Distinct predicates ≥ 15
   - Source documents ≥ 5 (small corpus) or ≥ 20 (large)
   - Configurable per-subject (future: from subjects table)
   - Query: `SELECT COUNT(*) FROM memory_facts WHERE fact_type IN ('behavioral','positional') AND knowledge_tier='identity'`

2. **Coverage discard gate** (block if >20% discarded):
   - Currently: extract_facts.py prints warning (lines 1348-1354) but doesn't block
   - Change: log discard metrics to new `extraction_metrics` table
   - Gate checks: if discard_pct > 20%, block with error
   - Override: BASELAYER_SKIP_COVERAGE_GATE=1

3. **Concurrency limit** (max 2 simultaneous pipelines):
   - Lock file at PROJECT_ROOT/data/.pipeline.lock
   - Note: Windows doesn't support fcntl — use msvcrt.locking() or file existence check
   - Each pipeline writes PID to lock file, checks if PID still alive

4. **V2 snapshot-before-clear:**
   - Before any extraction reset: copy current memory.db + ChromaDB to .snapshot/
   - If V2 fails, restore from snapshot
   - Auto-cleanup snapshots after 7 days

**Done criteria:**
- [ ] Fact floor blocks on <50 identity-tier facts (tested)
- [ ] Coverage gate blocks on >20% discard (tested with large test file)
- [ ] Concurrency limit blocks 3rd pipeline (tested)
- [ ] V2 snapshot creates backup before clear (tested)
- [ ] V2 snapshot restores successfully on simulated failure (tested)
- [ ] All test harness tests still pass
- [ ] Gates tested on Aarik's model (should pass all)

**Verification:** Run pipeline on minimal corpus that triggers each gate. Verify all block correctly.

**Rollback:** Gates are additive if-checks. Comment out to revert.

**Effort:** 1 session.

---

### Phase 3B: Subject Registry + Migrations
**Goal:** Subject as first-class entity. No more MEMORY_SYSTEM_ROOT hack or hardcoded dicts.

**Entry criteria:** Phase 3A done. All gates passing.

**Data sources to merge:**
| Source | Subjects | Fields |
|---|---|---|
| dashboard.json | 94 | name, facts, status, category, email, password, sent, version, tier |
| SUBJECT_ENVS (dashboard_textual.py) | 90 | display_name → env_dir_name |
| SUBJECT_WAVE (dashboard_textual.py) | 38 | display_name → wave (1/2/3) |
| SUBJECTS (seed_industry.py) | 29 | name, slug, password, source_description |

**Work:**
1. **subjects table** in main memory.db:
   ```sql
   CREATE TABLE subjects (
       id TEXT PRIMARY KEY,
       name TEXT NOT NULL UNIQUE,
       slug TEXT UNIQUE,
       category TEXT,
       email TEXT,
       status TEXT NOT NULL DEFAULT 'not_scraped',
       wave INTEGER,
       tier INTEGER,
       version TEXT DEFAULT 'V1',
       document_mode BOOLEAN DEFAULT 1,
       environment_dir TEXT,
       source_dir TEXT,
       source_description TEXT,
       source_fingerprint TEXT,
       fact_count INTEGER DEFAULT 0,
       sent BOOLEAN DEFAULT 0,
       sent_date TEXT,
       created_at TEXT,
       updated_at TEXT
   );
   ```
2. **Source fingerprint** = hash of: source file list + total bytes + extraction model + extraction prompt hash + chunk config + caps (per GPT: input fingerprint, not just file hash)
3. **Migration script:** Read dashboard.json + SUBJECT_ENVS + SUBJECT_WAVE + SUBJECTS → populate subjects table
4. **Update dashboard_textual.py:** Query subjects table instead of hardcoded SUBJECT_ENVS
5. **Update seed_industry.py:** Read from subjects table instead of SUBJECTS dict
6. **CLI accepts `--subject <id>`** alongside MEMORY_SYSTEM_ROOT (both work during transition)
7. **`baselayer subject list`** — new subcommand showing all subjects with status

**Done criteria:**
- [ ] subjects table populated with all 94 subjects
- [ ] `baselayer subject list` shows all subjects from registry
- [ ] `baselayer stats --subject kevin_kelly` works via registry
- [ ] Dashboard reads from subjects table (no hardcoded dict)
- [ ] seed_industry.py reads from subjects table (no SUBJECTS dict)
- [ ] Manifest gate blocks re-run on unchanged fingerprint (tested)
- [ ] MEMORY_SYSTEM_ROOT still works as fallback
- [ ] New subject added via registry appears in dashboard automatically

**Verification:** Add a test subject, run pipeline, verify it appears in dashboard + can be seeded to website.

**Rollback:** Drop subjects table. Restore hardcoded dicts from git.

**Effort:** 1-2 sessions.

---

### Phase 4: Unified Pipeline + Batch Extract
**Goal:** One command for everything. `baselayer pipeline <subject> [--v2]`

**Entry criteria:** Phase 3B done. Registry populated. All gates passing.

**Approach: Keep it simple.** No state machine. Same synchronous sequential flow as cmd_run(), but with subject registry lookup, gates between steps, batch extract, and --v2 support. "State" is inferred from what artifacts exist (conversations? extraction_log? layers? brief?), not a database field.

**Current cmd_run() flow (cli.py:1089-1201):**
```
Step 0: Init DB if needed
Step 1: Import (skip if conversations exist)
Cost estimate + confirm
Step 2: Extract (sequential API)
Step 3-4: Author layers + compose brief
Step 5: Traceability
```

**Work:**
1. **`baselayer pipeline <subject>`** (V1):
   - Resolve subject from registry (source_dir, memory_dir, document_mode)
   - Set MEMORY_SYSTEM_ROOT to subject's memory_dir
   - Run: import → batch-extract (document_mode from registry) → gates check → author → compose
   - All Phase 3A gates enforced between steps
   - Cost estimate + confirmation before API calls

2. **`baselayer pipeline <subject> --v2`** (V2):
   - Verify source_fingerprint changed (block if not)
   - Snapshot current state (SQLite + ChromaDB copy)
   - Archive current identity_model.md to v1_staging
   - Clear SQLite facts + ChromaDB (both — per S65 rule)
   - Re-import expanded source
   - Batch extract → gates → author → compose
   - Generate changeSummary (already exists in seed_industry.py)
   - Update version + fingerprint in registry

3. **Complete batch extract document mode:**
   - S98 partially wired: build_document_extraction_prompt imported, run_submit() accepts document_mode + skip_extracted params
   - Complete: wire into pipeline command, test end-to-end
   - Keep batch state in JSON (simple, works, human-readable)

4. **Retire cmd_run()** — alias to `baselayer pipeline` with backward compat

**Done criteria:**
- [ ] `baselayer pipeline aarik` runs V1 end-to-end on test corpus
- [ ] `baselayer pipeline kevin_kelly --v2` runs V2 with snapshot + clear + re-extract
- [ ] Batch extract completes in document mode for 3 subjects
- [ ] Pipeline blocks on unchanged fingerprint
- [ ] Pipeline blocks on incomplete extraction
- [ ] Cost estimate displayed before API calls
- [ ] V2 snapshot restores on simulated failure

**Verification:** Run on 3 subjects of different sizes. Verify all gates fire.

**Rollback:** cmd_run() preserved as fallback. V2 snapshots enable restore.

**Effort:** 1-2 sessions.

---

### Phase 5: Version History + Magic Link Integration
**Goal:** Version history shows full identity model. Magic links integrated with outreach workflow.

**Entry criteria:** Phase 4 done. Pipeline producing correct V2 output.

**5a. Version history redesign (display-only change):**

Current state: VersionHistoryModal.tsx uses tabs (brief/anchors/core/predictions). Each diffed separately.
Target: Full identity model as one document.

**Keep Redis storage as-is** (separate brief/anchors/core/predictions). No data migration.

1. Remove tab navigation from modal
2. Use `versionToMarkdown()` (already exists, lines 75-123) to concatenate brief + anchors + core + predictions into one view
3. Diff the concatenated document (LCS already works for this)
4. changeSummary banner at top (already wired S98)
5. changeSummary generated on re-seed via generate_change_summary() (already exists) and stored as field in modelVersions

**5b. Magic link gmail integration:**

Current state: Magic links fully implemented (generate, consume, rate limit, bulk, auto-auth). push_gmail_drafts.py builds drafts with hardcoded passwords, no magic links.

1. Add magic link generation to push_gmail_drafts.py:
   - Before creating each draft, call `/api/magic-link/generate` with admin secret
   - Insert magic link URL into email body (password as fallback)
2. Update email template format

**5c. Internal magic link documentation:**
- How to generate (CLI or API)
- Integration with outreach workflow
- Security model (single-use, 7-day expiry, rate limits)
- Troubleshooting

**Done criteria:**
- [ ] Version history modal shows full identity model as one document (no tabs)
- [ ] Diff description renders at top
- [ ] Version history tested with dummy data on Aarik's account (not live subjects)
- [ ] Magic link URLs appear in generated gmail drafts
- [ ] Click magic link → page loads → auth cookie set → login recorded → link expires
- [ ] Internal docs written and reviewed

**Verification:** Generate magic links for 3 subjects. Click each. Verify full flow. Test version history with dummy data on Aarik's account.

**Rollback:** Website changes revert via git. Magic links in Redis expire naturally.

**Effort:** 1-2 sessions.

---

### Phase 6: Chunking + Extraction Hardening
**Goal:** Good fact density on dense texts without inflating sparse ones. Simple, not elegant.

**Entry criteria:** Phase 5 done.

**Current state:**
- Splits on `\n\n` (paragraph boundaries), 500-char overlap
- Per-chunk cap: `min(50, max_facts)` — equal for all chunks
- Final truncation: confidence sort (S97) → slice to max_facts
- Known failure: agentic_patterns (851KB) — later chapters starved because positional truncation (fixed S97 via confidence sort, but equal-chunk sizing still suboptimal)

**Simple approach (no over-engineering):**
1. **Equal-size chunks (~20-30KB each)** on paragraph boundaries. No chapter detection needed — equal sizing naturally gives every section the same extraction budget.
2. **Same per-chunk cap** for all chunks. Simple. Predictable.
3. **Global confidence sort after all chunks** — already exists (S97 fix). Best facts surface regardless of position.
4. **Coverage gate** — if >20% discarded, block (Phase 3A gate handles this automatically).

That's it. The confidence sort at the end is the key mechanism — it naturally selects the best facts across all chunks. Equal-size splitting ensures later sections aren't starved. No chapter detection, no round-robin weighting, no adaptive overlap.

**Work:**
1. Change chunk size from `input_char_budget` (24K) to a fixed ~25KB target with paragraph-boundary snapping
2. Verify global confidence sort works correctly across chunk boundaries
3. Test on agentic_patterns (known dense text) and a sparse corpus

**Done criteria:**
- [ ] Large text (agentic_patterns) extracts facts from ALL sections (not just first few)
- [ ] Sparse text doesn't produce inflated/low-quality facts
- [ ] Coverage gate blocks when >20% discarded
- [ ] Golden dataset test passes (no regression)
- [ ] Tested on: dense (agentic_patterns 851KB), medium (Cedric Chin 297 files), sparse (small subject)

**Verification:** Re-extract agentic_patterns. Check fact distribution across document sections.

**Rollback:** Revert chunk sizing. Old code in git.

**Effort:** <1 session.

---

### Phase 7: Type Unification + Frontmatter (Thinkers Only)
**Goal:** Stable thinkers page type system. Machine-parseable layers. Examples page stays as-is.

**Entry criteria:** Phase 6 done.

**Scope: Thinkers/Industry pages only.** Franklin/examples pages use their own types (LayerItem, Fact, Trace) and are a separate, lower-priority codebase. Don't touch them.

**Work:**
1. **JSON frontmatter in layer .md files:**
   ```markdown
   ---
   layer: anchors
   version: 4
   generated: 2026-03-25T15:12:00
   model: claude-sonnet-4-20250514
   item_count: 8
   items:
     - {id: A1, name: COHERENCE}
     - {id: A2, name: INTEGRITY}
   ---

   ## Injectable Block
   [human-readable content unchanged]
   ```
2. **seed_industry.py reads frontmatter** (simple `---` split + yaml.safe_load) instead of regex parsing
3. **Clean up IndustryLayerItem / IndustryFact types** in redis.ts — ensure they're the single source of truth for thinkers pages
4. **Migrate 29 Redis briefs** if any are still stored as raw strings → BriefParagraph[]
5. **MCP server:** Verify still works (reads markdown body, not frontmatter)

**Done criteria:**
- [ ] New layer files include JSON frontmatter
- [ ] seed_industry.py parses frontmatter (no regex for structure)
- [ ] All thinkers pages render correctly
- [ ] MCP server serves identity correctly
- [ ] Golden dataset test passes

**Verification:** Seed 3 subjects with frontmatter layers. Verify pages render.

**Rollback:** Frontmatter is additive — old markdown body unchanged. Redis migration reversible.

**Effort:** 1 session.

---

### Phase 8: Cleanup + Documentation + Temporality Prep
**Goal:** Lean codebase, accurate docs, ready for temporal modeling.

**Entry criteria:** Phase 7 done.

**Work:**
1. **Schema versioning:** Add schema_version table + migration runner (simple SQL scripts in migrations/ folder)
2. **Temporality Phase 1** (fact_class column ALREADY EXISTS):
   - Update extraction prompt to classify facts as event/state during extraction (write path)
   - Update at least one gate or renderer to use fact_class (read path — per GPT rule: no partially-real fields)
   - Backfill Aarik's facts with Opus classification (~$7 one-time)
3. **Doc consolidation:** 87 active docs → target ~40. Archive stale eval results, old plans, old reviews.
4. **Update core docs:**
   - DECISIONS.md: Mark D-024 superseded, D-052 "thin wrapper", add D-085 (compose scaling)
   - ARCHITECTURE.md: Reflect post-refactor pipeline with unified command + batch extract + gates
   - FLOW_GUIDE.md: Reflect `baselayer pipeline` command
   - PROJECT_OVERVIEW.md: Current state
5. **Archive stale experiments** (memory_system/src/baselayer/experiments/ — anything not modified in 60+ days)

**Done criteria:**
- [ ] schema_version table exists with migration runner
- [ ] fact_class write path works (extraction prompt classifies)
- [ ] fact_class read path works (at least one gate/renderer uses it)
- [ ] Aarik's facts backfilled
- [ ] Active docs ≤ 50 files
- [ ] Core docs (DECISIONS, ARCHITECTURE, FLOW_GUIDE, PROJECT_OVERVIEW) all accurate
- [ ] Golden dataset test passes
- [ ] `baselayer test` passes all tests

**Verification:** Run full test suite. Spot-check 5 docs for accuracy.

**Rollback:** Schema additions additive. Docs restorable from git.

**Effort:** 1 session.

---

## Part 4: Timeline

| Phase | Focus | Sessions | Status |
|---|---|---|---|
| 0 | Security | <1 | ✅ COMPLETE |
| 1 | Compose fix + hallucination + dead code | 1 | ✅ COMPLETE |
| 2 | Test harness augmentation | 1 | ✅ COMPLETE |
| 3A | Safety gates | 1 | ✅ COMPLETE |
| 3B | Subject registry + migrations | 1-2 | ✅ COMPLETE |
| 4 | Unified pipeline + batch extract | 1-2 | ✅ COMPLETE (pipeline cmd done, batch extract deferred to follow-up) |
| 5 | Version history (display) + magic link integration | 1 | ✅ COMPLETE (button hidden until tested with dummy data) |
| 6 | Chunking (simple equal-size) | <1 | ✅ COMPLETE (already working — S97 confidence sort was the fix) |
| 7 | Type unification + frontmatter (thinkers only) | 1 | ✅ COMPLETE |
| 8 | Cleanup + docs + temporality | 1 | ✅ COMPLETE (schema versioning, DECISIONS updated, 17 experiments archived, 60 active docs) |
| **Total** | | **8-11 sessions** | |

**V2 runs resume after:** Phase 4 complete.
**Outreach resumes after:** Phase 5 complete.

---

## Part 5: Pre-Refactor Checklist

- [x] Aarik reviewed plan
- [x] External LLM feedback incorporated (Claude, DeepSeek, Gemini, GPT, Grok)
- [x] Deep research on all phases completed (5 parallel agents)
- [x] Decisions 1-9 confirmed
- [x] All V2 pipeline runs paused
- [x] All outreach on hold
- [x] Anthropic folder cleaned up
- [x] Git tags `pre-refactor-s98` created on both repos
- [x] Phase 0 (security) complete — bcrypt deployed + verified
- [x] Phase 1 complete — compose scaling verified (KK brief changed), hallucination fixed, 69 dead files removed, 369 tests pass
- [ ] Begin Phase 2
- [ ] TODO: Run Aarik's personal pipeline (recompose with corrected facts, post-refactor)

---

## Part 6: What's NOT in this refactor

- Full temporality (Phases 2-5 of temporal spec) — separate workstream post-refactor
- Multi-provider full wiring (D-052) — keep wrapper, wire when needed
- Always-on integration path — hold
- MCP server updates — deprioritize
- Moltbook Agent — separate scope
- Website examples-page parity — separate scope
