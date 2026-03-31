#!/usr/bin/env python3
"""
Seed industry pages with enriched data (full traceability).

Reads identity layer .md files and SQLite database, pushes enriched data
to the Base Layer website via the /api/industry/seed endpoint.

Usage:
    python -m baselayer.seed_industry --subject dan_shipper --slug dan-shipper --password "REDACTED"
    python -m baselayer.seed_industry --subject dan_shipper --slug dan-shipper --password "REDACTED" --dry-run

Environment:
    INDUSTRY_ADMIN_SECRET: Required. Admin secret for the seed API.
    BASE_LAYER_URL: Optional. Defaults to https://base-layer.ai
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Subject directory resolution
# ---------------------------------------------------------------------------

ANTHROPIC_ROOT = Path(os.environ.get("BASELAYER_ROOT", "C:/Users/Aarik/Anthropic"))


def resolve_subject_dir(subject: str) -> Path:
    """Find the subject's memory directory. Checks subjects table first, then filesystem."""
    # S98 Phase 3B: Try subjects table first
    try:
        main_db = ANTHROPIC_ROOT / "memory_system" / "data" / "database" / "memory.db"
        if main_db.exists():
            import sqlite3
            conn = sqlite3.connect(str(main_db), timeout=1)
            row = conn.execute("SELECT environment_dir FROM subjects WHERE id = ?", (subject,)).fetchone()
            conn.close()
            if row and row[0]:
                env_path = ANTHROPIC_ROOT / "subjects" / row[0]
                if env_path.exists():
                    return env_path
    except Exception:
        pass

    # Fallback: filesystem search
    candidates = [
        ANTHROPIC_ROOT / "subjects" / f"{subject}_memory",
        ANTHROPIC_ROOT / "subjects" / subject,
        ANTHROPIC_ROOT / f"{subject}_memory",
        ANTHROPIC_ROOT / "memory_system_v4",  # user_a
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"Cannot find memory directory for subject '{subject}'")


# ---------------------------------------------------------------------------
# Markdown parsing (from generate_website_data.py)
# ---------------------------------------------------------------------------


def _extract_body(text: str) -> str:
    """Extract body content from a layer file, stripping any header format.

    Supports both:
    - S98 YAML frontmatter: ---\\nyaml\\n---\\n\\n## Injectable Block\\n\\ncontent
    - Legacy comment header: # comment\\n# comment\\n\\n---\\n\\n## Injectable Block\\n\\ncontent
    """
    # Find ## Injectable Block and return everything after it
    marker = "## Injectable Block"
    idx = text.find(marker)
    if idx >= 0:
        return text[idx + len(marker):].strip()
    # Fallback: strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            return text[end + 3:].strip()
    # Fallback: strip comment header
    lines = text.split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        if not line.startswith("#") and line.strip():
            body_start = i
            break
    return "\n".join(lines[body_start:]).strip()


def _extract_provenance_from_line(line: str) -> list[str]:
    """Extract provenance fact IDs from a 'provenance: [F-xxx, F-yyy]' line."""
    match = re.match(r'^provenance:\s*\[(.+)\]', line, re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1)
    ids = [fid.strip().lstrip("F-")[:8] for fid in raw.split(",") if fid.strip()]
    return ids


def parse_anchors_md(text: str) -> list[dict]:
    items = []
    # Universal separator: match ANY non-alphanumeric characters between ID and name
    _SEP = r'[^A-Za-z0-9\n]+'
    pattern = rf'\*\*A(\d+){_SEP}\s*([A-Z][A-Z0-9 _,-]+)\*\*\s*\n(.*?)(?=\n\*\*A\d+|## AXIOM|\*\*AXIOM|$)'
    matches = re.findall(pattern, text, re.DOTALL)
    for num, name, body in matches:
        item = {"id": f"A{num}", "name": name.strip().rstrip("*"), "description": "", "activeWhen": None}
        lines = body.strip().split("\n")
        desc_lines = []
        for line in lines:
            line = line.strip()
            if line.lower().startswith("active when:") or line.lower().startswith("active_when:"):
                item["activeWhen"] = re.sub(r'^active[_ ]?when:?\s*', '', line, flags=re.IGNORECASE).strip()
            elif line.lower().startswith("directive:"):
                item["directive"] = line[len("Directive:"):].strip().lstrip(": ")
            elif line.lower().startswith("false positive"):
                val = re.sub(r'^false.positive[_ ]?warning:?\s*', '', line, flags=re.IGNORECASE)
                item["falsePositive"] = val.strip().lstrip(": ")
            elif line.lower().startswith("provenance:"):
                prov_ids = _extract_provenance_from_line(line)
                if prov_ids:
                    item["provenance"] = prov_ids
            else:
                desc_lines.append(line)
        item["description"] = " ".join(desc_lines).strip()
        items.append(item)

    # Also match heading-style: ## A1, ### A1, #### A1 with any separator
    if not items:
        _SEP_H = r'[^A-Za-z0-9\n]+'
        h_pattern = r'(?:#{2,4})\s+A(\d+)' + _SEP_H + r'\s*([A-Z][A-Z0-9 _,-]+)\s*\n(.*?)(?=\n(?:#{2,4})\s+A\d+|\n(?:#{2,4})\s+AXIOM|\Z)'
        h_matches = re.findall(h_pattern, text, re.DOTALL)
        for num, name, body in h_matches:
            item = {"id": f"A{num}", "name": name.strip(), "description": "", "activeWhen": None}
            lines = body.strip().split("\n")
            desc_lines = []
            for line in lines:
                line = line.strip()
                if line.lower().startswith("active when:") or line.lower().startswith("*active when:"):
                    item["activeWhen"] = re.sub(r'^\*?active[_ ]?when:?\s*', '', line, flags=re.IGNORECASE).strip().rstrip("*")
                elif line.lower().startswith("provenance:"):
                    prov_ids = _extract_provenance_from_line(line)
                    if prov_ids:
                        item["provenance"] = prov_ids
                else:
                    desc_lines.append(line)
            item["description"] = " ".join(desc_lines).strip()
            if item["description"]:
                items.append(item)

    return items


