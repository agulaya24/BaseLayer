# CMCS Implementation Spec — Collective Review

## Overview

Cross-Model Consistency Score measures whether the same brief produces structurally similar behavioral predictions across different foundation models. If models converge with the brief but diverge without it, the signal is in the brief.

```
CMCS = mean(structural_alignment across all prompts)
```

Threshold: CMCS >= 0.70. Key metric: CMCS_lift = CMCS(C5c) - CMCS(C1).

## Architecture: Two-Phase Claim Extraction + Alignment

### Phase 1: Generate Responses
4 models x 10 prompts x 2 conditions (C1, C5c) = 80 responses.

**Models:**
```python
CMCS_MODELS = {
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
    "gpt4o": "gpt-4o",  # optional, requires OPENAI_API_KEY
}
```

GPT-4o is optional — graceful degradation if no OpenAI key. `--cmcs-models` flag to override.

### Phase 2: Extract Structured Claims
For each response, extract atomic behavioral claims using Sonnet. 80 extraction calls.

**Claim Extraction Prompt:**
```
Extract every distinct behavioral claim as a short statement (1 sentence max):
- Specific behavioral predictions ("this person would X when Y")
- Value assertions ("this person prioritizes X over Y")
- Pattern identifications ("this person tends to X")
- Advice based on inferred traits ("you should X because you Y")

Exclude: Generic advice, restatements, filler, advice anyone would give anyone.
Normalize to third person. Each claim must be atomic.
Return JSON array of claim strings.
```

### Phase 3: Pairwise Alignment Scoring
For each prompt, C(4,2) = 6 pairwise comparisons x 2 conditions = 120 alignment calls (Sonnet).

**Alignment Score Formula:**
```
alignment_score = matched_count / min(len(claims_a), len(claims_b))
```

Uses shorter response as reference set. Prevents penalizing models that say more.

**Alignment Judge:** Sonnet reads both claim sets, identifies semantic matches (same pattern in different words = match), reports matched/unmatched with reasoning.

### Phase 4: Aggregation
```python
prompt_alignment(P, C) = mean(alignment_score for all pairs at P, C)
CMCS(C5c) = mean(prompt_alignment(P, C5c) for P in P1..P10)
CMCS(C1) = mean(prompt_alignment(P, C1) for P in P1..P10)
CMCS_lift = CMCS(C5c) - CMCS(C1)
```

**Bootstrap 95% CI:** Resample prompts 1000x, compute CMCS_lift. If lower bound > 0, significant.

**Parrot Check (CRITICAL):** Count claims containing 5+ word sequences verbatim from brief text. `parrot_rate = verbatim_claims / total_claims`. If > 0.50, flag metric as potentially inflated.

## Integration

```
python run_validation_study.py --cmcs [--cmcs-models sonnet opus haiku gpt4o]
```

Output: `{EVAL_DIR}/cmcs/` with:
- `responses.json` — 80 generated responses
- `claims.json` — 80 extracted claim sets
- `alignments.json` — 120 pairwise alignment scores
- `cmcs_report.json` — final aggregated results

## Cost Estimate

~$7.80 per subject:
- Generate: ~$5.80 (mixed models)
- Extract claims: ~$0.80 (Sonnet)
- Align pairs: ~$1.20 (Sonnet)

## Key Design Decisions

1. **Two-phase over direct comparison:** Extract claims first, then align. Produces auditable intermediates.
2. **min(len_a, len_b) denominator:** Prevents penalizing verbose models.
3. **Parrot rate mandatory:** CMCS without parrot check is misleading.
4. **GPT-4o optional:** Proves cross-family portability but adds operational complexity.
5. **Temperature 0:** CMCS measures between-model consistency, not within-model variance (that's VRI).

## Failure Modes

| Mode | Probability | Mitigation |
|------|-------------|------------|
| Claim extraction noise | HIGH | Alignment judge normalizes language; report extraction examples |
| Brief parroting inflates CMCS | HIGH | Parrot rate check; flag if > 50% |
| Public figure C1 baseline too high | MEDIUM | Most meaningful for private subjects; report both |
| Haiku too terse (few claims) | MEDIUM | Min 3 claims threshold; exclude low-claim responses |
| Ceiling effect | LOW | Include domain-gap prompts where brief provides less guidance |

## One-liner for HN Post

"Cold models disagree about who you are. Brief-equipped models converge."
