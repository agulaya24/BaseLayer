"""
Three-Layer Identity Block Authoring Pipeline (D-043)

Retrieves facts from the database, generates identity layers via API, and stores
them as injectable markdown files. Three layers:

  ANCHORS  — epistemic axioms (beliefs reasoned FROM, not ABOUT)
  CORE     — communication & operating guide (how to engage with this person)
  PREDICTIONS — behavioral patterns (situation -> pattern -> directive)

Modes:
  python author_layers.py --retrieve anchors       # Show facts for manual authoring
  python author_layers.py --retrieve core
  python author_layers.py --retrieve predictions
  python author_layers.py --generate anchors       # Generate via API (Sonnet)
  python author_layers.py --generate core
  python author_layers.py --generate predictions
  python author_layers.py --generate all           # Generate all three layers
  python author_layers.py --show anchors           # Show current injectable block
  python author_layers.py --show all               # Show all layers combined
  python author_layers.py --brief                  # Show assembled three-layer brief

Design constraints:
  D-040: Blind authoring — facts only, no prior blocks or analysis docs
  D-041: Audience is the understanding the AI needs to take on (updated S44)
  D-043: Three-layer architecture — ANCHORS + CORE + PREDICTIONS
  D-044: Scoped memory — personal scope only for identity blocks
  D-046: Cheap constraint, expensive discrimination
         Retrieval constrains the generation space.
"""

import contextlib
import sqlite3
import json
import argparse
import sys
import io
import os
import re
import time
from pathlib import Path
from datetime import datetime

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

from baselayer.config import (
    DATABASE_FILE, IDENTITY_LAYERS_DIR,
    ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
    AUTHORING_EXCLUSION_PATTERNS, LAYER_GENERATION_MODEL,
    AUTHORING_MAX_DOMAIN_PERCENT, AUTHORING_DOMAIN_KEYWORDS,
    get_db,
)


# ===========================================================================
# DATABASE
# ===========================================================================


def _get_user_pronouns():
    """Load user pronouns from entity_map.json. Returns 'they/them' as default."""
    from baselayer.config import PROJECT_ROOT
    entity_file = PROJECT_ROOT / "data" / "entity_map.json"
    if entity_file.exists():
        try:
            raw = json.loads(entity_file.read_text(encoding="utf-8"))
            return raw.get("_user_pronouns", "they/them")
        except Exception:
            pass
    return "they/them"


def apply_exclusion_filter(facts):
    """Remove facts matching AUTHORING_EXCLUSION_PATTERNS (D-040, D-044)."""
    filtered = []
    for f in facts:
        text_lower = f["fact_text"].lower()
        excluded = any(p.lower() in text_lower for p in AUTHORING_EXCLUSION_PATTERNS)
        if not excluded:
            filtered.append(f)
    return filtered


def _has_tiered_facts(conn):
    """Check if facts have FULL classification (tier + commitment_depth + scope).

    Returns True only if the full classification pipeline ran (tier + depth + scope).
    Returns False if we're in simplified mode — even if rule-based tiering was applied,
    the simplified path should be used when commitment_depth is not populated.
    """
    try:
        # Need BOTH identity tier AND conviction depth to use the non-simplified path
        row = conn.execute("""
            SELECT COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL
              AND knowledge_tier = 'identity'
              AND commitment_depth IS NOT NULL
              AND commitment_depth != 'unclassified'
              AND scope IS NOT NULL
        """).fetchone()
        return row[0] > 0
    except sqlite3.OperationalError:
        return False


# Predicate-based routing for simplified pipeline (no tiering/classification).
# Maps predicates to the layer they most naturally belong to.
ANCHOR_PREDICATES = {"believes", "values", "prioritizes", "decided", "identifies_as"}
PREDICTION_PREDICATES = {
    "practices", "avoids", "struggles_with", "fears", "excels_at",
    "enjoys", "dislikes", "hates", "loves", "prefers", "monitors",
    "plays", "trades", "builds", "manages", "maintains", "follows",
}
# CORE gets everything — no predicate filter needed.


def generate_data_profile(conn):
    """Generate a statistical data profile for authoring agents.

    Returns a formatted string describing the shape of the underlying fact corpus —
    predicate distribution, fact type breakdown, source types, and behavioral signal
    density. Injected into authoring prompts so agents can reason about what the data
    can and cannot support.
    """
    simplified = not _has_tiered_facts(conn)

    # Total active facts and identity-tier count
    total = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchone()[0]

    if simplified:
        identity = total  # All facts are usable in simplified mode
    else:
        identity = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier = 'identity'"
        ).fetchone()[0]

    # Predicate distribution — use all facts in simplified mode
    tier_filter = "" if simplified else "AND knowledge_tier = 'identity'"
    pred_rows = conn.execute(f"""
        SELECT predicate, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL {tier_filter}
        GROUP BY predicate ORDER BY cnt DESC
    """).fetchall()
    top_preds = pred_rows[:10]

    # Behavioral signal predicates (tension/conflict/failure-mode signal)
    behavioral_preds = {"struggles_with", "avoids", "fears", "dislikes", "conflicts_with"}
    behavioral_count = sum(r[1] for r in pred_rows if r[0] in behavioral_preds)
    behavioral_pct = (behavioral_count / identity * 100) if identity > 0 else 0

    # Conviction predicates (belief/value signal)
    conviction_preds = {"believes", "values", "prioritizes"}
    conviction_count = sum(r[1] for r in pred_rows if r[0] in conviction_preds)
    conviction_pct = (conviction_count / identity * 100) if identity > 0 else 0

    # Action predicates (observed behavior signal)
    action_preds = {"practices", "builds", "manages", "trades", "founded", "maintains"}
    action_count = sum(r[1] for r in pred_rows if r[0] in action_preds)
    action_pct = (action_count / identity * 100) if identity > 0 else 0

    # Fact type distribution
    type_rows = conn.execute(f"""
        SELECT fact_type, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL {tier_filter}
        GROUP BY fact_type ORDER BY cnt DESC
    """).fetchall()

    # Source type distribution
    source_rows = conn.execute(f"""
        SELECT c.source, COUNT(DISTINCT f.id) as cnt
        FROM memory_facts f
        LEFT JOIN conversations c ON f.source_conversation_id = c.id
        WHERE f.superseded_by IS NULL {('AND f.knowledge_tier = ' + "'identity'") if not simplified else ''}
        GROUP BY c.source ORDER BY cnt DESC
    """).fetchall()

    # Build the profile
    lines = ["--- DATA PROFILE ---"]
    lines.append(f"Total active facts: {total} | Identity-tier: {identity}")
    lines.append(f"Top predicates: {', '.join(f'{r[0]} ({r[1]})' for r in top_preds)}")
    lines.append(f"Conviction signal (believes/values/prioritizes): {conviction_count} ({conviction_pct:.1f}%)")
    lines.append(f"Action signal (practices/builds/manages/trades/founded): {action_count} ({action_pct:.1f}%)")
    lines.append(f"Tension signal (struggles_with/avoids/fears/dislikes/conflicts_with): {behavioral_count} ({behavioral_pct:.1f}%)")

    if type_rows:
        lines.append(f"Fact types: {', '.join(f'{r[0]} ({r[1]})' for r in type_rows)}")
    if source_rows:
        lines.append("Source types: " + ", ".join(f"{r[0] or 'unknown'} ({r[1]})" for r in source_rows))

    # Interpretive notes — let the agent reason from these
    notes = []
    if conviction_pct > 30 and behavioral_pct < 10:
        notes.append("High conviction, low tension: corpus describes what this person believes more than how they struggle. Infer tensions from spaces between beliefs — where do stated values conflict with each other or with observed actions?")
    if behavioral_pct > 20:
        notes.append("High tension signal: corpus contains rich internal conflict data. Lean into failure modes and contradictions.")
    if action_pct > 25:
        notes.append("High action signal: corpus describes what this person does, not just what they think. Ground behavioral predictions in observed patterns.")
    if identity < 50:
        notes.append("Small corpus: fewer than 50 facts. Be conservative with predictions — note data limitations rather than over-extrapolating.")
    if simplified:
        notes.append("Simplified pipeline mode: facts routed to layers by predicate type (no classification/tiering). All active facts are available.")

    source_types = [r[0] for r in source_rows if r[0]]
    if source_types and all(s in ("text_file", "journal") for s in source_types):
        notes.append("Single-author text source (autobiography/journal/treatise). All observations are self-reported — the person's self-image, not external observation.")

    if notes:
        lines.append("Observations:")
        for n in notes:
            lines.append(f"  - {n}")
    lines.append("--- END DATA PROFILE ---")

    return "\n".join(lines)


# ===========================================================================
# RETRIEVAL QUERIES — one per layer
# ===========================================================================

def retrieve_anchors_facts(conn):
    """
    ANCHORS layer input: conviction-level identity facts.

    These are the deepest beliefs — facts classified as identity-tier with
    conviction-level commitment depth. The anchor extraction process synthesizes
    these into epistemic axioms.

    If epistemic_anchors table exists with formalized axioms, returns those
    instead (they are the refined output of the extraction process).
    """
    # Check if formalized anchors exist
    try:
        rows = conn.execute("""
            SELECT anchor_number, anchor_text, status, review_notes, source_fact_ids
            FROM epistemic_anchors
            WHERE status IN ('confirmed', 'active', 'confirmed_flagged')
              AND superseded_by IS NULL
            ORDER BY anchor_number
        """).fetchall()
        if rows:
            return {
                "source": "epistemic_anchors_table",
                "facts": [dict(r) for r in rows],
                "count": len(rows),
            }
    except sqlite3.OperationalError:
        pass  # Table doesn't exist — fall through to raw facts

    # Raw conviction-level identity facts
    simplified = not _has_tiered_facts(conn)

    if simplified:
        # Simplified pipeline: route by predicate instead of tier/classification
        # Surface identifies_as facts first — these represent core self-concept
        # and are foundational by definition (Collective review S91)
        placeholders = ",".join(["?"] * len(ANCHOR_PREDICATES))
        rows = conn.execute(f"""
            SELECT id, fact_text, fact_type, commitment_depth, recurrence_count,
                   CASE WHEN predicate = 'identifies_as' THEN 0 ELSE 1 END AS sort_group
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND predicate IN ({placeholders})
            ORDER BY sort_group, recurrence_count DESC, fact_text
        """, list(ANCHOR_PREDICATES)).fetchall()
        source_label = "predicate_routed_anchors"
    else:
        rows = conn.execute("""
            SELECT id, fact_text, fact_type, commitment_depth, recurrence_count
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND scope = 'personal'
              AND knowledge_tier = 'identity'
              AND commitment_depth = 'conviction'
            ORDER BY recurrence_count DESC, fact_text
        """).fetchall()
        source_label = "conviction_identity_facts"

    if simplified and rows:
        print(f"  [Simplified pipeline] ANCHORS: {len(rows)} facts via predicate routing "
              f"({', '.join(sorted(ANCHOR_PREDICATES))})")

    facts = apply_exclusion_filter(rows)
    return {
        "source": source_label,
        "facts": [dict(f) for f in facts],
        "count": len(facts),
    }


MAX_FACTS_PER_CATEGORY = 15  # Prevents any single topic from dominating retrieval


def cap_by_category(facts, max_per_category=MAX_FACTS_PER_CATEGORY):
    """Cap facts per category to ensure topic diversity in retrieval.

    Within each category, facts retain their original sort order (commitment_depth
    then recurrence). This prevents high-recurrence domains (e.g., trading) from
    crowding out lower-recurrence but identity-significant topics (e.g., hobbies).
    """
    by_cat = {}
    for f in facts:
        cat = f.get("category") or "unknown"
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(f)

    capped = []
    for cat, cat_facts in by_cat.items():
        capped.extend(cat_facts[:max_per_category])

    return capped


