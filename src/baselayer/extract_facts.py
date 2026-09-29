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
import contextvars
import sys
import io
import os
import sqlite3
import dataclasses
import json
import time
import uuid
import argparse
import math
import requests
from datetime import datetime

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

# ---------------------------------------------------------------------------
# Shared config — single source of truth (config.py)
# ---------------------------------------------------------------------------
from baselayer.config import (
    PROJECT_ROOT, DATABASE_FILE, VECTORS_DIR, PROGRESS_FILE,
    EMBEDDING_MODEL, OLLAMA_URL, LLM_MODEL,
    EXTRACTION_BATCH_SIZE as BATCH_SIZE,
    SIMILARITY_THRESHOLD, MAX_RETRIES, MIN_FACT_LENGTH,
    MAX_FACTS_PER_CONVERSATION, MIN_MESSAGES_FOR_EXTRACTION,
    VALID_CATEGORIES, VALID_FACT_CLASSES,
    EXTRACTION_BACKEND, EXTRACTION_API_MODEL,
    SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE, CLAUDE_CODE_SOURCES, is_claude_code_source, source_family,
    CONSTRAINED_PREDICATES,
    EXTRACTION_CAPS,
    DYNAMIC_CAP_DEFAULT, CHARS_PER_FACT,
    OUTPUT_SAFE_CHUNK_CAP,
    EXTRACTION_TOKENS_PER_FACT, EXTRACTION_OUTPUT_BUFFER_TOKENS,
    EXTRACTION_MAX_OUTPUT_TOKENS,
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
    Safe to call repeatedly — silently skips if columns already exist.
    Also adds the turn-contract columns, since every extraction entry point
    (sequential and batch) calls this before its first INSERT."""
    for col in ["predicate", "object_text", "qualifier"]:
        try:
            conn.execute(f"ALTER TABLE memory_facts ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
    _ensure_turn_contract_columns(conn)


# Turn-contract columns on memory_facts (docs/core/TURN_CONTRACT.md §4, §7).
# Added by ALTER on an existing database; a fresh one gets them from
# init_database. NULL on every fact extracted before the contract.
TURN_CONTRACT_COLUMNS = (
    ("source_turn_id", "TEXT"),
    ("evidence_spans", "TEXT"),
    ("inferred", "INTEGER"),
    ("voice_class", "TEXT"),
    ("turn_contract_version", "TEXT"),
    ("extraction_model", "TEXT"),
    ("extraction_prompt_hash", "TEXT"),
    ("git_commit", "TEXT"),
    ("code_path", "TEXT"),
    ("practice", "TEXT"),
    ("grounding", "TEXT"),
)


def fact_practice(conn, evidence_spans):
    """The practice a gated fact is bounded to, read from the turns its spans cite.

    The tag when every cited turn carries the same one; NULL when none carries one; the
    sorted tags joined by `+` when they differ (an untagged turn counts as `general`), so a
    fact resting on two practices is not bounded to either. Read-only; returns NULL on a
    database without the turn table or its `practice` column, and for no spans."""
    if isinstance(evidence_spans, str):
        try:
            evidence_spans = json.loads(evidence_spans)
        except ValueError:
            return None
    ids = [s.get("turn_id") for s in (evidence_spans or []) if isinstance(s, dict)]
    ids = [t for t in dict.fromkeys(ids) if t]
    if not ids:
        return None
    cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
    if "practice" not in cols:
        return None
    q = ",".join("?" * len(ids))
    got = dict(conn.execute(f"SELECT turn_id, practice FROM turns WHERE turn_id IN ({q})", ids).fetchall())
    tags = {got.get(t) for t in ids}
    if tags == {None}:
        return None
    if len(tags) == 1:
        return tags.pop()
    return "+".join(sorted(t or "general" for t in tags))


def _ensure_turn_contract_columns(conn):
    """Add the turn-contract columns if missing. Idempotent; checks the table's
    actual columns rather than swallowing every OperationalError, so a real
    failure (a locked or read-only database) is not mistaken for 'exists'."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(memory_facts)")}
    for col, typ in TURN_CONTRACT_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE memory_facts ADD COLUMN {col} {typ}")


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


# Set for the duration of a batch submit/process that runs in turn mode without
# the BASELAYER_TURN_CONTRACT env var (the batch mode can come from its state
# file or an explicit argument). Read only by _dynamic_cap_enabled.
_TURN_MODE_ACTIVE = contextvars.ContextVar("baselayer_turn_mode_active", default=False)


def _dynamic_cap_enabled() -> bool:
    """B-halt dynamic fact cap gate (default OFF on the legacy path, ON in turn mode).

    Turn mode (D-108): the static tiers halt a dense conversation rather than
    trim gated facts, so the density backstop is the turn path's default. An
    explicit BASELAYER_DYNAMIC_CAP value (including 0) always wins.

    Read at call time (never cached at import) so tests and callers can toggle
    BASELAYER_DYNAMIC_CAP within a process — mirrors the inline env pattern used
    by the S98 coverage gate (BASELAYER_SKIP_COVERAGE_GATE). When the env var is
    unset, falls back to the config mirror DYNAMIC_CAP_DEFAULT (False), so the
    default path stays byte-for-byte identical to the static-cap pipeline.

    Truthy env values (case-insensitive): 1, true, yes, on.
    """
    raw = os.environ.get("BASELAYER_DYNAMIC_CAP")
    if raw is None:
        if _turn_contract_enabled() or _TURN_MODE_ACTIVE.get():
            return True
        return bool(DYNAMIC_CAP_DEFAULT)
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _extraction_max_tokens(fact_count: int) -> int:
    """B-halt output-token budget that fits a `fact_count`-fact extraction ask.

    ~EXTRACTION_TOKENS_PER_FACT tokens/fact + a JSON-wrapping buffer, floored at
    the legacy 2000 and clamped to the extraction model's documented max output
    tokens. Used ONLY on the flag-on chunk path so a large per-chunk ask does not
    overflow the fixed ~10K ceiling call_anthropic derives from prompt length
    (which truncates the JSON and silently loses the whole chunk). The flag-off
    path passes max_tokens=None and keeps that prompt-length heuristic untouched.
    """
    scaled = fact_count * EXTRACTION_TOKENS_PER_FACT + EXTRACTION_OUTPUT_BUFFER_TOKENS
    return min(EXTRACTION_MAX_OUTPUT_TOKENS, max(2000, scaled))


def _get_extraction_caps(message_count: int, total_chars: int = 0,
                          source: str = None) -> dict:
    """Determine extraction caps based on message count AND total character length.

    Session 55 (Plan 2): Scales extraction limits with conversation length.
    Session 65: Added char-based tiers for long single-message imports
    (autobiographies, chapters). Returns whichever tier gives higher max_facts.
    2026-05-17: Per-source max_facts override. Dense multi-day sources
    (claude_code) lift the per-conversation cap so AUDN dedup, not a tier cap,
    is what decides redundancy.

    Args:
        message_count: Number of messages in the conversation.
        total_chars: Total character count across all messages. 0 = skip char lookup.
        source: Conversation source (e.g. "claude_code"). Used to apply per-source
            max_facts overrides from EXTRACTION_CAPS["max_facts_ceiling_by_source"].

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
                    msg_caps = {
                        "max_facts": tier["max_facts"],
                        "input_char_budget": tier["input_char_budget"],
                    }
                break

    # Per-source override (2026-05-17): raise max_facts ceiling for dense sources
    # so the per-conversation cap is not what bounds extraction. AUDN dedup is.
    overrides = EXTRACTION_CAPS.get("max_facts_ceiling_by_source", {})

    # B-halt (flag ON, default OFF): demote the doc-level cap to a density-derived
    # runaway backstop — max_facts = min(source_ceiling, ceil(total_chars / CHARS_PER_FACT)).
    # Only input_char_budget (chunk-sizing) is left untouched. The total_chars == 0
    # fallback is load-bearing: callers pass total_chars=0 (identity path, some batch
    # callers), and ceil(0/N)=0 would otherwise zero out max_facts. In that case we
    # keep today's tier/override value.
    source = source_family(source)
    if _dynamic_cap_enabled() and total_chars > 0:
        ceiling = overrides.get(source, EXTRACTION_CAPS.get("max_facts_ceiling", 600))
        msg_caps["max_facts"] = min(ceiling, math.ceil(total_chars / CHARS_PER_FACT))
    else:
        # Flag OFF, or flag ON with total_chars == 0: unchanged per-source override.
        if source and source in overrides:
            msg_caps["max_facts"] = max(msg_caps["max_facts"], overrides[source])

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

        _ensure_turn_contract_columns(conn)
        conn.commit()

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


class ExtractionResponseError(Exception):
    """A model response that cannot yield facts for a structural reason.

    `reason` is one of "refusal", "max_tokens" or "no_text". These are not
    transient: retrying a refusal or a truncated answer returns the same thing,
    so callers count them instead of retrying them into a silent None.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# Per-process tally of structural response failures, read into the run record.
# A chunk that returns None is otherwise indistinguishable from a chunk with no
# facts, which is how a truncated JSON response used to vanish without trace.
_RESPONSE_FAILURES: dict = {}


def reset_response_failures():
    _RESPONSE_FAILURES.clear()


def response_failures() -> dict:
    return dict(_RESPONSE_FAILURES)


def _count_response_failure(reason: str):
    _RESPONSE_FAILURES[reason] = _RESPONSE_FAILURES.get(reason, 0) + 1


# MEASURED API usage, one entry per billed call, so a run can be priced from what it actually
# used rather than from a characters-per-token guess. Appended the moment a response exists,
# BEFORE it is parsed: a truncated or refused response is billed and discarded, and it must
# still count. Same lifecycle as _RESPONSE_FAILURES (reset at run start, copied at the end).
_USAGE_CALLS: list = []
_CURRENT_CONVERSATION = contextvars.ContextVar("baselayer_current_conversation", default=None)
# The chunk an extraction call is for: {"chunk": index, "citable_chars": n}. Carried into
# the call's usage entry so output per citable char can be re-derived from any run.
_CURRENT_CHUNK = contextvars.ContextVar("baselayer_current_chunk", default=None)
# Set by the turn path around its extraction calls: a max_tokens stop is raised to the
# caller (which re-chunks) instead of being counted and turned into None here.
_RAISE_MAX_TOKENS = contextvars.ContextVar("baselayer_raise_max_tokens", default=False)


def reset_usage():
    _USAGE_CALLS.clear()


class SpendCeilingExceeded(SystemExit):
    """A call would take measured spend past BASELAYER_SPEND_CEILING_USD. A SystemExit so
    that no per-conversation `except Exception` absorbs it: the run stops, and its record
    is still written from the loop's `finally`."""


def spend_ceiling_usd():
    raw = os.environ.get("BASELAYER_SPEND_CEILING_USD")
    return float(raw) if raw not in (None, "") else None


def measured_spend_usd(calls=None) -> float:
    from baselayer.config import SPEND_RATES_PER_MTOK as R
    t = _tc.usage_totals(_USAGE_CALLS if calls is None else calls)
    return (t["input_tokens"] * R["input"] + t["output_tokens"] * R["output"]
            + t["cache_read_input_tokens"] * R["cache_read"]
            + t["cache_creation_input_tokens"] * R["cache_write"]) / 1e6


def check_spend_ceiling(prompt_chars: int, max_tokens: int):
    """Refuse a call whose worst case would take measured spend past the ceiling."""
    ceiling = spend_ceiling_usd()
    if ceiling is None:
        return
    from baselayer.config import SPEND_CHARS_PER_TOKEN, SPEND_RATES_PER_MTOK as R
    spent = measured_spend_usd()
    worst = (prompt_chars / SPEND_CHARS_PER_TOKEN * R["input"] + max_tokens * R["output"]) / 1e6
    if spent + worst > ceiling:
        raise SpendCeilingExceeded(
            f"spend ceiling ${ceiling:.4f}: measured ${spent:.4f} plus this call's worst case "
            f"${worst:.4f} would pass it; stopping before the call")


def usage_calls() -> list:
    return list(_USAGE_CALLS)


def _record_usage(response, purpose: str):
    chunk = _CURRENT_CHUNK.get() if purpose == "extract" else None
    _USAGE_CALLS.append(_tc.usage_entry(
        getattr(response, "usage", None), purpose=purpose, model=EXTRACTION_API_MODEL, batch=False,
        conversation_id=_CURRENT_CONVERSATION.get(), at=time.time(), **(chunk or {})))


def response_text(response) -> str:
    """Return the concatenated text blocks of a Messages API response.

    Reads blocks by TYPE, never by position. On a 5-generation model with
    thinking on, content[0] is a thinking block, so `content[0].text` raises or
    reads the wrong block. Raises ExtractionResponseError on a refusal, a
    max_tokens stop (the JSON is truncated and unparseable), or no text at all.
    """
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise ExtractionResponseError("refusal")
    if stop == "max_tokens":
        raise ExtractionResponseError("max_tokens")
    parts = [getattr(b, "text", "") for b in (getattr(response, "content", None) or [])
             if getattr(b, "type", None) == "text"]
    text = "".join(parts).strip()
    if not text:
        raise ExtractionResponseError("no_text")
    return text


def _strip_json_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _get_anthropic_client():
    """Lazy-initialize and reuse a single Anthropic client instance."""
    global _anthropic_client
    if _anthropic_client is None:
        from baselayer.llm_provider import get_anthropic_client
        _anthropic_client = get_anthropic_client()
    return _anthropic_client


def json_instruction_for(schema: dict = None) -> str:
    """The instruction prepended to every extraction prompt. Shared by the
    sequential path, the batch path and the prompt hash, so the three cannot
    drift apart."""
    text = "Respond with ONLY valid JSON matching this schema. No explanation, no markdown fences.\n"
    if schema:
        text += f"Schema: {json.dumps(schema, indent=2)}\n\n"
    return text


