# Axiom Benchmark Research Plan

**Research Question:** Do axioms extracted from a project's own design rationale improve AI performance on that project's real engineering tasks?

**Date:** 2026-03-12 | **Status:** T4 COMPLETE — NULL RESULT. No condition beat baseline. See `data/swebench/AXIOM_STUDY_REPORT.md` for full results.

**Reviewers:** Opus API (methodology), Sonnet API (methodology)

---

## Background

Drift Experiment 1 proved that axiom-structured briefs produce **targeted** behavioral change (SR > 2.0 across 4 models). Dose-Response (E2) found the optimal dose is 3-5 axioms (peak SR 3.30 at dose 5, degradation at 8+). But targeted change ≠ better performance. This study closes the gap: does that targeted change translate to measurably better outcomes on established benchmarks?

### What We've Proven
- Axiom format routes new information to the correct behavioral dimension (E1, 4 models)
- Format matters more than model size (Qwen 7B axioms SR 2.55 > Sonnet atomic SR 0.54)
- Flat preference lists produce diffuse or missed drift (SR < 1.0)
- Optimal dose is 3-5 axioms; beyond 5 targeting degrades (E2)
- Generic personas ("You are an expert") show no improvement over no persona (literature)
- Unstructured repo context (AGENTS.md) REDUCES performance by ~3% (ETH Zurich, Feb 2026)

### What We Haven't Proven
- Whether axiom-conditioned agents produce **better** code
- Whether the improvement is **domain-specific** (repo axioms help that repo) or **general** (any good axioms help everywhere)
- Whether format advantage holds when measuring task outcomes (not just behavioral probes)

---

## Tiered Gating Structure

Each tier is gated by success. Aarik confirms go/no-go before proceeding.

| Tier | Gate | Go Condition | No-Go Action |
|---|---|---|---|
| T1 | Dose-response (E2) | Saturation curve found, optimal N identified | Redesign axiom injection approach |
| T2 | Axiom extraction | 5+ actionable, Django-specific axioms extracted | Try different source material or manual curation |
| T3 | Sanity check | Extracted axioms produce SR > 1.5 on E1 probes | Axioms aren't behavioral — re-extract or re-curate |
| T4 | SWE-Bench pilot (30 problems) | C2 > C0 by ≥5% with p < 0.05 | Null result — publish honestly |
| T5 | Cross-provider scale (100+ problems) | Effect replicates across ≥2 providers | Provider-specific effect — narrow finding |

**Current status:** T1 COMPLETE. T2 COMPLETE. T3 COMPLETE (PASS). **T4 COMPLETE — NULL RESULT.** C2 (30.0%) < C0 (36.7%), p=0.625. T5 NOT PROCEEDING.

**Framework:** OpenHands (industry standard, same as ETH Zurich study). Haiku 4.5, reasoning_effort: "none", 100 max iterations, Docker workspace.

**Actual cost:** $524 (OpenHands reported $146.52 — 3.5x underreport due to prompt caching).

---

## Study Design

### Phase 1: Dose-Response (E2) — COMPLETE

**Key finding:** Peak targeting at dose 5 (SR 3.30 Sonnet). Beyond 5, context overload causes diffuse drift. Optimal extraction target: **5 axioms per repository.**

See `docs/research/DRIFT_EXPERIMENT_RESULTS.md` for full results.

---

### Phase 2: Axiom Extraction — "What axioms?"

**Source: Django Design Documents**

Django covers 46% of SWE-Bench Verified (231 of 500 problems). Extract axioms from:

| Source | Type | Count |
|---|---|---|
| Django Enhancement Proposals (DEPs) | Design rationale — WHY decisions were made | 16 files |
| Django contributing guide | Process — HOW the project operates | 1 file |
| Django coding style docs | Standards — WHAT patterns are required | 1 file |
| Django design philosophies | Architecture — core principles | 1 file |

**Extraction method:** `baselayer run --document-mode` on scraped docs. Same pipeline that produces human identity briefs, applied to a codebase's design rationale.

**Curation:** From raw extraction (50-100+ axioms expected from 19 files), curate to top 5 (per E2 saturation). Selection criteria:
1. Must encode reasoning ("because..."), not just preference
2. Must be specific to Django, not generic engineering
3. Must be actionable for a code-change task

**C4 atomic conversion (REVIEWER FIX — confound addressed):** Previous plan stripped "because" clauses, which removes INFORMATION, not just FORMAT. Fixed approach: C4 preserves the same total information but restructures as flat bullet points without causal nesting. Example:
- C2 (axiom): "Django uses lazy evaluation for querysets because premature evaluation forces the database to do work the application layer could avoid, and lazy evaluation composes better with chaining operations"
- C4 (atomic): "Uses lazy evaluation for querysets. Avoids premature database evaluation. Prioritizes composability of chaining operations."
- Same information. Different structure. No "because" connectives, but the reasoning content IS preserved.

**Secondary source: scikit-learn SLEPs**
Same process, for the 32 scikit-learn problems in Verified. Provides cross-project validation.

