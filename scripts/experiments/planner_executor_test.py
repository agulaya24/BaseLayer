"""
Planner-Executor Architecture Test (D-079)

Tests whether splitting composition into two isolated passes reduces
pre-training knowledge contamination:

  PLANNER (Opus):  Reads all 3 source layers → outputs structured claim plan
  EXECUTOR (Sonnet): Reads ONE claim + its cited source text → writes one paragraph

The executor never sees enough context to infer subject identity.
Compare output against current Opus-composed brief for quality + contamination.

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/planner_executor_test.py <subject_dir>

Example:
    python experiments/planner_executor_test.py "C:/Users/Aarik/Anthropic/subjects/franklin_memory"
"""

import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import get_anthropic_client

# ============================================================================
# MODELS
# ============================================================================
PLANNER_MODEL = "claude-opus-4-20250514"
EXECUTOR_MODEL = "claude-sonnet-4-20250514"

# ============================================================================
# PLANNER PROMPT
# ============================================================================
PLANNER_PROMPT = """You are a behavioral brief architect. Your job is to read three source layers
(ANCHORS, CORE, PREDICTIONS) about a person and output a STRUCTURED PLAN for a
unified behavioral brief.

You must output ONLY a JSON object with two keys: "paragraphs" and "availability_index".

Format:

{{
  "paragraphs": [
    {{
      "paragraph_id": 1,
      "theme": "short thematic label",
      "claim": "The specific behavioral claim this paragraph should express",
      "sources": ["A1", "C2", "P3"],
      "source_text": "The exact text from the source layers that supports this claim — copy verbatim",
      "instructions": "How the executor should write this paragraph (tone, what to emphasize)"
    }}
  ],
  "availability_index": [
    {{
      "pattern": "Pattern name using source layer vocabulary",
      "trigger": "When this pattern surfaces — use source layer language",
      "source": "A1 or C2 or P3 — which source item this comes from"
    }}
  ]
}}

PARAGRAPH RULES:
1. Every claim MUST be grounded in the source layers. If it's not in the sources, it's not in the plan.
2. Copy the supporting source text VERBATIM — do not paraphrase or add to it.
3. Do NOT include biographical details not explicitly stated in the sources.
4. Do NOT include dates, numbers, specific names, pseudonyms, languages, or historical events unless they appear VERBATIM in the source text.
5. Plan 8-15 paragraphs covering the full scope of the source layers.
6. Include at least one paragraph for key tensions/conflicts between axioms.
7. Include a thin-data paragraph if the sources contain [THIN IN:] or [THIN DATA] markers.
8. The plan should produce a brief that reads as flowing prose, not a list.
9. Do NOT identify who this person is. Do NOT reference any knowledge about this person beyond what's in the sources.

AVAILABILITY INDEX RULES:
1. List 3-8 behavioral patterns from the source layers that are NOT foregrounded as primary paragraph themes.
2. Each item MUST cite a specific source (A1, C2, P3, etc.) and the pattern/trigger language MUST come from that source.
3. Do NOT invent patterns. Do NOT add domain knowledge. ONLY patterns that appear in the source layers.
4. Use the subject's own vocabulary from the source layers — not generic behavioral terms.

SOURCE LAYERS:

=== ANCHORS ===
{anchors}

=== CORE ===
{core}

=== PREDICTIONS ===
{predictions}

Output ONLY the JSON object. No commentary."""