def cap_by_domain(facts, max_percent=AUTHORING_MAX_DOMAIN_PERCENT):
    """Cap facts per domain to prevent any single life domain from dominating.

    D-055: Trading facts (or any other high-recurrence domain) spread across
    multiple categories, bypassing category caps. This function applies a
    cross-category domain cap based on keyword matching.

    Facts within each domain retain their original sort order. When a domain
    exceeds max_percent, the lowest-priority facts (last in sort order) are
    dropped first.
    """
    total = len(facts)
    if total == 0:
        return facts

    max_per_domain = max(1, int(total * max_percent / 100))

    # Classify each fact by domain
    domain_indices = {}  # domain -> list of indices
    for i, f in enumerate(facts):
        text_lower = f["fact_text"].lower()
        for domain, keywords in AUTHORING_DOMAIN_KEYWORDS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                if domain not in domain_indices:
                    domain_indices[domain] = []
                domain_indices[domain].append(i)

    # Identify indices to drop (excess facts from over-represented domains)
    drop_indices = set()
    for domain, indices in domain_indices.items():
        if len(indices) > max_per_domain:
            # Drop from the end (lowest priority in sort order)
            for idx in indices[max_per_domain:]:
                drop_indices.add(idx)

    result = [f for i, f in enumerate(facts) if i not in drop_indices]

    for domain, indices in domain_indices.items():
        if len(indices) > max_per_domain:
            print(f"    Domain cap: {domain} {len(indices)} -> {max_per_domain} facts ({max_percent}% of {total})")

    return result


def retrieve_core_facts(conn):
    """
    CORE layer input: all identity-tier personal facts.

    Grouped by fact_type for structured authoring:
    - biographical: background, demographics, life events
    - behavioral: how they operate, patterns, habits
    - positional: beliefs, values, positions on things
    - preference: likes, dislikes, preferences

    Per-category cap ensures topic diversity (Session 38 fix).
    """
    simplified = not _has_tiered_facts(conn)
    results = {}

    if simplified:
        # Simplified pipeline: use ALL facts for CORE (it's the comprehensive layer)
        rows = conn.execute("""
            SELECT id, fact_text, fact_type, commitment_depth,
                   recurrence_count, category, predicate
            FROM memory_facts
            WHERE superseded_by IS NULL
            ORDER BY recurrence_count DESC
        """).fetchall()

        facts = apply_exclusion_filter(rows)
        facts = cap_by_category([dict(f) for f in facts])
        facts = cap_by_domain(facts)

        # Group by predicate category instead of fact_type
        for f in facts:
            pred = f.get("predicate", "unknown")
            if pred in ANCHOR_PREDICATES:
                bucket = "positional"
            elif pred in PREDICTION_PREDICATES:
                bucket = "behavioral"
            elif pred in {"works_at", "lives_in", "married_to", "raised_in",
                          "graduated_from", "attended", "experienced", "lost",
                          "founded", "raised_by", "parents"}:
                bucket = "biographical"
            else:
                bucket = "preference"
            results.setdefault(bucket, []).append(f)

        total = sum(len(v) for v in results.values())
        print(f"  [Simplified pipeline] CORE: {total} facts via predicate routing "
              f"({', '.join(f'{k}: {len(v)}' for k, v in results.items())})")
    else:
        for fact_type in ["biographical", "behavioral", "positional", "preference"]:
            rows = conn.execute("""
                SELECT id, fact_text, fact_type, commitment_depth,
                       recurrence_count, category
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND scope = 'personal'
                  AND knowledge_tier = 'identity'
                  AND fact_type = ?
                ORDER BY
                  CASE commitment_depth
                    WHEN 'conviction' THEN 1
                    WHEN 'position' THEN 2
                    WHEN 'preference' THEN 3
                    WHEN 'factual' THEN 4
                    ELSE 5
                  END,
                  recurrence_count DESC
            """, (fact_type,)).fetchall()

            facts = apply_exclusion_filter(rows)
            facts = cap_by_category([dict(f) for f in facts])
            facts = cap_by_domain(facts)
            results[fact_type] = facts

        total = sum(len(v) for v in results.values())

    return {
        "source": "predicate_routed_by_type" if simplified else "identity_tier_by_type",
        "facts_by_type": results,
        "count": total,
    }


def retrieve_predictions_facts(conn):
    """
    PREDICTIONS layer input: behavioral identity-tier facts, with fallback
    expansion to action-oriented positional facts when behavioral count is low.

    Primary gate: fact_type = 'behavioral' (recurring patterns).
    Fallback (S65): When behavioral facts < 5, also include positional facts
    with action predicates (prioritizes, advocates_for, opposes, excels_at,
    demands, rejects). This handles treatise authors and historical subjects
    where Haiku classifies action patterns as positional rather than behavioral.
    Behavioral facts sort first; fallback facts sort after.
    """
    simplified = not _has_tiered_facts(conn)

    if simplified:
        # Simplified pipeline: route by behavioral predicates
        placeholders = ",".join(["?"] * len(PREDICTION_PREDICATES))
        rows = conn.execute(f"""
            SELECT id, fact_text, fact_type, commitment_depth,
                   recurrence_count, category
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND predicate IN ({placeholders})
            ORDER BY recurrence_count DESC
        """, list(PREDICTION_PREDICATES)).fetchall()

        print(f"  [Simplified pipeline] PREDICTIONS: {len(rows)} facts via predicate routing "
              f"({', '.join(sorted(PREDICTION_PREDICATES)[:5])}...)")
    else:
        # Primary: all behavioral identity-tier facts
        rows = conn.execute("""
            SELECT id, fact_text, fact_type, commitment_depth,
                   recurrence_count, category
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND scope = 'personal'
              AND knowledge_tier = 'identity'
              AND fact_type = 'behavioral'
            ORDER BY
              CASE commitment_depth
                WHEN 'conviction' THEN 1
                WHEN 'position' THEN 2
                WHEN 'factual' THEN 3
                ELSE 4
              END,
              recurrence_count DESC
        """).fetchall()

        behavioral_count = len(rows)

        # Fallback: expand to action-oriented positional facts when behavioral is thin
        if behavioral_count < 5:
            action_predicates = [
                "prioritizes", "advocates_for", "opposes",
                "excels_at", "demands", "rejects",
            ]
            ap_placeholders = ",".join(["?"] * len(action_predicates))
            fallback_rows = conn.execute(f"""
                SELECT id, fact_text, fact_type, commitment_depth,
                       recurrence_count, category
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND scope = 'personal'
                  AND knowledge_tier = 'identity'
                  AND fact_type = 'positional'
                  AND predicate IN ({ap_placeholders})
                ORDER BY recurrence_count DESC
            """, action_predicates).fetchall()

            if fallback_rows:
                print(f"  Behavioral facts thin ({behavioral_count}), expanding with "
                      f"{len(fallback_rows)} action-oriented positional facts")
                rows = list(rows) + list(fallback_rows)

    facts = apply_exclusion_filter(rows)
    facts = cap_by_category([dict(f) for f in facts])
    facts = cap_by_domain(facts)
    return {
        "source": "predicate_routed_behavioral" if simplified else "behavioral_identity_tier",
        "facts": facts,
        "count": len(facts),
    }


# ===========================================================================
# DISPLAY — for --retrieve mode
# ===========================================================================

def display_anchors(data):
    print(f"\n=== ANCHORS Layer — Retrieval ({data['count']} items) ===\n")

    if data["source"] == "epistemic_anchors_table":
        print("Source: Formalized epistemic anchors (epistemic_anchors table)\n")
        for a in data["facts"]:
            print(f"  [{a['status']}] Anchor #{a['anchor_number']}")
            print(f"    {a['anchor_text'][:120]}")
            print()
    else:
        print("Source: Conviction-level identity facts (no formalized anchors found)\n")
        for f in data["facts"][:50]:
            rec = f.get("recurrence_count", 0) or 0
            print(f"  [{f['commitment_depth']}] {f['fact_text'][:100]}  (rec: {rec})")
        if data["count"] > 50:
            print(f"\n  ... and {data['count'] - 50} more")


def display_core(data):
    print(f"\n=== CORE Layer — Retrieval ({data['count']} facts) ===\n")

    for fact_type, facts in data["facts_by_type"].items():
        print(f"  --- {fact_type.upper()} ({len(facts)} facts) ---")
        for f in facts[:20]:
            depth = f.get("commitment_depth", "?")
            rec = f.get("recurrence_count", 0) or 0
            print(f"    [{depth}] {f['fact_text'][:100]}  (rec: {rec})")
        if len(facts) > 20:
            print(f"    ... and {len(facts) - 20} more")
        print()


def display_predictions(data):
    print(f"\n=== PREDICTIONS Layer — Retrieval ({data['count']} facts) ===\n")

    for f in data["facts"][:50]:
        depth = f.get("commitment_depth", "?")
        rec = f.get("recurrence_count", 0) or 0
        print(f"  [{depth}] {f['fact_text'][:100]}  (rec: {rec})")
    if data["count"] > 50:
        print(f"\n  ... and {data['count'] - 50} more")


# ===========================================================================
# GENERATION PROMPTS — D-041 encoded (updated Session 44)
# ===========================================================================

ANCHORS_PROMPT = """You are authoring the EPISTEMIC ANCHORS layer of a personal identity brief.

CRITICAL: The audience is the intelligence and understanding an AI needs to take on to communicate naturally with this person. Every sentence you write must shape that understanding — not document the person, but create comprehension in the reader. Write to transform how the AI thinks about interacting with this person, not to inform it about who they are. Portrait descriptions are FORBIDDEN.

These are axioms — beliefs this person reasons FROM, not ABOUT. Pre-set certainties. Use them to narrow predictions before situation-specific information arrives.

STYLE REQUIREMENT — Directive-embedded descriptions:
Each axiom must be ONE integrated statement where the description IS the directive. The AI reading this should know what to do WITHOUT a separate instruction line.

IMPORTANT: The examples below are about a FICTIONAL person named "Alex" — they illustrate the STYLE only. Do NOT reuse any of this language in your output. Your output must be derived entirely from the input axioms and facts.

BAD (portrait + separate directive):
  "Alex cannot tolerate wasted resources in any project."
  "AI directive: Flag inefficiencies in proposed plans."

GOOD (directive-embedded — description IS the directive):
  "Before proposing a plan, audit it for resource waste — Alex will reject anything that allocates effort without measurable return and will distrust your judgment for not catching it."

BAD (portrait): "Alex views broken promises as moral failures."
GOOD (directive-embedded): "Never frame a missed commitment as circumstantial — treat every broken promise as a choice that requires accountability, not explanation."

These examples show the PATTERN: fuse what the person believes with what the AI should do. Generate your own language from the input data — do not copy or adapt the examples above.

For each axiom:
- Name it in 1-2 uppercase words (shorter is better: COHERENCE not COHERENCE IMPERATIVE)
- Write 1-3 sentences where description and directive are fused — every sentence tells the AI what to do AND why
- Include a DETECTION TRIGGER: a specific conversational signal that tells the AI this axiom is active. Format: "Active when: [specific observable pattern in their messages]"
- If an axiom is contested or flagged, note this briefly

DETECTION TRIGGER format:
  [AXIOM NAME] — Active when: [specific observable pattern in their messages, derived from the input facts]
Derive both the axiom name AND the detection trigger from the input data. Do NOT reuse example names or triggers from these instructions.

After all axioms, include an AXIOM INTERACTIONS section that:
- Shows specific interaction pairs: how axioms reinforce, tension with, or cascade into each other in THIS person's life
- Includes the specific conflict resolution directives provided in the input
- For each tension pair, describe what THIS person actually does when the axioms collide — use concrete examples from the input facts, not generic advice about "holding tension" or "acknowledging both sides"
- Format as short labeled pairs, not a wall of prose
- Do NOT include a generic "general frame" or universal statement about how to handle axiom conflicts. Jump straight to the specific pairs

When behavior contradicts an axiom, that is diagnostic — the AI should surface it as recognition ("you're doing the thing you said you don't do"), not correction.

IMPORTANT — For any axiom about emotion or internal process: do NOT describe the person's internal process (e.g., "they monitor emotions"). Instead, tell the AI what to OUTPUT differently — fuse the emotional pattern with the directive action. The sentence should instruct the AI how to respond when that emotional pattern appears, not describe what the person does internally.

INCOMPLETENESS: These axioms are derived from available conversation data, which is inherently incomplete. If an axiom has thin support (fewer than 3 independent facts), note it with [THIN DATA] rather than presenting it with false confidence. If domain coverage is uneven (e.g., heavy professional data, sparse personal data), acknowledge this in the interactions section. The honest posture is "here is what we know" not "here is the complete picture."

PROVENANCE — Each axiom must cite the input facts it draws from. After each axiom block, include a provenance line:
  provenance: [F-xxx, F-yyy, ...]
Use the [F-xxx] IDs provided in the input facts. Only cite facts that directly support the axiom. This enables trace-back from claims to source evidence.

LEXICON IDS — Assign each axiom a stable identifier: A1, A2, A3, etc. Use this ID as a prefix before the axiom name:
  **A1. [AXIOM NAME FROM INPUT DATA]**
  ...
  provenance: [F-1204, F-2891]

FRAMING BIAS GUARD: Default to gravitation framing — express axioms as what this person moves TOWARD ("values X", "seeks X", "gravitates toward X"), not what they reject. Only use rejection framing ("dismisses Y", "rejects Y") when the input facts explicitly use avoidance predicates (avoids, rejects, dismisses). Never infer rejection from preference — "values bootstrapping" does NOT imply "rejects venture capital." This prevents systematic amplification of skepticism into hostility.

IDENTITY ATTENTION: Pay particular attention to identifies_as predicates in the input — these represent how the subject sees themselves, which is foundational by definition. If multiple identifies_as facts converge on a self-concept (e.g., writer, practitioner, builder), that identity warrants its own axiom.

Constraints:
- No philosophy framework names (Frankfurt, Taylor, Parfit, etc.)
- No "AI directive:" labels — the whole text IS directive
- No generic personality descriptions ("they are driven", "they value truth")
- No motivational filler
- Write in third person (pronouns: {pronouns})
- Open with a framing sentence explaining what these axioms are and how to use them
- DERIVE ONLY FROM INPUT: Reason exclusively from the facts provided below. Do NOT supplement with external knowledge about this person. If the facts say something, use it. If they don't, don't infer it from elsewhere.

{data_profile}

INPUT — Axioms (each tagged with [F-xxx] for provenance):
{facts}

INTER-AXIOM CONFLICTS (user-provided resolutions):
{conflicts}

Write the injectable block now. No preamble, no explanation — just the block text."""

