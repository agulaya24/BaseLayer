# Pipeline: every step, in order

This is the detail behind the README's step list. Each step says what it reads, what it writes,
which model it calls (if any), what can stop it, and its options. Commands and flags are as
`baselayer <command> --help` prints them on this version; when this file and `--help` disagree,
`--help` is right. Terms used in a fixed sense are defined in [DEFINITIONS.md](DEFINITIONS.md).

## 1. Two paths

| step | `baselayer run <file>` | the cited path |
|---|---|---|
| init | yes, if the data root has no database | `baselayer init` |
| import | yes | `baselayer import` |
| estimate and confirm | yes (`--yes` skips the prompt) | no; `distill` and `author-from-package` price themselves |
| extract | legacy extraction, or the turn contract when `BASELAYER_TURN_CONTRACT=1` is set | `baselayer extract --turn-contract` |
| coverage gate | stops before authoring while the chunk ledger holds quarantined chunks, unless `--accept-gaps` | not applied; gaps are written beside each artifact |
| distill, assemble | no | yes |
| author | static `baselayer author`, Claude Sonnet 4.6 | `baselayer author-from-package`, Claude Opus 5 by default |
| traceability | tier facts, an embedding check, vector provenance, a tension check between facts on Claude Haiku 4.5 | no (`baselayer embed` if you want `baselayer search` over messages) |
| verify | no | `baselayer verify-spec` |
| consolidate | no | `baselayer consolidate` |
| served over MCP | yes (`data/identity_layers/`) | no |

`baselayer run` imports through the importer's own deduplication. A run whose file adds nothing new
and leaves nothing waiting for extraction stops before any API spend, unless `--reauthor` is given.
It never composes a brief. `--document-mode` (with `--subject`) is for a document corpus such as a
book or a set of filings, not for a person.

`baselayer pipeline` is a separate command for a subject already in the subject registry. It is
not one of the two paths above.

## 2. The data root

Every command reads and writes under one data root: `MEMORY_SYSTEM_ROOT` when set (the directory
must already exist). Without it, the root depends on where the code runs: a package installed from
the GitHub URL uses `~/.baselayer`, while code run from a clone of this repository (an editable or
source install) uses the clone itself, so data lands in the clone's `data/` directory (its
database, vectors, layers, distillation archive and import config are gitignored). It is never the current directory.
Set `MEMORY_SYSTEM_ROOT` to know which. `baselayer init` creates the database under `<root>/data/database/memory.db`.
`--accept-data-processing` acknowledges the privacy notice without a prompt; `--name` and
`--pronouns` skip the other two prompts. `init --force` drops nothing.

Use a fresh data root for each corpus, and always for the turn contract: turn-mode extraction
refuses a database holding facts that are not stamped with its version.

## 3. Step 0: the import config

A local JSON file holds everything specific to one person: their names, exclusions, an allowlist
of pasted segments to keep, meeting speaker labels and detector switches. It is read from
`BASELAYER_IMPORT_CONFIG` when set, otherwise `<root>/data/import_config.json`. It is personal data
and belongs beside the corpus, never in a repository. A missing file is an empty configuration; a
file that does not parse stops the run.

`subject_names` is required for the turn contract. It lists every form of the person's name the
text may use, for example a given name alone and the full name. Turn-mode extraction, sequential
and batch, refuses to start when it is empty, before any model call. Set it before importing: the
importer also uses it, to treat a greeting addressed to the person as pasted material.

Every key, with its default, is listed in the docstring of `src/baselayer/import_config.py`. What
each detector switch changes is in [core/DATA_TREATMENT_POLICY.md](core/DATA_TREATMENT_POLICY.md).

## 4. Import

`baselayer import <file>` reads a ChatGPT export, a Claude export, Claude Code sessions, a journal
folder, a text file or folder, a Claude Code `history.jsonl` (prompts only) or meeting transcripts (`--source`, detected when
omitted). It writes conversations, messages and a `turns` table with one row per turn.

Each turn records its speaker, taken from the source's own role field, and a voice class:

