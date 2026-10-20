"""`batch_extract --submit` must honour BASELAYER_SPEND_CEILING_USD.

WHY THIS EXISTS. The sequential extraction path checks the ceiling before every call
(extract_facts.check_spend_ceiling). The batch path built every request and submitted them in
one POST without reading the variable at all, so an operator who set a ceiling and chose the
batch path had no ceiling. A batch cannot be stopped part way through the way the sequential
loop can, so the only bound that holds is the batch's worst case before submit: every request's
prompt at the model's chars-per-token, every request's max_tokens as output, at the batch
discount.

No network: the fake Batches client from test_turn_batch_extract records what was submitted.
"""
import pytest

from tests.test_turn_batch_extract import benv, _seed  # noqa: F401  (benv is a fixture)
from tests.test_turn_extraction import env  # noqa: F401


def _submit(benv, monkeypatch, ceiling):
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    if ceiling is None:
        monkeypatch.delenv("BASELAYER_SPEND_CEILING_USD", raising=False)
    else:
        monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", str(ceiling))
    benv.be.run_submit()


def test_a_ceiling_below_the_worst_case_refuses_before_submit(benv, monkeypatch):
    with pytest.raises(benv.ef.SpendCeilingExceeded, match="batch worst case"):
        _submit(benv, monkeypatch, 0.000001)
    assert benv.batches.submitted is None, "the batch was submitted past the ceiling"


def test_a_ceiling_above_the_worst_case_submits(benv, monkeypatch):
    _submit(benv, monkeypatch, 100)
    assert benv.batches.submitted and len(benv.batches.submitted) == 1


def test_no_ceiling_means_no_ceiling_as_on_the_sequential_path(benv, monkeypatch):
    _submit(benv, monkeypatch, None)
    assert benv.batches.submitted


def test_worst_case_prices_every_request_at_the_batch_discount(benv):
    from baselayer.config import SPEND_BATCH_DISCOUNT, spend_rates_for
    model = "claude-haiku-4-5"
    r = spend_rates_for(model)
    reqs = [{"params": {"model": model, "max_tokens": 1000,
                        "messages": [{"role": "user", "content": "x" * 350}]}}] * 3
    got = benv.ef.batch_worst_case_usd(reqs, model)
    one = (350 / r["chars_per_token"] * r["input"] + 1000 * r["output"]) / 1e6
    assert got == pytest.approx(3 * one * SPEND_BATCH_DISCOUNT)


def test_a_model_with_no_rate_row_is_refused_when_a_ceiling_is_set(benv, monkeypatch):
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "100")
    reqs = [{"params": {"model": "claude-unknown-9", "max_tokens": 10,
                        "messages": [{"role": "user", "content": "x"}]}}]
    with pytest.raises(benv.ef.SpendCeilingExceeded, match="no published rate"):
        benv.ef.check_batch_spend_ceiling(reqs, "claude-unknown-9")
