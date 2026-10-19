"""When the tree cannot be archived beside the corpus, `distill` keeps the --out copy, and the run
ledger (distill_runs.jsonl) falls back to the --out directory. It used to raise TypeError
(os.path.join(None, ...)) after every billed call, so the run crashed at the end and the ledger
row was lost. No API calls: fake client only.
"""
import json
import sys

from baselayer.distillation import distill
from tests.test_artifact_stamps import FACTS, _make_db, no_network  # noqa: F401


def test_ledger_falls_back_to_out_dir_when_archive_fails(no_network, monkeypatch, tmp_path, capsys):
    db = _make_db(tmp_path / "c", FACTS)
    # a FILE where the archive directory would go makes os.makedirs fail
    (tmp_path / "c" / "data" / "distillation").write_text("not a directory", encoding="utf-8")
    outdir = tmp_path / "out"
    outdir.mkdir()
    out = outdir / "t.json"
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "2",
                                      "--layer", "anchors"])
    distill.main()
    assert "tree NOT archived" in capsys.readouterr().out
    assert json.load(open(out, encoding="utf-8"))["stamp"]["layer"] == "anchors"
    ledger = outdir / "distill_runs.jsonl"
    assert ledger.exists() and json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])["layer"] == "anchors"


def test_ledger_goes_to_the_archive_when_it_works(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(outdir / "t.json"),
                                      "--model", "claude-haiku-4-5", "--max-facts", "2",
                                      "--layer", "anchors"])
    distill.main()
    assert (tmp_path / "c" / "data" / "distillation" / "distill_runs.jsonl").exists()
    assert not (outdir / "distill_runs.jsonl").exists()
