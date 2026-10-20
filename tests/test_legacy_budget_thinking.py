"""Legacy-path output budgets on a model that thinks, and a chunk identity that does not move
when the model does.

1. The legacy path (`baselayer extract` without --turn-contract, and `baselayer run`) sized its
   output budgets for Haiku 4.5, which does not think: call_anthropic's prompt-length heuristic
   (2,000 to 10,000), the dynamic-cap budget (90 per fact, floor 2,000) and the legacy batch
   request (8,000). Thinking shares max_tokens, and a legacy reply that stops on max_tokens is
   counted and dropped (there is no re-chunk on that path). On a thinking model each is now
   multiplied by config.THINKING_OUTPUT_MULTIPLIER, floored at the thinking floor.
2. The ledger's chunk_input_hash included the chunk's max_tokens, which now depends on the
   model. A done chunk whose hash changes is re-run, so a model switch would have re-extracted
   the done chunks of every grown or retried conversation. The hash takes the model-independent
   budget, as it never took the model.
"""
import json
from types import SimpleNamespace

import pytest

from tests.test_turn_extraction import _seed, env  # noqa: F401


class _Capture:
    def __init__(self):
        self.kwargs = []

    def create(self, **kw):
        self.kwargs.append(kw)
        return SimpleNamespace(model=kw["model"], stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps({"facts": []}))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def _install(monkeypatch, model):
    import baselayer.extract_facts as ef
    msgs = _Capture()
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", model)
    monkeypatch.setattr(ef, "_get_anthropic_client", lambda: SimpleNamespace(messages=msgs))
    return ef, msgs


def test_the_prompt_length_heuristic_is_scaled_on_a_thinking_model(monkeypatch):
    prompt = "x" * 30_000                               # heuristic: 50 facts -> 10,000 tokens
    ef, msgs = _install(monkeypatch, "claude-haiku-4-5-20251001")
    ef.call_anthropic(prompt, retries=0)
    assert msgs.kwargs[0]["max_tokens"] == 10_000         # Haiku 4.5 unchanged
    ef, msgs = _install(monkeypatch, "claude-haiku-5-5")
    ef.call_anthropic(prompt, retries=0)
    assert msgs.kwargs[0]["max_tokens"] == 30_000
    ef, msgs = _install(monkeypatch, "claude-haiku-5-5")
    ef.call_anthropic("short", retries=0)               # heuristic floor 2,000 -> thinking floor
    assert msgs.kwargs[0]["max_tokens"] == 8_000


def test_an_explicit_max_tokens_is_passed_through(monkeypatch):
    ef, msgs = _install(monkeypatch, "claude-haiku-5-5")
    ef.call_anthropic("p", retries=0, max_tokens=12_345)  # the turn path sizes its own
    assert msgs.kwargs[0]["max_tokens"] == 12_345


def test_the_dynamic_cap_budget_is_scaled_on_a_thinking_model(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-4-5-20251001")
    base = ef._extraction_max_tokens(100)
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    assert ef._extraction_max_tokens(100) == 3 * base


def test_the_legacy_batch_budget_is_scaled_on_a_thinking_model(monkeypatch):
    from baselayer import batch_extract as be, config
    assert be.legacy_batch_max_tokens("claude-haiku-4-5-20251001") == be.BATCH_MAX_TOKENS
    assert be.legacy_batch_max_tokens("claude-haiku-5-5") == min(
        config.EXTRACTION_MAX_OUTPUT_TOKENS, 3 * be.BATCH_MAX_TOKENS)


def test_the_chunk_identity_does_not_change_with_the_model(env, monkeypatch):
    from tests.test_turn_extraction import TURNS
    _seed(env, turns=TURNS)
    ef = env.ef
    conn = env.get_db()
    conv = conn.execute("SELECT id, title, source FROM conversations").fetchone()
    turns = ef._tc.load_turns(conn, conv["id"])
    plan = {"fact_count_mode": "coverage", "input_char_budget": 6000, "per_chunk_cap": 40,
            "max_tokens": 4000}
    ch = next(c for c in ef.build_turn_chunks(turns, conv["source"], 6000) if c.has_citable)
    hashes = {}
    for model in ("claude-haiku-4-5-20251001", "claude-haiku-5-5"):
        monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", model)
        hashes[model] = ef.chunk_input_hash(conv["title"], ch, plan, False)
    assert hashes["claude-haiku-4-5-20251001"] == hashes["claude-haiku-5-5"]
    # the budget actually sent still differs
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    assert ef.turn_chunk_max_tokens(ch, plan) >= 8000


def test_a_capped_turn_chunk_is_scaled_at_call_time_not_in_its_plan(monkeypatch):
    import baselayer.extract_facts as ef
    plan = {"fact_count_mode": "capped", "max_tokens": 4000}
    ch = SimpleNamespace(citable_chars=500)
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-4-5-20251001")
    assert ef.turn_chunk_max_tokens(ch, plan) == 4000
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    assert ef.turn_chunk_max_tokens(ch, plan) == 12000
    assert ef._hash_budget(ch, plan) == 4000 and plan["max_tokens"] == 4000
