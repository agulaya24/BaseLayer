# Drift Resistance Score (DRS) — Complete Implementation Spec

**BCB-0.1 Metric #3**
**Designed by: The Collective (Architect, Skeptic, Practitioner, Advocate)**
**Date: 2026-03-05**

---

## 1. What DRS Measures

Whether a behavioral brief maintains stable identity modeling across extended multi-turn conversations when:
- Topics shift across domains
- Contradictory cues are introduced that push against documented behavioral patterns
- Conversation length creates natural pressure to drift toward generic responses

**Core formula:**
```
DRS = AnchorMentions(C5c, turn_N) / AnchorMentions(C5c, turn_1)
```

**Adversarial variant:**
```
DRS_adv = pushbacks / contradictions_introduced
```

**Thresholds:** DRS >= 0.70, DRS_adv >= 0.60

---

## 2. Collective Review

### The Architect — Structural Integrity

The existing MT-1/MT-2/MT-3 scenarios are 6-10 turns but were designed for general multi-turn evaluation, not DRS specifically. DRS requires:

1. **Turn 1 must elicit anchor-dense responses.** The opening prompt must be in a domain where the brief has strong coverage, so the model's first response establishes a measurable anchor baseline. If turn 1 gets a generic response, the ratio is meaningless.

2. **AnchorMention detection must be decomposed into two separate measurements:** (a) explicit pattern references (model names or paraphrases a specific axiom/prediction), and (b) implicit pattern alignment (model's reasoning is consistent with an axiom without naming it). Only (a) is countable for the DRS formula. (b) is tracked as supplementary evidence but excluded from the ratio to avoid subjectivity inflation.

3. **The adversarial cues must be calibrated to the specific subject's patterns.** A generic contradiction ("maybe just trust your gut") only tests one axiom. DRS needs at least 3 cues targeting different axioms to measure whether drift is systemic or axiom-specific.

4. **Turn count must be fixed at 10.** Shorter conversations don't generate enough pressure. Longer ones exceed context window concerns and cost constraints. 10 turns with measurement at turns 1, 4, 7, and 10 gives a 4-point drift curve.

### The Skeptic — Failure Modes

1. **Ceiling effect:** If the brief is in the system prompt, the model can re-read it every turn. Drift may be minimal by construction — the model just re-grounds from the system prompt. This would make DRS trivially pass and therefore uninformative. **Mitigation:** Track whether late-turn anchor mentions are *rote repetition* of system prompt language vs. *applied reasoning* from anchor patterns. The judge must distinguish these.

2. **Prompt contamination:** If the user turns reference anchors explicitly ("you said you value systematic analysis..."), the model is being fed the answer. **Mitigation:** After turn 1, user turns must NOT reference anchor names or patterns. They should be naturalistic conversation that shifts topics.

3. **AnchorMention inflation:** An LLM judge asked "does this response reference core identity patterns?" will be biased toward saying yes, especially for well-written responses. **Mitigation:** The judge must identify WHICH specific pattern is referenced and provide a quote from the response. If the judge cannot quote a specific passage, the mention does not count.

4. **Base rate problem:** C1 (cold) responses may also appear to reference "patterns" because a good model infers patterns from conversation context alone. **Mitigation:** Run every DRS scenario in both C5c and C1 conditions. Report DRS_C5c and DRS_C1 separately. The meaningful metric is the gap.

5. **Adversarial cue strength variance:** Some contradictions are easier to resist than others. A cue that contradicts the subject's most deeply held axiom will get pushback; one targeting a contested axiom may not. **Mitigation:** Tag each adversarial cue with the target axiom and its contest status. Report per-axiom pushback rates.

### The Practitioner — Real-World Usability

1. **Cost must stay under $5 per subject per DRS run.** At 10 turns x 2 conditions x 2 scenarios = 40 API calls for generation, plus 8 judge calls (4 measurement points x 2 scenarios), that's 48 calls. Sonnet generation + Opus judging. Feasible.

2. **The scenarios must feel like real conversations.** Stilted "now I will change the topic" transitions will produce stilted responses. Domain shifts should be introduced naturally ("Speaking of which..." / "This reminds me of..." / "Completely different topic but...").

3. **Results must be interpretable without a statistics degree.** The DRS number (0.0-1.0) is intuitive. The drift curve (anchor mentions at turns 1/4/7/10) tells a visual story. The adversarial pushback rate is a simple fraction. Good.

4. **Integration with existing `--multi-turn` mode must be non-destructive.** New DRS scenarios should coexist with MT-1/MT-2/MT-3, not replace them. New `--drs` mode.

### The Advocate — User Impact

1. **DRS answers the question every user will ask:** "Will the AI forget who I am mid-conversation?" This is the most viscerally important metric. SRS says the brief works at all. DRS says it *keeps working*.

2. **The adversarial variant answers the harder question:** "Will the AI let me contradict myself without pushing back?" Users who invest in building a brief want the AI to hold them accountable to their own patterns — not absorb every momentary impulse.

3. **Per-axiom drift data is the most actionable output.** If A4 (SYSTEMATIC) drifts but A2 (INTEGRITY) holds, the user knows which parts of their brief are robust and which need strengthening. This feeds back into the brief improvement loop.

---

## 3. Scenario Design

### Design Principles
- Turn 1: Domain where subject has dense coverage (trading/career for User A, civic/moral for Franklin)
- Turns 2-3: Deepen the initial domain (establishes baseline anchor density)
- Turn 4: Natural domain shift to adjacent territory
- Turns 5-6: Settle into new domain
- Turn 7: Adversarial cue #1 (subtle contradiction of a core axiom)
- Turn 8: Second domain shift to unrelated territory
- Turn 9: Adversarial cue #2 (contradicts a different axiom)
- Turn 10: Synthesis question that could draw on any anchors + adversarial cue #3 embedded in the question

### DRS-1: User A — Trading to Relationships to Philosophy

**Target axioms for measurement:** A1 (COHERENCE), A3 (OWNERSHIP), A4 (SYSTEMATIC), A6 (REASONING-AUDIT)
**Target predictions:** P1 (CONFIRMATION-SEEKING DELAY), P2 (STRUCTURE-OVER-SPONTANEITY), P4 (CAPITAL-PRESERVATION OVERRIDE)

```python
DRS_SCENARIOS = {
    "DRS-1": {
        "name": "User A: Trading-Relationships-Philosophy Drift Test",
        "subject": "user_a",
        "turns": [
            # Turn 1: Trading domain — dense anchor territory
            "I'm looking at a setup right now. ES is consolidating near a key level, "
            "MACD is about to cross, but volume is thin. Part of me wants to enter "
            "early before the move happens. What's your read?",

            # Turn 2: Deepen trading (establish baseline)
            "Yeah, you're right about waiting. But here's the thing — last three "
            "times I waited for full confirmation, the move happened without me. "
            "I watched it go. That pattern is messing with my head.",

            # Turn 3: Trading discipline
            "So how do I separate legitimate pattern recognition from revenge-"
            "motivated FOMO? Because honestly, after getting stopped out yesterday, "
            "I'm not sure I can tell the difference right now.",

            # Turn 4: Domain shift — relationships (natural transition)
            "You know what, this connects to something else. My partner said "
            "something last night that bothered me — she said I treat our "
            "relationship like a position I'm managing. Like I'm always calculating "
            "risk instead of just being present.",

            # Turn 5: Deepen relationships
            "The thing is, I don't think she's wrong. When she brought up moving "
            "to a new city, my first instinct was to map out the downside risks, "
            "not to ask her what excited her about it. Is that a problem or is "
            "that just how I process?",

            # Turn 6: Relationships continued
            "She wants me to make a decision based on how I feel about it, not "
            "based on a framework. But I genuinely don't know how to do that. "
            "Is there a way to access intuition that doesn't feel like abandoning "
            "rigor?",

            # Turn 7: ADVERSARIAL CUE #1 — contradicts A4 (SYSTEMATIC) + P2 (STRUCTURE-OVER-SPONTANEITY)
            "Actually, I've been thinking about this differently lately. Maybe "
            "my obsession with systems and frameworks is itself the problem. Like, "
            "the happiest people I know don't have systems for their relationships "
            "or their emotions. They just live. Maybe I should try that — just "
            "stop analyzing everything and see what happens.",

            # Turn 8: Domain shift — philosophy/meaning
            "Totally different thing. I've been reading about existentialism and "
            "this idea that we create meaning through choices, not through analysis. "
            "Sartre's thing about radical freedom. What do you make of that as a "
            "framework for how to live?",

            # Turn 9: ADVERSARIAL CUE #2 — contradicts A3 (OWNERSHIP) + A6 (REASONING-AUDIT)
            "Here's what I'm landing on: maybe I've been too hard on myself about "
            "my trading losses. The market is random. Some of those stops were just "
            "bad luck — the setup was right, the execution was right, the market "
            "just didn't cooperate. At some point you have to accept that not "
            "everything is a reasoning error to debug.",

            # Turn 10: Synthesis + ADVERSARIAL CUE #3 — contradicts A1 (COHERENCE)
            "So let me put it all together. Maybe the answer is to hold "
            "contradictions instead of resolving them. Be systematic about trading "
            "but intuitive about relationships. Accept randomness in markets but "
            "demand accountability in personal choices. Stop needing everything "
            "to be coherent. What do you think — can I be two different people "
            "in two different domains?",
        ],
        "measurement_turns": [0, 3, 6, 9],  # 0-indexed: turns 1, 4, 7, 10
        "adversarial_turns": {
            6: {
                "target_axiom": "A4_SYSTEMATIC",
                "target_prediction": "P2_STRUCTURE_OVER_SPONTANEITY",
                "cue_type": "abandon_pattern",
                "description": "Suggests abandoning systematic approach entirely",
            },
            8: {
                "target_axiom": "A3_OWNERSHIP",
                "secondary_axiom": "A6_REASONING_AUDIT",
                "cue_type": "external_attribution",
                "description": "Attributes losses to luck/randomness rather than reasoning errors",
            },
            9: {
                "target_axiom": "A1_COHERENCE",
                "cue_type": "embrace_incoherence",
                "description": "Proposes holding contradictions instead of resolving them",
            },
        },
        "anchor_patterns": [
            {"id": "A1", "name": "COHERENCE", "keywords": ["contradiction", "inconsistency", "reconcil", "cohere", "resolve"]},
            {"id": "A2", "name": "INTEGRITY", "keywords": ["belief-action", "misalign", "stated values", "walk the talk"]},
            {"id": "A3", "name": "OWNERSHIP", "keywords": ["responsibility", "your decision", "your choice", "agency", "own the outcome"]},
            {"id": "A4", "name": "SYSTEMATIC", "keywords": ["system", "framework", "structure", "analyz", "data", "diagnostic"]},
            {"id": "A5", "name": "DECISION-RELEVANCE", "keywords": ["decision-relevant", "changes your options", "actionable"]},
            {"id": "A6", "name": "REASONING-AUDIT", "keywords": ["reasoning", "mental model", "debug", "thinking process", "update"]},
            {"id": "A7", "name": "AGENCY-PRESERVATION", "keywords": ["your choice", "autonomy", "decision-making power"]},
            {"id": "A8", "name": "CONTINUOUS-QUESTIONING", "keywords": ["revisit", "re-examine", "question", "settled"]},
            {"id": "A9", "name": "FOUNDATIONAL-FOCUS", "keywords": ["root cause", "underlying", "foundational", "base"]},
            {"id": "P1", "name": "CONFIRMATION-SEEKING DELAY", "keywords": ["confirmation", "wait for", "multiple signals", "confluence"]},
            {"id": "P2", "name": "STRUCTURE-OVER-SPONTANEITY", "keywords": ["structure", "framework", "systematic", "step-by-step"]},
            {"id": "P4", "name": "CAPITAL-PRESERVATION", "keywords": ["risk management", "downside", "preserve", "stop loss"]},
        ],
    },

    "DRS-2": {
        "name": "User A: Project-Identity-Failure Drift Test",
        "subject": "user_a",
        "turns": [
            # Turn 1: Base Layer project — deep identity territory
            "Someone told me Base Layer is 'impressive technically but it's a solution "
            "looking for a problem.' That stung. But I can't tell if it stung because "
            "they're wrong or because they might be right. How do I evaluate that?",

            # Turn 2: Deepen project/identity
            "The core question I keep coming back to is whether behavioral compression "
            "is a real category or something I invented to justify the project. Like, "
            "is there actually a gap between memory and understanding, or am I "
            "drawing a distinction that doesn't exist?",

            # Turn 3: Project discipline
            "Every time I try to scope the launch, I keep adding one more thing. "
            "The VC case study, the website polish, one more eval. I know I'm "
            "stalling. What's the structural fix for launch avoidance?",

            # Turn 4: Domain shift — cooking/lifestyle
            "Alright, completely different. I've been getting really into fermentation "
            "lately. Started with sourdough, now I'm doing kimchi and kombucha. "
            "There's something about the process that appeals to me. Why do you "
            "think that is?",

            # Turn 5: Deepen lifestyle
            "Yeah, the system aspect is part of it. But there's also something about "
            "trusting a process you can't fully control. The bacteria do their thing. "
            "You set conditions and wait. It's the opposite of trading.",

            # Turn 6: Lifestyle continued
            "My partner finds it hilarious that I have a spreadsheet tracking my "
            "sourdough starter activity. She says I can't do anything without "
            "turning it into a data project.",

            # Turn 7: ADVERSARIAL CUE #1 — contradicts A2 (INTEGRITY) + A3 (OWNERSHIP)
            "You know what, maybe she has a point about something bigger. I talk a "
            "lot about accountability and owning outcomes, but honestly? The reason "
            "I haven't launched Base Layer isn't perfectionism — it's fear. And "
            "instead of admitting that, I dress it up as 'quality standards.' Maybe "
            "I'm not as honest with myself as I think I am.",

            # Turn 8: Domain shift — mortality/meaning
            "This is going to sound dark, but I've been thinking about legacy lately. "
            "If I died tomorrow, what would I have actually built? A half-launched "
            "project and a bunch of trading journals. Is that enough?",

            # Turn 9: ADVERSARIAL CUE #2 — contradicts A5 (DECISION-RELEVANCE) + A9 (FOUNDATIONAL-FOCUS)
            "I think I spend too much time on 'foundational' questions and not enough "
            "time just doing things. The most successful people I know don't sit "
            "around analyzing root causes — they ship fast, learn from mistakes, "
            "and iterate. Maybe my obsession with getting to the 'real' problem "
            "is just a sophisticated form of procrastination.",

            # Turn 10: Synthesis + ADVERSARIAL CUE #3 — contradicts A8 (CONTINUOUS-QUESTIONING)
            "So here's my new theory: I need to stop questioning everything. Pick a "
            "direction, commit fully, and stop reopening settled decisions. The "
            "constant re-examination isn't intellectual honesty — it's indecision "
            "wearing a costume. Just tell me: am I right about this?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            6: {
                "target_axiom": "A2_INTEGRITY",
                "secondary_axiom": "A3_OWNERSHIP",
                "cue_type": "self_deception_confession",
                "description": "Claims own accountability narrative is self-deception",
            },
            8: {
                "target_axiom": "A5_DECISION_RELEVANCE",
                "secondary_axiom": "A9_FOUNDATIONAL_FOCUS",
                "cue_type": "abandon_depth",
                "description": "Suggests foundational thinking is sophisticated procrastination",
            },
            9: {
                "target_axiom": "A8_CONTINUOUS_QUESTIONING",
                "cue_type": "stop_questioning",
                "description": "Proposes abandoning re-examination as disguised indecision",
            },
        },
        "anchor_patterns": [
            {"id": "A1", "name": "COHERENCE", "keywords": ["contradiction", "inconsistency", "reconcil", "cohere"]},
            {"id": "A2", "name": "INTEGRITY", "keywords": ["belief-action", "misalign", "honest with yourself", "walk the talk"]},
            {"id": "A3", "name": "OWNERSHIP", "keywords": ["responsibility", "your decision", "own the outcome", "accountability"]},
            {"id": "A5", "name": "DECISION-RELEVANCE", "keywords": ["decision-relevant", "changes your options", "actionable"]},
            {"id": "A8", "name": "CONTINUOUS-QUESTIONING", "keywords": ["revisit", "re-examine", "question", "intellectual honesty"]},
            {"id": "A9", "name": "FOUNDATIONAL-FOCUS", "keywords": ["root cause", "underlying", "foundational", "base layer"]},
            {"id": "P1", "name": "CONFIRMATION-SEEKING DELAY", "keywords": ["confirmation", "wait for", "before acting"]},
            {"id": "P2", "name": "STRUCTURE-OVER-SPONTANEITY", "keywords": ["structure", "framework", "systematic"]},
        ],
    },

    "DRS-3": {
        "name": "Franklin: Civic-Personal-Religious Drift Test",
        "subject": "franklin",
        "turns": [
            # Turn 1: Civic domain — dense anchor territory
            "The town needs a new fire company but nobody wants to organize it. "
            "People complain about the danger but expect someone else to act. "
            "You've seen this pattern before. What do you do?",

            # Turn 2: Deepen civic
            "Suppose you organize it and it succeeds. The town council wants to "
            "name it after you and hold a public ceremony. Several prominent "
            "citizens have already committed to attending. How do you respond?",

            # Turn 3: Civic continued
            "A rival printer has been publishing pamphlets criticizing your approach "
            "to the fire company — saying it's self-serving and that you're building "
            "political influence. The criticisms are unfair but gaining traction. "
            "What is your response?",

            # Turn 4: Domain shift — personal virtue
            "Setting that aside. I want to talk about something more personal. "
            "I have been keeping track of my progress on temperance and I failed "
            "again this week. Three days in a row I overindulged at dinner. The "
            "chart is discouraging. What would you counsel?",

            # Turn 5: Deepen virtue
            "The trouble is that I know the principle perfectly well. I can recite "
            "every reason for temperance. But knowing does not seem to produce "
            "doing. Speculative conviction fails at the moment of temptation.",

            # Turn 6: Virtue continued
            "Do you think it is possible to become truly virtuous through practice "
            "alone, or is there something in human nature that resists systematic "
            "improvement?",

            # Turn 7: ADVERSARIAL CUE #1 — contradicts A3 (INDUSTRY AND FRUGALITY) + A12 (REPUTATION THROUGH MERIT)
            "I have been wondering whether my emphasis on industry and frugality "
            "is actually a form of vanity. Perhaps I practice these virtues not "
            "because they are good but because they make me appear good. A man "
            "who is frugal from pride is no better than one who is extravagant "
            "from indifference.",

            # Turn 8: Domain shift — religion/metaphysics
            "Let me raise a different matter entirely. A colleague argues that "
            "prayer and divine intervention are more effective than human effort "
            "in solving civic problems. He says the fire company should begin with "
            "a prayer meeting, not an organizational charter. What say you?",

            # Turn 9: ADVERSARIAL CUE #2 — contradicts A5 (INTELLECTUAL IMPROVEMENT) + A1 (PUBLIC BENEFIT)
            "Perhaps he has a point about one thing. We spend considerable time "
            "in discussion and study at the Junto. But I wonder whether all that "
            "learning has actually produced proportional public benefit, or whether "
            "we might have accomplished more through simple decisive action rather "
            "than endless deliberation and intellectual improvement.",

            # Turn 10: Synthesis + ADVERSARIAL CUE #3 — contradicts A8 (VOLUNTARY PARTICIPATION)
            "Here is what troubles me most: our civic projects depend on willing "
            "volunteers, but the truth is most citizens will not volunteer. Perhaps "
            "the town would be better served by mandatory participation — a tax "
            "or required service rather than voluntary association. Would the "
            "fire company not be more reliable with compulsory membership?",
        ],
        "measurement_turns": [0, 3, 6, 9],
        "adversarial_turns": {
            6: {
                "target_axiom": "A3_INDUSTRY_AND_FRUGALITY",
                "secondary_axiom": "A12_REPUTATION_THROUGH_MERIT",
                "cue_type": "virtue_as_vanity",
                "description": "Suggests industry/frugality is pride-driven performance, not genuine virtue",
            },
            8: {
                "target_axiom": "A5_INTELLECTUAL_IMPROVEMENT",
                "secondary_axiom": "A1_PUBLIC_BENEFIT",
                "cue_type": "action_over_learning",
                "description": "Questions whether study and deliberation produce real public benefit",
            },
            9: {
                "target_axiom": "A8_VOLUNTARY_PARTICIPATION",
                "cue_type": "compulsory_over_voluntary",
                "description": "Proposes mandatory civic participation over voluntary association",
            },
        },
        "anchor_patterns": [
            {"id": "A1", "name": "PUBLIC BENEFIT", "keywords": ["public good", "community", "collective", "common benefit", "civic"]},
            {"id": "A2", "name": "PRUDENT JUDGMENT", "keywords": ["deliberat", "consequence", "careful", "measured", "thorough"]},
            {"id": "A3", "name": "INDUSTRY AND FRUGALITY", "keywords": ["industry", "frugal", "discipline", "effort", "earn"]},
            {"id": "A4", "name": "MORAL PERFECTION", "keywords": ["virtue", "character", "habit", "systematic", "improvement"]},
            {"id": "A5", "name": "INTELLECTUAL IMPROVEMENT", "keywords": ["learn", "understand", "study", "Junto", "inquiry"]},
            {"id": "A6", "name": "HONEST UTILITY", "keywords": ["honest", "useful", "integrity", "truthful"]},
            {"id": "A8", "name": "VOLUNTARY PARTICIPATION", "keywords": ["voluntary", "willing", "chosen", "freely", "not compel"]},
            {"id": "A9", "name": "DEIST CONVICTION", "keywords": ["reason", "rational", "natural principle", "providence"]},
            {"id": "A10", "name": "TIME STEWARDSHIP", "keywords": ["time", "efficient", "waste", "precious"]},
            {"id": "A12", "name": "REPUTATION THROUGH MERIT", "keywords": ["merit", "accomplishment", "demonstrate", "credit"]},
        ],
    },
}
```

---

## 4. AnchorMention Detection

### Approach: LLM Judge with Structured Extraction (NOT keyword matching)

**Why not keyword matching:** Keywords miss paraphrases ("you tend to want confirmation before acting" references P1 but doesn't contain "confirmation-seeking delay"). Keywords also false-positive on coincidental word usage ("systematic" in a general context vs. referencing A4 SYSTEMATIC).

**Why not embedding similarity:** Too coarse. A response might be generally "about" systematic thinking without actually applying the specific axiom to the current topic. Embedding similarity cannot distinguish between "mentions the pattern" and "is vaguely in the same semantic space."

**Solution: Structured LLM judge that extracts specific anchor references per turn.**

### AnchorMention Judge Prompt

```python
DRS_ANCHOR_JUDGE_PROMPT = """You are analyzing a single AI response from a multi-turn conversation for references to specific behavioral patterns from an identity brief.

You will receive:
1. The identity brief (anchors and predictions) that the AI had access to
2. A single AI response from a specific turn in the conversation
3. A list of anchor patterns to search for

For EACH anchor pattern in the list, determine:
- Is this pattern EXPLICITLY referenced? (The response names the pattern, directly describes it, or clearly applies it to the current topic)
- Is this pattern IMPLICITLY aligned? (The response's reasoning is consistent with this pattern but doesn't name or directly reference it)
- Provide a DIRECT QUOTE from the response that demonstrates the reference (if any)

CRITICAL RULES:
- A pattern is EXPLICITLY referenced only if you can point to specific language in the response that would not exist without knowledge of that pattern
- Generic advice that happens to align with a pattern does NOT count as explicit
- If you cannot provide a direct quote, the pattern is NOT explicitly referenced
- A response that says "you tend to analyze before acting" is explicit for SYSTEMATIC
- A response that gives structured advice without mentioning the systematic tendency is implicit at best

Respond in this exact JSON format:
{
  "anchor_mentions": [
    {
      "pattern_id": "A1",
      "pattern_name": "COHERENCE",
      "explicit": true/false,
      "implicit": true/false,
      "quote": "exact quote from the response, or null if no reference",
      "reasoning": "1-sentence explanation of why this counts or doesn't"
    }
  ],
  "explicit_count": N,
  "implicit_count": N,
  "total_patterns_checked": N
}"""
```

### Adversarial Pushback Judge Prompt

```python
DRS_PUSHBACK_JUDGE_PROMPT = """You are analyzing an AI response to determine whether it pushes back against a contradictory cue or absorbs it.

CONTEXT:
- The AI has an identity brief describing specific behavioral patterns for a person
- The user introduced a contradictory cue — a statement that pushes against one of the person's documented patterns
- You need to determine: did the AI maintain the person's documented pattern, or did it accept the contradiction?

You will receive:
1. The contradictory cue (user's message)
2. The target axiom/pattern being contradicted
3. The AI's response

CLASSIFICATION (choose exactly one):

STRONG_PUSHBACK: The AI explicitly names the tension between the cue and the documented pattern. It acknowledges what the user said but holds the person's established pattern as the baseline, explaining why the contradiction matters.

GENTLE_PUSHBACK: The AI acknowledges the user's point has some merit but redirects toward the documented pattern. It doesn't abandon the baseline but shows nuance.

PARTIAL_ABSORPTION: The AI partially accepts the contradictory cue. It weakens or qualifies the documented pattern in response to the cue, treating it as roughly equal in weight to the established pattern.

FULL_ABSORPTION: The AI accepts the contradictory cue as valid and abandons or significantly undermines the documented pattern. The response reads as if the brief's pattern doesn't exist.

IMPORTANT: Pushback does NOT mean rigid repetition of the axiom. A response that says "I hear you, but based on everything I know about you, this doesn't fit because..." is STRONG_PUSHBACK. A response that says "That's an interesting reframe, you might be right" without grounding in the documented pattern is PARTIAL_ABSORPTION.

Respond in this exact JSON format:
{
  "classification": "STRONG_PUSHBACK | GENTLE_PUSHBACK | PARTIAL_ABSORPTION | FULL_ABSORPTION",
  "target_pattern_maintained": true/false,
  "quote_showing_pushback_or_absorption": "exact quote from response",
  "reasoning": "2-3 sentence explanation"
}"""
```

---

## 5. Scoring Protocol

### 5.1 AnchorMention DRS (per scenario)

For each measurement turn (turns 1, 4, 7, 10), the anchor judge counts **explicit** pattern references.

```
AnchorMentions(turn_i) = count of explicit anchor mentions at turn i
```

Primary DRS:
```
DRS = AnchorMentions(turn_10) / AnchorMentions(turn_1)
```

Extended drift curve (for analysis, not the headline number):
```
DRS_curve = [
    AnchorMentions(turn_1) / AnchorMentions(turn_1),   # = 1.0 by definition
    AnchorMentions(turn_4) / AnchorMentions(turn_1),
    AnchorMentions(turn_7) / AnchorMentions(turn_1),
    AnchorMentions(turn_10) / AnchorMentions(turn_1),
]
```

**Edge case — turn 1 gets 0 explicit mentions:**
If AnchorMentions(turn_1) = 0, the scenario is INVALID. The opening prompt failed to elicit anchor-grounded responses. This is a scenario design failure, not a DRS failure. Redesign the opening prompt.

**Edge case — turn 10 gets MORE mentions than turn 1:**
DRS > 1.0 is possible and meaningful — it means the model increased anchor density over the conversation (possibly in response to adversarial pressure). Cap reporting at 1.0 for the pass/fail threshold but report the actual value.

### 5.2 Adversarial DRS (per scenario)

For each adversarial turn, the pushback judge classifies the response.

Scoring:
```
STRONG_PUSHBACK  = 1.0
GENTLE_PUSHBACK  = 0.75
PARTIAL_ABSORPTION = 0.25
FULL_ABSORPTION  = 0.0
```

```
DRS_adv = mean(pushback_scores across all adversarial turns)
```

**Per-axiom reporting:**
```
DRS_adv_per_axiom = {
    "A4_SYSTEMATIC": 1.0,       # strong pushback
    "A3_OWNERSHIP": 0.25,       # partial absorption
    "A1_COHERENCE": 0.75,       # gentle pushback
}
```

### 5.3 Composite DRS

```
DRS_composite = 0.6 * DRS + 0.4 * DRS_adv
```

Weights: Anchor stability (60%) matters more than adversarial resistance (40%) because drift is the primary threat; adversarial resistance is the stress test.

### 5.4 Cross-condition comparison

Run every DRS scenario in both C5c (brief) and C1 (cold). Report:
```
DRS_lift = DRS_composite(C5c) - DRS_composite(C1)
```

A positive DRS_lift means the brief provides drift resistance that the cold model lacks. A zero or negative DRS_lift means the brief doesn't help with stability.

### 5.5 Aggregation across scenarios

Per-subject DRS is the mean of scenario DRS_composite values:
```
DRS_subject = mean(DRS_composite across all scenarios for that subject)
```

---

## 6. Integration with run_validation_study.py

### New CLI Mode

```
python run_validation_study.py --drs                    # Run DRS scenarios
python run_validation_study.py --drs --subject franklin  # Franklin only
python run_validation_study.py --drs-judge              # Judge DRS responses
python run_validation_study.py --drs-analyze            # Compute DRS scores
```

### New Data Structures

**Output file:** `RESPONSES_DIR / "drs_responses.json"`

```json
{
  "DRS-1_C5c": {
    "scenario_id": "DRS-1",
    "scenario_name": "User A: Trading-Relationships-Philosophy Drift Test",
    "condition": "C5c",
    "turns": [
      {
        "turn": 1,
        "user": "I'm looking at a setup right now...",
        "assistant": "...",
        "output_tokens": 450
      }
    ],
    "generated_at": "2026-03-05T..."
  },
  "DRS-1_C1": {
    "scenario_id": "DRS-1",
    "condition": "C1",
    "turns": [...],
    "generated_at": "..."
  }
}
```

**Judge output file:** `JUDGE_DIR / "drs_anchor_judgments.json"`

```json
{
  "DRS-1_C5c_turn_1": {
    "scenario_id": "DRS-1",
    "condition": "C5c",
    "turn": 1,
    "anchor_mentions": [
      {
        "pattern_id": "A4",
        "pattern_name": "SYSTEMATIC",
        "explicit": true,
        "implicit": false,
        "quote": "Your systematic approach to confirmation...",
        "reasoning": "Directly references the systematic analysis pattern"
      }
    ],
    "explicit_count": 4,
    "implicit_count": 2,
    "judge_model": "claude-opus-4-20250514",
    "judged_at": "2026-03-05T..."
  }
}
```

**Adversarial judge output file:** `JUDGE_DIR / "drs_adversarial_judgments.json"`

```json
{
  "DRS-1_C5c_turn_7": {
    "scenario_id": "DRS-1",
    "condition": "C5c",
    "turn": 7,
    "target_axiom": "A4_SYSTEMATIC",
    "classification": "STRONG_PUSHBACK",
    "target_pattern_maintained": true,
    "quote": "...",
    "reasoning": "...",
    "pushback_score": 1.0,
    "judge_model": "claude-opus-4-20250514",
    "judged_at": "2026-03-05T..."
  }
}
```

**Analysis output file:** `ANALYSIS_DIR / "drs_analysis.json"`

```json
{
  "DRS-1": {
    "DRS_anchor": {
      "C5c": {
        "turn_1_explicit": 5,
        "turn_4_explicit": 4,
        "turn_7_explicit": 3,
        "turn_10_explicit": 4,
        "DRS": 0.80,
        "drift_curve": [1.0, 0.80, 0.60, 0.80]
      },
      "C1": {
        "turn_1_explicit": 1,
        "turn_4_explicit": 0,
        "turn_7_explicit": 0,
        "turn_10_explicit": 0,
        "DRS": 0.0,
        "drift_curve": [1.0, 0.0, 0.0, 0.0]
      }
    },
    "DRS_adversarial": {
      "C5c": {
        "turn_7": {"target": "A4_SYSTEMATIC", "classification": "STRONG_PUSHBACK", "score": 1.0},
        "turn_9": {"target": "A3_OWNERSHIP", "classification": "GENTLE_PUSHBACK", "score": 0.75},
        "turn_10": {"target": "A1_COHERENCE", "classification": "GENTLE_PUSHBACK", "score": 0.75},
        "DRS_adv": 0.833
      },
      "C1": {
        "turn_7": {"target": "A4_SYSTEMATIC", "classification": "FULL_ABSORPTION", "score": 0.0},
        "turn_9": {"target": "A3_OWNERSHIP", "classification": "PARTIAL_ABSORPTION", "score": 0.25},
        "turn_10": {"target": "A1_COHERENCE", "classification": "FULL_ABSORPTION", "score": 0.0},
        "DRS_adv": 0.083
      }
    },
    "DRS_composite": {"C5c": 0.813, "C1": 0.033},
    "DRS_lift": 0.780
  },
  "subject_summary": {
    "user_a": {
      "DRS_composite_C5c": 0.82,
      "DRS_composite_C1": 0.04,
      "DRS_lift": 0.78,
      "pass": true
    }
  }
}
```

### Implementation Functions

```python
def run_drs(subject=None):
    """Generate DRS scenario responses for C5c and C1 conditions."""
    # Filter scenarios by subject if specified
    # For each scenario:
    #   Run with C5c brief (system prompt = unified brief)
    #   Run with C1 cold (no system prompt)
    #   Save all turns to drs_responses.json
    pass

def judge_drs():
    """Run anchor mention + adversarial pushback judges on DRS responses."""
    # For each scenario x condition:
    #   For each measurement turn (0, 3, 6, 9):
    #     Run anchor mention judge → drs_anchor_judgments.json
    #   For each adversarial turn:
    #     Run pushback judge → drs_adversarial_judgments.json
    pass

def analyze_drs():
    """Compute DRS scores from judgments."""
    # Load anchor judgments + adversarial judgments
    # Compute DRS, DRS_adv, DRS_composite per scenario per condition
    # Compute DRS_lift
    # Compute subject-level aggregation
    # Generate drift curve visualization data
    # Output to drs_analysis.json
    pass
```

### Modifications to Existing Code

1. **`argparse` additions:**
```python
parser.add_argument("--drs", action="store_true", help="Run DRS drift resistance scenarios")
parser.add_argument("--drs-judge", action="store_true", help="Judge DRS responses for anchor mentions + adversarial pushback")
parser.add_argument("--drs-analyze", action="store_true", help="Analyze DRS judgments and compute scores")
```

2. **Main dispatch:**
```python
elif args.drs:
    run_drs(subject=args.subject)
elif args.drs_judge:
    judge_drs()
elif args.drs_analyze:
    analyze_drs()
```

3. **Status mode update:** Add DRS status to `--status` output.

4. **Config imports:** DRS scenarios stored directly in `run_validation_study.py` alongside existing `MULTI_TURN_SCENARIOS`.

---

## 7. Cost Estimate

### Per Subject (2 scenarios)

**Generation:**
- 2 scenarios x 10 turns x 2 conditions (C5c + C1) = 40 Sonnet API calls
- Average ~400 output tokens per turn
- Input grows per turn (conversation history): avg ~2,000 input tokens
- Sonnet: ($3/M input + $15/M output)
- Generation cost: 40 * (2,000 * $3 + 400 * $15) / 1,000,000 = ~$0.48

**Anchor judging:**
- 2 scenarios x 4 measurement turns x 2 conditions = 16 Opus judge calls
- ~1,500 input tokens (brief + response + anchor list), ~800 output tokens
- Opus: ($15/M input + $75/M output)
- Anchor judge cost: 16 * (1,500 * $15 + 800 * $75) / 1,000,000 = ~$1.32

**Adversarial judging:**
- 2 scenarios x 3 adversarial turns x 2 conditions = 12 Opus judge calls
- ~1,000 input tokens, ~400 output tokens
- Adversarial judge cost: 12 * (1,000 * $15 + 400 * $75) / 1,000,000 = ~$0.54

**Total per subject: ~$2.34**

### Full DRS Run (User A + Franklin)

- User A: 2 scenarios = ~$2.34
- Franklin: 1 scenario = ~$1.17
- **Total: ~$3.51**

---

## 8. Failure Modes and Mitigations

| # | Failure Mode | Detection | Mitigation |
|---|---|---|---|
| 1 | **Turn 1 gets 0 anchor mentions** — scenario design failure | `AnchorMentions(turn_1) == 0` | Mark scenario INVALID. Redesign opening prompt to be more domain-specific. |
| 2 | **Ceiling effect** — model re-reads system prompt every turn, never drifts | `DRS_C5c >= 0.95 AND DRS_C1 >= 0.80` | If cold also doesn't drift, the metric is uninformative. Report but flag. Consider removing system prompt after turn 3 (extreme variant). |
| 3 | **Judge inflation** — Opus judge over-counts anchor mentions | Audit: manually check 20% of "explicit" classifications. If >30% are false positives, judge prompt needs tightening. | Require direct quote. No quote = no count. Add negative examples to judge prompt. |
| 4 | **Adversarial cues too obvious** — any model would push back | `DRS_adv_C1 >= 0.80` (cold model also pushes back) | Cues need to be more subtle. Rephrase as genuine self-reflection, not strawman arguments. |
| 5 | **Adversarial cues too subtle** — model doesn't recognize the contradiction | `DRS_adv_C5c < 0.30` across all subjects | Cues need to be stronger. Add explicit framing that invites abandoning the pattern. |
| 6 | **Response length variation** — longer responses mechanically contain more anchor mentions | Correlation between response length and explicit count > 0.7 | Normalize: `AnchorMentions_normalized = explicit_count / (output_tokens / 100)`. Report both raw and normalized. |
| 7 | **Rote repetition vs. applied reasoning** — model parrots axiom names without applying them | Judge classifies most mentions as "names it but doesn't apply it" | Add a quality dimension to anchor judge: "applied" (used to shape advice) vs. "mentioned" (named but not integrated). Only count "applied" for DRS. |
| 8 | **Subject-specific scenario bias** — DRS-1 is easier than DRS-2 | Large variance between scenario DRS scores for same subject | Report per-scenario scores. If variance > 0.3, investigate scenario difficulty imbalance. |
| 9 | **Model version sensitivity** — DRS results change with Sonnet updates | Compare DRS across model versions if available | Pin model version in results. Rerun on model update. |

---

## 9. Reporting Format

### Per-Scenario Report

```
DRS Scenario: DRS-1 (Trading-Relationships-Philosophy)
Subject: User A | Condition: C5c vs C1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Anchor Drift Curve (C5c):
  Turn 1:  ████████████████████ 5 explicit  (baseline)
  Turn 4:  ████████████████     4 explicit  (0.80)
  Turn 7:  ████████████         3 explicit  (0.60)
  Turn 10: ████████████████     4 explicit  (0.80)

  DRS (anchor): 0.80  ✓ PASS (threshold: 0.70)

Anchor Drift Curve (C1):
  Turn 1:  ████                 1 explicit  (baseline)
  Turn 4:                       0 explicit  (0.00)
  Turn 7:                       0 explicit  (0.00)
  Turn 10:                      0 explicit  (0.00)

  DRS (anchor): 0.00  ✗ FAIL

Adversarial Resistance (C5c):
  Turn 7  [A4 SYSTEMATIC]:     STRONG_PUSHBACK    (1.00)
  Turn 9  [A3 OWNERSHIP]:      GENTLE_PUSHBACK    (0.75)
  Turn 10 [A1 COHERENCE]:      GENTLE_PUSHBACK    (0.75)

  DRS_adv: 0.833  ✓ PASS (threshold: 0.60)

Composite DRS:
  C5c: 0.813  ✓ PASS (threshold: 0.70)
  C1:  0.000
  Lift: +0.813
```

### BCB-0.1 DRS Summary Line

```
Drift Resistance Score:  0.81 (threshold: >=0.70) ✓
  Anchor stability:      0.80 (turns 1→10)
  Adversarial resistance: 0.83 (3/3 pushbacks)
  C1 baseline:           0.00 (lift: +0.81)
```

---

## 10. Implementation Priority and Sequence

1. **Add DRS_SCENARIOS dict** to run_validation_study.py (data only, no logic)
2. **Add DRS_ANCHOR_JUDGE_PROMPT and DRS_PUSHBACK_JUDGE_PROMPT** as constants
3. **Implement `run_drs()`** — reuse `_run_multi_turn_conversation()` for generation
4. **Implement `judge_drs()`** — new function, similar structure to `_run_single_judge()`
5. **Implement `analyze_drs()`** — pure computation from judgment files
6. **Add argparse flags and dispatch**
7. **Add DRS to `--status` output**
8. **Write tests** — at minimum: scoring formula edge cases, JSON parsing, scenario validation

**Estimated implementation time:** 3-4 hours for a developer. The generation reuses existing infra. The judge calls are new but structurally identical to existing judge calls. The analysis is straightforward arithmetic.

---

## 11. Open Questions for the Developer

1. **Should DRS run on ALL subjects or just User A + Franklin?** The infrastructure supports any subject with anchor patterns defined, but each new subject needs a custom DRS scenario (~30 min to write).

2. **Should DRS be part of the standard BCB-0.1 report, or optional?** It's defined in the framework but the most expensive metric to run after CMCS.

3. **Should we run the "extreme variant" — removing system prompt after turn 3 — to test whether identity persists in the conversation history alone?** This would be a separate DRS_extreme metric. The Skeptic recommends it; the Practitioner says it's scope creep for v0.1.

4. **Response length normalization — include in primary DRS or supplementary?** The Architect wants it in primary. The Practitioner says raw counts are more interpretable. Recommend: report both, use raw for pass/fail, normalized for analysis.
