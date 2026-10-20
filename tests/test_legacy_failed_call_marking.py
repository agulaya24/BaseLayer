"""The legacy sequential path must not mark a conversation extracted when a call failed.

call_llm returns None when an extraction call fails after its retries. The single-pass path
and every chunk of the chunked paths turned that None into "no facts": a failed chunk was
skipped while its siblings' facts were kept, and a failed single call returned [], which
process_conversation logged as a conversation with 0 facts. Either way the conversation got
an extraction_log row >= 0, so it read as done, and `--retry-errors` (which re-selects only
rows of -1) never retried it. A reply with an empty facts list is still a real 0.
"""
import pytest

from tests.test_turn_extraction import CONV, LEGACY_FACTS, _seed, env  # noqa: F401

pytestmark = pytest.mark.legacy


def _log(env, conv=CONV):
    c = env.get_db()
    try:
        row = c.execute("SELECT facts_extracted FROM extraction_log WHERE conversation_id = ?",
                        (conv,)).fetchone()
        return None if row is None else row[0]
    finally:
        c.close()


def _fact_count(env):
    c = env.get_db()
    try:
        return c.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    finally:
        c.close()


def _scripted_llm(replies):
    """call_llm stand-in: returns the scripted replies in order (None = a failed call)."""
    replies = list(replies)

    def call(prompt, schema=None, retries=None, max_tokens=None):
        return replies.pop(0) if replies else {"facts": []}
    return call


def _force_two_chunks(env, monkeypatch):
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 80, "input_char_budget": 10})
    monkeypatch.setattr(env.ef, "_chunk_text_for_extraction",
                        lambda *a, **k: ["chunk-0", "chunk-1"])


def test_a_failed_single_call_is_logged_as_an_error_and_retried(env, monkeypatch):
    _seed(env, with_turns=False)
    monkeypatch.setattr(env.ef, "call_llm", _scripted_llm([None]))
    env.ef.run_extraction()
    assert _log(env) == -1, "a failed call must not read as an extracted conversation"
    # --retry-errors re-selects it, and a working call now stores its facts.
    monkeypatch.setattr(env.ef, "call_llm", _scripted_llm([{"facts": LEGACY_FACTS}]))
    env.ef.run_extraction(retry_errors=True)
    assert _log(env) > 0 and _fact_count(env) > 0


def test_one_failed_chunk_fails_the_conversation_and_stores_nothing(env, monkeypatch):
    _seed(env, with_turns=False)
    _force_two_chunks(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", _scripted_llm([{"facts": LEGACY_FACTS}, None]))
    env.ef.run_extraction()
    assert _log(env) == -1
    # Nothing half-stored: the retry re-extracts the whole conversation, so facts kept from
    # the good chunk would be extracted again next to themselves.
    assert _fact_count(env) == 0


def test_an_empty_facts_reply_is_still_a_real_zero(env, monkeypatch):
    _seed(env, with_turns=False)
    monkeypatch.setattr(env.ef, "call_llm", _scripted_llm([{"facts": []}]))
    env.ef.run_extraction()
    assert _log(env) == 0


def test_identity_path_failed_chunk_raises(env, monkeypatch):
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 80, "input_char_budget": 10})
    monkeypatch.setattr(env.ef, "_chunk_text_for_extraction",
                        lambda *a, **k: ["chunk-0", "chunk-1"])
    monkeypatch.setattr(env.ef, "call_llm", _scripted_llm([{"facts": LEGACY_FACTS}, None]))
    msgs = [{"role": "user", "text": "I always write the plan before the code. " * 10}]
    with pytest.raises(env.ef.ExtractionCallFailed):
        env.ef.extract_identity_from_project_conversation("c", "t", msgs)
    monkeypatch.setattr(env.ef, "call_llm", _scripted_llm([None]))
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 80, "input_char_budget": 100000})
    with pytest.raises(env.ef.ExtractionCallFailed):
        env.ef.extract_identity_from_project_conversation("c", "t", msgs)
