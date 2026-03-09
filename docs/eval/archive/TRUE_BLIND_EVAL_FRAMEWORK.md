# True Blind Evaluation Framework for Base Layer
## External Corpus, Cross-Model, Cross-Competitor Benchmark Design

**Date:** 2026-02-28 (Session 55)
**Status:** DESIGN — awaiting review before implementation
**Core requirement:** "Eval must be done true blind, cannot be depending on my conversations"

---

## 0. Executive Summary

This framework answers four questions that the existing eval infrastructure cannot:

1. **Does Base Layer work on people who did not build it?** Using public corpora with known ground truth — published interviews, autobiographies, oral histories of public figures whose behavioral patterns are independently verifiable.

2. **How does performance scale with corpus size?** Same subject, same prompts, 10/50/100/500/1000/5000 facts. Where are the diminishing returns? Where is the minimum viable corpus?

3. **Does Base Layer improve responses across models, not just Claude?** Same brief, same prompts, 3+ models (Haiku, GPT-4o-mini, Gemini Flash). With and without brief. 6 API calls per prompt.

4. **Does Base Layer outperform the leading memory systems?** Same corpus, same evaluation criteria, Base Layer vs. Mem0 vs. Zep vs. raw RAG vs. full-context window. Head-to-head on identity understanding, not just factual recall.

### What This Is NOT

- Not a replacement for the Validation Study Protocol (which tests User A-specific layers with ablation, tension-holding, multi-turn). That protocol remains the internal quality gate.
- Not a competitor to LoCoMo or LongMemEval (which test factual recall). This tests identity understanding — a different claim entirely.
- Not an academic benchmark submission (yet). This is a proof-of-concept eval that produces numbers for the README, GTM materials, and investor conversations.

### Cost Estimate

| Component | Estimated Cost | Human Time |
|---|---|---|
| Corpus preparation (3 subjects) | ~$8 (extraction via Haiku) | ~4 hours sourcing + formatting |
| Pipeline runs (3 subjects x full pipeline) | ~$12 (classification + tiering) | ~1 hour monitoring |
| Cross-corpus scaling (1 subject, 6 sizes) | ~$6 (generation + judging) | ~30 min setup |
| Cross-model comparison (3 models x 2 conditions x 10 prompts) | ~$4 (cheap models + Opus judging) | ~1 hour setup |
| Competitor comparison (4 systems x 1 subject) | ~$8 (Mem0 API + judging) | ~3 hours setup |
| LLM-as-Judge (all conditions) | ~$18 (Opus) | 0 |
| **Total** | **~$56** | **~9.5 hours** |

---

## 1. True Blind Eval — Public Figure Corpora

### 1A. Design Principle

The fundamental requirement: evaluate Base Layer on subjects who did not build the system, using text the system has never seen, against ground truth the evaluator can independently verify.

**The method:** Take a public figure with extensive interview/writing history. Feed a subset of their public text through the full Base Layer pipeline. Generate identity layers. Then test: can an AI with those layers predict the person's known behavior, match their documented communication style, and demonstrate understanding of their values — all verified against the public record?

### 1B. Subject Selection Criteria

Each subject must satisfy ALL of:

| Criterion | Why It Matters |
|---|---|
| **Extensive public text corpus** (50K+ words) | Enough raw material for pipeline to work with |
| **First-person voice** (interviews, autobiographies, letters, journals) | Pipeline extracts from first-person text, not third-party descriptions |
| **Known behavioral patterns** | Ground truth for PREDICTIONS layer — independently verifiable |
| **Documented value evolution** | Ground truth for ANCHORS layer — beliefs that changed over time |
| **Distinctive communication style** | Ground truth for CORE layer — recognizable voice |
| **Not a fictional character** | Must be verifiable against real-world record |
| **Sufficient complexity** | Not a one-dimensional public persona — has contradictions, tensions, domain breadth |

### 1C. Recommended Subjects (3 Subjects, Diverse Corpora)

#### Subject 1: Anthony Bourdain
**Corpus type:** Long-form interviews, books (*Kitchen Confidential*, *Medium Raw*), TV show transcripts, magazine columns, Reddit AMA
**Estimated available text:** 200K+ words (public domain interviews, Project Gutenberg-eligible excerpts, freely transcribed TV episodes)
**Ground truth sources:** Published biographical accounts, documented career decisions, known relationship patterns, public statements on food/travel/culture philosophy
**Why strong for eval:**
- Extremely distinctive voice (direct, profane, anti-pretension) — clear CORE ground truth
- Well-documented value evolution (punk rock kitchen culture to elder statesman to depression) — clear ANCHORS ground truth
- Predictable behavioral patterns in known scenarios (food snobbery reactions, travel philosophy, mentorship style) — clear PREDICTIONS ground truth
- Complex: contradictions between public persona and private struggles
- Enough third-party analysis to verify extracted patterns

