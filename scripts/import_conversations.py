"""
Unified Conversation Importer

Imports conversations from multiple sources into the memory database.
Only imports NEW conversations that don't already exist in the database.

Sources supported:
  1. ChatGPT export (conversations.json) — incremental re-import
  2. Claude Code sessions (.claude/ directory) — local JSONL files
  3. Claude web export (ZIP from claude.ai settings) — conversation data
  4. Generic JSON files — extracts text from common fields (content, text, message, etc.)

Usage:
  python import_conversations.py --chatgpt path/to/conversations.json
  python import_conversations.py --claude-code
  python import_conversations.py --claude-web path/to/export.zip
  python import_conversations.py --stats
"""

import contextlib
import json
import sqlite3
import sys
import io
import os
import time
import argparse
import uuid
import zipfile
from pathlib import Path
from typing import Generator

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

# Shared config — single source of truth (config.py)
sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECT_ROOT, DATABASE_FILE, get_db

# Claude Code default location (Windows)
CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_PROJECTS_DIR = CLAUDE_DIR / "projects"
CLAUDE_HISTORY_FILE = CLAUDE_DIR / "history.jsonl"


# ===========================================================================
# DATABASE
# ===========================================================================

def get_db_connection():
    return get_db()


def get_existing_conversation_ids(conn):
    """Get all conversation IDs already in the database."""
    rows = conn.execute("SELECT id FROM conversations").fetchall()
    return {r["id"] for r in rows}


# ===========================================================================
# SOURCE 1: ChatGPT Export (conversations.json)
# ===========================================================================

def extract_text_content(content: dict) -> tuple:
    """Extract text content from a ChatGPT message content object."""
    content_type = content.get("content_type", "unknown")

    if content_type == "text":
        parts = content.get("parts", [])
        text = "\n".join(str(p) for p in parts if isinstance(p, str))
        return text, content_type

    elif content_type == "multimodal_text":
        parts = content.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if part.get("content_type") == "audio_transcription":
                    text_parts.append(part.get("text", ""))
                elif "asset_pointer" in part or "image_asset_pointer" in part:
                    text_parts.append("[media]")
        return "\n".join(text_parts), content_type

    elif content_type == "code":
        text = content.get("text", "")
        return text, content_type

    else:
        parts = content.get("parts", [])
        if parts:
            return "\n".join(str(p) for p in parts if isinstance(p, str)), content_type
        return "", content_type


def traverse_message_tree(mapping: dict):
    """BFS traversal of ChatGPT's message tree structure."""
    if not mapping:
        return

    root_id = None
    for msg_id, node in mapping.items():
        parent = node.get("parent")
        if parent is None or parent not in mapping:
            root_id = msg_id
            break

    if root_id is None:
        return

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

        children = node.get("children", [])
        queue.extend(children)


def import_chatgpt(conn, filepath, existing_ids):
    """Import new conversations from a ChatGPT export file."""
    print(f"\n=== Importing ChatGPT Export ===")
    print(f"  File: {filepath}")

    if zipfile.is_zipfile(filepath):
        with zipfile.ZipFile(filepath, 'r') as zf:
            candidates = [n for n in zf.namelist() if n.endswith('conversations.json')]
            if not candidates:
                print("Error: No conversations.json found in zip file")
                return 0
            with zf.open(candidates[0]) as f:
                conversations = json.load(f)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            conversations = json.load(f)

    print(f"  Total conversations in file: {len(conversations)}")

    new_count = 0
    new_messages = 0
    skipped = 0

    for conv in conversations:
        conv_id = conv.get("conversation_id") or conv.get("id")
        if not conv_id:
            conv_id = f"{conv.get('title', 'untitled')}_{conv.get('create_time', 0)}"

        # Skip if already imported
        if conv_id in existing_ids:
            skipped += 1
            continue

        title = conv.get("title", "")
        created_at = conv.get("create_time")
        updated_at = conv.get("update_time")
        mapping = conv.get("mapping", {})

        # Collect messages
        messages = []
        for seq, msg_id, message in traverse_message_tree(mapping):
            author = message.get("author", {})
            role = author.get("role", "unknown")

            metadata = message.get("metadata", {})
            if metadata.get("is_visually_hidden_from_conversation"):
                continue

            content = message.get("content", {})
            text, content_type = extract_text_content(content)

            if not text.strip():
                continue

            created = message.get("create_time")
            parent_id = None
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
            continue

        # Insert conversation
        conn.execute("""
            INSERT OR IGNORE INTO conversations
            (id, title, created_at, updated_at, message_count, source)
            VALUES (?, ?, ?, ?, ?, 'chatgpt')
        """, (conv_id, title, created_at, updated_at, len(messages)))

        # Insert messages
        conn.executemany("""
            INSERT OR IGNORE INTO messages
            (id, conversation_id, parent_id, role, content_text, content_type,
             created_at, sequence_order)
            VALUES (:id, :conversation_id, :parent_id, :role, :content_text,
                    :content_type, :created_at, :sequence_order)
        """, messages)

        new_count += 1
        new_messages += len(messages)
        existing_ids.add(conv_id)

        if new_count % 50 == 0:
            print(f"    Imported {new_count} new conversations...")
            conn.commit()

    conn.commit()

    print(f"\n  Results:")
    print(f"    Skipped (already in DB): {skipped}")
    print(f"    New conversations:       {new_count}")
    print(f"    New messages:            {new_messages}")

    return new_count


