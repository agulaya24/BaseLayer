# D-079 Diagnostic: The Provenance Enforcement Gap

**Generated:** 2026-03-10 | **Session:** S84 | **Status:** Collective Review
**Audience:** This document is designed to be handed to any AI system for independent analysis and recommendation.

---

## 1. The Problem, Precisely Stated

Base Layer is a pipeline that compresses conversation history into a behavioral brief — a ~5,000-10,000 character document that tells an AI who someone is. The pipeline has four steps:

```
EXTRACT (Haiku) → AUTHOR layers (Sonnet) → COMPOSE brief (Opus) → SERVE
```

**The problem:** The compose step produces claims that cannot be traced to any source material. Despite explicit prompt instructions saying "DERIVE ONLY FROM INPUT," the composing model (Opus) injects content from its pre-training knowledge when it recognizes who the subject is.

This is not a minor leakage issue. In a full contamination scan across 11 subjects:
- **Franklin:** 18 ungrounded claims (thirteen virtues numbering, Silence Dogood pseudonym, Pennsylvania fireplaces, rising at five, French/Spanish/Latin study)
- **Buffett:** 9 ungrounded (concert hall metaphor, depreciation/GAAP specifics, shareholders as owner-partners)
- **Marks:** 9 ungrounded (tulips to technology stocks, moral hazard terminology, 1950-1970 era references)
- **Roosevelt:** 8 ungrounded (walking night beats with patrolmen, society matrons, fabricated role examples)
- **Aarik:** 7 ungrounded + 1 *inverted* claim (brief said "exits positions on rule violations" — source says she *violates* rules under pressure)
- **Bavani:** 7 ungrounded (biographical details pulled from fact database, not layers)
- **Patent/Douglass/Wollstonecraft:** 1-5 ungrounded each
- **Base Layer project:** 0 ungrounded (no pre-training exposure)
- **Paul Graham:** 0 ungrounded (despite massive pre-training exposure)

**The critical observation:** Two subjects with zero contamination. One (Base Layer) has no pre-training data. The other (Paul Graham) has extensive pre-training data but the prompt constraint worked. This means the constraint is *sometimes* effective — it's not reliably effective. The failure mode is probabilistic, not deterministic, which makes it harder to engineer against.

**The most dangerous case:** Aarik's inverted claim. The model didn't just add information — it reversed a behavioral pattern. A brief that says someone exits positions on rule violations, when they actually violate rules under pressure, will cause an AI to give exactly wrong advice in exactly the moments it matters most.

---

## 2. Why This Is Not a "Tighter Gate" Problem

The instinctive engineering response is: make the faithfulness gate stricter. Check every sentence against source material. Reject anything that doesn't match. But this misunderstands the problem at several levels.

### 2.1 The Current Gate Is Structurally Inadequate

The existing `verify_brief_faithfulness()` function checks:
- ALL-CAPS pattern names (e.g., ANALYSIS-PARALYSIS) exist in source layers
- Technical terms (E46, M3) aren't cross-contaminated
- Proper nouns not in source are flagged

It does NOT check:
- Whether behavioral claims are grounded in source facts
- Whether synthesized patterns actually follow from the evidence
- Whether narrative connections between sentences are justified
- Whether specific details (dates, numbers, pseudonyms) appear in source material

A sentence like "He rises at five and plans each hour's activity" passes every current gate — it contains no ALL-CAPS patterns, no technical terms, no proper nouns. It's a behavioral claim that sounds plausible. It happens to be from Franklin's autobiography, which Opus has memorized, but it was NOT in the source layers for this pipeline run.

### 2.2 Semantic Similarity Is Not Provenance

The existing NLI entailment system (DeBERTa) checks: "Given these facts as premises, is the claim entailed?" But entailment ≠ derivation. A claim can be semantically consistent with source facts without being derived from them. "He rises at five" is consistent with "He values discipline and structured time management" — but the specific detail was hallucinated.

Worse: NLI checks individual fact-claim pairs and aggregates via max. It cannot assess whether facts *collectively* entail a synthesized claim. A brief that says "pattern of X across domains" may score high on entailment because each domain-specific fact partially matches, even though the cross-domain synthesis was the model's own inference (possibly correct, possibly wrong).

