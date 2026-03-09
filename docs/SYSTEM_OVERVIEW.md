# Base Layer: The Identity Layer on Top of Memory

Memory today is broadly flat. It is a drawer full of facts. It is context, but it is not understanding.

This is not a criticism. The memory systems shipping today — ChatGPT Memory, Claude Memory, Mem0, Supermemory, Zep — are genuinely good at what they do. Supermemory hits 81.6% on LongMemEval with sophisticated retrieval: temporal metadata, relational versioning, hybrid search. Claude Memory categorizes and dates facts. Mem0 does graph-based retrieval. These are real engineering achievements solving a real problem: contextual recall.

But there is a gap. Memory gives the model facts for the next message. It does not give the model a behavioral model of who you are. "User is a printer" and "User founded a library" are useful context. They are not comprehension. An AI that retrieves those facts knows things about you the way a stranger who read your file knows things about you.

This post is about a system called Base Layer that sits in that gap — an identity layer on top of memory. It reads your conversations, journals, published writing, or even technical documents like patents; extracts structured facts; classifies them by how central they are to identity; compresses them into three layers of behavioral understanding; then collapses those layers into a single narrative brief — roughly 2,000-4,000 tokens — that any AI model can use.

Memory handles "what did we discuss last Tuesday?" Identity handles "how should I frame this advice given who you are?"

These are not competing functions. They are complementary. A model with both memory AND an identity brief is better than either alone. Base Layer does not replace any memory system — it consumes the same raw material (conversations, text) but produces a fundamentally different artifact.

The claim, tested against a formal evaluation: a 3,000-token behavioral brief produces responses that score +0.40 above baseline on identity-sensitive tasks. That is higher than giving the model the full structured extraction. Compression does not just retain signal. It makes it actionable.

Here is how the system works, end to end.

---

## The Stack: Memory Layer and Identity Layer

To understand what Base Layer does, it helps to see where it fits in the stack.

**Memory layer** — stores and retrieves facts. "User is a printer." "User founded a library." "User prefers dark mode." This is what ChatGPT Memory, Claude Memory, Mem0, Supermemory, and Zep do — and they do it well. Sophisticated retrieval with temporal metadata, entity graphs, relational versioning. Context for recall.

**Identity layer** — compresses facts into behavioral understanding. "Tests every principle through implementation before advocating it publicly." "When challenged, responds with counter-questions rather than direct assertions." Instructions for reasoning, not facts for retrieval.

These are different problems. Memory answers "what do I know about this person?" Identity answers "how does this person think?" The first is retrieval. The second is compression.

Most AI personalization today ships at the memory layer. Some do it manually (ChatGPT Personalization — you fill out form fields, set style knobs, paste custom instructions) and some do it automatically (Claude Memory, Supermemory — the model extracts facts from conversations). Both are solving contextual recall. Neither is producing a behavioral model.

Base Layer is the identity layer. It sits on top of whatever memory system you use. The pipeline extracts facts (like memory systems do), but then goes further: it classifies each fact by how central it is to the person's identity, authors epistemic axioms (the pre-set certainties a person reasons FROM), identifies behavioral predictions (when X happens, this person tends to do Y), detects context modes (the different operating states a person enters depending on the domain), and compresses all of this into a narrative brief with provenance chains back to source facts.

Facts are context. A brief is comprehension.

---

## The Pipeline

Base Layer is 14 Python scripts run in sequence. There is no single clever trick. Each step exists because a simpler approach was tried and failed. Here is the full flow, with the interesting parts expanded.

### Step 1: Import

Multi-source ingestion. ChatGPT JSON exports, Claude conversation exports, plain text files, directories of journal entries. The import step normalizes everything into a common schema: conversations and messages in SQLite.

```bash
# Import a ChatGPT export
baselayer import conversations.json

# Import a plain text file (autobiography, journal, blog post)
baselayer import franklin_autobiography.txt

# Import a directory of journal entries
baselayer import ~/journals/

# All data stays local — SQLite + ChromaDB on your machine
```

Data isolation is handled by an environment variable — scripts stay shared, only the data directory changes:

```python
# config.py — data path resolution
# Set MEMORY_SYSTEM_ROOT to point all data paths at a different root
#   export MEMORY_SYSTEM_ROOT=/path/to/other_user
#   baselayer extract  # reads/writes other_user/data/...
```

