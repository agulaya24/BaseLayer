# Temporal Prediction Test — Can 2024 Conversations Predict 2025/2026 Behavior?

## Hypothesis

If identity compression captures genuine behavioral invariants (not topic snapshots), then an identity model built exclusively from 2024 conversations should predict behavioral patterns observed in 2025/2026 conversations. The identity model is a specification of HOW someone operates, not WHAT they discuss — so it should generalize forward in time even as topics, projects, and circumstances change.

## Why This Matters

1. **Strongest validation of identity compression.** If past behavior predicts future behavior through the identity model, the compression is capturing something real.
2. **Directly addresses the temporality concern.** The redesigned temporal model (Session 23) argues that events accrue meaning and states change via contradiction, not decay. This test validates that framework.
3. **Publishable finding.** No existing memory system has demonstrated temporal prediction from compressed behavioral models. This is novel.
4. **Practical implication.** If it works, it means an identity model doesn't need to be rebuilt constantly — the behavioral core is durable.

## Test Design

### Data Split

Subject: Aarik (1,892 conversations across 2024-2026)

```
TRAINING SET:  All conversations from 2024 (and earlier)
TEST SET:      All conversations from 2025-2026
HOLDOUT:       Most recent month (March 2026) — for final validation
```

Need to verify conversation date distribution first:
- How many conversations per year?
- Are there topic shifts between years? (e.g., more trading in 2024, more Base Layer in 2025)
- Are there life circumstance changes? (company collapse, job search, new project)

### Pipeline

1. **Extract facts from 2024 conversations only** — fresh extraction, isolated environment
2. **Author identity model from 2024 facts using H3 prompts** — anchors, core, predictions, brief
3. **Extract facts from 2025/2026 conversations** — separate extraction
4. **Test predictions against 2025/2026 facts** — does the 2024 model predict observed patterns?

### Evaluation Methods

#### Method 1: Twin-2K Style Prediction Test
- Generate paired responses to 2025/2026 conversation prompts: one using the 2024 identity model, one generic
- Have the actual 2025/2026 responses as ground truth
- Blind evaluation: which response better matches the actual behavior?
- Metric: prediction accuracy (% of times the identity-informed response is closer to ground truth)

#### Method 2: Behavioral Pattern Matching
- Extract behavioral patterns from 2025/2026 conversations independently
- Compare to predictions layer from 2024 model
- Score: how many 2025/2026 patterns were anticipated by 2024 predictions?
- Score: how many 2024 predictions are contradicted by 2025/2026 behavior?

#### Method 3: Axiom Stability Test
- Author anchors from 2024 data
- Author anchors from 2025/2026 data
- Compare: which axioms persist? Which change? Which are new?
- High persistence = durable identity. High change = identity model captures states, not traits.

#### Method 4: Fact Prediction (Most Rigorous)
- From the 2024 identity model, generate 20 specific predictions about how this person would handle novel situations
- Check whether 2025/2026 conversations contain evidence confirming or disconfirming each prediction
- This is the most publishable metric — specific, falsifiable, scored against real data

### What Would Be Surprising

- **If 2024 model predicts 2025/2026 at >70% accuracy**: identity compression captures durable behavioral invariants. Strong validation.
- **If accuracy is 50-70%**: some patterns are durable, some are contextual. The model captures a mix of identity and circumstance.
- **If accuracy is <50%**: the model captures a snapshot, not identity. Temporal window matters more than we thought.
- **If later conversations predict earlier better than vice versa** (already hinted in the Franklin data — Q3→Q1 scored 26.4 vs Q1→Q3 scored 20.1): later behavior is a superset of earlier patterns. Identity accumulates.

### What Changes Between 2024 and 2025/2026

Known life changes (these are the stress test):
- 2024: SAFA still active/collapsing, heavy trading, job search active
- 2025: Base Layer project begins, shifts from job-seeker to builder
- 2026: Base Layer public, outreach, research publication, identity as founder re-emerges

The question: do the AXIOMS (coherence demand, ownership, signal/noise discipline) persist despite these circumstance changes? Do the PREDICTIONS (confirmation gate, rules-execution gap, conviction-sizing mismatch) still fire in new contexts?

If the axioms hold but the context modes shift, that validates the three-layer architecture: anchors are durable, core is contextual, predictions bridge both.

## Implementation

### Step 1: Date Distribution Analysis
```python
# Count conversations by year/quarter
# Identify topic shifts
# Verify sufficient data in each split
```

### Step 2: Isolated 2024 Extraction
```bash
# Create isolated environment
# Import only 2024 conversations
# Run extraction with current pipeline
# Author with H3 prompts
```

### Step 3: 2025/2026 Extraction
```bash
# Same pipeline on remaining conversations
# Keep separate from 2024 model
```

### Step 4: Evaluation
- Twin-2K style: ~$15-20 for N=100
- Pattern matching: mechanical, $0
- Axiom stability: 2 authoring runs already done, comparison is manual
- Fact prediction: requires generating predictions then manual scoring against evidence

### Cost Estimate
- Extraction: ~$2 (2024 subset, Haiku)
- Authoring: ~$0.50 (H3 prompts, Sonnet 4.6)
- Twin-2K evaluation: ~$15-20 (Opus for judging)
- Total: ~$20

## Relationship to Serving Layer

The temporal prediction test directly informs serving layer design:

1. **If axioms are durable**: the serving layer can cache anchors aggressively. No need to re-author frequently.
2. **If predictions decay**: the serving layer needs temporal weighting — recent predictions scored higher than old ones.
3. **If context modes shift**: the serving layer needs to detect context changes and trigger re-authoring of core modes.
4. **If the 2024 model works for 2025/2026**: the identity model is a long-lived artifact, not a session-by-session computation. This changes the serving layer from "compute per request" to "serve cached artifact with periodic refresh."

## Prior Work

- Franklin temporal window experiment (S78): Q3→Q1 (26.4) > Q1→Q3 (20.1). Later predicts earlier better. Small effect, single historical subject.
- Twin-2K V4 (N=100): 71.83% accuracy at 18:1 compression. Baseline that this test should beat or match.
- Temporal processing redesign (S23): classification (event vs state) over time-math. This test validates that framework.

## Open Questions

1. **How to handle topic-specific facts?** 2024 has heavy trading data. 2025/2026 has heavy Base Layer data. Should topic-specific facts be excluded from the prediction test, or included to see if the model correctly generalizes the pattern underneath?
2. **What counts as a "prediction"?** If the 2024 model says "seeks confirmation before committing" and in 2025 they seek confirmation before committing to a different thing — is that a hit?
3. **How to score partial matches?** The axiom might be right but the specific manifestation different.
4. **Should we test on other subjects too?** Any subject with multi-year corpus could be split. Scott Alexander's 100 ACX posts span years.
