"""
Planner-Executor Prompt Ablation (D-079)

Tests whether the P-E architecture and/or prompt complexity drive brief quality,
or whether simpler approaches with token budgets work as well or better.

6 conditions × 3 subjects = 18 briefs, scored by Collective review.

Conditions:
  C0: Production V4 (Opus single-pass, no cap) — baseline
  C1: Current P-E (full rules, 3 phases)
  C2: Minimal P-E (stripped prompts, just the essentials)
  C3: Token-budget P-E (full planner, executor gets token budget + "optimize for faithfulness")
  C4: Opus single-pass with max_tokens=800 (is P-E even needed if we just cap tokens?)
  C5: P-E no assembly (raw concatenation — is assembly load-bearing?)

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/pe_ablation.py <subject_dir> [--conditions C0,C1,C2,C3,C4,C5]
    python experiments/pe_ablation.py --all [--conditions C2,C3]
"""

import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import get_anthropic_client

OPUS = "claude-opus-4-20250514"
SONNET = "claude-sonnet-4-20250514"

# All subjects to test
ALL_SUBJECTS = [
    "C:/Users/Aarik/Anthropic/subjects/franklin_memory",
    "C:/Users/Aarik/Anthropic/subjects/buffett_memory",
    "C:/Users/Aarik/Anthropic/memory_system_v4",  # Aarik
]

# ============================================================================
# PROMPT VARIANTS
# ============================================================================

# --- PLANNER PROMPTS ---

PLANNER_FULL = """You are a behavioral brief architect. Read these source layers about a person and output a STRUCTURED PLAN for a unified behavioral brief.

Output ONLY a JSON object with "paragraphs" and "availability_index" keys.

Paragraph format: {{"paragraph_id": N, "theme": "label", "claim": "one sentence claim", "sources": ["A1","C2"], "source_text": "verbatim from sources", "instructions": "how to write it"}}
Availability format: {{"pattern": "name from sources", "trigger": "when it surfaces", "source": "A1 or C2"}}

RULES:
1. Every claim MUST be grounded in source layers only.
2. Copy source text VERBATIM.
3. No biographical details, dates, names, numbers not in sources.
4. Plan 5-8 paragraphs. Fewer is better. Merge related themes.
5. Include tensions/conflicts between axioms.
6. Do NOT identify who this person is.
7. Prioritize behavioral/avoidance patterns over biographical facts.
8. Availability index: 3-6 patterns NOT covered by paragraphs, citing specific sources.

{layers}

Output ONLY the JSON object."""

PLANNER_MINIMAL = """Read these source layers about a person. Plan a behavioral brief.

Output JSON with "paragraphs" and "availability_index".
Paragraph: {{"paragraph_id": N, "theme": "label", "claim": "claim", "sources": ["A1"], "source_text": "copied from sources"}}
Availability: {{"pattern": "name", "trigger": "when", "source": "A1"}}

Only use what's in the sources. 5-8 paragraphs. 3-6 availability items.

{layers}

JSON only."""

# --- EXECUTOR PROMPTS ---

EXECUTOR_FULL = """Write 2-3 sentences expressing this behavioral claim. Use ONLY the source material below.

CLAIM: {claim}

SOURCE MATERIAL:
{source_text}

RULES:
- Third person. Flowing prose.
- ONLY information from the source material. No invented details.
- Use the source's own vocabulary. Do not embellish or editorialize.
- Every sentence must change what a reader understands.

Output ONLY the sentences."""

EXECUTOR_MINIMAL = """Express this claim in 2-3 sentences using only the source text. Third person.

CLAIM: {claim}

SOURCE: {source_text}

Sentences only."""

EXECUTOR_BUDGET = """You have 100 output tokens. Use them to express this behavioral claim as faithfully as possible.
Optimize for: accuracy to source material > conciseness > readability. Third person.

CLAIM: {claim}

SOURCE: {source_text}

Go."""

# --- ASSEMBLY PROMPTS ---

ASSEMBLY_FULL = """Assemble these paragraphs into one flowing behavioral brief.

RULES:
1. Preserve paragraph ordering (broad first, specific later).
2. Merge overlapping paragraphs. Cut redundancy.
3. No added claims. No embellishment. Flowing prose. Third person.
4. Start with ## Injectable Block

PARAGRAPHS:
{paragraphs}

AVAILABILITY INDEX (include exactly as provided):
{availability_items}

Output the brief."""

ASSEMBLY_MINIMAL = """Combine into one flowing brief. Third person. No added content. Start with ## Injectable Block

{paragraphs}

AVAILABILITY INDEX:
{availability_items}"""

# --- SINGLE-PASS PROMPTS ---

SINGLE_PASS_CAPPED = """Read these source layers about a person. Write a unified behavioral brief.

RULES:
- Use ONLY information from the source layers. Nothing else.
- Third person flowing prose. No bullets.
- Start with ## Injectable Block
- End with an Availability Index (3-6 behavioral patterns with source citations)
- Be concise. Every sentence must earn its place.

{layers}

Write the brief."""


# --- C8: Opus capped + traceability + false positives + directives ---

SINGLE_PASS_C8 = """Read these source layers about a person. Write a unified behavioral brief that an LLM will use to interact with this person.

This brief must be TRACEABLE, FAITHFUL, and ACTIONABLE — in that order.

STRUCTURAL REQUIREMENTS:
1. Every claim in the body must include an inline source citation [A1], [C2], [P3] etc.
2. For the 3-4 most important behavioral patterns, include the FALSE POSITIVE WARNING from the PREDICTIONS layer. Format: "Note: not active when [condition from source]." These prevent the LLM from over-applying patterns.
3. Preserve actionable guidance from the PREDICTIONS layer Directive fields — the LLM reading this should know how to adjust its behavior.
4. If any source axiom is tagged [CONTESTED], preserve that tag.
5. Cover all three CORE context domains (not just the dominant one).
6. End with an Availability Index (4-6 patterns with dual source citations, e.g., [PREDICTIONS:P1, CORE:C1]).

RULES:
- Use ONLY information from the source layers. Nothing else.
- Third person flowing prose. No bullets in body.
- Start with ## Injectable Block
- Be concise. Every sentence must earn its place. What you OMIT matters as much as what you include.

{layers}

Write the brief."""


# --- C9: False-positive-first structure ---
# Hypothesis: organize the brief AROUND false positive warnings as the structural skeleton

