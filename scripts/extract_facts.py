"""
Step 2: Extract — Fact Extraction Pipeline (Decisions D-005, D-010, D-013)

Implements the AUDN (ADD/UPDATE/DELETE/NOOP) fact lifecycle from Mem0's approach.

For each conversation:
  1. Extract candidate facts using Claude Haiku (Anthropic API, default) or Qwen via Ollama (local)
  2. For each fact, search existing facts by vector similarity (deduplication)
  3. AUDN decision: is this new, an update, a contradiction, or redundant?
  4. Store facts with confidence scores
  5. Link co-occurring facts (D-013: associative retrieval)

Backend: Anthropic Haiku API (default, ~$0.01/conversation, fast).
         Set BASELAYER_EXTRACTION_BACKEND=ollama to use local Qwen via Ollama.

Run: python extract_facts.py                     # Process all conversations
     python extract_facts.py --limit 50          # Process first 50 conversations
     python extract_facts.py --conversation <id>  # Process one conversation
     python extract_facts.py --stats              # Show extraction statistics
"""

import contextlib
import sys
import io
import sqlite3
import json
import time
import uuid
import argparse
import requests
from datetime import datetime

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

# ---------------------------------------------------------------------------
# Shared config — single source of truth (config.py)
# ---------------------------------------------------------------------------
from config import (
    PROJECT_ROOT, DATABASE_FILE, VECTORS_DIR, PROGRESS_FILE,
    EMBEDDING_MODEL, OLLAMA_URL, LLM_MODEL,
    EXTRACTION_BATCH_SIZE as BATCH_SIZE,
    SIMILARITY_THRESHOLD, MAX_RETRIES, MIN_FACT_LENGTH,
    MAX_FACTS_PER_CONVERSATION, MIN_MESSAGES_FOR_EXTRACTION,
    VALID_CATEGORIES, VALID_FACT_CLASSES,
    EXTRACTION_BACKEND, EXTRACTION_API_MODEL,
    SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE,
    CONSTRAINED_PREDICATES,
    EXTRACTION_CAPS,
    get_db,
)


# ---------------------------------------------------------------------------
# JSON Schemas for Ollama (D-010: schema enforcement)
# ---------------------------------------------------------------------------

# D-056 Tier 2: Structured extraction schema with constrained predicates.
# Fields: subject, predicate, object, qualifier, category, temporal, confidence.
# Replaces free-text "fact" field with structured triple (Variant D).
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},       # Who is this about?
                    "predicate": {"type": "string"},     # Constrained verb from CONSTRAINED_PREDICATES
                    "object": {"type": "string"},        # The specific value/entity
                    "qualifier": {"type": "string"},     # Temporal/conditional context
                    "category": {"type": "string"},
                    "temporal": {"type": "string"},      # Current/past/unknown
                    "confidence": {"type": "number"},
                },
                "required": ["subject", "predicate", "object", "category", "confidence"]
            }
        }
    },
    "required": ["facts"]
}

# Fallback schema with relaxed required fields
EXTRACT_SCHEMA_FALLBACK = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "qualifier": {"type": "string"},
                    "category": {"type": "string"},
                    "temporal": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["subject", "predicate", "object", "confidence"]
            }
        }
    },
    "required": ["facts"]
}

# VALID_CATEGORIES imported from config.py


