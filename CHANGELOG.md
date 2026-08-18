# Changelog

All notable changes to Base Layer are documented here.

---

## 0.5.0 - 2026-08-18

### Changed (BREAKING: Chroma distance conversion requires the distance space)
- `config.chromadb_dist_to_similarity(dist, space)` now takes the collection's distance space as a required second argument, and raises `ValueError` on any value outside `cosine`, `l2`, `ip`. `config.collection_space(collection)` reads it off the collection's `hnsw:space` metadata.
- Collections in this project are not uniform. `memory_facts` is created cosine; `messages`, `turn_pairs` and `conversation_summaries` are left at Chroma's l2 default. The previous version applied the l2 formula to all of them.
- Measured against the live cosine `memory_facts` collection, the single formula inflated similarity by about 0.46 to 0.47 across the returned range, and it inverted the threshold decision: a distance of 0.5477 was reported as 0.8500 and passed a 0.85 gate whose true similarity is 0.4523.
- Three of five call sites query `memory_facts` and were wrong: `assemble_brief.py`, and two in `verify_provenance.py`. Those feed `verify`, `provenance` and `trace_claim`. An inflated similarity makes an unrelated fact look like supporting evidence, which is the failure this project's auditability claim cannot absorb.
- `space` has no default, on purpose. A default is what produced the defect: the wrong formula applied silently to the collection that mattered most.

### Migration notes
- Every caller of `chromadb_dist_to_similarity` must pass a space. Read it from the collection rather than assuming: `chromadb_dist_to_similarity(d, collection_space(coll))`. There is no compatibility shim; a missing argument is a `TypeError` and a guessed one is a `ValueError`.
- New tests at `tests/test_similarity_space.py`. Five tests in `test_unified_brief.py` changed to name the l2 behaviour they actually assert.

### Changed (CLI accuracy)
- `init --force` help no longer claims to delete data. It drops nothing; the schema is `CREATE TABLE IF NOT EXISTS` throughout. A real reset is `forget --all` plus deleting the vector store.
- `run` is documented as the entry point. `pipeline` takes a registry `subject_id` and is the lower-level surface.

### Changed (documentation)
- README and `docs/core/ARCHITECTURE.md` rewritten around interpretive distillation as the authoring architecture.
- Personal material and third-party names removed from the public documentation tree.

---

## 0.4.0 - 2026-05-07

### Changed (resource simplification: inline structural layers)
- The `memory://specification` resource now returns CORE + ANCHORS + PREDICTIONS inline (~6 to 8K tokens) plus a brief manifest. The structural specification is fully loaded at session start; the model does not have to make routing decisions about layers it cannot see.
- Removed the `get_anchors` and `get_predictions` MCP tools. Their content is now part of the always-on resource.
- The `get_brief` tool remains on-demand because the unified narrative brief serves a different shape of query (broad self-reflective) and is large enough to keep behind a fetch.

### Why
- The 0.3.0 partial-serving design split CORE on the resource and ANCHORS/PREDICTIONS behind on-demand tools. Live use surfaced two issues. (1) The model had to make routing decisions about layers it could not see, leading to over- and under-fetching. (2) The token savings that justified the split (approximately 5K) are negligible in modern context windows. The proposal at `docs/reviews/mcp_titles_manifest_proposal_20260507.md` (gitignored) makes the structural argument; this release implements it.
- The `reason` parameter survives only on `get_brief` since it's the single remaining on-demand layer fetch.

### Migration notes
- External MCP clients that called `mcp__base-layer__get_anchors` or `mcp__base-layer__get_predictions` will receive "tool not found" errors. The same content is now in `memory://specification` payload.
- Per-session call-log shapes are unchanged. `get_help` still works; the agent guide section "When to fetch which layer" was simplified to reflect the single remaining on-demand fetch.

### Reproducibility
- The paper-version pin remains git tag `v0.2.0`. 0.4.0 is forward development; the paper does not cite it.

---

## Unreleased (post-0.3.0)

### Added (in-session spec-serving toggle)
- `baselayer serve enable | disable | status` CLI subcommand. Toggles whether the MCP server actually serves spec content without restarting Claude Code or the server.
- When disabled, the always-on `memory://specification` resource and the layer tools (`get_anchors()`, `get_predictions()`, `get_brief()`) return a polite disabled message instead of content. The model is told to continue helping without spec context. Other tools (recall_memories, search_facts, trace_claim, verify_claims, get_stats) keep working since they are fact-database queries, not spec serving.
- The toggle uses an on-disk state file at `~/.baselayer/serving_enabled`. The MCP server reads it on every call. Mid-session flips take effect on the next call; no restart required.

