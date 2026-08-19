"""Every extraction path must tier facts before authoring can gate on the tier.

The bug this guards against was not a broken function. `tier_facts_by_predicate`
worked correctly and was well tested. It was simply never called on the sequential
extraction path, so `baselayer extract` produced a corpus where every row had
knowledge_tier='untiered', and the author fact-floor gate, which counts
knowledge_tier='identity', read 0 and refused to run on a healthy corpus.

That is why these tests assert on CALL SITES rather than on behaviour. A unit test of
the function passes in both the broken and fixed states.

The same defect had already occurred once: the gate previously counted `fact_type`,
which nothing populated, and was moved to `knowledge_tier` in 2026-05-19. The move
fixed two of the three paths, so the identical symptom returned on the third.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).parent.parent / "src" / "baselayer"
FN = "tier_facts_by_predicate"


def _calls_in(path: pathlib.Path) -> set[str]:
    """Every function name called anywhere in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def test_sequential_extraction_tiers_facts():
    """`baselayer extract` must tier, or the author gate reads zero on a fresh corpus."""
    assert FN in _calls_in(SRC / "extract_facts.py"), (
        "extract_facts.py never calls tier_facts_by_predicate. A corpus extracted "
        "sequentially reaches authoring untiered, and the fact-floor gate rejects it."
    )


def test_batch_extraction_tiers_facts():
    assert FN in _calls_in(SRC / "batch_extract.py"), (
        "batch_extract.py never calls tier_facts_by_predicate."
    )


def test_traceability_still_tiers():
    """The post-compose call remains, as the idempotent backstop for older corpora."""
    assert FN in _calls_in(SRC / "cli.py"), (
        "cli.py no longer calls tier_facts_by_predicate; corpora extracted before "
        "the sequential-path fix would never be tiered."
    )


def test_tiering_is_idempotent_by_construction():
    """Safe to call on all three paths: it only touches rows that are not yet tiered."""
    src = (SRC / "extract_facts.py").read_text(encoding="utf-8", errors="replace")
    start = src.index(f"def {FN}")
    body = src[start:start + 2000]
    assert "knowledge_tier IS NULL OR knowledge_tier = 'untiered'" in body, (
        "tier_facts_by_predicate must only update untiered rows, otherwise calling it "
        "from several paths would overwrite tiers assigned by extraction."
    )
