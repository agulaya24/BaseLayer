# AGENTS.md for Base Layer

> The interpretive layer above memory. Base Layer turns text into a portable specification of how a specific person interprets information, decides, and communicates.

This file is for AI coding agents (Claude Code, Cursor, Windsurf, etc.) working in this repo or running Base Layer on a user's data.

## Orientation (read first if you are new here)

Base Layer is **human-side modeling**: it represents how a specific person reasons so an AI agent can act in alignment with that person rather than a population average. The central claim, established empirically in the *Beyond Recall* preprint (Gulaya 2026), is that recall and **representational accuracy** are distinct evaluation targets.

- **Recall** is whether a system can retrieve stored facts about a person.
- **Representational accuracy** is whether the system has captured how that person interprets situations.

Memory systems retrieve facts. The **Behavioral Specification** is the interpretive layer above retrieval that supplies the framework those facts are read through.

Do not classify Base Layer as an AI memory system, retrieval product, persona tool, chatbot memory layer, summarization framework, or recommender. Those are AI-side categories. Base Layer is a distinct lane: human-side modeling.

### The four artifacts (thesis stack)

| Artifact | Repo / location | Role |
|---|---|---|
| **Paper**: *Beyond Recall: Behavioral Specification as an Interpretive Layer for AI Personalization* | `https://github.com/agulaya24/beyond-recall` and arXiv (https://arxiv.org/abs/2605.28969) | Empirical argument |
| **Pipeline (this repo)**: BaseLayer | `https://github.com/agulaya24/BaseLayer` | Implementation (import -> extraction -> authoring, or the cited path through distillation, verification and consolidation; MCP server) |
| **Website / vision** | `https://www.base-layer.ai` | Public reference + long-form vision essay |
| **Study** | `https://github.com/agulaya24/beyond-recall` | Data, scripts, judge outputs, provenance behind every paper number |

Repo-specific orientation: [`ORIENTATION.md`](ORIENTATION.md). Long-form vision: `https://www.base-layer.ai/vision`. Machine-readable site index: `https://www.base-layer.ai/llms.txt`.

## What this repo is

A Python package + CLI + MCP server. The pipeline takes text (conversations, journals, essays) and produces a specification structured in three layers:

- **Anchors:** the axioms a person reasons from
- **Core:** operational constraints and communication patterns
- **Predictions:** situation, behavioral pattern, directive

On the cited path every claim in every layer cites the ids of the facts it rests on, and can carry an `Active when` line, the situation it applies in (the schema allows it to be empty; predictions are told to name a concrete situation). The three layers are the specification; a prose brief is optional.

Memory systems give the agent the facts of a person. Base Layer gives the framework those facts come from. The two compose; they don't compete.

**Why this matters.** An AI agent can only act in alignment with how a specific person would act to the extent it represents how they reason. The specification is that representation.

## Setup

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
```

Base Layer reads the model API key from the `ANTHROPIC_API_KEY` environment variable. Set it in the shell profile or a secrets manager; never type a key into a command or a file in the repository.

Or from a local clone:

```bash
git clone https://github.com/agulaya24/BaseLayer.git
cd BaseLayer
pip install -e .
```

> Base Layer is not currently on PyPI; the `baselayer` name there is held by an unrelated project. Install via the git URL or local clone.

## Running the pipeline

One command, with cost estimate gate:

```bash
baselayer init
baselayer import <file>          # ChatGPT/Claude export, journal, text file, directory
baselayer estimate                # preview cost
baselayer run <file>              # the older, quicker pipeline; far fewer checks than the cited path
```

Step-by-step:

```bash
baselayer extract                 # Haiku 4.5, 46 constrained predicates, AUDN lifecycle
baselayer embed                   # optional: messages -> ChromaDB, for `baselayer search`
baselayer author --layer all      # Sonnet 4.6, three-layer authoring (static path)
baselayer compose                 # optional: Opus 4.6, a prose brief from the layers (static path)
```

The cited path (experimental) is how the README describes making a specification: every claim cites facts that quote the person's own words. It is eight steps: name the person (`subject_names` in the import
config, before importing), `import`, `extract --turn-contract`, `distill` and `assemble` once per
layer, `author-from-package`, `verify-spec`, `consolidate`. Commands, options and spend:
[`docs/PIPELINE.md`](docs/PIPELINE.md). Terms: [`docs/DEFINITIONS.md`](docs/DEFINITIONS.md). Modules, tables and data flow: [`docs/core/ARCHITECTURE.md`](docs/core/ARCHITECTURE.md).

Model ids live in `config.py` (static path) and in the argparse defaults of the experimental
distillation commands (`distill`: Sonnet 5; `author-from-package`: Opus 5, Opus 5.5 via
`--model`). Read them there rather than from this file.

### The turn contract (opt-in extraction mode)

`docs/core/TURN_CONTRACT.md` (decision D-108) keeps a specification to the person's own words:

- **Import** writes a `turns` table. Every row records the speaker, taken from the source's own role
  field, and a voice class. Only `own_typed` and `own_dictated` can be cited. These classes are
  context only:
  - `assistant`
  - `other_person`
  - `pasted`
  - `compaction_summary`
  - `tool_result`
  - `harness_prompt`
  - `queued_command`

  Pasted text is excluded by default and can be allowlisted by turn id. Subject-specific signals
  (names, meeting speaker labels, exclusions, injection canaries) live in a local import config,
  never in the repo. `subject_names` must be set there before import: turn-mode extraction refuses
  to start without it.
- **`baselayer extract --turn-contract`** (or `BASELAYER_TURN_CONTRACT=1`):
  - chunks by whole turns, with read-only preceding context;
  - offers only own-voice turns as citable;
  - runs a gate in code that stores a fact only if every evidence span names an own-voice turn,
    matches its text verbatim, and is within the length bounds.
- **Rejections** are counted by reason (`no_grounding`, `no_turn`, `not_own_voice`,
  `span_not_found`, `span_length`, `self_object`) in `<corpus>/data/database/extraction_runs/<run_id>.json`. Read
  that record after every run: a gate that rejected nothing or everything is flagged `suspect`.
- **Stamps.** Every fact extracted by this version carries the extraction model, prompt hash, git
  commit (`unknown` when not run from a git clone) and repo-relative code path. Gated facts also carry the contract version, `source_turn_id` and `evidence_spans`.
- **`baselayer verify-spec <spec_dir> --label L --corpus C --out O`** checks a finished
  specification read-only. It is a dry run by default and calls no model. It re-gates every span of
  every gated fact and checks legacy facts at conversation level (`docs/core/VERIFY_SPEC.md`).
- **`baselayer consolidate <spec_dir> --out O`** builds the served form of a finished
  specification without calling a model. The output is the always-on claims in full, plus trigger
  categories whose lines name the claim ids to pull, plus an index JSON. Every stage writes one
  stamped JSON file, and 14 checks must pass: claim text unchanged, fact ids preserved, every claim
  reachable, every trigger wording verbatim from an authored condition
  (`docs/core/CONSOLIDATION.md`).
- **Build into a fresh corpus directory** (point `MEMORY_SYSTEM_ROOT` at a new directory). Turn
  mode refuses a database holding facts not stamped with its version.

## Checkpoints

Run between major stages to catch quality issues:

```bash
baselayer extract && baselayer checkpoint extraction
```

There is no `--fix` flag; `checkpoint` takes only a stage name. `scoring` and `classification` are legacy pre-S79 stages. On the cited path the checks are `verify-spec` and `consolidate`'s 14 checks.

## Output

After the pipeline:

1. **Specification**: the three layers. On the `baselayer run` path, `data/identity_layers/{anchors,core,predictions}_v4.md` under the data root; on the cited path, `<layer>.md` and `<layer>.json` in the `author-from-package` output directory.
2. **Optional brief**: `data/identity_layers/brief_v5_clean.md` (only if `compose` ran) or `brief.md` (only with `--compose`).
3. **Fact database** with tier, type, and confidence metadata.
4. **Vector store**: fact vectors written during extraction (for `recall_memories`, `verify` and vector provenance), and message vectors for `baselayer search` (after `embed`).
5. **Cited path only**: a `verify-spec` report and `consolidate` output (`served.txt`, `index.json`).

## Connecting to AI

### MCP server

```bash
# Claude Code, any folder
claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp

# Claude Desktop, claude_desktop_config.json:
{ "mcpServers": { "base-layer": { "command": "baselayer-mcp" } } }
```

The MCP server serves the three layers in `data/identity_layers/` (the `baselayer run` path) plus an optional on-demand brief. As of 0.4.0, ANCHORS and PREDICTIONS are served with CORE so the model never has to make a routing decision about a layer it cannot see. The server sends them in its MCP instructions; some clients may truncate long instructions, and the full text is always the `memory://specification` resource (or use the tools). It does not serve a cited-path specification or `consolidate` output.

Resources:

- **`memory://specification`** (canonical): CORE + ANCHORS + PREDICTIONS inline (its size depends on the corpus) plus a brief manifest pointing at supplementary tools.
- **`memory://identity`** (deprecated alias): forwards to `memory://specification`.

On-demand specification tool:

- **`get_brief(reason)`:** the optional prose brief, if one was composed. Fetched when the query is broad, abstract, or self-reflective. Takes a one-sentence private `reason` for the call log.

Other tools:

- **`recall_memories`:** semantic retrieval of facts and episodic memories
- **`search_facts`:** keyword search across the fact database
- **`trace_claim`:** provenance from a claim back to the facts linked to it in the database: each fact's text, tier, recurrence, link method and source conversation title, plus up to three of its evidence spans (the person's quoted words and turn id) when the fact came from turn-contract extraction
- **`verify_claims`:** run the provenance checks (existence, recurrence, cross-domain coverage, temporal consistency, contradictions) against the static layers' claims
- **`get_stats`:** pipeline and database statistics
- **`get_call_log`:** recent MCP calls in this session (in-memory ring buffer)
- **`get_help(topic)`:** comprehensive Base Layer agent reference. Includes intent-to-action mappings, diagnostic flow, full CLI surface, full MCP-tool surface, state-file layout, and behavioral norms. Consult any time the user asks about Base Layer itself.

