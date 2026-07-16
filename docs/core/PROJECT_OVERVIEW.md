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

Three properties are load-bearing.

1. **Local first.** Source text, extracted facts, embeddings, and the specification all live on the user's machine. Only API calls leave the box.
2. **Provenance traced.** Every claim in the specification cites the facts used to author it; every fact cites the source passage it was extracted from.
3. **Provider agnostic.** The specification format is plain structured text. It runs in Claude, ChatGPT, Gemini, or any model that accepts a system prompt.

---

## Internal architecture

The system has four parts: a fact graph, a three-layer authoring stage, a composition stage, and a serving stage. Each is independent enough to be inspected, replaced, or rerun without disturbing the others.

### The fact graph

A SQLite database holds source conversations and the structured facts extracted from them. Each fact is a `{subject, predicate, object, qualifier}` triple drawn from one of 47 constrained behavioral predicates. ChromaDB holds local MiniLM-L6-v2 embeddings of every fact and every claim, used for provenance retrieval and similarity search at serve time.

The 47 predicates are grouped into five categories: epistemic (`believes`, `values`, `prioritizes`), operational (`practices`, `avoids`, `struggles_with`, `monitors`, `builds`), affective (`fears`, `enjoys`, `loves`), relational (`relates_to`, `collaborates_with`, `follows`), and temporal (`experienced`, `decided`, `aspires_to`). The full schema lives at `lexicon_schema.yaml`.

The graph is the source of truth. Every later artifact derives from it. Re-authoring the specification on the same graph yields a different draft but draws from the same evidence.

### Three-layer authoring

The specification is authored in three independent layers, each from facts only. Each layer answers a different question and is generated blind, with no prior layer's output shown to the authoring model. Blind generation prevents anchoring (measured at 26 percent verbatim carryover when violated).

| Layer | Question it answers | Source | Form |
|---|---|---|---|
| **Anchors** | What does this person reason from? | Conviction-tier facts | A short list of axioms, each with supporting facts |
| **Core** | How does this person operate? | Identity-tier facts grouped by type | Operational constraints: communication patterns, context modes, essential background |
| **Predictions** | What does this person do in specific situations? | Behavioral identity-tier facts | Situation, behavioral pattern, directive, with detection cues and false-positive warnings |

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
| **Vector proximity** | The claim is embedded; the top-N most similar facts are retrieved and compared against the facts the authoring model cited. Catches topic drift. |
| **Recurrence gating** | Cited facts are checked for minimum recurrence across the corpus. A claim cannot stand on a single one-off mention. |
| **Cross-domain span** | Behavioral claims must draw from facts in more than one source category. Guards against single-domain overfit. |
| **NLI entailment** | A local DeBERTa NLI model scores whether the cited facts entail the claim. Measures supportability, not causal derivation. |

This is a strong data-quality audit, not a causal-traceability guarantee. It tells you a claim has supporting evidence in the corpus, that the evidence is recurrent, that it spans more than one domain, and that an NLI model judges it entailed. It does not tell you the claim was logically derived from those specific facts. Cross-domain synthesis claims can score lower than they should because no single fact contains the synthesis. The honest scope is documented in `verify_provenance.py`.

The verifier is exposed three ways: the `baselayer verify` CLI, the `verify_claims` MCP tool, and the per-claim trace surfaced by the website's Genius-style annotation view.

---

## Where it sits relative to memory systems

Memory systems (Mem0, Letta, Supermemory, Zep) optimize for recall. On standard recall benchmarks (LOCOMO, LongMemEval) they score in the 70 to 93 percent range. Recall is approaching solved.

What is left unmeasured is interpretation: how a specific person processes facts and experiences into judgments, decisions, and reactions. The same facts can yield different conclusions depending on whose interpretive framework reads them.

Base Layer composes with retrieval rather than replacing it. Three patterns govern when to use each:

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
