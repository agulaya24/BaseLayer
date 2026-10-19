# Zitkala-Sa, the cited example

This is the only example in the repository whose claims cite fact ids. Only the layer text ships
here: the corpus database is not published, so an outside reader cannot resolve the ids. The
counts below were checked by the maintainer against that database.

**Source:** *American Indian Stories* (1921) by Zitkala-Sa, public domain, Project Gutenberg.
**Built:** 2026-08-18 on the cited path as it stood then: IMPORT, EXTRACT, DISTILL, ASSEMBLE, AUTHOR,
COMPOSE (the brief was then composed by default). Extraction predates the turn contract, so the
facts carry no evidence spans, and `verify-spec` and `consolidate` did not exist yet.
**Corpus:** 407 facts, 59 predicates.

## What was verified

Every claim in the three layers carries the fact ids it was authored from, as an `*Evidence:*`
line and a machine-readable `provenance:` list. Those ids are rows in the (unpublished) corpus
database.

| file | claims | all cited | distinct fact ids | ids that resolve |
|---|---|---|---|---|
| `anchors.md` | 26 | yes | 340 | 340 |
| `core.md` | 28 | yes | 389 | 389 |
| `predictions.md` | 32 | yes | 360 | 360 |
| `brief.md` | 12 sections | yes | 405 | **404** |

Union across all four files: **407 distinct ids, 406 resolve**. The corpus has 407 facts, so
**99.8% of the corpus is cited somewhere** in the specification.

The distillation stage reported its own numbers before authoring ran: 407 of 407 facts received a
disposition, 0 citations fabricated at the leaves, and every singularity reproduced verbatim.

## The one failure, kept on purpose

`brief.md` cites **`F-15040000`, which does not exist.** It appears in no package the author was
given, so compose invented it. The shape gives it away: four trailing zeros, not a hash.

This is left in place because a page of only clean chains tells you nothing about whether anyone
checked. It also marks exactly where the guarantee stops:

- The three layers are authored under a schema that makes citation mandatory. Fabrication there: **0**.
- Compose is not under that schema. Fabrication there: **1 in 405**.

A mandatory-citation schema buys you a guarantee that ids are present. It does not make them
accurate. Those are different properties and this example shows both.

## What it does not show

The specification is derived from a single corpus in one run, so the "verified" label that
normally marks a singularity confirmed across runs is withheld here: with one tree, a majority of
one is every singularity, and the label would assert exactly what one run cannot establish.

Citation resolution proves a claim points at real facts a leaf actually read. It does not prove
the facts caused the claim. Only ablation tests that, and it has been run on samples, never
exhaustively.

## The other examples

The seven other directories predate this work and contain **no fact ids at all**. They were
generated on 2026-03-09, before citations were enforced. They are still useful as writing samples,
and they cannot be used to check provenance. See `../README.md`.
