"""The turn-contract pilot helper (baselayer.pilot). No API calls, ever.

`anthropic.Anthropic` is replaced by a constructor that raises for every test, and the run step
is an injected fake that records the ids it was handed. Every corpus lives under tmp_path.
"""
import json
import types
import sqlite3
from datetime import datetime, timezone

import pytest

from baselayer import pilot as P

V = "turn-contract/1"


def _ts(y, m):
    return datetime(y, m, 15, tzinfo=timezone.utc).timestamp()


# (id, source, (year, month), citable?, extracted?)
CONVS = (
    [("cg-%02d" % i, "chatgpt", (2025, 1), True, False) for i in range(6)]
    + [("cg-feb-%02d" % i, "chatgpt", (2025, 2), True, False) for i in range(3)]
    + [("cc-%02d" % i, "claude_code", (2025, 1), True, False) for i in range(2)]
    + [("cc-none", "claude_code", (2025, 1), False, False),      # nothing citable
       ("cg-done", "chatgpt", (2025, 1), True, True)]            # already extracted
)


def _turn_rows(conv, citable):
    own = "own_typed" if citable else "harness_prompt"
    det = None if citable else "source:promptSource=sdk"
    return [(f"{conv}:0", 0, "subject", own, "I want the weekly report sent every Monday "
             "morning before the standup starts.", det),
            (f"{conv}:1", 1, "assistant", "assistant", "Scheduled for Monday mornings.",
             "source:role=assistant")]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    from baselayer.init_database import init_database

    class NoNetwork:
        def __init__(self, *a, **k):
            raise AssertionError("the pilot tests must never build an API client")
    monkeypatch.setattr("anthropic.Anthropic", NoNetwork)
    for var in ("BASELAYER_DYNAMIC_CAP", "BASELAYER_TURN_CONTRACT"):
        monkeypatch.delenv(var, raising=False)
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")

    root = tmp_path / "corpus"
    db = root / "data" / "database" / "memory.db"
    init_database(db)
    # main() points MEMORY_SYSTEM_ROOT at the corpus; registering it here restores it after.
    monkeypatch.setenv("MEMORY_SYSTEM_ROOT", str(root))
    c = sqlite3.connect(db)
    for cid, src, (y, m), cit, done in CONVS:
        c.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                  (cid, "t " + cid, _ts(y, m), _ts(y, m), 2, src))
        for tid, o, sp, vc, text, det in _turn_rows(cid, cit):
            c.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, "
                      "voice_class, text, detector, source, turn_contract_version) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (tid, cid, o, sp, vc, text, det, src, V))
        if done:
            c.execute("INSERT INTO extraction_log VALUES (?, 1, 1.0)", (cid,))
    c.commit()
    c.close()
    ran = []
    return root, ran, (lambda ids: ran.append(list(ids)))


def _run(root, runner, *args):
    return P.main([str(root), *args], runner=runner)


def test_estimate_only_without_confirm_spend(corpus, capsys):
    root, ran, runner = corpus
    with pytest.raises(P.PilotRefused):
        _run(root, runner, "--sample", "4")
    assert ran == []
    out = capsys.readouterr().out
    assert "ESTIMATE $" in out and out.count("ASSUMPTION") == 3
    assert "TO CONFIRM" in out
    rec = json.loads(next((root / "data" / "pilot").glob("pilot_*.json")).read_text())
    assert rec["ran"] is False and "no --confirm-spend" in rec["refused"]
    assert len(rec["conversation_ids"]) == 4


def test_refuses_when_the_estimate_exceeds_the_cap(corpus):
    root, ran, runner = corpus
    with pytest.raises(P.PilotRefused):
        _run(root, runner, "--sample", "4", "--confirm-spend", "0.000001", "--rates-confirmed")
    assert ran == []


def test_default_rates_must_be_confirmed(corpus):
    root, ran, runner = corpus
    with pytest.raises(P.PilotRefused):
        _run(root, runner, "--sample", "4", "--confirm-spend", "100")
    assert ran == []


def test_runs_under_the_cap_with_confirmed_rates(corpus):
    root, ran, runner = corpus
    rec = _run(root, runner, "--sample", "4", "--confirm-spend", "100", "--rates-confirmed")
    assert rec["ran"] is True and ran == [rec["conversation_ids"]]


