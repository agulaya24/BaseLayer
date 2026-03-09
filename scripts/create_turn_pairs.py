"""
Phase 4, Step 2: Turn-Pair Embeddings (Decision D-007)
Pairs user+assistant messages and embeds them as single units into ChromaDB.

Why turn-pairs?
Individual messages like "yes" or "thanks" carry no meaning and pollute search.
A user question paired with the assistant's answer is a much richer unit of meaning.
Turn-pairs become the PRIMARY retrieval target for the memory system.

Run: python create_turn_pairs.py
"""

import contextlib
import sqlite3
import time
import uuid
from pathlib import Path

from config import DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL

# Turn-pair specific settings (distinct from message embedding settings)
COLLECTION_NAME = "turn_pairs"
BATCH_SIZE = 100
MIN_PAIR_LENGTH = 30  # Skip very short pairs (combined text)
MAX_TEXT_LENGTH = 1000  # Truncate each message to keep embeddings focused


def create_turn_pairs_table():
    """Create a table to store turn-pair mappings in SQLite."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turn_pairs (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    user_text TEXT,
                    assistant_text TEXT,
                    combined_text TEXT,
                    pair_order INTEGER,
                    created_at REAL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_turn_pairs_conversation
                ON turn_pairs(conversation_id)
            """)


def extract_turn_pairs() -> list[dict]:
    """Extract user+assistant message pairs from all conversations."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        conn.row_factory = sqlite3.Row

        # Get all conversations
        convos = conn.execute("""
            SELECT id, title, created_at FROM conversations
            ORDER BY created_at
        """).fetchall()

        all_pairs = []
        skipped_short = 0
        skipped_no_pairs = 0

        for conv in convos:
            conv_id = conv["id"]

            # Get messages in order, only user and assistant
            messages = conn.execute("""
                SELECT id, role, content_text, created_at, sequence_order
                FROM messages
                WHERE conversation_id = ?
                  AND role IN ('user', 'assistant')
                  AND content_text IS NOT NULL
                  AND LENGTH(content_text) > 5
                ORDER BY sequence_order
            """, (conv_id,)).fetchall()

            # Pair consecutive user→assistant messages
            pair_order = 0
            i = 0
            while i < len(messages) - 1:
                msg = messages[i]
                next_msg = messages[i + 1]

                # Look for user→assistant pairs
                if msg["role"] == "user" and next_msg["role"] == "assistant":
                    user_text = msg["content_text"][:MAX_TEXT_LENGTH]
                    assistant_text = next_msg["content_text"][:MAX_TEXT_LENGTH]
                    combined = f"User: {user_text}\nAssistant: {assistant_text}"

                    if len(combined) >= MIN_PAIR_LENGTH:
                        pair_id = str(uuid.uuid4())
                        all_pairs.append({
                            "id": pair_id,
                            "conversation_id": conv_id,
                            "conversation_title": conv["title"] or "",
                            "user_message_id": msg["id"],
                            "assistant_message_id": next_msg["id"],
                            "user_text": user_text,
                            "assistant_text": assistant_text,
                            "combined_text": combined,
                            "pair_order": pair_order,
                            "created_at": msg["created_at"] or conv["created_at"] or 0,
                        })
                        pair_order += 1
                    else:
                        skipped_short += 1

                    i += 2  # Skip both messages
                else:
                    i += 1  # Move to next message

            if pair_order == 0:
                skipped_no_pairs += 1

    print(f"Extracted {len(all_pairs)} turn-pairs from {len(convos)} conversations")
    print(f"  Skipped {skipped_short} pairs (too short, <{MIN_PAIR_LENGTH} chars)")
    print(f"  Skipped {skipped_no_pairs} conversations (no valid pairs)")

    return all_pairs


def save_turn_pairs_to_sqlite(pairs: list[dict]):
    """Save turn-pair mappings to SQLite for future reference."""
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        # Check how many already exist
        existing = conn.execute("SELECT COUNT(*) FROM turn_pairs").fetchone()[0]
        if existing > 0:
            print(f"\n  Turn pairs table already has {existing} entries.")
            print(f"  Clearing and rebuilding...")
            conn.execute("DELETE FROM turn_pairs")

        for pair in pairs:
            conn.execute("""
                INSERT INTO turn_pairs
                (id, conversation_id, user_message_id, assistant_message_id,
                 user_text, assistant_text, combined_text, pair_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pair["id"], pair["conversation_id"],
                pair["user_message_id"], pair["assistant_message_id"],
                pair["user_text"], pair["assistant_text"],
                pair["combined_text"], pair["pair_order"],
                pair["created_at"],
            ))

        conn.commit()
    print(f"  Saved {len(pairs)} turn-pairs to SQLite")


