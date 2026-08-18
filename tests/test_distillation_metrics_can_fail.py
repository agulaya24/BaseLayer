"""Mutation tests: every quality metric must be provably capable of reporting a failure.

🚨 WHY THIS EXISTS. A four-reviewer audit found that three of the four metrics in the
run ledger were arithmetically incapable of failing:

  citations_clean_pct     validate() STRIPS out-of-chunk ids before the block that REPORTS them,
                          so both violation branches are unreachable and the rate is pinned at 100.
  sing_survival_pct       root singularities are a mechanical copy of the leaf lane, deduped by
                          fact_id, so survival is bounded at 100% by construction.
  root_citations_resolved root themes are copied from already-stripped leaves, so the unresolved
                          set is empty by construction.

THE STANDARD THIS ENFORCES: a guard must be proven to FAIL on a known-bad input before it is
trusted, and to PASS on a good one.

⚠️ READ THIS BEFORE TRUSTING THE SUITE. The first five tests exercise `validate()` ONLY, and
`validate()` computes NONE of the three ledger metrics above. They prove the DETECTOR returns
violations; the pipeline then strips those violations, and for a long time the metrics were
computed downstream of the strip, so this suite passed with all three still tautological. A test
that exercises an adjacent function proves the wrong thing, which is the same defect it was
written to catch, one level up.

The `test_ledger_*` tests at the bottom close that gap: they assert the counts SURVIVE the strip
onto the stored leaf and that the aggregated rate moves off 100. Those are the tests that bind
the metric rather than its neighbour.

No API key and no database are required: the mutations target pure functions.

Run:  python -m pytest tests/test_distillation_metrics_can_fail.py -q
"""
from baselayer.distillation import distill


CHUNK_IDS = ["aaaaaaaa", "bbbbbbbb", "cccccccc"]


def _leaf(**over):
    d = {
        "themes": [{"statement": "a theme", "fact_ids": ["aaaaaaaa", "bbbbbbbb"]}],
        "singularities": [{"fact_id": "cccccccc", "verbatim": "a singular fact",
                           "why": "because"}],
        "contradictions": [],
        "dispositions": {"aaaaaaaa": "theme", "bbbbbbbb": "theme", "cccccccc": "singular"},
    }
    d.update(over)
    return d


def test_clean_leaf_passes():
    """The control. A guard that fires on good input is as useless as one that never fires."""
    bad = distill.validate(_leaf(), ids=CHUNK_IDS)
    assert bad == [], "clean leaf reported violations: %s" % bad


def test_theme_citing_a_fabricated_id_is_REPORTED():
    """MUTATION: a theme cites an id that is not in its chunk.

    This is the fabrication the strip exists to remove. Removing it is correct. Removing it
    WITHOUT recording it converts 'the model invented evidence' into 'this theme has no evidence',
    which is a different and quieter defect.
    """
    d = _leaf(themes=[{"statement": "a theme", "fact_ids": ["aaaaaaaa", "FABRICAT"]}])
    bad = distill.validate(d, ids=CHUNK_IDS)
    assert any("not in this chunk" in b for b in bad), (
        "FABRICATED THEME ID WAS NOT REPORTED. violations=%s ids_after=%s"
        % (bad, d["themes"][0]["fact_ids"]))


def test_invented_singularity_is_REPORTED():
    """MUTATION: a singularity names an id that is not in the chunk.

    The singularity lane's whole claim is verbatim fidelity to a real fact. An invented one must
    be dropped AND counted; dropping it silently makes the lane look perfect.
    """
    d = _leaf(singularities=[{"fact_id": "DEADBEEF", "verbatim": "invented", "why": "x"}])
    bad = distill.validate(d, ids=CHUNK_IDS)
    assert any("not in this chunk" in b for b in bad), (
        "INVENTED SINGULARITY WAS NOT REPORTED. violations=%s remaining=%s"
        % (bad, d["singularities"]))


def test_disposition_for_a_foreign_id_is_REPORTED():
    """MUTATION: a leaf dispositions a fact that belongs to a different chunk.

    Dispositions are merged across leaves with dict.update(), which is last-writer-wins. A verdict
    for a foreign id therefore OVERWRITES a real verdict from the leaf that actually read that
    fact. Evidence this is live rather than theoretical: a shipped ledger row records 408
    dispositions on a 407-fact corpus.
    """
    d = _leaf(dispositions={"aaaaaaaa": "theme", "bbbbbbbb": "theme", "cccccccc": "singular",
                            "NOTMINE1": "theme"})
    bad = distill.validate(d, ids=CHUNK_IDS)
    assert bad, "DISPOSITION FOR A FOREIGN ID WAS NOT REPORTED. dispositions=%s" % d["dispositions"]