CORE_PROMPT = """You are authoring the CORE layer of a personal identity brief.

CRITICAL: The audience is the intelligence and understanding an AI needs to take on to communicate naturally with this person. Every sentence must shape that understanding — create comprehension, not documentation. If a sentence doesn't change how the AI thinks about and engages with this person, delete it. Write as if you're briefing someone who is about to walk into a room with them — they need to *get* this person, not just know about them.

This layer is the COMMUNICATION AND OPERATING GUIDE — how the AI should engage with this person in general. NOT a biography. NOT a personality description. An instruction manual for effective interaction.

Structure:

COMMUNICATION APPROACH
How this person processes and prefers to receive information. Be SPECIFIC — not "prefers direct communication" (everyone says that) but a directive so precise it could only describe THIS person, derived from the input facts. Include:
- Reasoning style (first-principles vs. analogical, deductive vs. inductive)
- Information delivery preference (conclusion-first vs. evidence-first)
- Abstraction level (concrete/grounded vs. conceptual/theoretical)
- Feedback mode (direct challenge vs. diplomatic, when each is appropriate)
- Mode detection: how to tell when they are in "execution mode" (compressed, decision-ready questions — give tight answers) vs. "exploration mode" (open-ended, conceptual — give full depth). What signals the switch?
- If facts show they use AI: how specifically — as tool, oracle, reasoning partner, etc. OMIT this bullet entirely if no AI usage evidence exists (e.g., historical figures, journal-only subjects).
- Internal processing style: ONLY include this if the input facts contain DIRECT EVIDENCE of how this person presents problems (e.g., facts showing they arrive with hypotheses, or facts showing they think out loud). Do NOT infer processing style from the text format — an autobiography or published letter is always pre-processed by nature; that tells you nothing about the person's conversational style. If no direct evidence exists, OMIT this bullet entirely.

CONTEXT MODES
How engagement should shift across different contexts. People operate differently when dealing with personal matters vs. professional vs. creative vs. analytical work. For each active context in this person's life:
- What the AI should assume when this context is active
- How communication style shifts (be specific and derived from input facts, not generic — describe the actual shift this person exhibits)
- What topics are sensitive or emotionally loaded
- When to lead with acknowledgment before analysis vs. when to lead with analysis directly

NARRATIVE ORIENTATION
How this person relates to time and organizes their own experience:
- Are they past-referential, present-focused, or future-projecting?
- How do they tell stories? (chronological, thematic, conclusion-first)
- How should the AI match this temporal mode?

ESSENTIAL CONTEXT
Compressed biographical facts that DIRECTLY change AI behavior. Not "age 31, lives in X" but "Professional identity centers on [X] — connect recommendations to [Y]." Only include facts where knowing them changes what the AI outputs.
- Key relationships AS DECISION CONSTRAINTS (not biography)
- Active life tensions AS NAVIGATION GUIDES (don't resolve — name both sides)
- Frame biography as operational context, not credentials: "founded X and closed contracts with Y — use this as reference for what they have already done, not as credential to repeat back to them"

DOMAIN BALANCE: No single domain should occupy more than ~25% of the block. Compress dominant domains to behavioral essence.

BEHAVIORAL SPECIFICITY — This is the most important quality criterion. Generic directives like "be direct" or "challenge ideas" are worthless — every AI already tries to do this. The test: could this sentence appear in ANY person's CORE layer? If yes, it is too generic. Good CORE sentences are specific enough that only ONE person's layer would contain them. BAD: "They value clear communication." GOOD: A sentence so specific that only THIS person's layer would contain it, derived from their actual behavioral patterns in the input facts. Do NOT reuse examples from these instructions.

D-041 FILTER — Before including ANY detail, ask: "What would the AI do differently knowing this?" If nothing, cut it.

Constraints:
- No philosophy framework names
- No motivational filler
- No portrait descriptions ("they are driven", "complex and multifaceted")
- Specific: real details, not attributes
- ONLY include details present in the input facts. Do NOT invent or hallucinate.
- DERIVE ONLY FROM INPUT: Reason exclusively from the facts provided below. Do NOT supplement with external knowledge about this person. If the facts say something, use it. If they don't, don't infer it from elsewhere.
- ANTI-ANACHRONISM: Use vocabulary appropriate to the subject's era. Do NOT mention AI, technology, or modern tools for historical figures or subjects whose facts show no AI usage. Do NOT use modern corporate jargon ("stakeholders", "leverage", "career advancement") for pre-20th-century subjects.
- Write in third person (pronouns: {pronouns})
- Do NOT include epistemic axioms (those go in ANCHORS) or behavioral predictions (those go in PREDICTIONS)
- ONE CLAIM PER SENTENCE. Never join independent observations with ", and" or "; [new topic]". If two facts are causally related, explain the relationship explicitly. If they are not related, they belong in separate sentences. BAD: "They believe X fails due to Y, and value Z-led deployment." GOOD: "They believe X fails due to Y. This shapes their preference for Z-led deployment — fixing infrastructure before adding features."

Do NOT generate gap analysis questions. Every communication preference must be resolved into a directive based on the available facts. If the facts don't support a specific directive, omit it — do not leave open questions.

INCOMPLETENESS: These directives are derived from available conversation data, which is inherently incomplete. If a context mode has thin factual support, keep it brief rather than padding with generic advice. If domain coverage is uneven (e.g., heavy trading data, sparse personal data), compress the over-represented domain to behavioral essence and acknowledge sparse domains with what you have rather than over-inferring. The honest posture is "here is what we know" not "here is the complete picture."

PROVENANCE — For each major section or context mode, include a provenance line citing the input facts it draws from:
  provenance: [F-xxx, F-yyy, ...]
Use the [F-xxx] IDs provided in the input facts. Only cite facts that directly support the claim.

LEXICON IDS — Assign each context mode a stable identifier: C1, C2, C3, etc. Use this ID as a prefix:
  **C1. [CONTEXT NAME FROM INPUT DATA]**
  ...
  provenance: [F-301, F-455]
Use M1, M2, M3 for meta sections (COMMUNICATION_APPROACH, NARRATIVE_ORIENTATION, ESSENTIAL_CONTEXT).

{data_profile}

INPUT — Identity-tier facts by type (each tagged with [F-xxx] for provenance):

BIOGRAPHICAL:
{biographical}

BEHAVIORAL:
{behavioral}

POSITIONAL:
{positional}

PREFERENCE:
{preference}

Write the injectable block now. No preamble, no explanation, no questions — just the block text."""

PREDICTIONS_PROMPT = """You are authoring the BEHAVIORAL PREDICTIONS layer of a personal identity brief.

CRITICAL: The audience is the intelligence and understanding an AI needs to take on to communicate naturally with this person. Every sentence must shape that understanding. Each prediction should make the AI *feel* how to respond differently in that situation — not give it a checklist. If a prediction produces the same "provide structured frameworks" response as every other prediction, it has failed. Each pattern demands a unique response.

These are behavioral predictions — recurring patterns observed across conversations. Each names a GENERAL pattern (not domain-specific), how to detect it across specific domains, and what to do when it's active.

For each prediction, use this format:
PATTERN NAME: When [trigger situation] -> [characteristic response]
Detection: [how this manifests across MULTIPLE domains — must include at least 2 different life areas per pattern, e.g. professional AND personal, or trading AND relationship, etc.]
Directive: [what the AI should do when this pattern is active — specific, actionable, output-shaping]
False positive warning: [when this pattern might APPEAR active but isn't — to prevent over-application by the AI]

Rules:
- Patterns must be GENERAL behavioral patterns, not domain-specific ones
- Detection examples MUST span multiple domains. If a pattern only shows up in one domain, it belongs in a domain-specific brief, not here. Spread detection examples across: professional, personal, relational, intellectual, financial.
- MULTI-SOURCE GROUNDING: Each prediction must be supported by facts from 2+ source documents. Single-source patterns may appear in detection examples but cannot drive the prediction title or directive. This prevents overgeneralizing a single opinion into a personality trait.
- Directives must be actionable — tell the AI what to output differently, not what to understand
- DIRECTIVE ≠ TRIGGER: The directive must add information beyond the trigger. If the trigger is "names tensions rather than resolving them," the directive CANNOT be "name the tensions and don't resolve them." Instead, describe HOW this person specifically processes tension — do they deflect with humor? Build exhaustive analyses? Escalate to structural diagnosis? Sit with paradox through literary framing? The trigger detects the pattern; the directive tells the AI what this person's SPECIFIC version of that pattern looks like and how to match it.
- If a pattern is time-bounded, mark it [time-bounded]
- Open with a framing sentence explaining what these predictions are and how to use them
- Include patterns for: success responses, setback responses, feedback handling, relationship dynamics, decision-making patterns, self-accountability, learning/revision patterns
- ANTI-ANACHRONISM: Use vocabulary appropriate to the subject's era and domain. Do not project modern professional language (e.g. "optimizes workflows," "leverages synergies," "iterates on feedback loops") onto historical figures or non-professional subjects. If the source facts use plain language, the predictions must too.

ANTI-REDUNDANCY: This layer sits alongside an ANCHORS layer (epistemic axioms). Do NOT restate axioms as predictions. If a pattern IS an axiom (e.g., "seeks coherence" = COHERENCE axiom), do not include it here. Predictions describe WHAT HAPPENS in specific situations, not what the person believes.

Test: "When [X happens], this person characteristically does [Y]" — if Y is a belief or stance rather than an observable behavior, it belongs in ANCHORS, not here.

INCOMPLETENESS: These predictions are derived from available conversation data, which is inherently incomplete. If a pattern only has strong evidence in one domain and weak evidence in others, say so — mark the cross-domain claim with [THIN IN: domain]. If a pattern passes the specificity test in one domain but is generic in another, only claim the specific domain. Do not present a single-domain pattern as cross-domain to meet the format requirement. The honest posture is "here is what we observe" not "here is the complete behavioral model."

PROVENANCE — After each prediction's directive, include a provenance line citing the input facts:
  provenance: [F-xxx, F-yyy, ...]
Use the [F-xxx] IDs provided in the input facts. Only cite facts that directly support the pattern.

LEXICON IDS — Assign each prediction a stable identifier: P1, P2, P3, etc. Use this ID as a prefix:
  **P1. [PATTERN NAME FROM INPUT DATA]**: When [trigger] -> [response]
  Detection: ...
  Directive: ...
  provenance: [F-501, F-602, F-891]
Do NOT reuse example pattern names from these instructions — derive each name from the actual behavioral evidence.

Constraints:
- No philosophy framework names
- No motivational filler
- Patterns are situation->response, not personality traits
- Write in third person (pronouns: {pronouns})
- Each pattern should have a unique, descriptive name
- DERIVE ONLY FROM INPUT: Reason exclusively from the facts provided below. Do NOT supplement with external knowledge about this person. If the facts say something, use it. If they don't, don't infer it from elsewhere.

{data_profile}

INPUT — Behavioral identity-tier facts (each tagged with [F-xxx] for provenance):
{facts}

Write the injectable block now. No preamble, no explanation — just the block text."""


