# Recipe: Run the pipeline on a ChatGPT export

**Goal.** Take a user's ChatGPT export ZIP and produce a behavioral specification.

## Prerequisites

- Python 3.10 or newer.
- Base Layer installed: `pip install git+https://github.com/agulaya24/BaseLayer.git` (or `pip install -e .` from a source checkout). Base Layer is not currently on PyPI; install from GitHub.
- `ANTHROPIC_API_KEY` exported in the environment.
- A ChatGPT export ZIP file. The user can request one from `chat.openai.com -> Settings -> Data Controls -> Export data`.

## Working directory

Give each subject its own data root. The pipeline writes to `data/` under `MEMORY_SYSTEM_ROOT`, not under the current directory. When the variable is unset, an installed package uses `~/.baselayer` and code run from a clone uses the clone itself. Example:

```bash
mkdir -p ~/baselayer_subjects/me
export MEMORY_SYSTEM_ROOT=~/baselayer_subjects/me
```

## Steps

### 1. Initialize the database

```bash
baselayer init
```

Creates `data/database/memory.db` and the empty layer scaffolding.

### 2. Import the export

```bash
baselayer import /path/to/chatgpt-export.zip
```

The source type is auto-detected. To be explicit: `--source chatgpt`.

### 3. Preview cost (the gate)

```bash
baselayer estimate
```

Prints the estimated API spend for extraction. **Stop here and surface the estimate to the user. Wait for explicit confirmation before proceeding.** `baselayer estimate` prices extraction only, from your imported text and the dated rate table in `src/baselayer/distillation/spend.py`; it prints the table date, so check current prices. Authoring is not priced. Actual cost depends on text volume and provider pricing, so treat the estimate as a floor, not a budget.

### 4. Extract facts

```bash
baselayer extract
```

Runs Haiku across the imported conversations. Uses the 46 constrained predicates (`CONSTRAINED_PREDICATES` in `config.py`) and the AUDN lifecycle (Add, Update, Delete, NOOP).

Sanity-check after extraction:

```bash
baselayer stats
baselayer checkpoint extraction
```

`stats` shows conversation, message, and fact counts. `checkpoint extraction` flags quality issues. It reports only; there is no `--fix` flag.

**Under the turn contract** (`baselayer extract --turn-contract`, into a fresh corpus directory; see `docs/core/TURN_CONTRACT.md`). Before importing, set `subject_names` in `$MEMORY_SYSTEM_ROOT/data/import_config.json` to every form of the person's name the text uses, for example `{"subject_names": ["Benjamin", "Benjamin Franklin"]}`. Turn-mode extraction refuses to start without it.
- **Import.** It writes a `turns` table with each turn's speaker and voice class. Check the class distribution before extracting:

  ```bash
  sqlite3 "$MEMORY_SYSTEM_ROOT/data/database/memory.db" "SELECT voice_class, COUNT(*) FROM turns WHERE duplicate_of IS NULL GROUP BY voice_class"
  ```

  Pasted segments are excluded by default. What the local import config kept out is listed in `import_exclusions`.
- **Extraction.** Each run writes a record to `$MEMORY_SYSTEM_ROOT/data/database/extraction_runs/<run_id>.json`. Read its `gate_rejections` (`no_grounding`, `no_turn`, `not_own_voice`, `span_not_found`, `span_length`, `self_object`), `post_gate_drops` and `suspect` fields and report them to the user. A gate that rejected nothing or everything is flagged `suspect` and needs a look before anything is authored from the facts.

### 5. Embed for provenance

```bash
baselayer embed
```

Writes MiniLM-L6-v2 vectors to ChromaDB at `data/vectors/`.

### 6. Author the three layers

```bash
baselayer author --layer all
```

Generates anchors, core, and predictions via Claude Sonnet 4.6. Writes to `data/identity_layers/` under the data root.

### 7. Optional: compose a prose brief

```bash
baselayer compose
```

Optional. The three layers are the specification. `compose` writes a prose brief from them (Opus 4.6) at `data/identity_layers/brief_v5_clean.md`. `baselayer run` does not run it.

## Shortcut: full pipeline in one command

```bash
baselayer run /path/to/chatgpt-export.zip
```

`run` chains import, the cost-estimate gate, extract and author, then a traceability step (fact tiers, embeddings, vector provenance, a tension check). Under the turn contract (set `BASELAYER_TURN_CONTRACT=1`; `run` has no `--turn-contract` flag) it stops before authoring while extraction left quarantined chunks, unless given `--accept-gaps`. It does not compose a brief; `baselayer compose` is optional and separate. Use `--yes` only if the user has pre-confirmed the spend. Do not pass `--yes` automatically.

## Expected output

| Path | Contents |
|---|---|
| `data/identity_layers/anchors_v4.md` | Anchors layer. Decision foundations. |
| `data/identity_layers/core_v4.md` | Core layer. Operational constraints. |
| `data/identity_layers/predictions_v4.md` | Predictions layer. Behavioral triggers. |
| `data/identity_layers/brief_v5_clean.md` | Optional prose brief, only if `compose` was run. |
| `data/database/memory.db` | SQLite fact database. |
| `data/vectors/` | ChromaDB vector store. |

## Failure handling

- **Extraction returns zero facts.** Run `baselayer stats`. If conversation count is zero, the import did not work; check the file path and `--source` flag. If conversations exist but no facts, the corpus may be too short or noisy. Inspect a sample: `sqlite3 "$MEMORY_SYSTEM_ROOT/data/database/memory.db" "SELECT title FROM conversations LIMIT 10"`.
- **Extraction returns far fewer facts than expected (e.g. 12-42 instead of 200+).** Stale ChromaDB vectors cause AUDN to NOOP. Fix: run `python -m baselayer.extract_facts --reset`, then re-extract. The reset deletes extracted facts, the extraction log, and the fact vectors so every conversation is reprocessed. It is irreversible and has no confirmation prompt; confirm with the user first. It keeps imported conversations and user-corrected facts and does not touch layers already written under `data/identity_layers/`. The safest clean start is a fresh data root: point `MEMORY_SYSTEM_ROOT` at an empty directory. `baselayer forget --all` plus deleting `data/vectors/` is not a reset: the extraction log still marks every conversation as done, so re-extraction processes nothing.
- **`No API key` error.** `export ANTHROPIC_API_KEY=sk-ant-...`.
- **Authoring produces thin predictions.** Normal for short corpora. Anchors and core are usually sufficient. Do not regenerate without diagnosing.
- **Compose fails with missing layer files.** Re-run `baselayer author --layer all`.

## Voice when reporting back to the user

State what was produced. Cite paths. Do not editorialize. Report the cost estimate `baselayer estimate` printed and the number of facts extracted, as numbers.