def _ensure_structured_columns(conn):
    """D-056 Tier 2: Add predicate/object_text/qualifier columns if missing.
    Safe to call repeatedly — silently skips if columns already exist."""
    for col in ["predicate", "object_text", "qualifier"]:
        try:
            conn.execute(f"ALTER TABLE memory_facts ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists


def normalize_category(raw: str) -> str:
    """Normalize LLM category output to canonical lowercase singular form."""
    c = raw.strip().lower()
    if c in VALID_CATEGORIES:
        return c
    # Explicit plural-to-singular for known categories only (no blind rstrip)
    _PLURAL_MAP = {
        "preferences": "preference", "relationships": "relationship",
        "interests": "interest", "skills": "skill", "values": "value",
        "habits": "habit", "opinions": "opinion", "goals": "goal",
        "projects": "project",
    }
    if c in _PLURAL_MAP:
        return _PLURAL_MAP[c]
    # Fuzzy fallback for common variants
    mapping = {
        "biographical": "biography", "bio": "biography",
        "like": "preference",
        "work": "project",
        "family": "relationship",
        "hobby": "interest", "hobbies": "interest",
        "ability": "skill",
        "belief": "value",
        "routine": "habit",
        "view": "opinion",
        "aspiration": "goal",
        "negative_trait": "negative_trait", "negative trait": "negative_trait",
        "weakness": "negative_trait", "flaw": "negative_trait",
        "negative": "negative_trait", "trait": "negative_trait",
    }
    return mapping.get(c, mapping.get(raw.strip().lower(), "unknown"))


def normalize_subject(raw: str) -> str:
    """Normalize who a fact is about. Maps variants to canonical form.
    D-022: Entity resolution — distinguish user from user's wife, friend, etc.

    Two layers:
      1. Generic relationship resolution (works for any user)
      2. Per-user entity map from config (ENTITY_MAP) for name->canonical mappings
    """
    if not raw:
        return "user"
    s = raw.strip().lower()

    # --- Generic: user references ---
    if s in ("the user", "user", "me", "i", "myself", "self", "the person", "they",
             "the owner of the company"):
        return "user"
    if s.startswith("the user (") and s.endswith(")"):
        # "the user (Name)" or "the user (CEO)" — check entity map first
        inner = raw[raw.index("(")+1:raw.index(")")].strip()
        if inner.lower() in _get_user_names():
            return "user"
        # Role-based references
        if inner.lower() in ("ceo", "founder", "owner"):
            return "user"
        return "user"
    if s.startswith("the user (through "):
        return "user"

    # --- Check if this is the user by name ---
    if s in _get_user_names() or s.startswith(tuple(n + " " for n in _get_user_names())):
        return "user"

    # --- Per-user entity map ---
    entity_map = _get_entity_map()
    if s in entity_map:
        return entity_map[s]
    # Check if any entity map key is contained in s
    for key, canonical in entity_map.items():
        if key in s:
            return canonical

    # --- Generic: relationship roles ---
    if s in ("wife", "husband", "partner", "spouse", "the user's wife",
             "user's wife", "his wife", "her husband", "their wife",
             "their husband", "the user's partner", "the user's husband"):
        return "spouse"
    if s in ("the user's cat", "the user's pet", "the user's dog",
             "the user's pet (cat)", "the user's cat (male)"):
        return "pet"
    if s in ("the user's cats", "the user's dogs", "the user's pets"):
        return "pets"
    if s in ("the user's company", "the user's startup", "the user's business"):
        return "company"
    if "friend" in s:
        return "friend"
    if s.startswith("colleague") or s.startswith("coworker") or s.startswith("co-worker"):
        if "(" in raw and ")" in raw:
            name = raw[raw.index("(")+1:raw.index(")")].strip()
            return f"colleague:{name}"
        return "colleague"
    if s.startswith("the user's colleague"):
        if "(" in raw and ")" in raw:
            name = raw[raw.index("(")+1:raw.index(")")].strip()
            if name.lower() in _get_user_names():
                return "user"
            return f"colleague:{name}"
        return "colleague"

    # Keep named people as-is
    return raw.strip()


def _get_entity_map():
    """Load per-user entity map. Returns dict mapping lowercase variants to canonical forms.
    Override via ENTITY_MAP in a user-specific config or entity_map.json in data root."""
    if not hasattr(_get_entity_map, "_cache"):
        import json as _json
        entity_file = PROJECT_ROOT / "data" / "entity_map.json"
        if entity_file.exists():
            try:
                raw = _json.loads(entity_file.read_text(encoding="utf-8"))
                # Schema validation: must be a dict with string keys and reasonable values
                if not isinstance(raw, dict):
                    print("WARNING: entity_map.json is not a dict, ignoring", file=sys.stderr)
                    _get_entity_map._cache = {}
                else:
                    validated = {}
                    for k, v in raw.items():
                        if not isinstance(k, str):
                            continue
                        if isinstance(v, str) and len(v) > 1000:
                            print(f"WARNING: entity_map key '{k}' value too long ({len(v)} chars), skipping", file=sys.stderr)
                            continue
                        validated[k.lower()] = v
                    _get_entity_map._cache = validated
            except Exception as e:
                print(f"WARNING: Failed to load entity_map.json: {e}", file=sys.stderr)
                _get_entity_map._cache = {}
        else:
            _get_entity_map._cache = {}
    return _get_entity_map._cache


def _get_user_names():
    """Load the user's known names/aliases for user-reference detection."""
    if not hasattr(_get_user_names, "_cache"):
        import json as _json
        entity_file = PROJECT_ROOT / "data" / "entity_map.json"
        if entity_file.exists():
            try:
                raw = _json.loads(entity_file.read_text(encoding="utf-8"))
                _get_user_names._cache = set()
                if "_user_names" in raw:
                    _get_user_names._cache = {n.lower() for n in raw["_user_names"]}
            except Exception as e:
                print(f"WARNING: Failed to load user names from entity_map.json: {e}", file=sys.stderr)
                _get_user_names._cache = set()
        else:
            _get_user_names._cache = set()
    return _get_user_names._cache


def _get_known_entities_for_prompt():
    """Load known entities from entity_map.json and format them as extraction hints.

    Session 55 (Plan 1): Primes the extraction model with known people/entities
    so it actively looks for relationship facts involving them.
    Returns a formatted string for inclusion in the extraction prompt, or empty
    string if no entity_map is found.
    """
    entity_file = PROJECT_ROOT / "data" / "entity_map.json"
    if not entity_file.exists():
        return ""

    try:
        raw = json.loads(entity_file.read_text(encoding="utf-8"))
    except Exception:
        return ""

    # Build a human-readable list of known entities (skip internal keys)
    entities = []
    for key, value in raw.items():
        if key.startswith("_"):
            continue  # Skip _user_names, _user_pronouns, etc.
        # Format: "Jane (spouse)" from "jane": "spouse:Jane"
        if isinstance(value, str) and ":" in value:
            role, name = value.split(":", 1)
            entities.append(f"{name} ({role})")
        elif isinstance(value, str):
            entities.append(f"{key} ({value})")

    if not entities:
        return ""

    return (
        "\n\nKNOWN ENTITIES in this user's life (look for these and extract relationship facts):\n"
        + ", ".join(entities)
        + "\nIf any of these people are mentioned, extract WHO they are to the user and what the relationship dynamic is."
    )


def _get_extraction_caps(message_count: int, total_chars: int = 0) -> dict:
    """Determine extraction caps based on message count AND total character length.

    Session 55 (Plan 2): Scales extraction limits with conversation length.
    Session 65: Added char-based tiers for long single-message imports
    (autobiographies, chapters). Returns whichever tier gives higher max_facts.

    Args:
        message_count: Number of messages in the conversation.
        total_chars: Total character count across all messages. 0 = skip char lookup.

    Returns:
        dict with "max_facts" and "input_char_budget" keys.
    """
    # Message-based tier lookup
    msg_caps = {"max_facts": MAX_FACTS_PER_CONVERSATION, "input_char_budget": 12000}
    for tier in EXTRACTION_CAPS["tiers"]:
        if tier["min_messages"] <= message_count <= tier["max_messages"]:
            msg_caps = {
                "max_facts": tier["max_facts"],
                "input_char_budget": tier["input_char_budget"],
            }
            break

    # Character-based tier lookup (Session 65)
    if total_chars > 0 and "char_tiers" in EXTRACTION_CAPS:
        for tier in EXTRACTION_CAPS["char_tiers"]:
            if tier["min_chars"] <= total_chars <= tier["max_chars"]:
                if tier["max_facts"] > msg_caps["max_facts"]:
                    return {
                        "max_facts": tier["max_facts"],
                        "input_char_budget": tier["input_char_budget"],
                    }
                break

    return msg_caps


def normalize_intent(raw: str) -> str:
    """Normalize the user's relationship to a fact.
    D-022: Intent detection — 'asked about X' != 'does X'."""
    if not raw:
        return "does"
    i = raw.strip().lower()
    # Active/identity
    if i in ("does", "is", "has", "uses", "owns", "practices", "works", "plays",
             "drives", "trades", "builds", "manages", "active", "currently",
             "identifies", "believes"):
        return "does"
    # Learning/studying
    if i in ("learning", "studying", "training", "developing", "improving",
             "working on", "exploring"):
        return "learning"
    # Curiosity/one-off
    if i in ("curious", "asked about", "wondered", "inquired", "asked",
             "looked into", "researched", "considered", "thinking about"):
        return "curious"
    # Historical/past
    if i in ("historical", "used to", "was", "had", "previously", "formerly",
             "past", "did", "once"):
        return "historical"
    # Default to does (most common case)
    return "does"


def normalize_temporal(raw: str) -> str:
    """Normalize temporal state of a fact.
    D-022: Track whether facts are current or past."""
    if not raw:
        return "unknown"
    t = raw.strip().lower()
    if t in ("current", "present", "active", "now", "ongoing", "still"):
        return "current"
    if t in ("past", "was", "ended", "former", "previous", "historical",
             "no longer", "stopped", "quit"):
        return "past"
    return "unknown"


def normalize_fact_class(raw: str) -> str:
    """Normalize fact class: event (immutable anchor) vs state (mutable, can be contradicted).
    Temporal processing foundation — events never need contradiction checking,
    states are candidates for contradiction detection."""
    if not raw:
        return "unclassified"
    fc = raw.strip().lower()
    if fc in ("event", "events", "historical event", "milestone", "achievement",
              "one-time", "happened", "occurred", "completed"):
        return "event"
    if fc in ("state", "states", "current", "ongoing", "active", "habit",
              "routine", "preference", "condition", "status"):
        return "state"
    if fc in VALID_FACT_CLASSES:
        return fc
    return "unclassified"


VALID_KNOWLEDGE_TIERS = {"identity", "situational", "context"}

def normalize_knowledge_tier(raw: str) -> str:
    """Normalize knowledge tier classification (D-039).
    - identity: biographical anchors, values, patterns — stable over months/years
    - situational: current mutable conditions — active projects, employment, location
    - context: one-off conversation artifacts — product lookups, specific tasks"""
    if not raw:
        return "untiered"
    kt = raw.strip().lower()
    if kt in ("identity", "t1", "biographical", "permanent", "anchor"):
        return "identity"
    if kt in ("situational", "t2", "current", "mutable", "active"):
        return "situational"
    if kt in ("context", "t3", "conversational", "ephemeral", "one-off", "artifact"):
        return "context"
    if kt in VALID_KNOWLEDGE_TIERS:
        return kt
    return "untiered"


# ---------------------------------------------------------------------------
# D-056 Tier 2: Predicate normalization + fact_text reconstruction
# ---------------------------------------------------------------------------

# Map common LLM variants to canonical predicates
_PREDICATE_ALIASES = {
    # values
    "cares about": "values", "cares_about": "values", "prizes": "values",
    "treasures": "values", "holds dear": "values",
    # works_at
    "works for": "works_at", "works_for": "works_at", "employed at": "works_at",
    "employed_at": "works_at", "works at": "works_at",
    # fears
    "afraid of": "fears", "afraid_of": "fears", "worries about": "fears",
    "worries_about": "fears", "anxious about": "fears",
    # excels_at
    "good at": "excels_at", "good_at": "excels_at", "skilled in": "excels_at",
    "skilled_in": "excels_at", "talented at": "excels_at",
    # struggles_with
    "struggles with": "struggles_with", "has difficulty": "struggles_with",
    "has_difficulty": "struggles_with",
    # married_to
    "married to": "married_to", "spouse is": "married_to",
    # lives_in
    "lives in": "lives_in", "resides in": "lives_in", "resides_in": "lives_in",
    "based in": "lives_in", "based_in": "lives_in",
    # raised_in
    "raised in": "raised_in", "grew up in": "raised_in", "grew_up_in": "raised_in",
    # graduated_from
    "graduated from": "graduated_from",
    # attended — NOT aliased to graduated_from (attending != graduating)
    "attended": "attended",
    # aspires_to
    "aspires to": "aspires_to", "hopes to": "aspires_to",
    # wants_to — NOT aliased to aspires_to (a want is weaker than an aspiration)
    "wants to": "wants_to",
    # identifies_as
    "identifies as": "identifies_as", "considers self": "identifies_as",
    # dislikes
    "does not like": "dislikes", "doesn't like": "dislikes",
    # enjoys
    "likes": "enjoys",
    # loves — separate from enjoys (intensity matters for commitment_depth)
    "loves": "loves",
    # hates — separate from dislikes (intensity matters for commitment_depth)
    "hates": "hates",
    # practices
    "engages in": "practices", "engages_in": "practices",
    # does — NOT aliased to practices (context-dependent: "does yoga" vs "does taxes")
    # studies
    "learning": "studies", "studying": "studies", "researching": "studies",
    # builds
    "building": "builds", "creating": "builds", "developing": "builds",
    # follows
    "tracks": "follows", "keeps up with": "follows",
    # interested_in — NOT aliased to follows (interest is passive, following is active)
    "interested in": "interested_in", "interested_in": "interested_in",
    # owns — for possession ("has X" where X is a thing)
    "has": "owns", "keeps": "maintains",
    # Past-tense variants -> canonical present tense
    "struggled_with": "struggles_with",
    "studied": "studies",
    "practiced": "practices",
    "built": "builds",
    "managed": "manages",
    "worked_at": "works_at",
    # Semantic aliases for new canonical predicates
    "experiences": "experienced",
    "observes": "monitors",
    # Session 55: relationship predicate aliases (Plan 1)
    "relates to": "relates_to",
    "related to": "relates_to",
    "collaborates with": "collaborates_with",
    "works with": "collaborates_with",
    "collaborated with": "collaborates_with",
    "mentored by": "mentored_by",
    "mentor is": "mentored_by",
    "learned from": "mentored_by",
    "raised by": "raised_by",
    "brought up by": "raised_by",
    "friends with": "friends_with",
    "friend of": "friends_with",
    "is friends with": "friends_with",
    "reports to": "reports_to",
    "works under": "reports_to",
    "managed by": "reports_to",
    "admires": "admires",
    "looks up to": "admires",
    "respects": "admires",
    "conflicts with": "conflicts_with",
    "disagrees with": "conflicts_with",
    "clashes with": "conflicts_with",
    # Additional relationship aliases for common LLM output patterns
    "child of": "raised_by",
    "son of": "raised_by",
    "daughter of": "raised_by",
    "parent of": "parents",
    "father of": "parents",
    "mother of": "parents",
    "sibling of": "relates_to",
    "brother of": "relates_to",
    "sister of": "relates_to",
}

_CANONICAL_SET = set(CONSTRAINED_PREDICATES)


def normalize_predicate(raw: str) -> str:
    """Map LLM predicate output to a canonical predicate from CONSTRAINED_PREDICATES.

    Falls back to the raw value if no mapping found — logged for vocabulary expansion.
    """
    if not raw:
        return "unknown"  # filterable default — don't corrupt real predicates
    p = raw.strip().lower()
    # Direct match
    if p in _CANONICAL_SET:
        return p
    # Alias lookup
    mapped = _PREDICATE_ALIASES.get(p)
    if mapped:
        return mapped
    # Underscore normalization: "works at" -> "works_at"
    underscored = p.replace(" ", "_")
    if underscored in _CANONICAL_SET:
        return underscored
    # No match — return raw (downstream can still use it)
    return p


def reconstruct_fact_text(subject: str, predicate: str, object_text: str) -> str:
    """Build a clean fact_text string from structured fields.

    Qualifier intentionally NOT included — stored separately.
    This keeps fact_text clean for scoring, dedup, and domain matching.
    """
    pred_display = predicate.replace("_", " ") if predicate else ""
    return f"{subject} {pred_display} {object_text}".strip()


def _predicate_to_intent(predicate: str) -> str:
    """Map a structured predicate to a legacy intent value for backward compatibility."""
    _intent_map = {
        "studies": "learning", "learned": "learning",
        "experienced": "historical", "lost": "historical", "founded": "historical",
        "graduated_from": "historical", "raised_in": "historical",
    }
    return _intent_map.get(predicate, "does")


def compute_confidence(raw_llm_confidence: float, intent: str, subject: str,
                       message_count: int) -> float:
    """Compute objective confidence score from multiple signals.
    D-022: Replaces reliance on Qwen's self-assessed confidence (81% were 1.0).

    Formula:
        0.20 * qwen_confidence +    (LLM's guess, downweighted)
        0.30 * intent_score +       (does=1.0, learning=0.7, curious=0.4, etc.)
        0.25 * subject_score +      (user=1.0, others=0.5)
        0.25 * depth_score          (message_count / 30, capped at 1.0)
    """
    # Intent score
    intent_scores = {
        "does": 1.0,
        "learning": 0.7,
        "curious": 0.4,
        "historical": 0.6,
    }
    intent_score = intent_scores.get(intent, 0.5)

    # Subject score — user's own facts are more reliable
    subject_score = 1.0 if subject == "user" else 0.5

    # Depth score — longer conversations = more reliable facts
    depth_score = min(message_count / 30.0, 1.0)

    # Weighted combination
    confidence = (
        0.20 * min(max(raw_llm_confidence, 0.0), 1.0) +
        0.30 * intent_score +
        0.25 * subject_score +
        0.25 * depth_score
    )

    return round(min(max(confidence, 0.0), 1.0), 4)

# Schema for the AUDN decision step
AUDN_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["ADD", "UPDATE", "DELETE", "NOOP"]
        },
        "reasoning": {"type": "string"},
        "updated_fact": {"type": "string"},
        "confidence": {"type": "number"}
    },
    "required": ["action", "reasoning"]
}


# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------

def create_tables():
    """Create the memory_facts, fact_relationships, user_corrections tables."""
    with contextlib.closing(get_db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_facts (
                id TEXT PRIMARY KEY,
                fact_text TEXT NOT NULL,
                category TEXT,
                confidence REAL,
                surprise_score REAL,
                significance_score REAL,
                recurrence_count INTEGER DEFAULT 0,
                depth_score REAL DEFAULT 0,
                recurrence_span_days INTEGER DEFAULT 0,
                significance_type TEXT,
                source_conversation_id TEXT,
                created_at REAL,
                updated_at REAL,
                superseded_by TEXT,
                FOREIGN KEY (source_conversation_id) REFERENCES conversations(id)
            )
        """)

        # Add columns if they don't exist (idempotent)
        for col_sql in [
            "ALTER TABLE memory_facts ADD COLUMN source TEXT DEFAULT 'extraction'",
            "ALTER TABLE memory_facts ADD COLUMN subject TEXT DEFAULT 'user'",
            "ALTER TABLE memory_facts ADD COLUMN intent TEXT DEFAULT 'does'",
            "ALTER TABLE memory_facts ADD COLUMN temporal_state TEXT DEFAULT 'unknown'",
            "ALTER TABLE memory_facts ADD COLUMN raw_llm_confidence REAL",
            "ALTER TABLE memory_facts ADD COLUMN fact_class TEXT DEFAULT 'unclassified'",
            "ALTER TABLE memory_facts ADD COLUMN knowledge_tier TEXT DEFAULT 'untiered'",
            "ALTER TABLE memory_facts ADD COLUMN tiered_by TEXT",
            "ALTER TABLE memory_facts ADD COLUMN scope TEXT DEFAULT 'personal'",
        ]:
            try:
                conn.execute(col_sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_category
            ON memory_facts(category)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_confidence
            ON memory_facts(confidence)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_relationships (
                fact_id_1 TEXT,
                fact_id_2 TEXT,
                co_occurrence_count INTEGER DEFAULT 1,
                source_conversation_id TEXT,
                PRIMARY KEY (fact_id_1, fact_id_2)
            )
        """)

        # Track which conversations have been processed (for resuming)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extraction_log (
                conversation_id TEXT PRIMARY KEY,
                facts_extracted INTEGER,
                processed_at REAL
            )
        """)

        # User corrections — permanent record that survives extraction resets (D-021)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_corrections (
                id TEXT PRIMARY KEY,
                correction_type TEXT NOT NULL,
                original_fact_id TEXT,
                original_fact_text TEXT,
                corrected_fact_text TEXT,
                corrected_category TEXT,
                corrected_subject TEXT,
                annotation TEXT,
                match_patterns TEXT,
                created_at REAL NOT NULL,
                notes TEXT
            )
        """)

        conn.commit()
        print("Database tables ready (memory_facts, fact_relationships, extraction_log, user_corrections)")


# ---------------------------------------------------------------------------
# Ollama Helpers
# ---------------------------------------------------------------------------

def call_ollama(prompt: str, schema: dict = None, retries: int = MAX_RETRIES) -> dict:
    """
    Call Qwen via Ollama with optional JSON schema enforcement (D-010).
    Uses the 'format' parameter for schema-enforced output.
    Falls back to simpler prompt on parse failure.
    """
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2000},
    }

    # Use Ollama schema enforcement if schema provided
    if schema:
        payload["format"] = schema

    for attempt in range(retries + 1):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            response.raise_for_status()
            raw = response.json().get("response", "").strip()

            # Parse JSON
            if "```" in raw:
                raw = raw.split("```")[1].replace("json", "").strip()

            result = json.loads(raw)
            return result

        except json.JSONDecodeError:
            if attempt < retries:
                # Retry with simpler prompt
                payload["prompt"] = f"Respond with ONLY valid JSON. No explanation.\n\n{prompt}"
                if not schema:
                    payload["options"]["temperature"] = 0.0
                continue
            else:
                return None

        except requests.exceptions.ConnectionError:
            print("  ERROR: Cannot connect to Ollama. Is it running? (ollama serve)")
            return None

        except Exception as e:
            if attempt < retries:
                continue
            else:
                print(f"  ERROR: Ollama call failed: {e}")
                return None

    return None


_anthropic_client = None


def _get_anthropic_client():
    """Lazy-initialize and reuse a single Anthropic client instance."""
    global _anthropic_client
    if _anthropic_client is None:
        from llm_provider import get_anthropic_client
        _anthropic_client = get_anthropic_client()
    return _anthropic_client