**These become new examples on base-layer.ai** — "Base Layer for Django", "Base Layer for scikit-learn".

---

### Phase 3: SWE-Bench — "Do axioms improve real code?"

**The core claim:** Axioms extracted from Django's own design rationale improve performance on Django-specific SWE-Bench tasks.

#### Preregistered Hypotheses (REVIEWER ADDITION)

Specified before running, with corrections for multiple comparisons:

| Priority | Hypothesis | Test | Correction |
|---|---|---|---|
| **Primary** | H1: C2 > C0 (domain axioms beat baseline) | McNemar's test, α = 0.05 | None (single primary) |
| **Secondary** | H2: C2 > C4 (axiom format > atomic format) | McNemar's test, α = 0.025 | Bonferroni (2 secondary) |
| **Secondary** | H3: C2 > C3 (domain specificity matters) | McNemar's test, α = 0.025 | Bonferroni (2 secondary) |
| **Exploratory** | H4: C2 > C1 (domain axioms > generic prompt) | No correction | Report effect size only |
| **Exploratory** | H5: C5 > C2 (stacking helps) | No correction | Report effect size only |
| **Exploratory** | H6: C2 > C7 (structured axioms > raw repo context) | No correction | ETH Zurich replication |

Only H1 is required for the study to succeed. H2-H3 are bonus.

#### 7 Conditions (UPDATED — reviewer additions)

| Condition | System Prompt Content | What It Tests |
|---|---|---|
| **C0 — Bare** | Default model prompt | Baseline |
| **C1 — Generic** | "You are an expert software engineer. Think step by step." | Does ANY extra prompting help? |
| **C2 — Django Axioms** | 5 axioms in causal format from Django design docs | **THE TREATMENT** |
| **C3 — Wrong-Domain** | scikit-learn axioms on Django tasks | Domain specificity test |
| **C4 — Atomic Django** | Same info as C2, restructured as flat bullets (no causal nesting) | Format test (confound fixed) |
| **C5 — Combined** | Django axioms + generic prompt | Stacking test |
| **C7 — Raw Docs** | Raw Django design philosophy docs (~1183 tokens, unstructured) | Structured compression vs raw source material (ETH Zurich replication) |

**C6 DROPPED.** Replaced by C7 — stronger comparison. Tests whether axiom compression (C2, 327 tokens) outperforms raw source material (C7, 1183 tokens). Same content, different structure. Addresses ETH Zurich finding that unstructured repo context hurts.

#### Task Selection (REVISED — hard set)

**Original selection (easy set) failed.** 30 problems selected by patch size 2-50 lines produced 78.6% C0 solve rate — ceiling effect killed statistical power (McNemar's can't detect improvement when only 6 problems are unsolved).

**Revised selection (hard set):** 30 Django problems from SWE-Bench Verified, scored by:

| Criterion | Scoring |
|---|---|
| Difficulty rating | "1-4 hours" = +3, "15 min - 1 hour" = +1 |
| Files touched | 4+ = +3, 3 = +2, 2 = +1 |
| Patch lines | 100+ = +2, 50+ = +1, 30+ = +0.5 |

**Result:** Top 30 by composite score. 19x "1-4 hours", 11x "15 min-1 hour". Avg 95 patch lines, 2.3 files touched. Axiom relevance ≥3: 14/30 (47%, was 20%).

**Key improvement:** Problems now require system-wide reasoning (multi-file changes, cross-component interactions, async/sync coexistence) rather than isolated fixes. These are the problems where understanding Django's design philosophy should matter.

**Selection published:** `selected_django_30.txt` (hard set), `selected_django_30_easy.txt` (backup of original).

**Contamination control (REVIEWER ADDITION):** Verify selected problems are not trivially solvable by checking: (a) model cannot solve from issue title alone, (b) problems span multiple Django versions including recent ones, (c) report exact model training cutoff dates.

#### Evaluation

**Primary metric:** Pass@1 — does the model's patch pass the SWE-Bench test suite?

**Temperature:** 0 for all runs (REVIEWER FIX). Deterministic. No variance to characterize.

**Secondary metrics (REVIEWER ADDITIONS):**
- Partial credit: % of test cases passed (not just binary pass/fail)
- Patch size: lines changed (simpler passing patches = better)
- Axiom alignment: blind evaluation of whether solutions reflect injected principles

**Statistical approach (REVIEWER ADDITIONS):**
- McNemar's test for paired binary outcomes (same problems across conditions)
- Bootstrap confidence intervals for all effect sizes
- Report exact p-values, not just significance thresholds
- Mixed-effects model with problem difficulty as random effect (if sample size permits)

#### Infrastructure

- Docker required for SWE-Bench evaluation
- ~120GB disk, 16GB RAM
- Temperature = 0 across all conditions and models

#### Cost Estimate (REVISED — actual data from easy set)

| Component | Cost |
|---|---|
| Phase A easy set (C0 × 30, actual) | $19.33 |
| Phase A hard set (C0 × 30, est.) | ~$20-30 |
| Phase B hard set (C1-C5,C7 × 30, est.) | ~$120-180 |
| **Total Haiku (all 7 conditions)** | **~$140-210** |
| Sonnet replication (if signal) | ~$280-420 |

