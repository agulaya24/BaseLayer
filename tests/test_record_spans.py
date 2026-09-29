"""
Structured-record spans (TURN_CONTRACT.md §5, evidence kind and grounding).

A row from a pasted trade log ("3/04<TAB>3/02/2024<TAB>-$37.50") passes the span
length bound, because its tokens split on whitespace, yet a row alone says little
about the person. The gate classifies each span MECHANICALLY by its shape, not by
a model: `record` for tab-separated or columnar rows and for spans that are mostly
numbers, dates and symbols; `prose` otherwise. A fact grounded ONLY by record
spans is kept and counted with `grounding: record_only`, excluded from
distillation input by default; a fact with at least one prose span is normal.
The extraction prompt and schema the model sees are unchanged.
"""

import json
import sqlite3
import sys

import pytest

import baselayer.turn_contract as tc

REF = tc.Referent(names=("Dana Reyes",))
CONV = "conv-r"


@pytest.mark.parametrize("span", [
    "3/04\t3/02/2024\t-$37.50",
    "3/04 3/02/2024 -$37.50",                 # tabs lost in transit: still mostly numbers
    "XYZ   40C   3/02   -37.50",            # columnar
    "2024-03-02 XYZ 40 -37 +12",
    "Date\tTicker\tP/L",                        # a header row is a row
])
def test_rows_are_records(span):
    assert tc.span_evidence_kind(span) == "record"


@pytest.mark.parametrize("span", [
    "I closed the position at a loss of $37 today",
    "Do you have any materials?",
    "3/02 felt good about the trade today",
    "I track my daily P/L every evening to stay honest.",
    "we cut 3 of the 12 drafts in 2023",
])
def test_sentences_are_prose(span):
    assert tc.span_evidence_kind(span) == "prose"


# Content over layout: a layout signal (tab, two or more column gaps, a leading date) makes
# a span a record only when its alphabetic share is also under the dated cut (0.75). A
# tab used as an indent in front of a sentence is prose.
@pytest.mark.parametrize("span", [
    "•	Planned and ran the weekly reviews with the regional sales leads",
    "4/02		-$120.00	Overall the plan held up and I kept notes through the day",
    "Weekly review   went well overall   and I will keep the same plan next week",
])
def test_layout_with_mostly_words_is_prose(span):
    assert tc.span_evidence_kind(span) == "prose"


@pytest.mark.parametrize("span", [
    "3/02 40 1.20 -37.50",                       # date and numbers
    "3/02 sold 40 at 1.20",                      # date plus a short trade row
    "3/02	XYZ	-37.50",                        # tabbed, mostly values
])
def test_date_and_number_rows_are_records(span):
    assert tc.span_evidence_kind(span) == "record"


def _chunk():
    turns = [
        tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed",
                "3/04\t3/02/2024\t-$37.50\n3/05\t3/03/2024\t+$12.25"),
        tc.Turn(f"{CONV}:1", CONV, "subject", "own_typed",
                "I track my daily P/L every evening to stay honest."),
    ]
    return tc.build_chunks(turns, 5000, context_budget=400, context_max_turns=3)[0]


def _fact(*pairs):
    return {"subject": "user", "predicate": "practices", "object": "daily P/L tracking",
            "category": "habit", "confidence": 0.9, "inferred": True,
            "evidence_spans": [{"turn_id": t, "span": s} for t, s in pairs]}


def test_gate_tags_each_span_and_the_fact():
    only_rows = _fact((f"{CONV}:0", "3/04\t3/02/2024\t-$37.50"),
                      (f"{CONV}:0", "3/05\t3/03/2024\t+$12.25"))
    mixed = _fact((f"{CONV}:0", "3/04\t3/02/2024\t-$37.50"),
                  (f"{CONV}:1", "I track my daily P/L every evening"))
    g = tc.gate_facts([only_rows, mixed], _chunk(), referent=REF)
    a, b = g.accepted
    assert [s["evidence_kind"] for s in a["evidence_spans"]] == ["record", "record"]
    assert a["grounding"] == "record_only"
    assert [s["evidence_kind"] for s in b["evidence_spans"]] == ["record", "prose"]
    assert b["grounding"] == "prose"
    assert g.record_only == 1


