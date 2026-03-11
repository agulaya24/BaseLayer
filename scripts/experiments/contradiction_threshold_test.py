"""
Contradiction Threshold Variation Test

Embeds facts ONCE, then tests multiple threshold configurations to find
the optimal settings for tension/contradiction detection.

Expensive part is Haiku classification (~$0.01 per 50 pairs).
Embedding + candidate selection is $0.

Variations:
  V1: Current defaults (base=0.50, tension_pair=0.65, same_pred=0.50)
  V2: Lower tension pair threshold (base=0.50, tension_pair=0.55)
  V3: Lower base threshold (base=0.45, tension_pair=0.55)
  V4: Aggressive (base=0.40, tension_pair=0.45)
  V5: Only tension predicate pairs (ignore general similarity)
  V6: Cross-category focus (different predicates only, base=0.45)
"""

import contextlib
import json
import os
import sys
import time
import numpy as np
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))

from config import PROJECT_ROOT, DATABASE_FILE, get_db
from detect_contradictions import (
    load_facts,
    embed_facts,
    classify_pair_haiku,
    TENSION_PREDICATE_PAIRS,
)


def find_candidates_configurable(facts, embeddings, config):
    """Find candidate pairs with configurable thresholds."""
    n = len(facts)
    if n == 0:
        return []

    base_threshold = config["base_threshold"]
    tension_threshold = config.get("tension_threshold", base_threshold)
    same_pred_threshold = config.get("same_pred_threshold", base_threshold)
    cross_category_only = config.get("cross_category_only", False)
    tension_pairs_only = config.get("tension_pairs_only", False)

    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    sim_matrix = normalized @ normalized.T

    # Extract upper triangle
    tri_i, tri_j = np.triu_indices(n, k=1)
    sims = sim_matrix[tri_i, tri_j]

    # Use lowest threshold to get initial candidates
    min_threshold = min(base_threshold, tension_threshold, same_pred_threshold)
    mask = sims >= min_threshold
    above_i = tri_i[mask]
    above_j = tri_j[mask]
    above_sims = sims[mask]

    candidates = []
    for idx in range(len(above_i)):
        i, j = int(above_i[idx]), int(above_j[idx])
        fi, fj = facts[i], facts[j]
        sim = float(above_sims[idx])

        pred_a = fi.get("predicate", "")
        pred_b = fj.get("predicate", "")
        cat_a = fi.get("category", "")
        cat_b = fj.get("category", "")

        pred_pair = (pred_a, pred_b)
        is_tension_pair = pred_pair in TENSION_PREDICATE_PAIRS or pred_pair[::-1] in TENSION_PREDICATE_PAIRS
        is_same_pred = pred_a == pred_b and pred_a
        is_cross_category = cat_a != cat_b

        # Apply filters based on config
        if tension_pairs_only and not is_tension_pair:
            continue

        if cross_category_only and not is_cross_category and not is_tension_pair:
            continue

        # Apply appropriate threshold
        if is_tension_pair:
            if sim < tension_threshold:
                continue
        elif is_same_pred:
            if sim < same_pred_threshold:
                continue
        else:
            if sim < base_threshold:
                continue

        reason = "tension_pair" if is_tension_pair else ("same_predicate" if is_same_pred else "similarity")

        candidates.append({
            "fact_a": fi,
            "fact_b": fj,
            "similarity": round(sim, 4),
            "is_tension_pair": is_tension_pair,
            "is_same_predicate": is_same_pred,
            "is_cross_category": is_cross_category,
            "selection_reason": reason,
            "pred_pair": f"{pred_a}/{pred_b}",
        })

    candidates.sort(key=lambda x: (-x["is_tension_pair"], -x["similarity"]))
    return candidates


