# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

Base Layer is an open-source reference pipeline that produces a **Behavioral Specification** of how a specific person interprets information, decides, and communicates. The Specification is one implementation of an **interpretive layer** above memory: the framework an AI agent reads facts through to act in alignment with the individual rather than the population average.

[base-layer.ai](https://base-layer.ai) · [Live examples](https://base-layer.ai/examples/franklin) · [Research](https://base-layer.ai/research)

---

## Recall is not interpretation

Current AI memory systems (Mem0, Letta, Supermemory, Zep) optimize for recall. On standard recall benchmarks (LOCOMO, LongMemEval) they score in the 70 to 93 percent range. Recall is approaching solved.

What's left unmeasured is *interpretation*: how a specific person processes facts and experiences into judgments, decisions, and reactions. Facts are inert until something reads them. **Facts require a lens to be evaluated through, and the lens should be the individual's.** An interpretive layer above retrieval is what's missing from current AI memory.

The **Behavioral Specification** is one implementation of that interpretive layer. It is the artifact this project produces and the artifact the *Beyond Recall* paper tests. The category claim — that interpretation is a measurable axis, distinct from recall — is the contribution. The specific Behavioral Specification artifact is the demonstration. Other implementations of an interpretive layer are welcome and expected.

## What a Behavioral Specification is

A Behavioral Specification is a structured document encoding a person's behavioral patterns across three interpretive layers (anchors, core, predictions) plus a composed unified brief. Total size per subject is approximately **7,000 tokens, around 5,000 words, about the length of a short magazine article**. (Paper §3.7.)

```
ANCHORS      Decision foundations. The axioms someone reasons from.
CORE         Operational constraints. Communication patterns and context modes.
PREDICTIONS  Behavioral triggers with detection cues and directives.
```

The Specification is generated from raw text through a five-step pipeline:

```
IMPORT   Multi-source ingest (ChatGPT, Claude, journals, text)     -> SQLite
EXTRACT  Haiku, 47 constrained behavioral predicates              -> structured facts
EMBED    MiniLM-L6-v2 local embeddings                            -> ChromaDB vectors
AUTHOR   Sonnet, three-layer authoring with domain-agnostic guard -> anchors / core / predictions
COMPOSE  Opus, compresses three layers into unified specification -> ~7K token document
```

`baselayer run <file>` executes the full pipeline with a cost-estimate gate. See [`docs/core/ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) for the canonical description of each stage.

## What the output looks like

First paragraph of a real Specification, generated from approximately 1,900 conversations:

> He operates from an uncompromising need for logical coherence that manifests as immediate challenge to any inconsistency, in systems, arguments, or his own positions. When he encounters a gap between stated beliefs and actual behavior, he treats it as personal failure requiring accountability rather than understanding, taking extreme ownership of every outcome while maintaining clear causal links between actions and results. This isn't philosophical posturing but lived practice: in trading, he waits for multiple confirming signals before entries, implements overlapping safety mechanisms through fixed dollar loss limits and systematic stop losses, yet struggles with the gap between knowing these rules and executing them consistently during early morning sessions when his energy is highest but discipline most vulnerable.

That's from text alone. No questionnaires, no profiles, no manual input. Every claim cites the facts it was authored from, and every fact cites the source passage it was extracted from. [More examples](https://base-layer.ai/examples/franklin).

## Where the Specification helps

Across 14 historical subjects, the Behavioral Specification reliably moves a language model from refusal or generic guessing to grounded, person-specific responses **where the model knows the subject least**. Mean prediction-quality lift +0.89 on a 1-to-5 rubric across the 9 low-baseline subjects; every one of the 9 improved. (Paper §4.1.)

The lift is largest where the baseline is lowest. On subjects the model already knows well from pretraining (e.g., Benjamin Franklin, baseline 3.77), the Specification adds little or mildly hurts. The Specification is a leveler: it brings every subject to roughly the same operational quality (per-subject mean ≈ 2.44 across 14 subjects), regardless of where each subject's baseline sits. This is the equity property: it works for any user, not just users with substantial pretraining coverage. (Paper §4.1, §5.2.)

The population of practical interest is the long tail of users whose private reasoning is not in any training corpus. Almost no one in that population looks like Franklin; almost everyone sits at or near the rubric floor without context.

## How the Specification composes with other context

The Specification layers above other sources of context rather than replacing them. Memory systems supply facts. The full extracted fact set supplies facts. Raw source text supplies facts. The Specification supplies the lens those facts get read through. The lens travels with the person across any model and any provider; the AI engine, the memory system, and the fact source can change without the Specification needing to change.

What changes when the Specification is added depends on what context already exists. (Paper §4.2, §4.4.4.)

| Context | Approx. tokens | Lift over no-context baseline |
|---|---|---|
| Specification alone | ~7K | +0.71 |
| All facts only | ~10K | +0.83 |
| Raw corpus only | ~163K | +0.93 |
| All facts + Specification | ~17K | +0.93 |
| Raw corpus + Specification | ~170K | +0.98 |

Two readings.

**The Specification is one of multiple compression strategies.** All facts plus Specification at 17K tokens reaches the same end-state as raw corpus alone at 163K tokens. Two compression strategies, same predictive accuracy, ten times the context cost difference.

**The Specification's effect on top of richer context shifts mechanism.** Adding any context to a no-context baseline produces *re-ranking* — different questions become the well-answered ones. Adding the Specification on top of all facts or raw corpus produces *near-uniform lift* — the same questions remain strong; the Specification adds a small additional improvement to most. The aggregate mean Δ on info-rich pairs is small because per-question helps and hurts roughly cancel; per-question, the movement is real. (Paper §4.4.4.)

When composed with memory-system retrieval specifically, three patterns emerge (Paper §4.4.2):

- **Interpretive supply.** Retrieved facts underdetermine the answer. The Specification supplies the pattern that has to transfer to the new situation. *Increases representational accuracy.*
- **Over-theorization.** Retrieval already supplies the plain answer. The Specification pulls the response toward depth the question doesn't call for. *Decreases representational accuracy.*
- **Spec-induced refusal.** The Specification's axioms trigger principled refusal where the question lacks evidence to answer. The current rubric penalizes refusal even when refusal is correct. *Lowers measured score; whether it lowers actual representational accuracy depends on whether refusal was the right behavior.*

**An empirical note on memory-system divergence (Paper §4.4.1).** Given the same input fact pool, the four leading memory systems retrieve mostly different top-10 facts. Mean pairwise Jaccard overlap is 8.3% across the 10 system pairs. The systems converge on recall benchmark scores; they do not converge on which facts matter for a specific interpretive question. Different providers reflect different ranking design choices, not a shared theory of relevance.

## What the Specification is not

- **Not memory on the retrieval axis.** Memory systems retrieve facts; the Specification supplies interpretation. They are different layers.
- **Not a competitor to Mem0, Letta, Supermemory, or Zep on recall benchmarks.** Those systems perform within a few points of each other on LongMemEval and LOCOMO. The Specification operates at a different layer.
- **Not a replacement for facts or retrieved context.** Layered with them, it does better than either alone.
- **Not magic on subjects the model already knows well from pretraining.** High-baseline subjects show near-zero or mildly negative lift.
- **Not a final implementation.** The Behavioral Specification is one implementation of the interpretive layer; other implementations are welcome and expected. (Paper §1.4: *"The Behavioral Specification is one implementation of this option, not the only one."*)

## Quick Start

**Requirements:** Python 3.10+, [Anthropic API key](https://console.anthropic.com/account/keys).

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip
```

> Base Layer is not yet on PyPI; the `baselayer` name is held by an unrelated project. Install from source via the URL above, or clone the repo and `pip install -e .`.

Runs the full pipeline. Shows a cost estimate before spending. Roughly 30 minutes for ~1,000 conversations, $0.50 to $2.00 total.

For step-by-step control:

```bash
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate                         # preview cost before spending
baselayer extract
baselayer embed
baselayer author && baselayer compose
```

**Other input types.** Books, essays, letters, patents. Use `baselayer extract --document-mode`.
**No conversation history?** `baselayer journal` runs guided prompts that bootstrap a starter Specification.

**Cloud dependency.** Extraction, authoring, and composition send text to the [Anthropic API](https://www.anthropic.com/policies/privacy) (zero-retention by default as of March 2025). Extraction can run fully local via Ollama (`BASELAYER_EXTRACTION_BACKEND=ollama`); authoring and composition currently require the Claude API. 32B-class local models for the full pipeline are under active testing.

## Use your Specification

**MCP server** (Claude Desktop, Claude Code, Cursor):

```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

**Or paste directly** into Claude custom instructions, ChatGPT project files, Grok system prompts, or any system prompt. Approximately 7,000 tokens, fits anywhere.

## Auditability, not black-box claims

Every claim in a generated Specification cites the facts used to author it, and every fact cites the source text passage it was extracted from. The `baselayer verify` command runs four checks against that citation graph:

- **Vector proximity.** Each claim is embedded; the top-N most similar facts are retrieved and compared against the facts the authoring model cited. Measures topic consistency.
- **Recurrence gating.** Cited facts must occur multiple times across the corpus. A claim cannot stand on a one-off mention.
- **Cross-domain span.** Behavioral claims must draw from facts in more than one source category. Guards against single-domain overfit.
- **NLI entailment.** A local DeBERTa NLI model scores whether cited facts entail each claim. Measures supportability, not causal derivation.

Base Layer ships a strong data-quality audit, not a causal-traceability guarantee. You can inspect every claim's evidence chain, catch unsupported claims, and flag low-recurrence or single-domain citations. That is the honest scope.

## Honest scope

This is a methods paper plus an open-source reference pipeline.

- Tested on 14 historical subjects with public-domain autobiographies (4 continents, ~2 millennia of written experience).
- LLM-as-judge methodology (5-judge primary panel: Haiku 4.5, Sonnet 4.6, Opus 4.6, GPT-4o, GPT-5.4; 7-judge sensitivity adds Gemini 2.5 Flash and Pro).
- Pre-registered analysis plan; full results catalogued at [base-layer.ai/research](https://base-layer.ai/research).
- Direction reproduces across response models (Sonnet 4.6, Gemini 2.5 Pro) and across battery generation models. Absolute magnitudes are panel-dependent; the direction is not. (Paper §4.6.1.)
- **Faithfulness** — whether a compressed Specification structurally matches a person's reasoning rather than just predicting their behavior — remains the central open question. (Paper §5.6.)

This is not a product launch. The category claim is the contribution; the specific artifact is the demonstration.

## Privacy and ownership

What stays local: the database (SQLite), vectors (ChromaDB), extracted facts, and the Specification all live on the user's machine. No cloud sync, no accounts, no telemetry. The Specification is yours.

A representation of how a specific person interprets information is operationally consequential. It can be used to predict, steer, or act on that person's behalf. Base Layer ships local storage, inspection, and modification tools so the user can audit and correct what an agent uses about them. A representation that is opaque to the person it represents is a representation built for someone else; that is not the design here.

## Cost

| Corpus Size | Cost | Time |
|------------|------|------|
| ~100 conversations | $0.30 to $0.80 | ~5 min |
| ~500 conversations | $0.50 to $1.50 | ~15 min |
| ~1,000 conversations | $0.50 to $2.00 | ~30 min |

Run `baselayer estimate` to preview your exact cost before spending.

## Current limitations

- **Snapshot, not longitudinal.** The shipped Specification is a point-in-time cross-section. Phase-transition detection across behavioral dimensions exists in research tooling but is not yet in production.
- **Text-only.** Body language, tone of voice, and physical habits are invisible to the extractor.
- **Cloud dependency for authoring and composition.** Extraction can run fully local via Ollama; authoring (Sonnet) and composition (Opus) currently require the Claude API.
- **Pre-1.0.** 415 tests, design decisions catalogued. Expect rough edges.
- **Faithfulness is an open question.** A representation small enough to serve and scoring well on a held-out battery does not entail it captures the patterns most distinctive to a specific person.

## API and machine-readable discovery

Example Specifications are live (no auth):

```
GET https://base-layer.ai/api/identity/franklin
GET https://base-layer.ai/api/identity/buffett
GET https://base-layer.ai/api/identity/douglass
```

Each returns structured JSON: anchors, core, predictions, unified Specification, stats.

For agents and LLMs: [`llms.txt`](https://base-layer.ai/llms.txt), [`llms-full.txt`](https://base-layer.ai/llms-full.txt), [Agent card](https://base-layer.ai/.well-known/agent-card.json), [MCP server card](https://base-layer.ai/.well-known/mcp/server-card.json), [OpenAPI spec](https://base-layer.ai/api/openapi.json).

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

## Roadmap

The full roadmap with near-term, mid-term, and research-horizon items is in [`ROADMAP.md`](ROADMAP.md). Highlights:

- **Production readiness.** Paper-version tag and PyPI pin; alias-discipline refactor across naming surfaces.
- **Local pipeline.** 32B-class local models for authoring and composition.
- **Evaluation.** Differentiated rubric (interpretation vs literal recall), faithfulness as its own measurement axis, per-component ablation of the Specification.
- **Serving layer.** Dynamic routing between retrieval and interpretation by question type.

**Direction.** As AI moves from a tool people use to an agent acting on their behalf, the gap between what the agent does and what the person would have done becomes an alignment problem. A user-held, portable, inspectable representation of how a specific person interprets information is one structural way to close it. The Behavioral Specification is one implementation of that representation. Others are welcome.

## Reproducibility

The repository version corresponding to the *Beyond Recall* paper is tagged `v0.2.0` on GitHub. A frozen copy of that version is also vendored directly into the [memory-study-repo](https://github.com/agulaya24/memory-study-repo) under `./baselayer/`, so paper readers can clone the study repo and have the cited pipeline source in one place (no separate install step). Old surfaces (the `/api/identity/{subject}` URLs, the `memory://identity` MCP URI, the `data/identity_layers/` filesystem path, the `--identity-only` CLI flag) continue to serve indefinitely as aliases of the canonical names. New names are added alongside, never as replacements. Old paths and URLs do not break.

Install the paper-cited version directly:

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
