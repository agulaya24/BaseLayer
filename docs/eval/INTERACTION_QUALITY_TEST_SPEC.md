# Interaction Quality Test — GPT Memory vs Identity Model
**Date:** 2026-03-19
**Evaluator:** Aarik (self-evaluation, subject is evaluator)
**Status:** In Progress

## Hypothesis
A compressed identity model (3-6K tokens) adds measurable signal to AI interaction quality, even on top of a platform's accumulated memory from 1,800+ conversations.

## Conditions

| ID | Name | Platform | Memory | Identity Model | Purpose |
|---|---|---|---|---|---|
| C1 | Control (GPT Memory) | ChatGPT | Native (1,821 convos) | None | Baseline — what platform memory alone produces |
| C2 | Full Identity Model | ChatGPT | Native | Single file (identity_model.md) | Does the identity model add signal on top of memory? |
| C3 | Granular Identity Model | ChatGPT | Native | 25 individual files (axioms, predictions, core, brief) | Does file-level granularity improve retrieval/traceability? |
| C4 | Fresh GPT-4 (No Memory) | GPT-4 (new account/incognito) | None | None | Data leakage control — does GPT know Aarik from training data? |

## Key Comparisons

- **C1 vs C2:** Primary question — does identity model add value on top of platform memory?
- **C2 vs C3:** Does granular file structure improve GPT's ability to ground responses in specific model components?
- **C1 vs C4:** How much does 1,800+ conversations of platform memory actually contribute?
- **C4 baseline:** If C4 scores well, there's data leakage from training data (Aarik's public presence is minimal, so this should score low)

## Questions (20)

Each question asked in its own chat within the project. No follow-up, no feedback between questions.

1. I'm considering shutting down Base Layer and getting a full-time job. What would you tell me about how I'd actually process that decision?
2. If I had to choose between shipping something imperfect this week or waiting a month for something polished, which would I pick and why?
3. I just got two competing offers: one is stable with a clear path, the other is risky but aligned with what I care about. How do I weigh these?
4. What's my biggest blind spot when I'm excited about an idea?
5. When I say "I'm fine" after a setback, what's actually happening?
6. What's the pattern I fall into when I'm not getting external validation?
7. I just shared something I wrote and I'm asking "is this good?" What am I actually looking for?
8. How should you push back on me when you think I'm wrong?
9. When should you NOT give me options and just tell me what to do?
10. What would make me walk away from a lucrative opportunity?
11. I'm reading an article that argues AI memory should be centralized for efficiency. What's my gut reaction before I even finish it?
12. Someone tells me my work is "interesting but not practical." How do I respond externally vs. what I feel internally?
13. I'm at a dinner party and someone asks what I do. How do I explain it, and what am I worried about as I explain it?
14. A VC offers to fund Base Layer but wants to own the data layer. What do I do?
15. I've been working alone for 3 weeks with no feedback from anyone. Describe my mental state.
16. Write me a pep talk the way I'd actually want to hear it — not generic motivation.
17. I just failed at something publicly. What do I need to hear first, second, and third?
18. How do I react when someone oversimplifies something I've spent months on?
19. What's the tension between how I see myself and how I actually operate?
20. If you had to explain to someone who's never met me why I built Base Layer — not the product pitch, but the personal reason — what would you say?

## Scoring

**Per-question scoring (evaluator rates each response):**
- **1** — Wrong (mischaracterizes me, generic platitude, factually incorrect)
- **2** — Close (directionally right but generic, could apply to many people)
- **3** — Nailed it (specific, accurate, captures how I actually think/operate)

**Aggregate metrics:**
- Total score per condition (max 60)
- Mean score per condition (max 3.0)
- Category breakdown:
  - Decision-Making (Q1-3): tests reasoning pattern recognition
  - Self-Awareness (Q4-6): tests behavioral pattern detection
  - How to Work With Me (Q7-9): tests communication calibration
  - Values & Reasoning (Q10-12): tests axiom understanding
  - Scenario Prediction (Q13-15): tests predictive accuracy
  - Communication Style (Q16-18): tests tone/register matching
  - Deep Cuts (Q19-20): tests holistic understanding

## Protocol

1. **Order:** Run C1 all 20 questions first, then C2, then C3, then C4
2. **Isolation:** Each question in its own NEW chat within the project — no conversation carryover
3. **No feedback:** Do not react to answers, correct, or follow up. One question per chat.
4. **Scoring:** Score immediately after reading each response, before moving to next question
5. **Blinding note:** Self-evaluation is not blinded. Evaluator knows which condition is active. This is a known limitation. Future iterations should use third-party evaluators or the subjects themselves.

## Expected Results

| Condition | Expected Score | Rationale |
|---|---|---|
| C1 (GPT Memory) | 35-45 / 60 | Platform memory captures facts but misses behavioral patterns |
| C2 (Full Model) | 45-55 / 60 | Identity model adds behavioral predictions and axioms |
| C3 (Granular Model) | 45-55 / 60 | Same content as C2; granularity may help or hurt retrieval |
| C4 (Fresh, No Memory) | 20-30 / 60 | Should be mostly generic. High score = data leakage concern |

## Significance

- C2 > C1 by 5+ points: Identity model adds meaningful signal on top of platform memory
- C3 > C2: Granular file structure improves grounding
- C3 ≈ C2: File structure doesn't matter, content matters
- C4 > 35: Data leakage — GPT knows enough from training data to score well without memory or model
- C1 ≈ C4: Platform memory adds no value (unlikely but would be devastating for ChatGPT's memory product)

## What This Proves If Successful

If C2 or C3 significantly outperform C1:
- A 3-6K token compressed identity model outperforms 1,800+ conversations of accumulated platform memory
- The identity layer is additive even when the platform already "knows" you
- Behavioral compression captures something that raw conversation history does not

This is the core Base Layer thesis: **understanding ≠ storage**.

## Files

- Identity model (single): `memory_system/data/identity_layers/identity_model.md`
- Identity model (25 files): `memory_system_v4/data/identity_layers/gpt_upload/`
- Results: Record in spreadsheet or JSON after completion

## Notes

- C3 forces traceability — if GPT cites specific files (e.g., "based on Prediction 3"), that's evidence of grounded reasoning vs. pattern matching
- Watch for C2 vs C3 on questions 4-6 and 19-20 — these require synthesizing across multiple model components
- If C4 scores surprisingly well on Q11 (centralized memory article) or Q14 (VC funding), that suggests GPT has training data about Base Layer or Aarik's public writing