Every resource read and tool call emits a stderr log line of the form `[base-layer] INFO: mcp_call name=<tool> [k=v ...]`, routed by the MCP host to its log directory. Per-session traces live at `~/.baselayer/sessions/<pid>/log.jsonl` and are inspectable with `baselayer log list/show/tail/stats`.

### Manual injection

Paste the three layer files into any model's system prompt (on the `run` path, the text below `## Injectable Block` in each), or paste `consolidate`'s `served.txt` and look up the claims it names in `index.json`. You lose fact search this way. `baselayer brief` is archived.

## Layer regeneration

```bash
baselayer author --layer anchors      # regenerate anchors
baselayer author --layer core         # regenerate core
baselayer author --layer predictions  # regenerate predictions
baselayer compose                     # optional: recompose the prose brief from existing layers
```

## Key source files

| File | Purpose |
|---|---|
| `src/baselayer/cli.py` | CLI entry point |
| `src/baselayer/extract_facts.py` | Fact extraction with AUDN lifecycle |
| `src/baselayer/author_layers.py` | Three-layer authoring |
| `src/baselayer/agent_pipeline.py` | Optional prose brief (`compose`) |
| `src/baselayer/distillation/` | Cited path: `distill`, `assemble`, `author-from-package`, the quote gate, spend |
| `src/baselayer/verification/` | `verify-spec` |
| `src/baselayer/consolidation/` | `consolidate` |
| `src/baselayer/mcp_server.py` | MCP server |
| `src/baselayer/config.py` | Constants, paths, and the extraction predicate vocabulary (`CONSTRAINED_PREDICATES`: 46 constrained predicates, 45 behavioral plus an `unknown` fallback) |
| `lexicon_schema.yaml` | Element-type schema for authored specification containers (axiom, prediction, context_mode, meta_section) plus provenance syntax |

