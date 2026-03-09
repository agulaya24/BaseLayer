"""
Extract genuine epistemic anchors from conviction-depth identity facts.

Queries the database for conviction-level identity facts, sends them to Haiku
for anchor identification, and saves candidates for human review.

Usage:
  python scripts/extract_anchors.py
  baselayer extract-anchors  (future CLI integration)
"""

import contextlib
import sqlite3
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import DATABASE_FILE

ANCHOR_PROMPT = """Below are {count} facts about a person, all classified as conviction-level identity facts. \
Identify the 15-30 GENUINE epistemic anchors -- foundational premises this person reasons FROM across their entire life.

An epistemic anchor is NOT:
- A career preference ('interested in AI companies')
- A domain-specific skill ('good at translating technical concepts')
- A job search criterion ('values autonomy')
- A trading rule ('wait for confluence')
- A personality trait stated generically ('high emotional intelligence')

An epistemic anchor IS:
- A foundational belief that shapes how they approach EVERYTHING: work, relationships, self-evaluation, learning
- Something where if an AI didn't know this, it would fundamentally misread this person
- A premise so deep that it constrains reasoning before any specific topic comes up

From the facts below, identify the 15-30 genuine cross-life epistemic anchors. \
Group redundant expressions of the same anchor. For each, write one clean sentence.

Return JSON: [{{"anchor": "clean sentence", "source_facts": [fact numbers], "why": "why cross-domain"}}]

Facts:
{fact_block}"""


def main():
    from api_client import get_anthropic_client

    client = get_anthropic_client()

    with contextlib.closing(sqlite3.connect(str(DATABASE_FILE))) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT fact_text FROM memory_facts
            WHERE superseded_by IS NULL AND scope = 'personal'
            AND commitment_depth = 'conviction' AND knowledge_tier = 'identity'
            ORDER BY fact_text
        """)
        facts = [r[0][:200].replace('"', "'") for r in cur.fetchall()]

    if not facts:
        print("No conviction-level identity facts found. Run classification first.")
        return

    fact_block = "\n".join(f"{i+1}. {f}" for i, f in enumerate(facts))
    prompt = ANCHOR_PROMPT.format(count=len(facts), fact_block=fact_block)

    print(f"Extracting anchors from {len(facts)} conviction-level identity facts...")

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    text = resp.content[0].text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1

    input_cost = (resp.usage.input_tokens / 1e6) * 0.80
    output_cost = (resp.usage.output_tokens / 1e6) * 4.00
    print(f"Tokens: {resp.usage.input_tokens} in / {resp.usage.output_tokens} out")
    print(f"Cost: ${input_cost + output_cost:.4f}")
    print()

    if start >= 0 and end > start:
        results = json.loads(text[start:end])
        print(f"Anchors identified: {len(results)}")
        print()
        for i, r in enumerate(results):
            print(f"{i + 1}. {r['anchor']}")
            print(f"   Why: {r.get('why', '')}")
            sources = r.get("source_facts", [])
            print(f"   Sources: {sources[:5]}")
            print()

        # Save results
        output_path = DATABASE_FILE.parent / "anchor_candidates.json"
        with open(str(output_path), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Saved to {output_path}")
    else:
        print("PARSE FAILED")
        print(text[:500])


if __name__ == "__main__":
    main()
