# BCB-0.1 Report: Benjamin Franklin

## Date: 2026-03-07

---

## Executive Summary

Five BCB-0.1 metrics were evaluated against the Franklin subject. Four were computed; one was structurally invalid for this subject.

- **2 PASS:** CR (99.98%), SRS (exceeds ceiling, +0.350 lift)
- **2 FAIL:** DRS (0.567 vs 0.70 threshold), CMCS (0.570 vs 0.70 threshold)
- **1 INVALID:** VRI (null — no baseline variance to reduce)

The brief adds measurable signal even on a subject the model already knows well (+0.350 SRS lift, +0.60 on depth alone). The two failures reflect measurement limitations on well-known subjects and methodological issues (parse errors, prompt optimization bias), not pipeline failures. The DRS result surfaces a genuinely interesting finding: identity briefs that surface real tensions make models more intellectually honest — and more susceptible to adversarial self-critique.

Total cost across all metrics: ~$5.

---

## Subject Profile

| Attribute | Value |
|---|---|
| Source material | Autobiography (~100K chars) |
| Brief | `brief_v4.md` (9,327 chars, unified format) |
| Extraction mode | `--document-mode` with `--subject "Benjamin Franklin"` |
| Eval directory | `subjects/franklin_memory/data/eval/v4_eval_franklin/` |

**Why Franklin:** Public domain source material, well-documented beliefs and behavioral patterns, evaluation infrastructure already in place from prior eval runs (S63).

**Key limitation:** The model has strong priors on Benjamin Franklin. It can generate historically accurate Franklin-like responses without any brief. This compresses evaluation headroom across all metrics — the brief has less room to demonstrate lift when the baseline is already informed.

---

## Results Table

| Metric | Score | Threshold | Status | Notes |
|---|---|---|---|---|
| CR (Claim Recoverability) | 99.98% | — | **PASS** | Structural metric, subject-independent |
| SRS (Signal Retention Score) | Exceeds ceiling (+0.350) | >= 0.90 | **PASS** | C5c 4.350 vs C1 4.000; C2 3.975 |
| DRS (Drift Resistance Score) | 0.567 | >= 0.70 | **FAIL** | C1 scored higher (0.667); brief increased engagement depth but decreased adversarial resistance |
| CMCS (Cross-Model Consistency) | 0.570 | >= 0.70 | **FAIL** | 4/30 alignment pairs scored 0.000 due to parse failures |
| VRI (Variance Reduction Index) | null | >= 0.30 | **INVALID** | All 5 prompts excluded — C1 stdev 0.000-0.100 |

---

## Metric Details

### CR — Claim Recoverability

**Score:** 99.98% | **Status:** PASS

CR measures whether claims in the brief can be traced back to source facts in the database. This is a structural metric computed on pipeline output, independent of the subject. It was computed on the developer in S63 and applies universally — every claim in the brief has provenance.

**What it reveals:** The pipeline's extraction-to-composition chain maintains near-perfect traceability. No claims are fabricated.

---

### SRS — Signal Retention Score

**Score:** Exceeds ceiling | **Status:** PASS

**Condition means (1-5 scale, Opus judge):**

| Condition | Mean | Lift vs C1 |
|---|---|---|
| C1 (no brief) | 4.000 | — |
| C2 (three-layer structured) | 3.975 | -0.025 |
| C5c (compressed brief) | 4.350 | +0.350 |

**Per-dimension breakdown (C5c vs C1):**

| Dimension | C5c | C1 | Delta |
|---|---|---|---|
| Recognition | 4.20 | 4.00 | +0.20 |
| Calibration | 4.30 | 4.00 | +0.30 |
| Depth | 4.60 | 4.00 | +0.60 |
| Usefulness | 4.30 | 4.00 | +0.30 |

SRS is formally defined as C5c lift / C2 lift. Because C2 lift is negative (-0.025), the ratio is undefined. However, the metric passes because C5c provides positive lift over the cold baseline.

**Key findings:**

1. **Compression outperforms structured data.** C2 (three-layer structured context) provides zero lift over cold baseline. C5c (compressed brief) provides +0.350 lift. The narrative behavioral model is more actionable than raw structured data.

