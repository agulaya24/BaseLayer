# Recipe: Run the pipeline on a ChatGPT export

**Goal.** Take a user's ChatGPT export ZIP and produce a behavioral specification.

## Prerequisites

- Python 3.10 or newer.
- Base Layer installed: `pip install git+https://github.com/agulaya24/BaseLayer.git` (or `pip install -e .` from a source checkout). Base Layer is not currently on PyPI; install from GitHub.
- `ANTHROPIC_API_KEY` exported in the environment.
- A ChatGPT export ZIP file. The user can request one from `chat.openai.com -> Settings -> Data Controls -> Export data`.

## Working directory

Run all commands from a dedicated subject directory. The pipeline writes to `./data/` relative to the cwd. Example:

```bash
mkdir -p ~/baselayer_subjects/me
cd ~/baselayer_subjects/me
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

Prints the estimated API spend for extraction. **Stop here and surface the estimate to the user. Wait for explicit confirmation before proceeding.** Roughly $0.50 to $2.00 for ~1,000 conversations.

### 4. Extract facts

```bash
baselayer extract
```

Runs Haiku across the imported conversations. Uses the 47-predicate lexicon and the AUDN lifecycle (Add, Update, Deprecate, NOOP).

Sanity-check after extraction:

```bash
baselayer stats
baselayer checkpoint extraction
```

`stats` shows conversation, message, and fact counts. `checkpoint extraction` flags quality issues. Add `--fix` to apply rule-based corrections.

### 5. Embed for provenance

```bash
baselayer embed
```

Writes MiniLM-L6-v2 vectors to ChromaDB at `data/vectors/`.

### 6. Author the three layers

```bash
baselayer author --layer all
```

Generates anchors, core, and predictions via Sonnet. Writes to `data/identity_layers/`.

### 7. Compose the unified specification

```bash
baselayer compose
```

Opus composes the three layers into a unified specification at `data/identity_layers/brief_v4.md`.

## Shortcut: full pipeline in one command

```bash
baselayer run /path/to/chatgpt-export.zip
```

`run` chains import, extract, embed, author, and compose with the cost-estimate gate before extraction. Use `--yes` only if the user has pre-confirmed the spend. Do not pass `--yes` automatically.

## Expected output

| Path | Contents |
|---|---|
| `data/identity_layers/brief_v4.md` | Unified behavioral specification. Primary artifact. 5,000 to 10,000 tokens. |
| `data/identity_layers/anchors_v4.md` | Anchors layer. Decision foundations. |
| `data/identity_layers/core_v4.md` | Core layer. Operational constraints. |
| `data/identity_layers/predictions_v4.md` | Predictions layer. Behavioral triggers. |
| `data/database/memory.db` | SQLite fact database. |
| `data/vectors/` | ChromaDB vector store. |

## Failure handling

- **Extraction returns zero facts.** Run `baselayer stats`. If conversation count is zero, the import did not work; check the file path and `--source` flag. If conversations exist but no facts, the corpus may be too short or noisy. Inspect a sample: `sqlite3 data/database/memory.db "SELECT title FROM conversations LIMIT 10"`.
- **Extraction returns far fewer facts than expected (e.g. 12-42 instead of 200+).** Stale ChromaDB vectors cause AUDN to NOOP. Fix: `baselayer forget --all`, then delete `data/vectors/`, then re-extract.
- **`No API key` error.** `export ANTHROPIC_API_KEY=sk-ant-...`.
- **Authoring produces thin predictions.** Normal for short corpora. Anchors and core are usually sufficient. Do not regenerate without diagnosing.
- **Compose fails with missing layer files.** Re-run `baselayer author --layer all`.

## Voice when reporting back to the user

State what was produced. Cite paths. Do not editorialize. If the cost estimate was $1.40 and extracted 312 facts, say so.
