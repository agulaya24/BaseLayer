"""
Recompose all subjects with C31 prompt (D-080).

C31 = C28 (rubric awareness + temporal + cannot predict) + C27 (format freedom).
Collective chose C31 unanimously with high confidence over C28.

Replaces brief_v4.md for each subject. Backs up old brief as brief_v4_pre_c31.md.

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/recompose_c31.py [--dry-run] [--subjects franklin,buffett]
"""

import json
import os
import sys
import time
import shutil
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import get_anthropic_client

OPUS = "claude-opus-4-20250514"

C31_PROMPT = """You are writing a behavioral brief about a person. An LLM will read this brief before every interaction with them.

Your brief will be scored on four primitives of understanding how to work with a human:

PROVENANCE (30%): Every claim traces to source evidence [A1], [P3], [C2]. Cross-layer [Px, Ay] where connected. Fabricated content = failure.

BEHAVIORAL CHANGE (30%): Every sentence must change LLM behavior. Directives. Communication guidance [M1]. Mode-switching. Information without behavioral consequence is noise.

EPISTEMIC CALIBRATION (20%): The LLM must know boundaries of what it knows:
- When patterns activate AND when they don't (FP warnings from source PREDICTIONS only — never fabricate)
- [CONTESTED] and [THIN IN] tags preserved from source
- TEMPORAL AWARENESS: These patterns were extracted from a specific time window. They may evolve. Flag any patterns that appear situational vs stable.
- EXPLICIT GAPS: End the brief with a "CANNOT PREDICT" section listing 3-5 specific situations or contexts where the brief provides NO guidance. The LLM should know where it's flying blind.

SIGNAL DENSITY (20%): Every sentence adds new understanding. No redundancy. ~3,500-4,500 chars optimal.

You have complete creative freedom on format and structure. Choose whatever organization best captures this specific person. Cover all source codes (A, P, M, C). Start with ## Injectable Block.

{layers}"""

# All subjects with v4 layers
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


def load_layer(subject_dir, filename):
    path = os.path.join(subject_dir, "data", "identity_layers", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def format_layers(subject_dir):
    a = load_layer(subject_dir, "anchors_v4.md")
    c = load_layer(subject_dir, "core_v4.md")
    p = load_layer(subject_dir, "predictions_v4.md")
    parts = []
    if a:
        parts.append(f"=== ANCHORS ===\n{a}")
    if c:
        parts.append(f"=== CORE ===\n{c}")
    if p:
        parts.append(f"=== PREDICTIONS ===\n{p}")
    return "\n\n".join(parts)


def compose_brief(client, layers_text):
    prompt = C31_PROMPT.format(layers=layers_text)
    response = client.messages.create(
        model=OPUS,
        max_tokens=1500,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    cost = (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000
    return text, cost, response.usage.input_tokens, response.usage.output_tokens


def main():
    parser = argparse.ArgumentParser(description="Recompose all subjects with C31")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without calling API")
    parser.add_argument("--subjects", default=None, help="Comma-separated subject names to recompose (default: all)")
    args = parser.parse_args()

    subjects = ALL_SUBJECTS
    if args.subjects:
        names = [n.strip() for n in args.subjects.split(",")]
        subjects = [(n, p) for n, p in ALL_SUBJECTS if n in names]
        if not subjects:
            print(f"No matching subjects for: {args.subjects}")
            print(f"Available: {', '.join(n for n, _ in ALL_SUBJECTS)}")
            return

    client = get_anthropic_client() if not args.dry_run else None
    total_cost = 0.0
    results = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for name, subject_dir in subjects:
        layers_dir = os.path.join(subject_dir, "data", "identity_layers")
        brief_path = os.path.join(layers_dir, "brief_v4.md")
        backup_path = os.path.join(layers_dir, "brief_v4_pre_c31.md")

        # Check layers exist
        layers_text = format_layers(subject_dir)
        if not layers_text:
            print(f"  SKIP {name}: no v4 layers found")
            continue

        print(f"\n{'='*50}")
        print(f"  {name.upper()}")
        print(f"{'='*50}")
        print(f"  Layers: {len(layers_text):,} chars")

        if args.dry_run:
            print(f"  [DRY RUN] Would compose and save to {brief_path}")
            continue

        # Backup existing brief
        if os.path.exists(brief_path) and not os.path.exists(backup_path):
            shutil.copy2(brief_path, backup_path)
            print(f"  Backed up existing brief")

        # Compose
        start = time.time()
        brief_text, cost, in_tok, out_tok = compose_brief(client, layers_text)
        elapsed = time.time() - start
        total_cost += cost

        print(f"  Output: {len(brief_text):,} chars, {out_tok} tokens")
        print(f"  Cost: ${cost:.3f} ({elapsed:.1f}s)")

        # Save with frontmatter
        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(f"---\ncompose_prompt: C31\ngenerated: {timestamp}\n---\n\n{brief_text}\n")
        print(f"  Saved: {brief_path}")

        results.append({
            "subject": name,
            "chars": len(brief_text),
            "cost": round(cost, 4),
            "time": round(elapsed, 1),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
        })

    if not args.dry_run and results:
        print(f"\n{'='*50}")
        print(f"  RECOMPOSE COMPLETE")
        print(f"{'='*50}")
        print(f"  Subjects: {len(results)}")
        print(f"  Total cost: ${total_cost:.3f}")
        print(f"  Avg chars: {sum(r['chars'] for r in results) / len(results):,.0f}")

        # Save results
        results_path = os.path.join(os.path.dirname(__file__), "recompose_c31_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": timestamp, "prompt": "C31", "results": results, "total_cost": round(total_cost, 4)}, f, indent=2)
        print(f"  Results: {results_path}")


if __name__ == "__main__":
    main()
