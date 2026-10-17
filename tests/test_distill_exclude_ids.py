"""--exclude-ids: an operator's list of fact ids removed from the distillation population.

What it must do, and what each test pins:
- listed ids leave the population on the sequential, batch and convergence readers, and nothing
  else changes (the fact base is opened read-only and not written);
- ids are accepted as full uuids, 8-char prefixes, or F-<prefix>, from a JSON list, a JSON object
  with an "ids" list, or a text file with one id per line;
- an id that matches nothing in the population is REPORTED (printed and stamped), split into
  "not in the fact base at all" and "in the fact base but already outside the population";
- the tree stamp carries the file's sha256, its basename (never an absolute path), the number of
  ids requested and the number excluded; a run without the flag stamps that no file was used;
- a malformed entry is refused before any client exists;
- a batch submitted under one exclusion list cannot be resumed under another.
No API calls.
"""
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from baselayer.distillation import distill
from baselayer.distillation import spend
from tests.test_artifact_stamps import DistillClient, no_network  # noqa: F401
from tests.test_distill_subject import ROWS, _db, _prompts, _run

A, B, C, D, E = (r[0] for r in ROWS)          # C is about Dana, E has a NULL subject


def _file(tmp_path, content, name="exclude.json"):
    p = tmp_path / name
    p.write_bytes(content.encode("utf-8"))
    return p


def test_listed_ids_are_excluded_from_the_population(no_network, monkeypatch, tmp_path):
    ex = _file(tmp_path, json.dumps([A, "F-" + D[:8]]))
    tree = _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json", "--exclude-ids", str(ex))
    st = tree["stamp"]
    assert st["facts_total"] == 1                     # 3 user facts, 2 excluded
    assert st["exclude_ids_excluded"] == 2
    p = _prompts()
    assert "writes the plan" not in p and "dated backup" not in p
    assert "asks for two options" in p


def test_without_the_flag_the_population_is_unchanged_and_the_stamp_says_so(
        no_network, monkeypatch, tmp_path):
    st = _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json")["stamp"]
    assert st["facts_total"] == 3
    assert st["exclude_ids_file"] is None and st["exclude_ids_sha256"] is None
    assert st["exclude_ids_excluded"] == 0


def test_an_id_not_in_the_population_is_reported_not_silently_ignored(
        no_network, monkeypatch, tmp_path, capsys):
    absent = "0badc0de-0000-4000-8000-000000000009"
    ex = _file(tmp_path, json.dumps({"ids": [A, absent, C[:8]]}))
    st = _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json",
              "--exclude-ids", str(ex))["stamp"]
    assert st["exclude_ids_requested"] == 3
    assert st["exclude_ids_excluded"] == 1
    assert st["exclude_ids_not_in_corpus"] == [absent]
    assert st["exclude_ids_outside_population"] == [C[:8]]   # Dana's fact: another subject
    out = capsys.readouterr().out
    assert "NOT IN THE FACT BASE" in out and absent in out
    assert "already outside the population" in out


def test_the_stamp_carries_the_file_hash_basename_and_count(no_network, monkeypatch, tmp_path):
    ex = _file(tmp_path, "# support filter\n%s\n\nF%s  # prefix form\n" % (B, D[:8]),
               name="ids.txt")
    st = _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json",
              "--exclude-ids", str(ex))["stamp"]
    assert st["exclude_ids_sha256"] == hashlib.sha256(ex.read_bytes()).hexdigest()
    assert st["exclude_ids_file"] == "ids.txt"               # basename, never the full path
    assert str(tmp_path) not in json.dumps(st)
    assert st["exclude_ids_requested"] == 2 and st["exclude_ids_excluded"] == 2
    assert st["facts_total"] == 1


def test_a_different_file_gives_a_different_hash(no_network, monkeypatch, tmp_path):
    s1 = _run(monkeypatch, _db(tmp_path / "c1"), tmp_path / "t1.json", "--exclude-ids",
              str(_file(tmp_path, json.dumps([A]), "a.json")))["stamp"]
    s2 = _run(monkeypatch, _db(tmp_path / "c2"), tmp_path / "t2.json", "--exclude-ids",
              str(_file(tmp_path, json.dumps([B]), "b.json")))["stamp"]
    assert s1["exclude_ids_sha256"] != s2["exclude_ids_sha256"]