**Per-problem cost:** ~$0.69 (Haiku, reasoning_effort: "none", 100 max iterations).

**Why higher than original $75-100 estimate:** OpenHands uses richer tools and 100 max iterations. Original estimate assumed Sonnet batch API with simpler harness.

---

### Phase 4: Cross-Provider Scale (T5)

If T4 passes, replicate across providers to prove universality:

| Provider | Model | Method |
|---|---|---|
| Anthropic | Claude Sonnet | Batch API (50% discount) |
| OpenAI | GPT-4.1 | Batch API (50% discount) |
| Google | Gemini 2.5 Pro | Batch API (50% discount) |
| DeepSeek | DeepSeek-V3 | API |

100+ problems per provider. Same 7 conditions. Total cost ~$500-1000 with batch discounts.

---

### Phase 5: Analysis & Publication

#### Preregistered Outcomes

| Result | What It Means | Next Step |
|---|---|---|
| C2 > C0, C2 > C4 | Domain axioms in axiom format improve performance | Scale to T5, publish |
| C2 > C0, C2 ≈ C4 | Domain knowledge helps but format doesn't matter for outcomes | Nuanced finding — format matters for targeting, not outcomes |
| C2 ≈ C3 > C0 | Any axioms help — it's the format, not the content | Publish as structured prompting finding |
| C2 ≈ C0 | Axioms don't improve SWE-Bench performance | Null result — publish honestly |
| C6 ≈ C2 | Length effect, not content effect | Axiom content not special — prompt length is the variable |
| C1 ≈ C2 | Generic prompting = domain axioms | Axiom extraction adds no value over generic |

**Every outcome is publishable.** This isn't hypothesis confirmation — it's measurement.

---

## Reviewer Feedback: Acknowledged But Deferred

The following reviewer suggestions are valid but out of scope for this study:

1. **Inter-rater reliability for axiom curation** — Would require multiple human annotators. Deferred to follow-up study. We publish our extraction guidelines and curated axioms for reproducibility instead.
2. **RAG baseline (C7)** — Comparing axioms to full documentation retrieval is a different research question ("compression vs. retrieval"). Important but doubles study scope.
3. **Few-shot baseline (C8)** — Same: different research question. Deferred.
4. **Human-curated axiom baseline** — Valuable but requires domain experts. Could add post-pilot if results warrant.
5. **5+ repositories** — Django + sklearn is the minimum viable scope. Generalizability is a follow-up study.
6. **Theoretical framework (cognitive science grounding)** — Valid for publication at top venues. Not required for the empirical finding itself.
7. **Preregistration on OSF** — Ideal. Consider for T5 scale-up. For pilot, published plan serves as de facto preregistration.

---

## Cross-Cutting Dimension Finding (from E1)

F-TEST (testing) and F-SECURITY (security) produced diffuse drift in E1. This is correct behavior — testing and security ARE cross-cutting concerns that touch every coding task.

**For SWE-Bench:** Architecture-focused axioms will show the clearest signal. Security and testing axioms may improve overall performance without dimension-specific targeting — which is fine for a benchmark study where we measure pass rate, not specificity ratio.

---

## Risks

1. **SWE-Bench infrastructure complexity.** Docker setup, environment isolation, test evaluation. Mitigated by starting with 30-problem pilot.
2. **Axiom quality.** If Django docs don't produce actionable axioms, the extraction step fails. Mitigated by having multiple sources + manual curation step + T3 sanity gate.
3. **Sample size for pilot.** 30 problems may still be underpowered for small effects. McNemar's test on paired data helps. If borderline, scale before publishing.
4. **C4 confound (ADDRESSED).** Atomic version now preserves same total information in flat structure. Verified by word count comparison and content audit.
5. **Training data contamination.** Mitigated by checking historical pass rates and using problems from multiple Django versions.

---

## Connection to Base Layer

This study is the bridge between "Base Layer extracts behavioral patterns from people" and "Base Layer extracts expertise patterns from codebases." Same pipeline, same architecture, different input domain.

If it works: Base Layer isn't just a personal memory system. It's an expertise extraction and transfer system. "Base Layer for Django" becomes a product concept alongside "Base Layer for [person]."

The extracted axioms go on the website as new examples — alongside Franklin, Marks, Buffett. A codebase has an identity just like a person does.

---

## Files

| File | Purpose |
|---|---|
| `scripts/experiments/drift_experiment_2_dose_response.py` | E2 dose-response script |
| `scripts/experiments/drift_experiment_1.py` | E1 (imported by E2) |
| `docs/research/DRIFT_EXPERIMENT_RESULTS.md` | E1 results (publishable) |
| `docs/research/BEHAVIORAL_DRIFT_LITERATURE_REVIEW.md` | Academic context |
| `data/corpora/django/` | Django DEPs + docs (19 files) |
| `data/corpora/sklearn/` | scikit-learn SLEPs + docs (24 files) |
