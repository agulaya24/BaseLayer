#!/usr/bin/env python3
"""
Generate TypeScript data files for the Base Layer website from pipeline output.

Reads identity layer .md files and SQLite database, outputs .ts files matching
the website data format (see baselayer-website/data/franklin.ts for reference).

Usage:
    python -m scripts.generate_website_data --subject franklin --output path/to/output.ts
    python -m scripts.generate_website_data --subject franklin  # prints to stdout

Environment:
    MEMORY_SYSTEM_ROOT: Root directory for subject memory data.
                        Falls back to well-known paths (subjects/, root-level).
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Subject → directory mapping
# ---------------------------------------------------------------------------

# Known locations relative to the Anthropic workspace
SUBJECT_DIR_MAP = {
    "franklin": "subjects/franklin_memory",
    "douglass": "subjects/douglass_memory",
    "wollstonecraft": "subjects/wollstonecraft_memory",
    "roosevelt": "subjects/roosevelt_memory",
    "patents": "subjects/patent_memory",
    "lesswrong": "subjects/lesswrong_clt_memory",
    "buffett": "buffett_memory",
    "marks": "marks_memory",
    "user_a": "memory_system_v4",
    "paul_graham": "subjects/paul_graham_memory",
}


def resolve_memory_root(subject: str, env_root: Optional[str] = None) -> Path:
    """Resolve the memory root directory for a subject."""
    if env_root:
        root = Path(env_root)
        if root.exists():
            return root

    # Try MEMORY_SYSTEM_ROOT env var
    env = os.environ.get("MEMORY_SYSTEM_ROOT")
    if env:
        root = Path(env)
        if root.exists():
            return root

    # Try well-known paths
    anthropic_root = Path(__file__).resolve().parent.parent.parent  # memory_system/../..
    if subject in SUBJECT_DIR_MAP:
        candidate = anthropic_root / SUBJECT_DIR_MAP[subject]
        if candidate.exists():
            return candidate

    # Try generic pattern
    for pattern in [f"subjects/{subject}_memory", f"{subject}_memory"]:
        candidate = anthropic_root / pattern
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Cannot find memory root for subject '{subject}'. "
        f"Set MEMORY_SYSTEM_ROOT or ensure directory exists."
    )


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

def parse_anchors_md(text: str) -> list[dict]:
    """Parse anchors layer markdown into structured items."""
    items = []
    # Match **A1. NAME** or **A12. NAME** patterns
    pattern = r'\*\*A(\d+)\.\s+([A-Z][A-Z0-9 _-]+)\*\*\s*\n(.*?)(?=\n\*\*A\d+\.|## AXIOM INTERACTIONS|\*\*AXIOM INTERACTIONS|$)'
    matches = re.findall(pattern, text, re.DOTALL)

    for num, name, body in matches:
        item = {
            "id": f"A{num}",
            "name": name.strip().rstrip("*"),
            "description": "",
            "activeWhen": None,
        }
        lines = body.strip().split("\n")
        desc_lines = []
        for line in lines:
            line = line.strip()
            if line.lower().startswith("active when:"):
                item["activeWhen"] = line[len("Active when:"):].strip().lstrip(": ")
            elif line.lower().startswith("active_when:"):
                item["activeWhen"] = line[len("Active_when:"):].strip().lstrip(": ")
            elif line.lower().startswith("directive:"):
                item["directive"] = line[len("Directive:"):].strip().lstrip(": ")
            elif line.lower().startswith("false positive"):
                val = re.sub(r'^false.positive[_ ]?warning:?\s*', '', line, flags=re.IGNORECASE)
                item["falsePositive"] = val.strip().lstrip(": ")
            else:
                desc_lines.append(line)
        item["description"] = " ".join(desc_lines).strip()
        items.append(item)

    return items


def parse_core_md(text: str) -> list[dict]:
    """Parse core layer markdown into structured items."""
    items = []
    # Match **M1. NAME** or **C1. NAME** patterns
    pattern = r'\*\*([MC])(\d+)\.\s+([A-Z][A-Z0-9 _&-]+)\*\*\s*\n(.*?)(?=\n\*\*[MC]\d+\.|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)

    for prefix, num, name, body in matches:
        item_id = f"{prefix}{num}"
        item = {
            "id": item_id,
            "name": name.strip().rstrip("*"),
            "description": body.strip(),
        }
        items.append(item)

    return items


def parse_predictions_md(text: str) -> list[dict]:
    """Parse predictions layer markdown into structured items."""
    items = []
    # Match **P1. NAME**: or **P1. NAME** patterns
    pattern = r'\*\*P(\d+)\.\s+([A-Z][A-Z0-9 _-]+)\*\*:?\s*(.*?)(?=\n\*\*P\d+\.|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)

    for num, name, body in matches:
        item = {
            "id": f"P{num}",
            "name": name.strip().rstrip("*"),
            "description": "",
            "directive": None,
            "falsePositive": None,
            "thinData": False,
        }
        lines = body.strip().split("\n")
        desc_parts = []
        for line in lines:
            line = line.strip()
            if line.lower().startswith("detection:"):
                desc_parts.append(line)
            elif line.lower().startswith("directive:"):
                item["directive"] = line[len("Directive:"):].strip().lstrip(": ")
            elif line.lower().startswith("false positive"):
                val = re.sub(r'^false.positive[_ ]?warning:?\s*', '', line, flags=re.IGNORECASE)
                item["falsePositive"] = val.strip().lstrip(": ")
            elif "[THIN IN:" in line.upper() or "[THIN DATA" in line.upper():
                item["thinData"] = True
                desc_parts.append(line)
            else:
                desc_parts.append(line)

        # Combine description: first line is the trigger pattern, Detection line follows
        raw_desc = " ".join(desc_parts).strip()
        item["description"] = raw_desc

        # Check for THIN IN markers in body
        if "[THIN IN:" in body.upper():
            item["thinData"] = True

        items.append(item)

    return items


def parse_axiom_interactions_md(text: str) -> dict:
    """Parse axiom interactions from anchors markdown."""
    interactions = {"reinforcing": [], "tension": [], "cascades": []}

    # Find the AXIOM INTERACTIONS section
    interaction_section = ""
    if "AXIOM INTERACTIONS" in text.upper():
        idx = text.upper().index("AXIOM INTERACTIONS")
        interaction_section = text[idx:]

    if not interaction_section:
        return interactions

    # Parse interaction lines: look for patterns like A1 <-> A2 (tension) or A1 -> A2 (cascade/reinforcing)
    lines = interaction_section.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("**AXIOM"):
            continue
        if "When axioms conflict" in line:
            continue

        # Extract axiom references (A1, A2, etc.)
        axiom_refs = re.findall(r'\bA(\d+)\b', line)

        if len(axiom_refs) < 2:
            continue

        # Clean description: remove the leading **LABEL**: pattern
        desc = re.sub(r'^\*\*[^*]+\*\*:?\s*', '', line).strip()
        if not desc:
            desc = line

        if "↔" in line or "tension" in line.lower():
            interactions["tension"].append({
                "pair": [f"A{axiom_refs[0]}", f"A{axiom_refs[1]}"],
                "description": desc,
            })
        elif "→" in line or "cascade" in line.lower():
            interactions["cascades"].append({
                "chain": [f"A{r}" for r in axiom_refs],
                "description": desc,
            })
        elif "reinforce" in line.lower():
            interactions["reinforcing"].append({
                "pair": [f"A{axiom_refs[0]}", f"A{axiom_refs[1]}"],
                "description": desc,
            })
        else:
            # Default: if has arrow-like symbol, cascade; otherwise tension
            if "→" in line:
                interactions["cascades"].append({
                    "chain": [f"A{r}" for r in axiom_refs],
                    "description": desc,
                })
            else:
                interactions["tension"].append({
                    "pair": [f"A{axiom_refs[0]}", f"A{axiom_refs[1]}"],
                    "description": desc,
                })

    return interactions


def parse_brief_md(text: str, anchors: list[dict], core: list[dict], predictions: list[dict]) -> list[dict]:
    """Parse brief markdown into BriefParagraph structures with source layer tags."""
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3:].strip()

    # Strip header
    if text.startswith("## Injectable Block"):
        text = text[len("## Injectable Block"):].strip()

    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # Build keyword maps for source attribution
    anchor_keywords = {}
    for a in anchors:
        keywords = set()
        keywords.add(a["name"].lower())
        # Extract key terms from description
        for word in a["description"].lower().split():
            if len(word) > 5:
                keywords.add(word)
        anchor_keywords[a["id"]] = keywords

    core_keywords = {}
    for c in core:
        keywords = set()
        keywords.add(c["name"].lower())
        for word in c["description"].lower().split():
            if len(word) > 5:
                keywords.add(word)
        core_keywords[c["id"]] = keywords

    pred_keywords = {}
    for p in predictions:
        keywords = set()
        keywords.add(p["name"].lower())
        desc = p.get("description", "")
        for word in desc.lower().split():
            if len(word) > 5:
                keywords.add(word)
        pred_keywords[p["id"]] = keywords

    result = []
    for para in paragraphs:
        para_lower = para.lower()
        sources = set()
        related = []

        # Check anchors
        for aid, kws in anchor_keywords.items():
            matches = sum(1 for kw in kws if kw in para_lower)
            if matches >= 2:
                sources.add("A")
                related.append(aid)

        # Check core
        for cid, kws in core_keywords.items():
            matches = sum(1 for kw in kws if kw in para_lower)
            if matches >= 2:
                sources.add("C")
                related.append(cid)

        # Check predictions
        for pid, kws in pred_keywords.items():
            matches = sum(1 for kw in kws if kw in para_lower)
            if matches >= 2:
                sources.add("P")
                related.append(pid)

        # Heuristic fallbacks for common patterns
        if "[THIN DATA]" in para:
            sources.add("C")
        if "additional behavioral patterns" in para_lower:
            sources.add("A")
            sources.add("C")

        # If no sources matched, infer from content
        if not sources:
            if any(kw in para_lower for kw in ["predict", "when he", "detection", "directive", "reflex", "pattern"]):
                sources.add("P")
            if any(kw in para_lower for kw in ["axiom", "conviction", "foundational", "unshakeable"]):
                sources.add("A")
            if any(kw in para_lower for kw in ["context", "communication", "approach", "orientation"]):
                sources.add("C")
            # Default to A+C if still empty
            if not sources:
                sources = {"A", "C"}

        # Sort sources in canonical order
        source_order = {"A": 0, "C": 1, "P": 2}
        sorted_sources = sorted(sources, key=lambda s: source_order.get(s, 99))

        entry = {
            "text": para,
            "sources": sorted_sources,
        }
        if related:
            entry["relatedItems"] = sorted(set(related), key=lambda x: (x[0], int(re.search(r'\d+', x).group())))

        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def get_facts(db_path: Path) -> list[dict]:
    """Read all facts from memory_facts table."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, fact_text, category, confidence, knowledge_tier,
               fact_type, predicate, object_text, subject,
               source_conversation_id
        FROM memory_facts
        ORDER BY
            CASE knowledge_tier
                WHEN 'identity' THEN 0
                WHEN 'situational' THEN 1
                WHEN 'context' THEN 2
                ELSE 3
            END,
            confidence DESC
    """).fetchall()

    # Build conversation title map
    titles = {}
    try:
        title_rows = conn.execute("SELECT id, title FROM conversations").fetchall()
        for r in title_rows:
            titles[r["id"]] = r["title"]
    except Exception:
        pass

    conn.close()

    facts = []
    for r in rows:
        source_chapter = titles.get(r["source_conversation_id"], "")
        facts.append({
            "id": r["id"][:8] if r["id"] and len(r["id"]) > 8 else r["id"],
            "text": r["fact_text"],
            "category": r["category"] or "unknown",
            "confidence": round(r["confidence"], 2) if r["confidence"] else 0.0,
            "tier": r["knowledge_tier"] or "untiered",
            "type": r["fact_type"] if r["fact_type"] != "unclassified" else None,
            "predicate": r["predicate"],
            "object": r["object_text"],
            "subject": r["subject"] or "user",
            "sourceChapter": source_chapter,
        })

    return facts


def get_provenance(db_path: Path) -> dict:
    """Read layer_claim_provenance and build claim_id → [fact_id] mapping."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT layer_name, claim_id, claim_text, fact_id, link_method, similarity_score, rank_in_claim
        FROM layer_claim_provenance
        ORDER BY claim_id, rank_in_claim
    """).fetchall()
    conn.close()

    # Group by claim_id
    provenance = {}
    for r in rows:
        cid = r["claim_id"]
        if cid not in provenance:
            provenance[cid] = []
        provenance[cid].append({
            "fact_id": r["fact_id"][:8] if r["fact_id"] and len(r["fact_id"]) > 8 else r["fact_id"],
            "full_fact_id": r["fact_id"],
            "claim_text": r["claim_text"],
            "link_method": r["link_method"],
            "similarity": round(r["similarity_score"], 4) if r["similarity_score"] else None,
            "layer": r["layer_name"],
        })

    return provenance


def get_vector_traces(db_path: Path, claim_id: str, facts_by_id: dict, facts_by_short_id: dict, conv_titles: dict) -> list[dict]:
    """Get vector provenance traces for a claim, returning Trace-shaped dicts."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT lcp.fact_id, lcp.similarity_score, lcp.link_method,
               mf.fact_text, mf.confidence, mf.knowledge_tier, mf.category, mf.source_conversation_id
        FROM layer_claim_provenance lcp
        JOIN memory_facts mf ON mf.id = lcp.fact_id
        WHERE lcp.claim_id = ?
          AND lcp.link_method = 'vector'
        ORDER BY lcp.similarity_score DESC
        LIMIT 5
    """, (claim_id,)).fetchall()
    conn.close()

    traces = []
    for r in rows:
        source_chapter = conv_titles.get(r["source_conversation_id"], "")
        traces.append({
            "factId": r["fact_id"][:8] if r["fact_id"] and len(r["fact_id"]) > 8 else r["fact_id"],
            "text": r["fact_text"],
            "sourceChapter": "",
            "confidence": round(r["similarity_score"], 3) if r["similarity_score"] else 0.0,
            "tier": r["knowledge_tier"] or "untiered",
            "category": r["category"] or "unknown",
            "similarity": round(r["similarity_score"], 3) if r["similarity_score"] else 0.0,
            "source": source_chapter,
        })

    return traces


def get_authoring_provenance_ids(db_path: Path, claim_id: str) -> list[str]:
    """Get authoring provenance fact IDs for a claim."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT fact_id FROM layer_claim_provenance
        WHERE claim_id = ? AND link_method = 'authoring'
        ORDER BY rank_in_claim
    """, (claim_id,)).fetchall()
    conn.close()
    return [r[0][:8] if r[0] and len(r[0]) > 8 else r[0] for r in rows]


def get_conv_titles(db_path: Path) -> dict:
    """Get conversation id → title mapping."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT id, title FROM conversations").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        conn.close()
        return {}