### Added (per-session call traces with reasons)
- Each running MCP server now writes to its own session directory at `~/.baselayer/sessions/<pid>/`, with `meta.json` (pid, parent_pid, start_time, cwd), `count` (live integer call count), and `log.jsonl` (append-only call log). Sessions persist on disk after the server exits; `count` is removed on clean shutdown but the log stays for analysis.
- Two simultaneously-open Claude Code windows now show independent counts in the statusline because each window's MCP server has its own session dir. The statusline locates its session by matching its own parent PID (Claude Code) against the recorded `parent_pid` in each session's meta.
- The three layer tools (`get_anchors`, `get_predictions`, `get_brief`) now require a `reason: str` parameter. The model must provide a one-sentence rationale for each fetch ("user weighing a job offer that involves a values trade-off"). Reasons are persisted in the per-session log, giving a record of *when in the conversation* the model decided it needed each layer and *why*. The parameter was previously optional with default ""; per integration feedback (`docs/reviews/mcp_integration_feedback_20260507.md`), making it required forces the calling agent to articulate intent before it can fetch.
- `baselayer log list | show | tail | stats` CLI subcommand for analyzing call traces. `list` enumerates all sessions; `show <pid>` prints the full call log for a session; `tail --pid X --limit N` shows the last N calls; `stats` aggregates calls-by-tool across all sessions.
- The previous single-file counter at `~/.baselayer/mcp_session_count` is replaced by the per-session counter at `~/.baselayer/sessions/<pid>/count`. The old file is no longer used and can be deleted manually if it exists.

### Documentation
- `recipes/serve_specification_via_mcp.md` now includes a "Verifying the server is actually running" section. The Claude Code `/mcp` dialog has been observed reading "off" or "needs reconnect" while the server was responsively answering tool calls; readers are directed to `claude mcp list` or to ask the model to call a Base Layer tool as authoritative health checks. The `/mcp` dialog is for Anthropic-managed cloud connectors only; local stdio servers are managed via the CLI.

---

## 0.3.0 - 2026-05-06

### Changed (MCP partial-serving refactor)
- The `memory://specification` MCP resource now returns the CORE layer (Communication and Context) plus a manifest of available tools, rather than the full specification. Baseline MCP context cost drops from approximately 5,000 to 10,000 tokens to approximately 1,500 to 2,500 tokens. The full specification remains accessible via tools.
- The `memory://identity` deprecated alias continues to return identical content to `memory://specification` (i.e., it now returns the partial-serving payload too).

### Added
- `get_anchors()` MCP tool: returns the ANCHORS layer (foundational beliefs and worldview, approximately 2,500 tokens).
- `get_predictions()` MCP tool: returns the PREDICTIONS layer (situational behavioral predictions, approximately 2,500 tokens).
- `get_brief()` MCP tool: returns the unified narrative specification (approximately 3,000 tokens).
- Call logging: every MCP resource read and tool invocation logs to stderr at INFO level. Format: `[base-layer] INFO: mcp_call name=<name> [k=v ...]`. Tail the Claude Code MCP log to monitor usage in real-time.
- Spec-loading workflow documentation at `docs/internal/spec_loading_workflow.md`.

### Breaking
- The `memory://specification` resource content shape changed. Any client that hardcoded the assumption that the resource returns the full specification (rather than calling the new tools to fetch the rest) will see partial content. The manifest in the new payload describes the recovery path explicitly.

### Reproducibility
- This is a 0.3.0 release. The paper-version pin is git tag `v0.2.0`. The same source is also vendored into the `memory-study-repo` at `./baselayer/` for paper readers. Base Layer is not currently on PyPI; the `baselayer` name is held by an unrelated project. Paper readers install via `pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0` or use the vendored copy.

---

## 0.2.0 - 2026-05-06 (paper version)

This release is the immutable reference state corresponding to the "Beyond Recall" research paper. The git tag `v0.2-paper-2026` points at this commit. Future work continues under semver, with all paper-cited surfaces (URLs, MCP URIs, CLI flags, filesystem paths) preserved as aliases indefinitely.

