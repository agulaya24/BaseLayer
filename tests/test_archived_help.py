"""The archived `brief` and `chat` commands' help no longer describes the brief as the "current V4
unified brief" or refers to a "4-step pipeline": the three layers are the specification and the
brief is optional. No model calls.
"""
import sys

import pytest

from baselayer import cli


def test_archived_commands_help_is_current(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["baselayer", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    out = " ".join(capsys.readouterr().out.split())
    assert "[ARCHIVED]" in out
    assert "V4 unified brief" not in out
    assert "4-step pipeline" not in out
    assert "optional prose brief" in out
