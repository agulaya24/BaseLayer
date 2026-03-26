# Base Layer — Session Progress (S86+)

> Sessions S1-S85 archived in [PROGRESS_ARCHIVE.md](PROGRESS_ARCHIVE.md)

## Session 98 (2026-03-25) — Full System Audit, V2 Paused, Refactor Plan

### V2 Status Corrected
- Only Kevin Kelly is real V2 (76→2,324 facts, 670 files). Layers changed but brief byte-for-byte identical (compose saturation).
- David Perell + Henrik Karlsson are V1-FINAL (corpus-limited, fully scraped).
- Casey Newton (55/285 extracted) + Maggie Appleton (58/213 extracted) halted mid-extraction.
- S96 claimed 5 V2 upgrades — 4 were false (re-ran on identical data). Dashboard + docs corrected.

### Pipeline Failures Found
- **Agents ran author/compose on 10% extracted data** — no extraction completeness gate existed. Casey + Maggie briefs are garbage.
- **Batch extract doesn't support document mode** — all subject extractions burning 2x API cost on sequential calls.
- **No manifest gate** — nothing prevents re-runs on unchanged source data.
- Extraction gate added to cli.py + author_layers.py (blocks if extraction incomplete). Untested end-to-end.

### Full System Audit (3 parallel agents)
- **Pipeline audit:** 16,631 LOC, 20 modules. 19 duplicate files, 12 dead steps, llm_provider.py unused, assemble_brief.py dead.
- **Supporting files audit:** 67 source dirs, 50 subject envs, 148 docs (many stale), duplicate archives.
- **Website audit:** 2 critical security bugs (password plaintext + timing-safe negated), type inconsistencies, 2 dead components.

### External LLM Review (5 models: Claude, DeepSeek, Gemini, GPT, Grok)
- Unanimous: compose saturation must be investigated before pipeline work.
- Unanimous: Phase 2 overloaded — split into 2A (gates) and 2B (registry).
- GPT: manifest = input fingerprint (not just file hash). V2 needs snapshot-before-clear. Document mode explicit not auto-detect.
- Claude: done criteria per phase, rollback plans, Issue #7 needs phase assignment.
- Gemini: golden dataset regression test needed before schema changes.

### Code Changes
- Identity model versioning: auto-archive to v1_staging, changeSummary generation, website version history diffs all tabs.
- Website pushed + deployed (version history modal, changeSummary, layer prop chain).
- Extraction gate added to cli.py and author_layers.py.
- batch_extract.py partially wired for document mode (incomplete).
- V2 scraping: Casey Newton 103→273 files, Maggie Appleton 121→213 files. David Perell +12 (corpus-limited), Henrik +4 (corpus-limited).

### Anthropic Folder Cleanup
- Deleted API key file (outdated key exposed as filename since Feb 18).
- Archived: memory_system_v4, data exports (2.3GB), overnight results, stale scripts, old reviews.
- Organized: outreach files → drafts/, runner scripts → memory_system/runners/, ablation briefs → archive.
- Root-level: 9 active items, everything else archived with backups in _archive/backup_s98_20260325/.

### Refactor Plan Produced
- 8 phases, 10-14 sessions, gated with entry/done/verification/rollback per phase.
- See: `docs/core/REFACTOR_PLAN_S98.md`
- ALL V2 runs + outreach ON HOLD until refactor completes through Phase 4.

### Key Decisions (S98)
- D-087: Compose fact scaling (100→300 for large corpora). Confirmed: Kevin Kelly brief changed.
- D-088: Unified pipeline + safety gates. `baselayer pipeline <subject> [--v2]`
- Keep multi-provider (deprioritize), markdown+frontmatter, per-subject DBs
- Golden dataset: Aarik's own model
- Version history: full identity model as one document, not tabs

### Aarik's Pipeline Test
- Full pipeline run completed. 4,605 active facts, 2,682 identity-tier. 300 facts sampled for compose (was 100).
- Brief: 10,415 chars. All gates passed (contamination + faithfulness).
- Hallucinations fixed: Victoria/young child (authoring fabrication), SpaceX (quoted content misattributed).
- Thinkers page live at base-layer.ai/thinkers/aarik with version history.

