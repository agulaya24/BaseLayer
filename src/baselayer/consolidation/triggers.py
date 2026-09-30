"""Stage `triggers`: split each claim's Active_When into situation clauses and group the
clauses into distinct triggers, many-to-many to claims.

Rules (ported from the 2026-09-29 trigger index prototype):
  * a clause is an EXACT substring of its claim's authored Active_When; "*" means the
    whole condition;
  * clauses that name the same situation form one trigger;
  * a trigger's wording is one member's clause (or whole condition) verbatim, first
    letter capitalised; no situation is invented and no claim text is changed;
  * always-on claims are not hung off any trigger.

Grouping sources:
    grouping file   {"triggers": [{"key", "wording_source": {"claim", "clause"},
                                   "members": [{"claim", "clause"}]}]}
                    the hand grouping (the 9/29 index is one, ported by `port`), or the
                    output of any TriggerGrouper
    identity        no grouping supplied: one trigger per non-always-on claim on its whole
                    condition; claims whose conditions are identical (case and space
                    folded) share one trigger. Mechanical, lossless, and a baseline only.

This stage builds what it is given; validity (verbatim, reachability, coverage) is the
checks stage's job, so a bad grouping reaches the checks and goes red there instead of
being silently repaired here.

Output triggers.json = {"source", "triggers": [{"id","key","wording","wording_source",
"wording_clause","claims","members": [{"claim","clause","whole_condition","condition"}]}],
"claim_to_triggers", "stats"}.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Protocol

WHOLE = "*"


class TriggerGrouper(Protocol):
    """Produces a grouping document (the grouping-file shape above) from claims. A
    model-assisted grouper would implement this outside the package; not run here."""

    def group(self, claims: list[dict], always_on: list[str]) -> dict: ...


def identity_grouping(claims: list[dict], always_on: list[str]) -> dict:
    ao = set(always_on)
    by_cond: dict[str, list[str]] = {}
    for c in claims:
        if c["id"] in ao:
            continue
        k = re.sub(r"\s+", " ", c["active_when"].strip().lower())
        by_cond.setdefault(k, []).append(c["id"])
    out = []
    for ids in by_cond.values():
        out.append({"key": "claim_" + ids[0], "wording_source": {"claim": ids[0], "clause": WHOLE},
                    "members": [{"claim": i, "clause": WHOLE} for i in ids]})
    return {"triggers": out, "method": "identity: one trigger per distinct whole condition"}


def _clause(cmap: dict, cid: str, cl: str) -> str:
    return cmap[cid]["active_when"].strip() if cl == WHOLE else cl


def build(claims_doc: dict, always_on_doc: dict, grouping: dict | None = None) -> dict:
    cl = claims_doc["claims"]
    cmap = {c["id"]: c for c in cl}
    ao = list(always_on_doc["claims"])
    source = "grouping file"
    if grouping is None:
        grouping = identity_grouping(cl, ao)
        source = "identity"
    out = []
    for n, t in enumerate(grouping["triggers"], 1):
        for m in t["members"]:
            if m["claim"] not in cmap:
                raise ValueError(f"trigger {t.get('key')} names unknown claim {m['claim']}")
        ws = t["wording_source"]
        if ws["claim"] not in cmap:
            raise ValueError(f"trigger {t.get('key')} wording source names unknown claim {ws['claim']}")
        mem = [{"claim": m["claim"], "clause": _clause(cmap, m["claim"], m["clause"]),
                "whole_condition": m["clause"] == WHOLE, "condition": cmap[m["claim"]]["active_when"].strip()}
               for m in t["members"]]
        wclause = _clause(cmap, ws["claim"], ws["clause"])
        wording = wclause[:1].upper() + wclause[1:]
        out.append({"id": f"TG{n:02d}", "key": t.get("key") or f"t{n}", "wording": wording,
                    "wording_source": ws["claim"], "wording_clause": wclause,
                    "claims": list(dict.fromkeys(m["claim"] for m in mem)), "members": mem})
    by_claim: dict[str, list[str]] = {}
    for t in out:
        for c in t["claims"]:
            by_claim.setdefault(c, []).append(t["id"])
    sizes = [len(t["claims"]) for t in out]
    stats = {"triggers": len(out), "always_on": len(ao),
             "triggered_claims": len(by_claim), "edges": sum(sizes),
             "claims_on_2plus_triggers": sum(1 for v in by_claim.values() if len(v) > 1),
             "singleton_triggers": sum(1 for s in sizes if s == 1),
             "max_claims_per_trigger": max(sizes, default=0),
             "whole_condition_edges": sum(1 for t in out for m in t["members"] if m["whole_condition"]),
             "clause_edges": sum(1 for t in out for m in t["members"] if not m["whole_condition"]),
             "claims_per_trigger": dict(sorted(Counter(sizes).items()))}
    return {"source": source, "method": grouping.get("method"), "triggers": out,
            "claim_to_triggers": {c["id"]: by_claim.get(c["id"], []) for c in cl if c["id"] not in set(ao)},
            "stats": stats}
