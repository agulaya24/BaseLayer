#!/usr/bin/env python3
"""Generate tension/contradiction data for all outreach subjects and store in seed JSONs."""

import json
import os
import sys
import importlib
import sqlite3
from pathlib import Path

# Force sentence_transformers before baselayer caches
from sentence_transformers import SentenceTransformer

SUBJECTS = [
    "dan_shipper", "anne_lecunff", "henrik_karlsson", "david_perell",
    "fred_wilson", "simon_willison", "maggie_appleton", "cedric_chin",
    "casey_newton", "scott_alexander", "matt_yglesias", "swyx",
    "ethan_mollick", "cory_doctorow", "kevin_kelly",
    # Wave 2 + new subjects
    "paul_graham", "dan_luu", "derek_thompson", "linus_lee",
    "byrne_hobart", "noah_smith", "venkatesh_rao", "nathan_lambert",
    "packy_mccormick", "tina_he", "bernie_sanders", "ivan_bercovich",
    "jonathan_fulton", "eli_tyre",
]

# Subject directory name overrides (when dir name doesn't follow {name}_memory pattern)
SUBJECT_DIR_OVERRIDES = {
    "paul_graham": "paul_graham",
}

ANTHROPIC_ROOT = "C:/Users/Aarik/Anthropic"


def scan_subject(subject_name):
    """Run contradiction scan on a subject."""
    dir_name = SUBJECT_DIR_OVERRIDES.get(subject_name, f"{subject_name}_memory")
    subject_dir = os.path.join(ANTHROPIC_ROOT, "subjects", dir_name)
    os.environ["MEMORY_SYSTEM_ROOT"] = subject_dir

    # Reload config for new root
    import baselayer.config as cfg
    importlib.reload(cfg)

    # Force embedding model
    from baselayer.config import EMBEDDING_MODEL
    import baselayer.api_client as ac
    if ac._embedding_model is None:
        ac._embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    # Make 'config' importable as alias for 'baselayer.config' (archived scripts use bare 'config')
    import baselayer.config
    sys.modules['config'] = baselayer.config

    # Import contradiction detection from archive/utilities (has Haiku classification)
    dead_path = os.path.join(os.path.dirname(__file__), "src", "baselayer", "archive", "utilities")
    if dead_path not in sys.path:
        sys.path.insert(0, dead_path)

    # Also need api_client alias
    import baselayer.api_client
    sys.modules['api_client'] = baselayer.api_client

    try:
        import detect_contradictions as dc
        importlib.reload(dc)
    except ImportError as e:
        print(f"  Cannot import detect_contradictions: {e}")
        import traceback
        traceback.print_exc()
        return []

    from baselayer.config import get_db
    import contextlib

    with contextlib.closing(get_db()) as conn:
        facts = dc.load_facts(conn)
        print(f"  {len(facts)} active facts")

        if len(facts) < 2:
            return []

        embeddings = dc.embed_facts(facts)
        candidates = dc.find_candidate_pairs(facts, embeddings, threshold=0.45)
        print(f"  {len(candidates)} candidate pairs")

        if not candidates:
            return []

        max_pairs = 30
        classify_count = min(len(candidates), max_pairs)
        print(f"  Classifying top {classify_count} via Haiku...")

        findings = []
        for i, pair in enumerate(candidates[:classify_count]):
            fa, fb = pair["fact_a"], pair["fact_b"]
            pred_a = fa.get("predicate", "unknown")
            pred_b = fb.get("predicate", "unknown")

            result = dc.classify_pair_haiku(fa["fact_text"], fb["fact_text"], pred_a, pred_b)
            verdict = result.get("verdict", "CONSISTENT")

            if verdict in ("CONTRADICTION", "TENSION"):
                findings.append({
                    "factA": fa.get("fact_text", fa.get("id", "")),
                    "factB": fb.get("fact_text", fb.get("id", "")),
                    "sourceA": fa.get("source_title", "") or "",
                    "sourceB": fb.get("source_title", "") or "",
                    "verdict": verdict,
                    "similarity": round(pair["similarity"], 3),
                    "synthesis": result.get("reasoning", ""),
                    "predicateA": pred_a,
                    "predicateB": pred_b,
                    "confidence": result.get("confidence", 0.0),
                    "selectionReason": pair.get("selection_reason", "high similarity"),
                })

        c = sum(1 for f in findings if f["verdict"] == "CONTRADICTION")
        t = sum(1 for f in findings if f["verdict"] == "TENSION")
        print(f"  Results: {c} contradictions, {t} tensions")
        return findings


if __name__ == "__main__":
    print("=" * 60)
    print("TENSION DETECTION FOR ALL OUTREACH SUBJECTS")
    print("=" * 60)

    # Load existing tensions to avoid re-running completed subjects
    output_path = os.path.join(os.path.dirname(__file__), "tensions_all.json")
    all_tensions = {}
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            all_tensions = json.load(f)
        print(f"Loaded existing data for {len(all_tensions)} subjects")

    # Allow filtering to specific subjects via --only flag
    only_subjects = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_subjects = [s.strip() for s in sys.argv[idx + 1].split(",")]
            print(f"Running only: {only_subjects}")

    # --force flag to re-run even if data exists
    force = "--force" in sys.argv

    for subject in SUBJECTS:
        if only_subjects and subject not in only_subjects:
            continue

        if subject in all_tensions and all_tensions[subject] and not force:
            print(f"\n--- {subject} --- SKIP (already has {len(all_tensions[subject])} tensions)")
            continue

        print(f"\n--- {subject} ---")
        dir_name = SUBJECT_DIR_OVERRIDES.get(subject, f"{subject}_memory")
        subject_dir = os.path.join(ANTHROPIC_ROOT, "subjects", dir_name)
        if not os.path.exists(subject_dir):
            print(f"  SKIP: directory not found")
            continue

        try:
            findings = scan_subject(subject)
            all_tensions[subject] = findings
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_tensions[subject] = []

    # Save results
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_tensions, f, indent=2, ensure_ascii=False)

    total = sum(len(v) for v in all_tensions.values())
    print(f"\n{'=' * 60}")
    print(f"Total: {total} tensions/contradictions across {len(all_tensions)} subjects")
    print(f"Saved to: {output_path}")
