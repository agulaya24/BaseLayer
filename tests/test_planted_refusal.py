"""Planted pilot sessions never reach a specification by default. No API calls.

The planted known-bad sessions (turn_contract_fixtures) carry an own-voice sentence that the
extractor stores as a fact about the subject. distill.py refuses a fact base holding any active
fact from a `planted-` conversation, and assemble refuses a tree built with one, unless the
explicit opt-in flag says this is a pilot corpus.
"""
import json
import sqlite3
import sys

import pytest

from baselayer.distillation import assemble as asm
from baselayer.distillation import distill
from baselayer.turn_contract_fixtures import PLANTED_PREFIX
from tests.test_artifact_stamps import FACTS, DistillClient, _tree, no_network  # noqa: F401


def _db(root, planted=True):
    db = root / "data" / "database" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, predicate TEXT, "
              "category TEXT, superseded_by TEXT, created_at REAL, turn_contract_version TEXT, "
              "source_conversation_id TEXT)")
    for i, (fid, text, ver) in enumerate(FACTS):
        conv = (PLANTED_PREFIX + "paste") if (planted and i == 0) else "real-conv-%d" % i
        c.execute("INSERT INTO memory_facts VALUES (?,?,?,?,NULL,?,?,?)",
                  (fid, text, "prefers", "preference", float(i), ver, conv))
    c.commit()
    c.close()
    return db


def _distill(monkeypatch, db, out, *extra):
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "2",
                                      "--layer", "anchors", *extra])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def test_distill_refuses_planted_facts_before_any_call(no_network, monkeypatch, tmp_path):
    db = _db(tmp_path / "c")
    with pytest.raises(SystemExit, match="planted"):
        _distill(monkeypatch, db, tmp_path / "t.json")
    assert DistillClient.calls == []


def test_distill_allows_planted_facts_only_when_asked_and_says_so(no_network, monkeypatch,
                                                                  tmp_path):
    tree = _distill(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json", "--allow-planted")
    assert tree["stamp"]["planted_facts_included"] == 1


def test_distill_of_a_clean_corpus_records_zero_planted(no_network, monkeypatch, tmp_path):
    tree = _distill(monkeypatch, _db(tmp_path / "c", planted=False), tmp_path / "t.json")
    assert tree["stamp"]["planted_facts_included"] == 0


def _planted_tree(run_id, n):
    t = _tree(run_id, "turn-contract/1")
    t["stamp"]["planted_facts_included"] = n
    return t


def test_assemble_refuses_a_tree_built_from_planted_facts(capsys):
    with pytest.raises(SystemExit, match="planted"):
        asm.assemble([_planted_tree("r1", 0), _planted_tree("r2", 3)])


def test_assemble_allows_planted_trees_only_when_asked_and_carries_the_count(capsys):
    pkg = asm.assemble([_planted_tree("r1", 0), _planted_tree("r2", 3)], allow_planted=True)
    assert pkg["stamp"]["planted_facts_included"] == 3
    assert asm.assemble([_planted_tree("r1", 0)])["stamp"]["planted_facts_included"] == 0
