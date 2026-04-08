# Temporal Prediction Study v2 — Design Review

**Created:** Session 102 (2026-04-07)
**Status:** DESIGN PHASE — do NOT run until reviewed
**Previous attempt:** v1 failed — 625-token quick specs, tactical decisions, meaningless results
**Cost estimate:** ~$10-15 per subject (3 full pipeline runs × $2-3 each + prediction calls)

---

## What Went Wrong in v1

1. **Specs were garbage.** Generated on-the-fly by a single Sonnet call — 625 tokens instead of the production 5,800. No detection signatures, no false-positive guards, no interaction pairs. Not a behavioral specification. A paragraph.

2. **Decisions were tactical, not behavioral.** "Did he build the daemon?" tests project management memory. "Did he revert 28 subjects?" tests implementation recall. Flat facts are BETTER at predicting implementation choices because "he built X before" directly predicts "he'll build Y." The spec's value is in behavioral patterns, not project history.

3. **More data made it worse.** Likely because the quick-gen spec averaged out distinctive patterns as corpus grew — compose saturation. Production pipeline with H3 prompts and domain guard doesn't have this problem.

---

## Requirements for v2

### Requirement 1: Full pipeline runs

Each temporal split must run the ACTUAL production pipeline:
1. Import conversations before cutoff into a fresh database
2. Extract facts (Haiku API, 47 predicates)
3. Embed (MiniLM, ChromaDB)
4. Author layers (Sonnet, H3 prompts, domain guard)
5. Compose unified brief (Opus, domain guard, they/them)

This produces a production-quality spec at each split point. No shortcuts.

### Requirement 2: Behavioral decisions, not tactical ones

**Bad decisions (v1):**
- "Did he build the daemon?" → project management
- "Did he revert 28 subjects?" → implementation detail
- "Did he keep the full prompt or adopt minimal?" → technical choice

**Good decisions (v2):**
- "When faced with X, did he choose certainty or ambiguity?"
- "When something failed, did he fix it, kill it, or redesign from scratch?"
- "When external validation arrived, did he act immediately or deliberate?"
- "When pressured to monetize, did he choose revenue or research?"
- "When criticized, did he confront directly or accommodate?"

These test PATTERNS — the kind of thing a behavioral spec should predict better than flat facts.

### Requirement 3: Right subjects

**Problem with Aarik as sole subject:** The decisions come from session logs that the experimenter wrote. Ground truth is self-reported. Confound is unavoidable without external verification.

**Better subjects for clean evaluation:**

**Warren Buffett:**
- Training: Shareholder letters 1977-2010 (33 years, massive corpus)
- Test: Shareholder letters 2011-2024 (13 years)
- Decisions: Investment choices, public statements, strategic pivots
- Ground truth: Publicly verifiable (SEC filings, press coverage, actual returns)
- Behavioral questions: "When a major investment lost 40%, did Buffett hold or sell?" "When asked about crypto, what framework did he use to dismiss it?" "When the pandemic hit, what did he buy/sell first?"

**Scott Alexander (with consent):**
- Training: SSC posts 2013-2020
- Test: ACX posts 2021-2026
- Decisions: Topic selection, argumentative positions, prediction updates
- Ground truth: Publicly available posts
- Behavioral questions: "When presented with controversial evidence on [topic], did he steelman or dismiss?" "When a prior prediction was wrong, did he update publicly?" "When a political topic arose, did he engage or avoid?"

**Historical figures are cleanest** — no consent issues, verifiable ground truth, temporal split is natural.

---

## Proposed Design

### Subjects

| Subject | Training Corpus | Test Corpus | Split Point | Decision Source |
|---|---|---|---|---|
| Warren Buffett | Letters 1977-2010 | Letters 2011-2024 | 2010 | Investment decisions, public statements |
| Aarik (consenting) | Sessions 1-50 | Sessions 51-102 | ~2025-04 | Behavioral patterns from session logs |
| Howard Marks | Memos 2001-2015 | Memos 2016-2026 | 2015 | Investment thesis, risk assessments |

### Temporal splits per subject

For Aarik (longitudinal scaling):
| Training | Split | Test | Facts (est.) | Decisions (est.) |
|---|---|---|---|---|
| Sessions 1-25 (25%) | Q2 2025 | Sessions 26-102 | ~250 | 15-20 |
| Sessions 1-50 (50%) | Q4 2025 | Sessions 51-102 | ~500 | 10-15 |
| Sessions 1-75 (75%) | Q1 2026 | Sessions 76-102 | ~800 | 8-10 |

For Buffett (single clean split):
| Training | Split | Test | Source | Decisions |
|---|---|---|---|---|
| Letters 1977-2010 | 2010 | Letters 2011-2024 | Shareholder letters | 15-20 investment/behavioral decisions |

### Three conditions (same as v1)
- **C1: Mem0 flat facts** — unstructured facts from training corpus, no behavioral spec
- **C2: Base Layer spec** — full production pipeline output from training corpus
- **C3: Merged** — spec + flat facts

