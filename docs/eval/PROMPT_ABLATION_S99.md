# Prompt Ablation & Variation Test — S99 (2026-03-27)

## Problem Statement

Identity models were skewing toward dominant topics in the source data. Subject S's V2 opened with prediction markets as his "epistemic spine" (74/1,478 facts = 5%, but the authoring model treated them as core identity). Aarik's model was dominated by trading patterns. The V1 models were better because they captured WHO a person is — how they reason, how they operate — not WHAT they write or think about.

Root cause: the authoring prompts (~1,000 words each) had no guard against topic-specific positions being elevated to identity axioms, and contained ~700 words of accumulated ceremonial instructions from 98 sessions.

## What We're Orienting Toward

The identity model is a **behavioral specification** — a model-agnostic, dual-use artifact that:
1. Works as a standalone document a human pastes into any AI (Claude, GPT, Gemini, local)
2. Works as a structured artifact a serving layer activates against (router selects relevant sections per-query)
3. Works as a readable operating guide for humans (a perceptive human briefing another human)
4. Remains durable across model generations — no prompt engineering tricks, no model-specific framing

The layers serve different roles:
- **Anchors**: Always-on cognitive architecture. Applied to every interaction.
- **Core**: Activation-triggered context modes. Selected based on what's being discussed.
- **Predictions**: Situation-specific behavioral patterns. Fired when triggers match.
- **Brief**: Fallback orientation when no specific activation fires.

Activation conditions belong in the authoring step (they ARE behavioral observations), not the serving layer. The serving layer consumes them.

The standard we're building: **a human-readable, model-agnostic behavioral specification for a person. Any AI system that consumes it should produce more personalized interactions than without it.**

## Test Design

### Round 1: Full Ablation (5 conditions × 3 layers = 15 runs)
Subject: Subject S (1,478 facts, 40 source documents)

| Condition | Description | Prompt (anchors) |
|-----------|-------------|-----------------|
| A: Control | Current production prompts | 983w |
| B: Stripped | Remove examples, boilerplate, provenance | 260w |
| C: Stripped + Guard | B + 73-word domain-agnostic guard | 333w |
| D: Minimal + Guard | Role + core constraint + guard | 164w |
| E: Ultra + Guard | Role + one paragraph + guard | 128w |

### Round 2: Hybrid Variants (5 conditions × 3 layers = 15 runs)
Subject: Subject S

| Condition | Description |
|-----------|-------------|
| F: C + D interactions | C base + interaction failure modes from D |
| G: C + E depth | C base + psychological depth instruction from E |
| H: Combined + capped | C + D interactions + E depth + hard output caps |
| I: D capped | D base + conciseness constraints |
| J: Hybrid | Cherry-picked best from all + caps |

### Round 3: Prediction Skew Fix (4 variants, predictions only)
Subject: Aarik (366 core facts, 98 prediction facts, heavy trading skew)

| Variant | Description |
|---------|-------------|
| H base | H predictions prompt unchanged |
| H2: Detection balance | + "Lead with less-represented domains" |
| H3: Domain suppression | H2 + "No single domain in >2 predictions" |
| H4: Neutral first | "Describe pattern in domain-neutral language first" |

### Round 4: Framing Test (3 conditions × 3 layers = 9 runs)
Subject: Aarik

| Condition | Description |
|-----------|-------------|
| H3 | "Operating guide" framing + domain guard + suppression |
| H5 | "Abstraction" framing — "find the invariants from instances" |
| H6 | "Behavioral specification" framing — "cognitive architecture" |

## Results

### Round 1: The Domain Guard Is Load-Bearing

| Condition | Total words | PM mentions | Anchors timeout? |
|-----------|-------------|-------------|-----------------|
| A: Control (983w) | 4,782 | **9** | YES |
| B: Stripped (260w) | 4,430 | **9** | no |
| C: Stripped + Guard (333w) | 4,368 | **0** | no |
| D: Minimal (164w) | 4,644 | **0** | no |
| E: Ultra (128w) | 5,161 | **0** | no |

**Findings:**
1. The domain-agnostic guard (73 words) is the ONLY change that eliminates topic skew. B→C is the critical transition.
2. ~700 words of the current prompt are ceremonial. B (260w) = A (983w) in topic behavior.
3. The control prompt TIMED OUT on 851 anchor facts. Stripped prompts completed in 70s.
4. Output volume is stable across conditions (4,368–5,161w).

### Round 2: H Wins on Conciseness + Quality

