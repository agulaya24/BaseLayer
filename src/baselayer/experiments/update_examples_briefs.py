"""
Update examples.ts brief arrays with C31 briefs.

The examples.ts BriefParagraph format is simpler (no relatedItems).

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/update_examples_briefs.py [--dry-run]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from brief_to_website import parse_brief, extract_sources, escape_ts_string, SUBJECTS

EXAMPLES_TS = "C:/Users/Aarik/Anthropic/baselayer-website/data/examples.ts"

# Map examples.ts id → SUBJECTS key
EXAMPLE_SUBJECTS = {
    "franklin": "franklin",
    "douglass": "douglass",
    "wollstonecraft": "wollstonecraft",
    "roosevelt": "roosevelt",
    "patents": "patents",
    "baselayer": "baselayer",
    "buffett": "buffett",
    "marks": "marks",
}


def format_inline_brief(paragraphs, indent=4):
    """Format paragraphs as inline brief array (no relatedItems)."""
    prefix = " " * indent
    lines = [f"{prefix}brief: ["]
    for p in paragraphs:
        sources_str = ", ".join(f'"{s}"' for s in p["sources"])
        lines.append(f"{prefix}  {{")
        lines.append(f'{prefix}    text: "{escape_ts_string(p["text"])}",')
        lines.append(f"{prefix}    sources: [{sources_str}],")
        lines.append(f"{prefix}  }},")
    lines.append(f"{prefix}],")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv

    with open(EXAMPLES_TS, "r", encoding="utf-8") as f:
        content = f.read()

    for example_id, subject_key in EXAMPLE_SUBJECTS.items():
        brief_path, _ = SUBJECTS[subject_key]
        if not os.path.exists(brief_path):
            print(f"  SKIP {example_id}: brief not found")
            continue

        with open(brief_path, "r", encoding="utf-8") as f:
            brief_text = f.read()

        paragraphs = parse_brief(brief_text)
        new_brief = format_inline_brief(paragraphs)

        # Find the brief array for this example
        # Look for: id: "example_id" ... brief: [ ... ],
        # We need to find the brief: [ ... ] block within this example's object
        id_pattern = rf'id:\s*"{re.escape(example_id)}"'
        id_match = re.search(id_pattern, content)
        if not id_match:
            print(f"  SKIP {example_id}: not found in examples.ts")
            continue

        # Find the brief array after this id
        brief_start = content.find("brief: [", id_match.end())
        if brief_start == -1:
            print(f"  SKIP {example_id}: no brief array found")
            continue

        # Make sure this brief belongs to this example (not the next one)
        next_id = content.find('id: "', id_match.end() + 1)
        if next_id != -1 and brief_start > next_id:
            print(f"  SKIP {example_id}: brief array belongs to next example")
            continue

        # Find the matching close of the brief array
        # Count brackets to find the correct closing ],
        depth = 0
        pos = brief_start + len("brief: [")
        depth = 1
        while pos < len(content) and depth > 0:
            if content[pos] == '[':
                depth += 1
            elif content[pos] == ']':
                depth -= 1
            pos += 1
        # pos is now just after the closing ]
        # Include the trailing comma if present
        if pos < len(content) and content[pos] == ',':
            pos += 1

        old_brief = content[brief_start:pos]

        if dry_run:
            print(f"  {example_id}: {len(paragraphs)} paragraphs (old: {len(old_brief)} chars -> new: {len(new_brief)} chars)")
        else:
            content = content[:brief_start] + new_brief + content[pos:]
            print(f"  {example_id}: updated ({len(old_brief)} -> {len(new_brief)} chars)")

    if not dry_run:
        with open(EXAMPLES_TS, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n  Saved: {EXAMPLES_TS}")


if __name__ == "__main__":
    main()
