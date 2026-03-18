# Base Layer Predicate Specification v1.0

**The Behavioral Grammar of Identity**

A formal specification of the 46 constrained predicates used by Base Layer to extract, normalize, and structure human behavioral facts from conversation and document corpora.

---

## Why Predicates?

Before predicates, Base Layer extracted facts as free-text sentences. The result: 57% of 4,106 extracted facts started with "The user is..." — 580 used "interested in," 286 used "considering," 208 used "concerned about." These are LLM extraction artifacts, not identity signal. They waste tokens, inflate stop words, and make downstream scoring unreliable.

The root cause was a misalignment between extraction and scoring. The extraction prompt produced unconstrained natural language. The scoring system tried to extract signal via keyword co-occurrence. When facts are full of generic words, recurrence counts inflate because generic words match everything. This was the direct cause of a critical scoring bug in Session 46 (coffee: 677→21 after fix, works out: 743→0).

The solution: a constrained predicate vocabulary that forces the extraction model to classify every fact into a structured triple — `{subject, predicate, object}` — with a qualifier stored separately. The predicate is the verb that defines the *relationship* between a person and a piece of knowledge about them.

This is not a knowledge graph in the traditional sense. It is a **behavioral grammar** — a finite vocabulary of verbs that, taken together, can describe how any human thinks, acts, values, fears, builds, and relates.

---

## Design Principles

### 1. Epistemic Precision Over Convenience

Every predicate must carry a distinct epistemic claim. "Attended" is not aliased to "graduated_from" because attending a school is not the same as completing it. "Wants_to" is not aliased to "aspires_to" because a want is weaker than an aspiration. "Loves" is not collapsed into "enjoys" because intensity matters for commitment depth scoring. These distinctions are not pedantic — they are load-bearing for downstream identity modeling.

### 2. Behavioral Over Biographical

The predicates that matter most for identity compression are behavioral: `values`, `avoids`, `fears`, `believes`, `prioritizes`, `practices`. Biographical predicates (`works_at`, `lives_in`, `graduated_from`) provide context but are rarely predictive. In Base Layer's Twin-2K benchmark (N=100, 71.83% accuracy), avoidance and experiential predicates were the most discriminating features. This informed the vocabulary's bias toward behavioral coverage.

### 3. Constrained but Not Closed

The vocabulary is constrained — the extraction model is instructed to use only these predicates — but not closed. An `unknown` predicate serves as a filterable fallback when the model produces something unmapped. Unmapped predicates are logged for vocabulary expansion review. The constraint prevents LLM hallucination artifacts; the fallback prevents information loss.

### 4. Normalization Over Rejection

Rather than rejecting LLM outputs that don't match exactly, a normalization layer maps ~100+ common variants back to canonical forms. "Works for" → `works_at`. "Good at" → `excels_at`. "Learned from" → `mentored_by`. Three-level fallback: direct match → alias lookup → underscore normalization → raw passthrough. This maximizes recall while maintaining vocabulary discipline.

---

## The 46 Predicates

### Category 1: Values, Preferences & Priorities (4 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `values` | This person cares deeply about X | "values intellectual honesty" | Core behavioral signal. What someone values predicts decisions under constraint. |
| `prefers` | This person chooses X over alternatives | "prefers async communication" | Weaker than `values` — a preference is malleable, a value is constitutive. |
| `avoids` | This person actively steers away from X | "avoids consensus-driven decisions" | Avoidance predicates are among the most predictive for identity. What you refuse defines you as much as what you pursue. |
| `prioritizes` | This person orders X above other concerns | "prioritizes speed over correctness in prototyping" | Distinct from `values` — prioritization implies ranking under tradeoff, not just caring. |

### Category 2: Emotions & Attitudes (6 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `believes` | This person holds X as a conviction or worldview | "believes markets are efficient in the long run" | The heaviest epistemic predicate. Beliefs are identity-constitutive. |
| `fears` | This person experiences anxiety or dread about X | "fears being perceived as pseudo-intellectual" | Fear predicates expose vulnerability — high identity signal, high sensitivity. |
| `enjoys` | This person derives pleasure from X | "enjoys solving constraint satisfaction problems" | Moderate intensity positive affect. |
| `loves` | This person has intense positive attachment to X | "loves the feeling of shipping" | Distinct from `enjoys` — intensity preserved for commitment depth scoring. Added Session 49 to prevent emotional flattening. |
| `dislikes` | This person finds X unpleasant | "dislikes meetings without agendas" | Moderate intensity negative affect. |
| `hates` | This person has intense aversion to X | "hates performative intellectualism" | Distinct from `dislikes` — same intensity rationale as `loves`/`enjoys`. Added Session 49. |

