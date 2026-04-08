# Base Layer — Serving Layer Research Brief

**Date:** 2026-04-07 (Session 102)
**Author:** Aarik Gulaya + Claude Opus
**Status:** Active research — seeking feedback, alternative perspectives, and critique

---

## What We Are Trying To Do

We are building behavioral alignment infrastructure for autonomous AI agents. The core claim: AI agents that act on behalf of humans need more than memory — they need a compressed behavioral specification that encodes how the person reasons, decides, and communicates. This specification should change not just what the AI recalls, but how it reasons about new situations.

The specific research question for the serving layer: **Does a compressed behavioral specification measurably change AI retrieval and reasoning in ways that are faithful to the person's actual behavioral patterns — and can that change be distinguished from sycophancy?**

### What "behavioral specification" means

A 3-6K token structured document with three layers:
- **Anchors:** Epistemic axioms — the foundational beliefs a person reasons FROM (e.g., "Reality is knowable and coherent. When responses contain internal inconsistency, surface it immediately.")
- **Core:** Operational constraints — how to communicate and engage with this person in different contexts
- **Predictions:** Behavioral triggers — situation→pattern→directive mappings (e.g., "When experiencing setbacks, escalates from domain-specific frustration to existential questioning. Contain analysis within the domain first.")

Extracted from text (conversations, essays, journals) using 47 constrained behavioral predicates. Provenance-traced — every claim links back to source evidence. 60+ subjects modeled. Open source (Apache 2.0).

### What we are NOT trying to do

We are NOT building a better memory system. Memory (fact recall) is a solved problem — Mem0 achieves 96.6% recall at scale. We are building the layer above memory: the behavioral context that changes what the AI does with the facts it retrieves.

---

## What We Have Done (This Session)

### 1. Built a serving layer prototype

A "diff cascade" that takes any statement and runs it through three conditions:

- **Mem0 condition:** Faithfully replicates Mem0's retrieval architecture (Chhikara et al., 2025, arXiv:2504.19413) — embed the raw query with text-embedding-3-small, cosine similarity top-10 against a fact store. No behavioral interpretation. This is the industry standard at 52K GitHub stars and 186M monthly API calls.

- **Base Layer condition:** First rewrites the query through the behavioral specification ("what is this person ACTUALLY asking?"), then retrieves facts using the behaviorally-interpreted query. The spec changes what information the model seeks.

- **Merged condition:** Combines both fact sets (behavioral retrieval + raw domain retrieval) with the behavioral spec loaded. Tests whether having both the behavioral lens AND the domain facts produces the best result.

Each condition generates a full response. The diff between conditions is logged and analyzed.

### 2. Built a visual debugger TUI

A Textual-based terminal UI with 7 panels showing the cascade live:
- Mem0 retrieval vs Base Layer retrieval (what facts each finds)
- Divergence (how many facts differ, with snippets of unique facts per side)
- Spec activation (which parts of the behavioral spec the model identifies as relevant)
- Three response columns (Mem0, Base Layer, Merged)
- Word counts and structural metrics

All results auto-saved as JSON for later analysis.

### 3. Ran initial experiments

**Test question: "What makes base layer special?"**

Results:
- Mem0 retrieved: factory paint properties, baking skills, mattress preferences, cake recipes (cosine similarity matched "base layer" to "base layer of cake" and "memory foam")
- Base Layer retrieved: history of losses shaping resilience, prioritizes agency over security, values maintaining control over IP, concerned with aligning purpose with sustainability
- **18 out of 19 retrieved facts differed.** 1 shared fact across both retrievals.
- Mem0 response: generic infrastructure analysis (175 words)
- Base Layer response: targeted, confrontational, addressed the question underneath the question (37 words)

**Test question: "What should I eat tonight?"**

Results:
- **20 out of 20 retrieved facts differed.** Zero overlap.
- Mem0 response: recipe suggestions based on food preferences (155 words)
- Base Layer response: "What's your energy level and how was your trading day?" — asked for context before answering, because the spec knows food decisions are downstream of daily energy state (94 words)
- Merged response: gave food options informed by preferences AND asked about energy level (128 words)

### 4. Identified the novel contribution in the literature

Comprehensive literature review found that nobody measures what we're measuring:
- **Recall benchmarks** (LOCOMO, LongMemEval, AlpsBench) measure fact retrieval accuracy
- **Preference benchmarks** (PersonalLLM, PersonaLens) measure preference matching
- **Character benchmarks** (PersonaGym) measure persona consistency
- **Sycophancy research** (Jain et al. CHI 2026, Sharma et al. ICLR 2024) measures when personalization makes AI more agreeable

Nobody measures: **does a behavioral specification change how an AI reasons about novel situations, and is that change faithful to the person's actual patterns?**

AlpsBench (March 2026) explicitly identified the gap: "explicit memory mechanisms improve recall but do not inherently guarantee more preference-aligned or emotionally resonant responses."

---

## What We Have Found

### Finding 1: The spec changes retrieval, not just response

