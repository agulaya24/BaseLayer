# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://www.base-layer.ai) · [Paper](https://arxiv.org/abs/2605.28969) · [Research](https://www.base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

If something represents you, it has to know what it means to represent you. A person can write
that down themselves, or it can be derived from what they have written. Base Layer does the
second, as text the person can read, check and correct.

Memory gives an agent recall: what you said. It does not give the agent how you read those facts:
what you count as evidence, what you treat as settled, where you refuse a tradeoff. Facts do not
carry their own significance. An agent without that reading has not forgotten something about
you; it never knew it.

Base Layer takes a person's own writing and produces a **specification**: plain-text claims about
how that person reasons, communicates and decides, which an agent reads before acting for them.
In the cited build every claim cites the facts it rests on and every fact quotes the person's own
words, so each claim can be traced to the words it came from.

This README is written for people and for the agents working for them. If you are an agent, start
with [Using it with an agent](#using-it-with-an-agent) and [AGENTS.md](AGENTS.md).

## What this is

A specification has three layers:

- **ANCHORS**: where the person reasons from, the certainties that settle a question before the
  details arrive.
- **CORE**: how they communicate, and the context to read them in.
- **PREDICTIONS**: given a kind of situation, how they are likely to respond.

It is plain text, so it can be read, disputed and corrected. Every claim has an id and can say when it applies. One claim, from the
specification built from Zitkala-Sa's *American Indian Stories* (1921, public domain):

> **P15 TOLERANT TO PEOPLE HARSH TO SYSTEMS.** Their severity is aimed at institutions and at
> settler power in the aggregate, not at individuals in front of them: in face-to-face
> disagreement, including religious disagreement, they extend respect, pity for suffering, and
> forgiveness over punishment. Predict the polemic in writing and the courtesy in the room.
>
> *Active when:* They disagree with, or witness the hardship of, a particular person present
>
> *Evidence:* [F-86fc472d] [F-cabf4c6c] [F-124a3cd5] ... (17 facts)

The `Evidence` line lists the facts the claim was written from. This example was made with an
earlier version of the cited build, before its facts quoted the text they came from. The full
specification is in [examples/zitkala_sa/](examples/zitkala_sa/).

What it is not:

- **Not a memory system.** Memory systems retrieve facts. A specification is the lens those facts
  are read through, and it sits above whatever memory you use.
- **Not a copy of the person.** It is closer to what someone who knows you notices about how you
  approach a situation, written down for an agent.
- **Not a biography or a summary.** It describes how someone reasons, not what happened to them.
- **Not confirmed.** It is a reading made by models, and it is not confirmed until the person it
  describes says it is them.
- **Not a portrait for the person.** It is written for the agent working for them; the person reads
  it to correct it.

## How it works

The cited build is how Base Layer is meant to make a specification, in six steps. Each step has a
rule; [How to check it](#how-to-check-it) sets out which are enforced in code and which are
instructions to the model.

1. **Import.** The text goes into a local SQLite database, one row per turn (one message),
   labelled with who said it from the source's own role field, so the AI's words are not read as
   the person's; text the person pasted in is detected and set aside by default. Secrets with a
   recognisable shape (keys, tokens, card numbers) are replaced by `[REDACTED:<kind>]`.
2. **Extract: own words only.** Claude Haiku 4.5 draws short facts from the person's own turns
   only. Each fact quotes the words it rests on, and a check in code drops any fact whose quote
   is not in that turn.
3. **Distill: every fact considered.** Instead of writing from a selection, every fact gets one of
   three verdicts (folded into a theme, a one-off kept word for word, or not load-bearing), and
   code counts that none is missing. The model is told to carry contradictions between facts forward
   unresolved. This is the leaf stage (each model call on a chunk of facts is a leaf), on Claude
   Sonnet 5; `assemble` then packages each layer's results without a model call.
4. **Author: citations required.** Claude Opus 5 writes each layer by default. Code requires every
   claim to cite the facts it rests on: an id that was not in the input is removed, and when any
   claim is left with no valid id the layer is requested again. The
   model is told to mark a claim CONTESTED where the evidence disagrees with itself and to keep
   both sides. Each claim can carry an `Active when` condition; predictions are told to name a
   concrete situation.
5. **Verify.** `verify-spec` re-checks every citation and quote against the database at no cost.
   Checks that a model judges, such as whether the cited facts support the claim, are priced and
   sent only with `--run-model`.
6. **Consolidate.** `consolidate` groups duplicate claims by shared evidence without rewriting
   any, picks the always-on claims, and builds an index of situations from the `Active when`
   conditions, each naming the claims to read when it applies. Fourteen integrity checks confirm that no claim text or fact id changed and that every claim can be reached.

Extraction and authoring stamp what they made with the model that made it, and with the code
commit when run from a clone of the repository (`unknown` for a pip install). Extraction and
distillation write down any part of the corpus they did not cover.

Today the cited build is eight commands, not one, and it is not yet served to an agent
automatically: `consolidate` writes files you put in a system prompt by hand
([Using it with an agent](#using-it-with-an-agent)).

**`baselayer run`** is the older, quicker pipeline. It is one command, and its result is served to
Claude Code over MCP (Model Context Protocol) today. It makes far fewer checks. Extraction does not require the person's
own words unless `BASELAYER_TURN_CONTRACT=1` is set. Claude Sonnet 4.6 writes the three layers in
three separate calls, each from a selection of facts made by code and capped in size, so on a
large corpus each call reads a small share of the facts. Claims may cite facts but need not, and
there is no verification or consolidation step. Afterwards each claim is linked to the facts
nearest it in meaning, which shows that a fact is related, not that the writer used it.

## Quick start

To see a finished specification before spending anything, read
[examples/zitkala_sa/](examples/zitkala_sa/).

Requires Python 3.10 or later and git. Base Layer needs a model API key, which it reads from the
`ANTHROPIC_API_KEY` environment variable ([get a key](https://console.anthropic.com/account/keys));
set it in your shell profile or a secrets manager rather than typing it into a command.

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
```

Run it on your own writing, or on writing by someone who has agreed to it. Use the cited build
when you want every claim traceable to the person's quoted words and checked; use `baselayer run`
to try Base Layer in one command and have Claude Code load the result.

**The cited build** is eight commands into a fresh data root (the directory that holds the
database; see below): `init`, `import`,
`extract --turn-contract`, `distill` and `assemble` for each layer, `author-from-package`,
`verify-spec` and `consolidate`, plus a file listing the names the person goes by. `distill` and
`author-from-package` print an estimate and refuse to start without a spend ceiling at or above
it, and until you confirm the date of the rate table they price from. The commands in order, and the batch setup the measured builds used:
[docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end).

**`baselayer run`**, to try it and use the result in Claude Code today (the second line needs
[Claude Code](https://docs.anthropic.com/en/docs/claude-code)):

```bash
baselayer run chatgpt-export.zip     # or claude-export.json, a folder of journals, notes.md
claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp
```

The first time, it asks for consent and for the name and pronouns of the person the writing is by
(`--accept-data-processing` answers the consent prompt). It prints an estimate of the extraction
cost and asks before spending; the estimate covers extraction only and has run low, so treat it
as a floor.

The result is three markdown files in `data/identity_layers/` inside the data root, which is
`~/.baselayer` unless you set `MEMORY_SYSTEM_ROOT` to an existing directory (a source checkout
differs; see [docs/PIPELINE.md](docs/PIPELINE.md)). The second line registers the MCP server
(Model Context Protocol, how Claude Code loads outside tools and context), which serves those
files to new Claude Code sessions in any folder. For anyone other than you, build into a fresh
data root (`export MEMORY_SYSTEM_ROOT=...` and `mkdir -p` it first), so their facts do not mix
with yours, and register that server inside one project only:
`claude mcp add --scope local -e MEMORY_SYSTEM_ROOT=<that root> --transport stdio base-layer -- baselayer-mcp`.

Base Layer is pre-1.0 (version 0.5.0) and not on PyPI; the `baselayer` name there belongs to
another project.

## What you get

**From the cited build**, in the folders the commands in
[docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end) name:

- **The specification** (`spec/`): for each layer a readable `<layer>.md`, the same claims as
  `<layer>.json`, and a stamp with the model, effort, tokens, cost and (from a clone) code commit, plus a
  coverage gaps manifest.
- **The fact database:** every fact with the person's words it quotes, the turn they came from,
  and a stamp of the model, prompt and code that made it; a run record of what extraction
  rejected and why.
- **The leaf trees:** every fact's verdict, counted, and the contradictions carried forward.
- **A verification report** (`verify/`) from `verify-spec`.
- **What to serve** (`served/`): `served.txt`, the always-on claims in full plus one line per
  situation naming the claims to read, and `index.json`, each claim's full text, fact ids and
  contested note.

**From `baselayer run`**, served to Claude Code today:

- **Three layer files**, `anchors_v4.md`, `core_v4.md` and `predictions_v4.md` in
  `data/identity_layers/`, each claim with an id; ANCHORS claims carry an `Active when` line and
  PREDICTIONS a `When ...` trigger. Earlier generated versions are kept in `history/`.
- **The fact database:** every fact with its relation type, its source conversation and a vector,
  searchable over MCP.
- **Links from each claim to the facts nearest it in meaning**, each labelled with how it was made
  (`baselayer provenance`).
- **A tension count:** up to 30 Claude Haiku 4.5 calls check pairs of facts for tension; the count
  is printed, not stored.

## What it costs

API spend for one specification, by size of corpus. *Measured* figures are recorded token usage
from cited builds made in September and October 2026. *Projected* figures scale those builds'
per-fact costs, at 17 to 23 facts per 1,000 words of the person's writing. The cited build column
is the batch setup every measured build used: extraction and the leaf stage (one model call per 50 facts
per layer) sent through the Message Batches API at half price, and the layers written by Claude
Opus 5.5.

| corpus | facts | cited build, batch setup | `baselayer run` |
|---|---|---|---|
| about 50,000 words of essays or posts | about 1,000 | $6 to $8, projected | $1 to $2, projected |
| about 150,000 words of posts and talk transcripts | about 3,000 | about $18, projected | $3 to $4, projected |
| about 300,000 words of long essays | about 5,000 | $30.27, measured | about $6, projected |
| a chat history of about 1.4 million words from the person | about 22,000 | $112.32, measured | about $47, projected |

- **The cited build** spends about two thirds to four fifths on its leaf stage. Run as the plain
  command sequence instead, at full rate with Claude Opus 5 writing, it costs roughly 1.6 to 1.9
  times as much.
- **`baselayer run`** is nearly all extraction: writing the three layers measured about $0.12 on
  three corpora of about 600 to several thousand facts in July 2026; it does not grow with the
  corpus, because each layer reads a capped selection. Its extractor has not been priced on a recorded
  run, so the column is projected from the cited build's extractor; read it as an order of
  magnitude.
- **Rates**, per million input / output tokens, from Anthropic's
  [pricing page](https://platform.claude.com/docs/en/about-claude/pricing) as read on 19 October
  2026: Claude Haiku 4.5 $1 / $5, Claude Sonnet 4.6 $3 / $15, Claude Sonnet 5 $2 / $10, Claude
  Opus 5 $5 / $25, Claude Opus 5.5 $4 / $20; the Message Batches API at half these rates.

Stage by stage, with the basis of every figure: [docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end).

## Using it with an agent

- **A cited build, by hand:** put `served.txt` in the system prompt, and when a situation it lists
  applies, add the claims it names from `index.json`. Serving a cited build automatically is not
  in this repository yet.
- **A `baselayer run` build, over MCP:** in Claude Code, the `claude mcp add` line above; in
  Claude Desktop, through its config file, as
  [recipes/serve_specification_via_mcp.md](recipes/serve_specification_via_mcp.md) shows. The
  server sends the three layers with every session and offers tools, among them
  `recall_memories` and `search_facts` to find facts, `trace_claim` to show what a claim rests on,
  and `verify_claims` to check it against the database (it writes its results there). Some clients truncate long MCP
  instructions; the full text is always the `memory://specification` resource.
- **Any model, by hand:** put the three layer files in the system prompt. You lose fact search.

How an agent should read it:

1. A claim with an `Active when` line (or a prediction's `When ...` trigger) applies when that
   situation holds, not everywhere. The always-on claims at the top of `served.txt` apply in every
   exchange. A claim with no condition is context to read the person in, not a rule for every
   situation.
2. A claim marked CONTESTED keeps both sides of evidence that disagrees. Do not resolve it for the
   person.
3. Facts call the subject "user" or "this person". That is the person the specification describes.

## How to check it

A claim can be checked only if it cites its facts. In the cited build every claim cites its
facts and every fact quotes the person, so a reader can follow a claim back to the words it came
from, and `verify-spec` re-checks that those citations and quotes still hold.

### What is checked by code, and what is a model's reading

| step | checked by code | a model's reading, which can be wrong |
|---|---|---|
| import | who said each turn, from the source's own role field | none |
| extract | every quote exists word for word in the person's own turn | what fact a passage supports |
| distill | every fact's verdict is counted; a cited id that was not in the input is removed | which facts form a theme |
| author | every claim cites facts; with the quote gate, every quoted phrase is in a cited fact's quote | how each claim is worded |
| verify-spec | citations resolve; quotes still match the source | with `--run-model`: whether the cited facts support the claim |

The quote gate is off by default and runs only through
`python -m baselayer.distillation.author_from_package --quote-gate`; the measured builds used it.
The quote check shows that a fact's evidence is text from a turn the source attributes to the
person, not that the fact reads it correctly.

`baselayer run` lets the writer cite facts but does not require it, and links every claim to the
facts nearest it in meaning. `baselayer provenance --claim P3` (or `trace_claim` over MCP) prints
each link with how it was made.

No check here shows that the specification is faithful. A citation that resolves proves
the reference is real, not that the fact caused the claim. A specification that another model can
tell apart from others is distinguishable, which is not the same as faithful. Only the person can
confirm it. Every term used in a fixed sense is defined in [docs/DEFINITIONS.md](docs/DEFINITIONS.md).

## How to correct or update it

Facts do not carry their own significance. An extractor can find that someone rewrote a plan three
times; it cannot tell whether that was diligence or avoidance. That judgement comes from the person,
by editing the text.

- **Edit a cited build.** Change a claim in `spec/<layer>.md` and `spec/<layer>.json` together
  (`consolidate` fails when they disagree), then run `verify-spec` and `consolidate` again.
- **Edit a `baselayer run` build.** Open the files in `data/identity_layers/`. Delete what is
  wrong, rewrite what is close, add what the writing never said, then restart the MCP server.
  Running `author` or `run` again rewrites these files from the facts; earlier generated versions
  are kept in `data/identity_layers/history/`, but hand edits are not, so copy yours first.
- **Remove a wrong fact.** `baselayer review` walks through facts one at a time to hide or flag
  them; `baselayer forget` hides facts by id, by conversation, or all of them. Neither rewrites
  the layers already written: for a `baselayer run` build, run `baselayer author` again, then
  `baselayer verify --generate`; for a cited build, start again from `distill`.
- **Add more text.** For a `baselayer run` build, run `baselayer run` on the new file; extraction
  only processes what is new. For a cited build, `baselayer import` the file, run
  `baselayer extract --turn-contract`, then rebuild from `distill`.
- **Start over or remove everything.** Use a new, empty data root (`baselayer forget --all` is not
  a reset). To remove everything, delete the data root, the MCP session logs in
  `~/.baselayer/sessions/`, and any `trees/`, `packages/`, `spec/`, `verify/` and `served/`
  directories you created for a cited build.

For an agent making these changes on someone's behalf, [docs/CORRECTIONS.md](docs/CORRECTIONS.md)
sets out how a correction moves through facts, layers and what is served, in order. Base Layer
Live, which keeps a specification updated and served as corrections arrive, is in development.

## Limits and what is not included yet

- **Self-report.** The corpus is what the person wrote or said: text only, nothing observed by
  others.
- **No time axis.** Claims are not dated; the specification does not record how the person
  changed.
- **Little gain on the well known.** It helps most where the model knows the person least.
- **Anthropic models.** Base Layer has been tested almost entirely on Anthropic's models, and
  every language-model call goes to Anthropic except extraction, which can run on a local model
  through Ollama (`baselayer extract --backend ollama`). The local models we tried fell well short
  of what the pipeline needs: Qwen 2.5 14B failed at writing across 12 attempts and was kept for
  extraction only ([D-030](docs/core/DECISIONS.md#d-030-model-role-separation--qwen-extracts-claude-writes)).
- **The cited build is experimental.** Its tests run against fake model clients, most of its design
  was measured on one book-length corpus of about 400 facts, and the builds in the cost table ran on a
  development version of this code with the same stages.
- **Not in this repository yet:** one command for the cited build; serving a cited build to an
  agent; the support filter that judges each fact against its quote before distillation, and a sort
  of the facts that go beyond their quote by how they do so; a separate check by model judges of
  each claim's scope; and the
  fire-rate measurement for choosing always-on claims. The measured builds in the cost table used
  the support filter, from scripts outside the package. [ROADMAP.md](ROADMAP.md) lists each.

## Research

The *Beyond Recall* study tested specifications on 14 historical subjects with public-domain
autobiographies, scored by panels of model judges. Prediction is the test of whether a
specification represents the person accurately, not the goal.

- Gains were largest where the model knew the person least.
- The direction reproduced across response models; absolute sizes depend on the judge panel.

A later test, separate from the paper, asked where the difference shows. Given recorded responses
to the same decisions under nine specifications (some of them variants of one another), a
deliberately simple classifier, not a model judge, named the right specification 51.6% of the time
from the reasoning and 13.4% from the decision alone, against 11.1% chance. Differences of tone
and length were not ruled out.

Specifications change how decisions are argued in every situation tested, and change the decision
itself in some. An analysis plan was locked partway through the study, after most data had been
collected; it is not a preregistration of the full study, and it names a seven-judge panel while
the primary results use five
([ANALYSIS_PLAN_LOCK.md](https://github.com/agulaya24/beyond-recall/blob/master/docs/ANALYSIS_PLAN_LOCK.md)).
Method and results: the [paper](https://arxiv.org/abs/2605.28969), the
[research page](https://www.base-layer.ai/research), and the
[study code and data](https://github.com/agulaya24/beyond-recall). The version the paper used:

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0
```

## Privacy

The database, facts and specification are stored only on your machine. There are no accounts
and no sync. Extraction, distillation, writing, the tension check and any check a model judges send
text to the Anthropic API, whose [retention policy](https://www.anthropic.com/legal/privacy) applies; extraction can instead
run on a local model through Ollama (`baselayer extract --backend ollama`). The embedding model is
downloaded from Hugging Face on first use. Base Layer sends no usage data and turns off the
telemetry of its vector store, ChromaDB. A specification is meant to be legible to the
person it describes and under their control: they can read it, correct it, or delete it.

## Documentation

| topic | doc |
|---|---|
| every step, its options and costs, and the cited build's commands | [docs/PIPELINE.md](docs/PIPELINE.md) |
| how the code is organised and which tables hold what | [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md) |
| what each term means in this project | [docs/DEFINITIONS.md](docs/DEFINITIONS.md) |
| how to correct a specification, and what to rebuild after | [docs/CORRECTIONS.md](docs/CORRECTIONS.md) |
| the principles the design follows (dated March 2026) | [docs/core/DESIGN_PRINCIPLES.md](docs/core/DESIGN_PRINCIPLES.md) |
| why each design decision was made | [docs/core/DECISIONS.md](docs/core/DECISIONS.md) |
| what is planned, what is not yet in the package, and the open questions | [ROADMAP.md](ROADMAP.md) |
| known issues found by running the pipeline | [docs/PIPELINE_ISSUES.md](docs/PIPELINE_ISSUES.md) |
| what changed in each version | [CHANGELOG.md](CHANGELOG.md) |
| where Base Layer sits, for a newcomer or an agent | [ORIENTATION.md](ORIENTATION.md), and for coding agents [AGENTS.md](AGENTS.md) |
| earlier evaluation specs and reports (mostly early 2026; the paper is the current record) | [docs/eval/](docs/eval/) |
| example specifications | [examples/](examples/): `zitkala_sa/` is the cited example; the other seven predate citations |
| how to contribute, or report a security issue | [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) |

Contributions on evaluation, source adapters, other interpretive-layer implementations and local
models are welcome: [CONTRIBUTING.md](CONTRIBUTING.md).

```bibtex
@software{baselayer2026,
  title     = {Base Layer: An Open-Source Reference Pipeline for the Interpretive Layer Above Memory},
  author    = {Gulaya, Aarik},
  year      = {2026},
  url       = {https://github.com/agulaya24/BaseLayer},
  license   = {Apache-2.0}
}
```

Apache 2.0. See [LICENSE](LICENSE). The *Beyond Recall* paper is CC BY 4.0.
