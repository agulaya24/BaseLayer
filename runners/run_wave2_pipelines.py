#!/usr/bin/env python3
"""
Wave 2 Pipeline Runner — runs import + extract + author + compose for 10 subjects.
Run: python run_wave2_pipelines.py

Runs sequentially to avoid API rate limits. Logs progress to wave2_pipeline_log.txt.
"""
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

BASE = Path("C:/Users/Aarik/Anthropic")
MEMORY_SYSTEM = BASE / "memory_system"

# (env_name, display_name, source_dir_relative_to_memory_system/data, already_imported)
SUBJECTS = [
    ("paul_graham", "Paul Graham", None, True),  # Already imported, just author+compose
    ("dan_luu_memory", "Dan Luu", "danluu_source", False),
    ("derek_thompson_memory", "Derek Thompson", "derek_thompson_source", False),
    ("linus_lee_memory", "Linus Lee", "linus_lee_source", False),
    ("byrne_hobart_memory", "Byrne Hobart", "byrne_hobart_source", False),
    ("noah_smith_memory", "Noah Smith", "noah_smith_source", False),
    ("venkatesh_rao_memory", "Venkatesh Rao", "venkatesh_rao_source", False),
    ("nathan_lambert_memory", "Nathan Lambert", "nathan_lambert_source", False),
    ("packy_mccormick_memory", "Packy McCormick", "packy_source", False),
    ("tina_he_memory", "Tina He", "tina_he_source", False),
]

LOG_FILE = MEMORY_SYSTEM / "wave2_pipeline_log.txt"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_cmd(cmd, env_vars=None):
    """Run a command and return (success, output).
    cmd can be a string (shell=True) or a list (shell=False, preferred).
    """
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    use_shell = isinstance(cmd, str)
    try:
        result = subprocess.run(
            cmd, shell=use_shell, capture_output=True, text=True,
            timeout=7200, env=env, cwd=str(MEMORY_SYSTEM)
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT after 2 hours"
    except Exception as e:
        return False, str(e)


def run_pipeline(env_name, display_name, source_dir, already_imported):
    """Run full pipeline for one subject."""
    log(f"{'='*60}")
    log(f"STARTING: {display_name} ({env_name})")
    log(f"{'='*60}")

    env_path = BASE / "subjects" / env_name
    env_vars = {"MEMORY_SYSTEM_ROOT": str(env_path)}
    source_path = MEMORY_SYSTEM / "data" / source_dir if source_dir else None

    start = time.time()

    # Use `baselayer run` for full pipeline (import+extract+author+compose)
    if not already_imported and source_path:
        log(f"  Running full pipeline: import + extract + author + compose...")
        ok, out = run_cmd(
            [sys.executable, "-m", "baselayer.cli", "run", str(source_path),
             "--document-mode", "--subject", display_name, "-y"],
            env_vars
        )
        if not ok:
            log(f"  PIPELINE FAILED: {out[-500:]}")
            return False
    else:
        # Already imported, just extract + author + compose
        log(f"  Step 1: Skip import (already done)")

        log(f"  Step 2: Extracting facts...")
        ok, out = run_cmd(
            [sys.executable, "-m", "baselayer.cli", "extract", "--document-mode"],
            env_vars
        )
        if not ok:
            log(f"  EXTRACT FAILED: {out[-500:]}")
            return False

        # Count facts
        try:
            import sqlite3
            db = env_path / "data" / "database" / "memory.db"
            conn = sqlite3.connect(str(db))
            facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
            conn.close()
            log(f"  Extraction done: {facts} facts")
        except Exception:
            log(f"  Extraction done (could not count facts)")

        log(f"  Step 3: Authoring layers...")
        ok, out = run_cmd(
            [sys.executable, "-m", "baselayer.cli", "author", "--layer", "all"],
            env_vars
        )
        if not ok:
            log(f"  AUTHOR FAILED: {out[-500:]}")
            return False
        log(f"  Authoring done.")

        log(f"  Step 4: Composing brief...")
        ok, out = run_cmd(
            [sys.executable, "-m", "baselayer.cli", "compose"],
            env_vars
        )
        if not ok:
            log(f"  COMPOSE FAILED: {out[-500:]}")
            return False

    elapsed = time.time() - start
    log(f"  COMPLETE: {display_name} in {elapsed/60:.1f} minutes")
    return True


def main():
    log(f"\n{'='*60}")
    log(f"WAVE 2 PIPELINE RUN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"10 subjects, sequential execution")
    log(f"{'='*60}\n")

    results = {}
    for env_name, display_name, source_dir, already_imported in SUBJECTS:
        try:
            ok = run_pipeline(env_name, display_name, source_dir, already_imported)
            results[display_name] = "OK" if ok else "FAILED"
        except Exception as e:
            log(f"  EXCEPTION: {e}")
            results[display_name] = f"ERROR: {e}"

    log(f"\n{'='*60}")
    log(f"SUMMARY")
    log(f"{'='*60}")
    for name, status in results.items():
        log(f"  {name}: {status}")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    main()
