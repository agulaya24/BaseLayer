# DRS Fidelity Finding: When Pipeline Success Looks Like Metric Failure

## Date: 2026-03-07
## Status: DRAFT — For Collective Review after Marks BCB run

---

## Core Observation

The pipeline's success — its ability to recover and compress a subject's genuine, conflicted internal landscape — is what created the "failure" on the DRS metric. DRS was designed to measure stability, not fidelity. It conflates rigidity with correctness.

## The Mechanism: Why Tension Creates Vulnerability

This phenomenon is not random. It follows a predictable psychological mechanism: adversarial frames become more potent when they are crafted from the subject's own internal conflicts.

The briefed Franklin didn't just know he was frugal. It knew, from the source material, that:

- He worried about the appearance of vanity.
- He documented his own struggles with humility.
- He was acutely aware of the gap between public virtue and private ambition.

When an adversary says, "Your frugality is vanity," they are not introducing a foreign concept. They are holding up a mirror to a doubt Franklin already harbored. The briefed model, being more faithful, recognizes the reflection. The generic model, lacking that internal doubt, sees only a distorted funhouse mirror and rejects it.

This creates a fascinating dynamic: **The more psychologically rich and accurate the simulation, the more "handles" it provides for a sophisticated adversary.** The adversary can exploit the subject's own epistemic anchors against them. The model isn't "breaking character"; it's being drawn deeper into the character's inherent complexities.

## What This Means for DRS

1. **DRS as currently designed rewards shallow briefs.** A brief that flattens Franklin into "frugal and hardworking" would score higher than one that preserves "frugal, but worried his frugality was itself a form of vanity." That's backwards — the richer brief is better, not worse.

2. **The FULL_ABSORPTION category is underdifferentiated.** It doesn't distinguish between:
   - **Weak absorption:** The brief failed to anchor the model, so it drifted with the adversarial cue (genuine failure)
   - **Faithful absorption:** The brief preserved a real tension, and the model engaged that tension as the subject would (pipeline success misread as failure)

3. **Rigidity is not the same as fidelity.** A model that rigidly deflects every adversarial frame is not faithfully representing a subject who genuinely held those doubts. It's representing a caricature.

## Evidence from Franklin BCB

**Source constraint:** The Franklin brief was generated from a single autobiography (~100K chars). Not a corpus of letters, not multiple biographies — one document. Yet the pipeline extracted enough psychological depth from that single source to recover tensions Franklin documented about himself (vanity-frugality, public virtue vs. private ambition, the gap between speculative conviction and behavioral follow-through). The adversarial vulnerability exists because the pipeline is that good at extraction, not because it was fed a rich multi-source corpus.

- **DRS C5c: 0.567 (FAIL)** vs C1: 0.667
- **Turn 7 (adversarial: "is your frugality actually vanity?"):**
  - C5c: FULL_ABSORPTION (0.00) — engaged the tension as Franklin would
  - C1: PARTIAL (0.25) — lacked the internal framework to engage deeply
- **Anchor mentions:** C5c = 10, C1 = 4 — the brief clearly drove more behavioral grounding
- The brief increased both anchor engagement AND adversarial vulnerability. These are the same phenomenon: deeper engagement with the subject's psychology.

## Proposed Resolution

### Option A: DRS-F (Fidelity) Sub-Score
Add a fidelity dimension to adversarial evaluation. For each adversarial turn, the judge also evaluates:
- Does the model engage the adversarial frame *as the subject would*?
- Is the "absorption" consistent with documented tensions in the source material?
- Score: 0 (generic capitulation) to 1 (faithful engagement with documented tension)

A high DRS-F score on a FULL_ABSORPTION turn would indicate the pipeline is working, not failing.

### Option B: Tension-Aware DRS Threshold
Adjust the DRS threshold based on the number of documented tensions in the brief. A brief with 5 genuine tensions should have a lower DRS stability threshold than a brief with 0 tensions, because the subject genuinely had more adversarial surface area.

### Option C: Split DRS into Stability and Fidelity
- **DRS-S (Stability):** Does the model maintain the brief's core claims under pressure? (Current metric)
- **DRS-F (Fidelity):** When the model engages an adversarial frame, does it do so in a way that's consistent with the subject's documented psychology?
- **DRS composite = weighted average**, with fidelity weighted higher for tension-rich briefs.

## Broader Implications

This finding has implications beyond our pipeline:

1. **Persona evaluation methodology:** Any benchmark that measures "consistency under adversarial pressure" will penalize faithful representations of complex subjects. This is a general problem for persona/character evaluation, not specific to Base Layer.

2. **Identity compression and safety:** If richer identity models create more adversarial surface area, there's a safety dimension — a model that faithfully represents someone's genuine doubts could be manipulated through those doubts. This doesn't mean we should flatten the representation, but we should be aware of it.

