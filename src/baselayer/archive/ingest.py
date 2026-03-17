"""
Ground-Truth Memory Ingestion Script
Parses ChatGPT export and populates SQLite database.
"""

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Generator

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CONVERSATIONS_FILE = PROJECT_ROOT / "data" / "raw" / "conversations.json"
DATABASE_FILE = PROJECT_ROOT / "data" / "database" / "memory.db"


def create_schema(conn: sqlite3.Connection) -> None:
    """Create database tables and indexes."""
    conn.executescript("""
        -- Core tables
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at REAL,
            updated_at REAL,
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            parent_id TEXT,
            role TEXT,
            content_text TEXT,
            content_type TEXT,
            created_at REAL,
            sequence_order INTEGER,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
        CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
    """)
    conn.commit()


def extract_text_content(content: dict) -> tuple[str, str]:
    """
    Extract text content from a message's content object.
    Returns (text, content_type).
    """
    content_type = content.get("content_type", "unknown")

    if content_type == "text":
        parts = content.get("parts", [])
        text = "\n".join(str(p) for p in parts if isinstance(p, str))
        return text, content_type

    elif content_type == "multimodal_text":
        # Extract text from multimodal content (including audio transcriptions)
        parts = content.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                # Audio transcription
                if part.get("content_type") == "audio_transcription":
                    text_parts.append(part.get("text", ""))
                # Image or other asset - note its presence
                elif "asset_pointer" in part or "image_asset_pointer" in part:
                    text_parts.append("[media]")
        return "\n".join(text_parts), content_type

    elif content_type == "code":
        text = content.get("text", "")
        return text, content_type

    else:
        # Fallback: try to get parts or text
        parts = content.get("parts", [])
        if parts:
            return "\n".join(str(p) for p in parts if isinstance(p, str)), content_type
        return "", content_type


def traverse_message_tree(mapping: dict) -> Generator[tuple[int, str, dict], None, None]:
    """
    Traverse the message tree in order, yielding (sequence_order, message_id, message_data).
    Handles the tree structure where each node has parent/children references.
    """
    if not mapping:
        return

    # Find root node (no parent or parent not in mapping)
    root_id = None
    for msg_id, node in mapping.items():
        parent = node.get("parent")
        if parent is None or parent not in mapping:
            root_id = msg_id
            break

    if root_id is None:
        return

    # BFS traversal following children links
    sequence = 0
    queue = [root_id]
    visited = set()

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        node = mapping.get(current_id)
        if node is None:
            continue

        message = node.get("message")
        if message is not None:
            yield sequence, current_id, message
            sequence += 1

        # Add children to queue
        children = node.get("children", [])
        queue.extend(children)


def parse_conversations(filepath: Path) -> Generator[dict, None, None]:
    """Stream-parse the conversations JSON file."""
    print(f"Loading conversations from {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    print(f"Found {len(conversations)} conversations")
    for conv in conversations:
        yield conv


def ingest_conversation(conn: sqlite3.Connection, conv: dict) -> int:
    """
    Ingest a single conversation into the database.
    Returns the number of messages ingested.
    """
    # Generate a conversation ID from title + create_time if not present
    conv_id = conv.get("conversation_id") or conv.get("id")
    if not conv_id:
        conv_id = f"{conv.get('title', 'untitled')}_{conv.get('create_time', 0)}"

    title = conv.get("title", "")
    created_at = conv.get("create_time")
    updated_at = conv.get("update_time")

    mapping = conv.get("mapping", {})

    # Collect messages
    messages = []
    for seq, msg_id, message in traverse_message_tree(mapping):
        author = message.get("author", {})
        role = author.get("role", "unknown")

        # Skip system messages that are hidden
        metadata = message.get("metadata", {})
        if metadata.get("is_visually_hidden_from_conversation"):
            continue

        content = message.get("content", {})
        text, content_type = extract_text_content(content)

        # Skip empty messages
        if not text.strip():
            continue

        created = message.get("create_time")
        parent_id = None
        # Find parent from mapping
        for node_id, node in mapping.items():
            if msg_id in node.get("children", []):
                parent_id = node_id
                break

        messages.append({
            "id": msg_id,
            "conversation_id": conv_id,
            "parent_id": parent_id,
            "role": role,
            "content_text": text,
            "content_type": content_type,
            "created_at": created,
            "sequence_order": seq
        })

    if not messages:
        return 0

    # Insert conversation
    conn.execute("""
        INSERT OR REPLACE INTO conversations (id, title, created_at, updated_at, message_count)
        VALUES (?, ?, ?, ?, ?)
    """, (conv_id, title, created_at, updated_at, len(messages)))

    # Insert messages
    conn.executemany("""
        INSERT OR REPLACE INTO messages
        (id, conversation_id, parent_id, role, content_text, content_type, created_at, sequence_order)
        VALUES (:id, :conversation_id, :parent_id, :role, :content_text, :content_type, :created_at, :sequence_order)
    """, messages)

    return len(messages)


def main():
    """Main ingestion entry point."""
    print("=" * 60)
    print("Ground-Truth Memory Ingestion")
    print("=" * 60)

    # Create/connect to database
    print(f"\nDatabase: {DATABASE_FILE}")
    with contextlib.closing(sqlite3.connect(DATABASE_FILE)) as conn:
        # Create schema
        print("Creating schema...")
        create_schema(conn)

        # Ingest conversations
        total_conversations = 0
        total_messages = 0

        for conv in parse_conversations(CONVERSATIONS_FILE):
            msg_count = ingest_conversation(conn, conv)
            if msg_count > 0:
                total_conversations += 1
                total_messages += msg_count

                if total_conversations % 100 == 0:
                    print(f"  Processed {total_conversations} conversations...")
                    conn.commit()

        conn.commit()

        # Print summary
        print("\n" + "=" * 60)
        print("Ingestion Complete")
        print("=" * 60)
        print(f"Conversations: {total_conversations}")
        print(f"Messages:      {total_messages}")

        # Verify with queries
        print("\n--- Verification ---")
        cursor = conn.execute("SELECT COUNT(*) FROM conversations")
        print(f"Conversations in DB: {cursor.fetchone()[0]}")

        cursor = conn.execute("SELECT COUNT(*) FROM messages")
        print(f"Messages in DB: {cursor.fetchone()[0]}")

        cursor = conn.execute("SELECT role, COUNT(*) FROM messages GROUP BY role")
        print("Messages by role:")
        for role, count in cursor:
            print(f"  {role}: {count}")

    print(f"\nDatabase saved to: {DATABASE_FILE}")


if __name__ == "__main__":
    main()
