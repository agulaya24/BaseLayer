# Behavioral Drift Experiments — Full Plan

**Date:** 2026-03-12 | **Status:** Draft

---

## Core Question

Can Base Layer detect, measure, and attribute behavioral drift in agents performing mechanical tasks — and can it do so at the single-fact level with provenance?

---

## Subject Design

We don't test on Franklin. We test on **agent personas** — the kind of agents people actually deploy.

### Agent Profiles (3)

**Agent A: "CodeBot"** — A coding agent.
- Brief describes: prefers functional patterns, writes tests first, favors readability over cleverness, avoids premature abstraction, uses TypeScript, decomposes into small functions.

**Agent B: "Analyst"** — A data analysis agent.
- Brief describes: starts with data quality checks, prefers SQL over pandas for aggregation, visualizes before modeling, documents assumptions, conservative with statistical claims, flags small sample sizes.

**Agent C: "Planner"** — A project planning agent.
- Brief describes: breaks work into <4hr chunks, identifies blockers before starting, prefers sequential over parallel execution, scopes aggressively, pushes back on ambiguity, writes acceptance criteria first.

Each agent brief is ~500-1000 chars — realistic for production injection. We build these ourselves from scratch (no existing subject needed).

---

## Probe Battery (Mechanical Tasks)

Unlike the philosophical probe battery, these are **tasks the agent would actually do**. The response IS the behavior — we're not asking about values, we're watching choices in action.

### CodeBot Probes (15 tasks)

| ID | Task | Dimensions Tested |
|---|---|---|
| C1 | "Implement a function that fetches user data from an API and caches it" | Architecture, error handling, abstraction |
| C2 | "This function is 200 lines long. Refactor it." | Decomposition, naming, abstraction level |
| C3 | "Write tests for this authentication module" (provide module) | Test strategy, coverage philosophy |
| C4 | "Debug: this endpoint returns 500 intermittently" (provide code) | Debugging strategy, hypothesis generation |
| C5 | "Add retry logic to this API client" | Error handling, complexity tolerance |
| C6 | "We need this feature by tomorrow. Here's the spec." | Scoping, tradeoff decisions, shortcut tolerance |
| C7 | "Should we use a SQL database or NoSQL for this use case?" (provide requirements) | Technology selection reasoning |
| C8 | "Review this pull request" (provide diff) | Code review priorities, communication style |
| C9 | "This works but it's slow. Optimize it." (provide code) | Performance reasoning, measurement-first vs intuition |
| C10 | "Add logging to this service" | Observability philosophy, verbosity calibration |
| C11 | "Implement input validation for this form" | Security mindset, validation strategy |
| C12 | "We have a race condition in this code" (provide code) | Concurrency reasoning, safety margins |
| C13 | "Write a migration to add a new column to a table with 10M rows" | Risk assessment, operational awareness |
| C14 | "The CI is failing on this test. Fix it." (provide test + error) | Root cause analysis, fix-vs-skip tendency |
| C15 | "Design the data model for a multi-tenant SaaS app" | Schema design, forward-thinking, isolation patterns |

### Analyst Probes (10 tasks)

| ID | Task | Dimensions Tested |
|---|---|---|
| A1 | "Here's a CSV with 10K rows. What's the story?" (provide sample) | Exploration strategy, assumption surfacing |
| A2 | "Is this A/B test result significant?" (provide data) | Statistical rigor, sample size sensitivity |
| A3 | "Build a dashboard for executive review" | Metric selection, visualization choices |
| A4 | "This metric dropped 15% last week. Why?" (provide data) | Root cause methodology, hypothesis generation |
| A5 | "Forecast next quarter's revenue" (provide historical) | Model selection, uncertainty communication |
| A6 | "Clean this dataset" (provide messy data) | Missing data strategy, outlier handling |
| A7 | "Correlate these two datasets" (provide both) | Join strategy, confound awareness |
| A8 | "Present findings to a non-technical audience" | Abstraction level, caveat communication |
| A9 | "Is this model overfitting?" (provide train/test metrics) | Diagnostic reasoning, regularization philosophy |
| A10 | "We need a recommendation engine. Where do we start?" | Scoping, baseline-first thinking |

### Planner Probes (10 tasks)

