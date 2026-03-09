# Pipeline Ablation Study Protocol
## Base Layer — Which Steps Actually Matter?

**Status:** DRAFT — Ready for review
**Origin:** Collective Meta-Review Issue #3 (S77+, 2026-03-07)
**Pattern:** Autoresearch-style autonomous experiment loop (Karpathy, March 2026)
**Cost estimate:** ~$15-25 total across all conditions
**GPU required:** No — API calls only

---

## Motivation

The Collective meta-review (71/100) identified "no pipeline ablation study" as the #1 actionable research issue. The 14-step pipeline has never been tested for which steps are load-bearing vs ceremonial. This study answers:

1. **What's the minimal viable pipeline?** — Fewest steps that produce an acceptable brief
2. **Which steps are load-bearing?** — Removing them degrades quality measurably
3. **Which steps are ceremonial?** — Removing them has no measurable effect
4. **Is the Collective review theatrical?** — Does adversarial review actually improve briefs?
5. **Does enrichment justify its cost?** — Scoring, classification, tiering — are they earning their API spend?

---

## Pipeline Steps & Dependencies

```
STEP 1:  IMPORT         — Raw text → SQLite                    [REQUIRED — no input without it]
STEP 2:  EXTRACT         — Text → structured facts (Haiku API)  [REQUIRED — no facts without it]
STEP 3:  EMBED           — Facts → 384-dim vectors (local)      [Enables: SCORE, CONTRADICTIONS, CONSOLIDATE, ASSEMBLE]
STEP 4:  SCORE           — Recurrence + depth scoring            [Enables: TIER candidate ranking]
STEP 5:  CLASSIFY        — fact_type + commitment_depth (Haiku)  [Enables: TIER routing, AUTHOR fact selection]
STEP 6:  TIER            — knowledge_tier assignment (Sonnet)    [Enables: AUTHOR identity-tier filtering]
STEP 7:  CONTRADICTIONS  — Detect + resolve contradictions       [Enables: CONSOLIDATE]
STEP 8:  CONSOLIDATE     — Union-find clustering + dedup         [Cleans fact base for AUTHOR]
STEP 9:  ANCHORS         — Extract epistemic axioms              [Optional — manual step, not in `baselayer run`]
STEP 10: AUTHOR LAYERS   — Generate 3 layers (Sonnet)           [REQUIRED — compose needs layers]
STEP 11: COLLECTIVE      — 4-persona adversarial review (Opus)   [Optional — `--no-review` flag]
STEP 12: COMPOSE         — 3 layers → unified brief (Opus)      [REQUIRED — brief is the artifact]
STEP 13: ASSEMBLE        — Brief + theme + episode → injection   [Runtime only, not evaluated here]
STEP 14: SERVE           — MCP server                            [Runtime only, not evaluated here]
```

**Truly required:** IMPORT (1), EXTRACT (2), AUTHOR LAYERS (10), COMPOSE (12)
**Skippable candidates:** EMBED (3), SCORE (4), CLASSIFY (5), TIER (6), CONTRADICTIONS (7), CONSOLIDATE (8), ANCHORS (9), COLLECTIVE (11)

---

## Experimental Design

### Subject
**Franklin** — primary subject for all conditions.
- Cheapest to run (212 active facts, 135 identity-tier)
- Has existing eval data (BCB, SRS, Collective scores)
- Well-understood behavioral patterns from autobiography
- Brief already validated at 73-82/100

### Metric Battery

Each condition produces a brief. Each brief is evaluated on **4 independent metrics**:

| # | Metric | Type | Cost | What it measures |
|---|---|---|---|---|
| M1 | **Collective Score** | LLM judge (Opus) | ~$0.45/run | 4-persona quality assessment (0-100) |
| M2 | **Blind Pairwise** | LLM judge (Opus) | ~$0.30/pair | "Which brief better captures this person?" vs baseline |
| M3 | **Pattern Coverage** | Mechanical ($0) | Free | Count of distinct behavioral patterns, axioms, predictions |
| M4 | **Brief Diagnostics** | Mechanical ($0) | Free | Token count, section count, pronoun consistency, thin-data acknowledgment |

**M1 (Collective Score):** Run `collective_review_layer()` on each brief with `layer_name="unified_brief"`. Same prompt/model/temperature as production. Scores: cognitive_scientist, narrative_biographer, epistemologist, pragmatic_engineer, combined.

**M2 (Blind Pairwise):** Present baseline brief (Condition 0) and test brief to Opus. Randomize order. Ask: "Which brief more faithfully and usefully captures this person's identity? Explain which is better and why." Score: Win/Lose/Tie per pair.

