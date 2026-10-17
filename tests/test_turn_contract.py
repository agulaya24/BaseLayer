"""
Turn contract, extraction side: turn table reading, turn-bounded chunking, and
the §5 gate (docs/core/TURN_CONTRACT.md). Synthetic fixtures only.

The fixture's turn-table schema is the contract's §1 column list. The real table
is written by the importer (feat/respec-import); this suite does not depend on
that code, only on the contract.
"""

import random
import sqlite3

import pytest

from baselayer import turn_contract as tc

from baselayer.turn_contract import Referent as _Referent  # noqa: E402
_REFERENT = _Referent(names=("Dana Reyes",))


CONV = "conv-aaaa"


def _turns(n=12):
    """n alternating subject/assistant turns; turn 5 is pasted, turn 7 a tool result."""
    out = []
    for i in range(n):
        if i == 5:
            vc, sp, text = "pasted", "subject", f"PASTED BLOCK {i}: the vendor terms say net 90."
        elif i == 7:
            vc, sp, text = "tool_result", "subject", "[tool result]"
        elif i % 2 == 0:
            vc, sp, text = "own_typed", "subject", f"Subject turn {i}: I prefer plain answers, number {i}."
        else:
            vc, sp, text = "assistant", "assistant", f"Assistant turn {i}: shall I draft option {i}?"
        out.append(tc.Turn(f"{CONV}:{i}", CONV, sp, vc, text))
    return out


def _table(conn, turns, ordinals=True):
    """The turn table with the contract's binding §4a columns."""
    conn.execute(f"""CREATE TABLE {tc.TURN_TABLE} (turn_id TEXT PRIMARY KEY, conversation_id TEXT,
                     ordinal INTEGER, speaker TEXT, voice_class TEXT, text TEXT, detector TEXT,
                     turn_contract_version TEXT)""")
    rows = [(t.turn_id, t.conversation_id, tc.turn_sort_key(t.turn_id)[0] if ordinals else None,
             t.speaker, t.voice_class, t.text, None, tc.TURN_CONTRACT_VERSION) for t in turns]
    random.Random(7).shuffle(rows)
    conn.executemany(f"INSERT INTO {tc.TURN_TABLE} VALUES (?,?,?,?,?,?,?,?)", rows)


# ---------------------------------------------------------------------------
# ordering and loading
# ---------------------------------------------------------------------------

def test_sort_is_numeric_not_lexical():
    ids = [f"{CONV}:{i}" for i in (10, 2, 1, 11, 0)] + [f"{CONV}:2.1", f"{CONV}:2.0"]
    assert sorted(ids, key=tc.turn_sort_key) == [
        f"{CONV}:0", f"{CONV}:1", f"{CONV}:2", f"{CONV}:2.0", f"{CONV}:2.1",
        f"{CONV}:10", f"{CONV}:11"]


def test_sort_key_handles_colons_in_conversation_id():
    assert tc.turn_sort_key("a:b:c:12") == (12, -1)


def test_sort_key_rejects_malformed_id():
    with pytest.raises(ValueError):
        tc.turn_sort_key("no-ordinal-here")


def test_load_turns_orders_and_detects_table():
    conn = sqlite3.connect(":memory:")
    assert not tc.turn_table_exists(conn)
    _table(conn, _turns(12))
    assert tc.turn_table_exists(conn)
    loaded = tc.load_turns(conn, CONV)
    assert [t.turn_id for t in loaded] == [f"{CONV}:{i}" for i in range(12)]
    assert loaded[11].ordinal == 11 and loaded[0].contract_version == tc.TURN_CONTRACT_VERSION


def test_load_turns_orders_by_parsed_id_when_ordinal_is_null():
    conn = sqlite3.connect(":memory:")
    _table(conn, _turns(12), ordinals=False)
    assert [t.turn_id for t in tc.load_turns(conn, CONV)] == [f"{CONV}:{i}" for i in range(12)]


def test_load_turns_prefers_the_ordinal_column():
    # the ordinal column is authoritative when present; segments order within it
    conn = sqlite3.connect(":memory:")
    turns = [tc.Turn(f"{CONV}:{i}", CONV, "subject", "own_typed", f"t{i}") for i in range(3)]
    _table(conn, turns)
    conn.execute(f"UPDATE {tc.TURN_TABLE} SET ordinal = 5 WHERE turn_id = ?", (f"{CONV}:0",))
    conn.execute(f"INSERT INTO {tc.TURN_TABLE} VALUES (?,?,?,?,?,?,?,?)",
                 (f"{CONV}:5.1", CONV, 5, "subject", "pasted", "seg", "paste", None))
    order = [t.turn_id for t in tc.load_turns(conn, CONV)]
    assert order == [f"{CONV}:1", f"{CONV}:2", f"{CONV}:0", f"{CONV}:5.1"]