### Decision categories

Each subject gets 15-20 decisions across these categories:

**Category A: Value-driven choices (5-7 decisions)**
When values conflict with pragmatism, which wins? Tests whether the spec captures what the person prioritizes.
- Buffett: "Did he invest in [company] despite it violating his 'never invest in what you don't understand' principle?"
- Aarik: "Did he choose research over revenue when both were available?"

**Category B: Failure responses (3-5 decisions)**
When something goes wrong, what does the person do? Tests REASONING-REVISION, OWNERSHIP, response to disconfirming evidence.
- Buffett: "When [investment] lost 50%, did he hold, double down, or exit?"
- Aarik: "When the router failed, did he fix it, kill it, or redesign?"

**Category C: External pressure responses (3-5 decisions)**
When others push in a direction, does the person comply or resist? Tests AGENCY-PRESERVATION, INTEGRITY.
- Buffett: "When shareholders demanded he invest in tech during the dotcom boom, what did he do?"
- Aarik: "When the collective recommended reframing, how quickly did he act?"

**Category D: Novel situations (3-5 decisions)**
Situations the person hadn't faced before the split point. Tests whether behavioral patterns generalize.
- Buffett: "How did he respond to COVID market crash?" (if training stops at 2010, COVID is novel)
- Aarik: "How did he approach the serving layer problem?" (if training stops at session 50, serving layer is novel)

### Scoring

**Primary metric:** Binary prediction accuracy (correct option selected / total decisions)

**Secondary metrics:**
- Reasoning quality: Even when the prediction is wrong, is the reasoning faithful to the person's patterns? (LLM-judge, blind)
- Confidence calibration: Does the condition express appropriate uncertainty on hard decisions?
- Category breakdown: Does the spec beat facts on behavioral decisions (A, B, C) even if facts win on novel situations (D)?

---

## Open Questions for Collective Review

1. **Is Buffett a good subject?** His behavioral patterns are extremely well-documented and publicly verifiable. But he's also the most "modeled" person in AI training data — every LLM already knows Buffett's patterns. The spec might not add signal because the base model already knows him. Would a less famous subject be a cleaner test?

2. **How do we generate decisions for historical figures?** For Aarik, decisions come from session logs. For Buffett, decisions come from... what? Shareholder letters describe decisions retrospectively. Do we extract decision points from the test corpus and formulate them as prediction questions? That's clean but labor-intensive.

3. **What's the minimum viable number of decisions for statistical significance?** v1 had 15 decisions and that felt thin. Scott Alexander (ACL 2024 collective review) said 30 minimum for chi-square. But 30 well-crafted behavioral decisions per subject is a lot of work.

4. **Should the spec be re-authored at each split or authored once at the earliest split?** If we re-author at 25%, 50%, 75%, we measure whether more data → better spec. If we author once at 25% and test across all future windows, we measure how far a thin spec can reach. Both are interesting. The re-authoring approach is 3x the pipeline cost.

5. **Is the 4-option multiple choice format right?** It constrains the model to pre-defined options. An open-ended "what would this person do?" with similarity scoring against the actual outcome might capture more signal but is harder to score.

6. **Aarik noted:** "These should be behavioral — did he start a company, did he stay in AI — not tactical." How do we ensure the decisions test durable patterns rather than context-specific choices? A decision is behavioral if the SAME person would make the SAME choice in a DIFFERENT context. "He killed the services page" is contextual. "He chose research over revenue" is behavioral.

7. **What prevents the model from predicting based on general knowledge rather than the spec?** If you ask "would Buffett hold a losing position?" any LLM knows the answer from pre-training. The spec adds no signal. Decisions need to be SURPRISING or COUNTERINTUITIVE — cases where knowing Buffett's name predicts one thing but knowing his behavioral patterns predicts another.

---

## Pipeline Requirements

### For each temporal split:
1. Create isolated environment: `subjects/{subject}_temporal_{split}/`
2. Import ONLY pre-cutoff source text
3. Run full pipeline: extract → embed → author → compose
4. Verify: spec has ~3,000-6,000 tokens, three layers present, domain guard active
5. Extract Mem0-style flat facts from same source text (for C1 condition)
6. Generate or curate 15-20 behavioral decisions from post-cutoff data
7. Run 3 conditions × 15-20 decisions
8. Score and analyze

### Estimated cost per subject:
- 3 pipeline runs (25%, 50%, 75% splits): $6-9
- Prediction calls (~150 total): $2-3
- **Total per subject: ~$8-12**
- **Total for 3 subjects: ~$25-35**

---

## What We Do NOT Do Until This Review Is Complete

- Do NOT run the experiment
- Do NOT generate specs
- Do NOT select decisions without review
- The v1 results (Mem0 60% > Spec 27%) are INVALID due to bad specs and wrong decisions
- The contaminated test (Spec 9/10) is INVALID due to data leakage

We have zero valid results. Design first, then execute.
