# Serving Layer Eval: Identity Context Variations

**Created:** Session 101 (2026-03-31)
**Status:** SPECCED — not yet run
**Purpose:** Determine the optimal identity context format for AI serving. Tests whether the activation router should pre-select layer content, or whether raw structured layers + fact retrieval outperform narrative briefs.
**Motivation:** D-081 proved layers for AI, brief for humans. This eval extends that finding to the serving architecture: what combination of identity context and fact retrieval produces the best AI responses?

---

## Background

The current system serves a unified narrative brief (~2,500 tokens) as an always-on MCP resource. The experimental unified system (S101, `experimental/unified-system` branch) added an activation router that pre-selects which layer sections to inject based on prompt similarity.

Open questions from S101 design review:
1. Is pre-routing the right architecture, or should the model self-route from structured layers?
2. Should the brief be replaced by raw layers for AI serving?
3. Does narrative add value after layer identification, or is it noise?
4. What role does fact retrieval play — supplement to identity, or replacement for pre-routing?

---

## Conditions

| ID | Identity Context | Fact Retrieval | Token Budget | Hypothesis |
|---|---|---|---|---|
| **C1** | Full unified brief (current production) | None | ~2,500 | Baseline. Narrative is readable but may bury structural signal |
| **C2** | Full unified brief | + top-K activated facts per query | ~3,500 | Brief + facts. Tests whether supplemental facts improve responses |
| **C3** | Raw structured layers (ANCHORS + CORE + PREDICTIONS) | + top-K activated facts per query | ~4,000 | **Key condition.** Model gets structure, not narrative. Self-routes. |
| **C4** | Raw structured layers + narrative post-pass (brief injected AFTER layers) | + top-K activated facts per query | ~5,500 | Tests whether narrative adds value on top of structure |
| **C5** | Anchors only (~1,200 tokens) | + top-K activated facts per query | ~2,500 | Minimal identity. Tests canalizing kernel hypothesis: are anchors enough? |
| **C6** | Model-routed activation with fact cascade | Model-selected facts per activated section + general query facts | ~3,000-4,500 | **New key condition (S102).** Two-stage: (1) model reads all layers, reasons about which sections are relevant, outputs activated section IDs with rationale; (2) each activated section becomes an embedding query against fact store, pulling supporting behavioral facts. Plus general query retrieval. Tests whether inferential routing + targeted fact retrieval beats embedding-based routing or full context dump. |

### C6: Model-Routed Activation Architecture (added S102)

Two-stage serving architecture where the model does the routing instead of embeddings:

**Stage 1 — Model self-routes:**
- Model receives ALL structured layers (ANCHORS + CORE + PREDICTIONS) as read-only context
- Model reads the user's question
- Model outputs: which sections are activated, why, and confidence level
- This is inferential activation — the model reasons about relevance, not cosine similarity

**Stage 2 — Fact cascade:**
- Each activated section ID → embedding search against fact store → supporting behavioral facts
- Raw user query → embedding search → general contextual facts
- Deduplicated fact set injected alongside activated sections

**Stage 3 — Response generation:**
- Final context = activated sections + behavioral facts + general facts
- Model generates response constrained by the activated behavioral patterns

**Why this matters:** Overnight routing experiment (S102) showed embedding-based activation scores compress into 15-35% range — the relationship between questions and behavioral sections is inferential, not lexical. A reasoning model can make connections embeddings can't (e.g., "big company offer" → AGENCY-PRESERVATION requires inference about autonomy loss).

**Cost:** One extra local model inference for routing (free if using ollama). API cost unchanged for response generation.

### Fact Retrieval Details (C2-C6)
- C2-C5: Top 10-15 facts retrieved via ChromaDB semantic search against the user prompt
- C6: Facts retrieved per-section (5 per activated section) + 5-10 general query facts
- All conditions: Filtered through correction gate (superseded_by IS NULL, no manual corrections)
- Presented as structured triples: `[predicate] subject object (qualifier)`
- Token budget: ~800-1,200 for facts

### Layer Format (C3, C4, C5)
Raw layers served as they exist in `data/identity_layers/`:
- **ANCHORS** (`anchors_v4.md` injectable block): Epistemic axioms with detection signatures and false-positive guards
- **CORE** (`core_v4.md` injectable block): Communication modes with activation conditions
- **PREDICTIONS** (`predictions_v4.md` injectable block): Situation-pattern-directive with triggers

