# Provenance-Traced Evaluation Framework

## Status: DRAFT — Replaces judge-dependent evaluation where possible
## Date: 2026-03-07
## Triggered by: Marks BCB judge anomalies + research synthesis (PersonaGym, RVBench, Psych Fidelity, Narrative Identity)

---

## The Problem with Current Evaluation

Every published persona evaluation framework — PersonaGym (EMNLP 2025), RVBench (2025), PersonalLLM (ICLR 2025), and our own BCB — relies on LLM-as-judge scoring on subjective dimensions. This creates three failures:

1. **"Voice" conflates syntax and reasoning.** A response can sound like someone (word choice, tone) while reasoning nothing like them. Or reason exactly like them while sounding modern and generic. These are independent axes but judges conflate them. (Evidence: Marks P1 — Opus scored C5c R:1 S:1 despite correct reasoning; Sonnet scored same response all 5s.)

2. **Judge scores are opaque.** When two judges disagree (Opus: 1, Sonnet: 5), there is no way to adjudicate. The score is an opinion with no audit trail. A human reviewer cannot inspect WHY the score was given.

3. **Nobody else has provenance.** Base Layer's unique infrastructure — vector similarity, claim-to-source tracing, axiom mapping — enables mechanistic evaluation that no other identity system can perform. Not using it is leaving our strongest differentiator on the table.

## The Principle

**Evaluation should produce evidence, not opinion.**

Every score should be traceable: "The response said X → that traces to brief claim Y at similarity Z → the axiom applied was W." A human can inspect the chain and decide whether it holds. The eval becomes transparent and auditable.

## The Framework: Four Mechanical Layers

### Layer 1: Brief Activation (BA)

**Question:** Did the brief actually influence the response?

**Method:**
1. Chunk each response into claim-level segments
2. Embed each segment (same MiniLM embedder used in pipeline)
3. For each segment, find the nearest brief claim by cosine similarity
4. Compute mean and max similarity across all segments

**Metrics:**
- **BA-mean:** Average similarity of response segments to their nearest brief claims
- **BA-max:** Highest single similarity between any response segment and any brief claim
- **BA-delta:** BA-mean(C5c) minus BA-mean(C1). Positive = brief is activating.

**Properties:**
- Fully mechanical — no judge needed
- Human-auditable: "This response passage matched this brief claim at 0.71 similarity"
- Blind: similarity computed without knowing which condition produced the response

**Threshold:** BA-delta > 0 required. If C5c responses are not measurably closer to brief content than C1, the brief is not activating.

---

### Layer 2: Provenance Coverage (PC)

**Question:** What fraction of the response's claims trace back to the brief?

**Method:**
1. Extract claims from the response (claim extraction — already implemented in CMCS pipeline)
2. For each claim, run provenance trace against brief content (already implemented in verify_provenance.py)
3. A claim is "covered" if its nearest brief match exceeds a similarity threshold (e.g., 0.60)
4. Compute coverage ratio

**Metrics:**
- **PC-ratio:** (claims with provenance) / (total claims). Higher = more of the response is brief-derived.
- **PC-novel:** (claims WITHOUT provenance) / (total claims). These are claims the model added beyond the brief — not necessarily bad, but should be flagged.
- **PC-delta:** PC-ratio(C5c) minus PC-ratio(C1). Positive = brief is sourcing more claims.

**Properties:**
- Mechanical for extraction + matching; claim extraction may use LLM but output is inspectable
- Human-auditable: "This response made 8 claims. 6 trace to brief content. Here are the traces."
- Directly leverages existing provenance infrastructure

**Threshold:** PC-delta > 0 required. PC-ratio(C5c) > 0.50 expected (majority of claims should trace to brief).

---

### Layer 3: Reasoning Chain Reconstruction (RCR)

**Question:** For each conclusion, what interpretation was applied and does it match a documented axiom?