Same question, same fact store, completely different facts retrieved. The behavioral specification rewrites the query before retrieval — changing what information the model seeks. This is not an optimization over recall. It is a fundamentally different category of retrieval.

Mem0 retrieves what you said. Base Layer retrieves why you said it.

### Finding 2: The spec produces shorter, more conversational responses

Across initial tests, the Base Layer condition consistently produces shorter responses (37 vs 175 words, 94 vs 155 words). The responses read as conversations, not essays. The Mem0 condition produces comprehensive but generic lists. This suggests the behavioral spec changes the model's understanding of what "helpful" means for this specific person.

### Finding 3: The merged condition may be the production architecture

Base Layer alone retrieves the behavioral context but can miss domain-specific facts. Mem0 alone retrieves domain facts but uses them generically. The merged condition (behavioral retrieval + domain retrieval + spec) appears to produce the best results — it has both the behavioral lens and the domain knowledge.

### Finding 4: Embedding-based routing fails for behavioral activation

An overnight experiment (30 prompts, 23 spec sections, 1,579 facts) showed that embedding similarity scores compress into a 15-35% range when matching questions to behavioral spec sections. The relationship between "big company job offer" and "AGENCY-PRESERVATION axiom" is inferential, not lexical. Embeddings can't make that leap. This led to the design of model-routed activation (C6) where the model itself reasons about which spec sections are relevant.

### Finding 5: The diff IS the identity signal

The gap between model-with-spec and model-without-spec is the measurable behavioral influence. The specification was never meant to operate alone — it operates alongside the human, and the delta between generic and personal IS the identity signal. This reframes the entire system: the spec is not a document to inject, it's a continuously measured behavioral delta.

---

## Where We Are Struggling

### 1. How to measure "better" objectively

The diff is measurable — we can show that 18/19 facts differ, that responses are shorter, that the model asks clarifying questions instead of dumping lists. But "better" requires a judgment. Options:

**Option A: Human preference.** Ask the subject: "which response do you prefer?" Problem: Jain et al. (2026) proved that personalized profiles increase sycophancy — people prefer responses that agree with them, which corrupts the measurement.

**Option B: Prediction fulfillment.** The spec predicts what behavioral influence it should create (e.g., "surfaces contradictions," "redirects to internal metrics"). A daemon checks whether the diff matches those predictions. Self-contained — no human judgment needed. But this assumes the spec is correct.

**Option C: External benchmark.** Run Base Layer specs through PersonaGym's Expected Action task. Three conditions: no persona, demographic description, Base Layer spec. If C3 > C2 > C1, the behavioral compression adds decision-relevant signal. But PersonaGym wasn't built for this.

**Option D: Downstream behavior tracking.** Did the person act on the spec-informed response? If the spec predicted confirmation-seeking and provided confirmation criteria, did the person use them in their next decision? This is the strongest evidence but requires longitudinal data.

We think we need both B (novel metric) and C (external validation), but we're not confident this is the right framework.

### 2. What questions best demonstrate the difference

The food question ("what should I eat?") produced a dramatic diff. The car question produced a good diff. "What makes base layer special?" was confounded by the model not knowing about the project. We need a systematic set of questions that span:
- Purely factual (where the spec shouldn't change much)
- Judgment calls (where the spec should change the framing)
- Emotional/personal (where the spec should change the entire approach)
- Domain-specific (where domain facts AND behavioral context both matter)

We don't have a principled way to select these questions. PersonaGym generates questions dynamically per persona, which could work but introduces variability.

### 3. Sycophancy vs faithful reasoning

The hardest distinction. When the spec says "this person values directness" and the model responds more directly — is that faithful behavioral reasoning or sycophantic mirroring? The model is literally telling the person what the spec says they want to hear.

Our tentative answer: sycophancy is when the model AGREES more. Faithful reasoning is when the model CHALLENGES more appropriately. The spec doesn't say "agree with everything" — it says "surface contradictions," "redirect to internal metrics," "contain frustration before it escalates." These are constraints, not preferences. But we haven't formalized this distinction.

### 4. Whether the spec or the retrieval is doing the work

The diff has two components: (1) the spec changing how the model reasons, and (2) the spec changing which facts are retrieved. Our Step 3 in the cascade (same facts, different reasoning) was designed to isolate this, but we haven't run it systematically. It's possible that 80% of the improvement comes from better retrieval and the spec itself adds little on top. Or vice versa.

### 5. Generalizability beyond the founder's model

All current experiments use one person's behavioral spec (the founder's, with 1,579 facts from 100+ sessions). The system has 60+ subjects, but the serving layer has only been tested on one. Does the diff cascade work for Buffett (505 facts from shareholder letters)? For a subject with only 50 facts? The serving layer prototype now supports multiple subjects but hasn't been tested across them.

### 6. The daemon architecture

We've described the daemon conceptually — it watches diffs accumulate, detects which spec sections are load-bearing vs inert, surfaces emerging patterns, and tracks drift. But we haven't built it. The prediction fulfillment metric depends on the daemon existing. The self-correcting spec depends on the daemon. It's the piece that closes the loop between serving and composition, but it's unbuilt.