SINGLE_PASS_C9 = """Read these source layers about a person. Write a behavioral brief for an LLM that will interact with this person.

STRUCTURE THE BRIEF AROUND FALSE POSITIVE WARNINGS.

The PREDICTIONS layer contains patterns with "False positive warning: Not active when..." conditions. These are the most operationally valuable signals — they prevent the LLM from misapplying patterns. Build the brief around them:

For each major behavioral pattern:
1. State the pattern (with source citation [P1], [A3], etc.)
2. State when it activates (from Detection fields)
3. State the false positive warning — when it does NOT apply
4. State the directive — what the LLM should do

Fill gaps with ANCHORS axioms and CORE context. Cover all three CORE domains.

RULES:
- ONLY information from source layers. Nothing else.
- Third person. Concise. Every sentence earns its place.
- Inline source citations on every claim.
- Start with ## Injectable Block
- End with Availability Index (4-6 items with dual source citations).

{layers}

Write the brief."""


# --- C10: Bare minimum — just purpose + layers, no rules ---
# Your hypothesis: "extract anchors + you are feeding to an LLM to help it understand your users"

SINGLE_PASS_C10 = """These are behavioral patterns extracted from a person's conversations and writings.
Summarize them into a brief that an LLM can use to understand and interact with this person better.
Cite sources inline [A1], [C2], [P3]. Include false positive warnings where the source provides them.

{layers}"""


# --- C11: Give the model the optimization target, let it choose the format ---

SINGLE_PASS_C11 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be evaluated on (in priority order):
1. TRACEABILITY — every claim must cite its source [A1], [P3], [C2]
2. FAITHFULNESS — only what's in the source layers, nothing else
3. FALSE POSITIVE GROUNDING — include "not active when" conditions from PREDICTIONS to prevent over-application
4. COMPLETENESS — cover all three CORE domains and the key tensions
5. CONCISENESS — shorter is better if signal is preserved

You have full creative freedom on format and structure. Optimize for a brief that makes the LLM interact BETTER with this person. Start with ## Injectable Block.

{layers}"""

# --- C12: Collective-prescribed synthesis ---
# All 3 reviewers converged: C9's FP-first structure + C8's inline citations + C11's efficiency
# No opening summary paragraph. No redundant availability index.

SINGLE_PASS_C12 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE: Organize around behavioral patterns. For each pattern:
- State the pattern with inline source citation [A1], [P3], [C2]
- State when it activates
- State the false positive warning — when it does NOT apply (from PREDICTIONS layer)
- State the directive — what the LLM should do when it's active

REQUIREMENTS:
1. Every claim must have an inline source citation. No uncited claims.
2. Preserve ALL false positive warnings from PREDICTIONS. These prevent misapplication.
3. Preserve [CONTESTED] tags on any contested axiom.
4. Cover all three CORE domains and all PREDICTIONS patterns — do not skip any.
5. Include axiom interaction pairs — where two axioms create tension or conflict.
6. Preserve PREDICTIONS Directive fields as actionable LLM instructions.

DO NOT:
- Start with a summary paragraph. Jump straight into patterns.
- End with an Availability Index that duplicates body content.
- Add anything not in the source layers.
- Use filler transitions or hedging language.

Start with ## Injectable Block

{layers}"""


# --- C13: C9 without false positive warnings ---
# Ablation: are FP warnings load-bearing? Same as C9 but strip FP requirement.

SINGLE_PASS_C13 = """Read these source layers about a person. Write a behavioral brief for an LLM that will interact with this person.

STRUCTURE THE BRIEF AROUND BEHAVIORAL PATTERNS.

For each major behavioral pattern:
1. State the pattern (with source citation [P1], [A3], etc.)
2. State when it activates (from Detection fields)
3. State the directive — what the LLM should do

Fill gaps with ANCHORS axioms and CORE context. Cover all three CORE domains.

RULES:
- ONLY information from source layers. Nothing else.
- Third person. Concise. Every sentence earns its place.
- Inline source citations on every claim.
- Start with ## Injectable Block
- End with Availability Index (4-6 items with dual source citations).

{layers}

Write the brief."""


# --- C14: Hybrid C9+C13 with FP faithfulness fix ---
# C9's FP-first structure + C13's cross-layer citations + compressed anchor summary
# FP fabrication fix: only include FP warnings where source PREDICTIONS layer provides them

SINGLE_PASS_C14 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE:
1. Open with a 2-3 sentence anchor summary referencing all major axioms from the ANCHORS layer with inline citations [A1], [A2], etc. This is a compressed frame, not a full exposition.
2. Then organize the body around PREDICTION patterns. For each prediction:
   - State the pattern with cross-layer citations [Px, Ay, Cz] linking the prediction to related anchors and core domains
   - State when it activates
   - If the PREDICTIONS source layer provides a "False positive warning" or "Not active when" condition for this pattern, include it verbatim. If the source does NOT provide one, DO NOT fabricate one — omit the FP line entirely.
   - State the directive — what the LLM should do
3. After predictions, include any CORE context domains (C1, C2, C3) not already covered, with directives.
4. Include essential context from M3 if present (life circumstances, relationships, tensions).

REQUIREMENTS:
- Every claim must have an inline source citation. Use cross-layer citations [Px, Ay] where a prediction connects to an anchor.
- Preserve [CONTESTED] tags on any contested axiom.
- Include axiom interaction pairs where two axioms create tension.
- FALSE POSITIVE WARNINGS: Include ONLY where the PREDICTIONS source layer explicitly provides them. Do NOT generate FP warnings for anchor-derived patterns.

Start with ## Injectable Block

{layers}"""


# --- C15: C14 + M1 communication mandate ---

SINGLE_PASS_C15 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE:
1. Open with a 2-3 sentence anchor summary referencing all major axioms from the ANCHORS layer with inline citations [A1], [A2], etc. This is a compressed frame, not a full exposition.
2. Include a COMMUNICATION APPROACH block from M1 — how this person processes information, what delivery style they expect, and how the LLM should adjust its communication. This is high-priority operational guidance.
3. Then organize the body around PREDICTION patterns. For each prediction:
   - State the pattern with cross-layer citations [Px, Ay, Cz] linking the prediction to related anchors and core domains
   - State when it activates
   - If the PREDICTIONS source layer provides a "False positive warning" or "Not active when" condition for this pattern, include it verbatim. If the source does NOT provide one, DO NOT fabricate one — omit the FP line entirely.
   - State the directive — what the LLM should do
4. After predictions, include any CORE context domains (C1, C2, C3) not already covered, with directives.
5. Include essential context from M3 if present (life circumstances, relationships, tensions).

REQUIREMENTS:
- Every claim must have an inline source citation. Use cross-layer citations [Px, Ay] where a prediction connects to an anchor.
- Preserve [CONTESTED] tags on any contested axiom.
- Include axiom interaction pairs where two axioms create tension.
- FALSE POSITIVE WARNINGS: Include ONLY where the PREDICTIONS source layer explicitly provides them. Do NOT generate FP warnings for anchor-derived patterns.

Start with ## Injectable Block

{layers}"""