### Changed (Phase A: vocabulary alignment, non-breaking)
- Docstrings, comments, log strings, MCP resource descriptions, and CLI help text now use "specification" / "the three layers" / "behavioral specification" instead of "identity model" / "identity brief" / "identity layers." No filesystem, database, or API changes; existing installs work without migration.
- MCP server: `memory://specification` is now the canonical resource URI. `memory://identity` continues to work as an alias forwarding to the same handler.
- Repo cleanup: `docs/` consolidated to four sibling directories (`core/`, `eval/`, `archive/`, `internal/`); top-level cleaned of backup folders, internal handoff files, and out-of-scope working directories.
- Standard OSS files added: `CODEOWNERS`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.editorconfig`, `ROADMAP.md`.
- Token range standardized at 5,000 to 10,000 tokens across all user-facing documentation.

### Deprecated
- The MCP resource URI `memory://identity` is deprecated in favor of `memory://specification`. Both currently return identical content; the alias will be retained for the foreseeable future to preserve compatibility for any external MCP client that hardcoded the old URI.

### Reproducibility
- This version is tagged `v0.2.0` on GitHub and vendored into the `memory-study-repo` at `./baselayer/`.
- Paper readers can reproduce the experiments via `pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0` or by cloning the study repo and running `pip install -e ./baselayer`.
- Base Layer is not on PyPI; the `baselayer` name there is held by an unrelated project. The git-install path is the canonical install method for the paper-cited version.

### Roadmap
- Phase B (planned, non-breaking): add `data/specifications/` directory alongside `data/identity_layers/`; both read on load. Add `specification.md` output filename alongside `brief_v4.md`. Add `--specification-only` CLI flag alongside `--identity-only`. Will ship as `0.3.0`.
- Phase C (planned, non-breaking): website adds `/api/specifications/{subject}` endpoint alongside the existing `/api/identity/{subject}`. Both serve the same handler. Documented in `baselayer-website` repo.

---

## 0.1.1 - 2026-04-22

### Package surface cleanup
- Removed dev-internal subpackages from the shipped distribution: `baselayer.archive`, `baselayer.archive.dead_pipeline_steps`, and `baselayer.experiments` are no longer included in `pip install baselayer`. Directories remain on disk for developers.
- `pyproject.toml` `[tool.setuptools] packages` reduced to `["baselayer"]` with matching `exclude-package-data` entries to keep archive/experiment assets out of the wheel.
- Version bumped `0.1.0` -> `0.1.1` to reflect the narrowed public surface.

---

## Unreleased

### Planned
- **D-056 Tier 3** — Quality gate between extraction and storage (reject hedging, low-density, LLM artifacts)
- **Cross-provider blind evaluation** — Claude / ChatGPT / Gemini comparison
- **Fact correction UI/CLI** — `baselayer correct` command to flag, edit, or supersede individual facts. Current `user_corrections` table exists but has no user-facing interface. Triggered by S62 finding: aspirational facts ("aspires to a long-term personal goal" rec:93) and situational facts ("lives in a particular city" rec:24) were promoted into identity layers as confident biographical claims. Need: (1) CLI to list/search/edit/supersede facts by ID, (2) corrections cascade to layers on next authoring cycle, (3) hybrid verification — heuristic term-match + Haiku semantic check on composed brief vs source facts

---

## 2026-03-02

### Unified Brief Composition (S62)
- `baselayer compose` — Opus compresses 3 deployed layers + identity-tier facts into a unified narrative brief
- `UNIFIED_BRIEF_COMPOSITION_PROMPT` encodes 3 eval-proven properties: concrete autobiographical mechanisms, characteristic inner tensions, pragmatic framing
- Anti-anachronism constraint prevents modern professional vocabulary for historical subjects
- `store_unified_brief()` writes `brief_v4.md` with YAML header + Injectable Block format
- `baselayer author --compose` chains composition after layer generation
- Pipeline step count: 13 → 14 (COMPOSE inserted as Step 12)

### MCP + Brief Assembly Unified Brief Preference (S62)
- `get_identity_brief()` (MCP) now tries unified brief first, falls back to three-layer concatenation
- `get_current_identity()` (assemble_brief) adds priority 0 check for unified brief before layers
- Both paths gracefully degrade: unified brief → three layers → "no identity layers found"

### Eval Infrastructure Upgrades (S62)
- **Judge panel:** Multi-model judging (`--judges sonnet/opus/haiku/all`) with per-model output files and consensus scoring (mean across judges, disagreements >1 point flagged)
- **C2-AP ablation:** Anchors+predictions combination added to ablation conditions
- **CM condition:** Claude Memory Import comparison — loads `claude_memories.txt` wrapped in `<userMemories>` XML
- **Length normalization:** `--max-tokens` arg caps response length, per-token-normalized scores in analysis
- **Anachronism check:** Binary PASS/FAIL in public figure judge prompt with specific term listing

