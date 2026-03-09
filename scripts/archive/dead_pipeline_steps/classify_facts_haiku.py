"""
Classify fact_type and commitment_depth for active personal-scope facts using Haiku.
Batches 100 facts per API call. Updates memory_facts table directly.

D-043: fact_type feeds three-layer identity architecture routing.
D-044: Only classifies personal-scope facts.

Usage: python scripts/classify_facts_haiku.py [--dry-run] [--limit N] [--batch-size N]
"""

import contextlib
import json
import time
import sys
import os

# Add scripts dir to path for config import
sys.path.insert(0, os.path.dirname(__file__))
from config import DATABASE_FILE, VALID_FACT_TYPES, VALID_COMMITMENT_DEPTHS, get_db, LLM_PROVIDER_CONFIG

MODEL = LLM_PROVIDER_CONFIG["classification"]

BATCH_SIZE = 100

# Variant B (examples-heavy) — selected by Collective review Session 36
# Generalized for multi-user (Session 38): examples are person-agnostic
CLASSIFY_PROMPT = """Classify each fact about a person.

**fact_type** (what kind of knowledge):
biographical — facts about who they are, what happened to them, relationships, job history, one-off actions
  e.g. "Founded a startup in 2021" "Married with two children" "Former military officer" "Lives in Chicago"
behavioral — RECURRING patterns of how they characteristically act, react, or operate
  e.g. "Spirals after breaking own rules" "Builds frameworks before adopting others" "Procrastinates under pressure"
positional — what they explicitly believe, argue for, or evaluate as true/important
  e.g. "Believes remote work is more productive" "Values transparency over diplomacy" "Thinks AI regulation is premature"
preference — what they like, are interested in, choose, or gravitate toward
  e.g. "Prefers tea over coffee" "Interested in quantum computing" "Likes minimalist design" "Uses Linux"

**Disambiguation rules (apply these BEFORE classifying):**
- "Interested in X" → **preference** if it's a stable/general interest ("interested in quantum computing"). But if it describes a one-time task or inquiry in a specific context ("interested in motherboard compatibility for chosen processors"), that's **biographical**.
- "Considering X" / "planning to X" / "looking to X" → **biographical** (an action they're taking), NOT behavioral or positional
- "Skilled at X" / "adept at X" / "experienced in X" → **biographical** (a capability), NOT behavioral
- Personality traits ("ambitious", "creative", "resourceful", "detail-oriented") → **biographical**, NOT behavioral
- behavioral requires a RECURRING pattern ("tends to", "always", "characteristically"), not a one-time action or a trait
- positional requires an evaluative STANCE ("believes", "values", "argues", "thinks"), not just interest or activity

**commitment_depth** (how strongly held):
factual — not a belief; events, identifiers, relationships, observed capabilities, activities
preference — soft, could change easily
position — argued for, but would revise with evidence
conviction — core to who they are, would not change without fundamental shift

**Disambiguation rules:**
- Observed skills/competencies ("good at X", "skilled at X") → **factual**, not conviction
- Observed behavioral patterns ("tends to X", "struggles with X") → **factual**, not position
- conviction requires something the person deeply identifies with, not just something they're good at

Return JSON array: [{"id": "...", "fact_type": "...", "commitment_depth": "..."}]

Facts:
"""


def classify_batch(facts):
    """Send a batch of facts to Haiku for classification.

    Uses centralized api_client for singleton client, retry, and logging.
    """
    from api_client import call_api

    # Sanitize fact text: remove problematic characters, truncate long facts
    lines = []
    for fid, text in facts:
        clean = text.replace('"', "'").replace("\n", " ").replace("\r", " ")[:200]
        lines.append(f'[{fid}] {clean}')
    fact_list = "\n".join(lines)

    response = call_api(
        model=MODEL,
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": CLASSIFY_PROMPT + "<facts>\n" + fact_list + "\n</facts>"
        }],
        caller="classify_facts",
    )

    text = response.content[0].text.strip()

    # Extract JSON from response (may be wrapped in markdown code blocks)
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        print("  WARNING: Failed to parse JSON response, skipping batch")
        print("  Response: [%d chars, parse failed]" % len(text))
        return [], 0, 0

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    return results, input_tokens, output_tokens


