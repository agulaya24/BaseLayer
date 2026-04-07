# System Architecture
## Base Layer: Behavioral Compression for AI Identity
**Updated 2026-04-02 (Session 101+)**

---

## The Problem

AI agents do not understand how the people they serve actually think, decide, and communicate. This is not a memory problem (the agent forgets what you said) — it is a modeling problem (the agent never knew how you operate). Provider-side user models (ChatGPT Memory, Claude Projects) are opaque, non-portable, and non-inspectable. As agents gain autonomy and take actions on behalf of humans, a misaligned operator model compounds: the agent does not give a bad answer, it acts on a wrong assumption.

Larger context windows do not solve this. Raw conversation history is retrieval, not understanding. The agent still has no model of how you reason or what you prioritize.

## The Solution

Base Layer compresses text (conversations, journals, essays, any personal writing) into a portable behavioral specification: a 3-6K token structured document that captures how someone reasons, communicates, and decides. Inject that guide into any AI, and it operates within the person's behavioral constraints instead of guessing.

The output is locally owned, provenance-traced to source text, and provider-agnostic. 57+ subjects modeled across 6 source types. Validated via Twin-2K benchmark (N=100, 71.83% accuracy at 18:1 compression, p=0.008).

**North star:** Every agentic workflow needs a reliable model of who the human is. That model should be owned by the human: inspectable, correctable, portable across any system.

---

## Pipeline Overview (5 Steps)

Pipeline ablation (Session 79, 14 conditions, ~$16) proved that 10 of the original 14 processing steps were ceremonial. The simplified pipeline scores higher (87/100 vs 83/100). The three-layer architecture is load-bearing; the intermediate processing steps (scoring, classification, tiering, contradiction detection) are not. Cut — see `docs/eval/ablation/`.

