# Phase 3: Documentation Scan — 2026-03-09

## 3.1 docs/core/ Accuracy

| File | Status | Issues |
|---|---|---|
| ARCHITECTURE.md | partial | Current 4-step pipeline is documented accurately at the top, but the file tree (line ~960-988) lists removed scripts (score_facts.py, classify_facts_haiku.py, reclassify_tiers.py, consolidate_enrichments.py, detect_contradictions.py, store_anchors.py, extract_anchors.py, apply_corrections.py, run_eval.py) as if they are in `scripts/` root — they are actually in `scripts/archive/dead_pipeline_steps/` or `scripts/archive/eval_scripts/`. Line 32 "Memory management runs on local models" is stale (Qwen/Ollama is now optional, not default). assemble_brief.py is referenced as a serving path but is still in scripts/ root. Test count shows 392, current is 414. DECISIONS.md reference in file tree says "59 logged" but there are 76. |
| PROJECT_OVERVIEW.md | current | Updated 2026-03-08 (S80). Accurately describes 4-step pipeline, 47 predicates, 414 tests, 76 decisions, 25 CLI subcommands. Collective marked "ARCHIVED" inline. Classification system section header says "Archived from Full Pipeline." Matches current state. |
| PROGRESS.md | stale | Last entry is Session 77+ (2026-03-07). No entries for Session 79 (pipeline ablation, 14 conditions, C11 best) or Session 80 (V4 compose prompt locked, all 8 subjects recomposed). The introductory architecture overview at the top still lists "Semantic memory — Vector embeddings for retrieval" as a permanent layer, which predates the S79 finding that embedding/scoring are ceremonial. |
| DESIGN_PRINCIPLES.md | partial | Core principles content is philosophically valid and unchanged. However, the "Cheap Constraint, Expensive Discrimination" section (line 337-339) describes the Collective as an active scalability architecture ("If the expensive layer routinely generates content that the cheap layer should have produced, every pipeline run requires an expensive non-deterministic review step") without noting that the Collective was proven ceremonial in S79 and removed from the default pipeline. The section reads as if Collective is still the discriminating layer. Session 38b discussion (line 216) treats Collective-driven ANCHORS improvement as a current authoring model. No reference to ablation findings. |
| DECISIONS.md | partial | Index table lists D-024 (The Collective) as "Active" — should be "Superseded" or "Archived" after S79 ablation proved Collective review adds no measurable value (C11 no-review = 87 vs C0 full pipeline = 83). D-054 (Agent Architecture for Layer Authoring, which includes the Collective) also listed as "Active (implemented)" with no ablation caveat. D-033 ("Claude Code Session Authoring — identity blocks authored in sessions, not via API") is listed as "Active" but the pipeline now uses API-driven authoring (author_layers.py via Sonnet API), which directly contradicts D-033's stated approach. These three index entries are the most misleading staleness in the file. |

### Stale References Found

- `ARCHITECTURE.md` — file tree section (line ~960-988) — lists `score_facts.py`, `classify_facts_haiku.py`, `reclassify_tiers.py`, `consolidate_enrichments.py`, `detect_contradictions.py`, `store_anchors.py`, `extract_anchors.py`, `apply_corrections.py`, `run_eval.py` as `scripts/` root entries — these are now in `scripts/archive/dead_pipeline_steps/` and `scripts/archive/eval_scripts/`

- `ARCHITECTURE.md` — file tree (line 988) — "Test suite (392 tests)" — current count is 414

- `ARCHITECTURE.md` — file tree (line 992) — "Every design decision with reasoning (59 logged)" — current count is 76

- `ARCHITECTURE.md` — line 36 — "loaded by `assemble_brief.py` at runtime" — `assemble_brief.py` is the assembly fallback; the primary serving path is `agent_pipeline.py` + MCP server

- `ARCHITECTURE.md` — line 32 — "Memory management runs on local models" — Qwen/Ollama is optional, not the default path; default extraction is Haiku API

- `ARCHITECTURE.md` — line 985 — file tree describes `agent_pipeline.py` as "D-054: Layer-specific agents + Collective" — the Collective is no longer part of the default pipeline

- `ARCHITECTURE.md` — line 975 — file tree describes `author_layers.py` as "D-043: Three-layer authoring + automated Collective review" — Collective review is removed from default pipeline

- `PROGRESS.md` — introductory architecture overview — lists semantic memory (embed step) as a permanent active layer — this step was proven ceremonial in S79

- `PROGRESS.md` — missing S79 entry — pipeline ablation (14 conditions, C11 wins at 87/100), simplified pipeline proven, Collective review proven ceremonial

- `PROGRESS.md` — missing S80 entry — V4 compose prompt locked, 6 compose variations tested, all 8 subjects recomposed, website Hero restored

