"""
The fact count on the turn path is a switch (`fact_count_mode`), so both arms of an
A/B run from one code version.

- `capped`: the prompt says "Extract up to N facts ... most identity-relevant
  first" and accepted facts past the per-chunk cap are truncated, counted as
  `over_per_chunk_cap`. Byte-identical prompt to the code before the switch existed.
- `none`: no count and no ordering in the prompt, and no per-chunk truncation.

Selected by BASELAYER_FACT_COUNT_MODE, else config TURN_FACT_COUNT_MODE (default `coverage`,
tests/test_fact_count_default.py). The batch path
saves the mode in each chunk's plan at submit and reads it from there at process time.
"""

import json

import pytest

from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    CONV, _fact, _facts, _records, _seed, env)

# Turn prompt hashes at 809ef84, before the switch existed (entity hints empty).
CAPPED_HASH_GENERAL = "7ca2d4bb3cf670a5"
CAPPED_HASH_PROJECT = "257de75332d51b0a"

LONG = " ".join(f"Note {k}: I choose the slower option when the stakes are high." for k in range(20))
TURNS = [(0, "subject", "own_typed", "user", LONG)]


def _many_facts(n):
    notes = [f"Note {k}: I choose the slower option" for k in range(20)]
    return [_fact(f"grounded fact number {i}", [("S1", notes[i % 20])],
                  predicate="practices", category="habit") for i in range(n)]


def _llm(facts, prompts):
    def call(prompt, schema=None, retries=None, max_tokens=None):
        prompts.append((prompt, max_tokens))
        return {"facts": json.loads(json.dumps(facts))}
    return call


def test_capped_prompt_hash_is_unchanged(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.delenv("BASELAYER_FACT_COUNT_MODE", raising=False)
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    assert ef.turn_prompt_hash(False, mode="capped") == CAPPED_HASH_GENERAL
    assert ef.turn_prompt_hash(True, mode="capped") == CAPPED_HASH_PROJECT


def test_none_mode_prompt_carries_no_count(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "none")
    p = ef.build_turn_extraction_prompt("t", "", "[S1 | SUBJECT, typed] hi", max_facts=None,
                                        entity_hints="")
    assert "up to" not in p and "identity-relevant first" not in p
    assert "Extract facts about the SUBJECT as structured triples." in p
    assert ef.turn_prompt_hash(False) != CAPPED_HASH_GENERAL
    assert ef.turn_prompt_hash(True) != CAPPED_HASH_PROJECT


def test_unknown_mode_is_refused(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "top10")
    with pytest.raises(ValueError, match="fact_count_mode"):
        ef.turn_fact_count_mode()


def test_none_mode_keeps_every_accepted_fact(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "none")
    prompts = []
    monkeypatch.setattr(env.ef, "call_llm", _llm(_many_facts(150), prompts))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["settings"]["fact_count_mode"] == "none"
    assert rec["counts"]["accepted"] == 150
    assert rec["counts"]["facts_after_validation"] == 150
    assert "over_per_chunk_cap" not in rec["post_gate_drops"]
    assert len(_facts(env)) == 150
    assert "up to" not in prompts[0][0]
    # the stamp names the prompt the facts were actually extracted with
    assert all(f["extraction_prompt_hash"] != CAPPED_HASH_GENERAL for f in _facts(env))


def test_capped_mode_still_truncates_per_chunk(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    monkeypatch.setattr(env.ef, "_get_extraction_caps",
                        lambda *a, **k: {"max_facts": 5, "input_char_budget": 24000})
    prompts = []
    monkeypatch.setattr(env.ef, "call_llm", _llm(_many_facts(6), prompts))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["settings"]["fact_count_mode"] == "capped"
    assert "Extract up to 5 facts" in prompts[0][0]
    assert rec["post_gate_drops"]["over_per_chunk_cap"] == 1
    assert len(_facts(env)) == 5
    assert all(f["extraction_prompt_hash"] == CAPPED_HASH_GENERAL for f in _facts(env))


def test_batch_reads_the_mode_from_the_saved_plan(monkeypatch):
    """At process time the environment may differ from submit time; the chunk plan
    saved at submit decides."""
    import baselayer.extract_facts as ef
    import baselayer.turn_contract as tc
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")        # env says capped
    facts = [dict(f, evidence_spans=[{"turn_id": f"{CONV}:0", "span": "x y z",
                                      "evidence_kind": "prose"}],
                  source_turn_id=f"{CONV}:0", voice_class="own_typed", grounding="prose")
             for f in _many_facts(9)]
    g = tc.GateResult(candidates=9, accepted=facts)
    plan = {"max_facts": 2, "per_chunk_cap": 2, "total_chars": 100, "fact_count_mode": "none"}
    out = ef.finalize_turn_facts([(None, g)], 1, plan, project_session=False)
    assert len(out) == 9
    plan_old = {"max_facts": 20, "per_chunk_cap": 2, "total_chars": 100}   # pre-switch state file
    out = ef.finalize_turn_facts([(None, g)], 1, plan_old, project_session=False)
    assert len(out) == 2


def test_the_plan_carries_the_mode(monkeypatch):
    import baselayer.extract_facts as ef
    import baselayer.turn_contract as tc
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", LONG)]
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "none")
    assert ef.turn_extraction_plan(turns, "chatgpt")["fact_count_mode"] == "none"
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    assert ef.turn_extraction_plan(turns, "chatgpt")["fact_count_mode"] == "capped"
