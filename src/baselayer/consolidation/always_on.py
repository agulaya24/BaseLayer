"""Stage `always_on`: select the standing claims, served in full on every message.

Rules (parameter `rule`):
    literal     a claim is standing when its Active_When condition opens with one of
                `phrases` (case-insensitive, whole words). The default phrases are the
                pre-registered textual rule of the 2026-09-28 trigger eval: "conditions
                whose text reads Always / All communication / Any communication / Any
                message / Any written message / Task requests across any domain /
                Nearly all replies".
    fire_rate   a claim is standing when its measured fire rate is >= `threshold` in a
                rates file ({"rates": {claim id: float}}), default 0.80. One rate per
                claim: the 9/28 pre-registered measured rule needed >= 0.80 from an arm AND from
                that arm's reference pass, so combine the two (take the minimum) before
                writing the rates file.
    explicit    the claim ids in `claims`, in spec order.

Output always_on.json = {"rule", "claims": [ids in spec order], "conditions": {id: text}}.
"""
from __future__ import annotations

import re

DEFAULT_PHRASES = ("Always", "All communication", "Any communication", "Any message", "Any written message",
                   "Task requests across any domain", "Nearly all replies")
RULE_TEXT = ("conditions whose text reads Always / All communication / Any communication / Any message / "
             "Any written message / Task requests across any domain / Nearly all replies")


def literal_match(condition: str, phrases=DEFAULT_PHRASES) -> str | None:
    cond = condition.strip()
    for p in phrases:
        if re.match(re.escape(p) + r"(?![A-Za-z])", cond, flags=re.I):
            return p
    return None


def build(claims_doc: dict, *, rule: str = "literal", phrases=DEFAULT_PHRASES, rates: dict | None = None,
          threshold: float = 0.80, claims: list[str] | None = None) -> dict:
    cl = claims_doc["claims"]
    known = [c["id"] for c in cl]
    why = {}
    if rule == "literal":
        for c in cl:
            p = literal_match(c["active_when"], phrases)
            if p:
                why[c["id"]] = f"condition opens with '{p}'"
        rule_text = RULE_TEXT if tuple(phrases) == DEFAULT_PHRASES else \
            "conditions whose text opens with " + " / ".join(phrases)
    elif rule == "fire_rate":
        if rates is None:
            raise ValueError("rule=fire_rate needs a rates file")
        unknown = sorted(set(rates) - set(known))
        if unknown:
            raise ValueError(f"rates name unknown claims {unknown[:10]}")
        for cid in known:
            r = rates.get(cid)
            if r is not None and r >= threshold:
                why[cid] = f"fire rate {r} >= {threshold}"
        rule_text = f"measured fire rate >= {threshold}"
    elif rule == "explicit":
        unknown = sorted(set(claims or []) - set(known))
        if unknown:
            raise ValueError(f"explicit always-on names unknown claims {unknown}")
        for cid in claims or []:
            why[cid] = "named explicitly"
        rule_text = "named explicitly"
    else:
        raise ValueError(f"unknown always-on rule {rule!r}")
    ao = [cid for cid in known if cid in why]
    cmap = {c["id"]: c for c in cl}
    return {"rule": rule, "rule_text": rule_text, "claims": ao, "reasons": why,
            "conditions": {cid: cmap[cid]["active_when"].strip() for cid in ao}}
