"""Acceptance: reproduce a served text byte for byte from an authored spec plus its hand inputs.

Runs only when BASELAYER_CONSOLIDATION_ACCEPTANCE names a JSON file:

    {"spec_dir": "...", "grouping": "...", "categories": "...", "subject": "...", "possessive": "...",
     "expected_sha256": "<sha256 of the served text, UTF-8, LF>",
     "expected_trigger_categories": "<optional: a prototype trigger index whose categories must be recomputed>"}

The real inputs are one person's specification and stay outside this repository, so the
test carries no path and no content of its own. No model is called.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from baselayer.consolidation import run as crun
from baselayer.consolidation.common import read_json, sha256_bytes

CFG = os.environ.get("BASELAYER_CONSOLIDATION_ACCEPTANCE")


@pytest.mark.skipif(not CFG, reason="BASELAYER_CONSOLIDATION_ACCEPTANCE not set (real inputs live outside the repo)")
def test_reproduces_served_text(tmp_path):
    import argparse
    cfg = json.loads(Path(CFG).read_text(encoding="utf-8"))
    out = tmp_path / "out"
    args = crun.build_parser(argparse.ArgumentParser()).parse_args(
        [cfg["spec_dir"], "--out", str(out), "--grouping", cfg["grouping"], "--categories", cfg["categories"],
         "--subject", cfg["subject"], "--possessive", cfg.get("possessive", "their")])
    assert crun.execute(args) == 0
    assert read_json(out / "checks.json")["passed"]
    assert sha256_bytes((out / "served.txt").read_bytes()) == cfg["expected_sha256"]
    if cfg.get("expected_trigger_categories"):
        ti = read_json(cfg["expected_trigger_categories"])
        tr = read_json(out / "triggers.json")["triggers"]
        tc = read_json(out / "categories.json")["trigger_category"]
        mine = {t["key"]: tc[t["id"]] for t in tr}
        assert {t["key"]: t["category"] for t in ti["triggers"]} == mine