## Environment variables

```
ANTHROPIC_API_KEY=...                  # Required for every billed step: extraction, authoring, compose, distill, author-from-package, verify-spec --rater api
MEMORY_SYSTEM_ROOT=...                 # Data root. Default: ~/.baselayer for an installed package; a source checkout uses its own root. Not the current directory.
BASELAYER_EXTRACTION_BACKEND=ollama    # Optional: local extraction via Ollama
BASELAYER_SKIP_FACT_FLOOR=1            # Skip minimum fact check
ANONYMIZED_TELEMETRY=False             # Optional belt: Base Layer already builds every ChromaDB client with anonymized telemetry off (ChromaDB's default is on). This also covers clients you create yourself. Base Layer sends no usage data itself.
```

## Testing

```bash
pytest tests/
```

GitHub Actions CI runs the suite on Python 3.10, 3.11, 3.12.

## Live examples

- [Benjamin Franklin](https://www.base-layer.ai/examples/franklin): autobiography
- [Frederick Douglass](https://www.base-layer.ai/examples/douglass): autobiography
- [Warren Buffett](https://www.base-layer.ai/examples/buffett): 48 shareholder letters

In this repository, [`examples/zitkala_sa/`](examples/zitkala_sa/) is the one example whose claims cite fact ids. Its fact database is not published, so the ids cannot be resolved from the repository.

## Troubleshooting

- **"No API key"**: set the `ANTHROPIC_API_KEY` environment variable (shell profile or secrets manager), then open a new shell.
- **"No facts extracted"**: Check `baselayer stats`. May need more source data.
- **"0 identity-tier facts"**: Run `baselayer checkpoint classification` to inspect. It reports; it does not repair, and there is no `--fix` flag.
- **Thin predictions**: Normal for short texts. Anchors and core are often sufficient.
- **Re-extraction needed**: `python -m baselayer.extract_facts --reset` deletes extracted facts, the extraction log, and the fact vectors so every conversation is reprocessed. It is irreversible and has no confirmation prompt; confirm with the user first. It keeps imported conversations and user-corrected facts and does not touch layers already written under `data/identity_layers/`. The safest clean start is a fresh data root: point `MEMORY_SYSTEM_ROOT` at an empty directory. `baselayer forget --all` plus deleting `data/vectors/` is not a reset: the extraction log still marks every conversation as done, so re-extraction processes nothing.
- **Removing facts**: `baselayer forget` hides facts (soft delete: rows marked superseded and restorable; their vectors are removed and not restored). Imported conversation text stays. Specification layers already written are not regenerated; they are marked stale (`baselayer stats`, the MCP server log and the served specification say so) until they are re-authored without the hidden facts. How corrections flow: [`docs/CORRECTIONS.md`](docs/CORRECTIONS.md). To remove everything, delete the data directory and the MCP session logs under `~/.baselayer/sessions/`, which record tool queries.

## License

Apache 2.0. See [LICENSE](LICENSE).
