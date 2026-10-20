"""search_conversations' relevance must read the collection's distance space.

It converted with a literal `1 - distance`, which is right only for a cosine collection. The
messages collection is l2 on stores built before the `hnsw:space` metadata was set, and Chroma's
l2 distance is SQUARED, so two messages 30 degrees apart (cos 0.866) were reported at 0.732.
The test queries a real in-memory Chroma collection of each space at a known angle.
"""
import math

import pytest


@pytest.mark.parametrize("space", ["l2", "cosine", "ip"])
def test_relevance_is_the_true_cosine(space, monkeypatch):
    chromadb = pytest.importorskip("chromadb")
    from chromadb.config import Settings
    from baselayer import semantic_search as ss

    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    name = "relevance_probe_%s" % space
    try:
        client.delete_collection(name)
    except Exception:
        pass
    col = client.create_collection(name, metadata={"hnsw:space": space})
    th = math.radians(30)
    col.add(ids=["m1"], embeddings=[[math.cos(th), math.sin(th), 0.0]],
            documents=["a message"],
            metadatas=[{"conversation_id": "c1", "conversation_title": "t", "role": "user"}])

    def fake_search(query, n_results=10, role_filter=None):
        got = col.query(query_embeddings=[[1.0, 0.0, 0.0]], n_results=1)
        return [{"id": got["ids"][0][0], "text": got["documents"][0][0],
                 "conversation_id": got["metadatas"][0][0]["conversation_id"],
                 "conversation_title": got["metadatas"][0][0]["conversation_title"],
                 "role": "user", "created_at": None,
                 "distance": got["distances"][0][0]}]

    monkeypatch.setattr(ss, "search", fake_search)
    monkeypatch.setattr(ss, "_collection", col)
    convos = ss.search_conversations("anything", n_results=1)
    assert len(convos) == 1
    assert convos[0]["relevance"] == pytest.approx(math.cos(th), abs=2e-3), space
