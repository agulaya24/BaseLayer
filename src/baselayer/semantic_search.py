"""
Phase 2: Semantic Search Utility
Search your memory by meaning, not just keywords.

Run interactively: python semantic_search.py
Or import: from semantic_search import search, search_with_context
"""

import contextlib
from datetime import datetime

from baselayer.config import (
    VECTORS_DIR,
    MESSAGES_COLLECTION_NAME as COLLECTION_NAME,
    get_db,
)

# Lazy-loaded globals
_client = None
_collection = None


def get_collection():
    """Get ChromaDB collection (lazy loaded)."""
    global _client, _collection

    if _collection is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        _collection = _client.get_collection(name=COLLECTION_NAME)

    return _collection


def search(query: str, n_results: int = 10, role_filter: str = None) -> list[dict]:
    """
    Search messages by semantic similarity.

    Args:
        query: Natural language query
        n_results: Number of results to return
        role_filter: Optional filter by role ("user", "assistant", "tool")

    Returns:
        List of matching messages with metadata and similarity scores
    """
    collection = get_collection()

    # Build query
    where_filter = None
    if role_filter:
        where_filter = {"role": role_filter}

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"]
    )

    # Format results
    matches = []
    for i in range(len(results["ids"][0])):
        matches.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "conversation_id": results["metadatas"][0][i].get("conversation_id"),
            "conversation_title": results["metadatas"][0][i].get("conversation_title"),
            "role": results["metadatas"][0][i].get("role"),
            "created_at": results["metadatas"][0][i].get("created_at"),
            "distance": results["distances"][0][i]  # Lower = more similar
        })

    return matches


def search_with_context(query: str, n_results: int = 5, context_messages: int = 2) -> list[dict]:
    """
    Search and return results with surrounding conversation context.

    Args:
        query: Natural language query
        n_results: Number of results to return
        context_messages: Number of messages before/after to include

    Returns:
        List of results with conversation context
    """
    # Get semantic search results
    matches = search(query, n_results=n_results)

    if not matches:
        return []

    # Batch-load all messages for the matched conversations in one query
    # instead of N+1 per-result queries.
    conv_ids = list({m["conversation_id"] for m in matches})
    with contextlib.closing(get_db()) as conn:
        placeholders = ",".join("?" for _ in conv_ids)
        cursor = conn.execute(
            "SELECT id, conversation_id, role, content_text, sequence_order"
            " FROM messages"
            " WHERE conversation_id IN (" + placeholders + ")"
            " ORDER BY conversation_id, sequence_order",
            conv_ids
        )

        # Group messages by conversation_id
        messages_by_conv = {}
        for row in cursor:
            row_dict = dict(row)
            cid = row_dict["conversation_id"]
            if cid not in messages_by_conv:
                messages_by_conv[cid] = []
            messages_by_conv[cid].append(row_dict)

    results_with_context = []

    for match in matches:
        all_messages = messages_by_conv.get(match["conversation_id"], [])

        # Find the matched message's position
        match_idx = None
        for i, msg in enumerate(all_messages):
            if msg["id"] == match["id"]:
                match_idx = i
                break

        if match_idx is not None:
            # Get context window
            start = max(0, match_idx - context_messages)
            end = min(len(all_messages), match_idx + context_messages + 1)
            context = all_messages[start:end]

            results_with_context.append({
                "match": match,
                "context": context,
                "match_position": match_idx - start
            })

    return results_with_context


def search_conversations(query: str, n_results: int = 10) -> list[dict]:
    """
    Search and group results by conversation.

    Returns unique conversations that match the query.
    """
    # Get more results than needed to find unique conversations
    matches = search(query, n_results=n_results * 3)

    # Group by conversation
    seen_convos = set()
    conversations = []

    for match in matches:
        conv_id = match["conversation_id"]
        if conv_id not in seen_convos:
            seen_convos.add(conv_id)
            conversations.append({
                "conversation_id": conv_id,
                "title": match["conversation_title"],
                "best_match": match,
                "relevance": 1 - match["distance"]  # Convert distance to similarity
            })

            if len(conversations) >= n_results:
                break

    return conversations


def format_timestamp(ts: float | None) -> str:
    """Format Unix timestamp for display."""
    if ts is None or ts == 0:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def print_results(matches: list[dict], show_full: bool = False):
    """Pretty print search results."""
    for i, match in enumerate(matches):
        title = match.get("conversation_title", "")[:40]
        role = match.get("role", "?")
        date = format_timestamp(match.get("created_at"))
        from baselayer.config import chromadb_dist_to_similarity
        distance = match.get("distance", 0)
        similarity = chromadb_dist_to_similarity(distance) * 100

        print(f"\n{i+1}. [{role}] {title}")
        print(f"   Date: {date} | Similarity: {similarity:.1f}%")

        text = match.get("text", "")
        if show_full:
            print(f"   {text}")
        else:
            preview = text[:200].replace("\n", " ")
            if len(text) > 200:
                preview += "..."
            print(f"   {preview}")


def interactive_search():
    """Interactive search mode."""
    print("=" * 60)
    print("Semantic Memory Search")
    print("=" * 60)
    print("Search your conversations by meaning, not just keywords.")
    print("Type 'quit' to exit, 'help' for commands.\n")

    collection = get_collection()
    print(f"Loaded {collection.count():,} message embeddings.\n")

    while True:
        try:
            query = input("Search: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue

        if query.lower() == "quit":
            print("Goodbye!")
            break

        if query.lower() == "help":
            print("""
Commands:
  <query>           Search for messages
  user: <query>     Search only your messages
  assistant: <query> Search only assistant responses
  conv: <query>     Find relevant conversations
  context: <query>  Show results with conversation context
  quit              Exit
            """)
            continue

        # Parse special commands
        if query.startswith("user:"):
            matches = search(query[5:].strip(), role_filter="user")
            print_results(matches)
        elif query.startswith("assistant:"):
            matches = search(query[10:].strip(), role_filter="assistant")
            print_results(matches)
        elif query.startswith("conv:"):
            convos = search_conversations(query[5:].strip())
            print(f"\nFound {len(convos)} relevant conversations:\n")
            for i, c in enumerate(convos):
                print(f"  {i+1}. {c['title']}")
                print(f"     Relevance: {c['relevance']*100:.1f}%")
        elif query.startswith("context:"):
            results = search_with_context(query[8:].strip(), n_results=3)
            for r in results:
                print(f"\n{'='*60}")
                print(f"Conversation: {r['match']['conversation_title']}")
                print("=" * 60)
                for j, msg in enumerate(r["context"]):
                    marker = ">>>" if j == r["match_position"] else "   "
                    role = msg["role"].upper()
                    text = msg["content_text"][:300].replace("\n", " ")
                    print(f"{marker} [{role}] {text}")
        else:
            matches = search(query)
            print_results(matches)


def main():
    """Entry point for CLI: baselayer search."""
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        matches = search(query)
        print_results(matches)
    else:
        interactive_search()


if __name__ == "__main__":
    main()
