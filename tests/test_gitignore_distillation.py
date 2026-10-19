"""In a clone of this repository the data root is the clone itself, so `distill` archives trees
(which carry the person's own words) under data/distillation/. That directory must not be
stageable. Checked with `git add --dry-run --ignore-missing`, which asks whether a path would be
staged, not whether some ignore pattern matches it. Skipped outside a git work tree.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _would_stage(rel):
    r = subprocess.run(["git", "add", "--dry-run", "--ignore-missing", rel], cwd=ROOT,
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture(autouse=True)
def _in_git():
    if not shutil.which("git") or subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                                 cwd=ROOT, capture_output=True).returncode != 0:
        pytest.skip("not a git work tree")


@pytest.mark.parametrize("rel", ["data/distillation/anchors_0123abcd.json",
                                 "data/distillation/distill_runs.jsonl",
                                 "data/distillation/LATEST_core.json"])
def test_distillation_archive_is_ignored(rel):
    rc, out = _would_stage(rel)
    assert rc == 1 and "ignored" in out, out


def test_control_a_tracked_style_path_is_not_reported_ignored():
    rc, out = _would_stage("docs/probe_not_ignored.md")
    assert rc == 0 and "ignored" not in out, out