def normalize_fact_type(ft):
    ft = ft.lower().strip()
    if ft in VALID_FACT_TYPES:
        return ft
    return "unclassified"


def normalize_commitment_depth(cd):
    cd = cd.lower().strip()
    if cd in VALID_COMMITMENT_DEPTHS:
        return cd
    return "unclassified"


def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    batch_size = BATCH_SIZE

    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        if arg == "--batch-size" and i + 1 < len(sys.argv):
            batch_size = int(sys.argv[i + 1])

    with contextlib.closing(get_db()) as conn:
        cur = conn.cursor()

        # Get active personal-scope facts that haven't been classified yet
        query = """
            SELECT id, fact_text FROM memory_facts
            WHERE superseded_by IS NULL
            AND scope = 'personal'
            AND (fact_type = 'unclassified' OR fact_type IS NULL)
            ORDER BY id
        """
        params = ()
        if limit:
            query += " LIMIT ?"
            params = (limit,)

        cur.execute(query, params)
        facts = cur.fetchall()

        print("Facts to classify: %d" % len(facts))
        if dry_run:
            print("DRY RUN — no database updates")

        total_input_tokens = 0
        total_output_tokens = 0
        total_classified = 0
        total_batches = (len(facts) + batch_size - 1) // batch_size

        for batch_idx in range(0, len(facts), batch_size):
            batch = facts[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            print("Batch %d/%d (%d facts)..." % (batch_num, total_batches, len(batch)))

            try:
                results, input_tokens, output_tokens = classify_batch(batch)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
            except Exception as e:
                print("  ERROR: %s" % str(e))
                time.sleep(2)
                continue

            classified = 0
            for r in results:
                fact_id = r.get("id", "")
                ft = normalize_fact_type(r.get("fact_type", ""))
                cd = normalize_commitment_depth(r.get("commitment_depth", ""))

                if ft == "unclassified" and cd == "unclassified":
                    continue

                if not dry_run:
                    cur.execute("""
                        UPDATE memory_facts SET fact_type = ?, commitment_depth = ?
                        WHERE id = ?
                    """, (ft, cd, fact_id))
                classified += 1

            total_classified += classified

            if not dry_run:
                conn.commit()

            print("  Classified: %d/%d | Tokens: %d in, %d out" % (
                classified, len(batch), input_tokens, output_tokens))

            # Brief pause to avoid rate limits
            time.sleep(0.5)

        # Cost calculation (Haiku pricing)
        input_cost = (total_input_tokens / 1e6) * 0.80
        output_cost = (total_output_tokens / 1e6) * 4.00
        total_cost = input_cost + output_cost

        print("\n=== SUMMARY ===")
        print("Total classified: %d / %d" % (total_classified, len(facts)))
        print("Total tokens: %d input, %d output" % (total_input_tokens, total_output_tokens))
        print("Estimated cost: $%.4f (input $%.4f + output $%.4f)" % (
            total_cost, input_cost, output_cost))

        if not dry_run:
            # Print distribution
            cur.execute("""
                SELECT fact_type, COUNT(*) FROM memory_facts
                WHERE superseded_by IS NULL AND scope = 'personal'
                GROUP BY fact_type ORDER BY COUNT(*) DESC
            """)
            print("\nfact_type distribution:")
            for row in cur.fetchall():
                print("  %s: %d" % (row[0] or "NULL", row[1]))

            cur.execute("""
                SELECT commitment_depth, COUNT(*) FROM memory_facts
                WHERE superseded_by IS NULL AND scope = 'personal'
                GROUP BY commitment_depth ORDER BY COUNT(*) DESC
            """)
            print("\ncommitment_depth distribution:")
            for row in cur.fetchall():
                print("  %s: %d" % (row[0] or "NULL", row[1]))


if __name__ == "__main__":
    main()
