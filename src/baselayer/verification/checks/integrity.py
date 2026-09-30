"""(d) Mechanical integrity: every citation resolves, none is excluded, every quoted span is in its turn.

Per claim:
  citations   every cited id resolves to exactly one live fact (fail otherwise)
  exclusions  no cited fact is on an exclude list (--exclude-ids, repeatable; the distillation
              reader parses the files, so the same file that removed facts from a build checks it)
  spans       every evidence span of every live cited fact is found in its turn:
                exact       a verbatim substring                                  ok
                normalised  found after whitespace and quote-mark normalisation   ok (the turn
                            contract's own match rule, TURN_CONTRACT.md section 5)
                case_only   found only after also folding case                    flag
                not_found   not found, or the turn does not exist                 fail
              A fact with no evidence span has nothing to check and is counted (flag).
  quotes      every quoted phrase in the claim's name, statement or Active_When appears, at word
              boundaries, in an own-voice span of a live fact the claim cites (the author quote
              gate's rule, re-run on the artifact): elided (an ellipsis) flag, not found fail.
"""
from __future__ import annotations

from baselayer.distillation import quote_gate as qg

from ..corpus import norm_span
from ..definitions import OWN_VOICE_CLASSES
from .base import CheckContext, CheckResult, CheckRun, worst

NAME = "integrity"
DESCRIPTION = "citations resolve, none excluded, evidence spans and claim quotes found in their turns"
NEEDS = ()
SPAN_CLASSES = ("exact", "normalised", "case_only", "not_found", "no_turn")


def load_excludes(paths) -> tuple[dict, list[dict]]:
    """({id or 8-char prefix: file name}, per-file info). Raises ValueError on an unreadable or
    malformed file (distill.read_exclude_ids refuses those with SystemExit)."""
    from baselayer.distillation.distill import read_exclude_ids
    ids, info = {}, []
    for p in paths or ():
        try:
            got, sha = read_exclude_ids(str(p))
        except SystemExit as e:
            raise ValueError(str(e))
        for i in got:
            ids.setdefault(i.lower(), str(p))
        info.append({"file": str(p), "sha256": sha, "ids": len(got)})
    return ids, info


def span_class(span: str, turn_text: str) -> str:
    if span and span in turn_text:
        return "exact"
    a, b = norm_span(span), norm_span(turn_text)
    if a and a in b:
        return "normalised"
    if a and a.lower() in b.lower():
        return "case_only"
    return "not_found"


def _excluded(f, excl: dict) -> str | None:
    if not excl or not f.full_id:
        return None
    return excl.get(f.full_id.lower()) or excl.get(f.full_id[:8].lower())


def run(ctx: CheckContext) -> CheckRun:
    paths = ctx.options.get("exclude_ids") or []
    params = {"exclude_ids": [str(p) for p in paths]}
    try:
        excl, info = load_excludes(paths)
    except ValueError as e:
        return CheckRun(NAME, "error", str(e), params)
    params["exclude_files"] = info
    span_memo: dict[str, list] = {}
    totals = {"citations": 0, "unresolved": 0, "excluded": 0, "facts_without_spans": 0,
              "spans": dict.fromkeys(SPAN_CLASSES, 0), "quotes": 0, "quotes_elided": 0, "quotes_not_found": 0}
    distinct = {"facts": set(), "excluded": set(), "unresolved": set()}
    results = []
    for cl in ctx.spec.claims:
        items, statuses, evidence = [], [], []
        seen, live = set(), []
        for cited in cl.fact_ids:
            if cited in seen:
                continue
            seen.add(cited)
            totals["citations"] += 1
            f = ctx.corpus.fact(cited)
            if f.status != "live":
                totals["unresolved"] += 1
                distinct["unresolved"].add(f.fid)
                items.append({"fact": f.fid, "problem": f"unresolved ({f.status})"})
                statuses.append("fail")
                evidence.append(f.fid)
                continue
            live.append(f)
            distinct["facts"].add(f.full_id)
            src = _excluded(f, excl)
            if src:
                totals["excluded"] += 1
                distinct["excluded"].add(f.fid)
                items.append({"fact": f.fid, "problem": f"on exclude list {src}"})
                statuses.append("fail")
                evidence.append(f.fid)
            if f.full_id not in span_memo:
                rows = []
                for sp in f.evidence_spans or ():
                    tid = sp.get("turn_id") if isinstance(sp, dict) else None
                    t = ctx.corpus.turn(tid) if tid else None
                    klass = "no_turn" if t is None else span_class(str(sp.get("span") or ""), t["text"])
                    rows.append({"turn_id": tid, "class": klass,
                                 "own": bool(t and t.get("voice_class") in OWN_VOICE_CLASSES),
                                 "span": str(sp.get("span") or "")})
                span_memo[f.full_id] = rows
                if not rows:
                    totals["facts_without_spans"] += 1
                for r in rows:
                    totals["spans"][r["class"]] += 1
            rows = span_memo[f.full_id]
            if not rows:
                items.append({"fact": f.fid, "problem": "no evidence span to check"})
                statuses.append("flag")
            for r in rows:
                if r["class"] in ("not_found", "no_turn"):
                    items.append({"fact": f.fid, "turn": r["turn_id"], "problem": f"span {r['class']}",
                                  "span": r["span"][:200]})
                    statuses.append("fail")
                    evidence.append(f.fid)
                elif r["class"] == "case_only":
                    items.append({"fact": f.fid, "turn": r["turn_id"], "problem": "span matches only after case folding",
                                  "span": r["span"][:200]})
                    statuses.append("flag")
                    evidence.append(f.fid)
        # quotes in the claim's own text
        own_spans = [qg.normalise(r["span"]) for f in live for r in span_memo.get(f.full_id, []) if r["own"]]
        for field in qg.FIELDS:
            for q in qg.quoted_phrases(getattr(cl, field, "") or ""):
                totals["quotes"] += 1
                if qg._ELLIPSIS.search(q.inner):
                    totals["quotes_elided"] += 1
                    items.append({"quote": q.raw, "field": field, "problem": "quote carries an ellipsis"})
                    statuses.append("flag")
                    continue
                n = qg.normalise(q.inner)
                if not any(qg.contains_words(s, n) for s in own_spans):
                    totals["quotes_not_found"] += 1
                    items.append({"quote": q.raw, "field": field,
                                  "problem": "quoted words not in an own-voice span of a cited fact"})
                    statuses.append("fail")
        st = worst(statuses)
        reason = "; ".join(sorted({i["problem"] for i in items})) if items else "all citations, spans and quotes check out"
        results.append(CheckResult(NAME, cl.qid, st, reason, list(dict.fromkeys(evidence)), {"items": items}))
    summary = {**totals, "distinct_live_cited_facts": len(distinct["facts"]),
               "distinct_excluded": sorted(distinct["excluded"]), "distinct_unresolved": sorted(distinct["unresolved"]),
               "span_note": "spans are counted once per distinct live cited fact"}
    return CheckRun(NAME, "ran", "", params, results, summary)
