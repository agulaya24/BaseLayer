"""Stage `dedupe`: record duplicate groups as a mapping. Never rewrites a claim.

Output dedupe.json = {"basis", "groups": [{"id","members","edges"}], "claim_to_group": {id: group id}}.
Every claim maps to exactly one group; a claim with no duplicate is a singleton group.
The raw layers stay the record. Merged wording, if ever wanted, is a separate optional
step that reads this mapping (see `MergeWriter`); nothing in this package writes it.

Bases, one per run (parameter `basis`):
    judgements  union of pairs a PairJudge labelled with one of `merge_labels` (default SAME)
                in BOTH orders when `require_both_orders` (default true)
    evidence    union of pairs whose shared-evidence Jaccard is >= `jaccard_min`
    external    a mapping supplied from outside ({"source_to_group": {claim: group}}),
                e.g. the 2026-09-28 merge preview's mapping.json
"""
from __future__ import annotations

from collections import defaultdict
from typing import Protocol


def _components(ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    comp = defaultdict(list)
    for i in ids:
        comp[find(i)].append(i)
    pos = {i: n for n, i in enumerate(ids)}
    return sorted((sorted(v, key=pos.get) for v in comp.values()), key=lambda g: pos[g[0]])


def build(claims_doc: dict, overlap_doc: dict | None = None, *, basis: str = "evidence",
          jaccard_min: float = 0.5, judgements: list[dict] | None = None,
          merge_labels=("SAME",), require_both_orders: bool = True,
          external: dict | None = None) -> dict:
    ids = [c["id"] for c in claims_doc["claims"]]
    known = set(ids)
    if basis == "evidence":
        if overlap_doc is None:
            raise ValueError("basis=evidence needs overlap.json")
        edges = [(p["a"], p["b"]) for p in overlap_doc["pairs"] if p["jaccard"] >= jaccard_min]
    elif basis == "judgements":
        if judgements is None:
            raise ValueError("basis=judgements needs a judgements file")
        votes = defaultdict(set)
        for r in judgements:
            if r["a"] not in known or r["b"] not in known:
                raise ValueError(f"judgement names an unknown claim: {r['a']}|{r['b']}")
            key = tuple(sorted((r["a"], r["b"])))
            votes[key].add((r["a"], r["b"], r["label"] in merge_labels))
        edges = []
        for key, vs in votes.items():
            if require_both_orders:
                fwd = [v[2] for v in vs if (v[0], v[1]) == key]
                rev = [v[2] for v in vs if (v[1], v[0]) == key]
                if fwd and rev and all(fwd) and all(rev):
                    edges.append(key)
            elif any(v[2] for v in vs):
                edges.append(key)
    elif basis == "external":
        if external is None:
            raise ValueError("basis=external needs a mapping file")
        s2g = external["source_to_group"]
        if set(s2g) != known:
            raise ValueError(f"external mapping does not cover the claims exactly: missing "
                             f"{sorted(known - set(s2g))[:10]}, unknown {sorted(set(s2g) - known)[:10]}")
        by = defaultdict(list)
        for i in ids:
            by[s2g[i]].append(i)
        edges = [(g[0], m) for g in by.values() for m in g[1:]]
    else:
        raise ValueError(f"unknown dedupe basis {basis!r}")
    groups = []
    c2g = {}
    for n, members in enumerate(_components(ids, edges), 1):
        gid = f"D{n:03d}"
        ms = set(members)
        groups.append({"id": gid, "members": members,
                       "edges": sorted([list(e) for e in edges if e[0] in ms and e[1] in ms])})
        for m in members:
            c2g[m] = gid
    multi = [g for g in groups if len(g["members"]) > 1]
    return {"basis": basis, "groups": groups, "claim_to_group": c2g,
            "counts": {"claims": len(ids), "groups": len(groups), "multi_member_groups": len(multi),
                       "claims_in_multi": sum(len(g["members"]) for g in multi)},
            "rewrites": "none: claims are unchanged; merged wording is not produced by this stage"}


class MergeWriter(Protocol):
    """Optional, separate step: write merged wording for a multi-member group. Its output
    must sit beside dedupe.json, never replace a layer, and must pass the checks stage's
    claim-text and fact-id checks against the source claims it cites. Not implemented here."""

    def write(self, group: dict, claims_by_id: dict) -> dict: ...
