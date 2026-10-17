"""
The referent of a turn-contract corpus (TURN_CONTRACT.md §5, subject resolution).

The extractor names the subject in several ways: the subject's configured name,
the name without its surname, or a generic form ("this person", "the user"). On the
legacy path the referent lives in entity_map.json `_user_names`, which a scripted
run never fills, and the shared alias tuple in `normalize_subject` lacks "this person",
so a corpus can carry its own subject under three or four labels. Turn mode takes the
referent from the import config (`subject_names`), refuses to run without one, and
maps every one of those forms to `user`.

These tests CALL the normaliser; a populated config is not evidence it works.
"""

import pytest

import baselayer.turn_contract as tc
from baselayer.import_config import config_from_dict

NAMES = ["Dana", "Dana Reyes"]


def _ref(names=NAMES, aliases=None):
    return tc.Referent(names=tuple(names), aliases=aliases or {})


@pytest.mark.parametrize("raw", ["Dana", "dana", "Dana Reyes", "  DANA REYES ", "dana  reyes",
                                 "this person", "This Person", "the person", "the user",
                                 "user", "User", "", None])
def test_configured_names_and_generic_forms_resolve_to_user(raw):
    assert tc.normalize_turn_subject(raw, _ref()) == "user"


@pytest.mark.parametrize("raw", ["Sam Ortiz", "Reyes Corp", "the user's wife", "Danae"])
def test_other_subjects_are_left_alone(raw):
    assert tc.normalize_turn_subject(raw, _ref()) == raw.strip()


def test_legacy_alias_tuple_is_untouched():
    """The fix is scoped to turn mode. The shared normaliser still reads
    "this person" as a third party, because changing it would re-subject
    facts already stored on legacy corpora (AUDN keys on the subject)."""
    from baselayer.extract_facts import normalize_subject
    assert normalize_subject("this person") == "this person"


def test_referent_comes_from_the_import_config():
    ref = tc.referent_from_config(config_from_dict({"subject_names": NAMES}))
    assert ref.names == tuple(NAMES)
    assert tc.normalize_turn_subject("Dana Reyes", ref) == "user"


@pytest.mark.parametrize("names", [[], ["", "   "]])
def test_an_unconfigured_referent_is_refused(names):
    with pytest.raises(tc.ReferentNotConfigured):
        tc.referent_from_config(config_from_dict({"subject_names": names}))


def test_gate_requires_a_referent():
    """No caller can skip subject resolution by omission."""
    import inspect
    p = inspect.signature(tc.gate_facts).parameters["referent"]
    assert p.default is inspect.Parameter.empty and p.kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# refusal: every turn-mode entry point, before any model call
# ---------------------------------------------------------------------------

from tests.test_turn_extraction import _seed, env  # noqa: E402,F401  (env is a fixture)
from tests.test_turn_batch_extract import benv  # noqa: E402,F401  (fixture)


def _unconfigure(env):
    (env.root / "data" / "import_config.json").unlink()


def _no_model(*a, **k):
    raise AssertionError("a model call was made before the referent check")


def test_sequential_turn_run_refuses_without_a_referent(env, monkeypatch):
    _seed(env)
    _unconfigure(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    monkeypatch.setattr(env.ef, "call_llm", _no_model)
    with pytest.raises(env.ef.TurnContractViolation, match="subject_names"):
        env.ef.run_extraction()


def test_legacy_run_does_not_need_a_referent(env, monkeypatch):
    _seed(env, with_turns=False)
    _unconfigure(env)
    monkeypatch.setattr(env.ef, "call_llm", lambda *a, **k: {"facts": []})
    env.ef.run_extraction()


def test_batch_submit_refuses_without_a_referent(benv, monkeypatch):
    _seed(benv)
    _unconfigure(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    with pytest.raises(benv.ef.TurnContractViolation, match="subject_names"):
        benv.be.run_submit()
    assert benv.batches.submitted is None


def test_batch_process_refuses_without_a_referent(benv, monkeypatch):
    _seed(benv)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    benv.be.run_submit()
    _unconfigure(benv)
    benv.batches.results_for = lambda ids: []
    with pytest.raises(benv.ef.TurnContractViolation, match="subject_names"):
        benv.be.run_process()


def test_turn_run_stores_the_subject_as_user(env, monkeypatch):
    """End to end: the extractor names the subject three ways, all stored as `user`."""
    from tests.test_turn_extraction import _fact, _facts
    facts = []
    for name in ("Dana Reyes", "this person", "Dana"):
        f = _fact("short emails to vendors " + name, [("S2", "Keep the email short.")])
        f["subject"] = name
        facts.append(f)
    _seed(env)
    monkeypatch.setenv("BASELAYER_TURN_CONTRACT", "1")
    from tests.test_turn_extraction import _fake_llm
    monkeypatch.setattr(env.ef, "call_llm", _fake_llm(facts))
    env.ef.run_extraction()
    assert {f["subject"] for f in _facts(env)} == {"user"}
