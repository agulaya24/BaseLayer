# System Architecture
## Base Layer: An Interpretive Layer Above Memory
**Updated 2026-05-06**

---

## The Problem

The leading AI memory systems (Mem0, Letta, Supermemory, Zep) optimize for recall. On standard recall benchmarks (LOCOMO, LongMemEval) they score in the 70 to 93 percent range. Recall is approaching solved.

What they do not measure is interpretation: how a specific person processes facts and experiences into judgments, decisions, and reactions. The same set of facts can yield entirely different conclusions depending on whose interpretive framework reads them. For an AI to act on behalf of a specific person, it needs that framework, not just the facts.

Stored facts and stated preferences are surface artifacts of an underlying interpretive layer. Provider-side user models (ChatGPT Memory, Claude Projects) are opaque, non-portable, and non-inspectable. As agents gain autonomy and take actions on behalf of humans, a missing interpretive model compounds: the agent does not give a bad answer, it acts on a wrong assumption.

Larger context windows do not solve this. Raw conversation history is retrieval, not interpretation. The agent still has no model of how the person reasons or what they prioritize.

**Why this is operationally consequential.** An AI agent can only act in alignment with how a specific person would act to the extent it represents how they reason. Without that representation, the agent's actions revert to the population average; the more autonomy it has, the wider the gap compounds.

## The Solution

Base Layer compresses text (conversations, journals, essays, any personal writing) into a portable behavioral specification. The specification is a 5,000 to 10,000 token structured document that captures the recurring patterns in how a specific person reasons, communicates, and decides. Inject the specification into any AI and it operates within the person's interpretive constraints rather than guessing.

The specification composes with retrieval rather than replacing it. For interpretation-heavy questions where retrieved facts underdetermine the answer, the specification supplies the pattern that has to transfer to the new situation. For pure recall questions, retrieval alone is sufficient. The architecture documented below produces the specification; how it composes with retrieval at serving time is described in the final section.

Output is locally owned, provenance-traced to source text, and provider-agnostic. The specification format is the primary artifact. The pipeline that produces it is the rest of this document.

---

## Pipeline Overview (5 Steps)

Pipeline ablation (Session 79, 14 conditions) confirmed that 10 of the original 14 processing steps were ceremonial. The simplified pipeline scores higher (87/100 vs 83/100). The three-layer architecture is load-bearing; the intermediate processing steps (scoring, classification, tiering, contradiction detection) are not. Cut. See `docs/eval/ablation/`.

Authoring supersession: Step 4 in the 5-step pipeline is superseded by Interpretive Distillation. The 5-step pipeline below remains what `baselayer author` runs today and must stay documented. Steps 1, 2, 3 and 5 are unchanged in function. Step 4 is marked as superseded, with the current authoring architecture defined in Step 4 details.

```
                    BASE LAYER PIPELINE
 +--------------------------------------------------------------+
 |                                                              |
 |   STEP 1: IMPORT                                             |
 |   +--------------------------------------------------------+ |
 |   | Multi-source importer (ChatGPT, Claude, journals, text)| |
 |   | -> SQLite (conversations + messages)                   | |
 |   +-------------------------+------------------------------+ |
 |                             |                                |
 |   STEP 2: EXTRACT           v                                |
 |   +--------------------------------------------------------+ |
 |   | Haiku API -- 46 constrained predicates                 | |
 |   | Text -> {subject, predicate, object, qualifier} triples| |
 |   | AUDN (Add, Update, Delete, Noop) fact lifecycle        | |
 |   +-------------------------+------------------------------+ |
 |                             |                                |
 |   STEP 3: EMBED             v                                |
 |   +--------------------------------------------------------+ |
 |   | MiniLM-L6-v2 -- local vector embeddings                | |
 |   | ChromaDB storage for semantic search, verify,          | |
 |   | and provenance fallback                                | |
 |   +-------------------------+------------------------------+ |
 |                             |                                |
 |   STEP 4: AUTHOR            v                                |
 |   +--------------------------------------------------------+ |
 |   | Sonnet -- Three-layer generation (D-043)               | |
 |   | H3 prompts: domain-agnostic guard (D-089, S99 ablation)| |
 |   | ANCHORS | Epistemic axioms                             | |
 |   | CORE    | Operational constraints                      | |
 |   | PREDICT | Situation -> pattern -> directive            | |
 |   | [Superseded by Interpretive Distillation]              | |
 |   +-------------------------+------------------------------+ |
 |                             |                                |
 |   STEP 5: COMPOSE           v                                |
 |   +--------------------------------------------------------+ |
 |   | Opus -- Compress 3 layers -> specification (5-10K tok) | |
 |   | They/them pronouns enforced (D-092)                    | |
 |   | Domain-agnostic guard (D-091)                          | |
 |   | Served via MCP as always-on specification Resource     | |
 |   +--------------------------------------------------------+ |
 |                                                              |
 +--------------------------------------------------------------+
                                |
                                v
                   +----------------------------+
                   |   REASONING MODEL          |
                   |   Claude API (stateless)   |
                   |   Receives specification + |
                   |   user message             |
                   +----------------------------+
```

