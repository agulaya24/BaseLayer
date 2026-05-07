"""Comprehensive Base Layer reference for AI agents.

Returned by the get_help() MCP tool. Loaded on demand when the user asks
about Base Layer itself (status, capabilities, control, troubleshooting).
The text below is the canonical surface map: every CLI command, every
MCP tool, every state file, and the intent-to-action mapping the agent
should use to satisfy user requests without bouncing the user back to
docs.

Keep updated as new surfaces ship. The keys to AGENT_GUIDE_TOPICS map
the user's likely phrasing to the section they need.
"""

AGENT_GUIDE = """\
# Base Layer Agent Reference

Base Layer is the interpretive layer above memory. It serves a behavioral
specification of the user via an MCP server so the model can interpret
information, decide, and communicate the way the specific user does.

This reference exists so an AI agent (e.g., Claude Code) can answer any
user question about Base Layer and act on any Base Layer-related intent
without bouncing the user back to documentation. Treat the system as
invisible infrastructure: the user should not need to know commands,
file paths, or tool names; the agent runs them.

---

## Two states the user cares about

The user's mental model is binary:
- **on**: Base Layer is registered with Claude Code and the model is
  using the spec to inform responses.
- **off**: Base Layer is not registered or has been disabled, and the
  model is operating without spec context.

Everything else (counters, logs, reasons, per-session storage) is
infrastructure the agent can surface only when asked.

---

## Intent-to-action mapping

When the user says something like the left column, run the action on
the right and report the outcome plainly. Do not list commands at the
user; just do the work and report state.

| User intent (paraphrase)                          | Agent action                                                                                          |
|---------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| "Is Base Layer on?"                               | Run `claude mcp list`. If `base-layer: ✓ Connected` → on. Else → off.                                 |
| "Turn Base Layer on" / "enable it"                | Run `claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp`, then verify.         |
| "Turn it off everywhere"                          | Run `claude mcp remove --scope user base-layer`. Confirm it no longer appears.                        |
| "Pause it" (keep registered, stop serving)        | Run `baselayer serve disable`. Mid-session safe; no restart.                                          |
| "Resume it"                                       | Run `baselayer serve enable`.                                                                         |
| "What has it been doing?" / "show me usage"       | Run `baselayer log stats` for aggregate, `baselayer log tail --limit 20` for recent calls.            |
| "Why did you fetch X?" / "show me reasons"        | Run `baselayer log tail` and read the `reason:` lines.                                                |
| "What's in my spec?"                              | Pull from MCP via `get_brief(reason="user asked what's in their spec")` and summarize.                |
| "Regenerate my spec"                              | Run `baselayer author --layer all` then `baselayer compose`. Confirm cost gate first if noticeable.   |
| "Add this conversation to the corpus"             | Run `baselayer import <file>`, then `baselayer extract`, `baselayer embed`, then re-author/compose.   |
| "Is the model getting fresh info from my spec?"   | Re-author from current data: `baselayer author --layer all`, `baselayer compose`. Re-tag layer files. |
| "It's broken / not working"                       | Diagnostic flow below. Do not bounce the user; run the checks.                                        |

---

## Diagnostic flow when the user reports it's not working

Run in order and report what you find:

1. `claude mcp list`. Look for `base-layer`. If absent → not registered.
   Fix: `claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp`.
2. If present but says `Failed to connect`: try `claude mcp remove`, then re-add.
3. If present and `✓ Connected` but the user says spec is not being applied:
   a. Check `baselayer serve status` — if disabled, run `baselayer serve enable`.
   b. Check `baselayer log tail` — if you see calls but `reason` is missing
      from layer fetches, the model is running an older server cached in
      memory; advise the user to start a fresh Claude Code session.
   c. Check the spec files: ls `<MEMORY_SYSTEM_ROOT>/data/identity_layers/`.
      `core_v4.md`, `anchors_v4.md`, `predictions_v4.md`, `brief_v5_clean.md`
      should all exist. If missing, regenerate via the pipeline.
4. If the user mentions the `/mcp` dialog: that dialog is for
   Anthropic-managed cloud connectors (Drive, Calendar, Gmail). Local
   stdio servers like `base-layer` are managed only via `claude mcp ...`
   from the terminal. UI status indicators in `/mcp` may lag; trust
   `claude mcp list`.
5. Statusline shows `baselayer:off` even though the server is running:
   the statusline locates a session by matching its parent PID against
   recorded `parent_pid` in `~/.baselayer/sessions/<pid>/meta.json`.
   If the match fails (rare), the count display is stale — but the
   server is still serving the model. Run a tool to verify.

---

## CLI surface (subcommands of `baselayer`)

| Command                        | Purpose                                                                                  |
|--------------------------------|------------------------------------------------------------------------------------------|
| `baselayer init`               | Create database + vector store in current subject directory.                             |
| `baselayer import <file>`      | Import ChatGPT/Claude export, journal directory, or text file.                           |
| `baselayer estimate`           | Preview API cost before extraction.                                                      |
| `baselayer extract`            | Extract structured behavioral facts via Haiku (47 predicates, AUDN lifecycle).           |
| `baselayer embed`              | Generate ChromaDB vectors for the fact corpus.                                           |
| `baselayer author --layer all` | Generate the three layers (anchors, core, predictions) via Sonnet.                       |
| `baselayer compose`            | Compose unified narrative brief from the three layers via Opus.                          |
| `baselayer run <file>`         | Full pipeline (import -> extract -> embed -> author -> compose) with cost gate.          |
| `baselayer stats`              | Database stats: conversation count, fact count, tier breakdown.                          |
| `baselayer search "<query>"`   | FTS keyword search across active facts.                                                  |
| `baselayer provenance --claim` | Trace a specification claim back to its supporting facts.                                |
| `baselayer verify --layer all` | Run the four-check provenance audit on authored claims.                                  |
| `baselayer checkpoint <stage>` | Quality gate after a pipeline stage. `--fix` applies corrections.                        |
| `baselayer forget --all`       | Soft-delete all active facts. Confirm before running.                                    |
| `baselayer serve enable`       | Resume MCP spec serving (writes `~/.baselayer/serving_enabled = 1`).                     |
| `baselayer serve disable`      | Pause MCP spec serving without restart (writes 0). Mid-session safe.                     |
| `baselayer serve status`       | Print whether spec serving is currently enabled.                                         |
| `baselayer log list`           | List all MCP sessions (active + ended) with state and counts.                            |
| `baselayer log show --pid X`   | Print full call log for a specific session.                                              |
| `baselayer log tail [--limit]` | Print last N calls of most recent session.                                               |
| `baselayer log stats`          | Aggregate calls-by-tool across all sessions.                                             |
| `baselayer journal`            | Guided prompt session when the user has no conversation history.                         |

For the canonical command list, parse `src/baselayer/cli.py`.

---

## MCP tools (returned by the `base-layer` MCP server, as of 0.4.0)

| Tool / Resource                | Purpose                                                                                            |
|--------------------------------|----------------------------------------------------------------------------------------------------|
| `memory://specification`       | Always-on resource. Returns CORE + ANCHORS + PREDICTIONS inline (~6-8K tokens) plus a brief manifest. Loaded at session start. |
| `memory://identity`            | Deprecated alias for the above. Forwards to the same content.                                      |
| `get_brief(reason)`            | Unified narrative portrait (~3,000 tokens). Fetch for broad self-reflective queries.               |
| `recall_memories(query)`       | Semantic retrieval of facts and episodes from the user's history.                                  |
| `search_facts(query)`          | Keyword search across the active fact database.                                                    |
| `trace_claim(claim_id)`        | Provenance for a specification claim (e.g. `A1`, `P3`, `C2`).                                      |
| `verify_claims(...)`           | Binary verification checks against the fact database.                                              |
| `get_stats()`                  | Database summary: counts, tier breakdown, source breakdown.                                        |
| `get_call_log(limit, name_filter)` | Recent MCP calls in this session (in-memory ring buffer, 500 entries).                          |
| `get_help(topic)`              | This document. Consult when the user asks anything about Base Layer itself.                        |

**Note (0.4.0 design change):** Earlier 0.3.0 split ANCHORS and PREDICTIONS behind on-demand `get_anchors` and `get_predictions` tools. Live use surfaced two issues: (1) the model had to make routing decisions about layers it could not see, leading to over- and under-fetching; (2) the token savings were negligible. 0.4.0 inlines all three structural layers so the model always has the full structural spec without a routing decision. The unified narrative brief stays on-demand because it serves a different shape of query (broad self-reflective).

---

## State files (managed automatically)

| Path                                              | Purpose                                                          |
|---------------------------------------------------|------------------------------------------------------------------|
| `~/.baselayer/serving_enabled`                    | "1" or "0". Toggle for spec serving (the disable/enable toggle). |
| `~/.baselayer/sessions/<pid>/meta.json`           | Session metadata (pid, parent_pid, start_time, cwd).             |
| `~/.baselayer/sessions/<pid>/count`               | Live call counter for that session. Removed on clean shutdown.   |
| `~/.baselayer/sessions/<pid>/log.jsonl`           | Append-only call log, one JSON entry per call. Persists.         |
| `~/.claude.json` (`mcpServers` section)           | Claude Code MCP registration. Modified by `claude mcp add/remove`.|
| `<MEMORY_SYSTEM_ROOT>/data/identity_layers/`      | Layer source files. CORE is what the resource serves.            |
| `<MEMORY_SYSTEM_ROOT>/data/database/memory.db`    | SQLite fact + conversation database.                             |
| `<MEMORY_SYSTEM_ROOT>/data/vectors/`              | ChromaDB vector store for provenance and recall.                 |

`MEMORY_SYSTEM_ROOT` is resolved in `src/baselayer/config.py`: env var if
set, else the repo root (dev), else `~/.baselayer/` (install).

---

## Behavioral norms for the agent

- Treat Base Layer as invisible infrastructure. Don't say "I have access
  to your Base Layer specification" or "let me load your spec". Just
  behave consistently with what's in the spec.
- When the user asks anything about Base Layer (status, capabilities,
  control), don't respond with command lists. Run the relevant command
  yourself and report the outcome.
- If a Base Layer action requires the user's confirmation (anything
  costly, anything destructive, anything visible to others), confirm
  before acting. Otherwise, just do the work.
- The `reason` parameter on layer-fetch tools is a private internal
  trace, not a user dialog. Provide it honestly; never surface it in the
  conversation.
- If the model in the current session cannot directly run a CLI command
  (no terminal access), advise the user one short line ("run `baselayer
  serve disable`") rather than narrating the system.

---

## When to fetch the brief

The structural layers (CORE, ANCHORS, PREDICTIONS) are always loaded
inline at session start; you do not need to fetch them. The unified
brief is the only on-demand layer in 0.4.0.

- `get_brief` — fetch when the query is broad, abstract, or
  self-reflective and the structural layers feel too schematic for the
  shape of conversation. Examples: "help me think through my career",
  "what should I focus on this quarter", "I'm feeling stuck".
- Do not fetch the brief for narrow factual or single-domain queries;
  the structural spec already covers those.

---

## Common follow-up questions and answers

**"What is Base Layer doing right now?"**
Run `baselayer log tail`. Report the count and the last few `reason:`
lines.

**"Did you use my spec to answer that?"**
Check `baselayer log tail`. If you fetched a layer in the last few
calls, yes; if not, no.

**"Is my spec up to date?"**
`ls -la <MEMORY_SYSTEM_ROOT>/data/identity_layers/` shows file mtimes.
If they're stale relative to the user's recent corpus, suggest running
the pipeline to re-author.

**"Make Base Layer faster" / "trim what it sends"**
0.3.0 is already partial-serving (CORE plus on-demand layers). Further
reductions would require either (a) sub-CORE chunking or (b) activation
matching, both not yet implemented. Note as a future direction; don't
manually trim CORE.

**"Disable Base Layer for this conversation only"**
There is no per-conversation toggle. Run `baselayer serve disable`
before the conversation, work, then `baselayer serve enable` after. The
user can also remove the registration with `claude mcp remove`.
"""


