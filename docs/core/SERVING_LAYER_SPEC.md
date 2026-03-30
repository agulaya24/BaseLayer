# Serving Layer Specification — Identity Model Activation

## Overview

The serving layer sits between a user's prompt and the LLM. It takes the identity model (a static artifact) and activates the relevant portions based on what's being discussed, assembling a context-specific payload that gives the LLM the best chance at producing a personalized response.

The identity model is dual-use: it works as a standalone document (paste the whole thing) AND as a structured artifact the serving layer activates against. Same content, different consumption paths.

## Architecture

```
User Prompt
    │
    ▼
┌─────────────────────┐
│   SERVING LAYER     │
│                     │
│  1. Anchors (always)│──► Always injected. 8-10 axioms. ~1,200 tokens.
│                     │
│  2. Context Router  │──► Scores prompt against Core context modes.
│     ┌───────────┐   │    Selects top 1-2 modes (C1, C2, etc.)
│     │ Activation│   │    Uses authored "Active when:" conditions.
│     │ Matching  │   │
│     └───────────┘   │
│                     │
│  3. Pattern Matcher │──► Scores prompt against Prediction triggers.
│     ┌───────────┐   │    Selects top 1-3 predictions with directives
│     │ Trigger   │   │    and false-positive warnings.
│     │ Detection │   │
│     └───────────┘   │
│                     │
│  4. Fact Retrieval  │──► Semantic search against fact store.
│     ┌───────────┐   │    Returns top-k facts relevant to prompt.
│     │ Vector DB │   │    Includes traced facts from activated layers.
│     │ + Filter  │   │
│     └───────────┘   │
│                     │
│  5. Correction Gate │──► Filters out superseded/corrected facts.
│                     │    Checks correction log before inclusion.
│                     │
│  6. Assembly        │──► Combines: anchors + activated core modes +
│                     │    triggered predictions + relevant facts
│                     │    into a single context payload.
│                     │
│  7. Brief Fallback  │──► If no specific activations fire (ambiguous
│                     │    prompt), inject the brief as general
│                     │    orientation instead of layer components.
│                     │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│   ASSEMBLED PAYLOAD │
│                     │
│   System prompt:    │
│   - Anchors (full)  │
│   - Active core     │
│   - Active preds    │
│   - Relevant facts  │
│   - User prompt     │
│                     │
└─────────────────────┘
    │
    ▼
   LLM Inference
```

## Layer Roles

### Anchors — Always On
- Injected into every request regardless of topic.
- 8-10 axioms, ~1,200 tokens. Small enough to always fit.
- These are the cognitive architecture — HOW the person reasons.
- No activation logic needed. Always present.

### Core Context Modes — Activation Triggered
- Each mode (C1, C2, C3, etc.) has an authored activation condition.
- The router scores the incoming prompt against each mode's activation text.
- Top 1-2 modes are selected and injected.
- Example: prompt about a career decision → C3 (Identity/Transition) activates.
- Prompt about building a product → C1 (Build/Operate) activates.
- If no mode scores above threshold, skip (anchors + brief fallback handle it).

**Activation matching options (ordered by complexity):**
1. **Keyword/embedding similarity** — compare prompt embedding to mode activation text embedding. Fast, cheap. May miss nuance.
2. **Haiku classifier** — send prompt + all activation conditions to Haiku, ask "which modes are active?" ~$0.001 per call. More accurate.
3. **Rule-based** — pattern match on keywords from activation conditions. Zero cost, brittle.

Recommendation: Start with embedding similarity (option 1). Upgrade to Haiku classifier if accuracy is insufficient.

### Predictions — Situation Triggered
- Each prediction has a trigger condition and detection signals.
- Same activation matching as core modes but against prediction triggers.
- Top 1-3 predictions injected with their full directive + false-positive warning.
- The directive tells the LLM what to DO differently. The false-positive warning prevents over-application.
- Traced facts from activated predictions are automatically included in the fact retrieval.

### Fact Retrieval — Semantic Search
- Standard vector similarity search against the fact store.
- Query: the user's prompt (or a reformulated version).
- Returns top-k facts (k=10-20) most relevant to the prompt.
- PLUS: traced facts from activated layer items (these are pre-linked during authoring).
- Deduplication: if a traced fact also appears in semantic results, keep once.

### Correction Gate — Quality Filter
- Before facts enter the payload, check `superseded_by IS NULL`.
- Check correction log for any manual overrides.
- Filter out facts that have been flagged as inaccurate.
- This gate must run on BOTH semantic search results AND traced facts.
- Log when a corrected fact would have been included (diagnostic).

