# Progress

Where the Base Layer pipeline stands, what changed recently, and what comes next. Last updated
2026-10-19, against `main` after pull request #12.

This page is a summary. For how each step works, read [PIPELINE.md](PIPELINE.md). For what
changed in detail, read [CHANGELOG.md](../CHANGELOG.md). For plans, read
[ROADMAP.md](../ROADMAP.md). Terms used in a fixed sense are defined in
[DEFINITIONS.md](DEFINITIONS.md).

## How to read the status labels

Every line below carries one of these labels.

| label | meaning |
|---|---|
| **runs** | in this package, and runs by default when you use the command named |
| **built, opt-in** | in this package, tested, but off unless you pass a flag or run a module |
| **experimental command** | in this package and runnable, but its `--help` or the README marks it experimental: the interface and defaults may change |
| **not in this repository** | exists as research code outside this repository; not published |
| **designed** | written down, not built |

Two kinds of "experimental" are easy to confuse. The **cited build**, where every claim cites facts that quote the person's own words (`extract --turn-contract`,
`distill`, `assemble`, `author-from-package`, `verify-spec`, `consolidate`) is experimental but
ships in this package, and you can run it today. The work described in [docs/experimental/](experimental/README.md) is
not part of the package at all: it is design notes and research prototypes.

You can check every "runs" and "built" line yourself: the command exists in `baselayer --help`,
the module exists under `src/baselayer/`, and the CHANGELOG entry names it.

## Where the pipeline stands

### The `baselayer run` path (the older, quicker pipeline)

| part | status | where to check |
|---|---|---|
| Import of chat exports, journals, text files and folders, Claude Code sessions and history, meeting transcripts | runs | `baselayer import --help`; `import_conversations.py`, `turn_import.py` |
| Turn table on import: speaker from the source, a voice class per turn, pasted text excluded by default, secrets with a recognisable shape masked | runs | `turns.py`, `voice.py`, `redaction.py`; [PIPELINE.md](PIPELINE.md) section 4 |
| Legacy extraction on Claude Haiku 4.5, 46 listed predicates, AUDN against stored facts | runs (the default for `run`) | `extract_facts.py`; `CONSTRAINED_PREDICATES` in `config.py` |
| Static authoring of the three layers on Claude Sonnet 4.6 | runs | `baselayer author`; `author_layers.py` |
| Traceability step after authoring (vector provenance, a tension check on Claude Haiku 4.5) | runs | [PIPELINE.md](PIPELINE.md) section 1 |
| MCP server serving the three static layers, with tools to search facts and trace a claim | runs | `mcp_server.py`; README, "Using it with an agent" |
| Prose brief (`baselayer compose`) | built, opt-in; `run` never composes it | `baselayer compose --help` |
| Extraction on a local model through Ollama | built, opt-in (`baselayer extract --backend ollama`, or `BASELAYER_EXTRACTION_BACKEND=ollama`) | ROADMAP, "Local pipeline" |

### The cited build (the current design)

| part | status | where to check |
|---|---|---|
| Turn-contract extraction on Claude Haiku 5.5: every fact must quote the person's own words, checked by a gate in code | experimental command (`extract --turn-contract`, or `BASELAYER_TURN_CONTRACT=1`) | `turn_contract.py`; [core/TURN_CONTRACT.md](core/TURN_CONTRACT.md); decision D-108 |
| Chunk ledger: every extraction chunk is a checkpoint. Failed chunks retry, chunks that keep failing on their content are set aside, and gaps are written beside every artifact | runs on the turn-contract paths | `chunk_ledger.py`; `baselayer chunks --help` |
| Batch extraction through the Message Batches API | runs (`baselayer batch-extract`) | [PIPELINE.md](PIPELINE.md) section 5 |
| Distill: each chunk of facts yields themes, one-off facts kept word for word (singularities), contradictions kept unresolved, and one verdict per fact | experimental command | `distillation/distill.py`; [core/DISTILLATION.md](core/DISTILLATION.md) |
| Assemble: one package (the author's input) per layer, split into shards when too large, each authored in its own call; nothing dropped | experimental command | `distillation/assemble.py` |
| Author from package: every claim must cite fact ids, enforced by a strict schema | experimental command (Claude Opus 5 by default) | `distillation/author_from_package.py` |
| Quote gate, batch leaves, `--leaf-spans`, episode partitions, situation-first predictions | built, opt-in (module flags, off by default) | CHANGELOG, "Added (distillation)" |
| Spend guard: a dated rate table, an estimate before any billed call, and a required ceiling | runs on `distill` and `author-from-package` | `distillation/spend.py`; [PIPELINE.md](PIPELINE.md) section 12 |
| Stamps: facts extracted by this version (model, prompt hash, git commit, code path); every tree, package and layer of the cited build (also an input hash; a package has no model) | runs | [PIPELINE.md](PIPELINE.md) section 13 |
| `verify-spec`: deterministic checks run by default; model-judged checks are built and priced, and sent only with `--run-model` | experimental command | `src/baselayer/verification/`; [core/VERIFY_SPEC.md](core/VERIFY_SPEC.md) |
| `consolidate`: always-on set, duplicate groups and a trigger index, no model call, 14 checks | experimental command | `src/baselayer/consolidation/`; [core/CONSOLIDATION.md](core/CONSOLIDATION.md) |
| Model-built consolidation inputs (duplicate judge, trigger grouping, categories) | built, opt-in (`python -m baselayer.consolidation.build`) | [core/CONSOLIDATION.md](core/CONSOLIDATION.md), "Builders" |

### Not in this package

| part | status |
|---|---|
| Serving a cited build or its trigger index into an agent session, with claims pulled on demand | not in this repository; in progress (README, "Limits and what is not included yet") |
| Support filter (labels each fact supported, stretch or not supported against its own quote) and the sort of stretch facts by how they go beyond their quote | not in this repository; `distill --exclude-ids` accepts its output |
| A separate check of each claim's scope by model judges | not in this repository; `verify-spec --backcheck-results` reads a back-check's results |
| One command for the whole cited build | designed |
| Conformance checks, escalation for agents acting on someone's behalf, behavioural envelopes | designed or research prototypes; see [docs/experimental/](experimental/README.md) |

## Recent milestones

### Merged to main

- **2026-08-18, version 0.5.0.** Interpretive distillation moved into this package as
  `distill`, `assemble` and `author-from-package`, all marked experimental. The distance
  conversion for the vector store now reads each collection's distance measure, after a single
  formula was found to report unrelated facts as close matches. (CHANGELOG, 0.5.0)
- **2026-10-17, pull request #6.** The turn contract (decision D-108): import records who said
  each turn, and extraction stores a fact only if its quoted evidence is found word for word in
  the person's own turn. Also the chunk ledger, spend guards on distillation and authoring, the
  author quote gate, `verify-spec`, `consolidate`, stamps on every artifact, and a fix for
  responses whose first block is a thinking block. The prose brief left the automated flow.
- **2026-10-19, pull request #7.** The README was rewritten around the two build paths, with new
  [PIPELINE.md](PIPELINE.md), [DEFINITIONS.md](DEFINITIONS.md) and
  [CORRECTIONS.md](CORRECTIONS.md).
- **2026-10-19, pull request #8.** The remaining docs were brought into line with the code, plus
  small fixes: `estimate` prices extraction from the dated rate table, `distill` refuses a missing
  output directory before any billed call and warns when `--layer` is omitted, `verify-spec`
  passes `--safe-mode` to its CLI rater when available, and MCP `trace_claim` shows evidence
  spans.
- **2026-10-19, pull request #9.** The README was rewritten for a newcomer (one quick start,
  what each build produces and costs), with [PIPELINE.md](PIPELINE.md) section 14 (the cited build
  end to end) and an updated ROADMAP.