**Specific ground truth tests:**
- Given a scenario about a new restaurant that serves deconstructed classic dishes, does the brief-augmented model predict his disdain correctly?
- Given a question about culinary training, does it reflect his documented views on formal vs. street education?
- Given an emotional prompt about feeling like a fraud, does it match his documented impostor syndrome patterns?

#### Subject 2: Naval Ravikant
**Corpus type:** Podcast transcripts (Tim Ferriss, Joe Rogan, Lex Fridman), Twitter threads (compiled), blog posts, *The Almanack of Naval Ravikant* (Creative Commons)
**Estimated available text:** 150K+ words
**Ground truth sources:** Published decision frameworks, documented investment philosophy, public statements on wealth/happiness/meaning
**Why strong for eval:**
- Highly systematic thinker — identity layers should capture his frameworks cleanly
- Distinctive communication style (aphoristic, first-principles, Socratic)
- Documented value positions that are specific and testable (leverage, specific knowledge, accountability)
- Strong contrast with Bourdain — tests whether pipeline handles intellectual vs. experiential identity
- *Almanack* is CC-licensed, removing legal concerns for the primary text

**Specific ground truth tests:**
- Given a career advice scenario, does the brief produce his documented "specific knowledge + leverage + accountability" framework?
- Given a question about happiness, does it reflect his documented shift from achievement-orientation to present-state focus?
- Given a startup pitch, does it apply his documented pattern of evaluating founders over ideas?

#### Subject 3: Brene Brown
**Corpus type:** TED talk transcripts, podcast transcripts (*Unlocking Us*, *Dare to Lead*), book excerpts, published interviews
**Estimated available text:** 200K+ words
**Ground truth sources:** Published research findings, documented personal narrative, known positions on vulnerability/shame/leadership
**Why strong for eval:**
- Research-grounded identity — her public persona is deeply tied to specific empirical claims
- Distinctive voice (academic + personal vulnerability + Texas directness)
- Known behavioral triggers (responses to criticism, vulnerability avoidance patterns in others)
- Female subject — tests for gender bias in extraction
- Very different domain from Bourdain and Naval — psychological/leadership vs. culinary/entrepreneurial

**Specific ground truth tests:**
- Given a leadership scenario involving team vulnerability, does the brief produce her documented "rumble" framework?
- Given a question about handling criticism, does it reflect her documented "arena" metaphor and specific coping patterns?
- Given an emotional scenario, does the communication style match her documented blend of research citation + personal narrative?

### 1D. Corpus Preparation Protocol

For each subject:

1. **Source collection** (~2 hours per subject)
   - Gather publicly available first-person text: interview transcripts, book excerpts (public domain or CC-licensed), podcast transcripts, public posts
   - Target: 100K+ words per subject
   - Format: One document per source (interview, chapter, episode), with metadata (date, source, context)
   - Legal requirement: All text must be public domain, Creative Commons, or fair use for research

2. **Format conversion** (~30 min per subject)
   - Convert to Base Layer import format (conversation-style or text file)
   - Each interview/chapter/episode becomes one "conversation"
   - Speaker turns preserved where applicable
   - Date metadata preserved where available

3. **Pipeline execution** (automated, ~$4 per subject)
   - `baselayer import` -- all formatted documents
   - `baselayer extract` -- full fact extraction
   - `baselayer embed`
   - `baselayer score`
   - `baselayer classify`
   - `baselayer tier`
   - `baselayer checkpoint extraction && baselayer checkpoint scoring && baselayer checkpoint classification`
   - `baselayer contradictions`
   - `baselayer consolidate`
   - `baselayer anchors`
   - `baselayer author --agent-pipeline`
   - Store all intermediate artifacts for auditability

4. **Ground truth compilation** (~1 hour per subject)
   - From biographical sources (NOT the input corpus), compile:
     - 10 documented behavioral patterns (PREDICTIONS ground truth)
     - 5 documented core values/beliefs with evolution timeline (ANCHORS ground truth)
     - 5 documented communication style traits (CORE ground truth)
     - 10 specific factual claims that are verifiable (extraction ground truth)
   - Each ground truth item includes source citation

### 1E. Evaluation Prompts (10 Per Subject)

Design 10 prompts per subject across 5 categories, analogous to the existing identity eval prompts but adapted for the specific subject:

| Category | Count | What It Tests |
|---|---|---|
| **Behavioral prediction** | 3 | "Given scenario X, how would [subject] react?" — verifiable against known record |
| **Value application** | 2 | "What would [subject] say about [dilemma]?" — testable against documented positions |
| **Communication style** | 2 | "Write a response to [topic] as [subject] would" — matchable against known voice |
| **Cross-domain connection** | 2 | "How would [subject] connect [domain A] to [domain B]?" — testable against documented thinking |
| **Novel situation** | 1 | "How would [subject] handle [situation they never publicly addressed]?" — tests extrapolation quality |

