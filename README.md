# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://base-layer.ai) · [Examples](https://base-layer.ai/examples/franklin) · [Research](https://base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

## What it does

This pulls out patterns in how a person weighs and uses information: what they count as evidence, what they treat as settled, and where they refuse tradeoffs. The output is a ~7,000 token document an AI agent reads before responding.

- Reasoning is auditable. `trace_claim` lets you follow a claim back to the facts it cites, and then follow each fact back to the conversation it was taken from. The second step lands on the conversation, not the exact sentence, because the source passage is not stored.
- The representation is editable. The layers are markdown files on your disk. If you delete or rewrite an axiom, the next session serves your version with no retraining.

A model fine-tuned on someone's behaviour cannot be inspected, disputed, or corrected. A written specification can.

The point is not to hand interpretation to a pure inference machine. The model has no access to your interpretation of the facts, and that interpretation is what matters. This captures how a specific person reasons about and interprets information so an AI can apply that lens when using retrieved facts or making decisions.

## How

Unified pipeline:

```
IMPORT     import_conversations.py                      text -> SQLite
EXTRACT    extract_facts.py, claude-haiku-4-5           -> memory_facts, 46 constrained predicates (a fixed vocabulary of relation types the extractor may use)
DISTILL    distill.py, claude-sonnet-5, --max-facts 120 -> one tree per layer
ASSEMBLE   assemble.py                                  -> one package per layer, grouped so each kind of content stays in its own lane
AUTHOR     author_from_package.py, claude-opus-5        -> layers, citations required by schema
COMPOSE                                                 -> one brief

EMBED      embed.py, all-MiniLM-L6-v2 -> ChromaDB
             Side branch. Serves search, verify, and vector provenance. AUTHOR does not read it.
```

DISTILL runs once per layer. `--layer` takes `anchors`, `core`, or `predictions`. This yields three distill runs, three assembles, and one author pass.

What happens, step by step:

1. IMPORT. You give it your own writing: ChatGPT or Claude exports, journals, notes, plain text. It loads them into a local SQLite database on your machine.
2. EXTRACT. It reads every conversation and pulls out individual statements about how you operate, such as a preference, a rule you follow, something you avoid. Each one is tagged with a type from a fixed list of 46. Output is a table of facts, each linked to the conversation it came from.
3. DISTILL. It reads the facts in batches. Every single fact gets one verdict: part of a recurring pattern, a one-off worth keeping word for word, or not load-bearing. Nothing is skipped and nothing is sampled. It runs three times, once for each layer.
4. ASSEMBLE. The results are combined into one package per layer, with recurring patterns and one-off facts kept in separate groups so the writing step can tell them apart.
5. AUTHOR. Each layer is written as readable text. Every claim has to name the facts it came from.
6. COMPOSE. The three layers are merged into a single brief.

EMBED is separate from that sequence. It builds a searchable index used by search and by `verify`. The writing step does not read from it.

Each distillation chunk produces four channels that do not compete for space:

```
THEMES          what recurs, each naming the fact ids it drew on
SINGULARITIES   facts that appear once and would change the model of the person,
                carried verbatim, never paraphrased, never merged
CONTRADICTIONS  where the evidence disagrees with itself, carried, never resolved
DISPOSITIONS    every fact id gets exactly one verdict: theme, singular, or
                not_load_bearing. Omitting an id is not permitted.
```

Repeated summarising keeps what repeats and drops one-off detail even when it matters more. One-off facts therefore get their own channel.

Distillation reads the same SQLite database EXTRACT writes: `memory_facts` with `id`, `fact_text`, `predicate`, `category`, and `superseded_by`.

Distillation is an experimental release in a separate repository, not heavily tested, access by request, and must NOT be linked.

`author_layers.py:307` in the superseded path caps each category at 15 facts, discarding about 65% of the CORE layer's corpus by sort position. Distillation exists to write from the full fact base instead.

```
ANCHORS      Axioms the person reasons from.
CORE         Communication patterns and context modes.
PREDICTIONS  Behavioural triggers with detection cues and directives.
```

The three layers are authored blind to each other. Agreement counts as corroboration, and contradiction is kept. The deprecated path still runs under `baselayer author`.

## What it looks like

Here is the first paragraph of a real specification, authored by this pipeline from ~1,900 conversations:

