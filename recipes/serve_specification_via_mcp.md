# Recipe: Serve a specification via MCP

**Goal.** Connect an existing behavioral specification to Claude Desktop or Claude Code via the Base Layer MCP server, so the specification loads as context in every conversation.

## Prerequisites

- Base Layer installed: `pip install git+https://github.com/agulaya24/BaseLayer.git` (or `pip install -e .` from a source checkout). Base Layer is not currently on PyPI; install from GitHub. The `baselayer-mcp` entrypoint must resolve in your shell.
- An existing specification at `data/identity_layers/brief_v4.md` in the subject directory you intend to serve from. If you do not have one, run `recipes/run_pipeline_on_chatgpt_export.md` first.
- Claude Code or Claude Desktop installed.

## Step 1. Register the MCP server

### Claude Code

```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

Run this from the subject directory whose specification you want served. The server reads from the cwd at launch.

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

Start a new Claude Code session in the subject directory. The next conversation should load `memory://specification` automatically as context.

To confirm: ask the assistant to read the resources by URI.

```
Read memory://specification
Read memory://identity
```

Both should return identical content. `memory://identity` is a deprecated alias that forwards to `memory://specification`. If both resolve to the same text, the server is registered correctly.

If only one resolves: the server is running an older build. Reinstall: `pip install --upgrade baselayer`.

## Step 3 (optional). Test the tools

The server exposes five tools beyond the specification resource. Worth a quick smoke test on first connect.

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

Trace anchor claim `A1` back to the facts that support it. Replace `A1` with any claim ID from the specification (anchors are `A*`, core are `C*`, predictions are `P*`).

```
Call verify_claims(claim_id="A1")
```

Run the binary verification checks against a specific claim. Returns existence, recurrence, cross-domain coverage, and contradiction signals.

## Expected output

After registration, every new Claude Code or Claude Desktop conversation in the subject directory will have the unified specification loaded as context. The model treats it as background information about the user. No further action is needed per-conversation.

## Failure modes

- **`baselayer-mcp: command not found`.** The package is not installed in the active Python environment. `pip install git+https://github.com/agulaya24/BaseLayer.git` and confirm `which baselayer-mcp` resolves.
- **Resource returns "No specification found".** The subject directory has no `data/identity_layers/brief_v4.md`. Run the pipeline first.
- **Server starts but no resource appears in Claude Code.** Restart Claude Code after `claude mcp add`. The harness picks up new servers at session start, not mid-session.
- **`memory://identity` returns different content than `memory://specification`.** This is a bug. Both should be identical (alias forwards to same handler). File an issue.

## Notes

- The MCP server runs over stdio. No network. No accounts. No telemetry.
- The specification stays on the user's machine. Nothing is uploaded.
- For non-MCP integrations (paste into ChatGPT custom instructions, Cursor, etc.), use `baselayer brief "<message>"` to print a context-tailored specification to stdout.
