#!/usr/bin/env python3
"""
S98: Submit batch extraction for all high priority subjects.

For each subject:
1. Set MEMORY_SYSTEM_ROOT to subject's memory dir
2. Submit batch extraction (document mode, skip already-extracted)
3. Move to next subject

After all submitted, poll status and process results.

Usage:
    python runners/batch_all_subjects.py submit          # Submit all
    python runners/batch_all_subjects.py submit --only zvi  # Submit one
    python runners/batch_all_subjects.py status           # Check all
    python runners/batch_all_subjects.py process          # Process completed results
"""

import argparse
import json
import os
import sys
import sqlite3
import time
from pathlib import Path
from datetime import datetime
from importlib import reload

BASE = Path("C:/Users/Aarik/Anthropic")
MS = BASE / "memory_system"
SUBJECTS_DIR = BASE / "subjects"
DB_PATH = MS / "data" / "database" / "memory.db"
BATCH_TRACKER = MS / "data" / "database" / "batch_tracker.json"

sys.path.insert(0, str(MS / "src"))

SUBJECTS = [
    "derek_sivers", "andy_matuschak", "gwern_branwen", "kyle_harrison",
    "tomasz_tunguz", "zvi_mowshowitz", "eric_schwitzgebel", "jack_clark",
    "morgan_housel", "patrick_mckenzie", "seth_godin", "visakan_veerasamy",
]


def get_subject_info(subject_id):
    """Get subject info from registry."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def ensure_db(subject_id):
    """Ensure subject has initialized database with imported conversations."""
    info = get_subject_info(subject_id)
    if not info:
        print(f"  {subject_id}: NOT IN REGISTRY — skip")
        return None

    env_dir = info.get("environment_dir", f"{subject_id}_memory")
    mem_dir = SUBJECTS_DIR / env_dir
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "data" / "database").mkdir(parents=True, exist_ok=True)
    (mem_dir / "data" / "vectors").mkdir(parents=True, exist_ok=True)
    (mem_dir / "data" / "identity_layers").mkdir(parents=True, exist_ok=True)

    db_path = mem_dir / "data" / "database" / "memory.db"

    # Init DB if needed
    if not db_path.exists() or db_path.stat().st_size == 0:
        if db_path.exists():
            db_path.unlink()
        os.environ["MEMORY_SYSTEM_ROOT"] = str(mem_dir)
        import baselayer.config as cfg
        reload(cfg)
        from baselayer.init_database import init_database
        init_database(db_path)
        print(f"  Initialized DB: {db_path}")

    # Import if no conversations
    conn = sqlite3.connect(str(db_path))
    conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    conn.close()

    if conv_count == 0:
        source_name = info.get("source_dir", f"{subject_id}_source")
        source_dir = MS / "data" / source_name
        if not source_dir.exists():
            print(f"  {subject_id}: No source dir at {source_dir}")
            return None

        os.environ["MEMORY_SYSTEM_ROOT"] = str(mem_dir)
        reload(cfg)

        from baselayer.import_conversations import import_text_files
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        existing_ids = set()
        import_text_files(conn, str(source_dir), existing_ids)
        conn.commit()
        new_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        conn.close()
        print(f"  Imported {new_count} conversations from {source_dir.name}")
    else:
        print(f"  {conv_count} conversations already imported")

    return mem_dir


def submit_batch(subject_id, mem_dir):
    """Submit batch extraction for a subject."""
    os.environ["MEMORY_SYSTEM_ROOT"] = str(mem_dir)
    import baselayer.config as cfg
    reload(cfg)

    from baselayer.batch_extract import run_submit
    run_submit(document_mode=True, skip_extracted=True)


def check_status(subject_id, mem_dir):
    """Check batch status for a subject."""
    os.environ["MEMORY_SYSTEM_ROOT"] = str(mem_dir)
    import baselayer.config as cfg
    reload(cfg)

    from baselayer.batch_extract import run_status
    run_status()


def process_results(subject_id, mem_dir):
    """Process completed batch results for a subject."""
    os.environ["MEMORY_SYSTEM_ROOT"] = str(mem_dir)
    import baselayer.config as cfg
    reload(cfg)

    from baselayer.batch_extract import run_process
    run_process(resume=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["submit", "status", "process"])
    parser.add_argument("--only", type=str, help="Single subject")
    args = parser.parse_args()

    subjects = SUBJECTS
    if args.only:
        subjects = [s for s in subjects if args.only.lower() in s.lower()]

    print(f"\n{'='*60}")
    print(f"  Batch {args.action.upper()} — {len(subjects)} subjects")
    print(f"{'='*60}\n")

    for i, sid in enumerate(subjects):
        print(f"[{i+1}/{len(subjects)}] {sid}")

        info = get_subject_info(sid)
        if not info:
            print(f"  SKIP — not in registry")
            continue

        env_dir = info.get("environment_dir", f"{sid}_memory")
        mem_dir = SUBJECTS_DIR / env_dir

        if args.action == "submit":
            mem_dir = ensure_db(sid)
            if mem_dir:
                try:
                    submit_batch(sid, mem_dir)
                    print(f"  SUBMITTED")
                except Exception as e:
                    print(f"  ERROR: {e}")

        elif args.action == "status":
            if mem_dir.exists():
                try:
                    check_status(sid, mem_dir)
                except Exception as e:
                    print(f"  ERROR: {e}")

        elif args.action == "process":
            if mem_dir.exists():
                try:
                    process_results(sid, mem_dir)
                    print(f"  PROCESSED")
                except Exception as e:
                    print(f"  ERROR: {e}")

        print()


if __name__ == "__main__":
    main()
