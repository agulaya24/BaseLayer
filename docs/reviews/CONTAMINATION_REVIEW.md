# Collective Review Request: Cross-Platform Contamination & Claude Code Identity Recovery

## The Problem

Two related contamination vectors need to be addressed:

### Vector 1: Project language leaking into non-project conversations

The developer discusses Base Layer concepts with ChatGPT and Claude.ai (non-Code). These conversations are in the personal extraction pipeline. They may contain:
- Direct quotes or paraphrases from project documentation (DECISIONS.md, PROGRESS.md, analysis docs)
- System-specific terminology (epistemic anchors, knowledge tiers, behavioral predictions, contradiction over decay, etc.)
- Concepts shaped by the identity block itself — the developer's language about himself now reflects what the system has fed back to him

This creates a feedback loop: identity block shapes how the developer talks about himself in other AI conversations, those conversations get extracted as "personal facts," those facts feed back into the next identity block.

### Vector 2: Useful personal identity information trapped in Claude Code sessions

D-044 excludes Claude Code sessions from personal fact extraction because of meta-contamination (discussion about what identity blocks should say, fact classifications, system architecture). But the developer reveals genuine personal information during work sessions — values, reactions, decision-making patterns, emotional responses — that would be valuable for identity modeling.

Currently, this information is lost entirely.

## Proposed Approaches

### For Vector 1 — Contamination Detection

**Raw text matching against documentation:**
- Extract distinctive phrases/sentences from all project docs (DECISIONS.md, PROGRESS.md, CLAUDE.md, ARCHITECTURE.md, DESIGN_PRINCIPLES.md, analysis docs)
- Run substring or fuzzy matching against all conversation messages in the personal pipeline
- Flag conversations with significant overlap for review or exclusion
- Could also match against AUTHORING_EXCLUSION_PATTERNS as a first pass

**Questions for the Collective:**
- What similarity threshold constitutes contamination vs. the developer naturally using language he's developed?
- Should flagged conversations be excluded entirely, or can contaminated messages be filtered while preserving the rest?
- Is there a temporal cutoff — conversations before the project started (pre-Session 1) are clean by definition?

### For Vector 2 — Identity Recovery from Claude Code

**Filtered extraction with a specialized prompt:**
- Run Claude Code session messages through an extraction pass with a prompt that explicitly excludes:
  - Discussion about system architecture, design decisions, identity blocks
  - References to facts, fact extraction, memory system components
  - Meta-discussion about how to represent the user
- Only extract facts that would be true regardless of whether the project existed
- Apply AUTHORING_EXCLUSION_PATTERNS as a hard filter on extracted facts

**Isolation pass:**
- Extract to a staging table, not directly into memory_facts
- Human review before merging into personal scope
- Track provenance (source: claude_code_filtered) so they can be audited later

**Questions for the Collective:**
- Is a prompt-based filter reliable enough, or will meta-contamination bleed through?
- Should extracted facts from Claude Code be treated as lower-confidence and require cross-validation against facts from other sources?
- Is there a simpler approach: just identify the N most clearly personal messages from Claude Code sessions (emotional reactions, value statements, decision rationale) and extract from those only?

### For both vectors — The deeper feedback loop concern

The developer's self-description is now influenced by the system. He articulates his values, thinking style, and decision patterns more precisely BECAUSE the system has reflected them back. This means even "clean" conversations may contain language that's been shaped by the memory system. This may not be a problem — a person who understands themselves better is still themselves — but the Collective should consider whether this is contamination or just growth.

## Requested Review

