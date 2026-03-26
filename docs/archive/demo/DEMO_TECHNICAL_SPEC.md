# Talk to History — Technical Specification

## Overview

Interactive web demo where users chat with historical figures, seeing side-by-side responses from a vanilla LLM vs a Base Layer-injected LLM. Identity layers are visible, proving "transparency is the architecture."

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Browser (SPA)                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Figure   │  │ Identity Tab │  │ Side-by-Side  │  │
│  │ Selector  │  │  Viewer      │  │ Chat Panels   │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Server (demo/app.py)             │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  /figures │  │ /chat        │  │ Rate Limiter  │  │
│  │  /identity│  │ (parallel    │  │ (30/hr/IP)    │  │
│  │  /stats   │  │  API calls)  │  │               │  │
│  └──────────┘  └──────┬───────┘  └───────────────┘  │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌──────────────────┐  ┌──────────────────────────────┐
│  Anthropic API   │  │  Per-Figure Data              │
│  (Haiku/Sonnet)  │  │  ┌────────────┐              │
│                  │  │  │ memory.db  │ SQLite        │
│  2 calls/message │  │  │ vectors/   │ ChromaDB      │
│  ~$0.02/turn     │  │  │ layers/    │ Markdown      │
└──────────────────┘  │  │ metadata   │ JSON          │
                      │  └────────────┘              │
                      └──────────────────────────────┘
