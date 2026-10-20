# Base Layer: Project Overview

What the project is, why it exists, and how its parts fit. For installing and running it, start
with the [README](../../README.md). For every step's inputs, outputs and options, see
[PIPELINE.md](../PIPELINE.md); for modules, tables and data flow, see
[ARCHITECTURE.md](ARCHITECTURE.md). Terms used in a fixed sense are defined in
[DEFINITIONS.md](../DEFINITIONS.md).

---

## What it is

Base Layer is the interpretive layer above memory. Memory systems store what a person said and
what they prefer. Base Layer reads a person's own text (chat exports, journals, notes, essays) and
writes a **specification**: a set of claims about how that person reasons, communicates and tends
to respond. An AI reads the specification before working for that person. Retrieval supplies the
facts relevant to a question; the specification supplies how this person would read them.

**Why it is built.** An agent can act in line with how a specific person would act only to the
extent it represents how that person reasons. The specification is that representation, written
as plain text so the person can read every claim, look up the facts it rests on and correct it.

It is not a biography, a profile or a fact database. It is a reading made by models, and it is
not confirmed until the person it describes says it is them.

## The specification

The specification is three layers, authored separately, each blind to the others:

| layer | what it holds |
|---|---|
| **ANCHORS** | the certainties the person reasons from |
| **CORE** | how they communicate, and the context to read them in |
| **PREDICTIONS** | given a kind of situation, how they are likely to respond |

On the cited path each claim has an id, an `Active when` line saying when it applies, and the ids
of the facts it rests on (see [DEFINITIONS.md](../DEFINITIONS.md)). A claim whose evidence pulls
both ways is marked CONTESTED and keeps both sides.

A single prose **brief** composed from the layers is optional and off by default. `baselayer run`
never writes one; `baselayer compose` (static path) or `author-from-package --compose` (cited path)
writes it on request. The three layers are the specification.

## Two ways to build it

| | `baselayer run` (static path) | the cited path (experimental) |
|---|---|---|
| shape | one command | eight steps: name the person, import, extract, distill, assemble, author, verify, consolidate |
| extraction | legacy extraction (turn contract only when `BASELAYER_TURN_CONTRACT=1` is set) | `extract --turn-contract`: every fact must quote the person's own words, checked by a gate in code |
| authoring | each layer written from a selection of facts made by code | every fact is first distilled; the layer author reads a package and must cite fact ids |
| citations | asked for, not required | required by schema |
| checks | a traceability step (vector index, vector provenance, a tension check between facts) | `verify-spec` and `consolidate` |
| served over MCP | yes | no |

Both paths extract facts as subject, predicate, object statements, using 46 predicates
(`CONSTRAINED_PREDICATES` in `src/baselayer/config.py`, 45 plus `unknown`). New facts pass through
AUDN (add, update, delete as supersession, no-op) against the facts already stored.

**Why the cited path exists.** The static author hands each layer a fixed slice of facts, at most
15 per category (`MAX_FACTS_PER_CATEGORY` in `author_layers.py`), chosen by sort position rather
than importance. On one measured 407-fact corpus the CORE author received 141 of the 407 facts.
Interpretive distillation removes that selection: the facts are split into chunks, each chunk gets
one model call that gives every fact a verdict (part of a recurring theme, a one-off kept word for
word, or not load-bearing) and keeps contradictions unresolved, and the results are assembled into
one package per layer. The author then sees every theme and one-off and must cite the facts behind
each claim. Most of its design was measured on one 407-fact corpus, and the full path has run end
to end on one large corpus once; see [DISTILLATION.md](DISTILLATION.md).

## Models

Model ids as configured on this branch. Commands that take `--model` can override them.

| role | model | where it is set |
|---|---|---|
| extraction, turn contract (the cited build) | `claude-haiku-5-5`, effort medium | `EXTRACTION_API_MODEL`, `config.py` (override `BASELAYER_LLM_EXTRACTION`) |
| extraction, legacy (`run`) | `claude-haiku-4-5-20251001` | `LEGACY_EXTRACTION_API_MODEL`, `config.py` (same override) |
| tension check in `run`'s traceability step | `claude-haiku-4-5-20251001`, pinned | `detect_contradictions.py` |
| static `author` | `claude-sonnet-4-6` | `LLM_PROVIDER_CONFIG`, `config.py` |
| `compose` (optional brief, static path) | `claude-opus-4-6` | `LLM_PROVIDER_CONFIG`, `config.py` |
| `distill` and `distill_batch` leaves | `claude-sonnet-5` | `--model` default |
| `author-from-package` (layers, and the brief with `--compose`) | `claude-opus-5` | `--model` default |
| `verify-spec` model-judged checks | `--rater cli`: alias `sonnet` by default; `--rater api`: the `--model` you pass | `verify-spec --help` |
| consolidation builders (optional inputs) | API backend `claude-opus-5`; CLI backend `opus` | `consolidation/build.py` |

