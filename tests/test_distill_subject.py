"""Distillation reads only facts whose subject is the person (subject = 'user') by default.

A fact extracted under another person's subject reached two authored
claims as evidence about the person in the preflight mini run. By default such facts are now
excluded, counted and stamped. --include-other-subjects admits them as LABELLED context: the
subject travels as its own field from the leaf prompt through the tree and the package to the
author's rendered evidence, never spliced into the fact text. No API calls.
"""
import json
import runpy
import sqlite3
import sys
from pathlib import Path

import pytest

from baselayer.distillation import assemble as asm
from baselayer.distillation import author_from_package as afp
from baselayer.distillation import distill
from baselayer.distillation import spend
from tests.test_artifact_stamps import V, DistillClient, no_network  # noqa: F401

ROWS = [  # id, text, subject
    ("aaaaaaaa-0000-4000-8000-000000000001", "user writes the plan before code", "user"),
    ("bbbbbbbb-0000-4000-8000-000000000002", "user asks for two options", "user"),
    ("cccccccc-0000-4000-8000-000000000003", "Dana prefers the blue folder", "Dana"),
    ("dddddddd-0000-4000-8000-000000000004", "user keeps a dated backup", "user"),
    ("eeeeeeee-0000-4000-8000-000000000005", "unattributed statement", None),
]


def _db(root, rows=ROWS, with_subject=True):
    db = root / "data" / "database" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, predicate TEXT, "
              "category TEXT, superseded_by TEXT, created_at REAL, turn_contract_version TEXT"
              + (", subject TEXT" if with_subject else "") + ")")
    for i, (fid, text, subj) in enumerate(rows):
        vals = [fid, text, "prefers", "preference", None, float(i), V]
        if with_subject:
            vals.append(subj)
        c.execute("INSERT INTO memory_facts VALUES (%s)" % ",".join("?" * len(vals)), vals)
    c.commit()
    c.close()
    return db


def _run(monkeypatch, db, out, *extra):
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "10",
                                      "--layer", "anchors", *extra])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def _prompts():
    return "\n".join(c["messages"][0]["content"] for c in DistillClient.calls)


def test_default_reads_only_user_subject_and_stamps_the_rest(no_network, monkeypatch, tmp_path):
    tree = _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json")
    st = tree["stamp"]
    assert st["facts_total"] == 3
    assert st["subject_filter"] == "user"
    assert st["other_subject_facts_excluded"] == 2
    assert st["other_subject_facts_included"] == 0
    assert st["other_subject_counts"] == {"Dana": 1, "(null)": 1}
    p = _prompts()
    assert "Dana prefers" not in p and "unattributed" not in p
    assert "writes the plan" in p


def test_opt_in_includes_other_subjects_labelled_as_context(no_network, monkeypatch, tmp_path):
    tree = _run(monkeypatch, _db(tmp_path / "c"), tmp_path / "t.json",
                "--include-other-subjects")
    st = tree["stamp"]
    assert st["facts_total"] == 5
    assert st["subject_filter"] == "all, other subjects labelled"
    assert st["other_subject_facts_included"] == 2
    assert st["other_subject_ids"] == {"cccccccc": "Dana", "eeeeeeee": "(null)"}
    p = _prompts()
    assert "[cccccccc] (ABOUT Dana, NOT THE PERSON) Dana prefers" in p
    assert "[aaaaaaaa] user writes the plan" in p          # the person's own facts unlabelled


def test_no_user_facts_is_refused_before_any_call(no_network, monkeypatch, tmp_path):
    rows = [(f, t, "this person") for f, t, _ in ROWS]
    with pytest.raises(SystemExit, match="subject = 'user'"):
        _run(monkeypatch, _db(tmp_path / "c", rows), tmp_path / "t.json")
    assert DistillClient.calls == []


def test_corpus_without_subject_column_is_unfiltered_and_says_so(no_network, monkeypatch,
                                                                  tmp_path):
    tree = _run(monkeypatch, _db(tmp_path / "c", with_subject=False), tmp_path / "t.json")
    assert tree["stamp"]["facts_total"] == 5
    assert tree["stamp"]["subject_filter"] == "column absent"


def _tree_with_other(run_id):
    return {"stamp": {"run_id": run_id, "layer": "anchors", "turn_contract_version": V,
                      "input_hash": "h", "other_subject_ids": {"cccccccc": "Dana"}},
            "leaves": [{"dispositions": {"aaaaaaaa": "theme", "cccccccc": "singular"}}],
            "root": {"themes": [{"statement": "plans first", "fact_ids": ["aaaaaaaa",
                                                                          "cccccccc"]}],
                     "singularities": [{"fact_id": "cccccccc", "verbatim": "Dana prefers x",
                                        "subject": "Dana"}],
                     "contradictions": []}}


def test_package_and_author_render_carry_the_label(capsys):
    pkg = asm.assemble([_tree_with_other("r1")])
    assert pkg["other_subject_ids"] == {"cccccccc": "Dana"}
    out = afp.render(pkg)
    assert "[F-cccccccc] (ABOUT Dana, NOT THE PERSON) Dana prefers x" in out
    assert "cites facts about others: F-cccccccc (Dana)" in out
    assert "NOT THE PERSON" in out.split("## THEMES")[0]      # the header explains the label


def test_render_of_a_package_without_others_is_unchanged(capsys):
    t = _tree_with_other("r1")
    t["stamp"].pop("other_subject_ids")
    t["root"]["singularities"][0].pop("subject")
    out = afp.render(asm.assemble([t]))
    assert "NOT THE PERSON" not in out


@pytest.mark.parametrize("script,extra", [
    ("distill_batch.py", ["--outdir", "OUT", "--layers", "anchors", "--partitions", "predicate"]),
    ("convergence.py", ["--out", "OUT", "--runs", "1"]),
])
def test_sibling_readers_apply_the_subject_filter(script, extra, monkeypatch, tmp_path, capsys):
    import baselayer.distillation as pkg
    here = Path(pkg.__file__).parent
    monkeypatch.setenv("BASELAYER_SRC", str(here.parent.parent))
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    db = _db(tmp_path / "c")
    extra = [str(tmp_path / "out") if x == "OUT" else x for x in extra]
    for flag, n in (([], 3), (["--include-other-subjects"], 5)):
        monkeypatch.setattr(sys, "argv", [script, "--db", str(db), "--dry-run",
                                          "--max-facts", "10", *extra, *flag])
        runpy.run_path(str(here / script), run_name="__main__")
        out = capsys.readouterr().out
        assert "facts=%d " % n in out
        assert ("other-subject facts: 2 excluded" in out) == (not flag)


def test_cli_threads_include_other_subjects(monkeypatch):
    from baselayer import cli
    seen = {}
    monkeypatch.setattr(distill, "main", lambda: seen.setdefault("distill", list(sys.argv)))
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    monkeypatch.setattr(sys, "argv", ["baselayer", "distill", "--out", "t.json", "--db", "x.db",
                                      "--include-other-subjects"])
    cli.main()
    assert "--include-other-subjects" in seen["distill"]