def call_anthropic(prompt: str, schema: dict = None, retries: int = MAX_RETRIES,
                    max_tokens: int = None) -> dict:
    """
    Call Anthropic API (Haiku/Sonnet) for fact extraction.
    Alternative to local Ollama for users without GPU or Qwen.
    Returns parsed JSON dict, same interface as call_ollama.

    max_tokens scales dynamically with extraction request size.
    """
    client = _get_anthropic_client()
    json_instruction = json_instruction_for(schema)

    # Dynamic output tokens: estimate from prompt length if not specified
    if max_tokens is None:
        # ~150 tokens per fact, estimate facts from prompt length
        prompt_len = len(prompt)
        estimated_facts = min(50, max(10, prompt_len // 500))
        max_tokens = max(2000, estimated_facts * 200)

    for attempt in range(retries + 1):
        # Outside the try: a refusal here must stop the run, not be retried or swallowed.
        check_spend_ceiling(len(json_instruction) + len(prompt), max_tokens)
        try:
            response = client.messages.create(
                model=EXTRACTION_API_MODEL,
                max_tokens=max_tokens,
                temperature=0.1,
                messages=[{"role": "user", "content": json_instruction + prompt}],
            )
            _record_usage(response, "audn" if schema is AUDN_SCHEMA else "extract")
            raw = _strip_json_fences(response_text(response))

            result = json.loads(raw)
            return result

        except ExtractionResponseError as e:
            if e.reason == "max_tokens" and _RAISE_MAX_TOKENS.get():
                raise                       # the turn path re-chunks; it counts the outcome
            # Structural, not transient: count it and stop. Retrying a refusal
            # or a max_tokens truncation spends money and returns the same thing.
            _count_response_failure(e.reason)
            print(f"  WARNING: extraction response unusable ({e.reason})")
            return None

        except json.JSONDecodeError:
            if attempt >= retries:
                _count_response_failure("json_decode")
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


def call_llm(prompt: str, schema: dict = None, retries: int = MAX_RETRIES,
             max_tokens: int = None) -> dict:
    """Dispatch to configured backend (ollama or anthropic).

    max_tokens (B-halt): when provided, forwarded to call_anthropic to size the
    output-token budget to the extraction ask. None (the default, and every
    flag-off caller) preserves call_anthropic's prompt-length heuristic exactly.
    call_ollama uses a fixed num_predict and ignores it.
    """
    if EXTRACTION_BACKEND == "anthropic":
        return call_anthropic(prompt, schema, retries, max_tokens=max_tokens)
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
                                     max_facts: int = MAX_FACTS_PER_CONVERSATION,
                                     chunk_info: str = None) -> str:
    """Build the identity-focused extraction prompt for project conversations (D-048).

    Factored out for reuse by batch_extract.py.
    Session 55: Added relationship guidance and dynamic max_facts cap.
    2026-05-17: chunk_info for multi-window extraction of long project conversations.
    """
    predicates_str = ", ".join(CONSTRAINED_PREDICATES)

    # Session 55 (Plan 1): Load known entities to prime relationship extraction
    entity_hints = _get_known_entities_for_prompt()

    chunk_context = f"\n<chunk_context>{chunk_info}</chunk_context>\n" if chunk_info else ""

    return f"""You are extracting PERSONAL IDENTITY facts from a technical project conversation between a user and an AI coding assistant.
{chunk_context}
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
                                  max_facts: int = None,
                                  drop_counter: dict = None,
                                  uncapped: bool = False) -> list[dict]:
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
        uncapped: truncate nothing (turn path, fact_count_mode `none`). max_facts=None
                  does NOT mean uncapped: it means the legacy default.

    Returns:
        List of validated, normalized fact dicts.
    """
    # Session 55 (Plan 2): Use dynamic cap if provided, else legacy default
    effective_cap = max_facts if max_facts is not None else MAX_FACTS_PER_CONVERSATION

    # drop_counter (turn path): every fact removed here is counted by reason, so
    # post-gate losses are visible in the run record instead of vanishing.
    drops = drop_counter if drop_counter is not None else {}

    def _drop(reason):
        drops[reason] = drops.get(reason, 0) + 1

    if uncapped:
        effective_cap = len(raw_facts)
    if len(raw_facts) > effective_cap:
        drops["over_per_chunk_cap"] = drops.get("over_per_chunk_cap", 0) + len(raw_facts) - effective_cap

    valid_facts = []
    for fact in raw_facts[:effective_cap]:
        raw_confidence = fact.get("confidence", 0.5)
        if raw_confidence < 0.3:
            _drop("low_confidence")
            continue

        # Extract structured fields
        raw_subject = fact.get("subject", "user")
        raw_predicate = fact.get("predicate", "")
        raw_object = fact.get("object", "").strip()
        raw_qualifier = fact.get("qualifier", "unknown")

        if not raw_object or len(raw_object) < 3:
            _drop("short_object")
            continue

        # Normalize
        subject = normalize_subject(raw_subject)
        predicate = normalize_predicate(raw_predicate)
        temporal = normalize_temporal(fact.get("temporal", "unknown"))
        intent = _predicate_to_intent(predicate)

        # Reconstruct fact_text for downstream compatibility
        fact_text = reconstruct_fact_text(subject, predicate, raw_object)

        if len(fact_text) < MIN_FACT_LENGTH:
            _drop("short_fact")
            continue

        # D-048: Contamination filter for identity extraction from project conversations
        if identity_only:
            fact_lower = fact_text.lower()
            if any(kw in fact_lower for kw in _IDENTITY_CONTAMINATION_KEYWORDS):
                _drop("contamination_filter")
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
        # Turn-contract grounding, present only on facts that passed the gate.
        for key in ("source_turn_id", "evidence_spans", "voice_class", "inferred", "grounding"):
            if key in fact:
                valid_facts[-1][key] = fact[key]

    return valid_facts


def _strip_noise_content(text: str, verbose: bool = True) -> str:
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

    if replacements > 0 and verbose:
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

    # Session 65: Chunking path for long texts (e.g., autobiography chapters).
    # 2026-05-17: Also trigger when any single message exceeds budget. Prevents
    # the single-pass path's per-message [:1500] cap from silently dropping
    # content in conversations whose total fits the budget but contain a
    # long-form message.
    max_msg_chars = max((len(m.get("text", "")) for m in messages), default=0)
    if total_chars > input_char_budget or max_msg_chars > input_char_budget:
        # Build full text without per-message truncation
        full_text = ""
        for msg in messages:
            role = msg["role"].capitalize()
            full_text += f"{role}: {msg['text']}\n"

        # Session 68: Strip noise content (genome sequences, hex, etc.) before chunking
        full_text = _strip_noise_content(full_text)

        chunks = _chunk_text_for_extraction(full_text, input_char_budget)
        # B-halt (flag ON): drop the min(50, ...) per-chunk emission-order cut,
        # the biggest leak on dense chunks — let AUDN cull downstream. The ask is
        # still bounded by OUTPUT_SAFE_CHUNK_CAP so a density-scaled max_facts
        # (e.g. 239) does not overflow the output-token ceiling and lose the whole
        # chunk; the DOC cap stays density-scaled and aggregates across chunks.
        # chunk_max_tokens sizes the API output budget to the per-chunk ask.
        # Flag OFF: unchanged min(50, max_facts), heuristic max_tokens (None).
        # (The prior "D-076" comment mis-cited; the per-chunk cap's real decision is D-063.)
        if _dynamic_cap_enabled():
            per_chunk_cap = min(OUTPUT_SAFE_CHUNK_CAP, max_facts)
            chunk_max_tokens = _extraction_max_tokens(per_chunk_cap)
        else:
            per_chunk_cap = min(50, max_facts)
            chunk_max_tokens = None
        all_facts = []

        print(f"  Chunking: {len(full_text):,} chars -> {len(chunks)} chunks (budget {input_char_budget:,}, cap {max_facts})")

        for i, chunk in enumerate(chunks):
            print(f"  Chunk {i+1}/{len(chunks)}: {len(chunk):,} chars", end="", flush=True)
            chunk_info = f"Section {i + 1} of {len(chunks)} from '{conv_title}'. Extract facts from this section."
            if document_mode:
                prompt = build_document_extraction_prompt(conv_title, chunk,
                                                          max_facts=per_chunk_cap,
                                                          chunk_info=chunk_info)
            else:
                prompt = build_extraction_prompt(conv_title, chunk,
                                                 max_facts=per_chunk_cap,
                                                 chunk_info=chunk_info)
            result = call_llm(prompt, schema=schema, max_tokens=chunk_max_tokens)
            if result and "facts" in result:
                validated = validate_structured_response(
                    result["facts"], len(messages), max_facts=per_chunk_cap
                )
                all_facts.extend(validated)
                print(f" -> {len(validated)} facts", flush=True)
            else:
                print(f" -> FAILED (result={type(result).__name__}: {str(result)[:100]})", flush=True)

        # S97: Coverage report — detect underextraction before truncating
        if len(all_facts) > max_facts:
            discarded = len(all_facts) - max_facts
            pct = discarded / len(all_facts) * 100
            if _dynamic_cap_enabled():
                # B-halt: max_facts is a density-derived runaway backstop, not a
                # trim target. Report the breach as implausible density; below the
                # gate the facts are kept and handed to AUDN, not discarded.
                print(f"\n  DENSITY WARNING: {len(all_facts)} facts for {len(full_text):,} chars, backstop is {max_facts}.")
                print(f"  {pct:.0f}% over the implausible-density backstop.\n")
            else:
                print(f"\n  COVERAGE WARNING: {len(all_facts)} facts extracted, cap is {max_facts}.")
                print(f"  {discarded} facts ({pct:.0f}%) will be discarded.")
                print(f"  Consider raising max_facts_ceiling or splitting into chapters.\n")

            # S98 Phase 3A: Coverage discard gate — HARD BLOCK if >20% over cap.
            # Kept a hard block under both flag states (do NOT downgrade to a
            # warning). Overridable by BASELAYER_SKIP_COVERAGE_GATE.
            if pct > 20 and not os.environ.get("BASELAYER_SKIP_COVERAGE_GATE"):
                if _dynamic_cap_enabled():
                    print(f"  COVERAGE GATE: {pct:.0f}% implies implausibly many facts for input size.")
                    print(f"  Pipeline halted rather than trimming voice-bearing facts.")
                    print(f"  Options: raise CHARS_PER_FACT / max_facts_ceiling, split the file, or set BASELAYER_SKIP_COVERAGE_GATE=1")
                else:
                    print(f"  COVERAGE GATE: {pct:.0f}% discard rate exceeds 20% threshold.")
                    print(f"  Pipeline blocked to prevent silent data loss.")
                    print(f"  Options: raise max_facts_ceiling, split into smaller files, or set BASELAYER_SKIP_COVERAGE_GATE=1")
                raise SystemExit(1)

        # B-halt (flag ON): no silent confidence-sort truncation. Below the gate
        # threshold every fact passes to AUDN, which culls by cosine-to-corpus.
        if _dynamic_cap_enabled():
            return all_facts
        # Flag OFF (unchanged): apply overall max_facts cap, sorting by confidence
        # to keep best, not first.
        if len(all_facts) > max_facts:
            all_facts.sort(key=lambda f: f.get("confidence", 0.5), reverse=True)
        return all_facts[:max_facts]

    # Standard single-pass path (short conversations).
    # 2026-05-17: Per-message [:1500] cap removed. The chunking trigger above
    # now handles single-long-message cases, so any message that arrives here
    # is already bounded by the conversation-level budget.
    conv_text = ""
    for msg in messages:
        role = msg["role"].capitalize()
        text = msg["text"]
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
    - Keep ALL user messages (these are the identity signal) — full length, no truncation
    - Keep only short assistant messages (<500 chars after stripping) — these are
      summaries, questions, and clarifications that provide conversational context
    - Strip code blocks from all messages
    - Result: a "decision conversation" instead of a coding session

    2026-05-17: Removed per-message user-text cap and budget hard-break. Returns
    the full abstracted text. Callers window via _chunk_text_for_extraction so
    multi-day sessions get multi-pass extraction instead of silent truncation.
    """
    import re

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
            # Keep ALL user content — identity signal lives here.
            # Two trailing newlines so each message is a paragraph boundary;
            # _chunk_text_for_extraction splits on "\n\n" and would otherwise
            # treat the whole abstracted text as a single unsplittable block.
            abstracted += f"User: {text}\n\n"
        else:
            # Only keep short assistant messages (summaries, questions, context).
            # Long assistant turns are intentional D-048 design: the spec is
            # about the user, not Claude's reasoning.
            if len(text) <= 500:
                abstracted += f"Assistant: {text}\n\n"
            else:
                first_line = text.split('\n')[0][:200]
                abstracted += f"Assistant: {first_line} [...]\n\n"

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
    2026-05-17: Multi-window extraction for long project conversations (multi-day
    compacted Claude Code sessions). When abstracted text exceeds input_char_budget,
    the text is split into windows and each window gets its own extraction call.
    AUDN dedups across windows.
    """
    # Session 55 (Plan 2): Get scaled caps. Source hardcoded to claude_code:
    # this function is only called for project conversations, and the per-source
    # override lifts the per-conv cap so dense multi-day sessions don't trip
    # the coverage gate.
    caps = _get_extraction_caps(len(messages), source="claude_code")
    max_facts = caps["max_facts"]
    input_char_budget = caps["input_char_budget"]

    # D-048: Abstract conversation — strip code, keep user directives
    conv_text = _abstract_project_conversation(messages)

    if len(conv_text.strip()) < 100:
        return []  # Not enough content after abstraction

    schema = EXTRACT_SCHEMA_FALLBACK if use_fallback_schema else EXTRACT_SCHEMA

    # Multi-window path: abstracted text exceeds budget
    if len(conv_text) > input_char_budget:
        # No overlap for project conversations: text is turn-bounded, not prose.
        chunks = _chunk_text_for_extraction(conv_text, input_char_budget, overlap=0)
        # B-halt (flag ON): drop the min(50, ...) per-chunk cut, but bound the ask
        # by OUTPUT_SAFE_CHUNK_CAP so it fits the output-token ceiling, and size
        # max_tokens to the ask. Flag OFF: unchanged min(50, max_facts), None.
        if _dynamic_cap_enabled():
            per_chunk_cap = min(OUTPUT_SAFE_CHUNK_CAP, max_facts)
            chunk_max_tokens = _extraction_max_tokens(per_chunk_cap)
        else:
            per_chunk_cap = min(50, max_facts)
            chunk_max_tokens = None
        all_facts = []
        for i, chunk in enumerate(chunks):
            chunk_info = f"Section {i + 1} of {len(chunks)} from '{conv_title}'."
            prompt = build_identity_extraction_prompt(
                conv_title, chunk, max_facts=per_chunk_cap, chunk_info=chunk_info
            )
            result = call_llm(prompt, schema=schema, max_tokens=chunk_max_tokens)
            if result and "facts" in result:
                validated = validate_structured_response(
                    result["facts"], len(messages), identity_only=True, max_facts=per_chunk_cap
                )
                all_facts.extend(validated)

        # B-halt (flag ON): mirror path 1 — a hard coverage gate on breach instead
        # of a silent confidence-sort trim. This path has NO gate today; without
        # one, flag-ON with no trim would silently keep everything (the failure
        # mode the design exists to prevent). Extended here to honor the
        # "halt, don't trim" rationale. (If path 2 should stay uncapped instead,
        # this whole block reduces to `return all_facts`.)
        if _dynamic_cap_enabled():
            if len(all_facts) > max_facts:
                discarded = len(all_facts) - max_facts
                pct = discarded / len(all_facts) * 100
                print(f"\n  DENSITY WARNING: {len(all_facts)} identity facts for {len(conv_text):,} chars, backstop is {max_facts}.")
                print(f"  {pct:.0f}% over the implausible-density backstop.\n")
                if pct > 20 and not os.environ.get("BASELAYER_SKIP_COVERAGE_GATE"):
                    print(f"  COVERAGE GATE: {pct:.0f}% implies implausibly many facts for input size.")
                    print(f"  Pipeline halted rather than trimming voice-bearing facts.")
                    print(f"  Options: raise CHARS_PER_FACT / max_facts_ceiling, split the file, or set BASELAYER_SKIP_COVERAGE_GATE=1")
                    raise SystemExit(1)
            return all_facts
        # Flag OFF (unchanged): apply session-level cap, keeping highest-confidence facts.
        if len(all_facts) > max_facts:
            all_facts.sort(key=lambda f: f.get("confidence", 0.5), reverse=True)
        return all_facts[:max_facts]

    # Single-pass path (short abstracted text)
    prompt = build_identity_extraction_prompt(conv_title, conv_text, max_facts=max_facts)
    result = call_llm(prompt, schema=schema)

    if not result or "facts" not in result:
        return []

    return validate_structured_response(result["facts"], len(messages), identity_only=True,
                                        max_facts=max_facts)


# ---------------------------------------------------------------------------
# Turn-contract extraction (docs/core/TURN_CONTRACT.md)
# ---------------------------------------------------------------------------
#
# Four phases per conversation, and the order is the point:
#   1. LLM phase   extract_turn_chunks      model calls; may fail and be caught
#   2. gate        gate_turn_chunks         pure; NEVER inside an exception handler
#   3. finalize    finalize_turn_facts      validation + density backstop, counted
#   4. store       store_turn_facts         AUDN + INSERT; rolled back on error
# The legacy loop wraps everything in one try whose handler COMMITS, so a gate
# that raised half way through storing would have committed the facts already
# inserted. Here the gate runs before any INSERT and outside every handler.

from baselayer import turn_contract as _tc  # noqa: E402
from baselayer.config import (  # noqa: E402
    TURN_CONTEXT_CHAR_BUDGET, TURN_CONTEXT_MAX_TURNS,
    TURN_CONTAMINATION_FILTER, TURN_EVIDENCE_SPAN_MAX_CHARS, TURN_EVIDENCE_SPAN_MIN_WORDS,
    TURN_EXTRACTION_TOKENS_PER_FACT, TURN_FACT_COUNT_MODE, TURN_FACT_COUNT_MODES,
    TURN_UNCOUNTED_MODES, TURN_COVERAGE_SENTENCE, TURN_COVERAGE_MODES, TURN_FRAGMENT_SENTENCE,
    TURN_OUTPUT_TOKENS_FLOOR, TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR,
)

TURN_CONTRACT_VERSION = _tc.TURN_CONTRACT_VERSION

_TURN_FACT_ITEM = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "predicate": {"type": "string"},
        "object": {"type": "string"},
        "qualifier": {"type": "string"},
        "category": {"type": "string"},
        "temporal": {"type": "string"},
        "confidence": {"type": "number"},
        "inferred": {"type": "boolean"},
        "evidence_spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "turn": {"type": "string"},   # an S<n> label from the prompt
                    "span": {"type": "string"},   # verbatim words from that turn
                },
                "required": ["turn", "span"],
            },
        },
    },
    "required": ["subject", "predicate", "object", "category", "confidence",
                 "inferred", "evidence_spans"],
}

