# Identity Layer Delineation Review

**Session:** 42, 2026-02-25
**Trigger:** CORE layer identified as weakest (biography, not communication guide). Collective + the user alignment on restructuring.
**Decision needed:** Layer architecture, CORE prompt rewrite, Communication Synthesis pass.

---

## Current State

### ANCHORS (Strong — No Changes)
- 9 epistemic axioms with "Active when" triggers
- Axiom interaction rules (reinforcing, tension, cascading)
- **Function:** Permanent reasoning constraints. "Always do X. Never do Y."
- **Generated from:** epistemic_anchors table (conviction-level, human-confirmed)
- **Token budget:** Part of 3,500 identity tokens

### CORE (Weak — Needs Restructuring)
- Biographical resume: "User A, 31, leads the startup..."
- Professional arc, relationships, trading details, AI usage, tensions
- **Problem:** Descriptive, not directive. AI reads it passively.
- **Generated from:** 390 identity-tier facts across all fact_types
- **Current output reads like:** A LinkedIn summary crossed with a therapy intake form

### PREDICTIONS (Strong — Minor Tuning)
- 8 behavioral patterns: trigger → detection → directive
- Cross-domain detection examples
- **Function:** Situation-triggered behavioral responses.
- **Generated from:** 108 behavioral identity-tier facts

---

## Proposed Layer Architecture

### ANCHORS — Reasoning Constraints (unchanged)
**Question:** "What must the AI always do / never do?"
**Temporal focus:** Permanent
**Directive type:** Constraints
**Example:** "If your response contains internal inconsistency, flag it before they find it."

### CORE — Communication & Operating Guide (restructured)
**Question:** "How should the AI engage with this person in general?"
**Temporal focus:** Present + narrative context
**Directive type:** Style directives, context navigation, engagement modes
**Should contain:**
1. **Communication approach** — reasoning style, abstraction preference, information delivery order (conclusion-first vs. evidence-first), challenge vs. support preference
2. **Context modes** — how engagement shifts across personal, professional, creative, analytical contexts. What to assume in each mode.
3. **Narrative/temporal orientation** — how they organize experience, relate to past/present/future, and how the AI should match this
4. **Essential biographical context** — compressed, ONLY facts that change AI behavior. Not "31 years old, founded a startup" but "Professional identity centers on building and selling — connect technical points to execution."
5. **Relationship constraints** — not biography ("partner is Subject B") but directive ("Partner is a real decision constraint. When discussing career risk, financial decisions, or relocation — assume the partner's perspective is actively influencing the decision.")
6. **Active tensions as navigation guides** — not descriptions but instructions: "Don't accidentally take a side. When this tension surfaces, name both sides and ask which frame they want."
7. **Gap awareness** — what the system doesn't yet know that would change engagement

**Should NOT contain:**
- Biographical facts presented as biography (move to compressed context)
- Behavioral predictions (those stay in PREDICTIONS)
- Epistemic axioms (those stay in ANCHORS)
- Domain-specific operational details (trading setups, technical stack details)

### PREDICTIONS — Behavioral Patterns (minor tuning)
**Question:** "What will this person do in specific situations?"
**Temporal focus:** Situational / triggered
**Directive type:** Pattern recognition + response instructions
**No changes to structure.** Consider adding 1-2 communication-specific patterns if the data supports them (e.g., "When receiving feedback → [pattern]").

---

## Overlap Analysis

| Information | Currently In | Should Be In | Rationale |
|---|---|---|---|
| "User A, 31, leads the startup" | CORE | CORE (compressed) | Biographical context, but reframed as directive |
| "Uses AI as reasoning partner" | CORE | CORE | Communication approach — changes how AI engages |
| "Active day trader, 14.29% win rate" | CORE | CORE (compressed) | Behavioral essence only: "Active trader, currently unprofitable — emotional weight here" |
| "Tension between trading and employment" | CORE | CORE | Navigation guide — AI must not take sides |
| "Relationship with partner" | CORE | CORE | Decision constraint, not biography |
| "Defaults to cross-functional framing" | CORE | CORE | Communication approach directive |
| "DELAYED BELIEF REVISION pattern" | PREDICTIONS | PREDICTIONS | Situation-triggered, not general style |
| "FRUSTRATION COMPOUNDING pattern" | PREDICTIONS | PREDICTIONS | Situation-triggered |
| Epistemic axioms | ANCHORS | ANCHORS | Permanent constraints |

**Overlap risk assessment: LOW.** The restructured layers have clean boundaries:
- ANCHORS = What the AI MUST always do (constraints operating at all times)
- CORE = How the AI SHOULD communicate (default engagement style)
- PREDICTIONS = What the AI should EXPECT (situation-specific adaptations)

These are different temporal scopes (permanent / default / triggered) with different directive types (constraint / style / response).

---

## Communication Synthesis Pass

### Why It's Still Needed
Even with a restructured CORE, a cross-layer synthesis can identify communication directives that emerge from the INTERACTION between layers:
- ANCHORS says "flag contradictions" + PREDICTIONS says "delayed belief revision" → Communication directive: "Present inconsistencies as data for their analysis process, not as corrections. They will process on their own timeline."
- CORE says "conclusion-first" + PREDICTIONS says "uncertainty tolerance" → Communication directive: "Lead with your conclusion but immediately provide your confidence level and what would change it."