**Method:**
1. For each substantive conclusion in the response, decompose into: **observation** (what input was attended to) → **framework** (what reasoning pattern was applied) → **conclusion** (what was decided)
2. Match the **framework** step against the brief's documented axioms
3. Score: does the framework match an axiom? Is the axiom correctly applied?

**Metrics:**
- **RCR-match:** Fraction of conclusions where the applied framework matches a documented axiom
- **RCR-misapply:** Fraction where an axiom was referenced but applied incorrectly (hallucinated reasoning)
- **RCR-generic:** Fraction where no axiom was applied — generic domain knowledge used instead

**Properties:**
- Partially mechanical (axiom matching by similarity), partially requires narrow LLM judgment
- But the LLM question is narrow and verifiable: "Does this conclusion follow from axiom X?" — not "Does this sound like the person?"
- Human-auditable: "The response concluded Y. The reasoning path was: saw A → applied axiom B → concluded Y. Axiom B says [text from brief]."

**Threshold:** RCR-match(C5c) > RCR-match(C1). RCR-generic(C5c) < RCR-generic(C1).

---

### Layer 4: Priority Ordering (PO)

**Question:** When multiple axioms apply, does the response weight them the way the brief does?

**Method:**
1. Identify responses where multiple axioms are relevant (most substantive questions trigger 2-3 axioms)
2. Determine which axiom the response treated as primary (first mentioned, most weight given, or used as tiebreaker)
3. Compare against the brief's axiom ordering / hierarchy
4. Score alignment

**Metrics:**
- **PO-align:** Fraction of multi-axiom responses where priority ordering matches the brief's hierarchy
- **PO-invert:** Fraction where axioms are present but priority is reversed (e.g., brief says "price-value first, then cycle position" but response leads with cycle position)

**Properties:**
- Requires LLM judgment but on a narrow, structured question: "Which of these two axioms did the response treat as primary?"
- Human-auditable: "The response applied axioms A and B. It prioritized A over B. The brief's hierarchy places A above B. Aligned."
- Directly tests the insight from RVBench: models can state values but fail to prioritize correctly under pressure

**Threshold:** PO-align(C5c) > PO-align(C1). PO-invert(C5c) < 0.20.

---

## How This Replaces Current BCB Dimensions

| Current BCB Dimension | Problem | Replacement |
|---|---|---|
| **Recognition** ("does it sound like this person?") | Conflates syntax and reasoning; subjective | **BA** (did the brief activate?) + **PC** (do claims trace to brief?) |
| **Calibration** ("right style and register?") | Penalizes modern subjects; rewards surface imitation | **PO** (are axioms prioritized correctly?) |
| **Depth** ("engages structural question?") | Least problematic — somewhat measurable | **RCR** (reasoning chain traces to axioms, not generic knowledge) |
| **Usefulness** ("actionable and specific?") | Not identity-specific; any good response scores high | **PC-novel** (flags claims beyond brief — useful additions vs. hallucination) |
| **Specificity** ("requires knowledge of this person?") | Circular — judge decides if knowledge is specific | **RCR-match** (mechanically checks: did this require a specific axiom?) |
| **Anachronism Check** | Wrong for modern subjects; penalizes correct calibration | **Dropped entirely** |

## What Remains Judge-Dependent

Two narrow uses of LLM judgment survive:

1. **Claim extraction** (Layer 2) — Segmenting a response into discrete claims still benefits from LLM parsing. But the output is inspectable text, not a score.

2. **Axiom application verification** (Layer 3, Layer 4) — "Does this conclusion follow from this axiom?" and "Which axiom was treated as primary?" are narrow, verifiable questions. Unlike "does this sound like the person?", a human can check the judge's answer against the text.

Both are structured extraction tasks with auditable outputs, not subjective rating tasks.

## What This Means for Published Evaluation

No published persona evaluation framework has:
- Mechanical verification of whether a persona brief actually influenced a response
- Claim-level provenance tracing from response back to source material
- Reasoning chain decomposition with axiom matching
- Human-auditable evidence chains at every layer

