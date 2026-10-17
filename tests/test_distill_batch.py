"""The batch leaf path (distill_batch.py). No API calls: a scripted fake client stands in for
both the Message Batches API and the sequential Messages API used for repairs.

What it must do, and what each test pins:
- ONE submission carries every layer's leaves, so the three layers run concurrently;
- custom_ids are within the API's allowed shape;
- leaves go through the SAME validation and stripping as the sequential path, a result that
  fails to parse or errored is repaired sequentially (never stored as an empty leaf), and the
  repair is under the spend ceiling;
- trees are the sequential path's trees apart from path-identifying stamp fields and cost;
- batch tokens are priced at the batch discount, half the sequential cost;
- the batch id is written to a state file before waiting, and --resume never resubmits;
- record-only exclusion, the planted refusal and the subject filter apply, before any submit.
"""
import json
import re
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import distill
from baselayer.distillation import distill_batch as db_
from baselayer.distillation import spend
from baselayer.turn_contract_fixtures import PLANTED_PREFIX
from tests.test_artifact_stamps import (FACTS, V, DistillClient, _make_db, _Stream,  # noqa: F401
                                        no_network)


def _node_for(prompt, extra_theme_ids=()):
    body = prompt.split("CHUNK:", 1)[1]
    ids = re.findall(r"^\[([0-9a-f]{8})\] ", body, re.M)
    return {"themes": [{"statement": "a theme", "fact_ids": ids + list(extra_theme_ids)}],
            "singularities": [], "contradictions": [],
            "dispositions": {i: "theme" for i in ids}}


class FakeBatches:
    created = []
    script = {}          # custom_id -> "errored" | "garbage" | "fabricate"
    retrieves = 0

    def __init__(self, outer):
        self.outer = outer

    def create(self, requests):
        FakeBatches.created.append(list(requests))
        self._reqs = {r["custom_id"]: r for r in requests}
        FakeBatches._last = self._reqs
        return NS(id="msgbatch_test_%d" % len(FakeBatches.created))

    def retrieve(self, bid):
        FakeBatches.retrieves += 1
        return NS(id=bid, processing_status="ended",
                  request_counts=NS(processing=0, succeeded=len(FakeBatches._last), errored=0,
                                    canceled=0, expired=0))

    def results(self, bid):
        for cid, r in FakeBatches._last.items():
            kind = FakeBatches.script.get(cid)
            if kind == "errored":
                yield NS(custom_id=cid, result=NS(type="errored"))
                continue
            prompt = r["params"]["messages"][0]["content"]
            if kind == "garbage":
                text = "not json at all"
            elif kind == "fabricate":
                text = json.dumps(_node_for(prompt, extra_theme_ids=["deadbeef"]))
            else:
                text = json.dumps(_node_for(prompt))
            msg = NS(content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
                     usage=NS(input_tokens=10, output_tokens=5), stop_reason="end_turn")
            yield NS(custom_id=cid, result=NS(type="succeeded", message=msg))


class BatchClient(DistillClient):
    def __init__(self, *a, **k):
        super().__init__()
        self.messages = self
        self.batches = FakeBatches(self)

    def with_options(self, **kw):
        BatchClient.options = kw
        return self


@pytest.fixture
def batch_env(no_network, monkeypatch):
    FakeBatches.created, FakeBatches.script, FakeBatches.retrieves = [], {}, 0
    monkeypatch.setattr("anthropic.Anthropic", BatchClient)
    return monkeypatch


def _run(monkeypatch, db, outdir, *extra, layers="anchors,core,predictions"):
    monkeypatch.setattr(sys, "argv", ["distill_batch.py", "--db", str(db), "--outdir",
                                      str(outdir), "--model", "claude-haiku-4-5",
                                      "--max-facts", "2", "--layers", layers,
                                      "--partitions", "predicate", "--poll", "0", *extra])
    return db_.main()


