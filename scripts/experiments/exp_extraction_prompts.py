"""
Experiment 5: Extraction Prompt Variations
============================================
Question: Does prompt engineering improve fact extraction quality on local models?

Method:
  - Extract Franklin (10 chapters) with 4 prompt strategies, same Qwen model
  - Compare: fact count, predicate diversity, fact quality (via self-judge)

Conditions:
  A. Standard: Current production prompt (baseline)
  B. Chain-of-thought: Think step-by-step before extracting
  C. Two-pass: First extract topics, then extract facts per topic
  D. Negative-first: Extract what the person avoids/rejects/fears first, then positives
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import call_qwen, get_franklin_conversations, save_results

PREDICATES_STR = ", ".join([
    "owns", "values", "practices", "studies", "prefers", "avoids",
    "works_at", "lives_in", "married_to", "raised_in", "graduated_from",
    "manages", "builds", "trades", "believes", "fears", "enjoys",
    "dislikes", "struggles_with", "excels_at", "identifies_as",
    "maintains", "follows", "aspires_to", "lost", "founded",
    "parents", "experienced", "learned", "decided", "prioritizes",
    "unknown", "attended", "interested_in", "wants_to", "loves", "hates",
    "plays", "monitors", "relates_to", "collaborates_with", "mentored_by",
    "raised_by", "friends_with", "reports_to", "admires", "conflicts_with",
])


def prompt_standard(text: str) -> str:
    return f"""Extract structured facts about the person described in this text.

PREDICATES (use ONLY these): {PREDICATES_STR}

For each fact, return JSON with: subject, predicate, object, confidence (0.0-1.0).
Return a JSON object with a "facts" array. Extract up to 20 facts.

TEXT:
{text[:8000]}

Return ONLY valid JSON."""


def prompt_chain_of_thought(text: str) -> str:
    return f"""You will extract structured facts about the person described in this text.

First, think step by step:
1. Who is the main subject of this text?
2. What are their core beliefs and values?
3. What do they do regularly (practices, habits)?
4. What do they avoid or struggle with?
5. What relationships and roles do they have?
6. What decisions and priorities emerge?

After thinking through these questions, extract structured facts.

PREDICATES (use ONLY these): {PREDICATES_STR}

For each fact, return JSON with: subject, predicate, object, confidence (0.0-1.0).
Return a JSON object with:
  "reasoning": your step-by-step analysis (brief),
  "facts": array of extracted facts

Extract up to 20 facts.

TEXT:
{text[:7000]}

Return ONLY valid JSON."""


def prompt_negative_first(text: str) -> str:
    return f"""Extract structured facts about the person described in this text.
Focus FIRST on what this person avoids, fears, dislikes, struggles with, and rejects.
These negative/avoidance patterns are often the most identity-defining.

EXTRACTION ORDER:
1. First: avoidance, fears, dislikes, struggles, rejections (5+ facts minimum)
2. Then: beliefs, values, practices, preferences
3. Finally: biographical/relational facts

PREDICATES (use ONLY these): {PREDICATES_STR}

For each fact, return JSON with: subject, predicate, object, confidence (0.0-1.0).
Return a JSON object with a "facts" array. Extract up to 20 facts.

TEXT:
{text[:8000]}

Return ONLY valid JSON."""


def run_two_pass(text: str) -> list[dict]:
    """Two-pass extraction: first extract topics, then extract facts per topic."""
    # Pass 1: Extract topics
    topic_prompt = f"""Read this text and identify the 5-8 main topics or themes about the person described.
Return a JSON object with a "topics" array of strings.

TEXT:
{text[:6000]}

Return ONLY valid JSON."""

    try:
        topic_resp = call_qwen(topic_prompt, max_tokens=500, json_mode=True)
        topics = json.loads(topic_resp).get("topics", [])
    except (json.JSONDecodeError, KeyError):
        topics = ["general beliefs", "practices", "relationships", "decisions"]

    if not topics:
        topics = ["general"]

    # Pass 2: Extract facts per topic
    all_facts = []
    for topic in topics[:6]:
        fact_prompt = f"""Extract structured facts about the person described in this text,
focusing specifically on the topic: {topic}

PREDICATES (use ONLY these): {PREDICATES_STR}

For each fact, return JSON with: subject, predicate, object, confidence (0.0-1.0).
Return a JSON object with a "facts" array. Extract up to 5 facts for this topic.

TEXT:
{text[:6000]}