# ===========================================================================
# SOURCE 2: Claude Code Sessions (.claude/ directory)
# ===========================================================================

def find_claude_code_sessions():
    """Find all Claude Code session JSONL files."""
    sessions = []

    if not CLAUDE_PROJECTS_DIR.exists():
        print(f"  Claude projects directory not found: {CLAUDE_PROJECTS_DIR}")
        return sessions

    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # Skip tool-results and other non-session files
            if "tool-results" in str(jsonl_file):
                continue
            sessions.append(jsonl_file)

    return sessions


def parse_claude_code_session(filepath):
    """
    Parse a Claude Code JSONL session file into conversation + messages.

    Claude Code JSONL format:
    - type: "file-history-snapshot" — skip
    - type: "user" — user message, content in message.content (string)
    - type: "assistant" — assistant message, content in message.content (list of {type, text})
    - type: "summary" — context compression summary — skip
    """
    messages = []
    session_id = filepath.stem  # Filename without extension is the session ID
    first_user_message = None
    earliest_timestamp = None
    latest_timestamp = None

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type", "")

            # Skip non-message entries
            if msg_type in ("file-history-snapshot", "summary"):
                continue

            if msg_type not in ("user", "assistant"):
                continue

            message = obj.get("message", {})
            role = message.get("role", msg_type)
            content = message.get("content", "")
            timestamp = obj.get("timestamp")
            msg_uuid = obj.get("uuid", str(uuid.uuid4()))
            parent_uuid = obj.get("parentUuid")

            # Convert timestamps — may be int (ms), float (s), or string
            if timestamp is not None:
                if isinstance(timestamp, str):
                    try:
                        timestamp = float(timestamp)
                    except ValueError:
                        timestamp = None
                if timestamp is not None and timestamp > 1e12:
                    timestamp = timestamp / 1000.0

            # Track timestamps
            if timestamp is not None:
                if earliest_timestamp is None or timestamp < earliest_timestamp:
                    earliest_timestamp = timestamp
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp

            # Extract text content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # Assistant messages have content as list of {type, text}
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_use":
                            text_parts.append(f"[tool: {item.get('name', 'unknown')}]")
                        elif item.get("type") == "tool_result":
                            text_parts.append("[tool result]")
                    elif isinstance(item, str):
                        text_parts.append(item)
                text = "\n".join(text_parts)
            else:
                text = str(content) if content else ""

            if not text.strip():
                continue

            # Track first user message for title synthesis
            if role == "user" and first_user_message is None:
                first_user_message = text[:100].strip()

            messages.append({
                "id": msg_uuid,
                "conversation_id": session_id,
                "parent_id": parent_uuid,
                "role": role,
                "content_text": text,
                "content_type": "text",
                "created_at": timestamp,
                "sequence_order": len(messages)
            })

    if not messages:
        return None

    # Synthesize title from first user message
    title = first_user_message or "Claude Code Session"
    if len(title) > 80:
        title = title[:77] + "..."

    conversation = {
        "id": session_id,
        "title": title,
        "created_at": earliest_timestamp,
        "updated_at": latest_timestamp,
        "messages": messages,
        "source": "claude_code"
    }

    return conversation