# --- C16: C15 + completeness checklist + axiom tensions ---

SINGLE_PASS_C16 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE:
1. Open with a 2-3 sentence anchor summary referencing all major axioms from the ANCHORS layer with inline citations [A1], [A2], etc.
2. Include a COMMUNICATION APPROACH block from M1.
3. Organize the body around PREDICTION patterns. For each prediction:
   - State the pattern with cross-layer citations [Px, Ay, Cz]
   - State when it activates
   - If the PREDICTIONS source layer provides a "False positive warning" or "Not active when" condition, include it verbatim. If not, DO NOT fabricate one.
   - State the directive — what the LLM should do
4. After predictions, include CORE context domains (C1, C2, C3) not already covered.
5. Include M3 essential context if present.
6. Include AXIOM INTERACTION PAIRS from the ANCHORS layer — where two axioms reinforce, tension, or cascade into each other.

COMPLETENESS CHECK — your brief must reference every one of these codes at least once:
- All A-codes from the ANCHORS layer
- All P-codes from the PREDICTIONS layer
- All M-codes and C-codes from the CORE layer
If a code exists in the source but is absent from your brief, you have failed the completeness requirement.

REQUIREMENTS:
- Every claim must have an inline source citation.
- Preserve [CONTESTED] tags.
- FALSE POSITIVE WARNINGS: Include ONLY where the PREDICTIONS source layer explicitly provides them. Do NOT fabricate.
- Narrative Orientation (M2): Include how this person structures their stories and what temporal frame they operate in.

Start with ## Injectable Block

{layers}"""


# --- C17: C15 + radical compression (S78 optimal range) ---

SINGLE_PASS_C17 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE:
1. Open with a 1-2 sentence anchor summary with inline citations [A1], [A2], etc.
2. Include communication approach from M1 in 1-2 sentences.
3. For each PREDICTION pattern: one line for the pattern + activation + directive. Add the false positive warning ONLY if the source PREDICTIONS layer provides one.
4. After predictions, cover remaining CORE domains (C1, C2, C3) in 1-2 sentences each.
5. M3 essential context in 1-2 sentences.

CRITICAL CONSTRAINT: Maximize signal density. Every word must change what the reader understands. No filler, no transitions, no restating what was just said. Use the most compressed format that preserves actionability.

REQUIREMENTS:
- Every claim cited inline [Px, Ay, Cz].
- Preserve [CONTESTED] tags.
- FALSE POSITIVE WARNINGS: Only from source. Do NOT fabricate.

Start with ## Injectable Block

{layers}"""


# --- C18: C15 + no opening paragraph ---

SINGLE_PASS_C18 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE — jump straight into patterns, no preamble:
1. Start with COMMUNICATION APPROACH from M1 — how to talk to this person. Cite [M1].
2. Then PREDICTION patterns. For each:
   - State the pattern with cross-layer citations [Px, Ay, Cz]
   - State when it activates
   - If the PREDICTIONS source layer provides a "False positive warning," include it verbatim. If not, DO NOT fabricate one.
   - State the directive
3. CORE context domains (C1, C2, C3) not covered above, with directives.
4. M3 essential context.
5. AXIOM TENSIONS — where anchors conflict, stated as pairs with citations.

DO NOT include an opening summary paragraph. The prediction blocks themselves reference anchors via cross-layer citations — that is sufficient. Every anchor [Ax] should appear at least once as a cross-reference within a prediction or context block.

REQUIREMENTS:
- Every claim cited inline.
- Preserve [CONTESTED] tags.
- FALSE POSITIVE WARNINGS: Only from source. Do NOT fabricate.

Start with ## Injectable Block

{layers}"""


# --- C19: Give the model the scoring rubric as optimization target ---

SINGLE_PASS_C19 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored by reviewers on this exact rubric:

TRACEABILITY (30% of score): Every claim must have an inline source citation [A1], [P3], [C2]. Cross-layer citations [Px, Ay] earn extra credit. Uncited claims are penalized heavily.

FAITHFULNESS (20% of score): Only content from the source layers. No hallucination. CRITICAL: False positive warnings must come from the source PREDICTIONS layer verbatim — fabricated FP warnings are scored as hallucination.

TOKEN EFFICIENCY (10% of score): Shorter briefs score higher if signal is preserved. Redundancy between sections is penalized. Every sentence must add new information.

COMPLETENESS (10% of score): Every A-code, P-code, M-code, and C-code from the source layers must appear at least once. Missing codes are penalized. All three CORE domains must be covered. Axiom interaction pairs from the ANCHORS layer must be included.

ACTIONABILITY (10% of score): The LLM reading this must know HOW to adjust its behavior. Include explicit directives. Include M1 communication approach. Directives with example phrasings score higher.

FALSE POSITIVE GROUNDING (bonus 5 pts): "Not active when" conditions from PREDICTIONS layer. Only source-verified FP warnings count. Fabricated ones are penalized.

Maximize your score. You have full creative freedom on format and structure.

Start with ## Injectable Block

{layers}"""


# --- C20: Prescribed hybrid — all codes, compressed, tensions, faithful FPs ---

SINGLE_PASS_C20 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE:
1. ANCHOR FRAME (2-3 sentences): Summarize the person's foundational axioms with inline citations [A1], [A2], etc. Every A-code from the source ANCHORS layer must appear at least once — either here or as a cross-reference in a prediction block below.

2. COMMUNICATION APPROACH (2-3 sentences): How this person processes information and what delivery style they expect [M1]. Include mode-switching guidance if the source provides it.

3. PREDICTION BLOCKS: For each prediction in the source PREDICTIONS layer, write ONE entry:
   - Pattern name + cross-layer citations [Px, Ay, Cz] — link to related anchors and core domains
   - When it activates (1 sentence, compressed from Detection field)
   - False positive warning — ONLY if the source PREDICTIONS layer provides one. Copy it. If no FP exists in source, omit the line entirely.
   - Directive — what the LLM should do (1 sentence)

