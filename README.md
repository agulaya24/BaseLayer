# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://www.base-layer.ai) · [Paper](https://arxiv.org/abs/2605.28969) · [Research](https://www.base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

Base Layer reads a person's own writing and produces a **specification**: plain-text claims about
how that person reasons, communicates and decides, which an AI reads before working for them.

## What this is

An AI with memory can recall what someone said. It still has no access to how that person reads
those facts: what they count as evidence, what they treat as settled, where they refuse a
tradeoff. Recall is part of memory; interpretation is what makes it actionable. Base Layer is an
open-source pipeline for that interpretive layer above memory. It takes chat exports, journals,
notes or essays and writes three layers:

- **ANCHORS**: the certainties the person reasons from.
- **CORE**: how they communicate, and the context to read them in.
- **PREDICTIONS**: given a kind of situation, how they are likely to respond.

A model fine-tuned on someone's behavior cannot be inspected, disputed or corrected. A written
specification can. Every claim has an id, can say when it applies, can be traced to the facts it
cites (or, where it cites none, to the facts nearest it in meaning), and can be edited as text.

One claim, from the specification built from Zitkala-Sa's *American Indian Stories* (1921,
public domain):

> **P15 TOLERANT TO PEOPLE HARSH TO SYSTEMS.** Their severity is aimed at institutions and at
> settler power in the aggregate, not at individuals in front of them: in face-to-face
> disagreement, including religious disagreement, they extend respect, pity for suffering, and
> forgiveness over punishment. Predict the polemic in writing and the courtesy in the room.
>
> *Active when:* They disagree with, or witness the hardship of, a particular person present
>
> *Evidence:* [F-86fc472d] [F-cabf4c6c] [F-124a3cd5] ... (17 facts)

