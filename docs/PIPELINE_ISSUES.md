# Pipeline issues, found by running the pipeline

Opened 2026-08-19. Every entry here was found by running the pipeline end to end on a real
corpus, not by reading source. Each says what was observed, what it costs, and its status.

The rule this file exists to serve: **when a guard fires constantly, suspect the guard.**

---

## FIXED

### P-01 Sequential extraction never tiered facts, so the author gate could not pass
**Fixed `aa55b1c`, 2026-08-19.** `baselayer extract` produced a corpus with
`knowledge_tier='untiered'` on every row. The author fact-floor gate counts
`knowledge_tier='identity'`, read 0, and refused to run:

```
Error: Fact quality below threshold - identity-tier facts: 0/50, source documents: 1/5.
```

Measured on a fresh 124-fact corpus: **124 of 124 untiered**. After tiering, **89 identity /
35 contextual**, so the gate reads 89/50 and passes. It had been rejecting a corpus whose
other signals were healthy (35 distinct predicates against a floor of 15).

`tier_facts_by_predicate` was never broken. It had two call sites, batch extraction and
post-compose traceability, and traceability runs **after** compose. So the sequential ordering
was extract, author (gate reads zero, exits), compose, tier: the gate depended on a step that
runs later in the pipeline.

🚨 **Second occurrence of one defect.** The gate previously counted `fact_type`, which nothing
populates; it was moved to `knowledge_tier` in 2026-05-19 for exactly that reason. The move
corrected the field and not the coverage, so the same symptom returned on the one path that
still did not write it. `tests/test_tiering_call_sites.py` now asserts on **call sites** rather
than behavior, because a unit test of the function passes in both the broken and fixed states.

---

## OPEN

### P-02 Text import does not split, so one file is one conversation and one message
An 88,679-character book imported as **1 conversation, 1 message**. Extraction still works,
because `extract_facts.py` chunks internally on paragraph breaks, so this does not lose facts.

What it does affect:
- **The `source documents: 5` half of the fact-floor gate**, which counts
  `DISTINCT source_conversation_id`. A single-document corpus can never satisfy it.
- Any downstream step that chunks **per message** treats the whole corpus as one unit.

⚠️ Consequence worth stating plainly: **a book is a legitimate corpus and the gate rejects it.**
Both halves of the gate failed on the Zitkala-Sa training corpus for reasons unrelated to
quality. One is now fixed; this one is not.

**Candidate fix:** split text imports on section or paragraph boundaries into multiple
conversations, or count messages rather than conversations in the gate.

### P-03 The `source_docs < 5` check treats corpus breadth as corpus quality
Distinct from P-02. Even with splitting, five is an arbitrary floor with no measurement behind
it, and it hard-exits rather than warning. Breadth is a real signal for a person-specification
built from conversations, and meaningless for a single authored work.

**Candidate fix:** make it a warning, or scale it to the import source type.

### P-04 `fact_type` and `fact_class` are written but never assigned
100% of a fresh 124-fact corpus carries `fact_type='unclassified'` and
`fact_class='unclassified'`. These are the pre-D-056 taxonomy that `knowledge_tier` replaced.
They are not read by any gate today, so this costs nothing at present, but two always-constant
columns invite exactly the mistake P-01 records: a future check written against a field nothing
populates.

**Candidate fix:** drop them, or populate them, but do not leave them as available footguns.

---

## How to add an entry

Run something. Record what you observed, with the number. Say what it costs and what it does
not cost. If a guard fired, say whether the guard or the system was wrong, and prove it rather
than asserting it.
