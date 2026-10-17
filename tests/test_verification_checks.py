"""Modular verify-spec checks (src/baselayer/verification/checks).

Each check is tested two-sided: a planted defect must be caught AND a clean control must pass,
so a check that flags nothing and a check that flags everything both fail. Every fixture is
synthetic (a made-up gardener with a lemon tree called Pip); no model is called, and the back-check
slot is asserted never to start a process.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from baselayer.verification import checks as vc
from baselayer.verification import run as vrun
from baselayer.verification.checks import backcheck, corrections, integrity, occasions, time_split
from baselayer.verification.checks.base import session_key
from baselayer.verification.corpus import Corpus, open_readonly
from baselayer.verification.spec_io import load_spec

DAY = 86400.0
T0 = 1_700_000_000.0          # 2023-11-14
V = "turn-contract/1"


def fid(n: int) -> str:
    return f"{n:08x}-0000-0000-0000-{n:012x}"


# conversation, day offset, speaker, voice, text
TURNS = {
    "s1:0": ("s1", 0, "subject", "own_typed", "I water the tomatoes before sunrise, never at noon."),
    "s1:1": ("s1", 0, "assistant", "assistant", "Mulch solves most problems in a dry summer."),
    "s1:2": ("s1", 0, "subject", "own_typed", "I log every missed watering in a notebook."),
    "s2:0": ("s2", 40, "subject", "own_typed", "Pip’s feed goes in at 8 am, one scoop at the root."),
    "s3:0": ("s3", 200, "subject", "own_typed", "Now I water at dusk, sunrise is too cold for the seedlings."),
    "s4:0": ("s4", 400, "subject", "own_typed", "dusk watering works, the beds stay moist overnight."),
    "dbcopy_11111111-2222-3333-4444-555555555555:0": ("dbcopy_11111111-2222-3333-4444-555555555555", 90, "subject",
                                                      "own_typed", "I prune the roses in late winter."),
    "history_11111111-2222-3333-4444-555555555555:0": ("history_11111111-2222-3333-4444-555555555555", 90, "subject",
                                                       "own_typed", "I prune the roses in late winter, every year."),
    "s5:0": ("s5", 500, "subject", "own_typed", "The Compost Bin Is Full Again."),
}

# fact number -> (fact text, [(turn id, span)])
FACTS = {
    1: ("user waters before sunrise", [("s1:0", "water the tomatoes before sunrise")]),
    2: ("user logs missed watering", [("s1:2", "log every missed watering")]),
    3: ("user feeds Pip", [("s2:0", "Pip's feed goes in at 8 am")]),       # curly apostrophe in the turn
    4: ("user waters at dusk", [("s3:0", "Now I water at dusk")]),
    5: ("user waters at dusk now", [("s4:0", "dusk watering works")]),
    6: ("user prunes roses in winter", [("dbcopy_11111111-2222-3333-4444-555555555555:0", "prune the roses")]),
    7: ("user prunes roses yearly", [("history_11111111-2222-3333-4444-555555555555:0", "prune the roses in late winter")]),
    8: ("user relies on mulch", [("s1:1", "Mulch solves most problems")]),
    9: ("user composts", [("s1:0", "the compost bin is overflowing")]),                     # span not in its turn
    10: ("user empties the compost", [("s5:0", "the compost bin is full again")]),         # case only
    11: ("user believes Pip will die without the feed", [("s2:0", "one scoop at the root")]),
}


def make_corpus(root: Path) -> Path:
    from baselayer.init_database import init_database
    db = root / "data" / "database" / "memory.db"
    init_database(db)
    c = sqlite3.connect(str(db))
    convs = {t[0]: t[1] for t in TURNS.values()}
    for cv, d in convs.items():
        c.execute("INSERT INTO conversations (id, title, source, created_at) VALUES (?,?,?,?)",
                  (cv, "garden", "chatgpt", T0 + d * DAY))
    for i, (tid, (cv, d, spk, voice, text)) in enumerate(TURNS.items()):
        c.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, text, detector, "
                  "turn_contract_version, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                  (tid, cv, int(tid.rsplit(":", 1)[1]), spk, voice, text,
                   None if voice.startswith("own") else "source:role", V, T0 + d * DAY + 3600))
    for n, (text, spans) in FACTS.items():
        sp = [{"turn_id": t, "span": s} for t, s in spans]
        c.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id, source_turn_id, "
                  "evidence_spans, turn_contract_version) VALUES (?,?,?,?,?,?,?)",
                  (fid(n), text, "habit", TURNS[spans[0][0]][0], spans[0][0], json.dumps(sp), V))
    c.commit()
    c.close()
    return db


def cl(cid, facts, statement="A statement.", contested=False, name=None, active="A new bed is planted"):
    return {"id": cid, "name": name or f"CLAIM {cid}", "statement": statement, "active_when": active,
            "fact_ids": ["F-" + (f if isinstance(f, str) else fid(f)[:8]) for f in facts], "contested": contested}


def make_spec(d: Path, layers: dict, brief: str | None = None) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for layer, claims in layers.items():
        (d / f"{layer}.json").write_text(json.dumps({"layer": layer, "claims": claims}), encoding="utf-8")
    if brief is not None:
        (d / "brief.md").write_text(brief, encoding="utf-8")
    return d


RULES = {"corrections": [
    {"id": "gardener:CORR-001", "rules": [{"kind": "violation", "pattern": "\\bQX9\\b", "flags": ""}]},
    {"id": "gardener:CORR-002", "rules": [{"kind": "requires_nearby", "pattern": "nautical (slang|terms)", "flags": "i",
                                           "nearby": "sailing (club|crew)", "window": 250}]},
    {"id": "gardener:CORR-003", "rules": [{"kind": "review", "pattern": "\\bPip\\b", "flags": "i",
                                           "nearby": "\\b(death|die|dies|dying|fatal)\\b", "window": 200, "ignore_quoted": True,
                                           "quoted_framing": "\\b(worst[- ]case|risk\\w*|serious|illness(es)?|anxious\\w*)\\b"}]},
]}


@pytest.fixture
def world(tmp_path):
    corpus = tmp_path / "corpus"
    make_corpus(corpus)
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps(RULES), encoding="utf-8")
    return tmp_path, corpus, rules


def ctx_for(tmp: Path, corpus: Path, spec_dir: Path, **options):
    conn, info = open_readonly(corpus / "data" / "database" / "memory.db", tmp / "_snap")
    return vc.CheckContext(load_spec(spec_dir, "g"), Corpus(conn, info), options)


def by_claim(run):
    return {r.claim: r for r in run.results}


# ---------------------------------------------------------------- (a) corrections
def test_corrections_catches_each_rule_kind_and_passes_clean_controls(world):
    tmp, corpus, rules = world
    spec = make_spec(tmp / "spec", {"core": [
        cl("C1", [1], "Their greenhouse is a QX9 model."),                                        # violation
        cl("C2", [1], "Their greenhouse is a QX8 model."),                                        # clean
        cl("C3", [1], "They use nautical terms (starboard) and refer to their friend Sam."),       # qualifier missing
        cl("C4", [1], "They use nautical terms (starboard), only with their sailing club."),      # qualifier present
        cl("C5", [2], "Pip has had serious blights, tracked anxiously ('pip could die if the frost comes early')."),
        cl("C6", [2], "Pip is under fleece. They once wrote 'pip could die if the frost comes early'."),
        cl("C7", [2], "Pip may die of the blight."),                                               # plain review
    ]}, brief="# Brief\n\nThey own a QX9.\n")
    run = corrections.run(ctx_for(tmp, corpus, spec, corrections=str(rules)))
    r = by_claim(run)
    assert run.status == "ran"
    assert r["g:C1"].status == "fail" and "CORR-001" in r["g:C1"].reason
    assert r["g:C2"].status == "pass"
    assert r["g:C3"].status == "fail" and "CORR-002" in r["g:C3"].reason
    assert r["g:C4"].status == "pass"
    assert r["g:C5"].status == "flag" and "through a quote" in r["g:C5"].reason       # the tightening
    assert r["g:C6"].status == "pass"                                                   # a bare quote stays exempt
    assert r["g:C7"].status == "flag"
    files = [x for x in run.results if x.claim is None]
    assert len(files) == 1 and files[0].status == "fail" and files[0].evidence_ids == ["brief.md:3"]


def test_corrections_flags_a_claim_citing_a_fact_that_carries_the_overturned_version(world):
    tmp, corpus, rules = world
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [3, 11], "Pip gets feed at 8 am."),
                                             cl("C2", [3], "Pip gets feed at 8 am.")]})
    run = corrections.run(ctx_for(tmp, corpus, spec, corrections=str(rules)))
    r = by_claim(run)
    assert r["g:C1"].status == "flag" and r["g:C1"].evidence_ids == ["F-" + fid(11)[:8]]
    assert r["g:C2"].status == "pass"
    assert run.summary["corrections"]["gardener:CORR-003"]["fact_carriers"] == ["F-" + fid(11)[:8]]


def test_corrections_quote_in_an_evidence_or_fact_text_is_not_framing():
    txt = "Pip: serious blight logged ('pip could die if the frost comes early')"
    assert corrections.scan_text(txt, RULES, "fact") == []                  # fact / evidence text: quote exempt
    assert corrections.scan_text(txt, RULES, "prose")[0]["how"] == "framing_through_quote"
    bare = "Pip: logged ('pip could die if the frost comes early')"
    assert corrections.scan_text(bare, RULES, "prose") == []                # no framing words: exempt


def test_corrections_without_rules_is_not_run_and_a_bad_file_is_an_error(world, tmp_path):
    tmp, corpus, _ = world
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [1])]})
    assert corrections.run(ctx_for(tmp, corpus, spec)).status == "not_run"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"corrections": [{"id": "x", "rules": [{"kind": "review", "pattern": "a"}]}]}), encoding="utf-8")
    run = corrections.run(ctx_for(tmp, corpus, spec, corrections=str(bad)))
    assert run.status == "error" and "nearby" in run.reason


# ---------------------------------------------------------------- (b) occasions
def test_occasions_flags_a_single_occasion_prediction_and_passes_two(world):
    tmp, corpus, _ = world
    spec = make_spec(tmp / "spec", {
        "anchors": [cl("A1", [1, 2])],                  # one occasion, but anchors are not checked by default
        "predictions": [cl("P1", [1, 2]),                # one conversation, one day
                        cl("P2", [1, 4]),                # two conversations, two days
                        cl("P3", [6, 7])]})              # one session imported twice, one day
    run = occasions.run(ctx_for(tmp, corpus, spec))
    r = by_claim(run)
    assert r["g:P1"].status == "flag" and r["g:P1"].data["occasions"] == 1
    assert r["g:P2"].status == "pass" and r["g:P2"].data["occasions"] == 2
    assert r["g:P3"].status == "flag" and r["g:P3"].data["conversations"] == 1     # dbcopy_/history_ collapse
    assert r["g:A1"].status == "pass"
    assert run.summary["distribution"]["min"]["predictions"] == {1: 2, 2: 1}


def test_occasions_units_threshold_and_layers_are_parameters(world):
    tmp, corpus, _ = world
    spec = make_spec(tmp / "spec", {"anchors": [cl("A1", [1, 2])], "predictions": [cl("P2", [1, 4])]})
    ctx = ctx_for(tmp, corpus, spec)
    r = by_claim(occasions.run(ctx, min_occasions=3, layers=()))
    assert r["g:A1"].status == "flag" and r["g:P2"].status == "flag"
    assert occasions.run(ctx, unit="bogus").status == "error"


def test_session_key_collapses_reimported_sessions():
    u = "11111111-2222-3333-4444-555555555555"
    assert session_key(f"dbcopy_{u}") == session_key(f"history_{u}") == session_key(u) == u
    assert session_key("meeting_ab12") == "meeting_ab12"


# ---------------------------------------------------------------- (c) time split
def test_time_split_labels_a_change_over_time_and_not_an_interleaved_contradiction(world):
    tmp, corpus, _ = world
    f = lambda n: "F-" + fid(n)[:8]
    spec = make_spec(tmp / "spec", {"anchors": [
        cl("A1", [1, 2, 4, 5], contested=True),          # sunrise (day 0) then dusk (day 200, 400)
        cl("A2", [1, 4, 2, 5], contested=True),          # the same facts, sides interleaved
        cl("A3", [1, 2], contested=True),                # one side empty
        cl("A4", [1, 4], contested=True),                # no side assignment at all
        cl("A5", [1, 4])]})                              # not contested: not checked
    sides = {"A1": {f(1): "1", f(2): "1", f(4): "2", f(5): "2"},
             "A2": {f(1): "1", f(4): "1", f(2): "2", f(5): "2"},
             "A3": {f(1): "1", f(2): "1"}}
    run = time_split.run(ctx_for(tmp, corpus, spec, sides=sides))
    r = by_claim(run)
    assert r["g:A1"].status == "flag" and r["g:A1"].data["label"] == "changed_over_time" and r["g:A1"].data["clean"]
    assert r["g:A2"].status == "pass" and r["g:A2"].data["label"] == "not_separated"
    assert r["g:A3"].data["label"] == "undetermined"
    assert r["g:A4"].status == "flag" and r["g:A4"].data["label"] == "no_sides"
    assert "g:A5" not in r


def test_time_split_gap_threshold_and_missing_side_source(world):
    tmp, corpus, _ = world
    f = lambda n: "F-" + fid(n)[:8]
    spec = make_spec(tmp / "spec", {"anchors": [cl("A1", [1, 3], contested=True)]})   # day 0 vs day 40
    sides = {"A1": {f(1): "1", f(3): "2"}}
    assert by_claim(time_split.run(ctx_for(tmp, corpus, spec, sides=sides)))["g:A1"].data["label"] == "changed_over_time"
    assert by_claim(time_split.run(ctx_for(tmp, corpus, spec, sides=sides), min_gap_days=60))["g:A1"].data["label"] == "not_separated"
    assert time_split.run(ctx_for(tmp, corpus, spec)).status == "not_run"


# ---------------------------------------------------------------- (d) integrity
def test_integrity_catches_each_defect_and_passes_a_clean_claim(world):
    tmp, corpus, _ = world
    excl = tmp / "exclude.json"
    excl.write_text(json.dumps({"ids": [fid(2)[:8]]}), encoding="utf-8")
    spec = make_spec(tmp / "spec", {"core": [
        cl("C1", [1, 3], "They 'water the tomatoes before sunrise'."),      # clean; F-3 matches after quote normalisation
        cl("C2", [1, "deadbeef"]),                                          # unresolved citation
        cl("C3", [2]),                                                      # on the exclude list
        cl("C4", [9]),                                                      # span not in its turn
        cl("C5", [10]),                                                     # span matches only after case folding
        cl("C6", [1], "They say 'water the roses at noon'."),               # quote not in any cited own span
        cl("C7", [8], "They say 'Mulch solves most problems'."),            # quote only in an assistant span
    ]})
    run = integrity.run(ctx_for(tmp, corpus, spec, exclude_ids=[str(excl)]))
    r = by_claim(run)
    assert run.status == "ran"
    assert r["g:C1"].status == "pass", r["g:C1"].reason
    assert r["g:C2"].status == "fail" and "unresolved" in r["g:C2"].reason
    assert r["g:C3"].status == "fail" and "exclude" in r["g:C3"].reason
    assert r["g:C4"].status == "fail" and "not_found" in r["g:C4"].reason
    assert r["g:C5"].status == "flag" and "case" in r["g:C5"].reason
    assert r["g:C6"].status == "fail" and "quoted words" in r["g:C6"].reason
    assert r["g:C7"].status == "fail" and "quoted words" in r["g:C7"].reason
    assert run.summary["spans"]["normalised"] == 1 and run.summary["spans"]["not_found"] == 1


def test_integrity_refuses_a_malformed_exclude_file(world):
    tmp, corpus, _ = world
    bad = tmp / "bad.txt"
    bad.write_text("not-an-id\n", encoding="utf-8")
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [1])]})
    assert integrity.run(ctx_for(tmp, corpus, spec, exclude_ids=[str(bad)])).status == "error"


# ---------------------------------------------------------------- (e) back-check slot
def write_backcheck(root: Path, sides_for: dict) -> Path:
    run = root / "runs" / "full_1"
    run.mkdir(parents=True)
    rows = []
    for cid, (verdict, scope, sides) in sides_for.items():
        rows.append({"key": f"M_{cid}", "kind": "main", "qid": cid, "model": "judge-model",
                     "judgement": {"verdict": verdict, "scope": {"verdict": scope}, "missing": "x",
                                   "facts": [{"id": k, "support": "supports", "origin": "his_assertion", "side": v}
                                             for k, v in sides.items()],
                                   "contested": {"verdict": "real"} if sides else None}})
    rows.append({"key": "X1", "kind": "plant", "qid": "A1", "judgement": {"verdict": "unsupported"}})
    (run / "judgements.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return root


def test_backcheck_loads_results_never_runs_a_process_and_feeds_time_split(world, monkeypatch):
    tmp, corpus, _ = world

    def boom(*a, **k):
        raise AssertionError("the back-check slot must never start a process")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    f = lambda n: "F-" + fid(n)[:8]
    root = write_backcheck(tmp / "bc", {"A1": ("partly", "within", {f(1): "1", f(4): "2"}),
                                        "P1": ("overreaches", "within", {}),
                                        "P2": ("partly", "overgeneralises", {})})
    spec = make_spec(tmp / "spec", {"anchors": [cl("A1", [1, 4], contested=True)],
                                    "predictions": [cl("P1", [1]), cl("P2", [4]), cl("P3", [5])]})
    ctx_opts = {"backcheck_results": str(root)}
    conn, info = open_readonly(corpus / "data" / "database" / "memory.db", tmp / "_snap")
    runs, data = vc.run_checks(["time_split", "backcheck"], load_spec(spec, "g"), Corpus(conn, info), ctx_opts)
    b = by_claim(runs["backcheck"])
    assert b["g:A1"].status == "pass" and b["g:P1"].status == "fail" and b["g:P2"].status == "flag"
    assert b["g:P3"].status == "flag" and "no verdict" in b["g:P3"].reason
    assert data.claims["A1"]["verdict"] == "partly"                       # the plant row was not read as A1
    assert by_claim(runs["time_split"])["g:A1"].data["label"] == "changed_over_time"
    cmd = backcheck.Judge162External(results=root).command()
    assert cmd[-4:] == [str(root / "judge162.py"), "run", "--run-id", "full_1"]


def test_backcheck_without_results_is_not_run_and_names_the_command(world, tmp_path):
    tmp, corpus, _ = world
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [1])]})
    run = backcheck.run(ctx_for(tmp, corpus, spec, backcheck_script=str(tmp_path / "judge162.py")))
    assert run.status == "not_run" and "judge162.py run" in run.reason
    assert backcheck.run(ctx_for(tmp, corpus, spec)).status == "not_run"


# ---------------------------------------------------------------- the command
def test_verify_spec_runs_chosen_checks_and_writes_the_summary(world, capsys):
    tmp, corpus, rules = world
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [1], "A QX9 owner.")], "predictions": [cl("P1", [1, 2])]})
    out = tmp / "out"
    rc = vrun.main([str(spec), "--label", "g", "--corpus", str(corpus), "--out", str(out),
                    "--checks", "corrections,occasions,integrity", "--corrections", str(rules)])
    assert rc == 0
    rep = json.loads((out / "g.verification.json").read_text(encoding="utf-8"))
    assert set(rep["modular_checks"]) == {"corrections", "occasions", "integrity"}
    assert rep["meta"]["model"]["tasks"] == {}                             # no model check was named
    assert rep["summary"]["modular_checks"]["corrections"]["fail"] == 1
    assert any(f["kind"] == "modular" and f["check"] == "occasions" for f in rep["findings"])
    assert (out / "g.summary.md").read_text(encoding="utf-8").startswith("# Verify summary: g")


def test_verify_spec_named_check_without_its_input_is_refused_default_records_not_run(world):
    tmp, corpus, _ = world
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [1])]})
    with pytest.raises(SystemExit, match="corrections"):
        vrun.main([str(spec), "--label", "g", "--corpus", str(corpus), "--out", str(tmp / "o1"), "--checks", "corrections"])
    rc = vrun.main([str(spec), "--label", "g", "--corpus", str(corpus), "--out", str(tmp / "o2")])
    rep = json.loads((tmp / "o2" / "g.verification.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert rep["modular_checks"]["corrections"]["status"] == "not_run"
    assert rep["modular_checks"]["time_split"]["status"] == "not_run"
    assert rep["modular_checks"]["integrity"]["status"] == "ran"


def test_verify_spec_exits_nonzero_when_a_check_cannot_run(world, tmp_path):
    tmp, corpus, _ = world
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    spec = make_spec(tmp / "spec", {"core": [cl("C1", [1])]})
    rc = vrun.main([str(spec), "--label", "g", "--corpus", str(corpus), "--out", str(tmp / "o"),
                    "--checks", "corrections", "--corrections", str(bad)])
    assert rc == 2
