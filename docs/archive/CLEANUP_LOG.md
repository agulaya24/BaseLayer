# Docs Folder Cleanup Log
**Date:** 2026-03-10
**Session:** 85
**Status:** PLAN READY — requires Bash access to execute moves

---

## Summary

Audited 100+ .md files across `docs/`. Categorized every file. Identified 30 files to archive across 6 source locations. No files deleted. Core docs untouched.

---

## Moves to Execute

### 1. S81 Code Review → `docs/archive/s81_code_review/`
These are S81 Sonnet code review artifacts. Review is complete, bugs fixed, commits merged.

| File | Reason |
|---|---|
| `docs/REVIEW_PLAN.md` | S81 review plan — executed |
| `docs/REVIEW_RESULTS.md` | S81 review summary — complete |
| `docs/REVIEW_RESULTS_P1.md` | Phase 1 results — complete |
| `docs/REVIEW_RESULTS_P2.md` | Phase 2 results — complete |
| `docs/REVIEW_RESULTS_P3.md` | Phase 3 results — complete |
| `docs/REVIEW_RESULTS_P4.md` | Phase 4 results — complete |
| `docs/REVIEW_RESULTS_P5.md` | Phase 5 results — complete |
| `docs/REVIEW_RESULTS_P6.md` | Phase 6 results — complete |
| `docs/REVIEW_RESULTS_P7.md` | Phase 7 results — complete |

### 2. Top-level docs → `docs/archive/`
| File | Reason |
|---|---|
| `docs/SYSTEM_OVERVIEW.md` | Redundant with `core/PROJECT_OVERVIEW.md`. SYSTEM_OVERVIEW is a 42KB blog-post-style writeup; PROJECT_OVERVIEW is the operational reference (updated S82). |
| `docs/SONNET_HANDOFF.md` | S81 task handoff to Sonnet — tasks executed in S82. No longer actionable. |

### 3. `docs/temporary review/` → `docs/archive/temporary_review/`
Entire folder. These are one-off review docs from pre-launch sessions.

| File | Reason |
|---|---|
| `BASELAYER_OPENCLAW_GUIDE.md` | Temporary review doc |
| `BASE_LAYER_GTM_STRATEGY.md` | Temporary review doc |
| `CLAUDE_CODE_HANDOFF.md` | Temporary review doc |
| `WEBSITE_DEPLOYMENT_NOTES.md` | Temporary review doc |

### 4. `docs/analysis/` → `docs/archive/analysis/`
Entire folder. All files from Session 7-43 era (pre-S60). CHARACTER_OVERVIEW.md contains Aarik's full personal data — should not be in active docs regardless.

| File | Reason |
|---|---|
| `AARIK-ANALYSIS.md` | S7 observation log — historical only |
| `CHARACTER_OVERVIEW.md` | S43 identity portrait — superseded by pipeline output, contains PII |
| `CLAUDE-APPROACH.md` | S11 model shift reflection — historical only |

### 5. `docs/demo/` → `docs/archive/demo/`
Entire folder. "Talk to History" interactive demo was never built as specified. Website launched with a different approach (examples page, Try It page). These specs are dead.

| File | Reason |
|---|---|
| `DEMO_TECHNICAL_SPEC.md` | Unbuilt demo architecture spec |
| `FIGURE_PREP_GUIDE.md` | Figure prep for unbuilt demo |
| `IMPLEMENTATION_TASKS.md` | Task list for unbuilt demo |

### 6. `docs/plans/` → `docs/archive/plans/`
All plans are either executed, stale, or for features never built.

| File | Reason |
|---|---|
| `CONTRADICTION_WORKFLOW_PLAN.md` | S81 draft — contradictions proved ceremonial in S79 ablation |
| `MULTI_PROVIDER_PLAN.md` | S56/59 — never executed, stale |
| `PROVENANCE_TRACE_ARCHITECTURE.md` | S55 design — IMPLEMENTED in S56-57, now historical |
| `RELATIONSHIP_EXTRACTION_PLAN.md` | S55/56 — partially implemented, stale since S56 |
| `WEB_SECURITY_COMPLIANCE.md` | Pre-build checklist for web service never built |
| `WEB_SERVICE_SECURITY_THREAT_MODEL.md` | Threat model for web service never built |

