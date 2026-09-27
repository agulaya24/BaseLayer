"""
`baselayer run <file>` must import the file it was given, and must not spend on unchanged data.

WHY THIS EXISTS. `cmd_run` skipped import whenever ANY conversation was already in the
database ("N conversations already imported. Skipping import."), then ran estimate,
extraction and a full re-author (API spend) and printed "Done! Your specification is
ready" over a specification that excluded the file the user had just named. A second
`run` with a new journal silently did nothing with it and billed anyway.

The fix sends the named file through the importer's normal dedup path every time and
counts what actually arrived. If nothing new arrived and nothing is waiting for
extraction, `run` says so and stops before the estimate, unless `--reauthor` asks for a
regeneration.

A second hazard sat behind the blanket skip. Text and JSON conversation ids hash the path
AS TYPED, so `run notes.txt` and `run /abs/path/notes.txt` were different ids for the same
file. Once `run` stops skipping, that would re-import (and re-extract, and bill) the same
content on every change of spelling. The importer now also skips a file whose content is
already stored, so the test uses a differently spelled path on purpose: a test that reuses
the identical string would pass while the real case bills.

Isolation: config resolves paths at import time, so each step runs in a subprocess with
MEMORY_SYSTEM_ROOT pointed at a throwaway directory. The spending stages (estimate,
extract, author, traceability) are replaced by recorders, and ANTHROPIC_API_KEY is a
dummy, so any stage that escaped the stubs would fail loudly instead of billing.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

# Runs the real CLI with the four spending stages replaced by recorders. The extract
# recorder marks every conversation extracted, which is what the real stage leaves behind.
_WRAPPER = r"""
import json, os, sys
import baselayer.cli as cli

LOG = os.environ["BL_CALL_LOG"]

def _record(name):
    def f(*a, **k):
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(name + "\n")
    return f

def _fake_extract(args):
    _record("extract")()
    from baselayer.config import get_db
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO extraction_log SELECT id, 0, 0 FROM conversations")
    conn.commit()
    conn.close()

def _fake_batch_submit(*a, **k):
    # `baselayer pipeline` extracts through the batch API. Record, mark extracted, and
    # stop the process: reaching this point is the spend the test is about.
    _fake_extract(None)
    raise SystemExit(0)

import baselayer.batch_extract as _be
_be.run_submit = _fake_batch_submit

