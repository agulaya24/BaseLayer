"""Quick cleanup of boilerplate from Morgan Housel scraped files."""
import os
import re

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "morgan_housel_source")
cleaned = 0
for f in os.listdir(src):
    if not f.endswith(".txt"):
        continue
    path = os.path.join(src, f)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    original = text
    text = re.sub(r"\n\nbyMorgan Housel@morganhousel\n", "\n", text)
    text = re.sub(r"\n\nby Morgan Housel\n", "\n", text)
    text = re.sub(r"\n\nCopy Link\n", "\n", text)
    text = re.sub(r"\n\n@morganhousel\n", "\n", text)

    if text != original:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        cleaned += 1

print(f"Cleaned boilerplate from {cleaned} files")
