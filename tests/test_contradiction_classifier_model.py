"""The tension classifier in `baselayer run` step 5d stays on Haiku 4.5.

classify_pair_haiku used config.EXTRACTION_API_MODEL, so moving extraction to Haiku 5.5 would
have moved it too, without a decision or a measurement behind it: its 300-token budget is sized
for a model that does not think, and every exception there returns CONSISTENT. It is pinned.
"""
from types import SimpleNamespace


def test_the_classifier_does_not_follow_the_extraction_default(monkeypatch):
    import baselayer.detect_contradictions as dc
    seen = {}

    def fake_call_api(**kw):
        seen.update(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(
            type="text", text='{"verdict": "TENSION", "reasoning": "r", "confidence": 0.7}')])
    import baselayer.api_client as ac
    monkeypatch.setattr(ac, "call_api", fake_call_api)
    monkeypatch.setattr(dc, "EXTRACTION_API_MODEL", "claude-haiku-5-5", raising=False)
    out = dc.classify_pair_haiku("a", "b", "values", "values")
    assert seen["model"] == "claude-haiku-4-5-20251001" == dc.CONTRADICTION_CLASSIFIER_MODEL
    assert out["verdict"] == "TENSION"
