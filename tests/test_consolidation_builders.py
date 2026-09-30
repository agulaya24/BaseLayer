"""Consolidation builders (duplicate judge, trigger grouper, category builder) and their
backends, on a synthetic spec with a fake backend. No model, no network, no API key.

Each builder's own checks are shown to FAIL first: a scripted bad reply (a clause that
is not a substring, a split that leaves a span uncovered, answers out of order, a
missing line, a limit error) must be rejected or repaired, and the repair must be
recorded, before a clean run is trusted. The builders' outputs then go through
`baselayer consolidate`, whose 14 checks must pass on them.
"""
from __future__ import annotations

import json
import re
import types
from pathlib import Path

import pytest

from baselayer.consolidation import backends as be
from baselayer.consolidation import build as cbuild
from baselayer.consolidation import categorize, grouper, judge, overlap, spec
from baselayer.consolidation import always_on as ao_mod
from baselayer.consolidation import triggers as trig_mod
from baselayer.consolidation.common import read_json, write_json
from tests.test_consolidation import LAYERS, failed, md_for, rerun_checks, run_all


@pytest.fixture
def spec_dir(tmp_path):
    d = tmp_path / "spec"
    d.mkdir()
    for layer, cl in LAYERS.items():
        (d / f"{layer}.json").write_text(json.dumps({"layer": layer, "claims": cl}), encoding="utf-8")
        (d / f"{layer}.md").write_text(md_for(layer, cl), encoding="utf-8")
    return d


@pytest.fixture
def cd(spec_dir):
    return spec.build(spec_dir)


@pytest.fixture
def aod(cd):
    return ao_mod.build(cd)


def runner_for(fn, tmp_path, name="calls.jsonl", **kw):
    b = be.FakeBackend(fn)
    return be.CallRunner(b, be.CallStore(tmp_path / name), workers=1, backoff_s=kw.pop("backoff_s", (0, 0)),
                         sleep=lambda s: None, log=lambda *a: None, **kw), b


# ---------------------------------------------------------------- scripted model
def lines_of(prompt, prefix):
    return re.findall(rf"^({prefix}\d+): (.*)$", prompt, flags=re.M)


SPLITS = {"Any discussion of roses, orchards or soil chemistry.": ["Any discussion of roses",
                                                                       "orchards or soil chemistry"]}


def fake_model(prompt, *, splits=SPLITS):
    if prompt.startswith("Below are") and "conditions." in prompt.split("\n", 1)[0]:
        return json.dumps({s: splits.get(t, [t]) for s, t in lines_of(prompt, "S")})
    if "numbered lines" in prompt.split("\n", 1)[0]:
        by = {}
        for k, t in lines_of(prompt, "K"):
            by.setdefault(t.strip().lower(), []).append(k)
        return json.dumps({"groups": [{"members": v, "wording": v[-1]} for v in by.values()]})
    if "situation lines" in prompt.split("\n", 1)[0]:
        rs = [r for r, _ in lines_of(prompt, "R")]
        return json.dumps({"categories": [
            {"name": "Planting and pruning", "description": "Planting, seeds and pruning.", "members": rs[::2]},
            {"name": "Everything else", "description": "The rest.", "members": rs[1::2]}]})
    if prompt.startswith(overlap.JUDGE_HEAD):
        n = len(re.findall(r"^ITEM \d+$", prompt, flags=re.M))
        return json.dumps([{"item": i, "label": "SAME", "x_in_y": 80, "y_in_x": 80} for i in range(1, n + 1)])
    raise AssertionError("unexpected prompt: " + prompt[:80])


# ---------------------------------------------------------------- judge
def test_judge_prompt_is_the_prototype_format(cd):
    cmap = spec.by_id(cd)
    items = [{"x": "A1", "y": "P3"}, {"x": "C2", "y": "P1"}]
    fmt = lambda c: f'{c["statement"]}\n  Applies when: {c["active_when"]}'  # noqa: E731
    expect = overlap.JUDGE_HEAD + "\n" + "\n\n".join(
        f"ITEM {i}\nX: {fmt(cmap[it['x']])}\nY: {fmt(cmap[it['y']])}" for i, it in enumerate(items, 1)) + "\n"
    assert overlap.judge_prompt(items, cmap) == expect


