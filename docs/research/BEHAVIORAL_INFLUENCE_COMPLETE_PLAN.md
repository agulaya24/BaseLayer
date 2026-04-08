# Behavioral Influence: Complete Research Plan

**Date:** 2026-04-07 (Session 102)
**Status:** Ready for collective review
**Author:** Aarik Gulaya + Claude Opus

---

## The Thesis

Autonomous AI agents need more than memory — they need behavioral specifications that change how the agent reasons, not just what it recalls. The serving layer is not an injection mechanism. It is a continuously measured behavioral delta between a model with the specification and a model without it. That delta IS the identity signal.

**Core claim:** A compressed behavioral specification measurably changes AI retrieval and reasoning in ways that are faithful to the person's actual behavioral patterns — and this change is fundamentally different from what any memory system provides.

**We are not optimizing for recall. Recall is the wrong metric in a world where memory is good enough.**

---

## What We've Built (Session 102)

### Serving Engine
A diff cascade that runs any statement through three conditions:
- **Mem0 condition:** Faithfully replicates Mem0's architecture (Chhikara et al., 2025, arXiv:2504.19413) — text-embedding-3-small, cosine top-10, raw query. No behavioral interpretation.
- **Base Layer condition:** Rewrites the query through the behavioral specification, retrieves facts using the interpreted query, generates response with spec loaded.
- **Merged condition:** Both fact sets combined with spec loaded.

### Visual Debugger TUI
Terminal UI showing the cascade live across 7 panels: Mem0 retrieval, Base Layer retrieval, divergence (with fact snippets), spec activation (which behavioral sections fired), and three response columns.

### Initial Results
- "What makes base layer special?" — **18/19 retrieved facts differ** between Mem0 and Base Layer. Mem0 retrieved cake recipes and mattress preferences. Base Layer retrieved agency, resilience, sovereignty.
- "What should I eat tonight?" — **20/20 facts differ.** Mem0 gave recipe lists (155 words). Base Layer asked about energy level and trading day (94 words). Merged did both (128 words).

---

## The Prediction Triangle

### Three predictions per decision point
1. **Spec prediction:** What the behavioral specification says this person would do
2. **Facts prediction:** What raw Mem0-style facts suggest this person would do
3. **Actual outcome:** What the person actually did (ground truth)

### Why three, not two
The diff between spec and facts reveals what compression captures that flat memory misses. The diff between spec and reality reveals whether the spec is accurate. The diff between facts and reality reveals whether raw memory is sufficient. All three together train the daemon.

### Divergence patterns
| Pattern | Meaning |
|---|---|
| All three agree | Stable pattern, high confidence |
| Spec + facts agree, person deviated | Person is changing |
| Spec right, facts wrong | Compression found subtle pattern flat recall missed — Base Layer's value |
| Facts right, spec wrong | Compression lost something or is stale |
| Spec + person agree, facts wrong | Pattern is real but emergent — not in any single fact |

---

## The Experiment

### Design: Temporal Split with Sliding Window

Use the founder's 102 Claude Code sessions as the dataset. Each session is documented in PROGRESS.md, git history, and conversation logs. Real decisions, real reasoning, real outcomes.

**Five training windows:**

| Training | Predict | Gap | What it tests |
|---|---|---|---|
| Sessions 1-20 | 21-25 | 0 | Can an early spec predict near term? |
| Sessions 1-20 | 50-55 | 29 | Can an early spec predict medium term? |
| Sessions 1-50 | 51-55 | 0 | Does more data help for same horizon? |
| Sessions 1-50 | 95-100 | 44 | Can a mid spec predict far future? |
| Sessions 1-100 | 101-102 | 0 | Can the full spec predict now? |

**Three conditions at each window:**

| Condition | Input | Tests |
|---|---|---|
| Mem0 flat facts | Raw extracted facts, no structure | Can raw memory predict behavior? |
| Base Layer spec | Compressed behavioral specification | Does compression improve prediction? |
| Spec + facts | Both combined | Does combining help? |

**Total: 5 windows × 3 conditions × 5-10 decisions per window = 75-150 prediction points**

### What we measure

**Primary metric:** Prediction accuracy — did the condition correctly predict what the person actually did? Binary (correct/incorrect) + reasoning quality score.

**Scaling curves:**
- **Depth curve:** Does accuracy improve with more training data (10→20→50→80→100 sessions)?
- **Horizon decay:** Does accuracy drop as you predict further out?
- **Phase transitions:** Are there sessions where ALL conditions fail? That's where the person changed.

