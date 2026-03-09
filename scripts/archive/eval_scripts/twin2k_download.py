"""
Twin-2K-500 Dataset Downloader

Downloads participant data from HuggingFace for the Twin-2K-500 benchmark.
Saves persona_text, persona_summary, and wave4 holdout Q&A for each participant.

Usage:
    python twin2k_download.py --n 20                    # Download 20 participants
    python twin2k_download.py --n 20 --offset 0         # Start from participant 0
    python twin2k_download.py --participants 0 5 12 99   # Download specific participants

Output:
    subjects/twin2k/participant_{id}/persona_text.txt
    subjects/twin2k/participant_{id}/persona_summary.txt
    subjects/twin2k/participant_{id}/wave4_QA.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Resolve output directory
SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))


def download_dataset():
    """Load the Twin-2K-500 dataset from HuggingFace. Returns (persona_ds, wave_ds)."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' package required. Install with: pip install datasets")
        sys.exit(1)

    print("Loading Twin-2K-500 full_persona config...")
    persona_ds = load_dataset("LLM-Digital-Twin/Twin-2K-500", "full_persona")
    # The split may be "data" or "train" depending on version
    persona_split = "data" if "data" in persona_ds else "train"
    persona_data = persona_ds[persona_split]

    print("Loading Twin-2K-500 wave_split config...")
    wave_ds = load_dataset("LLM-Digital-Twin/Twin-2K-500", "wave_split")
    wave_split = "data" if "data" in wave_ds else "train"
    wave_data = wave_ds[wave_split]

    print(f"  Persona records: {len(persona_data)}")
    print(f"  Wave records: {len(wave_data)}")
    print(f"  Persona columns: {persona_data.column_names}")
    print(f"  Wave columns: {wave_data.column_names}")

    return persona_data, wave_data


def save_participant(pid, persona_row, wave_row, output_dir):
    """Save one participant's data to disk."""
    pdir = output_dir / f"participant_{pid}"
    pdir.mkdir(parents=True, exist_ok=True)

    # Save persona_text (the full ~130K char Q&A dump)
    persona_text = persona_row.get("persona_text", "")
    if persona_text:
        (pdir / "persona_text.txt").write_text(persona_text, encoding="utf-8")

    # Save persona_summary (the ~15K char stat sheet)
    persona_summary = persona_row.get("persona_summary", "")
    if persona_summary:
        (pdir / "persona_summary.txt").write_text(persona_summary, encoding="utf-8")

    # Save wave4 holdout Q&A (ground truth answers)
    # Column: wave4_Q_wave4_A — wave 4 questions with wave 4 answers (holdout)
    wave4_qa = wave_row.get("wave4_Q_wave4_A", "")
    if not wave4_qa:
        for col in ["wave4_QA", "wave_4", "wave4", "holdout_QA", "holdout"]:
            wave4_qa = wave_row.get(col, "")
            if wave4_qa:
                break

    if wave4_qa:
        if isinstance(wave4_qa, str):
            (pdir / "wave4_QA.json").write_text(wave4_qa, encoding="utf-8")
        else:
            (pdir / "wave4_QA.json").write_text(
                json.dumps(wave4_qa, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    # Save wave4 questions with wave1-3 answers (for comparison/calibration)
    wave4_w13a = wave_row.get("wave4_Q_wave1_3_A", "")
    if wave4_w13a:
        if isinstance(wave4_w13a, str):
            (pdir / "wave4_Q_w13A.json").write_text(wave4_w13a, encoding="utf-8")
        else:
            (pdir / "wave4_Q_w13A.json").write_text(
                json.dumps(wave4_w13a, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    # Save wave 1-3 persona text if available
    wave13 = wave_row.get("wave1_3_persona_text", "")
    if not wave13:
        for wave_key in ["wave1_3", "wave13"]:
            wave13 = wave_row.get(wave_key, "")
            if wave13:
                break
    if wave13:
        if isinstance(wave13, str):
            (pdir / "wave13_text.txt").write_text(wave13, encoding="utf-8")
        else:
            (pdir / "wave13_text.txt").write_text(
                json.dumps(wave13, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    return pdir


def main():
    parser = argparse.ArgumentParser(description="Download Twin-2K-500 participant data")
    parser.add_argument("--n", type=int, default=20, help="Number of participants to download")
    parser.add_argument("--offset", type=int, default=0, help="Starting participant index")
    parser.add_argument("--participants", type=int, nargs="+", help="Specific participant indices")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else SUBJECTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    persona_data, wave_data = download_dataset()

    # Determine which participants to download
    if args.participants:
        indices = args.participants
    else:
        max_idx = min(args.offset + args.n, len(persona_data))
        indices = list(range(args.offset, max_idx))

    print(f"\nDownloading {len(indices)} participants to {output_dir}")

    # Build index mapping for wave data
    # Wave data may have a participant_id or index column
    wave_columns = wave_data.column_names
    print(f"  Wave columns available: {wave_columns}")

    for i, idx in enumerate(indices):
        if idx >= len(persona_data):
            print(f"  SKIP participant {idx} (out of range, max={len(persona_data)-1})")
            continue

        persona_row = persona_data[idx]
        # Wave data should align by index
        wave_row = wave_data[idx] if idx < len(wave_data) else {}

        pdir = save_participant(idx, persona_row, wave_row, output_dir)
        files = list(pdir.iterdir())
        total_size = sum(f.stat().st_size for f in files)
        print(f"  [{i+1}/{len(indices)}] Participant {idx}: {len(files)} files, {total_size:,} bytes")

    print(f"\nDone. Data saved to {output_dir}")

    # Print summary of first participant for verification
    first_dir = output_dir / f"participant_{indices[0]}"
    if first_dir.exists():
        print(f"\nSample (participant {indices[0]}):")
        for f in sorted(first_dir.iterdir()):
            size = f.stat().st_size
            print(f"  {f.name}: {size:,} chars")


if __name__ == "__main__":
    main()
