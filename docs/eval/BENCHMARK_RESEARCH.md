# Benchmark Research: AI Identity Understanding, Personal Memory, and Personalization Evaluation

**Research Date:** 2026-02-25 (Session 43)
**Purpose:** Inform Base Layer benchmark design by cataloging what exists, what it measures, and where the gaps are.

---

## 1. Executive Summary

1. **The claim "no automated benchmarks exist for 'who is this person'" is MOSTLY TRUE but needs refinement.** KnowMe-Bench (January 2026) is the first benchmark that explicitly measures person understanding at a depth approaching identity — but it evaluates from autobiographical narratives, not conversation history, and has no adoption yet.

2. **Memory benchmarks are plentiful but measure the wrong thing for Base Layer.** LoCoMo, LongMemEval, MemoryBench, MemBench, and BEAM all test factual recall and temporal reasoning over conversation logs. None test whether a system builds a coherent model of who someone is.

3. **Personalization benchmarks exist but measure preference adherence, not identity.** PersonaLens (ACL 2025) and PrefEval (ICLR 2025) test whether LLMs follow stated preferences. PersonalLLM (ICLR 2025) tests response tailoring to synthetic taste profiles. None measure understanding of values, communication style, decision patterns, or behavioral tendencies.

4. **Competitor benchmarks are retrieval benchmarks, not identity benchmarks.** Mem0 uses LoCoMo (factual QA over conversations). Supermemory uses LongMemEval. Letta built its own leaderboard testing memory read/write operations. Cognee uses HotPotQA. None measure whether the system knows who you are.

5. **The entire field conflates "memory" with "understanding."** Every existing benchmark asks "can the system retrieve fact X?" — none ask "does the system understand person Y?" This is exactly the gap Base Layer claims to fill, and it is a real gap.

6. **KnowMe-Bench's three-tier framework (factual extraction, subjective state attribution, decision/principle reasoning) is the closest conceptual model to what Base Layer needs.** Its Tier 3 tasks — mnestic trigger analysis, mind-body interaction, psychoanalysis — are the first attempts at benchmarking deeper person understanding.

7. **LLM-as-a-Judge is the dominant automated evaluation methodology** across all recent benchmarks (LoCoMo, PersonaLens, PrefEval, Letta Leaderboard). It achieves 80-90% agreement with human evaluators and is the most viable path for automating Base Layer evaluation.

8. **Benchmark credibility is a live issue.** Zep claimed 84% on LoCoMo; Mem0 reproduced it at 58%; Zep disputed at 75%. LoCoMo itself is criticized as too short (16K-26K tokens) to truly test long-term memory. Benchmark design choices heavily influence results.

9. **Personality detection from text is well-studied but solves a different problem.** Big Five detection from social media text is a mature NLP task with established benchmarks (PANDORA, PAN/CLEF). This identifies personality traits from writing samples — Base Layer needs to measure whether a system can use extracted identity to generate appropriately personalized responses.

10. **Base Layer's existing eval framework (EVAL_FRAMEWORK.md) is actually more advanced than most competitor evaluation approaches** for measuring identity understanding, but it relies entirely on human judgment and does not scale.

---

## 2. Existing Benchmarks

### 2.1 Memory System Benchmarks

#### LoCoMo (2024, ACL)
- **Source:** Snap Research (Maharana et al.)
- **What it measures:** Long-term conversational memory via QA
- **Dataset:** 10 multi-session conversations, ~600 turns, ~16K-26K tokens each
- **Question types:** Single-hop, multi-hop, temporal, commonsense/world knowledge, adversarial
- **Metrics:** F1, BLEU-1, LLM-as-a-Judge score
- **Users:** Mem0 (primary benchmark), Zep, Letta, MemMachine, Backboard
- **Limitations for Base Layer:**
  - Tests factual recall, not person understanding
  - Conversations are synthetic (two people discussing daily events)
  - 16K-26K tokens is small — fits in a single context window for modern LLMs
  - No identity, preference, or behavioral evaluation
  - Benchmark credibility disputed (Zep/Mem0 disagreement over methodology)
- **Link:** https://snap-research.github.io/locomo/

