# Twin-2K-500 External Benchmark Test Plan

**Date:** 2026-03-06
**Status:** PLANNED (post-launch)
**Dataset:** Twin-2K-500 (Toubia et al., Marketing Science 2025)
**Source:** https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500
**License:** CC BY 4.0

---

## Hypothesis

A ~3,500-token Base Layer behavioral brief, extracted from structured persona data, can predict held-out behavioral responses as well as or better than a 15K-char persona summary — and approach the accuracy of a 130K-char full persona dump at 37x compression.

## Published Baselines

| Condition | Accuracy | Token Count |
|---|---|---|
| Random guessing | 59.17% | 0 |
| Persona summary (GPT-4.1-mini) | 68.02% | ~15K chars |
| Fine-tuned (500 samples, GPT-4.1-mini) | 69.61% | N/A (weights) |
| Full persona text (GPT-4.1-mini) | 71.72% | ~130K chars |
| Full persona JSON (GPT-4.1) | 71.05% | ~165K chars |
| Human test-retest ceiling | 81.72% | N/A |

## Success Criteria

| Outcome | What it proves |
|---|---|
| Brief > 68.02% (summary) | Behavioral compression outperforms naive summarization |
| Brief > 69.61% (fine-tuned) | Compression outperforms fine-tuning — no training needed |
| Brief approaches 71.72% (full dump) | 37x compression with minimal accuracy loss |
| Brief > 71.72% (full dump) | Compression IMPROVES signal by filtering noise — strongest result |

**Minimum success:** Beat 68.02% (persona summary baseline).
**Target:** Match or exceed 71.72% (full persona dump).

---

## Phase 0: Data Inspection (30 min, $0)

**Gate check before committing resources.**

1. Download dataset from HuggingFace
2. Inspect 5 participants' `persona_text` and `persona_summary` fields
3. Assess whether the text is rich enough for Base Layer's 47 predicates to extract behavioral signal
4. If the data is purely numeric Likert scales with no behavioral texture, STOP — the pipeline isn't designed for this input format

**Decision point:** Proceed to Phase 1 only if extraction looks viable on manual inspection.

---

## Phase 1: Extraction Viability (2-3 hours, ~$1)

**Test whether the pipeline produces meaningful output on survey data.**

1. Select 3 participants (random)
2. Export each participant's `persona_text` (~130K chars) to a text file
3. Run Base Layer extraction: `baselayer import` + `baselayer extract --document-mode`
4. Inspect extracted facts:
   - Do the 47 predicates find behavioral signal?
   - Are facts meaningful (e.g., "values delayed gratification") or trivial (e.g., "lives in Northeast")?
   - What's the identity-tier yield after classification + tiering?
5. If extraction produces <20 identity-tier facts per participant, consider Option B (use `persona_summary` as input instead)

**Decision point:** Proceed to Phase 2 only if extraction produces meaningful behavioral facts.

**Fallback — Option B:** If `persona_text` is too structured, try `persona_summary` (~15K chars, more narrative). This is a weaker test (same input as their summary baseline) but still tests whether brief FORMAT improves prediction.

**Fallback — Option C:** If neither works through the pipeline, use a single Opus call to compress persona data directly into brief format. Tests brief structure hypothesis only, not the full pipeline. Weakest proof but cheapest.

---

## Phase 2: Brief Generation (1 hour, ~$2)

**Generate briefs for the test cohort.**

1. Select 20 participants (random, stratified by age/gender if demographics available)
2. For each participant:
   - Run full pipeline: import → extract → embed → score → classify → tier → author → compose
   - Use `--document-mode` + `--subject "Participant [ID]"`
   - Store brief as `brief_v4.md`
3. Record per-participant stats: fact count, identity-tier count, brief token count
4. Spot-check 3 briefs for quality — do they capture behavioral tendencies, not just demographics?

**Expected output:** 20 briefs, ~3,500 tokens each.

---

## Phase 3: Prediction (2 hours, ~$35)

**Predict held-out wave 4 responses using the brief.**

### 3a. Prepare prediction harness

New script: `scripts/twin2k_predict.py`

```
For each participant:
    For each of 88 holdout questions:
        Construct prompt:
            System: "You are answering survey questions as the person
                     described in the behavioral brief below. Answer
                     exactly as this person would, based on their
                     documented reasoning patterns and behavioral
                     tendencies. Return ONLY the answer."
            User: [behavioral brief as document block]
                  [question text + response options]
        Call API (Sonnet — matches their GPT-4.1-mini tier)
        Parse response → extract answer
        Store prediction
```

### 3b. Run predictions

- 20 participants x 88 questions = 1,760 API calls
- Model: Sonnet (comparable capability tier to GPT-4.1-mini)
- Estimated cost: ~$35 (short prompts, brief as document block)
- Use Batch API to reduce cost 50% → ~$17.50

### 3c. Also run control conditions

