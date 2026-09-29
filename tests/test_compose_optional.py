"""The unified brief (compose) is no longer part of the automated flow.

- `author_from_package` authors the layers only; `--compose` builds the brief on request, and
  `--no-compose` is still accepted (it is now the default).
- `baselayer run` authors the layers and does not compose.
- `baselayer compose` stays, as an explicit optional command, and says so in its help.
- The MCP `get_brief` tool treats a missing brief as optional, not as a defect.
No API calls: fake clients only.
"""
import sqlite3
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from tests.test_artifact_stamps import AuthorClient, V, author_env  # noqa: F401  (fixture)


def _tools():
    return [c["tools"][0]["name"] for c in AuthorClient.calls]


def test_author_from_package_writes_no_brief_by_default(author_env, capsys):
    out = author_env.run(author_env.write_pkg("anchors.json", V))
    assert _tools() == ["emit_layer"]
    assert (out / "anchors.md").exists() and (out / "anchors.stamp.json").exists()
    assert not (out / "brief.md").exists()
    assert not (out / "brief.stamp.json").exists()
    printed = capsys.readouterr().out
    assert "--compose" in printed                   # says how to get one


def test_compose_flag_builds_the_brief(author_env):
    out = author_env.run(author_env.write_pkg("anchors.json", V), extra=("--compose",))
    assert _tools() == ["emit_layer", "emit_brief"]
    assert (out / "brief.md").exists() and (out / "brief.stamp.json").exists()


def test_no_compose_is_still_accepted(author_env):
    # Control: the old opt-out keeps working (it is now the default).
    out = author_env.run(author_env.write_pkg("anchors.json", V), extra=("--no-compose",))
    assert _tools() == ["emit_layer"] and not (out / "brief.md").exists()


def test_the_estimate_prices_no_compose_call_by_default(author_env, capsys):
    author_env.run(author_env.write_pkg("anchors.json", V))
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("ESTIMATE")][0]
    assert "compose" not in line
    author_env.run(author_env.write_pkg("core.json", V), extra=("--compose",))
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("ESTIMATE")][0]
    assert "compose" in line


def test_cli_author_from_package_forwards_compose(monkeypatch):
    from baselayer import cli
    from baselayer.distillation import author_from_package as afp
    seen = {}
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr(afp, "main", lambda: seen.setdefault("argv", list(sys.argv)))
    monkeypatch.setattr(sys, "argv", ["baselayer", "author-from-package", "--package", "p.json",
                                      "--outdir", "o", "--compose"])
    cli.main()
    assert "--compose" in seen["argv"]
    seen.clear()
    monkeypatch.setattr(sys, "argv", ["baselayer", "author-from-package", "--package", "p.json",
                                      "--outdir", "o"])
    cli.main()
    assert "--compose" not in seen["argv"]


def test_run_authors_the_layers_and_does_not_compose(monkeypatch, tmp_path):
    from baselayer import cli
    import baselayer.config as cfg
    import baselayer.agent_pipeline as ap
    db = tmp_path / "memory.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE conversations (id TEXT)")
    c.execute("INSERT INTO conversations VALUES ('c1')")
    c.commit()
    c.close()
    src = tmp_path / "export.json"
    src.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cfg, "DATABASE_FILE", db)
    monkeypatch.setattr(cfg, "database_initialized", lambda: True)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    seen = {}
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr(cli, "cmd_estimate", lambda a: None)
    monkeypatch.setattr(cli, "cmd_extract", lambda a: None)
    monkeypatch.setattr(cli, "cmd_author", lambda a: seen.setdefault("compose", a.compose))
    monkeypatch.setattr(cli, "_run_traceability", lambda: seen.setdefault("trace", True))

    def no_compose(*a, **k):
        raise AssertionError("baselayer run must not compose")
    monkeypatch.setattr(ap, "compose_unified_brief", no_compose)
    cli.cmd_run(NS(file=str(src), yes=True, document_mode=False, limit=None))
    assert seen == {"compose": False, "trace": True}


def test_compose_help_says_it_is_optional(monkeypatch, capsys):
    from baselayer import cli
    monkeypatch.setattr(sys, "argv", ["baselayer", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    out = " ".join(capsys.readouterr().out.split())
    i = out.index("compose ")
    assert "optional" in out[i:out.index(" distill ", i)].lower()


def test_get_brief_treats_a_missing_brief_as_optional(tmp_path):
    from baselayer import mcp_server
    with patch.object(mcp_server, "UNIFIED_BRIEF_FILE", tmp_path / "none.md"), \
         patch.object(mcp_server, "UNIFIED_BRIEF_CITED_FILE", tmp_path / "none_cited.md"), \
         patch.object(mcp_server, "_is_serving_enabled", lambda: True):
        msg = mcp_server.get_brief("test")
    assert "missing" not in msg.lower()
    assert "optional" in msg.lower() and "baselayer compose" in msg
