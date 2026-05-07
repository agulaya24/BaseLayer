"""
Base Layer MCP Server. Behavioral alignment for AI agents.

Exposes behavioral specifications and fact retrieval to MCP-compatible clients
(Claude Desktop, Claude Code, Cursor, etc.).

Partial-serving architecture (since 0.3.0):
  Resources (always available, client-controlled):
    memory://specification  Communication & Context (CORE layer) plus a manifest
                            of available tools. Roughly 1.5K to 2.5K tokens.
                            The full specification is accessible via tools.
    memory://identity       Deprecated alias for memory://specification.
                            Returns identical content. Retained for backward
                            compatibility; will be removed in a future release.

  Tools (model-controlled, called on demand):
    get_anchors        Foundational beliefs and worldview (ANCHORS layer)
    get_predictions    Situational behavioral predictions (PREDICTIONS layer)
    get_brief          Unified narrative specification
    recall_memories    Semantic retrieval of relevant facts + episodes for a query
    search_facts       Keyword search across all active facts
    trace_claim        Provenance from a specification claim to source facts
    verify_claims      Binary verification checks against the fact database
    get_stats          Database statistics

Transport: stdio (local, no network)

Usage:
  # Direct
  python mcp_server.py

  # Via installed package
  baselayer-mcp

  # Claude Desktop config (claude_desktop_config.json):
  {
    "mcpServers": {
      "base-layer": {
        "command": "baselayer-mcp"
      }
    }
  }

  # Claude Code:
  claude mcp add --transport stdio base-layer -- baselayer-mcp
"""

import sys
import os
import contextlib
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

# Logging to stderr only. Stdout is reserved for JSON-RPC (stdio transport).
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="[base-layer] %(levelname)s: %(message)s",
)
logger = logging.getLogger("base-layer")

