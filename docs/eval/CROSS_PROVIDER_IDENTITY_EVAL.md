# Cross-Provider Identity Evaluation Framework
**Created:** Session 49, 2026-02-26
**Purpose:** Test how well each major AI provider's native memory handles identity understanding and temporal reasoning
**Status:** Framework design — not yet executed

---

## What This Evaluates

The existing eval framework (`EVAL_FRAMEWORK.md`) tests whether **Base Layer's brief improves AI responses** by comparing with-brief vs. without-brief vs. native-memory conditions.

This framework tests a different question: **How well does each provider's own memory system understand identity?** Independent of Base Layer. What does each get right? What does each miss? Where does temporal reasoning break?

This produces:
1. A baseline understanding of what "memory" currently means across providers
2. Evidence for where Base Layer adds value over native memory
3. A temporality benchmark that tests the hardest dimension of identity understanding

---

## Providers Under Test

| ID | Provider | Memory System | Access |
|---|---|---|---|
| **GPT** | ChatGPT (Plus/Pro) | 4-layer memory + chat history reference | Web interface |
| **CLD** | Claude (Pro) | Memory summary + chat search + auto-memory | Web interface |
| **GEM** | Gemini (Advanced/AI Pro) | `user_context` + Personal Intelligence (if available) | Web interface |
| **PPX** | Perplexity (Pro) | Cross-model memory layer | Web interface |
| **BL** | Base Layer | Identity brief via MCP or paste | Injected into any model |

Meta AI and Apple Intelligence excluded: Meta's ad-targeting memory has different incentives; Apple's personalized Siri not shipped.

---

## Evaluation Design

### Phase 1: Memory Building (Weeks 1-3)

Use each provider as a primary conversation partner across the same topics. Natural usage — do not force facts. The same person (User A) uses all providers for real tasks so each builds its own memory from genuine interaction.

**Minimum interaction:** 50 substantive conversations per provider across 3 weeks.

**Topic diversity requirement:**
- Trading decisions and post-session reviews (at least 10 conversations)
- Base Layer architecture discussions (at least 10 conversations)
- Personal decisions, relationships, health (at least 10 conversations)
- Career and professional identity (at least 5 conversations)
- General knowledge / research (at least 5 conversations)
- Philosophical / reflective (at least 5 conversations)

**Why 3 weeks:** Temporal evaluation requires time separation between early and later conversations. Facts stated in week 1 may change or evolve by week 3. This is the test.

### Phase 2: Identity Probing (Week 4)

After 3 weeks of natural usage, probe each provider with the **same 10 identity evaluation prompts** from `data/eval/identity_eval_prompts.md`. These test recognition, calibration, depth, authenticity, and actionability.

Additionally, probe with **5 new temporality-specific prompts** (see Section 4 below).

**Protocol:**
1. Same prompt to each provider, in a new conversation
2. Each provider uses only its native memory (no brief injection, no conversation reference)
3. For BL condition: inject Base Layer brief into a cold Claude session via MCP
4. Record all responses verbatim

### Phase 3: Blind Evaluation (Week 5)

**Identity evaluation (10 prompts x 5 providers):**
- Randomize and label responses (A through E)
- Rate blind on 5 dimensions (1-5 scale): Recognition, Calibration, Depth, Authenticity, Actionability
- Rate one dimension at a time across all responses for a given prompt
- Wait 24+ hours before rating
- Rate fast — gut reaction

**Temporality evaluation (5 prompts x 5 providers):**
- Rate on 4 temporality dimensions (see Section 4)

### Phase 4: Analysis

- Per-provider average scores across all dimensions
- Per-dimension analysis (which provider wins on recognition? depth? temporality?)
- Qualitative analysis: what kinds of identity understanding does each provider exhibit or miss?
- Failure mode taxonomy: how does each provider fail? (profiling vs. generic vs. outdated vs. overgeneralized)

---

## Scoring Dimensions

### Standard Identity Dimensions (from existing eval)

| Dimension | What It Measures | Scale |
|---|---|---|
| **Recognition** | Does this feel like being known or profiled or generic? | 1-5 |
| **Calibration** | Is the response calibrated to how you actually think and communicate? | 1-5 |
| **Depth** | Does the response engage at the right level? | 1-5 |
| **Authenticity** | Does the response feel genuine or performative? | 1-5 |
| **Actionability** | If advice, is it actually useful given who you are? | 1-5 |

### Temporality Dimensions (new)

| Dimension | What It Measures | Scale |
|---|---|---|
| **Temporal Accuracy** | Does the provider know what is *currently* true vs. what *was* true? | 1-5 |
| **Contradiction Handling** | When beliefs have evolved, does it use the current belief or the old one? | 1-5 |
| **Evolution Recognition** | Does it recognize that views have changed and acknowledge the trajectory? | 1-5 |
| **Temporal Inference** | Does it distinguish stable traits from transient states? | 1-5 |

**Temporal Accuracy Scale:**
- 1: Uses outdated information as if current. "You live in X" when you moved 2 weeks ago.
- 2: Mixes current and outdated information. Some facts current, some stale.
- 3: Mostly current. Gets the big things right but misses recent updates.
- 4: Accurately tracks current state. When wrong, it is on minor details.
- 5: Knows what is current AND acknowledges what changed. "Since you moved to Y..."

