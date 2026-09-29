"""
The three halves of the turn contract, end to end, on synthetic data.

1. IMPORT with the real importers into a fresh temp corpus directory: a Claude
   Code session, a ChatGPT export, a history.jsonl and a meeting transcript.
2. EXTRACT in turn mode with a fake model that proposes a mix of facts:
   grounded in the subject's own words, grounded in the assistant's words,
   grounded in pasted text, grounded in another meeting participant's words,
   ungrounded, and grounded on a span too short to mean anything.
3. VERIFY a tiny synthetic specification that cites the stored facts, with
   the deterministic checks only (dry run, no model).

The assertions are the gate outcomes (which facts were stored, the counted
rejection reasons) and the verification mode. A second test runs the LEGACY
path on the same imported corpus, which must still work, and checks that
verification then runs in fallback mode.

No API calls, no model calls, no network, no embedding model download;
everything is written under tmp_path, and the test asserts that.
"""

import json
import re
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import baselayer.import_conversations as IC
from tests.test_turn_contract_import import (
    LONG_ASSISTANT, _cg_conv, _cg_node, assistant, typed, uid, write_session)
from tests.test_turn_extraction import FakeClient, FakeST

V = "turn-contract/1"
CANARY = "SYNTHETIC CANARY 7f3a: injected background follows"

CC_SID = "sess-e2e"
CC_OWN_1 = "I want the release notes written before the demo on Thursday."
CC_ASSISTANT = "I think you value polish over speed, so I will draft carefully."
CC_OWN_2 = "Keep the release notes under one page and link the changelog."
CC_OWN_BL = "I am building Base Layer so the pipeline reads only my own words."

CG_OWN_1 = "what is the retention policy for the archive?"
CG_OWN_2 = "I would rather keep the monthly drill because it catches problems early"

HIST_OWN = "rename the export folder to match the release tag"
HIST_PASTE = "line one of a pasted log\nline two of a pasted log"

MEETING = """# Weekly sync

  Meeting started: 1/5/2026, 9:00:00 AM
  Participants: Pat Q, Lee R

  ## Transcript

00:01 Pat Q: I think we should ship the smaller version first and learn from it
00:02 Lee R: That works for me and I can write the release note tonight
00:03 Pat Q: then let's do it on Monday morning
"""


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------

