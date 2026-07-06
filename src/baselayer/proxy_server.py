"""
Base Layer OpenRouter Proxy (D-049).

A local OpenAI-compatible proxy that puts the behavioral specification in
front of any model OpenRouter serves. Four responsibilities, nothing else:

  1. Accept   OpenAI-compatible requests on localhost (default port 5100):
              POST /v1/chat/completions and GET /v1/models.
  2. Inject   the structural specification (CORE + ANCHORS + PREDICTIONS,
              assembled by mcp_server._build_specification_text) into the
              system message of each chat request.
  3. Forward  the request to OpenRouter with OPENROUTER_API_KEY, streaming
              (SSE) or non-streaming, and relay the response unchanged.
  4. Record   each exchange to the local SQLite database with
              source='proxy' so a later `baselayer extract` can learn
              from proxied conversations.

Privacy model:
  Capture is LOCAL-ONLY. Exchanges are written to the same SQLite database
  the pipeline uses, on this machine. Nothing is uploaded anywhere except
  the forwarded request to OpenRouter itself (which is the point of the
  proxy). Disable capture entirely with `baselayer proxy --no-capture`.

Injection suppression (avoids double-injection when the client already
loads the specification, e.g. via the Base Layer MCP resource):
  - Per request:  send header `x-baselayer-inject: off`.
  - Per server:   start with `baselayer proxy --no-inject`.

Dependency: aiohttp, installed via the optional extra:
  pip install 'baselayer[proxy]'

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  baselayer proxy [--port 5100] [--no-inject] [--no-capture]
                  [--model-default openai/gpt-4o]

Then point any OpenAI-compatible client at http://localhost:5100/v1.
"""

import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

try:
    import aiohttp
    from aiohttp import web
except ImportError as _err:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "The Base Layer proxy requires aiohttp. "
        "Install the proxy extra: pip install 'baselayer[proxy]'"
    ) from _err

from baselayer.config import (
    DATABASE_FILE,
    OPENROUTER_BASE_URL,
    PROXY_HOST,
    PROXY_PORT,
    get_db,
    get_openrouter_api_key,
)

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="[baselayer-proxy] %(levelname)s: %(message)s",
)
logger = logging.getLogger("baselayer-proxy")

# aiohttp application-state keys (typed, per aiohttp >= 3.9 guidance).
K_UPSTREAM = web.AppKey("upstream_base", str)
K_API_KEY = web.AppKey("api_key", str)
K_INJECT = web.AppKey("inject", bool)
K_INJECT_TEXT = web.AppKey("inject_text", str)
K_DEFAULT_MODEL = web.AppKey("default_model", object)
K_RECORDER = web.AppKey("recorder", object)
K_CLIENT_SESSION = web.AppKey("client_session", object)

# Request headers the proxy understands.
INJECT_HEADER = "x-baselayer-inject"   # "off" suppresses injection for this request
SESSION_HEADER = "x-session-id"        # groups requests into one conversation

# Sections of the MCP specification text that reference MCP tools. Proxied
# models have no tools, so these are stripped before injection.
_TOOL_MANIFEST_MARKER = "## Tool guidance"
_HELP_PARAGRAPH_MARKER = "**If the user asks about Base Layer itself**"


# ==========================================================================
# SPECIFICATION ASSEMBLY
# ==========================================================================

def build_injection_text():
    """Assemble the specification text to inject into proxied requests.

    Reuses the canonical builder from mcp_server (the current 0.4.0 serving
    surface) and strips the MCP tool-guidance sections, which reference
    tools a proxied model cannot call.

    Returns an empty string when injection should be skipped: serving is
    disabled via `baselayer serve disable`, or no specification layers have
    been authored yet (graceful degradation: the proxy still forwards).
    """
    import baselayer.mcp_server as ms

    if not ms._is_serving_enabled():
        return ""

    blocks = [
        ms._extract_layer_block(p)
        for p in (ms.CORE_LAYER_FILE, ms.ANCHORS_LAYER_FILE, ms.PREDICTIONS_LAYER_FILE)
    ]
    if not any(blocks):
        return ""

    text = ms._build_specification_text()

    # Strip the tool manifest and everything after it (tool list, retrieval
    # routing table). Those sections direct an MCP-connected model; a model
    # reached through the proxy has no tools.
    idx = text.find(_TOOL_MANIFEST_MARKER)
    if idx > 0:
        text = text[:idx].rstrip()

    # Strip the get_help() paragraph from the preamble for the same reason.
    idx = text.find(_HELP_PARAGRAPH_MARKER)
    if idx > 0:
        end = text.find("\n\n", idx)
        text = text[:idx].rstrip() + ("\n\n" + text[end + 2:].lstrip() if end > 0 else "")

    return text.strip()