**Contradiction Handling Scale:**
- 1: Confidently asserts the old contradicted fact.
- 2: Asserts old fact but hedges. "I believe you said..."
- 3: Notices the contradiction but does not resolve it. Presents both.
- 4: Uses the newer/current fact. May not acknowledge the change explicitly.
- 5: Uses the current fact and recognizes the evolution. "You used to think X but now you..."

**Evolution Recognition Scale:**
- 1: No awareness that the person has changed. Treats all past statements as equally current.
- 2: Vague awareness of change. "Your thinking may have evolved."
- 3: Recognizes specific changes. "You mentioned X before, but more recently..."
- 4: Recognizes patterns of change. Connects multiple belief evolutions.
- 5: Understands the trajectory. Can articulate how and why views shifted.

**Temporal Inference Scale:**
- 1: Treats every stated fact as permanent. "You hate mornings" from one comment.
- 2: Some distinction but inconsistent. May treat a mood as a personality trait.
- 3: Generally distinguishes traits from states. Recognizes that frustration is temporary.
- 4: Good trait/state separation. Rarely over-generalizes transient states.
- 5: Nuanced temporal inference. Distinguishes core values from current moods from evolving beliefs from contextual preferences.

---

## Temporality Test Prompts

These 5 prompts are specifically designed to test temporal reasoning. They should be used AFTER 3 weeks of natural usage where at least some beliefs/facts have naturally changed.

### T1: Belief Evolution
> Remember when I was skeptical about [topic you changed your mind on]? Where do I stand on that now?

**Tests:** Does the provider track belief evolution? Does it know the current position vs. the former position? Can it articulate the trajectory?

**Ideal response:** Accurately states the former position, the current position, and what changed.
**Failure mode (temporal):** Asserts the former position as current. Or has no awareness of the change.

### T2: Contradicting a Stored Fact
> [State something that directly contradicts a fact you told the provider in week 1, naturally in conversation during week 3. Then in the probe session:] What do you know about my [the contradicted topic]?

**Tests:** When a fact has been updated, does the provider use the old fact or the new one? Does it notice the contradiction?

**Ideal response:** Uses the updated fact. May note: "You mentioned X before but more recently said Y."
**Failure mode (temporal):** Confidently asserts the old fact. Or merges both into a confused answer.

### T3: Stable Trait vs. Transient State
> I mentioned being frustrated with [topic] a few times. Is that a deep thing for me or was I just having a bad week?

**Tests:** Can the provider distinguish a stable pattern from a transient state? Does it have enough temporal context to judge?

**Ideal response:** Assesses based on frequency, duration, and connection to other patterns. Does not over-generalize.
**Failure mode (temporal):** "You definitely feel strongly about this" from 2 mentions. Or "hard to say" when there's actually enough data.

### T4: Temporal Ordering
> What have been the main things on my mind this month, in roughly the order they came up?

**Tests:** Does the provider have temporal ordering of topics? Can it reconstruct a timeline?

**Ideal response:** Correctly sequences major topics with approximate timing. Shows awareness of which concerns came first and which emerged later.
**Failure mode (temporal):** Lists topics with no temporal ordering. Or cannot distinguish early-month concerns from late-month concerns.

### T5: Prediction from Temporal Pattern
> Based on how my thinking has been evolving on [topic with clear trajectory], what do you think I will conclude?

**Tests:** Can the provider extrapolate from a temporal pattern? This is the hardest test — it requires not just remembering but reasoning over the trajectory of belief change.

**Ideal response:** Makes a specific, justified prediction based on the direction of change. Acknowledges uncertainty.
**Failure mode (temporal):** Cannot make a prediction. Or makes a prediction based on the most recent statement only, not the trajectory.

---

## Expected Results (Hypotheses)

| Dimension | GPT | Claude | Gemini | Perplexity | Base Layer |
|---|---|---|---|---|---|
| Recognition | 3-4 | 2-3 | 2-3 | 2-3 | 4-5 |
| Calibration | 3 | 2-3 | 2 | 2 | 4 |
| Depth | 3 | 3 | 2-3 | 2-3 | 4 |
| Authenticity | 3 | 3-4 | 2-3 | 3 | 4 |
| Actionability | 3 | 2-3 | 2-3 | 2-3 | 4 |
| **Temporal Accuracy** | **2-3** | **2** | **3** | **2** | **3-4** |
| **Contradiction Handling** | **2** | **1-2** | **2-3** | **1-2** | **3-4** |
| **Evolution Recognition** | **2** | **1** | **2** | **1** | **3** |
| **Temporal Inference** | **2** | **1-2** | **2** | **1-2** | **3** |