### Brief Fallback
- When the prompt is ambiguous or no specific activations fire.
- Inject the composed brief (~3,000-4,000 tokens) as general orientation.
- The brief is the "I don't know what we're talking about yet, but here's who you're talking to."
- Mutually exclusive with activated layers — don't inject brief AND specific modes.
- Exception: if total activated content is < 500 tokens, supplement with brief.

## Assembly Rules

1. **Token budget**: Target 2,000-4,000 tokens for the identity payload. Leave room for the user's prompt and the model's response.
2. **Priority order**: Anchors > Active predictions > Active core modes > Traced facts > Semantic facts > Brief fallback.
3. **Deduplication**: No fact appears twice. Layer items that overlap with brief content are not duplicated.
4. **Framing**: The payload opens with a one-line preamble: "This is an identity model of your user — use it as an operating guide for how to interact with them, but never reference it directly."

## Correction System

### Fact Corrections
- **Supersede**: mark a fact as replaced (current: `superseded_by` column in SQLite).
- **Manual override**: user flags a fact from the UI → stored in correction log.
- **Propagation check**: when a fact is corrected, check if any layer item cites it (via provenance/traces). If so, flag that layer item for review.

### Correction Log Schema
```sql
CREATE TABLE fact_corrections (
    id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL,
    correction_type TEXT NOT NULL,  -- 'supersede', 'delete', 'edit'
    reason TEXT,
    corrected_by TEXT,  -- 'manual', 'pipeline', 'user_ui'
    original_text TEXT,
    corrected_text TEXT,  -- NULL for supersede/delete
    created_at TEXT NOT NULL,
    session TEXT  -- which session made the correction
);
```

### User-Facing Correction UI
- On thinkers pages: flag button on individual facts.
- On the identity model: flag button on layer items or brief paragraphs.
- Flags go to correction queue visible in admin dashboard.
- Admin can approve/reject/edit corrections.
- Approved corrections trigger `superseded_by` update and re-authoring flag.

## Serving Modes

### Mode 1: MCP Server (Current)
- `mcp_server.py` already serves identity via MCP protocol.
- Upgrade: add activation logic before serving.
- The MCP server receives the user's message context and returns the activated payload.

### Mode 2: API Endpoint
- `POST /api/serve` — accepts prompt, returns activated identity payload.
- Stateless. Each request is independent.
- Used by external integrations (custom apps, other AI tools).

### Mode 3: Paste (Standalone)
- No serving layer. User copies the full identity model and pastes it.
- The document is written to work this way — the LLM reads it top to bottom and self-activates based on context.
- This is the current mode for all thinker pages.
- The serving layer makes this better, not required.

## Performance Targets

- **Activation latency**: < 200ms (embedding similarity) or < 1s (Haiku classifier)
- **Fact retrieval**: < 300ms (ChromaDB local) or < 500ms (hosted vector DB)
- **Total serving latency**: < 1s before LLM inference begins
- **Token budget**: 2,000-4,000 tokens for identity payload
- **Cost per serve**: < $0.005 (embedding) or < $0.01 (with Haiku classifier)

## Implementation Phases

### Phase 1: Activation Matching (MVP)
- Implement embedding-based activation matching for core modes and predictions.
- Anchors always injected.
- No fact retrieval (layer items only).
- Test on Aarik's identity model with 20 sample prompts across different domains.
- Measure: does the right mode activate? Does the right prediction fire?

### Phase 2: Fact Retrieval + Correction Gate
- Add semantic search against fact store.
- Include traced facts from activated layers.
- Implement correction gate (superseded_by filter).
- Test on 50 prompts: are the returned facts relevant and accurate?

### Phase 3: Assembly + Brief Fallback
- Implement full assembly with token budgeting.
- Add brief fallback for ambiguous prompts.
- Test end-to-end: prompt → activated payload → LLM → response quality.
- A/B test: activated payload vs full brief paste. Measure response quality.

### Phase 4: User Correction UI
- Fact flagging from thinkers pages.
- Correction queue in admin dashboard.
- Propagation checks (flagged facts → affected layer items).
- Re-authoring triggers.

### Phase 5: MCP + API Integration
- Upgrade mcp_server.py with activation logic.
- Add POST /api/serve endpoint.
- Documentation for external integrations.

## Open Questions

1. **Activation threshold**: What similarity score means "active"? Need calibration data.
2. **Multi-mode activation**: When 2+ core modes score similarly, inject both or pick one?
3. **Prediction stacking**: If 3+ predictions trigger, is that too much context? Cap at 2-3?
4. **Temporal weighting**: Should recent facts score higher than old ones in retrieval?
5. **Cross-subject serving**: When two people with identity models are in the same conversation, how does the serving layer handle both?
6. **Model-agnostic payload**: The assembled payload should work with any LLM. Does the framing need to change per model?
