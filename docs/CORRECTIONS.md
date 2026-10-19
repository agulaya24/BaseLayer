# Corrections: how a correction moves through the system

A specification is a reading made by models, so parts of it will be wrong. This file says where
each kind of error lives, how to correct it, and what has to be rebuilt afterwards. Commands are
as `--help` prints them on this version. Terms are defined in [DEFINITIONS.md](DEFINITIONS.md).

## 1. Kinds of correction

| what is wrong | where it lives | how to correct it |
|---|---|---|
| a claim is worded wrong, or overreaches | the layer file | edit the text (section 2), or correct the facts under it and re-author (sections 3 and 4) |
| a fact misreads what the person said | the fact database | hide the fact (section 3), then rebuild (section 4: re-author on the `run` path, start again from `distill` on the cited path) |
| a fact is not the person's (assistant text, a quote, another person) | the fact database | hide the fact and rebuild as above; under the turn contract, also check the turn's voice class and the import config |
| a pattern is missing | the source text, or the cut | add text (section 6), or check what extraction and distillation left out (the run record, the tree's dispositions, any `coverage_gaps*.json`) |

Correct the facts when the error is in the evidence. Edit the text when the evidence is right and
the wording is not. An edit to the text alone is lost the next time the layer is re-authored.

## 2. Editing layers by hand

**On the `baselayer run` path** the layers are `data/identity_layers/anchors_v4.md`, `core_v4.md`
and `predictions_v4.md` under the data root. The MCP server serves the text below each file's
`## Injectable Block` line, or, in a file without that line, everything after the first `---`
separator (or the whole file when there is none). It builds its instructions once when it starts, so restart the server
(or the client session) after an edit; the `memory://specification` resource re-reads the files on
each call.

**On the cited path** each layer is a `.md` and a `.json` file in the `author-from-package` output
directory. `consolidate` reads the `.json` and checks that the `.md` carries the same text (check
K02), so edit both, then run `consolidate` again. An edited claim keeps its fact ids unless you
change them; `verify-spec` will then check the edited claim against the facts it still cites.

## 3. Correcting facts

- **`baselayer review`** walks through active facts one at a time (`--tier`, `--limit`). Press `d`
  to hide a fact (it is marked superseded, by `user_review`; its vector is not removed, and no
  stale marker is written) or `f` to flag it with a note (a
  `user_corrections` row of type `flag`). It does not edit fact text, and a flag does not hide the
  fact or change any later step.
- **`baselayer forget`** hides facts by id (`--fact`), by conversation (`--conversation`) or all of
  them (`--all`, asks for confirmation). It is a soft delete: the fact rows stay and can be
  restored; their vectors are removed and are not restored. Imported conversation text stays.
- **Hidden facts drop out of later builds.** Distillation and static authoring read only active
  facts, and `verify-spec` reports a citation to a hidden fact as superseded.
- **Layers already written are not regenerated.** Only `forget` writes the stale marker. After a
  `forget`, the static layers in
  `data/identity_layers/` are marked stale (`baselayer stats`, the MCP server log and the served
  specification say so) until they are written again; any re-author clears the marker for the
  layers it rewrites. Hiding a fact with `review` leaves the layers unmarked, so re-author after a
  review yourself. A cited-path
  output directory is never marked stale. Run `verify-spec` on it to see which citations no longer
  resolve.
- **The `user_corrections` table.** Its schema has more columns and types than any command
  writes. What is and is not implemented:

  | part of a row | written by | read by |
  |---|---|---|
  | type `flag`, with the note in `annotation` | `baselayer review` (`f`) | nothing; a flag changes no later step |
  | types `DELETE`, `refuted`, `REATTRIBUTE` with `original_fact_id` | no command | `verify-spec`: a citation to that fact gets the status `corrected_<type>` instead of `live` |
  | `match_patterns` (a JSON list of strings), any type | no command | extraction (`extract`, with or without `--turn-contract`, and `batch-extract`): a new fact whose text contains any pattern, case-insensitive, is not stored |
  | type `REPLACE`, `corrected_fact_text` | no command | only the legacy module `python -m baselayer.assemble_brief --generate-identity`, which lists recent `DELETE` and `REPLACE` rows; no fact text is changed |
  | `corrected_category`, `corrected_subject`, `notes` | no command | nothing applies them |

  So the only corrections that take effect are a row you add by hand (for example with
  `sqlite3`) of one of the retiring types, which `verify-spec` honours, or with `match_patterns`,
  which later extraction honours. Neither rewrites existing facts or regenerates any layer; to drop
  a wrong fact from future builds, hide it with `review` or `forget`.

## 4. Re-authoring after a correction

Neither author reads the previous specification. Each layer is written from the facts (static
path) or from the package (cited path), so a corrected fact base gives a fresh reading, not an
edit of the old one.

**`baselayer run` path:** `baselayer author` rewrites all three layers (`--layer` for one) from the
current facts. No re-extraction is needed after a `forget`. `baselayer author --compose` also
rewrites the optional brief.

**Cited path:** every layer's tree is distilled from all the active facts (less any exclusions), so
a fact you hid is in
all three trees and all three packages. Re-authoring from the existing packages keeps it. After a
fact correction, start again from distillation for all three layers:

```
mkdir -p trees_v2 packages_v2
baselayer distill --layer anchors --max-facts 50 --out trees_v2/anchors.json \
    --rates-confirmed <table date> --confirm-spend <usd>       # repeat for core, predictions
baselayer assemble trees_v2/anchors.json --out packages_v2/anchors.json   # repeat for core, predictions
baselayer author-from-package --package packages_v2/anchors.json --package packages_v2/core.json \
    --package packages_v2/predictions.json --outdir spec_out_v2/ --db <memory.db> \
    --rates-confirmed <table date> --confirm-spend <usd>
baselayer verify-spec spec_out_v2/ --label me_v2 --corpus <data root> --out verify_v2/
baselayer consolidate spec_out_v2/ --out served_v2/
```

If you re-author from the old packages instead, the hidden facts stay in the input, and
`verify-spec` reports any claim that cites them as citing a superseded fact.

Write to a new output directory. `author-from-package` reuses any layer whose `.md` and `.json`
already exist in `--outdir` and does not re-author it unless `BASELAYER_REAUTHOR=1` is set. Claim
ids are assigned afresh on each authoring, so A3 in the new specification need not be A3 in the
old one.

## 5. Checking a specification against the person's corrections

When the person has said a statement about them is wrong, record it as a rule and check every new
specification against it, so the overturned statement cannot come back unnoticed:

```
baselayer verify-spec spec_out/ --label me --corpus <data root> --out verify_out/ \
    --corrections corrections.json
```

The file holds one entry per correction, each with rules of three kinds: `violation` (the
overturned wording is present), `requires_nearby` (a statement must carry its qualifier within a
window) and `review` (a likely regression for a person to decide). A violation in a claim's own text
fails; a cited fact carrying the old version is flagged, not failed, because it may be an accurate
record of what the person said at the time. The format is in the docstring of
`src/baselayer/verification/checks/corrections.py`. The file is about one person: keep it beside
their corpus, never in a repository.

## 6. Adding text later

`baselayer import` skips conversations it already holds; a Claude Code session that grew is
re-imported whole and marked for extraction again. Extraction then processes only what is waiting;
AUDN deduplicates against the facts already stored. `baselayer run <file>` stops before any spend when the file adds nothing, unless
`--reauthor` is given. On the batch path, submit with `--incremental` and process with
`--process --resume`. A cited-path specification is rebuilt from distillation, as in section 4.

## 7. Removing everything

Delete the data root (`MEMORY_SYSTEM_ROOT`; unset, `~/.baselayer` for an installed package, or the
`data/` directory of a clone you run from), which holds the database, the vectors, the layers, the
distillation archive and the default import config, and the MCP session logs in
`~/.baselayer/sessions/`, which record tool queries. Remove any output directories you created for
the cited path (trees, packages, specification, verification and consolidation output) and any
import config or corrections file kept elsewhere.
