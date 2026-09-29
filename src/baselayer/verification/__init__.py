"""Post-specification verification.

Runs once, after a specification has been authored, and reports. It never feeds
back into authoring: authoring must not see verification output, or the next
specification is graded by the thing that shaped it.

Layout:
    definitions   the standards every check applies, fixed before any rater output exists
    spec_io       load a spec directory (JSON layers or served markdown) into claims
    corpus        open a corpus database without writing to it; resolve facts, voice, turns
    deterministic checks that need no model
    raters        the rater interface: fake (tests), claude -p (subscription), API (explicit)
    model_checks  prompts, task builders and interpretation for model-judged checks
    pricing       dated price table and the pre-run estimate
    report        one JSON and one markdown report per spec
    run           orchestration and the `baselayer verify-spec` entry point

Every database is opened read-only (or from a snapshot copy under --out), and
the only directory written is --out.
"""

VERIFY_VERSION = "verify-spec/1"
