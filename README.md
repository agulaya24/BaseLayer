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
IMPORT     Your text into a local database, one row per turn, recording who said it
EXTRACT    Pull candidate facts about preferences, rules, habits
           (turn-contract mode: only the subject's own turns can be cited, and every fact
           must quote them verbatim; a gate in code enforces it)
DISTILL    Sort facts into recurring themes, one-offs, and not load-bearing
           (optional: show each fact's verbatim own-word spans to the summariser; all three
           layers can run in one batch submission; a reviewed exclusion list can leave facts out)
ASSEMBLE   Package each layer so writing can respect those groups
           (a package too large for one request is split into shards; nothing is dropped)
AUTHOR     Write the layers as readable text with citations where required
           (optional quote gate: quoted phrases must be the person's own words from cited facts)
           The three layers are the specification.
COMPOSE    Optional, separate, off by default: merge the layers into one prose brief
           (`baselayer compose`, or `--compose` on author-from-package)

EMBED      Side branch. Build a vector index for search and verification. The writer does not read it.
VERIFY     After authoring, a separate read-only check of the specification against its evidence.
```

Models by stage, as the code defaults them: extraction on Claude Haiku 4.5, distillation leaves on
Claude Sonnet 5, layers (and the optional brief) on Claude Opus 5 (Opus 5.5 is supported with `--model
claude-opus-5-5`). The static `baselayer author` path is separate and configured in `config.py`.
Every billed distillation or authoring run prints an estimate first and refuses to start without a
spend ceiling at or above it. Detail and the full option list: `docs/core/DISTILLATION.md`.

Not in this package: merging near-duplicate claims after authoring (consolidation) exists only as a
prototype outside this repository. A sharded layer can therefore repeat a pattern once per shard.

**The turn contract** (`docs/core/TURN_CONTRACT.md`, opt-in with `BASELAYER_TURN_CONTRACT=1` or
`baselayer extract --turn-contract`) is how a specification is kept to the person's own words.
- **Import** labels every turn with its speaker, taken from the source, and a voice class. Only
  text the person typed or spoke can be cited. Assistant turns, other people, pasted material,
  tool output, harness prompts and compaction summaries are context only. Pasted text is excluded
  by default and can be allowlisted.
- **Extraction** reads whole turns plus preceding context. It must ground each fact in verbatim
  spans of the person's own turns.
- **The gate** is code, not the prompt. It rejects any fact whose spans are missing, name a
  non-own turn, do not match the turn's text, or are too short or too long. Every rejection is
  counted by reason in a per-run record.
- **The chunk ledger** (`extraction_chunks`) makes every chunk its own checkpoint, sequential and
  batch: its facts, its row and the conversation's logged count commit together. A done chunk is
  never called again, a failed one is retried by the next run, and one that fails its two retries
  (or can no longer be rebuilt) is quarantined. Only content failures (truncated, unparseable,
  refused, input rejected) count toward that; an API access failure (network, timeout, 429, 5xx,
  auth, an expired batch) leaves the chunk failed and retryable and never quarantines it.
  `baselayer chunks list|retry|quarantine|ack-model` shows and moves them. Extraction exits 1
  while any chunk is pending or failed, and `baselayer run` does not author over quarantined
  chunks unless given `--accept-gaps`. A conversation with a quarantined chunk is marked partial,
  not extracted. Quarantined chunks are stated beside every authored artifact, never in its text:
  `baselayer run`/`author`, `distill` and `author-from-package` (with `--db`) write a
  `coverage_gaps*.json` manifest stamped with the run id, and `baselayer chunks list --review`
  lists each with why it failed. A corpus extracted before the ledger counts as done.
- **The model is recorded, never acted on.** Every ledger row records the extraction model that
  settled it; work extracted before that takes its model from its facts' `extraction_model`
  stamps (listed as mixed when they disagree, `unknown` when none carries one). A model change
  re-runs nothing: done work made by another model is a backlog (`baselayer chunks list
  --backlog`), announced in one line at the end of each run and acknowledged with `baselayer
  chunks ack-model`. Naming an already extracted conversation (`python -m
  baselayer.extract_facts --conversation ID --reason ...`) or its legacy block (`baselayer chunks
  retry`) re-extracts nothing; the request goes on the review backlog (`baselayer chunks list
  --review`).

Layers:

- ANCHORS: Axioms the person reasons from.
- CORE: Communication patterns and context modes.
- PREDICTIONS: Behavioral triggers with detection cues and directives.

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
baselayer author
baselayer compose                         # optional: a unified prose brief from the layers
```

`baselayer run` stops after the layers (and the traceability step); it does not compose a brief.
Under the turn contract it also stops before authoring while the chunk ledger holds quarantined
chunks, unless given `--accept-gaps` (`baselayer chunks list --review` lists them, with why each
failed). The gaps are then stated in `coverage_gaps_<spec_run_id>.json` beside the layers, and each
layer's frontmatter points to it; the layer text is unchanged.

Experimental distillation path (billed runs need the rate table confirmed and a spend ceiling;
`<table date>` is `RATES_AS_OF` in `src/baselayer/distillation/spend.py`):

```
baselayer distill --layer anchors --max-facts 50 --out trees/anchors.json \
    --rates-confirmed <table date> --confirm-spend <usd>
# repeat for --layer core and --layer predictions
baselayer assemble trees/anchors.json --out packages/anchors.json
# repeat for core and predictions
baselayer author-from-package --package packages/anchors.json --package packages/core.json \
    --package packages/predictions.json --outdir spec_out/ \
    --rates-confirmed <table date> --confirm-spend <usd>
```

The batch leaf path, own-word spans at the leaves, the quote gate and resuming a batch run through
`python -m baselayer.distillation.<module>`; the commands are in `docs/core/DISTILLATION.md`.

## Auditability / what you can verify

- You can trace a written claim back to its cited facts. On a corpus extracted under the turn contract, each fact then leads to the turn it rests on and the verbatim words it quotes. On a legacy corpus the second step lands on the conversation, not the exact sentence, because the source passage is not stored.
- Every fact is stamped with the extraction model, prompt hash, git commit and a repo-relative code path. Gated facts also carry the contract version.
- `baselayer verify-spec` checks a finished specification. It resolves every citation and re-gates every evidence span. It can also run model-judged checks of support, voice and fidelity, which are dry-run and priced by default. It reads the corpus read-only and writes only to its output directory.
- Checks run over the citation graph:
  - Vector proximity: the words in the claim should be close to the words in its cited facts.
  - Recurrence gating: a theme should not rest on a single one-off mention.
  - Cross-domain span: support should not come only from one narrow source type or topic.
  - Optional NLI: a local entailment model can score whether cited facts support the claim. This audits data quality. It does not prove causation.

Not all provenance is a citation. ANCHORS and PREDICTIONS often synthesize across facts. When a claim carries no inline citations, the system links nearest facts by embedding as vector provenance. That link shows proximity, not that the model asserted the link. `trace_claim` prints the link method for each row.

Read auditable as: what is cited can be checked. It does not mean everything is cited.

## Status and limits

- Experimental components: Distillation, assembly, and the package-based author are experimental in this repository. The distillation tests are mutation tests over the citation audit, call-shape tests of the author's request, and end-to-end runs against fake clients; they do not call a model. Most measurements behind the distillation design come from a single 407-fact corpus. The full path (batch leaves with own-word spans, sharded packages, authoring with the quote gate) has run end to end on one large corpus, once. Study harnesses that ship here may emit unstripped outputs. Use with care and inspect outputs.
- Two authoring paths: The legacy authoring path still ships. It does not guarantee inline citations, so verification that depends on parsing citations may produce no checks. The package-based author requires a citation field by schema. Required does not mean accurate. A resolving citation proves the reference is real, not that the fact caused the claim.
- Provenance scope: on a legacy corpus `trace_claim` lands on the source conversation, not the exact sentence. Under the turn contract it lands on the turn and the quoted span.
- What the gate proves: every stored fact rests on words that exist in the source and that the person typed or spoke. It does not prove the fact is a correct reading of those words. That is a judgement, so verification samples it.
- Pasted text: pasted material can be the person's own writing (a draft, a note). The importer cannot tell, so it excludes pasted segments, counts them, and leaves an allowlist by turn id.
- Vector provenance: When a claim has no inline citations the system may attach vector links. Treat these as nearby, not used.
- Faithfulness: A specification that serves cheaply and scores well on a held-out battery does not establish that it structurally matches a person’s reasoning. Distinguishable is not faithful. Only the subject can say where it is wrong.
- Corpus limits: The corpus is self-report. No third-party observation enters. There is no time axis. Changes over time are not recorded. The extractor only sees text. Tone, body language, and physical habit are absent.
- Scope of effect: It helps most where the model knows the person least. On a well-known public figure it often adds little.
- Operational notes:
  - Rebuild into a fresh corpus directory, never a reset one. `baselayer forget --all` keeps the extraction log, so a later extract finds nothing to do, and `init --force` deletes nothing. If an existing corpus must be cleared, the full extraction reset is `python -m baselayer.extract_facts --reset`. Stale vectors left behind by a partial clear cause over-deduplication.
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

It loads the layers as always-on context and exposes tools (`get_brief` returns the brief only
if one was composed):

- get_brief(reason)
- recall_memories(query)
- search_facts(query, limit)
- trace_claim(claim_id)
- verify_claims(claim_id, layer)
- get_stats, get_call_log, get_help

It runs over stdio locally. Traces write to ~/.baselayer/sessions/<pid>/log.jsonl.

You can also paste the layers (and a brief, if you composed one) into any system prompt. You will
lose retrieval.

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

Pre-1.0. The offline test suite runs with `pytest tests -q`.

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