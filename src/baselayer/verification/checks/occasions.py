"""(b) Occasions: how many separate occasions a claim's evidence comes from.

For each claim, over its live cited facts:
  conversations  distinct source sessions (an id ending in a UUID is keyed on that UUID, so one
                 session imported twice counts once; see base.session_key)
  dates          distinct calendar dates of the facts (the first evidence span's turn time, else
                 the conversation's; the source of each date is counted)
  occasions      by `unit`: 'date' = dates, 'conversation' = conversations, 'min' = the smaller
                 of the two (a lower bound: several facts from one long session, or from several
                 sessions on one day, count once)

A claim in `layers` (default: predictions) resting on fewer than `min_occasions` occasions is
flagged: a prediction asserts a habit, and one occasion cannot show a habit. The threshold is a
parameter; the summary carries the full distribution so it can be chosen from data.
"""
from __future__ import annotations

import collections

from .base import CheckContext, CheckResult, CheckRun, day, fact_session, fact_when, live_facts

NAME = "occasions"
DESCRIPTION = "claims (predictions by default) resting on too few separate occasions"
NEEDS = ()
UNITS = ("date", "conversation", "min")
DEFAULTS = {"min_occasions": 2, "unit": "min", "layers": ("predictions",), "tz_offset_hours": 0.0}


def profile(ctx: CheckContext, cl, tz_offset_hours: float = 0.0) -> dict:
    facts = live_facts(ctx, cl)
    sessions, dates, src = set(), set(), collections.Counter()
    for f in facts:
        s = fact_session(ctx, f)
        if s:
            sessions.add(s)
        ts, how = fact_when(ctx, f)
        src[how] += 1
        d = day(ts, tz_offset_hours)
        if d:
            dates.add(d)
    return {"live_facts": len(facts), "conversations": len(sessions), "dates": len(dates),
            "first": min(dates) if dates else None, "last": max(dates) if dates else None,
            "date_source": dict(src)}


def occasions_of(p: dict, unit: str) -> int:
    if unit == "date":
        return p["dates"]
    if unit == "conversation":
        return p["conversations"]
    return min(p["dates"], p["conversations"])


def run(ctx: CheckContext, min_occasions: int = 2, unit: str = "min", layers=("predictions",),
        tz_offset_hours: float = 0.0) -> CheckRun:
    if unit not in UNITS:
        return CheckRun(NAME, "error", f"unit must be one of {UNITS}", {"unit": unit})
    layers = tuple(layers) if layers else ()
    params = {"min_occasions": min_occasions, "unit": unit, "layers": list(layers), "tz_offset_hours": tz_offset_hours}
    results = []
    dist = {u: collections.defaultdict(collections.Counter) for u in UNITS}
    src_total = collections.Counter()
    for cl in ctx.spec.claims:
        p = profile(ctx, cl, tz_offset_hours)
        src_total.update(p["date_source"])
        for u in UNITS:
            dist[u][cl.layer][occasions_of(p, u)] += 1
        n = occasions_of(p, unit)
        p["occasions"] = n
        applies = (not layers) or cl.layer in layers
        if applies and n < min_occasions:
            st = "flag"
            reason = (f"{n} occasion(s) by {unit} ({p['conversations']} conversation(s), {p['dates']} date(s)) "
                      f"under the minimum of {min_occasions}")
        else:
            st = "pass"
            reason = f"{n} occasion(s) by {unit}" + ("" if applies else f" (layer {cl.layer} not checked)")
        results.append(CheckResult(NAME, cl.qid, st, reason, [], p))
    summary = {"distribution": {u: {layer: dict(sorted(c.items())) for layer, c in by.items()} for u, by in dist.items()},
               "date_source_of_live_citations": dict(src_total)}
    return CheckRun(NAME, "ran", "", params, results, summary)