def test_judge_both_orders_blind_and_feeds_dedupe(cd, tmp_path):
    from baselayer.consolidation import dedupe
    od = overlap.build(cd)
    r, b = runner_for(fake_model, tmp_path)
    doc = judge.build(cd, od, r, batch=2)
    npairs = len(od["pairs"])
    assert doc["summary"]["judged_items"] == 2 * npairs and not doc["unjudged_pairs"]
    for p in b.prompts:  # blind: no id, no claim name
        for tok in ("A1", "C2", "P3", "COMMIT ONLY", "FORMER NURSERY HAND"):
            assert tok not in p
    orders = {}
    for row in doc["judgements"]:
        orders.setdefault(row["pair"], set()).add((row["order"], row["task"]))
    for v in orders.values():  # both orders, in different calls
        assert {o for o, _ in v} == {"ab", "ba"} and len({t for _, t in v}) == 2
    path = tmp_path / "j.json"
    write_json(path, {"stamp": {}, **doc})
    dd = dedupe.build(cd, od, basis="judgements", judgements=overlap.load_judgements(path))
    assert dd["counts"]["multi_member_groups"] >= 1


def test_judge_rejects_bad_replies_and_never_records_them(cd, tmp_path):
    od = overlap.build(cd)
    bad = {"n": 0}

    def fn(prompt):
        bad["n"] += 1
        n = len(re.findall(r"^ITEM \d+$", prompt, flags=re.M))
        if bad["n"] == 1:
            return json.dumps([{"item": 1, "label": "SAME"}] * (n + 1))  # wrong length
        if bad["n"] == 2:
            return json.dumps([{"item": i, "label": "MAYBE"} for i in range(1, n + 1)])  # bad label
        if bad["n"] == 3:
            return json.dumps([{"item": n + 1 - i, "label": "SAME"} for i in range(1, n + 1)]) if n > 1 else "no"
        return "not json"
    r, _ = runner_for(fn, tmp_path, retries=2)
    doc = judge.build(cd, od, r, batch=2)
    assert doc["summary"]["judged_items"] == 0 and len(doc["unjudged_pairs"]) == len(od["pairs"])
    assert r.failed
    cp = tmp_path / "calls.jsonl"
    assert not cp.exists() or not cp.read_text().strip()
    assert (tmp_path / "calls.errors.jsonl").exists()


# ---------------------------------------------------------------- grouper
def test_accept_split_red_cases():
    cond = "Any discussion of roses, orchards or soil chemistry."
    # not a substring -> whole condition
    assert grouper.accept_split(cond, ["rose talk", "soil chemistry"]) == (["*"], "a clause is not a substring of the condition")
    # a content span left uncovered -> whole condition
    got, why = grouper.accept_split(cond, ["Any discussion of roses", "soil chemistry"])
    assert got == ["*"] and "uncovered" in why
    # case- and space-folded proposals are stored as the SOURCE slice
    got, why = grouper.accept_split(cond, ["any  discussion of roses", "Orchards or soil chemistry"])
    assert why is None and got == ["Any discussion of roses", "orchards or soil chemistry"]
    assert all(g in cond for g in got)
    # one clause -> "*"
    assert grouper.accept_split(cond, [cond]) == (["*"], None)


def test_grouper_output_passes_every_trigger_check(spec_dir, cd, aod, tmp_path):
    r, b = runner_for(fake_model, tmp_path)
    doc = grouper.build(cd, aod, r)
    assert doc["splits"]["C2"] == ["Any discussion of roses", "orchards or soil chemistry"]
    assert not doc["split_fallbacks"]
    for p in b.prompts:
        for tok in ("A1", "C2", "COMMIT ONLY"):
            assert tok not in p
    # A1 and P3 share a condition, so they share a trigger; C2 sits on two triggers
    td = trig_mod.build(cd, aod, doc)
    shared = [t for t in td["triggers"] if set(t["claims"]) == {"A1", "P3"}]
    assert len(shared) == 1
    assert len(td["claim_to_triggers"]["C2"]) == 2
    keys = [t["key"] for t in doc["triggers"]]
    assert len(keys) == len(set(keys))
    g = tmp_path / "grouping.json"
    write_json(g, doc)
    out = tmp_path / "out"
    rc = run_all(spec_dir, out, None, grouping=g)
    res = rerun_checks(spec_dir, out)
    assert rc == 0 and not failed(res), res["failed"]