For the primary test subject, this meant 1,892 conversations totaling 40,997 messages across ChatGPT, Claude Code, and Claude.ai. For Benjamin Franklin's autobiography (used as a public test case), it was a single text file split into 21 chapters. For a patent corpus (30 US patents across 10 technology domains), it was 30 text files imported with document mode enabled.

### Step 2: Extract — Constrained Predicates and AUDN

This is the first interesting step. Extraction uses Haiku (Anthropic's fast, cheap model) to pull structured facts from conversation text. But not free-text facts — structured triples.

Each fact has a subject, a predicate from a constrained vocabulary of 47 canonical verbs, an object, and an optional qualifier. No free-text verbs allowed. The LLM must choose from the list:

```python
# config.py — the full predicate vocabulary
CONSTRAINED_PREDICATES = [
    "owns", "values", "practices", "studies", "prefers", "avoids",
    "works_at", "lives_in", "married_to", "raised_in", "graduated_from",
    "manages", "builds", "trades", "believes", "fears", "enjoys",
    "dislikes", "struggles_with", "excels_at", "identifies_as",
    "maintains", "follows", "aspires_to", "lost", "founded",
    "parents", "experienced", "learned", "decided", "prioritizes",
    "unknown",        # fallback for unmapped predicates
    "attended",       # distinct from graduated_from (attending ≠ graduating)
    "interested_in",  # distinct from follows (passive interest ≠ active tracking)
    "wants_to",       # distinct from aspires_to (want ≠ aspiration)
    "loves",          # distinct from enjoys (intensity matters for commitment_depth)
    "hates",          # distinct from dislikes
    "plays",          # games, sports, instruments
    "monitors",       # active observation, distinct from follows
    "relates_to", "collaborates_with", "mentored_by", "raised_by",
    "friends_with", "reports_to", "admires", "conflicts_with",
]
```

The prompt tells the model exactly what structured output to produce:

```python
# extract_facts.py — the extraction prompt (abbreviated)
"""Extract facts about the USER as structured triples.
Maximize information density — every word should carry meaning.
No hedging language ("seems to", "appears to", "might be").
If uncertain, lower the confidence score instead of hedging in the text.

For each fact, provide:
- subject: Who the fact is about. Use the person's name if known, otherwise "user".
- predicate: MUST be one of: {predicates_str}
- object: The specific value, entity, or description. Be concrete and precise.
- qualifier: Temporal or conditional context.
- category: One of: preference, biography, project, relationship, interest, ...
- confidence: 0.0 to 1.0

Examples of good structured facts:
  {"subject": "user", "predicate": "values", "object": "data sovereignty over cloud convenience",
   "qualifier": "unknown", "category": "value", "temporal": "current", "confidence": 0.9}
  {"subject": "user", "predicate": "founded", "object": "a startup",
   "qualifier": "did not succeed", "category": "biography", "temporal": "past", "confidence": 0.85}
"""
```

Why constrain the predicates? Because without constraints, 57% of extracted facts were template language. "The user is interested in data sovereignty and considers it important." With constrained predicates, that becomes `user values data_sovereignty` — shorter, more precise, and actually usable downstream.

Every candidate fact runs through the AUDN lifecycle: Add, Update, Delete, or Noop. The candidate is embedded (MiniLM, 384 dimensions, runs locally), compared against all existing facts by vector similarity, and the system decides what to do based on similarity thresholds:

```python
# extract_facts.py — the AUDN decision logic
def make_audn_decision(candidate_fact, similar_facts):
    if not similar_facts or all(f["similarity"] < 0.3 for f in similar_facts):
        # No similar facts — clearly new, add without LLM call
        return {"action": "ADD", "reasoning": "No similar facts in memory"}

    max_similarity = max(f["similarity"] for f in similar_facts)

    if max_similarity > SIMILARITY_THRESHOLD:  # 0.85
        # Very similar fact exists — ask LLM: UPDATE, DELETE, or NOOP?
        prompt = f'NEW: "{candidate_fact}"\nEXISTING:\n'
        for sf in similar_facts[:3]:
            prompt += f'  "{sf["fact_text"]}" (similarity: {sf["similarity"]:.0%})\n'
        # ... LLM decides
    else:
        # Between 0.3 and 0.85 — add now, defer deduplication for later
        return {"action": "ADD", "reasoning": "Moderate similarity, deferring review"}
```

This is borrowed from Mem0's approach but with tighter thresholds. The optimization matters: below 0.3, no LLM call is needed (clearly new). Above 0.85, the LLM decides (likely duplicate). The middle range gets added and cleaned up in the consolidation step. The result: 4,610 active facts from 1,892 conversations with minimal redundancy.

For long single-message imports like autobiography chapters, the text is auto-chunked on paragraph boundaries with 500-character overlap. Each chunk gets its own extraction pass. AUDN handles cross-chunk deduplication.

**Document mode.** When the source material is not conversational — patents, research papers, published writing — the extraction step can run with `--document-mode`. This reframes the predicate vocabulary for document worldview: the "subject" is the document itself, and facts capture what the document believes, proposes, prioritizes, or avoids. A noise stripper (`_strip_noise_content()`) auto-removes genome sequences, hex strings, chemical notation, and dense numeric data that would confuse the LLM. Rule-based identity promotion then elevates document predicates like `believes`, `values`, `avoids`, `practices`, `prioritizes` directly to identity tier — appropriate because documents are inherently positional (a patent does not casually mention what it believes).

Cost for extraction: roughly $0.01 per conversation using Haiku. Full corpus: under $20. Franklin's autobiography: under $0.50. Patent corpus (30 documents): under $3.

### Step 3: Embed

Every fact and every message gets embedded using all-MiniLM-L6-v2 (384 dimensions, about 80 MB). Runs entirely locally. Vectors stored in ChromaDB. This powers all downstream similarity searches — deduplication, contradiction detection, retrieval for layer authoring.

A subtle bug lived here for months. ChromaDB defaults to L2 distance, not cosine. The conversion formula `similarity = 1 - distance` is for cosine distance. For L2 on normalized vectors, the correct formula is different:

```python
# config.py — single source of truth for distance conversion
def chromadb_dist_to_similarity(dist):
    """Convert ChromaDB L2 distance to cosine similarity (0-1).
    For L2 on normalized vectors: cos_sim = 1 - dist²/2."""
    if dist <= 0:
        return 1.0
    sim = 1.0 - (dist ** 2) / 2.0
    return round(max(0.0, min(1.0, sim)), 4)
```

With the wrong formula, provenance similarity scores were ~0.003 (useless). With the correct formula: ~0.54. Six files across the codebase were using the wrong conversion. This is the kind of bug that does not cause failures — everything runs, the numbers are just silently wrong.

### Step 4: Score

Significance scoring. Two signals: recurrence (how often does this topic appear across conversations?) and depth (how much engagement surrounds this fact?). Raw recurrence is windowed — 20 mentions in one day counts as 1 windowed recurrence, not 20. This prevents a single intense conversation from inflating a topic's significance score.

A hard lesson here: modifying the scoring algorithm without re-running all scores corrupts everything downstream. The system once had a coffee fact with a recurrence count of 677. The correct value was 14. Every tier classification and layer generation downstream was built on that corrupted score. Now there is a rule: if `score_facts.py` changes, full re-scoring is mandatory.

### Step 5: Classify

Haiku classifies each fact along two dimensions: fact type (biographical, behavioral, positional, preference) and commitment depth (factual, preference, position, conviction). These determine which layer a fact feeds into.

Biographical facts go to CORE (communication and operating context). Behavioral facts go to PREDICTIONS. Positional/conviction facts go to ANCHORS.

### Step 6: Tier

This is the step that separates identity-significant facts from context noise. Sonnet (a mid-tier model, good at discrimination) classifies each fact into one of three knowledge tiers:

- **Context** — true but not identity-defining. "User asked about Python syntax." This is most facts.
- **Situational** — relevant in certain contexts but not core. "User is learning Japanese."
- **Identity** — central to who the person is. "User values data sovereignty as non-negotiable." These are the facts that feed into the behavioral brief.

The distribution after classification: roughly 58% identity, 22% situational, 20% context. The identity tier is deliberately generous — better to include a fact that turns out to be marginal than to exclude one that matters.

A subtle bug surfaced here with historical texts. The tier classifier used a past-tense pre-filter to demote facts that looked stale. But autobiography text is inherently past-tense. Franklin "practiced frugality" — past tense, but still identity-defining. The fix: exempt text_file and journal sources from the past-tense filter.

### Step 7-8: Contradictions and Consolidation

Contradiction detection uses embedding similarity to find candidate contradictory pairs, then a judge model determines whether they actually conflict. One fact gets a `superseded_by` pointer to the other. Consolidation clusters near-duplicate facts (from transitive closure of similarity relationships) and selects a canonical representative for each cluster.

For the primary corpus: 815 candidate pairs judged, 124 facts consolidated.

For document corpora, contradiction detection becomes especially interesting. When 30 patents across 10 technology domains are run through the pipeline, the system surfaces both **intra-document** contradictions (a single patent advocating opposing positions) and **cross-document** contradictions (patents in the same field taking opposing stances). Examples from a patent corpus: a sensor fusion patent requiring multi-sensor integration while a retrofit LiDAR patent argues vision alone can replace LiDAR; a quantum computing patent prioritizing hardware error correction while another prioritizes software approaches; a CRISPR patent advocating both personalized genomic editing AND population-level databases within the same document. These are not bugs — they are genuine tensions in the corpus that reveal where the field is unresolved. The system classifies each as CONTRADICTION (hard conflict) or TENSION (compatible but pulling in different directions). Active facts went from 4,734 to 4,610.

### Step 9: Anchors — Epistemic Axioms

This is where the pipeline moves from facts to identity. Conviction-level facts — the things a person believes with foundational certainty — are surfaced as candidate axioms. The user reviews and confirms them. These become the ANCHORS layer: the pre-set certainties a person reasons FROM, not facts they reason about.

Here is a real axiom from Benjamin Franklin's brief:

> **A1. PUBLIC-FIRST**
> Frame every proposal by leading with public benefit — he will dismiss ideas that prioritize personal gain or fail to demonstrate clear service to the common good, and will question your judgment if you present self-serving options as equivalent to public-serving ones.
> *Active when: he evaluates competing options or discusses resource allocation decisions*

This is not a fact. "Franklin believed in public service" is a fact. The axiom is an instruction to the AI: when you interact with this person, here is a filter they apply before they even engage with your content. If your proposal does not lead with public benefit, it will be dismissed. That activation condition — "evaluates competing options or discusses resource allocation" — tells the model when the axiom fires.

Franklin's ANCHORS layer has 9 axioms, including axiom interactions that describe what happens when axioms conflict. PUBLIC-FIRST and EARNED-RECOGNITION interact: public service builds legitimate reputation, but recognition-seeking can corrupt public service. The layer tells the AI to watch for when visibility motivations begin driving public benefit claims.

### Step 10: Author Layers

Three layers are authored independently by Sonnet, each from a different slice of the classified facts:

**ANCHORS** — epistemic axioms (from conviction-level facts). What does this person reason FROM? Not their conclusions, but their starting assumptions.

**CORE** — communication and operating guide (from identity-tier facts grouped by fact type). Context modes that describe how the person operates in different domains. Franklin's CORE layer has five modes: Civic/Political, Business/Professional, Intellectual/Scientific, Personal/Moral, and an Essential Context overview.

Here is one of Franklin's context modes:

> **C3. INTELLECTUAL/SCIENTIFIC CONTEXT**
> When discussing experiments, learning, or knowledge-sharing, assume he values open publication over patents and personal profit. He believes inventions should serve public benefit freely. Approach topics through careful observation and systematic experimentation. Frame intellectual discussions as collaborative investigation rather than competitive debate.

**PREDICTIONS** — behavioral patterns (from behavioral identity-tier facts). When X happens, this person tends to do Y. The directive tells the AI what to do about it.

Here is a real prediction from Franklin:

> **P1. SOCRATIC DEFLECTION**: When challenged or questioned, he responds with counter-questions rather than direct assertions.
> *Directive: Prepare for question volleys. Structure responses to anticipate his counter-questions. Do not expect direct agreement or disagreement — expect inquiry that tests your reasoning.*

Each layer is authored blind — the model generating PREDICTIONS cannot see ANCHORS or CORE. This is not accidental. When Sonnet sees its own prior output, 26% of the text carries over verbatim. Blind authoring forces each layer to derive from facts, not from the model's prior language.

Before authoring, all data is anonymized. Subject names are replaced with "this person" so the authoring model derives behavioral patterns purely from facts, not from any prior knowledge about the subject. This is critical for public figures — without anonymization, Sonnet authoring Franklin's layers would draw on its training data about Franklin rather than strictly from the extracted facts. The anonymization layer detects subject names from the database and scrubs them from facts, anchor data, and prompts.

Key constraint: every sentence must change how the AI responds. The ANCHORS prompt makes this explicit:

```python
# author_layers.py — opening of the ANCHORS prompt
"""You are authoring the EPISTEMIC ANCHORS layer of a personal identity brief.

CRITICAL: The audience is the intelligence and understanding an AI needs to
take on to communicate naturally with this person. Every sentence you write
must shape that understanding — not document the person, but create
comprehension in the reader. Portrait descriptions are FORBIDDEN.

These are axioms — beliefs this person reasons FROM, not ABOUT. Pre-set
certainties. Use them to narrow predictions before situation-specific
information arrives.

BAD (portrait + separate directive):
  "Alex cannot tolerate wasted resources in any project."
  "AI directive: Flag inefficiencies in proposed plans."

GOOD (directive-embedded — description IS the directive):
  "Before proposing a plan, audit it for resource waste — Alex will reject
   anything that allocates effort without measurable return and will distrust
   your judgment for not catching it."
"""
```

The distinction between "portrait" and "directive-embedded" is the core design insight. A portrait describes the person to a human reader. A directive-embedded description tells the AI how to behave. The same information, structured differently, produces measurably different downstream behavior.

### Step 11: Collective Review

An automated review pipeline scores each layer. Sonnet does a self-review, then Opus (a stronger model) reviews with four adversarial personas: cognitive scientist, narrative biographer, epistemologist, pragmatic engineer. If a layer scores below 75/100, it gets regenerated with feedback. Maximum three iterations.

A critical rule: evaluation artifacts never feed back into generation prompts. If the Collective identifies "strengths to preserve," those strengths are NOT passed to the regeneration prompt. That would anchor the model on its own prior output. Feedback is negative only — what is wrong, not what to keep.

### Step 12: Compose — The Compression Step

This is the step that makes the system work.

Three independently authored layers go in. One narrative brief comes out. Opus reads all three layers plus the top 100 identity-tier facts and compresses them into a single narrative document — roughly 3,000 tokens — that captures the behavioral model in a form any AI can ingest.

The composition prompt enforces three properties that the evaluation proved matter:

```python
# agent_pipeline.py — the composition prompt (key section)
"""THREE PROPERTIES that make a good brief (from controlled evaluation):

1. CONCRETE AUTOBIOGRAPHICAL MECHANISMS — Not "values honesty" but "will
   terminate a conversation that uses strategic ambiguity." Not "is analytical"
   but "will reframe an emotional question as a structural question, then solve
   the structure." Specific tactics, not abstractions.

2. CHARACTERISTIC INNER TENSIONS — The contradictions that define this person.
   "Believes in systematic process but breaks own rules under emotional load."
   These tensions are MORE useful than clean descriptions because they let the
   AI anticipate failure modes.

3. PRAGMATIC FRAMING — Write for an AI that needs to ACT on this information.
   Every sentence should change what the AI would say. If a sentence produces
   the same generic response with or without it, cut it.

ANTI-ENUMERATION: Never list axioms sequentially in a single paragraph. A
paragraph that reads "A1 does X; A2 does Y; A3 does Z..." is a schema dump,
not a behavioral narrative. Instead, group related mechanisms thematically.
"""
```

A quality gate (`verify_brief_completeness()`) parses the source layers for required terms — axiom names, prediction labels, context modes, data-quality markers — and checks that all of them appear in the composed brief. If terms are missing, the brief is fed back for recomposition.

Why does this step exist? Because the eval proved it matters. Giving a model the three structured layers (condition C2 in the evaluation) produced scores that were flat relative to baseline — a lift of -0.02. Giving a model the compressed narrative brief (condition C5c) produced a lift of +0.40. The model can leverage a narrative behavioral description more effectively than a structured data dump.

This was the most counterintuitive finding of the project. More structure did not help. Narrative compression did.

### Step 13-14: Assemble and Serve

The brief is served via MCP (Model Context Protocol). The MCP server is compact — the core setup is a few lines:

```python
# mcp_server.py — the full serving architecture
mcp = FastMCP("base-layer")

@mcp.resource("memory://identity")
def get_identity_brief() -> str:
    """The user's full identity brief. Always-on context that tells you
    who you're talking to."""
    # Priority 1: Unified brief (compressed narrative — proven +0.40 vs structured)
    if UNIFIED_BRIEF_FILE.exists():
        content = UNIFIED_BRIEF_FILE.read_text(encoding="utf-8")
        # Extract injectable block, prepend anti-parrot preamble
        ...
    # Priority 2: Three-layer fallback (anchors + core + predictions)
    ...

@mcp.tool()
def recall_memories(query: str) -> str:
    """Semantic retrieval of relevant facts for a query."""

@mcp.tool()
def search_facts(query: str, limit: int = 15) -> str:
    """Keyword search across all active facts."""

@mcp.tool()
def trace_claim(claim_id: str) -> str:
    """Trace an identity layer claim back to supporting facts.
    Like Genius.com annotations — shows the evidence chain."""
```

The Resource (`memory://identity`) is always-on — roughly 3,500 tokens injected into every conversation. The Tools are on-demand. An anti-parrot preamble is prepended to every brief:

```
IMPORTANT: This brief contains ALL-CAPS pattern names as internal labels.
NEVER quote, reference, or name them in your responses. Do not say
'your [PATTERN] axiom' or 'the [PATTERN-NAME] pattern.' Instead,
demonstrate understanding through your behavior.
```

This prevents the model from saying things like "As your COHERENCE axiom suggests..." — which would be creepy and break immersion. The model should behave as if it knows you, not announce that it has a file about you.

Any MCP-compatible client — Claude Desktop, Cursor, custom tooling — gets the behavioral brief automatically. The brief is model-agnostic: it works with Claude, GPT, Gemini, or any model that accepts a system prompt.

---

## The Brief

Here is what the final artifact looks like, using Benjamin Franklin as an example (extracted from his autobiography, a public domain text).

The brief opens with the foundational behavioral mechanism:

> Benjamin Franklin operates from a fundamental conviction that public benefit must precede personal gain in all endeavors, viewing any proposal that prioritizes individual advancement over common good as inherently flawed. This PUBLIC-FIRST mechanism shapes every aspect of his engagement — from his printing business to his scientific experiments to his civic leadership.

It describes communication patterns with activation conditions:

> He practices the Socratic method instinctively, responding to challenges with counter-questions that expose weaknesses in opposing arguments rather than making direct assertions. This pattern extends beyond intellectual debates — in business discussions, he probes assumptions rather than stating positions, and in political contexts, he tests ideas through anonymous publication before committing publicly.

It captures tensions between competing values:

> His commitment to both truth-telling and relationship preservation creates situations where UTILITY-HONESTY might damage necessary collaborations — he navigates this through timing and method rather than compromising either principle.

And it honestly marks where data is thin:

> [THIN DATA] Note that behavioral prediction data remains thin in several domains, particularly personal relationships beyond business partnerships, leisure activities, and private emotional patterns beyond the documented grief over his son's death.

This brief was produced from 212 extracted facts (135 at identity tier) derived from Franklin's autobiography. The pipeline cost was under $2. The brief is roughly 2,800 tokens. The source autobiography is roughly 19,000 tokens. Compression ratio: 85%. For the primary test subject (1,892 conversations, roughly 10 million tokens of source material), the compression ratio is 99.96%.

---

## What the Eval Shows

The evaluation used a framework called BCB (Behavioral Compression Benchmark) with five metrics. The core test: 10 identity-sensitive prompts covering value tradeoffs, domain-specific predictions, emotional regulation, contradiction stress, and domain gaps. Responses generated under multiple conditions, judged blind.

**Franklin results (60 responses, $4.05):**

| Condition | Description | Mean Score | Lift over Baseline |
|-----------|-------------|-----------|-------------------|
| C1 | Cold — no identity context | 3.92 | — |
| C2 | Full structured layers | 3.90 | -0.02 |
| C5c | Compressed brief | 4.32 | +0.40 |

The structured layers (condition C2) provided zero improvement over cold. The compressed brief (C5c) provided a +0.40 lift — roughly 10% improvement on a 5-point scale.

This result has a specific interpretation: compression is not just retention, it is amplification. The model can leverage a narrative behavioral description more effectively than the same information organized as structured data. The narrative format aligns with how language models process context. A list of axioms and predictions is parseable but inert. A narrative that says "when he faces pressure to bend truth, he navigates through timing and method rather than compromising" gives the model a behavioral template it can instantiate.

The finding also validates the design principle that emerged from the project's history: prescriptions constrain, data composes. The brief provides behavioral data — patterns and tendencies — not instructions like "always respond formally." The model composes its own behavior from the patterns, which is exactly what language models are optimized to do.

---

## The N=8 Proof

Eight subjects have been run through the pipeline. Each represents a different source type:

| Subject | Source Type | Input | Active Facts | Identity Tier | Brief |
|---------|-----------|-------|-------------|--------------|-------|
| User A | 1,892 conversations (ChatGPT + Claude) | 40,997 messages | 4,610 | 2,684 | ~3,723 tokens |
| User B | 36 newsletter posts | Single-domain text | 309 | — | 77.7/100 |
| Subject B | 9 journal entries | Personal journals | 76 | — | 81.7/100 |
| Franklin | Autobiography | 21 chapters | 212 | 135 | ~2,800 tokens |
| Douglass | Autobiography | Book text | 88 | 51 | ~2,137 tokens |
| Wollstonecraft | Political treatise | Book text | 95 | 81 | ~1,688 tokens |
| Roosevelt | Autobiography | Book text | 398 | 264 | ~2,738 tokens |
| Patent Corpus | 30 US patents (document mode) | 10 tech domains | 572 | 499 | ~1,866 tokens |

Same pipeline. Same 14 steps. Same constrained predicates. Different source types — multi-year conversations, single-topic newsletters, introspective journals, 18th-century autobiography, political philosophy, early 20th-century memoir, and technical patent filings. The pipeline produces meaningful behavioral briefs for all of them.

The patent corpus is a particularly interesting test. These are not personal documents — they have no single author's voice, no biographical content, no emotional register. They are technical legal filings. Yet the pipeline extracted a coherent "document identity": what these patents collectively believe about the future of technology, where they agree, where they contradict, and what cross-domain patterns emerge (constraint-driven innovation, exhaustive enumeration, modular composability). The Opus review scored the patent brief 8/10 for impressiveness and 9/10 for cross-domain synthesis.

This does not prove the system works for everyone. But it demonstrates that the pipeline generalizes across source types, time periods, writing styles, and even non-personal documents. Franklin and Wollstonecraft wrote in 18th-century English. Roosevelt wrote in early 20th-century prose. The patent corpus was written in modern legalese. The constrained predicates and tier classification still produce usable output.

---

## What Does Not Work

Honesty demands a section on failures, and this project has a catalog.

**Qwen for narrative generation.** Twelve attempts across four sessions to use a local 14B model for identity layer authoring. Every one failed. The Collective's Narrative Biographer graded the best attempt D+. Qwen is fine for mechanical extraction — pulling structured triples from text. But synthesizing those facts into coherent behavioral narratives requires a frontier model. Different cognitive tasks require different capabilities. The pipeline is multi-model by design because of this failure.

**Vector similarity for directive text.** Embedding similarity works well for factual claims ("Franklin valued frugality" vs "Franklin was frugal"). It works poorly for behavioral directives ("Prepare for question volleys and structure responses to anticipate his counter-questions"). Directives are instructions, not descriptions. Their semantic similarity to source facts is low even when they are well-supported. This makes automated provenance for the PREDICTIONS layer unreliable. ANCHORS and PREDICTIONS synthesize across many facts rather than quoting from them, so citation-based provenance also fails. The current workaround is vector-proximity provenance (find the closest facts, link them), which is good enough for traceability but not for verification.

**Single-domain predictions.** When the source material covers only one domain (User B's 36 newsletter posts, all about technology), the PREDICTIONS layer struggles to find cross-domain behavioral patterns. There is nothing to cross-reference. The system detects this and uses a single-domain prompt variant, but the resulting predictions are less interesting — they describe domain-specific habits rather than portable behavioral patterns.

**Scoring algorithm sensitivity.** The scoring formula (40% novelty, 35% recurrence, 25% depth) is fragile. When a bug inflated a coffee fact's recurrence to 677 (correct value: 14), every downstream step — tier classification, layer authoring, identity brief — was built on corrupted data. The fix was operational: mandatory re-scoring whenever the algorithm changes. But the underlying sensitivity remains. A better architecture would make downstream steps resilient to individual fact score errors.

**The Ghost Layer.** Early in the project, an attempt was made to encode philosophical significance into per-fact weights. The result: "partner's dry skin" outranked "founded the startup" as the most identity-significant fact. Philosophy belongs in the schema — what questions to ask about a person — not in per-fact weights. This failure led to the current architecture where philosophy shapes the pipeline design, not individual fact scores.

**Template language in extraction.** Before constrained predicates, 57% of extracted facts were template language: "The user is interested in data sovereignty and considers it important for AI development." Fifteen words to say `user values data_sovereignty`. Structured extraction with 47 canonical predicates eliminated this, but only after it had corrupted an entire pipeline run.

---

## Provenance

Every claim in the brief traces back to source facts. Each axiom, context mode, and prediction carries provenance markers — fact IDs linking to the specific extracted facts that support the claim.

Here is what that looks like for Franklin's axiom A4, RESOURCE-STEWARDSHIP:

> **A4. RESOURCE-STEWARDSHIP**
> Audit every expenditure or time allocation for waste — he will reject proposals that spend money, time, or effort without clear return and views frugality as both practical wisdom and moral duty.
> provenance: [F-6451c944, F-067c2f2e, F-48920e36]

Each of those fact IDs maps to a specific extracted fact in the database: "Franklin practices frugality," "Franklin values industry over idleness," "Franklin tracks expenditures carefully." The MCP server exposes a `trace_claim` tool that resolves any fact ID to its full record:

```python
# mcp_server.py — trace_claim (abbreviated)
@mcp.tool()
def trace_claim(claim_id: str) -> str:
    """Trace an identity layer claim back to its supporting facts
    and source conversations."""
    rows = conn.execute("""
        SELECT p.claim_id, p.claim_text, p.fact_id, p.link_method,
               p.rank_in_claim, p.layer_name,
               f.fact_text, f.category, f.knowledge_tier,
               c.title as conv_title, c.conv_source
        FROM layer_claim_provenance p
        LEFT JOIN memory_facts f ON p.fact_id = f.fact_id
        LEFT JOIN conversations c ON f.conversation_id = c.id
        WHERE p.claim_id = ?
        ORDER BY p.rank_in_claim
    """, (claim_id,)).fetchall()
    # Format: claim text → supporting facts → source conversations
```

This is not just an engineering nicety. When a model tells you something based on your brief, you can ask: where did that come from? And the system can show you the chain — from the model's response, to the brief, to the layer, to the fact, to the original conversation or text. Every link in the chain is inspectable.

---

## Cost

The full pipeline for a new subject costs roughly $2 in API calls. The breakdown:

| Step | Model | Cost |
|------|-------|------|
| Extract | Haiku | ~$0.01/conversation |
| Classify | Haiku | ~$1 total |
| Tier | Sonnet | ~$1 total |
| Author layers | Sonnet | ~$0.06 |
| Collective review | Sonnet + Opus | ~$0.10 |
| Compose brief | Opus | ~$0.05 |

Embedding runs locally (free). Scoring runs locally (free). Contradiction detection and consolidation are the most expensive steps for large corpora (815 Sonnet calls for the primary corpus), but for a new user with a few hundred conversations, total cost stays under $5.

The ongoing cost is zero. The MCP server runs locally. The brief is a static file. No API calls at serving time.

---

## What Is Next

**Investor case studies.** Warren Buffett's 48 shareholder letters (1977-2024) and Howard Marks's 74 investment memos (2001-2026) are downloaded and ready for pipeline processing. These test whether the system can model investment decision-making patterns — thesis formation, risk assessment style, contrarian instincts. Strong launch artifacts: investors are the audience most likely to care about "here is how an AI models your investment style."

**Cross-domain interaction reasoning.** Before layer generation, an explicit reasoning step that maps how behavioral patterns interact across domains. "Confirmation-seeking manifests as: in trading, wait for confluence; in professional decisions, clarify goals before execution; in personal finance, avoid investments that seem too good." Makes cross-domain discovery systematic rather than hoping the model finds it emergently.

**Cross-provider evaluation.** Same brief, same prompts, different foundation models. Does Claude produce structurally similar behavioral predictions as GPT as Gemini? If yes, the signal is in the brief, not in model-specific priors.

---

## The Thesis

Memory is necessary but not sufficient for understanding. The gap is not in what memory captures — it is in what gets injected into the system prompt. An identity brief is what you would write if you sat down and tried to explain someone to a stranger. It is not a list of things they have said.

The memory systems shipping today are solving retrieval. They are good at it and getting better. But no amount of retrieval sophistication turns "User values frugality" and "User practices systematic self-examination" and "User publishes anonymously when content is controversial" into "Before proposing a plan, audit it for resource waste — he will reject anything that allocates effort without measurable return and will distrust your judgment for not catching it." That transformation requires compression, not retrieval.

No AI provider is incentivized to build portable identity. They want lock-in. The identity layer that sits outside any single provider is structurally impossible for incumbents to build — it requires neutrality they cannot have. Memory providers are not adversaries — they are potential integration partners. The stack works better with both layers.

The pipeline is 14 steps because identity is complex. Every step exists because a simpler approach failed. The 14 steps are not arbitrary — they are the minimum process that produces a behavioral brief an AI can actually use to behave as if it knows you.

The system is open source (Apache 2.0) because the methodology is the product. Hiding the pipeline behind an API would undermine the core claim that behavioral compression is a meaningful advance over fact retrieval. If the process is not inspectable, the claim is not verifiable.

The layer between your memories and your model. Always on.