### Overnight Runs (in progress)
- 12 high priority V1 pipelines: Derek Sivers, Andy Matuschak, Gwern, Kyle Harrison, Tunguz, Zvi, Schwitzgebel, Jack Clark, Morgan Housel, patio11, Seth Godin, Visakan. ~8,500 source files.
- Local model comparison: qwen2.5:32b, deepseek-r1:32b, gemma2:27b, mistral:7b, phi4:14b, haiku — 2 prompt variants x 20 conversations each.
- New model test (queued): qwen3:14b + gemma3:12b (just released, pulled).

### New Models Available
- Qwen 3 released (0.6B-32B). qwen3:14b matches qwen2.5:32b performance.
- Qwen 3.5 released (0.8B-27B). Native tool calling. March 2026.
- Gemma 3 released (270M-27B).
- Ollama now supports native structured JSON output (format parameter).

---

## Session 97 (2026-03-24) — Underextraction Fix, Agentic Patterns V2, GPU Large Models

### CRITICAL: Underextraction Bug Found + Fixed
- **Root cause:** `extract_facts.py` line 1349 — `return all_facts[:max_facts]` truncated positionally, not by quality. With 200-cap, later chunks (Ch14-Ch21) got 0-2 facts despite Haiku extracting them. 71% of facts silently discarded.
- **Fix 1:** Raised `max_facts_ceiling` to 600 (done prior session, confirmed working).
- **Fix 2:** Sort by confidence before truncating — keeps best facts, not first facts. Applied to both `src/baselayer/extract_facts.py` and `scripts/extract_facts.py`.
- **Fix 3:** Coverage warning added — prints discard % and recommendation when cap is hit.
- **Still needed:** Chapter-level import splitter, round-robin allocation, automated coverage gating (>20% discard = pipeline block).

### Agentic Patterns V2 Re-extraction
- Cleared SQLite + ChromaDB, re-extracted with 600 cap.
- **306 facts** (was 144) — 2.1x improvement. AUDN dedup kept quality high.
- Predicate distribution: believes 122, values 52, practices 46, avoids 33, prioritizes 32, builds 12.
- 3 layers authored: ANCHORS (vector provenance), CORE (433% citation provenance — 26 claims, 48 fact refs), PREDICTIONS (vector provenance).
- Brief composed: **8,417 chars / 2,104 tokens** (was 6,183 chars). Quality/contamination/faithfulness gates: all PASSED.
- Total cost: ~$0.22.

### GPU Large Models Downloaded
- `gemma2:27b` (15 GB), `deepseek-r1:32b` (19 GB), `qwen2.5:32b` (19 GB) — all pulled.
- 13 models total available for overnight testing.
- `overnight_gpu_full_pipeline.py` updated with new model lists for extraction/authoring/compose.

### Percepta GPU Test (Small Models)
- 10 models × 20 computational tasks = 200 runs.
- 126/200 complete at session mid-point. Final 2 models (sam860/LFM2 variants) still running.
- Results: `gpu_experiment_results/percepta/results_20260324_191052.json`.

### Priority Review
- Full audit of CLAUDE.md + MEMORY.md + PROGRESS.md active items — nothing dropped.
- Flagged: Moltbook Agent stale (dashboard scripts deleted), Aarik's brief short (738 words), 3 bounced emails unresolved.

### Folder Cleanup Verified
- All 50 subject directories intact, 91 subjects properly organized.
- No orphaned files, temp artifacts, or misplaced data.
- Archives clearly labeled in `archive/scripts_backup_20260310/` and `archive/stale_scripts/`.

---

## Session 88 (2026-03-11) — Aria Case Study, V5 Briefs Live, JSON Import

### Aria (VividnessMem AI Character) Case Study
- **First non-human subject.** Ran full pipeline on Aria's memory dump (70 reflections from u/Upper-Promotion8574's VividnessMem project).
- JSON import support added to pipeline (`--json` flag, auto-detect `.json` in `baselayer run`).
- Extracted 42 facts, authored 3 layers (24 axioms, 3 context modes, 5→6 predictions), composed V5 brief.
- **Axiom inflation identified:** 24 axioms from 42 facts vs typical 7-9 from hundreds of conversations. Insufficient data density to separate load-bearing axioms from surface opinions.
- Re-authored with citation API — CORE got 29 citation-linked claims. ANCHORS/PREDICTIONS fell back to vector provenance (heavy synthesis, API limitation).
- Tension detection run: 12 tensions found, added to website.
- Hidden example page at `base-layer.ai/examples/aria` — accessible via direct URL, not listed in nav or examples page.
- Total pipeline cost: ~$0.27.