def test_explicit_rates_need_no_confirmation_flag_and_are_used(corpus):
    root, ran, runner = corpus
    rec = _run(root, runner, "--sample", "4", "--confirm-spend", "100",
               "--input-rate", "2", "--output-rate", "10")
    a = rec["estimate"]["assumptions"]
    assert (a["input_rate_per_mtok"], a["output_rate_per_mtok"]) == (2.0, 10.0)
    assert ran


def test_non_haiku_model_requires_explicit_rates(corpus, monkeypatch):
    import baselayer.config as cfg
    monkeypatch.setattr(cfg, "EXTRACTION_API_MODEL", "claude-sonnet-5")
    root, ran, runner = corpus
    with pytest.raises(P.PilotRefused, match="not Haiku 4.5"):
        _run(root, runner, "--sample", "4", "--confirm-spend", "100", "--rates-confirmed")


def test_sample_is_stratified_citable_unextracted_and_seeded(corpus):
    root, _, _ = corpus
    conn = sqlite3.connect(root / "data" / "database" / "memory.db")
    pool = P.citable_conversations(conn, "planted-")
    ids = {c["id"] for c in pool}
    assert "cc-none" not in ids and "cg-done" not in ids and len(ids) == 11
    s = P.stratified_sample(pool, 5, seed=1)
    strata = {c["stratum"] for c in s}
    assert strata == {("chatgpt", "2025-01"), ("chatgpt", "2025-02"),
                      ("claude_code", "2025-01")}                     # every stratum present
    assert [c["id"] for c in s] == [c["id"] for c in P.stratified_sample(pool, 5, seed=1)]
    for seed in range(10):             # n == strata: exactly one from each, every seed
        got = sorted(c["stratum"] for c in P.stratified_sample(pool, 3, seed=seed))
        assert got == sorted(strata), seed
    assert len(P.stratified_sample(pool, 2, seed=0)) == 2              # fewer than strata
    assert len(P.stratified_sample(pool, 50, seed=0)) == 11            # capped at the pool


def test_estimate_arithmetic_is_the_stated_assumptions():
    m = [{"prompt_chars": 4000, "fact_ceiling": 10, "calls": 1},
         {"prompt_chars": 4001, "fact_ceiling": 5, "calls": 2}]
    e = P.estimate(m, input_rate=1.0, output_rate=5.0, chars_per_token=4.0, tokens_per_fact=180)
    assert e["input_tokens"] == 2001 and e["output_tokens_ceiling"] == 15 * 180
    assert e["usd"] == round(2001 / 1e6 * 1.0 + 2700 / 1e6 * 5.0, 4)


def test_measure_counts_the_prompts_extraction_would_send(corpus):
    import baselayer.extract_facts as ef
    root, _, _ = corpus
    conn = sqlite3.connect(root / "data" / "database" / "memory.db")
    pool = [c for c in P.citable_conversations(conn, "planted-") if c["id"] == "cg-00"]
    m = P.measure(conn, pool)[0]
    from baselayer import turn_contract as tc
    turns = tc.load_turns(conn, "cg-00")
    tok = ef._TURN_MODE_ACTIVE.set(True)
    try:
        plan = ef.turn_extraction_plan(turns, "chatgpt")
        ch = ef.build_turn_chunks(turns, "chatgpt", plan["input_char_budget"])[0]
        expect = (len(ef.json_instruction_for(ef.TURN_EXTRACT_SCHEMA))
                  + len(ef.turn_chunk_prompt(pool[0]["title"], ch, plan, False)))
    finally:
        ef._TURN_MODE_ACTIVE.reset(tok)
    assert m["calls"] == 1 and m["prompt_chars"] == expect
    assert m["fact_ceiling"] == plan["per_chunk_cap"]


def test_refuses_served_data_and_checkouts(tmp_path):
    served = tmp_path / "served"
    (served / "data" / "identity_layers").mkdir(parents=True)
    with pytest.raises(P.PilotRefused, match="identity_layers"):
        P.corpus_db(served)
    co = tmp_path / "checkout"
    (co / "src" / "baselayer").mkdir(parents=True)
    with pytest.raises(P.PilotRefused, match="checkout"):
        P.corpus_db(co)