The `Evidence` line lists the facts the claim was written from. This example was made with an
earlier version of the [cited build](#the-cited-build-experimental), before own-words extraction;
in the cited build every claim must carry an `Evidence` line. The full specification is in
[examples/zitkala_sa/](examples/zitkala_sa/).

What it is not:

- **Not a memory system.** Memory systems retrieve facts. A specification is the lens those facts
  are read through, and it sits above whatever memory you use.
- **Not a biography or a summary.** It describes how someone reasons, not what happened to them.
- **Not confirmed.** It is a reading made by models. Only the person it describes can say whether
  it is them.
- **Not a portrait for the person.** It is written for the AI working for them; the person reads it
  to correct it.

## Quick start

To see a finished specification before spending anything, read
[examples/zitkala_sa/](examples/zitkala_sa/). To build one:

- **To try it and use the result in Claude Code today**, run `baselayer run` (below).
- **To have every claim cite the person's own quoted words and be checked afterwards**, use the
  [cited build](#the-cited-build-experimental). It takes several commands, costs several times
  more, and is not yet served to an agent automatically.

Requires Python 3.10 or later and git. Base Layer needs a model API key, which it reads from the
`ANTHROPIC_API_KEY` environment variable ([get a key](https://console.anthropic.com/account/keys));
set it in your shell profile or a secrets manager rather than typing it into a command. The last
line below needs [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
baselayer run chatgpt-export.zip     # or claude-export.json, a folder of journals, notes.md
claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp
```

Run it on your own writing, or on writing by someone who has agreed to it. The first time, it asks
for consent and for the name and pronouns of the person the writing is by
(`--accept-data-processing` answers the consent prompt). It prints an estimate of the extraction
cost and asks before spending; the estimate covers extraction only and has run low, so treat it
as a floor. Projected from measured builds, about 50,000 words of essays cost a dollar or two and a large chat
history about $50 ([What it costs](#what-it-costs)).

The result is three markdown files in `data/identity_layers/` inside the data root, which is
`~/.baselayer` unless you set `MEMORY_SYSTEM_ROOT` to an existing directory (a source checkout
differs; see [docs/PIPELINE.md](docs/PIPELINE.md)). The last line registers the MCP server (Model
Context Protocol, how Claude Code loads outside tools and context), which serves those files to
new Claude Code sessions in any folder. For anyone other than you, build into a fresh data root
(`export MEMORY_SYSTEM_ROOT=...` and `mkdir -p` it before `baselayer run`), so their facts do not mix with yours, and
register that server inside one project only:
`claude mcp add --scope local -e MEMORY_SYSTEM_ROOT=<that root> --transport stdio base-layer -- baselayer-mcp`.

Base Layer is pre-1.0 (version 0.5.0) and not on PyPI; the `baselayer` name there belongs to
another project.

## How it works

1. **Import.** The text goes into a local SQLite database, one row per turn, with who said it.
2. **Extract.** Claude Haiku 4.5 reads the conversations and draws short facts about the person.
   Each fact is labelled with a relation type from a suggested list of 46 (the extractor can add others), such as `prefers`, `avoids` or
   `believes`, points back to the conversation it came from, and is stored with a vector from a
   local embedding model.
3. **Write.** Claude Sonnet 4.6 writes the three layers in three separate calls, each from a
   selection made by code and capped in size, so on a large corpus each call reads a small share
   of the facts. The calls cannot see each other's output, so where two layers agree, neither
   copied the other.
4. **Link.** Each claim is linked to the facts nearest it in meaning, using those vectors, and a
   short Haiku pass checks the facts for tensions.

`baselayer run` is these steps in order. The first three are also their own commands (`import`,
`extract`, `author`), so you can resume or redo one; `baselayer verify --generate` rebuilds the
links.

## What you get

**From `baselayer run`**, served to Claude Code today:

- **Three layer files**, `anchors_v4.md`, `core_v4.md` and `predictions_v4.md` in
  `data/identity_layers/`, each claim with an id; ANCHORS claims carry an `Active when` line and
  PREDICTIONS a `When ...` trigger. Earlier generated
  versions are kept in `history/`.
- **The fact database:** every fact with its relation type, its source conversation and a vector,
  searchable over MCP.
- **Links from each claim to the facts nearest it in meaning**, each labelled with how it was made
  (`baselayer provenance`). They show that a fact is related, not that the writer used it.
- **A tension count:** up to 30 Haiku calls check pairs of facts for tension; the count is
  printed, not stored.
- **With `BASELAYER_TURN_CONTRACT=1`, a coverage gaps manifest** beside the layers, naming any part
  of the corpus no fact came from.
  `run` will not write layers over such gaps without `--accept-gaps`.

**From the [cited build](#the-cited-build-experimental)**, every output and every check, step by
step. Each line is in this repository unless it says otherwise.

| step | what you get | what it protects against |
|---|---|---|
| import | each turn labelled with its speaker and voice (typed or dictated by the person, the AI, another person, pasted text), from the source's own role field | other people's words, or the AI's, read as the person's |
| import | secrets with a recognisable shape (keys, tokens, card numbers) replaced by `[REDACTED:<kind>]` and counted | secrets stored, or sent to a model |
| extract | facts drawn only from the person's own turns, each carrying its evidence spans (the person's exact words), checked in code against the turn | facts the person never said |
| extract | a stamp on every fact (model, prompt hash, code commit, contract version), a run record (rejections by reason, API usage, anything suspect) and a chunk ledger | not knowing what made a fact; parts of the corpus skipped without notice |
| filter | each fact judged against its source as supported, stretch or not supported, with confirmed unsupported facts left out. **Not yet in this repository**; `distill --exclude-ids` takes its list | facts that say more than their quote |
| filter | stretch facts sorted by kind (generalised, added detail, reported, truncation), each kind with its own check. **Not yet in this repository** | a stretch read as plain support |
| distill | one counted verdict for every fact: part of a recurring theme, a one-off kept word for word, or not load-bearing | facts dropped unread |
| distill | contradictions between facts, carried unresolved | a conflict averaged away |
| distill | cited ids that were not in the input removed, and a one-off with an invented id dropped whole; a coverage gaps manifest per tree | invented citations; hidden gaps |
| author | every claim cites the facts it rests on (a strict schema; a claim left with no valid id is sent back) | claims with no evidence |
| author | an `Active when` condition on each claim | a claim applied in every situation |
| author | CONTESTED claims that keep both sides of conflicting evidence | a model choosing a side the person never chose |
| author | with the quote gate (`--quote-gate` on `python -m baselayer.distillation.author_from_package`; not on the `baselayer` command), every quoted phrase checked against the cited facts' spans; a phrase not found loses its quote marks | words put in the person's mouth |
| author | a stamp per layer: model, effort, tokens over every attempt, rates, cost, code commit | not knowing what wrote a layer, or what it cost |
| verify-spec | free checks: citations resolve, evidence spans and quotes are still found in their turns, voice, duplicate claims, identical conditions, claims whose facts all come from one area of activity, or rest partly on records rather than the person's prose | citations or quotes broken after authoring; a narrow claim stated as a general trait |
| verify-spec | free checks with their own inputs: overturned statements returning, predictions resting on too few separate occasions, contested sides that separate by date | a correction undone; a habit inferred from one day; change over time read as contradiction |
| verify-spec | model-judged checks, priced and sent only with `--run-model`: how well each cited fact supports its claim, voice, fidelity to the turn, contradictions and tensions between claims, and each apparent contradiction read in its source context | claims their facts do not support; contradictions nobody examined |
| verify-spec | a claim back-check by separate research judges (scope, reliance on stretch facts). **Not yet in this repository**; `--backcheck-results` reads its results | claims that reach past their evidence |
| consolidate | duplicate-claim groups, by shared evidence by default (a model judge is a separate step, `python -m baselayer.consolidation.build judge`), never rewriting a claim | one idea served twice |
| consolidate | the always-on set: by default, claims whose condition applies to every exchange. A rule by measured fire rate reads rates from outside; the measurement is **not yet in this repository** | standing claims buried among situational ones |
| consolidate | the trigger index, each trigger naming the claims to read, written as `served.txt` and `index.json`. By default each whole condition is one trigger and the run is flagged DEGRADED; a grouping file from `python -m baselayer.consolidation.build group` splits conditions into situation clauses, exact substrings of them | a claim never reached, or read outside its situation |
| consolidate | 14 integrity checks: claim text and fact ids unchanged, every claim reachable, served text matching its hash | consolidation altering or losing a claim |

Serving a cited build to an agent is not in this repository yet; the cited build section says how
to do it by hand.

## What it costs

API spend for one specification, by size of corpus. *Measured* figures are recorded token usage
from cited builds made in September and October 2026. *Projected* figures scale those builds'
per-fact costs, at 17 to 23 facts per 1,000 words of the person's writing. The cited build column
is the setup every measured build used: extraction and the leaf stage (one model call per 50 facts
per layer) sent through the Message Batches API at half price, and the layers written by Claude
Opus 5.5.

| corpus | facts | `baselayer run` | cited build |
|---|---|---|---|
| about 50,000 words of essays or posts | about 1,000 | $1 to $2, projected | $6 to $8, projected |
| about 150,000 words of posts and talk transcripts | about 3,000 | $3 to $4, projected | about $18, projected |
| about 300,000 words of long essays | about 5,000 | about $6, projected | $30.27, measured |
| a chat history of about 1.4 million words from the person | about 22,000 | about $47, projected | $112.32, measured |

Run as the plain command sequence instead, at full rate with Claude Opus 5 writing, the cited
build costs roughly 1.7 to 1.9 times as much.

- **`baselayer run`** is nearly all extraction: writing the three layers measured $0.12 on three
  runs in July 2026, whatever the corpus size. Its extractor has not been priced on a recorded
  run, so the column is projected from the cited build's extractor; read it as an order of
  magnitude.
- **The cited build** spends about two thirds to four fifths on its leaf stage (Claude Sonnet 5).
- **Rates**, per million input / output tokens, from Anthropic's
  [pricing page](https://platform.claude.com/docs/en/about-claude/pricing) as read on 19 October
  2026: Claude Haiku 4.5 $1 / $5, Claude Sonnet 4.6 $3 / $15, Claude Sonnet 5 $2 / $10, Claude
  Opus 5 $5 / $25, Claude Opus 5.5 $4 / $20; the Message Batches API at half these rates.

Stage by stage, with the basis of every figure: [docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end).

## Using it with an agent

- **Over MCP:** in Claude Code, the `claude mcp add` line above; in Claude Desktop, through its
  config file, as the recipe below shows. The server sends the three layers with every session and
  offers tools, among them `recall_memories` and `search_facts` to find facts, `trace_claim` to show what a
  claim rests on, and `verify_claims` to check it against the database. Some clients truncate long MCP instructions; the full text is always the
  `memory://specification` resource.
  ([recipes/serve_specification_via_mcp.md](recipes/serve_specification_via_mcp.md))
- **Any model, by hand:** put the three layer files in the system prompt. You lose fact search.

How an agent should read it:

1. A claim applies in the situation its `Active when` line (or a prediction's `When ...` trigger)
   names, not everywhere.
2. Facts call the subject "user" or "this person". That is the person the specification describes.

## How to check it

What is cited can be checked; what is not cited cannot. `baselayer run` lets the writer cite facts
but does not require it, and it links every claim to the facts nearest it in meaning. A link shows
that a fact is related, not that the writer used it. `baselayer provenance --claim P3` (or
`trace_claim` over MCP) prints each link with how it was made. For claims that must cite their
facts, with the citations checked in code, use the cited build.

What no check establishes is that the specification is faithful. A citation that resolves proves
the reference is real, not that the fact caused the claim. A specification that another model can
tell apart from others is distinguishable, which is not the same as faithful. Only the person can
confirm it. Every term used in a fixed sense is defined in [docs/DEFINITIONS.md](docs/DEFINITIONS.md).

## How to correct or update it

Facts do not carry their own significance. An extractor can find that someone rewrote a plan three
times; it cannot tell whether that was diligence or avoidance. Editing is where that judgement
enters, which is why the specification is text.

- **Edit the layers.** Open the files in `data/identity_layers/`. Delete what is wrong, rewrite
  what is close, add what the writing never said, then restart the MCP server. Running `author`
  or `run` again rewrites these files from the facts; earlier generated versions are kept in
  `data/identity_layers/history/`, but hand edits are not, so copy yours first.
- **Remove a wrong fact.** `baselayer review` walks through facts one at a time to hide or flag
  them; `baselayer forget` hides facts by id, by conversation, or all of them. Neither rewrites
  the layers already written: run `baselayer author` again, then `baselayer verify --generate`.
- **Add more text.** Run `baselayer run` on the new file. Extraction only processes what is new.
- **Start over or remove everything.** Use a new, empty data root (`baselayer forget --all` is not
  a reset). To remove everything, delete the data root and the MCP session logs in
  `~/.baselayer/sessions/`.

For an agent making these changes on someone's behalf, [docs/CORRECTIONS.md](docs/CORRECTIONS.md)
sets out how a correction moves through facts, layers and what is served, in order. Base Layer
Live, which keeps a specification updated and served as corrections arrive, is in development.

## The cited build (experimental)

The cited build makes the same kind of specification under stricter rules:

- **Own words only.** Facts may be drawn only from text the person typed or spoke, and each must
  quote it. A check in code, not in the prompt, drops any fact whose quote is not in the person's
  own turn.
- **Every fact considered.** Instead of writing from a selection, every fact first gets one
  verdict: part of a recurring theme, a one-off kept word for word, or not load-bearing. This is
  the leaf stage: Claude Sonnet 5, one call per 50 facts per layer (`--max-facts 50`).
- **Citations required.** Every claim must cite the facts it rests on (Claude Opus 5 writes the
  layers by default; the measured builds used Claude Opus 5.5). Where the evidence disagrees with itself, the claim is marked CONTESTED and both sides
  are kept; an agent should not resolve it.
- **Checks afterwards.** `verify-spec` re-checks every citation and quote against the database,
  and `consolidate` builds the always-on set and the index of situations. Every output and check
  is listed under [What you get](#what-you-get).

It takes eight different commands (`init`, `import`, `extract --turn-contract`, `distill` and
`assemble` per layer, `author-from-package`, `verify-spec`, `consolidate`) plus a file listing the
person's names, and costs several times what `baselayer run` does, most of it in the leaf stage:
$30.27 measured on about 300,000 words of essays and $112.32 on a large chat history with the batch
setup in docs/PIPELINE.md, about 1.7 to 1.9 times that with these commands
([What it costs](#what-it-costs)). The leaf and writing steps print an estimate
and refuse to start without a spend ceiling at or above it. The commands in order, the batch setup
the measured builds used, and what each step writes:
[docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end).

Nothing in this package serves a cited build to an agent yet. `consolidate` writes `served.txt`
(the always-on claims plus an index of situations) to put in a system prompt by hand, and
`index.json`, from which to add the claims a situation names when it applies.

What code checks in the cited build, and what remains a model's reading:

| step | checked by code | a model's reading, which can be wrong |
|---|---|---|
| import | who said each turn, from the source's own role field | none |
| extract | every quote exists word for word in the person's own turn | what fact a passage supports |
| distill | every fact's verdict is counted; a cited id that was not in the input is removed | which facts form a theme |
| author | every claim cites facts; with the quote gate (module only, off by default; the measured builds used it), every quoted phrase is in a cited fact's quote | how each claim is worded |
| verify-spec | citations resolve; quotes still match the source | with `--run-model`: whether the cited facts support the claim |

The quote check shows that a fact's evidence is text from a turn the source attributes to the
person, not that the fact reads it correctly. Every step's inputs, outputs and options, the quote gate, and a side-by-side table of both builds:
[docs/PIPELINE.md](docs/PIPELINE.md).

## Limits and what is not included yet

- **Self-report.** The corpus is what the person wrote or said: text only, nothing observed by
  others.
- **No time axis.** Claims are not dated; the specification does not record how the person
  changed.
- **Little gain on the well known.** It helps most where the model knows the person least.
- **Anthropic models.** Base Layer has been tested almost entirely on Anthropic's models, and
  every language-model call goes to Anthropic except extraction, which can run on a local model
  through Ollama (`baselayer extract --backend ollama`); a layer for other providers' models exists
  in `src/baselayer/llm_provider.py`, but no step uses it yet. The local models we tried fell well
  short of what the pipeline needs: Qwen 2.5 14B failed at writing across 12 attempts and was kept
  for extraction only ([D-030](docs/core/DECISIONS.md#d-030-model-role-separation--qwen-extracts-claude-writes)),
  and three other local models were not viable for classifying facts
  ([D-039](docs/core/DECISIONS.md#d-039-knowledge-tier-classification-session-2831)).
- **The cited build is experimental.** Its tests run against fake model clients, most of its design
  was measured on one book-length corpus of about 400 facts, and the builds in the cost table ran on a
  development version of this code with the same stages.
- **Not in this repository yet:** serving a cited build to an agent; one command for the cited
  build; the support filter that judges each fact against its quote before distillation, and the
  stretch sort; the research judges' claim back-check; and the fire-rate measurement for the
  always-on set. The measured builds in the cost table used the support filter, from scripts
  outside the package.

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
and no sync. Extraction, writing and the tension check send text to the Anthropic API, whose
[retention policy](https://www.anthropic.com/legal/privacy) applies; extraction can instead run on
a local model through Ollama (`baselayer extract --backend ollama`). The embedding model is
downloaded from Hugging Face on first use. Base Layer sends no usage data and turns off the
telemetry of its vector store, ChromaDB. A representation that is opaque to the person it
represents is built for someone else.

## Documentation

| topic | doc |
|---|---|
| every step, its options and costs, both builds side by side | [docs/PIPELINE.md](docs/PIPELINE.md) |
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