# ============================================================================
# EXECUTOR PROMPT
# ============================================================================
EXECUTOR_PROMPT = """Write exactly ONE paragraph (3-6 sentences) expressing the behavioral claim below.

CLAIM: {claim}

INSTRUCTIONS: {instructions}

SOURCE MATERIAL (use ONLY this text — do not add anything not stated here):
{source_text}

RULES:
- Write in third person ("he", "she", "they")
- Write flowing prose, not bullet points
- Include ONLY information present in the source material above
- Do NOT invent biographical details, dates, names, numbers, or historical events
- Do NOT identify who this person is or reference any knowledge beyond the source material
- Make every sentence change what a reader would understand about this person

VOCABULARY CONSTRAINT (CRITICAL):
- Use ONLY words and phrases that appear in the source material above
- Do NOT add intensifying adjectives not in the source (e.g., "profound," "radical," "insatiable," "unwavering," "sophisticated," "relentless")
- Do NOT add editorial framing not in the source (e.g., "transforming X into Y," "revealing how," "suggesting that," "demonstrating a")
- Do NOT add causal explanations not stated in the source — if the source doesn't say WHY, neither should you
- Do NOT use clinical or academic labels not in the source (e.g., "imposter syndrome," "dialectic," "cognitive processes")
- If the source says "avoids X," write "avoids X" — do not rephrase as "harbors a deep-seated aversion to X"
- Simpler is better. The source language IS the right language.

Output ONLY the paragraph. No commentary, no headers."""


# ============================================================================
# ASSEMBLY PROMPT — stitch paragraphs into coherent brief
# ============================================================================
ASSEMBLY_PROMPT = """You are assembling a behavioral brief from pre-written paragraphs into a single
flowing document. This is a portrait of a person, not a reference manual.

YOUR JOB:
1. Order paragraphs for narrative flow — group by thematic resonance, not by source layer
2. MERGE paragraphs that cover overlapping themes into single stronger paragraphs
3. REWRITE opening sentences of each paragraph so they flow naturally from the prior paragraph's last sentence — no mechanical transitions
4. Add an opening anchor (2-3 sentences — concrete behavioral observation that reveals WHO this person is, as distinctive as a fingerprint)
5. Add a closing availability index paragraph
6. Add a [THIN DATA] paragraph ONLY if source paragraphs mention thin/limited data

CRITICAL RULES:
- Do NOT add new claims, facts, or information not present in the paragraphs
- Do NOT add biographical details, dates, names, numbers, or events not in the paragraphs
- Do NOT use mechanical transitions ("This extends to...", "His approach to X reflects...", "Similarly...", "This systematic worldview shapes...")
- Do NOT use phrases: "operates from", "unshakeable conviction", "fundamental belief", "deeply held"
- You MAY rephrase paragraph content for flow, combine related paragraphs, and cut redundancy
- You MAY reorder sentences within and across paragraphs for better narrative
- The output should read like an essay written by one voice, not 13 paragraphs stitched together
- Use third person pronouns throughout
- Write in flowing prose — no bullet points, no headers except ## Injectable Block
- Every sentence should change what the reader understands about this person. Cut anything generic.

PARAGRAPHS:
{paragraphs}

AVAILABILITY INDEX (include EXACTLY as provided — do not modify, add to, or remove items):
{availability_items}

Output the assembled brief. Start with ## Injectable Block"""