### 7. `docs/reviews/` (pre-S60 only) → `docs/archive/reviews/`
Keep: `COLLECTIVE_REVIEW_S78.md` (active), `SECURITY_REVIEW_S67.md` (referenced in CLAUDE.md).

| File | Reason |
|---|---|
| `ANCHOR_REVIEW_SESSION37.md` | S37 — pre-S60 |
| `CONTAMINATION_REVIEW.md` | Pre-D-044 era — pre-S60 |
| `LAYER_DELINEATION_REVIEW.md` | S42 — pre-S60 |
| `OPENROUTER_PROXY_DESIGN.md` | S41 — pre-S60, never built |
| `README_REVIEW_S57.md` | S57 — pre-S60 |
| `SECURITY_AUDIT_SESSION41.md` | S41 — pre-S60, superseded by S55 and S67 audits |
| `SECURITY_CODE_AUDIT_S55.md` | S55 — pre-S60, superseded by S67 audit |
| `SESSION42_RECOMMENDATIONS.md` | S42 — pre-S60 |
| `TEMPORAL_PROCESSING_REVIEW.md` | S23 — pre-S60 |
| `VALUE_PROPOSITION_REVIEW.md` | S37 — pre-S60 |

---

## Kept in Place (No Changes)

### `docs/core/` — Protected
- `ARCHITECTURE.md` — active
- `DECISIONS.md` — active (78 decisions)
- `DESIGN_PRINCIPLES.md` — active
- `PROGRESS.md` — active
- `PROJECT_OVERVIEW.md` — active (updated S82)
- `EPISTEMIC_AXIOMS.md` — S38 axioms, note says see deployed v4 version. Borderline archive but lives in core, leaving it.
- `FLOW_GUIDE.md` — user flow guide, still relevant for onboarding

### `docs/eval/` — Active evaluation docs
All kept. `docs/eval/archive/` already exists with its own archived evals.

### `docs/research/` — Active research
- `AXIOM_BENCHMARK_HYPOTHESIS.md` — active (ADRB)
- `BEHAVIORAL_DATASETS.md` — active
- `PHILOSOPHY_OF_IDENTITY.md` — active
- `VOICE_RESEARCH.md` — active (voice layer concept from S79)

### `docs/diagnostics/`
- `D079_PROVENANCE_ENFORCEMENT_DIAGNOSTIC.md` — S84, active

### `docs/reviews/` (post-S60, kept)
- `COLLECTIVE_REVIEW_S78.md` — S78, active
- `SECURITY_REVIEW_S67.md` — S67, referenced in CLAUDE.md

### `docs/versions/` — Already an archive folder
Left untouched.

### `docs/archive/` — Existing archive
Left untouched. New files will be added to subdirectories.

---

## Shell Commands to Execute

