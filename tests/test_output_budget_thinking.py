"""Output budget for an extraction model that thinks by default (5-generation).

Thinking shares max_tokens. On Haiku 5.5 at effort medium, one 313-char chat chunk stopped on
its 2,004-token budget (6.4 tokens per citable char, floor 2,000, both derived on Haiku 4.5) and
had to be re-chunked; three other chat chunks used 72-94% of theirs. A thinking model now gets
its own per-char rate and floor, derived the same way (config, beside the constants). Haiku 4.5
keeps its budget exactly.
"""
import json
import math
import types

from tests.test_api_usage_record import _usage
from tests.test_rechunk_on_max_tokens import SENT, TURNS, _caps, _client  # noqa: F401
from tests.test_turn_extraction import _facts, _fact, _records, _seed, env  # noqa: F401


def test_a_thinking_model_gets_the_thinking_floor_and_rate(monkeypatch):
    import baselayer.extract_facts as ef
    from baselayer.config import (EXTRACTION_MAX_OUTPUT_TOKENS, TURN_OUTPUT_TOKENS_FLOOR_THINKING,
                                  TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR_THINKING)
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    assert TURN_OUTPUT_TOKENS_FLOOR_THINKING == 8000
    assert TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR_THINKING == 16
    assert ef.turn_output_budget(313) == 8000           # the chunk that truncated at 2,004
    assert ef.turn_output_budget(863) == math.ceil(16 * 863)
    assert ef.turn_output_budget(10 ** 7) == EXTRACTION_MAX_OUTPUT_TOKENS


def test_haiku_45_keeps_its_budget(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "EXTRACTION_API_MODEL", "claude-haiku-4-5-20251001")
    assert ef.turn_output_budget(313) == math.ceil(6.4 * 313) == 2004
    assert ef.turn_output_budget(100) == 2000


def test_the_run_settings_record_the_budget_actually_used(env, monkeypatch):
    monkeypatch.setattr(env.ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    s = env.ef.turn_run_settings()
    assert (s["output_tokens_per_citable_char"], s["output_tokens_floor"]) == (16, 8000)


class ThinkingScripted:
    """A 5-generation reply: a thinking block first, then text. The first call stops on
    max_tokens; later calls return one fact per subject turn shown."""

    def __init__(self):
        self.calls = []

    def create(self, **kw):
        import re
        self.calls.append(kw)
        prompt = kw["messages"][0]["content"]
        aliases = re.findall(r"\[(S\d+) \| SUBJECT, typed\]\n(Entry \d)", prompt)
        stop = "max_tokens" if len(self.calls) == 1 else "end_turn"
        facts = [_fact(f"logs decisions {e}", [(a, e + ". " + SENT[:30])],
                       predicate="practices", category="habit") for a, e in aliases]
        think = types.SimpleNamespace(type="thinking", thinking="", signature="s")
        text = types.SimpleNamespace(type="text", text=json.dumps({"facts": facts}))
        content = [think] if stop == "max_tokens" else [think, text]
        return types.SimpleNamespace(model="claude-haiku-5-5", content=content,
                                     stop_reason=stop, usage=_usage())


def test_a_thinking_reply_cut_off_by_max_tokens_is_rechunked_not_lost(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "EXTRACTION_API_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(env.ef, "_get_extraction_caps", _caps)
    msgs = ThinkingScripted()
    _client(monkeypatch, env.ef, msgs)
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["counts"]["rechunked_on_max_tokens"] == 1
    assert rec["counts"].get("chunks_failed", 0) == 0
    assert sorted(f["object_text"] for f in _facts(env)) == [f"logs decisions Entry {i}"
                                                             for i in range(4)]
    assert all("temperature" not in c for c in msgs.calls)
    assert all(c["max_tokens"] >= 8000 for c in msgs.calls)