from baselayer.config import (
    DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL,
    ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
    UNIFIED_BRIEF_FILE, UNIFIED_BRIEF_CITED_FILE,
    get_db,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("ERROR: MCP SDK not installed. Run: pip install 'mcp[cli]'", file=sys.stderr)
    sys.exit(1)


def _escape_like(s):
    """Escape SQL LIKE metacharacters (%, _, \\) in user input."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _extract_layer_block(path):
    """Read a layer file and return its Injectable Block content.

    Returns empty string if the file is missing or no Injectable Block marker
    is present. Falls back to first-section-after-frontmatter if no marker is
    found but the file exists.
    """
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx >= 0:
        return content[idx + len(marker):].strip()
    sep = content.find("\n---\n")
    return content[sep + 5:].strip() if sep >= 0 else content.strip()


# In-memory ring buffer of recent MCP calls. Bounded so a long-running server
# does not grow unbounded. Queryable via the get_call_log() tool, which is the
# canonical way for an AI client to inspect its own usage of this server.
_CALL_LOG: "deque[dict]" = deque(maxlen=500)
_CALL_LOG_LOCK = threading.Lock()


def _log_call(name, **kwargs):
    """Record an MCP call. Emits a stderr line and appends to the in-memory log.

    Stderr format: ``[base-layer] INFO: mcp_call name=<name> [k=v ...]``

    The in-memory log is queryable via the ``get_call_log()`` MCP tool, which
    is the canonical way for an AI client (Claude, etc.) to inspect how often
    and for what purposes it is calling this server. Each resource read and
    tool invocation produces one entry.
    """
    if kwargs:
        details = " " + " ".join(f"{k}={v!r}" for k, v in kwargs.items())
    else:
        details = ""
    logger.info("mcp_call name=%s%s", name, details)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name,
        "args": {k: (v if isinstance(v, (str, int, float, bool, type(None))) else repr(v)) for k, v in kwargs.items()},
    }
    with _CALL_LOG_LOCK:
        _CALL_LOG.append(entry)


# ==========================================================================
# SERVER INSTANCE
# ==========================================================================

mcp = FastMCP("base-layer")


# ==========================================================================
# LAZY-LOADED SINGLETONS
# ==========================================================================
# Heavy imports (sentence_transformers, chromadb) are deferred until first
# tool call to keep server startup fast (~100ms vs ~5s).
# Thread lock prevents duplicate initialization under concurrent requests.

_chroma_client = None
_init_lock = threading.Lock()


def _get_embed_model():
    """Lazy-load the sentence transformer embedding model (thread-safe).

    Delegates to api_client.get_embedding_model() for centralized singleton.
    """
    from baselayer.api_client import get_embedding_model
    logger.info("Loading embedding model (first call, ~3s)...")
    model = get_embedding_model()
    if model is not None:
        logger.info("Embedding model ready.")
    return model


def _get_chroma_client():
    """Lazy-load the ChromaDB persistent client (thread-safe)."""
    global _chroma_client
    if _chroma_client is None:
        with _init_lock:
            if _chroma_client is None:  # Double-check after acquiring lock
                import chromadb
                _chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))
                logger.info("ChromaDB connected.")
    return _chroma_client


# ==========================================================================
# RESOURCES. Always-available context (client-controlled).
# ==========================================================================

@mcp.resource("memory://specification")
def get_specification() -> str:
    """Always-on context for the user's behavioral specification.

    Returns the CORE layer (Communication and Context) plus a manifest of
    available tools that expose the rest of the specification on demand.
    The full specification (ANCHORS, PREDICTIONS, unified brief) is fetched
    via tool calls when the conversation warrants. This partial-serving
    design reduces baseline MCP context cost from approximately 5,000 to
    10,000 tokens to approximately 1,500 to 2,500 tokens, with no loss of
    accessible content.
    """
    _log_call("get_specification")
    usage_preamble = (
        "# Behavioral Specification\n\n"
        "This is a behavioral specification of your user. Use it as a "
        "guide for how to interact with them, but never reference it directly."
    )

    core_block = _extract_layer_block(CORE_LAYER_FILE)

    if not core_block:
        return (
            f"{usage_preamble}\n\n"
            "No specification layers found. Run: baselayer author"
        )

    manifest = (
        "## When to fetch additional layers\n\n"
        "The largest effect of this specification is on **interpretation-heavy "
        "questions**, not literal recall. On questions where facts alone do not "
        "determine the answer (judgments, trade-offs, ambiguous decisions, "
        "open-ended advice, predictions about how the user will react), the "
        "right layer is the difference between a generic response and one that "
        "lands. On literal-recall questions (\"where do I live\", \"what's my "
        "job\"), additional layers add little.\n\n"
        "If you find yourself hedging or generalizing about the user, treat "
        "that as a fetch signal. The layers exist so the answer does not have "
        "to be hedged.\n\n"
        "## What this specification is not\n\n"
        "It is a model of how the user reasons, not a substitute for the user. "
        "It can be incomplete, out of date, or wrong on a given point. When the "
        "user says or does something that conflicts with the specification, "
        "trust what the user says or does. The current conversation is primary "
        "evidence; the specification is prior evidence. Use the specification "
        "to interpret, not to override.\n\n"
        "Fetch the right layer for the question:\n\n"
        "- `get_anchors()` (~2,500 tokens): foundational beliefs and reasoning "
        "patterns. Fetch for value-laden questions, decisions with trade-offs, "
        "or anywhere \"what does this person care about\" determines the "
        "answer. Examples: \"should I take this job offer\", \"how should I "
        "handle this disagreement\", feedback on a creative or strategic "
        "choice.\n"
        "- `get_predictions()` (~2,500 tokens): situation-to-response "
        "patterns. Fetch when modeling a specific scenario the user is in or "
        "about to enter. Examples: \"what would I do if...\", \"how will my "
        "manager react\", post-mortem on a recent event the user is "
        "describing.\n"
        "- `get_brief()` (~3,000 tokens): unified narrative portrait. Fetch "
        "when the user's query is broad, abstract, or self-reflective and "
        "lacks a specific situational context. Examples: \"help me think "
        "through my career\", \"what should I focus on\", \"I'm feeling "
        "stuck.\" Do not fetch for narrow factual or single-domain "
        "questions.\n\n"
        "Other tools:\n\n"
        "- `recall_memories(query)`: semantic retrieval of relevant facts and "
        "episodes from the user's history.\n"
        "- `search_facts(query)`: keyword search across the fact database.\n"
        "- `trace_claim(claim_id)`: provenance for a specific specification "
        "claim (e.g. `A1`, `P3`).\n"
        "- `verify_claims(...)`: binary verification checks against the fact "
        "database.\n"
        "- `get_stats()`: database summary (counts, tier breakdown).\n"
        "- `get_call_log(limit, name_filter)`: recent MCP calls in this "
        "session. Use when the user asks how the specification has been "
        "used, or to check whether you have already fetched a layer earlier "
        "in the conversation before fetching it again."
    )

    return (
        f"{usage_preamble}\n\n"
        f"## Communication & Context\n\n{core_block}\n\n"
        f"{manifest}"
    )


@mcp.resource("memory://identity")
def get_identity_brief() -> str:
    """Deprecated alias for memory://specification. Returns the same content. Will be removed in a future release."""
    return get_specification()


# ==========================================================================
# TOOLS. Model-controlled, called on demand.
# ==========================================================================

@mcp.tool()
def recall_memories(query: str) -> str:
    """Search the user's memory for facts and episodes relevant to a query.
    Use this when the conversation touches on personal topics, past experiences,
    preferences, or anything that would benefit from knowing the user's history.

    Args:
        query: Natural language description of what to recall (e.g. "career history", "relationship with partner", "trading approach")
    """
    _log_call("recall_memories", query=query)
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init && baselayer import"

    with contextlib.closing(get_db()) as conn:
        embed_model = _get_embed_model()
        chroma_client = _get_chroma_client()

        # Import retrieval functions from assemble_brief
        from baselayer.assemble_brief import get_theme_block, get_episode_block

        results = []

        # Theme retrieval (relevant facts)
        try:
            theme_text, theme_ids = get_theme_block(conn, query, embed_model, chroma_client)
            if theme_text and theme_text.strip():
                results.append("<relevant_facts>\n" + theme_text + "\n</relevant_facts>")
        except Exception as e:
            logger.warning(f"Theme retrieval failed: {e}")

        # Episode retrieval (conversation memories)
        try:
            episode_text = get_episode_block(conn, query, embed_model, chroma_client)
            if episode_text and episode_text.strip():
                results.append("<episodic_memories>\n" + episode_text + "\n</episodic_memories>")
        except Exception as e:
            logger.warning(f"Episode retrieval failed: {e}")

    if not results:
        return f"No relevant memories found for: {query}"

    return "\n\n".join(results)


@mcp.tool()
def search_facts(query: str, limit: int = 15) -> str:
    """Search the user's fact database by keyword. Returns matching facts with
    metadata (type, tier, category, recurrence).

    Args:
        query: Keywords to search for in fact text
        limit: Maximum results to return (default 15)
    """
    _log_call("search_facts", query=query, limit=limit)
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init"

    limit = min(limit, 100)

    with contextlib.closing(get_db()) as conn:
        rows = None

        # Session 57 (C11): Try FTS5 full-text search first (fast MATCH query).
        # Falls back to LIKE if FTS5 table doesn't exist or query syntax fails.
        try:
            rows = conn.execute("""
                SELECT f.id, f.fact_text, f.fact_type, f.knowledge_tier, f.category,
                       f.commitment_depth, f.recurrence_count
                FROM memory_facts f
                JOIN memory_facts_fts fts ON f.rowid = fts.rowid
                WHERE memory_facts_fts MATCH ?
                  AND f.superseded_by IS NULL
                ORDER BY
                  CASE f.knowledge_tier
                    WHEN 'identity' THEN 1
                    WHEN 'situational' THEN 2
                    WHEN 'context' THEN 3
                    ELSE 4
                  END,
                  f.recurrence_count DESC
                LIMIT ?
            """, (query, limit)).fetchall()
        except Exception:
            rows = None  # FTS5 table missing or query syntax error; fall back

        # Fallback: LIKE query (works everywhere, no FTS5 dependency)
        if rows is None:
            rows = conn.execute("""
                SELECT id, fact_text, fact_type, knowledge_tier, category,
                       commitment_depth, recurrence_count
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND LOWER(fact_text) LIKE LOWER(?) ESCAPE '\\'
                ORDER BY
                  CASE knowledge_tier
                    WHEN 'identity' THEN 1
                    WHEN 'situational' THEN 2
                    WHEN 'context' THEN 3
                    ELSE 4
                  END,
                  recurrence_count DESC
                LIMIT ?
            """, (f"%{_escape_like(query)}%", limit)).fetchall()

    if not rows:
        return f"No facts found matching '{query}'"

    lines = []
    for r in rows:
        tier = r["knowledge_tier"] or "?"
        ftype = r["fact_type"] or "?"
        rec = r["recurrence_count"] or 0
        lines.append(f"[{tier}/{ftype}] {r['fact_text']}  (rec: {rec})")

    return f"Found {len(rows)} facts:\n\n" + "\n".join(lines)


@mcp.tool()
def trace_claim(claim_id: str) -> str:
    """Trace a specification claim back to its supporting facts and source conversations.
    Like Genius.com annotations: shows the evidence chain behind each claim.

    Args:
        claim_id: The lexicon ID of the claim to trace (e.g. "A1", "P3", "C2")
    """
    _log_call("trace_claim", claim_id=claim_id)
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init"

    with contextlib.closing(get_db()) as conn:
        # Get provenance entries for this claim
        rows = conn.execute("""
            SELECT p.claim_id, p.claim_text, p.fact_id, p.link_method,
                   p.rank_in_claim, p.layer_name, p.layer_version,
                   f.fact_text, f.fact_type, f.knowledge_tier,
                   f.recurrence_count, f.source_conversation_id,
                   f.predicate, f.object_text
            FROM layer_claim_provenance p
            LEFT JOIN memory_facts f ON p.fact_id = f.id
            WHERE UPPER(p.claim_id) = UPPER(?)
            ORDER BY p.rank_in_claim
        """, (claim_id,)).fetchall()

        if not rows:
            return f"No provenance found for claim '{claim_id}'. Run: baselayer author (with provenance-enabled prompts)"

        # Build response
        first = rows[0]
        lines = [
            f"Claim: {first['claim_id']}: {first['claim_text'] or '(unnamed)'}",
            f"Layer: {first['layer_name']} ({first['layer_version'] or 'unknown'})",
            f"",
            f"Supporting Facts ({len(rows)}):",
        ]

        for r in rows:
            fact_text = r["fact_text"] or "(fact not found)"
            tier = r["knowledge_tier"] or "?"
            rec = r["recurrence_count"] or 0
            method = r["link_method"] or "?"
            lines.append(f"  [{r['rank_in_claim']}] {fact_text}")
            lines.append(f"      tier: {tier}, recurrence: {rec}, linked via: {method}")

            # Show source conversation if available
            if r["source_conversation_id"]:
                conv = conn.execute(
                    "SELECT title, created_at FROM conversations WHERE id = ?",
                    (r["source_conversation_id"],)
                ).fetchone()
                if conv and conv["title"]:
                    lines.append(f"      source: \"{conv['title']}\"")

        return "\n".join(lines)


@mcp.tool()
def get_stats() -> str:
    """Get summary statistics about the user's memory database.
    Shows conversation count, fact count, tier breakdown, and source breakdown.
    """
    _log_call("get_stats")
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init"

    with contextlib.closing(get_db()) as conn:
        convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        facts = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        superseded = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NOT NULL"
        ).fetchone()[0]

        # Tier breakdown
        tiers = conn.execute("""
            SELECT knowledge_tier, COUNT(*) as cnt
            FROM memory_facts WHERE superseded_by IS NULL
            GROUP BY knowledge_tier ORDER BY cnt DESC
        """).fetchall()

        # Source breakdown
        sources = conn.execute("""
            SELECT source, COUNT(*) as cnt
            FROM conversations GROUP BY source ORDER BY cnt DESC
        """).fetchall()

    lines = [
        "Base Layer Memory Statistics",
        f"  Conversations: {convos:,}",
        f"  Messages:      {messages:,}",
        f"  Active facts:  {facts:,}",
        f"  Superseded:    {superseded:,}",
    ]

    if tiers:
        lines.append("\n  Knowledge Tiers:")
        for t in tiers:
            name = t["knowledge_tier"] or "unclassified"
            lines.append(f"    {name:15s} {t['cnt']:,}")

    if sources:
        lines.append("\n  Sources:")
        for s in sources:
            lines.append(f"    {s['source']:15s} {s['cnt']:,}")

    return "\n".join(lines)


