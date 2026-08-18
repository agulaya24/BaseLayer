"""The similarity converter must use the collection's actual distance space.

WHY THIS EXISTS. `chromadb_dist_to_similarity` applied the L2 formula to every collection.
Its docstring claimed the difference was "small for the values we care about". Measured
against the real cosine `memory_facts` collection, the error is +0.46 to +0.47 across the
returned range, and it inverts the threshold decision.

Three of five call sites queried `memory_facts`, which is created cosine. Those three feed
`verify`, `provenance` and `trace_claim`: the surfaces this project sells as auditability.
A similarity inflated by 0.47 makes an unrelated fact look like supporting evidence.

These tests fail against the old implementation and pass against the current one.
"""
import pytest

from baselayer.config import chromadb_dist_to_similarity, collection_space


def _old_implementation(dist):
    """The behaviour being removed, kept so the tests can prove they detect it."""
    if dist <= 0:
        return 1.0
    return round(max(0.0, min(1.0, 1.0 - (dist ** 2) / 2.0)), 4)


class _FakeCollection:
    def __init__(self, metadata):
        self.metadata = metadata


def test_cosine_space_uses_one_minus_distance():
    """A cosine collection: similarity is 1 - d, not 1 - d^2/2."""
    assert chromadb_dist_to_similarity(0.5477, "cosine") == pytest.approx(0.4523, abs=1e-4)


def test_l2_space_keeps_the_squared_formula():
    """The control. An l2 collection must still use the old formula, which was correct there."""
    assert chromadb_dist_to_similarity(0.5477, "l2") == pytest.approx(0.8500, abs=1e-4)


def test_the_old_implementation_would_fail_the_cosine_case():
    """Proof these tests detect the defect rather than merely describing the fix."""
    got = _old_implementation(0.5477)
    assert got == pytest.approx(0.8500, abs=1e-4)
    assert abs(got - 0.4523) > 0.39, "the error the old code introduced on a cosine collection"


def test_threshold_decision_inverts():
    """The reason this mattered. At a 0.85 gate the old formula passed a 0.45 match."""
    d = 0.5477
    assert _old_implementation(d) >= 0.85          # old: passes the gate
    assert chromadb_dist_to_similarity(d, "cosine") < 0.85   # correct: does not


@pytest.mark.parametrize("d", [0.30, 0.4523, 0.5477, 0.70, 0.90])
def test_cosine_error_was_never_small(d):
    """The old docstring claimed the difference was small. It is 0.25 to 0.50."""
    assert _old_implementation(d) - chromadb_dist_to_similarity(d, "cosine") > 0.24


def test_space_is_required_and_unknown_values_raise():
    """No default. A default is what applied the wrong formula silently."""
    with pytest.raises(TypeError):
        chromadb_dist_to_similarity(0.5)          # missing space
    with pytest.raises(ValueError):
        chromadb_dist_to_similarity(0.5, "euclidean")


def test_collection_space_reads_metadata_and_defaults_to_chroma_default():
    assert collection_space(_FakeCollection({"hnsw:space": "cosine"})) == "cosine"
    assert collection_space(_FakeCollection({})) == "l2"      # Chroma's own default
    assert collection_space(_FakeCollection(None)) == "l2"


def test_boundaries():
    assert chromadb_dist_to_similarity(0.0, "cosine") == 1.0
    assert chromadb_dist_to_similarity(2.0, "cosine") == 0.0   # clamped
    assert chromadb_dist_to_similarity(0.0, "l2") == 1.0
