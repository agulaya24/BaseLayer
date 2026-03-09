"""
Experiment 1: Predicate Expansion — 47 vs 70 predicates
========================================================
Question: Do more predicates capture more nuanced identity signal, or just add noise?

Method:
  - Extract facts from Franklin (10 chapters) with standard 47 predicates
  - Extract same chapters with expanded 70 predicates (+23 new ones)
  - Compare: fact count, predicate distribution, unique info captured

New predicates (23): emotional/cognitive/social dimensions currently missing.
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import call_qwen, get_franklin_conversations, save_results

# Current 47 predicates (from config.py)
STANDARD_PREDICATES = [
    "owns", "values", "practices", "studies", "prefers", "avoids",
    "works_at", "lives_in", "married_to", "raised_in", "graduated_from",
    "manages", "builds", "trades", "believes", "fears", "enjoys",
    "dislikes", "struggles_with", "excels_at", "identifies_as",
    "maintains", "follows", "aspires_to", "lost", "founded",
    "parents", "experienced", "learned", "decided", "prioritizes",
    "unknown", "attended", "interested_in", "wants_to", "loves", "hates",
    "plays", "monitors",
    "relates_to", "collaborates_with", "mentored_by", "raised_by",
    "friends_with", "reports_to", "admires", "conflicts_with",
]

# Expanded 70 predicates: +23 covering emotional, cognitive, social gaps
EXPANDED_PREDICATES = STANDARD_PREDICATES + [
    # Cognitive patterns (how someone thinks)
    "reasons_from",       # epistemic starting point ("reasons from first principles")
    "defaults_to",        # automatic response pattern ("defaults to skepticism")
    "reframes_as",        # cognitive reframing habit ("reframes failure as learning")
    "distinguishes",      # key distinctions they make ("distinguishes effort from output")
    "assumes",            # background assumptions ("assumes good intent")
    # Emotional patterns
    "tolerates",          # what they can endure ("tolerates ambiguity")
    "resents",            # specific resentments ("resents bureaucracy")
    "regrets",            # stated regrets
    "celebrates",         # what they mark as wins
    "worries_about",      # ongoing concerns (distinct from fears — lower intensity)
    # Social/relational patterns
    "persuades_via",      # influence strategy ("persuades via questions not statements")
    "defers_to",          # who/what they defer to on decisions
    "protects",           # who/what they shield
    "teaches",            # what they pass on to others
    "delegates",          # what they hand off vs. own
    # Decision patterns
    "optimizes_for",      # terminal values in decisions ("optimizes for optionality")
    "sacrifices",         # known tradeoffs they make ("sacrifices speed for accuracy")
    "experiments_with",   # things they try without commitment
    "abandoned",          # things they used to do/believe but stopped
    "resists",            # things they push back on (distinct from avoids — active)
    # Identity markers
    "defines_self_as",    # self-description beyond identifies_as
    "rejects_label",      # labels they explicitly reject
    "oscillates_between", # known internal tensions ("oscillates between caution and risk")
]


def build_extraction_prompt(text: str, predicates: list[str], max_facts: int = 30) -> str:
    pred_list = ", ".join(predicates)
    return f"""Extract structured facts about the person described in this text.

PREDICATES (use ONLY these): {pred_list}

For each fact, return a JSON object with:
- subject: who the fact is about (use "this person" for the main subject)
- predicate: one of the predicates above
- object: the specific value/entity
- confidence: 0.0-1.0

Return a JSON object with a "facts" array. Extract up to {max_facts} facts.

TEXT:
{text[:8000]}