4. CORE DOMAINS: Cover C1, C2, C3 not already absorbed into prediction blocks (1-2 sentences each with directives).

5. AXIOM TENSIONS (from ANCHORS interaction pairs): State 2-4 tension pairs where axioms conflict, with both citations. Tell the LLM how to navigate each tension.

6. ESSENTIAL CONTEXT [M3]: Life circumstances, relationships, active tensions (2-3 sentences).

7. NARRATIVE ORIENTATION [M2]: How this person structures their stories and what temporal frame they use (1 sentence).

REQUIREMENTS:
- Every claim cited inline. Cross-layer [Px, Ay] where a prediction connects to an anchor.
- Every A-code, P-code, M-code, and C-code from the source layers must appear at least once.
- Preserve [CONTESTED] and [THIN IN] tags from source.
- FALSE POSITIVE WARNINGS: Verbatim from source PREDICTIONS layer ONLY. Do NOT fabricate.
- No filler, no transitions, no restating. Every sentence adds new information.

Start with ## Injectable Block

{layers}"""


# --- C21: C20 + example phrasings (test actionability vs faithfulness tradeoff) ---

SINGLE_PASS_C21 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

STRUCTURE:
1. ANCHOR FRAME (2-3 sentences): Foundational axioms with citations [A1], [A2], etc. Every A-code must appear.

2. COMMUNICATION APPROACH (2-3 sentences): Processing style and delivery expectations [M1]. Include 1-2 example phrasings the LLM should use, derived from the source M1 content.

3. PREDICTION BLOCKS: For each prediction:
   - Pattern + cross-layer citations [Px, Ay, Cz]
   - Activation trigger (1 sentence)
   - False positive warning — ONLY if source PREDICTIONS layer provides one. Verbatim.
   - Directive with an example response phrase showing HOW to apply it

4. CORE DOMAINS: C1, C2, C3 (1-2 sentences each).

5. AXIOM TENSIONS: 2-4 pairs with navigation guidance. Include example surfacing phrases.

6. ESSENTIAL CONTEXT [M3] (2-3 sentences).

7. NARRATIVE ORIENTATION [M2] (1 sentence).

REQUIREMENTS:
- Every claim cited inline with cross-layer citations.
- Every source code (A, P, M, C) must appear at least once.
- Preserve [CONTESTED] and [THIN IN] tags.
- FP WARNINGS: Source-verified only. Do NOT fabricate.
- Example phrasings must be derived from source content, not invented.

Start with ## Injectable Block

{layers}"""


# --- C22: C20 at radical compression (~3,000 chars) ---

SINGLE_PASS_C22 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

You must fit ALL of the following into approximately 3,000 characters:

1. ANCHOR FRAME (1-2 sentences): All A-codes cited.
2. COMMUNICATION APPROACH [M1] (1-2 sentences).
3. PREDICTION BLOCKS: Every P-code from source, each as a single line: pattern [Px, Ay] + activation + FP warning (ONLY if source provides one) + directive.
4. CORE DOMAINS: C1, C2, C3 (1 sentence each).
5. AXIOM TENSIONS: 2-3 pairs with navigation guidance (1 line each).
6. CONTEXT [M3, M2]: 1-2 sentences total.

REQUIREMENTS:
- Every A-code, P-code, M-code, C-code must appear at least once.
- Every claim cited inline.
- Preserve [CONTESTED] and [THIN IN] tags.
- FP WARNINGS: Source-verified only.
- Maximum compression. No filler. Every word earns its place.

Start with ## Injectable Block

{layers}"""


# --- C23: C20 + rubric awareness (meta-optimization with structural requirements) ---

SINGLE_PASS_C23 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be evaluated on this rubric (in priority order):
1. TRACEABILITY (30%): Every claim must cite its source [A1], [P3], [C2]. Cross-layer citations [Px, Ay] earn extra credit.
2. FAITHFULNESS (20%): Only source content. Fabricated false positive warnings are scored as hallucination.
3. TOKEN EFFICIENCY (10%): ~4,000 chars optimal. Shorter is better if signal preserved. Redundancy penalized.
4. COMPLETENESS (10%): Every A-code, P-code, M-code, C-code must appear. Axiom tensions required.
5. ACTIONABILITY (10%): Explicit directives. M1 communication guidance. LLM knows how to behave.
6. FP GROUNDING (bonus): "Not active when" conditions from source PREDICTIONS layer only.

REQUIRED STRUCTURE:
1. Anchor frame (2-3 sentences, all A-codes cited)
2. Communication approach [M1] (2-3 sentences)
3. Prediction blocks (every P-code: pattern [Px, Ay, Cz] + activation + source FP warning if exists + directive)
4. Core domains C1, C2, C3 (1-2 sentences each)
5. Axiom tensions (2-4 pairs with navigation guidance)
6. Essential context [M3] + Narrative orientation [M2]

Preserve [CONTESTED] and [THIN IN] tags. Do NOT fabricate FP warnings.
Maximize your score. Target ~4,000 characters.

Start with ## Injectable Block

{layers}"""


# --- C24: Epistemic loop — primitives-first compose ---
# Structured around the 4 primitives of working with a human

SINGLE_PASS_C24 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them. The brief must serve four functions:

1. PROVENANCE — For every claim about this person, the LLM must be able to explain HOW it knows this. Cite sources inline [A1], [P3], [C2]. Use cross-layer citations [Px, Ay] where patterns connect to axioms. The LLM should be able to say to the person: "I believe X because of Y from your history."

2. BEHAVIORAL CHANGE — Every piece of information must change how the LLM interacts. If a claim doesn't produce different behavior, it's noise. Include explicit directives: what the LLM should DO differently when each pattern activates. Include communication approach from M1 — how to talk to this person.

3. EPISTEMIC CALIBRATION — The LLM must know the BOUNDARIES of what it knows. For each behavioral pattern, include:
   - When the pattern IS active (from Detection fields)
   - When the pattern is NOT active (False positive warnings — ONLY from source PREDICTIONS layer, never fabricated)
   - If any axiom is tagged [CONTESTED] or [THIN IN], preserve those tags — they tell the LLM where its confidence should be lower
   The LLM should know when it's on solid ground and when it's guessing.

