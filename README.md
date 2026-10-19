# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://www.base-layer.ai) · [Paper](https://arxiv.org/abs/2605.28969) · [Research](https://www.base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

To represent you, an AI agent has to understand you.

Base Layer is an open-source pipeline that turns your writing into a specification for AI agents. It derives plain-text claims about how you reason, communicate and decide from your chats, essays, notes and transcripts. An agent reads the specification before acting for you.

Every claim cites the facts it rests on. Every fact quotes your own words. You can check any claim and correct it.

If you are an agent, start with [Using it with an agent](#using-it-with-an-agent) and [AGENTS.md](AGENTS.md).

## How it works

Each step produces an output you can inspect and a check. The table follows the cited build in order. A turn is one message. The leaf stage is `distill`, with one model call per chunk of facts.

| step | what you get | what it protects against |
|---|---|---|
| import | each turn labelled with its speaker and voice (typed or dictated by the person, the AI, another person, pasted text), using the source's own role field | other people's words, or the AI's, attributed to the person |
| import | secrets with a recognisable shape (keys, tokens, card numbers) replaced by `[REDACTED:<kind>]` and counted | secrets stored or sent to a model |
| extract | facts drawn only from the person's own turns, with evidence spans quoting their exact words, checked in code against the turn | facts the person never said |
| extract | a stamp on every fact (model, prompt hash, code commit, contract version), a run record (rejections by reason, API usage, anything suspect) and a chunk ledger | unknown fact origins; parts of the corpus skipped without notice |
| filter | each fact judged against its source as supported, stretch (says more than its quote) or not supported; confirmed unsupported facts excluded. **Not yet in this repository**; `distill --exclude-ids` takes its list | facts that say more than their quote |
| filter | stretch facts sorted by kind (generalised, added detail, reported, truncation), with a check for each kind. **Not yet in this repository** | a stretch read as plain support |
| distill | one counted verdict per fact, marking it as part of a recurring theme, a one-off kept word for word, or not load-bearing | facts dropped unread |
| distill | contradictions between facts, with instructions to carry them forward unresolved | a conflict averaged away |
| distill | cited ids absent from the input removed; a one-off with an invented id dropped whole; a coverage gaps manifest for each layer | invented citations; hidden gaps |
| author | every claim citing facts under a strict schema; the layer requested again if any claim has no valid id | claims with no evidence |
| author | an optional `Active when` condition on a claim; instructions that every prediction must name a concrete situation | a claim applied in every situation |
| author | instructions to mark claims CONTESTED where evidence disagrees and keep both sides | a model choosing a side the person never chose |
| author | with the quote gate (off by default; `--quote-gate` on `python -m baselayer.distillation.author_from_package`, not on the `baselayer` command), every quoted phrase checked against the cited facts' spans; unmatched phrases lose their quote marks | words put in the person's mouth |
| author | a stamp per layer recording model, effort, tokens over every attempt, rates, cost and code commit | unknown layer authorship or cost |
| verify-spec | free checks of citation resolution, evidence spans and quotes in their turns, voice, duplicate claims, identical conditions, and claims resting partly on records rather than the person's prose | citations or quotes broken after authoring; claims resting on records instead of the person's words |
| verify-spec | free checks with their own inputs for overturned statements returning, predictions based on too few separate occasions, and contested sides that separate by date | a correction undone; a habit inferred from one day; change over time read as contradiction |
| verify-spec | model-judged checks, priced and sent only with `--run-model`, of fact support for each claim, voice, fidelity to the turn, contradictions and tensions between claims, and each apparent contradiction in its source context | unsupported claims; unexamined contradictions |
| verify-spec | a claim back-check by separate research judges for scope and reliance on stretch facts. **Not yet in this repository**; `--backcheck-results` reads its results | claims that reach past their evidence |
| consolidate | duplicate-claim groups based on shared evidence by default; a model judge is a separate step, `python -m baselayer.consolidation.build judge`; no claims rewritten | one idea served twice |
| consolidate | an always-on set containing, by default, claims whose condition applies to every exchange; a measured-fire-rate rule reads external rates, but the measurement is **not yet in this repository** | standing claims buried among situational ones |
| consolidate | a trigger index naming the claims to read, written as `served.txt` and `index.json`; each whole condition is one trigger by default and the run is flagged DEGRADED; a grouping file from `python -m baselayer.consolidation.build group` splits conditions into situation clauses that are exact substrings | a claim never reached or read outside its situation |
| consolidate | 14 integrity checks, including unchanged claim text and fact ids, every claim reachable, and served text matching its hash | consolidation altering or losing a claim |

By default, extraction runs on Claude Haiku 4.5, the leaf stage on Claude Sonnet 5, and authoring on Claude Opus 5. Each row is implemented in this repository unless it says otherwise.

The cited build currently takes eight commands. `consolidate` writes files that you put in a system prompt by hand. Automatic serving to an agent is not yet implemented. See [Using it with an agent](#using-it-with-an-agent).

**`baselayer run`** is the older, quicker pipeline. It takes one command and serves its result to Claude Code over MCP (Model Context Protocol). It makes far fewer checks.

Extraction does not require the person's own words unless `BASELAYER_TURN_CONTRACT=1` is set. Claude Sonnet 4.6 writes the three layers in separate calls. Each call reads a size-capped selection of facts chosen by code, so it sees a small share of a large corpus. Citations are optional, and there is no verification or consolidation step. Afterwards, each claim is linked to the facts nearest it in meaning. These links show related facts; they do not establish which facts the writer used.

## What a specification contains

A specification has three layers.

- **ANCHORS** describe the certainties the person reasons from, which settle a question before the details arrive.
- **CORE** describes how they communicate and the context needed to read them.
- **PREDICTIONS** describe how they are likely to respond in a given kind of situation.

Every claim has an id and can state when it applies. This claim comes from the specification built from Zitkala-Sa's *American Indian Stories* (1921, public domain).

> **P15 TOLERANT TO PEOPLE HARSH TO SYSTEMS.** Their severity is aimed at institutions and at
> settler power in the aggregate, not at individuals in front of them: in face-to-face
> disagreement, including religious disagreement, they extend respect, pity for suffering, and
> forgiveness over punishment. Predict the polemic in writing and the courtesy in the room.
>
> *Active when:* They disagree with, or witness the hardship of, a particular person present
>
> *Evidence:* [F-86fc472d] [F-cabf4c6c] [F-124a3cd5] ... (17 facts)

The `Evidence` line lists the facts used to write the claim. This example used an earlier version of the cited build, before facts quoted their source text. The full specification is in [examples/zitkala_sa/](examples/zitkala_sa/).

A specification has these limits.

- **Not a memory system.** It guides how an agent interprets facts and sits above whatever memory system you use.
- **Not a copy of the person.** It records what someone who knows you might notice about how you approach a situation, for an agent to read.
- **Not a biography or a summary.** It describes how someone reasons.
- **Not confirmed.** Models produce the reading. The person it describes must confirm that it represents them.
- **Not a portrait for the person.** It is written for the agent working for them. The person reads it to correct it.

## Quick start

To see a finished specification before spending anything, read [examples/zitkala_sa/](examples/zitkala_sa/).

Requires Python 3.10 or later and git. Base Layer reads your model API key from the `ANTHROPIC_API_KEY` environment variable ([get a key](https://console.anthropic.com/account/keys)). Set it in your shell profile or a secrets manager rather than typing it into a command.

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
```

Run it on your own writing, or on writing by someone who has agreed to it. Choose the cited build for checked claims traceable to the person's quoted words. Choose `baselayer run` to try Base Layer in one command and load the result in Claude Code.

**The cited build** takes eight commands in a fresh data root, the directory holding the database. Run `init`, `import`, `extract --turn-contract`, `distill` and `assemble` for each layer, `author-from-package`, `verify-spec` and `consolidate`. It also needs a file listing the names the person goes by.

`distill` and `author-from-package` print a cost estimate. They require a spend ceiling at or above it and confirmation of the rate table's date before starting. The commands in order and the batch setup used for the measured builds are in [docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end).

**`baselayer run`** lets you try Base Layer and use the result in Claude Code today. The second line requires [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

```bash
baselayer run chatgpt-export.zip     # or claude-export.json, a folder of journals, notes.md
claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp
```

On the first run, it asks for consent and the writer's name and pronouns. `--accept-data-processing` answers the consent prompt. It estimates the extraction cost and asks before spending. The estimate covers extraction only and has run low, so treat it as a floor.

The result is three markdown files in `data/identity_layers/` inside the data root. The root defaults to `~/.baselayer`. Set `MEMORY_SYSTEM_ROOT` to an existing directory to change it. A source checkout differs; see [docs/PIPELINE.md](docs/PIPELINE.md).

The second line registers the MCP server. MCP is the Model Context Protocol, which Claude Code uses to load outside tools and context. The server serves those files to new Claude Code sessions in any folder.

For anyone other than you, use a fresh data root so their facts do not mix with yours. Set `export MEMORY_SYSTEM_ROOT=...` and `mkdir -p` it first. Register that server inside one project only with `claude mcp add --scope local -e MEMORY_SYSTEM_ROOT=<that root> --transport stdio base-layer -- baselayer-mcp`.

Base Layer is pre-1.0 (version 0.5.0) and not on PyPI. The `baselayer` name there belongs to another project.

## What it costs

The table shows API spend for one specification by corpus size. *Measured* figures use recorded token usage from cited builds made in September and October 2026. *Projected* figures scale those builds' per-fact costs at 17 to 23 facts per 1,000 words of the person's writing.

The cited build column uses the batch setup from every measured build. Extraction and the leaf stage went through the Message Batches API at half price. The leaf stage used one model call per 50 facts per layer. Claude Opus 5.5 wrote the layers.

| corpus | facts | cited build, batch setup | `baselayer run` |
|---|---|---|---|
| about 50,000 words of essays or posts | about 1,000 | $6 to $8, projected | $1 to $2, projected |
| about 150,000 words of posts and talk transcripts | about 3,000 | about $18, projected | $3 to $4, projected |
| about 300,000 words of long essays | about 5,000 | $30.27, measured | about $6, projected |
| a chat history of about 1.4 million words from the person | about 22,000 | $112.32, measured | about $47, projected |

- **The cited build** spends about two thirds to four fifths on its leaf stage. The plain command sequence, at full rate with Claude Opus 5 writing, costs roughly 1.6 to 1.9 times as much.
- **`baselayer run`** spends nearly all its cost on extraction. Writing the three layers measured about $0.12 on three corpora of about 600 to several thousand facts in July 2026. That cost does not grow with the corpus because each layer reads a capped selection. Its extractor has not been priced on a recorded run. The column projects from the cited build's extractor, so treat it as an order of magnitude.
- **Rates** are per million input / output tokens, from Anthropic's [pricing page](https://platform.claude.com/docs/en/about-claude/pricing) as read on 19 October 2026.
  - Claude Haiku 4.5 $1 / $5
  - Claude Sonnet 4.6 $3 / $15
  - Claude Sonnet 5 $2 / $10
  - Claude Opus 5 $5 / $25
  - Claude Opus 5.5 $4 / $20

  The Message Batches API costs half these rates.

See [docs/PIPELINE.md](docs/PIPELINE.md#14-the-cited-build-end-to-end) for stage-by-stage costs and the basis of every figure.

## Using it with an agent

- **A cited build, by hand.** Put `served.txt` in the system prompt. When a listed situation applies, add the claims it names from `index.json`. Automatic serving of a cited build is not yet in this repository.
- **A `baselayer run` build, over MCP.** In Claude Code, use the `claude mcp add` line above. In Claude Desktop, use its config file as shown in [recipes/serve_specification_via_mcp.md](recipes/serve_specification_via_mcp.md). The server sends the three layers with every session. Its tools include `recall_memories` and `search_facts` to find facts, `trace_claim` to show what a claim rests on, and `verify_claims` to check it against the database and store the results there. Some clients truncate long MCP instructions. The full text is always available as the `memory://specification` resource.
- **Any model, by hand.** Put the three layer files in the system prompt. Fact search is unavailable this way.

How an agent should read it:

1. Apply a claim with an `Active when` line, or a prediction's `When ...` trigger, only when that situation holds. The always-on claims at the top of `served.txt` apply in every exchange. A claim with no condition provides context for reading the person. Do not treat it as a rule for every situation.
2. A claim marked CONTESTED preserves both sides of conflicting evidence. Do not resolve it for the person.
3. Facts call the subject "user" or "this person". That is the person the specification describes.

## How to check it

Follow a cited claim's fact ids to the words they quote. Run `verify-spec` to re-check every citation and quote against the database at no cost.

### What is checked by code, and what is a model's reading

| step | checked by code | a model's reading, which can be wrong |
|---|---|---|
| import | who said each turn, from the source's own role field | none |
| extract | every quote exists word for word in the person's own turn | what fact a passage supports |
| distill | every fact's verdict is counted; cited ids absent from the input are removed | which facts form a theme |
| author | every claim cites facts; with the quote gate, every quoted phrase appears in a cited fact's quote | how each claim is worded |
| verify-spec | citations resolve; quotes still match the source | with `--run-model`, whether cited facts support the claim |

The measured builds used the quote gate. The quote check confirms that a fact's evidence appears in a turn the source attributes to the person. It does not establish whether the fact interprets that text correctly.

`baselayer run` allows citations but does not require them. It links every claim to the facts nearest it in meaning. `baselayer provenance --claim P3` (or `trace_claim` over MCP) prints each link and how it was made.

No check here establishes that the specification is faithful. A resolved citation confirms that the reference exists. It does not establish that the fact caused the claim. Another model's ability to distinguish a specification from others establishes distinguishability, without establishing fidelity. Only the person can confirm it.

Every term used in a fixed sense is defined in [docs/DEFINITIONS.md](docs/DEFINITIONS.md).

## How to correct or update it

Facts do not carry their own significance. An extractor can find that someone rewrote a plan three times. The person must judge whether that was diligence or avoidance and edit the text accordingly.

- **Edit a cited build.** Change the claim in both `spec/<layer>.md` and `spec/<layer>.json`. `consolidate` fails if they disagree. Run `verify-spec` and `consolidate` again.
- **Edit a `baselayer run` build.** Open the files in `data/identity_layers/`. Delete what is wrong, rewrite what is close, add what the writing never said, then restart the MCP server. Running `author` or `run` again rewrites these files from the facts. Earlier generated versions are kept in `data/identity_layers/history/`. Hand edits are not, so copy yours first.
- **Remove a wrong fact.** `baselayer review` walks through facts one at a time to hide or flag them. `baselayer forget` hides facts by id, by conversation, or all at once. Neither updates existing layers. For a `baselayer run` build, run `baselayer author` again, then `baselayer verify --generate`. For a cited build, rebuild from `distill`.
- **Add more text.** For a `baselayer run` build, run `baselayer run` on the new file. Extraction processes only new material. For a cited build, `baselayer import` the file, run `baselayer extract --turn-contract`, then rebuild from `distill`.
- **Start over or remove everything.** To start over, use a new, empty data root. `baselayer forget --all` is not a reset. To remove everything, delete the data root, the MCP session logs in `~/.baselayer/sessions/`, and any `trees/`, `packages/`, `spec/`, `verify/` and `served/` directories you created for a cited build.

For agents making changes on someone's behalf, [docs/CORRECTIONS.md](docs/CORRECTIONS.md) explains how to carry a correction through facts, layers and served output in order. Base Layer Live is in development to keep a specification updated and served as corrections arrive.

## Limits and what is not included yet

- **Self-report.** The corpus contains only what the person wrote or said. It includes no observations by others.
- **No time axis.** Claims are not dated. The specification does not record how the person changed.
- **Little gain on the well known.** It helps most where the model knows the person least.
- **Anthropic models.** Base Layer has been tested almost entirely on Anthropic's models. Every language-model call goes to Anthropic except extraction, which can use a local model through Ollama (`baselayer extract --backend ollama`). The local models we tried fell well short of the pipeline's needs. Qwen 2.5 14B failed at writing across 12 attempts and was kept for extraction only ([D-030](docs/core/DECISIONS.md#d-030-model-role-separation--qwen-extracts-claude-writes)).
- **The cited build is experimental.** Its tests use fake model clients. Most of its design was measured on one book-length corpus of about 400 facts. The builds in the cost table used a development version of this code with the same stages.
- **Not in this repository yet.** The cited build lacks a single command and automatic serving to an agent. Also missing are the support filter that judges each fact against its quote before distillation; sorting stretch facts by how they go beyond their quotes; a separate model-judge check of each claim's scope; and fire-rate measurement for choosing always-on claims. The measured builds in the cost table used the support filter through scripts outside the package. [ROADMAP.md](ROADMAP.md) lists each item.

## Research

The *Beyond Recall* study tested specifications on 14 historical subjects with public-domain autobiographies. Panels of model judges scored the results. Prediction tests whether a specification represents the person accurately. It is not the goal.

- Gains were largest where the model knew the person least.
- The direction reproduced across response models. Absolute sizes depend on the judge panel.

A later test, separate from the paper, examined where the difference appears. It used recorded responses to the same decisions under nine specifications, some of them variants of one another. A deliberately simple classifier identified the right specification 51.6% of the time from the reasoning and 13.4% from the decision alone, against 11.1% chance. This test used no model judge. Differences of tone and length were not ruled out.

Specifications changed how decisions were argued in every situation tested. They changed the decision itself in some situations.

An analysis plan was locked partway through the study, after most data had been collected. It is not a preregistration of the full study. It names a seven-judge panel; the primary results use five ([ANALYSIS_PLAN_LOCK.md](https://github.com/agulaya24/beyond-recall/blob/master/docs/ANALYSIS_PLAN_LOCK.md)).

Methods and results are in the [paper](https://arxiv.org/abs/2605.28969), the [research page](https://www.base-layer.ai/research), and the [study code and data](https://github.com/agulaya24/beyond-recall). The paper used this version.

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0
```

## Privacy

The database, facts and specification are stored only on your machine. There are no accounts and no sync.

Extraction, distillation, writing, the tension check and all model-judged checks send text to the Anthropic API. Anthropic's [retention policy](https://www.anthropic.com/legal/privacy) applies. Extraction can instead use a local model through Ollama (`baselayer extract --backend ollama`).

The embedding model is downloaded from Hugging Face on first use. Base Layer sends no usage data and disables telemetry in its vector store, ChromaDB.

The specification is meant to be readable by the person it describes and under their control. They can read it, correct it or delete it.

## Documentation

| topic | doc |
|---|---|
| pipeline steps, options, costs and cited build commands | [docs/PIPELINE.md](docs/PIPELINE.md) |
| where the pipeline stands, what is in the package and what comes next | [docs/PROGRESS.md](docs/PROGRESS.md) |
| research directions outside the package (conformance, escalation, behavioural envelopes) | [docs/experimental/](docs/experimental/README.md) |
| code organisation and database tables | [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md) |
| project terminology | [docs/DEFINITIONS.md](docs/DEFINITIONS.md) |
| correcting a specification and rebuilding affected outputs | [docs/CORRECTIONS.md](docs/CORRECTIONS.md) |
| design principles, and which the code follows today | [docs/core/DESIGN_PRINCIPLES.md](docs/core/DESIGN_PRINCIPLES.md) |
| reasons for design decisions | [docs/core/DECISIONS.md](docs/core/DECISIONS.md) |
| plans, missing package features and open questions | [ROADMAP.md](ROADMAP.md) |
| known issues found by running the pipeline | [docs/PIPELINE_ISSUES.md](docs/PIPELINE_ISSUES.md) |
| changes by version | [CHANGELOG.md](CHANGELOG.md) |
| project orientation for newcomers and agents | [ORIENTATION.md](ORIENTATION.md), and for coding agents [AGENTS.md](AGENTS.md) |
| earlier evaluation specs and reports (mostly early 2026; the paper is the current record) | [docs/eval/](docs/eval/) |
| example specifications | [examples/](examples/). `zitkala_sa/` is the cited example; the other seven predate citations |
| contributing and reporting security issues | [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) |

Contributions on evaluation, source adapters, other interpretive-layer implementations and local models are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

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
