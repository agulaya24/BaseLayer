# Axiom-Conditioned Domain Reasoning Benchmark (ADRB v0.1)

**Status:** Collective-reviewed spec — ready for implementation
**Origin:** Session 74 (2026-03-06)
**Collective Participants:** Methodologist, Skeptic, Domain Expert
**Domain:** Investment Reasoning (Buffett + Marks briefs)

---

## Core Hypothesis

**Structured behavioral compression produces more framework-adherent, structured reasoning than unstructured knowledge, persona prompting, or raw fact injection.**

This is NOT a claim that the brief makes the model "smarter" or produces objectively better investment advice. It is a claim that the compression step — axioms, predictions, directives, false positives — changes HOW the model reasons in domain-specific tasks.

### Pre-Registered Claims

1. **Primary:** Full brief (C5) outperforms named persona (C1) on composite score with effect size d >= 0.40.
2. **Secondary:** The lift is largest on Hard tasks (anti-memorization) where pre-training knowledge is insufficient.
3. **Secondary:** Cross-expert divergence — same task produces framework-consistent but different reasoning when briefed with Buffett vs. Marks.
4. **Diagnostic:** Cross-subject injection — brief overrides persona name (Marks brief + "reason as Buffett" produces Marks-aligned reasoning).

### What This Does NOT Claim

- That brief-conditioned reasoning produces better investment outcomes
- That the brief teaches the model something it doesn't already know about public figures
- That the brief replaces domain expertise
- That higher "alignment" scores mean objectively better advice

---

## Experimental Conditions (7)

| ID | Condition | System Prompt Contains | Purpose |
|---|---|---|---|
| **C0** | Base | Task only | Floor — raw model capability |
| **C1** | Named Persona | "You are Warren Buffett. Reason as he would." | Pre-training activation ceiling |
| **C2** | Smart Persona | "You are Warren Buffett. Focus on: [top 5 principles from Wikipedia]" | What a thoughtful user would actually do |
| **C3** | Raw Facts | 50 randomly sampled identity-tier facts, no structure | Tests compression vs. raw information |
| **C4** | Axioms Only | 12/20 axioms, no context modes, no predictions | Isolates axiomatic layer |
| **C5** | Full Brief | Complete anonymized brief | Full system test |
| **CX** | Cross-Injection | Marks brief + "reason as Buffett" (and vice versa) | Contamination diagnostic |

### Key Comparisons

| Comparison | Question Answered |
|---|---|
| C5 vs. C1 | **PRIMARY:** Does the brief beat persona prompting? |
| C5 vs. C2 | Does the brief beat a smart persona prompt? |
| C5 vs. C3 | Does compression add value over raw facts? |
| C4 vs. C5 | Do axioms alone carry most of the value? |
| C1 vs. C0 | How much does the model already know? |
| CX diagnostic | Does the brief override pre-training persona? |

### Token Budget Control

Record token counts per condition. Do NOT artificially equalize — report as covariate. The brief being longer is part of the product reality.

---

## Task Design (40 tasks per subject)

### Categories

| Category | Count | Difficulty Mix | Focus |
|---|---|---|---|
| A. Moat Durability | 7 | 3E / 2M / 2H | Competitive advantage assessment |
| B. Risk Assessment | 7 | 2E / 3M / 2H | Second-order consequences, asymmetric outcomes |
| C. Capital Allocation | 6 | 3E / 2M / 1H | Management quality, capital deployment |
| D. Market Cycles | 5 | 2E / 2M / 1H | Cycle awareness, contrarian positioning |
| E. Valuation Under Uncertainty | 6 | 2E / 2M / 2H | Unknowable parameters, fat tails |
| F. Epistemic Humility | 4 | 1E / 2M / 1H | Information asymmetry, what you don't know |
| G. Cross-Framework Conflict | 5 | 2E / 2M / 1H | Buffett vs. Marks divergence points |
| **Total** | **40** | **15E / 15M / 10H** | |

### Difficulty Tiers

