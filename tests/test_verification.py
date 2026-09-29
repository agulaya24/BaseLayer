"""Post-specification verification (src/baselayer/verification).

Every check is tested two-sided: a planted defect must be caught AND a clean control
must not be flagged, so a check that flags nothing and a check that flags everything
both fail. All fixtures are synthetic; no model is called (FakeRater only).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from baselayer.verification import model_checks as mc
from baselayer.verification import run as vrun
from baselayer.verification.corpus import Corpus, open_readonly
from baselayer.verification.deterministic import check_duplicates, check_existing, check_facts, trigger_groups
from baselayer.verification.pricing import estimate
from baselayer.verification.raters import (CLI_SETTINGS, ClaudeCliRater, FakeRater, check_rater_cwd, child_env, run_probe)
from baselayer.verification.spec_io import load_spec, parse_markdown_layer

LIVE = "aaaa0001-0000-0000-0000-000000000001"
LIVE2 = "aaaa0002-0000-0000-0000-000000000002"
LIVE3 = "aaaa0003-0000-0000-0000-000000000003"
ASSIST = "bbbb0001-0000-0000-0000-000000000001"
DOC = "cccc0001-0000-0000-0000-000000000001"
SUPER = "dddd0001-0000-0000-0000-000000000001"
DELETED = "eeee0001-0000-0000-0000-000000000001"
AMB1 = "ffff0001-0000-0000-0000-000000000001"
AMB2 = "ffff0001-0000-0000-0000-000000000002"
NOCONV = "abcd0001-0000-0000-0000-000000000001"
LIVE4 = "aaaa0004-0000-0000-0000-000000000004"
STAMP_MISS = "5a5a0001-0000-0000-0000-000000000001"
STAMP_BAD = "5b5b0001-0000-0000-0000-000000000001"


# ---------------------------------------------------------------- fixtures
def make_db(path: Path, turn_contract: bool = False, wal: bool = False, pending_wal: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    if wal:
        c.execute("PRAGMA journal_mode=WAL")
    extra = ", source_turn_id TEXT, evidence_spans TEXT, turn_contract_version TEXT" if turn_contract else ""
    c.executescript(f"""
    CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT, source TEXT);
    CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content_text TEXT, sequence_order INTEGER);
    CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, superseded_by TEXT, source_conversation_id TEXT,
        category TEXT, recurrence_count INTEGER, temporal_state TEXT, predicate TEXT, object_text TEXT{extra});
    CREATE TABLE user_corrections (id INTEGER PRIMARY KEY, correction_type TEXT, original_fact_id TEXT);
    """)
    c.executemany("INSERT INTO conversations VALUES (?,?,?)", [
        ("conv-u", "garden talk", "chatgpt"), ("conv-a", "assistant only", "chatgpt"), ("conv-d", "resume", "text_file")])
    c.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", [
        ("m0", "conv-u", "user", "I always water the tomatoes before sunrise, never at noon.", 0),
        ("m1", "conv-u", "assistant", "Mulch solves most problems in a dry summer.", 1),
        ("m2", "conv-u", "user", "Right, and I record every missed watering in a notebook.", 2),
        ("m3", "conv-a", "assistant", "Here is some advice about compost.", 0),
        ("m4", "conv-d", "user", "Notes: ran the community garden for two years.", 0)])
    rows = [
        (LIVE, "user waters the tomatoes before sunrise", None, "conv-u", "habit", 1, "current", "practices", "watering"),
        (LIVE2, "user records every missed watering", None, "conv-u", "value", 1, "current", "values", "record keeping"),
        (LIVE3, "user ran the community garden", None, "conv-d", "skill", 1, "past", "worked_as", "organiser"),
        (ASSIST, "user believes mulch solves most problems", None, "conv-a", "value", 1, "current", "believes", "mulch"),
        (DOC, "user ran a garden", None, "conv-d", "skill", 1, "past", "worked_as", "volunteer"),
        (SUPER, "user used to water at noon", LIVE, "conv-u", "habit", 1, "past", "practices", "early"),
        (DELETED, "user deleted fact", None, "conv-u", "habit", 1, "current", "practices", "x"),
        (AMB1, "ambiguous one", None, "conv-u", "habit", 1, "current", "p", "o"),
        (AMB2, "ambiguous two", None, "conv-u", "habit", 1, "current", "p", "o"),
        (NOCONV, "fact with no conversation", None, None, "habit", 1, "current", "p", "o"),
        (LIVE4, "user skips watering when it rains", None, "conv-u", "habit", 1, "current", "practices", "skipping"),
        (STAMP_MISS, "stamp missing fact", None, "conv-u", "habit", 1, "current", "p", "o"),
        (STAMP_BAD, "stamp mismatch fact", None, "conv-u", "habit", 1, "current", "p", "o"),
    ]
    if turn_contract:
        c.execute("CREATE TABLE import_turns (turn_id TEXT PRIMARY KEY, conversation_id TEXT, speaker TEXT, voice_class TEXT, text TEXT, detector TEXT)")
        c.executemany("INSERT INTO import_turns VALUES (?,?,?,?,?,?)", [
            ("conv-u:0", "conv-u", "subject", "own_typed", "I always water the tomatoes before sunrise, never at noon.", None),
            ("conv-u:1", "conv-u", "assistant", "assistant", "Mulch solves most problems in a dry summer.", None),
            ("conv-u:2", "conv-u", "subject", "own_typed", "Right, and I record every missed watering in a notebook.", None)])
        spans = {
            LIVE: ("conv-u:0", "water the tomatoes before sunrise", "turn-contract/1"),
            LIVE2: ("conv-u:2", "I record every “missed watering”".replace("“", "").replace("”", ""), "turn-contract/1"),
            ASSIST: ("conv-u:1", "Mulch solves most problems", "turn-contract/1"),       # cites an assistant turn
            LIVE3: ("conv-u:0", "ran the community garden", "turn-contract/1"),    # span not in the turn
            DOC: ("conv-u:9", "ran the community garden", "turn-contract/1"),      # turn does not exist
            STAMP_MISS: ("conv-u:0", "before sunrise", None),                         # stamp missing: grounding, no version
            STAMP_BAD: ("conv-u:0", "before sunrise", "turn-contract/0"),             # stamp mismatch
            LIVE4: ("conv-u:0", "before sunrise", "turn-contract/1"),
        }
        # the section-4a shape: evidence_spans is a JSON list of {"turn_id", "span"}
        def _cols(v):
            tid, span, version = v
            return (tid, json.dumps([{"turn_id": tid, "span": span}]) if span else None, version)
        rows = [r + _cols(spans.get(r[0], (None, None, None))) for r in rows]
        c.executemany(f"INSERT INTO memory_facts VALUES ({','.join('?' * 12)})", rows)
    else:
        c.executemany(f"INSERT INTO memory_facts VALUES ({','.join('?' * 9)})", rows)
    c.execute("INSERT INTO user_corrections (correction_type, original_fact_id) VALUES ('DELETE', ?)", (DELETED,))
    c.commit()
    if wal and not pending_wal:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if pending_wal:
        c.execute("PRAGMA wal_autocheckpoint=0")
        c.execute("INSERT INTO messages VALUES ('m9','conv-u','user','late row only in the wal',9)")
        c.commit()
        # keep the connection open is not possible across the test; copy the files out instead
        import shutil
        for suf in ("", "-wal", "-shm"):
            src = Path(str(path) + suf)
            if src.exists():
                shutil.copy2(src, Path(str(path) + suf + ".keep"))
    c.close()
    if pending_wal:
        for suf in ("", "-wal", "-shm"):
            keep = Path(str(path) + suf + ".keep")
            if keep.exists():
                keep.replace(Path(str(path) + suf))


def claim(cid, name, facts, active="A new bed is planted", contested=False, statement=None):
    return {"id": cid, "name": name, "statement": statement or f"Statement for {name} about {cid}.",
            "active_when": active, "fact_ids": ["F-" + f[:8] for f in facts], "contested": contested}


def make_spec(d: Path, layers: dict):
    d.mkdir(parents=True, exist_ok=True)
    for layer, claims in layers.items():
        (d / f"{layer}.json").write_text(json.dumps({"layer": layer, "preamble": "", "claims": claims}), encoding="utf-8")


def default_spec(d: Path):
    make_spec(d, {
        "anchors": [claim("A1", "WATER EARLY", [LIVE, LIVE2], active="Any garden task with lasting consequence", contested=True),
                    claim("A2", "LOST CITATIONS", [SUPER, DELETED, AMB1[:8], "99999999"], active="Planning the season")],
        "core": [claim("C1", "WATEREARLY", [LIVE3], active="All kitchen work"),
                 claim("C2", "NOT HIS", [ASSIST, ASSIST[:8]], active="Planning the season")],
        "predictions": [claim("P1", "SHARED A", [LIVE, LIVE2, LIVE3], active="Watering during a heatwave"),
                        claim("P2", "SHARED B", [LIVE, LIVE2, LIVE3], active="Watering during a heatwave", contested=True)],
    })


@pytest.fixture
def world(tmp_path):
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db")
    spec_dir = tmp_path / "spec"
    default_spec(spec_dir)
    return tmp_path, corpus, spec_dir


def open_corpus(corpus: Path, out: Path) -> Corpus:
    conn, info = open_readonly(corpus / "data" / "database" / "memory.db", out / "_snap")
    return Corpus(conn, info)


def by_check(findings, check):
    return [f for f in findings if f["check"] == check]


def dir_state(d: Path) -> dict:
    return {str(p.relative_to(d)): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(d.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------- spec loading
def test_label_is_required_and_ids_are_qualified(world):
    _, _, spec_dir = world
    with pytest.raises(ValueError):
        load_spec(spec_dir, "")
    a, b = load_spec(spec_dir, "specA"), load_spec(spec_dir, "specB")
    assert {c.qid for c in a.claims}.isdisjoint({c.qid for c in b.claims})
    assert "specA:A1" in {c.qid for c in a.claims}


SERVED_MD = """<!-- provenance comment -->