def import_claude_code(conn, existing_ids):
    """Import new Claude Code sessions."""
    print(f"\n=== Importing Claude Code Sessions ===")
    print(f"  Looking in: {CLAUDE_PROJECTS_DIR}")

    session_files = find_claude_code_sessions()
    print(f"  Found {len(session_files)} session files")

    new_count = 0
    new_messages = 0
    skipped = 0
    errors = 0

    for filepath in session_files:
        session_id = filepath.stem

        if session_id in existing_ids:
            skipped += 1
            continue

        try:
            conv = parse_claude_code_session(filepath)
        except Exception as e:
            print(f"    ERROR parsing {filepath.name}: {e}")
            errors += 1
            continue

        if conv is None:
            continue

        messages = conv["messages"]

        # Insert conversation
        conn.execute("""
            INSERT OR IGNORE INTO conversations
            (id, title, created_at, updated_at, message_count, source)
            VALUES (?, ?, ?, ?, ?, 'claude_code')
        """, (conv["id"], conv["title"], conv["created_at"],
              conv["updated_at"], len(messages)))

        # Insert messages
        conn.executemany("""
            INSERT OR IGNORE INTO messages
            (id, conversation_id, parent_id, role, content_text, content_type,
             created_at, sequence_order)
            VALUES (:id, :conversation_id, :parent_id, :role, :content_text,
                    :content_type, :created_at, :sequence_order)
        """, messages)

        new_count += 1
        new_messages += len(messages)
        existing_ids.add(session_id)

    conn.commit()

    print(f"\n  Results:")
    print(f"    Skipped (already in DB): {skipped}")
    print(f"    New sessions:            {new_count}")
    print(f"    New messages:            {new_messages}")
    if errors:
        print(f"    Errors:                  {errors}")

    return new_count


# ===========================================================================
# SOURCE 3: Claude Web Export (ZIP from claude.ai)
# ===========================================================================

def import_claude_web(conn, filepath, existing_ids):
    """
    Import conversations from a Claude.ai data export.

    Claude exports a ZIP containing JSON files with conversation data.
    The exact format may vary — this handles the known structure.
    """
    print(f"\n=== Importing Claude Web Export ===")
    print(f"  File: {filepath}")

    if not zipfile.is_zipfile(filepath):
        # Maybe it's already extracted — try as a directory
        if os.path.isdir(filepath):
            return _import_claude_web_dir(conn, Path(filepath), existing_ids)
        print(f"  ERROR: Not a valid ZIP file: {filepath}")
        return 0

    # Extract ZIP to temp location (with ZipSlip protection)
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_resolved = Path(tmpdir).resolve()
        with zipfile.ZipFile(filepath, 'r') as zf:
            for member in zf.namelist():
                member_path = (tmpdir_resolved / member).resolve()
                if not str(member_path).startswith(str(tmpdir_resolved)):
                    print(f"  WARNING: Skipping suspicious ZIP entry: {member}")
                    continue
                zf.extract(member, tmpdir)
            print(f"  Extracted to temp directory")
            return _import_claude_web_dir(conn, Path(tmpdir), existing_ids)