def test_record_only_count_reaches_the_run_record():
    rec = tc.ExtractionRunRecord("turn", {})
    rec.add_gate(tc.gate_facts([_fact((f"{CONV}:0", "3/04\t3/02/2024\t-$37.50"))], _chunk(),
                               referent=REF))
    assert rec.to_dict()["counts"]["record_only"] == 1


def test_the_model_never_sees_the_classification():
    """No new model-side categorisation: prompt and schema carry no evidence kind."""
    import baselayer.extract_facts as ef
    assert "evidence_kind" not in json.dumps(ef.TURN_EXTRACT_SCHEMA)
    assert "record_only" not in json.dumps(ef.TURN_EXTRACT_SCHEMA)
    prompt = ef.build_turn_extraction_prompt("t", "", "[S1 | SUBJECT, typed] hi", max_facts=3,
                                             entity_hints="")
    assert "evidence_kind" not in prompt and "record_only" not in prompt


# ---------------------------------------------------------------------------
# storage, AUDN and distillation
# ---------------------------------------------------------------------------

from tests.test_turn_extraction import (  # noqa: E402,F401  (env is a fixture)
    FakeClient, _facts, _fake_llm, _records, _seed, env)
from tests.test_artifact_stamps import no_network  # noqa: E402,F401  (fixture)

ROW_TURNS = [
    (0, "subject", "own_typed", "user", "3/04\t3/02/2024\t-$37.50\n3/05\t3/03/2024\t+$12.25"),
    (1, "subject", "own_typed", "user", "I track my daily P/L every evening to stay honest. "
     + "It keeps me from pretending a bad week was a good one, and it gives me a record "
     + "I can read back when I am deciding whether to change how I size a position."),
]


def _llm_fact(obj, *pairs):
    return {"subject": "user", "predicate": "practices", "object": obj, "qualifier": "unknown",
            "category": "habit", "temporal": "current", "confidence": 0.9, "inferred": True,
            "evidence_spans": [{"turn": t, "span": s} for t, s in pairs]}


def test_record_only_fact_is_stored_kept_and_marked(env, monkeypatch):
    _seed(env, turns=ROW_TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm([
        _llm_fact("daily trade logging", ("S1", "3/04\t3/02/2024\t-$37.50")),
        _llm_fact("evening P/L review", ("S2", "I track my daily P/L every evening")),
    ]))
    env.ef.run_extraction()
    by_obj = {f["object_text"]: f for f in _facts(env)}
    assert by_obj["daily trade logging"]["grounding"] == "record_only"
    assert by_obj["evening P/L review"]["grounding"] == "prose"
    spans = json.loads(by_obj["daily trade logging"]["evidence_spans"])
    assert spans[0]["evidence_kind"] == "record"
    assert _records(env)[-1]["counts"]["record_only"] == 1
    # vectors carry the grounding, and AUDN searches within one grounding only
    metas = list(FakeClient.collection.items.values())
    assert sorted(m["grounding"] for m in metas) == ["prose", "record_only"]
    wheres = [w for w in FakeClient.collection.queries if w]
    assert {"grounding": "record_only"} in wheres[0]["$and"]
    assert {"grounding": "prose"} in wheres[1]["$and"]


