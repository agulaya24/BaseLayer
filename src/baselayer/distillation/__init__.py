"""Interpretive distillation: exhaustive, auditable authoring. EXPERIMENTAL.

Turns a fact base into an evidence package in which every fact receives a recorded
disposition, then authors the specification layers from that package. Successor to the
capped selector behind `baselayer author`, which remains the shipped default; removing
the old path is a separate decision that has not been made.

EXPERIMENTAL STATUS, stated in code because docs get skipped:

- The tests are mutation tests over the citation audit and ledger metrics (`validate()`
  and `audit_citations()` in `distill.py`) plus call-shape tests of the request
  `author_from_package.py` sends, and the artifact stamps (tests/test_artifact_stamps.py),
  which run `distill.main`, `assemble()` and `author_from_package.main` end to end against
  fake clients. The package stratification in `assemble.py` is not tested beyond that.
  `distill_batch.py` runs end to end against a fake batch client
  (tests/test_distill_batch.py); `convergence.py` is exercised only in dry runs.
- Most measurements behind the design were taken on a single 407-fact corpus. Two
  defects invisible at that size appeared on the first large run.
- `convergence.py` does not call `validate()`, so its output is UNSTRIPPED: fabricated
  fact ids are not removed from what it writes. `distill_batch.py` validates and strips
  through the same `call_json` as `distill.py` and writes the same trees.
- Cost is real: a large corpus is hours and tens of dollars per layer. Read the cost
  notes in `distill.py` before running anything unbudgeted.

CLI surface: `baselayer distill`, `baselayer assemble`, `baselayer author-from-package`.
Each module also runs directly: `python src/baselayer/distillation/distill.py --help`.
`distill_batch.py` (all layers' leaves in one Message Batches submission) and
`convergence.py` (a study harness) run as modules only.
"""