def embed_turn_pairs(pairs: list[dict]):
    """Embed turn-pairs into ChromaDB."""
    print(f"\n{'=' * 60}")
    print("Embedding turn-pairs into ChromaDB...")
    print(f"{'=' * 60}")

    import chromadb
    from api_client import get_embedding_model

    # Load embedding model (centralized singleton)
    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = get_embedding_model()
    if model is None:
        print("ERROR: Could not load embedding model. Run: pip install sentence-transformers")
        return

    # Create ChromaDB collection
    client = chromadb.PersistentClient(path=str(VECTORS_DIR))

    # Delete existing collection to rebuild
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  Cleared existing '{COLLECTION_NAME}' collection")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "description": "User+assistant turn-pair embeddings (D-007)"}
    )

    # Embed in batches
    total = len(pairs)
    print(f"Embedding {total} turn-pairs in batches of {BATCH_SIZE}...")

    start_time = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = pairs[i:i + BATCH_SIZE]

        ids = [p["id"] for p in batch]
        texts = [p["combined_text"] for p in batch]
        metadatas = [
            {
                "conversation_id": p["conversation_id"],
                "conversation_title": p["conversation_title"],
                "pair_order": p["pair_order"],
                "created_at": p["created_at"],
            }
            for p in batch
        ]

        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        done = min(i + BATCH_SIZE, total)
        elapsed = time.time() - start_time
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"  [{done:,}/{total:,}] {rate:.1f} pairs/sec | ETA: {eta:.0f}s")

    total_time = time.time() - start_time
    print(f"\nEmbedding complete in {total_time:.1f} seconds")
    print(f"Average rate: {total / total_time:.1f} pairs/second")

    return collection


def verify_turn_pairs(collection):
    """Test the turn-pair embeddings with sample queries."""
    print(f"\n{'=' * 60}")
    print("Verification: Testing turn-pair search")
    print(f"{'=' * 60}")

    test_queries = [
        "managing a complex project with deadlines",
        "building a personal AI memory system",
        "weekend hobbies and interests",
        "learning a new skill from scratch",
    ]

    for query in test_queries:
        print(f"\nQuery: \"{query}\"")
        results = collection.query(query_texts=[query], n_results=3)

        for j, (doc, meta) in enumerate(zip(
            results["documents"][0], results["metadatas"][0]
        )):
            title = meta.get("conversation_title", "")[:40]
            preview = doc[:150].replace("\n", " ") + "..."
            print(f"  {j+1}. [{title}]")
            print(f"     {preview}")


def main():
    """Main turn-pair pipeline."""
    print("=" * 60)
    print("Phase 4, Step 2: Turn-Pair Embeddings (D-007)")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print("=" * 60)

    # Create SQLite table
    create_turn_pairs_table()

    # Extract pairs from all conversations
    print("\nExtracting turn-pairs from conversations...")
    pairs = extract_turn_pairs()

    if not pairs:
        print("No turn-pairs found. Check the database.")
        return

    # Save to SQLite
    print("\nSaving turn-pairs to SQLite...")
    save_turn_pairs_to_sqlite(pairs)

    # Embed into ChromaDB
    collection = embed_turn_pairs(pairs)

    # Verify
    verify_turn_pairs(collection)

    # Final stats
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    print(f"Turn-pairs extracted: {len(pairs)}")
    print(f"Turn-pairs embedded: {collection.count()}")
    print(f"SQLite table: turn_pairs")
    print(f"ChromaDB collection: {COLLECTION_NAME}")
    print(f"Vector storage: {VECTORS_DIR}")


if __name__ == "__main__":
    main()