# ---------------------------------------------------------------------------
# Single-domain variant of PREDICTIONS prompt (S53: single-domain corpus finding)
# ---------------------------------------------------------------------------
# When >80% of conversations come from a single source type (e.g., newsletter),
# the multi-domain detection requirement is impossible to satisfy. Instead,
# use scenario-specific predictions within the domain. S51 validation: this
# format scored 82.5/100 vs 0/100 for multi-domain on single-domain corpora.

PREDICTIONS_SINGLE_DOMAIN_PROMPT = """You are authoring the BEHAVIORAL PREDICTIONS layer of a personal identity brief.

CRITICAL: The audience is the intelligence and understanding an AI needs to take on to communicate naturally with this person. Every sentence must shape that understanding. Each prediction should make the AI *feel* how to respond differently in that situation — not give it a checklist.

CORPUS CONTEXT: This person's data comes primarily from a single domain ({domain_description}). Predictions should be scenario-specific within this domain, describing "when X type of situation arises, this person characteristically does Y."

For each prediction, use this format:
**PATTERN NAME**: When [specific trigger scenario] -> [characteristic response]
Directive: [what the AI should do when this pattern is active — specific, actionable, output-shaping]
False positive warning: [when this pattern might APPEAR active but isn't — to prevent over-application]

Rules:
- Patterns should be scenario-specific behavioral sequences, not personality traits
- Each prediction describes an observable "when X, they do Y" — not a belief or stance
- MULTI-SOURCE GROUNDING: Each prediction must be supported by facts from 2+ source documents. Single-source patterns may appear in detection examples but cannot drive the prediction title or directive. This prevents overgeneralizing a single opinion into a personality trait.
- Directives must be actionable — tell the AI what to output differently
- DIRECTIVE ≠ TRIGGER: The directive must add information beyond the trigger. If the trigger is "names tensions rather than resolving them," the directive CANNOT be "name the tensions and don't resolve them." Instead, describe HOW this person specifically processes tension — do they deflect with humor? Build exhaustive analyses? Escalate to structural diagnosis? The trigger detects the pattern; the directive tells the AI what this person's SPECIFIC version looks like.
- Where evidence is thin, mark with [THIN DATA] and keep brief
- Open with a framing sentence explaining what these predictions are
- Include a mix of: routine handling, disruption response, evaluation patterns, communication patterns
- ANTI-ANACHRONISM: Use vocabulary appropriate to the subject's era and domain. Do not project modern professional language (e.g. "optimizes workflows," "leverages synergies," "iterates on feedback loops") onto historical figures or non-professional subjects. If the source facts use plain language, the predictions must too.

ANTI-REDUNDANCY: This layer sits alongside an ANCHORS layer (epistemic axioms). Do NOT restate axioms as predictions. Predictions describe WHAT HAPPENS in specific situations, not what the person believes.

INCOMPLETENESS: These predictions are derived from a single-domain corpus. Acknowledge this constraint. Do not extrapolate to domains without evidence. The honest posture is "within this domain, here is what we observe."

PROVENANCE — After each prediction's directive, include a provenance line citing the input facts:
  provenance: [F-xxx, F-yyy, ...]
Use the [F-xxx] IDs provided in the input facts. Only cite facts that directly support the pattern.

LEXICON IDS — Assign each prediction a stable identifier: P1, P2, P3, etc. Use this ID as a prefix:
  **P1. PATTERN NAME**: When [trigger] -> [response]
  Directive: ...
  provenance: [F-501, F-602]

Constraints:
- No philosophy framework names
- No motivational filler
- Write in third person (pronouns: {pronouns})
- Each pattern should have a unique, descriptive name
- DERIVE ONLY FROM INPUT: Reason exclusively from the facts provided below. Do NOT supplement with external knowledge about this person. If the facts say something, use it. If they don't, don't infer it from elsewhere.

{data_profile}

INPUT — Behavioral identity-tier facts (each tagged with [F-xxx] for provenance):
{facts}

Write the injectable block now. No preamble, no explanation — just the block text."""


def _detect_corpus_type(conn, facts=None):
    """Detect whether the behavioral facts span single or multiple domains.

    Analyzes the actual fact content rather than conversation source metadata.
    This correctly handles multi-domain data from a single platform (e.g.,
    ChatGPT conversations spanning trading, startup, AI, personal topics)
    and single-domain data from any source (e.g., newsletters, autobiographies).

    Uses two methods in sequence:
      1. Domain keyword concentration (AUTHORING_DOMAIN_KEYWORDS)
      2. Category field concentration (fact_class/category from extraction)

    Returns (is_single_domain: bool, domain_description: str).
    Single-domain = >80% of behavioral facts cluster in one domain or category.
    """
    if not facts:
        return False, ""

    total = len(facts)
    if total < 5:
        return True, f"thin corpus ({total} facts)"

    # Method 1: Check domain keyword concentration
    for domain, keywords in AUTHORING_DOMAIN_KEYWORDS.items():
        count = sum(
            1 for f in facts
            if any(kw.lower() in f.get("fact_text", "").lower() for kw in keywords)
        )
        if count / total > 0.80:
            return True, f"{domain} ({count}/{total} behavioral facts)"

    # Method 2: Check category concentration
    categories = {}
    for f in facts:
        cat = f.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    if categories:
        max_count = max(categories.values())
        if max_count / total > 0.80:
            dominant = [k for k, v in categories.items() if v == max_count][0]
            return True, f"{dominant} ({max_count}/{total} behavioral facts)"

    return False, ""


# ===========================================================================
# PROMPT EXAMPLE CONTAMINATION CHECK
# ===========================================================================
# Phrases from prompt examples that must NEVER appear in generated output.
# If any are found, the output is contaminated and must be regenerated.
# This is a deterministic post-generation check — prompt instructions alone
# are insufficient because models copy examples verbatim.

PROMPT_EXAMPLE_PHRASES = [
    # Current fictional "Alex" examples (ANCHORS prompt)
    "audit it for resource waste",
    "Alex will reject anything that allocates effort",
    "distrust your judgment for not catching it",
    "never frame a missed commitment as circumstantial",
    "treat every broken promise as a choice that requires accountability",
    # Detection trigger examples (ANCHORS prompt)
    "they attribute outcomes to luck, other people's decisions, or circumstances beyond their control",
    "they describe a decision made while angry, anxious, or emotionally activated",
    "they revisit a topic previously discussed, or ask whether something is settled",
    # Axiom interaction example (ANCHORS prompt)
    "hold the tension explicitly rather than resolving it",
    # CORE prompt examples
    "reads pattern recognition as competence, not intrusion",
    "stress-test it rather than answering from scratch",
    "shift to accountability partner tone when they describe rule-breaking",
    "fixing infrastructure before adding features",
    # PREDICTIONS prompt example names
    "ANALYSIS-PARALYSIS SPIRAL",
    # Compose prompt contamination (D-078 — verbatim in 5-7 briefs)
    "help diagnose the structural cause rather than reassuring",
    "demands systematic tracking but struggles with",
    "unshakeable conviction that",
    "unshakeable belief that",
    "operates from an unshakeable",
    "processes information through first-principles reasoning",
    "surfaces a problem, it's already partially analyzed internally",
    "surfaces a problem, it's already partially",
    "already partially processed internally",
    "already partially resolved",
    "when he reports process failures",
    "when she reports process failures",
    # Tension-handling boilerplate (D-078 wave 2)
    "acknowledge both sides rather than",
    "acknowledge both as valid rather than forcing",
    "without forcing resolution",
    "rather than forcing resolution",
    "rather than pushing toward resolution",
    "rather than resolving toward either",
    "hold the tension explicitly rather than resolving",
    "surface which axioms are in play",
    "Behavioral prediction data is insufficient for this subject",
    "Behavioral prediction data remains limited",
    "Behavioral prediction data is insufficient for",
    # Legacy examples (from pre-S68 prompt — may persist in cached outputs)
    "flag it before they find it",
    "they will detect it and trust you less for not catching it first",
    "don't validate intentions without examining follow-through",
    "any gap between stated beliefs and actual behavior is a crisis to surface directly, not rationalize",
    # Emotion example (pre-S68)
    "reflect the reaction back as data — name the pattern, locate it in context, treat the signal as input to analysis rather than the conclusion",
]


def check_prompt_contamination(text, layer_name=""):
    """Check generated text for verbatim prompt example phrases.

    Returns:
        List of contaminated phrases found (empty = clean)
    """
    text_lower = text.lower()
    found = []
    for phrase in PROMPT_EXAMPLE_PHRASES:
        if phrase.lower() in text_lower:
            found.append(phrase)
    return found


def check_provenance_coverage(text, citation_provenance, layer_name, input_count=0):
    """Check that citation provenance has meaningful coverage of the generated output.

    Counts significant claims in the output (bold-header sections, paragraphs)
    and compares against citation count. Logs warnings when coverage is low.

    Args:
        text: Generated layer text
        citation_provenance: List of provenance dicts from Citations API (or None)
        layer_name: Layer name (ANCHORS, CORE, PREDICTIONS)
        input_count: Number of input items (axioms, facts, etc.)

    Returns:
        dict with {claims_in_output, citations_returned, coverage_pct, status}
        status is "GOOD", "LOW", or "EMPTY"
    """
    import re as _re

    if citation_provenance is None:
        return {"claims_in_output": 0, "citations_returned": 0, "coverage_pct": 0, "status": "EMPTY"}

    # Count significant claims in output — bold headers (**NAME**) or substantial paragraphs
    bold_headers = len(_re.findall(r'\*\*[A-Z]', text))
    # Count paragraphs > 80 chars (skip short lines, headers, provenance lines)
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 80]
    claims_in_output = max(bold_headers, len(paragraphs), 1)

    citations_returned = len(citation_provenance)
    coverage_pct = (citations_returned / claims_in_output * 100) if claims_in_output > 0 else 0

    if citations_returned == 0:
        status = "EMPTY"
    elif coverage_pct < 30:
        status = "LOW"
    else:
        status = "GOOD"

    # Log the result
    status_icon = {"GOOD": "[OK]", "LOW": "[LOW]", "EMPTY": "[EMPTY]"}[status]
    print(f"  {status_icon} Provenance coverage ({layer_name}): {citations_returned} citations / ~{claims_in_output} claims = {coverage_pct:.0f}%")
    if status == "EMPTY":
        print(f"    Citations API returned 0 results for {layer_name}. This layer synthesizes across facts rather than quoting them.")
        print(f"    Vector-based provenance needed for this layer (see: vector provenance generator in roadmap).")
    elif status == "LOW":
        print(f"    Low citation coverage — most claims in {layer_name} are not grounded to specific facts.")

    return {"claims_in_output": claims_in_output, "citations_returned": citations_returned,
            "coverage_pct": coverage_pct, "status": status}


