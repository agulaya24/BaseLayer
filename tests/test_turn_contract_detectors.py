"""
Planted known-bad inputs for the detectors and guards that a mutation run found
unpinned (drift audit of feat/respec-hardening; TURN_CONTRACT.md §2 requires every
detector to be shown failing on a planted input).

Each test targets ONE rule. It feeds the input that rule exists to catch and
asserts the outcome that only that rule produces, so switching the rule off (the
audit's mutants V01-V18, G02, G10, G11, R01) turns the test red.

Everything is synthetic; no API calls.
"""

import json
import subprocess
import types

import pytest

import baselayer.turn_contract as tc
import baselayer.voice as V
from baselayer.turn_contract import Referent as _Referent  # noqa: E402
_REFERENT = _Referent(names=("Dana Reyes",))


def _classes(text, **kw):
    c = V.classify_subject_text(text, **kw)
    return [(text[s.start:s.end].strip(), s.voice_class, s.detector or s.basis) for s in c.segments]


# ---------------------------------------------------------------------------
# voice.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("[tool result]", True),
    ("  [tool result]\n", True),
    ("see the [tool result] above and fix it", False),    # equality, not containment
    ("[tool results]", False),
    ("", False),
])
def test_tool_result_placeholder_is_an_exact_match(text, expected):
    assert V.is_tool_result_placeholder(text) is expected


def test_code_paste_signal_marks_pasted_code():
    """Two code lines with no fence, no log line and no other signal: only the code
    signal can make this segment pasted (V05)."""
    code = "def total(xs):\n    return sum(xs)\nimport os"
    f = V.features(code, V.VoiceSettings())
    assert V.paste_score(code, f, V.VoiceSettings()) >= 2
    got = _classes("why does this fail\n\n" + code)
    assert got == [("why does this fail", "own_typed", V.B_ROLE),
                   (code, "pasted", V.D_PASTE_STRUCTURAL)]


def test_terminal_prompt_signal_marks_pasted_terminal_output():
    """A line copied from a terminal prompt (V10)."""
    term = "❯ npm run build\nbuild failed with exit code 2"
    got = _classes("what happened here\n\n" + term)
    assert got[-1] == (term, "pasted", V.D_PASTE_STRUCTURAL)
    assert got[0][1] == "own_typed"


def test_typo_penalty_keeps_hastily_typed_lists_as_own_words():
    """A typed list with typing artifacts. Its three list lines alone score as a paste;
    the typo penalty is what keeps it the subject's own words (V11)."""
    seg = ("- i dont think teh first plan works for the team this week at all\n"
           "- we should move the launch and tell the vendor early about it\n"
           "- lets keep the budget flat and review it again next month")
    s = V.VoiceSettings()
    f = V.features(seg, s)
    assert f["typos"] >= 2 and f["words"] >= 25
    assert V.paste_score(seg, f, s) < s.paste_score_threshold
    assert [c[1] for c in _classes(seg, detect_dictation=False)] == ["own_typed"]


def test_dictated_run_on_text_is_reclassed_own_dictated():
    """Speech-to-text artifacts: one long unpunctuated line with mid-sentence capitals
    (V06)."""
    spoken = ("so I was thinking about the launch plan And then we could ship the smaller "
              "version first Right after that we measure what people actually use So basically "
              "we learn before we build the rest of it and keep the budget where it is")
    got = _classes(spoken)
    assert got == [(spoken, "own_dictated", V.B_DICTATION)]
    assert _classes(spoken, detect_dictation=False)[0][1] == "own_typed"


def test_paste_tag_placeholder_is_its_own_pasted_segment():
    """A history.jsonl paste placeholder with no pasted content supplied: the tag
    itself is split out and classed pasted (V08), not left as the subject's words."""
    got = _classes("look at this [Pasted text #1 +3 lines] and tell me why it failed")
    assert got == [("look at this", "own_typed", V.B_ROLE),
                   ("[Pasted text #1 +3 lines]", "pasted", V.D_PASTE_TAG),
                   ("and tell me why it failed", "own_typed", V.B_ROLE)]


def test_harness_template_text_is_pasted(tmp_path):
    """A prompt copied from a harness script's string literal (V09), through the real
    TemplateIndex built from a scripts directory."""
    literal = ("You are rating whether each condition below applies to the proposed action. "
               "Answer with one JSON object per condition and nothing else, and never explain.")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "rater.py").write_text(f"PROMPT = {literal!r}\n", encoding="utf-8")
    idx = V.TemplateIndex([tmp_path / "scripts"])
    assert idx and idx.is_template(literal)
    got = _classes("ok run it again\n\n" + literal, template_scorer=idx.hits)
    assert got == [("ok run it again", "own_typed", V.B_ROLE),
                   (literal, "pasted", V.D_PASTE_TEMPLATE)]
    assert not V.TemplateIndex([tmp_path / "missing"])        # no roots, no template


# ---------------------------------------------------------------------------
# turn_import.py: record rules, through the real Claude Code importer
# ---------------------------------------------------------------------------

from tests.test_turn_contract_import import (  # noqa: E402  (fixtures reused)

    cc_import, env, rec, typed, write_session)


def _rows(env, sid):
    return [dict(r) for r in env.conn.execute(
        "SELECT voice_class, detector, basis, text FROM turns WHERE conversation_id=? "
        "ORDER BY ordinal, COALESCE(segment, -1)", (sid,))]


