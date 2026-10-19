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