### Anti-Anachronism in Predictions (S62)
- Added to both `PREDICTIONS_PROMPT` and `PREDICTIONS_SINGLE_DOMAIN_PROMPT`
- Prohibits modern professional vocabulary (e.g. "optimizes workflows," "leverages synergies") for historical/non-professional subjects

### Testing (S62)
- 27 new tests in `test_unified_brief.py` (319 → 392 total, 365 pre-existing + 27 new)
- Covers: composition prompt properties, store format, MCP preference/fallback, manifest, config, C2-AP ablation, CM condition, judge panel consensus math, anachronism check

---

## 2026-03-01

### Verification + Testing (S57)
- `verify_provenance.py` — vector audit + claim verification + NLI verification
- `baselayer verify` CLI command (vector, claims, individual claim by ID)
- FTS5 full-text search virtual table (`memory_facts_fts`) with auto-sync triggers
- `baselayer rebuild-fts` CLI command for FTS index rebuilding
- Test suite expanded: 85 → 319 tests (test_unit.py, test_edge_cases.py, test_mcp.py, test_privacy.py, test_author_provenance.py, test_checkpoint.py, test_batch_extract.py, test_llm_provider.py)
- `EXTRACTION_CAP_SCALING_REVIEW.md` — implementation review, confirms current caps are sufficient
- `SCORE_FACTS_REFACTOR_PLAN.md` — O(N*M) refactor plan, deferred until 10x scale
- `MULTI_PROVIDER_PLAN.md` — comprehensive multi-provider implementation plan (D-052)
- `README_REVIEW_S57.md` — README draft review

---

## 2026-02-28

### Provenance + Lexicon (S55-S56)
- `layer_claim_provenance` and `claim_verification` database tables with indexes
- `[F-xxx]` fact IDs embedded in authoring prompts for traceability
- `parse_provenance_from_layer()` and `store_provenance()` in author_layers.py — authoring-time capture
- `trace_claim` MCP tool for on-demand provenance queries
- `baselayer provenance` CLI command (summary + `--claim ID` trace)
- `lexicon_schema.yaml` + `lexicon.yaml` created

### Pipeline Upgrades (S55-S56)
- **Relationship extraction:** 8 new predicates (47 total), 30+ aliases, entity map hints — targets 0.8% → 3-5%
- **Extraction cap scaling:** 4-tier (10/20/35/50 facts), input budget (12K-24K chars) based on conversation length
- **Temporal recurrence dedup:** 24h windowing, `windowed_recurrence` column — 20 mentions in one day = 1 recurrence
- **ChromaDB:** L2 → cosine distance metric across 10 files
- **`api_client.py`:** Centralized API singleton + retry + logging, 19 scripts migrated

### Multi-User Validation (S53-S54)
- **User B V4:** 36 newsletter posts → 309 active facts → 77.7/100
- **User C V4:** 9 journal entries → 76 active facts → 81.7/100
- **N=3 proof complete:** conversations, newsletter posts, journal entries — all 77-82/100
- Case study: V4 layers used 26% fewer tokens than raw data with structurally superior responses

### Contamination Fixes (S55)
- Removed hardcoded axioms from store_anchors.py — now file-based loading
- Removed hardcoded inter-axiom conflicts from author_layers.py — derived from actual anchors
- Removed user-specific cluster descriptions from assemble_brief.py
- Fixed extract_facts.py `len(messages) < 2` → `< 1` for single-message journals

### Anonymization (S56)
- 23 Python files + 27 docs files swept for personal data
- `.gitignore` updated for sensitive files
- `entity_map.json`, `PROGRESS.md`, `docs/versions/` excluded from repo

### Code Quality (S55-S56)
- D-059 RESOLVED: Keep trading data (~46% redundancy, needs tighter consolidation)
- Security audit: config path validation, LIKE metacharacter escaping, XML delimiters in extraction prompts
- Entity map `_user_pronouns` field — pronoun-aware layer authoring
- Batch re-extraction DONE (S51) — all 1,892 conversations re-extracted with structured triples
- V4 identity layers DONE (S52) — cycle_003, 78.5/100 Collective score

---

## 2026-02-26

