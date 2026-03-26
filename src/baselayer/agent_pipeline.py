"""
Unified Brief Composition

Composes a single narrative brief from the 3 deployed identity layers
(ANCHORS, CORE, PREDICTIONS) + source identity-tier facts.

Franklin eval (S61) proved compressed brief (C5c) outperforms structured
layers (C2) by +0.40. The pipeline extracts value; compression makes it
usable.

Usage:
  from agent_pipeline import compose_unified_brief
  brief = compose_unified_brief()
"""

import contextlib
import os
import re
import sys
from datetime import datetime

from baselayer.config import (
    IDENTITY_LAYERS_DIR,
    ANCHORS_LAYER_FILE,
    CORE_LAYER_FILE,
    PREDICTIONS_LAYER_FILE,
    UNIFIED_BRIEF_FILE, UNIFIED_BRIEF_CITED_FILE,
    IDENTITY_MODEL_FILE,
    V1_STAGING_DIR,
    get_db,
)


# ===========================================================================
# REQUIRED TERMS EXTRACTION + VERIFICATION
# ===========================================================================


def extract_required_terms(layer_texts):
    """Extract required terms from source layers for completeness verification.

    Parses axiom names from ANCHORS, context mode keywords from CORE,
    prediction names from PREDICTIONS, and markers like [CONTESTED]/[THIN DATA].

    Returns:
        dict with categories mapping to lists of (term, description) tuples
    """
    required = {}

    # --- ANCHORS: axiom mechanisms ---
    # Extract axiom names and derive behavioral keywords dynamically from
    # the axiom text. The brief can represent axioms through behavioral
    # descriptions (2nd-order) or explicit naming (1st-order) — both count.
    anchors = layer_texts.get("anchors", "")
    axiom_mechanisms = []

    def _extract_axiom_keywords(axiom_name, axiom_text):
        """Derive behavioral keywords from axiom name + surrounding text.

        Returns list of lowercase keywords. The brief is considered to cover
        this axiom if the axiom name OR 2+ keywords appear in proximity.
        """
        keywords = []
        # Always include hyphenated and unhyphenated forms of the name
        keywords.append(axiom_name.lower())
        keywords.append(axiom_name.lower().replace("-", " "))
        # Split compound name into component words (e.g., CHARACTER-PRIMACY → character, primacy)
        for part in axiom_name.lower().split("-"):
            if len(part) > 3:  # skip short fragments
                keywords.append(part)
        # Extract significant words from the axiom description text
        # Skip common stop words and short words
        stop_words = {"the", "and", "that", "this", "with", "from", "when", "they",
                      "their", "them", "will", "must", "should", "would", "could",
                      "than", "into", "been", "have", "what", "where", "which",
                      "each", "every", "both", "more", "also", "only", "does",
                      "your", "not", "any", "all", "for", "but", "are", "was",
                      "who", "how", "has", "his", "her", "its", "can", "may"}
        if axiom_text:
            words = re.findall(r'[a-z]{4,}', axiom_text.lower())
            # Take the most distinctive words (not stop words, appear in the text)
            for w in words:
                if w not in stop_words and w not in keywords:
                    keywords.append(w)
                if len(keywords) >= 8:
                    break
        return keywords

    # Parse axiom blocks: **A1. NAME** followed by description text
    axiom_blocks = re.split(r'\n\*\*[A-Z]\d+\.', anchors)
    # Also handle the first axiom which may start at beginning
    axiom_header_pattern = re.compile(r'\*\*(?:[A-Z]\d+\.\s*)?([A-Z][A-Z\-]+(?:\s*\[CONTESTED\])?)\*\*')
    current_axiom = None
    current_text = []
    for line in anchors.split("\n"):
        stripped = line.strip()
        header_match = axiom_header_pattern.search(stripped)
        if header_match:
            # Save previous axiom
            if current_axiom:
                text_block = " ".join(current_text)
                keywords = _extract_axiom_keywords(current_axiom, text_block)
                axiom_mechanisms.append((current_axiom, keywords,
                    f"Axiom '{current_axiom}' mechanism must be represented in brief"))
            # Start new axiom
            raw_name = header_match.group(1).replace("[CONTESTED]", "").strip()
            # Valid axiom: all uppercase, no "+" (interaction pairs), no ":" (section headers)
            if (raw_name.isupper() and len(raw_name) > 2
                    and "+" not in raw_name and ":" not in raw_name
                    and not raw_name.startswith("GENERAL")):
                current_axiom = raw_name
                current_text = []
            else:
                current_axiom = None
                current_text = []
        elif current_axiom and stripped and not stripped.startswith("provenance:"):
            current_text.append(stripped)
    # Don't forget the last axiom
    if current_axiom:
        text_block = " ".join(current_text)
        keywords = _extract_axiom_keywords(current_axiom, text_block)
        axiom_mechanisms.append((current_axiom, keywords,
            f"Axiom '{current_axiom}' mechanism must be represented in brief"))

    if axiom_mechanisms:
        required["axiom_mechanisms"] = axiom_mechanisms

    # --- ANCHORS: markers ---
    markers = []
    if "[CONTESTED]" in anchors:
        markers.append(("CONTESTED", "[CONTESTED] marker must appear for contested axioms"))
    if "[THIN DATA]" in anchors or "THIN DATA" in anchors:
        markers.append(("THIN DATA", "[THIN DATA] warning must be preserved"))
    if markers:
        required["markers"] = markers

    # --- ANCHORS: interaction patterns ---
    interactions = []
    if "Avoidance Circuit" in anchors:
        interactions.append(("Avoidance Circuit", "The Avoidance Circuit meta-pattern"))
    if "Fragile Axiom" in anchors:
        interactions.append(("Fragile Axiom", "The Fragile Axiom meta-pattern"))
    if "Core Triangle" in anchors:
        interactions.append(("Core Triangle", "The Core Triangle meta-pattern"))
    if interactions:
        required["meta_patterns"] = interactions

    # --- CORE: context mode keywords (dynamically extracted) ---
    core = layer_texts.get("core", "")
    context_keywords = []
    # Extract section headers from CORE (e.g. "**Trading Context:**", "**C1. PUBLIC ADMIN...**")
    # and require that the brief mentions each context mode by its key topic.
    core_sections = re.findall(r'\*\*(?:[A-Z]\d+\.\s+)?(.+?)\*\*', core)
    for raw_name in core_sections:
        section_name = raw_name.strip().rstrip(':')
        # Remove trailing " Context" suffix
        if section_name.endswith(" Context"):
            section_name = section_name[:-len(" Context")]
        # Skip generic section headers
        if section_name.upper() in ("COMMUNICATION APPROACH", "NARRATIVE ORIENTATION",
                                     "ESSENTIAL CONTEXT", "CONTEXT MODES",
                                     "INJECTABLE BLOCK"):
            continue
        if len(section_name) < 3:
            continue
        context_keywords.append((section_name.lower(), f"CORE context mode: '{section_name}'"))
    if context_keywords:
        required["core_keywords"] = context_keywords

    # --- CORE: narrative orientation ---
    narrative = []
    if "conclusion-first" in core.lower() or "conclusions, then" in core.lower():
        narrative.append(("conclusion-first", "Narrative orientation: conclusion-first storytelling"))
    if "future-projecting" in core.lower() or "future" in core.lower():
        narrative.append(("future-projecting", "Narrative orientation: future-projecting temporal orientation"))
    if narrative:
        required["narrative_orientation"] = narrative

    # --- PREDICTIONS: pattern names ---
    predictions = layer_texts.get("predictions", "")
    pred_names = []
    for line in predictions.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and ". " in stripped:
            # e.g. "## 1. ANALYSIS-PARALYSIS SPIRAL"
            parts = stripped.split(". ", 1)
            if len(parts) == 2:
                name = parts[1].strip()
                pred_names.append((name, f"Prediction '{name}' must be present"))
    if pred_names:
        required["prediction_names"] = pred_names

    # --- PREDICTIONS: directives (check for "Directive:" sections) ---
    directive_count = predictions.lower().count("**directive:**")
    if directive_count > 0:
        required["prediction_directives"] = [
            ("directive", f"At least {directive_count} prediction directives (When X, do Y instructions)")
        ]

    # --- PREDICTIONS: false positives ---
    fp_count = predictions.lower().count("**false positive:**")
    if fp_count > 0:
        required["prediction_false_positives"] = [
            ("false positive", f"At least {fp_count} false positive warnings")
        ]

    # --- PREDICTIONS: parked patterns ---
    if "parked" in predictions.lower() or "single-domain" in predictions.lower():
        required["parked_patterns"] = [
            ("parked", "Parked/single-domain patterns must be noted")
        ]

    return required


