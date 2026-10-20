"""The MCP server end to end, over its real stdio transport.

Every other MCP test calls the tool functions in-process. This one starts the server as a
subprocess, as Claude Code does, speaks JSON-RPC to it, and checks two things nothing else
can: every line the server writes to stdout is a JSON-RPC message, and a tool call returns.

Isolation: MEMORY_SYSTEM_ROOT points at an empty corpus under tmp_path, and HOME/USERPROFILE
point at tmp_path, so the server's session directory (~/.baselayer/sessions/<pid>) is written
there and never into the operator's home. No network, no model: the tools called here do not
load the embedding model, except recall_memories, which runs only when sentence-transformers
and its model are already available offline (HF_HUB_OFFLINE=1; nothing is downloaded).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

SRC = Path(__file__).resolve().parents[1] / "src"


def _rpc(i, method, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if i is not None:
        msg["id"] = i
    if params is not None:
        msg["params"] = params
    return json.dumps(msg) + "\n"


@pytest.fixture
def server_env(tmp_path):
    root = tmp_path / "corpus"
    (root / "data" / "database").mkdir(parents=True)
    from baselayer.init_database import init_database
    init_database(root / "data" / "database" / "memory.db")
    home = tmp_path / "home"
    home.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    env.update(MEMORY_SYSTEM_ROOT=str(root), HOME=str(home), USERPROFILE=str(home),
               PYTHONPATH=str(SRC), PYTHONIOENCODING="utf-8", BASELAYER_SPEC_INJECT="0",
               ANONYMIZED_TELEMETRY="False", HF_HUB_OFFLINE="1")
    return env, home


def test_stdio_server_speaks_only_json_rpc_on_stdout(server_env):
    env, home = server_env
    calls = [
        _rpc(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "pytest", "version": "0"}}),
        _rpc(None, "notifications/initialized"),
        _rpc(2, "tools/list"),
        # verify_claims reaches verify_provenance, which prints "No layer file found ..."
        _rpc(3, "tools/call", {"name": "verify_claims", "arguments": {}}),
        _rpc(4, "tools/call", {"name": "get_stats", "arguments": {}}),
    ]
    try:
        import sentence_transformers  # noqa: F401
        recall = True
        # Over an unembedded corpus, assemble_brief used to print two warnings to stdout here.
        calls.append(_rpc(5, "tools/call", {"name": "recall_memories",
                                            "arguments": {"query": "career history"}}))
    except ImportError:
        recall = False
    proc = subprocess.run(
        [sys.executable, "-c", "from baselayer.mcp_server import main; main()"],
        input="".join(calls), capture_output=True, text=True, encoding="utf-8",
        env=env, cwd=str(home), timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    bad = []
    for ln in lines:
        try:
            json.loads(ln)
        except ValueError:
            bad.append(ln)
    assert bad == [], "non-JSON on the protocol stream: %r\nstderr tail: %s" % (
        bad, proc.stderr[-800:])
    by_id = {m.get("id"): m for m in map(json.loads, lines)}
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert {"recall_memories", "verify_claims", "get_stats", "trace_claim"} <= names
    assert "No verification questions generated" in by_id[3]["result"]["content"][0]["text"]
    assert "result" in by_id[4]
    if recall:
        assert "result" in by_id[5], by_id.get(5)
    assert (home / ".baselayer" / "sessions").exists()   # written under tmp, not real home