```

## Integration Points with Base Layer

### Functions Reused Directly

| Function | File | Usage in Demo |
|---|---|---|
| `get_three_layer_identity()` | `assemble_brief.py:664` | Reads ANCHORS + CORE + PREDICTIONS from layer files, wraps in XML tags |
| `_read_injectable_block(file_path)` | `assemble_brief.py:649` | Reads individual layer markdown files (strips metadata headers) |
| `assemble_brief(conn, msg, embed, chroma, identity)` | `assemble_brief.py:1225` | Full brief assembly with themes + episodes (optional — may be overkill for demo) |
| `call_claude(system, messages, api_key)` | `assemble_brief.py:1415` | API call to Claude. Currently hardcoded to `claude-sonnet-4-5-20250929`. Demo should use Haiku for cost. |
| `get_db(db_path)` | `config.py:48` | SQLite connection with row_factory |

### Config Values Used

| Constant | Value | Usage |
|---|---|---|
| `MEMORY_SYSTEM_ROOT` | env var | Points to per-figure data directory |
| `DATABASE_FILE` | `{ROOT}/data/database/memory.db` | Per-figure fact database |
| `VECTORS_DIR` | `{ROOT}/data/vectors/` | Per-figure ChromaDB embeddings |
| `ANCHORS_LAYER_FILE` | `{ROOT}/data/identity_layers/anchors_v4.md` | Layer files |
| `CORE_LAYER_FILE` | `{ROOT}/data/identity_layers/core_v4.md` | Layer files |
| `PREDICTIONS_LAYER_FILE` | `{ROOT}/data/identity_layers/predictions_v4.md` | Layer files |
| `BRIEF_INSTRUCTION` | String constant | Preamble for identity brief injection |

### Key Decision: Full Brief vs Identity-Only

**Option A: Full brief** (`assemble_brief()`) — Identity + Themes + Episodes. Requires ChromaDB + embedding model loaded per figure. Heavier, slower, more impressive.

**Option B: Identity-only** — Just read the three layer files and inject as system prompt. No DB/vector lookups needed per message. Lighter, faster, sufficient for demo.

**Recommendation: Option B for v1.** The identity layers are the showcase. Theme/episode retrieval adds complexity without visible demo value (the user has no prior conversation history with the figure). The demo can upgrade to full brief later if needed.

### Adaptation Required

The `BRIEF_INSTRUCTION` constant is written for a personal memory system ("You know this person"). For the demo, this needs adaptation per figure:

```
DEMO_BRIEF_INSTRUCTION = """You are {figure_name} ({birth_year}–{death_year}).
Answer all questions as {figure_name} would, in first person.

The following is a behavioral model of {figure_name} derived from their writings
using Base Layer's identity extraction pipeline. Use this context to inform your
responses — it captures how {figure_name} thinks, what they value, and how they
behave. Reference it naturally, do not recite it."""
```

The vanilla side gets a minimal system prompt:
```
VANILLA_PROMPT = """You are {figure_name} ({birth_year}–{death_year}).
Answer all questions as {figure_name} would, in first person."""
```

The delta between these two is the entire point of the demo.

## API Contract

### `GET /api/figures`

Returns list of available historical figures.

```json
{
  "figures": [
    {
      "slug": "franklin",
      "name": "Benjamin Franklin",
      "birth_year": 1706,
      "death_year": 1790,
      "source_text": "The Autobiography of Benjamin Franklin",
      "source_url": "https://www.gutenberg.org/ebooks/148",
      "tagline": "Founding Father, inventor, diplomat, printer",
      "fact_count": null,
      "tier_distribution": null
    }
  ]
}
```

### `GET /api/figures/{slug}/identity`

Returns identity layers as markdown for display in tabs.

```json
{
  "slug": "franklin",
  "name": "Benjamin Franklin",
  "layers": {
    "anchors": "## ANCHORS\n\n**SELF-IMPROVEMENT**\n...",
    "core": "## CORE\n\n**COMMUNICATION APPROACH**\n...",
    "predictions": "## PREDICTIONS\n\n**1. FRUGALITY-VANITY TENSION**\n..."
  },
  "assembled_brief": "<epistemic_anchors>...</epistemic_anchors>\n<individual_overview>...",
  "token_count": 5200
}
```

### `POST /api/figures/{slug}/chat`

Sends a message, returns both vanilla and Base Layer responses.

**Request:**
```json
{
  "message": "What do you think about modern education?",
  "session_id": "abc123",
  "conversation_history": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Good day..."}
  ]
}
```

**Response:**
```json
{
  "vanilla": {
    "response": "Well, I believe education is...",
    "model": "claude-haiku-4-5-20251001",
    "tokens_used": 320
  },
  "baselayer": {
    "response": "Education — now there's a subject...",
    "model": "claude-haiku-4-5-20251001",
    "tokens_used": 480,
    "identity_tokens": 5200
  }
}
```

### `GET /api/figures/{slug}/stats`

Returns pipeline metadata for the selected figure.

```json
{
  "slug": "franklin",
  "fact_count": 342,
  "active_facts": 310,
  "tier_distribution": {
    "identity": 180,
    "situational": 85,
    "context": 45
  },
  "layer_word_counts": {
    "anchors": 1800,
    "core": 600,
    "predictions": 2200
  },
  "source_conversations": 1,
  "source_messages": 48
}
```

## Per-Figure Data Structure

Each figure gets an isolated directory that mirrors Base Layer's standard layout:

```
demo/data/figures/{slug}/
├── data/
│   ├── database/
│   │   └── memory.db              # SQLite with extracted facts
│   ├── vectors/
│   │   ├── chroma.sqlite3         # ChromaDB persistence
│   │   └── ...
│   └── identity_layers/
│       ├── anchors_v1.md          # Generated by pipeline
│       ├── core_v1.md
│       └── predictions_v1.md
├── source/
│   └── autobiography.txt          # Downloaded from Gutenberg
└── metadata.json                  # Figure info + vanilla prompt
```

### metadata.json Schema

```json
{
  "slug": "franklin",
  "name": "Benjamin Franklin",
  "birth_year": 1706,
  "death_year": 1790,
  "source_text": "The Autobiography of Benjamin Franklin",
  "source_url": "https://www.gutenberg.org/ebooks/148",
  "tagline": "Founding Father, inventor, diplomat, printer",
  "vanilla_prompt": "You are Benjamin Franklin (1706–1790). Answer all questions as Franklin would, in first person. You were a Founding Father of the United States, a printer, scientist, inventor, diplomat, and author.",
  "baselayer_preamble": "You are Benjamin Franklin (1706–1790). Answer all questions as Franklin would, in first person.\n\nThe following is a behavioral model derived from your autobiography using Base Layer's identity extraction pipeline. It captures how you think, what you value, and how you behave.",
  "pipeline_run_date": null,
  "pipeline_cost_usd": null
}
```

## Rate Limiting

- **30 messages/hour per IP** — prevents abuse, keeps API costs manageable
- Implementation: In-memory dict of `{ip: [timestamp, ...]}` with sliding window
- No persistence needed — resets on server restart (acceptable for demo)
- Returns `429 Too Many Requests` with `Retry-After` header when exceeded

## Session Management

- **In-memory conversation history** per session (no persistence)
- Session ID generated client-side (UUID), passed with each request
- Sessions expire after 30 minutes of inactivity
- Max 50 messages per session (safety cap)
- Separate conversation histories for vanilla and BL panels

## LLM Model Choice

| Use | Model | Cost per turn |
|---|---|---|
| Demo chat (both panels) | `claude-haiku-4-5-20251001` | ~$0.003 (2 calls = ~$0.006) |
| Pipeline extraction (prep) | `claude-haiku-4-5-20251001` | ~$1–2 per figure |
| Pipeline authoring (prep) | `claude-sonnet-4-20250514` | ~$0.10 per figure |

**Why Haiku for chat:** Cost efficiency. At ~$0.003/turn × 2 panels = ~$0.006/message. Budget of $50/month supports ~8,300 messages. Haiku's quality is sufficient for the demo since the identity layers do most of the work.

**Upgrade path:** Could offer Sonnet as premium option later. The quality delta between Haiku-with-layers vs Haiku-without-layers will still be dramatic.

## CORS Configuration

```python
origins = [
    "http://localhost:3000",     # Local dev
    "http://localhost:8000",     # FastAPI dev
    "https://talktohistory.com", # Production (TBD)
]
```

## Error Handling

| Scenario | Response |
|---|---|
| Figure not found | 404 with `{"error": "Figure not found: {slug}"}` |
| Rate limit exceeded | 429 with `{"error": "Rate limit exceeded", "retry_after": 120}` |
| API key missing | 500 with `{"error": "Server configuration error"}` (no key leak) |
| Anthropic API error | 502 with `{"error": "AI service temporarily unavailable"}` |
| Invalid request body | 422 (FastAPI default validation) |

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...        # Required for chat endpoints
DEMO_RATE_LIMIT=30                  # Messages per hour per IP (default: 30)
DEMO_SESSION_TTL=1800               # Session timeout in seconds (default: 1800)
DEMO_MODEL=claude-haiku-4-5-20251001  # Chat model (default: Haiku)
DEMO_DATA_DIR=./data/figures        # Figure data root
```

