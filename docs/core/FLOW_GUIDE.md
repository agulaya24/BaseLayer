# Base Layer: Flow Guide

## From install to a specification

A walkthrough of both ways to build a specification. Every step's options, inputs and outputs are
in [PIPELINE.md](../PIPELINE.md); when this guide and `baselayer <command> --help` disagree,
`--help` is right.

### 1. Install

```
pip install git+https://github.com/agulaya24/BaseLayer.git
```

Python 3.10 or later. Base Layer is not on PyPI (the `baselayer` name there belongs to another
project), so install from the GitHub URL, or clone the repository and `pip install -e .`.

### 2. Choose a data root and initialize

```
export MEMORY_SYSTEM_ROOT=~/bl/me && mkdir -p "$MEMORY_SYSTEM_ROOT"   # optional
baselayer init
```

Every command reads and writes under one data root: `MEMORY_SYSTEM_ROOT` when set (the directory
must already exist). Unset, it is `~/.baselayer` for a package installed from the GitHub URL, or
the clone itself (under its `data/`) when you run the code from a clone. It is never the current
directory. `init` creates
the database and asks you to acknowledge the privacy notice (`--accept-data-processing` skips the
prompt). Use a fresh data root for each corpus, and always for the cited path.

### 3. Set your API key

Set the `ANTHROPIC_API_KEY` environment variable in your shell profile or a secrets manager, not
by typing the key into a command.

Needed by every command that calls a model: `run`, `extract` (unless `--backend ollama`),
`batch-extract`, `author`, `compose`, `distill`, `author-from-package`, and
`verify-spec --run-model --rater api`. `import`, `estimate`, `embed`, `assemble`, `consolidate`,
`search`, `stats` and a dry-run `verify-spec` make no model call. `verify-spec --rater cli` runs
`claude -p` on your local Claude subscription with the API key removed from the child's
environment.

### 4. Pick a path

| | `baselayer run` | the cited path (experimental) |
|---|---|---|
| steps | one command | eight steps (0 to 7 below) |
| every claim cites facts | not guaranteed | required |
| verification and trigger index | not run | `verify-spec`, `consolidate` |
| served over MCP | yes | no |

---

## Path A: `baselayer run`

```
baselayer run chatgpt-export.zip      # or claude-export.json, a journal folder, notes.md
```

It initializes the data root if needed, imports the file, prints an extraction estimate and asks
to continue (`--yes` skips the prompt), extracts facts (Claude Haiku 5.5), writes the three layers
into `data/identity_layers/` (Claude Sonnet 4.6), then runs a traceability step: tiers facts,
builds the vector index, links claims to nearby facts, and runs a small Haiku check for tensions
between facts. It never composes a brief. A file that adds nothing new stops before any spend
unless you pass `--reauthor`.

`baselayer estimate` prices extraction only, from the dated rate table in
`src/baselayer/distillation/spend.py`. Treat it as a floor, not a budget.

The same steps, one at a time:

```
baselayer import chatgpt-export.zip     # .zip/.json exports, .txt/.md/.docx/.rst files or a folder
baselayer estimate
baselayer extract                       # --backend ollama for local extraction
baselayer author                        # all three layers; --layer core for one
baselayer embed                         # optional: message vectors for `baselayer search`
baselayer compose                       # optional: a single prose brief from the layers
```

Fact vectors are written during `extract`, so the MCP `recall_memories` tool and `baselayer verify`
work without `embed`. `embed` adds one vector per imported message, which only `baselayer search`
reads.

## Path B: the cited path

