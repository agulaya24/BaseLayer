# Plan: Relationship Extraction Improvement

**Status:** PARTIALLY IMPLEMENTED (S56)
**Session:** 55 (designed), 56 (implemented steps 1-3)
**Current:** 0.8% of facts are relationship category (pre-S56 extraction; re-extraction needed to realize gains)
**Target:** 3-5% relationship facts

## Implementation Status

| Step | Status | Notes |
|------|--------|-------|
| 1. Add 8 relationship predicates to config.py | DONE (S56) | relates_to, collaborates_with, mentored_by, raised_by, friends_with, reports_to, admires, conflicts_with. Total predicates: 47. |
| 2. Add relationship aliases to extract_facts.py | DONE (S56) | 30+ aliases added across all predicates. |
| 3. Modify extraction prompt with relationship emphasis | DONE (S56) | Entity map hints fed into extraction prompts. |
| 4. Use entity_map as extraction input | DONE (S56) | Entity map loaded and injected into extraction context. |
| 5. Post-extraction enrichment pass | NOT DONE | Optional. Needs re-extraction run to evaluate whether enrichment is still needed. |

**To realize gains:** A re-extraction run is needed. New predicates and prompt changes are in place but existing facts were extracted before these changes.

## Root Causes (original)

1. **Predicate gap** — Only 3 relationship predicates (married_to, parents, lost) out of 39 total
2. **Prompt bias** — Extraction prompt focuses on "facts about the USER" with no relationship emphasis
3. **Minimal entity map** — Only 6 entries, used for normalization only, not fed into extraction
4. **Passive category routing** — "relationship" is one of 11 options with no emphasis

## Effort: ~1 hour code (DONE) + re-extraction (~$4-8 API, NOT DONE)
## Dependencies: Run before temporal dedup (Plan 3)
