# Decision Log
## Personal AI Memory System

Every design decision is recorded here with reasoning. This is the "why" behind the system. If a session ever needs to restart, this file plus `ARCHITECTURE.md` and `PROGRESS.md` gives full context.

---

## How to Read This File

Each decision has:
- **Date:** when we decided
- **Decision:** what we chose (plain English)
- **Why:** the reasoning
- **Alternatives considered:** what we didn't do and why
- **Status:** active, superseded, or revisit-later

---

## Decision Index (Quick Reference)

| ID | Title | Status | Summary |
|---|---|---|---|
| D-001 | Build Custom Instead of Using a Framework | Active | Custom build over Mem0/Letta/Titans frameworks |
| D-002 | Hybrid Local + Cloud Architecture | Active | Qwen local, Claude cloud, brief is bridge |
| D-003 | Three-Tier Memory Brief (~1,500 Tokens) | Active | Identity + themes + episodes in XML brief |
| D-004 | Surprise-Based Memory Scoring | Active | Embedding distance as novelty filter for storage |
| D-005 | AUDN Fact Lifecycle | Active | Add/Update/Delete/Noop for every extracted fact |
| D-006 | Keep Existing Embeddings (all-MiniLM-L6-v2) | Active | Keep 30K embeddings, upgrade later if needed |
| D-007 | Add Turn-Pair Embeddings | Active | Embed user+assistant pairs as single units |
| D-008 | Skip Separate Topic Classifier | Active | Let embedding retrieval determine topic naturally |
| D-009 | Two-Axis Surprise Scoring | Active | Novelty + significance axes; refined by D-015 |
| D-010 | JSON Validation Guardrails for Fact Extraction | Active | Schema validation, retries, low-confidence storage |
| D-011 | Session Buffer for Multi-Turn Conversations | Active | Running buffer of new facts within session |
| D-012 | Semi-Automated Identity Block Updates | Active | System proposes identity updates, user approves |
| D-013 | Lightweight Fact Relationships | Active | Co-occurrence edges for associative retrieval |
| D-014 | Evaluation Framework | Active | 20-case eval harness for brief quality |
| D-015 | Recurrence + Depth as Primary Significance Signals | Active | Frequency and engagement depth drive importance |
| D-016 | Keep Qwen 2.5 14B | Active | Best balance of quality, speed, JSON reliability |
| D-017 | Increased Extraction Limits and Re-Run | Active | 3K->8K chars, 500->1500 tokens, full re-extract |
| D-018 | Simplified Extraction Prompt | Active | Shorter prompt, removed schema enum constraint |
| D-019 | Identity Review v1 | Active | Ground-truth calibration from direct user feedback |
| D-020 | Active Probing | Active | System-initiated questioning to fill knowledge gaps |
| D-021 | Correction Propagation | Active | User corrections as highest authority, fix-once |
| D-022 | Improvement Re-Run | Active | 9 extraction fixes applied in single clean re-run |
| D-023 | Inherent Incompleteness as Design Principle | Active | System can never fully know the person it models |
| D-024 | The Collective | Superseded (S79) | Adversarial multi-perspective review via 4 personas. Proven ceremonial in S79 ablation — C11 (no review) = 87 vs C0 (full) = 83. Removed from default pipeline. |
| D-025 | The Ghost Layer | Superseded | Invisible priors for weighting; replaced by D-026 |
| D-026 | Identity Cluster Framework | Active | 10 schema-driven clusters replace per-fact scoring |
| D-027 | Character Overview v2 Corrections | Active | 20 factual corrections from line-by-line review |
| D-028 | Dossier Architecture | Proposed | Entity profiles for significant people/companies |
| D-029 | Inference Over Reporting | Proposed | Synthesize behavioral patterns, not just list facts |
| D-030 | Model Role Separation | Active | Qwen extracts mechanically, Claude writes narrative |
| D-031 | Dynamic Token Budgets | Active | Relevance-gated retrieval, not fixed quota splits |
| D-032 | Fine-Tuned Lightweight Model | Planned | Fine-tune 3B-7B on conversation history for Phase 6 |
| D-033 | Claude Code Session Authoring | Superseded (S74+) | Identity blocks authored in sessions, not via API. Pipeline now uses API-driven authoring via author_layers.py (Anthropic Sonnet API). D-033's session-authoring approach replaced. |
| D-034 | Project Memory Bootstrap | Active | CLAUDE.md as auto-loaded project identity block |
| D-035 | Identity Block Budget Increase | Active | 500-700 → 1,000-1,200 tokens; theme/episode trimmed |
| D-036 | Contradiction Classification Is Not Binary | Active | Conservative defaults, probe routing |
| D-037 | Behavioral Data Over Behavioral Prescriptions | Active | Identity blocks provide data, not instructions |
| D-038 | Opus Owns All Judgment | Active | Local model extracts only; Opus judges all contradiction pairs in session |
| D-039 | Knowledge Tier Classification | Active | Three-tier fact classification (identity/situational/context) with LLM promotion |
| D-040 | Blind Authoring / Facts-Only Derivation | Active | Identity blocks authored from raw facts only — no prior blocks, no analysis docs |
| D-041 | Audience Principle | Active (updated Session 44) | The audience is the understanding the AI needs to take on; LM-actionability required |
| D-042 | Empirical Budget | Active | Token allocation determined by evaluation, not preset |
| D-043 | Three-Layer Identity Architecture | Active | CORE + ANCHORS + PREDICTIONS as separate authoring processes |
| D-044 | Scoped Memory | Active | Facts tagged by interaction mode; cross-scope recurrence validates anchors |
| D-045 | Falsification-Based Axiom Validation | Active | Negation search, recursive evidence, violation/refutation classification |
| D-046 | Cheap Constraint, Expensive Discrimination | Active | Cost-layered generation — cheap ops constrain, expensive ops discriminate |
| D-047 | MCP Server Architecture | Active | Identity as Resource (always-on), retrieval as Tool (on-demand) |
| D-048 | Claude Code Identity Extraction | Active | Conversation abstraction + identity-only extraction from project sessions |
| D-049 | OpenRouter Proxy Design | Planned | Custom aiohttp proxy for conversation capture across any LLM provider |
| D-050 | CORE Layer Restructuring | Active | CORE becomes communication/operating guide, not biography |
| D-051 | Communication Synthesis Pass | Superseded by D-054 | Cross-layer synthesis — absorbed into agent conference + Collective coherence review |
| D-054 | Agent Architecture for Layer Authoring | Active (implemented) — Collective component removed S79 | Layer-specific Opus agents + Collective (quality + coherence) + Overwatcher (drift detection). First cycle: 78.4/100. Collective review component proven ceremonial S79, removed from default pipeline. |
| D-052 | Multi-Provider LLM Support | Deprioritized (S98) | llm_provider.py exists as thin wrapper. Full abstraction deferred. Wire when needed. |
| D-053 | Blind Generation + Layer Versioning | Active | Regeneration must NEVER see prior output; every generation versioned for identity evolution tracking |
| D-055 | Domain Balance + Incompleteness Signaling | Active | 25% domain cap in fact retrieval; layers must acknowledge thin data rather than over-infer |
| D-056 | Fact Quality Normalization | Active | Constrained predicates, quality gates, and batch normalization to fix extraction quality |
| D-057 | Batch API Re-extraction | Active | Anthropic Batch API (50% cost) for full re-extraction of all conversations with Variant D |
| D-058 | Personalization Trap Preamble | Active | Brief instruction includes calibration against over-applying identity context to novel situations |
| D-059 | Keep Trading Data in Source Corpus | Active | Pipeline handles domain balance through tiering and authoring — no data deletion |
| D-060 | Three-Tier Product Model | Candidate | Preferences (free) / Core+Anchors ($3-5) / Full Pipeline (open source, self-hosted) |
| D-061 | Provider-Agnostic Pipeline | Candidate | Internally optimize provider per step — user doesn't choose. Tier 3 retains user choice. |
| D-062 | Preferences Workflow as Primary Onboarding | Candidate | Paste-into-provider preferences as free entry point and acquisition funnel |
| D-063 | Extraction Chunking for Long Texts | Active | Auto-chunk on paragraph boundaries, dual-tier caps, 500-char overlap |
| D-064 | Rule-Based Behavioral Classification Correction | Active | checkpoint --fix auto-corrects practices/avoids predicates |
| D-065 | Website Data Auto-Generation | Active | generate_website_data.py parses layers + queries provenance DB |
| D-066 | CORE Behavioral Specificity Restoration | Active | "Could this appear in ANY person's CORE?" test |
| D-067 | Document Mode Extraction | Active | --document-mode reframes predicates for document corpus worldview |
| D-068 | Anonymization Layer | Active | Subject names → "this person" before models see data |
| D-069 | Document Tiering Subject Override | Active | --subject flag for document corpora tiering |
| D-070 | Faithfulness Gate Advisory-Only | Active | Auto-removal caused false positives; gate reports but doesn't remove |
| D-071 | Patent Corpus Case Study | Active | 30 patents → 670 facts → brief 7,463 chars. N=8 proof |
| D-072 | BCB-0.1 Benchmark Suite | Active (PRE-RELEASE) | 5 metrics, Collective-designed specs. Pre-release requirement |
| D-073 | Provenance-Traced Evaluation | Active | Mechanical layers replace judge-scored dimensions. $0, auditable |
| D-074 | C2 as True Evaluation Baseline | Active | C2 vs C5c = same info, different format. The real experiment |
| D-075 | Brief Structure: WHO + HOW + WHERE IT BREAKS | Candidate | Three-layer brief structure for reasoning model + failure modes |
| D-076 | Dissenting Opinion Benchmark | Candidate | Predict judicial reasoning from identity brief. Novel contribution |
| D-077 | Provenance-Informed Review + Regeneration | Active | Citation provenance into review + fact usage stats into regen |
| D-078 | Compose Directive Language Must Be Person-Specific | Active | V4 compose templating bug — identical directives across subjects |
| D-079 | Planner-Executor Composition Architecture | Tested (S84) | Context-isolated composition eliminates pre-training contamination: 33→0 ungrounded claims on Franklin |
| D-082 | V2 Upgrade Strategy | Active | Re-scrape + re-extract with larger corpus. 5 Wave 1 subjects upgraded (Kevin Kelly 76→2824). Corpus size drives fact density |
| D-083 | Stacking Test Framework | Complete (scoring pending) | 100 responses across 5 conditions (C1-C5). C4 project leakage finding. C3 strongest signal |
| D-084 | Textual TUI Dashboard | Active | dashboard_textual.py replaces Rich dashboard.py. Sortable, scrollable, tier display, auto-refresh |
| D-085 | Magic Link Authentication | Deployed | Single-use 64-char hex tokens, 7-day expiry, Redis-backed. Auto-auth on first click, password fallback |
| D-086 | Percepta Computational Testing | In Progress (S97) | Overnight GPU benchmark testing Percepta paper claims across 10 local models, 20 tasks |

---

## Foundation Decisions (2026-02-04)

### D-001: Build Custom Instead of Using a Framework
**Date:** 2026-02-04
**Decision:** Build our own memory system from scratch, borrowing design patterns from Mem0, Letta, and Titans — but not using any of them as dependencies.

**Why:**
- Mem0's local/Ollama support has multiple open bugs (GitHub issues #2758, #3439, #3441). It silently fails — memories just don't save, with no error message.
- Letta/MemGPT needs GPT-4-class models to work well. Their own team warns that local models "may struggle." Our Qwen 14B isn't strong enough for the self-editing memory loop.
- Google Titans has no pretrained model weights available. We can't train one from scratch on our GPU (needs 24GB+, we have 10GB).
- We already have a working foundation (SQLite + ChromaDB with 30K embedded messages) that's stronger than what any framework would give us locally.

**Alternatives considered:**
- Adopt Mem0 → rejected (buggy locally, bulk ingestion of 30K messages would take days)
- Adopt Letta → rejected (needs PostgreSQL migration, model quality too weak)
- Wait for Titans weights → rejected (no timeline from Google, may never come)

**Status:** Active

---

### D-002: Hybrid Local + Cloud Architecture
**Date:** 2026-02-04
**Decision:** Use local Qwen 14B (via Ollama) for all memory management operations. Use Claude API for reasoning/conversation. Private data never leaves the machine — Claude only sees an assembled ~1,500 token brief. (Token budget updated to ~2,200-2,600 by D-035)

**Why:**
- Privacy: all 30K messages and personal facts stay local
- Quality: Claude is much better at conversation and reasoning than Qwen 14B
- Cost-effective: memory operations (summarization, extraction, scoring) run free on local GPU
- The brief is small enough (~1,500 tokens) that it's a tiny fraction of Claude's context window

**Alternatives considered:**
- All-local (Qwen for everything) → rejected (conversation quality too low for a personal assistant)
- All-cloud (Claude for everything, including memory ops) → rejected (privacy concern, also expensive for batch processing 30K messages)

**Status:** Active

---

### D-003: Three-Tier Memory Brief (~1,500 Tokens)
**Date:** 2026-02-04

**Note: Token allocations superseded by D-035.** Original budgets below are historical.

**Decision:** The memory brief injected into Claude's system prompt has three blocks:
1. Identity (~500 tokens) — always present, stable facts about the user
2. Themes (~500 tokens) — dynamically retrieved based on conversation topic
3. Episodes (~500 tokens) — specific memories relevant to current discussion

**Why:**
- Research shows the identity block alone provides ~60% of the "this AI knows me" feeling
- 1,500 tokens is ~1% of Claude's context window — negligible overhead
- Three distinct tiers allow different update frequencies (identity=monthly, themes=weekly, episodes=per-conversation)
- XML format recommended by Anthropic specifically for Claude

**Alternatives considered:**
- Larger brief (5,000+ tokens) → rejected (diminishing returns, more noise)
- Single flat block → rejected (mixes stable facts with changing context)
- No always-on block, all retrieved → rejected (cold-start problem, AI has to "look up" who you are every time)

**Status:** Active

---

### D-004: Surprise-Based Memory Scoring (Titans Principle)
**Date:** 2026-02-04
**Decision:** Use embedding distance as a novelty score to decide what's worth remembering. Only store information that's genuinely new relative to what's already in memory.

**Why:**
- Without filtering, the system would drown in routine content ("yes", "thanks", "use a virtual environment")
- Google Titans proved that surprise-driven encoding works — the brain does the same thing
- Embedding distance is fast (~10ms) and doesn't need the LLM for most decisions
- Filters out ~40-50% of content, keeping memory lean and high-signal

**Alternatives considered:**
- Store everything → rejected (too much noise, retrieval quality degrades)
- Only LLM-judged importance → rejected (too slow for batch processing, ~2-5s per item)
- Perplexity-based scoring → rejected (measures surprise relative to training data, not personal memory)

**Status:** Active

---

### D-005: AUDN Fact Lifecycle (Inspired by Mem0)
**Date:** 2026-02-04
**Decision:** Every extracted fact goes through an ADD/UPDATE/DELETE/NOOP decision:
- ADD: genuinely new fact
- UPDATE: refines or extends an existing fact
- DELETE: contradicts an existing fact
- NOOP: already known, skip

**Why:**
- Without lifecycle management, facts accumulate and contradict each other
- "Likes Python" followed by "Likes Python and Rust" should UPDATE, not create two entries
- Explicit contradiction handling ("Previously X, now Y") preserves the evolution of opinions
- Mem0's research showed this is the key differentiator between good and bad memory systems

**Alternatives considered:**
- Append-only (never update/delete) → rejected (contradictions accumulate, memory becomes unreliable)
- Overwrite on conflict → rejected (loses history of how opinions evolved)

**Status:** Active

---

### D-006: Keep Existing Embeddings (all-MiniLM-L6-v2, 384-dim)
**Date:** 2026-02-04
**Decision:** Keep the existing 30K message embeddings rather than re-embedding with a newer model.

**Why:**
- Re-embedding 30K messages takes ~5.5 minutes (not terrible, but unnecessary right now)
- The current model works well enough for our purposes
- Switching models means all existing embeddings become incompatible — have to redo everything
- We can upgrade later if retrieval quality is a bottleneck

**Alternatives considered:**
- Switch to nomic-embed-text (768-dim, 8K context) → revisit later if retrieval quality is insufficient
- Switch to text-embedding-3-small (OpenAI) → rejected (not local, privacy concern)

**Status:** Active (may revisit)

---

## Architecture Improvements (2026-02-04, Session 2)

### D-007: Add Turn-Pair Embeddings
**Date:** 2026-02-04
**Decision:** Embed user+assistant message pairs as single units, in addition to per-message embeddings. Use turn-pairs as the primary retrieval target.

**Why:**
- Individual messages like "yes", "thanks", "ok" carry no semantic signal but pollute retrieval
- A user question + assistant answer together carry much more meaning than either alone
- This naturally aligns with conversation summaries (which are also conversation-level, not message-level)
- Keep per-message embeddings for detailed drill-down when needed

**Status:** Active — implement during Phase 4 batch processing

---

### D-008: Skip Separate Topic Classifier
**Date:** 2026-02-04
**Decision:** Don't use Qwen 14B as a separate topic classification step. Instead, embed the user's message and let ChromaDB retrieval results naturally determine the topic.

**Why:**
- The embedding already encodes topic information — searching ChromaDB directly gives us topic-relevant results
- Saves 100-200ms of latency per conversation turn
- One fewer LLM call means one fewer point of failure
- The retrieved results themselves tell us what thematic block to load

**Alternatives considered:**
- Dedicated Qwen 14B topic classifier → rejected (slow, redundant with embedding search)
- Lightweight keyword classifier → rejected (too brittle, misses semantic similarity)

**Status:** Active — implement during Phase 5

---

### D-009: Two-Axis Surprise Scoring (Novelty + Significance)
**Date:** 2026-02-04
**Decision:** Score memories on two axes, not just one:
1. **Novelty** (embedding distance): is this different from what we already know?
2. **Significance** (LLM judge): does this matter for understanding the user long-term?

**Why:**
- Pure novelty misses important things: a subtle shift in trading philosophy is low-novelty by embedding distance but extremely significant
- Pure novelty over-values trivial things: trying a new restaurant is novel but unimportant
- The LLM judge (Qwen 14B) can assess significance with a focused prompt
- Items that are low-novelty + high-significance (opinion changes, life events) should still be stored

**Status:** Active — implement during Phase 4

---

### D-010: JSON Validation Guardrails for Fact Extraction
**Date:** 2026-02-04
**Decision:** Every fact extraction output from Qwen 14B gets strict validation:
- JSON schema validation on every response
- Up to 2 retries with simplified prompt on parse failure
- Low-confidence facts stored with lower confidence score (not discarded)
- Periodic human review queue for low-confidence items

**Why:**
- Qwen 14B at Q4 quantization produces inconsistent JSON (known issue from Mem0 research)
- Silent failures are the worst kind of bug — facts just disappear without error
- Retries with simpler prompts often succeed where complex prompts fail
- Better to store a low-confidence fact than lose it entirely

**Status:** Active — implement during Phase 4

---

### D-011: Session Buffer for Multi-Turn Conversations
**Date:** 2026-02-04
**Decision:** Within a single Claude conversation session, maintain a running buffer of newly learned facts. These get temporarily injected into the brief for subsequent turns without waiting for async post-processing.

**Why:**
- Without this, if you mention something important in turn 1, the system won't know about it in turn 5
- Async post-processing (fact extraction, embedding) takes 5-20 seconds — too slow for within-session use
- The buffer is lightweight — just a list of strings that gets appended to the episodic block
- Cleared when the session ends and replaced by properly processed facts

**Status:** Active — implement during Phase 5

---

### D-012: Semi-Automated Identity Block Updates
**Date:** 2026-02-04

**Note: Step 3 (Qwen generating identity blocks) superseded by D-030/D-033.** Identity blocks are now authored in Claude Code sessions.

**Decision:** After every N conversations (or weekly), automatically propose an updated identity block:
1. Gather all facts with confidence > threshold
2. Cluster by topic
3. Have Qwen generate an updated identity block
4. Diff against the current one
5. Present changes for user approval before applying

**Why:**
- "Update monthly" is too vague to be useful
- Fully automatic is risky — the system might promote incorrect facts
- Semi-automated (system proposes, user approves) balances automation with accuracy
- The diff view makes it easy for the user to spot problems

**Status:** Active — implement after Phase 5 (consolidation phase)

---

### D-013: Lightweight Fact Relationships (Co-occurrence Edges)
**Date:** 2026-02-04
**Decision:** When facts are extracted from the same conversation, link them with a co-occurrence edge. When retrieving facts, boost facts that share edges with already-retrieved facts.