# ===========================================================================
# GENERATION — API-based layer authoring
# ===========================================================================

def generate_layer(layer_name, prompt_text, max_contamination_retries=3):
    """Generate a layer via Anthropic API (Sonnet by default, per D-046).

    Uses centralized api_client for singleton client, retry, and logging.
    Falls back to plain text prompt when citations are not available.
    Includes deterministic contamination check — rejects output that
    contains verbatim prompt example phrases and regenerates.
    """
    from baselayer.api_client import call_api

    for attempt in range(1 + max_contamination_retries):
        suffix = f" (retry {attempt} — decontaminating)" if attempt > 0 else ""
        print(f"  Generating {layer_name} layer via {LAYER_GENERATION_MODEL}...{suffix}")
        start = time.time()

        messages = [{"role": "user", "content": prompt_text}]
        if attempt > 0:
            # On retry, add explicit decontamination instruction
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": (
                "CONTAMINATION DETECTED: Your output contains phrases copied verbatim from the prompt examples. "
                f"Specifically: {contaminated_phrases}. "
                "Regenerate the ENTIRE layer from scratch using ONLY the input axioms/facts. "
                "Every sentence must be original — derived from the data, not adapted from examples."
            )})

        resp = call_api(
            model=LAYER_GENERATION_MODEL,
            max_tokens=4096,
            messages=messages,
            caller="author_layers.generate",
        )

        text = resp.content[0].text.strip()
        elapsed = time.time() - start
        cost = (resp.usage.input_tokens / 1e6) * 3.00 + (resp.usage.output_tokens / 1e6) * 15.00
        print(f"  Done ({elapsed:.1f}s, {resp.usage.input_tokens} in / {resp.usage.output_tokens} out, ~${cost:.4f})")

        # Deterministic contamination check
        contaminated_phrases = check_prompt_contamination(text, layer_name)
        if not contaminated_phrases:
            return text
        print(f"  WARNING: CONTAMINATION: Found {len(contaminated_phrases)} verbatim prompt phrases in {layer_name} output:")
        for phrase in contaminated_phrases:
            print(f"    - \"{phrase[:80]}...\"" if len(phrase) > 80 else f"    - \"{phrase}\"")

    # Exhausted retries — return with warning
    print(f"  WARNING: {layer_name} still contains prompt contamination after {max_contamination_retries} retry(ies). Manual review needed.")
    return text


# ===========================================================================
# CITATIONS API — structured provenance via Anthropic Citations (S57)
# ===========================================================================
# Instead of asking the LLM to self-cite [F-xxx] IDs (unreliable, ~57%
# faithfulness), we pass facts as document content blocks with
# citations.enabled=True. The API returns structured citation objects
# with content_block_location references that map directly back to facts.
#
# Self-citation [F-xxx] in prompts is kept as fallback when citations
# are unavailable (e.g., non-Anthropic models or API issues).
# ===========================================================================


def _adapt_prompt_for_citations(prompt_text):
    """Adapt an authoring prompt for the Citations API path.

    When using the Citations API, facts are provided as document content blocks
    rather than inline in the prompt. This function:
    1. Replaces PROVENANCE instructions (self-citation is unnecessary — API handles it)
    2. Replaces INPUT sections (facts are in the document, not the prompt)
    3. Keeps all other instructions intact (LEXICON IDS, constraints, style, etc.)

    The LEXICON IDS section is preserved because it controls structural formatting
    (A1/C1/P1 naming), which is independent of provenance method.
    """
    # Replace PROVENANCE section — the Citations API handles this automatically.
    # Match the PROVENANCE paragraph(s) and replace with a brief note.
    # Pattern: "PROVENANCE — ..." through the next double-newline or section header
    prompt_text = re.sub(
        r'PROVENANCE\s*—[^\n]*(?:\n(?!(?:LEXICON|Constraints|INPUT|Write the|Rules|ANTI-REDUNDANCY|INCOMPLETENESS|DOMAIN|Do NOT))[^\n]*)*',
        'PROVENANCE is handled automatically — do not include provenance lines in your output.',
        prompt_text,
    )

    # Replace INPUT sections — facts are in the document blocks
    # Anchors: "INPUT — Axioms (each tagged with [F-xxx] for provenance):\n{facts}"
    prompt_text = re.sub(
        r'INPUT\s*—\s*Axioms\s*\([^)]*\):\s*\n\{facts\}',
        'INPUT — The axioms/facts are provided in the document above. Use all of them.',
        prompt_text,
    )
    # Core: "INPUT — Identity-tier facts by type...\n\nBIOGRAPHICAL:\n{biographical}\n\nBEHAVIORAL:..."
    prompt_text = re.sub(
        r'INPUT\s*—\s*Identity-tier facts by type[^\n]*\n+BIOGRAPHICAL:\s*\n\{biographical\}\s*\n+BEHAVIORAL:\s*\n\{behavioral\}\s*\n+POSITIONAL:\s*\n\{positional\}\s*\n+PREFERENCE:\s*\n\{preference\}',
        'INPUT — The identity-tier facts (biographical, behavioral, positional, preference) are provided in the documents above. Use all of them.',
        prompt_text,
    )
    # Predictions: "INPUT — Behavioral identity-tier facts (each tagged with [F-xxx] for provenance):\n{facts}"
    prompt_text = re.sub(
        r'INPUT\s*—\s*Behavioral identity-tier facts\s*\([^)]*\):\s*\n\{facts\}',
        'INPUT — The behavioral identity-tier facts are provided in the document above. Use all of them.',
        prompt_text,
    )

    return prompt_text


def _detect_subject_name(facts):
    """Detect the most common proper-noun subject from fact texts.

    Looks at the 'subject' field of fact dicts (the triple's subject).
    Returns the most common non-generic subject name, or None.
    """
    from collections import Counter
    subjects = Counter()
    for f in facts:
        subj = f.get("subject", "").strip()
        if subj and subj.lower() not in ("user", "i", "me", "self", "they", "he", "she"):
            subjects[subj] += 1
    if subjects:
        name, count = subjects.most_common(1)[0]
        if count >= 3:  # Must appear in at least 3 facts to be the subject
            return name
    return None


def _anonymize_text(text, subject_name):
    """Replace the subject's name with 'this person' in text.

    Handles full name, first name, and last name variants.
    Preserves case structure for readability.
    """
    if not subject_name or not text:
        return text

    # Replace full name first (e.g. "Theodore Roosevelt" -> "this person")
    text = text.replace(subject_name, "this person")

    # Replace name parts (first/last) only if multi-word name
    parts = subject_name.split()
    if len(parts) >= 2:
        for part in parts:
            if len(part) > 3:  # Skip short parts like "Jr", "de", etc.
                # Only replace standalone occurrences (not within other words)
                text = re.sub(r'\b' + re.escape(part) + r'\b', 'this person', text)

    # Clean up double replacements like "this person this person"
    text = re.sub(r'(this person\s*){2,}', 'this person', text)

    return text


def _anonymize_facts(facts, subject_name=None):
    """Anonymize a list of fact dicts by replacing the subject name.

    Detects subject name automatically if not provided.
    Returns (anonymized_facts, subject_name) — facts are copies, originals unchanged.
    """
    if subject_name is None:
        subject_name = _detect_subject_name(facts)
    if not subject_name:
        return facts, None

    anon_facts = []
    for f in facts:
        f_copy = dict(f)
        if "fact_text" in f_copy:
            f_copy["fact_text"] = _anonymize_text(f_copy["fact_text"], subject_name)
        if "formulation" in f_copy:
            f_copy["formulation"] = _anonymize_text(f_copy["formulation"], subject_name)
        if "subject" in f_copy and f_copy["subject"] == subject_name:
            f_copy["subject"] = "this person"
        anon_facts.append(f_copy)

    return anon_facts, subject_name


def _anonymize_anchor_data(data, subject_name=None):
    """Anonymize anchor data (from epistemic_anchors table or raw facts).

    Returns (anonymized_data, subject_name).
    """
    if subject_name is None:
        subject_name = _detect_subject_name(data.get("facts", []))
    if not subject_name:
        return data, None

    anon_data = dict(data)
    anon_facts = []
    for a in data.get("facts", []):
        a_copy = dict(a)
        if "anchor_text" in a_copy:
            a_copy["anchor_text"] = _anonymize_text(a_copy["anchor_text"], subject_name)
        if "fact_text" in a_copy:
            a_copy["fact_text"] = _anonymize_text(a_copy["fact_text"], subject_name)
        if "formulation" in a_copy:
            a_copy["formulation"] = _anonymize_text(a_copy["formulation"], subject_name)
        anon_facts.append(a_copy)
    anon_data["facts"] = anon_facts

    return anon_data, subject_name


def _format_facts_as_document_blocks(facts, max_items=100):
    """Convert a list of fact dicts into document content blocks for the Citations API.

    Each fact becomes a separate text content block within a document source.
    The block index (0-based) maps directly to the fact in the input list.

    Args:
        facts: List of fact dicts with 'id' and 'fact_text' (or 'formulation') keys.
        max_items: Maximum number of facts to include.

    Returns:
        (content_blocks, index_to_fact_id): Tuple of:
          - content_blocks: List of {'type': 'text', 'text': ...} dicts
          - index_to_fact_id: Dict mapping block index (int) -> fact database id (str)
    """
    content_blocks = []
    index_to_fact_id = {}

    for i, f in enumerate(facts[:max_items]):
        text = f.get("fact_text") or f.get("formulation", "")
        fact_id = str(f.get("id", ""))
        # Truncate extremely long facts to avoid token waste
        block_text = text[:300]
        content_blocks.append({"type": "text", "text": block_text})
        if fact_id:
            index_to_fact_id[i] = fact_id

    return content_blocks, index_to_fact_id


def _format_anchors_as_document_blocks(data):
    """Convert anchors data (epistemic_anchors table or raw facts) into document blocks.

    Anchors from the epistemic_anchors table include status notes and source fact IDs
    as part of the block text. Returns the same (content_blocks, index_to_fact_id) tuple.
    """
    content_blocks = []
    index_to_fact_id = {}

    if data["source"] == "epistemic_anchors_table":
        for i, a in enumerate(data["facts"]):
            parts = [f"Anchor #{a['anchor_number']}: {a['anchor_text']}"]
            if a.get("status") == "paused":
                parts.append("[PAUSED — do not include]")
            elif a.get("status") == "confirmed_flagged":
                parts.append("[FLAGGED — user operates from this but is reluctant to fully endorse. Include it as active but note the contested status.]")
            elif a.get("review_notes"):
                parts.append(f"[Note: {a['review_notes'][:100]}]")
            # Map source fact IDs for provenance — anchor rows don't have a single 'id',
            # but they have source_fact_ids. We store the anchor_number as the index key
            # and will handle source_fact_ids separately in _parse_citation_provenance.
            source_ids = a.get("source_fact_ids", "")
            if source_ids:
                parts.append(f"[source facts: {source_ids}]")
                # Store all source fact IDs for this block index
                index_to_fact_id[i] = source_ids  # Comma-separated string
            content_blocks.append({"type": "text", "text": " ".join(parts)})
    else:
        return _format_facts_as_document_blocks(data["facts"])

    return content_blocks, index_to_fact_id


