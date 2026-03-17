"""
Test the revised Haiku classification prompt against 80 random facts (20 per fact_type).
Read-only — does NOT update the database.
Compares Haiku's new classifications to existing database values.
"""

import contextlib
import sqlite3
import json
import time
import sys
import os
import anthropic

# Import the prompt and normalization from the actual script
sys.path.insert(0, os.path.dirname(__file__))
from classify_facts_haiku import CLASSIFY_PROMPT, MODEL, normalize_fact_type, normalize_commitment_depth

from config import DATABASE_FILE

CLIENT = None  # Lazy init — avoid crash on import without API key


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


def classify_batch(facts_for_api):
    """Send facts to Haiku for classification using the revised prompt."""
    lines = []
    for fid, text in facts_for_api:
        clean = text.replace('"', "'").replace("\n", " ").replace("\r", " ")[:200]
        lines.append(f'[{fid}] {clean}')
    fact_list = "\n".join(lines)

    response = CLIENT.messages.create(
        model=MODEL,
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
        print("  WARNING: Failed to parse JSON response")
        print("  Response preview: %s" % text[:500])
        return {}, response.usage.input_tokens, response.usage.output_tokens

    # Build lookup dict by id (IDs are UUIDs as strings)
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


def main():
    global CLIENT
    from api_client import get_anthropic_client
    CLIENT = get_anthropic_client()

    print("=" * 100)
    print("HAIKU CLASSIFICATION PROMPT TEST — 80 Random Facts (20 per type)")
    print("Model: %s" % MODEL)
    print("=" * 100)

    # Fetch sample facts
    print("\nSampling facts from database...")
    with contextlib.closing(sqlite3.connect(str(DATABASE_FILE))) as conn:
        all_facts = fetch_sample_facts(conn)
    print(f"  Total sampled: {len(all_facts)}")

    # Prepare for API call
    facts_for_api = [(row[0], row[1]) for row in all_facts]

    # Send to Haiku (single batch since 80 < 100)
    print("\nSending %d facts to Haiku..." % len(facts_for_api))
    haiku_results, input_tokens, output_tokens = classify_batch(facts_for_api)
    print(f"  Received {len(haiku_results)} classifications")
    print(f"  Tokens: {input_tokens} input, {output_tokens} output")

    # Cost calculation (Haiku pricing: $0.80/M input, $4.00/M output)
    input_cost = (input_tokens / 1e6) * 0.80
    output_cost = (output_tokens / 1e6) * 4.00
    total_cost = input_cost + output_cost
    print(f"  Cost: ${total_cost:.4f}")

    # Compare results
    print("\n" + "=" * 100)
    print("DETAILED RESULTS")
    print("=" * 100)
    print(f"{'ID':>6} | {'FACT TEXT':<80} | {'CUR_TYPE':<14} | {'HAI_TYPE':<14} | {'TM':<3} | {'CUR_DEPTH':<12} | {'HAI_DEPTH':<12} | {'DM':<3}")
    print("-" * 160)

    # Tracking
    type_matches = 0
    type_total = 0
    depth_matches = 0
    depth_total = 0
    type_changes = 0
    depth_changes = 0

    # Per-type tracking
    type_accuracy = {}  # {current_type: {total: N, match: N}}
    depth_accuracy = {}  # {current_depth: {total: N, match: N}}

    # Confusion tracking
    type_confusion = {}  # {(current, haiku): count}
    depth_confusion = {}

    missing_ids = []

    for row in all_facts:
        fact_id, fact_text, cur_type, cur_depth = row

        if fact_id not in haiku_results:
            missing_ids.append(fact_id)
            continue

        haiku = haiku_results[fact_id]
        hai_type = haiku["fact_type"]
        hai_depth = haiku["commitment_depth"]

        type_match = "Y" if cur_type == hai_type else "N"
        depth_match = "Y" if cur_depth == hai_depth else "N"

        # Truncate fact text for display
        display_text = fact_text[:80].replace("\n", " ")

        print(f"{fact_id:>6} | {display_text:<80} | {cur_type:<14} | {hai_type:<14} | {type_match:<3} | {cur_depth or 'NULL':<12} | {hai_depth:<12} | {depth_match:<3}")

        # Accumulate stats
        type_total += 1
        if cur_type == hai_type:
            type_matches += 1
        else:
            type_changes += 1

        depth_total += 1
        if cur_depth == hai_depth:
            depth_matches += 1
        else:
            depth_changes += 1

        # Per-type accuracy
        if cur_type not in type_accuracy:
            type_accuracy[cur_type] = {"total": 0, "match": 0}
        type_accuracy[cur_type]["total"] += 1
        if cur_type == hai_type:
            type_accuracy[cur_type]["match"] += 1

        # Per-depth accuracy
        cd = cur_depth or "NULL"
        if cd not in depth_accuracy:
            depth_accuracy[cd] = {"total": 0, "match": 0}
        depth_accuracy[cd]["total"] += 1
        if cur_depth == hai_depth:
            depth_accuracy[cd]["match"] += 1

        # Confusion tracking
        type_key = (cur_type, hai_type)
        type_confusion[type_key] = type_confusion.get(type_key, 0) + 1
        depth_key = (cur_depth or "NULL", hai_depth)
        depth_confusion[depth_key] = depth_confusion.get(depth_key, 0) + 1

    # Print summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    if missing_ids:
        print(f"\nWARNING: {len(missing_ids)} facts not returned by Haiku: {missing_ids[:10]}{'...' if len(missing_ids) > 10 else ''}")

    if type_total == 0:
        print("\nERROR: No facts were matched. Check ID format.")
        return

    print(f"\nOverall fact_type agreement:       {type_matches}/{type_total} ({100*type_matches/type_total:.1f}%)")
    print(f"Overall commitment_depth agreement: {depth_matches}/{depth_total} ({100*depth_matches/depth_total:.1f}%)")
    print(f"\nFacts with CHANGED fact_type:       {type_changes}/{type_total}")
    print(f"Facts with CHANGED commitment_depth: {depth_changes}/{depth_total}")

    print("\n--- Fact Type Agreement by Current Type ---")
    for ft in sorted(type_accuracy.keys()):
        stats = type_accuracy[ft]
        pct = 100 * stats["match"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {ft:<14}: {stats['match']}/{stats['total']} ({pct:.1f}%)")

    print("\n--- Commitment Depth Agreement by Current Depth ---")
    for cd in sorted(depth_accuracy.keys()):
        stats = depth_accuracy[cd]
        pct = 100 * stats["match"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {cd:<14}: {stats['match']}/{stats['total']} ({pct:.1f}%)")

    # Confusion matrix for fact_type (only mismatches)
    print("\n--- Fact Type Confusion (mismatches only) ---")
    print(f"  {'Current':<14} -> {'Haiku':<14} : Count")
    for (cur, hai), count in sorted(type_confusion.items(), key=lambda x: -x[1]):
        if cur != hai:
            print(f"  {cur:<14} -> {hai:<14} : {count}")

    print("\n--- Commitment Depth Confusion (mismatches only) ---")
    print(f"  {'Current':<14} -> {'Haiku':<14} : Count")
    for (cur, hai), count in sorted(depth_confusion.items(), key=lambda x: -x[1]):
        if cur != hai:
            print(f"  {cur:<14} -> {hai:<14} : {count}")

    # Print facts where classification changed — these are the interesting ones
    print("\n" + "=" * 100)
    print("CHANGED CLASSIFICATIONS (potential prompt improvements or errors)")
    print("=" * 100)

    changed_facts = []
    for row in all_facts:
        fact_id, fact_text, cur_type, cur_depth = row
        if fact_id not in haiku_results:
            continue
        haiku = haiku_results[fact_id]
        hai_type = haiku["fact_type"]
        hai_depth = haiku["commitment_depth"]

        if cur_type != hai_type or cur_depth != hai_depth:
            changed_facts.append((fact_id, fact_text, cur_type, hai_type, cur_depth, hai_depth))

    if not changed_facts:
        print("\nNo classifications changed!")
    else:
        print(f"\n{len(changed_facts)} facts with changed classifications:\n")
        for fact_id, fact_text, cur_type, hai_type, cur_depth, hai_depth in changed_facts:
            type_changed = " [TYPE CHANGED]" if cur_type != hai_type else ""
            depth_changed = " [DEPTH CHANGED]" if cur_depth != hai_depth else ""
            print(f"  Fact {fact_id}: {fact_text[:120]}")
            if cur_type != hai_type:
                print(f"    fact_type:       {cur_type} -> {hai_type}{type_changed}")
            if cur_depth != hai_depth:
                print(f"    commitment_depth: {cur_depth} -> {hai_depth}{depth_changed}")
            print()

    print("Done. Database was NOT modified.")


if __name__ == "__main__":
    main()
