# Sonnet Handoff: Repository Cleanup Plan

**Context:** Base Layer is a research project that's been public on GitHub (`agulaya24/BaseLayer`) for ~2 weeks. External reviewers (OpenPull, GPT) flagged packaging, privacy language, and contributor onboarding as the main gaps. This plan addresses all three.

**Goal:** Make the repo feel like "a productized research system" rather than "the author's internal lab." No pipeline logic changes. No feature work. Packaging and documentation only.

**Constraint:** Aarik does not write code. He will review the PR. Keep commits atomic and reviewable.

---

## Task 1: Package Restructure (`scripts/` → `src/baselayer/`)

**Priority:** #1 — Highest leverage. Every reviewer flags this.

### What to do

1. **Create `src/baselayer/` directory.** Move all `.py` files from `scripts/` to `src/baselayer/`.

2. **Move the archive too.** `scripts/archive/` → `src/baselayer/archive/`

3. **Update `pyproject.toml`:**
   ```toml
   [tool.setuptools]
   package-dir = {"" = "src"}
   packages = ["baselayer", "baselayer.archive", "baselayer.archive.dead_pipeline_steps"]
   ```
   Remove the old `baselayer = "scripts"` mapping.

4. **Update ALL imports in `src/baselayer/*.py`.** Every file currently does:
   ```python
   sys.path.insert(0, os.path.dirname(__file__))
   from config import ...
   ```
   Change to:
   ```python
   from baselayer.config import ...
   ```
   **Remove all `sys.path.insert` hacks.** There are ~100+ import statements across 24 files. The dependency graph is acyclic (no circular imports), so this is mechanical.

   **Import mapping (every occurrence):**
   - `from config import ...` → `from baselayer.config import ...`
   - `from extract_facts import ...` → `from baselayer.extract_facts import ...`
   - `from author_layers import ...` → `from baselayer.author_layers import ...`
   - `from import_conversations import ...` → `from baselayer.import_conversations import ...`
   - `from api_client import ...` → `from baselayer.api_client import ...`
   - `from agent_pipeline import ...` → `from baselayer.agent_pipeline import ...`
   - `from checkpoint import ...` → `from baselayer.checkpoint import ...`
   - `from verify_provenance import ...` → `from baselayer.verify_provenance import ...`
   - `from semantic_search import ...` → `from baselayer.semantic_search import ...`
   - `from init_database import ...` → `from baselayer.init_database import ...`
   - `from mcp_server import ...` → `from baselayer.mcp_server import ...`
   - `from embed import ...` → `from baselayer.embed import ...`
   - `from assemble_brief import ...` → `from baselayer.assemble_brief import ...`
   - `from batch_extract import ...` → `from baselayer.batch_extract import ...`
   - `from llm_provider import ...` → `from baselayer.llm_provider import ...`
   - `from ui import ...` → `from baselayer.ui import ...`
   - `import config` → `from baselayer import config` (or `import baselayer.config as config`)

5. **Update `config.py` path detection.** `config.py` uses `Path(__file__).parent.parent` to find PROJECT_ROOT. After the move, `__file__` will be in `src/baselayer/config.py`, so the depth increases by one. **Verify this carefully** — config.py is the hub that every other file depends on. Getting this wrong breaks everything.

   The actual function in `config.py` is `_resolve_project_root()`. The fix targets **two lines** inside it:

   ```python
   # BEFORE (scripts/config.py) — dev_root points to memory_system/
   dev_root = Path(__file__).parent.parent
   if (dev_root / "data").exists() or (dev_root / "scripts").exists():

   # AFTER (src/baselayer/config.py) — need one more .parent to reach repo root
   dev_root = Path(__file__).parent.parent.parent
   if (dev_root / "data").exists() or (dev_root / "src").exists():
   ```

   The `scripts` → `src` check update is also required: after the move, `scripts/` no longer exists at root.

6. **Update ALL test imports.** Tests currently do:
   ```python
   sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
   from config import ...
   ```
   Change to:
   ```python
   from baselayer.config import ...
   ```
   Remove all `sys.path.insert` lines from test files. Instead, ensure `pyproject.toml` or `conftest.py` makes the package importable (editable install via `pip install -e .` is the standard approach).

   **Update `conftest.py`:** Remove the `SCRIPTS_DIR` path hack. The package should be importable via normal Python machinery after `pip install -e .`.

7. **Update `__main__.py`:**
   ```python
   from baselayer.cli import main
   ```

8. **Leave a `scripts/` symlink or redirect.** Optional but helpful — if anyone has the old path in their shell history, a one-line `scripts/__init__.py` that raises an ImportError with "Package moved to src/baselayer/" prevents confusion.

