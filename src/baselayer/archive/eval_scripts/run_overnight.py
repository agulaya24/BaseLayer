"""
Overnight Runner — Chains all GPU-heavy scripts sequentially.
Logs everything to data/overnight_run.log with timestamps.

Launch detached: start /B python scripts/run_overnight.py
"""

import subprocess
import sys
import time
from datetime import datetime

from config import PROJECT_ROOT

LOG_FILE = PROJECT_ROOT / "data" / "overnight_run.log"


def log(msg: str):
    """Log a timestamped message to both console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_script(name: str, args: list[str]) -> bool:
    """Run a Python script and return True if it succeeded."""
    cmd = [sys.executable, "-u"] + args
    log(f"STARTING: {name}")
    log(f"  Command: {' '.join(cmd)}")
    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=False,
            stdout=open(LOG_FILE, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            timeout=36000,  # 10 hour safety cap per script
        )
        elapsed = time.time() - start
        minutes = elapsed / 60

        if result.returncode == 0:
            log(f"COMPLETED: {name} in {minutes:.1f} minutes")
            return True
        else:
            log(f"FAILED: {name} (exit code {result.returncode}) after {minutes:.1f} minutes")
            return False

    except subprocess.TimeoutExpired:
        log(f"TIMEOUT: {name} exceeded 10 hour limit")
        return False
    except Exception as e:
        log(f"ERROR: {name} — {e}")
        return False


def main():
    # Clear old log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    log("=" * 60)
    log("OVERNIGHT RUN — Memory System Pipeline")
    log(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    results = {}

    # Step 1: Batch Summarization (~2.5 hours)
    log("")
    log("STEP 1/3: Batch Summarization")
    log("-" * 40)
    results["summarize"] = run_script(
        "Batch Summarization",
        ["scripts/summarize.py"]
    )

    # Step 2: Surprise Scoring Demo (~1 minute)
    log("")
    log("STEP 2/3: Surprise Scoring Demo")
    log("-" * 40)
    results["surprise"] = run_script(
        "Surprise Scoring Demo",
        ["scripts/surprise_scoring.py", "--demo"]
    )

    # Step 3: Fact Extraction (~5+ hours)
    log("")
    log("STEP 3/3: Fact Extraction (Full)")
    log("-" * 40)
    results["extract"] = run_script(
        "Fact Extraction",
        ["scripts/extract_facts.py"]
    )

    # Final summary
    log("")
    log("=" * 60)
    log("OVERNIGHT RUN COMPLETE")
    log(f"Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        log(f"  {name}: {status}")
    log("=" * 60)


if __name__ == "__main__":
    main()
