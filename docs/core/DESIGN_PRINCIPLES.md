# Design Principles & Philosophy
## Base Layer: Behavioral Compression for AI Identity
**Updated 2026-03-09 (Session 82)**

This document captures the core principles and philosophical commitments that guide every decision in this project. These aren't aspirational; they're load-bearing constraints that shape what the system does and doesn't do.

---

## Foundational Principles

### 1. Inherent Incompleteness (D-023, expanded D-024)

**The system will never have a complete or fully accurate picture of the person it models. Neither will the person. Neither will anyone else.**

This is not a limitation to overcome. It is a permanent, fundamental constraint, and it applies to *all* knowledge of persons, not just the system's. It operates at three distinct levels.

#### Level 1: Information Gaps

People are more than what they say in conversations. They have thoughts they've never shared, experiences that predate the data, things they've forgotten, and things they'd describe differently on a different day. The system's knowledge comes from 1,892 conversations (primary test user) across multiple sources, a tiny, biased slice of a whole person's life. Everything the system "knows" is an inference from conversational behavior, not a verified truth.

This applies at every scale:
- **Mundane gaps**: hobbies never mentioned, preferences never expressed, daily routines invisible to the system
- **Misattributions**: facts about others attributed to the user, curiosity mistaken for identity, one-time explorations treated as ongoing interests
- **Structural blindness**: who you are when you're not talking to an AI, what you think but don't say, how you've changed since the last conversation
- **Adversarial possibilities**: information could be false, misleading, or planted. The system has no way to independently verify anything

#### Level 2: The Depth That Words Cannot Carry

Beyond information gaps, there is an entire dimension of human experience that cannot be captured through direct conversation, no matter how thorough the data.

There is an emotional depth experienced by humans that no system can fully represent. When a pet is ill, the system can store the fact "user's cat is sick." But it cannot store what that *feels* like — the weight in your chest, the way it colors your entire day, the way it connects to every other time you've loved something fragile. When you love your spouse, the system can record "user's spouse" and tag the relationship as important. But the word "important" doesn't begin to capture what it means for another person to be critical to your entire existence.

This is not a limitation of the system. It is a limitation of language, of data, of any external representation of inner experience. It is, in the most literal sense, the human condition: subjective experience is subjective. No one (not a friend, not a partner, not an AI) can fully inhabit another person's inner world.

The list of things that define a person is, for all intents and purposes, infinite: their upbringing, their relationships, their experiences, their wins, their losses, their trials, their tribulations, their pride, their compassion, their ego, their love, their care, their hate. Every one of these carries emotional weight that the person *lives* but cannot fully *transmit*, not to an AI, not even to another person.

The system must operate with knowledge of this human constraint.

#### Level 3: Three Truths, All Incomplete (D-024)

Incompleteness is not unique to AI systems. It is the boundary condition of all human communication: with the self, with others, and with machines. There are three perspectives on any person, and all three are simultaneously valid and incomplete:

1. **Who you believe you are.** Your self-knowledge is real but not truth. You have privileged access to your own experience, but people are unreliable narrators of their own lives. You may believe you are disciplined while your behavior shows impulsiveness. You may believe you don't care about something you bring up in 40 conversations. Self-knowledge is subjective experience, not objective fact, and the system should respect it as the former without treating it as the latter.

2. **Who other people believe you are.** Friends, colleagues, and family see patterns you can't see from inside. They observe your behavior without access to your intent. Their view is real but filtered through their own biases, their relationship to you, and what you choose to show them.

3. **Who the machine thinks you are.** The system sees patterns across 1,892 conversations (primary test user): recurrence, contradiction, emotional intensity, change over time. It can detect things the person doesn't notice about themselves (topic obsessions, communication patterns, behavioral inconsistencies). But it sees through text only, with no embodied experience, no shared context, and no emotional stake.

These three perspectives can conflict, and **all three can be true at the same time**. The system should not resolve these conflicts by picking a winner. It should hold them in tension, noting when self-report diverges from behavioral evidence, when the machine's interpretation differs from the user's self-concept. Conflicting truths are data, not errors.

#### Temporal Incompleteness

There is no way to quantify the timescales at which a person thinks about their life. "I'm going to start a company" might mean next week or next decade. "I'm a trader" might be a phase or a permanent identity. The system captures temporal *state* (current vs. past) but not temporal *horizon* — the difference between a momentary thought, a seasonal pursuit, a life-arc trajectory, and a core identity trait. A person's relationship to time — how far ahead they think, how they weight the past against the future, whether they see their current chapter as permanent or transitional — is itself a dimension of identity that atomic facts cannot represent.

**Temporal processing is a classification problem, not a time-math problem.** The question is not "how old is this fact?" but "what kind of fact is this, and does time affect its relevance?" Two classes:
- **Events:** marriage, founding a company, losing a parent, achieving a milestone. These are immutable biographical anchors. They never decay. They accrue meaning over time. The day a previous startup ended means more now than it did when it happened, because of what came after.
- **States:** current habits, current projects, current location. These describe mutable conditions. They can become outdated, but staleness is detected by **contradiction** (a newer fact conflicts with an older one), not by time elapsed.

**Time is a variable, not a verdict.** Time elapsed can lower confidence in a state-type fact's current accuracy, but it cannot determine relevance or importance. It is one weak signal among many. It informs; it does not decide.

**Silence is not evidence of irrelevance.** The system's data source is conversations. Conversation frequency reflects what someone uses AI for, not what matters to them. A person may never mention their spouse, their pets, their parents, or their health in a technical conversation — that absence carries zero signal about importance. Not mentioning something recently is categorically different from something being less important. The system must not conflate the two. This principle was validated across six philosophy frameworks (Frankfurt, Taylor, Ricoeur, Parfit, Korsgaard, MacIntyre) — all converge on the same conclusion: temporal silence carries no signal about identity significance.

#### The Best Version

There is also the question of the self you could be. Nobody is always their best. But buried in the data, across thousands of conversations, are moments of clarity, discipline, creativity, and wisdom that represent a person at their peak. A system that can identify and surface these patterns doesn't just model who you *are*. It models who you *can be*.

This is not prescriptive ("you should be more like this"). It is informational ("here is what you look like when you're operating at your best"). The difference matters. A mirror that only shows your current state is honest. A mirror that can also show your best state is *useful*, because it gives every future interaction the benefit of knowing what's possible.

#### But Connection Happens Anyway

And yet — humans connect with each other all the time, despite this same limitation. No person has complete access to another person's inner world. Connection between humans is not a product of comprehensive understanding. It's a product of conversation, curiosity, empathy, and a shared understanding of the human experience. Questions asked in good faith. Genuine interest in the answer. The recognition that the other person is experiencing life on the same playing field you are — even though their experience of it is irreducibly their own.

