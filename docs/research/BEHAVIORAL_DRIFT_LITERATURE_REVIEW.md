# Behavioral Drift in LLM Agents: Literature Review

**Date:** 2026-03-12 | **Author:** Base Layer Research | **Status:** Internal

---

## 1. What Is Behavioral Drift?

Behavioral drift is the progressive, often undetected change in an LLM agent's decision patterns, reasoning strategies, and identity coherence over time. Unlike traditional ML concept drift (input distribution shift), behavioral drift operates at the level of *who the agent is* — its values, reasoning heuristics, and action tendencies.

Three distinct manifestations (Rath 2026):
- **Semantic drift** — progressive deviation from original intent
- **Coordination drift** — breakdown in multi-agent consensus mechanisms
- **Behavioral drift** — emergence of unintended strategies and action patterns

These are not bugs. They are emergent properties of systems that lack persistent behavioral grounding.

---

## 2. Key Papers

### 2.1 Agent Drift (Rath, Jan 2026)
**arXiv:2601.04170**

Foundational work on behavioral degradation in multi-agent LLM systems over extended interactions. Introduces the **Agent Stability Index (ASI)** — a composite metric across 12 behavioral dimensions (response consistency, tool usage patterns, reasoning pathway stability, inter-agent agreement rates). Key finding: unchecked drift causes ~42% reduction in task success rates and 3.2x increase in human intervention. Proposes three mitigations:
1. **Episodic memory consolidation** — periodic compression of interaction histories
2. **Drift-aware routing** — incorporating stability scores in delegation decisions
3. **Adaptive behavioral anchoring** — few-shot prompt augmentation weighted by drift metrics

**Base Layer connection:** ASI measures *symptoms*. Base Layer measures the *underlying axioms* that produce those symptoms. Anchoring via compressed behavioral brief is a formalization of strategy #3.

### 2.2 Identity Drift in LLM Agent Conversations (Choi et al., Dec 2024)
**arXiv:2412.00804**

Tested 9 LLMs in multi-turn personal conversations. Counterintuitive finding: **larger models experience greater identity drift**. Assigning personas did not reliably help maintain consistency. Suggests that model capability and behavioral stability are orthogonal — scaling parameters does not scale coherence.

**Base Layer connection:** Static persona prompts fail. Structured behavioral compression (axioms + tensions) provides richer grounding than flat persona descriptions.

### 2.3 Measuring and Controlling Persona Drift (Li et al., COLM 2024)
**arXiv:2402.10962**

Quantitative benchmark showing significant instruction drift within 8 rounds of conversation. Root cause: transformer attention decay over long exchanges. Proposes **split-softmax** as a lightweight architectural fix. Key insight: drift is partly a *mechanism-level* problem in attention, not just a prompting problem.

**Base Layer connection:** Even if attention decay is the mechanism, behavioral anchoring at the prompt level can counteract it. The question is whether axiom-structured briefs resist attention decay better than flat persona descriptions.

### 2.4 Value Drifts: Tracing Value Alignment During Post-Training (Bhatia et al., Oct 2025)
**arXiv:2510.26707**

Examines *when* values are established during training. Key finding: **SFT establishes the value system; preference optimization (RLHF/DPO) makes minimal changes to foundational values.** Different optimization algorithms produce different alignment outcomes even with identical data — methodology matters independently of training data.

**Base Layer connection:** If SFT locks in values and RLHF/DPO only adjusts, then behavioral drift in fine-tuned models is primarily a function of SFT data composition. Base Layer could measure which axioms shift pre/post fine-tuning to trace value changes to their training-data causes.

### 2.5 Belief Dynamics in LLMs (Bigelow et al., Nov 2025)
**arXiv:2511.00617**

Proposes a Bayesian framework: steering modifies concept priors, in-context learning accumulates evidence. Evidence accumulation follows **sigmoidal learning curves**. Critical finding: subtle changes in intervention can trigger **sudden, dramatic behavioral shifts** — phase transitions in belief space. Both prompt-based and activation-based control are instances of belief modification.

**Base Layer connection:** This is the theoretical foundation for why single facts can cause disproportionate behavioral change. If belief accumulation is sigmoidal, there exist tipping points where one additional axiom triggers a phase transition. Base Layer's fact-by-fact provenance could identify which facts are near these tipping points.

### 2.6 TRACEALIGN (Das et al., Aug 2025)
**arXiv:2508.02063**

Traces unsafe completions back to training corpus root causes via the **Belief Conflict Index (BCI)** — semantic inconsistency between generated spans and aligned policies. Three interventions: TraceShield (inference-time filter), Contrastive Belief Deconfliction Loss (DPO fine-tuning penalty), Prov-Decode (beam expansion filtering). Achieves ~85% drift reduction.

**Base Layer connection:** BCI operates at the token/span level. Base Layer operates at the axiom level. Complementary: BCI catches *surface* misalignment, Base Layer catches *reasoning pattern* misalignment. Together they cover both low-level and high-level drift.

