"""
Contradiction Detection Test — Session 21
Tests similarity threshold and model judgment accuracy across Qwen, Sonnet, and Opus.

Usage:
  python scripts/test_contradiction.py                    # Run similarity + Qwen test
  python scripts/test_contradiction.py --model sonnet     # Run with Sonnet (requires API key)
  python scripts/test_contradiction.py --model opus       # Run with Opus (requires API key)
  python scripts/test_contradiction.py --similarity-only  # Just compute similarity scores
"""

import json
import sys
import time
import requests
from pathlib import Path
import numpy as np

# ── Test Pairs ──────────────────────────────────────────────────────────────
# Each pair has: fact_a, fact_b, expected_judgment, explanation
# expected_judgment: contradiction / enrichment / coexistent / ambiguous

TEST_PAIRS = [
    # ── TRUE CONTRADICTIONS (mutually exclusive) ──
    {
        "fact_a": "Wakes up at 5:30 AM for pre-market trading preparation",
        "fact_b": "Wakes up at 7:00 AM, no longer does pre-market prep",
        "expected": "contradiction",
        "explanation": "Same attribute (wake time), different value. Cannot both be current."
    },
    {
        "fact_a": "Lives in Portland, Texas",
        "fact_b": "Moved to Austin, Texas",
        "expected": "contradiction",
        "explanation": "Same attribute (city of residence), mutually exclusive."
    },
    {
        "fact_a": "Works as a software engineer at Google",
        "fact_b": "Left Google, now freelancing full-time",
        "expected": "contradiction",
        "explanation": "Explicit negation of prior employment state."
    },
    {
        "fact_a": "Currently single, focused on career",
        "fact_b": "In a committed relationship with partner",
        "expected": "contradiction",
        "explanation": "Relationship status is mutually exclusive."
    },
    {
        "fact_a": "Drives a sports car as daily driver",
        "fact_b": "Sold the sports car, now drives a Tesla Model 3",
        "expected": "contradiction",
        "explanation": "Explicit replacement of vehicle."
    },
    {
        "fact_a": "Rents an apartment in the city",
        "fact_b": "Bought a house in the suburbs",
        "expected": "contradiction",
        "explanation": "Housing situation changed — renting vs owning, city vs suburbs."
    },
    {
        "fact_a": "Vegetarian for ethical reasons",
        "fact_b": "Started eating meat again after 5 years",
        "expected": "contradiction",
        "explanation": "Diet state changed explicitly."
    },
    {
        "fact_a": "Uses TD Ameritrade as primary brokerage",
        "fact_b": "Switched to Interactive Brokers as primary brokerage",
        "expected": "contradiction",
        "explanation": "Same attribute (primary brokerage), explicit switch."
    },
    {
        "fact_a": "Studies computer science at University of Texas",
        "fact_b": "Graduated from University of Texas with CS degree",
        "expected": "contradiction",
        "explanation": "State (studying) superseded by event (graduated). Cannot still be studying."
    },
    {
        "fact_a": "CEO of TechCo, an active aerospace startup",
        "fact_b": "TechCo has shut down operations",
        "expected": "contradiction",
        "explanation": "Company active vs shut down — mutually exclusive states."
    },

    # ── NOT CONTRADICTIONS (coexistent) ──
    {
        "fact_a": "Trades SPY options regularly",
        "fact_b": "Has shifted focus to futures trading",
        "expected": "coexistent",
        "explanation": "Both can be true simultaneously. Shifting focus doesn't mean stopping options."
    },
    {
        "fact_a": "Learning Python for data analysis",
        "fact_b": "Learning Rust for systems programming",
        "expected": "coexistent",
        "explanation": "People learn multiple languages. No mutual exclusivity."
    },
    {
        "fact_a": "Working on memory system project",
        "fact_b": "Working on fellowship application",
        "expected": "coexistent",
        "explanation": "Multiple concurrent projects. No conflict."
    },
    {
        "fact_a": "Practices meditation daily",
        "fact_b": "Works out 3-5 times per week",
        "expected": "coexistent",
        "explanation": "Different activities, can both be true."
    },
    {
        "fact_a": "Has two cats named Luna and Milo",
        "fact_b": "Luna weighs 15 pounds",
        "expected": "coexistent",
        "explanation": "Complementary facts about the same entity. Not in conflict."
    },
    {
        "fact_a": "Married to Jordan",
        "fact_b": "Jordan has chronic back pain",
        "expected": "coexistent",
        "explanation": "Facts about the same person, not in conflict."
    },
    {
        "fact_a": "Interested in AI and machine learning",
        "fact_b": "Building a personal AI memory system",
        "expected": "coexistent",
        "explanation": "Complementary — building is a manifestation of interest."
    },
    {
        "fact_a": "Risk tolerance of $100 per trade",
        "fact_b": "Tendency to overtrade at end of day",
        "expected": "coexistent",
        "explanation": "Different attributes of trading behavior. Both can be true."
    },

    # ── ENRICHMENTS (same topic, more detail) ──
    {
        "fact_a": "Trades SPY options",
        "fact_b": "Trades SPY options using 0DTE strategies with strict risk management",
        "expected": "enrichment",
        "explanation": "Same fact with more detail. Not a contradiction."
    },
    {
        "fact_a": "Exercises regularly",
        "fact_b": "Works out 5 times per week, mix of strength and cardio",
        "expected": "enrichment",
        "explanation": "Adds specificity to a general fact."
    },
    {
        "fact_a": "Has a cat",
        "fact_b": "Has two cats named Luna and Milo",
        "expected": "enrichment",
        "explanation": "Adds detail — number and names."
    },
    {
        "fact_a": "Built and ran a company",
        "fact_b": "Built and ran TechCo, an aerospace startup that generated significant revenue",
        "expected": "enrichment",
        "explanation": "Same core fact with company name, domain, and revenue."
    },

    # ── AMBIGUOUS (could go either way) ──
    {
        "fact_a": "Day trades SPY options as primary income source",
        "fact_b": "Got a full-time job at a tech company",
        "expected": "ambiguous",
        "explanation": "Cascade effect — new job might affect day trading, but both could coexist."
    },
    {
        "fact_a": "Trades SPY options regularly",
        "fact_b": "Shifted to swing trading approach",
        "expected": "ambiguous",
        "explanation": "Swing trading might replace or complement options trading. Can't tell without context."
    },
    {
        "fact_a": "Follows a strict morning routine with trading prep",
        "fact_b": "Started a new job with 9-5 schedule",
        "expected": "ambiguous",
        "explanation": "Cascade — job schedule might disrupt morning trading routine, or might not."
    },
    {
        "fact_a": "One cup of coffee in the morning",
        "fact_b": "Switched to tea for health reasons",
        "expected": "ambiguous",
        "explanation": "Might have replaced coffee, might drink both. Unclear."
    },
]

