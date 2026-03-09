"""
Master Overnight Runner — runs all studies sequentially.
1. Overnight GPU phases 4-9 (already running separately)
2. Collaboration BCB (4 conditions × 20 tasks)
3. Voice/Framing Ablation (5 conditions on Franklin)
4. Pipeline Ablation Study (14 conditions on Franklin — the big one)
"""
import sys
import os
import subprocess
import time
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPTS_DIR, "..", "docs", "eval", "master_overnight_log.txt")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run_script(name, script_path, timeout_hours=3):
    log(f"STARTING: {name}")
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, "-u", script_path],
            capture_output=True, text=True,
            timeout=timeout_hours * 3600,
            encoding="utf-8", errors="replace",
            cwd=os.path.join(SCRIPTS_DIR, ".."),
        )
        elapsed = (time.time() - start) / 60
        if result.returncode == 0:
            log(f"COMPLETE: {name} ({elapsed:.1f} min)")
        else:
            log(f"FAILED: {name} (code {result.returncode}, {elapsed:.1f} min)")
            log(f"  STDERR: {result.stderr[-300:]}")
        # Print last 10 lines of stdout
        lines = result.stdout.strip().split("\n")
        for line in lines[-10:]:
            log(f"  {line}")
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT: {name} (>{timeout_hours}h)")
    except Exception as e:
        log(f"ERROR: {name}: {e}")

def main():
    log("=" * 70)
    log("MASTER OVERNIGHT RUNNER")
    log("=" * 70)

    studies = [
        ("Collaboration BCB", os.path.join(SCRIPTS_DIR, "collaboration_bcb.py")),
        ("Voice/Framing Ablation", os.path.join(SCRIPTS_DIR, "voice_ablation.py")),
        ("Predicate Quality Ablation", os.path.join(SCRIPTS_DIR, "predicate_ablation.py")),
    ]

    for name, path in studies:
        if not os.path.exists(path):
            log(f"SKIP: {name} — script not found at {path}")
            continue
        run_script(name, path)
        log("")

    log("=" * 70)
    log("ALL STUDIES COMPLETE")
    log("=" * 70)

if __name__ == "__main__":
    main()
