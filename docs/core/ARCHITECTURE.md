# System Architecture
## Base Layer — Behavioral Compression for AI Identity
**Updated 2026-03-09 (Session 82)**

---

## The Problem

Every conversation with an AI starts from zero. Three years of ChatGPT conversations — 1,892 of them (primary test user) — and none of that context carries forward. You repeat yourself. The AI re-explains things you already know. There's no continuity, no relationship, no growth.

Bigger context windows don't solve this. Dumping 40,000 messages into a prompt isn't memory — it's a filing cabinet with no librarian.

## The Goal

Build a **living model of the user** that evolves over time. Not searchable archives. Not RAG retrieval. Something closer to how a human friend remembers you — a compressed, always-available understanding that deepens with every interaction.

The AI should feel like it **knows** you, not like it was **briefed** about you.

**North star:** Every agentic workflow, AI interaction, and form of personalization is hollow if it doesn't understand who the human is behind the screen. Base Layer exists because AI should know you.

## Design Philosophy

**Compression-first, not storage-first.** The architecture compresses raw text into behavioral understanding:

> *Note: The original design drew heavily from brain-inspired memory metaphors (hippocampus/neocortex, sleep consolidation, surprise-driven encoding). Session 79 pipeline ablation study (14 conditions, [results](../eval/ablation/)) proved that the intermediate processing steps inspired by these metaphors — scoring, classification, tiering, contradiction detection — were ceremonial. What remains load-bearing is the compression itself: raw text → structured facts → three-layer identity → unified brief. The brain metaphors were useful scaffolding for building the system but the system outgrew them.*

- ~~**Hippocampus** (fast, episodic) --> recent conversations, specific memories~~
- **Neocortex** (slow, consolidated) --> stable identity, learned patterns
- **Sleep consolidation** (periodic compression) --> episodes compress into patterns over time
- **Surprise-driven encoding** --> novel information gets prioritized; routine gets filtered

**Core principles:**

1. **Local-first.** All data stays on your machine. Extraction uses Anthropic Haiku API by default; Ollama/local models available as optional alternative. Only reasoning goes to the cloud (Claude API), and only with an assembled brief (the compressed identity document that teaches an AI how someone thinks and communicates) — never raw data.

2. **Surprise-based writes.** Inspired by Google Titans: only store what's novel relative to what you already know. Routine information gets filtered. This keeps the memory system from drowning in noise.

3. **Always-on identity.** A compressed behavioral model is present in every single conversation. Not biography — behavioral predictions. The AI doesn't just know facts about you; it knows how you operate, what triggers you, and how to interact with you effectively. Three-layer architecture (D-043): epistemic axioms + individual overview + behavioral predictions, each authored independently. Stored as injectable markdown files, loaded by `assemble_brief.py` at runtime.

4. **Inherent incompleteness.** The system will never have a complete or fully accurate picture of the person it models. This operates at two levels. First, *information gaps*: the system only knows what came up in conversation, and even that is filtered through misattribution, intent confusion, and the difference between curiosity and identity. The model is always partial and potentially wrong. Second, and more fundamentally, *experiential depth*: there is an emotional dimension to human life that cannot be captured through conversation at all. What it feels like when your cat is ill, what it means to love your wife, the weight behind a loss or a triumph — these are real and central to who a person is, but no data representation can hold them. The system must operate with knowledge of both constraints. Every layer — confidence scores, correction propagation, active probing, human-in-the-loop review — exists in acknowledgment of this reality. The goal is useful understanding, not total understanding. Confidence is warranted; certainty never is. (See `DESIGN_PRINCIPLES.md` for the full treatment.)

5. **Scoped memory.** Facts are tagged by interaction mode — personal, project, professional (D-044). Personal-scope facts feed identity blocks. Project-scope facts feed project briefs (e.g., CLAUDE.md). Epistemic anchors are validated by cross-scope recurrence. This prevents meta-contamination (project language bleeding into personal identity) and enables multi-user deployments where each user's data is isolated.

---

## System Overview

### Simplified Pipeline (4 Steps)

