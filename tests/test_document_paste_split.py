"""
Within-turn document segmenter (voice.py, ``paste:document`` and
``paste:quote_back_earlier``).

A long subject turn often holds a short typed instruction with a pasted document
glued to it: no blank line between, or the document split into paragraphs that
each score as the subject's own text because each one is short. The per-segment
paste score cannot see that; these tests plant exactly that shape and assert the
document leaves the citable classes while the typed framing lines stay.

Everything is synthetic. No API calls.
"""
import json

import pytest

import baselayer.import_conversations as IC
import baselayer.voice as V

from tests.test_turn_contract_import import (  # noqa: F401  (fixtures)
    _cg_conv, _cg_node, assistant, cc_import, env, turns, typed, write_session,
)

CRLF_DOC = "\n".join([
    "Equipment Lending Terms\r",
    "Section 1. Scope\r",
    "These terms govern the loan of shared equipment by the Workshop to its members. The "
    "Workshop shall keep a register of every item lent, the member who holds it and the "
    "date on which it is due back.\r",
    "Section 2. Obligations of the borrower\r",
    "The borrower shall return each item clean and in working order no later than the due "
    "date. Any damage beyond ordinary wear shall be reported to the steward within two "
    "days, and the borrower shall bear the cost of repair where the steward so determines.\r",
    "Section 3. Suspension\r",
    "The steward may suspend borrowing privileges for any member who fails to return an item "
    "on time on three occasions within a calendar year. A suspended member may appeal in "
    "writing to the committee, whose decision shall be final.\r",
    "Section 4. Amendment\r",
    "These terms may be amended by a majority of the committee at any regular meeting, "
    "provided that notice of the proposed amendment was circulated to all members not less "
    "than fourteen days in advance.\r",
    "Section 5. Liability\r",
    "Nothing in these terms shall make the Workshop liable for any loss or injury arising "
    "from the use of borrowed equipment, except where such loss or injury results from the "
    "negligence of the Workshop or its stewards.\r",
    "Section 6. Records\r",
    "The steward shall keep the register for not less than three years and shall make it "
    "available to any member on request. Entries may be corrected only by the steward, and "
    "every correction shall be dated and initialled.\r",
    "Section 7. Notices\r",
    "Any notice under these terms shall be given in writing and delivered by hand or by post "
    "to the address the member last supplied to the Workshop.\r",
    "",
])

TYPED_OPENER = "can u check if this reads ok, i think section 3 is too harsh"


def _segs(text, **kw):
    c = V.classify_subject_text(text, **kw)
    return c, [(text[s.start:s.end], s.voice_class, s.detector or s.basis) for s in c.segments]


def _tiles(text, cls):
    """Segments cover the text exactly, in order, with nothing but whitespace between."""
    pos = 0
    for s in cls.segments:
        assert s.start >= pos
        assert text[pos:s.start].strip() == ""
        pos = s.end
    assert text[pos:].strip() == ""


def test_typed_line_glued_to_a_crlf_document_is_split():
    text = TYPED_OPENER + "\n" + CRLF_DOC
    assert len(text) >= 1500
    cls, got = _segs(text)
    _tiles(text, cls)
    assert got[0][0].strip() == TYPED_OPENER
    assert got[0][1] == "own_typed"
    assert all(vc == "pasted" for _, vc, _ in got[1:])
    assert any(det == V.D_PASTE_DOCUMENT for _, _, det in got[1:])
    pasted = "".join(t for t, vc, _ in got if vc == "pasted")
    assert "Section 3. Suspension" in pasted and TYPED_OPENER not in pasted


PLAIN_CRLF_DOC = "".join(line + "\r\n" for line in [
    "Harbor Street Bakery Cooperative",
    "Our bakery opened on the waterfront eleven years ago with two ovens and a borrowed "
    "mixer. Today the cooperative bakes for four neighbourhood cafes, a school kitchen and "
    "the Saturday market, and every loaf still leaves the building within six hours.",
    "Members share the early shifts on a rotating calendar. Each member keeps a starter "
    "culture at home during the winter closure and brings it back in March, which is how "
    "the rye has kept the same sour character since the first season.",
    "Deliveries go out by cargo bicycle before seven in the morning. On wet days the route "
    "changes so that the school kitchen is served first and the market stall last.",
    "Training for new members runs across three weekends. The first covers hygiene and "
    "ovens, the second covers doughs and timing, and the third is spent entirely on the "
    "market stall, where most new members discover what the customers actually want.",
    "The cooperative publishes its accounts every quarter and every member has a vote on "
    "prices, wages and the choice of flour suppliers.",
    "Surplus bread goes to the night shelter on Tuesdays and Fridays. The shelter collects "
    "it at closing time, and anything left after that is dried for crumbs and sold to two "
    "restaurants on the harbour front.",
    "The ovens were replaced last spring after a fundraising drive among regular market "
    "customers, who were offered a year of weekly loaves in return for their contribution.",
    "and every loaf is still shaped by hand",
])