@mcp.tool()
def verify_claims(claim_id: str = "", layer: str = "all") -> str:
    """Verify specification claims against the fact database.
    Runs binary verification checks: existence, recurrence, cross-domain coverage,
    temporal consistency, and internal contradictions.

    Args:
        claim_id: Optional specific claim to verify (e.g. "A1", "P3"). If empty, verifies all.
        layer: Which layer to verify: "anchors", "core", "predictions", or "all" (default).
    """
    _log_call("verify_claims", claim_id=claim_id, layer=layer)
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init"

    try:
        from baselayer.verify_provenance import (
            run_verification,
            format_claim_results,
        )
    except ImportError:
        return "Verification module not available. Ensure verify_provenance.py is in the scripts directory."

    claim_filter = claim_id.strip() if claim_id.strip() else None
    summary = run_verification(layer, claim_id_filter=claim_filter)

    if summary["total"] == 0:
        if claim_filter:
            return f"No verification questions generated for claim '{claim_filter}'. Check that provenance citations exist."
        return "No verification questions generated. Run: baselayer author (with provenance-enabled prompts)"

    return format_claim_results(summary)


@mcp.tool()
def get_anchors() -> str:
    """Return the user's foundational beliefs and reasoning patterns (ANCHORS layer).

    Call this for interpretation-heavy questions where "what does this person
    care about" determines the answer. Examples: "should I take this job
    offer", "how should I handle this disagreement with my partner", "is this
    business idea a fit for me", feedback on a creative or strategic choice.
    ANCHORS contains the axioms the user reasons from and is the
    highest-leverage layer for judgment-heavy conversations. Approximately
    2,500 tokens.

    Do not call for literal-recall questions ("what's my job", "where do I
    live"); CORE plus the user's own statements cover those.

    Note: ANCHORS describes how the user typically reasons, not what they must
    do in a given moment. If the current conversation contradicts ANCHORS,
    trust the conversation.
    """
    _log_call("get_anchors")
    block = _extract_layer_block(ANCHORS_LAYER_FILE)
    if not block:
        return (
            "ANCHORS layer is not present in this user's specification. "
            "Tell the user: \"Your ANCHORS layer is missing. Generate it with "
            "`baselayer author --layer anchors`.\" Continue using CORE."
        )
    return block


