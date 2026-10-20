"""MCP tools must never write to stdout.

WHY THIS EXISTS. The MCP server speaks JSON-RPC over stdio, so stdout is the protocol stream
(mcp_server.py logs to stderr for that reason). `recall_memories` calls assemble_brief's
get_theme_block and get_episode_block, which reported problems with print() to stdout. The
episode branch looks for a summary collection that nothing in the package creates, so EVERY
recall_memories call printed "Warning: No summary collection found in ChromaDB" into the
protocol stream. The existing recall tests patched both functions away and could not see it.

No network, no model: a fake embedding model and a fake Chroma client.
"""
import sqlite3

import pytest


class FakeModel:
    def encode(self, texts):
        class _A(list):
            def tolist(self):
                return list(self)
        return _A([[0.1, 0.2, 0.3] for _ in texts])


class EmptyChroma:
    """A store with no collections at all: a corpus that was never embedded."""
    def get_collection(self, name):
        raise ValueError("Collection %s does not exist." % name)


class FactsOnlyChroma:
    """memory_facts exists and matches nothing; no summary collection, as every real store."""
    class _C:
        metadata = {"hnsw:space": "cosine"}

        def query(self, **kw):
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    def get_collection(self, name):
        if name == "memory_facts":
            return self._C()
        raise ValueError("Collection %s does not exist." % name)


@pytest.fixture
def mcp(tmp_path, monkeypatch):
    import baselayer.mcp_server as m
    db = tmp_path / "memory.db"
    sqlite3.connect(db).close()

    def _get_db(*a, **k):
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(m, "DATABASE_FILE", db)
    monkeypatch.setattr(m, "get_db", _get_db)
    monkeypatch.setattr(m, "_get_embed_model", lambda: FakeModel())
    return m


@pytest.mark.parametrize("chroma", [EmptyChroma(), FactsOnlyChroma()],
                         ids=["no_collections", "facts_only"])
def test_recall_memories_writes_nothing_to_stdout(mcp, monkeypatch, capfd, chroma):
    monkeypatch.setattr(mcp, "_get_chroma_client", lambda: chroma)
    result = mcp.recall_memories("career history")
    out, _err = capfd.readouterr()
    assert out == "", "recall_memories wrote to stdout, the JSON-RPC stream: %r" % out
    assert "No relevant memories found" in result


def test_episode_block_reports_a_missing_summary_store_on_stderr(capfd):
    from baselayer.assemble_brief import get_episode_block
    assert get_episode_block(None, "q", FakeModel(), EmptyChroma()) == ""
    out, err = capfd.readouterr()
    assert out == ""
    assert "summary collection" in err


def test_a_print_inside_any_tool_goes_to_stderr(mcp, monkeypatch, capfd):
    """verify_claims reaches verify_provenance, which prints progress and warnings with plain
    print(). Any print inside a tool body must land on stderr, not the protocol stream."""
    import baselayer.verify_provenance as vp

    def noisy(layer, claim_id_filter=None):
        print("  No layer file found for ANCHORS")
        return {"total": 0}
    monkeypatch.setattr(vp, "run_verification", noisy)
    result = mcp.verify_claims()
    out, err = capfd.readouterr()
    assert out == ""
    assert "No layer file found" in err
    assert "No verification questions generated" in result


def test_every_registered_tool_and_resource_is_guarded(mcp):
    """A call-site check, so a tool added later cannot skip the guard."""
    import inspect
    names = [n for n, f in inspect.getmembers(mcp, inspect.isfunction)
             if f.__module__ == mcp.__name__ and n in _registered(mcp)]
    assert names, "found no registered tools"
    unguarded = [n for n in names if not getattr(getattr(mcp, n), "_stdout_guarded", False)]
    assert unguarded == []


def _registered(m):
    import re
    src = open(m.__file__, encoding="utf-8").read()
    return set(re.findall(r"@mcp\.(?:tool|resource)\([^)]*\)\s*\n(?:@\w+\s*\n)*def (\w+)", src))