**The prediction triangle at each point:**
- What the spec predicted
- What the facts predicted
- What actually happened
- The divergence pattern (which of the 5 patterns above)

### Ground truth

Actual decisions from documented sessions:
- "Killed the services page, chose research over revenue" (S102)
- "Cold-emailed 40+ public figures" (S100)
- "Applied to Anthropic as Solutions Architect, not engineering" (S101)
- "Ran 14-condition ablation and cut 10 of own pipeline steps" (S99)
- "Built solo for 100+ sessions without external validation" (S1-S102)
- And ~100 more decision points from session history

### Cost estimate

- 5 pipeline runs to build 5 specs: ~$10-15
- ~150 prediction API calls: ~$2-3
- Total: **~$15-20**

---

## The Daemon

### What it does
Watches the prediction triangle accumulate over time during live serving.

### What it computes
For each interaction:
1. Logs the spec-response and shadow-response
2. Computes the diff
3. Checks: which spec sections created the divergence?
4. Checks: does the divergence match the spec's predictions? (prediction fulfillment)
5. Accumulates divergence patterns

### What it reports (spec health)
| Metric | What it means |
|---|---|
| **Load-bearing sections** (fire >60%) | These spec sections consistently change the response. Keep them. |
| **Inert sections** (fire <10%) | These never change anything. Candidates for removal. |
| **Emerging patterns** | Divergence patterns appearing in diffs that aren't in the spec. Candidates for addition. |
| **Drift detection** | Prediction fulfillment rate changing over time. The person is changing. |
| **Phase shift alert** | Fulfillment drops below threshold across multiple sections simultaneously. Major behavioral change. |

### What it enables
- Self-correcting spec: daemon recommends additions/removals based on observed influence
- Temporal tracking: spec evolves with the person, not just with re-extraction
- The daemon is what makes the spec alive — without it, the spec is a dead document

### Open design questions
1. Does it use an LLM to classify each diff? (expensive but accurate)
2. Does it use embedding similarity between diff and predictions? (cheap but noisy)
3. How often does it run? (every interaction, every 10, daily?)
4. When does it recommend spec regeneration vs incremental update?

---

## The Paper

### Structure

1. **Introduction:** Agents need behavioral alignment, not just memory. AlpsBench proved recall is insufficient.
2. **Related work:** Memory systems (Mem0), persona evaluation (PersonaGym), sycophancy (Jain et al.), persona effect (Hu & Collier)
3. **The behavioral specification:** 47 predicates, three-layer architecture, extraction pipeline, 60+ subjects
4. **The diff:** With-spec vs without-spec comparison. What changes? Retrieval diverges (18/19 facts). Response quality changes (37 words vs 175). The model asks different questions.
5. **The prediction triangle:** Spec vs facts vs reality. Temporal split experiment. Scaling curves. Phase transitions.
6. **Comparison to SOTA:** Faithful replication of Mem0's architecture on the same data. Retrieval divergence. Response comparison.
7. **The daemon:** Self-correcting spec through observed behavioral influence. Prediction fulfillment rate as a novel metric.
8. **Discussion:** Sycophancy risk (Jain et al.), the difference between faithful reasoning and agreement, limitations.

### Key figures
1. Retrieval divergence chart (18/19 facts differ)
2. Scaling curve (depth vs accuracy)
3. Horizon decay curve (prediction accuracy vs temporal gap)
4. TUI screenshot (the activation cascade visible)
5. Prediction triangle heatmap (divergence patterns across conditions)

### Novel contributions
1. **Behavioral retrieval:** The spec changes what information the model seeks, not just how it responds
2. **The diff as identity signal:** Continuously measured behavioral delta between with-spec and without-spec
3. **Prediction fulfillment rate:** The spec validates itself through the diffs it creates
4. **The prediction triangle:** Three-way comparison (spec, facts, reality) that trains a self-correcting daemon
5. **Temporal scaling curves:** First measurement of how prediction accuracy scales with behavioral data depth and prediction horizon

### Key references
| Paper | Role in our paper |
|---|---|
| Chhikara et al. (2025) — Mem0 | The recall baseline we compare against |
| Jain et al. (2026) — Sycophancy | The adversary paper — the risk our approach must avoid |
| Hu & Collier (2024) — Persona effect | Closest prior work on measuring persona influence |
| AlpsBench (2026) | "Recall doesn't guarantee alignment" — the gap we fill |
| PersonaGym (2025) | Persona evaluation framework — context for our approach |
| Betley et al. (2026) — Anthropic PSM | Theoretical foundation for why specs change model behavior |
| Sharma et al. (2024) — SycophancyEval | Benchmark for the pathology we must avoid |
| ASPECT (2026) | AI-inferred communication profiles — closest product comparison |

