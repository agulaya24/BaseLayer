# D-080: V5 Compose Prompt Selection

**Decision:** V5 (C31 + citation stripping) replaces V4 as production compose prompt.
**Date:** 2026-03-10
**Status:** DECIDED
**Confidence:** High (unanimous Collective, 3/3 subjects)

---

## Summary

D-079 ran a 31-condition prompt ablation study to identify what makes briefs better. A new 4-primitives rubric was developed: Provenance (30), Behavioral Change (30), Epistemic Calibration (20), Signal Density (10) = /90. V4 scored 42/90 avg. V5 (C31) scored 83.7/90 avg — a 99% improvement at 56% smaller size.

---

## V4 vs V5

| Property | V4 (S80 production) | V5 (C31) |
|---|---|---|
| Architecture | Single Opus pass, detailed instructions | Rubric-aware, format-free, temporal-aware |
| Key features | FP guards + tension-action pairs woven into prose | Rubric-as-prompt + CANNOT PREDICT section + citation generation |
| Avg score (/90) | 42.0 | 83.7 |
| Avg size (chars) | 9,258 | 4,038 |
| Signal per char | 0.0045 | 0.0207 |
| Subjects composed | 14 | 12 |

---

## Scoring Comparison

### V4 Production (corrected rubric /90)

| Subject | P (/30) | B (/30) | E (/20) | S (/10) | Total |
|---------|---------|---------|---------|---------|-------|
| Franklin | 18 | 16 | 6 | 4 | 44 |
| Buffett | 16 | 15 | 6 | 4 | 41 |
| Aarik | 16 | 15 | 6 | 4 | 41 |
| **Avg** | **16.7** | **15.3** | **6.0** | **4.0** | **42.0** |

### V5 C31 (corrected rubric /90)

| Subject | P (/30) | B (/30) | E (/20) | S (/10) | Total |
|---------|---------|---------|---------|---------|-------|
| Franklin | 28 | 27 | 19 | 9 | 83 |
| Buffett | 29 | 28 | 19 | 9 | 85 |
| Aarik | 28 | 27 | 19 | 9 | 83 |
| **Avg** | **28.3** | **27.3** | **19.0** | **9.0** | **83.7** |

### Delta

| Primitive | V4 Avg | V5 Avg | Delta | % Gain |
|-----------|--------|--------|-------|--------|
| Provenance (/30) | 16.7 | 28.3 | +11.6 | +69% |
| Behavioral Change (/30) | 15.3 | 27.3 | +12.0 | +78% |
| Epistemic Calibration (/20) | 6.0 | 19.0 | +13.0 | +217% |
| Signal Density (/10) | 4.0 | 9.0 | +5.0 | +125% |
| **Total (/90)** | **42.0** | **83.7** | **+41.7** | **+99%** |

Epistemic calibration saw the largest relative gain (+217%). V4 had no mechanism to express uncertainty or mark unpredictable domains. V5's required CANNOT PREDICT section directly addresses this.

---

## V5 Innovations

### 1. Citation Stripping for Serve

V5 generates inline citations ([A1], [P3], etc.) during compose. The model uses these to trace every claim back to authored layer content. A regex pass then strips citations for the clean served version.

Two output files per subject:
- `brief_v5.md` — cited version (human audit, provenance verification)
- `brief_v5_clean.md` — clean version (served to LLMs via MCP)

This solves a fundamental tension: provenance requires citations, but served briefs should be clean prose.

### 2. Format Freedom

V4 prescribed structure (sections, ordering, prose style). V5 says "complete creative freedom on format." Result: the model adapts structure to each subject's behavioral signature.

- Franklin: mode detection patterns
- Buffett: decision triggers
- Douglass: trigger-response patterns

Structure becomes signal, not template.

### 3. Rubric-as-Prompt

Telling the model exactly what it's scored on makes it optimize for those primitives directly. The 4 primitives (provenance, behavioral change, epistemic calibration, signal density) become self-enforcing constraints rather than post-hoc evaluation criteria.

---

## Rubric Calibration Fix (D-079)

During scoring, discovered the reviewer was penalizing faithful FP paraphrases as "fabricated" (P3=3, E1=0) while giving full marks to briefs that omitted FP warnings entirely. This inverted the intended scoring.

**Fix:** Provenance-based evaluation:
- Citation traces to real source content (even paraphrased): score 8-10
- No traceable source: score 0-3
- Total omission despite source containing FP warnings: score 4-5

This correction added ~10 points across all C28/C31 scores. V4 scores were also re-evaluated under the corrected rubric for fair comparison.

---

## Collective Decision

Opus evaluated all 6 briefs (C28 x 3 subjects + C31 x 3 subjects). C31 was chosen unanimously with high confidence across all subjects:

| Subject | Winner | Confidence |
|---------|--------|------------|
| Franklin | C31 | High |
| Buffett | C31 | High |
| Aarik | C31 | High |

C31 = C28 (rubric awareness + temporal awareness) + format freedom from C27.

---

## Remaining Gaps

1. **Behavioral differentiation not tested.** All briefs scored individually. Need same-prompt-different-brief test to verify briefs produce meaningfully different LLM behavior across subjects.

2. **Twin-2K V5 not run.** V4 scored 71.83% on Twin-2K (N=100, p=0.008). V5 needs benchmark validation. Hypothesis: smaller + denser should maintain or improve accuracy.

3. **Local LLM validation.** All scoring done via Opus. Need Qwen local validation to confirm scores are not model-specific.

---

## Files Changed

| File | Change |
|---|---|
| `config.py` | `UNIFIED_BRIEF_FILE` -> `brief_v5_clean.md`, added `UNIFIED_BRIEF_CITED_FILE` |
| `agent_pipeline.py` | Compose saves both cited and clean versions |
| `mcp_server.py` | Serves clean version, falls back to cited |
| `cli.py`, `ui.py` | Updated brief path references |
| `generate_website_data.py` | Prefers v5 files |
| All 12 subjects | `brief_v5.md` (cited) + `brief_v5_clean.md` (clean) |
| Website data | All 8 data files + `examples.ts` updated with V5 content |
| Hero slides | Updated with V5-style showcase content |

---

## Decision Record

**D-080: V5 (C31 + citation strip) is the production compose prompt.**

Rationale: 99% score improvement, 56% size reduction, 2x signal density, unanimous Collective selection. Citation stripping preserves provenance for audit while serving clean prose. Format freedom produces subject-adapted structure. Rubric-as-prompt makes quality self-enforcing.

Supersedes: V4 compose prompt (D-070, S80).
Depends on: D-079 (31-condition ablation), D-078 (template contamination fix).
Blocked by: Nothing. All subjects recomposed.
Next validation: Twin-2K V5 benchmark run.
