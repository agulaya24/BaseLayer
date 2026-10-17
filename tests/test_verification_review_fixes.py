"""Review fixes in verify-spec. No model is called; the timeout tests replace subprocess.run.

- a turn-contract fact keeps its deterministic voice verdict: own only if every span's turn is
  own, unsettled when no span's turn resolved (definitions.py), never recomputed from the first
  span alone;
- a malformed rater reply (item without a string id, unhashable values) is a failed task, never
  an exception;
- a rater subprocess timeout is a failed task, never an exception that ends the run.
"""
import json
import sqlite3
from pathlib import Path

from tests.test_verification import (G_MIX, G_OK, ScriptedJudge, claim, make_spec, real_schema_db, run_fake)

G_MIX2 = "9b9b0002-0000-0000-0000-000000000002"
G_MIX3 = "9b9b0003-0000-0000-0000-000000000003"
G_NT1 = "9d9d0001-0000-0000-0000-000000000001"
G_NT2 = "9d9d0002-0000-0000-0000-000000000002"
G_NT3 = "9d9d0003-0000-0000-0000-000000000003"


def add_fact(db: Path, fid, text, spans, version="turn-contract/1"):
    c = sqlite3.connect(str(db))
    c.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id, source_turn_id, "
              "evidence_spans, turn_contract_version) VALUES (?,?,?,?,?,?,?)",
              (fid, text, "habit", "cv", spans[0]["turn_id"] if spans else None,
               json.dumps(spans) if spans else None, version))
    c.commit()
    c.close()


def build_world(tmp: Path):
    """real_schema_db (G_OK, G_MIX) plus two more mixed-span facts and three facts whose
    only span points at a turn that does not exist (voice 'unknown', gate no_turn)."""
    corpus = tmp / "corpus"
    db = corpus / "data" / "database" / "memory.db"
    real_schema_db(db)
    mix = [{"turn_id": "cv:0", "span": "before sunrise"}, {"turn_id": "cv:1", "span": "Mulch solves most problems"}]
    add_fact(db, G_MIX2, "user mulches and waters early (2)", mix)
    add_fact(db, G_MIX3, "user mulches and waters early (3)", mix)
    for i, fid in enumerate((G_NT1, G_NT2, G_NT3)):
        add_fact(db, fid, f"user fact with a missing turn {i}", [{"turn_id": "cv:9", "span": "anything"}])
    return corpus, db

import subprocess

import pytest

from baselayer.verification import model_checks as mc
from baselayer.verification import raters
from baselayer.verification import run as vrun


# ---------------------------------------------------------------- H-1
def _voice_run(tmp_path):
    corpus, _ = build_world(tmp_path)
    spec = tmp_path / "spec"
    make_spec(spec, {"anchors": [claim("A1", "MIXED", [G_MIX, G_MIX2, G_MIX3]),
                                 claim("A2", "UNKNOWN", [G_NT1, G_NT2, G_NT3]),
                                 claim("A3", "CLEAN", [G_OK])]})
    rc, rep, _ = run_fake(tmp_path, corpus, spec, ScriptedJudge(), ["--checks", "support"])
    return rep


def test_h1a_mixed_span_gated_fact_is_not_own(tmp_path):
    rep = _voice_run(tmp_path)
    v = rep["model_results"]["voice"]["t:A1"]
    assert (v["own"], v["not_own"]) == (0, 3), v
    nh = [f for f in rep["findings"] if f["check"] == "claim_not_his" and f["claims"] == ["t:A1"]]
    assert nh, "three facts each with an assistant span: definitions say not own"
    assert rep["model_results"]["voice"]["t:A3"]["own"] == 1          # clean control stays own


def test_h1b_unknown_voice_gated_fact_is_unsettled(tmp_path):
    rep = _voice_run(tmp_path)
    v = rep["model_results"]["voice"]["t:A2"]
    assert (v["unsettled"], v["not_own"], v["own_voice_ratio"]) == (3, 0, None), v
    assert not [f for f in rep["findings"] if f["check"] == "claim_not_his" and f["claims"] == ["t:A2"]]


# ---------------------------------------------------------------- H-2
@pytest.mark.parametrize("items,ids", [
    ([{"id": "Q1", "relation": "duplicate"}, {"relation": "duplicate"}], ["Q1", "Q2"]),   # missing id beside a str id
    ([{"id": "Q1", "relation": "duplicate"}, {"id": 2, "relation": "duplicate"}], ["Q1", "Q2"]),
    ([{"id": ["Q1"], "relation": "duplicate"}], ["Q1"]),                                   # unhashable id
    ([{"id": "Q1", "relation": "duplicate"}, "x"], ["Q1"]),                                # extra non-dict item
    ([{"id": "Q1", "relation": ["duplicate"]}], ["Q1"]),                                   # unhashable enum value
])
def test_h2_validate_returns_error_string_never_raises(items, ids):
    err = mc.validate("cross", {"items": items}, ids)
    assert isinstance(err, str) and err


def test_h2_malformed_reply_is_a_failed_task(tmp_path):
    fake = raters.FakeRater(lambda p: '{"items": [{"id": "Q1", "relation": "duplicate"}, "x"]}')
    res = vrun.run_tasks([{"kind": "cross", "key": "X_000", "prompt": "p", "ids": ["Q1"]}], fake, tmp_path / "raw", workers=1)
    assert res["X_000"]["ok"] is False and len(fake.prompts) == 3


def test_h2_valid_reply_still_accepted():
    assert mc.validate("cross", {"items": [{"id": "Q1", "relation": "duplicate"}]}, ["Q1"]) is None


# ---------------------------------------------------------------- H-3
def _timeout_rater(tmp_path, monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(raters.subprocess, "run", fake_run)
    cwd = tmp_path / "neutral"
    cwd.mkdir()
    return raters.ClaudeCliRater("sonnet", cwd, tmp_path / "work", [tmp_path / "corpus"], binary="not-a-real-claude", timeout=5)


def test_h3_timeout_becomes_reply_error(tmp_path, monkeypatch):
    r = _timeout_rater(tmp_path, monkeypatch).complete("x")
    assert r.text is None and r.error and "timeout" in r.error.lower()


def test_h3_timeout_is_a_failed_task_not_a_crash(tmp_path, monkeypatch):
    r = _timeout_rater(tmp_path, monkeypatch)
    res = vrun.run_tasks([{"kind": "cross", "key": "X_000", "prompt": "p", "ids": ["Q1"]}], r, tmp_path / "raw", workers=2)
    assert res["X_000"]["ok"] is False and "timeout" in res["X_000"]["error"].lower()
