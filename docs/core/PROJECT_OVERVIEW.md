# Base Layer: Project Overview
**Updated 2026-08-18**

---

Base Layer is the interpretive layer above memory. Memory systems store what a person has said and what they prefer; this system captures the framework those things come from, and serves it as a portable artifact called a behavioral specification.

**Why it is built.** An AI agent can only act in alignment with how a specific person would act to the extent it represents how they reason. The specification is that representation. The architecture below is what produces and serves it.

This document describes the system from the inside: what the major components are, how they compose, and what each one is responsible for. For product context and onboarding, read [`README.md`](../../README.md). For the canonical pipeline description, read [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## What it is

A pipeline plus a serving surface. The pipeline takes text (conversations, journals, essays, letters, any first-person source) and produces a structured behavioral specification, a few thousand tokens, describing how the author interprets information, decides, and communicates. The serving surface exposes that specification, and the underlying fact graph it was authored from, to consuming clients via MCP, an HTTP API, and direct paste-in.

The specification is not a profile, a memory store, or a fact database. It is a set of behavioral patterns extracted from the source text and compressed into a form an AI can consume as context. It composes with retrieval rather than replacing it: retrieval supplies the relevant facts for a question, the specification supplies how the specific person would interpret those facts.

1. **Ingestion.** Multi-source import (ChatGPT and Claude exports, journals, plain text, directories) normalized into conversations and messages in SQLite.

2. **Fact extraction.** Structured extraction with 46 constrained predicates (45 behavioral plus an `unknown` fallback) and 98 normalization aliases. Produces `{subject, predicate, object, qualifier}` triples from any text source.

3. **Specification authoring.** Facts written into a three-layer specification using the H3 prompt set, adopted after the Session 99 ablation in which a domain-agnostic guard eliminated topic skew:
   - **Epistemic Anchors:** core axioms that define reasoning foundations. Cross-scope, always on.
   - **Operational Constraints (CORE):** directive-format communication approach, context modes, narrative orientation, essential context. Always on.
   - **Behavioral Predictions:** situation-triggered response patterns with detection signatures and interaction directives. Structured output format validated in D-093. Always on.

4. **Brief composition.** The three layers compressed into a unified narrative brief. The compose prompt enforces they/them pronouns (D-092) and a domain guard (D-091). Served via MCP as an always-on Resource.

5. **Reasoning model.** Any LLM receives the brief and responds with understanding. Stateless, interchangeable.

### Three-layer specification architecture

The specification is authored in three independent layers, each with its own source data and authoring process:

| Layer | Source | Content |
|---|---|---|
| **ANCHORS** | Epistemic axioms extracted from conviction-level facts, confirmed by user | Reasoning foundations the model applies before situation-specific context arrives |
| **CORE** | Identity-tier facts organized by type | Directive communication guide: how to interact, what context modes exist, essential background |
| **PREDICTIONS** | Behavioral identity-tier facts | Situation-triggered patterns: when X happens, this person tends to Y, so do Z |

**Authoring constraints:**
- **Blind generation.** Layers are authored from facts only; no prior output is shown to the generation model. This prevents anchoring, measured at 26 percent verbatim carryover when violated.
- **Audience principle.** The audience is the intelligence and understanding the AI needs to take on to communicate naturally with the individual. Every sentence must change how the AI behaves.
- **Independent authoring.** Three layers authored independently, then reviewed for cross-layer coherence.
- **Mandatory versioning.** Every generation is stored with full metadata. Layer diffs over time represent identity evolution signal.

### Adversarial review pipeline (The Collective), archived

The original pipeline included a multi-agent adversarial review process ("The Collective": four AI personas evaluating specification layers for accuracy, completeness, tone, and behavioral utility). Pipeline ablation (Session 79, 14 conditions on Benjamin Franklin's autobiography, [results](../eval/ablation/)) showed that skipping Collective review produced higher-quality briefs (87/100 vs 83/100 for the full 14-step pipeline). The review step is preserved in the codebase but is no longer part of the default pipeline.

### Model roles

| Role | Model | What it does |
|---|---|---|
| **Extraction** | Haiku (API) | Structured fact extraction with the 46 constrained predicates and 98 normalization aliases |
| **Generation** | Sonnet (API) | Three-layer specification authoring from extracted facts |
| **Composition** | Opus (API) | Compresses the three layers into the unified narrative brief |
| **Brief assembly** | Pure code | Loads and serves the finished brief. No LLM in the critical path. ~100ms. |

Each step uses the cheapest model that can do the job. Scoring, classification, tiering, and contradiction detection were part of the original 14-step pipeline but proved ceremonial in ablation testing (Session 79, [results](../eval/ablation/)).

### Data architecture

- **Data sovereignty:** All conversations, facts, embeddings, and specification layers are stored on the user's machine. No cloud database, no sync, no telemetry.
- **API processing (default):** Conversation text is sent to the API for extraction and authoring. Nothing is stored remotely; the API processes and returns results.
- **Local processing (exploring):** The architecture is designed for cloud removal as local models improve. Local extraction is available today via Ollama for users with a GPU. A fully local pipeline is on the roadmap.
- **Brief delivery:** Only the assembled brief, a few thousand tokens, reaches the reasoning model. No raw conversations, no embeddings, no personal database.

---

## Pipeline

Pipeline ablation (Session 79) tested 14 conditions on Benjamin Franklin's autobiography and found that 10 of the original 14 steps added no measurable value: scoring, classification, tiering, contradiction detection, consolidation, anchor extraction, and collective review among them. The simplified pipeline scored higher (87/100 vs 83/100) while costing less.

What ships in this repository today:

```
IMPORT     import_conversations.py   any supported source into a normalized SQLite schema
EXTRACT    extract_facts.py          text into structured triples, 46 predicates (Haiku)
AUTHOR     author_layers.py          facts into the three specification layers (Sonnet)
COMPOSE                              three layers into one unified brief (Opus)
EMBED      embed.py                  facts into local vectors (all-MiniLM-L6-v2, ChromaDB); a side branch
```

`baselayer run <file>` executes the whole chain behind a cost-estimate gate, and every stage is also exposed as its own CLI command for step-by-step control. Cost is roughly $0.30 to $2.00 for corpora between 100 and 1,000 conversations.

**EMBED is a side branch, not a step authoring depends on.** The authoring stage selects its input facts with SQL queries against the database; it never reads ChromaDB. In `baselayer run`, embedding executes after authoring and composition, as part of the traceability step. The vectors serve semantic search, `baselayer verify`, and the vector-provenance fallback described under Provenance below.

The 46 predicates are grouped into five categories: epistemic (`believes`, `values`, `prioritizes`), operational (`practices`, `avoids`, `struggles_with`, `monitors`, `builds`), affective (`fears`, `enjoys`, `loves`), relational (`relates_to`, `collaborates_with`, `follows`), and temporal (`experienced`, `decided`, `aspires_to`). The full schema lives at `lexicon_schema.yaml`.

The graph is the source of truth. Every later artifact derives from it. Re-authoring the specification on the same graph yields a different draft but draws from the same evidence.

### The authoring cap, and the pipeline that replaces it

The AUTHOR stage in this repository hands each layer a fixed slice of facts, capped at 15 facts per category (`MAX_FACTS_PER_CATEGORY`, `author_layers.py:307`). The cap keeps one topic from dominating a fixed-size prompt, but it discards evidence by sort position rather than importance: on one measured 407-fact corpus, the CORE author received 141 of the 407 facts, so about 65 percent of that layer's corpus never reached the model.

Interpretive distillation is the experimental successor built to remove that cap. Instead of selecting facts, it summarizes all of them: the corpus is chunked, each chunk is distilled, and the distillates are assembled into one package per layer, so the layer author sees every fact in compressed form and no fact is dropped silently. Each chunk's distillate carries four channels: themes naming the fact ids they drew on; one-off facts carried word for word and never merged; disagreements kept unresolved; and one verdict per fact id, where omitting an id is not permitted.

Measured under a profiler on 2026-08-18, the distillation pipeline runs as:

```
IMPORT     import_conversations.py                        text into SQLite
EXTRACT    extract_facts.py (claude-haiku-4-5)            facts, 46 predicates
DISTILL    distill.py (claude-sonnet-5, --max-facts 120)  one tree per layer
ASSEMBLE   assemble.py                                    one package per layer
AUTHOR     author_from_package.py (claude-opus-5)         layers, with citations required by schema
COMPOSE                                                   one brief
EMBED      embed.py                                       side branch, same role as above
```

DISTILL runs once per layer (`--layer` takes `anchors`, `core`, or `predictions`), so a full build is three distill runs, three assembles, and one author pass. On a 149-fact corpus: DISTILL took 44 seconds and $0.04, ASSEMBLE 0.1 seconds at no cost, AUTHOR plus COMPOSE 83 seconds and $0.14. $0.18 in total.

Distillation ships in this repository as the experimental subpackage `baselayer.distillation` (`baselayer distill` / `assemble` / `author-from-package`); its test coverage is 10 mutation tests over one audit, so read `docs/core/DISTILLATION.md` before depending on it. This repository still ships the capped author as the default.

---

## Classification system (archived from the full pipeline)

The original pipeline classified facts across 5 dimensions. Ablation testing (Session 79) showed these classification steps are ceremonial: the authoring step produces equivalent or better results working directly from extracted facts. The schema remains in the database for research use.

| Dimension | Values | Purpose |
|---|---|---|
| **fact_type** | biographical, behavioral, positional, preference | Routes facts to specification layers |
| **commitment_depth** | factual, preference, position, conviction | Filters by strength of belief |
| **knowledge_tier** | identity, situational, context | Progressive refinement; identity tier feeds layer authoring |
| **temporal_state** | current, past, unknown | Contradiction vulnerability detection |
| **scope** | personal, project, professional | Interaction mode routing |

---

## Design principles

1. **Inherent incompleteness.** The system will never fully know the person. Confidence is warranted; certainty never is.
2. **Data sovereignty.** All personal data stays on the user's machine. Only compressed briefs reach the reasoning model.
3. **Surprise-based writes.** Only store what is novel relative to existing knowledge.
4. **Always-on specification.** The behavioral model is present in every conversation. Three-layer architecture, each layer authored independently.
5. **Confidence over deletion.** Knowledge is never deleted, only confidence-adjusted or superseded. Full history preserved.
6. **Silence is not evidence of irrelevance.** Conversation frequency reflects AI usage, not personal importance.
7. **Contradiction over decay.** Staleness is detected by contradiction, not elapsed time. No TTL, no access-frequency scoring.
8. **User as highest authority.** When the system disagrees with the user about who they are, the system defers.
9. **Behavioral modeling, not fact retrieval.** The brief contains predictions about how the user thinks and decides, not raw data.
10. **Faithful compression.** Compressed representations must faithfully reflect the underlying fact base. Correct behavior from incorrect understanding is a failure mode, not a success.

---

## Distribution model

### Three-tier product architecture (Session 59, candidate)

| Tier | Product | Price | What the user gets |
|---|---|---|---|
| **Tier 1: Preferences** | Structured preferences for paste-in | Free | Minimal pipeline (extract + classify). Exports formatted preferences for Claude/ChatGPT/Gemini native preference UI. Primary onboarding path. |
| **Tier 2: Core + Anchors** | Full specification layers | $3-5 per run | Full pipeline through layer authoring. ANCHORS + CORE + PREDICTIONS as injectable markdown. Delivered via MCP or manual paste. |
| **Tier 3: Full Pipeline** | Open-source self-hosted | Free (BYOS) | Complete pipeline, installed from the git URL, 25 CLI subcommands. User provider choice, full data control. |

Each layer carries its own guarantees. Anchors are stable across sessions; the model treats them as given. Core is consulted whenever the person is being addressed; it shapes tone and approach. Predictions activate when a situation matches a trigger; they inform what to do, not what to say.

The three layers compose by accumulation, not by overwrite. A consumer that needs only the foundational orientation can use Anchors alone. A consumer that needs full behavioral fidelity loads all three.

### Composition

The three layers feed a composition stage that compresses them into a single unified specification a few thousand tokens long. Composition is not summarization; it is selection. The composer keeps the patterns that are predictive across situations and drops the ones that only fire in narrow contexts. Pronouns are normalized to third-person plural. A domain-agnostic guard prevents the output from skewing toward whatever topic dominated the source corpus.

The unified specification is the artifact most consumers will use. The three underlying layers remain accessible for clients that want finer control or want to inspect why the specification says what it says.

### Compression is load bearing

A compact specification recovers most of the predictive accuracy of the full source corpus at 5 to 80 times smaller context. Selecting and structuring the behavioral signal does the work, not summarizing. A different person's specification applied to this subject scores about the same as the no-context baseline, no better and no worse; the matched content is what carries the lift.

---

## Serving

A consuming agent talks to the system through one of three surfaces. They expose the same artifacts; they differ in where the integration sits.

### MCP server

`baselayer-mcp` runs over stdio. Wired into Claude Desktop, Claude Code, or Cursor it adds:

**Resources** (always available, client controlled):
- `memory://specification`. The full specification plus the three underlying layers, loaded into context whenever the client deems appropriate.
- `memory://identity`. A deprecated alias for `memory://specification`. It returns the same content and will be removed in a future release.

**Tools** (model controlled, called on demand):
- `recall_memories(query)`. Semantic retrieval over the fact graph and source messages.
- `search_facts(query, limit)`. Keyword search over active facts with metadata.
- `trace_claim(claim_id)`. For a specific claim in the specification: the supporting facts, the source passages those facts were extracted from, and how each claim-to-fact link was established.
- `verify_claims(claim_id, layer)`. Runs the five binary claim checks (existence, recurrence, cross-domain span, temporal consistency, internal contradiction) against one claim or a whole layer. It does not run the vector audit or the NLI check; those are available only through `baselayer verify`.
- `get_stats()`. Database summary: conversation count, fact count, tier breakdown, source breakdown.
- `get_brief(reason)`. Returns the unified narrative brief on demand.
- `get_help(topic)`. Agent-facing help for operating and troubleshooting the server.
- `get_call_log()`. Recent tool and resource calls, so a user can see what the system has been doing.

The specification Resource is what most agents will use most of the time. The tools are what an agent reaches for when it wants to ground a claim in evidence or pull a specific fact.

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

Every claim in a generated specification links to facts, and every fact cites the source passage it was extracted from. Together these form a graph from any sentence in the specification back to the conversation or document line it ultimately came from.

The claim-to-fact links come in two kinds, and `trace_claim` labels each link with its kind:

- **Citation links** (`link_method` of `authoring` or `citation_api`): the author cited the fact while writing the claim.
- **Vector links** (`link_method` of `vector`): the claim carried no citation, so it was linked afterward to its nearest facts by meaning. In the current author, ANCHORS and PREDICTIONS produce no citations, so their links are vector links. A vector link means the fact is nearby in meaning; it does not mean the fact was used to author the claim.

`baselayer verify` audits the graph. The default run is a vector-proximity audit plus five binary claim checks; NLI entailment is opt-in:

| Check | What it measures | Default |
|---|---|---|
| Vector proximity | Does the claim sit near its linked facts in embedding space | yes |
| Existence | Does every cited fact resolve to an active, non-superseded fact | yes |
| Recurrence | Does any claim rest on a single one-off mention | yes |
| Cross-domain span | Do the cited facts span more than one topic area | yes |
| Temporal consistency | Are any cited facts stale or marked future-state | yes |
| Internal contradiction | Do any cited facts supersede each other | yes |
| NLI entailment | A local DeBERTa model scores whether the cited facts support the claim | `--nli` only, downloads ~700MB |

This is a data-quality audit, not a causal-traceability guarantee. A resolving citation proves the reference is real. It does not prove the fact drove the claim, and only ablation tests that.

---

## Where it sits relative to memory systems

Memory providers converge on recall scores and diverge on judgment. Given identical input, leading memory systems return substantially non-overlapping top-10 facts (mean pairwise overlap 8.3 percent across system pairs in the project's memory-systems study). They agree on how to store and retrieve; they do not agree on which facts matter. What none of them measure is interpretation: how a specific person processes facts and experiences into judgments, decisions, and reactions. The same facts can yield different conclusions depending on whose interpretive framework reads them.

That difference splits consumer questions three ways:

1. **Retrieval-only questions.** The memory system has the answer in storage. The specification adds nothing. Use retrieval alone.
2. **Interpretation-heavy questions.** The retrieved facts underdetermine the answer. The specification supplies the pattern that has to transfer to the new situation. Layer the specification on top of retrieval.
3. **Refusal-triggering questions.** When the specification supports principled refusal because the person genuinely does not have the information, it produces honest abstention rather than hedging or fabrication.

A serving system that routes between retrieval and interpretation by question type is an active research thread. Until that lands, the specification layered on top of retrieval covers the gap.

---

## Key completed milestones

All historical; session numbers refer to build sessions.

- **Pipeline ablation** (Session 79): 14 conditions on Franklin, ~$16. Found 10 of 14 steps ceremonial and simplified the pipeline.
- **H3 prompt ablation** (Session 99): 4 rounds, 10 conditions. A 73-word domain guard eliminated topic skew; H3 adopted as the production prompt set.
- **Pipeline refactor** (Sessions 98-99): extraction gate, H3 prompts, compose fixes (they/them pronouns, domain guard).
- **N=10 validation**: User A, User B, User C, Franklin, Douglass, Wollstonecraft, Roosevelt, Patents, Warren Buffett (48 shareholder letters), Howard Marks (74 investment memos). All scored 73-82/100.
- **Twin-2K-500 benchmark** (N=100): 71.83% accuracy at 18:1 compression, p=0.008.
- **BCB-0.1 Franklin**: 2 pass, 2 fail, 1 invalid. DRS (Dialectical Robustness Score) penalizes fidelity.
- **Provenance eval framework** (Session 77): mechanical BA+PC layers, $0 cost, human-auditable.
- **Website** live at [base-layer.ai](https://base-layer.ai): example specifications, magic link auth, feedback mechanism, version history UI.
- **Privacy scrub and git push** (Session 81): 0 security blockers.
- **44 subjects H3-authored**: all subjects recomposed with H3 prompts and compose fixes (0 he/him, 0 topic skew).
- **Serving layer spec** (Session 99): activation matching for brief-to-context relevance (`docs/core/SERVING_LAYER_SPEC.md`).
- **Cross-discipline research** (Session 99): 10 findings across 7 academic domains mapped to the architecture.

---

## Project status

Pre-1.0. The pipeline runs end to end, the MCP server is live, and example specifications are served at [base-layer.ai](https://base-layer.ai).

| Item | State |
|---|---|
| License | Apache 2.0 |
| Tests | 470 passed, 6 skipped (2026-08-18) |
| CLI | `baselayer` with 25 subcommands, including the one-command `baselayer run` pipeline |
| MCP | 2 resources plus 8 tools over stdio (one resource a deprecated alias) |
| Storage | SQLite + ChromaDB, all local |
| Extraction | Haiku via Anthropic API; Ollama for fully local extraction |
| Authoring / composition | Sonnet / Opus via Anthropic API |
| Repository | [agulaya24/BaseLayer](https://github.com/agulaya24/BaseLayer) |
| Site | [base-layer.ai](https://base-layer.ai) |

For the catalogued design choices and their rationale, see [`DECISIONS.md`](DECISIONS.md). For the principles those decisions ladder up to, see [`DESIGN_PRINCIPLES.md`](DESIGN_PRINCIPLES.md). For the prompts themselves, read the source. Nothing is hidden.

Active research threads include interpretive distillation as the successor to the capped author, 32B-class local models for a fully local pipeline, a serving system that routes by question type, faithfulness as its own measurement axis distinct from compactness and predictive accuracy, and per-component ablation across anchors, core, and predictions.