- `DESIGN_PRINCIPLES.md` — lines 337-339 — "Cheap Constraint, Expensive Discrimination" section presents the Collective as the active expensive-discrimination layer with no note that it was removed from the default pipeline after S79 ablation

- `DECISIONS.md` — index table D-024 — status "Active" — should be "Superseded/Archived" (Collective review proven ceremonial in S79)

- `DECISIONS.md` — index table D-054 — status "Active (implemented)" — should note that Collective component was removed from default pipeline in S79

- `DECISIONS.md` — index table D-033 — status "Active" — states "Identity blocks authored in sessions, not via API" — contradicts current reality where `author_layers.py` uses Anthropic API (Sonnet) for authoring

---

## 3.2 CLAUDE.md Accuracy

### Accurate

- Pipeline description (4 steps: Import → Extract → Author → Compose) matches current reality
- Script table core entries: `cli.py`, `mcp_server.py`, `config.py`, `agent_pipeline.py`, `author_layers.py`, `extract_facts.py`, `import_conversations.py`, `api_client.py`, `verify_provenance.py` — all exist in `scripts/` root
- "DO NOT" section is current and matches known constraints
- Key technical facts section is accurate (brief = final artifact, anonymization layer, document mode, extraction chunking, ChromaDB L2 distance, Haiku classification fix)
- Session protocol is appropriate
- Model usage guidance (Sonnet/Opus split) is accurate
- Active work items reflect current state

### Inaccurate (for Aarik's attention)

| Section | Current Content | What's Wrong |
|---|---|---|
| Key Scripts table | `classify_facts_haiku.py` listed as active | This script is in `scripts/archive/dead_pipeline_steps/` — not in `scripts/` root. Should be removed or marked archived. |
| Key Scripts table | `reclassify_tiers.py` listed as active | This script is in `scripts/archive/dead_pipeline_steps/` — not in `scripts/` root. Should be removed or marked archived. |
| Key Scripts table | `run_eval.py` / `run_validation_study.py` listed as active | Both are in `scripts/archive/eval_scripts/` — not in `scripts/` root. Should be removed or marked archived. |
| Key Scripts table | `provenance_eval.py` listed as active | This script is in `scripts/archive/eval_scripts/` — not in `scripts/` root. |
| Key Scripts table | `assemble_brief.py` listed as "Brief assembly — unified brief preferred, three-layer fallback" | The file exists in `scripts/` root, but this description implies it is a primary serving path. The primary path is `agent_pipeline.py` + `mcp_server.py`. `assemble_brief.py` is a fallback. Minor framing issue. |

---

## 3.3 Active Script Docstrings

| Script | Docstring Status | Issues |
|---|---|---|
| import_conversations.py | current | Module docstring accurately describes multi-source import (ChatGPT, Claude Code, Claude web). No references to removed steps. No decision refs at all. Clean. |
| extract_facts.py | stale | Module docstring (lines 1-19) describes the script as "Phase 4, Step 4" using the old 14-step numbering. Steps 1-5 in the docstring describe Qwen 2.5 14B as the extractor ("Extract candidate facts using Qwen 2.5 14B", "Ask Qwen for AUDN decision") and Ollama schema enforcement (D-010) as the primary mechanism. Default extraction is now Haiku API; Qwen/Ollama is the optional local path. The docstring describes the old local-first architecture, not the current API-first default. Line 1880 runtime print also outputs "Phase 4, Step 4" to the console during runs. |
| author_layers.py | current | Module docstring accurately describes three-layer authoring (ANCHORS, CORE, PREDICTIONS), CLI modes, and design constraints (D-040, D-041, D-043, D-044, D-046). No reference to Collective review in the docstring. No stale step numbering. Clean. |
| agent_pipeline.py | current | Module docstring accurately describes unified brief composition from 3 layers. Cites Franklin eval (S61) as evidence. No stale step numbering, no removed-step references. Clean. |

---

## 3.4 Decision References in Active Code

