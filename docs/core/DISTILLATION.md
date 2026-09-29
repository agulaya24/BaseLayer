# Interpretive Distillation

Lives in this repository at `src/baselayer/distillation/`, exposed as `baselayer distill`,
`baselayer assemble` and `baselayer author-from-package`. The batch leaf path
(`distill_batch.py`) and the situation-first design test (`situation_first.py`) run only as
modules, and several options run only on the modules (see "Command-line entry points and
module-only options"). This document is the detail doc for
that subpackage; the architecture-level summary is in `ARCHITECTURE.md`. Reference run records
(`distill_runs.jsonl`, `convergence_30run.json`) are in `data/distillation_reference/` -- named
that way because a run archives its own `distill_runs.jsonl` next to the corpus it reads, and
the reference copy must not sit where a quickstart run from a clone would append user rows.

> **EXPERIMENTAL RELEASE. This is not a tested pipeline.**
>
> It is published because the design is worth arguing with, not because it is ready to depend on.
> What that means concretely:
>
> - The tests are mutation tests over the citation audit and the ledger metrics, plus call-shape
>   tests of the request `author_from_package.py` sends, and end-to-end runs of `distill.py`,
>   `distill_batch.py` and `author_from_package.py` against fake clients. `convergence.py` is
>   exercised only in dry runs.
> - Most measurements behind the design were taken on one 407-fact corpus. Two defects that only
>   appear at scale were found on the first large run, which is the evidence that the small corpus
>   was not enough. The full path described below (batch leaves with own-word spans, a sharded
>   package, authoring with the quote gate) has since run end to end on one large corpus. That is
>   one run on one person, not a validation.
> - Three metrics were forced (arithmetically incapable of failing) until recently, and the test
>   suite passed the whole time because it exercised a function adjacent to them. Assume more of
>   that shape remains.
> - `convergence.py` does not call `validate()`, so its output is unstripped. That is
>   documented, not fixed. `distill_batch.py` validates and strips like `distill.py`.
> - Cost is real. A large corpus is hours and tens of dollars per layer. Read the cost notes
>   before running anything you have not budgeted.
>
> Use it to read the architecture, reproduce a measurement, or disagree with a choice. Do not put
> it in front of anything that matters yet.
>
> This subpackage first shipped as a standalone repository at version 0.1.0, and that is the
> maturity it still has regardless of the host package's version: faithfulness is unresolved,
> the suite is mutation tests over one audit, and most measurements come from a single
> 407-fact corpus.

Turns a fact base into an auditable evidence package, where **every fact receives a recorded
disposition**. There is no sampling and no stopping rule: coverage is a property of the control
flow rather than an estimate.

Built for a specific problem. Summarising a large fact base into a description of how someone
operates loses exactly the material that matters most, because a summariser is a frequency
amplifier: a recurring theme enters every round with many tickets, a fact that appeared once has to
survive elimination. Significance is not frequency, and a plain summariser does not merely fail to
encode that, it inverts it.

## The four channels

Each chunk of facts is read once and produces four things, which do not compete for space.

**Themes.** What recurs. Synthesised statements, each naming the fact ids it drew on.

**Singularities.** Facts that appear once and would change how you model the subject. Carried
**verbatim**, never paraphrased, never merged. This lane exists because the structure above it
would otherwise discard them.

**Contradictions.** Where the evidence disagrees with itself. Carried forward, **never resolved**.
A contradiction is a finding, not a defect to smooth away.

**Dispositions.** Every fact id gets exactly one verdict: `theme`, `singular`, or
`not_load_bearing`. Omitting an id is not permitted. This is what makes "every fact was considered"
checkable rather than asserted.

## Pipeline

```
distill.py             facts -> a tree of leaves, four channels each (one layer per run)
distill_batch.py       the same leaves for every layer in one Message Batches submission
assemble.py            one or more trees -> a stratified handoff package (no model call)
author_from_package.py package -> layered output with mandatory citations, then the brief
quote_gate.py          optional check of quoted phrases in authored claims (--quote-gate)
spend.py               the dated rate table, estimates and the spend ceiling
situation_first.py     design test: an alternative predictions author (not on the default path)
```

`convergence.py` measures run-to-run agreement across repeated distillations.
`distill_batch.py` submits every layer's leaves in ONE Message Batches request (the layers run
concurrently, at the batch discount), then validates, strips, repairs and finishes each tree with
the same code as `distill.py`, so `assemble.py` reads its trees unchanged. Failed or unparseable
results are repaired sequentially under the spend ceiling. The batch id is written to
`<outdir>/batch_state.json` before any waiting, and `--resume` collects it without resubmitting
(see "Batch path and resuming" below).