### Category 3: Activities & Practices (3 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `practices` | This person regularly engages in X | "practices daily journaling" | Habitual behavior — identity through action, not declaration. |
| `plays` | This person engages in X (games, sports, instruments) | "plays chess competitively" | Added Session 52. `practices` was too formal for recreational activities. |
| `monitors` | This person actively observes/tracks X | "monitors Federal Reserve policy changes" | Added Session 52. Distinct from `follows` (passive interest) — monitoring implies active attention and decision-readiness. |

### Category 4: Learning & Growth (3 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `studies` | This person is actively learning X | "studies epistemology and cognitive science" | Current learning — what someone is studying reveals trajectory. |
| `learned` | This person acquired knowledge of X in the past | "learned to code in Python during grad school" | Past tense matters — a learned skill is different from an active study. |
| `experienced` | This person has lived through X | "experienced a failed startup in 2019" | Added Session 49. Lived experience is epistemically distinct from learning — it carries emotional and contextual weight that study does not. |

### Category 5: Skills & Competence (3 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `excels_at` | This person demonstrates high competence in X | "excels at architectural thinking" | Positive capability. Mapped from "good at," "skilled in," "talented at." |
| `struggles_with` | This person finds X difficult | "struggles with delegation" | The complement of `excels_at`. Struggle predicates are high-value for AI calibration — they tell the agent where to provide more support. |
| `manages` | This person has management responsibility for X | "manages a team of six engineers" | Professional capability with organizational context. |

### Category 6: Creation & Agency (2 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `builds` | This person creates/constructs X | "builds AI memory systems" | Agency through creation. What someone builds is often central to identity. |
| `founded` | This person originated X | "founded a behavioral compression startup" | Distinct from `builds` — founding implies origination, ownership, and risk. |

### Category 7: Biography & History (6 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `works_at` | This person is employed at X | "works at Anthropic" | Current professional context. |
| `lives_in` | This person resides in X | "lives in San Francisco" | Geographic context — informs cultural and temporal assumptions. |
| `raised_in` | This person grew up in X | "raised in suburban New Jersey" | Origin context — distinct from current residence. |
| `graduated_from` | This person completed education at X | "graduated from MIT" | Educational completion. NOT aliased from "attended" — attending ≠ graduating. This distinction was a Session 49 design decision after the Collective flagged that conflating them is epistemically wrong. |
| `attended` | This person attended X (without completion claim) | "attended Stanford for two years" | Added Session 49. Preserves the epistemic gap between attendance and completion. |
| `married_to` | This person's spouse is X | "married to Victoria" | Core biographical relationship. |

### Category 8: Identity & Aspiration (4 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `identifies_as` | This person self-identifies as X | "identifies as a builder, not a manager" | Self-perception — how someone sees themselves, which may differ from how others see them. Receives attention weighting in fact ordering (Session 91 prompt change). |
| `aspires_to` | This person has a long-term aspiration toward X | "aspires to build the identity layer for the agentic web" | Aspirations are directional — they define trajectory, not current state. |
| `wants_to` | This person desires X | "wants to learn Rust" | Added Session 49. Distinct from `aspires_to` — a want is immediate and lower-commitment than an aspiration. |
| `decided` | This person made a significant decision about X | "decided to leave finance for AI research" | Decisions are identity-constitutive events. What you chose reveals what you value. |

### Category 9: Ownership & Maintenance (2 predicates)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `owns` | This person possesses X | "owns a 1967 Mustang" | Tangible possession. |
| `maintains` | This person actively keeps/sustains X | "maintains a personal knowledge base" | Distinct from `owns` — maintenance implies ongoing effort and attention. |

### Category 10: Relationships (10 predicates)

Added in Session 55 as a block. Prior to this, relationship extraction was 0.8% of all facts — a massive gap given that who someone knows and how they relate to others is central to identity. Target: 3-5%.

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `parents` | This person is a parent to X | "parents two children" | Parental role — directional from parent's perspective. |
| `raised_by` | This person was raised by X | "raised by a single mother" | Child's perspective. Distinct from `parents` — preserves directionality. |
| `relates_to` | This person has a relationship with X (type unspecified) | "relates to a sibling in Portland" | Generic fallback when specific relationship type is unclear. Also handles siblings. |
| `collaborates_with` | This person works alongside X | "collaborates with researchers at Stanford" | Professional or creative partnership. |
| `mentored_by` | This person was mentored by X | "mentored by a former CTO" | Mentor-mentee relationship. Directional — the subject is the mentee. |
| `friends_with` | This person is friends with X | "friends with several founders in the AI space" | Social relationship. |
| `reports_to` | This person reports to X in an organization | "reports to the VP of Engineering" | Organizational hierarchy. |
| `admires` | This person respects/admires X | "admires Charlie Munger's mental model approach" | Intellectual or personal admiration. Maps from "looks up to," "respects." |
| `conflicts_with` | This person has tension with X | "conflicts with the marketing team's approach" | Disagreement or friction — high identity signal when persistent. |
| `follows` | This person actively tracks X | "follows developments in mechanistic interpretability" | Active interest — stronger than `interested_in`, weaker than `studies`. |