## Injectable Block

# ANCHORS

Preamble text that is not a claim.

## A1 WATER EARLY  (CONTESTED)

Watering happens before the heat.

*Active when:* Any garden task with lasting consequence

*Evidence (2 facts):* [F-aaaa0001] [F-aaaa0002]

## A2 LOST CITATIONS

Second claim.

*Active when:* Planning the season

*Evidence (1 facts):* [F-dddd0001]
"""


def test_markdown_parser_reads_served_layout():
    cl = parse_markdown_layer(SERVED_MD, "anchors", "s")
    assert [c.id for c in cl] == ["A1", "A2"]
    assert cl[0].contested and not cl[1].contested
    assert cl[0].fact_ids == ["aaaa0001", "aaaa0002"]
    assert cl[0].active_when == "Any garden task with lasting consequence"
    assert "Preamble" not in cl[0].statement and "Evidence" not in cl[0].statement


def test_versioned_served_files_are_selected(tmp_path):
    d = tmp_path / "served"
    d.mkdir()
    (d / "anchors_v3.md").write_text(SERVED_MD.replace("A2 LOST", "A9 OLD"), encoding="utf-8")
    (d / "anchors_v4.md").write_text(SERVED_MD, encoding="utf-8")
    s = load_spec(d, "s")
    assert [c.id for c in s.claims] == ["A1", "A2"]
    assert s.files[0]["path"].endswith("anchors_v4.md")


def test_json_markdown_divergence_is_caught(tmp_path):
    d = tmp_path / "spec"
    make_spec(d, {"anchors": [claim("A1", "WATER EARLY", ["aaaa0001", "aaaa0002"], active="Any garden task with lasting consequence", contested=True),
                              claim("A2", "LOST CITATIONS", ["dddd0001"], active="Planning the season")]})
    (d / "anchors.md").write_text(SERVED_MD, encoding="utf-8")
    assert not [f for f in load_spec(d, "s").load_findings if f["check"] == "json_markdown_divergence"]  # clean control
    (d / "anchors.md").write_text(SERVED_MD.replace("[F-aaaa0002]", "").replace("(CONTESTED)", ""), encoding="utf-8")
    fields = {f["field"] for f in load_spec(d, "s").load_findings if f["check"] == "json_markdown_divergence"}
    assert {"fact_ids", "contested"} <= fields


def test_duplicate_claim_id_in_one_spec_is_caught(tmp_path):
    d = tmp_path / "spec"
    make_spec(d, {"anchors": [claim("A1", "X", [LIVE])], "core": [claim("A1", "Y", [LIVE2])]})
    assert [f for f in load_spec(d, "s").load_findings if f["check"] == "duplicate_claim_id"]


# ---------------------------------------------------------------- resolution and voice (fallback)
def test_resolution_catches_every_unresolvable_kind(world):
    tmp, corpus, spec_dir = world
    spec = load_spec(spec_dir, "t")
    prof, f = check_facts(spec, open_corpus(corpus, tmp / "out"))
    bad = by_check(f, "unresolved_citation")
    statuses = {x["fact_ids"][0]: x["status"] for x in bad}
    assert statuses == {"F-" + SUPER[:8]: "superseded", "F-" + DELETED[:8]: "corrected_DELETE",
                        "F-" + AMB1[:8]: "ambiguous", "F-99999999": "missing"}
    assert all(x["claims"] == ["t:A2"] for x in bad)          # the clean claims are not flagged
    assert prof["t:A1"]["resolution"]["ratio"] == 1.0


def test_conversation_fallback_never_invents_turns(world):
    tmp, corpus, spec_dir = world
    spec = load_spec(spec_dir, "t")
    c = open_corpus(corpus, tmp / "out")
    assert not c.turn_columns
    prof, f = check_facts(spec, c)
    rows = {r["id"]: r for p in prof.values() for r in p["facts"]}
    assert rows["F-" + LIVE[:8]]["voice"] == "unresolved_turn_level"
    assert rows["F-" + LIVE3[:8]]["voice"] == "document_import"
    assert rows["F-" + ASSIST[:8]]["voice"] == "no_subject_turns"
    assert all(r["turn_ids"] == [] for r in rows.values())
    not_own = by_check(f, "voice_not_own")
    assert [x["fact_ids"] for x in not_own] == [["F-" + ASSIST[:8]]]   # only the assistant-only conversation
    assert not_own[0]["conversation_ids"] == ["conv-a"]
    assert by_check(f, "duplicate_citation")[0]["claims"] == ["t:C2"]


# ---------------------------------------------------------------- turn contract
def test_turn_gate_rerun_catches_each_reason(tmp_path):
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db", turn_contract=True)
    spec_dir = tmp_path / "spec"
    make_spec(spec_dir, {"anchors": [claim("A1", "X", [LIVE, LIVE2, ASSIST, LIVE3, DOC, STAMP_MISS, STAMP_BAD])]})
    c = open_corpus(corpus, tmp_path / "out")
    assert c.turn_columns and c.turn_table == "import_turns"
    prof, f = check_facts(load_spec(spec_dir, "t"), c)
    reasons = {x["fact_ids"][0]: set(x["reasons"]) for x in by_check(f, "turn_gate_failed")}
    assert "F-" + LIVE[:8] not in reasons and "F-" + LIVE2[:8] not in reasons   # clean controls
    assert reasons["F-" + ASSIST[:8]] == {"not_own_voice"}
    assert reasons["F-" + LIVE3[:8]] == {"span_not_found"}
    assert reasons["F-" + DOC[:8]] == {"no_turn"}
    assert reasons["F-" + STAMP_MISS[:8]] == {"stamp_missing"}
    assert reasons["F-" + STAMP_BAD[:8]] == {"stamp_mismatch"}
    rows = {r["id"]: r for r in prof["t:A1"]["facts"]}
    assert rows["F-" + LIVE[:8]]["turn_ids"] == ["conv-u:0"]
    assert by_check(f, "turn_gate_failed")[0]["turn_ids"]  # findings carry turn ids


def test_span_match_normalises_quotes_and_whitespace(tmp_path):
    from baselayer.verification.corpus import norm_span
    assert norm_span("I  log “every”\nrule") == norm_span('I log "every" rule')


# ---------------------------------------------------------------- duplicates and triggers
def test_duplicates_identical_name_shared_evidence_and_flag_disagreement(world):
    _, _, spec_dir = world
    f, pairs = check_duplicates(load_spec(spec_dir, "t"))
    names = {tuple(x["claims"]) for x in by_check(f, "duplicate_identical_name")}
    assert names == {("t:A1", "t:C1")}                         # WATER EARLY == WATEREARLY
    shared = {tuple(x["claims"]) for x in by_check(f, "duplicate_shared_evidence")}
    assert ("t:P1", "t:P2") in shared and ("t:A1", "t:C2") not in shared
    dis = {tuple(x["claims"]) for x in by_check(f, "contested_flag_disagrees")}
    assert ("t:P1", "t:P2") in dis and ("t:A1", "t:C1") in dis
    # identical-name and shared-evidence pairs reach the cross-claim check even with a zero-size cut
    sent = {(p["a"], p["b"]) for t in mc.cross_tasks(load_spec(spec_dir, "t"), pairs, 0, 0) for p in t["pairs"]}
    assert sent == {("t:A1", "t:C1"), ("t:P1", "t:P2"), ("t:A1", "t:P1"), ("t:A1", "t:P2")}   # A1 shares 2 facts with P1, P2


def test_trigger_groups(world):
    _, _, spec_dir = world
    groups, f, meta = trigger_groups(load_spec(spec_dir, "t"))
    ident = [v for k, v in groups.items() if k.startswith("identical_")]
    assert sorted(map(sorted, ident)) == [["t:A2", "t:C2"], ["t:P1", "t:P2"]]
    assert groups["standing_lexical"] == ["t:A1"]              # "Any ..."; "All kitchen work" is not in the rule
    assert "not to predict" in meta["standing_note"]


def test_missing_active_when_is_caught(tmp_path):
    d = tmp_path / "spec"
    make_spec(d, {"anchors": [claim("A1", "X", [LIVE], active=""), claim("A2", "Y", [LIVE2])]})
    _, f, _ = trigger_groups(load_spec(d, "t"))
    assert [x["claims"] for x in by_check(f, "active_when_missing")] == [["t:A1"]]


def test_existing_machinery_runs_readonly_and_catches_supersession(tmp_path):
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db")
    d = tmp_path / "spec"
    make_spec(d, {"anchors": [claim("A1", "X", [LIVE, SUPER]), claim("A2", "Y", [LIVE, LIVE2])]})
    res, f = check_existing(load_spec(d, "t"), open_corpus(corpus, tmp_path / "out"))
    assert [x["claims"] for x in by_check(f, "cited_facts_supersede_each_other")] == [["t:A1"]]
    assert res["t:A2"]["supersession"]["result"] == 1


# ---------------------------------------------------------------- read-only guarantees
def test_connection_refuses_writes(world):
    tmp, corpus, _ = world
    c = open_corpus(corpus, tmp / "out")
    with pytest.raises(sqlite3.OperationalError):
        c.c.execute("INSERT INTO conversations VALUES ('x','y','z')")


@pytest.mark.parametrize("pending", [False, True])
def test_full_run_leaves_wal_corpus_byte_identical(tmp_path, pending):
    corpus = tmp_path / "corpus"
    db = corpus / "data" / "database" / "memory.db"
    make_db(db, wal=True, pending_wal=pending)
    wal = Path(str(db) + "-wal")
    assert (wal.exists() and wal.stat().st_size > 0) == pending
    spec_dir = tmp_path / "spec"
    default_spec(spec_dir)
    before = dir_state(corpus)
    out = tmp_path / "out"
    rc = vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(out)], rater=None)
    assert rc == 0
    assert dir_state(corpus) == before
    rep = json.loads((out / "t.verification.json").read_text(encoding="utf-8"))
    mode = rep["meta"]["corpus"]["open_mode"]
    assert mode.startswith("snapshot") if pending else mode.startswith("immutable")
    assert not (out / "_snapshot").exists()                     # snapshot removed after the run
    if pending:  # the snapshot saw the row that lives only in the wal
        conn, info = open_readonly(db, tmp_path / "snap2")
        assert conn.execute("SELECT count(*) FROM messages WHERE id='m9'").fetchone()[0] == 1
        conn.close()


def test_out_guard(world):
    tmp, corpus, spec_dir = world
    base = ["--label", "t", "--corpus", str(corpus)]
    for bad in (corpus / "data" / "reports", spec_dir / "out", tmp):   # inside corpus, inside spec, above both
        with pytest.raises(ValueError):
            vrun.main([str(spec_dir), *base, "--out", str(bad)])
    served = tmp / "memory_system" / "data"
    (served / "identity_layers").mkdir(parents=True)
    with pytest.raises(ValueError):
        vrun.main([str(spec_dir), *base, "--out", str(served / "verify")])
    assert vrun.main([str(spec_dir), *base, "--out", str(tmp / "reports")]) == 0   # clean control


# ---------------------------------------------------------------- raters
def test_child_env_strips_credentials_and_disables_injection():
    e = child_env({"ANTHROPIC_API_KEY": "sk-x", "ANTHROPIC_AUTH_TOKEN": "t", "PATH": "p", "BASELAYER_SPEC_INJECT": "1"})
    assert "ANTHROPIC_API_KEY" not in e and "ANTHROPIC_AUTH_TOKEN" not in e
    assert e["BASELAYER_SPEC_INJECT"] == "0" and e["PATH"] == "p"
    assert json.loads(CLI_SETTINGS)["disableAllHooks"] is True


def test_rater_cwd_must_be_outside_projects(tmp_path):
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "CLAUDE.md").write_text("x")
    with pytest.raises(ValueError):
        check_rater_cwd(proj / "sub", [])
    clean = tmp_path / "neutral"
    clean.mkdir()
    with pytest.raises(ValueError):
        check_rater_cwd(clean, [clean / "corpus"])                # cwd above a protected path
    check_rater_cwd(clean, [tmp_path / "elsewhere"])              # clean control


def test_cli_rater_command_and_provenance(tmp_path):
    cwd = tmp_path / "neutral"
    cwd.mkdir()
    r = ClaudeCliRater("sonnet", cwd, tmp_path / "work", [tmp_path / "corpus"], binary="claude")
    cmd = r.command()
    for flag in ("-p", "--strict-mcp-config", "--settings", "--allowedTools"):
        assert flag in cmd
    assert json.loads((tmp_path / "work" / "empty_mcp.json").read_text()) == {"mcpServers": {}}
    pv = r.provenance()
    assert pv["blind"] is False and "CLAUDE.md" in pv["blind_channel"] and pv["probe"] == "not_run"


def test_probe_sets_blind_only_when_clean(tmp_path):
    cwd = tmp_path / "n"
    cwd.mkdir()
    r = ClaudeCliRater("sonnet", cwd, tmp_path / "w", [], binary="claude")
    r.complete = lambda p: __import__("baselayer.verification.raters", fromlist=["Reply"]).Reply(text='{"people_named": ["Jane Roe"]}')
    run_probe(r, ["Jane Roe"], tmp_path / "probe.json")
    assert r.provenance()["blind"] is False and (tmp_path / "probe.json").exists()
    r.complete = lambda p: __import__("baselayer.verification.raters", fromlist=["Reply"]).Reply(text='{"people_named": []}')
    run_probe(r, ["Jane Roe"], tmp_path / "probe.json")
    assert r.provenance()["blind"] is True
    assert "Jane Roe" not in (tmp_path / "probe.json").read_text().split('"answer"')[0]


# ---------------------------------------------------------------- dry run and pricing
def test_dry_run_calls_no_model_and_prices(world, capsys):
    tmp, corpus, spec_dir = world
    fake = FakeRater(lambda p: "{}")
    rc = vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(tmp / "o")], rater=fake)
    assert rc == 0 and fake.prompts == []
    assert "estimate" in capsys.readouterr().out
    rep = json.loads((tmp / "o" / "t.verification.json").read_text(encoding="utf-8"))
    assert rep["meta"]["model"]["status"] == "dry_run"
    assert rep["meta"]["model"]["tasks"]["support"] == 5          # A2 has no live fact, so no support call
    assert (tmp / "o" / "t.verification.md").exists()
    for f in rep["findings"]:
        assert all(re.fullmatch(r"t:[ACPM]\d+", q) for q in f["claims"])


def test_estimate_matches_prototype_rate():
    tasks = {"support": [{"prompt": "x" * 17500}] * 100}
    e = estimate(tasks, "sonnet", "cli")
    per_call = e["phase1_usd"] / 100
    assert 0.06 < per_call < 0.10       # a prototype run measured about $0.079 per sonnet call
    assert "counterfactual" in e["billing"]
    assert "error" in estimate(tasks, "no-such-model", "cli")


def test_api_rater_requires_a_spend_cap(world):
    tmp, corpus, spec_dir = world
    base = [str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(tmp / "o"), "--run-model", "--rater", "api"]
    with pytest.raises(SystemExit):
        vrun.main(base + ["--model", "claude-sonnet-5"])
    with pytest.raises(SystemExit):
        vrun.main(base + ["--model", "claude-sonnet-5", "--confirm-api-spend", "0.0001"])
    with pytest.raises(SystemExit):
        vrun.main(base + ["--confirm-api-spend", "100"])            # no explicit model
    with pytest.raises(SystemExit):
        vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(tmp / "o"), "--run-model"])  # cli needs cwd


# ---------------------------------------------------------------- model-judged checks (FakeRater)
class ScriptedJudge:
    """Answers every task kind from the ids in the prompt, with planted verdicts."""

    def __init__(self, support=None, voice=None, cross=None, adjudicate=None, fidelity=None, break_kind=None):
        self.support = support or {}
        self.voice = voice or {}
        self.cross = cross or {}
        self.adjudicate = adjudicate or {}
        self.fidelity = fidelity or {}
        self.break_kind = break_kind

    def __call__(self, prompt: str) -> str:
        if prompt.startswith("You are auditing one claim"):
            q = re.search(r"CLAIM (\S+) ", prompt).group(1)
            ids = re.findall(r"^(F-[0-9a-f]{8}):", prompt, re.M)
            if self.break_kind == "support":
                ids = ids[:-1]
            plan = self.support.get(q, {})
            facts = [{"id": i, "support": plan.get(i, "supports"), "side": plan.get(("side", i), "1" if k == 0 else "2")}
                     for k, i in enumerate(ids)]
            return json.dumps({"side_1": "a", "side_2": "b", "facts": facts, "strongest": ids[0] if ids else None, "weakest": None})
        if prompt.startswith("Each item below is a statement"):
            items = re.findall(r"ITEM (V\d+)\nStatement: (.*)\n", prompt)
            out = []
            for vid, text in items:
                v, turn = self.voice.get(text, ("own_words", None))
                out.append({"id": vid, "voice": v, "turn": turn})
            return json.dumps({"items": out})
        if prompt.startswith("Each item below is a fact"):
            items = re.findall(r"ITEM (D\d+)\nFact: (.*)\n", prompt)
            return json.dumps({"items": [{"id": d, "label": self.fidelity.get(t, "own_words"), "reason": "r"} for d, t in items]})
        if prompt.startswith("Below are claims"):
            pairs = re.findall(r"^(Q\d+): (\S+) vs (\S+)$", prompt, re.M)
            return json.dumps({"items": [{"id": q, "relation": self.cross.get((a, b), "compatible"), "condition": "c"} for q, a, b in pairs]})
        if prompt.startswith("You are adjudicating"):
            items = re.findall(r"ITEM (K\d+) \((\w+);", prompt)
            return json.dumps({"items": [{"id": k, "verdict": self.adjudicate.get(kind, "no_conflict"), "condition": None,
                                          "which_fact": None, "own_words_support": {}, "reason": "r"} for k, kind in items]})
        raise AssertionError("unknown prompt: " + prompt[:80])


def run_fake(tmp, corpus, spec_dir, judge, extra=(), out_name="o"):
    fake = FakeRater(judge)
    out = tmp / out_name
    rc = vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(out), "--run-model", "--workers", "1", *extra], rater=fake)
    return rc, json.loads((out / "t.verification.json").read_text(encoding="utf-8")), fake


def test_model_clean_control_raises_no_model_findings(world):
    tmp, corpus, spec_dir = world
    rc, rep, fake = run_fake(tmp, corpus, spec_dir, ScriptedJudge())
    assert rc == 0 and fake.prompts
    model = [f for f in rep["findings"] if f["kind"] == "model" and f["severity"] != "info"]
    assert model == []
    assert rep["meta"]["model"]["status"] == "ran" and rep["meta"]["model"]["rater"]["rater"] == "fake"


def test_weak_support_contradiction_and_contested_side_are_caught(world):
    tmp, corpus, spec_dir = world
    l1, l2 = "F-" + LIVE[:8], "F-" + LIVE2[:8]
    judge = ScriptedJudge(support={"t:P1": {l1: "unrelated", l2: "unrelated"},
                                   "t:A1": {l2: "contradicts", ("side", l1): "1", ("side", l2): "1"}})
    rc, rep, _ = run_fake(tmp, corpus, spec_dir, judge)
    weak = by_check(rep["findings"], "weak_support")
    assert [f["claims"] for f in weak] == [["t:P1"]]
    assert set(weak[0]["fact_ids"]) == {l1, l2}
    assert by_check(rep["findings"], "cited_fact_contradicts_claim")[0]["fact_ids"] == [l2]
    assert ["t:A1"] in [f["claims"] for f in by_check(rep["findings"], "contested_unsupported")]
    adj = [f for f in rep["findings"] if f["check"].startswith("contradiction_")]
    assert adj and all(f["conversation_ids"] and f["turn_ids"] for f in adj)  # every read names its source context
    a1 = [f for f in adj if f["claims"] == ["t:A1"]]
    assert a1 and set(a1[0]["turn_ids"]) <= {"m0", "m1", "m2"}           # message ids from conv-u, not invented


def test_voice_check_flags_claim_not_his_and_maps_turns(tmp_path):
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db")
    d = tmp_path / "spec"
    # three live facts from the dialogue conversation; the judge calls two of them assistant
    make_spec(d, {"anchors": [claim("A1", "X", [LIVE, LIVE2, LIVE4]), claim("A2", "Y", [LIVE, LIVE2, LIVE3])]})
    judge = ScriptedJudge(voice={"user waters the tomatoes before sunrise": ("assistant", 1),
                                 "user records every missed watering": ("assistant", 7)})
    rc, rep, _ = run_fake(tmp_path, corpus, d, judge, ["--checks", "voice"])
    nh = by_check(rep["findings"], "claim_not_his")
    # A1: 1 own of 3 located -> not_his. A2: LIVE3 is a document import, unsettled, so only 2 located -> no verdict
    assert [f["claims"] for f in nh] == [["t:A1"]]
    assert set(nh[0]["fact_ids"]) == {"F-" + LIVE[:8], "F-" + LIVE2[:8]} and nh[0]["turn_ids"] == ["m1"]
    assert rep["model_results"]["voice"]["t:A2"]["unsettled"] == 1
    rows = {r["id"]: r for r in rep["claims"]["t:A1"]["facts"]}
    assert rows["F-" + LIVE[:8]]["turn_ids"] == ["m1"]            # rater turn 1 -> real message id
    assert rows["F-" + LIVE2[:8]]["turn_ids"] == []               # turn 7 was never shown: not kept


def test_voice_clean_control(tmp_path):
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db")
    d = tmp_path / "spec"
    make_spec(d, {"anchors": [claim("A1", "X", [LIVE, LIVE2]), claim("A2", "Y", [LIVE, LIVE2, LIVE3])]})
    rc, rep, _ = run_fake(tmp_path, corpus, d, ScriptedJudge(), ["--checks", "voice"])
    assert not by_check(rep["findings"], "claim_not_his")


def test_cross_claim_contradiction_is_caught_and_adjudicated(world):
    tmp, corpus, spec_dir = world
    judge = ScriptedJudge(cross={("t:A1", "t:C1"): "contradicts"}, adjudicate={"cross_claim": "misattribution"})
    rc, rep, _ = run_fake(tmp, corpus, spec_dir, judge)
    assert [f["claims"] for f in by_check(rep["findings"], "claims_contradict")] == [["t:A1", "t:C1"]]
    mis = by_check(rep["findings"], "contradiction_misattribution")
    assert [f["claims"] for f in mis] == [["t:A1", "t:C1"]]
    assert mis[0]["fact_ids"] == ["F-" + LIVE[:8], "F-" + LIVE3[:8]]
    assert set(mis[0]["conversation_ids"]) == {"conv-u", "conv-d"}


def test_contested_confirmation(world):
    tmp, corpus, spec_dir = world
    l1, l2 = "F-" + LIVE[:8], "F-" + LIVE2[:8]
    judge = ScriptedJudge(support={"t:A1": {("side", l2): "2"}}, adjudicate={"within_contested": "context_split"})
    rc, rep, _ = run_fake(tmp, corpus, spec_dir, judge)
    assert rep["model_results"]["contested_confirmation"]["t:A1"]["status"] == "confirmed"
    judge = ScriptedJudge(support={"t:A1": {("side", l2): "2"}}, adjudicate={"within_contested": "no_conflict"})
    rc, rep, _ = run_fake(tmp, corpus, spec_dir, judge, out_name="o2")
    assert rep["model_results"]["contested_confirmation"]["t:A1"]["status"] == "unconfirmed"


def test_fidelity_check_in_turn_contract_mode(tmp_path):
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db", turn_contract=True)
    d = tmp_path / "spec"
    make_spec(d, {"anchors": [claim("A1", "X", [LIVE, LIVE2]), claim("A2", "Y", [LIVE])]})
    judge = ScriptedJudge(fidelity={"user records every missed watering": "overreach"})
    rc, rep, _ = run_fake(tmp_path, corpus, d, judge, ["--checks", "fidelity"])
    ff = by_check(rep["findings"], "fidelity_failure")
    assert [f["claims"] for f in ff] == [["t:A1"]]
    assert ff[0]["fact_ids"] == ["F-" + LIVE2[:8]] and ff[0]["turn_ids"] == ["conv-u:2"]
    assert rep["model_results"]["fidelity"]["t:A1"]["strict"] == 0.5
    assert rep["model_results"]["fidelity"]["t:A2"]["lenient"] == 1.0


def test_malformed_reply_is_a_failed_task_not_a_result(world):
    tmp, corpus, spec_dir = world
    rc, rep, fake = run_fake(tmp, corpus, spec_dir, ScriptedJudge(break_kind="support"), ["--checks", "support"])
    assert rc == 2
    assert rep["meta"]["model"]["failed_tasks"]
    assert rep["model_results"]["support"] == {}                  # nothing partial was interpreted
    assert len(fake.prompts) == 5 * 3                              # 5 support tasks, 3 attempts each


def test_validate_rejects_bad_enum_and_ids():
    assert mc.validate("cross", {"items": [{"id": "Q1", "relation": "maybe"}]}, ["Q1"]).startswith("bad")
    assert mc.validate("cross", {"items": [{"id": "Q2", "relation": "duplicate"}]}, ["Q1"]).startswith("id_mismatch")
    assert mc.validate("cross", {"items": [{"id": "Q1", "relation": "duplicate"}]}, ["Q1"]) is None


def test_raw_replies_are_reused_only_for_identical_prompt_and_rater(world):
    tmp, corpus, spec_dir = world
    run_fake(tmp, corpus, spec_dir, ScriptedJudge(), ["--checks", "support"])

    def boom(prompt):
        raise AssertionError("should have been answered from the stored raw reply")
    rc, rep, fake = run_fake(tmp, corpus, spec_dir, boom, ["--checks", "support"])
    assert rc == 0 and fake.prompts == []
    # change one claim's statement: exactly that task's prompt changes and it alone is re-asked
    d = json.loads((spec_dir / "core.json").read_text(encoding="utf-8"))
    d["claims"][0]["statement"] = "A different statement."
    (spec_dir / "core.json").write_text(json.dumps(d), encoding="utf-8")
    rc, rep, fake = run_fake(tmp, corpus, spec_dir, ScriptedJudge(), ["--checks", "support"])
    assert len(fake.prompts) == 1 and "CLAIM t:C1 " in fake.prompts[0]


def test_api_rater_reports_cost_from_usage(monkeypatch):
    import sys
    import types
    from baselayer.verification import raters

    class Msgs:
        def create(self, **kw):
            blk = types.SimpleNamespace(type="text", text='{"items": []}')
            return types.SimpleNamespace(content=[blk], model=kw["model"], stop_reason="end_turn",
                                         usage=types.SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000))
    fake_mod = types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=Msgs()))
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    r = raters.ApiRater("claude-sonnet-5").complete("x")
    assert r.cost_usd == pytest.approx(2.0 + 1.0)          # $2/M in, $10/M out at the dated table
    assert raters.ApiRater("claude-sonnet-5").provenance()["bills_api"] is True


def test_served_database_is_always_snapshotted(tmp_path, monkeypatch):
    from baselayer import config
    data = tmp_path / "srv" / "data"
    db = data / "database" / "memory.db"
    make_db(db)
    spec_dir = tmp_path / "spec"
    default_spec(spec_dir)
    before = dir_state(data)
    args = [str(spec_dir), "--label", "t", "--corpus", str(db)]
    assert vrun.main(args + ["--out", str(tmp_path / "o1")]) == 0          # control: not served, not forced
    rep = json.loads((tmp_path / "o1" / "t.verification.json").read_text(encoding="utf-8"))
    assert rep["meta"]["corpus"]["open_mode"].startswith("immutable")
    monkeypatch.setattr(config, "DATABASE_FILE", db)
    assert vrun.main(args + ["--out", str(tmp_path / "o2")]) == 0
    rep = json.loads((tmp_path / "o2" / "t.verification.json").read_text(encoding="utf-8"))
    assert rep["meta"]["corpus"]["open_mode"].startswith("snapshot copy under --out (forced")
    assert dir_state(data) == before


def test_corpus_change_during_run_is_reported(world, monkeypatch):
    tmp, corpus, spec_dir = world
    sigs = iter([("before",), ("after",)])
    monkeypatch.setattr(vrun, "_file_sig", lambda db: next(sigs))
    vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(tmp / "o")])
    rep = json.loads((tmp / "o" / "t.verification.json").read_text(encoding="utf-8"))
    assert by_check(rep["findings"], "corpus_changed_during_run")


# ---------------------------------------------------------------- mode on the REAL schema (init_database)
G_OK = "9a9a0001-0000-0000-0000-000000000001"      # gated, both spans own voice
G_MIX = "9b9b0001-0000-0000-0000-000000000001"     # gated, second span is the assistant's
LEGACY = "9c9c0001-0000-0000-0000-000000000001"    # legacy fact: columns present, version NULL


def real_schema_db(path: Path, gated: bool = True):
    """A database created by init_database, so every turn-contract column exists
    (init_database adds them to every database, legacy ones included). Turns go
    through the real turn table; facts use the §4a names."""
    from baselayer.init_database import init_database
    init_database(path)
    c = sqlite3.connect(str(path))
    c.execute("INSERT INTO conversations (id, title, source, message_count) VALUES ('cv', 'garden', 'chatgpt', 3)")
    for i, (role, text) in enumerate([("user", "I water the tomatoes before sunrise."),
                                      ("assistant", "Mulch solves most problems."),
                                      ("user", "I log every missed watering.")]):
        c.execute("INSERT INTO messages (id, conversation_id, role, content_text, content_type, sequence_order) "
                  "VALUES (?,?,?,?,?,?)", (f"cv-m{i}", "cv", role, text, "text", i))
    c.executemany("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, text, detector, "
                  "turn_contract_version) VALUES (?,?,?,?,?,?,?,?)", [
                      ("cv:0", "cv", 0, "subject", "own_typed", "I water the tomatoes before sunrise.", None, "turn-contract/1"),
                      ("cv:1", "cv", 1, "assistant", "assistant", "Mulch solves most problems.", "source:role=assistant", "turn-contract/1"),
                      ("cv:2", "cv", 2, "subject", "own_typed", "I log every missed watering.", None, "turn-contract/1")])
    def fact(fid, text, spans, version):
        c.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id, source_turn_id, "
                  "evidence_spans, turn_contract_version) VALUES (?,?,?,?,?,?,?)",
                  (fid, text, "habit", "cv", spans[0]["turn_id"] if spans else None,
                   json.dumps(spans) if spans else None, version))
    if gated:
        fact(G_OK, "user keeps a careful watering routine",
             [{"turn_id": "cv:0", "span": "water the tomatoes before sunrise"},
              {"turn_id": "cv:2", "span": "log every missed watering"}], "turn-contract/1")
        fact(G_MIX, "user relies on mulch and early watering",
             [{"turn_id": "cv:0", "span": "before sunrise"},
              {"turn_id": "cv:1", "span": "Mulch solves most problems"}], "turn-contract/1")
    else:
        fact(LEGACY, "user waters before sunrise", [], None)
    c.commit()
    c.close()


def test_every_span_of_a_gated_fact_is_regated(tmp_path):
    """A gated fact stores a LIST of spans (§4a evidence_spans). Every span is
    re-gated, not only the first: a fact whose second span is the assistant's
    fails, and its finding names both turns."""
    corpus = tmp_path / "corpus"
    real_schema_db(corpus / "data" / "database" / "memory.db")
    spec_dir = tmp_path / "spec"
    make_spec(spec_dir, {"anchors": [claim("A1", "X", [G_OK, G_MIX])]})
    c = open_corpus(corpus, tmp_path / "out")
    assert c.turn_columns and c.turn_table == "turns"
    prof, f = check_facts(load_spec(spec_dir, "t"), c)
    rows = {r["id"]: r for r in prof["t:A1"]["facts"]}
    assert rows["F-" + G_OK[:8]]["voice_mode"] == "turn_contract"
    assert rows["F-" + G_OK[:8]]["turn_ids"] == ["cv:0", "cv:2"]
    bad = {x["fact_ids"][0]: x for x in by_check(f, "turn_gate_failed")}
    assert set(bad) == {"F-" + G_MIX[:8]}
    assert bad["F-" + G_MIX[:8]]["reasons"] == ["not_own_voice"]
    assert bad["F-" + G_MIX[:8]]["turn_ids"] == ["cv:0", "cv:1"]


def test_old_path_db_with_the_columns_but_null_versions_runs_in_fallback(tmp_path):
    """init_database now adds the turn-contract columns to EVERY database, so
    their presence says nothing. A fact is gated iff its turn_contract_version is
    NOT NULL; a legacy fact on such a database is verified in fallback mode, and
    the report says which mode ran."""
    corpus = tmp_path / "corpus"
    real_schema_db(corpus / "data" / "database" / "memory.db", gated=False)
    spec_dir = tmp_path / "spec"
    make_spec(spec_dir, {"anchors": [claim("A1", "X", [LEGACY])]})
    c = open_corpus(corpus, tmp_path / "out")
    prof, f = check_facts(load_spec(spec_dir, "t"), c)
    row = prof["t:A1"]["facts"][0]
    assert row["voice_mode"] == "conversation_only" and row["voice"] == "unresolved_turn_level"
    assert row["turn_ids"] == []
    assert by_check(f, "turn_gate_failed") == []
    rc, rep, _ = run_fake(tmp_path, corpus, spec_dir, ScriptedJudge(), ["--checks", "fidelity"])
    assert rep["meta"]["voice_mode"] == "fallback"
    assert rep["meta"]["voice_modes"] == {"conversation_only": 1}
    assert rep["model_results"].get("fidelity", {}) == {}


def test_mixed_corpus_reports_mixed_mode(tmp_path):
    corpus = tmp_path / "corpus"
    real_schema_db(corpus / "data" / "database" / "memory.db")
    c = sqlite3.connect(str(corpus / "data" / "database" / "memory.db"))
    c.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id) "
              "VALUES (?, 'user waters before sunrise', 'habit', 'cv')", (LEGACY,))
    c.commit()
    c.close()
    spec_dir = tmp_path / "spec"
    make_spec(spec_dir, {"anchors": [claim("A1", "X", [G_OK, LEGACY])]})
    rc, rep, _ = run_fake(tmp_path, corpus, spec_dir, ScriptedJudge(), ["--checks", "support"])
    assert rep["meta"]["voice_mode"] == "mixed"
    assert rep["meta"]["voice_modes"] == {"turn_contract": 1, "conversation_only": 1}


def test_report_code_path_is_repo_relative():
    """The report's own stamp follows contract §7: code_path repo-relative, never absolute
    (an absolute path writes the operator's home directory into every report)."""
    import re
    from baselayer.verification import run as vrun
    p = vrun._git_stamp()["code_path"]
    assert p == "src/baselayer/verification/run.py"
    assert not re.match(r"^[A-Za-z]:|^/", p) and "\\" not in p