#### LongMemEval (2024, ICLR 2025)
- **Source:** Wu et al.
- **What it measures:** Five long-term memory abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention
- **Dataset:** 500 questions across 115K-1.5M token conversation histories
- **Key finding:** GPT-4o drops from 92% (offline) to 58% (interactive) — context window size does not guarantee recall
- **Users:** Supermemory (primary benchmark)
- **Limitations for Base Layer:**
  - Tests memory retrieval, not identity construction
  - Human-assistant interaction format (closer to real-world than LoCoMo)
  - Does include preference extraction as a category, but shallow (literal stated preferences)
- **Link:** https://github.com/xiaowu0162/LongMemEval

#### MemoryBench (2025, October)
- **Source:** LittleDinoC et al.
- **What it measures:** Memory and continual learning in LLM systems
- **Design:** Inspired by neuroscience; categorizes memory as declarative or procedural
- **Key finding:** Existing systems cannot handle multiple types of declarative and procedural memory simultaneously
- **Limitations for Base Layer:**
  - Tests system-level memory management, not person understanding
  - Focuses on learning from user feedback, not building user models
- **Link:** https://arxiv.org/abs/2510.17281

#### MemBench (2025, ACL Findings)
- **Source:** Ma et al.
- **What it measures:** Memory effectiveness, efficiency, and capacity in LLM agents
- **Design:** Factual memory and reflective memory at different levels; participation and observation scenarios
- **Metrics:** Accuracy, recall, capacity, temporal efficiency
- **Limitations for Base Layer:**
  - Agent-focused (memory for task execution), not user-focused
- **Link:** https://aclanthology.org/2025.findings-acl.989/

#### BEAM (2025, "Beyond a Million Tokens")
- **What it measures:** Long-term memory at 10M-token scale
- **Dataset:** 100 conversations, 2,000 validated questions, up to 10M tokens
- **Added dimensions:** Contradiction resolution, event ordering, instruction following
- **Proposes LIGHT framework:** Episodic memory + working memory + scratchpad (cognition-inspired)
- **Limitations for Base Layer:**
  - Scale testing — does the system work at extreme length?
  - Still factual retrieval, not identity understanding
- **Link:** https://arxiv.org/abs/2510.27246

#### HaluMem (2025)
- **What it measures:** Hallucinations in memory systems across extraction, updating, and QA
- **Dataset:** 15K memory points, 3.5K questions per scale; up to 1M+ token contexts
- **Key finding:** All systems experience sharp accuracy declines at scale; extraction failures cascade into update and QA failures
- **Relevance to Base Layer:**
  - Directly relevant for measuring extraction quality
  - Base Layer's pipeline (extract → score → classify → tier) is exactly the kind of system this benchmarks
  - Could adapt HaluMem methodology to test fact extraction fidelity
- **Link:** https://arxiv.org/abs/2511.03506

### 2.2 Personalization Benchmarks

#### PersonaLens (2025, ACL Findings)
- **Source:** Amazon Science (Zhao, Vania et al.)
- **What it measures:** Personalization in task-oriented AI assistants
- **Design:** User profiles with preferences + interaction histories; LLM user agent generates dialogues; LLM judge evaluates personalization, response quality, task success
- **Key contribution:** First benchmark for task-oriented personalization (vs. chit-chat)
- **Limitations for Base Layer:**
  - Tests preference adherence in tasks (shopping, booking), not identity understanding
  - Synthetic user profiles, not real human identity
  - Still preference-level personalization, not values/communication/behavioral level
- **Link:** https://aclanthology.org/2025.findings-acl.927/

