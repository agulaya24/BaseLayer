"""Generate agentic.ts data file for the Base Layer website."""
import json
import re
import sqlite3


def js_str(s):
    if s is None:
        return "null"
    return json.dumps(s)


def main():
    # Load facts from SQLite
    conn = sqlite3.connect(
        "C:/Users/Aarik/Anthropic/subjects/agentic_patterns/data/database/memory.db"
    )
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT id, fact_text, category, confidence, knowledge_tier, fact_type,
           predicate, object_text, subject, source_conversation_id
           FROM memory_facts WHERE superseded_by IS NULL ORDER BY confidence DESC"""
    )
    facts = []
    for r in cur.fetchall():
        d = dict(r)
        src = d["source_conversation_id"] or ""
        chapter = (
            src.replace("textfile_", "").rsplit("_", 1)[0]
            if src.startswith("textfile_")
            else src
        )
        facts.append(
            {
                "id": d["id"],
                "text": d["fact_text"],
                "category": d["category"],
                "confidence": round(d["confidence"], 4),
                "tier": d["knowledge_tier"] or "untiered",
                "type": d["fact_type"],
                "predicate": d["predicate"],
                "object": d["object_text"],
                "subject": d["subject"],
                "sourceChapter": chapter,
            }
        )
    conn.close()

    # Parse brief paragraphs
    brief_text = open(
        "C:/Users/Aarik/Anthropic/subjects/agentic_patterns/data/identity_layers/brief_v5_clean.md",
        encoding="utf-8",
    ).read()
    lines = brief_text.strip().split("\n")
    content_lines = []
    dash_count = 0
    past_header = False
    for line in lines:
        if line.strip() == "---":
            dash_count += 1
            continue
        if dash_count < 2:
            continue
        if line.strip() == "## Injectable Block":
            past_header = True
            continue
        if past_header:
            content_lines.append(line)
    text = "\n".join(content_lines).strip()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # Source mapping for brief paragraphs
    brief_source_map = [
        (["A", "C", "P"], ["A7", "P1", "C3"]),
        (["A", "C"], ["A1", "A6", "M1"]),
        (["A", "C", "P"], ["A3", "P2", "M3"]),
        (["A", "C", "P"], ["A6", "P3", "M1"]),
        (["A", "P"], ["A2", "A5", "P4"]),
        (["A", "C", "P"], ["A3", "A4", "P6"]),
        (["A", "C", "P"], ["A6", "P5", "P7"]),
        (["A", "C"], ["A7", "A10", "A8"]),
        (["A", "C", "P"], ["A9", "P8", "C3"]),
        (["A", "C", "P"], ["A1", "A2", "A3", "A4", "A5", "M3"]),
        (["A", "C", "P"], []),
        (["A", "C", "P"], []),
    ]

    # Build TS
    ts = []
    ts.append("// Auto-generated from agentic_patterns pipeline output")
    ts.append(
        "// Source: subjects/agentic_patterns/data/identity_layers/ + SQLite"
    )
    ts.append(
        "// Book/document case study: Agentic Design Patterns processed through Base Layer"
    )
    ts.append("")
    ts.append(
        'import type { LayerItem, Fact, BriefParagraph, AxiomInteractions } from "@/data/baselayer";'
    )
    ts.append("")
    ts.append("export type { LayerItem, Fact, BriefParagraph, AxiomInteractions };")
    ts.append("")

    # Brief
    ts.append("export const agenticBrief: BriefParagraph[] = [")
    for i, p in enumerate(paragraphs):
        sources, related = (
            brief_source_map[i]
            if i < len(brief_source_map)
            else (["A", "C", "P"], [])
        )
        sources_str = ", ".join(f'"{s}"' for s in sources)
        related_str = ", ".join(f'"{r}"' for r in related)
        ts.append("  {")
        ts.append(f"    text: {js_str(p)},")
        ts.append(f"    sources: [{sources_str}],")
        if related:
            ts.append(f"    relatedItems: [{related_str}],")
        ts.append("  },")
    ts.append("];")
    ts.append("")

    # Cited brief
    ts.append("export const agenticCitedBrief: BriefParagraph[] = agenticBrief;")
    ts.append("")

    # Stats
    ts.append("export const agenticStats = {")
    ts.append("  chapters: 1,")
    ts.append("  totalFacts: 306,")
    ts.append(f"  activeFacts: {len(facts)},")
    ts.append("  identityTier: 0,")
    ts.append("  situationalTier: 0,")
    ts.append("  contextTier: 0,")
    ts.append("  anchors: 10,")
    ts.append("  contextModes: 3,")
    ts.append("  predictions: 8,")
    ts.append("  anchorsScore: 0,")
    ts.append("  coreScore: 0,")
    ts.append("  predictionsScore: 0,")
    ts.append("  pipelineCost: 0,")
    ts.append('  model: "claude-sonnet-4-20250514",')
    ts.append('  provenanceMethod: "citation_api",')
    ts.append("};")
    ts.append("")

    # Anchors
    anchors_md = open(
        "C:/Users/Aarik/Anthropic/subjects/agentic_patterns/data/identity_layers/anchors_v4.md",
        encoding="utf-8",
    ).read()
    ts.append("export const agenticAnchors: LayerItem[] = [")
    anchor_pattern = re.compile(
        r"\*\*A(\d+)\.\s+(.+?)\*\*\n(.+?)(?=\n\n\*\*A|\n\n##|\Z)", re.DOTALL
    )
    for m in anchor_pattern.finditer(anchors_md):
        aid = f"A{m.group(1)}"
        name = m.group(2).strip()
        body = m.group(3).strip()
        active_match = re.search(r"Active when:\s*(.+)", body)
        active_when = active_match.group(1).strip() if active_match else ""
        desc = body
        if active_match:
            desc = body[: active_match.start()].strip()
        ts.append("  {")
        ts.append(f"    id: {js_str(aid)},")
        ts.append(f"    name: {js_str(name)},")
        ts.append(f"    description: {js_str(desc)},")
        if active_when:
            ts.append(f"    activeWhen: {js_str(active_when)},")
        ts.append("    traces: [],")
        ts.append("  },")
    ts.append("];")
    ts.append("")

    # Core
    core_md = open(
        "C:/Users/Aarik/Anthropic/subjects/agentic_patterns/data/identity_layers/core_v4.md",
        encoding="utf-8",
    ).read()
    ts.append("export const agenticCore: LayerItem[] = [")
    core_pattern = re.compile(
        r"\*\*(M\d+|C\d+)\.\s+(.+?)\*\*\n+(.+?)(?=\n\n\*\*[MC]\d+|\Z)", re.DOTALL
    )
    for m in core_pattern.finditer(core_md):
        cid = m.group(1)
        name = m.group(2).strip()
        desc = m.group(3).strip()
        ts.append("  {")
        ts.append(f"    id: {js_str(cid)},")
        ts.append(f"    name: {js_str(name)},")
        ts.append(f"    description: {js_str(desc)},")
        ts.append("    traces: [],")
        ts.append("  },")
    ts.append("];")
    ts.append("")

    # Predictions
    pred_md = open(
        "C:/Users/Aarik/Anthropic/subjects/agentic_patterns/data/identity_layers/predictions_v4.md",
        encoding="utf-8",
    ).read()
    ts.append("export const agenticPredictions: LayerItem[] = [")
    pred_pattern = re.compile(
        r"\*\*(P\d+)\.\s+(.+?)\*\*:\s*(.+?)(?=\n\n\*\*P\d+|\Z)", re.DOTALL
    )
    for m in pred_pattern.finditer(pred_md):
        pid = m.group(1)
        name = m.group(2).strip()
        body = m.group(3).strip()
        directive_match = re.search(
            r"Directive:\s*(.+?)(?=\nFalse positive|\Z)", body, re.DOTALL
        )
        fp_match = re.search(
            r"False positive warning:\s*(.+?)(?=\n\n|\Z)", body, re.DOTALL
        )
        trigger_match = re.match(r"(.+?)(?=\nDetection:)", body, re.DOTALL)
        trigger = trigger_match.group(1).strip() if trigger_match else body.split("\n")[0]
        detection_match = re.search(
            r"Detection:\s*(.+?)(?=\nDirective:|\Z)", body, re.DOTALL
        )
        desc = trigger
        if detection_match:
            desc += "\n" + detection_match.group(1).strip()
        directive = directive_match.group(1).strip() if directive_match else ""
        fp = fp_match.group(1).strip() if fp_match else ""
        ts.append("  {")
        ts.append(f"    id: {js_str(pid)},")
        ts.append(f"    name: {js_str(name)},")
        ts.append(f"    description: {js_str(desc)},")
        if directive:
            ts.append(f"    directive: {js_str(directive)},")
        if fp:
            ts.append(f"    falsePositive: {js_str(fp)},")
        ts.append("    traces: [],")
        ts.append("  },")
    ts.append("];")
    ts.append("")

    # Facts
    ts.append("export const agenticFacts: Fact[] = [")
    for f in facts:
        ts.append("  {")
        ts.append(f"    id: {js_str(f['id'])},")
        ts.append(f"    text: {js_str(f['text'])},")
        ts.append(f"    category: {js_str(f['category'])},")
        ts.append(f"    confidence: {f['confidence']},")
        ts.append(f"    tier: {js_str(f['tier'])},")
        ts.append(f"    type: {js_str(f['type'])},")
        ts.append(f"    predicate: {js_str(f['predicate'])},")
        ts.append(f"    object: {js_str(f['object'])},")
        ts.append(f"    subject: {js_str(f['subject'])},")
        ts.append(f"    sourceChapter: {js_str(f['sourceChapter'])},")
        ts.append("  },")
    ts.append("];")
    ts.append("")

    # Axiom interactions
    ts.append("export const agenticAxiomInteractions: AxiomInteractions = {")
    ts.append("  reinforcing: [")
    ts.append("    {")
    ts.append('      pair: ["ORCHESTRATED COGNITION", "PRACTICAL ENGINEERING"],')
    ts.append(
        '      description: "Both demand concrete infrastructure over theoretical capability claims. When discussing AI systems, they expect specific orchestration patterns backed by implementation details.",'
    )
    ts.append("    },")
    ts.append("    {")
    ts.append('      pair: ["FAILURE RESILIENCE", "MEMORY PERSISTENCE"],')
    ts.append(
        '      description: "Both require robust state management and recovery mechanisms. They treat memory systems as critical infrastructure that must include failure recovery and data integrity protections.",'
    )
    ts.append("    },")
    ts.append("  ],")
    ts.append("  tension: [")
    ts.append("    {")
    ts.append('      pair: ["DYNAMIC REASONING", "STRUCTURED EXECUTION"],')
    ts.append(
        '      description: "Adaptability requirements conflict with systematic planning needs. Resolution: They implement structured frameworks that explicitly accommodate dynamic routing and conditional logic, building flexibility into the systematic approach.",'
    )
    ts.append("    },")
    ts.append("    {")
    ts.append('      pair: ["TRANSPARENCY IMPERATIVE", "SECURITY FOUNDATION"],')
    ts.append(
        '      description: "Visibility requirements can conflict with security constraints. Resolution: They implement role-based transparency where accountability mechanisms are tailored to user authorization levels, maintaining security while enabling appropriate oversight.",'
    )
    ts.append("    },")
    ts.append("  ],")
    ts.append("  cascades: [")
    ts.append("    {")
    ts.append('      chain: ["COLLABORATIVE INTELLIGENCE", "HUMAN AUTHORITY"],')
    ts.append(
        '      description: "Multi-agent systems amplify the need for human oversight. They resolve this by positioning humans as system architects who design agent collaboration patterns rather than micromanaging individual agent decisions.",'
    )
    ts.append("    },")
    ts.append("  ],")
    ts.append("};")
    ts.append("")

    output = "\n".join(ts) + "\n"
    with open(
        "C:/Users/Aarik/Anthropic/baselayer-website/data/agentic.ts",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(output)

    print(f"Generated agentic.ts: {len(output)} chars")
    print(f"  Brief paragraphs: {len(paragraphs)}")
    print(f"  Facts: {len(facts)}")


if __name__ == "__main__":
    main()
