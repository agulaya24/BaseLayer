# Demo Implementation Tasks

Ordered task list with dependencies. Each task produces a testable artifact.

## Phase 0: Data Preparation (Before Any Code)

### T0.1 — Download Franklin source text
- Download from Gutenberg: `https://www.gutenberg.org/cache/epub/148/pg148.txt`
- Strip Gutenberg header/footer
- Split into chapters if needed (see FIGURE_PREP_GUIDE.md)
- **Output:** `demo/data/figures/franklin/source/autobiography_clean.txt`
- **Blocked by:** Nothing
- **Test:** File exists, >100KB, clean text

### T0.2 — Run pipeline on Franklin
- `MEMORY_SYSTEM_ROOT=demo/data/figures/franklin baselayer init`
- Import, extract, embed, score, classify, tier, author
- Follow checkpoint protocol at each stage
- **Output:** `demo/data/figures/franklin/data/identity_layers/{anchors,core,predictions}_v1.md`
- **Blocked by:** T0.1
- **Test:** Three layer files exist, each >500 words
- **Cost:** ~$3-5

### T0.3 — Review Franklin layers
- Read each layer file
- Validate against review checklist (FIGURE_PREP_GUIDE.md)
- Re-author if quality is insufficient
- **Output:** Approved layer files
- **Blocked by:** T0.2
- **Test:** Manual review passes checklist

### T0.4 — Create Franklin metadata.json
- Write metadata file with figure info, vanilla prompt, BL preamble
- **Output:** `demo/data/figures/franklin/metadata.json`
- **Blocked by:** T0.3
- **Test:** Valid JSON, all required fields present

---

## Phase 1: Backend (demo/app.py + demo/requirements.txt)

Can be parallelized with Phase 2 if API contracts are agreed upon (see DEMO_TECHNICAL_SPEC.md).

### T1.1 — Scaffold FastAPI app
- Create `demo/app.py` with FastAPI instance, CORS middleware, static file serving
- Create `demo/requirements.txt`
- **Output:** Server starts, serves static files, returns 200 on health check
- **Blocked by:** Nothing
- **Test:** `uvicorn demo.app:app` starts without error, `curl localhost:8000/health` returns 200