**M3 (Pattern Coverage):** Parse each brief for:
- Number of behavioral patterns (sentences with "when...they..." or situational triggers)
- Number of explicit axioms/beliefs
- Number of predictions/directives
- Number of acknowledged limitations/thin-data markers
- Number of contradictions/tensions preserved

**M4 (Brief Diagnostics):** Automated checks:
- Character count, estimated token count
- Section count (paragraph breaks as proxy)
- Pronoun consistency (they/them vs she/her vs he/him)
- Presence of key structural elements (failure modes, thin data disclaimer, etc.)

### Conditions

#### Downward Ablation (remove one group at a time from full pipeline)

| ID | Condition | Steps Run | Steps Skipped | What it tests |
|---|---|---|---|---|
| **C0** | Full pipeline (baseline) | 1-12 | None | Baseline quality |
| **C1** | No Collective review | 1-10, 12 | 11 | Is adversarial review theatrical or load-bearing? |
| **C2** | No contradictions/consolidation | 1-6, 9-12 | 7, 8 | Does quality control on facts improve the brief? |
| **C3** | No scoring | 1-3, 5-12 | 4 | Does recurrence/depth scoring help tiering? |
| **C4** | No anchors step | 1-8, 10-12 | 9 | Do explicit axioms improve the brief? |
| **C5** | No tiering (all facts = identity) | 1-5, 7-12 | 6 | Does Sonnet tiering add value, or can we use all facts? |
| **C6** | No classification | 1-4, 6-12 | 5 | Does fact_type/commitment_depth help authoring? |
| **C7** | No enrichment block | 1-2, 10-12 | 3-9 | Can we go straight from raw facts to authoring? |

#### Upward Construction (build from minimal)

| ID | Condition | Steps Run | What it tests |
|---|---|---|---|
| **C8** | Minimal: EXTRACT → COMPOSE | 1-2, 12 | Can Opus compose a brief from raw facts alone? |
| **C9** | + CLASSIFY + TIER | 1-2, 5-6, 12 | Does classification + tiering help without scoring? |
| **C10** | + EMBED + SCORE | 1-6, 12 | Full enrichment but no quality control, no layers |
| **C11** | + AUTHOR LAYERS (no review) | 1-6, 10, 12 | Standard pipeline minus quality control and review |

#### Composition Variants (same facts, different compose approach)

| ID | Condition | Compose Method | What it tests |
|---|---|---|---|
| **C12** | Direct fact injection | Skip AUTHOR, give all identity facts to Opus directly | Do intermediate layers (ANCHORS/CORE/PREDICTIONS) add value? |
| **C13** | Single-layer compose | Author one combined layer, no 3-layer split | Does the 3-layer architecture matter? |

**Total conditions:** 14 (including baseline)

---

## Execution Protocol

### Phase 1: Setup (one-time)

1. **Snapshot Franklin's current database state.** Copy `franklin_memory/data/database/memory.db` as reference.
2. **Record baseline brief.** Save current `brief_v4.md` as `C0_baseline_brief.md`.
3. **Create results tracking file:** `ablation_results.tsv`

```
condition	collective_score	cs	nb	ep	pe	pairwise_vs_c0	pattern_count	axiom_count	prediction_count	char_count	token_est	cost	notes
```

### Phase 2: Run Conditions

For each condition C0-C13:

1. **Reset environment.** Restore Franklin database to snapshot. Clear generated layers.
2. **Run pipeline with specified steps only.** Use CLI flags or direct script calls.
3. **Capture the generated brief.** Save as `C{N}_brief.md`.
4. **Run M1 (Collective Score).** Record all 4 persona scores + combined.
5. **Run M3 + M4 (mechanical metrics).** Parse brief for patterns, counts, diagnostics.
6. **Log to results.tsv.**

After all conditions complete:
7. **Run M2 (Blind Pairwise).** Compare each condition's brief against C0 baseline. 13 comparisons.

### Phase 3: Analysis

1. **Rank conditions by Collective Score.** Identify quality tiers.
2. **Identify load-bearing steps.** Steps whose removal drops score >5 points from baseline.
3. **Identify ceremonial steps.** Steps whose removal drops score <2 points or improves it.
4. **Find minimal viable pipeline.** Cheapest condition that scores within 5 points of baseline.
5. **Cost-quality frontier.** Plot each condition's cost vs quality. Identify the Pareto-optimal set.

---

## Implementation Notes

### How to Skip Steps

