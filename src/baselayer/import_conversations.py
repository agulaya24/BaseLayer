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
import hashlib
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
from baselayer.config import PROJECT_ROOT, DATABASE_FILE, get_db, database_initialized
from baselayer import turn_import as TI
from baselayer.import_config import load_import_config
from baselayer.redaction import redact, redact_rows
from baselayer.turns import (TurnRow, ensure_turn_tables, legacy_messages, record_exclusion,
                             set_flag, write_conversation)

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
    config = load_import_config()
    ensure_turn_tables(conn)
    status_counts = {}

    for conv in conversations:
        conv_id = conv.get("conversation_id") or conv.get("id")
        if not conv_id:
            conv_id = f"{conv.get('title', 'untitled')}_{conv.get('create_time', 0)}"

        reason = config.excluded_reason(conversation_id=conv_id, source="chatgpt")
        if reason:
            record_exclusion(conn, conv_id, "chatgpt", reason)
            status_counts["excluded"] = status_counts.get("excluded", 0) + 1
            continue

        res = TI.build_chatgpt_turns(conv, config)
        if not res.rows:
            continue
        status = write_conversation(
            conn, conversation_id=conv_id, source="chatgpt", rows=res.rows,
            content_hash=res.content_hash, title=res.title, created_at=res.created_at,
            updated_at=res.updated_at, source_path=str(filepath),
            allowlist=config.paste_allowlist,
            own_writing=config.own_writing_rule())
        status_counts[status] = status_counts.get(status, 0) + 1
        existing_ids.add(conv_id)
        if sum(status_counts.values()) % 50 == 0:
            conn.commit()

    conn.commit()
    new_count = sum(v for k, v in status_counts.items() if k in ("new", "grown", "upgraded"))
    print(f"\n  Results: {status_counts}")
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


def parse_claude_code_session(filepath, config=None, ctx=None):
    """Parse one Claude Code session into the legacy conversation dict.

    Kept for callers that want the old shape. The rows come from the turn builder, so
    only citable subject text and assistant text appear as messages.
    """
    config = config or load_import_config()
    ctx = ctx or TI.build_claude_code_context([filepath], config)
    res = TI.build_claude_code_turns(filepath, ctx, config)
    session_id = Path(filepath).stem
    msgs = legacy_messages(session_id, res.rows)
    if not msgs:
        return None
    return {"id": session_id, "title": res.title, "created_at": res.created_at,
            "updated_at": res.updated_at, "messages": msgs, "source": "claude_code"}


def _bump(counts, key, n=1):
    counts[key] = counts.get(key, 0) + n


def import_claude_code(conn, existing_ids, session_files=None):
    """Import Claude Code sessions into the turn table (and legacy messages).

    A session already imported with the same content hash is skipped; one that grew is
    re-imported and marked for extraction (see ``turns.write_conversation``).
    """
    print(f"\n=== Importing Claude Code Sessions ===")
    print(f"  Looking in: {CLAUDE_PROJECTS_DIR}")

    if session_files is None:
        session_files = find_claude_code_sessions()
    print(f"  Found {len(session_files)} session files")
    config = load_import_config()
    ensure_turn_tables(conn)
    ctx = TI.build_claude_code_context(session_files, config)

    status_counts, detail = {}, {}
    errors = 0
    for filepath in sorted(session_files, key=str):
        session_id = Path(filepath).stem
        reason = config.excluded_reason(conversation_id=session_id, source="claude_code",
                                        path=filepath)
        if reason:
            record_exclusion(conn, session_id, "claude_code", reason)
            _bump(status_counts, "excluded")
            continue
        try:
            res = TI.build_claude_code_turns(filepath, ctx, config)
        except Exception as e:
            print(f"    ERROR parsing {Path(filepath).name}: {e}")
            errors += 1
            continue
        for k, v in res.counts.items():
            _bump(detail, k, v)
        if not res.rows:
            continue
        status = write_conversation(
            conn, conversation_id=session_id, source="claude_code", rows=res.rows,
            content_hash=res.content_hash, title=res.title, created_at=res.created_at,
            updated_at=res.updated_at, source_path=str(filepath),
            allowlist=config.paste_allowlist,
            own_writing=config.own_writing_rule())
        if status != "unchanged":
            for flag, d in res.flags.items():
                set_flag(conn, session_id, flag, d)
        _bump(status_counts, status)
        existing_ids.add(session_id)

    conn.commit()
    new_count = sum(v for k, v in status_counts.items() if k in ("new", "grown", "upgraded"))
    print(f"\n  Results: {status_counts}")
    if detail:
        print(f"  Record detail: {dict(sorted(detail.items()))}")
    if errors:
        print(f"    Errors:                  {errors}")
    return new_count


# ===========================================================================
# SOURCE 2b: Claude Code prompt history (history.jsonl)
# ===========================================================================

