"""
Parse extraction responses by content-block type, not by position.

On any 5-generation model with thinking on, content[0] is a thinking block and
`response.content[0].text` either raises or reads the wrong block. The extractor
must read the text blocks, and must count a refusal or a max_tokens stop instead
of retrying it into a silent None.

Fake clients only; no API calls.
"""

import json
from types import SimpleNamespace

import pytest


FACTS = {"facts": [{"subject": "user", "predicate": "values", "object": "plain speech",
                    "category": "value", "confidence": 0.9}]}


def _block(kind, **kw):
    return SimpleNamespace(type=kind, **kw)


def _response(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class _FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self.response


def _install(monkeypatch, response):
    import baselayer.extract_facts as ef
    msgs = _FakeMessages(response)
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: SimpleNamespace(messages=msgs))
    getattr(ef, "reset_response_failures", lambda: None)()
    return ef, msgs


def test_thinking_block_first_is_skipped(monkeypatch):
    # thinking blocks carry .thinking, not .text; a positional read raises here
    resp = _response([_block("thinking", thinking="let me see"),
                      _block("text", text=json.dumps(FACTS))])
    ef, _ = _install(monkeypatch, resp)
    assert ef.call_anthropic("p", retries=0) == FACTS


def test_multiple_text_blocks_are_joined(monkeypatch):
    raw = json.dumps(FACTS)
    resp = _response([_block("text", text=raw[:20]), _block("text", text=raw[20:])])
    ef, _ = _install(monkeypatch, resp)
    assert ef.call_anthropic("p", retries=0) == FACTS


def test_refusal_is_counted_and_not_retried(monkeypatch):
    resp = _response([], stop_reason="refusal")
    ef, msgs = _install(monkeypatch, resp)
    assert ef.call_anthropic("p", retries=3) is None
    assert msgs.calls == 1
    assert ef.response_failures()["refusal"] == 1


def test_max_tokens_stop_is_counted(monkeypatch):
    resp = _response([_block("text", text='{"facts": [{"subject": "us')], stop_reason="max_tokens")
    ef, msgs = _install(monkeypatch, resp)
    assert ef.call_anthropic("p", retries=3) is None
    assert msgs.calls == 1  # a truncated answer does not get better on retry
    assert ef.response_failures()["max_tokens"] == 1


def test_response_text_helper_directly():
    from baselayer.extract_facts import response_text
    resp = _response([_block("thinking", thinking="x"), _block("text", text=" {} ")])
    assert response_text(resp) == "{}"


def test_batch_parse_uses_block_types():
    from baselayer.batch_extract import _parse_batch_message
    msg = _response([_block("thinking", thinking="hmm"), _block("text", text="```json\n" + json.dumps(FACTS) + "\n```")])
    assert _parse_batch_message(msg) == FACTS


def test_batch_parse_raises_on_refusal():
    from baselayer.batch_extract import _parse_batch_message
    from baselayer.extract_facts import ExtractionResponseError
    with pytest.raises(ExtractionResponseError) as e:
        _parse_batch_message(_response([], stop_reason="refusal"))
    assert e.value.reason == "refusal"
