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
# Full suite (490 tests, ~30 seconds, no API calls)
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
  cli.py                # CLI entry point (28 subcommands)
  extract_facts.py      # Step 2: Fact extraction (Haiku API or Ollama)
  author_layers.py      # Step 4: Three-layer specification authoring
  agent_pipeline.py     # Step 5: Specification composition
  import_conversations.py  # Step 1: Multi-source importer
  mcp_server.py         # MCP server for Claude Desktop/Code
  verify_provenance.py  # Claim-to-source tracing
tests/                  # 490 tests, all offline
docs/                   # Architecture, decisions, evaluation
examples/               # Sample specifications for 7 subjects
```

## Architecture

The pipeline has 5 steps: **Import → Extract → Embed → Author → Compose.**

- `config.py` is the single source of truth for all constants, paths, and the 46 constrained predicates (45 behavioral plus an `unknown` fallback).
- Every other module imports from `config.py`. The dependency graph is acyclic.
- See `docs/core/ARCHITECTURE.md` for the full pipeline diagram.
- See `docs/core/DECISIONS.md` for the catalogue of design decisions with reasoning.

## Session and Decision Notation

You'll see references like `S79`, `D-056`, `D-078` in code comments and docs. These refer to:

- `S##`: Session number (development sessions with the AI pair-programming partner)
- `D-###`: Design decision number (documented in `docs/core/DECISIONS.md`)

These are internal development archaeology. They trace WHY code looks the way it does. You don't need to understand them to contribute, but they're there if you want the history.

## Where to Contribute

We especially welcome:

- **Evaluation:** new benchmarks, improved metrics, replication studies
- **Source type adapters:** new importers (Slack, Discord, email, etc.)
- **Local model support:** improving Ollama extraction quality, testing 32B-class models for authoring and composition
- **Documentation:** tutorials, examples, translations

## Pull Request Process

1. Fork the repo and create a feature branch
2. Run `pytest tests/ -x`. All tests must pass.
3. Keep changes focused. One concern per PR.
4. Include test coverage for new functionality
5. Reference relevant design decisions (D-###) if your change relates to documented architecture choices
