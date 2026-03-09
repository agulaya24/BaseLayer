"""
Twin-2K-500 Pipeline Runner

Runs the Base Layer pipeline (Steps 3-12) on parsed participant data
to generate identity briefs for C2 predictions.

Each participant has facts already loaded in their SQLite DB
(from twin2k_parser.py). This script runs:
  process (embed > score > classify > tier)
  contradictions
  consolidate
  author
  compose

Usage:
    python twin2k_pipeline.py --participant 0           # One participant
    python twin2k_pipeline.py --all                     # All participants
    python twin2k_pipeline.py --participant 0 --step process  # One step only
    python twin2k_pipeline.py --all --dry-run           # Show what would run
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))

# Pipeline steps in order
STEPS = [
    ("process", []),       # embed > score > classify > tier
    ("author", ["--compose"]),
]


def run_step(participant_dir, step_name, extra_args=None):
    """Run a single pipeline step for a participant."""
    env = os.environ.copy()
    env["MEMORY_SYSTEM_ROOT"] = str(participant_dir)

    cmd = ["baselayer", step_name] + (extra_args or [])
    print(f"    Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd, env=env, capture_output=True, text=True, cwd=str(participant_dir)
    )

    if result.returncode != 0:
        print(f"    ERROR (exit {result.returncode}):")
        # Show last 10 lines of stderr
        stderr_lines = result.stderr.strip().split('\n')
        for line in stderr_lines[-10:]:
            print(f"      {line}")
        return False

    # Show key output lines
    stdout_lines = result.stdout.strip().split('\n')
    for line in stdout_lines[-5:]:
        if line.strip():
            print(f"      {line.strip()}")

    return True


def has_brief(participant_dir):
    """Check if participant already has a brief."""
    for brief_path in [
        participant_dir / "data" / "identity_layers" / "brief_v4.md",
        participant_dir / "brief_v4.md",
    ]:
        if brief_path.exists():
            size = brief_path.stat().st_size
            if size > 100:
                return True
    return False


def run_pipeline(participant_id, subjects_dir, steps=None, force=False):
    """Run the full pipeline for one participant."""
    pdir = subjects_dir / f"participant_{participant_id}"
    if not pdir.exists():
        print(f"  ERROR: {pdir} does not exist")
        return False

    # Check for existing brief
    if has_brief(pdir) and not force:
        print(f"  Participant {participant_id}: brief already exists, skipping (use --force to override)")
        return True

    db_path = pdir / "data" / "database" / "memory.db"
    if not db_path.exists():
        print(f"  ERROR: No database at {db_path}")
        return False

    print(f"  Running pipeline for participant {participant_id}...")

    steps_to_run = STEPS
    if steps:
        steps_to_run = [(name, args) for name, args in STEPS if name in steps]

    for step_name, extra_args in steps_to_run:
        success = run_step(pdir, step_name, extra_args)
        if not success:
            print(f"  Pipeline FAILED at step '{step_name}' for participant {participant_id}")
            return False

    # Check for brief output
    brief_file = pdir / "data" / "identity_layers" / "brief_v4.md"
    if not brief_file.exists():
        brief_file = pdir / "brief_v4.md"
    if brief_file.exists() and brief_file.stat().st_size > 100:
        print(f"  SUCCESS: brief generated ({brief_file.stat().st_size:,} bytes)")
    else:
        layers_dir = pdir / "data" / "identity_layers"
        if layers_dir.exists():
            layer_files = list(layers_dir.glob("*.md"))
            print(f"  Layers generated: {len(layer_files)} files")
        else:
            print(f"  WARNING: No brief or layers generated")

    return True


def main():
    parser = argparse.ArgumentParser(description="Run Base Layer pipeline for Twin-2K participants")
    parser.add_argument("--participant", type=int, help="Participant index")
    parser.add_argument("--all", action="store_true", help="Run all participants")
    parser.add_argument("--step", type=str, help="Run specific step only")
    parser.add_argument("--force", action="store_true", help="Re-run even if brief exists")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    parser.add_argument("--subjects-dir", type=str, default=None)
    args = parser.parse_args()

    subjects_dir = Path(args.subjects_dir) if args.subjects_dir else SUBJECTS_DIR

    if args.all:
        indices = sorted([
            int(d.name.split('_')[1])
            for d in subjects_dir.iterdir()
            if d.is_dir() and d.name.startswith('participant_')
            and (d / "data" / "database" / "memory.db").exists()
        ])
    elif args.participant is not None:
        indices = [args.participant]
    else:
        print("ERROR: Specify --participant N or --all")
        sys.exit(1)

    steps = [args.step] if args.step else None

    print(f"Twin-2K Pipeline Runner")
    print(f"  Participants: {len(indices)}")
    print(f"  Steps: {steps or 'full pipeline'}")
    print()

    if args.dry_run:
        for pid in indices:
            pdir = subjects_dir / f"participant_{pid}"
            has = has_brief(pdir)
            print(f"  Participant {pid}: {'HAS BRIEF' if has else 'needs pipeline'}")
        return

    successes = 0
    failures = 0
    for pid in indices:
        print(f"\n=== Participant {pid} ===")
        ok = run_pipeline(pid, subjects_dir, steps=steps, force=args.force)
        if ok:
            successes += 1
        else:
            failures += 1

    print(f"\nDone. {successes} succeeded, {failures} failed.")


if __name__ == "__main__":
    main()