def inject_specification(messages, spec_text):
    """Return a new messages list with the specification in the system slot.

    If the request already carries a string-content system message, the
    specification is prepended to it (client instructions stay intact and
    keep precedence by proximity). Otherwise a new system message is
    inserted at position 0. List-form (multi-part) system content is left
    untouched and a separate system message is inserted before it.
    """
    messages = list(messages)
    if (
        messages
        and isinstance(messages[0], dict)
        and messages[0].get("role") == "system"
        and isinstance(messages[0].get("content"), str)
    ):
        merged = dict(messages[0])
        merged["content"] = spec_text + "\n\n" + merged["content"]
        messages[0] = merged
    else:
        messages.insert(0, {"role": "system", "content": spec_text})
    return messages


# ==========================================================================
# CONVERSATION CAPTURE (local-only)
# ==========================================================================

def _flatten_content(content):
    """Reduce OpenAI message content (string or list of parts) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return "" if content is None else str(content)


def _last_user_text(messages):
    """Return the text of the most recent user message, or empty string."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return _flatten_content(msg.get("content")).strip()
    return ""


def derive_session_id(headers, messages):
    """Derive a stable session id for conversation grouping.

    Prefers the client-supplied `x-session-id` header (sanitized). Falls
    back to a hash of the first user message, which is stable across the
    turns of a stateless multi-turn client that resends history.
    """
    header = (headers.get(SESSION_HEADER) or "").strip()
    if header:
        return re.sub(r"[^A-Za-z0-9_.-]", "-", header)[:64]
    first_user = next(
        (m for m in messages if isinstance(m, dict) and m.get("role") == "user"),
        None,
    )
    seed = _flatten_content(first_user.get("content")) if first_user else ""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class ConversationRecorder:
    """Writes proxied exchanges to the standard conversation schema.

    Rows land in the same `conversations` / `messages` tables the importers
    write, with source='proxy', so `baselayer extract` picks proxied
    conversations up with no special handling. Scope resolution happens at
    extraction time via SCOPE_SOURCE_MAPPING ('proxy' -> 'personal').

    Each request records only the newest user turn plus the assistant
    reply. Stateless clients resend the full history every turn; recording
    only the new turn reconstructs the conversation without duplication.

    All writes are local SQLite (WAL mode, safe alongside pipeline scripts).
    Nothing here performs network I/O.
    """

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DATABASE_FILE
        if not self.db_path.exists():
            from baselayer.init_database import init_database
            init_database(self.db_path)

    def record_exchange(self, session_id, messages, assistant_text, model=None):
        """Record one user/assistant exchange. Returns the conversation id."""
        user_text = _last_user_text(messages)
        assistant_text = (assistant_text or "").strip()
        if not user_text and not assistant_text:
            return None

        conv_id = f"proxy-{session_id}"
        now = time.time()
        title = (user_text or "Proxy conversation").splitlines()[0][:80]
        if model:
            title = f"{title} [{model}]" if len(title) <= 60 else title

        with contextlib.closing(get_db(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO conversations
                    (id, title, created_at, updated_at, message_count, source)
                    VALUES (?, ?, ?, ?, 0, 'proxy')
                    """,
                    (conv_id, title, now, now),
                )
                row = conn.execute(
                    "SELECT COALESCE(MAX(sequence_order), -1) FROM messages "
                    "WHERE conversation_id = ?",
                    (conv_id,),
                ).fetchone()
                seq = row[0] + 1
                for role, text in (("user", user_text), ("assistant", assistant_text)):
                    if not text:
                        continue
                    conn.execute(
                        """
                        INSERT INTO messages
                        (id, conversation_id, parent_id, role, content_text,
                         content_type, created_at, sequence_order)
                        VALUES (?, ?, NULL, ?, ?, 'text', ?, ?)
                        """,
                        (str(uuid.uuid4()), conv_id, role, text, now, seq),
                    )
                    seq += 1
                conn.execute(
                    """
                    UPDATE conversations
                    SET message_count = (SELECT COUNT(*) FROM messages
                                         WHERE conversation_id = ?),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (conv_id, now, conv_id),
                )
        return conv_id


# ==========================================================================
# RESPONSE PARSING
# ==========================================================================

def _extract_completion_text(payload):
    """Pull the assistant text out of a non-streaming completion response."""
    try:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return _flatten_content(message.get("content"))
    except AttributeError:
        return ""


def _extract_stream_text(raw):
    """Reassemble the assistant text from buffered SSE bytes."""
    parts = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue  # skips comments like ": OPENROUTER PROCESSING"
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        for choice in obj.get("choices", []):
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                parts.append(content)
    return "".join(parts)


# ==========================================================================
# HTTP HANDLERS
# ==========================================================================

def _error_response(status, message):
    """OpenAI-style error body so existing clients surface it cleanly."""
    return web.json_response(
        {"error": {"message": message, "type": "baselayer_proxy_error", "code": status}},
        status=status,
    )


def _record(app, session_id, messages, assistant_text, model):
    """Capture an exchange if recording is enabled. Never raises."""
    recorder = app.get(K_RECORDER)
    if recorder is None:
        return
    try:
        recorder.record_exchange(session_id, messages, assistant_text, model=model)
    except Exception as exc:  # capture must never break the response path
        logger.warning("capture failed: %s", exc)


async def handle_chat_completions(request):
    """POST /v1/chat/completions: inject, forward, relay, record."""
    app = request.app

    api_key = app[K_API_KEY]
    if not api_key:
        return _error_response(
            401,
            "OPENROUTER_API_KEY is not set. Export it before starting the "
            "proxy: export OPENROUTER_API_KEY=sk-or-...",
        )

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response(400, "Request body is not valid JSON.")
    if not isinstance(body, dict):
        return _error_response(400, "Request body must be a JSON object.")

    original_messages = body.get("messages") or []
    if app[K_DEFAULT_MODEL] and not body.get("model"):
        body["model"] = app[K_DEFAULT_MODEL]

    # Injection: server flag AND per-request header both have to allow it.
    header_off = (request.headers.get(INJECT_HEADER) or "").strip().lower() == "off"
    if app[K_INJECT] and app[K_INJECT_TEXT] and not header_off:
        body["messages"] = inject_specification(original_messages, app[K_INJECT_TEXT])

    session_id = derive_session_id(request.headers, original_messages)
    model = body.get("model")
    upstream_url = app[K_UPSTREAM] + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    session = app[K_CLIENT_SESSION]

    try:
        if body.get("stream"):
            return await _forward_streaming(
                request, session, upstream_url, headers, body,
                session_id, original_messages, model,
            )
        return await _forward_non_streaming(
            request, session, upstream_url, headers, body,
            session_id, original_messages, model,
        )
    except aiohttp.ClientError as exc:
        return _error_response(502, f"Could not reach OpenRouter: {exc}")


async def _forward_non_streaming(request, session, url, headers, body,
                                 session_id, original_messages, model):
    """Forward a non-streaming request and relay the JSON response."""
    async with session.post(url, json=body, headers=headers) as resp:
        payload = await resp.read()

    if resp.status == 200:
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = {}
        _record(request.app, session_id, original_messages,
                _extract_completion_text(parsed), model)

    return web.Response(
        body=payload,
        status=resp.status,
        content_type="application/json",
    )


async def _forward_streaming(request, session, url, headers, body,
                             session_id, original_messages, model):
    """Forward a streaming request, relaying SSE chunks as they arrive.

    Chunks are passed through unmodified and buffered so the assistant
    text can be reassembled for capture after the stream completes.
    """
    async with session.post(url, json=body, headers=headers) as resp:
        if resp.status != 200:
            payload = await resp.read()
            return web.Response(
                body=payload,
                status=resp.status,
                content_type="application/json",
            )

        stream_resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await stream_resp.prepare(request)

        buffered = bytearray()
        async for chunk in resp.content.iter_any():
            buffered.extend(chunk)
            await stream_resp.write(chunk)

        # Record before EOF so capture is complete when the client finishes
        # reading. Recording is a few local SQLite writes (milliseconds).
        _record(request.app, session_id, original_messages,
                _extract_stream_text(bytes(buffered)), model)

        await stream_resp.write_eof()
        return stream_resp


async def handle_models(request):
    """GET /v1/models: passthrough to OpenRouter (no key required)."""
    app = request.app
    headers = {}
    if app[K_API_KEY]:
        headers["Authorization"] = f"Bearer {app[K_API_KEY]}"
    try:
        async with app[K_CLIENT_SESSION].get(
            app[K_UPSTREAM] + "/models", headers=headers
        ) as resp:
            payload = await resp.read()
            return web.Response(
                body=payload,
                status=resp.status,
                content_type="application/json",
            )
    except aiohttp.ClientError as exc:
        return _error_response(502, f"Could not reach OpenRouter: {exc}")


# ==========================================================================
# APP FACTORY AND RUNNER
# ==========================================================================

async def _client_session_ctx(app):
    """Own one aiohttp ClientSession for the app's lifetime."""
    app[K_CLIENT_SESSION] = aiohttp.ClientSession()
    yield
    await app[K_CLIENT_SESSION].close()


def create_app(*, upstream_base=None, api_key=None, inject=True, capture=True,
               db_path=None, default_model=None, inject_text=None):
    """Build the proxy web application.

    Args:
        upstream_base: Upstream API base URL (default: OpenRouter).
        api_key: Upstream API key. Defaults to OPENROUTER_API_KEY from env.
        inject: Server-level injection switch (--no-inject sets False).
        capture: Local conversation capture switch (--no-capture sets False).
        db_path: Capture database path (default: the pipeline database).
        default_model: Model applied when the request omits one.
        inject_text: Pre-built specification text (tests use this; normal
            operation assembles it via build_injection_text()).
    """
    app = web.Application()
    app[K_UPSTREAM] = (upstream_base or OPENROUTER_BASE_URL).rstrip("/")
    app[K_API_KEY] = get_openrouter_api_key() if api_key is None else api_key
    app[K_INJECT] = inject
    app[K_DEFAULT_MODEL] = default_model
    if inject:
        app[K_INJECT_TEXT] = build_injection_text() if inject_text is None else inject_text
    else:
        app[K_INJECT_TEXT] = ""
    app[K_RECORDER] = ConversationRecorder(db_path) if capture else None
    app.cleanup_ctx.append(_client_session_ctx)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_get("/v1/models", handle_models)
    return app


def run_proxy(host=None, port=None, inject=True, capture=True,
              default_model=None, db_path=None):
    """Start the proxy server (blocking). Entry point for `baselayer proxy`."""
    host = host or PROXY_HOST
    port = port or PROXY_PORT
    app = create_app(
        inject=inject, capture=capture,
        db_path=db_path, default_model=default_model,
    )

    print(f"Base Layer proxy listening on http://{host}:{port}/v1")
    print(f"  Upstream: {app[K_UPSTREAM]}")

    if not app[K_API_KEY]:
        print("  WARNING: OPENROUTER_API_KEY is not set. Chat requests will "
              "return 401 until you export it and restart.")

    if not inject:
        print("  Injection: OFF (--no-inject)")
    elif not app[K_INJECT_TEXT]:
        print("  Injection: OFF (no specification layers authored, or serving "
              "disabled via `baselayer serve disable`)")
    else:
        approx_tokens = len(app[K_INJECT_TEXT]) // 4
        print(f"  Injection: ON (~{approx_tokens} tokens per request; "
              f"suppress per request with header {INJECT_HEADER}: off)")

    if capture:
        recorder = app[K_RECORDER]
        print(f"  Capture: ON, LOCAL-ONLY -> {recorder.db_path} "
              "(source='proxy'; disable with --no-capture)")
    else:
        print("  Capture: OFF (--no-capture)")

    web.run_app(app, host=host, port=port, print=None)


def main():
    run_proxy()


if __name__ == "__main__":
    main()