He operates from an uncompromising need for logical coherence that manifests as immediate challenge to any inconsistency, in systems, arguments, or his own positions. When he encounters a gap between stated beliefs and actual behavior, he treats it as personal failure requiring accountability rather than understanding, taking extreme ownership of every outcome while maintaining clear causal links between actions and results. This isn't philosophical posturing but lived practice: in trading, he waits for multiple confirming signals before entries, implements overlapping safety mechanisms through fixed dollar loss limits and systematic stop losses, yet struggles with the gap between knowing these rules and executing them consistently during early morning sessions when his energy is highest but discipline most vulnerable.

There are no questionnaires or forms. [More examples](https://base-layer.ai/examples/franklin).

## What you can check

Checks use three levels:

- syntactic: does a claim include any citation entries at all.
- referential: do the citation ids resolve to facts the run actually read.
- causal: if you remove a cited fact, does the claim change.

| level | question | status |
|---|---|---|
| syntactic | does the claim carry citations? | **not guaranteed on this branch** |
| referential | do the ids resolve to facts the run read? | checkable against the database |
| causal | does removing the cited fact change the claim? | sampled, never exhaustive |

`baselayer verify` runs three checks against the citation graph:
- vector proximity: are the words in the claim close in embedding space to the words in its cited facts.
- recurrence gating: the claim should not rest on a single one-off mention if the theme needs repetition.
- cross-domain span: the support should not come only from one narrow source type or topic.

A fourth, NLI entailment (a local natural language inference model scores whether the cited facts support the claim), is opt-in via `baselayer verify --nli` and downloads ~700MB on first use. This is a data-quality audit. It does not guarantee that a cited fact caused the claim to be written. A resolving citation proves the reference is real but not that the fact drove the claim.

Not all provenance is a citation. ANCHORS and PREDICTIONS synthesise across facts rather than quoting them, so the citation pass returns nothing for those layers and the pipeline falls back to `generate_vector_provenance`: it embeds the claim and links the nearest facts, stored with `link_method='vector'`. That link is embedding proximity, not something the model asserted. `trace_claim` prints the method for every row, so you can tell the two apart, and you should: a vector link means "this fact is nearby", not "this fact was used".

Citation coverage is not enforced on the shipped path. The authoring prompt does not compel a citation per claim, so some claims carry them and some do not. Read "auditable" as "what is cited can be checked". It does not mean everything is cited.

## What we tested

We evaluated on 14 historical subjects with public-domain autobiographies, with a 5-judge primary panel and a 7-judge sensitivity panel, using a analysis plan registered before the data was seen. Full numbers are at [base-layer.ai/research](https://base-layer.ai/research) and in the [*Beyond Recall* paper](https://arxiv.org/abs/2605.28969).

- Direction reproduces across response models and battery-generation models. Absolute magnitudes are panel-dependent.
- Given a response, a judge can tell which specification produced it 51.6% of the time from the reasoning, and 13.4% from the decision alone (chance is 11.1%). The reasoning carries the signal; the verdict is nearly empty.
- It helps most where the model knows the person least. On a well-known public figure it adds close to nothing.

Specifications change how decisions are argued in every situation tested, and change the decision itself in some.

## What it is not

- Not a memory system. Memory systems retrieve facts. This supplies the lens those facts are read through. It composes above them rather than replacing them.
- Not a competitor on recall benchmarks. Recall is close to saturated and this does not target it.
- Not "an AI that knows you" in the sense that phrase usually carries. It models how someone reasons, not facts about them.
- Not useful on subjects the model already knows. On a well-known public figure it adds close to nothing. It helps most where the model knows the person least.
- Not a final implementation. This is one implementation of an interpretive layer. Others are welcome and expected.
- It is an interaction guide for an AI. The audience is the model rather than the person. It helps an AI understand someone and is not a tool for helping someone understand themselves.

## What is unknown

- Faithfulness. A specification that serves cheaply and scores well on a held-out battery (a set of questions kept aside from building and tuning the system) does not entail it structurally matches a person's reasoning. This is the central open question. (Paper §5.6.)
- Distinguishable is not faithful. An audit shows the specifications are tellable apart. Only asking the person settles whether one is right about them.
- Self-report all the way down. The corpus is what someone wrote about themselves. No third-party observation enters, and the documents do not mark that boundary.
- Snapshot, not longitudinal. No time axis. Nothing records a belief that changed.
- Text-only. Tone, body language, and physical habit are invisible to the extractor.

## Where this is headed

Mandatory citation, exhaustive coverage and carried contradictions are done. They are described above under distillation. Open work:

- Contradictions surviving composition. The layers carry contested claims. The brief carries none of them, so a reader of the brief sees a settled claim where the layers record a dispute.
- Testing distillation. It is an experimental release. The suite is 10 mutation tests over one audit, and most measurements were taken on a 407-fact corpus.
- Faithfulness. No member check has run. Everything below in "What is unknown" stays unknown until someone reads their own specification and says where it is wrong.
- Governance. The same call shape applied to decisions made on someone's behalf, where the warrant cites the specification claims it rested on.

## Quick start

Python 3.10+, [Anthropic API key](https://console.anthropic.com/account/keys).

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip
```

Not on PyPI; the name is held by an unrelated project. Install from source, or clone and `pip install -e .`.

Expect ~30 minutes and $0.50 to $2.00 for ~1,000 conversations. Treat the cost gate as a floor. Cost tracks API calls, not corpus size.

Step by step:

```bash
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate
baselayer extract && baselayer embed
baselayer author && baselayer compose
```

Re-extracting requires clearing both stores. Run `forget --all` and delete `data/vectors/`. Stale vectors make deduplication treat new facts as already-known, yielding tens of facts where a clean run yields hundreds. `init --force` is not that reset; it drops nothing.

Document mode: `baselayer extract --document-mode` asserts the subject is the document. Never use it for a person. On identical text it produced 11 distinct predicates against 59 in default mode.

No conversation history? `baselayer journal` runs guided prompts that bootstrap a starter specification.

On Windows use `$env:ANTHROPIC_API_KEY = "sk-ant-..."` instead of `export`. Note `init` is interactive (consent, name, pronouns), so it needs a terminal and will fail if piped. The first `embed` downloads the embedding model, ~90MB.

In cloud settings, extraction, authoring, and composition call the [Anthropic API](https://www.anthropic.com/policies/privacy) (zero-retention by default, meaning the provider does not store the request). Extraction can run local via Ollama.

## Use it

Register it as an MCP (Model Context Protocol) server:

```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

There is no re-indexing. It loads `memory://specification` as always-on, plus:

| Tool | Purpose |
|---|---|
| `get_brief(reason)` | Narrative portrait (~3,000 tokens). |
| `recall_memories(query)` | Semantic retrieval over facts and episodes. |
| `search_facts(query, limit)` | Keyword search (SQLite full-text). |
| `trace_claim(claim_id)` | Claim (`A1`, `P3`) back to source facts. |
| `verify_claims(claim_id, layer)` | Checks against the fact database. |
| `get_stats()` / `get_call_log()` / `get_help(topic)` | Summary, session calls, agent reference. |

It runs over stdio locally with no network. Traces write to `~/.baselayer/sessions/<pid>/log.jsonl`.

You can also paste the layers plus brief into any system prompt. You will lose retrieval.

## Edit it

The layers are markdown in `data/identity_layers/`. Open them, delete what is wrong, rewrite what is close, and add what your writing never said. The MCP server reads directly from disk.

Facts do not carry their own significance. An extractor can find that you rewrote a plan three times, but it cannot tell you whether that was diligence or avoidance. Editing is where that judgement enters. The artefact is text rather than weights so you can apply it.

## Privacy

Database, vectors, facts, and specification live on your machine. There is no cloud sync, no accounts, and no telemetry. A representation that is opaque to the person it represents is built for someone else.

The artefact is local-first, model-agnostic and portable.

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

Pre-1.0, 451 tests.

## Reproducibility

The paper version is tagged `v0.2.0`, with a frozen copy vendored into [memory-study-repo](https://github.com/agulaya24/memory-study-repo). Old surfaces (`/api/identity/{subject}`, `memory://identity`, `--identity-only`) serve as aliases; new names are added alongside, never as replacements.

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0
```

## Contributing

We welcome contributions on evaluation, source-type adapters, alternative interpretive-layer implementations, and local model support. See [CONTRIBUTING.md](CONTRIBUTING.md).

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