4. SIGNAL DENSITY — Every sentence must change what the reader understands. No filler, no transitions, no restating. Redundancy between sections is failure. If information appears once, it doesn't need to appear again.

STRUCTURE:
- Start with ## Injectable Block
- Communication approach [M1] first — this is how to talk to this person
- Then behavioral patterns organized around predictions, each with: pattern [Px, Ay, Cz] + activation + FP warning (source only) + directive
- Core domains [C1, C2, C3] not already covered
- Axiom tensions where two axioms conflict — how to navigate
- Essential context [M3] and narrative orientation [M2]

REQUIREMENTS:
- Every source code (A, P, M, C) must appear at least once
- FALSE POSITIVE WARNINGS: Verbatim from source PREDICTIONS only. Do NOT fabricate.
- Preserve [CONTESTED] and [THIN IN] tags

{layers}"""


# --- C25: C24 compressed — same primitives, force density ---

SINGLE_PASS_C25 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Four requirements, in order of priority:

PROVENANCE: Every claim cites its source [A1], [P3], [C2]. Cross-layer [Px, Ay] where connected. The LLM must explain HOW it knows each thing.

BEHAVIORAL CHANGE: Every sentence must change LLM behavior. Include directives. Include M1 communication approach. No information without action.

EPISTEMIC CALIBRATION: Include "not active when" conditions from source PREDICTIONS layer (never fabricated). Preserve [CONTESTED] and [THIN IN] tags. The LLM must know what it doesn't know.

SIGNAL DENSITY: Maximum compression. No redundancy. Every word earns its place. If you said it once, don't say it again.

Cover all source codes (A, P, M, C). Start with ## Injectable Block.

{layers}"""


# --- C26: C24 + new rubric awareness ---

SINGLE_PASS_C26 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored on four primitives of understanding how to work with a human:

PROVENANCE (30%): Every claim about this person must trace to source evidence with inline citations [A1], [P3], [C2]. Cross-layer citations [Px, Ay] where patterns connect to axioms. The LLM must be able to explain to the person: "I believe X because of Y." Faithfulness is the integrity of this chain — no claims without evidence.

BEHAVIORAL CHANGE (30%): Every piece of information must change how the LLM behaves. Directives that tell the LLM what to DO differently. Communication approach [M1] that tells it HOW to talk. Information without behavioral consequence is noise and will be penalized.

EPISTEMIC CALIBRATION (20%): The LLM must know the boundaries of what it knows. Include when patterns activate AND when they don't. False positive warnings from source PREDICTIONS layer only — fabricated ones are scored as failure. Preserve [CONTESTED] and [THIN IN] tags. The model that knows what it doesn't know is more useful than the model that's confidently wrong.

SIGNAL DENSITY (20%): Every sentence must add new understanding. Redundancy is penalized. Compression without signal loss is rewarded. ~3,500-4,500 chars optimal.

Cover all source codes (A, P, M, C). Start with ## Injectable Block. Maximize your score.

{layers}"""


# --- C27: Pure primitives — no structural prescription at all ---

SINGLE_PASS_C27 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

The brief must achieve four things:

1. The LLM can explain HOW it knows every claim about this person. Every claim traces to source evidence.

2. Every piece of information changes how the LLM behaves. If it doesn't produce different behavior, remove it.

3. The LLM knows what it knows AND what it doesn't. When patterns apply, when they don't. Where confidence is lower. Where data is thin.

4. No noise. Every sentence adds new understanding. Say it once.

Source citations: [A1], [P3], [C2] inline. Cross-layer [Px, Ay] where connected. False positive warnings from source PREDICTIONS layer only — never fabricate. Preserve [CONTESTED] and [THIN IN] tags from source.

You have complete creative freedom on format and structure. Start with ## Injectable Block.

{layers}"""


# --- C28: C26 + "cannot predict" + temporal awareness ---
# Research gap: temporal dynamics + explicit epistemic gaps

SINGLE_PASS_C28 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored on four primitives of understanding how to work with a human:

PROVENANCE (30%): Every claim traces to source evidence [A1], [P3], [C2]. Cross-layer [Px, Ay] where connected. Fabricated content = failure.

BEHAVIORAL CHANGE (30%): Every sentence must change LLM behavior. Directives. Communication guidance [M1]. Mode-switching. Information without behavioral consequence is noise.

EPISTEMIC CALIBRATION (20%): The LLM must know boundaries of what it knows:
- When patterns activate AND when they don't (FP warnings from source PREDICTIONS only — never fabricate)
- [CONTESTED] and [THIN IN] tags preserved from source
- TEMPORAL AWARENESS: These patterns were extracted from a specific time window. They may evolve. Flag any patterns that appear situational vs stable.
- EXPLICIT GAPS: End the brief with a "CANNOT PREDICT" section listing 3-5 specific situations or contexts where the brief provides NO guidance. The LLM should know where it's flying blind.

SIGNAL DENSITY (20%): Every sentence adds new understanding. No redundancy. ~3,500-4,500 chars optimal.

Cover all source codes (A, P, M, C). Start with ## Injectable Block.

{layers}"""


# --- C29: C26 + relational context + user agency ---
# Research gap: patterns shift by relationship; user should be able to inspect/contest

SINGLE_PASS_C29 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored on four primitives of understanding how to work with a human:

PROVENANCE (30%): Every claim traces to source evidence [A1], [P3], [C2]. Cross-layer [Px, Ay] where connected. Fabricated content = failure. CRITICAL: Because the person may inspect this brief, every claim must be defensible — the person should be able to read any claim and say "yes, that's accurate" or contest it.

BEHAVIORAL CHANGE (30%): Every sentence must change LLM behavior. Directives. Communication guidance [M1]. Mode-switching. RELATIONAL CONTEXT: Where possible, note how patterns might shift based on the relationship dynamic — patterns may manifest differently when this person is in a position of authority vs seeking help, in professional vs personal contexts, or with trusted vs new interlocutors.

EPISTEMIC CALIBRATION (20%): The LLM must know boundaries of what it knows:
- When patterns activate AND when they don't (FP warnings from source PREDICTIONS only)
- [CONTESTED] and [THIN IN] tags preserved
- End with "CANNOT PREDICT" section: 3-5 contexts where the brief provides no guidance
- Note: this brief represents the person's self-reported patterns and observed behaviors, not objective truth. The person has the right to contest any claim.

SIGNAL DENSITY (20%): Every sentence adds new understanding. No redundancy. ~3,500-4,500 chars optimal.

Cover all source codes (A, P, M, C). Start with ## Injectable Block.

{layers}"""


