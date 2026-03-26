#!/usr/bin/env python3
"""
VC Pipeline Runner — runs import + extract + author + compose for 6 VC subjects.
Run: python run_vc_pipelines.py

Runs sequentially to avoid API rate limits. Logs progress to vc_pipeline_log.txt.
Skips Jerry Chen (7 files) and Martin Casado (3 files) — too thin for identity models.
"""
import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

BASE = Path("C:/Users/Aarik/Anthropic")
MEMORY_SYSTEM = BASE / "memory_system"

# (env_name, display_name, source_dir, file_count)
SUBJECTS = [
    ("brad_feld_memory", "Brad Feld", "brad_feld_source", 74),
    ("dharmesh_shah_memory", "Dharmesh Shah", "dharmesh_shah_source", 79),
    ("tomasz_tunguz_memory", "Tomasz Tunguz", "tomasz_tunguz_source", 75),
    ("elad_gil_memory", "Elad Gil", "elad_gil_source", 38),
    ("joseph_jacks_memory", "Joseph Jacks", "joseph_jacks_source", 27),
    ("nat_friedman_memory", "Nat Friedman", "nat_friedman_source", 15),
]

LOG_FILE = MEMORY_SYSTEM / "vc_pipeline_log.txt"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_cmd(cmd, env_vars=None):
    """Run a command and return (success, output)."""
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    try:
        result = subprocess.run(
            cmd, shell=False, capture_output=True, text=True,
            timeout=7200, env=env, cwd=str(MEMORY_SYSTEM)
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT after 2 hours"
    except Exception as e:
        return False, str(e)


def run_pipeline(env_name, display_name, source_dir, file_count):
    """Run full pipeline for one subject."""
    log(f"{'='*60}")
    log(f"STARTING: {display_name} ({env_name}) — {file_count} source files")
    log(f"{'='*60}")

    env_path = BASE / "subjects" / env_name
    env_vars = {"MEMORY_SYSTEM_ROOT": str(env_path)}
    source_path = MEMORY_SYSTEM / "data" / source_dir

    start = time.time()

    # Full pipeline: import + extract + author + compose
    log(f"  Running full pipeline: import + extract + author + compose...")
    ok, out = run_cmd(
        [sys.executable, "-m", "baselayer.cli", "run", str(source_path),
         "--document-mode", "--subject", display_name, "-y"],
        env_vars
    )
    if not ok:
        log(f"  PIPELINE FAILED: {out[-500:]}")
        return False

    # Count facts
    try:
        import sqlite3
        db = env_path / "data" / "database" / "memory.db"
        conn = sqlite3.connect(str(db))
        facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        conn.close()
        log(f"  Facts extracted: {facts}")
    except Exception:
        log(f"  (could not count facts)")

    elapsed = time.time() - start
    log(f"  COMPLETE: {display_name} in {elapsed/60:.1f} minutes")
    return True


def main():
    log(f"\n{'='*60}")
    log(f"VC PIPELINE RUN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"6 subjects, sequential execution")
    log(f"{'='*60}\n")

    results = {}
    for env_name, display_name, source_dir, file_count in SUBJECTS:
        ok = run_pipeline(env_name, display_name, source_dir, file_count)
        results[display_name] = "OK" if ok else "FAILED"
        log("")

    log(f"\n{'='*60}")
    log(f"SUMMARY")
    log(f"{'='*60}")
    for name, status in results.items():
        log(f"  {name}: {status}")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    main()
