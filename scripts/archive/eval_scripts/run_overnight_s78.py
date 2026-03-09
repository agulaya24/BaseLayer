"""
Master Overnight Runner — Session 78
Runs all experiment scripts sequentially with error handling.

Scripts (in order):
  1. sonnet_validation.py          — Verify Qwen findings with Sonnet (~$2-3)
  2. expanded_identity_ablation.py — Deep identity-tier + temporal experiments (~$3-5)
  3. voice_downstream_eval.py      — Voice briefs on downstream tasks via Sonnet (~$2-3)
  4. coverage_merge_adversarial.py  — Coverage gaps + counter-brief merge + adversarial (~$3-5)
  5. brief_optimization.py         — Length sweep + cross-subject (~$2-3)

Total estimated cost: ~$12-19
Total estimated time: 2-4 hours
"""

import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
LOG_DIR = os.path.join(PROJECT_ROOT, "docs", "eval")
LOG_PATH = os.path.join(LOG_DIR, "overnight_s78_log.txt")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


SCRIPTS = [
    ("sonnet_validation.py", "Sonnet Validation of Qwen Findings"),
    ("expanded_identity_ablation.py", "Expanded Identity-Tier + Temporal Ablation"),
    ("voice_downstream_eval.py", "Voice Downstream Evaluation (Sonnet)"),
    ("coverage_merge_adversarial.py", "Coverage + Merge + Adversarial"),
    ("brief_optimization.py", "Brief Length + Density Optimization"),
]


def main():
    log("=" * 70)
    log("OVERNIGHT RUNNER — SESSION 78")
    log(f"Scripts: {len(SCRIPTS)}")
    log(f"Est. cost: $12-19, Est. time: 2-4 hours")
    log("=" * 70)

    start = time.time()
    results = []

    for i, (script, name) in enumerate(SCRIPTS, 1):
        script_path = os.path.join(PROJECT_ROOT, "scripts", script)
        log(f"\n[{i}/{len(SCRIPTS)}] Starting: {name}")
        log(f"  Script: {script_path}")

        script_start = time.time()
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True, text=True, timeout=7200,  # 2 hours max per script
                cwd=PROJECT_ROOT,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            elapsed = time.time() - script_start
            status = "SUCCESS" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
            log(f"  {status} in {elapsed/60:.1f} min")

            if result.returncode != 0:
                log(f"  STDERR (last 500 chars): {result.stderr[-500:]}")

            results.append({
                "script": script, "name": name, "status": status,
                "elapsed_min": round(elapsed / 60, 1),
                "returncode": result.returncode,
            })

        except subprocess.TimeoutExpired:
            elapsed = time.time() - script_start
            log(f"  TIMEOUT after {elapsed/60:.1f} min")
            results.append({
                "script": script, "name": name, "status": "TIMEOUT",
                "elapsed_min": round(elapsed / 60, 1),
            })

        except Exception as e:
            elapsed = time.time() - script_start
            log(f"  ERROR: {e}")
            results.append({
                "script": script, "name": name, "status": f"ERROR: {e}",
                "elapsed_min": round(elapsed / 60, 1),
            })

    total = time.time() - start
    log(f"\n{'=' * 70}")
    log(f"COMPLETE — Total: {total/60:.1f} min ({total/3600:.1f} hours)")
    log(f"{'=' * 70}")

    for r in results:
        log(f"  {r['name']:<50} {r['status']:<15} {r['elapsed_min']:.1f} min")

    # Save summary
    import json
    summary_path = os.path.join(LOG_DIR, "overnight_s78_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "started": datetime.now().isoformat(),
            "total_minutes": round(total / 60, 1),
            "results": results,
        }, f, indent=2)
    log(f"\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
