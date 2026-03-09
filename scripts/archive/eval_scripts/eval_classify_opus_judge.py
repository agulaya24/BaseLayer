"""
Opus-as-judge evaluation of Haiku classification prompt.

1. Pulls 20 random active personal-scope facts from each of the 4 fact_type categories (80 total)
2. Sends all 80 to Haiku using the REVISED CLASSIFY_PROMPT
3. Sends all 80 facts + Haiku's classifications to Opus as judge (single call)
4. Reports accuracy, breakdowns, disagreements, and costs.

Read-only — does NOT update the database.
"""

import contextlib
import sqlite3
import json
import sys
import os
import re
import anthropic

# Import the prompt and normalization from the actual script
sys.path.insert(0, os.path.dirname(__file__))
from classify_facts_haiku import CLASSIFY_PROMPT, MODEL as HAIKU_MODEL, normalize_fact_type, normalize_commitment_depth

from config import DATABASE_FILE

CLIENT = None  # Lazy init — avoid crash on import without API key
OPUS_MODEL = "claude-opus-4-6"


def fetch_sample_facts(conn):
    """Pull 20 random active personal-scope facts from each of the 4 fact_type categories."""
    cur = conn.cursor()
    fact_types = ["biographical", "behavioral", "positional", "preference"]
    all_facts = []

    for ft in fact_types:
        cur.execute("""
            SELECT id, fact_text, fact_type, commitment_depth
            FROM memory_facts
            WHERE superseded_by IS NULL
            AND scope = 'personal'
            AND fact_type = ?
            ORDER BY RANDOM()
            LIMIT 20
        """, (ft,))
        rows = cur.fetchall()
        print(f"  Sampled {len(rows)} facts with fact_type = {ft}")
        all_facts.extend(rows)

    return all_facts


def classify_with_haiku(facts_for_api):
    """Send facts to Haiku for classification using the revised prompt."""
    lines = []
    for fid, text in facts_for_api:
        clean = text.replace('"', "'").replace("\n", " ").replace("\r", " ")[:200]
        lines.append(f'[{fid}] {clean}')
    fact_list = "\n".join(lines)

    response = CLIENT.messages.create(
        model=HAIKU_MODEL,
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": CLASSIFY_PROMPT + fact_list
        }]
    )

    text = response.content[0].text.strip()

    # Extract JSON from response
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        print("  WARNING: Failed to parse Haiku JSON response")
        print("  Response preview: %s" % text[:500])
        return {}, response.usage.input_tokens, response.usage.output_tokens

    # Build lookup dict by id
    lookup = {}
    for r in results:
        rid = str(r.get("id", "")).strip()
        if not rid:
            continue
        lookup[rid] = {
            "fact_type": normalize_fact_type(r.get("fact_type", "")),
            "commitment_depth": normalize_commitment_depth(r.get("commitment_depth", ""))
        }

    return lookup, response.usage.input_tokens, response.usage.output_tokens