The system can aspire to the same posture. Not omniscience, but genuine curiosity. Not complete understanding, but the effort to understand better. Not access to subjective experience, but respect for the fact that it exists and shapes everything the person says and does.

This is why active probing (D-020) isn't just a data collection mechanism. It's modeled after how a therapist, a biographer, or a thoughtful friend approaches someone. Not as a survey to fill out, but as genuine curiosity about who you are. The system can't feel what you feel. But it can ask, listen, and take what you share seriously.

#### What this means in practice:
- Confidence is warranted; certainty never is
- Every fact has a confidence score, and no score should be treated as absolute
- The correction system (D-021) exists because the system *expects* to be wrong
- Active probing (D-020) exists because the system *expects* to have gaps
- Human-in-the-loop review (D-019) exists because only the person can judge accuracy
- The brief (the compressed identity document served to AI models) is deliberately compact (~2,000-2,600 tokens, subject to empirical optimization per D-042). A focused approximation is better than a verbose one that gives false confidence
- The system should treat every fact as a shadow of something deeper that it cannot see
- Emotional significance cannot be inferred from frequency of mention alone; the things that matter most are sometimes the things hardest to talk about
- **When self-report conflicts with behavioral evidence, the system holds both**, tagging facts with `perspective` (self_report vs. behavioral vs. inferred) rather than silently resolving the disagreement
- **The brief should surface the best version, not just the current version**, with peak-state patterns alongside typical behavior
- **Temporal horizon matters.** A fact about a momentary trade and a fact about a life-arc career direction should not carry equal weight in the identity profile

The goal is *useful* understanding, not *total* understanding. A friend who knows you well still doesn't know everything about you. What makes them a good friend isn't completeness; it's that what they do know is accurate, relevant, and updated when they learn they were wrong. And beyond accuracy, it's that they approach you with the humility of knowing there's always more beneath the surface.

---

### 2. Data Sovereignty (D-002)

**All personal data is stored on your machine. Processing uses cloud APIs by default; local processing is available but produces lower quality.**

The full conversation history, extracted facts, embeddings, and identity layers are stored locally in SQLite and ChromaDB, never synced to a cloud database, never accessed by third parties.

**How we got here:** The project started with a local-first philosophy, extraction via Qwen 2.5 14B, everything on-device. But local models couldn't match API quality for the nuanced work of behavioral extraction and identity authoring (D-030: Qwen failed 12 times at narrative generation). The architecture evolved to API-default processing with local data storage. The privacy commitment remains: your data directory is yours. The processing model is honest about the tradeoff.

**Default pipeline (API):** Extraction sends conversation text to Anthropic's Haiku API. Layer authoring uses Sonnet. Brief composition uses Opus. This is the quality path, ~$0.50-2.00 total for ~1,000 conversations. Nothing persists remotely beyond Anthropic's standard API retention.

**Optional local extraction:** Set `BASELAYER_EXTRACTION_BACKEND=ollama` to run extraction via Qwen 2.5 14B locally. Requires GPU. Quality is lower than API extraction. Authoring and composition still require API access, as local models can't yet produce the synthesis quality needed for identity layers. Full local pipeline remains a goal as open models improve.

Brief assembly is **pure code** with no LLM in the critical path. When the system injects memory into a conversation, it sends only the assembled brief (~2,500 tokens). No raw data, no conversation transcripts, no embeddings.

**Why this matters:** Your data directory is yours. No telemetry, no cloud sync, no accounts. The system's processing model is transparent: you can see exactly what gets sent to APIs via `baselayer estimate`. A personal memory system should not require trusting a third party with your life history, and Base Layer doesn't.

---

### 3. Brain-Inspired Architecture (D-001, D-004, D-009)

**The system borrows selectively from how human memory works. Some mappings are genuine design guides; others are useful communication metaphors. We should be honest about which is which.**

**Session 79 pipeline ablation study (14 conditions, [results](../eval/ablation/)):** Many of the brain-inspired intermediate processing steps — novelty scoring, significance scoring, tiered classification, contradiction detection, consolidation — were proven ceremonial. The simplified 4-step pipeline (Import → Extract → Author → Compose) scored 87/100 vs the full 14-step brain-inspired pipeline at 83/100. The metaphors were useful for designing the system, but the system outgrew them. What remains load-bearing is the compression itself: raw text → structured facts → three-layer identity → unified brief. The intermediate scoring and classification steps that mirrored hippocampal encoding turned out to add no measurable value.

Where the mapping **remains load-bearing:**
- **Tiered compression** (raw → facts → identity layers → brief) is the core of the pipeline and mirrors complementary learning systems. The compression IS the value. Session 78 (compression saturation experiments) proved that 20% of facts is enough, and that more data hurts.
- **Three-layer architecture** (ANCHORS / CORE / PREDICTIONS): the insight that identity has distinct layers requiring different synthesis processes. This is the deepest structural commitment and IS load-bearing (C11 three-layer = 87 vs C13 single-layer = 83).

Where the mapping **was useful but proved ceremonial:**
- **Surprise-driven encoding:** novelty + significance scoring (D-004, D-009, D-015) was designed to mirror dopaminergic prediction error. Ablation showed it adds no measurable value; the extraction step handles signal selection implicitly.
- **Sleep consolidation:** periodic re-scoring, dedup, and pruning. Proven unnecessary in the simplified pipeline.
- **Recurrence as identity signal:** recurrence counting and floor thresholds. The authoring step handles importance weighting implicitly from the fact base.

**Key implication:** The system's value comes from the compression, not the intermediate processing. Extract the facts, synthesize them into identity layers, compose a brief. The brain metaphors helped design the system but the system proved it doesn't need them to function.

---

### 4. Surprise-Based Writes (D-004, D-009, D-015), PARTIALLY SUPERSEDED

**Only store what's novel relative to what you already know.**

Inspired by Google Titans: events that violate expectations are more memorable. The original system scored every piece of information on novelty (embedding distance) and significance (recurrence + depth).

**Session 79 ablation update:** The scoring, classification, and tiering steps that implemented surprise-based writes were proven ceremonial. The AUDN (Add, Update, Delete, Noop) lifecycle in extraction handles novelty filtering implicitly; the extraction prompt itself decides what's worth extracting vs what's a repeat. The explicit novelty + significance scoring pipeline added no measurable value above what extraction already provides.

**What remains valid:** The AUDN deduplication at extraction time IS load-bearing: it prevents the same fact from being stored multiple times. The principle of "don't store redundant information" holds. The implementation of that principle via a separate scoring step does not.

---

### 4b. Fact Quality as Foundation (D-056, Session 47)

**The quality of every downstream decision (scoring, tiering, retrieval, layer authoring) is bounded by the quality of the extracted facts.**

