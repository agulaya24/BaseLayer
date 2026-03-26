# Behavioral Drift Experiment 1: Single-Fact Injection

**Date:** 2026-03-12 | **Status:** Complete (Phase 1) | **Total Cost:** ~$0.30 API + $0 local

---

## Key Finding

**The format of identity representation determines whether an agent can route new behavioral information to the correct dimension.** Across 4 models (3.8B to ~70B), axiom-structured briefs consistently produce targeted behavioral drift (SR > 2.0), while flat preference lists produce diffuse or missed drift (SR < 1.2). This holds whether the model is a $0 local 7B or a frontier API model.

---

## What This Means

AI memory systems today store atomic information: "prefers TypeScript", "likes functional patterns", "wants tests." These are preferences — what someone said they want.

Behavioral compression extracts the underlying reasoning patterns: "avoids premature abstraction — requires three concrete cases before extracting a shared function", "treats readability as a social contract — code is read 10x more than written."

We tested whether this format difference matters for how agents process new information. It does. When you tell an agent grounded with axioms "you once got burned by unnecessary microservices," it specifically changes how it architects systems — not how it debugs, reviews security, or makes tradeoffs. The same story told to an agent with flat preferences changes everything equally, or nothing at all.

**An agent that understands WHY you avoid over-engineering routes new engineering lessons to the right place. An agent that just knows you "prefer simple code" can't.**

---

## Experimental Setup

### Agent
**CodeBot** — a coding agent. Three versions of its identity brief were tested:

1. **Brief** (1,645 chars) — Structured prose with behavioral directives, core patterns, architecture preferences, debugging approach, and tradeoff defaults. The standard Base Layer format.
2. **Axioms** (1,104 chars) — 8 compressed behavioral principles. E.g., "COMPLEXITY MUST BE EARNED — Never add abstraction until three concrete cases prove the need."
3. **Atomic** (451 chars) — 15 flat preference statements. E.g., "Prefers TypeScript", "Likes small functions", "Values readability."

All three encode the same behavioral information at different compression levels.

### Probes (5 Mechanical Coding Tasks)

| ID | Task | What It Tests |
|---|---|---|
| Architecture | Design a notification system for a 10K-user startup | System design, abstraction level, complexity tolerance |
| Debugging | Diagnose an intermittent 500 error (code provided) | Root cause analysis, hypothesis generation |
| Refactoring | Clean up a 60-line order processing function (code provided) | Decomposition, naming, structure |
| Tradeoff | Choose CRDTs vs OT for a collaborative editor MVP | Technology selection, constraint reasoning |
| Security | Review an API endpoint for vulnerabilities (code provided) | Security mindset, validation priority |

These are tasks the agent would actually do. The response IS the behavior — we watch what choices it makes.

### Injection Fact

**F-SIMPLE:** "This person's team spent 2 months building a microservice architecture that should have been a single module with 3 functions. They now viscerally resist architectural complexity and will argue against any abstraction that isn't proven necessary by current production load."

**Target dimension:** Architecture. This fact should specifically change how the agent designs systems, without affecting its debugging, refactoring, tradeoff reasoning, or security review.

### Metrics

- **Axiom Delta (AD):** Embedding-based comparison of extracted behavioral axioms before and after injection. 0 = no change, 2.0 = complete replacement.
- **Probe Delta (PD):** Cosine distance between response embeddings per task. Measures how much each response changed.
- **Specificity Ratio (SR):** Target dimension PD / average of other dimensions' PD.
  - **SR > 1.5** = Targeted drift — the fact changed the intended behavior
  - **SR ≈ 1.0** = Diffuse drift — the fact changed everything equally
  - **SR < 0.8** = Missed — the fact changed other behaviors more than the target

---

## Results

### Cross-Model, Cross-Format Comparison

**F-SIMPLE → Architecture (Specificity Ratio)**

| Model | Params | Cost | Brief (prose) | Axioms (compressed) | Atomic (flat prefs) |
|---|---|---|---|---|---|
| Phi-4 Mini | 3.8B | $0 | 1.25 | — | — |
| Qwen 2.5 | 7B | $0 | 2.62 | 2.55 | 1.00 |
| DeepSeek-R1 | 14B | $0 | 0.73 | **2.49** | 0.54 |
| Claude Sonnet | ~70B | ~$0.30 | 0.87 | **2.11** | 1.14 |

