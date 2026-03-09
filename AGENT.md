# Base Layer — Agent Deployment Guide

Use this file to run Base Layer's pipeline on a user's dataset from within Claude Code or any AI coding agent.

## Prerequisites
- Python 3.10+
- `pip install baselayer` (or clone the repo)
- `ANTHROPIC_API_KEY` set in environment

## Quick Pipeline (6 commands)

```bash
# 1. Initialize the data directory
baselayer init

# 2. Import the user's data (pick one or more)
baselayer import chatgpt-export.zip        # ChatGPT export
baselayer import claude-export.json        # Claude export
baselayer import ~/journals/               # Directory of text files
baselayer import my-notes.txt              # Single text file

# 3. Check cost before spending
baselayer estimate

# 4. Extract facts from conversations (Haiku API, ~$0.002/conversation)
baselayer extract

# 5. Run enrichment pipeline (embed → score → classify → tier)
baselayer process

# 6. Author identity layers + compose behavioral brief
baselayer author --compose
```

## What Each Step Does

| Step | Command | Model | Cost | Time |
|------|---------|-------|------|------|
| Init | `baselayer init` | None | Free | <1s |
| Import | `baselayer import <file>` | None | Free | seconds |
| Extract | `baselayer extract` | Haiku | ~$0.002/convo | 10-20min/1K |
| Process | `baselayer process` | Haiku + Sonnet | ~$2 total | 10-30min |
| Author | `baselayer author --compose` | Sonnet + Opus | ~$0.50 | 2-3min |

Total for ~1,000 conversations: **~$5-8**

## Checkpoints (recommended)

Run checkpoints between major stages to catch data quality issues early:

```bash
baselayer extract
baselayer checkpoint extraction        # verify extraction quality

baselayer process
baselayer checkpoint classification    # verify classification accuracy
baselayer checkpoint                   # full pipeline quality report

baselayer author --compose
```

If checkpoint reports issues, use `--fix` flag: `baselayer checkpoint classification --fix`

## Output

After the pipeline completes, the user has:

1. **Behavioral brief** (`~/.baselayer/data/identity_layers/brief_v4.md`) — compressed behavioral model, ~2,000-4,000 tokens. This is the primary artifact.
2. **Three identity layers** (anchors, core, predictions) — intermediate structured artifacts.
3. **Fact database** — all extracted facts with tier/type/confidence metadata.
4. **Vector store** — semantic search over facts and messages.

## Connecting to AI

### MCP Server (Claude Desktop / Claude Code)

```bash
# Claude Code
claude mcp add --transport stdio base-layer -- baselayer-mcp

# Claude Desktop — add to claude_desktop_config.json:
# { "mcpServers": { "base-layer": { "command": "baselayer-mcp" } } }
```

The MCP server exposes:
- **Identity Resource** (always-on) — unified brief injected into every conversation
- **recall_memories** (tool) — retrieve specific facts on demand
- **search_facts** (tool) — keyword search across fact database
- **trace_claim** (tool) — provenance from layer claims back to source facts

### Manual injection (any model)

```bash
baselayer brief "Help me write a cover letter"
```

Outputs a context-tailored brief to stdout. Paste into any model's system prompt.

## Individual Layer Regeneration

```bash
baselayer author --layer anchors       # regenerate just anchors
baselayer author --layer core          # regenerate just core
baselayer author --layer predictions   # regenerate just predictions
baselayer compose                      # recompose brief from existing layers
```

## Supported Input Formats

- ChatGPT exports (.zip or conversations.json)
- Claude exports (.json from claude.ai)
- Text files (.txt, .md, .docx)
- Directories (bulk import all text files)
- Journals and personal notes (highest quality identity data)

## Troubleshooting

- **"No API key"**: `export ANTHROPIC_API_KEY=sk-ant-...`
- **"No facts extracted"**: Check `baselayer stats` — may need more source data
- **"0 identity-tier facts"**: Run `baselayer checkpoint classification` to verify enrichment
- **Thin predictions**: Normal for short texts. ANCHORS and CORE may be sufficient.
- **Re-extraction needed**: Clear both SQLite and ChromaDB: `baselayer reset --facts` then re-extract
