# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://base-layer.ai) · [Examples](https://base-layer.ai/examples/franklin) · [Research](https://base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

An open-source pipeline that writes an interpretable specification of how a person reasons from their own text.

## What it does

It extracts patterns in how someone weighs and uses information: what counts as evidence, what they treat as settled, and where they refuse tradeoffs. The output is a document an AI reads before responding. You can edit it as text. You can trace many claims back to cited facts, then to the conversations those facts came from.

A fine-tuned model cannot be inspected or corrected. A written specification can.

## How it works

Unified pipeline:

```
IMPORT     Your text into a local database
EXTRACT    Pull candidate facts about preferences, rules, habits
DISTILL    Sort facts into recurring themes, one-offs, and not load-bearing
ASSEMBLE   Package each layer so writing can respect those groups
AUTHOR     Write the layers as readable text with citations where required
COMPOSE    Merge layers into one brief

EMBED      Side branch. Build a vector index for search and verification. The writer does not read it.
```

Layers:

- ANCHORS: Axioms the person reasons from.
- CORE: Communication patterns and context modes.
- PREDICTIONS: Behavioural triggers with detection cues and directives.

Distillation yields four channels that do not compete for space:
- Themes: what recurs, each naming the fact ids it drew on.
- Singularities: one-off facts that would change the model of the person. Carried verbatim.
- Contradictions: where the evidence disagrees with itself. Carried and never resolved.
- Dispositions: every fact gets one verdict. Theme, singular, or not load-bearing.

The three layers are authored blind to each other. Agreement counts as corroboration. Contradiction is kept.

## Quickstart

