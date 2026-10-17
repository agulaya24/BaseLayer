"""(e) The model-judged back-check, as a slot.

verify-spec never calls a model from this slot. A back-check is an EXTERNAL step: a driver knows
how to build the command that runs it (for a person to run, on the subscription, blind by the
method's own probe) and how to load its results once they are on disk. Loading costs nothing,
and the loaded results feed two things here:
  - the `backcheck` check: per claim, the judge's verdict as a result in the common shape
    (support failure -> fail; scope-only failure or a failed contested flag -> flag);
  - a side source for `time_split` (the judge assigns each cited fact of a contested claim to a side).

The interface is BackcheckDriver. Judge162External wires the 2026-09-29 method
(an external `judge162.py` script): `command()` returns its `run` invocation, `load()`
reads `runs/<id>/judgements.jsonl` and, when present, the aggregated `verdicts.json`.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .base import CheckContext, CheckResult, CheckRun

NAME = "backcheck"
DESCRIPTION = "model-judged claim back-check, loaded from an external run (never run here)"
NEEDS = ("backcheck",)


@dataclass
class BackcheckData:
    source: str
    claims: dict = field(default_factory=dict)       # claim id -> verdict row
    sides: dict = field(default_factory=dict)        # claim id -> {fact id: "1"|"2"}
    origins: dict = field(default_factory=dict)      # claim id -> {fact id: origin}
    models: dict = field(default_factory=dict)       # model -> calls


class BackcheckDriver:
    """A model-judged back-check that runs outside verify-spec."""
    name = "abstract"

    def command(self) -> list[str] | None:
        """The command that runs the back-check. Returned for a person to run; never executed here."""
        raise NotImplementedError

    def load(self) -> BackcheckData | None:
        """Results already on disk, or None when there are none yet."""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"driver": self.name, "command": self.command()}


class Judge162External(BackcheckDriver):
    """An external `judge162.py` script: one judge call per claim, claude --safe-mode -p."""
    name = "judge162"

    def __init__(self, results: Path | None = None, script: Path | None = None, run_id: str = "full_1"):
        self.results = Path(results) if results else None
        self.script = Path(script) if script else None
        self.run_id = run_id
        if self.results and self.results.is_dir() and (self.results / "judgements.jsonl").exists():
            # given the run directory itself: <root>/runs/<id>
            self.run_dir = self.results
            self.root = self.results.parent.parent
            self.run_id = self.results.name
        elif self.results and self.results.is_dir():
            self.root = self.results
            self.run_dir = self.results / "runs" / run_id
        elif self.results:   # a verdicts.json file
            self.root = self.results.parent
            self.run_dir = self.root / "runs" / run_id
        else:
            self.root = self.script.parent if self.script else None
            self.run_dir = self.root / "runs" / run_id if self.root else None

    def command(self) -> list[str] | None:
        script = self.script or (self.root / "judge162.py" if self.root else None)
        if not script:
            return None
        return [sys.executable, str(script), "run", "--run-id", self.run_id]

    def load(self) -> BackcheckData | None:
        jl = self.run_dir / "judgements.jsonl" if self.run_dir else None
        vj = (self.results if self.results and self.results.is_file() else
              (self.root / "verdicts.json" if self.root else None))
        if not (jl and jl.exists()) and not (vj and vj.exists()):
            return None
        data = BackcheckData(source=str(jl if jl and jl.exists() else vj))
        if jl and jl.exists():
            for line in jl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("kind") != "main":        # plants and retests are the instrument's, not the spec's
                    continue
                cid, j = r["qid"], r.get("judgement") or {}
                data.models[r.get("model")] = data.models.get(r.get("model"), 0) + 1
                facts = j.get("facts") or []
                data.sides[cid] = {f["id"]: str(f["side"]) for f in facts if str(f.get("side")) in ("1", "2")}
                data.origins[cid] = {f["id"]: f.get("origin") for f in facts}
                con = j.get("contested") or {}
                data.claims.setdefault(cid, {}).update(
                    {"verdict": j.get("verdict"), "scope": (j.get("scope") or {}).get("verdict"),
                     "missing": j.get("missing"), "contested_verdict": con.get("verdict"),
                     "contested_reason": con.get("reason")})
        if vj and vj.exists():
            for row in json.loads(vj.read_text(encoding="utf-8")):
                data.claims.setdefault(row["id"], {}).update(
                    {k: row.get(k) for k in ("verdict", "scope", "fails_support", "fails_scope", "claim_fails",
                                             "missing", "contested_verdict", "contested_flag_fails", "not_his_facts")})
        return data


def driver_from_options(options: dict) -> BackcheckDriver | None:
    if options.get("backcheck_driver"):
        return options["backcheck_driver"]
    res, script = options.get("backcheck_results"), options.get("backcheck_script")
    if not res and not script:
        return None
    return Judge162External(results=Path(res) if res else None, script=Path(script) if script else None)


def run(ctx: CheckContext) -> CheckRun:
    drv = driver_from_options(ctx.options)
    if drv is None:
        return CheckRun(NAME, "not_run", "no back-check driver or results given (--backcheck-results)")
    params = drv.describe()
    data = ctx.options.get("_backcheck_data") or drv.load()
    if data is None:
        return CheckRun(NAME, "not_run", "no back-check results on disk yet; run the external step: "
                        + " ".join(params["command"] or ["<no command>"]), params)
    params["source"] = data.source
    results = []
    for cl in ctx.spec.claims:
        row = data.claims.get(cl.id)
        if not row:
            results.append(CheckResult(NAME, cl.qid, "flag", "the back-check has no verdict for this claim"))
            continue
        fails_support = row.get("fails_support")
        if fails_support is None:
            fails_support = row.get("verdict") in ("overreaches", "unsupported")
        fails_scope = row.get("fails_scope")
        if fails_scope is None:
            fails_scope = row.get("scope") == "overgeneralises"
        not_his = [f for f, o in (data.origins.get(cl.id) or {}).items() if o == "not_his_assertion"]
        if fails_support:
            st = "fail"
        elif fails_scope or row.get("contested_flag_fails"):
            st = "flag"
        else:
            st = "pass"
        bits = [f"verdict {row.get('verdict')}", f"scope {row.get('scope')}"]
        if row.get("contested_verdict"):
            bits.append(f"contested {row['contested_verdict']}")
        if row.get("missing") and st != "pass":
            bits.append(f"missing: {row['missing']}")
        results.append(CheckResult(NAME, cl.qid, st, "; ".join(bits), not_his,
                                   {k: row.get(k) for k in ("verdict", "scope", "contested_verdict")}))
    summary = {"models": data.models, "claims_with_verdict": sum(1 for c in ctx.spec.claims if c.id in data.claims)}
    return CheckRun(NAME, "ran", "", params, results, summary)
