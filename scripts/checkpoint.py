"""
Pipeline Checkpoint Reports — Quality Gates

Generates quality reports at each pipeline stage.

Usage:
    baselayer checkpoint extraction    — After extraction: sample quality, predicate dist, qualifier coverage
    baselayer checkpoint all           — Run all checkpoints (for post-pipeline review)

    Legacy stages (pre-S79 pipeline, kept for backward compatibility):
    baselayer checkpoint scoring       — After scoring (archived step): recurrence distribution
    baselayer checkpoint classification — After classify+tier (archived step): spot-check 20 facts

Checkpoint Architecture (simplified pipeline, S79):
  1. Extract -> STOP -> checkpoint extraction -> review
  2. Author + Compose -> done

  Note: scoring, classification, and tiering stages were removed in S79 (pipeline simplification).
  The simplified pipeline routes facts by predicate type, not by tier or classification label.
"""

import contextlib
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    DATABASE_FILE, get_db, CONSTRAINED_PREDICATES,
    VALID_FACT_TYPES, VALID_COMMITMENT_DEPTHS,
)


def checkpoint_extraction(conn, sample_size=50):
    """Checkpoint 1: Post-extraction quality report."""
    print("=" * 70)
    print("  CHECKPOINT 1: Extraction Quality Report")
    print("=" * 70)

    total = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchone()[0]
    print(f"\nTotal active facts: {total}")

    if total == 0:
        print("  No facts to review. Extraction may not have run yet.")
        return False

    # --- Structured field integrity ---
    structured = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND predicate IS NOT NULL"
    ).fetchone()[0]
    unstructured = total - structured
    print(f"\nStructured field integrity:")
    print(f"  With predicate:    {structured} ({100*structured/total:.1f}%)")
    print(f"  Without predicate: {unstructured} ({100*unstructured/total:.1f}%)")

    # --- Predicate distribution ---
    print(f"\nPredicate distribution (top 20):")
    pred_dist = conn.execute("""
        SELECT predicate, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL AND predicate IS NOT NULL
        GROUP BY predicate ORDER BY cnt DESC
        LIMIT 20
    """).fetchall()
    canonical_set = set(CONSTRAINED_PREDICATES)
    for pred, cnt in pred_dist:
        flag = "" if pred in canonical_set else " [NON-CANONICAL]"
        print(f"  {pred:20s} {cnt:5d} ({100*cnt/max(structured,1):.1f}%){flag}")

    # Non-canonical predicates
    non_canonical = conn.execute("""
        SELECT predicate, COUNT(*) as cnt
        FROM memory_facts
        WHERE superseded_by IS NULL AND predicate IS NOT NULL
          AND predicate NOT IN ({})
        GROUP BY predicate ORDER BY cnt DESC
    """.format(",".join(["?"] * len(CONSTRAINED_PREDICATES))),
        list(CONSTRAINED_PREDICATES)
    ).fetchall()
    if non_canonical:
        print(f"\n  Non-canonical predicates ({len(non_canonical)} types, review for vocabulary expansion):")
        for pred, cnt in non_canonical[:10]:
            print(f"    {pred:20s} {cnt:5d}")

    # --- Qualifier coverage ---
    with_qual = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND qualifier IS NOT NULL AND qualifier != ''"
    ).fetchone()[0]
    print(f"\nQualifier coverage:")
    print(f"  With qualifier:    {with_qual} ({100*with_qual/total:.1f}%)")
    print(f"  Without qualifier: {total - with_qual} ({100*(total-with_qual)/total:.1f}%)")

    # --- Sample review ---
    sample = conn.execute("""
        SELECT id, fact_text, predicate, object_text, qualifier, category, confidence
        FROM memory_facts WHERE superseded_by IS NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (sample_size,)).fetchall()

    print(f"\nSample of {len(sample)} facts for manual review:")
    print("-" * 70)
    for i, row in enumerate(sample[:20]):  # Show 20 on screen
        fid, ft, pred, obj, qual, cat, conf = row
        qual_str = f" ({qual})" if qual else ""
        print(f"  [{i+1:2d}] [{pred or '?':15s}] {ft[:65]}{qual_str}")
    if len(sample) > 20:
        print(f"  ... ({len(sample) - 20} more in sample)")

    # --- Fact length distribution ---
    lengths = conn.execute("""
        SELECT LENGTH(fact_text) as len FROM memory_facts
        WHERE superseded_by IS NULL
    """).fetchall()
    lens = [r[0] for r in lengths]
    avg_len = sum(lens) / len(lens) if lens else 0
    short = sum(1 for l in lens if l < 20)
    long_facts = sum(1 for l in lens if l > 100)
    print(f"\nFact length distribution:")
    print(f"  Average: {avg_len:.0f} chars")
    print(f"  Short (<20 chars): {short} ({100*short/total:.1f}%)")
    print(f"  Long (>100 chars): {long_facts} ({100*long_facts/total:.1f}%)")

    # --- Subject distribution ---
    subjects = conn.execute("""
        SELECT subject, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL
        GROUP BY subject ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    print(f"\nSubject distribution:")
    for subj, cnt in subjects:
        print(f"  {subj:25s} {cnt:5d} ({100*cnt/total:.1f}%)")

    print(f"\n{'='*70}")
    print("  CHECKPOINT 1 COMPLETE — Review above before proceeding to authoring")
    print(f"{'='*70}")
    return True


def checkpoint_scoring(conn, v3_comparison=True):
    """Checkpoint 2: Post-scoring distribution report."""
    print("=" * 70)
    print("  CHECKPOINT 2: Scoring Distribution Report")
    print("=" * 70)

    total = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchone()[0]

    scored = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND significance_score IS NOT NULL"
    ).fetchone()[0]
    print(f"\nTotal active facts: {total}")
    print(f"Scored: {scored} ({100*scored/max(total,1):.1f}%)")

    if scored == 0:
        print("  No scored facts. Run scoring first.")
        return False

    # --- Recurrence distribution ---
    print(f"\nRecurrence count distribution:")
    buckets = [
        ("0 (episodic)", 0, 0),
        ("1-5 (low)", 1, 5),
        ("6-15 (moderate)", 6, 15),
        ("16-30 (recurring)", 16, 30),
        ("31-50 (strong)", 31, 50),
        ("51+ (identity-level)", 51, 999999),
    ]
    for label, lo, hi in buckets:
        cnt = conn.execute("""
            SELECT COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL AND recurrence_count BETWEEN ? AND ?
        """, (lo, hi)).fetchone()[0]
        bar = "#" * min(cnt // 5, 40)
        print(f"  {label:25s} {cnt:5d} {bar}")

    # --- Significance score distribution ---
    print(f"\nSignificance score distribution:")
    for lo, hi in [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10)]:
        cnt = conn.execute("""
            SELECT COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL AND significance_score >= ? AND significance_score < ?
        """, (lo, hi)).fetchone()[0]
        bar = "#" * min(cnt // 5, 40)
        print(f"  {lo:.0f}-{hi:.0f}: {cnt:5d} {bar}")

    # --- Top 10 highest recurrence (sanity check) ---
    print(f"\nTop 10 highest recurrence (sanity check — are these real?):")
    top = conn.execute("""
        SELECT fact_text, recurrence_count, recurrence_span_days
        FROM memory_facts
        WHERE superseded_by IS NULL
        ORDER BY recurrence_count DESC
        LIMIT 10
    """).fetchall()
    for ft, rc, span in top:
        print(f"  [{rc:4d} across {span:4d}d] {ft[:70]}")

    # --- Significance type breakdown ---
    print(f"\nSignificance type breakdown:")
    types = conn.execute("""
        SELECT significance_type, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL
        GROUP BY significance_type ORDER BY cnt DESC
    """).fetchall()
    for stype, cnt in types:
        print(f"  {stype or 'unknown':15s} {cnt:5d} ({100*cnt/total:.1f}%)")

    # --- Zero-score facts (potential extraction quality issue) ---
    zero_score = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND significance_score = 0"
    ).fetchone()[0]
    print(f"\nZero-score facts: {zero_score} ({100*zero_score/total:.1f}%)")
    if zero_score > total * 0.3:
        print("  WARNING: >30% of facts have zero significance. Check keyword extraction quality.")

    print(f"\n{'='*70}")
    print("  [LEGACY] CHECKPOINT 2 COMPLETE — Review recurrence distribution before classification")
    print(f"{'='*70}")
    return True


