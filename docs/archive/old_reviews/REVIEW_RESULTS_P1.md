# Phase 1: Code Inventory — 2026-03-09

## 1.1 Active Scripts

Scripts at `scripts/` root level (treated as active):

```
__init__.py
__main__.py
add_indexes.py
agent_pipeline.py          ← Step 4: Compose (active pipeline)
api_client.py
assemble_brief.py          ← FLAG: "removed step" but still active (see 1.4)
author_layers.py           ← Step 3: Author Layers (active pipeline)
batch_extract.py
checkpoint.py
cli.py
config.py
contradiction_ablation.py  ← Experimental (S81 study)
contradiction_threshold_test.py  ← Experimental (S81 study)
create_turn_pairs.py
detect_contradictions.py   ← Experimental (integrated into compose path)
embed.py
extract_facts.py           ← Step 2: Extract (active pipeline)
generate_tension_data.py
generate_docx.py
import_conversations.py    ← Step 1: Import (active pipeline)
init_database.py
llm_provider.py
mcp_server.py
monitor.py
query.py
semantic_search.py
summarize.py
ui.py
verify_provenance.py
```

Also present at root level (not in archive):
```
experiments/__init__.py
experiments/ollama_utils.py
experiments/exp_predicate_expansion.py
experiments/exp_chunking_variations.py
experiments/exp_extraction_prompts.py
experiments/exp_embedding_models.py
experiments/exp_contradiction_detection.py
experiments/exp_identity_formalization.py
experiments/exp_temporality.py
```

## 1.1 Archived Scripts

Scripts under `scripts/archive/` (all treated as archived):