def _tree(outdir, layer):
    return json.load(open(outdir / ("%s_predicate_0.json" % layer), encoding="utf-8"))


def test_one_submission_carries_all_three_layers(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    _run(batch_env, db, tmp_path / "out")
    assert len(FakeBatches.created) == 1
    cids = [r["custom_id"] for r in FakeBatches.created[0]]
    assert len(cids) == 6                                   # 3 layers x 2 chunks
    assert {c.split("-")[1] for c in cids} == {"anchors", "core", "predictions"}
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", c) for c in cids)
    assert BatchClient.options.get("max_retries") == 0      # a retried POST can bill twice
    for lay in ("anchors", "core", "predictions"):
        assert _tree(tmp_path / "out", lay)["stamp"]["layer"] == lay


def test_batch_tree_equals_sequential_tree_apart_from_path_and_cost(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    _run(batch_env, db, tmp_path / "out", layers="anchors")
    bt = _tree(tmp_path / "out", "anchors")
    batch_env.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out",
                                    str(tmp_path / "seq.json"), "--model", "claude-haiku-4-5",
                                    "--max-facts", "2", "--layer", "anchors"])
    distill.main()
    st = json.load(open(tmp_path / "seq.json", encoding="utf-8"))
    strip = lambda leaves: [{k: v for k, v in d.items() if k != "_stamp"} for d in leaves]
    assert strip(bt["leaves"]) == strip(st["leaves"])
    assert bt["root"] == st["root"]
    path_fields = {"leaf_path", "batch_id", "generated_utc", "spend_estimate_usd",
                   "spend_estimate_worst_usd", "spend_ceiling_usd", "spend_measured_usd",
                   "run_id", "code_sha", "git_commit", "batch_repairs",
                   "batch_discount"}
    diff = {k for k in set(bt["stamp"]) | set(st["stamp"])
            if bt["stamp"].get(k) != st["stamp"].get(k)}
    assert diff <= path_fields, diff - path_fields
    assert bt["stamp"]["leaf_path"] == "batch" and st["stamp"].get("leaf_path") == "sequential"
    for lb, ls in zip(bt["leaves"], st["leaves"]):
        assert lb["_stamp"]["input_hash"] == ls["_stamp"]["input_hash"]
        assert lb["_stamp"]["prompt_hash"] == ls["_stamp"]["prompt_hash"]
        assert lb["_stamp"]["batch_id"] == "msgbatch_test_1"


