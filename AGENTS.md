# AGENTS.md for Base Layer

> The interpretive layer above memory. Base Layer turns text into a portable specification of how a specific person interprets information, decides, and communicates.

This file is for AI coding agents (Claude Code, Cursor, Windsurf, etc.) working in this repo or running Base Layer on a user's data.

## What this repo is

A Python package + CLI + MCP server. The pipeline takes text (conversations, journals, essays) and produces a 5,000 to 10,000 token specification structured in three layers:

- **Anchors:** the axioms a person reasons from (always active)
- **Core:** operational constraints and communication patterns (activation-triggered)
- **Predictions:** situation, behavioral pattern, directive (situation-triggered)

Memory systems give the agent the facts of a person. Base Layer gives the framework those facts come from. The two compose; they don't compete.

**Why this matters.** An AI agent can only act in alignment with how a specific person would act to the extent it represents how they reason. The specification is that representation.

## Setup

```bash
pip install git+https://github.com/agulaya24/BaseLayer.git
export ANTHROPIC_API_KEY=sk-ant-...
```

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
baselayer run <file>              # full pipeline
```

Step-by-step:

```bash
baselayer extract                 # Haiku, 47 predicates, AUDN lifecycle
baselayer embed                   # MiniLM-L6-v2 -> ChromaDB
baselayer author --layer all      # Sonnet, three-layer authoring
baselayer compose                 # Opus, unified specification
```

## Checkpoints

Run between major stages to catch quality issues:

```bash
baselayer extract && baselayer checkpoint extraction
baselayer embed && baselayer checkpoint classification
baselayer author && baselayer compose
```

Add `--fix` to apply rule-based corrections: `baselayer checkpoint classification --fix`.

## Output

After the pipeline:

1. **Specification** at `data/identity_layers/brief_v4.md` (relative to the subject directory). Primary artifact, 5,000 to 10,000 tokens.
2. **Three layers** (anchors, core, predictions). Intermediate structured artifacts.
3. **Fact database** with tier, type, and confidence metadata.
4. **Vector store** for semantic search over facts and source text.

## Connecting to AI

### MCP server

```bash
# Claude Code
claude mcp add --transport stdio base-layer -- baselayer-mcp

# Claude Desktop, claude_desktop_config.json:
{ "mcpServers": { "base-layer": { "command": "baselayer-mcp" } } }
```

The MCP server exposes the structural specification inline plus a single on-demand brief. As of 0.4.0, ANCHORS and PREDICTIONS are loaded with CORE in the always-on resource so the model never has to make a routing decision about a layer it cannot see.

Resources:

- **`memory://specification`** (always-on, canonical): CORE + ANCHORS + PREDICTIONS inline (~6 to 8K tokens) plus a brief manifest pointing at supplementary tools.
- **`memory://identity`** (deprecated alias): forwards to `memory://specification`.

On-demand specification tool:

- **`get_brief(reason)`:** unified narrative portrait (~3,000 tokens). Fetched when the query is broad, abstract, or self-reflective. Takes a one-sentence private `reason` for the call log.

Other tools:

- **`recall_memories`:** semantic retrieval of facts and episodic memories
- **`search_facts`:** keyword search across the fact database
- **`trace_claim`:** provenance from specification claims back to source facts
- **`verify_claims`:** run the four-check provenance verifier against authored claims
- **`get_stats`:** pipeline and database statistics
- **`get_call_log`:** recent MCP calls in this session (in-memory ring buffer)
- **`get_help(topic)`:** comprehensive Base Layer agent reference. Includes intent-to-action mappings, diagnostic flow, full CLI surface, full MCP-tool surface, state-file layout, and behavioral norms. Consult any time the user asks about Base Layer itself.

Every resource read and tool call emits a stderr log line of the form `[base-layer] INFO: mcp_call name=<tool> [k=v ...]`, routed by the MCP host to its log directory. Per-session traces live at `~/.baselayer/sessions/<pid>/log.jsonl` and are inspectable with `baselayer log list/show/tail/stats`.

### Manual injection

```bash
baselayer brief "Help me write a cover letter"
```

Outputs a context-tailored specification to stdout. Paste into any model's system prompt.

## Layer regeneration

```bash
baselayer author --layer anchors      # regenerate anchors
baselayer author --layer core         # regenerate core
baselayer author --layer predictions  # regenerate predictions
baselayer compose                     # recompose specification from existing layers
```

## Key source files

| File | Purpose |
|---|---|
| `src/baselayer/cli.py` | CLI entry point |
| `src/baselayer/extract_facts.py` | Fact extraction with AUDN lifecycle |
| `src/baselayer/author_layers.py` | Three-layer authoring |
| `src/baselayer/agent_pipeline.py` | Specification composition |
| `src/baselayer/mcp_server.py` | MCP server |
| `src/baselayer/config.py` | Constants and paths |
| `lexicon_schema.yaml` | 47-predicate behavioral grammar |

## Environment variables

```
ANTHROPIC_API_KEY=...                  # Required for extraction/authoring/composition
MEMORY_SYSTEM_ROOT=...                 # Subject directory (default: current)
BASELAYER_EXTRACTION_BACKEND=ollama    # Optional: local extraction via Ollama
BASELAYER_SKIP_FACT_FLOOR=1            # Skip minimum fact check
```

## Testing

```bash
pytest tests/
```

403 tests. GitHub Actions CI on Python 3.10, 3.11, 3.12.

## Live examples

- [Benjamin Franklin](https://base-layer.ai/examples/franklin): 212 facts from autobiography
- [Frederick Douglass](https://base-layer.ai/examples/douglass): 88 facts from autobiography
- [Warren Buffett](https://base-layer.ai/examples/buffett): 505 facts from 48 shareholder letters

## Troubleshooting

- **"No API key"**: `export ANTHROPIC_API_KEY=sk-ant-...`
- **"No facts extracted"**: Check `baselayer stats`. May need more source data.
- **"0 identity-tier facts"**: Run `baselayer checkpoint classification --fix`.
- **Thin predictions**: Normal for short texts. Anchors and core are often sufficient.
- **Re-extraction needed**: clear facts with `baselayer forget --all`, then delete `data/vectors/` to clear ChromaDB, then re-extract.

## License

Apache 2.0. See [LICENSE](LICENSE).
