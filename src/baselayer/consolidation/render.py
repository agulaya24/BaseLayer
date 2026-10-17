"""Stage `render`: the served text and the machine-readable index the pull tool reads.

Served text (the layout chosen by the 2026-09-29 layout eval, arm LINES):

    <resident header>

    <each always-on claim's block, in full>

    <index header>

    [T1 <category name>]
    - <trigger wording> -> <claim id>, <claim id>
    ...

    <fetch instruction>

Categories with no trigger are left out of the text (they are reported by the categories
stage as gaps). Claim blocks are the claims stage's blocks, unchanged.

Index (index.json): claim id -> full served block, fact ids, contested flag and note,
layer, triggers and categories that reach it, duplicate group; plus the always-on list,
the categories with their triggers, and the sha256 of the served text it belongs with.

Templates are parameters. `{subject}` is the person's name and `{possessive}` the
pronoun the fetch instruction uses. With no subject the unnamed templates are used.
The fetch instruction is the eval's reply-line protocol; a server that exposes pulling
as a tool call replaces it through the `fetch_instruction` template.
"""
from __future__ import annotations

from .common import sha256_text

NAMED = {
    "resident_header": "{subject}'s specification: the standing claims below apply to every message.",
    "index_header": ("{subject}'s specification is indexed below by category and by situation; each situation "
                     "lists the ids of the claims that apply in that situation. If a situation applies to the "
                     "current message, fetch those claims before answering."),
    "fetch_instruction": ("To fetch claims from the behavioural specification of {subject}, the user, reply with "
                          "exactly one line of the form `get_claims: [id1, id2, ...]` and nothing else; the claim "
                          "text will then be sent to you and you answer the user's message. Fetch when "
                          "{possessive} preferences, patterns or judgement are relevant. Otherwise answer the "
                          "message directly."),
}
UNNAMED = {
    "resident_header": "The user's specification: the standing claims below apply to every message.",
    "index_header": ("The user's specification is indexed below by category and by situation; each situation "
                     "lists the ids of the claims that apply in that situation. If a situation applies to the "
                     "current message, fetch those claims before answering."),
    "fetch_instruction": ("To fetch claims from the user's behavioural specification, reply with exactly one line "
                          "of the form `get_claims: [id1, id2, ...]` and nothing else; the claim text will then be "
                          "sent to you and you answer the user's message. Fetch when {possessive} preferences, "
                          "patterns or judgement are relevant. Otherwise answer the message directly."),
}


def templates_for(subject: str | None, overrides: dict | None = None, possessive: str = "their") -> dict:
    base = dict(NAMED if subject else UNNAMED)
    base.update(overrides or {})
    return {k: v.format(subject=subject or "", possessive=possessive) for k, v in base.items()}


def category_block(cat: dict, trig_by_id: dict) -> str:
    rows = [f"- {trig_by_id[t]['wording'].rstrip()} -> {', '.join(trig_by_id[t]['claims'])}" for t in cat["triggers"]]
    return f"[{cat['id']} {cat['name']}]\n" + "\n".join(rows)


def served_text(claims_doc: dict, always_on_doc: dict, triggers_doc: dict, categories_doc: dict,
                tpl: dict) -> str:
    cmap = {c["id"]: c for c in claims_doc["claims"]}
    tby = {t["id"]: t for t in triggers_doc["triggers"]}
    parts = []
    if always_on_doc["claims"]:
        parts.append(tpl["resident_header"] + "\n\n" + "\n\n".join(cmap[c]["block"] for c in always_on_doc["claims"]))
    cats = [c for c in categories_doc["categories"] if c["triggers"]]
    if cats:
        parts.append(tpl["index_header"] + "\n\n" + "\n\n".join(category_block(c, tby) for c in cats))
    if tpl.get("fetch_instruction"):
        parts.append(tpl["fetch_instruction"])
    return "\n\n".join(parts)


def build(claims_doc: dict, always_on_doc: dict, triggers_doc: dict, categories_doc: dict,
          dedupe_doc: dict | None = None, *, subject: str | None = None, possessive: str = "their",
          template_overrides: dict | None = None) -> tuple[str, dict]:
    tpl = templates_for(subject, template_overrides, possessive)
    text = served_text(claims_doc, always_on_doc, triggers_doc, categories_doc, tpl)
    tcat = categories_doc["trigger_category"]
    cname = {c["id"]: c["name"] for c in categories_doc["categories"]}
    reach: dict[str, list[str]] = {}
    for t in triggers_doc["triggers"]:
        for c in t["claims"]:
            reach.setdefault(c, []).append(t["id"])
    ao = set(always_on_doc["claims"])
    groups = {g["id"]: g["members"] for g in (dedupe_doc or {}).get("groups", [])}
    c2g = (dedupe_doc or {}).get("claim_to_group", {})
    claims = {}
    for c in claims_doc["claims"]:
        g = c2g.get(c["id"])
        claims[c["id"]] = {
            "text": c["block"], "name": c["name"], "layer": c["layer"], "active_when": c["active_when"],
            "fact_ids": list(c["fact_ids"]), "contested": c["contested"], "contested_note": c.get("contested_note"),
            "always_on": c["id"] in ao, "triggers": reach.get(c["id"], []),
            "categories": list(dict.fromkeys(tcat[t] for t in reach.get(c["id"], []) if tcat.get(t))),
            "duplicate_group": g, "duplicates": [m for m in groups.get(g, []) if m != c["id"]] if g else [],
        }
    tby = {t["id"]: t for t in triggers_doc["triggers"]}
    index = {
        "served_sha256": sha256_text(text), "served_chars": len(text), "subject": subject,
        "templates": tpl,
        "always_on": list(always_on_doc["claims"]),
        "categories": [{"id": c["id"], "name": c["name"], "thin": c["thin"],
                        "triggers": [{"id": t, "key": tby[t]["key"], "wording": tby[t]["wording"],
                                      "claims": tby[t]["claims"]} for t in c["triggers"]]}
                       for c in categories_doc["categories"]],
        "triggers": {t["id"]: {"key": t["key"], "wording": t["wording"], "claims": t["claims"],
                               "category": tcat.get(t["id"]), "category_name": cname.get(tcat.get(t["id"]))}
                     for t in triggers_doc["triggers"]},
        "claims": claims,
    }
    return text, index
