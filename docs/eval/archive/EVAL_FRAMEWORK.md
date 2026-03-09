# Evaluation & Provenance Framework
## Measuring Whether the Brief Actually Works

---

## Overview

Base Layer injects a ~5,000 token brief into every AI conversation. That brief contains three identity layers (ANCHORS, CORE, PREDICTIONS), retrieved theme facts, and episodic memories. The question this framework answers: **does that injection actually change AI behavior in ways that match who the person is?**

This is not a standard NLP benchmark. No public dataset exists for "does this AI know this specific human." We are building the evaluation methodology from scratch, which means the framework must cover five distinct measurement problems:

1. **Brief Utilization** — What percentage of the injected brief actually influences responses?
2. **Provenance Tracking** — Which specific layers and facts drove a given response?
3. **Identity Accuracy** — Does the AI's behavior match the real person?
4. **Regression Testing** — When layers are regenerated, does quality hold or degrade?
5. **Benchmark Design** — A fixed, reusable query set that tests identity understanding at scale.

Each of these is a separate evaluation dimension with its own methodology, scoring, and implementation path. They build on each other — you cannot do provenance without utilization, and you cannot do regression without benchmarks.

---

## 1. Blind A/B/C Eval (Existing — Session 32)

The foundational eval. Already built and run once. Kept here as the canonical reference.

### Test Conditions

| Condition | Context Provided | What It Simulates |
|---|---|---|
| **A: Baseline** | None | Cold-start LLM, no knowledge of user |
| **B: Raw History** | Semantically retrieved conversation excerpts (~2,600 tokens) | Platform memory (GPT, Claude) — unstructured fact accumulation |
| **C: Brief** | Assembled brief with identity block + theme clusters + episodes | Memory system output |

Same prompt/question across all three conditions. Same model. Same temperature.

### Evaluation Dimensions

| Dimension | What It Measures | Scale |
|---|---|---|
| **Personalization accuracy** | Did the response reflect real traits, preferences, patterns? | 1-5 |
| **Behavioral prediction** | Did the model anticipate how the subject would react/decide? | 1-5 |
| **Advice fit** | If advice was given, would the subject actually follow it? | 1-5 |
| **Tone match** | Did the response feel like talking to someone who knows them? | 1-5 |
| **Novel composition** | Did the model combine context to produce insights not explicitly stated? | 1-5 |
| **"Seen" factor** | Overall: did this feel like being known? | 1-5 |

