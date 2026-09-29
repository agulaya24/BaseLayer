"""
Turn-contract extraction end to end on the SEQUENTIAL path (run_extraction),
with a synthetic corpus, a fake model and a fake vector store. No API calls,
nothing written outside tmp_path.

The headline test runs the same conversation through both paths: the legacy
path stores a fact the assistant said, the turn path rejects it at the gate.
That is the fails-before evidence for the gate as a whole.
"""

import json
import sqlite3
import sys
import types

import pytest

CONV = "conv-1"
V = "turn-contract/1"

TURNS = [
    # (ordinal, speaker, voice_class, role for legacy messages, text)
    (0, "subject", "own_typed", "user", "I want the migration done before Friday."),
    (1, "assistant", "assistant", "assistant",
     "Shall I migrate the schema tonight and email the vendor about the terms?"),
    (2, "subject", "own_typed", "user", "yes, do that. Keep the email short."),
    (3, "assistant", "assistant", "assistant", "Done. I also think you value speed over polish."),
    (4, "subject", "pasted", "user", "Vendor terms: net 90, auto-renewal every year."),
    (5, "subject", "own_dictated", "user", "Call the project Base Layer."),
]


def _fact(obj, spans, inferred=False, predicate="prefers", category="preference"):
    return {"subject": "user", "predicate": predicate, "object": obj, "qualifier": "unknown",
            "category": category, "temporal": "current", "confidence": 0.9,
            "inferred": inferred,
            "evidence_spans": [{"turn": t, "span": s} for t, s in spans]}


# What the fake model returns on the TURN path. Aliases: S1 = turn 0, S2 = turn 2,
# S3 = turn 5 (only own-voice turns get one).
TURN_FACTS = [
    _fact("short emails to vendors", [("S2", "Keep the email short.")]),                 # ok
    _fact("speed over polish", [("S2", "you value speed over polish")],                   # span_not_found
          predicate="values", category="value"),
    _fact("speed over polish in delivery", [(f"{CONV}:3", "I also think you value speed over polish.")],
          predicate="values", category="value"),                                          # not_own_voice
    _fact("delegating execution once a deadline is set",                                 # ok, inferred
          [("S1", "I want the migration done before Friday."), ("S2", "yes, do that.")],
          inferred=True, predicate="practices", category="habit"),
    {"subject": "user", "predicate": "values", "object": "ungrounded claim here",
     "category": "value", "confidence": 0.9, "inferred": True},                            # no_grounding
]

# What the fake model returns on the LEGACY path: the same assistant-sourced idea.
LEGACY_FACTS = [
    {"subject": "user", "predicate": "values", "object": "speed over polish",
     "qualifier": "unknown", "category": "value", "temporal": "current", "confidence": 0.9},
]


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------

class FakeCollection:
    def __init__(self):
        self.metadata = {"hnsw:space": "cosine"}
        self.items = {}          # id -> metadata
        self.queries = []        # the `where` each query received

    def count(self):
        return len(self.items)

    def add(self, ids, embeddings, documents, metadatas):
        for i, m in zip(ids, metadatas):
            self.items[i] = dict(m)

    def delete(self, ids):
        for i in ids:
            self.items.pop(i, None)

    def get(self, where=None, include=None):
        k, v = next(iter(where.items()))
        return {"ids": [i for i, m in self.items.items() if m.get(k) == v]}

    def query(self, query_embeddings, n_results, where=None):
        self.queries.append(where)
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


class FakeClient:
    collection = None

    def __init__(self, path=None):
        pass

    def get_collection(self, name):
        if FakeClient.collection is None:
            raise ValueError("no collection")
        return FakeClient.collection

    def create_collection(self, name, metadata=None):
        FakeClient.collection = FakeCollection()
        return FakeClient.collection


class FakeVec(list):
    def tolist(self):
        return list(self)


