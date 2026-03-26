#!/usr/bin/env python3
"""Run V2 pipelines for remaining Wave 1 subjects (re-extract with larger corpora)."""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path("C:/Users/Aarik/Anthropic")
MS = BASE / "memory_system"

# Wave 1 subjects needing V2 re-extraction (largest corpus first)
V2_SUBJECTS = [
    ("Cedric Chin",         "cedric_chin_memory",       "cedric_chin_source"),
    ("Matt Yglesias",       "matt_yglesias_memory",     "matt_yglesias_source"),
    ("Simon Willison",      "simon_willison_memory",    "simon_willison_source"),
    ("Cory Doctorow",       "cory_doctorow_memory",     "cory_doctorow_source"),
    ("Fred Wilson",         "fred_wilson_memory",       "fred_wilson_source"),
    ("Scott Alexander",     "scott_alexander_memory",   "scott_alexander_source"),
    ("Ethan Mollick",       "ethan_mollick_memory",     "ethan_mollick_source"),
    ("Henrik Karlsson",     "henrik_karlsson_memory",   "henrik_source"),
    ("Dan Shipper",         "dan_shipper_memory",       "dan_shipper_source"),
    ("swyx",                "swyx_memory",              "swyx_source"),
    ("Anne-Laure Le Cunff", "anne_lecunff_memory",      "anne_source"),
]

def run_pipeline(name, env_name, source_name):
    env_path = BASE / "subjects" / env_name
    source_path = MS / "data" / source_name

    if not source_path.exists():
        print(f"  SKIP: {source_path} not found")
        return False

    print(f"\n{'='*60}")
    print(f"  {name} — V2 Pipeline")
    print(f"  Source: {source_path} ({len(list(source_path.iterdir()))} files)")
    print(f"  Env: {env_path}")
    print(f"{'='*60}")

    import os
    env = os.environ.copy()
    env["MEMORY_SYSTEM_ROOT"] = str(env_path)
    env["PYTHONIOENCODING"] = "utf-8"

    start = time.time()
    log_file = Path(f"/tmp/v2_{env_name}.log")
    with open(log_file, "w", encoding="utf-8") as logf:
        proc = subprocess.run(
            [sys.executable, str(MS / "src" / "baselayer" / "cli.py"),
             "run", str(source_path),
             "--document-mode", "--subject", name, "--yes"],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            timeout=1800,  # 30 min max per subject
        )
    elapsed = time.time() - start

    print(f"  Done in {elapsed:.0f}s (exit code {proc.returncode})")
    if proc.returncode != 0:
        tail = log_file.read_text(encoding="utf-8", errors="replace")[-500:]
        print(f"  LOG TAIL: {tail}")
    else:
        # Check fact count
        import sqlite3
        db = env_path / "data" / "database" / "memory.db"
        if db.exists():
            conn = sqlite3.connect(str(db))
            facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
            conn.close()
            print(f"  Facts: {facts}")

    return result.returncode == 0

if __name__ == "__main__":
    print(f"V2 Pipeline Runner — {len(V2_SUBJECTS)} subjects")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}
    for name, env_name, source_name in V2_SUBJECTS:
        try:
            ok = run_pipeline(name, env_name, source_name)
            results[name] = "OK" if ok else "FAIL"
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = f"ERROR: {e}"

    print(f"\n{'='*60}")
    print("RESULTS:")
    for name, status in results.items():
        print(f"  {name}: {status}")
    print(f"Completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