For fair comparison, run two additional conditions on the same 20 participants:

| Condition | Input | Purpose |
|---|---|---|
| C1: No context | Question only | Replicates their random baseline |
| C2: Base Layer brief | Brief (~3,500 tokens) + question | Our test condition |
| C3: Full persona dump | Full persona_text (~130K chars) + question | Replicates their best baseline |

C1 and C3 let us verify our results are comparable to their published numbers before comparing C2.

---

## Phase 4: Scoring (1 hour, $0)

**Score predictions against ground truth.**

New script: `scripts/twin2k_score.py`

### Scoring rules (from their paper):

- **Categorical questions:** Binary match (1 if correct, 0 if not)
- **Likert/numeric questions:** 1 - |predicted - actual| / range
- **Aggregate:** Mean accuracy across all questions per participant, then mean across participants

### Output:

```
TWIN-2K-500 RESULTS
====================
                      Accuracy    vs Summary    vs Full Dump
C1 (no context):      XX.XX%
C2 (Base Layer):      XX.XX%      +X.XX%        -X.XX%
C3 (full dump):       XX.XX%

Published baselines:
  Summary:            68.02%
  Full dump:          71.72%
  Human ceiling:      81.72%

Compression ratio: 37x (3,500 tokens vs 130,000 chars)
```

### Per-category breakdown:

Score separately for each question category:
- Demographics (14 questions) — expect low lift (brief doesn't encode demographics)
- Personality inventories (279 questions, but only holdout subset)
- Cognitive ability (85 questions)
- Economic preferences (34 questions) — expect highest lift
- Behavioral economics experiments (16 tasks) — expect highest lift

The behavioral economics experiments are the most relevant — framing effects, sunk cost, conjunction fallacy. These are WHERE behavioral compression should shine because they test reasoning patterns, not factual recall.

---

## Phase 5: Analysis (1 hour, $0)

### 5a. Category analysis

Which question types benefit most from the brief? Hypothesis: behavioral economics experiments show the largest gap between brief and no-context, while demographics show the smallest.

### 5b. Compression efficiency curve

Plot accuracy vs. input tokens:
- No context (0 tokens): XX%
- Brief (~3,500 tokens): XX%
- Persona summary (~15K chars): 68.02% (published)
- Full dump (~130K chars): XX%

If brief is on or above the curve, compression adds signal per token.

### 5c. Failure analysis

For cases where C2 (brief) gets wrong but C3 (full dump) gets right:
- Is the answer derivable from behavioral patterns (brief should have helped)?
- Or is it a factual recall question (brief correctly ignores demographics)?

### 5d. Brief quality correlation

Does brief quality (fact count, identity-tier ratio, brief length) correlate with prediction accuracy? If so, which pipeline metrics predict downstream performance?

---

## Cost Summary

| Phase | Time | Cost |
|---|---|---|
| Phase 0: Data inspection | 30 min | $0 |
| Phase 1: Extraction viability | 2-3 hours | ~$1 |
| Phase 2: Brief generation | 1 hour | ~$2 |
| Phase 3: Prediction (with Batch API) | 2 hours | ~$17.50 |
| Phase 4: Scoring | 1 hour | $0 |
| Phase 5: Analysis | 1 hour | $0 |
| **Total** | **~8 hours** | **~$20.50** |

Scale to 50 participants for stronger statistical power: ~$45 total.

---

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Survey Q&A too structured for extraction | Medium | Phase 1 gate check. Fallback to persona_summary or Option C |
| Brief underperforms summary baseline | Low-Medium | Analyze per-category — may win on behavioral tasks, lose on factual recall |
| Model differences confound comparison | Low | Run C3 (full dump) ourselves to calibrate against their published number |
| 20 participants insufficient for significance | Low | Bootstrap confidence intervals. Scale to 50 if results are borderline |
| Parsing survey response format is complex | Medium | Phase 0 inspection. Build parser before committing |

---

## What This Proves (If Successful)

1. **Compression works on external data.** Not just our pipeline's own subjects — real humans from an independent study.
2. **Brief format adds signal.** Same information, better structure → better predictions.
3. **37x compression with no accuracy loss.** 3,500 tokens vs. 130,000 chars.
4. **Published, reproducible, credible.** Marketing Science venue, Columbia dataset, public data. The result would be citable.

## What This Does NOT Prove

- Does not prove the pipeline works on natural language (this is survey data)
- Does not prove the brief captures reasoning patterns (survey prediction ≠ reasoning evaluation)
- Does not replace BCB or ADRB (those test different claims)

---

## Decision Gate

**Run Phase 0 (data inspection) first.** The entire plan depends on whether the input data is viable for Base Layer's extraction pipeline. 30 minutes, zero cost, high information value.

If Phase 0 passes → commit to full run.
If Phase 0 fails → file as "input format incompatible" and move on. No sunk cost.
