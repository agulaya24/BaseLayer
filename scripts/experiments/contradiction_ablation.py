"""
Contradiction Ablation Test — S81

Does composing a brief WITH contradiction/tension awareness produce a better brief?

Design:
  Condition A (baseline): Standard V4 compose from layers + facts
  Condition B (tension-aware): V4 compose + explicit tensions injected into prompt

Steps:
  1. Run contradiction scan on subject DB (embedding + Haiku classification)
  2. Compose two briefs using Opus
  3. Pairwise judge (Sonnet) — blind comparison

Usage:
  # Set environment for subject
  set MEMORY_SYSTEM_ROOT=path/to/subject_memory
  python scripts/contradiction_ablation.py

Cost estimate: ~$0.50 (scan ~$0.02, 2x compose ~$0.20 each, judge ~$0.05)
"""

import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    PROJECT_ROOT, DATABASE_FILE,
    EXTRACTION_API_MODEL,
    get_db,
)

# Import compose infrastructure
from agent_pipeline import (
    compose_unified_brief,
    UNIFIED_BRIEF_COMPOSITION_PROMPT,
    ANCHORS_LAYER_FILE,
    CORE_LAYER_FILE,
    PREDICTIONS_LAYER_FILE,
)

from detect_contradictions import (
    load_facts,
    embed_facts,
    find_candidate_pairs,
    classify_pair_haiku,
)


def run_contradiction_scan(max_pairs=30, threshold=0.50):
    """Run contradiction scan, return findings."""
    with contextlib.closing(get_db()) as conn:
        print("=" * 60)
        print("STEP 1: Contradiction Scan")
        print("=" * 60)

        facts = load_facts(conn)
        print(f"  {len(facts)} active facts")

        if len(facts) < 2:
            print("  Not enough facts for contradiction detection")
            return []

        print("  Embedding facts...")
        embeddings = embed_facts(facts)
        print(f"  Embedded {len(embeddings)} facts ({embeddings.shape[1]}d)")

        print(f"  Finding candidates (threshold={threshold})...")
        candidates = find_candidate_pairs(facts, embeddings, threshold)
        print(f"  {len(candidates)} candidate pairs")

        if not candidates:
            print("  No candidates found")
            return []

        classify_count = min(len(candidates), max_pairs)
        print(f"  Classifying top {classify_count} pairs with Haiku...")

        findings = []
        for i, pair in enumerate(candidates[:classify_count]):
            fa, fb = pair["fact_a"], pair["fact_b"]
            pred_a = fa.get("predicate", "unknown")
            pred_b = fb.get("predicate", "unknown")

            result = classify_pair_haiku(fa["fact_text"], fb["fact_text"], pred_a, pred_b)
            verdict = result.get("verdict", "CONSISTENT")

            if verdict in ("CONTRADICTION", "TENSION"):
                marker = "[!!]" if verdict == "CONTRADICTION" else "[~~]"
                print(f"  {i+1}/{classify_count} {marker} {verdict} "
                      f"(sim={pair['similarity']:.2f})")
                print(f"    A ({pred_a}): {fa['fact_text'][:80]}")
                print(f"    B ({pred_b}): {fb['fact_text'][:80]}")
                print(f"    Reasoning: {result.get('reasoning', '')}")

                findings.append({
                    "verdict": verdict,
                    "fact_a_text": fa["fact_text"],
                    "fact_b_text": fb["fact_text"],
                    "fact_a_predicate": pred_a,
                    "fact_b_predicate": pred_b,
                    "similarity": pair["similarity"],
                    "reasoning": result.get("reasoning", ""),
                    "confidence": result.get("confidence", 0.0),
                    "fact_a_source": fa.get("source_title", ""),
                    "fact_b_source": fb.get("source_title", ""),
                })
            else:
                print(f"  {i+1}/{classify_count} [OK] CONSISTENT (sim={pair['similarity']:.2f})")

        contradictions = sum(1 for f in findings if f["verdict"] == "CONTRADICTION")
        tensions = sum(1 for f in findings if f["verdict"] == "TENSION")
        print(f"\n  RESULTS: {contradictions} contradictions, {tensions} tensions")
        return findings


