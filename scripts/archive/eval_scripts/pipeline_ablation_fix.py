"""
Re-run the 4 failed conditions from the pipeline ablation (C1, C2, C3, C5).
The briefs were generated but not saved/scored due to Windows file locking.
"""
import sys
import os
import json
import functools
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print = functools.partial(print, flush=True)

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from pipeline_ablation import (
    log, OUTPUT_DIR, FRANKLIN_BRIEF,
    run_c1_no_review, run_c2_no_contradictions,
    run_c3_no_scoring, run_c5_no_tiering,
    m1_collective_score, m3_pattern_coverage, m4_brief_diagnostics,
    m2_pairwise_comparison, read_brief_file, TOTAL_COST,
)
from datetime import datetime

MISSING = [
    ("C1", "No Collective review", run_c1_no_review),
    ("C2", "No contradictions/consolidation", run_c2_no_contradictions),
    ("C3", "No scoring", run_c3_no_scoring),
    ("C5", "No tiering (all facts = identity)", run_c5_no_tiering),
]

log("=" * 50)
log("RE-RUNNING MISSING CONDITIONS: C1, C2, C3, C5")
log("=" * 50)

briefs = {}
results = {}

# Phase 1: Generate briefs
for cid, desc, runner in MISSING:
    log(f"\n{'='*40}")
    try:
        brief = runner()
        if brief:
            briefs[cid] = brief
            path = os.path.join(OUTPUT_DIR, f"{cid}_brief.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {cid}: {desc}\n# Generated: {datetime.now().isoformat()}\n\n{brief}")
            log(f"  Saved: {path}")
        else:
            log(f"  {cid} FAILED")
    except Exception as e:
        log(f"  {cid} ERROR: {e}")
        import traceback
        traceback.print_exc()

# Phase 2: Score
for cid, desc, _ in MISSING:
    brief = briefs.get(cid)
    if not brief:
        results[cid] = {"condition": cid, "description": desc, "status": "FAILED"}
        continue
    log(f"\nScoring {cid}")
    m3 = m3_pattern_coverage(brief)
    m4 = m4_brief_diagnostics(brief)
    m1 = m1_collective_score(brief, cid)
    log(f"  M3: {m3['total']} patterns, M4: {m4['char_count']} chars")
    results[cid] = {
        "condition": cid, "description": desc, "status": "OK",
        "m1_collective": m1, "m3_patterns": m3, "m4_diagnostics": m4,
    }

# Phase 3: Pairwise vs C0
baseline = read_brief_file(FRANKLIN_BRIEF)
for cid, desc, _ in MISSING:
    brief = briefs.get(cid)
    if not brief:
        continue
    log(f"\nPairwise: C0 vs {cid}")
    m2 = m2_pairwise_comparison(baseline, brief, cid)
    results[cid]["m2_pairwise"] = m2

# Save
fix_path = os.path.join(OUTPUT_DIR, "ablation_results_fix.json")
with open(fix_path, "w", encoding="utf-8") as f:
    json.dump({"conditions": results, "timestamp": datetime.now().isoformat()}, f, indent=2)
log(f"\nResults saved: {fix_path}")

# Print summary
log("\nMISSING CONDITION RESULTS:")
for cid in ["C1", "C2", "C3", "C5"]:
    r = results.get(cid, {})
    score = r.get("m1_collective", {}).get("combined", "?")
    chars = r.get("m4_diagnostics", {}).get("char_count", "?")
    pw = r.get("m2_pairwise", {}).get("decoded_winner", "?")
    log(f"  {cid}: {score}/100, {chars} chars, pairwise: {pw}")

log("FIX COMPLETE")
