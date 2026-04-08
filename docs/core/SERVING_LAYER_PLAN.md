# Serving Layer Plan — Behavioral Alignment Infrastructure

**Created:** Session 102 (2026-04-07)
**Status:** In Progress
**Origin:** Session 102 design conversation — Aarik + Claude Opus

---

## The Thesis

The behavioral specification was never meant to operate alone. It operates live alongside the human. The gap between model-with-spec and model-without-spec IS the behavioral signal. The spec is a continuously measured behavioral delta — the document is just a snapshot of the delta at a point in time.

**Not recall. Influence.**

The metric is not "did the AI remember the right fact." The metric is "did the behavioral specification change what the AI retrieved, how it interpreted the question, and how it constructed the response — in a way that aligns with the person's actual reasoning patterns."

---

## How We Got Here (Session 102 Reasoning Chain)

### Step 1: The activation question

Initial assumption: the serving layer needs an activation gate — decide when to use the spec and when not to. Identity-heavy questions activate it, identity-light questions don't.

**Rejected.** Aarik's insight: every conversation requires personalization. When you ask what to cook, the AI needs to know your preferences. When you ask about your car, it needs to know the insecurity underneath. The spec isn't a gate — it's a lens the model sees through on every interaction.

### Step 2: Always on, but modulated

If the spec is always loaded, the model's job is to modulate — apply it heavily when the question requires judgment, lightly when it's factual. A person who knows you uses their full knowledge on every interaction, they just apply different amounts of it. "What's the capital of France?" still gets answered in your preferred communication style (direct, no preamble). "Should I take this job?" draws deeply on your axioms and predictions.

### Step 3: Inspection — the diff

The spec shapes every response. But how do you prove it? How do you see what the spec did?

**The counterfactual.** Run every statement twice: once with spec, once without. The response the user sees is the spec version. The shadow response is logged but never shown. The delta between them IS the activation trace.

No metacognition needed. No self-observation paradox. Just two outputs and a measurable gap.

### Step 4: The diff IS the identity signal

The daemon doesn't just log diffs — it watches them accumulate. Over time:
- Patterns that consistently create divergence are **load-bearing** (keep in spec)
- Patterns that never change the output are **inert** (candidates for removal)
- Divergence patterns that appear but aren't in the spec are **emerging** (candidates for addition)
- Drift in the delta pattern means the person is changing (temporality)

The spec becomes self-correcting through observed behavioral influence, not just user corrections or re-extraction.

### Step 5: Embedding routing fails

Overnight routing experiment (30 prompts, 23 spec sections, 1,579 facts): embedding-based activation scores compressed into 15-35% range. The relationship between questions and behavioral sections is inferential, not lexical. "Big company offer" → AGENCY-PRESERVATION requires reasoning about autonomy loss. Embeddings can't make that leap.

**Conclusion:** Embedding-based pre-routing is a ceiling, not a floor. Killed the router.

### Step 6: The spec changes what the model seeks

The breakthrough insight: the spec doesn't just change the response — it changes what information the model retrieves. Same question, same fact store, but the spec reinterprets the question before retrieval.

"What makes base layer special?" without spec → retrieves facts about baking, mattresses, paint.
"What makes base layer special?" with spec → retrieves facts about agency, resilience, sovereignty.

**18/19 retrieved facts differ.** Same question. Same database. The behavioral interpretation changed what the model thought the question was asking.

### Step 7: The Mem0 comparison

Replicated Mem0's retrieval architecture (Chhikara et al., 2025, arXiv:2504.19413) — the most widely adopted agent memory system (52K stars, 186M monthly API calls). Their approach: embed raw query with text-embedding-3-small, cosine similarity top-10. No query rewriting, no behavioral interpretation.

Result: Mem0 retrieved cake preferences and mattress opinions for "what makes base layer special?" Base Layer retrieved agency, resilience, sovereignty.

**18/19 facts differ. This is not an optimization over recall. It's a fundamentally different category of retrieval.**

The paper argument: "Mem0 retrieves what you said. Base Layer retrieves why you said it."

---

## Architecture

### Production Serving (always-on)

```
User statement
    |
    v
Model + behavioral spec (always loaded, ~5,800 tokens)
    |
    +--> Behavioral interpretation: model rewrites query through spec lens
    |       "what makes base layer special?"
    |       --> "What fundamental properties matter for long-term value
    |           accrual and system resilience?"
    |
    +--> Fact retrieval: behavioral query → embedding search → supporting facts
    |
    +--> Response: generated with spec + retrieved facts
    |
    v
User sees response
```

### Inspection (parallel, async)