### 2.3 The Reward Signal Problem

Even if we could build a perfect faithfulness gate, we face a fundamental reward engineering problem:

**Too strict:** Reject any claim not verbatim in source material → the brief becomes a reshuffled concatenation of source sentences. No synthesis, no insight, no compression. The brief's value comes precisely from its ability to synthesize patterns across facts — "he tests everything empirically" is more useful than 15 individual facts about specific experiments. But that synthesis is where hallucination enters.

**Too loose:** Accept any claim semantically consistent with source material → pre-training knowledge floods in. "He rises at five" is consistent with "he values time management." "She writes about women's rights" is consistent with literally any claim about Wollstonecraft.

**The fundamental tension:** Behavioral compression requires synthesis. Synthesis requires going beyond what any individual fact states. Going beyond individual facts opens the door to pre-training knowledge injection. There is no bright line between "legitimate synthesis from input" and "plausible fabrication from pre-training."

### 2.4 The Identity Inference Problem

The anonymization layer replaces subject names with "this person" before models see data. But Opus infers identity from contextual signatures:
- Printing press + Philadelphia + civic institutions → Franklin
- Shareholder letters + circle of competence + Omaha → Buffett
- Tenement reform + police commissioner + Rough Riders → Roosevelt

Once the model recognizes the subject, its pre-training knowledge about that person becomes available — and indistinguishable (to the model) from its understanding of the input data. The model isn't deliberately hallucinating. It's pattern-matching against its entire knowledge of this person, which includes both the input data AND everything it learned during training.

This is why Paul Graham was clean: his pre-training data is largely essays about startups and programming. The pipeline extracted behavioral patterns from those same essays. The overlap between "what the pipeline extracted" and "what Opus knows about Paul Graham" is nearly total — there's little room for the model to add something it knows but that isn't in the input.

For Franklin, the pipeline extracted from the autobiography. But Opus knows far more about Franklin than what's in the autobiography. The delta between "what the pipeline extracted" and "what Opus knows" is large — and that delta is where contamination enters.

---

## 3. Defining the Fundamental Behavior

Before proposing solutions, we need to define what we actually want the compose step to do. This is harder than it appears.

### 3.1 What Composition Should Be

The compose step takes three authored layers (ANCHORS: core axioms, CORE: contextual behaviors, PREDICTIONS: behavioral predictions) and synthesizes them into a unified narrative. Each layer already has provenance — claims cite specific facts via `provenance: [F-xxx]` lines.

Desired behavior:
1. **Preserve all content from source layers** — nothing should be dropped
2. **Synthesize across layers** — show how axioms, contexts, and predictions interact
3. **Generate readable prose** — not a concatenation but a portrait
4. **Add nothing** — no new facts, no new behavioral claims, no biographical details not in sources

### 3.2 What Composition Actually Does

In practice, composition does all of the above plus:
5. **Fills gaps with plausible detail** — if the source says "he values time management," Opus may add "rising at five" because it's a concrete illustration
6. **Adds biographical color** — pseudonyms, institutions, specific practices
7. **Invents bridging claims** — to connect axioms smoothly, Opus generates transitional behavioral claims that sound right but aren't sourced
8. **Applies pre-training personality models** — for famous subjects, Opus has a rich model of who this person is, and it blends that model with the input

Behaviors 5-8 are not bugs in the traditional sense. They're the model doing what language models do: generating the most probable continuation given the context. The context includes both the prompt (which says "derive only from input") and the model's weights (which encode everything it knows about this person). When the prompt says "write about someone who prints newspapers in Philadelphia and organizes civic institutions," the model's strongest prior is Franklin, and Franklin-associated details flow naturally into the output.

### 3.3 The Human Parallel

This problem mirrors a real cognitive bias. Ask a biographer to write a summary of someone they know well, based only on a specific set of notes. They will inevitably include details they "know" from other sources, because their knowledge of the subject is integrated — they can't cleanly separate "what's in these notes" from "what I know." The stronger their prior knowledge, the more contamination.

This isn't always bad. Sometimes the biographer's broader knowledge makes the summary more accurate. But it makes the summary *unverifiable* against the specified source material — and verifiability is the property we need.

