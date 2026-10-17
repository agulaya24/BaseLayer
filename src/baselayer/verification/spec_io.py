"""Load a specification directory into claims.

Two layouts are read:
  - distillation output: anchors.json / core.json / predictions.json, each {"claims": [...]}
    with id, name, statement, active_when, fact_ids, contested;
  - rendered markdown: anchors.md / core.md / predictions.md, or the served
    *_v<N>.md files, with `## A1 NAME  (CONTESTED)` headings, an `*Active when:*`
    line and `[F-xxxxxxxx]` evidence tags.

Exactly one file per layer is selected. JSON wins when both exist, and the
markdown is then compared against it (a divergence is a finding: the served text
is not the text that was verified).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LAYERS = ("anchors", "core", "predictions")

_HEAD = re.compile(r"^##\s+([ACPM]\d+)\s+(.*?)\s*$")
_CONTESTED = re.compile(r"\(\s*CONTESTED\s*\)", re.I)
_FACT_TAG = re.compile(r"\[F-([0-9a-fA-F]{6,36})\]")
_ACTIVE = re.compile(r"^\*?\s*Active when:\s*\*?\s*(.*)$", re.I)
_EVIDENCE = re.compile(r"^\*?\s*Evidence\b", re.I)


@dataclass
class Claim:
    label: str
    id: str
    layer: str
    name: str
    statement: str
    active_when: str
    fact_ids: list[str]          # 8-hex (or full) ids, without the "F-" prefix, citation order kept
    contested: bool
    source_file: str

    @property
    def qid(self) -> str:
        return f"{self.label}:{self.id}"


@dataclass
class Spec:
    label: str
    spec_dir: str
    claims: list[Claim]
    files: list[dict] = field(default_factory=list)   # {layer, path, format, sha256}
    load_findings: list[dict] = field(default_factory=list)

    def by_id(self) -> dict[str, Claim]:
        return {c.id: c for c in self.claims}


def norm_name(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _strip_prefix(fid: str) -> str:
    fid = str(fid).strip()
    return fid[2:] if fid.upper().startswith("F-") else fid


def _pick_layer_file(spec_dir: Path, layer: str) -> tuple[Path | None, Path | None]:
    """Return (json_path, md_path) for one layer; md may be a versioned served file."""
    j = spec_dir / f"{layer}.json"
    m = spec_dir / f"{layer}.md"
    if not m.exists():
        versioned = []
        for p in spec_dir.glob(f"{layer}_v*.md"):
            mm = re.fullmatch(rf"{layer}_v(\d+)\.md", p.name)
            if mm:
                versioned.append((int(mm.group(1)), p))
        m = max(versioned)[1] if versioned else None
    return (j if j.exists() else None), (m if m and m.exists() else None)


def parse_json_layer(path: Path, layer: str, label: str) -> list[Claim]:
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for c in d.get("claims", []):
        out.append(Claim(label=label, id=str(c["id"]), layer=layer, name=c.get("name", ""),
                         statement=c.get("statement", ""), active_when=c.get("active_when", "") or "",
                         fact_ids=[_strip_prefix(x) for x in c.get("fact_ids", [])],
                         contested=bool(c.get("contested")), source_file=str(path)))
    return out


def parse_markdown_layer(text: str, layer: str, label: str, source_file: str = "") -> list[Claim]:
    """Parse `## <ID> NAME` blocks. Text before the first claim heading (provenance
    comments, the `## Injectable Block` marker, the layer preamble) is skipped."""
    claims: list[Claim] = []
    cur = None
    body: list[str] = []

    def flush():
        if cur is None:
            return
        cid, head = cur
        contested = bool(_CONTESTED.search(head))
        name = _CONTESTED.sub("", head).strip()
        stmt, active, fids = [], "", []
        for line in body:
            s = line.strip()
            fids += _FACT_TAG.findall(s)
            a = _ACTIVE.match(s)
            if a:
                active = a.group(1).strip().strip("*").strip()
                continue
            if _EVIDENCE.match(s) or not s or s.startswith("<!--"):
                continue
            stmt.append(s)
        claims.append(Claim(label=label, id=cid, layer=layer, name=name, statement=" ".join(stmt),
                            active_when=active, fact_ids=list(fids), contested=contested,
                            source_file=source_file))

    for line in text.splitlines():
        h = _HEAD.match(line)
        if h:
            flush()
            cur, body = (h.group(1), h.group(2)), []
        elif line.startswith("## ") or line.startswith("# "):
            flush()
            cur, body = None, []
        elif cur is not None:
            body.append(line)
    flush()
    return claims


def _compare(json_claims: list[Claim], md_claims: list[Claim], layer: str, label: str) -> list[dict]:
    out = []
    J = {c.id: c for c in json_claims}
    M = {c.id: c for c in md_claims}
    for cid in sorted(set(J) ^ set(M)):
        where = "json only" if cid in J else "markdown only"
        out.append({"field": "id", "claim": f"{label}:{cid}", "detail": f"{layer}: {where}"})
    for cid in sorted(set(J) & set(M)):
        a, b = J[cid], M[cid]
        if norm_name(a.name) != norm_name(b.name):
            out.append({"field": "name", "claim": f"{label}:{cid}", "detail": f"{a.name!r} vs {b.name!r}"})
        if [x[:8].lower() for x in a.fact_ids] != [x[:8].lower() for x in b.fact_ids]:
            out.append({"field": "fact_ids", "claim": f"{label}:{cid}",
                        "detail": f"json cites {len(a.fact_ids)}, markdown cites {len(b.fact_ids)}"})
        if norm_text(a.active_when) != norm_text(b.active_when):
            out.append({"field": "active_when", "claim": f"{label}:{cid}", "detail": "Active_When text differs"})
        if a.contested != b.contested:
            out.append({"field": "contested", "claim": f"{label}:{cid}", "detail": f"json {a.contested}, markdown {b.contested}"})
    return out


def load_spec(spec_dir: str | Path, label: str) -> Spec:
    if not label or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-]*", label):
        raise ValueError("a spec label is required (e.g. 'subject98'); claim ids are only unique inside one specification")
    spec_dir = Path(spec_dir)
    if not spec_dir.is_dir():
        raise FileNotFoundError(f"spec directory not found: {spec_dir}")
    spec = Spec(label=label, spec_dir=str(spec_dir), claims=[])
    for layer in LAYERS:
        j, m = _pick_layer_file(spec_dir, layer)
        if j is None and m is None:
            spec.load_findings.append({"check": "layer_missing", "detail": f"no {layer}.json, {layer}.md or {layer}_v<N>.md"})
            continue
        if j is not None:
            cl = parse_json_layer(j, layer, label)
            spec.files.append({"layer": layer, "path": str(j), "format": "json", "sha256": _sha(j)})
            if m is not None:
                mc = parse_markdown_layer(m.read_text(encoding="utf-8"), layer, label, str(m))
                spec.files.append({"layer": layer, "path": str(m), "format": "markdown (compared, not used)", "sha256": _sha(m)})
                for d in _compare(cl, mc, layer, label):
                    spec.load_findings.append({"check": "json_markdown_divergence", **d})
        else:
            cl = parse_markdown_layer(m.read_text(encoding="utf-8"), layer, label, str(m))
            spec.files.append({"layer": layer, "path": str(m), "format": "markdown", "sha256": _sha(m)})
        if not cl:
            spec.load_findings.append({"check": "layer_empty", "detail": f"{layer}: 0 claims parsed"})
        spec.claims.extend(cl)
    seen: dict[str, int] = {}
    for c in spec.claims:
        seen[c.id] = seen.get(c.id, 0) + 1
    for cid, n in sorted(seen.items()):
        if n > 1:
            spec.load_findings.append({"check": "duplicate_claim_id", "claim": f"{label}:{cid}",
                                       "detail": f"claim id {cid} appears {n} times in one specification"})
    return spec