@pytest.mark.parametrize("content", ['["not-an-id"]', "%s\nzzzzzzzz\n" % A, "[]", '{"x": []}'])
def test_malformed_or_empty_files_are_refused_before_any_call(no_network, monkeypatch, tmp_path,
                                                              content):
    ex = _file(tmp_path, content)
    with pytest.raises(SystemExit, match="exclude-ids"):
        _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json", "--exclude-ids", str(ex))
    assert DistillClient.calls == []


def test_the_fact_base_is_not_written(no_network, monkeypatch, tmp_path):
    db = _db(tmp_path / "c")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    _run(monkeypatch, db, tmp_path / "t.json", "--exclude-ids",
         str(_file(tmp_path, json.dumps([A]))))
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


# --------------------------------------------------------------------------- batch path

def test_batch_path_excludes_and_stamps(monkeypatch, tmp_path):
    from tests.test_distill_batch import FakeBatches, BatchClient
    from tests.test_distill_batch import _run as brun, _tree
    DistillClient.calls = []
    FakeBatches.created, FakeBatches.script, FakeBatches.retrieves = [], {}, 0
    monkeypatch.setattr("anthropic.Anthropic", BatchClient)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")
    db = _db(tmp_path / "c")
    ex = _file(tmp_path, json.dumps([A]))
    out = tmp_path / "out"
    brun(monkeypatch, db, out, "--exclude-ids", str(ex), layers="anchors")
    st = _tree(out, "anchors")["stamp"]
    assert st["facts_total"] == 2 and st["exclude_ids_excluded"] == 1
    assert st["exclude_ids_sha256"] == hashlib.sha256(ex.read_bytes()).hexdigest()
    sent = "\n".join(r["params"]["messages"][0]["content"] for r in FakeBatches.created[0])
    assert "writes the plan" not in sent and "asks for two options" in sent
    state = json.load(open(out / "batch_state.json", encoding="utf-8"))
    assert state["exclude_ids_sha256"] == st["exclude_ids_sha256"]
    # Resuming the same batch under a different exclusion list is refused.
    other = _file(tmp_path, json.dumps([B]), "other.json")
    with pytest.raises(SystemExit, match="exclude-ids sha256"):
        brun(monkeypatch, db, out, "--resume", "--exclude-ids", str(other), layers="anchors")
    brun(monkeypatch, db, out, "--resume", "--exclude-ids", str(ex), layers="anchors")
    assert len(FakeBatches.created) == 1


@pytest.mark.parametrize("script,extra", [
    ("distill_batch.py", ["--outdir", "OUT", "--layers", "anchors", "--partitions", "predicate"]),
    ("convergence.py", ["--out", "OUT", "--runs", "1"]),
])
def test_sibling_readers_apply_the_exclusion(script, extra, monkeypatch, tmp_path, capsys):
    import baselayer.distillation as pkg
    here = Path(pkg.__file__).parent
    monkeypatch.setenv("BASELAYER_SRC", str(here.parent.parent))
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    db = _db(tmp_path / "c")
    ex = _file(tmp_path, json.dumps([A, B]))
    extra = [str(tmp_path / "out") if x == "OUT" else x for x in extra]
    monkeypatch.setattr(sys, "argv", [script, "--db", str(db), "--dry-run", "--max-facts", "10",
                                      *extra, "--exclude-ids", str(ex)])
    runpy.run_path(str(here / script), run_name="__main__")
    out = capsys.readouterr().out
    assert "facts=1 " in out
    assert "exclude-ids: 2 excluded of 3 population facts" in out


def test_cli_threads_exclude_ids(monkeypatch):
    from baselayer import cli
    seen = {}
    monkeypatch.setattr(distill, "main", lambda: seen.setdefault("distill", list(sys.argv)))
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr(sys, "argv", ["baselayer", "distill", "--out", "t.json", "--db", "x.db",
                                      "--exclude-ids", "ids.json"])
    cli.main()
    i = seen["distill"].index("--exclude-ids")
    assert seen["distill"][i + 1] == "ids.json"