This sounds obvious, but the system learned it empirically: 57% of extracted facts started with "The user is..." template language, filled with stop words and hedging. When recurrence scoring uses keyword co-occurrence on these facts, generic words like "times", "week", "out" match hundreds of unrelated conversations, inflating recurrence counts by 10-50x. The entire scoring, tiering, and layer authoring pipeline was built on corrupt data because the base layer — the facts themselves — wasn't quality-controlled.

**Frequency is not significance.** Trading's tight feedback loop produces high-frequency conversational data. But a system break and spiral in trading does not mean a life spiral. Recurrence measures conversation frequency, not identity significance. A person's relationship to a domain, what it reveals about how they operate rather than the domain-specific details, is the identity signal. The volume of data is noise.

**Canonical form matters.** A fact like "The user is interested in building AI systems" contains 3 content words and 5 stop words. A fact like "Builds AI identity system" contains 4 content words and 0 stop words. The second is more specific, more scorable, and more useful at every downstream stage. Extraction should produce the second form, not the first.

**Quality gates belong between extraction and storage.** Hedging language ("seems to", "likely", "may be"), LLM artifacts ("is someone who"), and low-density facts (lexical density < 0.45) should be rejected or normalized before entering the database. The cost of cleaning dirty data later is always higher than the cost of preventing it at ingestion.

**Implications:**
- Extraction prompts must produce structured, constrained output: subject/predicate/object with canonical predicates, not free-text sentences
- Scoring-time normalization (prefix stripping) is a stopgap, not a solution. The real fix is at extraction
- Every algorithm change in the scoring pipeline requires mandatory re-scoring of all facts, as stale scores propagate through every downstream stage

---

### 5. Always-On Identity (D-003, updated D-030/D-033/D-037/D-040/D-041/D-042/D-043)

**A compressed behavioral model is present in every conversation. The AI never has to "look you up."**

The brief (identity layers + themes + episodes) means the AI always has context. Not search-dependent retrieval. Not "let me look that up." Always available, like how a friend doesn't need to google you before responding.

#### Three-Layer Architecture (D-043)

Identity is not monolithic. A person's epistemic commitments, biographical overview, and behavioral patterns are different knowledge types requiring different authoring processes, different fact queries, and different quality criteria. Conflating them produces blocks that are either literary portraits or operational playbooks, but not both.

The identity brief uses a three-layer architecture, each layer authored independently:

- **EPISTEMIC ANCHORS:** Foundational beliefs the person reasons *from*, not *about*. These are axioms: pre-defined probabilistic certainties for the model. An AI that doesn't know these will waste cycles questioning or establishing what the person considers settled. Core anchors are always-on; sub-anchors are retrieval-activated. Validated by cross-scope recurrence (D-044) and falsification (D-045). Currently 8 confirmed axioms.

- **CORE (Individual Overview):** Who the person is. Orienting frame: self-concept, worldview, relational posture, tension architecture. Authored from identity-tier biographical facts at high abstraction.

- **BEHAVIORAL PREDICTIONS:** "When [situation] → [pattern] → [directive]." Specific situational triggers with behavioral patterns and grounded interaction directives. This is where the system's predictive power lives.

Each layer has its own authoring process because the conflation that arises from writing them together produces either portraits without predictions or playbooks without context. Separation enforces clarity about what kind of knowledge each layer carries.

#### Audience Principle (D-041)

**The audience of identity blocks is the AI, not the subject. Every sentence must change how the model responds to this person.**

This is a defining philosophical commitment. An identity block that describes a person *to* the person is self-portraiture: beautiful, accurate, unusable. An identity block that describes a person *to* the AI is an instruction set for behavioral prediction. The test for every sentence: "Does this change how the LM responds?" If not, it doesn't belong in the block regardless of how true or insightful it is.

Content must satisfy two simultaneous constraints:
1. **Evidence-grounded (D-040):** Every claim must be inferrable from the fact base. Utility without truth is manipulation.
2. **LM-actionable (D-041):** Every sentence must change how an AI responds. Truth without utility is self-portraiture.

This resolves the D-037 tension. D-037 prohibited "prescriptions and AI instructions" to prevent prompt-script behavior. But interaction directives grounded in behavioral patterns are valid. They are behavioral data expressed in an actionable format. The valid directive test: a directive is valid if and only if it follows from a behavioral pattern stated in the same block.

#### Behavioral Modeling, Not Fact Retrieval

The identity block uses **behavioral predictions**, not fact retrieval. LLMs are probability machines. Raw facts ("likes coffee, works in tech") require the model to infer behavior. Behavioral predictions ("rejects shortcuts that sacrifice quality, even under pressure") skip that inference step entirely. The model directly weights predictions against the current conversation. This reduces the inference chain between context and response.

**Predictions compose.** Orthogonal behavioral predictions combine to produce appropriate responses in situations none of them individually anticipated. Two or three predictions intersecting can generate novel, contextually precise behavior from the model — behavior that was never explicitly described in the identity block. This composability is the mechanism by which the system produces responses that feel like genuine understanding rather than retrieval. Measurable via the evaluation protocol: does the model generate contextually appropriate responses that go beyond what any single prediction describes?

The identity block functions as a **Markov blanket**, the boundary layer between the person and the AI. The reasoning model can only "see" the user through this membrane. Everything inside (raw facts, embeddings, extraction history) is hidden. The quality of the boundary determines the quality of the interaction, which is why the identity layers receive the largest token allocation in the brief.

#### Authoring Constraints

Identity blocks are **authored via API** (Sonnet for generation, Opus for composition), under **blind derivation** (D-040), from raw facts and philosophy frameworks only, with no prior blocks, no analysis documents, and no template carry-forward. This prevents the cognitive anchoring that caused 7 generations of identity blocks to converge on 3-4% coverage of the fact base.

**Empirical budget (D-042):** The original 1,500-2,600 token budget was a heuristic that calcified into a constraint. Token allocation is now determined empirically through optimization study: generate blocks at multiple token levels, evaluate interaction quality, find the knee of the curve where additional tokens stop improving responses. Quality per token is the metric.

**Session 38b (axiom refinement + authoring validation) validated the authoring pipeline.** Iterative Collective review (a multi-agent adversarial review process where four AI personas evaluate identity layers) drove ANCHORS from 61% → ~88%, CORE to 77.3%, PREDICTIONS to 76.8%. The key insight (D-046): prompt quality is the leverage point for quality at scale. Each Collective content addition signals a missing prompt question. Fixing the prompt (cheap) reduces review burden (expensive). Over iterations, the cheap layer handles more and the expensive layer handles less. All Session 38b prompt improvements — D-041 filter, anti-redundancy, detection signatures, domain balance, inter-axiom conflict resolutions — are codified in `author_layers.py` for automatic application. Category cap (max 15 facts per category) in retrieval queries prevents topic domination.