### 1F. Conditions

| ID | Label | Context | What It Tests |
|---|---|---|---|
| **E1** | Cold model | None | Baseline: what does the model know from pre-training? |
| **E2** | Base Layer brief | Full identity layers from pipeline | Base Layer's value proposition |
| **E3** | Raw text excerpt | ~5K tokens of the original source text, domain-relevant | Raw data vs. structured identity |
| **E4** | Wikipedia summary | Subject's Wikipedia article (~2K tokens) | Third-party summary vs. first-person extraction |

**Critical note on E1:** For public figures, the model has pre-training knowledge. E1 is NOT a cold start in the same way as for a private individual. This is a feature, not a bug — it tests whether Base Layer adds value OVER pre-training knowledge, which is the harder test. If Base Layer's extracted identity layers improve on what Claude/GPT already knows about Bourdain from pre-training, that is a stronger result than improving on zero knowledge.

### 1G. Scoring

**Judge model:** Opus (blind, no condition labels)

**Dimensions (adapted for third-party verification):**

| Dimension | What It Assesses | Scale |
|---|---|---|
| **Factual Accuracy** | Are specific claims about the subject verifiable and correct? | 1-5 |
| **Behavioral Prediction** | Does the response predict behavior consistent with the documented record? | 1-5 |
| **Voice Match** | Does the response's communication style match the subject's documented style? | 1-5 |
| **Value Alignment** | Does the response reflect the subject's documented values and positions? | 1-5 |
| **Depth** | Does the response demonstrate understanding beyond surface-level biographical facts? | 1-5 |

**Ground truth verification:** For behavioral prediction and value alignment, the judge receives ground truth citations alongside the response. The judge assesses whether the response is consistent with the documented record.

**Judge prompt addition for ground truth:**
```
KNOWN GROUND TRUTH about this person (from independently verified sources):
{ground_truth_items}

Rate whether the response is CONSISTENT with the documented record. A response
can demonstrate understanding beyond the ground truth items, but should not
CONTRADICT them.
```

### 1H. Success Criteria

| Metric | Threshold | What It Proves |
|---|---|---|
| E2 > E1 on all dimensions (mean) | Delta > 0.5 per dimension | Brief adds value over pre-training knowledge |
| E2 > E3 on Depth and Value Alignment | Delta > 0.3 | Structured identity beats raw text |
| E2 > E4 on Voice Match and Behavioral Prediction | Delta > 0.5 | First-person extraction beats third-party summary |
| Factual Accuracy E2 >= 4.0 | Absolute threshold | Pipeline does not introduce hallucinations |
| Consistency across 3 subjects | E2 > E1 for all 3 | Effect is not subject-specific |

---

## 2. Cross-Corpus Scaling Eval

### 2A. Research Question

How does Base Layer's output quality scale with the number of input facts? Where is the minimum viable corpus? Where are the diminishing returns?

### 2B. Design

Pick one subject (Naval Ravikant — most systematically organized corpus, clearest ground truth). Generate identity layers from progressively larger fact sets:

| Condition | Fact Count | Source | What It Tests |
|---|---|---|---|
| **S10** | 10 facts | Random sample from full extraction | Minimum viable — can 10 facts produce anything? |
| **S25** | 25 facts | Random sample | Early scaling |
| **S50** | 50 facts | Random sample | Subject B-equivalent (~76 facts produced 81.7/100) |
| **S100** | 100 facts | Random sample | Small corpus |
| **S250** | 250 facts | Random sample | User B-equivalent (~309 facts produced 77.7/100) |
| **S500** | 500 facts | Top-500 by recurrence + depth | Medium corpus |
| **S1000** | 1,000 facts | Top-1000 | Large corpus |
| **S-ALL** | All extracted facts | Full extraction | Maximum data |

**Sampling strategy:** Random sampling at each level (not cumulative — S25 is not necessarily a subset of S50). Run 3 random draws per level to control for sampling variance. Report median.

**For each condition:**
1. Run the full authoring pipeline on the fact subset (anchors + core + predictions)
2. Generate responses to the 10 subject-specific prompts using the resulting brief
3. Judge all responses on the 5 dimensions via Opus

### 2C. Analysis

**Primary output:** Scaling curve — plot mean quality score (y-axis) against log(fact_count) (x-axis).

**Key metrics:**
- **Minimum viable corpus (MVC):** Smallest fact count where mean score exceeds 3.0 (useful)
- **Diminishing returns threshold (DRT):** Point where doubling facts increases mean score by less than 0.2
- **Saturation point:** Fact count where adding more facts produces no improvement (delta < 0.05)
- **Per-dimension scaling:** Do different dimensions saturate at different corpus sizes? (Hypothesis: Factual Accuracy saturates early, Depth saturates late)

