"""Stage `claims`: load an authored specification directory into claims.json.

Input: a spec dir holding {anchors,core,predictions}.json as written by
author-from-package (each {"layer", "claims": [{id, name, statement, active_when,
fact_ids, contested, ...}]}), and optionally the matching .md files.

Output: claims.json = {"claims": [...], "order": [ids], "sources": {file: sha256},
"md_blocks": {...}} where each claim carries its served block, the text an agent
receives when it pulls the claim. The block is rendered from JSON and, when the .md
beside it exists, compared with the block the .md carries (evidence and provenance
lines stripped), so a divergence between the two artifacts is visible, not assumed.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import file_sha256, read_json

DEFAULT_LAYERS = ("anchors", "core", "predictions")
CLAIM_FIELDS = ("id", "name", "statement", "active_when", "fact_ids", "contested")
CONTESTED_NOTE = "Marked CONTESTED by the layer that wrote it."


def render_block(c: dict) -> str:
    """The served block of one claim, the author-from-package markdown shape without the
    evidence, provenance and gate-citation lines."""
    head = "## %s %s%s" % (c["id"], c["name"], "  (CONTESTED)" if c.get("contested") else "")
    parts = [head, c["statement"]]
    if c.get("active_when"):
        parts.append("*Active when:* %s" % c["active_when"])
    return "\n\n".join(parts).strip()


def _strip_block(b: str) -> str:
    keep = [ln for ln in b.splitlines()
            if not ln.startswith(("*Evidence:*", "provenance:", "*Citations added by the quote gate:*"))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def md_blocks(md_text: str) -> dict:
    out = {}
    for p in re.split(r"^(?=## [A-Z]+\d+ )", md_text, flags=re.M):
        m = re.match(r"## ([A-Z]+\d+) ", p)
        if m:
            out[m.group(1)] = _strip_block(p)
    return out


def load_layers(spec_dir: Path, layers=DEFAULT_LAYERS) -> tuple[list[dict], dict]:
    """(claims in layer order, {filename: sha256}). Raises on a missing field or a
    duplicate id: consolidation must not guess at a malformed spec."""
    spec_dir = Path(spec_dir)
    claims, sources, seen = [], {}, set()
    for layer in layers:
        f = spec_dir / f"{layer}.json"
        if not f.exists():
            raise FileNotFoundError(f"layer file missing: {f.name}")
        sources[f.name] = file_sha256(f)
        d = read_json(f)
        for c in d.get("claims") or []:
            miss = [k for k in ("id", "name", "statement", "active_when", "fact_ids") if k not in c]
            if miss:
                raise ValueError(f"{f.name}: claim {c.get('id')} lacks {miss}")
            if c["id"] in seen:
                raise ValueError(f"duplicate claim id {c['id']}")
            seen.add(c["id"])
            claims.append({"id": c["id"], "layer": layer, "name": c["name"], "statement": c["statement"],
                           "active_when": c["active_when"], "fact_ids": list(c["fact_ids"]),
                           "contested": bool(c.get("contested"))})
    return claims, sources


def build(spec_dir: Path, layers=DEFAULT_LAYERS) -> dict:
    claims, sources = load_layers(spec_dir, layers)
    md_cmp = {}
    for layer in layers:
        f = Path(spec_dir) / f"{layer}.md"
        if not f.exists():
            md_cmp[layer] = {"present": False}
            continue
        sources[f.name] = file_sha256(f)
        blocks = md_blocks(f.read_text(encoding="utf-8"))
        ids = [c["id"] for c in claims if c["layer"] == layer]
        mismatch = [i for i in ids if i in blocks and blocks[i] != render_block(next(c for c in claims if c["id"] == i))]
        md_cmp[layer] = {"present": True, "claims": len(ids), "missing_in_md": sorted(set(ids) - set(blocks)),
                         "extra_in_md": sorted(set(blocks) - set(ids)), "block_mismatch": mismatch}
    for c in claims:
        c["block"] = render_block(c)
        c["contested_note"] = CONTESTED_NOTE if c["contested"] else None
    return {"layers": list(layers), "order": [c["id"] for c in claims], "claims": claims,
            "sources": sources, "md_comparison": md_cmp,
            "counts": {"claims": len(claims),
                       "fact_ids_unique": len({f for c in claims for f in c["fact_ids"]}),
                       "citations": sum(len(c["fact_ids"]) for c in claims)}}


def by_id(claims_doc: dict) -> dict:
    return {c["id"]: c for c in claims_doc["claims"]}
