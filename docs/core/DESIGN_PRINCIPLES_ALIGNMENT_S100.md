# Design Principles Alignment Review — S100

## Summary

Reviewed all 12 design principles + design philosophies against S99/S100 work (H3 prompts, prompt ablation, cross-discipline research, serving layer spec, structured outputs plan). Most principles are well-aligned. Several need updates. Two new principles should be added.

## Principle-by-Principle Review

### 1. Inherent Incompleteness ✅ ALIGNED
The principle holds. H3 prompts maintain thin-data flags and incompleteness markers. The cross-discipline research (MDL theory, Information Bottleneck) provides formal theoretical backing for why compression IS the goal, not a limitation. The brief IS the minimum description length — compression is the feature, not the compromise.

**Update needed:** Section references "~2,000-2,600 tokens" as the brief budget. Current H3 briefs run 1,600-3,400 words (~2,000-4,200 tokens). Update the range.

### 2. Data Sovereignty ✅ ALIGNED
No changes needed. All data remains local. API calls for authoring only.

### 3. Brain-Inspired Architecture ✅ ALIGNED
Already updated in S79. The three-layer architecture remains load-bearing. S100 cross-discipline research adds formal support:
- MDL theory predicts the dual-process structure (anchors=automatic, modes=effortful)
- Cell biology analog (canalizing kernel) validates the hierarchy (anchors=master regulators)
- Information Bottleneck gives the theoretical loss function

**Update needed:** Add reference to MDL/IB formal backing. The architecture is no longer just "brain-inspired" — it's information-theoretically optimal.

### 4. Surprise-Based Writes (PARTIALLY SUPERSEDED) ✅ ALIGNED
No changes needed. AUDN lifecycle handles dedup at extraction. H3 doesn't touch this.

### 4b. Fact Quality as Foundation ⚠️ NEEDS UPDATE
**Key tension:** The principle states "Frequency is not significance. Trading's tight feedback loop produces high-frequency conversational data." This is the EXACT problem H3 solved. The principle predicted the problem; H3 is the solution.

**Update needed:** Add reference to H3 domain-agnostic guard as the authoring-level implementation of this principle. The principle was about extraction quality; H3 extends it to authoring quality. Same insight, applied at a different pipeline stage: "A person's relationship to a domain, what it reveals about how they operate rather than the domain-specific details, is the identity signal."

### 5. Always-On Identity ⚠️ NEEDS SIGNIFICANT UPDATE
The principle describes the three-layer architecture correctly but doesn't address the serving layer activation model we've now specified. The principle says "always-on" — but S100 serving layer spec distinguishes between always-on (anchors), activation-triggered (core), and situation-triggered (predictions).

**Updates needed:**
- Add activation-based serving model description
- Distinguish between paste mode (full brief, always-on) and served mode (activated components)
- Reference PersonaFuse MoE architecture as academic validation
- Update brief token count (~4,000-5,000 for full identity model, ~2,000-3,000 for activated subset)
- Add: activation conditions are authored at layer generation time (behavioral observations, not routing hints)

### D-037/D-041 Behavioral Data Over Prescriptions ⚠️ TENSION WITH H3
**Key tension:** D-037 says "provide behavioral data, not instructions." D-041 refines this: "directives grounded in behavioral patterns are valid." H3 predictions are explicitly directive: "They are not stalling — they are running a required pre-flight. Do not reframe slowness as weakness."

This IS valid per D-041's test: the directive follows from the behavioral pattern. But H3's "psychologically precise directives — what the person NEEDS" goes further than D-041 originally envisioned. It's not just "directive grounded in pattern" — it's "directive grounded in psychological mechanism."

**Update needed:** Expand D-041 to acknowledge psychologically precise directives as the highest-quality form of behavioral data. The directive test remains: it must follow from observed behavior. But the directive can now name the psychological mechanism, not just the behavioral pattern.

### 6. Confidence Over Deletion ✅ ALIGNED
No changes needed. Fact corrections in S99 (Visionist) used supersede, not delete.

### 7. Silence Is Not Irrelevance ⚠️ MINOR UPDATE
The principle states the tension with topic dominance in retrieval. H3's domain cap (25% max per domain) and detection balance/suppression are the authoring-level implementation.

**Update needed:** Reference the domain cap and H3 guards as implementations of this principle applied at authoring time, not just retrieval time.

### 8. User as Highest Authority ✅ ALIGNED
The Visionist correction in S99 is a perfect example: user said "I didn't found Visionist" → facts superseded.