### Models by stage

The distillation modules take their models from their own arguments, not from `config.py`.

| stage | module | default | notes |
|---|---|---|---|
| extraction (before distillation) | `extract_facts.py`, `batch_extract.py` | `claude-haiku-4-5-20251001` (`config.EXTRACTION_API_MODEL`) | stamped on every fact |
| leaves | `distill.py`, `distill_batch.py` | `claude-sonnet-5` | `--model` |
| layers and brief | `author_from_package.py` | `claude-opus-5`, effort `high` | Opus 5.5 with `--model claude-opus-5-5`; effort is always sent |
| situation-first predictions (design test) | `situation_first.py` | `claude-opus-5-5`, effort `high` | not on the default path |

The one configuration run end to end at scale used Sonnet 5 leaves on the batch path with
`--leaf-spans`, then Opus 5.5 at effort `high` with `--quote-gate`.

### Command-line entry points and module-only options

`baselayer distill`, `baselayer assemble` and `baselayer author-from-package` wrap the modules
but do not forward every option. The options below exist only when the module is run directly
(`python -m baselayer.distillation.<module>`):

| option | module(s) | on the `baselayer` subcommand? |
|---|---|---|
| `--leaf-spans`, `--span-cap` | `distill`, `distill_batch` | no |
| `--partition episode` (`distill`), `--partitions episode` (`distill_batch`), and the `--episode-*` options | `distill`, `distill_batch` | no |
| `--include-record-only` | `distill`, `distill_batch`, `convergence` | no |
| `--exclude-ids FILE` | `distill`, `distill_batch`, `convergence` | yes, on `distill` |
| `--include-other-subjects` | `distill`, `distill_batch`, `convergence` | yes, on `distill` |
| `--rates-confirmed`, `--rate-in`, `--rate-out`, `--confirm-spend` | every billed module | yes, on `distill` and `author-from-package` |
| `--quote-gate`, `--db` | `author_from_package` | no |
| `--no-compose` | `author_from_package` | no |
| `--dry-run`, `--resume` | `distill_batch` (module-only as a whole) | no |
| `--resume-step3` | `situation_first` (module-only as a whole) | no |

## What you need to supply

A SQLite database with a **`memory_facts`** table:

| column | required | notes |
|---|---|---|
| `id` | yes | **must be unique in its first 8 characters.** The run aborts on a prefix collision rather than silently merging two facts |
| `fact_text` | yes | the fact itself |
| `predicate` | yes | used by the default partition strategy |
| `category` | yes | used by `--partition category` |
| `superseded_by` | yes | only rows where this `IS NULL` are read |
| `created_at` | no | required **only** for `--partition time`, which raises without it rather than sorting by id and reporting a partition label that lies |

The database is opened read-only unless you pass `--write-provenance`, which creates and populates
a `layer_claim_provenance` table in **your** database.

## Install

Installs with the package: `pip install -e .` from the repository root, then
`export ANTHROPIC_API_KEY=...`.

`--partition semantic` additionally needs `scikit-learn` (`pip install -e .[semantic]`;
`sentence-transformers` and `numpy` are already core dependencies) and downloads an embedding
model on first use. It is imported lazily, so you only need it for that strategy.

## Quickstart

One layer, sequentially:

```
baselayer distill --db facts.db --out tree.json \
                  --layer anchors --max-facts 50 --model claude-sonnet-5 \
                  --rates-confirmed <table date> --confirm-spend <usd>
```