def test_is_meta_record_is_a_harness_prompt(env):
    """A user-role record flagged isMeta is harness-injected, even when it otherwise
    looks typed by a human (V14)."""
    write_session(env.projects, "s-meta", [
        typed("Caveat free text the harness injected for the model to read", "s-meta", isMeta=True),
        typed("a real question from the subject", "s-meta")])
    cc_import(env)
    rows = _rows(env, "s-meta")
    assert rows[0]["voice_class"] == "harness_prompt" and rows[0]["detector"] == V.D_IS_META
    assert rows[1]["voice_class"] == "own_typed"


def test_queued_human_prompt_is_the_subjects_words_even_under_sdk_cli(env):
    """promptSource=queued with a human origin is the subject typing while the
    assistant works (V15). Under an sdk-cli entrypoint it must still count as human,
    not fall to the harness rule."""
    write_session(env.projects, "s-q", [
        typed("please also update the changelog", "s-q", promptSource="queued",
              entrypoint="sdk-cli")])
    cc_import(env)
    rows = _rows(env, "s-q")
    assert [(r["voice_class"], r["detector"]) for r in rows] == [("own_typed", None)]


def test_cross_agent_relay_is_a_harness_prompt(env):
    """A message relayed from another agent session arrives in a user record (V18)."""
    write_session(env.projects, "s-relay", [
        typed("Another Claude session sent a message: the build is green, proceed", "s-relay")])
    cc_import(env)
    rows = _rows(env, "s-relay")
    assert [(r["voice_class"], r["detector"]) for r in rows] == [("harness_prompt", V.D_CROSS_AGENT)]


# ---------------------------------------------------------------------------
# turn_contract.py: the gate's defence-in-depth layers and `inferred`
# ---------------------------------------------------------------------------

def _turns():
    return [tc.Turn("c:0", "c", "subject", "own_typed", "I want the report done on Friday.", 0, tc.TURN_CONTRACT_VERSION),
            tc.Turn("c:1", "c", "assistant", "assistant", "You value speed over polish.", 1, tc.TURN_CONTRACT_VERSION)]


def test_build_chunks_offers_only_citable_text():
    """Only own-voice turns may enter citable_texts (G11): the gate's substring check
    reads from it."""
    ch = tc.build_chunks(_turns(), 4000, context_budget=0, context_max_turns=0)[0]
    assert set(ch.citable_texts) == {"c:0"}
    assert set(ch.alias_to_turn.values()) == {"c:0"}


def test_gate_checks_voice_even_if_a_chunk_offers_non_own_text():
    """Defence in depth (G02): if a chunk were ever built with a non-own turn in
    citable_texts, the gate's own voice check still rejects a span citing it."""
    ch = tc.Chunk(1, 1, [], [], {"S1": "c:1"}, {"c:1": "assistant"},
                  {"c:1": ["You value speed over polish."]})
    g = tc.gate_facts([{"evidence_spans": [{"turn": "S1", "span": "You value speed over polish."}]}],
                      ch, span_min_words=0, span_max_chars=0, referent=_REFERENT)
    assert g.rejected["not_own_voice"] == 1 and not g.accepted


@pytest.mark.parametrize("raw,expected", [
    ("false", False), ("False ", False), ("no", False), ("0", False), ("", False),
    ("true", True), ("TRUE", True), ("yes", True), ("1", True), ("inferred", True),
    (True, True), (False, False), (1, True), (0, False), (None, False),
    (2, False), ([], False), (["true"], False), ({"x": 1}, False),
])
def test_inferred_is_coerced_strictly(raw, expected):
    """G10: `bool("false")` is True. Only an explicit true value marks a fact inferred."""
    ch = tc.build_chunks(_turns(), 4000, context_budget=0, context_max_turns=0)[0]
    g = tc.gate_facts([{"inferred": raw, "evidence_spans": [{"turn": "S1", "span": "the report done on Friday"}]}], ch, referent=_REFERENT)
    assert g.accepted[0]["inferred"] is expected


# ---------------------------------------------------------------------------
# stamps outside a git checkout
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failure", ["not_a_repo", "no_git_binary"])
def test_stamps_fall_back_outside_a_git_checkout(monkeypatch, failure):
    """An installed wheel or an exported tree has no git. The stamp must still be
    relative and must say the commit is unknown, never raise or go absolute."""
    def fake_run(*a, **k):
        if failure == "no_git_binary":
            raise FileNotFoundError("git")
        return types.SimpleNamespace(returncode=128, stdout="", stderr="not a git repository")

    monkeypatch.setattr(subprocess, "run", fake_run)
    st = tc.extraction_stamp("m", "h", code_file=tc.__file__)
    assert st["code_path"] == "baselayer/turn_contract.py"
    assert st["git_commit"] == "unknown"


# ---------------------------------------------------------------------------
# verification: a claim that cites nothing
# ---------------------------------------------------------------------------

def test_verification_flags_a_claim_with_no_citations(tmp_path):
    """R01: an uncited claim is an error finding, not a silently empty profile."""
    from baselayer.init_database import init_database
    from baselayer.verification.corpus import Corpus, open_readonly
    from baselayer.verification.deterministic import check_facts
    from baselayer.verification.spec_io import load_spec
    db = tmp_path / "corpus" / "data" / "database" / "memory.db"
    init_database(db)
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "anchors.json").write_text(json.dumps({"layer": "anchors", "preamble": "", "claims": [
        {"id": "A1", "name": "UNCITED", "statement": "s", "active_when": "w", "contested": False,
         "fact_ids": []}]}), encoding="utf-8")
    conn, info = open_readonly(db, tmp_path / "out" / "_snap")
    try:
        _, findings = check_facts(load_spec(spec, "t"), Corpus(conn, info))
    finally:
        conn.close()
    assert [(f["check"], f["severity"], f["claims"]) for f in findings] == [
        ("no_citations", "error", ["t:A1"])]