def verify_brief_completeness(brief_text, required_terms):
    """Verify the composed brief contains all required terms from source layers.

    Args:
        brief_text: The composed brief
        required_terms: Dict from extract_required_terms()

    Returns:
        List of gap descriptions (empty = passed)
    """
    gaps = []
    brief_lower = brief_text.lower()
    brief_upper = brief_text  # for case-sensitive checks

    for category, terms in required_terms.items():
        if category == "prediction_directives":
            # Check for directive-like language (When X, do Y patterns)
            directive_patterns = [
                "when this pattern", "when he ", "when she ",
                "directive:", "redirect to", "name the pattern",
                "force the fork", "surface the cost", "ask:",
                "point to the evidence", "anchor to",
            ]
            found = sum(1 for p in directive_patterns if p in brief_lower)
            min_needed = int(terms[0][1].split()[2])  # extract the count
            if found < min_needed // 2:  # at least half should be present
                gaps.append(f"Prediction directives: found ~{found} directive-like phrases, need at least {min_needed // 2} (source has {min_needed})")
            continue

        if category == "prediction_false_positives":
            fp_patterns = ["false positive", "the tell:", "not the same as",
                          "does not mean", "is not", "distinguish"]
            found = sum(1 for p in fp_patterns if p in brief_lower)
            min_needed = int(terms[0][1].split()[2])
            if found < min_needed // 2:
                gaps.append(f"False positive warnings: found ~{found} FP-like phrases, need at least {min_needed // 2} (source has {min_needed})")
            continue

        if category == "axiom_mechanisms":
            # Behavioral coverage check: axiom is covered if its ALL-CAPS name
            # appears OR 2+ behavioral keywords from its description appear.
            for axiom_name, keywords, description in terms:
                # 1st-order check: explicit axiom name
                if axiom_name in brief_text or axiom_name.lower().replace("-", " ") in brief_lower:
                    continue  # Covered at 1st order
                # 2nd-order check: count keyword hits across all keywords.
                # Require at least 1 hit for lists of ≤2 keywords; 2+ hits for longer lists.
                # This prevents short keyword lists (edge case) from requiring 2 matches
                # when there are only 2 keywords total and one is not in the brief.
                keyword_hits = sum(1 for kw in keywords if kw in brief_lower)
                hit_threshold = 1 if len(keywords) <= 2 else 2
                if keyword_hits >= hit_threshold:
                    continue  # Covered at 2nd order (behavioral description)
                gaps.append(f"MISSING: {description} (0 of {len(keywords)} keywords found)")
            continue

        for term, description in terms:
            # Case-sensitive check for uppercase pattern names
            if term.isupper():
                if term not in brief_upper:
                    gaps.append(f"MISSING: {description}")
            else:
                if term.lower() not in brief_lower:
                    gaps.append(f"MISSING: {description}")

    return gaps


