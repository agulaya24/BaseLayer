"""The MCP server end to end, over its real stdio transport.

Every other MCP test calls the tool functions in-process. This one starts the server as a
subprocess, as Claude Code does, speaks JSON-RPC to it, and checks two things nothing else
can: every line the server writes to stdout is a JSON-RPC message, and a tool call returns.

Isolation: MEMORY_SYSTEM_ROOT points at an empty corpus under tmp_path, and HOME/USERPROFILE
point at tmp_path, so the server's session directory (~/.baselayer/sessions/<pid>) is written
there and never into the operator's home. No network, no model: the tools called here do not
load the embedding model, except recall_memories, which runs only when sentence-transformers
and its model are already available offline (HF_HUB_OFFLINE=1; nothing is downloaded).

stdin stays open until every request has its reply. Closing it early is EOF to the transport,
and newer mcp releases (1.30) cancel requests still in flight on EOF, so with the requests
piped in all at once the slower replies never came. That was the harness, not the server.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
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


def _converse(env, cwd, calls, want, err_path, timeout=120, nudge=True):
    """Send every request, read stdout until each id in `want` has a reply (or the deadline
    passes, or the server exits), then close stdin. Returns (stdout lines, ids seen).

    nudge: after 3 s with no output, send a ping (ids from 1000), as a live client would send
    its next message. On Windows the first recall_memories call stalls until stdin receives
    more input (see test_recall_replies_with_no_further_input); the ping lets this test check
    the protocol stream anyway, and that defect is pinned by its own test."""
    with open(err_path, "w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            [sys.executable, "-c", "from baselayer.mcp_server import main; main()"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True,
            encoding="utf-8", env=env, cwd=str(cwd))
        out_q = queue.Queue()

        def _read():
            for ln in proc.stdout:
                out_q.put(ln)
            out_q.put(None)

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        proc.stdin.write("".join(calls))
        proc.stdin.flush()
        lines, seen = [], set()
        deadline = time.monotonic() + timeout
        finished = False
        ping_id = 1000
        while not want <= seen:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                ln = out_q.get(timeout=min(left, 3.0) if nudge else left)
            except queue.Empty:
                if nudge and time.monotonic() < deadline:
                    proc.stdin.write(_rpc(ping_id, "ping"))
                    proc.stdin.flush()
                    ping_id += 1
                    continue
                break
            if ln is None:
                finished = True
                break
            if ln.strip():
                lines.append(ln.rstrip("\n"))
                try:
                    seen.add(json.loads(ln).get("id"))
                except ValueError:
                    pass
        proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        reader.join(timeout=10)
        while not finished:            # anything written after the last awaited reply
            try:
                ln = out_q.get_nowait()
            except queue.Empty:
                break
            if ln is None:
                break
            if ln.strip():
                lines.append(ln.rstrip("\n"))
    return lines, seen


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
    want = {1, 2, 3, 4} | ({5} if recall else set())
    err_path = home.parent / "server_stderr.txt"
    lines, seen = _converse(env, home, calls, want, err_path)
    stderr_tail = err_path.read_text(encoding="utf-8", errors="replace")[-800:]
    bad = []
    for ln in lines:
        try:
            json.loads(ln)
        except ValueError:
            bad.append(ln)
    assert bad == [], "non-JSON on the protocol stream: %r\nstderr tail: %s" % (
        bad, stderr_tail)
    assert want <= seen, "no reply for ids %s\nstderr tail: %s" % (sorted(want - seen), stderr_tail)
    by_id = {m.get("id"): m for m in map(json.loads, lines)}
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert {"recall_memories", "verify_claims", "get_stats", "trace_claim"} <= names
    assert "No verification questions generated" in by_id[3]["result"]["content"][0]["text"]
    assert "result" in by_id[4]
    if recall:
        assert "result" in by_id[5], by_id.get(5)
    assert (home / ".baselayer" / "sessions").exists()   # written under tmp, not real home


@pytest.mark.xfail(sys.platform == "win32", strict=True,
                   reason="known defect: on Windows the first recall_memories call imports the "
                          "embedding stack while the transport's reader thread is blocked reading "
                          "stdin, and the import stalls until stdin receives more input (shown by "
                          "pre-importing sentence_transformers before the transport starts, which "
                          "removes the stall). A client that waits for the reply never gets it.")
def test_recall_replies_with_no_further_input(server_env):
    """recall_memories must reply while stdin stays open and nothing more is sent."""
    pytest.importorskip("sentence_transformers")
    env, home = server_env
    calls = [
        _rpc(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "pytest", "version": "0"}}),
        _rpc(None, "notifications/initialized"),
        _rpc(5, "tools/call", {"name": "recall_memories",
                               "arguments": {"query": "career history"}}),
    ]
    err_path = home.parent / "server_stderr.txt"
    lines, seen = _converse(env, home, calls, {1, 5}, err_path, timeout=90, nudge=False)
    assert {1, 5} <= seen, "no reply for ids %s" % sorted({1, 5} - seen)
