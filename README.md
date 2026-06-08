# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

Base Layer is an open-source reference pipeline that produces a **Behavioral Specification** of how a specific person interprets information, decides, and communicates. The Specification is one implementation of an **interpretive layer** above memory: the framework an AI agent reads facts through to act in alignment with the individual rather than the population average.

[base-layer.ai](https://base-layer.ai) · [Live examples](https://base-layer.ai/examples/franklin) · [Research](https://base-layer.ai/research) · [Benchmark dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

---

## Recall is not interpretation

Current AI memory systems (Mem0, Letta, Supermemory, Zep) optimize for recall and score 70 to 93 percent on standard benchmarks (LOCOMO, LongMemEval). Recall is approaching saturation on those benchmarks.

What's left unmeasured is *interpretation*: how a specific person turns facts and experiences into judgments, decisions, and reactions. Facts are inert until something reads them, and the lens should be the individual's. The **Behavioral Specification** is one implementation of that missing interpretive layer, and the artifact the *Beyond Recall* paper tests. The category claim, that interpretation is a measurable axis distinct from recall, is the contribution. The specific artifact is the demonstration. Other implementations of an interpretive layer are welcome and expected.

## What a Behavioral Specification is

A structured document encoding a person's behavioral patterns across three interpretive layers plus a composed unified brief. About **7,000 tokens, roughly 5,000 words, the length of a short magazine article**. (Paper §3.7.)

```
ANCHORS      Decision foundations. The axioms someone reasons from.
CORE         Operational constraints. Communication patterns and context modes.
PREDICTIONS  Behavioral triggers with detection cues and directives.
```

Generated from raw text through a five-step pipeline:

```
IMPORT   Multi-source ingest (ChatGPT, Claude, journals, text)     -> SQLite
EXTRACT  Haiku, 46 constrained behavioral predicates              -> structured facts
EMBED    MiniLM-L6-v2 local embeddings                            -> ChromaDB vectors
AUTHOR   Sonnet, three-layer authoring with domain-agnostic guard -> anchors / core / predictions
COMPOSE  Opus, compresses three layers into one specification     -> ~7K token document
```

`baselayer run <file>` executes the full pipeline with a cost-estimate gate. See [`docs/core/ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) for the canonical description of each stage.

## What the output looks like

First paragraph of a real Specification, generated from approximately 1,900 conversations:

> He operates from an uncompromising need for logical coherence that manifests as immediate challenge to any inconsistency, in systems, arguments, or his own positions. When he encounters a gap between stated beliefs and actual behavior, he treats it as personal failure requiring accountability rather than understanding, taking extreme ownership of every outcome while maintaining clear causal links between actions and results. This isn't philosophical posturing but lived practice: in trading, he waits for multiple confirming signals before entries, implements overlapping safety mechanisms through fixed dollar loss limits and systematic stop losses, yet struggles with the gap between knowing these rules and executing them consistently during early morning sessions when his energy is highest but discipline most vulnerable.

Text alone. No questionnaires, no profiles, no manual input. Every claim cites the facts it was authored from, and every fact cites the source passage it was extracted from. [More examples](https://base-layer.ai/examples/franklin).

## What it does in practice

The Specification gives a model person-specific grounding where it would otherwise refuse or guess from population averages, and it helps most where the model knows the person least. It composes above other context rather than replacing it: memory systems and raw text supply facts, the Specification supplies the lens those facts are read through, and that lens travels with the person across any model or provider. It is small enough to serve on every turn yet carries most of the predictive signal of a raw corpus many times its size.

It also acts as a leveler. On a subject a model already knows well from pretraining it adds little, but on the long tail of people whose reasoning sits in no training corpus, it brings responses to roughly the same grounded, person-specific quality. The full evaluation across 14 public-domain subjects, with numbers and methodology, is in the [*Beyond Recall* paper](https://arxiv.org/abs/2605.28969) and at [base-layer.ai/research](https://base-layer.ai/research).

## What it is not

- **Not memory on the retrieval axis.** Memory systems retrieve facts; the Specification supplies interpretation. Different layers.
- **Not a competitor to Mem0, Letta, Supermemory, or Zep on recall benchmarks.** Those systems perform within a few points of each other; the Specification operates at a different layer.
- **Not magic on subjects the model already knows well.** High-baseline subjects show near-zero or mildly negative lift.
- **Not a final implementation.** The Behavioral Specification is one implementation of the interpretive layer; others are welcome and expected. (Paper §1.4.)

## Quick start

**Requirements:** Python 3.10+, [Anthropic API key](https://console.anthropic.com/account/keys).

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip
```

> Base Layer is not yet on PyPI; the `baselayer` name is held by an unrelated project. Install from source via the URL above, or clone the repo and `pip install -e .`.

Runs the full pipeline with a cost gate. Roughly 30 minutes and $0.50 to $2.00 for ~1,000 conversations.

For step-by-step control:

```bash
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate                         # preview cost before spending
baselayer extract && baselayer embed
baselayer author && baselayer compose
```

**Other input types.** Books, essays, letters, patents: `baselayer extract --document-mode`. No conversation history? `baselayer journal` runs guided prompts that bootstrap a starter Specification.

**Cloud dependency.** Extraction, authoring, and composition send text to the [Anthropic API](https://www.anthropic.com/policies/privacy) (zero-retention by default). Extraction can run fully local via Ollama; authoring and composition currently require the Claude API.

## Use your Specification

Two ways to put a Specification in front of a model: register the MCP server, or paste the unified brief into a system prompt.

**MCP server** (Claude Desktop, Claude Code, Cursor):

```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

Reads from the same SQLite + ChromaDB store the pipeline builds, with no re-indexing. It loads an always-on resource (`memory://specification`, approximately 6 to 8K tokens: CORE, ANCHORS, PREDICTIONS, plus a tools manifest) and on-demand tools the model calls when it needs grounded retrieval or provenance:

| Tool | Purpose |
|---|---|
| `get_brief(reason)` | Unified narrative portrait of the user (~3,000 tokens). |
| `recall_memories(query)` | Semantic retrieval over facts and episodes (ChromaDB, MiniLM-L6-v2). |
| `search_facts(query, limit)` | FTS5 keyword search across active facts. |
| `trace_claim(claim_id)` | Provenance from a claim (e.g. `A1`, `P3`) back to source facts. |
| `verify_claims(claim_id, layer)` | Verification checks against the fact database. |
| `get_stats()` / `get_call_log()` / `get_help(topic)` | Database summary, session calls, agent reference. |

Stdio, local, no network. Per-session traces land in `~/.baselayer/sessions/<pid>/log.jsonl` (`baselayer log list / show / tail / stats`).

**Paste directly.** Paste the full Specification (three layers plus unified brief, approximately 7,000 tokens) into Claude custom instructions, ChatGPT project files, or any system prompt. Keeps the structural Specification, loses the on-demand fact retrieval.

## Auditability

Every claim in a generated Specification cites the facts used to author it, and every fact cites the source passage it was extracted from. `baselayer verify` runs four checks against that citation graph: vector proximity (topic consistency), recurrence gating (no claim stands on a one-off mention), cross-domain span (no single-domain overfit), and NLI entailment (a local DeBERTa model scores supportability). This is a strong data-quality audit, not a causal-traceability guarantee. You can inspect every claim's evidence chain and flag low-recurrence or single-domain citations.

## Honest scope and limitations

A methods paper plus an open-source reference pipeline, not a product launch. The category claim is the contribution; the specific artifact is the demonstration.

- Tested on 14 historical subjects with public-domain autobiographies (4 continents, ~2 millennia of written experience). 5-judge primary panel, 7-judge sensitivity, pre-registered analysis plan. Full results: [base-layer.ai/research](https://base-layer.ai/research).
- Direction reproduces across response models and battery-generation models; absolute magnitudes are panel-dependent.
- **Snapshot, not longitudinal.** A point-in-time cross-section.
- **Text-only.** Tone of voice, body language, and physical habits are invisible to the extractor.
- **Cloud dependency** for authoring and composition (extraction can run local via Ollama).
- **Pre-1.0.** 451 tests; expect rough edges.
- **Faithfulness is the central open question.** A Specification that serves cheaply and scores well on a held-out battery does not entail it structurally matches a person's reasoning. (Paper §5.6.)

## Privacy and ownership

The database (SQLite), vectors (ChromaDB), extracted facts, and Specification all live on the user's machine. No cloud sync, no accounts, no telemetry. A representation of how a specific person interprets information is operationally consequential, so Base Layer ships local inspection and modification tools. A representation that is opaque to the person it represents is built for someone else; that is not the design here.

## Data, API, and discovery

- **Benchmark dataset.** The *Beyond Recall* specifications, batteries, facts, corpora, and results are on Hugging Face: [`agulaya24/beyond-recall`](https://huggingface.co/datasets/agulaya24/beyond-recall).
- **Live example Specifications** (no auth): `GET https://base-layer.ai/api/identity/{franklin,buffett,douglass}` return structured JSON (anchors, core, predictions, unified Specification, stats).
- **For agents and LLMs:** [`llms.txt`](https://base-layer.ai/llms.txt), [`llms-full.txt`](https://base-layer.ai/llms-full.txt), [Agent card](https://base-layer.ai/.well-known/agent-card.json), [MCP server card](https://base-layer.ai/.well-known/mcp/server-card.json), [OpenAPI spec](https://base-layer.ai/api/openapi.json).

## Documentation

| Doc | Contents |
|-----|----------|
| [`ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) | Pipeline design, canonical 5-step description |
| [`PROJECT_OVERVIEW.md`](docs/core/PROJECT_OVERVIEW.md) | Internal architecture, components, composition |
| [`DECISIONS.md`](docs/core/DECISIONS.md) | Design decisions with rationale |
| [`DESIGN_PRINCIPLES.md`](docs/core/DESIGN_PRINCIPLES.md) | Foundational principles |
| [`ROADMAP.md`](ROADMAP.md) | Near-term, mid-term, and research-horizon work |
| [`docs/eval/`](docs/eval/) | Evaluation frameworks and study results |

The prompts are in the code. Nothing is hidden.

## Reproducibility

The repository version corresponding to the *Beyond Recall* paper is tagged `v0.2.0`, and a frozen copy is vendored into [memory-study-repo](https://github.com/agulaya24/memory-study-repo) under `./baselayer/`. Old surfaces (the `/api/identity/{subject}` URLs, the `memory://identity` MCP URI, the `--identity-only` CLI flag) continue to serve indefinitely as aliases; new names are added alongside, never as replacements.

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0
```

## Contributing

Contributions welcome, especially around evaluation, source-type adapters, alternative interpretive-layer implementations, and local model support. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

```bibtex
@software{baselayer2026,
  title     = {Base Layer: An Open-Source Reference Pipeline for the Interpretive Layer Above Memory},
  author    = {Gulaya, Aarik},
  year      = {2026},
  url       = {https://github.com/agulaya24/BaseLayer},
  license   = {Apache-2.0}
}
```

## License

Apache 2.0. See [LICENSE](LICENSE). The accompanying *Beyond Recall* paper is CC-BY 4.0.
