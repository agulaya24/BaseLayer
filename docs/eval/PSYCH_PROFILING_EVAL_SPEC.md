# Psychological Profiling Evaluation Study (D-078-PSYCH)

## Hypothesis

Base Layer's automated behavioral extraction produces conclusions that significantly overlap with professional psychological assessment when given identical source material.

If the pipeline captures real behavioral signal (not just statistical pattern-matching on surface language), a trained psychologist reviewing the same transcripts should independently arrive at substantially similar conclusions about who the person is, how they make decisions, what they avoid, and where their blind spots are.

## Motivation

Current benchmarks validate the pipeline from different angles:
- **Twin-2K (71.83%, N=100):** Tests whether the brief is *useful* for predicting behavior, but not whether it is *accurate* as a behavioral portrait.
- **BCB:** Tests compression fidelity and structural properties, but uses LLM-as-judge.
- **Provenance eval:** Tests whether claims trace to source data, but not whether the *interpretation* of that data is correct.

None of these provide external validation from an independent methodology. A clinical psychologist reading the same raw material applies a completely different analytical lens -- decades of theory, pattern recognition from clinical practice, and formal training in behavioral assessment. Where the two methods converge, we have strong evidence the pipeline captures real signal. Where they diverge, we have identified either pipeline blind spots or places where automated extraction finds patterns that escape human attention.

This study was also motivated by a specific finding: Base Layer's V4 compose prompt generates templated response directive language across different subjects (e.g., identical "help diagnose the structural cause rather than reassuring" phrasing appearing in two different briefs). The psychological profiling comparison would reveal whether this templating masks real behavioral differences that a human assessor would distinguish.

## Design