def call_anthropic(prompt: str, schema: dict = None, retries: int = MAX_RETRIES,
                    max_tokens: int = None) -> dict:
    """
    Call Anthropic API (Haiku/Sonnet) for fact extraction.
    Alternative to local Ollama for users without GPU or Qwen.
    Returns parsed JSON dict, same interface as call_ollama.

    max_tokens scales dynamically with extraction request size.
    """
    client = _get_anthropic_client()
    json_instruction = "Respond with ONLY valid JSON matching this schema. No explanation, no markdown fences.\n"
    if schema:
        json_instruction += f"Schema: {json.dumps(schema, indent=2)}\n\n"

    # Dynamic output tokens: estimate from prompt length if not specified
    if max_tokens is None:
        # ~150 tokens per fact, estimate facts from prompt length
        prompt_len = len(prompt)
        estimated_facts = min(50, max(10, prompt_len // 500))
        max_tokens = max(2000, estimated_facts * 200)

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=EXTRACTION_API_MODEL,
                max_tokens=max_tokens,
                temperature=0.1,
                messages=[{"role": "user", "content": json_instruction + prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            result = json.loads(raw)
            return result

        except json.JSONDecodeError:
            if attempt < retries:
                continue
            else:
                return None

        except Exception as e:
            if attempt < retries:
                continue
            else:
                print(f"  ERROR: Anthropic API call failed: {e}")
                return None

    return None


def call_llm(prompt: str, schema: dict = None, retries: int = MAX_RETRIES) -> dict:
    """Dispatch to configured backend (ollama or anthropic)."""
    if EXTRACTION_BACKEND == "anthropic":
        return call_anthropic(prompt, schema, retries)
    else:
        return call_ollama(prompt, schema, retries)


# ---------------------------------------------------------------------------
# Correction Guard (D-021: Fix Once, Fixed Forever)
# ---------------------------------------------------------------------------

def load_corrections(conn):
    """
    Load all user corrections from the database.
    Returns a list of match patterns that should block re-extraction.
    Called once at the start of an extraction run.
    """
    try:
        rows = conn.execute("""
            SELECT id, correction_type, match_patterns, corrected_fact_text, notes
            FROM user_corrections
        """).fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return []

    corrections = []
    for row in rows:
        patterns_raw = row[2]
        if patterns_raw:
            try:
                patterns = json.loads(patterns_raw)
            except (json.JSONDecodeError, TypeError):
                patterns = []
        else:
            patterns = []

        corrections.append({
            "id": row[0],
            "type": row[1],
            "patterns": [p.lower() for p in patterns if p],
            "corrected_text": row[3],
            "notes": row[4],
        })

    return corrections


def check_against_corrections(candidate_fact_text, corrections):
    """
    Check a candidate fact against known corrections.
    Returns True if the fact should be BLOCKED (matches a known wrong pattern).
    Uses case-insensitive substring matching on keywords.
    """
    fact_lower = candidate_fact_text.lower()

    for correction in corrections:
        for pattern in correction["patterns"]:
            if pattern in fact_lower:
                return True  # Block this fact

    return False  # Allow this fact


# ---------------------------------------------------------------------------
# Fact Extraction
# ---------------------------------------------------------------------------

def build_extraction_prompt(conv_title: str, conv_text: str,
                            max_facts: int = MAX_FACTS_PER_CONVERSATION,
                            chunk_info: str = None) -> str:
    """Build the Variant D structured extraction prompt.

    Factored out for reuse by batch_extract.py — prompt is identical whether
    called sequentially or submitted as a batch request.

    Session 55: Added relationship extraction guidance (Plan 1) and dynamic
    max_facts cap communicated to the LLM for self-prioritization (Plan 2).
    Session 65: Added chunk_info for multi-chunk extraction of long texts.
    """
    predicates_str = ", ".join(CONSTRAINED_PREDICATES)

    # Session 55 (Plan 1): Load known entities to prime relationship extraction
    entity_hints = _get_known_entities_for_prompt()

    chunk_context = f"\n<chunk_context>{chunk_info}</chunk_context>\n" if chunk_info else ""

    return f"""You are extracting personal facts about a user from their conversation with an AI assistant.
{chunk_context}

<conversation_title>{conv_title}</conversation_title>

<conversation_content>
{conv_text}
</conversation_content>

Extract facts about the USER as structured triples. Maximize information density — every word should carry meaning. No hedging language ("seems to", "appears to", "might be"). If uncertain, lower the confidence score instead of hedging in the text.

Extract up to {max_facts} facts, prioritizing the most identity-relevant ones.

For each fact, provide:
- subject: Who the fact is about. Use the person's name if known, otherwise "user".
- predicate: The relationship or attribute. MUST be one of: {predicates_str}
- object: The specific value, entity, or description. Be concrete and precise — names, numbers, and specifics over vague descriptions.
- qualifier: Temporal or conditional context. IMPORTANT: If temporal scope is unclear, mark as "unknown" rather than guessing. Only include qualifiers when you have clear evidence.
- category: One of: preference, biography, project, relationship, interest, skill, value, habit, opinion, goal, negative_trait
- temporal: current, past, or unknown
- confidence: 0.0 to 1.0

RELATIONSHIP EXTRACTION (important — relationships are severely underrepresented):
Pay special attention to relationships mentioned: family members, friends, colleagues, mentors, romantic partners, children, siblings, collaborators.
For each person mentioned, extract:
  1. WHO they are to the user (use predicates: married_to, parents, raised_by, friends_with, collaborates_with, mentored_by, reports_to, relates_to)
  2. What the relationship DYNAMIC is (e.g., "user collaborates_with Alex on newsletter content")
  3. Use category "relationship" for all interpersonal facts
Do NOT skip relationship facts in favor of more opinions or preferences.
{entity_hints}

Examples of good structured facts:
  {{"subject": "user", "predicate": "married_to", "object": "Partner", "qualifier": "unknown", "category": "relationship", "temporal": "current", "confidence": 0.95}}
  {{"subject": "user", "predicate": "trades", "object": "US equities, scalping and day trading", "qualifier": "active as of 2024", "category": "interest", "temporal": "current", "confidence": 0.9}}
  {{"subject": "user", "predicate": "founded", "object": "a startup", "qualifier": "did not succeed", "category": "biography", "temporal": "past", "confidence": 0.85}}
  {{"subject": "user", "predicate": "values", "object": "data sovereignty over cloud convenience", "qualifier": "unknown", "category": "value", "temporal": "current", "confidence": 0.9}}
  {{"subject": "user", "predicate": "friends_with", "object": "Alex, childhood friend", "qualifier": "unknown", "category": "relationship", "temporal": "current", "confidence": 0.85}}
  {{"subject": "user", "predicate": "mentored_by", "object": "Jordan, former manager at first job", "qualifier": "unknown", "category": "relationship", "temporal": "past", "confidence": 0.8}}

Focus on durable identity facts. Skip trivial conversation artifacts (product lookups, debugging steps, one-off tasks) unless they reveal something lasting about the person.

Return a JSON object with a "facts" array."""


def build_identity_extraction_prompt(conv_title: str, conv_text: str,
                                     max_facts: int = MAX_FACTS_PER_CONVERSATION) -> str:
    """Build the identity-focused extraction prompt for project conversations (D-048).

    Factored out for reuse by batch_extract.py.
    Session 55: Added relationship guidance and dynamic max_facts cap.
    """
    predicates_str = ", ".join(CONSTRAINED_PREDICATES)

    # Session 55 (Plan 1): Load known entities to prime relationship extraction
    entity_hints = _get_known_entities_for_prompt()

    return f"""You are extracting PERSONAL IDENTITY facts from a technical project conversation between a user and an AI coding assistant.

<conversation_title>{conv_title}</conversation_title>

<conversation_content>
{conv_text}
</conversation_content>

IMPORTANT CONTEXT: This is a project/coding session. The code and technical content has been stripped. What remains are the user's directives, decisions, and feedback. Extract ONLY facts about the USER AS A PERSON.

Extract up to {max_facts} facts, prioritizing the most identity-relevant ones.

Extract facts as structured triples. Maximize information density — every word should carry meaning. No hedging language.

For each fact, provide:
- subject: Who the fact is about. Use the person's name if known, otherwise "user".
- predicate: MUST be one of: {predicates_str}
- object: The specific value, entity, or description. Be concrete and precise.
- qualifier: Temporal or conditional context. Mark as "unknown" if unclear.
- category: One of: preference, biography, relationship, interest, skill, value, habit, opinion, goal, negative_trait
- temporal: current, past, or unknown
- confidence: 0.0 to 1.0

EXTRACT facts about: Working style, communication preferences, values, cognitive patterns, leadership style, personality traits, preferences and opinions that transcend the project.

RELATIONSHIP EXTRACTION: If colleagues, collaborators, or other people are mentioned, extract WHO they are and their role/dynamic.
{entity_hints}

DO NOT EXTRACT: Software architecture, technical decisions, tools/libraries/frameworks, code artifacts, anything only true within this project context.

Return a JSON object with a "facts" array. If no personal identity facts are found, return {{"facts": []}}."""


def build_document_extraction_prompt(doc_title: str, doc_text: str,
                                     max_facts: int = MAX_FACTS_PER_CONVERSATION,
                                     chunk_info: str = None) -> str:
    """Build extraction prompt for document corpora (patents, papers, reports).

    Session 68: Treats the document corpus itself as the subject. Extracts the
    document's implicit worldview — what it assumes, what it prioritizes, how it
    approaches problems — as if the corpus were a person.

    The subject is 'this corpus' rather than 'user'. Predicates are reinterpreted:
    - believes → implicit assumptions the document takes as given
    - values → what the document optimizes for or treats as important
    - practices → methodologies and approaches the document employs
    - prioritizes → what the document foregrounds vs backgrounds
    - avoids → what the document guards against or explicitly excludes
    - struggles_with → tensions or unresolved problems in the document
    """
    predicates_str = ", ".join(CONSTRAINED_PREDICATES)

    chunk_context = f"\n<chunk_context>{chunk_info}</chunk_context>\n" if chunk_info else ""

    return f"""You are extracting the IMPLICIT WORLDVIEW of a document. Treat this document as if it were a person — what does it "believe"? What does it "value"? How does it "think"?
{chunk_context}

<document_title>{doc_title}</document_title>

<document_content>
{doc_text}
</document_content>

Extract the document's worldview as structured triples. The subject is "this corpus" (or a more specific label like "this patent" or "this paper" if appropriate).

Extract up to {max_facts} facts, prioritizing the most distinctive and identity-revealing ones.

For each fact, provide:
- subject: "this corpus" (or "this patent", "this paper", etc.)
- predicate: The relationship or attribute. MUST be one of: {predicates_str}
- object: The specific value, assumption, or pattern. Be concrete and precise.
- qualifier: Conditional context. Mark as "unknown" if unclear.
- category: One of: value, opinion, skill, interest, preference, habit, goal
- temporal: current, past, or unknown
- confidence: 0.0 to 1.0

HOW TO READ DOCUMENTS AS IDENTITY:
- "believes" = what the document assumes without arguing for it (prior art, axioms, unstated premises)
- "values" = what the document optimizes for (novelty, efficiency, safety, precision, cost reduction)
- "practices" = methodologies the document employs (mathematical proof, empirical testing, comparative analysis)
- "prioritizes" = what gets foregrounded vs backgrounded (which problems matter most)
- "avoids" = what the document guards against or explicitly excludes (failure modes, prior art limitations)
- "struggles_with" = tensions or unresolved tradeoffs (accuracy vs speed, specificity vs generality)
- "builds" = what the document constructs or proposes (systems, methods, compositions)
- "excels_at" = what the document does particularly well or claims novelty in

Examples of good document-worldview facts:
  {{"subject": "this patent", "predicate": "believes", "object": "sensor fusion of LiDAR and camera data produces more reliable 3D object detection than either modality alone", "qualifier": "unstated assumption", "category": "value", "temporal": "current", "confidence": 0.9}}
  {{"subject": "this patent", "predicate": "values", "object": "real-time processing speed over exhaustive accuracy in autonomous vehicle perception", "qualifier": "unknown", "category": "value", "temporal": "current", "confidence": 0.85}}
  {{"subject": "this patent", "predicate": "struggles_with", "object": "the tradeoff between computational cost and detection resolution in multi-sensor systems", "qualifier": "acknowledged limitation", "category": "opinion", "temporal": "current", "confidence": 0.8}}
  {{"subject": "this patent", "predicate": "avoids", "object": "dependence on GPS positioning for object localization", "qualifier": "explicit design choice", "category": "preference", "temporal": "current", "confidence": 0.85}}

Focus on the DISTINCTIVE worldview — what makes this document's perspective unique? Skip generic facts that would be true of any document in the field. Extract the implicit philosophy, not just the technical content.

Return a JSON object with a "facts" array."""


# D-048: Contamination keywords for identity extraction from project conversations
_IDENTITY_CONTAMINATION_KEYWORDS = [
    "memory system", "pipeline", "extraction", "chromadb", "sqlite",
    "embedding", "identity block", "identity layer", "mcp server",
    "brief assembly", "fact extraction", "base layer", "baselayer",
    "claude code", "ollama", "qwen", "haiku", "sonnet", "opus",
    "d-0", "decision d-", "collective review",
]


def validate_structured_response(raw_facts: list[dict], message_count: int,
                                  identity_only: bool = False,
                                  max_facts: int = None) -> list[dict]:
    """Validate and normalize structured extraction results.

    D-056 Tier 2: Processes raw LLM output into normalized fact dicts with
    reconstructed fact_text for downstream compatibility.

    Factored out for reuse by batch_extract.py — validation is identical
    whether facts came from sequential or batch extraction.

    Args:
        raw_facts: List of raw fact dicts from LLM response.
        message_count: Number of messages in source conversation (for confidence).
        identity_only: If True, apply contamination filter (D-048).
        max_facts: Dynamic cap on facts per conversation (Session 55, Plan 2).
                   Falls back to MAX_FACTS_PER_CONVERSATION if not provided.

    Returns:
        List of validated, normalized fact dicts.
    """
    # Session 55 (Plan 2): Use dynamic cap if provided, else legacy default
    effective_cap = max_facts if max_facts is not None else MAX_FACTS_PER_CONVERSATION

    valid_facts = []
    for fact in raw_facts[:effective_cap]:
        raw_confidence = fact.get("confidence", 0.5)
        if raw_confidence < 0.3:
            continue

        # Extract structured fields
        raw_subject = fact.get("subject", "user")
        raw_predicate = fact.get("predicate", "")
        raw_object = fact.get("object", "").strip()
        raw_qualifier = fact.get("qualifier", "unknown")

        if not raw_object or len(raw_object) < 3:
            continue

        # Normalize
        subject = normalize_subject(raw_subject)
        predicate = normalize_predicate(raw_predicate)
        temporal = normalize_temporal(fact.get("temporal", "unknown"))
        intent = _predicate_to_intent(predicate)

        # Reconstruct fact_text for downstream compatibility
        fact_text = reconstruct_fact_text(subject, predicate, raw_object)

        if len(fact_text) < MIN_FACT_LENGTH:
            continue

        # D-048: Contamination filter for identity extraction from project conversations
        if identity_only:
            fact_lower = fact_text.lower()
            if any(kw in fact_lower for kw in _IDENTITY_CONTAMINATION_KEYWORDS):
                continue

        computed_conf = compute_confidence(raw_confidence, intent, subject, message_count)

        # Normalize qualifier — "unknown" or empty means no qualifier
        qualifier = raw_qualifier.strip() if raw_qualifier else None
        if qualifier and qualifier.lower() in ("unknown", "none", "n/a", ""):
            qualifier = None

        valid_facts.append({
            "fact": fact_text,
            "category": normalize_category(fact.get("category", "unknown")),
            "confidence": computed_conf,
            "raw_llm_confidence": min(max(raw_confidence, 0.0), 1.0),
            "subject": subject,
            "intent": intent,
            "temporal": temporal,
            "fact_class": "unclassified",
            "knowledge_tier": "untiered",
            "predicate": predicate,
            "object_text": raw_object,
            "qualifier": qualifier,
        })

    return valid_facts


def _strip_noise_content(text: str) -> str:
    """Strip non-natural-language content that wastes extraction budget.

    Session 68: Automated noise stripping so any text corpus can be imported
    without manual preprocessing. Handles:
    - Genome/DNA sequences (ATCG runs of 50+ chars)
    - Chemical formulas / SMILES notation (long alphanumeric+symbol runs)
    - Hex dumps and binary data
    - Repeated structural data (long sequences of numbers/symbols)

    Replaces noise with a short placeholder so surrounding context is preserved.
    """
    import re

    original_len = len(text)
    replacements = 0

    # 1. Genome sequences: runs of ATCG (50+ chars, possibly with spaces/newlines)
    text, n = re.subn(r'[ATCG]{50,}', '[SEQUENCE_OMITTED]', text)
    replacements += n

    # 2. Long hex strings (32+ hex chars, common in blockchain/crypto patents)
    text, n = re.subn(r'(?<![a-zA-Z])[0-9a-fA-F]{32,}(?![a-zA-Z])', '[HEX_OMITTED]', text)
    replacements += n

    # 3. Chemical notation: SMILES strings (long runs of special chars + letters)
    # Match strings like C1=CC(=O)N(C2=CC=CC=C2)... (40+ chars, contains =()[]/ mixed with letters)
    text, n = re.subn(r'[A-Za-z0-9\(\)\[\]=\+\-\\/\.#@]{60,}', '[NOTATION_OMITTED]', text)
    replacements += n

    # 4. Coordinate/matrix dumps: lines that are 80%+ numbers/commas/spaces
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if len(line) > 100:
            non_alpha = sum(1 for c in line if c.isdigit() or c in '.,;:| \t')
            if non_alpha / len(line) > 0.8:
                cleaned_lines.append('[NUMERIC_DATA_OMITTED]')
                replacements += 1
                continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # Collapse consecutive omission placeholders
    text = re.sub(r'(\[(?:SEQUENCE|HEX|NOTATION|NUMERIC_DATA)_OMITTED\]\s*){2,}',
                  '[DATA_OMITTED]\n', text)

    if replacements > 0:
        saved = original_len - len(text)
        print(f"  Noise stripping: {replacements} replacements, {saved:,} chars removed")

    return text


def _chunk_text_for_extraction(full_text: str, input_char_budget: int,
                                overlap: int = 500) -> list[str]:
    """Split long text into chunks for multi-pass extraction.

    Session 65: Handles long single-message imports (autobiographies, chapters)
    that exceed the input_char_budget. Splits on paragraph boundaries with overlap.

    Args:
        full_text: The complete text to chunk.
        input_char_budget: Target size for each chunk.
        overlap: Characters of overlap between chunks for boundary context.

    Returns:
        List of text chunks. Single-element list if text fits in budget.
    """
    if len(full_text) <= input_char_budget:
        return [full_text]

    chunks = []
    paragraphs = full_text.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph would exceed budget, finalize current chunk
        if current_chunk and len(current_chunk) + len(para) + 2 > input_char_budget:
            chunks.append(current_chunk)
            # Start next chunk with overlap from end of current
            if overlap > 0 and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + "\n\n" + para
            else:
                current_chunk = para
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk)

    return chunks


def extract_facts_from_conversation(conv_id: str, conv_title: str, messages: list[dict],
                                     use_fallback_schema: bool = False,
                                     document_mode: bool = False) -> list[dict]:
    """
    Extract candidate facts from a conversation's messages.

    D-056 Tier 2: Structured extraction with constrained predicates (Variant D).
    Returns structured triples {subject, predicate, object, qualifier} with
    fact_text reconstructed for downstream compatibility.

    Session 55 (Plan 2): Input text budget and max facts now scale with
    message count via EXTRACTION_CAPS config.

    Session 65: Added chunking path for long single-message imports.
    When total text exceeds input_char_budget, splits into chunks and
    extracts from each chunk separately. AUDN dedup handles cross-chunk dupes.

    Session 68: document_mode treats the text as a document corpus (patents,
    papers, reports) and extracts the document's implicit worldview rather
    than personal facts about a user.
    """
    # Compute total character count across all messages
    total_chars = sum(len(msg.get("text", "")) for msg in messages)

    # Session 65: Get scaled extraction caps using both message count and char count
    caps = _get_extraction_caps(len(messages), total_chars)
    input_char_budget = caps["input_char_budget"]
    max_facts = caps["max_facts"]

    schema = EXTRACT_SCHEMA_FALLBACK if use_fallback_schema else EXTRACT_SCHEMA

    # Session 65: Chunking path for long texts (e.g., autobiography chapters)
    if total_chars > input_char_budget:
        # Build full text without per-message truncation
        full_text = ""
        for msg in messages:
            role = msg["role"].capitalize()
            full_text += f"{role}: {msg['text']}\n"

        # Session 68: Strip noise content (genome sequences, hex, etc.) before chunking
        full_text = _strip_noise_content(full_text)

        chunks = _chunk_text_for_extraction(full_text, input_char_budget)
        per_chunk_cap = min(50, max_facts)  # D-076: Raised from 15 — let AUDN handle dedup, not caps
        all_facts = []

        for i, chunk in enumerate(chunks):
            chunk_info = f"Section {i + 1} of {len(chunks)} from '{conv_title}'. Extract facts from this section."
            if document_mode:
                prompt = build_document_extraction_prompt(conv_title, chunk,
                                                          max_facts=per_chunk_cap,
                                                          chunk_info=chunk_info)
            else:
                prompt = build_extraction_prompt(conv_title, chunk,
                                                 max_facts=per_chunk_cap,
                                                 chunk_info=chunk_info)
            result = call_llm(prompt, schema=schema)
            if result and "facts" in result:
                validated = validate_structured_response(
                    result["facts"], len(messages), max_facts=per_chunk_cap
                )
                all_facts.extend(validated)

        # Apply overall max_facts cap to combined results
        return all_facts[:max_facts]

    # Standard single-pass path (short conversations, no change)
    conv_text = ""
    for msg in messages:
        role = msg["role"].capitalize()
        text = msg["text"][:1500]
        conv_text += f"{role}: {text}\n"
        if len(conv_text) > input_char_budget:
            conv_text += "\n[conversation continues...]\n"
            break

    # Session 68: Strip noise content (genome sequences, hex, etc.)
    conv_text = _strip_noise_content(conv_text)

    if document_mode:
        prompt = build_document_extraction_prompt(conv_title, conv_text, max_facts=max_facts)
    else:
        prompt = build_extraction_prompt(conv_title, conv_text, max_facts=max_facts)
    result = call_llm(prompt, schema=schema)

    if not result or "facts" not in result:
        return []

    return validate_structured_response(result["facts"], len(messages), max_facts=max_facts)


def _abstract_project_conversation(messages: list[dict]) -> str:
    """
    D-048: Abstract a project conversation for identity extraction.

    Claude Code sessions are ~90% code, tool output, and file diffs.
    The identity signal lives in the user's directives, feedback, and decisions.

    Strategy:
    - Keep ALL user messages (these are the identity signal)
    - Keep only short assistant messages (<500 chars after stripping) — these are
      summaries, questions, and clarifications that provide conversational context
    - Strip code blocks from all messages
    - Result: a "decision conversation" instead of a coding session
    """
    import re

    # Session 55 (Plan 2): Scale input budget for project conversations too
    caps = _get_extraction_caps(len(messages))
    input_char_budget = caps["input_char_budget"]

    abstracted = ""

    for msg in messages:
        role = msg["role"]
        text = msg["text"]

        # Strip fenced code blocks — never identity-relevant
        text = re.sub(r'```[\s\S]*?```', '[code removed]', text)

        # Strip XML-style tool blocks (common in Claude Code transcripts)
        text = re.sub(r'<[a-z_]+>[\s\S]*?</[a-z_]+>', '[tool output removed]', text)

        # Strip file paths and diff-like content
        text = re.sub(r'^\s*[+-]{3}\s+[a-z]/.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*@@.*@@.*$', '', text, flags=re.MULTILINE)

        # Collapse multiple whitespace/newlines
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        if role == "user":
            # Keep ALL user messages — this is where identity signal lives
            abstracted += f"User: {text[:1500]}\n"
        else:
            # Only keep short assistant messages (summaries, questions, context)
            if len(text) <= 500:
                abstracted += f"Assistant: {text}\n"
            else:
                # For long assistant messages, just keep the first line as context
                first_line = text.split('\n')[0][:200]
                abstracted += f"Assistant: {first_line} [...]\n"

        if len(abstracted) > input_char_budget:
            abstracted += "\n[conversation continues...]\n"
            break

    return abstracted


def extract_identity_from_project_conversation(conv_id: str, conv_title: str,
                                                messages: list[dict],
                                                use_fallback_schema: bool = False) -> list[dict]:
    """
    D-048: Extract ONLY identity-relevant facts from project-scope conversations.
    D-056 Tier 2: Now uses structured predicates (Variant D) same as main extraction.

    Uses conversation abstraction to strip code/tool output, then a specialized
    prompt that focuses on facts about the USER's working style, values,
    preferences, decision-making patterns, and communication style.

    These facts are tagged scope='personal' because they describe who the person IS,
    even though they come from a project context.

    Session 55 (Plan 2): Max facts now scaled by message count.
    """
    # Session 55 (Plan 2): Get scaled caps
    caps = _get_extraction_caps(len(messages))
    max_facts = caps["max_facts"]

    # D-048: Abstract conversation — strip code, keep user directives
    conv_text = _abstract_project_conversation(messages)

    if len(conv_text.strip()) < 100:
        return []  # Not enough content after abstraction

    prompt = build_identity_extraction_prompt(conv_title, conv_text, max_facts=max_facts)

    schema = EXTRACT_SCHEMA_FALLBACK if use_fallback_schema else EXTRACT_SCHEMA
    result = call_llm(prompt, schema=schema)

    if not result or "facts" not in result:
        return []

    return validate_structured_response(result["facts"], len(messages), identity_only=True,
                                        max_facts=max_facts)


# ---------------------------------------------------------------------------
# AUDN Decision (D-005)
# ---------------------------------------------------------------------------

def find_similar_facts(fact_text: str, collection, embed_model, top_k: int = 5) -> list[dict]:
    """
    Find existing facts that are similar to the candidate fact.
    Used for deduplication — if a very similar fact exists, we UPDATE or NOOP.
    Uses pre-loaded embed_model to avoid repeated model reloads.
    """
    if collection is None or embed_model is None:
        return []

    try:
        # Use pre-loaded model instead of query_texts to avoid reloading
        embedding = embed_model.encode([fact_text]).tolist()
        results = collection.query(
            query_embeddings=embedding,
            n_results=top_k,
        )

        similar = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                # Convert L2 distance to similarity (for normalized vectors)
                similarity = max(0, 1 - (distance ** 2) / 2)
                similar.append({
                    "fact_text": doc,
                    "fact_id": meta.get("fact_id", ""),
                    "similarity": round(similarity, 4),
                })

        return similar

    except Exception as e:
        print(f"  WARNING: find_similar_facts failed: {e}", file=sys.stderr)
        return []


def make_audn_decision(candidate_fact: str, similar_facts: list[dict]) -> dict:
    """
    Ask Qwen whether this fact should be ADDed, UPDATEd, DELETEd, or NOOPed.
    Provides similar existing facts as context for deduplication.
    """
    # OPTIMIZATION: Only call LLM when similarity is very high (likely true duplicate)
    # For batch extraction, we prioritize speed — deduplication can be refined later

    if not similar_facts or all(f["similarity"] < 0.3 for f in similar_facts):
        # No similar facts — this is clearly new
        return {
            "action": "ADD",
            "reasoning": "No similar facts in memory",
            "updated_fact": candidate_fact,
            "confidence": 0.8,
        }

    # Check if any are very similar (likely duplicate)
    max_similarity = max(f["similarity"] for f in similar_facts)

    # Only call LLM for very high similarity (>0.85) — likely true duplicates
    if max_similarity > SIMILARITY_THRESHOLD:
        # Build context with similar facts
        similar_text = ""
        for i, sf in enumerate(similar_facts[:3]):  # Limit to top 3
            similar_text += f"  {i+1}. \"{sf['fact_text']}\" (similarity: {sf['similarity']:.0%})\n"

        # Very similar fact exists — ask LLM to decide
        prompt = f"""A new fact was extracted. Similar facts exist in memory.

NEW: "{candidate_fact}"

EXISTING:
{similar_text}

Is this a duplicate? Reply with JSON: action=NOOP if duplicate, ADD if genuinely new, UPDATE if it refines existing."""

        result = call_llm(prompt, schema=AUDN_SCHEMA)

        if result and "action" in result:
            if result["action"] == "UPDATE" and not result.get("updated_fact"):
                result["updated_fact"] = candidate_fact
            return result

    # Moderate similarity (0.3-0.85) — treat as new, skip LLM to save time
    # These can be reviewed later if needed
    return {
        "action": "ADD",
        "reasoning": f"Moderate similarity ({max_similarity:.0%}), treating as new",
        "updated_fact": candidate_fact,
        "confidence": 0.6,
    }


# ---------------------------------------------------------------------------
# Fact Storage
# ---------------------------------------------------------------------------

def store_fact(conn, fact_text: str, category: str, confidence: float,
               conv_id: str, audn_action: str, supersedes_id: str = None,
               subject: str = "user", intent: str = "does",
               temporal: str = "unknown", raw_llm_confidence: float = None,
               fact_class: str = "unclassified",
               knowledge_tier: str = "untiered",
               tiered_by: str = None,
               scope: str = None,
               predicate: str = None,
               object_text: str = None,
               qualifier: str = None) -> str:
    """Store a fact in memory_facts and return its ID.
    D-022: Now stores subject, intent, temporal_state, and raw_llm_confidence.
    Temporal processing: Now stores fact_class (event/state/unclassified).
    D-039: Now stores knowledge_tier (identity/situational/context/untiered).
    D-044: Now stores scope (personal/project) derived from conversation source.
    D-056 Tier 2: Now stores predicate, object_text, qualifier from structured extraction.
    Provenance: tiered_by tracks which model assigned the tier (qwen/opus)."""
    fact_id = str(uuid.uuid4())
    now = time.time()

    conn.execute("""
        INSERT INTO memory_facts
        (id, fact_text, category, confidence, source_conversation_id,
         created_at, updated_at, superseded_by, source,
         subject, intent, temporal_state, raw_llm_confidence, fact_class,
         knowledge_tier, tiered_by, scope,
         predicate, object_text, qualifier)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'extraction', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fact_id, fact_text, category, confidence, conv_id, now, now,
          subject, intent, temporal, raw_llm_confidence, fact_class,
          knowledge_tier, tiered_by, scope,
          predicate, object_text, qualifier))

    # If this supersedes another fact, mark the old one
    if supersedes_id:
        conn.execute("""
            UPDATE memory_facts SET superseded_by = ?, updated_at = ?
            WHERE id = ?
        """, (fact_id, now, supersedes_id))

    return fact_id


def link_facts(conn, fact_ids: list[str], conv_id: str):
    """Create co-occurrence edges between facts from the same conversation (D-013)."""
    for i in range(len(fact_ids)):
        for j in range(i + 1, len(fact_ids)):
            id1, id2 = sorted([fact_ids[i], fact_ids[j]])
            conn.execute("""
                INSERT INTO fact_relationships (fact_id_1, fact_id_2, co_occurrence_count, source_conversation_id)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(fact_id_1, fact_id_2) DO UPDATE SET
                    co_occurrence_count = co_occurrence_count + 1
            """, (id1, id2, conv_id))


def embed_fact(fact_id: str, fact_text: str, category: str, collection, model):
    """Embed a fact into the ChromaDB facts collection."""
    embedding = model.encode([fact_text]).tolist()
    collection.add(
        ids=[fact_id],
        embeddings=embedding,
        documents=[fact_text],
        metadatas=[{"fact_id": fact_id, "category": category}],
    )


# ---------------------------------------------------------------------------
# Main Processing Pipeline
# ---------------------------------------------------------------------------

def get_conversations_to_process(conn, limit: int = None, conv_id: str = None,
                                  source_filter: str = None,
                                  retry_errors: bool = False) -> list[dict]:
    """Get list of conversations that haven't been processed yet.
    D-044: Now includes source for scope derivation.
    source_filter: if set, only return conversations from that source (e.g. 'claude_code').
    retry_errors: if True, also include conversations that previously errored (-1 in extraction_log)."""
    if retry_errors and not conv_id:
        # Clear error entries so they're re-processed
        deleted = conn.execute(
            "DELETE FROM extraction_log WHERE facts_extracted = -1"
        ).rowcount
        conn.commit()
        if deleted:
            print(f"  Cleared {deleted} errored extraction_log entries for retry")
    if conv_id:
        rows = conn.execute("""
            SELECT id, title, created_at, message_count, source
            FROM conversations WHERE id = ?
        """, (conv_id,)).fetchall()
    else:
        # Sources that use single-message conversations (text files, journals)
        # are exempt from the minimum message count filter
        single_msg_sources = ('text_file', 'journal')
        if source_filter:
            rows = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.message_count, c.source
                FROM conversations c
                LEFT JOIN extraction_log e ON c.id = e.conversation_id
                WHERE e.conversation_id IS NULL
                  AND (c.message_count >= ? OR c.source IN (?, ?))
                  AND c.source = ?
                ORDER BY c.created_at
            """, (MIN_MESSAGES_FOR_EXTRACTION, *single_msg_sources, source_filter)).fetchall()
        else:
            rows = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.message_count, c.source
                FROM conversations c
                LEFT JOIN extraction_log e ON c.id = e.conversation_id
                WHERE e.conversation_id IS NULL
                  AND (c.message_count >= ? OR c.source IN (?, ?))
                ORDER BY c.created_at
            """, (MIN_MESSAGES_FOR_EXTRACTION, *single_msg_sources)).fetchall()

    if limit:
        rows = rows[:limit]

    return [
        {"id": r[0], "title": r[1] or "Untitled", "created_at": r[2],
         "message_count": r[3], "source": r[4] or "unknown"}
        for r in rows
    ]


def get_conversation_messages(conn, conv_id: str) -> list[dict]:
    """Get messages for a conversation, ordered by sequence."""
    rows = conn.execute("""
        SELECT role, content_text
        FROM messages
        WHERE conversation_id = ?
          AND role IN ('user', 'assistant')
          AND content_text IS NOT NULL
          AND LENGTH(content_text) > 5
        ORDER BY sequence_order
    """, (conv_id,)).fetchall()

    return [{"role": r[0], "text": r[1]} for r in rows]


def process_conversation(conv: dict, conn, fact_collection, embed_model,
                         corrections=None, identity_only: bool = False,
                         document_mode: bool = False) -> int:
    """
    Process a single conversation through the full extraction pipeline.
    Returns the number of facts stored.

    D-044: Derives scope from conversation source via SCOPE_SOURCE_MAPPING.
    identity_only: if True, uses specialized identity extraction prompt for
    project-scope conversations (extracts who you ARE, not what you're building).
    document_mode: if True, treats text as a document corpus and extracts
    the document's implicit worldview (S68 — patents, papers, reports).
    """
    conv_id = conv["id"]
    conv_title = conv["title"]
    conv_source = conv.get("source", "unknown")

    # D-044: Derive scope from conversation source
    scope = SCOPE_SOURCE_MAPPING.get(conv_source, DEFAULT_SCOPE)
    # identity_only mode: extract personal facts from project conversations
    if identity_only:
        scope = "personal"

    # Get messages
    messages = get_conversation_messages(conn, conv_id)
    if len(messages) < 1:
        # Log as processed so we don't re-try
        conn.execute("""
            INSERT OR REPLACE INTO extraction_log (conversation_id, facts_extracted, processed_at)
            VALUES (?, 0, ?)
        """, (conv_id, time.time()))
        conn.commit()
        return 0

    # Step 1: Extract candidate facts
    # D-048: Use identity extraction prompt for project conversations in identity_only mode
    # S68: Use document extraction prompt for document corpora (patents, papers)
    if identity_only:
        candidates = extract_identity_from_project_conversation(conv_id, conv_title, messages)
    elif document_mode:
        candidates = extract_facts_from_conversation(conv_id, conv_title, messages,
                                                      document_mode=True)
    else:
        candidates = extract_facts_from_conversation(conv_id, conv_title, messages)
    if not candidates:
        # Log as processed even with 0 facts so we don't re-try
        conn.execute("""
            INSERT OR REPLACE INTO extraction_log (conversation_id, facts_extracted, processed_at)
            VALUES (?, 0, ?)
        """, (conv_id, time.time()))
        conn.commit()
        return 0

    # Step 2-3: For each candidate, check similarity and make AUDN decision
    stored_fact_ids = []
    stats = {"ADD": 0, "UPDATE": 0, "DELETE": 0, "NOOP": 0, "ERROR": 0, "BLOCKED": 0}

    for candidate in candidates:
        fact_text = candidate["fact"]
        category = candidate["category"]
        confidence = candidate["confidence"]
        # D-022: New fields
        subject = candidate.get("subject", "user")
        intent = candidate.get("intent", "does")
        temporal = candidate.get("temporal", "unknown")
        raw_llm_conf = candidate.get("raw_llm_confidence")
        fact_cls = candidate.get("fact_class", "unclassified")
        k_tier = candidate.get("knowledge_tier", "untiered")
        tier_source = EXTRACTION_BACKEND if k_tier != "untiered" else None
        # D-056 Tier 2: Structured fields
        predicate = candidate.get("predicate")
        object_text = candidate.get("object_text")
        qualifier = candidate.get("qualifier")

        # D-021: Check against user corrections before proceeding
        if corrections and check_against_corrections(fact_text, corrections):
            stats["BLOCKED"] += 1
            continue

        # Find similar existing facts (pass embed_model to avoid reloads)
        similar = find_similar_facts(fact_text, fact_collection, embed_model)

        # Make AUDN decision
        decision = make_audn_decision(fact_text, similar)
        action = decision.get("action", "ADD")

        if action == "ADD":
            fact_id = store_fact(conn, fact_text, category, confidence, conv_id, "ADD",
                                subject=subject, intent=intent, temporal=temporal,
                                raw_llm_confidence=raw_llm_conf, fact_class=fact_cls,
                                knowledge_tier=k_tier, tiered_by=tier_source,
                                scope=scope,
                                predicate=predicate, object_text=object_text,
                                qualifier=qualifier)
            if embed_model and fact_collection:
                embed_fact(fact_id, fact_text, category, fact_collection, embed_model)
            stored_fact_ids.append(fact_id)
            stats["ADD"] += 1

        elif action == "UPDATE":
            updated_text = decision.get("updated_fact", fact_text)
            # Find the existing fact to supersede
            supersedes_id = None
            if similar:
                best_match = max(similar, key=lambda x: x["similarity"])
                supersedes_id = best_match.get("fact_id")

            fact_id = store_fact(conn, updated_text, category, confidence,
                               conv_id, "UPDATE", supersedes_id,
                               subject=subject, intent=intent, temporal=temporal,
                               raw_llm_confidence=raw_llm_conf, fact_class=fact_cls,
                               knowledge_tier=k_tier, tiered_by=tier_source,
                               scope=scope,
                               predicate=predicate, object_text=object_text,
                               qualifier=qualifier)
            if embed_model and fact_collection:
                embed_fact(fact_id, updated_text, category, fact_collection, embed_model)
            stored_fact_ids.append(fact_id)
            stats["UPDATE"] += 1

        elif action == "DELETE":
            # Mark the contradicted fact as superseded
            if similar:
                best_match = max(similar, key=lambda x: x["similarity"])
                supersedes_id = best_match.get("fact_id")
                if supersedes_id:
                    conn.execute("""
                        UPDATE memory_facts SET superseded_by = 'CONTRADICTED', updated_at = ?
                        WHERE id = ?
                    """, (time.time(), supersedes_id))
            stats["DELETE"] += 1

        elif action == "NOOP":
            stats["NOOP"] += 1

        else:
            stats["ERROR"] += 1

    # Step 4: Link co-occurring facts (D-013)
    if len(stored_fact_ids) >= 2:
        link_facts(conn, stored_fact_ids, conv_id)

    # Log completion
    conn.execute("""
        INSERT OR REPLACE INTO extraction_log (conversation_id, facts_extracted, processed_at)
        VALUES (?, ?, ?)
    """, (conv_id, stats["ADD"] + stats["UPDATE"], time.time()))

    conn.commit()
    return stats["ADD"] + stats["UPDATE"]


def run_extraction(limit: int = None, conv_id: str = None,
                    identity_only: bool = False, source_filter: str = None,
                    retry_errors: bool = False, document_mode: bool = False):
    """Main extraction pipeline.
    D-048: identity_only mode extracts personal identity facts from project conversations.
    S68: document_mode treats text as document corpus (patents, papers, reports).
    source_filter: restrict to conversations from a specific source (e.g. 'claude_code').
    retry_errors: clear errored entries and re-process those conversations."""
    if document_mode:
        mode_label = "Document Corpus Extraction (S68)"
    elif identity_only:
        mode_label = "Identity Extraction (D-048)"
    else:
        mode_label = "Fact Extraction (AUDN Pipeline)"
    print("=" * 60)
    print(f"Step 2: Extract — {mode_label}")
    model_display = EXTRACTION_API_MODEL if EXTRACTION_BACKEND == "anthropic" else LLM_MODEL
    print(f"Model: {model_display}")
    print(f"Similarity threshold: {SIMILARITY_THRESHOLD}")
    if source_filter:
        print(f"Source filter: {source_filter}")
    if identity_only:
        print("Mode: IDENTITY-ONLY — extracting personal traits from project conversations")
    if document_mode:
        print("Mode: DOCUMENT — extracting implicit worldview from document corpus")
    # Session 55 (Plan 2): Show extraction cap tiers
    print(f"Extraction caps: {len(EXTRACTION_CAPS['tiers'])} tiers, "
          f"ceiling {EXTRACTION_CAPS['max_facts_ceiling']} facts")
    print("=" * 60)

    # Setup
    create_tables()

    with contextlib.closing(get_db()) as conn:
        # D-056 Tier 2: Ensure structured columns exist (safe migration)
        _ensure_structured_columns(conn)
        conn.commit()
        # Load embedding model and create facts collection
        print("\nLoading embedding model...")
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            embed_model = SentenceTransformer(EMBEDDING_MODEL)
            client = chromadb.PersistentClient(path=str(VECTORS_DIR))

            # Create or get facts collection
            try:
                fact_collection = client.get_collection("memory_facts")
                print(f"  Existing facts collection: {fact_collection.count()} facts")
            except Exception:
                fact_collection = client.create_collection(
                    name="memory_facts",
                    metadata={"description": "Extracted personal facts (AUDN pipeline)", "hnsw:space": "cosine"}
                )
                print("  Created new memory_facts collection")

        except ImportError:
            print("  WARNING: chromadb/sentence-transformers not available. Running without embeddings.")
            embed_model = None
            fact_collection = None

        # Get conversations to process
        # D-048: identity_only mode uses source_filter to target project conversations
        effective_source = source_filter
        if identity_only and not effective_source:
            effective_source = "claude_code"  # Default: extract identity from Claude Code sessions
        conversations = get_conversations_to_process(conn, limit=limit, conv_id=conv_id,
                                                      source_filter=effective_source,
                                                      retry_errors=retry_errors)
        total = len(conversations)

        if total == 0:
            print("\nNo conversations to process (all already done, or none found).")
            return

        # D-021: Load user corrections to guard against re-extracting wrong facts
        corrections = load_corrections(conn)
        if corrections:
            pattern_count = sum(len(c["patterns"]) for c in corrections)
            print(f"  Loaded {len(corrections)} corrections ({pattern_count} block patterns)")

        print(f"\nProcessing {total} conversations...")
        if limit:
            print(f"  (limited to {limit})")

        # Process
        start_time = time.time()
        total_facts = 0
        errors = 0

        for i, conv in enumerate(conversations):
            try:
                facts_stored = process_conversation(conv, conn, fact_collection, embed_model,
                                                    corrections=corrections,
                                                    identity_only=identity_only,
                                                    document_mode=document_mode)
                total_facts += facts_stored

                # Progress update
                if (i + 1) % BATCH_SIZE == 0 or i == total - 1:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    eta = (total - i - 1) / rate if rate > 0 else 0

                    print(
                        f"  [{i+1}/{total}] "
                        f"{rate:.1f} convos/sec | "
                        f"Facts: {total_facts} | "
                        f"Errors: {errors} | "
                        f"ETA: {eta:.0f}s"
                    )

            except Exception as e:
                errors += 1
                print(f"  ERROR on conversation '{conv['title'][:40]}': {e}")
                # Log the error but continue
                conn.execute("""
                    INSERT OR REPLACE INTO extraction_log
                    (conversation_id, facts_extracted, processed_at)
                    VALUES (?, -1, ?)
                """, (conv["id"], time.time()))
                conn.commit()

        # Database maintenance before final stats
        print("Running database maintenance...")
        conn.execute("ANALYZE")

        # Final stats
        total_time = time.time() - start_time

        print(f"\n{'=' * 60}")
        print("Extraction Complete")
        print(f"{'=' * 60}")
        print(f"Conversations processed: {total}")
        print(f"Facts stored: {total_facts}")
        print(f"Errors: {errors}")
        print(f"Time: {total_time:.1f}s ({total_time/60:.1f} min)")
        if total > 0:
            print(f"Average: {total_facts/total:.1f} facts per conversation")
            print(f"Rate: {total/total_time:.2f} conversations/second")


def show_stats():
    """Show current extraction statistics."""
    with contextlib.closing(get_db()) as conn:
        # Check if tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

        print("=" * 60)
        print("Fact Extraction Statistics")
        print("=" * 60)

        if "memory_facts" not in table_names:
            print("\nNo facts extracted yet (memory_facts table doesn't exist).")
            return

        # Total facts
        total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        superseded = total - active

        # User-corrected facts
        user_corrected = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE source = 'user_correction' AND superseded_by IS NULL"
        ).fetchone()[0]

        print(f"\nFacts: {total} total ({active} active, {superseded} superseded, {user_corrected} user-corrected)")

        # Corrections
        if "user_corrections" in table_names:
            corrections = conn.execute("SELECT COUNT(*) FROM user_corrections").fetchone()[0]
            print(f"User corrections stored: {corrections}")

        # By category
        categories = conn.execute("""
            SELECT category, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY category
            ORDER BY cnt DESC
        """).fetchall()

        if categories:
            print(f"\nBy category:")
            for cat, count in categories:
                print(f"  {cat or 'unknown':<15} {count:>5}")

        # Confidence distribution
        high = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE confidence >= 0.8 AND superseded_by IS NULL"
        ).fetchone()[0]
        medium = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE confidence >= 0.5 AND confidence < 0.8 AND superseded_by IS NULL"
        ).fetchone()[0]
        low = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE confidence < 0.5 AND superseded_by IS NULL"
        ).fetchone()[0]

        print(f"\nConfidence levels:")
        print(f"  High (0.8+):    {high}")
        print(f"  Medium (0.5-0.8): {medium}")
        print(f"  Low (<0.5):     {low}")

        # D-022: Subject distribution (entity resolution check)
        subjects = conn.execute("""
            SELECT COALESCE(subject, 'user') as subj, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY subj
            ORDER BY cnt DESC
        """).fetchall()
        if subjects:
            print(f"\nBy subject (who is the fact about):")
            for subj, count in subjects:
                print(f"  {subj or 'user':<20} {count:>5}")

        # D-022: Intent distribution
        intents = conn.execute("""
            SELECT COALESCE(intent, 'does') as int_val, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY int_val
            ORDER BY cnt DESC
        """).fetchall()
        if intents:
            print(f"\nBy intent (relationship to fact):")
            for intent_val, count in intents:
                print(f"  {intent_val or 'does':<20} {count:>5}")

        # D-039: Knowledge tier distribution
        tiers = conn.execute("""
            SELECT COALESCE(knowledge_tier, 'untiered') as kt, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY kt
            ORDER BY cnt DESC
        """).fetchall()
        if tiers:
            print(f"\nBy knowledge tier (D-039):")
            for tier_val, count in tiers:
                print(f"  {tier_val:<20} {count:>5}")

        # D-022: Temporal distribution
        temporals = conn.execute("""
            SELECT COALESCE(temporal_state, 'unknown') as temp, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY temp
            ORDER BY cnt DESC
        """).fetchall()
        if temporals:
            print(f"\nBy temporal state:")
            for temp, count in temporals:
                print(f"  {temp or 'unknown':<20} {count:>5}")

        # Fact class distribution (temporal processing)
        fact_classes = conn.execute("""
            SELECT COALESCE(fact_class, 'unclassified') as fc, COUNT(*) as cnt
            FROM memory_facts
            WHERE superseded_by IS NULL
            GROUP BY fc
            ORDER BY cnt DESC
        """).fetchall()
        if fact_classes:
            print(f"\nBy fact class (temporal processing):")
            for fc, count in fact_classes:
                print(f"  {fc or 'unclassified':<20} {count:>5}")

        # D-022: Raw vs computed confidence comparison
        raw_high = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE raw_llm_confidence >= 0.8 AND superseded_by IS NULL AND raw_llm_confidence IS NOT NULL"
        ).fetchone()[0]
        if raw_high > 0:
            print(f"\nConfidence redesign check:")
            print(f"  Raw LLM confidence >= 0.8:  {raw_high}")
            print(f"  Computed confidence >= 0.8:  {high}")

        # Relationships
        if "fact_relationships" in table_names:
            rels = conn.execute("SELECT COUNT(*) FROM fact_relationships").fetchone()[0]
            print(f"\nFact relationships: {rels} co-occurrence edges")

        # Extraction progress
        if "extraction_log" in table_names:
            processed = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
            total_convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            remaining = total_convos - processed
            print(f"\nExtraction progress: {processed}/{total_convos} conversations ({remaining} remaining)")

        # Sample facts
        print(f"\nSample active facts:")
        samples = conn.execute("""
            SELECT fact_text, category, confidence
            FROM memory_facts
            WHERE superseded_by IS NULL
            ORDER BY confidence DESC
            LIMIT 10
        """).fetchall()

        for fact, cat, conf in samples:
            print(f"  [{cat:<12} {conf:.1f}] {fact[:80]}")


def main():
    parser = argparse.ArgumentParser(description="Fact Extraction Pipeline (AUDN)")
    parser.add_argument("--limit", type=int, help="Limit number of conversations to process")
    parser.add_argument("--conversation", type=str, help="Process a single conversation by ID")
    parser.add_argument("--stats", action="store_true", help="Show extraction statistics")
    parser.add_argument("--reset", action="store_true",
                        help="Reset extraction log (reprocess all conversations)")
    parser.add_argument("--identity-only", action="store_true",
                        help="D-048: Extract only identity-relevant facts from project conversations "
                             "(strips code/tools, keeps user directives and behavioral patterns)")
    parser.add_argument("--source", type=str, default=None,
                        help="Filter to conversations from a specific source (chatgpt, claude_code, claude_web)")
    parser.add_argument("--document-mode", action="store_true",
                        help="S68: Treat text as document corpus (patents, papers, reports). "
                             "Extracts the document's implicit worldview rather than personal facts.")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Clear errored extraction_log entries (-1) and re-process those conversations")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.reset:
        with contextlib.closing(get_db()) as conn:
            with conn:
                conn.execute("DELETE FROM extraction_log")
                # D-021: Protected reset — only clear extraction-sourced facts
                # User corrections and user-direct facts survive the wipe
                deleted = conn.execute("""
                    DELETE FROM memory_facts
                    WHERE source = 'extraction' OR source IS NULL
                """).rowcount
                conn.execute("DELETE FROM fact_relationships")
            # Show what survived
            survived = conn.execute("""
                SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL
            """).fetchone()[0]

        # D-022: Also clear ChromaDB memory_facts collection (prevent ghost embeddings)
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(VECTORS_DIR))
            try:
                client.delete_collection("memory_facts")
                print("ChromaDB memory_facts collection cleared.")
            except Exception:
                print("ChromaDB memory_facts collection was already empty.")
        except ImportError:
            print("ChromaDB not available — skipping vector cleanup.")

        print(f"Extraction reset: removed {deleted} extracted facts.")
        print(f"Protected: {survived} user-corrected facts survived the reset.")
        print("Extraction log cleared. All conversations will be reprocessed.")
    else:
        run_extraction(limit=args.limit, conv_id=args.conversation,
                       identity_only=args.identity_only, source_filter=args.source,
                       retry_errors=args.retry_errors,
                       document_mode=args.document_mode)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