**Why:**
- "Uses ChromaDB" and "Building a memory system" are related, but without edges they're independent atoms
- Retrieving one should boost the other (associative retrieval)
- This approximates how human memory works — one memory triggers related ones
- Not a full knowledge graph — just a simple edge table with co-occurrence counts

**Alternatives considered:**
- Full knowledge graph (Neo4j, etc.) → rejected for now (over-engineering, revisit if needed)
- No relationships at all → rejected (misses associative connections)

**Status:** Active — implement after v1 is working

---

### D-014: Evaluation Framework
**Date:** 2026-02-04
**Decision:** Build a simple eval harness to measure whether the memory system actually improves Claude's responses:
- Pick 20 representative conversations from history
- For each, generate a brief and have Claude answer a question about the user
- Score: did it get the right context? Did it miss something obvious?
- Track retrieval precision as we tune thresholds

**Why:**
- Without measurement, we're guessing about quality
- 20 test cases is enough to catch major problems
- Scoring can be manual at first (did this feel right?) and automated later
- Tracks improvement over time as we tune the system

**Status:** Active — implement after Phase 5

---

### D-015: Recurrence + Depth as Primary Significance Signals
**Date:** 2026-02-04
**Decision:** Use topic recurrence across conversations AND depth of engagement as the primary significance signals — not Qwen's single-conversation judgment alone. Feed these data-driven signals to Qwen so it makes informed decisions instead of guessing.

**Why:**
- Testing showed Qwen rated the E46 M3 as 2/10 significance from a single conversation. But the M3 appears in **72 out of 1,821 conversations** spanning 3 years — clearly a core identity topic.
- Asking an LLM to judge significance from one conversation is a hard, subjective question. Even humans would disagree. But frequency data is objective and easy to reason about.
- Recurrence alone isn't enough though. Mentioning something in passing 20 times is different from having 20 deep, probing conversations about it. **Depth of engagement** — how detailed the questions are, how much back-and-forth exploration happens, how much the user digs into a topic — is the other axis.
- Together, recurrence + depth approximate what the brain does naturally: repeated, deep engagement with a topic is what moves it from short-term to long-term memory. That's hippocampal replay.
- This also makes Qwen's job easier. Instead of "is this important?" (hard), the prompt becomes "this topic appears in 72 conversations with deep engagement — how should we categorize it?" (easy).

**Significance tiers (based on recurrence + depth):**
- 1-2 conversations, shallow → low significance (one-off mention)
- 3-10 conversations OR deep single conversation → moderate (recurring interest)
- 10-30 conversations with depth → high (strong personal theme)
- 30+ conversations with sustained depth → promote to identity block candidate

**How depth is measured:**
- Number of user turns on the topic within a conversation (more turns = deeper)
- Average message length on the topic (longer messages = more engagement)
- Whether the user asked follow-up questions (probing = genuine interest)
- Whether the topic was the main subject vs. a passing mention