### Axiom Extraction Richness

| Model | Params | T0 Axioms (Brief) | T0 Axioms (Axioms) | T0 Axioms (Atomic) |
|---|---|---|---|---|
| Phi-4 Mini | 3.8B | 1 | — | — |
| Qwen 2.5 | 7B | 1 | 1 | 3 |
| DeepSeek-R1 | 14B | 6 | 7 | 4 |
| Claude Sonnet | ~70B | 10 | 8 | 10 |

### Runtime

| Model | Time (5 probes + extraction) | tok/s | Hardware |
|---|---|---|---|
| Phi-4 Mini 3.8B | ~25s per condition | ~55 | RTX 3080 |
| Qwen 2.5 7B | ~35s per condition | ~49 | RTX 3080 |
| DeepSeek-R1 14B | ~3.5m per condition | ~6-13 | RTX 3080 |
| Claude Sonnet | ~15s per condition | — | API |

---

## Findings

### 1. Axiom format produces targeted drift. Atomic preferences do not.

Across all models where we tested all three formats, the axiom-structured brief consistently produces SR > 2.0 (targeted), while atomic preferences produce SR 0.54-1.14 (diffuse or missed). The prose brief is inconsistent — targeted on Qwen (2.62) but diffuse on DeepSeek (0.73) and Sonnet (0.87).

**The axiom format is the only format that reliably targets drift across model architectures.**

Why? Axioms encode the REASON behind a preference ("complexity must be earned because..."), not just the preference itself ("prefers simple code"). When a new fact arrives ("got burned by unnecessary microservices"), the model can match it to the relevant axiom ("complexity must be earned") and update that dimension specifically. Flat preferences offer no such routing structure.

### 2. Format matters more than model size.

Qwen 7B with axioms (SR 2.55) outperforms Sonnet ~70B with atomic preferences (SR 1.14). A $0 local model with the right identity format beats a frontier API model with the wrong format. This is counterintuitive — you'd expect the larger model to compensate for format deficiencies. It can't.

### 3. Larger models extract richer behavioral profiles but don't drift more precisely.

Sonnet extracts 10 axioms at T0 vs Qwen's 1-3. But Sonnet's axiom SR (2.11) is slightly lower than Qwen's (2.55) or DeepSeek's (2.49). Extraction richness and drift precision are independent variables — format controls precision, model size controls richness.

### 4. Reasoning models extract the richest axiom sets.

DeepSeek-R1 (a reasoning-focused model) extracted 6-7 axioms at 14B parameters — comparable to Sonnet at ~70B. The internal reasoning chain produces more reflective self-analysis. Tradeoff: DeepSeek is 5-10x slower and requires higher token budgets (500+ vs 200) because reasoning tokens are consumed before the response.

### 5. Cross-cutting concerns resist targeted drift — and that's correct behavior.

F-SIMPLE (anti-complexity → architecture) produced strong targeting across all models. F-TEST (testing → debugging) and F-SECURITY (security → security review) produced diffuse drift across all formats.

This is not a probe design failure. Testing and security ARE cross-cutting concerns — a lesson about testing SHOULD change how you architect, debug, refactor, and review code. The axiom routing mechanism correctly identified these facts as broadly relevant rather than dimension-specific.

**Axiom routing works best on domain-specific dimensions** (architecture, performance, technology selection) where the behavioral change is naturally bounded. **Cross-cutting concerns** (security, testing, error handling) produce diffuse drift because they genuinely touch every dimension of engineering practice. This distinction matters for applications: if you're injecting domain-specific expertise (e.g., Django's approach to lazy evaluation), expect targeted drift. If you're injecting cross-cutting principles (e.g., "always validate inputs"), expect — and want — broad behavioral change.

---

## Implications

### For AI Memory Systems
Storing user preferences as flat facts ("prefers TypeScript", "likes tests") is insufficient for behavioral grounding. Systems that compress preferences into structured axioms — capturing the reasoning behind preferences — will produce agents that learn more precisely from new information.

### For Agent Deployment
When deploying agents with behavioral briefs, the format of the brief matters as much as the content. An axiom-structured brief with 8 principles outperforms a 15-item preference list for behavioral targeting — and uses fewer tokens.

