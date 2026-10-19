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
# `run` does not embed messages or compose, the brief is optional, `embed` writes the `messages`
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