def _import_claude_web_dir(conn, dirpath, existing_ids):
    """Import Claude web conversations from an extracted directory."""
    new_count = 0
    new_messages = 0
    skipped = 0

    # Look for conversation JSON files
    json_files = list(dirpath.rglob("*.json"))
    print(f"  Found {len(json_files)} JSON files")

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        # Handle both single conversation and array of conversations
        conversations = data if isinstance(data, list) else [data]

        for conv in conversations:
            # Claude web export format: uuid, name, chat_messages[]
            conv_id = conv.get("uuid") or conv.get("id") or conv.get("conversation_id")
            if not conv_id:
                continue

            if conv_id in existing_ids:
                skipped += 1
                continue

            title = conv.get("name") or conv.get("title") or "Claude Conversation"
            created_at = conv.get("created_at") or conv.get("create_time")
            updated_at = conv.get("updated_at") or conv.get("update_time")

            # Parse timestamp strings if needed
            if isinstance(created_at, str):
                try:
                    from datetime import datetime
                    created_at = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    ).timestamp()
                except (ValueError, TypeError):
                    created_at = None

            if isinstance(updated_at, str):
                try:
                    from datetime import datetime
                    updated_at = datetime.fromisoformat(
                        updated_at.replace("Z", "+00:00")
                    ).timestamp()
                except (ValueError, TypeError):
                    updated_at = None

            # Extract messages
            raw_messages = conv.get("chat_messages") or conv.get("messages") or []
            messages = []

            for i, msg in enumerate(raw_messages):
                role = msg.get("sender") or msg.get("role") or "unknown"
                # Claude uses "human"/"assistant" — normalize
                if role == "human":
                    role = "user"

                text = msg.get("text") or msg.get("content") or ""

                # Handle content as list (like API format)
                if isinstance(text, list):
                    text_parts = []
                    for item in text:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            text_parts.append(item)
                    text = "\n".join(text_parts)

                if not text.strip():
                    continue

                msg_id = msg.get("uuid") or msg.get("id") or str(uuid.uuid4())
                msg_created = msg.get("created_at") or msg.get("create_time")

                if isinstance(msg_created, str):
                    try:
                        from datetime import datetime
                        msg_created = datetime.fromisoformat(
                            msg_created.replace("Z", "+00:00")
                        ).timestamp()
                    except (ValueError, TypeError):
                        msg_created = None

                messages.append({
                    "id": msg_id,
                    "conversation_id": conv_id,
                    "parent_id": None,
                    "role": role,
                    "content_text": text,
                    "content_type": "text",
                    "created_at": msg_created,
                    "sequence_order": i
                })

            if not messages:
                continue

            conn.execute("""
                INSERT OR IGNORE INTO conversations
                (id, title, created_at, updated_at, message_count, source)
                VALUES (?, ?, ?, ?, ?, 'claude_web')
            """, (conv_id, title, created_at, updated_at, len(messages)))

            conn.executemany("""
                INSERT OR IGNORE INTO messages
                (id, conversation_id, parent_id, role, content_text, content_type,
                 created_at, sequence_order)
                VALUES (:id, :conversation_id, :parent_id, :role, :content_text,
                        :content_type, :created_at, :sequence_order)
            """, messages)

            new_count += 1
            new_messages += len(messages)
            existing_ids.add(conv_id)

    conn.commit()

    print(f"\n  Results:")
    print(f"    Skipped (already in DB): {skipped}")
    print(f"    New conversations:       {new_count}")
    print(f"    New messages:            {new_messages}")

    return new_count


# ===========================================================================
# STATS
# ===========================================================================

def show_stats(conn):
    """Show import statistics by source."""
    print(f"\n=== Import Statistics ===\n")

    rows = conn.execute("""
        SELECT source, COUNT(*) as conv_count
        FROM conversations
        GROUP BY source
        ORDER BY conv_count DESC
    """).fetchall()

    total_convs = 0
    for r in rows:
        source = r["source"] or "unknown"
        count = r["conv_count"]
        total_convs += count
        print(f"  {source:15s} {count:5d} conversations")

    print(f"  {'TOTAL':15s} {total_convs:5d} conversations")

    # Message counts
    total_msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    print(f"\n  Total messages: {total_msgs:,}")

    # Extraction coverage
    extracted = conn.execute("""
        SELECT COUNT(DISTINCT source_conversation_id)
        FROM memory_facts
        WHERE superseded_by IS NULL
    """).fetchone()[0]
    print(f"  Conversations with extracted facts: {extracted}")
    print(f"  Conversations without extraction:   {total_convs - extracted}")

    # Recent imports
    print(f"\n  Recent conversations (last 5 added):")
    rows = conn.execute("""
        SELECT id, title, source, created_at
        FROM conversations
        ORDER BY rowid DESC
        LIMIT 5
    """).fetchall()
    for r in rows:
        source = r["source"] or "?"
        title = (r["title"] or "Untitled")[:50]
        print(f"    [{source:12s}] {title}")


