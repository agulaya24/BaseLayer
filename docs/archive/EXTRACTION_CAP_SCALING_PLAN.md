# Plan: Extraction Cap Scaling

**Status:** IMPLEMENTED (S56), reviewed S57 (sufficient — see EXTRACTION_CAP_SCALING_REVIEW.md)
**Session:** 55 (designed), 56 (implemented), 57 (reviewed)
**Current:** 4-tier scaling in config.py EXTRACTION_CAPS (replaces hardcoded 20)

## Design

Message-count scaling with floor and ceiling:
- 6-15 messages → 10 facts
- 16-40 messages → 20 facts (current behavior)
- 40+ messages → 20 + 1 per 2 extra messages
- Ceiling: 50 facts

Also scale input text budget:
- Current: all conversations get 12,000 chars regardless of length
- Proposed: base 12K, +100 per message above 20, max 24K

Tell the LLM about the cap for self-prioritization.

## Key Insight

Double truncation: long conversations are both input-capped (12K chars) AND output-capped (20 facts). Deeper topics that emerge later in long conversations are systematically under-extracted.

## Effort: ~1.5 hours code + re-extraction
## Expected Impact: 10-15% more facts from long conversations (~500-700 additional)
## Dependencies: Can combine with Plan 1 (relationships) for single re-extraction
