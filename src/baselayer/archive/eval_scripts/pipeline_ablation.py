"""
Pipeline Step Ablation Study — Which of 14 Steps Are Load-Bearing?
==================================================================
Tests 14 conditions (C0-C13) on Franklin to determine which pipeline
steps actually improve brief quality vs which are ceremonial.

Subject: Franklin (212 active facts, 135 identity-tier)
Cost: ~$16-20 total
Time: ~1-2 hours

Metrics:
  M1: COLLECTIVE SCORE — Opus 4-persona review (0-100)
  M2: BLIND PAIRWISE — A/B comparison vs C0 baseline (after all conditions)
  M3: PATTERN COVERAGE — mechanical count of behavioral patterns
  M4: BRIEF DIAGNOSTICS — char count, token count, section count, structure

Conditions:
  C0:  Full pipeline (baseline)
  C1:  No Collective review
  C2:  No contradictions/consolidation
  C3:  No scoring
  C4:  No anchors step
  C5:  No tiering (all facts = identity)
  C6:  No classification
  C7:  No enrichment block (raw facts → author → compose)
  C8:  Minimal: EXTRACT → COMPOSE (no author layers)
  C9:  + CLASSIFY + TIER → COMPOSE (no author layers)
  C10: + EMBED + SCORE → COMPOSE (no author layers)
  C11: + AUTHOR LAYERS (no review) → COMPOSE
  C12: Direct fact injection (identity facts → Opus, no author)
  C13: Single-layer compose (one combined layer, not 3)
"""

import sys
import os
import json
import time
import shutil
import sqlite3
import re
import tempfile
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Force unbuffered output for background execution
import functools
print = functools.partial(print, flush=True)

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from api_client import call_api

_HOME = str(Path.home() / "Anthropic")
FRANKLIN_ROOT = os.path.join(_HOME, "subjects", "franklin_memory")
FRANKLIN_DB = os.path.join(FRANKLIN_ROOT, "data", "database", "memory.db")
FRANKLIN_BRIEF = os.path.join(FRANKLIN_ROOT, "data", "identity_layers", "brief_v4.md")
FRANKLIN_ANCHORS = os.path.join(FRANKLIN_ROOT, "data", "identity_layers", "anchors_v4.md")
FRANKLIN_CORE = os.path.join(FRANKLIN_ROOT, "data", "identity_layers", "core_v4.md")
FRANKLIN_PREDICTIONS = os.path.join(FRANKLIN_ROOT, "data", "identity_layers", "predictions_v4.md")

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs", "eval", "ablation")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Track costs
TOTAL_COST = 0.0

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ============================================================
# DATABASE HELPERS
# ============================================================

def copy_db(suffix=""):
    """Copy Franklin's DB to a temp location. Returns path."""
    tmp = os.path.join(OUTPUT_DIR, f"franklin_temp{suffix}.db")
    shutil.copy2(FRANKLIN_DB, tmp)
    # Also copy WAL/SHM files if they exist
    for ext in ["-wal", "-shm"]:
        src = FRANKLIN_DB + ext
        if os.path.exists(src):
            shutil.copy2(src, tmp + ext)
    return tmp

def get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Use DELETE journal mode (not WAL) for temp DBs to avoid Windows locking
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn

def cleanup_db(db_path):
    """Safely remove temp DB files."""
    for ext in ["", "-wal", "-shm"]:
        p = db_path + ext
        try:
            if os.path.exists(p):
                os.remove(p)
        except PermissionError:
            pass  # Windows file locking — leave for manual cleanup


# ============================================================
# FACT RETRIEVAL
# ============================================================

def get_all_active_facts(conn):
    """Get all active (non-superseded) facts."""
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, commitment_depth,
               predicate, object_text, subject, recurrence_count, category, scope
        FROM memory_facts
        WHERE superseded_by IS NULL
        ORDER BY recurrence_count DESC
    """).fetchall()
    return [dict(r) for r in rows]

def get_identity_facts(conn):
    """Get identity-tier active facts."""
    rows = conn.execute("""
        SELECT id, fact_text, fact_type, knowledge_tier, commitment_depth,
               predicate, object_text, subject, recurrence_count, category, scope
        FROM memory_facts
        WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        ORDER BY recurrence_count DESC
    """).fetchall()
    return [dict(r) for r in rows]

def format_facts_for_compose(facts):
    """Format facts for direct injection into compose prompt."""
    lines = []
    for f in facts:
        ftype = f.get("fact_type") or "?"
        cat = f.get("category") or "?"
        text = f["fact_text"]
        # Anonymize
        for name in ["Franklin", "Benjamin Franklin", "Ben Franklin"]:
            text = text.replace(name, "this person")
        lines.append(f"- [{cat}/{ftype}] {text}")
    return "\n".join(lines)


# ============================================================
# LAYER READING (for baseline)
# ============================================================

def read_layer_file(path):
    """Read a layer file and extract the injectable block."""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx >= 0:
        return content[idx + len(marker):].strip()
    sep = content.find("\n---\n")
    if sep >= 0:
        return content[sep + 5:].strip()
    return content.strip()

def read_brief_file(path):
    """Read a brief file, stripping metadata header."""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()
    return text.replace("## Injectable Block\n\n", "").replace("## Injectable Block\n", "")


# ============================================================
# BRIEF GENERATION
# ============================================================

COMPOSE_SYSTEM = """You compose behavioral identity briefs from structured inputs about a person.
The brief will be injected into an AI's system prompt so it understands this person.

