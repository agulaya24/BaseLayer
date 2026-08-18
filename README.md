# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://base-layer.ai) · [Examples](https://base-layer.ai/examples/franklin) · [Research](https://base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

## What it does

Extracts interpretive patterns from a person's own writing: how they weigh evidence, what they treat as settled, where they refuse to trade one thing for another. Outputs a ~7,000 token document an AI agent reads before responding.

Two properties are the point:

- **Reasoning is auditable.** `trace_claim` walks a claim back to the facts behind it, and each fact back to the conversation it was extracted from. The source passage itself is not stored, so the second hop lands on a conversation rather than a sentence.
- **The representation is editable.** The layers are markdown on your disk. Delete an axiom, rewrite one, and the next session serves your version. No retraining.

A model fine-tuned on someone's behaviour cannot be inspected, disputed, or corrected. A specification can. That is the trade this makes.

## How

```
IMPORT   ChatGPT, Claude, journals, text            -> SQLite
EXTRACT  Haiku, 46 constrained predicates           -> structured facts
EMBED    MiniLM-L6-v2, local                        -> ChromaDB
AUTHOR   Sonnet, three layers, blind to each other  -> anchors / core / predictions
COMPOSE  Opus, three layers into one brief          -> ~3K brief (full spec ~7K)
```

```
ANCHORS      Axioms the person reasons from.
CORE         Communication patterns and context modes.
PREDICTIONS  Behavioral triggers with detection cues and directives.
```

The three layers are authored blind to each other. Agreement between them is independent corroboration. Contradiction is a finding, and it is kept rather than smoothed away.

## What it looks like

First paragraph of a real specification, from ~1,900 conversations:

> He operates from an uncompromising need for logical coherence that manifests as immediate challenge to any inconsistency, in systems, arguments, or his own positions. When he encounters a gap between stated beliefs and actual behavior, he treats it as personal failure requiring accountability rather than understanding, taking extreme ownership of every outcome while maintaining clear causal links between actions and results. This isn't philosophical posturing but lived practice: in trading, he waits for multiple confirming signals before entries, implements overlapping safety mechanisms through fixed dollar loss limits and systematic stop losses, yet struggles with the gap between knowing these rules and executing them consistently during early morning sessions when his energy is highest but discipline most vulnerable.

