# Session 100 Plan — Structured Pipeline + Outreach Push

## Context

Session 99 accomplished:
- H3 prompts adopted (domain-agnostic guard, detection balance, domain suppression)
- 44 subjects fully H3-authored with zero topic skew
- Prompt ablation study published on research page + LinkedIn
- Scott Alexander emailed with magic link (H3 V2)
- Magic link auth fixed (Route Handler pattern)
- Core parser fixed for flexible separators
- Serving layer spec drafted
- Temporal prediction test spec drafted
- 16 Wave 4/5 email drafts generated
- Visionist facts corrected in Aarik's model

## Outstanding Issues from S99

### Critical (Blocking Outreach)
1. **Pronouns: Maggie Appleton shows "he" throughout brief.** Compose step infers gender. Fix: enforce they/them universally in compose prompt. Rerun Maggie.
2. **Pages not seeded.** 44 subjects H3-authored locally but not pushed to website. Need seed run.
3. **Version history state.** Most pages had history cleared. Need clean V1 state (no version history for first-time pages, V1→V2 for upgrade pages).

### High Priority (Quality)
4. **Prediction format inconsistent.** Some subjects use labeled Detection/Directive/False Positive, others use prose. Need deterministic scaffolding via structured outputs.
5. **Kevin Kelly brief opens with biographical anecdote** (hitchhiking) instead of reasoning pattern. Compose quality — the pattern underneath is correct but the ordering breaks H3 principles.
6. **AI topic mentions in Kevin Kelly (25) and Dan Shipper (24).** Layers are clean (H3 guard works), but compose step reassembles topic-specific content from the layers. Compose prompt needs its own domain guard.
7. **Anchor cap not holding.** H3 says 8-10 max, most subjects produce 13-16. Decide: enforce cap or accept if anchors are genuinely distinct.

### Medium Priority (Pipeline)
8. **Structured outputs for layer generation.** Move from free-form markdown to JSON schema constrained decoding. Deterministic format, parseable output, no regex parsing in seed pipeline.
9. **Compose prompt domain guard.** Add: "If a paragraph could only apply to one subject domain, compress to the pattern underneath."
10. **Fact cap for large corpora.** Tomasz (25K facts) hit Vercel payload limit. Auto-cap facts at 2,000 in seed pipeline.
11. **Carlini scraping.** Add nicholas.carlini.com to subject pipeline.

### Research (Not Blocking)
12. **Temporal prediction test.** Split Aarik's 1,892 conversations by year. Build 2024 model, test against 2025/2026. ~$20.
13. **Stacking test scoring.** 100 responses across 5 conditions logged but unscored.
14. **Serving layer Phase 1.** Activation matching MVP.

## Proposed Approach

### Phase 1: Structured Output Adoption (Predictions Only — Test)

**Goal:** Validate that structured outputs maintain content quality while guaranteeing format.

**Schema:**
```python
class Prediction(BaseModel):
    id: str                    # "P1"
    name: str                  # "CONFIRMATION GATE"
    trigger: str               # "When approaching any decision point"
    response: str              # "refuses to act until multiple signals converge"
    detection: list[str]       # 3 domain examples
    directive: str             # what the AI should do (long prose)
    false_positive_warning: str  # when pattern is NOT active

class PredictionsLayer(BaseModel):
    preamble: str              # framing sentence
    predictions: list[Prediction]  # 6-8 items
```

**Test:** Run one subject (Scott Alexander) with structured output vs current free-form. Compare:
- Content quality (do the predictions capture the same patterns?)
- Prose quality (are the descriptions as rich, or more formulaic?)
- Format compliance (are Detection/Directive/FP always present?)
- Word count (does constrained decoding produce shorter output?)

**Decision gate:** If structured output quality matches or exceeds free-form, adopt for all layers. If it produces more formulaic output, keep free-form with better prompt scaffolding.

### Phase 2: Pronoun + Compose Fixes

**Changes to compose prompt (`agent_pipeline.py`):**
1. Replace `Use pronouns ("he", "she", "they")` with `Use "they/them" pronouns exclusively. Do not infer or assign gender.`
2. Add domain guard: `The brief should capture behavioral patterns, not topic positions. If a paragraph describes beliefs about a specific domain (AI, policy, markets) rather than a reasoning pattern that applies across domains, compress to the pattern underneath.`
3. Update across all layer prompts: enforce they/them in `{pronouns}` substitution.

**Test:** Rerun Maggie Appleton. Verify they/them throughout. Check that content quality is maintained.

### Phase 3: Seed All 44 Subjects to Website

**Approach:**
- First-time subjects (Wave 4/5): seed with no version history. These are V1 (H3).
- Existing subjects (Wave 1/2/3): decision needed — seed as noSnapshot overwrite (clean V1 with H3) or seed with version history (V1 old → V2 H3).

**Recommendation:** For this round, seed all with noSnapshot. Label as V1 (H3). When the structured output pipeline is finalized and compose domain guard is proven, THAT becomes V2. Don't create version history for an intermediate state.