Grade the severity of each vector and evaluate the proposed approaches. Specifically:
1. Is raw text matching sufficient for Vector 1, or do we need semantic matching?
2. What's the right extraction approach for Vector 2 — prompt filtering, message-level selection, or something else?
3. Is there a contamination threshold below which we accept the noise?
4. Does the deeper feedback loop (the developer's language shaped by the system) require any action, or is it an acceptable feature of a self-correcting system?

---

# Collective Review — 2026-02-20

## 1. Cognitive Scientist

**Grade: B+**

**Key Observations:**

1. **The feedback loop is a known phenomenon, not a bug.** In cognitive science, this is the *testing effect* crossed with *retrieval-induced facilitation*. When a person encounters a structured description of their own behavior (the identity block), it strengthens the neural pathways for that specific articulation. The person then reproduces that articulation in future conversations — not because they are "contaminated" but because the system has aided their self-knowledge consolidation. This is exactly what happens in psychotherapy: a therapist reflects patterns, the patient adopts the language, and the language becomes genuinely theirs. The line between "externally shaped vocabulary" and "internalized understanding" dissolves over time. This is identity development, not contamination.

2. **Vector 1 and Vector 2 are different problems with different cognitive signatures.** Vector 1 (project language in personal conversations) is a *source monitoring* problem — the system cannot distinguish between the developer discussing the project as a project and the developer expressing beliefs that happen to use project vocabulary. "Contradiction over decay" is a project design principle, but it is also genuinely how the developer thinks about knowledge management in all domains. Vector 2 (personal facts in Claude Code) is a *signal extraction* problem — the genuine personal data exists but is embedded in a high-noise context. These require different solutions.

3. **Temporal framing matters more than the document acknowledges.** The document asks about a temporal cutoff for pre-project conversations. This is the right instinct but underspecified. The cognitive reality is a gradient: early conversations are clean, conversations from the first 10 sessions have project concepts but not yet project vocabulary, conversations from sessions 20+ have deeply integrated language. A binary clean/contaminated split misses this gradient.

**Concerns:**

1. The proposed raw text matching for Vector 1 conflates *language overlap* with *conceptual contamination*. the developer might say "I believe in iterative improvement over certainty" in a personal conversation — this matches project documentation, but it is a genuine personal belief that existed before the project named it. String matching would flag this as contamination and suppress a real fact. The problem is not that the words match; the problem is distinguishing between "the developer is describing his project's design philosophy" and "the developer is expressing a personal value that his project also adopted."

2. The staging table approach for Vector 2 assumes human review will scale. With 25 Claude Code sessions now and a growing count, manual review of extracted facts becomes a bottleneck. The cognitive science answer is: trust the extraction model to handle the easy cases and reserve human attention for ambiguous ones. But defining "ambiguous" programmatically is the hard part.

**Recommendation:**

For Vector 1, use a two-layer filter: (a) AUTHORING_EXCLUSION_PATTERNS as a hard substring filter on extracted facts (already exists), and (b) a *context classifier* at the message level — not the fact level — that tags messages as "discussing Base Layer project" vs. "discussing personal topics." This is more reliable than fact-level filtering because the surrounding context makes the intent clear. A message about "how we should handle knowledge tier classification" is unambiguously project. A message about "I think knowledge should never be deleted, it should be recontextualized" could be either, but the surrounding messages disambiguate.

---

## 2. Narrative Biographer

**Grade: A-**

**Key Observations:**

1. **This document identifies the most philosophically interesting problem in the entire project.** The question "is this contamination or growth?" is not a technical question — it is the central question of narrative identity. When a person encounters a mirror that shows them their own patterns, and they then articulate those patterns more precisely, the mirror has become part of their story. A biographer would not say "this subject's self-understanding was contaminated by therapy" — they would say "therapy became a formative influence." The memory system is in the same position. The developer's vocabulary has been shaped by building this system. That shaping is now part of who he is. Trying to subtract it would be like trying to subtract the influence of a philosophy degree from a philosopher's self-description.

2. **The real danger is not feedback but *flattening*.** The contamination risk is not that project language appears in personal conversations. The risk is that the system's categories *constrain* how the developer describes himself. If he starts seeing all his beliefs through the lens of "epistemic anchors" and "commitment depths," he may stop expressing beliefs that do not fit those categories. A good biographical system should capture what the subject says, not force the subject to speak in system-compatible terms. The question to ask is: has the taxonomy narrowed his self-expression? If his post-system conversations show the same range of topics but more precise language, that is growth. If they show a narrower range of topics clustered around system categories, that is flattening.

3. **Vector 2 is a genuine information loss problem and should be prioritized.** From a biographical perspective, how someone behaves under working conditions — their reactions to setbacks, their decision-making under time pressure, their emotional responses to technical problems — is some of the richest identity data available. The fact that D-044 blanket-excludes this is understandable but costly. A biographer would never discard work diaries because they also contain work content. They would read them for the personal revelations embedded within the professional context.

**Concerns:**

1. The document frames Vector 2 as "recovery" — implying the information is currently lost and needs to be retrieved. But "lost" overstates it. The Claude Code sessions still exist. The information is not lost; it is unprocessed. The urgency should be proportional to how much unique personal information exists in those sessions that does not appear anywhere else. If the developer expresses the same values in ChatGPT conversations (which he likely does, given that values are stable), the Claude Code sessions are redundant for identity modeling. The unique contribution would be *behavioral* facts — how he actually works, which is different from how he describes his values.

2. The proposal to "only extract facts that would be true regardless of whether the project existed" is a useful heuristic but epistemically fragile. Many facts about the developer are true *because* the project exists — his current priorities, his time allocation, his skill development. These are real personal facts. The filter should not be "would this be true without the project" but "is this about the person or about the system's architecture."

**Recommendation:**

For Vector 2, use message-level selection rather than prompt filtering. Go through Claude Code sessions and identify messages where the developer is expressing a personal reaction, value judgment, or decision rationale — not discussing system architecture. Extract only from those messages. This is more labor-intensive than prompt filtering but produces higher-quality facts because the extraction model sees clean input rather than being asked to filter contaminated input. A practical approach: tag messages by speaker role (user vs. assistant), then within user messages, classify as "directive" (do X), "architectural" (the system should Y), or "personal" (I think/feel/want Z). Extract only from "personal" messages.

---

## 3. Epistemologist

**Grade: B**

**Key Observations:**

1. **The document correctly identifies three levels of contamination but misses the epistemological asymmetry between them.** Level 1 (direct contamination — system terms in facts) is a *classification error* and is fully correctable with filters. Level 2 (context poisoning — extraction model influenced by surrounding system discussion) is a *source reliability* problem that degrades the extraction model's output quality. Level 3 (feedback loop — the subject's self-description is shaped by the system) is an *epistemological transformation* of the ground truth itself. These are fundamentally different kinds of problems. Level 1 is engineering. Level 2 is model quality. Level 3 is philosophical and may not have a "solution" — it may only have a position.

