# Prompt Ablation Study: Optimizing Behavioral Brief Composition (D-079)

**Base Layer Research Report**
**Date:** 2026-03-10 | **Session:** 85
**Status:** All 7 rounds complete
**Cost:** ~$18.40 total (~$12 generation, ~$6.40 review)

---

## Abstract

We conducted a 30-condition prompt ablation study to determine the optimal method for composing behavioral briefs — short documents that compress a person's behavioral patterns into a form an LLM can use to adapt its interactions. The study tested architectural choices (single-pass vs. multi-stage), prompt content (what instructions to include), structural decisions (how to organize the output), and evaluation rubric design (what to optimize for). Three subjects were used: Benjamin Franklin (historical, document-derived), Warren Buffett (public figure, document-derived), and Aarik (the system's creator, conversation-derived). Key findings: single-pass Opus outperforms multi-stage architectures, false positive warnings are load-bearing but prone to fabrication, rubric awareness is the strongest meta-strategy, and epistemic calibration — explicitly marking what the system cannot predict — is the study's novel contribution to AI personalization. The winning condition (C28: rubric awareness + temporal markers + "cannot predict" gaps) scored 87.0/90 average across subjects.

---

## 1. Background

### 1.1 The Composition Problem

Base Layer extracts behavioral facts from conversation history and other documents, then organizes them into three source layers:

- **Anchors:** Core axioms and non-negotiable principles (what the person will not compromise on)
- **Core:** Context, communication style, and domain expertise (how the person operates)
- **Predictions:** Behavioral patterns with detection triggers, action directives, and false-positive conditions (when and how to apply each pattern)

The composition step takes these three layers and produces a unified brief — a single document injected into LLM context. The brief must be faithful to source material, compressed enough for practical context windows, and actionable enough to change LLM behavior. Prior to this study, composition used a "V4" prompt that had been iteratively refined but never systematically ablated.

### 1.2 Motivation

Session 78 research established that shorter briefs (~1,000-2,500 chars) outperform longer ones on downstream tasks, that behavioral facts are the strongest cross-type predictors, and that an annotated guide format outperforms raw prose. Session 79 ablation proved that 10 of 14 pipeline steps were ceremonial. But the composition prompt itself — the final step that determines what the LLM actually sees — had never been subjected to controlled variation. This study fills that gap.

### 1.3 Experimental Setup

| Parameter | Value |
|---|---|
| Subjects | Franklin, Buffett, Aarik |
| Conditions | 30 (C0-C30) |
| Briefs generated | ~90 |
| Compose model | claude-opus-4-20250514 |
| Review model | claude-opus-4-20250514 (Collective review) |
| Avg. cost per brief | ~$0.13 |
| Avg. cost per review | ~$0.11 |
| Total cost | ~$18.40 |
| Script | `scripts/experiments/pe_ablation.py` |
| Results | `scripts/experiments/pe_ablation_results.json`, `scripts/experiments/score_ablation_results.json` |

Each condition was run on all three subjects. Briefs were scored by Collective review (Opus) against the source layers, not against ground truth behavior. Two rubric versions were used across the study (detailed in Section 4).

---

## 2. Study Design

### 2.1 Condition Summary

| Round | Conditions | Question |
|---|---|---|
| 1 | C0-C7 | Does multi-stage (Planner-Executor) beat single-pass? |
| 2 | C8-C11 | Which prompt content elements matter? |
| 3 | C12-C13 | Are false positive warnings load-bearing? |
| 4 | C14 | Can we fix FP fabrication without removing FP warnings? |
| 5 | C15-C23 | Can we close remaining quality gaps? |
| 6 | C24-C27 | How do conditions perform under a redesigned rubric? |
| 7 | C28-C30 | Does integrating research gaps improve quality? |

### 2.2 Subjects

- **Benjamin Franklin:** Historical figure. Source layers derived from autobiography via document-mode extraction. High axiom density, strong tension patterns, no live conversation data.
- **Warren Buffett:** Public figure. Source layers derived from shareholder letters and interviews. Systematic thinker with coherent investment philosophy. High internal consistency.
- **Aarik:** System creator. Source layers derived from 80+ sessions of conversation history. Highest data density, most complex behavioral signature, and the only subject with ground-truth validation available.

---

## 3. Results by Round

### 3.1 Round 1: Architecture Comparison (C0-C7)

**Question:** Does a Planner-Executor (P-E) architecture outperform a single Opus pass?