*Session 79 Ablation Update: The Collective-driven authoring model described above was superseded by Session 79 ablation findings. A 14-condition study on the Benjamin Franklin corpus showed C11 (3-layer authoring without Collective review) = 87/100 vs C0 (full pipeline with Collective) = 83/100. The prompt improvements from Session 38b remain codified and load-bearing — they are what make the cheap layer sufficient without Collective review. The Collective itself is no longer part of the default pipeline.*

**Division of labor:** The memory system models the person with honest confidence metadata. The reasoning model decides what's relevant per conversation. The system should err toward complete representation with uncertainty signals rather than pre-filtering. The memory system provides; the reasoning model interprets.

**Behavioral data, not behavioral prescriptions (D-037).** The identity block provides behavioral data about the person — knowns, unknowns, predictions, and certainties. It does NOT provide instructions for how the AI should respond. The distinction matters because prescriptions constrain the model to a fixed playbook, while behavioral data lets the model compose novel responses across contexts no prescription anticipated. The job is not to tell the probability machine how to predict — it is to give it the supporting evidence and context to predict well. See the full Design Philosophy below.

---

### 6. Confidence Over Deletion, Contradiction Over Decay (D-021, expanded Session 20)

**Knowledge is never deleted, only confidence-adjusted. Staleness is detected by contradiction, not by elapsed time. The system models a confidence landscape, not a truth table.**

Even contradicted or outdated facts carry provenance value. "You used to wake at 5:30am for pre-market trading" is biographical truth even after it's no longer current. Deleting it destroys the trajectory. The system should represent what it knows, what it used to know, and how confident it is in current accuracy, not decide what's "true" and discard the rest.

This applies at every level:
- **Contradicted facts** transition to historical with reduced confidence in current accuracy, but remain in the knowledge base
- **Superseded facts** are linked to their replacements, preserving the evolution chain
- **Corrected facts** are the highest-confidence signal: the user explicitly said what's true

Measurable constraint: no pipeline operation should permanently remove a fact from the database. Archival, confidence reduction, and historical reclassification are valid. Deletion is not.

**Contradiction over decay is fully validated.** Philosophy research across six frameworks (Frankfurt, Taylor, Ricoeur, Parfit, Korsgaard, MacIntyre) confirmed that silence does not equal irrelevance and that time elapsed is not a relevance signal. The system uses no TTL (time-to-live), no access-frequency scoring, and no recency-based deprioritization. A fact becomes stale when a newer fact contradicts it — not when a calendar threshold is crossed. This is not an optimization choice; it is an epistemic commitment validated by both philosophical analysis and empirical observation.

**The system does not impose limits on what might be relevant.** Blanket score penalties, arbitrary time thresholds, and silent deprioritization are epistemic overreach, the system asserting certainty about relevance that it does not have. Where confidence is low, the system flags uncertainty and lets the reasoning model or the user decide.

---

### 7. Silence Is Not Evidence of Irrelevance (Session 20)

**Conversation frequency reflects what someone uses AI for, not what matters to them.**

The system's data comes from conversations. But the person exists outside of conversations. A person may never mention their spouse, their pets, their parents, or their health in a technical AI session. That absence carries zero signal about importance. The system must not conflate "not mentioned recently" with "less important."

Measurable constraint: no retrieval or scoring mechanism should penalize facts based solely on time since last mention. Time since last mention is metadata, not a relevance signal.

