# Batch Extraction + Model Update Spec (S98)

## Problem
Running 12 high-priority subjects (~8,500 files) via sequential Haiku API calls would take ~55 hours. We have batch infrastructure that should do it in <1 hour at 50% cost — but it's broken (document mode threshold, custom_id length, stale models, no prompt caching).

## Changes Required

### 1. Update Model IDs (3x cost reduction on compose)

**config.py:**
```
EXTRACTION_API_MODEL: claude-haiku-4-5-20251001 → KEEP (still current)
LAYER_GENERATION_MODEL: claude-sonnet-4-20250514 → claude-sonnet-4-6
LAYER_REVIEW_MODEL: claude-opus-4-20250514 → claude-opus-4-6
```

**agent_pipeline.py cost calc (line 701):**
```
OLD: cost = (input_tokens * 15 + output_tokens * 75) / 1_000_000
NEW: cost = (input_tokens * 5 + output_tokens * 25) / 1_000_000
```

### 2. Fix batch_extract.py (8 items)

| # | Fix | File:Line | Change |
|---|-----|-----------|--------|
| 1 | Document mode bypasses MIN_MESSAGES threshold | batch_extract.py:149 | `min_msgs = 1 if document_mode else MIN_MESSAGES_FOR_EXTRACTION` (DONE in S98) |
| 2 | Truncate custom_id to 64 chars | batch_extract.py:200 | `"custom_id": conv_id[:64]` |
| 3 | Model-aware cost estimate | batch_extract.py:225 | Read pricing from config dict, not hardcoded |
| 4 | Handle canceled/expired result types | batch_extract.py:478-489 | Explicit handling, don't count as errors |
| 5 | Batch size guard | batch_extract.py:214 | `if len(requests) > 100_000: error` |
| 6 | Add "ended" to state guard | batch_extract.py:132 | Add to the completion check set |
| 7 | Add "canceling" status display | batch_extract.py:300 | New elif branch |
| 8 | Store conv_id mapping for truncated IDs | batch_extract.py:200 | Dict mapping truncated → full ID |

### 3. Wire batch into pipeline command

**cli.py cmd_pipeline:**
Currently calls `extract_facts.main()` (sequential).
Change to:
1. Import from source dir
2. Submit batch via `batch_extract.run_submit(document_mode=True, skip_extracted=True)`
3. Poll status in loop (sleep 30s between checks)
4. Process results via `batch_extract.run_process(resume=True)`
5. Continue to author → compose

The polling loop makes the pipeline synchronous from the user's perspective while using async batch on the backend. User sees progress updates.

### 4. Add prompt caching to extraction

**For sequential extraction (extract_facts.py):**
- The extraction system prompt (schema + instructions) is identical for every conversation in a subject
- Add `cache_control` to the system message block
- ~90% savings on input tokens after first call
- Cached tokens don't count toward rate limits

**For batch extraction (batch_extract.py):**
- Same system prompt across all requests in batch
- Add `cache_control: {"type": "ephemeral", "ttl": "1h"}` to shared system content
- Batch + cache discounts stack

### 5. Consider Structured Outputs (future)

**NOT for this immediate fix** — would require:
- Restructuring the extraction call to use `output_config.format` instead of prompt-based JSON instruction
- Testing that extraction quality doesn't degrade with constrained decoding
- Verifying SDK version supports it

**Benefit:** Zero JSON parse failures. Eliminates retry loops.
**Risk:** Constrained decoding may reduce extraction quality (model has less freedom in output).
**Decision:** Test in next overnight GPU comparison. If quality holds, adopt.

### 6. Fix ChromaDB distance metric

**extract_facts.py line 1518:**
```
OLD: similarity = max(0, 1 - (distance ** 2) / 2)  # L2 formula
NEW: similarity = max(0, 1 - distance)              # Cosine formula
```
Or use `config.py`'s `chromadb_dist_to_similarity()` helper which handles both.

**Update CLAUDE.md:** Remove stale note "ChromaDB uses L2 distance (not cosine despite S56 attempt)". Code now creates cosine collections.

## Execution Order

1. Update model IDs + cost calc (config.py, agent_pipeline.py) — 5 min
2. Fix batch_extract.py (8 items) — 30 min
3. Wire batch into cmd_pipeline — 20 min
4. Add prompt caching — 15 min
5. Fix ChromaDB distance — 5 min
6. Test on one subject (Seth Godin, smallest at 200 files) — verify end-to-end
7. Submit all 12 as batch

## Cost Estimate (revised with current pricing)

| Step | Per Subject | 12 Subjects |
|------|------------|-------------|
| Extraction (Haiku batch) | ~$0.35 | ~$4.20 |
| Extraction (with cache) | ~$0.15 | ~$1.80 |
| Authoring (Sonnet 4.6, 3 layers) | ~$0.15 | ~$1.80 |
| Compose (Opus 4.6) | ~$0.12 | ~$1.44 |
| **Total** | **~$0.42** | **~$5.04** |

Previous estimate was $12. With model updates + caching + batch: **~$5**.