| voice class | citable |
|---|---|
| `own_typed`, `own_dictated` | yes |
| `assistant`, `other_person`, `pasted`, `compaction_summary`, `tool_result`, `harness_prompt`, `queued_command` | no, context only |

Pasted text is excluded by default and counted; a pasted segment can be kept by its turn id
(`paste_allowlist`). Secrets with a recognisable shape (provider keys, tokens, card numbers and the
like) are replaced by `[REDACTED:<kind>]` in every turn before it is stored, and counted per kind. A
secret written as free prose has no shape and is not caught.

Detail: [core/TURN_CONTRACT.md](core/TURN_CONTRACT.md) sections 1 and 2.

## 5. Extract

Model: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`). Facts are subject, predicate, object
statements, using a list of 46 predicates (`CONSTRAINED_PREDICATES` in `config.py`). New facts
pass through AUDN (add, update, delete as supersession, no-op) against the facts already stored.

**Legacy extraction** (`baselayer extract`, and `baselayer run` by default) reads whole
conversations in chunks and stores facts with no quoted evidence.

**Turn-contract extraction** (`baselayer extract --turn-contract`, or `BASELAYER_TURN_CONTRACT=1`)
chunks by whole turns with read-only preceding context, offers only own-voice turns as citable,
and asks for verbatim evidence spans with every fact. A gate in code, not in the prompt, stores a
fact only if every span names an own-voice turn in the chunk, matches that turn's text exactly
(after whitespace and quote-mark normalisation), and is within the length bounds (at least 3 words,
at most 400 characters by default). Rejections are counted by reason: `no_grounding`, `no_turn`,
`not_own_voice`, `span_not_found`, `span_length`, `self_object`.

- **The run record.** Every turn-mode run writes `<root>/data/database/extraction_runs/<run_id>.json`
  and a row in the `extraction_runs` table: settings, stamps, rejections by reason, subject
  resolution counts, the measured API usage of every billed call, and a `suspect` list. A gate that
  rejected nothing, or everything, is flagged. Read it after every run.
- **Fact count mode.** `BASELAYER_FACT_COUNT_MODE` sets whether the prompt carries a fact count:
  `coverage` (the default), `none`, `coverage_fragments` or `capped`. The mode used is recorded.
- **The chunk ledger** (`extraction_chunks`) makes every chunk its own checkpoint, sequential and
  batch: its facts, its row and the conversation's logged count commit together. A done chunk is
  never called again, a failed one is retried by the next run, and one that fails its two retries
  (or can no longer be rebuilt) is quarantined. Only content failures (truncated, unparseable,
  refused, input rejected) count toward that; an API access failure (network, timeout, 429, 5xx,
  auth, an expired batch) leaves the chunk failed and retryable and never quarantines it.
  Extraction exits 1 while any chunk is pending or failed. A conversation with a quarantined chunk
  is marked partial, not extracted. A corpus extracted before the ledger counts as done.
- **Commands.** `baselayer chunks list` shows chunks by status; `list --review` lists each
  quarantined chunk with why it failed, plus requests to re-extract a finished conversation;
  `list --backlog` lists done work made by another extraction model. `baselayer chunks retry`
  requeues failed or quarantined chunks; `baselayer chunks quarantine` quarantines one by hand;
  `baselayer chunks ack-model` records that backlog items were seen.
- **Gaps are stated, never hidden.** `baselayer run` does not author over quarantined chunks unless
  given `--accept-gaps`. Every authored artifact (`baselayer run` and `author`, `distill`, and
  `author-from-package`) gets a `coverage_gaps*.json` manifest beside it, stamped with the run id.
  `author-from-package` writes it in every run; without `--db` the manifest says the ledger was NOT
  CHECKED. The layer text is unchanged; static layers point to the manifest in their
  frontmatter.
- **The model is recorded, never acted on.** Every ledger row records the extraction model that
  settled it. A model change re-runs nothing: done work made by another model is a backlog,
  announced in one line at the end of each run. Naming an already extracted conversation
  (`python -m baselayer.extract_facts --conversation ID --reason ...`) or its legacy block
  (`baselayer chunks retry`) re-extracts nothing; the request goes on the review backlog.
- **Batch.** `baselayer batch-extract --submit` (add `--turn-contract`), then `--status`, then
  `--process`, uses the Message Batches API at half the per-token rate. `--incremental` submits only
  conversations not yet extracted, plus sessions that grew; process it with `--process --resume`.
  A plain `--process` first deletes every extracted fact and the extraction log.
- **Starting again.** `python -m baselayer.extract_facts --reset` deletes extracted facts, the
  extraction log, the chunk ledger and the fact vectors, keeps imported conversations and
  user-corrected facts, and asks no confirmation. The safest clean start is a new, empty data root.
  `baselayer forget --all` is not a reset: the extraction log still marks every conversation as
  done, so a later extraction processes nothing.

Detail: [core/TURN_CONTRACT.md](core/TURN_CONTRACT.md) sections 3 to 7.

## 6. Distill

`baselayer distill --layer <anchors|core|predictions> --out <tree.json>`, once per layer.
Model: Claude Sonnet 5 by default (`--model`). It reads the database read-only (`--db`, default
the data root's `memory.db`). It writes the tree to `--out` and a gaps manifest beside it
(`<out name>.coverage_gaps.json`), and also archives the tree beside the corpus, in
`<root>/data/distillation/` for the standard layout (otherwise a `distillation/` directory beside
the database file):
`<layer>_<run_id>.json`, `LATEST_<layer>.json` (a pointer to the newest tree),
`coverage_gaps_<layer>_<run_id>.json` and the run ledger `distill_runs.jsonl`. If that archive
cannot be written, the `--out` copy is the only record and the ledger goes beside it.

The facts are split into chunks (`--max-facts`, default 120; 50 is what the measured runs used,
and the leaf output ceiling was sized for about 60). Each chunk is one model call, a leaf, which
returns four channels: themes, singularities carried word for word, contradictions carried
unresolved, and one disposition for every fact in the chunk. A cited id that was not in the chunk
is removed; a singularity with such an id is dropped whole. Themes and singularities are then
collected from the leaves mechanically.

- `--layer`: always pass it. The default, `blind`, is an undirected control arm whose output is
  not comparable to a layer; a run that omits `--layer` prints a warning saying so.
- `--partition`: how facts are chunked (`predicate` by default; `category`, `predcat`, `random`,
  `semantic`, `time`).
- `--exclude-ids FILE`: leave named facts out of the population (a JSON list or one id per line).
  The file's sha256 and counts are stamped on the tree.
- `--include-other-subjects`: admit facts about other people, labelled as context. Excluded by
  default and counted either way.
- `--checkpoint FILE` writes leaves after every chunk; `--resume-from FILE` reloads them.
  `--limit-chunks N` stops early and stamps the tree `PARTIAL_RUN`.
- `--write-provenance` writes root citations into the corpus database. Off by default.
- Create the directories for `--out` and `--checkpoint` before the run. `distill` checks that
  they exist before facts load or any model call and refuses otherwise; it does not create them.
  The tree itself is written at the end, after the billed calls.

Module-only options (`python -m baselayer.distillation.distill`): `--leaf-spans` shows each leaf
up to three of every fact's own-word spans, and a singularity may then carry an `own_words`
excerpt that must match those spans; `--include-record-only` admits facts grounded only in record
rows (excluded by default). The batch path, `python -m baselayer.distillation.distill_batch`,
submits the leaves for all three layers as one Message Batches request (`--dry-run` prices it and
sends nothing; `--resume` collects a submitted batch without resubmitting). Its `--max-facts`
default is 50.

Detail: [core/DISTILLATION.md](core/DISTILLATION.md).

## 7. Assemble

`baselayer assemble <tree.json> [<tree.json> ...] --out <package.json>`, once per layer, all trees
of the same layer. No model call. It stratifies the tree's themes, singularities and contradictions
into one package for the author.

- `--min-runs`: how many runs a singularity must appear in to count as verified (default 3, or the
  number of trees when fewer). With one tree the verified label is withheld.
- `--shard-token-budget`: tokens of rendered evidence one author request may carry (default
  `BASELAYER_LEAF_PAYLOAD_CEILING` or 400,000). A package over it is split into shards of disjoint
  leaf ranges, and `--out` becomes a manifest. Nothing is dropped.
- The module (`python -m baselayer.distillation.assemble`) also accepts `--allow-failed-leaves`,
  needed when a tree holds a leaf whose reply could not be parsed.

## 8. Author

`baselayer author-from-package --package <anchors.json> --package <core.json> --package
<predictions.json> --outdir <spec_out>`. Model: Claude Opus 5 by default (`--model`; Claude Opus
5.5 is `claude-opus-5-5`), effort `high` (`--effort`). One call per layer, or one per shard, each
blind to the other layers.

Each claim is emitted through a strict schema: an id, a name, a statement, an `Active when` line,
the fact ids it rests on, and a contested flag. Fact ids not in the package are stripped from the
claim and counted; the request is sent again only when a claim is left with no valid fact id. It
writes, per layer, `<layer>.md` (readable) and `<layer>.json` (the same claims, structured), plus
`<layer>.stamp.json`, and a coverage gaps manifest (`coverage_gaps.json`, checked against the
chunk ledger only with `--db`). `--compose` adds a prose brief (`brief.md`), off by default.

**The quote gate** (module only: `python -m baselayer.distillation.author_from_package
--quote-gate --db <memory.db>`) checks every quoted phrase in a claim against the own-voice spans
of the facts the claim cites, at word boundaries. A quote of three or more words found in at most
five other supplied facts has those facts added to the claim's citations (listed in
`gate_added_citations`); any other failing quote loses its quote marks and keeps its words. It
never re-asks the author, and it refuses to run on a database without the span columns.

**The static path, for comparison.** `baselayer author` (and `baselayer run`) writes
`data/identity_layers/{anchors,core,predictions}_v4.md` on Claude Sonnet 4.6, from fact selections
made by code, with citations asked for but not required. `baselayer compose` writes an optional
prose brief from those layers on Claude Opus 4.6.

## 9. Verify

`baselayer verify-spec <spec_dir> --label <label> --corpus <root or memory.db> --out <dir>`. It
reads the corpus read-only and writes only `--out`. By default it is a dry run: every deterministic
check runs (citation resolution, a re-check of every evidence span against its turn, voice, stamps,
duplicates, trigger groups, grounding, practice), and the model-judged checks (support, voice,
fidelity, cross, adjudicate) are built and priced but not sent.

`--run-model` sends them, through one of two raters:

- `--rater cli` runs `claude -p` children on the local subscription, with API credentials removed
  from the child's environment, and with `--safe-mode` when the installed CLI lists it in
  `claude --help` (on a CLI without it the run continues, warns, and records `safe_mode: false`).
  `--rater-cwd` must be outside every project tree. `--probe` first
  asks the child what it can see and stores the answer; a run is recorded blind only when a probe
  ran clean, which needs at least one `--probe-canary` (with none, the probe cannot come back
  clean).
- `--rater api --model <id> --confirm-api-spend <usd>` bills API credits and refuses to start when
  the upper estimate exceeds the cap.

Modular checks with their own inputs: `--corrections` (the person's corrections file),
`--exclude-ids`, `--min-occasions`, `--backcheck-results` (reads an external back-check's results;
never runs one). Detail and the full check list: [core/VERIFY_SPEC.md](core/VERIFY_SPEC.md).

## 10. Consolidate

`baselayer consolidate <spec_dir> --out <dir>`. No model call. It reads the layer `.json` files
written by `author-from-package` (not the static `*_v4.md` layers) and writes, through stages that
each produce one stamped JSON file: the claims, evidence overlap, a duplicate grouping, the
always-on set, triggers, categories, `served.txt` (the always-on claims in full plus one line per
situation naming the claims to read), `index.json` (claim id to full text, fact ids and contested
note) and `checks.json`. It exits 1 when any of its 14 checks fails. No claim text is rewritten.

Three optional inputs are judged by a model and built separately, each priced and capped or run
on the subscription: `python -m baselayer.consolidation.build judge` (duplicate verdicts), `group`
(trigger grouping) and `categorize` (categories). Detail:
[core/CONSOLIDATION.md](core/CONSOLIDATION.md).

## 11. Side branches

- `baselayer embed`: embeds imported messages (`all-MiniLM-L6-v2`) into the ChromaDB `messages`
  collection, which `baselayer search` reads. Fact vectors (`memory_facts`), which `verify`, vector
  provenance and the MCP `recall_memories` tool read, are written during extraction, not here. The
  model is downloaded from Hugging Face on first use. ChromaDB's own anonymized telemetry is on by default; Base Layer builds every client it
  creates with it off. If you create ChromaDB clients in your own code, pass
  `Settings(anonymized_telemetry=False)` or set `ANONYMIZED_TELEMETRY=False`.
- `baselayer verify`: the older provenance audit of static layers (vector proximity, recurrence,
  cross-domain span, optional local NLI with `--nli`). It writes rows into the corpus database and
  is a different command from `verify-spec`. `--generate` links every claim, cited or not, to its
  nearest facts by embedding (top N per claim, no similarity floor), as the `run` traceability step
  also does; read every `vector` link as nearby, not used.
- `baselayer provenance --claim A1`: trace a static-layer claim to its facts.
- `baselayer search "<query>"`, `baselayer stats`: semantic search over embedded messages (needs
  `baselayer embed`); database counts.
- `baselayer checkpoint extraction`: a report on extraction quality. It changes nothing.

## 12. Spend

| command | priced before it runs | ceiling |
|---|---|---|
| `distill`, `author-from-package`, `distill_batch` | yes, from a dated rate table | required: `--confirm-spend <usd>` at or above the estimate, or `BASELAYER_SPEND_CEILING_USD`; a run with neither is refused |
| sequential extraction (`extract`, and `run`) | `run` prints `baselayer estimate` and asks | only when `BASELAYER_SPEND_CEILING_USD` is set, checked before every call against measured spend plus that call's worst case |
| `batch-extract` | no | none |
| static `author`, `compose` | no | none |
| the `run` traceability tension check (Claude Haiku 4.5, up to 30 calls) | no | none |
| `verify-spec --rater api` | yes | `--confirm-api-spend` |
| `consolidation.build` with the API backend | yes | as for `distill` |

The rate table lives in `src/baselayer/distillation/spend.py` with the date it was read
(`RATES_AS_OF`). A billed run refuses until you confirm that date (`--rates-confirmed`, or
`BASELAYER_RATES_CONFIRMED`) or pass both `--rate-in` and `--rate-out`. Check current prices before
confirming. Estimates assume about 3.5 characters per token and have undercounted real input, so
treat them as a floor. Each process takes its own ceiling; a full build's budget is the sum.

`baselayer estimate` prices extraction only, from the same dated rate table, and prints no
authoring figure. Treat it as a floor for extraction, not a budget for a run.

## 13. Stamps

| artifact | carries |
|---|---|
| fact (extracted by this version, either path) | `extraction_model`, `extraction_prompt_hash`, `git_commit`, repo-relative `code_path`; gated facts also `turn_contract_version`, `source_turn_id`, `evidence_spans` |
| tree, package, `author-from-package` layer and brief | `stamp_version`, `kind`, `turn_contract_version`, `model`, `prompt_hash`, `input_hash` (on a tree, a hash of the fact ids and fact text; on a package or layer, a hash of its input JSON), `git_commit`, `code_path`; layers also effort, token usage over every attempt, the rates used and the cost (`<layer>.stamp.json`); packages have no model |
| static layer (`*_v4.md`) | frontmatter: layer, generated time, version, model, provenance method, item count, a pointer to any coverage gaps manifest |
| consolidate output | `stage`, `run_id`, `git_commit`, `code_path`, `code_sha256` (a hash of the package's modules), `inputs`, `inputs_hash`, `params`, `model_calls: 0` |
| `verify-spec` report | verify version, definitions version, git commit, code path |

`git_commit` is the checkout's HEAD, with `-dirty` when it has uncommitted or untracked changes and
`-state-unknown` when that could not be read. Code outside a git work tree (a pip install) records
`unknown`. Facts extracted before these fields
existed carry none of them, and nothing back-fills them. Read an artifact's stamp before trusting it.
