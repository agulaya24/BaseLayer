"""
Experiment 4: Temporality Experiments
======================================
Question: Does temporal signal (recency, drift, evolution) improve identity modeling?

Method:
  - Use User A's 1,892 conversations (the only subject with enough temporal data)
  - Test 3 temporal conditions on a sample:
    A. Flat extraction (current): all conversations equal weight
    B. Recency-weighted: weight recent conversations 2x in extraction prompt
    C. Temporal drift: extract from Q1 and Q4 separately, compare predicate shifts
  - Measure: fact stability, predicate evolution, new-vs-stable ratio

Note: Uses Qwen on User A's imported conversations. Only extracts — no authoring.
"""

import json
import sys
import os
import time
import sqlite3
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from ollama_utils import call_qwen, save_results

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


def load_user_a_conversations(quartile: str = "all", sample: int = 20) -> list[dict]:
    """Load User A's conversations, optionally filtered by temporal quartile."""
    # User A's main DB
    _root = Path(__file__).parent.parent.parent
    db_path = str(_root / "data" / "database" / "memory.db")
    if not os.path.exists(db_path):
        db_path = str(_root.parent / "memory_system_v4" / "data" / "database" / "memory.db")
    if not os.path.exists(db_path):
        print(f"ERROR: User A's database not found")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get date range
    date_range = conn.execute(
        "SELECT MIN(created_at) as earliest, MAX(created_at) as latest FROM conversations"
    ).fetchone()

    if quartile == "all":
        order = "ORDER BY RANDOM()"
    elif quartile == "Q1":
        # First quartile by date
        order = "ORDER BY c.created_at ASC"
    elif quartile == "Q4":
        # Last quartile by date
        order = "ORDER BY c.created_at DESC"
    else:
        order = "ORDER BY RANDOM()"

    rows = conn.execute(f"""
        SELECT c.id, c.title, c.created_at,
               GROUP_CONCAT(m.content_text, '\n\n') as full_text
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        WHERE m.content_text IS NOT NULL AND LENGTH(m.content_text) > 50
          AND m.role = 'user'
        GROUP BY c.id
        HAVING LENGTH(full_text) > 200
        {order}
        LIMIT ?
    """, (sample,)).fetchall()

    convos = [{
        "id": r["id"],
        "title": r["title"] or "Untitled",
        "created_at": r["created_at"],
        "text": r["full_text"],
    } for r in rows]

    conn.close()
    return convos


def extract_facts(text: str, extra_instruction: str = "") -> list[dict]:
    """Extract facts from text using Qwen."""
    prompt = f"""Extract structured facts about the person speaking in this conversation.
{extra_instruction}
PREDICATES (use ONLY these): {PREDICATES_STR}

For each fact, return JSON with: subject, predicate, object, confidence (0.0-1.0).
Return a JSON object with a "facts" array. Extract up to 15 facts.

TEXT:
{text[:6000]}

Return ONLY valid JSON."""

    try:
        response = call_qwen(prompt, max_tokens=3000, json_mode=True)
        data = json.loads(response)
        return data.get("facts", [])
    except (json.JSONDecodeError, KeyError):
        return []


def run_condition(conversations: list[dict], label: str, extra_instruction: str = "") -> dict:
    """Run extraction on a set of conversations."""
    all_facts = []
    pred_counts = {}

    for i, convo in enumerate(conversations):
        print(f"  [{label}] {i+1}/{len(conversations)}: {convo['title'][:50].encode('ascii', errors='replace').decode()}...")
        facts = extract_facts(convo["text"], extra_instruction)
        for f in facts:
            pred = f.get("predicate", "unknown")
            pred_counts[pred] = pred_counts.get(pred, 0) + 1
            all_facts.append({
                "predicate": pred,
                "object": f.get("object", ""),
                "confidence": f.get("confidence", 0.5),
                "source_date": convo.get("created_at", ""),
            })

    fact_sigs = set(f"{f['predicate']}:{str(f.get('object', '')).lower().strip()}" for f in all_facts)

    return {
        "label": label,
        "conversations": len(conversations),
        "total_facts": len(all_facts),
        "unique_facts": len(fact_sigs),
        "predicate_distribution": dict(sorted(pred_counts.items(), key=lambda x: -x[1])),
        "facts": all_facts,
    }


