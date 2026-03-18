"""
Shared Configuration — Single Source of Truth for Memory System Constants

All hardcoded paths, model names, thresholds, token budgets, and category
definitions used across the pipeline scripts. Scripts import from here
rather than defining their own copies.

Organization:
  === ACTIVE PIPELINE CONSTANTS ===   — Used by the current 4-step pipeline
  === ARCHIVED (unused, kept for reference) ===  — Dead constants from removed steps;
      kept to avoid breaking any external code that may import them, but not
      used by the simplified pipeline (Import → Extract → Author → Compose).
"""

import contextlib
import os
import sqlite3
from pathlib import Path


# ============================================================
# === ACTIVE PIPELINE CONSTANTS ==============================
# ============================================================

# ==========================================================================
# PATHS
# ==========================================================================
# Data directory resolution (in priority order):
#   1. MEMORY_SYSTEM_ROOT env var (explicit override, supports multi-user D-044)
#   2. Development mode: parent of scripts/ directory (memory_system/)
#   3. Installed mode: ~/.baselayer/ (pip install baselayer)
#
# DATA ISOLATION (D-044): Set MEMORY_SYSTEM_ROOT env var to point all data
# paths at a different root (e.g., other_user/). Scripts stay shared;
# only the data directory changes.
#   export MEMORY_SYSTEM_ROOT=/path/to/other_user
#   python extract_facts.py  # reads/writes other_user/data/...

def _resolve_project_root():
    """Determine the data root directory."""
    # 1. Explicit env var override
    env_root = os.environ.get("MEMORY_SYSTEM_ROOT")
    if env_root:
        root = Path(env_root).resolve()
        if not root.exists():
            raise FileNotFoundError(
                f"MEMORY_SYSTEM_ROOT directory does not exist: {root}"
            )
        if not root.is_dir():
            raise NotADirectoryError(
                f"MEMORY_SYSTEM_ROOT is not a directory: {root}"
            )
        return root
    # 2. Development mode: src/baselayer/ lives inside memory_system/src/
    dev_root = Path(__file__).parent.parent.parent
    if (dev_root / "data").exists() or (dev_root / "src").exists():
        return dev_root
    # 3. Installed mode: default to ~/.baselayer/
    return Path.home() / ".baselayer"

PROJECT_ROOT = _resolve_project_root()

# SQLite database (conversations, facts, corrections, scores, logs)
DATABASE_FILE = PROJECT_ROOT / "data" / "database" / "memory.db"