**One command:** `baselayer run <file>` runs steps 1 through 5 with a cost estimate gate before spending anything.

**Runner note.** Embeddings are not read by the authoring step. Authoring reads facts from SQLite via SQL. ChromaDB serves semantic search, `verify`, and provenance fallback only. The `baselayer run` one-command path runs Import, Extract, Author, Compose, then performs Embed together with tiering and verification in a post-compose traceability phase. Step-by-step usage can still run `baselayer embed` at any time, but it is not semantically between `extract` and `author`. Both paths produce the same final artifacts. The logical stage semantics treat Embed as independent of Author for generation, and as a dependency only for verification and vector-provenance fallback.

---

## Step 1: Import

Ingests text from multiple source formats into a normalized SQLite schema. Incremental: re-running on the same export skips already-imported conversations.

**Supported sources:** ChatGPT JSON export, Claude Code sessions, Claude.ai web export, plain text files, directories of text files, journal entries.

**Script:** `src/baselayer/import_conversations.py`

**Schema:**

| Table | Columns | Purpose |
|-------|---------|---------|
| `conversations` | id, title, created_at, updated_at, message_count, source | One row per conversation or document |
| `messages` | id, conversation_id, parent_id, role, content_text, created_at, sequence_order | One row per message or text chunk |

For non-conversation text (autobiographies, patents, essays), use `--document-mode`. The importer treats the entire document as a single conversation with the text as one message.

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

**Output format:** `{subject, predicate, object, qualifier}` triples. The 46 constrained predicates, 45 behavioral plus an `unknown` fallback (owns, values, practices, fears, excels_at, relates_to, collaborates_with, and others; see `CONSTRAINED_PREDICATES` in `config.py`), enforce keyword-rich, structured output. `normalize_predicate()` maps LLM variants to canonical forms. This structured format replaced free-text extraction after discovering that generic language ("The user is interested in X") inflated recurrence counts by 30x (D-056).

**Text chunking:** Long texts exceeding `input_char_budget` are auto-chunked on paragraph boundaries with 500-char overlap. Character tiers: 0-12K chars yields 10 facts max, 12K-30K yields 20, 30K-60K yields 35, 60K+ yields 50. Per-chunk cap: 15 facts. AUDN dedup handles cross-chunk duplication.

**Anonymization:** `author_layers.py` replaces subject names with "this person" before any model sees data. All extraction prompts include a "DERIVE ONLY FROM INPUT" constraint.

**Script:** `src/baselayer/extract_facts.py`

**Re-extraction requirement:** Clearing extraction data requires deleting BOTH SQLite rows (`memory_facts` plus `extraction_log`) AND the ChromaDB collection. Without clearing ChromaDB, old vectors cause AUDN to NOOP on legitimate new facts.

---

## Step 3: Embed