def _parse_citation_provenance(response, index_maps, layer_name):
    """Extract provenance entries from Citations API response objects.

    Walks through all content blocks in the response, finds citations with
    content_block_location type, and maps block indices back to fact IDs.

    Args:
        response: Anthropic API response object with .content blocks.
        index_maps: List of (document_index, index_to_fact_id) tuples, one per
                    document in the request. For single-document requests, this
                    is [(0, {block_idx: fact_id, ...})].
        layer_name: Layer name for claim_id prefixing.

    Returns:
        List of dicts: [{claim_id, claim_text, fact_ids}] matching the format
        expected by store_provenance().
    """
    # Build a lookup: document_index -> index_to_fact_id
    doc_lookup = {doc_idx: idx_map for doc_idx, idx_map in index_maps}

    # Walk response content blocks, collect citations per text segment
    # The response has multiple text blocks, each potentially with citations.
    # We group citations by the text they annotate.
    claim_counter = 0
    prefix_map = {
        "ANCHORS": "A",
        "CORE": "C",
        "PREDICTIONS": "P",
    }
    prefix = prefix_map.get(layer_name, "X")

    results = []
    for block in response.content:
        if block.type != "text":
            continue
        citations = getattr(block, "citations", None)
        if not citations:
            continue

        # Collect fact IDs from all citations on this text block
        fact_ids = []
        for citation in citations:
            if citation.type != "content_block_location":
                continue
            doc_idx = citation.document_index
            idx_map = doc_lookup.get(doc_idx, {})
            # The citation covers blocks from start_block_index to end_block_index (exclusive).
            # Typically each fact is one block, so start == the fact index.
            for block_idx in range(citation.start_block_index, citation.end_block_index):
                raw_id = idx_map.get(block_idx, "")
                if not raw_id:
                    continue
                # Handle comma-separated source_fact_ids from anchors
                if "," in str(raw_id):
                    for part in str(raw_id).split(","):
                        part = part.strip()
                        if part:
                            fact_ids.append(part)
                else:
                    fact_ids.append(str(raw_id))

        if fact_ids:
            claim_counter += 1
            # Use a short excerpt of the text as claim_text
            claim_text = block.text.strip()[:120]
            results.append({
                "claim_id": f"{prefix}{claim_counter}_cite",
                "claim_text": claim_text,
                "fact_ids": list(dict.fromkeys(fact_ids)),  # dedupe preserving order
            })

    return results


def generate_layer_with_citations(layer_name, prompt_text, document_blocks,
                                   index_to_fact_id, document_title="Identity Facts"):
    """Generate a layer via Anthropic Citations API for structured provenance.

    Sends facts as document content blocks with citations.enabled=True. The API
    returns structured citation objects that map generated text back to specific
    input facts — far more reliable than LLM self-citation.

    Falls back to generate_layer() (plain text, self-citation) if the Citations
    API call fails.

    Args:
        layer_name: Layer name (ANCHORS, CORE, PREDICTIONS).
        prompt_text: The authoring prompt (without facts — facts are in the document).
        document_blocks: List of {'type': 'text', 'text': ...} content blocks.
        index_to_fact_id: Dict mapping block index -> fact database id.
        document_title: Title for the document source.

    Returns:
        (text, citation_provenance): Tuple of generated text and list of provenance
        entries from the Citations API. citation_provenance is None if citations
        failed and we fell back to plain text.
    """
    from baselayer.api_client import get_anthropic_client, logger

    print(f"  Generating {layer_name} layer via {LAYER_GENERATION_MODEL} (Citations API)...")
    start = time.time()

    client = get_anthropic_client()

    # Build the message with document + prompt as separate content blocks
    user_content = [
        {
            "type": "document",
            "source": {
                "type": "content",
                "content": document_blocks,
            },
            "title": document_title,
            "citations": {"enabled": True},
        },
        {
            "type": "text",
            "text": prompt_text,
        },
    ]

    try:
        resp = client.messages.create(
            model=LAYER_GENERATION_MODEL,
            max_tokens=4096,
            temperature=0,
            messages=[{"role": "user", "content": user_content}],
        )

        # Extract text from response (may have multiple text blocks with citations)
        text_parts = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
        text = "".join(text_parts).strip()

        elapsed = time.time() - start
        cost = (resp.usage.input_tokens / 1e6) * 3.00 + (resp.usage.output_tokens / 1e6) * 15.00
        print(f"  Done ({elapsed:.1f}s, {resp.usage.input_tokens} in / {resp.usage.output_tokens} out, ~${cost:.4f})")

        # Parse citation provenance from the response
        index_maps = [(0, index_to_fact_id)]
        citation_provenance = _parse_citation_provenance(resp, index_maps, layer_name)
        citation_count = sum(len(e["fact_ids"]) for e in citation_provenance)
        print(f"  Citations API: {len(citation_provenance)} claims, {citation_count} fact references")

        # Provenance coverage check
        coverage = check_provenance_coverage(text, citation_provenance, layer_name,
                                             input_count=len(document_blocks))

        # Deterministic contamination check
        contaminated = check_prompt_contamination(text, layer_name)
        if contaminated:
            print(f"  WARNING: CONTAMINATION in {layer_name} (citations path): {len(contaminated)} verbatim prompt phrases found")
            for phrase in contaminated:
                print(f"    - \"{phrase[:80]}\"")
            print(f"  Falling back to non-citations path for decontamination retry...")
            return None, None  # Forces fallback to generate_layer() which has retry logic

        return text, citation_provenance

    except Exception as e:
        elapsed = time.time() - start
        print(f"  WARNING: Citations API failed ({elapsed:.1f}s): {e}", file=sys.stderr)
        print(f"  Caller should fall back to self-citation path.", file=sys.stderr)
        return None, None


def generate_layer_with_citations_multi_doc(layer_name, prompt_text, documents):
    """Generate a layer with multiple documents (for CORE layer's fact types).

    Each fact type (biographical, behavioral, etc.) becomes a separate document
    so citation objects reference the correct fact group.

    Args:
        layer_name: Layer name.
        prompt_text: The authoring prompt.
        documents: List of (title, document_blocks, index_to_fact_id) tuples.

    Returns:
        (text, citation_provenance) tuple.
    """
    from baselayer.api_client import get_anthropic_client, logger

    print(f"  Generating {layer_name} layer via {LAYER_GENERATION_MODEL} (Citations API, {len(documents)} documents)...")
    start = time.time()

    client = get_anthropic_client()

    # Build user content with multiple documents + prompt
    # Track actual API document index (skipping empty documents)
    user_content = []
    index_maps = []
    actual_doc_idx = 0
    for title, blocks, idx_map in documents:
        if not blocks:
            continue
        user_content.append({
            "type": "document",
            "source": {
                "type": "content",
                "content": blocks,
            },
            "title": title,
            "citations": {"enabled": True},
        })
        index_maps.append((actual_doc_idx, idx_map))
        actual_doc_idx += 1

    user_content.append({
        "type": "text",
        "text": prompt_text,
    })

    try:
        resp = client.messages.create(
            model=LAYER_GENERATION_MODEL,
            max_tokens=4096,
            temperature=0,
            messages=[{"role": "user", "content": user_content}],
        )

        text_parts = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
        text = "".join(text_parts).strip()

        elapsed = time.time() - start
        cost = (resp.usage.input_tokens / 1e6) * 3.00 + (resp.usage.output_tokens / 1e6) * 15.00
        print(f"  Done ({elapsed:.1f}s, {resp.usage.input_tokens} in / {resp.usage.output_tokens} out, ~${cost:.4f})")

        citation_provenance = _parse_citation_provenance(resp, index_maps, layer_name)
        citation_count = sum(len(e["fact_ids"]) for e in citation_provenance)
        print(f"  Citations API: {len(citation_provenance)} claims, {citation_count} fact references")

        # Provenance coverage check
        total_blocks = sum(len(idx_map) for _, idx_map in index_maps)
        check_provenance_coverage(text, citation_provenance, layer_name,
                                  input_count=total_blocks)

        return text, citation_provenance

    except Exception as e:
        elapsed = time.time() - start
        print(f"  WARNING: Citations API failed ({elapsed:.1f}s): {e}", file=sys.stderr)
        print(f"  Caller should fall back to self-citation path.", file=sys.stderr)
        return None, None


def format_facts_for_prompt(facts, max_items=100, include_ids=True):
    """Format a list of fact dicts as numbered lines for prompt injection.

    When include_ids=True, each line includes the fact's database ID as [F-xxx]
    so the LLM can cite provenance in its output. This enables authoring-time
    provenance tracing (S56).
    """
    lines = []
    for i, f in enumerate(facts[:max_items]):
        text = f.get("fact_text") or f.get("formulation", "")
        fact_id = f.get("id", "")
        if include_ids and fact_id:
            lines.append(f"{i+1}. [F-{fact_id}] {text[:200]}")
        else:
            lines.append(f"{i+1}. {text[:200]}")
    return "\n".join(lines)


def parse_provenance_from_layer(layer_name, layer_text):
    """Parse provenance citations from generated layer text.

    Extracts lexicon IDs (A1, P2, C3, M1) and provenance lines
    (provenance: [F-xxx, F-yyy]) from the LLM output.

    Returns list of dicts: [{claim_id, claim_text, fact_ids}]
    """
    results = []
    lines = layer_text.split("\n")
    current_claim_id = None
    current_claim_text = None

    # Pattern for lexicon IDs: **A1. NAME**, **P2. NAME**, etc.
    id_pattern = re.compile(r'\*\*([APCM]\d+)\.\s+(.+?)\*\*')
    # Pattern for provenance lines: provenance: [F-xxx, F-yyy]
    prov_pattern = re.compile(r'provenance:\s*\[([^\]]+)\]', re.IGNORECASE)

    for line in lines:
        # Check for lexicon ID
        id_match = id_pattern.search(line)
        if id_match:
            current_claim_id = id_match.group(1)
            current_claim_text = id_match.group(2).strip()

        # Check for provenance line
        prov_match = prov_pattern.search(line)
        if prov_match and current_claim_id:
            raw_ids = prov_match.group(1)
            # Parse fact IDs: F-xxx or just xxx
            fact_ids = []
            for part in raw_ids.split(","):
                part = part.strip()
                if part.startswith("F-"):
                    fact_ids.append(part[2:])  # Strip "F-" prefix
                elif part:
                    fact_ids.append(part)

            results.append({
                "claim_id": current_claim_id,
                "claim_text": current_claim_text,
                "fact_ids": fact_ids,
            })

    return results


def store_provenance(conn, layer_name, provenance_entries, layer_version=None,
                     cycle_id=None, link_method="authoring"):
    """Store parsed provenance entries in the database.

    Creates the table if it doesn't exist (for backward compatibility).

    Args:
        conn: SQLite connection.
        layer_name: Layer name (ANCHORS, CORE, PREDICTIONS).
        provenance_entries: List of dicts from parse_provenance_from_layer().
        layer_version: Optional version string (e.g. "v4").
        cycle_id: Optional cycle identifier (e.g. "gen3").
        link_method: How the link was established. 'authoring' = LLM self-citation,
                     'vector' = embedding proximity post-authoring.
    """
    # Ensure table exists (safety net — canonical schema lives in init_database.py)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS layer_claim_provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            layer_name TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            claim_text TEXT,
            fact_id TEXT,
            link_method TEXT DEFAULT 'authoring',
            similarity_score REAL,
            rank_in_claim INTEGER,
            layer_version TEXT,
            cycle_id TEXT,
            created_at REAL,
            FOREIGN KEY (fact_id) REFERENCES memory_facts(id)
        )
    """)

    # Clear previous provenance for this layer+method combination
    # (authoring entries are replaced separately from vector entries)
    conn.execute(
        "DELETE FROM layer_claim_provenance WHERE layer_name = ? AND link_method = ?",
        (layer_name, link_method)
    )

    # Insert new entries
    now = time.time()
    inserted = 0
    for entry in provenance_entries:
        for rank, fact_id in enumerate(entry["fact_ids"], 1):
            conn.execute("""
                INSERT INTO layer_claim_provenance
                (layer_name, claim_id, claim_text, fact_id, link_method,
                 rank_in_claim, layer_version, cycle_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                layer_name,
                entry["claim_id"],
                entry["claim_text"],
                fact_id,
                link_method,
                rank,
                layer_version,
                cycle_id,
                now,
            ))
            inserted += 1

    conn.commit()
    return inserted