def main():
    print("=" * 60)
    print("EXPERIMENT 4: Temporality")
    print("=" * 60)

    # Condition A: Flat random sample
    print("\n--- Condition A: Flat (random sample, 20 convos) ---")
    flat_convos = load_user_a_conversations("all", sample=20)
    if not flat_convos:
        print("ERROR: No conversations found")
        return
    print(f"  Loaded {len(flat_convos)} conversations")
    t0 = time.time()
    flat_result = run_condition(flat_convos, "A_flat")
    flat_result["time_seconds"] = round(time.time() - t0, 1)

    # Condition B: Recency-weighted (recent 20 convos, with emphasis prompt)
    print("\n--- Condition B: Recency-weighted (newest 20 convos) ---")
    recent_convos = load_user_a_conversations("Q4", sample=20)
    print(f"  Loaded {len(recent_convos)} recent conversations")
    t0 = time.time()
    recency_instruction = "Focus on CURRENT, ACTIVE patterns. Prioritize facts that reflect the person's present state over historical facts. Weight recent behaviors and beliefs higher."
    recent_result = run_condition(recent_convos, "B_recency", recency_instruction)
    recent_result["time_seconds"] = round(time.time() - t0, 1)

    # Condition C: Early quartile (oldest 20 convos)
    print("\n--- Condition C: Early quartile (oldest 20 convos) ---")
    early_convos = load_user_a_conversations("Q1", sample=20)
    print(f"  Loaded {len(early_convos)} early conversations")
    t0 = time.time()
    early_result = run_condition(early_convos, "C_early")
    early_result["time_seconds"] = round(time.time() - t0, 1)

    # Drift analysis: compare Q1 vs Q4 predicate distributions
    q1_preds = set(early_result["predicate_distribution"].keys())
    q4_preds = set(recent_result["predicate_distribution"].keys())
    stable_preds = q1_preds & q4_preds
    q1_only = q1_preds - q4_preds
    q4_only = q4_preds - q1_preds

    q1_facts = set(f"{f['predicate']}:{str(f.get('object', '')).lower().strip()}" for f in early_result["facts"])
    q4_facts = set(f"{f['predicate']}:{str(f.get('object', '')).lower().strip()}" for f in recent_result["facts"])
    stable_facts = q1_facts & q4_facts
    evolved_facts = q4_facts - q1_facts
    dropped_facts = q1_facts - q4_facts

    drift = {
        "stable_predicates": sorted(stable_preds),
        "q1_only_predicates": sorted(q1_only),
        "q4_only_predicates": sorted(q4_only),
        "predicate_stability": round(len(stable_preds) / max(len(q1_preds | q4_preds), 1), 3),
        "stable_facts": len(stable_facts),
        "evolved_facts": len(evolved_facts),
        "dropped_facts": len(dropped_facts),
        "fact_stability": round(len(stable_facts) / max(len(q1_facts | q4_facts), 1), 3),
    }

    summary = {
        "experiment": "temporality",
        "question": "Does temporal signal improve identity modeling?",
        "conditions": {
            "A_flat": {
                "total_facts": flat_result["total_facts"],
                "unique_facts": flat_result["unique_facts"],
                "predicates_used": len(flat_result["predicate_distribution"]),
                "time_seconds": flat_result["time_seconds"],
            },
            "B_recency": {
                "total_facts": recent_result["total_facts"],
                "unique_facts": recent_result["unique_facts"],
                "predicates_used": len(recent_result["predicate_distribution"]),
                "time_seconds": recent_result["time_seconds"],
            },
            "C_early": {
                "total_facts": early_result["total_facts"],
                "unique_facts": early_result["unique_facts"],
                "predicates_used": len(early_result["predicate_distribution"]),
                "time_seconds": early_result["time_seconds"],
            },
        },
        "temporal_drift": drift,
        "full_results": {
            "flat": flat_result,
            "recency": recent_result,
            "early": early_result,
        },
    }

    print()
    print("=" * 60)
    print("SUMMARY")
    print(f"{'Condition':<20} {'Facts':>6} {'Unique':>7} {'Preds':>6} {'Time':>6}")
    print("-" * 50)
    for name, r in summary["conditions"].items():
        print(f"{name:<20} {r['total_facts']:>6} {r['unique_facts']:>7} "
              f"{r['predicates_used']:>6} {r['time_seconds']:>5.0f}s")
    print()
    print("TEMPORAL DRIFT (Q1 vs Q4):")
    print(f"  Predicate stability: {drift['predicate_stability']:.1%}")
    print(f"  Fact stability: {drift['fact_stability']:.1%}")
    print(f"  Evolved (new in Q4): {drift['evolved_facts']}")
    print(f"  Dropped (gone from Q1): {drift['dropped_facts']}")
    print(f"  Stable (present in both): {drift['stable_facts']}")
    print(f"  Q1-only predicates: {drift['q1_only_predicates']}")
    print(f"  Q4-only predicates: {drift['q4_only_predicates']}")
    print("=" * 60)

    save_results("temporality", summary)


if __name__ == "__main__":
    main()
