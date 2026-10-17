"""Batch custom ids on the turn-contract submit path.

The Message Batches API refuses a request whose custom_id is not 1-64 characters of
[A-Za-z0-9_-], and refuses the WHOLE batch with a 400. Text-file conversation ids are
`textfile_<stem>_<8hex>`, so a staged filename stem over ~46 characters made an id the API
refused (one document corpus, 2026-10-05: 40 of 215 ids were 65-72 characters). The base-chunk branch sent
`custom_id = conv_id` unguarded; only the split-part branch had a guard (d47b691).

These tests use a fake Batches client that validates ids the way the API does, so the
failure is the API's failure, and check that every id still maps back to its conversation
through chunk_map. Synthetic corpus only; nothing is sent anywhere.
"""
import re
import types

import pytest

from tests.test_turn_batch_extract import FakeBatches, _result, _state, benv  # noqa: F401
from tests.test_turn_extraction import TURN_FACTS, _facts, _seed, env  # noqa: F401

API_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# 79 characters, the shape of the ids the API refused on 10/5 (65-72 there; synthetic stem).
LONG_ID = "textfile_synthetic_protocol_draft__03_conventions_and_definitions__p01_1a2b3c4d"
# A stem may carry characters the API refuses even when short.
DOTTED_ID = "textfile_notes.v2 final_1a2b3c4d"


class ApiLikeBatches(FakeBatches):
    """Refuses the whole batch as the API does: a bad or duplicate custom_id is a 400."""

    def create(self, requests):
        ids = [r["custom_id"] for r in requests]
        bad = [i for i in ids if not API_ID.fullmatch(i)]
        if bad or len(set(ids)) != len(ids):
            raise RuntimeError(f"400 invalid_request_error: custom_id {bad or 'duplicate'}")
        return super().create(requests)


@pytest.fixture
def api_benv(benv, monkeypatch):  # noqa: F811
    batches = ApiLikeBatches()
    client = types.SimpleNamespace(messages=types.SimpleNamespace(batches=batches))
    monkeypatch.setattr(benv.be, "_get_anthropic_client", lambda: client)
    benv.batches = batches
    return benv


def test_long_and_dotted_conversation_ids_submit_and_map_back(api_benv):
    assert len(LONG_ID) > 64
    _seed(api_benv, conv=LONG_ID)
    _seed(api_benv, conv=DOTTED_ID)
    _seed(api_benv)                                              # a plain short id, kept as is
    api_benv.be.run_submit(turn_contract=True)
    reqs = api_benv.batches.submitted
    assert reqs is not None, "the API-like client refused the batch"
    ids = [r["custom_id"] for r in reqs]
    assert all(API_ID.fullmatch(i) for i in ids) and len(set(ids)) == len(ids)
    assert "conv-1" in ids                                       # short ids are unchanged
    cmap = _state(api_benv)["chunk_map"]
    assert {cmap[i]["parent_conv_id"] for i in ids} == {LONG_ID, DOTTED_ID, "conv-1"}

    api_benv.batches.results_for = lambda cids: [_result(i, TURN_FACTS) for i in cids]
    api_benv.be.run_process(resume=False)
    by_conv = {}
    for f in _facts(api_benv):
        by_conv.setdefault(f["source_conversation_id"], []).append(f)
    assert by_conv.get(LONG_ID) and by_conv.get(DOTTED_ID) and by_conv.get("conv-1")


def test_safe_custom_id_keeps_valid_ids_and_replaces_invalid_ones():
    from baselayer import batch_extract as be
    assert be._safe_custom_id("conv-1", "0123456789abcdef") == "conv-1"
    assert be._safe_custom_id("conv-1__c2of3", "0123456789abcdef") == "conv-1__c2of3"
    for bad in (LONG_ID, DOTTED_ID, LONG_ID + "__c1of2", ""):
        assert be._safe_custom_id(bad, "0123456789abcdef") == "blk_0123456789abcdef"


def test_an_invalid_id_is_refused_before_any_client_exists(api_benv, monkeypatch):
    """The $0 preflight traps at client construction, so a check after that point is a check
    the preflight cannot see. A bad id must stop the run first."""
    _seed(api_benv)
    real = api_benv.be._build_request_for_conv

    def bad_id(custom_id, *a, **k):
        return real("x" * 65, *a, **k)
    monkeypatch.setattr(api_benv.be, "_build_request_for_conv", bad_id)

    def no_client():
        raise AssertionError("an Anthropic client was constructed before the ids were checked")
    monkeypatch.setattr(api_benv.be, "_get_anthropic_client", no_client)
    with pytest.raises(api_benv.be.BatchRequestError, match="custom_id"):
        api_benv.be.run_submit(turn_contract=True)


def test_duplicate_ids_are_refused():
    from baselayer import batch_extract as be
    reqs = [{"custom_id": "a"}, {"custom_id": "a"}]
    with pytest.raises(be.BatchRequestError, match="duplicate"):
        be._check_custom_ids(reqs)
    be._check_custom_ids([{"custom_id": "a"}, {"custom_id": "b"}])
