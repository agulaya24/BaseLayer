# Base Layer: Behavioral Compression for Portable AI Identity Models

**Draft Paper — For ArXiv / Workshop Submission**

## Abstract

We present Base Layer, an open-source system that extracts behavioral patterns from text corpora and compresses them into portable identity models for AI personalization. Unlike existing memory systems that store facts or conversation summaries, Base Layer produces structured operating guides that capture *how* a person reasons rather than *what* they reason about. The system uses a 47-predicate behavioral grammar for constrained extraction, a three-layer identity architecture (epistemic axioms, communication modes, behavioral predictions), and domain-agnostic authoring prompts that provably eliminate topic skew. In a prompt ablation study (4 rounds, 10 conditions), a 73-word domain guard reduced topic-specific mentions from 9 to 0 across all conditions while cutting prompt size by 78%. On the Twin-2K benchmark (N=100), compressed identity models achieve 71.83% prediction accuracy at 18:1 compression ratio (p=0.008). We demonstrate that 20% of extracted facts are sufficient for behavioral identification, that format determines behavioral routing (axiom-structured briefs outperform flat preference lists), and that the simplified 4-step pipeline outperforms the original 14-step design. The system has been validated on 44 subjects across historical figures, public writers, and private individuals.

## 1. Introduction

As AI systems transition from generic assistants to personalized agents, the question of *how* an AI understands its user becomes load-bearing infrastructure. Current approaches fall into two categories: platform memory (ChatGPT Memory, Claude Memory) which stores preferences and facts opaquely, and RAG-based systems (Mem0, Zep, Letta) which retrieve relevant context from conversation history. Neither produces a compressed behavioral model — a portable representation of how someone reasons, communicates, and makes decisions that any AI system can consume.

We introduce *behavioral compression*: the extraction of universal behavioral patterns from domain-specific text, compressed into a model-agnostic operating guide. The key insight is that identity is how someone reasons, not what they reason about. A person who writes 1,000 posts about AI policy is not defined by AI policy — they are defined by how they evaluate claims, construct arguments, navigate tensions, and update beliefs. The identity model captures the invariant; the topics are instances.

## 2. System Architecture

### 2.1 Pipeline

Base Layer operates as a 5-step pipeline:

1. **Import**: Multi-source text ingestion (conversations, blog posts, essays, documents)
2. **Extract**: Constrained fact extraction using 47 behavioral predicates via Haiku API
3. **Embed**: Vector embeddings for provenance tracing (MiniLM-L6-v2)
4. **Author**: Three-layer identity generation via Sonnet API with H3 domain-agnostic prompts
5. **Compose**: Unified narrative brief via Opus API

### 2.2 Behavioral Grammar

We define 47 constrained predicates organized into five categories:
- **Cognitive**: believes, values, fears, prioritizes, identifies_as (12 predicates)
- **Behavioral**: practices, avoids, builds, monitors, struggles_with (10 predicates)
- **Relational**: collaborates, mentors, trusts, relates_to (8 predicates)
- **Contextual**: works_at, lives_in, experienced (9 predicates)
- **Experiential**: struggled_with, excels_at, enjoys (8 predicates)

Each extracted fact is a structured triple: {subject, predicate, object}. The constrained vocabulary eliminates 57% of extraction artifacts (generic "The user is..." statements) and enables statistical analysis across subjects.

### 2.3 Three-Layer Identity Architecture

- **ANCHORS**: Epistemic axioms — beliefs reasoned FROM, not about. Always-on cognitive architecture. 8-10 per subject.
- **CORE**: Communication operating guide — context-specific engagement shifts, mode detection, narrative orientation. Activation-triggered.
- **PREDICTIONS**: Behavioral predictions — situation→response patterns with detection signals, directives, and false-positive warnings. Situation-triggered.

### 2.4 Domain-Agnostic Guard (H3)

The authoring prompt includes a 73-word domain guard:

> "You are writing a UNIVERSAL operating guide — not a summary of interests or positions. Every item must apply ACROSS this person's life, not within one topic. Test: if removing a specific subject (markets, policy, technology, medicine) makes the item meaningless, it does not belong. How someone reasons IS identity. What they reason ABOUT is not."

