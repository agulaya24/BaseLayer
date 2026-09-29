"""
AUDN must never act on a superseded fact.

A superseded fact's vector stays in the vector store. Two defects followed from that:

1. The AUDN neighbour search returned superseded facts. A later near-duplicate could be
   ruled UPDATE against the dead fact, or NOOP-merge its spans into it.
2. store_fact wrote `superseded_by` unconditionally. When B had already superseded A, a
   later UPDATE C that landed on A re-pointed A to C, leaving B live and referenced by
   nothing: two live near-duplicates and a broken chain.

Guard 1: find_similar_facts, given the connection, excludes every fact whose
`superseded_by` is set (read on the caller's connection, so uncommitted supersessions in
the same transaction count), and over-fetches until it has top_k live hits or runs out.
Guard 2: store_fact never overwrites a set `superseded_by`. It follows the chain to its
live head and supersedes that, or, when the chain ends in a marker (CONTRADICTED and the
like), stores the new fact as live and supersedes nothing. Both cases are counted.

Real chromadb in tmp_path, a fake embedding model, no API calls.
"""

import json
import sqlite3
from collections import Counter
from types import SimpleNamespace

import pytest

chromadb = pytest.importorskip("chromadb")

import baselayer.extract_facts as ef  # noqa: E402
from baselayer.init_database import init_database  # noqa: E402

V = "turn-contract/1"
STAMP = {"turn_contract_version": V, "extraction_model": "m", "extraction_prompt_hash": "h",
         "git_commit": "g", "code_path": "src/baselayer/extract_facts.py"}

# text -> vector. Chosen so the ORIGINAL fact A is the single nearest neighbour of the
# later candidates, with its successor B a close second.
VEC = {
    "user likes tea": [1.0, 0.0, 0.0],
    "user likes green tea": [0.95, 0.31, 0.0],
    "user likes green tea daily": [0.99, 0.14, 0.0],
    "unrelated": [0.0, 0.0, 1.0],
}


class _Vec(list):
    def tolist(self):
        return list(self)


class _Model:
    def encode(self, texts):
        return _Vec([VEC[t] for t in texts])


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "data" / "database" / "memory.db"
    init_database(p)
    conn = sqlite3.connect(str(p))
    yield conn
    conn.close()


@pytest.fixture
def col(tmp_path):
    return chromadb.PersistentClient(path=str(tmp_path / "vectors")).create_collection(
        "memory_facts", metadata={"hnsw:space": "cosine"})


def _record():
    return SimpleNamespace(c=Counter(), audn=Counter(), post_gate_drops=Counter())


def _row(conn, fid):
    return conn.execute("SELECT superseded_by, evidence_spans FROM memory_facts WHERE id = ?",
                        (fid,)).fetchone()


def _live(conn):
    return [r[0] for r in conn.execute("SELECT id FROM memory_facts WHERE superseded_by IS NULL")]


def _store_and_embed(conn, col, text, action="ADD", supersedes=None, record=None):
    fid = ef.store_fact(conn, text, "preference", 0.9, "conv", action, supersedes,
                        stamp=STAMP, grounding="prose", record=record) if record is not None \
        else ef.store_fact(conn, text, "preference", 0.9, "conv", action, supersedes,
                           stamp=STAMP, grounding="prose")
    ef.embed_fact(fid, text, "preference", col, _Model(), contract_version=V, grounding="prose")
    return fid


# ---------------------------------------------------------------------------
# guard 1: the neighbour search
# ---------------------------------------------------------------------------

def test_search_excludes_a_superseded_fact_and_returns_its_live_successor(db, col):
    a = _store_and_embed(db, col, "user likes tea")
    b = _store_and_embed(db, col, "user likes green tea", "UPDATE", a)
    assert _row(db, a)[0] == b
    got = ef.find_similar_facts("user likes green tea daily", col, _Model(), top_k=1,
                                contract_version=V, grounding="prose", conn=db)
    # The live neighbour IS returned. find_similar_facts swallows every exception and
    # returns [], so asserting only that A is absent would pass on a crash.
    assert [s["fact_id"] for s in got] == [b]


def test_search_overfetches_past_superseded_hits(db, col):
    # Four dead facts nearer to the query than the one live fact, top_k=1: a single
    # query of n_results=1 would find only dead facts and return nothing.
    dead = [_store_and_embed(db, col, "user likes tea")]
    live = _store_and_embed(db, col, "unrelated")
    for _ in range(3):
        fid = ef.store_fact(db, "user likes tea", "preference", 0.9, "conv", "ADD",
                            stamp=STAMP, grounding="prose")
        col.add(ids=[fid], embeddings=[VEC["user likes tea"]], documents=["user likes tea"],
                metadatas=[{"fact_id": fid, "category": "preference",
                            "turn_contract_version": V, "grounding": "prose"}])
        dead.append(fid)
    for d in dead:
        db.execute("UPDATE memory_facts SET superseded_by = 'CONTRADICTED' WHERE id = ?", (d,))
    got = ef.find_similar_facts("user likes tea", col, _Model(), top_k=1,
                                contract_version=V, grounding="prose", conn=db)
    assert [s["fact_id"] for s in got] == [live]


def test_search_sees_an_uncommitted_supersession_on_the_same_connection(db, col):
    a = _store_and_embed(db, col, "user likes tea")
    db.commit()
    b = _store_and_embed(db, col, "user likes green tea", "UPDATE", a)   # not committed
    got = ef.find_similar_facts("user likes green tea daily", col, _Model(), top_k=5,
                                contract_version=V, grounding="prose", conn=db)
    assert [s["fact_id"] for s in got] == [b]


