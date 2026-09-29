"""
Own-writing paste allowlist (config ``allowlist_own_writing_pasted``).

A pasted document can be the subject's own writing, for example a journal kept in a
spreadsheet and pasted into a chat. The segmenter marks it ``paste:document`` because the
layout (carriage returns, tab rows, dated lines) is not typed into a chat box, but its
lines carry the subject's typing traits. With the switch on, a ``paste:document`` segment
whose typing-trait score (``voice.typing_trait_score``) reaches the threshold (default 3)
is re-classed ``own_typed`` with basis ``allowlist:own_writing_pasted`` and a ``practice``
tag, so downstream knows the evidence is bounded to one practice. 1-2 traits stay pasted.
Quote-back and other paste detectors are never eligible.

Everything is synthetic. No API calls.
"""
import json
import sqlite3

import pytest

import baselayer.import_conversations as IC
import baselayer.voice as V
from baselayer.import_config import config_from_dict

from tests.test_document_paste_split import CRLF_DOC, TYPED_OPENER
from tests.test_turn_contract_import import (  # noqa: F401  (fixtures)
    LONG_ASSISTANT, _cg_conv, _cg_node, assistant, cc_import, env, typed, write_session,
)

# A tab-structured trade log with the notes column typed in a hurry: apostrophe-less
# contractions and a lowercase "i" are typing traits (at least 3 in total).
JOURNAL_ROWS = [
    "Date\tTrade\tSize\tEntry\tExit\tP/L\tNotes",
    "3/2\t410C\t2\t1.20\t1.45\t$50.00\twaited for the 5m cross, didnt chase the open",
    "3/3\t405P\t3\t2.10\t1.80\t-$90.00\tforced it, dont take trades before the range sets",
    "3/4\t412C\t2\t1.05\t1.60\t$110.00\tgood patience, i held through the pullback to vwap",
    "3/5\t408P\t4\t1.75\t1.70\t-$20.00\tchop all morning, sized too big for the setup",
    "3/6\t415C\t2\t1.30\t1.95\t$130.00\tclean breakout, took profit at the prior day high",
    "3/9\t411P\t3\t1.90\t1.40\t-$150.00\tmoved the stop back, never again, cant keep doing this",
    "3/10\t418C\t2\t1.10\t1.35\t$50.00\tsmall win, entry on the retest of the opening range",
    "3/11\t416P\t2\t1.60\t2.05\t$90.00\tbearish cross on the 15m, waited for confirmation",
    "3/12\t420C\t3\t1.25\t1.20\t-$15.00\tflat day, should have sat out after the first loss",
    "3/13\t417P\t2\t1.85\t2.40\t$110.00\tgood read on the gap fill, exit at the target",
    "3/16\t422C\t2\t1.40\t1.10\t-$60.00\tearly entry, the 5m had not crossed yet",
    "3/17\t419P\t3\t1.70\t2.20\t$150.00\tbest day of the week, followed every rule",
    "3/18\t424C\t2\t1.15\t1.50\t$70.00\tpatient entry at support, scaled out in two parts",
    "3/19\t421P\t2\t1.95\t1.60\t-$70.00\tfought the trend, the higher timeframe was bullish",
    "3/20\t426C\t2\t1.35\t1.85\t$100.00\tgood week overall, capital use under half by noon",
    "3/23\t423P\t2\t1.80\t2.25\t$90.00\tfollowed the plan, one trade and done for the day",
    "3/24\t428C\t3\t1.20\t0.95\t-$75.00\tentered on news, the spread was too wide to manage",
    "3/25\t425P\t2\t1.65\t2.10\t$90.00\tbearish open, waited for the retest and took the move",
    "3/26\t430C\t2\t1.45\t1.90\t$90.00\tsteady trend day, trailed the stop under each higher low",
    "3/27\t427P\t2\t1.70\t1.55\t-$30.00\tsmall loss, exit was right when the level broke back",
    "3/30\t432C\t3\t1.30\t1.75\t$135.00\tstrong close to the month, kept size steady all day",
    "3/31\t429P\t2\t1.90\t2.30\t$80.00\tmonth end, reviewed every losing trade before the open",
]
JOURNAL = "\r\n".join(JOURNAL_ROWS) + "\r\n"
assert len(JOURNAL) >= 1500   # the document segmenter reads turns of 1,500+ chars

# The same layout with one typing trait only (1-2 traits stay pasted).
ONE_TRAIT = JOURNAL.replace("didnt", "did not").replace("dont", "do not").replace(
    " i held", " I held")

# A pasted document with no typing traits at all (stays pasted).
LEGAL = CRLF_DOC