Generates vector embeddings of extracted facts using MiniLM-L6-v2 (384 dimensions, runs locally). Stored in ChromaDB. Used for semantic search, verification, and provenance fallback when authored text does not contain explicit citations.

**Collections do not share a distance space, so read it before converting a distance.** `memory_facts` is created with `hnsw:space=cosine`, where similarity is `1 - dist`. `messages`, `turn_pairs` and `conversation_summaries` are left at Chroma's l2 default, where similarity is `1 - dist^2/2`. Use `collection_space()` and pass the result to `chromadb_dist_to_similarity()`, which requires it. Applying one formula to both was a live defect: on a cosine collection it inflated similarity by about 0.47 and passed a 0.85 gate whose true value was 0.45.

**Script:** `src/baselayer/embed.py`

---

## Step 4: Author

The shipped Step 4 generates the three specification layers from extracted facts. This shipped step remains in `baselayer author` and is documented below, but it is superseded at the architecture level by Interpretive Distillation, which is the current authoring architecture.

### Current Authoring Architecture: Interpretive Distillation

Interpretive Distillation replaces the monolithic authoring pass with three stages that record a verdict for every fact.

- DISTILL: Every fact -> a tree of leaves, four channels per chunk.
  - THEMES: What recurs, each theme names the fact IDs it drew on.
  - SINGULARITIES: Facts that appear once and would change the model of the person. Carried verbatim, never paraphrased or merged.
  - CONTRADICTIONS: Kept, never resolved.
  - DISPOSITIONS: Every fact ID receives exactly one verdict: theme, singular, or not_load_bearing. Omitting an ID is not permitted.

- ASSEMBLE: One or more trees -> a stratified package.

- AUTHOR: Package -> the three layers, with citations mandatory by schema.

Why this replaced the old author step:
- The shipped author reads a SQL selection capped at 15 facts per category (`MAX_FACTS_PER_CATEGORY`, `author_layers.py:307`). Measured, that discards about 65% of the CORE layer's corpus, and it cuts by sort position rather than importance. This cap appears in none of the recorded decisions. Distillation gives every fact a recorded verdict instead.

Data access:
- Distillation reads this project's database directly. It requires `memory_facts` with the fields `id`, `fact_text`, `predicate`, `category`, and `superseded_by`. No adapter is needed.

Status:
- Distillation is an experimental release in a separate repository. It is not heavily tested: its suite is 10 mutation tests over one audit and does not exercise its other modules, and most of its measurements were taken on a single 407-fact corpus. Access is by request. No URL is included here.

Compatibility:
- The 5-step pipeline remains what `baselayer author` runs today. Steps 1, 2, 3 and 5 are unchanged. Step 4 here is the shipped path and remains documented for operational continuity.

### Three-Layer Specification Architecture (D-043)

| Layer | Input Facts | Content | Update Cadence |
|-------|------------|---------|----------------|
| **ANCHORS** | Conviction-level facts, confirmed axioms | Epistemic axioms that pre-define how the model should weigh competing interpretations | Rare (axioms change slowly) |
| **CORE** | Identity-tier biographical and behavioral facts | Communication patterns, operating modes, relationships, career context | When life circumstances change |
| **PREDICTIONS** | Behavioral plus conviction/position facts | Situation -> pattern -> directive. "When X happens, this person tends to Y. Do Z." | As behavior evolves |

**Concrete example of each layer:**

```
ANCHORS -- The axioms you reason from.

  COHERENCE
  If your response contains internal inconsistency, flag it before
  presenting it. They will detect it and trust you less for not
  catching it first.

PREDICTIONS -- Behavioral patterns with triggers and directives.

  ANALYSIS-PARALYSIS SPIRAL
  Trigger: A high-stakes decision with multiple valid options.
  Directive: "The decision on the table is X. Your analysis would
  change the decision if Y. Is Y still plausible?"

CORE -- How you operate. Communication patterns, context modes.
```

### Authoring Constraints

These are the load-bearing design decisions that prevent the most common failure modes:

| Decision | Rule | Why |
|----------|------|-----|
| D-040 (Blind derivation) | Facts-only input. No prior blocks, no analysis docs, no inherited text. | Showing prior output to Sonnet causes 26% anchoring bias. |
| D-041 (Audience = AI) | Every sentence must change LM behavior. No philosophy framework names in output. | The specification teaches an AI, not describes a person. |
| D-043 (Three layers) | Each layer authored independently from different fact subsets. | Prevents conflation of axioms, biography, and behavior. |
| D-044 (Scoped) | Only personal-scope facts feed the specification layers. | Prevents project language from contaminating personal patterns. |
| D-053 (No prior layer leakage) | Sonnet does not see prior layer output during regeneration. No Collective evaluation artifacts in generation prompts. | Blind regeneration only. Prior output anchors the next pass. |
| D-089 (Domain guard) | 73-word guard in all prompts: "How someone reasons IS identity. What they reason ABOUT is not." | Eliminates topic skew. H3 prompts adopted after 4-round, 10-condition ablation. |
| D-093 (Structured output) | Validated structured output format for PREDICTIONS. | Enables downstream parsing for serving layer activation matching. |

**Script:** `src/baselayer/author_layers.py`

**Output:** Three markdown files in `data/identity_layers/`:
- `anchors_v4.md`: epistemic axioms
- `core_v4.md`: operational constraints
- `predictions_v4.md`: behavioral predictions

Each file has a metadata header above `---` and injectable text below.

---

## Step 5: Compose

Compresses the three authored layers into a single specification (5,000 to 10,000 tokens) using Opus API. The specification is the primary artifact: what gets injected into any AI's system prompt.

**Compose constraints:**
- D-091 (Compose domain guard): prevents topic-specific content from reassembling even when individual layers are domain-agnostic.
- D-092 (Universal they/them): enforces gender-neutral pronouns across all subjects.
- Quality gate: `extract_required_terms()` plus `verify_brief_completeness()` plus a compose-verify loop.

**Script:** `src/baselayer/agent_pipeline.py`

**Output:** `data/identity_layers/brief_v4.md` is the specification file. This is the artifact that gets served. The filename uses the legacy `brief_v4.md` name; the artifact itself is the specification.

---

## Serving: MCP Server

The specification is served via Model Context Protocol (MCP) as an always-on specification Resource. No LLM in the serving path: pure file read.

**Script:** `src/baselayer/mcp_server.py`

**Capabilities:**

| Type | Name | Function |
|------|------|----------|
| Resource | `memory://specification` | Returns the structural specification (CORE + ANCHORS + PREDICTIONS) for injection into the system prompt. `memory://identity` is a deprecated alias. |
| Tool | `get_brief` | Unified narrative brief (~3,000 tokens), fetched on demand |
| Tool | `recall_memories` | Retrieves facts relevant to a query via vector similarity |
| Tool | `search_facts` | Full-text keyword search across facts |
| Tool | `trace_claim` | Given a claim, returns source facts with similarity scores |
| Tool | `verify_claims` | Runs binary verification questions against the database |
| Tool | `get_stats` / `get_call_log` / `get_help` | Database summary, session call log, agent reference |

**Runtime data flow:**

```
User message arrives
    |
    v
MCP server loads specification from brief_v4.md (~0ms, file read)
    |
    v
Claude API receives: system prompt with specification + user message
    |
    v
Response returned to user
```

