"""`baselayer run` step 5b must repair the FACT vectors, not embed messages.

WHY THIS EXISTS. `_run_traceability` step 5b compared the `memory_facts` vector count with the
`memory_facts` row count and, under 90%, called `cmd_embed`. `cmd_embed` embeds MESSAGES into the
`messages` collection, so it could never raise the fact-vector count: the step printed "Running
embed..." and left every missing fact vector missing, and 5c (vector provenance, which queries
`memory_facts`) then ran on an incomplete index without saying so. Facts missing from the index
never surface as provenance for any claim.

No network, no model download: a fake embedding model and a fake Chroma client stand in.
Nothing is written outside tmp_path.
"""
import sqlite3
import types

import pytest

from baselayer import cli


class FakeModel:
    def encode(self, texts):
        class _A(list):
            def tolist(self):
                return list(self)
        return _A([[float(len(t)), 1.0, 0.0] for t in texts])


class FakeCollection:
    def __init__(self, ids=()):
        self.store = {i: {"document": "old", "metadata": {"fact_id": i}} for i in ids}
        self.metadata = {"hnsw:space": "cosine"}

    def count(self):
        return len(self.store)

    def get(self, ids=None, include=None, limit=None, offset=None):
        keys = list(self.store) if ids is None else [i for i in ids if i in self.store]
        if offset:
            keys = keys[offset:]
        if limit is not None:
            keys = keys[:limit]
        return {"ids": keys}

    def add(self, ids, embeddings, documents, metadatas):
        for i, d, m in zip(ids, documents, metadatas):
            if i in self.store:
                continue                      # Chroma ignores an existing id on add
            self.store[i] = {"document": d, "metadata": m}


class FakeChroma:
    def __init__(self, coll):
        self.coll = coll
        self.created = []

    def get_collection(self, name):
        if name != "memory_facts" or self.coll is None:
            raise ValueError("Collection %s does not exist." % name)
        return self.coll

    def get_or_create_collection(self, name, metadata=None):
        assert name == "memory_facts"
        if self.coll is None:
            self.coll = FakeCollection()
            self.coll.metadata = dict(metadata or {})
            self.created.append(metadata)
        return self.coll


def _db(path, n_active=10, n_superseded=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, category TEXT, "
              "superseded_by TEXT, knowledge_tier TEXT DEFAULT 'untiered', predicate TEXT, "
              "turn_contract_version TEXT, grounding TEXT)")
    for i in range(n_active):
        c.execute("INSERT INTO memory_facts (id, fact_text, category, predicate, "
                  "turn_contract_version, grounding) VALUES (?,?,?,?,?,?)",
                  ("f%02d" % i, "fact text %d" % i, "values", "values",
                   "tc-1" if i % 2 else None, "typed" if i % 3 == 0 else None))
    for i in range(n_superseded):
        c.execute("INSERT INTO memory_facts (id, fact_text, category, superseded_by) "
                  "VALUES (?,?,?,?)", ("s%02d" % i, "gone %d" % i, "values", "user_forget"))
    c.commit()
    c.close()


@pytest.fixture
def trace_env(tmp_path, monkeypatch):
    import baselayer.config as config
    import baselayer.api_client as ac
    dbf = tmp_path / "data" / "database" / "memory.db"
    _db(dbf)
    monkeypatch.setattr(config, "DATABASE_FILE", dbf)
    monkeypatch.setattr(config, "VECTORS_DIR", tmp_path / "data" / "vectors")
    monkeypatch.setattr(ac, "get_embedding_model", lambda: FakeModel())
    monkeypatch.setattr(ac, "_embedding_model", FakeModel())
    embeds = []
    monkeypatch.setattr(cli, "cmd_embed", lambda a: embeds.append(a))
    # 5c and 5d are out of scope here, and 5d calls a paid model: make both inert.
    import baselayer.verify_provenance as vp
    monkeypatch.setattr(vp, "generate_vector_provenance", lambda layer: [])
    monkeypatch.setattr(vp, "_reset_chroma_cache", lambda: None)
    import baselayer.detect_contradictions as dc
    monkeypatch.setattr(dc, "load_facts", lambda conn: [])
    return types.SimpleNamespace(db=dbf, embeds=embeds, monkeypatch=monkeypatch,
                                 config=config)