**Finding:** Single-pass Opus beats P-E across all variants. P-E added cost ($0.20+ vs $0.11), latency (~60s vs ~30s), and complexity without improving quality. Composition quality is bounded by prompt content and rubric alignment, not by planning depth. The pipeline remains 4 steps with no additional orchestration layer needed.

### 3.2 Round 2: Prompt Content Ablation (C8-C11)

**Finding 1:** C9's false-positive-first structure won. Organizing the brief around "when NOT to apply this pattern" proved more effective than organizing around the patterns themselves. This aligns with S78's finding that avoidance predicates are the most predictive behavioral facts.

**Finding 2:** When given complete freedom (C11), Opus independently chose the annotated guide format — the same format S78 identified as optimal (+24% on downstream tasks). Convergence across independent experiments strengthens confidence in the format choice.

### 3.3 Round 3: FP Warning Ablation (C12-C13)

**Finding:** FP warnings are load-bearing. Removing them (C13) degraded quality by 4.6 points on average. However, C12 revealed a critical failure mode: when instructed to synthesize FP warnings, the model fabricated warnings for anchor-derived patterns that had no FP conditions in the source layers. This fabrication is the single largest faithfulness leak observed in the study.

### 3.4 Round 4: FP Faithfulness Fix (C14)

**Finding:** A single instruction — "only include FP warnings where the source material explicitly provides them" — eliminated the fabrication leak. C14 scored 73.0/85 avg (old rubric best). The faithfulness problem was instructional, not architectural.

### 3.5 Round 5: Systematic Gap Closure (C15-C23)

**Finding 1 — Completeness vs. efficiency is a fundamental tension.** C16 achieved exhaustive source coverage at 10K+ chars — well above the optimal 1,000-5,000 range. Completeness as a standalone optimization target drives briefs toward exhaustive enumeration.

**Finding 2 — Example phrasings are fabricated content.** C19 and C21 tested "example phrasings." These improved actionability but introduced faithfulness risk — the phrasings don't appear in source layers. Connected to D-078 (template contamination).

**Finding 3 — Rubric awareness helps.** C19 and C23 both included the rubric in the compose prompt. Both scored at or near the top. The model optimizes for what it is told to optimize for — which makes rubric design the highest-leverage activity.

### 3.6 Rubric Redesign

The original rubric over-weighted structural properties (traceability at 35%) and under-weighted purpose (actionability at 12%). A redesign derived four primitives from: "What must be true for an LLM to understand how to work with a specific human?"

**Old Rubric (/85):** Traceability 3x (30), Faithfulness 2x (20), Token Efficiency 1x (10), Completeness 1x (10), Actionability 1x (10), FP Grounding +5

**New Rubric (/90):** Provenance 3x (30), Behavioral Change 3x (30), Epistemic Calibration 2x (20), Signal Density 1x (10)

Key changes: Traceability + Faithfulness merged into Provenance. Actionability upgraded from 1x to 3x as Behavioral Change. FP Grounding absorbed into Epistemic Calibration at 2x. Completeness absorbed into Signal Density. Each primitive grounded in research (see Section 5).

### 3.7 Round 6: New Rubric Conditions (C24-C27)

| Condition | Avg. Score | Notes |
|---|---|---|
| C24 (epistemic loop) | 71.0/90 | Solid but structurally rigid |
| C25 (compressed) | Below C24 | Compression destroyed behavioral specificity |
| C26 (rubric awareness) | 73.7/90 | **Round 6 leader** |
| C27 (no structural prescription) | Variable | Format varied by subject — appropriate |

**Finding 1 — C26 wins.** Rubric awareness remains the strongest meta-strategy.

**Finding 2 — Different people need different formats.** C27 produced: tension-centered (Franklin), system-coherence (Buffett), imperative-structured (Aarik). Reviewers confirmed appropriateness.

**Finding 3 — "Cannot predict" is the top improvement suggestion.** Across all Round 6 reviews, the most consistent recommendation was to include explicit epistemic gaps.

### 3.8 Round 7: Research Integration (C28-C30)

Three conditions integrated research-identified gaps into the C26 base:

| Condition | Description | Franklin | Buffett | Aarik | **Average** |
|---|---|---|---|---|---|
| **C28** | C26 + cannot predict + temporal | 89 | 86 | 86 | **87.0** |
| C29 | C26 + relational + agency | 73 | 68 | 87 | 76.0 |
| C30 | Full research synthesis | 86 | 82 | 88 | 85.3 |