def test_audn_search_filter_by_grounding_works_in_real_chroma(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    from baselayer.extract_facts import embed_fact, find_similar_facts

    class _Vec(list):
        def tolist(self):
            return list(self)

    class _Model:
        def encode(self, texts):
            return _Vec([[1.0, 0.0, 0.0] for _ in texts])

    col = chromadb.PersistentClient(path=str(tmp_path / "v")).create_collection(
        "memory_facts", metadata={"hnsw:space": "cosine"})
    V = tc.TURN_CONTRACT_VERSION
    embed_fact("rec", "user logs trades", "habit", col, _Model(), contract_version=V,
               grounding="record_only")
    embed_fact("pro", "user logs trades daily", "habit", col, _Model(), contract_version=V,
               grounding="prose")
    got = find_similar_facts("user logs trades", col, _Model(), contract_version=V,
                             grounding="prose")
    assert [s["fact_id"] for s in got] == ["pro"]
    got = find_similar_facts("user logs trades", col, _Model(), contract_version=V,
                             grounding="record_only")
    assert [s["fact_id"] for s in got] == ["rec"]


def _distill_db(root):
    from tests.test_artifact_stamps import FACTS
    db = root / "data" / "database" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, predicate TEXT, "
              "category TEXT, superseded_by TEXT, created_at REAL, turn_contract_version TEXT, "
              "source_conversation_id TEXT, grounding TEXT)")
    for i, (fid, text, ver) in enumerate(FACTS):
        c.execute("INSERT INTO memory_facts VALUES (?,?,?,?,NULL,?,?,?,?)",
                  (fid, text, "prefers", "preference", float(i), ver, "conv-%d" % i,
                   "record_only" if i == 0 else "prose"))
    c.commit()
    c.close()
    return db


def _distill(monkeypatch, db, out, *extra):
    from baselayer.distillation import distill
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "2",
                                      "--layer", "anchors", *extra])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def test_distill_excludes_record_only_facts_by_default(no_network, monkeypatch, tmp_path):
    tree = _distill(monkeypatch, _distill_db(tmp_path / "c"), tmp_path / "t.json")
    assert tree["stamp"]["facts_total"] == 2
    assert tree["stamp"]["record_only_facts_excluded"] == 1
    assert tree["stamp"]["record_only_facts_included"] == 0


def test_distill_includes_record_only_facts_when_asked(no_network, monkeypatch, tmp_path):
    tree = _distill(monkeypatch, _distill_db(tmp_path / "c"), tmp_path / "t.json",
                    "--include-record-only")
    assert tree["stamp"]["facts_total"] == 3
    assert tree["stamp"]["record_only_facts_excluded"] == 0
    assert tree["stamp"]["record_only_facts_included"] == 1


@pytest.mark.parametrize("script,extra", [
    ("distill_batch.py", ["--outdir", "OUT", "--layers", "anchors", "--partitions", "predicate"]),
    ("convergence.py", ["--out", "OUT", "--runs", "1"]),
])
def test_every_distillation_reader_excludes_record_only_by_default(script, extra, monkeypatch,
                                                                    tmp_path, capsys):
    """The sibling readers of the fact base apply the same filter as distill.main. Both are
    scripts that call main() at import, so they are run as scripts, dry, with no network."""
    import runpy
    from pathlib import Path
    import baselayer.distillation as pkg
    here = Path(pkg.__file__).parent
    # convergence execs distill.py without a __file__; BASELAYER_SRC is its supported pin
    monkeypatch.setenv("BASELAYER_SRC", str(here.parent.parent))
    from baselayer.distillation import spend
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")
    db = _distill_db(tmp_path / "c")
    extra = [str(tmp_path / "out") if x == "OUT" else x for x in extra]
    for flag, n in (([], 2), (["--include-record-only"], 3)):
        monkeypatch.setattr(sys, "argv", [script, "--db", str(db), "--dry-run",
                                          "--max-facts", "2", *extra, *flag])
        runpy.run_path(str(here / script), run_name="__main__")
        out = capsys.readouterr().out
        assert "facts=%d " % n in out
        assert ("record_only facts: 1 excluded" in out) == (not flag)