def test_crlf_is_enough_to_split_off_an_untyped_looking_instruction():
    """The only hard signal here is the CRLF line ending, and the typed line carries no
    typing trait: only the CRLF/LF block split separates it, and only the CRLF signal
    moves the document."""
    opener = "Summarise the cooperative for a grant application"
    text = opener + "\n" + PLAIN_CRLF_DOC
    assert len(text) >= 1500
    cls, got = _segs(text)
    _tiles(text, cls)
    own = "".join(t for t, vc, _ in got if vc in V.CITABLE_VOICE_CLASSES)
    assert own.strip() == opener
    assert any(d == V.D_PASTE_DOCUMENT for _, _, d in got)


def test_crlf_lines_starting_lowercase_or_with_a_number_stay_in_the_document():
    """A lowercase or numeric start marks typing only on an LF line; on a CRLF line it is
    the document's own line and must not be peeled off as the subject's."""
    doc = "5+ years of experience running shared equipment programs\r\n" + CRLF_DOC
    text = TYPED_OPENER + "\n" + doc
    cls, got = _segs(text)
    own = "".join(t for t, vc, _ in got if vc in V.CITABLE_VOICE_CLASSES)
    assert own.strip() == TYPED_OPENER


def test_instruction_and_document_on_one_line_are_split_at_the_colon():
    text = 'summarise this for me: "' + CRLF_DOC + '"'
    cls, got = _segs(text)
    _tiles(text, cls)
    assert got[0][1] == "own_typed"
    assert got[0][0].strip().startswith("summarise this for me")
    assert "Equipment Lending" not in got[0][0]
    assert got[-1][1] == "pasted" or got[-1][0].strip() == '"'
    pasted = "".join(t for t, vc, _ in got if vc == "pasted")
    assert "Section 5. Liability" in pasted


def test_lead_in_followed_by_an_opening_quote_is_split_at_the_quote():
    text = 'Here is the context "' + CRLF_DOC + '" what would you change'
    cls, got = _segs(text)
    _tiles(text, cls)
    assert got[0][1] == "own_typed" and got[0][0].strip() == "Here is the context"
    assert got[-1][1] == "own_typed" and "what would you change" in got[-1][0]
    assert "Section 1. Scope" in "".join(t for t, vc, _ in got if vc == "pasted")


def _tab_log():
    rows = []
    for d in range(1, 29):
        # an apostrophe-less word on some rows: the per-segment typo penalty then keeps the
        # whole table as typed text, which is the failure this pins
        dont = " Dont chase the open next time." if d % 4 == 0 else ""
        rows.append(f"3/{d}\t\t${d * 7}.00\tHeld the position through the open and closed it "
                    f"before the afternoon session; sizing stayed under the daily limit.{dont}")
    return "\n".join(rows)


def test_tab_separated_dated_rows_are_pasted_and_the_title_line_stays():
    title = "march review"
    text = title + "\n\n" + _tab_log()
    assert "\r" not in text and len(text) >= 1500
    cls, got = _segs(text)
    _tiles(text, cls)
    assert got[0] == (title, "own_typed", V.B_ROLE)
    assert [vc for _, vc, _ in got[1:]] == ["pasted"]


def test_typed_question_after_the_document_stays_own():
    tail = "whats ur take, am i being unreasonable here"
    text = TYPED_OPENER + "\n" + CRLF_DOC + tail
    cls, got = _segs(text)
    _tiles(text, cls)
    assert got[-1][1] == "own_typed" and got[-1][0].strip() == tail
    assert got[0][1] == "own_typed"


def test_long_clean_typed_prose_with_no_hard_signal_stays_own():
    para = ("I have been thinking about how the lending rules should work for the workshop, and "
            "my view is that we should keep them light. People borrow tools because they need "
            "them for a weekend project, and if the rules feel punitive they will stop asking. "
            "What I would rather do is make the register visible so that everyone can see who "
            "has what, and trust that most people return things when they are done.")
    text = "\n\n".join([para] * 5)
    assert len(text) >= 1500 and "\r" not in text
    cls, got = _segs(text)
    assert {vc for _, vc, _ in got} == {"own_typed"}


def test_short_turn_is_out_of_scope():
    """Below the length floor the segmenter does not run: a short CRLF note keeps the
    classification the per-segment rules give it."""
    text = "fix this\nThe steward may suspend borrowing privileges.\r\n"
    cls, got = _segs(text)
    assert {vc for _, vc, _ in got} == {"own_typed"}


def test_crlf_document_inside_dictated_text_leaves_before_dictation_is_scored():
    """The pass runs before the dictation score, so the pasted document cannot drag the
    subject's own text into or out of the dictated class."""
    spoken = ("so basically what I want is for you to look at this and tell me If the "
              "suspension part is fair because I think it is too strict And the committee "
              "part is fine")
    text = spoken + "\n" + CRLF_DOC
    cls, got = _segs(text)
    own = [t for t, vc, _ in got if vc in V.CITABLE_VOICE_CLASSES]
    assert own and all("Section" not in t for t in own)


