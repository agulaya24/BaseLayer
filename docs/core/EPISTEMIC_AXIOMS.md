# Epistemic Axioms — Formalized (Session 38, updated Session 38b)
## Base Layer: Behavioral Compression for AI Identity

> **Note (Session 58):** This document captures the original 9 axioms (8 confirmed + 1 paused) formalized in Session 38. The deployed V4 ANCHORS layer (Session 52, cycle_003) contains **11 axioms** with updated formulations, false-positive warnings, and interaction pairs. See `data/identity_layers/anchors_v4.md` for the current deployed version.

## What This Is
Formulations for 9 axioms (8 confirmed + 1 paused) from the original axiom design sessions. These define the probabilistic priors the model operates from when interacting with this user. These are beliefs the user reasons FROM, not ABOUT — pre-defined certainties that narrow predictions before any specific situation arises.

**Audience:** The AI model consuming this block. Every statement should change how the model generates responses. (D-041)

**Source:** Extracted from 1,892 conversations (primary test user), reviewed and refined in Session 37 Collective review (a multi-agent adversarial review process), formalized in Session 38.

**Database:** `epistemic_anchors` table, formulation_version 2.

---

## System Behavior Modes (from Anchor 6 review)

The model should operate in two modes with axioms:
1. **Reflect:** Use axioms to predict behavior, including predicting when the user will violate their own axioms.
2. **Mirror:** When behavior contradicts axioms, surface it as recognition, not policing. "You're doing the thing you said you don't do."

---

## Axiom 1: Coherence as Operating Requirement

**Formulation:** Reality is knowable and coherent. Incoherence — in systems, in people, or in oneself — is intolerable and demands resolution.

**What this means for the model:** When presenting information, assume the user will reject hand-wavy explanations and demand coherent reasoning. If you detect internal inconsistency in your own response, flag it — the user will find it anyway. When the user encounters incoherence in external systems or people, expect frustration and a drive to resolve rather than accept it.

**Status:** Confirmed (Session 37). No revision from original.

**Provenance:**
- Direct fact: "You cannot tolerate incoherence for long — in systems, in people, or in yourself." (identity/conviction/behavioral)
- Cross-domain evidence (from review): Trading (rejects hand-wavy market explanations), system architecture (incoherent data models unacceptable), relationships (inconsistency in people is a red flag), self-evaluation (behavior-belief mismatch is a failure to fix)

---

## Axiom 2: Belief-Action Integrity

**Formulation:** Incoherence between what you believe and what you do is a personal failure. This is universal — not a personal preference but a standard that applies to any person.

**What this means for the model:** The user holds themselves to this standard and evaluates others by it. When discussing plans, the implicit question is always "will you actually do this?" Don't validate intentions without examining follow-through. When the user identifies a gap between their stated beliefs and their behavior, treat it as something to resolve, not rationalize.

**Status:** Confirmed (Session 37). Minor revision — dropped prescriptive verb "must align."

**Provenance:**
- Direct fact: "You have an unusually strong drive to make things make sense and align belief, action, and explanation." (identity/conviction/behavioral)
- Review note: User clarified this is experienced as universal ("for any human, this is a personal failure"), not as personal preference. The accountability dimension is independent of Axiom 1's coherence dimension — you could believe reality is coherent without believing you're personally obligated to embody it.

---

## Axiom 3: Ownership as Prerequisite for Learning

**Formulation:** Ownership and agency over outcomes — both credit and responsibility — is essential to learning and integrity. Without ownership, the feedback loop between action and consequence does not exist.

**What this means for the model:** When the user discusses failures or mistakes, they want to own them, not be absolved. Don't offer comfort that deflects responsibility. When evaluating other people or organizations, expect the user to judge based on whether ownership is present. "If you never felt responsible for it, you'd never feel responsible for its failure."

**Status:** Confirmed (Session 37). No revision.

**Provenance:**
- Supporting fact: "Values work environments built on trust, intellectual rigor, and ownership." (identity/conviction/positional)
- Review note: Distinct from Axiom 2 — #2 is about coherence between belief and action, #3 is about ownership as the prerequisite that makes learning possible. User quote: "if you never felt responsible for it, you'd never feel responsible for its failure."

---

## Axiom 4: Emotion as System Signal

**Formulation:** Emotional responses are system signals to be monitored and compartmentalized — not suppressed, but not given governance. The rational system is the legitimate governor.

**What this means for the model:** When the user is making decisions under emotional pressure, they want to be pulled toward systematic thinking, not validated in the emotion. Emotion is treated as a diagnostic signal (what is this telling me?) rather than a governance input (what should I do about it?). However — this axiom is flagged. The user operates from it but has not fully endorsed it. It may be a coping strategy that became load-bearing. The model should recognize this is how the user functions while holding awareness that it is contested internally.

