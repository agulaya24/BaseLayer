# AGENTS.md — Base Layer

> Behavioral compression for AI identity. Extracts behavioral patterns from text and compresses them into portable operating guides.

## What This Repo Does

Base Layer is a pipeline that takes text (conversations, blog posts, essays) and produces a structured identity model — a document that tells an AI how a specific person reasons, communicates, and makes decisions. Not what they know. How they think.

The output is a 3,000-5,000 token operating guide with three layers:
- **Anchors**: Epistemic axioms — beliefs this person reasons FROM (always active)
- **Core**: Communication operating guide — context-specific engagement modes (activation-triggered)
- **Predictions**: Behavioral patterns — situation→response loops (situation-triggered)

## Setup

```bash
git clone https://github.com/agulaya24/BaseLayer.git
cd BaseLayer
pip install -r requirements.txt
```

## Quick Start

```bash
# Initialize a subject
baselayer init

# Import text
baselayer import path/to/text --source text

# Extract behavioral facts (uses Anthropic Haiku API)
baselayer extract

# Embed facts for provenance tracing
baselayer embed

# Author identity layers (uses Anthropic Sonnet API)
baselayer author --layer all --compose

# View the result
cat data/identity_layers/identity_model.md
```

## Pipeline (5 Steps)

```
Import → Extract → Embed → Author → Compose
```

- **Import**: Multi-source (ChatGPT, Claude, journals, text files, directories)
- **Extract**: 47 constrained predicates via Haiku API. AUDN lifecycle (Add/Update/Delete/Noop)
- **Embed**: MiniLM-L6-v2 local vector embeddings for provenance tracing (ChromaDB)
- **Author**: Three-layer generation via Sonnet with H3 domain-agnostic prompts (73-word guard)
- **Compose**: Unified narrative brief via Opus (they/them, domain guard, FP warnings)

## Key Files

| File | Purpose |
|---|---|
| `src/baselayer/cli.py` | CLI entry point |
| `src/baselayer/extract_facts.py` | Fact extraction with AUDN |
| `src/baselayer/author_layers.py` | Layer authoring (ANCHORS/CORE/PREDICTIONS) |
| `src/baselayer/agent_pipeline.py` | Brief composition |
| `src/baselayer/mcp_server.py` | MCP server for Claude integration |
| `src/baselayer/seed_industry.py` | Website seeding pipeline |
| `src/baselayer/config.py` | All constants and paths |

## Architecture

- **Database**: SQLite (facts, conversations, provenance)
- **Vectors**: ChromaDB (local embeddings for retrieval)
- **API**: Anthropic (Haiku for extraction, Sonnet for authoring, Opus for composition)
- **Serving**: MCP server (identity Resource + recall/search/trace Tools)

## Testing

```bash
pytest tests/
```

400+ tests. GitHub Actions CI on Python 3.10, 3.11, 3.12.

## Environment Variables

```
ANTHROPIC_API_KEY=your-key     # Required for extraction/authoring
MEMORY_SYSTEM_ROOT=path        # Subject directory (default: current)
BASELAYER_SKIP_FACT_FLOOR=1    # Skip minimum fact check
```

## Research Findings

- 73-word domain guard eliminates topic skew in identity models
- 20% of facts sufficient for behavioral identification
- 71.83% prediction accuracy at 18:1 compression (Twin-2K, N=100, p=0.008)
- Structured output (JSON schema) eliminates parser fragility for predictions
- Format determines behavioral routing — axiom-structured briefs outperform flat preference lists

## Live Examples

- [Benjamin Franklin](https://base-layer.ai/examples/franklin) — 212 facts from autobiography
- [Frederick Douglass](https://base-layer.ai/examples/douglass) — 88 facts from autobiography
- [Warren Buffett](https://base-layer.ai/examples/buffett) — 505 facts from 48 shareholder letters

## License

Apache 2.0
