"""verify-spec --rater api: the spend gate must bound what the run can actually send.

The estimate assumed 6K output tokens per call, but the API rater sends max_tokens 16000 and
run_tasks retries a call up to 3 times, so the "upper" estimate was not an upper bound. And
BASELAYER_SPEND_CEILING_USD was never read. Now the gate uses the worst case (every call at
its max_tokens, every attempt), checks it against --confirm-api-spend and the ceiling, and the
rater itself refuses a call whose worst case would pass the cap. No API calls: the anthropic
module is a fake that counts requests.
"""
import json
import sys
import types

import pytest

from baselayer.verification import raters
from baselayer.verification import run as vrun
from tests.test_verification import world  # noqa: F401  (fixture)


class _Msgs:
    def __init__(self, usage_in=1000, usage_out=1000):
        self.calls = 0
        self.usage = types.SimpleNamespace(input_tokens=usage_in, output_tokens=usage_out)

    def create(self, **kw):
        self.calls += 1
        blk = types.SimpleNamespace(type="text", text='{"items": []}')
        return types.SimpleNamespace(content=[blk], model=kw["model"], stop_reason="end_turn",
                                     usage=self.usage)


@pytest.fixture
def fake_api(monkeypatch):
    msgs = _Msgs()
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=msgs)))
    monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    return msgs


def _dry_estimate(tmp, corpus, spec_dir):
    out = tmp / "dry"
    vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(out),
               "--rater", "api", "--model", "claude-sonnet-5", "--checks", "support"], rater=None)
    return json.loads((out / "t.verification.json").read_text(encoding="utf-8"))["meta"]["model"]["estimate"]


def _api_run(tmp, corpus, spec_dir, cap):
    return vrun.main([str(spec_dir), "--label", "t", "--corpus", str(corpus), "--out", str(tmp / "o"),
                      "--run-model", "--rater", "api", "--model", "claude-sonnet-5", "--checks", "support",
                      "--workers", "1", "--confirm-api-spend", repr(cap)], rater=None)


def test_a_cap_at_the_old_upper_estimate_is_refused(world, fake_api):
    tmp, corpus, spec_dir = world
    est = _dry_estimate(tmp, corpus, spec_dir)
    assert est["total_worst_usd"] > est["total_upper_usd"]
    with pytest.raises(SystemExit):
        _api_run(tmp, corpus, spec_dir, est["total_upper_usd"])
    assert fake_api.calls == 0, "nothing may be sent when the worst case exceeds the cap"


def test_the_spend_ceiling_is_enforced_too(world, fake_api, monkeypatch):
    tmp, corpus, spec_dir = world
    est = _dry_estimate(tmp, corpus, spec_dir)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", repr(est["total_worst_usd"] / 2))
    with pytest.raises(SystemExit):
        _api_run(tmp, corpus, spec_dir, est["total_worst_usd"] * 10)
    assert fake_api.calls == 0


def test_a_cap_over_the_worst_case_runs(world, fake_api):
    tmp, corpus, spec_dir = world
    est = _dry_estimate(tmp, corpus, spec_dir)
    _api_run(tmp, corpus, spec_dir, est["total_worst_usd"] * 1.01)
    assert fake_api.calls >= 1


def test_the_rater_refuses_a_call_that_would_pass_its_cap(fake_api):
    fake_api.usage = types.SimpleNamespace(input_tokens=1_000_000, output_tokens=0)   # $2.00
    r = raters.ApiRater("claude-sonnet-5", cap_usd=2.1)
    assert r.complete("x").cost_usd == pytest.approx(2.0)   # worst case $0.16 fit under $2.10
    with pytest.raises(raters.ApiSpendCapReached):
        r.complete("x")        # $2.00 spent + this call's worst case ($0.16) > $2.10
    assert fake_api.calls == 1