### V5 Briefs Live on All Examples
- All 8 public example pages updated from V4 to V5 clean briefs.
- Added "Annotated Brief" download option — serves the cited brief_v5.md with [A1], [C2], [P3] markers preserved.
- Added `citedBrief` export to all data files + SubjectConfig interface + DownloadMenu.

### Research Page Fixes
- Section ordering fixed to match nav sidebar (prompt-ablation first).
- Study count updated: "Six studies" → "Seven studies".
- Design decisions: 76 → 80.
- Preliminary results disclaimer added to prompt ablation section.

### Script Cleanup
- 10 orphaned scripts moved to `scripts/archive/utilities/` (add_indexes, check_progress, create_turn_pairs, detect_contradictions, generate_docx, generate_tension_data, generate_website_data, monitor, query, summarize).
- Dependency graph traced from cli.py and mcp_server.py — 19 active scripts confirmed.

### External Project Reviews
- Reviewed claude-memory-mcp, VividnessMem, LAM protocol, identity-ai, AIUC-1.
- Drafted Reddit responses for r/aigamedev (VividnessMem) and r/aimemory.

### Pipeline Notes
- **Citations API on ANCHORS/PREDICTIONS:** Returns 0 because model synthesizes too heavily. Vector provenance fallback works. This is an API limitation, not a bug.
- **Tension detection + predicate distributions are not pipeline steps** — they run separately via archived scripts. Should be integrated into the pipeline.
- **JSON import design (Approach A):** Flatten JSON tree, try known text field names (content, text, message, body, reflection, etc.), fall back to all strings >50 chars.

---

## Session 89 — 2026-03-12 (SWE-Bench Infrastructure + T4 Ready)

### Infrastructure Setup
- WSL2 v2.6.3 installed (Ubuntu 22.04).
- Docker Desktop v29.2.1 installed (WSL2 backend).
- swebench 4.1.0 installed in WSL Python venv (`~/swebench-env`).
- Docker images cached: base (Ubuntu + conda, 2.18GB), env (Django deps), instance (Django at base_commit).

### Harness Built (`scripts/swebench_harness.py`)
- Two-phase architecture: GENERATE (agent loop) + EVALUATE (swebench Docker).
- Agent: Minimal — Anthropic API tool_use + bash in Docker container. 25 turns max, temp=0.
- Framework constant across conditions — only system prompt varies.
- Resume support — skips completed problem×condition pairs on rerun.
- Subcommands: `generate`, `evaluate`, `run` (both).

### Validation Run
- Problem: `django__django-10097` (URLValidator invalid chars).
- Condition: C0 (bare). Model: Haiku.
- Agent used 25 turns, explored repo, found `validators.py`, tested fix in Python, applied regex change.
- Patch: 641 chars. Cost: $0.30.
- swebench evaluation: **RESOLVED** (all fail-to-pass tests passed).
- End-to-end pipeline confirmed working.

### Bugs Fixed During Setup
- `make_test_spec` import path changed in swebench 4.1.0 (`swebench.harness.test_spec.test_spec`).
- `build_container()` requires `nocache` param in 4.1.0.
- `swebench` doesn't run on Windows (Unix-only `resource` module) — must run in WSL.
- Docker `exec_run` `workdir` unreliable — wrapped commands with `cd /testbed &&`.
- API key not inherited in WSL — must export explicitly.

### T4 Gating Strategy (decided)
1. Run full T4 on Haiku first (~$63, ~10 hrs overnight). 30 problems × 7 conditions.
2. If C2 > C0 with p < 0.05: replicate on Sonnet (~$100).
3. If null on Haiku: save $100, publish null honestly.
- Rationale: Haiku ~10x cheaper. E1 showed format effect is LARGER on smaller models. Haiku pilot is the cheapest path to a publishable result.

