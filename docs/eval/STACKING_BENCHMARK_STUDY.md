# Base Layer Stacking Benchmark Study
## Proving the Identity Layer Thesis Across Established Benchmarks

**Status:** DRAFT — Collective review pending
**Author:** the developer (architecture) + Opus (design)
**Date:** 2026-03-06

---

## Core Thesis

Base Layer is not a replacement for any existing system. It is a **layer** that makes every other layer work better. Memory systems retrieve facts. Coding agents write code. Personalization systems match preferences. All of them implicitly model the user. Base Layer makes that model **explicit, compressed, and portable**.

**The claim:** System X + Base Layer brief > System X alone.

**The proof:** Run established benchmarks with and without a Base Layer brief injected. Measure the delta.

---

## Universal Experimental Design

Every benchmark follows the same three-condition pattern:

| Condition | Description | What it tests |
|---|---|---|
| **C1** | System X alone | Their published baseline |
| **C2** | System X + Base Layer brief (~3-8K tokens in system prompt) | Does the identity layer help? |
| **C3** | System X + full persona/preference dump (raw, uncompressed) | Does compression matter, or is more context always better? |

**Interpretation:**
- C2 > C1 → Brief adds value (the identity layer thesis)
- C2 > C3 → Compression beats raw dump (the behavioral compression thesis)
- C2 >= C3 → Compression MATCHES raw at 1/20th the tokens (efficiency thesis)

---

## TIER 1 — Run First (Pre-Launch or Launch Week)

### 1. Twin-2K-500: Digital Twin Prediction
**Category:** Personalization / Behavioral Prediction
**Status:** IN PROGRESS — C1 baseline running

| Detail | Value |
|---|---|
| **Source** | Columbia Business School + Virginia Tech (Marketing Science 2025) |
| **Dataset** | 2,058 participants, 500+ survey questions, 4 waves |
| **License** | CC BY 4.0 |
| **HuggingFace** | `LLM-Digital-Twin/Twin-2K-500` |
| **What it measures** | Can an LLM predict how a specific person answers survey questions? |
| **Their model** | GPT-4.1-mini |
| **Their baselines** | Random 59.17%, Summary 68.02%, Fine-tuned 69.61%, Full dump 71.72%, Human ceiling 81.72% |

**Our design:**
- C1: GPT-4.1-mini, no context (question only)
- C2: GPT-4.1-mini + Base Layer brief
- C3: GPT-4.1-mini + full persona_text (~130K chars)
- Also run C1/C2 on Opus to test model-independence

**Target:** Beat 68.02% summary baseline. Approach or exceed 71.72% full dump.

**Why this matters:** Their summary is a stat sheet (demographics, Big Five scores). Our brief is a behavioral model. If compression-with-structure beats compression-without-structure, that's the thesis in one number.

**Estimated cost:** ~$5-10 for 20 participants across all conditions on GPT-4.1-mini.

---

### 2. BCB-0.1: Behavioral Compression Benchmark (Internal)
**Category:** Brief Quality Validation
**Status:** Code ready, not yet executed

Already designed and specced (D-072). Five metrics that validate the brief itself:
- **CR** (Claim Recall): 99.98% — DONE
- **SRS** (Signal Retention Score): Re-run on Franklin
- **DRS** (Distinguishability Rating Score): Can judges tell briefs apart?
- **CMCS** (Cross-Model Consistency Score): Same brief → 5 models → do they converge?
- **VRI** (Variance Reduction Index): Does the brief reduce response variance?

BCB validates WHAT we're stacking. The other benchmarks validate WHERE stacking helps.

---

## TIER 2 — Run Post-Launch (High Priority)

### 3. LongMemEval: Memory Recall Stacking
**Category:** Long-Term Memory
**Status:** Not started — design ready

