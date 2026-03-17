#!/usr/bin/env python3
"""Test 3 compose prompt variations on Franklin.

Variations:
  V1: FALSE POSITIVE GUARDS — preserve per-pattern false positive warnings as inline qualifiers
  V2: TENSION-INDEXED DIRECTIVES — replace closing tensions with tension-action pairs
  V3: NO AVAILABILITY INDEX — remove the availability index entirely

Each variation modifies the compose prompt, runs Opus composition on Franklin's
existing layers, and saves the output for comparison.

Usage:
    set MEMORY_SYSTEM_ROOT=path/to/subjects/franklin_memory
    python scripts/test_compose_variations.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Setup paths
_HOME = Path.home() / "Anthropic"
MEMORY_ROOT = Path(os.environ.get("MEMORY_SYSTEM_ROOT", str(_HOME / "subjects" / "franklin_memory")))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["MEMORY_SYSTEM_ROOT"] = str(MEMORY_ROOT)

from config import ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE, IDENTITY_LAYERS_DIR
from api_client import get_anthropic_client
import agent_pipeline

# ── Read Franklin's existing layers ──────────────────────────────────────────

def read_layers():
    layer_texts = {}
    for name, path in [("anchors", ANCHORS_LAYER_FILE),
                       ("core", CORE_LAYER_FILE),
                       ("predictions", PREDICTIONS_LAYER_FILE)]:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            marker = "## Injectable Block"
            idx = content.find(marker)
            if idx >= 0:
                layer_texts[name] = content[idx + len(marker):].strip()
            else:
                sep = content.find("\n---\n")
                layer_texts[name] = content[sep + 5:].strip() if sep >= 0 else content.strip()
    return layer_texts


def read_facts():
    """Read identity-tier facts from Franklin's DB."""
    import contextlib
    from config import get_db
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT id, fact_text, fact_type, category, recurrence_count
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND knowledge_tier = 'identity'
            ORDER BY recurrence_count DESC
            LIMIT 100
        """).fetchall()
        lines = []
        for r in rows:
            ftype = r["fact_type"] or "?"
            cat = r["category"] or "?"
            fact_text = r["fact_text"]
            # Anonymize Franklin
            import re
            for name in ["Benjamin Franklin", "Franklin", "Benjamin"]:
                fact_text = re.sub(r'\b' + re.escape(name) + r'\b', 'this person', fact_text)
            fact_text = re.sub(r'(this person\s*){2,}', 'this person', fact_text)
            lines.append(f"- [{cat}/{ftype}] {fact_text}")
        return "\n".join(lines), len(rows)


def compose_with_prompt(prompt_text, layer_texts, facts_text, fact_count, variation_name):
    """Run a single compose variation."""
    from config import LAYER_REVIEW_MODEL
    import httpx

    full_prompt = prompt_text.replace(
        "{anchors}", layer_texts.get("anchors", "(no anchors layer)")
    ).replace(
        "{core}", layer_texts.get("core", "(no core layer)")
    ).replace(
        "{predictions}", layer_texts.get("predictions", "(no predictions layer)")
    ).replace(
        "{facts}", facts_text
    ).replace(
        "{fact_count}", str(fact_count)
    )

    print(f"\n{'='*60}")
    print(f"  Variation: {variation_name}")
    print(f"  Model: {LAYER_REVIEW_MODEL}")
    print(f"{'='*60}")

    client = get_anthropic_client()
    response = client.messages.create(
        model=LAYER_REVIEW_MODEL,
        max_tokens=16384,
        temperature=0,
        messages=[{"role": "user", "content": full_prompt}],
        timeout=httpx.Timeout(600.0, connect=30.0),
    )

    brief_text = response.content[0].text
    cost = (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000
    print(f"  Generated: {len(brief_text)} chars")
    print(f"  Cost: ~${cost:.3f}")

    return brief_text, cost


# ── Prompt Variations ────────────────────────────────────────────────────────

def get_v4_prompt():
    """V4: FP GUARDS + TENSION DIRECTIVES WOVEN — combine V1 + V2 with anti-enumeration."""
    base = agent_pipeline.UNIFIED_BRIEF_COMPOSITION_PROMPT

    # Add false positive guard instruction
    fp_instruction = """