Text alone. No questionnaires, no forms. [More examples](https://base-layer.ai/examples/franklin).

## What you can check

| level | question | status |
|---|---|---|
| syntactic | does the claim carry citations? | **not guaranteed on this branch** |
| referential | do the ids resolve to facts the run read? | checkable against the database |
| causal | does removing the cited fact change the claim? | sampled, never exhaustive |

`baselayer verify` runs three checks against the citation graph: vector proximity (does the claim sit near its cited facts), recurrence gating (no claim rests on a one-off mention), and cross-domain span (no single-domain overfit). A fourth, NLI entailment (a local model scores whether the cited facts support the claim), is opt-in via `baselayer verify --nli` and downloads ~700MB on first use. This is a data-quality audit, not a causal-traceability guarantee. A resolving citation proves the reference is real, not that the fact drove the claim.

**Two things that will otherwise surprise you:**

Citation coverage is not enforced here. The authoring prompt does not compel a citation per claim, so some claims carry them and some do not. Read "auditable" as "what is cited can be checked", not "everything is cited".

`author_layers.py:307` caps each category at 15 facts before authoring. Measured, that discards about 65% of the CORE layer's corpus, cutting by sort position rather than importance. It was never a recorded decision. There is no environment override in this repo: to change it, edit the constant.

## What we tested

14 historical subjects, public-domain autobiographies. 5-judge primary panel, 7-judge sensitivity, pre-registered analysis plan. Full numbers: [base-layer.ai/research](https://base-layer.ai/research) and the [*Beyond Recall* paper](https://arxiv.org/abs/2605.28969).

- Direction reproduces across response models and battery-generation models. Absolute magnitudes are panel-dependent.
- Specifications separate arms at **51.6% via justification vs 13.4% via decision** (chance 11.1%). The reasoning carries the signal; the verdict is nearly empty.
- It helps most where the model knows the person least. On a well-known public figure it adds close to nothing.

Supportable claim: **specifications change how decisions are argued in every situation tested, and change the decision itself in some.**

## What is unknown

- **Faithfulness.** A specification that serves cheaply and scores well on a held-out battery does not entail it structurally matches a person's reasoning. This is the central open question. (Paper §5.6.)
- **Distinguishable is not faithful.** An audit shows the specifications are tellable apart. Only asking the person settles whether one is right about them.
- **Self-report all the way down.** The corpus is what someone wrote about themselves. No third-party observation enters, and the documents do not mark that boundary.
- **Snapshot, not longitudinal.** No time axis. Nothing records a belief that changed.
- **Text-only.** Tone, body language, and physical habit are invisible to the extractor.

## Where this is headed

- **Citation mandatory by schema**, so omission is impossible rather than discouraged.
- **Exhaustive coverage instead of capped selection.** Every fact receives a recorded disposition, so "everything was considered" is checkable rather than asserted.
- **Contradictions carried to the end.** Measured on a sibling branch, they survive into the layers and are lost at composition. Carrying them through is the intent here.
- **Governance.** The same call shape applied to decisions made on someone's behalf, where the warrant cites the specification claims it rested on.

## Quick start

Python 3.10+, [Anthropic API key](https://console.anthropic.com/account/keys).

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip
```

> Not on PyPI; the name is held by an unrelated project. Install from source, or clone and `pip install -e .`.

~30 minutes and $0.50 to $2.00 for ~1,000 conversations. The cost gate is a floor, not a budget: cost tracks API call count, not corpus size.

Step by step:

```bash
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate
baselayer extract && baselayer embed
baselayer author && baselayer compose
```

**Re-extracting:** clear both stores. `forget --all` **and** delete `data/vectors/`. Stale vectors make deduplication treat new facts as already-known, yielding tens of facts where a clean run yields hundreds. `init --force` is not that reset; it drops nothing.

**Documents, not people:** `baselayer extract --document-mode` asserts the subject *is* the document. Never use it for a person. On identical text it produced 11 distinct predicates against 59 in default mode.

**No conversation history?** `baselayer journal` runs guided prompts that bootstrap a starter specification.

**Windows:** use `$env:ANTHROPIC_API_KEY = "sk-ant-..."` instead of `export`. Note `init` is interactive (consent, name, pronouns), so it needs a terminal and will fail if piped. First `embed` downloads the embedding model, ~90MB.

**Cloud:** extraction, authoring, composition call the [Anthropic API](https://www.anthropic.com/policies/privacy) (zero-retention by default). Extraction can run local via Ollama.

## Use it

```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

Reads the same store the pipeline builds, no re-indexing. Loads `memory://specification` always-on, plus:

| Tool | Purpose |
|---|---|
| `get_brief(reason)` | Narrative portrait (~3,000 tokens). |
| `recall_memories(query)` | Semantic retrieval over facts and episodes. |
| `search_facts(query, limit)` | FTS5 keyword search. |
| `trace_claim(claim_id)` | Claim (`A1`, `P3`) back to source facts. |
| `verify_claims(claim_id, layer)` | Checks against the fact database. |
| `get_stats()` / `get_call_log()` / `get_help(topic)` | Summary, session calls, agent reference. |

Stdio, local, no network. Traces in `~/.baselayer/sessions/<pid>/log.jsonl`.

Or paste the layers plus brief into any system prompt. Keeps the specification, loses retrieval.

## Edit it

The layers are markdown in `data/identity_layers/`. Open them, delete what is wrong, rewrite what is close, add what your writing never said. The MCP server reads from disk.

Facts do not carry their own significance. An extractor can find that you rewrote a plan three times; it cannot tell you whether that was diligence or avoidance. Editing is where that judgment enters, and it is why the artifact is text rather than weights.

## Privacy

Database, vectors, facts, and specification live on your machine. No cloud sync, no accounts, no telemetry. A representation that is opaque to the person it represents is built for someone else.

## Reference

- **Dataset:** [`agulaya24/beyond-recall`](https://huggingface.co/datasets/agulaya24/beyond-recall)
- **Live specs (no auth):** `GET https://base-layer.ai/api/identity/{franklin,buffett,douglass}`
- **For agents:** [`llms.txt`](https://base-layer.ai/llms.txt), [Agent card](https://base-layer.ai/.well-known/agent-card.json), [OpenAPI](https://base-layer.ai/api/openapi.json)

| Doc | Contents |
|-----|----------|
| [`ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) | Pipeline design, 5-step description |
| [`PROJECT_OVERVIEW.md`](docs/core/PROJECT_OVERVIEW.md) | Components and composition |
| [`DECISIONS.md`](docs/core/DECISIONS.md) | Design decisions with rationale |
| [`DESIGN_PRINCIPLES.md`](docs/core/DESIGN_PRINCIPLES.md) | Foundational principles |
| [`ROADMAP.md`](ROADMAP.md) | Near-term and research-horizon work |
| [`docs/eval/`](docs/eval/) | Evaluation frameworks and results |

The prompts are in the code. Nothing is hidden. Pre-1.0, 451 tests, expect rough edges.

## Reproducibility

Paper version tagged `v0.2.0`, frozen copy vendored into [memory-study-repo](https://github.com/agulaya24/memory-study-repo). Old surfaces (`/api/identity/{subject}`, `memory://identity`, `--identity-only`) serve as aliases; new names are added alongside, never as replacements.

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0
```

## Contributing

Especially evaluation, source-type adapters, alternative interpretive-layer implementations, local model support. See [CONTRIBUTING.md](CONTRIBUTING.md).

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

Apache 2.0. See [LICENSE](LICENSE). The *Beyond Recall* paper is CC-BY 4.0.
