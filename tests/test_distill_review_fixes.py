"""Review fixes in distillation. No network: fake clients only.

- distill_batch --resume refuses a changed chunking (layers, partitions, seeds, max-facts);
- convergence.py imports without BASELAYER_SRC;
- a non-string or whitespace-only own_words excerpt is stripped, never a crash or a kept excerpt;
- convergence --resume refuses a different --exclude-ids file than the batch was submitted with;
- an unreadable --exclude-ids file (bad JSON, missing, UTF-16) is refused, not a traceback.
"""
import json
import runpy
import sys
from pathlib import Path

import pytest

import baselayer.distillation as pkg
from baselayer.distillation import distill, spend
from tests.test_artifact_stamps import V, DistillClient, _make_db, no_network  # noqa: F401
from tests.test_distill_batch import FakeBatches, BatchClient, batch_env, _run as brun  # noqa: F401
from tests.test_distill_subject import ROWS, _db, _run
from tests.test_distill_subject import _db as subject_db

HERE = Path(pkg.__file__).parent
A = ROWS[0][0]


FIVE = [("%s-0000-4000-8000-00000000000%d" % (c * 8, i), "fact number %d" % i, V)
        for i, c in enumerate("abcde", 1)]


# E_distill-3 ------------------------------------------------------------------------------
@pytest.mark.parametrize("submit,resume", [
    (("--max-facts", "3"), ("--max-facts", "4")),          # 5 facts -> 2 chunks either way
    (("--max-facts", "3"), ("--max-facts", "3", "--partitions", "category")),
])
def test_resume_refuses_a_changed_chunking(batch_env, tmp_path, submit, resume):
    db = _make_db(tmp_path / "c", FIVE)
    out = tmp_path / "out"
    brun(batch_env, db, out, *submit, layers="anchors")
    DistillClient.calls = []
    with pytest.raises(SystemExit, match="Resume with the arguments that submitted it"):
        brun(batch_env, db, out, "--resume", *resume, layers="anchors")
    assert len(FakeBatches.created) == 1 and DistillClient.calls == []


# E_distill-4 ------------------------------------------------------------------------------
def test_convergence_imports_without_baselayer_src(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BASELAYER_SRC", raising=False)
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    db = subject_db(tmp_path / "c")
    monkeypatch.setattr(sys, "argv", ["convergence.py", "--db", str(db), "--out",
                                      str(tmp_path / "out"), "--runs", "1", "--dry-run",
                                      "--max-facts", "10"])
    got = None
    try:
        runpy.run_path(str(HERE / "convergence.py"), run_name="__main__")
    except BaseException as e:          # noqa: BLE001 - the defect is the exception type
        got = e
    assert got is None, repr(got)
    assert "facts=3 " in capsys.readouterr().out


# E_distill-5 ------------------------------------------------------------------------------
SPANS = {"aaaaaaaa": ["I always write the plan first."]}


def _node(ow):
    return {"themes": [], "contradictions": [], "dispositions": {"aaaaaaaa": "singular"},
            "singularities": [{"fact_id": "aaaaaaaa", "verbatim": "v", "own_words": ow,
                               "why": "w"}]}


@pytest.mark.parametrize("ow", [["x"], 7, {"a": 1}])
def test_non_string_own_words_is_stripped_and_counted_not_a_crash(ow):
    d = _node(ow)
    got = None
    try:
        distill.validate(d, ["aaaaaaaa"], SPANS)
    except BaseException as e:          # noqa: BLE001
        got = e
    assert got is None, repr(got)
    assert d["singularities"][0]["own_words"] == ""
    assert d["_stripped"]["own_words"] == 1


def test_whitespace_only_own_words_is_not_kept_as_a_verified_excerpt():
    d = _node(" \t ")
    distill.validate(d, ["aaaaaaaa"], SPANS)
    assert d["singularities"][0]["own_words"] == ""


# G_exclude_ids-2 --------------------------------------------------------------------------
@pytest.mark.parametrize("resume_extra", [(), ("--exclude-ids", "B")])
def test_convergence_resume_refuses_a_different_exclusion(no_network, monkeypatch, tmp_path,
                                                          resume_extra):
    monkeypatch.delenv("BASELAYER_SRC", raising=False)
    FakeBatches.created, FakeBatches.script, FakeBatches.retrieves = [], {}, 0
    monkeypatch.setattr("anthropic.Anthropic", BatchClient)
    db = _db(tmp_path / "c")
    a = tmp_path / "a.json"; a.write_text(json.dumps([A]))
    b = tmp_path / "b.json"; b.write_text(json.dumps([ROWS[1][0]]))
    out = tmp_path / "out"

    def conv(*extra):
        monkeypatch.setattr(sys, "argv", ["convergence.py", "--db", str(db), "--out", str(out),
                                          "--runs", "1", "--max-facts", "10", *extra])
        runpy.run_path(str(HERE / "convergence.py"), run_name="__main__")

    conv("--exclude-ids", str(a))
    bid = json.load(open(out / "batch.json"))["batch_id"]
    extra = [str(b) if x == "B" else x for x in resume_extra]
    with pytest.raises(SystemExit, match="exclude-ids sha256"):
        conv("--resume", bid, *extra)
    conv("--resume", bid, "--exclude-ids", str(a))        # the matching resume still works
    assert len(FakeBatches.created) == 1


# G_exclude_ids-3 --------------------------------------------------------------------------
@pytest.mark.parametrize("case", ["truncated_json", "missing_path", "utf16_bom"])
def test_unreadable_exclude_files_are_refused_not_a_traceback(no_network, monkeypatch, tmp_path,
                                                              case):
    p = tmp_path / "ex.json"
    if case == "truncated_json":
        p.write_bytes(('["%s"' % A).encode("utf-8"))
    elif case == "utf16_bom":
        p.write_bytes(json.dumps([A]).encode("utf-16"))
    got = None
    try:
        _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json", "--exclude-ids", str(p))
    except BaseException as e:          # noqa: BLE001 - the defect is the exception type
        got = e
    assert isinstance(got, SystemExit) and "exclude-ids" in str(got), repr(got)
    assert DistillClient.calls == []
