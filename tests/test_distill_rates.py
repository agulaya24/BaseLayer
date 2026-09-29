"""Distillation prices from ONE dated table that the operator confirms per run. No API calls.

The distill copy of the rate table listed claude-sonnet-5 at $3/$15 against a published $2/$10,
so every printed distill cost was 1.5x the bill. Rates now live in spend.py only.
"""
import json
import sys

import pytest

from baselayer.distillation import author_from_package as afp
from baselayer.distillation import distill
from baselayer.distillation import spend
from tests.test_artifact_stamps import (FACTS, DistillClient, _make_db, author_env,  # noqa: F401
                                        no_network)


def test_no_rate_constants_outside_the_table():
    assert not hasattr(distill, "_RATES")
    assert not hasattr(afp, "_RATES")
    assert not hasattr(distill, "_cost")


def test_table_is_dated_and_sonnet5_is_the_published_rate():
    assert spend.RATES_AS_OF and spend.RATES_SOURCE
    assert spend.RATES_PER_MTOK["claude-sonnet-5"] == (2.0, 10.0)
    assert spend.BATCH_DISCOUNT == 0.5


def test_unconfirmed_table_is_refused(monkeypatch):
    monkeypatch.delenv("BASELAYER_RATES_CONFIRMED", raising=False)
    with pytest.raises(SystemExit, match="RATES NOT CONFIRMED"):
        spend.resolve_rates("claude-sonnet-5")
    with pytest.raises(SystemExit, match="RATES NOT CONFIRMED"):
        spend.resolve_rates("claude-sonnet-5", confirmed="2020-01-01")
    r = spend.resolve_rates("claude-sonnet-5", confirmed=spend.RATES_AS_OF)
    assert (r["in"], r["out"], r["as_of"]) == (2.0, 10.0, spend.RATES_AS_OF)


def test_operator_rates_override_and_unknown_model_needs_them(monkeypatch):
    monkeypatch.delenv("BASELAYER_RATES_CONFIRMED", raising=False)
    with pytest.raises(SystemExit, match="no rate"):
        spend.resolve_rates("claude-future-9", confirmed=spend.RATES_AS_OF)
    with pytest.raises(SystemExit, match="both"):
        spend.resolve_rates("claude-future-9", rate_in=1.0)
    r = spend.resolve_rates("claude-future-9", rate_in=1.5, rate_out=7.0)
    assert (r["in"], r["out"], r["source"]) == (1.5, 7.0, "operator")


def test_batch_cost_is_half_of_sequential():
    r = spend.resolve_rates("claude-sonnet-5", confirmed=spend.RATES_AS_OF)
    seq = spend.cost_usd(r, 1_000_000, 1_000_000)
    assert seq == pytest.approx(12.0)
    assert spend.cost_usd(r, 1_000_000, 1_000_000, batch=True) == pytest.approx(6.0)


def _run(monkeypatch, db, out, *extra):
    monkeypatch.setattr(sys, "argv", ["distill.py", "--db", str(db), "--out", str(out),
                                      "--model", "claude-haiku-4-5", "--max-facts", "2",
                                      "--layer", "anchors", *extra])
    distill.main()
    return json.load(open(out, encoding="utf-8"))


def test_distill_refuses_unconfirmed_rates_before_any_call(no_network, monkeypatch, tmp_path):
    monkeypatch.delenv("BASELAYER_RATES_CONFIRMED", raising=False)
    db = _make_db(tmp_path / "c", FACTS)
    with pytest.raises(SystemExit, match="RATES NOT CONFIRMED"):
        _run(monkeypatch, db, tmp_path / "t.json")
    assert DistillClient.calls == []


def test_tree_records_the_rates_it_priced_at(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path / "c", FACTS)
    tree = _run(monkeypatch, db, tmp_path / "t.json", "--rates-confirmed", spend.RATES_AS_OF)
    st = tree["stamp"]
    assert st["rates_per_mtok"] == {"in": 1.0, "out": 5.0}
    assert st["rates_source"] == spend.RATES_SOURCE and st["rates_as_of"] == spend.RATES_AS_OF
    # 2 leaves, each 10 in / 5 out at $1/$5 per MTok.
    assert tree["usage"]["cost_usd"] == pytest.approx((20 * 1 + 10 * 5) / 1e6, abs=1e-9)


def test_author_refuses_unconfirmed_rates_before_any_call(author_env, monkeypatch):
    from tests.test_artifact_stamps import AuthorClient, V
    monkeypatch.delenv("BASELAYER_RATES_CONFIRMED", raising=False)
    pkg = author_env.write_pkg("anchors.json", V)
    with pytest.raises(SystemExit, match="RATES NOT CONFIRMED"):
        author_env.run(pkg)
    assert AuthorClient.calls == []


def test_cli_threads_the_rate_flags(monkeypatch):
    """cli.py builds argv by hand; a flag it does not forward cannot be given on the CLI path."""
    from baselayer import cli
    seen = {}
    monkeypatch.setattr(distill, "main", lambda: seen.setdefault("distill", list(sys.argv)))
    monkeypatch.setattr(afp, "main", lambda: seen.setdefault("afp", list(sys.argv)))
    monkeypatch.setattr(cli, "_check_api_key", lambda: None)
    for argv in (["baselayer", "distill", "--out", "t.json", "--db", "x.db",
                  "--rates-confirmed", spend.RATES_AS_OF],
                 ["baselayer", "author-from-package", "--package", "p.json", "--outdir", "o",
                  "--rate-in", "4", "--rate-out", "20"]):
        monkeypatch.setattr(sys, "argv", argv)
        cli.main()
    assert "--rates-confirmed" in seen["distill"] and spend.RATES_AS_OF in seen["distill"]
    assert seen["afp"][seen["afp"].index("--rate-in") + 1] == "4.0"
    assert seen["afp"][seen["afp"].index("--rate-out") + 1] == "20.0"