def verify_brief_faithfulness(brief_text, layer_texts, facts_text="", subject_name=""):
    """Verify the composed brief does NOT contain hallucinated content.

    Advisory-only gate (S68): reports potential issues but does NOT auto-remove content.

    Checks that ALL-CAPS pattern names and specific technical terms in the
    brief are traceable to the source layers or facts. Flags any content
    that appears fabricated.

    Args:
        brief_text: The composed brief
        layer_texts: Dict with keys "anchors", "core", "predictions" -> text
        facts_text: The supporting facts text fed to the composition model
        subject_name: Optional subject name to whitelist (e.g. "Frederick Douglass")

    Returns:
        List of hallucination warnings (empty = clean)
    """
    warnings = []

    # Combine all source material into one searchable text
    source_combined = "\n".join([
        layer_texts.get("anchors", ""),
        layer_texts.get("core", ""),
        layer_texts.get("predictions", ""),
        facts_text,
    ]).lower()

    # Build whitelist of names to skip (subject name + common metadata)
    name_whitelist = {
        "Thin Data", "Core Triangle", "Fragile Axiom", "Avoidance Circuit",
        "Active when", "Injectable Block", "False Positive",
    }
    # Add subject name and its parts to whitelist
    if subject_name:
        name_whitelist.add(subject_name)
        for part in subject_name.split():
            if len(part) > 2:
                name_whitelist.add(part)
    # Auto-detect subject name from layers (first capitalized multi-word name that appears 3+ times)
    if not subject_name:
        all_layer_text = " ".join(layer_texts.get(k, "") for k in ("anchors", "core", "predictions"))
        candidate_names = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', all_layer_text)
        from collections import Counter
        name_counts = Counter(candidate_names)
        for n, count in name_counts.most_common(3):
            if count >= 3 and n not in name_whitelist:
                name_whitelist.add(n)
                for part in n.split():
                    if len(part) > 2:
                        name_whitelist.add(part)

    # 1. Extract ALL-CAPS pattern names from brief (2+ chars, may contain hyphens)
    brief_patterns = set(re.findall(r'\b([A-Z][A-Z\-]{2,}(?:\s+[A-Z\-]{2,})*)\b', brief_text))
    # Filter out common English words, format labels, and metadata markers
    skip_words = {
        "IMPORTANT", "NEVER", "NOT", "ALL", "THE", "AND", "FOR", "BUT",
        "WHEN", "THIS", "THIN", "DATA", "CONTESTED", "CRITICAL", "WARNING",
        "INJECTABLE", "BLOCK", "ANCHORS", "CORE", "PREDICTIONS", "LAYER",
        "ANTI", "NOTE", "FORMAT", "PROVENANCE", "DETECTION", "DIRECTIVE",
        "THIN DATA", "DATA LIMITATION", "NO PREDICTIONS",
    }
    for pattern in brief_patterns:
        if pattern in skip_words:
            continue
        if pattern.lower() not in source_combined:
            warnings.append(f"HALLUCINATED PATTERN: '{pattern}' appears in brief but NOT in any source layer or fact")

    # 2. Check for specific technical terms that could indicate cross-subject contamination
    specific_terms = re.findall(r'\b([A-Z]\d+[A-Z]?\d*)\b', brief_text)  # e.g. E46, M3, S55
    for term in specific_terms:
        if term.lower() not in source_combined:
            # Skip lexicon IDs like A1, P1, C1, M1 which are format labels
            if re.match(r'^[APCM]\d+$', term):
                continue
            warnings.append(f"HALLUCINATED TERM: '{term}' appears in brief but NOT in any source layer or fact")

    # 3. Check for proper nouns / specific names not in source
    potential_names = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', brief_text)
    for name in potential_names:
        if name in name_whitelist:
            continue
        if any(wl in name or name in wl for wl in name_whitelist):
            continue
        if name.lower() not in source_combined:
            warnings.append(f"UNGROUNDED NAME: '{name}' appears in brief but NOT in any source — verify it's not fabricated")

    return warnings


