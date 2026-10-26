"""
The mechanical subject check (TURN_CONTRACT.md §5, subject resolution).

The gate proves grounding, not reference. Rule since 2026-10-26: the subject under a
configured name or a generic form becomes `user`; any other subject is KEPT. When
every span is the subject's own turn and no span names the other subject (its name,
a configured alias, case-insensitive, with or without a surname), the subject is
still kept, and counted (`subject_unnamed`), never silent.

Before 2026-10-26 such a subject was rewritten to `user`. That put other people's
actions into the person's facts and, on a policy extraction of Zitkala-Sa's essays,
turned a guest into the host (tests/test_gate_zitkala.py). A wrong subject that is
not `user` stays out of the person's specification; a wrong `user` goes into it.
"""

import pytest

import baselayer.turn_contract as tc

CONV = "conv-s"


def _chunk():
    turns = [
        tc.Turn(f"{CONV}:0", CONV, "other", "other_person", "What does your team work on?"),
        tc.Turn(f"{CONV}:1", CONV, "subject", "own_dictated",
                "We build scheduling software for small clinics."),
        tc.Turn(f"{CONV}:2", CONV, "subject", "own_dictated",
                "Sam said the launch slipped a week. My wife is a doctor at the clinic. "
                "Sammy called twice about the contract. The company ships weekly now."),
    ]
    return tc.build_chunks(turns, 5000, context_budget=400, context_max_turns=3)[0]


REF = tc.Referent(names=("Dana Reyes", "Dana"), aliases={"sam ortiz": ("Sammy",)})


def _fact(subject, turn, span):
    return {"subject": subject, "predicate": "works_at", "object": "a software company",
            "category": "project", "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn_id": turn, "span": span}]}


def _gate(*facts, referent=REF):
    return tc.gate_facts(list(facts), _chunk(), referent=referent)


def test_other_subject_absent_from_the_spans_is_kept_and_counted():
    g = _gate(_fact("Sam Ortiz", f"{CONV}:1", "We build scheduling software"))
    assert [a["subject"] for a in g.accepted] == ["Sam Ortiz"]
    assert g.subject_unnamed == {"Sam Ortiz": 1}
    assert g.subject_referent == 0


@pytest.mark.parametrize("subject,span", [
    ("Sam Ortiz", "Sam said the launch slipped"),          # surname missing in the span
    ("sam ortiz", "Sam said the launch slipped"),          # case-insensitive
    ("Sam Ortiz", "Sammy called twice about the contract"),  # configured alias
    ("the user's wife", "My wife is a doctor"),            # role subject, possessive stripped
    ("The company", "The company ships weekly now."),       # determiner stripped
    ("colleague (Sam)", "Sam said the launch slipped"),    # parenthetical name
])
def test_other_subject_named_in_a_span_is_kept_and_not_counted(subject, span):
    g = _gate(_fact(subject, f"{CONV}:2", span))
    assert [a["subject"] for a in g.accepted] == [subject]
    assert not g.subject_unnamed


def test_a_leading_determiner_alone_does_not_name_a_subject():
    """'The company' is not named by the word 'The': kept, and counted as unnamed."""
    g = _gate(_fact("The company", f"{CONV}:1", "We build scheduling software"))
    assert [a["subject"] for a in g.accepted] == ["The company"]
    assert g.subject_unnamed == {"The company": 1}


def test_partial_word_does_not_count_as_a_name():
    g = _gate(_fact("Sa", f"{CONV}:2", "Sam said the launch slipped"))
    assert [a["subject"] for a in g.accepted] == ["Sa"]
    assert g.subject_unnamed == {"Sa": 1}


def test_the_subject_itself_is_resolved_not_counted():
    g = _gate(_fact("Dana Reyes", f"{CONV}:1", "We build scheduling software"))
    assert [a["subject"] for a in g.accepted] == ["user"]
    assert not g.subject_unnamed and g.subject_referent == 1


def test_subject_unnamed_reaches_the_run_record():
    rec = tc.ExtractionRunRecord("turn", {})
    rec.add_gate(_gate(_fact("Sam Ortiz", f"{CONV}:1", "We build scheduling software"),
                       _fact("Sam Ortiz", f"{CONV}:2", "Sam said the launch slipped")))
    d = rec.to_dict()
    assert d["counts"]["subject_unnamed"] == 1
    assert d["subject_unnamed"] == {"Sam Ortiz": 1}
    assert any("subject_unnamed 1" in line for line in rec.summary_lines())


def test_referent_aliases_come_from_the_entity_map(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_entity_map", lambda: {"sammy": "Sam Ortiz", "s. ortiz": "Sam Ortiz"})
    monkeypatch.setattr(tc, "referent_from_config", lambda c: tc.Referent(names=("Dana",)))
    ref = ef.turn_referent()
    assert set(ref.aliases["sam ortiz"]) == {"sammy", "s. ortiz"}


from tests.test_turn_extraction import _facts, _fake_llm, _records, _seed, env  # noqa: E402,F401


def test_end_to_end_another_subject_is_stored_as_that_subject(env, monkeypatch):
    """The stored subject and the rebuilt fact text keep the other subject (it is not
    stored as a fact about the person), and the run record on disk counts it."""
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    fact = {"subject": "Sam Ortiz", "predicate": "prefers", "object": "short vendor emails",
            "qualifier": "unknown", "category": "preference", "temporal": "current",
            "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn": "S2", "span": "Keep the email short."}]}
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([fact]))
    env.ef.run_extraction()
    [stored] = _facts(env)
    assert stored["subject"] != "user" and not stored["fact_text"].startswith("user ")
    assert "sam ortiz" in stored["fact_text"].lower()
    rec = _records(env)[-1]
    assert rec["counts"]["subject_unnamed"] == 1
    assert rec["subject_unnamed"] == {"Sam Ortiz": 1}


def test_end_to_end_a_strength_stretch_is_stored_on_the_fact(env, monkeypatch):
    """The gate's strength label reaches memory_facts.stretch as JSON; the fact's
    predicate and object are stored unchanged (carried, never repaired)."""
    import json
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    fact = {"subject": "user", "predicate": "prohibits", "object": "long vendor emails",
            "qualifier": "unknown", "category": "rule", "temporal": "current",
            "confidence": 0.9, "inferred": True,
            "evidence_spans": [{"turn": "S2", "span": "Keep the email short."}]}
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([fact]))
    env.ef.run_extraction()
    [stored] = _facts(env)
    assert stored["predicate"] == "prohibits" and stored["object_text"] == "long vendor emails"
    st = json.loads(stored["stretch"])
    assert st == {"kind": "strength", "predicate": "prohibits", "stored": "must",
                  "span": "none", "span_word": "none"}
    assert _records(env)[-1]["counts"]["strength_stretch"] == 1


def test_end_to_end_a_fact_without_a_stretch_stores_null(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    fact = {"subject": "user", "predicate": "prefers", "object": "short vendor emails",
            "qualifier": "unknown", "category": "preference", "temporal": "current",
            "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn": "S2", "span": "Keep the email short."}]}
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([fact]))
    env.ef.run_extraction()
    [stored] = _facts(env)
    assert stored["stretch"] is None
