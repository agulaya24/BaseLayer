"""`distill --out` (or `--checkpoint`) in a directory that does not exist is refused before facts
load and before any client exists. The tree is written only after every billed leaf call, so the
directory used to be found missing after the money was spent. No API calls: fake client only.
"""
import json
import sys
import pytest

from baselayer.distillation import distill
from tests.test_artifact_stamps import FACTS, DistillClient, _make_db, no_network  # noqa: F401


def _argv(db, out, *extra):
    return ["distill.py", "--db", str(db), "--out", str(out), "--model", "claude-haiku-4-5",
            "--max-facts", "2", *extra]


def test_missing_out_directory_is_refused_before_any_call(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    out = tmp_path / "no_such_dir" / "t.json"
    monkeypatch.setattr(sys, "argv", _argv(db, out, "--layer", "anchors"))
    with pytest.raises(SystemExit, match="does not exist"):
        distill.main()
    assert DistillClient.calls == []
    assert not out.parent.exists()          # refused, not created


def test_missing_checkpoint_directory_is_refused_before_any_call(no_network, monkeypatch,
                                                                 tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    monkeypatch.setattr(sys, "argv", _argv(db, tmp_path / "t.json", "--layer", "anchors",
                                           "--checkpoint", str(tmp_path / "nope" / "ck.json")))
    with pytest.raises(SystemExit, match="--checkpoint"):
        distill.main()
    assert DistillClient.calls == []


def test_bare_filename_out_means_the_current_directory(no_network, monkeypatch, tmp_path):
    # no_network chdirs into tmp_path; a bare name has an empty dirname and must not be refused
    db = _make_db(tmp_path / "c", FACTS)
    monkeypatch.setattr(sys, "argv", _argv(db, "t.json", "--layer", "anchors"))
    distill.main()
    assert (tmp_path / "t.json").exists()



def test_cli_help_says_the_out_directory_must_exist(monkeypatch, capsys):
    from baselayer import cli
    monkeypatch.setattr(sys, "argv", ["baselayer", "distill", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "must already exist" in " ".join(capsys.readouterr().out.split())