### Structured Extraction (D-056 Tier 2)
- Replaced free-text extraction with structured `{subject, predicate, object, qualifier}` triples
- Constrained predicates enforce keyword-rich, machine-parseable facts (31 at launch, now 47)
- Predicate normalization maps LLM variants to canonical forms
- New database columns: `predicate`, `object_text`, `qualifier`
- `fact_text` reconstructed from structured fields for full downstream compatibility
- Eval harness tested 4 prompt variants on 16 conversations — Variant D scored 85/100 in adversarial review

### Scoring Data Integrity Fix
- Discovered and fixed inflated recurrence scores across all 4,106 facts
- Root cause: generic template language ("The user is interested in...") produced keywords that matched hundreds of unrelated conversations
- Expanded stop words, re-scored entire fact base
- Fixed `sys.stdout` import side effects across 6 scripts that broke test capture

---

## 2026-02-25

### Agent Pipeline for Identity Authoring (D-054)
- Multi-agent identity authoring: Sonnet generates, three isolated Opus agents refine, confer, undergo 4-persona adversarial review, then revise
- True agent isolation — separate context windows, no cross-visibility between layer agents
- 13 artifacts per cycle stored in `data/identity_layers/runs/`
- First cycle deployed as v3: ANCHORS 82.3, CORE 77.3, PREDICTIONS 75.8 (78.4/100 overall)

### Blind Generation and Layer Versioning (D-053)
- Identity layers now generated blind — no prior output shown to the generation model
- Eliminates 26% verbatim anchoring measured when prior output was visible
- Mandatory versioning: every generation stored with full metadata and history naming

### Multi-Provider LLM Support (D-052)
- Provider abstraction layer for Anthropic, Google, OpenAI
- Cross-provider evaluation harness with blind comparison
- Cost analysis across all providers — tier step identified as 64% of pipeline cost

### Identity Evaluation Harness
- 10 test prompts across identity-relevant scenarios
- With-brief vs without-brief vs GPT-native-memory comparison framework
- Paste packets for cross-provider testing

### Domain Balance (D-055)
- 25% category cap prevents any single topic from dominating identity layers
- Reduced trading over-indexing: 39% → 32% in PREDICTIONS, 23% in CORE

---

## 2026-02-25 (Earlier)

### CLI Packaging and MCP Server
- `pip install baselayer` with CLI subcommands (19 at initial packaging, now 25)
- MCP server: identity layers as always-on Resource (~3,500 tokens), `recall_memories` as on-demand Tool, `search_facts` and `get_stats` tools
- `baselayer-mcp` entry point for MCP client configuration

### CORE Prompt Restructuring (D-050)
- CORE layer rewritten as 4-section directive communication guide
- Sections: Communication Approach, Context Modes, Narrative Orientation, Essential Context

### Code Quality Overhaul
- 87 `conn.close` → `contextlib.closing` across 38 files
- Bare excepts eliminated
- MCP thread safety verified
- F-string SQL injection vectors eliminated (0 remaining)

### Evaluation Framework Design
- 6-phase evaluation plan covering brief utilization, regression detection, identity benchmarking
- Confirmed no existing identity benchmarks — KnowMe-Bench (Jan 2026) is closest attempt

### Security and Infrastructure
- Database indexes: 18 applied across all query-heavy tables
- Scope backfill: all 4,106 facts tagged with interaction scope (0 NULL)
- Data isolation via `MEMORY_SYSTEM_ROOT` environment variable for multi-user support

---

## 2026-02-23

### Initial Release
- Full 13-step pipeline: Import → Extract → Embed → Score → Classify → Tier → Contradictions → Consolidate → Anchors → Author → Review → Assemble → Serve
- Multi-source ingestion: ChatGPT exports, Claude Code sessions, Claude web conversations, journals, text files
- AUDN fact lifecycle: Add, Update, Delete, NOOP operations with entity resolution
- Five-dimension classification: fact type, commitment depth, knowledge tier, temporal state, scope
- Three-layer identity architecture: ANCHORS (epistemic axioms), CORE (communication guide), PREDICTIONS (behavioral patterns)
- Automated Collective review: Sonnet self-review + Opus 4-persona adversarial panel
- Contradiction detection: embedding similarity filter + Opus judgment (1,562 pairs judged)
- Enrichment consolidation: union-find clustering with canonical selection
- Brief assembly: ~5,000 tokens in ~100ms, no API calls
- 9 confirmed epistemic axioms
- User correction system with permanent enforcement at extraction time
- Apache 2.0 license
