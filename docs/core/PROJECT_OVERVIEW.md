# Base Layer — Project Overview
**Updated 2026-03-08 (Session 80)**

---

## What This Is

A personal AI memory system that extracts what matters from your conversation history, builds a compressed behavioral model of who you are, and injects that understanding into every AI conversation. The AI responds as if it knows you — without being told every time.

All data stored on the user's machine. Processing uses cloud APIs by default, with local deployability being actively explored as local models improve.

## Core Idea

Modern LLMs are powerful but stateless. Every conversation starts from zero. Base Layer adds a durable understanding layer: extract facts from conversations, author a compressed identity brief, and inject it as context. The result is persistent understanding without replaying history or running up token costs.

Base Layer is a structured reasoning process that produces understanding. The identity brief isn't a profile — it's a chain of thought that teaches an AI how to understand and communicate naturally with a specific person.

**North star:** perceived alignment — AI responses reflecting an accurate behavioral model of the user.

---

## System Architecture

### Core Layers

1. **Ground-Truth Memory** — All conversations stored locally in SQLite. Nothing is ever deleted. This is the source of truth.

2. **Fact Extraction** — Structured fact extraction with 47 constrained predicates. Produces `{subject, predicate, object, qualifier}` triples from any text source.

3. **Identity Authoring** — Facts compressed into a three-layer identity brief:
   - **Epistemic Anchors** — Core axioms that define reasoning foundations. Cross-scope, always-on.
   - **Communication & Operating Guide (CORE)** — Directive-format communication approach, context modes, narrative orientation, essential context. Always-on.
   - **Behavioral Predictions** — Situation-triggered response patterns with detection signatures and interaction directives. Always-on.

4. **Brief Composition** — Three layers compressed into a unified narrative brief (~3,500 tokens). Served via MCP as an always-on identity Resource.

5. **Reasoning Model** — Any LLM receives the brief and responds with understanding. Stateless, interchangeable.

### Three-Layer Identity Architecture

The identity brief is authored in three independent layers, each with its own source data and authoring process:

| Layer | Source | Content |
|---|---|---|
| **ANCHORS** | Epistemic axioms extracted from conviction-level facts, confirmed by user | Reasoning foundations the model applies before situation-specific context arrives |
| **CORE** | Identity-tier facts organized by type | Directive communication guide — how to interact, what context modes exist, essential background |
| **PREDICTIONS** | Behavioral identity-tier facts | Situation-triggered patterns — when X happens, this person tends to Y, so do Z |

**Authoring constraints:**
- **Blind generation** — Layers authored from facts only. No prior output shown to the generation model. Prevents anchoring (measured at 26% verbatim carryover when violated).
- **Audience principle** — The audience is the intelligence and understanding the AI needs to take on to communicate naturally with the individual. Every sentence must change how the AI behaves.
- **Independent authoring** — Three layers authored independently, then reviewed for cross-layer coherence.
- **Mandatory versioning** — Every generation stored with full metadata. Layer diffs over time represent identity evolution signal.

### Adversarial Review Pipeline (The Collective) — ARCHIVED

The original pipeline included a multi-agent adversarial review process (The Collective) for identity layers. Pipeline ablation (Session 79, 14 conditions on Franklin) demonstrated that skipping Collective review produced higher-quality briefs (87/100 vs 83/100 for the full 14-step pipeline). The review step is preserved in the codebase but is no longer part of the default pipeline.

### Model Roles

| Role | Model | What it does |
|---|---|---|
| **Extraction** | Haiku (API) | Structured fact extraction with 47 constrained predicates + 30+ aliases |
| **Generation** | Sonnet (API) | Three-layer identity authoring from extracted facts |
| **Composition** | Opus (API) | Compresses 3 layers into unified narrative brief |
| **Brief assembly** | Pure code | Loads and serves final brief. No LLM in the critical path. ~100ms. |

Each step uses the cheapest model that can do the job. Embedding, scoring, classification, tiering, and contradiction detection were part of the original 14-step pipeline but proved ceremonial in ablation testing (Session 79).

### Data Architecture

- **Data sovereignty:** All conversations, facts, embeddings, and identity layers stored on the user's machine. No cloud database, no sync, no telemetry.
- **API processing (default):** Conversation text sent to API for extraction and classification. Nothing stored remotely — the API processes and returns results.
- **Local processing (exploring):** Architecture designed for cloud removal as local models improve. Local extraction available today via Ollama for users with GPU. Full local pipeline on the roadmap.
- **Brief delivery:** Only the assembled brief (~5,000 tokens) reaches the reasoning model. No raw conversations, no embeddings, no personal database.