(The modules also run directly: `python -m baselayer.distillation.distill --help`.
`--db` defaults to this project's `data/database/memory.db` when omitted.)

Every flag above is stated explicitly on purpose. The defaults differ from this line, and two of
them matter: `--layer` defaults to `blind`, which is the **control arm**, and `--max-facts` defaults
to 120 on the sequential path. The leaf output ceiling (16,000 tokens) was sized for about 60 facts
per chunk, and 120-fact leaves truncated in a measured run. The batch path defaults to 50.

`<table date>` is the date of the rate table in `spend.py` (`RATES_AS_OF`). Check the current
price list before confirming it; see "Spend and prices" under Limits, below.

A full build of all three layers, on the batch path, with the options the end-to-end run used:

```
# 1. Leaves for every layer in one batch. --dry-run builds and prices every request, sends nothing.
python -m baselayer.distillation.distill_batch --db <memory.db> --outdir <trees> \
    --max-facts 50 --leaf-spans --rates-confirmed <table date> --dry-run
python -m baselayer.distillation.distill_batch --db <memory.db> --outdir <trees> \
    --max-facts 50 --leaf-spans --rates-confirmed <table date> --confirm-spend <usd>

# 2. One package per layer. No model call. Over the shard budget, --out is a manifest.
baselayer assemble <trees>/anchors_predicate_0.json --out <packages>/anchors.json
baselayer assemble <trees>/core_predicate_0.json --out <packages>/core.json
baselayer assemble <trees>/predictions_predicate_0.json --out <packages>/predictions.json

# 3. Author the three layers, then compose the brief.
python -m baselayer.distillation.author_from_package \
    --package <packages>/anchors.json --package <packages>/core.json \
    --package <packages>/predictions.json --outdir <spec> \
    --model claude-opus-5-5 --effort high --quote-gate --db <memory.db> \
    --rates-confirmed <table date> --confirm-spend <usd>
```

Add `--exclude-ids <file>` to both step 1 commands if an exclusion list is used (see below).

## Chunking

Every strategy orders the facts and then cuts **equal-sized** chunks, so the only thing that varies
is which facts share a chunk. Predicate groups are wildly uneven in practice, so a naive by-group
partition would vary size and composition together and no difference could be attributed to either.

`predicate` (default) · `category` · `predcat` · `semantic` · `time` · `random`

**The partition is not neutral, and that is the point.** Selection happens competitively *within* a
chunk: two facts that would synthesize into one theme can both die separately if split, and a
contradiction is only visible to a chunk holding both sides. **`random` is the null arm.** If
survival under a content-based partition does not beat random packing, the partition is doing
nothing.

## Reading the audit

Every run prints an audit block. What each line is worth:

- **`facts with disposition`** — the coverage claim. Should be 100%; below that means a leaf failed
  to parse and its facts carry no verdict.
- **`leaf citations ... fabricated and STRIPPED`** — fabricated ids, counted **before** the
  stripper removes them and recorded on the leaf, so the rate reaches the ledger.
  `citations_clean_pct` is `cited / attempted` and **can report below 100**; proven by mutation
  test, and proven to return to 100 on a clean leaf. `citations_survived_stripper` is the
  separate invariant and must be 0.
- **`singularity verbatim ... exact`** — compared against the database, so this one can fail.
  ⚠️ But its denominator counts only ids that RESOLVE, so a malformed or fabricated id is
  excluded rather than failed. Shipped rows in `data/distillation_reference/distill_runs.jsonl`
  carry 7- and 9-character ids while reading 100.0.
- **`singularities L1 -> L2 -> root`** — with the merge off (the default), `L2=0` is normal and does
  not mean the lane was discarded.

## Tests

```
python -m pytest tests/test_distillation_metrics_can_fail.py -q
```

These are mutation tests. Each plants a specific defect — a theme citing a fabricated id, an
invented singularity, a disposition for a fact from another chunk — and asserts the corresponding
check **notices**. Two controls confirm the harness itself works.

The standard they enforce: a guard that has not been shown to fail on a known-bad input is not a
guard.

The first five tests exercise `validate()`, the detector. ⚠️ **That is not sufficient on its own,
and for a while it was all there was**: `validate()` computes none of the ledger metrics, so the
suite passed while three of them were arithmetically incapable of failing. A test that exercises
an adjacent function proves the wrong thing, which is the same defect it was written to catch, one
level up.

The `test_ledger_*` tests call `distill.audit_citations`, which is the same function `main()`
uses to produce the ledger. That matters more than it sounds: an earlier version of these tests
re-implemented that arithmetic, and a mutation pinning the rate at 100 in the real code left all
of them passing. **A test that copies the code it checks tests the copy.** Three mutations are
known to break them: removing the pre-strip persistence, pinning the rate, and zeroing either of
the two fabrication counters.

Two metrics were **deleted rather than fixed**, because a measurement that cannot fail should not
be dressed up as one. `sing_survival_pct` became `sing_dedup_pct`, which is what it measured, and
`root_citations_resolved` became an explicit invariant. On the direct path the root lane is a
mechanical copy of the leaves, so neither could ever have registered loss.

## Inputs under the turn contract

Leaves read facts only. When the corpus was extracted under the turn contract
(`docs/core/TURN_CONTRACT.md`, D-108), every fact a leaf sees is already grounded in the subject's
own typed or spoken words. The leaf check that rejects fact ids outside the supplied set keeps
theme statements tied to those gated facts. Distillation adds no speaker logic of its own.

Stamps (contract §7). Every leaf, the tree, the package, each authored layer and the brief carry
a stamp:
- the contract version, read from the input facts (a mix of versions is refused before any call);
- the model, or null for the mechanical package step;
- a prompt hash;
- `git_commit` and a repo-relative `code_path`;
- the hash of the input: fact ids AND fact text for leaves and trees, content hashes of the trees
  for a package, the package for a layer.

The tree also keeps its SHA of `distill.py`, its partition settings, and the ids-only
`corpus_hash` for comparison with older trees. The tree's run id is keyed on the id-and-text hash,
so run ids written before this change are not comparable with later ones. Layers and the brief
write `<name>.stamp.json` beside the authored file, with effort, `max_tokens`, token usage summed
over every attempt, the rates used and the cost.

Authoring model. `author-from-package` defaults to `claude-opus-5`. It also runs on Opus 5.5
through `--model`, with `--effort` (sent explicitly, default `high`) and `--max-tokens` (thinking
counts toward it; default 64,000 per layer call and 96,000 for compose, capped at 128,000). A call
that stops at `max_tokens` raises rather than retrying, because the same request truncates the
same way.

## Own words at the leaves (`--leaf-spans`)

Off by default. With it, every fact line in a leaf prompt is followed by `own words:` and up to
`--span-cap` (default 3) of the verbatim evidence spans the fact was extracted from. Under the turn
contract those spans are the person's own typed or spoken words. Spans past the cap are counted in
the line and in the stamp (`facts_truncated_by_cap`), never silently dropped. The leaf may quote
those words inside theme statements and may add an `own_words` excerpt to a singularity. An
`own_words` excerpt that is not a substring of that fact's own spans is emptied and counted under
the leaf's `_stripped` record; it costs no repair call. Without the flag, every prompt, schema and
prompt hash is byte-identical to the path without it.

Spans make leaves longer. Expect more output per leaf and more truncation repairs than without the
flag, and price the run with `--est-out-per-leaf` set from a measured sample rather than the
default constant.

## Quote gate (`--quote-gate`)

Off by default; `author_from_package` only, and it needs `--db`, the corpus database the packages
were built from (read-only). With spans at the leaves, the author starts quoting the person, and
some quoted phrases turn out not to be the person's words (an assistant's phrasing, an idiom, a
paraphrase inside quote marks). The gate checks every quoted phrase in a claim's `name`,
`statement` and `active_when` against the own-voice evidence spans (voice class `own_typed` or
`own_dictated`) of the facts that claim cites. Matching ignores case, whitespace, quote-mark style
and leading or trailing sentence punctuation (`.,;:!?`).

