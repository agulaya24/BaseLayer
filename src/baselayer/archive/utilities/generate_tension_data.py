"""
Generate tension/contradiction data for all subjects for the website.
Outputs TypeScript file for baselayer-website.
"""

import contextlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_ANTHROPIC_ROOT = os.environ.get("ANTHROPIC_ROOT", str(Path(__file__).parent.parent.parent))

SUBJECTS = {
    "franklin": f"{_ANTHROPIC_ROOT}/subjects/franklin_memory",
    "douglass": f"{_ANTHROPIC_ROOT}/subjects/douglass_memory",
    "wollstonecraft": f"{_ANTHROPIC_ROOT}/subjects/wollstonecraft_memory",
    "roosevelt": f"{_ANTHROPIC_ROOT}/subjects/roosevelt_memory",
    "patents": f"{_ANTHROPIC_ROOT}/subjects/patent_memory",
    "buffett": f"{_ANTHROPIC_ROOT}/subjects/buffett_memory",
    "marks": f"{_ANTHROPIC_ROOT}/subjects/marks_memory",
}

OUTPUT_FILE = f"{_ANTHROPIC_ROOT}/baselayer-website/data/tensionData.ts"


def scan_subject(name, db_path):
    """Run contradiction scan on a subject, return findings."""
    os.environ["MEMORY_SYSTEM_ROOT"] = db_path

    # Force reimport of config to pick up new MEMORY_SYSTEM_ROOT
    import importlib
    import config
    importlib.reload(config)

    from config import get_db
    from detect_contradictions import (
        load_facts, embed_facts, find_candidate_pairs, classify_pair_haiku,
    )

    print(f"\n{'=' * 50}")
    print(f"Scanning: {name}")
    print(f"DB: {config.DATABASE_FILE}")

    with contextlib.closing(get_db()) as conn:
        facts = load_facts(conn)
        print(f"  {len(facts)} active facts")

        if len(facts) < 2:
            return []

        embeddings = embed_facts(facts)
        candidates = find_candidate_pairs(facts, embeddings, threshold=0.45)
        print(f"  {len(candidates)} candidates")

        if not candidates:
            return []

        max_pairs = 40
        classify_count = min(len(candidates), max_pairs)
        print(f"  Classifying top {classify_count}...")

        findings = []
        for i, pair in enumerate(candidates[:classify_count]):
            fa, fb = pair["fact_a"], pair["fact_b"]
            pred_a = fa.get("predicate", "unknown")
            pred_b = fb.get("predicate", "unknown")

            result = classify_pair_haiku(fa["fact_text"], fb["fact_text"], pred_a, pred_b)
            verdict = result.get("verdict", "CONSISTENT")

            if verdict in ("CONTRADICTION", "TENSION"):
                marker = "[!!]" if verdict == "CONTRADICTION" else "[~~]"
                print(f"  {i+1}/{classify_count} {marker} {pred_a}/{pred_b} sim={pair['similarity']:.2f}")

                findings.append({
                    "verdict": verdict,
                    "factA": fa["fact_text"],
                    "factB": fb["fact_text"],
                    "predicateA": pred_a,
                    "predicateB": pred_b,
                    "sourceA": fa.get("source_title", "") or "",
                    "sourceB": fb.get("source_title", "") or "",
                    "similarity": pair["similarity"],
                    "reasoning": result.get("reasoning", ""),
                    "confidence": result.get("confidence", 0.0),
                    "selectionReason": pair.get("selection_reason", ""),
                })

        c = sum(1 for f in findings if f["verdict"] == "CONTRADICTION")
        t = sum(1 for f in findings if f["verdict"] == "TENSION")
        print(f"  Results: {c} contradictions, {t} tensions")
        return findings


def generate_typescript(all_data):
    """Generate TypeScript file with tension data."""
    lines = [
        "// Tension/contradiction data per subject -- generated from pipeline databases",
        "// S81 threshold variation: two-pass strategy (tension pairs @ 0.40, cross-category @ 0.45)",
        "",
        "export interface TensionEntry {",
        "  verdict: \"CONTRADICTION\" | \"TENSION\";",
        "  factA: string;",
        "  factB: string;",
        "  predicateA: string;",
        "  predicateB: string;",
        "  sourceA: string;",
        "  sourceB: string;",
        "  similarity: number;",
        "  reasoning: string;",
        "  confidence: number;",
        "  selectionReason: string;",
        "}",
        "",
        "export const tensionData: Record<string, TensionEntry[]> = {",
    ]

    for subject, findings in all_data.items():
        lines.append(f"  {subject}: [")
        for f in findings:
            lines.append("    {")
            lines.append(f'      verdict: "{f["verdict"]}",')
            lines.append(f'      factA: {json.dumps(f["factA"])},')
            lines.append(f'      factB: {json.dumps(f["factB"])},')
            lines.append(f'      predicateA: "{f["predicateA"]}",')
            lines.append(f'      predicateB: "{f["predicateB"]}",')
            lines.append(f'      sourceA: {json.dumps(f["sourceA"])},')
            lines.append(f'      sourceB: {json.dumps(f["sourceB"])},')
            lines.append(f'      similarity: {f["similarity"]},')
            lines.append(f'      reasoning: {json.dumps(f["reasoning"])},')
            lines.append(f'      confidence: {f["confidence"]},')
            lines.append(f'      selectionReason: "{f["selectionReason"]}",')
            lines.append("    },")
        lines.append("  ],")

    lines.append("};")
    lines.append("")

    return "\n".join(lines)


def main():
    all_data = {}

    for name, path in SUBJECTS.items():
        if not Path(path).exists():
            print(f"WARNING: {path} does not exist, skipping {name}")
            continue
        findings = scan_subject(name, path)
        all_data[name] = findings

    # Generate TypeScript
    ts_content = generate_typescript(all_data)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ts_content)

    print(f"\n{'=' * 50}")
    print(f"Generated: {OUTPUT_FILE}")
    for name, findings in all_data.items():
        c = sum(1 for f in findings if f["verdict"] == "CONTRADICTION")
        t = sum(1 for f in findings if f["verdict"] == "TENSION")
        print(f"  {name}: {c} contradictions, {t} tensions")

    total_api = sum(len(f) for f in all_data.values())
    print(f"\nTotal findings: {total_api}")


if __name__ == "__main__":
    main()