## 3. Experiments

### 3.1 Prompt Ablation (N=10 conditions, 2 subjects)

| Condition | Prompt size | Topic mentions | Quality |
|-----------|------------|----------------|---------|
| A: Control | 983w | 9 | Timed out |
| B: Stripped | 260w | 9 | Equivalent |
| C: Stripped + Guard | 333w | 0 | Equivalent |
| H: Combined + Capped | 222w | 0 | Best conciseness |

Finding: The domain guard is the only load-bearing change. 78% of prompt content is ceremonial.

### 3.2 Twin-2K Benchmark (N=100)

Using the Twin-2K-500 dataset (Toubia et al.), compressed identity models achieve 71.83% accuracy at 18:1 compression ratio (p=0.008). 20% of facts are sufficient for identification.

### 3.3 Pipeline Ablation (N=14 conditions)

The simplified 4-step pipeline scores 87/100 vs the full 14-step pipeline at 83/100. Ten intermediate steps (scoring, classification, tiering, contradiction detection, etc.) are ceremonial.

### 3.4 Behavioral Drift (N=4 models × 3 formats)

Axiom-structured briefs achieve targeted behavioral drift (Specificity Ratio > 2.0). Flat preference lists produce diffuse or missed drift (SR < 1.2). Format determines behavioral routing.

### 3.5 Sycophancy Resistance

Following Jain et al. (ICLR 2025), we frame identity models as operating guides (adviser role) rather than user profiles (persona role). The "operating guide" framing preserves AI independence; false-positive warnings on predictions prevent over-application of behavioral knowledge.

## 4. Local Model Evaluation

Extended overnight testing on RTX 3080 10GB:

| Model | Facts/Conv | Time/Conv | Assessment |
|-------|-----------|-----------|-----------|
| qwen3:14b | 14.8 | 41.4s | Quality leader |
| gemma3:12b | 10.8 | 6.3s | Sweet spot |
| mistral:7b (behavioral predicates) | 8.5 | 3.5s | Fast, restricted vocab |
| llama3.1:8b | 0.7 | 4.0s | Non-functional |

Finding: Predicate set matters per model. mistral:7b improves from 3.0 to 8.5 facts/conv when restricted to behavioral predicates only.

## 5. Cross-Disciplinary Connections

The system architecture is independently validated by:
- **MDL Theory** (Moskovitz et al., 2024): Compression pressure produces dual-process cognition, predicting the anchors-always-on / modes-triggered structure.
- **Information Bottleneck** (Tishby): The brief is the IB-optimal representation — maximum predictive signal at minimum representation cost.
- **Canalizing Kernel** (CAESAR, 2024): Anchors function as master regulators — changes cascade through the model. Core changes are local.
- **PersonaFuse** (2025): MoE-style selective trait activation validates the serving layer architecture.
- **CAUSM** (Jain et al., ICLR 2025): User profiles increase sycophancy. Operating guide framing is the correct countermeasure.

## 6. Limitations

- Single-builder system — quality gates and daemon agent address bus factor
- Corpus quality bounds model quality — professional-only corpora produce professional-only models
- No real-time updating — batch pipeline, not streaming
- Provenance depends on embedding quality — Citations API returns 0 for highly abstracted content
- Evaluation primarily on English-language text

## 7. Conclusion

Behavioral compression is a distinct discipline from fact storage, memory management, or personality classification. The identity model captures universal reasoning patterns that hold across domains and time, producing a portable operating guide that any AI system can consume. The 73-word domain guard that eliminates topic skew — "How someone reasons IS identity. What they reason ABOUT is not" — encapsulates the entire thesis.

## References

[To be completed — key citations: Toubia et al. Twin-2K, Jain et al. CAUSM, Moskovitz et al. MDL, Tishby IB, PersonaFuse, PersonaX, PersonaMem, CAESAR canalizing kernel]

---

**Code**: https://github.com/agulaya24/BaseLayer
**Live Demo**: https://base-layer.ai/examples/franklin
**Research**: https://base-layer.ai/research
