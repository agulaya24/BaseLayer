# Recipe: Serve a specification via MCP

**Goal.** Connect an existing behavioral specification to Claude Desktop or Claude Code via the Base Layer MCP server. The server serves the three layers in `data/identity_layers/` (CORE, ANCHORS and PREDICTIONS, written by `baselayer run` or `baselayer author`) plus a manifest of supplementary tools. It sends them in its MCP instructions; some clients may truncate long instructions, and the `memory://specification` resource always returns the full text. The optional prose brief, if one was composed, is on demand via `get_brief(reason)`.

The server does not serve a specification written by `baselayer author-from-package` (the cited path) or the output of `baselayer consolidate`. Nothing in this package serves those yet.

## Prerequisites

- Base Layer installed: `pip install git+https://github.com/agulaya24/BaseLayer.git` (or `pip install -e .` from a source checkout). Base Layer is not currently on PyPI; install from GitHub. The `baselayer-mcp` entrypoint must resolve in your shell.
- The three layer files `anchors_v4.md`, `core_v4.md` and `predictions_v4.md` under `data/identity_layers/` in the data root you intend to serve from. If you do not have them, run `recipes/run_pipeline_on_chatgpt_export.md` first.
- Claude Code or Claude Desktop installed.

## Step 1. Register the MCP server

### Claude Code

```bash
claude mcp add --scope user --transport stdio base-layer -- baselayer-mcp
```

The server reads the data root from `MEMORY_SYSTEM_ROOT` (unset: `~/.baselayer` for an installed package, the clone itself when run from a clone), not from the current directory. Set that variable in the server's environment to serve a specific subject.

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "base-layer": {
      "command": "baselayer-mcp"
    }
  }
}
```

Restart Claude Desktop after editing.

## Step 2. Verify both resource URIs resolve

Start a new Claude Code session. The server reads the data root from `MEMORY_SYSTEM_ROOT`, not from the session's working directory. The next conversation should receive the specification through the server's instructions.

To confirm: ask the assistant to read the resources by URI.

```
Read memory://specification
Read memory://identity
```

Both should return identical content. `memory://identity` is a deprecated alias that forwards to `memory://specification`. If both resolve to the same text, the server is registered correctly.

If only one resolves: the server is running an older build. Reinstall: `pip install --upgrade git+https://github.com/agulaya24/BaseLayer.git`.

## Step 3 (optional). Test the tools

The server exposes eight tools beyond the specification resource (`get_brief`, `recall_memories`, `search_facts`, `trace_claim`, `verify_claims`, `get_stats`, `get_call_log`, `get_help`). Worth a quick smoke test on first connect.

`trace_claim` and `verify_claims` read provenance tables keyed by the served claim ids. If the served layers were authored somewhere else (for example by `author-from-package`), those tables may not hold the served ids, and both tools return nothing useful. For a specification built from packages, `baselayer verify-spec` checks citations against the corpus directly and read-only.

```
Call get_stats()
```

Returns conversation count, fact count, tier breakdown.

```
Call recall_memories("trading approach")
```

Returns relevant facts and episodic memories for the query.

```
Call search_facts("startup", limit=10)
```

Keyword search across active facts.

```
Call trace_claim("A1")
```

Trace anchor claim `A1` back to the facts linked to it: each fact's text, tier, recurrence, link method and source conversation title, plus up to three evidence spans (the person's quoted words and turn id) for a fact that came from turn-contract extraction. Replace `A1` with any claim ID from the specification (anchors are `A*`, core are `C*`, predictions are `P*`).

```
Call verify_claims(claim_id="A1")
```

Run the binary verification checks against a specific claim. Returns existence, recurrence, cross-domain coverage, temporal consistency, and contradiction signals. It writes its results into the corpus database.

## Expected output

After registration, every new Claude Code or Claude Desktop conversation receives the structural specification (CORE + ANCHORS + PREDICTIONS) plus a manifest through the server's instructions, as far as the client passes them on; ask the model to read `memory://specification` to be sure it has the full text. If a prose brief was composed, the model can pull it via `get_brief(reason)` when the conversation is broad, abstract, or self-reflective. Recent MCP usage is queryable in-session via `get_call_log()`.

## Verifying the server is actually running

The Claude Code `/mcp` dialog and other UI status indicators have been observed to read "off" or "needs reconnect" while the server was actively responding to tool calls. **Do not trust the UI indicator as the source of truth.** Verify by either:

- Running `claude mcp list` from a terminal. Healthy local stdio servers show `✓ Connected`.
- Asking the model to call any Base Layer tool (e.g., "what does my specification say about my communication style") and seeing it return content.

The `/mcp` dialog itself is for managing Anthropic-hosted cloud connectors (Google Drive, Calendar, Gmail). Local stdio servers like `base-layer` are managed only via the CLI (`claude mcp list/add/remove`).

## Failure modes

- **`baselayer-mcp: command not found`.** The package is not installed in the active Python environment. `pip install git+https://github.com/agulaya24/BaseLayer.git` and confirm `which baselayer-mcp` resolves.
- **Resource returns "No specification layers found".** The data root (`MEMORY_SYSTEM_ROOT`) has no layer files under `data/identity_layers/`. Run the pipeline first; the always-on resource reads the authored layers.
- **Server starts but no resource appears in Claude Code.** Restart Claude Code after `claude mcp add`. The harness picks up new servers at session start, not mid-session.
- **The model never calls `get_brief()`.** Tail the MCP host's stderr log and filter for `[base-layer]` to see what the model is actually fetching. If the model never fetches the brief on broad or self-reflective questions, the manifest's trigger language may need sharpening; current behavior is informed by the Beyond Recall finding that interpretation-heavy questions are where the brief adds the most value.
- **`memory://identity` returns different content than `memory://specification`.** This is a bug. Both should be identical (alias forwards to same handler). File an issue.

## Notes

- The MCP server runs over stdio. No accounts. Base Layer sends no usage data.
- The specification stays on the user's machine. Base Layer uploads nothing.
- Retrieval tools open a local ChromaDB store. ChromaDB has its own anonymized telemetry setting, on by default; Base Layer opens the store with that setting off.
- For non-MCP integrations (ChatGPT custom instructions, Cursor, any system prompt), paste the text below `## Injectable Block` in each of the three layer files. You lose fact search this way. `baselayer brief` is archived; do not use it.
