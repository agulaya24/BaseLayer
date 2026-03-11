# D-079 Rubric Calibration Report

## Issue Discovered
During Round 7 scoring (C28-C31), Buffett briefs that included faithfully paraphrased FP warnings were scored as "fabricated" by the reviewer. The original rubric said "ANY fabricated false positive warning = max 3" for P3, and "Fabricated FP warnings = 0" for E1. The reviewer interpreted paraphrased-but-sourced FP warnings as fabricated.

## Evidence
Buffett's PREDICTIONS layer contains explicit FP warnings for all 8 predictions (P1-P8). Example:
- Source P1: "Not every mention of future planning triggers this pattern—only when he's actively resisting short-term thinking pressure"
- C31 brief: "Future planning mentions don't always trigger long-horizon reframing [P1]"
- This is a faithful paraphrase with correct citation — NOT fabrication

## Impact on Scores (Before → After rubric fix)

| Condition | Buffett Before | Buffett After | Delta |
|---|---|---|---|
| C28 (no FPs included) | 86 | 83 | -3 |
| C29 (faithful FPs) | 68 | 84 | +16 |
| C30 (no FPs included) | 82 | 74 | -8 |
| C31 (faithful FPs) | 68 | 85 | +17 |

C28 and C30 dropped slightly because the fixed rubric correctly penalizes omitting FP warnings (score 4-5) vs the old rubric which gave full marks (10) for omission.

## Rubric Fix
Changed P3 (Faithfulness) and E1 (FP Grounding) to use provenance-based evaluation:
- **Faithful paraphrase with citation** → 8-10 (traces to source)
- **No traceable source** → 0-3 (fabricated)
- **FP warnings omitted entirely** → 4-5 (missed opportunity)

The test is whether the citation chain is valid, not whether the text is verbatim.

## Corrected Final Results

| Condition | Franklin | Buffett | Aarik | Average |
|---|---|---|---|---|
| C28 (cannot predict + temporal) | 88 | 83 | 82 | 84.3 |
| C29 (relational + agency) | 72 | 84 | 84 | 80.0 |
| C30 (full synthesis) | 83 | 74 | 88 | 81.7 |
| C31 (C28 + format freedom) | 83 | 85 | 83 | 83.7 |

## Conclusion
C28 and C31 are statistically tied (84.3 vs 83.7). The original 7-point gap was an artifact of rubric miscalibration.

Remaining legitimate failures:
- C29 Franklin (E1=0): Brief genuinely omitted all FP warnings
- C30 Buffett (E1=0): Brief genuinely omitted all FP warnings

The relational context (C29) and full synthesis (C30) prompts sometimes crowd out FP warnings — these are real prompt-quality issues, not rubric artifacts.

## Decision: D-080 — Production Compose Prompt Selection
Status: PENDING Collective review selection. C28 and C31 are the top candidates.

Key tradeoff:
- C28: More consistent across subjects (lower variance). Structured rubric keeps FP faithful.
- C31: Higher ceiling on individual subjects (Buffett 85, Franklin 83) but relies on model choosing good format.

## Future Work (TODO)
- Collective selects winner between C28 and C31
- Recompose all subjects with winning prompt
- Push updated briefs to website
- Consider rubric weight ablation (is 3:3:2:1 optimal?)