| Step | How to skip |
|---|---|
| EMBED (3) | Don't run `baselayer embed`. Facts remain unembedded. |
| SCORE (4) | Don't run `baselayer score`. Facts keep default scores (0). |
| CLASSIFY (5) | Don't run `baselayer classify`. Facts keep NULL fact_type/commitment_depth. |
| TIER (6) | Don't run `baselayer tier`. All facts stay at 'context' tier. Need SQL override: `UPDATE memory_facts SET knowledge_tier='identity'` |
| CONTRADICTIONS (7) | Don't run `baselayer contradictions`. No superseded_by markers. |
| CONSOLIDATE (8) | Don't run `baselayer consolidate`. Duplicate facts remain. |
| ANCHORS (9) | Don't run `baselayer anchors`. No epistemic_anchors table entries. |
| COLLECTIVE (11) | Use `--no-review` flag on `baselayer author`. |
| AUTHOR LAYERS (10) | For C8/C12: pass all identity facts directly to compose prompt. |

### Special Conditions

**C7 (No enrichment block):** All facts at default scores, no classification, no tiering. Must SQL-promote all facts to identity tier for authoring to work: `UPDATE memory_facts SET knowledge_tier='identity' WHERE superseded_by IS NULL`.

**C8 (Minimal):** Skip AUTHOR LAYERS entirely. Modify compose step to accept raw facts instead of layers. This tests whether the 3-layer intermediate representation adds value.

**C12 (Direct fact injection):** Same as C8 but with classified + tiered facts. Tests whether AUTHOR LAYERS → COMPOSE is better than FACTS → COMPOSE.

**C13 (Single-layer compose):** Modify author_layers to generate one combined layer instead of separate ANCHORS/CORE/PREDICTIONS. Tests the D-043 architectural decision.

---

## Cost Estimate

| Component | Per condition | Total (14 conditions) |
|---|---|---|
| Pipeline steps (Haiku + Sonnet) | ~$0.10-0.50 | ~$3-7 |
| AUTHOR LAYERS (Sonnet generation) | ~$0.10 | ~$1.00 |
| COMPOSE (Opus) | ~$0.15 | ~$2.10 |
| M1: Collective Score (Opus) | ~$0.45 | ~$6.30 |
| M2: Blind Pairwise (Opus) | ~$0.30 | ~$3.90 (13 pairs) |
| M3 + M4: Mechanical | $0 | $0 |
| **Total** | | **~$16-20** |

Note: Conditions that skip steps cost less. C8 (minimal) costs ~$0.60 total. C0 (full) costs ~$1.50.

---

## Expected Outcomes

### Hypotheses (pre-registered)

| # | Hypothesis | If confirmed | If rejected |
|---|---|---|---|
| H1 | Removing COLLECTIVE (C1) drops score <3 points | Review is ceremonial — remove from MVP | Review is load-bearing — keep |
| H2 | Removing CONTRADICTIONS+CONSOLIDATE (C2) drops score <3 points | Quality control has minimal impact on small corpora | Quality control matters even at N=212 facts |
| H3 | Removing SCORE (C3) drops score >5 points | Scoring is load-bearing — significance matters | Scoring is ceremonial — all facts are roughly equal |
| H4 | No enrichment (C7) scores within 10 points of baseline | Enrichment is mostly ceremony — Opus can handle raw facts | Enrichment is essential — raw facts produce poor briefs |
| H5 | Minimal pipeline (C8) scores >60 | Opus composing directly from facts is viable MVP | Intermediate layers are essential |
| H6 | Direct fact injection (C12) scores within 5 points of C0 | 3-layer architecture is unnecessary complexity | 3-layer architecture genuinely helps |
| H7 | The Pareto-optimal pipeline has ≤8 steps | Current pipeline is overengineered by ~40%+ | Current pipeline is close to optimal |

### Decision Matrix

| Outcome | Action |
|---|---|
| C1 ≈ C0 | Remove Collective from default pipeline. Offer as optional `--review` flag. |
| C7 ≈ C0 | Enrichment block is ceremony. Redesign as optional quality pass. |
| C8 > 60 | Ship minimal pipeline as "quick mode" (`baselayer run --quick`). |
| C12 ≈ C0 | Eliminate 3-layer architecture. Compose directly from facts. |
| All conditions < C0 by >5 | Every step is load-bearing. Pipeline justified. |

---

## Relationship to Other Work

- **Meta-review issue #3:** This study directly answers the ablation gap.
- **Meta-review issue #8:** C1 vs C0 specifically tests whether Collective is theatrical.
- **Stacking Study (Tier 1):** Ablation findings determine which pipeline to use for stacking benchmarks.
- **MVP question:** The minimal viable condition becomes the basis for "quick mode" or Tier 1 product.
- **Cost optimization:** If enrichment is ceremonial, per-user cost drops from ~$0.50-3.00 to ~$0.15-0.50.

---

## Reproducibility

All ablation runs must save:
1. Database snapshot (pre-run state)
2. Generated brief (`C{N}_brief.md`)
3. Collective review JSON
4. Pairwise comparison response
5. Mechanical metric outputs
6. Pipeline step timings and API costs
7. This protocol document

Output directory: `docs/eval/ablation/`
