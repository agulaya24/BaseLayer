"""
Update website data files with C31 briefs.

Reads each subject's brief_v4.md, converts to BriefParagraph[], and replaces
the existing brief array in the corresponding website .ts data file.

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/update_website_briefs.py [--dry-run]
"""

import os
import re
import sys

# Import the parser from brief_to_website
sys.path.insert(0, os.path.dirname(__file__))
from brief_to_website import parse_brief, format_ts, SUBJECTS

WEBSITE_DATA_DIR = "C:/Users/Aarik/Anthropic/baselayer-website/data"

# Map subject → website data file
WEBSITE_FILES = {
    "franklin": "franklin.ts",
    "douglass": "douglass.ts",
    "wollstonecraft": "wollstonecraft.ts",
    "roosevelt": "roosevelt.ts",
    "patents": "patents.ts",
    "buffett": "buffett.ts",
    "marks": "marks.ts",
    "baselayer": "baselayer.ts",
}


def replace_brief_in_file(filepath, var_name, new_brief_ts):
    """Replace the existing brief array in a .ts file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the existing brief export and replace it
    # Pattern: export const varName: BriefParagraph[] = [ ... ];
    pattern = rf'export const {var_name}: BriefParagraph\[\] = \[.*?\];'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        # Try without type annotation
        pattern = rf'export const {var_name} = \[.*?\];'
        match = re.search(pattern, content, re.DOTALL)

    if not match:
        return False, f"Could not find {var_name} in {filepath}"

    new_content = content[:match.start()] + new_brief_ts + content[match.end():]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True, f"Updated {var_name} ({match.end() - match.start()} chars -> {len(new_brief_ts)} chars)"


def main():
    dry_run = "--dry-run" in sys.argv

    for subject, ts_file in WEBSITE_FILES.items():
        brief_path, var_name = SUBJECTS[subject]
        ts_path = os.path.join(WEBSITE_DATA_DIR, ts_file)

        if not os.path.exists(brief_path):
            print(f"  SKIP {subject}: brief not found")
            continue
        if not os.path.exists(ts_path):
            print(f"  SKIP {subject}: website file not found ({ts_path})")
            continue

        with open(brief_path, "r", encoding="utf-8") as f:
            brief_text = f.read()

        paragraphs = parse_brief(brief_text)
        new_ts = format_ts(var_name, paragraphs)

        if dry_run:
            print(f"  {subject}: {len(paragraphs)} paragraphs -> {ts_file} ({var_name})")
        else:
            ok, msg = replace_brief_in_file(ts_path, var_name, new_ts)
            status = "OK" if ok else "FAIL"
            print(f"  {subject}: [{status}] {msg}")


if __name__ == "__main__":
    main()