# ===========================================================================
# SOURCE 4: Generic JSON Files
# ===========================================================================

# Common field names for text content in JSON structures
_JSON_TEXT_FIELDS = ("content", "text", "message", "body", "reflection",
                     "note", "entry", "summary", "description", "thought")


def _extract_texts_from_json(data) -> list[str]:
    """Extract text strings from arbitrary JSON structures.

    Walks the JSON tree and pulls text from common field names.
    Falls back to collecting all string values over 50 chars.
    Returns a list of text strings suitable for import.
    """
    texts = []

    def _walk(obj, depth=0):
        if depth > 20:  # prevent infinite recursion
            return
        if isinstance(obj, dict):
            # Try known text fields first
            for field in _JSON_TEXT_FIELDS:
                val = obj.get(field)
                if isinstance(val, str) and len(val.strip()) >= 50:
                    texts.append(val.strip())
            # Recurse into all values
            for v in obj.values():
                _walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, depth + 1)

    _walk(data)

    # If known fields found nothing, fall back to all long strings
    if not texts:
        fallback = []

        def _collect_strings(obj, depth=0):
            if depth > 20:
                return
            if isinstance(obj, str) and len(obj.strip()) >= 50:
                fallback.append(obj.strip())
            elif isinstance(obj, dict):
                for v in obj.values():
                    _collect_strings(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _collect_strings(item, depth + 1)

        _collect_strings(data)
        texts = fallback

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in texts:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return unique


def import_json_files(conn, filepath, existing_ids):
    """Import generic JSON files as conversations.

    Walks the JSON structure and extracts text from common field names
    (content, text, message, body, reflection, etc.). Falls back to
    collecting all string values over 50 characters.

    Each extracted text block becomes one conversation message.
    If only one text block is found, it becomes a single conversation.
    If multiple are found, they are grouped into one conversation
    with sequential messages.
    """
    print(f"\n=== Importing JSON File ===")
    print(f"  Path: {filepath}")

    path = Path(filepath)
    files = []
    if path.is_dir():
        files.extend(sorted(path.glob("*.json")))
        files.extend(sorted(path.glob("**/*.json")))
        files = sorted(set(files))
    elif path.is_file():
        files = [path]
    else:
        print(f"  ERROR: Path not found: {filepath}")
        return 0

    print(f"  Found {len(files)} JSON files")

    new_count = 0
    total_messages = 0

    for file_path in files:
        import hashlib
        path_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
        conv_id = f"json_{file_path.stem}_{path_hash}"
        if conv_id in existing_ids:
            continue

        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"  Skipping {file_path.name}: {e}")
            continue

        texts = _extract_texts_from_json(data)
        if not texts:
            print(f"  Skipping {file_path.name}: no text content found")
            continue

        try:
            created_at = file_path.stat().st_mtime
        except Exception:
            created_at = time.time()

        title = file_path.stem.replace("_", " ").replace("-", " ").title()

        conn.execute("""
            INSERT INTO conversations (id, title, created_at, updated_at, message_count, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (conv_id, title, created_at, created_at, len(texts), "json_file"))

        for seq, text in enumerate(texts):
            msg_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO messages (id, conversation_id, role, content_text, sequence_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (msg_id, conv_id, "user", text, seq, created_at))

        new_count += 1
        total_messages += len(texts)
        existing_ids.add(conv_id)

    conn.commit()
    print(f"  Imported: {new_count} files ({total_messages} messages)")
    return new_count


# ===========================================================================
# MAIN
# ===========================================================================

def import_text_files(conn, filepath, existing_ids):
    """Import personal notes, journals, or text files as conversations.

    Supports: .txt, .md, .docx, .rst files or a directory containing them.
    Each file becomes one conversation. High-quality identity input —
    journal/notes tend to be self-reflective (finding: journal > chat for identity signal).
    """
    print(f"\n=== Importing Text Files ===")
    print(f"  Path: {filepath}")

    path = Path(filepath)
    files = []
    if path.is_dir():
        for ext in ("*.txt", "*.md", "*.docx", "*.rst"):
            files.extend(path.glob(ext))
            files.extend(path.glob(f"**/{ext}"))
        files = sorted(set(files))
    elif path.is_file():
        files = [path]
    else:
        print(f"  ERROR: Path not found: {filepath}")
        return 0

    print(f"  Found {len(files)} text files")

    new_count = 0
    new_messages = 0

    for file_path in files:
        # Use file path as stable ID (hashlib, not hash() which is randomized per-process)
        import hashlib
        path_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
        conv_id = f"textfile_{file_path.stem}_{path_hash}"
        if conv_id in existing_ids:
            continue

        # Read content
        text = ""
        if file_path.suffix.lower() == ".docx":
            try:
                from docx import Document
                doc = Document(str(file_path))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except Exception as e:
                print(f"  Skipping {file_path.name}: {e}")
                continue
        else:
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    text = file_path.read_text(encoding="latin-1")
                except Exception:
                    print(f"  Skipping {file_path.name}: encoding error")
                    continue

        if not text.strip() or len(text.strip()) < 50:
            continue

        # Get file modification time as conversation date
        try:
            created_at = file_path.stat().st_mtime
        except Exception:
            created_at = time.time()

        title = file_path.stem.replace("_", " ").replace("-", " ").title()

        # Store as conversation
        conn.execute("""
            INSERT INTO conversations (id, title, created_at, updated_at, message_count, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (conv_id, title, created_at, created_at, 1, "text_file"))

        # Store entire file as a single "user" message (self-authored content)
        msg_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO messages (id, conversation_id, role, content_text, sequence_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg_id, conv_id, "user", text, 0, created_at))

        new_count += 1
        new_messages += 1
        existing_ids.add(conv_id)

    conn.commit()
    print(f"  Imported: {new_count} files ({new_messages} messages)")
    return new_count


