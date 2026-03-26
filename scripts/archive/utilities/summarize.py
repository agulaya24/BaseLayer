"""
Phase 3: Conversation Summarization
Uses local Ollama model to generate summaries, then embeds them for semantic search.

Run: python summarize.py
"""

import contextlib
import sys
import io
import json
import time
import requests
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import (
    VECTORS_DIR, OLLAMA_URL,
    LLM_MODEL as MODEL_NAME,
    get_db,
)

# Summarization settings
MAX_MESSAGES_PER_CONVERSATION = 50  # Limit to avoid huge prompts
MIN_MESSAGES_FOR_SUMMARY = 3  # Skip very short conversations
BATCH_SIZE = 10  # Save progress every N conversations

SUMMARY_PROMPT = """Summarize this conversation in 2-3 sentences as a narrative. What was discussed and what was the outcome or insight? Be direct and concise.

Conversation:
{conversation}

Summary:"""


def get_conversations_to_summarize() -> list[dict]:
    """Get conversations that haven't been summarized yet."""
    with contextlib.closing(get_db()) as conn:
        # Check if summaries table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='conversation_summaries'
        """)
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Get conversations without summaries
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.message_count
                FROM conversations c
                LEFT JOIN conversation_summaries s ON c.id = s.conversation_id
                WHERE s.conversation_id IS NULL
                  AND c.message_count >= ?
                ORDER BY c.created_at DESC
            """, (MIN_MESSAGES_FOR_SUMMARY,))
        else:
            # Get all conversations
            cursor = conn.execute("""
                SELECT id, title, created_at, message_count
                FROM conversations
                WHERE message_count >= ?
                ORDER BY created_at DESC
            """, (MIN_MESSAGES_FOR_SUMMARY,))

        conversations = [dict(row) for row in cursor]
    return conversations


def get_conversation_messages(conv_id: str) -> list[dict]:
    """Get messages for a conversation."""
    with contextlib.closing(get_db()) as conn:
        cursor = conn.execute("""
            SELECT role, content_text
            FROM messages
            WHERE conversation_id = ?
              AND role IN ('user', 'assistant')
              AND content_text IS NOT NULL
              AND LENGTH(content_text) > 10
            ORDER BY sequence_order
            LIMIT ?
        """, (conv_id, MAX_MESSAGES_PER_CONVERSATION))

        messages = [dict(row) for row in cursor]
    return messages


def format_conversation_for_summary(messages: list[dict]) -> str:
    """Format messages into a readable conversation."""
    lines = []
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        text = msg["content_text"][:500]  # Truncate long messages
        if len(msg["content_text"]) > 500:
            text += "..."
        lines.append(f"{role}: {text}")
    return "\n\n".join(lines)


def generate_summary_ollama(conversation_text: str) -> str | None:
    """Generate summary using Ollama."""
    prompt = SUMMARY_PROMPT.format(conversation=conversation_text)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower = more focused
                    "num_predict": 200,  # Max tokens for summary
                }
            },
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
    except Exception as e:
        print(f"    Error generating summary: {e}")
        return None


def create_summaries_table():
    """Create the summaries table if it doesn't exist."""
    with contextlib.closing(get_db()) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT PRIMARY KEY,
                    summary TEXT,
                    created_at REAL,
                    model_used TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)