- **2026-10-19, pull request #10.** The README now describes the cited build as how Base Layer
  makes a specification, and `baselayer run` as the older, quicker pipeline.
- **2026-10-19, pull request #11.** The README opens by saying what Base Layer is and does, and
  How it works is again a table of every step of the cited build, what it gives you and what it
  protects against.
- **2026-10-19, pull request #12.** Plainer wording throughout the README, with a new opening.

### Learned from full runs

Since the 0.5.0 release the cited build has been run end to end, outside this repository, on more
than one corpus. The corpora and the specifications built from them are not published. These are the
findings that changed the code or the docs:

- **A leaf could fail on the person's own quotation marks.** A leaf reply that quoted the person's
  words, inner double quotes included, was invalid JSON, and a retry that only said "not valid
  JSON" got the same reply. The retry now names the parser's error and asks for inner quotes to
  be escaped, keeping the words verbatim. (`distillation/distill.py`)
- **A failed leaf could reach the author.** `assemble` now refuses a tree that holds a leaf whose
  reply could not be parsed, unless the module is run with `--allow-failed-leaves`
  (`python -m baselayer.distillation.assemble`), so a gap is a decision and not an accident.
- **Re-running one failed leaf is cheaper than re-running a layer.** Leaves are independent of
  each other, so a repaired leaf can be added to a tree whose other leaves are reused unchanged.
  This was done with a script outside this package; no command does it yet.
- **Adding text to a corpus.** A plain `batch-extract --process` deletes every extracted fact, then
  stores the batch's results. To add text, use sequential extraction (it processes only
  conversations not yet extracted) or `batch-extract --submit --incremental` followed by
  `batch-extract --process --resume`. ([PIPELINE.md](PIPELINE.md) section 5)

## Known open issues

The full list, with evidence, is [PIPELINE_ISSUES.md](PIPELINE_ISSUES.md). One found in recent runs
is not yet entered there:

- **Fixed 2026-10-26: a fact about someone else could be assigned to the person.** The gate's
  subject resolution (`turn_contract.resolve_subject`) gave a fact to the person when every quoted
  span was the person's own turn and the other subject was not named in the span. It now keeps
  any subject that is not the configured referent, and counts one no span names
  (`subject_unnamed` in the run record). The rewrite had turned a guest into the host on a policy
  extraction of Zitkala-Ša's essays ([core/TURN_CONTRACT.md](core/TURN_CONTRACT.md) §5).
- **The predicate list is a suggestion, not enforced.** `normalize_predicate()` keeps a verb
  that is not on the 46-item list, by design. So a small share of facts carries other predicates, and some of
  those facts are cited by claims. Open decision: map them to listed predicates, extend the list,
  or document them as allowed.

## What comes next

Consistent with [ROADMAP.md](../ROADMAP.md):

1. **Serve the cited build.** Put the always-on claims and the trigger index into an agent session
   and let the agent pull claims by id. Designed and tested outside this repository; not yet in
   the package.
2. **One command for the cited build**, so it no longer takes eight steps and several modules.
3. **Settle the open predicate-list issue above.**
4. **A trigger grouper stable enough to ship.** Two runs of the grouper still agree less than two
   runs of the duplicate judge do. ([core/CONSOLIDATION.md](core/CONSOLIDATION.md))
5. **Confirmation by the person.** The checks in this package establish that evidence is real
   and quoted correctly, not that a specification is faithful. Only the person it describes can
   confirm that, and the tooling for recording their answers is not built.
6. **Production readiness from the roadmap:** renaming "identity" to "specification" in the code, and a
   stable 1.0 command and tool surface.

Experimental directions that are not on the package roadmap are described, with their status, in
[docs/experimental/](experimental/README.md).
