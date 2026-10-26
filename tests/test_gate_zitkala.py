"""
The gate on real facts from a public-domain autobiography (Zitkala-Sa, three essays,
The Atlantic Monthly, 1900). A policy-vocabulary extraction of these essays on 2026-10-26
returned the facts below; the gate's subject check rewrote 9 of 31 subjects to `user`.

1. Subject. A subject that is not the configured referent is kept, even when no span
   names it. The span check proves the words are the subject's own; it does not show
   who the fact is about. Rewriting such a subject to `user` turned "guest" into the
   host (PO030) and replaced an action's name with `user` (PO019, PO028). A kept
   subject that no span names is counted (`subject_unnamed`), never silent.

2. Strength. A fact whose predicate carries a modality (obliges, prohibits, ...) is
   compared with its spans' own modal wording. When the stored strength exceeds the
   words ("should not" stored as `prohibits`; "I was afraid" stored as a rule), the
   fact carries `stretch` = {"kind": "strength", ...}. It is carried, never repaired:
   the subject, predicate and object are unchanged.
"""
import pytest

import baselayer.turn_contract as tc

CONV = "conv-zs"

# Source passages, verbatim (whitespace joined). One turn per passage, all own voice.
PASSAGES = [
    # 0, Impressions of an Indian Childhood
    "As I frolicked about our dwelling I used to stop suddenly, and with a fearful awe watch "
    "the smoking of the unknown fires. While the vapor was visible I was afraid to go very far "
    "from our wigwam unless I went with my mother.",
    # 1
    "I wanted very much to catch him and rub his pretty fur back, but my mother said he would "
    "be so frightened if I caught him that he would bite my fingers.",
    # 2
    "I was ready to run out to meet them, but I did not dare to displease my mother.",
    # 3
    "Unless my mother had cautioned me not to tell, I generally answered her questions "
    "without reserve. At the arrival of our guests I sat close to my mother, and did not "
    "leave her side without first asking her consent.",
    # 4
    "For this reason, my mother said, I should not do much alone in quills until I was as "
    "tall as my cousin Warca-Ziwin.",
    # 5
    "It was a custom for young Indian women to invite some older relative to escort them to "
    "the public feasts. Though it was not an iron law, it was generally observed.",
    # 6
    "But neither she nor the warrior, whom the law of our custom had compelled to partake of "
    "my insipid hospitality, said anything to embarrass me.",
    # 7
    "\"Never pluck a single plum from this brush, my child, for its roots are wrapped around "
    "an Indian's skeleton.\"",
    # 8
    "\"Hush; my little daughter must never talk about my tears\"; and smiling through them, "
    "she patted my head.",
    # 9
    "\"Wait a moment before you invite any one. If other plans are being discussed, do not "
    "interfere, but go elsewhere.\"",
    # 10
    "My mother required of me original designs for my lessons in beading.",
    # 11, School Days of an Indian Girl
    "One morning we learned through her ears that we were forbidden to fall lengthwise in "
    "the snow, as we had been doing, to see our own impressions.",
    # 12
    "If she looks straight into your eyes and talks loudly, you must wait until she stops.",
    # 13
    "The following autumn I ventured upon a college career against my mother's will. I had "
    "written for her approval, but in her reply I found no encouragement.",
    # 14
    "My mother had not yet forgiven my rudeness to her, and I had no moment for "
    "letter-writing.",
    # 15
    "Relentlessly her pencil black-marked our daily records if we were not present to "
    "respond to our names, and no chum of ours had done it successfully for us.",
    # 16
    "Then I heard the paleface woman say that this terrible creature roamed loose in the "
    "world, and that little girls who disobeyed school regulations were to be tortured by him.",
    # 17, An Indian Teacher Among Indians
    "\"The Indian cannot complain to the Great Father in Washington without suffering outrage "
    "for it here.\"",
]


def _chunk():
    turns = [tc.Turn(f"{CONV}:{i}", CONV, "subject", "own_typed", t) for i, t in enumerate(PASSAGES)]
    return tc.build_chunks(turns, 20000, context_budget=0, context_max_turns=0)[0]


REF = tc.Referent(names=("Zitkala-Sa", "Gertrude Simmons Bonnin"))


def _fact(subject, predicate, obj, passage, *spans, inferred=False):
    return {"subject": subject, "predicate": predicate, "object": obj, "qualifier": "unknown",
            "category": "rule", "confidence": 0.8, "inferred": inferred,
            "evidence_spans": [{"turn_id": f"{CONV}:{passage}", "span": s} for s in spans]}


def _gate(*facts):
    return tc.gate_facts(list(facts), _chunk(), referent=REF)


