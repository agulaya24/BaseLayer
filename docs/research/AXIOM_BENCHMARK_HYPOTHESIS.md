# Axiom-Conditioned Benchmark Hypothesis

**Status:** Research concept — not yet tested
**Origin:** Session 74 (2026-03-06)
**Author:** The developer (hypothesis), Opus (analysis)

---

## Core Hypothesis

Injecting domain-expert identity briefs (specifically axioms and behavioral predictions) into a model's context will improve performance on domain-specific benchmarks — because the model gains access to structured reasoning patterns, not just knowledge.

## Why This Is Different From Persona Prompting

| Approach | What the model gets |
|---|---|
| Base model | General training knowledge |
| Persona prompt ("think like Buffett") | Permission to roleplay, surface-level heuristics |
| Memory/RAG (facts about Buffett) | Retrievable knowledge, no reasoning structure |
| **Base Layer brief (Buffett axioms)** | **Specific decision frameworks, tensions, false positives, cross-domain behavioral patterns** |

The distinction matters. "Think like Buffett" activates pre-training associations. A Base Layer brief gives the model Buffett's actual axioms — second-level thinking, margin of safety over upside, contrarian positioning when consensus is high — with directives for when each pattern activates and warnings about when it doesn't apply.

## What We'd Test

### Experimental Conditions
- **C1:** Base model (no context)
- **C2:** Persona prompt ("You are an expert investor with Warren Buffett's philosophy")
- **C3:** Raw facts (Base Layer facts, no brief — like a memory system would provide)
- **C4:** Full Base Layer brief (axioms + core + predictions)
- **C5:** Axioms only (isolates the structured reasoning layer)

### Candidate Domains (We Already Have Briefs)

1. **Investment reasoning** — Buffett brief (12 axioms, 8 predictions) or Marks brief (20 axioms, 13 predictions)
   - Tasks: Investment case analysis, risk assessment, portfolio allocation reasoning
   - Benchmarks: CFA-style case studies, historical investment decisions, "would you invest?" scenarios

2. **Engineering/invention** — Patent corpus brief (constraint-driven innovation, modular composability)
   - Tasks: System design problems, trade-off analysis, cross-domain engineering challenges
   - Benchmarks: Design review scenarios, patent prior art analysis

3. **Political/governance reasoning** — Roosevelt brief (principle-over-politics, deed-over-declaration)
   - Tasks: Policy trade-off analysis, crisis decision-making, stakeholder management
   - Benchmarks: Historical policy scenarios with known outcomes

4. **Paul Graham (pending)** — VC/startup evaluation
   - Tasks: Startup evaluation, founder assessment, market analysis
   - Benchmarks: Y Combinator-style application review, startup post-mortems

### Metrics
- **Domain accuracy:** Correct/expert-aligned answers on structured tasks
- **Reasoning quality:** Does the model invoke relevant frameworks vs. generic analysis?
- **Alignment with expert:** How closely does the model's reasoning match the actual expert's known positions?
- **Parrot check:** Is the model just quoting the brief, or is it applying the axioms to novel situations?

## Strong vs. Realistic Claims

**Strong claim (hard to prove, very compelling):**
"A Buffett brief + Sonnet outperforms base Opus on investment reasoning tasks."
This would mean structured expert axioms are worth more than raw model capability for domain tasks.

**Realistic claim (easier to prove, still valuable):**
"Brief-conditioned models produce more expert-aligned, structured reasoning on domain tasks than base models or persona-prompted models."

**Minimum viable claim:**
"Axiom injection produces measurably different (more structured, more expert-like) reasoning compared to persona prompting and fact injection."

## Why This Matters for Base Layer

1. **Extends value prop beyond personalization.** Identity briefs aren't just "AI that knows you" — they're transferable expertise.
2. **Quantifiable proof.** Benchmark scores are harder to argue with than subjective quality judgments.
3. **New use case: expertise transfer.** Feed in an expert's writing, extract their reasoning axioms, inject into any model for any user. The expert doesn't need to be present.
4. **B2B angle:** Companies could build domain-specific reasoning layers. A law firm's brief improves legal reasoning. An investment firm's brief improves analysis.
5. **Addresses "so what?" directly.** The brief doesn't just make AI feel personalized — it makes AI perform better on domain tasks.

## Implementation Notes

- Start with Buffett or Marks — richest briefs, clearest domain (investment), most testable.
- Need to design or source domain benchmarks. CFA practice questions, investment case studies, or build custom scenarios from historical data.
- Same eval infrastructure as existing BCB framework (run_validation_study.py) — just different prompts and different scoring.
- Paul Graham brief (when ready) is the perfect VC case: "Does PG's brief help a model evaluate startups better?"

## Open Questions

- How do we define "better" for subjective domains like investment? Expert alignment? Outcome prediction? Reasoning structure?
- Does brief size matter? Would axioms-only (smallest) outperform full brief (largest)?
- Cross-domain transfer: Does Buffett's brief improve reasoning on non-investment tasks that share structural patterns (e.g., risk assessment in engineering)?
- Diminishing returns: Is there a point where more axioms don't help?

## Relationship to BCB

BCB-0.1 measures whether the brief *preserves signal* (compression ratio, signal retention, drift resistance). This hypothesis tests whether the brief *improves performance* — a stronger and more commercially relevant claim. If proven, it becomes BCB-0.2 or a separate benchmark entirely.