def import_history(conn, filepaths, existing_ids):
    """Import subject prompts from Claude Code's history.jsonl (one or more copies).

    Prompts only: history carries no assistant turns. Sessions whose full transcript is
    already in the database are skipped, so the same prompt is not imported twice.
    Import transcripts first.
    """
    if isinstance(filepaths, (str, Path)):
        filepaths = [filepaths]
    print(f"\n=== Importing Claude Code prompt history ===")
    config = load_import_config()
    ensure_turn_tables(conn)
    sessions = TI.load_history_sessions(filepaths)
    status_counts = {}
    # A prompt can survive in history under one session id and in a transcript under
    # another (resume, fork). Index the transcript's citable text so such a prompt is
    # marked a duplicate rather than counted twice. Short texts ("ok", "continue") are
    # separate utterances, not copies, so only texts of 8+ words are matched.
    transcript_text = {}
    for cid, text in conn.execute(
            "SELECT conversation_id, text FROM turns WHERE source='claude_code' AND "
            "voice_class IN ('own_typed','own_dictated') AND duplicate_of IS NULL"):
        if len(text.split()) >= 8:
            transcript_text.setdefault(TI.V.norm_hash(text), cid)
    from baselayer import recovered_import as RI
    for sid in sorted(sessions):
        conv_id = f"history_{sid}"
        entries = sessions[sid]
        if conn.execute("SELECT 1 FROM conversations WHERE id=? AND source='claude_code'",
                        (sid,)).fetchone():
            # A transcript copied before its session ended lacks the later prompts;
            # keep those, and only those, as history turns.
            entries = RI.entries_after_transcript(conn, sid, entries)
            if not entries:
                _bump(status_counts, "covered_by_transcript")
                continue
            _bump(status_counts, "covered_but_later_prompts_kept")
        reason = (config.excluded_reason(conversation_id=conv_id, source="claude_code_history")
                  or config.excluded_reason(conversation_id=sid))
        if reason:
            record_exclusion(conn, conv_id, "claude_code_history", reason)
            _bump(status_counts, "excluded")
            continue
        res = TI.build_history_turns(sid, entries, config)
        if not res.rows:
            continue
        # Mask secrets BEFORE the dedupe comparisons: the transcript and copy text they are
        # compared against was masked when it was written, so an unmasked prompt holding a
        # secret would never match its own stored copy.
        redact_rows(res.rows)
        for r in res.rows:
            if r.citable and len(r.text.split()) >= 8:
                dup = transcript_text.get(TI.V.norm_hash(r.text))
                if dup:
                    r.duplicate_of = dup
        # Prompts a database copy of this session already carries, with its context.
        for k, v in RI.mark_history_rows(conn, sid, res.rows).items():
            _bump(status_counts, f"db_copy_{k}", v)
        status = write_conversation(
            conn, conversation_id=conv_id, source="claude_code_history", rows=res.rows,
            content_hash=res.content_hash, title=res.title, created_at=res.created_at,
            updated_at=res.updated_at, source_path=";".join(str(p) for p in filepaths),
            allowlist=config.paste_allowlist,
            own_writing=config.own_writing_rule())
        _bump(status_counts, status)
        existing_ids.add(conv_id)
    conn.commit()
    print(f"  Results: {status_counts}")
    return sum(v for k, v in status_counts.items() if k in ("new", "grown", "upgraded"))


# ===========================================================================
# SOURCE 2b': originless queued prompts, append-only
# ===========================================================================