A quote that fails is handled on the accepted attempt. The gate never re-asks for a quote:

| finding | what the gate does |
|---|---|
| the words are in an own-voice span of another fact supplied to this call, the quote has at least 3 words, and at most 5 supplied facts hold it | every holding fact is appended to the claim's `fact_ids` and also listed in `gate_added_citations` |
| the same, but under 3 words or more than 5 holders | quote marks removed, words kept (a short or common phrase would add many weak citations) |
| the quote carries an ellipsis | quote marks removed, words kept |
| the words are in no own-voice span of any supplied fact | quote marks removed, words kept |

- "Supplied" is per call. A sharded layer only auto-cites within its own shard.
- The rendered layer shows gate-added citations on their own line (`Citations added by the quote
  gate:`), so a citation the gate chose is never presented as the author's.
- Claims are re-checked after the gate; anything still flagged is printed as a warning and counted
  as `residual_after_gate`.
- The layer stamp records the mode (`auto_cite_strip`), both bounds, and each quote's action
  (`auto_cited`, `stripped_short`, `stripped_many_holders`, `stripped_elided`,
  `stripped_not_found`).
- The gate refuses to run, rather than passing claims unchecked, if the database lacks the
  evidence-span or turn columns or any supplied id resolves to no live fact.
- Report the count of gate-added citations beside the author's own. A high rate means the author
  quotes correctly and cites loosely.