Return ONLY valid JSON."""

        try:
            resp = call_qwen(fact_prompt, max_tokens=2000, json_mode=True)
            facts = json.loads(resp).get("facts", [])
            for f in facts:
                f["_topic"] = topic
            all_facts.extend(facts)
        except (json.JSONDecodeError, KeyError):
            pass

    return all_facts


PROMPT_STRATEGIES = {
    "A_standard": {"fn": prompt_standard, "two_pass": False},
    "B_chain_of_thought": {"fn": prompt_chain_of_thought, "two_pass": False},
    "C_two_pass": {"fn": None, "two_pass": True},
    "D_negative_first": {"fn": prompt_negative_first, "two_pass": False},
}


def extract_with_strategy(conversations: list[dict], strategy_name: str, strategy: dict) -> dict:
    """Run extraction with a specific prompt strategy."""
    all_facts = []
    pred_counts = {}
    errors = 0
    avoidance_predicates = {"avoids", "fears", "dislikes", "struggles_with", "hates", "conflicts_with", "resents"}

    for i, convo in enumerate(conversations):
        print(f"  [{strategy_name}] {i+1}/{len(conversations)}: {convo['title'][:50]}...")

        try:
            if strategy["two_pass"]:
                facts = run_two_pass(convo["text"])
            else:
                prompt = strategy["fn"](convo["text"])
                response = call_qwen(prompt, max_tokens=4000, json_mode=True)
                data = json.loads(response)
                facts = data.get("facts", [])

            for f in facts:
                pred = f.get("predicate", "unknown")
                pred_counts[pred] = pred_counts.get(pred, 0) + 1
                all_facts.append({
                    "predicate": pred,
                    "object": f.get("object", ""),
                    "confidence": f.get("confidence", 0.5),
                })
        except (json.JSONDecodeError, KeyError) as e:
            errors += 1

    fact_sigs = set(f"{f['predicate']}:{str(f.get('object', '')).lower().strip()}" for f in all_facts)
    avoidance_facts = sum(1 for f in all_facts if f["predicate"] in avoidance_predicates)

    return {
        "label": strategy_name,
        "conversations": len(conversations),
        "total_facts": len(all_facts),
        "unique_facts": len(fact_sigs),
        "predicates_used": len(pred_counts),
        "predicate_distribution": dict(sorted(pred_counts.items(), key=lambda x: -x[1])),
        "avoidance_facts": avoidance_facts,
        "avoidance_pct": round(avoidance_facts / max(len(all_facts), 1) * 100, 1),
        "parse_errors": errors,
        "facts": all_facts,
    }


def main():
    print("=" * 60)
    print("EXPERIMENT 5: Extraction Prompt Variations")
    print("=" * 60)

    conversations = get_franklin_conversations(limit=10)
    if not conversations:
        print("ERROR: No Franklin conversations found")
        return

    print(f"Loaded {len(conversations)} Franklin chapters")
    print()

    results = {}
    for name, strategy in PROMPT_STRATEGIES.items():
        print(f"--- {name} ---")
        t0 = time.time()
        result = extract_with_strategy(conversations, name, strategy)
        result["time_seconds"] = round(time.time() - t0, 1)
        results[name] = result
        print(f"  Facts: {result['total_facts']}, Unique: {result['unique_facts']}, "
              f"Avoidance: {result['avoidance_pct']}%, Time: {result['time_seconds']}s")
        print()

    summary = {
        "experiment": "extraction_prompts",
        "question": "Does prompt engineering improve fact extraction quality?",
        "conditions": {},
    }

    print("=" * 60)
    print("SUMMARY")
    print(f"{'Strategy':<25} {'Facts':>6} {'Unique':>7} {'Preds':>6} {'Avoid%':>7} {'Time':>6}")
    print("-" * 60)
    for name, r in results.items():
        print(f"{name:<25} {r['total_facts']:>6} {r['unique_facts']:>7} "
              f"{r['predicates_used']:>6} {r['avoidance_pct']:>6.1f}% {r['time_seconds']:>5.0f}s")
        summary["conditions"][name] = {
            "total_facts": r["total_facts"],
            "unique_facts": r["unique_facts"],
            "predicates_used": r["predicates_used"],
            "avoidance_pct": r["avoidance_pct"],
            "time_seconds": r["time_seconds"],
        }
    print("=" * 60)

    # Key finding: which strategy extracts the most unique, diverse facts?
    best = max(results.values(), key=lambda r: r["unique_facts"])
    print(f"\nBest unique fact yield: {best['label']} ({best['unique_facts']} unique)")
    summary["best_strategy"] = best["label"]
    summary["full_results"] = results
    save_results("extraction_prompts", summary)


if __name__ == "__main__":
    main()