# ── Similarity Computation ──────────────────────────────────────────────────

def compute_similarities(pairs):
    """Compute embedding similarity for all test pairs."""
    from api_client import get_embedding_model
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = get_embedding_model()

    results = []
    for i, pair in enumerate(pairs):
        emb_a = model.encode([pair["fact_a"]])[0]
        emb_b = model.encode([pair["fact_b"]])[0]

        # Cosine similarity
        similarity = float(np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b)))

        results.append({
            "pair_index": i,
            "fact_a": pair["fact_a"],
            "fact_b": pair["fact_b"],
            "expected": pair["expected"],
            "similarity": round(similarity, 4),
            "explanation": pair["explanation"],
        })

    return results


def print_similarity_results(results):
    """Print similarity results grouped by expected judgment."""
    groups = {}
    for r in results:
        groups.setdefault(r["expected"], []).append(r)

    print("\n" + "=" * 90)
    print("SIMILARITY THRESHOLD ANALYSIS")
    print("=" * 90)

    for category in ["contradiction", "coexistent", "enrichment", "ambiguous"]:
        if category not in groups:
            continue
        items = groups[category]
        sims = [r["similarity"] for r in items]
        print(f"\n{'-' * 90}")
        print(f"  {category.upper()} pairs (n={len(items)})")
        print(f"  Mean similarity: {np.mean(sims):.4f}  |  Min: {np.min(sims):.4f}  |  Max: {np.max(sims):.4f}")
        print(f"{'-' * 90}")
        for r in sorted(items, key=lambda x: x["similarity"], reverse=True):
            print(f"  {r['similarity']:.4f}  {r['fact_a'][:40]:40s} <-> {r['fact_b'][:40]}")

    # Threshold analysis
    print(f"\n{'=' * 90}")
    print("THRESHOLD RECOMMENDATIONS")
    print("=" * 90)

    contradiction_sims = [r["similarity"] for r in results if r["expected"] == "contradiction"]
    non_contradiction_sims = [r["similarity"] for r in results if r["expected"] in ("coexistent", "enrichment")]

    if contradiction_sims and non_contradiction_sims:
        min_contradiction = min(contradiction_sims)
        max_non_contradiction = max(non_contradiction_sims)
        print(f"\n  Lowest contradiction similarity:     {min_contradiction:.4f}")
        print(f"  Highest non-contradiction similarity: {max_non_contradiction:.4f}")

        if min_contradiction > max_non_contradiction:
            midpoint = (min_contradiction + max_non_contradiction) / 2
            print(f"  Clean separation! Suggested threshold: {midpoint:.4f}")
        else:
            print(f"  OVERLAP detected — similarity alone cannot distinguish.")
            print(f"  This confirms the need for LLM judgment on candidates above threshold.")

            # Find a threshold that catches most contradictions with acceptable false positives
            for threshold in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]:
                caught = sum(1 for s in contradiction_sims if s >= threshold)
                false_pos = sum(1 for s in non_contradiction_sims if s >= threshold)
                total_non = len(non_contradiction_sims)
                print(f"    Threshold {threshold:.2f}: catches {caught}/{len(contradiction_sims)} contradictions, "
                      f"{false_pos}/{total_non} false positives")