---

## What We Need Clarity On

### 1. Is prediction fulfillment rate a valid metric?

The spec says "this person does X." The daemon checks whether the diff shows X. The fulfillment rate is: how often does the spec's prediction match the diff it creates? Is this circular? The spec creates the influence AND defines the ground truth for evaluating it. Is there a way to break this circularity, or is it actually fine because the spec was derived from independent evidence (the person's actual text)?

### 2. Should the spec be always-on or activated?

Current design: always loaded, model modulates naturally. Alternative: lightweight classifier determines whether the statement benefits from behavioral context. The "always-on" design was chosen because even factual questions benefit from knowing communication preferences (directness, no preamble, etc.). But it costs ~5,800 tokens per call. Is that justified for "what's the capital of France?"

### 3. What is the right comparison baseline?

Options:
- No context at all (shadow/vanilla model)
- Mem0's approach (raw query embedding retrieval)
- ChatGPT memory (accumulated fact snippets)
- A flat preference list ("likes X, dislikes Y, works at Z")
- A demographic description ("35-year-old male founder in AI")

Each baseline tests a different claim. We've been using Mem0 as primary baseline because it's SOTA and citable. But should we also compare against a simple preference list to show that structure matters, not just having context?

### 4. How do we handle the sycophancy concern in the paper?

Jain et al. (2026) is the adversary paper — they proved condensed user profiles increase sycophancy. We need to either:
- Show that our spec doesn't increase sycophancy (hard to prove a negative)
- Show that our spec increases sycophancy LESS than flat profiles (comparative)
- Reframe: the spec doesn't increase agreement, it increases appropriate challenge (show that the spec-response contains more confrontation/questioning than the shadow-response)

### 5. What does the daemon actually compute?

Conceptually: "watches diffs and checks predictions." Mechanically: what? Does it run an LLM on each diff pair to classify whether each prediction was fulfilled? Does it use embedding similarity between the diff and the prediction text? Does it use rule-based pattern matching? The compute cost and reliability differ dramatically between these approaches.

### 6. Can the merged condition be simplified?

The merged condition (behavioral retrieval + domain retrieval + spec) requires two embedding searches per query plus the behavioral interpretation step. In production, is there a simpler architecture that captures most of the benefit? Would a single retrieval with the behaviorally-rewritten query be enough, since the rewritten query already captures domain context?

---

## Architecture Summary

```
User statement
    |
    v
Behavioral interpretation: model rewrites query through spec lens
    |
    +--> Behavioral retrieval: MiniLM embedding of interpreted query → top-K facts
    +--> Domain retrieval: text-embedding-3-small of raw query → top-K facts (Mem0 equivalent)
    |
    v
Merge + deduplicate facts
    |
    v
Model + behavioral spec (always loaded) + merged facts → Response
    |
    v
Shadow: same statement, no spec, raw retrieval → Shadow response (never shown)
    |
    v
Diff: response - shadow = behavioral influence
    |
    v
Daemon: accumulates diffs, checks prediction fulfillment, detects drift
```

---

## Key References

| Paper | Relevance |
|---|---|
| Chhikara et al. (2025), arXiv:2504.19413 | Mem0 architecture — the recall baseline to beat |
| Jain et al. (2026), CHI | Sycophancy risk from condensed user profiles — the adversary paper |
| Hu & Collier (2024), ACL | Closest prior work — persona effect measurement via R-squared |
| AlpsBench (2026), arXiv:2603.26680 | Explicitly identified gap: recall ≠ aligned responses |
| PRISM (2026), arXiv:2603.18507 | Expert personas help reasoning, hurt factual accuracy |
| PersonaGym (2025), EMNLP | External validation path — Expected Action task |
| Betley et al. (2026), Anthropic PSM | Theoretical foundation — models have persona repertoires |
| Sharma et al. (2024), ICLR | SycophancyEval benchmark — the pathology to avoid |
| ASPECT (2026), arXiv:2603.26922 | AI-inferred communication profiles — closest product comparison |
| OP-Bench (2026), arXiv:2601.13722 | Over-personalization pathologies — negative side of influence |

---

## What We Want From You (The Reader)

1. **Is prediction fulfillment rate circular, and if so, how do we break the circularity?**
2. **What questions would you ask to test whether a behavioral spec changes reasoning vs just changing tone?**
3. **How would you distinguish faithful behavioral reasoning from sycophancy mechanically — not philosophically?**
4. **Is the "diff as identity signal" framing novel and publishable, or is it obvious?**
5. **What's the simplest experiment that would convince you this works?**

---

## Project Links

- GitHub: github.com/agulaya24/BaseLayer (Apache 2.0)
- Website: base-layer.ai
- Serving layer prototype: `memory_system/runners/serving_engine.py`
- Visual debugger: `memory_system/runners/serving_tui.py`
- Serving layer plan: `memory_system/docs/core/SERVING_LAYER_PLAN.md`