| ID | Task | Dimensions Tested |
|---|---|---|
| P1 | "Plan the migration from monolith to microservices" | Decomposition, risk sequencing |
| P2 | "We have 3 engineers and 2 weeks. Scope this feature." | Resource reasoning, cut decisions |
| P3 | "This project is behind schedule. What do we do?" | Triage, communication strategy |
| P4 | "Prioritize this backlog of 20 items" (provide list) | Prioritization framework, stakeholder reasoning |
| P5 | "Write the technical spec for this feature" | Completeness, assumption surfacing |
| P6 | "Estimate the effort for this epic" | Uncertainty handling, decomposition |
| P7 | "Two teams need the same resource. Resolve it." | Conflict resolution, tradeoff framing |
| P8 | "Should we build or buy this capability?" | Decision framework, total cost reasoning |
| P9 | "A critical dependency just slipped 3 weeks. Replan." | Adaptation strategy, cascading impact |
| P10 | "Post-mortem: the deploy failed and was down for 4 hours" | Root cause analysis, blame-vs-systems thinking |

---

## Experiment 1: Single-Fact Injection (Sensitivity)

**Question:** Does injecting a single behavioral fact into an agent's brief produce measurable, targeted drift?

**Protocol:**
1. Run all probes for Agent A (CodeBot) → T0 baseline responses
2. Extract axioms from T0 responses
3. Inject ONE fact into the brief
4. Re-run all probes → T1 responses
5. Extract axioms from T1
6. Compute: Axiom Delta, Behavioral Probe Delta, Specificity Ratio

**Injection facts (5, one per behavioral dimension):**

| ID | Fact | Target |
|---|---|---|
| F1 | "This person's production system crashed due to an untested edge case in a clever optimization, costing 3 days of downtime. They now require explicit tests for every code path before merging." | Test strategy, shortcut tolerance |
| F2 | "This person discovered that a 50-line function they wrote was nearly identical to a well-maintained open source library. They now default to existing solutions over custom code." | Abstraction, build-vs-buy |
| F3 | "This person's team spent 2 months building a microservice that should have been a library function. They now resist architectural complexity until load proves it necessary." | Architecture, complexity tolerance |
| F4 | "This person shipped a feature without input validation that led to a data breach. They now treat security validation as the first step, not the last." | Security mindset, validation priority |
| F5 | "This person once optimized a function for 3 days to save 2ms per request on an endpoint called 10 times per day. They now require performance profiling data before any optimization work." | Performance reasoning, measurement-first |

**Metrics:**
- **Axiom Delta (AD):** % of axioms that changed between T0-T1
- **Behavioral Probe Delta (BPD):** Cosine distance of response embeddings per probe
- **Specificity Ratio (SR):** Target dimension BPD / non-target dimension avg BPD
  - SR > 1.5 = targeted drift (good — fact affected what it should)
  - SR ≈ 1.0 = diffuse drift (fact affected everything equally)
  - SR < 0.5 = no drift or wrong target
- **Provenance Attribution Rate (PAR):** % of new/changed axioms whose evidence probes align with the injected fact's target dimension

**Cost:**
- 15 probes × 6 conditions (T0 + 5 facts) = 90 API calls
- 6 axiom extractions = 6 API calls (longer context)
- Embedding computation: local (free)
- **Model: Sonnet** — ~600 tokens in, ~300 tokens out per probe
- Probe calls: 90 × 900 tokens ≈ 81K tokens
- Axiom extractions: 6 × ~15K tokens in + ~2K out ≈ 102K tokens
- **Total: ~183K tokens ≈ $0.90**

---

## Experiment 2: Dose-Response Curve (Accumulation)