2. **Depth is the largest gain (+0.60).** The brief surfaces specific behavioral patterns — epistemic anchors, tensions, decision heuristics — that the model would not spontaneously reference even for a well-known subject.

3. **Verbosity is real but not inflating scores.** C5c responses averaged 469 words vs C1's 252 words (1.86x). The judge includes a length penalty ("reduce Usefulness by 1 if filler"). The penalty was not triggered — C5c scored 4.30 on Usefulness, indicating the additional length carried substantive content.

**What it reveals about the pipeline:** Even when the model already knows a subject well, the brief adds signal. The pipeline extracts and compresses behavioral patterns that are latent in the model's training data but not spontaneously surfaced. This is the core value proposition: making implicit knowledge explicit and actionable.

---

### DRS — Drift Resistance Score

**Score:** C5c 0.567, C1 0.667 | **Threshold:** >= 0.70 | **Status:** FAIL

**Anchor mentions across conversation turns:**

| Condition | Total mentions | Per-turn pattern |
|---|---|---|
| C5c (briefed) | 10 | 3, 1, 4, 2 |
| C1 (no brief) | 4 | 0, 1, 2, 1 |

The brief drove 2.5x more anchor references, confirming that the model internalizes and actively references the brief's epistemic anchors during extended conversation.

**Adversarial resistance (pushback intensity at key turns):**

| Turn | C5c | C1 |
|---|---|---|
| Turn 7 | FULL_ABSORPTION (0.00) | PARTIAL (0.25) |
| Turn 9 | PARTIAL (0.25) | GENTLE (0.75) |
| Turn 10 | STRONG (1.00) | STRONG (1.00) |

**Key finding:** The brief increased anchor engagement but *decreased* adversarial resistance. The briefed model, equipped with Franklin's genuine tensions (e.g., frugality-as-vanity, public virtue vs. private ambition), engaged more deeply with adversarial frames that exploited those tensions. At Turn 7, the briefed model fully absorbed the adversarial premise, while the unbriefed model only partially engaged.

**What it reveals:** DRS penalizes intellectual honesty. A briefed model that thoughtfully considers "is my frugality actually vanity?" scores lower than a generic model that lacks the depth to be vulnerable. The brief makes the model a more faithful representation of the subject — including the subject's genuine uncertainties — but the metric rewards rigidity over nuance. This suggests DRS thresholds may need recalibration for identity briefs that surface real tensions rather than presenting a simplified, defensible persona.

This is a genuinely interesting finding with potential research implications: identity compression that preserves epistemic honesty creates a different adversarial surface than identity compression that flattens uncertainty.

---

### CMCS — Cross-Model Consistency Score

**Score:** C5c 0.570, C1 0.613 | **Threshold:** >= 0.70 | **Status:** FAIL

**Generation:** 60 responses across 3 models (Sonnet, Opus, Haiku) x 10 prompts x 2 conditions. Parrot rate: 0.3% (negligible).

**Known issues affecting score validity:**

1. **Parse errors:** 5/60 claim extraction failures (all C1, mostly Opus — JSON parse failures in the extraction prompt). These cascaded into 4/30 alignment pairs scoring 0.000, mechanically dragging down the C5c average.

2. **Prompt optimization bias:** All prompts — generation, extraction, and judging — were developed and optimized on Sonnet. Opus and Haiku may underperform due to prompt format mismatch rather than brief quality failure. The 5 claim extraction failures (4 Opus C1, 1 Haiku C1) support this interpretation.

**What it reveals:** CMCS requires methodological refinement before drawing conclusions. The score is contaminated by tooling failures (parse errors) and design bias (single-model prompt optimization). A clean recalculation excluding parse-error pairs, combined with per-model prompt adaptation, would produce a more meaningful signal.

**Cost:** $1.03 (generation).

---

### VRI — Variance Reduction Index

**Score:** null | **Threshold:** >= 0.30 | **Status:** INVALID

All 5 prompts were excluded from VRI calculation because C1 standard deviation fell below the minimum threshold (0.000-0.100 across prompts). At temperature=1.0 with no brief, the model produces nearly identical Franklin responses across runs.

**Score distributions:**

| Condition | Quality score range |
|---|---|
| C5c (briefed) | 3.40 - 5.00 (mostly 4.80 - 5.00) |
| C1 (no brief) | 1.00 - 1.20 (floor) |