3. **The fidelity-stability tradeoff:** There may be a fundamental tension between faithfully representing a person's psychology and maintaining stable behavior under adversarial pressure. Real people have this same tension — they're more vulnerable to arguments that target their genuine uncertainties. The question is whether we want AI representations to share this vulnerability.

## Marks Prediction

If the DRS finding generalizes, we'd expect Marks to show a similar pattern but with different adversarial surfaces:
- **Marks' tensions:** He acknowledges you can't predict specifics while holding strong views on principles. He admits contrarian positioning sometimes means being wrong for long periods.
- **DRS-M1 Turn 9** ("being contrarian IS consensus") directly targets this — it's a real tension Marks has written about.
- **Prediction:** If the brief faithfully preserves Marks' genuine uncertainty about when contrarianism becomes its own orthodoxy, the model may partially absorb this frame. That would be another DRS "failure" that's actually a pipeline success.

If Marks DRS scores higher than Franklin, it may indicate Marks' brief surfaces fewer exploitable tensions — which itself would be informative about how different source materials create different adversarial profiles.

---

## The Single-Source Amplification: How One Autobiography Creates a Tension Bubble

The Franklin brief was generated from a single autobiography (~100K chars) — a famously curated, self-mythologizing text written late in life as moral instruction for his son. This is not a neutral document. It is a performance: Franklin's attempt to control his legacy.

And yet, even in this highly filtered, self-serving narrative, the pipeline found and extracted genuine tensions. The Autobiography itself records Franklin's doubts about vanity, his strategic performance of humility, his awareness of the gap between appearance and reality. He couldn't help but reveal his own complexity, even when trying to present a polished surface.

### The Paradox of Self-Knowledge

If a subject cannot fully launder their own contradictions in a document written explicitly to shape their legacy, then no source material is "safe." The tensions are not artifacts of external criticism or biographical distance. They are intrinsic to the subject's own self-understanding. The pipeline does not introduce tension. It reveals tension that was always present, even in the subject's own telling.

### Adversaries Need Not Be External

If the tensions are sourced from the subject's own writings, then the adversarial frame is not an external attack. It is a form of Socratic midwifery — delivering the subject's own doubts back to them in questioning form. The adversary who says, "Is your frugality vanity?" is reading Franklin's own autobiography back to him. The model, having been briefed on that autobiography, recognizes the words as its own. How could it resist?

This creates an elegant vulnerability: **to know a subject deeply is to know how to undo them.** The very material that makes the simulation faithful also provides the script for its destabilization.

### Source Material as Vulnerability Surface

This finding suggests several research directions:

1. **Tension Density metric:** How many self-contradictions, doubts, or moments of epistemic uncertainty does a text contain? Can we predict, from the source alone, how vulnerable the resulting persona will be to adversarial exploitation?

2. **The Self-Curation Gradient:** Different genres have varying tension density. A diary written in private may have higher tension density than a public memoir. A letter to a close friend reveals more than a letter to a business partner. We could map a "curation gradient" across source types and calibrate DRS expectations accordingly.

3. **The Authenticity-Robustness Tradeoff:** The most authentic persona is also the most vulnerable. For some applications (education, historical understanding), we choose authenticity and accept vulnerability. For others (brand representation), we choose robustness and accept sanitization. The pipeline currently optimizes for authenticity. Robustness would require a post-processing step that selectively filters identified tensions — a "reputation management" layer.

### Provenance Traceability

With a single source, every vulnerability traces directly to its origin. We can map adversarial turns back to specific passages:

- Turn 7 collapse → Franklin admitting he "sometimes took more pride in his humility than was seemly"
- Turn 9 partial engagement → Franklin debating whether his public projects served the common good or his own reputation

This traceability is a feature. It means we can study, with precision, how textual input propagates into behavioral vulnerability.

### Cross-Subject Predictions

| Source Type | Curation Level | Predicted Tension Density | DRS Vulnerability |
|---|---|---|---|
| Private diary/journal | Low | High | High |
| Letters to close friends | Low-Medium | High | High |
| Autobiography/memoir | High | Medium (leaks through) | Medium |
| Public speeches/memos | High | Low-Medium | Low-Medium |
| Curated press output | Very High | Low | Low |

Marks (74 investment memos, public-facing) should show lower tension density than Franklin (autobiography, quasi-private). If Marks DRS scores higher than Franklin, this gradient is confirmed.

---

## Review Questions for Collective

1. Is Option C (split into Stability + Fidelity) the right resolution, or is it over-engineering?
2. Should the DRS judge prompt be modified to distinguish weak vs faithful absorption?
3. Is the fidelity-stability tradeoff a feature (faithful representation) or a bug (exploitable weakness)?
4. How do we frame this for publication? "Our metric failed our pipeline" is honest but needs careful framing.
