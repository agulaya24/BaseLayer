# Contributing to Base Layer

## Quick Start

```bash
git clone https://github.com/agulaya24/BaseLayer.git
cd BaseLayer
pip install -e ".[dev]"
pytest tests/ -x
```

## Running Tests

```bash
# Full suite (414 tests, ~30 seconds, no API calls)
pytest tests/

# Specific module
pytest tests/test_extract_normalizers.py

# With coverage
pytest tests/ --cov=baselayer
```

All tests run offline. No API key needed for testing.

## Project Structure

```
src/baselayer/          # Core package
  config.py             # Constants, paths, predicates (start here)
  cli.py                # CLI entry point (25 subcommands)
  extract_facts.py      # Step 2: Fact extraction (Haiku API or Ollama)
  author_layers.py      # Step 3: Three-layer identity authoring
  agent_pipeline.py     # Step 4: Brief composition
  import_conversations.py  # Step 1: Multi-source importer
  mcp_server.py         # MCP server for Claude Desktop/Code
  verify_provenance.py  # Claim-to-source tracing
tests/                  # 414 tests, all offline
docs/                   # Architecture, decisions, evaluation
examples/               # Sample briefs for 9 subjects
```

## Architecture

The pipeline has 4 steps: **Import → Extract → Author → Compose.**

- `config.py` is the single source of truth for all constants, paths, and the 47 constrained predicates.
- Every other module imports from `config.py`. The dependency graph is acyclic.
- See `docs/core/ARCHITECTURE.md` for the full pipeline diagram.
- See `docs/core/DECISIONS.md` for 93 design decisions with reasoning.

## Session and Decision Notation

You'll see references like `S79`, `D-056`, `D-078` in code comments and docs. These refer to:
- **S##** — Session number (development sessions with the AI pair-programming partner)
- **D-###** — Design decision number (documented in `docs/core/DECISIONS.md`)

These are internal development archaeology. They trace WHY code looks the way it does. You don't need to understand them to contribute, but they're there if you want the history.

## Where to Contribute

We especially welcome:
- **Evaluation** — New benchmarks, improved metrics, replication studies
- **Source type adapters** — New importers (Slack, Discord, email, etc.)
- **Local model support** — Improving Ollama extraction quality
- **Documentation** — Tutorials, examples, translations

## Pull Request Process

1. Fork the repo and create a feature branch
2. Run `pytest tests/ -x` — all tests must pass
3. Keep changes focused — one concern per PR
4. Include test coverage for new functionality
5. Reference relevant design decisions (D-###) if your change relates to documented architecture choices
