#!/usr/bin/env python3
"""
Urgent Pipeline Runner — Ivan, Jonathan, Eli. End of day target.
Run: python run_urgent_pipelines.py
"""
import subprocess, sys, os, time
from datetime import datetime
from pathlib import Path

BASE = Path("C:/Users/Aarik/Anthropic")
MEMORY_SYSTEM = BASE / "memory_system"
LOG = MEMORY_SYSTEM / "urgent_pipeline_log.txt"

SUBJECTS = [
    ("ivan_bercovich_memory", "Ivan Bercovich", "ivan_bercovich_source"),
    ("jonathan_fulton_memory", "Jonathan Fulton", "jonathan_fulton_source"),
    ("eli_tyre_memory", "Eli Tyre", "eli_tyre_source"),
]

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, env_vars):
    env = os.environ.copy()
    env.update(env_vars)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=7200, env=env, cwd=str(MEMORY_SYSTEM))
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)

def main():
    log(f"{'='*50}")
    log(f"URGENT PIPELINES — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"{'='*50}\n")

    results = {}
    for env_name, display, source_dir in SUBJECTS:
        env_path = BASE / "subjects" / env_name
        source = MEMORY_SYSTEM / "data" / source_dir
        env_vars = {"MEMORY_SYSTEM_ROOT": str(env_path)}

        log(f"STARTING: {display}")
        start = time.time()

        ok, out = run(
            f'python -m baselayer.cli run "{source}" --document-mode --subject "{display}" -y',
            env_vars
        )

        elapsed = (time.time() - start) / 60
        if ok:
            # Count facts
            try:
                import sqlite3
                conn = sqlite3.connect(str(env_path / "data/database/memory.db"))
                facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
                conn.close()
                log(f"  COMPLETE: {display} — {facts} facts in {elapsed:.1f}m")
                results[display] = f"OK ({facts} facts)"
            except:
                log(f"  COMPLETE: {display} in {elapsed:.1f}m")
                results[display] = "OK"
        else:
            log(f"  FAILED: {display} — {out[-300:]}")
            results[display] = "FAILED"

    log(f"\n{'='*50}")
    log("SUMMARY")
    for name, status in results.items():
        log(f"  {name}: {status}")
    log(f"{'='*50}")

if __name__ == "__main__":
    main()
