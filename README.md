# Base Layer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Tests](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg)](https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

[base-layer.ai](https://www.base-layer.ai) · [Paper](https://arxiv.org/abs/2605.28969) · [Research](https://www.base-layer.ai/research) · [Dataset](https://huggingface.co/datasets/agulaya24/beyond-recall)

Start here. This file is written for you and for any agent you point at this repository. Terms used
in a fixed sense (claim, fact, own words, CONTESTED and so on) are defined under
[How to trust it](#how-to-trust-it) and in full in [docs/DEFINITIONS.md](docs/DEFINITIONS.md).

## What this is

Base Layer is an open-source pipeline that reads a person's own text (chat exports, journals,
notes, essays) and writes a **specification**: a set of claims about how that person reasons,
communicates and tends to respond. An AI reads it before working for that person. It is an
interpretive layer above memory: memory supplies facts, the specification supplies the way that
person reads them.

The specification is plain text. You can read every claim, look up the facts it cites in your own
database, see the exact words of the person each fact was drawn from (for facts extracted under the
turn contract), and correct what is wrong.

It is not a biography and not a summary. It is a reading made by models, and it is not confirmed
until the person it describes says it is them.

### What you get

| part | what it is |
|---|---|
| three layers | **ANCHORS** (the certainties the person reasons from), **CORE** (how they communicate, and the context to read them in), **PREDICTIONS** (given a kind of situation, how they are likely to respond). Each claim has an id, an `Active when` line and the ids of the facts it rests on. |
| the facts | every fact extracted about the person, in a local database. Each fact extracted by this version carries stamps for the model, prompt and code that made it. On the cited path each fact also carries the person's own words it was drawn from. |
| a verification report | `verify-spec` output: which citations resolve, which evidence still matches the source, and (optionally) model-judged checks of each claim against its facts. |
| a trigger index | `consolidate` output: the always-on claims in full, a list of situations each naming the claims to read, groups of claims that state the same idea, and an index file to look claims up by id. |

An example claim, from the specification built from Zitkala-Sa's *American Indian Stories* (1921,
public domain; full example in [examples/zitkala_sa/](examples/zitkala_sa/)). The example ships
the layer text only. Its fact ids cannot be resolved from this repository: the fact database is
not published, and those facts were extracted before the turn contract, so they carry no evidence
spans.

> **P1 SYSTEMIC CRITIQUE OVER SINGLE COMPLAINT.** Presented with a specific grievance or
> malpractice, they will not treat it as an isolated incident; they escalate it to the level of
> the system that produced it ...
>
> *Active when:* A concrete instance of institutional wrongdoing, mismanagement or partial remedy
> is put in front of them
>
> *Evidence:* [F-0e7a1b8f] [F-024cb8de] ... (14 facts)

## How to use it

### Install

```
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
```

Python 3.10 or later. Not on PyPI (the `baselayer` name there belongs to another project). Data
lives wherever `MEMORY_SYSTEM_ROOT` points (the directory must already exist). Without it, a
package installed with the `pip install` line above uses `~/.baselayer`, while code run from a
clone of this repository (an editable or source install) uses the clone itself, under its `data/`
directory, whose database, vectors, layers, distillation archive and import config are
gitignored. Setting
`MEMORY_SYSTEM_ROOT` avoids both surprises.

### Two ways to build a specification

