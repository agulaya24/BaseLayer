"""The planted known-bad pilot sessions (baselayer.turn_contract_fixtures). No API calls.

The sessions are imported with the REAL Claude Code importer into a temp database, then:
  - check_import must report nothing (every planted turn classed as the manifest says), and must
    report a problem when the importer is weakened, or it is not a check;
  - a fake model that cites every planted turn's probe span is gated the way extraction gates:
    only own-voice spans are accepted;
  - check_stored_facts must flag a stored fact that rests on a planted bad turn.
The canary is a synthetic marker; the real sentence is never written into the tree.
"""
import json
import sqlite3

import pytest

import baselayer.import_conversations as IC
from baselayer import turn_contract as tc
from baselayer import turn_contract_fixtures as F

from baselayer.turn_contract import Referent as _Referent  # noqa: E402
_REFERENT = _Referent(names=("Dana Reyes",))

MARKER = "SYNTHETIC PLANTED MARKER 91c2"


@pytest.fixture
def planted(tmp_path, monkeypatch):
    from baselayer.init_database import init_database
    db = tmp_path / "data" / "database" / "memory.db"
    init_database(db)
    conf = tmp_path / "import_config.json"
    conf.write_text(json.dumps({"canary_strings": [MARKER]}), encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(conf))
    monkeypatch.setattr(IC, "CLAUDE_PROJECTS_DIR", tmp_path / "no-real-projects")
    manifest = F.write_planted_sessions(tmp_path / "planted", canary=MARKER)

    def do_import():
        conn = sqlite3.connect(str(db))
        IC.import_claude_code(conn, IC.get_existing_conversation_ids(conn),
                              session_files=manifest["files"])
        conn.commit()
        return conn
    return manifest, do_import


def test_manifest_and_files_are_synthetic_and_prefixed(planted, tmp_path):
    manifest, _ = planted
    assert (tmp_path / "planted" / F.MANIFEST_NAME).exists()
    assert len(manifest["files"]) == 6
    for sid in manifest["sessions"]:
        assert sid.startswith(F.PLANTED_PREFIX)
    kinds = {e["voice_class"] for s in manifest["sessions"].values() for e in s["expect"]}
    assert kinds == {"own_typed", "compaction_summary", "harness_prompt", "pasted",
                     "tool_result"}
    # no canary unless one is passed
    assert not any(s.sid.endswith("canary") for s in F.planted_sessions())


def test_real_importer_classifies_every_planted_turn(planted):
    manifest, do_import = planted
    conn = do_import()
    assert F.check_import(conn, manifest) == []


def test_check_import_fails_when_the_paste_detector_is_weakened(planted, monkeypatch):
    """The check must be able to fail: with the structural and terminal paste rules disabled,
    the log block is stored as the subject's own words and check_import has to say so."""
    import baselayer.voice as V
    monkeypatch.setattr(V, "paste_score", lambda seg, f, settings: 0)
    monkeypatch.setattr(V, "is_terminal_segment", lambda seg: False)
    manifest, do_import = planted
    problems = F.check_import(do_import(), manifest)
    assert any("paste_block" in p for p in problems), problems


def test_gate_accepts_only_the_own_voice_probes(planted):
    import baselayer.extract_facts as ef
    manifest, do_import = planted
    conn = do_import()
    for sid, sess in manifest["sessions"].items():
        turns = tc.load_turns(conn, sid)
        by_text = {t.text: t for t in turns}
        chunks = ef.build_turn_chunks(turns, "claude_code", 10_000_000)
        assert len(chunks) == 1, sid
        for e in sess["expect"]:
            t = by_text[e["text"]]
            fact = {"subject": "user", "predicate": "prefers", "object": "x",
                    "category": "preference", "confidence": 0.9,
                    "evidence_spans": [{"turn_id": t.turn_id, "span": e["probe_span"]}]}
            g = tc.gate_facts([fact], chunks[0], referent=_REFERENT)
            if e["citable"]:
                assert len(g.accepted) == 1, (sid, e["key"], dict(g.rejected))
            else:
                assert not g.accepted, (sid, e["key"])
                assert g.rejected["not_own_voice"] + g.rejected["no_turn"] == 1, (
                    sid, e["key"], dict(g.rejected))