PersonaGym uses LLM judges on 5 subjective dimensions. RVBench uses psychometric questionnaires (forced-choice, better than Likert, but still self-report). PersonalLLM uses reward model ensembles. All produce numbers without audit trails.

Provenance-traced evaluation is a methodological contribution independent of Base Layer's pipeline. It applies to any identity/persona system that maintains source provenance.

## Implementation Path

### Phase 1: Layer 1 + Layer 2 (fully mechanical)
- Embed existing C1/C5c responses from Marks and Franklin
- Run blind similarity against brief claims
- Extract claims and trace provenance
- Compute BA-delta and PC-delta
- **No new API calls needed** — uses local embeddings + existing provenance infrastructure
- **Cost: ~$0 (local compute only)**

### Phase 2: Layer 3 (narrow LLM judgment)
- Decompose responses into observation → framework → conclusion chains
- Match frameworks to axioms by similarity
- LLM verifies matches on borderline cases
- **Cost: ~$1-2 per subject (claim extraction + verification)**

### Phase 3: Layer 4 (priority ordering)
- Identify multi-axiom responses
- Determine priority ordering
- Compare against brief hierarchy
- **Cost: ~$0.50-1 per subject**

### Phase 4: Validation
- Run on Franklin (known-good data) and Marks (fresh data)
- Compare provenance-traced scores against existing judge scores
- Identify where they agree (judge was measuring the right thing) and disagree (judge was measuring voice, not reasoning)
- The P1 anomaly is the test case: provenance-traced eval should show C5c_P1 IS brief-faithful despite judge scoring it R:1

## Relationship to Other Frameworks

- **BCB-0.1:** Provenance-traced eval replaces the SRS judge dimensions. CR (provenance coverage) is already mechanical. DRS fidelity finding stands — provenance tracing can distinguish weak absorption (no brief trace) from faithful absorption (brief tension traced).
- **ADRB:** Provenance-traced eval IS the right methodology for ADRB. Axiom-conditioned reasoning is exactly "did this axiom produce this reasoning chain?" — Layer 3 measures this directly.
- **EVAL_PROMPT_REDESIGN.md:** Superseded for mechanical layers. Judge prompt redesign still relevant for Layers 3-4 where narrow LLM judgment is needed, but the scope of what the judge evaluates shrinks dramatically.
- **Twin-2K:** Different methodology (preference prediction accuracy). Provenance tracing doesn't apply — Twin-2K is behavioral prediction, not reasoning evaluation.

---

## Research Grounding

### From the literature (5 research agents, 2026-03-07):

**Psychological Fidelity (Kozlowski & DeShon, 2004; Rehmann et al., 1995):**
Physical fidelity (looks right) and psychological fidelity (produces same cognitive processes) are independent dimensions. A simulation can look perfect but engage wrong reasoning, or look nothing like reality but engage identical cognitive processes. Current persona evals measure physical fidelity. We need psychological fidelity. Provenance tracing measures whether the same reasoning structures were activated — process fidelity.

**RVBench (Wang et al., 2025):**
Models score well on stated values (Rating) but fail on value prioritization under pressure (Ranking). The gap between "knowing what to say" and "knowing how to prioritize" is the core measurement challenge. Layer 4 (Priority Ordering) directly addresses this.

**PersonaGym (EMNLP 2025):**
Their own case study showed PersonaGym scored 4.0+ when humans scored 2.0 on Linguistic Habits. LLM judges cannot reliably evaluate surface-level voice matching. Confirms: drop voice as an evaluation target entirely.

**Narrative Identity (Ricoeur, Taylor, Korsgaard):**
Faithful representation includes tensions and self-doubt (ipse-identity). A model that rigidly deflects is less faithful than one that engages documented tensions. Provenance tracing can distinguish "engaged a real tension from the brief" (faithful) from "collapsed without brief grounding" (failure) — something current DRS cannot do.

**PersonalLLM (ICLR 2025):**
Evaluates preference matching through reward model ensembles. No provenance, no reasoning chain analysis, no human auditability. Demonstrates the field has no mechanistic evaluation methodology — the gap we fill.