# ------------------------------------------------------------------ 1. subject
# (raw subject as extracted, predicate, object, passage, span). Every one of these was
# rewritten to `user` by the gate on 2026-10-26.
NOT_THE_AUTHOR = [
    ("PO003", "college career without mother's approval", "has_consequence",
     "mother had not yet forgiven the user's rudeness", 14,
     "My mother had not yet forgiven my rudeness to her"),
    ("PO005", "complaint to the Great Father in Washington", "has_consequence",
     "the complainant suffers outrage in the village", 17,
     "The Indian cannot complain to the Great Father in Washington without suffering outrage for it here."),
    ("PO006", "pupils", "prohibits", "falling lengthwise in the snow", 11,
     "we were forbidden to fall lengthwise in the snow"),
    ("PO009", "roll call attendance", "has_consequence",
     "absence or tardiness recorded in the daily records", 15,
     "Relentlessly her pencil black-marked our daily records if we were not present to respond to our names"),
    ("PO012", "disobeying school regulations", "has_consequence", "being tortured by the devil", 16,
     "little girls who disobeyed school regulations were to be tortured by him"),
    ("PO019", "going far from the wigwam", "conditioned_on",
     "the morning smoke from the pit is visible, and only with mother", 0,
     "While the vapor was visible I was afraid to go very far from our wigwam unless I went with my mother."),
    ("PO028", "work alone with porcupine quills", "conditioned_on",
     "subject is as tall as cousin Warca-Ziwin", 4, "should not do much alone in quills"),
    ("PO030", "guest", "obliges", "partake of the host's hospitality", 6,
     "the law of our custom had compelled to partake of my insipid hospitality"),
    ("PO031", "young Indian women", "obliges",
     "invite an older relative to escort them to public feasts", 5,
     "to invite some older relative to escort them to the public feasts."),
]


@pytest.mark.parametrize("idx,subject,pred,obj,passage,span", NOT_THE_AUTHOR,
                         ids=[r[0] for r in NOT_THE_AUTHOR])
def test_a_subject_that_is_not_the_referent_is_kept(idx, subject, pred, obj, passage, span):
    g = _gate(_fact(subject, pred, obj, passage, span))
    [a] = g.accepted
    assert a["subject"] == subject, f"{idx}: subject rewritten to {a['subject']!r}"


def test_the_guest_is_not_turned_into_the_host():
    """PO030: the span says the warrior (a guest) was compelled to partake of 'my'
    hospitality. The first-person 'my' is the host. The fact is about the guest."""
    g = _gate(_fact("guest", "obliges", "partake of the host's hospitality", 6,
                    "the law of our custom had compelled to partake of my insipid hospitality"))
    assert g.accepted[0]["subject"] == "guest"


def test_a_kept_subject_no_span_names_is_counted():
    g = _gate(*[_fact(s, p, o, n, sp) for _i, s, p, o, n, sp in NOT_THE_AUTHOR])
    assert len(g.accepted) == len(NOT_THE_AUTHOR)
    # None of the nine is named in its span (the reason each was rewritten before).
    assert sum(g.subject_unnamed.values()) == len(NOT_THE_AUTHOR)
    assert set(g.subject_unnamed) == {r[1] for r in NOT_THE_AUTHOR}
    assert g.subject_referent == 0


@pytest.mark.parametrize("raw", ["user", "Zitkala-Sa", "zitkala-sa", "this person", "the person"])
def test_the_referent_still_resolves_to_user(raw):
    g = _gate(_fact(raw, "prohibits", "pluck any plums from the plum bush", 7,
                    "Never pluck a single plum from this brush, my child,"))
    assert g.accepted[0]["subject"] == "user"
    assert not g.subject_unnamed


