# Lexicon Evaluation — Shared Dictionary for Identity Layers

**Status:** PARTIALLY IMPLEMENTED (S56 — schema + YAML created, not yet enforced in authoring)
**Session:** 55 (evaluated), 56 (lexicon_schema.yaml + lexicon.yaml created)

## Verdict: YES — Standardize the Container, Not the Contents

A lexicon would improve:
- **Consistency** across users (standardize structural elements)
- **Structured referencing** (A3 references P2 with verifiable links)
- **Trace pointers** (stable IDs enable provenance linking)
- **Machine readability** (programmatic validation, automated diffs)
- **Compression enforcement** (schema limits = word budget per element)
- **Pipeline reproducibility** (structural shape is deterministic)

A lexicon should NOT standardize:
- Axiom/prediction names (COHERENCE, INTEGRITY — these are personal)
- Directive content (must be authored fresh per user)
- Detection signatures (domain-specific)
- Communication approach and narrative orientation (deeply personal)

## Sample Structure

```yaml
element_types:
  axiom: {id_prefix: "A", required: [id, name, definition, active_when]}
  prediction: {id_prefix: "P", required: [id, name, trigger, detection, directive]}
  context_mode: {id_prefix: "C", required: [id, domain, directives]}

tags: [CONTESTED, THIN_DATA, PARKED, DERIVED]

cross_reference_syntax: "see A3" / "depends on A3+A5"

provenance_format: "provenance: [F-1204, F-2891]"
```

## Implementation Recommendation

Start with identifiers and cross-references only (A1-A11, P1-P8). YAML companion alongside markdown layers. Don't formalize full schema in one step.

## Verbosity Assessment

| User | Words | Tokens | Signal % | Compressible |
|------|-------|--------|----------|-------------|
| User A | 5,647 | ~7,510 | 55% | ~2,200 (39%) |
| Subject B | 1,379 | ~1,834 | 77% | ~280 (20%) |
| User B | 1,598 | ~2,126 | 72% | ~380 (24%) |

Main compression sources in User A's layers: redundant restatements (~800w), inferrable axiom interactions (~250w), formulaic template overhead in PREDICTIONS (~500w), parked trading patterns (~170w), convincing prose (~400w).