Pipeline ablation (Session 79) tested 14 conditions on Benjamin Franklin (autobiography, [live example](https://base-layer.ai/examples/franklin)) (~$16) and proved that 10 of the original 14 steps were ceremonial. The simplified 4-step pipeline scores higher (87/100 vs 83/100 for the full pipeline). The 3-layer architecture is load-bearing; the intermediate processing steps are not.

```
                    THE MEMORY SYSTEM (BASE LAYER)
 +--------------------------------------------------------------+
 |                                                                |
 |   STEP 1: IMPORT                                               |
 |   +----------------------------------------------------------+ |
 |   | Multi-source importer (ChatGPT, Claude, journals, text)  | |
 |   | → SQLite (conversations + messages)                       | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 2: EXTRACT             v                                |
 |   +----------------------------------------------------------+ |
 |   | Haiku API — 47 constrained predicates                     | |
 |   | Text → {subject, predicate, object, qualifier} triples    | |
 |   | AUDN (Add, Update, Delete, Noop) fact lifecycle            | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 3: AUTHOR              v                                |
 |   +----------------------------------------------------------+ |
 |   | Sonnet — Three-layer identity generation (D-043)          | |
 |   | ANCHORS | Epistemic axioms                                | |
 |   | CORE    | Communication & operating guide                 | |
 |   | PREDICT | Situation → pattern → directive                 | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 4: COMPOSE             v                                |
 |   +----------------------------------------------------------+ |
 |   | Opus — Compress 3 layers → unified brief (~2,500 tokens)  | |
 |   | Served via MCP (Model Context Protocol) as always-on      | |
 |   | identity Resource                                          | |
 |   +----------------------------------------------------------+ |
 |                                                                |
 +--------------------------------------------------------------+
                                |
                                v
                   +----------------------------+
                   |   REASONING MODEL          |
                   |   Claude API (stateless)    |
                   |   Receives brief +          |
                   |   user message              |
                   +----------------------------+
```

**One command:** `baselayer run <file>` runs steps 1-4 automatically with cost estimate gate.

---

## The Layers

The original architecture described five layers. After ablation (Session 79), the active pipeline uses Layers 1 (Ground Truth), 3 (Extraction), 4 (Context Projection), and 5 (Reasoning Model). Layers 2 (Semantic Memory) and much of Layer 3's processing (scoring, classification, tiering, contradiction detection, consolidation) proved ceremonial and are preserved in the codebase but no longer part of the default pipeline.

### Layer 1: Ground Truth (COMPLETE)

The raw, unmodified record of everything. Never fed directly to an LLM. Serves as the source of truth that all other layers derive from.

**Technology:** SQLite
**Contents:** 1,892 conversations, 40,997 messages (primary test user, Jan 2023 -- Feb 2026, multi-source)
**Schema:**

| Table | Purpose |
|-------|---------|
| `conversations` | id, title, created_at, updated_at, message_count, source |
| `messages` | id, conversation_id, parent_id, role, content_text, created_at, sequence_order |

**Sources:** ChatGPT export (1,859 conversations), Claude Code sessions (25+), Claude.ai web export (8+)

**Scripts:** `import_conversations.py` (multi-source incremental import — ChatGPT, Claude Code, Claude web parsers), `query.py` (keyword search), `init_database.py` (initialize clean databases for new users)

---

### Layer 2: Semantic Memory (COMPLETE + expanding)

Vector representations of all content, enabling search by meaning rather than keywords. Multiple collections serve different retrieval needs.

**Technology:** ChromaDB + sentence-transformers (`all-MiniLM-L6-v2`, 384 dimensions)

| Collection | Contents | Status |
|-----------|----------|--------|
| `message_embeddings` | 30,061 individual message vectors | COMPLETE |
| `turn_pair_embeddings` | User+assistant pairs as single units (primary retrieval target) | COMPLETE (13,377) |
| `summary_embeddings` | Conversation-level summary vectors | PENDING |
| `fact_embeddings` | Extracted atomic fact vectors | COMPLETE (4,610 active) |

**Why turn-pair embeddings?** (Decision D-007) Individual messages like "yes" or "thanks" carry no meaning and pollute search results. A user question paired with the assistant's answer is a much richer unit of meaning. Turn-pairs become the primary retrieval target; per-message embeddings remain for detailed drill-down.

**Scripts:** `embed.py` (create embeddings), `semantic_search.py` (interactive search)

---

### Layer 3: Memory Control

The mechanical intelligence layer. In the simplified 4-step pipeline, this layer handles fact extraction only (Haiku API with 47 constrained predicates). The original pipeline included scoring, classification, tiering, contradiction detection, and consolidation — all proved ceremonial in ablation testing (Session 79).

**Active in simplified pipeline:** Haiku-based structured fact extraction with AUDN lifecycle.

<details>
<summary>Original Layer 3 detail (archived)</summary>

The full Layer 3 handled fact extraction, classification, scoring, embedding, deduplication, consolidation, and AUDN lifecycle decisions. Multiple models served different roles:

- **Haiku (API, default):** Structured fact extraction with constrained predicates (D-056 Tier 2, Variant D). Produces `{subject, predicate, object, qualifier}` triples with 47 constrained predicates (31 original + 6 S49 + 2 S52 + 8 S55 relationship). Also: fact classification — `fact_type` and `commitment_depth`. 91.2% accuracy on type, 93.8% on depth. Batch API mode available (`batch_extract.py`) for 50% cost reduction.
- **Qwen 2.5 14B (local, via Ollama):** Optional local extraction for users with GPU. No narrative generation (D-030).
- **Sonnet (API):** Knowledge tier reclassification (~$1 for full corpus), three-layer identity generation with D-041/D-046 encoded prompts. Single-domain corpus detection (`_detect_corpus_type()`) selects appropriate PREDICTIONS prompt.
- **Opus (session):** Contradiction judgment (when MiniLM similarity surfaces candidate pairs), identity block review (Collective), architecture decisions. All judgment via Claude Code sessions (D-038, $0 incremental under BYOS).

**Contradiction detection (COMPLETE — multi-pass):** MiniLM similarity filter (threshold 0.50) surfaces candidate pairs from non-context state-facts. Opus judges whether each pair represents a contradiction, enrichment, coexistence, or ambiguity. V3 (Session 28): 1,562 pairs judged across 32 Opus batches, 6 contradictions resolved. V4 (Session 52): 815 pairs judged, 160 enrichment, 655 coexistent, 124 facts consolidated (superseded). Active facts: 4,734 → 4,610. See `docs/reviews/TEMPORAL_PROCESSING_REVIEW.md` (V3).

**Hardware:** RTX 3080 (10GB VRAM), 32GB system RAM

#### 3A. Conversation Summarization

Each conversation gets a 3-5 sentence summary capturing the essence, key decisions, and emotional context. Summaries are embedded for high-level retrieval.

**Script:** `summarize.py`
**Storage:** `conversation_summaries` table in SQLite + `summary_embeddings` collection in ChromaDB
**Status:** 1,380 conversations summarized

#### 3B. Surprise Scoring (Titans-Inspired)

Not every piece of information deserves to be remembered. Inspired by Google Titans' principle that **events violating expectations are more memorable**, we score novelty at two levels:

**Two axes of scoring** (Decision D-009): Pure novelty misses important things — a subtle shift in your trading philosophy is low-novelty by embedding distance but extremely significant. So we score on two dimensions:

1. **Novelty** (embedding distance, fast): is this different from what we already know?
2. **Significance** (data-driven): does this matter for understanding you long-term?

#### Novelty Scoring -- Fast Path (~10ms)

```
novelty = 1.0 - max_cosine_similarity(new_text, existing_memories)
```
- Novelty < 0.3 --> SKIP (clearly redundant)
- Novelty > 0.8 --> STORE (clearly novel)
- Novelty 0.3-0.8 --> send to significance scoring

#### Significance Scoring -- Data-Driven (Decisions D-015, D-016)

Model testing (D-016) proved that **the data matters more than the model**. Feeding recurrence + depth metrics to any model shifted scores significantly, while swapping models barely changed them. The scoring formula is therefore **data-first, LLM-second**:

**Step 1 -- Compute data signals (deterministic, fast):**
1. **Recurrence:** How many conversations mention this topic?
2. **Depth of engagement:** Does the user go deep, or just mention it in passing? Measured by: user turns on the topic per conversation, average message length, follow-up questions asked, whether the topic was the main subject.

**Step 2 -- Apply recurrence floor (deterministic, no LLM needed):**

Not all significance requires depth. Some topics aren't "deep" by any metric — just practical, everyday conversations — but they're so persistent across years that they're clearly part of who you are. Anyone who knows you would mention them. We call these **identity-significant** (vs. **depth-significant**).

| Windowed Recurrence | Time Span | Floor Score | Category |
|------------|-----------|-------------|----------|
| 30+ windows | 1+ year | **7 minimum** | Identity-significant -- auto-elevated |
| 18-29 windows | 1+ year | **6 minimum** | Strong personal theme |
| 10-17 windows | any | No floor | Use formula normally |
| <10 windows | any | No floor | Use formula normally |

Note: "Windowed recurrence" uses 24-hour temporal dedup (Session 55). 20 mentions in one day = 1 recurrence window, not 20. Raw thresholds (50/30) were proportionally reduced to (30/18) to reflect windowed counts.

The floor means highly persistent topics **cannot** score below a certain level, regardless of what the LLM thinks. The data speaks for itself.

**Scoring is fully data-driven (no LLM needed):**

Final significance = max(recurrence_floor, data_computed_score)

Where data_computed_score = 40% embedding novelty + 35% recurrence signal + 25% depth metrics.

**Two flavors of significance** (key insight from model testing):
- **Depth-significant:** Topics the user goes deep on — probing questions, many turns, long messages, lots of follow-ups.
- **Identity-significant:** Not "deep" by metrics, but so persistently present across years of conversation that it's clearly part of who the user is. High recurrence, spans a long time period, but individual conversations may be practical/shallow.

Both are important. The recurrence floor ensures identity-significant topics don't get under-scored just because the user discusses them practically rather than philosophically.

**Momentum:** If turn N in a conversation is surprising, turns N+1, N+2... get a decaying surprise boost. This preserves context around insights — the same way your brain remembers not just the surprising event, but the moments surrounding it.

#### Fact Quality (D-056, Sessions 47-48)

Recurrence scoring depends on keyword extraction from fact text. When facts are written in generic language ("The user is interested in X"), the keywords extracted are generic words that co-occur in hundreds of unrelated conversations, inflating recurrence counts. Session 47 discovered that 57% of 4,106 facts start with "The user is..." — a template artifact from LLM extraction. This caused coffee to score 677 recurrence (correct: 21), "works out" to score 743 (correct: 0 — entirely generic words).

**Root cause:** Extraction prompt produces unconstrained natural language, but the scoring system needs structured, keyword-rich text. These two systems were misaligned.

**Tier 1 (done, Session 47):** Expanded stop words list in `score_facts.py` to cover temporal/positional words. Fixed `sys.stdout` import side effects across 6 scripts. All 4,106 facts re-scored.

**Tier 2 (done, Session 48):** Replaced free-text extraction with structured `{subject, predicate, object, qualifier}` format (Variant D). 31 constrained predicates at launch (now 47 after S49, S52, S55 additions) enforce keyword-rich output. Eval harness tested 4 variants on 16 conversations — Variant D scored 85/100 in Collective review, won 3/4 Opus personas. New DB columns (`predicate`, `object_text`, `qualifier`) store structured fields; `fact_text` reconstructed as `"{subject} {predicate} {object}"` for downstream compatibility. Full re-extraction completed via Batch API (S51).

**Tier 3 (next):** Quality gate between extraction and storage — reject hedging, low lexical density (<0.45), LLM artifacts.

**Tier 4 (planned):** Batch normalize any remaining free-text facts. Entity clustering.

#### 3C. Fact Extraction (AUDN Pipeline)

Every conversation gets processed through a fact extraction pipeline. For each candidate fact, the system decides:

| Action | When | Example |
|--------|------|---------|
| **ADD** | No equivalent exists | "Started learning Rust" |
| **UPDATE** | Refines existing fact | "Likes Python" --> "Likes Python and Rust" |
| **DELETE** | Contradicts existing | "Is vegetarian" contradicted by new info |
| **NOOP** | Already known | "Lives in SF" already stored |

**Extraction models:** Haiku (API, default) or Qwen 2.5 14B (local, optional). D-056 Tier 2: extraction uses structured `{subject, predicate, object, qualifier}` schema with 47 constrained predicates (owns, values, practices, trades, fears, excels_at, relates_to, collaborates_with, etc.) + 30+ aliases. `normalize_predicate()` maps LLM variants to canonical forms. `fact_text` reconstructed for downstream compatibility. Extraction prompts are person-agnostic for multi-user support. Batch API mode available via `batch_extract.py` (D-057) for 50% cost reduction.

**Text chunking (S65):** Long single-message texts (autobiographies, journals, chapters) exceeding `input_char_budget` are auto-chunked on paragraph boundaries with 500-char overlap. Dual-tier cap lookup in `config.py`: message-based AND character-based tiers, whichever yields higher `max_facts` wins. Character tiers: 0-12K→10 facts, 12K-30K→20, 30K-60K→35, 60K+→50. Per-chunk extraction cap: 15 facts. AUDN dedup handles cross-chunk duplication. This enables 2-5x more facts per autobiography subject vs. pre-chunking baseline.

**Re-extraction requirement:** Clearing extraction data requires deleting BOTH SQLite rows (memory_facts + extraction_log) AND the ChromaDB collection (`client.delete_collection('memory_facts')`). Without clearing ChromaDB, old vectors cause AUDN to NOOP on legitimate new facts.

**Haiku classification correction (S65):** The classify step (`classify_facts_haiku.py`) requires recurrence words ("tends to", "always") for behavioral classification, but predicates like `practices` and `avoids` already encode recurrence. `checkpoint.py --fix` applies post-hoc rule-based correction: `practices`/`avoids` facts auto-corrected to `fact_type='behavioral'`. `prioritizes` excluded (correctly positional). PREDICTIONS retrieval (`author_layers.py`) falls back to action-oriented positional facts when behavioral count < 5 (common for treatise/autobiography subjects).

**Entity resolution:** Per-user `entity_map.json` provides name-to-canonical-entity mapping (e.g., "wife" --> "spouse:[name]"). Loaded from the data root, not hardcoded.

**Deduplication:** Vector similarity search finds the top-10 most similar existing facts. The extraction model then decides if the candidate is truly new, a refinement, or redundant.

**Validation guardrails** (Decision D-010): Ollama supports **schema-enforced JSON output** — you pass a JSON schema to the API and it forces the model to conform at the token level. This eliminates most JSON parsing failures at the source. Remaining guardrails:
- Ollama `format` parameter with JSON schema for all structured outputs
- Fallback: up to 2 retries with a simpler prompt if schema enforcement fails
- Low-confidence facts stored at lower confidence (not discarded)
- Periodic review queue for low-confidence items

**Storage:**

```sql
CREATE TABLE memory_facts (
    id TEXT PRIMARY KEY,
    fact_text TEXT NOT NULL,
    category TEXT,            -- 'preference', 'biography', 'project', etc.
    confidence REAL,
    surprise_score REAL,      -- embedding novelty at time of extraction
    significance_score REAL,  -- final computed significance (respects recurrence floor)
    recurrence_count INTEGER, -- how many conversations mention this topic
    depth_score REAL,         -- computed from turns, msg length, follow-ups
    recurrence_span_days INTEGER, -- days between first and last mention
    significance_type TEXT,   -- 'depth' or 'identity' (D-015 distinction)
    source_conversation_id TEXT,
    created_at REAL,
    updated_at REAL,
    superseded_by TEXT,       -- tracks contradictions/updates
    source TEXT,              -- 'extraction', 'manual', etc.
    subject TEXT,             -- entity this fact is about
    intent TEXT,              -- 'does', 'wants', 'believes', etc.
    temporal_state TEXT,      -- 'current', 'past', 'unknown'
    raw_llm_confidence REAL,
    sentiment TEXT,
    fact_class TEXT,          -- 'event' (immutable) or 'state' (can be contradicted)
    knowledge_tier TEXT,      -- 'identity', 'situational', 'context'
    tiered_by TEXT,           -- which model assigned the tier (opus, sonnet, qwen)
    scope TEXT,               -- 'personal', 'project', 'professional' (D-044)
    fact_type TEXT,           -- 'biographical', 'behavioral', 'positional', 'preference' (D-043)
    commitment_depth TEXT,    -- 'factual', 'preference', 'position', 'conviction' (Frankfurt)
    predicate TEXT,           -- constrained verb from CONSTRAINED_PREDICATES (D-056 Tier 2)
    object_text TEXT,         -- structured object field (D-056 Tier 2)
    qualifier TEXT            -- temporal/conditional context, stored separately from fact_text (D-056 Tier 2)
);

-- Tracks which facts were found together (associative retrieval)
CREATE TABLE fact_relationships (
    fact_id_1 TEXT,
    fact_id_2 TEXT,
    co_occurrence_count INTEGER DEFAULT 1,
    source_conversation_id TEXT,
    PRIMARY KEY (fact_id_1, fact_id_2)
);

-- Cluster assignments for identity generation (D-026)
CREATE TABLE fact_cluster_assignments (
    fact_id TEXT NOT NULL,
    cluster_key TEXT NOT NULL,
    similarity REAL,
    assigned_at REAL,
    PRIMARY KEY (fact_id, cluster_key)
);

-- Epistemic anchors (D-043 ANCHORS layer)
CREATE TABLE epistemic_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_number INTEGER NOT NULL,
    anchor_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    formulation_version INTEGER DEFAULT 1,
    original_text TEXT,
    review_notes TEXT,
    session_confirmed INTEGER,
    source_fact_ids TEXT,
    layer TEXT DEFAULT 'core',
    created_at REAL,
    superseded_by INTEGER,
    updated_at REAL
);

-- Provenance: links layer claims to supporting facts (S56)
CREATE TABLE layer_claim_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer_name TEXT NOT NULL,
    claim_id TEXT NOT NULL,       -- lexicon ID (A1, P3, C2, etc.)
    claim_text TEXT,
    fact_id TEXT,
    link_method TEXT DEFAULT 'authoring',
    similarity_score REAL,
    rank_in_claim INTEGER,
    layer_version TEXT,
    cycle_id TEXT,
    created_at REAL
);

-- Claim verification: binary verification questions per claim (S57)
CREATE TABLE claim_verification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    layer_name TEXT NOT NULL,
    verification_type TEXT NOT NULL,  -- existence, recurrence, cross_domain, temporal
    question TEXT NOT NULL,
    result INTEGER,
    evidence TEXT,
    verified_at REAL,
    layer_version TEXT,
    cycle_id TEXT
);

-- FTS5 full-text search on fact_text (S57)
CREATE VIRTUAL TABLE memory_facts_fts USING fts5(
    fact_text, content='memory_facts', content_rowid='rowid'
);
```

**Total: 16 tables** (13 core + layer_claim_provenance + claim_verification + memory_facts_fts virtual table).

**Fact classification (5 dimensions):**

| Dimension | Values | Purpose | Assigned By |
|-----------|--------|---------|-------------|
| `fact_type` | biographical, behavioral, positional, preference | Routes facts to identity layers (D-043) | Haiku |
| `commitment_depth` | factual, preference, position, conviction | Filters by strength of belief (Frankfurt hierarchy) | Haiku |
| `knowledge_tier` | identity, situational, context | Progressive refinement signal (D-039) | Sonnet / Qwen |
| `temporal_state` | current, past, unknown | Contradiction vulnerability | Qwen |
| `scope` | personal, project, professional | Interaction mode routing (D-044) | Source-based |

**Distribution (4,610 active facts, post-S52 consolidation):** knowledge_tier: identity 2,684, situational 1,022, context 904. fact_class: 4,456 classified (94.1%), 278 biography facts pending Opus classification.

**Multi-user validation (S53-54):**
- **User A:** 1,892 conversations → 4,610 active facts → layers at 78.5/100 (Collective — a multi-agent adversarial review process, since proven ceremonial and removed from the default pipeline)
- **User B:** 36 newsletter posts → 309 active facts → layers at 77.7/100 (Collective)
- **User C:** 9 journal entries → 76 active facts → layers at 81.7/100 (Collective)

**Fact relationships** (Decision D-013): When multiple facts are extracted from the same conversation, they get linked (10,581 co-occurrence edges). When retrieving facts, those that share links with already-retrieved facts get a boost. This approximates human associative memory — remembering one thing triggers related memories.

#### 3D. Enrichment Consolidation

Over time, the AUDN pipeline creates chains of enrichment: fact A updated to B, B updated to C. The enrichment consolidation pass (Session 32) identifies these clusters and selects canonical representatives:

1. **Union-find clustering:** Build a graph of all supersession chains. Use union-find to identify connected components — groups of facts that are all versions of the same underlying knowledge.
2. **Canonical selection:** Within each cluster, pick the most recent active fact as the canonical representative. Mark all others as superseded.
3. **Mega-cluster reduction:** Clusters above a configurable size threshold (default 15) are skipped to avoid collapsing genuinely distinct facts that happen to share transitive enrichment chains.

**Result:** 604 facts consolidated. Superseded facts are never deleted — they remain in the database with `superseded_by` pointers for full provenance tracking.

**Script:** `consolidate_enrichments.py`

#### 3D-2. Provenance and Verification (S56-S57)

Every claim in an identity layer traces back to source facts. Provenance is captured at authoring time (not post-mortem) — fact IDs (`[F-xxx]`) are embedded in generation prompts, and `parse_provenance_from_layer()` extracts the citations from generated markdown. The `layer_claim_provenance` table stores these links.

**Verification** operates in two modes:
- **Vector audit** — embeds each claim, computes cosine similarity against all facts, reports which claims have weak fact support
- **Claim verification** — generates binary yes/no questions per claim (existence, recurrence, cross-domain validation, temporal consistency), executable against the live database

**Access points:**
- `baselayer provenance` CLI command (summary + `--claim ID` trace)
- `baselayer verify` CLI command (vector audit + claim verification)
- `trace_claim` MCP tool (on-demand Genius-style annotation)

**Scripts:** `verify_provenance.py` (vector audit + claim checks), provenance functions in `author_layers.py`

#### 3E. Active Probing (Therapist/Biographer-Inspired)

Most memory systems are passive — they only learn when you happen to mention something. Active Probing turns the memory system from a passive listener into an active interviewer. Instead of waiting for you to volunteer information, the system analyzes what it knows, identifies what's missing or uncertain, and generates targeted questions.

**Gap types detected:**

| Gap Type | Detection Method | Example Question |
|----------|-----------------|------------------|
| **Missing entities** | Named entity with no details | "I know you have two pets and one is [name]. What's the other's name?" |
| **Low confidence** | Facts below threshold or conflicting versions | "Conflicting data about citizenship. Which is right?" |
| **Shallow coverage** | High recurrence but few specific facts | "Cars come up in 76 conversations but mostly modification details. What does the hobby mean to you?" |
| **Temporal gaps** | Long periods with no data on a known topic | "Your project conversations stop mid-2025. What happened since?" |
| **Missing sentiment** | Relationships with no positive/negative signal | "How was your relationship with that colleague?" |
| **Attribution ambiguity** | Facts that might be about someone else | "Conversations about a medical topic. Is that for you or someone in your family?" |
| **Contradictions** | Two facts that can't both be true | "Earlier data says X strategy, but recent data suggests otherwise. Do you?" |
| **Missing negatives** | Only positive traits captured | "I have a lot about your strengths. What are your biggest growth areas?" |

**Modes of probing:**
1. **Opportunistic (preferred)** — organic questions woven into natural conversation. The best personal data comes unprompted during corrections, not from directed questions.
2. **Topical** — when a topic comes up that has known gaps, ask ONE related question
3. **Periodic calibration** — optional, user-initiated review sessions (not forced)
4. **Contradiction triggered** — immediately when the system detects conflicting information

**Script:** `generate_probes.py` (designed but deferred)

#### 3F. Periodic Consolidation ("Sleep")

Like the brain's sleep consolidation process, the system periodically:
1. Re-scores all facts by surprise (things that were novel may now be well-covered)
2. Merges redundant facts via enrichment consolidation
3. Promotes high-confidence patterns into identity tier
4. Adjusts confidence scores based on contradiction detection — facts are never deleted, only superseded or confidence-reduced when contradicted by newer evidence

---

</details>

### Layer 4: Context Projection (IMPLEMENTED -- D-026, D-043)

The assembly layer. Transforms raw memory into a compressed, structured brief injected into the reasoning model's system prompt. The three-layer identity block is authored independently and stored as markdown files; dynamic context (themes, episodes) is assembled per-message by code. Total brief: ~5,000 tokens. No LLM in the critical path for brief assembly — all code-based retrieval.

**Script:** `scripts/assemble_brief.py`
**Format:** XML tags for structure, markdown inside blocks for readability.

#### Three-Layer Identity Architecture (D-043)

Replaces the single identity block from earlier sessions. Each layer is authored independently through its own process:

| Layer | Source Facts | Content | Always-On |
|-------|-------------|---------|-----------|
| **ANCHORS** | Conviction-level facts, confirmed axioms | Epistemic axioms — pre-define probabilistic certainties for the model. 11 confirmed. | Yes |
| **CORE** | Identity-tier biographical facts, clustered by type | Individual overview — who they are, relationships, career, traits | Yes |
| **PREDICTIONS** | Behavioral + conviction/position facts | Situation --> pattern --> directive ("When X, this person tends to Y") | Yes |

**Authoring constraints:**
- **D-040 (Blind):** Facts-only derivation. No prior blocks, no analysis docs, no inherited text, no template carry-forward.
- **D-041 (Audience Principle):** Audience is the AI, not the subject. Every sentence must change LM behavior. D-041 filter encoded in generation prompts (no philosophy framework names in output).
- **D-043 (Three Layers):** Each layer authored independently, from different fact subsets, with different generation prompts.
- **D-044 (Scoped):** Only personal-scope facts feed identity blocks.
- **D-046 (Cheap constraint, expensive discrimination):** Sonnet generates layers (constraint). Collective review in Claude Code sessions (discrimination). Prompt quality is the leverage point — each Collective addition signals a missing prompt question.

**V4 quality outcomes (S52 cycle_003, Collective review: 78.5/100):**
- ANCHORS: 11 axioms with false-positive warnings. 4 axiom interaction pairs. Directive-embedded style with detection signatures.
- CORE: 5 context modes (vs V3's 3). Domain-balanced. D-041 filter applied.
- PREDICTIONS: 8 cross-domain patterns + 4 parked domain-specific. False-positive warnings on all predictions (V3 had none). Pattern interaction map with compound activations.
- Category cap (max 15 facts per category) in retrieval queries prevents topic domination.
- D-055 domain balance: 25% cap prevents any single domain from dominating predictions.
- Single-domain corpus detection: `_detect_corpus_type()` selects PREDICTIONS_SINGLE_DOMAIN_PROMPT for journal/newsletter sources (S53).
- All prompt improvements codified in `author_layers.py` for automatic application on regeneration.

**Authoring pipeline (`author_layers.py`):**
```
python author_layers.py --retrieve anchors       # Show facts for manual authoring
python author_layers.py --retrieve core           # Show facts for manual authoring
python author_layers.py --retrieve predictions    # Show facts for manual authoring
python author_layers.py --generate anchors        # Generate via API (Sonnet)
python author_layers.py --generate all            # Generate all three layers
python author_layers.py --show all                # Show all current layers
python author_layers.py --brief                   # Show assembled three-layer brief
python author_layers.py --store                   # Store layers to data directory
```

**Storage:** Three markdown files in `data/identity_layers/`:
- `anchors_v4.md` — epistemic axioms
- `core_v4.md` — communication & operating guide
- `predictions_v4.md` — behavioral predictions

Each file has a metadata header above `---` and injectable text below. `assemble_brief.py` reads the injectable blocks at assembly time. Unified brief (`brief_v4.md`) is preferred when available; three-layer concatenation is the fallback. Legacy single-block identity (from `identity_blocks` table) is the final fallback.

**Epistemic anchors (11 confirmed, V4):** Stored in the `epistemic_anchors` table with formulation text, status, provenance (source fact IDs), review notes, and versioning. Managed via `extract_anchors.py` + `store_anchors.py` (note: store_anchors.py previously had hardcoded axioms — fixed for multi-user in S55). Reframed as axioms — they pre-define probabilistic certainties for the model, not beliefs to be debated.

**Philosophy research (COMPLETE -- Session 34):** Six identity philosophy frameworks researched, four with implementable mappings:
- **Frankfurt:** `commitment_depth` hierarchy (preference --> position --> conviction)
- **Taylor:** Strong evaluation — meta-preferences distinguishable from first-order preferences
- **Ricoeur:** idem/ipse — stable traits vs. narrative identity evolution
- **Parfit:** Connectedness scoring — psychological continuity measured by overlapping belief chains
- Key insight validated across all 6 frameworks: silence does not equal irrelevance.

#### Identity Cluster Framework (D-026)

The system uses 10 universal identity clusters — predefined dimensions of human identity, inspired by Maslow's hierarchy but for personal knowledge. Each cluster defines a question about the person; semantic retrieval finds the best facts to answer it.

**The 10 Clusters:**

| Cluster | What It Captures | Max Facts |
|---------|-----------------|-----------|
| Who you are | Age, location, education, biography | 4 |
| Who you love | Spouse, family, pets, close relationships | 4 |
| What you've built | Companies, products, achievements | 4 |
| What you've lost | Shutdowns, departures, failures, formative losses | 3 |
| What drives you | Core values, motivations, what matters | 4 |
| What you believe | Worldview, convictions, philosophy | 3 |
| What you struggle with | Weaknesses, negative traits, growth edges | 4 |
| How you operate | Communication style, work habits, preferences | 3 |
| Where you're headed | Goals, aspirations, current trajectory | 3 |
| What's unresolved | Tensions, contradictions, open questions (excluded from identity generation) | 2 |

**How it works:**
1. For each cluster, the cluster description is used as a ChromaDB query against the `memory_facts` collection
2. Semantic retrieval returns candidate facts ranked by meaning-similarity to the cluster description
3. Representative facts are selected from candidates (with fallback to significance+recurrence ranking)
4. Selected facts are grouped by cluster and formatted for identity generation

**Why clusters instead of composite scoring (D-025):** The original Ghost Layer scored every fact individually using a 9-component formula. But 3 of 9 inputs were effectively constant across the dataset, making the category weights the only differentiating signal. Clusters solve this by asking "what are the best facts about X?" rather than "which facts score highest overall."

**Temporal depth** runs through every cluster, not on top of it. Rather than arbitrary time-based boundaries, the system uses a contradiction-based model: facts remain at full confidence until contradicted by newer evidence. MiniLM similarity filtering surfaces candidate contradiction pairs, and Opus judges whether they represent genuine contradictions, enrichments, or coexistence. Time informs context but does not determine relevance — silence does not equal irrelevance. See `docs/reviews/TEMPORAL_PROCESSING_REVIEW.md` (V3).

**Volatility** markers indicate how fast each cluster changes: low (who you are), medium (what you believe), high (where you're headed). This guides update frequency.

#### Block 2: Relevant Themes (Retrieved, ~700-800 tokens)

Dynamically assembled based on the user's message. Scoring: **60% semantic similarity + 40% importance** (significance x 0.7 + recurrence x 0.3). Associative retrieval (D-013) boosts facts that co-occur with already-selected facts by 20%.

Facts are grouped by category with readable labels (People, Values, Skills, etc.) and annotated with subject and temporal state.

#### Block 3: Episodic Details (Retrieved, ~500-600 tokens)

Top 5 conversation summaries, scored: **50% similarity + 30% recency + 20% base**. Each enriched with conversation title, date, and the top 2-3 facts extracted from that conversation. Formatted as dated XML episodes.

```xml
<episode date="2025-09-25" topic="Trading buddy setup">
Detailed trading session review with entry/exit prices, P/L tracking.
Key facts: focused on technical analysis; concerned with risk-reward ratio.
</episode>
```

#### Assembly Pipeline

```
User message arrives
    |
    v
Embed user message (sentence-transformers, ~10ms)
    |
    +-->  Search ChromaDB memory_facts (top 30) --> theme candidates
    +-->  Search ChromaDB conversation_summaries (top 10) --> episode candidates
    |     (scored by: similarity x ghost importance / similarity x recency)
    |
    v
Assemble brief:
    Instruction: "You know this person. Trust user over profile."
  + Identity (three-layer: anchors + core + predictions, from markdown files)
      Falls back to legacy identity_blocks table if three-layer files absent
  + Themes (top 25 facts, 60% sim + 40% ghost, associative boost, ~700-800 tokens)
  + Episodes (top 5 summaries, enriched with facts, ~500-600 tokens)
  + Session buffer (heuristic-captured facts from this session)
    |
    v
~2,000-2,600 token brief ready for injection (~100ms total assembly)
```

**No separate topic classifier** (Decision D-008): The embedding already encodes topic information. Searching ChromaDB directly gives us topic-relevant results without a slow LLM classification step.

**Session buffer** (Decision D-011): Heuristic pattern matching captures obvious declarations mid-conversation ("I just...", "I started...", "my name is...") without LLM calls. Buffer clears when the session ends.

**Measured performance:** ~100-120ms assembly time (well under 2,600 token budget).

---

### Layer 5: Reasoning Model

Claude serves as the conversational reasoning model. At runtime, Claude is stateless — all "memory" comes from the brief injected into its system prompt.

**Technology:** Claude API (Sonnet for daily conversations, Opus for complex reasoning); Claude Code for identity authoring and architecture decisions
**Runtime input:** System prompt with memory brief (up to ~5,000 tokens) + user message
**Runtime output:** Response to user

**Model Roles (Simplified Pipeline):**

| Model | Role | When | Cost |
|-------|------|------|------|
| **Haiku** (API) | Extraction | Structured fact extraction with 47 constrained predicates | ~$0.10-0.50 per corpus |
| **Sonnet** (API) | Generation | Three-layer identity authoring (D-046) | ~$0.05-0.15 |
| **Opus** (API) | Composition | Compress 3 layers → unified narrative brief | ~$0.05-0.15 |
| **Pure code** | Brief assembly + serving | Loads and serves final brief via MCP | $0 |

The original pipeline also used Qwen 2.5 14B (local extraction), MiniLM (similarity/dedup), and Haiku classification (fact_type + commitment_depth). These remain available but are not part of the simplified pipeline.

**Why Claude stays stateless for conversation:** Updatability. If memory were baked into model weights (fine-tuning), every new conversation would require re-training. With injection, updating memory is instant — just update the database.

---

## Data Flow

### Pipeline: Building the Brief

```
1. IMPORT: User provides conversation exports, journals, or text files
         |
         v
2. EXTRACT (Haiku API): Text → structured facts (AUDN lifecycle)
         |
         v
3. AUTHOR (Sonnet API): Facts → three-layer identity (ANCHORS + CORE + PREDICTIONS)
         |
         v
4. COMPOSE (Opus API): 3 layers → unified narrative brief (~2,500 tokens)
         |
         v
5. SERVE (MCP): Brief available as always-on identity Resource
```

### Runtime: A Conversation Turn

```
1. USER types a message
         |
         v
2. LOAD (code only, no LLM): Unified brief from brief_v4.md
         |
         v
3. CLOUD (Claude API): System prompt with brief + user message --> response
         |
         v
4. USER sees the response
```

No LLM in the runtime critical path — brief assembly is pure code (~100ms).

**Latency budget:**

| Step | Operation | Time |
|------|-----------|------|
| 2 | Embed user message | ~10ms |
| 3 | Vector retrieval | 20-50ms |
| 4 | Brief assembly | 50-100ms |
| 5 | Claude API response | 1-3 seconds |
| **Total** | **User-facing** | **~1.1-3.2 seconds** |
| 7 | Session buffer update | <50ms |
| 8 | Full post-processing | 5-20 seconds (async, non-blocking) |

Note: Removing the separate topic classification step (Decision D-008) saves 100-200ms from the original design.

---

## Four Memory Tiers

The system maintains four tiers of memory, each at a different level of compression and accessibility:

```
+-------------------------------------------------------+
|  TIER 1: Core Identity              ~5,000 tokens  |
|  Always in context. Three-layer architecture (D-043).  |
|  ANCHORS + CORE + PREDICTIONS.                         |
|                                                        |
|  Epistemic axioms, stable facts, values,               |
|  behavioral predictions, communication style.          |
+--------------------------------------------------------+
|  TIER 2: Thematic Patterns          ~700-800 tokens      |
|  Retrieved by topic. Updated as patterns emerge.       |
|  "What does this person care about?"                   |
|                                                        |
|  Project architectures, strategies, career goals,      |
|  recurring interests, opinions.                        |
+--------------------------------------------------------+
|  TIER 3: Episodic Summaries         ~50K tokens          |
|  Searchable. One per conversation.                     |
|  "What happened in conversation X?"                    |
|                                                        |
|  3-5 sentence summaries with key topics,               |
|  decisions, emotional context, extracted facts.        |
+--------------------------------------------------------+
|  TIER 4: Raw Conversations          Infinite             |
|  Ground truth. Never fed to LLM directly.              |
|  "What exactly was said?"                              |
|                                                        |
|  40,997 messages across 1,892 conversations             |
|  (primary test user).                                   |
|  SQLite database, fully indexed and searchable.        |
+--------------------------------------------------------+
```

**Information flows upward through consolidation:**
- Raw conversations --> summarized into episodes (Tier 4 --> 3)
- Surprising episodes --> extracted into facts and patterns (Tier 3 --> 2)
- High-confidence patterns --> promoted into identity layers (Tier 2 --> 1)
- Conviction-level facts --> cross-referenced for epistemic anchors

**The "Intelligent Update Rules" govern promotion:**

| Signal | Action |
|--------|--------|
| Confirms existing pattern | Strengthen confidence score |
| Adds nuance to a pattern | Update with specificity |
| Contradicts existing pattern | Note evolution: "Previously X, now Y" |
| New domain entirely | Create new thematic entry |
| One-off detail | Keep in episodic layer, don't promote |
| 30+ windowed recurrence, 1+ year span | **Auto-elevate to identity candidate** (recurrence floor) |
| High depth on any topic | Promote as depth-significant theme |
| Conviction-level commitment (Frankfurt) | Candidate for ANCHORS layer |

---

## Technology Stack

| Component | Technology | Purpose | Status |
|-----------|-----------|---------|--------|
| Ground truth DB | SQLite | Raw conversation + fact storage | COMPLETE |
| Vector store | ChromaDB | Semantic search, embedding storage | COMPLETE |
| Embedding model | all-MiniLM-L6-v2 | 384-dim sentence embeddings | COMPLETE |
| Local LLM | Qwen 2.5 14B (Q4_K_M) via Ollama | Fact extraction, event/state classification (no narrative; scoring is data-driven) | CONFIRMED (D-016) |
| Classification | Haiku (API) | fact_type + commitment_depth, batched | COMPLETE |
| Layer generation | Sonnet (API) | Three-layer identity generation (D-046) | IMPLEMENTED |
| Contradiction judge | Opus 4.6 (session) | Judges fact-pair contradictions via MiniLM filtering | COMPLETE |
| Reasoning LLM | Claude API (Sonnet 4.5) | User-facing conversation, complex reasoning | IMPLEMENTED |
| Identity authoring | Claude Code sessions + author_layers.py | Layer authoring, Collective review, $0 API cost | IMPLEMENTED |
| Language | Python | All scripts and pipelines | ACTIVE |
| Hardware | RTX 3080 (10GB), 32GB RAM | Local inference | ACTIVE |

---

## Multi-User and Data Isolation

The system is designed for multi-user deployment without code duplication:

**Data isolation (D-044):** Set the `MEMORY_SYSTEM_ROOT` environment variable to redirect all data paths to a different root directory. Scripts stay shared; only the data directory changes.

```
export MEMORY_SYSTEM_ROOT=/path/to/user_b_memory
python extract_facts.py   # reads/writes user_b_memory/data/...
python author_layers.py --generate all  # generates for User B's data
```

**Database initialization:** `init_database.py` creates all tables needed by the pipeline for a new user. Used for the Subject B experiment and future multi-user deployments.

**Entity maps:** Per-user `entity_map.json` in the data root provides name-to-canonical-entity resolution (e.g., "wife" --> "spouse:[name]"). Extraction prompts reference this at runtime instead of hardcoding entities.

**Prompt generalization:** Classification and extraction prompts are person-agnostic. No hardcoded names, no person-specific examples. Generic examples selected by Collective review (Session 38).

**Multi-user validation (N=10, Sessions 53-79):**
- **User C (9 journal entries):** V4 pipeline: 81 extracted → 76 active → layers at 81.7/100 (Collective). Case study proved V4 > V3 (V3 hallucinated client's children as User C's). Token efficiency: identity layers use 26% fewer input tokens than raw journal while producing structurally superior responses.
- **User B (36 newsletter posts):** V4 pipeline: 406 extracted → 309 active → layers at 77.7/100. Single-domain PREDICTIONS prompt + corpus-type detection fixed (S53). Revealed 2 CRITICAL contamination bugs (store_anchors.py hardcoded axioms, author_layers.py hardcoded conflicts).
- **User A — the primary test user (1,892 ChatGPT conversations):** V4 pipeline: 5,270 extracted → 4,610 active → layers at 78.5/100 (cycle_003). Blind eval: +2.8 behavioral prediction gap.
- **Benjamin Franklin (autobiography):** 117 active facts → 79 identity-tier → ANCHORS 75.75/100 + CORE 73/100 + PREDICTIONS 75/100. Eval: C5c wins (+0.40).
- **Frederick Douglass (autobiography):** 47 active facts → brief ~2,137 tokens.
- **Mary Wollstonecraft (published treatise):** 45 active facts → brief ~1,688 tokens.
- **Theodore Roosevelt (autobiography):** 87 active facts → brief ~2,738 tokens.

**Note on first-run pipelines:** New pipelines produce facts with `knowledge_tier = NULL` ('untiered'). The tier step (Step 6) now auto-initializes these to 'context' before running Sonnet promotion, preventing downstream failures in layer authoring that expect all facts to have a tier assigned.

**Known contamination risks (S53):** store_anchors.py previously had hardcoded axioms, author_layers.py had hardcoded inter-axiom conflicts (heuristic guard added but brittle), assemble_brief.py had user-specific cluster descriptions. Fixed in S55 for multi-user release.

---

## Evaluation: How We Know It's Working

(Decision D-014) Without measurement, we're guessing.

**Evaluation harness (`run_eval.py`):** 20-case test suite covering diverse topics.
- For each test case, generate a memory brief
- Have Claude answer a question about the user using only the brief
- Score: Did it get the right context? Did it miss something obvious? Did it feel natural?
- **Current results:** 85% pass rate, 0.91 presence score (brief captures relevant facts), 1.00 absence score (doesn't hallucinate absent information)
- Track scores over time as thresholds and prompts are tuned

**The Collective (D-024):** 4-persona adversarial review mechanism. Each persona evaluates identity blocks from a different angle (accuracy, completeness, tone, behavioral utility). Used for identity block review and layer review.

**A/B/C blind eval (D-014):** Generate multiple brief variants, rate them blind, reveal which approach produced each. Prevents anchoring to the current approach.

---

## What's Built vs. What's Next

```
COMPLETE (Core Pipeline)                    COMPLETE (Infrastructure)
------------------------                    -------------------------
[x] 4-step pipeline (Import→Extract→       [x] CLI packaging (baselayer, pip install)
    Author→Compose)                         [x] MCP server (identity + recall/search/trace)
[x] 47 constrained predicates              [x] Cost estimator (baselayer estimate)
[x] Three-layer identity (D-043)           [x] Multi-source importer (ChatGPT/Claude/text)
[x] Unified brief composition              [x] Document mode (books, essays, patents)
[x] Provenance traces (S56-57)             [x] Data isolation (MEMORY_SYSTEM_ROOT)
[x] N=10 validation (73-82/100)            [x] 414 tests, 76 design decisions
[x] Pipeline ablation (14→4 steps, S79)    [x] Anti-parrot preamble (S63)
[x] Twin-2K benchmark (71.83%, p=0.008)    [x] Person-agnostic prompts
[x] BCB-0.1 Franklin                       [x] Anonymization layer
[x] Website LIVE (base-layer.ai)            [x] Database initializer (init_database.py)
[x] GitHub repo LIVE (agulaya24/BaseLayer)  [x] Code review S81 (13 bugs fixed, 0 blockers)
[x] Privacy scrub (S81)                     [x] Pipeline validation (all subjects)

NEXT                                        POST-LAUNCH
----                                        -----------
[ ] Paul Graham case study                  [ ] ADRB benchmark (~$30)
[ ] Self-referential case study             [ ] Dissenting opinion benchmark (D-076)
                                            [ ] Brief structure update (D-075)
                                            [ ] Cross-provider blind eval
                                            [ ] Local deployability improvements
```

---

## Cold Start Problem

**Scenario:** A new user installs Base Layer and connects via MCP with zero data. The identity resource returns nothing, recall tools return empty results. The AI has no context.

**Three user profiles at install:**

| Profile | Path | Status |
|---|---|---|
| Has conversation history (ChatGPT/Claude exports) | Import → pipeline → identity in ~30 min | Works today |
| Has journals/notes | Import text files → pipeline | Works today |
| Has nothing | ??? | Not solved |

**The "has nothing" user is a first-impression problem.** Anyone hearing about Base Layer, installing it, and connecting MCP expects value. Getting an empty identity is a dead end.

**Mitigation strategy:**
1. **Journal-first onboarding** (Task #7) — `baselayer init` prompts the user through 10-15 guided questions about values, relationships, career, preferences. Answers are imported as text files. Journal input produces higher-quality identity facts per entry than conversation history.
2. **Graceful degradation** — MCP identity resource should communicate "building your profile" state rather than "nothing found."
3. **Real-time ingestion** (v2) — MCP captures conversations as they happen, triggers incremental extraction. Adds complexity; raises circularity question (extracting from conversations that already have the brief injected). Deferred.

**Key insight:** This is likely an edge case. Most AI users have conversation history to import. But it's the *first impression* edge case — the one that determines whether a new user gets to the "aha" moment or bounces.

---

## Autobiography Case Study

**Idea:** Run the full Base Layer pipeline on published autobiographies of public figures. Import the text, extract facts, generate identity layers, and evaluate against known information about the person.

**Why this is valuable:**
- **Validation without privacy concerns** — public figures, published material
- **Ground truth available** — can check identity layers against well-documented lives
- **Marketing material** — "We ran Base Layer on [famous person]'s autobiography and here's what it produced"
- **Pipeline stress test** — book-length input (50K-100K+ words) tests extraction at scale

**Candidate format:** Import autobiography as text file(s), run standard pipeline, evaluate identity layer quality against known biographical facts.

---

## Three-Tier Product Architecture (Session 59 — CANDIDATE)

Base Layer ships as three product tiers, each serving a different user type:

| Tier | What | Price | How It Works |
|---|---|---|---|
| **Preferences** | Structured preferences exported for Claude/ChatGPT/Gemini paste-in | Free | Minimal pipeline (extract + classify). User pastes output into provider's native preferences/memory UI. |
| **Core + Anchors** | Full identity layers (ANCHORS + CORE + PREDICTIONS) | $3-5 per run | Full pipeline through authoring. Output is injectable markdown. Delivered via MCP or manual paste. |
| **Full Pipeline** | Open-source self-hosted pipeline | Free (BYOS) | User runs entire pipeline locally. Full control over provider choice, data, and processing. |

**Cost structure (per user):**
- Full pipeline: ~$0.52-3.33 depending on corpus size and provider
- Simple preferences: ~$0.17-0.47
- At 100 users: ~$106 (full) or ~$35 (simple preferences)

**Provider-agnostic pipeline:** For Tier 1 (Preferences) and Tier 2 (Core + Anchors), the pipeline internally benchmarks Anthropic, OpenAI, and Google at each step, selecting the best cost/quality combination per role. The user does not choose a provider. Tier 3 (open-source self-hosted) retains user provider choice for full control.

**New CLI commands (planned):**
- `baselayer export --format preferences --provider claude/chatgpt/gemini` -- export structured preferences for paste-in
- `baselayer generate --tier standard` -- generate Tier 2 output (Core + Anchors)

**Competitive context:** Claude launched its own memory import feature (claude.com/import-memory, March 2026), which exports flat facts from ChatGPT/Gemini into Claude's native memory. Base Layer's Tier 1 (Preferences) serves a similar surface-level need, but the full pipeline (Tier 2-3) produces structured behavioral models that flat fact imports cannot.

**Analogy:** Quiet-STaR ("thinking before speaking") at the system level -- the pipeline is the reasoning that happens before the model ever sees the brief. The question is whether that upstream reasoning adds value over simply handing the model raw data with a good prompt.

---

## Key Research Decisions

These conclusions come from deep research into Google Titans, Mem0, Letta/MemGPT, and context engineering best practices. Full details in `docs/versions/archived-research/RESEARCH_FINDINGS.md`.

**Why build custom instead of adopting a framework?**
- Mem0's local Ollama support has multiple open bugs; bulk ingestion would take days
- Letta/MemGPT needs GPT-4-class models for self-editing memory; Qwen 14B is too weak
- Google Titans has no pretrained weights; can't train on consumer hardware
- Our existing SQLite + ChromaDB stack is a stronger foundation than any of them

**Why surprise-based scoring?**
- Standard RAG retrieves everything similar. Surprise scoring answers "is this *new*?"
- Filters out ~40-50% of routine content, keeping only genuinely novel information
- Mirrors how human memory works: surprising events are encoded more strongly
- Significance is measured by **recurrence + depth**, not just LLM judgment — a topic appearing in 72 conversations with deep engagement is objectively important, no guessing needed

**Why hybrid local + cloud + session?**
- Local (optional Qwen 14B via Ollama): handles fact extraction locally if configured — private data never leaves your machine. No narrative generation.
- Cloud (Haiku/Sonnet): handles extraction (conversation text sent for fact extraction), classification (individual fact text, batched), and layer generation (D-046). Nothing stored remotely.
- Cloud (Claude API): handles reasoning — gets only an assembled brief, never raw data
- Session (Opus, Claude Code): handles identity authoring, Collective review, architecture decisions — periodic, manual, $0 API cost
- Best of all approaches: privacy for data, intelligence for conversation, quality for identity

**Why Qwen 2.5 14B over newer/bigger models?** (Decision D-016)
- Tested four models head-to-head: Qwen 2.5, Qwen 3, Llama 3.1, Hermes 2 Pro
- Qwen 3 is marginally smarter (10 vs 9 on top topics) but 5-8x slower — impractical for batch processing 1,800+ conversations
- Hermes 2 Pro has perfect JSON but weak judgment (7B brain caps at 7 for everything)
- Key finding: **the data-informed approach (D-015) mattered more than the model**. All models improved equally when given recurrence + depth data. Invest in better data, not bigger models.

**Why three-layer identity instead of a single block?**
- Single blocks conflate axioms, biography, and behavior. A sentence about a core belief sits next to a pet's name sits next to a work habit.
- Three layers let each type of knowledge be authored from the right facts, with the right prompt, at the right update cadence.
- ANCHORS change rarely (axioms). CORE changes when life circumstances change. PREDICTIONS change as behavior evolves.
- Each layer can be evaluated independently. A bad prediction doesn't contaminate a good axiom.

**Why journal input produces better identity layers than conversation history?**
- User C's 76 journal-derived facts scored higher on identity layer quality than User A's 5,270 conversation-derived facts
- Journal writing is inherently self-reflective — higher signal-to-noise for identity extraction
- Conversations are reactive; journals are reflective. The self-reflection produces better behavioral data.
- Argues for journal-first onboarding flow for new users — active self-reflection yields richer identity layers per fact

**Why ~5,000 tokens for the brief?**
- Research shows adding 512 input tokens costs less latency than generating 8 output tokens
- ~5,000 tokens is ~2.5% of Claude's context window — leaves 97%+ for actual conversation
- Identity layers (~2,500 tokens, V4 briefs) carry the behavioral model; theme + episode retrieval (~1,400 tokens) adds query-specific context
- D-042 (empirical budget) suspends a priori budget assumptions; optimization study planned
- The 80/20 rule: this budget captures ~90% of the "knowing" feeling

---

## File Structure

```
memory_system/
+-- pyproject.toml                     # Package config (pip install baselayer)
+-- README.md                          # Quick-start guide
+-- data/
|   +-- raw/
|   |   +-- conversations.json         # ChatGPT export
|   |   +-- media/                     # Images, audio files
|   +-- database/
|   |   +-- memory.db                  # SQLite ground truth
|   |   +-- extraction_progress.json   # Resumable extraction state
|   +-- vectors/                       # ChromaDB embeddings
|   +-- identity_layers/               # Three-layer identity files (D-043)
|   |   +-- anchors_v4.md             #   Epistemic axioms
|   |   +-- core_v4.md                #   Communication & operating guide
|   |   +-- predictions_v4.md         #   Behavioral predictions
|   +-- entity_map.json                # Per-user name resolution
+-- scripts/
|   +-- config.py                      # Shared configuration (single source of truth)
|   +-- cli.py                         # CLI entry point (baselayer command, 25 subcommands)
|   +-- mcp_server.py                  # MCP server (identity resource + recall/search/trace/verify_claims tools)
|   +-- api_client.py                  # Centralized Anthropic API singleton + retry + logging (S56)
|   +-- __init__.py                    # Package init (version)
|   +-- __main__.py                    # python -m baselayer support
|   +-- init_database.py               # Initialize clean databases (multi-user)
|   +-- import_conversations.py        # Multi-source importer (ChatGPT/Claude/text files)
|   +-- extract_facts.py               # Phase 4: AUDN fact extraction (Haiku API or Ollama)
|   +-- embed.py                       # Phase 2: Create embeddings
|   +-- score_facts.py                 # [ARCHIVED → scripts/archive/dead_pipeline_steps/score_facts.py]
|   +-- classify_facts_haiku.py        # [ARCHIVED → scripts/archive/dead_pipeline_steps/classify_facts_haiku.py]
|   +-- reclassify_tiers.py            # [ARCHIVED → scripts/archive/dead_pipeline_steps/reclassify_tiers.py]
|   +-- consolidate_enrichments.py     # [ARCHIVED → scripts/archive/dead_pipeline_steps/consolidate_enrichments.py]
|   +-- detect_contradictions.py       # Contradiction detection (MiniLM + Opus)
|   +-- assemble_brief.py             # Phase 5: Brief assembly + three-layer identity + Claude
|   +-- author_layers.py              # Three-layer authoring (D-043) — Collective review removed S79
|   +-- store_anchors.py              # [ARCHIVED → scripts/archive/dead_pipeline_steps/store_anchors.py]
|   +-- extract_anchors.py            # [ARCHIVED → scripts/archive/dead_pipeline_steps/extract_anchors.py]
|   +-- apply_corrections.py           # [ARCHIVED → scripts/archive/one_off/apply_corrections.py]
|   +-- semantic_search.py             # Phase 2: Meaning-based search
|   +-- run_eval.py                   # [ARCHIVED → scripts/archive/eval_scripts/run_eval.py]
|   +-- verify_provenance.py          # Vector audit + claim verification (S57)
|   +-- llm_provider.py               # Multi-provider LLM abstraction (D-052)
|   +-- batch_extract.py              # Batch API re-extraction (D-057)
|   +-- checkpoint.py                 # Pipeline quality gate reports
|   +-- agent_pipeline.py             # D-054: Layer-specific agents (Collective removed S79 — proven ceremonial)
+-- lexicon_schema.yaml               # Lexicon structure definition (S56)
+-- agents/                           # Agent definitions for D-054 (ANCHORS, CORE, PREDICTIONS, Collective)
+-- tests/                            # Test suite (414 tests)
+-- docs/
|   +-- core/
|   |   +-- ARCHITECTURE.md            # This document -- the full system design
|   |   +-- DECISIONS.md               # Every design decision with reasoning (76 logged)
|   |   +-- DESIGN_PRINCIPLES.md       # Core principles and philosophical commitments
|   |   +-- PROGRESS.md                # Build progress and session history
|   |   +-- PROJECT_OVERVIEW.md        # Concise project overview
|   |   +-- FLOW_GUIDE.md              # User flow guide (install to brief, 10 steps)
|   |   +-- EPISTEMIC_AXIOMS.md        # Formalized axiom definitions with provenance
|   |   +-- architecture_diagram.html   # Visual architecture diagram (HTML+SVG)
|   +-- analysis/
|   |   +-- USER-ANALYSIS.md           # Observations on the user as collaborator
|   |   +-- CLAUDE-APPROACH.md         # How Claude's approach has evolved
|   |   +-- CHARACTER_OVERVIEW.md      # Full identity portrait (D-040: do not use for block authoring)
|   +-- reviews/
|   |   +-- TEMPORAL_PROCESSING_REVIEW.md  # V4: Contradiction-based temporal model
|   |   +-- ANCHOR_REVIEW_SESSION37.md  # Epistemic anchor review notes
|   |   +-- CONTAMINATION_REVIEW.md     # Scope contamination measurement
|   |   +-- VALUE_PROPOSITION_REVIEW.md  # Value prop Collective review (B+)
|   +-- research/
|   |   +-- PHILOSOPHY_OF_IDENTITY.md   # Frankfurt, Taylor, Parfit, Ricoeur + 6 more
|   +-- eval/
|   |   +-- EVAL_FRAMEWORK.md          # Brief vs. raw history evaluation protocol
|   +-- plans/                         # Implementation plans (multi-provider, score refactor, extraction cap scaling)
|   +-- versions/                      # Timestamped doc snapshots
|   |   +-- archived-research/         # Completed/historical research
|   |   |   +-- RESEARCH_FINDINGS.md   # Session 4 deep research on Titans, Mem0, Letta
|   |   |   +-- LLM_PROXY_RESEARCH.md  # Session 16 LiteLLM/OpenRouter research
|   |   +-- archived-reviews/          # Superseded review artifacts
|   |   |   +-- COLLECTIVE_REVIEW_BLOCK_13.md  # Block 13 review (pre-three-layer)
|   |   |   +-- IDENTITY_REVIEW_V1.md  # Session 9 identity review corrections
|   |   +-- SESSION_20_NOTES.md        # Raw intellectual threads from Session 20
+-- gtm/                               # Go-to-market materials
|   +-- content/                        # Landing page copy, content assets
|   +-- strategy/                       # GTM strategy, comparables, manifesto, project evolution
|   +-- research/                       # Provider memory analysis, launch examples
|   +-- archive/                        # Superseded GTM materials
+-- reference/                         # Session transcripts and early prototypes
+-- backups/                           # Timestamped project backups
```

---

## Tracking and Context Recovery

All design decisions are logged in `docs/core/DECISIONS.md` with full reasoning (62 decisions, D-001 to D-062). If a session needs to restart, these files provide complete context:

1. **`ARCHITECTURE.md`** (this file) -- what the system IS
2. **`DESIGN_PRINCIPLES.md`** -- the philosophical and design commitments that guide every decision
3. **`DECISIONS.md`** -- WHY each choice was made
4. **`PROGRESS.md`** -- WHERE we are in the build (session history)
5. **`PROJECT_OVERVIEW.md`** -- concise project overview with current stats

Additionally, `CLAUDE.md` in the project root provides auto-loaded session bootstrap for Claude Code, including current state, open work, session reminders, and key constraints.
