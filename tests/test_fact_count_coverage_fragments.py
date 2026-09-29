"""
fact_count_mode `coverage_fragments`: `coverage` plus ONE instruction about fragments and
unclear questions. Everything else must equal `coverage` (and so `none`): no count or ordering
in the prompt, the output budget sized from citable characters, no per-chunk truncation, on the
sequential and the batch path. Only the prompt wording (and so its hash) differs.
"""
from tests.test_fact_count_mode import (  # noqa: F401  (env is a fixture)
    CAPPED_HASH_GENERAL, CAPPED_HASH_PROJECT, LONG, TURNS, _llm, _many_facts)
from tests.test_turn_extraction import CONV, _facts, _records, _seed, env  # noqa: F401

COVERAGE = ("Extract every distinct fact the subject's own words support; do not stop early "
            "and do not restate the same fact in different words.")
FRAGMENTS = ("If a turn is a fragment or a question whose meaning is not clear from its "
             "context, extract nothing from it.")
MODE = "coverage_fragments"


def _prompt(ef, mode, monkeypatch, project=False):
    import baselayer.turn_contract as tc
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", mode)
    turns = [tc.Turn(f"{CONV}:0", CONV, "subject", "own_typed", LONG)]
    plan = ef.turn_extraction_plan(turns, "chatgpt")
    ch = ef.build_turn_chunks(turns, "chatgpt", plan["input_char_budget"])[0]
    return plan, ch, ef.turn_chunk_prompt("t", ch, plan, project)


def test_mode_is_accepted_and_uncounted(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", MODE)
    assert ef.turn_fact_count_mode() == MODE
    assert ef.uncounted_mode(MODE)


def test_prompt_has_both_sentences_and_no_count(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    for project in (False, True):
        plan, _ch, p = _prompt(ef, MODE, monkeypatch, project)
        assert plan["fact_count_mode"] == MODE
        assert COVERAGE in p and FRAGMENTS in p
        assert "Extract up to" not in p and "identity-relevant first" not in p


def test_prompt_is_coverage_plus_one_sentence(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    for project in (False, True):
        _p, _c, frag = _prompt(ef, MODE, monkeypatch, project)
        _p, _c, cov = _prompt(ef, "coverage", monkeypatch, project)
        assert frag.count(FRAGMENTS) == 1
        assert frag.replace(" " + FRAGMENTS, "", 1) == cov


def test_budget_equals_coverage(monkeypatch):
    import baselayer.extract_facts as ef
    plan_f, ch, _ = _prompt(ef, MODE, monkeypatch)
    plan_c, _ch, _ = _prompt(ef, "coverage", monkeypatch)
    assert ef.turn_chunk_max_tokens(ch, plan_f) == ef.turn_chunk_max_tokens(ch, plan_c) \
        == ef.turn_output_budget(ch.citable_chars)


def test_hash_distinct_from_every_mode_and_capped_is_pinned(monkeypatch):
    import baselayer.extract_facts as ef
    monkeypatch.setattr(ef, "_get_known_entities_for_prompt", lambda: "")
    for project in (False, True):
        h = ef.turn_prompt_hash(project, mode=MODE)
        others = {m: ef.turn_prompt_hash(project, mode=m) for m in ("capped", "none", "coverage")}
        assert h not in others.values(), others
    assert ef.turn_prompt_hash(False, mode="capped") == CAPPED_HASH_GENERAL
    assert ef.turn_prompt_hash(True, mode="capped") == CAPPED_HASH_PROJECT


def test_keeps_every_accepted_fact_and_stamps_its_hash(env, monkeypatch):
    _seed(env, turns=TURNS)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setenv("BASELAYER_FACT_COUNT_MODE", MODE)
    prompts = []
    monkeypatch.setattr(env.ef, "call_llm", _llm(_many_facts(150), prompts))
    env.ef.run_extraction()
    rec = _records(env)[-1]
    assert rec["settings"]["fact_count_mode"] == MODE
    assert rec["counts"]["facts_after_validation"] == 150
    assert "over_per_chunk_cap" not in rec["post_gate_drops"]
    assert len(_facts(env)) == 150
    assert COVERAGE in prompts[0][0] and FRAGMENTS in prompts[0][0]
    assert "up to" not in prompts[0][0]
    h = env.ef.turn_prompt_hash(False, mode=MODE)
    assert all(f["extraction_prompt_hash"] == h for f in _facts(env))


def test_batch_finalize_does_not_truncate():
    import baselayer.extract_facts as ef
    import baselayer.turn_contract as tc
    facts = [dict(f, evidence_spans=[{"turn_id": f"{CONV}:0", "span": "x y z",
                                      "evidence_kind": "prose"}],
                  source_turn_id=f"{CONV}:0", voice_class="own_typed", grounding="prose")
             for f in _many_facts(9)]
    g = tc.GateResult(candidates=9, accepted=facts)
    plan = {"max_facts": 2, "per_chunk_cap": 2, "total_chars": 100, "fact_count_mode": MODE}
    assert len(ef.finalize_turn_facts([(None, g)], 1, plan,
                                      project_session=False)) == 9