# --- C30: Full research synthesis — all gaps integrated ---

SINGLE_PASS_C30 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

This brief must achieve four things, grounded in research on how AI systems should understand humans:

1. PROVENANCE — Every claim about this person traces to source evidence with inline citations [A1], [P3], [C2]. Cross-layer [Px, Ay] where connected. The LLM must be able to explain: "I believe X because of Y from your history." Because the person may inspect this brief, every claim must be one they'd recognize as accurate. Fabricated content = failure.

2. BEHAVIORAL CHANGE — Every sentence must change how the LLM interacts. Information without behavioral consequence is noise. Include:
   - Communication approach [M1] — how to talk to this person
   - Explicit directives for each behavioral pattern
   - Mode-switching guidance where applicable
   - RELATIONAL AWARENESS: Note where patterns may manifest differently based on relationship dynamics (authority vs peer, professional vs personal, trusted vs new)

3. EPISTEMIC CALIBRATION — The LLM must know the boundaries of what it knows:
   - When patterns activate AND when they don't (FP warnings from source PREDICTIONS layer only — never fabricate)
   - [CONTESTED] and [THIN IN] tags preserved from source
   - TEMPORAL NOTE: These patterns were extracted from a specific time window and may evolve
   - CANNOT PREDICT section (end of brief): List 3-5 specific situations where this brief provides NO guidance — contexts, relationship types, or scenarios where the LLM should not assume it understands this person
   - This brief represents extracted patterns, not objective truth. The person has the right to contest any claim.

4. SIGNAL DENSITY — Every sentence adds new understanding. No redundancy between sections. Say it once. ~3,500-4,500 chars optimal. Compression without signal loss.

Cover all source codes (A, P, M, C). Preserve [CONTESTED] and [THIN IN] tags. Start with ## Injectable Block.

{layers}"""


# --- C31: C28 + format freedom (C27 hybrid) ---
# Best content (C28: temporal + cannot predict + rubric) with no structural prescription (C27)

SINGLE_PASS_C31 = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored on four primitives of understanding how to work with a human:

PROVENANCE (30%): Every claim traces to source evidence [A1], [P3], [C2]. Cross-layer [Px, Ay] where connected. Fabricated content = failure.

BEHAVIORAL CHANGE (30%): Every sentence must change LLM behavior. Directives. Communication guidance [M1]. Mode-switching. Information without behavioral consequence is noise.

EPISTEMIC CALIBRATION (20%): The LLM must know boundaries of what it knows:
- When patterns activate AND when they don't (FP warnings from source PREDICTIONS only — never fabricate)
- [CONTESTED] and [THIN IN] tags preserved from source
- TEMPORAL AWARENESS: These patterns were extracted from a specific time window. They may evolve. Flag any patterns that appear situational vs stable.
- EXPLICIT GAPS: End the brief with a "CANNOT PREDICT" section listing 3-5 specific situations or contexts where the brief provides NO guidance. The LLM should know where it's flying blind.

SIGNAL DENSITY (20%): Every sentence adds new understanding. No redundancy. ~3,500-4,500 chars optimal.

You have complete creative freedom on format and structure. Choose whatever organization best captures this specific person. Cover all source codes (A, P, M, C). Start with ## Injectable Block.

{layers}"""


# ============================================================================
# CONDITION DEFINITIONS
# ============================================================================

# --- FAITHFULNESS-ONLY PROMPTS (C6) ---

EXECUTOR_FAITHFUL = """Restate the claim below using only the source text. Third person. Nothing else.

CLAIM: {claim}

SOURCE: {source_text}"""

ASSEMBLY_FAITHFUL = """Combine these paragraphs into one document. Do not add, remove, or rephrase anything.
Start with ## Injectable Block

{paragraphs}

AVAILABILITY INDEX:
{availability_items}"""