---

## Pipeline (4 Steps)

Pipeline ablation (Session 79) tested 14 conditions on Franklin and proved that 10 of the original 14 steps were ceremonial — scoring, classification, tiering, contradiction detection, consolidation, anchor extraction, and collective review added no measurable value. The simplified 4-step pipeline scores higher (87/100 vs 83/100) while costing less.

```
STEP 1:  IMPORT        — Multi-source importer (ChatGPT, Claude, journals, text files)
STEP 2:  EXTRACT       — Text → structured triples {subject, predicate, object, qualifier} (Haiku API)
STEP 3:  AUTHOR        — Facts → three-layer identity generation (Sonnet)
STEP 4:  COMPOSE       — 3 layers → unified narrative brief (~3,500 tokens) (Opus)
```

**One command:** `baselayer run <file>` runs steps 1-4 automatically with cost estimate gate.

The 3-layer architecture (ANCHORS / CORE / PREDICTIONS) IS load-bearing — C11 (3 layers, no review) scored 87 vs C13 (single layer) at 83. The intermediate processing steps are not.

<details>
<summary>Original 14-step pipeline (archived)</summary>

The full 14-step pipeline remains available in the codebase for research purposes:

```
STEP 1:  IMPORT        — Multi-source conversation importer
STEP 2:  EXTRACT       — Conversations → structured triples with entity resolution
STEP 3:  EMBED         — Facts + messages → vector embeddings (local)
STEP 4:  SCORE         — Novelty + significance scoring
STEP 5:  CLASSIFY      — Fact type + commitment depth classification
STEP 6:  TIER          — Knowledge tier assignment (identity / situational / context)
STEP 7:  CONTRADICTIONS — Embedding similarity → LLM judgment → superseded_by pointers
STEP 8:  CONSOLIDATE   — Union-find clustering → canonical selection → deduplication
STEP 9:  ANCHORS       — Conviction facts → candidate axioms → user confirmation
STEP 10: AUTHOR LAYERS — Fact retrieval → three-layer identity generation
STEP 11: REVIEW        — Adversarial multi-agent review pipeline
STEP 12: COMPOSE       — Opus compresses 3 layers → unified narrative brief
STEP 13: ASSEMBLE      — Unified brief preferred, three-layer fallback
STEP 14: SERVE         — MCP server: identity as always-on Resource
```
</details>

---

## Classification System (Archived from Full Pipeline)

The original pipeline classified facts across 5 dimensions. Ablation testing (Session 79) showed these classification steps are ceremonial — the authoring step produces equivalent or better results working directly from extracted facts. The schema remains in the database for research use.

| Dimension | Values | Purpose |
|---|---|---|
| **fact_type** | biographical, behavioral, positional, preference | Routes facts to identity layers |
| **commitment_depth** | factual, preference, position, conviction | Filters by strength of belief |
| **knowledge_tier** | identity, situational, context | Progressive refinement — identity tier feeds layer authoring |
| **temporal_state** | current, past, unknown | Contradiction vulnerability detection |
| **scope** | personal, project, professional | Interaction mode routing |

---

## Design Principles

1. **Inherent Incompleteness** — The system will never fully know the person. Confidence is warranted; certainty never is.
2. **Data Sovereignty** — All personal data stays on the user's machine. Only compressed briefs reach the reasoning model.
3. **Surprise-Based Writes** — Only store what's novel relative to existing knowledge.
4. **Always-On Identity** — Behavioral model present in every conversation. Three-layer architecture, each layer authored independently.
5. **Confidence Over Deletion** — Knowledge is never deleted, only confidence-adjusted or superseded. Full history preserved.
6. **Silence Is Not Evidence of Irrelevance** — Conversation frequency reflects AI usage, not personal importance.
7. **Contradiction Over Decay** — Staleness detected by contradiction, not elapsed time. No TTL, no access-frequency scoring.
8. **User as Highest Authority** — When the system disagrees with the user about who they are, the system defers.
9. **Behavioral Modeling, Not Fact Retrieval** — The brief contains predictions about how the user thinks and decides, not raw data.
10. **Faithful Compression** — Compressed representations must faithfully reflect the underlying fact base. Correct behavior from incorrect understanding is a failure mode, not a success.

---

## Distribution Model

### Three-Tier Product Architecture (Session 59 — CANDIDATE)

