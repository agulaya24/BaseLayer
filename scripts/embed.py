"""
Phase 2: Semantic Memory — Embedding Script
Creates vector embeddings for all messages and stores them in ChromaDB.

Run: python embed.py
"""

import contextlib
import time

from config import (
    VECTORS_DIR,
    EMBEDDING_MODEL as MODEL_NAME,
    EMBEDDING_BATCH_SIZE as BATCH_SIZE,
    MESSAGES_COLLECTION_NAME as COLLECTION_NAME,
    get_db,
)


def get_messages_from_sqlite() -> list[dict]:
    """Load all messages from SQLite database."""
    print("Loading messages from database...")

    with contextlib.closing(get_db()) as conn:
        cursor = conn.execute("""
            SELECT
                m.id,
                m.conversation_id,
                m.role,
                m.content_text,
                m.created_at,
                c.title as conversation_title
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.content_text IS NOT NULL
              AND LENGTH(m.content_text) > 10
            ORDER BY m.created_at
        """)

        # Note: loads all messages into memory at once (~41K rows currently).
        # Could be batched with LIMIT/OFFSET for very large datasets.
        messages = [dict(row) for row in cursor]

    print(f"Loaded {len(messages)} messages")
    return messages


def create_embedding_model():
    """Load the sentence transformer model (uses shared singleton from api_client)."""
    print(f"\nLoading embedding model: {MODEL_NAME}")
    print("(First run will download the model, ~80MB)")

    from api_client import get_embedding_model
    model = get_embedding_model()

    if model is None:
        raise ImportError("Could not load embedding model. Run: pip install sentence-transformers")

    print(f"Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")
    return model


def create_chroma_collection():
    """Create or get the ChromaDB collection."""
    import chromadb

    print(f"\nInitializing ChromaDB at {VECTORS_DIR}")

    # Create persistent client
    client = chromadb.PersistentClient(path=str(VECTORS_DIR))

    # Get or create collection (cosine distance for native similarity scores)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "description": "Message embeddings for semantic search"}
    )

    print(f"Collection '{COLLECTION_NAME}' ready. Current count: {collection.count()}")
    return client, collection


def embed_messages(messages: list[dict], model, collection, skip_existing: bool = True):
    """Embed all messages and store in ChromaDB."""

    # Check what's already embedded
    if skip_existing and collection.count() > 0:
        existing_ids = set(collection.get()["ids"])
        messages = [m for m in messages if m["id"] not in existing_ids]
        print(f"Skipping {len(existing_ids)} already-embedded messages")

    if not messages:
        print("All messages already embedded!")
        return

    total = len(messages)
    print(f"\nEmbedding {total} messages...")
    print(f"Batch size: {BATCH_SIZE}")

    start_time = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = messages[i:i + BATCH_SIZE]

        # Prepare batch data
        ids = [m["id"] for m in batch]
        texts = [m["content_text"] for m in batch]
        metadatas = [
            {
                "conversation_id": m["conversation_id"],
                "conversation_title": m["conversation_title"] or "",
                "role": m["role"],
                "created_at": m["created_at"] or 0
            }
            for m in batch
        ]

        # Generate embeddings
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        # Store in ChromaDB
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

        # Progress
        done = min(i + BATCH_SIZE, total)
        elapsed = time.time() - start_time
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0

        print(f"  [{done:,}/{total:,}] {rate:.1f} msg/sec | ETA: {eta:.0f}s")

    total_time = time.time() - start_time
    print(f"\nEmbedding complete in {total_time:.1f} seconds")
    print(f"Average rate: {total / total_time:.1f} messages/second")


def verify_embeddings(collection):
    """Verify embeddings with a test query."""
    print("\n" + "=" * 60)
    print("Verification: Testing semantic search")
    print("=" * 60)

    test_queries = [
        "trading strategy for options",
        "how to manage risk",
        "memory and context for AI"
    ]

    for query in test_queries:
        print(f"\nQuery: \"{query}\"")
        results = collection.query(
            query_texts=[query],
            n_results=3
        )

        for j, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
            title = meta.get("conversation_title", "")[:40]
            role = meta.get("role", "?")
            preview = doc[:100].replace("\n", " ") + "..."
            print(f"  {j+1}. [{role}] {title}")
            print(f"     {preview}")


def main():
    """Main embedding pipeline."""
    print("=" * 60)
    print("Phase 2: Semantic Memory — Embedding Pipeline")
    print("=" * 60)

    # Load messages
    messages = get_messages_from_sqlite()

    # Load model
    model = create_embedding_model()

    # Create ChromaDB collection
    client, collection = create_chroma_collection()

    # Embed messages
    embed_messages(messages, model, collection)

    # Verify
    verify_embeddings(collection)

    # Final stats
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total embeddings: {collection.count():,}")
    print(f"Vector storage: {VECTORS_DIR}")
    print(f"Model: {MODEL_NAME}")


if __name__ == "__main__":
    main()