**C28 is the study winner at 87.0/90 (96.7%).**

Detailed C28 scoring breakdown:

| Subject | Provenance | Behavioral Change | Epistemic Cal. | Signal Density | Total |
|---|---|---|---|---|---|
| Franklin | 30/30 | 30/30 | 20/20 | 9/10 | 89/90 |
| Buffett | 29/30 | 29/30 | 19/20 | 9/10 | 86/90 |
| Aarik | 27/30 | 30/30 | 20/20 | 9/10 | 86/90 |

**Finding 1 — C28 is the production candidate.** Adding "cannot predict" and temporal awareness to the rubric-aware prompt produced the highest scores across all 30 conditions. The additions are small (2 paragraphs in the prompt) but high-leverage.

**Finding 2 — C29 has a faithfulness problem.** The relational context + agency prompt caused FP fabrication on 2 of 3 subjects: Buffett C29 got P3=3/10 (fabricated FP warnings), Franklin C29 got E1=0/10 (missing FPs entirely). The relational prompt competes with faithfulness as an optimization target. However, Aarik C29 scored 87 — the prompt works when source layers have richer relational data.

**Finding 3 — C30 is worse than C28 despite being a superset.** C30 included ALL research integrations (temporal + relational + agency + cannot predict). At 85.3 avg, it trails C28 by 1.7 points. More instructions create more competing optimization targets. Focused additions outperform comprehensive ones.

**Finding 4 — Signal Density is a ceiling.** Every brief across all 9 Round 7 reviews scored 9/10 on Signal Density. It is no longer differentiating at this quality level.

**Finding 5 — Epistemic Calibration is the differentiator.** C28 averaged 19.7/20 on Epistemic Calibration. C29 averaged 12.0/20. The gap between the best and worst conditions is almost entirely in this dimension.

---

## 4. Major Conclusions

### 4.1 Single-pass beats multi-stage
P-E architecture added cost and complexity without improving quality. Composition quality is bounded by prompt content, not planning depth.

### 4.2 False positive warnings are load-bearing but fabrication-prone
+4.6 avg when included. But the model fabricates them when source material lacks them. Fix: explicit "do not fabricate" instruction.

### 4.3 Rubric awareness is the strongest meta-strategy
Across both rubrics, including evaluation criteria in the prompt produced the best results. Makes rubric design the highest-leverage activity.

### 4.4 The rubric must derive from first principles
Original rubric misallocated weight (35% to traceability, 12% to actionability). Redesigned around 4 primitives of understanding how to work with a human.

### 4.5 Completeness and efficiency are in direct tension
Exhaustive coverage → 10K+ chars. Optimal is 3,500-5,000. Completeness absorbed into Signal Density.

### 4.6 Different people need different formats
No structural prescription → model chooses format matched to subject. Prescribing format constrains quality.

### 4.7 Epistemic calibration is the novel contribution
No comparable system includes "not active when" conditions, [CONTESTED] tags, or "cannot predict" gaps. An LLM that knows where its model breaks down is more useful than one that's confidently wrong.

### 4.8 Focused additions outperform comprehensive ones
C28 (2 focused additions) beat C30 (all additions). More prompt instructions create competing optimization targets.

---

## 5. Research Grounding

### 5.1 Provenance
Grounded in XAI literature (Ribeiro et al. LIME, Lundberg SHAP). Explanations of reasoning improve user trust and enable error detection. In the brief context: the LLM must explain "I believe X because of Y from your history."

### 5.2 Behavioral Change
Grounded in adaptive systems literature and Information Bottleneck theory (Tishby et al.). Information that does not change behavior is noise. The bottleneck principle: maximize relevant information at minimum description length.

### 5.3 Epistemic Calibration
Grounded in calibration research (Guo et al. 2017), selective prediction ("I don't know" as a feature). A model that knows what it doesn't know prevents confident errors in unknown contexts.

### 5.4 Signal Density
Grounded in information theory, minimum description length, compression-as-understanding. Every sentence must add new understanding; redundancy is penalized.

### 5.5 Research Gaps Identified
Three gaps not addressed in published literature, integrated into C28-C30:
1. **Temporal dynamics** — behavioral patterns from a specific time window may evolve
2. **Relational context** — patterns may shift based on relationship dynamics
3. **User agency** — the person should be able to inspect and contest claims

### 5.6 No Published Framework Combines All Four
Individual primitives are well-established. No published personalization framework combines provenance, behavioral change, epistemic calibration, and signal density. This combination is Base Layer's contribution.