UNIFIED_BRIEF_COMPOSITION_PROMPT = """You are composing a unified behavioral brief from identity layers about a specific person. This brief will be injected into AI system prompts so the AI can communicate naturally with — or as — this person.

The source layers are:
1. ANCHORS — epistemic axioms (what they reason FROM)
2. CORE — communication & operating guide (how to engage)
3. PREDICTIONS — behavioral patterns (situation → response)

Not all layers may be present. Some subjects have thin data — compose only from what exists.

Your task: combine the provided layers into a SINGLE narrative brief that faithfully represents ALL content from the source layers. The brief must be COMPLETE — nothing from the source layers should be left out. Size does not matter. A complete 15,000-token brief is better than a 5,000-token brief that drops content.

CRITICAL ANTI-HALLUCINATION CONSTRAINT:
You must ONLY include information that appears in the source layers or supporting facts below. Do NOT invent, fabricate, or fill in:
- Hobbies, interests, or possessions not mentioned in the sources
- Biographical details not stated in the sources
- Behavioral patterns not described in the sources
- Historical context not grounded in the sources
If a category (e.g., hobbies, creative interests) has NO content in the sources, OMIT IT ENTIRELY. Completeness means including everything FROM the sources, not filling gaps with fabricated content. When in doubt, leave it out.

THREE PROPERTIES that make a good brief (from controlled evaluation):

1. CONCRETE AUTOBIOGRAPHICAL MECHANISMS — Not "values honesty" but "will terminate a conversation that uses strategic ambiguity." Not "is analytical" but "will reframe an emotional question as a structural question, then solve the structure." Specific tactics, not abstractions.

2. CHARACTERISTIC INNER TENSIONS — The contradictions that define this person, stated in THEIR domain vocabulary. Tensions are MORE useful than clean descriptions because they let the AI anticipate failure modes. Each tension must be specific enough that a reader could identify the subject from the tension alone.

3. PRAGMATIC FRAMING — Write for an AI that needs to ACT on this information. Every sentence should change what the AI would say. If a sentence produces the same generic response with or without it, cut it.

ANTI-ANACHRONISM: Use vocabulary appropriate to the subject's era and lived experience. Do not project modern professional jargon onto historical figures or non-professional subjects. If the source material uses plain language, the brief must too.

NO SELF-REFERENCE: The brief describes WHO this person is — their identity, patterns, and how to engage with them. It must NOT reference the pipeline, system, or tools that created the brief.

ANONYMIZATION: Do NOT use the subject's full name in the brief. Use pronouns ("he", "she", "they") or generic references ("this person"). The brief describes behavioral patterns — including the name risks the reading AI pattern-matching to its pre-training knowledge about this person rather than using the behavioral model provided. The brief should work because of what it says, not who it's about.

COMPLETENESS REQUIREMENTS — include these elements IF AND ONLY IF they exist in the source layers:

From ANCHORS (if present):
- Every axiom's behavioral MECHANISM must be represented — but weave them into thematic narrative paragraphs, do NOT list them sequentially (e.g., "A1 does X; A2 does Y; A3 does Z" is FORBIDDEN). Group axioms by how they interact and manifest together in real situations. Some axioms may be mentioned by name where natural; others can be represented through their mechanism without explicit naming.
- Every [CONTESTED] marker preserved as-is
- Every false positive warning included
- Axiom interaction pairs (reinforcing AND tension) if described
- Meta-patterns if described (only those explicitly named in the source)
- [THIN DATA] warnings preserved as-is

From CORE (if present):
- Communication approach directives
- Context modes that appear in the source (only those listed — do not add unlisted domains)
- Narrative orientation if described
- Essential biographical context from the source
- Specific "do not" directives if listed in the source

From PREDICTIONS (if present):
- All behavioral predictions with their triggers as described in the source
- Detection signatures if provided
- False positive warnings if provided
- Pathological modes if provided
- Directives (what the AI should DO) if provided
- Parked/single-domain patterns noted as such if present
- Pattern interaction map if described

If no PREDICTIONS layer exists: Note at the end of the brief that behavioral prediction data is insufficient for this subject. The source material may not contain enough behavioral evidence to generate predictions — this is a data limitation, not a gap in the brief.

FALSE POSITIVE GUARD PRESERVATION (REQUIRED):
For behavioral predictions that include false positive warnings in the PREDICTIONS layer,
preserve them as inline qualifiers in the brief narrative. Format: describe the pattern,
then add a natural-language qualifier describing the false positive scenario and what
distinguishes it from the real pattern. These guards prevent the reading AI from over-applying patterns.
Use the subject's own domain language for each guard — do NOT use a formulaic "but not when X, which looks similar but stems from Y" template.
Do NOT strip false positive warnings during composition. Each guard should appear as a
natural parenthetical or dash-separated qualifier within the behavioral description.
If the PREDICTIONS layer has N false positive warnings, the composed brief should have
at least N-2 of them represented (some may merge naturally).

FORMAT:
- Write in flowing prose paragraphs, not bullet points or structured headers
- Use third person (match the pronouns used in the source layers)
- Open with a 2-3 sentence identity anchor (who this person IS, irreducibly). BANNED OPENING PHRASES (will trigger automatic rejection): "operates from", "unshakeable conviction", "unshakeable belief", "fundamental belief that", "deeply held", "at his/her core". Instead, open with a concrete behavioral observation — what does this person DO that reveals who they are? The opening should be as distinctive as a fingerprint
- Follow with behavioral mechanisms grouped by natural theme, not by source layer
- Close with the key tensions, but make each one ACTIONABLE: state the contradiction AND what the reading AI should do when it surfaces. Weave these into 1-2 flowing prose paragraphs (NOT a bulleted list, NOT a separate labeled section). Each tension-action pair should read as natural prose, not as a formatted directive. CRITICAL: Every tension and directive MUST use vocabulary, domain language, and specific details drawn from the source layers — never generic advisory language. A reader familiar with this person should be able to identify them from ANY single directive. Do NOT use stock phrases like "help diagnose the structural cause" or "demands systematic tracking but struggles with order" — derive each tension's language from the actual behavioral evidence in the layers below. If the source layers describe a specific domain tension (e.g., moral perfectionism vs. pragmatic compromise in governance), the directive must use THOSE terms, not therapeutic abstractions
- End with an AVAILABILITY INDEX (see below)
- Do NOT reproduce the layer structure — this is a synthesis, not a concatenation
- Directives can be woven into narrative paragraphs — they do not need separate formatting
- ANTI-ENUMERATION: Never list axioms, predictions, or context modes sequentially in a single paragraph. A paragraph that reads "A1 does X; A2 does Y; A3 does Z..." is a schema dump, not a behavioral narrative. Instead, group related mechanisms thematically — show how axioms interact and manifest together in real situations from this person's life.

AVAILABILITY INDEX (required, place at end of brief after [THIN DATA]):
The brief is a compression. Some identity-significant patterns from the source layers were represented as behavioral texture (woven into descriptions of other patterns) rather than foregrounded as themes. The availability index signals what else exists in the deeper behavioral model, so the reading AI knows when to retrieve more detail.

Format — a single paragraph starting with "Additional behavioral patterns available:" followed by a comma-separated list. Each item is: "[pattern name or concept] — [when it surfaces / how it manifests]". Only include patterns that:
1. Appear in the source layers (axioms, context modes, or predictions) but were NOT foregrounded as a primary theme in the brief
2. Are genuinely identity-significant (they survived the full extraction pipeline)
3. Have a clear manifestation trigger (when would this pattern become relevant in conversation?)

Do NOT include patterns that are already well-developed in the brief. Do NOT pad the list. 3-8 items is typical.

Each item should use the subject's own terminology for both the pattern name and the trigger context. Do NOT use generic pattern names — derive them from the source layers.

USAGE INSTRUCTIONS (note to composing model: these instructions will be prepended separately when served — do NOT include them in the brief output):
- The brief will contain ALL-CAPS pattern names as internal reference labels. These are for the AI's understanding — the reading AI should never quote or name them in responses.
- These usage instructions are handled separately. Just compose the brief.

ANTI-REDUNDANCY:
- State each idea ONCE. If public benefit is the core axiom, establish it in one paragraph and refer back — do not restate it in every context mode.
- Do NOT reproduce provenance lines (provenance: [F-xxx, ...]) from the source layers. Those are metadata, not brief content.
- Do NOT reproduce layer taxonomy labels (PERSONAL/MORAL CONTEXT, BUSINESS/PROFESSIONAL CONTEXT, etc.) as inline headers. The brief is a narrative, not a structured data format.
- Do NOT use pipeline jargon ("future-projecting temporal orientation", "context modes", "epistemic axioms"). Describe the person in plain language.
- Target: each behavioral insight appears exactly once, in the paragraph where it has the most thematic resonance.

ANTI-CATALOGING (HARD RULE — most common failure mode):
- NEVER organize paragraphs by domain. Do NOT write "His approach to governance...", then "In matters of reform...", then "His military thinking..." — that mirrors the CORE layer's structure and produces a reference manual, not a portrait.
- NEVER use the word "mechanism" to describe axioms (e.g., "his CORPORATE-ACCOUNTABILITY mechanism demands..."). This is pipeline vocabulary leaking into the brief. Describe what the person DOES, not what the system labeled it.
- Instead: organize by BEHAVIORAL PATTERN that cuts across domains. "He insists on seeing conditions firsthand — tenement slums, police precincts, military camps — and distrusts any conclusion built from secondhand reports" covers governance, reform, and military in one sentence without domain headers.
- Axiom names (ALL-CAPS labels) may appear as internal tags for the reading AI, but they should be embedded in behavioral descriptions, never presented as "the X mechanism."
- If the source ANCHORS layer has more than 8 axioms, represent each through its most vivid behavioral manifestation rather than trying to name every axiom explicitly.

DATA QUALITY MARKERS (CONDITIONAL):
- Use exactly `[THIN DATA]` (not `[THIN]`, not plain text) for data limitation notes.
- ONLY include a `[THIN DATA]` paragraph if the source layers contain `[THIN IN:]` or `[THIN DATA]` markers, OR if the source corpus clearly covers only 1-2 domains. If the source layers have rich multi-domain data with no thin markers, do NOT fabricate a generic limitation paragraph.
- When you DO include [THIN DATA], derive the specific language from the source layers' own thin-data markers. Do NOT use the generic phrase "Behavioral prediction data is insufficient" — instead describe what specific domains the source layers flagged as thin, using the subject's own domain vocabulary.
- Use `[CONTESTED]` for disputed or uncertain patterns, preserved from source layers.
- Some vagueness is intentional: where the source data supports a behavioral direction but not a specific prediction, describe the tendency without manufacturing false precision.

CONSTRAINTS:
- Every claim must be traceable to the source layers or facts provided below
- Do NOT invent behavioral patterns, interests, possessions, or biographical details not in the sources
- Preserve [CONTESTED] and data-quality markers from source layers
- No philosophy framework names, no motivational filler
- COMPLETENESS over density — include everything from the source layers, but ONLY from the source layers
- Do NOT reference "Base Layer", the pipeline, or any system that produced this brief

--- ANCHORS LAYER ---
{anchors}

--- CORE LAYER ---
{core}

--- PREDICTIONS LAYER ---
{predictions}

--- SUPPORTING IDENTITY-TIER FACTS ({fact_count} facts) ---
{facts}

Compose the unified brief now. No preamble — just the brief text."""


