# OpenRouter Proxy Design — Session 41

**Status:** Design complete, ready to build
**Decision:** D-049 (Custom OpenRouter Proxy over LiteLLM)
**Estimated build time:** ~3 hours

## Architecture

Custom aiohttp proxy (~400 LOC) that:
1. **Accepts** OpenAI-compatible chat/completions requests on localhost:5100
2. **Injects** identity brief into the system message
3. **Forwards** to OpenRouter (which routes to any model provider)
4. **Records** conversations and messages in SQLite for future extraction

## Why Custom Over LiteLLM

OpenRouter already provides multi-provider routing. LiteLLM would be a router on top of a router, adding 50+ dependencies for capabilities we don't need. The custom proxy does exactly four things: accept, inject, forward, record.

## Key Design Decisions

- **Optional dependency:** `pip install baselayer[proxy]` adds `aiohttp>=3.9.0`
- **Two modes:** `--mode identity` (fast, reads layer files ~1ms) or `--mode full` (full brief with retrieval ~200ms)
- **Session tracking:** X-Session-Id header or hash of first user message for conversation continuity
- **Streaming support:** SSE chunks forwarded in real-time, buffered for recording
- **Graceful degradation:** If no identity layers exist, proxy still works (forwards without injection)
- **Source tagging:** Conversations stored with `source='proxy'`, `scope='personal'`
- **SQLite WAL mode:** For concurrent access (proxy running + pipeline scripts)

## New Files

| File | Purpose |
|---|---|
| `scripts/proxy_server.py` | Core proxy server with streaming support |
| `scripts/proxy_session.py` | Session tracking and message recording |
| `tests/test_proxy.py` | Mock-based tests for injection, recording, streaming |

## Config Changes

```python
PROXY_PORT = int(os.environ.get("BASELAYER_PROXY_PORT", "5100"))
PROXY_HOST = os.environ.get("BASELAYER_PROXY_HOST", "127.0.0.1")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PROXY_BRIEF_MODE = os.environ.get("BASELAYER_PROXY_MODE", "identity")
```

Add to SCOPE_SOURCE_MAPPING: `"proxy": "personal"`

## CLI Addition

```
baselayer proxy [--port 5100] [--host 127.0.0.1] [--mode identity|full]
```

## Message Flow

1. Client sends POST /v1/chat/completions to localhost:5100
2. Extract/create session ID
3. Record new user message in SQLite
4. Load identity brief (identity-only or full)
5. Inject brief into system message
6. Forward to OpenRouter with API key
7. Stream response back to client, buffer for recording
8. Record complete assistant message
9. Update conversation metadata

## Integration

Reuses existing code:
- `assemble_brief.get_three_layer_identity()` for identity-only mode
- `assemble_brief.assemble_brief()` for full mode
- `init_database.init_database()` for first-run setup
- Same SQLite schema — `baselayer extract` picks up proxy conversations automatically

## Build Order

1. Config additions (5 min)
2. Session manager (30 min)
3. Core proxy — non-streaming first (60 min)
4. Streaming support (30 min)
5. CLI integration (15 min)
6. Tests (30 min)
7. Documentation (15 min)