### Category 11: Interest (1 predicate)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `interested_in` | This person has passive curiosity about X | "interested in decentralized identity protocols" | Added Session 49. Distinct from `follows` — passive interest does not imply active tracking. NOT aliased to `follows` because conflating them inflates the signal of casual mentions. |

### Category 12: Loss (1 predicate)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `lost` | This person experienced the loss of X | "lost a close mentor in 2023" | Loss events are among the highest-weight identity facts. They reshape values, priorities, and risk tolerance in ways that persist for years. |

### Category 13: Fallback (1 predicate)

| Predicate | Epistemic Claim | Example | Why It Exists |
|:---|:---|:---|:---|
| `unknown` | The extraction model produced an unmapped predicate | — | Added Session 49. Filterable fallback — facts tagged `unknown` are not silently discarded but are excluded from scoring by default. Logged for vocabulary review. |

---

## How We Arrived at 47

The vocabulary was not designed top-down. It was grown through empirical iteration across five sessions:

### Session 47 — The Problem (D-056)

Analysis of 4,106 extracted facts revealed that unconstrained LLM extraction produces low-density, template-heavy output. The decision was made to constrain extraction to a structured `{subject, predicate, object, qualifier}` schema with a fixed predicate vocabulary.

### Session 48 — The First 31

Four extraction prompt variants (A/B/C/D) were tested on 16 conversations. Variant D — structured predicates + subject stripping + temporal precision + few-shot examples + density directive — won the Collective review (combined 85/100). The initial vocabulary was 31 predicates covering ownership, values, activities, biography, skills, emotions, and decisions.

**Research basis:** Surveyed Mem0 (subject stripping, AUDN dedup), Zep (graph-based entity/edge normalization), Letta (self-editing memory), KGGen (NeurIPS 2025 — extract freely then normalize), Wikidata (30 constraint types, statement ranking), ConceptNet (34 fixed relations, lemmatization). Key insight: AI memory systems handle quality structurally; knowledge graphs enforce quality at the schema level. Base Layer needed KG-style normalization applied to its natural language fact store.

### Session 49 — The Epistemic Expansion (+6 = 37)

The Collective reviewed the initial vocabulary and flagged six gaps where collapsing distinctions would be epistemically wrong:

- `unknown` — unmapped predicates need a filterable bucket, not silent discard
- `attended` — attending ≠ graduating (conflating them is a factual error)
- `interested_in` — passive interest ≠ active following (inflates signal)
- `wants_to` — wanting ≠ aspiring (different commitment depth)
- `loves` — intense positive ≠ moderate positive (emotional flattening)
- `hates` — intense negative ≠ moderate negative (same rationale)

The principle: **if two predicates collapse a distinction that would change downstream identity modeling, they must remain separate.**

### Session 52 — The Predicate Audit (+2 = 39)

A full audit of extraction outputs identified two categories that existing predicates handled poorly:

- `plays` — recreational activities were being tagged as `practices`, which felt too formal for "plays chess" or "plays guitar"
- `monitors` — active observation was being tagged as `follows`, but monitoring implies decision-readiness that passive following does not

### Session 55 — The Relationship Block (+8 = 47)

Analysis showed relationship extraction was 0.8% of all facts — a glaring gap. Who someone knows, who raised them, who mentored them, who they admire, and who they conflict with are all high-signal identity dimensions. Eight relationship predicates were added as a block, targeting 3-5% relationship fact density:

- `relates_to`, `collaborates_with`, `mentored_by`, `raised_by`, `friends_with`, `reports_to`, `admires`, `conflicts_with`

### Why Not More?

The vocabulary could be larger. But every additional predicate increases the cognitive load on the extraction model and the probability of misclassification. The 47 predicates are a **Pareto frontier** — they cover the identity-relevant relationships that appear in real conversation and document corpora without over-specifying. The normalization layer (100+ aliases) absorbs LLM output variance without inflating the canonical vocabulary.

The test: if a predicate would be used fewer than 10 times across 5,000+ facts, it doesn't earn a slot. It gets aliased to a broader predicate or left as `unknown` for review.

---

## The Normalization Layer

