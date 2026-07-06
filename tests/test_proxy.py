"""
Tests for the OpenRouter proxy (proxy_server.py, D-049).

All tests run against a mock upstream server (a local aiohttp app standing
in for OpenRouter). No real network calls, no API key required.

Covers: injection placement, header and flag suppression, capture rows,
streaming and non-streaming forwarding, models passthrough, missing-key
error, default model, session grouping, and specification assembly.
"""

import asyncio
import json
import sqlite3

import pytest

aiohttp = pytest.importorskip("aiohttp", reason="proxy extra not installed")

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from baselayer.proxy_server import (
    ConversationRecorder,
    build_injection_text,
    create_app,
    derive_session_id,
    inject_specification,
)

SPEC_TEXT = "TEST SPECIFICATION: reason from first principles."

COMPLETION_RESPONSE = {
    "id": "gen-test-1",
    "object": "chat.completion",
    "model": "openai/gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from upstream"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4},
}

STREAM_CHUNKS = [
    {"id": "gen-test-2", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hel"}}]},
    {"id": "gen-test-2", "choices": [{"index": 0, "delta": {"content": "lo "}}]},
    {"id": "gen-test-2", "choices": [{"index": 0, "delta": {"content": "streamed"}}]},
]

MODELS_RESPONSE = {"data": [{"id": "openai/gpt-4o"}, {"id": "anthropic/claude-sonnet-4"}]}


def make_upstream_app(received):
    """Mock OpenRouter: records incoming payloads, returns canned responses."""

    async def chat(request):
        payload = await request.json()
        received.append({
            "payload": payload,
            "auth": request.headers.get("Authorization"),
        })
        if payload.get("stream"):
            resp = web.StreamResponse(
                status=200, headers={"Content-Type": "text/event-stream"}
            )
            await resp.prepare(request)
            await resp.write(b": OPENROUTER PROCESSING\n\n")
            for chunk in STREAM_CHUNKS:
                await resp.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            await resp.write(b"data: [DONE]\n\n")
            await resp.write_eof()
            return resp
        return web.json_response(COMPLETION_RESPONSE)

    async def models(request):
        return web.json_response(MODELS_RESPONSE)

    app = web.Application()
    app.router.add_post("/chat/completions", chat)
    app.router.add_get("/models", models)
    return app


def run_proxy_scenario(scenario, tmp_path, *, inject=True, capture=True,
                       api_key="test-key", inject_text=SPEC_TEXT,
                       default_model=None):
    """Run an async scenario(client, received) against proxy + mock upstream.

    Manages its own event loop so the suite needs no pytest-asyncio plugin.
    Returns (scenario_result, received_upstream_calls, capture_db_path).
    """
    received = []
    db_path = tmp_path / "proxy_capture.db"

    async def runner():
        upstream = TestServer(make_upstream_app(received))
        await upstream.start_server()
        try:
            app = create_app(
                upstream_base=str(upstream.make_url("")).rstrip("/"),
                api_key=api_key,
                inject=inject,
                capture=capture,
                db_path=db_path,
                default_model=default_model,
                inject_text=inject_text,
            )
            client = TestClient(TestServer(app))
            await client.start_server()
            try:
                return await scenario(client, received)
            finally:
                await client.close()
        finally:
            await upstream.close()

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(runner())
    finally:
        loop.close()
    return result, received, db_path


def fetch_capture_rows(db_path):
    """Return (conversations, messages) rows from the capture database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        convs = conn.execute(
            "SELECT * FROM conversations ORDER BY created_at"
        ).fetchall()
        msgs = conn.execute(
            "SELECT * FROM messages ORDER BY conversation_id, sequence_order"
        ).fetchall()
        return [dict(r) for r in convs], [dict(r) for r in msgs]
    finally:
        conn.close()


BASE_REQUEST = {
    "model": "openai/gpt-4o",
    "messages": [{"role": "user", "content": "What should I focus on?"}],
}


# ==========================================================================
# INJECTION
# ==========================================================================

class TestInjection:
    def test_system_message_inserted_when_absent(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 200
            return await resp.json()

        result, received, _ = run_proxy_scenario(scenario, tmp_path)
        sent = received[0]["payload"]["messages"]
        assert sent[0]["role"] == "system"
        assert sent[0]["content"] == SPEC_TEXT
        assert sent[1] == BASE_REQUEST["messages"][0]
        # Response relayed unchanged
        assert result["choices"][0]["message"]["content"] == "Hello from upstream"

    def test_spec_prepended_to_existing_system_message(self, tmp_path):
        request = {
            "model": "openai/gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a pirate."},
                {"role": "user", "content": "Hello"},
            ],
        }

        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=request)
            assert resp.status == 200

        _, received, _ = run_proxy_scenario(scenario, tmp_path)
        sent = received[0]["payload"]["messages"]
        assert len(sent) == 2
        assert sent[0]["role"] == "system"
        assert sent[0]["content"].startswith(SPEC_TEXT)
        assert sent[0]["content"].endswith("You are a pirate.")

    def test_header_suppresses_injection(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post(
                "/v1/chat/completions",
                json=BASE_REQUEST,
                headers={"x-baselayer-inject": "off"},
            )
            assert resp.status == 200

        _, received, _ = run_proxy_scenario(scenario, tmp_path)
        sent = received[0]["payload"]["messages"]
        assert sent == BASE_REQUEST["messages"]

    def test_no_inject_flag_suppresses_injection(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 200

        _, received, _ = run_proxy_scenario(scenario, tmp_path, inject=False)
        sent = received[0]["payload"]["messages"]
        assert sent == BASE_REQUEST["messages"]

    def test_inject_specification_unit(self):
        # No system message: inserted at position 0
        out = inject_specification([{"role": "user", "content": "hi"}], "SPEC")
        assert out[0] == {"role": "system", "content": "SPEC"}
        # Existing string system message: prepended
        out = inject_specification(
            [{"role": "system", "content": "base"}, {"role": "user", "content": "hi"}],
            "SPEC",
        )
        assert out[0]["content"] == "SPEC\n\nbase"
        # List-form system content stays intact; separate system message inserted
        parts = [{"type": "text", "text": "base"}]
        out = inject_specification(
            [{"role": "system", "content": parts}, {"role": "user", "content": "hi"}],
            "SPEC",
        )
        assert out[0] == {"role": "system", "content": "SPEC"}
        assert out[1]["content"] is parts


# ==========================================================================
# CAPTURE (local-only)
# ==========================================================================

class TestCapture:
    def test_exchange_recorded_with_proxy_source(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 200

        _, _, db_path = run_proxy_scenario(scenario, tmp_path)
        convs, msgs = fetch_capture_rows(db_path)
        assert len(convs) == 1
        assert convs[0]["source"] == "proxy"
        assert convs[0]["id"].startswith("proxy-")
        assert convs[0]["message_count"] == 2
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["content_text"] == "What should I focus on?"
        assert msgs[1]["content_text"] == "Hello from upstream"
        # The injected specification is never captured
        assert all(SPEC_TEXT not in m["content_text"] for m in msgs)

    def test_no_capture_flag_writes_nothing(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 200

        _, _, db_path = run_proxy_scenario(scenario, tmp_path, capture=False)
        assert not db_path.exists()

    def test_session_header_groups_turns_into_one_conversation(self, tmp_path):
        async def scenario(client, received):
            headers = {"x-session-id": "abc-123"}
            r1 = await client.post(
                "/v1/chat/completions",
                json={"model": "m", "messages": [{"role": "user", "content": "turn one"}]},
                headers=headers,
            )
            assert r1.status == 200
            r2 = await client.post(
                "/v1/chat/completions",
                json={"model": "m", "messages": [
                    {"role": "user", "content": "turn one"},
                    {"role": "assistant", "content": "Hello from upstream"},
                    {"role": "user", "content": "turn two"},
                ]},
                headers=headers,
            )
            assert r2.status == 200

        _, _, db_path = run_proxy_scenario(scenario, tmp_path)
        convs, msgs = fetch_capture_rows(db_path)
        assert len(convs) == 1
        assert convs[0]["id"] == "proxy-abc-123"
        assert convs[0]["message_count"] == 4
        # Only the newest user turn is recorded per request (no duplication)
        user_texts = [m["content_text"] for m in msgs if m["role"] == "user"]
        assert user_texts == ["turn one", "turn two"]
        assert [m["sequence_order"] for m in msgs] == [0, 1, 2, 3]

    def test_derived_session_id_stable_across_turns(self):
        first = [{"role": "user", "content": "same opening"}]
        later = first + [
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "follow-up"},
        ]
        assert derive_session_id({}, first) == derive_session_id({}, later)

    def test_recorder_initializes_missing_database(self, tmp_path):
        db_path = tmp_path / "fresh.db"
        recorder = ConversationRecorder(db_path)
        conv_id = recorder.record_exchange(
            "s1", [{"role": "user", "content": "hello"}], "world", model="m"
        )
        assert conv_id == "proxy-s1"
        convs, msgs = fetch_capture_rows(db_path)
        assert convs[0]["source"] == "proxy"
        assert len(msgs) == 2


# ==========================================================================
# FORWARDING
# ==========================================================================

class TestForwarding:
    def test_authorization_header_carries_key(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 200

        _, received, _ = run_proxy_scenario(scenario, tmp_path)
        assert received[0]["auth"] == "Bearer test-key"

    def test_default_model_applied_when_missing(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            assert resp.status == 200

        _, received, _ = run_proxy_scenario(
            scenario, tmp_path, default_model="openai/gpt-4o-mini"
        )
        assert received[0]["payload"]["model"] == "openai/gpt-4o-mini"

    def test_request_model_wins_over_default(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 200

        _, received, _ = run_proxy_scenario(
            scenario, tmp_path, default_model="openai/gpt-4o-mini"
        )
        assert received[0]["payload"]["model"] == "openai/gpt-4o"

    def test_streaming_passthrough_and_capture(self, tmp_path):
        request = dict(BASE_REQUEST, stream=True)

        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=request)
            assert resp.status == 200
            assert resp.headers["Content-Type"].startswith("text/event-stream")
            return await resp.read()

        raw, received, db_path = run_proxy_scenario(scenario, tmp_path)
        # SSE chunks relayed unmodified, including the [DONE] sentinel
        assert received[0]["payload"]["stream"] is True
        assert b'"content": "Hel"' in raw or b'"content":"Hel"' in raw
        assert b"data: [DONE]" in raw
        # Assistant text reassembled from deltas and captured
        _, msgs = fetch_capture_rows(db_path)
        assistant = [m for m in msgs if m["role"] == "assistant"]
        assert assistant[0]["content_text"] == "Hello streamed"

    def test_models_passthrough(self, tmp_path):
        async def scenario(client, received):
            resp = await client.get("/v1/models")
            assert resp.status == 200
            return await resp.json()

        result, _, _ = run_proxy_scenario(scenario, tmp_path)
        assert result == MODELS_RESPONSE

    def test_missing_key_returns_401_without_forwarding(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post("/v1/chat/completions", json=BASE_REQUEST)
            assert resp.status == 401
            return await resp.json()

        result, received, db_path = run_proxy_scenario(
            scenario, tmp_path, api_key=""
        )
        assert "OPENROUTER_API_KEY" in result["error"]["message"]
        assert received == []  # upstream never called
        _, msgs = fetch_capture_rows(db_path)
        assert msgs == []  # nothing captured for failed requests

    def test_invalid_json_returns_400(self, tmp_path):
        async def scenario(client, received):
            resp = await client.post(
                "/v1/chat/completions",
                data=b"not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400

        _, received, _ = run_proxy_scenario(scenario, tmp_path)
        assert received == []


# ==========================================================================
# SPECIFICATION ASSEMBLY
# ==========================================================================

class TestBuildInjectionText:
    def _patch_layers(self, monkeypatch, tmp_path, core_content):
        import baselayer.mcp_server as ms

        core = tmp_path / "core_v4.md"
        core.write_text(
            f"---\nlayer: core\n---\n\n## Injectable Block\n\n{core_content}",
            encoding="utf-8",
        )
        monkeypatch.setattr(ms, "CORE_LAYER_FILE", core)
        monkeypatch.setattr(ms, "ANCHORS_LAYER_FILE", tmp_path / "missing_anchors.md")
        monkeypatch.setattr(ms, "PREDICTIONS_LAYER_FILE", tmp_path / "missing_predictions.md")
        monkeypatch.setattr(ms, "_is_serving_enabled", lambda: True)

    def test_includes_layers_and_strips_tool_sections(self, monkeypatch, tmp_path):
        self._patch_layers(monkeypatch, tmp_path, "CORE CONTENT MARKER")
        text = build_injection_text()
        assert "CORE CONTENT MARKER" in text
        # MCP-only sections stripped: proxied models have no tools
        assert "## Tool guidance" not in text
        assert "get_help" not in text
        assert "recall_memories" not in text

    def test_empty_when_no_layers_authored(self, monkeypatch, tmp_path):
        import baselayer.mcp_server as ms

        monkeypatch.setattr(ms, "CORE_LAYER_FILE", tmp_path / "a.md")
        monkeypatch.setattr(ms, "ANCHORS_LAYER_FILE", tmp_path / "b.md")
        monkeypatch.setattr(ms, "PREDICTIONS_LAYER_FILE", tmp_path / "c.md")
        monkeypatch.setattr(ms, "_is_serving_enabled", lambda: True)
        assert build_injection_text() == ""

    def test_empty_when_serving_disabled(self, monkeypatch, tmp_path):
        import baselayer.mcp_server as ms

        self._patch_layers(monkeypatch, tmp_path, "CORE CONTENT")
        monkeypatch.setattr(ms, "_is_serving_enabled", lambda: False)
        assert build_injection_text() == ""


# ==========================================================================
# CLI REGISTRATION
# ==========================================================================

class TestCliRegistration:
    def test_proxy_subcommand_parses(self, monkeypatch):
        import baselayer.cli as cli

        captured = {}
        monkeypatch.setattr(
            cli, "cmd_proxy", lambda args: captured.update(vars(args))
        )
        monkeypatch.setattr(
            "sys.argv",
            ["baselayer", "proxy", "--port", "5200", "--no-inject",
             "--no-capture", "--model-default", "openai/gpt-4o"],
        )
        cli.main()
        assert captured["port"] == 5200
        assert captured["no_inject"] is True
        assert captured["no_capture"] is True
        assert captured["model_default"] == "openai/gpt-4o"
