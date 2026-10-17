"""
Responses are read by block TYPE, never by position, at every live call site.

On a model with extended thinking on (the default on the 5 generation), the
first content block is a thinking block, which has no `.text`. A site that
reads `response.content[0].text` then raises, or reads the wrong block. Each
test here hands one site a THINKING-FIRST response and asserts it returns the
text block. Every test failed before the sites were changed.

No API calls: every client and call_api is faked.
"""

import json
import sys
import types
from pathlib import Path

import pytest


def _resp(text, *, stop="end_turn", thinking_first=True):
    blocks = [types.SimpleNamespace(type="text", text=text)]
    if thinking_first:
        blocks.insert(0, types.SimpleNamespace(type="thinking", thinking="weighing it", signature="s"))
    return types.SimpleNamespace(content=blocks, stop_reason=stop,
                                 usage=types.SimpleNamespace(input_tokens=10, output_tokens=20))


# ---------------------------------------------------------------- the helper

def test_response_text_reads_text_blocks_only():
    from baselayer.api_client import response_text
    r = _resp("hello")
    r.content.append(types.SimpleNamespace(type="text", text=" world"))
    assert response_text(r) == "hello world"


@pytest.mark.parametrize("resp,reason", [
    (types.SimpleNamespace(content=[], stop_reason="refusal"), "refusal"),
    (types.SimpleNamespace(content=[types.SimpleNamespace(type="thinking", thinking="x")],
                           stop_reason="end_turn"), "no_text"),
])
def test_response_text_raises_on_refusal_and_no_text(resp, reason):
    from baselayer.api_client import ResponseTextError, response_text
    with pytest.raises(ResponseTextError) as e:
        response_text(resp, caller="t")
    assert e.value.reason == reason


def test_no_positional_content_reads_remain_in_the_live_package():
    """A static backstop for the enumerate-call-sites rule: no live module reads
    `.content[0]`. archive/ and experiments/ are not shipped and are excluded."""
    import baselayer
    root = Path(baselayer.__file__).parent
    hits = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(("archive/", "experiments/")):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if ".content[0]" in code:
                hits.append(f"{rel}:{i}")
    assert hits == []


# ---------------------------------------------------------------- each site

def test_llm_provider_call_anthropic(monkeypatch):
    import baselayer.api_client as api
    from baselayer.llm_provider import _call_anthropic
    monkeypatch.setattr(api, "call_api", lambda **k: _resp("  provider text  "))
    assert _call_anthropic("p", "m", 100, 0)["text"] == "provider text"


def test_detect_contradictions_classify_pair(monkeypatch):
    import baselayer.api_client as api
    import baselayer.detect_contradictions as dc
    verdict = {"verdict": "TENSION", "reasoning": "r", "confidence": 0.7}
    monkeypatch.setattr(api, "call_api", lambda **k: _resp(json.dumps(verdict)))
    assert dc.classify_pair_haiku("a", "b", "values", "avoids") == verdict


def test_assemble_brief_call_claude(monkeypatch):
    from baselayer.assemble_brief import call_claude

    class Client:
        def __init__(self, api_key=None):
            self.messages = types.SimpleNamespace(create=lambda **k: _resp("brief answer"))

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=Client))
    assert call_claude("sys", [{"role": "user", "content": "hi"}], "key") == "brief answer"


def test_author_layers_generate_layer(monkeypatch):
    import baselayer.api_client as api
    import baselayer.author_layers as al
    monkeypatch.setattr(api, "call_api", lambda **k: _resp("  layer body  "))
    monkeypatch.setattr(al, "check_prompt_contamination", lambda text, layer: [])
    assert al.generate_layer("core", "prompt") == "layer body"


def test_author_layers_generate_layer_structured(monkeypatch):
    import baselayer.api_client as api
    import baselayer.author_layers as al
    parsed = {"predictions": [{"id": "P1"}]}
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **k: _resp(json.dumps(parsed))))
    monkeypatch.setattr(api, "get_anthropic_client", lambda *a, **k: client)
    assert al.generate_layer_structured("predictions", "prompt", {"type": "object"}) == parsed


def test_agent_pipeline_compose_first_call_and_retry(monkeypatch):
    """Both sites in compose_unified_brief: the first call and the
    decontamination retry. Storage is faked so nothing is written."""
    import baselayer.agent_pipeline as ap
    import baselayer.api_client as api
    import baselayer.author_layers as al
    replies = iter([_resp("first brief draft"), _resp("clean brief")])
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **k: next(replies)))
    monkeypatch.setattr(api, "get_anthropic_client", lambda *a, **k: client)
    flags = iter([["template phrase"], []])
    monkeypatch.setattr(al, "check_prompt_contamination", lambda text, layer: next(flags))
    stored = []
    monkeypatch.setattr(ap, "store_unified_brief", lambda run_dir, text: stored.append(text))
    # source_facts_text given, so no database is read
    out = ap.compose_unified_brief(layer_texts={"anchors": "A", "core": "C", "predictions": "P"},
                                   source_facts_text="")
    assert out == "clean brief" and stored == ["clean brief"]