**Rationale:**
- **GPT expected to lead on recognition/calibration** — most developed native memory (4-layer system, inferred preferences). Weak on temporality (no contradiction detection).
- **Gemini expected to lead on temporal accuracy** — time-aware `user_context` with timestamps. Personal Intelligence adds data richness but not temporal modeling.
- **Claude expected to score lower on memory-dependent dimensions** — auto-memory is newer and sparser. Should score well on depth and authenticity (model quality).
- **Perplexity expected mid-range** — cross-model memory is flat preferences. Strong transparency (citation-based attribution).
- **Base Layer expected to lead on temporality** — only system with explicit temporal_state, contradiction detection, knowledge tiering. Should lead on recognition/depth from 3-layer identity.

---

## Fairness Constraints

### Memory Advantage Normalization
Each provider builds memory from different volumes and types of interaction. To ensure fairness:
- Same person, same time period, same topic mix
- Minimum 50 conversations per provider
- No artificial "memory loading" (e.g., listing 20 facts to remember)
- Natural usage only — whatever each system remembers from organic conversation

### Model Quality vs. Memory Quality
A provider may score well on "Depth" or "Authenticity" because of model quality, not memory quality. To isolate memory contribution:
- Compare each provider's **memory condition** against its own **cold condition** (same model, no memory)
- The delta tells you what memory added
- This is separate from the absolute score comparison

### Base Layer Double-Test
Base Layer should be tested in two conditions:
1. **BL-Claude:** Brief injected into Claude via MCP (tests brief quality + Claude model)
2. **BL-GPT:** Brief pasted into ChatGPT (tests brief quality + GPT model, isolating from native memory)

This lets us measure: does the brief improve GPT beyond GPT's own native memory?

---

## Temporality as Independent Benchmark

The temporality evaluation has value beyond the cross-provider comparison. It can become a standalone benchmark:

**Temporal Identity Reasoning Benchmark (TIRB)**

A standardized test of whether AI memory systems can:
1. Track what is currently true vs. what was true (temporal accuracy)
2. Detect and resolve contradictions (contradiction handling)
3. Recognize belief evolution over time (evolution recognition)
4. Distinguish stable traits from transient states (temporal inference)
5. Predict future beliefs from temporal trajectories (temporal prediction)

No such benchmark exists. KnowMe-Bench (Jan 2026) tests temporal reasoning over autobiographical narratives but does not test live memory systems. LongMemEval tests temporal reasoning but only for factual recall, not identity understanding.

Building this benchmark would:
- Establish Base Layer as a research contributor, not just a product
- Create a credibility signal for GitHub (README case study)
- Produce publishable results if well-designed
- Give the Collective a structured framework for evaluating each pipeline run

**Design considerations:**
- Needs to be reproducible (fixed scenarios, not dependent on one person's life)
- Could use synthetic personas with documented belief evolution timelines
- Each test case: persona description + conversation history with temporal changes + probe questions with known-correct temporal answers
- Automated scoring via LLM-as-judge with human validation on a subset

---

## Implementation Plan

### Phase 0: Preparation (1 day)
- Set up accounts/subscriptions for all 5 providers
- Document starting state of each provider's memory (screenshot/export)
- Prepare conversation topic plan ensuring coverage

### Phase 1: Memory Building (3 weeks)
- Natural daily usage across all providers
- Log which topics discussed with which provider (for coverage tracking)
- Introduce at least 3 natural belief changes during the period
- Mark dates of key fact changes for temporal evaluation

### Phase 2: Probing (2 days)
- Run all 15 prompts (10 identity + 5 temporal) across all providers
- Run cold conditions for each provider (new account or temp chat)
- Run Base Layer conditions (BL-Claude, BL-GPT)
- Record all responses verbatim in structured format

### Phase 3: Blind Rating (2-3 days)
- Randomize and blind all responses
- Rate using scoring rubric
- Wait 24h minimum before starting
- Rate one dimension at a time

### Phase 4: Analysis (1-2 days)
- Score compilation and statistical analysis
- Per-provider strengths/weaknesses
- Temporality analysis
- Qualitative failure mode taxonomy
- Write-up for README and evaluation study section

### Total Timeline: ~4-5 weeks

---

## Relationship to Existing Eval

| Framework | Question | Conditions | Focus |
|---|---|---|---|
| **A/B/C Eval** (Session 32) | Does the brief help vs. raw history vs. cold start? | Same model, 3 context conditions | Brief utilization |
| **Identity Eval** (`identity_eval_prompts.md`) | Does the brief improve recognition across providers? | Claude cold/brief, GPT native/augmented | Brief improvement |
| **This Framework** | How well does each provider natively understand identity? | 5 providers, native memory only + Base Layer | Provider comparison + temporality |
| **TIRB (future)** | Can AI memory systems reason about identity over time? | Standardized benchmark, any system | Temporal reasoning |

Each framework builds on the previous. The cross-provider eval is the broadest, testing every major competitor on their own terms. TIRB would be the benchmark contribution.

---

## Output Artifacts

1. **Scored comparison table** — per-provider, per-dimension scores (shareable for README)
2. **Temporality deep-dive** — how each system handles time (publishable if well-designed)
3. **Failure mode taxonomy** — how each provider fails at identity (GTM material)
4. **Provider-specific recommendations** — what each provider should build (thought leadership)
5. **Base Layer evidence** — measurable improvement over native memory (credibility signal)
