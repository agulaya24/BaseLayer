# Changelog

All notable changes to Base Layer are documented here.

---

## Unreleased

### Planned
- **D-056 Tier 3** — Quality gate between extraction and storage (reject hedging, low-density, LLM artifacts)
- **Cross-provider blind evaluation** — Claude / ChatGPT / Gemini comparison
- **Fact correction UI/CLI** — `baselayer correct` command to flag, edit, or supersede individual facts. Current `user_corrections` table exists but has no user-facing interface. Triggered by S62 finding: aspirational facts ("aspires to provide for wife and future children" rec:93) and situational facts ("lives in Victoria" rec:24) were promoted into identity layers as confident biographical claims. Need: (1) CLI to list/search/edit/supersede facts by ID, (2) corrections cascade to layers on next authoring cycle, (3) hybrid verification — heuristic term-match + Haiku semantic check on composed brief vs source facts

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
