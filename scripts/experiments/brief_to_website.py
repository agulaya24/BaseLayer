"""
Convert C31 brief_v4.md files to BriefParagraph[] TypeScript format for the website.

Parses the C31 markdown brief into structured paragraphs with source tags.

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/brief_to_website.py franklin
    python experiments/brief_to_website.py --all
"""

import os
import re
import sys


# Subject name → (brief path, website data variable name)
SUBJECTS = {
    "franklin": (
        "C:/Users/Aarik/Anthropic/subjects/franklin_memory/data/identity_layers/brief_v4.md",
        "franklinBrief",
    ),
    "douglass": (
        "C:/Users/Aarik/Anthropic/subjects/douglass_memory/data/identity_layers/brief_v4.md",
        "douglassBrief",
    ),
    "wollstonecraft": (
        "C:/Users/Aarik/Anthropic/subjects/wollstonecraft_memory/data/identity_layers/brief_v4.md",
        "wollstonecraftBrief",
    ),
    "roosevelt": (
        "C:/Users/Aarik/Anthropic/subjects/roosevelt_memory/data/identity_layers/brief_v4.md",
        "rooseveltBrief",
    ),
    "patents": (
        "C:/Users/Aarik/Anthropic/subjects/patent_memory/data/identity_layers/brief_v4.md",
        "patentsBrief",
    ),
    "buffett": (
        "C:/Users/Aarik/Anthropic/subjects/buffett_memory/data/identity_layers/brief_v4.md",
        "buffettBrief",
    ),
    "marks": (
        "C:/Users/Aarik/Anthropic/subjects/marks_memory/data/identity_layers/brief_v4.md",
        "marksBrief",
    ),
    "baselayer": (
        "C:/Users/Aarik/Anthropic/subjects/baselayer_meta/data/identity_layers/brief_v4.md",
        "baselayerBrief",
    ),
}


def extract_sources(text):
    """Extract source types (A, C, P, M) from citation codes in text."""
    sources = set()
    # Match [A1], [P3, A2], [C1-C3], [M1], etc.
    codes = re.findall(r'\[([A-Z][0-9]+(?:[-–][A-Z]?[0-9]+)?(?:\s*,\s*[A-Z][0-9]+(?:[-–][A-Z]?[0-9]+)?)*)\]', text)
    for code_group in codes:
        for code in re.split(r'\s*,\s*', code_group):
            if code[0] in ('A', 'C', 'P', 'M'):
                # Map M to C since website only has A, C, P
                sources.add('C' if code[0] == 'M' else code[0])
    return sorted(sources) if sources else ["A", "C", "P"]


def extract_related_items(text):
    """Extract all specific code references like A1, P3, C2, M1."""
    items = set()
    codes = re.findall(r'\[([A-Z][0-9]+(?:[-–][A-Z]?[0-9]+)?(?:\s*,\s*[A-Z][0-9]+(?:[-–][A-Z]?[0-9]+)?)*)\]', text)
    for code_group in codes:
        for code in re.split(r'\s*,\s*', code_group):
            code = code.strip()
            # Handle ranges like A1-A9 or A1-9
            range_match = re.match(r'([A-Z])(\d+)[-–]([A-Z]?)(\d+)', code)
            if range_match:
                prefix = range_match.group(1)
                start = int(range_match.group(2))
                end = int(range_match.group(4))
                for i in range(start, end + 1):
                    items.add(f"{prefix}{i}")
            elif re.match(r'^[A-Z]\d+$', code):
                items.add(code)
    return sorted(items) if items else None


def parse_brief(text):
    """Parse C31 brief markdown into BriefParagraph objects."""
    paragraphs = []

    # Remove frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()

    # Remove ## Injectable Block header
    text = re.sub(r'^##\s+Injectable Block\s*\n+', '', text, flags=re.MULTILINE)

    # Split into sections by bold headers (**SECTION NAME**)
    # Also handle ### headers
    section_pattern = r'(?:^|\n)\*\*([^*]+)\*\*\s*\n'
    sections = re.split(section_pattern, text)

    # sections alternates: [pre-text, header1, body1, header2, body2, ...]
    if len(sections) < 3:
        # No bold headers found — try splitting by paragraphs
        for para in text.split("\n\n"):
            para = para.strip()
            if para and not para.startswith("---"):
                paragraphs.append({
                    "text": para,
                    "sources": extract_sources(para),
                    "relatedItems": extract_related_items(para),
                })
        return paragraphs

    # Process section pairs
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if not body:
            continue

        # Check if body has sub-items (bold sub-patterns like **Name**: description)
        sub_items = re.findall(r'\*\*([^*]+)\*\*:?\s*(.+?)(?=\*\*[^*]+\*\*:?|$)', body, re.DOTALL)

        if sub_items and len(sub_items) > 1:
            # Multiple sub-items — combine into one paragraph per section
            combined = body.strip()
            # Clean up for readability — remove bold markers
            clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', combined)
            clean = clean.strip()
            paragraphs.append({
                "text": clean,
                "sources": extract_sources(body),
                "relatedItems": extract_related_items(body),
            })
        else:
            # Single body paragraph
            clean = body.strip()
            # Remove leading list markers
            clean = re.sub(r'^\d+\.\s+', '', clean)
            paragraphs.append({
                "text": clean,
                "sources": extract_sources(body),
                "relatedItems": extract_related_items(body),
            })

    return paragraphs


def escape_ts_string(s):
    """Escape a string for TypeScript template literal or regular string."""
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    return s


def format_ts(var_name, paragraphs):
    """Format paragraphs as TypeScript BriefParagraph[] export."""
    lines = [f"export const {var_name}: BriefParagraph[] = ["]
    for p in paragraphs:
        sources_str = ", ".join(f'"{s}"' for s in p["sources"])
        lines.append("  {")
        lines.append(f'    text: "{escape_ts_string(p["text"])}",')
        lines.append(f"    sources: [{sources_str}],")
        if p.get("relatedItems"):
            items_str = ", ".join(f'"{item}"' for item in p["relatedItems"])
            lines.append(f"    relatedItems: [{items_str}],")
        lines.append("  },")
    lines.append("];")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <subject> | --all")
        print(f"Available: {', '.join(SUBJECTS.keys())}")
        return

    if sys.argv[1] == "--all":
        subjects = list(SUBJECTS.keys())
    else:
        subjects = [sys.argv[1]]

    for subject in subjects:
        if subject not in SUBJECTS:
            print(f"Unknown subject: {subject}")
            continue

        path, var_name = SUBJECTS[subject]
        if not os.path.exists(path):
            print(f"Brief not found: {path}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        paragraphs = parse_brief(text)
        ts = format_ts(var_name, paragraphs)

        print(f"\n// === {subject.upper()} ({len(paragraphs)} paragraphs) ===")
        print(ts)
        print()


if __name__ == "__main__":
    main()