```
                    BASE LAYER PIPELINE
 +--------------------------------------------------------------+
 |                                                                |
 |   STEP 1: IMPORT                                               |
 |   +----------------------------------------------------------+ |
 |   | Multi-source importer (ChatGPT, Claude, journals, text)  | |
 |   | -> SQLite (conversations + messages)                      | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 2: EXTRACT             v                                |
 |   +----------------------------------------------------------+ |
 |   | Haiku API -- 47 constrained predicates                    | |
 |   | Text -> {subject, predicate, object, qualifier} triples   | |
 |   | AUDN (Add, Update, Delete, Noop) fact lifecycle           | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 3: EMBED               v                                |
 |   +----------------------------------------------------------+ |
 |   | MiniLM-L6-v2 -- local vector embeddings                  | |
 |   | ChromaDB storage for provenance tracing                   | |
 |   | Required for fact->claim linking                          | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 4: AUTHOR              v                                |
 |   +----------------------------------------------------------+ |
 |   | Sonnet -- Three-layer identity generation (D-043)         | |
 |   | H3 prompts: domain-agnostic guard (D-089, S99 ablation)  | |
 |   | ANCHORS | Epistemic axioms                                | |
 |   | CORE    | Operational constraints                         | |
 |   | PREDICT | Situation -> pattern -> directive               | |
 |   +---------------------------+------------------------------+ |
 |                               |                                |
 |   STEP 5: COMPOSE             v                                |
 |   +----------------------------------------------------------+ |
 |   | Opus -- Compress 3 layers -> unified brief (3-6K tokens)  | |
 |   | They/them pronouns enforced (D-092)                       | |
 |   | Domain-agnostic guard (D-091)                             | |
 |   | Served via MCP as always-on identity Resource              | |
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

**One command:** `baselayer run <file>` runs steps 1-5 with a cost estimate gate before spending anything.

---

## Step 1: Import

Ingests text from multiple source formats into a normalized SQLite schema. Incremental — re-running on the same export skips already-imported conversations.

**Supported sources:** ChatGPT JSON export, Claude Code sessions, Claude.ai web export, plain text files, directories of text files, journal entries.

**Script:** `src/baselayer/import_conversations.py`

**Schema:**

| Table | Columns | Purpose |
|-------|---------|---------|
| `conversations` | id, title, created_at, updated_at, message_count, source | One row per conversation or document |
| `messages` | id, conversation_id, parent_id, role, content_text, created_at, sequence_order | One row per message or text chunk |

For non-conversation text (autobiographies, patents, essays), use `--document-mode`. The importer treats the entire document as a single "conversation" with the text as one message.

---

## Step 2: Extract

Transforms raw text into structured facts using Haiku API (or optionally Ollama for local extraction).

Each message or text chunk is processed through the AUDN lifecycle:

| Action | When | Example |
|--------|------|---------|
| **ADD** | No equivalent fact exists | "Started learning Rust" |
| **UPDATE** | Refines existing fact | "Likes Python" -> "Likes Python and Rust" |
| **DELETE** | Contradicts existing fact | "Is vegetarian" contradicted by new info |
| **NOOP** | Already known | "Lives in SF" already stored |

**Output format:** `{subject, predicate, object, qualifier}` triples. The 47 constrained predicates (owns, values, practices, trades, fears, excels_at, relates_to, collaborates_with, etc.) enforce keyword-rich, structured output. `normalize_predicate()` maps LLM variants to canonical forms. This structured format replaced free-text extraction after discovering that generic language ("The user is interested in X") inflated recurrence counts by 30x (D-056).

**Text chunking:** Long texts exceeding `input_char_budget` are auto-chunked on paragraph boundaries with 500-char overlap. Character tiers: 0-12K chars -> 10 facts max, 12K-30K -> 20, 30K-60K -> 35, 60K+ -> 50. Per-chunk cap: 15 facts. AUDN dedup handles cross-chunk duplication.

**Anonymization:** `author_layers.py` replaces subject names with "this person" before any model sees data. All extraction prompts include "DERIVE ONLY FROM INPUT" constraint.

**Script:** `src/baselayer/extract_facts.py`

**Re-extraction requirement:** Clearing extraction data requires deleting BOTH SQLite rows (`memory_facts` + `extraction_log`) AND the ChromaDB collection. Without clearing ChromaDB, old vectors cause AUDN to NOOP on legitimate new facts.

---

## Step 3: Embed

Generates vector embeddings of extracted facts using MiniLM-L6-v2 (384 dimensions, runs locally). Stored in ChromaDB. Required for provenance tracing — linking identity claims back to source facts via vector similarity.

**ChromaDB uses L2 distance** (not cosine). Similarity calculation: `1 - dist^2/2`.

**Script:** `src/baselayer/embed.py`

---

## Step 4: Author

Generates three identity layers from extracted facts using Sonnet API. Each layer is authored independently from different fact subsets with different prompts.

### Three-Layer Identity Architecture (D-043)

| Layer | Input Facts | Content | Update Cadence |
|-------|------------|---------|----------------|
| **ANCHORS** | Conviction-level facts, confirmed axioms | Epistemic axioms that pre-define how the model should weigh competing interpretations | Rare (axioms change slowly) |
| **CORE** | Identity-tier biographical + behavioral facts | Communication patterns, operating modes, relationships, career context | When life circumstances change |
| **PREDICTIONS** | Behavioral + conviction/position facts | Situation -> pattern -> directive. "When X happens, this person tends to Y. Do Z." | As behavior evolves |

**Concrete example of each layer:**

```
ANCHORS -- The axioms you reason from.

  COHERENCE
  If your response contains internal inconsistency, flag it before presenting
  it -- they will detect it and trust you less for not catching it first.

PREDICTIONS -- Behavioral patterns with triggers and directives.

  ANALYSIS-PARALYSIS SPIRAL
  Trigger: A high-stakes decision with multiple valid options.
  Directive: "The decision on the table is X. Your analysis would change
  the decision if Y. Is Y still plausible?"

CORE -- How you operate. Communication patterns, context modes.
```

### Authoring Constraints

These are the load-bearing design decisions that prevent the most common failure modes:

| Decision | Rule | Why |
|----------|------|-----|
| D-040 (Blind derivation) | Facts-only input. No prior blocks, no analysis docs, no inherited text. | Showing prior output to Sonnet causes 26% anchoring bias. |
| D-041 (Audience = AI) | Every sentence must change LM behavior. No philosophy framework names in output. | The brief teaches an AI, not describes a person. |
| D-043 (Three layers) | Each layer authored independently from different fact subsets. | Prevents conflation of axioms, biography, and behavior. |
| D-044 (Scoped) | Only personal-scope facts feed identity blocks. | Prevents project language from contaminating personal identity. |
| D-089 (Domain guard) | 73-word guard in all prompts: "How someone reasons IS identity. What they reason ABOUT is not." | Eliminates topic skew. H3 prompts adopted after 4-round, 10-condition ablation. |
| D-093 (Structured output) | Validated structured output format for PREDICTIONS. | Enables downstream parsing for serving layer activation matching. |

**Script:** `src/baselayer/author_layers.py`

**Output:** Three markdown files in `data/identity_layers/`:
- `anchors_v4.md` — epistemic axioms
- `core_v4.md` — operational constraints
- `predictions_v4.md` — behavioral predictions

Each file has a metadata header above `---` and injectable text below.

---

## Step 5: Compose

Compresses the three authored layers into a single unified brief (3-6K tokens) using Opus API. The unified brief is the primary artifact — what gets injected into any AI's system prompt.

**Compose constraints:**
- D-091 (Compose domain guard): prevents topic-specific content from reassembling even when individual layers are domain-agnostic.
- D-092 (Universal they/them): enforces gender-neutral pronouns across all subjects.
- Quality gate: `extract_required_terms()` + `verify_brief_completeness()` + compose-verify loop.

**Script:** `src/baselayer/agent_pipeline.py`

**Output:** `data/identity_layers/brief_v4.md` — the unified brief. This is the file that gets served.

---

## Serving: MCP Server

The brief is served via Model Context Protocol (MCP) as an always-on identity Resource. No LLM in the serving path — pure file read.

**Script:** `src/baselayer/mcp_server.py`

**Capabilities:**

| Type | Name | Function |
|------|------|----------|
| Resource | Identity | Returns the unified brief for injection into system prompt |
| Tool | `recall` | Retrieves facts relevant to a query via vector similarity |
| Tool | `search` | Full-text keyword search across facts |
| Tool | `trace_claim` | Given an identity claim, returns source facts with similarity scores |
| Tool | `verify_claims` | Runs binary verification questions against the database |

**Runtime data flow:**

```
User message arrives
    |
    v
