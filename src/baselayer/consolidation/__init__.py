"""Consolidation: turn an authored specification into what an agent is served.

Runs after authoring. Reads the authored layer JSON (anchors, core, predictions) and
writes only into an output directory. No stage calls a model. Three separate builders
(`python -m baselayer.consolidation.build`) make the stage inputs that need judgement:
duplicate verdicts, the trigger grouping and the category assignment. They call a model
through a pluggable backend, and each writes a file a hand-made input could replace.

Every stage is a function from JSON files to one JSON file, runnable alone and
replaceable, and every output carries a stamp (code sha, inputs hash, parameters,
run id). The raw layers stay the record: no stage rewrites claim text.

Stages, in execution order (file in, file out):

    claims      spec dir                                   -> claims.json
    overlap     claims.json                                -> overlap.json
    dedupe      claims.json, overlap.json [judgements]     -> dedupe.json
    always_on   claims.json                                -> always_on.json
    triggers    claims.json, always_on.json [grouping]     -> triggers.json
    categories  claims.json, triggers.json [assignment]    -> categories.json
    render      all of the above                           -> served.txt (+ served.stamp.json), index.json
    checks      all of the above, and the spec dir again   -> checks.json

Modules:
    common      stamps, hashing, atomic LF writes, the --out guard
    spec        the claims stage: load layer JSON, render each claim's served block
    overlap     shared-evidence overlap; the pair-judge interface (not run)
    dedupe      duplicate groups as a mapping, never a rewrite
    always_on   standing-claim selection by a stated, parameterised rule
    triggers    Active_When clauses grouped into triggers, many-to-many to claims
    categories  triggers assigned to data-defined categories, with coverage counts
    render      the served text and the machine-readable index the pull tool reads
    checks      the mechanical checks over every output
    port        convert the 2026-09-28/29 prototype files into stage inputs
    run         orchestration and the `baselayer consolidate` entry point

Builders (model calls, outside `consolidate`):
    backends    API / claude -p / fake backends, the checkpointed call runner, limit backoff
    judge       duplicate judge: blind SAME / FACET / DISTINCT, both orders   -> judgements
    grouper     trigger grouper: split conditions into clauses, group clauses -> grouping
    categorize  category builder: data-defined categories over the triggers   -> assignment
    build       `python -m baselayer.consolidation.build` entry point, stamps
"""

CONSOLIDATION_VERSION = "consolidation/1"
STAMP_VERSION = "consolidation-stamp/1"

STAGES = ("claims", "overlap", "dedupe", "always_on", "triggers", "categories", "render", "checks")
