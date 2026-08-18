"""
First-run behaviour: the import-before-init trap and cancelled-init exit codes.

Both defects were found by RUNNING the pipeline as a first-time user:

1. `baselayer import` against an uninitialised root died with
   `sqlite3.OperationalError: no such table: conversations` AND left a
   zero-table memory.db behind (sqlite3.connect creates the file before the
   first query). `baselayer init` then saw the file, printed "Database already
   exists" and exited having created nothing. Import would not run, init would
   not run, and nothing said `--force`.

2. `baselayer init` with stdin closed (CI, piped invocation) printed
   "Setup cancelled" and exited 0 with zero tables created, so automation read
   success and every later stage failed for unrelated-looking reasons.

These tests run the real CLI in a subprocess with MEMORY_SYSTEM_ROOT pointed at
a throwaway directory, because config.py resolves paths at import time. The
subprocess env pins PYTHONPATH to this checkout's src/ so the editable install
of another checkout can never be what gets tested.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def run_cli(cli_args, root, stdin_text=None):
    """Run `python -m baselayer.cli <args>` against an isolated data root."""
    env = os.environ.copy()
    env["MEMORY_SYSTEM_ROOT"] = str(root)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    kwargs = dict(capture_output=True, text=True, env=env, timeout=120)
    if stdin_text is None:
        kwargs["stdin"] = subprocess.DEVNULL  # no terminal: the CI/piped case
    else:
        kwargs["input"] = stdin_text
    return subprocess.run(
        [sys.executable, "-m", "baselayer.cli", *cli_args], **kwargs
    )


def db_file(root):
    return Path(root) / "data" / "database" / "memory.db"


def table_names(path):
    with sqlite3.connect(str(path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {r[0] for r in rows}


@pytest.fixture
def sample_txt(tmp_path):
    f = tmp_path / "sample.txt"
    # The text importer silently skips files under 50 characters; stay above it.
    f.write_text(
        "I enjoy hiking in the mountains and reading long novels on rainy "
        "weekend afternoons.\n",
        encoding="utf-8",
    )
    return f


# ---------------------------------------------------------------------------
# Defect 1: import before init
# ---------------------------------------------------------------------------

class TestImportBeforeInit:
    def test_import_names_the_exact_command_instead_of_crashing(
        self, tmp_path, sample_txt
    ):
        root = tmp_path / "root"
        root.mkdir()
        result = run_cli(["import", str(sample_txt), "--source", "text"], root)

        assert result.returncode != 0
        assert "baselayer init" in result.stdout, (
            f"import against an uninitialised root must name the command to "
            f"run.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "Traceback" not in result.stderr, (
            f"import must fail cleanly, not with a traceback:\n{result.stderr}"
        )

    def test_failed_import_leaves_no_orphan_database_file(
        self, tmp_path, sample_txt
    ):
        # The orphan file is what made init refuse afterwards. The guard must
        # run before the first connect, which is what creates the file.
        root = tmp_path / "root"
        (root / "data" / "database").mkdir(parents=True)
        run_cli(["import", str(sample_txt), "--source", "text"], root)
        assert not db_file(root).exists(), (
            "a failed import must not leave a zero-table memory.db behind"
        )

    def test_init_treats_zero_table_database_as_uninitialised(self, tmp_path):
        # The trap state as older code left it: file exists, zero tables.
        root = tmp_path / "root"
        (root / "data" / "database").mkdir(parents=True)
        sqlite3.connect(str(db_file(root))).close()
        assert table_names(db_file(root)) == set()

        result = run_cli(["init"], root, stdin_text="Y\nTester\n3\n")
        assert result.returncode == 0, (
            f"init must recover a zero-table database without --force.\n"
            f"stdout:\n{result.stdout}"
        )
        assert "conversations" in table_names(db_file(root))
        assert "already exists" not in result.stdout

    def test_init_still_refuses_over_an_initialised_database(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        first = run_cli(["init"], root, stdin_text="Y\nTester\n3\n")
        assert first.returncode == 0
        second = run_cli(["init"], root, stdin_text="Y\nTester\n3\n")
        assert "already exists" in second.stdout
        assert "--force" in second.stdout

    def test_first_run_sequence_recovers_without_guessing(
        self, tmp_path, sample_txt
    ):
        # The exact user journey: import fails and names init; init runs; the
        # same import command then succeeds. No --force, no guessing.
        root = tmp_path / "root"
        root.mkdir()
        failed = run_cli(["import", str(sample_txt), "--source", "text"], root)
        assert failed.returncode != 0
        assert "baselayer init" in failed.stdout

        init = run_cli(["init"], root, stdin_text="Y\nTester\n3\n")
        assert init.returncode == 0, init.stdout

        retried = run_cli(["import", str(sample_txt), "--source", "text"], root)
        assert retried.returncode == 0, (
            f"stdout:\n{retried.stdout}\nstderr:\n{retried.stderr}"
        )
        assert "1 new conversations added" in retried.stdout


# ---------------------------------------------------------------------------
# Defect 2: cancelled init exits 0
# ---------------------------------------------------------------------------

class TestInitCancellation:
    def test_stdin_closed_exits_nonzero_and_points_at_the_flag(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        result = run_cli(["init"], root)  # stdin closed
        assert result.returncode != 0, (
            "a cancelled init must not exit 0: automation reads that as "
            "success and gets an empty database"
        )
        assert "--accept-data-processing" in result.stdout
        assert not db_file(root).exists() or "conversations" not in table_names(
            db_file(root)
        )

    def test_declined_consent_exits_nonzero(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        result = run_cli(["init"], root, stdin_text="n\n")
        assert result.returncode != 0
        assert "cancelled" in result.stdout.lower()

    def test_noninteractive_init_records_explicit_consent(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        result = run_cli(
            [
                "init",
                "--accept-data-processing",
                "--name", "Test User",
                "--pronouns", "she/her",
            ],
            root,  # stdin closed: must complete with no terminal at all
        )
        assert result.returncode == 0, (
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "conversations" in table_names(db_file(root))

        # Consent is a privacy disclosure: the non-interactive path must
        # record the acknowledgement explicitly, not silently default it.
        entity_map = json.loads(
            (root / "data" / "entity_map.json").read_text(encoding="utf-8")
        )
        consent = entity_map["_data_processing_consent"]
        assert consent["acknowledged"] is True
        assert "accept-data-processing" in consent["via"]
        assert consent["at"]
        assert entity_map["_user_names"] == ["Test User"]
        assert entity_map["_user_pronouns"] == "she/her"

    def test_interactive_init_also_records_consent(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        result = run_cli(["init"], root, stdin_text="Y\nTester\n3\n")
        assert result.returncode == 0
        entity_map = json.loads(
            (root / "data" / "entity_map.json").read_text(encoding="utf-8")
        )
        consent = entity_map["_data_processing_consent"]
        assert consent["acknowledged"] is True
        assert consent["via"] == "interactive prompt"