def save_summary(conv_id: str, summary: str):
    """Save a summary to the database."""
    with contextlib.closing(get_db()) as conn:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO conversation_summaries
                (conversation_id, summary, created_at, model_used)
                VALUES (?, ?, ?, ?)
            """, (conv_id, summary, time.time(), MODEL_NAME))


def embed_summaries():
    """Embed all summaries into ChromaDB."""
    print("\n" + "=" * 60)
    print("Embedding summaries into vector database...")
    print("=" * 60)

    import chromadb
    from api_client import get_embedding_model

    # Load summaries
    with contextlib.closing(get_db()) as conn:
        cursor = conn.execute("""
            SELECT s.conversation_id, s.summary, c.title, c.created_at
            FROM conversation_summaries s
            JOIN conversations c ON s.conversation_id = c.id
            WHERE s.summary IS NOT NULL
        """)
        summaries = [dict(row) for row in cursor]

    if not summaries:
        print("No summaries to embed.")
        return

    print(f"Found {len(summaries)} summaries to embed")

    # Load embedding model (centralized singleton)
    print("Loading embedding model...")
    model = get_embedding_model()
    if model is None:
        print("ERROR: Could not load embedding model. Run: pip install sentence-transformers")
        return

    # Create ChromaDB collection for summaries
    client = chromadb.PersistentClient(path=str(VECTORS_DIR))

    # Delete existing collection if it exists (to rebuild)
    try:
        client.delete_collection("conversation_summaries")
    except Exception:
        pass

    collection = client.create_collection(
        name="conversation_summaries",
        metadata={"hnsw:space": "cosine", "description": "Conversation summaries for high-level retrieval"}
    )

    # Embed and store
    print("Embedding summaries...")
    ids = [s["conversation_id"] for s in summaries]
    texts = [s["summary"] for s in summaries]
    metadatas = [
        {
            "title": s["title"] or "",
            "created_at": s["created_at"] or 0
        }
        for s in summaries
    ]

    embeddings = model.encode(texts, show_progress_bar=True).tolist()

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )

    print(f"Embedded {collection.count()} summaries")


def summarize_single_conversation(conv_id: str) -> str | None:
    """Summarize a single conversation (for live use)."""
    messages = get_conversation_messages(conv_id)
    if len(messages) < MIN_MESSAGES_FOR_SUMMARY:
        return None

    conversation_text = format_conversation_for_summary(messages)
    summary = generate_summary_ollama(conversation_text)

    if summary:
        create_summaries_table()
        save_summary(conv_id, summary)

    return summary


def main():
    """Main summarization pipeline."""
    print("=" * 60)
    print("Phase 3: Conversation Summarization")
    print(f"Model: {MODEL_NAME}")
    print("=" * 60)

    # Create summaries table
    create_summaries_table()

    # Get conversations to summarize
    conversations = get_conversations_to_summarize()
    total = len(conversations)

    if total == 0:
        print("\nAll conversations already summarized!")
        embed_summaries()
        return

    print(f"\nFound {total} conversations to summarize")
    print(f"Minimum messages required: {MIN_MESSAGES_FOR_SUMMARY}")
    print()

    # Test Ollama connection
    print("Testing Ollama connection...")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        print("Ollama is running.\n")
    except Exception as e:
        print(f"Error: Cannot connect to Ollama. Is it running?")
        print(f"Start it with: ollama serve")
        return

    # Process conversations
    start_time = time.time()
    success_count = 0
    error_count = 0

    for i, conv in enumerate(conversations):
        conv_id = conv["id"]
        title = (conv["title"] or "Untitled")[:40]
        msg_count = conv["message_count"]

        print(f"[{i+1}/{total}] {title} ({msg_count} msgs)")

        # Get messages
        messages = get_conversation_messages(conv_id)
        if len(messages) < MIN_MESSAGES_FOR_SUMMARY:
            print(f"    Skipping: too few messages")
            continue

        # Format and summarize
        conversation_text = format_conversation_for_summary(messages)
        summary = generate_summary_ollama(conversation_text)

        if summary:
            save_summary(conv_id, summary)
            print(f"    ✓ {summary[:80]}...")
            success_count += 1
        else:
            error_count += 1

        # Progress stats
        if (i + 1) % BATCH_SIZE == 0:
            elapsed = time.time() - start_time
            rate = success_count / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate / 60 if rate > 0 else 0
            print(f"\n    Progress: {success_count} done, {rate:.1f}/sec, ETA: {eta:.1f} min\n")

    # Final stats
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("Summarization Complete")
    print("=" * 60)
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Time: {total_time/60:.1f} minutes")
    print(f"Rate: {success_count/total_time*60:.1f} conversations/minute")

    # Embed summaries
    embed_summaries()


if __name__ == "__main__":
    main()