@mcp.tool()
def get_predictions() -> str:
    """Return the user's situation-to-response patterns (PREDICTIONS layer).

    Call this when modeling a specific scenario the user is in or about to
    enter. Examples: "what would I do if my startup fails", "how will my
    manager react to this proposal", "what's my likely response to this
    setback", post-mortem on a recent event the user is describing.
    PREDICTIONS encodes situation-trigger-directive patterns derived from the
    user's track record. Approximately 2,500 tokens.

    Do not call for hypothetical questions about other people, or for
    questions that don't ask about the user's likely behavior.

    Note: predictions are calibrated probabilities, not certainties. People
    deviate from their patterns; the user may surprise you. Use predictions
    as a default to interpret against, not as a forecast to insist on.
    """
    _log_call("get_predictions")
    block = _extract_layer_block(PREDICTIONS_LAYER_FILE)
    if not block:
        return (
            "PREDICTIONS layer is not present in this user's specification. "
            "Tell the user: \"Your PREDICTIONS layer is missing. Generate it "
            "with `baselayer author --layer predictions`.\" Continue using "
            "CORE plus ANCHORS if available."
        )
    return block


@mcp.tool()
def get_brief() -> str:
    """Return the unified narrative specification that contextualizes the layers.

    Call this when the current query is broad, abstract, or self-reflective
    and lacks a specific situational context. Examples: "help me think
    through my career", "what should I focus on this quarter", "I'm feeling
    stuck, give me some perspective". The unified brief is a connected
    portrait of the user that the structural layers do not replicate.
    Approximately 3,000 tokens.

    Do not call for narrow factual or single-domain questions; CORE plus
    a single targeted layer is usually enough.

    Note: the brief is a snapshot from when it was authored. Treat it as
    high-quality context, not as ground truth. The current conversation
    overrides any specific claim in the brief.
    """
    _log_call("get_brief")
    brief_file = UNIFIED_BRIEF_FILE if UNIFIED_BRIEF_FILE.exists() else UNIFIED_BRIEF_CITED_FILE
    if not brief_file.exists():
        return (
            "Unified brief is not present in this user's specification. "
            "Tell the user: \"Your unified brief is missing. Generate it with "
            "`baselayer compose`.\" Continue using CORE plus the structural "
            "layers."
        )
    content = brief_file.read_text(encoding="utf-8")
    marker = "## Injectable Block"
    idx = content.find(marker)
    if idx >= 0:
        block = content[idx + len(marker):].strip()
        if block:
            return block
    return content.strip()