**dead_pipeline_steps/**
```
batch_classify.py
batch_pipeline.py
batch_tier.py
classify_facts_haiku.py
consolidate_enrichments.py
dedup_facts.py
detect_contradictions.py   ← NOTE: duplicate name with root-level script
extract_anchors.py
reclassify_tiers.py
score_facts.py
store_anchors.py
surprise_scoring.py
```

**eval_scripts/**
```
collaboration_bcb.py
eval_classify_opus_judge.py
eval_classify_round3.py
eval_cross_provider.py
eval_extraction.py
expanded_identity_ablation.py
gpu_overnight_s78.py
marks_bcb_prompts.py
overnight_gpu.py
pipeline_ablation.py
pipeline_ablation_fix.py
predicate_ablation.py
provenance_eval.py
run_all_overnight.py
run_eval.py
run_identity_eval.py
run_overnight.py
run_overnight_s78.py
run_validation_study.py
sonnet_validation.py
twin2k_download.py
twin2k_migrate_db.py
twin2k_parser.py
twin2k_pipeline.py
twin2k_predict.py
twin2k_score.py
twin2k_v4_rerun.py
voice_ablation.py
voice_downstream_eval.py
```

**one_off/**
```
apply_corrections.py
backfill_fact_class.py
backfill_knowledge_tier.py
backfill_scope.py
brief_optimization.py
coverage_merge_adversarial.py
recompose_all.py
regen_with_feedback.py
review_briefs.py
review_project.py
test_classify_prompt.py
test_compose_variations.py
test_contradiction.py
test_contradiction_detection.py
test_knowledge_tier.py
test_significance.py
```

**archive root/**
```
experiments.py
ingest.py
```

## 1.1 Duplicates (in both locations)

**`detect_contradictions.py`** — exists at both:
- `scripts/detect_contradictions.py` (root, active)
- `scripts/archive/dead_pipeline_steps/detect_contradictions.py` (archived)

These are NOT the same file. The archived version is the old implementation using ChromaDB. The root version is a new S81 rewrite using direct embedding (no ChromaDB, Haiku classification, tension predicate pairs). Different docstrings and implementation. The naming collision is a clarity hazard but not a functional bug.

## 1.2 Dead Imports

**`scripts/cli.py` — lines 334, 342**
```python
import assemble_brief
```
`assemble_brief` is listed as a removed pipeline step in the spec, but it is still imported at runtime by two active CLI subcommands (`brief` and `chat`). This is an active dependency, not a dead import in the traditional sense — the import works because `assemble_brief.py` still exists at root level. However, `assemble_brief` is architecturally dead per S79 simplification (the `compose` command in `agent_pipeline.py` replaced it as the primary brief artifact). The `brief` and `chat` subcommands still depend on it for MCP serving and interactive use.

**`scripts/mcp_server.py` — lines 188-189**
```python
from assemble_brief import get_theme_block, get_episode_block
```
Same issue — `assemble_brief` is imported by the MCP server for theme/episode retrieval in the `recall` tool. This is a live runtime dependency, not dead code, but `assemble_brief` is architecturally a removed step. The MCP server's retrieval path still runs the old block-assembly logic.

**No other dead imports found in active scripts.** All four core pipeline scripts (import_conversations, extract_facts, author_layers, agent_pipeline) import only from `config.py`, `api_client.py`, `llm_provider.py`, and stdlib. No references to `score_facts`, `classify_facts_haiku`, `reclassify_tiers`, or any dead step modules.

## 1.3 Hardcoded Paths

**`scripts/generate_tension_data.py` — lines 15-24 — SEVERITY: HIGH**

Eight hardcoded absolute Windows paths as module-level constants:
```python
"franklin":      "C:/Users/Aarik/Anthropic/subjects/franklin_memory",
"douglass":      "C:/Users/Aarik/Anthropic/subjects/douglass_memory",
"wollstonecraft":"C:/Users/Aarik/Anthropic/subjects/wollstonecraft_memory",
"roosevelt":     "C:/Users/Aarik/Anthropic/subjects/roosevelt_memory",
"patents":       "C:/Users/Aarik/Anthropic/subjects/patent_memory",
"buffett":       "C:/Users/Aarik/Anthropic/buffett_memory",
"marks":         "C:/Users/Aarik/Anthropic/marks_memory",
OUTPUT_FILE = "C:/Users/Aarik/Anthropic/baselayer-website/data/tensionData.ts"
```
This script will fail for any user other than Aarik on this machine. Subject paths should come from a subjects registry or env vars. Output path should be relative or configurable. This script is not part of the 4-step pipeline but is a website data generation utility — pre-launch public release would break it for all contributors.

**`scripts/experiments/ollama_utils.py` — line 74 — SEVERITY: MEDIUM (experiments only)**
```python
"C:/Users/Aarik/Anthropic/subjects/franklin_memory/data/database/memory.db"
```
Hardcoded inside an experiment utility. Breaks for other users but `experiments/` is not part of the released pipeline.

**`scripts/experiments/exp_embedding_models.py` — line 40 — SEVERITY: MEDIUM (experiments only)**
```python
"C:/Users/Aarik/Anthropic/subjects/franklin_memory/data/database/memory.db"
```

**`scripts/experiments/exp_temporality.py` — lines 44, 46 — SEVERITY: MEDIUM (experiments only)**
```python
"C:/Users/Aarik/Anthropic/memory_system/data/database/memory.db"
"C:/Users/Aarik/Anthropic/memory_system_v4/data/database/memory.db"
```

**`scripts/experiments/exp_contradiction_detection.py` — line 36 — SEVERITY: MEDIUM (experiments only)**
```python
"C:/Users/Aarik/Anthropic/subjects/franklin_memory/data/database/memory.db"
```

**`scripts/experiments/exp_identity_formalization.py` — lines 72-73 — SEVERITY: MEDIUM (experiments only)**
```python
("franklin", "C:/Users/Aarik/Anthropic/subjects/franklin_memory/data/database/memory.db"),
("aarik",    "C:/Users/Aarik/Anthropic/memory_system/data/database/memory.db"),
```

**All four pipeline scripts (import_conversations, extract_facts, author_layers, agent_pipeline), `cli.py`, `checkpoint.py`, `mcp_server.py`, `assemble_brief.py`, and `config.py` contain NO hardcoded absolute paths.** All paths derive from `config.py`'s `PROJECT_ROOT` via the `MEMORY_SYSTEM_ROOT` env var resolution chain.

## 1.4 References to Removed Steps

### Active References (bugs or architectural debt)

**`scripts/cli.py` — lines 334-344**
`cmd_brief` and `cmd_chat` both import and invoke `assemble_brief.main()`. These are exposed CLI subcommands (`baselayer brief`, `baselayer chat`). If `assemble_brief.py` were removed, these two subcommands would break at runtime. `assemble_brief` is listed as a removed step in the simplification, but it was not removed from disk and the CLI still routes to it.

**`scripts/mcp_server.py` — lines 188-189**
`from assemble_brief import get_theme_block, get_episode_block` — the MCP server's `recall` tool uses these functions to retrieve dynamic theme and episode context. This is a live code path: any call to the MCP recall tool executes into `assemble_brief.py`.

**`scripts/agent_pipeline.py` — line 524, 609, 620**
`from config import LAYER_REVIEW_MODEL` — this constant is named for the (removed) Collective review step, but it is actively used in `compose_unified_brief()` as the model for the compose call (Opus). The constant is not dead — it is the compose model. The name is misleading but the usage is correct. Flagged as technical debt, not a bug.

**`scripts/detect_contradictions.py` — line 40**
`from config import CONTRADICTION_SIMILARITY_THRESHOLD` — this constant is marked "ARCHIVED" in `config.py` but is actively imported and used by the root-level `detect_contradictions.py` script. That script is integrated into the S81 contradiction ablation study. Whether "contradiction detection" is a removed step or a new experimental step is architecturally ambiguous — the CLAUDE.md spec removed the old detect_contradictions from the pipeline, but a new version was written and kept at root. If this is intentionally part of the active pipeline, the config.py ARCHIVED label is wrong. If it's only for experiments, it should move to `experiments/`.

**`scripts/contradiction_ablation.py` — line 154**
`from config import LAYER_REVIEW_MODEL` — same misleading name issue as agent_pipeline. Used as the judge model in the ablation pairwise evaluation. Active usage.

### Passive References (informational)

**`scripts/config.py` — lines 166, 337, 348, 442, 445**
Comments and section headers referencing removed scripts by name (`surprise_scoring.py`, `score_facts.py`, `reclassify_tiers.py`, `consolidate_enrichments.py`, Collective review). All are in comment/docstring context only. Not code.

**`scripts/extract_facts.py` — line 1103**
String `"collective review"` appears in an exclusion filter list (AUTHORING_EXCLUSION_PATTERNS applied during extraction to skip meta-references). This is a data value used to filter fact text, not a code import. Correct passive use.

**`scripts/config.py` — line 378**
Comment `"block mentions, decision references, collective review mentions"` describes the exclusion pattern list. Passive.

**`scripts/config.py` — lines 430, 436-437**
Comment text references `"Collective review"` in the LAYER_REVIEW_MODEL docstring. Passive.

## 1.5 Stale Constants in config.py

The config.py file is well self-annotated. Constants in the `=== ARCHIVED ===` sections are explicitly labeled. Below is a verification of each.

### Potentially Stale (unused in active pipeline scripts)

**`NOVELTY_SKIP`, `NOVELTY_STORE`** (lines 160-161)
- Labeled ARCHIVED. Only consumed by `scripts/archive/dead_pipeline_steps/surprise_scoring.py`.
- Verified unused in all active root-level scripts.
- Stale: **YES**

**`RECURRENCE_FLOOR_HIGH`, `RECURRENCE_FLOOR_MID`, `RECURRENCE_FLOOR_HIGH_SCORE`, `RECURRENCE_FLOOR_MID_SCORE`, `RECURRENCE_MIN_SPAN_DAYS`** (lines 173-177)
- Labeled ARCHIVED. Only consumed by `surprise_scoring.py` and `score_facts.py` (both archived).
- Verified unused in all active root-level scripts.
- Stale: **YES**

**`WEIGHT_NOVELTY`, `WEIGHT_RECURRENCE`, `WEIGHT_DEPTH`** (lines 188-190)
- Labeled ARCHIVED. Only consumed by `surprise_scoring.py` (archived).
- Verified unused in all active root-level scripts.
- Stale: **YES**

**`RECLASSIFY_MODEL`, `RECLASSIFY_BATCH_SIZE`** (lines 343-344)
- Labeled ARCHIVED. Consumed by `reclassify_tiers.py`, `batch_tier.py`, and `consolidate_enrichments.py` (all archived).
- Verified unused in all active root-level scripts.
- Stale: **YES**

**`CONSOLIDATION_MAX_CLUSTER_SIZE`** (line 354)
- Labeled ARCHIVED. Consumed only by `consolidate_enrichments.py` (archived).
- Verified unused in all active root-level scripts.
- Stale: **YES**

**`CONTRADICTION_SIMILARITY_THRESHOLD`** (line 333)
- Labeled ARCHIVED. Consumed by `scripts/detect_contradictions.py` (root-level, active) AND `archive/dead_pipeline_steps/detect_contradictions.py` (archived).
- The root-level `detect_contradictions.py` imports this constant at line 40 and uses it as the default similarity threshold.
- **This constant is NOT stale** — it is actively imported by a root-level script.
- The ARCHIVED label in config.py is **incorrect** given this active usage.
- Resolution needed: either relabel this constant as active, or move the threshold into `detect_contradictions.py` directly if that script is experimental.

**`REVIEW_DEPLOY_THRESHOLD`, `REVIEW_MAX_ITERATIONS`, `REVIEW_IMPROVEMENT_MIN`, `REVIEW_MIN_FACTS_FOR_GENERATION`, `REVIEW_SELF_REVIEW_GATE`, `REVIEW_TIER_THIN`, `REVIEW_TIER_STANDARD`** (lines 448-456)
- Labeled ARCHIVED (Collective review pipeline).
- Verified unused in all active root-level scripts. `author_layers.py` does NOT import any of these.
- Stale: **YES**

**`LAYER_REVIEW_MODEL`** (line 438)
- Labeled as dead in comment ("ARCHIVED — review models dead after pipeline simplification").
- HOWEVER: actively imported and used in `agent_pipeline.py` (compose model) and `contradiction_ablation.py` (judge model).
- **This constant is NOT stale** — it is functionally active. The constant's name is misleading (describes the old review role, now used as compose model), but it maps to Opus via `LLM_PROVIDER_CONFIG["review"]`, which is the correct model for composition.
- The ARCHIVED label is **incorrect**.

**`LAYER_SELF_REVIEW_MODEL`** (line 439)
- Labeled as dead in comment alongside LAYER_REVIEW_MODEL.
- Grepping all active root-level scripts: **no active imports found**.
- Stale: **YES**

### Potentially Active Constants Labeled Correctly

**`RECURRENCE_NORMALIZATION_CEILING`, `RECURRENCE_WINDOW_HOURS`** (lines 256-257)
- Not labeled ARCHIVED despite being used primarily by the scoring step.
- Grep confirms: not imported by any active root-level pipeline script.
- These appear to exist only for the archived `score_facts.py`. Should be labeled ARCHIVED.
- Currently **unlabeled but stale**.

### Missing Constants

**Subject registry** — `generate_tension_data.py` hardcodes 7 subject paths as a dict literal (lines 15-22). There is no subjects registry in `config.py`. Any script that needs to iterate over subjects must either hardcode paths or read them ad-hoc. This is a gap: a `SUBJECTS_DIR` or `KNOWN_SUBJECTS` constant in config.py would let `generate_tension_data.py` and similar scripts resolve subject environments portably via env var.

**Output paths for website data** — `generate_tension_data.py` line 24 hardcodes the website data output path. No constant in config.py for website output directories. Low priority (not part of user-facing pipeline) but should not be hardcoded.

---

## Summary

Phase 1 reveals a clean core pipeline (the four main scripts are disciplined) with four areas of concern:

**1. assemble_brief.py is not actually removed.** It was declared a removed step but remains at root level and is actively depended on by two CLI subcommands (`baselayer brief`, `baselayer chat`) and the MCP server's recall tool (`get_theme_block`, `get_episode_block`). This is the largest architectural gap: the "simplified" pipeline still has `assemble_brief` in the serving path. Either these subcommands should be rewritten to use the unified brief, or `assemble_brief` should be explicitly kept and labeled as the MCP/serving layer rather than a "removed pipeline step."

**2. generate_tension_data.py has 8 hardcoded absolute paths** that will fail on any machine other than Aarik's. This is the most urgent pre-launch blocker from a portability standpoint among active scripts.

**3. config.py has two mislabeled constants.** `LAYER_REVIEW_MODEL` is labeled ARCHIVED but is actively used as the compose model in `agent_pipeline.py`. `CONTRADICTION_SIMILARITY_THRESHOLD` is labeled ARCHIVED but is imported by root-level `detect_contradictions.py`. Seven other archived constants (`NOVELTY_*`, `WEIGHT_*`, `RECLASSIFY_*`, etc.) are correctly labeled and truly unused by active scripts. Two constants (`RECURRENCE_NORMALIZATION_CEILING`, `RECURRENCE_WINDOW_HOURS`) are stale but not labeled as such.

**4. detect_contradictions.py at root level has ambiguous status.** It is a rewrite of the archived contradiction step, but it is not wired into the 4-step pipeline per the CLAUDE.md spec. It functions as experiment infrastructure (used by `contradiction_ablation.py` and `contradiction_threshold_test.py`) rather than a dead code artifact. It should be explicitly classified — either integrated into the pipeline (and the spec updated) or moved to `experiments/`.