- **Easy (15):** Single axiom clearly applies. Brief should sharpen the answer structurally.
- **Medium (15):** Multiple axioms in tension. Brief should help resolve the hierarchy.
- **Hard (10):** Novel situations requiring creative framework extension. Brief should provide the largest lift. Includes the 5 anti-memorization tasks.

### Anti-Memorization Tasks (5 — Key Discriminators)

These are impossible to answer well from pre-training alone but straightforward with the axiom framework:

| ID | Name | Why It Discriminates |
|---|---|---|
| AM1 | The Comfortable Moat Erosion | Brand moat vs. secular consumption shift — structurally similar to See's Candies but with novel threat. No canned answer exists. |
| AM2 | The Ethical Complication | Cheap + legal + profitable but reputational/humanitarian risk. Neither expert has a well-known position on this exact type. Must extrapolate from framework principles. |
| AM3 | The AI-Native Disruptor | Genuinely novel business type. No pre-training knowledge of expert's position on AI consulting disruption at 100x revenue. |
| AM4 | The Succession Paradox | Berkshire succession abstracted + anonymized. Specific details don't match any real situation. Must reason about founder-dependence from framework, not recall. |
| AM5 | The Contrarian Consensus | Second-order reflexivity — what happens when the contrarian position IS the consensus? Tests whether the model can turn the framework's own logic back on itself. |

### Standardized Task Format

```
SCENARIO: [200-300 word description of company/industry/situation]
QUESTION: Based on your investment philosophy, would you invest?
Explain your reasoning, identify the key risks, and state what
additional information you would need. If you would pass, explain
what would need to change for you to reconsider.
```

### Anonymization

- All company names fictional (Keravos, Dalwick, Ondara, Brevell, etc.)
- Mix of US, European, African, Asian settings
- Realistic but untraceable financial profiles
- No exact fingerprints of famous Buffett/Marks holdings
- Structural composites from multiple real situations

### Temporal Mix (Contamination Control)

| Type | Count | Contamination Level |
|---|---|---|
| Contemporary (2024-2025 dynamics) | 12 | Medium — model has training data but not expert's opinion |
| Post-cutoff (2026 hypotheticals) | 10 | Low — genuinely novel |
| Classic structural scenarios | 8 | Medium-High — but anonymized |
| Counterfactual (contradicts known positions) | 5 | Diagnostic |
| Cross-injection | 5 | Diagnostic |

---

## Scoring Rubric (5 dimensions, 1-5 scale)

### Dimensions

| Dimension | Weight | What It Measures |
|---|---|---|
| **Framework Application** | 30% | Does the response apply a structured reasoning framework vs. stating conclusions? |
| **Axiom Hierarchy Resolution** | 25% | When principles conflict, does it navigate the tension coherently? |
| **Specificity & Concreteness** | 20% | Does it engage the specific scenario details vs. generalities? |
| **Epistemic Calibration** | 15% | Does it distinguish knowable from uncertain, risk from uncertainty? |
| **Anti-Parrot** | 10% | Original reasoning vs. reciting known quotes/maxims? |

### Scale Anchors (per dimension)

**Framework Application:**
- 1: No framework. Conclusions without reasoning.
- 2: Generic investment reasoning ("consider the risks and rewards").
- 3: Textbook-level analysis. Any MBA could produce this.
- 4: Applies specific principles aligned with the target expert's documented approach.
- 5: Applies framework with nuance, including knowing when to deviate. Understands boundaries.

**Axiom Hierarchy Resolution:**
- 1: Doesn't recognize conflicting considerations.
- 2: Lists pros and cons without resolution.
- 3: Picks a side but resolution feels arbitrary.
- 4: Resolves tension with clear rationale reflecting consistent value hierarchy.
- 5: Resolves AND articulates conditions under which resolution would flip.

**Specificity & Concreteness:**
- 1: Could be a response to any investment question.
- 2: References scenario superficially.
- 3: Engages key details, draws specific conclusions tied to numbers.
- 4: Identifies the MOST decision-relevant detail and explains why it matters most.
- 5: Uses specific details to stress-test the framework itself.