No embedding, no vector retrieval, no LLM call in the serving path. The specification is a static file.

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
    predicate TEXT,                  -- constrained verb from the 46 CONSTRAINED_PREDICATES
    object_text TEXT,                -- structured object field
    qualifier TEXT                   -- temporal/conditional context
);
```

**Fact classification (4 dimensions used in authoring):**

| Dimension | Values | Routes To |
|-----------|--------|-----------|
| `fact_type` | biographical, behavioral, positional, preference | Determines which layer receives the fact |
| `commitment_depth` | factual, preference, position, conviction | Conviction-level facts route to ANCHORS candidates |
| `scope` | personal, project, professional | Only `personal` feeds identity layers (D-044) |
| `temporal_state` | current, past, unknown | Past facts excluded from active specification |

**Additional tables:**

| Table | Purpose |
|-------|---------|
| `fact_relationships` | Co-occurrence edges between facts extracted from the same conversation |
| `layer_claim_provenance` | Links authored claims to supporting facts with similarity scores |
| `claim_verification` | Binary verification questions per claim (existence, recurrence, temporal) |
| `memory_facts_fts` | FTS5 virtual table for full-text search on fact_text |

---

## Provenance

Every claim in a specification layer is traceable to source facts. Provenance is captured at or after authoring time by two distinct methods. These methods must not be conflated.

### Citation-first provenance

- During authoring, fact IDs (`[F-xxx]`) are embedded in generation prompts.
- If authored text includes citations, `parse_provenance_from_layer()` extracts them from the generated markdown.
- The `layer_claim_provenance` table stores these links, including per-link similarity scores when computed and the recorded method when present.

This is a direct link asserted by the model through explicit citation.

### Synthesis layers and vector fallback

- ANCHORS and PREDICTIONS synthesise rather than quote. The citation pass often returns nothing for these layers.
- In that case, `author_layers.py:2073` falls back to `generate_vector_provenance`, which embeds the claim and links nearest facts with `link_method='vector'`.
- This is embedding proximity, not a link the model asserted. The `trace_claim` tool prints the method per row so consumers can distinguish citation from vector fallback.

ChromaDB and embeddings exist for this fallback, for `verify`, and for semantic search. The author does not read from ChromaDB.

### Verification

Verification operates in two modes:
- Vector audit: Embeds each claim, computes similarity against all facts, reports which claims have weak support.
- Claim verification: Generates binary yes or no questions per claim (existence, recurrence, cross-domain, temporal consistency), executable against the database.

**Access points:**
- `baselayer provenance`: summary plus `--claim ID` trace
- `baselayer verify`: vector audit plus claim verification
- `trace_claim` MCP tool: on-demand annotation

**Script:** `src/baselayer/verify_provenance.py`

The shipped audit is a strong data-quality check, not a causal-traceability guarantee. Vector proximity, recurrence gating, cross-domain span, and NLI entailment together flag unsupported or single-domain claims. Cross-domain synthesis claims can score lower than they should because no single fact contains the synthesis. This limitation is documented in `verify_provenance.py`.

---

## Model Roles

| Model | Step | Role | Typical Cost |
|-------|------|------|-------------|
| **Haiku** (API) | Extract | Structured fact extraction, 46 constrained predicates | ~$0.10-0.50/corpus |
| **MiniLM-L6-v2** (local) | Embed | 384-dim vectors for search, verify, and vector provenance fallback | $0 |
| **Sonnet** (API) | Author | Three-layer generation | ~$0.05-0.15 |
| **Opus** (API) | Compose | Compress 3 layers into specification | ~$0.05-0.15 |
| **Pure code** | Serve | Load and serve final specification via MCP | $0 |

Total cost per subject includes only the shipped 5-step pipeline. The current authoring architecture, Interpretive Distillation, runs in a separate repository and is experimental.

**Total cost per subject:** ~$0.30 to $2.00 depending on corpus size. `baselayer estimate` previews exact cost before spending anything.

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

**Validation reference:**

| Subject | Source | Facts | Spec Size | Score |
|---------|--------|-------|-----------|-------|
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

Scores are from the original 10-subject validation. Additional subjects have been modeled through the H3 prompt set without individual scoring.

---

## Design Decisions (Key Subset)

90+ design decisions are logged in `docs/core/DECISIONS.md`. The ones most relevant to understanding the architecture:

| ID | Decision | Rationale |
|----|----------|-----------|
| D-007 | Turn-pair embeddings as primary retrieval unit | Individual messages like "yes" carry no meaning. User+assistant pairs are richer semantic units. |
| D-013 | Associative fact retrieval via co-occurrence | Facts extracted from the same conversation get linked. Retrieving one boosts related facts. |
| D-015 | Data-driven significance over LLM judgment | Recurrence and depth metrics matter more than which model scores them. All models improved equally when given these signals. |
| D-026 | 10 universal identity clusters for fact grouping | Asking "what are the best facts about X?" outperforms composite scoring across all facts. |
| D-040 | Blind derivation (no prior output in prompts) | Showing prior blocks causes 26% anchoring. Each regeneration starts from facts only. |
| D-043 | Three-layer architecture (ANCHORS/CORE/PREDICTIONS) | Separates axioms, biography, and behavior. Each layer authored from different facts with different prompts and update cadences. |
| D-044 | Scoped memory (personal/project/professional) | Prevents project language from contaminating personal identity. |
| D-046 | Sonnet generates, Opus reviews | Cheap constraint (Sonnet), expensive discrimination (Opus). Prompt quality is the leverage point. |
| D-053 | No prior layer leakage in regeneration | Blind regeneration only. No Collective evaluation artifacts feed into generation prompts. |
| D-056 | Structured extraction schema (46 constrained predicates) | Replaced free-text extraction that caused 30x recurrence inflation. |
| D-089 | Domain-agnostic guard (73 words) | Eliminates topic skew. "How someone reasons IS identity. What they reason ABOUT is not." |
| D-091 | Compose domain guard | Prevents topic-specific content from reassembling in the specification. |
| D-092 | Universal they/them pronouns | Gender-neutral across all subjects in the composed specification. |

---

## Cold Start

| User Profile | Path to Specification | Status |
|---|---|---|
| Has conversation history (ChatGPT/Claude exports) | `baselayer run export.zip` produces specification in ~30 min | Works today |
| Has journals or notes | `baselayer run ~/journals/` produces specification via document mode | Works today |
| Has nothing | `baselayer journal` runs guided prompts to bootstrap extraction | Works today |

Journal input produces higher-quality behavioral facts per entry than conversation history. Journals are self-reflective (higher signal-to-noise); conversations are reactive. User C's 76 journal-derived facts scored 81.7, higher than User A's 4,610 conversation-derived facts at 78.5.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Ground truth DB | SQLite | Conversation and fact storage |
| Vector store | ChromaDB (cosine for facts, l2 for messages) | Semantic search, verification, provenance fallback |
| Embedding model | all-MiniLM-L6-v2 | 384-dim local embeddings |
| Extraction | Haiku API (default) or Ollama | Structured fact extraction |
| Layer generation | Sonnet API | Three-layer authoring (shipped pipeline) |
| Specification composition | Opus API | Three-layer compression |
| Serving | MCP (Model Context Protocol) | Specification injection at runtime |
| Language | Python 3.10+ | All scripts and pipelines |
| Package | `pip install git+https://github.com/agulaya24/BaseLayer.git` | CLI with 25 subcommands. Not on PyPI. |