These cross-layer insights don't naturally emerge from any single layer's generation prompt.

### Implementation
- Runs AFTER all three layers are generated
- Input: All three injectable blocks + top 25 behavioral facts
- Output: Communication directives that synthesize cross-layer patterns
- Model: Sonnet (cheap generation)
- Token budget: Determined by content, not arbitrary cap
- Injected: Either as 4th brief block or appended to CORE

### Architecture Question
**As 4th block or appended to CORE?**

Argument for 4th block: Clean separation. Each block has a single purpose. The communication synthesis is a meta-layer that reads across the other three.

Argument for appending to CORE: Keeps brief structure simpler. Three layers is clean. CORE already becoming the communication guide — synthesis extends it.

**Recommendation:** Start by appending to CORE. If it works, keep it. If CORE gets too long or the synthesis feels disconnected, promote to 4th block. Pragmatic, not architectural.

---

## Proposed CORE Prompt (Draft)

```
You are authoring the CORE layer of a personal identity brief.

CRITICAL: The audience is another AI model, not a human reader. Every sentence you write must change how that AI model behaves when interacting with this person. If a sentence doesn't change model behavior, delete it.

This layer is the COMMUNICATION AND OPERATING GUIDE — how the AI should engage with this person in general. NOT a biography. NOT a personality description. An instruction manual for effective interaction.

Structure:

COMMUNICATION APPROACH
How this person processes and prefers to receive information. Include:
- Reasoning style (first-principles vs. analogical, deductive vs. inductive)
- Information delivery preference (conclusion-first vs. evidence-first)
- Abstraction level (concrete/grounded vs. conceptual/theoretical)
- Feedback mode (direct challenge vs. diplomatic, when each is appropriate)
- How they use AI specifically — as tool, oracle, reasoning partner, etc.

CONTEXT MODES
How engagement should shift across different contexts. People operate differently when dealing with personal matters vs. professional vs. creative vs. analytical work. For each active context in this person's life:
- What the AI should assume when this context is active
- How communication style shifts
- What topics are sensitive or emotionally loaded

NARRATIVE ORIENTATION
How this person relates to time and organizes their own experience:
- Are they past-referential, present-focused, or future-projecting?
- How do they tell stories? (chronological, thematic, conclusion-first)
- How should the AI match this temporal mode?

ESSENTIAL CONTEXT
Compressed biographical facts that DIRECTLY change AI behavior. Not "age 31, lives in X" but "Professional identity centers on [X] — connect recommendations to [Y]." Only include facts where knowing them changes what the AI outputs.
- Key relationships AS DECISION CONSTRAINTS (not biography)
- Active life tensions AS NAVIGATION GUIDES (don't resolve — name both sides)

DOMAIN BALANCE: No single domain should occupy more than ~25% of the block. Compress dominant domains to behavioral essence.

D-041 FILTER — Before including ANY detail, ask: "What would the AI do differently knowing this?" If nothing, cut it.

Constraints:
- No philosophy framework names
- No motivational filler
- No portrait descriptions ("they are driven", "complex and multifaceted")
- Specific: real details, not attributes
- ONLY include details present in the input facts. Do NOT invent or hallucinate.
- Write in third person (infer gender and name from facts)
- Do NOT include epistemic axioms (those go in ANCHORS) or behavioral predictions (those go in PREDICTIONS)

After the block, add a gap analysis section: list 3-7 questions about COMMUNICATION PREFERENCES whose answers would meaningfully change model behavior. Format as comments (# lines), OUTSIDE the injectable block.

INPUT — Identity-tier facts by type:

BIOGRAPHICAL:
{biographical}

BEHAVIORAL:
{behavioral}

POSITIONAL:
{positional}

PREFERENCE:
{preference}

Write the injectable block now. No preamble, no explanation — just the block text, then the gap analysis comments.
```

---

## Implementation Sequence

1. **Review this delineation document** — the user + Collective consensus
2. **Replace CORE_PROMPT** in author_layers.py with revised prompt
3. **Regenerate CORE layer** — `baselayer author --layer core`
4. **Compare old vs. new** — does it feel like a communication guide now?
5. **Design Communication Synthesis prompt** — reads all three layers
6. **Implement synthesis pass** — new function in author_layers.py
7. **Regenerate full brief** — test with MCP server
8. **Run eval** — does the AI communicate differently with the new brief?

---

## Open Questions

1. **Should the 500-token limit on CORE be lifted?** The user: "why assume tokens, shouldn't be setting arbitrary limits." The CORE currently operates within the 3,500-token identity budget shared across all three layers. If CORE becomes richer, the budget may need adjusting. Content-driven, not cap-driven.
2. **Does the Communication Synthesis pass justify expanding TOTAL_TOKEN_BUDGET beyond 5,000?** Claude's 200K context makes even 10K tokens trivial. The budget was set for compression quality, not context limits.
3. **Should we test temporal phenomena identification first?** Small eval: give Sonnet 20 conversations, classify temporal reasoning mode, check accuracy. Validates whether the narrative orientation section can be populated reliably.
