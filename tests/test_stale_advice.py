"""After `forget`, every notice says to re-author the layers (`baselayer author`), not
`baselayer author --compose`: staleness is per file by modification time, so any re-author clears
it for the layers, and `--compose` only rebuilds the optional brief. No model calls.
"""
import inspect
import json

from baselayer import cli, mcp_server, spec_staleness


def test_marker_note_does_not_prescribe_compose(tmp_path):
    spec_staleness.record_forget(tmp_path, 2, "fact", now=1.0)
    note = json.loads(spec_staleness.marker_path(tmp_path).read_text(encoding="utf-8"))["note"]
    assert "`baselayer author`" in note
    assert "author --compose" not in note


def test_no_source_notice_prescribes_author_compose():
    for mod in (cli, mcp_server, spec_staleness):
        src = inspect.getsource(mod)
        assert "author --compose" not in src, mod.__name__



# get_help() returns agent_guide.AGENT_GUIDE to any MCP client, so stale pipeline advice there is
# acted on by an agent, not just read. Each string below is advice the code no longer supports:
# `run` does not compose and `embed` is not one of its steps, the brief is optional, `embed` writes the `messages`
# collection only (fact vectors are written during extraction), `baselayer search` is semantic
# search over messages, and the brief has no fixed size.
_STALE_AGENT_GUIDE = (
    "import -> extract -> embed -> author -> compose",
    "then `baselayer compose`",
    "`baselayer embed`, then re-author",
    "`baselayer compose`. Re-tag",
    "Generate ChromaDB vectors for the fact corpus",
    "FTS keyword search across active facts",
    "~3,000 tokens",
)


def test_agent_guide_carries_no_stale_pipeline_advice():
    from baselayer import agent_guide
    for phrase in _STALE_AGENT_GUIDE:
        assert phrase not in agent_guide.AGENT_GUIDE, phrase


# The README registers the MCP server with `--scope user` so it serves any folder, and tells the
# reader to keep the API key in the environment rather than type it into a command. Every
# user-facing hint in the package must say the same: a `claude mcp add` without a scope registers
# the server for one folder only, and a printed `sk-ant-...` example invites pasting a key.
def _package_sources():
    from pathlib import Path
    root = Path(cli.__file__).resolve().parent
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(("archive/", "experiments/")):
            continue
        yield rel, p.read_text(encoding="utf-8")


def test_every_mcp_add_hint_names_a_scope():
    import re
    bad = []
    for rel, src in _package_sources():
        for m in re.finditer(r"claude mcp add(?!/)[^\n`\"]*", src):
            if "--scope" not in m.group(0):
                bad.append((rel, m.group(0)))
    assert not bad, bad


def test_no_hint_shows_a_key_to_paste():
    bad = [rel for rel, src in _package_sources() if "ANTHROPIC_API_KEY=sk-ant-" in src]
    assert not bad, bad


def test_mcp_add_hint_follows_the_data_root(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMORY_SYSTEM_ROOT", raising=False)
    assert "--scope user" in cli._mcp_add_hint()
    monkeypatch.setenv("MEMORY_SYSTEM_ROOT", str(tmp_path))
    hint = cli._mcp_add_hint()
    assert "--scope local" in hint
    assert '"MEMORY_SYSTEM_ROOT=%s"' % tmp_path.resolve() in hint