FALSE POSITIVE GUARD PRESERVATION (REQUIRED):
For behavioral predictions that include false positive warnings in the PREDICTIONS layer,
preserve them as inline qualifiers in the brief narrative. Format: describe the pattern,
then add "— but not when [false positive scenario], which looks similar but stems from
[different mechanism]." These guards prevent the reading AI from over-applying patterns.
Do NOT strip false positive warnings during composition. Each guard should appear as a
natural parenthetical or dash-separated qualifier within the behavioral description.
If the PREDICTIONS layer has N false positive warnings, the composed brief should have
at least N-2 of them represented (some may merge naturally).
"""
    base = base.replace("FORMAT:\n", fp_instruction + "\nFORMAT:\n")

    # Replace tensions with woven tension-action pairs (NOT a separate section)
    old_tensions = "- Close with the key tensions and failure modes"
    new_tensions = """- Close with the key tensions, but make each one ACTIONABLE: state the contradiction AND what the reading AI should do when it surfaces. Weave these into 1-2 flowing prose paragraphs (NOT a bulleted list, NOT a separate labeled section). Example: "He demands systematic tracking but struggles with Order in practice — when he reports process failures, help diagnose the structural cause rather than reassuring him the system works." Each tension-action pair should read as natural prose, not as a formatted directive"""

    base = base.replace(old_tensions, new_tensions)

    return base


def get_v5_prompt():
    """V5: V4 + NO AVAILABILITY INDEX — full combined, no index."""
    base = get_v4_prompt()

    # Remove the availability index section
    avail_start = "AVAILABILITY INDEX (required, place at end of brief after [THIN DATA]):"
    avail_end = 'Example: "Additional behavioral patterns available:'
    idx_start = base.find(avail_start)
    idx_end = base.find('."', base.find(avail_end)) + 2
    if idx_start >= 0 and idx_end > idx_start:
        removed = base[idx_start:idx_end]
        base = base.replace(removed, "")

    base = base.replace("- End with an AVAILABILITY INDEX (see below)\n", "")

    return base


def get_v6_prompt():
    """V6: V4 + SHORTER — combined but with compression target."""
    base = get_v4_prompt()

    # Add compression guidance
    compression = """
COMPRESSION TARGET: Aim for the most compact brief that preserves all behavioral mechanisms,
false positive guards, and tension-action pairs. Prefer dense, information-rich sentences
over expansive paragraphs. If two sentences convey the same behavioral pattern, merge them.
The ideal brief is 5,000-7,000 characters — long enough to be complete, short enough to
leave context window room for conversation.
"""
    base = base.replace("CONSTRAINTS:\n", compression + "\nCONSTRAINTS:\n")

    return base


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Compose Variation Test — Franklin")
    print("=" * 60)

    layer_texts = read_layers()
    print(f"Layers loaded: {list(layer_texts.keys())}")
    for name, text in layer_texts.items():
        print(f"  {name}: {len(text)} chars")

    facts_text, fact_count = read_facts()
    print(f"Facts loaded: {fact_count}")

    output_dir = IDENTITY_LAYERS_DIR / "compose_variations"
    output_dir.mkdir(parents=True, exist_ok=True)

    variations = [
        ("V4_fp_guards_plus_tension_woven", get_v4_prompt()),
        ("V5_v4_no_availability_index", get_v5_prompt()),
        ("V6_v4_compressed", get_v6_prompt()),
    ]

    results = []
    total_cost = 0.0

    for name, prompt in variations:
        brief, cost = compose_with_prompt(prompt, layer_texts, facts_text, fact_count, name)
        total_cost += cost

        # Save
        outfile = output_dir / f"brief_{name}.md"
        header = f"---\nlayer: unified_brief\nvariation: {name}\ngenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\npipeline: compose variation test\n---\n\n## Injectable Block\n\n"
        outfile.write_text(header + brief, encoding="utf-8")
        print(f"  Saved: {outfile}")

        results.append({
            "name": name,
            "chars": len(brief),
            "cost": cost,
            "file": str(outfile),
        })

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['name']}: {r['chars']} chars, ${r['cost']:.3f}")
    print(f"  Total cost: ${total_cost:.3f}")
    print(f"\n  Output dir: {output_dir}")

    # Also save the current brief as baseline for comparison
    current_brief = IDENTITY_LAYERS_DIR / "brief_v4.md"
    if current_brief.exists():
        import shutil
        shutil.copy2(current_brief, output_dir / "brief_BASELINE.md")
        print(f"  Baseline copied: {output_dir / 'brief_BASELINE.md'}")


if __name__ == "__main__":
    main()
