# VRI Implementation Spec — Collective Review

## Overview

Variance Reduction Index measures whether the brief reduces stochastic variance in model outputs. A cold model guesses from priors (high variance). A brief-equipped model should converge (low variance). VRI measures how much.

```
VRI = 1 - (Var(C5c) / Var(C1))
```

VRI = 0: no reduction. VRI = 1.0: perfect consistency. Negative: brief increased variance.
Threshold: VRI >= 0.30.

## Prompt Selection (5 prompts)

### User A (default subject)

| VRI ID | Source | Category | Why high C1 variance |
|--------|--------|----------|---------------------|
| V1 | P1 | Trading discipline | Cold oscillates: therapeutic vs coaching vs tough-love |
| V2 | P6 | Existential/philosophical | Cold scatters: imposter syndrome vs motivational vs philosophical |
| V3 | P3 | Relationship/decision | Cold varies: pros/cons vs couples counseling vs "follow your heart" |
| V4 | P10 | Decision/uncertainty | Cold splits: pick a path vs decision matrix vs generic uncertainty advice |
| V5 | P9 | Meta/AI relationship | Cold ranges: reassurance to concern-trolling to philosophical |

### Franklin (public figure)

| VRI ID | Source | Category |
|--------|--------|----------|
| V1 | P1 | Credit/recognition |
| V2 | P3 | Conflict/dispute |
| V3 | P5 | Discovery/sharing |
| V4 | P8 | Persuasion |
| V5 | P10 | Legacy/purpose |

## Protocol

1. **Generate:** 10 responses per prompt x 5 prompts x 2 conditions = 100 responses
2. **Judge:** 100 judge calls (Sonnet at temp=0)
3. **Embed:** 100 embeddings (MiniLM, local, free)
4. **Analyze:** Compute VRI, bootstrap CI, permutation test

### Temperature: 1.0 (not 0.7)

At 0.7 Sonnet is too constrained. 1.0 produces noticeably diverse outputs while remaining coherent. Single temperature — no sensitivity curve (separate study).

### Judge: Sonnet (not Opus)

- 100 calls at Opus = ~$2. Sonnet = ~$0.35.
- At temperature=0, Sonnet is deterministic and stable.
- VRI measures variance (large signal), not nuanced 0.5-point differences.

**MANDATORY stability check:** Judge 3 existing responses 5 times each at temp=0. If composite stdev > 0.3, escalate to Opus.

## Variance Measurement

### Score Variance (Primary)

```python
composite = mean(recognition, calibration, depth, usefulness)
var_score_C1[p] = stdev([composite(r) for r in C1_responses[p]])
var_score_C5c[p] = stdev([composite(r) for r in C5c_responses[p]])
VRI_score[p] = 1 - (var_score_C5c[p] / var_score_C1[p])
```

Guard: If C1 stdev < 0.25, exclude prompt (insufficient baseline variance).

### Content Variance (Secondary)

```python
embeddings = [embed(r) for r in responses[p]]
pairwise_sims = [cosine_sim(e_i, e_j) for all pairs]
dispersion = 1 - mean(pairwise_sims)
VRI_content[p] = 1 - (dispersion_C5c[p] / dispersion_C1[p])
```

Guard: If C1 dispersion < 0.05, exclude.

### Aggregation

```python
# Primary: mean of valid per-prompt VRIs
VRI_aggregate = mean([v for v in VRI_score.values() if not isnan(v)])
```

Report both score-based and content-based. Headline = score-based.

## Statistical Validity

- **Bootstrap CI:** Resample 10 responses per condition 1000x, compute VRI each time. Report 95% CI.
- **Permutation test:** Combine 20 responses (10 C1 + 10 C5c), randomly split 5000x, compute VRI. p-value = fraction with VRI >= observed.
- If CI includes 0, VRI not significant at alpha=0.05.

## Integration

```
python run_validation_study.py --vri [--phase all|stability|generate|judge|analyze]
baselayer vri [--phase all|stability|generate|judge|analyze]
```

Output: `{EVAL_DIR}/vri/`
- `responses/` — 100 response files
- `judge/vri_judge_ratings.json` — 100 ratings
- `embeddings/vri_embeddings.json` — 100 embeddings
- `analysis/vri_results.json` — final VRI computation
- `analysis/vri_report.md` — human-readable

## Cost Estimate

~$1.45 per subject:
- C1 generation (50 calls, Sonnet temp=1.0): ~$0.45
- C5c generation (50 calls, Sonnet temp=1.0): ~$0.60
- Judging (100 calls, Sonnet temp=0): ~$0.35
- Stability check (15 calls): ~$0.05
- Embeddings (local MiniLM): $0.00

## Execution Order

1. Run stability check (~$0.05, 5 min). Fail = stop.
2. Generate C1 responses (50 calls, ~10 min)
3. Generate C5c responses (50 calls, ~10 min)
4. Judge all 100 (100 calls, ~15 min)
5. Compute embeddings (local, ~30 sec)
6. Run analysis (local, ~10 sec)
7. Review per-prompt VRIs; flag low-variance prompts
8. Write report

**Total: ~45 min, ~$1.45**

## Failure Modes

| Mode | Detection | Mitigation |
|------|-----------|------------|
| Judge variance dominates | Stability stdev > 0.3 | Escalate to Opus judge |
| Low C1 variance | Per-prompt C1 stdev < 0.25 | Exclude prompt, report as "strong priors" |
| Temperature too low | Majority C1 responses near-identical | Bump to 1.2 |
| Negative VRI | Brief increases variance | Report honestly; investigate conflicting axioms |
| MiniLM too coarse | Score VRI and content VRI disagree by > 0.3 | Score-based is primary; note limitation |
| Prompt-specific outlier | 1 of 5 prompts dominates | Report per-prompt; compute with/without outlier |

## Collective Verdict

IMPLEMENT. Under $1.50 for a credible variance benchmark. The two-track measurement (score + content) with statistical rigor (bootstrap + permutation) makes this publishable. VRI is the most intuitively compelling metric: "The brief reduces response randomness by X%."