# --------------------------------------------------------------------------- threshold pins
# Synthetic spans on either side of each cut (RECORD_MAX_ALPHA_SHARE 0.5, and
# RECORD_DATED_MAX_ALPHA_SHARE 0.75 after a leading date), with the share each
# one has. Both comparisons are strict, so a span exactly at a cut is prose.
# The measured data behind the cuts is outside the repo (RECORD_THRESHOLD_DATA.md
# in the respec plan); these pins make any change to a cut, or to the tie rule,
# visible in the suite.

ALPHA_PINS = [
    ("sold 40 at 1.20 then 25 at 1.35 then 10 at 1.50 and 5 7", 7 / 15, "record"),
    ("sold 40 at 1.20 and 25", 0.5, "prose"),                  # the tie: strict <
    ("sold 40 at 1.20 then 25 at 1.35 later", 5 / 9, "prose"),
]
DATED_PINS = [
    ("3/02 trading review", 2 / 3, "record"),
    ("3/02 sold 40 at 1.20 and kept the rest for overnight", 8 / 11, "record"),
    ("3/02 reviewed the trades", 0.75, "prose"),                # the tie: strict <
    ("3/02 reviewed all the trades", 0.8, "prose"),
]


def _share(span):
    toks = span.split()
    return sum(1 for t in toks if tc._ALPHA_TOKEN.match(t)) / len(toks)


@pytest.mark.parametrize("span,share,kind", ALPHA_PINS + DATED_PINS)
def test_threshold_pins(span, share, kind):
    assert _share(span) == pytest.approx(share)
    assert bool(tc._LEADING_DATE.match(span)) == span.startswith("3/02")
    assert tc.span_evidence_kind(span) == kind


@pytest.mark.parametrize("attr,value", [
    ("RECORD_MAX_ALPHA_SHARE", 0.45), ("RECORD_MAX_ALPHA_SHARE", 0.55),
    ("RECORD_DATED_MAX_ALPHA_SHARE", 0.70), ("RECORD_DATED_MAX_ALPHA_SHARE", 0.80),
])
def test_the_pins_catch_a_moved_cut(monkeypatch, attr, value):
    """Each cut moved by five points flips at least one pin, so the pins above
    fail on a moved threshold rather than passing on any value."""
    monkeypatch.setattr(tc, attr, value)
    flipped = [s for s, _share_, kind in ALPHA_PINS + DATED_PINS
               if tc.span_evidence_kind(s) != kind]
    assert flipped


# Known limits of the shape rule, pinned with the kind a reader would give them.
# strict xfail: if a later rule fixes one, the suite says so.
@pytest.mark.xfail(strict=True, reason="a clock time is not a leading date, and the "
                   "row sits exactly at the 0.5 tie")
def test_known_limit_clock_time_trade_row():
    assert tc.span_evidence_kind("8:50 out at 1.53") == "record"


def test_code_line_is_stopped_upstream_by_the_paste_detector():
    # Formerly a strict xfail here: code with English keywords has a prose-like share, so
    # the shape rule calls it prose. The limit is discharged upstream, not in the gate:
    # paste:code_or_machine marks the line pasted at import, so it never becomes an
    # own-voice span. span_evidence_kind itself is unchanged.
    from baselayer import voice as V
    line = "for j = i + 1 to n"
    text = "the loop header looks like this\n" + line + "\nshould it start at i instead"
    segs = V.classify_subject_text(text, "", V.VoiceSettings()).segments
    code = [text[s.start:s.end] for s in segs if s.detector == V.D_PASTE_CODE_MACHINE]
    assert code == [line]
    assert all(s.voice_class == "own_typed" for s in segs if s.detector is None)
    assert tc.span_evidence_kind(line) == "prose"


@pytest.mark.xfail(strict=True, reason="_LEADING_DATE matches a plain decimal such as 4.2")
def test_known_limit_decimal_read_as_date():
    assert tc.span_evidence_kind("4.2 it is") == "prose"
