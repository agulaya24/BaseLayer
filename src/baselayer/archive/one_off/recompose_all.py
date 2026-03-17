#!/usr/bin/env python3
"""Recompose briefs for all subjects using updated V4 compose prompt.

Reads existing layers, backs up current brief, runs compose with the
updated prompt (false positive guards + woven tension directives).

Usage:
    python scripts/recompose_all.py
"""

import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

_HOME = Path.home() / "Anthropic"
SUBJECTS = [
    ("franklin", str(_HOME / "subjects" / "franklin_memory")),
    ("douglass", str(_HOME / "subjects" / "douglass_memory")),
    ("wollstonecraft", str(_HOME / "subjects" / "wollstonecraft_memory")),
    ("roosevelt", str(_HOME / "subjects" / "roosevelt_memory")),
    ("patent", str(_HOME / "subjects" / "patent_memory")),
    ("marks", str(_HOME / "marks_memory")),
    ("buffett", str(_HOME / "buffett_memory")),
    ("user_a", str(_HOME / "memory_system_v4")),
]


def recompose_subject(name, root_dir):
    """Recompose a single subject's brief."""
    root = Path(root_dir)
    os.environ["MEMORY_SYSTEM_ROOT"] = str(root)

    # Force reimport of config with new MEMORY_SYSTEM_ROOT
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("config", "api_client", "agent_pipeline"):
            del sys.modules[mod_name]

    from config import ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE, IDENTITY_LAYERS_DIR
    import agent_pipeline

    print(f"\n{'='*60}")
    print(f"  Subject: {name}")
    print(f"  Root: {root}")
    print(f"{'='*60}")

    # Check layers exist
    layer_files = {
        "anchors": ANCHORS_LAYER_FILE,
        "core": CORE_LAYER_FILE,
        "predictions": PREDICTIONS_LAYER_FILE,
    }

    present = {k: v for k, v in layer_files.items() if v.exists()}
    if not present:
        print(f"  SKIP — no layers found")
        return None

    print(f"  Layers: {list(present.keys())}")

    # Backup current brief
    brief_file = IDENTITY_LAYERS_DIR / "brief_v4.md"
    if brief_file.exists():
        backup = IDENTITY_LAYERS_DIR / "brief_v4_pre_v4compose_backup.md"
        if not backup.exists():  # Don't overwrite existing backup
            shutil.copy2(brief_file, backup)
            print(f"  Backed up: {backup.name}")

    # Run compose
    try:
        brief_text = agent_pipeline.compose_unified_brief()
        if brief_text:
            print(f"  SUCCESS: {len(brief_text)} chars")
            return len(brief_text)
        else:
            print(f"  FAILED: compose returned None")
            return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def main():
    print("Recompose All Subjects — V4 Prompt (FP Guards + Tension Directives)")
    print("=" * 60)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Subjects: {len(SUBJECTS)}")

    results = []
    total_subjects = 0
    success_count = 0

    for name, root in SUBJECTS:
        total_subjects += 1
        chars = recompose_subject(name, root)
        results.append((name, chars))
        if chars:
            success_count += 1

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for name, chars in results:
        status = f"{chars} chars" if chars else "SKIPPED/FAILED"
        print(f"  {name:20s} {status}")
    print(f"\n  {success_count}/{total_subjects} subjects recomposed")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