# ------------------------------------------------------------------ 2. strength
# Known positives: the modality facts graded as misreads on 2026-10-26 (fidelity.tsv).
# (idx, predicate, object, passage, spans, expected span strength, expected span word)
MISREADS = [
    ("PO002", "obliges", "obtain her mother's approval before beginning a college career", 13,
     ["I had written for her approval"], "none", "none"),                    # approval sought
    ("PO017", "prohibits", "catch the ground squirrel", 1,
     ["my mother said he would be so frightened if I caught him that he would bite my fingers."],
     "none", "frightened"),                                                    # a warning
    ("PO018", "prohibits", "go very far from the wigwam", 0,
     ["While the vapor was visible I was afraid to go very far from our wigwam unless I went with my mother."],
     "none", "afraid"),                                                        # a fear
    ("PO020", "prohibits", "displease my mother by disobeying her", 2,
     ["I did not dare to displease my mother."], "none", "dare"),             # deference
    ("PO025", "prohibits", "answer questions without reserve", 3,
     ["Unless my mother had cautioned me not to tell"], "should", "cautioned"),  # inverted
    ("PO026", "requires_consent_of", "mother", 3,
     ["leave her side without first asking her consent."], "none", "none"),   # a habit
    ("PO027", "prohibits", "work alone with porcupine quills", 4,
     ["should not do much alone in quills"], "should", "should"),             # "should not"
    ("PO031", "obliges", "invite an older relative to escort them to public feasts", 5,
     ["to invite some older relative to escort them to the public feasts.",
      "Though it was not an iron law, it was generally observed."], "should", "not an iron law"),
]
# Known negatives: modality facts graded policy-grade AND faithful (fidelity.tsv `F`) whose
# span carries the modal word.
FAITHFUL = [
    ("PO006", "prohibits", "falling lengthwise in the snow", 11,
     ["we were forbidden to fall lengthwise in the snow"]),
    ("PO013", "obliges", "wait until the woman stops talking before answering", 12,
     ["you must wait until she stops"]),
    ("PO014", "prohibits", "pluck any plums from the plum bush", 7,
     ["Never pluck a single plum from this brush, my child, for its roots are wrapped around an Indian's skeleton."]),
    ("PO021", "prohibits", "talk about her mother's tears", 8,
     ["my little daughter must never talk about my tears"]),
    ("PO023", "prohibits", "interfere with other plans being discussed", 9,
     ["being discussed, do not interfere, but go elsewhere."]),
    ("PO029", "obliges", "produce original designs for beadwork lessons", 10,
     ["My mother required of me original designs for my lessons"]),
    ("PO030", "obliges", "partake of the host's hospitality", 6,
     ["the law of our custom had compelled to partake of my insipid hospitality"]),
]


@pytest.mark.parametrize("idx,pred,obj,passage,spans,level,word", MISREADS,
                         ids=[r[0] for r in MISREADS])
def test_a_modality_stronger_than_its_words_carries_a_strength_stretch(idx, pred, obj, passage,
                                                                      spans, level, word):
    g = _gate(_fact("user", pred, obj, passage, *spans))
    [a] = g.accepted
    st = a.get("stretch")
    assert st, f"{idx}: no stretch label"
    assert st["kind"] == "strength" and st["predicate"] == pred
    assert st["stored"] == "must" and st["span"] == level and st["span_word"] == word
    # carried, never repaired
    assert (a["subject"], a["predicate"], a["object"]) == ("user", pred, obj)
    assert g.strength_stretch == 1


@pytest.mark.parametrize("idx,pred,obj,passage,spans", FAITHFUL, ids=[r[0] for r in FAITHFUL])
def test_a_modality_its_words_carry_is_not_flagged(idx, pred, obj, passage, spans):
    g = _gate(_fact("user", pred, obj, passage, *spans))
    assert "stretch" not in g.accepted[0], f"{idx}: {g.accepted[0].get('stretch')}"
    assert g.strength_stretch == 0


def test_a_should_stored_as_a_should_is_not_flagged():
    g = _gate(_fact("user", "discourages", "work alone with porcupine quills", 4,
                    "should not do much alone in quills"))
    assert "stretch" not in g.accepted[0]


def test_a_fact_without_a_modality_predicate_is_never_checked():
    """The person vocabulary carries no modality: a fear stored as `fears` is not a rule."""
    span = "While the vapor was visible I was afraid to go very far from our wigwam"
    g = _gate(_fact("user", "fears", "going far from the wigwam while the smoke is visible", 0, span),
              _fact("going far from the wigwam", "conditioned_on", "the smoke is visible", 0, span))
    assert len(g.accepted) == 2
    assert all("stretch" not in a for a in g.accepted) and g.strength_stretch == 0


def test_the_model_cannot_supply_its_own_stretch_label():
    f = _fact("user", "prohibits", "pluck any plums from the plum bush", 7,
              "Never pluck a single plum from this brush, my child,")
    f["stretch"] = {"kind": "strength", "span_word": "invented"}
    assert "stretch" not in _gate(f).accepted[0]


def test_strength_stretch_reaches_the_run_record():
    rec = tc.ExtractionRunRecord("turn", {})
    rec.add_gate(_gate(*[_fact("user", p, o, n, *s) for _i, p, o, n, s, _l, _w in MISREADS]))
    assert rec.to_dict()["counts"]["strength_stretch"] == len(MISREADS)
    assert any(line.strip().startswith(f"strength_stretch {len(MISREADS)}")
               for line in rec.summary_lines())


def test_subject_unnamed_reaches_the_run_record():
    rec = tc.ExtractionRunRecord("turn", {})
    rec.add_gate(_gate(_fact("guest", "obliges", "partake of the host's hospitality", 6,
                             "the law of our custom had compelled to partake of my insipid hospitality")))
    d = rec.to_dict()
    assert d["counts"]["subject_unnamed"] == 1 and d["subject_unnamed"] == {"guest": 1}
    assert any("subject_unnamed 1" in line for line in rec.summary_lines())