Local extraction through Ollama is available with `baselayer extract --backend ollama`
(`LLM_MODEL` in `config.py`, `qwen2.5:14b`).

## Serving

**MCP.** `baselayer-mcp` serves the three layers in `data/identity_layers/`
(`anchors_v4.md`, `core_v4.md`, `predictions_v4.md`), which only the static path writes. It does
not serve a cited-path output directory or the `consolidate` output. It offers two resources
(`memory://specification`, and `memory://identity` as a deprecated alias) and eight tools:
`recall_memories`, `search_facts`, `trace_claim`, `verify_claims`, `get_stats`, `get_brief`,
`get_help`, `get_call_log`.

- The server also places the layers in its MCP instructions. Some clients may truncate long
  instructions; the full text is always the `memory://specification` resource, which re-reads the
  layer files on every call.
- `recall_memories` reads the fact vectors written during extraction (`baselayer embed` does not
  write them); `search_facts` is keyword search and needs no vectors.
- `trace_claim` lists the facts linked to a claim with tier, recurrence, how each link was made and
  the source conversation title. For facts from turn-contract extraction it also prints up to three
  of the person's own quoted words per fact, with the turn they came from.
- `get_brief` returns the optional brief, or says that none was composed.

Setup: [recipes/serve_specification_via_mcp.md](../../recipes/serve_specification_via_mcp.md).

**By hand.** The layers are plain text. Put the three layer files in a system prompt, or put
consolidate's `served.txt` there and look up claims by id in its `index.json`. Fact search is lost
this way.

**The hosted site.** [www.base-layer.ai](https://www.base-layer.ai) serves example specifications
and a JSON API over them. That API is part of the site, not of this package.

## Provenance and what it proves

- Every fact extracted by this version is stamped with the model, prompt hash and code path that
  made it, and the git commit when run from a git clone. Turn-contract facts also carry the turn
  they rest on and the exact words they quote (see [PIPELINE.md](../PIPELINE.md#13-stamps)).
- On the cited path every claim cites fact ids, `verify-spec` re-checks every citation and every
  evidence span against the database, and can add model-judged checks
  ([VERIFY_SPEC.md](VERIFY_SPEC.md)). `consolidate` builds an always-on set and a trigger index
  without rewriting any claim ([CONSOLIDATION.md](CONSOLIDATION.md)).
- On the static path the traceability step links every claim, cited or not, to its nearest facts
  by embedding. Read those links as nearby, not used. `baselayer verify` audits static layers
  ([PIPELINE.md](../PIPELINE.md#11-side-branches)).

What none of this establishes: that the specification is a faithful account of the person. A
resolving citation proves the reference is real, not that the fact caused the claim. A
specification another model can tell apart from others is distinguishable, not faithful. Only the
person can confirm it.

## Data

Conversations, facts, vectors and layers are stored on the user's machine under the data root
(`MEMORY_SYSTEM_ROOT`; unset, `~/.baselayer` for an installed package or the clone itself when run
from a clone). There are no accounts and no
sync. Extraction and authoring send text to the model API you configure. Base Layer sends no usage
data and turns off ChromaDB's own telemetry on every client it creates. How each source is treated
on import: [DATA_TREATMENT_POLICY.md](DATA_TREATMENT_POLICY.md). How corrections flow:
[CORRECTIONS.md](../CORRECTIONS.md).

## Limits

- The corpus is self-report: only text the person produced.
- Claims are not dated; the specification does not record how the person changed over time.
- It helps most where a model knows the person least; on a well-known public figure it often adds
  little.
- The cited path is experimental: its tests run against fake model clients, and nothing in this
  package serves its output.

## History

The original pipeline had more steps (scoring, classification, tiering, multi-agent review). An
ablation on one corpus found most of them added nothing measurable, and they were removed from the
default path; the condition outputs are in [../eval/archive/ablation/](../eval/archive/ablation/).
Some classification columns remain in the schema, and `baselayer run` still assigns a knowledge
tier to each fact by predicate in its traceability step. Study results, panels and caveats are in
the paper, [*Beyond Recall*](https://arxiv.org/abs/2605.28969). Design choices and their
rationale: [DECISIONS.md](DECISIONS.md) and [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).
