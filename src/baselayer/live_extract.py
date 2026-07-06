"""
Live extraction: single-conversation ingestion orchestrator.

Wraps extract_facts.process_conversation to process one conversation in
near-real-time, then runs the contradiction pipeline on any new
state-facts. Returns a change manifest describing every action taken.
This is the entry point a conversation-capture proxy (D-049) calls per
conversation; the batch pipeline (``baselayer extract``) remains the bulk
path.

Public API:
  - ``extract_single(conn, conversation_id, chroma_client=None,
    embed_model=None)``: extract one already-imported conversation.
    Returns the change manifest.
  - ``extract_from_file(file_path)``: import a single text file, then
    extract from the resulting conversation. Same manifest shape.

Manifest shape:
  {
    "conversation_id": str,
    "facts_stored": int,
    "actions": [{"type": "ADD"|"NOOP", "fact_id", "fact_text",
                 "fact_class", ...}],
    "contradictions_found": int,
    "probes_queued": int,
    "error": str (only present on failure),
  }

Command line:
  python -m baselayer.live_extract --conversation <id> [--json]
  python -m baselayer.live_extract --file <path> [--json]
"""

import argparse
import contextlib
import hashlib
import json
import logging
import sys
from pathlib import Path

from baselayer.config import (
    EMBEDDING_MODEL,
    VECTORS_DIR,
    get_db,
)

logger = logging.getLogger("base-layer")


# ---------------------------------------------------------------------------
# ChromaDB / embedding setup (follows the run_extraction() pattern)
# ---------------------------------------------------------------------------

def _init_chroma_and_model():
    """Initialize the ChromaDB client, facts collection, and embedding model.

    Returns (chroma_client, fact_collection, embed_model). All three are
    None when the optional embedding dependencies are missing; extraction
    still runs, without similarity-based checks.
    """
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        embed_model = SentenceTransformer(EMBEDDING_MODEL)
        chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))

        try:
            fact_collection = chroma_client.get_collection("memory_facts")
        except Exception:
            fact_collection = chroma_client.create_collection(
                name="memory_facts",
                metadata={"description": "Extracted personal facts (AUDN pipeline)",
                          "hnsw:space": "cosine"},
            )

        return chroma_client, fact_collection, embed_model

    except ImportError:
        print("  WARNING: chromadb/sentence-transformers not available. "
              "Running without embeddings.", file=sys.stderr)
        return None, None, None


# ---------------------------------------------------------------------------
# Core: extract a single conversation
# ---------------------------------------------------------------------------

def extract_single(conn, conversation_id: str, chroma_client=None,
                   embed_model=None) -> dict:
    """Extract facts from one conversation and run contradiction checks.

    Snapshots fact IDs before extraction so newly stored facts can be
    reported individually. Returns the change manifest (see module
    docstring). Never raises for per-conversation failures; errors are
    reported in the manifest's ``error`` key.
    """
    from baselayer.extract_facts import (
        process_conversation,
        get_conversations_to_process,
        create_tables,
        _ensure_structured_columns,
        load_corrections,
    )

    # Ensure tables and structured columns exist.
    create_tables()
    _ensure_structured_columns(conn)
    conn.commit()

    # Look up the conversation metadata.
    convs = get_conversations_to_process(conn, conv_id=conversation_id)
    if not convs:
        return {
            "conversation_id": conversation_id,
            "facts_stored": 0,
            "actions": [],
            "error": "Conversation not found",
            "contradictions_found": 0,
            "probes_queued": 0,
        }

    conv = convs[0]

    # Resolve the fact collection when a Chroma client is available.
    fact_collection = None
    if chroma_client is not None:
        try:
            fact_collection = chroma_client.get_collection("memory_facts")
        except Exception:
            logger.debug("Live extract: memory_facts collection unavailable")

    # Snapshot fact IDs before extraction to identify new ones afterwards.
    rows = conn.execute(
        "SELECT id FROM memory_facts WHERE source_conversation_id = ?",
        (conversation_id,)
    ).fetchall()
    before_ids = {r[0] for r in rows}

    corrections = load_corrections(conn)

    try:
        facts_stored = process_conversation(
            conv, conn, fact_collection, embed_model, corrections=corrections
        )
    except Exception as e:
        logger.warning("Live extract: extraction failed for %s: %s",
                       conversation_id, e)
        return {
            "conversation_id": conversation_id,
            "facts_stored": 0,
            "actions": [],
            "error": f"Extraction failed: {e}",
            "contradictions_found": 0,
            "probes_queued": 0,
        }

    # Compare before/after to identify the facts this run added.
    after_rows = conn.execute("""
        SELECT id, fact_text, fact_class, category, predicate, object_text,
               source_conversation_id
        FROM memory_facts
        WHERE source_conversation_id = ?
    """, (conversation_id,)).fetchall()

    actions = []
    new_state_facts = []

    for row in after_rows:
        fact_id = row[0]
        if fact_id in before_ids:
            continue  # Pre-existing fact from a prior run; not re-reported.

        fact_dict = {
            "fact_id": row[0],
            "fact_text": row[1],
            "fact_class": row[2] or "unclassified",
            "category": row[3],
            "predicate": row[4],
            "object_text": row[5],
            "source_conversation_id": row[6],
        }
        actions.append({"type": "ADD", **fact_dict})

        if fact_dict["fact_class"] == "state":
            new_state_facts.append(fact_dict)

    # process_conversation does not return per-fact AUDN actions. When it
    # stored nothing and no new rows appeared, everything was a NOOP.
    if facts_stored == 0 and not actions:
        actions.append({
            "type": "NOOP",
            "fact_id": None,
            "fact_text": "No new facts extracted",
            "fact_class": "unclassified",
        })

    # Run the contradiction pipeline on new state-facts.
    contradiction_stats = {"contradictions": 0, "probes_queued": 0}
    if new_state_facts and chroma_client is not None and embed_model is not None:
        from baselayer.contradiction_pipeline import process_new_state_facts
        try:
            stats = process_new_state_facts(
                conn, new_state_facts, chroma_client, embed_model
            )
            contradiction_stats["contradictions"] = stats.get("contradictions", 0)
            contradiction_stats["probes_queued"] = stats.get("probes_queued", 0)
        except Exception as e:
            logger.warning("Live extract: contradiction pipeline failed: %s", e)

    return {
        "conversation_id": conversation_id,
        "facts_stored": facts_stored,
        "actions": actions,
        "contradictions_found": contradiction_stats["contradictions"],
        "probes_queued": contradiction_stats["probes_queued"],
    }