def _use_chroma(env, chroma):
    env.monkeypatch.setattr(env.config, "get_chroma_client", lambda path=None: chroma)
    env.monkeypatch.setitem(__import__("sys").modules, "chromadb",
                            types.SimpleNamespace(PersistentClient=lambda *a, **k: chroma))


def test_under_90_percent_embeds_the_missing_facts_not_messages(trace_env):
    coll = FakeCollection(ids=["f00", "f01", "f02"])          # 3 of 10 active facts
    _use_chroma(trace_env, FakeChroma(coll))
    cli._run_traceability()
    assert trace_env.embeds == [], "5b called cmd_embed, which embeds messages, not facts"
    assert set(coll.store) == {"f%02d" % i for i in range(10)}
    assert not any(k.startswith("s") for k in coll.store), "a forgotten fact was re-embedded"
    new = coll.store["f03"]
    assert new["document"] == "fact text 3"
    assert new["metadata"] == {"fact_id": "f03", "category": "values",
                               "turn_contract_version": "tc-1", "grounding": "typed"}
    assert "turn_contract_version" not in coll.store["f04"]["metadata"]   # never None in Chroma


def test_missing_collection_is_created_cosine_and_filled(trace_env):
    chroma = FakeChroma(None)
    _use_chroma(trace_env, chroma)
    cli._run_traceability()
    assert trace_env.embeds == []
    assert chroma.created and chroma.created[0]["hnsw:space"] == "cosine"
    assert chroma.coll.count() == 10


def test_a_complete_index_is_left_alone(trace_env):
    coll = FakeCollection(ids=["f%02d" % i for i in range(10)])
    _use_chroma(trace_env, FakeChroma(coll))
    cli._run_traceability()
    assert trace_env.embeds == []
    assert all(v["document"] == "old" for v in coll.store.values())


def test_embed_missing_facts_counts_only_what_it_added(tmp_path):
    from baselayer.extract_facts import embed_missing_facts
    dbf = tmp_path / "m.db"
    _db(dbf, n_active=5, n_superseded=1)
    coll = FakeCollection(ids=["f00"])
    with sqlite3.connect(dbf) as conn:
        assert embed_missing_facts(conn, coll, FakeModel(), batch_size=2) == 4
        assert embed_missing_facts(conn, coll, FakeModel(), batch_size=2) == 0
    assert coll.count() == 5


def test_against_a_real_chroma_collection_with_paging(tmp_path):
    """The fakes above encode an assumption about Chroma's API; this asks the artifact.
    get(include=[], limit, offset) paging and add() must behave as embed_missing_facts expects
    on the installed chromadb, across more than one page."""
    chromadb = pytest.importorskip("chromadb")
    from baselayer.extract_facts import embed_missing_facts, _collection_ids
    from chromadb.config import Settings
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))  # no telemetry
    try:
        client.delete_collection("memory_facts_probe")
    except Exception:
        pass
    coll = client.create_collection("memory_facts_probe", metadata={"hnsw:space": "cosine"})
    coll.add(ids=["f00"], embeddings=[[1.0, 0.0, 0.0]], documents=["x"],
             metadatas=[{"fact_id": "f00", "category": "values"}])
    dbf = tmp_path / "m.db"
    _db(dbf, n_active=7, n_superseded=2)
    with sqlite3.connect(dbf) as conn:
        assert embed_missing_facts(conn, coll, FakeModel(), batch_size=3) == 6
        assert embed_missing_facts(conn, coll, FakeModel(), batch_size=3) == 0
    assert _collection_ids(coll, page=2) == {"f%02d" % i for i in range(7)}
    got = coll.get(ids=["f03"], include=["metadatas", "documents"])
    assert got["documents"] == ["fact text 3"]
    assert got["metadatas"][0]["turn_contract_version"] == "tc-1"
