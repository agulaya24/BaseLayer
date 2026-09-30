"""Stage `checks`: mechanical checks over every consolidation output. No model.

A check that cannot run (its input is missing or unreadable) is a FAILURE, never a
skip: a verification that reports success when it did not run is worse than none.

    K01 claims.json matches the layer JSON re-read now (text, conditions, fact ids, flags, file hashes)
    K02 each layer's .md, when present, carries the same served block as its JSON
    K03 every clause is an exact substring of its claim's authored Active_When
    K04 every trigger wording is verbatim text of its source claim's condition, and the source is a member
    K05 every claim is reachable: always-on, or pulled by at least one trigger
    K06 always-on claims exist and are not hung off any trigger
    K07 trigger ids unique; no duplicate (claim, clause) edge within a trigger
    K08 no content-bearing span of any triggered claim's condition is left uncovered by its clauses
    K09 every trigger has exactly one category from the category set; coverage counts recompute
    K10 claim text unchanged: every index entry's text is the block rendered from the layers
    K11 fact ids preserved: per claim, and the union over the spec
    K12 served text: hash matches the index; always-on blocks and trigger lines present; every served id resolves
    K13 dedupe is a partition of the claims (each claim in exactly one group); no rewrite recorded
    K14 every stage output carries a complete stamp; the served stamp's hash matches the served text
"""
from __future__ import annotations

import json
import re

from . import spec as spec_mod
from .common import sha256_text

# ported verbatim from the 9/29 trigger index (build_index.py FILLER)
FILLER = {"and", "or", "the", "a", "an", "any", "of", "to", "in", "on", "when", "whenever", "they", "their", "them",
          "with", "for", "by", "is", "are", "at", "as", "or", "especially", "most", "all", "versus", "is", "who",
          "that", "it", "be", "being", "other", "others", "most of all", "then", "do", "does"}
STAMP_KEYS = ("stamp_version", "stage", "run_id", "git_commit", "code_sha256", "inputs", "inputs_hash", "params")


def uncovered(cond: str, clauses: list[str]) -> list[str]:
    """Spans of cond not covered by any clause, filler words dropped (ported)."""
    mask = [False] * len(cond)
    for cl in clauses:
        if not cl:
            continue
        i = cond.find(cl)
        while i >= 0:
            for k in range(i, i + len(cl)):
                mask[k] = True
            i = cond.find(cl, i + 1)
    spans, cur = [], ""
    for ch, m in zip(cond, mask):
        if m:
            if cur:
                spans.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        spans.append(cur)
    res = []
    for s in spans:
        words = [w for w in re.findall(r"[A-Za-z'\-]+", s) if w.lower() not in FILLER]
        if words:
            res.append(s.strip())
    return res


def _r(cid: str, name: str, ok: bool, detail=None) -> dict:
    return {"id": cid, "name": name, "pass": bool(ok), "detail": detail if not ok else None}


def _need(docs: dict, *names) -> list[str]:
    return [n for n in names if docs.get(n) is None]