**Fact cap:** Auto-cap facts at 2,000 in `build_payload` for subjects with >5K facts (Tomasz, Eric Schwitzgebel, Visakan, Zvi, etc.).

**Parser:** Already fixed for flexible separators. Verify on all subjects before seeding.

### Phase 4: Email Drafts + Magic Links

**Wave 4/5 first outreach (16 subjects):**
- Drafts already generated at `drafts/wave45_email_drafts.md`
- Need: email addresses for ~13 subjects
- Need: magic links generated at send time
- Format: "XXXX facts from XXX items. AI's operating guide for [first name]."

**Wave 1/2/3 follow-up (existing subjects):**
- These now have H3 models (better than what was originally sent)
- Follow-up email: "Upgraded the model — it now focuses on how you reason rather than what you write about."
- Include magic link + identity model attachment

**Maggie Appleton:** Personal email (she engaged). Fix pronouns first.
**Scott Alexander:** Already sent. Monitor for response.

### Phase 5: Structured Output Full Adoption (If Phase 1 Passes)

**Schemas for all three layers:**

```python
# Anchors
class Axiom(BaseModel):
    id: str
    name: str
    description: str      # fused description-directive
    active_when: str      # detection trigger
    contested: bool = False

class AxiomInteraction(BaseModel):
    pair: str             # "A1 × A6"
    description: str
    failure_mode: str

class AnchorsLayer(BaseModel):
    preamble: str
    axioms: list[Axiom]
    interactions: list[AxiomInteraction]

# Core
class ContextMode(BaseModel):
    id: str
    name: str
    description: str

class CoreLayer(BaseModel):
    communication_approach: str
    context_modes: list[ContextMode]
    narrative_orientation: str
    essential_context: str

# Predictions (from Phase 1)
class PredictionsLayer(BaseModel):
    preamble: str
    predictions: list[Prediction]
```

**Benefits:**
- No regex parsing in seed pipeline — structured data flows directly
- Deterministic format across all subjects
- Pronoun enforcement via prompt (schema doesn't handle this — it's content, not structure)
- Parseable for serving layer activation matching

**Render to markdown:** After generation, render the structured JSON into markdown for the identity_model.md file. The JSON is the source of truth; the markdown is the human-readable view.

### Phase 6: Research + Evaluation

**Temporal prediction test (~$20):**
1. Split Aarik's conversations by year
2. Build 2024-only identity model with H3
3. Test predictions against 2025/2026 behavior
4. 4 evaluation methods (Twin-2K, pattern matching, axiom stability, fact prediction)

**Stacking test scoring:**
- 100 responses logged across 5 conditions
- Score and publish results
- Add to research page (currently "Coming Soon")

**Structured output quality comparison:**
- Same subject, free-form vs structured
- Side-by-side prose quality evaluation
- Decision: adopt structured outputs or keep free-form with better scaffolding

## Priority Order

1. **Pronouns fix + Maggie rerun** (30 min) — blocks her outreach
2. **Structured output test on Scott** (30 min) — informs pipeline direction
3. **Seed all 44 to website** (1-2 hours) — blocks all outreach
4. **Email address research** (1 hour) — blocks Wave 4/5 sends
5. **Generate magic links + finalize drafts** (30 min) — enables Monday sends
6. **Compose domain guard + Kevin Kelly rerun** (1 hour) — quality improvement
7. **Full structured output adoption** (2-3 hours) — pipeline upgrade
8. **Temporal prediction test** (2 hours) — research

## Risk Assessment

- **Structured outputs might reduce prose quality.** Mitigated by Phase 1 test before full adoption.
- **44 subjects seeded at once could surface new parser bugs.** Mitigated by pre-seed validation (parser check on all subjects before POSTing).
- **Compose domain guard might over-correct.** Could strip legitimate domain context that IS behavioral. Test on 2-3 subjects before batch run.
- **They/them for all subjects might feel impersonal.** The content personalizes — the pronouns don't need to. This is a deliberate tradeoff for correctness.

## Open Decisions (Need Aarik Input)

1. **Anchor cap: enforce or accept?** Most subjects produce 13-16 anchors. The H3 prompt says 8-10. Should we tighten enforcement or accept that 13-16 is the natural range for this model?
2. **Version history on seed:** Seed all as V1 (H3) with no history, or create V1→V2 history for existing subjects?
3. **Structured outputs: adopt or test first?** Can go straight to adoption for predictions (format is well-defined) while keeping free-form for anchors/core (more prose-heavy).
4. **Which subjects to prioritize for Monday outreach?** Wave 4/5 are first-time (higher novelty). Wave 1/2/3 follow-ups have existing relationship.

## Cost Estimate

| Item | Cost |
|------|------|
| Structured output test (1 subject × 3 layers) | ~$0.15 |
| Maggie recompose | ~$0.11 |
| Kevin Kelly recompose | ~$0.11 |
| Seeding (API calls, no LLM cost) | $0 |
| Temporal prediction test | ~$20 |
| Stacking test scoring | ~$15 |
| **Total (pipeline work)** | **~$0.40** |
| **Total (with research)** | **~$35** |
