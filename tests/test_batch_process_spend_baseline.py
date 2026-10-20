"""batch --process checks its synchronous calls against the ceiling WITH the batch's spend.

run_process called reset_usage() before storing, so the AUDN and re-chunk calls it makes
synchronously were checked against BASELAYER_SPEND_CEILING_USD from $0, as if the batch had
cost nothing. It now seeds the ceiling with the billed usage of every succeeded result.
No API calls: the batch client is a fake that returns scripted usage.
"""
import types

import pytest

from tests.test_turn_batch_extract import FakeBatches, _result  # noqa: F401
from tests.test_turn_batch_extract import benv  # noqa: F401  (fixture)
from tests.test_turn_extraction import LEGACY_FACTS, _seed, env  # noqa: F401

pytestmark = pytest.mark.legacy

MODEL = "claude-haiku-4-5-20251001"


def _billed(res, input_tokens):
    res.result.message.usage = types.SimpleNamespace(input_tokens=input_tokens, output_tokens=0)
    res.result.message.model = MODEL
    return res


def _run(benv, monkeypatch, ceiling, input_tokens):
    _seed(benv, with_turns=False)
    monkeypatch.setenv("BASELAYER_LLM_EXTRACTION", MODEL)
    benv.be.run_submit()                                   # no ceiling at submit
    benv.batches.results_for = lambda ids: [_billed(_result(i, LEGACY_FACTS), input_tokens)
                                            for i in ids]
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", str(ceiling))
    seen = []

    def audn_with_a_sync_call(fact_text, similar):
        # what a synchronous AUDN call does first: check the ceiling for its worst case
        benv.ef.check_spend_ceiling(4000, 1000)
        seen.append(benv.ef.measured_spend_usd())
        return {"action": "ADD"}
    monkeypatch.setattr(benv.be, "make_audn_decision", audn_with_a_sync_call)
    benv.be.run_process()
    return seen


def test_a_sync_call_after_the_batch_sees_the_batch_spend(benv, monkeypatch):
    # 1M input tokens at Haiku 4.5's $1/MTok, batch half: $0.50 billed. Ceiling $0.50, so any
    # further call must be refused. The old code checked it against $0 and let it through.
    from baselayer.extract_facts import SpendCeilingExceeded
    with pytest.raises(SpendCeilingExceeded):
        _run(benv, monkeypatch, ceiling=0.50, input_tokens=1_000_000)


def test_an_unpriceable_batch_refuses_before_the_reset(benv, monkeypatch):
    """Pricing the batch can refuse (a model with no rate row). That refusal must come while
    the prior corpus is intact: --process deletes every extracted fact before storing."""
    from baselayer.extract_facts import SpendCeilingExceeded
    _seed(benv, with_turns=False)
    c = benv.get_db()
    c.execute("INSERT INTO memory_facts (id, fact_text, source) VALUES ('old', 'kept', 'extraction')")
    c.commit()
    c.close()
    benv.be.run_submit()
    benv.batches.results_for = lambda ids: [_billed(_result(i, LEGACY_FACTS), 1000) for i in ids]
    monkeypatch.setattr("baselayer.config.spend_rates_for", lambda model: None)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "5")
    with pytest.raises(SpendCeilingExceeded):
        benv.be.run_process()
    c = benv.get_db()
    try:
        assert c.execute("SELECT COUNT(*) FROM memory_facts WHERE id = 'old'").fetchone()[0] == 1
    finally:
        c.close()


def test_under_the_ceiling_the_run_still_goes_through(benv, monkeypatch):
    seen = _run(benv, monkeypatch, ceiling=5.0, input_tokens=1_000_000)
    assert seen, "the synchronous call ran"