def _resolve_inter_axiom_conflicts(conn):
    """Derive inter-axiom conflict guidance from the user's actual anchors.

    Always instructs the LLM to identify tensions from the anchors themselves.
    No hardcoded user-specific content.
    """
    try:
        anchors = conn.execute(
            "SELECT anchor_text FROM epistemic_anchors WHERE status != 'paused' ORDER BY anchor_number"
        ).fetchall()
        if not anchors or len(anchors) < 2:
            return "(No inter-axiom conflicts established yet. Generate the layer without conflict resolution directives.)"
        return "(Identify any tensions between the axioms above. Where two axioms could pull in opposite directions, note how the person would likely resolve that tension based on the evidence.)"
    except Exception as e:
        print(f"  WARNING: inter-axiom conflict resolution failed: {e}", file=sys.stderr)
    return "(No inter-axiom conflicts established yet. Generate the layer without conflict resolution directives.)"


def generate_anchors(conn, use_citations=True):
    """Generate ANCHORS layer. Uses Citations API by default, falls back to self-citation.

    Args:
        conn: SQLite connection.
        use_citations: If True, attempt Citations API. If False, use self-citation only.

    Returns:
        text (str) when use_citations=False or citations fail.
        (text, citation_provenance) tuple when use_citations=True and citations succeed.
        citation_provenance is a list of dicts or None.
    """
    data = retrieve_anchors_facts(conn)
    if data["count"] == 0:
        print("  No anchor facts found (need identity-tier conviction-depth facts).")
        print("  Run: baselayer stats  to check fact distribution.")
        print("  In the simplified pipeline, facts are routed to layers by predicate type (no tiering step needed).")
        return None

    # Anonymize to prevent pre-training pattern matching (S68)
    anon_data, subject_name = _anonymize_anchor_data(data)
    if subject_name:
        print(f"  Anonymized: '{subject_name}' -> 'this person'")

    conflicts = _resolve_inter_axiom_conflicts(conn)
    if subject_name:
        conflicts = _anonymize_text(conflicts, subject_name)
    pronouns = _get_user_pronouns()
    profile = generate_data_profile(conn)

    # Citations API path
    if use_citations:
        doc_blocks, idx_map = _format_anchors_as_document_blocks(anon_data)
        if doc_blocks:
            # Build prompt without inline facts
            cite_prompt = _adapt_prompt_for_citations(ANCHORS_PROMPT)
            cite_prompt = cite_prompt.replace("{conflicts}", conflicts).replace("{pronouns}", pronouns).replace("{data_profile}", profile)
            text, citation_prov = generate_layer_with_citations(
                "ANCHORS", cite_prompt, doc_blocks, idx_map,
                document_title="Epistemic Anchor Facts",
            )
            if text:  # Citations succeeded
                return text, citation_prov
            # Citations failed — fall through to self-citation
            print("  Falling back to self-citation path...")

    # Self-citation fallback path (original behavior)
    if anon_data["source"] == "epistemic_anchors_table":
        lines = []
        for i, a in enumerate(anon_data["facts"]):
            status_note = ""
            if a.get("status") == "paused":
                status_note = " [PAUSED — do not include]"
            elif a.get("status") == "confirmed_flagged":
                notes = a.get("review_notes", "")
                status_note = f" [FLAGGED — user operates from this but is reluctant to fully endorse. Include it as active but note the contested status.]"
            elif a.get("review_notes"):
                status_note = f" [Note: {a['review_notes'][:100]}]"
            # Include source fact IDs for provenance tracing (S56)
            source_ids = a.get("source_fact_ids", "")
            if source_ids:
                status_note += f" [source facts: {source_ids}]"
            lines.append(f"{i+1}. Anchor #{a['anchor_number']}: {a['anchor_text']}{status_note}")
        facts_text = "\n".join(lines)
    else:
        facts_text = format_facts_for_prompt(anon_data["facts"])

    prompt = ANCHORS_PROMPT.replace("{facts}", facts_text).replace("{conflicts}", conflicts).replace("{pronouns}", pronouns).replace("{data_profile}", profile)
    text = generate_layer("ANCHORS", prompt)
    if use_citations:
        return text, None  # Citations were requested but fell through
    return text


def generate_core(conn, use_citations=True):
    """Generate CORE layer. Uses Citations API by default, falls back to self-citation.

    For the CORE layer, facts are grouped by type (biographical, behavioral, positional,
    preference). With the Citations API, each type becomes a separate document so
    citation objects correctly reference the source fact group.
    """
    data = retrieve_core_facts(conn)
    if data["count"] == 0:
        print("  No core facts found (need identity-tier biographical/behavioral facts).")
        print("  Run: baselayer stats  to check fact distribution.")
        print("  In the simplified pipeline, facts are routed to layers by predicate type (no tiering step needed).")
        return None

    # Anonymize to prevent pre-training pattern matching (S68)
    # Detect subject name from all facts, then anonymize per-type
    all_facts = []
    for facts_list in data.get("facts_by_type", {}).values():
        all_facts.extend(facts_list)
    subject_name = _detect_subject_name(all_facts)
    if subject_name:
        print(f"  Anonymized: '{subject_name}' -> 'this person'")

    by_type = {}
    for fact_type, facts_list in data["facts_by_type"].items():
        anon_facts, _ = _anonymize_facts(facts_list, subject_name)
        by_type[fact_type] = anon_facts

    pronouns = _get_user_pronouns()
    profile = generate_data_profile(conn)

    # Citations API path — multiple documents (one per fact type)
    if use_citations:
        documents = []
        for fact_type in ["biographical", "behavioral", "positional", "preference"]:
            facts = by_type.get(fact_type, [])
            if facts:
                blocks, idx_map = _format_facts_as_document_blocks(facts)
                documents.append((f"{fact_type.title()} Facts", blocks, idx_map))

        if documents:
            cite_prompt = _adapt_prompt_for_citations(CORE_PROMPT)
            cite_prompt = cite_prompt.replace("{pronouns}", pronouns).replace("{data_profile}", profile)
            text, citation_prov = generate_layer_with_citations_multi_doc(
                "CORE", cite_prompt, documents,
            )
            if text:  # Citations succeeded
                return text, citation_prov
            # Citations failed — fall through to self-citation
            print("  Falling back to self-citation path...")

    # Self-citation fallback path (original behavior)
    prompt = CORE_PROMPT.replace(
        "{biographical}", format_facts_for_prompt(by_type.get("biographical", []))
    ).replace(
        "{behavioral}", format_facts_for_prompt(by_type.get("behavioral", []))
    ).replace(
        "{positional}", format_facts_for_prompt(by_type.get("positional", []))
    ).replace(
        "{preference}", format_facts_for_prompt(by_type.get("preference", []))
    ).replace("{pronouns}", pronouns).replace("{data_profile}", profile)
    text = generate_layer("CORE", prompt)
    if use_citations:
        return text, None
    return text


def generate_predictions(conn, use_citations=True):
    """Generate PREDICTIONS layer. Uses Citations API by default, falls back to self-citation."""
    data = retrieve_predictions_facts(conn)
    if data["count"] == 0:
        print("  No prediction facts found (need identity-tier behavioral facts).")
        print("  This is normal for thin datasets — ANCHORS and CORE may be sufficient.")
        return None

    # Anonymize to prevent pre-training pattern matching (S68)
    anon_facts, subject_name = _anonymize_facts(data["facts"])
    if subject_name:
        print(f"  Anonymized: '{subject_name}' -> 'this person'")

    pronouns = _get_user_pronouns()
    profile = generate_data_profile(conn)

    # S53/S67: Detect single-domain corpus from fact content (not source metadata)
    is_single_domain, domain_desc = _detect_corpus_type(conn, facts=data["facts"])

    # Citations API path
    if use_citations:
        doc_blocks, idx_map = _format_facts_as_document_blocks(anon_facts)
        if doc_blocks:
            if is_single_domain:
                print(f"  Single-domain corpus detected: {domain_desc}")
                print(f"  Using scenario-specific predictions prompt (S53 fix)")
                cite_prompt = _adapt_prompt_for_citations(PREDICTIONS_SINGLE_DOMAIN_PROMPT)
                cite_prompt = cite_prompt.replace("{domain_description}", domain_desc).replace("{pronouns}", pronouns).replace("{data_profile}", profile)
            else:
                cite_prompt = _adapt_prompt_for_citations(PREDICTIONS_PROMPT)
                cite_prompt = cite_prompt.replace("{pronouns}", pronouns).replace("{data_profile}", profile)

            text, citation_prov = generate_layer_with_citations(
                "PREDICTIONS", cite_prompt, doc_blocks, idx_map,
                document_title="Behavioral Identity Facts",
            )
            if text:  # Citations succeeded
                return text, citation_prov
            # Citations failed — fall through to self-citation
            print("  Falling back to self-citation path...")

    # Self-citation fallback path (original behavior)
    facts_text = format_facts_for_prompt(anon_facts)
    if is_single_domain:
        print(f"  Single-domain corpus detected: {domain_desc}")
        print(f"  Using scenario-specific predictions prompt (S53 fix)")
        prompt = PREDICTIONS_SINGLE_DOMAIN_PROMPT.replace(
            "{facts}", facts_text
        ).replace("{domain_description}", domain_desc).replace("{pronouns}", pronouns).replace("{data_profile}", profile)
    else:
        prompt = PREDICTIONS_PROMPT.replace("{facts}", facts_text).replace("{pronouns}", pronouns).replace("{data_profile}", profile)
    text = generate_layer("PREDICTIONS", prompt)
    if use_citations:
        return text, None
    return text


# ===========================================================================
# FILE I/O — layer storage and reading
# ===========================================================================

def _get_next_version(layer_name):
    """Determine next version number for a layer from history directory.

    Versioning scheme (D-053):
      - Authoring cycle = vN (v1, v2, v3...) — new cycle when user re-runs author
      - Generation within cycle = genM or regenM — iteration within one cycle
      - History file: {layer}_v{N}_{gen|regen}{M}_{timestamp}.md
    """
    history_dir = IDENTITY_LAYERS_DIR / "history"
    if not history_dir.exists():
        return 1, 1  # First ever generation: v1, gen1

    import glob
    prefix = layer_name.lower()
    existing = sorted(history_dir.glob(f"{prefix}_v*_*.md"))

    if not existing:
        return 1, 1

    # Find highest version number
    max_version = 0
    max_gen = 0
    for f in existing:
        name = f.stem  # e.g. "anchors_v2_gen3_20260225_154500"
        parts = name.split("_")
        for part in parts:
            if part.startswith("v") and part[1:].isdigit():
                v = int(part[1:])
                if v > max_version:
                    max_version = v
                    max_gen = 0  # Reset gen counter for new version
            if part.startswith("gen") and part[3:].isdigit():
                g = int(part[3:])
                max_gen = max(max_gen, g)
            if part.startswith("regen") and part[5:].isdigit():
                g = int(part[5:])
                max_gen = max(max_gen, g)

    return max(max_version, 1), max_gen + 1