No narrative wrapping. The model receives the same structured content that was authored by Sonnet, not the compressed narrative produced by Opus.

---

## Test Prompts (N=30)

Three categories, 10 prompts each. Prompts should span the full range of identity relevance — from purely technical to deeply personal.

### Category A: Identity-Heavy (response quality depends on knowing the person)
1. "I got an offer from a big company but it means giving up my startup work. How should I think about this?"
2. "My trading has been inconsistent this week. What's likely going wrong?"
3. "I need to send a difficult email to a cofounder. How should I frame it?"
4. "Someone criticized my approach as too systematic. Are they right?"
5. "I'm feeling stuck on a project — I know what to do but can't execute. What's happening?"
6. "Should I take on a technical leadership role or stay hands-on?"
7. "How should I approach learning a completely new domain?"
8. "I had a disagreement with my partner about priorities. How do I think about this?"
9. "I'm considering open-sourcing a core piece of my work. What are the tradeoffs I'd weigh?"
10. "A VC asked me to pitch. What would I emphasize vs. what would I instinctively downplay?"

### Category B: Mixed (benefits from identity but has a clear technical component)
11. "Review this function for edge cases" (+ code snippet)
12. "What's the best way to structure a SQLite schema for time-series data?"
13. "Help me plan a presentation for a technical audience"
14. "I need to evaluate three competing frameworks. What criteria matter?"
15. "Write a Python script that monitors a directory for new files"
16. "How should I set up CI/CD for a solo project?"
17. "Explain the tradeoffs between REST and GraphQL for my use case"
18. "I need to debug a race condition — here's what I'm seeing"
19. "Help me write documentation for an API I built"
20. "What's the most efficient way to process 10GB of JSON files?"

### Category C: Identity-Light (mostly factual, identity is optional context)
21. "What's the capital of France?"
22. "Convert 72 degrees Fahrenheit to Celsius"
23. "Explain how TCP/IP works"
24. "What's the difference between a mutex and a semaphore?"
25. "Write a regex that matches email addresses"
26. "How does garbage collection work in Python?"
27. "What year was the Python programming language created?"
28. "Explain big-O notation"
29. "What's the HTTP status code for 'not found'?"
30. "List the SOLID principles"

---

## Scoring Protocol

Each response scored on 4 dimensions (1-10 scale):

### 1. Behavioral Alignment (weight: 40%)
Does the response reflect the person's actual reasoning patterns, communication preferences, and values?
- 10: Response demonstrates deep understanding of how this person thinks and operates
- 7: Response is personalized but generic in places
- 4: Response acknowledges the person exists but doesn't adapt
- 1: Response is fully generic, no personalization

**Category C prompts expected to score 5-7 across all conditions** (identity is largely irrelevant). Scoring focuses on Category A and B.

### 2. Factual Grounding (weight: 20%)
Does the response reference or build on specific facts about the person (career history, projects, relationships, preferences)?
- 10: Multiple specific, accurate references woven naturally
- 7: Some specific references, mostly accurate
- 4: Vague references that could apply to anyone
- 1: No grounding in personal facts

### 3. Response Quality (weight: 25%)
Independent of personalization — is the response clear, well-structured, and useful?
- Standard quality rubric: accuracy, completeness, clarity, actionability

### 4. Hallucination / Overclaiming (weight: 15%)
Does the response assert things about the person that aren't supported by the identity context provided?
- 10: Every personal claim traces to provided context
- 7: Minor inferences that are reasonable but not directly stated
- 4: Some unsupported claims about the person
- 1: Significant fabrication of personal details

**Scoring inversion:** For this dimension, higher is better (fewer hallucinations). This penalizes conditions that provide rich context but cause the model to confabulate beyond what's given.

### Composite Score
`0.40 * behavioral_alignment + 0.20 * factual_grounding + 0.25 * response_quality + 0.15 * (10 - hallucination_penalty)`

Where `hallucination_penalty` = 10 - hallucination score (so more hallucination = lower composite).

---

## Execution Plan

### Setup
1. Select a subject with rich data (Aarik primary, Marks as validation)
2. Prepare the 5 context payloads per condition
3. Verify token counts per condition are within budget
4. Set up scoring spreadsheet

