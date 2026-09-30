"""Modular verification checks, each independently runnable, one result shape.

    name          module          needs                what it answers
    corrections   corrections.py  --corrections JSON   overturned statements returning (a)
    occasions     occasions.py    -                    claims resting on too few separate occasions (b)
    time_split    time_split.py   a side source        contested claims that are changes over time (c)
    integrity     integrity.py    -                    citations resolve, not excluded, spans and quotes found (d)
    backcheck     backcheck.py    --backcheck-results  the model-judged back-check, loaded, never run here (e)

Every check returns a base.CheckRun whose results are base.CheckResult rows
(check, claim, status pass|flag|fail, reason, evidence_ids, data). To add a check: write a module
with NAME, DESCRIPTION, NEEDS and run(ctx, **params), and register it in CHECKS below.
"""
from __future__ import annotations

from . import backcheck, corrections, integrity, occasions, time_split
from .base import CheckContext, CheckResult, CheckRun

CHECKS = {m.NAME: m for m in (corrections, occasions, time_split, integrity, backcheck)}
DEFAULT = tuple(CHECKS)


def missing_inputs(name: str, options: dict) -> list[str]:
    """The options a check needs that were not given. time_split's side source may come from
    the back-check results, so either satisfies it."""
    need = []
    for key in CHECKS[name].NEEDS:
        if key == "sides":
            if not (options.get("sides") or options.get("backcheck_results") or options.get("backcheck_driver")):
                need.append("a side source (--backcheck-results)")
        elif key == "backcheck":
            if not (options.get("backcheck_results") or options.get("backcheck_script") or options.get("backcheck_driver")):
                need.append("--backcheck-results")
        elif not options.get(key):
            need.append(f"--{key.replace('_', '-')}")
    return need


def run_checks(names, spec, corpus, options: dict | None = None, params: dict | None = None) -> tuple[dict, object]:
    """Run the named checks in registry order. Returns ({name: CheckRun}, loaded back-check data or
    None). An exception inside a check is recorded as status 'error', never swallowed into a pass."""
    options = dict(options or {})
    params = params or {}
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        raise ValueError(f"unknown checks: {unknown}; known: {list(CHECKS)}")
    drv = backcheck.driver_from_options(options)
    if drv is not None and ("backcheck" in names or "time_split" in names):
        data = drv.load()
        if data is not None:
            options["_backcheck_data"] = data
            if not options.get("sides"):
                options["sides"] = data.sides
                options["sides_source"] = f"back-check side labels ({data.source})"
    ctx = CheckContext(spec, corpus, options)
    out = {}
    for name in CHECKS:
        if name not in names:
            continue
        try:
            out[name] = CHECKS[name].run(ctx, **params.get(name, {}))
        except Exception as e:  # a check that cannot run is a failure, never a pass
            out[name] = CheckRun(name, "error", f"{type(e).__name__}: {e}", params.get(name, {}))
    return out, options.get("_backcheck_data")


__all__ = ["CHECKS", "DEFAULT", "CheckContext", "CheckResult", "CheckRun", "missing_inputs", "run_checks"]
