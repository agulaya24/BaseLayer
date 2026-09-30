"""(c) Time split: a contested claim whose two sides come from different periods is a change
over time, not a contradiction.

Input: a side assignment per cited fact of each contested claim ({claim id: {fact id: "1"|"2"}}),
from a side source such as the model-judged back-check (see backcheck.py). This check never
assigns sides itself; without a side source it does not run.

For one contested claim, over the live, dated facts on each side:
  - for each orientation (side 1 earlier, or side 2 earlier) and each cut between two distinct
    dates, accuracy = share of facts on the expected side of the cut; the best is kept;
  - clean split: accuracy 1.0 (every fact of one side before every fact of the other);
  - the claim is labelled `changed_over_time` (flag) when accuracy >= `majority` AND the median
    dates of the two sides are at least `min_gap_days` apart. This is a review flag for a person,
    never an automatic relabel: on a real specification the side labels of the model-judged
    back-check did not encode its own time-split readings (one side held facts from both periods),
    and most of its labels fell on claims that back-check read as real contradictions;
  - otherwise `not_separated` (pass), or `undetermined` (pass) when a side has no dated fact.
A contested claim with no side assignment at all is flagged as an input gap.

Both thresholds were fixed before the check was first run on a real specification:
majority 0.8, min_gap_days 30.
"""
from __future__ import annotations

import statistics
import time

from .base import CheckContext, CheckResult, CheckRun, fact_when, live_facts

NAME = "time_split"
DESCRIPTION = "contested claims whose sides separate by date: changed over time, not a contradiction"
NEEDS = ("sides",)
DEFAULTS = {"majority": 0.8, "min_gap_days": 30.0}
DAY = 86400.0


def _d(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts is not None else None


def best_split(early: list[float], late: list[float]) -> tuple[float, float | None]:
    """(accuracy, cut) for `early` expected before `late`; the cut is the last time counted early."""
    n = len(early) + len(late)
    cuts = sorted(set(early) | set(late))
    best, best_cut = -1.0, None
    # a cut at t puts every fact at or before t on the early side; include "everything late"
    for cut in [cuts[0] - 1.0] + cuts:
        acc = (sum(1 for t in early if t <= cut) + sum(1 for t in late if t > cut)) / n
        if acc > best:
            best, best_cut = acc, cut
    return best, best_cut


def assess(side1: list[float], side2: list[float], majority: float, min_gap_days: float) -> dict:
    if not side1 or not side2:
        return {"label": "undetermined", "why": "a side has no dated live fact", "n1": len(side1), "n2": len(side2)}
    a12, c12 = best_split(side1, side2)
    a21, c21 = best_split(side2, side1)
    if a12 >= a21:
        acc, cut, early_side = a12, c12, "1"
        early, late = side1, side2
    else:
        acc, cut, early_side = a21, c21, "2"
        early, late = side2, side1
    gap = (statistics.median(late) - statistics.median(early)) / DAY
    clean = acc == 1.0
    label = "changed_over_time" if acc >= majority and gap >= min_gap_days else "not_separated"
    return {"label": label, "accuracy": round(acc, 3), "clean": clean, "earlier_side": early_side,
            "cut_date": _d(cut), "median_gap_days": round(gap, 1), "n1": len(side1), "n2": len(side2),
            "side1_dates": [_d(min(side1)), _d(statistics.median(side1)), _d(max(side1))],
            "side2_dates": [_d(min(side2)), _d(statistics.median(side2)), _d(max(side2))]}


def run(ctx: CheckContext, majority: float = 0.8, min_gap_days: float = 30.0) -> CheckRun:
    sides = ctx.options.get("sides")
    params = {"majority": majority, "min_gap_days": min_gap_days,
              "side_source": ctx.options.get("sides_source")}
    if not sides:
        return CheckRun(NAME, "not_run", "no side assignment for contested claims (a side source, e.g. "
                        "--backcheck-results)", params)
    results, labels = [], {}
    for cl in ctx.spec.claims:
        if not cl.contested:
            continue
        assign = sides.get(cl.id)
        if not assign:
            labels[cl.qid] = "no_sides"
            results.append(CheckResult(NAME, cl.qid, "flag", "contested, but the side source assigns no sides", [],
                                       {"label": "no_sides"}))
            continue
        s1, s2, ids = [], [], {"1": [], "2": []}
        for f in live_facts(ctx, cl):
            side = assign.get(f.fid) or assign.get(f.cited) or assign.get(f.full_id)
            if side not in ("1", "2"):
                continue
            ts, _ = fact_when(ctx, f)
            if ts is None:
                continue
            (s1 if side == "1" else s2).append(ts)
            ids[side].append(f.fid)
        a = assess(s1, s2, majority, min_gap_days)
        labels[cl.qid] = a["label"]
        if a["label"] == "changed_over_time":
            reason = (f"sides separate by date, possibly a change over time rather than a contradiction "
                      f"(a review flag, not a relabel): side {a['earlier_side']} earlier "
                      f"(split accuracy {a['accuracy']}, {'clean' if a['clean'] else 'majority'}, "
                      f"median gap {a['median_gap_days']} days, cut {a['cut_date']})")
            st = "flag"
        elif a["label"] == "undetermined":
            reason, st = a["why"], "pass"
        else:
            reason = (f"sides do not separate by date (best split accuracy {a['accuracy']}, "
                      f"median gap {a['median_gap_days']} days)")
            st = "pass"
        results.append(CheckResult(NAME, cl.qid, st, reason, ids["1"] + ids["2"], {**a, "side_facts": ids}))
    summary = {"contested": sum(1 for c in ctx.spec.claims if c.contested),
               "labels": {k: sum(1 for v in labels.values() if v == k)
                          for k in ("changed_over_time", "not_separated", "undetermined", "no_sides")}}
    return CheckRun(NAME, "ran", "", params, results, summary)
