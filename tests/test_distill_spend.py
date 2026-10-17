"""Spend ceiling and up-front estimate for the distillation path. No API calls.

A billed distillation or authoring run prints a dollar estimate before any call, refuses to start
without a ceiling (BASELAYER_SPEND_CEILING_USD) or an explicit --confirm-spend at or above the
estimate, and checks the ceiling before EVERY model call, including a leaf's schema-repair call
and a rejected authoring attempt's re-ask, not only once per leaf.
"""
import json
import sys
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import author_from_package as afp
from baselayer.distillation import distill
from baselayer.distillation import spend
from tests.test_artifact_stamps import (FACTS, V, DistillClient, _make_db, _Stream,  # noqa: F401
                                        _tree, author_env, no_network)
from baselayer.distillation import assemble as asm


# --------------------------------------------------------------------------- spend.py units

def test_plan_ceiling_rules(monkeypatch):
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    with pytest.raises(SystemExit, match="NO SPEND CEILING"):
        spend.plan_ceiling(1.0)
    with pytest.raises(SystemExit, match="below the estimate"):
        spend.plan_ceiling(1.0, confirm_spend=0.5)
    assert spend.plan_ceiling(1.0, confirm_spend=2.0) == 2.0
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "0.8")
    with pytest.raises(SystemExit, match="exceeds the ceiling"):
        spend.plan_ceiling(1.0)
    # --confirm-spend at or above the estimate becomes the ceiling for the run.
    assert spend.plan_ceiling(1.0, confirm_spend=1.0) == 1.0
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "5")
    assert spend.plan_ceiling(1.0) == 5.0


def test_guard_checks_worst_case_before_and_counts_after():
    r = spend.resolve_rates("claude-haiku-4-5", confirmed=spend.RATES_AS_OF)
    g = spend.SpendGuard(r, ceiling_usd=0.10)
    g.check(prompt_chars=3500, max_tokens=10000)          # 0.001 + 0.05 <= 0.10
    g.record(1000, 10000)                                  # spent 0.051
    with pytest.raises(spend.SpendCeilingExceeded):
        g.check(prompt_chars=3500, max_tokens=10000)      # 0.051 + 0.051 > 0.10
    assert issubclass(spend.SpendCeilingExceeded, SystemExit)


def test_guard_prices_batch_usage_at_the_discount():
    r = spend.resolve_rates("claude-sonnet-5", confirmed=spend.RATES_AS_OF)
    g = spend.SpendGuard(r, ceiling_usd=100)
    g.record(1_000_000, 1_000_000, batch=True)
    assert g.spent_usd == pytest.approx(6.0)


# --------------------------------------------------------------------------- distill

def _run(monkeypatch, db, out, *extra, max_facts="2"):
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", max_facts,
                                      "--layer", "anchors", *extra])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def test_distill_refuses_without_a_ceiling_before_any_call(no_network, monkeypatch, tmp_path,
                                                          capsys):
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    db = _make_db(tmp_path / "c", FACTS)
    with pytest.raises(SystemExit, match="NO SPEND CEILING"):
        _run(monkeypatch, db, tmp_path / "t.json")
    assert DistillClient.calls == []
    assert "ESTIMATE" in capsys.readouterr().out


def test_distill_refuses_when_estimate_exceeds_ceiling(no_network, monkeypatch, tmp_path):
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "0.0001")
    db = _make_db(tmp_path / "c", FACTS)
    with pytest.raises(SystemExit, match="exceeds the ceiling"):
        _run(monkeypatch, db, tmp_path / "t.json")
    assert DistillClient.calls == []
    with pytest.raises(SystemExit, match="below the estimate"):
        _run(monkeypatch, db, tmp_path / "t.json", "--confirm-spend", "0.0001")
    assert DistillClient.calls == []


def test_distill_runs_when_confirmed_and_stamps_estimate_and_ceiling(no_network, monkeypatch,
                                                                    tmp_path):
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    db = _make_db(tmp_path / "c", FACTS)
    tree = _run(monkeypatch, db, tmp_path / "t.json", "--confirm-spend", "5")
    st = tree["stamp"]
    assert st["spend_ceiling_usd"] == 5.0
    assert st["spend_estimate_usd"] > 0
    assert tree["usage"]["cost_usd"] == pytest.approx(st["spend_measured_usd"])


class RepairClient(DistillClient):
    """First reply is unparseable and bills a full max_tokens; the repair would parse."""
    def stream(self, **kw):
        DistillClient.calls.append(kw)
        if len(DistillClient.calls) == 1:
            return _Stream(NS(content=[NS(type="text", text="not json")],
                              usage=NS(input_tokens=100, output_tokens=16000),
                              stop_reason="max_tokens"))
        DistillClient.calls.pop()
        return super().stream(**kw)