def test_turn_path_chains_a_second_update_onto_the_live_head(db, col, monkeypatch):
    """store_turn_facts, the one store step of both turn paths (sequential and batch):
    A, then B UPDATEs A, then C, whose nearest vector is A. Before the guard C re-pointed
    A and left B live; now C supersedes B and exactly one fact is live."""
    monkeypatch.setattr(ef, "make_audn_decision", lambda text, similar: (
        {"action": "UPDATE", "updated_fact": text} if similar else {"action": "ADD"}))

    def fact(text):
        return {"fact": text, "category": "preference", "confidence": 0.9,
                "source_turn_id": "conv:0", "grounding": "prose",
                "evidence_spans": [{"turn_id": "conv:0", "span": text}]}
    rec = _record()
    for text in ("user likes tea", "user likes green tea", "user likes green tea daily"):
        ef.store_turn_facts(db, "conv", [fact(text)], col, _Model(), scope="personal",
                            stamp=STAMP, record=rec)
    ids = {t: i for i, t in db.execute("SELECT id, fact_text FROM memory_facts")}
    a, b, c = (ids["user likes tea"], ids["user likes green tea"],
               ids["user likes green tea daily"])
    assert _row(db, a)[0] == b
    assert _row(db, b)[0] == c
    assert _live(db) == [c]


def test_turn_path_noop_merges_spans_into_the_live_fact_not_the_dead_one(db, col, monkeypatch):
    decisions = iter([{"action": "UPDATE", "updated_fact": "user likes green tea"},
                      {"action": "NOOP"}])
    monkeypatch.setattr(ef, "make_audn_decision",
                        lambda text, similar: next(decisions) if similar else {"action": "ADD"})

    def fact(text, turn):
        return {"fact": text, "category": "preference", "confidence": 0.9,
                "source_turn_id": turn, "grounding": "prose",
                "evidence_spans": [{"turn_id": turn, "span": text}]}
    rec = _record()
    for text, turn in (("user likes tea", "c1:0"), ("user likes green tea", "c2:0"),
                       ("user likes green tea daily", "c3:0")):
        ef.store_turn_facts(db, turn[:2], [fact(text, turn)], col, _Model(), scope="personal",
                            stamp=STAMP, record=rec)
    ids = {t: i for i, t in db.execute("SELECT id, fact_text FROM memory_facts")}
    a, b = ids["user likes tea"], ids["user likes green tea"]
    assert [s["turn_id"] for s in json.loads(_row(db, a)[1])] == ["c1:0"]
    assert [s["turn_id"] for s in json.loads(_row(db, b)[1])] == ["c2:0", "c3:0"]
    assert rec.c["noop_spans_merged"] == 1


# ---------------------------------------------------------------------------
# guard 2: store_fact never overwrites superseded_by
# ---------------------------------------------------------------------------

def test_store_fact_routes_a_second_update_to_the_live_head(db):
    rec = _record()
    a = ef.store_fact(db, "user likes tea", "preference", 0.9, "conv", "ADD", record=rec)
    b = ef.store_fact(db, "user likes green tea", "preference", 0.9, "conv", "UPDATE", a,
                      record=rec)
    c = ef.store_fact(db, "user likes green tea daily", "preference", 0.9, "conv", "UPDATE", a,
                      record=rec)
    assert _row(db, a)[0] == b          # never overwritten
    assert _row(db, b)[0] == c          # C supersedes the live head
    assert _live(db) == [c]
    assert rec.c["update_target_already_superseded"] == 1
    assert rec.c["update_rerouted_to_live_head"] == 1


def test_store_fact_follows_a_long_chain(db):
    rec = _record()
    a = ef.store_fact(db, "a", "x", 0.9, "conv", "ADD")
    b = ef.store_fact(db, "b", "x", 0.9, "conv", "UPDATE", a)
    c = ef.store_fact(db, "c", "x", 0.9, "conv", "UPDATE", b)
    d = ef.store_fact(db, "d", "x", 0.9, "conv", "UPDATE", a, record=rec)
    assert (_row(db, a)[0], _row(db, b)[0], _row(db, c)[0]) == (b, c, d)
    assert _live(db) == [d]


def test_store_fact_onto_a_contradicted_chain_supersedes_nothing(db):
    rec = _record()
    a = ef.store_fact(db, "user likes tea", "preference", 0.9, "conv", "ADD")
    db.execute("UPDATE memory_facts SET superseded_by = 'CONTRADICTED' WHERE id = ?", (a,))
    c = ef.store_fact(db, "user likes green tea", "preference", 0.9, "conv", "UPDATE", a,
                      record=rec)
    assert _row(db, a)[0] == "CONTRADICTED"
    assert _row(db, c)[0] is None
    assert rec.c["update_target_already_superseded"] == 1
    assert rec.c["update_target_chain_dead"] == 1


def test_store_fact_counts_a_missing_target(db):
    rec = _record()
    c = ef.store_fact(db, "user likes tea", "preference", 0.9, "conv", "UPDATE", "no-such-id",
                      record=rec)
    assert _row(db, c)[0] is None
    assert rec.c["update_target_missing"] == 1


def test_counters_reach_the_serialised_run_record(db):
    from baselayer.turn_contract import ExtractionRunRecord as RunRecord
    rec = RunRecord("turn", {})
    a = ef.store_fact(db, "a", "x", 0.9, "conv", "ADD")
    ef.store_fact(db, "b", "x", 0.9, "conv", "UPDATE", a)
    ef.store_fact(db, "c", "x", 0.9, "conv", "UPDATE", a, record=rec)
    counts = json.loads(json.dumps(rec.to_dict()))["counts"]
    assert counts["update_target_already_superseded"] == 1
    assert counts["update_rerouted_to_live_head"] == 1