RULES:
- Every sentence must change how an AI responds. No filler.
- Use he/him pronouns. Refer to subject as "this person" or "he."
- Focus on behavioral patterns, reasoning tendencies, decision-making, failure modes.
- Write in flowing prose paragraphs, not bullet points.
- Open with a 2-3 sentence identity anchor.
- Include characteristic inner tensions and contradictions.
- Close with failure modes and thin-data acknowledgments.
- Do NOT name the person.
- Do NOT reference any pipeline, system, or tools.
- ONLY include information from the provided inputs."""


def compose_from_layers(layer_texts, facts_text, fact_count, condition_name):
    """Compose a brief from 3 layers + facts (standard pipeline path)."""
    global TOTAL_COST

    # Use the full production compose prompt from agent_pipeline
    from agent_pipeline import UNIFIED_BRIEF_COMPOSITION_PROMPT

    prompt = UNIFIED_BRIEF_COMPOSITION_PROMPT.replace(
        "{anchors}", layer_texts.get("anchors", "(no anchors layer)")
    ).replace(
        "{core}", layer_texts.get("core", "(no core layer)")
    ).replace(
        "{predictions}", layer_texts.get("predictions", "(no predictions layer)")
    ).replace(
        "{facts}", facts_text
    ).replace(
        "{fact_count}", str(fact_count)
    )

    try:
        resp = call_api(
            model="claude-opus-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16384, temperature=0,
            caller=f"ablation_{condition_name}_compose",
            timeout=600,
        )
        cost = (resp.usage.input_tokens * 15 + resp.usage.output_tokens * 75) / 1_000_000
        TOTAL_COST += cost
        log(f"  Compose: {len(resp.content[0].text)} chars, ~${cost:.3f}")
        return resp.content[0].text
    except Exception as e:
        log(f"  ERROR compose {condition_name}: {e}")
        return None


def compose_from_facts_only(facts_text, fact_count, condition_name):
    """Compose a brief directly from raw facts (no intermediate layers)."""
    global TOTAL_COST

    prompt = f"""{COMPOSE_SYSTEM}

You have {fact_count} structured facts about a person. Compose a unified behavioral brief directly from these facts.

Structure: ANCHORS (epistemic axioms) -> CORE (communication/operating guide) -> PREDICTIONS (trigger->behavior).
Target: 1500-3000 characters. Dense, specific, actionable.

FACTS:
{facts_text}

Compose the unified brief now. No preamble — just the brief text."""

    try:
        resp = call_api(
            model="claude-opus-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192, temperature=0,
            caller=f"ablation_{condition_name}_direct_compose",
            timeout=600,
        )
        cost = (resp.usage.input_tokens * 15 + resp.usage.output_tokens * 75) / 1_000_000
        TOTAL_COST += cost
        log(f"  Direct compose: {len(resp.content[0].text)} chars, ~${cost:.3f}")
        return resp.content[0].text
    except Exception as e:
        log(f"  ERROR direct compose {condition_name}: {e}")
        return None


def author_layer_from_conn(conn, layer_name, condition_name):
    """Generate a single layer (anchors/core/predictions) from a database connection.
    Calls the production author_layers functions but WITHOUT review."""
    global TOTAL_COST

    # Set MEMORY_SYSTEM_ROOT temporarily for the authoring functions
    old_root = os.environ.get("MEMORY_SYSTEM_ROOT")

    try:
        if layer_name == "anchors":
            from author_layers import generate_anchors
            result = generate_anchors(conn, use_citations=False)
        elif layer_name == "core":
            from author_layers import generate_core
            result = generate_core(conn, use_citations=False)
        elif layer_name == "predictions":
            from author_layers import generate_predictions
            result = generate_predictions(conn, use_citations=False)
        else:
            return None

        # Handle tuple returns (text, citation_provenance)
        if isinstance(result, tuple):
            text = result[0]
        else:
            text = result

        return text

    except Exception as e:
        log(f"  ERROR authoring {layer_name} for {condition_name}: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if old_root:
            os.environ["MEMORY_SYSTEM_ROOT"] = old_root
        elif "MEMORY_SYSTEM_ROOT" in os.environ:
            del os.environ["MEMORY_SYSTEM_ROOT"]


def author_single_combined_layer(conn, condition_name):
    """Generate ONE combined layer instead of 3 separate (for C13)."""
    global TOTAL_COST

    # Get all identity-tier facts
    facts = get_identity_facts(conn)
    facts_text = format_facts_for_compose(facts)

    prompt = f"""You are authoring a SINGLE COMBINED identity layer for a behavioral brief.