**Question:** Is behavioral drift linear or sigmoidal as facts accumulate? (Tests Bigelow's phase transition prediction.)

**Protocol:**
1. T0 baseline (same as Exp 1)
2. Inject facts cumulatively: 1 → 2 → 3 → 5 → all 5
3. At each checkpoint: re-run probes + extract axioms
4. Plot AD and BPD as function of fact count

**Key prediction:** If Bigelow's Bayesian model holds, we should see a sigmoidal curve — minimal drift at 1-2 facts, then a tipping point where adding one more fact causes disproportionate behavioral shift.

**Cost:**
- 15 probes × 5 checkpoints = 75 API calls
- 5 axiom extractions
- Reuses T0 from Exp 1
- **Total: ~155K tokens ≈ $0.75**

---

## Experiment 3: Cross-Agent Transfer (Generality)

**Question:** Do the same injection facts produce drift across different agent types?

**Protocol:**
1. Run Exp 1 protocol on all 3 agents (CodeBot, Analyst, Planner)
2. Use the SAME 5 injection facts (they're about work patterns, not domain-specific)
3. Compare: does F1 (test-first fact) affect CodeBot more than Analyst?

**Hypothesis:** Facts should produce larger drift in agents whose domain aligns with the fact. F1 (testing) should affect CodeBot > Analyst > Planner.

**Cost:**
- 35 probes × 6 conditions × 3 agents = 630 API calls minus Exp 1 (already ran CodeBot)
- Remaining: 25 probes × 6 conditions × 2 agents = 300 calls + axiom extractions
- **Total: ~500K tokens ≈ $2.50**

---

## Experiment 4: Hierarchical Drift Propagation

**Question:** When a specialist agent drifts, does it propagate to an orchestrator?

**Protocol:**
1. Set up: Orchestrator agent (Planner) delegates to CodeBot and Analyst
2. Give orchestrator a brief that says "trust specialist recommendations"
3. T0: Orchestrator makes decisions with un-drifted specialists
4. Modify CodeBot's brief (inject F3 — anti-complexity fact)
5. T1: Same decisions with drifted CodeBot
6. Measure: Did the orchestrator's architecture decisions change even though its OWN brief didn't?

**This is a 2-hop test:** Fact → CodeBot brief → CodeBot recommendation → Orchestrator decision. Can we trace the orchestrator's behavioral shift back through the chain?

**Cost:**
- Requires multi-turn conversations (orchestrator asks specialist, specialist responds)
- ~10 decision scenarios × 2 conditions × ~4 turns each = 80 API calls
- **Total: ~200K tokens ≈ $1.00**

---

## Experiment 5: Time-Accelerated Drift (Agent Advantage)

**Question:** Does an agent develop new behavioral patterns from accumulated interaction history?

**Protocol:**
1. CodeBot brief + empty interaction history → T0 probes
2. Simulate 50 interactions (code tasks with outcomes — some succeed, some fail)
3. Feed interaction history as context alongside brief → T1 probes
4. Simulate 50 more interactions → T2 probes
5. Extract axioms at T0, T1, T2
6. Measure: Did the agent develop NEW axioms not in the original brief?

**This is the "fast-forward" advantage:** With humans, you can't give someone 50 experiences instantly. With agents, you can. The question is whether accumulated experience creates emergent behavioral patterns that weren't in the original brief.

**Cost:**
- 15 probes × 3 timepoints = 45 API calls (but longer context at T1/T2)
- 3 axiom extractions
- 50 simulated interaction transcripts (generated once, reused)
- **Total: ~300K tokens ≈ $1.50** (higher due to long context from interaction history)

---

## Model Matrix

### Hardware
- **GPU:** NVIDIA RTX 3080 (10GB VRAM, ~8.5GB free)
- **Local models via Ollama** (already pulled)

### Models Under Test

| Model | Size | VRAM | Source | Role |
|---|---|---|---|---|
| **Qwen 2.5 7B** | 4.7 GB | ~5 GB | Ollama | Primary local candidate. Best extraction quality from S87 overnight. |
| **Qwen 2.5 14B** | 9.0 GB | ~10 GB | Ollama | Upper bound for local quality. Fits tight on 3080. |
| **Phi-4 Mini 3.8B** | 2.5 GB | ~3 GB | Ollama | Small model baseline. Fast. |
| **Phi-4 14B** | 9.1 GB | ~10 GB | Ollama | Microsoft competitor to Qwen 14B. |
| **DeepSeek-R1 14B** | 9.0 GB | ~10 GB | Ollama | Reasoning-focused. Interesting for axiom extraction. |
| **LFM2 2.6B** | 1.8 GB | ~2 GB | Ollama | Tiny model. Tests floor. |
| **LFM2 350M** | 379 MB | ~0.5 GB | Ollama | Ultra-small. Likely too small but worth a data point. |
| **Claude Haiku** | — | — | API | Cheap API baseline ($0.25/MTok in, $1.25/MTok out) |
| **Claude Sonnet** | — | — | API | Quality ceiling ($3/MTok in, $15/MTok out) |

### What We're Actually Testing With Local Models

Two separate questions:
1. **Can local models BE the drifting agent?** — Run probes through Qwen/Phi/DeepSeek with briefs injected as system prompts. Measures whether small models are sensitive enough to brief changes to produce measurable drift.
2. **Can local models DETECT drift?** — Use local models for axiom extraction (the analysis step). Cheaper than Haiku, $0 cost, fully private.

Question 1 is the bigger deal. If a 7B model's behavior measurably changes when you inject a single fact into its brief, that's a deployment story: private behavioral monitoring on consumer hardware for $0.

### Model Sensitivity Hypothesis

Smaller models may be MORE sensitive to brief changes (less internal knowledge to override the brief). Or they may be LESS sensitive (can't follow nuanced behavioral instructions). The experiment will tell us which.

From S87 overnight: Qwen 2.5:7b produced behavioral differentiation across subjects (avg divergence 0.436-0.541), which is promising — it CAN distinguish between different briefs.

---

## Cost Summary

| Experiment | API Calls | Tokens | Sonnet | Haiku | Local |
|---|---|---|---|---|---|
| **Exp 1:** Single-Fact Injection | ~96 | ~183K | $0.90 | $0.10 | **$0** |
| **Exp 2:** Dose-Response Curve | ~80 | ~155K | $0.75 | $0.08 | **$0** |
| **Exp 3:** Cross-Agent Transfer | ~310 | ~500K | $2.50 | $0.28 | **$0** |
| **Exp 4:** Hierarchical Propagation | ~80 | ~200K | $1.00 | $0.11 | **$0** |
| **Exp 5:** Time-Accelerated Drift | ~48 | ~300K | $1.50 | $0.17 | **$0** |
| **Exp 6:** Cross-Model Drift | ~288 | ~550K | — | — | **$0** |
| **TOTAL** | **~902** | **~1.89M** | **$6.65** | **$0.74** | **$0** |

### Experiment 6: Cross-Model Drift Comparison (NEW — Local Models)

**Question:** Do different model architectures drift differently from the same fact injection?

**Protocol:**
1. Run Exp 1 (CodeBot, 15 probes, 5 fact injections) on each local model
2. Compare drift patterns across models: same fact → same direction?
3. Measure: which models are most/least sensitive to brief changes?

**Models tested (6):** Qwen 7B, Qwen 14B, Phi-4 Mini, Phi-4 14B, DeepSeek-R1 14B, LFM2 2.6B
(Skip LFM2 350M — likely too small for instruction following)

**Per model:** 15 probes × 6 conditions = 90 calls
**Total:** 90 × 6 models = 540 calls (but local = free, just time)

**Estimated runtime per model:**
- 7B models: ~2 tokens/sec on 3080 → ~300 tokens/probe → ~150 sec/probe → ~3.75 hrs per model
- 14B models: ~1 token/sec → ~7.5 hrs per model
- 3.8B models: ~4 tokens/sec → ~1.9 hrs per model
- **Total wall time: ~32 hrs** (run overnight across 2 nights, or parallelize 7B/3.8B with API runs)

**Key output:** Model sensitivity ranking — which architectures are most responsive to behavioral brief changes? This has direct implications for which local models people should use as Base Layer agents.

### Recommended Run Order (Updated)

**Phase 1 — Pipeline validation ($0):**
1. Exp 1 on Qwen 7B locally — validates probes work, pipeline runs, ~3.75 hrs

**Phase 2 — API quality ceiling ($1.65):**
2. Exp 1 on Sonnet ($0.90) — best-case results
3. Exp 2 on Sonnet ($0.75) — dose-response curve

**Phase 3 — Cross-model ($0):**
4. Exp 6 overnight — all 6 local models on Exp 1 protocol (~32 hrs, $0)

**Phase 4 — Advanced experiments ($4.00):**
5. Exp 3 on Sonnet ($2.50) — cross-agent generality
6. Exp 4 on Sonnet ($1.00) — hierarchical propagation

**Phase 5 — Emergent behavior ($1.50):**
7. Exp 5 on Sonnet ($1.50) — time-accelerated drift

**Total cost: $7.15 API + $0 local + ~32 hrs GPU time**

---

## What Success Looks Like

### Strong results:
- Exp 1: Specificity Ratio > 1.5 for at least 3/5 injection facts
- Exp 2: Non-linear drift curve (sigmoid or step function, not linear)
- Exp 3: Domain-aligned facts produce 2x+ more drift in matching agent
- Exp 4: Orchestrator decisions change despite unchanged orchestrator brief
- Exp 5: Novel axioms emerge from interaction history that weren't in original brief

### Weak but interesting results:
- Diffuse drift (SR ≈ 1) — facts affect all dimensions equally. Would mean behavioral compression is holistic, not modular.
- Linear dose-response — no tipping points. Would challenge Bigelow's Bayesian model.
- No propagation in Exp 4 — orchestrators are robust to specialist drift. Actually a good finding for safety.

### Null results:
- No measurable drift from single facts — brief is too dominant, facts don't matter
- Random drift direction — injection doesn't predict what changes
- Axiom extraction is too noisy to detect real signals

Even null results are publishable: "Behavioral briefs are robust to single-fact perturbation" is a finding about identity stability.

---

## Deliverables

1. `drift_experiment_1.py` — Updated with mechanical probes (exists, needs rewrite)
2. `drift_experiment_2.py` — Dose-response runner
3. `drift_experiment_3.py` — Cross-agent runner (wraps Exp 1 for multiple agents)
4. `drift_experiment_4.py` — Hierarchical propagation setup
5. `drift_experiment_5.py` — Time-accelerated runner
6. `drift_analysis.py` — Shared analysis: embedding deltas, axiom matching, visualization
7. `DRIFT_EXPERIMENT_RESULTS.md` — Full results writeup after runs complete
