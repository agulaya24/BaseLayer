"""Interpretive distillation: exhaustive, auditable authoring. EXPERIMENTAL.

Turns a fact base into an evidence package in which every fact receives a recorded
disposition, then authors the specification layers from that package. Successor to the
capped selector behind `baselayer author`, which remains the shipped default; removing
the old path is a separate decision that has not been made.

EXPERIMENTAL STATUS, stated in code because docs get skipped:

- The test suite is 10 mutation tests over the citation audit (`validate()` and
  `audit_citations()` in `distill.py`). It exercises none of the other four modules.
- Most measurements behind the design were taken on a single 407-fact corpus. Two
  defects invisible at that size appeared on the first large run.
- `distill_batch.py` and `convergence.py` do not call `validate()`, so their output is
  UNSTRIPPED: fabricated fact ids are not removed from what they write.
- Cost is real: a large corpus is hours and tens of dollars per layer. Read the cost
  notes in `distill.py` before running anything unbudgeted.

CLI surface: `baselayer distill`, `baselayer assemble`, `baselayer author-from-package`.
Each module also runs directly: `python src/baselayer/distillation/distill.py --help`.
`distill_batch.py` and `convergence.py` are study harnesses and run as scripts only.
"""
