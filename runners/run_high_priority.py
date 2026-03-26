#!/usr/bin/env python3
"""
S98: Run V1 pipelines for all 12 high priority subjects.

Creates memory directories, registers source_dir in subjects table,
then runs `baselayer pipeline` for each subject sequentially.

Usage:
    python runners/run_high_priority.py              # Run all
    python runners/run_high_priority.py --only zvi   # Run one
    python runners/run_high_priority.py --dry-run    # Preview only
"""

import argparse
import os
import sys
import sqlite3
import subprocess
import time
from pathlib import Path
from datetime import datetime

BASE = Path("C:/Users/Aarik/Anthropic")
MS = BASE / "memory_system"
SUBJECTS_DIR = BASE / "subjects"
DB_PATH = MS / "data" / "database" / "memory.db"

# Source directory name mapping (some don't follow the {id}_source pattern)
SOURCE_MAP = {
    "derek_sivers": "derek_sivers_source",
    "andy_matuschak": "andy_matuschak_source",
    "gwern_branwen": "gwern_branwen_source",
    "kyle_harrison": "kyle_harrison_source",
    "tomasz_tunguz": "tomasz_tunguz_source",
    "zvi_mowshowitz": "zvi_mowshowitz_source",
    "eric_schwitzgebel": "eric_schwitzgebel_source",
    "jack_clark": "jack_clark_source",
    "morgan_housel": "morgan_housel_source",
    "patrick_mckenzie": "patrick_mckenzie_source",
    "seth_godin": "seth_godin_source",
    "visakan_veerasamy": "visakan_veerasamy_source",
}

SUBJECTS = list(SOURCE_MAP.keys())


def setup_memory_dir(subject_id):
    """Create memory directory structure for a subject."""
    mem_dir = SUBJECTS_DIR / f"{subject_id}_memory"
    (mem_dir / "data" / "database").mkdir(parents=True, exist_ok=True)
    (mem_dir / "data" / "vectors").mkdir(parents=True, exist_ok=True)
    (mem_dir / "data" / "identity_layers").mkdir(parents=True, exist_ok=True)
    return mem_dir


def update_registry(subject_id, source_dir_name, mem_dir):
    """Update subjects table with source_dir and environment_dir."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        UPDATE subjects SET
            source_dir = ?,
            environment_dir = ?,
            status = 'importing',
            updated_at = ?
        WHERE id = ?
    """, (source_dir_name, f"{subject_id}_memory", datetime.now().isoformat(), subject_id))
    conn.commit()
    conn.close()


def run_pipeline(subject_id):
    """Run baselayer pipeline for a subject."""
    result = subprocess.run(
        [sys.executable, "-u", "-m", "baselayer.cli", "pipeline", subject_id],
        cwd=str(MS / "src"),
        capture_output=False,
        timeout=7200,  # 2 hour timeout per subject
    )
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=str, help="Run single subject matching this string")
    parser.add_argument("--dry-run", action="store_true", help="Preview without running")
    args = parser.parse_args()

    subjects = SUBJECTS
    if args.only:
        subjects = [s for s in subjects if args.only.lower() in s.lower()]
        if not subjects:
            print(f"No match for '{args.only}'")
            return

    print(f"{'='*60}")
    print(f"  High Priority Pipeline Runner — {len(subjects)} subjects")
    print(f"{'='*60}\n")

    for i, sid in enumerate(subjects):
        source_name = SOURCE_MAP[sid]
        source_dir = MS / "data" / source_name
        file_count = len(list(source_dir.glob("*"))) if source_dir.exists() else 0

        print(f"[{i+1}/{len(subjects)}] {sid} ({file_count} source files)")

        if not source_dir.exists():
            print(f"  SKIP — no source directory at {source_dir}")
            continue

        if args.dry_run:
            print(f"  DRY RUN — would create memory dir + run pipeline")
            continue

        # Setup
        mem_dir = setup_memory_dir(sid)
        update_registry(sid, source_name, mem_dir)
        print(f"  Memory dir: {mem_dir}")
        print(f"  Running pipeline...")

        start = time.time()
        try:
            rc = run_pipeline(sid)
            elapsed = time.time() - start
            if rc == 0:
                print(f"  DONE in {elapsed:.0f}s")
            else:
                print(f"  FAILED (exit code {rc}) after {elapsed:.0f}s")
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT (>2 hours)")
        except Exception as e:
            print(f"  ERROR: {e}")

        print()

    print(f"\nAll done.")


if __name__ == "__main__":
    main()
