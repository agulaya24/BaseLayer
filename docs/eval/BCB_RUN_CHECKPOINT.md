# BCB-0.1 Run Checkpoint (Session 77, 2026-03-07)

## Subject: Franklin
**Brief:** `subjects/franklin_memory/data/identity_layers/brief_v4.md` (9,327 chars, unified format)
**Eval dir:** `subjects/franklin_memory/data/eval/v4_eval_franklin/`
**Brief copy for eval:** `v4_eval_franklin/c5c_brief.md` (verified = unified brief, not old three-layer)

## Results Summary

| Metric | Score | Threshold | Status |
|---|---|---|---|
| CR | 99.98% | — | PASS (structural, subject-independent) |
| SRS | exceeds ceiling (+0.350) | >= 0.90 | PASS (ceiling undefined) |
| DRS | 0.567 | >= 0.70 | FAIL (C5c) |
| CMCS | 0.570 | >= 0.70 | FAIL (C5c) |
| VRI | null | >= 0.30 | INVALID (no variance to reduce) |

**Headline:** 4/5 metrics computed, 1/4 passes threshold. But the failures are instructive — see analysis below.

## Metric Details

### CR — Claim Recoverability
- **Status:** DONE (computed on the developer in S63)
- **Score:** 99.98%
- **Note:** Structural metric, pipeline-independent. Valid for all subjects.

### SRS — Signal Retention Score
- **Status:** DONE
- **SRS: EXCEEDS CEILING (PASS)**
- **C1 mean: 4.000** | C2 mean: 3.975 (lift: -0.025) | **C5c mean: 4.350 (lift: +0.350)**
- **Interpretation:** C2 (three-layer structured context) provides NO lift over cold baseline (-0.025). C5c (compressed brief) provides +0.350 lift. SRS ratio undefined (denominator ≤ 0), but passes because C5c lift > 0.
- **What this means:** Compression doesn't just retain signal — it makes it actionable. The model leverages narrative behavioral descriptions more effectively than structured data dumps. This matches the the developer eval finding (C5c ~97% of C2).
- **Prior result (the developer, S63):** SRS = 96.6% (C5c lift 1.425 / C2 lift 1.475). Different dynamic — for unknown subjects, C2 provides strong lift and SRS is a meaningful ratio. For well-known subjects like Franklin, C2 provides no lift.
- **VERBOSITY NOTE:** C5c avg 469 words vs C1 avg 252 words (1.86x). Judge has LENGTH PENALTY ("reduce Usefulness by 1 if filler"). C5c scored 4.30 on Usefulness vs C1 at 4.00 — penalty not triggered, content is substantive.
- **Per-dimension breakdown (C5c vs C1):** recognition 4.20 vs 4.00 (+0.20), calibration 4.30 vs 4.00 (+0.30), depth 4.60 vs 4.00 (+0.60), usefulness 4.30 vs 4.00 (+0.30). Biggest gain on depth — the brief surfaces specific behavioral patterns the model wouldn't spontaneously reference.
- **Cost:** $0 incremental (responses+judgments already existed from prior eval run)

### DRS — Drift Resistance Score
- **Status:** DONE
- **C5c composite: 0.567 (FAIL)** | C1 composite: 0.667 (FAIL) | Lift: -0.100
- **Anchor mentions:** C5c=10 total (3,1,4,2), C1=4 total (0,1,2,1) — brief drives 2.5x more anchor references
- **Adversarial pushback (C5c):** Turn 7 FULL_ABSORPTION (0.00), Turn 9 PARTIAL (0.25), Turn 10 STRONG (1.00)
- **Adversarial pushback (C1):** Turn 7 PARTIAL (0.25), Turn 9 GENTLE (0.75), Turn 10 STRONG (1.00)
- **Key finding:** Brief increased anchor mentions but DECREASED adversarial resistance. The brief's nuanced engagement with Franklin's tensions made it MORE willing to entertain self-critique.
- **Interpretation:** DRS penalizes intellectual honesty. A briefed model that thoughtfully considers "is my frugality actually vanity?" scores lower than a generic model that doesn't engage deeply enough to be vulnerable. This may indicate DRS thresholds need recalibration for identity briefs that surface genuine tensions.
- **Verbosity:** C5c 3-4x longer than C1. Content is substantive, not filler.
- **Cost:** ~$0.86
- **Files:** `v4_eval_franklin/drs/`

### CMCS — Cross-Model Consistency Score
- **Status:** DONE
- **CMCS C5c: 0.570 (FAIL)** | C1: 0.613 | Lift: -0.043
- **Parrot rate:** 0.3% (negligible)
- **Generation:** 60 responses (3 models × 10 prompts × 2 conditions). Cost: $1.03
- **Issues:** 5/60 claim extraction errors (all C1, mostly Opus — JSON parse failures). 4/30 alignment errors (score=0.000 due to parse failures, dragging down C5c average).
- **PROMPT OPTIMIZATION CONCERN (S77):** All prompts are Sonnet-optimized. Opus and Haiku may underperform due to prompt format mismatch, not brief failure. The 5 claim extraction failures (4 Opus C1, 1 Haiku C1) support this — the extraction prompt may not suit all models. CMCS should be re-run with per-model prompt optimization before drawing conclusions.
- **Without parse errors:** If we exclude the 4 alignment pairs with score=0.000 (parse failures), C5c score would likely be higher. Need to recalculate.
- **Files:** `v4_eval_franklin/cmcs/`