# ---------------------------------------------------------------------------
# Trace building
# ---------------------------------------------------------------------------

def build_traces_for_item(item_id: str, db_path: Path, conv_titles: dict) -> tuple[list[str], list[dict]]:
    """Build provenance list and traces for a layer item."""
    # Get authoring provenance
    prov_ids = get_authoring_provenance_ids(db_path, item_id)

    # Get vector traces
    traces = get_vector_traces(db_path, item_id, {}, {}, conv_titles)

    return prov_ids, traces


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def compute_stats(db_path: Path, anchors: list, core: list, predictions: list) -> dict:
    """Compute pipeline stats from database."""
    conn = sqlite3.connect(str(db_path))

    total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]

    tier_counts = {}
    for row in conn.execute("SELECT knowledge_tier, COUNT(*) FROM memory_facts GROUP BY knowledge_tier").fetchall():
        tier_counts[row[0] or "untiered"] = row[1]

    # Count chapters/conversations
    try:
        chapters = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    except Exception:
        chapters = 0

    conn.close()

    return {
        "chapters": chapters,
        "totalFacts": total,
        "activeFacts": active,
        "identityTier": tier_counts.get("identity", 0),
        "situationalTier": tier_counts.get("situational", 0),
        "contextTier": tier_counts.get("context", 0),
        "anchors": len(anchors),
        "contextModes": len([c for c in core if c["id"].startswith("C")]),
        "predictions": len(predictions),
        "anchorsScore": 85,
        "coreScore": 85,
        "predictionsScore": 85,
        "pipelineCost": 0.60,
        "model": "claude-sonnet-4-20250514",
        "provenanceMethod": "citation_api",
    }