def test_ceiling_is_checked_before_the_repair_call_not_only_per_leaf(no_network, monkeypatch,
                                                                     tmp_path):
    """One leaf. The first call fits the ceiling and bills 16,000 output tokens ($0.08 at
    Haiku rates); the schema-repair call's worst case would pass the ceiling, so it must be
    refused. A check placed once per leaf would let the repair through."""
    monkeypatch.setattr("anthropic.Anthropic", RepairClient)
    db = _make_db(tmp_path / "c", FACTS)
    with pytest.raises(spend.SpendCeilingExceeded):
        _run(monkeypatch, db, tmp_path / "t.json", "--confirm-spend", "0.12", max_facts="3")
    assert len(DistillClient.calls) == 1


# --------------------------------------------------------------------------- author

class BigAuthorClient:
    """Every attempt returns no tool call and bills 20,000 output tokens."""
    calls = []

    def __init__(self, *a, **k):
        self.messages = self

    def stream(self, **kw):
        BigAuthorClient.calls.append(kw)
        return _Stream(NS(content=[NS(type="text", text="prose")], stop_reason="end_turn",
                          stop_details=None, usage=NS(input_tokens=1000, output_tokens=20000)))


def test_author_refuses_without_ceiling_before_any_call(author_env, monkeypatch, capsys):
    from tests.test_artifact_stamps import AuthorClient
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    pkg = author_env.write_pkg("anchors.json", V)
    with pytest.raises(SystemExit, match="NO SPEND CEILING"):
        author_env.run(pkg)
    assert AuthorClient.calls == []
    assert "ESTIMATE" in capsys.readouterr().out


def test_author_checks_the_ceiling_before_each_reask(author_env, monkeypatch):
    """Attempt 1 bills $0.404 at Opus 5.5 rates and is rejected (no tool call). The re-ask's
    worst case (max_tokens 20,000 = $0.40 output) would pass a $0.70 ceiling: refused."""
    BigAuthorClient.calls = []
    monkeypatch.setattr("anthropic.Anthropic", BigAuthorClient)
    pkg = author_env.write_pkg("anchors.json", V)
    with pytest.raises(spend.SpendCeilingExceeded):
        author_env.run(pkg, extra=("--confirm-spend", "0.70"))
    assert len(BigAuthorClient.calls) == 1


def test_cli_threads_confirm_spend(monkeypatch):
    from baselayer import cli
    seen = {}
    monkeypatch.setattr(distill, "main", lambda: seen.setdefault("distill", list(sys.argv)))
    monkeypatch.setattr(afp, "main", lambda: seen.setdefault("afp", list(sys.argv)))
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    for argv in (["baselayer", "distill", "--out", "t.json", "--db", "x.db",
                  "--confirm-spend", "12.5"],
                 ["baselayer", "author-from-package", "--package", "p.json", "--outdir", "o",
                  "--confirm-spend", "3"]):
        monkeypatch.setattr(sys, "argv", argv)
        cli.main()
    assert seen["distill"][seen["distill"].index("--confirm-spend") + 1] == "12.5"
    assert seen["afp"][seen["afp"].index("--confirm-spend") + 1] == "3.0"


def test_guards_do_not_outlive_main(author_env, no_network, monkeypatch, tmp_path):
    """The per-call guard is process state. A main() that stopped on the ceiling must not
    leave its guard (with its spend and ceiling) on the module for the next caller."""
    from baselayer.distillation import distill_batch
    monkeypatch.setattr("anthropic.Anthropic", RepairClient)
    db = _make_db(tmp_path / "c", FACTS)
    with pytest.raises(spend.SpendCeilingExceeded):
        _run(monkeypatch, db, tmp_path / "t.json", "--confirm-spend", "0.12", max_facts="3")
    assert distill._GUARD is None
    BigAuthorClient.calls = []
    monkeypatch.setattr("anthropic.Anthropic", BigAuthorClient)
    pkg = author_env.write_pkg("anchors.json", V)
    with pytest.raises(spend.SpendCeilingExceeded):
        author_env.run(pkg, extra=("--confirm-spend", "0.70"))
    assert afp._GUARD is None
    monkeypatch.setattr(sys, "argv", ["distill_batch.py", "--db", str(db), "--outdir",
                                      str(tmp_path / "b"), "--model", "claude-haiku-4-5",
                                      "--max-facts", "3", "--layers", "anchors", "--poll", "0"])
    with pytest.raises(SystemExit):
        distill_batch.main()              # refused by the planted/ceiling path or the client
    assert distill._GUARD is None