def import_originless_queued(conn, session_files, existing_ids) -> dict:
    """Write each session's originless queued prompts as a conversation of its own,
    ``queued_<sid>``, source ``claude_code_queued``. Returns the status counts.

    The session's own conversation is not touched. Putting the prompts inline (the
    ``include_originless_queued`` switch) inserts turns mid-session, which renumbers every
    later turn and moves the turn ids facts cite; ``write_conversation`` refuses that as a
    conflict. So this path refuses to run while the switch is on: the two would import the
    same prompts twice. Prompts of 8+ words whose text a transcript already carries as a
    citable turn are marked ``duplicate_of``, as history prompts are.
    """
    config = load_import_config()
    if config.include_originless_queued:
        raise ValueError("include_originless_queued is on: the transcript import already carries "
                         "these prompts inline; the append-only feeder would import them twice")
    ensure_turn_tables(conn)
    session_files = [Path(f) for f in session_files]
    ctx = TI.build_claude_code_context(session_files, config)
    transcript_text = {}
    for cid, text in conn.execute(
            "SELECT conversation_id, text FROM turns WHERE source='claude_code' AND "
            "voice_class IN ('own_typed','own_dictated') AND duplicate_of IS NULL"):
        if len(text.split()) >= 8:
            transcript_text.setdefault(TI.V.norm_hash(text), cid)
    status_counts = {}
    for filepath in sorted(session_files, key=str):
        sid = filepath.stem
        conv_id = f"queued_{sid}"
        reason = (config.excluded_reason(conversation_id=conv_id, source="claude_code_queued")
                  or config.excluded_reason(conversation_id=sid, source="claude_code",
                                            path=filepath))
        if reason:
            record_exclusion(conn, conv_id, "claude_code_queued", reason)
            _bump(status_counts, "excluded")
            continue
        res = TI.build_originless_queued_turns(filepath, ctx, config)
        if not res.rows:
            continue
        redact_rows(res.rows)
        for r in res.rows:
            if r.citable and r.duplicate_of is None and len(r.text.split()) >= 8:
                dup = transcript_text.get(TI.V.norm_hash(r.text))
                if dup:
                    r.duplicate_of = dup
        status = write_conversation(
            conn, conversation_id=conv_id, source="claude_code_queued", rows=res.rows,
            content_hash=res.content_hash, title=res.title, created_at=res.created_at,
            updated_at=res.updated_at, source_path=str(filepath),
            allowlist=config.paste_allowlist, own_writing=config.own_writing_rule())
        if status != "unchanged":
            for flag, d in res.flags.items():
                set_flag(conn, conv_id, flag, d)
        _bump(status_counts, status)
        existing_ids.add(conv_id)
    conn.commit()
    print(f"  Originless queued prompts: {status_counts}")
    return status_counts


# ===========================================================================
# SOURCE 2c: Meeting transcripts ("HH:MM Speaker Name: text" lines)
# ===========================================================================

def import_meetings(conn, path, existing_ids):
    """Import meeting transcripts. The subject's speaker label(s) come from the local
    import config (``meeting_subject_labels``); those lines are ``own_dictated`` and every
    other speaker is ``other_person``. A transcript in which no line carries a configured
    subject label is NOT imported: it would enter as all other people, which reads as a
    successful import of nothing.
    """
    print(f"\n=== Importing meeting transcripts ===")
    config = load_import_config()
    if not config.meeting_subject_labels:
        raise ValueError("meeting import needs meeting_subject_labels in the import config "
                         "(the subject's speaker label); refusing to import every line as "
                         "another person")
    ensure_turn_tables(conn)
    p = Path(path)
    files = sorted(p.rglob("*.txt")) if p.is_dir() else [p]
    status_counts = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_text(encoding="latin-1")
        if not TI.looks_like_meeting(text):
            _bump(status_counts, "not_meeting_format")
            continue
        res = TI.build_meeting_turns(text, config)
        conv_id = f"meeting_{res.content_hash[:16]}"
        reason = config.excluded_reason(conversation_id=conv_id, source="meeting", path=f)
        if reason:
            record_exclusion(conn, conv_id, "meeting", reason)
            _bump(status_counts, "excluded")
            continue
        if res.counts["subject_lines"] == 0:
            print(f"  WARNING: no line in {f.name} carries a configured subject label; "
                  f"not imported")
            _bump(status_counts, "no_subject_lines")
            continue
        status = write_conversation(
            conn, conversation_id=conv_id, source="meeting", rows=res.rows,
            content_hash=res.content_hash, title=res.title or f.stem,
            created_at=res.created_at, updated_at=res.updated_at, source_path=str(f),
            allowlist=config.paste_allowlist,
            own_writing=config.own_writing_rule())
        _bump(status_counts, status)
        existing_ids.add(conv_id)
    conn.commit()
    print(f"  Results: {status_counts}")
    return sum(v for k, v in status_counts.items() if k in ("new", "grown", "upgraded"))


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
    config = load_import_config()
    ensure_turn_tables(conn)

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

            reason = config.excluded_reason(conversation_id=conv_id, source="claude_web")
            if reason:
                record_exclusion(conn, conv_id, "claude_web", reason)
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

            res = TI.build_message_list_turns(
                [{"role": m["role"], "text": m["content_text"], "id": m["id"],
                  "created_at": m["created_at"]} for m in messages],
                config,
                hashlib.sha256(json.dumps(conv, sort_keys=True, default=str).encode("utf-8")).hexdigest())
            status = write_conversation(
                conn, conversation_id=conv_id, source="claude_web", rows=res.rows,
                content_hash=res.content_hash, title=title, created_at=created_at,
                updated_at=updated_at, source_path=str(json_file),
                allowlist=config.paste_allowlist,
                own_writing=config.own_writing_rule())
            if status == "unchanged":
                skipped += 1
                continue

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
            text, _ = redact(text)
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

# Files shorter than this are skipped. The floor exists because a file of a few words
# yields no extractable behaviour and costs an API call to discover that. 50 is inherited and
# has no measurement behind it; it is named here so it can be found and argued with rather
# than sitting as a literal inside a condition.
MIN_TEXT_FILE_CHARS = 50