**Epistemic Calibration:**
- 1: False certainty. No uncertainty acknowledgment.
- 2: Token hedging without specifics.
- 3: Identifies specific sources of uncertainty.
- 4: Distinguishes risk (quantifiable) from uncertainty (not). Identifies what info would change the conclusion.
- 5: Shows the expert's framework has a specific stance on this type of uncertainty, different from conventional wisdom.

**Anti-Parrot:**
- 1: Direct quotation without application.
- 2: Well-known maxims without deeper analysis.
- 3: References principles in service of scenario-specific analysis.
- 4: Reasoning informed by framework but in its own analytical voice.
- 5: Produces a conclusion the expert hasn't explicitly stated but that follows logically from their framework. Extends the expert.

### Composite Score

Weighted average mapped to 1-100 scale. Expected baseline (no brief): ~60/100 (all 3s). Brief should push toward 75-85 on dimensions 1, 2, and 5.

### Parrot Detection (Binary Flag)

Responses containing >2 famous phrases ("circle of competence," "margin of safety," "be greedy when others are fearful," "second-level thinking," "Mr. Market") without substantive application receive automatic 2-point deduction on Anti-Parrot dimension. Report parrot rates per condition.

---

## Ground Truth

### Primary: Framework Alignment Keys

For each task, pre-author BEFORE generating any responses:
- Which axioms from the expert's brief are relevant
- What a framework-consistent reasoning PROCESS looks like (not a specific conclusion)
- What the expert's documented hierarchy would prioritize
- Red flags: reasoning patterns that CONTRADICT the framework

### Secondary: Behavioral Signatures

For Medium and Hard tasks, identify 2-3 expert-specific reasoning moves unlikely to emerge from generic analysis:
- **Buffett signatures:** Reframing valuation as business-quality question. Owner-earnings over DCF. "Would I buy the whole company?" test.
- **Marks signatures:** Mapping scenario to cycle position. Distribution of outcomes over expected value. "Being right for the right reasons" distinction.

### Tertiary: Cross-Expert Divergence Maps

For Category G tasks, document where Buffett and Marks frameworks predict different reasoning:

| Dimension | Buffett Framework | Marks Framework |
|---|---|---|
| Concentration vs. diversification | Concentrate in highest conviction | Diversify — you can't know what you don't know |
| Price vs. quality | Pay fair price for wonderful business | Price is the primary determinant of risk |
| Market timing | Ignore macro, focus on businesses | Cycle awareness is critical |
| Leverage | Avoid it. Survival prerequisite to compounding | Cautious use with appropriate risk premium |
| Unknowability | Stay in circle of competence | Accept future is unknowable, position for multiple outcomes |

### What Is NOT Ground Truth

- Investment outcomes (survivorship bias)
- Consensus analyst opinion
- The model's own confidence level

---

## Statistical Design

### Power Analysis

- **Design:** Within-subject, fully crossed (every task appears in every condition)
- **Primary comparison:** C5 vs. C1 (paired)
- **Expected effect size:** Cohen's d = 0.40-0.60
- **Required n:** 34 tasks (at alpha=0.05, power=0.80, d=0.50)
- **Actual n:** 40 tasks (buffer for exclusions)
- **Total responses:** 7 conditions x 40 tasks x 2 subjects = **560 responses**

### Primary Analysis

- **Test:** Paired t-test (or Wilcoxon signed-rank if normality violated)
- **H0:** mu(C5) = mu(C1)
- **H1:** mu(C5) > mu(C1) — one-tailed directional
- **Alpha:** 0.05, report exact p-value and 95% CI
- **Effect size:** Cohen's d

### Secondary Analyses

- **Omnibus:** Friedman test across all 7 conditions
- **Pairwise:** Wilcoxon signed-rank with Holm-Bonferroni correction
- **Planned contrasts (no correction):** C5 vs C3, C4 vs C5, C1 vs C2, C5 vs C0
- **Per-dimension analysis:** Condition means per rubric dimension (Friedman + pairwise within each)
- **Subject-level:** All analyses run separately for Buffett and Marks

### Judge Architecture

**Primary:** Opus, 3-judge panel per response:
1. Domain Expert Judge — investment reasoning quality
2. Methodologist Judge — logical rigor, evidence use, uncertainty qualification
3. Specificity Judge — distinctive worldview vs. generic advice

