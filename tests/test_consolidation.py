"""Consolidation stages on a synthetic spec. No model, no network, no corpus database.

The checks are shown to FAIL first: every mutation below breaks one property on purpose
and asserts the check that owns it goes red, before the clean run is trusted green.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from baselayer.consolidation import always_on, categories, checks, dedupe, overlap, port, render, spec, triggers
from baselayer.consolidation import run as crun
from baselayer.consolidation.common import guard_out, payload_hash, read_json, sha256_text, write_json

ROOT = Path(__file__).resolve().parent.parent

LAYERS = {
    "anchors": [
        {"id": "A1", "name": "PLANT ONLY AFTER FROST", "statement": "They wait for the last frost before planting.",
         "active_when": "Before planting seeds or bulbs in a bed.", "fact_ids": ["F-a1", "F-a2"],
         "contested": False},
        {"id": "A2", "name": "JUDGE BY HARVEST", "statement": "They judge beds by what they yield.",
         "active_when": "When judging any bed or border.", "fact_ids": ["F-a3"], "contested": False},
    ],
    "core": [
        {"id": "C1", "name": "SHORT NOTES", "statement": "They keep short notes; read brevity as habit.",
         "active_when": "Any message, especially watering logs.", "fact_ids": ["F-c1"], "contested": False},
        {"id": "C2", "name": "FORMER NURSERY HAND", "statement": "They worked at a nursery for three years.",
         "active_when": "Any discussion of roses, orchards or soil chemistry.", "fact_ids": ["F-c2", "F-a1"],
         "contested": True},
    ],
    "predictions": [
        {"id": "P1", "name": "TENTATIVE YIELDS", "statement": "They put their own estimates as questions.",
         "active_when": "When stating a yield in a seed swap.", "fact_ids": ["F-p1"], "contested": False},
        {"id": "P2", "name": "WINTER IS WORK", "statement": "They treat winter as part of the season.",
         "active_when": "When wintering", "fact_ids": ["F-p2"], "contested": False},
        {"id": "P3", "name": "SAME FROST", "statement": "They hold off until the frost has passed.",
         "active_when": "Before planting seeds or bulbs in a bed.", "fact_ids": ["F-a1", "F-a2"],
         "contested": False},
    ],
}

GROUPING = {"triggers": [
    {"key": "before_planting", "wording_source": {"claim": "A1", "clause": "*"},
     "members": [{"claim": "A1", "clause": "*"}, {"claim": "P3", "clause": "*"}]},
    {"key": "judge_bed", "wording_source": {"claim": "A2", "clause": "*"}, "members": [{"claim": "A2", "clause": "*"}]},
    {"key": "roses", "wording_source": {"claim": "C2", "clause": "Any discussion of roses"},
     "members": [{"claim": "C2", "clause": "Any discussion of roses"}]},
    {"key": "orchards_soil", "wording_source": {"claim": "C2", "clause": "orchards or soil chemistry"},
     "members": [{"claim": "C2", "clause": "orchards or soil chemistry"}]},
    {"key": "seed_swap_yield", "wording_source": {"claim": "P1", "clause": "*"},
     "members": [{"claim": "P1", "clause": "*"}]},
    {"key": "wintering", "wording_source": {"claim": "P2", "clause": "*"}, "members": [{"claim": "P2", "clause": "*"}]},
]}

ASSIGNMENT = {"categories": [
    {"id": "T1", "name": "Planting and roses", "members": ["A1", "C2", "P1", "P3"]},
    {"id": "T2", "name": "Judging and winter", "members": ["A2", "P2"]},
    {"id": "T3", "name": "Nothing yet", "members": []},
]}


def md_for(layer, claims):
    """The author-from-package markdown shape, evidence lines included."""
    L = [f"# {layer.upper()}", "", "preamble", ""]
    for c in claims:
        L += [f"## {c['id']} {c['name']}{'  (CONTESTED)' if c['contested'] else ''}", "", c["statement"], "",
              f"*Active when:* {c['active_when']}", "", "*Evidence:* " + " ".join(f"[{f}]" for f in c["fact_ids"]), "",
              "provenance: [" + ", ".join(c["fact_ids"]) + "]", ""]
    return "\n".join(L)


@pytest.fixture
def spec_dir(tmp_path):
    d = tmp_path / "spec"
    d.mkdir()
    for layer, cl in LAYERS.items():
        (d / f"{layer}.json").write_text(json.dumps({"layer": layer, "claims": cl}), encoding="utf-8")
        (d / f"{layer}.md").write_text(md_for(layer, cl), encoding="utf-8")
    return d


@pytest.fixture
def inputs(tmp_path):
    d = tmp_path / "inputs"
    d.mkdir()
    write_json(d / "grouping.json", GROUPING)
    write_json(d / "categories.json", ASSIGNMENT)
    return d


def args_for(spec_dir, out, inputs=None, **kw):
    import argparse
    p = crun.build_parser(argparse.ArgumentParser())
    argv = [str(spec_dir), "--out", str(out)]
    if inputs is not None:
        argv += ["--grouping", str(inputs / "grouping.json"), "--categories", str(inputs / "categories.json")]
    for k, v in kw.items():
        flag = "--" + k.replace("_", "-")
        argv += [flag] if v is True else [flag, str(v)]
    return p.parse_args(argv)


def run_all(spec_dir, out, inputs=None, **kw) -> int:
    return crun.execute(args_for(spec_dir, out, inputs, **kw))


def rerun_checks(spec_dir, out):
    docs = {n: (read_json(out / f) if (out / f).exists() else None)
            for n, f in crun.FILES.items() if n != "checks"}
    served = (out / "served.txt").read_bytes().decode("utf-8") if (out / "served.txt").exists() else None
    sst = read_json(out / "served.stamp.json") if (out / "served.stamp.json").exists() else None
    return checks.run(spec_dir, docs, served, sst)


def failed(res):
    return set(res["failed"])


@pytest.fixture
def built(spec_dir, inputs, tmp_path):
    out = tmp_path / "out"
    assert run_all(spec_dir, out, inputs, subject="Sam", possessive="her") == 0
    return out


# ---------------------------------------------------------------- the clean run
def test_clean_run_passes_every_check(built, spec_dir):
    res = read_json(built / "checks.json")
    assert res["passed"], checks.format_checks(res)
    assert res["n_checks"] == 14
    assert rerun_checks(spec_dir, built)["passed"]


def test_every_output_is_stamped(built):
    for f in ("claims.json", "overlap.json", "dedupe.json", "always_on.json", "triggers.json", "categories.json",
              "index.json", "checks.json", "served.stamp.json"):
        st = read_json(built / f)
        st = st if f == "served.stamp.json" else st["stamp"]
        for k in ("stamp_version", "stage", "run_id", "git_commit", "code_sha256", "inputs", "inputs_hash",
                  "params", "model_calls"):
            assert k in st, (f, k)
        assert st["model_calls"] == 0
        assert not Path(st["code_path"]).is_absolute(), st["code_path"]
    assert read_json(built / "served.stamp.json")["served_sha256"] == sha256_text(
        (built / "served.txt").read_bytes().decode("utf-8"))


def test_inputs_hash_stable_across_runs_and_run_id_is_not(spec_dir, inputs, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_all(spec_dir, a, inputs, subject="Sam") == 0
    assert run_all(spec_dir, b, inputs, subject="Sam") == 0
    for f in ("triggers.json", "categories.json", "index.json"):
        sa, sb = read_json(a / f)["stamp"], read_json(b / f)["stamp"]
        assert sa["inputs_hash"] == sb["inputs_hash"], f
        assert payload_hash(read_json(a / f)) == payload_hash(read_json(b / f)), f
    assert (a / "served.txt").read_bytes() == (b / "served.txt").read_bytes()


# ---------------------------------------------------------------- render: exact format
EXPECTED_SERVED = (
    "Sam's specification: the standing claims below apply to every message.\n\n"
    "## C1 SHORT NOTES\n\nThey keep short notes; read brevity as habit.\n\n"
    "*Active when:* Any message, especially watering logs.\n\n"
    "Sam's specification is indexed below by category and by situation; each situation lists the ids of the "
    "claims that apply in that situation. If a situation applies to the current message, fetch those claims "
    "before answering.\n\n"
    "[T1 Planting and roses]\n"
    "- Before planting seeds or bulbs in a bed. -> A1, P3\n"
    "- Any discussion of roses -> C2\n"
    "- Orchards or soil chemistry -> C2\n"
    "- When stating a yield in a seed swap. -> P1\n\n"
    "[T2 Judging and winter]\n"
    "- When judging any bed or border. -> A2\n"
    "- When wintering -> P2\n\n"
    "To fetch claims from the behavioural specification of Sam, the user, reply with exactly one line of the "
    "form `get_claims: [id1, id2, ...]` and nothing else; the claim text will then be sent to you and you "
    "answer the user's message. Fetch when her preferences, patterns or judgement are relevant. Otherwise "
    "answer the message directly."
)


def test_render_exact_format_lf_and_empty_category_left_out(built):
    raw = (built / "served.txt").read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8") == EXPECTED_SERVED
    cats = read_json(built / "categories.json")
    assert cats["empty_categories"] == ["T3"]
    assert "[T3" not in EXPECTED_SERVED


def test_render_matches_the_layout_eval_formula(built):
    """The 9/29 layout eval built its LINES arm as: resident header + always-on blocks, index header,
    one [id name] block per category of '- wording -> ids' lines, fetch instruction, joined by blank lines.
    Rebuild that formula independently from the stage files and compare."""
    cl = {c["id"]: c["block"] for c in read_json(built / "claims.json")["claims"]}
    ao = read_json(built / "always_on.json")["claims"]
    tr = {t["id"]: t for t in read_json(built / "triggers.json")["triggers"]}
    cats = read_json(built / "categories.json")["categories"]
    tpl = read_json(built / "index.json")["templates"]
    ao_block = tpl["resident_header"] + "\n\n" + "\n\n".join(cl[c] for c in ao)
    blocks = [f"[{c['id']} {c['name']}]\n" + "\n".join(f"- {tr[t]['wording'].rstrip()} -> {', '.join(tr[t]['claims'])}"
                                                        for t in c["triggers"]) for c in cats if c["triggers"]]
    expect = ao_block + "\n\n" + tpl["index_header"] + "\n\n" + "\n\n".join(blocks) + "\n\n" + tpl["fetch_instruction"]
    assert (built / "served.txt").read_bytes().decode("utf-8") == expect


def test_unnamed_templates_carry_no_name(spec_dir, inputs, tmp_path):
    out = tmp_path / "o"
    assert run_all(spec_dir, out, inputs) == 0
    t = (out / "served.txt").read_text(encoding="utf-8")
    assert t.startswith("The user's specification: ")
    assert "{subject}" not in t and "{possessive}" not in t and "their preferences" in t


def test_index_carries_what_the_pull_tool_needs(built):
    ix = read_json(built / "index.json")
    c2 = ix["claims"]["C2"]
    assert c2["text"].startswith("## C2 FORMER NURSERY HAND  (CONTESTED)")
    assert c2["fact_ids"] == ["F-c2", "F-a1"] and c2["contested"] and c2["contested_note"]
    assert len(c2["triggers"]) == 2 and c2["categories"] == ["T1"]
    assert ix["claims"]["C1"]["always_on"] and ix["always_on"] == ["C1"]
    assert ix["served_sha256"] == sha256_text((built / "served.txt").read_bytes().decode("utf-8"))


# ---------------------------------------------------------------- fail first: each check goes red
def _mutated_grouping(fn):
    g = copy.deepcopy(GROUPING)
    fn(g)
    return g


def _run_with_grouping(spec_dir, inputs, tmp_path, g, name):
    write_json(inputs / "grouping.json", g)
    out = tmp_path / name
    rc = run_all(spec_dir, out, inputs)
    return rc, read_json(out / "checks.json")


def test_red_drop_the_only_edge_of_a_singleton_trigger(spec_dir, inputs, tmp_path):
    g = _mutated_grouping(lambda g: g["triggers"].__delitem__(4))  # seed_swap_yield, P1's only trigger
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, g, "m1")
    assert rc == 1 and "K05" in failed(res)
    assert next(r for r in res["checks"] if r["id"] == "K05")["detail"] == ["P1"]


def test_red_change_one_letter_of_a_clause(spec_dir, inputs, tmp_path):
    def f(g):
        g["triggers"][3]["members"][0]["clause"] = "orchards or soil chemistrz"
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, _mutated_grouping(f), "m2")
    assert rc == 1 and {"K03", "K08"} <= failed(res)


def test_red_hang_an_always_on_claim_off_a_trigger(spec_dir, inputs, tmp_path):
    def f(g):
        g["triggers"][0]["members"].append({"claim": "C1", "clause": "*"})
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, _mutated_grouping(f), "m3")
    assert rc == 1 and "K06" in failed(res)


def test_red_drop_one_clause_of_a_split_claim(spec_dir, inputs, tmp_path):
    g = _mutated_grouping(lambda g: g["triggers"].__delitem__(3))  # orchards_soil; C2 still reachable
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, g, "m4")
    assert rc == 1 and failed(res) == {"K08"}


def test_red_wording_not_verbatim(spec_dir, inputs, tmp_path):
    def f(g):
        g["triggers"][1]["wording_source"] = {"claim": "A2", "clause": "When judging any bed at all"}
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, _mutated_grouping(f), "m5")
    assert rc == 1 and "K04" in failed(res)


def test_red_wording_source_not_a_member(spec_dir, inputs, tmp_path):
    def f(g):
        g["triggers"][4]["wording_source"] = {"claim": "A2", "clause": "*"}
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, _mutated_grouping(f), "m6")
    assert rc == 1 and "K04" in failed(res)


def test_red_duplicate_edge(spec_dir, inputs, tmp_path):
    def f(g):
        g["triggers"][0]["members"].append({"claim": "A1", "clause": "*"})
    rc, res = _run_with_grouping(spec_dir, inputs, tmp_path, _mutated_grouping(f), "m7")
    assert rc == 1 and "K07" in failed(res)


def test_red_index_statement_changed(built, spec_dir):
    ix = read_json(built / "index.json")
    ix["claims"]["A1"]["text"] = ix["claims"]["A1"]["text"].replace("last frost", "first frost")
    write_json(built / "index.json", ix)
    assert failed(rerun_checks(spec_dir, built)) == {"K10"}


def test_red_renderer_defect_is_caught_without_the_md(spec_dir, inputs, tmp_path, monkeypatch):
    """K10 must not rest on the renderer it checks: a renderer that drops the condition line, used
    by both render and checks, still goes red, with no .md present to catch it through K02."""
    for f in spec_dir.glob("*.md"):
        f.unlink()
    monkeypatch.setattr(spec, "render_block", lambda c: "## %s %s\n\n%s" % (c["id"], c["name"], c["statement"]))
    out = tmp_path / "defect"
    assert run_all(spec_dir, out, inputs) == 1
    assert "K10" in failed(read_json(out / "checks.json"))


def test_red_index_fact_id_dropped(built, spec_dir):
    ix = read_json(built / "index.json")
    ix["claims"]["C2"]["fact_ids"] = ["F-a1"]
    write_json(built / "index.json", ix)
    res = rerun_checks(spec_dir, built)
    assert failed(res) == {"K11"}
    assert next(r for r in res["checks"] if r["id"] == "K11")["detail"]["lost"] == ["F-c2"]


def test_red_served_text_edited(built, spec_dir):
    p = built / "served.txt"
    p.write_bytes(p.read_bytes().replace(b"-> A1, P3", b"-> A1"))
    assert {"K12", "K14"} <= failed(rerun_checks(spec_dir, built))


def test_red_served_text_names_an_unknown_id(built, spec_dir):
    p = built / "served.txt"
    t = p.read_bytes().decode("utf-8").replace("- When wintering -> P2", "- When wintering -> P2, P9")
    p.write_bytes(t.encode("utf-8"))
    ix = read_json(built / "index.json")
    ix["served_sha256"] = sha256_text(t)
    write_json(built / "index.json", ix)
    res = rerun_checks(spec_dir, built)
    assert "K12" in failed(res)
    assert "P9" in json.dumps(next(r for r in res["checks"] if r["id"] == "K12")["detail"])


def test_red_layer_changed_after_the_claims_stage(built, spec_dir):
    f = spec_dir / "core.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["claims"][1]["statement"] += " Edited."
    f.write_text(json.dumps(d), encoding="utf-8")
    assert {"K01", "K10"} <= failed(rerun_checks(spec_dir, built))


def test_red_md_and_json_disagree(spec_dir, inputs, tmp_path):
    f = spec_dir / "predictions.md"
    f.write_text(f.read_text(encoding="utf-8").replace("as questions", "as statements"), encoding="utf-8")
    out = tmp_path / "md"
    assert run_all(spec_dir, out, inputs) == 1
    res = read_json(out / "checks.json")
    assert failed(res) == {"K02"}
    assert next(r for r in res["checks"] if r["id"] == "K02")["detail"]["predictions"]["block_mismatch"] == ["P1"]


def test_red_category_counts_tampered(built, spec_dir):
    cd = read_json(built / "categories.json")
    cd["categories"][0]["n_facts"] += 1
    write_json(built / "categories.json", cd)
    assert failed(rerun_checks(spec_dir, built)) == {"K09"}


def test_red_trigger_without_a_valid_category(built, spec_dir):
    cd = read_json(built / "categories.json")
    tid = cd["categories"][1]["triggers"][0]
    cd["trigger_category"][tid] = "T9"
    write_json(built / "categories.json", cd)
    assert "K09" in failed(rerun_checks(spec_dir, built))


def test_red_dedupe_not_a_partition(built, spec_dir):
    dd = read_json(built / "dedupe.json")
    dd["groups"][0]["members"].append("P2")
    write_json(built / "dedupe.json", dd)
    assert failed(rerun_checks(spec_dir, built)) == {"K13"}


def test_red_missing_input_fails_rather_than_skips(built, spec_dir):
    (built / "triggers.json").unlink()
    res = rerun_checks(spec_dir, built)
    for k in ("K03", "K04", "K05", "K06", "K07", "K08", "K09", "K14"):
        assert k in failed(res), k
    k03 = next(r for r in res["checks"] if r["id"] == "K03")
    assert "cannot_run" in k03["detail"]


def test_red_stamp_missing(built, spec_dir):
    d = read_json(built / "overlap.json")
    d.pop("stamp")
    write_json(built / "overlap.json", d)
    assert failed(rerun_checks(spec_dir, built)) == {"K14"}


# ---------------------------------------------------------------- stages alone
def test_stage_needs_its_inputs(spec_dir, tmp_path):
    out = tmp_path / "alone"
    assert run_all(spec_dir, out, stages="triggers") == 1
    assert not (out / "triggers.json").exists()


def test_stage_rerun_alone_replaces_only_its_file(built, spec_dir, inputs):
    before = (built / "triggers.json").read_bytes()
    assert crun.execute(args_for(spec_dir, built, inputs, stages="always_on", always_on_rule="explicit",
                                 always_on_claims="C1,P2")) == 0
    assert read_json(built / "always_on.json")["claims"] == ["C1", "P2"]
    assert (built / "triggers.json").read_bytes() == before


def test_identity_grouping_is_lossless_and_merges_identical_conditions(spec_dir, tmp_path):
    out = tmp_path / "id"
    assert run_all(spec_dir, out) == 0
    tr = read_json(out / "triggers.json")
    assert tr["source"] == "identity"
    shared = [t for t in tr["triggers"] if set(t["claims"]) == {"A1", "P3"}]
    assert len(shared) == 1
    assert read_json(out / "checks.json")["passed"]
    assert [c["name"] for c in read_json(out / "categories.json")["categories"]] == ["Situations"]


# ---------------------------------------------------------------- always-on rules
def test_always_on_literal_rule():
    cd = {"claims": [
        {"id": "X1", "active_when": "Any message, especially drafts."},
        {"id": "X2", "active_when": "Any messages about gardening."},
        {"id": "X3", "active_when": "Anything about money."},
        {"id": "X4", "active_when": "nearly all replies to them."},
        {"id": "X5", "active_when": "Task requests across any domain."},
        {"id": "X6", "active_when": "When wintering, always."},
    ]}
    assert always_on.build(cd)["claims"] == ["X1", "X4", "X5"]
    assert always_on.build(cd, phrases=("Anything",))["claims"] == ["X3"]


def test_always_on_fire_rate_rule():
    cd = {"claims": [{"id": "X1", "active_when": "a"}, {"id": "X2", "active_when": "b"}]}
    assert always_on.build(cd, rule="fire_rate", rates={"X1": 0.81, "X2": 0.79})["claims"] == ["X1"]
    with pytest.raises(ValueError):
        always_on.build(cd, rule="fire_rate", rates={"X9": 1.0})
    with pytest.raises(ValueError):
        always_on.build(cd, rule="fire_rate")


# ---------------------------------------------------------------- categories rule
def _tdoc(*trigs):
    return {"triggers": [{"id": f"TG{i}", "key": k, "claims": cl, "wording_source": ws}
                         for i, (k, cl, ws) in enumerate(trigs, 1)]}


def test_category_majority_tie_goes_to_wording_source():
    cd = {"claims": [{"id": i, "fact_ids": []} for i in ("A", "B", "C")]}
    asg = {"categories": [{"id": "T1", "name": "one", "members": ["A"]},
                          {"id": "T2", "name": "two", "members": ["B", "C"]}]}
    r = categories.build(cd, _tdoc(("maj", ["A", "B", "C"], "A"), ("tie", ["A", "B"], "B"), ("tie2", ["B", "A"], "A")),
                         asg)
    assert r["trigger_category"] == {"TG1": "T2", "TG2": "T2", "TG3": "T1"}
    assert r["order"] == ["TG3", "TG1", "TG2"]  # stable within category


def test_category_override_and_undecided():
    cd = {"claims": [{"id": i, "fact_ids": []} for i in ("A", "B")]}
    asg = {"categories": [{"id": "T1", "name": "one", "members": ["A"]}], "trigger_overrides": {"x": "T1"}}
    r = categories.build(cd, _tdoc(("x", ["B"], "B"), ("y", ["B"], "B")), asg)
    assert r["trigger_category"] == {"TG1": "T1", "TG2": None}
    assert r["undecided_triggers"] == ["TG2"] and r["unassigned_claims"] == ["B"]


def test_category_thin_flag():
    cd = {"claims": [{"id": "A", "fact_ids": ["f1"]}, {"id": "B", "fact_ids": ["f2", "f3"]}]}
    asg = {"categories": [{"id": "T1", "name": "one", "members": ["A", "B"]}]}
    r = categories.build(cd, _tdoc(("x", ["A", "B"], "A")), asg, thin_claims=2, thin_facts=3)
    assert not r["categories"][0]["thin"]
    r = categories.build(cd, _tdoc(("x", ["A", "B"], "A")), asg, thin_claims=2, thin_facts=4)
    assert r["thin_categories"] == ["T1"]


# ---------------------------------------------------------------- dedupe
def test_dedupe_bases(spec_dir):
    cd = spec.build(spec_dir)
    od = overlap.build(cd)
    r = dedupe.build(cd, od, basis="evidence", jaccard_min=1.0)
    assert [g["members"] for g in r["groups"] if len(g["members"]) > 1] == [["A1", "P3"]]
    assert set(r["claim_to_group"]) == {c["id"] for c in cd["claims"]}
    one_order = [{"a": "A2", "b": "P2", "label": "SAME"}]
    assert dedupe.build(cd, basis="judgements", judgements=one_order)["counts"]["multi_member_groups"] == 0
    both = one_order + [{"a": "P2", "b": "A2", "label": "SAME"}]
    assert dedupe.build(cd, basis="judgements", judgements=both)["counts"]["multi_member_groups"] == 1
    with pytest.raises(ValueError):
        dedupe.build(cd, basis="external", external={"source_to_group": {"A1": "M1"}})


def test_judge_tasks_are_blind_and_split_orders(spec_dir):
    cd = spec.build(spec_dir)
    pairs = [(p["a"], p["b"]) for p in overlap.build(cd)["pairs"]]
    tasks = overlap.judge_tasks(pairs, spec.by_id(cd), batch=2)
    assert sum(len(t["items"]) for t in tasks) == 2 * len(pairs)
    for t in tasks:
        assert len({it["pair"] for it in t["items"]}) == len(t["items"])
        for cid in ("A1", "C2", "P3", "COMMIT ONLY", "FORMER NURSERY HAND"):
            assert cid not in t["prompt"]


# ---------------------------------------------------------------- port, guard, isolation
def test_port_recovers_wording_source_and_drops_category():
    ti = {"triggers": [{"id": "TG01", "key": "k", "wording": "Orchards or soil", "wording_source": "C2",
                        "category": "T4", "members": [
                            {"claim": "C2", "clause": "roses", "whole_condition": False},
                            {"claim": "C2", "clause": "orchards or soil", "whole_condition": False},
                            {"claim": "P1", "clause": "When x.", "whole_condition": True}]}]}
    g = port.grouping_from_trigger_index(ti)["triggers"][0]
    assert g["wording_source"] == {"claim": "C2", "clause": "orchards or soil"}
    assert g["members"][2] == {"claim": "P1", "clause": "*"} and "category" not in g
    ti["triggers"][0]["members"].append({"claim": "C2", "clause": "Orchards or soil", "whole_condition": False})
    with pytest.raises(ValueError):
        port.grouping_from_trigger_index(ti)


def test_guard_refuses_spec_dir_and_data_dirs(spec_dir, tmp_path):
    with pytest.raises(ValueError):
        guard_out(spec_dir / "out", [spec_dir])
    data = tmp_path / "corpus" / "data"
    (data / "identity_layers").mkdir(parents=True)
    with pytest.raises(ValueError):
        guard_out(data / "consolidated", [spec_dir])
    assert run_all(spec_dir, spec_dir / "out") == 2
    assert not (spec_dir / "out").exists()


def test_package_imports_no_model_client():
    code = ("import sys; import baselayer.consolidation.run, baselayer.consolidation.port; "
            "bad=[m for m in ('anthropic','openai','baselayer.api_client','baselayer.llm_provider') if m in sys.modules]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT),
                       env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_registers_consolidate(spec_dir, inputs, tmp_path):
    out = tmp_path / "cli"
    r = subprocess.run([sys.executable, "-m", "baselayer.cli", "consolidate", str(spec_dir), "--out", str(out),
                        "--grouping", str(inputs / "grouping.json"), "--categories", str(inputs / "categories.json")],
                       capture_output=True, text=True, cwd=str(ROOT),
                       env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert read_json(out / "checks.json")["passed"]
