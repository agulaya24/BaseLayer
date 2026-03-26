"""Clean up Ryan Holiday scraped posts: remove social buttons, comments, newsletter CTAs."""

import os
import re

SOURCE_DIR = os.path.join(os.path.dirname(__file__), "ryan_holiday_source")

# Patterns that indicate end of article content
CUTOFF_PATTERNS = [
    r"^Facebook$",
    r"^Twitter$",
    r"^Google\+$",
    r"^Pinterest$",
    r"^LinkedIn$",
    r"^\d+ Comments?$",
    r"^Get New Posts From Ryan Holiday",
    r"^Like this article\?",
    r"^Written by Ryan Holiday$",
    r"^Share this:",
    r"^Related$",
    r"^Filed Under:",
    r"^Tagged With:",
    r"^Thought Catalog$",
    r"^This post originally appeared",
    r"^Sign up for my reading",
    r"^If you enjoyed this",
    r"^Subscribe to",
]

CUTOFF_RE = re.compile("|".join(CUTOFF_PATTERNS), re.IGNORECASE)


def clean_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.split("\n\n")  # Split on double newlines (paragraph breaks)

    cleaned = []
    for para in lines:
        stripped = para.strip()
        if CUTOFF_RE.match(stripped):
            break
        cleaned.append(para)

    cleaned_text = "\n\n".join(cleaned).rstrip() + "\n"

    if cleaned_text != text:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(cleaned_text)
        return True
    return False


def main():
    files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".txt")]
    print(f"Processing {len(files)} files...")

    modified = 0
    removed = 0

    for fname in sorted(files):
        fpath = os.path.join(SOURCE_DIR, fname)

        if clean_file(fpath):
            modified += 1

        # Check if file is now too short (< 200 words after cleanup)
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()

        # First line is title, rest is body
        parts = text.split("\n\n", 1)
        body = parts[1] if len(parts) > 1 else ""
        word_count = len(body.split())

        if word_count < 150:
            os.remove(fpath)
            removed += 1
            print(f"  Removed (too short after cleanup, {word_count}w): {fname}")

    remaining = len(files) - removed
    print(f"\nDone. Modified: {modified}, Removed: {removed}, Remaining: {remaining}")


if __name__ == "__main__":
    main()