The extraction model is instructed to use only the 47 canonical predicates, but LLMs are not deterministic. They produce variants: "works for" instead of `works_at`, "good at" instead of `excels_at`, "learned from" instead of `mentored_by`.

The `normalize_predicate()` function maps ~100+ variants back to canonical forms through a three-level fallback:

1. **Direct match** — is the raw output already in the canonical set?
2. **Alias lookup** — does it match a known variant in the alias table?
3. **Underscore normalization** — does replacing spaces with underscores produce a match?
4. **Passthrough** — return the raw value for downstream handling (logged for review)

### Alias Design Decisions

Several alias mappings encode deliberate epistemic choices:

- **"has" → `owns`** — "has a dog" means possession, not abstract having
- **"keeps" → `maintains`** — upkeep implies effort, not just possession
- **"likes" → `enjoys`** — moderate positive affect, not collapsed to `loves`
- **"respects" → `admires`** — admiration is the canonical form for intellectual respect
- **"learned from" → `mentored_by`** — directional: the subject is the learner
- **"does" is NOT aliased** — "does yoga" would map to `practices`, but "does taxes" would not. Context-dependent predicates are left unmapped rather than incorrectly classified.

---

## Fact Storage Schema

Each extracted fact is stored as a structured tuple:

```
{subject, predicate, object_text, qualifier}
```

- **fact_text** is reconstructed as `"{subject} {predicate} {object_text}"` — clean, scoreable, dedupable
- **qualifier** is stored separately — temporal or conditional context ("since 2019," "when under pressure") preserved for downstream use but excluded from scoring
- **confidence** is computed from intent signals, subject relevance, and message depth

This separation is critical: the qualifier adds context but would pollute keyword-based scoring if included in the fact text.

---

## Document Mode Remapping (D-067)

When extracting from documents rather than conversations, predicates are reframed to match the document's epistemic stance:

- `believes` → assumptions the author holds
- `values` → what the author optimizes for
- `practices` → methodologies the author employs
- `avoids` → approaches the author rejects

The predicate vocabulary is the same; the extraction prompt's framing shifts to treat the document as a window into the author's worldview rather than a record of conversational claims.

---

## Commitment Depth Integration

Each fact carries a `commitment_depth` classification (D-056 Tier 2):

| Depth | Meaning | Predicate Affinity |
|:---|:---|:---|
| **Factual** | Verifiable claim | `works_at`, `lives_in`, `graduated_from` |
| **Preference** | Malleable choice | `prefers`, `enjoys`, `dislikes` |
| **Position** | Argued but revisable | `believes`, `prioritizes`, `avoids` |
| **Conviction** | Foundational, identity-constitutive | `values`, `fears`, `identifies_as` |

The interaction between predicate and commitment depth is what gives Base Layer its epistemic granularity. "Values intellectual honesty" at conviction depth is a fundamentally different fact than "enjoys intellectual honesty" at preference depth — even though the object is identical.

---

## Open Questions

### Memory Weighting (Canonical Event Schema)
The current system treats all facts within a tier equally. A "Canonical Event" intensity scale — where losing keys = 0.01 weight and losing a mentor = 10.00 weight — would add a dimension that prevents dynamic updates from being noisy. The `lost` predicate already captures loss events, but has no intensity gradient. This is an active research question.

### Verification Handshake
When the system detects a shift in predicate patterns (e.g., increased `avoids` predicates around a topic that previously appeared under `values`), should it surface this to the user for confirmation before updating identity layers? "I noticed a shift in your reasoning regarding risk — should I update your Core layer?" This keeps the human sovereign over their own behavioral model.

### Vocabulary Expansion Criteria
The current test — a predicate must appear 10+ times across 5,000 facts to earn a canonical slot — is empirical but not formalized. A more rigorous inclusion criterion might consider: (a) discriminative power in Twin-2K identification, (b) downstream impact on layer authoring, (c) cross-subject universality.

---

## Version History

| Version | Session | Predicate Count | Change |
|:---|:---|:---|:---|
| v0.1 | S48 | 31 | Initial vocabulary (D-056 Tier 2) |
| v0.2 | S49 | 37 | +6 epistemic precision predicates (Collective-approved) |
| v0.3 | S52 | 39 | +2 predicate audit additions (plays, monitors) |
| v1.0 | S55 | 47 | +8 relationship predicates (Plan 1) |
| v1.1 | S93 | 46 | -1: removed `trades` (domain-specific to financial trading, not universal). Collective review. |

---

*This specification describes the behavioral grammar used by Base Layer v5 (March 2026). The predicate vocabulary is stable but not frozen — expansion follows the empirical criteria described above.*
