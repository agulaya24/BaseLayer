"""Builder: the category builder. Triggers to data-defined categories, by a model.

Categories are not a fixed vocabulary: the model reads this spec's triggers and names
the categories they fall into. The model sees each trigger's wording and the other
clauses grouped under it, shuffled by `seed`, under neutral ids, and nothing else (no
claim text, ids, layers or names). It returns, per category, a short name, a one-line
description and the member ids.

Mechanical after the reply: a trigger the reply leaves out goes to an "Unplaced"
category that is flagged for review (never silently merged into another), a repeated
trigger keeps its first placement, and unknown ids are dropped; each repair is counted.
Categories are ordered by size, then by first appearance, and numbered T1..Tn.

Output (categories assignment, stamped): the claim-level assignment the categories
stage reads, plus a `trigger_overrides` entry for EVERY trigger, so the stage uses the
builder's trigger placement outright and its majority rule never decides. A claim's
`members` entry is the category holding most of its triggers (ties: its first
trigger's), which keeps the claim lists a partition, as the stage requires. The
per-category coverage (triggers, claims, distinct facts) and the thin flags come from
running the categories stage itself on the result, so they are the counts the served
index will carry. Descriptions stay in this file; the served text shows names only.
"""
from __future__ import annotations

import random
from collections import Counter

from . import categories as cat_mod
from .backends import CallRunner, parse_json

TEMPLATE = "categorize/1 (wording + grouped clauses; names, descriptions, members)"
MAX_TOKENS = 32000
UNPLACED = {"name": "Unplaced", "description": "Triggers the category builder did not place; review them."}

HEAD = """Below are {n} situation lines. Each is a trigger: when it applies, some advice about one person applies. After "also:" a line lists other wordings grouped under the same trigger. Do not use any tool; answer directly from the text.

Task:
1. Group the lines into categories by the kind of SITUATION they describe (what is going on in the conversation or in the person's life), not by wording. Use as many categories as the lines need, between {lo} and {hi}. Every line goes in exactly one category.
2. Name each category by its situation, in plain words, at most 8 words (e.g. "Reviewing work someone else produced").
3. Describe each category in one line of at most 25 words, saying which situations it holds.

Return STRICT JSON only:
{{"categories": [{{"name": "...", "description": "...", "members": ["R01", ...]}}, ...]}}

Lines:
{lines}
"""