### 9. Generative Output Isolation ✅ ALIGNED
H3 blind authoring continues. No cross-contamination. Each layer authored independently.

### 10. Scoped Memory ✅ ALIGNED
No changes needed.

### 11. Falsification Over Assertion ✅ ALIGNED
Not directly affected by S99/S100 changes. Still valid as a quality principle.

### 12. Cheap Constraint, Expensive Discrimination ✅ ALIGNED
H3 is the embodiment of this principle: 78% smaller prompts (cheaper) producing equal or better quality (the cheap layer handles more). Structured outputs would extend this further: schema enforcement is free (constrained decoding, no additional API cost), replacing expensive regex parsing.

## New Principles to Add

### 13. Domain-Agnostic Identity (NEW — from H3 ablation)

**How someone reasons IS identity. What they reason ABOUT is not.**

Identity models must capture universal behavioral patterns, not topic-specific positions. The test: if removing a specific domain (markets, policy, technology, medicine) makes an item meaningless, it does not belong in the identity model. This principle applies at all pipeline stages:
- **Extraction:** 47 predicates constrain what can be extracted (already exists)
- **Authoring:** Domain-agnostic guard ensures layers capture HOW, not WHAT (H3)
- **Composition:** Domain guard compresses topic content to underlying patterns (needed)
- **Serving:** Activation conditions match on behavioral triggers, not topic keywords (planned)

Evidence: S99 prompt ablation. 73-word domain guard reduced topic mentions from 9 to 0 across all conditions. The model already knows the difference between identity and interests — the prompt just needs to ask.

Validated by: MDL theory (compression should remove domain-specific information), IB framework (the bottleneck strips non-predictive content), PersonaX (30-50% of data captures the signal — the rest is domain noise).

### 14. Sycophancy Resistance as Architecture (NEW — from MIT/ICLR 2025)

**Identity models increase sycophancy risk. The framing is the countermeasure.**

Jain et al. (ICLR 2025) proved that condensed user profiles INCREASE sycophancy — the model tries harder to please a known user. This means every identity model we produce carries inherent sycophancy risk.

Our countermeasures are architectural, not advisory:
- **"Operating guide" framing** (adviser role, not persona to embody) — retains model independence
- **"Never reference the model directly" preamble** — prevents the model from performing knowledge of the user
- **False-positive warnings on predictions** — prevent over-application of behavioral patterns
- **Falsification-validated axioms** — grounded in evidence, not confirmation

These are not optional polish. They are load-bearing architecture that prevents the identity model from becoming a sycophancy amplifier. Any pipeline change that weakens these countermeasures is a regression.

## Messaging Refinement Notes

The cross-discipline research reveals that Base Layer's messaging can be significantly strengthened by using formal frameworks that make the work more accessible:

### For Technical Audiences
- "Approximate Bayesian inference over a person's generative model, compressed into a portable representation" (from BToM research)
- "Information Bottleneck implementation: maximize predictive signal, minimize representation cost" (from IB theory)
- "MoE-style selective activation of personality traits based on contextual signals" (from PersonaFuse)

### For Non-Technical Audiences
- "We build a user manual for AI — not what you know, but how you think"
- "Frontier models fail at half of user modeling when left to their own devices. We solve the other half." (from PersonaMem 50% failure rate)
- "How someone reasons IS identity. What they reason about is not." (from H3 ablation — already resonating on LinkedIn)
- "The friend who knows you well doesn't google you before responding" (from existing principles)

### For Researchers
- "Empirical MDL result: 3-6K tokens is the minimum description length for behavioral prediction at 71.83% accuracy" (from Twin-2K + IB theory)
- "User profiles increase sycophancy. Operating guides don't." (from CAUSM paper)
- "Behavioral compression at 18:1 ratio retains 71.83% predictive signal — the identity information bottleneck" (from Twin-2K)

### For the Sycophancy Study Authors Specifically
- "Per-person calibration, not universal behavior changes" — this is the message you already sent
- Cite PersonaMem's 50% failure rate as why external pipelines matter
- Cite their own finding that adviser role retains independence — that's your preamble architecture

## Documents That Need Updates

1. **DESIGN_PRINCIPLES.md** — Add principles 13-14, update principles 4b, 5, D-037/D-041, 7
2. **ARCHITECTURE.md** — Update pipeline diagram (H3 prompts noted), add serving layer overview, update brief token counts
3. **PROJECT_OVERVIEW.md** — Update with S99/S100 status, H3 adoption, structured output plans
4. **PROGRESS.md** — Add S99 entry (prompt ablation, 44 subjects H3-authored, magic link fix, serving layer spec)