@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A fresh corpus directory with the real importers run into it."""
    import baselayer.config as cfg
    import baselayer.extract_facts as ef
    from baselayer.init_database import init_database

    root = tmp_path / "corpus"
    db = root / "data" / "database" / "memory.db"
    init_database(db)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", root)
    monkeypatch.setattr(cfg, "DATABASE_FILE", db)

    conf = tmp_path / "import_config.json"
    conf.write_text(json.dumps({"meeting_subject_labels": ["Pat Q"],
                                "subject_names": ["Pat Q"],
                                "canary_strings": [CANARY]}), encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(conf))

    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(IC, "CLAUDE_PROJECTS_DIR", projects)
    hook = {"type": "attachment", "uuid": uid(), "sessionId": CC_SID,
            "attachment": {"type": "hook_additional_context", "hookEvent": "SessionStart",
                           "content": [CANARY + " ... spec text ..."]}}
    write_session(projects, CC_SID, [hook, typed(CC_OWN_1, CC_SID), assistant(CC_ASSISTANT, CC_SID),
                                     typed(CC_OWN_2, CC_SID), assistant("Done.", CC_SID),
                                     typed(CC_OWN_BL, CC_SID)])

    export = tmp_path / "conversations.json"
    export.write_text(json.dumps([_cg_conv("cg-e2e", [
        _cg_node("n1", None, "user", CG_OWN_1, 1.0),
        _cg_node("n2", "n1", "assistant", LONG_ASSISTANT, 2.0),
        _cg_node("n3", "n2", "user", LONG_ASSISTANT + "\n\n" + CG_OWN_2, 3.0),
    ])]), encoding="utf-8")

    history = tmp_path / "history.jsonl"
    history.write_text("\n".join(json.dumps(e) for e in [
        {"display": HIST_OWN, "pastedContents": {}, "timestamp": 1000, "project": "/p",
         "sessionId": "h-e2e"},
        {"display": "look at this [Pasted text #1 +2 lines] and tell me why it failed",
         "pastedContents": {"1": {"id": 1, "type": "text", "content": HIST_PASTE}},
         "timestamp": 2000, "project": "/p", "sessionId": "h-e2e"},
    ]) + "\n", encoding="utf-8")

    meeting = tmp_path / "meetings" / "sync.txt"
    meeting.parent.mkdir()
    meeting.write_text(MEETING, encoding="utf-8")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    # Transcripts before history: history dedupes against transcript text.
    IC.import_claude_code(conn, IC.get_existing_conversation_ids(conn))
    IC.import_chatgpt(conn, str(export), set())
    IC.import_history(conn, [history], set())
    IC.import_meetings(conn, meeting, set())
    conn.commit()
    conn.close()

    FakeClient.collection = None
    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=FakeClient))
    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        types.SimpleNamespace(SentenceTransformer=FakeST))
    for var in ("BASELAYER_TURN_CONTRACT", "BASELAYER_DYNAMIC_CAP", "BASELAYER_SKIP_COVERAGE_GATE",
                "BASELAYER_TURN_SPAN_MIN_WORDS", "BASELAYER_TURN_SPAN_MAX_CHARS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")

    # Everything this test writes must be under tmp_path, never the served data.
    with ef.get_db() as c:
        path = Path(c.execute("PRAGMA database_list").fetchone()[2]).resolve()
    assert tmp_path.resolve() in path.parents
    return types.SimpleNamespace(root=root, db=db, tmp=tmp_path, ef=ef)


def _rows(db, sql, args=()):
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    out = [dict(r) for r in c.execute(sql, args)]
    c.close()
    return out


def _turn_id(db, conv, voice, contains):
    for r in _rows(db, "SELECT turn_id, voice_class, text FROM turns WHERE conversation_id=?", (conv,)):
        if r["voice_class"] == voice and contains in r["text"]:
            return r["turn_id"]
    raise AssertionError(f"no {voice} turn in {conv} containing {contains!r}")


def _alias(prompt, phrase):
    """The S<n> alias of the citable turn whose text contains `phrase`."""
    for alias, body in re.findall(r"\[(S\d+) \| SUBJECT[^\]]*\]\n(.*?)(?=\n\n\[|\Z)", prompt, re.S):
        if phrase in body:
            return alias
    return None


def _fact(obj, spans, predicate="prefers", category="preference"):
    return {"subject": "user", "predicate": predicate, "object": obj, "qualifier": "unknown",
            "category": category, "temporal": "current", "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn": t, "span": s} for t, s in spans]}


# ---------------------------------------------------------------------------
# 1 + 2 + 3: import, turn-mode extraction, verification
# ---------------------------------------------------------------------------

def test_import_extract_verify_under_the_turn_contract(corpus, monkeypatch):
    db = corpus.db
    # ---- import: the voice classes the gate will rely on
    classes = {(r["conversation_id"], r["voice_class"]) for r in _rows(db, "SELECT * FROM turns")}
    assert (CC_SID, "own_typed") in classes and (CC_SID, "assistant") in classes
    assert ("cg-e2e", "pasted") in classes                   # quote-back of the assistant
    assert ("history_h-e2e", "pasted") in classes             # [Pasted text #1]
    meeting_id = _rows(db, "SELECT id FROM conversations WHERE source='meeting'")[0]["id"]
    assert (meeting_id, "own_dictated") in classes and (meeting_id, "other_person") in classes
    assert _rows(db, "SELECT conversation_id, flag FROM conversation_flags") == [
        {"conversation_id": CC_SID, "flag": "injection_canary"}]
    # the history session has 2 legacy messages: below MIN_MESSAGES_FOR_EXTRACTION
    from baselayer.config import MIN_MESSAGES_FOR_EXTRACTION
    hist_msgs = _rows(db, "SELECT message_count FROM conversations WHERE id='history_h-e2e'")
    assert hist_msgs[0]["message_count"] < MIN_MESSAGES_FOR_EXTRACTION

    ids = {
        "cc_assistant": _turn_id(db, CC_SID, "assistant", "polish over speed"),
        "cg_pasted": _turn_id(db, "cg-e2e", "pasted", "retention policy keeps"),
        "hist_pasted": _turn_id(db, "history_h-e2e", "pasted", "pasted log"),
        "meet_other": _turn_id(db, meeting_id, "other_person", "release note tonight"),
    }

    # ---- extraction: a fake model proposing a mix, keyed on what the prompt shows
    def fake_llm(prompt, schema=None, retries=None, max_tokens=None):
        facts = []
        if CC_OWN_2 in prompt:
            facts += [
                _fact("release notes under one page", [(_alias(prompt, CC_OWN_2), "Keep the release notes under one page")]),
                _fact("building Base Layer from own words",                         # kept: filter off
                      [(_alias(prompt, CC_OWN_BL), "I am building Base Layer")], "builds", "project"),
                _fact("values polish over speed", [(ids["cc_assistant"], "you value polish over speed")],
                      "values", "value"),                                            # not_own_voice
                _fact("values polish, paraphrased", [(_alias(prompt, CC_OWN_2), "I value polish over speed")],
                      "values", "value"),                                            # span_not_found
                {"subject": "user", "predicate": "values", "object": "careful drafting",
                 "category": "value", "confidence": 0.9},                            # no_grounding
            ]
        if CG_OWN_2 in prompt:
            facts += [
                _fact("keeps the monthly drill", [(_alias(prompt, CG_OWN_2), "keep the monthly drill")]),
                _fact("weekly snapshots for ninety days", [(ids["cg_pasted"], "weekly snapshots for ninety days")],
                      "practices", "habit"),                                         # not_own_voice (pasted)
            ]
        if HIST_OWN in prompt:
            facts += [
                _fact("names folders after release tags", [(_alias(prompt, HIST_OWN), "rename the export folder")],
                      "practices", "habit"),
                _fact("reads logs", [(ids["hist_pasted"], "line one of a pasted log")],
                      "practices", "habit"),                                         # not_own_voice (pasted)
            ]
        if "ship the smaller version first" in prompt:
            facts += [
                _fact("ships small first", [(_alias(prompt, "ship the smaller version first"),
                                             "ship the smaller version first")], "prefers", "preference"),
                _fact("writes release notes", [(ids["meet_other"], "I can write the release note")],
                      "practices", "habit"),                                         # not_own_voice (other person)
                _fact("agrees to proceed", [(_alias(prompt, "let's do it"), "then let's")],
                      "decided", "decision"),                                        # span_length (2 words)
            ]
        return {"facts": facts}

    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(corpus.ef, "call_llm", fake_llm)
    corpus.ef.run_extraction()

    stored = {f["object_text"]: f for f in _rows(db, "SELECT * FROM memory_facts")}
    assert sorted(stored) == sorted([
        "release notes under one page", "building Base Layer from own words",
        "keeps the monthly drill", "names folders after release tags", "ships small first"])
    for f in stored.values():
        assert f["turn_contract_version"] == V and f["voice_class"] in ("own_typed", "own_dictated")
        spans = json.loads(f["evidence_spans"])
        assert spans and all(set(s) == {"turn_id", "span", "evidence_kind"} for s in spans)
        assert f["source_turn_id"] == spans[0]["turn_id"]
    assert stored["ships small first"]["voice_class"] == "own_dictated"

    runs = sorted((json.loads(p.read_text(encoding="utf-8"))
                   for p in (corpus.root / "data" / "database" / "extraction_runs").glob("*.json")),
                  key=lambda r: r["started_at"])
    rec = runs[-1]
    assert rec["gate_rejections"] == {"no_grounding": 1, "no_turn": 0, "not_own_voice": 4,
                                      "span_not_found": 1, "span_length": 1, "self_object": 0}
    assert rec["counts"]["candidates"] == 12 and rec["counts"]["accepted"] == 5
    assert rec["post_gate_drops"] == {}
    assert rec["settings"]["dynamic_cap"] is True and rec["settings"]["contamination_filter"] is False
    assert rec["suspect"] == []
    # every conversation marked for extraction by the importer was extracted and cleared
    assert _rows(db, "SELECT COUNT(*) AS n FROM import_state WHERE needs_extraction=1")[0]["n"] == 0

    # ---- verification: a tiny spec citing the stored facts, deterministic checks only
    fid = {k: "F-" + v["id"][:8] for k, v in stored.items()}
    spec = corpus.tmp / "spec"
    spec.mkdir()
    (spec / "anchors.json").write_text(json.dumps({"layer": "anchors", "preamble": "", "claims": [
        {"id": "A1", "name": "SHIPS SMALL", "statement": "Ships a small version first.",
         "active_when": "A release is being planned", "contested": False,
         "fact_ids": [fid["ships small first"], fid["release notes under one page"]]},
        {"id": "A2", "name": "KEEPS DRILLS", "statement": "Keeps recurring checks.",
         "active_when": "An operational routine is questioned", "contested": False,
         "fact_ids": [fid["keeps the monthly drill"], fid["names folders after release tags"],
                      fid["building Base Layer from own words"]]},
    ]}), encoding="utf-8")
    from baselayer.verification import run as vrun
    out = corpus.tmp / "verify_out"
    rc = vrun.main([str(spec), "--label", "e2e", "--corpus", str(corpus.root), "--out", str(out)])
    assert rc == 0
    rep = json.loads((out / "e2e.verification.json").read_text(encoding="utf-8"))
    assert rep["meta"]["voice_mode"] == "turn_contract"
    assert rep["meta"]["voice_modes"] == {"turn_contract": 5}
    assert rep["meta"]["turn_table"] == "turns"
    bad = [f for f in rep["findings"] if f["check"] in ("turn_gate_failed", "unresolved_citation")]
    assert bad == []
    rows = {r["id"]: r for p in rep["claims"].values() for r in p["facts"]}
    assert all(r["turn_ids"] and r["own"] is True for r in rows.values())
    assert rows[fid["ships small first"]]["voice"] == "own_dictated"
    assert rep["meta"]["model"]["status"] == "dry_run"


# ---------------------------------------------------------------------------
# the legacy path still runs on a corpus the new importer wrote
# ---------------------------------------------------------------------------

def test_legacy_path_runs_on_the_imported_corpus_and_verifies_in_fallback(corpus, monkeypatch):
    """`baselayer run` extracts on the legacy path. The importer writes turn rows
    AND the legacy messages projection, so the legacy path must keep working on a
    freshly imported corpus. Its facts carry no contract version, so verification
    runs them in fallback mode even though every turn-contract column exists."""
    def legacy_llm(prompt, schema=None, retries=None, max_tokens=None):
        return {"facts": [{"subject": "user", "predicate": "prefers", "object": "short release notes",
                           "qualifier": "unknown", "category": "preference", "temporal": "current",
                           "confidence": 0.9}]}

    monkeypatch.setattr(corpus.ef, "call_llm", legacy_llm)
    monkeypatch.setattr(corpus.ef, "MIN_MESSAGES_FOR_EXTRACTION", 1)
    corpus.ef.run_extraction()
    facts = _rows(corpus.db, "SELECT id, turn_contract_version, source_turn_id FROM memory_facts")
    assert facts and all(f["turn_contract_version"] is None and f["source_turn_id"] is None
                         for f in facts)

    spec = corpus.tmp / "spec"
    spec.mkdir()
    (spec / "anchors.json").write_text(json.dumps({"layer": "anchors", "preamble": "", "claims": [
        {"id": "A1", "name": "SHORT NOTES", "statement": "Prefers short notes.",
         "active_when": "Writing release notes", "contested": False,
         "fact_ids": ["F-" + facts[0]["id"][:8]]}]}), encoding="utf-8")
    from baselayer.verification import run as vrun
    out = corpus.tmp / "verify_out"
    assert vrun.main([str(spec), "--label", "e2e", "--corpus", str(corpus.root), "--out", str(out)]) == 0
    rep = json.loads((out / "e2e.verification.json").read_text(encoding="utf-8"))
    assert rep["meta"]["turn_columns"] is True
    assert rep["meta"]["voice_mode"] == "fallback"
    assert not [f for f in rep["findings"] if f["check"] == "turn_gate_failed"]
