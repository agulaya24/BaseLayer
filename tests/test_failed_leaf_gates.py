"""A leaf the model could not finish must not reach an author silently. No API calls.

Design decision 2026-10-16: a 50-fact leaf stopped at max_tokens in the batch and again in
the sequential repair. Leaf requests set no thinking budget, so the model's thinking shared the
16,000-token ceiling and the reply text came back EMPTY; the repair re-sent the same ceiling with
"emit fewer themes", which does not shrink thinking. The tree stored the leaf as _parse_failed,
assemble packaged it without comment, and 50 facts were missing from the anchors package
(5,015 dispositioned of 5,065) with one log line as the only signal.

Two gates: (1) a retry after truncation gets a larger output ceiling; (2) assemble refuses a tree
holding a _parse_failed leaf unless the caller opts in, and the package records the count.
"""
import pytest

from baselayer.distillation import assemble as asm
from baselayer.distillation import distill
from tests.test_artifact_stamps import V, _tree

GOOD = '{"themes": [], "singularities": [], "contradictions": [], "dispositions": {}}'


def _stats():
    return {"in": 0, "out": 0, "parse_fail": [], "parse_fail_final": [], "repaired": [],
            "truncated": [], "schema_fail": [], "schema_repaired": [], "schema_fail_final": [],
            "_expect_ids": None}


def _scripted(monkeypatch, replies):
    seen = []

    def fake_call(cl, model, prompt, maxtok=16000):
        seen.append(maxtok)
        return replies.pop(0)
    monkeypatch.setattr(distill, "call", fake_call)
    return seen


def test_retry_after_truncation_gets_a_larger_output_ceiling(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = _scripted(monkeypatch, [("", 10, 16000, "max_tokens"), (GOOD, 10, 900, "end_turn")])
    d, stop = distill.call_json(None, "m", "p", 16000, "L1-01", _stats())
    assert d is not None and stop == "end_turn"
    assert seen == [16000, distill.REPAIR_MAX_TOKENS]
    assert distill.REPAIR_MAX_TOKENS > 16000


def test_batch_truncation_retry_also_gets_the_larger_ceiling(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = _scripted(monkeypatch, [(GOOD, 10, 900, "end_turn")])
    d, _ = distill.call_json(None, "m", "p", 16000, "L1-14", _stats(),
                             first=("", 10, 16000, "max_tokens"))
    assert d is not None
    assert seen == [distill.REPAIR_MAX_TOKENS]


def test_a_parse_failure_that_was_not_truncated_keeps_its_ceiling(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = _scripted(monkeypatch, [("not json", 10, 500, "end_turn"), (GOOD, 10, 900, "end_turn")])
    distill.call_json(None, "m", "p", 16000, "L1-02", _stats())
    assert seen == [16000, 16000]


def test_an_invalid_json_retry_names_the_error_and_the_quote_rule(monkeypatch, tmp_path):
    """Design decision 2026-10-17: a leaf quoting the person's words that contain double quotes
    returned complete but invalid JSON twice, because the retry said only "not valid JSON"."""
    monkeypatch.chdir(tmp_path)
    prompts = []

    def fake_call(cl, model, prompt, maxtok=16000):
        prompts.append(prompt)
        if len(prompts) == 1:
            return ('{"themes": [{"statement": "he wrote \'not "Can one party adopt it?"\' here"}]}',
                    10, 900, "end_turn")
        return (GOOD, 10, 900, "end_turn")
    monkeypatch.setattr(distill, "call", fake_call)
    d, _ = distill.call_json(None, "m", "p", 16000, "L1-60", _stats())
    assert d is not None
    retry = prompts[1]
    assert "line 1 column" in retry               # the parser's own location
    assert '\\"' in retry and "escape" in retry.lower()


def _tree_with_failed_leaf(run_id):
    t = _tree(run_id, V)
    t["leaves"].append({"themes": [], "singularities": [], "contradictions": [],
                        "dispositions": {}, "_parse_failed": True,
                        "_chunk": "predicate-14/102 believes(50)", "_n": 50})
    return t


def test_assemble_refuses_a_tree_with_a_failed_leaf(capsys):
    with pytest.raises(SystemExit, match="(?i)failed leaf|could not be parsed"):
        asm.assemble([_tree_with_failed_leaf("r1")])


def test_assemble_allows_a_failed_leaf_only_when_asked_and_records_it(capsys):
    pkg = asm.assemble([_tree_with_failed_leaf("r1")], allow_failed_leaves=True)
    assert pkg["stamp"]["failed_leaves"] == 1
    assert pkg["stamp"]["facts_in_failed_leaves"] == 50


def test_a_clean_tree_records_zero_failed_leaves(capsys):
    pkg = asm.assemble([_tree("r1", V)])
    assert pkg["stamp"]["failed_leaves"] == 0
    assert pkg["stamp"]["facts_in_failed_leaves"] == 0