# ============================================================================
# MAIN
# ============================================================================
def load_layer(subject_dir, filename):
    """Load a layer file, return empty string if not found."""
    path = os.path.join(subject_dir, "data", "identity_layers", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def run_planner(client, anchors, core, predictions):
    """Opus plans the brief structure."""
    prompt = PLANNER_PROMPT.format(
        anchors=anchors,
        core=core,
        predictions=predictions,
    )

    print("\n" + "=" * 60)
    print("  PHASE 1: PLANNER (Opus)")
    print("=" * 60)

    start = time.time()
    response = client.messages.create(
        model=PLANNER_MODEL,
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start

    text = response.content[0].text
    cost = (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000

    print(f"  Model: {PLANNER_MODEL}")
    print(f"  Tokens: {response.usage.input_tokens + response.usage.output_tokens}")
    print(f"  Cost: ~${cost:.3f}")
    print(f"  Time: {elapsed:.1f}s")

    # Parse JSON from response
    # Handle potential markdown code fences
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean[:-3]

    try:
        parsed = json.loads(clean)
        # Support both old format (array) and new format (object with paragraphs + availability_index)
        if isinstance(parsed, list):
            plan = parsed
            availability_index = []
        else:
            plan = parsed.get("paragraphs", parsed)
            availability_index = parsed.get("availability_index", [])
        print(f"  Claims planned: {len(plan)}")
        if availability_index:
            print(f"  Availability index items: {len(availability_index)}")
    except json.JSONDecodeError as e:
        print(f"  ERROR: Failed to parse planner output as JSON: {e}")
        print(f"  Raw output (first 500 chars): {text[:500]}")
        # Save raw output for debugging
        with open("planner_raw_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        return None, [], cost

    return plan, availability_index, cost


def run_executor(client, plan):
    """Sonnet writes each paragraph independently."""
    print("\n" + "=" * 60)
    print(f"  PHASE 2: EXECUTOR (Sonnet) — {len(plan)} paragraphs")
    print("=" * 60)

    paragraphs = []
    total_cost = 0.0

    for i, item in enumerate(plan):
        prompt = EXECUTOR_PROMPT.format(
            claim=item["claim"],
            instructions=item.get("instructions", "Write clearly and specifically."),
            source_text=item.get("source_text", "No source text provided."),
        )

        start = time.time()
        response = client.messages.create(
            model=EXECUTOR_MODEL,
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - start

        text = response.content[0].text.strip()
        cost = (response.usage.input_tokens * 3 + response.usage.output_tokens * 15) / 1_000_000
        total_cost += cost

        paragraphs.append({
            "paragraph_id": item["paragraph_id"],
            "theme": item["theme"],
            "sources": item["sources"],
            "text": text,
        })

        print(f"  [{i+1}/{len(plan)}] {item['theme']}: {len(text)} chars, ${cost:.4f}, {elapsed:.1f}s")

    print(f"\n  Total executor cost: ~${total_cost:.3f}")
    return paragraphs, total_cost


def run_assembly(client, paragraphs, availability_index=None):
    """Sonnet assembles paragraphs into a coherent brief."""
    print("\n" + "=" * 60)
    print("  PHASE 3: ASSEMBLY (Sonnet)")
    print("=" * 60)

    # Build paragraph block
    para_block = ""
    for p in paragraphs:
        para_block += f"\n--- Paragraph {p['paragraph_id']} ({p['theme']}) [Sources: {', '.join(p['sources'])}] ---\n"
        para_block += p["text"] + "\n"

    # Format availability index from planner (not generated by assembly)
    if availability_index:
        avail_text = "\n".join(
            f"- {item['pattern']} — {item['trigger']} [Source: {item.get('source', 'N/A')}]"
            for item in availability_index
        )
    else:
        avail_text = "(No availability index provided by planner)"

    prompt = ASSEMBLY_PROMPT.format(
        paragraphs=para_block,
        availability_items=avail_text,
    )

    start = time.time()
    response = client.messages.create(
        model=EXECUTOR_MODEL,
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start

    text = response.content[0].text.strip()
    cost = (response.usage.input_tokens * 3 + response.usage.output_tokens * 15) / 1_000_000

    print(f"  Model: {EXECUTOR_MODEL}")
    print(f"  Output: {len(text)} chars")
    print(f"  Cost: ~${cost:.3f}")
    print(f"  Time: {elapsed:.1f}s")

    return text, cost


def main():
    parser = argparse.ArgumentParser(description="Planner-Executor composition test")
    parser.add_argument("subject_dir", help="Path to subject memory directory")
    parser.add_argument("--plan-only", action="store_true", help="Only run the planner phase")
    parser.add_argument("--skip-assembly", action="store_true", help="Skip the assembly phase")
    args = parser.parse_args()

    subject_dir = args.subject_dir
    subject_name = os.path.basename(subject_dir).replace("_memory", "").replace("_meta_v2", "")

    print(f"\n{'=' * 60}")
    print(f"  PLANNER-EXECUTOR TEST: {subject_name}")
    print(f"  Subject dir: {subject_dir}")
    print(f"  Planner: {PLANNER_MODEL}")
    print(f"  Executor: {EXECUTOR_MODEL}")
    print(f"{'=' * 60}")

    # Load layers
    anchors = load_layer(subject_dir, "anchors_v4.md")
    core = load_layer(subject_dir, "core_v4.md")
    predictions = load_layer(subject_dir, "predictions_v4.md")

    if not anchors and not core and not predictions:
        print("  ERROR: No layers found. Check subject_dir path.")
        sys.exit(1)

    print(f"\n  Layers loaded:")
    print(f"    ANCHORS:     {len(anchors):,} chars" if anchors else "    ANCHORS:     (none)")
    print(f"    CORE:        {len(core):,} chars" if core else "    CORE:        (none)")
    print(f"    PREDICTIONS: {len(predictions):,} chars" if predictions else "    PREDICTIONS: (none)")

    client = get_anthropic_client()
    total_cost = 0.0

    # Phase 1: Plan
    plan, availability_index, plan_cost = run_planner(client, anchors, core, predictions)
    total_cost += plan_cost

    if plan is None:
        print("\n  ABORTED: Planner failed to produce valid JSON.")
        sys.exit(1)

    # Save plan
    out_dir = os.path.join(subject_dir, "data", "identity_layers")
    plan_path = os.path.join(out_dir, "pe_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({"paragraphs": plan, "availability_index": availability_index}, f, indent=2)
    print(f"\n  Plan saved: {plan_path}")

    if args.plan_only:
        print(f"\n  Total cost: ~${total_cost:.3f}")
        return

    # Phase 2: Execute
    paragraphs, exec_cost = run_executor(client, plan)
    total_cost += exec_cost

    # Save paragraphs
    paras_path = os.path.join(out_dir, "pe_paragraphs.json")
    with open(paras_path, "w", encoding="utf-8") as f:
        json.dump(paragraphs, f, indent=2)
    print(f"  Paragraphs saved: {paras_path}")

    if args.skip_assembly:
        # Just concatenate paragraphs
        raw_brief = "\n\n".join(p["text"] for p in paragraphs)
        brief_path = os.path.join(out_dir, "brief_pe_test.md")
        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(f"---\nlayer: unified_brief_pe_test\ngenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\npipeline: planner-executor (no assembly)\nplanner: {PLANNER_MODEL}\nexecutor: {EXECUTOR_MODEL}\n---\n\n")
            f.write(raw_brief)
        print(f"  Brief (raw) saved: {brief_path}")
    else:
        # Phase 3: Assemble
        brief_text, asm_cost = run_assembly(client, paragraphs, availability_index)
        total_cost += asm_cost

        # Save final brief
        brief_path = os.path.join(out_dir, "brief_pe_test.md")
        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(f"---\nlayer: unified_brief_pe_test\ngenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\npipeline: planner-executor\nplanner: {PLANNER_MODEL}\nexecutor: {EXECUTOR_MODEL}\n---\n\n")
            f.write(brief_text)
        print(f"\n  Brief saved: {brief_path}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Claims planned: {len(plan)}")
    print(f"  Paragraphs written: {len(paragraphs)}")

    total_chars = sum(len(p["text"]) for p in paragraphs)
    print(f"  Total paragraph chars: {total_chars:,}")
    print(f"  Total cost: ~${total_cost:.3f}")

    # Load current brief for comparison
    current_brief_path = os.path.join(out_dir, "brief_v4.md")
    if os.path.exists(current_brief_path):
        with open(current_brief_path, "r", encoding="utf-8") as f:
            current = f.read()
        print(f"\n  Current brief (Opus-only): {len(current):,} chars")
        print(f"  P-E brief:                 {total_chars:,} chars (paragraphs only)")

    print(f"\n  Compare: {brief_path}")
    print(f"       vs: {current_brief_path}")
    print(f"\n  Next: Run contamination scan on both briefs to compare.")


if __name__ == "__main__":
    main()