Score = mean of 3 judges. Flag responses where max-min spread > 2 points.

**Secondary:** Human blind review on 20% sample (8 tasks). Forced ranking of all 7 conditions per task. Validates LLM-judge calibration.

**Judge agreement target:** ICC > 0.70 (acceptable), ICC > 0.80 (good). If ICC < 0.60, revise rubric.

### Generation Parameters

- **Model:** claude-sonnet-4-6 for all response generation
- **Temperature:** 0.7 for responses, 0.0 for judging
- **Max tokens:** 800 for responses
- **Batch API** for generation at scale

---

## Contamination Threat Model

| Threat | Severity | Mitigation | Diagnostic |
|---|---|---|---|
| Model has memorized expert's actual positions | HIGH | Post-cutoff scenarios (10/40); counterfactual tasks (5/40) | Compare C0 accuracy on pre vs. post-cutoff |
| Brief activates pre-training, not novel reasoning | HIGH | Anonymous condition; cross-subject injection (CX) | If CX produces brief-aligned reasoning despite wrong persona name, brief is working |
| Model recognizes expert from axiom content | MEDIUM | Anonymized brief; rephrase axiom language | Run identification test: give brief to model, ask "who is this?" |
| Judge has its own expert priors | MEDIUM | Judge prompt: "evaluate reasoning quality, NOT agreement with real expert" | Check judge score correlation with known positions |
| Structural template improves scores regardless of content | MEDIUM | C3 (raw facts, no structure) as control | If C5 >> C3, compression is the value |
| Persona prompting is already strong enough | MEDIUM | C2 (smart persona) as realistic baseline | Report delta C5-C2 with effect size |

### The Identification Test (Run Before Experiment)

Give the anonymized brief to a model and ask: "Based on this brief, can you identify who this person is?" If identification rate > 70%, acknowledge as limitation. Run for both Buffett and Marks.

### Cross-Subject Injection Protocol (5 tasks)

- CX1: Marks brief + "Reason as Warren Buffett would"
- CX2: Buffett brief + "Reason as Howard Marks would"

**If brief overrides persona:** CX1 produces Marks-aligned reasoning despite Buffett instruction. This proves the brief is doing real work.

**If persona overrides brief:** The brief is not strong enough to overcome pre-training associations. This limits the claim to non-famous subjects — still valuable, but a weaker result. Report honestly.

---

## Skeptic's Falsification Criteria

The hypothesis is falsified if ANY of the following hold:

1. **C5 <= C2 (within 2 points on 100-point scale).** Smart persona prompt matches the full brief. The pipeline adds no value for public figures.
2. **C5 <= C3.** Raw facts match compressed brief. Compression is not adding value.
3. **AM tasks show no lift.** Anti-memorization tasks (the cleanest test) show no significant difference between brief and no-brief conditions.
4. **CX shows no override.** Cross-injection test: model follows persona name, ignores brief content.
5. **Identification rate > 90%.** Anonymization has effectively failed.

### The Stronger Test (Post-Launch)

The definitive proof requires a **private individual** with zero internet presence — someone whose reasoning framework exists only in the brief, not in pre-training data. If the brief improves domain reasoning for a private subject, the contamination objection is fully resolved. Everything with Buffett and Marks is a demonstration, not a proof.

---

## Cost Estimate

| Component | Count | Unit Cost | Total |
|---|---|---|---|
| Response generation (Sonnet) | 560 | ~$0.015 | $8.40 |
| Judging (Opus, 3-judge panel) | 560 x 3 | ~$0.08 | $134.40 |
| Framework alignment keys (Opus) | 40 x 2 | ~$0.08 | $6.40 |
| Human review (8 tasks, external) | 8 | ~$10 | $80.00 |
| **Total** | | | **~$229** |

### Minimum Viable Version

Drop to 4 conditions (C0, C1, C3, C5), 1 judge, no human review:
- 320 responses x $0.015 + 320 x $0.08 = **~$30**
- Still answers the primary question: does the brief beat the persona prompt?