def store_layer(layer_name, text, file_path, metadata_lines=None, is_regen=False,
                citation_provenance=None):
    """
    Store a generated layer as a markdown file.
    D-053: Also saves a versioned copy to history/ for identity evolution tracking.
    S56: Also parses and stores provenance citations from the generated text.
    S57: When citation_provenance is provided (from Citations API), uses that
         instead of parsing self-citations from text. Both methods stored with
         their respective link_method tags.

    Args:
        layer_name: Layer name (ANCHORS, CORE, PREDICTIONS).
        text: Generated layer text.
        file_path: Path to write the deployed layer file.
        metadata_lines: Optional list of metadata strings for the file header.
        is_regen: Whether this is a regeneration (affects version labeling).
        citation_provenance: Optional list of provenance dicts from Citations API.
            When provided, stored with link_method='citation_api'. Text-based
            self-citation parsing is still attempted as a secondary source.

    Format:
      # LAYER_NAME Layer vN — Description
      # metadata lines...
      ---
      ## Injectable Block
      [text]
    """
    IDENTITY_LAYERS_DIR.mkdir(parents=True, exist_ok=True)

    descriptions = {
        "ANCHORS": "Epistemic Axioms",
        "CORE": "Communication & Operating Guide",
        "PREDICTIONS": "Behavioral Predictions",
    }

    version, gen_num = _get_next_version(layer_name)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    timestamp_file = datetime.now().strftime('%Y%m%d_%H%M%S')
    gen_label = f"regen{gen_num}" if is_regen else f"gen{gen_num}"

    # S98 Phase 7: YAML frontmatter (machine-parseable) replaces comment header
    import re
    # Count items in the generated text
    item_pattern = {"ANCHORS": r'\*\*A\d+', "CORE": r'\*\*[MC]\d+', "PREDICTIONS": r'\*\*P\d+'}
    item_count = len(re.findall(item_pattern.get(layer_name, r'\*\*[A-Z]\d+'), text))

    provenance_method = "citation_api" if citation_provenance is not None else "self_citation"
    input_info = ""
    if metadata_lines:
        for m in metadata_lines:
            if "Input:" in m or "input:" in m.lower():
                input_info = m.split(":", 1)[-1].strip()
                break

    frontmatter_lines = [
        "---",
        f"layer: {layer_name.lower()}",
        f"description: {descriptions.get(layer_name, '')}",
        f"generated: {timestamp}",
        f"version: v{version} {gen_label}",
        f"model: {LAYER_GENERATION_MODEL}",
        f"provenance: {provenance_method}",
        f"item_count: {item_count}",
    ]
    if input_info:
        frontmatter_lines.append(f"input: {input_info}")
    frontmatter_lines.append("---")

    content = "\n".join(frontmatter_lines) + "\n\n## Injectable Block\n\n" + text + "\n"

    # Write deployed version
    file_path.write_text(content, encoding="utf-8")
    print(f"  Stored: {file_path} (v{version} {gen_label})")

    # D-053: Write versioned copy to history/
    history_dir = IDENTITY_LAYERS_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"{layer_name.lower()}_v{version}_{gen_label}_{timestamp_file}.md"
    history_file.write_text(content, encoding="utf-8")
    print(f"  History: {history_file}")

    # S57: Store Citation API provenance (primary, structured)
    if citation_provenance:
        try:
            with contextlib.closing(get_db()) as conn:
                inserted = store_provenance(
                    conn, layer_name, citation_provenance,
                    layer_version=f"v{version}",
                    cycle_id=f"{gen_label}",
                    link_method="citation_api",
                )
                print(f"  Provenance (citation_api): {len(citation_provenance)} claims, {inserted} fact links stored")
        except Exception as e:
            print(f"  WARNING: Citation API provenance storage failed: {e}", file=sys.stderr)

    # S56: Parse and store self-citation provenance (fallback/supplementary)
    provenance_entries = parse_provenance_from_layer(layer_name, text)
    if provenance_entries:
        try:
            with contextlib.closing(get_db()) as conn:
                inserted = store_provenance(
                    conn, layer_name, provenance_entries,
                    layer_version=f"v{version}",
                    cycle_id=f"{gen_label}",
                    link_method="authoring",
                )
                print(f"  Provenance (authoring): {len(provenance_entries)} claims, {inserted} fact links stored")
        except Exception as e:
            print(f"  WARNING: Authoring provenance storage failed: {e}", file=sys.stderr)

    # S68: Auto-generate vector provenance when citation_api returns empty.
    # ANCHORS/PREDICTIONS synthesize across facts (don't quote), so citation_api
    # returns 0 results. Vector provenance fills that gap by embedding claims
    # and finding the closest facts in ChromaDB.
    has_citation_provenance = bool(citation_provenance)
    if not has_citation_provenance:
        try:
            from baselayer.verify_provenance import generate_vector_provenance
            print(f"  No citation_api provenance — generating vector provenance for {layer_name}...")
            vector_results = generate_vector_provenance(layer_name)
            if not vector_results:
                print(f"  WARNING: Vector provenance also empty for {layer_name}. Check ChromaDB embeddings.")
        except Exception as e:
            print(f"  WARNING: Vector provenance generation failed: {e}", file=sys.stderr)

    return file_path


def read_injectable_block(file_path):
    """
    Read the injectable block from a layer file.

    Returns the text below '## Injectable Block', stripping gap analysis
    comment lines (# lines) that are metadata, not injectable content.
    """
    if not file_path.exists():
        return None

    content = file_path.read_text(encoding="utf-8")

    # Find the injectable block marker
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx < 0:
        # Try just reading everything below ---
        sep_idx = content.find("\n---\n")
        if sep_idx >= 0:
            return content[sep_idx + 5:].strip()
        return content.strip()

    # Return everything after the marker, stripping gap analysis comments
    block_start = idx + len(marker)
    block = content[block_start:].strip()

    # Strip comment lines (# ...) — these are gap analysis metadata, not injectable content
    lines = block.split("\n")
    injectable_lines = [line for line in lines if not line.strip().startswith("# ")]
    return "\n".join(injectable_lines).strip()


def read_all_layers():
    """Read all three injectable blocks. Returns dict with layer contents."""
    return {
        "anchors": read_injectable_block(ANCHORS_LAYER_FILE),
        "core": read_injectable_block(CORE_LAYER_FILE),
        "predictions": read_injectable_block(PREDICTIONS_LAYER_FILE),
    }


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Three-Layer Identity Block Authoring Pipeline (D-043)"
    )
    parser.add_argument("--retrieve", type=str, metavar="LAYER",
                        choices=["anchors", "core", "predictions", "all"],
                        help="Retrieve and display facts for a layer")
    parser.add_argument("--generate", type=str, metavar="LAYER",
                        choices=["anchors", "core", "predictions", "all"],
                        help="Generate a layer via API")
    parser.add_argument("--show", type=str, metavar="LAYER",
                        choices=["anchors", "core", "predictions", "all"],
                        help="Show current injectable block for a layer")
    parser.add_argument("--brief", action="store_true",
                        help="Show assembled three-layer identity brief")
    parser.add_argument("--no-citations", action="store_true",
                        help="Disable Citations API — use self-citation [F-xxx] fallback only")
    parser.add_argument("--store", type=str, nargs=2, metavar=("LAYER", "FILE"),
                        help="Store a manually authored layer from a text file")
    args = parser.parse_args()

    if args.retrieve:
        with contextlib.closing(get_db()) as conn:
            layers = [args.retrieve] if args.retrieve != "all" else ["anchors", "core", "predictions"]
            for layer in layers:
                if layer == "anchors":
                    display_anchors(retrieve_anchors_facts(conn))
                elif layer == "core":
                    display_core(retrieve_core_facts(conn))
                elif layer == "predictions":
                    display_predictions(retrieve_predictions_facts(conn))
        return

    if args.generate:
        # S98 gate: block if extraction incomplete
        with contextlib.closing(get_db()) as _gate_conn:
            total_convs = _gate_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            extracted = _gate_conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
            if total_convs > 0 and extracted < total_convs:
                pct = extracted / total_convs * 100
                print(f"\nError: Extraction incomplete — {extracted}/{total_convs} ({pct:.0f}%).")
                print(f"Finish extraction before authoring. Set BASELAYER_SKIP_EXTRACTION_GATE=1 to override.")
                if not os.environ.get("BASELAYER_SKIP_EXTRACTION_GATE"):
                    sys.exit(1)

        with contextlib.closing(get_db()) as conn:
            layers = [args.generate] if args.generate != "all" else ["anchors", "core", "predictions"]
            use_citations = not getattr(args, 'no_citations', False)

            generated_texts = {}

            for layer in layers:
                print(f"\n{'='*60}")
                print(f"  Generating {layer.upper()} layer")
                print(f"{'='*60}")

                if layer == "anchors":
                    data = retrieve_anchors_facts(conn)
                    result = generate_anchors(conn, use_citations=use_citations)
                    text, cite_prov = result if isinstance(result, tuple) else (result, None)
                    if text:
                        generated_texts[layer] = text
                        store_layer("ANCHORS", text, ANCHORS_LAYER_FILE,
                                    [f"Input: {data['count']} {data['source']}"],
                                    citation_provenance=cite_prov)
                elif layer == "core":
                    data = retrieve_core_facts(conn)
                    result = generate_core(conn, use_citations=use_citations)
                    text, cite_prov = result if isinstance(result, tuple) else (result, None)
                    if text:
                        generated_texts[layer] = text
                        store_layer("CORE", text, CORE_LAYER_FILE,
                                    [f"Input: {data['count']} identity-tier facts"],
                                    citation_provenance=cite_prov)
                elif layer == "predictions":
                    data = retrieve_predictions_facts(conn)
                    result = generate_predictions(conn, use_citations=use_citations)
                    text, cite_prov = result if isinstance(result, tuple) else (result, None)
                    if text:
                        generated_texts[layer] = text
                        store_layer("PREDICTIONS", text, PREDICTIONS_LAYER_FILE,
                                    [f"Input: {data['count']} behavioral identity-tier facts"],
                                    citation_provenance=cite_prov)
        return

    if args.show:
        layers_to_show = [args.show] if args.show != "all" else ["anchors", "core", "predictions"]
        all_layers = read_all_layers()

        for layer in layers_to_show:
            text = all_layers.get(layer)
            if text:
                tokens = len(text) // 4
                print(f"\n--- {layer.upper()} (~{tokens} tokens) ---")
                print(text)
                print(f"--- END {layer.upper()} ---\n")
            else:
                file_map = {"anchors": ANCHORS_LAYER_FILE, "core": CORE_LAYER_FILE,
                            "predictions": PREDICTIONS_LAYER_FILE}
                print(f"\n  {layer.upper()}: not found at {file_map[layer]}")

        if args.show == "all":
            total_tokens = sum(len(t) // 4 for t in all_layers.values() if t)
            print(f"  Total: ~{total_tokens} tokens across {sum(1 for t in all_layers.values() if t)} layers")
        return

    if args.brief:
        all_layers = read_all_layers()
        parts = []

        if all_layers["anchors"]:
            parts.append("<epistemic_anchors>")
            parts.append(all_layers["anchors"])
            parts.append("</epistemic_anchors>")
            parts.append("")

        if all_layers["core"]:
            parts.append("<individual_overview>")
            parts.append(all_layers["core"])
            parts.append("</individual_overview>")
            parts.append("")

        if all_layers["predictions"]:
            parts.append("<behavioral_predictions>")
            parts.append(all_layers["predictions"])
            parts.append("</behavioral_predictions>")

        brief = "\n".join(parts)
        tokens = len(brief) // 4
        print(f"\n--- THREE-LAYER IDENTITY BRIEF (~{tokens} tokens) ---\n")
        print(brief)
        print(f"\n--- END ---")
        return

    if args.store:
        layer_name, file_path = args.store
        layer_name = layer_name.lower()
        if layer_name not in ("anchors", "core", "predictions"):
            print(f"ERROR: Invalid layer name '{layer_name}'. Use: anchors, core, predictions")
            return

        source = Path(file_path)
        if not source.exists():
            print(f"ERROR: File not found: {source}")
            return

        text = source.read_text(encoding="utf-8").strip()
        file_map = {
            "anchors": ANCHORS_LAYER_FILE,
            "core": CORE_LAYER_FILE,
            "predictions": PREDICTIONS_LAYER_FILE,
        }
        store_layer(layer_name.upper(), text, file_map[layer_name],
                     ["Manually authored, stored via --store"])
        return

    parser.print_help()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