def test_batch_tokens_cost_half_of_sequential(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    _run(batch_env, db, tmp_path / "out", layers="anchors")
    u = _tree(tmp_path / "out", "anchors")["usage"]
    assert (u["batch_in"], u["batch_out"], u["in"], u["out"]) == (20, 10, 0, 0)
    r = spend.resolve_rates("claude-haiku-4-5", confirmed=spend.RATES_AS_OF)
    assert u["cost_usd"] == pytest.approx(0.5 * spend.cost_usd(r, 20, 10))


def test_fabricated_ids_go_through_the_sequential_validator(batch_env, tmp_path):
    """A batch leaf citing an id outside its chunk is a schema violation, exactly as on the
    sequential path: one schema-repair call is made, and no fabricated id reaches the tree."""
    db = _make_db(tmp_path / "c", FACTS)
    FakeBatches.script = {"L1-anchors-predicate-0-0000": "fabricate"}
    _run(batch_env, db, tmp_path / "out", layers="anchors")
    t = _tree(tmp_path / "out", "anchors")
    ids = {f for d in t["leaves"] for th in d["themes"] for f in th["fact_ids"]}
    assert "deadbeef" not in ids
    assert len(DistillClient.calls) == 1
    assert "violated the schema" in DistillClient.calls[0]["messages"][0]["content"]


def test_errored_and_unparseable_results_are_repaired_sequentially(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    FakeBatches.script = {"L1-anchors-predicate-0-0000": "errored",
                          "L1-anchors-predicate-0-0001": "garbage"}
    _run(batch_env, db, tmp_path / "out", layers="anchors")
    t = _tree(tmp_path / "out", "anchors")
    assert not any(d.get("_parse_failed") for d in t["leaves"])
    assert all(d["dispositions"] for d in t["leaves"])
    assert len(DistillClient.calls) == 2                    # one fresh call, one repair
    assert t["usage"]["in"] > 0                             # sequential tokens at full rate
    assert t["stamp"]["batch_repairs"] == {"errored": 1, "unparseable": 1}


def test_repairs_are_under_the_spend_ceiling(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    FakeBatches.script = {"L1-anchors-predicate-0-0000": "errored"}
    # Estimate at the batch rate for 2 leaves of Haiku is ~$0.043; one sequential repair's
    # worst case (16,000 output tokens at $5/MTok) is $0.08, so a $0.05 ceiling refuses it.
    with pytest.raises(spend.SpendCeilingExceeded):
        _run(batch_env, db, tmp_path / "out", "--confirm-spend", "0.05", layers="anchors")
    assert DistillClient.calls == []


def test_state_file_before_wait_and_resume_never_resubmits(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    out = tmp_path / "out"
    _run(batch_env, db, out, layers="anchors")
    state = json.load(open(out / "batch_state.json", encoding="utf-8"))
    assert state["batch_id"] == "msgbatch_test_1" and state["n_requests"] == 2
    with pytest.raises(SystemExit, match="already submitted"):
        _run(batch_env, db, out, layers="anchors")
    assert len(FakeBatches.created) == 1
    _run(batch_env, db, out, "--resume", layers="anchors")
    assert len(FakeBatches.created) == 1


def test_refusals_happen_before_any_submit(batch_env, tmp_path):
    batch_env.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    db = _make_db(tmp_path / "c", FACTS)
    with pytest.raises(SystemExit, match="NO SPEND CEILING"):
        _run(batch_env, db, tmp_path / "o1")
    batch_env.setenv("BASELAYER_SPEND_CEILING_USD", "50")
    root = tmp_path / "p"
    dbp = root / "data" / "database" / "memory.db"
    dbp.parent.mkdir(parents=True)
    c = sqlite3.connect(dbp)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, predicate TEXT, "
              "category TEXT, superseded_by TEXT, created_at REAL, turn_contract_version TEXT, "
              "source_conversation_id TEXT)")
    for i, (fid, text, ver) in enumerate(FACTS):
        c.execute("INSERT INTO memory_facts VALUES (?,?,?,?,NULL,?,?,?)",
                  (fid, text, "p", "c", float(i), ver, (PLANTED_PREFIX + "x") if i == 0 else "r"))
    c.commit()
    c.close()
    with pytest.raises(SystemExit, match="planted"):
        _run(batch_env, dbp, tmp_path / "o2")
    assert FakeBatches.created == []


def test_record_only_and_subject_filters_apply(batch_env, tmp_path):
    from tests.test_record_spans import _distill_db
    _run(batch_env, _distill_db(tmp_path / "c"), tmp_path / "out", layers="anchors")
    st = _tree(tmp_path / "out", "anchors")["stamp"]
    assert st["facts_total"] == 2 and st["record_only_facts_excluded"] == 1


def test_resume_skips_finished_trees_and_does_not_repay_repairs(batch_env, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    out = tmp_path / "out"
    FakeBatches.script = {"L1-anchors-predicate-0-0000": "errored"}
    _run(batch_env, db, out, layers="anchors")
    assert len(DistillClient.calls) == 1
    first = (out / "anchors_predicate_0.json").read_text(encoding="utf-8")
    _run(batch_env, db, out, "--resume", layers="anchors")
    assert len(DistillClient.calls) == 1                 # no repair re-paid
    assert (out / "anchors_predicate_0.json").read_text(encoding="utf-8") == first
