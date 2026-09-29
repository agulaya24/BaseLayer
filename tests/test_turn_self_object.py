"""
Object normalisation (TURN_CONTRACT.md §5, subject resolution, the object slot).

The extractor can put the subject's configured name in a fact's OBJECT
("user collaborates with Dana Reyes"). After the subject is resolved, an object
equal to a configured name is the subject too:
  - when the resolved subject is also `user`, the fact relates the subject to
    themselves and is rejected with reason `self_object`;
  - when the subject is another person, the object becomes `user`.
Only configured names are matched, whole object only. The generic forms are not
matched in the object slot ("the user" there is usually a product's end user),
and a possessive or a longer phrase containing the name is left alone.
"""
import pytest

import baselayer.turn_contract as tc

CONV = "conv-o"


def _chunk():
    turns = [
        tc.Turn(f"{CONV}:0", CONV, "other", "other_person", "Who runs the clinic project?"),
        tc.Turn(f"{CONV}:1", CONV, "subject", "own_dictated",
                "We build scheduling software for small clinics."),
        tc.Turn(f"{CONV}:2", CONV, "subject", "own_dictated",
                "Sam said the launch slipped a week. 2024-03-01  AAPL  150.00  buy"),
    ]
    return tc.build_chunks(turns, 5000, context_budget=400, context_max_turns=3)[0]


REF = tc.Referent(names=("Dana Reyes", "Dana"))


def _fact(subject, obj, turn=f"{CONV}:1", span="We build scheduling software"):
    return {"subject": subject, "predicate": "collaborates_with", "object": obj,
            "category": "relationship", "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn_id": turn, "span": span}]}


def _gate(*facts):
    return tc.gate_facts(list(facts), _chunk(), referent=REF)


def test_self_object_is_a_reject_reason():
    assert "self_object" in tc.REJECT_REASONS


@pytest.mark.parametrize("subject", ["user", "Dana Reyes", "this person", "the user"])
@pytest.mark.parametrize("obj", ["Dana Reyes", "dana reyes", " Dana ", "“Dana Reyes”"])
def test_subject_related_to_their_own_name_is_rejected(subject, obj):
    g = _gate(_fact(subject, obj))
    assert g.accepted == []
    assert g.rejected == {"self_object": 1}
    assert g.subject_referent == 0 and not g.subject_reassigned


def test_reassigned_subject_with_the_name_as_object_is_rejected_not_counted_as_reassigned():
    """'Sam Ortiz collaborates with Dana' on a span that never names Sam: the
    subject becomes `user`, so the fact relates the subject to themselves."""
    g = _gate(_fact("Sam Ortiz", "Dana Reyes"))
    assert g.accepted == [] and g.rejected == {"self_object": 1}
    assert not g.subject_reassigned


def test_other_person_named_in_the_span_keeps_the_fact_and_the_object_becomes_user():
    g = _gate(_fact("Sam", "Dana Reyes", turn=f"{CONV}:2", span="Sam said the launch slipped"))
    assert [(a["subject"], a["object"]) for a in g.accepted] == [("Sam", "user")]
    assert sum(g.rejected.values()) == 0


@pytest.mark.parametrize("obj", ["the user", "user", "users of the clinic app",
                                 "Dana's clinic", "Dana Reyes and Sam", "", None])
def test_other_objects_are_untouched(obj):
    f = _fact("user", obj)
    if obj is None:
        del f["object"]
    g = _gate(f)
    assert len(g.accepted) == 1 and sum(g.rejected.values()) == 0
    assert g.accepted[0].get("object") == obj


def test_a_rejected_record_fact_is_not_counted_as_record_only():
    g = _gate(_fact("user", "Dana", turn=f"{CONV}:2", span="2024-03-01  AAPL  150.00  buy"))
    assert g.rejected == {"self_object": 1}
    assert g.record_only == 0 and g.accepted == []


def test_run_record_carries_self_object():
    rec = tc.ExtractionRunRecord("sequential", {})
    rec.add_gate(_gate(_fact("user", "Dana Reyes"), _fact("user", "a clinic")))
    d = rec.to_dict()
    assert d["gate_rejections"]["self_object"] == 1
    assert d["counts"]["accepted"] == 1