The citation gate is unchanged: a missing tool call or a claim without valid citations is still
re-asked, up to three attempts, and each re-ask re-sends the whole layer prompt. The estimate
prices one attempt per call.

## Exclusion list (`--exclude-ids`)

`--exclude-ids FILE` removes fact ids from the distillation population. The fact base is not
touched. FILE is a JSON list, a JSON object with an `ids` list, or text with one id per line (`#`
starts a comment). An id is a full uuid or its 8-character prefix, optionally written `F-<prefix>`.
A malformed entry or an empty list is refused. The tree stamp records the file's name and sha256,
the number of ids requested and excluded, and the listed ids that are not in the corpus or are
outside the population already (for example, a fact another filter had removed).

The list can come from any external review, for example a check of whether each fact is supported
by the words it cites. That review is not part of this package; only the list is.

## Batch path and resuming

`distill_batch.py` builds every request, prints the estimate at batch rates, and with `--dry-run`
stops there. A billed run checks the whole batch's estimate against the ceiling before the single
submit (a submitted batch cannot be stopped per request), then checks each sequential repair before
it is sent. Repairs run at the full rate and are not in the estimate.

`--resume` collects the batch recorded in `<outdir>/batch_state.json` and never submits. It
refuses when the recorded request count, model or exclusion-list sha256 differs from the current
invocation. `--max-facts`, `--layers`, `--partitions` and `--seeds` are compared only indirectly,
through the request count. It does NOT record or compare `--leaf-spans`, `--span-cap` or the
episode options, so
**resume with exactly the flags that submitted the batch**. Otherwise repairs are sent with a
different prompt and the trees carry a different prompt hash. A resumed run skips trees that are
already finished and counts only its own repairs.

Other resume options are separate and unrelated: `--checkpoint` and `--resume-from` on sequential
`distill.py`, `--resume-step3` on `situation_first.py`, and `batch-extract --process --resume` on
the extraction side. The study harness `convergence.py` has its own `--dry-run` and `--resume <batch id>`.

## Design tests (off by default)

- **Episode chunks** (`--partition episode`): facts are chunked by episode instead of by sorted
  predicate. An episode is a conversation, or, for day-grouped conversations, one local calendar
  day across conversations, in the order things happened. Nothing is day-grouped by default: a
  conversation is day-grouped when its title matches `--episode-day-title-regex` or one of its
  facts carries a practice tag named with `--episode-day-practice` (repeatable). The option
  requires `--episode-tz`, the timezone that defines a calendar day. Small episodes are packed
  with neighbours (`--episode-min`); long ones are split (`--episode-max`).