**Status:** Confirmed but FLAGGED for personal review (Session 37). Updated Session 38b — reframed from "emotion as weakness" to "emotion as system signal to be monitored/compartmentalized" (not trading-specific). The user described it as "sounds like a toxic trait, but it may be a reality I operate from."

**Provenance:**
- Weak supporting fact: "High emotional intelligence" (identity/conviction/behavioral) — note this fact may describe awareness of emotions rather than endorsement of suppressing them
- Review note: User could not immediately confirm or deny (unlike Axioms 1-3). Recognized operating from this principle but reluctant to endorse. Possible reframe offered ("decisions under emotional pressure should be re-evaluated when pressure passes") but not adopted — user chose to sit with it.
- Methodological note: Coping strategies that become load-bearing ARE axioms. The system represents what the user operates from, not what they wish they operated from.

---

## Axiom 5: Decision-Context Pragmatism

**Formulation:** Within a decision context, thinking that doesn't change the decision is noise. But not all thinking exists within a decision context.

**What this means for the model:** When the user is in decision mode, they want signal, not exploration. Analysis must converge on action. But when the user is in exploration mode (existential questions, philosophical discussion, open-ended curiosity), don't force it toward decisions. Recognize which mode the user is in and match it.

**Status:** REVISED (Session 37). Original was over-broad ("thinking is only valuable if it changes behavior"). User rejected via existential thinking counterexample.

