# Plan: Temporal Recurrence Dedup

**Status:** IMPLEMENTED (S56)
**Session:** 55 (designed), 56 (implemented)
**Problem:** 20 mentions in one day ≠ 20 recurrences. Frequency inflation.

## Design

24-hour daily windowing:
- Group conversations into temporal windows
- Count each window as 1 recurrence regardless of conversations within it
- Handles cross-model dedup (same topic, same day, ChatGPT + Claude = 1 recurrence)

Store both:
- `recurrence_count` — windowed (deduped) value
- `raw_recurrence_count` — original count (diagnostics)

## Adjustments

- Normalization ceiling: 300 → 150 (lower max after dedup)
- Recurrence floor thresholds: 50/30 → 30/18 (proportional reduction)
- No change to WEIGHT_RECURRENCE (0.35)

## Key Principle (Developer)

"Take learnings from trading temporality. If talked about 20 times in one day, should not dominate."
"If you do the same thing across 4 models, asking 4 questions to each, that does not make it 4x more important."

## Effort: ~1.5 hours code + MANDATORY full re-score
## Dependencies: Run AFTER Plans 1 & 2 (new facts need scoring)