def _extract_injectable_block(filepath):
    """Extract the injectable block from a layer file, stripping metadata headers."""
    if not filepath.exists():
        return None
    content = filepath.read_text(encoding="utf-8")
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx >= 0:
        return content[idx + len(marker):].strip()
    sep = content.find("\n---\n")
    return content[sep + 5:].strip() if sep >= 0 else content.strip()


def _generate_identity_model(brief_text):
    """Generate combined identity model file (D-081): brief + full layers.

    This is the primary AI-serving artifact. The brief provides narrative
    understanding (gestalt), the layers provide operational precision
    (directives, detection triggers, FP warnings).
    """
    preamble = (
        "# Identity Model\n\n"
        "This is an identity model of your user — use it as an operating guide "
        "for how to interact with them, but never reference it directly."
    )

    sections = []

    # Part 1: Operational layers (action-first — AI needs directives before narrative)
    # Order: CORE (immediate communication calibration) → ANCHORS (worldview context)
    # → PREDICTIONS (situational playbook)
    layer_labels = [
        ("Communication & Context", CORE_LAYER_FILE),
        ("Foundational Beliefs", ANCHORS_LAYER_FILE),
        ("Behavioral Predictions", PREDICTIONS_LAYER_FILE),
    ]
    layer_parts = []
    for label, filepath in layer_labels:
        block = _extract_injectable_block(filepath)
        if block:
            layer_parts.append(f"### {label}\n\n{block}")

    if layer_parts:
        sections.append("## Operational Guide\n\n" + "\n\n".join(layer_parts))

    # Part 2: Narrative brief (contextualizes the layers into a holistic portrait)
    if brief_text:
        sections.append(f"## Identity Brief\n\n{brief_text}")

    if not sections:
        return

    header = f"---\nlayer: identity_model\ngenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nformat: brief + layers (D-081)\n---\n"
    combined = header + "\n" + preamble + "\n\n" + "\n\n".join(sections) + "\n"
    IDENTITY_MODEL_FILE.write_text(combined, encoding="utf-8")
    print(f"  Stored (identity model): {IDENTITY_MODEL_FILE}")