```bash
# Create archive subdirectories
mkdir -p docs/archive/s81_code_review
mkdir -p docs/archive/temporary_review
mkdir -p docs/archive/analysis
mkdir -p docs/archive/demo
mkdir -p docs/archive/plans
mkdir -p docs/archive/reviews

# 1. S81 code review
mv docs/REVIEW_PLAN.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P1.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P2.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P3.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P4.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P5.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P6.md docs/archive/s81_code_review/
mv docs/REVIEW_RESULTS_P7.md docs/archive/s81_code_review/

# 2. Top-level redundant docs
mv docs/SYSTEM_OVERVIEW.md docs/archive/
mv docs/SONNET_HANDOFF.md docs/archive/

# 3. Temporary review folder
mv "docs/temporary review/BASELAYER_OPENCLAW_GUIDE.md" docs/archive/temporary_review/
mv "docs/temporary review/BASE_LAYER_GTM_STRATEGY.md" docs/archive/temporary_review/
mv "docs/temporary review/CLAUDE_CODE_HANDOFF.md" docs/archive/temporary_review/
mv "docs/temporary review/WEBSITE_DEPLOYMENT_NOTES.md" docs/archive/temporary_review/
rmdir "docs/temporary review"

# 4. Analysis folder
mv docs/analysis/AARIK-ANALYSIS.md docs/archive/analysis/
mv docs/analysis/CHARACTER_OVERVIEW.md docs/archive/analysis/
mv docs/analysis/CLAUDE-APPROACH.md docs/archive/analysis/
rmdir docs/analysis

# 5. Demo folder
mv docs/demo/DEMO_TECHNICAL_SPEC.md docs/archive/demo/
mv docs/demo/FIGURE_PREP_GUIDE.md docs/archive/demo/
mv docs/demo/IMPLEMENTATION_TASKS.md docs/archive/demo/
rmdir docs/demo

# 6. Plans folder
mv docs/plans/CONTRADICTION_WORKFLOW_PLAN.md docs/archive/plans/
mv docs/plans/MULTI_PROVIDER_PLAN.md docs/archive/plans/
mv docs/plans/PROVENANCE_TRACE_ARCHITECTURE.md docs/archive/plans/
mv docs/plans/RELATIONSHIP_EXTRACTION_PLAN.md docs/archive/plans/
mv docs/plans/WEB_SECURITY_COMPLIANCE.md docs/archive/plans/
mv docs/plans/WEB_SERVICE_SECURITY_THREAT_MODEL.md docs/archive/plans/
rmdir docs/plans

# 7. Pre-S60 reviews
mv docs/reviews/ANCHOR_REVIEW_SESSION37.md docs/archive/reviews/
mv docs/reviews/CONTAMINATION_REVIEW.md docs/archive/reviews/
mv docs/reviews/LAYER_DELINEATION_REVIEW.md docs/archive/reviews/
mv docs/reviews/OPENROUTER_PROXY_DESIGN.md docs/archive/reviews/
mv docs/reviews/README_REVIEW_S57.md docs/archive/reviews/
mv docs/reviews/SECURITY_AUDIT_SESSION41.md docs/archive/reviews/
mv docs/reviews/SECURITY_CODE_AUDIT_S55.md docs/archive/reviews/
mv docs/reviews/SESSION42_RECOMMENDATIONS.md docs/archive/reviews/
mv docs/reviews/TEMPORAL_PROCESSING_REVIEW.md docs/archive/reviews/
mv docs/reviews/VALUE_PROPOSITION_REVIEW.md docs/archive/reviews/
```

---

## Post-Cleanup Structure

```
docs/
  CLEANUP_LOG.md              ← this file
  archive/                    ← all archived material
    s81_code_review/          ← 9 files (REVIEW_PLAN + REVIEW_RESULTS*)
    temporary_review/         ← 4 files
    analysis/                 ← 3 files (AARIK-ANALYSIS, CHARACTER_OVERVIEW, CLAUDE-APPROACH)
    demo/                     ← 3 files (DEMO_TECHNICAL_SPEC, FIGURE_PREP_GUIDE, IMPLEMENTATION_TASKS)
    plans/                    ← 6 files
    reviews/                  ← 10 files (pre-S60 reviews)
    [existing 7 files]        ← EXTRACTION_CAP_SCALING_PLAN etc.
    SYSTEM_OVERVIEW.md
    SONNET_HANDOFF.md
  core/                       ← 7 files (untouched)
  diagnostics/                ← 1 file
  eval/                       ← 20+ files + subfolders (untouched)
  research/                   ← 4 files (untouched)
  reviews/                    ← 2 files (COLLECTIVE_REVIEW_S78, SECURITY_REVIEW_S67)
  versions/                   ← untouched
```

**30 files archived. 0 files deleted. 0 core files modified. 4 empty directories removed.**