VARIATIONS = {
    "V1_current_defaults": {
        "base_threshold": 0.50,
        "tension_threshold": 0.65,
        "same_pred_threshold": 0.50,
        "description": "Current defaults (base=0.50, tension=0.65)",
    },
    "V2_lower_tension": {
        "base_threshold": 0.50,
        "tension_threshold": 0.55,
        "same_pred_threshold": 0.50,
        "description": "Lower tension pair threshold (tension=0.55)",
    },
    "V3_lower_base": {
        "base_threshold": 0.45,
        "tension_threshold": 0.55,
        "same_pred_threshold": 0.45,
        "description": "Lower base threshold (base=0.45, tension=0.55)",
    },
    "V4_aggressive": {
        "base_threshold": 0.40,
        "tension_threshold": 0.45,
        "same_pred_threshold": 0.40,
        "description": "Aggressive (base=0.40, tension=0.45)",
    },
    "V5_tension_pairs_only": {
        "base_threshold": 0.30,
        "tension_threshold": 0.40,
        "same_pred_threshold": 0.30,
        "tension_pairs_only": True,
        "description": "Only tension predicate pairs (threshold=0.40)",
    },
    "V6_cross_category": {
        "base_threshold": 0.45,
        "tension_threshold": 0.45,
        "same_pred_threshold": 0.45,
        "cross_category_only": True,
        "description": "Cross-category focus (diff predicates, base=0.45)",
    },
}


def classify_candidates(candidates, max_pairs=40, cache=None):
    """Classify candidates, using cache to avoid re-classifying duplicates."""
    if cache is None:
        cache = {}

    results = []
    classified = 0

    for pair in candidates[:max_pairs]:
        fa = pair["fact_a"]
        fb = pair["fact_b"]
        cache_key = (fa["id"], fb["id"])

        if cache_key in cache:
            result = cache[cache_key]
        else:
            pred_a = fa.get("predicate", "unknown")
            pred_b = fb.get("predicate", "unknown")
            result = classify_pair_haiku(fa["fact_text"], fb["fact_text"], pred_a, pred_b)
            cache[cache_key] = result
            classified += 1

        verdict = result.get("verdict", "CONSISTENT")
        results.append({
            "verdict": verdict,
            "fact_a_text": fa["fact_text"],
            "fact_b_text": fb["fact_text"],
            "fact_a_predicate": fa.get("predicate", ""),
            "fact_b_predicate": fb.get("predicate", ""),
            "similarity": pair["similarity"],
            "reasoning": result.get("reasoning", ""),
            "confidence": result.get("confidence", 0.0),
            "selection_reason": pair["selection_reason"],
            "pred_pair": pair["pred_pair"],
            "is_cross_category": pair.get("is_cross_category", False),
        })

    return results, classified