Return ONLY valid JSON."""


def run_extraction(conversations: list[dict], predicates: list[str], label: str) -> dict:
    """Run extraction on conversations with given predicate set."""
    all_facts = []
    predicate_counts = {}
    errors = 0

    for i, convo in enumerate(conversations):
        print(f"  [{label}] {i+1}/{len(conversations)}: {convo['title'][:60]}...")
        prompt = build_extraction_prompt(convo["text"], predicates)

        try:
            response = call_qwen(prompt, max_tokens=4000, json_mode=True)
            data = json.loads(response)
            facts = data.get("facts", [])

            for fact in facts:
                pred = fact.get("predicate", "unknown")
                predicate_counts[pred] = predicate_counts.get(pred, 0) + 1
                all_facts.append({
                    "source": convo["title"],
                    "predicate": pred,
                    "object": fact.get("object", ""),
                    "confidence": fact.get("confidence", 0.5),
                })
        except (json.JSONDecodeError, KeyError) as e:
            errors += 1
            print(f"    ERROR: {e}")

    return {
        "label": label,
        "predicate_set_size": len(predicates),
        "conversations_processed": len(conversations),
        "total_facts": len(all_facts),
        "unique_predicates_used": len(predicate_counts),
        "predicate_distribution": dict(sorted(predicate_counts.items(), key=lambda x: -x[1])),
        "parse_errors": errors,
        "facts": all_facts,
    }


def main():
    print("=" * 60)
    print("EXPERIMENT 1: Predicate Expansion (47 vs 70)")
    print("=" * 60)

    conversations = get_franklin_conversations(limit=10)
    if not conversations:
        print("ERROR: No Franklin conversations found")
        return

    print(f"Loaded {len(conversations)} Franklin chapters")
    print()

    # Run with standard predicates
    print("--- Standard 47 predicates ---")
    t0 = time.time()
    standard_results = run_extraction(conversations, STANDARD_PREDICATES, "standard_47")
    standard_results["time_seconds"] = round(time.time() - t0, 1)
    print(f"  Total facts: {standard_results['total_facts']}, "
          f"Unique predicates used: {standard_results['unique_predicates_used']}, "
          f"Time: {standard_results['time_seconds']}s")
    print()

    # Run with expanded predicates
    print("--- Expanded 70 predicates ---")
    t0 = time.time()
    expanded_results = run_extraction(conversations, EXPANDED_PREDICATES, "expanded_70")
    expanded_results["time_seconds"] = round(time.time() - t0, 1)
    print(f"  Total facts: {expanded_results['total_facts']}, "
          f"Unique predicates used: {expanded_results['unique_predicates_used']}, "
          f"Time: {expanded_results['time_seconds']}s")
    print()

    # New predicates actually used
    new_preds_used = set(expanded_results["predicate_distribution"].keys()) - set(STANDARD_PREDICATES)
    new_pred_facts = sum(expanded_results["predicate_distribution"].get(p, 0) for p in new_preds_used)

    summary = {
        "experiment": "predicate_expansion",
        "question": "Do more predicates capture more nuanced identity signal?",
        "standard": {
            "predicate_count": 47,
            "facts_extracted": standard_results["total_facts"],
            "unique_predicates_used": standard_results["unique_predicates_used"],
            "time_seconds": standard_results["time_seconds"],
        },
        "expanded": {
            "predicate_count": 70,
            "facts_extracted": expanded_results["total_facts"],
            "unique_predicates_used": expanded_results["unique_predicates_used"],
            "time_seconds": expanded_results["time_seconds"],
            "new_predicates_used": sorted(new_preds_used),
            "facts_from_new_predicates": new_pred_facts,
        },
        "delta": {
            "fact_count_diff": expanded_results["total_facts"] - standard_results["total_facts"],
            "new_predicate_utilization": f"{len(new_preds_used)}/23",
            "pct_facts_from_new_predicates": round(new_pred_facts / max(expanded_results["total_facts"], 1) * 100, 1),
        },
        "standard_detail": standard_results,
        "expanded_detail": expanded_results,
    }

    print("=" * 60)
    print("SUMMARY")
    print(f"  Standard (47): {summary['standard']['facts_extracted']} facts, "
          f"{summary['standard']['unique_predicates_used']} predicates used")
    print(f"  Expanded (70): {summary['expanded']['facts_extracted']} facts, "
          f"{summary['expanded']['unique_predicates_used']} predicates used")
    print(f"  New predicates utilized: {summary['delta']['new_predicate_utilization']}")
    print(f"  Facts from new predicates: {summary['delta']['pct_facts_from_new_predicates']}%")
    print("=" * 60)

    save_results("predicate_expansion", summary)


if __name__ == "__main__":
    main()