# ---------------------------------------------------------------------------
# Convenience: import a file then extract
# ---------------------------------------------------------------------------

def extract_from_file(file_path: str) -> dict:
    """Import a single text file and extract facts from it.

    Uses the standard importer, then calls extract_single on the resulting
    conversation. Re-importing an already-imported file resolves to the
    same conversation ID (stable path hash) and extracts from it.

    Args:
        file_path: Path to a text file (.txt, .md, .docx, .rst).

    Returns a manifest dict (same shape as extract_single).
    """
    from baselayer.import_conversations import import_text_files

    path = Path(file_path)
    if not path.exists():
        return {
            "conversation_id": None,
            "facts_stored": 0,
            "actions": [],
            "error": f"File not found: {file_path}",
            "contradictions_found": 0,
            "probes_queued": 0,
        }

    chroma_client, _fact_collection, embed_model = _init_chroma_and_model()

    with contextlib.closing(get_db()) as conn:
        # Snapshot conversation IDs so the importer's additions are visible.
        existing = set()
        try:
            rows = conn.execute("SELECT id FROM conversations").fetchall()
            existing = {r[0] for r in rows}
        except Exception:
            logger.debug("Live extract: conversations table not initialized yet")

        before_ids = set(existing)

        # import_text_files adds new conversation IDs to the passed set.
        import_text_files(conn, str(path), existing)

        new_ids = existing - before_ids
        if not new_ids:
            # Already imported. Reconstruct the stable ID from the path hash
            # (mirrors import_conversations.import_text_files).
            path_hash = hashlib.md5(str(path).encode()).hexdigest()[:8]
            conv_id = f"textfile_{path.stem}_{path_hash}"
        else:
            conv_id = new_ids.pop()

        return extract_single(conn, conv_id, chroma_client, embed_model)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Live extraction: single-conversation processing"
    )
    parser.add_argument("--conversation", type=str, metavar="ID",
                        help="Extract from an existing conversation by ID")
    parser.add_argument("--file", type=str, metavar="PATH",
                        help="Import a file then extract (txt, md, docx, rst)")
    parser.add_argument("--json", action="store_true",
                        help="Output the manifest as JSON")
    args = parser.parse_args()

    if not args.conversation and not args.file:
        parser.error("Provide either --conversation <id> or --file <path>")

    if args.file:
        manifest = extract_from_file(args.file)
    else:
        chroma_client, _fact_collection, embed_model = _init_chroma_and_model()
        with contextlib.closing(get_db()) as conn:
            manifest = extract_single(conn, args.conversation,
                                      chroma_client, embed_model)

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        print(f"\n{'=' * 50}")
        print(f"Live Extraction: {manifest.get('conversation_id', '?')}")
        print(f"{'=' * 50}")
        print(f"  Facts stored: {manifest.get('facts_stored', 0)}")
        print(f"  Contradictions found: {manifest.get('contradictions_found', 0)}")
        print(f"  Probes queued: {manifest.get('probes_queued', 0)}")

        if manifest.get("error"):
            print(f"  Error: {manifest['error']}")

        actions = manifest.get("actions", [])
        if actions:
            print(f"\n  Actions ({len(actions)}):")
            for a in actions[:20]:  # Cap display at 20.
                atype = a.get("type", "?")
                text = (a.get("fact_text") or "")[:60]
                fclass = a.get("fact_class", "")
                print(f"    [{atype}] ({fclass}) {text}")
            if len(actions) > 20:
                print(f"    ... and {len(actions) - 20} more")


if __name__ == "__main__":
    main()