def test_grouper_repairs_are_recorded_and_checks_still_hold(spec_dir, cd, aod, tmp_path):
    bad_splits = {"Any discussion of roses, orchards or soil chemistry.": ["rose stuff", "soil"]}

    def fn(prompt):
        if "numbered lines" in prompt.split("\n", 1)[0]:
            ks = [k for k, _ in lines_of(prompt, "K")]
            # drops the last line, repeats the first, names a wording outside its group
            return json.dumps({"groups": [{"members": ks[:-1], "wording": "K999"}, {"members": [ks[0]]}]})
        return fake_model(prompt, splits=bad_splits)
    r, _ = runner_for(fn, tmp_path)
    doc = grouper.build(cd, aod, r)
    assert doc["split_fallbacks"] == {"C2": "a clause is not a substring of the condition"}
    rep = doc["group_repairs"]
    assert len(rep["missing_lines"]) == 1 and len(rep["repeated_lines"]) == 1 and rep["wording_not_member"] == 1
    g = tmp_path / "grouping.json"
    write_json(g, doc)
    out = tmp_path / "out"
    assert run_all(spec_dir, out, None, grouping=g) == 0
    assert not failed(rerun_checks(spec_dir, out))


def test_an_unchecked_split_would_fail_the_trigger_checks(spec_dir, cd, aod, tmp_path):
    """The red run behind accept_split: the same proposal, written without it, goes red
    on K03 (not a substring) and K08 (span uncovered)."""
    grouping = {"triggers": [
        {"key": "a", "wording_source": {"claim": "A1", "clause": "*"},
         "members": [{"claim": "A1", "clause": "*"}, {"claim": "P3", "clause": "*"}]},
        {"key": "b", "wording_source": {"claim": "A2", "clause": "*"}, "members": [{"claim": "A2", "clause": "*"}]},
        {"key": "c", "wording_source": {"claim": "C2", "clause": "rose stuff"},
         "members": [{"claim": "C2", "clause": "rose stuff"}]},
        {"key": "d", "wording_source": {"claim": "P1", "clause": "*"}, "members": [{"claim": "P1", "clause": "*"}]},
        {"key": "e", "wording_source": {"claim": "P2", "clause": "*"}, "members": [{"claim": "P2", "clause": "*"}]}]}
    g = tmp_path / "grouping.json"
    write_json(g, grouping)
    out = tmp_path / "out"
    assert run_all(spec_dir, out, None, grouping=g) == 1
    assert {"K03", "K04", "K08"} <= failed(rerun_checks(spec_dir, out))


# ---------------------------------------------------------------- categories
def _triggers(cd, aod, tmp_path):
    r, _ = runner_for(fake_model, tmp_path, name="g.jsonl")
    return trig_mod.build(cd, aod, grouper.build(cd, aod, r))


def test_categorize_overrides_every_trigger_and_partitions_claims(spec_dir, cd, aod, tmp_path):
    td = _triggers(cd, aod, tmp_path)
    r, b = runner_for(fake_model, tmp_path)
    doc = categorize.build(cd, td, r)
    assert set(doc["trigger_overrides"]) == {t["key"] for t in td["triggers"]}
    members = [m for c in doc["categories"] for m in c["members"]]
    assert len(members) == len(set(members))
    assert all(c["description"] for c in doc["categories"])
    assert {c["id"] for c in doc["coverage"]} == {c["id"] for c in doc["categories"]}
    assert "thin" in doc["gaps"] and not doc["gaps"]["unplaced"]
    for p in b.prompts:
        assert "A1" not in p and "COMMIT ONLY" not in p
    # the stage reproduces the builder's placement exactly, and K09 passes
    from baselayer.consolidation import categories as cat_mod
    cat = cat_mod.build(cd, td, doc)
    assert cat["trigger_category"] == doc["trigger_categories"]
    g, c = tmp_path / "grouping.json", tmp_path / "categories.json"
    r2, _ = runner_for(fake_model, tmp_path, name="g.jsonl")
    write_json(g, grouper.build(cd, aod, r2))
    write_json(c, doc)
    out = tmp_path / "out"
    assert run_all(spec_dir, out, None, grouping=g, categories=c) == 0
    served = (out / "served.txt").read_text(encoding="utf-8")
    assert "[T1 " in served and "Planting, seeds and pruning." not in served  # names only


