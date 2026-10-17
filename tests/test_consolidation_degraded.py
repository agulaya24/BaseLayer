"""A consolidation built on its package defaults says so, in its outputs, stamps and summary.

Without its model-built inputs (a trigger grouping and a category assignment), `baselayer
consolidate` falls back to identity triggers (one per distinct whole condition) and one flat
category, "Situations". On 10/6 (a second person's package run) that run printed "14/14 checks pass" and
nothing else: the checks verify structure, not content, so a fallback read as a pass. These tests
pin that the fallback is flagged in the outputs, the stamps and the printed summary, and that
supplied inputs reproducing the defaults are not flagged and give the same served text.

Synthetic specifications only; no model, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

from baselayer.consolidation import run as cons_run
from baselayer.consolidation import triggers as trig_mod
from baselayer.consolidation.common import read_json

CLAIMS = {
    "anchors": [
        {"id": "A1", "name": "PLAIN WORDS", "statement": "They write plainly.", "active_when": "Drafting any document.",
         "fact_ids": ["F-1", "F-2"], "contested": False},
        {"id": "A2", "name": "SHORT DRAFTS", "statement": "They keep drafts short.", "active_when": "Drafting any document.",
         "fact_ids": ["F-1", "F-2"], "contested": True},
    ],
    "core": [
        {"id": "C1", "name": "WEEKLY PLANS", "statement": "They plan by the week.", "active_when": "Planning work.",
         "fact_ids": ["F-3"], "contested": False},
        {"id": "C2", "name": "FEW TOOLS", "statement": "They use few tools.", "active_when": "Choosing tools.",
         "fact_ids": ["F-4"], "contested": False},
    ],
    "predictions": [
        {"id": "P1", "name": "ASKS FOR SOURCES", "statement": "They ask for a source.", "active_when": "A claim is made.",
         "fact_ids": ["F-5"], "contested": False},
        {"id": "P2", "name": "CUTS SCOPE", "statement": "They cut scope first.", "active_when": "Planning work.",
         "fact_ids": ["F-6"], "contested": False},
    ],
}


def _spec(d: Path, claims=CLAIMS) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for layer, cl in claims.items():
        (d / f"{layer}.json").write_text(json.dumps({"layer": layer, "claims": cl}), encoding="utf-8")
    return d


def _explicit_inputs(tmp: Path) -> list[str]:
    """A supplied grouping and category assignment: what the model builders would write."""
    d = tmp / "cons_inputs"
    d.mkdir(exist_ok=True)
    flat = [c for cl in CLAIMS.values() for c in cl]
    g = trig_mod.identity_grouping(flat, [])
    g["method"] = "synthetic test grouping"
    (d / "grouping.json").write_text(json.dumps(g), encoding="utf-8")
    cats = {"method": "synthetic test assignment",
            "categories": [{"id": "T1", "name": "Writing", "members": ["A1", "A2"]},
                           {"id": "T2", "name": "Planning", "members": ["C1", "C2", "P1", "P2"]}]}
    (d / "categories.json").write_text(json.dumps(cats), encoding="utf-8")
    return ["--grouping", str(d / "grouping.json"), "--categories", str(d / "categories.json")]


def _consolidate(tmp: Path, *, defaults: bool, capsys=None) -> tuple[Path, str]:
    spec = _spec(tmp / "spec", CLAIMS)
    out = tmp / "cons"
    argv = [str(spec), "--out", str(out)] + ([] if defaults else _explicit_inputs(tmp))
    assert cons_run.main(argv) == 0
    printed = capsys.readouterr().out if capsys else ""
    return out, printed


def _consolidate_supplied_defaults(tmp: Path, claims=CLAIMS) -> Path:
    """A consolidation built from SUPPLIED trigger and category inputs that reproduce the package
    defaults (identity triggers, one category "Situations"), so it is not degraded."""
    spec = _spec(tmp / "spec", claims)
    out = tmp / "cons"
    assert cons_run.main([str(spec), "--out", str(out), "--stages", "claims,overlap,dedupe,always_on"]) == 0
    ao = read_json(out / "always_on.json")["claims"]
    flat = [c for cl in claims.values() for c in cl]
    inp = tmp / "cons_inputs"
    inp.mkdir(exist_ok=True)
    (inp / "grouping.json").write_text(json.dumps({**trig_mod.identity_grouping(flat, ao),
                                                   "method": "supplied (test)"}), encoding="utf-8")
    (inp / "categories.json").write_text(json.dumps({"method": "supplied (test)", "categories": [
        {"id": "T1", "name": "Situations", "members": [c["id"] for c in flat]}]}), encoding="utf-8")
    assert cons_run.main([str(spec), "--out", str(out), "--stages", "triggers,categories,render,checks",
                          "--grouping", str(inp / "grouping.json"), "--categories", str(inp / "categories.json")]) == 0
    return out


# ---------------------------------------------------------------- consolidate flags it
def test_package_defaults_are_flagged_in_outputs_stamps_and_summary(tmp_path, capsys):
    out, printed = _consolidate(tmp_path, defaults=True, capsys=capsys)
    tr, cat = read_json(out / "triggers.json"), read_json(out / "categories.json")
    assert tr["fallback"] and "grouping" in tr["fallback"]
    assert cat["fallback"] and "categor" in cat["fallback"]
    assert tr["stamp"]["params"]["fallback"] is True and cat["stamp"]["params"]["fallback"] is True
    for name in ("index.json", "checks.json"):
        assert len(read_json(out / name)["degraded"]) == 2, name
    assert "DEGRADED" in printed and "14/14 checks pass" in printed
    assert "FAILED" not in printed                         # a flag, not a check failure: exit stays 0


def test_supplied_inputs_are_not_degraded(tmp_path, capsys):
    out, printed = _consolidate(tmp_path, defaults=False, capsys=capsys)
    assert read_json(out / "triggers.json")["fallback"] is None
    assert read_json(out / "categories.json")["fallback"] is None
    assert read_json(out / "index.json")["degraded"] == [] and read_json(out / "checks.json")["degraded"] == []
    assert "DEGRADED" not in printed


def test_the_served_text_stamp_carries_the_flag(tmp_path):
    """served.stamp.json is the stamp of consolidation's deliverable; reading only the served text
    and its stamp must not show a clean run."""
    out, _ = _consolidate(tmp_path, defaults=True)
    sst = read_json(out / "served.stamp.json")
    assert len(sst["degraded"]) == 2 and sst["params"]["degraded"] == sst["degraded"]
    clean, _ = _consolidate(tmp_path / "clean", defaults=False)
    sst = read_json(clean / "served.stamp.json")
    assert sst["degraded"] == [] and sst["params"]["degraded"] == []


def test_supplied_inputs_that_reproduce_the_defaults_give_the_same_served_text(tmp_path):
    """Supplied inputs that reproduce the defaults give the same served text as the defaults, and
    only the defaults are flagged."""
    deg, _ = _consolidate(tmp_path / "d", defaults=True)
    sup = _consolidate_supplied_defaults(tmp_path / "s")
    assert (deg / "served.txt").read_bytes() == (sup / "served.txt").read_bytes()
    assert len(read_json(deg / "index.json")["degraded"]) == 2
    assert read_json(sup / "index.json")["degraded"] == []
