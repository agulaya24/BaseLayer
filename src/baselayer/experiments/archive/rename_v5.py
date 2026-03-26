"""
Rename brief_v4.md -> brief_v5.md and brief_v4_clean.md -> brief_v5_clean.md
for all subjects. Updates frontmatter to say v5.
"""

import os
import re

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

for name, subject_dir in ALL_SUBJECTS:
    layers_dir = os.path.join(subject_dir, "data", "identity_layers")

    # Rename cited version
    old_cited = os.path.join(layers_dir, "brief_v4.md")
    new_cited = os.path.join(layers_dir, "brief_v5.md")
    if os.path.exists(old_cited):
        with open(old_cited, "r", encoding="utf-8") as f:
            content = f.read()
        # Only rename C31 briefs (not old V4 production ones which are backed up)
        if "compose_prompt: C31" in content:
            content = content.replace("compose_prompt: C31", "compose_prompt: V5 (C31 + citation strip)")
            with open(new_cited, "w", encoding="utf-8") as f:
                f.write(content)
            os.remove(old_cited)
            print(f"  {name}: brief_v4.md -> brief_v5.md (cited)")

    # Rename clean version
    old_clean = os.path.join(layers_dir, "brief_v4_clean.md")
    new_clean = os.path.join(layers_dir, "brief_v5_clean.md")
    if os.path.exists(old_clean):
        with open(old_clean, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("compose_prompt: C31", "compose_prompt: V5 (C31 + citation strip)")
        with open(new_clean, "w", encoding="utf-8") as f:
            f.write(content)
        os.remove(old_clean)
        print(f"  {name}: brief_v4_clean.md -> brief_v5_clean.md (clean)")
