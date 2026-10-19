"""An AUDN call that fails is counted, not silently turned into an ADD.

make_audn_decision asks the model only when a candidate is very similar to a stored fact
(a likely duplicate). When that call returned None (an API error swallowed by call_anthropic,
a refusal, an unparseable reply) or a reply with no `action`, the code fell through to the
"moderate similarity" branch and returned ADD: a possible duplicate stored, with nothing in
the run record to say the adjudication never happened.

Now the failure is counted in response_failures (which the run record carries) and the
decision says so. The fact is still kept (ADD): a missed dedup is visible and repairable, a
dropped fact is not. And call_anthropic counts the API error it swallows.
"""
from types import SimpleNamespace

import pytest

SIMILAR = [{"fact_text": "plans the week on Sunday", "similarity": 0.95, "fact_id": "f1"}]


@pytest.mark.parametrize("reply", [None, {}, {"reasoning": "no action key"}])
def test_a_failed_audn_call_is_counted_and_marked(monkeypatch, reply):
    import baselayer.extract_facts as ef
    ef.reset_response_failures()
    monkeypatch.setattr(ef, "call_llm", lambda prompt, schema=None, **k: reply)
    d = ef.make_audn_decision("plans the week on Sunday evening", SIMILAR)
    assert ef.response_failures().get("audn_no_decision") == 1
    assert d["action"] == "ADD"                 # kept, not dropped
    assert d.get("audn_failed") is True
    assert "AUDN" in d["reasoning"]


def test_a_real_audn_decision_is_not_counted_as_a_failure(monkeypatch):
    import baselayer.extract_facts as ef
    ef.reset_response_failures()
    monkeypatch.setattr(ef, "call_llm", lambda prompt, schema=None, **k: {"action": "NOOP"})
    d = ef.make_audn_decision("plans the week on Sunday evening", SIMILAR)
    assert d["action"] == "NOOP"
    assert "audn_no_decision" not in ef.response_failures()


def test_a_moderate_similarity_add_makes_no_call_and_counts_nothing(monkeypatch):
    import baselayer.extract_facts as ef
    ef.reset_response_failures()
    monkeypatch.setattr(ef, "call_llm", lambda *a, **k: pytest.fail("no call expected"))
    d = ef.make_audn_decision("x", [{"fact_text": "y", "similarity": 0.5}])
    assert d["action"] == "ADD" and not d.get("audn_failed")
    assert ef.response_failures() == {}


def test_call_anthropic_counts_the_api_error_it_swallows(monkeypatch):
    import baselayer.extract_facts as ef

    class Failing:
        def create(self, **kw):
            raise RuntimeError("400 temperature is deprecated for this model")
    ef.reset_response_failures()
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: SimpleNamespace(messages=Failing()))
    assert ef.call_anthropic("p", retries=0) is None
    assert ef.response_failures().get("api_error") == 1
