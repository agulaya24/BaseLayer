"""run_submit says what happened, and `pipeline` processes only the batch it just submitted.

run_submit returned None on every outcome: submitted, nothing to submit, an active batch
already in the way, or a failed submission. The CLI exited 0 on all of them, and `pipeline`
went on to poll batch_state.json, so when nothing new was submitted it found the PREVIOUS
batch's state (status completed) and ran `run_process(resume=True)` on that old batch again.
Now a refusal or failure exits non-zero, nothing-to-submit returns None, a submission returns
its batch id, and the pipeline's batch step processes only that id. No API calls.
"""
import json

import pytest

from tests.test_turn_batch_extract import FakeBatches  # noqa: F401
from tests.test_turn_batch_extract import benv  # noqa: F401  (fixture)
from tests.test_turn_extraction import _seed, env  # noqa: F401

pytestmark = pytest.mark.legacy


def _write_state(benv, **state):
    p = benv.root / "data" / "database" / "batch_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")


def test_a_submission_returns_its_batch_id(benv):
    _seed(benv, with_turns=False)
    assert benv.be.run_submit() == "batch-1"


def test_nothing_to_submit_returns_none_without_failing(benv):
    assert benv.be.run_submit() is None          # no conversations at all


def test_an_active_batch_in_the_way_exits_non_zero(benv):
    _seed(benv, with_turns=False)
    _write_state(benv, batch_id="batch-old", status="submitted")
    with pytest.raises(SystemExit) as e:
        benv.be.run_submit()
    assert e.value.code not in (0, None)


def test_a_failed_submission_exits_non_zero(benv, monkeypatch):
    _seed(benv, with_turns=False)

    def boom(requests):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(benv.batches, "create", boom)
    with pytest.raises(SystemExit) as e:
        benv.be.run_submit()
    assert e.value.code not in (0, None)


def test_pipeline_does_not_reprocess_an_old_batch_when_nothing_was_submitted(benv, monkeypatch):
    from baselayer import cli
    _write_state(benv, batch_id="batch-old", status="completed", total_requests=5)
    processed = []
    monkeypatch.setattr(benv.be, "run_process", lambda resume=False: processed.append(resume))
    cli._pipeline_batch_extract(doc_mode=False, poll_seconds=0)
    assert processed == [], "the previous batch was processed again"


def test_pipeline_processes_the_batch_it_submitted(benv, monkeypatch):
    from baselayer import cli
    _seed(benv, with_turns=False)
    processed = []
    monkeypatch.setattr(benv.be, "run_process", lambda resume=False: processed.append(resume))
    monkeypatch.setattr("baselayer.api_client.get_anthropic_client",
                        lambda: benv.be._get_anthropic_client())
    cli._pipeline_batch_extract(doc_mode=False, poll_seconds=0)
    assert processed == [True]