### Pre-Flight Tasks (Opus + Sonnet review recommendations)
1. **Axiom-problem relevance ratings** — Sonnet rated all 30 problems. 16 score 1 (no axiom relevant), 8 score 2, 6 score ≥3. Saved: `data/swebench/axiom_relevance_ratings.json`. Enables subgroup analysis if H1 fails.
2. **Token counts measured** — All conditions counted via API. C7 (1183 tokens) is 3.6x C2 (327). Saved: `data/swebench/condition_token_counts.json`.
3. **C7 built** — Raw Django design philosophy docs (unstructured, same source as C2). Replaces C6. Tests ETH Zurich finding: structured compression vs raw repo context.
4. **C6 dropped** — Length-matched generic SE advice was weakest control. C7 is stronger comparison. C3 + C7 cover length confound.

### Study Design Changes (S89)
- **C6 → C7:** Reviewed by Opus and Sonnet. Both approved. C7 tests Base Layer's core thesis: structured compression > raw context dumping.
- **Two-phase launch:** Phase A = C0 baseline (verify solve rate). Phase B = remaining conditions.
- **Subgroup analysis pre-registered:** High-relevance problems (score ≥3, N=6).
- **H6 updated:** C2 > C7 (structured axioms > raw repo context).

### Migration to OpenHands (S89 continued)
- **Switched from custom bash-only harness to OpenHands** — industry-standard agent framework used by ETH Zurich study (arxiv 2602.11988).
- **Why:** Custom harness gave agent only bash tool. OpenHands provides file editor, search, bash — proper SWE-bench agent toolset. Results directly comparable to published benchmarks.
- **OpenHands benchmarks repo cloned:** `/home/agulaya/openhands-benchmarks/` (git submodule initialized, `uv sync` for deps).
- **7 Jinja2 prompt templates created:** `benchmarks/swebench/prompts/swe_C0.j2` through `swe_C7.j2`. Each prepends condition text to OpenHands' default 8-phase instruction template.
- **LLM config:** `llm_config_haiku.json` — `anthropic/claude-haiku-4-5-20251001`, temp=0, prompt caching enabled.
- **Instance list:** `selected_django_30.txt` — 30 Django problem IDs, one per line.
- **Wrapper script:** `run_axiom_study.sh` — supports `phase_a`, `phase_b`, `all`, or single condition.
- **Max iterations:** 100 (OpenHands standard). Each iteration = one tool call. Typical solve: 30-60 iterations.
- **Docker images:** Auto-built on first run via `ensure_local_image()`. No pre-build needed.
- **Old harness (`scripts/swebench_harness.py`) SUPERSEDED** — kept for reference only.

### Updated Cost Estimates (OpenHands + Haiku 4.5)
- **Phase A (C0 baseline, 30 runs):** ~$15-45
- **Phase B (C1-C5,C7, 180 runs):** ~$90-270
- **Total Haiku T4:** ~$100-300
- **Sonnet replication (if signal):** ~$400-800
- Higher than custom harness (~$63) because OpenHands uses richer tools, longer context per iteration, and 100 max iterations (vs 25 turns). Standard for published SWE-bench evaluations.

### Next Step
- **Phase A:** C0 baseline on 30 problems. Verify solve rate 10-70%.
- **Phase B:** If Phase A passes, run remaining 6 conditions.
- Run commands: `cd /home/agulaya/openhands-benchmarks && export ANTHROPIC_API_KEY='...' && ./run_axiom_study.sh phase_a`
- Review results in S90.


## Session 90 (2026-03-17) — SWE-Bench T4 Complete + Dan Shipper Pipeline

### SWE-Bench T4 — COMPLETE, NULL RESULT
- **Result:** C0 (36.7%) beat all conditions. Axioms produce behavioral drift but do NOT improve coding task completion.
- **Conditions:** 7 (C0 bare, C1 name, C2 axioms, C3 long-axioms, C4 persona, C5 full-brief, C7 raw-repo-context).
- **Key finding:** Base Layer's value is human understanding, not agent task performance. Sharpens positioning.
- **Cost lesson:** OpenHands underreports 3.5x due to prompt caching. Always verify against API dashboard.
- See `memory/swebench_study.md` for full results + lessons.