Subject rates blind (doesn't know which condition produced which response).

### Rating Scale Calibration

| Score | Meaning | Gut Check |
|---|---|---|
| **1** | Generic. Could be written for anyone. | "This is a stranger." |
| **2** | Vaguely relevant. Gets the domain right but not me. | "They read my LinkedIn." |
| **3** | Some real knowledge present. A few things land. | "They've met me once." |
| **4** | Clearly knows me. Specific, accurate, mostly right. | "They've worked with me." |
| **5** | Feels like someone who actually knows me. Specific details, right tone, anticipates my reaction. | "This person gets me." |

### Per-Dimension Guidance

- **Personalization accuracy** — Are the facts right? Don't reward correct vibes — reward correct specifics. A response that says "as someone who trades options" when you do is accurate. One that says "as someone who values work-life balance" when you don't is a miss.
- **Behavioral prediction** — Did it anticipate how you'd react or what you'd actually do? "You'd probably overthink this for a week" is a prediction. "Take some time to reflect" is generic advice. Score predictions, not platitudes.
- **Advice fit** — Would you actually follow this advice? Not "is it good advice" — is it good advice *for you*? The response that accounts for what you'd actually do scores higher.
- **Tone match** — Does it feel like talking to someone who knows you, or a customer service bot? Directness level, formality, whether it challenges you or coddles you.
- **Novel composition** — Did the response combine things to produce an insight you hadn't been explicitly told? Restating known facts isn't composition.
- **"Seen" factor** — The holistic question. Don't analyze it. Just feel it.

### Test Prompts (10)

Revised via Collective review (Session 32). Spans all 5 framework categories. Each prompt activates multiple identity clusters with clear differentiation potential between conditions.

| # | Prompt | Category | Key Clusters |
|---|--------|----------|-------------|
| 1 | "I just had my worst trading day in months. Broke my rules, revenge traded, and lost $400." | Emotional | struggle, operate |
| 2 | "I got an offer for a VP of Operations role at a Series B company, but it means pausing Base Layer development. How should I think about this?" | Career/life | built, lost, drives, headed |
| 3 | "My partner and I are planning our anniversary dinner. What kind of place should we look for?" | Preference | love, operate |
| 4 | "How should I pitch Base Layer to someone who's never heard of it?" | Practical | built, believe, headed |
| 5 | "I'm considering getting another cat. Good idea?" | Preference/life | love, who_you_are |
| 6 | "Sometimes I wonder if I'm just building another thing that won't make it, like my previous startup. How do I know this is different?" | Emotional/reflection | lost, drives, headed |
| 7 | "I need to make a decision about whether to build the multi-user auth system myself or use a third-party service like Auth0. Walk me through how to think about this." | Practical | operate, believe |
| 8 | "My back has been killing me lately and I've been skipping the gym. How do I get back on track?" | Lifestyle/advice | struggle, operate |
| 9 | "A VC just told me that fine-tuning is the future of AI personalization and memory systems like mine are a dead end. How do I respond?" | Career/debate | believe, built, headed |
| 10 | "Help me write the opening paragraph of a blog post about why AI should remember you." | Creative collaboration | believe, operate (tone) |

### Coverage Validation

| Framework Category | Prompts | Count |
|---|---|---|
| Practical decisions | #4 (pitch), #5 (cat), #7 (build vs buy) | 3 |
| Emotional situations | #1 (trading loss), #6 (startup doubt), #8 (health) | 3 |
| Career/life advice | #2 (VP offer), #9 (VC challenge) | 2 |
| Preference questions | #3 (dinner), #5 (cat) | 2 |
| Creative collaboration | #10 (blog post) | 1 |

### Test Protocol

1. Run each prompt through conditions A, B, C using `run_eval.py --generate`
2. Randomize and label responses (X, Y, Z) — subject doesn't know which is which
3. Wait at least 24 hours before rating (temporal distance)
4. Rate one dimension at a time across all responses (not all dimensions per response)
5. Rate fast — first instinct over deliberation
6. Jot a one-sentence justification for any score of 4 or 5
7. Flag any factually incorrect statements in responses
8. Before unblinding: write down which response you think is C, with confidence level
9. Reveal conditions and discuss surprises

### Subject-Rater Protocol

The eval subject is also the rater. This creates bias risk — the subject designed the system and knows what the brief contains.

**Mitigations:**
- Rate one dimension at a time across all 3 responses (breaks halo effect)
- Rate fast — gut feeling over analysis (prevents reverse-engineering conditions)
- Don't try to guess conditions during rating
- Don't compare across prompts — rate all of prompt 1 before moving to prompt 2
- Record condition-C detection attempt before unblinding (measures blinding quality)

**Watch for:**
- Penalizing vagueness too harshly (baseline will be vague — that's expected, a 1-2 is fair)
- Rewarding name-drops over comprehension (mentioning a spouse's name isn't automatically better)
- The "too much" penalty (over-sharing knowledge awkwardly is a tone miss, not a personalization win)

### What Success Looks Like

- **C > B on "Seen" factor by >= 1.0 points average** — the brief measurably outperforms raw history
- **C > A on all dimensions** — the brief adds value over baseline (table stakes)
- **B > A on personalization** — raw history provides some signal (validates that the comparison is fair)
- **Novel composition scores higher in C than B** — predictions compose better than raw facts
- **Condition C correctly identified on fewer than 7/10 prompts** — blinding worked

### First Eval Results (Session 32, User A)

**Conditions:** A=Baseline (no context), B=Raw History (~2,600 tokens), C=Brief (identity+theme+episodes)
**Model:** claude-sonnet-4-5-20250929, temperature=0
**Rated:** 3 of 6 dimensions (personalization accuracy, behavioral prediction, advice fit). Subject fatigued after 78/180 ratings — protocol too long.

#### Scores by Dimension

| Dimension | A (Baseline) | B (Raw) | C (Brief) | C-B Gap |
|-----------|-------------|---------|-----------|---------|
| Personalization Accuracy | 1.5 | 2.8 | 3.5 | +0.7 |
| Behavioral Prediction | 1.1 | 2.7 | 3.9 | +1.2 |
| Advice Fit | 2.7 | 2.8 | 4.2 | +1.4 |
| **Overall** | **1.7** | **2.8** | **3.8** | **+1.0** |

#### Key Findings

1. **C > B > A across all dimensions.** The brief measurably outperforms raw history.
2. **Behavioral prediction shows the largest gap (C-B=+1.2).** The brief enables inference, not just recall. Synthesis > accumulation.
3. **Prompt 9 (VC debate about fine-tuning vs memory systems) was a total failure** — all three conditions scored 1 on personalization. The system didn't surface Base Layer knowledge in a debate framing. Fixed post-eval by adding conviction knowledge to identity block.
4. **B occasionally beat C** (prompts 2, 9, 10 on some dimensions). Raw history sometimes has the right verbatim excerpt that the brief's scoring deprioritized.
5. **Subject notes reveal voice > facts.** Highest scores went to responses that were direct, opinionated, and framework-oriented. Penalties for wordiness, coddling, "doing too much."
6. **Baseline advice fit surprised** — scored 5 on prompt 2 (career crossroads). Generic advice is sometimes good advice.

#### Post-Eval Fixes Applied

- **Voice calibration:** BRIEF_INSTRUCTION updated with communication preferences (direct, opinionated, concise)
- **Conviction knowledge:** Identity block #14 added CONVICTIONS section (Base Layer thesis)
- **Prompt 9 retest:** Dramatic improvement — now references Base Layer architecture directly

#### Protocol Lessons

- 6 dimensions x 3 responses x 10 prompts = 180 ratings is too many. Subject fatigued at 78.
- Next run: 3 dimensions max (personalization, behavioral prediction, seen factor)
- Rating one dimension at a time works well for preventing halo effect
- Notes/justifications were more valuable than the numerical scores

---

## 2. Brief Utilization Scoring

### The Problem

The brief is ~5,000 tokens. Not all of it matters for every query. If a user asks about dinner plans, the ANCHORS layer (epistemic axioms about coherence and ownership) should contribute nothing. If 80% of the brief goes unused in a typical interaction, the system is over-stuffed and the token budget could be smaller — or the retrieval is selecting poorly.

Utilization scoring answers: **what fraction of the injected brief actually influenced the AI's response?**

### Methodology

#### Step 1: Segment the Brief

The brief has clearly delimited components that can be scored independently:

| Segment | XML Tag / Marker | Typical Tokens |
|---|---|---|
| BRIEF_INSTRUCTION | (preamble text before XML) | ~90 |
| ANCHORS layer | Within `<user_identity>`, first block | ~700 |
| CORE layer | Within `<user_identity>`, second block | ~500 |
| PREDICTIONS layer | Within `<user_identity>`, third block | ~500 |
| Theme facts | `<relevant_context>` | ~800 |
| Episodic memories | `<episodic_memories>` | ~600 |

Within each layer, further segmentation is possible:
- ANCHORS: each axiom (COHERENCE, INTEGRITY, OWNERSHIP, etc.) is a segment
- CORE: each paragraph is a segment
- PREDICTIONS: each behavioral pattern (DELAYED BELIEF REVISION, FRUSTRATION COMPOUNDING, etc.) is a segment
- Themes: each fact is a segment
- Episodes: each retrieved memory is a segment

#### Step 2: LLM-as-Judge Attribution

For each query-response pair, ask a judge model (Sonnet or Opus) to identify which brief segments informed the response.

**Judge prompt:**

```
You are evaluating whether an AI response was influenced by specific context that was injected into its system prompt.

Below is the full brief that was injected, divided into labeled segments. Below that is the user's message and the AI's response.

For each segment, classify its influence on the response:

- ACTIVE: The response clearly draws on information or framing from this segment. Specific content, tone, or reasoning traces back to it.
- LATENT: The segment didn't produce visible content in the response, but it plausibly shaped the framing, tone, or what was NOT said. (Example: an axiom about ownership didn't produce text about ownership, but the response avoided blame-shifting language.)
- UNUSED: No detectable influence on the response.

Be conservative. ACTIVE requires clear evidence. LATENT requires a plausible causal story. When in doubt, mark UNUSED.

<brief_segments>
[Numbered segments with labels]
</brief_segments>

<user_message>
[The query]
</user_message>

<ai_response>
[The response]
</ai_response>

For each segment, respond in JSON:
{
  "segment_id": <number>,
  "segment_label": "<label>",
  "influence": "ACTIVE" | "LATENT" | "UNUSED",
  "evidence": "<1-sentence explanation>"
}
```

#### Step 3: Compute Utilization Scores

From the judge's attributions, compute:

| Metric | Formula | What It Measures |
|---|---|---|
| **Active Utilization Rate** | ACTIVE segments / total segments | What fraction of the brief visibly drove the response |
| **Effective Utilization Rate** | (ACTIVE + LATENT) / total segments | What fraction of the brief plausibly mattered |
| **Layer Utilization** | ACTIVE segments per layer / segments in layer | Which layers pull their weight |
| **Token Efficiency** | Response quality score / total brief tokens | Quality per token spent |
| **Dead Weight** | UNUSED segments x their token count | Tokens injected but never used |

#### Step 4: Utilization Thresholds

| Metric | Healthy | Warning | Problem |
|---|---|---|---|
| Active Utilization (per query) | > 25% | 15-25% | < 15% |
| Effective Utilization (per query) | > 40% | 25-40% | < 25% |
| Layer Utilization (ANCHORS, avg across queries) | > 30% | 15-30% | < 15% |
| Layer Utilization (CORE, avg) | > 50% | 30-50% | < 30% |
| Layer Utilization (PREDICTIONS, avg) | > 30% | 15-30% | < 15% |
| Layer Utilization (Themes, avg) | > 40% | 20-40% | < 20% |
| Dead Weight (avg tokens per query) | < 1,500 | 1,500-2,500 | > 2,500 |

**Why different thresholds per layer?** ANCHORS are epistemic constraints — they should be invisibly active (latent) more often than visibly active. CORE is biographical — if the AI is personalizing, CORE should be the most-used layer. PREDICTIONS are situational — they activate only when the right behavioral pattern is triggered, so lower active rates are expected. Themes are query-specific retrieval — if retrieval is working, they should be relevant.

#### Step 5: Differential Utilization (Brief vs. No-Brief)

To distinguish "the brief caused this" from "the model would have said that anyway," run the same query with and without the brief, then compare responses.

**Methodology:**
1. Generate response WITH brief (condition C)
2. Generate response WITHOUT brief (condition A)
3. Ask judge: "For each segment marked ACTIVE in step 2, would the response have contained this information/framing even without the brief?"
4. Segments that appear in both responses are **coincidental** — the model knew it anyway
5. Segments that only appear in condition C are **brief-dependent** — the brief caused this

**Brief-Dependent Utilization** = brief-dependent segments / total segments. This is the real measure of what the brief adds.

### Expected Output

Per-query utilization report:

```
Query: "I just had my worst trading day in months..."
Active Utilization: 31% (8/26 segments)
Effective Utilization: 46% (12/26 segments)

Layer Breakdown:
  ANCHORS:     2/9 ACTIVE, 3/9 LATENT  (OWNERSHIP, SYSTEMATIZE active)
  CORE:        3/5 ACTIVE, 0/5 LATENT  (trading para, spouse para, tension para)
  PREDICTIONS: 2/8 ACTIVE, 1/8 LATENT  (FRUSTRATION COMPOUNDING, ACCOUNTABILITY AMPLIFICATION)
  Themes:      1/3 ACTIVE              (trading discipline fact)
  Episodes:    0/1 ACTIVE              (unused)

Dead Weight: 1,247 tokens (episodes + unused anchors)
Brief-Dependent: 6/8 active segments would NOT have appeared without brief
```

---

## 3. Provenance Tracking

### The Problem

Utilization tells you WHAT got used. Provenance tells you HOW it got used — tracing the causal chain from specific facts in the database, through the authored layers, into the assembled brief, and finally into the AI's response.

This matters because:
- If a response is wrong, provenance tells you which fact or layer to fix
- If a response is great, provenance tells you which parts of the pipeline produced the value
- Layer regeneration (especially after D-050 CORE rewrite) needs before/after provenance comparison

### Provenance Chain

Every AI response has a provenance chain with four links:

```
FACTS (SQLite)
  --> authored into LAYERS (anchors_v4.md, core_v4.md, predictions_v4.md)
    --> assembled into BRIEF (assemble_brief.py output)
      --> consumed by LLM --> RESPONSE
```

Each link can be traced:

| Link | Traceable How |
|---|---|
| Facts --> Layers | author_layers.py logs which fact IDs were retrieved per layer. Layer headers record input count. |
| Layers --> Brief | assemble_brief.py reads layer files and wraps in XML. Deterministic — the entire layer is included. |
| Brief --> Response | LLM-as-judge attribution (Section 2 above). |

The gap is **Facts --> Response**: given a response, which specific facts in the database contributed? This requires chaining through the layers.

### Provenance Query Protocol

Given an AI response the user found particularly good or bad, run a provenance query:

**Step 1: Identify active brief segments** (from utilization scoring)

**Step 2: Map segments back to source facts**

For identity layer segments, the mapping is indirect — the layer was authored from facts, but the authoring process synthesized and compressed them. The provenance here is "which facts informed this paragraph/axiom," not "this paragraph contains fact #1234."

Two approaches:
- **Embedding similarity:** Embed the active segment, query the fact database, find the top-N most similar facts. These are the likely provenance sources.
- **Authoring log:** If author_layers.py logged which facts were retrieved for each layer, check those logs.

For theme/episode segments, the mapping is direct — assemble_brief.py retrieves specific fact IDs and conversation IDs. These are stored in the `brief_assembly_log` table and returned in the metadata dict.

**Step 3: Build the provenance record**

```json
{
  "query": "I just had my worst trading day...",
  "response_id": "eval_001_C",
  "active_segments": [
    {
      "layer": "ANCHORS",
      "segment": "OWNERSHIP",
      "influence": "ACTIVE",
      "evidence": "Response redirected from market blame to personal rule-breaking",
      "source_facts": [
        {"fact_id": 2341, "text": "Believes outcomes are his responsibility..."},
        {"fact_id": 1872, "text": "Axiom: personal agency over external attribution..."}
      ]
    },
    {
      "layer": "PREDICTIONS",
      "segment": "FRUSTRATION COMPOUNDING",
      "influence": "ACTIVE",
      "evidence": "Response isolated the trading loss from career/life concerns",
      "source_facts": [
        {"fact_id": 3102, "text": "Multiple concurrent frustrations compound into existential questioning..."}
      ]
    }
  ],
  "theme_facts_used": [1456, 1457, 2890],
  "episode_conversations_used": [1234],
  "provenance_depth": 3,
  "timestamp": "2026-02-25T14:00:00"
}
```

### Provenance Scoring

Each provenance record gets scored on two axes:

**Accuracy** — Did the response use the brief content correctly?
- 1: Misinterpreted (used a fact but got it wrong)
- 2: Shallow (mentioned the topic but added nothing)
- 3: Correct (used the fact accurately)
- 4: Enriched (combined the fact with other context to produce insight)
- 5: Transformed (used the fact in a way that demonstrates deep understanding)

**Necessity** — Would the response have been worse without this provenance chain?
- 1: No — the model would have said the same thing
- 2: Marginal — slightly better with the fact
- 3: Noticeable — meaningfully different with the fact
- 4: Essential — this insight only exists because of the brief
- 5: Defining — this fact shaped the entire response frame

**Provenance Value** = Accuracy x Necessity (1-25 scale, 15+ is high-value provenance)

### Aggregate Provenance Metrics

Across many queries, provenance data reveals systemic patterns:

| Metric | What It Reveals |
|---|---|
| **Most-cited facts** | Which facts in the database produce the most value |
| **Never-cited facts** | Identity-tier facts that never influence responses — candidates for removal |
| **Layer contribution ratio** | ANCHORS vs CORE vs PREDICTIONS vs Themes vs Episodes — where does the value come from? |
| **Fact-to-response distance** | How many provenance links between the raw fact and the response? More links = more transformation |
| **Error provenance** | When the AI gets something wrong, which fact or layer introduced the error? |

---

## 4. Identity Accuracy

### The Problem

Utilization and provenance measure HOW the brief is used. Identity accuracy measures WHETHER the AI's behavior actually matches the person. This is the "ground truth" question: is the AI right about who this person is?

### Methodology: Multi-Source Validation

Identity accuracy cannot be measured from a single angle. Four complementary approaches:

#### 4A: Subject Self-Rating (Existing)

The blind A/B/C eval (Section 1). The subject rates responses on the 1-5 scale across personalization, prediction, advice fit, tone, composition, and "seen" factor.

**Strengths:** Only the person themselves can truly judge.
**Weaknesses:** Bias (subject designed the system), fatigue (180 ratings is too many), subjectivity.

**Improved protocol (based on Session 32 lessons):**
- 3 dimensions only: personalization accuracy, behavioral prediction, "seen" factor
- 3 dimensions x 3 conditions x 10 prompts = 90 ratings (manageable in one sitting)
- Mandatory 24h delay between generation and rating
- Notes required for all 4+ and 1 scores only (reduces note burden)

#### 4B: Factual Verification (Automated)

Ask the judge model to extract every factual claim the AI made in its response, then verify each claim against the fact database.

**Judge prompt for claim extraction:**

```
Read this AI response and extract every factual claim it makes about the user. Include:
- Explicit claims ("you founded a startup" — claims he founded a startup)
- Implicit claims ("given your experience with startup fundraising" — claims he has fundraising experience)
- Behavioral claims ("you tend to overthink these decisions" — claims a behavioral pattern)
- Relational claims ("your spouse would probably..." — claims knowledge of a relationship)

For each claim, output:
{
  "claim": "<the factual claim>",
  "type": "explicit" | "implicit" | "behavioral" | "relational",
  "quote": "<the text in the response that contains this claim>"
}
```

**Verification** against fact database:
1. Embed each extracted claim
2. Query ChromaDB for the most similar facts
3. If similarity > threshold (e.g., 0.75): check if the fact confirms or contradicts the claim
4. If no similar fact found: mark as UNVERIFIABLE (the system made it up or the fact base doesn't cover it)

**Accuracy metrics:**

| Metric | Formula |
|---|---|
| **Factual Precision** | Verified-correct claims / total claims |
| **Hallucination Rate** | Claims contradicted by facts / total claims |
| **Confabulation Rate** | Unverifiable claims / total claims |
| **Claim Density** | Total claims / response word count |

**Thresholds:**

| Metric | Target | Acceptable | Failure |
|---|---|---|---|
| Factual Precision | > 90% | 80-90% | < 80% |
| Hallucination Rate | < 5% | 5-10% | > 10% |
| Confabulation Rate | < 20% | 20-30% | > 30% |

**Note:** Confabulation is not always bad. An AI that says "you'd probably want a restaurant that's not too loud" might be making a reasonable inference even if no fact explicitly says the person dislikes loud restaurants. High confabulation rate with high subject approval means the system enables good inference. High confabulation rate with low approval means the AI is making things up.

#### 4C: Third-Party Validation

Ask someone who knows the subject well (partner, close friend, long-time colleague) to rate the AI's responses WITHOUT seeing the brief.

**Protocol:**
1. Show the third party 5 AI responses to 5 prompts (brief-augmented only)
2. Ask: "On a scale of 1-5, how well does this AI seem to know [person]?"
3. Ask: "What did the AI get wrong?"
4. Ask: "What did the AI miss that it should have known?"

**Strengths:** Independent verification. Catches self-serving bias in subject's own ratings.
**Weaknesses:** Different people know different facets. A partner knows different things than a colleague.
**Use case:** The external user experiment is the first test of this. Their ratings compared to the primary user's self-ratings reveal whether the brief captures what others observe, not just what the subject believes about themselves.

#### 4D: Prediction Verification (Longitudinal)

The PREDICTIONS layer makes specific behavioral claims: "When experiencing multiple concurrent frustrations, individual setbacks compound into systemic despair." These are testable over time.

**Protocol:**
1. Extract every prediction from the PREDICTIONS layer
2. For each prediction, define a detection trigger (already present in the layer as "Detection:" fields)
3. As new conversations are imported, flag conversations where detection triggers match
4. In those conversations, check: did the predicted behavior actually occur?
5. Score: prediction confirmed / prediction contradicted / ambiguous

**Prediction tracking table:**

| Prediction | Detection Trigger | Conversations Tested | Confirmed | Contradicted | Accuracy |
|---|---|---|---|---|---|
| DELAYED BELIEF REVISION | Extended drawdown, sudden overhaul | - | - | - | - |
| FRUSTRATION COMPOUNDING | Domain-specific to existential shift | - | - | - | - |
| RAPID RECOVERY CYCLING | Setback followed by systematic adjustment | - | - | - | - |

This is a slow-burn evaluation. It requires ongoing conversation import and cannot be batch-run. But it is the most rigorous test of whether the PREDICTIONS layer is actually predictive.

---

## 5. Regression Testing

### The Problem

Every time a layer is regenerated (CORE rewrite per D-050, periodic ANCHORS re-extraction, PREDICTIONS refresh after new conversations), quality might improve or degrade. Without regression testing, you only discover degradation when the AI starts behaving badly.

### Fixed Query Set

Regression testing requires a **fixed, versioned query set** that is run before and after every layer change. The existing 10 eval prompts from the A/B/C eval serve as the foundation, expanded to 30 for broader coverage (see Section 6: Benchmark Design).

### Regression Protocol

**Before any layer regeneration:**

1. Run the full benchmark query set against the current brief (condition C only — no need for A/B comparison during regression)
2. Save all responses with timestamps and layer versions
3. Run utilization scoring on all responses
4. Compute aggregate scores: mean "seen" factor, mean utilization, mean factual precision

**After layer regeneration:**

5. Run the same benchmark query set against the new brief
6. Save all responses with timestamps and new layer versions
7. Run utilization scoring on all responses
8. Compute aggregate scores with new layers

**Comparison:**

| Metric | Before | After | Delta | Verdict |
|---|---|---|---|---|
| Mean Seen Factor (human-rated) | 3.8 | ? | ? | Improve / Hold / Regress |
| Mean Active Utilization | 31% | ? | ? | Improve / Hold / Regress |
| Mean Factual Precision | 88% | ? | ? | Improve / Hold / Regress |
| Hallucination Rate | 3% | ? | ? | Improve / Hold / Regress |
| Layer Utilization (changed layer) | X% | ? | ? | Improve / Hold / Regress |

**Regression thresholds:**
- **Pass:** No metric drops by more than 0.5 points (1-5 scale) or 5 percentage points
- **Warning:** Any metric drops 0.5-1.0 points or 5-10 percentage points
- **Fail:** Any metric drops more than 1.0 point or 10 percentage points — do not deploy the new layer

### Automated Regression (No Human Rating)

Full human rating for every layer change is impractical. The automated path:

1. Run benchmark queries against old and new brief
2. Run LLM-as-judge on both response sets using the same rubric (personalization, prediction, "seen" factor — but scored by judge model, not human)
3. Run factual verification (Section 4B) on both response sets
4. Run utilization scoring on both response sets
5. Compare all metrics

**LLM-as-judge prompt for automated regression:**

```
You are evaluating an AI response for how well it demonstrates knowledge of a specific person. You have access to the person's identity brief (ground truth).

Rate this response on three dimensions (1-5 scale each):

1. Personalization Accuracy: Does the response reflect real traits, preferences, patterns from the brief? (1=generic, 5=deeply specific)
2. Behavioral Prediction: Does the response anticipate how this person would react or decide? (1=platitudes, 5=specific predictions)
3. "Seen" Factor: Overall, does this response feel like it was written by someone who knows this person? (1=stranger, 5=close friend)

<identity_brief>
[Full brief]
</identity_brief>

<user_message>
[Query]
</user_message>

<ai_response>
[Response to evaluate]
</ai_response>

Respond with JSON:
{
  "personalization_accuracy": <1-5>,
  "behavioral_prediction": <1-5>,
  "seen_factor": <1-5>,
  "justification": "<2-3 sentences>"
}
```

**Calibration:** Before trusting the LLM judge, run it on the existing Session 32 eval data where human scores exist. If the judge's scores correlate with human scores (Pearson r > 0.7), the judge is calibrated. If not, adjust the judge prompt until correlation is acceptable.

### Version Tracking

Every layer regeneration creates a version record:

```json
{
  "layer": "CORE",
  "version": "v2",
  "generated_at": "2026-02-26T10:00:00",
  "model": "claude-sonnet-4-20250514",
  "input_facts": 390,
  "prompt_version": "D-050",
  "regression_result": {
    "benchmark_run_id": "reg_003",
    "verdict": "PASS",
    "metrics": {
      "seen_factor_delta": +0.3,
      "utilization_delta": +5,
      "precision_delta": +2
    }
  },
  "previous_version": "v1",
  "deployed": true
}
```

---

## 6. Benchmark Design

### The Problem

The existing 10 eval prompts were designed for the A/B/C blind eval. They test important dimensions, but 10 queries is too few for regression testing (small sample size makes deltas noisy) and the category coverage has gaps.

A proper benchmark needs 30-50 queries with systematic coverage of every identity dimension the brief claims to capture.

### Benchmark Query Categories

Queries are organized by what aspect of identity they test. Each query should be answerable differently depending on what the AI knows about the person.

#### Category 1: Biographical Recall (5 queries)
Tests whether the AI knows basic facts about the person.

| # | Query | What It Tests | Expected Brief Element |
|---|---|---|---|
| B1 | "What do you know about my professional background?" | Direct biographical recall | CORE layer |
| B2 | "Can you help me update my LinkedIn headline?" | Biographical + career framing | CORE (career section) |
| B3 | "My mom asked what I'm doing for work these days. How do I explain it?" | Biographical + audience adaptation | CORE + PREDICTIONS (communication) |
| B4 | "I'm filling out a visa application and need to describe my occupation." | Factual biographical accuracy | CORE (career facts) |
| B5 | "Someone asked my partner what I do. What would they say?" | Relational + biographical | CORE (spouse paragraph, career) |

**Scoring:** Primarily factual precision. Count correct facts, flag hallucinations.

#### Category 2: Preference Prediction (5 queries)
Tests whether the AI can predict what the person would choose.

| # | Query | What It Tests | Expected Brief Element |
|---|---|---|---|
| P1 | "I need a new book to read. What would I like?" | Interest prediction | CORE + Themes |
| P2 | "We're picking a restaurant for my partner's birthday. What should I look for?" | Preference + relational | CORE (spouse) + Themes |
| P3 | "I'm setting up a new home office. What matters most to me?" | Environmental preference | CORE (how he works) |
| P4 | "Should I get a MacBook or stick with Windows for my next laptop?" | Technical preference | CORE + Themes (technical context) |
| P5 | "I have a free Saturday. What would I probably end up doing?" | Lifestyle prediction | CORE + PREDICTIONS |

**Scoring:** Subject rates whether the prediction is accurate (would they actually choose/do that?).

#### Category 3: Emotional Situations (5 queries)
Tests whether the AI responds appropriately to the person's emotional patterns.

| # | Query | What It Tests | Expected Brief Element |
|---|---|---|---|
| E1 | "I just had my worst trading day in months. Broke my rules, revenge traded, and lost $400." | Emotional response calibration | PREDICTIONS (frustration compounding, accountability amplification) + ANCHORS (ownership) |
| E2 | "My partner and I had a fight about money. I don't want to talk about the details, just... help me think." | Relational stress | PREDICTIONS (uncertainty tolerance) + CORE (spouse) |
| E3 | "I keep thinking about my previous startup and what went wrong. I can't let it go." | Past loss processing | CORE (what he's lost) + PREDICTIONS (delayed belief revision) |
| E4 | "Everything feels stuck. Trading isn't working, job search is slow, Base Layer is taking forever." | Compounding frustration | PREDICTIONS (frustration compounding) + ANCHORS (ownership, systematize) |
| E5 | "I actually had a really good day. Three winning trades, got a callback on a role, and made progress on the manifesto." | Positive momentum (trap for premature optimization) | PREDICTIONS (premature optimization trigger) |

**Scoring:** Tone match + behavioral prediction. Did the AI respond in the right way for THIS person, not just any person in this situation?

#### Category 4: Decision Frameworks (5 queries)
Tests whether the AI provides advice calibrated to how this person actually makes decisions.

| # | Query | What It Tests | Expected Brief Element |
|---|---|---|---|
| D1 | "I got an offer for a VP role but it means pausing Base Layer. How do I think about this?" | Career decision framework | ANCHORS (agency, foundation) + CORE (career + Base Layer) |
| D2 | "Should I raise money for Base Layer or bootstrap it?" | Business strategy | CORE (built, Base Layer) + ANCHORS (agency) |
| D3 | "I'm thinking about switching from Haiku to Sonnet for extraction. It's 10x the cost but probably better. Worth it?" | Technical cost/quality tradeoff | Themes (project context) |
| D4 | "A friend wants me to co-found a company with him. He's a great engineer but we've never worked together." | Partnership evaluation | PREDICTIONS (environmental threat scanning) + ANCHORS (agency) |
| D5 | "My trading account is down 20% this month. Do I stop trading or double down on fixing my system?" | Risk management under pressure | PREDICTIONS (delayed belief revision, accountability amplification) + ANCHORS (learning, ownership) |

**Scoring:** Advice fit (would the subject actually follow this advice?) + framework quality (did it provide a structure for thinking, not just an answer?).

#### Category 5: Communication Style (5 queries)
Tests whether the AI matches the person's communication preferences.

| # | Query | What It Tests | Expected Brief Element |
|---|---|---|---|
| C1 | "Explain to me why RAG isn't good enough for what we're building." | Direct technical explanation | BRIEF_INSTRUCTION (direct, opinionated) |
| C2 | "Give me honest feedback on this idea: what if we let users edit their own facts?" | Willingness to challenge | ANCHORS (questioning, coherence) + BRIEF_INSTRUCTION |
| C3 | "I need you to help me prep for a pitch meeting in 10 minutes. Go." | Time pressure, conciseness | BRIEF_INSTRUCTION (concise, framework-oriented) |
| C4 | "This is a philosophical question, not a practical one. What does it mean for an AI to 'know' someone?" | Abstract reasoning tolerance | ANCHORS (questioning, relevance) |
| C5 | "I'm frustrated and I just need someone to tell me I'm not crazy for trying to build this." | Validation request vs. challenge | PREDICTIONS (accountability amplification) + BRIEF_INSTRUCTION |

**Scoring:** Tone match. Did the AI respond with the right level of directness, challenge, conciseness, and framework-thinking?

#### Category 6: Creative Collaboration (5 queries)
Tests whether the AI collaborates in a way that fits the person's style.

| # | Query | What It Tests | Expected Brief Element |
|---|---|---|---|
| CR1 | "Help me write the opening paragraph of a blog post about why AI should remember you." | Writing voice match | BRIEF_INSTRUCTION + CORE (beliefs about AI) |
| CR2 | "I need a name for a feature that lets users review and correct facts about themselves. Brainstorm with me." | Collaborative ideation | CORE (Base Layer context) + BRIEF_INSTRUCTION |
| CR3 | "Draft an email to a potential beta tester explaining what Base Layer does." | External communication calibration | CORE (Base Layer + career) |
| CR4 | "I want to write a journal entry about today. Start me off." | Personal voice match | CORE (communication style) + Themes |
| CR5 | "Help me structure a presentation about the difference between memory and identity for an AI audience." | Technical communication | CORE (beliefs) + ANCHORS (framework thinking) |

**Scoring:** Novel composition + tone match. Did the creative output sound like the person, or like a generic AI?

### Total Benchmark: 30 Queries

| Category | Count | Primary Scoring Dimensions |
|---|---|---|
| Biographical Recall | 5 | Factual precision, hallucination rate |
| Preference Prediction | 5 | Subject accuracy rating |
| Emotional Situations | 5 | Tone match, behavioral prediction |
| Decision Frameworks | 5 | Advice fit, framework quality |
| Communication Style | 5 | Tone match |
| Creative Collaboration | 5 | Novel composition, tone match |

### Benchmark Versioning

The benchmark query set is versioned and frozen. When queries need updating (person's life changes, prompts become stale), a new version is created and old versions are archived. This allows longitudinal comparison across system versions.

```
data/eval/benchmark_v1.json   # 30 queries, frozen
data/eval/benchmark_v2.json   # Future revision (new queries for changed life circumstances)
```

---

## 7. Implementation Plan

### Phase 1: Benchmark Foundation (Build First)

**What:** Finalize the 30-query benchmark set and build the automated runner.

**Implementation:**
1. Add 20 new queries to `run_eval.py` (currently has 10)
2. Add benchmark versioning (load queries from `data/eval/benchmark_v1.json` instead of hardcoded)
3. Add condition-C-only mode for regression testing (`run_eval.py --regression`)
4. Add LLM-as-judge scoring (`run_eval.py --auto-score`)

**Depends on:** Nothing. Can start immediately.
**Cost:** ~$2-5 per full benchmark run (30 queries x Sonnet generation + judge scoring)
**Time:** 1-2 sessions.

### Phase 2: Automated Utilization Scoring

**What:** Build the segment-and-score pipeline from Section 2.

**Implementation:**
1. Build brief segmenter: parse the assembled brief XML into labeled segments
2. Build judge prompt for segment attribution
3. Run attribution on benchmark responses
4. Compute utilization metrics
5. Store results in `data/eval/utilization/`

**Depends on:** Phase 1 (needs benchmark responses to score).
**Cost:** ~$1-3 per full utilization run (30 queries x judge call)
**Time:** 1-2 sessions.

### Phase 3: Provenance Chain

**What:** Build the fact-to-response tracing from Section 3.

**Implementation:**
1. Add fact-ID logging to author_layers.py (which facts were retrieved per layer)
2. Build provenance query: given active segments, trace back to source facts via embedding similarity
3. Build provenance record format (JSON)
4. Add `baselayer provenance <response-id>` CLI command

**Depends on:** Phase 2 (needs utilization scoring to identify active segments).
**Cost:** Minimal (embedding queries are local, no API cost).
**Time:** 1-2 sessions.

### Phase 4: Factual Verification

**What:** Build the automated claim extraction and verification from Section 4B.

**Implementation:**
1. Build claim extractor (judge prompt)
2. Build claim verifier (embed claim, query fact database, compare)
3. Compute precision / hallucination / confabulation metrics
4. Add to regression pipeline

**Depends on:** Phase 1 (needs benchmark responses). Independent of Phases 2-3.
**Cost:** ~$1-2 per verification run (30 queries x claim extraction)
**Time:** 1 session.

### Phase 5: Regression Pipeline

**What:** Wire together Phases 1-4 into a single regression command.

**Implementation:**
1. `baselayer eval --regression` runs the full pipeline:
   - Generate benchmark responses with current brief
   - Run LLM-as-judge scoring
   - Run utilization scoring
   - Run factual verification
   - Compare to previous run
   - Output pass/warning/fail verdict
2. Store version records for each layer change
3. Add `baselayer eval --compare v1 v2` to diff any two runs

**Depends on:** Phases 1-4.
**Cost:** ~$5-10 per regression run.
**Time:** 1 session.

### Phase 6: Longitudinal Tracking

**What:** Prediction verification and long-term accuracy trends from Section 4D.

**Implementation:**
1. Extract testable predictions from PREDICTIONS layer
2. Build detection trigger matching against new conversations
3. Track confirmation/contradiction rates over time
4. Dashboard or report generation

**Depends on:** Ongoing conversation import. No code dependency on Phases 1-5.
**Time:** Ongoing.

### Implementation Priority

```
Phase 1 (Benchmark)     ████████  HIGH — everything depends on this
Phase 4 (Verification)  ██████    HIGH — automated, no human rating needed
Phase 2 (Utilization)   █████     MEDIUM — valuable but not blocking
Phase 5 (Regression)    █████     MEDIUM — needs Phases 1+4 minimum
Phase 3 (Provenance)    ███       MEDIUM — diagnostic, not blocking
Phase 6 (Longitudinal)  ██        LOW — slow burn, start when convenient
```

---

## 8. Cost Estimates

| Operation | Model | Queries | Est. Cost |
|---|---|---|---|
| Benchmark generation (C only) | Sonnet | 30 | ~$1.50 |
| Benchmark generation (A/B/C) | Sonnet | 90 | ~$4.50 |
| LLM-as-judge scoring | Sonnet | 30 | ~$1.00 |
| Utilization scoring | Sonnet | 30 | ~$1.50 |
| Factual verification | Sonnet | 30 | ~$1.00 |
| **Full regression run** | **Sonnet** | **30** | **~$5.00** |
| **Full A/B/C eval + all scoring** | **Sonnet** | **90** | **~$9.00** |

All costs assume Sonnet. Using Haiku for judge/verification tasks would cut costs by ~80% but with lower judgment quality. Recommended: Sonnet for all eval tasks — accuracy of evaluation matters more than cost savings here.

---

## 9. Open Questions

1. **LLM judge calibration:** How well does the LLM judge correlate with human ratings? Must validate before trusting automated regression. The Session 32 data provides the calibration set.

2. **LATENT attribution reliability:** Can a judge model reliably identify when an axiom shaped what the AI did NOT say? Latent influence is important (ANCHORS work by constraining, not by producing text) but may be unreliable at scale.

3. **Cross-model benchmark validity:** If the benchmark is calibrated on Sonnet responses, do scores transfer when the user switches to Opus or Haiku? Brief effectiveness may vary by model capability.

4. **Benchmark decay:** The benchmark queries reference current life circumstances (previous startup, trading, Base Layer). As life changes, queries become stale. How often should the benchmark be refreshed? Proposal: annual review, with a stable "evergreen" subset (emotional patterns, decision frameworks) that should remain valid across life changes.

5. **Third-party validation logistics:** Getting external subjects or friends to rate responses requires designing a simple, non-technical rating interface. A markdown file with responses and a 1-5 scale is minimum viable.

6. **Provenance for theme/episode retrieval:** Theme and episode retrieval changes per query (unlike identity layers which are static). This means provenance for these layers is query-specific. Should utilization scoring weight these differently than the always-on identity layers?

---

## 10. First Experiment: Subject B (30-day journals)

- **Input:** 30 days of freeform journals
- **Pipeline:** extract_facts -> score -> embed -> cluster -> assemble_brief
- **Additional validation:** Subject B reviews the generated identity block directly — "is this me?"
- **Eval timing:** After brief is generated, run the 30-query benchmark protocol above
- **Cold start signal:** 30 days of journals vs. User A's 1,892 conversations — how much data is enough?
- **Cross-validation:** User A rates Subject B's brief-augmented responses (third-party validation for her, subject validation for him)

---

## 11. Pipeline vs Prompt Eval (Session 59)

### The Problem

The existing A/B/C eval (Section 1) tests whether the brief outperforms raw history and baseline. But it does not isolate *why* the brief works. Is the value from the pipeline execution (extraction, scoring, classification, tiering, authoring) or from the structured prompt format (XML tags, three-layer architecture, behavioral predictions)? If someone took the same raw data and wrote a good prompt around it — without running any pipeline — would the result be comparable?

This is the critical question for the three-tier product model (D-060): if prompting alone produces 80% of the value, Tier 1 (Preferences) is the product. If pipeline execution adds measurable value, Tier 2-3 justify their existence.

### Test Conditions

| Condition | Context Provided | What It Isolates |
|---|---|---|
| **A: Base Layer Brief** | Full assembled brief (~5,000 tokens). Three-layer identity (ANCHORS + CORE + PREDICTIONS) + themes + episodes. Pipeline-produced. | Full pipeline value |
| **B: Raw + Naive Prompt** | Same raw conversation data, stuffed into a generic prompt: "Here is the user's conversation history. Use it to personalize your response." No structure, no extraction, no classification. | Baseline: raw data + minimal prompting |
| **C: Raw + Pipeline Prompts** | Same raw conversation data, structured with Base Layer's prompt engineering (XML tags, three-layer headers, behavioral prediction format) but WITHOUT running the pipeline. Manually or heuristically assembled — no extraction, no scoring, no tiering. | Prompt engineering value (format + structure) |

Same prompts/questions across all three conditions. Same model. Same temperature. Same token budget (~5,000 tokens per condition).

### What Each Comparison Reveals

| Comparison | What It Measures |
|---|---|
| **A > B** | Full system value (pipeline + prompts) over raw data |
| **C > B** | Prompt engineering / structural format value |
| **A > C** | Pipeline execution value — the delta that extraction, scoring, classification, tiering, and authoring add beyond good prompting |
| **A = C** | Pipeline adds no value — prompt engineering is the product |
| **C = B** | Prompt format adds no value — all value comes from pipeline processing |

**The key result is A vs C.** If A > C by a meaningful margin, the pipeline's upstream reasoning (Quiet-STaR analogy: "thinking before speaking" at the system level) adds real value. If A = C, the pipeline is overhead.

### Protocol

1. Select 10 prompts from the existing benchmark set (Section 6) spanning all categories
2. For each prompt, generate responses under all three conditions
3. **LLM-as-Judge (Opus):** Score all responses blind on personalization accuracy, behavioral prediction, and "seen" factor using the judge prompt from Section 5
4. **Human review:** Subject rates a 5-response sample per condition (15 total) as calibration
5. Compare: A vs B (table stakes), C vs B (format value), A vs C (pipeline value)
6. If A > C by >= 0.5 mean score on any dimension, pipeline execution is validated
7. If A = C (< 0.3 mean delta), the pipeline adds no measurable value — reconsider Tier 2-3 product model

### Double-Blind Methodology

Both the LLM judge and the human rater evaluate blind:
- **LLM judge** receives responses labeled X, Y, Z (randomized per prompt). Judge does not know which condition produced which response.
- **Human rater** receives the same blinded labels. Rates independently of judge scores.
- **Correlation check:** After scoring, compute agreement between LLM judge and human rater. If Pearson r < 0.6, investigate calibration gap before drawing conclusions.

This double-blind design (LLM judge + human review) ensures no single evaluation source can bias the result.

### Estimated Cost

- Response generation: 10 prompts x 3 conditions x Sonnet = ~$1.50
- LLM-as-Judge: 30 responses x Opus scoring = ~$3.00
- Total: ~$4.50 (excluding human time)

---

## 12. Cross-Domain Eval (Session 59)

### The Problem

Base Layer has been validated on three corpora: AI conversations (User A), newsletters (User B), and journals (Subject B). All are personal or semi-personal text. The question: does the pipeline generalize to fundamentally different text types?

### Proposed Domains

| Domain | Source Material | Why It Matters |
|---|---|---|
| **Book** | Published autobiography or memoir (public domain) | Long-form narrative, single voice, rich behavioral data |
| **Research paper** | Published academic paper(s) by a single author | Technical reasoning, intellectual identity, citation patterns |
| **Legal document** | Court filings, legal briefs (public record) | Formal register, adversarial framing, domain-specific language |
| **Journal** | Personal journal entries (consented participant) | Reflective, high identity signal, already validated with Subject B |

### Evaluation Approach

For each domain:
1. Import text through standard pipeline (`baselayer import`)
2. Run full 13-step pipeline
3. Generate identity layers
4. Evaluate with Collective review (Sonnet self-review + Opus 4-persona)
5. Run Pipeline vs Prompt eval (Section 11) on domain-specific prompts
6. Score: Does the pipeline produce identity layers that a domain expert would recognize as accurate?

**Public domain materials only** for published results. No consent issues, full reproducibility.

### Success Criteria

- Collective score >= 70/100 on at least 3 of 4 domains
- Pipeline vs Prompt eval shows A > C on at least 2 of 4 domains
- No catastrophic failure (hallucinated identity, completely wrong behavioral model) on any domain

### Connection to Three-Tier Model

Cross-domain validation directly tests the strategic reframing from Session 52: Base Layer is a behavioral pattern extraction/compression engine for ANY text corpus, not just conversations. If the pipeline works on books, papers, and legal documents, the addressable market expands beyond "people who talk to AI" to "anyone with text they want an AI to understand."

---

## 13. Future Experiments

- **Autobiography test:** Generate identity block from published autobiography, send to living author for validation
- **Cross-model:** Same brief, different LLMs — does the brief transfer across models?
- **Longitudinal:** Re-run eval after 60, 90 days — does the brief improve with more data?
- **Degradation test:** Intentionally corrupt/omit predictions — which ones matter most? (ablation study)
- **Token budget optimization:** Run benchmark at 2K, 3K, 4K, 5K token budgets — where is the quality knee?
- **Competitor comparison:** Run the benchmark with Mem0 memory injection as condition D. Requires Mem0 integration for fair comparison.
- **Multi-user benchmark:** Once Subject B experiment completes, compare benchmark scores across two users to identify whether the framework generalizes or is overfit to one person.

---

## 14. File Organization

```
docs/eval/EVAL_FRAMEWORK.md          # This document
data/eval/benchmark_v1.json           # Frozen query set (30 queries)
data/eval/eval_results.json           # A/B/C response data
data/eval/eval_ratings.json           # Human ratings
data/eval/eval_analysis.json          # Computed analysis
data/eval/eval_blind_responses.md     # Blind rating file
data/eval/utilization/                # Per-run utilization reports
data/eval/provenance/                 # Per-run provenance records
data/eval/regression/                 # Version comparison data
data/eval/pipeline_vs_prompt/         # Pipeline vs Prompt eval results (S59)
data/eval/cross_domain/              # Cross-domain eval results (S59)
scripts/run_eval.py                   # Eval runner (A/B/C + regression + auto-score)
scripts/run_validation_study.py       # Validation study runner (8 modes)
```