def test_categorize_missing_trigger_goes_to_flagged_unplaced(cd, aod, tmp_path):
    td = _triggers(cd, aod, tmp_path)

    def fn(prompt):
        rs = [r for r, _ in lines_of(prompt, "R")]
        return json.dumps({"categories": [{"name": "All but one", "description": "d", "members": rs[:-1] + ["R99"]}]})
    r, _ = runner_for(fn, tmp_path)
    doc = categorize.build(cd, td, r)
    assert doc["gaps"]["unplaced"] == [doc["categories"][-1]["id"]]
    assert doc["categories"][-1]["name"] == "Unplaced" and len(doc["repairs"]["missing_triggers"]) == 1
    assert doc["repairs"]["unknown_ids"] == ["R99"]


def test_categorize_refuses_duplicate_trigger_keys(cd, aod, tmp_path):
    td = _triggers(cd, aod, tmp_path)
    td["triggers"][1]["key"] = td["triggers"][0]["key"]
    r, _ = runner_for(fake_model, tmp_path)
    with pytest.raises(ValueError):
        categorize.build(cd, td, r)


# ---------------------------------------------------------------- runner and checkpoint
def test_checkpoint_resumes_without_calls_and_refuses_a_changed_prompt(tmp_path):
    r, b = runner_for(lambda p: '{"ok": 1}', tmp_path)
    calls = [{"key": "k1", "prompt": "hello", "max_tokens": 10}, {"key": "k2", "prompt": "world", "max_tokens": 10}]
    parse = be.parse_json
    assert set(r.run(calls, parse)) == {"k1", "k2"} and r.new_calls == 2
    r2, b2 = runner_for(lambda p: pytest.fail("a checkpointed call was sent again"), tmp_path)
    assert set(r2.run(calls, parse)) == {"k1", "k2"} and r2.replayed == 2 and not b2.prompts
    with pytest.raises(RuntimeError, match="prompt changed"):
        r2.run([{"key": "k1", "prompt": "HELLO", "max_tokens": 10}], parse)
    # a torn last line is ignored and does not swallow the next record
    p = tmp_path / "calls.jsonl"
    p.write_bytes(p.read_bytes() + b'{"key": "k3", "prom')
    r3, _ = runner_for(lambda p: '{"ok": 2}', tmp_path)
    assert set(r3.run([{"key": "k3", "prompt": "x", "max_tokens": 1}], parse)) == {"k3"}
    assert len([ln for ln in p.read_text().splitlines() if ln.startswith('{"key": "k3", "prompt_sha"')]) == 1