- **Independent variable:** Assessment method (Base Layer pipeline vs clinical psychologist)
- **Dependent variable:** Behavioral pattern agreement rate
- **Source material:** Same raw conversation transcripts (anonymized)
- **Condition:** Blind -- neither assessor sees the other's output
- **Suggested subjects:** 2-3 subjects with existing Base Layer briefs (e.g., Aarik's data if consented, or synthetic subjects with known ground truth)

### Why This Design

The key constraint is that behavioral identity has no objective ground truth. The person being modeled is one signal. An independent professional assessment is another. The pipeline is a third. By comparing all three, we triangulate rather than relying on any single authority.

## Protocol

1. **Select conversation corpus.** Minimum 50K words per subject. Must be naturalistic conversation (not interview responses or structured prompts), since Base Layer's extraction pipeline is optimized for conversational data.

2. **Anonymize all identifying information.** Replace names, locations, organizations, and any other identifying details. Both the pipeline and the psychologist receive identical anonymized transcripts.

3. **Base Layer pipeline processes corpus.** Standard pipeline run: Import, Extract, Author (anchors + core + predictions), Compose (V4). Outputs: unified brief, three layer files, raw extracted facts.

4. **Clinical psychologist independently reviews same corpus.** No time limit, but track hours spent. Psychologist produces a written behavioral assessment covering the comparison framework dimensions (below). No specific format imposed -- the assessment should reflect their professional judgment and methodology.

5. **Blind condition enforced.** Neither the pipeline output nor the psychologist's assessment is shared with the other party at any point during the assessment phase. The psychologist is told only that they are assessing behavioral patterns from conversation data -- not that an AI system is doing the same.

6. **Third-party rater maps both outputs to shared comparison framework.** An independent rater (not the psychologist, not the pipeline operator) reads both outputs and codes them against the comparison dimensions. This rater determines: which patterns appear in both, which are unique to one method, and where the two methods contradict each other.

7. **Calculate agreement metrics** (see Metrics section below).

8. **Optional: Subject validation.** If the subject consents, they review both assessments and rate accuracy. This adds a third signal but is not required for the core comparison.

## Comparison Framework

The third-party rater maps both outputs to these seven dimensions:

| Dimension | What It Captures | Example Pattern |
|---|---|---|
| **Decision-making patterns** | How they approach choices, what information they seek, how they handle uncertainty | "Decides by eliminating options rather than selecting for fit" |
| **Conflict and avoidance patterns** | What they engage with vs sidestep, how they handle disagreement | "Avoids direct confrontation but escalates through structural changes" |
| **Core values and priorities** | Stated values vs revealed behavioral priorities, hierarchy of concerns | "Claims to value collaboration but consistently makes unilateral decisions" |
| **Interpersonal dynamics** | How they relate to others, communication patterns, trust/authority orientation | "Defers to expertise on execution but not on strategy" |
| **Cognitive style** | Analytical vs intuitive, structured vs flexible, abstract vs concrete | "Reasons by analogy, tests ideas by running them to logical extremes" |
| **Key tensions and contradictions** | Internal conflicts, inconsistencies between stated and enacted behavior | "Values speed but refuses to ship without structural clarity" |
| **Blind spots and thin data** | Areas where behavior is opaque, unexplored, or potentially misread | "No data on how they handle sustained failure" |

Each identified pattern is coded as a discrete claim. The rater then classifies each claim as:
- **Convergent:** Both methods identify substantially the same pattern
- **Pipeline-unique:** Only the pipeline identifies this pattern
- **Psychologist-unique:** Only the psychologist identifies this pattern
- **Contradictory:** The two methods make opposing claims about the same dimension

## Metrics

### Primary

- **Pattern overlap rate:** Percentage of total unique patterns identified by both methods. Target: >50% overlap would be a strong signal.
- **Contradiction rate:** Percentage of patterns where the two methods disagree. Target: <15% would suggest the pipeline is not generating false signal.

### Secondary

- **Unique discovery rate (pipeline):** Patterns found only by the pipeline. High rate may indicate either noise or genuine automated advantage (e.g., detecting patterns across 50K words that a human cannot track).
- **Unique discovery rate (psychologist):** Patterns found only by the psychologist. These are the pipeline's blind spots -- the most actionable output of the study.
- **Specificity comparison:** For convergent patterns, which method produces more specific, actionable descriptions? Rated by the third-party rater on a 1-5 scale.
- **False positive analysis:** For pipeline-unique patterns, the psychologist reviews and rates whether each pattern is (a) supported by source data but missed, (b) plausible but insufficient evidence, or (c) not supported by source data.

### Optional (if subject validates)

- **Subject accuracy rating:** Subject rates each convergent, unique, and contradictory pattern as accurate/inaccurate/partially accurate.
- **Assessment preference:** Subject ranks which output (pipeline or psychologist) they find more useful as a description of themselves.

## Cost Estimate

| Item | Per Subject | Notes |
|---|---|---|
| Psychologist time | $1,500-6,000 | 10-20 hours at $150-300/hr depending on specialization |
| Base Layer pipeline | ~$1.50 | Standard pipeline run (Haiku extraction + Sonnet authoring + Opus compose) |
| Third-party rater | $750-1,500 | 5-10 hours at $150/hr |
| Subject validation (optional) | $0-500 | Depends on whether subject is consented volunteer or paid |
| **Minimum viable study (2 subjects)** | **$5,000-15,000** | |
| **Ideal study (3 subjects)** | **$7,500-22,500** | |

The asymmetry is the point: the pipeline costs $1.50 and takes minutes. The psychologist costs thousands and takes weeks. If the pipeline achieves >50% overlap, the compression ratio is not just textual but methodological.

## Novel Contribution

No existing AI personalization system has been validated against professional psychological assessment. This creates:

1. **External ground truth that is not self-referential or LLM-as-judge.** Every current AI eval for behavioral modeling uses either the person being modeled or another LLM as the evaluator. A trained psychologist is an independent methodology with its own theoretical foundation.

2. **Identification of what automated extraction misses that humans catch (and vice versa).** The pipeline's blind spots become concrete and addressable. The psychologist's blind spots reveal where automated processing has a structural advantage (e.g., tracking patterns across 50K+ words of conversation).

3. **Publishable result regardless of outcome.** High convergence validates automated behavioral extraction. Low convergence reveals specific failure modes. Both are informative. Both are novel.

4. **Templating detection.** If the psychologist produces clearly differentiated assessments for two subjects while the pipeline produces suspiciously similar language, that is direct evidence of a compose-step templating problem. Conversely, if both methods produce similar-sounding assessments for two genuinely similar subjects, the templating concern is mitigated.

## Risks

- **Small N.** At $5,000-15,000 for two subjects, this is expensive per data point. Results will be suggestive, not statistically conclusive. Framing must be "design study" not "proof."

- **Psychologist assessment is not itself ground truth.** It is another lens, not an oracle. Inter-rater reliability among psychologists varies. A single psychologist's assessment reflects their theoretical orientation, not objective reality.

- **Theoretical framework mismatch.** The pipeline is behavioral (extracts what the person *does*, avoids, prioritizes). A psychodynamically-oriented psychologist may frame patterns through attachment theory, defense mechanisms, or developmental history. These frameworks may describe the same underlying patterns in incompatible language, creating false divergence.

- **Comparison framework introduces bias.** The seven dimensions listed above were chosen to be framework-neutral, but any structured comparison imposes a lens. Patterns that do not fit neatly into these dimensions may be lost in the mapping step.

- **Demand characteristics.** If the psychologist knows this is a comparison study, they may unconsciously adjust their assessment style (e.g., emphasizing behavioral patterns over psychodynamic ones). The protocol mitigates this by not disclosing the comparison, but full blinding may not be achievable.

- **Anonymization artifacts.** Heavy anonymization may remove contextual cues that a psychologist would normally use (cultural background, professional context, relationship dynamics). This could artificially depress the psychologist's accuracy while having less effect on the pipeline (which operates on linguistic patterns).

## Connection to Existing Work

- **Extends BCB framework:** BCB measures compression fidelity through structured tasks. This study measures fidelity through independent expert assessment -- a different axis of the same question.

- **Complements Twin-2K:** Twin-2K tests whether the brief is *useful* (can it predict behavior?). This study tests whether the brief is *accurate* (does it describe the right patterns?). A brief could be useful but inaccurate (captures surface patterns that predict behavior but misidentifies the underlying structure), or accurate but not useful (correctly identifies patterns but in a format that does not help downstream tasks).

- **Addresses the "only the person can judge" limitation:** Current evaluation relies heavily on the modeled person's self-assessment. Adding professional assessment creates a three-way triangulation: pipeline output, subject validation, and expert assessment.

- **Related to D-076 (dissenting opinion benchmark):** Both use expert judgment as validation. D-076 uses judicial reasoning as ground truth; this study uses psychological assessment. Same principle: compare automated behavioral extraction against trained human pattern recognition.

- **Informs the templating problem:** The V4 compose prompt generates similar response directive language across subjects. If the psychologist clearly differentiates subjects that the pipeline describes similarly, we have evidence that the compose step (not the extraction step) is losing signal. This would motivate compose-step improvements without requiring a new benchmark.

## Open Questions

1. **Should the psychologist know this is a comparison study?** Disclosing the comparison could bias their assessment toward behavioral language. Not disclosing raises ethical concerns about informed consent for professional work. Recommended: disclose that their assessment will be used in a research comparison, but do not disclose that the comparison is against an AI system until after their assessment is complete.

2. **What type of psychologist?** Clinical psychologists have deep assessment training but may default to pathology framing. I/O (industrial-organizational) psychologists focus on behavioral patterns in professional contexts, which is closer to what the pipeline extracts. Personality researchers may be most framework-neutral. Recommendation: I/O psychologist for the first study, with a clinical psychologist as a second rater if budget allows.

3. **Can existing psychological instruments serve as the shared framework?** Big Five (OCEAN), HEXACO, or other validated personality instruments could replace or supplement the custom comparison framework. Advantage: established validity. Disadvantage: these instruments measure traits, not behavioral patterns -- the pipeline explicitly avoids trait-level claims (e.g., "this person is extraverted") in favor of behavioral observations (e.g., "this person initiates conversations about technical problems but avoids social small talk"). Using trait instruments could penalize the pipeline for being more specific than the instrument allows.

4. **Should we include a "person being modeled validates both" step?** This adds a valuable third signal but introduces its own biases (people are not always accurate about their own patterns). Recommended: include as optional, do not make it a gating metric.

5. **How do we handle the density difference?** The pipeline produces a structured brief (~2,000-10,000 chars). The psychologist will produce a narrative assessment that may be longer, shorter, or structured differently. The third-party rater must normalize for density before calculating overlap.

6. **Can this be done with pro bono or academic partners?** University psychology departments may be interested in a study comparing AI behavioral extraction to professional assessment. This could reduce cost and add academic credibility. Risk: slower timeline, IRB requirements.

## Implementation Priority

**Post-launch.** This study requires budget, external partners, and IRB-level consent processes. It is not a blocking dependency for any current work. However, the spec should be ready so that when funding or academic partnerships become available, execution can begin immediately.

Estimated timeline from green light to results: 8-12 weeks (partner recruitment, corpus preparation, independent assessments, comparison coding, analysis).