# ---------------------------------------------------------------------------
# TypeScript generation
# ---------------------------------------------------------------------------

def escape_ts_string(s: str) -> str:
    """Escape a string for TypeScript output."""
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def ts_string(s: str) -> str:
    """Format a value as a TypeScript string literal."""
    if s is None:
        return "null"
    return f'"{escape_ts_string(s)}"'


def ts_string_or_null(s) -> str:
    """Format a value as TS string or null."""
    if s is None:
        return "null"
    return f'"{escape_ts_string(str(s))}"'


def generate_typescript(
    subject: str,
    anchors: list[dict],
    core: list[dict],
    predictions: list[dict],
    brief: list[dict],
    facts: list[dict],
    interactions: dict,
    stats: dict,
    db_path: Path,
) -> str:
    """Generate the full TypeScript file content."""
    conv_titles = get_conv_titles(db_path)

    lines = []

    # Header
    lines.append(f"// Auto-generated from {subject} pipeline output")
    lines.append(f"// Source: subjects/{subject}_memory/data/identity_layers/ + SQLite")
    lines.append("// Generated by generate_website_data.py")
    lines.append("")

    # Interfaces
    lines.append("export interface Trace {")
    lines.append("  factId: string;")
    lines.append("  text: string;")
    lines.append("  sourceChapter: string;")
    lines.append("  confidence: number;")
    lines.append("  tier: string;")
    lines.append("  category: string;")
    lines.append("  similarity: number;")
    lines.append("  source?: string;")
    lines.append("}")
    lines.append("")

    lines.append("export interface LayerItem {")
    lines.append("  id: string;")
    lines.append("  name: string;")
    lines.append("  description: string;")
    lines.append("  activeWhen?: string;")
    lines.append("  directive?: string;")
    lines.append("  falsePositive?: string;")
    lines.append("  thinData?: boolean;")
    lines.append("  provenance?: string[];")
    lines.append("  traces: Trace[];")
    lines.append("}")
    lines.append("")

    lines.append("export interface Fact {")
    lines.append("  id: string;")
    lines.append("  text: string;")
    lines.append("  category: string;")
    lines.append("  confidence: number;")
    lines.append("  tier: string;")
    lines.append("  type: string | null;")
    lines.append("  predicate: string | null;")
    lines.append("  object: string | null;")
    lines.append("  subject: string | null;")
    lines.append("  sourceChapter: string;")
    lines.append("}")
    lines.append("")

    lines.append("export interface BriefParagraph {")
    lines.append("  text: string;")
    lines.append('  sources: ("A" | "C" | "P")[];')
    lines.append("  relatedItems?: string[];")
    lines.append("}")
    lines.append("")

    lines.append("export interface AxiomInteraction {")
    lines.append("  pair: string[];")
    lines.append("  description: string;")
    lines.append("}")
    lines.append("")

    lines.append("export interface CascadeInteraction {")
    lines.append("  chain: string[];")
    lines.append("  description: string;")
    lines.append("}")
    lines.append("")

    lines.append("export interface AxiomInteractions {")
    lines.append("  reinforcing: AxiomInteraction[];")
    lines.append("  tension: AxiomInteraction[];")
    lines.append("  cascades: CascadeInteraction[];")
    lines.append("}")
    lines.append("")

    # Brief
    lines.append(f"export const {subject}Brief: BriefParagraph[] = [")
    for bp in brief:
        lines.append("  {")
        lines.append(f'    text: {ts_string(bp["text"])},')
        sources_str = ", ".join(f'"{s}"' for s in bp["sources"])
        lines.append(f"    sources: [{sources_str}],")
        if bp.get("relatedItems"):
            items_str = ", ".join(f'"{i}"' for i in bp["relatedItems"])
            lines.append(f"    relatedItems: [{items_str}],")
        lines.append("  },")
    lines.append("];")
    lines.append("")

    # Stats
    lines.append(f"export const {subject}Stats = {{")
    for key, val in stats.items():
        if isinstance(val, str):
            lines.append(f'  {key}: {ts_string(val)},')
        elif isinstance(val, float):
            lines.append(f"  {key}: {val},")
        else:
            lines.append(f"  {key}: {val},")
    lines.append("};")
    lines.append("")

    # Anchors
    lines.append(f"export const {subject}Anchors: LayerItem[] = [")
    for item in anchors:
        prov_ids, traces = build_traces_for_item(item["id"], db_path, conv_titles)
        lines.append("  {")
        lines.append(f'    id: {ts_string(item["id"])},')
        lines.append(f'    name: {ts_string(item["name"])},')
        lines.append(f'    description: {ts_string(item["description"])},')
        if item.get("activeWhen"):
            lines.append(f'    activeWhen: {ts_string(item["activeWhen"])},')
        if prov_ids:
            prov_str = ", ".join(f'"{pid}"' for pid in prov_ids)
            lines.append(f"    provenance: [{prov_str}],")
        lines.append("    traces: [")
        for t in traces:
            lines.append(f'    {{ factId: {ts_string(t["factId"])}, text: {ts_string(t["text"])}, sourceChapter: {ts_string(t["sourceChapter"])}, confidence: {t["confidence"]}, tier: {ts_string(t["tier"])}, category: {ts_string(t["category"])}, similarity: {t["similarity"]}, source: {ts_string(t.get("source", ""))} }},')
        lines.append("  ],")
        lines.append("  },")
    lines.append("];")
    lines.append("")

    # Core
    lines.append(f"export const {subject}Core: LayerItem[] = [")
    for item in core:
        prov_ids, traces = build_traces_for_item(item["id"], db_path, conv_titles)
        lines.append("  {")
        lines.append(f'    id: {ts_string(item["id"])},')
        lines.append(f'    name: {ts_string(item["name"])},')
        lines.append(f'    description: {ts_string(item["description"])},')
        if prov_ids:
            prov_str = ", ".join(f'"{pid}"' for pid in prov_ids)
            lines.append(f"    provenance: [{prov_str}],")
        lines.append("    traces: [")
        for t in traces:
            lines.append(f'    {{ factId: {ts_string(t["factId"])}, text: {ts_string(t["text"])}, sourceChapter: {ts_string(t["sourceChapter"])}, confidence: {t["confidence"]}, tier: {ts_string(t["tier"])}, category: {ts_string(t["category"])}, similarity: {t["similarity"]}, source: {ts_string(t.get("source", ""))} }},')
        lines.append("  ],")
        lines.append("  },")
    lines.append("];")
    lines.append("")

    # Predictions
    lines.append(f"export const {subject}Predictions: LayerItem[] = [")
    for item in predictions:
        prov_ids, traces = build_traces_for_item(item["id"], db_path, conv_titles)
        lines.append("  {")
        lines.append(f'    id: {ts_string(item["id"])},')
        lines.append(f'    name: {ts_string(item["name"])},')
        lines.append(f'    description: {ts_string(item["description"])},')
        if item.get("directive"):
            lines.append(f'    directive: {ts_string(item["directive"])},')
        if item.get("falsePositive"):
            lines.append(f'    falsePositive: {ts_string(item["falsePositive"])},')
        if prov_ids:
            prov_str = ", ".join(f'"{pid}"' for pid in prov_ids)
            lines.append(f"    provenance: [{prov_str}],")
        lines.append("    traces: [")
        for t in traces:
            lines.append(f'    {{ factId: {ts_string(t["factId"])}, text: {ts_string(t["text"])}, sourceChapter: {ts_string(t["sourceChapter"])}, confidence: {t["confidence"]}, tier: {ts_string(t["tier"])}, category: {ts_string(t["category"])}, similarity: {t["similarity"]}, source: {ts_string(t.get("source", ""))} }},')
        lines.append("  ],")
        lines.append("  },")
    lines.append("];")
    lines.append("")

    # Axiom interactions
    lines.append("export const axiomInteractions: AxiomInteractions = {")
    lines.append("  reinforcing: [")
    for inter in interactions.get("reinforcing", []):
        pair_str = ", ".join(f'"{p}"' for p in inter["pair"])
        lines.append(f'    {{ pair: [{pair_str}], description: {ts_string(inter["description"])} }},')
    lines.append("  ],")
    lines.append("  tension: [")
    for inter in interactions.get("tension", []):
        pair_str = ", ".join(f'"{p}"' for p in inter["pair"])
        lines.append(f'    {{ pair: [{pair_str}], description: {ts_string(inter["description"])} }},')
    lines.append("  ],")
    lines.append("  cascades: [")
    for inter in interactions.get("cascades", []):
        chain_str = ", ".join(f'"{c}"' for c in inter["chain"])
        lines.append(f'    {{ chain: [{chain_str}], description: {ts_string(inter["description"])} }},')
    lines.append("  ],")
    lines.append("};")
    lines.append("")

    # Facts
    lines.append(f"export const {subject}Facts: Fact[] = [")
    for f in facts:
        lines.append(f'  {{ id: {ts_string(f["id"])}, text: {ts_string(f["text"])}, category: {ts_string(f["category"])}, confidence: {f["confidence"]}, tier: {ts_string(f["tier"])}, type: {ts_string_or_null(f["type"])}, predicate: {ts_string_or_null(f["predicate"])}, object: {ts_string_or_null(f["object"])}, subject: {ts_string_or_null(f["subject"])}, sourceChapter: {ts_string(f["sourceChapter"])} }},')
    lines.append("];")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate TypeScript data files for the Base Layer website from pipeline output."
    )
    parser.add_argument(
        "--subject", required=True,
        help="Subject key (e.g. franklin, douglass, marks, buffett)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output .ts file path. If omitted, prints to stdout."
    )
    parser.add_argument(
        "--root", default=None,
        help="Override MEMORY_SYSTEM_ROOT for the subject's data directory."
    )
    args = parser.parse_args()

    subject = args.subject

    # Resolve paths
    memory_root = resolve_memory_root(subject, args.root)
    layers_dir = memory_root / "data" / "identity_layers"
    db_path = memory_root / "data" / "database" / "memory.db"

    if not layers_dir.exists():
        print(f"Error: Identity layers directory not found: {layers_dir}", file=sys.stderr)
        sys.exit(1)

    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    # Find layer files (prefer v4, fall back to non-versioned)
    def find_layer_file(name: str) -> Optional[Path]:
        for suffix in ["_v5_clean.md", "_v5.md", "_v4.md", "_v3.md", "_v2.md", ".md"]:
            candidate = layers_dir / f"{name}{suffix}"
            if candidate.exists():
                return candidate
        return None

    anchors_file = find_layer_file("anchors")
    core_file = find_layer_file("core")
    predictions_file = find_layer_file("predictions")
    brief_file = find_layer_file("brief")

    if not anchors_file:
        print(f"Error: No anchors layer file found in {layers_dir}", file=sys.stderr)
        sys.exit(1)
    if not core_file:
        print(f"Error: No core layer file found in {layers_dir}", file=sys.stderr)
        sys.exit(1)
    if not predictions_file:
        print(f"Error: No predictions layer file found in {layers_dir}", file=sys.stderr)
        sys.exit(1)
    if not brief_file:
        print(f"Error: No brief file found in {layers_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading layers from: {layers_dir}", file=sys.stderr)
    print(f"  Anchors:     {anchors_file.name}", file=sys.stderr)
    print(f"  Core:        {core_file.name}", file=sys.stderr)
    print(f"  Predictions: {predictions_file.name}", file=sys.stderr)
    print(f"  Brief:       {brief_file.name}", file=sys.stderr)
    print(f"Database: {db_path}", file=sys.stderr)

    # Parse layers
    anchors_text = anchors_file.read_text(encoding="utf-8")
    core_text = core_file.read_text(encoding="utf-8")
    predictions_text = predictions_file.read_text(encoding="utf-8")
    brief_text = brief_file.read_text(encoding="utf-8")

    anchors = parse_anchors_md(anchors_text)
    core = parse_core_md(core_text)
    predictions = parse_predictions_md(predictions_text)

    print(f"Parsed: {len(anchors)} anchors, {len(core)} core items, {len(predictions)} predictions", file=sys.stderr)

    # Parse brief with layer references
    brief = parse_brief_md(brief_text, anchors, core, predictions)
    print(f"Parsed: {len(brief)} brief paragraphs", file=sys.stderr)

    # Parse axiom interactions from anchors
    interactions = parse_axiom_interactions_md(anchors_text)
    n_interactions = len(interactions["reinforcing"]) + len(interactions["tension"]) + len(interactions["cascades"])
    print(f"Parsed: {n_interactions} axiom interactions", file=sys.stderr)

    # Read facts
    facts = get_facts(db_path)
    print(f"Read: {len(facts)} facts from database", file=sys.stderr)

    # Compute stats
    stats = compute_stats(db_path, anchors, core, predictions)

    # Generate TypeScript
    ts_content = generate_typescript(
        subject=subject,
        anchors=anchors,
        core=core,
        predictions=predictions,
        brief=brief,
        facts=facts,
        interactions=interactions,
        stats=stats,
        db_path=db_path,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ts_content, encoding="utf-8")
        print(f"Written: {output_path} ({len(ts_content)} bytes)", file=sys.stderr)
    else:
        sys.stdout.write(ts_content)


if __name__ == "__main__":
    main()
