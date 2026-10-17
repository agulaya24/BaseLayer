"""Agreement with a loaded back-check, and the one-page markdown summary of the modular checks."""
from __future__ import annotations

import collections

from .occasions import UNITS, occasions_of


def compare_with_backcheck(runs: dict, data, spec) -> dict:
    """How the deterministic checks line up with the model-judged back-check, when one is loaded.

    occasions: the back-check's support failures (verdict overreaches or unsupported) caught by the
    occasions flag, per layer, and the flagged claims that are NOT support failures, for thresholds
    2, 3 and 4 in every unit. time_split: the time-split label against the judge's contested verdict.
    """
    if data is None:
        return {}
    out = {}
    layer = {c.id: c.layer for c in spec.claims}
    fails = {cid for cid, r in data.claims.items()
             if (r.get("fails_support") if r.get("fails_support") is not None
                 else r.get("verdict") in ("overreaches", "unsupported"))}
    occ = runs.get("occasions")
    if occ is not None and occ.status == "ran":
        prof = {r.claim.split(":", 1)[1]: r.data for r in occ.results}
        table = []
        for unit in UNITS:
            for t in (2, 3, 4):
                low = {cid for cid, p in prof.items() if occasions_of(p, unit) < t}
                low_p = {c for c in low if layer.get(c) == "predictions"}
                fails_p = {c for c in fails if layer.get(c) == "predictions"}
                table.append({"unit": unit, "threshold": t,
                              "predictions_flagged": len(low_p),
                              "predictions_support_failures_caught": len(low_p & fails_p),
                              "predictions_support_failures": len(fails_p),
                              "predictions_flagged_not_failing": len(low_p - fails),
                              "all_below": len(low), "all_support_failures_caught": len(low & fails),
                              "all_support_failures": len(fails)})
        flagged = {r.claim.split(":", 1)[1] for r in occ.results if r.status == "flag"}
        out["occasions"] = {"support_failures": sorted(fails, key=_key),
                            "flagged_and_failing": sorted(flagged & fails, key=_key),
                            "flagged_not_failing": sorted(flagged - fails, key=_key),
                            "failing_not_flagged": sorted({c for c in fails if layer.get(c) in
                                                           occ.params.get("layers", [])} - flagged, key=_key),
                            "threshold_table": table}
    ts = runs.get("time_split")
    if ts is not None and ts.status == "ran":
        conf = collections.Counter()
        rows = []
        for r in ts.results:
            cid = r.claim.split(":", 1)[1]
            cv = (data.claims.get(cid) or {}).get("contested_verdict") or "none"
            lab = r.data.get("label")
            conf[(lab, cv)] += 1
            rows.append({"claim": cid, "label": lab, "judge": cv})
        out["time_split"] = {"confusion": {f"{a} | judge {b}": n for (a, b), n in sorted(conf.items())},
                             "changed_over_time": [x for x in rows if x["label"] == "changed_over_time"],
                             "caveat": "the sides come from the same judge that made the contested calls, so "
                                       "agreement is partly the judge agreeing with itself"}
    return out


def _key(cid):
    return (cid[0], int(cid[1:]) if cid[1:].isdigit() else 0)


def render(label: str, runs: dict, comparison: dict, meta: dict) -> str:
    L = [f"# Verify summary: {label}", ""]
    L.append(f"- Spec: `{meta.get('spec_dir')}` ({meta.get('n_claims')} claims); corpus opened {meta.get('open_mode')}")
    if meta.get("out_note"):
        L.append(f"- {meta['out_note']}")
    L += ["", "| check | run | pass | flag | fail | note |", "|---|---|---|---|---|---|"]
    for name, r in runs.items():
        c = r.counts()
        L.append(f"| {name} | {r.status} | {c['pass']} | {c['flag']} | {c['fail']} | {(r.reason or '').replace('|', '/')[:90]} |")
    L.append("")
    for name, r in runs.items():
        if r.status != "ran":
            continue
        bad = [x for x in r.results if x.status != "pass"]
        L.append(f"## {name}")
        if name == "corrections":
            for cid, v in r.summary.get("corrections", {}).items():
                L.append(f"- {cid}: {v['violations']} violation(s), {v['reviews']} review(s), "
                         f"cited fact carriers {', '.join(v['fact_carriers']) or 'none'}")
        if name == "occasions":
            d = r.summary["distribution"][r.params["unit"]]
            L.append(f"- unit `{r.params['unit']}`, minimum {r.params['min_occasions']}, layers {r.params['layers']}")
            for lay, hist in d.items():
                L.append(f"- {lay}: " + ", ".join(f"{k}:{v}" for k, v in hist.items()))
        if name == "integrity":
            s = r.summary
            L.append(f"- citations {s['citations']}, unresolved {s['unresolved']}, on exclude list {s['excluded']} "
                     f"({len(s['distinct_excluded'])} distinct); spans {s['spans']}; quotes {s['quotes']} "
                     f"(elided {s['quotes_elided']}, not found {s['quotes_not_found']})")
        if name == "time_split":
            L.append(f"- labels {r.summary['labels']} over {r.summary['contested']} contested claims; "
                     f"majority {r.params['majority']}, min gap {r.params['min_gap_days']} days")
        shown = bad[:12]
        for x in shown:
            L.append(f"- **{x.status}** {x.claim or ''} {x.reason[:220]}")
        if len(bad) > len(shown):
            L.append(f"- ... {len(bad) - len(shown)} more in the JSON report")
        L.append("")
    if comparison:
        L.append("## Against the back-check")
        oc = comparison.get("occasions")
        if oc:
            L += ["", "| unit | min | predictions flagged | support failures caught (predictions) | flagged, not failing | all layers caught |",
                  "|---|---|---|---|---|---|"]
            for t in oc["threshold_table"]:
                L.append(f"| {t['unit']} | {t['threshold']} | {t['predictions_flagged']} | "
                         f"{t['predictions_support_failures_caught']} of {t['predictions_support_failures']} | "
                         f"{t['predictions_flagged_not_failing']} | {t['all_support_failures_caught']} of {t['all_support_failures']} |")
            L.append("")
        ts = comparison.get("time_split")
        if ts:
            L.append("- time split vs the judge's contested verdict: " + "; ".join(f"{k}: {v}" for k, v in ts["confusion"].items()))
            L.append(f"- caveat: {ts['caveat']}")
    return "\n".join(L) + "\n"
