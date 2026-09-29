"""
AUDN NOOP on the turn path keeps the duplicate's evidence. A fact stated again in another
turn or conversation is not stored twice, but its own-voice spans are appended to the
surviving fact (deduplicated on turn id and normalised span), so recurrence is recorded as
independent grounding instead of being discarded. Counted as `noop_spans_merged`.
"""

import json

from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    _fact, _facts, _records, _seed, env)

A = "I always write the summary before the details."
B = "Honestly I always write the summary before the details, every time."


def _one_turn(text):
    return [(0, "subject", "own_typed", "user", text)]


def _setup(env, monkeypatch, convs):
    for cid, text in convs:
        _seed(env, conv=cid, turns=_one_turn(text))
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")

    def call(prompt, schema=None, retries=None, max_tokens=None):
        if schema is env.ef.AUDN_SCHEMA:
            return {"action": "NOOP", "reasoning": "duplicate"}
        span = "I always write the summary before the details"
        return {"facts": [_fact("summary before details", [("S1", span)],
                                predicate="practices", category="habit")]}
    monkeypatch.setattr(env.ef, "call_llm", call)

    def similar(text, collection, embed_model, top_k=5, contract_version=None, grounding=None,
                conn=None):
        c = env.get_db()
        rows = c.execute("SELECT id, fact_text FROM memory_facts ORDER BY created_at").fetchall()
        c.close()
        return [{"fact_id": rows[0][0], "fact_text": rows[0][1], "similarity": 0.97}] if rows else []
    monkeypatch.setattr(env.ef, "find_similar_facts", similar)


def test_noop_appends_the_duplicates_spans_to_the_survivor(env, monkeypatch):
    _setup(env, monkeypatch, [("conv-a", A), ("conv-b", B)])
    env.ef.run_extraction()
    facts = _facts(env)
    assert len(facts) == 1
    spans = json.loads(facts[0]["evidence_spans"])
    assert [s["turn_id"] for s in spans] == ["conv-a:0", "conv-b:0"]
    assert all(s["evidence_kind"] == "prose" for s in spans)
    assert facts[0]["source_turn_id"] == "conv-a:0"          # the first span is unchanged
    rec = _records(env)[-1]
    assert rec["audn"]["NOOP"] == 1
    assert rec["counts"]["noop_spans_merged"] == 1


def test_a_span_already_held_is_not_appended_twice(env, monkeypatch):
    _setup(env, monkeypatch, [("conv-a", A), ("conv-b", B), ("conv-c", B)])
    env.ef.run_extraction()
    spans = json.loads(_facts(env)[0]["evidence_spans"])
    assert [s["turn_id"] for s in spans] == ["conv-a:0", "conv-b:0", "conv-c:0"]
    _setup_again = _records(env)[-1]
    assert _setup_again["counts"]["noop_spans_merged"] == 2


def test_merged_spans_still_regate_in_verification(env, monkeypatch):
    """Every stored span, merged ones included, must pass verification's span re-check,
    which looks each span's turn up by its own id, not by the fact's conversation."""
    from baselayer.verification.corpus import Corpus
    _setup(env, monkeypatch, [("conv-a", A), ("conv-b", B)])
    env.ef.run_extraction()
    conn = env.get_db()
    corpus = Corpus(conn, {})
    f = corpus.fact(_facts(env)[0]["id"])
    v = corpus.voice(f)
    assert v["mode"] == "turn_contract" and v["gate"] == [] and v["own"] is True
    assert v["turn_ids"] == ["conv-a:0", "conv-b:0"]