```
Same statement
    |
    +--> Shadow: same model, no spec, no behavioral retrieval
    |       Raw query → embedding search → surface facts
    |       Generate response with surface facts only
    |
    v
Shadow response logged (never shown to user)
    |
    v
Delta computed: spec response - shadow response = behavioral influence
```

### Daemon (background, periodic)

```
Accumulated diffs over N interactions
    |
    v
Analysis:
    - Which spec sections consistently create divergence? (load-bearing)
    - Which never create divergence? (inert)
    - What divergence patterns appear that aren't in the spec? (emerging)
    - Is the delta pattern drifting over time? (temporality)
    |
    v
Spec health report
    - Recommendations: add/remove/modify spec sections
    - Phase shift detection
    - Confidence scores per spec section based on observed influence
```

---

## The Diff Cascade (Evaluation Protocol)

Five steps, each adding one variable and measuring the delta:

### Step 2: Spec influence only (no facts)
- WITH: behavioral spec loaded, no fact retrieval
- WITHOUT: no spec, no facts
- MEASURES: does the spec alone change interpretation?
- RESULT: yes — "base layer" interpreted as infrastructure (spec) vs clothing (no spec)

### Step 3: Same facts, different reasoning
- WITH: spec + raw-query-retrieved facts
- WITHOUT: no spec + same facts
- MEASURES: does the spec change how facts are used?
- RESULT: pending

### Step 4: Different retrieval
- WITH: spec + behaviorally-interpreted facts
- WITHOUT: no spec + raw-query facts
- MEASURES: does the spec change what information the model seeks?
- RESULT: 18/19 facts differ

### Step 5: Mem0 baseline (SOTA comparison)
- MEM0: text-embedding-3-small, raw query, cosine top-10 (per Chhikara et al., 2025)
- BASE LAYER: behavioral interpretation, MiniLM, spec-informed retrieval
- MEASURES: does behavioral retrieval differ from SOTA memory retrieval?
- RESULT: 18/19 facts differ. Mem0 retrieves preferences. Base Layer retrieves reasoning patterns.

---

## What This Proves

1. **The spec changes interpretation.** Same question means different things to different people. The spec tells the model who's asking and why.

2. **The spec changes retrieval.** Same fact store, different query interpretation, completely different facts surface. This is not an optimization over cosine similarity — it's a different category of retrieval.

3. **The diff is measurable.** No need for the model to self-report. Run with spec, run without, compute the delta. The behavioral influence is visible in the gap.

4. **SOTA memory systems don't do this.** Mem0 (52K stars, $24M Series A) retrieves by text similarity to the raw query. No behavioral interpretation. No spec. The retrieval is fundamentally different.

---

## Implementation Status

| Component | Status | File |
|---|---|---|
| Serving layer v2 (CLI) | WORKING | `runners/serving_layer_v2.py` |
| Serving TUI (visual) | WORKING | `runners/serving_tui.py` |
| Routing experiment (embedding) | COMPLETE | `runners/routing_experiment.py` |
| Mem0 comparison | WORKING | Integrated into serving_layer_v2.py step 5 |
| Daemon (diff accumulation) | NOT STARTED | — |
| Spec health report | NOT STARTED | — |
| Phase shift detection | NOT STARTED | — |

---

## Next Steps

1. **Run TUI on 10+ statements** — record demos for paper/posts
2. **Build daemon** — accumulate diffs, produce spec health report
3. **Formalize the eval** — run the diff cascade on 30 prompts, score responses
4. **Write paper section** — "Behavioral Retrieval vs Memory Retrieval"
5. **Add Mem0 comparison to paper** — cite Chhikara et al., replicate faithfully

---

## Key Decision: What We're NOT Optimizing For

We are NOT optimizing for recall. Recall is the wrong metric in a world where memory is good enough. Mem0 gets 96.6% recall. That's fine. Recall measures whether you found the right fact.

We are optimizing for **influence** — whether the retrieved information changed the response in a way that aligns with the person's actual behavioral patterns. That's a fundamentally different metric. You can have perfect recall and zero influence (retrieve every fact but use them generically). You can have low recall and high influence (retrieve the right 3 facts and use them through a behavioral lens).

The serving layer's job is not to remember. It's to align.

---

## Key Quotes (Session 102)

> "Every human has a whole universe of behaviors, beliefs, cycles, going on beneath the surface. Therefore the behavioral spec should be always on." — Aarik

> "The spec was always meant to operate live alongside the human. The diff — it was never meant to operate alone." — Aarik

> "We are not optimizing for recall. That is fundamentally the wrong metric in a world with memory that's good enough." — Aarik

> "Step 4 is the proof. Fact retrieval off raw questions vs fact retrieval based on a behavioral interpretation." — Aarik

> "Mem0 retrieves what you said. Base Layer retrieves why you said it." — Session synthesis
