"""Stage `categories`: assign every trigger to one category, with per-category coverage.

Categories are data, not a fixed vocabulary. The input is a claim-level assignment:

    {"categories": [{"id": "T1", "name": "...", "members": [claim ids]}, ...],
     "trigger_overrides": {trigger key: category id}}          (overrides optional)

A trigger's category is the majority category over its UNIQUE member claims; on a tie,
the category of the claim its wording comes from (the 2026-09-29 rule). An override
names the category outright. Claims with no category do not vote. Triggers are then
ordered by category order, stably, so the order within a category is the grouping's.

With no assignment every trigger goes into one category, "Situations": a flat index.

Coverage per category: triggers, the claims they pull, the distinct fact ids behind those
claims, and the claims assigned to the category. A category is flagged `thin` when it
pulls fewer than `thin_claims` claims or rests on fewer than `thin_facts` facts, so a
gap in the evidence shows as a gap in the index rather than disappearing into it.

Output categories.json = {"categories": [{"id","name","triggers","claims","n_claims",
"n_facts","assigned_claims","thin"}], "trigger_category": {trigger id: category id},
"order": [trigger ids], "unassigned_claims", "empty_categories", "undecided_triggers"}.
"""
from __future__ import annotations

from collections import Counter


def build(claims_doc: dict, triggers_doc: dict, assignment: dict | None = None, *,
          thin_claims: int = 3, thin_facts: int = 10) -> dict:
    cmap = {c["id"]: c for c in claims_doc["claims"]}
    if assignment is None:
        assignment = {"categories": [{"id": "T1", "name": "Situations", "members": list(cmap)}],
                      "method": "none supplied: one flat category"}
    cats = []
    for i, c in enumerate(assignment["categories"], 1):
        cats.append({"id": c.get("id") or f"T{i}", "name": c["name"], "members": list(c.get("members") or [])})
    ids = [c["id"] for c in cats]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate category id")
    claim_cat = {}
    for c in cats:
        for m in c["members"]:
            if m in claim_cat:
                raise ValueError(f"claim {m} is assigned to two categories")
            claim_cat[m] = c["id"]
    order = {cid: n for n, cid in enumerate(ids)}
    overrides = assignment.get("trigger_overrides") or {}
    tcat, undecided = {}, []
    for t in triggers_doc["triggers"]:
        if t["key"] in overrides:
            tcat[t["id"]] = overrides[t["key"]]
            continue
        votes = Counter(claim_cat[c] for c in dict.fromkeys(t["claims"]) if c in claim_cat)
        if not votes:
            tcat[t["id"]] = None
            undecided.append(t["id"])
            continue
        top = max(votes.values())
        tied = [k for k, v in votes.items() if v == top]
        if len(tied) == 1:
            tcat[t["id"]] = tied[0]
        elif t["wording_source"] in claim_cat:
            tcat[t["id"]] = claim_cat[t["wording_source"]]
        else:
            tcat[t["id"]] = sorted(tied, key=order.get)[0]
    trig = sorted(triggers_doc["triggers"], key=lambda t: order.get(tcat[t["id"]], len(order)))
    out = []
    for c in cats:
        ts = [t for t in trig if tcat[t["id"]] == c["id"]]
        pulled = list(dict.fromkeys(x for t in ts for x in t["claims"]))
        facts = {f for x in pulled for f in cmap[x]["fact_ids"]}
        assigned = [m for m in c["members"] if m in cmap]
        out.append({"id": c["id"], "name": c["name"], "triggers": [t["id"] for t in ts],
                    "claims": pulled, "n_triggers": len(ts), "n_claims": len(pulled), "n_facts": len(facts),
                    "assigned_claims": assigned, "n_assigned_claims": len(assigned),
                    "n_assigned_facts": len({f for x in assigned for f in cmap[x]["fact_ids"]}),
                    "thin": len(pulled) < thin_claims or len(facts) < thin_facts})
    return {"method": assignment.get("method"), "categories": out, "trigger_category": tcat,
            "order": [t["id"] for t in trig],
            "unassigned_claims": [c for c in cmap if c not in claim_cat],
            "unknown_assigned": sorted(set(claim_cat) - set(cmap)),
            "empty_categories": [c["id"] for c in out if not c["triggers"]],
            "thin_categories": [c["id"] for c in out if c["thin"]],
            "undecided_triggers": undecided,
            "params": {"thin_claims": thin_claims, "thin_facts": thin_facts}}
