"""Request shape and response handling of the distillation authoring call. No API calls.

Claude Opus 5.5 rejects forced tool use (tool_choice "tool"/"any" -> 400), returns thinking
blocks before content, and can stop with stop_reason == "refusal". These tests pin the
behaviour of `call_structured` against a scripted fake client so the model-agnostic call shape
cannot regress silently. The first test fails on the pre-5.5 code, which sent
tool_choice={"type": "tool", ...}.
"""
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import author_from_package as afp

SUPPLIED = {"a1b2c3d4", "b2c3d4e5"}


def _usage():
    return NS(input_tokens=100, output_tokens=50)


def _tool_msg(claims, thinking_first=True):
    blocks = []
    if thinking_first:
        blocks.append(NS(type="thinking", thinking=""))
    blocks.append(NS(type="tool_use", name="emit_layer",
                     input={"layer": "anchors", "preamble": "", "claims": claims}))
    return NS(content=blocks, stop_reason="tool_use", stop_details=None, usage=_usage())


def _claim(cid="A1", fids=("a1b2c3d4",)):
    return {"id": cid, "name": "X", "statement": "s", "active_when": "",
            "fact_ids": list(fids), "contested": False}


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        return _Stream(self.responses.pop(0))


def _run(cl, **kw):
    return afp.call_structured(cl, "claude-opus-5-5", "PROMPT", afp.LAYER_SCHEMA, SUPPLIED, **kw)


def test_never_forces_tool_choice_and_tool_is_strict():
    cl = FakeClient([_tool_msg([_claim()])])
    _run(cl)
    call = cl.calls[0]
    assert call["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert call["tools"][0]["strict"] is True
    assert "eager_input_streaming" not in call["tools"][0]
    assert "thinking" not in call
    assert "emit_layer" in call["system"]


def test_effort_is_sent_explicitly():
    cl = FakeClient([_tool_msg([_claim()])])
    _run(cl, effort="low")
    assert cl.calls[0]["output_config"] == {"effort": "low"}
    cl = FakeClient([_tool_msg([_claim()])])
    _run(cl)
    assert cl.calls[0]["output_config"] == {"effort": "high"}


@pytest.mark.parametrize("effort", [None, ""])
def test_missing_effort_refuses_rather_than_defaulting(effort):
    cl = FakeClient([_tool_msg([_claim()])])
    with pytest.raises(ValueError, match="effort"):
        _run(cl, effort=effort)
    assert cl.calls == []


def test_two_tool_calls_rejected_not_truncated_to_first():
    two = NS(content=[NS(type="tool_use", name="emit_layer",
                         input={"layer": "anchors", "preamble": "", "claims": [_claim("A1")]}),
                      NS(type="tool_use", name="emit_layer",
                         input={"layer": "anchors", "preamble": "", "claims": [_claim("A2")]})],
             stop_reason="tool_use", stop_details=None, usage=_usage())
    cl = FakeClient([two, _tool_msg([_claim("A1"), _claim("A2")])])
    data, _, _ = _run(cl)
    assert len(cl.calls) == 2
    assert "exactly ONE" in cl.calls[1]["messages"][0]["content"]
    assert [c["id"] for c in data["claims"]] == ["A1", "A2"]


def test_thinking_block_first_still_parses():
    cl = FakeClient([_tool_msg([_claim()], thinking_first=True)])
    data, i, o = _run(cl)
    assert data["claims"][0]["fact_ids"] == ["a1b2c3d4"]


@pytest.mark.parametrize("details", [
    {"category": "cyber", "explanation": "declined"},          # shape on SDK 0.79.0 (extra field)
    NS(category="cyber", explanation="declined"),              # shape once the SDK types it
])
def test_refusal_raises_after_one_call(details):
    refused = NS(content=[], stop_reason="refusal", stop_details=details, usage=_usage())
    cl = FakeClient([refused, _tool_msg([_claim()])])
    with pytest.raises(afp.AuthoringRefused, match="category=cyber"):
        _run(cl)
    assert len(cl.calls) == 1


def test_max_tokens_raises_without_retry():
    trunc = NS(content=[NS(type="thinking", thinking="")], stop_reason="max_tokens",
               stop_details=None, usage=_usage())
    cl = FakeClient([trunc, _tool_msg([_claim()])])
    with pytest.raises(RuntimeError, match="TRUNCATED"):
        _run(cl)
    assert len(cl.calls) == 1


def test_missing_tool_call_consumes_one_attempt_then_succeeds():
    prose = NS(content=[NS(type="thinking", thinking=""), NS(type="text", text="here it is")],
               stop_reason="end_turn", stop_details=None, usage=_usage())
    cl = FakeClient([prose, _tool_msg([_claim()])])
    data, _, _ = _run(cl)
    assert len(cl.calls) == 2
    assert "did not call the emit_layer tool" in cl.calls[1]["messages"][0]["content"]
    assert len(cl.calls[1]["messages"]) == 1  # fresh single-turn re-ask, no replayed thinking


def test_missing_tool_call_every_time_fails_within_budget():
    prose = NS(content=[NS(type="text", text="no")], stop_reason="end_turn",
               stop_details=None, usage=_usage())
    cl = FakeClient([prose, prose, prose, prose])
    with pytest.raises(RuntimeError, match="did not call"):
        _run(cl, tries=3)
    assert len(cl.calls) == 3


def test_empty_fact_ids_still_rejected():
    naked = _tool_msg([_claim(fids=())])
    cl = FakeClient([naked, naked, naked])
    with pytest.raises(RuntimeError, match="CITATION GATE FAILED"):
        _run(cl, tries=3)


def test_fabricated_only_ids_rejected():
    bogus = _tool_msg([_claim(fids=("deadbeef",))])
    cl = FakeClient([bogus, bogus, bogus])
    with pytest.raises(RuntimeError, match="CITATION GATE FAILED"):
        _run(cl, tries=3)