def format_tensions_for_prompt(findings):
    """Format contradiction/tension findings into compose prompt injection."""
    if not findings:
        return ""

    lines = [
        "\n## DETECTED TENSIONS AND CONTRADICTIONS",
        "",
        "The following tensions were detected in the source facts via embedding similarity + LLM classification.",
        "These are NOT errors — they reveal identity complexity. Weave them into the brief as characteristic tensions.",
        "",
    ]

    for i, f in enumerate(findings, 1):
        lines.append(f"### {'Contradiction' if f['verdict'] == 'CONTRADICTION' else 'Tension'} {i}")
        lines.append(f"- Fact A ({f['fact_a_predicate']}): {f['fact_a_text']}")
        lines.append(f"- Fact B ({f['fact_b_predicate']}): {f['fact_b_text']}")
        lines.append(f"- Reasoning: {f['reasoning']}")
        lines.append(f"- Similarity: {f['similarity']:.2f}, Confidence: {f['confidence']:.1f}")
        lines.append("")

    lines.append("INSTRUCTION: Integrate these tensions into the brief. They show where this person's")
    lines.append("identity is complex rather than simple. Frame each as a characteristic tension that")
    lines.append("helps an AI understand when to expect contradictory behavior.")
    lines.append("")

    return "\n".join(lines)


def compose_condition(condition_name, extra_context=""):
    """Run compose with optional extra context injected."""
    from config import LAYER_REVIEW_MODEL
    from api_client import get_anthropic_client
    import httpx

    print(f"\n{'=' * 60}")
    print(f"COMPOSE: {condition_name}")
    print(f"{'=' * 60}")

    # Read deployed layers
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

    if not any(layer_texts.get(k) for k in ("anchors", "core", "predictions")):
        print("  ERROR: No deployed layers found")
        return None

    # Get identity-tier facts
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT id, fact_text, fact_type, category, recurrence_count, subject
            FROM memory_facts
            WHERE superseded_by IS NULL
              AND knowledge_tier = 'identity'
            ORDER BY recurrence_count DESC
            LIMIT 100
        """).fetchall()
        fact_count = len(rows)

        # Detect subject name for anonymization
        from collections import Counter
        subjects = Counter()
        for r in rows:
            subj = r["subject"]
            if subj and subj.strip().lower() not in ("user", "i", "me", "self", "they", "he", "she"):
                subjects[subj.strip()] += 1
        subject_name = None
        if subjects:
            top_name, top_count = subjects.most_common(1)[0]
            if top_count >= 3:
                subject_name = top_name

        lines = []
        for r in rows:
            ftype = r["fact_type"] or "?"
            cat = r["category"] or "?"
            fact_text = r["fact_text"]
            if subject_name:
                fact_text = fact_text.replace(subject_name, "this person")
                for part in subject_name.split():
                    if len(part) > 3:
                        fact_text = re.sub(r'\b' + re.escape(part) + r'\b', 'this person', fact_text)
                fact_text = re.sub(r'(this person\s*){2,}', 'this person', fact_text)
            lines.append(f"- [{cat}/{ftype}] {fact_text}")
        source_facts_text = "\n".join(lines)

    # Build prompt
    prompt = UNIFIED_BRIEF_COMPOSITION_PROMPT.replace(
        "{anchors}", layer_texts.get("anchors", "(no anchors layer)")
    ).replace(
        "{core}", layer_texts.get("core", "(no core layer)")
    ).replace(
        "{predictions}", layer_texts.get("predictions", "(no predictions layer)")
    ).replace(
        "{facts}", source_facts_text
    ).replace(
        "{fact_count}", str(fact_count)
    )

    # Inject extra context (tensions) if provided
    if extra_context:
        prompt = prompt + "\n\n" + extra_context

    print(f"  Model: {LAYER_REVIEW_MODEL}")
    print(f"  Layers: {len(layer_texts)}, Facts: {fact_count}")
    if extra_context:
        print(f"  Extra context: {len(extra_context)} chars (tensions injected)")

    client = get_anthropic_client()
    try:
        response = client.messages.create(
            model=LAYER_REVIEW_MODEL,
            max_tokens=16384,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            timeout=httpx.Timeout(600.0, connect=30.0),
        )
        brief_text = response.content[0].text
        cost = (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000
        print(f"  Generated: {len(brief_text)} chars, ~${cost:.3f}")
        return brief_text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def pairwise_judge(brief_a, brief_b, condition_a_name, condition_b_name):
    """Blind pairwise comparison using Sonnet."""
    from api_client import call_api

    print(f"\n{'=' * 60}")
    print("PAIRWISE JUDGE (blind)")
    print(f"{'=' * 60}")

    # Randomize order to avoid position bias
    import random
    if random.random() > 0.5:
        first, second = brief_a, brief_b
        first_name, second_name = condition_a_name, condition_b_name
        swapped = False
    else:
        first, second = brief_b, brief_a
        first_name, second_name = condition_b_name, condition_a_name
        swapped = True

    prompt = f"""You are evaluating two identity briefs generated from the same source data.