def judge_with_opus(all_facts, haiku_results):
    """Send all facts + Haiku classifications to Opus for judging."""

    # Build the facts list for Opus
    facts_for_judge = []
    for row in all_facts:
        fact_id, fact_text, db_type, db_depth = row
        if fact_id not in haiku_results:
            continue
        haiku = haiku_results[fact_id]
        facts_for_judge.append({
            "id": fact_id,
            "fact_text": fact_text[:200],
            "assigned_fact_type": haiku["fact_type"],
            "assigned_commitment_depth": haiku["commitment_depth"]
        })

    judge_prompt = """You are evaluating fact classifications. For each fact, judge whether the assigned fact_type and commitment_depth are correct.

Definitions:
- biographical: facts about who they are, what happened to them, relationships, job history, one-off actions, capabilities
- behavioral: RECURRING patterns of how they characteristically act — requires repeated tendency, not one-time actions
- positional: what they explicitly believe, argue for, or evaluate as true/important — requires evaluative stance
- preference: what they like, are interested in, choose, or gravitate toward

- factual: not a belief; events, identifiers, relationships, observed capabilities
- preference: soft, could change easily
- position: argued for, but would revise with evidence
- conviction: core to who they are, would not change without fundamental shift

For each fact, return:
{"id": "...", "fact_type_correct": true/false, "fact_type_should_be": "...", "depth_correct": true/false, "depth_should_be": "...", "notes": "brief reason if incorrect"}

Return JSON array only. No markdown fences, no explanation outside the array.

Facts to evaluate:
""" + json.dumps(facts_for_judge, indent=2)

    response = CLIENT.messages.create(
        model=OPUS_MODEL,
        max_tokens=16384,
        messages=[{
            "role": "user",
            "content": judge_prompt
        }]
    )

    text = response.content[0].text.strip()

    # Extract JSON from response
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        print("  WARNING: Failed to parse Opus JSON response")
        print("  Response preview: %s" % text[:1000])
        return {}, response.usage.input_tokens, response.usage.output_tokens

    # Build lookup
    lookup = {}
    for r in results:
        rid = str(r.get("id", "")).strip()
        if not rid:
            continue
        lookup[rid] = {
            "fact_type_correct": r.get("fact_type_correct", True),
            "fact_type_should_be": r.get("fact_type_should_be", ""),
            "depth_correct": r.get("depth_correct", True),
            "depth_should_be": r.get("depth_should_be", ""),
            "notes": r.get("notes", "")
        }

    return lookup, response.usage.input_tokens, response.usage.output_tokens


