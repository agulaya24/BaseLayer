# Behavioral Compression Benchmark (BCB-0.1)

## Purpose

Measure whether a behavioral brief — a compressed representation of a person's reasoning patterns, values, and behavioral tendencies — retains decision-relevant signal from source material while dramatically reducing context size.

This benchmark tests **the brief as an artifact**, independent of how it was produced. Any system that takes personal text and outputs a behavioral brief can be evaluated against these metrics.

## Core Claim (Pre-Registered)

> A behavioral brief retaining <5% of source tokens preserves ≥90% of decision-relevant signal as measured by identity-sensitive behavioral prediction tasks.

Null hypothesis: The brief performs no better than a cold model (no context).

## Five Metrics

### 1. Compression Ratio (CR)

**What it measures:** How much the brief reduces source material.

**Definition:**
```
CR = 1 - (brief_tokens / source_tokens)
```

**Two levels:**
- **Pipeline CR**: source_tokens = total input corpus (conversations, journals, etc.)
- **Extraction CR**: source_tokens = extracted facts/structured data

**Threshold:** CR ≥ 0.95 (95%+ reduction) for Pipeline CR.

**Current data:**
| Subject | Source tokens | Brief tokens | Pipeline CR |
|---------|-------------|-------------|-------------|
| User A | ~10M (est. 40,997 messages) | ~2,400 | 99.98% |
| Franklin | ~19K (75,383 words) | ~1,200 (est.) | 93.7% |

### 2. Signal Retention Score (SRS)

**What it measures:** How much behavioral prediction quality the brief preserves compared to providing the model with full structured context.

**Protocol:**
1. Define N identity-sensitive prompts (≥10) covering: value tradeoffs, domain-specific decisions, emotional regulation, contradiction stress, domain gaps
2. Generate responses under conditions:
   - **C1 (Cold):** No identity context — establishes baseline
   - **C2 (Full Extraction):** All structured layers/facts — establishes ceiling
   - **C5c (Brief):** Compressed behavioral brief only — test condition
3. Judge all responses blind on 5 dimensions (1-5 scale):
   - **Recognition:** Does the response reflect documented behavioral patterns?
   - **Calibration:** Does the voice match characteristic communication style?
   - **Depth:** Does it go beyond surface-level to reveal underlying reasoning?
   - **Usefulness:** Does it predict how the subject would actually behave?
   - **Specificity:** Does it reference subject-specific details, not generic advice?
4. Compute:

```
Signal_Lift(condition) = Score(condition) - Score(C1)
SRS = Signal_Lift(C5c) / Signal_Lift(C2)
```

**Edge case:** When Signal_Lift(C2) ≤ 0 (full context provides no lift or hurts), SRS is undefined. This is itself an important finding — it means structured context failed and the formula reduces to a simpler question: does the brief provide any lift at all? Report as:
- **SRS = "exceeds ceiling"** when Signal_Lift(C5c) > 0 and Signal_Lift(C2) ≤ 0
- Use absolute lift (Score(C5c) - Score(C1)) as the primary metric in this case

**Threshold:** SRS ≥ 0.90 (brief retains ≥90% of full-context lift). When SRS is undefined, the brief passes if Signal_Lift(C5c) > 0.

**Current data (Franklin, N=10):**
| Condition | Mean Score | Lift over C1 |
|-----------|-----------|-------------|
| C1 (Cold) | 3.92 | — |
| C2 (Full Layers) | 3.90 | -0.02 |
| C5c (Brief) | 4.32 | +0.40 |

Franklin SRS = **exceeds ceiling**. Full layers provided zero lift (-0.02); brief provided +0.40 absolute lift. This suggests compression doesn't just retain signal — it makes it actionable. Models can leverage narrative behavioral descriptions more effectively than structured data dumps.

**Current data (User A, N=10, computed S73):**
| Condition | Mean Score | Lift over C1 |
|-----------|-----------|-------------|
| C1 (Cold) | 3.425 | — |
| C2 (Full Layers) | 4.900 | +1.475 |
| C3 (Raw Facts) | 4.475 | +1.050 |
| C5c (Brief) | 4.850 | +1.425 |