---

## 6. Contradictions with Prior Research

### 6.1 Brief Length: S78 vs. Ablation

**S78:** "Shorter is better" (1,000-2,500 chars optimal on downstream tasks)
**Ablation:** Best briefs are 3,500-5,000 chars

**Reconciliation:** S78 tested downstream task accuracy with GPT-4.1-mini (Twin-2K benchmark). The ablation scored composition quality with Opus. Different measures, different optima. Downstream task accuracy may plateau at shorter lengths because the task only needs a subset of the brief. Composition quality requires more content to cover all four primitives. There may be a model-dependent sweet spot — smaller models need shorter briefs.

### 6.2 Data Volume: S78 vs. Ablation

**S78:** "More data hurts" (Q1 alone outperforms Q1+Q2+Q3 for predicting Q4)
**Ablation:** More source coverage is better (B3 context coverage scores)

**Reconciliation:** S78 tested INPUT data volume — feeding more raw conversations into extraction. The ablation tested OUTPUT coverage of already-extracted patterns. Not contradictory: you want comprehensive coverage of compressed input, not comprehensive input.

### 6.3 Adding Content: S78 vs. C28-C30

**S78:** "Adding content hurts" (counter-brief merge -0.74)
**Ablation:** C28-C30 add new sections (temporal, cannot predict, relational) and score highest

**Reconciliation:** S78 counter-brief merge added REDUNDANT content (same patterns rephrased). C28-C30 add NOVEL epistemic content (uncertainty markers, explicit gaps). New information types improve quality; more of the same degrades it.

### 6.4 Collective Review: S79 vs. This Study

**S79:** "Collective review is ceremonial" (author without review scores equal or better)
**This Study:** Uses Collective review as the scoring mechanism

**Reconciliation:** S79 tested review as a GENERATION step (reviewing layers before composition). This study uses review as an EVALUATION mechanism with a defined rubric. Different function — review-as-gate vs. review-as-judge. The finding stands: review as a generation step is ceremonial. Review as evaluation with a rubric is valuable.

### 6.5 Confirmed Findings

**S78: "Behavioral > biographical"** — CONFIRMED. C12's completeness mandate forced biographical coverage → bloat without quality gain.

**S78: "Avoidance/experiential predicates win"** — CONFIRMED. FP warnings (avoidance patterns) are the highest-leverage individual feature (+4.6 avg).

**S79: "3-layer architecture is load-bearing"** — NOT TESTED in this study (all conditions use the same 3-layer source input).

---

## 7. Practical Implications

### 7.1 Recommended Compose Prompt

Based on C28 (study winner at 87.0/90):

1. **Single Opus pass** (not multi-stage)
2. **New rubric in prompt** (Provenance 30%, Behavioral Change 30%, Epistemic Calibration 20%, Signal Density 20%)
3. **FP faithfulness guard** ("include only where source PREDICTIONS layer provides them")
4. **Temporal awareness** ("patterns from specific time window, may evolve")
5. **"Cannot predict" section** (3-5 explicit epistemic gaps)
6. **No structural prescription** (model chooses format)
7. **Target length: 3,500-4,500 chars**

### 7.2 Not Recommended

- Multi-stage P-E architecture (more cost, no quality gain)
- Structural templates (constrain format unnecessarily)
- Completeness mandates (drive bloat)
- Example phrasings (fabrication risk)
- Relational context prompting (causes FP fabrication on subjects with thin relational data)

---

## 8. Limitations

1. **Model-judged, not human-judged.** Scoring by Opus Collective review measures faithfulness and structure, not real-world behavioral improvement. Twin-2K provides behavioral validation separately.

2. **N=3 subjects.** Historical, public, personal profiles represented, but does not cover sparse data or highly contradictory behavioral patterns.

3. **Two rubric versions.** C0-C23 scored under old rubric (/85), C24-C30 under new (/90). Direct cross-rubric comparison invalid.

4. **Rubric awareness ceiling.** If the prompt includes the rubric, the model optimizes for it. The rubric IS the ceiling — any missing dimension will be systematically under-served.

5. **Single compose model.** All conditions used Opus. Rubric awareness may not transfer to other models.

6. **C28 scores may be inflated.** At 87.0/90, the scores are near ceiling. This could reflect genuine quality OR reviewer leniency at high quality levels. Human evaluation needed to validate.

---

## 9. Future Work