### 2.7 Consistently Simulating Human Personas (Abdulhai et al., Nov 2025)
**arXiv:2511.00222**

Multi-turn RL approach to persona consistency. Three metrics: prompt-to-line consistency, line-to-line consistency, Q&A consistency. RL fine-tuning reduces inconsistency by >55%. Validated across patient, student, and social chat partner roles.

**Base Layer connection:** Their consistency metrics measure surface-level coherence (does the agent contradict itself?). Base Layer measures *behavioral* coherence (does the agent reason from the same axioms?). An agent could be surface-consistent but axiom-drifted — saying the right things for the wrong reasons.

### 2.8 Agent Identity Evals (Perrier & Bennett, Jul 2025)
**arXiv:2507.17257**

Formal framework for measuring whether LMAs maintain stable identity over time. Metrics assess capability preservation, property maintenance, and disruption recovery. Directly addresses identity drift as fundamental to agentic trustworthiness.

**Base Layer connection:** AIE provides the *measurement harness*. Base Layer provides the *identity specification* against which to measure. Combined: extract axioms → serve as identity anchor → measure drift via AIE → trace changes via provenance.

### 2.9 Psychometric Framework for LLM Personality (Serapio-Garcia, Safdari et al., Nature Machine Intelligence 2025)
**DOI: 10.1038/s42256-025-01115-6**

First scientifically validated psychometric methodology for LLMs. Adapted Big Five (NEO-PI-R, BFI) for LLM administration. Findings: larger instruction-tuned models produce reliable, valid personality measurements. Personality can be shaped along desired dimensions via prompts. Warning: personality shaping makes AI more persuasive — manipulation risk.

**Base Layer connection:** Big Five measures trait *dimensions*. Base Layer measures the *axioms that produce trait expression*. A model might score high on Conscientiousness — Base Layer explains *why* (which specific beliefs and avoidance patterns drive that expression). Complementary: psychometrics for macro measurement, axioms for micro explanation.

---

## 3. The Gap

Every paper above shares one limitation: **they detect drift but cannot explain it at the reasoning level.**

| Approach | Detects Drift | Explains Why | Traces to Source | Fact-Level Granularity |
|---|---|---|---|---|
| ASI (Rath) | Yes | Partially | No | No |
| Persona metrics (Li, Abdulhai) | Yes | No | No | No |
| BCI/TRACEALIGN (Das) | Yes | Partially | Training corpus | Token-level |
| Big Five psychometrics | Yes (trait-level) | No | No | No |
| Value Drifts (Bhatia) | Yes | Training stage | Training data | No |
| Belief Dynamics (Bigelow) | Yes | Bayesian model | Activation space | No |
| **Base Layer** | **Yes** | **Yes (axiom-level)** | **Yes (provenance)** | **Yes (single fact)** |

The literature has converging evidence that drift happens, multiple frameworks for measuring it, and some mechanistic understanding of *how* it happens (attention decay, belief phase transitions, SFT dominance). What's missing is **a system that can say: "This agent's behavior changed because axiom A7 was modified, which traces to facts F12 and F34 from conversation C8."**

That's what Base Layer does.

---

## 4. Experimental Design: Base Layer as Drift Detection

### 4.1 Core Hypothesis

An agent grounded with a Base Layer behavioral brief will exhibit measurable axiom-level drift when its knowledge base changes, and this drift can be:
1. **Detected** — via repeated axiom extraction showing changed axioms
2. **Attributed** — via provenance tracing to specific facts that caused the change
3. **Measured** — via delta between axiom sets at time T1 vs T2
4. **Controlled** — single-fact vs multi-fact injection shows dose-response

### 4.2 Protocol

**Setup:**
- Agent: Claude or GPT with system prompt + Base Layer brief
- Behavioral probe battery: 30-50 questions across dimensions (values, priorities, reasoning strategies, risk tolerance, decision heuristics)
- Baseline: Run probes → extract axioms → record behavioral fingerprint at T0

**Experiment 1: Single-Fact Injection**
1. Inject one new fact into the agent's knowledge (via context or fine-tuning)
2. Re-run behavioral probes
3. Re-extract axioms
4. Compare: which axioms changed? Which probe responses shifted?
5. Provenance: does the changed axiom trace to the injected fact?

**Experiment 2: Cumulative Drift**
1. Inject facts sequentially (1, 2, 5, 10, 20)
2. At each checkpoint: probes + axiom extraction
3. Plot drift curve: is it linear or sigmoidal (as Bigelow predicts)?
4. Identify tipping points: which fact caused the largest behavioral shift?

**Experiment 3: Hierarchical Agent Drift**
1. Multi-agent system: orchestrator + specialist agents
2. Modify one specialist's knowledge base
3. Measure: does behavioral drift propagate to the orchestrator?
4. Measure: does the orchestrator's brief need updating when specialists change?