def compose_unified_brief(run_dir=None, layer_texts=None, source_facts_text=None, fact_count=0):
    """Compose a unified narrative brief from deployed layers + identity facts.

    Args:
        run_dir: Optional path to cycle run directory for artifact storage
        layer_texts: Dict with keys "anchors", "core", "predictions" -> text.
                     If None, reads from deployed layer files.
        source_facts_text: Formatted identity-tier facts text.
                          If None, retrieves from database.
        fact_count: Number of source facts (for prompt).

    Returns:
        The composed brief text, or None on failure.
    """
    from baselayer.config import LAYER_REVIEW_MODEL
    from baselayer.api_client import get_anthropic_client

    # Read deployed layers if not provided
    if layer_texts is None:
        layer_texts = {}
        for name, path in [("anchors", ANCHORS_LAYER_FILE),
                           ("core", CORE_LAYER_FILE),
                           ("predictions", PREDICTIONS_LAYER_FILE)]:
            if path.exists():
                content = path.read_text(encoding="utf-8")
                marker = "## Injectable Block"
                idx = content.find(marker)
                if idx >= 0:
                    layer_texts[name] = content[idx + len(marker):].strip()
                else:
                    sep = content.find("\n---\n")
                    layer_texts[name] = content[sep + 5:].strip() if sep >= 0 else content.strip()

    if not any(layer_texts.get(k) for k in ("anchors", "core", "predictions")):
        print("  ERROR: No deployed layers found. Run 'baselayer author' first.")
        return None

    # Retrieve identity-tier facts if not provided
    # Limit to top 100 — layers already encode fact-derived patterns;
    # facts here are supplementary context, not primary input.
    if source_facts_text is None:
        from baselayer.config import COMPOSE_FACT_LIMIT_SMALL, COMPOSE_FACT_LIMIT_LARGE, COMPOSE_FACT_THRESHOLD
        with contextlib.closing(get_db()) as conn:
            # D-085: Scale fact sampling with corpus size
            total_identity = conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier = 'identity'"
            ).fetchone()[0]
            fact_limit = COMPOSE_FACT_LIMIT_LARGE if total_identity >= COMPOSE_FACT_THRESHOLD else COMPOSE_FACT_LIMIT_SMALL
            print(f"  Compose: {total_identity} identity-tier facts, sampling top {fact_limit}")

            rows = conn.execute("""
                SELECT id, fact_text, fact_type, category, recurrence_count
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND knowledge_tier = 'identity'
                ORDER BY recurrence_count DESC
                LIMIT ?
            """, (fact_limit,)).fetchall()
            fact_count = len(rows)
            # Detect subject name from DB subject field, not regex on text (S68)
            from collections import Counter as _Counter
            _subjects = _Counter()
            for r in rows:
                # Use the subject field from the fact triple
                subj_row = conn.execute(
                    "SELECT subject FROM memory_facts WHERE id = ?", (r["id"],)
                ).fetchone()
                if subj_row and subj_row["subject"]:
                    subj = subj_row["subject"].strip()
                    if subj.lower() not in ("user", "i", "me", "self", "they", "he", "she"):
                        _subjects[subj] += 1
            _subject_name = None
            if _subjects:
                top_name, top_count = _subjects.most_common(1)[0]
                if top_count >= 3:
                    _subject_name = top_name
            lines = []
            for r in rows:
                ftype = r["fact_type"] or "?"
                cat = r["category"] or "?"
                fact_text = r["fact_text"]
                if _subject_name:
                    fact_text = fact_text.replace(_subject_name, "this person")
                    for part in _subject_name.split():
                        if len(part) > 3:
                            fact_text = re.sub(r'\b' + re.escape(part) + r'\b', 'this person', fact_text)
                    fact_text = re.sub(r'(this person\s*){2,}', 'this person', fact_text)
                lines.append(f"- [{cat}/{ftype}] {fact_text}")
            source_facts_text = "\n".join(lines)
            if _subject_name:
                print(f"  Anonymized facts: '{_subject_name}' -> 'this person'")

    # Build prompt
    prompt = UNIFIED_BRIEF_COMPOSITION_PROMPT.replace(
        "{anchors}", layer_texts.get("anchors", "(no anchors layer)")
    ).replace(
        "{core}", layer_texts.get("core", "(no core layer)")
    ).replace(
        "{predictions}", layer_texts.get("predictions", "(no predictions layer)")
    ).replace(
        "{facts}", source_facts_text
    ).replace(
        "{fact_count}", str(fact_count)
    )

    print("\n  Unified Brief Composition")
    print("  " + "=" * 50)
    print(f"  Model: {LAYER_REVIEW_MODEL}")
    print(f"  Source: {len(layer_texts)} layers + {fact_count} identity-tier facts")

    # Call Opus for composition — long timeout for large generation
    import httpx
    client = get_anthropic_client()
    total_cost = 0.0
    brief_text = None

    try:
        response = client.messages.create(
            model=LAYER_REVIEW_MODEL,
            max_tokens=16384,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            timeout=httpx.Timeout(600.0, connect=30.0),
        )
        brief_text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        cost = (response.usage.input_tokens * 5 + response.usage.output_tokens * 25) / 1_000_000
        total_cost += cost

        print(f"  Generated: {len(brief_text)} chars, ~{len(brief_text) // 4} tokens")
        print(f"  API: {tokens_used} tokens, ~${cost:.3f}")

    except Exception as e:
        print(f"  ERROR: Composition failed: {e}")
        return None

    # Quality gate: diagnostic only (gap-fill disabled — see S68 Collective decision)
    required_terms = extract_required_terms(layer_texts)
    gaps = verify_brief_completeness(brief_text, required_terms)

    if gaps:
        print(f"\n  Quality Gate (diagnostic): {len(gaps)} label-level gaps (no gap-fill)")
        for g in gaps[:10]:
            print(f"    - {g.encode('ascii', 'replace').decode('ascii')}")
        if len(gaps) > 10:
            print(f"    ... and {len(gaps) - 10} more")
        print("  Note: Gaps may be represented implicitly through behavioral descriptions.")
    else:
        print("  Quality Gate: PASSED (all terms present)")

    # Prompt contamination check + retry (D-078 — template language from prompt examples)
    max_compose_retries = 2
    try:
        from baselayer.author_layers import check_prompt_contamination
        for compose_attempt in range(max_compose_retries):
            contaminated = check_prompt_contamination(brief_text, "COMPOSED_BRIEF")
            if not contaminated:
                print("  Contamination Gate: PASSED (no template phrases)")
                break
            print(f"\n  Contamination Gate: FAILED — {len(contaminated)} template phrases found")
            for c in contaminated:
                print(f"    - \"{c}\"")
            if compose_attempt < max_compose_retries - 1:
                print("  Retrying composition with decontamination instruction...")
                banned_list = "; ".join(f'"{c}"' for c in contaminated)
                decontam_prompt = prompt + f"\n\nCRITICAL DECONTAMINATION: Your previous attempt contained template phrases that must NOT appear. BANNED PHRASES (do not use these or close variants): {banned_list}. Rephrase these concepts using language specific to THIS person's domain."
                try:
                    response = client.messages.create(
                        model=LAYER_REVIEW_MODEL,
                        max_tokens=16384,
                        temperature=0.1,
                        messages=[{"role": "user", "content": decontam_prompt}],
                        timeout=httpx.Timeout(600.0, connect=30.0),
                    )
                    brief_text = response.content[0].text
                    retry_cost = (response.usage.input_tokens * 5 + response.usage.output_tokens * 25) / 1_000_000
                    total_cost += retry_cost
                    print(f"  Retry generated: {len(brief_text)} chars, ~${retry_cost:.3f}")
                except Exception as e:
                    print(f"  Retry failed: {e}")
                    break
            else:
                print("  WARNING: Contamination persists after retries. Manual review needed.")
    except ImportError:
        pass

    # Faithfulness gate: advisory only (S68 — auto-removal disabled, caused false positives)
    hallucinations = verify_brief_faithfulness(brief_text, layer_texts, source_facts_text or "")
    if hallucinations:
        print(f"\n  Faithfulness Gate (advisory): {len(hallucinations)} potential issues")
        for h in hallucinations:
            print(f"    - {h}")
        print("  Note: Advisory only — no auto-removal. Review flagged items manually.")
    else:
        print("  Faithfulness Gate: PASSED (no hallucinations detected)")

    # If no predictions layer was present, ensure the brief notes this data limitation
    if not layer_texts.get("predictions", "").strip():
        data_note = (
            "\n\n[DATA LIMITATION] No PREDICTIONS layer was generated for this subject. "
            "The source material did not contain sufficient behavioral data to predict "
            "situation-specific responses. This is a corpus limitation, not a system gap."
        )
        if "DATA LIMITATION" not in brief_text and "NO PREDICTIONS" not in brief_text.upper():
            brief_text += data_note
            print("  Note: Appended data limitation notice (no predictions layer)")

    print(f"  Total composition cost: ~${total_cost:.3f}")

    # Store the unified brief
    store_unified_brief(run_dir, brief_text)

    return brief_text