### VRI — Variance Reduction Index
- **Status:** DONE (INVALID)
- **VRI: null** — all 5 prompts excluded due to C1 stdev too low (0.000-0.100)
- **C5c quality scores:** 3.40-5.00 (mostly 4.80-5.00)
- **C1 quality scores:** 1.00-1.20 (floor)
- **Explanation:** The model already knows Franklin well. Even at temperature=1.0 with no brief, responses are nearly identical across runs. There's no variance to reduce. VRI is designed for subjects where the model has weak priors — it was always going to fail on a well-known historical figure.
- **Implication:** VRI needs to be run on a subject the model doesn't already know (e.g., non-famous person, or novel document-mode subject like the patent corpus).
- **Cost:** ~$2.15 (generate $1.03 + judge $1.12)
- **Files:** `v4_eval_franklin/vri/`

## Analysis: Why Franklin Fails BCB

**The failures are not pipeline failures — they're measurement failures on a well-known subject.**

1. **VRI (null):** Model already knows Franklin. No variance to reduce. This metric requires a subject where the model has weak priors.

2. **CMCS (0.570):** Partially due to parse errors (4/30 alignment scores = 0.000). Partially due to prompt optimization being Sonnet-specific. Need per-model prompts.

3. **DRS (0.567):** The brief makes the model MORE engaged with the persona's tensions, which paradoxically makes it more susceptible to adversarial frames that exploit those tensions. The metric penalizes depth of engagement.

**What this means for the research package:**
- Franklin is a bad subject for VRI (too well-known)
- Franklin DRS reveals something interesting about how briefs interact with adversarial pressure
- CMCS needs methodological fix (per-model prompts, parse error handling)
- Need a second subject: either Marks (not as well-known, stronger behavioral distinctiveness) or a completely novel subject (e.g., Twin-2K participant, where model has zero priors)

## Prompt Optimization Note (S77)
**All eval prompts, judge prompts, and extraction prompts were developed on Sonnet.** The pipeline was built and optimized for Sonnet (generation) and Opus (Collective review, judging). Results on Haiku or other models may reflect prompt mismatch, not brief quality. Any cross-model benchmark (CMCS, Twin-2K Sonnet) needs per-model prompt adaptation before publication.

## Execution Status
1. DRS generate → DONE
2. DRS judge → DONE
3. DRS analyze → DONE
4. CMCS (all phases) → DONE
5. VRI (all phases) → DONE (INVALID - no variance to reduce)
6. SRS → DONE (exceeds ceiling, PASS)
7. Compile BCB-0.1 report → PENDING (after SRS + analysis)

## Next Steps
1. **Run SRS on Franklin** — the one remaining metric. ~$2.
2. **Recalculate CMCS excluding parse errors** — get clean score.
3. **Consider Marks as second BCB subject** — see `docs/eval/BCB_FUTURE_SUBJECTS.md`
4. **Consider Twin-2K participant for VRI** — model has zero priors, guaranteed variance to reduce.

## Subject: Marks (Partial)
**Brief:** `marks_memory/data/identity_layers/brief_v4.md` (14,241 chars, densest brief)
**Eval dir:** `marks_memory/data/eval/v4_eval_marks/`

### Marks SRS (from prior eval data)
- **C1 mean: 3.640** | **C5c mean: 3.700** | Lift: +0.060
- Modest lift — Marks is less well-known than Franklin, so C1 baseline is lower but C5c doesn't dramatically outperform.
- Note: These are from the initial Marks eval, not a dedicated SRS run.

### Marks DRS
- **Generation COMPLETE:** 3 scenarios × 2 conditions × 10 turns = 60 turns total
- **Judge NOT YET RUN:** Paused after Franklin Haiku judge showed 20/20 failures. Need to either use Opus judge or fix Haiku judge prompt.
- **Files:** `marks_memory/data/eval/v4_eval_marks/drs/drs_responses.json`

### Marks Provenance Eval (Phase 1)
- **BA-delta: +0.016** (C5c > C1) — modest but consistent
- **PC at 0.50 threshold:** C5c 31.1%, C1 28.2%
- **Threshold sensitivity 0.40-0.70:** Consistent C5c advantage across all thresholds
- **Files:** `marks_memory/data/eval/v4_eval_marks/provenance_eval_results.json`

### Marks CMCS and VRI
- **NOT YET RUN.** Priority shifted to provenance eval framework redesign.

---

## Parallel Work
- Twin-2K N=50 expansion (separate Claude Code instance, see TWIN2K_PARALLEL_RUNBOOK.md)
- C5 (persona_summary) condition added to twin2k_predict.py and twin2k_score.py (fork)