def main():
    global CLIENT
    from api_client import get_anthropic_client
    CLIENT = get_anthropic_client()

    with contextlib.closing(sqlite3.connect(str(DATABASE_FILE))) as conn:
        print("=" * 110)
        print("OPUS-AS-JUDGE EVALUATION OF HAIKU CLASSIFICATION PROMPT")
        print(f"Haiku model: {HAIKU_MODEL}")
        print(f"Judge model: {OPUS_MODEL}")
        print("=" * 110)

        # Step 1: Fetch sample facts
        print("\n[Step 1] Sampling facts from database...")
        all_facts = fetch_sample_facts(conn)
        print(f"  Total sampled: {len(all_facts)}")

        # Step 2: Classify with Haiku
        facts_for_api = [(row[0], row[1]) for row in all_facts]
        print(f"\n[Step 2] Sending {len(facts_for_api)} facts to Haiku for classification...")
        haiku_results, haiku_in, haiku_out = classify_with_haiku(facts_for_api)
        print(f"  Received {len(haiku_results)} classifications")
        print(f"  Haiku tokens: {haiku_in:,} input, {haiku_out:,} output")
        haiku_cost = (haiku_in / 1e6) * 0.80 + (haiku_out / 1e6) * 4.00
        print(f"  Haiku cost: ${haiku_cost:.4f}")

        missing_haiku = [row[0] for row in all_facts if row[0] not in haiku_results]
        if missing_haiku:
            print(f"  WARNING: {len(missing_haiku)} facts not returned by Haiku")

        # Step 3: Judge with Opus
        print(f"\n[Step 3] Sending {len(haiku_results)} facts + Haiku classifications to Opus as judge...")
        opus_results, opus_in, opus_out = judge_with_opus(all_facts, haiku_results)
        print(f"  Received {len(opus_results)} judgments")
        print(f"  Opus tokens: {opus_in:,} input, {opus_out:,} output")
        opus_cost = (opus_in / 1e6) * 15.00 + (opus_out / 1e6) * 75.00
        print(f"  Opus cost: ${opus_cost:.4f}")

        missing_opus = [fid for fid in haiku_results if fid not in opus_results]
        if missing_opus:
            print(f"  WARNING: {len(missing_opus)} facts not judged by Opus")

        # Step 4: Calculate accuracy
        print("\n" + "=" * 110)
        print("RESULTS")
        print("=" * 110)

        # Overall counters
        type_correct = 0
        type_total = 0
        depth_correct = 0
        depth_total = 0

        # Per haiku-assigned-type accuracy
        type_by_haiku_type = {}  # {haiku_type: {correct: N, total: N}}
        depth_by_haiku_type = {}

        # Per haiku-assigned-depth accuracy
        depth_by_haiku_depth = {}

        # Disagreement details
        disagreements = []

        for row in all_facts:
            fact_id, fact_text, db_type, db_depth = row

            if fact_id not in haiku_results or fact_id not in opus_results:
                continue

            haiku = haiku_results[fact_id]
            opus = opus_results[fact_id]

            h_type = haiku["fact_type"]
            h_depth = haiku["commitment_depth"]

            # fact_type accuracy
            type_total += 1
            is_type_correct = opus["fact_type_correct"]
            if is_type_correct:
                type_correct += 1

            # commitment_depth accuracy
            depth_total += 1
            is_depth_correct = opus["depth_correct"]
            if is_depth_correct:
                depth_correct += 1

            # Per haiku-assigned-type breakdown
            if h_type not in type_by_haiku_type:
                type_by_haiku_type[h_type] = {"correct": 0, "total": 0}
            type_by_haiku_type[h_type]["total"] += 1
            if is_type_correct:
                type_by_haiku_type[h_type]["correct"] += 1

            if h_type not in depth_by_haiku_type:
                depth_by_haiku_type[h_type] = {"correct": 0, "total": 0}
            depth_by_haiku_type[h_type]["total"] += 1
            if is_depth_correct:
                depth_by_haiku_type[h_type]["correct"] += 1

            # Per haiku-assigned-depth breakdown
            if h_depth not in depth_by_haiku_depth:
                depth_by_haiku_depth[h_depth] = {"correct": 0, "total": 0}
            depth_by_haiku_depth[h_depth]["total"] += 1
            if is_depth_correct:
                depth_by_haiku_depth[h_depth]["correct"] += 1

            # Track disagreements
            if not is_type_correct or not is_depth_correct:
                disagreements.append({
                    "id": fact_id,
                    "fact_text": fact_text[:80].replace("\n", " "),
                    "db_type": db_type,
                    "haiku_type": h_type,
                    "opus_type": opus.get("fact_type_should_be", h_type) if not is_type_correct else h_type,
                    "db_depth": db_depth,
                    "haiku_depth": h_depth,
                    "opus_depth": opus.get("depth_should_be", h_depth) if not is_depth_correct else h_depth,
                    "type_disagree": not is_type_correct,
                    "depth_disagree": not is_depth_correct,
                    "notes": opus.get("notes", "")
                })

        # Print overall accuracy
        if type_total == 0:
            print("\nERROR: No facts were matched across Haiku + Opus. Check IDs.")
            return

        print(f"\nOverall fact_type accuracy (Opus judgment):       {type_correct}/{type_total} ({100*type_correct/type_total:.1f}%)")
        print(f"Overall commitment_depth accuracy (Opus judgment): {depth_correct}/{depth_total} ({100*depth_correct/depth_total:.1f}%)")

        # Per haiku-assigned-type breakdown: fact_type accuracy
        print("\n--- fact_type accuracy by Haiku's assigned type ---")
        for ht in sorted(type_by_haiku_type.keys()):
            stats = type_by_haiku_type[ht]
            pct = 100 * stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {ht:<14}: {stats['correct']}/{stats['total']} correct ({pct:.1f}%)")

        # Per haiku-assigned-type breakdown: commitment_depth accuracy
        print("\n--- commitment_depth accuracy by Haiku's assigned type ---")
        for ht in sorted(depth_by_haiku_type.keys()):
            stats = depth_by_haiku_type[ht]
            pct = 100 * stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {ht:<14}: {stats['correct']}/{stats['total']} correct ({pct:.1f}%)")

        # Per haiku-assigned-depth breakdown
        print("\n--- commitment_depth accuracy by Haiku's assigned depth ---")
        for hd in sorted(depth_by_haiku_depth.keys()):
            stats = depth_by_haiku_depth[hd]
            pct = 100 * stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {hd:<14}: {stats['correct']}/{stats['total']} correct ({pct:.1f}%)")

        # Confusion: what does Opus think the type should be when it disagrees?
        type_confusion = {}
        depth_confusion = {}
        for d in disagreements:
            if d["type_disagree"]:
                key = (d["haiku_type"], d["opus_type"])
                type_confusion[key] = type_confusion.get(key, 0) + 1
            if d["depth_disagree"]:
                key = (d["haiku_depth"], d["opus_depth"])
                depth_confusion[key] = depth_confusion.get(key, 0) + 1

        if type_confusion:
            print("\n--- fact_type confusion (Haiku -> Opus correction) ---")
            print(f"  {'Haiku assigned':<14} -> {'Opus says':<14} : Count")
            for (h, o), count in sorted(type_confusion.items(), key=lambda x: -x[1]):
                print(f"  {h:<14} -> {o:<14} : {count}")

        if depth_confusion:
            print("\n--- commitment_depth confusion (Haiku -> Opus correction) ---")
            print(f"  {'Haiku assigned':<14} -> {'Opus says':<14} : Count")
            for (h, o), count in sorted(depth_confusion.items(), key=lambda x: -x[1]):
                print(f"  {h:<14} -> {o:<14} : {count}")

        # Print all disagreements
        print("\n" + "=" * 110)
        print(f"DISAGREEMENTS ({len(disagreements)} facts where Opus disagrees with Haiku)")
        print("=" * 110)

        if not disagreements:
            print("\nNo disagreements! Haiku and Opus fully agree.")
        else:
            # Separate type and depth disagreements for clarity
            type_disagrees = [d for d in disagreements if d["type_disagree"]]
            depth_disagrees = [d for d in disagreements if d["depth_disagree"]]
            both_disagrees = [d for d in disagreements if d["type_disagree"] and d["depth_disagree"]]

            print(f"\n  Type only: {len(type_disagrees) - len(both_disagrees)}  |  Depth only: {len(depth_disagrees) - len(both_disagrees)}  |  Both: {len(both_disagrees)}")

            print(f"\n{'#':>3} | {'FACT TEXT':<80} | {'H_TYPE':<13} | {'O_TYPE':<13} | {'H_DEPTH':<11} | {'O_DEPTH':<11} | NOTES")
            print("-" * 170)

            for i, d in enumerate(disagreements, 1):
                h_type_disp = d["haiku_type"]
                o_type_disp = d["opus_type"] if d["type_disagree"] else "=="
                h_depth_disp = d["haiku_depth"]
                o_depth_disp = d["opus_depth"] if d["depth_disagree"] else "=="
                notes = d["notes"][:60] if d["notes"] else ""
                print(f"{i:>3} | {d['fact_text']:<80} | {h_type_disp:<13} | {o_type_disp:<13} | {h_depth_disp:<11} | {o_depth_disp:<11} | {notes}")

        # Cost summary
        print("\n" + "=" * 110)
        print("COST SUMMARY")
        print("=" * 110)
        print(f"  Haiku: {haiku_in:,} input + {haiku_out:,} output tokens = ${haiku_cost:.4f}")
        print(f"  Opus:  {opus_in:,} input + {opus_out:,} output tokens = ${opus_cost:.4f}")
        total_cost = haiku_cost + opus_cost
        print(f"  TOTAL: ${total_cost:.4f}")

        # Also show what it would cost at full-corpus scale (3,956 facts)
        scale_factor = 3956 / max(len(all_facts), 1)
        print(f"\n  Estimated full-corpus Haiku cost (3,956 facts): ${haiku_cost * scale_factor:.2f}")

    print("\nDone. Database was NOT modified.")


if __name__ == "__main__":
    main()