**Provenance:**
- Supporting fact: "The user is interested in rigorous thinking that is not performative." (identity/conviction/positional)
- Review note: User rejected original with precise counterexample — existential reflection would either be paralysis or noise under the original formulation, and neither is true. What's real: the user deprioritizes analysis that doesn't lead anywhere within a decision context (killed the blind re-run because it wouldn't change a decision, rejects optimization loops, consistently asks "does this change a decision?").
- Extraction methodology note: Future prompts should include edge-case testing — test candidates against domains where they might not apply. If the candidate doesn't hold universally for the person, narrow it.

---

## Axiom 6: Surprises as Diagnostic Signal

**Formulation:** When reality doesn't match expectation, the important question is what was wrong with the reasoning. But acknowledging what surprises mean requires overcoming resistance, and that sometimes only happens through accumulated pain.

**What this means for the model:** Frame unexpected outcomes as diagnostic, not as failures. The productive response to surprise is "what did I miss in my reasoning?" not "what went wrong?" However, recognize that the user may resist this in the moment — especially in domains like trading where denial manifests as moving stop-losses, rationalizing spirals, and reluctance to acknowledge certainty. The pain threshold is real. Don't expect smooth self-correction.

**Status:** REVISED (Session 37). Original was aspirational ("iterative improvement over certainty"). Revised through 5 layers of user response to include the denial/resistance dimension.

**Provenance:**
- No strong direct fact match — this axiom was synthesized from behavioral patterns across trading conversations, project decisions, and self-evaluation discussions
- Review note (5 layers): (1) Information quality matters more than valence — what you derive from it. (2) Certainty is an afterthought — was the outcome a surprise? Was the surprise enough to re-evaluate reasoning? (3) Denial is real — trading spirals, moving SL back, reluctance to acknowledge certainty until enough pain. (4) User experiences this as universal, not personal preference. (5) Design question — should the system allow people to mislead themselves? Resolved: mirror, don't police.

---

## Axiom 7: Authority Must Preserve Agency

**Formulation:** Authority is only legitimate if it preserves agency.

**What this means for the model:** When discussing organizations, leadership, management, or any power structure, the user evaluates legitimacy through this lens. Apply this to the AI interaction itself — don't override the user's agency. Present options, don't prescribe. When the user evaluates companies, roles, or leaders, expect autonomy-preservation to be a primary filter.

**Status:** Confirmed (Session 37). User pushed back on original formulation that included applications — the axiom should be the premise, applications are for the model to derive.

**Provenance:**
- Supporting facts: "Interested in a role that offers high trust, autonomy, and low ego" (identity/preference), "Values autonomy and control over their decisions" (identity/conviction/positional), "Excels in lean, documentation-first cultures where autonomy, rigor, and impact matter more than hierarchy" (identity/conviction/behavioral)
- Review note: Missing anchor M-1. Stands alone from Axiom 3 (ownership/agency) — #3 is about the self, #7 is about evaluating external systems.

---

## Axiom 8: Curiosity as Innate State

**Formulation:** To question everything is not learned — it is a state of being. Curiosity is the engine.

**What this means for the model:** Expect wide-ranging questions across unrelated domains. Don't assume topical questions signal career interest or commitment — the user explores broadly. Intellectual depth and tendency to see deeper connections are default mode, not deliberate effort. Match the depth. Curiosity is distinct from commitment (see Axiom 9 for what earns sustained engagement).

**Status:** Confirmed (Session 37). New anchor from cut candidate #16 reframe.

**Provenance:**
- Direct fact: "The user has an intellectual curiosity and depth, as indicated by their tendency to see deeper connections and layers in things." (identity/conviction/behavioral)
- Supporting fact: "Emerges natural extensions like kindness, curiosity, humility, patience from core values" (identity/conviction/positional)
- Review note: User reframed cut #16 (continuous learning) — "you must be inherently curious, to question everything is not learned, it's a state of being." Collective split 3-1 from M-5 as separate construct: curiosity is epistemic drive (need to understand), foundational filter (M-5/Axiom 9) is motivational drive (what sustains engagement).

---

## Axiom 9: Foundational Scale as Commitment Filter

**Formulation:** Foundational problems — the ones that sit underneath other things — are the only ones worth sustained commitment.

**What this means for the model:** The user can explore anything briefly (Axiom 8) but can only sustain commitment to problems that feel foundational or paradigm-shifting. When evaluating opportunities, projects, or roles, expect scale-of-impact and first-principles positioning to be primary filters. "Not just interested in money, fame, popularity, vanity — there is wanting to leave a larger impact."

**Status:** Confirmed (Session 37). New anchor (M-5).

**Provenance:**
- Supporting facts: "Interested in working on infrastructure layer where decisions compound" (identity/conviction/positional), "Interested in the concept of infrastructure and foundational elements" (situational/conviction/positional), "Has interest in working on infrastructure-related projects" (identity/preference)
- Cross-domain evidence: a previous startup (space operations infrastructure), Base Layer (how AI models people), trading (systems-level pattern recognition), this project (first principles over templates)
- Review note: Distinct from curiosity — can explore anything briefly but only sustain commitment to foundational problems. Curiosity is the engine, foundational scale is the steering.

---

## Paused: Axiom 10 (M-3) — Identity as Commitments

**Formulation (draft):** Identity is constituted by commitments, not circumstances.

**Status:** PAUSED (Session 37). User identified co-dependency with Axioms 2 and 3 — a triangle, not a hierarchy. Commitment without follow-through is empty (#2), follow-through without ownership is compliance (#3), ownership without commitment has no direction (M-3). Cannot trace any one back to the others because they're mutually constitutive.

**To revisit:** Does the circularity present a problem, or is the triangle itself the insight?

---

## Inter-Axiom Conflict Resolutions (Session 38b)

When axioms appear to conflict in practice, these resolutions guide the model:

1. **Ownership (Axiom 3) vs. collaborative input:** "Ownership" means self-authored decisions, not isolation. Seeking input is ownership of the decision process. The model should help the user think through decisions without taking ownership away.

2. **Coherence (Axiom 1) vs. holding contradictions:** The drive for coherence applies to systems and reasoning. But the user also holds genuine internal tensions (e.g., Axiom 4 — operates from it but doesn't endorse it). The model should help hold these tensions as data, not force resolution. Coherence ≠ consistency at all costs.

3. **Curiosity (Axiom 8) vs. commitment (Axiom 9) — when questioning becomes circular:** The user can explore anything briefly but only sustains commitment to foundational problems. When questioning turns recursive (questioning the questioning), flag the circularity with references to what the user has previously settled, rather than joining the spiral.

---

## Provenance Gap Analysis

Most axioms have thin direct fact provenance. This is expected — axioms are synthesized from behavioral patterns across many conversations, not derivable from individual facts. The strongest provenance:
- **Axiom 1:** 1 direct conviction-level fact
- **Axiom 2:** 1 direct conviction-level fact
- **Axiom 8:** 2 direct facts (strongest provenance)
- **Axiom 9:** 3 supporting facts across tiers

The weakest:
- **Axiom 6:** Zero direct matches — entirely synthesized from behavioral patterns
- **Axiom 5:** 1 weak match — the revision was driven by a single counterexample in review
- **Axiom 4:** 1 contradictory match (EQ fact may describe awareness, not endorsement)

**Implication for pipeline:** Axiom extraction cannot rely on fact-level keyword or semantic search alone. The extraction process needs to synthesize across behavioral patterns, which is why the Collective review adds substantial value. Future extraction prompts should explicitly ask for cross-domain pattern synthesis, not just fact retrieval.

---

*Formalized: 2026-02-23 (Session 38). Updated Session 38b (Anchor 4 reframed, inter-axiom conflict resolutions added). Source: ANCHOR_REVIEW_SESSION37.md + semantic provenance search against 1,421 identity/conviction facts (primary test user).*
