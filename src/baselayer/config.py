"""
Shared Configuration — Single Source of Truth for Memory System Constants

All hardcoded paths, model names, thresholds, token budgets, and category
definitions used across the pipeline scripts. Scripts import from here
rather than defining their own copies.

Organization:
  === ACTIVE PIPELINE CONSTANTS ===   — Used by the current 5-step pipeline
      (Import → Extract → Embed → Author → Compose).
  === ARCHIVED (unused, kept for reference) ===  — Dead constants from removed steps;
      kept to avoid breaking any external code that may import them, but not
      used by the simplified 5-step pipeline.
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


def database_initialized(db_path=None):
    """True if the database file exists AND carries the core schema.

    File existence alone is the wrong test: sqlite3.connect() creates an empty
    file before the first query runs, so a failed first `import` leaves a
    zero-table memory.db behind. Checking only the file misreads that wreckage
    as an initialised database (import then dies on "no such table" while init
    refuses to run). The `conversations` table is created unconditionally by
    init_database.py, so its presence is the marker for "init has run".
    """
    path = Path(db_path or DATABASE_FILE)
    if not path.exists():
        return False
    try:
        # Read-only URI open: this check must never be the thing that creates the file.
        with contextlib.closing(
            sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        ) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        # Unreadable or corrupt file: not a usable initialised database.
        return False


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

# D-085 (S98): Compose fact sampling — scales with corpus size
# Small corpora (<500 identity facts): sample all up to 100
# Large corpora (500+): sample up to 300 to capture V2 depth
COMPOSE_FACT_LIMIT_SMALL = 100   # corpora with <500 identity-tier facts
COMPOSE_FACT_LIMIT_LARGE = 300   # corpora with 500+ identity-tier facts
COMPOSE_FACT_THRESHOLD = 500     # identity-tier fact count that triggers large limit


def compute_source_fingerprint(source_dir, extraction_model=None):
    """S98 Phase 3B: Compute input fingerprint for manifest gate.

    Fingerprint includes: file list + total bytes + extraction model + extraction caps.
    Changes to any of these mean the pipeline should re-run.
    """
    import hashlib
    source_path = Path(source_dir)
    if not source_path.exists():
        return None

    h = hashlib.md5()

    # File list + sizes (sorted for determinism)
    files = sorted(source_path.glob("*"))
    for f in files:
        if f.is_file():
            h.update(f.name.encode())
            h.update(str(f.stat().st_size).encode())

    # Extraction model
    model = extraction_model or EXTRACTION_API_MODEL
    h.update(model.encode())

    # Extraction caps (ceiling + budget)
    h.update(str(EXTRACTION_CAPS.get("max_facts_ceiling", 600)).encode())

    return h.hexdigest()


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
        {"min_chars": 60001,  "max_chars": 200000,   "max_facts": 200, "input_char_budget": 24000},
        # S97: Large documents (textbooks, full corpora >200K chars). 833K agentic patterns was hitting 200 ceiling.
        {"min_chars": 200001, "max_chars": 500000,   "max_facts": 400, "input_char_budget": 24000},
        {"min_chars": 500001, "max_chars": 99999999, "max_facts": 600, "input_char_budget": 24000},
    ],
    # Absolute ceiling regardless of message count (S97: raised from 200 for large documents)
    "max_facts_ceiling": 600,
    # NOTE (B-halt / dynamic fact cap): when BASELAYER_DYNAMIC_CAP is enabled the
    # static tier max_facts above is demoted to a density-derived runaway backstop
    # (see DYNAMIC_CAP_DEFAULT + CHARS_PER_FACT below). The tier values here are
    # unchanged and remain the sole cap when the flag is off.
    # 2026-05-17: per-source overrides for the absolute ceiling. Multi-day Claude
    # Code sessions (compacted instead of restarted) can produce thousands of
    # candidate facts across windows; the default 600 trips the >20% coverage
    # gate. Per-source override preserves the gate for ChatGPT/journals while
    # giving dense project sources room to land their content.
    "max_facts_ceiling_by_source": {
        "claude_code": 1500,
    },
    "max_input_char_budget": 24000,
}


# ==========================================================================
# DYNAMIC FACT CAP — "B-halt" (default OFF)
# ==========================================================================
# Gated behind the BASELAYER_DYNAMIC_CAP env var. When unset/false, extraction
# behavior is byte-for-byte identical to the static-cap pipeline above. When
# enabled, three things change (all in extract_facts.py):
#   1. per_chunk_cap = max_facts (drops the min(50, ...) emission-order cut —
#      the main leak on dense chunks).
#   2. the doc-level max_facts becomes a density-derived runaway backstop:
#      min(source_ceiling, ceil(total_chars / CHARS_PER_FACT)).
#   3. the silent confidence-sort truncation is removed, so on breach the S98
#      coverage gate HALTS rather than quietly keeping the top-N.
# The S98 coverage gate and the S65/S106 stale-vector guards are unchanged.
#
# DYNAMIC_CAP_DEFAULT is the config mirror of the env var: it is the fallback
# used only when BASELAYER_DYNAMIC_CAP is unset. Flip it to True here to enable
# B-halt globally without setting the env var. Left False so the default path
# is unchanged. The env var, when present, always wins over this mirror.
DYNAMIC_CAP_DEFAULT = False

# Density estimate for the B-halt backstop: roughly one extracted fact per this
# many input characters. EMPIRICALLY TUNABLE — this 175 is a starting point, not
# a measured constant. Derive it from a real dense-doc run before trusting it.
CHARS_PER_FACT = 175

# Per-CHUNK extraction ask ceiling (B-halt, flag-on only). The doc-level cap is
# density-scaled and aggregates across chunks, but the per-CHUNK ask is bounded
# by the API output-token ceiling: asking the extraction model for many more than
# this in one chunk overflows max_tokens, truncates the JSON response, and loses
# the entire chunk's facts (observed on a document build: chunks of about 130 facts
# succeeded, about 140 or more failed). Only the per-chunk ask is bounded here — a dense doc still lands
# its full density across N chunks, and AUDN dedups. EMPIRICALLY TUNABLE.
OUTPUT_SAFE_CHUNK_CAP = 100

# max_tokens scaling for extraction (B-halt, flag-on only). Output tokens must
# cover the requested fact count, so the ceiling tracks the ask instead of a
# fixed value. ~EXTRACTION_TOKENS_PER_FACT tokens/fact + a JSON-wrapping buffer,
# clamped to the extraction model's documented max output tokens.
# Haiku 4.5 (claude-haiku-4-5-20251001) max output = 64000 tokens.
EXTRACTION_TOKENS_PER_FACT = 90
EXTRACTION_OUTPUT_BUFFER_TOKENS = 2000
EXTRACTION_MAX_OUTPUT_TOKENS = 64000


# ==========================================================================
# TURN CONTRACT EXTRACTION (docs/core/TURN_CONTRACT.md)
# ==========================================================================
# Named caps for turn-contract extraction. Each one is printed in the run
# header and written into the per-run record, so no cap in this path is hidden.
#
# Opt-in: turn-contract extraction runs only when BASELAYER_TURN_CONTRACT is
# truthy (or `baselayer extract --turn-contract`). It is never inferred from a
# table existing: a mismatch in the turn table's name would otherwise fall back
# silently to the legacy path and store ungated, unstamped facts.
#
# Preceding turns carried into each chunk as read-only CONTEXT (no citable ids).
# This is what lets the model read a short reply ("yes, do that") against the
# turn it answers. It is input on top of the chunk body, so it is a direct cost
# lever; measure its effect on a pilot before raising it.
TURN_CONTEXT_CHAR_BUDGET = 3000
TURN_CONTEXT_MAX_TURNS = 4
# Bounds on one evidence span, ENFORCED by the gate (contract section 5, reason
# `span_length`) and stated in the prompt. A span under the minimum ("yes", "ok")
# grounds nothing on its own; a span over the maximum is usually a whole turn
# cited wholesale, which passes the substring check while pointing at nothing in
# particular. Overridable per run with BASELAYER_TURN_SPAN_MIN_WORDS and
# BASELAYER_TURN_SPAN_MAX_CHARS; the values used are written to the run record.
TURN_EVIDENCE_SPAN_MIN_WORDS = 3
TURN_EVIDENCE_SPAN_MAX_CHARS = 400
# The D-048 contamination filter (drop any fact that mentions the pipeline, the
# project, extraction, a model name...) exists because legacy extraction read
# assistant text in project sessions as the subject's. Under the turn contract
# the span gate removes that failure at the source, and the filter would also
# drop facts the subject grounded in their own words about their own project. OFF in
# turn mode; the legacy path keeps it.
TURN_CONTAMINATION_FILTER = False
# Output tokens per fact on the turn path. The legacy 90 (EXTRACTION_TOKENS_PER_FACT)
# was tuned for triples without grounding; each fact now also carries one or more
# spans of up to TURN_EVIDENCE_SPAN_MAX_CHARS (~100 tokens each) plus ids and the inferred flag.
# Under-sizing this truncates the JSON and loses the whole chunk, which is the
# failure OUTPUT_SAFE_CHUNK_CAP exists to prevent. EMPIRICALLY TUNABLE: set it
# from the pilot's measured output tokens per fact.
TURN_EXTRACTION_TOKENS_PER_FACT = 180
# Whether the turn-path prompt carries a fact count. Overridable per run with
# BASELAYER_FACT_COUNT_MODE; the mode used is written to the run record.
#   capped: "Extract up to N facts ... most identity-relevant first", and accepted facts past
#           the per-chunk cap are truncated (counted as over_per_chunk_cap). The behaviour
#           before the switch existed; its prompt hash is pinned in tests. Selectable per run;
#           also what a batch plan without the key (written before the switch) is read as.
#   none:   no count and no ordering in the prompt, no per-chunk truncation of gated facts.
#   coverage: `none` plus TURN_COVERAGE_SENTENCE in the prompt. Everything but the wording
#           is `none`'s: budget from citable chars, no per-chunk truncation.
#   coverage_fragments: `coverage` plus TURN_FRAGMENT_SENTENCE, which asks the model to
#           extract nothing from a fragment or an unclear question. Everything else is
#           `coverage`'s.
# Default `coverage`: in a same-sample comparison of the three modes it dropped most of
# capped's noise facts (over-read fragments, stretches, pasted text) and its duplicates at
# lower output cost; `coverage_fragments` was not better than `coverage` on its own target.
TURN_FACT_COUNT_MODES = ("capped", "none", "coverage", "coverage_fragments")
TURN_UNCOUNTED_MODES = ("none", "coverage", "coverage_fragments")
TURN_COVERAGE_MODES = ("coverage", "coverage_fragments")
TURN_COVERAGE_SENTENCE = ("Extract every distinct fact the subject's own words support; do not "
                          "stop early and do not restate the same fact in different words.")
TURN_FRAGMENT_SENTENCE = ("If a turn is a fragment or a question whose meaning is not clear from "
                          "its context, extract nothing from it.")
TURN_FACT_COUNT_MODE = "coverage"
# Output budget in fact_count_mode `none`, per chunk:
#   max_tokens = clamp(TURN_OUTPUT_TOKENS_FLOOR,
#                      ceil(TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR x chunk citable chars),
#                      EXTRACTION_MAX_OUTPUT_TOKENS)
# Derivation (a turn-contract pilot run, capped prompt, Haiku 4.5,
# 22 extraction calls): output tokens per citable char of each call's own chunk. On the 8
# chunks over 600 citable chars the ratio was 0.33 to 2.11 (max 2.111, a 1,319-char chunk
# that returned 2,784 tokens); the per-CONVERSATION averages used in the design review
# (max 1.39) hide that chunk. Three times the per-chunk maximum is 6.33, rounded up to 6.4.
# Below 600 chars the ratio is dominated by the small denominator (up to 18 on an
# 82-char chunk); the floor covers every small chunk observed (largest small-chunk output
# 1,482 tokens). The largest output of any call was 2,784 tokens.
# Every extraction call's usage entry carries `citable_chars`, so this constant is
# re-derived from each run's own record rather than from this one. A chunk that still
# stops on max_tokens is re-chunked, never dropped (extract_facts).
TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR = 6.4
TURN_OUTPUT_TOKENS_FLOOR = 2000
# Run-wide spend ceiling (the runaway guard that replaced the fact-count halt on the turn
# path). Set per run with BASELAYER_SPEND_CEILING_USD; unset means no ceiling. Checked
# before every sequential model call: measured spend so far (every call's usage, AUDN
# included) plus the call's worst case (prompt chars / SPEND_CHARS_PER_TOKEN input, plus
# max_tokens output) must stay at or under the ceiling, or the run stops.
# Rates are USD per million tokens for the extraction model, Claude Haiku 4.5, published
# first-party rates (input 1, output 5; cache read 0.1x and cache write 1.25x input).
# Confirm them against the current price list before relying on the ceiling.
SPEND_RATES_PER_MTOK = {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25}
SPEND_CHARS_PER_TOKEN = 3.5   # conservative: the pilot measured 3.77 prompt chars per token


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


def collection_space(collection):
    """Read the distance space off a Chroma collection. Never assume it.

    Chroma stores it in collection metadata as `hnsw:space`. When unset, Chroma's
    default is l2. Collections in this project are NOT uniform: `memory_facts` is
    created cosine (embed.py, extract_facts.py, batch_extract.py), while `messages`,
    `turn_pairs` and `conversation_summaries` are left at the l2 default.
    """
    md = getattr(collection, "metadata", None) or {}
    return md.get("hnsw:space", "l2")


def chromadb_dist_to_similarity(dist, space):
    """Convert a Chroma distance to cosine similarity (0-1). `space` is required.

    THE OLD VERSION APPLIED THE L2 FORMULA TO EVERY COLLECTION and its docstring said
    the difference was "small for the values we care about". Measured against a real
    cosine collection, the error is +0.46 to +0.47 across the returned range, and it
    inverts the threshold decision: a distance of 0.5477 was reported as 0.8500 and
    passed a 0.85 gate whose true similarity is 0.4523.

    Three of five call sites queried `memory_facts`, which is cosine, so `verify`,
    `provenance` and `trace_claim` were all reading inflated similarity. Those are the
    surfaces the project sells as its auditability story.

    `space` has no default on purpose. A default is what produced the bug: the wrong
    formula applied silently to the collection that mattered most.
    """
    if space not in ("cosine", "l2", "ip"):
        raise ValueError(
            "unknown Chroma space %r. Read it off the collection with collection_space(); "
            "do not guess. Guessing is what made every memory_facts similarity wrong." % (space,))
    if dist <= 0:
        return 1.0
    if space == "cosine":
        # Chroma cosine distance is 1 - cos_sim.
        sim = 1.0 - dist
    elif space == "l2":
        # Squared L2 on normalized vectors: cos_sim = 1 - d/2.
        # For unnormalized L2 this is an approximation; embeddings here are normalized.
        sim = 1.0 - (dist ** 2) / 2.0
    else:  # ip
        sim = dist
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

# Sources whose conversations have Claude Code SESSION SHAPE: a subject directing an agent
# through tool calls, with assistant turns full of code and tool traffic. Live and recovered
# raw transcripts import as "claude_code"; database copies of older sessions and Claude
# Desktop agent-mode sessions carry their own source names (recovered_import) so provenance
# stays visible, but every behaviour keyed on session shape (project scope, chunk overlap,
# abstraction of assistant text, the per-source fact ceiling, the identity-only default)
# must treat them alike. Prompt history (claude_code_history) is NOT a member: it holds
# prompts only, with no assistant turns, so nothing about session shape applies to it.
# Whether its facts are project or personal scope is an open decision.
CLAUDE_CODE_SOURCES = ("claude_code", "claude_code_db_copy", "claude_desktop_agent")


def is_claude_code_source(source) -> bool:
    return source in CLAUDE_CODE_SOURCES


def source_family(source):
    """The key per-source settings are looked up under: "claude_code" for every member of
    CLAUDE_CODE_SOURCES, the source itself otherwise."""
    return "claude_code" if source in CLAUDE_CODE_SOURCES else source


SCOPE_SOURCE_MAPPING = {
    "chatgpt": "personal",
    "claude_web": "personal",
    **{s: "project" for s in CLAUDE_CODE_SOURCES},
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
# SPECIFICATION LAYER PATHS (D-043 — Three-Layer Architecture)
# ==========================================================================
# Pre-authored specification layers stored as markdown files with injectable blocks.
# Each file has a metadata header above --- and injectable text below.
# assemble_brief.py reads the injectable blocks at assembly time.

IDENTITY_LAYERS_DIR = PROJECT_ROOT / "data" / "identity_layers"
ANCHORS_LAYER_FILE = IDENTITY_LAYERS_DIR / "anchors_v4.md"
CORE_LAYER_FILE = IDENTITY_LAYERS_DIR / "core_v4.md"
PREDICTIONS_LAYER_FILE = IDENTITY_LAYERS_DIR / "predictions_v4.md"
UNIFIED_BRIEF_FILE = IDENTITY_LAYERS_DIR / "brief_v5_clean.md"  # Stripped citations — for serving
UNIFIED_BRIEF_CITED_FILE = IDENTITY_LAYERS_DIR / "brief_v5.md"  # With citations — for audit
IDENTITY_MODEL_FILE = IDENTITY_LAYERS_DIR / "identity_model.md"  # D-081: brief + layers combined, primary AI artifact
V1_STAGING_DIR = IDENTITY_LAYERS_DIR / "v1_staging"  # S98: previous specification archived here before pipeline overwrites

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
    "tiering": "claude-sonnet-4-6",                    # LEGACY — tiering removed in S79
    "authoring": "claude-sonnet-4-6",                  # S98: updated from claude-sonnet-4-20250514
    "review": "claude-opus-4-6",                       # S98: updated from claude-opus-4-20250514 (3x cheaper)
    "contradiction": "claude-sonnet-4-6",              # Used by detect_contradictions.py (experimental)
}

# S98: Known latest model versions — used for freshness check
_LATEST_MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}


def check_model_freshness():
    """Check if configured models are the latest available. Prints warnings for outdated models."""
    warnings = []
    for role, model_id in LLM_PROVIDER_CONFIG.items():
        for family, latest in _LATEST_MODELS.items():
            if family in model_id.lower() and model_id != latest:
                warnings.append(f"  {role}: using {model_id}, latest is {latest}")
    if warnings:
        print("Model freshness warning — outdated models detected:")
        for w in warnings:
            print(w)
        print("  Update _LLM_DEFAULTS in config.py or set BASELAYER_LLM_<ROLE> env vars.")
        print()
    return len(warnings) == 0

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
# 46 verbs (45 behavioral plus the `unknown` fallback) covering: ownership,
# values, activities, biography, relationships, skills, emotions, decisions.
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


# ==========================================================================
# IDENTITY_PREDICATES — tier-classification subset of CONSTRAINED_PREDICATES
# ==========================================================================
# Predicates whose facts are tagged knowledge_tier='identity' during the
# post-compose traceability pass (cli._run_traceability, step 5a).
# Everything not in this set tiers to 'contextual'.
#
# Source-of-truth invariant: every entry MUST appear in CONSTRAINED_PREDICATES.
# A runtime assertion below enforces this so the two lists cannot drift.
# Pre-2026-05-06 history: a parallel list lived in cli.py and drifted to
# include 'decides' (extraction emits 'decided') and 'trades' (not canonical).
# Both were dead matches at tier time. Removed when this list moved here.
IDENTITY_PREDICATES = (
    "values", "believes", "fears", "identifies_as", "aspires_to",
    "prioritizes", "avoids", "practices", "excels_at", "struggles_with",
    "loves", "hates", "enjoys", "dislikes", "builds", "founded",
    "decided", "experienced", "lost", "follows", "monitors",
    "plays", "maintains", "prefers",
)

_canonical_set = set(CONSTRAINED_PREDICATES)
_identity_drift = [p for p in IDENTITY_PREDICATES if p not in _canonical_set]
assert not _identity_drift, (
    f"IDENTITY_PREDICATES drifted from CONSTRAINED_PREDICATES: {_identity_drift}. "
    f"Every identity predicate must be a canonical predicate."
)
del _canonical_set, _identity_drift