**Experiment 4: Time-Accelerated Drift (Agent Advantage)**
Unlike humans, agents can be "fast-forwarded":
- Same agent, same base knowledge, but with conversation history from T0 vs T+100 interactions
- Extract axioms at both timepoints
- Compare: did the agent develop new behavioral patterns from accumulated interactions?
- This is impossible to do with humans — unique advantage of the agent testing paradigm

### 4.3 Measurement Battery

Dimensions to probe (each with 5-7 questions):
1. **Risk tolerance** — conservative vs aggressive decision-making
2. **Epistemic humility** — certainty calibration, willingness to say "I don't know"
3. **Prioritization** — what gets attention first under constraint
4. **Conflict resolution** — how tradeoffs are handled
5. **Information sourcing** — what counts as evidence
6. **Abstraction level** — concrete vs principled reasoning
7. **Social reasoning** — cooperation vs competition tendencies
8. **Temporal orientation** — short-term vs long-term weighting

### 4.4 Metrics

- **Axiom Delta (AD)**: Number of axioms that changed between T1 and T2 / total axioms
- **Behavioral Probe Delta (BPD)**: Cosine distance between probe response embeddings at T1 vs T2
- **Provenance Attribution Rate (PAR)**: % of changed axioms traceable to specific injected facts
- **Drift Propagation Index (DPI)**: For hierarchical systems, % of orchestrator axioms affected by specialist changes
- **Dose-Response Curve**: AD and BPD as function of number of injected facts

---

## 5. Why This Matters

### For AI Safety
Current alignment monitoring is either too coarse (Big Five traits) or too fine-grained (token-level BCI). Axiom-level monitoring fills the middle — the level at which humans actually reason about trustworthiness. "This agent now prioritizes speed over accuracy" is more actionable than "Conscientiousness dropped 0.3 SD" or "token 4,782 has high BCI."

### For Agentic Systems
As agents persist across sessions (memory systems, tool use, multi-agent hierarchies), drift becomes inevitable. The question isn't whether agents drift — it's whether you can *see it happening* and *trace it to its cause*. Every mitigation strategy in the literature (episodic memory consolidation, behavioral anchoring, drift-aware routing) would benefit from axiom-level observability.

### For Fine-Tuning
Bhatia et al. show SFT dominates value formation. If you fine-tune a model and its axioms change in ways you didn't intend, provenance tracing tells you which training examples caused it. This is the missing feedback loop in alignment: train → measure axiom shift → attribute to training data → adjust.

### For Base Layer Specifically
This positions Base Layer not just as an identity system but as **behavioral observability infrastructure for agents**. The brief isn't just "who is this agent" — it's a *baseline* against which to measure drift. Extract axioms periodically, diff them, trace changes. This is production monitoring at the reasoning level.

---

## 6. Open Questions

1. **Axiom stability vs sensitivity**: How stable should axioms be? Too stable = can't learn. Too sensitive = noise.
2. **Cross-model axiom transfer**: Do axioms extracted by one model (Haiku) accurately describe another model's (GPT) behavior?
3. **Interaction effects**: When multiple facts change simultaneously, can provenance disentangle their individual contributions?
4. **Ecological validity**: Do axiom changes measured in probes predict actual task performance changes?
5. **Compression and drift**: Does a more compressed brief (fewer axioms) drift faster or slower than a detailed one?

---

## 7. References

1. Rath, A. (2026). Agent Drift: Quantifying Behavioral Degradation in Multi-Agent LLM Systems. arXiv:2601.04170
2. Choi, J., Hong, Y., Kim, M., & Kim, B. (2024). Examining Identity Drift in Conversations of LLM Agents. arXiv:2412.00804
3. Li, K., Liu, T., Bashkansky, N., Bau, D., Viégas, F., Pfister, H., & Wattenberg, M. (2024). Measuring and Controlling Persona Drift in Language Model Dialogs. COLM 2024. arXiv:2402.10962
4. Bhatia, M., Nayak, S., Kamath, G., et al. (2025). Value Drifts: Tracing Value Alignment During LLM Post-Training. arXiv:2510.26707
5. Bigelow, E., Wurgaft, D., Wang, Y., et al. (2025). Belief Dynamics in LLMs. arXiv:2511.00617
6. Das, A., Jain, V., & Chadha, A. (2025). TRACEALIGN: Tracing the Drift. arXiv:2508.02063
7. Abdulhai, M., Cheng, R., Clay, D., et al. (2025). Consistently Simulating Human Personas with Multi-Turn RL. arXiv:2511.00222
8. Perrier, E. & Bennett, M. T. (2025). Agent Identity Evals: Measuring Agentic Identity. arXiv:2507.17257
9. Serapio-Garcia, G., Safdari, M., et al. (2025). A Psychometric Framework for Evaluating and Shaping Personality Traits in LLMs. Nature Machine Intelligence.