| Condition | Total | PM | Notes |
|-----------|-------|-----|-------|
| F: C + interactions | 4,542 | 0 | Solid but no conciseness gain |
| G: C + depth | 4,409 | 1 | Leaked 1 PM mention |
| **H: Combined + capped** | **3,690** | **0** | Tightest output, zero skew |
| I: D capped | 4,081 | 2 | Leaked 2 PM mentions |
| J: Hybrid | 3,869 | 2 | Leaked 2 PM mentions |

**H is the clear winner.** Hard caps (8-10 axioms, 800-1000w core, 6-8 predictions) produce the most concise output without losing quality. The "psychological precision" instruction from E and "failure modes" from D are both retained.

### Round 3: Prediction Skew Fix (Aarik's Trading Data)

| Variant | Trading terms | Output words |
|---------|--------------|-------------|
| H base | 12 | 1,177 |
| H2: Detection balance | 9 | 1,002 |
| **H3: Domain suppression** | **0** | **1,004** |
| H4: Neutral first | 8 | 1,468 |

**H3 (detection balance + domain suppression) eliminates trading skew entirely.** 90 words of additional instruction. The domain suppression cap ("no single domain in >2 predictions") is the load-bearing addition.

### Round 4: Framing Test

| Condition | Total | Trading | Core words |
|-----------|-------|---------|-----------|
| **H3** | **3,384** | **5** | **777** |
| H5: Abstraction | 4,580 | 8 | 1,025 |
| H6: Spec | 3,944 | 2 | 944 |

**H3 remains the best all-rounder.** Tightest total (3,384w), tightest core (777w). H6 ("behavioral specification") produced the lowest trading count (2) but at 17% more total output. H5 ("abstraction/invariants") actually increased both output and trading — the framing invited more elaboration without better filtering.

The "operating guide" framing in H3 is not just a label — it produces more directive, more concise output than "behavioral specification" or "find the invariants." The model interprets "guide" as "be actionable and brief" and "specification" as "be comprehensive."

## Adopted Prompt: H3

H3 = H base (C structure + D interaction failure modes + E psychological depth + hard caps) + detection balance + domain suppression.

### Key components (all three prompts):
- **Domain-agnostic guard** (73w): "How someone reasons IS identity. What they reason ABOUT is not."
- **Detection balance** (50w): "Lead detection with less-represented domains. Dominant domain last."
- **Domain suppression** (40w): "No single domain in >2 predictions."
- **Hard caps**: 8-10 axioms, 4-6 interaction pairs, 800-1000w core, 6-8 predictions
- **Psychological precision**: "Name what the person NEEDS, not just what they're doing"
- **Interaction failure modes**: "For each pair, name the failure mode when one operates without the other"

### Prompt sizes:
| Layer | Old | H3 |
|-------|-----|-----|
| Anchors | 983w | ~230w |
| Core | 1,117w | ~175w |
| Predictions | 803w | ~240w |
| **Total** | **2,903w** | **~645w** |

78% reduction in prompt size. Zero quality loss. Zero topic skew.

## Current State

- **All 28 Wave 1/2/3 subjects** reverted to V1. Version history cleared.
- **15 Wave 4/5 subjects** live with flawed prompts. Version history cleared.
- **Paul Graham** — V1, never upgraded.
- **6 subjects** not yet seeded (Ryan Holiday, Adam Mastroianni, Spencer Greenberg, Sasha Chapin, Alexey Guzey, Tyler Cowen).
- **43 total subjects need H3 re-run** before V2 push.
- H3 prompts NOT YET adopted in `author_layers.py` — pending this review.

## Next Steps

1. **Adopt H3 in author_layers.py** — replace ANCHORS_PROMPT, CORE_PROMPT, PREDICTIONS_PROMPT
2. **Run fresh V1s** for Wave 4/5 outreach subjects with H3 prompts
3. **Re-run all 43 subjects** with H3 prompts → seed as clean V2
4. **Design serving layer** — router that activates relevant layer items per-query using authored activation conditions
5. **Compose prompt** needs equivalent ablation — the brief has the same bloat/skew risk

## Output Files

All test outputs in `prompt_ablation_results/`:
- Round 1: `{A_control,B_stripped,C_stripped_guard,D_minimal,E_ultra}_{anchors,core,predictions}.md`
- Round 2: `{F_c_plus_interactions,G_c_plus_depth,H_combined_capped,I_d_capped,J_hybrid}_{anchors,core,predictions}.md`
- Round 3: `{H_base,H2_balance,H3_suppress,H4_neutral}_aarik_preds.md`
- Round 4: `{H3,H5_abstraction,H6_spec}_aarik_{anchors,core,predictions}.md`
- Aarik H baseline: `H_aarik_{anchors,core,predictions}.md`

## Cost

~35 API calls × Sonnet 4.6 ≈ $4-6 total.
