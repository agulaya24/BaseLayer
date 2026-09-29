"""The leaf payload ceiling: projected BEFORE any leaf is paid for, and handled by sharding the
package rather than by stopping the run. No API calls.

Before: distill.py counted the leaf payload after every leaf of the layer was paid for and
raised above BASELAYER_LEAF_PAYLOAD_CEILING, discarding the tree. Now:
- distill projects the payload from the fact count before the first call and stamps it;
- the measured payload over the ceiling no longer raises; the tree is written and says so;
- assemble splits an over-budget package into shards along CONTIGUOUS LEAF RANGES, with no model
  call and no merge: every theme, singularity and contradiction lands in exactly one shard,
  unchanged (seen_in_leaves stays the whole-tree count), and each shard renders within budget;
- author_from_package authors each shard as its own request, told it is shard k of K, and
  concatenates the claims (renumbered, shard recorded). There is no second authoring pass over
  the shard claims; cross-shard collapse is left to compose, which reads all three layers.
"""
import json
import sys
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import assemble as asm
from baselayer.distillation import author_from_package as afp
from baselayer.distillation import distill
from baselayer.distillation import spend
from tests.test_artifact_stamps import (FACTS, V, DistillClient, _make_db, _Stream,  # noqa: F401
                                        author_env, no_network)


# --------------------------------------------------------------------------- distill