def test_missing_disposition_is_REPORTED():
    """The one check that already worked. Kept as the positive control for the suite itself."""
    d = _leaf(dispositions={"aaaaaaaa": "theme"})
    bad = distill.validate(d, ids=CHUNK_IDS)
    assert bad, "a leaf omitting two of three dispositions reported nothing"


# ---------------------------------------------------------------------------
# LEDGER METRICS. These bind the number that gets WRITTEN, not the detector beside it.
# ---------------------------------------------------------------------------


# NO REPLICA HERE. The previous version of this file re-implemented main()'s arithmetic and
# called that "binding the numbers that actually get written". It was not: pinning clean_pct at
# the line that writes the ledger left all eight tests passing. A test that copies the code it
# checks tests the copy. `distill.audit_citations` is now the single implementation and main()
# calls it, so mutating the real path breaks these tests.


def _leaf_with(fabricated_theme_ids=0, fabricated_singularity=False):
    """Build a leaf, plant fabrications, run the real validate(), return it audit-ready."""
    themes = [{"statement": "t", "fact_ids": ["aaaaaaaa"] +
               ["FABRICA%d" % i for i in range(fabricated_theme_ids)]}]
    sings = [{"fact_id": "cccccccc", "verbatim": "v", "why": "w"}]
    if fabricated_singularity:
        sings.append({"fact_id": "NOTMINE1", "verbatim": "invented", "why": "w"})
    d = _leaf(themes=themes, singularities=sings)
    distill.validate(d, ids=CHUNK_IDS)
    d["_ids"] = CHUNK_IDS
    return d


def test_ledger_records_what_the_stripper_removed():
    """MUTATION: two fabricated ids. The COUNT must survive onto the stored leaf.

    Before the fix, validate() detected and then stripped, and nothing downstream could tell a
    leaf that never fabricated from one that fabricated and was cleaned.
    """
    d = _leaf(themes=[{"statement": "t", "fact_ids": ["aaaaaaaa", "FABRICA1", "FABRICA2"]}])
    distill.validate(d, ids=CHUNK_IDS)
    assert d.get("_stripped"), "no _stripped record survived validate()"
    assert d["_stripped"]["theme_ids"] == 2, (
        "expected 2 stripped theme ids, got %s" % d["_stripped"])


def test_ledger_clean_pct_CAN_report_below_100():
    """The test the old suite could not make. Plant fabrications, assert the RATE moves.

    A rate that cannot leave 100 is not a measurement.
    """
    d = _leaf_with(fabricated_theme_ids=2)
    agg = distill.audit_citations([d])
    assert agg["fabricated"] == 2, agg
    assert agg["clean_pct"] < 100.0, (
        "CLEAN RATE STILL PINNED AT 100 WITH 2 PLANTED FABRICATIONS: %s" % agg)
    assert agg["survived_stripper"] == 0, (
        "a fabricated id survived the stripper, which breaks the invariant: %s" % agg)


def test_ledger_clean_pct_is_100_on_a_clean_leaf():
    """The control. If this ever falls below 100 the metric has become a false positive."""
    d = _leaf_with()
    agg = distill.audit_citations([d])
    assert agg["fabricated"] == 0 and agg["clean_pct"] == 100.0, agg


def test_ledger_counts_a_fabricated_SINGULARITY_too():
    """MUTATION: an invented singularity, not just an invented theme id.

    Both counters feed the rate, and every earlier test planted only theme ids. That gap let a
    mutation zeroing the singularity counter pass the whole suite. A metric with two inputs
    needs a test per input.
    """
    d = _leaf_with(fabricated_singularity=True)
    assert d["_stripped"]["singularities"] == 1, d.get("_stripped")
    agg = distill.audit_citations([d])
    assert agg["fabricated"] == 1, agg
    assert agg["clean_pct"] < 100.0, (
        "A FABRICATED SINGULARITY DID NOT MOVE THE RATE: %s" % agg)


def test_ledger_counts_BOTH_kinds_together():
    """Control on the arithmetic: two theme ids plus one singularity must total three."""
    d = _leaf_with(fabricated_theme_ids=2, fabricated_singularity=True)
    agg = distill.audit_citations([d])
    assert agg["fabricated"] == 3, agg
