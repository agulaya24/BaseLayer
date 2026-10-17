"""
The mechanical subject check (TURN_CONTRACT.md §5, subject resolution).

The gate proves grounding, not reference. In a meeting, the subject's own words
about their own work can come back with another participant's name as the
subject. Rule: when every span is the subject's own turn and the fact's subject
is not `user`, the other subject is kept only if its name (or a configured alias,
case-insensitive, with or without a surname) appears literally in at least one
span. Otherwise the subject becomes `user`, and the reassignment is counted,
never silent.
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


def test_other_subject_absent_from_the_spans_becomes_user_and_is_counted():
    g = _gate(_fact("Sam Ortiz", f"{CONV}:1", "We build scheduling software"))
    assert [a["subject"] for a in g.accepted] == ["user"]
    assert g.subject_reassigned == {"Sam Ortiz": 1}


@pytest.mark.parametrize("subject,span", [
    ("Sam Ortiz", "Sam said the launch slipped"),          # surname missing in the span
    ("sam ortiz", "Sam said the launch slipped"),          # case-insensitive
    ("Sam Ortiz", "Sammy called twice about the contract"),  # configured alias
    ("the user's wife", "My wife is a doctor"),            # role subject, possessive stripped
    ("The company", "The company ships weekly now."),       # determiner stripped
    ("colleague (Sam)", "Sam said the launch slipped"),    # parenthetical name
])
def test_other_subject_named_in_a_span_is_kept(subject, span):
    g = _gate(_fact(subject, f"{CONV}:2", span))
    assert [a["subject"] for a in g.accepted] == [subject]
    assert not g.subject_reassigned


def test_a_leading_determiner_alone_does_not_keep_a_subject():
    """'The company' must not survive on the word 'The'."""
    g = _gate(_fact("The company", f"{CONV}:1", "We build scheduling software"))
    assert [a["subject"] for a in g.accepted] == ["user"]
    assert g.subject_reassigned == {"The company": 1}


def test_partial_word_does_not_count_as_a_name():
    g = _gate(_fact("Sa", f"{CONV}:2", "Sam said the launch slipped"))
    assert [a["subject"] for a in g.accepted] == ["user"]


def test_the_subject_itself_is_resolved_not_reassigned():
    g = _gate(_fact("Dana Reyes", f"{CONV}:1", "We build scheduling software"))
    assert [a["subject"] for a in g.accepted] == ["user"]
    assert not g.subject_reassigned and g.subject_referent == 1


def test_reassignment_reaches_the_run_record():
    rec = tc.ExtractionRunRecord("turn", {})
    rec.add_gate(_gate(_fact("Sam Ortiz", f"{CONV}:1", "We build scheduling software"),
                       _fact("Sam Ortiz", f"{CONV}:2", "Sam said the launch slipped")))
    d = rec.to_dict()
    assert d["counts"]["subject_reassigned"] == 1
    assert d["subject_reassigned_from"] == {"Sam Ortiz": 1}
    assert any("subject_reassigned 1" in line for line in rec.summary_lines())


def test_referent_aliases_come_from_the_entity_map(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_entity_map", lambda: {"sammy": "Sam Ortiz", "s. ortiz": "Sam Ortiz"})
    monkeypatch.setattr(tc, "referent_from_config", lambda c: tc.Referent(names=("Dana",)))
    ref = ef.turn_referent()
    assert set(ref.aliases["sam ortiz"]) == {"sammy", "s. ortiz"}


from tests.test_turn_extraction import _facts, _fake_llm, _records, _seed, env  # noqa: E402,F401


def test_end_to_end_the_stored_fact_is_about_the_subject(env, monkeypatch):
    """The stored subject and the rebuilt fact text both carry `user`, and the
    run record on disk counts the reassignment."""
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    fact = {"subject": "Sam Ortiz", "predicate": "prefers", "object": "short vendor emails",
            "qualifier": "unknown", "category": "preference", "temporal": "current",
            "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn": "S2", "span": "Keep the email short."}]}
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([fact]))
    env.ef.run_extraction()
    [stored] = _facts(env)
    assert stored["subject"] == "user" and stored["fact_text"].startswith("user ")
    rec = _records(env)[-1]
    assert rec["counts"]["subject_reassigned"] == 1
    assert rec["subject_reassigned_from"] == {"Sam Ortiz": 1}