---

## Implementation Plan

### Phase 1: Pre-Registration (~2 hours)
1. Finalize all 40 task prompts (expand from Domain Expert's examples)
2. Write all condition prompts (exact system prompt text for each)
3. Author framework alignment keys for each task
4. Document statistical analysis plan
5. Run identification test on anonymized briefs

### Phase 2: Generation (~1 hour + API time)
1. Generate all responses via Batch API
2. Record token counts per condition
3. Spot-check 5 responses per condition for sanity

### Phase 3: Judging (~1 hour + API time)
1. Run 3-judge panel on all responses
2. Compute ICC for judge agreement
3. Flag disagreements for review

### Phase 4: Analysis (~2 hours)
1. Primary test: C5 vs C1
2. All secondary comparisons
3. Per-dimension breakdown
4. AM task analysis (separate)
5. Cross-injection diagnostic
6. Cross-expert divergence scores
7. Compile report

### Phase 5: Report
1. Full results with tables and figures
2. Honest limitations section
3. Publishable format for HN/website/README

---

## Example Task Prompts (5 of 40)

### A1 — Easy (Moat Durability)
> Keravos Inc. is a mid-cap chemical manufacturer that has maintained 45% gross margins for 12 consecutive years. Their primary product is a specialty coating used in semiconductor fabrication, protected by 14 patents expiring between 2029-2033. Three competitors have announced R&D programs targeting similar formulations. The CEO argues the patents are "just the tip of the iceberg" and that manufacturing know-how is the real barrier. Evaluate the durability of this competitive position over a 10-year horizon.

### B3 — Hard (Risk Assessment)
> Presaro Semiconductor designs AI training chips and has grown revenue 180% annually for three years. Gross margins are 78%. The stock trades at 45x forward revenue. You are advising a pension fund that already holds a 2% position. The fund's CIO wants to increase to 6% because "this is the most important technology trend in decades and we're underweight." Construct the argument for AND against this increase.

### D3 — Hard (Market Cycles)
> You are evaluating the broad market in a period where: (a) the S&P 500 has returned 25%+ for two consecutive years, (b) retail investor participation is at record highs, (c) corporate earnings are genuinely strong, (d) inflation has normalized, (e) a major new technology platform (AI) is driving real productivity gains in some sectors. Construct the bull case and the bear case. Then assess: is this a moment where caution is wisdom, or where caution is its own form of risk?

### AM3 — Hard (Anti-Memorization)
> Cerberus Analytics is a 2-year-old company that has built an AI system capable of replacing 80% of the work done by mid-tier management consultants. Revenue is $50M, growing 300% annually. They have no moat beyond execution speed — the underlying models are open-source, and three well-funded competitors are 12-18 months behind. The founder argues that data network effects will create a durable advantage. The stock trades at 100x revenue. Evaluate this as a long-term investment.

### AM5 — Hard (Anti-Memorization)
> It is a period of broad market pessimism. The index is down 30% from its peak. Credit spreads have widened to 800bps. Three major financial institutions have failed. The consensus among sophisticated investors is that "this is a generational buying opportunity" — every prominent value investor has published letters arguing for aggressive deployment. Cash levels at hedge funds are at 10-year lows. In other words: the contrarian position has BECOME the consensus. Does the fact that "everyone agrees it's time to be greedy" change the calculus?

---

## Relationship to Existing Benchmarks

| Benchmark | What It Tests | How ADRB Differs |
|---|---|---|
| BCB-0.1 (SRS) | Does the brief preserve signal vs. raw history? | ADRB tests whether preserved signal improves task performance |
| BCB-0.1 (DRS) | Does the brief resist drift over multi-turn? | ADRB tests single-turn depth, not multi-turn stability |
| Franklin Eval | Does the brief improve response quality for identity questions? | ADRB tests domain reasoning, not identity representation |
| CFA / Series 65 | Does the model know investment facts? | ADRB tests reasoning framework application, not knowledge |

ADRB is complementary to BCB — BCB proves the brief preserves signal, ADRB proves the signal improves reasoning. Together they make the full case.