2. **The justification for accepting the feedback loop is stronger than the document realizes.** The document tentatively suggests "a person who understands themselves better is still themselves." This is correct and can be stated more firmly. In epistemology, the distinction that matters is between *constitutive* and *distorting* influences. A constitutive influence is one that changes the subject in a way the subject endorses upon reflection (Frankfurt's second-order desires). A distorting influence changes the subject in ways they would reject if they saw the mechanism. If the developer reflects on his more precise self-articulation and endorses it — "yes, this is what I mean" — then the system's influence is constitutive, not contaminating. The test is reflective endorsement, not causal independence.

3. **The contamination threshold question (Question 3) is the wrong question.** Asking "below what threshold do we accept the noise?" implies that contamination is a continuous quantity that can be tolerated at low levels. But contamination is categorical, not continuous. A fact is either about the person or about the system. There is no "5% contaminated fact." The right question is: what is the false positive rate of the detection method, and is that acceptable? If AUTHORING_EXCLUSION_PATTERNS catch 95% of meta-facts and the remaining 5% are borderline cases that are arguably personal, the system is working. The threshold is on the *detector*, not on the *contamination*.

**Concerns:**

1. The proposal for Vector 1 (raw text matching against documentation) has a serious epistemic problem: it treats the documentation as the canonical source and the conversations as derivative. But the causal direction may be reversed — the developer's beliefs shaped the documentation, not the other way around. Matching his conversation language against his documentation language and calling it "contamination" when they align is backwards. The alignment may mean the documentation accurately captured his beliefs, which he then continues to express. Flagging these as contaminated would systematically suppress his most strongly held and consistently articulated views.

2. The cross-validation proposal for Vector 2 (requiring Claude Code facts to be confirmed by other sources) sets up an asymmetric evidence standard. Facts from ChatGPT are accepted at face value, but identical facts from Claude Code require corroboration. If the concern is meta-contamination, the filter should address meta-contamination directly, not impose a blanket credibility penalty on an entire source. This is the epistemological equivalent of discounting a witness's entire testimony because they were at the scene of the crime — the proximity is precisely what makes some of their observations valuable.

**Recommendation:**

Abandon the contamination metaphor. Replace it with *provenance tracking*. Every fact should carry metadata about its source context: which platform, what the conversation was about, whether project terminology appeared in the surrounding messages. This does not require excluding or downweighting anything — it just makes the information available for downstream decisions. When authoring identity blocks, the authoring process can then choose to prefer facts that appear across multiple contexts (high cross-context recurrence = robust signal) without penalizing any single source. This aligns with D-044's cross-scope anchor validation concept and extends it from scope to provenance.

---

## 4. Pragmatic Engineer

**Grade: B+**

**Key Observations:**

1. **The existing AUTHORING_EXCLUSION_PATTERNS (16 patterns) already handle the majority of Level 1 contamination for Vector 1.** The 29 meta-contamination facts that motivated D-044 were caught and superseded. Before building new infrastructure, measure the current false negative rate: how many meta-facts are in the active fact base right now that were NOT caught by the existing patterns? If the answer is "very few" or "none we can find," then Vector 1 is a solved problem at the fact level, and the proposed raw text matching against documentation is over-engineering. If the answer is "there are still dozens," then the patterns need expansion, not a new matching system.

2. **For Vector 2, the simplest thing that works is message-level pre-filtering, not fact-level post-filtering.** The proposed approach of running extraction with a specialized prompt and then filtering the output is fighting the problem at the wrong stage. If you send the extraction model a message about "we should add a commitment_depth column to the schema," no prompt instruction will reliably prevent it from extracting something about the user's data modeling preferences. The simpler approach: before extraction, classify each user message in Claude Code sessions as "personal" or "project" using a lightweight classifier (even a keyword list would work for the obvious cases). Only feed "personal" messages to the extraction pipeline. The extraction model then sees clean input and does not need to be told what to ignore.

3. **The staging table proposal is good engineering and should be adopted regardless of which extraction approach is chosen.** Any new source of facts — whether from Claude Code filtered extraction, re-extraction on Sonnet, or future sources — should go through a staging table with human review before merging. This is a general-purpose safety mechanism. Build it once, use it for everything. Track `source_type` (e.g., "claude_code_filtered", "sonnet_reextraction", "chatgpt_standard") and `review_status` (pending, approved, rejected) as columns.

**Concerns:**

1. The document proposes building a documentation-matching system for Vector 1 (extracting phrases from project docs, running fuzzy matching against conversations). This is a significant engineering investment for an unclear payoff. How many conversations actually discuss Base Layer outside of Claude Code? The document says the developer discusses it with ChatGPT and Claude.ai, but does not quantify. If it is 20 out of 1,859 ChatGPT conversations, the ROI of building a matching system is low — just tag those 20 conversations manually and exclude them. If it is 200, the investment is justified. Measure before building.

2. Semantic matching (as opposed to raw text matching) for Vector 1 would require embedding all project documentation and computing similarity against all conversation messages. This is computationally expensive and introduces a new failure mode: legitimate personal statements that happen to be semantically close to project documentation would be falsely flagged. The Epistemologist is right — the causal arrow often runs from beliefs to documentation, not the reverse. Semantic matching would amplify this false positive problem.

**Recommendation:**

Three concrete steps, ordered by effort:

1. **Measure first (low effort).** Query the fact base for facts containing project-specific terms not already in AUTHORING_EXCLUSION_PATTERNS. Count them. If fewer than 20, expand the pattern list and call Vector 1 handled. If more, proceed to step 2.

2. **Message-level classifier for Claude Code (medium effort).** Build a simple keyword + heuristic classifier that tags each user message in Claude Code sessions as "personal" or "project." Keywords like "I feel," "I think," "I want," "reminds me of," "my experience" lean personal. Keywords like "the pipeline," "this script," "we should implement," "the schema" lean project. Extract only from personal-tagged messages. Route to staging table.

3. **Staging table infrastructure (medium effort, high reuse).** Build once as a general mechanism. Add `staging_facts` table with same schema as `memory_facts` plus `source_type`, `review_status`, `reviewed_at` columns. All non-standard extraction flows go through staging.

---

## Synthesis

**Consensus Grade: B+**

All four reviewers agree the problem is real and well-articulated. The document correctly identifies the two vectors and the deeper philosophical question. The proposed approaches are reasonable but over-engineered in places (documentation matching for Vector 1) and under-specified in others (prompt filtering for Vector 2).

### Areas of Agreement

- **The feedback loop (Question 4) is not contamination — it is growth.** All four personas converge on this. The Cognitive Scientist calls it retrieval-induced facilitation. The Narrative Biographer calls it a formative influence. The Epistemologist calls it constitutive rather than distorting. The Pragmatic Engineer implicitly agrees by not proposing any solution for it. The developer's more precise self-articulation is a feature, not a bug, as long as it broadens rather than narrows his self-expression. **No action required on the feedback loop itself**, but monitor for flattening (narrowing of topics to fit system categories).

- **Message-level filtering is superior to fact-level filtering for Vector 2.** The Narrative Biographer, Epistemologist, and Pragmatic Engineer all independently recommend operating on messages before extraction rather than on facts after extraction. The extraction model produces better output when given clean input than when asked to ignore contamination in mixed input.

- **The staging table is sound infrastructure.** All reviewers implicitly or explicitly endorse isolated extraction with human review before merging. This is a general-purpose safety mechanism with high reuse value.

- **Measure before building for Vector 1.** The Pragmatic Engineer and Epistemologist both note that the scale of Vector 1 is unquantified. The existing AUTHORING_EXCLUSION_PATTERNS may already be sufficient. Measure the current false negative rate before investing in new detection infrastructure.

### Areas of Disagreement

- **Provenance tracking vs. detection/exclusion.** The Epistemologist advocates abandoning the contamination metaphor entirely in favor of provenance metadata that informs downstream decisions without excluding anything. The Pragmatic Engineer favors explicit filtering and exclusion as simpler to reason about. The Cognitive Scientist sits between — wanting context classification but not hard exclusion. The Narrative Biographer leans toward the Epistemologist's position. This is a genuine architectural tension: provenance tracking is more principled but adds complexity; exclusion is simpler but risks information loss.

- **Whether Vector 2 is urgent.** The Narrative Biographer considers it a significant information loss that should be prioritized. The Cognitive Scientist and Pragmatic Engineer consider it lower priority because the personal information in Claude Code sessions likely duplicates what appears in other conversations. The unique contribution (behavioral data about working style) is valuable but not essential for the current identity block architecture.

### Answers to the Four Questions

**Q1: Is raw text matching sufficient for Vector 1, or do we need semantic matching?**
Neither. Raw text matching against documentation over-indexes on vocabulary overlap and will produce false positives on genuinely held beliefs that also appear in project docs. Semantic matching amplifies this problem. The recommended approach is: expand AUTHORING_EXCLUSION_PATTERNS if measurement shows current patterns are insufficient, and optionally add a message-level context classifier for conversations that discuss the project. Do not build a documentation-matching pipeline.

**Q2: What's the right extraction approach for Vector 2?**
Message-level selection. Classify each user message in Claude Code sessions as "personal" or "project" using a keyword + heuristic classifier. Extract only from personal-tagged messages. Route extracted facts to a staging table for human review before merging into the personal scope. Do not rely on prompt-level filtering — the extraction model should not see project messages at all.

**Q3: Is there a contamination threshold below which we accept the noise?**
The question is reframed: the threshold is on the *detector's false positive/negative rate*, not on the contamination level. If AUTHORING_EXCLUSION_PATTERNS catch the clear meta-facts and the remainder are arguably personal, the system is working. There is no need to define a numeric contamination percentage. Accept that borderline cases (personal beliefs expressed in project vocabulary) are genuine facts, not noise.

**Q4: Does the deeper feedback loop require any action?**
No. Unanimous across all four personas. The feedback loop is constitutive influence, not contamination. The developer's more precise self-articulation is genuine self-knowledge development. The only monitoring needed is for *flattening* — if his self-expression narrows to fit system categories rather than broadening with more precise language. This can be checked qualitatively during identity block authoring.

### Top 3 Actionable Recommendations

1. **Measure Vector 1 contamination in the current fact base.** Query active facts for project-specific terms beyond AUTHORING_EXCLUSION_PATTERNS. If fewer than ~20 are found, expand the pattern list and consider Vector 1 handled at the fact level. If more are found, add a message-level context classifier for conversations that discuss Base Layer.

2. **Build message-level pre-filtering for Claude Code extraction (Vector 2).** Classify user messages as personal vs. project before extraction. Extract only from personal-tagged messages. Route to a staging table for human review. Track provenance as `source_type = 'claude_code_filtered'`.

3. **Build the staging table as general infrastructure.** Add `staging_facts` table with `source_type`, `review_status`, and `reviewed_at` columns. Use for all non-standard extraction flows (Claude Code filtered, Sonnet re-extraction, future sources). This decouples extraction experimentation from production fact base integrity.