cli.cmd_estimate = _record("estimate")
cli.cmd_extract = _fake_extract
cli.cmd_author = _record("author")
cli._run_traceability = _record("traceability")
sys.argv = ["baselayer"] + json.loads(os.environ["BL_ARGV"])
cli.main()
"""


def _run(argv, root, cwd, log, extra_env=None):
    env = os.environ.copy()
    env.update(extra_env or {})
    env["MEMORY_SYSTEM_ROOT"] = str(root)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["ANTHROPIC_API_KEY"] = "sk-ant-dummy-not-a-real-key"
    env["BL_CALL_LOG"] = str(log)
    env["BL_ARGV"] = json.dumps(argv)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-c", _WRAPPER], env=env, cwd=str(cwd),
        capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
    )


def _calls(log):
    if not Path(log).exists():
        return []
    return Path(log).read_text(encoding="utf-8").split()


def _conversation_count(root):
    db = Path(root) / "data" / "database" / "memory.db"
    with sqlite3.connect(str(db)) as conn:
        return conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "first.txt").write_text(
        "I keep a running list of every decision I defer, and I revisit it each Sunday "
        "before planning the week ahead.\n", encoding="utf-8")
    (inputs / "second.txt").write_text(
        "When two options look equal I pick the one that is easier to undo, and I write "
        "down why so I can check the call later.\n", encoding="utf-8")
    log = tmp_path / "calls.log"
    r = _run(["init", "--accept-data-processing", "--name", "Test User"], root, tmp_path, log)
    assert r.returncode == 0, r.stdout + r.stderr
    return root, inputs, log, tmp_path


def _assert_ok(r):
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def test_first_run_imports_and_authors(workspace):
    root, inputs, log, _ = workspace
    r = _run(["run", "first.txt", "--yes"], root, inputs, log)
    _assert_ok(r)
    assert _conversation_count(root) == 1
    assert _calls(log) == ["estimate", "extract", "author", "traceability"]


def test_second_run_with_a_new_file_imports_it(workspace):
    root, inputs, log, _ = workspace
    _assert_ok(_run(["run", "first.txt", "--yes"], root, inputs, log))
    log.unlink()
    r = _run(["run", "second.txt", "--yes"], root, inputs, log)
    _assert_ok(r)
    assert "Skipping import" not in r.stdout
    assert _conversation_count(root) == 2, r.stdout
    assert _calls(log) == ["estimate", "extract", "author", "traceability"]


def test_unchanged_file_does_not_trigger_authoring_spend(workspace):
    root, inputs, log, _ = workspace
    _assert_ok(_run(["run", "first.txt", "--yes"], root, inputs, log))
    log.unlink()
    r = _run(["run", "first.txt", "--yes"], root, inputs, log)
    _assert_ok(r)
    assert _conversation_count(root) == 1
    assert _calls(log) == [], r.stdout
    assert "nothing new" in r.stdout.lower()
    assert "Done!" not in r.stdout


def test_unchanged_file_under_a_different_path_spelling_does_not_reimport(workspace):
    root, inputs, log, tmp = workspace
    _assert_ok(_run(["run", "first.txt", "--yes"], root, inputs, log))
    log.unlink()
    # Same file, spelled from a different working directory.
    r = _run(["run", str(Path("inputs") / "first.txt"), "--yes"], root, tmp, log)
    _assert_ok(r)
    assert _conversation_count(root) == 1, r.stdout
    assert _calls(log) == [], r.stdout


def test_reauthor_regenerates_when_nothing_is_new(workspace):
    root, inputs, log, _ = workspace
    _assert_ok(_run(["run", "first.txt", "--yes"], root, inputs, log))
    log.unlink()
    r = _run(["run", "first.txt", "--yes", "--reauthor"], root, inputs, log)
    _assert_ok(r)
    assert "author" in _calls(log)


def test_rerun_after_cancel_continues_with_unextracted_data(workspace):
    """A run cancelled at the cost prompt leaves data imported and unextracted.
    Running it again must carry on with that data, not stop as 'nothing new'."""
    root, inputs, log, _ = workspace
    # stdin closed and no --yes: the confirm prompt reads EOF and cancels.
    r = _run(["run", "first.txt"], root, inputs, log)
    _assert_ok(r)
    assert _calls(log) == ["estimate"]
    log.unlink()
    r = _run(["run", "first.txt", "--yes"], root, inputs, log)
    _assert_ok(r)
    assert _calls(log) == ["estimate", "extract", "author", "traceability"]


def test_completion_message_does_not_point_at_archived_chat(workspace):
    root, inputs, log, _ = workspace
    # Give the done-branch a brief to print so its "Next steps" block renders.
    brief = root / "data" / "identity_layers" / "brief_v5_clean.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("## Injectable Block\n\nA short brief.\n", encoding="utf-8")
    r = _run(["run", "first.txt", "--yes"], root, inputs, log)
    _assert_ok(r)
    assert "Done!" in r.stdout
    assert "baselayer chat" not in r.stdout


# ---------------------------------------------------------------------------
# `baselayer pipeline <subject_id>` had the same blanket skip (outside --v2).
# ---------------------------------------------------------------------------

def test_pipeline_imports_new_source_files_and_stops_on_unchanged(tmp_path):
    main_root = tmp_path / "main"
    main_root.mkdir()
    anth = tmp_path / "anth"
    (anth / "subjects" / "test_env").mkdir(parents=True)
    source = anth / "memory_system" / "data" / "test_source"
    source.mkdir(parents=True)
    (source / "a.txt").write_text(
        "The committee minutes record that the proposal was deferred twice before it "
        "was finally adopted with amendments.\n", encoding="utf-8")
    log = tmp_path / "calls.log"
    env = {"BASELAYER_ROOT": str(anth)}
    _assert_ok(_run(["init", "--accept-data-processing", "--name", "Test User"],
                    main_root, tmp_path, log, env))
    with sqlite3.connect(str(main_root / "data" / "database" / "memory.db")) as conn:
        conn.execute(
            "INSERT INTO subjects (id, name, environment_dir, source_dir, document_mode, version)"
            " VALUES ('test_subject', 'Test Subject', 'test_env', 'test_source', 1, 'V1')")
    subj_root = anth / "subjects" / "test_env"

    r = _run(["pipeline", "test_subject", "--yes"], main_root, tmp_path, log, env)
    _assert_ok(r)
    assert _conversation_count(subj_root) == 1, r.stdout
    assert _calls(log) == ["extract"], r.stdout

    log.unlink()
    r = _run(["pipeline", "test_subject", "--yes"], main_root, tmp_path, log, env)
    _assert_ok(r)
    assert _calls(log) == [], r.stdout
    assert "nothing new" in r.stdout.lower()

    (source / "b.txt").write_text(
        "A later entry notes that the amended proposal was reviewed after six months and "
        "kept without further change.\n", encoding="utf-8")
    r = _run(["pipeline", "test_subject", "--yes"], main_root, tmp_path, log, env)
    _assert_ok(r)
    assert _conversation_count(subj_root) == 2, r.stdout
    assert _calls(log) == ["extract"], r.stdout
