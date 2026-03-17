"""
Store and manage epistemic anchors in the database.

Usage:
  python scripts/store_anchors.py --store                          # Store from data/anchors_candidates.json
  python scripts/store_anchors.py --store --file path/to/file.json # Store from specific file
  python scripts/store_anchors.py --list                           # List all stored anchors
  python scripts/store_anchors.py --active                         # Show only active anchors
"""

import contextlib
import sqlite3
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from config import DATABASE_FILE, PROJECT_ROOT


def create_table(conn):
    """Create epistemic_anchors table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS epistemic_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_number INTEGER NOT NULL,
            anchor_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            formulation_version INTEGER DEFAULT 1,
            original_text TEXT,
            review_notes TEXT,
            session_confirmed INTEGER,
            source_fact_ids TEXT,
            layer TEXT DEFAULT 'core',
            created_at REAL,
            superseded_by INTEGER,
            FOREIGN KEY (superseded_by) REFERENCES epistemic_anchors(id)
        )
    """)
    conn.commit()


def store_anchors(conn, anchors_file=None):
    """Store anchors from a JSON file into the database.

    The anchors file should be a JSON array of objects with fields:
        number, text, status, original_text (optional), review_notes (optional),
        session (optional), layer (optional, default 'core')

    If no file is specified, looks for data/anchors_candidates.json relative
    to MEMORY_SYSTEM_ROOT.
    """
    create_table(conn)

    if anchors_file is None:
        # Check both possible locations (extract_anchors saves to data/database/)
        candidates = [
            PROJECT_ROOT / "data" / "anchors_candidates.json",
            PROJECT_ROOT / "data" / "database" / "anchor_candidates.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                anchors_file = candidate
                break
        if anchors_file is None:
            print("ERROR: Anchors file not found. Checked:")
            for c in candidates:
                print("  %s" % c)
            print("Create a JSON file with your confirmed anchors, or run extract_anchors first.")
            return

    anchors_path = Path(anchors_file)
    if not anchors_path.exists():
        print("ERROR: Anchors file not found: %s" % anchors_path)
        return

    with open(anchors_path, "r", encoding="utf-8") as f:
        anchors = json.load(f)

    if not isinstance(anchors, list):
        print("ERROR: Anchors file must contain a JSON array.")
        return

    # Normalize format: extract_anchors outputs {"anchor", "source_facts", "why"}
    # but store expects {"number", "text"}. Accept either.
    normalized = []
    for i, a in enumerate(anchors):
        if "text" in a and "number" in a:
            normalized.append(a)
        elif "anchor" in a:
            normalized.append({
                "number": a.get("number", i + 1),
                "text": a["anchor"],
                "status": a.get("status", "confirmed"),
                "source_facts": a.get("source_facts", []),
            })
        else:
            print("WARNING: Skipping unrecognized anchor format: %s" % a)
    anchors = normalized

    now = time.time()
    count = 0
    for a in anchors:
        if "number" not in a or "text" not in a:
            print("WARNING: Skipping anchor missing 'number' or 'text': %s" % a)
            continue
        # Idempotency guard: skip if anchor_number already exists (non-superseded)
        existing = conn.execute(
            "SELECT id FROM epistemic_anchors WHERE anchor_number = ? AND superseded_by IS NULL",
            (a["number"],)
        ).fetchone()
        if existing:
            continue
        source_ids = a.get("source_facts") or a.get("source_fact_ids")
        source_ids_str = json.dumps(source_ids) if source_ids else None
        conn.execute("""
            INSERT INTO epistemic_anchors
            (anchor_number, anchor_text, status, original_text, review_notes,
             session_confirmed, layer, source_fact_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            a["number"],
            a["text"],
            a.get("status", "confirmed"),
            a.get("original_text"),
            a.get("review_notes"),
            a.get("session"),
            a.get("layer", "core"),
            source_ids_str,
            now,
        ))
        count += 1

    conn.commit()
    print("Stored %d epistemic anchors from %s." % (count, anchors_path.name))


def list_anchors(conn, active_only=False):
    """List stored anchors."""
    create_table(conn)

    query = "SELECT anchor_number, anchor_text, status, review_notes FROM epistemic_anchors"
    if active_only:
        query += " WHERE status IN ('confirmed', 'confirmed_flagged') AND superseded_by IS NULL"
    query += " ORDER BY anchor_number"

    rows = conn.execute(query).fetchall()

    if not rows:
        print("No anchors stored.")
        return

    for num, text, status, notes in rows:
        flag = ""
        if status == "confirmed_flagged":
            flag = " [FLAGGED]"
        elif status == "paused":
            flag = " [PAUSED]"
        print("#%d%s: %s" % (num, flag, text))

    print("\n%d anchors total." % len(rows))


def main():
    with contextlib.closing(sqlite3.connect(str(DATABASE_FILE))) as conn:
        if "--store" in sys.argv:
            # Optional: --file path/to/anchors.json
            anchors_file = None
            if "--file" in sys.argv:
                idx = sys.argv.index("--file")
                if idx + 1 < len(sys.argv):
                    anchors_file = sys.argv[idx + 1]
                    # Validate file path resolves within project data directory
                    file_resolved = Path(anchors_file).resolve()
                    data_dir = (PROJECT_ROOT / "data").resolve()
                    if not str(file_resolved).startswith(str(data_dir)):
                        print("ERROR: File must be within project data directory: %s" % data_dir)
                        return
            store_anchors(conn, anchors_file=anchors_file)
        elif "--active" in sys.argv:
            list_anchors(conn, active_only=True)
        elif "--list" in sys.argv:
            list_anchors(conn)
        else:
            print(__doc__)


if __name__ == "__main__":
    main()