def main():
    max_pairs_per_variation = 40

    output_dir = PROJECT_ROOT / "data" / "eval" / "threshold_variation"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("CONTRADICTION THRESHOLD VARIATION TEST")
    print(f"DB: {DATABASE_FILE}")
    print(f"Max pairs per variation: {max_pairs_per_variation}")
    print()

    # Load and embed once
    with contextlib.closing(get_db()) as conn:
        facts = load_facts(conn)
    print(f"Loaded {len(facts)} active facts")

    print("Embedding facts (one-time)...")
    embeddings = embed_facts(facts)
    print(f"Embedded {len(embeddings)} facts ({embeddings.shape[1]}d)")
    print()

    # Classification cache — avoid re-classifying the same pair across variations
    cache = {}
    all_results = {}
    total_api_calls = 0

    for var_name, config in VARIATIONS.items():
        print(f"{'=' * 60}")
        print(f"{var_name}: {config['description']}")
        print(f"{'=' * 60}")

        candidates = find_candidates_configurable(facts, embeddings, config)
        print(f"  Candidates found: {len(candidates)}")

        if not candidates:
            all_results[var_name] = {
                "config": {k: v for k, v in config.items() if k != "description"},
                "description": config["description"],
                "candidates_found": 0,
                "classified": 0,
                "contradictions": 0,
                "tensions": 0,
                "consistent": 0,
                "findings": [],
            }
            print(f"  No candidates\n")
            continue

        # Breakdown by selection reason
        reasons = Counter(c["selection_reason"] for c in candidates)
        for reason, count in reasons.most_common():
            print(f"    {reason}: {count}")

        results, new_calls = classify_candidates(candidates, max_pairs_per_variation, cache)
        total_api_calls += new_calls

        contradictions = [r for r in results if r["verdict"] == "CONTRADICTION"]
        tensions = [r for r in results if r["verdict"] == "TENSION"]
        consistent = [r for r in results if r["verdict"] == "CONSISTENT"]

        print(f"  Classified: {len(results)} (new API calls: {new_calls}, cached: {len(results) - new_calls})")
        print(f"  Results: {len(contradictions)} contradictions, {len(tensions)} tensions, {len(consistent)} consistent")

        # Show findings
        for r in contradictions + tensions:
            marker = "[!!]" if r["verdict"] == "CONTRADICTION" else "[~~]"
            print(f"    {marker} {r['verdict']} (sim={r['similarity']:.2f}, {r['selection_reason']})")
            print(f"      {r['fact_a_predicate']}: {r['fact_a_text'][:70]}")
            print(f"      {r['fact_b_predicate']}: {r['fact_b_text'][:70]}")
            print(f"      {r['reasoning']}")

        # Calculate yield rate
        total_classified = len(results)
        yield_rate = (len(contradictions) + len(tensions)) / total_classified * 100 if total_classified > 0 else 0

        all_results[var_name] = {
            "config": {k: v for k, v in config.items() if k != "description"},
            "description": config["description"],
            "candidates_found": len(candidates),
            "classified": total_classified,
            "contradictions": len(contradictions),
            "tensions": len(tensions),
            "consistent": len(consistent),
            "yield_rate_pct": round(yield_rate, 1),
            "findings": contradictions + tensions,
        }
        print(f"  Yield rate: {yield_rate:.1f}%")
        print()

    # Summary comparison
    print("\n" + "=" * 80)
    print("SUMMARY COMPARISON")
    print("=" * 80)
    print(f"{'Variation':<28} {'Candidates':>10} {'Classified':>10} {'C':>4} {'T':>4} {'Yield%':>7} {'Unique':>7}")
    print("-" * 80)

    for var_name, data in all_results.items():
        unique_findings = set()
        for f in data.get("findings", []):
            key = tuple(sorted([f["fact_a_text"][:50], f["fact_b_text"][:50]]))
            unique_findings.add(key)

        print(f"{var_name:<28} {data['candidates_found']:>10} {data['classified']:>10} "
              f"{data['contradictions']:>4} {data['tensions']:>4} "
              f"{data['yield_rate_pct']:>6.1f}% {len(unique_findings):>7}")

    # Find all unique findings across ALL variations
    all_unique = {}
    for var_name, data in all_results.items():
        for f in data.get("findings", []):
            key = tuple(sorted([f["fact_a_text"][:80], f["fact_b_text"][:80]]))
            if key not in all_unique:
                all_unique[key] = {
                    "finding": f,
                    "found_in": [var_name],
                }
            else:
                all_unique[key]["found_in"].append(var_name)

    print(f"\nTotal unique findings across all variations: {len(all_unique)}")
    print(f"Total API calls (deduplicated across variations): {total_api_calls}")
    print(f"Estimated cost: ~${total_api_calls * 0.0004:.3f}")

    # Show which findings are variation-specific
    print(f"\n{'=' * 80}")
    print("FINDINGS BY COVERAGE")
    print("=" * 80)

    for key, info in sorted(all_unique.items(), key=lambda x: len(x[1]["found_in"]), reverse=True):
        f = info["finding"]
        coverage = len(info["found_in"])
        total = len(VARIATIONS)
        marker = "[!!]" if f["verdict"] == "CONTRADICTION" else "[~~]"
        print(f"  {marker} ({coverage}/{total} variations) sim={f['similarity']:.2f}")
        print(f"    {f['fact_a_predicate']}: {f['fact_a_text'][:80]}")
        print(f"    {f['fact_b_predicate']}: {f['fact_b_text'][:80]}")
        print(f"    Found in: {', '.join(info['found_in'])}")
        print()

    # Save full results
    results_file = output_dir / "threshold_results.json"
    # Convert findings to serializable format
    save_data = {}
    for var_name, data in all_results.items():
        save_data[var_name] = {k: v for k, v in data.items()}

    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to: {results_file}")


if __name__ == "__main__":
    main()