@mcp.tool()
def get_call_log(limit: int = 50, name_filter: str = "") -> str:
    """Return recent MCP calls made against this server in this process.

    Use this to inspect how this specification has been used in the current
    session: which tools were called, in what order, with what arguments.
    Useful when the user asks how the spec is being applied, when calibrating
    fetch behavior, or when debugging "did the model actually pull anchors?"

    The log is in-memory and bounded to the most recent 500 calls. It does
    not persist across server restarts. For longer-horizon monitoring, the
    same calls are emitted to stderr in the format
    ``[base-layer] INFO: mcp_call name=<n> [k=v ...]``, which the MCP host
    captures in its own log files.

    Args:
        limit: Maximum number of recent entries to return. Default 50.
        name_filter: Substring filter on tool name (e.g. "get_" to see only
            specification fetches, "anchors" for anchor calls). Empty string
            returns all.
    """
    _log_call("get_call_log", limit=limit, name_filter=name_filter)
    with _CALL_LOG_LOCK:
        entries = list(_CALL_LOG)

    if name_filter:
        entries = [e for e in entries if name_filter in e["name"]]

    if not entries:
        return "No MCP calls recorded yet in this session."

    entries = entries[-limit:]
    by_name: dict[str, int] = {}
    for e in entries:
        by_name[e["name"]] = by_name.get(e["name"], 0) + 1

    lines = [
        f"MCP call log ({len(entries)} of {len(_CALL_LOG)} total recorded)",
        "",
        "Counts by tool:",
    ]
    for n, c in sorted(by_name.items(), key=lambda x: -x[1]):
        lines.append(f"  {n}: {c}")
    lines.append("")
    lines.append("Recent calls (oldest first):")
    for e in entries:
        args_str = ""
        if e["args"]:
            args_str = " " + " ".join(f"{k}={v!r}" for k, v in e["args"].items())
        lines.append(f"  [{e['timestamp']}] {e['name']}{args_str}")
    return "\n".join(lines)


# ==========================================================================
# ENTRY POINT
# ==========================================================================

def main():
    """Run the MCP server (stdio transport)."""
    logger.info(f"Starting Base Layer MCP server...")
    logger.info(f"Database: {DATABASE_FILE}")
    logger.info(f"Vectors: {VECTORS_DIR}")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
