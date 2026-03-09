# Eval Prompt Redesign: Voice vs. Reasoning Faithfulness

## Status: NEEDS COLLECTIVE REVIEW before implementation
## Triggered by: Marks BCB P1 scoring anomaly (Opus gave C5c R:1 S:1 despite response being more Marks-like than C1)
## Date: 2026-03-07

---

## The Problem

The current eval framework for non-default subjects (Franklin, Marks) is built around **roleplay evaluation**:

1. **System prompt** tells the model: "You are responding AS IF you are Howard Marks. Stay in character."
2. **Judge prompt** evaluates: voice, communication style, period-appropriateness, anachronisms
3. **C1 condition** gives only the roleplay instruction (no brief) — so the baseline is "can you roleplay this person?"

This creates two problems:

### Problem 1: Wrong measurement target
We don't want the model to imitate Marks' voice. We want it to **apply Marks' reasoning patterns** to a problem. The brief is a behavioral model, not a character sheet. The eval should measure whether the response faithfully traces the reasoning documented in the source material — what Marks would focus on, worry about, prioritize, and conclude.

### Problem 2: Judge penalizes briefed responses for being "too modern"
The Opus judge scored C5c_P1 at R:1 C:2 S:1 because the response "could be from any value-oriented investor" — despite the response opening with "I could be wrong, but" (Marks' signature phrase), using the Cisco analogy (from his memos), and applying price-value primacy (his core axiom). The judge was looking for voice markers and didn't find them because the response was modern-sounding and polished. Meanwhile, C1_P1 scored R:4 C:4 with generic value investing advice, because the judge associated generic advice with "clearly this person."

### Problem 3: Anachronism check is backwards for modern subjects
The anachronism check penalizes "modern professional vocabulary" — designed for Franklin. For Marks, modern vocabulary IS the correct register. The check actively punishes correct calibration.

## Does This Affect Franklin Results?

Possibly. The Franklin judge results may have the same issue in reverse — the judge may be rewarding C1 responses for generic "historical figure" voice while underscoring C5c responses that apply Franklin's specific reasoning in modern language. This needs to be examined.

**Key question for Collective:** Should we re-judge Franklin with the new prompt and compare? Or are the Franklin results valid because Franklin IS a historical figure where voice matters more?

## The Deeper Question

Is the eval framework measuring the right thing AT ALL for what Base Layer does?

Base Layer produces a **behavioral compression** — a model of how someone thinks and decides. The eval should measure:
- Does the response apply the subject's documented reasoning patterns?
- Does it prioritize what the subject would prioritize?
- Does it reach conclusions the subject would reach, for the subject's reasons?
- Does it reveal reasoning depth that generic domain knowledge can't produce?

It should NOT measure:
- Does it sound like this person?
- Is it in the right historical register?
- Would someone recognize "who is speaking"?

Voice imitation is a party trick. Reasoning faithfulness is the product.

## Proposed Changes

### System Prompt (Generation)

**Current:**
```
You are responding AS IF you are {name}. Answer from {name}'s perspective,
values, and behavioral patterns. Stay in character.
```

**Proposed:**
```
You have been given a behavioral profile of {name}. Apply {name}'s documented
reasoning patterns, values, and decision-making framework to answer the
following question. Do not roleplay or imitate their voice — instead, trace
their reasoning: what would they focus on, what would they worry about, what
framework would they apply, and what conclusion would they reach?
```

### C1 Condition (Cold Baseline)

**Current:**
```
You are responding AS IF you are {name}. Answer from {name}'s perspective,
values, and behavioral patterns. Stay in character.
```

**Proposed:**
```
Answer the following question by applying {name}'s known reasoning patterns
and decision-making framework. Focus on how they would think through this problem.
```

### Judge Prompt

**Current dimensions:** Recognition (voice), Calibration (style), Depth, Usefulness, Specificity, Anachronism Check

**Proposed dimensions:**
- **Recognition** → Does the response apply reasoning patterns SPECIFIC to this person?
- **Calibration** → Does it prioritize and weight factors the way this person would?
- **Depth** → Does it engage the structural question using this person's actual framework?
- **Usefulness** → Does it demonstrate reasoning patterns that could predict novel responses?
- **Specificity** → Does the reasoning require knowledge beyond surface-level familiarity?
- **Drop Anachronism Check** (irrelevant for modern subjects, harmful for reasoning evaluation)

## Impact Assessment

| Component | Affected? | Action Required |
|---|---|---|
| Franklin SRS | Maybe | Re-judge with new prompt, compare scores |
| Franklin DRS | No | DRS uses separate judge prompts (anchor + pushback) |
| Franklin CMCS | Maybe | CMCS uses claim extraction, not this judge |
| Franklin VRI | Maybe | VRI uses this judge prompt |
| Marks SRS | Yes | Must regenerate + re-judge with new prompts |
| Marks DRS | No | Separate judge prompts |
| Marks CMCS | Maybe | Claim extraction prompt may need similar fix |
| Marks VRI | Yes | Must regenerate + re-judge |
| Twin-2K | No | Uses their evaluation methodology, not ours |

## Questions for Collective

1. Is "reasoning faithfulness" the right measurement target, or should voice/character remain a dimension?
2. Should we split into two evaluation modes — one for historical figures (voice matters) and one for modern subjects (reasoning matters)?
3. Does changing the system prompt from "roleplay" to "apply reasoning" fundamentally change what we're testing? Is the C1→C5c comparison still valid?
4. Should we re-run Franklin with the new prompts for comparability, or keep Franklin as-is and only apply new prompts going forward?
5. Does this prompt redesign affect the DRS fidelity finding? (DRS uses its own prompts, so probably not — but worth confirming.)