This layer replaces the normal 3-layer architecture (ANCHORS + CORE + PREDICTIONS).
Combine all aspects into one cohesive layer.

Use he/him pronouns. Refer to subject as "this person" or "he."
Every sentence must change how an AI responds. No filler.
Do NOT name the person.
Do NOT reference any pipeline or system.
ONLY derive from the input facts below.

Include:
1. Epistemic axioms — what this person reasons FROM (deepest beliefs)
2. Communication & operating guide — how to engage with this person
3. Behavioral predictions — situation triggers and expected responses
4. Failure modes and blind spots
5. Inner tensions and contradictions

INPUT — {len(facts)} identity-tier facts:
{facts_text}

Generate the combined identity layer now. No preamble."""

    try:
        resp = call_api(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096, temperature=0,
            caller=f"ablation_{condition_name}_single_layer",
        )
        cost = (resp.usage.input_tokens * 3 + resp.usage.output_tokens * 15) / 1_000_000
        TOTAL_COST += cost
        log(f"  Single layer: {len(resp.content[0].text)} chars, ~${cost:.3f}")
        return resp.content[0].text
    except Exception as e:
        log(f"  ERROR single layer {condition_name}: {e}")
        return None


# ============================================================
# MECHANICAL SCORING (M3 + M4)
# ============================================================

def m3_pattern_coverage(brief_text):
    """M3: Count distinct behavioral patterns in the brief."""
    if not brief_text:
        return {"total": 0, "behavioral": 0, "axioms": 0, "predictions": 0,
                "limitations": 0, "tensions": 0}

    text_lower = brief_text.lower()

    # Behavioral patterns: when/if + person reference
    behavioral = len(re.findall(r'\bwhen\b.*\b(he|they|this person)\b', text_lower))
    behavioral += len(re.findall(r'\bif\b.*\b(he|they|this person)\b', text_lower))
    behavioral += len(re.findall(r'\btend[s]?\s+to\b', text_lower))
    behavioral += len(re.findall(r'\bdefault[s]?\s+to\b', text_lower))
    behavioral += len(re.findall(r'\bwill\s+(likely|often|always|typically)\b', text_lower))

    # Axioms/beliefs
    axioms = len(re.findall(r'\bbelieve[s]?\b', text_lower))
    axioms += len(re.findall(r'\baxiom\b', text_lower))
    axioms += len(re.findall(r'\bconviction\b', text_lower))
    axioms += len(re.findall(r'\bprinciple\b', text_lower))

    # Predictions/directives
    predictions = len(re.findall(r'\bexpect\b', text_lower))
    predictions += len(re.findall(r'\bpredict\b', text_lower))
    predictions += len(re.findall(r'\btrigger\b', text_lower))
    predictions += len(re.findall(r'\bfailure\s+mode\b', text_lower))
    predictions += len(re.findall(r'\bblind\s+spot\b', text_lower))

    # Limitations/thin data
    limitations = len(re.findall(r'\bthin\s+data\b', text_lower))
    limitations += len(re.findall(r'\bdata\s+limitation\b', text_lower))
    limitations += len(re.findall(r'\binsufficient\b', text_lower))

    # Tensions/contradictions
    tensions = len(re.findall(r'\btension\b', text_lower))
    tensions += len(re.findall(r'\bcontradict\b', text_lower))
    tensions += len(re.findall(r'\byet\b', text_lower))
    tensions += len(re.findall(r'\bhowever\b', text_lower))
    tensions += len(re.findall(r'\bdespite\b', text_lower))
    tensions += len(re.findall(r'\brather\s+than\b', text_lower))

    total = behavioral + axioms + predictions + limitations + tensions

    return {
        "total": total,
        "behavioral": behavioral,
        "axioms": axioms,
        "predictions": predictions,
        "limitations": limitations,
        "tensions": tensions,
        "density_per_1000_chars": round(total / max(1, len(brief_text)) * 1000, 2),
    }


def m4_brief_diagnostics(brief_text):
    """M4: Structural diagnostics of the brief."""
    if not brief_text:
        return {"char_count": 0, "token_est": 0, "sections": 0,
                "pronoun_consistency": "N/A"}

    char_count = len(brief_text)
    token_est = char_count // 4  # rough estimate

    # Section count (paragraph breaks)
    paragraphs = [p.strip() for p in brief_text.split("\n\n") if p.strip()]
    sections = len(paragraphs)

    # Pronoun consistency
    he_count = len(re.findall(r'\bhe\b', brief_text.lower()))
    she_count = len(re.findall(r'\bshe\b', brief_text.lower()))
    they_count = len(re.findall(r'\bthey\b', brief_text.lower()))
    total_pronouns = he_count + she_count + they_count

    if total_pronouns > 0:
        dominant = max(("he/him", he_count), ("she/her", she_count), ("they/them", they_count), key=lambda x: x[1])
        consistency = round(dominant[1] / total_pronouns * 100, 1)
        pronoun_str = f"{dominant[0]} ({consistency}%)"
    else:
        pronoun_str = "no pronouns"

    # Structural elements
    has_thin_data = "[THIN DATA]" in brief_text or "thin data" in brief_text.lower()
    has_contested = "[CONTESTED]" in brief_text
    has_availability = "additional behavioral patterns" in brief_text.lower() or "availability" in brief_text.lower()
    has_failure_modes = "failure" in brief_text.lower() or "blind spot" in brief_text.lower()

    return {
        "char_count": char_count,
        "token_est": token_est,
        "sections": sections,
        "pronoun_consistency": pronoun_str,
        "has_thin_data": has_thin_data,
        "has_contested": has_contested,
        "has_availability": has_availability,
        "has_failure_modes": has_failure_modes,
    }


# ============================================================
# COLLECTIVE REVIEW SCORING (M1)
# ============================================================

def m1_collective_score(brief_text, condition_name):
    """M1: Run Opus Collective review on the brief. Returns score dict."""
    global TOTAL_COST

    prompt = f"""You are a panel of 4 expert reviewers evaluating a behavioral identity brief.