def test_planted_sessions_join_the_sample_and_are_checked(corpus, tmp_path, monkeypatch):
    import baselayer.import_conversations as IC
    from baselayer import turn_contract_fixtures as F
    root, ran, runner = corpus
    conf = tmp_path / "import_config.json"
    marker = "SYNTHETIC PILOT MARKER 3d7e"      # never the real canary sentence
    conf.write_text(json.dumps({"canary_strings": [marker]}), encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(conf))
    monkeypatch.setattr(IC, "CLAUDE_PROJECTS_DIR", tmp_path / "none")
    manifest = F.write_planted_sessions(tmp_path / "planted", canary=marker)
    assert any(s["flag"] for s in manifest["sessions"].values())
    conn = sqlite3.connect(root / "data" / "database" / "memory.db")
    IC.import_claude_code(conn, set(), session_files=manifest["files"])
    conn.commit()
    conn.close()
    rec = _run(root, runner, "--sample", "3", "--confirm-spend", "100", "--rates-confirmed",
               "--planted-manifest", str(tmp_path / "planted" / F.MANIFEST_NAME))
    planted = [i for i in rec["conversation_ids"] if i.startswith(F.PLANTED_PREFIX)]
    assert len(planted) == len(manifest["sessions"])
    assert len(rec["conversation_ids"]) == 3 + len(planted)
    assert rec["planted_fact_problems"] == []


def test_extractor_selects_exactly_the_given_ids(corpus):
    import baselayer.extract_facts as ef
    root, _, _ = corpus
    conn = sqlite3.connect(root / "data" / "database" / "memory.db")
    got = ef.get_conversations_to_process(conn, conv_ids=["cg-02", "cg-done", "nope", "cc-01"])
    assert [c["id"] for c in got] == ["cg-02", "cc-01"]                # extracted/unknown dropped


def test_default_runner_refuses_a_foreign_database(corpus, tmp_path, monkeypatch):
    """The only path that spends. It must refuse when the extractor resolved another database."""
    import baselayer.extract_facts as ef
    other = tmp_path / "other.db"
    sqlite3.connect(other).close()
    monkeypatch.setattr(ef, "get_db", lambda *a, **k: sqlite3.connect(other))
    called = []
    monkeypatch.setattr(ef, "run_extraction", lambda **kw: called.append(kw))
    root, _, _ = corpus
    with pytest.raises(P.PilotRefused, match="not the pilot database"):
        P._default_runner(["cg-00"], root / "data" / "database" / "memory.db")
    assert called == []


def test_default_runner_extracts_exactly_the_sample_in_turn_mode(corpus, monkeypatch):
    import os
    import baselayer.extract_facts as ef
    root, _, _ = corpus
    db = root / "data" / "database" / "memory.db"
    monkeypatch.setattr(ef, "get_db", lambda *a, **k: sqlite3.connect(db))
    called = []
    monkeypatch.setattr(ef, "run_extraction", lambda **kw: called.append(
        (kw, os.environ.get("BASELAYER_TURN_CONTRACT"))))
    P._default_runner(["cg-00", "cc-01"], db)
    assert called == [({"conv_ids": ["cg-00", "cc-01"]}, "1")]


def test_pilot_reads_back_the_measured_usage_of_its_run(corpus, capsys):
    """The full run is priced from the pilot's MEASURED tokens, not its estimate."""
    import time
    from baselayer import turn_contract as tc
    root, _, _ = corpus

    def runner(ids):
        rec = tc.ExtractionRunRecord("turn", {})
        rec.usage_calls = [tc.usage_entry(types.SimpleNamespace(
            input_tokens=12000, output_tokens=3000, cache_read_input_tokens=0,
            cache_creation_input_tokens=0), batch=False) for _ in ids]
        rec.write(root=root)
    rec = _run(root, runner, "--sample", "2", "--confirm-spend", "100", "--rates-confirmed")
    m = rec["measured"]
    assert m["totals"]["input_tokens"] == 24000 and m["totals"]["output_tokens"] == 6000
    assert m["usd_input_output"] == round(24000 / 1e6 * 1 + 6000 / 1e6 * 5, 4)
    assert "MEASURED cost $" in capsys.readouterr().out


def test_pilot_says_when_nothing_was_measured(corpus, capsys):
    root, _, runner = corpus
    rec = _run(root, runner, "--sample", "2", "--confirm-spend", "100", "--rates-confirmed")
    assert rec["measured"] is None
    assert "spend is unmeasured" in capsys.readouterr().out


def test_pilot_next_steps_say_the_corpus_is_not_for_distillation(corpus, capsys):
    root, _, runner = corpus
    _run(root, runner, "--sample", "2", "--confirm-spend", "100", "--rates-confirmed")
    out = capsys.readouterr().out
    assert "NOT for distillation" in out and "fresh corpus directory" in out
