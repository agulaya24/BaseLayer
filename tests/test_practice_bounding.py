"""
Domain bounding: a pattern that rests on one practice must not read as a general trait.

1. Import tags rows re-classed by the own-writing rule with a ``practice``
   (``turns.practice``, see test_own_writing_allowlist.py).
2. Extraction carries it to every stored fact (``memory_facts.practice``), read from
   the turns the fact's evidence spans cite: the tag when every span's turn carries the
   same one, NULL when none does, and the sorted tags joined by ``+`` (``general`` for an
   untagged turn) when they differ.
3. Verification reports, per claim, how its live cited facts spread across practices
   and categories, and flags ``bounded:<practice>`` when every live cited fact carries
   the same practice tag. Report only: the spec is never edited.

Synthetic data, fake model, no API calls; everything under tmp_path.
"""
import hashlib
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import baselayer.import_conversations as IC
from baselayer.turns import ensure_turn_tables

from tests.test_own_writing_allowlist import JOURNAL, OPENER
from tests.test_turn_contract_import import LONG_ASSISTANT, _cg_conv, _cg_node
from tests.test_turn_extraction import FakeClient, FakeST

TYPED = "I would rather keep the monthly drill because it catches problems early"
TYPED_2 = "I plan every garden bed a full season ahead so nothing is rushed in spring"


# --------------------------------------------------------------------------- units

def _turn_db():
    c = sqlite3.connect(":memory:")
    ensure_turn_tables(c)
    rows = [("c:0", "own_typed", None), ("c:1", "own_typed", "trading_journal"),
            ("c:2", "own_typed", "trading_journal"), ("c:3", "own_typed", "own_document")]
    for tid, vc, pr in rows:
        c.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, "
                  "text, basis, turn_contract_version, practice) VALUES (?,?,?,?,?,?,?,?,?)",
                  (tid, "c", int(tid.split(":")[1]), "subject", vc, "x", "source:role",
                   "turn-contract/1", pr))
    return c


def test_fact_practice_from_cited_turns():
    from baselayer.extract_facts import fact_practice
    c = _turn_db()
    sp = lambda *t: [{"turn_id": x, "span": "s"} for x in t]  # noqa: E731
    assert fact_practice(c, sp("c:1", "c:2")) == "trading_journal"
    assert fact_practice(c, sp("c:0")) is None
    assert fact_practice(c, sp("c:0", "c:1")) == "general+trading_journal"
    assert fact_practice(c, sp("c:1", "c:3")) == "own_document+trading_journal"
    assert fact_practice(c, json.dumps(sp("c:2"))) == "trading_journal"
    assert fact_practice(c, None) is None and fact_practice(c, []) is None


def test_fact_practice_on_a_database_without_the_column():
    from baselayer.extract_facts import fact_practice
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE turns (turn_id TEXT, voice_class TEXT)")
    assert fact_practice(c, [{"turn_id": "c:1", "span": "s"}]) is None
    c2 = sqlite3.connect(":memory:")                   # no turn table at all
    assert fact_practice(c2, [{"turn_id": "c:1", "span": "s"}]) is None


def test_practice_column_on_memory_facts(tmp_path):
    from baselayer.extract_facts import TURN_CONTRACT_COLUMNS, _ensure_turn_contract_columns
    from baselayer.init_database import init_database
    assert ("practice", "TEXT") in TURN_CONTRACT_COLUMNS
    db = tmp_path / "m.db"
    init_database(db)
    c = sqlite3.connect(str(db))
    assert "practice" in {r[1] for r in c.execute("PRAGMA table_info(memory_facts)")}
    old = sqlite3.connect(":memory:")
    old.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT)")
    _ensure_turn_contract_columns(old)
    assert "practice" in {r[1] for r in old.execute("PRAGMA table_info(memory_facts)")}


# --------------------------------------------------------------------------- end to end

@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import baselayer.config as cfg
    import baselayer.extract_facts as ef
    from baselayer.init_database import init_database

    root = tmp_path / "corpus"
    db = root / "data" / "database" / "memory.db"
    init_database(db)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", root)
    monkeypatch.setattr(cfg, "DATABASE_FILE", db)
    conf = tmp_path / "import_config.json"
    conf.write_text(json.dumps({"allowlist_own_writing_pasted": True,
                                "subject_names": ["Dana Reyes"]}), encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(conf))

    export = tmp_path / "conversations.json"
    export.write_text(json.dumps([_cg_conv("cg-prac", [
        _cg_node("n1", None, "user", TYPED, 1.0),
        _cg_node("n2", "n1", "assistant", LONG_ASSISTANT, 2.0),
        _cg_node("n3", "n2", "user", OPENER + "\n" + JOURNAL, 3.0),
        _cg_node("n4", "n3", "assistant", "Noted. The notes show patience after a loss.", 4.0),
        _cg_node("n5", "n4", "user", TYPED_2, 5.0),
    ])]), encoding="utf-8")
    conn = sqlite3.connect(str(db))
    IC.import_chatgpt(conn, str(export), set())
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


def _alias(prompt, phrase):
    import re
    for alias, body in re.findall(r"\[(S\d+) \| SUBJECT[^\]]*\]\n(.*?)(?=\n\n\[|\Z)", prompt, re.S):
        if phrase in body:
            return alias
    return None


def _fact(obj, spans, predicate="practices", category="habit"):
    return {"subject": "user", "predicate": predicate, "object": obj, "qualifier": "unknown",
            "category": category, "temporal": "current", "confidence": 0.9, "inferred": False,
            "evidence_spans": [{"turn": t, "span": s} for t, s in spans]}


J1 = "waited for the 5m cross, didnt chase the open"
J2 = "moved the stop back, never again, cant keep doing this"
J3 = "followed the plan, one trade and done for the day"