---

## File Structure

```
memory_system/
+-- pyproject.toml                     # Package config (install via git URL; not on PyPI)
+-- README.md                          # Quick-start guide
+-- src/baselayer/                     # Canonical source location
|   +-- cli.py                         # CLI entry (baselayer command, 25 subcommands)
|   +-- config.py                      # Shared constants (single source of truth)
|   +-- import_conversations.py        # Step 1: Multi-source importer
|   +-- extract_facts.py               # Step 2: AUDN fact extraction (Haiku/Ollama)
|   +-- embed.py                       # Step 3: Vector embeddings
|   +-- author_layers.py               # Step 4: Three-layer authoring
|   +-- agent_pipeline.py              # Step 5: Specification composition
|   +-- mcp_server.py                  # MCP server (specification + tools)
|   +-- api_client.py                  # Centralized API singleton + retry
|   +-- verify_provenance.py           # Provenance audit + claim verification
|   +-- checkpoint.py                  # Pipeline quality gate reports
|   +-- assemble_brief.py              # Specification assembly (runtime context building)
|   +-- batch_extract.py               # Batch API extraction (50% cost reduction)
|   +-- llm_provider.py                # Multi-provider LLM abstraction
|   +-- init_database.py               # Initialize databases for new users
|   +-- semantic_search.py             # Meaning-based search interface
+-- data/
|   +-- raw/                           # Source text (ChatGPT exports, etc.)
|   +-- database/memory.db             # SQLite (conversations + facts)
|   +-- vectors/                       # ChromaDB embeddings
|   +-- identity_layers/               # Authored layers + specification
|       +-- anchors_v4.md
|       +-- core_v4.md
|       +-- predictions_v4.md
|       +-- brief_v4.md                # The specification (primary artifact)
+-- tests/                             # 451 tests
+-- docs/
|   +-- core/                          # Architecture, decisions, principles
|   +-- eval/                          # Benchmarks, ablation studies, eval frameworks
```