Both briefs describe the same person. Your job is to determine which brief better captures
the person's identity — their characteristic tensions, behavioral patterns, and predictive value.

## Brief X

{first}

## Brief Y

{second}

## Evaluation Criteria

Rate each brief on these dimensions (1-10):

1. **Tension Awareness**: Does the brief capture characteristic contradictions and tensions?
   (e.g., "values frugality but enjoys luxury" — internal complexity, not errors)
2. **Predictive Power**: Could an AI use this brief to predict how the person would respond
   to novel situations?
3. **Behavioral Specificity**: Does the brief describe specific behavioral patterns rather
   than generic traits?
4. **Completeness**: Does the brief cover the full range of the person's identity?
5. **Conciseness**: Is the brief efficiently written without redundancy?

## Output Format

Return ONLY a JSON object:
{{
  "brief_x_scores": {{"tension": N, "predictive": N, "specificity": N, "completeness": N, "conciseness": N}},
  "brief_y_scores": {{"tension": N, "predictive": N, "specificity": N, "completeness": N, "conciseness": N}},
  "winner": "X" or "Y" or "TIE",
  "reasoning": "2-3 sentences explaining the key differences"
}}"""

    try:
        response = call_api(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0,
            caller="contradiction_ablation_judge",
        )
        text = response.content[0].text.strip()
        # Parse JSON
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
        else:
            result = {"error": "Could not parse judge response", "raw": text[:500]}

        # Unswap if needed
        if swapped:
            if result.get("winner") == "X":
                result["winner"] = "Y"
            elif result.get("winner") == "Y":
                result["winner"] = "X"
            result["brief_x_scores"], result["brief_y_scores"] = result.get("brief_y_scores", {}), result.get("brief_x_scores", {})

        # Map back to condition names
        result["condition_x"] = condition_a_name
        result["condition_y"] = condition_b_name
        result["presentation_order"] = "swapped" if swapped else "original"

        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"error": str(e)}


def main():
    output_dir = PROJECT_ROOT / "data" / "eval" / "contradiction_ablation"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("CONTRADICTION ABLATION TEST")
    print(f"DB: {DATABASE_FILE}")
    print(f"Output: {output_dir}")
    print()

    # Step 1: Run contradiction scan
    findings = run_contradiction_scan(max_pairs=30, threshold=0.50)

    # Save findings
    findings_file = output_dir / "contradiction_findings.json"
    with open(findings_file, "w") as f:
        json.dump(findings, f, indent=2)
    print(f"\n  Saved {len(findings)} findings to {findings_file}")

    if not findings:
        print("\n  No contradictions/tensions found. Cannot run ablation.")
        print("  This itself is a finding — the subject may have low internal tension.")
        return

    # Step 2: Compose two briefs
    # Condition A: baseline (no tension context)
    brief_a = compose_condition("Condition A: Baseline V4")

    # Condition B: tension-aware (tensions injected)
    tension_context = format_tensions_for_prompt(findings)
    brief_b = compose_condition("Condition B: Tension-Aware V4", extra_context=tension_context)

    if not brief_a or not brief_b:
        print("\n  ERROR: One or both briefs failed to generate")
        return

    # Save briefs
    (output_dir / "brief_condition_a_baseline.md").write_text(brief_a, encoding="utf-8")
    (output_dir / "brief_condition_b_tension.md").write_text(brief_b, encoding="utf-8")
    print(f"\n  Saved briefs to {output_dir}")

    # Step 3: Pairwise judge
    result = pairwise_judge(brief_a, brief_b, "Baseline V4", "Tension-Aware V4")

    # Save and display results
    results_file = output_dir / "ablation_results.json"
    with open(results_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{'=' * 60}")
    print("ABLATION RESULTS")
    print(f"{'=' * 60}")

    if "error" in result:
        print(f"  Error: {result['error']}")
    else:
        winner = result.get("winner", "?")
        winner_name = result.get(f"condition_{'x' if winner == 'X' else 'y'}", winner)
        print(f"  Winner: {winner} ({winner_name})")
        print(f"  Presentation order: {result.get('presentation_order', '?')}")
        print()

        for label, key in [("Baseline V4", "brief_x_scores"), ("Tension-Aware V4", "brief_y_scores")]:
            scores = result.get(key, {})
            if scores:
                total = sum(scores.values())
                print(f"  {label}:")
                for dim, score in scores.items():
                    print(f"    {dim}: {score}/10")
                print(f"    TOTAL: {total}/50")
                print()

        print(f"  Reasoning: {result.get('reasoning', '?')}")

    print(f"\n  Full results: {results_file}")


if __name__ == "__main__":
    main()
