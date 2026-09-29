"""
fact_count_mode `coverage`: `none` plus ONE sentence asking for complete coverage with no
number. Everything else must equal `none`: no count or ordering in the prompt, the output
budget sized from citable characters, no per-chunk truncation, on the sequential and the
batch path. Only the prompt wording (and so its hash) differs from `none`.
"""
from tests.test_fact_count_mode import (  # noqa: F401  (env is a fixture)
    CAPPED_HASH_GENERAL, CAPPED_HASH_PROJECT, LONG, TURNS, _llm, _many_facts)
from tests.test_turn_extraction import CONV, _facts, _records, _seed, env  # noqa: F401

SENTENCE = ("Extract every distinct fact the subject's own words support; do not stop early "
            "and do not restate the same fact in different words.")


def _prompt(ef, mode, monkeypatch):
    import baselayer.turn_contract as tc
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", mode)
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", LONG)]
    plan = ef.turn_extraction_plan(turns, "chatgpt")
    ch = ef.build_turn_chunks(turns, "chatgpt", plan["input_char_budget"])[0]
    return plan, ch, ef.turn_chunk_prompt("t", ch, plan, False)


def test_coverage_prompt_has_the_sentence_and_no_count(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    plan, _ch, p = _prompt(ef, "coverage", monkeypatch)
    assert plan["fact_count_mode"] == "coverage"
    assert SENTENCE in p
    assert "Extract up to" not in p and "identity-relevant first" not in p


def test_coverage_prompt_is_none_plus_one_sentence(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    _p, _c, cov = _prompt(ef, "coverage", monkeypatch)
    _p, _c, none = _prompt(ef, "none", monkeypatch)
    assert cov.replace(" " + SENTENCE, "", 1) == none


def test_coverage_budget_equals_none(monkeypatch):
    import baselayer.extract_facts as ef
    plan_c, ch, _ = _prompt(ef, "coverage", monkeypatch)
    plan_n, _ch, _ = _prompt(ef, "none", monkeypatch)
    assert ef.turn_chunk_max_tokens(ch, plan_c) == ef.turn_chunk_max_tokens(ch, plan_n) \
        == ef.turn_output_budget(ch.citable_chars)


def test_coverage_hash_differs_from_both_and_capped_is_pinned(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    for project in (False, True):
        cov = ef.turn_prompt_hash(project, mode="coverage")
        assert cov != ef.turn_prompt_hash(project, mode="none")
        assert cov != ef.turn_prompt_hash(project, mode="capped")
    assert ef.turn_prompt_hash(False, mode="capped") == CAPPED_HASH_GENERAL
    assert ef.turn_prompt_hash(True, mode="capped") == CAPPED_HASH_PROJECT


def test_coverage_keeps_every_accepted_fact(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", "coverage")
    prompts = []
    monkeypatch.setattr(env.ef, "call_llm", _llm(_many_facts(150), prompts))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["settings"]["fact_count_mode"] == "coverage"
    assert rec["counts"]["facts_after_validation"] == 150
    assert "over_per_chunk_cap" not in rec["post_gate_drops"]
    assert len(_facts(env)) == 150
    assert SENTENCE in prompts[0][0] and "up to" not in prompts[0][0]
    cov_hash = env.ef.turn_prompt_hash(False, mode="coverage")
    assert all(f["extraction_prompt_hash"] == cov_hash for f in _facts(env))


def test_batch_finalize_does_not_truncate_coverage():
    import baselayer.extract_facts as ef
    import baselayer.turn_contract as tc
    facts = [dict(f, evidence_spans=[{"turn_id": f"{CONV}:0", "span": "x y z",
                                      "evidence_kind": "prose"}],
                  source_turn_id=f"{CONV}:0", voice_class="own_typed", grounding="prose")
             for f in _many_facts(9)]
    g = tc.GateResult(candidates=9, accepted=facts)
    plan = {"max_facts": 2, "per_chunk_cap": 2, "total_chars": 100, "fact_count_mode": "coverage"}
    assert len(ef.finalize_turn_facts([(None, g)], 1, plan,
                                      project_session=False)) == 9
