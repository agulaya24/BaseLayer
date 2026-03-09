# Collective Review — S78 Research Status (2026-03-08)

## Scores

| Persona | Score | Delta from S77 |
|---------|-------|----------------|
| Systems Architect | 68/100 | -3 |
| Cognitive Psychologist | 64/100 | -10 |
| Research Scientist | 58/100 | -20 |
| Product Strategist | 52/100 | -10 |
| **Collective** | **60.5/100** | **-10.5** |

## Why the Score Dropped

S77 was graded on potential. S78 has enough data to grade on execution, and execution reveals structural problems:
- Production system doesn't use its own best findings (annotated guide, 2,500 chars)
- Pipeline hasn't been ablated (14 steps, unknown how many load-bearing)
- Citations API bug: core feature never worked on Windows, 414 tests missed it
- Sonnet effect size (p=0.117) is not significant — the deployment model shows the weakest result
- Internal evaluation framework has circularity concerns
- Adversarial vulnerability of best format is newly quantified (60%)

## Top 5 Issues (Ranked by Impact)

### 1. Ship the Annotated Guide Format (~2,500 chars)
Your own data says the current production brief is the worst performer. Every day you ship the old format, you undermine your own research. Highest-ROI change — compose step rewrite, no pipeline modification needed.

### 2. Run Pipeline Ablation Study (~$16-20)
Until you know which steps are load-bearing, you cannot credibly claim the pipeline is the contribution. If a single Opus prompt gets within 15% of 14-step pipeline quality, the contribution is the research findings, not the engineering.

### 3. Test on At Least One More External Benchmark
Twin-2K is strong but singular. One benchmark is an anecdote. LongMemEval or PersonaChat would test different aspects of the brief's value.

### 4. Define What "Identity" Means in This System
"Behavioral compression" is more precise than "identity." The lack of theoretical grounding makes every claim ambiguous. 47 predicates mix traits, behaviors, biography, and relationships — these have fundamentally different psychometric properties.

### 5. Address Adversarial Vulnerability with a Concrete Plan
Annotated guide format lists behavioral triggers and failure modes explicitly. Before open-sourcing, decide: redact sensitive patterns, implement "safe mode," or accept risk and document it.

## Per-Persona Detail

### Research Scientist (58/100)

**Strengths:** Twin-2K on external data (p=0.008). Cross-model replication discipline. Honest failure reporting.

**Weaknesses:** N=10 is not generalizable. Internal eval is self-referential (pipeline's embeddings evaluating pipeline's outputs). Multiple comparisons without correction — dozens of experiments, no Bonferroni.

**Key question:** "Sonnet effect is p=0.117. How do you claim 'compression works' when it disappears on the model that matters most?"

**Swing factor:** Reproducing Twin-2K on 2-3 additional external benchmarks.

### Product Strategist (52/100)

**Strengths:** Stacking thesis is correct positioning. Multi-source extraction is a genuine differentiator. Research framing is strategically right for launch.

**Weaknesses:** Production system doesn't use its own best findings. No user-facing value proposition survives scrutiny. Platform risk remains existential.

**Key question:** "Who is your user? Researcher, developer, or end user? The system serves none well."

**Swing factor:** Ship annotated guide format + hosted API or trivial integration path.

### Systems Architect (68/100)

**Strengths:** Pipeline is well-decomposed. Constraint-based extraction prevents hallucination. Anonymization layer is architecturally correct.

**Weaknesses:** 14 steps is almost certainly over-engineered. Citations API bug reveals broad exception handling and test gaps. ChromaDB L2 vs cosine is unresolved technical debt.

**Key question:** "What happens when you replace the 14-step pipeline with a single Opus prompt?"

**Swing factor:** Pipeline ablation study + minimal viable pipeline refactor.

### Cognitive Psychologist (64/100)

**Strengths:** "Behavioral > biographical" aligns with personality psychology. Temporal stability maps to narrative identity theory (McAdams). Compression saturation is consistent with Big Five variance structure.

**Weaknesses:** "Identity" used without theoretical definition. No validation against established personality measures (Big Five, HEXACO). Adversarial vulnerability is an ethical risk beyond what's acknowledged.

**Key question:** "You test prediction accuracy but not reasoning process. Does a briefed model actually REASON differently?"

**Swing factor:** Running one subject through a validated personality instrument for construct validity.

## Verdict

Base Layer has produced genuine research findings — compression saturation, temporal stability, behavioral > biographical, annotated guide advantage. These hold across models and subjects. The Twin-2K result (18:1 compression, p=0.008) is the project's strongest credential. But the gap between what the research has discovered and what the system actually ships is the central problem. This is a research project with strong preliminary findings and a promising compression thesis, not a validated system ready for confident claims. The path forward: ship the annotated guide, run the ablation, test on more benchmarks, and stop saying "proven" until the evidence supports it.