| File:Line | Decision | Context | Still Accurate |
|---|---|---|---|
| extract_facts.py:2 | D-005, D-010, D-013 | Module docstring — "Phase 4, Step 4" header | D-005 (AUDN lifecycle): yes. D-010 (JSON validation guardrails): partially — the schema enforcement was for Ollama; the Haiku API path uses different validation. D-013 (co-occurrence edges): yes, still implemented. |
| extract_facts.py:7 | (implied D-010) | "Extract candidate facts using Qwen 2.5 14B" — Qwen is described as primary extractor | No — Haiku API is the default. Qwen/Ollama is optional. |
| extract_facts.py:11 | D-013 | "Link co-occurring facts (D-013: associative retrieval)" | Yes — function `link_co_occurring_facts()` is still present and called. |
| extract_facts.py:54 | D-010 | "JSON Schemas for Ollama (D-010: schema enforcement)" — the comment implies Ollama is the primary path | Partially stale — these schemas are used for the Ollama path only, but the comment reads as if Ollama is primary. |
| extract_facts.py:57 | D-056 | "Tier 2: Structured extraction schema with constrained predicates" | Yes — accurate. |
| extract_facts.py:414 | D-039 | "Normalize knowledge tier classification (D-039)" | D-039 is a classification/tiering step that was proven ceremonial in S79 ablation. The function exists and assigns tiers to extracted facts, but the downstream tiering pipeline (reclassify_tiers.py) is archived. The tier normalization in extraction is benign (schema compliance) but referencing it as an active design decision without noting the tiering pipeline is archived is mildly misleading. |
| extract_facts.py:708 | D-021 | "User corrections — permanent record that survives extraction resets (D-021)" | Yes — correction guard logic is still active. |
| extract_facts.py:865 | D-021 | "Correction Guard (D-021: Fix Once, Fixed Forever)" | Yes — still accurate. |
| extract_facts.py:990 | D-048 | "Build the identity-focused extraction prompt for project conversations (D-048)" | Yes — still accurate. |
| extract_facts.py:1327 | (comment) | "D-077+: Raised from 15 — let AUDN handle dedup, not caps" | References D-077 which does not exist in the DECISIONS.md index (decisions go to D-076). Either a forward reference or a typo. |
| author_layers.py:2 | D-043 | Module docstring — "Three-Layer Identity Block Authoring Pipeline (D-043)" | Yes — accurate. |
| author_layers.py:24-28 | D-040, D-041, D-043, D-044, D-046 | Design constraints in docstring | Yes — all accurate. D-040 (blind authoring), D-041 (audience principle), D-043 (three-layer), D-044 (scoped memory), D-046 (cheap constraint/expensive discrimination). |
| author_layers.py:311 | D-055 | "Trading facts spread across..." domain balance | Yes — domain balance cap is still in the retrieval logic. |
| author_layers.py:566 | D-041 | "GENERATION PROMPTS — D-041 encoded (updated Session 44)" | Yes — accurate. |
| author_layers.py:684 | D-041 | "D-041 FILTER — Before including ANY detail..." | Yes — accurate. |
| author_layers.py:979 | D-046 | "Generate a layer via Anthropic API (Sonnet by default, per D-046)" | Yes — accurate. |
| author_layers.py:1850 | D-053 | "Versioning scheme (D-053)" | Yes — versioning logic is active. |
| import_conversations.py | (none) | No decision references found | N/A |
| agent_pipeline.py | (none) | No decision references found | N/A |

### Decision References Flagging Removed Pipeline Steps

- `extract_facts.py:414` — D-039 (Knowledge Tier Classification): referenced as active normalization, but the downstream tiering pipeline (`reclassify_tiers.py`) is archived. Tier assignment during extraction populates a schema column but the promotion step is gone. This is accurate at the code level (the column is still populated) but the decision's stated purpose — progressive refinement feeding layer authoring — is no longer operative.

- `extract_facts.py:1327` — "D-077+" comment: D-077 does not appear in the DECISIONS.md index (which ends at D-076). Either a forward-looking placeholder or a numbering error.

---

## Summary

Documentation health is mixed. The two most public-facing docs (`ARCHITECTURE.md` and `PROJECT_OVERVIEW.md`) are in reasonably good shape — both were updated on 2026-03-08 and correctly describe the 4-step pipeline. However, both still carry legacy content in their lower sections.

The most significant gaps are: (1) `PROGRESS.md` has no entries for S79 or S80 — the two most consequential sessions in the project's history (ablation proof and V4 compose) are entirely absent; (2) `DECISIONS.md` index marks D-024 (The Collective) as "Active" and D-033 ("authored in sessions, not via API") as "Active," both of which contradict current reality; (3) `extract_facts.py`'s module docstring describes Qwen 2.5 14B as the primary extractor using Ollama — this was the architecture before Haiku API became the default, and the mismatch is visible at runtime (console prints "Phase 4, Step 4"); (4) `CLAUDE.md` lists four scripts as active (`classify_facts_haiku.py`, `reclassify_tiers.py`, `run_eval.py`, `provenance_eval.py`) that are archived and no longer in `scripts/` root.

No active pipeline scripts reference decisions about genuinely removed steps in a load-bearing way — the D-039 tier normalization reference is the closest, and it is benign. The one anomaly is the "D-077+" comment in `extract_facts.py` referencing a decision number that does not exist in the log.