TURN_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": _TURN_FACT_ITEM}},
    "required": ["facts"],
}


def _turn_contract_enabled() -> bool:
    """Turn-contract mode is opt-in and explicit (BASELAYER_TURN_CONTRACT or
    `baselayer extract --turn-contract`). It is never inferred from the turn
    table existing, because a table-name mismatch would then fall back to the
    legacy path and store ungated, unstamped facts while reporting success."""
    raw = os.environ.get("BASELAYER_TURN_CONTRACT")
    return bool(raw) and raw.strip().lower() in ("1", "true", "yes", "on")


def _turn_extraction_max_tokens(fact_count: int) -> int:
    """Output budget for a turn-path ask: sized per fact WITH grounding spans.
    Always explicit on this path, whatever the dynamic-cap flag, because the
    prompt-length heuristic in call_anthropic predates evidence spans."""
    scaled = fact_count * TURN_EXTRACTION_TOKENS_PER_FACT + EXTRACTION_OUTPUT_BUFFER_TOKENS
    return min(EXTRACTION_MAX_OUTPUT_TOKENS, max(2000, scaled))


def turn_output_budget(citable_chars: int) -> int:
    """max_tokens for one chunk in fact_count_mode `none`, from its citable characters
    (config TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR, where the derivation is written)."""
    scaled = math.ceil(TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR * max(0, citable_chars))
    return min(EXTRACTION_MAX_OUTPUT_TOKENS, max(TURN_OUTPUT_TOKENS_FLOOR, scaled))


def turn_chunk_max_tokens(chunk, plan: dict) -> int:
    """The output budget for one chunk: from the fact count when capped, from the chunk's
    citable characters when the prompt carries no count."""
    if uncounted_mode(plan.get("fact_count_mode")):
        return turn_output_budget(chunk.citable_chars)
    return plan["max_tokens"]