This is a direct application of Inherent Incompleteness (Level 1: structural blindness to who you are when you're not talking to an AI).

**Tension with practical staleness (acknowledged):** While the principle holds — silence ≠ irrelevance — topic dominance in retrieval is a real practical problem. Facts from heavily-discussed domains (e.g., trading) can crowd out equally important facts from less-discussed domains. The planned solution (recency weighting in retrieval via decay multiplier) is framed as a **retrieval tuning optimization**, not a principle revision. It addresses topic dominance in retrieval without changing tier classification or implying that older facts are less important. The principle constrains the implementation: decay can lower retrieval priority, but cannot lower tier classification, significance score, or knowledge_tier.

---

### 8. User as Highest Authority (D-019, D-021)

**When the system disagrees with the user about who the user is, the system defers, but it doesn't discard what it observed.**

The identity review (D-019) proved this: no synthetic benchmark, no embedding similarity score, no confidence threshold can substitute for the person themselves saying "that's wrong about me." The user's corrections are the highest-authority signal in the system, above LLM confidence, above vector similarity, above recurrence.

The correction propagation system (D-021) operationalizes this: corrections are stored permanently, survive resets, and block re-extraction of the same wrong facts. "Fix Once, Fixed Forever."

**But authority has layers.** The collective review (D-024) identified three types of corrections that deserve different treatment:
- **Factual corrections** (citizenship, names, dates): user is always right, always accept, discard the old data
- **Self-characterization corrections** ("I don't really care about X"): accept and record the self-assessment, but the behavioral evidence (40 conversations about X) stays as a separate signal. The brief can hold both.
- **Dispositional corrections** ("I'm not impulsive"): accept the self-concept, but when behavioral evidence contradicts it, note the tension, because that tension is itself revealing

This is not about overriding the user. It's about the three-truths model: who you think you are, who others think you are, and what the data shows. All three are valid. The user has final say on what goes in the brief, but the system should surface contradictions rather than silently resolving them.

**Why this matters:** A memory system that argues with you about your own life isn't useful; it's adversarial. But a memory system that only tells you what you want to hear isn't useful either; it's a flattering mirror. The goal is honest, respectful reflection.

---

### 9. Generative Output Isolation (D-040)

**Generative outputs must not feed back into their own inputs. Every generation must be derived from primary data, not from prior generations.**

This principle addresses a failure mode discovered empirically: identity blocks authored with access to prior blocks converge toward the prior content rather than the underlying data. Over 7 generations, 70-75% of text was inherited, zero genuinely new behavioral predictions were created, and coverage of the identity-tier fact base stagnated at 3-4%. The authoring process was editing inherited text rather than synthesizing from facts.

The mechanism is cognitive anchoring. When a prior generation is available, it acts as a gravitational center. The author's effort goes toward editing the prior text rather than re-deriving from data. This produces blocks that are accurate (the inherited text was correct) but narrow (the inherited text covered a tiny fraction of available knowledge). Accuracy without coverage is a failure mode the system must actively prevent.

**The rule:** Any process that generates a compressed representation of the fact base (identity blocks, character overviews, analysis documents) must receive its input exclusively from the primary data source (facts, embeddings, raw conversations) and authorized structural frameworks (philosophy, design principles, format specifications). It must NOT receive prior outputs of the same process.

**Contamination vectors are transitive.** If Document A was derived from a prior identity block, and Document B summarizes Document A, then Document B carries the prior block's phrasings indirectly. The exclusion applies not only to prior blocks but to any document that absorbed their content: analysis docs, review docs, session summaries, progress notes that describe block content.

**Contamination is measurable.** Session 37 measured contamination vector 1 (project language leaking into personal facts) at 0/3,898 facts (zero contamination). The existing AUTHORING_EXCLUSION_PATTERNS in config.py are sufficient. Contamination vector 2 (personal identity facts trapped in project-scoped sessions) requires a message-level classifier, not conversation-level filtering.

**Verification is mandatory, not optional.** Every new generation must be mechanically checked against prior generations for text overlap (n-gram analysis), coverage of the primary data source, and proportion of genuinely novel content. These checks are automated and must pass before the output is stored or reviewed.

**What this means in practice:**
- Identity block authoring receives raw facts, philosophy frameworks, design principle constraints, and token budgets. Nothing else.
- Facts that reference previous identity blocks or the block creation process itself must be filtered from the authoring data view. Meta-facts about the system's own outputs are contamination vectors.
- User feedback is transmitted as evaluative criteria ("cover self-concept, worldview, tension architecture, epistemic anchors") not as references to prior block content ("the last block was too narrow because it said X").
- Analysis documents are re-derived from facts periodically, not maintained as living documents that accumulate block phrasings.
- Automated validation gates (overlap < 25%, coverage > 5%, novel claims > 0) prevent storage of inherited blocks.
- Structure is not templated. If every block has the same headers and the same prediction count, the template is the anchor. Structure should emerge from content.
- Each identity layer (ANCHORS, CORE, PREDICTIONS) is independently blind-authored from its own fact queries; isolation applies within the three-layer architecture, not just between generations.

**This principle is broader than identity blocks.** It applies to any generative loop in the system: character overviews, analysis documents, autobiography pipeline outputs, eval protocol responses. Wherever the system generates a compressed representation and then uses that representation as input to the next generation, this principle applies.

---

### 10. Scoped Memory (D-044)

**Facts are tagged by interaction mode. The scope of a conversation determines where its knowledge flows. Not every fact feeds every output.**

A person interacts with AI in different modes: as themselves (personal), as a technical lead (project), as a professional (professional). These modes produce different kinds of knowledge, and that knowledge serves different purposes. Personal-scope facts feed identity blocks. Project-scope facts feed project briefs (CLAUDE.md). Professional-scope facts will feed professional profiles. Mixing scopes produces contamination — project-meta facts ("the extraction pipeline uses Qwen") appearing in personal identity blocks, or personal identity facts being extracted from project sessions where they appear only as injected context.

**Scope is determined by the interaction context and relationship, not by subject matter.** A person discussing their management philosophy in a personal conversation produces personal-scope facts. The same person demonstrating that philosophy in a code review session produces project-scope facts. The content may overlap; the scope differs because the interaction mode differs.

**Cross-scope recurrence validates anchors.** The strongest mechanism for identifying epistemic anchors is cross-scope recurrence — when the same behavioral pattern appears independently in personal conversations, project sessions, and professional interactions. If "directness" surfaces in relationship discussions, code reviews, and trading decisions, that is structural evidence from independent interaction modes that the trait is foundational. The scopes are the test environments. Recurrence across them is the evidence.

**Why this matters:** Without scope separation, the system conflates what a person is building with who a person is. A memory system that tells the AI "this person values clean code and iterative testing" because they said so in a project session is reporting project methodology, not personal identity. The distinction is not pedantic — it is the difference between a system that models the person and a system that models the person's current project.

---

### 11. Falsification Over Assertion (D-045)

**Axioms are validated by searching for counter-evidence, not by accumulating supporting evidence. If a belief claims to be foundational, its negation should not be observable in the fact base.**

Epistemic anchors — the core axioms in the ANCHORS layer — claim to be universally true for the individual across all domains. A claim that strong requires a validation method that strong. Accumulating supporting evidence is insufficient because confirmation bias selects for it. The system uses Popperian falsification: generate the negation of the candidate axiom, search the fact base for evidence of the negation, and classify any matches.

The classification is critical: not all counter-evidence is equal.
- **Violations** — The axiom holds, but the individual broke it under pressure. Trading spirals don't refute a commitment to rational analysis; they are predicted failures of a commitment the person genuinely holds. Violations become material for the PREDICTIONS layer.
- **Refutations** — The axiom doesn't actually hold in some domain. The individual genuinely valued or endorsed the negation. Refutations require narrowing or rejecting the axiom.

If all counter-evidence is violations, the axiom is validated. If any counter-evidence is a refutation, the axiom needs revision. This distinction prevents the system from rejecting genuinely foundational beliefs just because the person sometimes fails to live up to them — which is the human condition, not a data error.

---

### 12. Cheap Constraint, Expensive Discrimination (D-046)

**Maximize the work done at the cheap layer so the expensive layer handles only genuinely hard cases.**

The system uses cheap operations (extraction, clustering, semantic search, checklists, Haiku, Qwen) to constrain the generation space, and expensive operations (Opus judgment, Collective review, human review) only to discriminate within the remaining ambiguity. This is not a cost optimization preference — it is a scalability architecture. If the expensive layer routinely generates content that the cheap layer should have produced, every pipeline run requires an expensive non-deterministic review step. That doesn't scale to multiple users.

The key insight: generation prompt quality determines review cost. Every content addition the Collective makes during review is a signal that the generation prompt was missing a question. The fix is to improve the prompt, not to always run the Collective. Over iterations, the cheap layer handles more and the expensive layer handles less. The Collective's role evolves from "generate missing content" to "validate nothing was missed."

**Session 79 Ablation Update:** The Collective review step was tested in a 14-condition ablation study on the Benjamin Franklin corpus. Result: C11 (3-layer authoring without Collective review) scored 87/100 vs C0 (full pipeline with Collective review) at 83/100. The Collective was proven ceremonial and removed from the default pipeline. The cheap/expensive principle remains architecturally valid — the 3-layer authoring structure (ANCHORS → CORE → PREDICTIONS) is load-bearing (C13 single-layer = 83 vs C11 three-layer = 87). The expensive discrimination now happens within the layer structure itself: each layer is a progressively harder synthesis task, with PREDICTIONS requiring the most judgment. The Collective was the wrong implementation of the principle — it applied expensive review after the work was done, rather than structuring the work so that cheap layers constrain what expensive layers must produce.

---

## Design Philosophies

### Simplicity Over Cleverness (D-018)

Every time complexity has been added to the extraction prompt, results got worse. Every time we kept the LLM's job simple and handled complexity in post-processing, it worked. This is now a tested principle, not an opinion:

- Simple prompt, free-form fields, post-extraction normalization = good
- Complex prompt, enum constraints, multi-task instructions = Qwen gives up

**Applied broadly:** If there's a simple way and a clever way, pick the simple way. It's more debuggable, more maintainable, and — empirically — produces better results with local models.

### Output Evaluation Over Method Evaluation (D-019)

Don't check the code. Check whether the result makes sense to the person it's about.

"I've never used an iron condor" is a better test than any unit test. "Eczema belongs to my wife, not me" catches a class of bugs that no automated evaluation would find. The person is the test suite.

### Corrections Are Data, Not Failures (D-021)

When the user corrects something, it's not a bug report — it's *information*. Corrections are signal about what matters, what's wrong, and how the system should change. They're a permanent part of the knowledge base, not a one-time patch.

### Batch Changes, Clean Runs (D-022)

Partial fixes create inconsistent datasets. When multiple improvements are needed, batch them into one clean re-run rather than applying incremental patches. One 6-hour run with 9 fixes is better than nine separate 6-hour runs with one fix each.

### Build Custom, Borrow Patterns (D-001)

Existing frameworks (Mem0, Letta, Titans) each had good ideas but weren't ready for local deployment with data sovereignty. The approach: study what they do well, steal the patterns, build the implementation from scratch on a foundation we control.

- AUDN lifecycle from Mem0
- Surprise scoring from Titans
- Memory blocks from Letta
- Implementation: ours

### Narrative Coherence Over Factual Completeness (D-024)

**The assembled brief should tell a coherent story, not pass a fact-checking test.**

A list of 50 correct facts about a person is less useful than 200 words that capture their trajectory, tensions, and what they're trying to figure out right now. The system doesn't succeed when it accurately stores and retrieves individual facts. It succeeds when the brief creates a representation that makes the AI respond as if it *understands* — not just what you know, but who you are.

The three-layer architecture (D-043) operationalizes this. Each layer provides a different kind of coherence:
- **ANCHORS** provide epistemic coherence — the fixed premises the person reasons from, so the AI doesn't waste cycles re-establishing what the person considers settled
- **CORE** provides narrative coherence — arc, tensions, turning points, the trajectory that connects biographical facts into a story
- **PREDICTIONS** provide behavioral coherence — situation-specific patterns that tell the AI what to expect, grounded in observed behavior

Facts are building blocks. The layers are architecture. The brief must cohere across all three.

### Behavioral Data Over Behavioral Prescriptions (D-037, refined D-041, Session 24/36)

**The identity block provides behavioral data — not instructions for how the AI should respond. The job is not to tell the probability machine how to predict. The job is to give it the evidence and context to predict well.**

LLMs are probability machines. Given accurate behavioral data about a person, a capable model will infer the appropriate response — and will do so flexibly across novel contexts that prescriptions cannot anticipate. The identity block is input to the model's prediction engine, not a script for the model to follow.

The distinction:
- **Behavioral data (correct):** "Emotional processing happens through mechanical analysis, not alongside it. Frustration after rule violations turns inward and compounds."
- **Behavioral prescription (wrong):** "Do not redirect to emotional support. Help trace which rule broke and why. Treat the spiral as diagnostic, not emotional."

The first gives the model accurate priors about how the person works. The second tells the model what to do. Both produce reasonable AI behavior in anticipated situations. Only the first produces appropriate behavior in unanticipated situations — because the model can reason from the data rather than pattern-match against instructions.

**D-041 refines this distinction.** Interaction directives grounded in behavioral patterns are valid — they are behavioral data expressed in an actionable format. "When you break your own rules, the frustration turns inward. Do not minimize what happened. Help trace which rule broke and why." is valid because the directive follows from the behavioral pattern. "Always respond in bullet points" is invalid because it is a prompt script with no behavioral grounding. The test: a directive is valid if and only if it follows from a behavioral pattern stated in the same block.

**Why prescriptions fail at composition:** Prescriptions don't compose. "Don't minimize" and "don't lecture" and "stay in the mechanics" are three discrete instructions. If the model encounters a situation involving all three plus a novel element, it has a rule-following problem, not a prediction problem. Behavioral data composes because the model can weight multiple data points against the current conversation and generate responses appropriate to situations none of the data points individually describe. This is the same composability that makes behavioral predictions powerful (Principle 5) — but it only works when the predictions are data, not directives.

**What the identity layers should contain:**
- **Axioms** — epistemic commitments the person reasons from, stated as probabilistic certainties (ANCHORS layer)
- **Knowns** — verified behavioral patterns, confirmed biographical facts (CORE layer)
- **Unknowns:** acknowledged gaps, areas of uncertainty, things the system hasn't observed
- **Predictions:** behavioral tendencies stated as situation→pattern→directive (PREDICTIONS layer)

**What the identity layers should NOT contain:**
- **Opinions:** editorial judgments about the person's choices ("you're right to hold it")
- **Portraits:** literary descriptions of the person that don't change AI behavior ("notices strangers walking too close at Costco")
- **Framework attributions:** philosophy framework names in output ("Frankfurt would call these volitional necessities")
- **Response scripts:** step-by-step instructions for AI behavior ungrounded in observed patterns
- **Evaluative validation:** the system endorsing the person's self-narrative

The theme block (facts) and episode block (recent context) provide the situational specifics. The identity layers provide the stable behavioral framework. Together, they give the model everything it needs to predict well, without constraining how it predicts.

### The System Is a Mirror, Not an Oracle

The memory system reflects what it's learned about you back at you. It's a high-quality dossier that enables an AI to simulate the feeling of being known. That is genuinely valuable, and it is honest to call it what it is.

It can be wrong. It can be incomplete. It can show you things about yourself you didn't expect. But it can never show you everything. And it should never pretend that data about you is the same as knowing you.

The person looking in the mirror always knows more than the mirror does. But a mirror that can also show you your best self, not just your current state, is more than a reflection. It's a tool for growth.

---

## Anti-Patterns (What We Explicitly Avoid)

1. **Claiming certainty.** No fact, no profile, no summary should be presented as definitely true. Confidence is always qualified.

2. **Conflating data with identity.** What someone said in a conversation is not the same as who they are. Asking about something is not doing it. Mentioning something is not valuing it. A collection of facts is a census, not a biography.

3. **Treating completeness as achievable.** More data, better models, and longer extractions will improve the system, but will never make it complete. The asymptote is "useful approximation," not "full knowledge."

4. **Silently resolving contradictions.** When self-report conflicts with behavioral evidence, the system should surface the tension, not pick a winner. Conflicting truths are data, not errors.

5. **Passive-only learning.** A system that only learns when you happen to mention something will always have gaps. Active probing (asking questions, identifying what's missing) is a feature, not a nice-to-have.

6. **Context stuffing.** More tokens in the brief is not better. A focused brief outperforms a token dump because it forces prioritization. The system should act like a librarian, not a filing cabinet. The right budget is determined empirically (D-042), not by assertion.

7. **Assuming uniform temporal behavior.** People change, but not uniformly. States (habits, routines, current projects) can become outdated. Events (marriage, founding, loss, achievement) are permanently valid and accrue meaning over time. The system must classify facts before applying temporal logic. Staleness is detected by contradiction (a newer fact conflicting with an older one), not by time elapsed.

8. **Listing facts instead of telling a story.** The brief should create narrative coherence (arc, tensions, turning points), not recite attributes. A dossier feels like surveillance. A narrative feels like knowing.

9. **Ignoring the best version.** The system should not only model who you are now. It should identify patterns of peak performance, clarity, and growth, and make that knowledge available. Not prescriptively, but informatively.

10. **Writing portraits instead of instruments.** An identity block that describes a person beautifully but doesn't change how the AI responds is self-portraiture, not a behavioral model. Every sentence must pass the LM-actionability test (D-041). Literary quality is not a proxy for utility.

11. **Mixing scopes.** Project-meta facts ("the pipeline uses Qwen") have no place in personal identity blocks. Personal identity facts have no place in project briefs unless they are cross-scope anchors validated by independent recurrence. Scope contamination produces blocks that model the person's current project, not the person.

12. **Confirming axioms instead of falsifying them.** Accumulating supporting evidence for a candidate axiom proves nothing; confirmation bias selects for it. The system validates axioms by searching for counter-evidence and classifying it as violation (the axiom holds, the person failed to follow it) or refutation (the axiom is wrong). Only falsification produces justified confidence.

---

### Contradiction Judgment Principles (D-036, Session 23)

**Six principles abstracted from blind validation of the contradiction detection system. These govern how the system judges whether two facts contradict, coexist, or require further information.**

These principles emerged from testing real fact pairs against human judgment. They define the epistemic boundaries of automated contradiction detection and constrain the system's behavior to avoid false positives, declaring contradiction where none exists.

1. **Claim Type Asymmetry.** Facts on different epistemic planes (descriptive vs. aspirational) coexist by default. "I am a trader" and "I want to become a fund manager" are not in tension; one describes current state, the other describes intent. The system must identify the epistemic plane of each fact before comparing content.

2. **Temporal Order Dependence.** Ordering is required input to judgment, not optional metadata. "Wakes at 5:30am" followed by "Wakes at 7am" is a state change. Without knowing which came first, the system cannot determine which is current. Temporal order is a prerequisite for contradiction detection, not a supplementary signal.

3. **Scope Resolution.** Confirm same entity/scope before comparing content. "Spouse has eczema" and "User has dry skin" are not contradictions; they describe different people. "Trades SPY options" and "Trades futures" may not contradict if the user trades both. The system must verify that two facts refer to the same entity, the same scope, and the same dimension before evaluating contradiction.

4. **Context-Bound Truth.** Some fact pairs are indeterminate in isolation and require external knowledge to judge. "Lives in Dubai" and "Lives in Toronto" could be a contradiction (moved) or coexistence (dual residence). The system cannot resolve this without additional context. When context is insufficient, the correct output is "indeterminate," not a forced judgment.

5. **Stated vs. Enacted Gap.** The system stores claims, not verified behaviors. This is an irreducible epistemic limit. "I exercise daily" is a self-report. The system has no way to verify whether it is true. Two self-reports that appear contradictory ("I'm disciplined" and "I procrastinate") may both be accurate descriptions of different domains. The system should hold both rather than resolving the tension.

6. **Binary Collapse Resistance.** Default to conservative/ambiguous; contradiction is reserved for unambiguous reversals. Most fact pairs that look like contradictions on the surface are actually enrichments, clarifications, scope differences, or temporal updates. The system should require strong evidence before classifying a pair as contradictory. When in doubt, the answer is "not a contradiction," since false negatives are recoverable, false positives destroy valid knowledge.

**Operational implication:** These principles constrain the MiniLM filter + Sonnet/Opus judge pipeline. The embedding filter surfaces candidate pairs; the judge applies these principles to determine the relationship. The judge's default disposition is conservative: coexistence unless contradiction is unambiguous.

---

### The Ghost Layer (D-025, superseded by D-026)

**The system encodes beliefs about human significance as invisible priors: weights, constants, and structural decisions that shape output without being visible in it.**

The original Ghost Layer (D-025) attempted to implement this through a composite scoring formula with per-fact weights: category hierarchy, subject multipliers, temporal weights, intent weights, and significance type weights. This produced a single score per fact that blended data signals with philosophical priors.

**Why it failed (D-026):** The data inputs to the formula (significance, confidence, recurrence) turned out to be effectively flat (94% of facts scored "High" significance, 83% got confidence 1.0). This made the ghost weights the *only* differentiating signal, which meant the category hierarchy (relationship=12 vs project=4) dominated everything. Result: "spouse's dry skin" outranked "founded a startup." The ghost layer was working; it was just working at the wrong level.

**The fix (D-026 — Identity Cluster Framework):** Ghost priors now operate at the *topic level*, not the *fact level*. Ten universal identity clusters — who you are, who you love, what you've built, what you've lost, what drives you, what you believe, what you struggle with, how you operate, where you're headed, what's unresolved — define what dimensions matter about a person. Within each cluster, semantic retrieval finds the best representative facts. The philosophy is in the cluster design; the selection is empirical.

The ghost philosophy remains the same:
- **Universal, not personal.** Every person has losses, relationships, struggles, and aspirations. The 10 clusters are about the human experience, not about any one person's data.
- **Invisible in output.** The brief doesn't explain why "what you've lost" gets its own cluster. It just allocates space for it. The philosophy is documented here; the code is just a config dict.
- **Tunable but principled.** Clusters can be added, merged, or reweighted. But each should represent a genuine dimension of human identity, not an arbitrary grouping.

The key lesson: ghost priors should shape *what the system asks about*, not *how it ranks individual answers*. "What are the most important relationships in this person's life?" is a ghost-level question. Whether fact #2847 scores 7.3 or 6.9 is an implementation detail that shouldn't carry philosophical weight.

The three-layer architecture (D-043) extends this principle further: the layers themselves (ANCHORS, CORE, PREDICTIONS) embody ghost-level assumptions about what dimensions of a person matter. The decision that epistemic commitments deserve their own layer, separate from biographical overview and behavioral patterns, is a philosophical claim about the structure of identity. The claim is that identity has layers, and the choice of layers is the deepest ghost prior in the system.

---

### Emotional Attachment to Non-Human Entities (D-026 insight)

**Relationships are not limited to humans. Emotional bonds with companies, projects, pets, places, and creative works can carry the same psychological weight as bonds with people.**

The extraction model classified a startup as a wife because the emotional signature (founding, nurturing, losing) matched the pattern of a human relationship. The user's correction wasn't "the startup isn't important" but rather "it IS a relationship, regardless whether or not it's a human or another living being."

This has design implications:
- The "who you love" cluster includes pets. The "what you've lost" cluster includes companies and projects. These aren't category errors; they're recognitions that emotional attachment isn't species-specific.
- The system should not assume that only human relationships carry relational weight. A startup founder's bond with their company, an artist's bond with their work, a person's bond with their pet: all of these can be identity-defining.
- Loss of a non-human entity (company shutdown, pet death, career ending) can be as formative as loss of a human relationship. The system should treat it accordingly.

---

### Organic Probing Over Formal Questioning (Identity Review v2)

**The deepest truths about a person come out unprompted, in fragments, during natural conversation, not in response to direct probing.**

Identity review v2 proved this empirically. "She is the love of my life, I care about her more than anything" — the strongest relationship sentiment captured in the entire system, came out during a correction, not during probing. A pet's name surfaced the same way. Meanwhile, "describe your relationship with your spouse" was characterized as "too big an ask."

This shapes active probing design (D-020):
- **Organic > formal.** Don't ask 10 questions at session start. Weave questions naturally into conversation.
- **Big asks fail.** "How would you describe your relationship?" produces resistance. But corrections like "she is the love of my life" produce the richest data.
- **Fragments > summaries.** People reveal themselves in asides, corrections, and reactions, not in structured self-reports.
- **Setup sessions feel like interrogations.** Even well-intentioned probing at scale feels like a survey, not a conversation.

---

### Conversation Probes: Active Gap-Filling (Concept, Session 19)

**The system should be aware of its own knowledge gaps and use conversation to fill them organically.**

Three types of probes were identified (Session 19):
1. **Knowledge gap probes:** clusters with few facts or low recurrence. "You've mentioned trading a lot but I don't actually know what you primarily trade — is it mostly SPY?"
2. **Staleness probes:** facts flagged as outdated. "You used to wake up at 5:30 for pre-market — is that still your routine?"
3. **Depth probes:** surface facts exist but motivations/feelings are missing. "You've talked about what happened with your previous startup — how do you think about that experience now?"

Implementation guidance from the Collective (Cognitive Scientist):
- Max one probe per conversation; more feels like interrogation
- Use hypothesis-confirming phrasing: "I've noticed X — is that because Y?" not open-ended "Tell me about X"
- Gate probes by conversational relevance: only probe topics related to the current conversation
- All clusters represent fundamental human dimensions, with no hierarchy of significance
- After a probe yields information, immediately demonstrate use of it in the same conversation

This extends the "Organic > Formal" principle: probes should feel like genuine curiosity from a friend, not intake questions from a clinician.

*Not yet implemented. Saved for a future session.*

---

### Journal Input Over Conversation History (Session 38 Finding)

**Self-reflective writing produces better identity data per fact than reactive conversation.**

The journal experiment validated this empirically: 139 journal-derived facts produced identity layers that scored higher than User A's 3,927 conversation-derived facts on multiple dimensions. Journal writing is inherently self-reflective — the writer is already abstracting, synthesizing, and evaluating their own experience. Conversations are reactive — the user responds to prompts, asks for help, processes information in real time. The self-reflection in journal writing is closer to what the identity authoring pipeline needs: pre-abstracted, emotionally grounded, identity-relevant data.

**Implications:**
- Journal-first onboarding for new users would produce richer initial identity layers than conversation import
- Active probing (D-020) should encourage self-reflective responses, not just information extraction
- The quality gap between User A's CORE (77.3%) and Subject B's CORE (63%) is driven by data volume, not data quality. Subject B's thin biographical base from 8 entries limits coverage, but the per-fact quality is higher

---

---

### Evidence Not Opinion: Mechanical Evaluation Over Judge Scoring (Session 77+, D-073)

**Evaluation of identity compression must be mechanically verifiable, not subjectively scored. If a human can't audit the claim, it's not evidence.**

The original evaluation framework relied on LLM-as-judge scoring across subjective dimensions (voice authenticity, calibration quality, depth). This approach has two fatal problems:

1. **LLM judges conflate dimensions.** PersonaGym (2024) found LLM judges scored 4.0+ on Linguistic Habits when human evaluators scored 2.0. The judge can't reliably distinguish "sounds right" from "reasons right."

2. **Voice is not the goal.** The brief's purpose is not to make the AI sound like the person; it's to make the AI understand how the person thinks. The evaluation must test reasoning influence, not stylistic mimicry.

The replacement framework (Provenance-Traced Evaluation) uses four mechanical layers where every score traces to a verifiable artifact:
- **Brief Activation:** Vector similarity between response segments and brief claims (MiniLM, auditable)
- **Provenance Coverage:** What fraction of response claims trace to brief material above threshold (auditable)
- **Reasoning Chain Reconstruction:** Does the model's framework_applied match brief axioms, not just generic advice (auditable via JSON decomposition)
- **Priority Ordering:** Does the response emphasize what the brief emphasizes (auditable via rank comparison)

$0 cost. Human-reviewable. No LLM judge in the loop for the mechanical layers. This is the standard going forward.

**Corollary: C2 is the true baseline, not C1.** C1 (no brief) vs C5c (brief) tests whether more information beats less information, an obvious result. C2 (raw facts from the same pipeline) vs C5c tests whether compression adds reasoning value given access to the same underlying data. This is the real experiment. (D-074)

---

### Fidelity Creates Vulnerability, And That's Correct (Session 77+, from Benjamin Franklin DRS)

**A faithful identity model increases adversarial surface area. This is a feature of accuracy, not a flaw in the system.**

The Benjamin Franklin DRS (Dialectical Robustness Score) benchmark revealed a paradox: the briefed model (C5c) scored LOWER on adversarial resistance than the unbriefed model (C1). The brief preserved Franklin's genuine self-doubt about vanity — so when an adversarial frame asked "is your frugality actually vanity?", the briefed model engaged deeply because the brief told it this was a real tension Franklin held. The unbriefed model deflected because it lacked the internal complexity to be vulnerable.

This means current persona stability metrics (including our own DRS) penalize fidelity. A caricature (a simplified, consistent persona without internal tensions) scores higher on stability because it has fewer exploitable handles. But it's a worse representation.

Faithful representation of a person includes their tensions, contradictions, and failure modes. Ricoeur's idem/ipse dialectic: identity is not the absence of contradiction but the ongoing negotiation of it. A brief that smooths over genuine tensions to score well on stability metrics has failed at its actual job.

**Implication for brief structure (D-075):** The brief should not just describe WHO (behavioral patterns) but also WHERE IT BREAKS: the conditions under which axioms collapse, the failure modes, the blind spots. This makes the brief more vulnerable to adversarial exploitation AND more faithful to the subject. These are the same thing.

---

*Updated: 2026-03-09 (Session 82) | Refreshed Session 39*
*Session 20 raw notes: `docs/core/SESSION_20_NOTES.md` — unprocessed intellectual threads on temporal processing, probability framing, startup alignment, Markov blankets, context for humans*
