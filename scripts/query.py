"""
Query utilities for the ground-truth memory database.
Run interactively or import as a module.
"""

import contextlib
import sqlite3
from datetime import datetime

from config import DATABASE_FILE


def _escape_like(s):
    """Escape SQL LIKE metacharacters (%, _, \\) in user input."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def list_conversations(limit: int = 20, offset: int = 0) -> list[dict]:
    """List conversations ordered by most recent."""
    with contextlib.closing(get_connection()) as conn:
        cursor = conn.execute("""
            SELECT id, title, created_at, updated_at, message_count
            FROM conversations
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        results = [dict(row) for row in cursor]
    return results


def search_conversations(query: str, limit: int = 20) -> list[dict]:
    """Search conversations by title."""
    with contextlib.closing(get_connection()) as conn:
        cursor = conn.execute("""
            SELECT id, title, created_at, message_count
            FROM conversations
            WHERE title LIKE ? ESCAPE '\\'
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"%{_escape_like(query)}%", limit))
        results = [dict(row) for row in cursor]
    return results


def get_conversation(conv_id: str) -> dict | None:
    """Get a conversation with all its messages."""
    with contextlib.closing(get_connection()) as conn:
        # Get conversation metadata
        cursor = conn.execute("""
            SELECT * FROM conversations WHERE id = ?
        """, (conv_id,))
        conv = cursor.fetchone()
        if not conv:
            return None

        conv = dict(conv)

        # Get messages
        cursor = conn.execute("""
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY sequence_order
        """, (conv_id,))
        conv["messages"] = [dict(row) for row in cursor]
    return conv


def search_messages(query: str, limit: int = 50) -> list[dict]:
    """Full-text search across all messages."""
    with contextlib.closing(get_connection()) as conn:
        cursor = conn.execute("""
            SELECT m.id, m.conversation_id, m.role, m.content_text, m.created_at,
                   c.title as conversation_title
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.content_text LIKE ? ESCAPE '\\'
            ORDER BY m.created_at DESC
            LIMIT ?
        """, (f"%{_escape_like(query)}%", limit))
        results = [dict(row) for row in cursor]
    return results


def get_stats() -> dict:
    """Get database statistics."""
    with contextlib.closing(get_connection()) as conn:
        stats = {}

        cursor = conn.execute("SELECT COUNT(*) FROM conversations")
        stats["total_conversations"] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM messages")
        stats["total_messages"] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT role, COUNT(*) FROM messages GROUP BY role")
        stats["messages_by_role"] = dict(cursor.fetchall())

        cursor = conn.execute("""
            SELECT MIN(created_at), MAX(created_at) FROM conversations
            WHERE created_at IS NOT NULL
        """)
        min_ts, max_ts = cursor.fetchone()
        if min_ts:
            stats["earliest_conversation"] = datetime.fromtimestamp(min_ts).isoformat()
        if max_ts:
            stats["latest_conversation"] = datetime.fromtimestamp(max_ts).isoformat()

        cursor = conn.execute("""
            SELECT AVG(message_count) FROM conversations
        """)
        stats["avg_messages_per_conversation"] = round(cursor.fetchone()[0], 1)
    return stats


def format_timestamp(ts: float | None) -> str:
    """Format a Unix timestamp for display."""
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def print_conversation(conv_id: str, max_messages: int = None) -> None:
    """Pretty-print a conversation."""
    conv = get_conversation(conv_id)
    if not conv:
        print(f"Conversation not found: {conv_id}")
        return

    print("=" * 60)
    print(f"Title: {conv['title']}")
    print(f"Created: {format_timestamp(conv['created_at'])}")
    print(f"Messages: {conv['message_count']}")
    print("=" * 60)

    messages = conv["messages"]
    if max_messages:
        messages = messages[:max_messages]

    for msg in messages:
        role = msg["role"].upper()
        text = msg["content_text"]
        if len(text) > 500:
            text = text[:500] + "..."
        print(f"\n[{role}]")
        print(text)

    if max_messages and len(conv["messages"]) > max_messages:
        print(f"\n... ({len(conv['messages']) - max_messages} more messages)")


# Interactive mode
if __name__ == "__main__":
    print("Ground-Truth Memory Query Utility")
    print("=" * 40)

    stats = get_stats()
    print(f"\nDatabase Statistics:")
    print(f"  Conversations: {stats['total_conversations']}")
    print(f"  Messages: {stats['total_messages']}")
    print(f"  Date range: {stats.get('earliest_conversation', 'N/A')} to {stats.get('latest_conversation', 'N/A')}")
    print(f"  Avg messages/conversation: {stats['avg_messages_per_conversation']}")

    print("\n\nRecent Conversations:")
    print("-" * 40)
    for conv in list_conversations(10):
        date = format_timestamp(conv["created_at"])
        title = conv["title"][:50] if conv["title"] else "(untitled)"
        print(f"  [{date}] {title} ({conv['message_count']} msgs)")

    print("\n\nUsage (import in Python):")
    print("  from query import search_messages, get_conversation, list_conversations")
    print("  results = search_messages('API')")
    print("  conv = get_conversation('conversation_id')")