# A typed-trait document that is not a trade log (a plan pasted from a notes app).
NOTES_DOC = "\r\n".join([
    "Garden plan\tBed\tWeek",
    "tomatoes\tnorth bed\t12",
    "beans\twest bed\t14",
    "",
]) + "\r\n".join([
    "didnt get the soil test back yet so the lime amounts are a guess for now",
    "dont plant the squash next to the beans again, they shaded out the whole row",
    "i want the herbs by the door this year so they actually get picked and used",
    "compost bins need turning every two weeks, the back one went anaerobic in june",
    "the drip line on the north bed leaks at the second elbow and needs a new fitting",
    "order more straw before the first frost so the garlic can be mulched in time",
    "the rain barrel overflowed twice in april, add a diverter before the next storm",
    "seed potatoes arrived early, keep them in the cool room until the ground warms",
    "the fence on the east side is sagging, two posts need resetting before spring",
    "keep a note of which varieties bolted early so they are not ordered again",
    "thin the carrots twice this year, the crowded rows gave nothing but thin roots",
    "",
])

OPENER = "here are my notes from this week, what patterns do you see in how i trade?"


def _settings():
    return V.VoiceSettings()


# --------------------------------------------------------------------------- units

def test_trait_score_is_the_sum_of_per_line_typing_traits():
    s = _settings()
    expect = sum(V._typing_traits(ln, s) for ln in JOURNAL.split("\n") if ln.strip())
    assert V.typing_trait_score(JOURNAL, s) == expect >= 3
    assert 1 <= V.typing_trait_score(ONE_TRAIT, s) <= 2
    assert V.typing_trait_score(LEGAL, s) == 0


def test_configured_typos_count_toward_the_score():
    text = "went sizeing it\nand sizeing that"
    assert V.typing_trait_score(text, _settings()) == 0
    s = V.VoiceSettings(extra_typos=frozenset({"sizeing"}))
    assert V.typing_trait_score(text, s) == 2


def test_practice_tag_trade_log_vs_other_document():
    assert V.practice_of_pasted(JOURNAL) == "trading_journal"
    assert V.practice_of_pasted(NOTES_DOC) == "own_document"
    assert V.practice_of_pasted(LEGAL) == "own_document"


def test_rule_eligibility_and_threshold():
    rule = V.OwnWritingRule(settings=_settings(), min_traits=3)
    assert rule.decide(JOURNAL, V.D_PASTE_DOCUMENT) == "trading_journal"
    assert rule.decide(ONE_TRAIT, V.D_PASTE_DOCUMENT) is None
    assert rule.decide(LEGAL, V.D_PASTE_DOCUMENT) is None
    # quote-back is assistant text by construction; structural pastes were never measured
    for det in (V.D_PASTE_QUOTE_BACK, V.D_PASTE_QUOTE_BACK_EARLIER, V.D_PASTE_STRUCTURAL,
                V.D_PASTE_TAG, V.D_PASTE_TERMINAL, V.D_PASTE_TEMPLATE):
        assert rule.decide(JOURNAL, det) is None, det


# --------------------------------------------------------------------------- config

def test_config_switch_default_off_and_parsed():
    assert config_from_dict({}).own_writing_rule() is None
    assert config_from_dict({"allowlist_own_writing_pasted": False}).own_writing_rule() is None
    rule = config_from_dict({"allowlist_own_writing_pasted": True}).own_writing_rule()
    assert rule is not None and rule.min_traits == 3
    rule = config_from_dict({"allowlist_own_writing_pasted": True,
                             "own_writing_min_traits": 5}).own_writing_rule()
    assert rule.min_traits == 5


@pytest.mark.parametrize("bad", [True, "3", 0, -1, 2.5])
def test_config_threshold_must_be_a_positive_int(bad):
    with pytest.raises(ValueError):
        config_from_dict({"allowlist_own_writing_pasted": True, "own_writing_min_traits": bad})


# --------------------------------------------------------------------------- import

