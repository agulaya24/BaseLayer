"""Stamps on distillation artifacts (docs/core/TURN_CONTRACT.md §7). No API calls.

Every leaf, tree, package, layer and brief records: the turn-contract version of the facts it
was built from (a mix is refused), the model, a prompt hash, git_commit, a REPO-RELATIVE
code_path, and the hash of its input. The input hash covers fact ids AND fact text, because a
hash of ids alone cannot tell two corpora apart when the same ids carry different text.

distill.main and author_from_package.main run end to end against scripted fake clients; the
real `anthropic.Anthropic` is replaced for the whole test, so nothing can reach the network.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import assemble as asm
from baselayer.distillation import author_from_package as afp
from baselayer.distillation import distill

V = "turn-contract/1"
REQUIRED = ("turn_contract_version", "model", "prompt_hash", "input_hash", "git_commit",
            "code_path")

FACTS = [
    ("aaaaaaaa-0000-4000-8000-000000000001", "They write the plan before they write code.", V),
    ("bbbbbbbb-0000-4000-8000-000000000002", "They ask for two options, never a spectrum.", V),
    ("cccccccc-0000-4000-8000-000000000003", "They keep a dated backup before any rewrite.", V),
]


# --------------------------------------------------------------------------- fakes

class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class DistillClient:
    """Answers every leaf with a well-formed node covering exactly the ids in its prompt."""
    calls = []

    def __init__(self, *a, **k):
        self.messages = self

    def stream(self, **kw):
        DistillClient.calls.append(kw)
        prompt = kw["messages"][0]["content"]
        body = prompt.split("CHUNK:", 1)[1]
        import re
        ids = re.findall(r"^\[([0-9a-f]{8})\] ", body, re.M)
        node = {"themes": [{"statement": "a theme", "fact_ids": ids}], "singularities": [],
                "contradictions": [], "dispositions": {i: "theme" for i in ids}}
        return _Stream(NS(content=[NS(type="text", text=json.dumps(node))],
                          usage=NS(input_tokens=10, output_tokens=5), stop_reason="end_turn"))

    def count_tokens(self, **kw):
        return NS(input_tokens=10)


def _make_db(root, facts, with_version_col=True):
    db = root / "data" / "database" / "memory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, predicate TEXT, "
              "category TEXT, superseded_by TEXT, created_at REAL"
              + (", turn_contract_version TEXT" if with_version_col else "") + ")")
    for i, (fid, text, ver) in enumerate(facts):
        if with_version_col:
            c.execute("INSERT INTO memory_facts VALUES (?,?,?,?,NULL,?,?)",
                      (fid, text, "prefers", "preference", float(i), ver))
        else:
            c.execute("INSERT INTO memory_facts VALUES (?,?,?,?,NULL,?)",
                      (fid, text, "prefers", "preference", float(i)))
    c.commit()
    c.close()
    return db


@pytest.fixture
def no_network(monkeypatch, tmp_path):
    DistillClient.calls = []
    monkeypatch.setattr("anthropic.Anthropic", DistillClient)
    monkeypatch.chdir(tmp_path)          # call_json writes *.RAWFAIL.txt into the cwd
    monkeypatch.delenv("BASELAYER_FORCE_MERGE", raising=False)
    # The operator's per-run confirmation of the dated rate table (spend.py). Tests that check
    # the refusal delete it.
    from baselayer.distillation import spend
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    # A run-wide spend ceiling (spend.plan_ceiling); refusal tests delete or lower it.
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")


def _distill(monkeypatch, db, out, layer="anchors"):
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "2",
                                      "--layer", layer, "--partition", "predicate"])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def _assert_relative(path_value):
    assert path_value, "code_path missing"
    assert not os.path.isabs(path_value), path_value
    assert ":" not in path_value and not path_value.startswith("/"), path_value
    assert str(Path.home()) not in path_value


# --------------------------------------------------------------------------- distill

def test_tree_and_ledger_carry_no_absolute_path(no_network, monkeypatch, tmp_path):
    """Task P-06: the tree stamp wrote os.path.abspath(__file__), i.e. the operator's home
    directory, into every tree; the ledger wrote the absolute --out path."""
    db = _make_db(tmp_path / "corpus", FACTS)
    tree = _distill(monkeypatch, db, tmp_path / "tree.json")
    _assert_relative(tree["stamp"]["code_path"])
    assert tree["stamp"]["code_path"].endswith("distillation/distill.py")
    assert str(Path.home()) not in json.dumps(tree).replace("\\\\", "\\")
    ledger = (tmp_path / "corpus" / "data" / "distillation" / "distill_runs.jsonl").read_text(
        encoding="utf-8")
    row = json.loads(ledger.strip().splitlines()[-1])
    assert not os.path.isabs(row["tree_path"])
    assert str(Path.home()) not in ledger.replace("\\\\", "\\")


def test_tree_stamp_is_complete(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path / "corpus", FACTS)
    tree = _distill(monkeypatch, db, tmp_path / "tree.json")
    st = tree["stamp"]
    for k in REQUIRED:
        assert k in st, k
    assert st["turn_contract_version"] == V
    assert st["model"] == "claude-haiku-4-5"
    _assert_relative(st["code_path"])
    # Nothing in the tree or the ledger carries an absolute path.
    blob = json.dumps(tree)
    assert str(tmp_path) not in blob and str(Path.home()) not in blob
    ledger = (tmp_path / "corpus" / "data" / "distillation" / "distill_runs.jsonl").read_text(
        encoding="utf-8")
    assert str(tmp_path) not in ledger.replace("\\\\", "\\")
    row = json.loads(ledger.strip().splitlines()[-1])
    assert not os.path.isabs(row["tree_path"])
    assert row["input_hash"] == st["input_hash"]


def test_every_leaf_carries_its_own_stamp_and_input_hash(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path / "corpus", FACTS)
    tree = _distill(monkeypatch, db, tmp_path / "tree.json")
    leaves = tree["leaves"]
    assert len(leaves) == 2                      # 3 facts, chunk size 2
    hashes = set()
    for leaf in leaves:
        st = leaf["_stamp"]
        for k in REQUIRED:
            assert k in st, k
        _assert_relative(st["code_path"])
        hashes.add(st["input_hash"])
    assert len(hashes) == 2, "each leaf hashes its own chunk, not the corpus"


def test_changed_fact_text_changes_input_hash_and_run_id(no_network, monkeypatch, tmp_path):
    t1 = _distill(monkeypatch, _make_db(tmp_path / "c1", FACTS), tmp_path / "t1.json")
    edited = [FACTS[0], (FACTS[1][0], "They ask for a spectrum of options.", V), FACTS[2]]
    t2 = _distill(monkeypatch, _make_db(tmp_path / "c2", edited), tmp_path / "t2.json")
    # Same ids, so the old ids-only hash cannot tell them apart ...
    assert t1["stamp"]["corpus_hash"] == t2["stamp"]["corpus_hash"]
    # ... and the input hash, and therefore the run id and the archived file name, can.
    assert t1["stamp"]["input_hash"] != t2["stamp"]["input_hash"]
    assert t1["stamp"]["run_id"] != t2["stamp"]["run_id"]


@pytest.mark.parametrize("versions", [(V, V, None), (V, "turn-contract/2", V)])
def test_mixed_contract_versions_are_refused_before_any_call(no_network, monkeypatch, tmp_path,
                                                           versions):
    facts = [(f, t, v) for (f, t, _), v in zip(FACTS, versions)]
    db = _make_db(tmp_path / "corpus", facts)
    with pytest.raises(SystemExit, match="(?i)mix"):
        _distill(monkeypatch, db, tmp_path / "tree.json")
    assert DistillClient.calls == []


def test_corpus_without_version_column_distils_as_unversioned(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path / "corpus", FACTS, with_version_col=False)
    tree = _distill(monkeypatch, db, tmp_path / "tree.json")
    assert "turn_contract_version" in tree["stamp"]
    assert tree["stamp"]["turn_contract_version"] is None


# --------------------------------------------------------------------------- assemble

def _tree(run_id, version, layer="anchors", fids=("aaaaaaaa",)):
    return {"stamp": {"run_id": run_id, "layer": layer, "turn_contract_version": version,
                      "input_hash": "h" + run_id},
            "root": {"themes": [{"statement": "t", "fact_ids": list(fids)}],
                     "singularities": [{"fact_id": fids[0], "verbatim": "v"}],
                     "contradictions": []},
            "leaves": [{"dispositions": {f: "theme" for f in fids}}]}


def test_package_is_stamped(capsys):
    pkg = asm.assemble([_tree("r1", V), _tree("r2", V), _tree("r3", V)])
    st = pkg["stamp"]
    for k in REQUIRED:
        assert k in st, k
    assert st["turn_contract_version"] == V
    assert st["model"] is None                 # mechanical: no model runs here
    _assert_relative(st["code_path"])
    assert st["code_path"].endswith("distillation/assemble.py")
    other = asm.assemble([_tree("r1", V), _tree("r2", V), _tree("r4", V)])
    assert other["stamp"]["input_hash"] != st["input_hash"]


@pytest.mark.parametrize("second", ["turn-contract/2", None])
def test_package_refuses_a_mix_of_versions(second, capsys):
    with pytest.raises(SystemExit, match="(?i)mix"):
        asm.assemble([_tree("r1", V), _tree("r2", second)])


# --------------------------------------------------------------------------- author

class AuthorClient:
    """Scripted: optional leading rejects, then a valid tool call for whichever tool is asked."""
    script = []
    calls = []

    def __init__(self, *a, **k):
        self.messages = self

    def stream(self, **kw):
        AuthorClient.calls.append(kw)
        name = kw["tools"][0]["name"]
        if AuthorClient.script:
            kind = AuthorClient.script.pop(0)
            if kind == "no_tool":
                return _Stream(NS(content=[NS(type="text", text="prose")], stop_reason="end_turn",
                                  stop_details=None, usage=NS(input_tokens=100, output_tokens=7)))
        if name == "emit_layer":
            inp = {"layer": "anchors", "preamble": "",
                   "claims": [{"id": "A1", "name": "X", "statement": "s", "active_when": "",
                               "fact_ids": ["aaaaaaaa"], "contested": False}]}
        else:
            inp = {"title": "t", "sections": [{"heading": "h", "body": "b [F-aaaaaaaa]",
                                               "fact_ids": ["aaaaaaaa"]}],
                   "carried_contradictions": []}
        return _Stream(NS(content=[NS(type="thinking", thinking=""),
                                   NS(type="tool_use", name=name, input=inp)],
                          stop_reason="tool_use", stop_details=None,
                          usage=NS(input_tokens=100, output_tokens=50)))


@pytest.fixture
def author_env(monkeypatch, tmp_path, capsys):
    AuthorClient.script, AuthorClient.calls = [], []
    monkeypatch.setattr("anthropic.Anthropic", AuthorClient)
    monkeypatch.delenv("BASELAYER_REAUTHOR", raising=False)
    from baselayer.distillation import spend
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    # A run-wide spend ceiling (spend.plan_ceiling); refusal tests delete or lower it.
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")

    def write_pkg(name, version):
        pkg = asm.assemble([_tree("r1", version), _tree("r2", version), _tree("r3", version)])
        p = tmp_path / name
        p.write_text(json.dumps(pkg), encoding="utf-8")
        return p

    def run(*pkgs, extra=()):
        argv = ["afp", "--outdir", str(tmp_path / "out"), "--model", "claude-opus-5-5",
                "--effort", "high", "--max-tokens", "20000", *extra]
        for p in pkgs:
            argv += ["--package", str(p)]
        monkeypatch.setattr(sys, "argv", argv)
        afp.main()
        return tmp_path / "out"
    return NS(write_pkg=write_pkg, run=run, tmp=tmp_path)


def test_layer_and_brief_each_get_a_stamp_file(author_env):
    out = author_env.run(author_env.write_pkg("anchors.json", V))
    for name, tool in (("anchors", "emit_layer"), ("brief", "emit_brief")):
        st = json.loads((out / ("%s.stamp.json" % name)).read_text(encoding="utf-8"))
        for k in REQUIRED + ("effort", "max_tokens", "usage", "cost_usd", "rates_per_mtok"):
            assert k in st, (name, k)
        assert st["model"] == "claude-opus-5-5"
        assert st["effort"] == "high"
        assert st["turn_contract_version"] == V
        assert st["usage"]["input_tokens"] == 100 and st["usage"]["output_tokens"] == 50
        assert st["cost_usd"] == pytest.approx(100 / 1e6 * 4 + 50 / 1e6 * 20)
        _assert_relative(st["code_path"])
    assert json.loads((out / "anchors.stamp.json").read_text())["max_tokens"] == 20000
    assert json.loads((out / "brief.stamp.json").read_text())["max_tokens"] == 30000


def test_rejected_attempts_are_counted_in_usage(author_env):
    AuthorClient.script = ["no_tool"]
    out = author_env.run(author_env.write_pkg("anchors.json", V))
    st = json.loads((out / "anchors.stamp.json").read_text(encoding="utf-8"))
    assert st["usage"] == {"input_tokens": 200, "output_tokens": 57, "attempts": 2}


def test_reused_layer_keeps_its_original_stamp(author_env):
    pkg = author_env.write_pkg("anchors.json", V)
    out = author_env.run(pkg)
    first = (out / "anchors.stamp.json").read_text(encoding="utf-8")
    AuthorClient.calls = []
    author_env.run(pkg)
    assert (out / "anchors.stamp.json").read_text(encoding="utf-8") == first
    assert all(c["tools"][0]["name"] == "emit_brief" for c in AuthorClient.calls)


def test_packages_of_different_versions_are_refused(author_env):
    a = author_env.write_pkg("anchors.json", V)
    b = author_env.write_pkg("core.json", "turn-contract/2")
    with pytest.raises(SystemExit, match="(?i)mix"):
        author_env.run(a, b)
    assert AuthorClient.calls == []