def test_check_stored_facts_flags_a_fact_resting_on_a_planted_bad_turn(planted):
    manifest, do_import = planted
    conn = do_import()
    sid = F.PLANTED_PREFIX + "compaction"
    rows = dict(conn.execute("SELECT text, turn_id FROM turns WHERE conversation_id=?",
                             (sid,)).fetchall())
    own, bad = rows[F.OWN_FACT], rows[F.COMPACT_FLAGGED]
    for fid, tid in (("f-own", own), ("f-bad", bad)):
        conn.execute("INSERT INTO memory_facts (id, fact_text, source_conversation_id, "
                     "evidence_spans) VALUES (?,?,?,?)",
                     (fid, "x", sid, json.dumps([{"turn_id": tid, "span": "y"}])))
    problems = F.check_stored_facts(conn, manifest)
    assert len(problems) == 1 and "f-bad" in problems[0] and "compaction_summary" in problems[0]


# --- AUDN NOOP merges spans across conversations: a fact stored under one conversation can
# cite turns of another. The check resolves every span's turn corpus-wide.

def _insert_fact(conn, fid, conv, turn_ids):
    conn.execute("INSERT INTO memory_facts (id, fact_text, source_conversation_id, "
                 "evidence_spans) VALUES (?,?,?,?)",
                 (fid, "x", conv, json.dumps([{"turn_id": t, "span": "y"} for t in turn_ids])))


def _real_turn(conn, conv="real-conv-0001", voice_class="own_typed"):
    tid = f"{conv}:0"
    conn.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, "
                 "text, turn_contract_version) VALUES (?,?,?,?,?,?,?)",
                 (tid, conv, 0, "subject", voice_class, "real text", "test"))
    return tid


def _turn(conn, sid, text):
    return conn.execute("SELECT turn_id FROM turns WHERE conversation_id=? AND text=?",
                        (sid, text)).fetchone()[0]


def test_check_stored_facts_accepts_a_merged_span_on_another_conversations_citable_turn(planted):
    manifest, do_import = planted
    conn = do_import()
    comp, harn = F.PLANTED_PREFIX + "compaction", F.PLANTED_PREFIX + "harness"
    real = _real_turn(conn)
    _insert_fact(conn, "f-merged", comp,
                 [_turn(conn, comp, F.OWN_FACT), _turn(conn, harn, F.OWN_FACT), real])
    assert F.check_stored_facts(conn, manifest) == []


def test_check_stored_facts_flags_a_merged_span_on_another_planted_sessions_bad_turn(planted):
    manifest, do_import = planted
    conn = do_import()
    comp, harn = F.PLANTED_PREFIX + "compaction", F.PLANTED_PREFIX + "harness"
    bad = _turn(conn, comp, F.COMPACT_FLAGGED)
    _insert_fact(conn, "f-cross", harn, [_turn(conn, harn, F.OWN_FACT), bad])
    problems = F.check_stored_facts(conn, manifest)
    assert len(problems) == 1
    assert "f-cross" in problems[0] and bad in problems[0] and "compaction_summary" in problems[0]


def test_check_stored_facts_flags_a_real_fact_that_cites_a_planted_bad_turn(planted):
    manifest, do_import = planted
    conn = do_import()
    harn = F.PLANTED_PREFIX + "harness"
    bad = _turn(conn, harn, F.HARNESS_META)
    real = _real_turn(conn)
    _insert_fact(conn, "f-real", "real-conv-0001", [real, bad])
    problems = F.check_stored_facts(conn, manifest)
    assert len(problems) == 1 and "f-real" in problems[0] and "harness_prompt" in problems[0]


def test_check_stored_facts_still_flags_a_span_that_resolves_nowhere(planted):
    manifest, do_import = planted
    conn = do_import()
    comp = F.PLANTED_PREFIX + "compaction"
    _insert_fact(conn, "f-ghost", comp, [_turn(conn, comp, F.OWN_FACT), comp + ":999"])
    _insert_fact(conn, "f-ghost2", "real-conv-0001", [F.PLANTED_PREFIX + "harness:999"])
    problems = F.check_stored_facts(conn, manifest)
    assert len(problems) == 2
    assert all("unknown turn" in p for p in problems)
    assert any("f-ghost:" in p or "f-ghost " in p for p in problems)
    assert any("f-ghost2" in p for p in problems)


def test_check_stored_facts_ignores_superseded_facts_across_conversations(planted):
    manifest, do_import = planted
    conn = do_import()
    bad = _turn(conn, F.PLANTED_PREFIX + "compaction", F.COMPACT_FLAGGED)
    _insert_fact(conn, "f-old", "real-conv-0001", [bad])
    conn.execute("UPDATE memory_facts SET superseded_by='f-new' WHERE id='f-old'")
    assert F.check_stored_facts(conn, manifest) == []