9. **Update references in docs:**
   - `README.md` — any references to `scripts/` directory
   - `AGENT.md` — pipeline commands should still work (they use `baselayer` CLI, not direct file paths)
   - `CLAUDE_CODE_SETUP.md` — check for `scripts/` references
   - `GIT_PUSH_PREP.md` — references to script paths
   - `REFACTOR_GUIDE.md` — update if it references `scripts/`

### How to verify

```bash
pip install -e .
baselayer --help          # CLI still works
pytest tests/ -x          # All 414 tests pass
baselayer init            # Creates database
python -c "from baselayer.config import DATABASE_FILE; print(DATABASE_FILE)"
```

### Risk

**HIGH.** This touches every file. One missed import = broken pipeline. Run full test suite before and after. Diff every file. Do NOT batch this with other changes — commit separately.

---

## Task 2: Rewrite Privacy Section in README

**Priority:** #2 — Lead with the API dependency, not local storage.

### Current (lines 129-134):
```markdown
## Privacy

Your database, vectors, and identity layers are stored locally (SQLite + ChromaDB). No cloud sync, no accounts, no telemetry.

Extraction sends text to the Anthropic API. Nothing persists remotely beyond [Anthropic's standard API retention](https://www.anthropic.com/policies/privacy). For fully local processing, use `BASELAYER_EXTRACTION_BACKEND=ollama`.
```

### Rewrite:
```markdown
## Privacy & Data Flow

Base Layer sends your text to the Anthropic API during extraction and authoring. This is how the pipeline works — language models process your conversations to extract structured facts and author identity layers. Your data is subject to [Anthropic's API data policy](https://www.anthropic.com/policies/privacy) (zero-retention for API usage by default as of March 2025).

**What stays local:** Your database (SQLite), vectors (ChromaDB), extracted facts, and identity brief all live on your machine. No cloud sync, no accounts, no telemetry. The brief is yours.

**Fully local option:** Set `BASELAYER_EXTRACTION_BACKEND=ollama` to run extraction through a local model (Qwen 2.5). Authoring and composition still require Claude API access. A fully local pipeline is on the [roadmap](https://base-layer.ai/journey) as open model quality improves.
```

### Why this ordering matters:
- First sentence: what leaves your machine (the thing people worry about)
- Second paragraph: what stays local (the thing that's genuinely strong)
- Third paragraph: the escape hatch (Ollama) with honest scope

### Risk

**LOW.** Documentation only. No code changes.

---

## Task 3: Add CONTRIBUTING.md

**Priority:** #3 — Unblocks outside contributors.

### Create `CONTRIBUTING.md` at repo root:

```markdown
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
- See `docs/core/DECISIONS.md` for 80+ design decisions with reasoning.

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
```

**Note:** Update the `src/baselayer/` paths in this file AFTER Task 1 is complete. If Task 1 hasn't landed yet, use `scripts/` and update later.

### Risk

**LOW.** New file only.

---

## Task 4: Add GitHub Actions CI

**Priority:** #4 — Shows 414 tests actually run.

### Create `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: pytest tests/ -x --tb=short
```

### Risk

**LOW.** New file. But verify tests pass on Linux first — they currently run on Windows. Watch for path separator issues (`\` vs `/`). `config.py` uses `Path` objects, so this should be fine, but check.

---

## Task 5: Generate Lockfile (Optional)

**Priority:** #5 — Nice-to-have.

Run `pip freeze > requirements-lock.txt` from a clean install and commit it. Or if using `uv`, run `uv lock`. Add a note in README:

```markdown
# Pinned dependencies (for reproducible installs)
pip install -r requirements-lock.txt
```

### Risk

**LOW.**

---

## Execution Order

1. **Task 1 first, alone.** Commit, push, verify CI (if Task 4 is done) or run tests locally. This is the risky one.
2. **Tasks 2-4 can be done in parallel** after Task 1 lands. They're independent documentation/config changes.
3. **Task 5 last** — depends on Task 1 being stable.

## What NOT to Change

- No pipeline logic changes
- No prompt changes
- No new features
- Don't remove session notation comments (S##, D-###) from code
- Don't restructure `docs/`, `examples/`, `data/`, or `tests/` beyond import fixes
- Don't touch `archive/dead_pipeline_steps/` contents (they're historical reference)
- Don't add type annotations, docstrings, or linting fixes to files you're not already touching for imports

---

*Drafted by Opus for Sonnet execution. Aarik reviews PR.*