| Detail | Value |
|---|---|
| **Source** | ICLR 2025 |
| **Paper** | arxiv.org/abs/2410.10813 |
| **GitHub** | github.com/xiaowu0162/LongMemEval |
| **Dataset** | 500 questions in multi-session chat histories |
| **Scales** | LongMemEval_S (~115K tokens, ~40 sessions), LongMemEval_M (~1.5M tokens) |
| **What it measures** | 5 abilities: Information Extraction, Multi-Session Reasoning, Knowledge Updates, Temporal Reasoning, Abstention |
| **2026 SOTA** | Mastra 95%, EverMemOS 83%, Supermemory 81.6%, TiMem 76.9% |

**Our design:**
- C1: Memory system (Mem0 or open-source baseline) alone
- C2: Memory system + Base Layer brief in system prompt
- C3: Memory system + full persona dump

**Where lift is expected:**
- Multi-Session Reasoning (brief provides interpretive frame to connect dots)
- Knowledge Updates (brief tracks what's CURRENT, pipeline handles supersession)
- Temporal Reasoning (brief compresses timeline into coherent narrative)

**Where lift is NOT expected:**
- Information Extraction (single-session fact retrieval — you either found the chunk or didn't)
- Abstention (structural, not identity-dependent)

**Why this matters:** Every system on the LongMemEval leaderboard is a memory system. None inject an identity layer. If we show +X% on the hard categories by stacking, that proves memory + identity > memory alone. Memory providers become integration partners.

**Estimated cost:** TBD — depends on memory system API costs + LLM inference.

---

### 4. LaMP: Language Model Personalization
**Category:** Personalization (Text Tasks)
**Status:** Not started

| Detail | Value |
|---|---|
| **Source** | ACL 2024 |
| **Paper** | arxiv.org/abs/2304.11406 |
| **GitHub** | github.com/LaMP-Benchmark/LaMP |
| **Dataset** | 7 personalized tasks (3 classification, 4 generation) with user profiles |
| **What it measures** | Can an LLM personalize outputs (headlines, emails, product reviews, etc.) given a user's history? |

**Our design:**
- C1: LLM with no user profile
- C2: LLM + Base Layer brief (generated from their user profile data)
- C3: LLM + their full user profile

**Why this matters:** LaMP is the standard academic personalization benchmark. Showing improvement here gives us a publishable result in the personalization literature.

**Also consider:** LaMP-QA (personalized question answering) and LongLaMP (long-form generation) as extensions.

---

### 5. PersonaLens: Conversational AI Personalization
**Category:** Personalization (Conversational)
**Status:** Not started

| Detail | Value |
|---|---|
| **Source** | arxiv.org/abs/2506.09902 |
| **What it measures** | Personalization quality, response quality, and task success in task-oriented dialogues |
| **Method** | LLM-as-Judge with user agent + judge agent |

**Our design:**
- C1: AI assistant with no personalization context
- C2: AI assistant + Base Layer brief
- C3: AI assistant + full interaction history

**Why this matters:** PersonaLens explicitly measures personalization quality with a judge model. If the brief improves judge scores, that's a direct measure of identity-layer value.

---

## TIER 3 — Run Post-Launch (Strategic)

### 6. SWE-bench: Coding Agent Lift
**Category:** Coding / Agent Performance
**Status:** Not started — hypothesis stage

| Detail | Value |
|---|---|
| **Source** | Princeton (NeurIPS 2024) |
| **GitHub** | github.com/SWE-bench/SWE-bench |
| **Dataset** | 2,294 real GitHub issues + PRs from popular Python repos |
| **Variants** | SWE-bench Verified (500 human-verified), SWE-bench Pro (1,865 cross-repo) |
| **What it measures** | Can an agent resolve real GitHub issues by generating correct diffs? |
| **2026 leaders** | Devin, Claude Code, Codex, various SWE-agents at 40-70% on Verified |

**Our design:**
- C1: Coding agent alone (standard SWE-agent or Claude Code)
- C2: Coding agent + domain brief with coding axioms (architectural preferences, quality heuristics, codebase conventions)
- C3: Coding agent + verbose style guide / full preferences dump

**The brief would contain:**
- Architectural preferences ("prefers composition over inheritance", "flat > nested")
- Quality axioms ("readability over cleverness", "minimize blast radius")
- Codebase-specific conventions (inferred from the repo's patterns)

**Where lift is expected:**
- Complex issues requiring judgment (architectural decisions, refactoring)
- Issues where multiple valid solutions exist (the brief constrains productively)

**Where lift is NOT expected:**
- Simple bug fixes with one obvious solution
- Pure algorithm problems

**Why this matters:** Coding agents are the hottest category in AI. If a brief improves SWE-bench scores even marginally, that's headline-worthy. Also tests the hypothesis that identity compression works for ORGANIZATIONS (codebase identity), not just individuals.

**Estimated cost:** High — each SWE-bench instance requires full agent runs. Start with Verified (500 instances).

---

### 7. tau-bench / tau2-bench: Tool-Agent-User Interaction
**Category:** Agent Reliability
**Status:** Not started

| Detail | Value |
|---|---|
| **Source** | Sierra AI |
| **Paper** | arxiv.org/abs/2406.12045 |
| **GitHub** | github.com/sierra-research/tau2-bench |
| **What it measures** | Agent reliability in multi-turn conversations with tools and policy constraints |
| **Key metric** | Pass^k — success rate that decays exponentially (90% single-try = 57% at k=8) |
| **Domains** | Retail, airline, telecom |

**Our design:**
- C1: Agent with domain policy guidelines only
- C2: Agent + Base Layer brief of a "customer persona" (preferences, communication style, risk tolerance)
- C3: Agent + full customer history dump

**Why this matters:** tau-bench tests whether agents follow policies while handling users. A brief that models the USER should help the agent anticipate needs, interpret ambiguous requests, and personalize within policy bounds. The pass^k metric is brutal — even small reliability improvements compound.

---

### 8. PersonalLLM: Preference Alignment
**Category:** Preference Modeling
**Status:** Not started

| Detail | Value |
|---|---|
| **Source** | ICLR 2025 |
| **What it measures** | Can an LLM adapt to individual user preferences over response quality? |
| **Method** | Diverse simulated users with preference models (reward models) |

**Our design:**
- C1: LLM with no preference context
- C2: LLM + Base Layer brief capturing preference patterns
- C3: LLM + raw preference examples

**Why this matters:** PersonalLLM uses reward models to simulate diverse users. If our brief captures preference structure that reward models recognize, that validates behavioral compression at the preference level.

---

## Benchmark Priority Matrix

| # | Benchmark | Category | Stacking Target | Expected Lift | Cost | Priority |
|---|---|---|---|---|---|---|
| 1 | Twin-2K-500 | Personalization | GPT-4.1-mini | HIGH (behavioral prediction is our core claim) | ~$10 | PRE-LAUNCH |
| 2 | BCB-0.1 | Brief Quality | N/A (internal) | N/A (validates what we stack) | ~$14 | PRE-LAUNCH |
| 3 | LongMemEval | Memory | Mem0/Supermemory | MEDIUM-HIGH (multi-session, knowledge update) | TBD | POST-LAUNCH T1 |
| 4 | LaMP | Personalization | Any LLM | MEDIUM (structured user modeling) | Low | POST-LAUNCH T1 |
| 5 | PersonaLens | Conversational | Any LLM | MEDIUM (judge-scored personalization) | Low | POST-LAUNCH T1 |
| 6 | SWE-bench | Coding | Claude Code/SWE-agent | LOW-MEDIUM (judgment tasks only) | High | POST-LAUNCH T2 |
| 7 | tau-bench | Agent | Any agent | MEDIUM (reliability + personalization) | Medium | POST-LAUNCH T2 |
| 8 | PersonalLLM | Preferences | Any LLM | MEDIUM (preference modeling) | Low | POST-LAUNCH T2 |

---

## What Victory Looks Like

**Minimum viable proof (pre-launch):**
- Twin-2K-500 C2 > 68.02% (beat their summary baseline)
- BCB-0.1 all five metrics at threshold

**Strong proof (launch week):**
- Twin-2K-500 C2 approaching 71.72% (match their full dump at 1/20th tokens)
- LongMemEval multi-session + knowledge-update categories show +5% with brief

**The dream (post-launch):**
- Improvement on 3+ independent benchmarks across different categories
- At least one coding/agent benchmark showing lift
- Publishable result: "An identity layer improves [X benchmark] by Y% when stacked on [Z system]"

---

## Inspectability and Provenance

**Every claim in the brief traces back to source evidence.** This is not a nice-to-have — it's a prerequisite for trust, and it's what separates a behavioral model from a black box.

No existing system on any of these leaderboards offers this. Memory systems retrieve chunks but don't explain WHY a memory matters to who someone is. Personalization systems match preferences but can't show you the evidence chain. Fine-tuned models are completely opaque.

**Base Layer's provenance stack:**
- Every fact in the brief traces to a specific source conversation, document, or text passage
- Vector provenance links brief claims → supporting facts → source material
- Citation provenance (where available) links to exact quotes
- The website already renders this: hover a claim, see the evidence trail with similarity scores

**Why this matters for benchmarks:**
- When we show C2 > C1 on any benchmark, the natural question is "why?" Provenance lets us answer: the brief captured THIS pattern from THESE sources, which led to THIS correct prediction.
- Inspectability turns a benchmark score into a **story**. Not just "we got 72%" but "we got 72% because the brief identified that this person values X based on 4 converging sources, and that's why we predicted Y correctly."
- For enterprise adoption, audit trails are non-negotiable. A brief without provenance is a liability. A brief with provenance is a decision-support tool.

**Provenance should be surfaced in every benchmark report:**
- For Twin-2K: When C2 gets a prediction right that C1 gets wrong, trace WHY — which brief claim drove the correct answer?
- For LongMemEval: When the brief helps multi-session reasoning, show which axioms connected the dots
- For SWE-bench: When coding axioms improve resolution, trace which axiom applied

**This is also a research contribution.** No personalization benchmark currently measures inspectability or provenance quality. We could propose extending benchmarks with a provenance dimension — not just "did you get the right answer" but "can you explain why from evidence?"

---

## Open Questions for Collective Review

1. **Brief adaptation per benchmark:** Should we tailor the brief format for each benchmark (e.g., coding axioms for SWE-bench, preference structure for PersonalLLM), or use the same universal brief format everywhere? Universal is cleaner but adapted may perform better.

2. **Which memory system for LongMemEval:** Mem0 (most popular, YC-backed, $24M), Supermemory (current SOTA claimant), or open-source baseline? Using a well-known system makes the result more credible.

3. **Codebase identity for SWE-bench:** This extends Base Layer from PERSONAL identity to ORGANIZATIONAL identity. Is that scope creep or natural extension? A codebase has beliefs, values, and conventions — that IS identity by our design principle (D-068: "Document identity IS identity").

4. **Cost prioritization:** LongMemEval stacking is the highest strategic value (proves the layer thesis with memory providers). SWE-bench is the highest visibility (coding agents are the hot category). Which gets resources first?

5. **Publication target:** UMAP 2026 (ACM Conference on User Modeling, Adaptation and Personalization, June 2026) accepts papers on exactly this topic. Should we target a submission?

---

## References

- Twin-2K-500: Toubia et al., Marketing Science 2025. HuggingFace: `LLM-Digital-Twin/Twin-2K-500`
- LongMemEval: Wu et al., ICLR 2025. arxiv.org/abs/2410.10813
- LaMP: Salemi et al., ACL 2024. arxiv.org/abs/2304.11406
- PersonaLens: arxiv.org/abs/2506.09902
- PersonalLLM: ICLR 2025. openreview.net/forum?id=2R7498e2Tx
- SWE-bench: Jimenez et al., NeurIPS 2024. swebench.com
- tau-bench: Sierra AI. arxiv.org/abs/2406.12045
- tau2-bench: github.com/sierra-research/tau2-bench