def checkpoint_classification(conn, spot_check_count=20):
    """Checkpoint 3: Post-classification spot-check."""
    print("=" * 70)
    print("  CHECKPOINT 3: Classification Spot-Check")
    print("=" * 70)

    total = conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchone()[0]

    # --- Fact type distribution ---
    print(f"\nFact type distribution:")
    ft_dist = conn.execute("""
        SELECT fact_type, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL
        GROUP BY fact_type ORDER BY cnt DESC
    """).fetchall()
    for ft, cnt in ft_dist:
        bar = "#" * min(cnt // 5, 40)
        print(f"  {ft or 'NULL':15s} {cnt:5d} ({100*cnt/total:.1f}%) {bar}")

    unclassified = sum(cnt for ft, cnt in ft_dist if ft in ("unclassified", None))
    if unclassified > total * 0.1:
        print(f"  WARNING: {unclassified} facts still unclassified ({100*unclassified/total:.1f}%)")

    # --- Commitment depth distribution ---
    print(f"\nCommitment depth distribution:")
    cd_dist = conn.execute("""
        SELECT commitment_depth, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL
        GROUP BY commitment_depth ORDER BY cnt DESC
    """).fetchall()
    for cd, cnt in cd_dist:
        bar = "#" * min(cnt // 5, 40)
        print(f"  {cd or 'NULL':15s} {cnt:5d} ({100*cnt/total:.1f}%) {bar}")

    # --- Knowledge tier distribution ---
    print(f"\nKnowledge tier distribution:")
    tier_dist = conn.execute("""
        SELECT knowledge_tier, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL
        GROUP BY knowledge_tier ORDER BY cnt DESC
    """).fetchall()
    for tier, cnt in tier_dist:
        print(f"  {tier or 'untiered':15s} {cnt:5d} ({100*cnt/total:.1f}%)")

    identity_count = sum(cnt for tier, cnt in tier_dist if tier == "identity")
    if identity_count < 20:
        print(f"  WARNING: Only {identity_count} identity-tier facts. Layer authoring needs more signal.")

    # --- Cross-tabulation: tier x type ---
    print(f"\nIdentity-tier facts by type:")
    cross = conn.execute("""
        SELECT fact_type, COUNT(*) as cnt
        FROM memory_facts
        WHERE superseded_by IS NULL AND knowledge_tier = 'identity'
        GROUP BY fact_type ORDER BY cnt DESC
    """).fetchall()
    cross_dict = {}
    for ft, cnt in cross:
        print(f"  {ft or 'NULL':15s} {cnt:5d}")
        cross_dict[ft] = cnt

    # --- Behavioral anomaly detection + graduated fix (S65) ---
    identity_total = sum(cross_dict.values())
    behavioral_count = cross_dict.get("behavioral", 0)
    behavioral_pct = behavioral_count / identity_total if identity_total > 0 else 0

    if identity_total >= 20 and (behavioral_count < 5 or behavioral_pct < 0.05):
        print(f"\n  *** BEHAVIORAL ANOMALY DETECTED ***")
        print(f"  Only {behavioral_count}/{identity_total} identity facts are behavioral ({behavioral_pct:.1%})")
        print(f"  PREDICTIONS layer will be starved — it only uses behavioral facts.")
        print()

        # --- Step 1: Rule-based predicate correction (free, no API) ---
        # Only predicates that UNAMBIGUOUSLY encode recurring action patterns.
        # "practices" and "avoids" mean recurring behavior by definition.
        # "prioritizes" is NOT included — Haiku correctly tags it positional
        # across all subjects (value hierarchy, not action pattern).
        behavioral_predicates = ["practices", "avoids"]
        placeholders = ",".join(["?"] * len(behavioral_predicates))
        correctable = conn.execute(f"""
            SELECT id, fact_text, fact_type, predicate
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND knowledge_tier = 'identity'
              AND fact_type != 'behavioral'
              AND predicate IN ({placeholders})
        """, behavioral_predicates).fetchall()

        if correctable:
            print(f"  STEP 1 — Rule-based predicate correction:")
            print(f"  Found {len(correctable)} facts with behavioral predicates tagged non-behavioral:")
            for fid, ft, ftype, pred in correctable:
                print(f"    [{ftype:12s}] -> behavioral  [{pred}] {ft[:65]}")

            if "--fix" in sys.argv:
                for fid, ft, ftype, pred in correctable:
                    conn.execute(
                        "UPDATE memory_facts SET fact_type = 'behavioral' WHERE id = ?",
                        (fid,)
                    )
                conn.commit()
                print(f"  APPLIED: {len(correctable)} facts corrected to behavioral")
                behavioral_count += len(correctable)
            else:
                print(f"  Run with --fix to apply corrections automatically")
            print()

        # Recheck after rule-based fix
        behavioral_pct = behavioral_count / identity_total if identity_total > 0 else 0

        if behavioral_count < 5 or behavioral_pct < 0.05:
            # --- Step 2: Show remaining suspects for Opus spot-check ---
            broader_action_predicates = [
                "excels_at", "prioritizes", "advocates_for",
                "opposes", "demands", "rejects",
            ]
            placeholders2 = ",".join(["?"] * len(broader_action_predicates))
            suspects = conn.execute(f"""
                SELECT fact_text, fact_type, predicate
                FROM memory_facts
                WHERE superseded_by IS NULL
                  AND knowledge_tier = 'identity'
                  AND fact_type != 'behavioral'
                  AND predicate IN ({placeholders2})
                ORDER BY RANDOM()
                LIMIT 20
            """, broader_action_predicates).fetchall()

            if suspects:
                print(f"  STEP 2 — Still anomalous after predicate correction.")
                print(f"  {len(suspects)} facts with action predicates remain non-behavioral:")
                print(f"  " + "-" * 66)
                for ft, ftype, pred in suspects:
                    print(f"    [{ftype:12s}] [{pred:15s}] {ft[:65]}")
                print()
                print(f"  RECOMMENDATION: Run Opus spot-check on these {len(suspects)} facts (~$0.10).")
                print(f"  If Opus flags >30% as misclassified -> re-classify subject with Sonnet.")
                print(f"  Also consider expanding PREDICTIONS retrieval to include positional")
                print(f"  facts with action predicates (author_layers.py retrieve_predictions_facts).")
        else:
            print(f"  After predicate correction: {behavioral_count} behavioral facts ({behavioral_pct:.1%})")
            print(f"  Anomaly resolved — PREDICTIONS layer should have sufficient input.")
        print()

    # --- Spot-check: random sample with classifications ---
    print(f"\nSpot-check ({spot_check_count} random classified facts):")
    print("-" * 70)
    sample = conn.execute("""
        SELECT fact_text, fact_type, commitment_depth, knowledge_tier
        FROM memory_facts
        WHERE superseded_by IS NULL
          AND fact_type IS NOT NULL AND fact_type != 'unclassified'
        ORDER BY RANDOM()
        LIMIT ?
    """, (spot_check_count,)).fetchall()
    for i, (ft, ftype, cd, tier) in enumerate(sample):
        print(f"  [{i+1:2d}] {ft[:55]}")
        print(f"       type={ftype:12s} depth={cd:12s} tier={tier}")

    # --- Tier promotion source breakdown ---
    print(f"\nTier assignment source:")
    tiered_by = conn.execute("""
        SELECT tiered_by, COUNT(*) as cnt
        FROM memory_facts WHERE superseded_by IS NULL AND tiered_by IS NOT NULL
        GROUP BY tiered_by ORDER BY cnt DESC
    """).fetchall()
    for src, cnt in tiered_by:
        print(f"  {src:15s} {cnt:5d}")

    print(f"\n{'='*70}")
    print("  [LEGACY] CHECKPOINT 3 COMPLETE — Review classifications before green-lighting pipeline")
    print(f"{'='*70}")
    return True


def run_checkpoint(stage, args=None):
    """Run a specific checkpoint or all checkpoints."""
    if not DATABASE_FILE.exists():
        print("No database found. Run: baselayer init")
        return

    with contextlib.closing(get_db()) as conn:
        if stage == "extraction":
            checkpoint_extraction(conn)
        elif stage == "scoring":
            checkpoint_scoring(conn)
        elif stage == "classification":
            checkpoint_classification(conn)
        elif stage == "all":
            checkpoint_extraction(conn)
            print("\n\n")
            checkpoint_scoring(conn)
            print("\n\n")
            checkpoint_classification(conn)
        else:
            print(f"Unknown checkpoint stage: {stage}")
            print("Valid stages: extraction, scoring, classification, all")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    run_checkpoint(sys.argv[1])
