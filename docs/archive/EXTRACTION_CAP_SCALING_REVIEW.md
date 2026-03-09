# Plan C4: Extraction Cap Scaling — Implementation Review

**Status:** Implemented (Session 55-56), needs evaluation
**Reviewed:** 2026-03-01 (Session 57)
**Original plan:** `docs/plans/EXTRACTION_CAP_SCALING_PLAN.md`

## Current Implementation

The extraction cap scaling system is fully implemented across two files:

### config.py — EXTRACTION_CAPS

4-tier message-count-based scaling:

| Tier | Messages | Max Facts | Input Budget |
|------|----------|-----------|-------------|
| 1    | 1-10     | 10        | 12,000 chars |
| 2    | 11-30    | 20        | 18,000 chars |
| 3    | 31-60    | 35        | 24,000 chars |
| 4    | 61+      | 50        | 24,000 chars |

Absolute ceiling: 50 facts, 24,000 chars.

### extract_facts.py — _get_extraction_caps()

- Reads from `EXTRACTION_CAPS["tiers"]` config
- Falls back to legacy `MAX_FACTS_PER_CONVERSATION` (20) if no tier matches
- Applied in three extraction paths:
  1. `extract_facts_from_conversation()` — standard extraction
  2. `_abstract_project_conversation()` — project conversation abstraction (input budget only)
  3. `extract_identity_from_project_conversation()` — identity extraction (max facts only; input budget via abstraction)
- Dynamic `max_facts` value is communicated to the LLM via the prompt for self-prioritization
- `validate_structured_response()` enforces the cap as a hard ceiling on returned facts

## Assessment: Is the Implementation Sufficient?

**Yes, for current scale.** The implementation is clean, well-integrated, and addresses the core problem (double truncation). Specific strengths:

1. **Config-driven.** Tiers are defined in config.py, not hardcoded in extraction logic. Easy to tune.
2. **LLM-aware.** The max_facts cap is communicated in the prompt, enabling the model to self-prioritize rather than just having output truncated.
3. **Three-path coverage.** All extraction paths (standard, project abstraction, identity) use the same scaling function.
4. **Backward compatible.** Legacy `MAX_FACTS_PER_CONVERSATION` preserved as fallback.

## Edge Cases Not Handled

### 1. Per-message truncation at 1,500 chars (MODERATE)
In `extract_facts_from_conversation()`, each message is hard-truncated at 1,500 chars before the input budget check:
```python
text = msg["text"][:1500]
```
This means a conversation with 10 messages of 3,000 chars each (30K total) effectively becomes 15K after per-message truncation, fitting comfortably in tier 2's 18K budget. The per-message cap and the input budget cap interact but are not coordinated. In practice this is fine — 1,500 chars per message preserves the vast majority of signal in conversational exchanges — but very long single messages (essays, journal entries) lose their second half regardless of input budget.

**Risk:** Low. Journal entries and long monologues are the only affected case, and those are rare in conversation data.

### 2. Tier 3 and Tier 4 share the same input budget (LOW)
Both 31-60 message and 61+ message conversations get 24,000 chars input budget. A 100-message conversation gets the same text window as a 35-message one. The fact cap scales (35 vs 50), but the LLM sees the same amount of input text, so the extra 15 fact slots may go unused because later-conversation content is truncated.

**Risk:** Low at current scale. At User A's current data (avg conversation ~22 messages), very few conversations hit tier 4. If the system processes longer-form corpora (multi-hour sessions, Slack threads), this would become a real limitation.

**Fix if needed:** Tier 4 could use a higher input budget (e.g., 36,000 chars), but this increases API cost per conversation and may exceed Haiku's optimal input range.

### 3. No scaling for assistant message length (LOW)
The per-message truncation applies equally to user and assistant messages. In Claude Code sessions, the `_abstract_project_conversation()` function handles this well (strips code, keeps only short assistant messages). But in standard extraction, long assistant responses (which often contain summaries, analysis, or recommendations the user engaged with) are truncated to 1,500 chars. The user's response to that truncated message may reference content that was cut.

**Risk:** Low. Assistant messages rarely contain identity signal directly — the user's reaction to them does.

### 4. No validation that LLM respects the cap (LOW)
`validate_structured_response()` enforces the cap by slicing `raw_facts[:effective_cap]`. This is correct, but it means the LLM might return 80 facts when asked for 50, and the last 30 are silently dropped. Those 30 might contain higher-quality facts than some of the first 50.

**Risk:** Low in practice. LLMs generally respect the "up to N" instruction, and confidence-based filtering (< 0.3 dropped) provides a secondary quality gate.