# ---------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------

def _chunks(turns, budget=300, ctx=400, ctx_turns=3, xform=None):
    return tc.build_chunks(turns, budget, context_budget=ctx, context_max_turns=ctx_turns,
                           noncitable_transform=xform)


def test_chunks_contain_whole_turns_in_order():
    turns = _turns(12)
    chunks = _chunks(turns)
    assert len(chunks) > 1
    seen = [p.turn.turn_id for ch in chunks for p in ch.body]
    assert seen == [t.turn_id for t in turns]
    for ch in chunks:
        for p in ch.body:
            assert p.parts == 1 and p.text == next(t.text for t in turns if t.turn_id == p.turn.turn_id)


def test_only_own_voice_turns_get_citable_ids():
    for ch in _chunks(_turns(12)):
        for alias, tid in ch.alias_to_turn.items():
            assert ch.body_voice[tid] in tc.CITABLE_VOICE_CLASSES
        cited = set(ch.alias_to_turn.values())
        for p in ch.body:
            assert (p.turn.turn_id in cited) == p.turn.citable
        # the rendered body offers aliases only on subject turns
        for line in ch.rendered_body.split("\n"):
            if line.startswith("[S"):
                assert "SUBJECT" in line
            if line.startswith("[") and ("ASSISTANT" in line or "PASTED MATERIAL" in line
                                         or "TOOL OUTPUT" in line):
                assert "not citable" in line


def test_chunk_carries_preceding_turns_as_context_without_ids():
    chunks = _chunks(_turns(12))
    assert chunks[0].context == []
    second = chunks[1]
    first_body_idx = len(chunks[0].body)
    prev = _turns(12)[first_body_idx - 1]
    assert second.context, "second chunk must carry the turns before it"
    assert prev.text in second.context[-1][1] or second.context[-1][1].endswith(prev.text[-50:])
    assert "CONTEXT" in second.rendered_context
    for alias in second.alias_to_turn:
        assert f"[{alias} " not in second.rendered_context


def test_context_respects_turn_and_char_caps():
    chunks = _chunks(_turns(12), budget=250, ctx=60, ctx_turns=2)
    for ch in chunks[1:]:
        assert len(ch.context) <= 2
        assert sum(len(t) for _, t in ch.context) <= 60 + len("[...] ")


def test_oversize_turn_is_split_into_segments_that_keep_turn_id():
    big = " ".join(f"Sentence {i} about my plan." for i in range(200))
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", big),
             tc.Turn(f"{CONV}:1", CONV, "assistant", "assistant", "ok")]
    chunks = _chunks(turns, budget=500)
    segs = [p for ch in chunks for p in ch.body if p.turn.turn_id == f"{CONV}:0"]
    assert len(segs) > 1
    assert "".join(p.text for p in segs) == big            # exact, contiguous cover
    assert all(p.parts == len(segs) for p in segs)
    assert all(len(p.text) <= 500 for p in segs)
    # every chunk holding a segment offers that turn as citable
    for ch in chunks:
        if any(p.turn.turn_id == f"{CONV}:0" for p in ch.body):
            assert f"{CONV}:0" in ch.alias_to_turn.values()


def test_citable_text_is_verbatim_even_with_a_transform():
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", "```code``` keep me EXACTLY"),
             tc.Turn(f"{CONV}:1", CONV, "assistant", "assistant", "x" * 900)]
    ch = _chunks(turns, budget=5000, xform=lambda s: s[:10] + " [...]")[0]
    assert "```code``` keep me EXACTLY" in ch.rendered_body
    assert "x" * 11 not in ch.rendered_body


def test_chunk_with_no_subject_turns_has_no_citable():
    turns = [tc.Turn(f"{CONV}:{i}", CONV, "assistant", "assistant", "a" * 100) for i in range(3)]
    assert not any(ch.has_citable for ch in _chunks(turns, budget=250))


def test_unknown_voice_class_is_not_citable():
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "mystery", "hello there")]
    ch = _chunks(turns)[0]
    assert not ch.has_citable
    assert "UNCLASSIFIED" in ch.rendered_body


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

@pytest.fixture
def chunk():
    turns = [
        tc.Turn(f"{CONV}:0", CONV, "assistant", "assistant", "Shall I migrate the schema tonight?"),
        tc.Turn(f"{CONV}:1", CONV, "subject", "own_typed", "yes, do that. I’d rather  ship\nearly."),
        tc.Turn(f"{CONV}:2", CONV, "subject", "pasted", "Vendor terms: net 90."),
        tc.Turn(f"{CONV}:3", CONV, "subject", "own_dictated", "Call it Base Layer."),
    ]
    return _chunks(turns, budget=5000)[0]