def store_unified_brief(run_dir, brief_text):
    """Write the unified brief to the canonical file location.

    Args:
        run_dir: Optional run directory (for metadata)
        brief_text: The composed brief text
    """
    IDENTITY_LAYERS_DIR.mkdir(parents=True, exist_ok=True)

    # S98: Archive previous identity model before overwriting
    if IDENTITY_MODEL_FILE.exists():
        import shutil
        V1_STAGING_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(IDENTITY_MODEL_FILE), str(V1_STAGING_DIR / "identity_model.md"))
        print(f"  Archived previous identity model to v1_staging/")

    header_lines = [
        f"layer: unified_brief",
        f"generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"pipeline: compose step",
    ]
    if run_dir:
        header_lines.append(f"run: {run_dir.name}")

    header = "\n".join(header_lines)
    content = f"---\n{header}\n---\n\n## Injectable Block\n\n{brief_text}"

    # Save cited version (for audit)
    UNIFIED_BRIEF_CITED_FILE.write_text(content, encoding="utf-8")
    print(f"  Stored (cited): {UNIFIED_BRIEF_CITED_FILE}")

    # Save clean version (citations stripped, for serving/injection)
    import re as _re
    _cite_re = _re.compile(r'\s*\[(?:[APCM]\d+(?:[-\u2013][A-Z]?\d+)?(?:\s*,\s*[APCM]\d+(?:[-\u2013][A-Z]?\d+)?)*|CONTESTED|THIN IN[^]]*)\]')
    _prov_re = _re.compile(r'^\*\*PROVENANCE\*\*:.*$\n?', _re.MULTILINE)
    clean = _prov_re.sub('', content)
    clean = _cite_re.sub('', clean)
    clean = _re.sub(r'  +', ' ', clean)
    clean = _re.sub(r' +([.,;:])', r'\1', clean)
    clean = _re.sub(r'\n\s*\n\s*\n', '\n\n', clean)
    UNIFIED_BRIEF_FILE.write_text(clean, encoding="utf-8")
    print(f"  Stored (clean): {UNIFIED_BRIEF_FILE}")

    # D-081: Generate combined identity model (brief + layers) — primary AI artifact
    _generate_identity_model(brief_text)