def run(spec_dir, docs: dict, served: str | None, served_stamp: dict | None) -> dict:
    """docs: {"claims", "overlap", "dedupe", "always_on", "triggers", "categories", "index"} -> dict or None."""
    R = []

    def cannot(cid, name, missing):
        R.append(_r(cid, name, False, {"cannot_run": f"missing input: {', '.join(missing)}"}))

    # ---- K01
    name = "claims.json matches the layer JSON re-read now"
    layers = None
    try:
        layers, sources = spec_mod.load_layers(spec_dir, tuple(docs["claims"]["layers"]) if docs.get("claims")
                                               else spec_mod.DEFAULT_LAYERS)
    except Exception as e:  # noqa: BLE001 -- a check that cannot run fails
        R.append(_r("K01", name, False, {"cannot_run": f"{type(e).__name__}: {e}"}))
    if layers is not None:
        if docs.get("claims") is None:
            cannot("K01", name, ["claims.json"])
        else:
            L = {c["id"]: c for c in layers}
            got = {c["id"]: c for c in docs["claims"]["claims"]}
            diff = []
            if list(L) != docs["claims"]["order"]:
                diff.append({"order": "claim ids or order differ"})
            for cid, c in L.items():
                g = got.get(cid)
                if g is None:
                    diff.append({cid: "missing"})
                    continue
                for k in spec_mod.CLAIM_FIELDS:
                    if c[k] != g.get(k):
                        diff.append({cid: k})
            for f, h in sources.items():
                if docs["claims"]["sources"].get(f) != h:
                    diff.append({f: "file hash changed since the claims stage"})
            R.append(_r("K01", name, not diff, diff[:50]))

    # ---- K02
    name = "each layer's .md carries the same served block as its JSON"
    if _need(docs, "claims"):
        cannot("K02", name, ["claims.json"])
    else:
        bad = {lay: v for lay, v in docs["claims"]["md_comparison"].items()
               if v.get("present") and (v["missing_in_md"] or v["extra_in_md"] or v["block_mismatch"])}
        R.append(_r("K02", name, not bad, bad))

    trig_ok = not _need(docs, "claims", "always_on", "triggers")
    cmap = {c["id"]: c for c in (layers or (docs.get("claims") or {}).get("claims") or [])}
    trig = (docs.get("triggers") or {}).get("triggers") or []
    ao = set((docs.get("always_on") or {}).get("claims") or [])

    # ---- K03
    name = "every clause is an exact substring of its claim's authored Active_When"
    if not trig_ok:
        cannot("K03", name, _need(docs, "claims", "always_on", "triggers"))
    else:
        bad = [[t["id"], m["claim"], m["clause"]] for t in trig for m in t["members"]
               if m["claim"] not in cmap or not m["clause"] or m["clause"] not in cmap[m["claim"]]["active_when"]]
        R.append(_r("K03", name, not bad, bad[:50]))

    # ---- K04
    name = "every trigger wording is verbatim text of its source claim's condition; the source is a member"
    if not trig_ok:
        cannot("K04", name, _need(docs, "claims", "always_on", "triggers"))
    else:
        bad = []
        for t in trig:
            cond = cmap.get(t["wording_source"], {}).get("active_when", "")
            w = t["wording"]
            ok = bool(w) and ((w in cond) or ((w[0].lower() + w[1:]) in cond))
            ok = ok and t["wording_source"] in t["claims"]
            if not ok:
                bad.append([t["id"], t["wording"]])
        R.append(_r("K04", name, not bad, bad[:50]))

    # ---- K05, K06
    if not trig_ok:
        cannot("K05", "every claim is always-on or reachable from a trigger", _need(docs, "claims", "always_on", "triggers"))
        cannot("K06", "always-on claims exist and are not hung off any trigger", _need(docs, "claims", "always_on", "triggers"))
    else:
        reach = {c for t in trig for c in t["claims"]}
        miss = sorted(set(cmap) - ao - reach)
        R.append(_r("K05", "every claim is always-on or reachable from a trigger", not miss, miss))
        both = sorted(ao & reach)
        unknown = sorted(ao - set(cmap))
        R.append(_r("K06", "always-on claims exist and are not hung off any trigger", not both and not unknown,
                    {"on_a_trigger": both, "unknown": unknown}))

    # ---- K07
    name = "trigger ids unique; no duplicate (claim, clause) edge"
    if not trig_ok:
        cannot("K07", name, _need(docs, "triggers"))
    else:
        ids = [t["id"] for t in trig]
        dup = [t["id"] for t in trig if len({(m["claim"], m["clause"]) for m in t["members"]}) != len(t["members"])]
        R.append(_r("K07", name, len(ids) == len(set(ids)) and not dup,
                    {"duplicate_ids": sorted({i for i in ids if ids.count(i) > 1}), "duplicate_edges": dup}))

    # ---- K08
    name = "no content-bearing span of any triggered claim's condition is left uncovered"
    if not trig_ok:
        cannot("K08", name, _need(docs, "claims", "always_on", "triggers"))
    else:
        cov = {}
        for cid, c in cmap.items():
            if cid in ao:
                continue
            cls = [m["clause"] for t in trig for m in t["members"] if m["claim"] == cid]
            u = uncovered(c["active_when"].strip(), cls)
            if u:
                cov[cid] = u
        R.append(_r("K08", name, not cov, cov))

    # ---- K09
    name = "every trigger has one category from the set; coverage counts recompute"
    if _need(docs, "claims", "triggers", "categories"):
        cannot("K09", name, _need(docs, "claims", "triggers", "categories"))
    else:
        cd = docs["categories"]
        cat_ids = [c["id"] for c in cd["categories"]]
        tc = cd["trigger_category"]
        prob = []
        tids = [t["id"] for t in trig]
        no_cat = [t for t in tids if tc.get(t) not in cat_ids]
        if no_cat:
            prob.append({"no_valid_category": no_cat})
        listed = [t for c in cd["categories"] for t in c["triggers"]]
        if sorted(listed) != sorted(tids) or len(listed) != len(set(listed)):
            prob.append({"triggers_listed_under_categories": "not exactly once each"})
        if sorted(cd["order"]) != sorted(tids):
            prob.append({"order": "does not list every trigger once"})
        tby = {t["id"]: t for t in trig}
        for c in cd["categories"]:
            if any(tc.get(t) != c["id"] for t in c["triggers"]):
                prob.append({c["id"]: "lists a trigger assigned elsewhere"})
            pulled = list(dict.fromkeys(x for t in c["triggers"] if t in tby for x in tby[t]["claims"]))
            nf = len({f for x in pulled if x in cmap for f in cmap[x]["fact_ids"]})
            if (c["n_triggers"], c["n_claims"], c["n_facts"]) != (len(c["triggers"]), len(pulled), nf):
                prob.append({c["id"]: {"stored": [c["n_triggers"], c["n_claims"], c["n_facts"]],
                                       "recomputed": [len(c["triggers"]), len(pulled), nf]}})
        R.append(_r("K09", name, not prob, prob))

    # ---- K10, K11
    if _need(docs, "index") or layers is None:
        cannot("K10", "claim text unchanged: index text equals the block rendered from the layers",
               _need(docs, "index") or ["layer JSON"])
        cannot("K11", "fact ids preserved per claim and in union", _need(docs, "index") or ["layer JSON"])
    else:
        ic = docs["index"]["claims"]
        bad = [cid for cid, c in cmap.items() if cid not in ic or ic[cid]["text"] != spec_mod.render_block(c)]
        # Independent of render_block, so a defect in the one renderer cannot pass on both sides:
        # the header opens the text and the name, statement and condition each appear verbatim.
        for cid, c in cmap.items():
            t = ic.get(cid, {}).get("text", "")
            if not (t.startswith(f"## {cid} {c['name']}") and c["statement"] in t
                    and (not c["active_when"] or f"*Active when:* {c['active_when']}" in t)):
                if cid not in bad:
                    bad.append(cid)
        extra = sorted(set(ic) - set(cmap))
        R.append(_r("K10", "claim text unchanged: index text equals the block rendered from the layers",
                    not bad and not extra, {"changed_or_missing": bad, "extra": extra}))
        badf = [cid for cid, c in cmap.items() if cid in ic and list(ic[cid]["fact_ids"]) != list(c["fact_ids"])]
        u_layers = {f for c in cmap.values() for f in c["fact_ids"]}
        u_index = {f for c in ic.values() for f in c["fact_ids"]}
        R.append(_r("K11", "fact ids preserved per claim and in union", not badf and u_layers == u_index,
                    {"claims_changed": badf, "lost": sorted(u_layers - u_index)[:50],
                     "added": sorted(u_index - u_layers)[:50]}))

    # ---- K12
    name = "served text: hash matches the index; always-on blocks and trigger lines present; ids resolve"
    if served is None or _need(docs, "index", "triggers", "always_on", "categories"):
        cannot("K12", name, (["served.txt"] if served is None else []) + _need(docs, "index", "triggers", "always_on", "categories"))
    else:
        ix = docs["index"]
        prob = []
        if sha256_text(served) != ix["served_sha256"]:
            prob.append("served text hash differs from index.served_sha256")
        for c in docs["always_on"]["claims"]:
            if c not in ix["claims"] or ix["claims"][c]["text"] not in served:
                prob.append(f"always-on block {c} not in served text")
        tc = docs["categories"]["trigger_category"]
        for t in trig:
            line = f"- {t['wording'].rstrip()} -> {', '.join(t['claims'])}"
            if tc.get(t["id"]) and line not in served:
                prob.append(f"trigger line {t['id']} not in served text")
        ids_in_text = set()
        for ln in served.splitlines():
            if ln.startswith("- ") and " -> " in ln:
                ids_in_text |= {x.strip() for x in ln.rsplit(" -> ", 1)[1].split(",")}
        unresolved = sorted(ids_in_text - set(ix["claims"]))
        if unresolved:
            prob.append({"served ids with no index entry": unresolved})
        R.append(_r("K12", name, not prob, prob[:50]))

    # ---- K13
    name = "dedupe is a partition of the claims; no rewrite"
    if _need(docs, "dedupe") or not cmap:
        cannot("K13", name, _need(docs, "dedupe") or ["claims"])
    else:
        dd = docs["dedupe"]
        members = [m for g in dd["groups"] for m in g["members"]]
        prob = []
        if sorted(members) != sorted(cmap) or len(members) != len(set(members)):
            prob.append("groups do not cover every claim exactly once")
        if any(dd["claim_to_group"].get(m) != g["id"] for g in dd["groups"] for m in g["members"]):
            prob.append("claim_to_group disagrees with groups")
        if any(k in g for g in dd["groups"] for k in ("statement", "name", "merged_text")):
            prob.append("a group carries rewritten text")
        R.append(_r("K13", name, not prob, prob))

    # ---- K14
    name = "every stage output carries a complete stamp; served stamp hash matches"
    prob = []
    for n in ("claims", "overlap", "dedupe", "always_on", "triggers", "categories", "index"):
        d = docs.get(n)
        if d is None:
            prob.append(f"{n}: missing")
            continue
        st = d.get("stamp") or {}
        miss = [k for k in STAMP_KEYS if k not in st]
        if miss:
            prob.append(f"{n}: stamp lacks {miss}")
    if served is None or served_stamp is None:
        prob.append("served.txt or served.stamp.json missing")
    else:
        miss = [k for k in STAMP_KEYS if k not in served_stamp]
        if miss:
            prob.append(f"served.stamp.json lacks {miss}")
        if served_stamp.get("served_sha256") != sha256_text(served):
            prob.append("served.stamp.json served_sha256 does not match served.txt")
    R.append(_r("K14", name, not prob, prob))

    return {"passed": all(r["pass"] for r in R), "n_checks": len(R),
            "failed": [r["id"] for r in R if not r["pass"]], "checks": R}


def format_checks(result: dict) -> str:
    lines = []
    for r in result["checks"]:
        lines.append(f"{'PASS' if r['pass'] else 'FAIL'}  {r['id']} {r['name']}")
        if not r["pass"]:
            lines.append("      " + json.dumps(r["detail"], ensure_ascii=False)[:600])
    return "\n".join(lines)