def parse_core_md(text: str) -> list[dict]:
    items = []

    def _extract_body(body: str) -> tuple[str, list[str] | None]:
        desc_lines = []
        prov = None
        for line in body.strip().split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("provenance:"):
                prov_ids = _extract_provenance_from_line(stripped)
                if prov_ids:
                    prov = prov_ids
            elif not stripped.startswith("**") and not stripped.startswith("##"):
                desc_lines.append(stripped)
        return " ".join(desc_lines).strip(), prov

    # Universal separator: match ANY non-alphanumeric characters between ID and name
    SEP = r'[^A-Za-z0-9\n]+'

    # Match numbered items: **C1. NAME** or **M1 — NAME** (bold style)
    pattern = r'\*\*([MC])(\d+)' + SEP + r'\s*([A-Z][A-Z0-9 _&/,-]+)\*\*\s*\n(.*?)(?=\n\*\*[MC]\d+|\n(?:#{2,4})\s+[MC]\d+|\n\*\*[A-Z][A-Z ]+\*\*|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)
    for prefix, num, name, body in matches:
        item = {"id": f"{prefix}{num}", "name": name.strip().rstrip("*"), "description": ""}
        item["description"], prov = _extract_body(body)
        if prov:
            item["provenance"] = prov
        items.append(item)

    # Match numbered items: ## M1. NAME or ### M1 — NAME (heading style, h2/h3/h4)
    heading_pattern = r'(?:#{2,4})\s+([MC])(\d+)' + SEP + r'\s*([A-Z][A-Z0-9 _&/,-]+)\s*\n(.*?)(?=\n(?:#{2,4})\s+[MC]\d+|\n(?:#{2,4})\s+[A-Z]|\Z)'
    heading_matches = re.findall(heading_pattern, text, re.DOTALL)
    seen_ids = {it["id"] for it in items}
    for prefix, num, name, body in heading_matches:
        item_id = f"{prefix}{num}"
        if item_id in seen_ids:
            continue
        item = {"id": item_id, "name": name.strip().rstrip("*"), "description": ""}
        item["description"], prov = _extract_body(body)
        if prov:
            item["provenance"] = prov
        if item["description"]:
            items.append(item)
            seen_ids.add(item_id)

    # Match inline bold items: **C1 — NAME:** description on same line
    # These appear as sub-items within a parent section (e.g., context modes inside M2)
    inline_sep = r'(?:\.|\s*[—–:|\-]\s*)'
    inline_pattern = rf'\*\*([MC])(\d+){inline_sep}\s*([^*]+?)\*\*:?\s*(.*?)(?=\n\*\*[MC]\d+|\n##|\Z)'
    inline_matches = re.findall(inline_pattern, text, re.DOTALL)
    seen_ids = {it["id"] for it in items}
    for prefix, num, name, body in inline_matches:
        item_id = f"{prefix}{num}"
        if item_id in seen_ids:
            continue
        clean_name = name.strip().rstrip("*:").strip()
        # Only add if it looks like a real item (not already captured as heading)
        if not clean_name or clean_name == clean_name.lower():
            continue
        item = {"id": item_id, "name": clean_name, "description": ""}
        item["description"], prov = _extract_body(body)
        if prov:
            item["provenance"] = prov
        if item["description"]:
            items.append(item)
            seen_ids.add(item_id)

    # Match unnumbered items: **COMMUNICATION APPROACH**, **NARRATIVE ORIENTATION**, etc.
    unnum_pattern = r'\*\*([A-Z][A-Z ]+)\*\*\s*\n(.*?)(?=\n\*\*[MC]\d+|\n#{2,4}\s+[MC]\d+|\n\*\*[A-Z][A-Z ]+\*\*|\Z)'
    unnum_matches = re.findall(unnum_pattern, text, re.DOTALL)
    for i, (name, body) in enumerate(unnum_matches):
        if any(name.strip() in it["name"] for it in items):
            continue
        item_id = f"U{i+1}"
        item = {"id": item_id, "name": name.strip(), "description": ""}
        item["description"], prov = _extract_body(body)
        if prov:
            item["provenance"] = prov
        if item["description"]:
            items.append(item)

    return items


def parse_predictions_md(text: str) -> list[dict]:
    items = []
    # Universal separator
    _SEP = r'[^A-Za-z0-9\n]+'
    pattern = rf'\*\*P(\d+){_SEP}\s*([A-Z][A-Z0-9 _,-]+)\*\*:?\s*(.*?)(?=\n\*\*P\d+|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)
    for num, name, body in matches:
        item = {"id": f"P{num}", "name": name.strip().rstrip("*"), "description": "", "directive": None, "falsePositive": None, "thinData": False}
        lines = body.strip().split("\n")
        desc_parts = []
        for line in lines:
            line = line.strip()
            if line.lower().startswith("directive:"):
                item["directive"] = line[len("Directive:"):].strip().lstrip(": ")
            elif line.lower().startswith("false positive"):
                val = re.sub(r'^false.positive[_ ]?warning:?\s*', '', line, flags=re.IGNORECASE)
                item["falsePositive"] = val.strip().lstrip(": ")
            elif line.lower().startswith("provenance:"):
                prov_ids = _extract_provenance_from_line(line)
                if prov_ids:
                    item["provenance"] = prov_ids
            elif "[THIN IN:" in line.upper() or "[THIN DATA" in line.upper():
                item["thinData"] = True
                desc_parts.append(line)
            else:
                desc_parts.append(line)
        item["description"] = " ".join(desc_parts).strip()
        if "[THIN IN:" in body.upper():
            item["thinData"] = True
        items.append(item)
    return items


