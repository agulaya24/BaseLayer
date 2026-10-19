"""`verify-spec --rater cli` passes --safe-mode to the `claude -p` child when the installed CLI
lists it, and runs without it (with a warning and a provenance record) when it does not.

--safe-mode drops the user-scope ~/.claude/CLAUDE.md, which otherwise loads into every child and
can name the subject. Blindness still needs a clean context probe either way. No model calls and
no real CLI: the --help call is faked.
"""
import subprocess
from types import SimpleNamespace as NS

from baselayer.verification import raters


def _fake_help(text, seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.append(list(cmd))
        return NS(stdout=text, stderr="", returncode=0)
    return run


def _rater(tmp_path, **kw):
    cwd = tmp_path / "neutral"
    cwd.mkdir(exist_ok=True)
    return raters.ClaudeCliRater("sonnet", cwd, tmp_path / "work", [tmp_path / "corpus"],
                                 binary="claude-test-binary", **kw)


def test_detects_support_and_passes_the_flag(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(raters.subprocess, "run", _fake_help("  --safe-mode   Start with ...", seen))
    r = _rater(tmp_path)
    assert seen == [["claude-test-binary", "--help"]]       # detection is the free --help call
    assert "--safe-mode" in r.command()
    pv = r.provenance()
    assert pv["safe_mode"] is True and pv["user_scope_instructions"] == "--safe-mode"
    assert pv["blind"] is False                              # safe mode alone is not blindness
    assert "WARNING" not in capsys.readouterr().err


def test_without_support_runs_without_the_flag_and_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(raters.subprocess, "run", _fake_help("Usage: claude [options]"))
    r = _rater(tmp_path)
    assert "--safe-mode" not in r.command()
    err = capsys.readouterr().err
    assert "does not list --safe-mode" in err and "CLAUDE.md" in err
    pv = r.provenance()
    assert pv["safe_mode"] is False and pv["blind_channel"] == raters.USER_SCOPE_CHANNEL


def test_a_help_call_that_fails_counts_as_unsupported(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(raters.subprocess, "run", boom)
    assert raters.cli_supports_safe_mode("missing-binary") is False


def test_forced_values_skip_detection(tmp_path, monkeypatch):
    def never(cmd, **kw):
        raise AssertionError("no --help call when safe_mode is given")
    monkeypatch.setattr(raters.subprocess, "run", never)
    assert "--safe-mode" in _rater(tmp_path, safe_mode=True).command()
    assert "--safe-mode" not in _rater(tmp_path, safe_mode=False).command()


def test_blind_still_requires_a_clean_probe(tmp_path):
    r = _rater(tmp_path, safe_mode=True)
    r.complete = lambda p: raters.Reply(text='{"people_named": []}')
    raters.run_probe(r, ["Jane Roe"], tmp_path / "probe.json")
    assert r.provenance()["blind"] is True
    r2 = _rater(tmp_path, safe_mode=True)
    r2.complete = lambda p: raters.Reply(text='{"people_named": ["Jane Roe"]}')
    raters.run_probe(r2, ["Jane Roe"], tmp_path / "probe2.json")
    assert r2.provenance()["blind"] is False
