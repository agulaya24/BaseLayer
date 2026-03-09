# Temporal Processing — Redesigned Approach

**Version 4 — 2026-02-13 (Session 23)**
**Previous version:** Version 3 (Session 21)
**Supersedes:** Version 1 (Session 19), which proposed time-based decay with staleness sweeps and blanket score penalties. That approach was fundamentally rejected in Session 20. Version 2 (earlier Session 21) was refined based on Collective review and user feedback on contradiction complexity, model selection, and probe delivery. Version 3 (Session 21) added frequency delta, conservative contradiction default, cascade effects, model role pipeline, probe delivery spec, empirical similarity threshold, cost model. Version 4 (Session 23) adds Layer 2 test results, blind validation, judgment principles, and updates execution model to Claude Code sessions.

**Governing principles:** Confidence Over Deletion (Principle #6), Silence Is Not Evidence of Irrelevance (Principle #7), Inherent Incompleteness — Temporal Incompleteness subsection.

---

## Why the Original Approach Was Wrong

The Session 19 proposal treated temporal processing as a time-math problem: measure how old a fact is, apply category-dependent thresholds (180/365/730 days), penalize stale facts by 30%, sweep periodically. This failed on multiple grounds:

1. **Time is not the primary axis.** A fact about your cat being sick doesn't become less important because 90 days passed. The importance of a fact is determined by its magnitude — what it represents in a person's life — not when it was last mentioned.

2. **Silence ≠ irrelevance.** Conversation frequency reflects AI usage patterns, not personal importance. the user's pet, spouse, parents — these may never appear in a technical conversation. Deprioritizing them because they haven't been mentioned recently is the exact opposite of understanding someone.

3. **Blanket penalties are epistemic overreach.** A 30% score reduction asserts certainty about relevance that the system does not have. The system cannot know what is or isn't relevant to a future conversation.

4. **Arbitrary thresholds have no basis.** Who decides 180 days for habits, 365 for values, 730 for biography? On what basis? In a probabilistic environment, imposing hard cutoffs is pretending to have precision that doesn't exist.

5. **Four strata were over-engineered.** State/Pattern/Phase/Trait attempted to classify temporal behavior along a gradient. The actual distinction is simpler: things that happened (events) vs. things that are currently true (states).

---

## The Redesigned Model

### Core Insight

Temporal processing is a **classification problem**, not a time-math problem. The question is not "how old is this fact?" but "what kind of fact is this, and does time affect its relevance?"

### Two Fact Classes

| Class | Definition | Temporal behavior | Examples |
|---|---|---|---|
| **Event** | Something that happened. Immutable biographical anchor. | Never decays. Accrues meaning over time. | Founded a company, got married, lost a parent, shipped a product, achieved a milestone |
| **State** | Something currently true. Mutable condition. | Can become outdated — detected by **contradiction**, not by time elapsed. | Current wake time, active project, trading strategy, living situation, current habits |

**The 5:30am bug, correctly diagnosed:** A state ("wakes at 5:30am") was stored with no mechanism to detect when it stopped being true. The fix is not to decay it after N days. The fix is to detect when a contradicting fact appears ("now wakes at 7am") and adjust confidence accordingly.

**Events accrue, not decay.** The day a previous startup ended means more now than it did when it happened, because of what came after. Events organize memory around them — they are anchors, not entries on a deprecation schedule.

### Fact Evolution: States That Become Events

A state ("is building a memory system") will eventually become an event ("built a memory system"). The state doesn't transform — it gets **superseded by a fact that happens to be an event.** When the project ships, a new fact is extracted ("shipped the memory system") that contradicts the active state. The state transitions to past; the new fact is classified as an event. The biographical anchor emerges from the state's completion.

The fact system stores the chain: state → superseded → event. The identity block (authored in Claude Code sessions, D-033) is where narrative synthesis happens — where "built" becomes part of a trajectory, not just a database entry.

### States That Fade Without Contradiction

Some states fade without a clear completion event. "Learning Python" → just... stops being mentioned. No contradicting fact is extracted because no contradicting fact exists. This is a genuine edge case.

**Frequency delta as signal:** The system can detect changes in engagement pattern relative to the person's own baseline for a topic. If someone mentioned Python 15 times in 4 weeks (high mention velocity) and then zero times for 12 weeks, the *velocity drop* is informative. This is:

- Not a blanket time penalty (Principle #7 preserved — the signal is relative to the person, not a calendar threshold)
- Not an arbitrary cutoff (it's measured against the person's own behavior with that specific topic)
- Pattern recognition, not time-math
- Metadata for the reasoning model, not a score reduction

**How it works:**
- `recurrence_count` and `recurrence_span_days` already exist in the schema
- Compute **mention velocity** — mentions per time period for state-facts
- Compare current velocity to the fact's historical velocity
- A significant velocity drop → flag as "engagement pattern changed"
- This becomes probe material: "You were working on Python pretty actively — is that still going?"
- It does NOT become automatic confidence reduction

**Key distinction:** Someone who mentioned Python once and never again — that's not a velocity drop, that's a single data point with no baseline. Someone who mentioned it 15 times in 4 weeks then zero for 12 weeks — that's a measurable pattern change. The signal requires a baseline to compare against.

**When frequency delta does NOT apply:**
- Relationships, values, biographical facts — these have no expected mention frequency. Not mentioning your spouse for 3 months is not a velocity drop. There was never a "spouse mention rate" to compare against.
- One-time mentions — no baseline exists.
- Topics that naturally appear in bursts (a project, a crisis) — the burst ending is normal, not a signal.

---

### Contradiction Detection (Not Decay)

Staleness is not a function of time. It is a function of **contradiction** — a newer fact that conflicts with an older state-type fact.

**Conservative default: both facts can be true.** The system assumes coexistence unless there is clear mutual exclusivity. Contradiction is declared only when two facts cannot logically coexist for the same person at the same time.

**What IS a contradiction (mutually exclusive):**
- "Lives in Houston" + "Moved to Austin" → same attribute (location), different value, mutually exclusive
- "Wakes at 5:30am" + "Wakes at 7am" → same attribute (wake time), different value
- "Works at Google" + "Left Google, now freelancing" → explicit negation of prior state

**What is NOT a contradiction (can coexist):**
- "Trades SPY options" + "Shifted to futures trading" → both can be true simultaneously. A shift doesn't mean abandonment. These are additive, not exclusive.
- "Learning Python" + "Learning Rust" → people learn multiple things
- "Working on memory system" + "Working on fellowship application" → multiple projects coexist
- "Trades SPY options" + "Shifted to swing trading" → these *might* conflict, but the system can't know without more context. Default: both may be true. Flag for probe.

**Cascade effects:** A major event in one cluster can affect state-facts in other clusters without any direct contradiction being stated.
- "Got a full-time job" (event, what_youve_built) → affects "day trades SPY options" (state, how_you_operate). No direct contradiction — the trading fact was never negated. But the context changed.
- When a major event is extracted, the system should flag related state-facts in other clusters as **potentially affected** and queue them for probing — not auto-resolve them.
- The system cannot infer mutual exclusivity from cascade events. Only the user can confirm whether they stopped day trading after getting a job.

**When in doubt: probe, don't resolve.** The working assumption is that the user will correct any inaccuracy when it surfaces in a future conversation. Ambiguous cases always go to the probe queue.

---

### The Contradiction Pipeline

**Model roles — who does what (D-030, D-038 compliance):**

| Step | Component | What it does |
|---|---|---|
| 1. Extract | **Local model** (currently Qwen 2.5 14B) | Extracts facts from conversation, classifies each as event/state. Bounded, structured task. |
| 2. Filter | **Embedding model** (currently MiniLM, local) | For new state-facts: query ChromaDB for similar existing state-facts in same cluster. Pure vector math. Threshold: 0.50. |
| 3. Judge | **Reasoning model** (currently Opus 4.6 via Claude Code session) | For ALL candidate pairs above similarity threshold: judge whether contradiction, enrichment, coexistent, or ambiguous. D-038: reasoning model owns all judgment — no local model judgment layer. |
| 4. Execute | **Pure code** | If contradiction confirmed: adjust confidence, link `superseded_by`, transition `temporal_state`. Database operations. |
| 5. Queue | **Pure code** | If ambiguous or cascade: add to probe queue in SQLite. |

**Note on model flexibility:** Each step references a role (local model, embedding model, reasoning model), not a specific model. Models are interchangeable — config.py specifies which model fills each role. Future model swaps (e.g., Qwen3 14B for extraction, a different embedding model, or a different reasoning model) require only config changes, not pipeline changes.

**Full pipeline:**
1. Local model extracts fact from conversation (existing pipeline)
2. Local model classifies fact as event or state (new: added to extraction prompt)
3. If event → store, done. Events don't need contradiction checking.
4. If state → embed the new fact (embedding model, existing pipeline)
5. Query ChromaDB for similar existing state-facts in same cluster
6. If similarity below 0.50 → no candidate contradictions. Done.
7. If similarity >= 0.50 → candidate pair exists. Send to Claude Code session for judgment.
8. Reasoning model returns: **contradiction** / **enrichment** / **coexistent** / **ambiguous**
9. If contradiction → code auto-resolves (confidence reduction, superseded_by link, temporal_state → past)
10. If enrichment → code may merge or link facts
11. If coexistent → no action, both facts remain active
12. If ambiguous → probe queue

**Clean separation of concerns:** Local model handles extraction and classification (bounded, structured). Reasoning model handles ALL judgment (D-038). The handoff is: local model extracts → embeddings filter → reasoning model judges (in session) → code executes. No local model is involved in judgment decisions.

**Execution model for judgment — Claude Code sessions (D-033, D-038, BYOS):**
- ALL contradiction judgment is executed in Claude Code sessions, not via API calls
- This aligns with D-033 (Claude Code session execution) and D-038 (Opus owns all judgment)
- The user's existing Claude subscription covers the reasoning cost — no separate API billing
- Candidate pairs are presented to the session with judgment principles (see below) and the model returns a classification
- This is a session-level task, not a pipeline-automated API call

**Model selection test results (Session 23 + Session 26 clean blind):**

| Model | Overall Accuracy | Contradiction | Enrichment | Coexistent | Unrelated |
|---|---|---|---|---|---|
| **Qwen 2.5 14B** single-pass (S23+S26) | **90% (45/50)** | 84% (21/25) | 100% (10/10) | 100% (10/10) | 80% (4/5) |
| **Qwen 2.5 14B** iterative refinement (S26) | **70% (35/50)** | 92% (23/25) | 100% (10/10) | 20% (2/10) | 0% (0/5) |
| **Opus 4.6** contaminated (S23) | **100% (50/50)** | 100% | 100% | 100% | 100% |
| **Opus 4.6** blind session (S26) | **94% (47/50)** | 88% (22/25) | 100% (10/10) | 100% (10/10) | 100% (5/5) |

**Qwen failure mode (confirmed Session 26):** Identical to Session 23. Struggles with value-replacement contradictions where the newer fact supersedes (not reverses) the old one. Same 4 contradiction misses: quantitative state change ($50K→$120K), market view reversal (bearish→bullish), sleep habit change (6hr→prioritizes 8hr), goal shift (startup fundraising→solo project). The model sees "update" where it should see "replacement."

**Opus 4.6 blind results (Session 26 — contamination fixed):** 94% on truly blind pairs (expected labels stripped from prompt). Three disagreements: Pair 11 (book progression — called enrichment, test set says contradiction; defensible per D-036 Principle 6), Pair 7 (goal shift — called contradiction, matches test set), Pair 16 (sleep — called contradiction, but D-036 owner labeled coexistent). Against owner-validated labels: ~96%+.

**Iterative refinement experiment (Session 26 — killed):** Inspired by looped LLM research (Ouro/LoopLM, arXiv 2510.25741). Two-pass Qwen: judge, then feed own judgment back with nudge toward "does B replace A?" Result: fixed 2 contradiction misses (market view, sleep habit) but regressed on 12 other pairs. Coexistent accuracy dropped 100%→20%, unrelated 80%→0%. The refinement prompt induced false positives. Not viable.

**Blind validation results (Session 23):**
- The project owner independently labeled 14 fact-pairs without seeing model outputs or expected labels
- Owner disagreed with 5 of the 25 pairs originally labeled as "contradiction" in the test set
- All 5 disagreements were pairs labeled "contradiction" that the owner judged as ambiguous, coexistent, or enrichment
- Qwen's "misses" on pairs B, C, and D were arguably correct per owner validation — Qwen called them non-contradictions, and the owner agreed
- **Adjusted Qwen accuracy against owner-validated labels: ~95%+**
- This validates D-036: the test set's binary contradiction labels were themselves flawed. The model was being penalized for getting closer to the truth.

**Architecture decision (D-038, Session 26):** Opus owns ALL judgment. Qwen is restricted to extraction and classification. The two-layer model (Qwen filters, Opus judges hard cases) was rejected because: (1) no reliable escalation signal exists at runtime — Qwen doesn't output confidence scores, (2) 60-70% of pairs would escalate anyway, (3) BYOS model eliminates the cost argument. Pipeline: MiniLM filters (threshold 0.50) → Opus judges all candidates in Claude Code session → code executes.

**Similarity threshold — empirically determined:**
- Pull 50 known pairs from existing facts (25 that should be contradictions, 25 that should not)
- Compute embedding similarity for all pairs
- Find the separation point in the distribution
- Set initial threshold based on empirical data
- Track false positive/negative rates, adjust over time
- No arbitrary threshold. The data decides.

---

### Contradiction Judgment Principles (D-036, Session 23)

**Six principles abstracted from blind validation. These constrain the LLM judgment layer to avoid false positives.**

1. **Claim Type Asymmetry.** Facts on different epistemic planes (descriptive vs. aspirational) coexist by default. "Sleeps 6 hours" (reality) and "prioritizes 8 hours" (intent) are not contradictions.

2. **Temporal Order Dependence.** Ordering is required input to judgment, not optional metadata. Without knowing which fact is older, the system cannot determine which is current.

3. **Scope Resolution.** Confirm same entity/scope before comparing content. "Spouse has eczema" and "User has dry skin" describe different people — not a contradiction.

4. **Context-Bound Truth.** Some fact pairs are indeterminate in isolation. "Lives in Dubai" and "Lives in Toronto" could be contradiction or coexistence (dual residence). When context is insufficient, output "indeterminate."

5. **Stated vs. Enacted Gap.** The system stores claims, not verified behaviors. Two self-reports that appear contradictory may both be accurate descriptions of different domains.

6. **Binary Collapse Resistance.** Default to conservative/ambiguous. Contradiction is reserved for unambiguous reversals. False negatives are recoverable; false positives destroy valid knowledge.

**Operational implication:** The judge's default disposition is conservative — coexistence unless contradiction is unambiguous. Ambiguous cases route to the probe queue for user resolution.

---

### Temporal Confidence Qualifier

**Time is a point of reference, not a verdict.** Time elapsed on a state-fact is metadata that informs confidence in current accuracy. It does not reduce retrieval priority, score, or importance.

How it manifests in the brief:
- State-fact extracted recently, no contradictions: no qualifier needed
- State-fact with significant velocity drop: `(engagement pattern changed — may be outdated)`
- State-fact extracted 8+ months ago, no corroboration, high-volatility cluster: `(as of [date])`
- State-fact extracted 2+ years ago, no corroboration: `(as of [date], unconfirmed)`
- Event-fact: no qualifier regardless of age — events are permanent

The system never acts on time alone. It annotates with time so the reasoning model has full information. **Time informs. Time does not decide.**

---

### Confidence Adjustment Model

The system models a **confidence landscape**, not a truth table.

| Fact state | Confidence in current accuracy | Behavior |
|---|---|---|
| **Active, no contradiction** | Original confidence maintained | Fully available for retrieval |
| **Active, time elapsed** | Original confidence maintained — time alone does not reduce confidence | Fully available for retrieval, temporal qualifier as metadata |
| **Active, velocity drop** | Original confidence maintained — velocity drop is metadata, not a penalty | Available with engagement-change annotation; probe candidate |
| **Contradicted by newer fact** | Reduced; transition to historical | Available with `[past]` marker; linked to successor via `superseded_by` |
| **Cascade-affected** | Original confidence maintained — cascade is a flag, not a verdict | Available; flagged for probing when topic arises |
| **User-corrected** | Highest confidence signal | Correction survives resets (D-021) |
| **Event-class** | Permanent — events are immutable | Always available; may accrue context over time |

**No fact is ever deleted from the database.** Archival, confidence reduction, and historical reclassification are valid operations. Deletion is not. (Principle #6, measurable constraint.)

---

### Division of Labor

The memory system and the reasoning model have different jobs:

| Component | Responsibility | What it does NOT do |
|---|---|---|
| **Memory system** | Classify facts, detect contradictions, adjust confidence, compute velocity, manage probe queue, provide context with metadata | Decide what's relevant to this specific conversation |
| **Reasoning model** (Claude) | Receive brief with confidence metadata and probe directives, decide relevance in the moment, phrase probes naturally | Memory operations, fact classification, confidence adjustment, probe delivery decisions |

The memory system provides honest context with confidence signals. The reasoning model decides what matters right now. This means the system should err toward **complete representation with uncertainty signals** rather than pre-filtering. If a fact might be outdated but hasn't been contradicted, include it with appropriate metadata — let the model decide.

---

### Probe Delivery (Option C: Brief Injection with Directive)

**Architecture:** Probe queue stored in SQLite. Probes are injected into the brief as directives when conversationally relevant. The system decides THAT a probe must be delivered and WHEN it's relevant. The reasoning model decides only HOW to phrase it.

**Pipeline:**
1. Contradiction/cascade/velocity-drop detected → probe created, stored in probe queue (SQLite) with topic embedding
2. At brief assembly time, system checks: is any queued probe topic semantically related to the current conversation? (embedding similarity between probe topic and user's message)
3. If yes → probe injected into the brief as a **directive**:

```
[PROBE — DELIVER THIS CONVERSATION]
Previously recorded: "trades SPY options" (state, 2025-08-14)
Recently extracted: "shifted to swing trading" (state, 2026-02-10)
Status: Ambiguous — may coexist, may conflict.
Action: Confirm current trading approach.
Delivery rules:
  - Weave into conversation flow, not as a standalone question.
  - Frame as curiosity or confirmation. Do not say "my records
    show" or "I want to verify." Do not break conversational
    immersion.
  - Use the current conversation topic as context.
  - Example: "Are you still primarily doing SPY options, or has
    the approach shifted?"
```

4. The reasoning model phrases the probe naturally within the conversation. It does NOT get to decide whether to deliver it. The system already made that decision based on conversational relevance.
5. If the probe topic is NOT related to the current conversation → probe stays in queue. It waits for a relevant conversation.
6. Probes are resolved when: user responds (answer stored as high-authority correction), a future extraction resolves the ambiguity, or the user explicitly dismisses.

**Constraints:**
- Maximum one probe per conversation
- Low-volatility contradictions get priority over high-volatility ones (something significant changed in a stable cluster)
- Probes use hypothesis-confirming format
- Cascade-triggered probes are lower priority than direct contradictions
- Undelivered probes persist in queue indefinitely — no time-based expiry

**Probe trigger table:**

| Trigger | Priority | Queue behavior |
|---|---|---|
| High-confidence contradiction in low-volatility cluster | High | Deliver at next relevant conversation |
| Direct contradiction in any cluster | Medium-High | Deliver when topic arises |
| Cascade effect (event affects states in other clusters) | Medium | Deliver when related topic arises |
| Significant velocity drop on state-fact | Medium-Low | Deliver when topic arises |
| Multiple ambiguous pairs in same cluster | Low | Deliver when cluster topic arises |

---

## What Already Exists in Code

### Used

| Asset | Location | Current usage | Redesign role |
|---|---|---|---|
| `temporal_state` (current/past/unknown) | memory_facts table, extract_facts.py | Set at extraction, cosmetic `[past]` prefix in theme block | **Expand:** Core classification signal. Transitions to `past` on contradiction. |
| `superseded_by` | memory_facts table | Binary links exist | **Activate:** Core of contradiction chain. Populate when contradiction confirmed. |
| `recurrence_count` | memory_facts table | Used for significance scoring | **Extend:** Input to mention velocity computation. |
| `recurrence_span_days` | score_facts.py | Used for significance floors only | **Extend:** Input to mention velocity computation. |
| Episode recency scoring (30%) | assemble_brief.py | Only temporal logic actually working | **Keep as-is.** Episodes are inherently recent — this is correct behavior. |

### Defined But Never Wired

| Asset | Location | Current status | Redesign role |
|---|---|---|---|
| `temporal_bias` per cluster | assemble_brief.py cluster configs | Defined in all 10 clusters, never read by retrieval | **Repurpose** as metadata annotation for reasoning model. |
| `volatility` per cluster | assemble_brief.py cluster configs | Defined in all 10 clusters, completely unused | **Repurpose** as contradiction sensitivity calibration. |

### Does Not Exist (Needs Building)

| Asset | Purpose |
|---|---|
| `fact_class` column (event/state/unclassified) | Binary classification of every fact |
| Contradiction detection pipeline | Embeddings filter → Claude Code session judgment → code execution |
| Confidence adjustment operations | Reduce confidence on contradicted facts, transition temporal_state |
| Probe queue table | SQLite table storing pending probes with topic embeddings |
| Mention velocity computation | Track per-fact engagement pattern for frequency delta detection |
| Cascade detection | Flag state-facts in related clusters when major event extracted |

---

## Repurposing Existing Cluster Config Fields

### temporal_bias → Retrieval Guidance

The existing `temporal_bias` values per cluster are conceptually sound — they describe which temporal orientation a cluster's facts should lean toward. Under the redesigned model, they guide **metadata annotations passed to the reasoning model**, not retrieval filtering.

| Cluster | temporal_bias | Redesign interpretation |
|---|---|---|
| who_you_are | foundational, active | Mostly events and stable traits. States included but less common. |
| who_you_love | foundational, formative, active | Relationships are events (meeting, marriage) + ongoing states. All temporal orientations valid. |
| what_youve_built | formative, active | Mix of events (founded, shipped) and states (currently building). |
| what_youve_lost | foundational, formative, active | Primarily events. Losses are immutable anchors. |
| what_drives_you | formative, foundational | Mostly stable. Changes here are significant and should trigger probes. |
| what_you_believe | formative, active | Values evolve slowly. Contradictions here are high-signal. |
| what_you_struggle_with | active, formative | Mix of ongoing states and historical patterns. |
| how_you_operate | formative, active | Behavioral patterns — relatively stable but can evolve. |
| where_youre_headed | active | Primarily states. Most likely cluster to have outdated facts. |
| whats_unresolved | active | Primarily states. Active questions that may be resolved. |

**Implementation:** When assembling the theme block, `temporal_bias` informs the metadata passed to the reasoning model. Clusters biased toward "active" include a note that state-facts should be treated with appropriate uncertainty. Clusters biased toward "foundational" signal that facts here are likely permanent.

### volatility → Contradiction Sensitivity

Repurpose `volatility` to indicate how likely facts in a cluster are to be contradicted over time. This does **not** trigger automatic degradation — it calibrates how the system prioritizes contradiction checking and probe delivery.

| Volatility | Meaning | Clusters |
|---|---|---|
| low | Facts rarely change. Contradictions here are high-signal — something significant happened. | who_you_are, who_you_love, what_youve_lost |
| medium | Facts evolve over time. Contradictions are normal but worth tracking. | what_drives_you, what_you_believe, how_you_operate |
| high | Facts change regularly. Contradictions expected — track but don't over-alert. | what_you_struggle_with, where_youre_headed, whats_unresolved |

**Note on low-volatility contradictions:** When a contradiction is detected in a low-volatility cluster (who_you_love, what_youve_lost), this is a stronger signal that something important changed. These are prioritized for probe delivery.

---

## Implementation Plan

### Phase 1: Fact Classification (Schema + Extraction)

**Add `fact_class` column to memory_facts:**
- Values: `event`, `state`, `unclassified`
- Default: `unclassified` (for existing 4,704 facts)
- New extractions: classify during extraction via Qwen

**Modify extraction prompt:**
- Add fact_class to extraction output: "Is this something that happened (event) or something currently true (state)?"
- This is a bounded classification task — well within Qwen's capabilities (D-030)

**Backfill existing facts:**
- Run classification pass over existing 4,704 facts via Opus 4.6 (one-time operation, accuracy on the foundation matters)
- Events: marriage, founding, loss, achievement, milestone → `event`
- States: habits, current projects, preferences, routines → `state`
- Some facts are genuinely ambiguous — classify as `state` by default (more conservative: states can be contradicted, events cannot)
- Estimated cost: ~$7 one-time (4,704 facts batched, ~235 API calls)

### Phase 2: Contradiction Detection

**Model selection test (completed Session 23):**
- 50 hand-labeled fact-pairs (25 contradictions, 10 enrichments, 10 coexistent, 5 unrelated)
- Qwen 2.5 14B: 90% accuracy (84% on contradictions, 100% enrichment/coexistent, 80% unrelated)
- Opus 4.6 via Claude Code: 100% accuracy but methodologically contaminated (labels visible)
- Blind validation (D-036): 5/25 contradiction labels disputed by owner — model was arguably correct
- **Recommended architecture:** Qwen first-pass for clear cases, Claude Code session judgment for ambiguous cases

**Build contradiction pipeline:**
1. New state-fact extracted → embed via MiniLM (existing pipeline)
2. Query ChromaDB for similar existing state-facts in same cluster
3. If similarity below empirically-determined threshold → done, no candidate
4. If similarity at or above threshold → send pair to selected model for judgment
5. Model returns: contradiction / enrichment / coexistent / ambiguous
6. Code executes the appropriate action (confidence adjust, link, queue probe)

**Cascade detection:**
- When a new event-fact is extracted, identify state-facts in related clusters that may be affected
- Flag these as cascade-affected → probe queue
- Do not auto-resolve cascade effects — only the user can confirm

### Phase 3: Wire Into Brief Assembly

**Temporal confidence qualifiers:**
- State-facts include `(as of [date])` annotation when: high-volatility cluster + no recent corroboration, or significant velocity drop detected
- Event-facts: no temporal qualifier regardless of age
- Metadata passed alongside facts: `fact_class`, `temporal_state`, velocity data if available

**Cluster-level annotations:**
- `temporal_bias` metadata informs the reasoning model which clusters are foundational vs. active
- `volatility` metadata signals which clusters' state-facts should be treated with appropriate uncertainty

**Do NOT:**
- Pre-filter facts based on age
- Apply score penalties based on time
- Remove facts from retrieval based on staleness
- Override the reasoning model's judgment about relevance

### Phase 4: Probe Queue + Delivery

**Create probe queue table in SQLite:**
- Fields: probe_id, source_fact_id, conflicting_fact_id, probe_type (contradiction/cascade/velocity_drop), cluster, topic_embedding, priority, status (pending/delivered/resolved), created_at
- Probes persist until resolved — no time-based expiry

**Brief assembly integration:**
- At assembly time, compute similarity between user's message embedding and queued probe topic embeddings
- If match found → inject probe directive into brief with delivery rules
- Maximum one probe per brief assembly

**Probe directive template:**
```
[PROBE — DELIVER THIS CONVERSATION]
Context: [description of the contradiction/cascade/velocity change]
Action: [what to confirm]
Delivery rules:
  - Weave into conversation flow, not as a standalone question.
  - Frame as curiosity or confirmation. Do not say "my records
    show" or "I want to verify." Do not break immersion.
  - Use the current conversation topic as entry point.
  - Example phrasing: [specific example relevant to the probe]
```

### Phase 5: Mention Velocity (Frequency Delta)

**Compute mention velocity for state-facts:**
- Using existing `recurrence_count` and `recurrence_span_days`
- Track mentions per time period (weekly/monthly granularity)
- Compare recent velocity to historical velocity for the same fact
- Significant drop → flag fact as "engagement pattern changed"
- This is metadata and probe material, not confidence reduction

**When frequency delta applies:** Only for state-facts with an established baseline (multiple mentions over a meaningful time span). Single-mention facts and relationship/value facts are excluded.

---

## Cost Model

**Ongoing costs (contradiction detection — BYOS model, D-033):**
- Layer 1 (MiniLM similarity filter): zero cost, runs locally
- Layer 2 (Claude Code session judgment): covered by existing Claude Code subscription — zero incremental cost
- Triggers only when: new state-fact + high similarity to existing state-fact in same cluster
- Per extraction batch: ~2-5 judgment calls (narrow trigger)

**One-time costs (backfill classification):**
- 4,704 facts via Opus 4.6: ~$7 (if using API; free if done in Claude Code sessions)

**Privacy:**
- Layer 1: entirely local (MiniLM embeddings)
- Layer 2: only fact-pairs (~100 tokens per pair) sent to Claude Code session for judgment — no raw conversations
- No raw conversations, no full database, no embeddings
- Consistent with existing privacy model (brief sends ~1,500-2,600 tokens)

---

## What This Approach Does NOT Do

1. **No time-based decay.** Facts do not lose score or confidence based on age alone.
2. **No staleness sweep.** There is no periodic job that degrades facts by time elapsed.
3. **No blanket penalties.** No percentage-based score reduction applied uniformly.
4. **No arbitrary thresholds.** No 180/365/730 day cutoffs. Similarity threshold is empirically determined from data.
5. **No silent deprioritization.** If the system is uncertain, it flags uncertainty — it does not quietly reduce a fact's weight.
6. **No deletion.** Facts are never removed from the database.
7. **No hierarchy of cluster significance.** All 10 clusters represent fundamental human dimensions.
8. **No auto-resolution of ambiguous cases.** When in doubt, the system probes — it does not assume.
9. **No cascade auto-resolution.** Events in one cluster cannot automatically change facts in another cluster. Only the user can confirm cascade effects.

---

## Relationship to Existing Infrastructure

| Session 19 proposal | Session 21 replacement |
|---|---|
| `last_corroborated_at` column | **Not needed.** Corroboration is a weak signal. Contradiction + frequency delta are the signals. |
| `temporal_status` enum (fresh/aging/stale_candidate/archived) | **Replaced by:** `fact_class` (event/state) + confidence adjustment on contradiction + velocity metadata. No aging states. |
| Category-dependent thresholds (180/365/730 days) | **Removed.** No time-based thresholds. Similarity threshold empirically determined. |
| 30% score penalty for stale facts | **Removed.** No blanket penalties. |
| Staleness sweep (temporal_audit.py) | **Replaced by:** Contradiction detection during extraction + frequency delta monitoring. Real-time, not batch. |
| Step-function decay | **Removed entirely.** No decay function of any kind. |
| Wire `temporal_bias` into retrieval (prefer recent/old) | **Repurposed:** `temporal_bias` as metadata annotation for reasoning model, not retrieval filter. |

---

## Measuring Success

**The system has correct temporal behavior when:**

1. Events never lose retrieval priority regardless of age
2. State-facts maintain full confidence until contradicted
3. Contradictions are detected during extraction, not on a timer
4. Contradicted facts transition to historical with provenance preserved
5. The reasoning model receives confidence metadata and makes its own relevance judgments
6. User probes are triggered by contradictions, velocity drops, and cascade effects — not by time elapsed
7. No fact is ever permanently removed from the database
8. Ambiguous cases go to probe queue, not auto-resolution
9. Cascade effects are flagged for user confirmation, not silently resolved

**The system has failed if:**

1. A pet's importance is reduced because it hasn't been mentioned in 90 days
2. A habit fact is silently deprioritized without a contradicting fact
3. The system applies a score penalty based on any time measurement
4. An event (marriage, founding, loss) is treated as potentially outdated
5. The system resolves a contradiction without logging it or preserving the superseded fact
6. Two facts that can coexist are declared contradictions (e.g., "trades options" + "also trades futures")
7. A cascade event auto-resolves state-facts in other clusters without user confirmation

---

## Decision Log

This document supersedes the Session 19 temporal processing review. The redesign is governed by:

- **D-021:** Correction propagation — corrections are highest-authority signal
- **D-023:** Inherent incompleteness — the system will never fully know the person
- **D-026:** Identity cluster framework — 10 universal dimensions, no hierarchy
- **D-030:** Model role separation — Qwen extracts/classifies, Claude judges (in Code sessions), code executes (updated Session 23)
- **D-033:** Claude Code session authoring — Layer 2 judgment via sessions, not API (BYOS model)
- **D-036:** Contradiction classification is not binary — conservative defaults, 6 judgment principles (Session 23)
- **Principle #6:** Confidence Over Deletion
- **Principle #7:** Silence Is Not Evidence of Irrelevance
- **Anti-pattern #7:** No uniform temporal behavior assumption
- **Session 20 raw notes:** `docs/core/SESSION_20_NOTES.md`

---

*Collective review + user feedback incorporated: Session 21, 2026-02-13*
*Key additions v3: frequency delta for fading states, conservative contradiction default, cascade effects, model role pipeline, probe delivery spec (Option C), empirical similarity threshold, cost model*
*Key additions v4 (Session 23): Layer 2 test results (Qwen 90%, Opus 100% contaminated), blind validation (D-036), 6 judgment principles, execution model updated to Claude Code sessions (D-033/BYOS)*