EARLY_ASSISTANT = (
    "Here is a review of the week. Monday went well because you waited for the trend to "
    "confirm before committing capital, and you kept most of it in reserve until the second "
    "hour. Tuesday was also disciplined: you identified a choppy open and stood aside rather "
    "than forcing entries. Wednesday gave back an early gain because you anticipated a "
    "reversal too soon, and the lesson there is to let the position work until a signal "
    "actually changes. Thursday was the best day, with no morning trades because nothing "
    "aligned. Friday broke the rule about trading only when every timeframe agrees, and "
    "losses were not cut quickly enough. Overall the week shows good capital control with "
    "one lapse that cost more than the other four days earned."
)


def test_chatgpt_quote_back_of_an_assistant_turn_several_turns_back(env, tmp_path):
    long_typed = "ok so combining everything, here is what we had earlier\n" + EARLY_ASSISTANT
    long_typed += "\n" + EARLY_ASSISTANT.replace("Here is a review of the week.", "Same again:")
    conv = _cg_conv("cg-qb", [
        _cg_node("n1", None, "user", "review my week please", 1.0),
        _cg_node("n2", "n1", "assistant", EARLY_ASSISTANT, 2.0),
        _cg_node("n3", "n2", "user", "thanks, now what about sizing", 3.0),
        _cg_node("n4", "n3", "assistant", "Keep each entry under a fifth of capital.", 4.0),
        _cg_node("n5", "n4", "user", long_typed, 5.0),
    ])
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps([conv]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    rows = [r for r in turns(env.conn, "cg-qb") if r["turn_id"].startswith("cg-qb:4")]
    own = [r for r in rows if r["voice_class"] in V.CITABLE_VOICE_CLASSES]
    assert own and all("capital control" not in r["text"] for r in own)
    assert any(r["detector"] == V.D_PASTE_QUOTE_BACK_EARLIER for r in rows)


def test_claude_code_quote_back_of_an_assistant_turn_several_turns_back(env):
    sid = "sess-qb-early"
    body = "can you tighten this up\n" + "\n".join([EARLY_ASSISTANT] * 3)
    assert len(body) >= 1500
    write_session(env.projects, sid, [
        typed("review my week please", sid),
        assistant(EARLY_ASSISTANT, sid),
        typed("thanks, now what about sizing", sid),
        assistant("Keep each entry under a fifth of capital.", sid),
        typed(body, sid)])
    cc_import(env)
    rows = [r for r in turns(env.conn, sid) if r["turn_id"].startswith(f"{sid}:4")]
    own = [r for r in rows if r["voice_class"] in V.CITABLE_VOICE_CLASSES]
    assert own and own[0]["text"].strip() == "can you tighten this up"
    assert all("capital control" not in r["text"] for r in own)


def test_typed_prefix_before_an_inline_separator_is_not_swallowed_by_quote_back():
    """The per-segment rules cut at a run of hyphens typed against a word; the document
    pass must cut there too, or the whole line (typed prefix included) is judged as one
    quoted block."""
    text = "i cut it down to this ---" + " ".join([EARLY_ASSISTANT] * 3)
    assert "\n" not in text and len(text) >= 1500
    cls, got = _segs(text, earlier_assistant=V.AssistantShingles([EARLY_ASSISTANT]))
    own = "".join(t for t, vc, _ in got if vc in V.CITABLE_VOICE_CLASSES)
    assert "i cut it down to this" in own
    assert "capital control" not in own


def _fenced(name):
    body = "\n".join(f"    total_{name}_{i} = compute_{name}(rows[{i}], limit={i * 3})"
                     for i in range(14))
    return f"```python\ndef run_{name}(rows):\n{body}\n    return total_{name}_0\n```"


def test_typed_sentence_between_two_pastes_the_old_rules_caught_stays_own():
    """A sentence the subject typed between two pastes has no typing trait to protect
    it. Only blocks between two documents this pass found are absorbed; a neighbour the
    per-segment rules marked pasted is not evidence about the sentence between them."""
    mid = "Here is the second file with the same problem as the first one."
    text = _fenced("alpha") + "\n\n" + mid + "\n\n" + _fenced("beta")
    assert len(text) >= 1500
    cls, got = _segs(text)
    assert (mid, "own_typed", V.B_ROLE) in [(t.strip(), vc, d) for t, vc, d in got]


def test_allowlisting_a_document_segment_makes_it_citable(env, tmp_path):
    conv = _cg_conv("cg-doc", [_cg_node("n1", None, "user", TYPED_OPENER + "\n" + CRLF_DOC, 1.0)])
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps([conv]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    rows = turns(env.conn, "cg-doc")
    doc = [r for r in rows if r["detector"] == V.D_PASTE_DOCUMENT]
    assert doc
    env.config(paste_allowlist=[doc[0]["turn_id"]])
    IC.import_chatgpt(env.conn, str(f), set())
    row = [r for r in turns(env.conn, "cg-doc") if r["turn_id"] == doc[0]["turn_id"]][0]
    assert row["voice_class"] == "own_typed" and row["allowlisted"] == 1
    assert row["basis"] == f"config:allowlist({V.D_PASTE_DOCUMENT})"