| | `baselayer run` | the cited path (experimental) |
|---|---|---|
| what it is | one command, the original pipeline | eight steps (0 to 7 below), the current design |
| extraction | Claude Haiku 4.5 | Claude Haiku 4.5, own words only (the turn contract) |
| authoring | Claude Sonnet 4.6, layers written from facts | Claude Sonnet 5 sorts the facts, Claude Opus 5 writes the layers |
| every claim cites facts | not guaranteed | required |
| verification and trigger index | not run | `verify-spec` and `consolidate` |
| served to Claude over MCP | yes | no (see [For your agent](#for-your-agent)) |
| spend ceiling | none unless `BASELAYER_SPEND_CEILING_USD` is set (checked by sequential extraction only; `batch-extract`, `author`, `compose` and the traceability tension check, up to 30 Haiku calls, have none) | `distill` and `author-from-package` price the run and refuse to start without one; extraction as on the left |

### Quick start: one command

```
baselayer run chatgpt-export.zip      # or claude-export.json, a journal folder, notes.md
```

It imports the file, prints an extraction estimate and asks to continue, extracts facts, writes
the three layers into `data/identity_layers/` under your data root, then builds an audit trail
(vector index, vector provenance, a small Haiku check for tensions between facts). It does not run
any of the cited-path steps below. `baselayer estimate` prices extraction only; treat it as a floor,
not a budget.

### The cited path, step by step

Run these into a fresh data root. Each step links to its detail.

0. **Name the person.** Own-words extraction refuses to start until the person's names are set as
   `subject_names` in `data/import_config.json` under the data root (every form the text may use,
   for example a first name and the full name). Set it before importing: the importer also uses it.
1. **Import.** `baselayer import <file>` stores the text one turn per row, recording who said each
   turn. Only turns the person typed or spoke can be cited later; assistant turns, other people,
   pasted text and tool output are context only. ([docs/core/TURN_CONTRACT.md](docs/core/TURN_CONTRACT.md))
2. **Extract.** `baselayer extract --turn-contract` draws short facts about the person. Every fact
   must quote the person's own words, and a check in code (the gate) drops any fact whose quote is
   not found in the person's own turn. A rerun resumes where it stopped.
   ([docs/core/TURN_CONTRACT.md](docs/core/TURN_CONTRACT.md))
3. **Distill**, once per layer. `baselayer distill --layer anchors` (then `core`, `predictions`)
   gives every fact one verdict: part of a recurring theme, a one-off kept word for word, or not
   load-bearing. Contradictions are kept, not resolved. ([docs/core/DISTILLATION.md](docs/core/DISTILLATION.md))
4. **Assemble**, once per layer. `baselayer assemble` packages each layer's result for the writer.
   No model call; a package too large for one request is split, and nothing is dropped.
5. **Author.** `baselayer author-from-package` writes the three layers. Every claim must cite fact
   ids. An optional quote gate checks that any quoted phrase is the person's own words from the
   cited facts. A single prose brief is optional and off by default (`--compose`).
   ([docs/core/DISTILLATION.md](docs/core/DISTILLATION.md))
6. **Verify.** `baselayer verify-spec` checks the finished specification against the database,
   read-only. The mechanical checks are free. The model-judged checks are priced and skipped unless
   you add `--run-model`. ([docs/core/VERIFY_SPEC.md](docs/core/VERIFY_SPEC.md))
7. **Consolidate.** `baselayer consolidate` builds the trigger index and duplicate groups from the
   authored layers. No model call, no claim text rewritten, 14 checks that must pass.
   ([docs/core/CONSOLIDATION.md](docs/core/CONSOLIDATION.md))

`baselayer embed` embeds imported messages for `baselayer search`. Fact vectors, which the MCP
recall tool and `baselayer verify` read, are written during extraction. The cited path needs
neither.

```
export MEMORY_SYSTEM_ROOT=~/bl/franklin && mkdir -p "$MEMORY_SYSTEM_ROOT"
baselayer init
echo '{"subject_names": ["Benjamin", "Benjamin Franklin"]}' > "$MEMORY_SYSTEM_ROOT/data/import_config.json"
baselayer import chatgpt-export.zip
baselayer estimate                            # a floor for extraction, not a budget
export BASELAYER_SPEND_CEILING_USD=<usd>      # sequential extraction stops before passing it
baselayer extract --turn-contract
mkdir -p trees packages
baselayer distill --layer anchors --max-facts 50 --out trees/anchors.json \
    --rates-confirmed <table date> --confirm-spend <usd>       # repeat for core, predictions
baselayer assemble trees/anchors.json --out packages/anchors.json   # repeat for core, predictions
baselayer author-from-package --package packages/anchors.json --package packages/core.json \
    --package packages/predictions.json --outdir spec_out/ \
    --db "$MEMORY_SYSTEM_ROOT/data/database/memory.db" \
    --rates-confirmed <table date> --confirm-spend <usd>
baselayer verify-spec spec_out/ --label me --corpus "$MEMORY_SYSTEM_ROOT" --out verify_out/
baselayer consolidate spec_out/ --out served_out/
```

`distill` and `author-from-package` print an estimate and refuse to start unless `--confirm-spend`
(or `BASELAYER_SPEND_CEILING_USD`) covers it; a large corpus is hours and tens of dollars per layer. `<table date>` is the date of the
in-repo rate table, printed by `baselayer distill --help`; check current prices before confirming
it. Always pass `--layer` to `distill` (without it the run is the undirected control, and it
prints a warning saying so), and create the output directories first (`distill` refuses to start
without them). Spend options,
the quote gate and batch modules, and every step's inputs and outputs:
[docs/PIPELINE.md](docs/PIPELINE.md).

### For your agent

- **Over MCP (Claude Code, Claude Desktop):** `claude mcp add --transport stdio base-layer -- baselayer-mcp`.
  The server serves the three layers in `data/identity_layers/` (written by `baselayer run` or
  `baselayer author`) and offers tools to search facts and trace a claim to its facts. It sends the
  layers in its MCP instructions, and some clients may truncate long instructions; the full text
  is always the `memory://specification` resource. It does not serve a cited-path `spec_out/` directory or the
  trigger index.
  ([recipes/serve_specification_via_mcp.md](recipes/serve_specification_via_mcp.md))
- **Any model, by hand:** put the three layer files in the system prompt, or put consolidate's
  `served.txt` (always-on claims plus the trigger index) there and look up the claims a situation
  names in `index.json`. You lose fact search this way.

How an agent should read a specification:

1. Read each claim with its `Active when` line. It applies in that situation, not everywhere.
2. **CONTESTED** means the evidence pulls both ways. Both sides are in the claim. Do not resolve it.
3. Claims in the same duplicate group state one idea in more than one layer; read them together.
4. Before relying on a claim, check the verification report. A claim flagged there names what was
   found missing.
5. Facts name the subject generically ("user", "this person"); that is the person the
   specification describes.

## How to trust it

### What is checked by code, and what is a model's reading

| step | checked by code (cannot be argued with) | judged by a model (a reading that can be wrong) |
|---|---|---|
| import | each turn's speaker comes from the source's own role field; rules mark pasted text, tool output and summaries | none |
| extract | the gate: every quoted span exists verbatim in a turn the person wrote or spoke | what fact a passage supports |
| distill | every fact's verdict is counted; a cited id that was not in the input is removed | which facts form a theme, which are one-offs |
| author | every claim cites fact ids; optional quote gate on quoted phrases | how each claim is worded |
| verify-spec | citations resolve; every evidence span is re-checked against the source; stamps match; duplicate candidates | with `--run-model`: whether each cited fact supports the claim, whether each fact is a fair reading of the person's turn, contradictions between claims |
| consolidate | claim text unchanged, fact ids preserved, every claim reachable, every trigger worded verbatim from an `Active when` line (14 checks) | optional inputs only: duplicate verdicts, trigger grouping, categories |

What this does not establish: that the specification is a faithful account of the person. The gate
proves a fact rests on words the person wrote or spoke, not that the fact reads them correctly. A
citation that resolves proves the reference is real, not that the fact caused the claim. A
specification another model can tell apart from others is distinguishable, not faithful. Only the
person can confirm it.

Every fact extracted by this version is stamped with the model, prompt hash and code path that made
it, and the git commit when run from a git clone (outside a git work tree it records `unknown`). On
the `baselayer run` path, traceability also links every claim to its nearest facts by embedding
(`link_method` `vector`), cited or not: read every vector link as nearby, not used.

**Looking up a cited-path claim's facts.** No command prints them yet. MCP `trace_claim` and
`baselayer provenance` read the `layer_claim_provenance` table, which `author-from-package` does not
write (static `author`, `run`, `verify --generate` and `distill --write-provenance` do; the last
stores tree themes and singularities under ids such as T1 and S1, not claim ids). Each claim's fact ids are in the
layer's `.json` file (`fact_ids`; each is a fact id or its first 8 characters, sometimes written
with `F-`), the facts and their evidence spans are in the `memory_facts` table of your database,
and `verify-spec` re-checks every citation and span.

### Terms

- **Claim:** one statement with an id (A1, C14, P26), a body, an `Active when` line and cited fact
  ids. Ids are unique within one specification only.
- **Fact:** a short statement about the person drawn from one piece of their text, with an id
  (`F-` and 8 characters).
- **Own words:** text the person typed or spoke. Only own words can be a fact's evidence.
- **CONTESTED:** the author's marker for a claim whose evidence disagrees with itself.

Every other term: [docs/DEFINITIONS.md](docs/DEFINITIONS.md).

### Limits

- The corpus is self-report: only text the person produced, nothing observed by others.
- Claims are not dated. The specification does not record how the person changed over time.
- It helps most where the model knows the person least; on a well-known public figure it often adds
  little.
- The cited path is experimental. Its tests run against fake model clients, most of its design was
  measured on one 407-fact corpus, and the full path has run end to end on one large corpus once.
  ([docs/core/DISTILLATION.md](docs/core/DISTILLATION.md))

## How to correct or update it

- **Edit the text.** On the `baselayer run` path the layers are markdown files in
  `data/identity_layers/`; edit them and restart the MCP server. On the cited path each layer is a
  `.md` and a `.json` file; edit both, because `consolidate` fails when they disagree.
- **Correct a fact.** `baselayer review` walks through facts one at a time: you can hide a fact
  (marked superseded; its vector stays) or flag it with a note; it does not edit fact text.
  `baselayer forget` hides facts (by id, conversation, or all) and removes their vectors; the rows
  stay and can be restored. Layers already written are not regenerated by either. On the `run`
  path, re-author them (`baselayer author`). Only `forget` marks the layers stale until you do;
  hiding with `review` leaves no marker. On the cited path, rebuild from `distill` for all three layers: each tree was built from
  all the active facts, so re-authoring from the old packages keeps the hidden ones.
- **Add more text.** Import the new file and run the steps again. Extraction only processes what is
  new; `baselayer run` stops before spending anything when the file adds nothing.
- **Start clean.** The safest clean start is a new, empty data root. `python -m
  baselayer.extract_facts --reset` deletes extracted facts, the extraction log and the fact vectors,
  with no confirmation. `baselayer forget --all` is not a reset.
- **Remove everything.** Delete the data root and the MCP session logs in `~/.baselayer/sessions/`,
  which record tool queries.

How corrections flow through the system: [docs/CORRECTIONS.md](docs/CORRECTIONS.md).

## What is not included yet

- **Serving the cited path.** Nothing in this package puts a cited-path specification or its
  trigger index into an agent session, or pulls claims on demand. That work is in progress and not
  in this repository.
- **The support filter**, which labels every fact supported, stretch or not supported against its
  own quote before distillation, and **the stretch sort** are research scripts, not published.
  `distill --exclude-ids` accepts a list of facts to leave out.
- **The research verification judges** (a back-check and a combined support, reach and recency
  judge) are not in the package. `verify-spec --backcheck-results` reads a back-check's results but
  does not run one. verify-spec's own model-judged checks are in the package, built and priced. In
  this repository they are tested only against a scripted fake rater, and no run against a real
  model is published here ([docs/core/VERIFY_SPEC.md](docs/core/VERIFY_SPEC.md)).
- **One command for the cited path.** It is eight steps, and the quote gate, batch leaves and
  the model-built consolidation inputs run as Python modules.

## Privacy

The database, vectors, facts and specification stay on your machine. There are no accounts and no
sync. Extraction and authoring send text to the model API you configure, and that provider's
retention policy applies ([Anthropic's](https://www.anthropic.com/legal/privacy)). The first
embedding run downloads the embedding model from Hugging Face. Base Layer sends no usage data, and
turns off ChromaDB's own telemetry on every client it creates.

## What we tested

The *Beyond Recall* study evaluated specifications on 14 historical subjects with public-domain
autobiographies. Gains are largest where the model knows the person least. Specifications change
how decisions are argued in every situation tested, and change the decision itself in some. An
analysis plan was locked partway through the study, after most data had been collected; it is not a
preregistration of the full study, and it specifies a seven-judge panel, while the five-judge
primary panel is not in it
([ANALYSIS_PLAN_LOCK.md](https://github.com/agulaya24/beyond-recall/blob/master/docs/ANALYSIS_PLAN_LOCK.md)).
Method, panels and caveats: the [paper](https://arxiv.org/abs/2605.28969) and the
[research page](https://www.base-layer.ai/research).

## Links

- Site: https://www.base-layer.ai · examples: https://www.base-layer.ai/examples/franklin
- Paper: *Beyond Recall*, https://arxiv.org/abs/2605.28969 (CC BY 4.0); study code and data:
  https://github.com/agulaya24/beyond-recall; dataset: https://huggingface.co/datasets/agulaya24/beyond-recall
- Examples in this repository: [examples/](examples/). `zitkala_sa/` is the one whose claims cite
  fact ids (the fact database is not included, so the ids cannot be resolved from here); the other
  seven predate citations.
- Docs: [docs/PIPELINE.md](docs/PIPELINE.md) (every step), [docs/DEFINITIONS.md](docs/DEFINITIONS.md),
  [docs/CORRECTIONS.md](docs/CORRECTIONS.md), [docs/core/FLOW_GUIDE.md](docs/core/FLOW_GUIDE.md) (a walkthrough),
  [docs/core/ARCHITECTURE.md](docs/core/ARCHITECTURE.md) (modules, tables, data flow),
  [docs/core/PROJECT_OVERVIEW.md](docs/core/PROJECT_OVERVIEW.md),
  [docs/core/DECISIONS.md](docs/core/DECISIONS.md),
  [ROADMAP.md](ROADMAP.md), [CHANGELOG.md](CHANGELOG.md). For coding agents: [AGENTS.md](AGENTS.md).
- Reproducing the paper: the paper's version is tagged `v0.2.0`
  (`pip install git+https://github.com/agulaya24/BaseLayer.git@v0.2.0`) and vendored in the study
  repository.
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Evaluation, source adapters, other
  interpretive-layer implementations and local-model support are welcome.

```bibtex
@software{baselayer2026,
  title     = {Base Layer: An Open-Source Reference Pipeline for the Interpretive Layer Above Memory},
  author    = {Gulaya, Aarik},
  year      = {2026},
  url       = {https://github.com/agulaya24/BaseLayer},
  license   = {Apache-2.0}
}
```

Apache 2.0. See [LICENSE](LICENSE).
