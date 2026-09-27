"""
Every ChromaDB client the package builds must have anonymized telemetry OFF.

WHY THIS EXISTS. ChromaDB's `Settings().anonymized_telemetry` defaults to True, and its
product-telemetry client sends events unless that flag is off. Base Layer built every
client as `chromadb.PersistentClient(path=...)` with default settings, at a dozen call
sites, while the README says the tool has no telemetry. The fix routes every client
through `baselayer.config.get_chroma_client`, which passes
`Settings(anonymized_telemetry=False)`.

WHY THE TEST ASSERTS THE SETTINGS OBJECT AND NOT THE NETWORK. ChromaDB disables its own
telemetry whenever `pytest` is imported, so no test can observe a transmission. What a
test CAN check is (1) the helper's client carries the flag, (2) no source file builds a
client any other way, and (3) real call sites hand the helper's settings to chromadb.
"""

import ast
import os
import sys
import types
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
HELPER_FILE = SRC_DIR / "baselayer" / "config.py"
HELPER_NAME = "get_chroma_client"
CLIENT_CONSTRUCTORS = {"PersistentClient", "Client", "EphemeralClient", "HttpClient",
                       "AsyncHttpClient", "CloudClient"}


def _client_construction_sites():
    """Every call to a chromadb client constructor anywhere under src/, by AST.

    Catches `chromadb.PersistentClient(...)`, `chromadb.Client(...)` and names bound by
    `from chromadb import PersistentClient [as X]`. The one permitted site is inside the
    helper itself. The archive directory is scanned too: it is shipped in the package,
    so a client built there would be built without the flag.
    """
    sites = []
    for py in SRC_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("chromadb"):
                for a in node.names:
                    if a.name in CLIENT_CONSTRUCTORS:
                        aliases.add(a.asname or a.name)
        helper_ranges = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == HELPER_NAME and py == HELPER_FILE:
                helper_ranges.append((node.lineno, node.end_lineno))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = None
            if isinstance(f, ast.Attribute) and f.attr in CLIENT_CONSTRUCTORS:
                base = f.value
                if isinstance(base, ast.Name) and base.id == "chromadb":
                    name = f"chromadb.{f.attr}"
            elif isinstance(f, ast.Name) and f.id in aliases:
                name = f.id
            if name is None:
                continue
            if any(lo <= node.lineno <= hi for lo, hi in helper_ranges):
                continue
            sites.append(f"{py.relative_to(SRC_DIR)}:{node.lineno} {name}")
    return sites


def test_no_chroma_client_is_built_outside_the_helper():
    sites = _client_construction_sites()
    assert sites == [], (
        "ChromaDB clients built without the telemetry-off helper "
        f"(use baselayer.config.{HELPER_NAME}):\n  " + "\n  ".join(sites)
    )


def test_helper_client_has_telemetry_disabled(tmp_path):
    from baselayer.config import get_chroma_client
    client = get_chroma_client(tmp_path / "vectors")
    assert client.get_settings().anonymized_telemetry is False


def test_helper_defaults_to_the_configured_vectors_dir(monkeypatch):
    import baselayer.config as config
    import chromadb.config  # noqa: F401  keep the real Settings importable under the fake package
    seen = {}

    fake = types.ModuleType("chromadb")
    def PersistentClient(path=None, settings=None):
        seen["path"] = path
        seen["settings"] = settings
        return object()
    fake.PersistentClient = PersistentClient
    monkeypatch.setitem(sys.modules, "chromadb", fake)
    config.get_chroma_client()
    assert seen["path"] == str(config.VECTORS_DIR)
    assert seen["settings"].anonymized_telemetry is False


@pytest.fixture
def recording_chromadb(monkeypatch):
    """Replace chromadb.PersistentClient with a recorder; keep the real Settings class."""
    import chromadb
    calls = []

    class _Coll:
        def get(self, ids=None, **kw):
            return {"ids": []}
        def delete(self, ids=None, **kw):
            pass

    class _Client:
        def get_collection(self, name, **kw):
            return _Coll()
        def get_or_create_collection(self, name, **kw):
            return _Coll()

    def PersistentClient(path=None, settings=None, **kw):
        calls.append({"path": path, "settings": settings})
        return _Client()

    monkeypatch.setattr(chromadb, "PersistentClient", PersistentClient)
    return calls


def test_forget_vector_cleanup_builds_a_telemetry_off_client(recording_chromadb):
    from baselayer.cli import _delete_vectors
    _delete_vectors(["some-fact-id"])
    assert recording_chromadb, "no client was built"
    assert all(c["settings"] is not None and c["settings"].anonymized_telemetry is False
               for c in recording_chromadb)


def test_mcp_server_builds_a_telemetry_off_client(recording_chromadb, monkeypatch):
    import baselayer.mcp_server as mcp_server
    monkeypatch.setattr(mcp_server, "_chroma_client", None)
    mcp_server._get_chroma_client()
    assert recording_chromadb, "no client was built"
    assert recording_chromadb[-1]["settings"].anonymized_telemetry is False