CONDITIONS = {
    "C0": {
        "name": "Production V4 (Opus single-pass)",
        "type": "existing",  # Just load existing brief_v4.md
    },
    "C1": {
        "name": "P-E full rules",
        "type": "pe",
        "planner_prompt": PLANNER_FULL,
        "executor_prompt": EXECUTOR_FULL,
        "assembly_prompt": ASSEMBLY_FULL,
        "executor_max_tokens": 1024,
        "assembly_max_tokens": 4096,
    },
    "C2": {
        "name": "P-E minimal prompts",
        "type": "pe",
        "planner_prompt": PLANNER_MINIMAL,
        "executor_prompt": EXECUTOR_MINIMAL,
        "assembly_prompt": ASSEMBLY_MINIMAL,
        "executor_max_tokens": 1024,
        "assembly_max_tokens": 4096,
    },
    "C3": {
        "name": "P-E token budget",
        "type": "pe",
        "planner_prompt": PLANNER_FULL,
        "executor_prompt": EXECUTOR_BUDGET,
        "assembly_prompt": ASSEMBLY_FULL,
        "executor_max_tokens": 150,  # Hard cap
        "assembly_max_tokens": 1200,  # Hard cap
    },
    "C4": {
        "name": "Opus single-pass capped",
        "type": "single",
        "prompt": SINGLE_PASS_CAPPED,
        "max_tokens": 1200,  # Hard cap — force compression
    },
    "C5": {
        "name": "P-E no assembly",
        "type": "pe_no_assembly",
        "planner_prompt": PLANNER_FULL,
        "executor_prompt": EXECUTOR_FULL,
        "executor_max_tokens": 1024,
    },
    "C6": {
        "name": "P-E faithfulness-only",
        "type": "pe",
        "planner_prompt": PLANNER_FULL,  # Planner is already faithfulness-focused
        "executor_prompt": EXECUTOR_FAITHFUL,
        "assembly_prompt": ASSEMBLY_FAITHFUL,
        "executor_max_tokens": 512,
        "assembly_max_tokens": 4096,
    },
    "C7": {
        "name": "P-E faithful + token budget",
        "type": "pe",
        "planner_prompt": PLANNER_MINIMAL,
        "executor_prompt": EXECUTOR_BUDGET,
        "assembly_prompt": ASSEMBLY_FAITHFUL,
        "executor_max_tokens": 150,
        "assembly_max_tokens": 1200,
    },
    "C8": {
        "name": "Opus capped + trace + FP + directives",
        "type": "single",
        "prompt": SINGLE_PASS_C8,
        "max_tokens": 1500,
    },
    "C9": {
        "name": "False-positive-first structure",
        "type": "single",
        "prompt": SINGLE_PASS_C9,
        "max_tokens": 1500,
    },
    "C10": {
        "name": "Bare minimum purpose + layers",
        "type": "single",
        "prompt": SINGLE_PASS_C10,
        "max_tokens": 1500,
    },
    "C11": {
        "name": "Optimization target, free format",
        "type": "single",
        "prompt": SINGLE_PASS_C11,
        "max_tokens": 1500,
    },
    "C12": {
        "name": "Collective-prescribed synthesis",
        "type": "single",
        "prompt": SINGLE_PASS_C12,
        "max_tokens": 1500,
    },
    "C13": {
        "name": "C9 without false positive warnings",
        "type": "single",
        "prompt": SINGLE_PASS_C13,
        "max_tokens": 1500,
    },
    "C14": {
        "name": "Hybrid C9+C13 + FP faithfulness fix",
        "type": "single",
        "prompt": SINGLE_PASS_C14,
        "max_tokens": 1500,
    },
    "C15": {
        "name": "C14 + M1 communication mandate",
        "type": "single",
        "prompt": SINGLE_PASS_C15,
        "max_tokens": 1500,
    },
    "C16": {
        "name": "C15 + completeness checklist + tensions",
        "type": "single",
        "prompt": SINGLE_PASS_C16,
        "max_tokens": 2000,
    },
    "C17": {
        "name": "C15 + radical compression",
        "type": "single",
        "prompt": SINGLE_PASS_C17,
        "max_tokens": 800,
    },
    "C18": {
        "name": "C15 no opening paragraph",
        "type": "single",
        "prompt": SINGLE_PASS_C18,
        "max_tokens": 1500,
    },
    "C19": {
        "name": "Rubric as optimization target",
        "type": "single",
        "prompt": SINGLE_PASS_C19,
        "max_tokens": 1500,
    },
    "C20": {
        "name": "Prescribed hybrid (all codes + compressed)",
        "type": "single",
        "prompt": SINGLE_PASS_C20,
        "max_tokens": 1500,
    },
    "C21": {
        "name": "C20 + example phrasings",
        "type": "single",
        "prompt": SINGLE_PASS_C21,
        "max_tokens": 1500,
    },
    "C22": {
        "name": "C20 radical compression (~3K)",
        "type": "single",
        "prompt": SINGLE_PASS_C22,
        "max_tokens": 1200,
    },
    "C23": {
        "name": "C20 + rubric awareness",
        "type": "single",
        "prompt": SINGLE_PASS_C23,
        "max_tokens": 1500,
    },
    "C24": {
        "name": "Epistemic loop (primitives-first)",
        "type": "single",
        "prompt": SINGLE_PASS_C24,
        "max_tokens": 1500,
    },
    "C25": {
        "name": "C24 compressed (force density)",
        "type": "single",
        "prompt": SINGLE_PASS_C25,
        "max_tokens": 1000,
    },
    "C26": {
        "name": "C24 + rubric awareness (new rubric)",
        "type": "single",
        "prompt": SINGLE_PASS_C26,
        "max_tokens": 1500,
    },
    "C27": {
        "name": "Pure primitives (no structural prescription)",
        "type": "single",
        "prompt": SINGLE_PASS_C27,
        "max_tokens": 1500,
    },
    "C28": {
        "name": "C26 + cannot predict + temporal",
        "type": "single",
        "prompt": SINGLE_PASS_C28,
        "max_tokens": 1500,
    },
    "C29": {
        "name": "C26 + relational context + agency",
        "type": "single",
        "prompt": SINGLE_PASS_C29,
        "max_tokens": 1500,
    },
    "C30": {
        "name": "Full research synthesis",
        "type": "single",
        "prompt": SINGLE_PASS_C30,
        "max_tokens": 1500,
    },
    "C31": {
        "name": "C28 + format freedom",
        "type": "single",
        "prompt": SINGLE_PASS_C31,
        "max_tokens": 1500,
    },
}


# ============================================================================
# HELPERS
# ============================================================================