- **Situation-first predictions** (`situation_first.py`): the author first names situations from
  the predictions package, citing the facts that show the person in each. Code then routes facts
  to each situation: the cited seeds, every other fact of a package theme that cites a seed, both
  sides of a contradiction touching a seed, and, on episode trees, the facts of a seed's episode
  that its leaf kept. The author then writes predictions citing only facts routed to that
  situation. `--route-cap` bounds each situation and every cut is recorded. The default predictions
  path does not read any of this.

## Not in this package: consolidation

A sharded layer is the concatenation of its shards' claims. Shards see disjoint evidence, so the
same pattern can be written once per shard, and the three blind layer authors can also restate one
another. Nothing in this package merges those claims. A post-authoring consolidation stage
(grouping claims by evidence overlap and trigger, merging with every source claim mapped, and
mechanical checks that nothing was lost) exists only as a prototype outside this repository. It is
not shipped, not tested here, and not called by any command.

## Limits

**The merge is off by default.** A hierarchical merge exists and is retained behind
`BASELAYER_FORCE_MERGE=1`, but at scale it was where things broke: empty roots, interior nodes
inventing themes and fact ids. Themes and singularities are collected mechanically from the leaves
instead, which costs nothing and loses nothing by construction.

**Auditability is not fidelity.** Every claim following back to evidence does not make the claim
correct about the subject. A traceable specification can be traceably wrong.

**A resolving citation is not proof of influence.** The model chooses which ids to attach. Presence
is guaranteed by schema and resolution is checked against the database; whether the cited fact
actually drove the claim is a separate question, and removal is the only test for it.

**Configuration** is read from the environment: `BASELAYER_FORCE_MERGE`, `BASELAYER_MERGE_FAN`
(default 4), `BASELAYER_LEAF_PAYLOAD_CEILING` (default 400000), `BASELAYER_REAUTHOR`,
`BASELAYER_BROAD_CLAIMS`, `BASELAYER_SRC`, `BASELAYER_SPEND_CEILING_USD`,
`BASELAYER_RATES_CONFIRMED`.

**Spend and prices.** Rates come from one dated table (`spend.py`) that a billed run refuses to
use until the operator confirms its date (`--rates-confirmed`) or supplies rates
(`--rate-in`/`--rate-out`). Every billed run prints an estimate before any call and needs a
ceiling at or above it (`BASELAYER_SPEND_CEILING_USD`, or `--confirm-spend`, which becomes the
ceiling). The ceiling is checked before every call, repairs and re-asks included; on the batch
path the whole batch's estimate is checked once before submit. Unlike extraction, where an unset
`BASELAYER_SPEND_CEILING_USD` means no ceiling, a billed distillation or authoring run with neither
a ceiling nor `--confirm-spend` refuses to start. Each process takes its own `--confirm-spend`, so
a build's total budget is the sum of the leaf and authoring amounts. The estimates convert
characters to tokens at a fixed ratio and undercount real input, most on authoring; the ceiling,
checked against measured usage, is what bounds a run.

**Payload over one author request.** `distill.py` projects the leaf payload from the fact count
before the first leaf and records the measured payload on the tree; it no longer stops above
`BASELAYER_LEAF_PAYLOAD_CEILING`. `assemble.py` splits a package whose rendered evidence exceeds
`--shard-token-budget` into shards along contiguous leaf ranges, with no model call and nothing
dropped, and writes a manifest; `author_from_package.py` authors each shard separately and
concatenates the claims. The layer files are not collapsed across shards, so they can hold near
duplicates; compose reads all of them when it writes the brief (see "Not in this package:
consolidation").

**Subjects.** Distillation reads only facts whose subject is the person (`subject = 'user'`);
the rest are counted on the tree. `--include-other-subjects` admits them, labelled as being about
someone else in the leaf prompt and in the author's evidence.

## License

Apache 2.0. See `LICENSE`.
