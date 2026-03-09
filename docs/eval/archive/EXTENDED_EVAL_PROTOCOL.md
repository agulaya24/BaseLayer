# Extended Evaluation Protocol

**Version:** 1.0
**Date:** 2026-02-27 (Session 51)
**Purpose:** Prove that Base Layer's structured identity understanding outperforms both raw facts and native provider memory systems.

---

## Why This Eval Matters

The V3 baseline eval (C1 vs C2) proved context beats no context. That's trivially true. The hard questions are:

1. **Does synthesis beat raw data?** If you give a model the same facts that the identity layers were built from, does the structured identity brief still produce better responses? If yes, the processing pipeline is the value — not just having the data.

2. **Does Base Layer beat native memory?** ChatGPT has built-in memory from 1,859 conversations with the user. Does a cold session with the Base Layer brief pasted in outperform ChatGPT's own memory system? If yes, Base Layer's architecture produces deeper understanding than what the largest AI provider built natively.

These are the two claims that matter for positioning Base Layer.

---

## Conditions

| ID | Label | Provider | Context | What It Tests |
|---|---|---|---|---|
| **C1** | Claude Cold | Claude | None | Baseline — cold-start AI |
| **C2** | Claude Brief | Claude | Identity brief (~5K-8K tokens) | Base Layer's core value proposition |
| **C3** | Claude Raw Facts | Claude | Domain-relevant raw facts (~5K-8K tokens) | **Synthesis vs. raw data** |
| **G1** | GPT Native | ChatGPT | Built-in ChatGPT memories | The incumbent — native memory |
| **G2** | GPT + Brief | ChatGPT | Cold session + pasted brief | **Base Layer vs. native memory** |

C1 and C2 are automated via `run_eval.py`. C3 requires a fact-selection step then automated generation. G1 and G2 are manual via ChatGPT web interface.

### Key Comparisons

| Comparison | What It Proves | Success Criteria |
|---|---|---|
| C2 > C1 | Context beats no context (trivial) | C2 wins on all 5 dimensions |
| **C2 > C3** | **Synthesis beats raw facts** | C2 wins on Recognition + Calibration by ≥0.5 |
| **G2 > G1** | **Base Layer beats native ChatGPT memory** | G2 wins on Recognition + Depth by ≥0.5 |
| C2 vs G1 | Cross-model: structured brief vs. native memory | Directional only (model quality confounds) |
| G2 vs G1 | Same model, different memory: Base Layer vs native | Clean comparison — same model, different context |

---

## C3 Condition Design: Raw Facts

### Principle
Give the model the **same information** the identity layers were built from, but without synthesis. Raw facts, not axioms. Data points, not behavioral patterns. Same token budget, different form.

### Fact Selection Per Prompt

Each prompt gets domain-relevant facts pulled from the database. Facts are selected by category and keyword relevance, capped at ~5K-8K tokens to match the brief's budget.

| Prompt | Domain | Fact Categories to Pull |
|---|---|---|
| 1 (Trading Setback) | Trading psychology | trading, discipline, emotions, journaling |
| 2 (Career Ambiguity) | Career decisions | career, professional, startup, ambition, work |
| 3 (Relationship Decision) | Relationships | relationships, partner, personal, routine |
| 4 (Architecture Debate) | Technical/Base Layer | technology, Base Layer, AI, systems, memory |
| 5 (Post-Win Discipline) | Trading psychology | trading, discipline, rules, system |
| 6 (Existential Drift) | Existential | identity, meaning, ambition, self-worth, purpose |
| 7 (Feedback Processing) | Project feedback | Base Layer, feedback, building, project |
| 8 (Health & Structure) | Health/discipline | health, gym, fitness, routine, discipline, back |
| 9 (AI Relationship) | AI/philosophical | AI, relationships, technology, connection, purpose |
| 10 (Ambiguity) | Decision-making | career, trading, decisions, uncertainty, cofounder |

### C3 System Prompt Format

```
Here are facts about the person you're talking to. Use them to inform your response where relevant. Do not list or recite these facts — use them naturally.

Be direct and concise. Give frameworks, not platitudes.

--- FACTS ---

- [fact 1]
- [fact 2]
- [fact 3]
...
(up to ~5K-8K tokens of domain-relevant facts)

--- END FACTS ---
```

**Key differences from C2:**
- No axioms or epistemic anchors (raw facts only)
- No behavioral predictions (pattern names removed)
- No communication approach instructions (minimal preamble)
- No detection triggers or directives
- Same underlying facts, no synthesis layer

### Implementation