def parse_axiom_interactions_md(text: str) -> dict:
    interactions = {"reinforcing": [], "tension": [], "cascades": []}
    if "AXIOM INTERACTIONS" not in text.upper():
        return interactions
    idx = text.upper().index("AXIOM INTERACTIONS")
    section = text[idx:]
    for line in section.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("**AXIOM") or "When axioms conflict" in line:
            continue
        axiom_refs = re.findall(r'\bA(\d+)\b', line)
        if len(axiom_refs) < 2:
            continue
        desc = re.sub(r'^\*\*[^*]+\*\*:?\s*', '', line).strip() or line
        if "tension" in line.lower() or "\u2194" in line:
            interactions["tension"].append({"pair": [f"A{axiom_refs[0]}", f"A{axiom_refs[1]}"], "description": desc})
        elif "cascade" in line.lower() or "->" in line:
            interactions["cascades"].append({"chain": [f"A{r}" for r in axiom_refs], "description": desc})
        elif "reinforce" in line.lower():
            interactions["reinforcing"].append({"pair": [f"A{axiom_refs[0]}", f"A{axiom_refs[1]}"], "description": desc})
        else:
            interactions["tension"].append({"pair": [f"A{axiom_refs[0]}", f"A{axiom_refs[1]}"], "description": desc})
    return interactions