---

## 4. Potential Approaches

### 4.1 Provenance-Preserving Composition

**Concept:** Require the compose model to cite source layer claims for every sentence in the brief. Format: each paragraph includes inline citations like `[A3, C2, P1]` referencing specific anchors, core items, and predictions.

**Post-composition verification:** Parse citations from the brief. For each cited claim, check that it exists in the source layer. For each brief sentence, check that its content is supported by its cited claims (via NLI or semantic similarity).

**Advantages:**
- Creates explicit trace from brief → layer → fact
- Enables automated auditing
- Citations constrain the model's generation (it must justify each claim)

**Disadvantages:**
- Citations may be fabricated (model cites [A3] but the content doesn't match A3)
- Adds structural complexity to the brief that must be stripped before serving
- May degrade prose quality (writing with citations is different from writing prose)
- Doesn't prevent the model from *also* including uncited claims

**Feasibility:** Medium. Requires compose prompt rewrite + post-processing parser + verification loop. Could be implemented as a two-pass system: first pass generates with citations, second pass strips citations for the served brief while storing the mapping.

### 4.2 Claim-Level Faithfulness Gate (Semantic Verification)

**Concept:** After composition, decompose the brief into individual claims. For each claim, compute semantic similarity against all source layer sentences. Flag any claim below a threshold as potentially ungrounded.

**Implementation:** Use sentence embeddings (e.g., all-MiniLM-L6-v2) to embed each brief sentence and each source layer sentence. For each brief sentence, find the max cosine similarity to any source sentence. Threshold at, say, 0.65 — below that, the claim is flagged.

**Advantages:**
- Fully post-hoc — doesn't change the compose step
- Cheap (local model, no API cost)
- Can flag specific sentences for human review

**Disadvantages:**
- Semantic similarity ≠ derivation (see 2.2 above)
- Synthesized claims that combine multiple source sentences may score low even when legitimate
- Threshold tuning is fragile — too high rejects valid synthesis, too low misses hallucinations
- Doesn't prevent contamination, only detects it after the fact
- The inverted-claim problem: "exits positions on violations" is semantically similar to source material about rule violations — similarity doesn't catch directional inversion

**Feasibility:** High. Could be implemented in a few hours. But the false positive/negative rate may make it more noise than signal.

### 4.3 Two-Pass Composition (Generate Then Verify)

**Concept:**
- Pass 1: Opus generates the brief normally
- Pass 2: A different model (or the same model with a different prompt) reads the brief AND the source layers, and for each sentence outputs: GROUNDED (with citation) or UNGROUNDED (with explanation)
- Pass 3: Strip or rewrite ungrounded sentences

**Advantages:**
- Leverages model capability for semantic understanding (better than embedding similarity)
- The verifier model has a simpler task than the generator (classification vs. generation)
- Can catch subtle issues like directional inversion

**Disadvantages:**
- The verifier model has the same pre-training knowledge problem — it may "verify" a hallucinated claim because it knows it's true about Franklin, even if it's not in the source layers
- Doubles (or triples) API cost
- If the verifier is the same model (Opus), it may share the same blind spots
- If the verifier is a different model, it may have different capabilities and miss things Opus caught

**Feasibility:** Medium-high. This is essentially what the Contamination Gate already does for template phrases, extended to semantic claims. The challenge is making the verifier reliably distinguish "in the source layers" from "true about this person."

### 4.4 Local Model Composition (LiquidAI / Small LLM)

**Concept:** Replace Opus with a smaller, less knowledgeable model for the compose step. A model that hasn't memorized Franklin's autobiography can't hallucinate details from it.

**Candidates:**
- **LiquidAI** (LFMs): Efficient, task-specific models. Could be fine-tuned on the compose task.
- **Qwen 2.5 (local):** Already used for benchmarking. 7B-72B parameter range.
- **Llama 3 / Mistral:** Open-weight models with less biographical memorization than Opus.
- **Phi-3 / Gemma 2:** Smaller models that may lack detailed biographical knowledge.

**Advantages:**
- Fundamentally addresses the pre-training knowledge problem — less knowledge = less contamination
- Zero API cost (local inference)
- Full control over model behavior
- Could be fine-tuned specifically for faithful composition

**Disadvantages:**
- Smaller models produce worse prose quality
- D-030 established that Qwen fails at narrative generation — this was tested 12 times
- Models may lack the reasoning capability to synthesize across three complex layers
- "Less knowledge" doesn't mean "no knowledge" — even 7B models know about Franklin
- Fine-tuning requires training data (which pairs of source layers → good briefs do we have?)
- Maintenance burden of running local inference infrastructure

**Feasibility:** Low-medium for current quality bar. The D-030 finding (Qwen fails at narrative generation) is directly relevant. However, newer models (Qwen 2.5, Llama 3.1) may have improved. Worth testing but risky as primary approach.

**Hybrid variant:** Use Opus for composition but a local model for verification (4.3). The local model doesn't need to write well — it just needs to classify "is this sentence supported by the source text?" This is a much simpler task that smaller models handle well.

### 4.5 Constrained Decoding / Structured Generation

**Concept:** Instead of free-form prose generation, constrain the model's output to only reference tokens/phrases that appear in the source material. This is how some summarization systems prevent hallucination — the model can only copy or minimally rephrase source text.

**Techniques:**
- **Extractive-then-abstractive:** First extract key sentences from layers, then rephrase into prose
- **Copy mechanism:** Model can only generate tokens that appear in input (with minimal connecting language)
- **Constrained beam search:** At each generation step, bias toward tokens that appear in source

**Advantages:**
- Architecturally prevents hallucination — can't generate what isn't in the input
- No post-hoc verification needed

**Disadvantages:**
- Severely limits synthesis capability — the brief's value comes from abstraction, not extraction
- Not available through standard API (requires model-level control)
- Would produce stilted, unnatural prose
- Prevents legitimate synthesis (cross-domain patterns, tension identification)

**Feasibility:** Low. Incompatible with API-based composition. Would require local model with custom decoding. And the synthesis constraint defeats the purpose of the compose step.

### 4.6 Source-Layer-Only Context (Remove Fact Database Access)

**Concept:** Currently, the compose step receives both the three authored layers AND the top 100 facts from the database. Remove the raw facts — compose only from the three layers.

**Rationale:** The authored layers already have provenance. If compose only sees layers (not raw facts), and layers are provenance-traced, then the compose step's input is fully provenance-grounded. Any claim in the brief must come from a layer, which must come from a fact.

**Advantages:**
- Reduces the surface area for contamination (layers are curated; raw facts are noisy)
- Layers are already synthesized — compose is doing synthesis-of-synthesis
- Simpler input = more constrained output

**Disadvantages:**
- Doesn't solve the pre-training injection problem at all — Opus infers identity from layers too
- May reduce brief quality if layers have gaps that facts would fill
- Doesn't address the Bavani case (her ungrounded claims came from the fact database)

**Feasibility:** High (trivial code change). But insufficient as sole solution.

### 4.7 Provenance Chain Architecture (The Full Solution)

**Concept:** Enforce provenance at every pipeline boundary, not just within layers.

**Architecture:**

```
FACTS [F-xxx]
  ↓ (extraction provenance: source conversation, chunk, timestamp)
LAYERS [A1, C2, P3] with provenance: [F-xxx, F-yyy]
  ↓ (authoring provenance: Citations API or self-citation)
BRIEF [B-001, B-002, ...] with provenance: [A1, C2] → [F-xxx, F-yyy]
  ↓ (composition provenance: explicit citation + post-hoc verification)
SERVED BRIEF (clean prose, provenance stored separately)
```

**Implementation:**
1. Compose prompt requires inline citations: `[A3,C2]` after each claim
2. Post-compose parser extracts citation graph: brief_claim → layer_claims → facts
3. Verification pass: for each brief claim, check that cited layer claims exist AND that the brief claim is semantically supported by those layer claims
4. Ungrounded claims (no citation, or citation doesn't support) are flagged
5. Retry with flagged claims listed as "remove or ground these"
6. Final brief strips citations; citation graph stored in `brief_claim_provenance` table
7. Served brief is clean prose; provenance is queryable via MCP `trace` tool

**Advantages:**
- Complete provenance chain from brief → layer → fact → source conversation
- Architectural enforcement, not prompt-level constraint
- Enables the "trace any claim" feature that differentiates Base Layer
- Verification is mechanical (embeddings + NLI), not subjective
- Retry loop gives the model a chance to self-correct

**Disadvantages:**
- Most complex to implement
- Citations in compose output may degrade prose quality (mitigated by stripping)
- Verification still relies on semantic similarity (imperfect)
- Adds ~2x compose cost (verification pass)
- Model may fabricate citations (cite [A3] when A3 doesn't support the claim)

**Feasibility:** Medium. This is the architecturally correct solution. Implementation is ~1 session of work. The risk is that fabricated citations undermine the verification, requiring the NLI/embedding check as a second line of defense.

---

## 5. The Difficulty of Setting Appropriate Guardrails

This section addresses what makes this problem genuinely hard, beyond the engineering.

### 5.1 Synthesis Is the Product

Base Layer's value proposition is behavioral compression — taking thousands of conversation turns and producing a document that captures who someone is. This requires synthesis: identifying patterns across facts, naming tensions, predicting behaviors. Every one of these synthesis operations goes beyond what any individual source fact states.

A faithfulness gate that's too aggressive kills synthesis. A gate that's too permissive allows hallucination. The optimal point is context-dependent:
- For famous subjects (Franklin, Buffett): the model's pre-training knowledge is extensive, so more contamination risk → stricter gate needed
- For private subjects (Aarik, Bavani): less pre-training knowledge, so less contamination risk → but the inverted-claim problem shows this isn't zero
- For project subjects (Base Layer): no pre-training knowledge → gate is irrelevant

There is no single threshold that works across all subject types.

### 5.2 The Evaluation Bootstrapping Problem

To build a good faithfulness gate, we need labeled examples of:
- Grounded claims (synthesis that's legitimate)
- Ungrounded claims (hallucination from pre-training)
- Edge cases (synthesis that's debatable)

We don't have these labels at scale. The contamination scan was manual (human + AI reviewing each claim against source layers). To build an automated gate, we'd need hundreds of labeled examples per subject type. This is a cold-start problem.

### 5.3 The Reward Misalignment

When we tell Opus "derive only from input," we're setting up competing objectives:
1. **Write a compelling, specific, useful behavioral portrait** (quality objective)
2. **Only include information from the source layers** (faithfulness objective)

For famous subjects, objective 1 is best served by including pre-training knowledge (it makes the portrait more vivid and accurate). Objective 2 prohibits this. The model resolves this conflict probabilistically — sometimes faithfulness wins, sometimes quality wins. We can't control which.

This is structurally similar to the RLHF helpfulness-harmlessness tradeoff. The solution in that domain was Constitutional AI / RLAIF — using the model to self-evaluate against explicit principles. A similar approach here might work: have the model generate, then self-evaluate each claim against the source material, then revise. But this is essentially approach 4.3 (two-pass composition) with the same pre-training knowledge problem.

### 5.4 The Philosophical Question

Is a hallucinated-but-true claim harmful? If Opus adds "He rises at five" to Franklin's brief, and this is factually accurate about Franklin, does the brief become worse?

**Yes, for two reasons:**
1. **Verifiability:** The pipeline's differentiator is provenance — every claim traces to source. A true-but-unsourced claim breaks this contract.
2. **Trust:** If we accept true-but-unsourced claims for famous subjects, we have no mechanism to reject false-but-plausible claims. The inverted claim about Aarik shows that "plausible" doesn't mean "correct." The only safe policy is: if it's not in the source, it's not in the brief.

### 5.5 What "Good Enough" Might Look Like

Perfect provenance enforcement may be impossible with current technology. A pragmatic target:

- **0 inversions** (claims that contradict source material) — these are dangerous and detectable
- **<3 ungrounded claims per brief** for famous subjects — down from 8-18 currently
- **0 ungrounded claims** for private/project subjects — already nearly achieved
- **Every claim either cited or flagged** — so a human reviewer knows exactly what to audit
- **Provenance chain queryable** — any user can ask "where does this claim come from?" and get an answer

---

## 6. Recommended Approach

Based on this analysis, the recommended implementation combines approaches 4.7 (provenance chain) and 4.4 (local model for verification):

### Phase 1: Provenance-Preserving Composition
- Modify compose prompt to require `[A1,C3,P2]` citations after each behavioral claim
- Post-compose parser extracts citation graph
- Store in `brief_claim_provenance` table
- Strip citations from served brief

### Phase 2: Mechanical Verification
- For each brief claim + its cited layer claims, run:
  - Sentence embedding similarity (threshold: 0.60)
  - NLI entailment check (threshold: 0.50 for SUPPORTED)
- Flag claims that fail both checks as UNGROUNDED
- Flag claims with no citations as UNCITED

### Phase 3: Decontamination Retry
- If >3 claims flagged: retry composition with specific decontamination instruction listing flagged claims
- Max 2 retries (existing pattern from D-078)
- If still >3 after retries: output brief with `[UNVERIFIED]` markers on flagged claims

### Phase 4: Local Model Verifier (Optional Enhancement)
- Run a local model (Qwen 2.5 7B or similar) as an independent verifier
- Task: "Given ONLY this source text, is this claim supported? YES/NO/PARTIAL"
- Local model has less pre-training knowledge → less likely to "verify" a hallucination
- Disagreements between Opus verification and local verification trigger human review

### Cost Estimate
- Phase 1-3: ~$0.10-0.30 per compose (current: ~$0.15) — roughly 2x
- Phase 4: $0 (local inference)
- Implementation: ~1 session for Phase 1-3, ~0.5 session for Phase 4

---

## 7. Open Questions for External Review

1. **Is provenance-preserving composition sufficient, or do we need to fundamentally change the compose architecture?** The model can fabricate citations. If it cites [A3] for a hallucinated claim, the citation graph looks clean but the content is wrong. How do we handle this?

2. **Should we accept that famous-subject briefs will always have some pre-training contamination and focus on detecting/marking it rather than preventing it?** The Paul Graham case shows prevention CAN work. But it's not reliable.

3. **Is there a better anonymization strategy that would prevent identity inference?** Current: replace names with "this person." Could we go further — abstract domain vocabulary? Replace "printing press" with "trade equipment"? This would prevent identity inference but also strip the brief of specificity.

4. **Would fine-tuning a small model specifically for faithful composition be worth the investment?** We have ~11 subjects with source layers and briefs. Is that enough training data? What would the training objective be?

5. **Is the two-model approach (Opus generates, local model verifies) fundamentally sound, or does it just add complexity without solving the core problem?** The local model may have its own biases and failure modes.

6. **How do we handle legitimate synthesis that goes beyond any single source fact?** "He tests everything empirically" synthesized from 15 individual experiment facts is legitimate. "He rises at five" synthesized from "he values time management" is not. Where's the line, and can it be operationalized?

7. **Should provenance enforcement be configurable per subject type?** Strict for famous subjects (high contamination risk), relaxed for private subjects (low risk), off for project subjects (zero risk)?

---

## Appendix: Current Pipeline Provenance Flow

```
SOURCE CONVERSATIONS / DOCUMENTS
  │
  ├─ extract_facts.py (Haiku) ──→ FACTS table [F-xxx]
  │   provenance: source_id, chunk_index, timestamp
  │
  ├─ author_layers.py (Sonnet) ──→ ANCHORS [A1-An], CORE [C1-Cn], PREDICTIONS [P1-Pn]
  │   provenance: each claim cites [F-xxx, F-yyy] via Citations API or self-citation
  │   STATUS: Citations API never worked on Windows (S77 bug). All subjects used
  │   self-citation fallback. Bug fixed in code, layers not yet re-authored.
  │
  ├─ agent_pipeline.py (Opus) ──→ UNIFIED BRIEF (brief_v4.md)
  │   provenance: ██ NONE ██  ← THIS IS THE GAP
  │   Current gates: term completeness (regex), faithfulness (proper nouns only),
  │   contamination (template phrase blocklist)
  │
  └─ mcp_server.py ──→ SERVED TO AI
      provenance: vector similarity recall (L2 distance proxy)
      No claim-level trace from served brief back to source facts.
```

**The gap:** Layer claims have provenance. The brief has none. The brief is the artifact that reaches the end user. This means the pipeline's most important output is its least verifiable.