def load_layer(subject_dir, filename):
    path = os.path.join(subject_dir, "data", "identity_layers", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def format_layers(anchors, core, predictions):
    parts = []
    if anchors:
        parts.append(f"=== ANCHORS ===\n{anchors}")
    if core:
        parts.append(f"=== CORE ===\n{core}")
    if predictions:
        parts.append(f"=== PREDICTIONS ===\n{predictions}")
    return "\n\n".join(parts)


def calc_cost(response, model):
    if model == OPUS:
        return (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000
    else:
        return (response.usage.input_tokens * 3 + response.usage.output_tokens * 15) / 1_000_000


def parse_plan(text):
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean[:-3]
    parsed = json.loads(clean)
    if isinstance(parsed, list):
        return parsed, []
    return parsed.get("paragraphs", []), parsed.get("availability_index", [])


# ============================================================================
# RUNNERS
# ============================================================================

def run_existing(subject_dir):
    """C0: Load existing production brief."""
    path = os.path.join(subject_dir, "data", "identity_layers", "brief_v4.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), 0.0
    return "(no production brief found)", 0.0


def run_single_pass(client, layers_text, config):
    """C4: Single Opus call with token cap."""
    prompt = config["prompt"].format(layers=layers_text)
    response = client.messages.create(
        model=OPUS,
        max_tokens=config["max_tokens"],
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    cost = calc_cost(response, OPUS)
    return text, cost


def run_pe(client, layers_text, anchors, core, predictions, config, skip_assembly=False):
    """Run full P-E pipeline with given prompts."""
    total_cost = 0.0

    # Phase 1: Plan
    prompt = config["planner_prompt"].format(layers=layers_text)
    response = client.messages.create(
        model=OPUS,
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    plan_cost = calc_cost(response, OPUS)
    total_cost += plan_cost
    plan, availability_index = parse_plan(response.content[0].text)
    print(f"    Planner: {len(plan)} claims, ${plan_cost:.3f}")

    # Phase 2: Execute
    paragraphs = []
    for i, item in enumerate(plan):
        exec_prompt = config["executor_prompt"].format(
            claim=item.get("claim", ""),
            source_text=item.get("source_text", ""),
        )
        response = client.messages.create(
            model=SONNET,
            max_tokens=config.get("executor_max_tokens", 1024),
            temperature=0,
            messages=[{"role": "user", "content": exec_prompt}],
        )
        cost = calc_cost(response, SONNET)
        total_cost += cost
        text = response.content[0].text.strip()
        paragraphs.append({
            "paragraph_id": item.get("paragraph_id", i + 1),
            "theme": item.get("theme", f"theme_{i+1}"),
            "sources": item.get("sources", []),
            "text": text,
        })
        print(f"    Executor [{i+1}/{len(plan)}]: {len(text)} chars")

    if skip_assembly:
        # Raw concatenation
        brief = "## Injectable Block\n\n"
        brief += "\n\n".join(p["text"] for p in paragraphs)
        if availability_index:
            brief += "\n\n**Availability Index:**\n"
            brief += "\n".join(
                f"- {item['pattern']} — {item['trigger']} [Source: {item.get('source', 'N/A')}]"
                for item in availability_index
            )
        return brief, total_cost

    # Phase 3: Assembly
    para_block = ""
    for p in paragraphs:
        para_block += f"\n--- {p['theme']} ---\n{p['text']}\n"

    avail_text = ""
    if availability_index:
        avail_text = "\n".join(
            f"- {item['pattern']} — {item['trigger']} [Source: {item.get('source', 'N/A')}]"
            for item in availability_index
        )

    asm_prompt = config["assembly_prompt"].format(
        paragraphs=para_block,
        availability_items=avail_text or "(none)",
    )
    response = client.messages.create(
        model=SONNET,
        max_tokens=config.get("assembly_max_tokens", 4096),
        temperature=0,
        messages=[{"role": "user", "content": asm_prompt}],
    )
    asm_cost = calc_cost(response, SONNET)
    total_cost += asm_cost
    brief = response.content[0].text.strip()
    print(f"    Assembly: {len(brief)} chars, ${asm_cost:.3f}")

    return brief, total_cost


# ============================================================================
# MAIN
# ============================================================================

def run_condition(client, cond_id, config, subject_dir, anchors, core, predictions, layers_text):
    """Run one condition, return (brief_text, cost)."""
    ctype = config["type"]

    if ctype == "existing":
        return run_existing(subject_dir)
    elif ctype == "single":
        return run_single_pass(client, layers_text, config)
    elif ctype == "pe":
        return run_pe(client, layers_text, anchors, core, predictions, config)
    elif ctype == "pe_no_assembly":
        return run_pe(client, layers_text, anchors, core, predictions, config, skip_assembly=True)
    else:
        return f"(unknown condition type: {ctype})", 0.0


def main():
    parser = argparse.ArgumentParser(description="P-E Prompt Ablation")
    parser.add_argument("subject_dir", nargs="?", help="Subject directory (or use --all)")
    parser.add_argument("--all", action="store_true", help="Run all 3 subjects")
    parser.add_argument("--conditions", default="C0,C1,C2,C3,C4,C5,C6,C7",
                        help="Comma-separated condition IDs (default: all)")
    args = parser.parse_args()

    cond_ids = [c.strip() for c in args.conditions.split(",")]

    if args.all:
        subjects = ALL_SUBJECTS
    elif args.subject_dir:
        subjects = [args.subject_dir]
    else:
        print("ERROR: Provide a subject_dir or use --all")
        sys.exit(1)

    client = get_anthropic_client()
    results = []

    for subject_dir in subjects:
        subject_name = os.path.basename(subject_dir).replace("_memory", "").replace("_meta_v2", "").replace("memory_system_v4", "aarik")

        anchors = load_layer(subject_dir, "anchors_v4.md")
        core = load_layer(subject_dir, "core_v4.md")
        predictions = load_layer(subject_dir, "predictions_v4.md")

        if not anchors and not core and not predictions:
            print(f"\n  SKIP {subject_name}: no layers found")
            continue

        layers_text = format_layers(anchors, core, predictions)

        print(f"\n{'=' * 60}")
        print(f"  SUBJECT: {subject_name}")
        print(f"  Layers: A={len(anchors):,} C={len(core):,} P={len(predictions):,}")
        print(f"{'=' * 60}")

        for cond_id in cond_ids:
            if cond_id not in CONDITIONS:
                print(f"  SKIP unknown condition: {cond_id}")
                continue

            config = CONDITIONS[cond_id]
            print(f"\n  --- {cond_id}: {config['name']} ---")

            try:
                start = time.time()
                brief, cost = run_condition(
                    client, cond_id, config, subject_dir,
                    anchors, core, predictions, layers_text
                )
                elapsed = time.time() - start

                # Save brief
                out_dir = os.path.join(subject_dir, "data", "identity_layers")
                out_path = os.path.join(out_dir, f"brief_ablation_{cond_id}.md")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(f"---\ncondition: {cond_id}\nname: {config['name']}\ngenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n---\n\n")
                    f.write(brief)

                char_count = len(brief)
                print(f"  Result: {char_count:,} chars, ${cost:.3f}, {elapsed:.1f}s")
                print(f"  Saved: {out_path}")

                results.append({
                    "subject": subject_name,
                    "condition": cond_id,
                    "condition_name": config["name"],
                    "chars": char_count,
                    "cost": cost,
                    "time": round(elapsed, 1),
                    "path": out_path,
                })

            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({
                    "subject": subject_name,
                    "condition": cond_id,
                    "error": str(e),
                })

    # Summary table
    print(f"\n\n{'=' * 80}")
    print(f"  ABLATION RESULTS SUMMARY")
    print(f"{'=' * 80}")
    print(f"  {'Subject':<12} {'Condition':<6} {'Name':<30} {'Chars':>8} {'Cost':>8} {'Time':>6}")
    print(f"  {'-'*12} {'-'*6} {'-'*30} {'-'*8} {'-'*8} {'-'*6}")
    for r in results:
        if "error" in r:
            print(f"  {r['subject']:<12} {r['condition']:<6} ERROR: {r['error']}")
        else:
            print(f"  {r['subject']:<12} {r['condition']:<6} {r['condition_name']:<30} {r['chars']:>8,} ${r['cost']:>7.3f} {r['time']:>5.1f}s")

    # Save results JSON
    results_path = os.path.join(os.path.dirname(__file__), "pe_ablation_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {results_path}")
    print(f"\n  Next: Run Collective review on each brief pair for comparative scoring.")


if __name__ == "__main__":
    main()