### Dan Shipper Pipeline — COMPLETE
- 60 source files → 244 facts → anchors_v4 + core_v4 + predictions_v4 + brief_v5_clean.md
- Environment: `C:\Users\Aarik\Anthropic\dan_shipper_memory\`
- Cost: ~$0.20 actual
- **3 prompt changes shipped** (S91):
  1. ANCHORS: Gravitation framing — axioms are things the subject reasons FROM
  2. PREDICTIONS: 2+ source minimum — no thin-data predictions
  3. CORE: `identifies_as` attention weighting — professional self-concept elevated
- **D-081 decided:** Layers for AI, brief for humans. AI contexts (MCP, Claude Code) serve full three-layer artifact. Brief is human-only (website, outreach).

## Session 91 (2026-03-17) — Repo Cleanup + Hidden Industry Section (Build)

### Repo Cleanup
- Deleted dead archive scripts, consolidated utilities, removed stale docs.
- `generate_website_data.py` confirmed as canonical script for website data generation.

### Industry Outreach Section — Infrastructure Built (S91 Sonnet)
- Hidden `/industry/[token]` section built. Token = password. Server-side auth on every request.
- Storage: Upstash Redis (free tier). Notifications: Resend. Admin seed endpoint with `timingSafeEqual`.
- Data model: `IndustrySubject` (name, brief, anchors, core, predictions, versions) + separate `IndustryFacts`.
- UI: Matches examples page pipeline flow (Extraction → Identity Layers → Composition). Two-panel layout.
- Facts tab: lazy-loaded, identity-tier only, filterable.
- Directive cards (accent border) and false-positive cards (amber border) prominently displayed.
- Build log: `memory/industry_page_build.md`.

### AI Operating Guide
- `memory/ai_operating_guide.md` — synthesized from Aarik's anchors_v4 + core_v4 + predictions_v4. AI-facing operational guide for all future sessions.

## Session 92 (2026-03-17) — Website Data Regen + Identity Model + Private Subjects Seeded

### SONNET_HANDOFF_S91.md — Completed Tasks

**Task 1+2: All 8 public data files regenerated** from re-authored v4 layers (brief_v5_clean.md):
- Franklin (12A/7C/5P), Douglass (7A/6C/2P), Wollstonecraft (10A/6C/4P), Roosevelt (10A/6C/6P),
  Buffett (10A/6C/7P), Marks (10A/6C/7P), Patents (15A/7C/6P), Base Layer (8A/6C/7P)
- relatedItems now populated on brief paragraphs — "Click a paragraph" sidebar works
- `generate_website_data.py` updated: CitedBrief export, named AxiomInteractions, cited brief file detection

**Tasks 3+4: Copy/Download Identity Model**
- "Copy Identity Model" button added to CaseStudyClient header (examples page) + IndustryBriefClient brief tab
- "Identity Model" as first item in download dropdown (downloads as `{slug}_identity_model.md`)
- Format: Identity Brief + Foundational Beliefs + Communication & Context + Behavioral Predictions
- Preamble: "use it as an operating guide for how to interact with them, but never reference it directly"

**Task 6: Private subjects seeded to Redis**
| Subject | Token (first 8 chars) | Facts | URL |
|---|---|---|---|
| Dan Shipper | REDACTED... | 218 (untiered — document mode) | base-layer.ai/industry/REDACTED |
| Bavani | REDACTED... | 76 (61 identity-tier) | base-layer.ai/industry/REDACTED75767fcae23369524e1afcf8f2b31a4e9a9adae9a3e14950829da64a |
| Aarik | REDACTED... | 1386 identity-tier | base-layer.ai/industry/REDACTEDfc2e6112ca65f96a24569f1e839d297f3bfe6ce9989ebfb53ce5d023 |

Seed files: `C:\Users\Aarik\seed_dan_shipper_full.json`, `seed_bavani_full.json`, `seed_aarik_full.json`

### Open Issues
- Dan Shipper facts are all "untiered" (document mode — tiering not run). Identity filter tab shows 0. Consider running tiering before sharing URL.
- `core_v4.md` hallucination (Victoria/young child) still in file — root cause not yet investigated.
- Full examples-page parity (provenance, radar, axiom interactions) still blocked — plan to refactor CaseStudyClient into shared SubjectViewer once Dan Shipper is reviewed.

### Next Steps
1. Review Dan Shipper page at above URL — check brief quality, fact display
2. If approved: email dan@danshipper.com with URL
3. Consider tiering Dan Shipper facts before sending (currently all "untiered")