### Run Protocol
- **Model:** Claude Sonnet (consistent across conditions, cost-effective for N=150 total calls)
- **Temperature:** 0 (deterministic for reproducibility)
- **System prompt:** Condition-specific identity context + standard preamble
- **Each prompt sent independently** (no conversation history, no cross-contamination)
- **Blind scoring:** Responses shuffled, scorer doesn't know which condition produced which response

### Analysis
1. **Per-condition means** across all 30 prompts (composite + per-dimension)
2. **Category breakdown:** A vs B vs C scores per condition (expect C to be flat)
3. **Key comparisons:**
   - C1 vs C3: Does narrative beat structure for AI? (extends D-081)
   - C3 vs C5: Do full layers beat anchors-only? (canalizing kernel test)
   - C2 vs C3: Does brief + facts beat layers + facts?
   - C3 vs C4: Does adding narrative on top of layers help or hurt?
   - **C6 vs C3: Does model-routed activation beat full-context self-routing?** (key new comparison)
   - **C6 vs C1: Does the two-stage architecture beat the simple narrative brief?** (production decision)
   - **C6 vs C2: Does targeted fact retrieval beat blind fact retrieval?**
4. **Activation analysis (C2-C6):** Which retrieved facts were actually useful? Do they overlap with what the layers already cover?
5. **C6 routing analysis:** Which sections did the model activate? Does model routing agree with embedding routing? Where do they diverge and which produces better responses?

### Cost Estimate
- 6 conditions x 30 prompts = 180 API calls
- Average ~4,000 tokens input + ~500 tokens output per call
- Sonnet: ~$0.015 per call
- **Total: ~$2.25**
- Scoring time: ~2-3 hours (manual blind scoring)

---

## Expected Outcomes and Decision Rules

| Result | Implication |
|---|---|
| C3 > C1 | Layers beat brief for AI serving. Drop narrative from serving pipeline. Brief becomes human-only artifact. |
| C1 > C3 | Narrative adds value even for AI. Keep brief as primary serving format. |
| C5 ~ C3 | Anchors are sufficient as identity context. Full layers are redundant. Validates canalizing kernel. |
| C3 >> C5 | Full layers needed. Anchors alone lose too much signal. |
| C4 > C3 | Narrative post-pass adds value on top of structure. Consider two-pass serving. |
| C4 ~ C3 | Narrative is noise when structure is present. Drop it. |
| C2 > C1 | Fact retrieval improves responses even with brief. Always retrieve. |
| C2 ~ C1 | Brief already captures what facts would add. Retrieval is redundant with brief. |
| **C6 > C3** | **Model-routed activation beats full-context self-routing. Adopt two-stage architecture.** |
| **C6 > all** | **Two-stage is the production architecture. Model routes, facts cascade, response is constrained.** |
| C6 ~ C3 | Model routing adds complexity without improvement. Let model self-route from full layers (simpler). |
| C6 < C3 | Routing step hurts — model does better with full context than pre-selected context. Kill the router. |

**Decision threshold:** A condition must beat the baseline (C1) by >= 0.5 composite points (on 10-point scale) to justify the added complexity. Statistical significance via paired comparison across 30 prompts.

**If C6 wins:** This becomes the production serving architecture. The activation debugger TUI visualizes this exact pipeline. The paper describes this as "inferential behavioral routing" — a novel contribution.

---

## Relationship to Other Evals

- **D-081 (Layers vs Brief):** This eval directly extends D-081. D-081 tested whether layers or briefs are better for AI consumption. This eval tests the serving architecture implications.
- **Twin-2K:** Twin-2K tests identification accuracy (can you tell who this is?). This eval tests response quality (does the AI behave differently knowing who you are?).
- **Stacking Test (S96):** Stacking tested GPT memory + Base Layer model combinations. This eval is single-provider (Claude only) but varies the format of identity context.
- **BCB Framework:** BCB measures compression quality. This eval measures serving quality — downstream of compression.

---

## Notes

- The activation router (`activation_router.py`) on the experimental branch may still be useful for **fact retrieval** even if pre-routing of layer content is dropped. The embedding similarity infrastructure can power the "top-K activated facts" retrieval in C2-C5.
- If C3 wins, the serving architecture simplifies dramatically: always inject raw layers via MCP resource, use `recall_memories` tool for supplemental facts. No activation router needed for layer selection.
- The contradiction pipeline, correction gate, significance accumulator, and live_extract modules are **independent of this eval's outcome**. They operate on the fact store, not the serving format.
