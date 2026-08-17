# Base Layer: Project Overview
**Updated 2026-05-06**

---

Base Layer is the interpretive layer above memory. Memory systems store what a person has said and what they prefer; this system captures the framework those things come from, and serves it as a portable artifact called a behavioral specification.

**Why it is built.** An AI agent can only act in alignment with how a specific person would act to the extent it represents how they reason. The specification is that representation. The architecture below is what produces and serves it.

This document describes the system from the inside: what the major components are, how they compose, and what each one is responsible for. For product context and onboarding, read [`README.md`](../../README.md). For the canonical pipeline description, read [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## What it is

A pipeline plus a serving surface. The pipeline takes text (conversations, journals, essays, letters, any first-person source) and produces a structured 5,000 to 10,000 token behavioral specification of how the author interprets information, decides, and communicates. The serving surface exposes that specification, and the underlying fact graph it was authored from, to consuming clients via MCP, an HTTP API, and direct paste-in.

The specification is not a profile, a memory store, or a fact database. It is a set of behavioral patterns extracted from the source text and compressed into a form an AI can consume as context. It composes with retrieval rather than replacing it: retrieval supplies the relevant facts for a question, the specification supplies how the specific person would interpret those facts.

2. **Fact Extraction:** Structured fact extraction with 46 constrained predicates (45 behavioral plus an `unknown` fallback). Produces `{subject, predicate, object, qualifier}` triples from any text source.

3. **Specification Authoring:** Facts compressed into a three-layer specification using H3 prompts (Session 99 ablation — domain-agnostic guard eliminates topic skew):
   - **Epistemic Anchors:** Core axioms that define reasoning foundations. Cross-scope, always-on.
   - **Operational Constraints (CORE):** Directive-format communication approach, context modes, narrative orientation, essential context. Always-on.
   - **Behavioral Predictions:** Situation-triggered response patterns with detection signatures and interaction directives. Structured output format validated (D-093). Always-on.

4. **Brief Composition:** Three layers compressed into a unified narrative brief (~3,000-5,000 tokens). Compose prompt enforces they/them pronouns (D-092) and domain guard (D-091). Served via MCP (Model Context Protocol) as an always-on specification Resource.

5. **Reasoning Model:** Any LLM receives the brief and responds with understanding. Stateless, interchangeable.

### Three-Layer Specification Architecture

The specification is authored in three independent layers, each with its own source data and authoring process:

| Layer | Source | Content |
|---|---|---|
| **ANCHORS** | Epistemic axioms extracted from conviction-level facts, confirmed by user | Reasoning foundations the model applies before situation-specific context arrives |
| **CORE** | Identity-tier facts organized by type | Directive communication guide: how to interact, what context modes exist, essential background |
| **PREDICTIONS** | Behavioral identity-tier facts | Situation-triggered patterns: when X happens, this person tends to Y, so do Z |

**Authoring constraints:**
- **Blind generation:** Layers authored from facts only. No prior output shown to the generation model. Prevents anchoring (measured at 26% verbatim carryover when violated).
- **Audience principle:** The audience is the intelligence and understanding the AI needs to take on to communicate naturally with the individual. Every sentence must change how the AI behaves.
- **Independent authoring:** Three layers authored independently, then reviewed for cross-layer coherence.
- **Mandatory versioning:** Every generation stored with full metadata. Layer diffs over time represent identity evolution signal.

### Adversarial Review Pipeline (The Collective), ARCHIVED

The original pipeline included a multi-agent adversarial review process ("The Collective" — four AI personas evaluating specification layers from different angles: accuracy, completeness, tone, behavioral utility). Pipeline ablation (Session 79, 14 conditions on Benjamin Franklin's autobiography, [results](../eval/ablation/)) demonstrated that skipping Collective review produced higher-quality briefs (87/100 vs 83/100 for the full 14-step pipeline). The review step is preserved in the codebase but is no longer part of the default pipeline.

### Model Roles

| Role | Model | What it does |
|---|---|---|
| **Extraction** | Haiku (API) | Structured fact extraction with 46 constrained predicates + 98 normalization aliases |
| **Generation** | Sonnet (API) | Three-layer specification authoring from extracted facts |
| **Composition** | Opus (API) | Compresses 3 layers into unified narrative brief |
| **Brief assembly** | Pure code | Loads and serves final brief. No LLM in the critical path. ~100ms. |

Each step uses the cheapest model that can do the job. Embedding, scoring, classification, tiering, and contradiction detection were part of the original 14-step pipeline but proved ceremonial in ablation testing (Session 79, [results](../eval/ablation/)).

### Data Architecture

- **Data sovereignty:** All conversations, facts, embeddings, and specification layers stored on the user's machine. No cloud database, no sync, no telemetry.
- **API processing (default):** Conversation text sent to API for extraction and classification. Nothing stored remotely; the API processes and returns results.
- **Local processing (exploring):** Architecture designed for cloud removal as local models improve. Local extraction available today via Ollama for users with GPU. Full local pipeline on the roadmap.
- **Brief delivery:** Only the assembled brief (~5,000 tokens) reaches the reasoning model. No raw conversations, no embeddings, no personal database.

---

## Pipeline (5 Steps)

Pipeline ablation (Session 79) tested 14 conditions on Benjamin Franklin (autobiography) and proved that 10 of the original 14 steps were ceremonial (scoring, classification, tiering, contradiction detection, consolidation, anchor extraction, and collective review added no measurable value). The simplified pipeline scores higher (87/100 vs 83/100) while costing less. Embed remains as the provenance step: vectors are required for claim-to-fact tracing.

```
STEP 1:  IMPORT        — Multi-source importer (ChatGPT, Claude, journals, text files)
STEP 2:  EXTRACT       — Text → structured triples {subject, predicate, object, qualifier} (Haiku API)
STEP 3:  EMBED         — Facts → local vectors (MiniLM-L6-v2, ChromaDB) for provenance tracing
STEP 4:  AUTHOR        — Facts → three-layer specification generation (Sonnet, H3 prompts with domain guard)
STEP 5:  COMPOSE       — 3 layers → unified narrative brief (~3,000-5,000 tokens) (Opus, they/them + domain guard)
```

**One command:** `baselayer run <file>` runs steps 1-5 automatically with cost estimate gate.

The 47 predicates are grouped into five categories: epistemic (`believes`, `values`, `prioritizes`), operational (`practices`, `avoids`, `struggles_with`, `monitors`, `builds`), affective (`fears`, `enjoys`, `loves`), relational (`relates_to`, `collaborates_with`, `follows`), and temporal (`experienced`, `decided`, `aspires_to`). The full schema lives at `lexicon_schema.yaml`.

The graph is the source of truth. Every later artifact derives from it. Re-authoring the specification on the same graph yields a different draft but draws from the same evidence.

### Three-layer authoring

The specification is authored in three independent layers, each from facts only. Each layer answers a different question and is generated blind, with no prior layer's output shown to the authoring model. Blind generation prevents anchoring (measured at 26 percent verbatim carryover when violated).

---

## Classification System (Archived from Full Pipeline)

The original pipeline classified facts across 5 dimensions. Ablation testing (Session 79) showed these classification steps are ceremonial — the authoring step produces equivalent or better results working directly from extracted facts. The schema remains in the database for research use.

| Dimension | Values | Purpose |
|---|---|---|
| **fact_type** | biographical, behavioral, positional, preference | Routes facts to specification layers |
| **commitment_depth** | factual, preference, position, conviction | Filters by strength of belief |
| **knowledge_tier** | identity, situational, context | Progressive refinement — identity tier feeds layer authoring |
| **temporal_state** | current, past, unknown | Contradiction vulnerability detection |
| **scope** | personal, project, professional | Interaction mode routing |

---

## Design Principles

1. **Inherent Incompleteness** — The system will never fully know the person. Confidence is warranted; certainty never is.
2. **Data Sovereignty** — All personal data stays on the user's machine. Only compressed briefs reach the reasoning model.
3. **Surprise-Based Writes** — Only store what's novel relative to existing knowledge.
4. **Always-On Specification** — Behavioral model present in every conversation. Three-layer architecture, each layer authored independently.
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
| **Tier 2: Core + Anchors** | Full specification layers | $3-5 per run | Full pipeline through layer authoring. ANCHORS + CORE + PREDICTIONS as injectable markdown. Delivered via MCP or manual paste. |
| **Tier 3: Full Pipeline** | Open-source self-hosted | Free (BYOS) | Complete 5-step pipeline. Installed from the git URL, 27 CLI subcommands. User provider choice, full data control. |

Each layer carries its own guarantees. Anchors are stable across sessions; the model treats them as given. Core is consulted whenever the person is being addressed; it shapes tone and approach. Predictions activate when a situation matches a trigger; they inform what to do, not what to say.

The three layers compose by accumulation, not by overwrite. A consumer that needs only the foundational orientation can use Anchors alone. A consumer that needs full behavioral fidelity loads all three.

### Composition

The three layers feed a composition stage that compresses them into a single unified specification of 5,000 to 10,000 tokens. Composition is not summarization; it is selection. The composer keeps the patterns that are predictive across situations and drops the ones that only fire in narrow contexts. Pronouns are normalized to third-person plural. A domain-agnostic guard prevents the output from skewing toward whatever topic dominated the source corpus.

The unified specification is the artifact most consumers will use. The three underlying layers remain accessible for clients that want finer control or want to inspect why the specification says what it says.

### Compression is load bearing

A 5 to 10K token specification recovers most of the predictive accuracy of the full source corpus at 5 to 80 times smaller context. Selecting and structuring the behavioral signal does the work, not summarizing. A different person's specification applied to this subject drops accuracy below the no-context baseline; the matched content is what carries the lift.

---

## Pipeline at a glance

Five stages. The full canonical description is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

| Stage | What it does | Model |
|---|---|---|
| **IMPORT** | Multi-source ingest (ChatGPT, Claude, journals, plain text, document mode) into a normalized SQLite schema. Incremental. | None |
| **EXTRACT** | 47 constrained predicates over the source text produce structured triples. AUDN lifecycle: Add, Update, Delete, Noop. | Haiku (or Ollama, local) |
| **EMBED** | Local MiniLM-L6-v2 embeddings for every fact and message, stored in ChromaDB. Required for provenance and serve-time retrieval. | Local |
| **AUTHOR** | Three-layer generation from facts only. Domain-agnostic guard prevents topic skew. Layers authored blind. | Sonnet |
| **COMPOSE** | Three layers compressed into a unified specification. They/them pronouns enforced. Domain guard reapplied. | Opus |

`baselayer run <file>` executes all five stages with a cost-estimate gate before any spend. The CLI also exposes each stage independently for users who want step-by-step control or who are iterating on a single stage.

Cost is bounded. Roughly $0.30 to $2.00 for corpora ranging from 100 to 1,000 conversations.

---

## Serving

A consuming agent talks to the system through one of three surfaces. They expose the same artifacts; they differ in where the integration sits.

### MCP server

`baselayer-mcp` runs over stdio. Wired into Claude Desktop, Claude Code, or Cursor it adds:

**Resources** (always available, client controlled):
- `memory://identity`. The full specification plus the three underlying layers. Loaded into context whenever the client deems appropriate.

**Tools** (model controlled, called on demand):
- `recall_memories(query)`. Semantic retrieval over the fact graph and source messages.
- `search_facts(query, limit)`. Keyword search over active facts with metadata.
- `trace_claim(claim_id)`. For a specific claim in the specification, return the supporting facts and the source passages those facts were extracted from.
- `verify_claims(claim_id, layer)`. Run the four-check verifier against one claim or a whole layer.
- `get_stats()`. Database summary: conversation count, fact count, tier breakdown, source breakdown.

The Resource is what most agents will use most of the time. The Tools are what an agent reaches for when it wants to ground a claim in evidence or pull a specific fact.

### HTTP API

For consumers that do not speak MCP, the same data is served as JSON:

```
GET /api/identity/<subject>            full specification + layers + stats
GET /api/identity/<subject>/anchors    anchors only
GET /api/identity/<subject>/core       core only
GET /api/identity/<subject>/predictions predictions only
```

Live example specifications (no auth required) are at [base-layer.ai](https://base-layer.ai). The OpenAPI spec is at `/api/openapi.json`. An agent card at `/.well-known/agent-card.json` and an MCP server card at `/.well-known/mcp/server-card.json` cover machine-readable discovery.

### Direct paste

The specification is plain structured text. Pasted into Claude custom instructions, ChatGPT project files, or any system prompt, it works without any additional integration. This is the lowest-friction surface and the one most users start from.

---

## Provenance and auditability

Every claim in a generated specification cites the facts used to author it. Every fact cites the source passage it was extracted from. Together these form a citation graph from any sentence in the specification back to the conversation or document line it ultimately came from.

`baselayer verify` runs four checks against that graph:

| Check | What it measures |
|---|---|
| Total subjects on dashboard | 92+ |
| Subjects H3-authored | 44 |
| Thinkers pages live (base-layer.ai) | 29 (17 Wave 4/5 ready to seed) |
| Pipeline refactor | COMPLETE (S98-S99). H3 prompts adopted. |
| Wave 4/5 subjects seeded | 17 (ready for outreach) |
| Anthropic targets scraped | 3 subjects |
| Active facts (User A — primary test user, 1,892 ChatGPT conversations) | 4,610 |
| Identity-tier facts (User A) | 2,684 |
| Conversations imported | 1,892 (primary test user, multi-source) |
| Messages | 40,997 |
| Epistemic axioms (User A) | 11 |
| Design decisions logged | 93 |
| Design principles | 14 |
| Classification accuracy | 91.2% type, 93.8% depth |
| Brief assembly time | ~100ms |
| Brief token budget | ~3,000-5,000 tokens (unified narrative brief) |
| Pipeline steps | 5 (simplified from 14 in S79) |
| Authoring prompts | H3 (domain-agnostic guard, S99 ablation) |
| CLI subcommands | 27 |
| MCP tools | 8 tools + 2 resources (one a deprecated alias) |
| Constrained predicates | 46 (45 behavioral + `unknown` fallback) + 98 aliases |
| Build sessions | 100 |
| Tests passing | 451 |
| GPU extraction | mistral:7b best (59 facts, 232s); authoring still requires API |
| Stacking test | 100 responses, 5 conditions (C4 project leakage finding) |
| Auth | Magic link (7-day tokens, Redis-backed, Route Handler pattern) + password fallback |
| Dashboard | Textual TUI (sortable, scrollable, tier display, auto-refresh) |

---

## Where it sits relative to memory systems

### Key Completed Milestones
- **Pipeline ablation** — DONE (Session 79): 14 conditions on Franklin, ~$16. Proved 10 of 14 steps ceremonial. Simplified to 4-step pipeline.
- **H3 prompt ablation** — DONE (Session 99): 4 rounds, 10 conditions. 73-word domain guard eliminated topic skew entirely. H3 adopted as production prompt set.
- **Pipeline refactor** — DONE (Session 98-99): Codebase refactor complete. Extraction gate, H3 prompts, compose fixes (they/them, domain guard).
- **N=10 validation** — DONE: User A, User B, User C, Franklin, Douglass, Wollstonecraft, Roosevelt, Patents, Warren Buffett (48 shareholder letters), Howard Marks (74 investment memos). All scored 73-82/100.
- **Twin-2K-500 benchmark** — DONE (N=100): 71.83% accuracy at 18:1 compression, p=0.008.
- **BCB-0.1 Franklin** — DONE: 2 pass, 2 fail, 1 invalid. DRS (Dialectical Robustness Score) penalizes fidelity.
- **Provenance eval framework** — DONE (Session 77): Mechanical BA+PC layers, $0 cost, human-auditable.
- **Website** — LIVE at [base-layer.ai](https://base-layer.ai). 29 thinkers pages, thoughts page, research page with authoring ablation published. Magic link auth (Route Handler pattern), feedback mechanism, version history UI.
- **Privacy scrub + git push** — DONE (Session 81): 0 security blockers.
- **44 subjects H3-authored** — All subjects recomposed with H3 prompts and compose fixes (0 he/him, 0 topic skew).
- **17 Wave 4/5 subjects seeded** — Ready for outreach.
- **Serving layer spec** — DONE (Session 99): `docs/core/SERVING_LAYER_SPEC.md`. Activation matching for brief-to-context relevance.
- **Cross-discipline research** — DONE (Session 99): 10 findings across 7 academic domains mapped to Base Layer architecture.
- **93 design decisions, 14 principles, 27 CLI subcommands, 100 build sessions.**

What is left unmeasured is interpretation: how a specific person processes facts and experiences into judgments, decisions, and reactions. The same facts can yield different conclusions depending on whose interpretive framework reads them.

### Next
- **Temporality research** — Time-aware specification modeling. Temporal prediction test spec drafted.

1. **Retrieval-only questions.** The memory system has the answer in storage. The specification adds nothing. Use retrieval alone.
2. **Interpretation-heavy questions.** The retrieved facts underdetermine the answer. The specification supplies the pattern that has to transfer to the new situation. Layer the specification on top of retrieval.
3. **Refusal-triggering questions.** When the specification supports principled refusal because the person genuinely does not have the information, it produces honest abstention rather than hedging or fabrication.

A serving system that routes between retrieval and interpretation by question type is an active research thread. Until that lands, the specification layered on top of retrieval covers the gap.

One empirical note worth carrying. Given identical input, the four leading memory systems return substantially non-overlapping top-10 facts (mean pairwise overlap 8.3 percent across ten system pairs). Providers converge on recall scores. They do not converge on which facts matter. Interpretation is a different problem from the one those systems are solving.

---

## Project status

Pre-1.0. The pipeline runs end to end, the MCP server is live, and example specifications are served at base-layer.ai.

| Item | State |
|---|---|
| License | Apache 2.0 |
| Tests | 400+ passing |
| CLI | `baselayer` with 25 subcommands plus `baselayer run` one-command pipeline |
| MCP | Resource plus 5 tools over stdio |
| Storage | SQLite + ChromaDB, all local |
| Extraction | Haiku via Anthropic API; Ollama for fully local extraction |
| Authoring / composition | Sonnet / Opus via Anthropic API |
| Repository | [agulaya24/BaseLayer](https://github.com/agulaya24/BaseLayer) |
| Site | [base-layer.ai](https://base-layer.ai) |

For the catalogued design choices and their rationale, see [`DECISIONS.md`](DECISIONS.md). For the principles those decisions ladder up to, see [`DESIGN_PRINCIPLES.md`](DESIGN_PRINCIPLES.md). For the prompts themselves, read the source. Nothing is hidden.

Active research threads include 32B-class local models for a fully local pipeline, a serving system that routes by question type, faithfulness as its own measurement axis distinct from compactness and predictive accuracy, and per-component ablation across anchors, core, and predictions.
