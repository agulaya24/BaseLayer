"""
Base Layer MCP Server — Personal AI Memory System

Exposes identity layers and memory retrieval to MCP-compatible clients
(Claude Desktop, Claude Code, Cursor, etc.).

Architecture:
  Resources (always available, client-controlled):
    memory://identity  — Full three-layer identity brief (ANCHORS + CORE + PREDICTIONS)

  Tools (model-controlled, called on demand):
    recall_memories    — Semantic retrieval of relevant facts + episodes for a query
    search_facts       — Keyword search across all active facts
    get_stats          — Database statistics

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
from pathlib import Path

# Logging to stderr only — stdout is reserved for JSON-RPC (stdio transport)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="[base-layer] %(levelname)s: %(message)s",
)
logger = logging.getLogger("base-layer")

# Ensure scripts directory is importable
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL,
    ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
    UNIFIED_BRIEF_FILE,
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
    from api_client import get_embedding_model
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
# RESOURCES — always available context (client-controlled)
# ==========================================================================

@mcp.resource("memory://identity")
def get_identity_brief() -> str:
    """The user's full identity brief: a unified behavioral narrative (preferred) or three-layer format (fallback). This is always-on context that tells you who you're talking to."""
    usage_preamble = (
        "IMPORTANT: This brief contains ALL-CAPS pattern names as internal labels. NEVER "
        "quote, reference, or name them in your responses. Do not say 'your [PATTERN] axiom' or "
        "'the [PATTERN-NAME] pattern.' Instead, demonstrate understanding through your behavior: "
        "how you frame questions, what you push back on, what you anticipate. "
        "Match response length to question complexity — default shorter."
    )

    # Priority 1: Unified brief (compressed narrative — proven +0.40 vs structured layers)
    if UNIFIED_BRIEF_FILE.exists():
        content = UNIFIED_BRIEF_FILE.read_text(encoding="utf-8")
        marker = "## Injectable Block"
        idx = content.find(marker)
        if idx >= 0:
            block = content[idx + len(marker):].strip()
            if block:
                return f"{usage_preamble}\n\n{block}"

    # Fallback: Three-layer concatenation
    parts = []

    for name, path in [
        ("ANCHORS", ANCHORS_LAYER_FILE),
        ("CORE", CORE_LAYER_FILE),
        ("PREDICTIONS", PREDICTIONS_LAYER_FILE),
    ]:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            marker = "## Injectable Block"
            idx = content.find(marker)
            if idx >= 0:
                block = content[idx + len(marker):].strip()
            else:
                sep = content.find("\n---\n")
                block = content[sep + 5:].strip() if sep >= 0 else content.strip()
            parts.append(block)

    if not parts:
        return "No identity layers found. Run: baselayer author"

    return f"{usage_preamble}\n\n" + "\n\n".join(parts)


# ==========================================================================
# TOOLS — model-controlled, called on demand
# ==========================================================================

@mcp.tool()
def recall_memories(query: str) -> str:
    """Search the user's memory for facts and episodes relevant to a query.
    Use this when the conversation touches on personal topics, past experiences,
    preferences, or anything that would benefit from knowing the user's history.

    Args:
        query: Natural language description of what to recall (e.g. "career history", "relationship with partner", "trading approach")
    """
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init && baselayer import"

    with contextlib.closing(get_db()) as conn:
        embed_model = _get_embed_model()
        chroma_client = _get_chroma_client()

        # Import retrieval functions from assemble_brief
        from assemble_brief import get_theme_block, get_episode_block

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
            rows = None  # FTS5 table missing or query syntax error — fall back

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
    """Trace an identity layer claim back to its supporting facts and source conversations.
    Like Genius.com annotations — shows the evidence chain behind each claim.

    Args:
        claim_id: The lexicon ID of the claim to trace (e.g. "A1", "P3", "C2")
    """
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
            f"Claim: {first['claim_id']} — {first['claim_text'] or '(unnamed)'}",
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
    """Verify identity layer claims against the fact database.
    Runs binary verification checks: existence, recurrence, cross-domain coverage,
    temporal consistency, and internal contradictions.

    Args:
        claim_id: Optional specific claim to verify (e.g. "A1", "P3"). If empty, verifies all.
        layer: Which layer to verify: "anchors", "core", "predictions", or "all" (default).
    """
    if not DATABASE_FILE.exists():
        return "No memory database found. Run: baselayer init"

    try:
        from verify_provenance import (
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