def _f(*pairs, inferred=False):
    """A raw fact grounded in (turn_ref, span) pairs."""
    return {"subject": "user", "predicate": "prefers", "object": "x", "category": "preference",
            "confidence": 0.9, "inferred": inferred,
            "evidence_spans": [{"turn": r, "span": s} for r, s in pairs]}


def test_gate_accepts_alias_and_resolves_real_id(chunk):
    alias = next(a for a, t in chunk.alias_to_turn.items() if t == f"{CONV}:1")
    g = tc.gate_facts([_f((alias, "yes, do that"))], chunk, referent=_REFERENT)
    assert len(g.accepted) == 1 and not g.rejected
    a = g.accepted[0]
    assert a["source_turn_id"] == f"{CONV}:1"
    assert a["voice_class"] == "own_typed"
    # exactly the §4a shape: {"turn_id", "span", "evidence_kind"} per span, voice on the fact
    assert a["evidence_spans"] == [{"turn_id": f"{CONV}:1", "span": "yes, do that",
                                    "evidence_kind": "prose"}]
    assert a["grounding"] == "prose"
    assert a["inferred"] is False


def test_gate_accepts_real_turn_id_and_dictated(chunk):
    g = tc.gate_facts([_f((f"{CONV}:3", "Call it Base Layer."))], chunk, referent=_REFERENT)
    assert len(g.accepted) == 1 and g.accepted[0]["voice_class"] == "own_dictated"


def test_gate_accepts_inference_grounded_in_several_own_turns(chunk):
    # A fact need not be a quote: an understanding drawn from two turns passes
    # when every span it rests on is the subject's own words.
    fact = _f((f"{CONV}:1", "rather ship early"), (f"{CONV}:3", "Call it Base Layer"), inferred="true")
    fact["object"] = "moves to naming and shipping quickly once a direction is set"
    g = tc.gate_facts([fact], chunk, referent=_REFERENT)
    assert len(g.accepted) == 1
    a = g.accepted[0]
    assert [s["turn_id"] for s in a["evidence_spans"]] == [f"{CONV}:1", f"{CONV}:3"]
    assert a["source_turn_id"] == f"{CONV}:1" and a["inferred"] is True


def test_gate_normalises_quotes_and_whitespace(chunk):
    g = tc.gate_facts([_f((f"{CONV}:1", "I'd rather ship early."))], chunk, referent=_REFERENT)
    assert len(g.accepted) == 1


@pytest.mark.parametrize("span", [
    "yes, do that... ship early.",    # ellipsis-joined
    "Yes, do that",                    # case change
    "I would rather ship early",       # paraphrase
    "",                                # empty
    None,                              # not a string
])
def test_gate_rejects_span_not_found(chunk, span):
    g = tc.gate_facts([_f((f"{CONV}:1", span))], chunk, referent=_REFERENT)
    assert g.rejected == {"span_not_found": 1} and not g.accepted


@pytest.mark.parametrize("spans", [None, [], "yes, do that", {"turn": "S1"}])
def test_gate_rejects_fact_without_grounding(chunk, spans):
    fact = _f()
    fact["evidence_spans"] = spans
    g = tc.gate_facts([fact, "not a dict"], chunk, referent=_REFERENT)
    assert g.rejected == {"no_grounding": 2} and not g.accepted


def test_gate_rejects_grounding_only_in_assistant_or_pasted_text(chunk):
    g = tc.gate_facts([_f((f"{CONV}:0", "Shall I migrate the schema tonight?")),
                       _f((f"{CONV}:2", "Vendor terms: net 90."))], chunk, referent=_REFERENT)
    assert g.rejected == {"not_own_voice": 2}


def test_gate_rejects_fact_mixing_own_and_non_own_spans(chunk):
    # every span must be own-voice; one assistant span sinks the fact
    g = tc.gate_facts([_f((f"{CONV}:1", "yes, do that"),
                          (f"{CONV}:0", "Shall I migrate the schema tonight?"))], chunk, referent=_REFERENT)
    assert g.rejected == {"not_own_voice": 1}


def test_gate_counts_the_first_failing_span(chunk):
    g = tc.gate_facts([_f((f"{CONV}:1", "not in the turn"), (f"{CONV}:0", "Shall I"))], chunk, referent=_REFERENT)
    assert g.rejected == {"span_not_found": 1}