def import_text_files(conn, filepath, existing_ids):
    """Import personal notes, journals, or text files as conversations.

    Supports: .txt, .md, .docx, .rst files or a directory containing them.
    Each file becomes one conversation. High-quality identity input —
    journal/notes tend to be self-reflective (finding: journal > chat for identity signal).
    """
    print(f"\n=== Importing Text Files ===")
    print(f"  Path: {filepath}")
    skipped_short = []

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
    config = load_import_config()
    ensure_turn_tables(conn)
    n_excluded = 0

    for file_path in files:
        # Use file path as stable ID (hashlib, not hash() which is randomized per-process)
        import hashlib
        path_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
        conv_id = f"textfile_{file_path.stem}_{path_hash}"
        reason = config.excluded_reason(conversation_id=conv_id, source="text_file",
                                        path=file_path)
        if reason:
            record_exclusion(conn, conv_id, "text_file", reason)
            n_excluded += 1
            continue
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

        if not text.strip() or len(text.strip()) < MIN_TEXT_FILE_CHARS:
            # SAY SO. This used to `continue` in silence while the encoding-error branch
            # directly above it printed. A user pointing the importer at a directory of short
            # notes got "0 conversations" and no reason, which is the same silent-first-run
            # shape as import-before-init.
            skipped_short.append((file_path.name, len(text.strip())))
            continue

        # Get file modification time as conversation date
        try:
            created_at = file_path.stat().st_mtime
        except Exception:
            created_at = time.time()

        title = file_path.stem.replace("_", " ").replace("-", " ").title()

        # The whole file is one subject turn. Whoever imports a text file asserts it is
        # the subject's own writing; the basis records that it is an assertion, and the
        # exclusion config is the way to keep out files that are not (for example documents
        # an assistant wrote).
        row = TurnRow(ordinal=0, speaker="subject", voice_class="own_typed", text=text,
                      basis="source:text_file_assertion", created_at=created_at)
        write_conversation(conn, conversation_id=conv_id, source="text_file", rows=[row],
                           content_hash=hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
                           title=title, created_at=created_at, updated_at=created_at,
                           source_path=str(file_path), allowlist=config.paste_allowlist,
                           own_writing=config.own_writing_rule())

        new_count += 1
        new_messages += 1
        existing_ids.add(conv_id)

    conn.commit()
    print(f"  Imported: {new_count} files ({new_messages} messages)")
    if n_excluded:
        print(f"  Excluded by the import config: {n_excluded} file(s)")
    if skipped_short:
        print(f"  Skipped {len(skipped_short)} file(s) under {MIN_TEXT_FILE_CHARS} characters:")
        for name, n in skipped_short[:10]:
            print(f"    {name} ({n} chars)")
        if len(skipped_short) > 10:
            print(f"    ... and {len(skipped_short) - 10} more")
    if new_count == 0 and skipped_short:
        print(f"  Nothing was imported. Every file was under {MIN_TEXT_FILE_CHARS} characters.")
    return new_count


def main():
    parser = argparse.ArgumentParser(
        description="Unified Conversation Importer"
    )
    parser.add_argument("--chatgpt", type=str, metavar="FILE",
                        help="Import from ChatGPT export (conversations.json)")
    parser.add_argument("--claude-code", nargs="?", const=True, default=None, metavar="DIR",
                        help="Import Claude Code sessions (default ~/.claude/projects, or DIR)")
    parser.add_argument("--history", type=str, action="append", metavar="FILE",
                        help="Import subject prompts from a Claude Code history.jsonl "
                             "(repeatable; import transcripts first)")
    parser.add_argument("--meetings", type=str, metavar="PATH",
                        help="Import meeting transcripts (HH:MM Speaker: text); needs "
                             "meeting_subject_labels in the import config")
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

    # Guard BEFORE the first connect: sqlite3.connect() creates the database file,
    # so importing against an uninitialised root used to die on "no such table:
    # conversations" AND leave an empty memory.db behind, which then made `init`
    # refuse to run. Fail with the exact command to run instead.
    if not database_initialized():
        print("Database not initialized. Run this first:")
        print("  baselayer init")
        sys.exit(1)

    with contextlib.closing(get_db_connection()) as conn:
        if args.stats:
            show_stats(conn)
            return

        if not any([args.chatgpt, args.claude_code, args.claude_web, args.text, args.json,
                    args.history, args.meetings, args.all]):
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
            global CLAUDE_PROJECTS_DIR
            if isinstance(args.claude_code, str):
                CLAUDE_PROJECTS_DIR = Path(args.claude_code)
            total_new += import_claude_code(conn, existing_ids)

        if args.history:
            total_new += import_history(conn, args.history, existing_ids)

        if args.meetings:
            total_new += import_meetings(conn, args.meetings, existing_ids)

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
