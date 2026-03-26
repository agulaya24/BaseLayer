"""
Strip citation markers from brief_v4.md files, saving clean versions for injection.

Keeps brief_v4.md (cited, for audit). Creates brief_v4_clean.md (stripped, for serving).

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/strip_citations.py [--dry-run]
"""

import os
import re
import sys

ALL_SUBJECTS = [
    ("franklin", "C:/Users/Aarik/Anthropic/subjects/franklin_memory"),
    ("buffett", "C:/Users/Aarik/Anthropic/subjects/buffett_memory"),
    ("aarik", "C:/Users/Aarik/Anthropic/memory_system_v4"),
    ("douglass", "C:/Users/Aarik/Anthropic/subjects/douglass_memory"),
    ("marks", "C:/Users/Aarik/Anthropic/subjects/marks_memory"),
    ("bavani", "C:/Users/Aarik/Anthropic/subjects/bavani_memory"),
    ("patent", "C:/Users/Aarik/Anthropic/subjects/patent_memory"),
    ("lesswrong", "C:/Users/Aarik/Anthropic/subjects/lesswrong_clt"),
    ("baselayer_meta", "C:/Users/Aarik/Anthropic/subjects/baselayer_meta"),
    ("paul_graham", "C:/Users/Aarik/Anthropic/subjects/paul_graham"),
    ("roosevelt", "C:/Users/Aarik/Anthropic/subjects/roosevelt_memory"),
    ("wollstonecraft", "C:/Users/Aarik/Anthropic/subjects/wollstonecraft_memory"),
]

# Matches [A1], [P3, A2], [C1-C3], [M1], [A1-12], [CONTESTED], [THIN IN: ...], etc.
CITATION_RE = re.compile(
    r'\s*\['
    r'(?:'
    r'[APCM]\d+(?:[-\u2013][A-Z]?\d+)?'  # Single code or range: A1, A1-9, A1-A9
    r'(?:\s*,\s*[APCM]\d+(?:[-\u2013][A-Z]?\d+)?)*'  # Additional codes: , P3, A2
    r'|CONTESTED'
    r'|THIN IN[^]]*'
    r')'
    r'\]'
)

# Full provenance line like **PROVENANCE**: [A1-12] from ANCHORS...
PROVENANCE_LINE_RE = re.compile(r'^\*\*PROVENANCE\*\*:.*$\n?', re.MULTILINE)


def strip_citations(text):
    """Remove all citation markers from brief text."""
    # Remove full provenance header lines
    text = PROVENANCE_LINE_RE.sub('', text)
    # Remove inline citations
    text = CITATION_RE.sub('', text)
    # Clean up double spaces left behind
    text = re.sub(r'  +', ' ', text)
    # Clean up empty parentheses or trailing spaces before punctuation
    text = re.sub(r' +([.,;:])', r'\1', text)
    # Clean up lines that are now empty
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text


def main():
    dry_run = "--dry-run" in sys.argv

    for name, subject_dir in ALL_SUBJECTS:
        brief_path = os.path.join(subject_dir, "data", "identity_layers", "brief_v4.md")
        clean_path = os.path.join(subject_dir, "data", "identity_layers", "brief_v4_clean.md")

        if not os.path.exists(brief_path):
            continue

        with open(brief_path, "r", encoding="utf-8") as f:
            cited = f.read()

        clean = strip_citations(cited)
        diff = len(cited) - len(clean)

        if dry_run:
            print(f"  {name}: {len(cited)} -> {len(clean)} chars (-{diff})")
        else:
            with open(clean_path, "w", encoding="utf-8") as f:
                f.write(clean)
            print(f"  {name}: saved {clean_path} (-{diff} chars)")


if __name__ == "__main__":
    main()
