"""`python -m baselayer.batch_extract` flag routing.

`--process --resume` must resume. A plain --process first deletes every extracted fact and the
whole extraction log; on a non-incremental batch that reset runs, so the flag the user typed to
AVOID the reset caused it. The `baselayer batch-extract --process --resume` CLI form already
resumes; this pins the module's own main() to the same reading.
"""
import sys

import pytest

from baselayer import batch_extract as be


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(be, "run_process", lambda resume=False: seen.append(("process", resume)))
    monkeypatch.setattr(be, "run_submit", lambda **k: seen.append(("submit", k)))
    monkeypatch.setattr(be, "run_status", lambda: seen.append(("status",)))
    return seen


@pytest.mark.parametrize("argv, want", [
    (["--process", "--resume"], [("process", True)]),
    (["--resume", "--process"], [("process", True)]),
    (["--resume"], [("process", True)]),
    (["--process"], [("process", False)]),
])
def test_process_flags_route_to_the_right_mode(monkeypatch, calls, argv, want):
    monkeypatch.setattr(sys, "argv", ["batch_extract", *argv])
    be.main()
    assert calls == want