def get_topic_section(topic: str) -> str:
    """Return a focused slice of the guide for a specific topic.

    Used by get_help(topic) when the agent wants only the relevant
    section, not the whole guide.
    """
    if not topic:
        return AGENT_GUIDE

    topic_lower = topic.lower().strip()

    # Map common queries to section headers
    aliases = {
        "intent": "## Intent-to-action mapping",
        "intents": "## Intent-to-action mapping",
        "actions": "## Intent-to-action mapping",
        "broken": "## Diagnostic flow",
        "fix": "## Diagnostic flow",
        "diagnostic": "## Diagnostic flow",
        "troubleshoot": "## Diagnostic flow",
        "cli": "## CLI surface",
        "commands": "## CLI surface",
        "tools": "## MCP tools",
        "mcp": "## MCP tools",
        "files": "## State files",
        "paths": "## State files",
        "state": "## State files",
        "norms": "## Behavioral norms",
        "behavior": "## Behavioral norms",
        "fetch": "## When to fetch which layer",
        "layer": "## When to fetch which layer",
        "questions": "## Common follow-up questions",
        "faq": "## Common follow-up questions",
    }

    section_header = None
    for alias, header in aliases.items():
        if alias in topic_lower:
            section_header = header
            break

    if section_header is None:
        # Topic not recognized; return the whole guide.
        return AGENT_GUIDE

    # Extract the section: from the header to the next ## or end
    lines = AGENT_GUIDE.splitlines()
    section_start = None
    for i, line in enumerate(lines):
        if line.startswith(section_header):
            section_start = i
            break

    if section_start is None:
        return AGENT_GUIDE

    section_end = len(lines)
    for i in range(section_start + 1, len(lines)):
        if lines[i].startswith("## ") and not lines[i].startswith(section_header):
            section_end = i
            break

    return "\n".join(lines[section_start:section_end]).rstrip()