---

## Serving Layer

The current (0.4.0) MCP design serves the full structural specification inline. The always-on `memory://specification` resource returns CORE, ANCHORS, and PREDICTIONS (~6 to 8K tokens) plus a manifest of supplementary tools. Only the unified narrative brief stays on demand, behind `get_brief(reason)`.

History: the 0.3.0 release shipped a partial-serving design that put only CORE on the resource and exposed ANCHORS and PREDICTIONS behind on-demand `get_anchors()`/`get_predictions()` tools. Live use surfaced two issues: the model had to make routing decisions about layers it could not see, and the token savings were negligible. 0.4.0 removed those tools and inlined all three layers.

The manifest's fetch-trigger language for `get_brief` is grounded in the Beyond Recall finding that the specification's largest effect is on interpretation-heavy questions (judgments, decisions, predictions about user behavior), not literal recall. The model is told to fetch when interpreting and to skip when recalling.

A separate, more aggressive design exists in spec form but is not implemented: activation matching, which scores specification sections against the current conversation and injects only the top-K relevant constraints per turn. This is a future direction that complements rather than replaces the inline design.

**Implementation:** `src/baselayer/mcp_server.py`
**Activation-matching spec (future):** `docs/core/SERVING_LAYER_SPEC.md`
**Activation-matching eval (future):** `docs/eval/SERVING_LAYER_EVAL.md`. 5 conditions, 30 prompts. Required before activation-matching can ship.

---

## Composition with Memory Systems

The specification produced by this pipeline is not a memory system. It does not store dated facts, does not retrieve by query, does not maintain a per-conversation working set. Memory systems do those things. The specification is the interpretive layer that sits above them.

A serving system that routes between retrieval and interpretation by question type does not yet exist as a shipped product. The composition pattern below describes how the two layers interact today when both are present.

**Three patterns of interaction:**

1. Retrieval-only questions. The user asks something whose answer is a stored fact. ("What time is my flight on Friday?", "What did I say about the Q3 plan last week?") A memory system supplies the answer directly. The specification adds nothing useful and should be omitted from context. Use retrieval alone.

2. Interpretation-heavy questions. The user asks something whose answer requires applying a pattern to a new situation. ("Should I take the offer?", "Draft a response to this in my voice.", "Is this consistent with what I would actually do?") Retrieved facts underdetermine the answer. The specification supplies the pattern that has to transfer. Layer the specification on top of retrieval.

3. Refusal-triggering questions. The user asks something the specification supports principled refusal on. ("What is my opinion on X topic I have never engaged with?") A naive retrieval system produces hedging or confabulation. The specification produces honest abstention grounded in the person's documented patterns of engagement.

**Empirical note on retrieval divergence.** Given identical input, the four leading memory systems return substantially non-overlapping top-10 facts (mean pairwise overlap 8.3% across ten system pairs). Providers converge on recall scores. They do not converge on which facts matter. Interpretation is a different problem from retrieval, and providers have not yet committed to either.

The specification format is provider-agnostic. The output of `baselayer compose` can be injected into any system prompt, fed into any retrieval-augmented pipeline as a static interpretive layer, or served as an MCP Resource alongside any tool ecosystem. The architecture above is one implementation of that layer, not the only possible one.