1. **Temporal stability on conversation data.** Original temporal study used Franklin (autobiography) and Marks (memos). Rerun on Aarik's GPT conversations (linear conversation history) to test whether findings generalize to conversational data.

2. **Human evaluation.** Have Aarik and domain experts rate C28 briefs for real-world utility vs. rubric-scored quality.

3. **Rubric weight ablation.** Test alternative weight distributions (e.g., Behavioral Change at 4x).

4. **Cross-model transfer.** Test whether C28 prompt produces equivalent quality on Sonnet.

5. **Downstream task validation.** Run Twin-2K with C28 briefs vs. production V4 briefs.

---

## Appendix A: Full Score Table (New Rubric, Rounds 6-7)

| Condition | Franklin | Buffett | Aarik | Average |
|---|---|---|---|---|
| C24 (epistemic loop) | - | - | - | 71.0 |
| C25 (compressed) | - | - | - | < C24 |
| C26 (rubric awareness) | 77 | 66 | 78 | 73.7 |
| C27 (no structural rx) | - | - | - | Variable |
| **C28 (cannot predict + temporal)** | **89** | **86** | **86** | **87.0** |
| C29 (relational + agency) | 73 | 68 | 87 | 76.0 |
| C30 (full synthesis) | 86 | 82 | 88 | 85.3 |

## Appendix B: Condition Reference

| Cond | Round | Description | Rubric | Key Finding |
|---|---|---|---|---|
| C0 | 1 | Production V4 (baseline) | Old | Low traceability |
| C1-C3 | 1 | P-E variants | Old | All worse than single-pass |
| C4 | 1 | Single Opus + token cap | Old | Best architecture |
| C5-C7 | 1 | P-E + variants | Old | Assembly/faithfulness checks don't help |
| C8 | 2 | Traceability + FP + directives | Old | Solid baseline |
| C9 | 2 | FP-first structure | Old | Round 2 winner (68.3) |
| C10 | 2 | Bare minimum | Old | Competitive despite simplicity |
| C11 | 2 | Free format | Old | Model discovers annotated guide |
| C12 | 3 | Collective-prescribed | Old | Bloat + FP fabrication |
| C13 | 3 | C9 - FP warnings | Old | -4.6 avg (FP load-bearing) |
| C14 | 4 | FP faithfulness fix | Old | Old rubric winner (73.0) |
| C15 | 5 | + M1 mandate | Old | M1 verbatim = bloat |
| C16 | 5 | + completeness checklist | Old | 10K+, proves tension |
| C17 | 5 | Radical compression | Old | Too terse |
| C18 | 5 | No opening paragraph | Old | Negligible effect |
| C19 | 5 | Old rubric as target | Old | Near-best, but example fabrication |
| C20 | 5 | Prescribed hybrid | Old | Solid, unremarkable |
| C21 | 5 | + example phrasings | Old | Phrasings = fabrication |
| C22 | 5 | Radical compression v2 | Old | Good FP, too terse |
| C23 | 5 | Old rubric awareness | Old | Tied C14 |
| C24 | 6 | Epistemic loop | New | Structurally rigid |
| C25 | 6 | Compressed | New | Destroyed specificity |
| C26 | 6 | New rubric awareness | New | Round 6 winner (73.7) |
| C27 | 6 | No structural rx | New | Format-per-person insight |
| **C28** | **7** | **Cannot predict + temporal** | **New** | **STUDY WINNER (87.0)** |
| C29 | 7 | Relational + agency | New | FP fabrication on 2/3 |
| C30 | 7 | Full synthesis | New | Good but less focused |

## Appendix C: New Rubric Specification

| Dimension | Items | Max | Description |
|---|---|---|---|
| Provenance | P1 (citation coverage), P2 (cross-layer), P3 (faithfulness) | 30 | Can the LLM explain HOW it knows each claim? |
| Behavioral Change | B1 (directives), B2 (communication), B3 (context coverage) | 30 | Does information change LLM behavior? |
| Epistemic Calibration | E1 (FP grounding), E2 (uncertainty marking) | 20 | Does the brief mark what is uncertain or unpredictable? |
| Signal Density | S1 (compression quality) | 10 | Maximum signal, minimum noise |
| **Total** | | **90** | |

---

*Study conducted as part of the Base Layer project (Session 85). All briefs stored in subject `data/identity_layers/` directories. Scripts: `pe_ablation.py`, `score_ablation.py`. Results: `pe_ablation_results.json`, `score_ablation_results.json`.*