User A SRS = **96.6%** (1.425 / 1.475). Brief retains 96.6% of full structured context lift. Passes ≥90% threshold. Unlike Franklin (where C2 provided no lift), User A's C2 provides substantial lift (+1.475), making SRS a meaningful ratio. The brief loses only 0.05 points (4.85 vs 4.90) despite 99.98% token reduction.

**Interpretation framework:**
- SRS = "exceeds ceiling": Compression amplifies. The brief format helps the model leverage information that structured context cannot.
- SRS > 1.0: Compression amplifies (structured context helped, brief helped more).
- SRS = 0.90–1.0: Strong retention. Brief loses minimal signal.
- SRS = 0.50–0.90: Partial retention. Significant information loss in compression.
- SRS < 0.50: Compression failure. Brief discards too much.

### 3. Drift Resistance Score (DRS)

**What it measures:** Whether the brief maintains stable identity modeling across extended multi-turn conversations, especially when topics shift or contradictory cues are introduced.

**Protocol:**
1. Run multi-turn scenarios (≥8 turns) that:
   - Start in one domain (trading, career)
   - Shift to a different domain mid-conversation (parenting, philosophy)
   - Include subtle contradictory cues ("Maybe I should just trust my gut" to someone whose pattern is systematic analysis)
2. Judge the final turn response for:
   - **Anchor stability:** Does the model still reference core identity patterns from the brief?
   - **Cross-domain transfer:** Does it connect the new domain to known reasoning patterns?
   - **Contradiction handling:** Does it acknowledge the tension rather than accepting the contradictory cue?
3. Compare C1 vs C5c conditions on the same multi-turn sequence.

**Definition:**
```
DRS = AnchorMentions(C5c, turn_N) / AnchorMentions(C5c, turn_1)
```

Where AnchorMentions counts references to core identity patterns. DRS = 1.0 means perfect stability; DRS < 1.0 means drift.

**Threshold:** DRS ≥ 0.70 (retains ≥70% of anchor references by final turn).

**Adversarial variant:** Inject 3+ contradictory cues across the conversation. Measure whether the model pushes back or absorbs the contradiction. Score = (pushbacks / contradictions_introduced).

### 4. Cross-Model Consistency Score (CMCS)

**What it measures:** Whether the same brief produces structurally similar behavioral predictions across different foundation models.

**Protocol:**
1. Feed identical brief to ≥3 models (e.g., Sonnet, Opus, Haiku; or Claude, GPT, Gemini)
2. Generate responses to the same N prompts
3. For each prompt, measure structural alignment:
   - **Fact overlap:** What percentage of specific claims/references appear in all model outputs?
   - **Recommendation alignment:** Do the models give the same directional advice?
   - **Pattern recognition:** Do they identify the same behavioral patterns?
4. Score each prompt 0-1 for structural alignment, average across prompts.

**Definition:**
```
CMCS = mean(structural_alignment across all prompts)
```

**Threshold:** CMCS ≥ 0.70 (≥70% structural alignment across models).

**Why this matters:** If the brief produces consistent behavioral predictions across models, the signal is in the brief, not in model-specific patterns. This demonstrates that behavioral compression has externalized something real.

**Comparative baseline:** Run the same protocol with C1 (cold). Cold responses should show lower cross-model consistency because each model falls back on its own priors.

### 5. Variance Reduction Index (VRI)

**What it measures:** Whether the brief reduces stochastic variance in model outputs.

**Protocol:**
1. Select 5 identity-sensitive prompts
2. For each prompt, generate 10 responses at temperature > 0 (e.g., 0.7)
3. Measure variance:
   - **Score variance:** Standard deviation of judge ratings across 10 runs
   - **Content variance:** Semantic similarity (embedding cosine) of response pairs
4. Compare C1 variance vs C5c variance.

**Definition:**
```
VRI = 1 - (Var(C5c) / Var(C1))
```

VRI = 0 means no reduction. VRI = 1.0 means perfect consistency. Negative VRI means the brief *increased* variance.

**Threshold:** VRI ≥ 0.30 (brief reduces response variance by ≥30%).

**Intuition:** A cold model has wide variance because it's guessing from priors. A brief-equipped model should converge because identity constraints narrow the response space. The VRI measures how much the brief constrains the "cognitive jump distance" — the space of plausible responses.

