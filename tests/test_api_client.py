"""
Tests for api_client.py — singleton Anthropic client, call_api() retry logic,
and embed_texts() batching.

All tests run without API keys or external services.
"""

import pytest
import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock



# ============================================================
# SINGLETON PATTERN
# ============================================================

class TestGetAnthropicClient:
    """Test singleton pattern for Anthropic client."""

    def setup_method(self):
        import baselayer.api_client as mod
        self._old = mod._anthropic_client
        mod._anthropic_client = None

    def teardown_method(self):
        import baselayer.api_client as mod
        mod._anthropic_client = self._old

    def test_returns_client_instance(self):
        import baselayer.api_client as mod
        mock_client = MagicMock()
        with patch("anthropic.Anthropic", return_value=mock_client):
            client = mod.get_anthropic_client()
        assert client is mock_client

    def test_singleton_returns_same_instance(self):
        import baselayer.api_client as mod
        mock_client = MagicMock()
        with patch("anthropic.Anthropic", return_value=mock_client) as ctor:
            c1 = mod.get_anthropic_client()
            c2 = mod.get_anthropic_client()
        assert c1 is c2
        assert ctor.call_count == 1

    def test_passes_max_retries_and_timeout(self):
        import baselayer.api_client as mod
        with patch("anthropic.Anthropic", return_value=MagicMock()) as ctor:
            mod.get_anthropic_client(max_retries=5, timeout=60.0)
        ctor.assert_called_once_with(max_retries=5, timeout=60.0)

    def test_subsequent_calls_ignore_args(self):
        import baselayer.api_client as mod
        mock_client = MagicMock()
        with patch("anthropic.Anthropic", return_value=mock_client) as ctor:
            mod.get_anthropic_client(max_retries=1, timeout=10.0)
            mod.get_anthropic_client(max_retries=99, timeout=999.0)
        assert ctor.call_count == 1

    def test_raises_import_error_if_anthropic_missing(self):
        import baselayer.api_client as mod
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("no module named 'anthropic'")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="anthropic package not installed"):
                mod.get_anthropic_client()

    def test_thread_safety(self):
        import baselayer.api_client as mod
        mock_client = MagicMock()
        results = []
        with patch("anthropic.Anthropic", return_value=mock_client):
            def get_client():
                results.append(mod.get_anthropic_client())
            threads = [threading.Thread(target=get_client) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        assert all(r is mock_client for r in results)


# ============================================================
# CALL_API RETRY LOGIC
# ============================================================

class TestCallApi:
    """Test call_api() retry logic and error handling."""

    def setup_method(self):
        import baselayer.api_client as mod
        self._old = mod._anthropic_client
        self.mock_client = MagicMock()
        mod._anthropic_client = self.mock_client

    def teardown_method(self):
        import baselayer.api_client as mod
        mod._anthropic_client = self._old

    def _make_response(self, text="ok", in_tok=10, out_tok=5):
        resp = MagicMock()
        resp.content = [MagicMock(text=text)]
        resp.usage = MagicMock(input_tokens=in_tok, output_tokens=out_tok)
        return resp

    def test_successful_call(self):
        from baselayer.api_client import call_api
        resp = self._make_response("hello")
        self.mock_client.messages.create.return_value = resp
        result = call_api(model="claude-haiku-4-5-20251001",
                          messages=[{"role": "user", "content": "hi"}])
        assert result is resp

    def test_passes_system_prompt(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}],
                 system="You are helpful.")
        kwargs = self.mock_client.messages.create.call_args[1]
        assert kwargs["system"] == "You are helpful."

    def test_no_system_prompt_omitted(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}])
        kwargs = self.mock_client.messages.create.call_args[1]
        assert "system" not in kwargs

    def test_timeout_passed_when_provided(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}], timeout=30)
        kwargs = self.mock_client.messages.create.call_args[1]
        assert kwargs["timeout"] == 30

    def test_timeout_omitted_when_none(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}])
        kwargs = self.mock_client.messages.create.call_args[1]
        assert "timeout" not in kwargs

    def test_retries_on_rate_limit(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.RateLimitError(
            message="rate limited", response=MagicMock(status_code=429), body={})
        self.mock_client.messages.create.side_effect = error
        with patch("time.sleep"):
            with pytest.raises(anthropic.RateLimitError):
                call_api(model="claude-haiku-4-5-20251001",
                         messages=[{"role": "user", "content": "hi"}])
        assert self.mock_client.messages.create.call_count == 4

    def test_retries_on_server_500(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIStatusError(
            message="server error", response=MagicMock(status_code=500), body={})
        resp = self._make_response()
        self.mock_client.messages.create.side_effect = [error, resp]
        with patch("time.sleep"):
            result = call_api(model="claude-haiku-4-5-20251001",
                              messages=[{"role": "user", "content": "hi"}])
        assert result is resp

    def test_retries_on_server_502(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIStatusError(
            message="bad gateway", response=MagicMock(status_code=502), body={})
        resp = self._make_response()
        self.mock_client.messages.create.side_effect = [error, resp]
        with patch("time.sleep"):
            result = call_api(model="claude-haiku-4-5-20251001",
                              messages=[{"role": "user", "content": "hi"}])
        assert result is resp

    def test_retries_on_server_529(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIStatusError(
            message="overloaded", response=MagicMock(status_code=529), body={})
        resp = self._make_response()
        self.mock_client.messages.create.side_effect = [error, resp]
        with patch("time.sleep"):
            result = call_api(model="claude-haiku-4-5-20251001",
                              messages=[{"role": "user", "content": "hi"}])
        assert result is resp

    def test_no_retry_on_400_error(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIStatusError(
            message="bad request", response=MagicMock(status_code=400), body={})
        self.mock_client.messages.create.side_effect = error
        with pytest.raises(anthropic.APIStatusError):
            call_api(model="claude-haiku-4-5-20251001",
                     messages=[{"role": "user", "content": "hi"}])
        assert self.mock_client.messages.create.call_count == 1

    def test_no_retry_on_401_error(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIStatusError(
            message="unauthorized", response=MagicMock(status_code=401), body={})
        self.mock_client.messages.create.side_effect = error
        with pytest.raises(anthropic.APIStatusError):
            call_api(model="claude-haiku-4-5-20251001",
                     messages=[{"role": "user", "content": "hi"}])
        assert self.mock_client.messages.create.call_count == 1

    def test_retries_on_connection_error(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIConnectionError(request=MagicMock())
        resp = self._make_response()
        self.mock_client.messages.create.side_effect = [error, error, resp]
        with patch("time.sleep"):
            result = call_api(model="claude-haiku-4-5-20251001",
                              messages=[{"role": "user", "content": "hi"}])
        assert result is resp

    def test_connection_error_exhausts_retries(self):
        import anthropic
        from baselayer.api_client import call_api
        error = anthropic.APIConnectionError(request=MagicMock())
        self.mock_client.messages.create.side_effect = error
        with patch("time.sleep"):
            with pytest.raises(anthropic.APIConnectionError):
                call_api(model="claude-haiku-4-5-20251001",
                         messages=[{"role": "user", "content": "hi"}])

    def test_no_retry_on_unexpected_exception(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.side_effect = ValueError("bad")
        with pytest.raises(ValueError):
            call_api(model="claude-haiku-4-5-20251001",
                     messages=[{"role": "user", "content": "hi"}])
        assert self.mock_client.messages.create.call_count == 1

    def test_caller_tag_accepted(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}],
                 caller="test_caller")

    def test_default_temperature_zero(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}])
        kwargs = self.mock_client.messages.create.call_args[1]
        assert kwargs["temperature"] == 0

    def test_default_max_tokens(self):
        from baselayer.api_client import call_api
        self.mock_client.messages.create.return_value = self._make_response()
        call_api(model="claude-haiku-4-5-20251001",
                 messages=[{"role": "user", "content": "hi"}])
        kwargs = self.mock_client.messages.create.call_args[1]
        assert kwargs["max_tokens"] == 4096


# ============================================================
# EMBEDDING MODEL SINGLETON
# ============================================================

class TestGetEmbeddingModel:
    def setup_method(self):
        import baselayer.api_client as mod
        self._old = mod._embedding_model
        mod._embedding_model = None

    def teardown_method(self):
        import baselayer.api_client as mod
        mod._embedding_model = self._old

    def test_singleton_caches_model(self):
        import baselayer.api_client as mod
        mock_model = MagicMock()
        mod._embedding_model = mock_model
        result = mod.get_embedding_model()
        assert result is mock_model


# ============================================================
# EMBED_TEXTS BATCHING
# ============================================================

class TestEmbedTexts:
    def setup_method(self):
        import baselayer.api_client as mod
        self._old = mod._embedding_model
        self.mock_model = MagicMock()
        mod._embedding_model = self.mock_model

    def teardown_method(self):
        import baselayer.api_client as mod
        mod._embedding_model = self._old

    def test_single_batch(self):
        import baselayer.api_client as mod
        import numpy as np
        self.mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
        result = mod.embed_texts(["hello", "world"], batch_size=64)
        assert len(result) == 2
        self.mock_model.encode.assert_called_once()

    def test_multiple_batches(self):
        import baselayer.api_client as mod
        import numpy as np
        # Return correct number of embeddings per batch
        self.mock_model.encode.side_effect = [
            np.array([[0.1, 0.2], [0.3, 0.4]]),  # batch 1: 2 items
            np.array([[0.5, 0.6], [0.7, 0.8]]),  # batch 2: 2 items
            np.array([[0.9, 1.0]]),                # batch 3: 1 item
        ]
        result = mod.embed_texts(["a", "b", "c", "d", "e"], batch_size=2)
        assert len(result) == 5
        assert self.mock_model.encode.call_count == 3

    def test_returns_none_when_model_unavailable(self):
        import baselayer.api_client as mod
        mod._embedding_model = None
        with patch.object(mod, "get_embedding_model", return_value=None):
            result = mod.embed_texts(["hello"])
        assert result is None

    def test_empty_list(self):
        import baselayer.api_client as mod
        result = mod.embed_texts([])
        assert result == []

    def test_show_progress_bar_disabled(self):
        import baselayer.api_client as mod
        import numpy as np
        self.mock_model.encode.return_value = np.array([[0.1]])
        mod.embed_texts(["hello"])
        _, kwargs = self.mock_model.encode.call_args
        assert kwargs.get("show_progress_bar") is False