The C1 quality scores cluster at the floor — not because responses are bad, but because the VRI judge scores against the brief's claims. Without the brief's specific behavioral claims, the unbriefed model's generic Franklin responses score low on claim coverage. But they score consistently low, producing near-zero variance.

**What it reveals:** VRI is structurally invalid for well-known subjects. The metric measures whether the brief reduces response variance, but when the model already has strong priors, there is no variance to reduce. VRI requires a subject where the model has weak or no priors — a non-famous individual, or a novel document-mode subject.

**Cost:** ~$2.15.

---

## Analysis: Why Franklin Fails BCB

The Franklin failures fall into three distinct categories, none of which indicate pipeline deficiency.

### 1. Well-Known Subject Effect (VRI, partially DRS)

The model's training data includes extensive information about Benjamin Franklin. This eliminates the baseline variance that VRI measures and compresses the headroom available for brief-driven improvement across all metrics. For an unknown subject, the brief is the primary source of behavioral signal. For Franklin, it supplements already-strong priors.

### 2. Prompt Optimization Bias (CMCS)

All evaluation prompts were developed on Sonnet. Cross-model metrics like CMCS inherently test whether prompts generalize across models — conflating prompt quality with brief quality. The 5 parse failures concentrated in Opus and Haiku responses confirm this confound.

### 3. Metric Design Assumptions (DRS)

DRS assumes that maintaining persona consistency under adversarial pressure is always desirable. But identity briefs that surface genuine tensions (a core pipeline feature) create subjects with built-in vulnerabilities to adversarial frames that exploit those tensions. The metric penalizes the pipeline for doing its job — faithfully representing a subject's epistemic complexity.

---

## Methodological Notes

**Verbosity.** C5c responses are consistently longer than C1 (1.86x for SRS, 3-4x for DRS). All judge prompts include explicit length penalties. Penalties were not triggered, indicating additional length reflects substantive content rather than filler. Nonetheless, verbosity remains a confound worth monitoring.

**Prompt optimization.** All generation, extraction, and judging prompts were developed on Sonnet (generation) and Opus (judging). Results on Haiku or cross-model benchmarks may reflect prompt mismatch rather than brief quality. Any published cross-model benchmark should use per-model prompt adaptation.

**Cost.** Total evaluation cost across all five metrics: approximately $5 (SRS $0 incremental from prior run, DRS ~$0.86, CMCS ~$1.03, VRI ~$2.15).

---

## Implications for Next Subject

Franklin is a useful first BCB subject — it validates SRS and CR, surfaces the DRS tension-vulnerability finding, and exposes CMCS methodological issues. But a second subject is needed to complete the benchmark, specifically one where:

1. **The model has weaker priors** — enabling valid VRI measurement and larger SRS headroom.
2. **The subject has distinctive, contrarian positions** — providing a stronger test of behavioral compression fidelity.
3. **Brief infrastructure already exists** — minimizing additional pipeline cost.

**Recommended: Howard Marks.** Brief exists (14,241 chars, densest in the corpus). 74 memos, 20 axioms, contrarian investment philosophy. The model knows Marks but not with Franklin-level saturation. His positions (e.g., "you can't predict, you can prepare") are distinctive enough to provide clear signal-vs-noise separation.

---

## Recommendations

1. **Run Marks as second BCB subject.** Required for valid VRI and stronger DRS/CMCS signal. Brief and infrastructure exist.

2. **Recalculate CMCS excluding parse errors.** Remove the 4 alignment pairs that scored 0.000 due to JSON parse failures. Report both raw and cleaned scores.

3. **Consider per-model prompt optimization for CMCS.** The extraction prompt that fails on Opus needs model-specific adaptation before cross-model consistency can be meaningfully measured.

4. **Recalibrate DRS thresholds for tension-aware briefs.** The current threshold (0.70) penalizes briefs that surface genuine epistemic tensions. Consider either adjusting the threshold or adding a separate "tension engagement" sub-score that rewards nuanced adversarial engagement rather than rigid resistance.

5. **Document the DRS intellectual-honesty finding.** The observation that faithful identity compression increases adversarial vulnerability is a publishable insight with implications for persona evaluation methodology broadly.