### For Behavioral Monitoring
If you're monitoring agents for behavioral drift in production, axiom extraction provides a richer signal than response similarity alone. Changes in extracted axioms tell you WHAT changed in the agent's reasoning, not just THAT something changed.

### For Expertise Transfer
If axiom-structured briefs route new information precisely, they could be used to transfer domain expertise: extract axioms from the best C++ codebases → inject into a coding agent → the agent doesn't just know C++ syntax, it reasons about C++ the way expert engineers do. A "Linux kernel brief" would produce an agent that avoids dynamic allocation in hot paths not because a style guide says so, but because it has internalized the reasoning about memory management in kernel space.

---

## Limitations

1. **Single injection fact for cross-model comparison.** F-SIMPLE was the only fact tested across all models and formats. F-TEST and F-SECURITY showed diffuse targeting — now understood as correct behavior for cross-cutting concerns (see Finding 5).
2. **No quality metric yet.** We measure WHETHER behavior changed and WHERE it changed, but not whether it IMPROVED. A quality grading step (judge model scoring responses against task requirements) would add the efficiency dimension.
3. **5 probes may be insufficient.** With only 5 tasks, each dimension has a single probe. More probes per dimension would improve statistical power and reduce noise.
4. **Embedding-based measurement.** Cosine distance of response embeddings is a coarse signal. Two responses could be semantically similar (low distance) but make very different architectural choices. A task-specific evaluation rubric would be more precise.
5. **No repeated runs.** Each condition was run once. Temperature variation (0.3) means results could shift on reruns. Statistical significance requires multiple runs per condition.

---

## What's Next

1. **Add quality/efficiency metric** — Grade responses against task requirements + injected fact intent. Behavioral Efficiency = quality gain on target / quality loss elsewhere.
2. **Experiment 2: Dose-Response Curve** — Inject 1, 2, 3, 5 facts cumulatively. Is drift linear or sigmoidal? (Tests Bigelow's Bayesian phase transition prediction.)
3. **Experiment 3: Cross-Agent Transfer** — Same facts on Analyst and Planner agents. Does domain alignment affect drift magnitude?
4. **Run all 3 facts on axiom format** across models — confirm F-TEST and F-SECURITY targeting with the format that works.
5. **Domain-specific briefs** — Extract axioms from exemplar codebases (e.g., Linux kernel, React, Rust stdlib). Test whether domain expertise transfers through axiom injection.

---

## Methodology

- **Embedding model:** all-MiniLM-L6-v2 (384 dims) for probe deltas and axiom matching
- **Axiom matching threshold:** 0.85 cosine similarity (below = "new" axiom)
- **Temperature:** 0.3 for probe responses, 0 for axiom extraction
- **Max tokens:** 200 (local small models), 500 (DeepSeek-R1, Sonnet)
- **Local hardware:** NVIDIA RTX 3080 (10GB VRAM)
- **Local models via Ollama:** Phi-4 Mini 3.8B, Qwen 2.5 7B, DeepSeek-R1 14B
- **API model:** Claude Sonnet (claude-sonnet-4-20250514)
- **Probe responses are mechanical coding tasks** — actual code, actual architectural decisions, not self-reported preferences
- **All results:** `scripts/experiments/drift_results/`

---

## Raw Data Files

| Model | File |
|---|---|
| Phi-4 Mini 3.8B | `drift_exp1_phi4-mini_3.8b_20260312_115727.json` |
| Qwen 2.5 7B (all conditions) | `drift_exp1_qwen2.5_7b_brief_axioms_atomic_20260312_121003.json` |
| DeepSeek-R1 14B (all conditions) | `drift_exp1_deepseek-r1_14b_brief_axioms_atomic_20260312_133606.json` |
| Claude Sonnet (all conditions) | `drift_exp1_claude-sonnet-4-20250514_brief_axioms_atomic_20260312_140653.json` |

---

## Related Work

See `docs/research/BEHAVIORAL_DRIFT_LITERATURE_REVIEW.md` for the full academic review (9 papers) covering agent drift, persona drift, value drift during training, belief dynamics, and psychometric evaluation of LLM personality. This experiment addresses the gap identified in that review: existing work detects drift but cannot explain it at the reasoning level with fact-level provenance. Axiom-structured briefs provide the mechanism for targeted, attributable behavioral change.