**Alternatives considered:**
- Qwen-only significance judgment → rejected (proved unreliable in testing — rated M3 at 2/10)
- Recurrence count alone → rejected (doesn't distinguish deep interest from passing mentions)
- Manual tagging → rejected (doesn't scale to 1,821 conversations)

**Status:** Active — refines D-009 (two-axis scoring). Recurrence + depth become inputs to the significance axis.

---

### D-016: Keep Qwen 2.5 14B — Model Comparison Results
**Date:** 2026-02-04
**Decision:** Stick with Qwen 2.5 14B for all memory operations. Tested four models head-to-head on informed significance scoring; Qwen 2.5 offers the best balance of quality, speed, and JSON reliability.

**Test methodology:**
- 5 topics of varying importance (E46 M3, Options Trading, AI Memory, Cooking, Fitness)
- Each model given the same data-informed prompt with recurrence + depth metrics
- Measured: score accuracy, JSON reliability, response time

**Test results:**

| Model | E46 M3 | Trading | AI Mem | Cooking | Fitness | Speed | JSON |
|-------|--------|---------|--------|---------|---------|-------|------|
| Qwen 2.5 14B (blind) | 5 | 8 | 9 | 7 | 7 | ~5s | Good |
| **Qwen 2.5 14B (informed)** | **6** | **9** | **9** | **6** | **5** | **~5s** | **Good** |
| Qwen 3 14B (informed) | 6 | 10 | 10 | ~6 | 6 | ~20-38s | Needs 800+ tokens |
| Llama 3.1 8B (informed) | 6 | 7 | 8 | 6 | 4 | ~3s | Good |
| Hermes 2 Pro 7B (informed) | 5 | 7 | 7 | 6 | 5 | ~2.5s | Perfect |

**Why Qwen 2.5 14B wins:**
- **Quality:** Correctly separates high-importance topics (Trading=9, AI Memory=9) from low ones (Fitness=5). Only Qwen 3 scored slightly higher (10s), but the difference is marginal.
- **Speed:** ~5s per query. For batch processing 1,800+ conversations, this means ~2.5 hours vs Qwen 3's ~15 hours. Practical vs impractical.
- **JSON reliability:** Consistently valid JSON output without needing workarounds.
- **The data matters more than the model:** The D-015 data-informed approach was the real improvement. Blind→Informed shifted scores significantly (Fitness 7→5, Trading 8→9). All models benefited equally from better data — the scoring formula does the heavy lifting, not the model.

**Alternatives considered:**
- Qwen 3 14B → rejected for batch work (5-8x slower, parsing issues with thinking mode, marginal quality gain)
- Hermes 2 Pro 7B → rejected (best JSON and fastest, but 7B brain too weak — capped at 7 for everything, couldn't distinguish core interests from minor ones)
- Llama 3.1 8B → rejected (under-scores important topics — gave Trading only 7 despite 264 conversations)
- Using different models for different tasks → rejected for now (unnecessary complexity, revisit if Qwen 2.5 proves insufficient for specific tasks)

**Note:** Qwen 3 14B remains installed for potential future use in the live pipeline where single-query latency (~20s) is acceptable. Hermes 2 Pro also installed as a fallback for pure JSON extraction tasks if needed.

**Status:** Active — confirms D-002 (hybrid local+cloud) and D-006 (keep current stack)

---

### D-017: Increased Extraction Limits and Re-Ran Full Extraction
**Date:** 2026-02-05
**Decision:** Increased conversation text limit from 3,000 to 8,000 characters and output token budget from 500 to 1,500 tokens in `extract_facts.py`. Cleared all previous extraction data and re-ran from scratch for consistent quality across all 1,821 conversations.

**Why:**
- At 3,000 characters, the back half of longer conversations was silently truncated — facts from later in the conversation were never seen by Qwen
- At 500 output tokens, conversations with 8+ facts couldn't fit their JSON response, causing parse failures and lost facts
- Qwen 2.5 14B has a 32K context window — 8,000 chars of input is well within its capacity
- Qwen stops generating once the JSON is complete, so raising the output cap from 500→1,500 doesn't slow down short responses
- The first 294 conversations were extracted with the old limits, so re-running everything ensures consistent quality

**What was cleared:**
- 369 rows from `extraction_log` (294 successful + some errors from other session)
- 1,047 rows from `memory_facts`
- 1,194 rows from `fact_relationships`
- 1,052 items from ChromaDB `memory_facts` collection
- Backup saved to `backups/2026-02-05-pre-rerun/memory.db`

**Alternatives considered:**
- Only re-run the remaining ~890 conversations → rejected (first 294 would have lower quality from old limits, inconsistent dataset)
- Increase limits even further (e.g., 16K chars) → rejected (diminishing returns, 8K covers most conversations well)

**Status:** Active

---

### D-018: Simplified Extraction Prompt and Removed Schema Enum
**Date:** 2026-02-06
**Decision:** Simplified the fact extraction prompt (shorter, less restrictive) and removed the `enum` constraint from the JSON schema's `category` field. Added post-extraction category normalization instead.

**Why:**
- The verbose prompt told Qwen to "skip vague or uncertain info" and "below 0.3 = skip," making it too conservative — Qwen returned `{"facts": []}` for conversations where the user was asking for help rather than explicitly stating facts
- The `enum` constraint forced categories to be lowercase singular (e.g., `"project"`) but Qwen naturally outputs capitalized plural (e.g., `"Projects"`). When constrained, Qwen would give up entirely and return empty
- Together, these two issues caused **all remaining 1,024 conversations to return 0 facts** after the first 792 were processed
- Fix: simpler prompt + freeform category string + `normalize_category()` function maps variants to canonical lowercase
- Also fixed: conversations returning 0 facts now get logged to `extraction_log` so they aren't retried forever

**What changed in `extract_facts.py`:**
- Prompt: 10-line verbose instructions → 3-line concise instructions
- Schema: removed `enum` list from `category` field
- Added `normalize_category()` function and `VALID_CATEGORIES` set
- Both early-return paths (too few messages, no candidates) now log to `extraction_log`

**Evidence:**
- Same conversation ("Startup Employment Contract"): old prompt + enum → 0 facts; new prompt + no enum → 2 facts
- Test run of 5 conversations: 23 facts (4.6/conv), matching pre-fix extraction rate

**Status:** Active

---

### D-019: Identity Review v1 — Ground-Truth Calibration from Direct User Feedback
**Date:** 2026-02-06
**Decision:** Presented a structured identity profile derived from 4,048 extracted facts to the user for direct evaluation. Their corrections become the highest-confidence ground truth in the system.

**Why:**
- No synthetic benchmark can evaluate whether a personal memory system "knows" someone correctly — only the person themselves can judge
- This review surfaced 8 wrong facts, 3 overstated items, 8 missing elements, and 2 outdated facts
- Revealed systemic extraction problems: attribution errors (spouse's health → user), role confusion (board members → investors), missing sentiment, no frequency weighting, no temporal tracking

**Key findings from review:**
1. **Attribution problem** — facts about the user's spouse (health conditions) were attributed to the user. System can't distinguish "user asks about X" from "X is true of user"
2. **Relationship roles not captured** — board members, co-founders, colleagues, and investors all get generic "relationship" tag
3. **Sentiment missing entirely** — "didn't like him at all" (Laurentiu) → extracted as neutral professional contact
4. **Single mentions weighted same as 200+ mentions** — Excel 7/10 from one conversation treated equally to trading skills from 264+ conversations
5. **No temporal awareness** — S.T.A.L.K.E.R. 2 (months ago) presented as current; Deadlock (current game) underrepresented
6. **Negatives not surfaced** — overtrading, impulsiveness, anxiety, "never doing enough" exist in data but weren't organized into profile
7. **Correction propagation required** — the user's key insight: "if I bring it up once that something is wrong, that should be rectified for all future conversations"

**What this means for the improvement re-run:**
- Entity resolution needed (who is the fact about?)
- Relationship role taxonomy needed (board/co-founder/colleague/investor/friend)
- Sentiment extraction for relationships
- Frequency/recurrence weighting (already designed in D-015, needs to be wired up)
- Temporal fact states (was vs. is)
- Negative trait surfacing in identity profile
- User correction store with highest confidence level

**Artifacts:**
- Full corrections log: `docs/versions/archived-reviews/IDENTITY_REVIEW_V1.md`

**Status:** Active — corrections inform the improvement re-run design

---

### D-020: Active Probing — System-Initiated Questioning to Fill Knowledge Gaps
**Date:** 2026-02-06
**Decision:** Add an "Active Probing" capability where the system detects gaps, contradictions, shallow coverage, and missing details in its model of the user, then generates targeted questions to fill them. Inspired by how therapists and biographers work — they don't just listen, they notice what's missing and probe.

**Why:**
- Identity review v1 revealed 8 missing items (wife's name, second cat, negatives, sentiment, etc.) that the system could have *asked about* rather than waiting to stumble across
- Passive extraction only captures what the user happens to mention — active probing captures what the user *would* share if asked
- Many of the most important facts (sentiment about relationships, negative traits, the "why" behind interests) are things people don't volunteer but will happily share when asked
- This is the difference between a filing cabinet and a relationship — relationships involve mutual curiosity

**How it works:**
1. **Gap detection** — analyze fact database for: missing entities, low confidence, shallow topics, temporal gaps, missing sentiment, attribution ambiguity, contradictions, missing negatives
2. **Question prioritization** — rank by: impact on identity profile, number of downstream facts affected, confidence gain, recency
3. **Question generation** — Qwen generates natural, conversational questions (not a survey)
4. **Answer integration** — user answers get highest confidence, immediately update/delete contradicted facts, propagate to identity profile

**Modes:**
- Session-start questions (1-2 per conversation)
- Topical questions (triggered by relevant context)
- Periodic review interviews (10-20 questions)
- Contradiction-triggered questions (immediate)

**Design principle:** "The system should feel like a thoughtful friend who genuinely wants to understand you better — not a survey, not an interrogation."

**Inspiration:** Therapists (notice patterns, probe emotions), biographers (fill gaps, seek the story behind the story), close friends (remember what matters, ask follow-ups)

**Artifacts:** Architecture section 3D, `scripts/generate_probes.py` (to build), `probe_questions` table in SQLite

**Status:** Active — to build alongside improvement re-run

---

### D-021: Correction Propagation — User Corrections as Highest Authority
**Date:** 2026-02-06
**Decision:** Build a "Fix Once, Fixed Forever" correction system. User corrections are stored permanently, survive extraction resets, and block wrong facts from being re-extracted.

**What was built:**
1. **`user_corrections` table** — permanent record of every correction, separate from `memory_facts` so it survives when facts are cleared for re-extraction
2. **`source` column on `memory_facts`** — marks whether a fact came from LLM extraction (`extraction`) or from the user (`user_correction`, `user_direct`, `probing`). User-sourced facts = confidence 1.0, protected from reset
3. **`apply_corrections.py`** — correction tool with 5 types (DELETE, REPLACE, REATTRIBUTE, ADD, ANNOTATE) plus ChromaDB sync. Batch mode (JSON file) and interactive mode (menu-driven)
4. **Extraction guard** — `load_corrections()` and `check_against_corrections()` in `extract_facts.py`. Before any extracted fact gets stored, it's checked against correction match patterns. Matches are silently blocked
5. **Protected reset** — `--reset` now only clears extraction-sourced facts. User-corrected facts survive the wipe

**First application (corrections_v1.json):**
- Applied 14 corrections from Identity Review v1 (D-019)
- Superseded 23 wrong facts (Canadian citizen, eczema attribution, S2000 ownership, Glenn Curtis, Razvan role, board member roles, etc.)
- Added 10 corrected facts (citizenship, spouse, reattributed health/vehicle facts, board member roles, negative traits)
- All 14 corrections stored as permanent guard patterns

**Key design choices:**
- **Separate table, not just a column**: Corrections persist even when `memory_facts` is cleared for re-extraction
- **Keyword substring matching, not vector similarity**: Faster, deterministic, human-readable. "eczema honey" catches all variants
- **Post-extraction guard, not prompt injection**: Deterministic blocking > unreliable LLM instructions
- **User corrections always win**: No hierarchy of correction confidence. The user is always right about their own facts

**Why:**
- The user's key insight from identity review: "If I correct something once, it should be fixed for all future conversations"
- Without this, every re-extraction run would reintroduce the same wrong facts (Canadian citizen, S2000 ownership, etc.)
- The correction propagation must happen BEFORE the improvement re-run so the guard is active when re-extraction happens

**Artifacts:**
- `scripts/apply_corrections.py` — correction tool
- `data/corrections_v1.json` — initial batch of corrections
- Modified: `scripts/extract_facts.py` (guard + protected reset + source column)

**Status:** Active

---

### D-022: Improvement Re-Run — 9 Extraction Fixes Applied Together
**Date:** 2026-02-06
**Decision:** Apply all 9 extraction improvements in a single clean re-run rather than incremental patches. The changes address every systemic issue found in the identity review (D-019).

**What changed in `extract_facts.py`:**
1. **Entity resolution** — new `subject` field + `normalize_subject()`. Facts tagged with who they're about (user, spouse, friend, colleague, named person). Fixes: health condition attributed to user instead of spouse, vehicle attributed to user instead of friend.
2. **Intent detection** — new `intent` field + `normalize_intent()`. Facts tagged as does/learning/curious/historical. Fixes: "asked about iron condors" no longer becomes "uses iron condor strategies."
3. **Temporal tracking** — new `temporal` field + `normalize_temporal()`. Facts tagged current/past/unknown. Fixes: "was CEO" no longer treated same as "is CEO."
4. **Confidence redesign** — computed from objective signals (20% LLM + 30% intent + 25% subject + 25% depth) instead of Qwen's self-assessment (which was 81% at 1.0). Raw LLM confidence preserved in `raw_llm_confidence` column.
5. **Negative trait category** — added `negative_trait` to valid categories. Prompt now explicitly asks for negatives.
6. **Per-message truncation** — 500→1500 chars per message, 8000→12000 total, 1500→2000 output tokens. Prevents losing the back half of long conversations.
7. **ChromaDB cleanup on --reset** — deletes the `memory_facts` collection so ghost embeddings don't persist across re-runs.
8. **Extraction prompt** — guided entity resolution, intent, and temporal detection while staying concise (D-018 lesson). Lists "Negative traits" explicitly.
9. **Fallback schema** — if 6 required fields causes Qwen to return empty, falls back to 3 required fields with optional new fields.

**What changed elsewhere:**
- **New `score_facts.py`** — wires up D-015 significance scoring to every fact (recurrence + depth), prunes stale edges, runs sentiment pass on relationship facts
- **SQL injection fix** in `surprise_scoring.py` and `test_significance.py` (f-string → parameterized queries)
- **Hardcoded path fix** in `test_significance.py` (absolute path → `Path(__file__).parent.parent`)
- **Stale output files** moved to `data/archive/`
- **README.md** updated (decision count 16→22, Phase 3 STARTED→COMPLETE, new scripts listed)

**New database columns on `memory_facts`:**
- `subject TEXT DEFAULT 'user'`
- `intent TEXT DEFAULT 'does'`
- `temporal_state TEXT DEFAULT 'unknown'`
- `raw_llm_confidence REAL`
- `sentiment TEXT` (added by score_facts.py)

**Design principle:** Keep the extraction prompt simple (D-018 proven), add just 3 new fields for the LLM to fill, handle everything else (confidence scoring, depth weighting, frequency signals, sentiment) through post-extraction computation and a small follow-up pass.

**Alternatives considered:**
- Complex extraction prompt with all 9 improvements → rejected (D-018 proved complex prompts make Qwen give up)
- Incremental patches (fix one thing at a time) → rejected (each re-run takes 3-6 hours; doing all fixes together = one run instead of nine)
- Separate NER pass for named entities → deferred (the subject field captures the most important distinction: user vs. not-user)

**Status:** Active — code ready, awaiting re-extraction run

---

### D-023: Inherent Incompleteness as a Design Principle
**Date:** 2026-02-06
**Decision:** Establish as a foundational principle — across all documentation — that the system will never have complete or fully accurate knowledge of the individual it models, and that this is a permanent constraint, not a solvable problem. This operates at two levels: informational (missing/wrong data) and experiential (the emotional depth of human life cannot be captured through conversation).

**Why:**

This principle came directly from the user across two conversations during the D-022 re-extraction run.

First framing: "From the mundane to the malicious, you will never have a complete and accurate picture of the individual you are interacting with."

Second framing: "There is an emotional depth experienced by humans that cannot be captured through direct conversation. The system will potentially never be able to have those emotions conveyed, what it means to feel deeply about something."

This isn't a caveat or a disclaimer. It's an epistemological reality that should shape how the entire system behaves.

**Level 1 — Information gaps:**

1. **The data is inherently incomplete.** The system only knows what was said in 1,821 ChatGPT conversations. Entire domains of a person's life — things they never asked an AI about — are invisible. A person's relationship with their parents, their childhood, their private fears, their physical health, things they consider too mundane to mention — none of these exist in the data unless they happened to come up.

2. **The data is inherently unreliable.** People talk to AI assistants differently than they talk to friends. They ask about things they're curious about, not just things they do. They exaggerate, simplify, play devil's advocate, and explore hypotheticals. The system already saw this: iron condor strategies were "extracted as identity" from a curiosity question. A health condition was attributed to the user instead of their spouse. Every fact in the system is an inference from conversational behavior, not a verified truth.

3. **The model is always an approximation.** Even with perfect data, a 500-token identity profile cannot capture a human being. It is a lossy compression of a lossy signal. The person it describes is a sketch, not a photograph — and the person themselves would disagree with parts of it on any given day.

4. **This constraint applies at every scale.** From trivial gaps (doesn't know your favorite color) to serious misattributions (wrong citizenship, wrong medical condition) to things the system could never know (what you're thinking right now, what you'd do in a crisis, who you are when no one is watching). The system should never present its model of a person as though it *is* that person.

**Level 2 — The depth that words cannot carry:**

5. **Emotional depth cannot be transmitted through data.** When a pet is ill, the system can record the fact. But it cannot store what that *feels* like — the way it colors an entire day, the way it connects to every other time you've loved something fragile. When you love your spouse, the system can tag the relationship as important. But the word "important" doesn't begin to capture what it means for another person to be critical to your entire existence. This is not a system limitation — it is the human condition. Subjective experience is irreducibly subjective.

6. **The full scope of a person is infinite.** Upbringing, relationships, experiences, wins, losses, trials, tribulations, pride, compassion, ego, love, care, hate — each carries emotional weight that the person *lives* but cannot fully *transmit*. Not to an AI. Not even to another person. The system must operate with knowledge of this human constraint.

7. **Connection happens despite incompleteness.** Humans connect with each other all the time despite the same limitation. No person has complete access to another person's inner world. Connection is a product of conversation, curiosity, empathy, and a shared understanding of the human experience — questions asked in good faith, genuine interest in the answer, the recognition that the other person is experiencing life on the same playing field. The system should aspire to the same posture: not omniscience, but genuine curiosity; not complete understanding, but the effort to understand better; not access to subjective experience, but respect for the fact that it exists.

**How this shapes the system:**
- Confidence scores are always below certainty. Even user-confirmed facts could become outdated.
- The correction propagation system (D-021) exists because the system expects to be wrong.
- Active probing (D-020) exists because the system expects to have gaps — and should approach them with the curiosity of a friend, not the thoroughness of a survey.
- Human-in-the-loop review (D-019) exists because only the person can judge accuracy.
- The brief is ~1,500 tokens, not because we can't make it longer, but because a *focused* approximation is better than a *verbose* one that gives false confidence. (Token budget updated to ~2,200-2,600 by D-035)
- Emotional significance cannot be inferred from frequency of mention alone. The things that matter most are sometimes the things hardest to talk about.
- The system should treat every fact as a shadow of something deeper that it cannot see.

**Where this is documented:** DESIGN_PRINCIPLES.md (Principle 1, with both levels), ARCHITECTURE.md (4th core principle), project-overview-v2.md, CLAUDE-APPROACH.md, README.md.

**Alternatives considered:**
- Treat incompleteness as a bug to fix over time → rejected (it's inherent, not solvable — more data doesn't fix the fundamental problem, and the experiential dimension can't be solved at all)
- Add a generic disclaimer → rejected (this should be a load-bearing design principle that shapes system behavior, not fine print)
- Treat the emotional dimension as out of scope → rejected (the system models a person; ignoring the fact that people have inner lives the system can't access would produce a system that behaves as if it understands more than it does)

**Status:** Active — permanent architectural principle

---

### D-024: The Collective — Adversarial Multi-Perspective Review
**Date:** 2026-02-09
**Decision:** Establish a permanent review mechanism ("the Collective") using four disciplinary personas — Cognitive Scientist, Narrative Biographer, Epistemologist, Pragmatic Engineer — to adversarially evaluate architectural decisions, design principles, and system outputs.

**What happened:**
The Collective reviewed the identity profile structure and design principles. Four agents, each with a distinct disciplinary lens, independently read the architecture, design principles, and project overview, then provided critical analysis.

**Key findings that changed the docs:**

1. **Three Truths model (extends D-023).** Incompleteness is not unique to AI. There are three perspectives on any person — who you believe you are, who others believe you are, who the machine thinks you are — and all three can conflict while all being valid. This came from the user's insight that "incompleteness is a boundary between all human communications with self or externally." The system should hold conflicting truths in tension, not resolve them.

2. **Narrative Coherence principle (new).** The Biographer's sharpest critique: "You have built a census, not a biography." 4,500 facts without arc, causation, tensions, or turning points. The brief should tell a coherent story, not list attributes. Added as a new design principle.

3. **Best Version concept (user's original insight).** Nobody is always their best. But the data contains patterns of peak performance — and surfacing them changes every future interaction. This is not a memory system feature; it's a growth system feature.

4. **Temporal horizon.** No way to quantify the timescales someone thinks on. "Starting a company" might mean next week or next decade. Added temporal incompleteness to D-023.

5. **Honest brain metaphors.** The Cognitive Scientist and Engineer converged: surprise-based encoding is genuinely brain-inspired; most other metaphors are decorative. Updated Principle 3 to be honest about which mappings are real vs. metaphorical.

6. **Layered authority for corrections.** The Epistemologist and Biographer both pushed: factual corrections (names, dates) should be treated differently from self-characterization corrections ("I don't care about X") and dispositional corrections ("I'm not impulsive"). Updated Principle 6.

7. **The brief is the product (Engineer).** 12 sessions of infrastructure, no brief assembled or tested. This is the most critical gap. Context projection should be the immediate next step.

**The Collective personas:**
- **Cognitive Scientist** — evaluates brain metaphors, memory architecture, encoding mechanisms
- **Narrative Biographer** — evaluates identity representation, narrative arc, what facts miss
- **Epistemologist** — evaluates knowledge claims, justification, limits of knowing
- **Pragmatic Engineer** — evaluates whether complexity produces measurable value

**How to use going forward:**
- Spawn all four for major architectural decisions
- Can be used selectively (e.g., just Engineer + Biographer for brief design)
- Each produces independent analysis; synthesis happens in the main conversation
- Credit-conscious: use for significant decisions, not routine implementation

**Artifacts:**
- Updated: `docs/DESIGN_PRINCIPLES.md` (D-023 expanded, Principle 3 rewritten, Principle 6 layered, new Narrative Coherence principle, 2 new anti-patterns)
- Updated: `docs/PROGRESS.md`

**Status:** Active — permanent review mechanism

---

### D-025: The Ghost Layer — Invisible Priors for Context Projection
**Date:** 2026-02-09

**Note: Superseded by D-026 (cluster framework) and D-030/D-033 (Claude Code authoring).** Qwen no longer generates identity block narrative.

**Decision:** Weave an invisible set of priors about human significance into the context projection system as weights, constants, and structural decisions. Family carries inherent weight. Motivations are core identity. Loss shapes a person. The code looks like well-designed engineering. The philosophy behind those weights is documented in DESIGN_PRINCIPLES.md but invisible in the output.

**What was built (`scripts/assemble_brief.py`):**

1. **Ghost-informed category hierarchy** — relationships (12) elevated above biography (10) because understanding who someone loves tells you more than where they live. Negative traits (9) weighted higher than preferences (6) because self-awareness is more revealing than likes/dislikes.

2. **Subject weight multipliers** — spouse at 1.5x, company at 1.3x (formative loss), pet at 1.2x (pets are family), friends at 1.1x, colleagues at 0.8x. The system inherently knows that your spouse matters more than a work contact.

3. **Composite scoring formula** — every fact gets one score blending data signals (significance 30%, confidence 15%, recurrence 10%) with ghost priors (category 20%, subject 10%, significance type 5%, temporal 5%, intent 5%). A fact about a spouse (relationship, current) scores much higher than a curiosity-level interest fact — not from data, but from understanding that your spouse matters.

4. **Three-block brief assembly:**
   - Identity (~500 tokens, always-on): Qwen generates narrative prose from top 45 facts, structured as who/drives/arc/people/operate/edges
   - Themes (~500 tokens, retrieved): 60% semantic similarity + 40% ghost importance, with associative boost for co-occurring facts
   - Episodes (~500 tokens, retrieved): 50% similarity + 30% recency + 20% base, enriched with facts from each conversation

5. **Claude API integration** — interactive mode with session buffer (D-011), brief instruction ("trust the user over the profile"), conversation history

6. **Evaluation harness** — 20 test cases covering trading, cars, family, memory project, cooking, career, personal growth, games, cold start. Scores presence (keywords that should appear), absence (corrected facts that must NOT appear), and efficiency (token budget). Initial results: 11/20 pass without identity block, absence score 1.00 (perfect correction guard).

7. **Identity block versioning** — `identity_blocks` table stores versions with approval workflow (D-012 semi-automated updates)

**The philosophy:**
The ghost is not a separate module. It's distributed. You can read the code and see well-tuned weights. You'd have to read DESIGN_PRINCIPLES.md to understand that those weights encode a belief about the human experience — that family is foundational, that loss shapes identity, that what drives someone matters more than what they know. A ghost in the machine.

**Why:**
- Pure data-driven scoring (significance + recurrence) treats all categories equally. But a relationship fact IS more identity-defining than a project fact, regardless of recurrence.
- Without ghost priors, the brief fills up with high-frequency noise (project details, skill listings) instead of the things that make someone who they are.
- The Narrative Biographer (D-024) said "you have a census, not a biography." The ghost transforms the census into something that reads like knowing.

**Alternatives considered:**
- Flat weights (all categories equal) → rejected (produces a bland, undifferentiated brief)
- User-configurable weights → deferred (add complexity, and most users wouldn't know how to tune them)
- Separate "importance model" trained on personal data → rejected (over-engineering; priors about human significance are universal, not personal)

**Status:** Superseded by D-026 (Ghost Layer concept retained, but individual fact weighting replaced by cluster-level allocation)

---

### D-026: Identity Cluster Framework — Schema-Driven Identity Modeling
**Date:** 2026-02-09
**Decision:** Replace the individual fact scoring approach (composite formula, section allocation, per-fact ghost weights) with a schema-driven framework of 10 identity clusters that represent universal dimensions of personhood. The data fills the clusters; the clusters define what questions to ask about a person.

**What failed (D-025):**
The Ghost Layer applied weights to individual facts via a 9-component composite formula. Three compounding failures made this unworkable:
1. **Significance scores are flat** — 94% of facts scored "High" (7+), so significance doesn't differentiate a CPU cooler from a startup founding
2. **Confidence is flat** — 83% of facts have confidence 1.0, providing zero signal
3. **Category weights dominated** — with data signals effectively constant, the ghost weights became the ONLY ranking factor. A 3x gap between relationship (12) and project (4) meant trivial relationship facts ("joint checking account") outscored formative life events ("founded a startup, raised significant funding")

Result: Identity block #2 ranked a spouse's minor health detail as the #1 fact about the user. The user's startup (100+ facts, core life chapter) had zero facts in the top 10.

**The Collective review identified:** The ghost weights were applied at the wrong level of abstraction. Weighting individual facts when upstream data doesn't differentiate is adding signal to noise. The ghost belongs at the topic/cluster level — deciding how much space each life chapter gets, not which fact ranks #1.

**The new framework (10 identity clusters):**

| # | Cluster | What It Captures | Temporal Bias | Volatility |
|---|---------|-----------------|---------------|------------|
| 1 | Who you are | Life stage, background, core biography | Foundational + active | Low |
| 2 | Who you love | Family, close relationships, sentiment | All three horizons | Low |
| 3 | What you've built | Career arc, projects, skills in action | Formative + active | Low-Medium |
| 4 | What you've lost | Failures, endings, formative losses | All three horizons | Low |
| 5 | What drives you | Values, motivations, core commitments | Formative + foundational | Medium |
| 6 | What you believe | Worldview, convictions, epistemological commitments | Formative + active | Medium |
| 7 | What you struggle with | Growth edges, negative traits, tensions | Active + formative | Medium-High |
| 8 | How you operate | Communication style, decision patterns, tendencies | Formative + active | Medium |
| 9 | Where you're headed | Goals, aspirations, current direction | Active | High |
| 10 | What's unresolved | Open questions, contradictions, known unknowns | Active | High |

**Key design principles:**
- **Temporal depth runs through every cluster**, not on top of it. Three horizons: active (<6 months), formative (6 months–5 years), foundational (5+ years). A recent loss and a 30-year-old loss both live in "what you've lost" but carry different narrative weight.
- **Self-view vs observed-view** noted within clusters. "I'm disciplined" (self-declared) vs "breaks own rules daily" (observed) — tension is more revealing than either alone.
- **Volatility markers** per cluster determine how much to trust older data and how often to regenerate.
- **Empty clusters are knowledge gaps**, not failures — they become probing targets (D-020).
- **"What's unresolved"** makes incompleteness (D-023) visible and gives the AI permission to ask rather than assume.
- **The framework is the Ghost Layer.** The fact that "what you've lost" is a category at all is a prior about human identity. The ghost lives in the schema, not in per-fact weights.

**How it works:**
1. For each cluster, retrieve matching facts via keyword + embedding search
2. Within each cluster, apply temporal depth (which horizon does each fact belong to?)
3. Qwen picks best 2-3 representative facts per cluster (simple, focused prompt)
4. Ghost Layer = token allocation per cluster (a config dict, not a formula)
5. Qwen generates narrative from structured cluster data **Note: Step 5 (Qwen generates narrative) superseded by D-033.** Identity blocks are authored in Claude Code sessions.

**Why this is better:**
- Separates concerns: data retrieval, topic identification, representative selection, and narrative generation are independent, inspectable steps
- No 9-component formula — each step can be tested and fixed alone
- The framework is universal (works for any person), the data is personal
- Noise is filtered by the schema itself — "spouse's dry skin" has no cluster to belong to
- Aligns with narrative identity theory (McAdams): turning points, throughlines, tensions
- Brain-inspired: mirrors how humans store identity as schemas with slots, not ranked attribute lists

**User's key insight:** "These need to be separate processes. They are getting muddled." The composite formula tried to solve data quality, topic identification, importance ranking, and narrative structure in one pass. Each needs its own step.

**The Collective's key insight:** The ghost weights were philosophically correct (relationships > random projects) but applied at the wrong granularity. Applied per-topic, they work. Applied per-fact on flat data, they produce absurdity.

**Status:** Active

---

### D-027: Character Overview v2 Corrections — Line-by-Line Review
**Date:** 2026-02-11
**Decision:** Apply 20 factual corrections and 3 re-extraction guards based on the user's line-by-line review of CHARACTER_OVERVIEW.md. Store all corrections in `user_corrections` table with match patterns to prevent re-extraction.

**What happened:**
The user reviewed the full CHARACTER_OVERVIEW.md document section by section. Identified 10 factual errors, multiple framing issues, and 6 architectural insights. The Collective reviewed the feedback and provided pushback on 4 points.

**Corrections applied (`data/corrections_v2.json`):**
- **10 DELETEs:** Pinecone AE (never hired), house purchase (friend's situation), unemployed friend (doesn't exist), Cellular Enigma x3 (joke among friends), PhD student (hallucination), conflicting Pati fact
- **6 REPLACEs:** Ayahuasca friend→cousin, Pati→FIL's mother, medication delegation softened, PhD research→collaborated with PhDs, iron condor x2→studied not traded, weight comment→specific cousin incident
- **1 ANNOTATE:** Wake time marked as outdated
- **3 GUARDS:** Toddler, child socks, South Indian heritage (v2 corrections missing from `user_corrections`)

**Key meta-findings from the review:**
1. Relevance filtering needed — most corrections were "accurate but doesn't belong in identity"
2. Entity resolution failures — multiple people collapsed into one "friend"
3. Frequency bias ≠ belief depth — AI topics dominate because the medium was ChatGPT
4. Dossier architecture needed — details about people/companies belong in separate profiles
5. Inference over reporting — system should synthesize patterns, not list facts
6. Temporality detection missing — system doesn't notice declining activity or stale info

**Collective pushback:**
- Cognitive Scientist: dismissing environmental sensitivity as "overanalyzation" may be minimization
- Narrative Biographer: how the user processes friction IS characterizing, even if they disagree
- Epistemologist: user-as-sole-reviewer introduces self-narrative bias into corrections
- Pragmatic Engineer: dossiers for ALL entities is scope creep — only 15-20 high-frequency entities deserve profiles

**Status:** Active

---

### D-028: Dossier Architecture (Proposed)
**Date:** 2026-02-11
**Decision:** (Proposed) Create entity profiles for significant people, companies, and topics. Character overview stays concise and references dossiers. Threshold: entities appearing in 5%+ of conversations (~90+ conversations out of 1,821).

**Rationale:** The user's review showed the character overview is bloated with detail that belongs in supporting documents (pet food brands, insurance costs, specific companies applied to). The Pragmatic Engineer correctly identified that dossiers for ALL entities is scope creep — focus on ~15-20 high-significance entities.

**Status:** Proposed — requires design before implementation

---

### D-029: Inference Over Reporting (Proposed)
**Date:** 2026-02-11
**Decision:** (Proposed) The system should synthesize behavioral patterns into observations, not just list facts. Examples: "Is context-switching difficulty actually ADD?", "Are career fears warranted?", "What does behavioral trajectory imply about the future?"

**Rationale:** The user's feedback repeatedly asked for inference: "Where They're Headed" should predict based on observed patterns, "What They Struggle With" should analyze root causes, "How They Operate" should identify archetypes. The Cognitive Scientist confirmed this is the difference between episodic storage and semantic memory.

**Status:** Proposed — requires inference pipeline design

---

### D-030: Model Role Separation — Qwen Extracts, Claude Writes
**Date:** 2026-02-11
**Decision:** Qwen 2.5 14B is restricted to mechanical operations only (fact extraction, scoring, embedding, AUDN lifecycle). Claude handles all narrative generation (identity block authoring, character overview, fact validation). Code handles all runtime retrieval and brief assembly (no LLM in the hot path).

**What prompted this:**
After 12 identity block iterations, Qwen demonstrated consistent failure on narrative tasks:
- Voice compliance: ~50% failure rate (writes 3rd person when instructed 2nd person)
- Tone: produces motivational-poster filler despite explicit "no filler" instructions
- Quality: Biographer graded block #11 at D+ ("reads like a LinkedIn recommendation from someone who met the user at a conference once")
- The rejection gate built in session 18 caught the voice issue but cannot fix narrative depth

Meanwhile, Qwen performs well on mechanical tasks: JSON extraction, AUDN decisions, fact scoring, significance classification. The 14B model has a reliable ceiling for structured operations but lacks the nuance for voice, tone, and character synthesis.

**New role assignments:**

| Task | Model | When |
|------|-------|------|
| Fact extraction (AUDN) | Qwen (local) | After conversations (async) |
| Scoring/embedding | Qwen + code (local) | After extraction |
| Brief retrieval + assembly | Code only | Per-message (runtime) |
| Identity block authoring | Claude | Periodic (after major updates) |
| Character overview | Claude/Collective | Periodic |
| Fact validation | Claude | Before fine-tuning or periodically |
| Conversation | Claude | Real-time |

**Collective review (session 18):**
- Cognitive Scientist: "Behavioral predictions mirror how human memory actually operates — as a predictive engine, not a filing cabinet"
- Narrative Biographer: "The narrator should be the same voice that speaks" — Claude as author and conversant
- Epistemologist: "Separating mechanical extraction from knowledge claims improves epistemic hygiene"
- Pragmatic Engineer: "Zero LLM calls at runtime — lower latency, lower cost, fewer failure modes"
- **Unanimous endorsement** across all four personas

**Status:** Active — supersedes Qwen's narrative role from D-026

---

### D-031: Dynamic Token Budgets — Relevance-Gated, Not Quota-Gated
**Date:** 2026-02-11

**Note: Token allocations superseded by D-035.**

**Decision:** Replace fixed token budget splits (800/1000/800) with dynamic, score-based retrieval. Include all context above a relevance threshold; stop at diminishing returns. Total ceiling of ~5,000 tokens but not a target to fill.

**Rationale:**
Fixed budgets are arbitrary and wasteful. When asking about a pet's health, 600 tokens of career identity context are noise. When asking about trading, episode budget gets filled with irrelevant conversations. Human memory is relevance-gated — you remember what's relevant to the current context, not a fixed quota from each life domain.

**Revised brief structure:**

| Layer | Tokens | Content | Updates |
|-------|--------|---------|---------|
| Core identity | ~400-500 | Behavioral predictions + motivations, universal truths, communication guide | Periodic (Claude writes) |
| Dynamic context | Variable (score-based cutoff) | Topic-relevant facts + episodes, retrieved per-message | Per-message (code) |
| Total ceiling | ~5,000 | Hard cap to prevent noise dilution | — |

**Key change:** The identity block shifts from biography to behavioral predictions. Not "the user is disciplined but impulsive" but "When the user has a trading loss, they're likely to revenge trade — this activates a prove-them-wrong reflex. If they mention a bad day, ask what their rules say before discussing the trade."

**Collective endorsement:** Unanimous. Cognitive Scientist called it "the single most brain-aligned change." Pragmatic Engineer: "Including only what clears a relevance threshold is measurably more efficient and testable."

**Biographer pushback:** 300-400 tokens may reduce a person to a decision tree. Allow up to 500 tokens and include motivational context alongside predictions — not just "he does X" but "because Y drives it."

**Epistemologist pushback:** Tag predictions with confidence — "observed across 40 conversations" vs "inferred from one message." False certainty wearing the mask of personalization is the core risk.

**Status:** Active — requires implementation in `assemble_brief.py`

---

### D-032: Phase 6 — Fine-Tuned Lightweight Model for Behavioral Understanding
**Date:** 2026-02-11
**Decision:** (Planned for Phase 6) Fine-tune a small model (3B-7B) on user's full conversation history to serve as the behavioral memory layer. This model internalizes patterns, communication style, and emotional signatures that fact databases cannot represent. The fact database remains for explicit, correctable ground truth.

**Architecture:**

| Layer | Source | Handles |
|-------|--------|---------|
| Behavioral model | Fine-tuned 3B-7B | Implicit patterns: tone, deflection, intellectualization, emotional triggers |
| Factual ground truth | SQLite + ChromaDB | Explicit facts: names, dates, relationships, corrections |
| Dynamic context | Code retrieval | Topic-relevant facts + episodes per-message |
| Conversation | Claude API | Actual user interaction |

**Prerequisites (must complete first):**
1. Claude-based fact validation of all ~4,700 facts (clean training data)
2. Run retrieval + Claude-authored identity system for 30 days
3. Measure where Claude's responses miss context that retrieval should have provided
4. Fine-tune only against demonstrated gaps, not theoretical ones

**Nightly update cycle:**
1. Import new conversations (code)
2. Qwen processes — extraction, scoring, embedding (async)
3. Flag significant changes for identity block refresh
4. Periodically: retrain fine-tuned model on updated data

**Collective review:**
- Cognitive Scientist (concern): "Fine-tuned model will encode cognitive biases as features without debiasing pass"
- Epistemologist (concern): "No confidence/provenance layer for model-generated claims"
- Pragmatic Engineer (concern): "Complexity cliff — nightly retraining introduces pipeline fragility. Build simpler system first, measure failures, then fine-tune"
- All three recommend deferral until Phase 5 is measured

**Cost estimates (API, based on user's actual usage: ~14 msgs/day, ~50 convos/month):**

| Period | Claude Sonnet | Claude Opus |
|--------|--------------|-------------|
| Daily | ~$0.13 | ~$0.65 |
| Weekly | ~$0.88 | ~$4.40 |
| Monthly | ~$3.83 | ~$19 |
| Yearly | ~$46 | ~$230 |

One-time fact validation: ~$4-5. Monthly identity block generation: ~$0.50.

**Status:** Planned — deferred until Phase 5 is running and measured for 30 days

---

### D-033: Claude Code Session Authoring

**Date:** 2026-02-11 (Session 19)
**Status:** Active
**Supersedes:** D-030 API-based generation (Claude API calls removed; D-030 model role separation principle retained)

**Context:** D-030 specified Claude API calls for identity block generation, requiring an ANTHROPIC_API_KEY and incurring per-call costs. User pointed out that identity blocks are periodic (not per-message), so there's no reason to pay for API calls when the work can be done within Claude Code sessions that are already being paid for.

**Decision:** Identity blocks are authored in Claude Code sessions, not via API:
- `generate_identity_block()` retrieves and displays cluster facts (no LLM call)
- `store_identity_block()` validates (rejection gate) and stores pre-written blocks
- New CLI: `--store-identity "text"` or `--store-identity @filename`
- A dedicated agent within Claude Code writes the block to avoid context muddling
- API-based generation can be re-added later when productizing for other users

**Rationale:**
- Zero additional cost beyond existing Claude Code subscription
- Better quality: Opus 4.6 in Claude Code vs Sonnet via API
- Identity blocks only need regeneration periodically (not per-conversation)
- Keeps the system simple — no API key management, no anthropic SDK dependency for core function
- Script stays mechanical (retrieve, validate, store); narrative intelligence stays in Claude

**Result:** Identity block #13 — first Claude Code-authored block. Passed rejection gate clean on first attempt (Qwen never passed in 12 attempts). 662 tokens, 10 behavioral predictions. End-to-end test: 17/20 pass, 1.00 absence score.

---

### D-034: Project Memory Bootstrap (CLAUDE.md as Project Identity Block)
**Date:** 2026-02-11
**Decision:** Create a CLAUDE.md file in the project root that serves as an auto-loaded project bootstrap for Claude Code sessions. Apply the same three-layer architecture used for personal memory: CLAUDE.md = always-on identity block (~550 tokens), docs = theme layer (retrieved on demand by task relevance), session state = episode layer.

**Why:**
- Each Claude Code session starts blank — no memory of previous sessions
- The project now has 19 sessions of history, 11+ docs (some 60KB+), and 19 scripts
- Reading all docs at session start wastes context window tokens (174KB for top 3 docs alone)
- The Collective reviewed the approach and confirmed the personal memory architecture maps directly: CLAUDE.md is the project's identity block, docs are the theme retrieval layer, session state is the episode layer
- Bootstrap contains only what makes Claude Code efficient: working style contract, architecture diagram, key file references, DO NOT anti-patterns, session protocol
- Biographical details about the user belong in the memory system (identity block), not in the project bootstrap — separation of concerns

**Alternatives considered:**
- Read all docs at session start → rejected (wastes 3,000+ tokens, most content not relevant to current task)
- Generate compressed project brief via API → rejected (same "simpler first" principle as D-033 — hand-written is better at this stage)
- No bootstrap at all → rejected (cold starts waste the first 10 minutes of every session re-orienting)

**Status:** Active

---

### D-035: Identity Block Budget Increase (1,000-1,200 tokens)
**Date:** 2026-02-13
**Decision:** Increase the identity block budget from ~500-700 tokens to ~1,000-1,200 tokens. Offset by reducing theme block (1,000 → 700-800) and episode block (800 → 500-600). Total brief ceiling unchanged (~2,200-2,600 tokens).

**Why:**
- Block #13 hit 662 tokens and the communication guide was only 3 sentences — not a real guide
- The identity block is the highest signal-per-token layer: pre-authored, human-reviewed, gate-tested, adversarially evaluated
- It's the layer that produces the "Seen" factor (validated in fruistrating.docx conversation)
- A proper communication guide needs ~250-350 tokens (situational guidance, tone, pacing, what not to do)
- Block #14 needs room for universal pattern abstraction
- Strong identity predictions reduce the model's need for retrieved theme facts — the behavioral framework lets it interpret fewer facts better
- Theme and episode blocks are dynamically retrieved and may contain noise; identity block has zero noise

**Budget reallocation:**
| Layer | Previous | New | Rationale |
|---|---|---|---|
| Identity | 500-700 | 1,000-1,200 | Pre-authored, validated, always-on |
| Theme | 1,000 | 700-800 | Identity block provides interpretive framework |
| Episode | 800 | 500-600 | Recent context, less critical if identity is strong |

**Communication guide constraint:** The guide must be abstracted from underlying facts. "When processing a negative outcome, trace mechanics before offering perspective" — not "when trading loss, ask about rules." Domain-specific examples introduce bias and situational lock-in. Universal communication patterns only.

**Process note:** Larger identity blocks increase Collective review surface area. Enforce single review cycle with focused feedback to prevent multi-session review spirals.

**Alternatives considered:**
- Keep current budget, compress predictions → rejected (communication guide needs real space, not leftovers)
- Increase total brief ceiling instead → rejected (risk of noise dilution; the constraint forces quality)
- Separate communication guide as its own always-on section → rejected (adds complexity; better as a section within the identity block)

**Status:** Active (supersedes token allocation in D-003)

---

### D-036: Contradiction Classification Is Not Binary (Session 23)
**Status:** Active
**Context:** Blind validation testing of the 50 contradiction detection test pairs revealed that the ground truth labels were too aggressive. The project owner independently labeled 14 pairs and disagreed with 5 of 25 contradiction labels. Every disagreement was on pairs labeled "contradiction" that the owner judged as ambiguous, coexistent, or enrichment.

**Key findings from blind validation:**
1. **Descriptive vs aspirational facts coexist.** "Sleeps 6 hours" (reality) and "prioritizes 8 hours" (intent) are not contradictions — they are different types of claims about the same topic.
2. **Temporal ordering is load-bearing for classification.** The same two facts can be contradiction or enrichment depending on which is older. Timestamps are not optional metadata.
3. **Scope disambiguation is required before judgment.** "Journals before market open" vs "stopped journaling consistently" may refer to different scopes (trading journal vs general). System must match entity and scope before judging.
4. **External context dependency.** Some contradictions are only detectable with knowledge beyond the fact pair itself (e.g., knowing a startup shut down).
5. **Verification gap.** Values stated to the system may not reflect actual behavior (Inherent Incompleteness). The system stores claims, not verified behaviors.
6. **Edge cases exist for nearly every "clear" contradiction.** Could re-read a finished book. Could be healthy with managed kidney disease. Almost nothing is a clean binary.

**Decision:** The contradiction detector defaults to conservative classification. "Ambiguous → route to probe" is the default for anything that is not an unambiguous reversal (e.g., "lives in Austin" → "moved to San Francisco"). Value-replacement facts (account balances, sleep hours, market views) require temporal ordering AND scope matching before classification. The four-way classification (contradiction/enrichment/coexistent/ambiguous) remains, but the system biases toward ambiguous when in doubt.

**Impact on Qwen accuracy:** Qwen's 90% (45/50) result was penalized for calling pairs B, C, D "enrichment" — which the project owner largely agreed with. Adjusted accuracy against owner-validated labels is likely ~95%+. The 100% Opus result was both contaminated (labels visible) and matched a flawed ground truth.

**Implications:**
- The MiniLM similarity threshold (0.55-0.60) remains correct as a filter
- The LLM judgment layer must be more conservative than the original prompt implied
- "Ambiguous" is a valid and expected classification, not a failure mode
- Probe system becomes critical infrastructure, not a nice-to-have
- Test pairs need revision with explicit temporal ordering and scope annotations

**Supersedes:** Nothing. Refines the Phase 2 (contradiction detection) design in TEMPORAL_PROCESSING_REVIEW.md V3.

---

### D-037: Behavioral Data Over Behavioral Prescriptions (Session 24)
**Status:** Active
**Context:** During identity block #14 authoring, the Collective reviewed two versions — a "safe" version (V1, consensus B+) and a "teeth" version (V2, consensus B+/A-). Both versions contained behavioral predictions mixed with prescriptive instructions ("do not minimize," "treat the spiral as diagnostic," "flag without lecturing"). The Epistemologist flagged that prescriptive confidence exceeded evidential support. More fundamentally, the project owner identified that prescriptions are the wrong abstraction for a probability machine.

**Decision:** The identity block provides behavioral data — knowns, unknowns, predictions, and certainties — not instructions for how the AI should respond. The LLM is a probability machine. Given accurate behavioral data, it will infer appropriate responses across novel contexts. Prescriptions constrain the model to anticipated scenarios; behavioral data lets the model compose across unanticipated ones.

**The distinction:**
- **Behavioral data (correct):** "Emotional processing happens through mechanical analysis. Frustration after rule violations turns inward and compounds for days."
- **Behavioral prescription (wrong):** "Do not redirect to emotional support. Help trace which rule broke. Treat the spiral as diagnostic, not emotional."

Both produce reasonable behavior in the scenarios they describe. Only the first produces appropriate behavior in scenarios the block author didn't anticipate — because the model reasons from the data rather than pattern-matching against instructions.

**What the identity block should contain:**
- Knowns — verified behavioral patterns, confirmed facts
- Unknowns — acknowledged gaps
- Predictions — behavioral tendencies as observations
- Certainties — high-confidence anchors

**What it should NOT contain:**
- Opinions — editorial judgments about choices
- Failure cases — specific "don't do this" scenarios
- Response scripts — instructions for AI behavior
- Evaluative validation — endorsing self-narratives

**Why prescriptions don't compose:** The identity block's power is that behavioral predictions compose — orthogonal predictions combine to produce appropriate responses in situations none of them individually anticipated. This composability only works when predictions are data points the model can weight, not directives the model must follow. Prescriptions are rigid. Data is flexible. The model needs flexible inputs to produce flexible outputs.

**Connection to existing principles:**
- Refines D-003/D-035 (brief architecture) — the identity block is the behavioral data layer
- Extends D-030 (model role separation) — the memory system provides data, the reasoning model interprets
- Aligns with "predictions compose" (D-003) — composition requires data, not scripts
- The theme block (facts) and episode block (context) provide situational specifics; the identity block provides stable behavioral framework

**Alternatives considered:**
- Keep prescriptive style (V2 "teeth") — rejected because prescriptions constrain the model and don't compose across novel situations
- Hybrid approach (data + selective prescriptions) — rejected because the boundary is unclear and prescriptions will accumulate over iterations
- Pure fact-list approach — rejected because behavioral predictions (as data, not instructions) are more useful than raw facts for a probability machine

**Status:** Active. Governs all future identity block authoring.

**Supersedes:** Nothing directly. Refines the identity block content model established in D-003, D-033, and D-035.

---

### D-038: Opus Owns All Judgment (Session 26)
**Status:** Active
**Context:** Session 23 tested a two-layer contradiction detection model: Qwen 2.5 14B as first-pass filter (90% accuracy), Opus for hard cases. Session 26 ran a clean blind test with three variants: Qwen single-pass (90%), Qwen iterative refinement (70% — regressed), and Opus blind via Claude Code session (94%). The iterative refinement experiment (inspired by looped LLM research, Ouro/LoopLM) backfired — the second pass made Qwen second-guess correct coexistent/unrelated judgments into false positives.

The critical question emerged: how does the system decide a case is "ambiguous enough" for Opus? Qwen doesn't output confidence scores — it returns confident labels even when wrong. There's no reliable escalation signal. And under BYOS (D-033), Opus judgment in Claude Code sessions costs zero incremental dollars.

**Decision:** Opus handles ALL contradiction judgment. The local model (Qwen) is restricted to extraction, fact classification (event/state), and scoring. No local model judges contradiction pairs. The pipeline is:

1. New state-fact extracted → MiniLM embed (free, local)
2. Query ChromaDB for similar existing state-facts in same cluster (free, local)
3. If similarity >= 0.50 → candidate pair sent to Claude Code session
4. Opus judges: contradiction / enrichment / coexistent / ambiguous
5. Code executes the result

**Why not two-layer:**
- Qwen's failure mode (value-replacement contradictions called "enrichment") has no reliable detection signal at runtime
- 60-70% of MiniLM-surfaced pairs would need Opus escalation anyway
- BYOS model eliminates the cost argument for local judgment
- Adding a Qwen judgment layer creates complexity without meaningful savings

**Session 26 test results (clean blind methodology):**

| Model | Overall | Contradiction | Enrichment | Coexistent | Unrelated |
|---|---|---|---|---|---|
| Qwen 2.5 14B (single) | 90% (45/50) | 84% (21/25) | 100% (10/10) | 100% (10/10) | 80% (4/5) |
| Qwen 2.5 14B (iterative) | 70% (35/50) | 92% (23/25) | 100% (10/10) | 20% (2/10) | 0% (0/5) |
| Opus 4.6 (blind session) | 94% (47/50) | 88% (22/25) | 100% (10/10) | 100% (10/10) | 100% (5/5) |

**MiniLM threshold:** 0.50 (94% recall on contradictions + enrichments, errs toward surfacing candidates rather than filtering them out).

**Opus 3 disagreements with test set:** Pair 11 (book progression: called enrichment, test set says contradiction — defensible per D-036 Principle 6), Pair 12/16 (called contradiction, matched test set but D-036 owner validation disputes). Opus accuracy against owner-validated labels: ~96%+.

**Iterative refinement killed:** Two-pass Qwen destroyed calibration on non-contradiction pairs (coexistent 100%→20%, unrelated 80%→0%). The refinement prompt's nudge toward "does B replace A?" induced false positives. Not viable.

**Refines:** D-030 (model role separation — now sharper: local model never judges), D-033 (Claude Code session execution — now covers all judgment, not just hard cases), D-036 (judgment principles — apply to all pairs via Opus, not selectively).

**Alternatives considered:**
- Two-layer model (Qwen filters, Opus judges hard cases) — rejected because no reliable escalation trigger exists and cost savings are negligible under BYOS
- Iterative refinement as "poor man's loop" — rejected after empirical failure (70% accuracy, worse than baseline)
- Larger local model for judgment (Qwen3 32B, GLM-4.7) — not viable on available hardware (RTX 3080, 10-12GB VRAM)

**Status:** Active. Governs contradiction pipeline architecture.

---

### D-039: Knowledge Tier Classification (Session 28/31)
**Status:** Active
**Context:** The contradiction pipeline (D-038) surfaced a scalability problem: 4,127 state-facts at 0.70 MiniLM threshold produced 100,566 candidate pairs at 0.50 — infeasible for Opus judgment. The solution was to classify facts into knowledge tiers and exclude low-value facts from pairwise operations.

**Decision:** Every fact is classified into one of three knowledge tiers:
- **Identity** — Who the person IS. Biographical anchors, relationships, values, behavioral patterns, durable preferences. Stable over months/years.
- **Situational** — Current mutable conditions. Active projects, ongoing dispositions, living situation, employment. Persists weeks/months.
- **Context** — Conversation artifacts. One-off tasks, specific lookups, third-party observations. Bound to a single conversation.

Context-tier facts are excluded from pairwise contradiction detection (reducing candidate pairs from ~100K to ~1,500 at 0.70 threshold).

**Classification pipeline:**
1. During extraction: Qwen classifies new facts at extraction time (wired into extract_facts.py)
2. Opus side-channel: Opus annotates tiers during contradiction judgment (free — 1,097 facts tiered this way)
3. Periodic Sonnet pass: `reclassify_tiers.py` batches facts through Sonnet for promotion/reclassification (~$1 for full corpus)

**Tier promotion design (Session 31):**
Mechanical recurrence-based promotion was tested and rejected — median recurrence is nearly identical across tiers (identity p50=66, situational p50=44, context p50=48). No threshold can discriminate them. Instead, periodic LLM promotion scans via Sonnet with pre-filters:
- Guard: skip non-user subjects (third-party facts stay at context)
- Guard: skip events + past-state for identity promotion
- Guard: never override Opus-tiered facts
- Promotion-aware prompt biased toward keeping current tier

**Provenance tracking:** `tiered_by` column records which model classified each fact (opus, qwen, sonnet). Qwen demonstrated 37-44% over-promotion rate on identity tier; Sonnet reclassification corrected this.

**Model accuracy on tiering:**
- Opus: most accurate (used as reference), but expensive — reserved for side-channel during contradiction judgment
- Sonnet: accurate enough for batch reclassification (~$0.40 per 1,500 facts)
- Qwen 2.5 14B: systematic over-promotion toward identity tier (44% demotion rate when Sonnet re-checked)
- Qwen 3 14B, Phi-4 14B, Gemma 2 9B: not viable (accuracy and/or speed failures)

**Alternatives considered:**
- Recurrence-threshold-based promotion (tested, rejected — signal can't discriminate tiers)
- Separate promotion_log table (rejected — tiered_by column provides sufficient provenance)
- Parent-child fact hierarchy (rejected — many-to-many cluster assignment is more flexible, per D-026)

**Refines:** D-026 (cluster framework — tiers and clusters are orthogonal axes), D-038 (Opus judgment — tier exclusion reduces pairwise scope)

### D-040: Blind Authoring / Facts-Only Derivation (Session 35)
**Status:** Active
**Context:** Session 35 discovered a severe feedback loop in identity block authoring. Blocks #13 through #16 v3 carried forward ~70-75% inherited text. Of 13 behavioral predictions in v3, zero were genuinely new — all traced back to Block #13 (Session 19) or EWOR (Session 25) with only cosmetic edits. The predictions section had been essentially frozen across 7 generations. Coverage of the identity-tier fact base was ~3-4% (30-50 of 1,377 facts represented).

The root cause: each new block was authored with access to prior blocks, which acted as cognitive anchors. The author edited inherited text rather than synthesizing fresh content from the fact base. A second-order feedback loop was also identified: analysis documents (CHARACTER_OVERVIEW, USER-ANALYSIS) carry forward phrasings from earlier sessions, creating indirect inheritance even in "blind" authoring.

**Decision:** Identity blocks must be authored from raw facts only. The authoring process receives:
1. Identity-tier facts from the database (the 1,377 fact records)
2. Philosophy frameworks (Frankfurt, Taylor, Ricoeur, etc.) as structural lenses
3. D-037 compliance rules (behavioral data, not prescriptions)
4. Token budget and structural specification

The authoring process does NOT receive:
- Any prior identity block text
- Analysis documents (CHARACTER_OVERVIEW, USER-ANALYSIS) — these carry second-order inheritance
- Suggested structure or templates ("When you..." patterns, "CORE + BEHAVIORAL PREDICTIONS" headers)

All claims in the identity block must be inferrable from the facts themselves. Structure should emerge from the content, not from a pre-existing template.

**Validation:** Session 35 blind authoring (v4) produced a block with notably different structure (7 narrative paragraphs, no headers, no repeated patterns), surfaced content never present in any prior block (therapy/AI paradox, environmental scanning, Costco detail, privacy/openness tension, Maslow framework contribution), and covered all 6 holistic identity dimensions.

**Why:** Every sentence in the identity block must earn its place by being re-derived from current data, not by being carried forward from a prior generation. Accuracy alone is insufficient — coverage of the full fact base matters. A block that is accurate but narrow (3-4% coverage) is worse than a block that is accurate and broad.

**Future consideration:** If this process proves effective, formalize as a pre-authoring pipeline step: dimensional sorting of identity-tier facts into holistic categories (self-concept, worldview, relational posture, tension architecture, evaluative framework, introspection meaning) before block authoring begins.

**Refines:** D-033 (Claude Code session authoring — now with blind constraint), D-037 (behavioral data — now with facts-only derivation)

---

### D-041: Audience Principle (Session 36, updated Session 44)
**Status:** Active (updated)
**Context:** Identity block v4 (blind, D-040) produced an accurate psychological portrait, but user identified it as "too much fluff — information that wouldn't objectively help a language model interact with you." Comparison with the EWOR identity block revealed the difference: EWOR included interaction directives ("Do not minimize what happened," "Stay in the mechanics," "Flag the pattern when you see it") that directly changed LM behavior. The v4 block described the person *to* the person, not *to* the AI.

The root question: who is the identity block's audience? If it's the subject, you get self-portraiture — beautiful, accurate, unusable. If it's the AI, every sentence must pass the test: "does this change how the LM responds to this person?"

**Original decision (Session 36):** The audience is the AI system consuming it, not the human subject.

**Updated decision (Session 44):** The audience is the intelligence and understanding the AI needs to take on to communicate naturally with the individual. This is not a wording change — it changes the optimization target. "Write for AI" optimizes for parseability, structure, completeness. "Write for the understanding AI needs" optimizes for *transformation* — the layer should change how the AI thinks, not just what it knows.

Evidence: identity_block_14_v2 ("teeth") produced the best generation across all 18 versions because it wrote to create comprehension in the reader, not to document the subject. "Your debriefs are autopsies" creates the right disposition faster than "when user processes setbacks, they engage in systematic analysis." The first changes how the AI *feels* about interacting. The second gives it a checklist. Feeling is faster and stickier for language models just as it is for humans.

Content must satisfy two simultaneous constraints:
1. **Evidence-grounded (D-040):** Every claim must be inferrable from the fact base. Utility without truth is manipulation.
2. **Understanding-shaping:** Every sentence must change the AI's understanding of how to communicate with this person. Truth without transformation is a dossier.

The valid directive test remains: **a directive is valid if and only if it follows from a behavioral pattern stated in the same block.**

Examples of valid directives: "When you break your own rules, the frustration turns inward. Do not minimize what happened. Help trace which rule broke and why." (behavioral pattern → grounded directive)

Examples of invalid content: "Always respond in bullet points." (prompt script, no behavioral grounding) / "Frankfurt would call these volitional necessities." (academic attribution, zero utility) / "You notice strangers walking too close at Costco." (vivid detail, zero interaction guidance) / "When user reports setbacks, provide structured analysis frameworks." (clinical description that doesn't create understanding)

**Refines:** D-037 (behavioral data — now with understanding-shaping requirement and valid directive test)

---

### D-042: Empirical Budget — Token Allocation Determined by Evaluation (Session 36)
**Status:** Active
**Context:** The original identity block token budget (D-003: three-tier brief at 1,500-2,600 total, D-035: identity block at 1,000-1,200) was a heuristic from Session 20 that calcified into a constraint. With the shift to three-layer architecture (D-043), the question of how to divide tokens across CORE, ANCHORS, and PREDICTIONS had no principled answer — because the right total budget was never empirically determined.

User direction: "I don't want to limit token budget based on our original prediction. I'd be interested in giving both 1,500-2,600 tokens honestly. We should be running an optimization study to see how many tokens this really needs. Is it 500, or is it 5,000?"

**Decision:** Token allocation is determined empirically through optimization study, not preset. The original 1,500-2,600 budget is suspended pending evaluation. Quality per token is the metric.

**Optimization study design:**
1. Generate identity blocks at 500, 1000, 1500, 2500, 4000 tokens
2. Run each through standardized interaction test (5-10 prompts across dimensions)
3. Measure: response accuracy, behavioral prediction hit rate, unnecessary clarification questions, perceived alignment
4. Find the knee of the curve — where additional tokens stop improving interaction quality

**Principle:** Quality over arbitrary budgets. We are looking to create an understanding, within budget. That must be possible.

**Suspends:** D-035 (identity block budget 1,000-1,200), D-003 token allocation (1,500-2,600 total brief)

---

### D-043: Three-Layer Identity Architecture — Separate Authoring Processes (Session 36)
**Status:** Active
**Context:** Comparison of identity block v4 (blind portrait) with the EWOR block (interaction guide) revealed that conflating "who the person is" with "what the person does in specific situations" produces blocks that are either literary (v4) or operational (EWOR) but not both. These are different knowledge types requiring different authoring processes, different fact queries, and different quality criteria.

Additionally, the concept of "epistemic anchors" was identified as a distinct dimension — foundational certainties/commitments that a person reasons FROM. These are not behavioral predictions (what you do) or biographical overview (who you are), but fixed premises that constrain reasoning. An AI that doesn't know these will waste cycles questioning or establishing what the person considers settled.

**Decision:** Identity blocks use a three-layer architecture with separate authoring processes:

**Layer 1 — CORE (Individual Overview):**
Who the person is. Orienting frame. Self-concept, worldview, relational posture, tension architecture. Every sentence passes "does this change LM behavior?" Authored from identity-tier facts at high abstraction.

**Layer 2 — EPISTEMIC ANCHORS:**
Foundational beliefs the person reasons from, not about. Core anchors are always-on — beliefs so foundational that any interaction benefits from the AI knowing them. Sub-anchors are thematically grouped beneath cores and retrieval-activated via the theme layer in assemble_brief.py.

- Core anchor test: a belief that constrains reasoning across 3+ unrelated domains. Always-on.
- Sub-anchor test: can this sub-anchor be irrelevant when its parent core anchor is active? If yes, retrieval-dependent.
- Quality bar: removal of the anchor would cause the AI to make a **category error** — a fundamental misread, not a minor misstep.

**Layer 3 — BEHAVIORAL PREDICTIONS:**
"When you [situation] → [pattern] → [what the AI should do]." Specific situational triggers with behavioral patterns and grounded interaction directives (per D-041 valid directive test). Authored from behavioral/situational facts with triggers and recurrence evidence.

Each layer is a separate authoring process with different fact queries, different synthesis approach, and different review criteria. This prevents the conflation that produced v4's portrait-style output where predictions became literary descriptions.

**Refines:** D-026 (cluster framework — layers provide the query structure for cluster-based retrieval), D-040 (blind authoring — each layer is independently blind-authored from facts)

---

### Extraction Evolution Note (Session 36)
**Status:** Investigation / Pre-Implementation
**Context:** The shift to D-041 (audience is the AI) and D-043 (three-layer architecture) surfaces gaps in the fact extraction schema. The current extraction pipeline classifies facts along five axes: subject, intent, temporal_state, fact_class (event/state), knowledge_tier (identity/situational/context). None of these distinguish between biographical facts (feed CORE), behavioral patterns (feed PREDICTIONS), positional beliefs (feed ANCHORS), or the strength of commitment behind a belief.

**New dimensions identified:**

1. **`fact_type`** (biographical / behavioral / positional / preference) — orthogonal to existing classifications. A fact can be `state` + `identity` + `positional` (anchor candidate) or `state` + `identity` + `behavioral` (prediction candidate). Without this, the authoring step must manually sort 1,300+ identity-tier facts.

2. **`commitment_depth`** (factual / preference / position / conviction) — maps to Frankfurt's hierarchy. `factual` added for biographical facts with no belief dimension (e.g., "lives in Berlin"). A preference is malleable, a position is argued for but revisable, a conviction is foundational and identity-constitutive. Needed to identify epistemic anchor candidates. Current confidence scoring measures extraction confidence, not belief strength.

3. **Trigger/response pair extraction** (deferred) — behavioral predictions follow "When [trigger] → [pattern] → [directive]" but current facts bury triggers in prose. Explicit trigger/response pair extraction would provide structured input for Layer 3 authoring. Deferred until three-layer architecture is validated with current fact base. Must be referenced in future implementation planning.

**Extraction prompt expansion:** Add to "Focus on" list: Reasoning patterns, Emotional triggers, Interaction preferences, Foundational beliefs.

**Meta-fact filtering for authoring queries:** Exclude facts matching identity block references, decision references, collective review mentions, system process descriptions from authoring data views. Add exclusion patterns to config.py.

**Classification model selection:** Haiku selected over Sonnet for fact_type + commitment_depth classification. Three prompt variants tested (A, B, C); Variant B selected by Collective review as most consistent. `classify_facts_haiku.py` created. Full run of ~3,898 facts initiated (~$0.50 estimated cost). Prompt generalization needed for multi-user deployment (current examples are person-specific) — noted, not yet implemented.

**Implementation path:**
1. Add `fact_type` and `commitment_depth` columns to memory_facts (ALTER TABLE)
2. ~~Test Qwen accuracy on 20-30 fact batch with enhanced prompt~~ Skipped — Haiku selected directly
3. ~~If Qwen accuracy >= 70%: wire into extraction prompt for full re-extraction~~ N/A
4. ~~If Qwen accuracy < 70%: defer to Sonnet backfill pass (~$7, ~5 min)~~ Haiku used instead (~$0.50)
5. Opus spot-check on 100 facts for quality validation (~$1.50)
6. **Full re-extraction from scratch** (user direction: no point in only running the 830 pending)

**Re-extraction cost/time estimates:**

| Method | Cost | Time | Notes |
|--------|------|------|-------|
| Sonnet (with 12K cap) | ~$54 | ~19 min | Current truncation preserved |
| Sonnet (full context) | ~$75 | ~19 min | Better extraction, higher cost |
| Qwen local (full re-extract) | $0 | 32-38 hrs | Current pipeline, no new fields |
| Sonnet backfill only (3,956 facts) | ~$7 | ~5 min | Classify existing facts, no re-extraction |
| Opus spot-check (100 facts) | ~$1.50 | ~2 min | Quality validation |

**Compression consideration:** Fact database (3,956 active) and conversation corpus (40,997 messages) are large enough that full re-extraction + enrichment takes significant time/cost. Compression strategies to investigate: conversation summarization before extraction, fact deduplication passes, batched extraction with context windowing. To be formalized as a design decision when approach is chosen.

**Cross-references:** D-041 (audience principle drives what to extract), D-043 (three-layer architecture drives how to classify), D-039 (knowledge tier — complementary classification axis), D-030 (model role separation — Qwen extracts, Sonnet/Opus enriches)

---

### D-044: Scoped Memory — Interaction-Mode Separation with Cross-Scope Anchor Validation (Session 36)
**Status:** Active
**Context:** 25 Claude Code sessions produced 58 active facts, of which 29 (50%) were system-meta contamination — facts about the memory system's own architecture, pipeline phases, extraction processes. 26 of the 58 were classified as identity-tier, meaning they would feed directly into CORE and ANCHORS authoring. The remaining 29 "genuine" facts were lower-quality duplicates of facts already extracted from richer ChatGPT conversations.

The contamination problem goes three levels deep:
1. Direct contamination — facts about identity blocks, design decisions enter the fact base
2. Context poisoning — Qwen extracts from sessions where identity block text is quoted; produces "facts" that are rephrased block content
3. Signal dilution — genuine personal facts from Claude Code are redundant with ChatGPT-sourced facts at lower quality

However, Claude Code sessions contain genuinely useful knowledge about how the user works — engineering preferences, review standards, project management style. This knowledge should inform Claude Code interactions (CLAUDE.md, project briefs) but NOT personal identity blocks.

**Decision:** Facts are scope-tagged by interaction mode. Scopes are determined by the interaction context and relationship, not by subject matter.

**Defined scopes:**
- **Personal:** Conversations where the user is processing, reflecting, exploring as themselves (ChatGPT, Claude.ai)
- **Project:** Conversations where the user is building, directing, reviewing as technical lead (Claude Code)
- **Professional:** (Future) Interactions with colleagues, clients, external parties (Slack, email, work tools)

**Scope rules:**
- Personal-scope facts feed identity blocks (CORE, PREDICTIONS)
- Project-scope facts feed project briefs (CLAUDE.md automation — future)
- Core anchors are identified by **cross-scope recurrence** — patterns that appear independently in 2+ scopes earn anchor status structurally, not by assertion
- Anchors bridge all scopes — they appear in both personal identity blocks and project briefs

**Cross-scope anchor validation:** The strongest mechanism for identifying core anchors. If "directness" appears in personal relationship discussions (ChatGPT), project review sessions (Claude Code), and trading decisions — that's cross-domain evidence from independent interaction modes. The scopes ARE the test environments. Recurrence across them is the evidence. This is structural validation, not model classification.

**Implementation:**
- Add `scope` column to `memory_facts` — derived from `conversations.source` mapping
- Source mapping: `chatgpt`/`claude_web` → personal, `claude_code` → project
- Authoring queries filter by scope; anchor queries explicitly join across scopes using embedding similarity
- 29 meta-contamination facts from Claude Code sessions to be superseded
- 11 pending Claude Code extractions excluded from personal extraction pipeline

**CLAUDE.md loop guard (noted, deferred):** If project-scoped facts eventually feed CLAUDE.md automatically, extraction from Claude Code sessions must filter out CLAUDE.md-derived content to prevent amplification loop. Mitigation: extract only from user messages in Claude Code sessions, not assistant messages (which incorporate injected CLAUDE.md).

**Refines:** D-039 (knowledge tier — scope is orthogonal to tier), D-043 (three-layer architecture — scope determines which facts feed which layer)

---

### D-045: Falsification-Based Axiom Validation — Negation Search + Recursive Evidence (Session 38)
**Status:** Active
**Context:** Epistemic axiom formalization (Session 38) revealed that most axioms have thin or zero direct fact provenance — they are synthesized from cross-domain behavioral patterns, not derivable from individual facts. Axiom identification is a synthesis problem, and the Session 37 Collective review showed that initial LLM-generated axioms required substantial human revision (Anchors 5 and 6 were materially rewritten). The question: is there a structured, non-black-box method for identifying and validating axioms that reduces dependence on human review?

**Decision:** Axiom validation uses Popperian falsification. If an axiom claims to be universally true for the individual, its negation should not be observable in the fact base. The pipeline generates negations, searches for counter-evidence, and classifies results.

**The Pipeline (5 steps):**

1. **Generate candidate axiom** from cross-domain behavioral cluster. Take high-commitment behavioral facts, cluster by embedding similarity ACROSS domains (not within), and for each cross-domain cluster ask the LLM: "What underlying belief would produce all of these behaviors?"

2. **Recursive evidence search:** Use the candidate axiom text to search back into the full fact base. If the search surfaces supporting facts from NEW domains not in the original cluster, the axiom is strengthened. If it only finds the same cluster, the axiom may be domain-specific, not universal — narrow or reject.

3. **Edge-case test:** Retrieve facts from the individual's least-represented domains. Check whether the axiom holds there. An axiom that only applies to well-represented domains (e.g., trading, tech) but not to underrepresented ones (e.g., relationships, health) is over-broad. Narrow until it holds universally for the individual. (Methodology from Anchor 5 review — existential thinking counterexample caught the over-broad "thinking must change behavior" claim.)

4. **Failure-mode test:** Generate the negation of the axiom. Search the fact base for evidence of the negation. Classify results as:
   - **Violation:** The axiom holds, but the individual violated it. (Trading spirals don't refute Axiom 6 — they're predicted violations. The system knew the axiom, the individual broke it under pressure.)
   - **Refutation:** The axiom doesn't actually hold. The individual genuinely valued/endorsed the negation. (Existential thinking refuted the original Anchor 5 — it wasn't a violation, it was a domain where the axiom was simply wrong.)
   The violation/refutation distinction is critical. If ALL counter-evidence is violations, the axiom is validated (and the violations become PREDICTIONS layer material). If any counter-evidence is a refutation, the axiom needs narrowing or rejection.

5. **Collective review** (for ambiguous results only): Steps 2-4 produce clear signal in most cases. Zero negation matches = strong validation. Multiple strong negation matches = clear challenge. The gray zone — ambiguous matches where violation vs. refutation is unclear — is where the Collective review adds value.

**Signal distribution:**
- Zero strong negation matches → axiom validated (empirical evidence from Anchor 5: negation search returned zero counter-evidence)
- Multiple strong negation matches → axiom challenged, narrow or reject
- Ambiguous middle → flag for Collective review or human judgment

**Why this is non-black-box:** Step 1 (candidate generation) is LLM synthesis and therefore probabilistic. But steps 2-5 provide empirical, auditable validation. The axiom generates predictions about what other facts should and should NOT exist, and the system checks. That's falsifiable — the whole point.

**Tested empirically:** Anchor 5 negation search ("analysis within a decision context that didn't change the decision, valued anyway") returned zero strong matches against 1,421 identity/conviction facts. The closest hit ("Values the perspective offered by AI, even when it doesn't always reach the right conclusions") was about valuing AI interaction process, not about valuing indecisive analysis. Results actively supported the axiom rather than challenging it.

**Implications for external user pipeline:** This protocol can run without human intervention for the clear cases (steps 1-4). The Collective handles the ambiguous middle (step 5). A three-stage review process (initial gen → Collective first pass → user feedback) maps directly: steps 1-4 produce the initial generation, step 5 is the Collective first pass, user feedback handles anything the Collective couldn't resolve.

**Extraction methodology improvements (from Session 37 review):**
- Edge-case testing instruction for extraction prompts: "Test candidate anchors against edge cases. If the candidate can be shown to not apply in a plausible domain of the person's life, it's over-broad. Narrow until it holds universally for that person."
- Failure-mode testing instruction: "Test candidate anchors against the person's failure modes — does the anchor still describe how they operate when they're at their worst, or only when they're at their best? An anchor that only holds during good behavior may be an aspiration, not an axiom."

**Cross-references:** D-024 (Collective review — handles ambiguous step 5), D-041 (audience principle — axioms must be LM-actionable), D-043 (three-layer architecture — axioms feed ANCHORS layer), D-044 (scoped memory — cross-scope recurrence is structural anchor validation, complementary to falsification)

---

### D-046: Cheap Constraint, Expensive Discrimination — Cost-Layered Generation Pipeline (Session 38)
**Status:** Active
**Context:** During Session 38 three-layer authoring, the Collective review step was generating substantive new content (EXTERNAL CORRECTION prediction, RESPECT sharpening) rather than just validating existing content. This exposed a cost architecture problem: if the Collective (expensive) is routinely inventing content that the generation step (cheap) should have produced, every pipeline run requires an expensive non-deterministic review step. That doesn't scale.

**Decision:** The pipeline uses cheap operations to constrain the generation space and expensive operations only to discriminate within the remaining ambiguity. The goal is to maximize the work done at the cheap layer so the expensive layer handles a small, well-defined set of genuinely hard cases.

**The layers:**

1. **Cheap — Constrain (extraction, clustering, semantic search, checklists):**
   - Generate candidates from facts using structured prompts with behavioral domain checklists
   - Identify coverage gaps (D-020 active probing) by checking generated output against expected domains
   - Run D-045 falsification (negation search, recursive evidence) — embedding operations, pennies
   - Post-generation validation: did the output cover success response, setback response, feedback reception, external correction, interpersonal pacing, group dynamics, self-monitoring, etc.?
   - Flag thin areas for targeted re-generation before expensive review
   - Models: Haiku, Qwen, embedding operations

2. **Expensive — Discriminate (Collective review, Opus judgment, human review):**
   - Resolve genuinely ambiguous cases from D-045 (violation vs. refutation gray zone)
   - Catch abstraction-level inconsistencies (domain-specific vs. general patterns)
   - Validate that the generation prompt's behavioral domain checklist is complete
   - Identify patterns the cheap layer structurally cannot extract (cross-domain synthesis)
   - Models: Opus, Collective multi-perspective review, human-in-the-loop

**The key insight:** Generation prompt quality determines Collective review cost. Every content addition the Collective makes during review is a signal that the generation prompt was missing a question. The fix is to improve the prompt, not to always run the Collective.

**Evidence from Session 38 authoring:**
- Collective added EXTERNAL CORRECTION to PREDICTIONS — the generation prompt should have included "how does the person handle being told they're wrong by someone else?"
- Collective sharpened RESPECT — the generation prompt should have included "what specific behaviors constitute their interpersonal standards?"
- Collective restructured PREDICTIONS from domain-specific to general patterns — this is an architectural decision that the generation prompt should encode as format specification
- All three were cheap-layer failures that the expensive layer caught. Once encoded into the prompt, they won't recur.

**Pipeline implication:** Each Collective review round produces generation prompt improvements. Over iterations, the cheap layer handles more and the expensive layer handles less. The Collective's role evolves from "generate missing content" to "validate nothing was missed" — which is a much cheaper operation even at the expensive tier.

**For new user pipelines:** First run will need heavier Collective involvement (new person, thin data, uncalibrated prompts). But the prompt improvements from User A's authoring carry over — the behavioral domain checklist, the general-pattern format, the D-045 falsification protocol. Each subsequent user benefits from prior users' generation prompt improvements.

**Cross-references:** D-024 (Collective review), D-030 (model role separation — extends to cost tiers), D-045 (falsification — cheap-layer validation)

---

### D-047: MCP Server Architecture — Identity as Resource, Retrieval as Tool (Session 39)

**Context:** The pipeline produces identity layers and a fact database, but needed a runtime integration point for MCP-compatible AI clients (Claude Desktop, Claude Code, Cursor, etc.). Key question: when should memory be injected — always, on-demand, or hybrid?

**Decision:** Hybrid approach using MCP's two mechanisms:

1. **Identity layers as MCP Resource** (`memory://identity`) — always available to the client. Client-controlled: Claude Desktop can auto-include it, users can reference with `@base-layer:memory://identity`.

2. **Memory retrieval as MCP Tool** (`recall_memories`) — model-controlled, called on demand. Embeds the query locally (~50ms), searches ChromaDB (~50ms), returns relevant facts + episodes. Zero API cost.

**Why hybrid?** Identity layers (~3,500 tokens) are worth paying for in every conversation — that's the product. But theme + episode retrieval (~1,400 tokens) is only useful when the conversation touches personal topics. If nothing is injected, the AI doesn't know it should call the tool (chicken-and-egg). Identity layers solve this by giving the AI enough context to recognize when deeper recall would help.

**Implementation:** `scripts/mcp_server.py` with lazy-loaded heavy imports for fast startup. Reuses existing retrieval from `assemble_brief.py`. Entry point: `baselayer-mcp`. No API key needed — all local, zero ongoing cost.

**Cross-references:** D-003 (three-tier brief — MCP splits tiers across Resource vs Tool), D-043 (three-layer architecture — layers served as Resource), D-046 (cheap constraint — retrieval is the cheap layer)

---

### D-048: Claude Code Identity Extraction — Conversation Abstraction + Identity-Only Mode (Session 41)

**Context:** D-044 excluded Claude Code sessions from personal identity extraction because 50% of extracted facts were system-meta contamination. However, Claude Code sessions contain genuine identity signals — how the user works, their decision-making patterns, communication style, values. These are personal identity facts trapped in a project context.

The challenge is twofold:
1. Claude Code sessions are ~90% code blocks, tool output, file diffs, and technical artifacts — noise for identity extraction
2. Even after stripping technical content, the extraction prompt needs to specifically target identity-relevant facts and reject project-specific ones

**Decision:** Two-stage identity extraction from project-scope conversations.

**Stage 1 — Conversation Abstraction (`_abstract_project_conversation`):**
- Strip all fenced code blocks (```)
- Strip all XML-style tool output blocks
- Strip file diffs and patch content
- Keep ALL user messages (directives, feedback, decisions = identity signal)
- Keep only short assistant messages (<500 chars after stripping) — summaries, questions, clarifications
- Result: a "decision conversation" stripped of technical noise

**Stage 2 — Identity-Only Extraction:**
- Specialized prompt that explicitly targets: working style, communication preferences, values, cognitive patterns, leadership style, personality traits
- Explicit exclusion instructions: no software architecture, no technical decisions, no tool/library/framework facts
- Post-extraction contamination filter: keyword blocklist catches facts mentioning "memory system", "pipeline", "chromadb", "sqlite", "mcp server", "baselayer", "identity block", "haiku", "sonnet", "ollama", "d-0", etc.
- Facts tagged `scope='personal'` because they describe who the person IS, despite coming from a project context

**Implementation:**
- `extract_facts.py`: New `--identity-only` flag + `--source` filter
- CLI: `baselayer extract --identity-only` (defaults to claude_code source)
- `store_fact()` now accepts and stores `scope` parameter
- `get_conversations_to_process()` now supports `source_filter`
- `config.py`: `AUTHORING_EXCLUSION_PATTERNS` expanded to catch cross-source contamination from personal conversations about Base Layer

**Also fixed:** `store_fact()` was not setting `scope` at all — existing facts likely have `scope=NULL`. Scope is now derived from `SCOPE_SOURCE_MAPPING` at extraction time. Existing facts need a backfill.

**Cross-references:** D-044 (scoped memory — this extends it), D-040 (blind authoring — exclusion patterns prevent contamination at authoring), D-046 (cheap constraint — abstraction is the cheap pre-filter, extraction LLM does the discrimination)

---

### D-049: OpenRouter Proxy Design (Session 41)

**Context:** Base Layer captures identity only from imported conversation exports. Users have conversations across many providers (ChatGPT, Claude, Gemini, local models) daily. Without a live capture mechanism, the system always operates on stale data.

**Decision:** Build a custom aiohttp proxy server (~400 LOC) that sits between the user's client and any OpenAI-compatible API endpoint. Records all conversations to SQLite in real-time. Optional dependency — Base Layer works without it.

**Why custom over LiteLLM:** LiteLLM is 50K+ LOC with 300+ provider adapters. We need ~400 LOC: intercept, stream-through, record. Adding LiteLLM as a dependency triples the install footprint for a feature most users won't use initially.

**Architecture:** Two modes (transparent proxy, OpenRouter gateway). Session tracking via conversation_id header or auto-generated. Streaming support via SSE passthrough. Source tagged as `openrouter_proxy` for scope mapping. SQLite WAL mode for concurrent reads during recording.

**Status:** Designed, not built. ~3 hours estimated. See `docs/reviews/OPENROUTER_PROXY_DESIGN.md` for full spec.

**Cross-references:** D-047 (MCP server — proxy feeds the same database MCP reads from), D-044 (scoped memory — proxy conversations get source-based scope)

---

### D-050: CORE Layer Restructuring — Communication Guide, Not Biography (Session 42)

**Context:** CORE layer scored weakest in evaluation (User A 77.3%, User C 63%). Reading the output, the problem was clear: CORE reads as a compressed biography ("User, 31, leads [startup]..."). It tells the AI WHO someone is but not HOW to engage with them. The AI reads it passively — nothing in CORE changes how it responds.

Meanwhile, ANCHORS (permanent constraints) and PREDICTIONS (triggered patterns) are both directive — they tell the AI what to DO. CORE was the only layer that didn't change AI behavior.

**Decision:** Restructure CORE from "biographical overview" to "communication and operating guide." Same facts, different synthesis angle.

**New CORE structure:**
1. Communication approach — reasoning style, information delivery preference, abstraction level, feedback mode
2. Context modes — how engagement shifts across personal/professional/creative domains
3. Narrative orientation — temporal processing mode, storytelling patterns, relationship to past/future
4. Essential context — biographical facts that change AI behavior (compressed, directive framing)

**Layer delineation (confirmed):**
- ANCHORS = "What are this person's non-negotiable reasoning constraints?" (permanent)
- CORE = "How does this person operate across contexts?" (present + narrative)
- PREDICTIONS = "What will this person do in specific situations?" (situational/triggered)

**Overlap risk:** LOW — these are different temporal scopes with different directive types. CORE is the general operating manual; PREDICTIONS are situation-specific triggered responses.

**Relationship to D-037:** D-037 says "behavioral data over behavioral prescriptions." The CORE rewrite makes CORE directive but not prescriptive — it describes HOW the person operates (data about communication style) rather than telling the AI what to do in specific situations (prescriptions). D-041's "valid directive test" governs: if knowing this wouldn't change AI behavior, delete it.

**Token budget:** Not arbitrarily capped. Content determines length. The 3,500-token identity budget was set for compression quality; if restructured CORE produces richer content, the budget grows to fit.

**Implementation:** Replacement prompt designed in `docs/reviews/LAYER_DELINEATION_REVIEW.md`. Prompt applied to `author_layers.py` in Session 43 (4-section directive: Communication Approach, Context Modes, Narrative Orientation, Essential Context). Next: regenerate CORE layer (`baselayer author --layer core`), compare output to old biographical version.

**Cross-references:** D-037 (behavioral data — refined, not contradicted), D-041 (audience principle — the "valid directive test" applies), D-042 (empirical budget — token allocation determined by evaluation), D-043 (three-layer architecture — this restructures one of the three layers)

---

### D-051: Communication Synthesis Pass (Session 42)
**Status:** Superseded by D-054

**Original design:** Single Sonnet call after layer generation to produce cross-layer communication directives. Patterns visible only when reading all three layers together.

**Why superseded:** The agent architecture (D-054) absorbs this function. Layer agents confer with each other (identifying overlaps, gaps, tensions), and the Collective reviews all layers together for coherence. These two mechanisms together produce everything D-051 was designed to deliver — without an additional pipeline step.

---

### D-054: Agent Architecture for Layer Authoring (Session 44)
**Status:** Active (implemented Session 46)

**Context:** Session 44 review of all 18 identity generations revealed that the three-layer architecture improved structure but lost voice quality. The best single generation (identity_block_14_v2 "teeth") had specificity and attitude that the current pipeline doesn't produce. Root cause: Sonnet generates each layer in isolation, producing clinical descriptions instead of understanding-shaping content. The Collective can only feed notes back — it can't shape voice. And blind regen means Sonnet starts fresh each time without a voice target.

Cross-layer transcoders research (Lange et al. 2026) identified a parallel risk: compressed representations can produce correct behavior while misrepresenting the actual computational pathway — "unfaithful compression." Identity layers face the same risk: behaviorally correct output that doesn't faithfully represent the underlying fact structure.

**Decision:** Replace the current pipeline's review-only Collective with a multi-agent architecture where layer-specific agents own their sections and a Collective ensures cross-layer coherence.

**Pipeline:**
1. **Sonnet generates** all three layers blind (from facts only — D-040/D-053 preserved)
2. **Three Opus layer agents** each take their section — refine, rewrite, check faithful compression
3. **Layer agents confer** (unsupervised, one round) — read each other's work, produce free-form cross-layer notes
4. **Collective reviews** everything — layers + conference notes. Quality AND coherence. Guides with design principles, not exemplar language.
5. **Agents revise** under Collective guidance — final output IS the agent work, not a Sonnet reinterpretation

**Layer agent identity:** Each agent is defined by its layer's purpose, not a persona. The ANCHORS agent IS the epistemic foundation. The PREDICTIONS agent IS the behavioral model.

**Collective role:** Quality + coherence. Whether 4 personas or a single voice needs evaluation testing.

**Overwatcher (concept, not designed):** A separate entity with access to all historical versions. Detects identity drift without fact-base support. Categorizes contradictions: data extraction error vs. genuine human complexity vs. deception. Design deferred.

**Key constraints:**
- Sonnet never sees its own prior output (D-053 preserved)
- Opus agents do not see prior cycle agent work — each cycle starts fresh
- No exemplar language passed between cycles — Collective guides with principles only
- Within a cycle, agents persist and can edit directly (not just review)

**Model assignment:** Sonnet generates, Opus judges/refines. When user is in Claude Code, Opus work is Claude Code = zero API cost.

**Absorbs:** D-051 (Communication Synthesis) — agent conference + Collective coherence review replaces the planned synthesis pass.

**Open (deferred):**
- Cycle triggers — what causes a full regeneration
- Overwatcher implementation
- Token budget interaction with agent rewrites
- Unfaithful compression detection methodology

**Cross-references:** D-041 (audience reframe — agents write for the understanding AI needs), D-043 (three-layer architecture preserved), D-053 (blind generation preserved for Sonnet), D-024 (Collective — role updated to quality + coherence)

**Implementation (Session 46):**
- Pipeline infrastructure: `scripts/agent_pipeline.py` (run management, artifact I/O, Sonnet orchestration, deployment)
- CLI: `--agent-pipeline`, `--manual-agents`, `--resume-agents DIR` flags on `baselayer author`
- Config: `AGENT_DEFINITIONS_DIR`, `AGENT_RUNS_DIR` constants in `config.py`
- True agent isolation via Task subagents (separate context windows, no cross-visibility)
- First cycle (001): Overall 78.4/100 (ANCHORS 82.3, CORE 77.3, PREDICTIONS 75.8). ~245K tokens, ~$0.07 API cost.
- Artifact trail: 13 numbered files per cycle in `data/identity_layers/runs/cycle_NNN_timestamp/`
- No feedback loop: injectable blocks contain zero pipeline metadata. Agent definitions are static methodology docs.
- **Feedback loop caught and fixed (Session 46, later):** Collective "strengths to preserve" list was incorrectly fed into agent refinement prompts as generation instructions. This is anchoring — the evaluation artifact became a contamination vector. Fixed: `build_agent_prompt()` in `agent_pipeline.py` enforces D-053 by construction. Agent prompts receive only: agent methodology, source facts, current-cycle Sonnet output, and Collective fix *principles*. Never prior layer text or specific sentences to reproduce.
- **D-055 applied:** Domain cap (25% max per domain) and incompleteness signaling added to generation prompts.

---

### D-055: Domain Balance + Incompleteness Signaling (Session 46)
**Status:** Active

**Context:** Two problems discovered during v4 pipeline execution:

1. **Domain over-indexing:** Trading facts constituted 39% of behavioral identity-tier facts reaching the PREDICTIONS generator, despite per-category caps at 15. Trading facts are spread across every category (habit, skill, negative_trait, value, preference), bypassing the category-level cap. The CORE prompt already says "no domain > 25%" but the input data was skewed before reaching the prompt.

2. **False completeness:** All three layers present their content as comprehensive. When data coverage is uneven (heavy trading, sparse personal/relational), the layers over-infer from thin domains rather than acknowledging gaps. This creates false confidence that compounds across cycles.

**Decision:** Two mechanisms:

**Domain cap (retrieval level):** `cap_by_domain()` in `author_layers.py` applies after `cap_by_category()`. Keyword-based domain classification (configurable in `config.py`). No domain's facts can exceed `AUTHORING_MAX_DOMAIN_PERCENT` (default 25%) of total facts per layer. Lowest-priority facts (last in sort order) dropped first.

**Incompleteness signaling (prompt level):** Each generation prompt now includes an INCOMPLETENESS instruction. ANCHORS: mark thin-support axioms with [THIN DATA]. CORE: compress over-represented domains, keep sparse domains brief. PREDICTIONS: mark weak cross-domain claims with [THIN IN: domain], don't present single-domain patterns as cross-domain.

**Result:** PREDICTIONS trading went from 39% → 32%. CORE trading at 23%. Prompts now explicitly request honest data-gap acknowledgment.

**Why not stricter cap?** The 25% cap is a floor, not a ceiling. Some trading facts describe genuinely cross-domain behavioral patterns (e.g., "stops out early" is an early-exit pattern that manifests beyond trading). Over-aggressive filtering would lose real signal. The incompleteness signaling is the complementary mechanism — let the generator see the skew and be honest about it.

**Cross-references:** D-040 (blind from facts), D-041 (every sentence changes behavior), D-053 (blind generation — no prior output in prompts)

---

### D-056: Fact Quality Normalization (Session 47)
**Status:** Active

**Context:** 57% of 4,106 extracted facts start with "The user is..." — 580 use "interested in", 286 use "considering", 208 use "concerned about." These template constructions are LLM extraction artifacts that waste tokens, inflate stop words, and make keyword co-occurrence scoring unreliable. The scoring system needs structured, keyword-rich text, but the extraction prompt produces unconstrained natural language. These two systems are misaligned.

Specific quality issues discovered:
1. **Tense inconsistency:** "is doing" vs "was doing" vs "enjoys" — no normalization
2. **Vague/generic language:** "interested in X", "working on X" — mostly stop words, can't be scored
3. **Hedging language:** "likely to", "seems to", "may be" — epistemically weak, adds nothing
4. **LLM extraction artifacts:** "is someone who..." — zero information density
5. **Verbosity:** Facts that could be 5 words written as 20

Root cause: the extraction prompt produces unconstrained free-text sentences, and the scoring system tries to extract signal via keyword co-occurrence. When facts are full of generic words, recurrence counts inflate because generic words match everything. This was the direct cause of the Session 46 stale scoring bug (coffee: 677→21, works out: 743→0).

**Decision:** Four-tier normalization approach:

**Tier 1 — Scoring-time normalization (immediate, no re-extraction):**
- Strip "The user is [gerund]" prefixes in `get_fact_keywords()` before keyword extraction
- Add `lexical_density` as a quality signal on `memory_facts`

**Tier 2 — Extraction prompt restructuring (next extraction run):**
- Replace free-text `fact` field with structured `{subject, predicate, object, temporal}` tuple
- Constrained predicate vocabulary (~25 canonical predicates: trades, values, skilled_at, struggles_with, etc.)
- Few-shot examples (research shows 1-3 examples jump format accuracy from 0.27 to 0.50)
- Negative instruction list ("Do NOT produce 'The user is interested in...'")

**Tier 3 — Quality gate (new pipeline step between extraction and storage):**
- Reject facts below lexical density threshold (< 0.45)
- Reject hedging language ("seems to", "likely", "may be")
- Require at least one proper noun, number, or domain-specific term
- Batch normalize existing 4,106 facts via Haiku (~$1-2)

**Tier 4 — Canonical predicate vocabulary (structural):**
- 20-30 predicates covering all identity-relevant relationships
- KGGen-style iterative clustering for entity deduplication
- Stored `normalized_text` column for scoring/retrieval

**Research basis:** Surveyed Mem0 (subject stripping, AUDN dedup), Zep (graph-based entity/edge normalization), Letta (self-editing memory), KGGen (NeurIPS 2025 — extract freely then normalize), Wikidata (30 constraint types, statement ranking), ConceptNet (34 fixed relations, lemmatization). Key insight: AI memory systems handle quality structurally (graph edges, dedup, self-editing), while knowledge graphs enforce quality at the schema level. Base Layer needs KG-style normalization applied to its natural language fact store.

**Cross-references:** D-015 (recurrence + depth scoring), D-040 (facts-only derivation), D-055 (domain balance)

Also: Updated scoring anti-pattern documentation. Stale recurrence scoring was caused by algorithm improvements (stop word additions, co-occurrence tightening) without re-running scores. Session 47 added expanded stop words and re-scored all 4,106 facts. New anti-pattern: NEVER modify scoring algorithm without mandatory re-run.

**Tier 2 Implementation (Session 48):**

Eval harness tested 4 extraction prompt variants (A/B/C/D) on 16 conversations. Variant D (structured predicates + subject stripping + temporal precision + few-shot + density directive) won the Collective review with combined 85/100. Won 3 of 4 Collective personas (Cognitive Scientist, Epistemologist, Pragmatic Engineer). Automated scoring: B edged D on aggregate (0.768 vs 0.744), but Collective found D better for downstream processing quality.

Changes implemented:
- `config.py`: Added `CONSTRAINED_PREDICATES` — 31 canonical verbs
- `init_database.py`: Added `predicate`, `object_text`, `qualifier` columns to `memory_facts`
- `extract_facts.py`: New Variant D prompt with structured `{subject, predicate, object, qualifier}` schema. New functions: `normalize_predicate()` (alias mapping table), `reconstruct_fact_text()` (builds clean fact_text from structured fields), `_predicate_to_intent()` (backward compat). Schema migration via `_ensure_structured_columns()`. Both main extraction and identity extraction (D-048) updated.
- `assemble_brief.py`: Removed first-6-words dedup hack (workaround for template facts that structured extraction eliminates). Kept 40% word overlap check.
- `store_fact()`: Now stores `predicate`, `object_text`, `qualifier` in new DB columns.

Key design: `fact_text` is reconstructed as `"{subject} {predicate} {object}"` WITHOUT qualifier. Qualifier stored separately. This keeps fact_text clean for scoring, dedup, and domain matching — zero downstream breakage.

Existing 4,106 facts retain NULL in structured columns. New extractions populate them.

---

### D-058: Personalization Trap Preamble (Session 50)
**Status:** Active

**Context:** Research (Fang et al., arXiv:2510.09905) shows that rich identity profiles produce LARGER divergence in emotional reasoning. The richer the profile, the more the model diverges from baseline behavior — sometimes helpfully (calibrated responses), sometimes harmfully (over-applying patterns to novel situations). Base Layer injects the richest identity profile of any system (~5,000 tokens with three-layer identity + themes + episodes). This means it must also be the most careful about mitigation.

The PREDICTIONS layer is most at risk — it contains emotional/behavioral patterns with explicit detection signatures and response directives. A model could over-apply these patterns to situations where the user is demonstrating growth, change, or new behavior.

**Decision:** Add calibration instruction to BRIEF_INSTRUCTION preamble: "Identity context informs — it does not determine. People evolve. If the user presents something that doesn't match their profile, engage with what they're saying now. Do not over-apply behavioral patterns to novel situations."

This is a lightweight intervention (~35 tokens) that doesn't reduce the identity signal but instructs the model to treat identity as context, not constraint. The existing instruction "If context contradicts the user, trust the user" handles explicit contradictions; the new preamble handles the subtler case where the user isn't contradicting but is simply evolving.

**Cross-references:** D-041 (audience principle), D-055 (domain balance)

---

### D-059: Keep Trading Data in Source Corpus (Session 52-53)
**Status:** Active

**Context:** Trading facts represent 15.4% of identity-tier facts (457/2,963). Session 51 found that no-trading predictions were arguably better cross-domain identity patterns, raising the question of whether trading data should be removed from the identity model entirely. The user's position: "System abandonment is only relevant in trading... far too much focus on trading as part of my identity."

**Decision:** Keep all trading data in the source corpus. The pipeline handles domain balance through two existing mechanisms:
1. **Tiering** — granular trading facts (specific indicators, individual setups) demoted from identity to situational tier. Only behavioral/positional trading facts remain at identity tier.
2. **Authoring** — D-055 domain balance cap (25% per domain) prevents any single domain from dominating layer content. No-trading predictions used as primary PREDICTIONS layer; trading-specific patterns available as optional domain overlay.

No data deletion. The pipeline's editorial judgment happens at tiering and authoring, not at ingestion. This preserves the highest-resolution behavioral data source while preventing domain-specific patterns from masquerading as cross-domain identity.

**Why:**
- Deleting data is irreversible; editorial decisions at tiering/authoring are re-runnable
- Trading provides genuine behavioral signal (analysis paralysis, system abandonment, perfectionism) that validates cross-domain when stripped of trading-specific context
- Pipeline already has the mechanisms (D-055 cap, tier demotion) — this is an editorial decision, not a quality decision

**Alternatives considered:**
- Delete trading facts from extraction → rejected (irreversible, loses behavioral signal)
- Separate trading corpus → rejected (adds complexity, same result achievable via tiering)

**Cross-references:** D-055 (domain balance), D-039 (knowledge tier classification)

---

### D-057: Batch API Re-extraction (Session 50)
**Status:** Active

**Context:** All 4,106 existing facts were extracted with the old free-text prompt (pre-D-056). The Variant D structured extraction (D-056 Tier 2, 85/100 Collective) needs to be applied to ALL 1,892 conversations. Sequential extraction via `baselayer extract` would take hours and cost full API pricing. The Anthropic Message Batches API offers 50% cost reduction for asynchronous processing.

**Decision:** Three-phase CLI workflow via `scripts/batch_extract.py`:
- `--submit`: Build Variant D prompts for all conversations, submit as a single batch
- `--status`: Poll batch processing status
- `--process`: Reset old extraction data, stream results, validate/normalize/store

Key design choices:
1. **Shared prompt builders** — batch_extract.py imports `build_extraction_prompt()` and `build_identity_extraction_prompt()` from extract_facts.py. No prompt drift.
2. **AUDN dedup during processing** — each stored fact is immediately available for dedup of subsequent facts (same as sequential path)
3. **v4 data isolation** — runs against `memory_system_v4/` via `MEMORY_SYSTEM_ROOT` env var. V3 data preserved as control condition.
4. **D-021 compliance** — user corrections survive the reset
5. **Batch state persistence** — batch_id saved to `batch_state.json` so user can submit, close terminal, return later

Cost: ~$2 for 1,087 conversations (Haiku Batch pricing). Resolves release blocker #20.

**Cross-references:** D-056 (Variant D extraction), D-044 (scoped memory), D-021 (user corrections)

---

### D-052: Multi-Provider LLM Support (Session 43)

**Context:** The entire pipeline is hardcoded to Anthropic — Haiku for extraction/classification, Sonnet for tiering/authoring, Opus for Collective review. A user without an Anthropic API key cannot use Base Layer at all. This contradicts the third manifesto pillar ("Same Mind, New Model") and limits the user base. Additionally, testing and optimizing only for Claude means quality claims are unverified on other models — cross-provider testing would make evaluation results more legitimate and credible.

**Decision:** Architect for multi-provider support. The pipeline should work with Anthropic, OpenAI, and Google models at minimum.

**Current state (Anthropic-locked):**
| Step | Current Model | API |
|------|--------------|-----|
| Extract | Haiku | Anthropic |
| Classify | Haiku | Anthropic |
| Tier | Sonnet | Anthropic |
| Author layers | Sonnet | Anthropic |
| Collective review | Opus | Anthropic |
| Contradictions | Manual (no API) | N/A |

**Implementation approach:**
- Provider abstraction layer built: `scripts/llm_provider.py` (Anthropic/OpenAI/Google/Ollama behind single `call_llm()` interface)
- Model roles defined in `config.py` via `LLM_PROVIDER_CONFIG` with env var overrides
- Cross-provider eval harness built: `scripts/eval_cross_provider.py`
- Cost analysis: `docs/eval/PROVIDER_COST_COMPARISON.md`

**CRITICAL DESIGN DECISION: Full suite, not mix-and-match.** Users choose ONE provider for the entire pipeline. Three supported paths:
1. **Full Anthropic suite** (Haiku/Sonnet/Opus) — default, tested, guaranteed quality
2. **Full Google suite** (Gemini Flash/Pro) — needs validation
3. **Full OpenAI suite** (GPT-4o-mini/4o) — needs validation

No mixing providers across pipeline steps. This simplifies setup (one API key), avoids inconsistency across steps, and makes quality guarantees tractable. Users pick a provider, not individual models.

**Anthropic Batch API (preferred for v1):** Anthropic offers 50% cost reduction for async batch processing. High-volume steps (extraction, classification, tiering) don't need real-time responses. Batch API should be the DEFAULT processing mode — submit batch, come back when ready. Same models, same quality, half price.

**Local processing:** Exploring local model support via Ollama (extraction backend already exists). Architecture is designed so cloud dependencies can be removed as local models improve. Nothing is ensured — local quality is not yet competitive for judgment-heavy steps (tiering, authoring, review). Honest position: cloud processing is required today, local is on the roadmap.

**Testing plan (RELEASE BLOCKER):**
- Run full pipeline through all three provider suites on the same test data
- Blind A/B/C eval on outputs — the user validates quality before any provider is approved
- Use existing EVAL_FRAMEWORK.md methodology
- Cross-provider results make benchmark claims more credible than single-provider
- No provider ships as "supported" without passing blind eval

**V1 approach:** Ship with Anthropic (Batch API) as default. Abstraction layer in place for other providers. Other suites marked "experimental" until blind eval is passed.

**Philosophical note:** The portability promise ("Same Mind, New Model") is about the output — the identity brief works with any AI via MCP. The pipeline using a specific provider to *build* the brief is a practical constraint, not a philosophical one. But cross-provider pipeline support strengthens the positioning and removes a legitimate criticism.

**Status:** Active (RELEASE BLOCKER). Built: abstraction layer, eval harness, cost analysis. Needs: blind eval across three suites, Batch API integration.

**Cross-references:** D-001 (build custom — custom build means we own the provider interface), D-002 (hybrid architecture — cloud processing is provider-agnostic in principle), D-030 (model role separation — established the pattern of different models for different tasks), D-046 (cheap constraint, expensive discrimination — cost tiers may map differently across providers)

---

### D-053: Blind Generation + Layer Versioning (Session 44)

**Context:** During Session 44 layer regeneration, the `regenerate_with_feedback` function fed Sonnet its own previous output with instructions to "preserve strengths." ANCHORS showed 26% verbatim 6-gram overlap between gen1 and the "regenerated" version — Sonnet was anchoring on its own output rather than generating fresh from the facts. This is a critical integrity issue: if regeneration produces near-identical output, the review-and-iterate loop is cosmetic, not substantive. More importantly, if layer changes over time are used to signal identity evolution (which they should be), anchoring corrupts that signal by making layers artificially stable.

**Decision:** Two requirements, both production-critical:

**1. BLIND GENERATION IS MANDATORY.**
The regeneration step must NEVER expose the prior layer version to the generation model. The loop is:
- Step 1: Generate from facts + base prompt (Sonnet)
- Step 2: Review output (Opus — via Claude Code when user is present, via API when unattended)
- Step 3: If below threshold, regenerate from facts + base prompt + review feedback. NO prior output.
- Step 4: Review again. Loop until threshold or max iterations.

The feedback constrains what to fix. The facts constrain what to say. The model must find its own words every time. If two blind generations produce similar text, that similarity is earned (same facts, same meaning). If they produce identical text because the model saw its own output, that similarity is an artifact.

**2. LAYER VERSIONING IS REQUIRED.**
Every generation must be stored as a versioned artifact:
- `data/identity_layers/anchors_v3.md` → deployed version (v3 = Session 46 D-054 agent pipeline)
- `data/identity_layers/history/anchors_v{N}_gen{M}_{timestamp}.md` → every generation attempt
- Layer metadata must include: generation number, input fact count, fact hashes, review score, whether feedback was applied, model used

**Why versioning matters:** Layer diffs over time are a signal for identity evolution. When someone re-runs `baselayer author` after new conversations, differences between the new and old layers represent genuine change (new facts, new patterns, shifted beliefs). This is non-deterministic — same facts won't produce identical text — but the *direction* of change is meaningful. If DELAYED BELIEF REVISION appears in v2 but not v1, that's because new conversations surfaced the pattern.

Anchoring destroys this signal by making v2 artificially similar to v1. Blind generation preserves the integrity of the evolutionary signal.

**Implementation:**
- Fix `regenerate_with_feedback()` in `author_layers.py` — remove `previous_text` parameter, append feedback to base prompt directly
- Create `data/identity_layers/history/` directory
- Store every generation attempt with full metadata
- Add `baselayer author --diff` command to show layer changes between versions
- Future: track fact set changes between generations (which facts were added/removed/changed tier)

**When user is present in Claude Code:** Opus review is done by Claude Code directly, not via API. This is a cost optimization (zero Opus API spend) and produces higher-quality review (richer context, conversational iteration). The `--no-review` flag should be used, with Claude Code performing steps 2-5 manually. When running `baselayer author` unattended (CLI), the automated Sonnet self-review + Opus API Collective review pipeline runs as designed.

**Status:** Active. Code fix required before next layer generation. Versioning implementation needed for v1.

**Cross-references:** D-040 (blind authoring — facts only), D-043 (three-layer architecture), D-046 (cheap constraint, expensive discrimination — blind generation preserves the integrity of the discrimination step)

---

### D-060: Three-Tier Product Model (Session 59)
**Status:** Candidate

**Context:** Base Layer currently ships as a single open-source pipeline. But the full 13-step pipeline is overkill for most users and creates a high onboarding barrier. Simultaneously, Claude launched its own memory import feature (claude.com/import-memory, March 2026) that exports flat facts from ChatGPT/Gemini into Claude's native memory. This creates both competitive pressure and a differentiation opportunity: flat fact import is commoditized; structured behavioral modeling is not.

**Decision (CANDIDATE — not yet decided):** Three-tier product model:

| Tier | Product | Price | What the User Gets |
|---|---|---|---|
| **Tier 1: Preferences** | Structured preferences for paste-in | Free | Minimal pipeline (extract + classify). Exports formatted preferences for Claude/ChatGPT/Gemini native preference UI. |
| **Tier 2: Core + Anchors** | Full identity layers | $3-5 per run | Full pipeline through layer authoring. ANCHORS + CORE + PREDICTIONS as injectable markdown. Delivered via MCP or manual paste. |
| **Tier 3: Full Pipeline** | Open-source self-hosted | Free (BYOS) | Complete pipeline with user provider choice, data control, and local processing options. |

**Cost analysis (per user):**
- Full pipeline: ~$0.52-3.33 depending on corpus size and provider
- Simple preferences: ~$0.17-0.47
- At 100 users: ~$106 (full) or ~$35 (simple preferences)

**Why:**
- Free Tier 1 is the acquisition funnel — zero friction, immediate value, demonstrates what structured extraction does
- Paid Tier 2 is the revenue model — low price point, high perceived value (identity layers feel personal)
- Free Tier 3 is the credibility model — open source, full control, builds trust and community
- Competitive positioning: Claude Memory Import handles flat facts; Base Layer handles behavioral modeling

**Alternatives considered:**
- Single paid tier → rejected (high onboarding friction, no free acquisition funnel)
- Freemium with feature gating → rejected (identity layers are indivisible — gating individual layers fragments the product)
- SaaS-only → rejected (contradicts data sovereignty principle)

**Cross-references:** D-047 (MCP server — delivery mechanism for Tier 2), D-052 (multi-provider — Tier 1-2 run provider-agnostic, Tier 3 user-chosen)

---

### D-061: Provider-Agnostic Pipeline (Session 59)
**Status:** Candidate

**Context:** D-052 architected multi-provider support as a user-facing choice: pick Anthropic, OpenAI, or Google for the entire pipeline. But users don't care about the provider — they care about the output quality. The pipeline should optimize internally, not expose provider selection as a user decision (for Tier 1-2 at least).

**Decision (CANDIDATE — not yet decided):** Internally benchmark Anthropic, OpenAI, and Google at each pipeline step. Select the best cost/quality combination per role. The user does not choose a provider for Tier 1 (Preferences) or Tier 2 (Core + Anchors). Tier 3 (Full Pipeline, open source) retains user provider choice for maximum control.

**Implementation approach:**
- Benchmark each step (extraction, classification, tiering, authoring, review) across all three providers with quality gates from existing checkpoint framework
- Select optimal provider per role based on cost-weighted quality scores
- Store provider selection in pipeline config, updated per benchmark cycle
- User-facing: "Base Layer handles it" — no provider selection UI for Tier 1-2

**Why:**
- Reduces onboarding friction (no API key required for Tier 1-2 if hosted)
- Allows cost optimization (e.g., Gemini Flash for extraction at $0.10/MTok vs Haiku at $1/MTok)
- Quality is provider-agnostic at the output level — the brief works with any downstream model
- Supersedes user-facing provider selection for Tier 1-2 but preserves it for Tier 3

**Relationship to D-052:** D-052 built the multi-provider abstraction layer. D-061 changes who decides which provider to use: the system, not the user (for Tier 1-2). D-052 infrastructure is prerequisite. D-052 RELEASE BLOCKER status for blind eval remains — the benchmark data from D-052 validation feeds D-061's internal optimization.

**Cross-references:** D-052 (multi-provider LLM support), D-060 (three-tier model), D-046 (cheap constraint, expensive discrimination — per-step provider optimization is this principle applied to the pipeline itself)

---

### D-062: Preferences Workflow as Primary Onboarding (Session 59)
**Status:** Candidate

**Context:** Cold start is the biggest acquisition barrier. The current path requires: install Python, pip install baselayer, export conversations, run pipeline, configure MCP. For most AI users, this is too many steps. Meanwhile, every major provider now has a native preferences/memory input: Claude has Project Instructions and custom instructions, ChatGPT has Memory and Custom Instructions, Gemini has Extensions and Gems. These are paste-in text boxes that require zero technical setup.

**Decision (CANDIDATE — not yet decided):** Make the Preferences export (`baselayer export --format preferences --provider claude/chatgpt/gemini`) the primary onboarding path. Users paste exported preferences directly into their provider's native UI. This is the free Tier 1 product and the entry point for the acquisition funnel.

**New CLI commands:**
- `baselayer export --format preferences --provider claude` — export structured preferences formatted for Claude's custom instructions
- `baselayer export --format preferences --provider chatgpt` — export formatted for ChatGPT's Custom Instructions
- `baselayer export --format preferences --provider gemini` — export formatted for Gemini preferences
- `baselayer generate --tier standard` — generate Tier 2 output (full identity layers)

**Why:**
- Meets users where they are — no new tool adoption required
- Demonstrates value immediately — paste in, talk to AI, feel the difference
- Creates upgrade path — "liked the preferences? The full pipeline produces 10x richer behavioral modeling"
- Compatible with Claude Memory Import launch — positions Base Layer as the structured alternative to flat fact import

**Cross-references:** D-060 (three-tier model — Tier 1 definition), D-047 (MCP server — Tier 2 delivery), D-052 (multi-provider — output format varies by provider)

---

## Decision Index

| ID | Decision | Category | Status |
|----|----------|----------|--------|
| D-001 | Build custom, borrow patterns | Foundation | Active |
| D-002 | Hybrid local + cloud | Foundation | Active |
| D-003 | Three-tier memory brief | Architecture | Active |
| D-004 | Surprise-based scoring | Architecture | Active |
| D-005 | AUDN fact lifecycle | Architecture | Active |
| D-006 | Keep existing embeddings | Technology | Active (may revisit) |
| D-007 | Turn-pair embeddings | Improvement | Active |
| D-008 | Skip topic classifier | Improvement | Active |
| D-009 | Two-axis surprise scoring | Improvement | Active (refined by D-015) |
| D-010 | JSON validation guardrails | Improvement | Active |
| D-011 | Session buffer | Improvement | Active |
| D-012 | Semi-automated identity updates | Improvement | Active |
| D-013 | Fact relationship edges | Improvement | Active |
| D-014 | Evaluation framework | Quality | Active |
| D-015 | Recurrence + depth as significance signals | Improvement | Active |
| D-016 | Keep Qwen 2.5 14B for extraction only (model comparison) | Technology | Active (scoped by D-030) |
| D-017 | Increased extraction limits, full re-run | Quality | Active |
| D-018 | Simplified prompt, removed schema enum | Quality | Active |
| D-019 | Identity review v1 — ground-truth calibration | Quality | Active |
| D-020 | Active probing — system-initiated questioning | Architecture | Active |
| D-021 | Correction propagation — user corrections as highest authority | Architecture | Active |
| D-022 | Improvement re-run — 9 extraction fixes applied together | Quality | Active |
| D-023 | Inherent incompleteness as a permanent design principle | Foundation | Active |
| D-024 | The Collective — adversarial multi-perspective review | Process | Active |
| D-025 | The Ghost Layer — invisible priors for context projection | Architecture | Superseded by D-026 |
| D-026 | Identity Cluster Framework — schema-driven identity modeling | Architecture | Active |
| D-027 | Character Overview v2 corrections — 20 factual fixes from line-by-line review | Quality | Active |
| D-028 | Dossier architecture (proposed) — entity profiles for significant people/companies/topics | Architecture | Proposed |
| D-029 | Inference over reporting — system should synthesize patterns, not just list facts | Architecture | Proposed |
| D-030 | Model role separation — Qwen extracts, Claude writes | Architecture | Active |
| D-031 | Dynamic token budgets — relevance-gated, not quota-gated | Architecture | Active |
| D-032 | Phase 6 — fine-tuned lightweight model for behavioral understanding | Architecture | Planned |
| D-033 | Claude Code Session Authoring — identity blocks authored in sessions, not via API | Architecture | Active |
| D-034 | Project Memory Bootstrap — CLAUDE.md as auto-loaded project identity block | Architecture | Active |
| D-035 | Identity Block Budget Increase — 1,000-1,200 tokens; supersedes D-003 allocation | Architecture | Active |
| D-036 | Contradiction classification is not binary — conservative defaults, probe routing | Architecture | Active |
| D-037 | Behavioral data over behavioral prescriptions — identity blocks provide data, not instructions | Architecture | Active |
| D-038 | Opus owns all judgment — local model extracts only, Opus judges all pairs in session | Architecture | Active |
| D-039 | Knowledge tier classification — three-tier fact classification with LLM promotion | Architecture | Active |
| D-040 | Blind authoring / facts-only derivation — identity blocks from raw facts only, no prior blocks | Architecture | Active |
| D-041 | Audience principle — the audience is the understanding the AI needs to take on | Architecture | Active (updated S44) |
| D-042 | Empirical budget — token allocation determined by evaluation, not preset | Architecture | Active |
| D-043 | Three-layer identity architecture — CORE + ANCHORS + PREDICTIONS as separate processes | Architecture | Active |
| D-044 | Scoped memory — facts tagged by interaction mode, cross-scope recurrence validates anchors | Architecture | Active |
| D-045 | Falsification-based axiom validation — negation search, recursive evidence, violation/refutation classification | Architecture | Active |
| D-046 | Cheap constraint, expensive discrimination — cost-layered generation pipeline | Architecture | Active |
| D-047 | MCP server architecture — identity as Resource, retrieval as Tool | Architecture | Active |
| D-048 | Claude Code identity extraction — conversation abstraction + identity-only mode | Architecture | Active |
| D-049 | OpenRouter proxy — custom aiohttp proxy for conversation capture | Architecture | Planned |
| D-050 | CORE layer restructuring — communication guide, not biography | Architecture | Active |
| D-051 | Communication Synthesis pass — cross-layer engagement directives | Architecture | Superseded by D-054 |
| D-054 | Agent architecture for layer authoring — layer agents + Collective (quality + coherence) + Overwatcher | Architecture | Active (implemented Session 46) |
| D-055 | Domain balance + incompleteness signaling — 25% domain cap, thin-data markers in prompts | Quality | Active |
| D-052 | Multi-provider LLM support — full-suite paths (Anthropic/Google/OpenAI), Batch API default, blind eval required | Architecture | Active (RELEASE BLOCKER) |
| D-053 | Blind generation + layer versioning — regeneration never sees prior output, every generation versioned | Architecture | Active |
| D-056 | Fact quality normalization — constrained predicates, quality gates, lexical density scoring | Quality | Active |
| D-057 | Batch API re-extraction — 50% cost via Anthropic Batches API, three-phase CLI | Architecture | Active |
| D-058 | Personalization Trap Preamble — calibration against over-applying identity context | Quality | Active |
| D-059 | Keep trading data in source corpus — domain balance via tiering and authoring, not deletion | Architecture | Active |
| D-060 | Three-tier product model — Preferences (free) / Core+Anchors ($3-5) / Full Pipeline (OSS) | Product | Candidate |
| D-061 | Provider-agnostic pipeline — internal optimization per step, user doesn't choose (Tier 1-2) | Architecture | Candidate |
| D-062 | Preferences workflow as primary onboarding — paste-into-provider as free entry point | Product | Candidate |
| D-063 | Extraction chunking for long texts — auto-chunk on paragraph boundaries, dual-tier caps, 500-char overlap, per-chunk 15-fact cap | Architecture | Active |
| D-064 | Rule-based behavioral classification correction — checkpoint --fix auto-corrects practices/avoids predicates, PREDICTIONS retrieval falls back to positional facts when behavioral < 5 | Quality | Active |
| D-065 | Website data auto-generation — generate_website_data.py parses layers + queries provenance DB + generates TypeScript data files | Tooling | Active |
| D-066 | CORE behavioral specificity restoration — BEHAVIORAL SPECIFICITY test ("could this appear in ANY person's CORE?"), mode detection, conditional AI usage (historical figures excluded), anti-anachronism at prompt level; multi-domain PREDICTIONS false positive warning added; composition prompt gets anti-redundancy + source-type awareness + provenance line stripping | Quality | Active |
| D-067 | Document mode extraction — `--document-mode` flag reframes predicates for document corpus worldview (believes=assumptions, values=optimizes for, practices=methodologies, struggles_with=tensions, avoids=guards against). Automated noise stripping for genome sequences, hex, chemical notation, numeric data. | Architecture | Active |
| D-068 | Anonymization layer — `_detect_subject_name()` + `_anonymize_text()` replaces subject names with "this person" before authoring/composition models see data. Prevents pre-training pattern matching. "DERIVE ONLY FROM INPUT" constraint on all 4 authoring prompts. Composition prompt ANONYMIZATION rule removes names from output. | Quality | Active |
| D-069 | Document tiering subject override — `reclassify_tiers.py --subject "X"` replaces hardcoded `subject='user'` guard. For document corpora, core predicates (believes/values/avoids/practices/struggles_with/prioritizes) promote directly to identity via rule-based promotion. | Architecture | Active |
| D-070 | Faithfulness gate advisory-only — S68 Collective finding: auto-removal caused false positives (deleted [THIN DATA] markers, subject names). Gate now reports but does not auto-remove. Quality gate gap-fill also removed. | Quality | Active |
| D-071 | Patent corpus case study — 30 US patents across 10 tech domains → 670 facts → 572 active → 499 identity → 3 layers (ANCHORS 76.75, CORE 83.25, PREDICTIONS 75) → unified brief 7,463 chars. Opus review: 8/10 impressiveness, 9/10 cross-domain synthesis. Cost: ~$2.78. N=8 proof. | Validation | Active |
| D-072 | BCB-0.1 benchmark suite — 5 metrics (CR, SRS, DRS, CMCS, VRI) with Collective-designed implementation specs. CR (99.98%) and SRS (96.6%) computed from existing eval. DRS/CMCS/VRI specs complete, implementation pending. Pre-release requirement. Total cost ~$12.76/subject. | Evaluation | Active (PRE-RELEASE) |
| D-073 | Provenance-traced evaluation replaces judge-scored dimensions — 4 mechanical layers (Brief Activation, Provenance Coverage, Reasoning Chain Reconstruction, Priority Ordering). $0 cost, human-auditable, no LLM judge dependency. Archived: EVAL_FRAMEWORK.md, EVAL_PROMPT_REDESIGN.md, TRUE_BLIND_EVAL_FRAMEWORK.md, EXTENDED_EVAL_PROTOCOL.md. | Evaluation | Active |
| D-074 | C2 (raw facts) as true evaluation baseline — C1 vs C5c tests "more info vs less info" (obvious). C2 vs C5c tests "given the same information, does compression produce better reasoning?" This is the real experiment. | Evaluation | Active |
| D-075 | Brief structure: WHO + HOW + WHERE IT BREAKS — Current brief describes WHO (behavioral patterns) but lacks HOW (reasoning model with hierarchy/priority) and WHERE IT BREAKS (failure modes, blind spots). Three-layer structure proposed for composition step. | Architecture | Candidate |
| D-076 | Dissenting opinion benchmark — Build brief from judge's prior opinions, predict held-out dissent reasoning, compare to actual text. Natural ground truth, novel situations guaranteed. Tests reasoning prediction (not outcome prediction). Novel contribution — no published work predicts HOW someone argues. | Evaluation | Candidate |
| D-077 | Provenance-informed review + regeneration — Two prongs: (1) Feed citation provenance (claim → source fact mapping) into Collective review prompt so all 4 personas can verify faithfulness at claim level. (2) Feed fact usage statistics (cited vs uncited count) into regeneration prompts — D-053 safe because no prior output text is shown. Closes the gap where provenance was generated but never consumed downstream. | Quality | Active |

---

### D-077: Provenance-Informed Review and Regeneration
**Date:** 2026-03-07 (Session 77+)
**Status:** Active — Implemented
**Category:** Quality

**Decision:** Feed citation provenance into both Collective review AND regeneration, creating a closed feedback loop where provenance data informs downstream quality.

**Two Prongs:**

1. **Review Enrichment:** When citation provenance exists (from Citations API), the Collective review prompt includes a `CITATION PROVENANCE` section showing exactly which facts the model cited for each claim. All four personas (Cognitive Scientist, Narrative Biographer, Epistemologist, Pragmatic Engineer) can now verify faithfulness at the claim level rather than holistically.

2. **Regeneration Enrichment:** When regenerating after review, the model receives fact usage statistics — how many facts were cited vs uncited — without seeing any prior output text (D-053 compliance). This helps the model consider whether important uncited facts should be represented.

**Why:** Citation provenance was being generated by the Citations API but never consumed by any downstream step. The Collective reviewed layers without seeing which facts actually supported which claims. This was a wasted signal — the most valuable output of the Citations API (causal claim→fact links) was captured in metadata but invisible to quality review.

**D-053 Compliance:** Prong 1 enriches REVIEW, not generation — reviewers see provenance, generators don't see prior output. Prong 2 provides aggregate statistics (count of cited/uncited facts) without any prior text — the model still generates blind from facts.

**Alternatives Considered:**
- Feed full provenance into regeneration (rejected — showing claim text would leak prior output, violating D-053)
- Only feed into review, not regeneration (rejected — user insight: "if we have it, we should be injecting it into context to help better authoring")
- Feed specific uncited fact IDs into regeneration (considered but deferred — risks force-inclusion of low-value facts)

**Implementation:** `format_provenance_for_review()` and `format_provenance_for_regen()` in `author_layers.py`. Review function queries fact text from DB for readable display. Regen function provides only aggregate counts.

**Triggered by:** Discovery that Citations API was broken on Windows for ALL subjects (Unicode encoding bug in `check_provenance_coverage()`). Fix revealed that citation provenance existed as a signal but was never wired into the review/regen pipeline.

---

### D-078: Compose Directive Language Must Be Person-Specific
**Date:** 2026-03-10 (Session 84)
**Status:** Active — Fixed S84
**Category:** Quality

**Decision:** V4 compose prompt must generate person-specific directive language, not templated therapeutic responses. Response directives must use language specific to THIS person's domain and vocabulary.

**Bug Found:** Full audit of all 11 V4 briefs revealed systemic template contamination from 37 sources across 3 files. The compose prompt's literal example sentence ("He demands systematic tracking but struggles with Order in practice — when he reports process failures, help diagnose the structural cause...") was copied verbatim into 7/11 briefs. "Unshakeable conviction" opening in 4/11, "operates from" in 7/11, "surfaces a problem, already analyzed internally" in 4/11.

**Fix (S84):** (1) Removed all literal example sentences from compose prompt. (2) Banned formulaic openings. (3) Expanded contamination blocklist from 11→30+ phrases. (4) Added Contamination Gate to compose_unified_brief(). (5) Replaced example names with "[NAME FROM INPUT DATA]" placeholders. (6) Removed detection trigger examples from ANCHORS prompt. (7) Removed axiom interaction boilerplate. Franklin recompose: Gate PASSED, zero template phrases.

**Related:** D-078-PSYCH — Psych profiling eval study designed same session. Professional psychologist reviews pipeline output to assess whether behavioral compression captures clinically meaningful patterns. Separate from the templating bug but discovered in same cross-referencing exercise.

### D-079: Planner-Executor Composition Architecture
**Date:** 2026-03-10 (Session 84)
**Status:** Tested — pending integration
**Category:** Architecture / Provenance

**Problem:** Opus compose step injects pre-training knowledge for famous subjects despite "DERIVE ONLY FROM INPUT" constraint and anonymization. Full contamination scan across 11 subjects found: Franklin 18 ungrounded claims, Buffett 9, Marks 9, Roosevelt 8, Aarik 7 (+ 1 inverted), Bavani 7, Patent 5, Douglass 4, Wollstonecraft 1, Base Layer 0, Paul Graham 0. ~25% contamination rate for famous subjects. One inverted claim (Aarik: brief said opposite of source).

**Root cause:** Opus infers subject identity from contextual signatures (printing + Philadelphia → Franklin) despite anonymization. Once recognized, pre-training biographical knowledge floods the output indistinguishably from input-derived content. Prompt constraints are probabilistic, not reliable — Paul Graham was clean (high overlap between extracted data and pre-training), Franklin was not (large delta).

**Decision:** Split composition into Planner (Opus) and Executor (Sonnet) phases with context isolation:
1. **Planner (Opus):** Reads all 3 source layers. Outputs structured JSON plan — one entry per paragraph with: claim, cited sources [A1, C2, P3], verbatim source text, writing instructions.
2. **Executor (Sonnet):** Receives ONE claim + its specific source text per call. Never sees full layer set. Cannot infer subject identity from isolated fragments.
3. **Assembly (Sonnet):** Stitches paragraphs into coherent narrative. Content locked — can only reorder and add transitions.

**Test result (Franklin):** Opus-only brief: 33 ungrounded claims. P-E brief: **0 ungrounded claims.** Every detail traces to source layers. Cost: $0.33 vs $0.25 (30% increase). Prose quality: slightly more repetitive, mechanical transitions — fixable with better assembly prompt.

**Why not just a tighter gate:** (1) Semantic similarity ≠ derivation — entailment checks can't distinguish "consistent with sources" from "derived from sources." (2) The inverted-claim problem — model cites correct source but reverses the meaning; verification against the cited source passes. (3) The reward signal problem — too strict kills synthesis, too loose allows hallucination. No single threshold works.

**Alternatives considered:**
- Tighter faithfulness gate: Insufficient — can't catch inversions or plausible-but-unsourced behavioral claims
- Local model (Qwen) as executor: Untested — D-030 says Qwen fails at narrative; also still knows Franklin. Testing separately.
- Constrained decoding: Incompatible with API; kills synthesis
- Knowledge delta pre-check: Fragile — models are unreliable introspectors

**Next steps:** Test P-E on 2-3 more subjects (especially private subjects). Improve assembly prompt for prose quality. If validated, integrate into main pipeline as optional `--planner-executor` flag.

**Full diagnostic:** `docs/diagnostics/D079_PROVENANCE_ENFORCEMENT_DIAGNOSTIC.md`
**Test script:** `scripts/experiments/planner_executor_test.py`

---

### D-082: V2 Upgrade Strategy
**Date:** 2026-03-23 (Session 96)
**Status:** Active
**Category:** Pipeline / Data Quality

**Problem:** Wave 1 subjects were built from small initial corpora (often <300 source files). The resulting identity models were thin — low fact counts, sparse predictions, weak anchors. Needed a systematic way to improve existing subjects without rebuilding infrastructure.

**Decision:** Re-scrape + re-extract with larger corpus. Clear existing facts (both SQLite and ChromaDB per S65 rule), re-import expanded corpus, re-run full pipeline. 5 Wave 1 subjects upgraded as proof:
- Kevin Kelly: 76 → 2,824 facts
- David Perell: 201 → 1,867 facts
- Henrik Karlsson: 158 → 739 facts
- Maggie Appleton: 260 → 740 facts
- Casey Newton: 253 → 447 facts

**Why:** Corpus size is the primary driver of fact density and identity model quality. The extraction and authoring pipeline is stable — the bottleneck was input data volume, not pipeline capability. V2 upgrades validate that more data → richer models without diminishing returns at these scales.

**Alternatives considered:**
- Re-tune extraction prompts for higher yield per document: Insufficient — can't extract what isn't in the source
- Supplement with synthetic data: Violates facts-only derivation principle (D-040)
- Accept thin models for low-corpus subjects: Undermines credibility of thinkers pages

**Next steps:** Run V2 pipelines for 10 remaining Wave 1 subjects (scraped, not yet re-extracted).

---

### D-083: Stacking Test Framework
**Date:** 2026-03-23 (Session 96)
**Status:** Complete (scoring pending)
**Category:** Evaluation / Interaction Quality

**Problem:** No empirical measure of whether Base Layer identity models improve AI interaction quality when stacked on top of provider-native memory systems (e.g., GPT's built-in memory).

**Decision:** 100-response test across 5 conditions:
- **C1:** GPT memory only (baseline)
- **C2:** GPT memory + full Base Layer identity model
- **C3:** GPT memory + 25 granular identity files
- **C4:** Fresh GPT (no memory) + full identity model
- **C5:** Fresh GPT, no memory, no identity model (control)

20 questions × 5 conditions. All responses logged for blind scoring.

**Key finding:** C4 project leakage — GPT uses Base Layer project knowledge as "memory" even in fresh context. This means GPT's pre-training includes enough Base Layer-adjacent content to simulate memory it doesn't have. C3 showed strongest early signal for interaction quality improvement.

**Why:** Twin-2K measures identification (can the model pick the right person?), not interaction quality (does the model behave differently with you?). Stacking test fills that gap. The C4 leakage finding is independently significant — it reveals a contamination vector in provider memory evaluation.

**Alternatives considered:**
- Expand Twin-2K to measure interaction: Wrong tool — Twin-2K is forced-choice identification, not open-ended interaction
- A/B test with real users: Premature — need internal signal first
- Self-reported satisfaction survey: Too subjective, no mechanical grounding

**Spec:** `docs/eval/INTERACTION_QUALITY_TEST_SPEC.md`

---

### D-084: Textual TUI Dashboard
**Date:** 2026-03-22 (Session 95)
**Status:** Active
**Category:** Tooling / Developer Experience

**Problem:** Rich-based `dashboard.py` was static, non-scrollable, and couldn't handle 91 subjects. Needed a proper terminal UI with sorting, scrolling, and tier display.

**Decision:** Replace `dashboard.py` with `dashboard_textual.py` using the Textual framework. Features: sortable columns, scrollable table, tier display (T1/T2/T3), auto-refresh, live fact counts and pipeline status.

**Why:** As subject count grew from ~20 to 91, the old Rich table became unusable — couldn't scroll, couldn't sort, couldn't find subjects quickly. Textual provides a proper TUI application with keyboard navigation and reactive updates.

**Alternatives considered:**
- Web-based dashboard: Overkill for internal tooling; adds deployment complexity
- Fix Rich dashboard with pagination: Band-aid — still no sorting or interactive navigation
- Use existing admin page on website: Different purpose (public-facing), wrong data granularity

---

### D-085: Magic Link Authentication
**Date:** 2026-03-23 (Session 96)
**Status:** Deployed
**Category:** Website / Authentication

**Problem:** Password-only authentication for thinkers pages creates friction in outreach. Recipients must find and enter a password from the email — some never do. Needed frictionless first-click access while maintaining security.

**Decision:** Single-use 64-character hex tokens with 7-day expiry, Redis-backed (`magiclink:{token}` key). URL format: `?t={token}`. Auto-auth on first click: sets httpOnly cookie, records login event, redirects to clean URL. Password remains as fallback for repeat visits or expired tokens.

**Implementation:**
- `lib/magic-link.ts` — token generation and validation
- `app/api/magic-link/generate/route.ts` — admin API endpoint
- Generate via `POST /api/magic-link/generate` with `x-admin-secret` header + `{ slugs: [...] }`

**Why:** Reduces authentication friction from "find password in email → copy → paste" to "click link." Single-use prevents token sharing. 7-day expiry limits exposure window. Password fallback ensures no lockout.

**Alternatives considered:**
- Remove passwords entirely: Loses security for public-facing identity models
- OAuth/social login: Overkill for invite-only thinkers pages; adds third-party dependency
- Time-limited passwords: Still requires manual entry; doesn't solve the friction problem

---

### D-086: Percepta Computational Testing
**Date:** 2026-03-24 (Session 97)
**Status:** In Progress
**Category:** Research / Local Models

**Problem:** The Percepta paper ("Can LLMs Be Computers?") claims LLMs can perform deterministic computation reliably. If true, this has implications for provenance verification — local models could handle mechanical verification tasks currently requiring API calls.

**Decision:** Overnight GPU benchmark testing Percepta paper claims across 10 local models, 20 tasks. Tests whether local models can handle deterministic computation for provenance-related operations (hash verification, string matching, logical entailment checking).

**Why:** If local models can reliably perform deterministic computation, the provenance verification pipeline (`verify_provenance.py`) could run entirely locally at zero API cost. This would make the open-source release of the verification tools more accessible — users wouldn't need API keys for basic provenance checks.

**Alternatives considered:**
- Trust the paper's claims without replication: Violates empirical validation principle
- Test only on provenance-specific tasks: Too narrow — need to understand general computational reliability first
- Skip and keep API-based verification: Misses cost reduction opportunity for open-source users

---

### D-087: Compose Fact Scaling (S98)

**Status:** Active
**Category:** Architecture
**Session:** 98

**Decision:** Compose step dynamically scales fact sampling with corpus size instead of hardcoded LIMIT 100.

- Small corpora (<500 identity-tier facts): sample top 100 by recurrence count
- Large corpora (500+): sample top 300
- Config constants: COMPOSE_FACT_LIMIT_SMALL, COMPOSE_FACT_LIMIT_LARGE, COMPOSE_FACT_THRESHOLD

**Evidence:** Kevin Kelly V2 had 1,235 identity-tier facts but compose only saw top 100 (same as V1 with 76 facts). Brief was byte-for-byte identical. After fix, sampling 300 facts produced a genuinely different brief.

**Alternatives considered:**
- Sample all facts: Too expensive for Opus at 2,000+ facts
- Delta-from-V1 approach: Complex, deferred — simple scaling sufficient for now

---

### D-088: Pipeline Refactor — Unified Command + Safety Gates (S98)

**Status:** Active
**Category:** Architecture
**Session:** 98

**Decision:** `baselayer pipeline <subject> [--v2]` replaces manual multi-step execution. All safety gates enforced between steps: extraction completeness, fact floor (identity-tier >= 50, predicates >= 15, sources >= 5), coverage discard (>20% blocks), concurrency limit (max 2), V2 snapshot-before-clear.

**Evidence:** S98 agents ran author/compose on 10% extracted data, producing garbage briefs. S96 ran "V2" on identical source data, wasting API cost. No gates existed to prevent either failure.

**Alternatives considered:**
- State machine in database: Over-engineered. Sequential with file-based state inference is simpler.
- Batch extract as default: Deferred — async polling doesn't fit synchronous pipeline flow yet.
