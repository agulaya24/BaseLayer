"""
The turn path's default fact_count_mode is `coverage` (config TURN_FACT_COUNT_MODE).

- With BASELAYER_FACT_COUNT_MODE unset, the mode, the plan, the prompt and the prompt hash
  are coverage's.
- `capped` is still selectable per run, and its prompt hash is still the pinned pre-switch hash.
- The legacy path does not read the mode: its prompt hash does not move with it.
- A plan without the key (a batch state file written before the switch) still reads as
  `capped`, because that is the prompt those chunks were submitted with.
"""

import pytest

from tests.test_fact_count_mode import CAPPED_HASH_GENERAL, CAPPED_HASH_PROJECT, LONG
from tests.test_turn_extraction import (  # noqa: F401  (env is a fixture)
    CONV, _fact, _facts, _records, _seed, env)


@pytest.fixture
def ef(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.delenv("BASELAYER_FACT_COUNT_MODE", raising=False)
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    return ef


def test_default_mode_is_coverage(ef):
    assert ef.turn_fact_count_mode() == "coverage"


def test_default_prompt_hash_is_coverage(ef):
    for project in (False, True):
        assert ef.turn_prompt_hash(project) == ef.turn_prompt_hash(project, mode="coverage")
        assert ef.turn_prompt_hash(project) != ef.turn_prompt_hash(project, mode="capped")


def test_default_plan_carries_coverage(ef):
    import baselayer.turn_contract as tc
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", LONG)]
    assert ef.turn_extraction_plan(turns, "chatgpt")["fact_count_mode"] == "coverage"


def test_capped_still_selectable_and_pinned(ef, monkeypatch):
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    assert ef.turn_fact_count_mode() == "capped"
    assert ef.turn_prompt_hash(False) == CAPPED_HASH_GENERAL
    assert ef.turn_prompt_hash(True) == CAPPED_HASH_PROJECT


def test_legacy_prompt_hash_does_not_depend_on_the_mode(ef, monkeypatch):
    default = ef.legacy_prompt_hash(ef.build_extraction_prompt)
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "capped")
    assert ef.legacy_prompt_hash(ef.build_extraction_prompt) == default


def test_pre_switch_plan_still_reads_capped(ef):
    assert ef.uncounted_mode(None) is False


def test_default_run_prompt_and_record(env, monkeypatch):
    monkeypatch.delenv("BASELAYER_FACT_COUNT_MODE", raising=False)
    _seed(env, turns=[(0, "subject", "own_typed", "user", LONG)])
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    prompts = []

    def call(prompt, schema=None, retries=None, max_tokens=None):
        prompts.append(prompt)
        return {"facts": [_fact("chooses the slower option", [("S1", "I choose the slower option")],
                                predicate="practices", category="habit")]}
    monkeypatch.setattr(env.ef, "call_llm", call)
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["settings"]["fact_count_mode"] == "coverage"
    assert "Extract up to" not in prompts[0]
    assert env.ef.TURN_COVERAGE_SENTENCE in prompts[0]
    h = env.ef.turn_prompt_hash(False, mode="coverage")
    assert _facts(env) and all(f["extraction_prompt_hash"] == h for f in _facts(env))
