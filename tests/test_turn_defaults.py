"""
Turn-mode defaults approved for the re-specification run (docs/core/DECISIONS.md
D-108). Each applies in TURN mode only; the legacy path is unchanged, and each
legacy behaviour is pinned here too so the change cannot leak into it.

  1. The D-048 contamination filter is off: the span gate replaces it.
  2. The dynamic fact cap defaults on (an explicit BASELAYER_DYNAMIC_CAP=0 still
     turns it off).
  3. MIN_MESSAGES_FOR_EXTRACTION does not apply: short and prompt-only
     conversations are extracted.
  4. Evidence spans are bounded (min words, max chars); out-of-bounds spans are
     rejected as `span_length` and counted with the other reasons.
  5. Conversations the importer re-marked `needs_extraction` (grown sessions)
     are picked up again, and the mark is cleared after a successful run.

No API calls; nothing written outside tmp_path.
"""

import sqlite3
import time

import pytest

from baselayer.turn_contract import Referent as _Referent  # noqa: E402
_REFERENT = _Referent(names=("Dana Reyes",))

from tests.test_turn_extraction import (  # shared synthetic corpus and fakes

    CONV, TURNS, _dense_llm, _dense_seed, _fact, _facts, _fake_llm, _records, _seed, env,  # noqa: F401
)


def _turn_mode(monkeypatch):
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")


# ---------------------------------------------------------------------------
# 1. contamination filter
# ---------------------------------------------------------------------------

BASE_LAYER_FACT = _fact("building the base layer pipeline", [("S3", "Call the project Base Layer.")])
SHORT_EMAIL_FACT = _fact("short emails to vendors", [("S2", "Keep the email short.")])


def test_turn_mode_keeps_facts_the_contamination_filter_would_drop(env, monkeypatch):
    _seed(env, source="claude_code")
    _turn_mode(monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([BASE_LAYER_FACT, SHORT_EMAIL_FACT]))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["accepted"] == 2
    assert "contamination_filter" not in rec["post_gate_drops"]
    assert sorted(f["object_text"] for f in _facts(env)) == [
        "building the base layer pipeline", "short emails to vendors"]
    assert rec["settings"]["contamination_filter"] is False


def test_legacy_validation_still_applies_the_contamination_filter():
    from baselayer.extract_facts import validate_structured_response
    raw = [{"subject": "user", "predicate": "builds", "object": "the base layer pipeline",
            "category": "skill", "confidence": 0.9},
           {"subject": "user", "predicate": "prefers", "object": "short emails to vendors",
            "category": "preference", "confidence": 0.9}]
    drops = {}
    kept = validate_structured_response(raw, 10, identity_only=True, drop_counter=drops)
    assert [f["object_text"] for f in kept] == ["short emails to vendors"]
    assert drops == {"contamination_filter": 1}


# ---------------------------------------------------------------------------
# 2. dynamic cap
# ---------------------------------------------------------------------------

def test_turn_mode_defaults_the_dynamic_cap_on(env, monkeypatch):
    _dense_seed(env)
    _turn_mode(monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", _dense_llm())
    env.ef.run_extraction()                       # would halt with the cap off
    rec = _records(env)[-1]
    assert rec["settings"]["dynamic_cap"] is True
    assert rec["counts"]["facts_stored"] == 48


def test_dynamic_cap_default_is_unchanged_on_the_legacy_path(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
    monkeypatch.delenv("BASELAYER_TURN_CONTRACT", raising=False)
    assert ef._dynamic_cap_enabled() is False
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    assert ef._dynamic_cap_enabled() is True
    monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "0")         # explicit off wins
    assert ef._dynamic_cap_enabled() is False


# ---------------------------------------------------------------------------
# 3. MIN_MESSAGES_FOR_EXTRACTION
# ---------------------------------------------------------------------------

SHORT = [(0, "subject", "own_typed", "user", "I prefer to review contracts on paper first."),
         (1, "subject", "own_typed", "user", "And I sign nothing on a Friday.")]


def test_turn_mode_extracts_short_prompt_only_conversations(env, monkeypatch):
    """A history.jsonl session is the subject's prompts with no assistant turns,
    often fewer than MIN_MESSAGES_FOR_EXTRACTION. The legacy selector skips it;
    turn mode keeps it."""
    from baselayer.config import MIN_MESSAGES_FOR_EXTRACTION
    assert len(SHORT) < MIN_MESSAGES_FOR_EXTRACTION
    _seed(env, source="claude_code_history", turns=SHORT)
    c = env.get_db()
    assert env.ef.get_conversations_to_process(c) == []            # legacy: skipped
    c.close()
    _turn_mode(monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(
        [_fact("signs nothing on a Friday", [("S2", "I sign nothing on a Friday.")])]))
    env.ef.run_extraction()
    assert [f["object_text"] for f in _facts(env)] == ["signs nothing on a Friday"]
    assert _records(env)[-1]["settings"]["min_messages_for_extraction"] is None


# ---------------------------------------------------------------------------
# 4. span length
# ---------------------------------------------------------------------------

LONG_TURN = "I keep a written log of every decision. " * 14      # ~560 chars


def test_out_of_bounds_spans_are_rejected_as_span_length(env, monkeypatch):
    turns = TURNS + [(6, "subject", "own_typed", "user", LONG_TURN.strip())]
    _seed(env, turns=turns)
    _turn_mode(monkeypatch)
    facts = [_fact("agrees to proceed", [("S2", "yes,")]),                          # 1 word
             _fact("keeps a decision log", [("S4", LONG_TURN.strip())]),           # > 400 chars
             _fact("short emails to vendors", [("S2", "Keep the email short.")])]  # in bounds
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(facts))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["gate_rejections"]["span_length"] == 2
    assert [f["object_text"] for f in _facts(env)] == ["short emails to vendors"]
    assert rec["settings"]["span_min_words"] == 3 and rec["settings"]["span_max_chars"] == 400


