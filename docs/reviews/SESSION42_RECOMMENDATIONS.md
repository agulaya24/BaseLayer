# Session 42 Recommendations — Complete List with Feedback

**Session:** 42, 2026-02-25
**Context:** Collective analysis + user feedback. Captured from conversation before context crash.

---

## Manifesto & Positioning — APPROVED (all 6)

1. **Finalize manifesto with confirmed structure.** Felt experience (learning styles) → Insight (AI doesn't understand HOW to work with you) → Thesis (commodification as stated belief) → Pillars (Ownership, Understanding, Continuity — external names) → Product → Stakes ("this future cannot exist without it"). Both internal and external versions, both public. Explicit data sovereignty language matching Kin's clarity.

2. **External pillar names confirmed:** "Your Data, Your Machine" / "Understanding, Not Just Memory" / "Same Mind, New Model"

3. **Commodification thesis as stated belief, not certainty** — "We believe..."

4. **Explicit data sovereignty language:** "Your data lives on your device. Processing touches cloud APIs. Nothing is stored remotely. Your identity model is yours." Additional note from the user: ideally we would do this all locally but tech is not there yet for 99% of consumers. This should be noted somewhere.

5. **Split internal + external manifesto, both public.** External = product value. Internal = worldview + architectural conviction.

6. **Audience-specific framings need to be identified:** investors, industry leaders, technical users, consumers.

**User feedback:** "Let's do all of these, update all GTM, including website, etc."

---

## Identity Layer Architecture — APPROVED (all 6)

7. **Rewrite CORE generation prompt to be directive, not descriptive.** "How to engage with this person" — communication guide, not biography. Distinct from ANCHORS (permanent axioms) and PREDICTIONS (triggered patterns).

8. **Build Communication Synthesis pass after layer generation.** Reads all three layers + behavioral facts. Produces communication directives: reasoning style, abstraction preference, feedback mode, temporal/narrative orientation. Token budget determined by content needs, not arbitrary cap.

   **User feedback on token limit:** "Why assume 500 tokens, shouldn't be setting arbitrary limits."

9. **Assess layer delineation formally.** ANCHORS = permanent reasoning constraints. CORE = general operating/communication guide. PREDICTIONS = situation-triggered patterns. Review all three current generations against this framework and identify what moves where.

   **User feedback:** "I'm in agreement, but let's assess overlap between layers, and how we want these layers to truly work together. If it means taking an entirely different approach, new sections, whatever, that's fine. We should review all identity layer/block generations to come to a proper consensus on this."

10. **Test whether temporal phenomena can be accurately identified by LLMs** before committing to temporal scope as a field. Small eval: give Sonnet/Opus 20 conversations, ask it to classify temporal reasoning mode. Check accuracy.

    **User feedback (Epistemologist voice):** "Can these phenomena be accurately identified by language models, will need to test."

11. **Add temporal scope as optional field on conviction-level facts** (if test passes): "permanent," "bounded," "evolving." Enhances commitment_depth.

    **User feedback:** "I'm fine with not adding a new fact type. I agree with recommendation."

12. **Do NOT add new fact types.** Communication style is a synthesis concern, not an extraction concern.

    **User feedback (Pragmatic Engineer voice):** "It seems we generally don't want to add fact types here."

---

## Evaluation & Provenance — APPROVED (framework)

13. **Build LLM-verified provenance eval.** Query with brief → Response → "Which brief elements informed this?" → Score for communication fit + brief utilization.

14. **Provenance should be background metadata, not visible to user** — the LLM acknowledges which parts of the brief it used, scored automatically.

15. **Collective judges sample batches periodically, not every eval.** Automated loop with periodic human spot-check.

**User feedback:** "Sounds good, let's get a framework for this."

---

## Data Pipeline — CONDITIONAL

16. **Lower extraction threshold for content-rich short conversations.** 59 conversations with 1,000+ chars skipped because <6 messages. Adjust to content-length floor or run manually.

    **User feedback:** "I'm reluctant to dive into some of the behavioral trade reviews, because I don't want to continue skewing, there should be enough data there to say I have a problem with overtrading yadda yadda, I don't think there will be some insane insight there, but if we can have a cheap overview of it via Haiku may be worth it." Also: "Have Collective look into this based on my earlier comment, I don't want to add them if they are overly trading heavy at this point, too much importance is being given to that as is."

17. **Sonnet re-extraction deferred** until extraction prompt is finalized (especially if communication-style extraction changes the prompt).

---

## Code Quality — IN PROGRESS

18. ✅ Database indexes applied — 18 total, ANALYZE run
19. ✅ Scope backfill complete — 4,106 active facts, 0 NULL scope
20. ✅ LICENSE created — Apache 2.0, pyproject.toml updated
21. **Still needed:** ~~f-string SQL fixes (0 remaining)~~, resource leaks (87 conn.close → context managers), bare excepts (2 in test_significance.py), thread-unsafe globals (status unknown)

**User feedback:** "Good, let's finish up fixes there."

---

## GTM & Distribution — APPROVED (all)

22. **Update stale GTM docs** (BASE_LAYER_OVERVIEW, SLIDE_DECK) after manifesto finalized — numbers, models, token budgets all wrong.

23. **Update README** — 19 commands, not 16 (missing forget, review, journal). Also: says "Personal AI Memory System" instead of "Base Layer" in places, mentions Qwen in ways that are dated.

24. ✅ GitHub remote connected and pushed (master → origin/main).

25. **Competitive positioning:** Base Layer is in the "understanding" business, not the "memory" business. None of the three competitors (Mem0, Supermemory, Letta) build identity. The differentiator is depth, not breadth.

26. **Category risk:** Market may equate "AI memory" with "preference retrieval." Manifesto must establish that memory ≠ understanding.

**User feedback:** "As mentioned earlier, update everything." Also on benchmarks: "This is great, this reminds me we need benchmarks, are there any that can be used or run in an automated fashion or do none exist for 'who is this person'. Need to keep this comparison somewhere, and needs to stay top of mind for investors and the like."

---

## Deferred

27. **OpenRouter proxy** (~3 hours build) — "Need to figure out initial release. It's all a bit fuzzy in my head."
28. Cold start / journal onboarding
29. Subject B feedback loop
30. Landing page
31. Full Sonnet re-extraction

---

## Identity Layer Assessment (from session)

**ANCHORS (strong):** 9 axioms with "Active when" triggers and interaction rules. Fully directive. Tells the AI what to DO. No changes needed.

**CORE (weak — confirmed):** Reads as a resume/biography. "User A, 31, leads [previous startup]..." Descriptive, not directive. Tells the AI WHO someone is, but not HOW to engage. The gap analysis section at the bottom is interesting but the main block is a compressed biography.

**PREDICTIONS (strong):** 8 behavioral patterns with trigger → detection → directive format. Pattern-based, actionable. Tells the AI what to EXPECT and how to RESPOND.

**Delineation (approved):**

| Layer | Question | Temporal Focus | Directive Type |
|-------|----------|---------------|----------------|
| ANCHORS | "What are this person's non-negotiable reasoning constraints?" | Permanent | "Never do X, always do Y" |
| CORE | "How does this person operate across contexts?" | Present + narrative | "When engaging, approach them this way" |
| PREDICTIONS | "What will this person do in specific situations?" | Situational/triggered | "When you see X, expect Y, do Z" |

---

## 800-Conversation Analysis (partial — agent results lost)

**Known from conversation:**
- 799 remaining conversations with user content
- Content length distribution:
  - 5,000+ chars: 21 (definitely worth extracting)
  - 2,000-5,000 chars: 23 (yes)
  - 1,000-2,000 chars: 15 (probably)
  - 500-1,000 chars: 24 (maybe)
  - 200-500 chars: 77 (unlikely)
  - <200 chars: 639 (no)
- 59 conversations with 1,000+ chars being skipped purely because <6 messages
- Top conversation: 74,742 chars in just 2 messages
- Many are trade reviews (rich behavioral data), resume work, technical conversations
- **Detailed trading skew breakdown was lost — needs re-running**

---

## Competitive Analysis Summary

Saved to `gtm/COMPARABLES.md`. Key finding: None of Mem0 ($24M), Supermemory ($3M), or Letta ($10M/$70M valuation) build identity. All solve "memory" (fact/document retrieval for agents). Base Layer solves "understanding." Mem0's own benchmark shows 25% accuracy at 6-fact retrieval — the RAG ceiling that Base Layer's pipeline was designed to overcome.

**User action item:** Need automated benchmarks for "who is this person" — none exist in the market. Must be designed.