| Tier | Product | Price | What the User Gets |
|---|---|---|---|
| **Tier 1: Preferences** | Structured preferences for paste-in | Free | Minimal pipeline (extract + classify). Exports formatted preferences for Claude/ChatGPT/Gemini native preference UI. Primary onboarding path. |
| **Tier 2: Core + Anchors** | Full identity layers | $3-5 per run | Full pipeline through layer authoring. ANCHORS + CORE + PREDICTIONS as injectable markdown. Delivered via MCP or manual paste. |
| **Tier 3: Full Pipeline** | Open-source self-hosted | Free (BYOS) | Complete 4-step pipeline. `pip install baselayer`, 25 CLI subcommands. User provider choice, full data control. |

**Cost structure (per user):** Full pipeline ~$0.52-3.33/user. Simple preferences ~$0.17-0.47/user. At 100 users: ~$106 (full) or ~$35 (simple preferences).

**Provider-agnostic pipeline (CANDIDATE):** For Tier 1-2, the pipeline internally benchmarks Anthropic, OpenAI, and Google per step and selects the optimal cost/quality combination. Users don't choose a provider. Tier 3 retains user provider choice.

Multi-provider support is under development — full-suite provider paths with blind evaluation required before any provider ships as supported.

### Competitive Context

**Claude Memory Import (March 2026):** Anthropic launched claude.com/import-memory, exporting flat facts from ChatGPT/Gemini into Claude's native memory. This commoditizes flat fact transfer. Base Layer's differentiation: structured behavioral modeling (ANCHORS + CORE + PREDICTIONS) produces understanding that flat fact imports cannot.

Local deployability is being actively explored. The architecture is designed for progressive cloud removal as local model capabilities improve. Today: local extraction available via Ollama. Tomorrow: full local pipeline.

---

## Current State

| Metric | Value |
|---|---|
| Active facts (User A) | 4,610 |
| Active facts (User B) | 309 |
| Active facts (Subject B) | 76 |
| Active facts (Franklin) | 212 (135 identity-tier) |
| Active facts (Douglass) | 88 (51 identity-tier) |
| Active facts (Wollstonecraft) | 95 (81 identity-tier) |
| Active facts (Roosevelt) | 398 (264 identity-tier) |
| Identity-tier facts (User A) | 2,684 |
| Conversations imported | 1,892 (multi-source) |
| Messages | 40,997 |
| Epistemic axioms (User A) | 11 |
| Design decisions logged | 76 |
| Classification accuracy | 91.2% type, 93.8% depth |
| Brief assembly time | ~100ms |
| Brief token budget | ~3,723 tokens (unified narrative brief) |
| CLI commands | 25 |
| MCP tools | 5 tools + 1 resource |
| Constrained predicates | 47 + 30 aliases |
| External subjects validated | 10 (User A, User B, User C, Franklin, Douglass, Wollstonecraft, Roosevelt, Patents, Buffett, Marks) |
| Build sessions | 80+ |
| V4 Collective score (User A) | 78.5/100 |
| V4 Collective score (User B) | 77.7/100 |
| V4 Collective score (Subject B) | 81.7/100 |
| Tests passing | 414 |

---

## What's Next

### Key Completed Milestones
- **Pipeline ablation** — DONE (S79): 14 conditions on Franklin, ~$16. Proved 10 of 14 steps ceremonial. Simplified to 4-step pipeline.
- **N=10 validation** — DONE: User A, User B, User C, Franklin, Douglass, Wollstonecraft, Roosevelt, Patents, Buffett, Marks. All scored 73-82/100.
- **Twin-2K-500 benchmark** — DONE (N=100): 71.83% accuracy at 18:1 compression, p=0.008.
- **BCB-0.1 Franklin** — DONE: 2 pass, 2 fail, 1 invalid. DRS penalizes fidelity.
- **Provenance eval framework** — DONE (S77): Mechanical BA+PC layers, $0 cost, human-auditable.
- **Website** — LIVE at base-layer.ai. 4 routes (Home, Journey, Examples, Try It).
- **414 tests, 76 design decisions, 25 CLI subcommands.**

### Active
- **Privacy scrub + git push** — See `GIT_PUSH_PREP.md`. Fresh repo planned.
- **Pipeline validation** — Re-running simplified 4-step pipeline across all subjects.
- **Paul Graham case study** — 28 essays ready. Pipeline run pending.
- **Self-referential case study** — Run Base Layer on its own documentation.

### Post-Launch
- **ADRB benchmark** — 40 tasks, 7 conditions. ~$30 minimum.
- **Dissenting opinion benchmark (D-076)** — Novel contribution.
- **Brief structure update (D-075)** — Add HOW + WHERE IT BREAKS to composition step.

---

## Repository

Open source under Apache 2.0.

GitHub: https://github.com/baselayer/baselayer.git
