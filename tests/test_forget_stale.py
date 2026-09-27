"""
`baselayer forget` must say what it does not do, and must mark the specification stale.

WHY THIS EXISTS. `forget` soft-deletes facts (superseded_by = 'user_forget') and removes
their vectors. It does not touch the raw conversation text they came from, and it does not
touch the authored layers, brief or claim provenance. So the MCP server kept serving
claims built from facts the user had just asked to forget, with nothing anywhere saying
so, while the help text read "Delete a specific fact".

The fix: help and output say "hide (soft-delete)", say that raw text stays and that
specifications are not regenerated; a successful forget writes a marker recording when it
ran; any specification file older than that marker is reported stale by `stats`, by the
MCP server's log, and inside the served specification text. Staleness is computed from
file times, so regenerating the layers through any entry point clears it with no cleanup
step to forget.

The planted fact below appears verbatim in a served claim, which is the case that matters:
after `forget`, the served text still carries it (the layers were not regenerated) and now
says so.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
PLANTED = "Keeps a spare house key under the blue planter by the back door"
MARKER_NAME = "stale_after_forget.json"


def run_cli(cli_args, root):
    env = os.environ.copy()
    env["MEMORY_SYSTEM_ROOT"] = str(root)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("ANTHROPIC_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "baselayer.cli", *cli_args], env=env,
        capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
    )


def _layers_dir(root):
    return Path(root) / "data" / "identity_layers"


def _write_layers(root, mtime):
    d = _layers_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    for name in ("anchors_v4.md", "core_v4.md", "predictions_v4.md"):
        f = d / name
        f.write_text(f"## Injectable Block\n\nC1. {PLANTED}.\n", encoding="utf-8")
        os.utime(f, (mtime, mtime))


@pytest.fixture
def root_with_fact(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    r = run_cli(["init", "--accept-data-processing", "--name", "Test User"], root)
    assert r.returncode == 0, r.stdout + r.stderr
    db = root / "data" / "database" / "memory.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("INSERT INTO conversations (id, title, created_at, updated_at,"
                     " message_count, source) VALUES ('c1', 't', 0, 0, 1, 'text_file')")
        conn.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id,"
                     " created_at, updated_at) VALUES ('f-planted', ?, 'biography', 'c1', 0, 0)",
                     (PLANTED,))
    _write_layers(root, time.time() - 3600)
    return root


def test_help_says_hide_not_delete_and_names_what_stays(tmp_path):
    r = run_cli(["forget", "--help"], tmp_path)
    text = " ".join(r.stdout.lower().split())
    assert "hide" in text
    assert "raw conversation text" in text
    assert "not regenerated" in text
    assert "delete a specific fact" not in text


def test_forget_marks_specification_stale_and_says_so(root_with_fact):
    root = root_with_fact
    r = run_cli(["forget", "--fact", "f-planted"], root)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout.lower()
    assert "raw conversation text" in out
    assert "stale" in out and "baselayer author --compose" in out
    marker = _layers_dir(root) / MARKER_NAME
    assert marker.exists()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["facts_forgotten"] == 1
    assert data["forgotten_at"] > 0

    s = run_cli(["stats"], root)
    assert "stale" in s.stdout.lower(), s.stdout


def test_regenerating_the_layers_clears_the_warning(root_with_fact):
    root = root_with_fact
    assert run_cli(["forget", "--fact", "f-planted"], root).returncode == 0
    assert "stale" in run_cli(["stats"], root).stdout.lower()
    _write_layers(root, time.time() + 5)  # as if `baselayer author` had just run
    assert "stale" not in run_cli(["stats"], root).stdout.lower()


def test_forget_of_an_unknown_fact_writes_no_marker(root_with_fact):
    root = root_with_fact
    r = run_cli(["forget", "--fact", "no-such-fact"], root)
    assert r.returncode == 0
    assert not (_layers_dir(root) / MARKER_NAME).exists()
    assert "stale" not in run_cli(["stats"], root).stdout.lower()


def test_mcp_served_text_carries_the_stale_notice(tmp_path):
    import baselayer.mcp_server as mcp_server
    _write_layers(tmp_path, time.time() - 3600)
    d = _layers_dir(tmp_path)
    marker = d / MARKER_NAME
    patches = [
        patch.object(mcp_server, "ANCHORS_LAYER_FILE", d / "anchors_v4.md"),
        patch.object(mcp_server, "CORE_LAYER_FILE", d / "core_v4.md"),
        patch.object(mcp_server, "PREDICTIONS_LAYER_FILE", d / "predictions_v4.md"),
        patch.object(mcp_server, "UNIFIED_BRIEF_FILE", d / "brief_v5_clean.md"),
        patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", d / "brief_v5.md"),
    ]
    for p in patches:
        p.start()
    try:
        text = mcp_server._build_specification_text()
        assert PLANTED in text
        assert "forget" not in text.lower()

        marker.write_text(json.dumps({"forgotten_at": time.time(), "facts_forgotten": 1}),
                          encoding="utf-8")
        text = mcp_server._build_specification_text()
        assert PLANTED in text  # not regenerated, so the claim is still there ...
        assert "stale" in text.lower()  # ... and the served text now says so
        # The notice must sit early: the instructions field is cut at ~2,048 characters.
        assert text.lower().index("stale") < 2048

        _write_layers(tmp_path, time.time() + 5)
        assert "stale" not in mcp_server._build_specification_text().lower()
    finally:
        for p in patches:
            p.stop()


def test_forget_count_restarts_after_regeneration(tmp_path):
    """forget(10) -> regenerate -> forget(1) must report 1 fact hidden since the files
    were written, not 11."""
    from baselayer.spec_staleness import record_forget, read_marker
    d = tmp_path / "layers"
    d.mkdir()
    files = [d / "core_v4.md"]
    files[0].write_text("x", encoding="utf-8")
    os.utime(files[0], (1000, 1000))
    record_forget(d, 10, "all", now=2000, files=files)
    assert read_marker(d)["facts_forgotten"] == 10
    record_forget(d, 2, "fact", now=2500, files=files)  # still unaddressed: accumulates
    assert read_marker(d)["facts_forgotten"] == 12
    os.utime(files[0], (3000, 3000))  # regenerated
    record_forget(d, 1, "fact", now=4000, files=files)
    assert read_marker(d)["facts_forgotten"] == 1