def _abstract_noncitable_project_text(text: str) -> str:
    """The D-048 rule for Claude Code sessions, applied to NON-CITABLE turns
    only: strip code, tool blocks and diff lines; keep a short turn whole and a
    long one as its first line. Same treatment the legacy abstraction gave
    assistant turns, so the context a model sees is unchanged in kind."""
    import re
    text = re.sub(r'```[\s\S]*?```', '[code removed]', text)
    text = re.sub(r'<[a-z_]+>[\s\S]*?</[a-z_]+>', '[tool output removed]', text)
    text = re.sub(r'^\s*[+-]{3}\s+[a-z]/.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*@@.*@@.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if len(text) <= 500:
        return text
    return text.split('\n')[0][:200] + " [...]"


def _turn_noncitable_transform(source: str):
    """Per-source treatment of non-citable turns, kept exactly as the legacy
    path treats assistant text today (so any cost change is attributable to
    the context turns, not to a changed assistant rule): Claude Code sessions
    get the D-048 abstraction, every other source the noise strip only."""
    if is_claude_code_source(source):
        return _abstract_noncitable_project_text
    return lambda t: _strip_noise_content(t, verbose=False)


_TURN_LABELS_HELP = """HOW THE TURNS ARE LABELLED
- [S1 | SUBJECT, typed] or [S2 | SUBJECT, spoken]: the subject's own words. Only these S labels can be cited.
- Every other label (ASSISTANT, OTHER PERSON, PASTED MATERIAL, TOOL OUTPUT, HARNESS SUMMARY, PROGRAMMATIC PROMPT, UNCLASSIFIED) is marked "not citable". Read those turns to understand what the subject is responding to. Never attribute their content to the subject: something the assistant said is not a fact about the subject, even when the subject replied to it."""


def uncounted_mode(mode) -> bool:
    """True for the modes whose prompt carries no count (TURN_UNCOUNTED_MODES): no per-chunk
    truncation and the output budget from citable chars. The one test every mode site uses.
    A missing mode (a pre-switch batch state file) is `capped`."""
    return (mode or "capped") in TURN_UNCOUNTED_MODES


def _mode_prompt_flags(mode) -> dict:
    """The prompt sentences a fact-count mode adds: the coverage sentence for
    TURN_COVERAGE_MODES, and the fragment sentence for `coverage_fragments`."""
    return {"coverage": mode in TURN_COVERAGE_MODES, "fragments": mode == "coverage_fragments"}


def turn_fact_count_mode() -> str:
    """One of TURN_FACT_COUNT_MODES (config TURN_FACT_COUNT_MODE, overridable per run with
    BASELAYER_FACT_COUNT_MODE). Read at call time. An unknown value is refused, never
    read as a default."""
    raw = os.environ.get("BASELAYER_FACT_COUNT_MODE")
    mode = (raw if raw is not None and raw.strip() else TURN_FACT_COUNT_MODE).strip().lower()
    if mode not in TURN_FACT_COUNT_MODES:
        raise ValueError(f"fact_count_mode {mode!r} is not one of {TURN_FACT_COUNT_MODES}")
    return mode


def build_turn_extraction_prompt(conv_title: str, context_text: str, body_text: str,
                                 max_facts, chunk_info: str = None,
                                 project_session: bool = False,
                                 entity_hints: str = None, coverage: bool = False,
                                 fragments: bool = False) -> str:
    """The turn-contract extraction prompt (contract §3). The prompt ASKS for
    grounding; gate_facts is what enforces it (§3: "the prompt is not the
    enforcement"). max_facts None is fact_count_mode `none`: no count and no
    ordering in the prompt."""
    predicates_str = ", ".join(CONSTRAINED_PREDICATES)
    if max_facts is None:
        ask = "Extract facts about the SUBJECT as structured triples."
        if coverage:
            ask += " " + TURN_COVERAGE_SENTENCE
        if fragments:
            ask += " " + TURN_FRAGMENT_SENTENCE
    else:
        ask = (f"Extract up to {max_facts} facts about the SUBJECT as structured triples, "
               f"most identity-relevant first.")
    if entity_hints is None:
        entity_hints = _get_known_entities_for_prompt()
    chunk_context = f"\n<chunk_context>{chunk_info}</chunk_context>\n" if chunk_info else ""
    earlier = context_text.strip() or "(none: this section starts the conversation)"
    if project_session:
        setting = ("a technical project session with an AI coding assistant. Code and tool "
                   "output in non-citable turns has been abbreviated")
        focus = ("EXTRACT facts about the subject AS A PERSON: working style, communication "
                 "preferences, values, decision patterns, how they direct work, preferences and "
                 "opinions that transcend the project. DO NOT EXTRACT: software architecture, "
                 "tools or libraries used, code artifacts, anything only true inside this project.")
    else:
        setting = "a conversation with an AI assistant"
        focus = ("Pay attention to relationships the subject mentions (family, friends, colleagues, "
                 "mentors, partners): who each person is to the subject, and the dynamic. Use "
                 "category \"relationship\" for interpersonal facts. Skip one-off tasks and "
                 "product lookups unless they reveal something lasting about the subject.")

    return f"""You are extracting facts about one person, the SUBJECT, from {setting}.
{chunk_context}
<conversation_title>{conv_title}</conversation_title>

<earlier_turns>
These turns come before this section. They are here only so you can understand what the subject is responding to. Do not extract from them and do not cite them.

{earlier}
</earlier_turns>

<turns>
{body_text}
</turns>

{_TURN_LABELS_HELP}

WHAT TO EXTRACT
{ask} A fact may restate what the subject said, or state an understanding you infer from one or several of the subject's turns. When the subject accepts, rejects or corrects something the assistant proposed, the fact is what the subject decided, grounded in the subject's reply (for example "yes, do that") read together with the turn it answers.
{focus}{entity_hints}

GROUNDING (required on every fact)
- evidence_spans: 1 or more excerpts, each {{"turn": "S<n>", "span": "<exact words>"}}. Copy each span character for character from that S turn: no paraphrase, no ellipsis, no joining of separate sentences, no words from any other turn. Each span must be at least {TURN_EVIDENCE_SPAN_MIN_WORDS} words and at most {TURN_EVIDENCE_SPAN_MAX_CHARS} characters. An inferred fact lists every subject passage it rests on.
- inferred: false when the fact restates what the subject said; true when it is your interpretation of the subject's words.
- If a fact cannot be grounded in the subject's own words in <turns>, do not output it.

For each fact also provide:
- subject: the person's name if known, otherwise "user".
- predicate: MUST be one of: {predicates_str}
- object: the specific value, entity or description. Concrete and precise; no hedging language.
- qualifier: temporal or conditional context, or "unknown".
- category: one of: preference, biography, project, relationship, interest, skill, value, habit, opinion, goal, negative_trait
- temporal: current, past, or unknown
- confidence: 0.0 to 1.0

Example:
  {{"subject": "user", "predicate": "prefers", "object": "direct answers before reasoning", "qualifier": "unknown", "category": "preference", "temporal": "current", "confidence": 0.9, "inferred": false, "evidence_spans": [{{"turn": "S2", "span": "just give me the answer first"}}]}}

Return a JSON object with a "facts" array. If the subject's turns support no facts, return {{"facts": []}}."""


def turn_prompt_hash(project_session: bool, mode: str = None) -> str:
    """Hash of the turn prompt TEMPLATE, the schema and the JSON instruction.
    Content and entity hints are replaced by fixed sentinels, so the hash
    changes when the wording changes and not when the conversation does.
    The fact-count mode changes the wording, so it changes the hash."""
    mode = mode or turn_fact_count_mode()
    template = build_turn_extraction_prompt(
        "<TITLE>", "<CONTEXT>", "<TURNS>", max_facts=None if uncounted_mode(mode) else 0,
        chunk_info="<CHUNK>",
        project_session=project_session, entity_hints="", **_mode_prompt_flags(mode))
    return _tc.prompt_hash(template + json_instruction_for(TURN_EXTRACT_SCHEMA))


def legacy_prompt_hash(builder, schema=None) -> str:
    """Same idea for the legacy builders, so legacy facts carry a prompt hash too."""
    try:
        template = builder("<TITLE>", "<CONTENT>", max_facts=0, chunk_info="<CHUNK>")
    except TypeError:
        template = builder("<TITLE>", "<CONTENT>", max_facts=0)
    return _tc.prompt_hash(template + json_instruction_for(schema or EXTRACT_SCHEMA))


def _extraction_model_name() -> str:
    return EXTRACTION_API_MODEL if EXTRACTION_BACKEND == "anthropic" else LLM_MODEL


def turn_stamps() -> dict:
    """Per-prompt-variant stamps for a turn-contract run (contract §7)."""
    model = _extraction_model_name()
    return {variant: _tc.extraction_stamp(model, turn_prompt_hash(variant), code_file=__file__)
            for variant in (False, True)}


class TurnChunkResult:
    """One chunk's outcome. `budget` and `upto` say how the chunk was built (input character
    budget; built from the first `upto` turns, 0 = all), so a failed chunk can be rebuilt
    exactly and retried alone. `reason` names why a failed chunk failed."""
    __slots__ = ("chunk", "raw_facts", "failed", "budget", "upto", "reason")

    def __init__(self, chunk, raw_facts, failed=False, budget=None, upto=0, reason=None):
        self.chunk, self.raw_facts, self.failed = chunk, raw_facts, failed
        self.budget, self.upto, self.reason = budget, upto, reason


def turn_extraction_plan(turns, source: str) -> dict:
    """Caps for one conversation's turn-contract extraction. `fact_count_mode` is
    saved in the plan so the batch path finalises with the mode it submitted with."""
    total_chars = sum(len(t.text) for t in turns)
    caps = _get_extraction_caps(len(turns), total_chars, source=source)
    max_facts = caps["max_facts"]
    if _dynamic_cap_enabled():
        per_chunk_cap = min(OUTPUT_SAFE_CHUNK_CAP, max_facts)
    else:
        per_chunk_cap = min(50, max_facts)
    return {"input_char_budget": caps["input_char_budget"], "max_facts": max_facts,
            "per_chunk_cap": per_chunk_cap, "total_chars": total_chars,
            "max_tokens": _turn_extraction_max_tokens(per_chunk_cap),
            "fact_count_mode": turn_fact_count_mode(),
            "citable_chars": sum(len(t.text) for t in turns if t.citable)}


def build_turn_chunks(turns, source: str, budget: int):
    return _tc.build_chunks(turns, budget,
                            context_budget=TURN_CONTEXT_CHAR_BUDGET,
                            context_max_turns=TURN_CONTEXT_MAX_TURNS,
                            noncitable_transform=_turn_noncitable_transform(source))


def turn_chunk_prompt(conv_title: str, chunk, plan: dict, project_session: bool) -> str:
    info = f"Section {chunk.index} of {chunk.total} from '{conv_title}'." if chunk.total > 1 else None
    mode = plan.get("fact_count_mode")
    count = None if uncounted_mode(mode) else plan["per_chunk_cap"]
    return build_turn_extraction_prompt(conv_title, chunk.rendered_context, chunk.rendered_body,
                                        max_facts=count, chunk_info=info,
                                        project_session=project_session,
                                        **_mode_prompt_flags(mode))


def _call_turn_chunk(conv_title: str, ch, plan: dict, project_session: bool, chunk_label):
    """One extraction call for one chunk. Returns the facts list, or None when the
    response was unusable. Raises ExtractionResponseError("max_tokens") so the caller
    can re-chunk."""
    prompt = turn_chunk_prompt(conv_title, ch, plan, project_session)
    tok = _CURRENT_CHUNK.set({"chunk": chunk_label, "citable_chars": ch.citable_chars})
    raise_tok = _RAISE_MAX_TOKENS.set(True)
    try:
        result = call_llm(prompt, schema=TURN_EXTRACT_SCHEMA,
                          max_tokens=turn_chunk_max_tokens(ch, plan))
    finally:
        _RAISE_MAX_TOKENS.reset(raise_tok)
        _CURRENT_CHUNK.reset(tok)
    if result and isinstance(result.get("facts"), list):
        return result["facts"]
    return None


def rechunk_after_max_tokens(conv_title: str, turns, source: str, *, failed_index,
                             body_ids, citable_ids, plan: dict, project_session: bool,
                             record, path: str = "sequential"):
    """A chunk stopped on max_tokens: rebuild the conversation up to the chunk's last
    body turn at HALF the input budget, keep the parts that carry any of the failed
    chunk's citable turns, and call each part once. Returns TurnChunkResult list (a part
    that fails is a failed result). Every outcome is counted and the chunk is listed in
    the run record: nothing is dropped silently. A part that overlaps an earlier chunk
    can re-extract a turn already extracted there; AUDN deduplicates it."""
    positions = [i for i, t in enumerate(turns) if t.turn_id in body_ids]
    half = max(1, plan["input_char_budget"] // 2)
    upto = max(positions) + 1 if positions else 0
    parts = [c for c in build_turn_chunks(turns[:upto] if upto else turns, source, half)
             if c.has_citable and set(c.alias_to_turn.values()) & set(citable_ids)]
    entry = {"conversation_id": _CURRENT_CONVERSATION.get(), "chunk": failed_index,
             "path": path, "input_char_budget": half, "parts": len(parts),
             "still_truncated": 0, "failed": 0}
    if record is not None:
        record.c["rechunked_on_max_tokens"] += 1
        record.rechunked.append(entry)
    results = []
    for part in parts:
        label = f"{failed_index}.r{part.index}"
        if record is not None:
            record.c["chunks_called"] += 1
            record.c["rechunk_calls"] += 1
        reason = "unusable_response"
        try:
            facts = _call_turn_chunk(conv_title, part, plan, project_session, label)
        except ExtractionResponseError as e:          # truncated again: count, list, go on
            _count_response_failure(e.reason)
            entry["still_truncated"] += 1
            facts, reason = None, "max_tokens"
        if facts is None:
            entry["failed"] += 1
            if record is not None:
                record.c["chunks_failed"] += 1
            results.append(TurnChunkResult(part, None, failed=True, budget=half, upto=upto,
                                           reason=reason))
        else:
            results.append(TurnChunkResult(part, facts, budget=half, upto=upto))
    return results


def extract_turn_chunks(conv_title: str, turns, source: str, *, project_session: bool,
                        record=None):
    """Phase 1: one model call per chunk that has at least one citable turn.
    Returns (results, plan). A chunk with no subject turn is skipped (there is
    nothing it could ground) and still serves as context for the next chunk."""
    plan = turn_extraction_plan(turns, source)
    chunks = build_turn_chunks(turns, source, plan["input_char_budget"])
    results = []
    for ch in chunks:
        if not ch.has_citable:
            if record is not None:
                record.c["chunks_skipped_no_citable"] += 1
            continue
        prompt = turn_chunk_prompt(conv_title, ch, plan, project_session)
        if record is not None:
            record.c["chunks_called"] += 1
            record.c["prompt_chars"] += len(prompt)
            record.c["context_chars"] += len(ch.rendered_context)
        try:
            facts = _call_turn_chunk(conv_title, ch, plan, project_session, ch.index)
        except ExtractionResponseError:               # max_tokens: re-chunk, retry once
            results.extend(rechunk_after_max_tokens(
                conv_title, turns, source, failed_index=ch.index,
                body_ids={p.turn.turn_id for p in ch.body},
                citable_ids=set(ch.alias_to_turn.values()), plan=plan,
                project_session=project_session, record=record))
            continue
        if facts is not None:
            results.append(TurnChunkResult(ch, facts, budget=plan["input_char_budget"]))
        else:
            if record is not None:
                record.c["chunks_failed"] += 1
            results.append(TurnChunkResult(ch, None, failed=True,
                                           budget=plan["input_char_budget"],
                                           reason="unusable_response"))
    return results, plan


def turn_referent():
    """The subject's names for a turn-contract run, from the import config
    (`subject_names`). Refuses, before any model call, when none is configured:
    without it the extractor's own name for the subject is stored as a third
    party (contract §5). Aliases of other people come from the entity map and
    are used only by the gate's subject check."""
    from baselayer.import_config import load_import_config
    try:
        ref = _tc.referent_from_config(load_import_config())
    except _tc.ReferentNotConfigured as e:
        raise TurnContractViolation(str(e)) from None
    groups = {}
    for variant, canonical in _get_entity_map().items():
        if isinstance(canonical, str) and not variant.startswith("_"):
            groups.setdefault(canonical.strip().lower(), {canonical.strip().lower()}).add(variant)
    aliases = {m: tuple(sorted(g - {m})) for g in groups.values() for m in g}
    return dataclasses.replace(ref, aliases=aliases)


def gate_turn_chunks(results, referent) -> list:
    """Phase 2, the §5 gate, per chunk, on EVERY raw fact the model returned
    (before any cap slice, so rejections past a cap are still counted).
    Pure and deliberately free of exception handling: if it raises, the run
    stops before anything from this conversation is stored."""
    return [(r.chunk, _tc.gate_facts(r.raw_facts, r.chunk, referent=referent))
            for r in results if not r.failed]


def finalize_turn_facts(gated, message_count: int, plan: dict, *, project_session: bool,
                        record=None) -> list[dict]:
    """Phase 3: normalise the accepted facts (the per-chunk cap applies in capped
    mode only) and add the conversation to the density alarm. Every drop is counted
    in the run record; nothing is trimmed at the conversation level."""
    drops = {}
    facts = []
    # Pre-switch batch state files carry no mode: they were submitted capped.
    uncapped = uncounted_mode(plan.get("fact_count_mode"))
    for _chunk, g in gated:
        if record is not None:
            record.add_gate(g)
        # The D-048 contamination filter rides on identity_only. It is OFF in turn
        # mode (TURN_CONTAMINATION_FILTER, D-108): the span gate replaces it.
        facts.extend(validate_structured_response(
            g.accepted, message_count,
            identity_only=bool(project_session and TURN_CONTAMINATION_FILTER),
            max_facts=plan["per_chunk_cap"], drop_counter=drops, uncapped=uncapped))

    # No conversation-level halt or trim on the turn path, in either mode. A dense
    # conversation is REPORTED in the run record's density block (the alarm), never cut;
    # the runaway guard is the spend ceiling. Capped mode keeps only its per-chunk
    # truncation above, which is what its prompt promised the model.
    if record is not None:
        record.density.append({"conversation_id": _CURRENT_CONVERSATION.get(),
                               "citable_chars": plan.get("citable_chars"),
                               "facts": len(facts)})

    if record is not None:
        record.post_gate_drops.update(drops)
        record.c["facts_after_validation"] += len(facts)
    return facts


def merge_noop_spans(conn, target_id, spans, version: str, record=None) -> int:
    """Append a NOOPed duplicate's evidence spans to the surviving fact, deduplicated on
    (turn_id, normalised span), and re-read the survivor's `practice` from the turns it
    now cites. Returns the number of spans added. Runs inside the caller's transaction,
    so a failed conversation rolls it back with everything else. A survivor that cannot
    be found (no row for the id at this contract version) is counted, never guessed."""
    if not target_id or not spans:
        return 0
    row = conn.execute("SELECT evidence_spans FROM memory_facts WHERE id = ? AND "
                       "turn_contract_version = ?", (target_id, version)).fetchone()
    if row is None:
        if record is not None:
            record.c["noop_survivor_missing"] += 1
        return 0
    try:
        held = json.loads(row[0]) if row[0] else []
    except (TypeError, ValueError):
        if record is not None:
            record.c["noop_survivor_spans_unparseable"] += 1
        return 0
    seen = {(s.get("turn_id"), _tc.normalise_for_match(str(s.get("span", ""))))
            for s in held if isinstance(s, dict)}
    added = 0
    for s in spans:
        key = (s.get("turn_id"), _tc.normalise_for_match(str(s.get("span", ""))))
        if key in seen:
            continue
        seen.add(key)
        held.append(dict(s))
        added += 1
    if added:
        conn.execute("UPDATE memory_facts SET evidence_spans = ?, practice = ?, updated_at = ? "
                     "WHERE id = ?", (json.dumps(held, ensure_ascii=False),
                                      fact_practice(conn, held), time.time(), target_id))
    return added


def store_turn_facts(conn, conv_id: str, facts: list[dict], fact_collection, embed_model, *,
                     scope: str, stamp: dict, corrections=None, record=None,
                     embedded: list = None) -> int:
    """Phase 4: AUDN against gated facts of the same contract version only,
    then INSERT with grounding and stamp. The caller rolls back on error."""
    stored_ids = []
    version = stamp["turn_contract_version"]
    for f in facts:
        text = f["fact"]
        if corrections and check_against_corrections(text, corrections):
            if record is not None:
                record.post_gate_drops["user_correction_block"] += 1
            continue
        similar = find_similar_facts(text, fact_collection, embed_model,
                                     contract_version=version, grounding=f.get("grounding"),
                                     conn=conn)
        decision = make_audn_decision(text, similar)
        action = decision.get("action", "ADD")
        if record is not None:
            record.audn[action] += 1
        if action not in ("ADD", "UPDATE"):
            if action == "NOOP" and similar:
                # A duplicate is not stored twice, but its grounding is kept: the
                # survivor gains the duplicate's own-voice spans (TURN_CONTRACT §5).
                target = max(similar, key=lambda x: x["similarity"]).get("fact_id")
                added = merge_noop_spans(conn, target, f.get("evidence_spans") or [],
                                         version, record=record)
                if record is not None:
                    record.c["noop_spans_merged"] += added
            if action == "DELETE" and similar:
                target = max(similar, key=lambda x: x["similarity"]).get("fact_id")
                if target:
                    conn.execute("UPDATE memory_facts SET superseded_by = 'CONTRADICTED', "
                                 "updated_at = ? WHERE id = ? AND turn_contract_version = ?",
                                 (time.time(), target, version))
            continue
        supersedes = None
        if action == "UPDATE":
            text = decision.get("updated_fact") or text
            if similar:
                supersedes = max(similar, key=lambda x: x["similarity"]).get("fact_id")
        fid = store_fact(conn, text, f["category"], f["confidence"], conv_id, action, supersedes,
                         subject=f.get("subject", "user"), intent=f.get("intent", "does"),
                         temporal=f.get("temporal", "unknown"),
                         raw_llm_confidence=f.get("raw_llm_confidence"),
                         fact_class=f.get("fact_class", "unclassified"),
                         knowledge_tier=f.get("knowledge_tier", "untiered"), tiered_by=None,
                         scope=scope, predicate=f.get("predicate"),
                         object_text=f.get("object_text"), qualifier=f.get("qualifier"),
                         source_turn_id=f["source_turn_id"],
                         evidence_spans=f["evidence_spans"], inferred=f.get("inferred"),
                         voice_class=f.get("voice_class"), stamp=stamp,
                         grounding=f.get("grounding"), record=record)
        if embed_model and fact_collection:
            embed_fact(fid, text, f["category"], fact_collection, embed_model,
                       contract_version=version, grounding=f.get("grounding"))
            if embedded is not None:
                embedded.append(fid)
        stored_ids.append(fid)
    if len(stored_ids) >= 2:
        link_facts(conn, stored_ids, conv_id)
    return len(stored_ids)


def _facts_stamp_counts(conn, version: str) -> tuple[int, int]:
    """(facts NOT stamped `version`, facts stamped with ANY version), read-only.

    Never ALTERs: the guards run before anything writes, so a run pointed at the
    wrong database (for instance the live served one) refuses without having
    added a column to it. A missing table counts as empty; a missing version
    column means no fact is stamped."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "memory_facts" not in tables:
        return 0, 0
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memory_facts)")}
    if "turn_contract_version" not in cols:
        n = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        return n, 0
    unstamped = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE turn_contract_version IS NULL "
        "OR turn_contract_version != ?", (version,)).fetchone()[0]
    stamped_any = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE turn_contract_version IS NOT NULL").fetchone()[0]
    return unstamped, stamped_any


class TurnContractViolation(RuntimeError):
    """Raised before any model call when the corpus cannot be extracted under
    the turn contract (or cannot be extracted outside it) without mixing."""


def assert_fresh_for_turn_contract(conn, fact_collection=None,
                                   version: str = TURN_CONTRACT_VERSION):
    """Refuse a turn-contract run on a database that holds any fact not stamped
    with this contract version, in SQLite or in the Chroma collection.

    The operating assumption is a fresh corpus directory. Gated and ungated
    facts must never meet in AUDN: a gated fact NOOPed against a legacy one is
    a gated fact silently replaced by an assistant-sourced one. The search-time
    version filter in find_similar_facts is the second layer; this is the first.
    Note that `baselayer forget --all` does not clear extraction_log; the full
    reset is `python -m baselayer.extract_facts --reset`, and a fresh directory
    is safer than either. Read-only."""
    bad, _ = _facts_stamp_counts(conn, version)
    if bad:
        raise TurnContractViolation(
            f"{bad} facts in this database are not stamped {version}. Turn-contract "
            f"extraction must run in a FRESH corpus directory; gated facts must never be "
            f"deduplicated against legacy ones.")
    if fact_collection is not None:
        total = fact_collection.count()
        if total:
            stamped = len(fact_collection.get(where={"turn_contract_version": version},
                                              include=[])["ids"])
            if stamped != total:
                raise TurnContractViolation(
                    f"the vector store holds {total - stamped} fact vectors not stamped "
                    f"{version} (of {total}). Use a fresh corpus directory.")


def assert_legacy_allowed(conn):
    """Refuse a LEGACY run on a corpus whose facts were extracted under the turn
    contract, so gated and ungated facts never share a database.

    A turn table alone is NOT refused. The importer writes turn rows for every
    source it knows, and projects them into the legacy `messages` table
    (citable subject text plus assistant text only) precisely so that the
    default pipeline (`baselayer run`, which extracts on the legacy path) keeps
    working on a freshly imported corpus. The mixing hazard is facts, so facts
    are what this checks."""
    _, n = _facts_stamp_counts(conn, TURN_CONTRACT_VERSION)
    if n:
        raise TurnContractViolation(
            f"{n} facts here were extracted under the turn contract; a legacy run would "
            f"mix ungated facts into a gated corpus. Extract it with --turn-contract "
            f"(BASELAYER_TURN_CONTRACT=1), not the legacy path.")


def turn_run_settings() -> dict:
    """Every cap and switch that shapes a turn-contract run, for the header and
    the per-run record (no hidden caps)."""
    return {
        "turn_contract_version": TURN_CONTRACT_VERSION,
        "turn_table": _tc.TURN_TABLE,
        "fact_count_mode": turn_fact_count_mode(),
        "spend_ceiling_usd": spend_ceiling_usd(),
        "output_tokens_per_citable_char": TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR,
        "output_tokens_floor": TURN_OUTPUT_TOKENS_FLOOR,
        "output_tokens_ceiling": EXTRACTION_MAX_OUTPUT_TOKENS,
        "dynamic_cap": _dynamic_cap_enabled(),
        "skip_coverage_gate": bool(os.environ.get("BASELAYER_SKIP_COVERAGE_GATE")),
        "context_char_budget": TURN_CONTEXT_CHAR_BUDGET,
        "context_max_turns": TURN_CONTEXT_MAX_TURNS,
        "span_min_words": _tc.span_bounds()[0],
        "span_max_chars": _tc.span_bounds()[1],
        "contamination_filter": bool(TURN_CONTAMINATION_FILTER),
        # MIN_MESSAGES_FOR_EXTRACTION is not applied in turn mode (D-108): a
        # conversation is extracted if it has any citable turn.
        "min_messages_for_extraction": None,
        "tokens_per_fact": TURN_EXTRACTION_TOKENS_PER_FACT,
        "output_safe_chunk_cap": OUTPUT_SAFE_CHUNK_CAP,
        "chars_per_fact": CHARS_PER_FACT,
        "extraction_model": _extraction_model_name(),
        "backend": EXTRACTION_BACKEND,
    }


def check_turn_versions(turns, record=None):
    """Turns written under a different contract version cannot be extracted
    under this one: raise. A NULL version (importer did not stamp) is counted,
    not refused, and shows up in the run record."""
    other = {t.contract_version for t in turns
             if t.contract_version is not None and t.contract_version != TURN_CONTRACT_VERSION}
    if other:
        raise TurnContractViolation(
            f"turns stamped {sorted(other)} cannot be extracted under {TURN_CONTRACT_VERSION}")
    if record is not None:
        record.c["turns_unstamped"] += sum(1 for t in turns if t.contract_version is None)


# ---------------------------------------------------------------------------
# Failed chunks (turn contract): recorded as FAILED, retried alone
# ---------------------------------------------------------------------------
#
# A chunk whose call fails (an API error after retries, a refusal, an unparseable or
# schema-invalid reply, a part that truncated again after re-chunking) used to be dropped:
# the conversation was logged as extracted with the other chunks' count, its import mark was
# cleared, the batch path marked the chunk done, and nothing ever selected it again. Now:
#   - the conversation's good chunks are still stored (nothing that worked is thrown away);
#   - each failed chunk is written here, in the same transaction, with what it takes to
#     rebuild it exactly (its body turn ids, input budget and turn prefix);
#   - the run counts it as an error and exits non-zero after its record is written;
#   - the next run (sequential, or an incremental batch submit) and `--process --resume`
#     retry ONLY these chunks. A retried chunk that truncates is re-chunked at half its own
#     budget, so a persistent truncation is retried smaller each time, never skipped.
# A chunk that keeps failing (a refusal, say) is retried, and fails the run, every time; the
# row's `attempts` counts it. `--process` without --resume clears the table with the reset.

FAILED_CHUNKS_TABLE = "extraction_chunks_failed"
_FAILED_PLAN_KEYS = ("max_facts", "per_chunk_cap", "max_tokens", "fact_count_mode")


def ensure_failed_chunks_table(conn) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {FAILED_CHUNKS_TABLE} (
            conversation_id TEXT NOT NULL,
            chunk_key TEXT NOT NULL,            -- JSON list of the chunk's body turn ids, sorted
            input_char_budget INTEGER NOT NULL, -- the budget the chunk was built with
            turns_upto INTEGER NOT NULL,        -- built from the first N turns; 0 = all
            plan TEXT NOT NULL,                 -- JSON: the plan fields the call used
            path TEXT NOT NULL,                 -- sequential | batch
            reason TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 1,
            batch_id TEXT,
            recorded_at REAL NOT NULL,
            PRIMARY KEY (conversation_id, chunk_key, input_char_budget, turns_upto)
        )""")


def failed_chunks_table_exists(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (FAILED_CHUNKS_TABLE,)).fetchone() is not None


def chunk_key(body_turn_ids) -> str:
    return json.dumps(sorted(body_turn_ids), separators=(",", ":"))


def failed_chunk(conv_id: str, body_turn_ids, budget: int, upto: int, plan: dict, path: str,
                 reason: str) -> dict:
    return {"conversation_id": conv_id, "chunk_key": chunk_key(body_turn_ids),
            "input_char_budget": int(budget), "turns_upto": int(upto or 0),
            "plan": json.dumps({k: plan.get(k) for k in _FAILED_PLAN_KEYS}, sort_keys=True),
            "path": path, "reason": reason or "unusable_response"}


def failures_of(results, conv_id: str, plan: dict, path: str) -> list:
    """failed_chunk rows for every failed TurnChunkResult."""
    return [failed_chunk(conv_id, r.chunk.body_voice, r.budget or plan["input_char_budget"],
                         r.upto, plan, path, r.reason)
            for r in results if r.failed]


def load_failed_chunks(conn, conv_id: str) -> list:
    if not failed_chunks_table_exists(conn):
        return []
    cur = conn.execute(f"SELECT conversation_id, chunk_key, input_char_budget, turns_upto, "
                       f"plan, path, reason, attempts FROM {FAILED_CHUNKS_TABLE} "
                       f"WHERE conversation_id = ? ORDER BY recorded_at, chunk_key", (conv_id,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def failed_chunk_conversations(conn) -> set:
    if not failed_chunks_table_exists(conn):
        return set()
    return {r[0] for r in conn.execute(
        f"SELECT DISTINCT conversation_id FROM {FAILED_CHUNKS_TABLE}")}


def write_failed_chunks(conn, conv_id: str, failures, *, replace_all: bool, resolved=(),
                        batch_id: str = None) -> None:
    """Record failed chunks. The caller commits, with the facts, in one transaction.
    replace_all: a full extraction of the conversation supersedes every earlier row.
    resolved: (chunk_key, input_char_budget, turns_upto) of rows a retry settled.
    A failure that is already recorded has its attempts counted up."""
    ensure_failed_chunks_table(conn)
    if replace_all:
        conn.execute(f"DELETE FROM {FAILED_CHUNKS_TABLE} WHERE conversation_id = ?", (conv_id,))
    for key, budget, upto in resolved:
        conn.execute(f"DELETE FROM {FAILED_CHUNKS_TABLE} WHERE conversation_id = ? AND "
                     f"chunk_key = ? AND input_char_budget = ? AND turns_upto = ?",
                     (conv_id, key, budget, upto))
    now = time.time()
    for f in failures:
        conn.execute(f"""
            INSERT INTO {FAILED_CHUNKS_TABLE} (conversation_id, chunk_key, input_char_budget,
                turns_upto, plan, path, reason, attempts, batch_id, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id, chunk_key, input_char_budget, turns_upto) DO UPDATE SET
                attempts = attempts + 1, reason = excluded.reason, path = excluded.path,
                plan = excluded.plan, batch_id = excluded.batch_id,
                recorded_at = excluded.recorded_at
        """, (f["conversation_id"], f["chunk_key"], f["input_char_budget"], f["turns_upto"],
              f["plan"], f["path"], f["reason"], 1, batch_id, now))


def note_failed_chunks(record, failures) -> None:
    """Count and list the failed chunks this run leaves open, in the run record."""
    if record is None:
        return
    record.c["chunks_failed_open"] += len(failures)
    for f in failures:
        record.failed_chunks.append({
            "conversation_id": f["conversation_id"], "path": f["path"], "reason": f["reason"],
            "body_turns": len(json.loads(f["chunk_key"])),
            "input_char_budget": f["input_char_budget"], "turns_upto": f["turns_upto"]})


def rebuild_failed_chunk(turns, source: str, row: dict):
    """The chunk a failed-chunk row describes, rebuilt from the current turns, or None when
    no chunk with the same body turns is built any more (the turns or settings changed)."""
    upto = row["turns_upto"]
    for ch in build_turn_chunks(turns[:upto] if upto else turns, source,
                                row["input_char_budget"]):
        if ch.has_citable and chunk_key(ch.body_voice) == row["chunk_key"]:
            return ch
    return None


def failed_chunk_plan(base: dict, row: dict) -> dict:
    """The plan a failed chunk is retried with: the conversation's current plan, overlaid with
    the recorded fields and the chunk's own input budget."""
    plan = dict(base, **{k: v for k, v in json.loads(row["plan"]).items() if v is not None})
    plan["input_char_budget"] = row["input_char_budget"]
    return plan


def upsert_log_sum(conn, conv_id: str, stored: int) -> None:
    """A retry ADDS its facts to the conversation's logged count; it never replaces it."""
    conn.execute("""
        INSERT INTO extraction_log (conversation_id, facts_extracted, processed_at)
        VALUES (?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
            facts_extracted = MAX(facts_extracted, 0) + excluded.facts_extracted,
            processed_at = excluded.processed_at
    """, (conv_id, stored, time.time()))


def retry_failed_chunks(conv: dict, conn, fact_collection, embed_model, *, stamps: dict, record,
                        referent, corrections=None, identity_only: bool = False,
                        path: str = "sequential", batch_id: str = None) -> tuple:
    """Retry ONLY the recorded failed chunks of one conversation, synchronously. Each is
    rebuilt exactly, called, gated and stored like any chunk; a row is deleted when its chunk
    succeeds and kept (attempts + 1) when it fails again. A chunk that can no longer be
    rebuilt stays recorded as `not_reproducible`. Returns (facts stored, failures left)."""
    conv_id, source = conv["id"], conv.get("source", "unknown")
    rows = load_failed_chunks(conn, conv_id)
    turns = _tc.load_turns(conn, conv_id)
    if not rows or not turns:
        return 0, 0
    check_turn_versions(turns, record)
    project = identity_only or is_claude_code_source(source)
    scope = "personal" if identity_only else SCOPE_SOURCE_MAPPING.get(source, DEFAULT_SCOPE)
    title = conv.get("title") or "Untitled"
    base = turn_extraction_plan(turns, source)
    results, failures, resolved, recovered = [], [], [], 0
    fplan = None
    for row in rows:
        plan = failed_chunk_plan(base, row)
        fplan = fplan or plan
        key = (row["chunk_key"], row["input_char_budget"], row["turns_upto"])
        record.c["chunks_retried"] += 1
        ch = rebuild_failed_chunk(turns, source, row)
        if ch is None:
            record.c["chunks_not_reproducible"] += 1
            failures.append(dict(row, path=path, reason="not_reproducible"))
            continue
        record.c["chunks_called"] += 1
        label = f"retry:{ch.index}"
        try:
            facts = _call_turn_chunk(title, ch, plan, project, label)
        except ExtractionResponseError:           # max_tokens: re-chunk at half this budget
            parts = rechunk_after_max_tokens(
                title, turns, source, failed_index=label,
                body_ids={p.turn.turn_id for p in ch.body},
                citable_ids=set(ch.alias_to_turn.values()), plan=plan,
                project_session=project, record=record, path=path)
            resolved.append(key)                  # the parts replace the row
            left = failures_of(parts, conv_id, plan, path)
            failures.extend(left)
            recovered += 0 if left else 1
            results.extend(r for r in parts if not r.failed)
            continue
        if facts is None:
            record.c["chunks_failed"] += 1
            failures.append(dict(row, path=path, reason="unusable_response"))
        else:
            results.append(TurnChunkResult(ch, facts, budget=row["input_char_budget"],
                                           upto=row["turns_upto"]))
            resolved.append(key)
            recovered += 1

    gated = gate_turn_chunks(results, referent)              # NO handler above this
    facts = finalize_turn_facts(gated, len(turns), fplan, project_session=project,
                                record=record)
    embedded = []
    try:
        stored = store_turn_facts(conn, conv_id, facts, fact_collection, embed_model,
                                  scope=scope, stamp=stamps[project], corrections=corrections,
                                  record=record, embedded=embedded)
        upsert_log_sum(conn, conv_id, stored)
        write_failed_chunks(conn, conv_id, failures, replace_all=False, resolved=resolved,
                            batch_id=batch_id)
        conn.commit()
    except BaseException:
        conn.rollback()
        if embedded and fact_collection is not None:
            fact_collection.delete(ids=embedded)
        raise
    record.c["facts_stored"] += stored
    record.c["chunks_recovered"] += recovered
    note_failed_chunks(record, failures)
    return stored, len(failures)


def process_turn_conversation(conv: dict, conn, fact_collection, embed_model, *,
                              stamps: dict, record, referent, corrections=None,
                              identity_only: bool = False) -> int:
    """One conversation through the four phases. Returns facts stored, or -1
    when the LLM phase failed. Raises (never swallows) on a gate failure,
    missing turns, or the coverage gate."""
    conv_id, source = conv["id"], conv.get("source", "unknown")
    if conv.get("grown"):
        record.c["grown_conversations"] += 1
    turns = _tc.load_turns(conn, conv_id)
    if not turns:
        # The importer writes every turn, citable or not. No rows at all means
        # the conversation never went through the turn-contract importer.
        record.c["conversations_without_turns"] += 1
        conn.execute("INSERT OR REPLACE INTO extraction_log "
                     "(conversation_id, facts_extracted, processed_at) VALUES (?, -1, ?)",
                     (conv_id, time.time()))
        conn.commit()
        return -1
    check_turn_versions(turns, record)
    project = identity_only or is_claude_code_source(source)
    scope = "personal" if identity_only else SCOPE_SOURCE_MAPPING.get(source, DEFAULT_SCOPE)
    record.c["turns"] += len(turns)
    record.c["citable_turns"] += sum(1 for t in turns if t.citable)
    record.c["turns_chars"] += sum(len(t.text) for t in turns)
    record.c["citable_chars"] += sum(len(t.text) for t in turns if t.citable)

    try:
        results, plan = extract_turn_chunks(conv["title"], turns, source,
                                            project_session=project, record=record)
    except Exception as e:  # model / network failure only; nothing stored yet
        record.c["conversation_errors"] += 1
        print(f"  ERROR (model phase) on '{conv['title'][:40]}': {e}")
        conn.execute("INSERT OR REPLACE INTO extraction_log "
                     "(conversation_id, facts_extracted, processed_at) VALUES (?, -1, ?)",
                     (conv_id, time.time()))
        conn.commit()
        return -1

    failures = failures_of(results, conv_id, plan, "sequential")
    gated = gate_turn_chunks(results, referent)              # NO handler above this
    facts = finalize_turn_facts(gated, len(turns), plan,      # may SystemExit, by design
                                project_session=project, record=record)

    embedded = []
    try:
        stored = store_turn_facts(conn, conv_id, facts, fact_collection, embed_model,
                                  scope=scope, stamp=stamps[project], corrections=corrections,
                                  record=record, embedded=embedded)
        conn.execute("INSERT OR REPLACE INTO extraction_log "
                     "(conversation_id, facts_extracted, processed_at) VALUES (?, ?, ?)",
                     (conv_id, stored, time.time()))
        # A failed chunk is recorded as FAILED, with the good chunks' facts, never dropped.
        if failures or failed_chunks_table_exists(conn):
            write_failed_chunks(conn, conv_id, failures, replace_all=True)
        mark_turn_conversation_extracted(conn, conv_id)
        conn.commit()
    except BaseException:
        # never commit a half-stored conversation, whatever stopped it (the spend
        # ceiling raises SystemExit, which `except Exception` would let through)
        conn.rollback()
        if embedded and fact_collection is not None:
            fact_collection.delete(ids=embedded)  # and leave no orphan vectors behind
        raise
    record.c["facts_stored"] += stored
    note_failed_chunks(record, failures)
    return stored


# ---------------------------------------------------------------------------
# AUDN Decision (D-005)
# ---------------------------------------------------------------------------

def find_similar_facts(fact_text: str, collection, embed_model, top_k: int = 5,
                       contract_version: str = None, grounding: str = None,
                       conn=None) -> list[dict]:
    """
    Find existing facts that are similar to the candidate fact.
    Used for deduplication — if a very similar fact exists, we UPDATE or NOOP.
    Uses pre-loaded embed_model to avoid repeated model reloads.

    contract_version (turn path): restrict the search to facts stamped with the
    same turn-contract version, so AUDN can never NOOP, UPDATE or DELETE a gated
    fact against an ungated legacy one. Legacy vectors carry no version key and
    are therefore invisible to the filter.

    conn (turn path): exclude superseded facts. A superseded fact's vector stays
    in the store, so without this an UPDATE could land on a dead fact (and
    re-point it, orphaning its first successor) and a NOOP could merge spans into
    it. `superseded_by` is read on the caller's connection, so a supersession made
    earlier in the same uncommitted transaction counts. The query over-fetches
    until it holds top_k live hits or the store runs out.
    """
    if collection is None or embed_model is None:
        return []

    try:
        # Use pre-loaded model instead of query_texts to avoid reloading
        embedding = embed_model.encode([fact_text]).tolist()
        query = {"query_embeddings": embedding, "n_results": top_k}
        if contract_version and grounding:
            # Turn path: never deduplicate a prose-grounded fact against a record-only
            # one (or the reverse): the survivor could be excluded from distillation.
            query["where"] = {"$and": [{"turn_contract_version": contract_version},
                                       {"grounding": grounding}]}
        elif contract_version:
            query["where"] = {"turn_contract_version": contract_version}
        results = collection.query(**query)
        if conn is not None:
            results = _drop_superseded_hits(conn, collection, query, results, top_k)

        similar = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                # A SIXTH CONVERSION SITE, INLINE, MISSED BY THE 8/18 SWEEP because it does
                # not call chromadb_dist_to_similarity and so did not appear in a search for
                # that name. It ran the L2 formula against the facts collection, which current
                # code creates as cosine, inflating similarity by up to 0.47 and making AUDN
                # dedup over-aggressive: new facts get treated as already-known. That is the
                # exact failure the low-yield extraction guard exists to catch.
                from baselayer.config import (chromadb_dist_to_similarity,
                                               collection_space)
                similarity = chromadb_dist_to_similarity(distance,
                                                         collection_space(collection))
                similar.append({
                    "fact_text": doc,
                    "fact_id": meta.get("fact_id", ""),
                    "similarity": round(similarity, 4),
                })

        return similar

    except Exception as e:
        print(f"  WARNING: find_similar_facts failed: {e}", file=sys.stderr)
        # Counted, because a failing search silently switches AUDN dedup off
        # (every candidate becomes ADD); the run record surfaces the count.
        _count_response_failure("similarity_search_error")
        return []


def _drop_superseded_hits(conn, collection, query: dict, results: dict, top_k: int) -> dict:
    """Remove hits whose fact is superseded (any non-NULL `superseded_by`, markers
    included), re-querying with a larger n_results until top_k live hits remain or
    the collection is exhausted. Returns a results dict of the same shape."""
    n = query["n_results"]
    total = None
    while True:
        metas = results["metadatas"][0] if results.get("metadatas") else []
        ids = [m.get("fact_id", "") for m in metas]
        dead = set()
        for i in range(0, len(ids), 500):
            part = [x for x in ids[i:i + 500] if x]
            if part:
                q = ",".join("?" * len(part))
                dead.update(r[0] for r in conn.execute(
                    f"SELECT id FROM memory_facts WHERE id IN ({q}) "
                    f"AND superseded_by IS NOT NULL", part))
        keep = [k for k, fid in enumerate(ids) if fid not in dead]
        if len(keep) >= top_k or len(ids) < n:
            break
        if total is None:
            total = collection.count()
        if n >= total:
            break
        n = min(n * 4, total)
        results = collection.query(**{**query, "n_results": n})
    keep = keep[:top_k]
    return {k: [[results[k][0][j] for j in keep]] for k in ("documents", "metadatas", "distances")}


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
               qualifier: str = None,
               source_turn_id: str = None,
               evidence_spans=None,
               inferred=None,
               voice_class: str = None,
               stamp: dict = None,
               grounding: str = None,
               record=None) -> str:
    """Store a fact in memory_facts and return its ID.
    D-022: Now stores subject, intent, temporal_state, and raw_llm_confidence.
    Temporal processing: Now stores fact_class (event/state/unclassified).
    D-039: Now stores knowledge_tier (identity/situational/context/untiered).
    D-044: Now stores scope (personal/project) derived from conversation source.
    D-056 Tier 2: Now stores predicate, object_text, qualifier from structured extraction.
    Provenance: tiered_by tracks which model assigned the tier (qwen/opus)."""
    fact_id = str(uuid.uuid4())
    now = time.time()
    stamp = stamp or {}
    # The practice the fact is bounded to comes from the turns its spans cite (a gated
    # fact only; a legacy fact has no spans and gets NULL).
    practice = fact_practice(conn, evidence_spans) if evidence_spans else None
    if evidence_spans is not None and not isinstance(evidence_spans, str):
        evidence_spans = json.dumps(evidence_spans, ensure_ascii=False)
    if inferred is not None:
        inferred = 1 if inferred else 0

    conn.execute("""
        INSERT INTO memory_facts
        (id, fact_text, category, confidence, source_conversation_id,
         created_at, updated_at, superseded_by, source,
         subject, intent, temporal_state, raw_llm_confidence, fact_class,
         knowledge_tier, tiered_by, scope,
         predicate, object_text, qualifier,
         source_turn_id, evidence_spans, inferred, voice_class,
         turn_contract_version, extraction_model, extraction_prompt_hash,
         git_commit, code_path, practice, grounding)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'extraction', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fact_id, fact_text, category, confidence, conv_id, now, now,
          subject, intent, temporal, raw_llm_confidence, fact_class,
          knowledge_tier, tiered_by, scope,
          predicate, object_text, qualifier,
          source_turn_id, evidence_spans, inferred, voice_class,
          stamp.get("turn_contract_version"), stamp.get("extraction_model"),
          stamp.get("extraction_prompt_hash"), stamp.get("git_commit"),
          stamp.get("code_path"), practice, grounding))

    # If this supersedes another fact, mark the old one. A set superseded_by is
    # never overwritten: that re-points a dead fact and orphans its first
    # successor, leaving two live near-duplicates. The chain's live head is
    # superseded instead (see _supersede).
    if supersedes_id:
        _supersede(conn, supersedes_id, fact_id, now, record)

    return fact_id


def live_head(conn, fact_id: str):
    """Follow superseded_by from fact_id to the end of its chain. Returns
    (head_id, None) when the chain ends at a live fact, and (None, reason) when it
    ends at a non-fact marker (the marker itself, e.g. 'CONTRADICTED'), at a
    missing row ('missing') or in a cycle ('cycle'). Read-only."""
    seen = set()
    cur = fact_id
    while True:
        row = conn.execute("SELECT superseded_by FROM memory_facts WHERE id = ?",
                           (cur,)).fetchone()
        if row is None:
            return None, "missing"
        nxt = row[0]
        if nxt is None:
            return cur, None
        seen.add(cur)
        if nxt in seen:
            return None, "cycle"
        if conn.execute("SELECT 1 FROM memory_facts WHERE id = ?", (nxt,)).fetchone() is None:
            return None, nxt
        cur = nxt


def _supersede(conn, target_id: str, new_id: str, now: float, record=None):
    """Mark target_id superseded by new_id only while it is live. If it is already
    superseded, supersede the live head of its chain; if the chain ends in a marker,
    a missing row or a cycle, supersede nothing and new_id stays live. Returns the id
    actually superseded, or None. Every case other than the direct one is counted."""
    def count(key):
        if record is not None:
            record.c[key] += 1
    upd = ("UPDATE memory_facts SET superseded_by = ?, updated_at = ? "
           "WHERE id = ? AND superseded_by IS NULL")
    if conn.execute(upd, (new_id, now, target_id)).rowcount == 1:
        return target_id
    if conn.execute("SELECT 1 FROM memory_facts WHERE id = ?", (target_id,)).fetchone() is None:
        count("update_target_missing")
        return None
    count("update_target_already_superseded")
    head, _end = live_head(conn, target_id)
    if head is not None and head != new_id and conn.execute(upd, (new_id, now, head)).rowcount == 1:
        count("update_rerouted_to_live_head")
        return head
    count("update_target_chain_dead")
    return None


def tier_facts_by_predicate(conn) -> tuple[int, int]:
    """Rule-based knowledge_tier assignment from predicate.

    Facts whose predicate is in IDENTITY_PREDICATES become 'identity' tier;
    all other untiered facts become 'contextual'. Only touches untiered facts,
    so it is idempotent and safe to call repeatedly or after a partial run.

    2026-05-19: Extracted into a shared function. Both the batch extraction
    path (batch_extract.run_process) and the post-compose traceability step
    call this. Previously tiering lived only in post-compose traceability, so
    batch-extracted facts were left untiered until compose ran, and any step
    between extraction and compose (the author fact-floor gate, pipeline-mode
    detection) saw an untiered corpus.

    Returns (identity_count, contextual_count) — rows updated for each tier.
    """
    from baselayer.config import IDENTITY_PREDICATES
    placeholders = ",".join("?" * len(IDENTITY_PREDICATES))
    id_count = conn.execute(f"""
        UPDATE memory_facts SET knowledge_tier = 'identity'
        WHERE (knowledge_tier IS NULL OR knowledge_tier = 'untiered')
          AND predicate IN ({placeholders})
    """, list(IDENTITY_PREDICATES)).rowcount
    ctx_count = conn.execute("""
        UPDATE memory_facts SET knowledge_tier = 'contextual'
        WHERE knowledge_tier IS NULL OR knowledge_tier = 'untiered'
    """).rowcount
    return id_count, ctx_count


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


def embed_fact(fact_id: str, fact_text: str, category: str, collection, model,
               contract_version: str = None, grounding: str = None):
    """Embed a fact into the ChromaDB facts collection.

    contract_version is written as metadata only when set: Chroma rejects None
    values, and a legacy fact must stay WITHOUT the key so the version filter in
    find_similar_facts cannot match it."""
    embedding = model.encode([fact_text]).tolist()
    meta = {"fact_id": fact_id, "category": category}
    if contract_version:
        meta["turn_contract_version"] = contract_version
    if grounding:
        meta["grounding"] = grounding
    collection.add(
        ids=[fact_id],
        embeddings=embedding,
        documents=[fact_text],
        metadatas=[meta],
    )


# ---------------------------------------------------------------------------
# Main Processing Pipeline
# ---------------------------------------------------------------------------

def mark_turn_conversation_extracted(conn, conv_id: str) -> None:
    """Clear the importer's needs_extraction mark after a successful turn-mode
    extraction. The caller commits. A database without import_state (a turn table
    written some other way) has nothing to clear."""
    try:
        conn.execute("UPDATE import_state SET needs_extraction = 0 WHERE conversation_id = ?",
                     (conv_id,))
    except sqlite3.OperationalError:
        pass


def _turn_conversations_to_process(conn, source_filter: str = None) -> list:
    """Turn mode (D-108). Two differences from the legacy selector:

    - No MIN_MESSAGES_FOR_EXTRACTION. A history.jsonl session or a short
      conversation is the subject's own words; a conversation with no citable
      turn costs nothing, because a chunk with no citable turn makes no call.
    - Grown sessions come back. The importer rewrites a conversation whose source
      grew and sets import_state.needs_extraction. needs_extraction is also 1 on
      every fresh import, so on its own it cannot mean "grown"; grown is
      re-imported AFTER the last extraction (imported_at > processed_at). An
      errored conversation is therefore not retried here (use --retry-errors).
    - A conversation with a recorded failed chunk (extraction_chunks_failed) comes back,
      flagged `retry`: unless it also grew, only its failed chunks are called again.
    - Conversations whose turns hold nothing citable (no own-voice turn outside a
      fork/resume copy: harness children, tool-only sessions) are not selected. They
      could never yield a fact, and returning them made `--limit N` spend its N on
      them. A conversation with NO turn rows is still selected, so the missing-import
      error stays loud.
    """
    has_state = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                             "AND name='import_state'").fetchone() is not None
    grown = ("(s.needs_extraction = 1 AND s.imported_at > e.processed_at)"
             if has_state else "0")
    join = "LEFT JOIN import_state s ON c.id = s.conversation_id" if has_state else ""
    # A conversation with a recorded failed chunk comes back too, for that chunk alone.
    retry = (f"EXISTS (SELECT 1 FROM {FAILED_CHUNKS_TABLE} f WHERE f.conversation_id = c.id)"
             if failed_chunks_table_exists(conn) else "0")
    sql = f"""
        SELECT c.id, c.title, c.created_at, c.message_count, c.source,
               CASE WHEN e.conversation_id IS NOT NULL AND {grown} THEN 1 ELSE 0 END AS grown,
               CASE WHEN e.conversation_id IS NOT NULL AND {retry} THEN 1 ELSE 0 END AS retry
        FROM conversations c
        LEFT JOIN extraction_log e ON c.id = e.conversation_id
        {join}
        WHERE (e.conversation_id IS NULL OR {grown} OR {retry})
          AND (NOT EXISTS (SELECT 1 FROM turns t0 WHERE t0.conversation_id = c.id)
               OR EXISTS (SELECT 1 FROM turns t1 WHERE t1.conversation_id = c.id
                          AND t1.voice_class IN ('own_typed', 'own_dictated')
                          AND t1.duplicate_of IS NULL))
        {"AND c.source IN (" + ",".join("?" * len(_filter_sources(source_filter))) + ")"
         if source_filter else ""}
        ORDER BY c.created_at
    """
    return conn.execute(sql, _filter_sources(source_filter)).fetchall()


def _filter_sources(source_filter) -> tuple:
    """Stored source names a --source filter selects. "claude_code" selects every source
    with Claude Code session shape (config.CLAUDE_CODE_SOURCES): database copies and Desktop
    agent sessions are the same kind of conversation under a provenance-bearing name. Any
    other value, including a single family member, selects exactly that source."""
    if not source_filter:
        return ()
    if is_claude_code_source(source_filter) and source_family(source_filter) == source_filter:
        # the family name itself ("claude_code"), not one named member
        return tuple(CLAUDE_CODE_SOURCES)
    return (source_filter,)


def get_conversations_to_process(conn, limit: int = None, conv_id: str = None,
                                  source_filter: str = None,
                                  retry_errors: bool = False,
                                  turn_mode: bool = None,
                                  conv_ids: list = None) -> list[dict]:
    """Get list of conversations that haven't been processed yet.
    D-044: Now includes source for scope derivation.
    source_filter: if set, only return conversations from that source (e.g. 'claude_code').
    retry_errors: if True, also include conversations that previously errored (-1 in extraction_log).
    turn_mode: None reads BASELAYER_TURN_CONTRACT. Turn mode selects with
    _turn_conversations_to_process (no minimum message count; grown sessions).
    conv_ids: an explicit list (a pilot sample). Only those not yet in extraction_log
    are returned, in the order given, so one run record covers the whole sample."""
    if turn_mode is None:
        turn_mode = _turn_contract_enabled()
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
    elif conv_ids is not None:
        done = ({r[0] for r in conn.execute("SELECT conversation_id FROM extraction_log")}
                - failed_chunk_conversations(conn))
        found = {r[0]: r for r in conn.execute(
            "SELECT id, title, created_at, message_count, source FROM conversations "
            f"WHERE id IN ({','.join('?' * len(conv_ids))})", list(conv_ids)).fetchall()}             if conv_ids else {}
        rows = [found[i] for i in conv_ids if i in found and i not in done]
    elif turn_mode:
        rows = _turn_conversations_to_process(conn, source_filter)
    else:
        # Sources that use single-message conversations (text files, journals)
        # are exempt from the minimum message count filter
        single_msg_sources = ('text_file', 'journal')
        if source_filter:
            rows = conn.execute(f"""
                SELECT c.id, c.title, c.created_at, c.message_count, c.source
                FROM conversations c
                LEFT JOIN extraction_log e ON c.id = e.conversation_id
                WHERE e.conversation_id IS NULL
                  AND (c.message_count >= ? OR c.source IN (?, ?))
                  AND c.source IN ({",".join("?" * len(_filter_sources(source_filter)))})
                ORDER BY c.created_at
            """, (MIN_MESSAGES_FOR_EXTRACTION, *single_msg_sources,
                  *_filter_sources(source_filter))).fetchall()
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
         "message_count": r[3], "source": r[4] or "unknown",
         **({"grown": bool(r[5])} if len(r) > 5 else {}),
         **({"retry": bool(r[6])} if len(r) > 6 else {})}
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


_LEGACY_STAMPS: dict = {}


def _legacy_stamp(kind: str) -> dict:
    """Stamp for a legacy (ungated) fact: turn_contract_version is None."""
    if kind not in _LEGACY_STAMPS:
        builder = {"identity": build_identity_extraction_prompt,
                   "document": build_document_extraction_prompt}.get(kind, build_extraction_prompt)
        _LEGACY_STAMPS[kind] = _tc.extraction_stamp(
            _extraction_model_name(), legacy_prompt_hash(builder),
            contract_version=None, code_file=__file__)
    return _LEGACY_STAMPS[kind]


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

    This is the LEGACY (ungated) path. It refuses to run while turn-contract
    mode is on, so a direct caller cannot store ungated facts into a gated
    corpus; process_turn_conversation is the turn-contract equivalent.
    """
    if _turn_contract_enabled():
        raise TurnContractViolation(
            "process_conversation is the legacy, ungated path; with the turn contract on, "
            "use process_turn_conversation")
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

    # Legacy facts are stamped too (model, prompt hash, commit, repo-relative
    # code path), with turn_contract_version left NULL: they are NOT gated.
    if identity_only:
        stamp = _legacy_stamp("identity")
    elif document_mode:
        stamp = _legacy_stamp("document")
    else:
        stamp = _legacy_stamp("general")

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
                                qualifier=qualifier, stamp=stamp)
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
                               qualifier=qualifier, stamp=stamp)
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


def _should_warn_stale_vectors(vector_count: int, log_count: int) -> bool:
    """Stability guard predicate: a populated facts collection alongside an empty
    extraction_log is the signature of stale vectors surviving a SQLite-only clear,
    which makes AUDN NOOP new facts. Pure function so it can be unit-tested."""
    return vector_count > 0 and log_count == 0


# Low-yield warning threshold, in facts per 10,000 characters of extracted message
# text. Derived 2026-08-18 from a survey of every extraction database on disk
# (186 DBs under corpora/ and subjects/; 29 were person-mode full extractions with
# intact message text. Document-mode corpora are excluded because this guard never
# runs in document mode, and DBs with purged message text are excluded as
# unmeasurable). Healthy person-mode yields span 2.33-68.9 facts/10K chars; the
# floor is wollstonecraft_memory at 111 facts / 476,118 chars = 2.33/10K. The
# failure this guard exists to catch, stale ChromaDB vectors making AUDN NOOP every
# new fact (D-022), measured 12-42 facts where a clean run on the same 197,791-char
# corpus (zitkala) yields 150+, i.e. 0.61-2.12/10K. 2.2 is the midpoint of the
# [2.12, 2.33] gap between the worst measured collapse and the lowest measured
# healthy corpus. The previous absolute threshold (< 50 facts) fired on any corpus
# under ~60K chars regardless of rate: 12,000 chars correctly yielding 10 facts
# (8.3/10K, above the 7.58/10K zitkala reference rate) was warned at as a silent
# failure.
LOW_YIELD_WARN_PER_10K = 2.2


def _should_warn_low_fact_count(total_facts: int, errors: int, *, total_chars: int,
                                limit, conv_id, retry_errors: bool,
                                identity_only: bool, document_mode: bool) -> bool:
    """Stability guard predicate: a full extraction run (not limited, single-conversation,
    retry, identity, or document mode) that completes with no errors but yields facts at a
    rate below every healthy full extraction measured is the signature of a silent failure.
    total_chars is the character count of message text handed to the extractor, so the
    threshold scales with input instead of firing on an absolute count. Pure function so
    it can be unit-tested."""
    full_run = (limit is None and conv_id is None and not retry_errors
                and not identity_only and not document_mode)
    return (full_run and errors == 0
            and total_facts < LOW_YIELD_WARN_PER_10K * total_chars / 10_000)


def run_extraction(limit: int = None, conv_id: str = None,
                    identity_only: bool = False, source_filter: str = None,
                    retry_errors: bool = False, document_mode: bool = False,
                    conv_ids: list = None):
    """Main extraction pipeline.
    D-048: identity_only mode extracts personal identity facts from project conversations.
    S68: document_mode treats text as document corpus (patents, papers, reports).
    source_filter: restrict to conversations from a specific source (e.g. 'claude_code').
    retry_errors: clear errored entries and re-process those conversations.
    conv_ids: extract exactly these conversations (a pilot sample), in one run."""
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
    print(f"Dynamic fact cap (BASELAYER_DYNAMIC_CAP): {'ON' if _dynamic_cap_enabled() else 'OFF'}")
    print(f"Turn contract (BASELAYER_TURN_CONTRACT): "
          f"{TURN_CONTRACT_VERSION if _turn_contract_enabled() else 'OFF (legacy, ungated)'}")
    import baselayer.config as _cfg
    print(f"Database: {_cfg.DATABASE_FILE}")
    print("=" * 60)

    # Turn contract preflight: READ-ONLY, before create_tables() or the vector
    # store can write anything. A run aimed at the wrong database refuses here
    # without having altered it.
    turn_mode = _turn_contract_enabled()
    with contextlib.closing(get_db()) as _pre:
        if turn_mode:
            if document_mode:
                raise TurnContractViolation(
                    "--document-mode has no subject voice to ground facts in; the turn "
                    "contract does not apply to document corpora.")
            if not _tc.turn_rows_exist(_pre):
                raise TurnContractViolation(
                    f"turn-contract extraction needs the turn table '{_tc.TURN_TABLE}' with "
                    f"rows; this database has none. Import with the turn-contract importer.")
            assert_fresh_for_turn_contract(_pre)
            referent = turn_referent()
        else:
            assert_legacy_allowed(_pre)
            referent = None

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

        # Stability guard (no-silent-data-loss): a populated facts collection with
        # an empty extraction_log means a prior run's vectors survived a SQLite-only
        # clear. AUDN would then dedup every new fact against those ghost vectors and
        # mark them NOOP, silently storing ~0-12 facts instead of 200+. Warn and point
        # to --reset, which clears both SQLite and ChromaDB (D-022).
        if fact_collection is not None:
            try:
                _stale_vectors = fact_collection.count()
            except Exception:
                _stale_vectors = 0
            _log_count = conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]
            if _should_warn_stale_vectors(_stale_vectors, _log_count):
                print("\n" + "!" * 60)
                print(f"  WARNING: {_stale_vectors} fact vectors present but extraction_log is empty.")
                print("  AUDN will likely dedup new facts against these stale vectors (NOOP),")
                print("  producing far fewer facts than expected. Run `baselayer extract --reset`")
                print("  (clears SQLite + ChromaDB) before re-extracting.")
                print("!" * 60)

        # Second half of the preflight: the vector store, now that it is open.
        # Refuses before any model call if it holds vectors not stamped V.
        if turn_mode:
            assert_fresh_for_turn_contract(conn, fact_collection)

        # Get conversations to process
        # D-048: identity_only mode uses source_filter to target project conversations
        effective_source = source_filter
        if identity_only and not effective_source:
            effective_source = "claude_code"  # Default: extract identity from Claude Code sessions
        conversations = get_conversations_to_process(conn, limit=limit, conv_id=conv_id,
                                                      source_filter=effective_source,
                                                      retry_errors=retry_errors,
                                                      conv_ids=conv_ids)
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
        total_chars = 0
        errors = 0
        reset_usage()

        turn_record = None
        if turn_mode:
            # The turn path has its own loop (four phases, gate outside every
            # handler); the legacy loop below then iterates over nothing.
            turn_record, total_facts, total_chars, errors = _run_turn_loop(
                conversations, conn, fact_collection, embed_model,
                corrections=corrections, identity_only=identity_only, start_time=start_time,
                referent=referent)

        for i, conv in enumerate([] if turn_mode else conversations):
            try:
                # Input size for the low-yield guard. Must stay in sync with the
                # filter in get_conversation_messages(), so it counts exactly the
                # text the extractor is handed.
                total_chars += conn.execute("""
                    SELECT COALESCE(SUM(LENGTH(content_text)), 0)
                    FROM messages
                    WHERE conversation_id = ?
                      AND role IN ('user', 'assistant')
                      AND content_text IS NOT NULL
                      AND LENGTH(content_text) > 5
                """, (conv["id"],)).fetchone()[0]
                _conv_tok = _CURRENT_CONVERSATION.set(conv["id"])
                try:
                    facts_stored = process_conversation(conv, conn, fact_collection, embed_model,
                                                        corrections=corrections,
                                                        identity_only=identity_only,
                                                        document_mode=document_mode)
                finally:
                    _CURRENT_CONVERSATION.reset(_conv_tok)
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

        # Rule-based tiering, on the sequential path too.
        #
        # tier_facts_by_predicate had exactly two call sites: batch_extract.run_process
        # and _run_traceability, which runs AFTER compose. Sequential extraction never
        # called it, so a corpus extracted with `baselayer extract` reached authoring
        # with knowledge_tier='untiered' on every row. The author fact-floor gate counts
        # knowledge_tier='identity' and therefore read 0 and refused to run, on a corpus
        # whose other quality signals were fine.
        #
        # The gate had already been moved off `fact_type` for this exact reason in
        # 2026-05-19 (see the docstring on _check_fact_floor): that field was unpopulated
        # too. Switching the field did not fix it, because the new field was written on
        # two of the three extraction paths. Tiering here closes the third.
        #
        # Idempotent by construction: only rows still NULL or 'untiered' are touched, so
        # the later traceability call remains a safe no-op.
        if total_facts:
            _id, _ctx = tier_facts_by_predicate(conn)
            conn.commit()
            if _id or _ctx:
                print(f"Tiering facts by predicate: {_id} identity, {_ctx} contextual")

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
        print(_tc.usage_line(_tc.usage_totals(usage_calls())))
        print(f"Time: {total_time:.1f}s ({total_time/60:.1f} min)")
        if total > 0:
            print(f"Average: {total_facts/total:.1f} facts per conversation")
            print(f"Rate: {total/total_time:.2f} conversations/second")

        # Stability guard (no-silent-data-loss): a full run that yields very few
        # facts with no errors is the signature of a silent failure (stale vectors
        # causing AUDN NOOP, or input text flattened so the corpus collapsed to one
        # chunk). Only flag full runs — limited/single-conversation runs are
        # legitimately small.
        # Not applied on the turn path: its 2.2/10K floor was calibrated on
        # legacy extraction, where assistant text also yielded facts. The turn
        # path's own tripwires are the gate's suspect flags in the run record.
        if not turn_mode and _should_warn_low_fact_count(
                                       total_facts, errors, total_chars=total_chars,
                                       limit=limit, conv_id=conv_id,
                                       retry_errors=retry_errors, identity_only=identity_only,
                                       document_mode=document_mode):
            print("\n" + "!" * 60)
            print(f"  WARNING: only {total_facts} facts from a full extraction of {total} conversations")
            print(f"  ({total_chars:,} chars of message text = {total_facts / total_chars * 10000:.1f} facts/10K chars;")
            print(f"  every healthy extraction measured yields {LOW_YIELD_WARN_PER_10K}+/10K).")
            print("  This is the signature of a silent failure. Likely causes:")
            print("    - stale ChromaDB vectors making AUDN NOOP new facts (run --reset)")
            print("    - input text flattened (lost paragraph breaks), collapsing to one chunk")
            print("  Verify the fact count before running author/compose on this data.")
            print("!" * 60)

        if turn_record is not None and turn_record.c["conversations_without_turns"]:
            print(f"\nERROR: {turn_record.c['conversations_without_turns']} conversations have no "
                  f"rows in the turn table; they were not extracted. See the run record.")
            raise SystemExit(2)
        if turn_record is not None and errors:
            n_open = turn_record.c["chunks_failed_open"]
            print(f"\nERROR: {errors} extraction error(s): {n_open} failed chunk(s) recorded "
                  f"for retry, {errors - n_open} conversation(s) failed outright. Nothing a "
                  f"failed chunk would have produced is stored; the next run retries the "
                  f"failed chunks (extraction_chunks_failed) and --retry-errors the failed "
                  f"conversations. See the run record.")
            raise SystemExit(1)