#### PrefEval (2025, ICLR Oral)
- **Source:** Amazon Science
- **What it measures:** Whether LLMs recognize and follow user preferences in conversation
- **Dataset:** 3,000 curated preference-query pairs across 20 topics; explicit and implicit preferences; up to 100K token contexts
- **Key finding:** In zero-shot, preference following falls below 10% accuracy at just 10 turns (~3K tokens). Even with RAG/prompting, performance degrades in long contexts.
- **Relevance to Base Layer:**
  - Validates that raw conversation history is not enough (supports Base Layer's thesis)
  - Methodology — testing implicit vs. explicit preference recognition — is transferable
  - But "preferences" are still surface-level (food preferences, communication preferences), not deep identity
- **Link:** https://prefeval.github.io/

#### PersonalLLM (2025, ICLR)
- **What it measures:** Whether LLMs can be tailored to individual user preference profiles
- **Design:** Prompts with high-quality responses from GPT-4o, Claude 3 Opus, Gemini; 10 reward models with heterogeneous preferences; weighted ensembles create synthetic "users"
- **Key contribution:** Tests personalization algorithms (meta-learning, ICL) that leverage user bases
- **Limitations for Base Layer:**
  - Tests response selection (which response fits this user?), not response generation
  - Synthetic preference profiles, not real identity
  - Persona prompting produces preferences "only half as diverse" as PersonalLLM users
- **Link:** https://arxiv.org/abs/2409.20296

### 2.3 Person Understanding Benchmarks

#### KnowMe-Bench (2026, January)
- **Source:** QuantaAlpha
- **What it measures:** Person understanding for lifelong digital companions
- **Dataset:** 2,580 evaluation queries from 4.7M tokens of autobiographical narratives
- **Three-tier evaluation:**
  - **Tier 1: Factual extraction** — entity recall under spatiotemporal constraints
  - **Tier 2: Subjective state attribution** — adversarial abstention, temporal reasoning, event ordering
  - **Tier 3: Decision and principle reasoning** — mnestic trigger analysis, mind-body interaction, psychoanalysis
- **Seven distinct tasks:**
  - T1: Context-Aware Extraction
  - T2: Adversarial Abstention (resistance to hallucination traps)
  - T3: Temporal Reasoning (duration/timeline reconstruction)
  - T4: Logical Event Ordering
  - T5: Mnestic Trigger Analysis (sensory cues triggering memories)
  - T6: Mind-Body Interaction (explaining contradictory behaviors)
  - T7: Expert-Annotated Psychoanalysis (motivations and identity reasoning)
- **Key finding:** RAG improves factual accuracy but errors persist on temporally grounded explanations and higher-level inferences
- **Relevance to Base Layer:**
  - **THIS IS THE CLOSEST EXISTING BENCHMARK TO WHAT BASE LAYER NEEDS**
  - Tier 3 explicitly tests identity-level understanding (motivations, decision principles, contradictory behaviors)
  - Uses autobiographical narratives, not conversation logs (different input format but similar goal)
  - Requires evidence-grounded reasoning (auditability, discourages speculation)
  - Very new (January 2026) — no adoption yet, methodology unproven at scale
- **Link:** https://arxiv.org/abs/2601.04745

### 2.4 Dialogue Consistency and Persona Benchmarks

#### PersonaGym (2025, EMNLP Findings)
- **What it measures:** Persona consistency in LLM-generated responses
- **Dataset:** 200 personas, 10 questions per task, 10K total questions across 10 LLMs
- **Limitations:** Tests whether an AI can maintain a given persona, not whether it can build one from data

#### RMTBench (2025)
- **What it measures:** Multi-turn role-playing in LLMs
- **Dataset:** 80 characters, 8,000+ dialogue rounds (English + Chinese)
- **Metrics:** Ethical boundaries, persona consistency
- **Limitations:** Tests fictional character role-play, not real person understanding

#### PersonaChat / ConvAI2
- **What it measures:** Persona-grounded dialogue generation
- **Dataset:** 10.9K English dialogues with crowd-sourced persona descriptions
- **Status:** Cornerstone dataset; 9/18 recent personalization papers evaluate on it
- **Limitations:** Persona = 5-sentence description of fictional person. Not real identity.

#### INTIMA (2025)
- **What it measures:** Companionship behaviors in LLMs
- **Dataset:** 368 prompts across 31 behaviors (assistant traits, user vulnerabilities, intimacy, emotional investment)
- **Evaluation:** Responses classified as companionship-reinforcing, boundary-maintaining, or neutral
- **Relevance:** Tests emotional intelligence and boundary-setting, not identity understanding
- **Link:** https://arxiv.org/abs/2508.09998

### 2.5 RAG Evaluation Frameworks

#### RAGAS
- **What it measures:** Retrieval quality and generation faithfulness in RAG pipelines
- **Metrics:** Context precision, context recall, faithfulness, answer relevance
- **Status:** De facto standard for RAG evaluation; used by 60% of production AI applications
- **Limitations for Base Layer:**
  - Tests retrieval-generation pipeline quality, not identity understanding
  - But RAGAS-style metrics (faithfulness, context precision) are transferable to measuring whether a brief's claims are grounded in facts
- **Link:** https://docs.ragas.io/

### 2.6 Personality Detection (NLP)

#### Big Five / OCEAN Detection
- **Mature NLP task:** Predicting personality traits from text (social media posts, essays)
- **Datasets:** PANDORA (Reddit), PAN/CLEF authorship challenges, myPersonality (Facebook)
- **Models:** RoBERTa and BERT fine-tuned on PANDORA; zero-shot LLM prompting
- **2025 state:** Springer comprehensive survey; Nature Machine Intelligence psychometric framework for LLM personality evaluation
- **Relevance to Base Layer:**
  - Not directly applicable — this detects traits IN text, not tests whether a system understands a person
  - But the evaluation methodology (trait prediction accuracy against ground truth) is transferable
  - Could potentially validate extracted facts against known personality dimensions
- **Key paper:** https://www.nature.com/articles/s42256-025-01115-6

### 2.7 Value and Behavioral Alignment

#### Deep Value Benchmark (DVB)
- **What it measures:** Whether models predict based on deep values vs. shallow features
- **Design:** Training phase (values correlate with features) then testing phase (decoupled)
- **Relevance:** Conceptually similar to testing whether Base Layer captures deep identity vs. surface preferences
- **Link:** https://arxiv.org/pdf/2511.02109

---

## 3. Competitor Approaches

### 3.1 Mem0
- **Benchmark used:** LoCoMo (primary); self-published comparative benchmark
- **Claimed result:** 26% relative accuracy improvement over OpenAI's memory (66.9% vs 52.9% LLM-as-Judge)
- **Methodology:** 10 extended LoCoMo conversations; single-hop, multi-hop, temporal, open-domain QA; temperature=0; F1, BLEU-1, LLM-as-Judge scoring
- **Comparative testing:** Tested against OpenAI Memory, LangMem, MemGPT, RAG baselines, full-context
- **What it actually measures:** Factual recall accuracy from conversation logs
- **What it does NOT measure:** Whether the AI knows who the user is, communicates appropriately, predicts behavior, or understands values
- **Credibility issues:** Published their own benchmark paper; disputed Zep's results; methodology criticized for including/excluding adversarial questions selectively

### 3.2 Letta (formerly MemGPT)
- **Benchmark used:** Letta Leaderboard (custom); LoCoMo; Context-Bench
- **Methodology:** Tests core memory reads, archival memory reads, conversation learning; fictional QA dataset; GPT-4.1 as judge following SimpleQA grading
- **Key finding:** Simple filesystem storage scores 74% on LoCoMo, beating specialized memory tools
- **What it actually measures:** Memory management operations (read/write/update efficiency)
- **What it does NOT measure:** User understanding, personalization quality, identity coherence

### 3.3 Supermemory
- **Benchmark used:** LongMemEval (primary); also released open-source "memorybench" framework
- **Methodology:** Session-by-session ingestion; 500 questions across 6 categories; 5 core memory capabilities
- **Results:** Strong on multi-session (71.43%) and temporal reasoning (76.69%)
- **What it actually measures:** Information extraction and temporal reasoning from chat histories
- **What it does NOT measure:** Person understanding, identity construction

### 3.4 Cognee
- **Benchmark used:** HotPotQA subset (24 multi-hop questions); 45 runs per system
- **Methodology:** Exact Match, F1, DeepEval Correctness, Human-like Correctness
- **Results:** 0.93 Human-like Correctness (vs. Mem0, LightRAG, Graphiti)
- **What it actually measures:** Multi-hop reasoning and factual consistency
- **What it does NOT measure:** Anything about users or identity

### 3.5 Zep / Graphiti
- **Benchmark used:** LoCoMo; Deep Memory Retrieval (DMR)
- **Controversy:** Claimed 84% on LoCoMo; Mem0 reproduced at 58%; Zep disputed at 75%
- **What it actually measures:** Memory retrieval accuracy
- **What it does NOT measure:** Person understanding

### 3.6 OpenAI (ChatGPT Memory)
- **No published benchmark.** No academic paper, no public evaluation methodology.
- **Claims:** "More comprehensive" memory as of April 2025; references all past conversations
- **Evaluation:** None visible. User satisfaction implied but not measured publicly.

### Summary: Competitor Benchmark Gap

| Competitor | Benchmark | Measures Recall? | Measures Identity? | Measures Personalization? |
|---|---|---|---|---|
| Mem0 | LoCoMo | Yes | No | No |
| Letta | Letta Leaderboard | Yes | No | No |
| Supermemory | LongMemEval | Yes | No | No |
| Cognee | HotPotQA | Yes | No | No |
| Zep | LoCoMo/DMR | Yes | No | No |
| OpenAI | None published | N/A | N/A | N/A |
| **Base Layer** | **EVAL_FRAMEWORK.md** | **Partial** | **Yes (human-judged)** | **Yes (human-judged)** |

---

## 4. Academic Research: Key Methodologies

### 4.1 LLM-as-a-Judge
- **Status:** Dominant evaluation paradigm across 2024-2025 benchmarks
- **Agreement with humans:** 80-90% on many quality dimensions (comparable to inter-annotator agreement)
- **Variants:** Single-judge, multi-judge panel, personalized judge (role-adapted)
- **Reliability metrics:** Cohen's Kappa, Krippendorff's Alpha for inter-judge agreement
- **Best practices (2025 survey):** Reproducible scoring templates, documented chain-of-thought reasoning, calibration against human baselines
- **Relevance to Base Layer:** Primary path to automating evaluation. The existing human-judge protocol could be partially replaced with LLM-as-Judge for scalability.

### 4.2 Recommendation System Evaluation (Beyond Accuracy)
- **Established metrics:** Precision, Recall, F1, NDCG, MAP
- **Beyond accuracy:** Diversity (intra-list variety), Novelty (unfamiliarity), Serendipity (pleasant surprise), Coverage (catalog utilization), Personalization (inter-list diversity)
- **Key insight:** These metrics measure whether a system serves different content to different users. Base Layer could adapt "inter-list diversity" — do two different users get meaningfully different briefs?
- **Trade-off research:** More diverse recommendations reduce precision; more novel items increase risk. The same tension exists in identity systems: more specific predictions are riskier.

### 4.3 Stylometric Analysis
- **What it is:** Detecting writing style/authorship from text features (lexical, syntactic, grammatical patterns)
- **Datasets:** PAN/CLEF challenges, PANDORA (Reddit)
- **Methods:** N-grams, dependency trees, transformer-based (STAR, RoBERTa)
- **Relevance to Base Layer:** Could be used to evaluate tone match — does AI output match the communication style described in the brief? Stylometric features could quantify "tone match" dimension currently scored subjectively.

### 4.4 Psychometric Frameworks for LLMs
- **Nature Machine Intelligence (2025):** Comprehensive psychometric methodology for personality tests on LLMs
- **Key finding:** Large, instruction-tuned models give reliable personality measurement results; specific personality profiles can be mimicked in downstream tasks
- **Relevance to Base Layer:** Could test whether a brief-augmented LLM exhibits personality traits consistent with the user's extracted profile

---

## 5. Gap Analysis

### What Exists
| Capability | Benchmarks | Maturity |
|---|---|---|
| Factual recall from conversations | LoCoMo, LongMemEval, BEAM | High (multiple papers, adopted by industry) |
| Temporal reasoning over chat history | LoCoMo, LongMemEval, BEAM | High |
| Memory system hallucination detection | HaluMem | Medium (single paper, 2025) |
| Preference adherence | PrefEval, PersonaLens | Medium (2025, ICLR/ACL) |
| Response personalization (synthetic users) | PersonalLLM | Medium (ICLR 2025) |
| Persona consistency (fictional) | PersonaGym, PersonaChat, RMTBench | High (many papers) |
| RAG pipeline quality | RAGAS, multiple tools | Very high (industry standard) |
| Personality trait detection from text | PANDORA, PAN/CLEF | High (mature NLP task) |
| Memory management operations | Letta Leaderboard, MemBench | Medium |

### What Does NOT Exist
| Capability | Status | Impact for Base Layer |
|---|---|---|
| **"Does this system know who I am?"** | No benchmark | CRITICAL — this is the central claim |
| **Behavioral prediction accuracy** | No benchmark | HIGH — Base Layer's PREDICTIONS layer |
| **Communication style matching** | No benchmark (stylometry is adjacent but different) | HIGH — Base Layer's CORE layer |
| **Value/belief understanding** | No benchmark (DVB is conceptual) | HIGH — Base Layer's ANCHORS layer |
| **Identity coherence over time** | No benchmark | MEDIUM — does the model evolve without contradicting |
| **Brief vs. raw history comparison** | Base Layer's EVAL_FRAMEWORK.md only | HIGH — the core competitive claim |
| **Cross-model brief portability** | No benchmark | MEDIUM — does the same brief work across models |
| **Cold-start identity quality** | No benchmark | HIGH — how much data is enough |

### The Core Gap, Precisely Stated

Every existing benchmark tests: **"Given facts about conversations, can the system retrieve the right facts?"**

No existing benchmark tests: **"Given a person's history, does the system understand who they are well enough to behave as if it knows them?"**

KnowMe-Bench (January 2026) is the first attempt to bridge this gap with its Tier 3 tasks (decision reasoning, mnestic triggers, psychoanalysis), but it evaluates comprehension of autobiographical narratives — not whether an AI system can build an identity model and use it to generate personalized responses in live interaction.

The gap is real. The claim holds — with the nuance that KnowMe-Bench is the first step in the right direction.

---

## 6. Recommended Approach: Base Layer Benchmark Design

### 6.1 Design Principles

1. **Measure understanding, not recall.** Every existing benchmark tests retrieval. Base Layer must test whether the compressed identity model enables the AI to behave as if it knows the person.

2. **Test generation quality, not extraction quality.** The pipeline's value is in the end-to-end output (personalized AI responses), not in intermediate artifacts (fact count, embedding quality).

3. **Use the existing A/B/C framework as the foundation.** The EVAL_FRAMEWORK.md protocol is already more advanced than any competitor's evaluation for identity. Automate it, do not replace it.

4. **LLM-as-Judge for scalability; human validation for calibration.** Run LLM judges on every evaluation, but periodically validate against human ratings to ensure the judge is calibrated.

5. **Design for comparison.** The benchmark must produce numbers that can be placed next to Mem0's 26% claim, Supermemory's 76% temporal reasoning, etc. — even though those benchmarks measure different things.

### 6.2 Proposed Benchmark: "Identity Understanding Evaluation" (IUE)

#### Three evaluation tiers (inspired by KnowMe-Bench structure, adapted for Base Layer's use case):

**Tier 1: Factual Grounding (table stakes)**
- Can the system correctly answer biographical questions about the user?
- Questions generated from known facts in the database (ground truth available)
- Automated: LLM generates question from fact → system answers → LLM judges correctness
- Metrics: Accuracy, F1 (similar to LoCoMo single-hop)
- Example: "What is the user's trading strategy?" / "What pet does the user have?"
- Purpose: Proves the pipeline works. Comparable to competitor benchmarks.

**Tier 2: Preference Prediction (differentiation begins)**
- Can the system predict what the user would choose in novel scenarios?
- Present scenarios with multiple options; compare system's prediction to known user preferences
- Semi-automated: Generate scenarios from preference-type facts; LLM-as-Judge scores alignment
- Metrics: Prediction accuracy, confidence calibration
- Example: "The user is choosing between two restaurants: a trendy fusion place and a classic Italian spot. Which would they pick, and why?"
- Purpose: Tests whether the system goes beyond retrieval to inference. Comparable to PrefEval but for identity-derived preferences.

**Tier 3: Identity Understanding (the unique claim)**
- Does the AI behave as if it knows the person across diverse interaction types?
- The existing 10-prompt protocol with A/B/C conditions, scored on the 6 dimensions
- Automated version: LLM-as-Judge rates each response on the 6 dimensions using a calibrated rubric
- Human validation: Periodic human re-rating to check LLM judge calibration
- Metrics: Per-dimension scores (1-5); composite "Identity Understanding Score"; C-B gap
- Sub-dimensions (mapped to layers):
  - **Values/Beliefs** (ANCHORS): Does the response reflect the user's actual convictions?
  - **Communication Style** (CORE): Does the response match how the user communicates? (directness, formality, tone)
  - **Behavioral Prediction** (PREDICTIONS): Does the response anticipate how the user would react?
  - **Novel Composition**: Does the response synthesize identity knowledge into insights not explicitly stated?
  - **"Seen" Factor**: Holistic — does the response feel like talking to someone who knows them?
- Purpose: The irreducible core. No competitor measures this. This IS the benchmark.

#### Evaluation Methodology

**Automated pipeline:**
1. Generate test scenarios from the user's fact database (ensures ground truth)
2. Run each scenario through three conditions: A (baseline/no context), B (raw retrieved history), C (assembled brief)
3. LLM-as-Judge scores each response on relevant dimensions using a standardized rubric
4. Compute per-tier scores and composite Identity Understanding Score (IUS)
5. Compute C-B gap (the key metric: "how much does the brief outperform raw memory?")

**Judge calibration:**
- Use strong model (Opus-class) as judge
- Calibrate against human ratings on a seed set of 50+ rated responses (from existing EVAL_FRAMEWORK.md results)
- Report inter-rater reliability (Cohen's Kappa between LLM judge and human)
- Re-calibrate when brief format changes

**Reproducibility:**
- Temperature=0 for all generation and judging
- Fixed model versions
- Published rubrics and scoring templates
- Seed set of calibration examples published

### 6.3 Comparison Strategy

To make results comparable to competitor claims:

| Competitor Claim | Base Layer Counter | Metric |
|---|---|---|
| Mem0: "26% accuracy improvement over OpenAI Memory" | Base Layer: "X% identity understanding improvement over raw history" | IUS C-B gap |
| Supermemory: "76% temporal reasoning" | Base Layer: "Y% on Tier 1 factual grounding" (+ Tier 3 which they do not have) | Tier 1 accuracy |
| Letta: "74% on LoCoMo with filesystem" | Base Layer: Can optionally run LoCoMo for direct comparison | LoCoMo J score |
| All competitors: Retrieval-only benchmarks | Base Layer: "Z% on behavioral prediction, W% on novel composition" | Tier 3 sub-dimensions |

The pitch: "Competitors measure whether AI can retrieve facts about your conversations. We measure whether AI understands who you are."

### 6.4 Practical Next Steps

1. **Automate the existing A/B/C protocol with LLM-as-Judge** — this is the highest-leverage single action. The 10 prompts and 6 dimensions already exist. Adding LLM-as-Judge makes it runnable on every pipeline change.

2. **Build Tier 1 (Factual Grounding) as a regression test** — auto-generate QA pairs from the fact database. Run after every extraction or scoring change. This is the simplest tier and catches pipeline regressions.

3. **Design the Tier 2 scenario generator** — needs a prompt that generates plausible choice scenarios from preference-type facts. LLM-as-Judge evaluates whether the system's prediction aligns with the known preference.

4. **Calibrate LLM-as-Judge against existing human ratings** — the Session 32 eval data (78 ratings across 3 dimensions) is a starting calibration set. Run the same prompts through an LLM judge and measure agreement.

5. **Run LoCoMo for comparability** (optional but strategic) — if the MCP server can answer LoCoMo questions, publish the score alongside the IUS. This lets people compare on their terms before seeing Base Layer's unique metrics.

6. **Multi-user validation** — the Subject B experiment is the first test of whether the benchmark generalizes beyond one person. If IUS is meaningful, it should differentiate between User A's brief and Subject B's brief when applied to the same prompts.

### 6.5 What NOT to Build

- **Do not try to build a general-purpose "identity understanding" benchmark** for the research community. Build a benchmark that proves Base Layer works. Generalization comes later.
- **Do not replace human evaluation entirely.** The "Seen" factor is irreducibly subjective. LLM-as-Judge approximates it, but the gold standard remains the user's gut reaction.
- **Do not benchmark against LoCoMo as the primary metric.** LoCoMo measures the wrong thing. Use it for comparability, not for validation.
- **Do not build a personality test (Big Five) evaluator.** Personality detection from text is a solved problem that does not map to Base Layer's value proposition. The system does not claim to detect personality traits — it claims to enable AI that knows you.

---

## 7. Sources

### Memory System Benchmarks
- [LoCoMo: Evaluating Very Long-Term Conversational Memory](https://snap-research.github.io/locomo/) — Maharana et al., ACL 2024
- [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://github.com/xiaowu0162/LongMemEval) — Wu et al., ICLR 2025
- [MemoryBench: A Benchmark for Memory and Continual Learning in LLM Systems](https://arxiv.org/abs/2510.17281) — October 2025
- [MemBench: Towards More Comprehensive Evaluation on the Memory of LLM-based Agents](https://aclanthology.org/2025.findings-acl.989/) — ACL 2025 Findings
- [Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs](https://arxiv.org/abs/2510.27246) — 2025
- [HaluMem: Evaluating Hallucinations in Memory Systems of Agents](https://arxiv.org/abs/2511.03506) — 2025

### Personalization Benchmarks
- [PersonaLens: A Benchmark for Personalization Evaluation in Conversational AI Assistants](https://aclanthology.org/2025.findings-acl.927/) — Amazon Science, ACL 2025
- [PrefEval: Do LLMs Recognize Your Preferences?](https://prefeval.github.io/) — Amazon Science, ICLR 2025 Oral
- [PersonalLLM: Tailoring LLMs to Individual Preferences](https://arxiv.org/abs/2409.20296) — ICLR 2025

### Person Understanding
- [KnowMe-Bench: Benchmarking Person Understanding for Lifelong Digital Companions](https://arxiv.org/abs/2601.04745) — January 2026

### Dialogue and Persona
- [PersonaGym: Evaluating Persona Agents and LLMs](https://aclanthology.org/2025.findings-emnlp.368.pdf) — EMNLP 2025
- [INTIMA: A Benchmark for Human-AI Companionship Behavior](https://arxiv.org/abs/2508.09998) — 2025
- [PersonaChat / ConvAI2](https://arxiv.org/abs/1801.07243) — Foundational dataset

### Competitor Evaluation
- [Mem0 Research: 26% Accuracy Boost for LLMs](https://mem0.ai/research) — Mem0
- [Mem0 arXiv paper](https://arxiv.org/abs/2504.19413) — April 2025
- [Mem0 Benchmark Comparison Blog](https://mem0.ai/blog/benchmarked-openai-memory-vs-langmem-vs-memgpt-vs-mem0-for-long-term-memory-here-s-how-they-stacked-up) — Mem0
- [Letta Leaderboard: Benchmarking LLMs on Agentic Memory](https://www.letta.com/blog/letta-leaderboard) — Letta
- [Benchmarking AI Agent Memory: Is a Filesystem All You Need?](https://www.letta.com/blog/benchmarking-ai-agent-memory) — Letta
- [Supermemory Research: State-of-the-Art in Agent Memory](https://supermemory.ai/research) — Supermemory
- [Supermemory memorybench (open-source)](https://github.com/supermemoryai/memorybench) — Supermemory
- [Cognee AI Memory Tools Evaluation](https://www.cognee.ai/blog/deep-dives/ai-memory-tools-evaluation) — Cognee
- [Cognee AI Memory Benchmarking](https://www.cognee.ai/blog/deep-dives/ai-memory-evals-0825) — Cognee
- [Zep LoCoMo Claims Dispute](https://github.com/getzep/zep-papers/issues/5) — GitHub Issue
- [Is Mem0 Really SOTA in Agent Memory?](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/) — Zep

### Evaluation Methodology
- [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217) — Standard RAG evaluation
- [LLMs-as-Judges: A Comprehensive Survey](https://arxiv.org/html/2412.05579v2) — December 2024
- [Deep Value Benchmark](https://arxiv.org/pdf/2511.02109) — 2025

### Personality and Style
- [Machine and Deep Learning for Personality Traits Detection (Comprehensive Survey)](https://link.springer.com/article/10.1007/s10462-025-11245-3) — Springer, 2025
- [A Psychometric Framework for Evaluating and Shaping Personality Traits in LLMs](https://www.nature.com/articles/s42256-025-01115-6) — Nature Machine Intelligence, 2025
- [Stylometry Recognizes Human and LLM-Generated Texts](https://arxiv.org/pdf/2507.00838) — 2025

### Recommendation System Evaluation
- [Beyond-Accuracy: Diversity, Serendipity, and Fairness in Recommender Systems](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2023.1251072/full) — Frontiers, 2023
- [Comprehensive Survey of Evaluation Techniques for Recommendation Systems](https://arxiv.org/html/2312.16015v2) — 2024