---

## What We Need From The Collective

1. **Is the prediction triangle the right measurement framework?** Spec predicts spec, facts predict you — is the three-way comparison the cleanest way to separate compression value from recall value?

2. **Is the temporal split on 102 sessions sufficient?** We have one primary subject (the founder) with deep data. Is N=1 with deep longitudinal data publishable, or do we need multiple subjects?

3. **How do we handle the sycophancy concern?** The spec might produce responses the person prefers NOT because they're more faithful but because they're more agreeable. How do we mechanically distinguish faithful behavioral reasoning from sycophantic mirroring?

4. **Is the daemon architecture sound?** Watching diffs accumulate, checking prediction fulfillment, detecting drift — is this the right architecture for a self-correcting spec? What are we missing?

5. **What would you cut?** This plan includes: serving layer, diff cascade, Mem0 comparison, prediction triangle, temporal scaling curves, daemon design, benchmark design, and paper outline. What's essential vs what's scope creep?

6. **What's the simplest experiment that proves the thesis?** If we could only run ONE thing, what would it be?

7. **Is "the diff IS the identity signal" a publishable insight or an obvious restatement?** We think it's novel — nobody has proposed measuring identity as the continuous delta between personalized and generic AI behavior. But is this genuinely new, or are we just restating what personalization means?

8. **Does the scaling curve matter?** Is "more sessions → better spec → better predictions, with diminishing returns" an interesting finding, or is it obvious?

9. **Where does this break?** What scenario would disprove the thesis? What kind of person or situation would the spec fail on? What would make the prediction triangle uninformative?

10. **Should we benchmark against PersonaGym or create our own?** PersonaGym's framework was built for thin fictional personas. Our data is deep and real. Feller's concern: "real data, synthetic framework — calling it behavioral doesn't fix the mismatch." Build our own benchmark or adapt theirs?

---

## Implementation Status (S102)

### Built
| Component | File | Status |
|---|---|---|
| Serving engine (diff cascade) | `runners/serving_engine.py` | WORKING |
| Serving TUI (visual debugger) | `runners/serving_tui.py` | WORKING |
| Prediction test (10 decisions, contaminated) | `runners/prediction_test.py` | RAN — 9/10 spec, 6/10 facts (contaminated) |
| Temporal prediction study (clean split) | `runners/temporal_prediction_study.py` | RUNNING — 4 splits, 15 decisions, 3 conditions |
| Routing experiment (embedding, killed) | `runners/routing_experiment.py` | COMPLETE — proved embeddings fail |
| Scraping (waves 9+10) | `runners/scrape_wave9_targets.py`, `scrape_wave10_agentic.py` | COMPLETE — 1,769 files across 15 targets |

### Contaminated Prediction Test (S102, not publishable)
Spec built from ALL data including test decisions. Results inflated.
- Mem0 flat facts: 6/10 (60%)
- Base Layer spec: 9/10 (90%) — contaminated
- Merged: 7/10 (70%) — contaminated

### Clean Temporal Study (S102, running now)
4 temporal splits, spec built from ONLY pre-cutoff facts:
- 2025-06-01: 448 facts → predict 15 decisions
- 2025-10-01: 747 facts → predict 15 decisions
- 2026-01-01: 1,116 facts → predict 12 decisions
- 2026-03-01: 1,484 facts → predict 11 decisions

### Decision Set (pre-registered, 15 decisions from S86-S102)
All selected BEFORE running predictions. Spans: pipeline decisions, integrity decisions, outreach decisions, architectural decisions, prioritization decisions. Includes decisions the founder might regret (D09 — building daemon over higher-priority work).

## Timeline

| Week | Focus |
|---|---|
| Week 1 | Analyze temporal study results. Run TUI demos. Record videos. |
| Week 2 | Add Buffett as second subject (N=2). Run scaling curves. |
| Week 3 | Write paper draft around results. |
| Week 4 | Collective review. Submit to ArXiv. Apply to Emergent Ventures + AI Grant. |

---

## Feller's Questions (Unresolved)

> "Spec predicts itself. Raw facts predict you. Which one's actually you?"

The difference between them. The triangle's shape at any point in time is the identity signal.

> "The spec predicts the spec. What predicts the spec changing?"

The horizon decay curve. When prediction fulfillment drops, the person is changing faster than the spec. The daemon detects this.

> "Real data, synthetic framework — calling it behavioral doesn't fix the mismatch."

Don't use PersonaGym's framework. Build our own evaluation using Twin-2K methodology on temporal-split data with real ground truth.