def test_span_bounds_are_configurable(env, monkeypatch):
    _seed(env)
    _turn_mode(monkeypatch)
    monkeypatch.setenv("BASELAYER_TURN_SPAN_MIN_WORDS", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([_fact("agrees to proceed", [("S2", "yes,")])]))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["gate_rejections"]["span_length"] == 0
    assert rec["settings"]["span_min_words"] == 1
    assert [f["object_text"] for f in _facts(env)] == ["agrees to proceed"]


def test_span_length_gate_unit():
    import baselayer.turn_contract as tc
    turns = [tc.Turn(f"c:{i}", "c", "subject", "own_typed", t, i, tc.TURN_CONTRACT_VERSION)
             for i, t in enumerate(["one two three four", "x " * 300])]
    chunk = tc.build_chunks(turns, 4000, context_budget=0, context_max_turns=0)[0]
    raw = [{"evidence_spans": [{"turn": "S1", "span": "one two"}]},
           {"evidence_spans": [{"turn": "S1", "span": "one two three"}]},
           {"evidence_spans": [{"turn": "S2", "span": ("x " * 201).strip()}]}]
    g = tc.gate_facts(raw, chunk, span_min_words=3, span_max_chars=400, referent=_REFERENT)
    assert g.rejected["span_length"] == 2 and len(g.accepted) == 1


# ---------------------------------------------------------------------------
# 5. needs_extraction (grown sessions)
# ---------------------------------------------------------------------------

def _mark(env, conv, needs, imported_at):
    c = env.get_db()
    c.execute("INSERT OR REPLACE INTO import_state (conversation_id, source, content_hash, n_turns, "
              "revision, status, needs_extraction, imported_at, turn_contract_version) "
              "VALUES (?, 'chatgpt', 'h', 6, 1, 'new', ?, ?, 'turn-contract/1')",
              (conv, needs, imported_at))
    c.commit()
    c.close()


def _needs(env, conv):
    c = env.get_db()
    v = c.execute("SELECT needs_extraction FROM import_state WHERE conversation_id=?",
                  (conv,)).fetchone()[0]
    c.close()
    return v


def test_grown_sessions_are_picked_up_and_the_mark_is_cleared(env, monkeypatch):
    _seed(env)
    _mark(env, CONV, 1, time.time() - 100)
    _turn_mode(monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(
        [_fact("short emails to vendors", [("S2", "Keep the email short.")])]))
    env.ef.run_extraction()
    assert _needs(env, CONV) == 0                                   # cleared on success

    # nothing new: a second run selects nothing
    c = env.get_db()
    assert env.ef.get_conversations_to_process(c, turn_mode=True) == []
    # the importer grows the session and re-marks it AFTER the last extraction
    c.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, text, "
              "turn_contract_version) VALUES (?, ?, 6, 'subject', 'own_typed', ?, 'turn-contract/1')",
              (f"{CONV}:6", CONV, "I review every invoice myself."))
    c.commit()
    c.close()
    _mark(env, CONV, 1, time.time() + 5)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(
        [_fact("reviews invoices personally", [("S4", "I review every invoice myself.")])]))
    env.ef.run_extraction()
    assert "reviews invoices personally" in [f["object_text"] for f in _facts(env)]
    assert _needs(env, CONV) == 0
    assert _records(env)[-1]["counts"]["grown_conversations"] == 1


def test_an_errored_conversation_is_not_retried_through_needs_extraction(env, monkeypatch):
    """needs_extraction is 1 on every fresh import, so it alone cannot mean
    'grown': an errored conversation would be re-selected on every run and
    bypass --retry-errors. Grown means re-imported AFTER the last extraction."""
    _seed(env)
    _mark(env, CONV, 1, time.time() - 100)
    c = env.get_db()
    c.execute("INSERT INTO extraction_log (conversation_id, facts_extracted, processed_at) "
              "VALUES (?, -1, ?)", (CONV, time.time()))
    c.commit()
    assert env.ef.get_conversations_to_process(c, turn_mode=True) == []
    c.close()


# ---------------------------------------------------------------------------
# selection skips conversations with nothing citable
# ---------------------------------------------------------------------------

HARNESS_ONLY = [(0, "subject", "harness_prompt", "user", "You are rating conditions. Reply in JSON."),
                (1, "assistant", "assistant", "assistant", "{\"verdicts\": []}")]


def test_turn_selection_skips_conversations_with_nothing_citable(env, monkeypatch):
    """Most imported sessions can hold no citable turn at all (harness children,
    tool-only sessions). They make no model call, but if the selector returns them,
    `--limit N` spends its N on sessions that cannot yield a fact. A conversation
    with NO turn rows is still selected, so the missing-import error stays loud."""
    _seed(env, conv="a-harness", turns=HARNESS_ONLY)       # created first, sorts first
    _seed(env, conv="b-own")
    _seed(env, conv="c-no-turns", with_turns=False)
    c = env.get_db()
    c.execute("UPDATE conversations SET created_at = CASE id WHEN 'a-harness' THEN 1 "
              "WHEN 'b-own' THEN 2 ELSE 3 END")
    c.commit()
    ids = [r["id"] for r in env.ef.get_conversations_to_process(c, turn_mode=True)]
    assert ids == ["b-own", "c-no-turns"]
    assert [r["id"] for r in env.ef.get_conversations_to_process(c, turn_mode=True, limit=1)] == ["b-own"]
    c.close()
