"""
Score ablation briefs using new primitives rubric (D-079).

Rubric: Provenance (30) + Behavioral Change (30) + Epistemic Calibration (20) + Signal Density (10) = 90

Usage:
    cd C:/Users/Aarik/Anthropic/memory_system/scripts
    python experiments/score_ablation.py --conditions C28,C29,C30
"""

import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import get_anthropic_client

OPUS = "claude-opus-4-20250514"

ALL_SUBJECTS = [
    ("franklin", "C:/Users/Aarik/Anthropic/subjects/franklin_memory"),
    ("buffett", "C:/Users/Aarik/Anthropic/subjects/buffett_memory"),
    ("aarik", "C:/Users/Aarik/Anthropic/memory_system_v4"),
]

REVIEW_PROMPT = """You are a behavioral brief evaluator. Score this brief against four primitives of understanding how to work with a human.

SOURCE LAYERS (ground truth — the brief should be derived ONLY from these):

{layers}

BRIEF TO EVALUATE:

{brief}

SCORING RUBRIC (90 points total):

PROVENANCE (30 points, 3 items × 10):
P1. Citation coverage (0-10): What percentage of claims have inline source citations [A1], [P3], [C2]? 10=all claims cited, 0=none.
P2. Cross-layer citations (0-10): Does the brief connect patterns across layers with [Px, Ay] citations? 10=rich cross-references, 0=none.
P3. Faithfulness (0-10): Are ALL claims actually grounded in the source layers? For each claim, check whether it traces to a cited source code. A paraphrased claim that cites a real source code and conveys the same meaning as the source = faithful (score 8-10). A claim with NO traceable source = fabricated (score 0-3). The test is provenance, not verbatim reproduction.

BEHAVIORAL CHANGE (30 points, 3 items × 10):
B1. Directive quality (0-10): Does the brief tell the LLM what to DO differently? Concrete behavioral instructions, not just descriptions. 10=every section has clear directives, 0=purely descriptive.
B2. Communication guidance (0-10): Does it include HOW to communicate — mode switching, tone, structure of responses? 10=comprehensive comm guidance, 0=none.
B3. Context coverage (0-10): Does it cover all major source domains (A, P, M, C codes)? 10=comprehensive, 0=major gaps.

EPISTEMIC CALIBRATION (20 points, 2 items × 10):
E1. False positive grounding (0-10): Are FP warnings present? Check each FP warning against the PREDICTIONS layer source. If the FP warning cites a prediction code [Px] and that prediction's "False positive warning" section contains the same meaning (even paraphrased) = faithful (8-10). If the FP warning has NO corresponding source = fabricated (0-3). If the brief omits FP warnings entirely despite the source PREDICTIONS layer containing them = missed opportunity (4-5). The test is whether the citation traces to real source content.
E2. Uncertainty marking (0-10): Does it preserve [CONTESTED], [THIN IN] tags? Does it include "cannot predict" or temporal awareness? 10=explicit epistemic boundaries, 0=presents everything as certain.

SIGNAL DENSITY (10 points, 1 item × 10):
S1. Compression quality (0-10): Is every sentence adding new understanding? Redundancy? Appropriate length (3,500-4,500 chars optimal)? 10=maximally dense, 0=bloated/repetitive.

Output ONLY a JSON object:
{{
    "P1": <score>, "P1_note": "<brief justification>",
    "P2": <score>, "P2_note": "<brief justification>",
    "P3": <score>, "P3_note": "<brief justification>",
    "B1": <score>, "B1_note": "<brief justification>",
    "B2": <score>, "B2_note": "<brief justification>",
    "B3": <score>, "B3_note": "<brief justification>",
    "E1": <score>, "E1_note": "<brief justification>",
    "E2": <score>, "E2_note": "<brief justification>",
    "S1": <score>, "S1_note": "<brief justification>",
    "total": <sum>,
    "summary": "<1-2 sentence overall assessment>"
}}"""