def _import_cg(env, tmp_path, cid, user_text):
    conv = _cg_conv(cid, [
        _cg_node("n1", None, "user", "i keep a trade log, can i paste it?", 1.0),
        _cg_node("n2", "n1", "assistant", "Yes, paste it and I will look for patterns.", 2.0),
        _cg_node("n3", "n2", "user", user_text, 3.0),
    ])
    f = tmp_path / f"{cid}.json"
    f.write_text(json.dumps([conv]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    return f


def _rows(conn, cid):
    return [dict(zip(("turn_id", "voice_class", "detector", "basis", "allowlisted", "practice", "text"), r))
            for r in conn.execute(
                "SELECT turn_id, voice_class, detector, basis, allowlisted, practice, text FROM turns "
                "WHERE conversation_id=? ORDER BY ordinal, COALESCE(segment, -1)", (cid,)).fetchall()]


def _journal_row(rows):
    got = [r for r in rows if "410C" in r["text"]]
    assert len(got) == 1
    return got[0]


def test_switch_off_journal_stays_pasted(env, tmp_path):
    _import_cg(env, tmp_path, "cg-off", OPENER + "\n" + JOURNAL)
    row = _journal_row(_rows(env.conn, "cg-off"))
    assert row["voice_class"] == "pasted" and row["detector"] == V.D_PASTE_DOCUMENT
    assert row["practice"] is None and row["allowlisted"] == 0


def test_switch_on_journal_becomes_own_typed_with_practice(env, tmp_path):
    env.config(allowlist_own_writing_pasted=True)
    _import_cg(env, tmp_path, "cg-on", OPENER + "\n" + JOURNAL)
    rows = _rows(env.conn, "cg-on")
    row = _journal_row(rows)
    assert row["voice_class"] == "own_typed"
    assert row["detector"] is None
    assert row["basis"] == V.B_OWN_WRITING == "allowlist:own_writing_pasted"
    assert row["allowlisted"] == 1
    assert row["practice"] == "trading_journal"
    # the typed opener is ordinary typed text: no practice tag
    opener = [r for r in rows if r["text"].startswith("here are my notes")][0]
    assert opener["voice_class"] == "own_typed" and opener["practice"] is None
    # the legacy messages projection now carries the journal as the subject's text
    um = [r[0] for r in env.conn.execute(
        "SELECT content_text FROM messages WHERE conversation_id='cg-on' AND role='user'")]
    assert any("410C" in m for m in um)


def test_switch_on_low_trait_and_clean_documents_stay_pasted(env, tmp_path):
    env.config(allowlist_own_writing_pasted=True)
    _import_cg(env, tmp_path, "cg-one", OPENER + "\n" + ONE_TRAIT)
    row = _journal_row(_rows(env.conn, "cg-one"))
    assert row["voice_class"] == "pasted" and row["practice"] is None
    _import_cg(env, tmp_path, "cg-legal", TYPED_OPENER + "\n" + LEGAL)
    legal = [r for r in _rows(env.conn, "cg-legal") if "Workshop" in r["text"]]
    assert legal and all(r["voice_class"] == "pasted" for r in legal)


def test_quote_back_with_typing_traits_is_never_allowlisted(env, tmp_path):
    env.config(allowlist_own_writing_pasted=True)
    said = ("i think you didnt size it right and you dont need to chase, "
            "the setup was fine but the entry wasnt, and thats the lesson for this week")
    conv = _cg_conv("cg-qb", [
        _cg_node("n1", None, "user", "review my day", 1.0),
        _cg_node("n2", "n1", "assistant", said, 2.0),
        _cg_node("n3", "n2", "user", said + "\n\nwhat did you mean here", 3.0),
    ])
    f = tmp_path / "qb.json"
    f.write_text(json.dumps([conv]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    qb = [r for r in _rows(env.conn, "cg-qb") if r["detector"] == V.D_PASTE_QUOTE_BACK]
    assert qb and V.typing_trait_score(qb[0]["text"], _settings()) >= 3


def test_manual_allowlist_wins_over_the_rule(env, tmp_path):
    env.config(allowlist_own_writing_pasted=True)
    _import_cg(env, tmp_path, "cg-probe", OPENER + "\n" + JOURNAL)
    tid = _journal_row(_rows(env.conn, "cg-probe"))["turn_id"].replace("cg-probe", "cg-man")
    env.config(allowlist_own_writing_pasted=True, paste_allowlist=[tid])
    _import_cg(env, tmp_path, "cg-man", OPENER + "\n" + JOURNAL)
    row = _journal_row(_rows(env.conn, "cg-man"))
    assert row["basis"] == "config:allowlist(paste:document)"
    assert row["voice_class"] == "own_typed" and row["allowlisted"] == 1


def test_unchanged_reimport_keeps_rule_rows(env, tmp_path):
    """sync_allowlist runs on an unchanged source; it must not revert rule rows as if
    they were manual allowlist entries that had been removed."""
    env.config(allowlist_own_writing_pasted=True)
    f = _import_cg(env, tmp_path, "cg-re", OPENER + "\n" + JOURNAL)
    IC.import_chatgpt(env.conn, str(f), IC.get_existing_conversation_ids(env.conn))
    row = _journal_row(_rows(env.conn, "cg-re"))
    assert row["voice_class"] == "own_typed" and row["basis"] == V.B_OWN_WRITING
    assert row["detector"] is None and row["practice"] == "trading_journal"


def test_claude_code_path_applies_the_rule(env):
    env.config(allowlist_own_writing_pasted=True)
    sid = "sess-journal"
    write_session(env.projects, sid, [
        typed("i keep a trade log, can i paste it?", sid),
        assistant("Yes, paste it and I will look for patterns.", sid),
        typed(OPENER + "\n" + JOURNAL, sid)])
    cc_import(env)
    row = _journal_row(_rows(env.conn, sid))
    assert row["voice_class"] == "own_typed" and row["practice"] == "trading_journal"


def test_existing_turn_table_gains_the_practice_column(tmp_path):
    from baselayer.turns import ensure_turn_tables
    db = tmp_path / "old.db"
    c = sqlite3.connect(str(db))
    c.executescript("""
    CREATE TABLE turns (turn_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL, segment INTEGER, speaker TEXT NOT NULL,
        voice_class TEXT NOT NULL, text TEXT NOT NULL, detector TEXT, basis TEXT,
        source TEXT, source_record_id TEXT, created_at REAL, char_start INTEGER,
        char_end INTEGER, duplicate_of TEXT, allowlisted INTEGER NOT NULL DEFAULT 0,
        turn_contract_version TEXT NOT NULL);
    """)
    ensure_turn_tables(c)
    cols = {r[1] for r in c.execute("PRAGMA table_info(turns)")}
    assert "practice" in cols