```
export MEMORY_SYSTEM_ROOT=~/bl/me && mkdir -p "$MEMORY_SYSTEM_ROOT"
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

0. **Name the person.** Set `subject_names` in `data/import_config.json` under the data root to
   every form of the person's name the text may use, before importing. Turn-contract extraction
   refuses to start without it, and the importer uses it too.
1. **Import** stores the text one turn per row and records who said each turn. Only turns the
   person typed or spoke can be cited later.
2. **Extract** with `--turn-contract`: every fact must quote the person's own words, and a gate in
   code drops any fact whose quote is not found in the person's turn. A rerun resumes where it
   stopped. Detail: [TURN_CONTRACT.md](TURN_CONTRACT.md).
3. **Distill**, once per layer (Claude Sonnet 5). Always pass `--layer`: without it the run uses
   `blind`, an undirected control arm, and prints a warning. The directory for `--out` must exist;
   `distill` checks it before any call. Detail: [DISTILLATION.md](DISTILLATION.md).
4. **Assemble**, once per layer. No model call.
5. **Author** the three layers (Claude Opus 5). Every claim must cite fact ids. A prose brief is
   written only with `--compose`.
6. **Verify.** `verify-spec` checks citations, evidence spans, voice and stamps against the
   database, read-only. Model-judged checks are priced and sent only with `--run-model`. Detail:
   [VERIFY_SPEC.md](VERIFY_SPEC.md).
7. **Consolidate** into an always-on set, a trigger index and duplicate groups. No model call, no
   claim text rewritten, 14 checks that must pass. Detail: [CONSOLIDATION.md](CONSOLIDATION.md).

`distill` and `author-from-package` print an estimate and refuse to start until you confirm the
rate table's date (`--rates-confirmed`, printed by `baselayer distill --help`) and give a spend
ceiling (`--confirm-spend` or `BASELAYER_SPEND_CEILING_USD`). Check current prices before
confirming. Spend rules: [PIPELINE.md](../PIPELINE.md#12-spend).

---

## Connect to your AI

**MCP (Claude Code):**

```
claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp
```

**Claude Desktop**, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "base-layer": {
      "command": "baselayer-mcp"
    }
  }
}
```

The server serves the three layers in `data/identity_layers/`, which only Path A writes. It does
not serve a cited-path `spec_out/` directory or the `consolidate` output. What the AI gets:

- `memory://specification` (resource): the three layers (CORE, ANCHORS, PREDICTIONS) with a short
  usage note and a list of the tools. The server also places this text in its MCP instructions;
  some clients may truncate long instructions, so the resource and the tools are the reliable way
  to read it in full.
- `recall_memories`, `search_facts`: retrieval over the facts (`recall_memories` needs the vector
  index).
- `trace_claim`: the facts linked to a claim, how each was linked and the source conversation; for
  turn-contract facts, also the person's quoted words.
- `verify_claims`, `get_stats`, `get_brief` (the optional brief, if one was composed), `get_help`,
  `get_call_log`.

Setup and checks: [recipes/serve_specification_via_mcp.md](../../recipes/serve_specification_via_mcp.md).

**By hand:** put the three layer files in the system prompt, or consolidate's `served.txt`
(always-on claims plus the trigger index) and look up the claims a situation names in
`index.json`.

```
Your text --> import --> extract --+--> author ----------------------------> data/identity_layers/ --> MCP server
                                   |    (Path A, `baselayer run`)                                     (resource + tools)
                                   |
                                   +--> distill --> assemble --> author-from-package --> spec_out/
                                        (Path B, cited)                                      |
                                                                          verify-spec, consolidate --> by hand
```

## Correcting and updating

Edit the layer files, hide facts with `baselayer review` or `baselayer forget`, and re-author.
Import new text and run the steps again; extraction only processes what is new. How a correction
moves through each path: [CORRECTIONS.md](../CORRECTIONS.md).

## Requirements

- Python 3.10 or later.
- An Anthropic API key for the model steps listed in step 3.
- Optional: Ollama with the model named by `LLM_MODEL` in `config.py` (`qwen2.5:14b`) for local
  extraction.
- Disk for the embedding model (downloaded from Hugging Face on first use) and the vector store.

Cost depends on how much text you import and on current provider prices. Model calls scale with
the corpus; `distill` and `author-from-package` print their own estimate before any call.