def _run_turn_loop(conversations, conn, fact_collection, embed_model, *, corrections,
                   identity_only, start_time, referent):
    """The turn-contract loop. The per-run record is written in a `finally`
    (which catches nothing), so an aborted run still leaves its counts."""
    stamps = turn_stamps()
    settings = turn_run_settings()
    settings["referent_names"] = len(referent.names)     # a count; the names stay in the config
    record = _tc.ExtractionRunRecord(
        "turn", settings, stamp={"general": stamps[False], "project": stamps[True]})
    reset_response_failures()
    print(f"\nTurn contract {TURN_CONTRACT_VERSION}: grounded facts only.")
    for k, v in settings.items():
        print(f"  {k}: {v}")
    print(f"  git_commit: {stamps[False]['git_commit']}  code_path: {stamps[False]['code_path']}")
    total = len(conversations)
    total_facts = errors = 0
    completed = False
    try:
        for i, conv in enumerate(conversations):
            _conv_tok = _CURRENT_CONVERSATION.set(conv["id"])
            open_before = record.c["chunks_failed_open"]
            try:
                if conv.get("retry") and not conv.get("grown"):
                    # only the recorded failed chunks; the rest are already stored
                    n, _left = retry_failed_chunks(conv, conn, fact_collection, embed_model,
                                                   stamps=stamps, record=record,
                                                   referent=referent, corrections=corrections,
                                                   identity_only=identity_only)
                else:
                    n = process_turn_conversation(conv, conn, fact_collection, embed_model,
                                                  stamps=stamps, record=record,
                                                  referent=referent, corrections=corrections,
                                                  identity_only=identity_only)
            except SpendCeilingExceeded as e:
                record.notes.append(f"spend ceiling: {e}")
                raise
            finally:
                _CURRENT_CONVERSATION.reset(_conv_tok)
            if n < 0:
                errors += 1
            else:
                total_facts += n
            errors += record.c["chunks_failed_open"] - open_before
            if (i + 1) % BATCH_SIZE == 0 or i == total - 1:
                elapsed = time.time() - start_time
                print(f"  [{i+1}/{total}] Facts: {total_facts} | Errors: {errors} | "
                      f"gate rejected {sum(record.rejected.values())} of "
                      f"{record.c['candidates']} | {elapsed:.0f}s")
        completed = True
    finally:
        record.response_failures = response_failures()
        record.usage_calls = usage_calls()
        if not completed:
            record.notes.append("run aborted by an exception; counts are partial")
        for line in record.summary_lines():
            print(line)
        path = record.write(conn)
        print(f"  run record: {path}")
    return record, total_facts, record.c["turns_chars"], errors


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
                        help="DESTRUCTIVE full extraction reset: deletes extraction-sourced "
                             "facts, the extraction log and fact relationships, and drops the "
                             "fact vector collection (user corrections survive). Prefer building "
                             "into a fresh corpus directory.")
    parser.add_argument("--identity-only", action="store_true",
                        help="D-048: Extract only identity-relevant facts from project conversations "
                             "(strips code/tools, keeps user directives and behavioral patterns)")
    parser.add_argument("--source", type=str, default=None,
                        help="Filter to conversations from a specific source (chatgpt, claude_web, "
                             "claude_code_history, meeting, text_file, ...). 'claude_code' selects "
                             "every source with Claude Code session shape (claude_code, "
                             "claude_code_db_copy, claude_desktop_agent); name one of those to "
                             "select it alone.")
    parser.add_argument("--document-mode", action="store_true",
                        help="S68: Treat text as document corpus (patents, papers, reports). "
                             "Extracts the document's implicit worldview rather than personal facts.")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Clear errored extraction_log entries (-1) and re-process those conversations")
    parser.add_argument("--turn-contract", action="store_true",
                        help="Extract under the turn contract (docs/core/TURN_CONTRACT.md): "
                             "turn-bounded chunks, only the subject's own turns citable, every "
                             "fact grounded in verbatim spans and gated. Same as "
                             "BASELAYER_TURN_CONTRACT=1. Needs a fresh corpus directory.")

    args = parser.parse_args()
    if args.turn_contract:
        os.environ["BASELAYER_TURN_CONTRACT"] = "1"

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