def main():
    parser = argparse.ArgumentParser(
        description="Unified Conversation Importer"
    )
    parser.add_argument("--chatgpt", type=str, metavar="FILE",
                        help="Import from ChatGPT export (conversations.json)")
    parser.add_argument("--claude-code", action="store_true",
                        help="Import Claude Code sessions from ~/.claude/")
    parser.add_argument("--claude-web", type=str, metavar="FILE",
                        help="Import from Claude.ai export (ZIP file)")
    parser.add_argument("--text", type=str, metavar="PATH",
                        help="Import text files (.txt, .md, .docx, .rst) or a directory of them")
    parser.add_argument("--json", type=str, metavar="PATH",
                        help="Import generic JSON files or a directory of them")
    parser.add_argument("--stats", action="store_true",
                        help="Show import statistics")
    parser.add_argument("--all", action="store_true",
                        help="Import from all available sources")
    args = parser.parse_args()

    with contextlib.closing(get_db_connection()) as conn:
        if args.stats:
            show_stats(conn)
            return

        if not any([args.chatgpt, args.claude_code, args.claude_web, args.text, args.json, args.all]):
            parser.print_help()
            return

        # Get existing IDs to avoid re-importing
        existing_ids = get_existing_conversation_ids(conn)
        print(f"Existing conversations in database: {len(existing_ids)}")

        total_new = 0

        if args.chatgpt or args.all:
            filepath = args.chatgpt
            if args.all and not filepath:
                default = PROJECT_ROOT / "data" / "raw" / "conversations.json"
                if default.exists():
                    filepath = str(default)
            if filepath:
                total_new += import_chatgpt(conn, filepath, existing_ids)

        if args.claude_code or args.all:
            total_new += import_claude_code(conn, existing_ids)

        if args.claude_web:
            total_new += import_claude_web(conn, args.claude_web, existing_ids)

        if args.text:
            total_new += import_text_files(conn, args.text, existing_ids)

        if args.json:
            total_new += import_json_files(conn, args.json, existing_ids)

        # Summary
        print(f"\n{'='*50}")
        print(f"Import Complete: {total_new} new conversations added")
        print(f"{'='*50}")

        if total_new > 0:
            print(f"\nNext steps:")
            print(f"  1. Extract facts:     baselayer extract")
            print(f"  2. Run full pipeline: baselayer process")
            print(f"  3. Author layers:     baselayer author")

        show_stats(conn)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
