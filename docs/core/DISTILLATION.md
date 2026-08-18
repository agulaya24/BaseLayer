# Interpretive Distillation

Lives in this repository at `src/baselayer/distillation/`, exposed as `baselayer distill`,
`baselayer assemble` and `baselayer author-from-package`. This document is the detail doc for
that subpackage; the architecture-level summary is in `ARCHITECTURE.md`. Reference run records
(`distill_runs.jsonl`, `convergence_30run.json`) are in `data/distillation_reference/` -- named
that way because a run archives its own `distill_runs.jsonl` next to the corpus it reads, and
the reference copy must not sit where a quickstart run from a clone would append user rows.

> **EXPERIMENTAL RELEASE. This is not a tested pipeline.**
>
> It is published because the design is worth arguing with, not because it is ready to depend on.
> What that means concretely:
>
> - The test suite is 10 mutation tests over the citation audit. It is not integration coverage,
>   and it does not exercise `assemble.py`, `author_from_package.py`, `convergence.py`, or
>   `distill_batch.py` at all.
> - Most measurements behind the design were taken on one 407-fact corpus. Two defects that only
>   appear at scale were found on the first large run, which is the evidence that the small corpus
>   was not enough.
> - Three metrics were forced (arithmetically incapable of failing) until recently, and the test
>   suite passed the whole time because it exercised a function adjacent to them. Assume more of
>   that shape remains.
> - `distill_batch.py` and `convergence.py` do not call `validate()`, so their output is
>   unstripped. That is documented, not fixed.
> - Cost is real. A large corpus is hours and tens of dollars per layer. Read the cost notes
>   before running anything you have not budgeted.
>
> Use it to read the architecture, reproduce a measurement, or disagree with a choice. Do not put
> it in front of anything that matters yet.
>
> This subpackage first shipped as a standalone repository at version 0.1.0, and that is the
> maturity it still has regardless of the host package's version: faithfulness is unresolved,
> the suite is 10 mutation tests over one audit, and most measurements come from a single
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
distill.py             facts -> a tree of leaves, four channels each
assemble.py            one or more trees -> a stratified handoff package
author_from_package.py package -> layered output with mandatory citations
```

`convergence.py` measures run-to-run agreement across repeated distillations.
`distill_batch.py` submits **level-1 leaves only** through the Batch API at lower cost. ⚠️ It is
not a drop-in: it does not call `validate()`, so its output is unstripped, and `assemble.py` does
not accept its `L1.json`.

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

```
baselayer distill --db facts.db --out tree.json \
                  --layer anchors --max-facts 60 --model claude-haiku-4-5
```

(The modules also run directly: `python src/baselayer/distillation/distill.py --help`.
`--db` defaults to this project's `data/database/memory.db` when omitted.)

Every flag above is stated explicitly on purpose. The defaults differ from this line, and two of
them matter: `--layer` defaults to `blind`, which is the **control arm**, and `--max-facts` defaults
to 120, where a measured comparison found 60 recovers materially more singular facts.

## Chunking

Every strategy orders the facts and then cuts **equal-sized** chunks, so the only thing that varies
is which facts share a chunk. Predicate groups are wildly uneven in practice, so a naive by-group
partition would vary size and composition together and no difference could be attributed to either.

`predicate` (default) · `category` · `predcat` · `semantic` · `time` · `random`

**The partition is not neutral, and that is the point.** Selection happens competitively *within* a
chunk: two facts that would synthesise into one theme can both die separately if split, and a
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
`BASELAYER_BROAD_CLAIMS`, `BASELAYER_SRC`.

## License

Apache 2.0. See `LICENSE`.