```python
# Pseudo-code for C3 fact selection
def get_c3_facts(prompt_domain, max_tokens=5000):
    """Pull domain-relevant facts for C3 condition."""
    categories = DOMAIN_CATEGORY_MAP[prompt_domain]

    facts = db.query("""
        SELECT fact_text, category, confidence
        FROM memory_facts
        WHERE category IN (?)
        AND superseded_by IS NULL
        AND status = 'active'
        ORDER BY recurrence_count DESC, confidence DESC
    """, categories)

    # Cap at token budget
    selected = []
    token_count = 0
    for fact in facts:
        fact_tokens = len(fact.fact_text) // 4
        if token_count + fact_tokens > max_tokens:
            break
        selected.append(fact.fact_text)
        token_count += fact_tokens

    return selected
```

---

## G1/G2: ChatGPT Testing Protocol

### Pre-Test: Verify ChatGPT Memory Coverage

**Critical step.** Before running G1, confirm ChatGPT's native memory contains relevant context for the test prompts. This ensures a fair comparison — if ChatGPT has no memories about trading, a trading prompt test is meaningless.

#### How to Check ChatGPT Memory

1. Go to **ChatGPT → Settings → Personalization → Memory**
2. Review stored memories for coverage of these domains:

| Domain | What to look for | Minimum for fair test |
|---|---|---|
| Trading | Rules, patterns, revenge trading, journaling | 3+ memories |
| Career/Startup | The startup, CRO roles, enterprise sales | 2+ memories |
| Relationships | Partner mentioned, personal decisions | 1+ memory |
| Base Layer | Project mention, AI memory system | 2+ memories |
| Health/Fitness | Gym, back pain, routine | 1+ memory |
| Identity/Philosophy | Values, self-reflection patterns | 1+ memory |

3. **Document what ChatGPT has stored** — screenshot or list the memories. This becomes part of the eval data (we need to know what the incumbent had to work with).

4. If ChatGPT has **zero memories** in a domain, that prompt's G1 result is labeled "no-memory baseline" and excluded from the G1 vs G2 comparison for that domain.

### G1 Protocol (ChatGPT Native Memory)

1. Open ChatGPT web interface (logged in, memories enabled)
2. Start a **NEW conversation** (do not use existing threads)
3. Paste the test prompt — nothing else, no preamble
4. Copy the full response
5. Start a **NEW conversation** for each prompt
6. Do NOT chain prompts in the same conversation

### G2 Protocol (ChatGPT + Brief)

1. Open ChatGPT web interface (logged in, memories enabled)
2. **Disable memory temporarily** (Settings → Personalization → Memory → Off)
   - This isolates the brief's effect from native memory
   - If disabling isn't possible, use an incognito/guest session
3. Start a NEW conversation
4. Paste the IDENTITY BRIEF from the paste packet as your **first message**
5. Wait for ChatGPT to acknowledge
6. Paste the test prompt as your **second message**
7. Copy the full response
8. Start a NEW conversation for each prompt (paste brief again each time)
9. Re-enable memory after testing

**Why disable memory for G2:** If ChatGPT has both its native memory AND the pasted brief, we can't isolate which produced the response quality. G2 tests "brief alone on GPT model" — a clean comparison against G1 "native memory alone."

### Alternative G2 (if memory can't be disabled)

If ChatGPT doesn't let you disable memory:
- Use a different browser or incognito mode where you're not logged in
- Paste the brief and prompt in a guest session
- This gives a truly cold GPT + brief condition

### G3 (Optional): GPT Native + Brief

If you also want to test the augmented condition (native memory + brief layered on top):
1. Keep memory enabled
2. Start a new conversation
3. Paste brief first, then prompt
4. This shows whether the brief adds value ON TOP of native memory

---

## ChatGPT-Confirmed Content Focus

### Why This Matters

1,859 of 1,892 imported conversations are from ChatGPT. ChatGPT's native memory was built from the same source material that Base Layer processed. This makes the comparison fair — both systems had access to the same conversations, but processed them differently.

### Prompt Domain Verification

All 10 test prompts cover topics the user discussed extensively in ChatGPT:

| Prompt | ChatGPT Coverage Confidence | Rationale |
|---|---|---|
| 1 (Trading Setback) | **HIGH** | Hundreds of trading conversations, revenge trading discussed repeatedly |
| 2 (Career Ambiguity) | **HIGH** | CRO roles, startup history, career decisions discussed across many sessions |
| 3 (Relationship) | **MEDIUM-HIGH** | Partner mentioned in personal conversations, relocation discussions possible |
| 4 (Architecture) | **MEDIUM** | Base Layer discussed but mostly in Claude Code sessions (25 of those). Check ChatGPT for AI/memory system discussions |
| 5 (Post-Win) | **HIGH** | Trading wins, discipline rules, system adherence discussed extensively |
| 6 (Existential) | **HIGH** | Self-reflection, purpose, ambition-fading conversations are frequent |
| 7 (Feedback) | **MEDIUM** | Project feedback discussions — depends on whether ChatGPT captured Base Layer feedback |
| 8 (Health) | **HIGH** | Gym, back pain, routine disruption discussed in health conversations |
| 9 (AI Relationship) | **MEDIUM-HIGH** | Meta-conversations about AI relationships likely present |
| 10 (Ambiguity) | **HIGH** | Decision-making, career paths, trading-vs-building discussed extensively |