def parse_brief_md(text: str, anchors: list, core: list, predictions: list) -> list[dict]:
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3:].strip()
    if text.startswith("## Injectable Block"):
        text = text[len("## Injectable Block"):].strip()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # Build keyword maps
    def build_kw_map(items):
        m = {}
        for item in items:
            # Use name words + first 8 distinctive words from description (not all)
            name_words = {w.lower() for w in item["name"].split() if len(w) > 3}
            desc = item.get("description", "").lower()
            # Extract distinctive words (7+ chars, not common)
            common = {"through", "between", "rather", "whether", "without", "because", "another", "against",
                       "towards", "something", "everything", "anything", "however", "although", "specifically",
                       "particularly", "fundamentally", "simultaneously", "understanding", "relationship",
                       "information", "experience", "approach", "process", "pattern", "system", "decision"}
            desc_words = [w.strip(".,;:!?()\"'") for w in desc.split() if len(w) > 6 and w.strip(".,;:!?()\"'").lower() not in common]
            # Take only the first 8 most distinctive
            kws = name_words | set(desc_words[:8])
            m[item["id"]] = kws
        return m

    anchor_kw = build_kw_map(anchors)
    core_kw = build_kw_map(core)
    pred_kw = build_kw_map(predictions)

    result = []
    for para in paragraphs:
        pl = para.lower()
        sources = set()
        related = []
        # Require 3+ keyword matches (stricter than 2) to reduce false positives
        for aid, kws in anchor_kw.items():
            if sum(1 for kw in kws if kw in pl) >= 3:
                sources.add("A")
                related.append(aid)
        for cid, kws in core_kw.items():
            if sum(1 for kw in kws if kw in pl) >= 3:
                sources.add("C")
                related.append(cid)
        for pid, kws in pred_kw.items():
            if sum(1 for kw in kws if kw in pl) >= 3:
                sources.add("P")
                related.append(pid)
        if "[THIN DATA]" in para:
            sources.add("C")
        if "additional behavioral patterns" in pl:
            sources.update({"A", "C"})
        if not sources:
            if any(kw in pl for kw in ["predict", "when he", "when she", "when they", "detection", "directive"]):
                sources.add("P")
            if any(kw in pl for kw in ["axiom", "conviction", "foundational"]):
                sources.add("A")
            if any(kw in pl for kw in ["context", "communication", "approach"]):
                sources.add("C")
            if not sources:
                sources = {"A", "C"}
        order = {"A": 0, "C": 1, "P": 2}
        entry = {"text": para, "sources": sorted(sources, key=lambda s: order.get(s, 99))}
        if related:
            entry["relatedItems"] = sorted(set(related), key=lambda x: (x[0], int(re.search(r'\d+', x).group())))
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def get_conv_titles(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT id, title FROM conversations").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        conn.close()
        return {}


def get_facts(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, fact_text, category, confidence, knowledge_tier,
               fact_type, predicate, object_text, subject, source_conversation_id
        FROM memory_facts
        ORDER BY
            CASE knowledge_tier WHEN 'identity' THEN 0 WHEN 'situational' THEN 1 WHEN 'context' THEN 2 ELSE 3 END,
            confidence DESC
    """).fetchall()
    titles = {}
    try:
        for r in conn.execute("SELECT id, title FROM conversations").fetchall():
            titles[r["id"]] = r["title"]
    except Exception:
        pass
    conn.close()
    facts = []
    for r in rows:
        facts.append({
            "id": r["id"][:8] if r["id"] and len(r["id"]) > 8 else r["id"],
            "fact_text": r["fact_text"],
            "category": r["category"] or "unknown",
            "confidence": round(r["confidence"], 2) if r["confidence"] else 0.0,
            "knowledge_tier": r["knowledge_tier"] or "untiered",
            "type": r["fact_type"] if r["fact_type"] != "unclassified" else None,
            "predicate": r["predicate"],
            "object_text": r["object_text"],
            "subject": r["subject"] or "user",
            "source": get_conv_titles(db_path).get(r["source_conversation_id"], ""),
        })
    return facts


def get_predicate_distribution(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT predicate, category, COUNT(*) as cnt
        FROM memory_facts
        WHERE predicate IS NOT NULL AND predicate != 'unknown'
        GROUP BY predicate, category
        ORDER BY cnt DESC
    """).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    conn.close()

    predicates = []
    categories = {}
    unique_preds = set()
    for r in rows:
        predicates.append({"predicate": r["predicate"], "count": r["cnt"], "category": r["category"] or "unknown"})
        unique_preds.add(r["predicate"])
        cat = r["category"] or "unknown"
        categories[cat] = categories.get(cat, 0) + r["cnt"]

    cat_list = [{"category": k, "count": v, "pct": round(v / total * 100, 1) if total else 0} for k, v in sorted(categories.items(), key=lambda x: -x[1])]

    return {
        "totalFacts": total,
        "uniquePredicates": len(unique_preds),
        "predicates": predicates,
        "categories": cat_list,
    }


def build_traces_for_item(item_id: str, db_path: Path, conv_titles: dict) -> tuple[list[str], list[dict]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Authoring + citation_api provenance (both are API-traced)
    # Query both plain and "_cite" suffix formats for backwards compatibility
    auth_rows = conn.execute("""
        SELECT fact_id, link_method FROM layer_claim_provenance
        WHERE claim_id IN (?, ?) AND link_method IN ('authoring', 'citation_api')
        ORDER BY rank_in_claim
    """, (item_id, f"{item_id}_cite")).fetchall()
    prov_ids = [r["fact_id"][:8] if r["fact_id"] and len(r["fact_id"]) > 8 else r["fact_id"] for r in auth_rows]

    # Vector traces (embedding similarity)
    trace_rows = conn.execute("""
        SELECT lcp.fact_id, lcp.similarity_score, lcp.link_method,
               mf.fact_text, mf.confidence,
               mf.knowledge_tier, mf.category, mf.source_conversation_id
        FROM layer_claim_provenance lcp
        JOIN memory_facts mf ON mf.id = lcp.fact_id
        WHERE lcp.claim_id IN (?, ?) AND lcp.link_method = 'vector'
        ORDER BY lcp.similarity_score DESC
        LIMIT 10
    """, (item_id, f"{item_id}_cite")).fetchall()

    # Also include API-traced facts as traces (with confidence as similarity proxy)
    api_trace_rows = conn.execute("""
        SELECT lcp.fact_id, lcp.similarity_score, lcp.link_method,
               mf.fact_text, mf.confidence,
               mf.knowledge_tier, mf.category, mf.source_conversation_id
        FROM layer_claim_provenance lcp
        JOIN memory_facts mf ON mf.id = lcp.fact_id
        WHERE lcp.claim_id IN (?, ?) AND lcp.link_method IN ('authoring', 'citation_api')
        ORDER BY lcp.rank_in_claim
    """, (item_id, f"{item_id}_cite")).fetchall()
    conn.close()

    traces = []
    seen_fact_ids = set()

    # API-traced facts first (highest provenance quality — model cited these directly)
    for r in api_trace_rows:
        fid = r["fact_id"][:8] if r["fact_id"] and len(r["fact_id"]) > 8 else r["fact_id"]
        if fid in seen_fact_ids:
            continue
        seen_fact_ids.add(fid)
        source = conv_titles.get(r["source_conversation_id"], "")
        traces.append({
            "factId": fid,
            "text": r["fact_text"],
            "sourceChapter": "",
            "confidence": round(r["confidence"], 3) if r["confidence"] else 0.0,
            "tier": r["knowledge_tier"] or "untiered",
            "category": r["category"] or "unknown",
            "similarity": 1.0,  # API-cited = perfect relevance
            "source": source,
        })

    # Then vector traces (embedding similarity)
    for r in trace_rows:
        fid = r["fact_id"][:8] if r["fact_id"] and len(r["fact_id"]) > 8 else r["fact_id"]
        if fid in seen_fact_ids:
            continue
        seen_fact_ids.add(fid)
        source = conv_titles.get(r["source_conversation_id"], "")
        traces.append({
            "factId": fid,
            "text": r["fact_text"],
            "sourceChapter": "",
            "confidence": round(r["similarity_score"], 3) if r["similarity_score"] else 0.0,
            "tier": r["knowledge_tier"] or "untiered",
            "category": r["category"] or "unknown",
            "similarity": round(r["similarity_score"], 3) if r["similarity_score"] else 0.0,
            "source": source,
        })
    return prov_ids, traces


# ---------------------------------------------------------------------------
# Build enriched payload
# ---------------------------------------------------------------------------

def compute_radar_profile(name: str, db_path: Path, anchors: list, core: list, predictions: list, facts: list) -> dict:
    """Auto-generate radar profile from fact distribution and layer structure.

    8 axes scored 0-1:
    - conviction: ratio of high-commitment predicates (believes, values, fears, identifies_as)
    - consistency: how concentrated the predicate distribution is (low entropy = high consistency)
    - breadth: number of unique predicates / 46 (max possible)
    - stability: ratio of identity-tier facts
    - awareness: ratio of self-reflective predicates (struggles_with, fears, identifies_as)
    - relational: ratio of relationship predicates
    - temporal: based on source diversity (conversations/documents)
    - predictability: predictions layer size relative to anchors+core
    """
    import math

    total = len(facts) if facts else 1

    # Count predicates
    pred_counts = {}
    tier_counts = {"identity": 0, "contextual": 0, "untiered": 0}
    for f in facts:
        p = f.get("predicate") or "unknown"
        pred_counts[p] = pred_counts.get(p, 0) + 1
        t = f.get("knowledge_tier") or "untiered"
        tier_counts[t] = tier_counts.get(t, 0) + 1

    # 1. Conviction: ratio of conviction-level predicates
    conviction_preds = {"believes", "values", "fears", "identifies_as", "prioritizes"}
    conviction_count = sum(pred_counts.get(p, 0) for p in conviction_preds)
    conviction = min(1.0, conviction_count / max(total * 0.3, 1))  # normalize: 30%+ = 1.0

    # 2. Consistency: inverse entropy of predicate distribution
    if pred_counts:
        probs = [c / total for c in pred_counts.values()]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(len(pred_counts)) if len(pred_counts) > 1 else 1
        consistency = 1.0 - (entropy / max(max_entropy, 1))
    else:
        consistency = 0.5

    # 3. Breadth: unique predicates / 46
    breadth = min(1.0, len(pred_counts) / 46)

    # 4. Stability: identity-tier ratio
    identity_count = tier_counts.get("identity", 0)
    stability = min(1.0, identity_count / max(total * 0.7, 1))  # 70%+ identity = 1.0

    # 5. Awareness: self-reflective predicates
    awareness_preds = {"struggles_with", "fears", "identifies_as", "experienced", "lost", "decided"}
    awareness_count = sum(pred_counts.get(p, 0) for p in awareness_preds)
    awareness = min(1.0, awareness_count / max(total * 0.15, 1))  # 15%+ = 1.0

    # 6. Relational: relationship predicates
    relational_preds = {"collaborates_with", "mentored_by", "friends_with", "relates_to", "admires", "conflicts_with", "reports_to", "raised_by", "parents"}
    relational_count = sum(pred_counts.get(p, 0) for p in relational_preds)
    relational = min(1.0, relational_count / max(total * 0.1, 1))  # 10%+ = 1.0

    # 7. Temporal: source diversity (number of unique sources)
    sources = set()
    for f in facts:
        s = f.get("source") or f.get("sourceChapter") or ""
        if s:
            sources.add(s)
    temporal = min(1.0, len(sources) / 30)  # 30+ sources = 1.0

    # 8. Predictability: prediction coverage relative to total layer items
    total_items = len(anchors) + len(core) + len(predictions)
    predictability = min(1.0, len(predictions) / max(total_items * 0.35, 1))  # 35%+ predictions = 1.0

    # Round all values
    slug = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
    color = "#38bdf8"  # accent blue

    return {
        "id": slug,
        "label": name,
        "axes": [
            {"key": "conviction", "label": "Conviction Strength", "value": round(conviction, 2)},
            {"key": "consistency", "label": "Behavioral Consistency", "value": round(consistency, 2)},
            {"key": "breadth", "label": "Domain Breadth", "value": round(breadth, 2)},
            {"key": "stability", "label": "Identity Stability", "value": round(stability, 2)},
            {"key": "awareness", "label": "Self-Awareness", "value": round(awareness, 2)},
            {"key": "relational", "label": "Relational Depth", "value": round(relational, 2)},
            {"key": "temporal", "label": "Temporal Span", "value": round(temporal, 2)},
            {"key": "predictability", "label": "Predictability", "value": round(predictability, 2)},
        ],
        "color": color,
        "fillColor": color,
    }


def generate_change_summary(old_text: str, new_text: str, model_note: str = "") -> tuple[str, dict]:
    """Mechanical diff between two identity models. Returns (summary_string, changeDetail_dict)."""
    import re

    def count_items(text, pattern):
        return len(re.findall(pattern, text))

    old_anchors = count_items(old_text, r'\*\*A\d+')
    new_anchors = count_items(new_text, r'\*\*A\d+')
    old_core = count_items(old_text, r'\*\*(?:C|M)\d+')
    new_core = count_items(new_text, r'\*\*(?:C|M)\d+')
    old_preds = count_items(old_text, r'\*\*P\d+')
    new_preds = count_items(new_text, r'\*\*P\d+')

    def section_words(text, start_pattern, end_patterns=None):
        match = re.search(start_pattern, text, re.DOTALL)
        if not match:
            return 0
        content = text[match.end():]
        if end_patterns:
            for ep in end_patterns:
                end_match = re.search(ep, content)
                if end_match:
                    content = content[:end_match.start()]
                    break
        return len(content.split())

    old_bw = section_words(old_text, r'## (?:Identity Brief|Injectable Block)\s*\n')
    new_bw = section_words(new_text, r'## (?:Identity Brief|Injectable Block)\s*\n')
    old_total = len(old_text.split())
    new_total = len(new_text.split())

    # Build summary string
    parts = []
    layer_changes = []
    if new_anchors != old_anchors:
        layer_changes.append(f"anchors {old_anchors}->{new_anchors}")
    if new_core != old_core:
        layer_changes.append(f"core {old_core}->{new_core}")
    if new_preds != old_preds:
        layer_changes.append(f"predictions {old_preds}->{new_preds}")

    if model_note:
        parts.append(model_note)
    if layer_changes:
        parts.append(f"Layers changed: {', '.join(layer_changes)}.")
    elif old_text != new_text:
        parts.append("Content revised (same structure, different substance).")
    parts.append(f"Total {old_total:,}->{new_total:,} words.")

    summary = " ".join(parts)

    # Build changeDetail
    detail = {}

    # Anchors
    if new_anchors != old_anchors:
        detail["anchors"] = (
            f"Expanded from {old_anchors} to {new_anchors} axioms. "
            "Each now includes full prose on how it operates and what violating it feels like. "
            "Interaction maps rewritten as cascade mechanics showing what happens when axioms conflict."
        )
    elif old_anchors > 0 and old_text != new_text:
        detail["anchors"] = (
            f"{new_anchors} axioms retained. Descriptions deepened with operational prose, "
            "interaction mechanics, and domain-specific activation caveats."
        )

    # Core
    if new_core != old_core:
        detail["core"] = (
            f"Restructured from {old_core} to {new_core} context modes. "
            "Now includes explicit mode detection, per-context style shifts, emotional load flags, "
            "and lead-with directives for each domain."
        )
    elif old_core > 0 and old_text != new_text:
        detail["core"] = (
            f"{new_core} context modes retained. Rewritten with explicit style shifts, "
            "emotional load flags, and mode detection rules per domain."
        )

    # Predictions
    if new_preds != old_preds:
        detail["predictions"] = (
            f"Expanded from {old_preds} to {new_preds} behavioral patterns. "
            "Each now includes cross-domain detection signals, specific AI directives, "
            "and false-positive warnings for when the pattern is NOT active."
        )
    elif old_preds > 0 and old_text != new_text:
        detail["predictions"] = (
            f"{new_preds} patterns retained. Sharpened with cross-domain detection, "
            "specific directives, and false-positive warnings."
        )

    # Brief
    if old_bw and new_bw and abs(new_bw - old_bw) > 50:
        direction = "expanded" if new_bw > old_bw else "condensed"
        detail["brief"] = (
            f"Brief {direction} from {old_bw:,} to {new_bw:,} words. "
            "Unified into a single coherent narrative that weaves axioms, context modes, "
            "and predictions together rather than concatenating separate sections."
        )
    elif old_bw and new_bw:
        detail["brief"] = f"Brief revised ({new_bw:,} words). Content rewritten for coherence and depth."

    return summary, detail


def build_payload(subject_dir: Path, name: str, slug: str, password: str, source_desc: str, token: Optional[str] = None) -> dict:
    layers_dir = subject_dir / "data" / "identity_layers"
    db_path = subject_dir / "data" / "database" / "memory.db"

    if not layers_dir.exists():
        raise FileNotFoundError(f"No identity_layers directory at {layers_dir}")
    if not db_path.exists():
        raise FileNotFoundError(f"No database at {db_path}")

    # Find layer files
    def find_file(prefix: str) -> Optional[Path]:
        for suffix in ["_v5_clean.md", "_v5.md", "_v4.md", "_v3.md", ".md"]:
            p = layers_dir / f"{prefix}{suffix}"
            if p.exists():
                return p
        # Try glob
        matches = sorted(layers_dir.glob(f"{prefix}*.md"))
        return matches[0] if matches else None

    anchors_file = find_file("anchors")
    core_file = find_file("core")
    predictions_file = find_file("predictions")
    brief_file = find_file("brief")

    if not all([anchors_file, core_file, predictions_file, brief_file]):
        missing = [n for n, f in [("anchors", anchors_file), ("core", core_file), ("predictions", predictions_file), ("brief", brief_file)] if not f]
        raise FileNotFoundError(f"Missing layer files: {missing}")

    # Parse layers
    anchors_text = anchors_file.read_text(encoding="utf-8")
    core_text = core_file.read_text(encoding="utf-8")
    predictions_text = predictions_file.read_text(encoding="utf-8")
    brief_text = brief_file.read_text(encoding="utf-8")

    anchors = parse_anchors_md(anchors_text)
    core = parse_core_md(core_text)
    predictions = parse_predictions_md(predictions_text)
    brief = parse_brief_md(brief_text, anchors, core, predictions)
    interactions = parse_axiom_interactions_md(anchors_text)

    # Cited brief
    cited_brief_file = find_file("brief_v5")
    cited_brief = cited_brief_file.read_text(encoding="utf-8") if cited_brief_file else None

    # Database queries
    conv_titles = get_conv_titles(db_path)
    facts = get_facts(db_path)
    pred_dist = get_predicate_distribution(db_path)

    # Build traces for each layer item
    has_provenance = False
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1 FROM layer_claim_provenance LIMIT 1").fetchone()
        conn.close()
        has_provenance = True
    except Exception:
        pass

    if has_provenance:
        for item in anchors:
            prov_ids, traces = build_traces_for_item(item["id"], db_path, conv_titles)
            item["provenance"] = prov_ids
            item["traces"] = traces
        for item in core:
            prov_ids, traces = build_traces_for_item(item["id"], db_path, conv_titles)
            item["provenance"] = prov_ids
            item["traces"] = traces
        for item in predictions:
            prov_ids, traces = build_traces_for_item(item["id"], db_path, conv_titles)
            item["provenance"] = prov_ids
            item["traces"] = traces
    else:
        print(f"  Warning: No layer_claim_provenance table found. Traces will be empty.")
        for item in anchors + core + predictions:
            item["provenance"] = []
            item["traces"] = []

    # Compute stats
    conn = sqlite3.connect(str(db_path))
    total = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    try:
        chapters = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    except Exception:
        chapters = 0
    conn.close()

    # Generate radar profile from fact distribution
    radar = compute_radar_profile(name, db_path, anchors, core, predictions, facts)

    # Load tensions if available
    tensions_file = Path(__file__).parent.parent.parent / "tensions_all.json"
    contradictions = []
    if tensions_file.exists():
        try:
            all_tensions = json.loads(tensions_file.read_text(encoding="utf-8"))
            subject_key = subject_dir.name.replace("_memory", "")
            contradictions = all_tensions.get(subject_key, [])
        except Exception:
            pass

    # Build source documents list from conversations table
    source_documents = []
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT title, source FROM conversations ORDER BY title"
        ).fetchall()
        conn.close()
        seen_titles = set()
        for i, (title, src) in enumerate(rows, 1):
            if title in seen_titles:
                continue
            seen_titles.add(title)
            # Map source type to domain label
            domain = {
                "text_file": "Essays & Articles",
                "chatgpt": "Conversations",
                "claude_web": "Conversations",
                "journal": "Journal",
            }.get(src or "", src or "Other")
            # Try to infer domain from source directory structure
            source_documents.append({
                "id": str(i),
                "title": title,
                "domain": domain,
            })
    except Exception:
        pass

    # Try to enrich domains from source file paths
    source_dir = subject_dir / "data" / "sources"
    if source_dir.exists():
        folder_to_domain = {
            "op-eds": "Op-Eds",
            "speeches": "Speeches",
            "debates": "Debates",
            "interviews": "Interviews",
            "books": "Books",
            "historical": "Historical",
            "archives": "Archives",
        }
        file_title_to_domain = {}
        for folder, domain_label in folder_to_domain.items():
            folder_path = source_dir / folder
            if folder_path.exists():
                for f in folder_path.glob("*.txt"):
                    clean_title = f.stem.replace("_", " ").replace("-", " ").title()
                    file_title_to_domain[clean_title] = domain_label
        # Match source documents to folder-based domains
        for doc in source_documents:
            if doc["title"] in file_title_to_domain:
                doc["domain"] = file_title_to_domain[doc["title"]]

    payload = {
        "name": name,
        "slug": slug,
        "password": password,
        "sourceDescription": f"{len(source_documents)} source documents" if source_documents else source_desc,
        "brief": brief,  # structured, not plain text
        "citedBrief": cited_brief,
        "anchors": anchors,
        "core": core,
        "predictions": predictions,
        "facts": facts,
        "interactions": interactions,
        "contradictions": contradictions,
        "stats": pred_dist,
        "radar": radar,
        "sourceDocuments": source_documents,
    }

    if token:
        payload["token"] = token

    # S98: Generate change summary if previous identity model exists
    v1_staging = subject_dir / "data" / "identity_layers" / "v1_staging"
    v1_identity = v1_staging / "identity_model.md"
    current_identity = subject_dir / "data" / "identity_layers" / "identity_model.md"
    if v1_identity.exists() and current_identity.exists():
        old_text = v1_identity.read_text(encoding="utf-8")
        new_text = current_identity.read_text(encoding="utf-8")
        if old_text.strip() != new_text.strip():
            summary, detail = generate_change_summary(
                old_text, new_text,
                model_note="Model upgraded from Sonnet 4 / Opus 4 to Sonnet 4.6 / Opus 4.6."
            )
            if summary:
                payload["changeSummary"] = summary
                print(f"  Change summary: {summary}")
            if detail:
                payload["changeDetail"] = detail
                print(f"  Change detail: {len(detail)} sections")

    return payload


# ---------------------------------------------------------------------------
# Subjects config
# ---------------------------------------------------------------------------

def _load_passwords():
    """Load passwords from untracked passwords.json file."""
    import json
    pw_file = Path(__file__).parent.parent.parent / "data" / "seeds" / "passwords.json"
    if pw_file.exists():
        return json.loads(pw_file.read_text(encoding="utf-8"))
    return {}

_PASSWORDS = _load_passwords()



SUBJECTS = {
    "dan_shipper":      {"name": "Dan Shipper",         "slug": "dan-shipper",      "password": "",              "source": "84 Chain of Thought essays, interviews, and talks"},
    "anne_lecunff":      {"name": "Anne-Laure Le Cunff", "slug": "anne-laure",        "password": "",            "source": "131 Ness Labs essays"},
    "henrik_karlsson":   {"name": "Henrik Karlsson",     "slug": "henrik-karlsson",   "password": "",        "source": "90 Escaping Flatland essays"},
    "david_perell":      {"name": "David Perell",        "slug": "david-perell",      "password": "",         "source": "140 essays"},
    "fred_wilson":       {"name": "Fred Wilson",         "slug": "fred-wilson",       "password": "",           "source": "143 AVC posts"},
    "simon_willison":    {"name": "Simon Willison",      "slug": "simon-willison",    "password": "",         "source": "208 blog posts"},
    "maggie_appleton":   {"name": "Maggie Appleton",     "slug": "maggie-appleton",   "password": "",              "source": "121 essays, notes, and talks"},
    "cedric_chin":       {"name": "Cedric Chin",         "slug": "cedric-chin",       "password": "",        "source": "297 Commoncog posts"},
    "casey_newton":      {"name": "Casey Newton",        "slug": "casey-newton",      "password": "",             "source": "103 Platformer articles"},
    "scott_alexander":   {"name": "Scott Alexander",     "slug": "scott-alexander",   "password": "",   "source": "100 ACX posts"},
    "matt_yglesias":     {"name": "Matt Yglesias",       "slug": "matt-yglesias",     "password": "",                  "source": "277 Slow Boring posts"},
    "swyx":              {"name": "swyx",                "slug": "swyx",              "password": "",        "source": "70 posts"},
    "ethan_mollick":     {"name": "Ethan Mollick",       "slug": "ethan-mollick",     "password": "",            "source": "99 One Useful Thing posts"},
    "cory_doctorow":     {"name": "Cory Doctorow",       "slug": "cory-doctorow",     "password": "",         "source": "163 Pluralistic posts"},
    "kevin_kelly":       {"name": "Kevin Kelly",         "slug": "kevin-kelly",       "password": "",              "source": "670 Technium essays, Extrapolations, and archives"},
    # Wave 2
    "paul_graham":       {"name": "Paul Graham",         "slug": "paul-graham",       "password": "",       "source": "56 essays"},
    "dan_luu":           {"name": "Dan Luu",             "slug": "dan-luu",           "password": "",               "source": "80 blog posts"},
    "derek_thompson":    {"name": "Derek Thompson",      "slug": "derek-thompson",    "password": "",                  "source": "40 essays"},
    "linus_lee":         {"name": "Linus Lee",           "slug": "linus-lee",         "password": "",             "source": "64 essays and project write-ups"},
    "byrne_hobart":      {"name": "Byrne Hobart",        "slug": "byrne-hobart",      "password": "",        "source": "40 Diff essays"},
    "noah_smith":        {"name": "Noah Smith",          "slug": "noah-smith",        "password": "",            "source": "40 Noahpinion essays"},
    "venkatesh_rao":     {"name": "Venkatesh Rao",       "slug": "venkatesh-rao",     "password": "",                 "source": "43 Ribbonfarm essays"},
    "nathan_lambert":    {"name": "Nathan Lambert",      "slug": "nathan-lambert",    "password": "",                 "source": "40 Interconnects posts"},
    "packy_mccormick":   {"name": "Packy McCormick",     "slug": "packy-mccormick",   "password": "",                 "source": "40 Not Boring essays"},
    "tina_he":           {"name": "Tina He",             "slug": "tina-he",           "password": "",              "source": "40 Fakepixels essays"},
    "bernie_sanders":    {"name": "Bernie Sanders",      "slug": "bernie-sanders",    "password": "",         "source": "130 speeches, op-eds, and interviews"},
    "ivan_bercovich":    {"name": "Ivan Bercovich",      "slug": "ivan-bercovich",    "password": "",           "source": "50 essays and interviews"},
    "jonathan_fulton":   {"name": "Jonathan Fulton",     "slug": "jonathan-fulton",   "password": "",            "source": "20 blog posts"},
    "eli_tyre":          {"name": "Eli Tyre",            "slug": "eli-tyre",          "password": "",           "source": "197 posts and essays"},
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed industry pages with enriched data.")
    parser.add_argument("--subject", help="Subject key (e.g. dan_shipper). Omit to seed all.")
    parser.add_argument("--slug", help="Override slug")
    parser.add_argument("--password", help="Override password")
    parser.add_argument("--token", help="Existing Redis token (for re-seeding)")
    parser.add_argument("--dry-run", action="store_true", help="Build payload but don't POST")
    parser.add_argument("--output", help="Write payload JSON to file instead of POSTing")
    args = parser.parse_args()

    admin_secret = os.environ.get("INDUSTRY_ADMIN_SECRET")
    if not admin_secret and not args.dry_run and not args.output:
        # Try Windows user env
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", "[System.Environment]::GetEnvironmentVariable('INDUSTRY_ADMIN_SECRET', 'User')"],
                capture_output=True, text=True
            )
            admin_secret = result.stdout.strip()
        except Exception:
            pass

    if not admin_secret and not args.dry_run and not args.output:
        print("Error: INDUSTRY_ADMIN_SECRET not set", file=sys.stderr)
        sys.exit(1)

    base_url = os.environ.get("BASE_LAYER_URL", "https://base-layer.ai")

    subjects_to_seed = {}
    if args.subject:
        if args.subject not in SUBJECTS:
            print(f"Unknown subject: {args.subject}. Known: {', '.join(SUBJECTS.keys())}", file=sys.stderr)
            sys.exit(1)
        subjects_to_seed[args.subject] = SUBJECTS[args.subject].copy()
        if args.slug:
            subjects_to_seed[args.subject]["slug"] = args.slug
        if args.password:
            subjects_to_seed[args.subject]["password"] = args.password
    else:
        subjects_to_seed = {k: v.copy() for k, v in SUBJECTS.items()}

    for subject_key, config in subjects_to_seed.items():
        print(f"\n{'='*60}")
        print(f"Seeding: {config['name']} ({subject_key})")
        print(f"{'='*60}")

        try:
            subject_dir = resolve_subject_dir(subject_key)
            print(f"  Directory: {subject_dir}")
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            continue

        try:
            payload = build_payload(
                subject_dir=subject_dir,
                name=config["name"],
                slug=config["slug"],
                password=_PASSWORDS.get(subject_key, config.get("password", "")),
                source_desc=config["source"],
                token=args.token,
            )
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        # Stats
        n_anchors = len(payload["anchors"])
        n_core = len(payload["core"])
        n_preds = len(payload["predictions"])
        n_facts = len(payload["facts"])
        n_traces = sum(len(item.get("traces", [])) for item in payload["anchors"] + payload["core"] + payload["predictions"])
        n_interactions = sum(len(v) for v in payload["interactions"].values())
        n_brief = len(payload["brief"])

        print(f"  Anchors: {n_anchors}, Core: {n_core}, Predictions: {n_preds}")
        print(f"  Facts: {n_facts}, Traces: {n_traces}, Interactions: {n_interactions}")
        print(f"  Brief paragraphs: {n_brief}")

        if args.output:
            out_path = Path(args.output) if args.subject else Path(f"seed_{subject_key}.json")
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  Written to: {out_path}")
            continue

        if args.dry_run:
            print(f"  DRY RUN: Would POST {len(json.dumps(payload))} bytes to {base_url}/api/industry/seed")
            continue

        # POST to seed endpoint using requests-style redirect handling
        url = f"{base_url}/api/industry/seed"
        data = json.dumps(payload).encode("utf-8")

        # Follow redirects manually for POST
        max_redirects = 3
        current_url = url
        for _ in range(max_redirects + 1):
            req = urllib.request.Request(
                current_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-admin-secret": admin_secret,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    print(f"  SUCCESS: token={result.get('token', 'N/A')}")
                    if "viewUrl" in result:
                        print(f"  URL: {result['viewUrl']}")
                    break
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 307, 308):
                    current_url = e.headers.get("Location", current_url)
                    print(f"  Redirect -> {current_url}")
                    continue
                body = e.read().decode("utf-8", errors="replace")
                print(f"  FAILED: HTTP {e.code} - {body}")
                break
            except Exception as e:
                print(f"  FAILED: {e}")
                break


if __name__ == "__main__":
    main()