# ── LLM Judgment ────────────────────────────────────────────────────────────

CONTRADICTION_PROMPT = """You are judging whether two facts about the same person can coexist as currently true.

Fact A: "{fact_a}"
Fact B: "{fact_b}"

Classify this pair as exactly one of:
- CONTRADICTION: These facts cannot both be currently true for the same person. One explicitly replaces or negates the other.
- ENRICHMENT: Fact B adds detail to Fact A. They describe the same thing at different levels of specificity.
- COEXISTENT: Both facts can be true at the same time. They describe different things or compatible states.
- AMBIGUOUS: It's unclear whether these conflict. A person would need to confirm.

Rules:
- Default to COEXISTENT. Only declare CONTRADICTION if there is clear mutual exclusivity.
- A "shift" in focus or interest does NOT mean the prior activity stopped.
- People can do multiple things simultaneously (multiple projects, hobbies, investments).
- A new job does NOT automatically mean other activities stopped.
- Adding detail is ENRICHMENT, not contradiction.

Respond with exactly one line in this format:
JUDGMENT: [CONTRADICTION|ENRICHMENT|COEXISTENT|AMBIGUOUS]
REASONING: [one sentence explaining why]"""


def test_qwen(pairs, similarity_results):
    """Test Qwen 2.5 14B via Ollama on contradiction judgment."""
    print("\n" + "=" * 90)
    print("QWEN 2.5 14B — CONTRADICTION JUDGMENT TEST")
    print("=" * 90)

    correct = 0
    total = len(pairs)
    results = []

    for i, pair in enumerate(pairs):
        prompt = CONTRADICTION_PROMPT.format(fact_a=pair["fact_a"], fact_b=pair["fact_b"])
        sim = similarity_results[i]["similarity"]

        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:14b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 150},
                },
                timeout=60,
            )
            output = resp.json().get("response", "").strip()

            # Parse judgment
            judgment = "UNKNOWN"
            reasoning = ""
            for line in output.split("\n"):
                if line.startswith("JUDGMENT:"):
                    judgment = line.split(":", 1)[1].strip().upper()
                elif line.startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip()

            is_correct = judgment.lower() == pair["expected"].lower()
            if is_correct:
                correct += 1

            mark = "OK" if is_correct else "MISS"
            print(f"\n  [{mark}] Pair {i+1}/{total} (sim={sim:.4f})")
            print(f"    A: {pair['fact_a'][:70]}")
            print(f"    B: {pair['fact_b'][:70]}")
            print(f"    Expected: {pair['expected']:15s} | Got: {judgment}")
            if reasoning:
                print(f"    Reasoning: {reasoning[:80]}")

            results.append({
                "pair_index": i,
                "expected": pair["expected"],
                "judgment": judgment,
                "correct": is_correct,
                "similarity": sim,
                "reasoning": reasoning,
            })

        except Exception as e:
            print(f"\n  [ERR] Pair {i+1}: {e}")
            results.append({
                "pair_index": i, "expected": pair["expected"],
                "judgment": "ERROR", "correct": False, "similarity": sim,
                "reasoning": str(e),
            })

    # Summary
    print(f"\n{'=' * 90}")
    print(f"QWEN RESULTS: {correct}/{total} correct ({correct/total*100:.1f}%)")
    print(f"{'=' * 90}")

    for category in ["contradiction", "coexistent", "enrichment", "ambiguous"]:
        cat_results = [r for r in results if r["expected"] == category]
        cat_correct = sum(1 for r in cat_results if r["correct"])
        if cat_results:
            print(f"  {category:15s}: {cat_correct}/{len(cat_results)} correct")

    return results


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    similarity_only = "--similarity-only" in sys.argv

    # Step 1: Compute similarities
    print(f"Computing similarities for {len(TEST_PAIRS)} test pairs...")
    sim_results = compute_similarities(TEST_PAIRS)
    print_similarity_results(sim_results)

    if similarity_only:
        return

    # Step 2: Run Qwen judgment test
    print("\nRunning Qwen 2.5 14B judgment test...")
    print("(This will take a few minutes — one Ollama call per pair)")
    qwen_results = test_qwen(TEST_PAIRS, sim_results)

    # Save results
    output_path = Path(__file__).parent.parent / "data" / "test_contradiction_results.json"
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "num_pairs": len(TEST_PAIRS),
        "similarity_results": sim_results,
        "qwen_results": qwen_results,
    }
    output_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