class FakeST:
    def __init__(self, name):
        pass

    def encode(self, texts):
        return FakeVec([[0.1, 0.2, 0.3] for _ in texts])


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fresh corpus directory under tmp_path, with every extraction dependency faked."""
    import baselayer.config as cfg
    import baselayer.extract_facts as ef
    from baselayer.init_database import init_database

    db = tmp_path / "data" / "database" / "memory.db"
    init_database(db)

    def _get_db(db_path=None):
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(ef, "get_db", _get_db)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    FakeClient.collection = None
    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=FakeClient))
    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        types.SimpleNamespace(SentenceTransformer=FakeST))
    monkeypatch.delenv("BASELAYER_TURN_CONTRACT", raising=False)
    monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
    monkeypatch.delenv("BASELAYER_SKIP_COVERAGE_GATE", raising=False)
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    # Turn mode refuses without a configured referent (TURN_CONTRACT.md §5). The
    # corpus directory's own import config, never the operator's.
    monkeypatch.delenv("BASELAYER_IMPORT_CONFIG", raising=False)
    (tmp_path / "data" / "import_config.json").write_text(
        json.dumps({"subject_names": ["Dana Reyes", "Dana"]}), encoding="utf-8")
    return types.SimpleNamespace(db=db, root=tmp_path, ef=ef, get_db=_get_db)


# Detector per non-citable class, taken from what the importer writes.
from baselayer.voice import D_PASTE_STRUCTURAL  # noqa: E402

_DETECTOR = {"assistant": "source:role=assistant", "pasted": D_PASTE_STRUCTURAL,
             "harness_prompt": "source:promptSource=sdk"}


def _seed(env, with_turns=True, source="chatgpt", conv=CONV, turns=TURNS, turn_version=V):
    c = env.get_db()
    c.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?)",
              (conv, "Migration plan", 1.0, 2.0, len(turns), source))
    for o, sp, vc, role, text in turns:
        c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
                  (f"{conv}-m{o}", conv, None, role, text, "text", float(o), o))
    if with_turns:
        # The REAL turn table, as init_database creates it (baselayer.turns.SCHEMA).
        # Named columns only: the table has more columns than the §4a binding set,
        # and its CHECK requires a detector exactly on the non-citable rows, so the
        # fixture uses the importer's own detector names.
        for o, sp, vc, role, text in turns:
            c.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, "
                      "voice_class, text, detector, source, turn_contract_version) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (f"{conv}:{o}", conv, o, sp, vc, text, _DETECTOR.get(vc), source,
                       turn_version))
    c.commit()
    c.close()


def _fake_llm(facts, prompts=None):
    def call(prompt, schema=None, retries=None, max_tokens=None):
        if prompts is not None:
            prompts.append((prompt, schema, max_tokens))
        return {"facts": json.loads(json.dumps(facts))}
    return call


def _facts(env):
    c = env.get_db()
    rows = [dict(r) for r in c.execute("SELECT * FROM memory_facts")]
    c.close()
    return rows


def _records(env):
    d = env.root / "data" / "database" / "extraction_runs"
    # Ordered by start time: run ids share a one-second timestamp prefix, so two
    # runs inside one second would otherwise sort by their random suffix.
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")]
    return sorted(recs, key=lambda r: r["started_at"])


# ---------------------------------------------------------------------------
# the headline: legacy stores the assistant's words, the turn path rejects them
# ---------------------------------------------------------------------------

def test_legacy_stores_assistant_sourced_fact(env, monkeypatch):
    _seed(env, with_turns=False)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(LEGACY_FACTS))
    env.ef.run_extraction()
    facts = _facts(env)
    assert [f["object_text"] for f in facts] == ["speed over polish"]
    # stored with no grounding at all, and not stamped as gated
    assert facts[0]["source_turn_id"] is None and facts[0]["turn_contract_version"] is None
    # but legacy facts are now stamped with model, prompt hash, commit and a relative path
    assert facts[0]["extraction_model"] and facts[0]["extraction_prompt_hash"]
    assert facts[0]["code_path"] == "src/baselayer/extract_facts.py"


def test_turn_path_rejects_the_same_fact_and_keeps_grounded_ones(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    # The max_tokens assertion below is the capped budget; the uncounted modes' budget is
    # pinned in test_output_budget.py.
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    prompts = []
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS, prompts))
    env.ef.run_extraction()

    facts = _facts(env)
    objects = sorted(f["object_text"] for f in facts)
    assert objects == ["delegating execution once a deadline is set", "short emails to vendors"]
    assert not any("polish" in o for o in objects)

    by = {f["object_text"]: f for f in facts}
    short = by["short emails to vendors"]
    assert short["source_turn_id"] == f"{CONV}:2"
    assert json.loads(short["evidence_spans"]) == [
        {"turn_id": f"{CONV}:2", "span": "Keep the email short.", "evidence_kind": "prose"}]
    assert short["inferred"] == 0 and short["voice_class"] == "own_typed"
    inferred = by["delegating execution once a deadline is set"]
    assert inferred["inferred"] == 1
    assert [s["turn_id"] for s in json.loads(inferred["evidence_spans"])] == [f"{CONV}:0", f"{CONV}:2"]
    for f in facts:
        assert f["turn_contract_version"] == V
        assert f["extraction_model"] and len(f["extraction_prompt_hash"]) == 16
        assert f["code_path"] == "src/baselayer/extract_facts.py"
        assert f["git_commit"]

    # one prompt, carrying citable aliases only for the subject's turns
    assert len(prompts) == 1
    prompt, schema, max_tokens = prompts[0]
    assert "[S1 | SUBJECT, typed]" in prompt and "[S3 | SUBJECT, spoken]" in prompt
    assert "[ASSISTANT | not citable]" in prompt
    assert "[PASTED MATERIAL, not the subject's words | not citable]" in prompt
    assert "S4" not in prompt
    assert "evidence_spans" in json.dumps(schema)
    # Dynamic cap on (the turn-mode default): max facts = ceil(chars / CHARS_PER_FACT),
    # and the budget is sized at TURN_EXTRACTION_TOKENS_PER_FACT per grounded fact.
    import math
    from baselayer.config import CHARS_PER_FACT
    chars = sum(len(t[4]) for t in TURNS)
    assert max_tokens == max(2000, math.ceil(chars / CHARS_PER_FACT) * 180 + 2000)

    rec = _records(env)[-1]
    assert rec["gate_rejections"] == {"no_grounding": 1, "no_turn": 0,
                                      "not_own_voice": 1, "span_not_found": 1, "span_length": 0, "self_object": 0}
    assert rec["counts"]["candidates"] == 5 and rec["counts"]["accepted"] == 2
    assert rec["counts"]["facts_stored"] == 2
    assert rec["settings"]["context_char_budget"] and rec["settings"]["turn_table"] == "turns"
    assert rec["stamp"]["general"]["code_path"] == "src/baselayer/extract_facts.py"
    assert rec["suspect"] == []


def test_run_output_reports_the_rejections(env, monkeypatch, capsys):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    env.ef.run_extraction()
    out = capsys.readouterr().out
    assert "candidates 5 | accepted 2" in out
    assert "no_grounding 1 | no_turn 0 | not_own_voice 1 | span_not_found 1" in out
    assert "run record:" in out


def test_gate_that_rejects_everything_is_flagged(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS[1:3]))
    env.ef.run_extraction()
    assert _facts(env) == []
    assert "gate_rejected_everything" in _records(env)[-1]["suspect"]


# ---------------------------------------------------------------------------
# the gate sits outside every handler
# ---------------------------------------------------------------------------

def test_a_raising_gate_propagates_and_commits_nothing(env, monkeypatch):
    _seed(env)
    _seed(env, conv="conv-2")
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))

    def broken_gate(results, referent=None):
        raise RuntimeError("gate broke")

    monkeypatch.setattr(env.ef, "gate_turn_chunks", broken_gate)
    with pytest.raises(RuntimeError, match="gate broke"):
        env.ef.run_extraction()
    assert _facts(env) == []
    rec = _records(env)[-1]
    assert any("aborted" in n for n in rec["notes"])


def test_a_storage_failure_rolls_back_the_conversation(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    real_embed = env.ef.embed_fact
    calls = []

    def embed_then_fail(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("vector store down")
        return real_embed(*a, **k)

    monkeypatch.setattr(env.ef, "embed_fact", embed_then_fail)
    with pytest.raises(RuntimeError, match="vector store down"):
        env.ef.run_extraction()
    assert _facts(env) == []                    # first fact's INSERT rolled back
    assert FakeClient.collection.count() == 0   # and its vector removed


# ---------------------------------------------------------------------------
# mode selection and the fresh-corpus assumption
# ---------------------------------------------------------------------------

def test_turn_mode_requires_the_turn_table(env, monkeypatch):
    _seed(env, with_turns=False)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    with pytest.raises(env.ef.TurnContractViolation, match="turn table"):
        env.ef.run_extraction()


def test_turn_mode_refuses_document_mode(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    with pytest.raises(env.ef.TurnContractViolation, match="document"):
        env.ef.run_extraction(document_mode=True)


def _stamp_a_gated_fact(env):
    """A corpus that was EXTRACTED under the turn contract: one stamped fact."""
    c = env.get_db()
    c.execute("INSERT INTO memory_facts (id, fact_text, turn_contract_version) "
              "VALUES ('gated', 'user prefers short emails', ?)", (V,))
    c.commit()
    c.close()


def test_legacy_mode_refuses_a_turn_contract_corpus(env, monkeypatch):
    # A turn-contract corpus is one holding gated facts. Turn rows alone are not
    # refused (see test_legacy_runs_on_a_turn_imported_corpus): every importer
    # writes them, and `baselayer run` extracts on the legacy path.
    _seed(env)
    _stamp_a_gated_fact(env)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(LEGACY_FACTS))
    with pytest.raises(env.ef.TurnContractViolation, match="--turn-contract"):
        env.ef.run_extraction()
    assert [f["id"] for f in _facts(env)] == ["gated"]     # nothing legacy was stored


def test_legacy_runs_on_a_turn_imported_corpus(env, monkeypatch):
    """The importer writes turn rows AND the legacy messages projection. The
    legacy path must keep running on such a corpus (it is what `baselayer run`
    calls); only gated facts make a corpus off-limits to it."""
    _seed(env)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(LEGACY_FACTS))
    env.ef.run_extraction()
    facts = _facts(env)
    assert [f["object_text"] for f in facts] == ["speed over polish"]
    assert facts[0]["turn_contract_version"] is None


def test_turn_mode_refuses_a_database_with_legacy_facts(env, monkeypatch):
    _seed(env)
    c = env.get_db()
    c.execute("INSERT INTO memory_facts (id, fact_text) VALUES ('old', 'user values legacy things')")
    c.commit()
    c.close()
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    with pytest.raises(env.ef.TurnContractViolation, match="FRESH corpus"):
        env.ef.run_extraction()


def test_turn_mode_refuses_unstamped_vectors(env, monkeypatch):
    _seed(env)
    FakeClient.collection = FakeCollection()
    FakeClient.collection.items["ghost"] = {"fact_id": "ghost", "category": "value"}
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    with pytest.raises(env.ef.TurnContractViolation, match="vector store"):
        env.ef.run_extraction()


def test_audn_only_ever_searches_same_version_facts(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    env.ef.run_extraction()
    col = FakeClient.collection
    # every AUDN search is restricted to this version AND to the fact's own grounding
    assert col.queries and all(w == {"$and": [{"turn_contract_version": V}, {"grounding": "prose"}]} for w in col.queries)
    assert col.items and all(m["turn_contract_version"] == V for m in col.items.values())


def test_legacy_embeds_carry_no_version_key(env, monkeypatch):
    _seed(env, with_turns=False)
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(LEGACY_FACTS))
    env.ef.run_extraction()
    col = FakeClient.collection
    assert col.items and all("turn_contract_version" not in m for m in col.items.values())
    assert all(w is None for w in col.queries)


def test_conversation_without_turns_is_a_counted_hard_error(env, monkeypatch):
    _seed(env)
    _seed(env, with_turns=False, conv="conv-no-turns")
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    with pytest.raises(SystemExit) as e:
        env.ef.run_extraction()
    assert e.value.code == 2
    rec = _records(env)[-1]
    assert rec["counts"]["conversations_without_turns"] == 1
    assert rec["counts"]["facts_stored"] == 2  # the other conversation still ran


# ---------------------------------------------------------------------------
# caps, backstop, post-gate drops
# ---------------------------------------------------------------------------

def test_density_backstop_counts_accepted_facts_only(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 2, "input_char_budget": 24000})
    # 5 candidates, 2 accepted: at the backstop, not over it, so no halt
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    env.ef.run_extraction()
    assert len(_facts(env)) == 2


def test_accepted_runaway_is_reported_not_halted(env, monkeypatch):
    """The conversation-level halt is retired on the turn path (the density alarm and the
    spend ceiling replace it, test_density_alarm_and_spend). A conversation whose accepted
    facts run past the old backstop is stored whole and listed in the density block."""
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 2, "input_char_budget": 24000})
    # small chunks: each subject turn lands in its own chunk, so the per-chunk
    # cap (2) is respected in every chunk and only the conversation total runs away
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 2, "input_char_budget": 250})
    import re

    def per_chunk(prompt, schema=None, retries=None, max_tokens=None):
        first = re.search(r"\[S1 \| SUBJECT[^\]]*\]\n(.+)", prompt).group(1)
        return {"facts": [_fact(f"grounded fact {i} {first[:8]}", [("S1", first[:12])])
                          for i in range(2)]}

    monkeypatch.setattr(env.ef, "call_llm", per_chunk)
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["facts_after_validation"] > 2          # past the old backstop of 2
    assert rec["density"]["top10"][0]["conversation_id"] == CONV
    assert not any("coverage gate halted" in n for n in rec["notes"])


# The D-048 contamination filter is OFF in turn mode (D-108): see
# tests/test_turn_defaults.py, which also pins that the legacy path still applies it.


def test_turn_output_budget_is_sized_for_spans():
    from baselayer.extract_facts import _turn_extraction_max_tokens, _extraction_max_tokens
    assert _turn_extraction_max_tokens(100) > _extraction_max_tokens(100)
    assert _turn_extraction_max_tokens(100) >= 100 * 180


# ---------------------------------------------------------------------------
# prompt hash
# ---------------------------------------------------------------------------

def test_prompt_hash_ignores_content_and_tracks_wording(monkeypatch):
    import baselayer.extract_facts as ef
    h_general, h_project = ef.turn_prompt_hash(False), ef.turn_prompt_hash(True)
    assert h_general != h_project
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "\nKNOWN: Alex (friend)")
    assert ef.turn_prompt_hash(False) == h_general          # corpus data does not move it
    monkeypatch.setattr(ef, "_TURN_LABELS_HELP", ef._TURN_LABELS_HELP + " Reworded.")
    assert ef.turn_prompt_hash(False) != h_general          # wording does


def test_mutation_without_the_gate_the_assistant_fact_gets_through(env, monkeypatch):
    """Can-fail check on the headline test: replace the gate with one that
    accepts everything, and the assistant's words are stored as the subject's.
    So it is the gate, not the fixture, that keeps them out."""
    import baselayer.turn_contract as tc
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))

    def accept_all(raw, chunk, referent=None):
        g = tc.GateResult(candidates=len(raw))
        for f in raw:
            f = dict(f)
            f.update(source_turn_id="unchecked", voice_class="unchecked", inferred=False,
                     evidence_spans=f.get("evidence_spans") or [])
            g.accepted.append(f)
        return g

    monkeypatch.setattr(tc, "gate_facts", accept_all)
    env.ef.run_extraction()
    assert any("polish" in f["object_text"] for f in _facts(env))


def test_turns_from_another_contract_version_are_refused(env, monkeypatch):
    _seed(env, turn_version="turn-contract/0")
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(TURN_FACTS))
    with pytest.raises(env.ef.TurnContractViolation, match="turn-contract/0"):
        env.ef.run_extraction()
    assert _facts(env) == []


def test_unstamped_turns_are_counted():
    """check_turn_versions counts turns with no version. The real schema makes
    such a row impossible (next test), so the counter is exercised on Turn
    objects directly: it stays as a backstop for a table built some other way."""
    import types as _t
    import baselayer.turn_contract as tc
    from baselayer.extract_facts import check_turn_versions
    turns = [tc.Turn(f"{CONV}:{o}", CONV, sp, vc, text, o, None)
             for o, sp, vc, role, text in TURNS]
    record = _t.SimpleNamespace(c={"turns_unstamped": 0})
    check_turn_versions(turns, record)
    assert record.c["turns_unstamped"] == len(TURNS)


def test_the_real_turn_table_refuses_an_unstamped_turn(env):
    with pytest.raises(sqlite3.IntegrityError):
        _seed(env, turn_version=None)


def test_legacy_process_conversation_refuses_in_turn_mode(env, monkeypatch):
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    with pytest.raises(env.ef.TurnContractViolation, match="legacy"):
        env.ef.process_conversation({"id": CONV, "title": "t", "source": "chatgpt"},
                                    None, None, None)


# ---------------------------------------------------------------------------
# the dynamic cap on the TURN path, through the real caps (no patch)
# ---------------------------------------------------------------------------

def _dense_seed(env):
    """12 turns, 6 of them ~2,900-char subject turns (~17.5K chars in all). The
    static tiers cap the conversation at 20 facts; the density backstop
    (ceil(chars / 175)) is about 101. The fake model grounds 8 facts in each
    subject turn, 48 in all: 140% over the static cap, well under the backstop."""
    turns = []
    for i in range(12):
        if i % 2 == 0:
            body = " ".join(f"Subject note {i}-{k}: I decide by looking at evidence {k}." for k in range(55))
            turns.append((i, "subject", "own_typed", "user", body))
        else:
            turns.append((i, "assistant", "assistant", "assistant", f"Assistant reply {i}."))
    _seed(env, turns=turns)
    return turns


def _dense_llm():
    import re

    def call(prompt, schema=None, retries=None, max_tokens=None):
        facts = []
        for alias, body in re.findall(r"\[(S\d+) \| SUBJECT[^\]]*\]\n(.+)", prompt):
            notes = re.findall(r"Subject note \d+-\d+: I decide by looking at evidence \d+\.", body)
            for n in notes[:8]:
                facts.append(_fact(f"weighs {n[13:18]} before deciding", [(alias, n)],
                                   predicate="practices", category="habit"))
        return {"facts": facts}
    return call


def test_dense_conversation_completes_without_the_dynamic_cap(env, monkeypatch):
    """Used to halt on the static tiers (20 facts). The conversation-level halt and trim are
    retired on the turn path, so it completes; each chunk keeps its per-chunk cap."""
    _dense_seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "0")      # explicit off; the turn default is on
    monkeypatch.setattr(env.ef, "call_llm", _dense_llm())
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["accepted"] == 48
    kept = 48 - rec["post_gate_drops"].get("over_per_chunk_cap", 0)     # per-chunk cap 20
    assert rec["counts"]["facts_stored"] == rec["counts"]["facts_after_validation"] == kept > 20
    assert "over_conversation_cap" not in rec["post_gate_drops"]
    assert not any("coverage gate halted" in n for n in rec["notes"])


def test_dense_conversation_completes_with_the_dynamic_cap(env, monkeypatch):
    _dense_seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
    monkeypatch.setattr(env.ef, "call_llm", _dense_llm())
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["settings"]["dynamic_cap"] is True
    assert rec["counts"]["accepted"] == 48 and rec["counts"]["facts_stored"] == 48
    assert rec["post_gate_drops"] == {}


# ---------------------------------------------------------------------------
# the preflight is read-only
# ---------------------------------------------------------------------------

def test_preflight_refuses_without_altering_the_database(tmp_path, monkeypatch):
    """A turn-mode run pointed at a database without a turn table (for instance
    the live one, by a missing MEMORY_SYSTEM_ROOT) refuses before
    create_tables(), so the database gains no columns."""
    import baselayer.extract_facts as ef
    db = tmp_path / "old.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT NOT NULL)")
    c.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
    c.commit()
    before = [r[1] for r in c.execute("PRAGMA table_info(memory_facts)")]
    c.close()

    def _get_db(db_path=None):
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(ef, "get_db", _get_db)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    with pytest.raises(ef.TurnContractViolation, match="turn table"):
        ef.run_extraction()
    c = sqlite3.connect(str(db))
    assert [r[1] for r in c.execute("PRAGMA table_info(memory_facts)")] == before
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"memory_facts", "conversations"}


# ---------------------------------------------------------------------------
# fork / resume copies (the importer's duplicate_of) are context, never citable
# ---------------------------------------------------------------------------

def test_a_duplicate_turn_is_not_citable(env, monkeypatch):
    """The importer keeps fork and resume copies of a session's turns and marks
    them `duplicate_of = <owner session>`. The owner's row is the citable one; a
    copy cited again would store the same grounding twice and bill for it
    twice. The legacy projection already skips copies; the turn path must too."""
    _seed(env)
    c = env.get_db()
    c.execute("UPDATE turns SET duplicate_of='owner-session' WHERE turn_id=?", (f"{CONV}:2",))
    c.commit()
    c.close()
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    prompts = []
    facts = [_fact("short emails to vendors", [(f"{CONV}:2", "Keep the email short.")]),
             _fact("wants the migration before Friday",
                   [("S1", "I want the migration done before Friday.")])]
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(facts, prompts))
    env.ef.run_extraction()
    stored = [f["object_text"] for f in _facts(env)]
    assert stored == ["wants the migration before Friday"]
    rec = _records(env)[-1]
    assert rec["gate_rejections"]["not_own_voice"] == 1
    prompt = prompts[0][0]
    assert "yes, do that. Keep the email short." in prompt       # still shown as context
    assert "[S1 | SUBJECT, typed]" in prompt and "[S2 | SUBJECT, typed]" not in prompt