## What Would a Re-extraction with New Caps Yield?

### Current Data Profile (User A)

- 1,892 conversations total
- 5,270 total facts extracted (4,610 active after consolidation)
- Average ~2.8 facts per conversation
- Extraction was done with the legacy 20-fact cap for the bulk of conversations

### Estimated Yield from Re-extraction

To estimate the uplift, we need the message-count distribution of conversations:

| Tier | Messages | Old Cap | New Cap | Delta per Convo | Est. Conversations | Est. New Facts |
|------|----------|---------|---------|-----------------|-------------------|---------------|
| 1    | 1-10     | 20      | 10      | -10 (but few convos hit 20) | ~800 | ~0 net (most extract < 10) |
| 2    | 11-30    | 20      | 20      | 0               | ~700              | 0              |
| 3    | 31-60    | 20      | 35      | +15 potential    | ~250              | +500-1,000     |
| 4    | 61+      | 20      | 50      | +30 potential    | ~142              | +800-1,500     |

**Estimated net uplift: 1,300-2,500 additional facts from tiers 3-4 conversations.**

However, this assumes the LLM can actually find 35-50 identity-relevant facts in those conversations. In practice, many long conversations are repetitive (trading sessions, debugging sessions) where additional facts would be low-novelty duplicates. Realistic uplift after dedup and consolidation: **500-1,000 net new active facts** (~10-20% increase).

Tier 1 conversations might actually extract *fewer* facts than before (cap reduced from 20 to 10), but this is the correct behavior — short conversations rarely contain 10+ genuine identity facts.

### For Other Corpora

- **User B (36 newsletter posts):** Most are likely tier 1-2. Minimal impact.
- **Subject B (9 journal entries):** Tier 1. No impact.
- **New users with long conversation history:** Significant benefit for anyone with 100+ conversations averaging 30+ messages.

## Cost Estimate for Full Re-extraction

### Haiku API (current default)
- 1,892 conversations
- Average input: ~3,000 tokens per conversation (after truncation)
- Average output: ~400 tokens per conversation (structured JSON)
- Input cost: 1,892 * 3,000 / 1M * $0.80 = **$4.54**
- Output cost: 1,892 * 400 / 1M * $4.00 = **$3.03**
- **Total: ~$7.57**

### With Batch API (50% discount)
- **Total: ~$3.79**

### Marginal cost of new caps specifically
The caps don't change the number of API calls — every conversation is processed regardless. The only cost increase is:
- Tier 3-4 conversations send ~50-100% more input text (18K-24K vs 12K)
- Tier 3-4 conversations return ~75-150% more output (35-50 facts vs 20)

This affects ~392 conversations (tier 3+4), adding roughly:
- Extra input: 392 * 3,000 / 1M * $0.80 = **$0.94**
- Extra output: 392 * 300 / 1M * $4.00 = **$0.47**
- **Marginal cost of new caps: ~$1.41** (or $0.71 via Batch API)

## Recommendation

**Do NOT re-extract solely for cap scaling.** Here is why:

1. **The current 5,270 extracted facts already represent a well-saturated extraction.** At 2.8 facts per conversation average, the system is extracting meaningfully from conversations. The cap was rarely the binding constraint — most conversations naturally produce fewer than 20 facts.

2. **The uplift is moderate and heavily concentrated in duplicate-prone long conversations.** The 500-1,000 net new facts from tiers 3-4 would mostly come from long trading sessions and debugging conversations — domains already well-represented (or deliberately downweighted) in the fact base.

3. **Cap scaling is already in place for new extractions.** Any new conversations imported will benefit from the scaled caps immediately. The cost of re-extraction ($3.79 via Batch) is low, but the human cost of re-running the full downstream pipeline (score, classify, tier, consolidate, author) is significant.

4. **If re-extraction is done for OTHER reasons** (relationship extraction improvements, prompt refinements, predicate additions), the new caps will automatically apply. Bundle, don't run separately.

### If Re-extraction Is Bundled with Other Changes

If a re-extraction run is planned for relationship extraction (Plan 1) or other prompt improvements, the new caps add zero marginal complexity and ~$1.41 marginal cost. In that case, they should be included.

### One Tuning Consideration

The tier 1 cap of 10 facts may be too conservative for journal entries. A single rich journal entry (1 message, 2,000+ words) could contain 15-20 genuine identity facts. Consider adding a content-length heuristic alongside message count:

```
If message_count < 10 BUT total_char_count > 8,000:
    Use tier 2 caps (20 facts, 18K budget)
```

This is a minor enhancement, not a blocker.