def test_gate_rejects_unknown_turn_and_missing_ref(chunk):
    g = tc.gate_facts([_f(("S99", "yes")), _f((f"{CONV}:77", "yes")), _f((None, "yes"))], chunk, referent=_REFERENT)
    assert g.rejected == {"no_turn": 3} and g.candidates == 3


def test_gate_rejects_own_turn_that_is_only_context():
    turns = [tc.Turn(f"{CONV}:{i}", CONV, "subject", "own_typed", f"Own words number {i} " + "z" * 150)
             for i in range(4)]
    chunks = _chunks(turns, budget=300, ctx=2000, ctx_turns=4)
    second = chunks[1]
    ctx_turn = f"{CONV}:0"
    assert ctx_turn not in second.body_voice
    assert any("Own words number 0" in t for _, t in second.context)
    g = tc.gate_facts([_f((ctx_turn, "Own words number 0"))], second, referent=_REFERENT)
    assert g.rejected == {"no_turn": 1}


def test_gate_checks_span_against_the_segment_shown():
    big = "AAAA first half words. " * 30 + "BBBB second half words. " * 30
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", big)]
    chunks = _chunks(turns, budget=700)
    assert len(chunks) >= 2
    first = chunks[0]
    g_ok = tc.gate_facts([_f((f"{CONV}:0", "AAAA first half words."))], first, referent=_REFERENT)
    g_bad = tc.gate_facts([_f((f"{CONV}:0", "BBBB second half words."))], first, referent=_REFERENT)
    assert len(g_ok.accepted) == 1
    assert g_bad.rejected == {"span_not_found": 1}


def test_manifest_round_trip_rebuilds_the_gate(chunk):
    m = chunk.manifest()
    assert all(isinstance(x, (str, int)) for row in m["citable"] for x in row)
    import json
    assert "rather" not in json.dumps(m)  # ids and offsets, never turn text
    texts = {t: (v, None) for t, v in chunk.body_voice.items()}
    full = {f"{CONV}:1": ("own_typed", "yes, do that. I’d rather  ship\nearly."),
            f"{CONV}:3": ("own_dictated", "Call it Base Layer.")}
    rebuilt = tc.chunk_from_manifest(m, full)
    alias = next(a for a, t in chunk.alias_to_turn.items() if t == f"{CONV}:1")
    assert tc.gate_facts([_f((alias, "rather ship early"))], rebuilt, referent=_REFERENT).accepted
    # a turn reclassified to pasted after submit is no longer citable
    full[f"{CONV}:1"] = ("pasted", full[f"{CONV}:1"][1])
    rebuilt = tc.chunk_from_manifest(m, full)
    assert tc.gate_facts([_f((alias, "rather ship early"))], rebuilt, referent=_REFERENT).rejected == {"no_turn": 1}


# ---------------------------------------------------------------------------
# run record
# ---------------------------------------------------------------------------

def test_run_record_flags_gate_that_rejects_nothing_or_everything(tmp_path):
    r = tc.ExtractionRunRecord("turn", {"k": 1})
    g = tc.GateResult(accepted=[{}] * 25, candidates=25)
    r.add_gate(g)
    assert "gate_rejected_nothing" in r.to_dict()["suspect"]
    r2 = tc.ExtractionRunRecord("turn", {})
    from collections import Counter
    r2.add_gate(tc.GateResult(accepted=[], rejected=Counter(no_turn=3), candidates=3))
    d = r2.to_dict()
    assert "gate_rejected_everything" in d["suspect"]
    assert d["gate_rejections"] == {"no_grounding": 0, "no_turn": 3, "not_own_voice": 0,
                                    "span_not_found": 0, "span_length": 0, "self_object": 0}
    conn = sqlite3.connect(":memory:")
    path = r2.write(conn=conn, root=tmp_path)
    assert path.exists() and path.parent == tmp_path / "data" / "database" / "extraction_runs"
    assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 1


def test_git_commit_of_never_raises(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("")
    assert tc.git_commit_of(f) == "unknown"


@pytest.mark.skipif(__import__("shutil").which("git") is None, reason="needs a git checkout")
def test_code_path_is_repo_relative_never_absolute(tmp_path):
    import os
    st = tc.extraction_stamp("m", "h")
    assert st["code_path"] == "src/baselayer/turn_contract.py"
    assert not os.path.isabs(st["code_path"]) and ":" not in st["code_path"]
    assert st["git_commit"] != "unknown"
    f = tmp_path / "pkg" / "x.py"
    f.parent.mkdir()
    f.write_text("")
    assert tc.code_path_of(f) == "pkg/x.py"
