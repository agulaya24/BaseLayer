"""`distill --layer` omitted: the run still uses `blind` (the default value is unchanged), but it
now says so on stderr, because `blind` is the undirected control arm and its tree is not a layer.
An explicit `--layer blind` prints no warning. No API calls: fake client only.
"""
import json
import sys
import pytest

from baselayer import cli
from baselayer.distillation import distill
from tests.test_artifact_stamps import FACTS, DistillClient, _make_db, no_network  # noqa: F401


def _argv(db, out, *extra):
    return ["distill.py", "--db", str(db), "--out", str(out), "--model", "claude-haiku-4-5",
            "--max-facts", "2", *extra]


def test_omitted_layer_runs_blind_and_warns(no_network, monkeypatch, tmp_path, capsys):
    db = _make_db(tmp_path / "c", FACTS)
    out = tmp_path / "t.json"
    monkeypatch.setattr(sys, "argv", _argv(db, out))
    distill.main()
    err = capsys.readouterr().err
    assert "--layer not given" in err and "control" in err
    assert json.load(open(out, encoding="utf-8"))["stamp"]["layer"] == "blind"


def test_explicit_blind_does_not_warn(no_network, monkeypatch, tmp_path, capsys):
    db = _make_db(tmp_path / "c", FACTS)
    monkeypatch.setattr(sys, "argv", _argv(db, tmp_path / "t.json", "--layer", "blind"))
    distill.main()
    assert "--layer not given" not in capsys.readouterr().err


def test_explicit_layer_does_not_warn(no_network, monkeypatch, tmp_path, capsys):
    db = _make_db(tmp_path / "c", FACTS)
    out = tmp_path / "t.json"
    monkeypatch.setattr(sys, "argv", _argv(db, out, "--layer", "anchors"))
    distill.main()
    assert "--layer not given" not in capsys.readouterr().err
    assert json.load(open(out, encoding="utf-8"))["stamp"]["layer"] == "anchors"


def _cli_argv(monkeypatch, *args):
    seen = {}
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr(distill, "main", lambda: seen.setdefault("argv", list(sys.argv)))
    monkeypatch.setattr(sys, "argv", ["baselayer", "distill", "--out", "t.json", *args])
    cli.main()
    return seen["argv"]


def test_cli_forwards_layer_only_when_given(monkeypatch):
    argv = _cli_argv(monkeypatch)
    assert "--layer" not in argv            # so the module can tell the default applied
    argv = _cli_argv(monkeypatch, "--layer", "core")
    assert argv[argv.index("--layer") + 1] == "core"


def test_cli_help_states_the_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["baselayer", "distill", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    h = " ".join(capsys.readouterr().out.split())
    assert "blind" in h and "control" in h and "Always pass it" in h