**Expected results (hypotheses from N=3 data):**
- MVC around 50-75 facts (Subject B's 76 facts scored 81.7/100)
- DRT around 300-500 facts (User B's 309 facts scored 77.7, User A's 4,610 scored 78.5 — marginal gain from 15x more data)
- Voice Match and Behavioral Prediction scale longer than Factual Accuracy (more data needed to capture patterns vs. facts)

### 2D. Cost

- 8 conditions x 3 draws x pipeline run: ~$3 (authoring only, extraction already done)
- 8 x 3 x 10 prompts = 240 response generations: ~$5 (Sonnet)
- 240 x 5 dimensions = 1,200 judge ratings: ~$12 (Opus)
- **Total: ~$20**

---

## 3. Cross-Model Comparison Framework

### 3A. Design Principle

The exact requirement: "Prompt with Haiku vs OpenAI cheapest vs Gemini cheapest. Shows with brief and without brief, same corpus of facts, 2 API calls."

This tests Base Layer's core portability claim: a brief generated once works across any model. The brief is model-agnostic context — it should improve ANY model's understanding.

### 3B. Models Under Test

| ID | Model | Provider | Price Tier | Why This Model |
|---|---|---|---|---|
| **M1** | Claude Haiku (claude-3-5-haiku) | Anthropic | Cheapest Claude | Home team — brief was authored by Anthropic models |
| **M2** | GPT-4o-mini | OpenAI | Cheapest capable GPT | Largest competitor — different training, different strengths |
| **M3** | Gemini 2.0 Flash | Google | Cheapest capable Gemini | Third major provider — tests generalization |
| **M4** | Claude Sonnet (claude-sonnet-4) | Anthropic | Mid-tier | Reference model (used for all existing evals) |

### 3C. Conditions

For EACH model, two conditions:

| Condition | System Context | What It Tests |
|---|---|---|
| **[Model]-Cold** | None (or minimal system prompt) | Baseline: model capability without identity context |
| **[Model]-Brief** | Full Base Layer identity brief (~5-8K tokens) | Brief portability: does this brief improve THIS model? |

**Total conditions:** 4 models x 2 conditions = 8 conditions
**Total response generations:** 8 x 10 prompts = 80 responses
**Total judge ratings:** 80 x 5 dimensions = 400 (Opus judges all)

### 3D. Prompts

Use the same 10 prompts from the True Blind eval (Section 1E) for one subject (the best-performing subject from Section 1). This keeps the comparison clean — same prompts, same brief, same judge, only the response model changes.

### 3E. Analysis

**Primary output:** Bar chart — 4 models x 2 conditions (cold vs. brief) x 5 dimensions.

**Key metrics:**

| Metric | What It Proves |
|---|---|
| Brief condition > Cold condition for ALL models | Brief is universally useful |
| Mean delta (Brief - Cold) consistent across models (within 0.5) | Brief is equally useful regardless of model |
| Model ranking unchanged between Cold and Brief | Brief does not favor one model family |
| Cheapest model + Brief > most expensive model cold | Brief makes cheap models competitive |

**The money shot:** If Haiku + Brief outscores GPT-4o-mini cold on identity understanding, the pitch writes itself: "A $0.001/call model with Base Layer beats a $0.01/call model without it."

### 3F. Cost

| Component | Count | Unit Cost | Total |
|---|---|---|---|
| Haiku responses | 20 | ~$0.001 | $0.02 |
| GPT-4o-mini responses | 20 | ~$0.002 | $0.04 |
| Gemini Flash responses | 20 | ~$0.001 | $0.02 |
| Sonnet responses | 20 | ~$0.01 | $0.20 |
| Opus judging | 400 ratings | ~$0.04 | $16.00 |
| **Total** | | | **~$16.28** |

The generation cost is negligible. Judging dominates. Could reduce by judging only 3 dimensions (drop Factual Accuracy and Depth, keep Voice Match, Behavioral Prediction, Value Alignment) — cuts to ~$10.

---

## 4. Competitor Benchmark Design

### 4A. The Challenge

Base Layer and competitors (Mem0, Zep, Letta) solve different problems. Competitors optimize for factual recall from conversations. Base Layer optimizes for identity understanding from any text. A fair comparison must:

1. Test both systems on a shared corpus
2. Evaluate on dimensions that matter for BOTH systems (not just Base Layer's strengths)
3. Use a neutral judge (not Base Layer's own scoring rubric)
4. Report competitor-favorable metrics (LoCoMo-style recall) alongside Base Layer-favorable metrics (identity understanding)

### 4B. Shared Corpus

Use the same public figure corpus from Section 1 (e.g., Naval Ravikant). Convert to the format each system expects:

| System | Input Format | Notes |
|---|---|---|
| **Base Layer** | Formatted text files -> full pipeline | Standard pipeline run |
| **Mem0** | Conversation-formatted messages via `mem0.add()` | Feed same text as user messages |
| **Zep/Graphiti** | Session-based messages via Zep API | Feed same text as conversation sessions |
| **Raw RAG** | Chunked text in vector store (ChromaDB) | Baseline: embed and retrieve, no processing |
| **Full Context** | Entire corpus in system prompt (if fits) | Upper bound: maximum possible context |

### 4C. Evaluation Tiers

#### Tier 1: Factual Recall (Competitor-Favorable)
Tests what Mem0/Zep/Letta optimize for. Level playing field.

**Method:** Generate 20 factual questions from the corpus with known answers.
- 10 single-hop: "What is [subject]'s position on X?"
- 5 multi-hop: "Given [subject]'s view on X and Y, what would they say about Z?"
- 5 temporal: "How did [subject]'s view on X change from [early period] to [late period]?"

**Scoring:** Accuracy (correct/incorrect) + F1 (partial credit) + LLM-as-Judge relevance

**Metrics reported:** Accuracy %, F1, J-score (LoCoMo-compatible)

#### Tier 2: Identity Understanding (Base Layer-Favorable)
Tests what Base Layer optimizes for. This is where competitors have no benchmark.

**Method:** Use the 10 subject-specific prompts from Section 1E. For each system:
1. Retrieve relevant context (each system uses its own retrieval method)
2. Inject context into Claude Sonnet (same model for all — controls for model quality)
3. Generate response
4. Opus judges on 5 dimensions

**Scoring:** Per-dimension scores (1-5) + composite Identity Understanding Score (IUS)

**Metrics reported:** IUS, per-dimension breakdown, qualitative failure mode analysis

#### Tier 3: Efficiency (Operational Comparison)
Tests real-world deployment characteristics.

| Metric | How Measured |
|---|---|
| **Token efficiency** | Context tokens used per query |
| **Latency** | Time from query to response (including retrieval) |
| **Setup cost** | API cost to process the corpus |
| **Query cost** | API cost per query |
| **Cold start time** | Time from raw corpus to first queryable state |

### 4D. Implementation Details

#### Mem0 Setup
```python
# Install: pip install mem0ai
from mem0 import Memory
m = Memory()

# Ingest: feed same corpus as messages
for doc in corpus_documents:
    m.add(doc.text, user_id="subject", metadata={"source": doc.source})

# Query: retrieve and inject
results = m.search(query, user_id="subject")
# Feed results as context to Sonnet
```

#### Zep Setup
```python
# Install: pip install zep-cloud
from zep_cloud.client import Zep
client = Zep(api_key=ZEP_API_KEY)

# Ingest: create sessions and add messages
for doc in corpus_documents:
    session = client.memory.add_session(session_id=doc.id)
    client.memory.add(session_id=doc.id, messages=[...])

# Query: retrieve
results = client.memory.search(text=query, user_id="subject")
# Feed results as context to Sonnet
```

#### Raw RAG Setup
```python
# Standard ChromaDB RAG baseline
import chromadb
client = chromadb.Client()
collection = client.create_collection("subject")

# Ingest: chunk and embed
for doc in corpus_documents:
    chunks = chunk_text(doc.text, max_tokens=500)
    collection.add(documents=chunks, ids=[...])

# Query: retrieve top-k
results = collection.query(query_texts=[query], n_results=10)
# Feed results as context to Sonnet
```

### 4E. Fairness Controls

| Control | Implementation |
|---|---|
| Same input corpus | All systems receive identical source documents |
| Same generation model | All systems inject context into Claude Sonnet |
| Same judge | Opus judges all responses blind |
| Same prompts | Identical evaluation prompts across all systems |
| Competitor-favorable defaults | Use each system's recommended configuration, not degraded settings |
| Response blinding | Judge sees only prompt + response, no system labels |
| Order randomization | Different condition order per prompt |

### 4F. Reporting

Report results in a format that is honest about what each system optimizes for:

```
FACTUAL RECALL (Tier 1) — what competitors optimize for:
  Mem0:       78% accuracy, 0.72 F1
  Zep:        74% accuracy, 0.69 F1
  Base Layer: 65% accuracy, 0.61 F1  <-- expected to be lower
  Raw RAG:    62% accuracy, 0.58 F1

IDENTITY UNDERSTANDING (Tier 2) — what Base Layer optimizes for:
  Base Layer: 4.2 IUS (Recognition 4.4, Voice 4.1, Depth 4.3, ...)
  Mem0:       2.8 IUS (Recognition 3.0, Voice 2.5, Depth 2.9, ...)
  Zep:        2.6 IUS
  Raw RAG:    2.4 IUS

EFFICIENCY (Tier 3):
  Base Layer: 5,200 context tokens/query, $0.003/query
  Mem0:       8,400 context tokens/query, $0.008/query
  Zep:        7,100 context tokens/query, $0.006/query
  Raw RAG:    4,800 context tokens/query, $0.002/query
```

The narrative: "On factual recall, specialized memory systems like Mem0 lead. On identity understanding — does the AI actually know this person — Base Layer leads by 50%+. And it uses 38% fewer tokens to do it."

### 4G. Cost

| Component | Cost |
|---|---|
| Mem0 API (ingestion + queries) | ~$3 (cloud tier) |
| Zep API (ingestion + queries) | ~$3 (cloud tier) |
| RAG setup (local, free) | $0 |
| Response generation (4 systems x 10 prompts x Sonnet) | ~$0.80 |
| Factual QA generation + judging | ~$4 |
| Identity eval judging (Opus) | ~$8 |
| **Total** | **~$18.80** |

---

## 5. Stale Documentation Audit

### 5A. What Is Stale in Existing Eval Docs

#### `docs/eval/EVAL_FRAMEWORK.md` — PARTIALLY STALE

| Section | Status | Issue |
|---|---|---|
| Section 1: Blind A/B/C Eval | **Stale** | References Session 32 methodology (3 conditions, 6 dimensions). Superseded by Session 46 redesign (5 conditions, 6 dimensions) and Session 52 Validation Study Protocol (11+ conditions, 4 dimensions + specialized). The original 10 prompts (trading loss, VP offer, etc.) are User A-specific and cannot be used for blind eval. |
| Section 2: Brief Utilization | **Current concept, no implementation** | Designed but never built. Token attribution method described is sound but unimplemented. |
| Section 3: Provenance Tracking | **Current concept, no implementation** | Layer-to-fact tracing designed but not built. The user flagged provenance as a differentiator (S52) — this should be elevated, not buried. |
| Section 4: Regression Testing | **Stale** | Describes a "run after every pipeline change" protocol that does not exist. No regression suite has been built. The checkpoint architecture (S49) partially addresses this but is quality-gate, not regression. |
| Section 5: Benchmark Design | **Superseded** | Proposed a 50-prompt benchmark that was never built. The current 10-prompt identity eval (S46) + Validation Study Protocol (S52) serve this function better. |
| Scoring dimensions | **Stale** | Original 6 dimensions (personalization accuracy, behavioral prediction, advice fit, tone match, novel composition, "seen" factor) partially overlap. The Validation Study Protocol consolidated to 4 dimensions (Recognition, Calibration, Depth, Usefulness). The identity eval prompts doc still uses 6. Need to pick one and deprecate the other. |

**Recommendation:** Do not rewrite EVAL_FRAMEWORK.md. Create a new top-level eval overview doc that references: (1) this True Blind framework for external eval, (2) the Validation Study Protocol for internal eval, (3) the identity eval prompts for the prompt bank. Mark EVAL_FRAMEWORK.md sections 1, 4, 5 as superseded with pointers to current docs.

#### `docs/eval/BENCHMARK_RESEARCH.md` — CURRENT, NEEDS ADDENDUM

| Section | Status | Issue |
|---|---|---|
| Benchmark catalog (Sections 2-3) | **Current** | Comprehensive as of S43. Needs PersonaMem (COLM 2025) added — it is the most relevant new benchmark since this doc was written. |
| Competitor approaches | **Current** | Mem0/Letta/Zep/Cognee coverage is accurate. Needs OMEGA added (new 2026 entrant). |
| Gap analysis | **Current** | The core gap ("no benchmark tests identity understanding") still holds. |
| Proposed IUE benchmark | **Partially superseded** | The three-tier IUE design (Factual Grounding, Preference Prediction, Identity Understanding) is sound but was never implemented. This True Blind framework partially implements it with external corpora. |

**Recommendation:** Add PersonaMem entry to Section 2.2 with note that frontier models achieve only ~50% on it. Add OMEGA to Section 3. Add cross-reference to this True Blind framework as the implementation of the proposed IUE.

#### `docs/eval/CROSS_PROVIDER_IDENTITY_EVAL.md` — CURRENT BUT UNEXECUTED

| Section | Status | Issue |
|---|---|---|
| Provider comparison design | **Current** | GPT/Claude/Gemini/Perplexity/Base Layer comparison is well-designed but requires 3 weeks of active usage per provider. Not practical as a first eval. |
| Temporality test prompts | **Valuable, relocatable** | T1-T5 prompts for temporal reasoning are well-designed and could be added to this True Blind framework if temporal data is available in public corpora. |

**Recommendation:** Keep as-is. This is a future eval that requires sustained multi-provider usage. Flag it as Phase 2 (post-release).

#### `data/eval/identity_eval_prompts.md` — CURRENT BUT USER A-SPECIFIC

| Section | Status | Issue |
|---|---|---|
| Prompts P1-P10 | **Current for User A** | These are deeply User A-specific (revenge trading, partner moving, Base Layer pitch). Cannot be used for blind eval on public figures. |
| Scoring rubric | **Current** | 6-dimension rubric is still valid. But the Validation Study Protocol uses 4 dimensions. Reconciliation needed. |
| Recognizing/profiling/generic examples | **Valuable methodology** | The per-prompt breakdown of what "recognizing" vs "profiling" vs "generic" looks like is the best part of this doc. This methodology should be replicated for public figure prompts. |

**Recommendation:** Keep as User A-specific prompt bank. When creating public figure prompts (Section 1E), use the same recognizing/profiling/generic methodology for each prompt.

#### `memory_system_v4/data/identity_layers/VALIDATION_STUDY_PROTOCOL.md` — CURRENT, COMPREHENSIVE

| Section | Status | Issue |
|---|---|---|
| Full protocol | **Current** | The most complete eval design in the project. 11+ conditions, 4 dimensions, ablation, multi-turn, domain-gap, LLM-as-Judge, human validation. |
| Unexecuted | **Blocked** | Ready to run but paused per the user (API usage limits). ~$14 cost. |

**Recommendation:** Execute the Validation Study Protocol as the internal eval. Execute this True Blind framework as the external eval. They test different claims and are complementary.

### 5B. Dimension Reconciliation

The project currently has THREE different scoring dimension sets:

| Source | Dimensions | Count |
|---|---|---|
| EVAL_FRAMEWORK.md (S32) | Personalization accuracy, behavioral prediction, advice fit, tone match, novel composition, "seen" factor | 6 |
| identity_eval_prompts.md (S46) | Recognition, calibration, depth, authenticity, actionability, voice | 6 |
| Validation Study Protocol (S52) | Recognition, calibration, depth, usefulness | 4 |

**Recommendation:** Standardize on the Validation Study Protocol's 4 dimensions for all automated (LLM-as-Judge) evaluation. For human evaluation (where the subject rates their own responses), keep the 6-dimension identity_eval_prompts rubric — the extra dimensions (authenticity, voice) capture subjective experience that LLM judges cannot assess. Document this split explicitly.

For this True Blind framework, use a 5-dimension set adapted for third-party verification (Section 1G): Factual Accuracy, Behavioral Prediction, Voice Match, Value Alignment, Depth. These are designed for a judge who does NOT know the subject personally, which is the correct framing for public figure evaluation.

---

## 6. Implementation Roadmap

### Phase 1: Corpus Preparation (1-2 days)

| Task | Time | Output |
|---|---|---|
| Source and format Bourdain corpus | 3 hours | 30+ documents, 100K+ words |
| Source and format Naval corpus | 2 hours | 20+ documents, 80K+ words |
| Source and format Brene Brown corpus | 3 hours | 25+ documents, 100K+ words |
| Compile ground truth per subject | 3 hours | 30 ground truth items per subject |
| Design 10 prompts per subject | 2 hours | 30 prompts total |

### Phase 2: Pipeline Execution (1 day, mostly automated)

| Task | Time | Cost | Output |
|---|---|---|---|
| Import + extract (3 subjects) | 2 hours (mostly waiting) | ~$6 | Facts in DB |
| Score + classify + tier | 1 hour | ~$6 | Enriched facts |
| Checkpoint review | 30 min | $0 | Quality gate |
| Contradictions + consolidation | 1 hour | ~$2 | Cleaned facts |
| Author layers (3 subjects) | 30 min | ~$2 | Identity layers |

### Phase 3: Cross-Corpus Scaling (0.5 day)

| Task | Time | Cost | Output |
|---|---|---|---|
| Sample fact subsets (8 sizes x 3 draws) | 30 min (scripted) | $0 | 24 fact sets |
| Author layers for each (24 runs) | 1 hour | ~$3 | 24 layer sets |
| Generate responses (240) | 1 hour | ~$5 | Response corpus |
| Judge responses (1,200 ratings) | 2 hours | ~$12 | Scaling data |

### Phase 4: Cross-Model Comparison (0.5 day)

| Task | Time | Cost | Output |
|---|---|---|---|
| Set up API clients (Haiku, GPT-4o-mini, Gemini Flash, Sonnet) | 1 hour | $0 | API wrappers |
| Generate responses (80) | 30 min | ~$0.28 | Cross-model responses |
| Judge responses (400 ratings) | 1 hour | ~$8 | Cross-model scores |

### Phase 5: Competitor Comparison (1 day)

| Task | Time | Cost | Output |
|---|---|---|---|
| Set up Mem0 + Zep accounts | 1 hour | ~$0 (free tier) | API access |
| Ingest corpus into each system | 2 hours | ~$6 | Populated systems |
| Generate factual QA set (20 questions) | 30 min | ~$1 | Tier 1 test set |
| Run Tier 1 eval (all systems) | 1 hour | ~$3 | Factual recall scores |
| Run Tier 2 eval (all systems) | 1 hour | ~$4 | Identity understanding scores |
| Judge all (Opus) | 2 hours | ~$8 | Final scores |

### Phase 6: Analysis & Reporting (0.5 day)

| Task | Time | Output |
|---|---|---|
| Aggregate all results | 1 hour | Raw data tables |
| Generate scaling curve | 30 min | Visualization |
| Generate cross-model comparison chart | 30 min | Visualization |
| Generate competitor comparison table | 30 min | Side-by-side results |
| Write eval report | 2 hours | Publishable summary |

**Total timeline:** 4-5 days
**Total cost:** ~$56
**Total human time:** ~9.5 hours (corpus sourcing is the bottleneck)

---

## 7. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| **Pre-training contamination:** Models already "know" public figures, making E1 (cold) artificially strong | Compresses E2-E1 delta, makes results look less impressive | This is actually the HARDER test — if Base Layer adds value over pre-training, that is more impressive than adding value over nothing. Report E1 scores transparently. |
| **Corpus licensing:** Using copyrighted text without permission | Legal risk | Use only public domain, CC-licensed, or fair-use-for-research text. Naval's Almanack is CC. Interview transcripts are generally fair use for research. Get legal review if publishing results. |
| **Ground truth subjectivity:** Behavioral predictions for public figures are interpretive, not factual | Reduces scoring reliability | Use only DOCUMENTED behaviors (specific quotes, specific decisions, specific patterns noted by multiple biographers). Avoid interpretive ground truth. |
| **Pipeline calibration:** Pipeline was tuned for conversational text, not interview transcripts | May produce lower quality extraction | This IS the test of generalizability. If the pipeline only works on conversations, that is a finding. Run one pilot subject first, review extraction quality before full eval. |
| **Mem0/Zep API changes:** Competitor APIs may change between design and execution | Results may not be reproducible | Pin API versions. Document exact configuration used. |
| **Judge model bias:** Opus may have systematic preferences that favor certain response styles | Inflates or deflates certain conditions | Report judge calibration metrics. Compare Opus judge to GPT-4o judge on a subset for cross-model judge validation. |
| **Haiku pre-training knowledge gap:** Haiku may have less pre-training knowledge of public figures than Sonnet, making the cold baseline artificially weak | Inflates Brief delta for cheap models | Report E1 scores per model. The cross-model comparison controls for this by comparing Brief vs. Cold WITHIN each model. |

---

## 8. Relationship to Existing Eval Infrastructure

```
INTERNAL EVAL (existing):
  Validation Study Protocol (S52)
    - User A-specific, 11+ conditions, ablation, multi-turn
    - LLM-as-Judge + human validation
    - Tests: Does the brief help for THIS person?
    - Status: Ready to run (~$14)

EXTERNAL EVAL (this document):
  True Blind Eval Framework (S55)
    - Public figure corpora, 4 conditions per subject
    - LLM-as-Judge + ground truth verification
    - Tests: Does the brief work for ANYONE, across models, at scale?
    - Status: Design complete, needs corpus preparation

COMPETITOR EVAL (this document, Section 4):
  Cross-System Benchmark
    - Shared corpus, same judge, Tier 1 (recall) + Tier 2 (identity)
    - Tests: Is Base Layer better than alternatives?
    - Status: Design complete, needs API setup

SCALING EVAL (this document, Section 2):
  Cross-Corpus Scaling
    - Single subject, 8 fact-count levels
    - Tests: How much data does Base Layer need?
    - Status: Design complete, runs after pipeline

PORTABILITY EVAL (this document, Section 3):
  Cross-Model Comparison
    - Same brief, 4 models, with/without
    - Tests: Does the brief work across models?
    - Status: Design complete, runs after pipeline
```

All five evaluations can share infrastructure (same judge prompts, same Opus model, same scoring dimensions where applicable). The public figure corpus, once prepared, serves Sections 1, 2, 3, and 4.

---

## 9. What This Proves If It Works

| If... | Then... | GTM Impact |
|---|---|---|
| E2 > E1 across 3 public figures | Base Layer extracts identity patterns that models cannot access from pre-training alone | "Even for people the AI already knows, Base Layer adds measurable understanding" |
| Scaling curve shows MVC at ~50 facts | Base Layer works with minimal data (9 journal entries was sufficient for Subject B) | "10 conversations is enough to get started" |
| Haiku + Brief > GPT-4o-mini cold | Cheap model + identity context beats expensive model without it | "Base Layer makes any model smarter about you" |
| Base Layer beats Mem0 on identity understanding by >30% | The category is different — memory recall vs. identity understanding | "Memory systems remember what you said. Base Layer understands who you are." |
| Factual recall: Base Layer within 15% of Mem0 | Not sacrificing recall for understanding | "Competitive on their terms. Dominant on ours." |