MCP server loads unified brief from brief_v4.md (~0ms, file read)
    |
    v
Claude API receives: system prompt with brief + user message
    |
    v
Response returned to user
```

No embedding, no vector retrieval, no LLM call in the serving path. The brief is a static file.

---

## Fact Schema

The `memory_facts` table is the central data store. Understanding this schema is essential for modifying extraction or authoring.

```sql
CREATE TABLE memory_facts (
    id TEXT PRIMARY KEY,
    fact_text TEXT NOT NULL,         -- reconstructed as "{subject} {predicate} {object}"
    category TEXT,                   -- 'preference', 'biography', 'project', etc.
    confidence REAL,
    source_conversation_id TEXT,
    created_at REAL,
    updated_at REAL,
    superseded_by TEXT,              -- tracks contradictions/updates (never deleted)
    source TEXT,                     -- 'extraction', 'manual', etc.
    subject TEXT,                    -- entity this fact is about
    temporal_state TEXT,             -- 'current', 'past', 'unknown'
    scope TEXT,                      -- 'personal', 'project', 'professional' (D-044)
    fact_type TEXT,                  -- 'biographical', 'behavioral', 'positional', 'preference'
    commitment_depth TEXT,           -- 'factual', 'preference', 'position', 'conviction'
    predicate TEXT,                  -- constrained verb from 47 CONSTRAINED_PREDICATES
    object_text TEXT,                -- structured object field
    qualifier TEXT                   -- temporal/conditional context
);
```

**Fact classification (4 dimensions used in authoring):**

| Dimension | Values | Routes To |
|-----------|--------|-----------|
| `fact_type` | biographical, behavioral, positional, preference | Determines which layer receives the fact |
| `commitment_depth` | factual, preference, position, conviction | Conviction-level facts -> ANCHORS candidates |
| `scope` | personal, project, professional | Only `personal` feeds identity layers (D-044) |
| `temporal_state` | current, past, unknown | Past facts excluded from active brief |

**Additional tables:**

| Table | Purpose |
|-------|---------|
| `fact_relationships` | Co-occurrence edges between facts extracted from the same conversation |
| `layer_claim_provenance` | Links identity claims to supporting facts with similarity scores |
| `claim_verification` | Binary verification questions per claim (existence, recurrence, temporal) |
| `memory_facts_fts` | FTS5 virtual table for full-text search on fact_text |

---

## Provenance

Every claim in an identity layer traces to source facts. Provenance is captured at authoring time: fact IDs (`[F-xxx]`) are embedded in generation prompts, and `parse_provenance_from_layer()` extracts citations from generated markdown. The `layer_claim_provenance` table stores these links.

**Verification operates in two modes:**
- **Vector audit:** Embeds each claim, computes similarity against all facts, reports which claims have weak support.
- **Claim verification:** Generates binary yes/no questions per claim (existence, recurrence, cross-domain, temporal consistency), executable against the database.

**Access points:**
- `baselayer provenance` — summary + `--claim ID` trace
- `baselayer verify` — vector audit + claim verification
- `trace_claim` MCP tool — on-demand annotation

**Script:** `src/baselayer/verify_provenance.py`

---

## Model Roles

| Model | Step | Role | Typical Cost |
|-------|------|------|-------------|
| **Haiku** (API) | Extract | Structured fact extraction, 47 predicates | ~$0.10-0.50/corpus |
| **MiniLM-L6-v2** (local) | Embed | 384-dim vectors for provenance | $0 |
| **Sonnet** (API) | Author | Three-layer identity generation | ~$0.05-0.15 |
| **Opus** (API) | Compose | Compress 3 layers -> unified brief | ~$0.05-0.15 |
| **Pure code** | Serve | Load and serve final brief via MCP | $0 |

**Total cost per subject:** ~$0.30-2.00 depending on corpus size. `baselayer estimate` previews exact cost before spending anything.

**Local extraction option:** Set `BASELAYER_EXTRACTION_BACKEND=ollama` to run extraction through a local model (Mistral 7B tested best for extraction quality). Authoring and composition still require Claude API.

---

## Multi-User and Data Isolation

**Data isolation:** Set `MEMORY_SYSTEM_ROOT` to redirect all data paths to a different directory. Scripts stay shared; only data changes.

```bash
export MEMORY_SYSTEM_ROOT=/path/to/user_b_memory
baselayer extract    # reads/writes user_b_memory/data/...
baselayer author     # generates for User B's data
```

**Database initialization:** `baselayer init` creates all tables for a new user.

**Entity maps:** Per-user `entity_map.json` in the data root provides name-to-canonical-entity resolution (e.g., "wife" -> "spouse:[name]"). Referenced at extraction runtime.

**Prompt generalization:** All extraction and authoring prompts are person-agnostic. No hardcoded names or person-specific examples.

**Validation (N=57+):**

| Subject | Source | Facts | Brief Size | Score |
|---------|--------|-------|------------|-------|
| User A | 1,892 conversations | 4,610 | 9,642 chars | 78.5 |
| User B | 36 newsletter posts | 309 | -- | 77.7 |
| User C | 9 journal entries | 76 | -- | 81.7 |
| Franklin | Autobiography (21 ch.) | 212 | 9,144 chars | 75 |
| Douglass | Autobiography | 88 | 5,939 chars | 73 |
| Wollstonecraft | Published treatise | 95 | 9,110 chars | 78 |
| Roosevelt | Autobiography | 398 | 8,439 chars | 82 |
| Patent corpus | 30 US patents | 670 | 7,463 chars | 80 |
| Buffett | 48 shareholder letters | 505 | 7,173 chars | 78 |
| Marks | 74 investment memos | 723 | 14,241 chars | 81 |

Scores are from the original 10-subject validation. 47 additional subjects have been modeled through the H3 prompt set without individual scoring.

---

## Design Decisions (Key Subset)

93 design decisions are logged in `docs/core/DECISIONS.md`. The ones most relevant to understanding the architecture:

| ID | Decision | Rationale |
|----|----------|-----------|
| D-007 | Turn-pair embeddings as primary retrieval unit | Individual messages like "yes" carry no meaning. User+assistant pairs are richer semantic units. |
| D-013 | Associative fact retrieval via co-occurrence | Facts extracted from the same conversation get linked. Retrieving one boosts related facts. |
| D-015 | Data-driven significance over LLM judgment | Recurrence + depth metrics matter more than which model scores them. All models improved equally when given these signals. |
| D-026 | 10 universal identity clusters for fact grouping | Asking "what are the best facts about X?" outperforms composite scoring across all facts. |
| D-040 | Blind derivation (no prior output in prompts) | Showing prior blocks causes 26% anchoring. Each regeneration starts from facts only. |
| D-043 | Three-layer architecture (ANCHORS/CORE/PREDICTIONS) | Separates axioms, biography, and behavior. Each layer authored from different facts with different prompts and different update cadences. |
| D-044 | Scoped memory (personal/project/professional) | Prevents project language from contaminating personal identity. |
| D-046 | Sonnet generates, Opus reviews | Cheap constraint (Sonnet), expensive discrimination (Opus). Prompt quality is the leverage point. |
| D-056 | Structured extraction schema (47 predicates) | Replaced free-text extraction that caused 30x recurrence inflation. |
| D-089 | Domain-agnostic guard (73 words) | Eliminates topic skew. "How someone reasons IS identity. What they reason ABOUT is not." |
| D-091 | Compose domain guard | Prevents topic-specific content from reassembling in the unified brief. |
| D-092 | Universal they/them pronouns | Gender-neutral across all subjects in composed brief. |

---

## Cold Start

| User Profile | Path to Brief | Status |
|---|---|---|
| Has conversation history (ChatGPT/Claude exports) | `baselayer run export.zip` -> identity in ~30 min | Works today |
| Has journals or notes | `baselayer run ~/journals/` -> identity via document mode | Works today |
| Has nothing | `baselayer journal` -> guided prompts -> bootstrap extraction | Works today |

Journal input produces higher-quality identity facts per entry than conversation history. Journals are self-reflective (higher signal-to-noise); conversations are reactive. User C's 76 journal-derived facts scored 81.7 — higher than User A's 4,610 conversation-derived facts at 78.5.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Ground truth DB | SQLite | Conversation + fact storage |
| Vector store | ChromaDB (L2 distance) | Provenance tracing, semantic search |
| Embedding model | all-MiniLM-L6-v2 | 384-dim local embeddings |
| Extraction | Haiku API (default) or Ollama | Structured fact extraction |
| Layer generation | Sonnet API | Three-layer identity authoring |
| Brief composition | Opus API | Unified brief compression |
| Serving | MCP (Model Context Protocol) | Identity injection at runtime |
| Language | Python 3.10+ | All scripts and pipelines |
| Package | `pip install baselayer` | CLI with 25 subcommands |

---

## File Structure

```
memory_system/
+-- pyproject.toml                     # Package config (pip install baselayer)
+-- README.md                          # Quick-start guide
+-- src/baselayer/                     # Canonical source location
|   +-- cli.py                         # CLI entry (baselayer command, 25 subcommands)
|   +-- config.py                      # Shared constants (single source of truth)
|   +-- import_conversations.py        # Step 1: Multi-source importer
|   +-- extract_facts.py              # Step 2: AUDN fact extraction (Haiku/Ollama)
|   +-- embed.py                       # Step 3: Vector embeddings
|   +-- author_layers.py              # Step 4: Three-layer authoring
|   +-- agent_pipeline.py             # Step 5: Unified brief composition
|   +-- mcp_server.py                 # MCP server (identity + tools)
|   +-- api_client.py                 # Centralized API singleton + retry
|   +-- verify_provenance.py          # Provenance audit + claim verification
|   +-- checkpoint.py                 # Pipeline quality gate reports
|   +-- assemble_brief.py             # Brief assembly (runtime context building)
|   +-- batch_extract.py              # Batch API extraction (50% cost reduction)
|   +-- llm_provider.py               # Multi-provider LLM abstraction
|   +-- init_database.py              # Initialize databases for new users
|   +-- semantic_search.py            # Meaning-based search interface
+-- data/
|   +-- raw/                           # Source text (ChatGPT exports, etc.)
|   +-- database/memory.db             # SQLite (conversations + facts)
|   +-- vectors/                       # ChromaDB embeddings
|   +-- identity_layers/               # Authored layers + unified brief
|       +-- anchors_v4.md
|       +-- core_v4.md
|       +-- predictions_v4.md
|       +-- brief_v4.md               # The unified brief (primary artifact)
+-- tests/                             # 402 tests
+-- docs/
|   +-- core/                          # Architecture, decisions, principles
|   +-- eval/                          # Benchmarks, ablation studies, eval frameworks
|   +-- research/                      # Philosophy of identity, axiom hypotheses
|   +-- reviews/                       # Security, contamination, temporal processing
+-- agents/                            # Agent definitions (ANCHORS, CORE, PREDICTIONS)
```

---

## Serving Layer (Specced, Not Built)

The current serving path injects the full brief every turn. The specced serving layer adds activation matching: scoring brief sections against conversation context, ranking by relevance, injecting top-K. This reduces token cost for long conversations and surfaces the most relevant identity constraints per turn.

**Spec:** `docs/core/SERVING_LAYER_SPEC.md`
**Eval:** `docs/eval/SERVING_LAYER_EVAL.md` — 5 conditions, 30 prompts, ~$2.25. Must run before architecture decision.
**Status:** Specced, not implemented.

---

## Key Research Findings

From 101+ sessions of experimentation:

1. **20% of facts is enough for identification.** Compression saturates early. More content degrades quality.
2. **What you avoid predicts better than what you believe.** Avoidance and struggle patterns are the strongest behavioral predictors.
3. **Format matters more than content.** The same information in annotated guide format outperforms narrative prose by 24%.
4. **Most pipeline steps are ceremonial.** 4 steps scored 87/100. Full 14-step scored 83/100. But the 3-layer architecture IS load-bearing.
5. **Domain guard eliminates topic skew.** A 73-word instruction in authoring prompts completely prevents the model from anchoring to domain-specific content.
6. **Journal input outperforms conversation history per-fact.** Self-reflective text has higher signal-to-noise for behavioral extraction.
7. **Compression amplifies signal.** Twin-2K (N=100): compressed brief (71.83%) beats full persona (71.72%) at 18:1 compression ratio (p=0.008).