def test_a_limit_is_backed_off_and_never_recorded(tmp_path):
    seq = [be.Reply(text=None, error="Claude AI usage limit reached", limit=True), '{"ok": 1}']
    r, b = runner_for(lambda p: seq.pop(0), tmp_path, backoff_s=(0, 0))
    out = r.run([{"key": "k", "prompt": "p", "max_tokens": 1}], be.parse_json)
    assert out["k"]["parsed"] == {"ok": 1} and len(r.state["limit_events"]) == 1
    recs = [json.loads(ln) for ln in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert len(recs) == 1 and recs[0]["text"] == '{"ok": 1}'


def test_a_persistent_limit_stops_cleanly(tmp_path):
    lim = be.Reply(text=None, error="You've hit your limit", limit=True)
    r, _ = runner_for(lambda p: lim, tmp_path, backoff_s=(0, 0))
    with pytest.raises(be.UsageLimitStop):
        r.run([{"key": "k", "prompt": "p", "max_tokens": 1}], be.parse_json)
    assert not (tmp_path / "calls.jsonl").exists() or not (tmp_path / "calls.jsonl").read_text().strip()


def test_limit_text_is_recognised():
    for s in ("Claude AI usage limit reached|1759000000", "You've hit your limit · resets 3pm", "429 Too Many Requests",
              "overloaded_error"):
        assert be.LIMIT_RE.search(s)
    assert not be.LIMIT_RE.search("The reply did not parse")


# ---------------------------------------------------------------- API backend (no network)
class FakeClient:
    def __init__(self, blocks, stop="end_turn"):
        self.sent = []
        self.messages = types.SimpleNamespace(create=self._create)
        self.blocks, self.stop = blocks, stop

    def _create(self, **kw):
        self.sent.append(kw)
        return types.SimpleNamespace(content=self.blocks, stop_reason=self.stop, model=kw["model"],
                                     usage=types.SimpleNamespace(input_tokens=1000, output_tokens=200))


def test_api_backend_refuses_before_any_client_exists(monkeypatch):
    from baselayer.distillation import spend
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    monkeypatch.delenv("BASELAYER_RATES_CONFIRMED", raising=False)
    made = []
    b = be.ApiBackend("claude-opus-5", client_factory=lambda: made.append(1))
    with pytest.raises(spend.RatesNotConfirmed):
        b.prepare([{"prompt_chars": 1000, "max_tokens": 100}])
    b = be.ApiBackend("claude-opus-5", rates_confirmed=spend.RATES_AS_OF, client_factory=lambda: made.append(1))
    with pytest.raises(spend.SpendNotConfirmed):
        b.prepare([{"prompt_chars": 1000, "max_tokens": 100}])
    b = be.ApiBackend("claude-opus-5", rates_confirmed=spend.RATES_AS_OF, confirm_spend=0.0001,
                      client_factory=lambda: made.append(1))
    with pytest.raises(spend.SpendNotConfirmed):
        b.prepare([{"prompt_chars": 100000, "max_tokens": 100}])
    assert made == []
    b = be.ApiBackend("claude-opus-5", client_factory=lambda: made.append(1))
    with pytest.raises(RuntimeError, match="priced first"):
        b.complete("x", 10)
    assert made == []


def test_api_backend_prices_from_spend_table_and_caps_each_call():
    from baselayer.distillation import spend
    fc = FakeClient([types.SimpleNamespace(type="thinking", thinking=""), types.SimpleNamespace(type="text", text='{"a": 1}')])
    b = be.ApiBackend("claude-opus-5", rates_confirmed=spend.RATES_AS_OF, confirm_spend=1.0, client_factory=lambda: fc)
    est = b.prepare([{"prompt_chars": 3500, "max_tokens": 1000}])
    assert est["rates"]["in"] == spend.RATES_PER_MTOK["claude-opus-5"][0] and est["ceiling_usd"] == 1.0
    r = b.complete("p" * 3500, 1000)
    assert r.text == '{"a": 1}' and r.error is None  # thinking block first, text joined by type
    assert b.guard.calls == 1 and b.guard.spent_usd > 0
    b.guard.ceiling_usd = b.guard.spent_usd  # the next call's worst case no longer fits
    with pytest.raises(spend.SpendCeilingExceeded):
        b.complete("p" * 3500, 1000)
    assert len(fc.sent) == 1


def test_api_backend_reports_refusal_and_rate_limit():
    from baselayer.distillation import spend
    fc = FakeClient([], stop="refusal")
    b = be.ApiBackend("claude-opus-5", rates_confirmed=spend.RATES_AS_OF, confirm_spend=1.0, client_factory=lambda: fc)
    b.prepare([{"prompt_chars": 10, "max_tokens": 10}])
    assert b.complete("x", 10).error == "refusal"

    class RateLimitError(Exception):
        status_code = 429

    def boom(**kw):
        raise RateLimitError("rate limited")
    fc.messages = types.SimpleNamespace(create=boom)
    r = b.complete("x", 10)
    assert r.limit and r.text is None


# ---------------------------------------------------------------- CLI backend (no child launched)
def test_cli_backend_isolation_flags_and_probe_gate(tmp_path, monkeypatch):
    import sys
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    b = be.ClaudeCliBackend("opus", cwd, tmp_path / "work", [tmp_path / "repo"], binary=sys.executable)
    cmd = b.command()
    for flag in ("--safe-mode", "--no-session-persistence", "--strict-mcp-config", "--tools"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert Path(cmd[cmd.index("--mcp-config") + 1]).is_absolute()  # the child's cwd differs from ours
    assert json.loads(cmd[cmd.index("--settings") + 1])["disableAllHooks"] is True
    with pytest.raises(RuntimeError, match="probe"):
        b.prepare([{"prompt_chars": 1, "max_tokens": 1}])
    from baselayer.verification.raters import child_env
    e = child_env({"ANTHROPIC_API_KEY": "x", "ANTHROPIC_AUTH_TOKEN": "y", "PATH": "p"})
    assert "ANTHROPIC_API_KEY" not in e and "ANTHROPIC_AUTH_TOKEN" not in e and e["BASELAYER_SPEC_INJECT"] == "0"
    # the probe runs through the real complete() (a scripted child process): the spec-injection
    # canary in the child's answer makes it unclean, and prepare() refuses
    sent = []

    def fake_run(cmd, input=None, env=None, cwd=None, **kw):
        sent.append({"cmd": cmd, "env": env, "cwd": cwd})
        if "--version" in cmd:
            return types.SimpleNamespace(stdout="9.9.9 (Claude Code)", stderr="", returncode=0)
        return types.SimpleNamespace(stdout=json.dumps({"result": answer[0], "is_error": False,
                                                        "modelUsage": {"claude-opus-5-5": {}}}),
                                     stderr="", returncode=0)
    monkeypatch.setattr(be.subprocess, "run", fake_run)
    answer = ['{"people_named": [], "project_instructions": "' + be.SPEC_INJECTION_CANARY + '"}']
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    res = b.run_probe([], tmp_path / "probe.json")
    assert res["clean"] is False and res["canaries_found"] == 1
    assert "ANTHROPIC_API_KEY" not in sent[0]["env"] and sent[0]["env"]["BASELAYER_SPEC_INJECT"] == "0"
    assert sent[0]["cwd"] == b.cwd and "--safe-mode" in sent[0]["cmd"]
    with pytest.raises(RuntimeError):
        b.prepare([{"prompt_chars": 1, "max_tokens": 1}])
    answer[0] = '{"people_named": []}'
    assert b.run_probe(["Somebody"], tmp_path / "probe.json")["clean"] is True
    assert b.complete("x").model == "claude-opus-5-5"
    assert b.prepare([{"prompt_chars": 1, "max_tokens": 1}])["usd"] == 0.0


def test_cli_cwd_inside_a_project_is_refused(tmp_path):
    import sys
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "CLAUDE.md").write_text("x")
    with pytest.raises(ValueError):
        be.ClaudeCliBackend("opus", proj / "sub", tmp_path / "w", [], binary=sys.executable)


# ---------------------------------------------------------------- build CLI
def test_build_cli_plan_only_prices_without_calling(spec_dir, tmp_path, monkeypatch, capsys):
    from baselayer.distillation import spend
    out = tmp_path / "c"
    assert run_all(spec_dir, out, None, stages="claims,overlap,always_on") == 0
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    base = ["judge", "--claims", str(out / "claims.json"), "--overlap", str(out / "overlap.json"),
            "--out", str(tmp_path / "j.json"), "--work", str(tmp_path / "w"), "--backend", "api"]
    assert cbuild.main(base + ["--plan-only"]) == 2  # rates not confirmed: refused
    assert "RATES NOT CONFIRMED" in capsys.readouterr().err
    assert cbuild.main(base + ["--plan-only", "--rates-confirmed", spend.RATES_AS_OF]) == 2  # no ceiling
    assert cbuild.main(base + ["--plan-only", "--rates-confirmed", spend.RATES_AS_OF, "--confirm-spend", "5"]) == 0
    o = capsys.readouterr().out
    assert "plan only: nothing called" in o and "usd" in o
    assert not (tmp_path / "j.json").exists()


def test_build_stamp_carries_backend_and_calls(spec_dir, tmp_path, monkeypatch):
    out = tmp_path / "c"
    assert run_all(spec_dir, out, None, stages="claims,overlap,always_on") == 0
    fb = be.FakeBackend(fake_model)
    monkeypatch.setattr(cbuild, "make_backend", lambda a, work, protected: fb)
    monkeypatch.setattr(fb, "run_probe", lambda cans, p: {"clean": True, "canaries_checked": 1, "canaries_found": 0},
                        raising=False)
    rc = cbuild.main(["group", "--claims", str(out / "claims.json"), "--always-on", str(out / "always_on.json"),
                      "--out", str(tmp_path / "g.json"), "--work", str(tmp_path / "w"), "--backend", "api"])
    assert rc == 0
    d = read_json(tmp_path / "g.json")
    st = d["stamp"]
    assert st["stage"] == "group" and st["model_calls"] == 2 and st["backend"]["backend"] == "fake"
    assert st["calls"]["new_calls"] == 2 and "always_on.json" in st["inputs"]
    rc = cbuild.main(["group", "--claims", str(out / "claims.json"), "--always-on", str(out / "always_on.json"),
                      "--out", str(tmp_path / "g2.json"), "--work", str(tmp_path / "w"), "--backend", "api"])
    assert rc == 0 and read_json(tmp_path / "g2.json")["stamp"]["calls"]["replayed"] == 2
    assert read_json(tmp_path / "g2.json")["triggers"] == d["triggers"]
