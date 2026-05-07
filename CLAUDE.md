# CLAUDE.md

Claude Code-specific guide for working in the Base Layer repo. This file complements [`AGENTS.md`](AGENTS.md) (provider-neutral) with Claude Code harness specifics.

For background on the project, read [`AGENTS.md`](AGENTS.md) and [`README.md`](README.md) first. This file is shorter on purpose.

## Project context

Base Layer is the interpretive layer above memory. The pipeline takes text (conversations, journals, essays, books) and produces a behavioral specification: a 5,000 to 10,000 token structured document that captures how a specific person interprets information, decides, and communicates. Memory systems retrieve facts. The specification supplies the framework those facts are read through.

If you are running in this repo as Claude Code, you are most likely doing one of four things:

1. Running the pipeline on the user's text data (ChatGPT export, journal directory, document corpus).
2. Debugging extraction, authoring, or composition (a stage produced too few facts, a layer regenerated wrong, etc.).
3. Exploring example specifications under `examples/` to understand the output format.
4. Connecting the local MCP server to inject the specification into a Claude conversation.

If the user's request is ambiguous, ask before running anything that spends API budget.

## Voice and prose constraints

When you generate user-facing text in this repo (commit messages, doc edits, blog drafts, paper edits, recipes, comments in source), follow the project's voice constraints:

- No em-dashes. Restructure sentences. Do not substitute hyphens.
- No GTM language ("beats", "crushes", "outperforms", "wins"). Scientific framing only.
- Canonical terms: "interpretive layer" and "specification" body-primary. "Behavioral specification" on first mention. Do not use "behavioral compression" or "identity model" in new prose.
- No marketing prose. Action-first. Direct.
- Aarik wrote the project. He does not write code; he architects and directs. Write for an audience of one technical product owner.

The voice constraints exist as user-memory entries (e.g. `feedback_no_em_dashes.md`). Do not duplicate their contents here; just follow them.

## Commands an AI agent should know

All commands invoked as `baselayer <subcommand>`. Source of truth: [`src/baselayer/cli.py`](src/baselayer/cli.py).

| Command | One-liner |
|---|---|
| `baselayer init` | Initialize a fresh database in the current subject directory. |
| `baselayer import <file>` | Import ChatGPT/Claude export, journal, text file, or directory. |
| `baselayer estimate` | Preview API cost before extraction. |
| `baselayer extract` | Extract facts via Haiku (47 predicates, AUDN lifecycle). |
| `baselayer embed` | Generate ChromaDB vectors for provenance tracing. |
| `baselayer author --layer all` | Author anchors, core, and predictions layers (Sonnet). |
| `baselayer compose` | Compose unified specification from the three layers (Opus). |
| `baselayer run <file>` | Full pipeline with cost-gate. Runs `import` -> `extract` -> `embed` -> `author` -> `compose`. |
| `baselayer brief "<message>"` | Print a context-tailored specification to stdout. |
| `baselayer stats` | Database stats: conversations, facts, tier breakdown. |
| `baselayer search "<query>"` | FTS keyword search across active facts. |
| `baselayer provenance --claim A1` | Trace a specification claim back to its supporting facts. |
| `baselayer verify --layer all` | Run the four-check provenance audit on authored claims. |
| `baselayer checkpoint extraction` | Quality gate after extraction. Add `--fix` to apply corrections. |
| `baselayer forget --all` | Soft-delete all active facts. Confirm before running. |
| `baselayer journal` | Guided prompts when the user has no conversation history. |

For long-form usage details and step-by-step pipeline structure, see [`AGENTS.md`](AGENTS.md). Do not invent commands. If a flag does not appear in `cli.py`, it does not exist.

## MCP server quick-connect

Register the Base Layer MCP server with Claude Code:

```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

Once registered, the next Claude Code session loads two resources and eight tools.

**Resources** (always-on, client-controlled):

- `memory://specification`. The CORE layer (communication approach, context modes, narrative orientation, essential context) plus a manifest of what else is available on demand. Approximately 2,500 tokens, not the full specification. Canonical resource. Loads as context in every conversation.
- `memory://identity`. Deprecated alias for `memory://specification`. Forwards to the same content. Retained for backward compatibility; will be removed in a future release.

**Specification tools** (model-controlled, fetched when the conversation warrants):

- `get_anchors()`. Foundational beliefs and worldview (the ANCHORS layer). Approximately 2,500 tokens. Use when the conversation touches values, principles, or "what does this person care about."
- `get_predictions()`. Behavioral predictions across domains (the PREDICTIONS layer). Approximately 2,500 tokens. Use when modeling how the user will react in a specific situation.
- `get_brief()`. Unified composed brief (~7,000 tokens). The full specification document. Use sparingly; usually CORE plus a single layer is enough.

**Memory tools** (model-controlled, called on demand):