### T1.2 — Implement figure registry
- Load `figures.json` at startup
- Scan `demo/data/figures/` for available figure directories
- `GET /api/figures` endpoint
- **Output:** Endpoint returns figure list
- **Blocked by:** T1.1, T0.4 (for at least one figure's metadata)
- **Test:** `curl localhost:8000/api/figures` returns JSON with Franklin

### T1.3 — Implement identity layer serving
- `GET /api/figures/{slug}/identity` endpoint
- Read layer markdown files from figure's data directory
- Return individual layers (for tabs) + assembled brief (for system prompt)
- **Output:** Endpoint returns layer markdown
- **Blocked by:** T1.2, T0.3 (needs layer files)
- **Test:** `curl localhost:8000/api/figures/franklin/identity` returns three layers

### T1.4 — Implement chat endpoint
- `POST /api/figures/{slug}/chat` endpoint
- Build vanilla system prompt from metadata
- Build BL system prompt from identity layers + preamble
- Make two parallel Anthropic API calls
- Return both responses
- **Output:** Endpoint returns vanilla + BL responses
- **Blocked by:** T1.3
- **Test:** POST with message returns two different responses
- **Requires:** `ANTHROPIC_API_KEY` in environment

### T1.5 — Implement rate limiting
- In-memory sliding window rate limiter (30/hr/IP)
- Apply to `/api/figures/{slug}/chat` endpoint only
- Return 429 with retry_after when exceeded
- **Output:** Rate limiting works
- **Blocked by:** T1.4
- **Test:** Send 31 requests rapidly, 31st returns 429

### T1.6 — Implement session management
- In-memory session store with conversation history
- Session ID from client, 30-minute TTL, 50-message cap
- Separate vanilla/BL history per session
- **Output:** Multi-turn conversations maintain context
- **Blocked by:** T1.4
- **Test:** Second message in session gets contextual response

### T1.7 — Implement stats endpoint
- `GET /api/figures/{slug}/stats` endpoint
- Read fact count, tier distribution from SQLite
- Read layer word counts from files
- **Output:** Stats endpoint returns metadata
- **Blocked by:** T1.2
- **Test:** `curl localhost:8000/api/figures/franklin/stats` returns JSON with counts

---

## Phase 2: Frontend (demo/static/)

Can be parallelized with Phase 1 backend.

### T2.1 — HTML structure
- Create `demo/static/index.html`
- Figure selector (dropdown or cards)
- Identity layer tabs (ANCHORS / CORE / PREDICTIONS)
- Side-by-side chat panels (left: vanilla, right: BL)
- Single input field + send button
- Footer with Base Layer links
- **Output:** Static HTML renders correctly in browser
- **Blocked by:** Nothing
- **Test:** Open in browser, all sections visible

### T2.2 — CSS styling
- Create `demo/static/style.css`
- Dark mode (dark background, light text)
- Monospace for identity layer content
- Clean sans-serif for chat
- Responsive layout (side-by-side on desktop, stacked on mobile)
- Chat message bubbles (user vs assistant, vanilla vs BL)
- Loading states (spinner during API calls)
- **Output:** Looks good in browser
- **Blocked by:** T2.1
- **Test:** Visual inspection on desktop and mobile viewport

### T2.3 — JavaScript: figure loading
- Create `demo/static/app.js`
- Fetch `/api/figures` on page load
- Populate figure selector
- On figure select: fetch `/api/figures/{slug}/identity`, display in tabs
- **Output:** Figure selection loads identity layers
- **Blocked by:** T2.1, T1.2, T1.3
- **Test:** Select Franklin, see identity layers in tabs

### T2.4 — JavaScript: chat functionality
- Send message to `/api/figures/{slug}/chat`
- Display both responses in side-by-side panels
- Maintain conversation history client-side
- Handle loading state (disable input, show spinner)
- Handle errors (rate limit, server error)
- **Output:** Full chat works end-to-end
- **Blocked by:** T2.3, T1.4
- **Test:** Type question, see two responses appear side-by-side

### T2.5 — JavaScript: UX polish
- Enter key sends message
- Auto-scroll chat panels
- Markdown rendering in responses (basic: bold, italic, lists)
- Clear conversation button
- Message count / rate limit indicator
- **Output:** Polished UX
- **Blocked by:** T2.4
- **Test:** User flow feels smooth

---

## Phase 3: Second Figure + Polish

### T3.1 — Download and prep Douglass
- Same process as T0.1–T0.4 for Douglass
- **Output:** `demo/data/figures/douglass/` with layers + metadata
- **Blocked by:** Working pipeline (T0.2 validates this)
- **Cost:** ~$1-3

### T3.2 — Validate generalization
- Load both Franklin and Douglass in the demo
- Run test questions from FIGURE_PREP_GUIDE.md
- Verify side-by-side quality delta for both figures
- **Output:** Both figures work, quality is demonstrable
- **Blocked by:** T3.1, T2.4

### T3.3 — Error handling polish
- Graceful handling of all error states
- Friendly error messages in UI
- Fallback if API is down
- **Blocked by:** T2.4

### T3.4 — Mobile responsiveness
- Test on actual mobile device / responsive mode
- Fix any layout issues
- **Blocked by:** T2.5

---

## Phase 4: Deploy

### T4.1 — Create deployment config
- Railway config or Fly.io config or Dockerfile
- Environment variable setup
- **Blocked by:** T2.5

### T4.2 — Deploy and test
- Push to hosting provider
- Test all endpoints on production URL
- Verify rate limiting works in production
- **Blocked by:** T4.1

### T4.3 — Record demo videos
- Screen recordings of side-by-side conversations
- 2-3 compelling questions per figure
- Short (30-60 sec) clips for social sharing
- **Blocked by:** T4.2

---

## Parallel Execution Strategy

### If splitting across two Claude Code instances:

**Instance A (Backend):** T1.1 → T1.2 → T1.3 → T1.4 → T1.5 → T1.6 → T1.7
- Files: `demo/app.py`, `demo/requirements.txt`

**Instance B (Frontend):** T2.1 → T2.2 → T2.3 → T2.4 → T2.5
- Files: `demo/static/index.html`, `demo/static/style.css`, `demo/static/app.js`

**Shared files (write before parallel work begins):**
- `demo/figures.json` — write first, both instances reference it
- `demo/data/figures/*/metadata.json` — write first

**Zero overlap:** No file is touched by both instances.

### Dependency graph (simplified):

```
T0.1 → T0.2 → T0.3 → T0.4
                        │
                ┌───────┴───────┐
                ▼               ▼
           T1.1→T1.2       T2.1→T2.2
                │               │
           T1.3→T1.4       T2.3→T2.4→T2.5
                │               │
           T1.5→T1.6       ────┘
                │
           T1.7─┘
                │
           T3.1→T3.2→T3.3→T3.4
                │
           T4.1→T4.2→T4.3
```

## Time Estimates

| Phase | Tasks | Estimated Time |
|---|---|---|
| Phase 0: Data Prep | T0.1–T0.4 | ~1-2 hours (mostly pipeline) |
| Phase 1: Backend | T1.1–T1.7 | ~1 session |
| Phase 2: Frontend | T2.1–T2.5 | ~1 session |
| Phase 3: Second Figure + Polish | T3.1–T3.4 | ~1 hour + 1 session |
| Phase 4: Deploy | T4.1–T4.3 | ~1 session |
| **Total** | | ~4-5 sessions |

Phase 1 and Phase 2 can run in parallel = ~3-4 sessions.