def get_db(db_path=None):
    """Return a SQLite connection with row_factory set.

    Use with contextlib.closing() to ensure the connection is closed:
        with contextlib.closing(get_db()) as conn:
            rows = conn.execute("SELECT ...").fetchall()

    Note: sqlite3 context manager commits/rollbacks but does NOT close.
    contextlib.closing() handles the close on exit.
    """
    conn = sqlite3.connect(str(db_path or DATABASE_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ChromaDB persistent vector storage directory
VECTORS_DIR = PROJECT_ROOT / "data" / "vectors"

# Raw ChatGPT export (used by import_conversations.py)
CONVERSATIONS_FILE = PROJECT_ROOT / "data" / "raw" / "conversations.json"

# Extraction progress tracking (for resuming interrupted runs)
PROGRESS_FILE = PROJECT_ROOT / "data" / "database" / "extraction_progress.json"


# ==========================================================================
# MODELS
# ==========================================================================

# Sentence-transformer model for vector embeddings (384 dimensions, ~80 MB)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Local Ollama endpoint for LLM calls (Qwen)
OLLAMA_URL = "http://localhost:11434/api/generate"

# LLM used for fact extraction, AUDN decisions, identity selection,
# sentiment scoring, and significance categorization
LLM_MODEL = "qwen2.5:14b"

# ==========================================================================
# EXTRACTION BACKEND (extract_facts.py)
# ==========================================================================
# Which LLM backend to use for fact extraction.
# "ollama" = local Qwen (free, slow, requires GPU + Ollama)
# "anthropic" = Haiku API (fast, cheap ~$0.01/conversation, requires API key)
# Set via BASELAYER_EXTRACTION_BACKEND env var or change default here.

EXTRACTION_BACKEND = os.environ.get("BASELAYER_EXTRACTION_BACKEND", "anthropic")
EXTRACTION_API_MODEL = "claude-haiku-4-5-20251001"  # Fast + cheap for extraction


# ==========================================================================
# TOKEN BUDGETS (assemble_brief.py)
# ==========================================================================
# Approximate conversion: 1 token ~ 4 characters for English text.
# Relaxed for local storage usage — no per-token cost constraint.
# Claude's 200K context window makes 5,000 tokens trivial.
# Updated Session 38: Identity expanded to 3,500 for three-layer architecture.

CHARS_PER_TOKEN = 4

IDENTITY_TOKEN_BUDGET = 3500   # Block 1: who you are (always-on, 3 layers)
THEME_TOKEN_BUDGET = 800       # Block 2: what matters right now (retrieved)
EPISODE_TOKEN_BUDGET = 600     # Block 3: "I remember when..." moments (retrieved)
TOTAL_TOKEN_BUDGET = 5000      # Combined budget for the full brief


# ==========================================================================
# RETRIEVAL SETTINGS (assemble_brief.py)
# ==========================================================================

# Recency decay: facts older than this (in days) get zero recency bonus.
# ~3 years. Recent facts within this window get proportional boost.
RECENCY_DECAY_WINDOW_DAYS = 1100

THEME_FACTS_TO_RETRIEVE = 40   # ChromaDB candidates for theme block
THEME_SUMMARIES_TO_RETRIEVE = 12
THEME_TURN_PAIRS_TO_RETRIEVE = 12
THEME_FACTS_TO_KEEP = 25       # Facts kept after dedup/scoring
EPISODE_COUNT = 5              # Episodic memory slots in the brief
ASSOCIATIVE_BOOST = 0.20       # 20% score boost for co-occurring facts


# ============================================================
# === ARCHIVED (unused, kept for reference) ==================
# ============================================================

# ==========================================================================
# ARCHIVED — SCORING THRESHOLDS — NOVELTY (surprise_scoring.py)
# ==========================================================================
# DEAD after pipeline simplification (S79). Scripts moved to archive.

NOVELTY_SKIP = 0.3             # Below this = clearly redundant, skip
NOVELTY_STORE = 0.8            # Above this = clearly novel, store immediately
# Between SKIP and STORE = borderline, send to significance scoring


# ==========================================================================
# ARCHIVED — SCORING THRESHOLDS — RECURRENCE FLOOR (surprise_scoring.py, score_facts.py)
# ==========================================================================
# Highly persistent topics cannot score below a minimum, regardless of depth.
# This catches identity-significant topics like cars, hobbies, etc.
# Session 55: Thresholds adjusted for windowed recurrence (temporal dedup).
# Raw recurrence 50/30 → windowed ~30/18 after 24h dedup.

RECURRENCE_FLOOR_HIGH = 30             # 30+ windowed recurrences (was 50 raw)
RECURRENCE_FLOOR_MID = 18              # 18-29 windowed recurrences (was 30 raw)
RECURRENCE_FLOOR_HIGH_SCORE = 7        # Minimum score when floor_high applies
RECURRENCE_FLOOR_MID_SCORE = 6         # Minimum score when floor_mid applies
RECURRENCE_MIN_SPAN_DAYS = 365         # Must span at least 1 year for floor to apply


# ==========================================================================
# ARCHIVED — SCORING FORMULA WEIGHTS (surprise_scoring.py)
# ==========================================================================
# Final significance = max(recurrence_floor, weighted_score)
# Where weighted_score = WEIGHT_NOVELTY * novelty
#                      + WEIGHT_RECURRENCE * recurrence_normalized
#                      + WEIGHT_DEPTH * depth_score

WEIGHT_NOVELTY = 0.40
WEIGHT_RECURRENCE = 0.35
WEIGHT_DEPTH = 0.25


# ============================================================
# === ACTIVE PIPELINE CONSTANTS (continued) ==================
# ============================================================

# ==========================================================================
# FACT EXTRACTION SETTINGS (extract_facts.py)
# ==========================================================================

SIMILARITY_THRESHOLD = 0.85            # Above this = likely the same fact (dedup)
EXTRACTION_BATCH_SIZE = 10             # Conversations per progress update
MAX_RETRIES = 2                        # Retries on JSON parse failure
MIN_FACT_LENGTH = 10                   # Skip very short extracted facts
MAX_FACTS_PER_CONVERSATION = 20        # Legacy default cap (use EXTRACTION_CAPS for scaling)
MIN_MESSAGES_FOR_EXTRACTION = 6        # Skip conversations with fewer messages


# ==========================================================================
# EXTRACTION CAP SCALING (Session 55 — Plan 2)
# ==========================================================================
# Scales max facts and input text budget based on conversation message count.
# Addresses double truncation: long conversations were both input-capped (12K)
# AND output-capped (20 facts). Deeper topics in long conversations were
# systematically under-extracted.
#
# Keys are (min_messages, max_messages) tuples.
# Values are {"max_facts": int, "input_char_budget": int}.
# Conversations are matched to the first range where message_count falls.

EXTRACTION_CAPS = {
    "tiers": [
        # Short conversations: conservative extraction
        {"min_messages": 1,  "max_messages": 10,  "max_facts": 10, "input_char_budget": 12000},
        # Medium conversations: standard extraction (matches legacy 20-fact cap)
        {"min_messages": 11, "max_messages": 30,  "max_facts": 20, "input_char_budget": 18000},
        # Long conversations: expanded extraction
        {"min_messages": 31, "max_messages": 60,  "max_facts": 35, "input_char_budget": 24000},
        # Very long conversations: maximum extraction
        {"min_messages": 61, "max_messages": 99999, "max_facts": 50, "input_char_budget": 24000},
    ],
    # Session 65: Character-based tiers for long single-message imports (autobiographies, chapters).
    # Used alongside message tiers — whichever gives higher max_facts wins.
    "char_tiers": [
        {"min_chars": 0,      "max_chars": 12000,    "max_facts": 10, "input_char_budget": 12000},
        {"min_chars": 12001,  "max_chars": 30000,    "max_facts": 20, "input_char_budget": 18000},
        {"min_chars": 30001,  "max_chars": 60000,    "max_facts": 35, "input_char_budget": 24000},
        {"min_chars": 60001,  "max_chars": 99999999, "max_facts": 200, "input_char_budget": 24000},
    ],
    # Absolute ceiling regardless of message count
    "max_facts_ceiling": 200,
    "max_input_char_budget": 24000,
}


# ==========================================================================
# TEMPORAL RECURRENCE DEDUP (Session 55 — Plan 3)
# ==========================================================================
# 24-hour windowing for recurrence counting. 20 mentions in one day = 1
# windowed recurrence, not 20. Cross-model dedup: same topic, same day,
# ChatGPT + Claude = 1 recurrence.
#
# Normalization ceiling lowered from 300 → 150 because windowed counts
# are roughly half of raw counts.

RECURRENCE_NORMALIZATION_CEILING = 150  # ARCHIVED — unused; only referenced by archived score_facts.py
RECURRENCE_WINDOW_HOURS = 24           # ARCHIVED — unused; only referenced by archived score_facts.py


# ==========================================================================
# EMBEDDING SETTINGS (embed.py)
# ==========================================================================

EMBEDDING_BATCH_SIZE = 100             # Messages per batch when embedding
MESSAGES_COLLECTION_NAME = "messages"  # ChromaDB collection for message embeddings


def chromadb_dist_to_similarity(dist):
    """Convert ChromaDB distance to cosine similarity (0-1).

    ChromaDB collections may use L2 distance (default) or cosine distance.
    For L2 on normalized vectors (MiniLM): cos_sim = 1 - dist²/2.
    For cosine distance: cos_sim = 1 - dist.

    L2 distances are always >= 0. For normalized vectors, L2 <= 2.
    When dist <= 2, we use the L2 formula. This also works acceptably
    for cosine-distance collections since the difference is small for
    the values we care about.
    """
    if dist <= 0:
        return 1.0
    # L2 formula for normalized vectors: cos_sim = 1 - L2²/2
    sim = 1.0 - (dist ** 2) / 2.0
    return round(max(0.0, min(1.0, sim)), 4)


# ==========================================================================
# VALID FACT CATEGORIES (extract_facts.py)
# ==========================================================================
# Canonical set used to normalize freeform LLM output.
# D-022: Added negative_trait category.

VALID_CATEGORIES = {
    "preference",
    "biography",
    "project",
    "relationship",
    "interest",
    "skill",
    "value",
    "habit",
    "opinion",
    "goal",
    "negative_trait",
}


# ==========================================================================
# VALID FACT CLASSES (extract_facts.py)
# ==========================================================================
# Binary classification for temporal processing (D-038, TEMPORAL_PROCESSING_REVIEW).
# Events are immutable anchors; states can be contradicted.

VALID_FACT_CLASSES = {"event", "state", "unclassified"}


# ==========================================================================
# TEMPORAL QUALIFIER SETTINGS (assemble_brief.py)
# ==========================================================================
# State-facts older than this threshold get "(as of YYYY-MM)" in the brief.
# Events are never qualified (immutable). Past-tagged facts skip (already marked).
# Per TEMPORAL_PROCESSING_REVIEW V4 — annotation, not penalty.

TEMPORAL_QUALIFIER_THRESHOLD_DAYS = 240  # ~8 months


# ==========================================================================
# CONTRADICTION PIPELINE SETTINGS
# ==========================================================================
# Used by detect_contradictions.py (root-level script, not in default pipeline).
# detect_contradictions.py is not part of the 4-step pipeline but is not archived.

CONTRADICTION_SIMILARITY_THRESHOLD = 0.50  # MiniLM similarity threshold for candidate pairs


# ==========================================================================
# ARCHIVED — TIER RECLASSIFICATION (reclassify_tiers.py)
# ==========================================================================
# DEAD after pipeline simplification (S79: 14 steps → 4 steps).
# Script moved to scripts/archive/dead_pipeline_steps/.
# Constants kept to avoid breaking any remaining imports.

RECLASSIFY_MODEL = "claude-sonnet-4-20250514"
RECLASSIFY_BATCH_SIZE = 10


# ==========================================================================
# ARCHIVED — ENRICHMENT CONSOLIDATION (consolidate_enrichments.py)
# ==========================================================================
# DEAD after pipeline simplification (S79: 14 steps → 4 steps).
# Script moved to scripts/archive/dead_pipeline_steps/.
# Constants kept to avoid breaking any remaining imports.

CONSOLIDATION_MAX_CLUSTER_SIZE = 15


# ==========================================================================
# SCOPED MEMORY (D-044)
# ==========================================================================
# Facts are scope-tagged by interaction mode. Personal feeds identity blocks.
# Project feeds project briefs (CLAUDE.md). Anchors cross scopes.

SCOPE_SOURCE_MAPPING = {
    "chatgpt": "personal",
    "claude_web": "personal",
    "claude_code": "project",
    # Future: "slack" -> "professional", "email" -> "professional"
}

DEFAULT_SCOPE = "personal"


# ==========================================================================
# AUTHORING EXCLUSION PATTERNS (D-040, D-044)
# ==========================================================================
# Facts matching these patterns are excluded from identity block authoring
# queries. Prevents meta-contamination: system process references, identity
# block mentions, decision references, collective review mentions.
# Applied as case-insensitive substring matches on fact_text.

# ==========================================================================
# IDENTITY LAYER PATHS (D-043 — Three-Layer Architecture)
# ==========================================================================
# Pre-authored identity layers stored as markdown files with injectable blocks.
# Each file has a metadata header above --- and injectable text below.
# assemble_brief.py reads the injectable blocks at assembly time.

IDENTITY_LAYERS_DIR = PROJECT_ROOT / "data" / "identity_layers"
ANCHORS_LAYER_FILE = IDENTITY_LAYERS_DIR / "anchors_v4.md"
CORE_LAYER_FILE = IDENTITY_LAYERS_DIR / "core_v4.md"
PREDICTIONS_LAYER_FILE = IDENTITY_LAYERS_DIR / "predictions_v4.md"
UNIFIED_BRIEF_FILE = IDENTITY_LAYERS_DIR / "brief_v5_clean.md"  # Stripped citations — for serving
UNIFIED_BRIEF_CITED_FILE = IDENTITY_LAYERS_DIR / "brief_v5.md"  # With citations — for audit
IDENTITY_MODEL_FILE = IDENTITY_LAYERS_DIR / "identity_model.md"  # D-081: brief + layers combined — primary AI artifact

# D-054: Agent pipeline directories
AGENT_DEFINITIONS_DIR = PROJECT_ROOT / "agents"
AGENT_RUNS_DIR = IDENTITY_LAYERS_DIR / "runs"


# ==========================================================================
# LLM PROVIDER CONFIGURATION (D-052)
# ==========================================================================
# Default models per pipeline role. All Anthropic for v1.
# Override via BASELAYER_LLM_{ROLE} env vars (e.g. BASELAYER_LLM_EXTRACTION=gpt-4o-mini).
# Model prefix determines provider: claude-* -> Anthropic, gpt-*/o1-*/o3-* -> OpenAI,
# gemini-* -> Google, ollama:* -> local Ollama.
#
# Non-Anthropic providers require additional packages:
#   pip install openai              # For gpt-*, o1-*, o3-*
#   pip install google-generativeai # For gemini-*

_LLM_DEFAULTS = {
    "extraction": "claude-haiku-4-5-20251001",
    "classification": "claude-haiku-4-5-20251001",   # LEGACY — classification removed in S79
    "tiering": "claude-sonnet-4-20250514",             # LEGACY — tiering removed in S79
    "authoring": "claude-sonnet-4-20250514",
    "review": "claude-opus-4-20250514",                # Used as compose model in agent_pipeline.py
    "contradiction": "claude-sonnet-4-20250514",       # Used by detect_contradictions.py (experimental)
}

LLM_PROVIDER_CONFIG = {
    role: os.environ.get(f"BASELAYER_LLM_{role.upper()}", default_model)
    for role, default_model in _LLM_DEFAULTS.items()
}


# ==========================================================================
# LAYER GENERATION MODEL (author_layers.py)
# ==========================================================================
# Model used for automated layer generation (e.g., new user pipeline).
# Sonnet for layer authoring, Opus for brief composition.
# Collective review removed in S79 (ceremonial per ablation).
# These reference LLM_PROVIDER_CONFIG for forwards compatibility but
# remain importable as before for backwards compatibility.

LAYER_GENERATION_MODEL = LLM_PROVIDER_CONFIG["authoring"]
# LAYER_REVIEW_MODEL is actively used as the compose model in agent_pipeline.py.
# LAYER_SELF_REVIEW_MODEL is imported by author_layers.py (legacy, collective review path).
LAYER_REVIEW_MODEL = LLM_PROVIDER_CONFIG["review"]
LAYER_SELF_REVIEW_MODEL = LLM_PROVIDER_CONFIG["authoring"]

# ==========================================================================
# ARCHIVED — COLLECTIVE REVIEW PIPELINE (author_layers.py)
# ==========================================================================
# DEAD after pipeline simplification (S79: 14 steps → 4 steps).
# Ablation proved Collective review is ceremonial (C11 no-review = 87 vs C0 full = 83).
# Constants kept because author_layers.py and agent_pipeline.py still import them.

REVIEW_DEPLOY_THRESHOLD = 75       # Combined score to deploy without quality flag
REVIEW_MAX_ITERATIONS = 3          # Max generate-review cycles per layer
REVIEW_IMPROVEMENT_MIN = 3         # Min score improvement to continue iterating
REVIEW_MIN_FACTS_FOR_GENERATION = 3  # Skip layer if fewer input facts
REVIEW_SELF_REVIEW_GATE = 60      # Sonnet self-review must pass this to proceed to Opus

# Data density tiers (fact count thresholds)
REVIEW_TIER_THIN = 100             # < 100 facts: Sonnet self-review only
REVIEW_TIER_STANDARD = 500         # 100-500 facts: + single Opus pass
# 500+ facts: full iterative Opus review


# ==========================================================================
# DOMAIN BALANCE (D-055 — authoring domain cap)
# ==========================================================================
# Facts matching these keywords are classified as belonging to a domain.
# No single domain's facts can exceed this percentage of total facts sent
# to a layer generator. Prevents trading (or any other high-recurrence
# domain) from crowding out cross-domain behavioral signal.

AUTHORING_MAX_DOMAIN_PERCENT = 25  # No domain > 25% of facts per layer

AUTHORING_DOMAIN_KEYWORDS = {
    "trading": [
        "trading", "trade", "trades", "trader", "scalp", "scalping",
        "position size", "stop out", "overtrad", "P/L", "profit", "loss",
        "chart", "setup", "entry", "ATR", "MACD", "ORB", "Level II",
        "streak", "revenge trad", "win rate", "risk tier", "capital usage",
    ],
}


AUTHORING_EXCLUSION_PATTERNS = [
    # System process references
    "identity block",
    "identity layer",
    "block #",
    "block number",
    "blind authoring",
    "collective review",
    "extraction process",
    "extraction pipeline",
    "fact extraction",
    "pipeline step",
    "authoring process",
    "brief assembly",
    # Design decision references (D-001 through D-048+)
    "D-0",
    "design decision",
    # Project-specific tooling
    "CLAUDE.md",
    "ChromaDB",
    "assemble_brief",
    "extract_facts",
    "MCP server",
    "mcp_server",
    "baselayer",
    "base layer pipeline",
    # Technical stack references (system-meta, not identity)
    "SQLite",
    "Ollama",
    "embedding model",
    "vector database",
    "memory system project",
    "memory system's",
    "memory system uses",
]


# ==========================================================================
# VALID FACT TYPES (D-043 — Three-Layer Architecture)
# ==========================================================================
# Classification for routing facts to identity block layers.
# Biographical -> CORE, Behavioral -> PREDICTIONS, Positional -> ANCHORS.

VALID_FACT_TYPES = {"biographical", "behavioral", "positional", "preference", "unclassified"}


# ==========================================================================
# VALID COMMITMENT DEPTHS (D-043 / Frankfurt hierarchy)
# ==========================================================================
# Strength of belief/commitment. Preference = malleable, Position = argued
# but revisable, Conviction = foundational, identity-constitutive.

VALID_COMMITMENT_DEPTHS = {"factual", "preference", "position", "conviction", "unclassified"}


# ==========================================================================
# CONSTRAINED PREDICATES (D-056 Tier 2 — Structured Extraction)
# ==========================================================================
# Canonical predicate vocabulary for structured fact extraction.
# LLM is instructed to use ONLY these predicates. normalize_predicate()
# maps common variants back to canonical form.
# 47 verbs covering: ownership, values, activities, biography, relationships,
# skills, emotions, decisions.
# Session 49: +6 predicates. Session 52: +2 (plays, monitors).
# Session 55: +8 relationship predicates (Plan 1 — 0.8% → 3-5% target).

CONSTRAINED_PREDICATES = [
    "owns", "values", "practices", "studies", "prefers", "avoids",
    "works_at", "lives_in", "married_to", "raised_in", "graduated_from",
    "manages", "builds", "believes", "fears", "enjoys",
    "dislikes", "struggles_with", "excels_at", "identifies_as",
    "maintains", "follows", "aspires_to", "lost", "founded",
    "parents", "experienced", "learned", "decided", "prioritizes",
    # Session 49: Collective-approved additions
    "unknown",        # fallback for unmapped predicates (filterable, not silent)
    "attended",       # distinct from graduated_from (attending ≠ graduating)
    "interested_in",  # distinct from follows (passive interest ≠ active tracking)
    "wants_to",       # distinct from aspires_to (want ≠ aspiration)
    "loves",          # distinct from enjoys (intensity preserved for commitment_depth)
    "hates",          # distinct from dislikes (intensity preserved for commitment_depth)
    # Session 52: predicate audit additions
    "plays",          # games, sports, instruments
    "monitors",       # active observation, distinct from follows
    # Session 55: relationship extraction predicates (Plan 1 — 0.8% → 3-5% target)
    "relates_to",         # generic relationship (fallback when specific type unclear)
    "collaborates_with",  # professional or creative collaboration
    "mentored_by",        # mentor/mentee relationship (directional: subject was mentored)
    "raised_by",          # parental/guardian relationship (child's perspective)
    "friends_with",       # friendship
    "reports_to",         # organizational hierarchy
    "admires",            # respect/admiration relationship
    "conflicts_with",     # tension/disagreement relationship
]