## File Manifest

| File | Purpose | Lines (est.) |
|---|---|---|
| `demo/app.py` | FastAPI server — all endpoints, rate limiting, session management, API calls | ~350 |
| `demo/static/index.html` | Single-page app — figure selector, tabs, chat panels | ~120 |
| `demo/static/style.css` | Dark mode, monospace layers, clean chat UI | ~250 |
| `demo/static/app.js` | Client logic — API calls, DOM manipulation, state management | ~300 |
| `demo/figures.json` | Figure registry — metadata, prompts, taglines | ~60 |
| `demo/README.md` | Setup, deployment, and data prep instructions | ~100 |
| `demo/requirements.txt` | Python dependencies for demo server | ~10 |

**Total new code:** ~1,190 lines across 7 files.

## Dependencies (demo-specific)

```
fastapi>=0.104.0
uvicorn>=0.24.0
anthropic>=0.39.0
python-multipart>=0.0.6
```

Note: `sentence-transformers` and `chromadb` are NOT required for the demo if using identity-only mode (Option B). They're only needed for full brief assembly.

## Deployment Options

### Option 1: Railway (Recommended)

```bash
# railway.json
{
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "uvicorn demo.app:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

Cost: ~$5/month (hobby tier)

### Option 2: Fly.io

```toml
# fly.toml
[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
```

### Option 3: Single-machine (dev/demo)

```bash
cd demo
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Cost Model

| Component | Monthly Cost |
|---|---|
| Hosting (Railway/Fly) | ~$5 |
| API (2,500 conversations × 3 turns × $0.006) | ~$45 |
| Domain (optional) | ~$1 |
| **Total** | **~$51/month** |

## Security Considerations

- API key stored server-side only, never exposed to client
- CORS restricted to known origins
- Rate limiting per IP
- No user data persistence (ephemeral sessions)
- Input validation on message length (max 2,000 chars)
- No authentication required (public demo)
- Content moderation: rely on Claude's built-in safety