Requirements: Python 3.10+ and an Anthropic API key (https://console.anthropic.com/account/keys).

```
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip
```

Step by step:

```
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate
baselayer extract && baselayer embed
baselayer author && baselayer compose
```

Experimental distillation path:

```
baselayer distill --layer anchors
baselayer distill --layer core
baselayer distill --layer predictions
baselayer assemble
baselayer author-from-package --outdir spec_out/
```

## Auditability / what you can verify

- You can trace a written claim back to its cited facts. You can then jump from each fact to the conversation it was taken from. The second step lands on the conversation, not the exact sentence, because the source passage is not stored.
- Checks run over the citation graph:
  - Vector proximity: the words in the claim should be close to the words in its cited facts.
  - Recurrence gating: a theme should not rest on a single one-off mention.
  - Cross-domain span: support should not come only from one narrow source type or topic.
  - Optional NLI: a local entailment model can score whether cited facts support the claim. This audits data quality. It does not prove causation.

Not all provenance is a citation. ANCHORS and PREDICTIONS often synthesise across facts. When a claim carries no inline citations, the system links nearest facts by embedding as vector provenance. That link shows proximity, not that the model asserted the link. `trace_claim` prints the link method for each row.

Read auditable as: what is cited can be checked. It does not mean everything is cited.

## Status and limits

- Experimental components: Distillation, assembly, and the package-based author are experimental in this repository. The distillation test suite is 10 mutation tests over the citation audit and exercises none of the other modules. Most measurements behind the distillation design come from a single 407-fact corpus. Study harnesses that ship here may emit unstripped outputs. Use with care and inspect outputs.
- Two authoring paths: The legacy authoring path still ships. It does not guarantee inline citations, so verification that depends on parsing citations may produce no checks. The package-based author requires a citation field by schema. Required does not mean accurate. A resolving citation proves the reference is real, not that the fact caused the claim.
- Provenance scope: `trace_claim` lands on the source conversation, not the exact sentence. The source passage is not stored.
- Vector provenance: When a claim has no inline citations the system may attach vector links. Treat these as nearby, not used.
- Faithfulness: A specification that serves cheaply and scores well on a held-out battery does not establish that it structurally matches a person’s reasoning. Distinguishable is not faithful. Only the subject can say where it is wrong.
- Corpus limits: The corpus is self-report. No third-party observation enters. There is no time axis. Changes over time are not recorded. The extractor only sees text. Tone, body language, and physical habit are absent.
- Scope of effect: It helps most where the model knows the person least. On a well-known public figure it often adds little.
- Operational notes:
  - Re-extracting from the same files without clearing prior state can leave stale vectors that cause over-deduplication. Clear both the fact store and vector store before a clean run.
  - Document mode asserts the subject is the document. Use it for documents only, not people.
  - Not on PyPI. Install from source.
  - Costs and run times vary with API pricing and corpus size.

## What it looks like

An excerpt from a real specification authored from about 1,900 conversations:

He operates from an uncompromising need for logical coherence that manifests as immediate challenge to any inconsistency, in systems, arguments, or his own positions. When he encounters a gap between stated beliefs and actual behavior, he treats it as personal failure requiring accountability rather than understanding, taking extreme ownership of every outcome while maintaining clear causal links between actions and results. This isn't philosophical posturing but lived practice: in trading, he waits for multiple confirming signals before entries, implements overlapping safety mechanisms through fixed dollar loss limits and systematic stop losses, yet struggles with the gap between knowing these rules and executing them consistently during early morning sessions when his energy is highest but discipline most vulnerable.

There are no questionnaires or forms. More examples at the link above.

## Use it

Register as an MCP server:

```
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

It loads the brief and layers as always-on context and exposes tools:

- get_brief(reason)
- recall_memories(query)
- search_facts(query, limit)
- trace_claim(claim_id)
- verify_claims(claim_id, layer)
- get_stats, get_call_log, get_help

It runs over stdio locally. Traces write to ~/.baselayer/sessions/<pid>/log.jsonl.

You can also paste the layers and brief into any system prompt. You will lose retrieval.

## Edit it

The layers are markdown files on disk. Open them. Delete what is wrong. Rewrite what is close. Add what your writing never said. The MCP server reads them from disk on each run.

Facts do not carry their own significance. Editing is where judgement enters. The artefact is text so you can apply it.

## What we tested

We evaluated on 14 historical subjects with public-domain autobiographies. A five-judge primary panel and a seven-judge sensitivity panel scored responses under a pre-registered plan. Full results are on the site and in the Beyond Recall paper (https://arxiv.org/abs/2605.28969).

- Direction reproduces across response models and battery-generation models. Absolute magnitudes are panel-dependent.
- Given a response, a judge can tell which specification produced it 51.6% of the time from the reasoning, and 13.4% from the decision alone. Chance is 11.1%. The reasoning carries the signal.
- Gains are largest where the model knows the person least.

Specifications change how decisions are argued in every situation tested. They change the decision itself in some.

## What it is not

- Not a memory system. It provides the lens that retrieved facts are read through.
- Not a recall benchmark competitor.
- Not an AI that knows you in the usual sense. It models how someone reasons, not facts about them.
- Not useful on subjects the model already knows well.
- Not the final word. This is one implementation of an interpretive layer.
- It is an interaction guide for an AI. The audience is the model, not the person.

## Privacy

Database, vectors, facts, and the specification live on your machine. There is no cloud sync, no accounts, and no telemetry. Extraction and authoring can call a model API if you configure one. Provider retention policies apply. Anthropic’s policy is here: https://www.anthropic.com/policies/privacy.

The artefact is local-first, model-agnostic, and portable.

## Reference

- Dataset: https://huggingface.co/datasets/agulaya24/beyond-recall
- Live specs (no auth): GET https://base-layer.ai/api/identity/{franklin,buffett,douglass}
- For agents: https://base-layer.ai/llms.txt, https://base-layer.ai/.well-known/agent-card.json, https://base-layer.ai/api/openapi.json

Docs:
- ARCHITECTURE.md: pipeline design
- PROJECT_OVERVIEW.md: components and composition
- DECISIONS.md: design decisions
- DESIGN_PRINCIPLES.md: principles
- ROADMAP.md
- docs/eval: evaluation frameworks and results

Pre-1.0, 490 tests.

## Reproducibility

The paper version is tagged v0.2.0 and is vendored into the memory-study-repo (https://github.com/agulaya24/memory-study-repo).

```
pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0
```

## Contributing

Contributions on evaluation, source-type adapters, alternative interpretive-layer implementations, and local model support are welcome. See CONTRIBUTING.md.

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

Apache 2.0. See LICENSE. The Beyond Recall paper is CC-BY 4.0.