def _extract(corpus, monkeypatch):
    def fake_llm(prompt, schema=None, retries=None, max_tokens=None):
        facts = []
        if J1 in prompt and _alias(prompt, J1):
            j = _alias(prompt, J1)
            facts += [_fact("waits for confirmation before entering", [(j, J1)]),
                      _fact("does not move a stop back", [(j, J2)], "avoids", "value"),
                      _fact("stops after one planned trade", [(j, J3)])]
            if _alias(prompt, TYPED):
                facts.append(_fact("prefers checks that catch problems early",
                                   [(_alias(prompt, TYPED), "keep the monthly drill"), (j, J1)],
                                   "prefers", "preference"))
        if _alias(prompt, TYPED_2):
            facts.append(_fact("plans a season ahead",
                               [(_alias(prompt, TYPED_2), "plan every garden bed a full season ahead")],
                               "prefers", "preference"))
        return {"facts": facts}

    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(corpus.ef, "call_llm", fake_llm)
    corpus.ef.run_extraction()
    return {f["object_text"]: f for f in _rows(corpus.db, "SELECT * FROM memory_facts")}


def _spec(dirpath, claims):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "predictions.json").write_text(json.dumps(
        {"layer": "predictions", "preamble": "", "claims": claims}), encoding="utf-8")


def _claim(cid, name, fids):
    return {"id": cid, "name": name, "statement": f"{name}.", "active_when": "A decision is made",
            "contested": False, "fact_ids": fids}


def _state(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()}


def test_practice_flows_from_turns_to_facts_to_a_bounded_flag(corpus, monkeypatch):
    stored = _extract(corpus, monkeypatch)
    assert stored["waits for confirmation before entering"]["practice"] == "trading_journal"
    assert stored["does not move a stop back"]["practice"] == "trading_journal"
    assert stored["plans a season ahead"]["practice"] is None
    assert stored["prefers checks that catch problems early"]["practice"] == "general+trading_journal"

    fid = {k: "F-" + v["id"][:8] for k, v in stored.items()}
    spec = corpus.tmp / "spec"
    _spec(spec, [
        _claim("P1", "WAITS FOR CONFIRMATION", [fid["waits for confirmation before entering"],
                                                fid["does not move a stop back"],
                                                fid["stops after one planned trade"]]),
        _claim("P2", "PLANS AHEAD", [fid["plans a season ahead"],
                                     fid["waits for confirmation before entering"]]),
        _claim("P3", "CATCHES PROBLEMS EARLY", [fid["prefers checks that catch problems early"],
                                                fid["does not move a stop back"]]),
        _claim("P4", "PLANS A SEASON", [fid["plans a season ahead"]]),
    ])
    before = _state(spec)
    from baselayer.verification import run as vrun
    out = corpus.tmp / "verify_out"
    assert vrun.main([str(spec), "--label", "prac", "--corpus", str(corpus.root), "--out", str(out)]) == 0
    assert _state(spec) == before                      # report only: the spec is untouched

    rep = json.loads((out / "prac.verification.json").read_text(encoding="utf-8"))
    flags = [f for f in rep["findings"] if f["check"] == "practice_bounded"]
    assert [f["claims"] for f in flags] == [["prac:P1"]]
    assert flags[0]["bounded"] == "trading_journal"
    assert flags[0]["detail"].startswith("bounded:trading_journal")
    assert sorted(flags[0]["fact_ids"]) == sorted([fid["waits for confirmation before entering"],
                                                   fid["does not move a stop back"],
                                                   fid["stops after one planned trade"]])

    prac = {q: p["practice"] for q, p in rep["claims"].items()}
    assert prac["prac:P1"]["by_practice"] == {"trading_journal": 3}
    assert prac["prac:P1"]["bounded"] == "trading_journal"
    assert prac["prac:P1"]["dominant_share"] == 1.0
    assert prac["prac:P2"]["by_practice"] == {"trading_journal": 1, "untagged": 1}
    assert prac["prac:P2"]["bounded"] is None and prac["prac:P2"]["dominant_share"] == 0.5
    # a fact resting on two practices does not make its claim bounded to either
    assert prac["prac:P3"]["by_practice"] == {"general+trading_journal": 1, "trading_journal": 1}
    assert prac["prac:P3"]["bounded"] is None
    # untagged is not a practice: a claim resting only on untagged facts is not flagged
    assert prac["prac:P4"]["by_practice"] == {"untagged": 1} and prac["prac:P4"]["bounded"] is None
    assert prac["prac:P1"]["by_category"] == {"habit": 2, "value": 1}
    assert rep["summary"]["practice_bounded_claims"] == {"trading_journal": 1}
    md = (out / "prac.verification.md").read_text(encoding="utf-8")
    assert "practice_bounded" in md and "bounded:trading_journal" in md


def test_legacy_corpus_reports_practice_unknown_and_never_flags(tmp_path):
    from tests.test_verification import LIVE, LIVE2, claim, make_db, make_spec
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db")
    spec = tmp_path / "spec"
    make_spec(spec, {"anchors": [claim("A1", "WATER EARLY", [LIVE, LIVE2])]})
    from baselayer.verification import run as vrun
    out = tmp_path / "o"
    assert vrun.main([str(spec), "--label", "g", "--corpus", str(corpus), "--out", str(out)]) == 0
    rep = json.loads((out / "g.verification.json").read_text(encoding="utf-8"))
    assert not [f for f in rep["findings"] if f["check"] == "practice_bounded"]
    p = rep["claims"]["g:A1"]["practice"]
    assert p["available"] is False and p["bounded"] is None
    assert p["by_category"] == {"habit": 1, "value": 1}