## Evaluation Conditions

Standard condition set for full BCB evaluation:

| Code | Description | Purpose |
|------|-------------|---------|
| C1 | Cold — no identity context | Baseline |
| C2 | Full structured extraction (layers, facts) | Ceiling / structured context |
| C3 | Raw extracted facts only | Extraction without compression |
| C5c | Compressed behavioral brief | Test condition |
| C2-A | Anchors layer only | Ablation — axioms |
| C2-P | Predictions layer only | Ablation — behavioral predictions |
| C2-AP | Anchors + Predictions | Ablation — most compressed structured subset |

Optional conditions:
| Code | Description | Purpose |
|------|-------------|---------|
| CM | Provider memory import (e.g., Claude Memories) | Competitor comparison |
| G1 | ChatGPT with same user's conversation history | Cross-provider |

## Prompt Design Requirements

BCB prompts must cover:
1. **Value tradeoffs** — decisions where values conflict (2+ prompts)
2. **Domain-specific behavioral prediction** — how would the person act in their known domain? (2+ prompts)
3. **Emotional regulation** — how do they handle setbacks, stress, or success? (2+ prompts)
4. **Contradiction stress** — prompt that subtly invites the person to act against their documented patterns (1+ prompt)
5. **Domain gap — thin coverage** — area with minimal data (1+ prompt)
6. **Domain gap — zero coverage** — area with no data (1+ prompt)
7. **Meta-cognitive** — questions about the person's relationship to their own patterns (1+ prompt)

Minimum: 10 prompts. Recommended: 13+ (10 standard + 3 stress tests).

## Judging

**Primary:** LLM-as-Judge with a different model than the response generator. 5 dimensions, 1-5 scale.

**Validation:** Human blind review (subject rates responses without condition labels). Single dimension: "How well does this AI know you?" (1-5). Used to validate LLM judge rankings, not as primary metric.

**Multi-model judge panel (recommended):** ≥2 judge models. Flag disagreements >1 point. Report consensus scores.

## Reporting

A BCB-0.1 report must include:

```
BCB-0.1 Results: [Subject Identifier]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Source corpus:    [description, token count]
Brief size:       [token count]
Compression Ratio: [CR]%

Signal Retention Score:  [SRS] (threshold: ≥0.90)
Drift Resistance Score:  [DRS] (threshold: ≥0.70)
Cross-Model Consistency: [CMCS] (threshold: ≥0.70)
Variance Reduction:      [VRI] (threshold: ≥0.30)

Conditions tested: [N]
Prompts per condition: [N]
Judge model(s): [list]
Human validation: [yes/no, N responses]
```

## What This Benchmark Does NOT Measure

- **Extraction quality:** Whether the right facts were identified from source material. That's a pipeline evaluation, not a compression evaluation.
- **Privacy preservation:** Whether the brief leaks information that should be suppressed.
- **Temporal stability:** Whether the brief stays accurate as the person changes over time. (Candidate for BCB-0.2.)
- **Adversarial robustness:** Whether the brief can be jailbroken to override safety. (Separate evaluation needed.)

## Reproducibility

All BCB evaluations must provide:
1. Prompt set (full text)
2. Brief (full text, or redacted with token count)
3. Condition definitions
4. Judge prompt (full text)
5. Raw scores per response
6. Code to reproduce the evaluation

For privacy: subjects may redact brief content while still reporting metrics. Token counts and scores are sufficient for comparison.

## Relationship to Existing Benchmarks

- **KnowMe-Bench** (if published): Focuses on factual recall from conversations. BCB focuses on behavioral prediction, which requires compression and synthesis, not retrieval.
- **PerLTQA / LaMP:** Task-specific personalization benchmarks. BCB measures identity modeling, not task adaptation.
- **TIRB (Temporal Identity Reasoning Benchmark):** Complementary — tests temporal reasoning about identity change. BCB tests static identity compression at a point in time.

## Versioning

- **BCB-0.1:** Current. Single-subject, single-snapshot evaluation.
- **BCB-0.2 (planned):** Temporal stability (brief decay over simulated sessions), adversarial probing, multi-subject aggregation.
- **BCB-1.0 (target):** Standardized test harness, public leaderboard, N≥10 subjects, pre-registered analysis plans.