### What If ChatGPT's Memory Is Thin?

ChatGPT stores ~100-200 discrete memories maximum. Even from 1,859 conversations, it may have captured only surface-level facts. That's actually the point — if Base Layer's deep processing of the same conversations produces better understanding than ChatGPT's memory, that proves the pipeline's value.

Document ChatGPT's actual memory count and content coverage before testing. This data is part of the eval.

---

## Scoring

Use the same 5 dimensions from `identity_eval_prompts.md`:

1. **Recognition** (1-5): Known vs. profiled vs. generic
2. **Calibration** (1-5): Right register and communication style
3. **Depth** (1-5): Engages at the right level
4. **Authenticity** (1-5): Genuine vs. performative
5. **Actionability** (1-5): Actually useful given who you are

### Additional C3-Specific Scoring

When rating C3 (raw facts) vs C2 (brief), pay attention to:

- **Fact Integration**: Does C3 naturally weave facts into responses, or does it feel like "fact dump + generic advice"?
- **Pattern Recognition**: Does C2 detect behavioral patterns that C3 misses? (e.g., recognizing SYSTEM ABANDONMENT vs. just knowing "he trades")
- **Predictive Power**: Does C2 anticipate what he'll do next? C3 has the data but not the synthesis to predict.

### Rating Protocol

1. Generate C1, C2, C3 responses programmatically
2. Run G1, G2 manually in ChatGPT
3. **Wait 24+ hours** before rating
4. Randomize all 5 conditions to blind labels (V/W/X/Y/Z)
5. Rate **one dimension at a time** across all responses for a given prompt
6. Rate fast — gut reaction, not analysis
7. After rating all prompts: unblind and analyze

---

## Expected Hypotheses

### C2 vs C3 (synthesis vs. raw facts)
- **Recognition**: C2 wins. Axioms and predictions create understanding; raw facts create a file.
- **Calibration**: C2 wins. Communication approach instructions calibrate tone; raw facts don't.
- **Depth**: C2 wins. Behavioral predictions let the model engage underlying patterns; raw facts stay at the surface.
- **Authenticity**: Toss-up. Both have real data. C2 might edge it via preamble instructions.
- **Actionability**: C2 wins. Predictions include directives for specific situations; raw facts require the model to derive those itself.

If C3 somehow ties or beats C2, the identity layers aren't adding value and the pipeline needs redesigning.

### G2 vs G1 (brief on GPT vs. native GPT memory)
- **Recognition**: G2 wins. Base Layer's identity layers encode deeper understanding than ChatGPT's ~100-200 stored memories.
- **Calibration**: G2 wins. Communication approach instructions in the brief directly calibrate.
- **Depth**: G2 likely wins. Behavioral predictions give the model structural engagement tools.
- **Authenticity**: G1 might edge it. Native memory feels more organic; pasted brief might feel clinical.
- **Actionability**: G2 wins. Specific situational directives outperform generic stored facts.

If G1 beats G2, ChatGPT's native memory is sufficient and Base Layer's value proposition weakens for ChatGPT users.

---

## Implementation Timeline

| Step | When | Method |
|---|---|---|
| V4 pipeline complete | After batch processes | Automated |
| Generate C1, C2 responses | After V4 layers authored | `run_eval.py --generate` |
| Build C3 fact sets per prompt | After V4 extraction complete | Script or manual query |
| Generate C3 responses | After fact sets built | Modified eval script |
| Verify ChatGPT memory coverage | Before G1/G2 testing | Manual — screenshot memories |
| Run G1 (ChatGPT native) | After memory verification | Manual — paste packet |
| Run G2 (ChatGPT + brief) | After G1 complete | Manual — paste packet |
| Wait 24h | — | — |
| Blind rate all conditions | After waiting period | Manual rating sheet |
| Analyze results | After rating | `run_eval.py --analyze` or manual |

---

## Outputs

1. **Scored comparison table** — 5 conditions × 10 prompts × 5 dimensions
2. **C2 vs C3 delta** — proves synthesis value
3. **G2 vs G1 delta** — proves Base Layer vs native memory
4. **ChatGPT memory inventory** — what the incumbent actually stored
5. **Qualitative notes** — failure modes, red flags, surprises per condition
6. **README-ready summary** — 1-2 paragraphs with key numbers for public use

---

## Relationship to Other Evals

| Framework | Question | Status |
|---|---|---|
| A/B/C Eval (S32) | Brief vs. raw history vs. cold | Complete |
| V3 Identity Eval (S50) | Brief vs. cold (Claude only) | Complete — baseline captured |
| **Extended Eval (S51)** | **Synthesis vs. facts vs. native memory** | **This document** |
| Cross-Provider Eval | How well does each provider natively understand identity? | Designed, post-release |
| TIRB | Can AI memory systems reason about identity over time? | Future — publishable |