def load_layer(subject_dir, filename):
    path = os.path.join(subject_dir, "data", "identity_layers", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def format_layers(anchors, core, predictions):
    parts = []
    if anchors:
        parts.append(f"=== ANCHORS ===\n{anchors}")
    if core:
        parts.append(f"=== CORE ===\n{core}")
    if predictions:
        parts.append(f"=== PREDICTIONS ===\n{predictions}")
    return "\n\n".join(parts)


def score_brief(client, layers_text, brief_text):
    prompt = REVIEW_PROMPT.format(layers=layers_text, brief=brief_text)
    response = client.messages.create(
        model=OPUS,
        max_tokens=2000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    cost = (response.usage.input_tokens * 15 + response.usage.output_tokens * 75) / 1_000_000

    # Parse JSON
    clean = text
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean[:-3]

    try:
        scores = json.loads(clean)
    except json.JSONDecodeError:
        scores = {"raw": text, "total": -1, "parse_error": True}

    return scores, cost


def main():
    parser = argparse.ArgumentParser(description="Score ablation briefs")
    parser.add_argument("--conditions", default="C28,C29,C30",
                        help="Comma-separated condition IDs")
    args = parser.parse_args()

    cond_ids = [c.strip() for c in args.conditions.split(",")]
    client = get_anthropic_client()

    all_results = []
    total_cost = 0.0

    for subject_name, subject_dir in ALL_SUBJECTS:
        anchors = load_layer(subject_dir, "anchors_v4.md")
        core = load_layer(subject_dir, "core_v4.md")
        predictions = load_layer(subject_dir, "predictions_v4.md")
        layers_text = format_layers(anchors, core, predictions)

        print(f"\n{'='*60}")
        print(f"  SUBJECT: {subject_name}")
        print(f"{'='*60}")

        for cond_id in cond_ids:
            brief_path = os.path.join(subject_dir, "data", "identity_layers", f"brief_ablation_{cond_id}.md")
            if not os.path.exists(brief_path):
                print(f"  SKIP {cond_id}: brief not found at {brief_path}")
                continue

            with open(brief_path, "r", encoding="utf-8") as f:
                brief_text = f.read()

            print(f"\n  --- {cond_id} ---")
            start = time.time()
            scores, cost = score_brief(client, layers_text, brief_text)
            elapsed = time.time() - start
            total_cost += cost

            total = scores.get("total", -1)
            print(f"  Score: {total}/90  (${cost:.3f}, {elapsed:.1f}s)")

            if not scores.get("parse_error"):
                print(f"    P: {scores.get('P1',0)}+{scores.get('P2',0)}+{scores.get('P3',0)} = {scores.get('P1',0)+scores.get('P2',0)+scores.get('P3',0)}/30")
                print(f"    B: {scores.get('B1',0)}+{scores.get('B2',0)}+{scores.get('B3',0)} = {scores.get('B1',0)+scores.get('B2',0)+scores.get('B3',0)}/30")
                print(f"    E: {scores.get('E1',0)}+{scores.get('E2',0)} = {scores.get('E1',0)+scores.get('E2',0)}/20")
                print(f"    S: {scores.get('S1',0)}/10")
                print(f"    Summary: {scores.get('summary','')}")

            all_results.append({
                "subject": subject_name,
                "condition": cond_id,
                "scores": scores,
                "cost": round(cost, 4),
                "time": round(elapsed, 1),
            })

    # Summary table
    print(f"\n\n{'='*80}")
    print(f"  SCORING SUMMARY")
    print(f"{'='*80}")
    print(f"  {'Subject':<10} {'Cond':<6} {'Prov':>6} {'BChg':>6} {'Epis':>6} {'SDen':>6} {'Total':>6}")
    print(f"  {'-'*10} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")

    for r in all_results:
        s = r["scores"]
        if s.get("parse_error"):
            print(f"  {r['subject']:<10} {r['condition']:<6} PARSE ERROR")
        else:
            prov = s.get("P1",0) + s.get("P2",0) + s.get("P3",0)
            bchg = s.get("B1",0) + s.get("B2",0) + s.get("B3",0)
            epis = s.get("E1",0) + s.get("E2",0)
            sden = s.get("S1",0)
            total = s.get("total", prov+bchg+epis+sden)
            print(f"  {r['subject']:<10} {r['condition']:<6} {prov:>4}/30 {bchg:>4}/30 {epis:>4}/20 {sden:>4}/10 {total:>4}/90")

    # Averages per condition
    print(f"\n  CONDITION AVERAGES:")
    for cond_id in cond_ids:
        cond_results = [r for r in all_results if r["condition"] == cond_id and not r["scores"].get("parse_error")]
        if cond_results:
            avg = sum(r["scores"].get("total", 0) for r in cond_results) / len(cond_results)
            print(f"  {cond_id}: {avg:.1f}/90 (n={len(cond_results)})")

    print(f"\n  Total scoring cost: ${total_cost:.3f}")

    # Save
    results_path = os.path.join(os.path.dirname(__file__), "score_ablation_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"  Results saved: {results_path}")


if __name__ == "__main__":
    main()
