"""
The two Chroma call shapes the turn contract depends on, against REAL chromadb
in tmp_path (local, no network, no API):

- assert_fresh_for_turn_contract: collection.get(where=..., include=[]), with
  no handler around it. If Chroma rejected that shape, a run would crash on its
  first step.
- find_similar_facts(contract_version=V): collection.query(where=...), inside a
  try that returns [] on error. If Chroma rejected the filter, AUDN dedup would
  silently switch off instead of failing, so this proves the filter WORKS, not
  merely that it does not raise.
"""

import sqlite3

import pytest

chromadb = pytest.importorskip("chromadb")

V = "turn-contract/1"


class _Vec(list):
    def tolist(self):
        return list(self)


class _Model:
    def encode(self, texts):
        return _Vec([[1.0, 0.0, 0.0] for _ in texts])


@pytest.fixture
def collection(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "vectors"))
    col = client.create_collection("memory_facts", metadata={"hnsw:space": "cosine"})
    return col


def _empty_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT NOT NULL, "
                 "turn_contract_version TEXT)")
    return conn


def test_fresh_check_refuses_an_unstamped_vector(collection):
    from baselayer.extract_facts import assert_fresh_for_turn_contract, TurnContractViolation
    collection.add(ids=["gated"], embeddings=[[1.0, 0.0, 0.0]], documents=["user prefers a"],
                   metadatas=[{"fact_id": "gated", "category": "x", "turn_contract_version": V}])
    collection.add(ids=["legacy"], embeddings=[[1.0, 0.0, 0.0]], documents=["user prefers b"],
                   metadatas=[{"fact_id": "legacy", "category": "x"}])
    with pytest.raises(TurnContractViolation, match="1 fact vectors not stamped"):
        assert_fresh_for_turn_contract(_empty_db(), collection)


def test_fresh_check_passes_an_all_stamped_collection(collection):
    from baselayer.extract_facts import assert_fresh_for_turn_contract
    collection.add(ids=["gated"], embeddings=[[1.0, 0.0, 0.0]], documents=["user prefers a"],
                   metadatas=[{"fact_id": "gated", "category": "x", "turn_contract_version": V}])
    assert_fresh_for_turn_contract(_empty_db(), collection)


def test_version_filter_returns_only_same_version_vectors(collection):
    from baselayer.extract_facts import embed_fact, find_similar_facts
    model = _Model()
    embed_fact("gated", "user prefers plain answers", "preference", collection, model,
               contract_version=V)
    embed_fact("legacy", "user prefers plain answers", "preference", collection, model)
    assert "turn_contract_version" not in collection.get(ids=["legacy"])["metadatas"][0]

    unfiltered = find_similar_facts("user prefers plain answers", collection, model)
    filtered = find_similar_facts("user prefers plain answers", collection, model,
                                  contract_version=V)
    assert {s["fact_id"] for s in unfiltered} == {"gated", "legacy"}
    assert [s["fact_id"] for s in filtered] == ["gated"]
    assert filtered[0]["similarity"] > 0.99   # the filter did not break the distance maths


def test_a_failing_search_is_counted_not_silent():
    import baselayer.extract_facts as ef

    class Broken:
        metadata = {"hnsw:space": "cosine"}

        def query(self, **kw):
            raise ValueError("bad where")

    ef.reset_response_failures()
    assert ef.find_similar_facts("x", Broken(), _Model(), contract_version=V) == []
    assert ef.response_failures() == {"similarity_search_error": 1}