Each reviewer scores independently. The brief was composed from structured facts about a historical person.

REVIEWERS:
1. COGNITIVE SCIENTIST — Does the brief capture genuine behavioral patterns (not cliches)?
2. NARRATIVE BIOGRAPHER — Is this a faithful, complete portrait?
3. EPISTEMOLOGIST — Are knowledge claims properly grounded? Are limitations acknowledged?
4. PRAGMATIC ENGINEER — Would an AI produce better responses with this brief?

SCORING (0-100 each):
- 90-100: Exceptional. Could not be meaningfully improved.
- 75-89: Strong. Minor issues only.
- 60-74: Adequate. Some gaps or weaknesses.
- 40-59: Weak. Significant problems.
- 0-39: Poor. Fundamental issues.

BRIEF TO EVALUATE:
---
{brief_text}
---

Evaluate the brief. Return ONLY valid JSON (no markdown, no commentary):
{{
  "scores": {{
    "cognitive_scientist": <int>,
    "narrative_biographer": <int>,
    "epistemologist": <int>,
    "pragmatic_engineer": <int>
  }},
  "combined": <int average of 4 scores>,
  "issues": [
    {{"category": "<category>", "description": "<issue>", "severity": "<high|medium|low>"}}
  ],
  "strengths": ["<strength1>", "<strength2>"]
}}"""

    try:
        resp = call_api(
            model="claude-opus-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048, temperature=0,
            caller=f"ablation_{condition_name}_collective",
            timeout=300,
        )
        cost = (resp.usage.input_tokens * 15 + resp.usage.output_tokens * 75) / 1_000_000
        TOTAL_COST += cost

        text = resp.content[0].text.strip()
        # Extract JSON
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        result = json.loads(text)
        combined = result.get("combined", 0)
        scores = result.get("scores", {})
        log(f"  Collective: {combined}/100 (CS:{scores.get('cognitive_scientist','?')} "
            f"NB:{scores.get('narrative_biographer','?')} "
            f"EP:{scores.get('epistemologist','?')} "
            f"PE:{scores.get('pragmatic_engineer','?')}) ~${cost:.3f}")
        return result

    except json.JSONDecodeError as e:
        log(f"  ERROR parsing collective JSON for {condition_name}: {e}")
        return {"combined": 0, "scores": {}, "issues": [], "error": str(e)}
    except Exception as e:
        log(f"  ERROR collective review {condition_name}: {e}")
        return {"combined": 0, "scores": {}, "issues": [], "error": str(e)}


# ============================================================
# PAIRWISE COMPARISON (M2) — run after all conditions
# ============================================================

def m2_pairwise_comparison(baseline_brief, test_brief, condition_name):
    """M2: Blind pairwise comparison vs baseline."""
    global TOTAL_COST

    import random
    # Randomize order
    if random.random() > 0.5:
        brief_a, brief_b = baseline_brief, test_brief
        order = "baseline_first"
    else:
        brief_a, brief_b = test_brief, baseline_brief
        order = "test_first"

    prompt = f"""You are comparing two behavioral identity briefs about the same person.