def default_range(n: int) -> tuple[int, int]:
    lo = max(2, n // 10)
    return lo, max(lo + 1, min(30, n // 3))


def trigger_line(t: dict) -> str:
    also = [m["clause"] for m in t["members"] if m["clause"] != t["wording_clause"]]
    also = list(dict.fromkeys(a.strip() for a in also))
    return t["wording"] + (f"  (also: {'; '.join(also)})" if also else "")


class ModelCategoryBuilder:
    def __init__(self, runner: CallRunner, *, seed: int = 20260930, lo: int | None = None, hi: int | None = None,
                 key_prefix: str = ""):
        self.runner, self.seed, self.lo, self.hi, self.key_prefix = runner, seed, lo, hi, key_prefix

    def call(self, triggers: list[dict]) -> tuple[dict, dict]:
        order = list(triggers)
        random.Random(self.seed).shuffle(order)
        width = max(2, len(str(len(order))))
        rid = {f"R{i:0{width}d}": t["id"] for i, t in enumerate(order, 1)}
        tby = {t["id"]: t for t in triggers}
        lo, hi = default_range(len(order))
        lo, hi = self.lo or lo, self.hi or hi
        prompt = HEAD.format(n=len(order), lo=lo, hi=hi,
                             lines="\n".join(f"{r}: {trigger_line(tby[tid])}" for r, tid in rid.items()))
        b = self.runner.backend

        def parse(text):
            p = parse_json(text)
            if not isinstance(p, dict) or not isinstance(p.get("categories"), list):
                return None
            ok = [c for c in p["categories"] if isinstance(c, dict) and isinstance(c.get("name"), str)
                  and isinstance(c.get("members"), list)]
            placed = {m for c in ok for m in c["members"] if m in rid}
            return p if ok and len(placed) >= len(rid) - max(1, len(rid) // 10) else None
        return {"key": f"{self.key_prefix}categorize|{TEMPLATE}|{b.name}|{b.model}|seed{self.seed}|c1",
                "prompt": prompt, "max_tokens": MAX_TOKENS, "parse": parse}, {"rid": rid, "lo": lo, "hi": hi}

    def build(self, claims_doc: dict, triggers_doc: dict, *, thin_claims: int = 3, thin_facts: int = 10) -> dict:
        trig = triggers_doc["triggers"]
        keys = [t["key"] for t in trig]
        if len(set(keys)) != len(keys):
            raise ValueError("trigger keys are not unique; category overrides are keyed by trigger key")
        call, info = self.call(trig)
        rid = info["rid"]
        res = self.runner.run([call], meta={"builder": "categorize"})
        got = res.get(call["key"])
        if got is None:
            raise RuntimeError("category builder: the call failed after retries; no assignment written")
        seen, cats, rep = set(), [], {"missing_triggers": [], "repeated_triggers": [], "unknown_ids": [],
                                      "empty_categories_dropped": 0}
        for n, c in enumerate(got["parsed"]["categories"]):
            if not (isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("members"), list)):
                continue
            mem = []
            for m in c["members"]:
                if m not in rid:
                    rep["unknown_ids"].append(m)
                elif m in seen:
                    rep["repeated_triggers"].append(rid[m])
                else:
                    seen.add(m)
                    mem.append(rid[m])
            if not mem:
                rep["empty_categories_dropped"] += 1
                continue
            cats.append({"name": c["name"].strip(), "description": str(c.get("description") or "").strip(),
                         "triggers": mem, "_first": n})
        missing = [rid[r] for r in rid if r not in seen]
        if missing:
            rep["missing_triggers"] = missing
            cats.append({**UNPLACED, "triggers": missing, "_first": 10 ** 6, "unplaced": True})
        tpos = {t["id"]: n for n, t in enumerate(trig)}
        cats.sort(key=lambda c: (bool(c.get("unplaced")), -len(c["triggers"]), c["_first"]))
        tcat, out = {}, []
        for i, c in enumerate(cats, 1):
            cid = f"T{i}"
            c["triggers"].sort(key=tpos.get)
            for t in c["triggers"]:
                tcat[t] = cid
            out.append({"id": cid, "name": c["name"], "description": c["description"], "triggers": c["triggers"],
                        "unplaced": bool(c.get("unplaced"))})
        # claim-level partition: the category holding most of a claim's triggers
        by_claim: dict[str, list[str]] = {}
        for t in trig:
            for x in t["claims"]:
                by_claim.setdefault(x, []).append(t["id"])
        members = {c["id"]: [] for c in out}
        for x in [c["id"] for c in claims_doc["claims"]]:
            ts = by_claim.get(x)
            if not ts:
                continue
            votes = Counter(tcat[t] for t in ts)
            top = max(votes.values())
            first = next(tcat[t] for t in ts if votes[tcat[t]] == top)
            members[first].append(x)
        tkey = {t["id"]: t["key"] for t in trig}
        assignment = {"method": f"model category builder ({TEMPLATE}); seed {self.seed}",
                      "categories": [{"id": c["id"], "name": c["name"], "description": c["description"],
                                      "members": members[c["id"]]} for c in out],
                      "trigger_overrides": {tkey[t]: tcat[t] for t in tcat}}
        cov = cat_mod.build(claims_doc, triggers_doc, assignment, thin_claims=thin_claims, thin_facts=thin_facts)
        coverage = [{"id": c["id"], "name": c["name"], "n_triggers": c["n_triggers"], "n_claims": c["n_claims"],
                     "n_facts": c["n_facts"], "thin": c["thin"]} for c in cov["categories"]]
        return {**assignment, "template": TEMPLATE,
                "params": {"seed": self.seed, "lo": info["lo"], "hi": info["hi"], "thin_claims": thin_claims,
                           "thin_facts": thin_facts},
                "trigger_categories": {t: tcat[t] for t in sorted(tcat, key=tpos.get)},
                "coverage": coverage,
                "gaps": {"thin": cov["thin_categories"], "empty": cov["empty_categories"],
                         "unplaced": [c["id"] for c in out if c["unplaced"]]},
                "repairs": rep}


def build(claims_doc: dict, triggers_doc: dict, runner: CallRunner, *, seed: int = 20260930,
          lo: int | None = None, hi: int | None = None, thin_claims: int = 3, thin_facts: int = 10,
          key_prefix: str = "") -> dict:
    return ModelCategoryBuilder(runner, seed=seed, lo=lo, hi=hi, key_prefix=key_prefix).build(
        claims_doc, triggers_doc, thin_claims=thin_claims, thin_facts=thin_facts)