- `recall_memories(query)`. Semantic retrieval of relevant facts plus episodic memories for a query.
- `search_facts(query, limit=15)`. Keyword search across active facts (FTS5 with LIKE fallback).
- `trace_claim(claim_id)`. Provenance from a specification claim (e.g. `A1`, `P3`, `C2`) back to source facts and conversations.
- `verify_claims(claim_id="", layer="all")`. Run the binary verification checks (existence, recurrence, cross-domain coverage, temporal consistency, contradictions).
- `get_stats()`. Database summary: conversations, messages, active and superseded facts, tier and source breakdowns.

**Monitoring.** Every resource read and tool call emits a stderr log line of the form `[base-layer] INFO: mcp_call name=<tool> [k=v ...]`. Claude Code routes MCP server stderr to its log directory (`%APPDATA%\Claude\logs\` on Windows). Filter for `[base-layer]` to see which tools the model is choosing and how often it fetches additional layers vs operating on CORE alone.

**Partial-serving design.** The resource intentionally returns CORE plus a manifest, not the full specification. Rationale: CORE captures communication style and context-mode triggers (the highest-leverage content for any conversation), while ANCHORS and PREDICTIONS are situational. The model fetches them when relevant and skips them when not, keeping context costs in line with the conversation's actual needs. See [`docs/internal/spec_loading_workflow.md`](docs/internal/spec_loading_workflow.md) for the full picture and rollback procedure.

## Where to find what

| Path | Contents |
|---|---|
| `src/baselayer/cli.py` | CLI entry point. Source of truth for all subcommands and flags. |
| `src/baselayer/extract_facts.py` | Fact extraction with the AUDN lifecycle (Add, Update, Deprecate, NOOP). |
| `src/baselayer/author_layers.py` | Three-layer authoring (anchors, core, predictions). |
| `src/baselayer/agent_pipeline.py` | Specification composition (Opus). |
| `src/baselayer/mcp_server.py` | MCP server. Resources + tools. |
| `src/baselayer/config.py` | Constants, paths, database singletons. |
| `src/baselayer/verify_provenance.py` | The four-check verifier. |
| `lexicon_schema.yaml` | The 47 behavioral predicates. AUDN-governed. |
| `tests/` | 403 tests. `pytest tests/` runs them all. |
| `docs/core/` | Architecture, decisions, design principles. Read on demand, not at session start. |
| `docs/internal/` | Internal plans (refactor plans, agent-facing reviews, runbooks). Not user-facing. |
| `examples/` | Live example specifications (Franklin, Buffett, Douglass, Roosevelt, Wollstonecraft, Marks, patents). |
| `recipes/` | Copy-paste agent task recipes. |
| `data/` | User data (database, vectors, layers, briefs). Do not touch unless the task requires it. |

## Phase A naming alignment status

Phase A of the identity-to-specification refactor shipped 2026-05-06. The pattern is **additive aliases, not renames**. Both old and new names live forever; the new name is canonical.

- `memory://specification` is the canonical MCP resource URI.
- `memory://identity` is the deprecated alias. Forwards to the same content.
- The CLI flag `--identity-only` will gain a `--specification-only` alias in Phase B.
- The Python class `IdentityLayer` and module `identity_layers` will gain `SpecificationLayer` and `specification_layers` aliases in Phase B.

Full plan: [`docs/internal/identity_to_specification_refactor_plan.md`](docs/internal/identity_to_specification_refactor_plan.md). Do not duplicate that plan in new docs; link to it.

When writing new prose, use "specification" and "interpretive layer". Do not reintroduce "identity" terminology.

## Things NOT to do

- **Do not run destructive commands without confirmation.** `baselayer forget --all` deletes facts. `baselayer init --force` reinitializes the database. If the user did not explicitly request the action, ask first.
- **Do not invent commands or flags.** If a flag is not in `cli.py`, it does not exist. Read the source before running anything you have not run before.
- **Do not POST to unknown endpoints.** Read the route handler first. The S101 incident wiped tracking data for 48 subjects because an agent called a cleanup endpoint without reading it.
- **Do not modify `lexicon_schema.yaml` without understanding the AUDN lifecycle.** The schema governs predicates; predicate changes invalidate stored facts. Read [`docs/core/ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) and the extraction code first.
- **Do not re-extract without clearing both SQLite and ChromaDB.** Old vectors cause AUDN to return NOOP and you get 12-42 facts instead of 200+. Clear both: `baselayer forget --all` and delete `data/vectors/`, then re-extract.
- **Do not run the pipeline without the cost-estimate gate.** Use `baselayer run` (which gates by default) or run `baselayer estimate` before `baselayer extract`.
- **Do not use the `brief` or `chat` subcommands for new work.** Both are archived. Use `compose` for the V4 unified specification.
- **Do not retry the same failing approach more than twice.** Diagnose and redesign. If extraction returns zero facts twice, stop and read `extract_facts.py`.

## When in doubt

Ask the user before doing anything irreversible. Read the source before invoking unfamiliar commands. Prefer one fewer step over one extra step.