Both were generated from the same source facts. Your task: determine which brief
more faithfully and usefully captures this person's identity for AI injection.

BRIEF A:
---
{brief_a}
---

BRIEF B:
---
{brief_b}
---

Evaluate on:
1. Behavioral specificity (concrete patterns vs generic descriptions)
2. Faithfulness (claims grounded in patterns, not fabricated)
3. Actionability (would an AI respond differently with this brief?)
4. Completeness (are important patterns present?)
5. Structural quality (readable, well-organized)

Return ONLY valid JSON:
{{
  "winner": "A" or "B" or "TIE",
  "confidence": <1-5 scale>,
  "reasoning": "<1-2 sentences>"
}}"""

    try:
        resp = call_api(
            model="claude-opus-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512, temperature=0,
            caller=f"ablation_{condition_name}_pairwise",
            timeout=300,
        )
        cost = (resp.usage.input_tokens * 15 + resp.usage.output_tokens * 75) / 1_000_000
        TOTAL_COST += cost

        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        result = json.loads(text)

        # Decode winner based on order
        raw_winner = result.get("winner", "TIE")
        if order == "baseline_first":
            decoded = "baseline" if raw_winner == "A" else ("test" if raw_winner == "B" else "tie")
        else:
            decoded = "test" if raw_winner == "A" else ("baseline" if raw_winner == "B" else "tie")

        result["decoded_winner"] = decoded
        result["presentation_order"] = order
        log(f"  Pairwise {condition_name}: {decoded} wins (confidence {result.get('confidence', '?')})")
        return result

    except Exception as e:
        log(f"  ERROR pairwise {condition_name}: {e}")
        return {"decoded_winner": "error", "error": str(e)}


# ============================================================
# CONDITION RUNNERS
# ============================================================

def run_c0_baseline():
    """C0: Full pipeline baseline — use existing production brief."""
    log("C0: Full pipeline (baseline)")
    brief = read_brief_file(FRANKLIN_BRIEF)
    if not brief:
        log("  ERROR: No baseline brief found at " + FRANKLIN_BRIEF)
        return None
    log(f"  Using existing production brief: {len(brief)} chars")
    return brief


def run_c1_no_review():
    """C1: No Collective review — author layers fresh (no review), then compose."""
    log("C1: No Collective review")
    db_path = copy_db("_c1")
    conn = get_conn(db_path)

    try:
        layers = {}
        for name in ["anchors", "core", "predictions"]:
            log(f"  Authoring {name}...")
            text = author_layer_from_conn(conn, name, "c1")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c1")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c2_no_contradictions():
    """C2: No contradictions/consolidation — clear superseded_by, author + compose."""
    log("C2: No contradictions/consolidation")
    db_path = copy_db("_c2")
    conn = get_conn(db_path)

    try:
        # Undo contradiction resolution: restore all superseded facts
        conn.execute("UPDATE memory_facts SET superseded_by = NULL")
        conn.commit()
        restored = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
        log(f"  Restored all facts (now {restored} active, contradictions removed)")

        layers = {}
        for name in ["anchors", "core", "predictions"]:
            text = author_layer_from_conn(conn, name, "c2")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c2")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c3_no_scoring():
    """C3: No scoring — zero out recurrence_count and depth_score."""
    log("C3: No scoring")
    db_path = copy_db("_c3")
    conn = get_conn(db_path)

    try:
        conn.execute("UPDATE memory_facts SET recurrence_count = 0, depth_score = 0")
        conn.commit()
        log("  Zeroed all recurrence_count and depth_score")

        layers = {}
        for name in ["anchors", "core", "predictions"]:
            text = author_layer_from_conn(conn, name, "c3")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c3")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c4_no_anchors():
    """C4: No anchors step — author only CORE + PREDICTIONS, compose with 2 layers."""
    log("C4: No anchors step")
    db_path = copy_db("_c4")
    conn = get_conn(db_path)

    try:
        # Also drop the epistemic_anchors table data so author_layers falls back to raw facts
        try:
            conn.execute("DELETE FROM epistemic_anchors")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Table might not exist

        layers = {"anchors": ""}  # No anchors
        for name in ["core", "predictions"]:
            text = author_layer_from_conn(conn, name, "c4")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c4")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c5_no_tiering():
    """C5: No tiering — promote ALL facts to identity tier."""
    log("C5: No tiering (all facts = identity)")
    db_path = copy_db("_c5")
    conn = get_conn(db_path)

    try:
        conn.execute("UPDATE memory_facts SET knowledge_tier = 'identity' WHERE superseded_by IS NULL")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE knowledge_tier = 'identity' AND superseded_by IS NULL").fetchone()[0]
        log(f"  Promoted all active facts to identity tier ({count} facts)")

        layers = {}
        for name in ["anchors", "core", "predictions"]:
            text = author_layer_from_conn(conn, name, "c5")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c5")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c6_no_classification():
    """C6: No classification — NULL out fact_type and commitment_depth."""
    log("C6: No classification")
    db_path = copy_db("_c6")
    conn = get_conn(db_path)

    try:
        conn.execute("UPDATE memory_facts SET fact_type = NULL, commitment_depth = NULL")
        conn.commit()
        log("  Cleared all fact_type and commitment_depth")

        # With no classification, author_layers grouping won't work well
        # Core expects facts grouped by type — give it all as "unclassified"
        layers = {}
        for name in ["anchors", "core", "predictions"]:
            text = author_layer_from_conn(conn, name, "c6")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c6")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c7_no_enrichment():
    """C7: No enrichment — zero scores, NULL classification, all facts = identity."""
    log("C7: No enrichment block")
    db_path = copy_db("_c7")
    conn = get_conn(db_path)

    try:
        conn.execute("""
            UPDATE memory_facts SET
                recurrence_count = 0,
                depth_score = 0,
                fact_type = NULL,
                commitment_depth = NULL,
                knowledge_tier = 'identity'
            WHERE superseded_by IS NULL
        """)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
        log(f"  Stripped all enrichment: {count} raw facts, all identity-tier")

        layers = {}
        for name in ["anchors", "core", "predictions"]:
            text = author_layer_from_conn(conn, name, "c7")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c7")
        return brief
    finally:
        conn.close()
        cleanup_db(db_path)


def run_c8_minimal():
    """C8: Minimal — EXTRACT → COMPOSE. Raw facts directly to Opus."""
    log("C8: Minimal (EXTRACT -> COMPOSE)")
    conn = get_conn(FRANKLIN_DB)

    try:
        # Use ALL active facts (no tiering, no filtering)
        facts = get_all_active_facts(conn)
        facts_text = format_facts_for_compose(facts)
        log(f"  Raw facts: {len(facts)} (unfiltered)")
        brief = compose_from_facts_only(facts_text, len(facts), "c8")
        return brief
    finally:
        conn.close()


def run_c9_classify_tier():
    """C9: + CLASSIFY + TIER → COMPOSE. Identity-tier facts directly to Opus."""
    log("C9: CLASSIFY + TIER -> COMPOSE")
    conn = get_conn(FRANKLIN_DB)

    try:
        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        log(f"  Identity-tier facts: {len(facts)} (classified + tiered)")
        brief = compose_from_facts_only(facts_text, len(facts), "c9")
        return brief
    finally:
        conn.close()


def run_c10_full_enrich():
    """C10: + EMBED + SCORE → COMPOSE. Fully enriched facts directly to Opus."""
    log("C10: Full enrichment -> COMPOSE (no layers)")
    conn = get_conn(FRANKLIN_DB)

    try:
        facts = get_identity_facts(conn)
        # Sort by recurrence (scoring matters here)
        facts.sort(key=lambda f: f.get("recurrence_count", 0), reverse=True)
        facts_text = format_facts_for_compose(facts)
        log(f"  Enriched identity facts: {len(facts)} (scored, classified, tiered)")
        brief = compose_from_facts_only(facts_text, len(facts), "c10")
        return brief
    finally:
        conn.close()


def run_c11_author_no_review():
    """C11: + AUTHOR LAYERS (no review) → COMPOSE. Standard minus quality control."""
    log("C11: Full enrichment + AUTHOR (no review) -> COMPOSE")
    # This is basically the same as C1 but with the standard DB (no modifications)
    conn = get_conn(FRANKLIN_DB)

    try:
        layers = {}
        for name in ["anchors", "core", "predictions"]:
            log(f"  Authoring {name}...")
            text = author_layer_from_conn(conn, name, "c11")
            layers[name] = text or ""

        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c11")
        return brief
    finally:
        conn.close()


def run_c12_direct_injection():
    """C12: Direct fact injection — identity facts to Opus, skip author layers."""
    log("C12: Direct fact injection (identity facts -> Opus)")
    conn = get_conn(FRANKLIN_DB)

    try:
        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        log(f"  Identity-tier facts: {len(facts)} (same data as C9 but Opus compose)")
        brief = compose_from_facts_only(facts_text, len(facts), "c12")
        return brief
    finally:
        conn.close()


def run_c13_single_layer():
    """C13: Single-layer compose — one combined layer instead of 3."""
    log("C13: Single-layer compose")
    conn = get_conn(FRANKLIN_DB)

    try:
        # Author one combined layer
        combined_layer = author_single_combined_layer(conn, "c13")
        if not combined_layer:
            log("  ERROR: Single layer generation failed")
            return None

        # Compose from the single layer (treat as the only "core" layer)
        layers = {"anchors": "", "core": combined_layer, "predictions": ""}
        facts = get_identity_facts(conn)
        facts_text = format_facts_for_compose(facts)
        brief = compose_from_layers(layers, facts_text, len(facts), "c13")
        return brief
    finally:
        conn.close()


# ============================================================
# MAIN RUNNER
# ============================================================

CONDITION_RUNNERS = [
    ("C0", "Full pipeline (baseline)", run_c0_baseline),
    ("C1", "No Collective review", run_c1_no_review),
    ("C2", "No contradictions/consolidation", run_c2_no_contradictions),
    ("C3", "No scoring", run_c3_no_scoring),
    ("C4", "No anchors step", run_c4_no_anchors),
    ("C5", "No tiering", run_c5_no_tiering),
    ("C6", "No classification", run_c6_no_classification),
    ("C7", "No enrichment block", run_c7_no_enrichment),
    ("C8", "Minimal: EXTRACT -> COMPOSE", run_c8_minimal),
    ("C9", "+ CLASSIFY + TIER -> COMPOSE", run_c9_classify_tier),
    ("C10", "+ EMBED + SCORE -> COMPOSE", run_c10_full_enrich),
    ("C11", "+ AUTHOR (no review) -> COMPOSE", run_c11_author_no_review),
    ("C12", "Direct fact injection", run_c12_direct_injection),
    ("C13", "Single-layer compose", run_c13_single_layer),
]


def main():
    global TOTAL_COST

    log("=" * 70)
    log("PIPELINE ABLATION STUDY — S78")
    log(f"Subject: Franklin | Conditions: {len(CONDITION_RUNNERS)}")
    log(f"Output: {OUTPUT_DIR}")
    log("=" * 70)

    results = {}
    briefs = {}
    start_time = time.time()

    # Phase 1: Generate briefs for all conditions
    log("\n--- PHASE 1: GENERATE BRIEFS ---")
    for cid, desc, runner in CONDITION_RUNNERS:
        log(f"\n{'='*50}")
        condition_start = time.time()
        try:
            brief = runner()
            elapsed = time.time() - condition_start

            if brief:
                briefs[cid] = brief
                # Save brief to file
                brief_path = os.path.join(OUTPUT_DIR, f"{cid}_brief.md")
                with open(brief_path, "w", encoding="utf-8") as f:
                    f.write(f"# {cid}: {desc}\n# Generated: {datetime.now().isoformat()}\n\n{brief}")
                log(f"  Saved: {brief_path}")
                log(f"  {cid} complete in {elapsed:.1f}s")
            else:
                log(f"  {cid} FAILED in {elapsed:.1f}s")
                briefs[cid] = None
        except Exception as e:
            log(f"  {cid} ERROR: {e}")
            import traceback
            traceback.print_exc()
            briefs[cid] = None

    # Phase 2: Score all briefs (M1 + M3 + M4)
    log("\n--- PHASE 2: SCORE BRIEFS ---")
    for cid, desc, _ in CONDITION_RUNNERS:
        brief = briefs.get(cid)
        if not brief:
            results[cid] = {"condition": cid, "description": desc, "status": "FAILED"}
            continue

        log(f"\nScoring {cid}: {desc}")

        # M3: Pattern Coverage
        m3 = m3_pattern_coverage(brief)
        log(f"  M3 patterns: {m3['total']} (behavioral:{m3['behavioral']}, axioms:{m3['axioms']}, "
            f"predictions:{m3['predictions']}, tensions:{m3['tensions']})")

        # M4: Brief Diagnostics
        m4 = m4_brief_diagnostics(brief)
        log(f"  M4 diagnostics: {m4['char_count']} chars, ~{m4['token_est']} tokens, "
            f"{m4['sections']} sections, pronouns: {m4['pronoun_consistency']}")

        # M1: Collective Score (Opus)
        m1 = m1_collective_score(brief, cid)

        results[cid] = {
            "condition": cid,
            "description": desc,
            "status": "OK",
            "m1_collective": m1,
            "m3_patterns": m3,
            "m4_diagnostics": m4,
        }

    # Phase 3: Pairwise comparisons vs C0 baseline
    log("\n--- PHASE 3: PAIRWISE COMPARISONS ---")
    baseline_brief = briefs.get("C0")
    if baseline_brief:
        for cid, desc, _ in CONDITION_RUNNERS:
            if cid == "C0":
                results[cid]["m2_pairwise"] = {"decoded_winner": "baseline (self)", "note": "baseline vs self"}
                continue
            test_brief = briefs.get(cid)
            if not test_brief:
                results[cid]["m2_pairwise"] = {"decoded_winner": "skipped", "note": "no brief generated"}
                continue

            log(f"\nPairwise: C0 vs {cid}")
            m2 = m2_pairwise_comparison(baseline_brief, test_brief, cid)
            results[cid]["m2_pairwise"] = m2
    else:
        log("  ERROR: No baseline brief — skipping pairwise comparisons")

    # Phase 4: Analysis
    log("\n--- PHASE 4: ANALYSIS ---")
    total_elapsed = time.time() - start_time

    # Rank by collective score
    scored = [(cid, r.get("m1_collective", {}).get("combined", 0))
              for cid, r in results.items() if r.get("status") == "OK"]
    scored.sort(key=lambda x: x[1], reverse=True)

    log("\nRANKING BY COLLECTIVE SCORE:")
    log(f"{'Condition':<8} {'Score':>6} {'Chars':>7} {'Patterns':>9} {'vs C0':>12}")
    log("-" * 50)
    c0_score = results.get("C0", {}).get("m1_collective", {}).get("combined", 0)
    for cid, score in scored:
        r = results[cid]
        chars = r.get("m4_diagnostics", {}).get("char_count", 0)
        patterns = r.get("m3_patterns", {}).get("total", 0)
        pairwise = r.get("m2_pairwise", {}).get("decoded_winner", "?")
        delta = score - c0_score
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        log(f"{cid:<8} {score:>6} {chars:>7} {patterns:>9} {delta_str:>6} ({pairwise})")

    # Identify load-bearing vs ceremonial
    log("\nLOAD-BEARING STEPS (removal drops score >5 from baseline):")
    for cid, score in scored:
        if cid == "C0":
            continue
        delta = c0_score - score
        if delta > 5:
            log(f"  {cid}: {results[cid]['description']} (delta: -{delta})")

    log("\nCEREMONIAL STEPS (removal drops score <2 or improves):")
    for cid, score in scored:
        if cid == "C0":
            continue
        delta = c0_score - score
        if delta < 2:
            log(f"  {cid}: {results[cid]['description']} (delta: {'+' if delta < 0 else ''}{-delta})")

    # Minimal viable pipeline
    log("\nMINIMAL VIABLE PIPELINE:")
    for cid, score in scored:
        if cid.startswith("C8") or cid.startswith("C9") or cid.startswith("C10"):
            if score >= c0_score - 5:
                log(f"  {cid} scores within 5 of baseline ({score} vs {c0_score})")
                log(f"  -> {results[cid]['description']}")

    # Save results
    results_path = os.path.join(OUTPUT_DIR, "ablation_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "subject": "Franklin",
            "total_cost": round(TOTAL_COST, 2),
            "total_time_seconds": round(total_elapsed, 1),
            "conditions": results,
            "ranking": [(cid, score) for cid, score in scored],
        }, f, indent=2)
    log(f"\nResults saved: {results_path}")
    log(f"Total cost: ${TOTAL_COST:.2f}")
    log(f"Total time: {total_elapsed/60:.1f} min")
    log("ABLATION STUDY COMPLETE")


if __name__ == "__main__":
    main()