def _run(monkeypatch, db, out):
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "1",
                                      "--layer", "anchors"])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def test_payload_is_projected_before_the_first_leaf(no_network, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BASELAYER_LEAF_PAYLOAD_CEILING", "30")
    tree = _run(monkeypatch, _make_db(tmp_path / "c", FACTS), tmp_path / "t.json")
    out = capsys.readouterr().out
    assert out.index("PAYLOAD PROJECTION") < out.index("  L1 ")
    st = tree["stamp"]
    assert st["payload_projected_tokens"] == pytest.approx(
        3 * spend.MEASURED_PAYLOAD_TOKENS_PER_FACT)
    assert st["payload_shards_projected"] == 3          # ceil(72.3 / 30)
    assert st["single_author_ceiling_tokens"] == 30


def test_measured_payload_over_ceiling_writes_the_tree(no_network, monkeypatch, tmp_path,
                                                       capsys):
    """The fake count_tokens reports 10 tokens; a ceiling of 5 used to raise SystemExit after
    every leaf was paid for."""
    monkeypatch.setenv("BASELAYER_LEAF_PAYLOAD_CEILING", "5")
    tree = _run(monkeypatch, _make_db(tmp_path / "c", FACTS), tmp_path / "t.json")
    st = tree["stamp"]
    assert st["leaf_payload_tokens"] == 10
    assert st["exceeds_single_author_ceiling"] is True
    assert "will be sharded" in capsys.readouterr().out


# --------------------------------------------------------------------------- assemble

def _ids(i):
    return ["%08x" % (0xa0000000 + i * 16 + k) for k in range(3)]


def _big_tree(run_id="r1", n_leaves=4, pad=2000):
    """n_leaves disjoint leaves; each carries 2 themes, 1 singularity, 1 contradiction."""
    leaves, themes, sings, contra = [], [], [], []
    for i in range(n_leaves):
        ids = _ids(i)
        th = [{"statement": "theme %d-%d %s" % (i, j, "x" * pad), "fact_ids": ids[:2]}
              for j in range(2)]
        sg = [{"fact_id": ids[2], "verbatim": "sing %d %s" % (i, "y" * pad), "why": "w"}]
        co = [{"a_fact_ids": [ids[0]], "b_fact_ids": [ids[1]], "tension": "tension %d" % i}]
        leaves.append({"_chunk": "predicate-%d/%d x" % (i + 1, n_leaves), "_ids": ids,
                       "themes": th, "singularities": sg, "contradictions": co,
                       "dispositions": {f: "theme" for f in ids}})
        for t in th:
            themes.append(dict(t, seen_in_leaves=1))
        sings += sg
        contra += co
    # a theme statement seen in two leaves: its seen_in_leaves must stay 2 in whichever shard
    themes[0]["seen_in_leaves"] = 2
    return {"stamp": {"run_id": run_id, "layer": "anchors", "turn_contract_version": V,
                      "input_hash": "h"},
            "leaves": leaves,
            "root": {"themes": themes, "singularities": sings, "contradictions": contra}}


def _items(pkg):
    return (sorted(json.dumps(t, sort_keys=True) for t in pkg["themes"]),
            sorted(json.dumps(s, sort_keys=True) for s in pkg["singularities_verified"]
                   + pkg["singularities_unverified"]),
            sorted(json.dumps(c, sort_keys=True) for c in pkg["contradictions"]))


def test_package_under_budget_is_one_package(capsys):
    trees = [_big_tree()]
    shards = asm.shard(trees, asm.assemble(trees), budget_tokens=10 ** 6)
    assert len(shards) == 1 and "shard" not in shards[0]


def test_shards_are_lossless_contiguous_and_within_budget(capsys):
    trees = [_big_tree()]
    full = asm.assemble(trees)
    budget = int(len(afp.render(full)) / asm.SHARD_CHARS_PER_TOKEN / 2.5)
    shards = asm.shard(trees, full, budget_tokens=budget)
    assert len(shards) >= 2
    # every item in exactly one shard, unchanged
    union = [[], [], []]
    for s in shards:
        for k, part in enumerate(_items(s)):
            union[k] += part
    assert [sorted(u) for u in union] == list(_items(full))
    # contiguous, covering, ordered leaf ranges
    ranges = [tuple(s["shard"]["leaf_range"]) for s in shards]
    assert ranges[0][0] == 0 and ranges[-1][1] == 4
    assert all(a[1] == b[0] for a, b in zip(ranges, ranges[1:]))
    for i, s in enumerate(shards, 1):
        assert (s["shard"]["index"], s["shard"]["of"]) == (i, len(shards))
        assert s["stamp"]["shard"] == s["shard"]
        assert len(afp.render(s)) / asm.SHARD_CHARS_PER_TOKEN <= budget
    seen = {t["statement"]: t["seen_in_leaves"] for s in shards for t in s["themes"]}
    assert seen[full["themes"][0]["statement"]] == 2


def test_misaligned_trees_are_not_sharded(capsys):
    a, b = _big_tree("r1"), _big_tree("r2")
    b["leaves"][0]["_chunk"] = "random-1/4 x"
    full = asm.assemble([a, b])
    with pytest.raises(SystemExit, match="partitions do not align"):
        asm.shard([a, b], full, budget_tokens=100)


def test_assemble_main_writes_manifest_and_shards(tmp_path, monkeypatch, capsys):
    tp = tmp_path / "anchors_tree.json"
    tp.write_text(json.dumps(_big_tree()), encoding="utf-8")
    out = tmp_path / "anchors_pkg.json"
    monkeypatch.setattr(sys, "argv", ["assemble.py", str(tp), "--out", str(out),
                                      "--shard-token-budget", "3000"])
    asm.main()
    man = json.load(open(out, encoding="utf-8"))
    assert man["shard_manifest"] is True and man["layer"] == "anchors"
    assert len(man["shards"]) >= 2
    for name in man["shards"]:
        sp = json.load(open(tmp_path / name, encoding="utf-8"))
        assert sp["shard"]["of"] == len(man["shards"])


def test_dismissed_contested_count_is_not_the_display_cap(capsys):
    t1, t2 = _big_tree("r1", n_leaves=1), _big_tree("r2", n_leaves=1)
    t1["leaves"][0]["dispositions"] = {"%08x" % i: "not_load_bearing" for i in range(250)}
    t2["leaves"][0]["dispositions"] = {"%08x" % i: "theme" for i in range(250)}
    pkg = asm.assemble([t1, t2])
    assert pkg["dismissed_CONTESTED_total"] == 250
    assert "250 are CONTESTED" in afp.render(pkg)


# --------------------------------------------------------------------------- author

class ShardAuthorClient:
    """Cites the first id it can find in the prompt's evidence, plus one id from the OTHER
    shard, which the per-shard gate must strip."""
    calls = []

    def __init__(self, *a, **k):
        self.messages = self

    def stream(self, **kw):
        ShardAuthorClient.calls.append(kw)
        name = kw["tools"][0]["name"]
        prompt = kw["messages"][0]["content"]
        import re
        ids = re.findall(r"\[F-([0-9a-f]{8})\]", prompt)
        if name == "emit_layer":
            foreign = "a0000030" if "a0000000" in ids else "a0000000"
            inp = {"layer": "anchors", "preamble": "p",
                   "claims": [{"id": "A1", "name": "X", "statement": "s", "active_when": "",
                               "fact_ids": [ids[0], foreign], "contested": False},
                              {"id": "A2", "name": "Y", "statement": "t", "active_when": "",
                               "fact_ids": [ids[1]], "contested": True}]}
        else:
            inp = {"title": "t", "sections": [{"heading": "h", "body": "b",
                                               "fact_ids": ids[:1]}],
                   "carried_contradictions": []}
        return _Stream(NS(content=[NS(type="tool_use", name=name, input=inp)],
                          stop_reason="tool_use", stop_details=None,
                          usage=NS(input_tokens=100, output_tokens=50)))


def test_author_authors_each_shard_and_concatenates(author_env, monkeypatch, tmp_path):
    ShardAuthorClient.calls = []
    monkeypatch.setattr("anthropic.Anthropic", ShardAuthorClient)
    tp = tmp_path / "t.json"
    tp.write_text(json.dumps(_big_tree()), encoding="utf-8")
    man = tmp_path / "anchors_pkg.json"
    monkeypatch.setattr(sys, "argv", ["assemble.py", str(tp), "--out", str(man),
                                      "--shard-token-budget", "3000"])
    asm.main()
    n = len(json.load(open(man, encoding="utf-8"))["shards"])
    out = author_env.run(man)
    layer_calls = [c for c in ShardAuthorClient.calls if c["tools"][0]["name"] == "emit_layer"]
    assert len(layer_calls) == n
    for k, c in enumerate(layer_calls, 1):
        assert "SHARD %d OF %d" % (k, n) in c["messages"][0]["content"]
    data = json.load(open(out / "anchors.json", encoding="utf-8"))
    assert [c["id"] for c in data["claims"]] == ["A%d" % i for i in range(1, 2 * n + 1)]
    assert [c["shard"] for c in data["claims"]] == [k for k in range(1, n + 1) for _ in (0, 1)]
    assert all(c["shard_claim_id"] in ("A1", "A2") for c in data["claims"])
    # the foreign id was stripped by the shard's own gate
    for c in data["claims"]:
        shard_ids = {f for f in c["fact_ids"]}
        assert len(shard_ids) == 1
    st = json.load(open(out / "anchors.stamp.json", encoding="utf-8"))
    assert [s["index"] for s in st["shards"]] == list(range(1, n + 1))
    assert (out / "brief.md").exists()
    compose = [c for c in ShardAuthorClient.calls if c["tools"][0]["name"] == "emit_brief"]
    assert len(compose) == 1


def test_two_packages_for_one_layer_are_refused(author_env):
    from tests.test_artifact_stamps import AuthorClient
    a = author_env.write_pkg("a1.json", V)
    b = author_env.write_pkg("a2.json", V)
    with pytest.raises(SystemExit, match="more than one package for a layer"):
        author_env.run(a, b)
    assert AuthorClient.calls == []


def test_cli_threads_shard_token_budget(monkeypatch):
    from baselayer import cli
    seen = {}
    monkeypatch.setattr(asm, "main", lambda: seen.setdefault("asm", list(sys.argv)))
    monkeypatch.setattr(sys, "argv", ["baselayer", "assemble", "t.json", "--out", "p.json",
                                      "--shard-token-budget", "123"])
    cli.main()
    assert seen["asm"][seen["asm"].index("--shard-token-budget") + 1] == "123"
