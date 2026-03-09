# Plan C8: score_facts.py O(N*M) Refactor

**Status:** Plan only, not implemented
**Created:** 2026-03-01 (Session 57)
**Priority:** Medium now, Critical at 10x scale
**Original finding:** `docs/plans/INDEXING_VECTORIZATION_OPTIMIZATION.md` (item 7)

## Problem Statement

`score_facts.py::compute_fact_significance()` scores each fact by scanning the entire messages table for keyword co-occurrence. At current scale this is borderline acceptable; at 10x scale it becomes a multi-hour blocking operation.

## Current Algorithm Analysis

### Flow per Fact

```
For each fact (N = 4,610):
  1. get_fact_keywords(fact_text) → 2-4 keywords
  2. Build SQL: SELECT ... FROM messages WHERE role='user' GROUP BY conversation_id
                HAVING (SUM(CASE WHEN LOWER(content_text) LIKE '%keyword1%' ...) + ...) >= min_co_occur
  3. Execute scan across ALL user messages (M = ~20,000 user messages)
  4. For matching conversations: get timestamps, compute windowed recurrence
  5. Compute depth_score, recurrence_normalized, floor, final_score
```

### Time Complexity

- **Step 2-3** is the bottleneck: each fact executes a full table scan of the messages table
- SQL LIKE '%keyword%' cannot use indexes (leading wildcard)
- GROUP BY conversation_id requires sorting or hash aggregation
- Per-fact query touches all ~20,000 user messages

**Total operations: N * M = 4,610 * 20,000 = ~92M row scans**

(The CLAUDE.md states 4,610 * 40,997 = ~189M, but only user messages are scanned, so the actual count is closer to 92M. Still substantial.)

### Measured Performance

At current scale, the scoring loop runs at ~10-20 facts/second (observed from progress logging). Full scoring of 4,610 facts takes **~4-8 minutes**. This is acceptable but not fast.

### At 10x Scale (46,000 facts, 200,000 user messages)

- Operations: 46,000 * 200,000 = **9.2 BILLION row scans**
- Estimated runtime: **40-80 minutes** (assuming same per-row cost)
- At 100x scale: **6-13 hours**

## Proposed Approach

### Core Idea: Inverted Keyword Index

Instead of scanning all messages for each fact's keywords, pre-build an inverted index mapping keywords to conversations, then look up each fact's keywords in the index.

### Phase 1: Pre-compute Message Keyword Sets (One-Time Pass Over Messages)

```python
def build_keyword_conversation_index(conn) -> dict[str, set[str]]:
    """Build inverted index: keyword -> set of conversation_ids.

    Single pass over all user messages. O(M) time, O(K*C) space
    where K = unique keywords and C = avg conversations per keyword.
    """
    keyword_to_convos = defaultdict(set)

    rows = conn.execute("""
        SELECT conversation_id, content_text
        FROM messages
        WHERE role = 'user'
    """).fetchall()

    for conv_id, text in rows:
        # Tokenize and normalize (same logic as get_fact_keywords stop words)
        words = set(re.findall(r'\b[a-z]{3,}\b', text.lower()))
        words -= STOP_WORDS  # Same stop_words set from get_fact_keywords
        for word in words:
            keyword_to_convos[word].add(conv_id)

    return keyword_to_convos
```

### Phase 2: Score Facts via Index Lookup

```python
def compute_fact_significance_indexed(conn, fact_id, fact_text, source_conv_id,
                                       keyword_index, conv_metadata) -> dict:
    """Score a fact using pre-built inverted index. O(K) per fact."""

    keywords = get_fact_keywords(fact_text)
    if not keywords:
        return zero_result()

    # Find conversations containing 2+ keywords (set intersection)
    min_co_occur = min(2, len(keywords))

    # For each conversation, count how many keywords appear
    conv_keyword_counts = defaultdict(int)
    for kw in keywords:
        for conv_id in keyword_index.get(kw, set()):
            conv_keyword_counts[conv_id] += 1

    # Filter to conversations with sufficient co-occurrence
    matching_convos = [
        conv_id for conv_id, count in conv_keyword_counts.items()
        if count >= min_co_occur
    ]

    if not matching_convos:
        return zero_result()

    # Look up pre-cached metadata (turns, timestamps, avg_msg_length)
    # instead of running per-fact SQL queries
    raw_recurrence = len(matching_convos)
    ...  # rest of scoring logic unchanged
```

### Phase 3: Pre-cache Conversation Metadata

```python
def build_conversation_metadata(conn) -> dict:
    """Pre-compute per-conversation stats. Single pass, O(M) time."""
    metadata = {}

    rows = conn.execute("""
        SELECT m.conversation_id,
               COUNT(*) as user_turns,
               AVG(LENGTH(m.content_text)) as avg_msg_length
        FROM messages m
        WHERE m.role = 'user'
        GROUP BY m.conversation_id
    """).fetchall()

    for conv_id, turns, avg_len in rows:
        metadata[conv_id] = {
            "user_turns": turns,
            "avg_msg_length": avg_len,
        }

    # Add timestamps
    ts_rows = conn.execute("""
        SELECT id, created_at FROM conversations
    """).fetchall()
    for conv_id, created_at in ts_rows:
        if conv_id in metadata:
            metadata[conv_id]["created_at"] = created_at

    return metadata
```

### Revised Scoring Flow

```
SETUP (once):
  1. Build keyword_index: keyword -> {conv_ids}     O(M)
  2. Build conv_metadata: conv_id -> {turns, ts}     O(M)

PER FACT (N times):
  3. get_fact_keywords(fact_text) → 2-4 keywords     O(1)
  4. For each keyword, look up conv_ids from index    O(K * avg_convos_per_keyword)
  5. Count co-occurrences, filter to 2+ matches       O(K * C_k) where C_k = matching convos
  6. Look up metadata for matching convos              O(R) where R = matching count
  7. Compute windowed recurrence, depth, score         O(R)
```

## Expected Speedup

### New Time Complexity

- Setup: O(M) — single pass over all messages
- Per-fact: O(K * C_avg) where K = 2-4 keywords, C_avg = average conversations per keyword
- Total: O(M + N * K * C_avg)

### Estimated Runtime at Current Scale

- Setup: ~2-5 seconds (scan 20K messages, tokenize)
- Per-fact: ~0.01ms (dict lookups, set operations)
- 4,610 facts * 0.01ms = ~0.05 seconds
- **Total: ~5-10 seconds** (vs current 4-8 minutes)

**Speedup: ~30-50x**

### At 10x Scale

- Setup: ~20-50 seconds (scan 200K messages)
- Per-fact: ~0.05ms (larger sets)
- 46,000 facts * 0.05ms = ~2.3 seconds
- **Total: ~25-55 seconds** (vs projected 40-80 minutes)

**Speedup: ~80-100x**

## Semantic Equivalence Verification

The refactored algorithm MUST produce identical scores to the current algorithm for the same input data. Key equivalence points:

1. **Keyword extraction** (`get_fact_keywords`): Unchanged. Same function, same stop words.
2. **Co-occurrence logic**: Current SQL checks `LOWER(content_text) LIKE '%keyword%'` per conversation. The inverted index pre-computes the same set of {keyword -> conversations} using `re.findall(r'\b[a-z]{3,}\b', text.lower())`. These are NOT identical:
   - SQL LIKE `%keyword%` matches substrings (e.g., `%trade%` matches "traded", "trading", "trade")
   - Regex `\b[a-z]{3,}\b` matches whole words only ("trade" but not "traded" or "trading")

   **This is the critical divergence.** The current SQL approach casts a wider net via substring matching. The inverted index approach with word-boundary tokenization would narrow matches.

   **Resolution options:**
   - **Option A: Preserve substring semantics.** Use character n-grams or substring matching in the index. More complex, larger index.
   - **Option B: Accept word-boundary semantics.** Slightly different results but arguably more correct (matching "trade" but not "traded" as a separate word). Requires validation that score distributions don't meaningfully shift.
   - **Option C: Stemming.** Apply Porter stemming to both index and keywords. "Trading" -> "trade", "traded" -> "trade". Better semantic matching than either current approach.

   **Recommendation: Option B with validation.** Run both algorithms on the full dataset, compare scores. If < 5% of facts change score by more than 1 point, accept the new semantics.

3. **Windowed recurrence**: Unchanged. Same `_apply_temporal_windowing` function operating on the same conversation timestamps.
4. **Depth scoring**: Unchanged formula. Requires pre-cached `user_turns` per conversation (from Phase 3).
5. **Recurrence floors**: Unchanged thresholds, unchanged logic.

## Migration Path (Backward Compatibility)

### Step 1: Add New Function Alongside Old

Add `compute_fact_significance_indexed()` as a new function. Keep `compute_fact_significance()` unchanged. Add `--use-index` flag to score_facts.py.

### Step 2: Validation Run

Run both algorithms on the full fact set. Compare output:
```python
for fact in facts:
    old_result = compute_fact_significance(conn, ...)
    new_result = compute_fact_significance_indexed(conn, ..., keyword_index, conv_metadata)
    assert abs(old_result["significance_score"] - new_result["significance_score"]) < threshold
```

### Step 3: Switch Default

Once validated, make the indexed path the default. Keep old function available with `--legacy` flag for one release cycle.

### Step 4: Remove Old Function

After one full pipeline run with the indexed path producing identical results, remove the legacy function.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Semantic divergence (substring vs word) | High | Medium | Validation run comparing old vs new scores |
| Memory pressure from keyword index | Low | Low | Index is ~10-50MB for 200K messages |
| Edge cases in tokenization | Medium | Low | Comprehensive stop word list already exists |
| Regression in score quality | Low | High | Side-by-side validation before switching |
| Increased code complexity | Medium | Low | Clear separation of index-building and scoring |

### Memory Usage Estimate

- Keyword index: ~50,000 unique words * avg 100 conv_ids per word * 40 bytes per conv_id = ~200MB at 10x scale
- Conversation metadata: ~20,000 convos * 100 bytes = ~2MB
- **Total: ~200MB at 10x scale** — acceptable for a batch scoring job.

At current scale: ~20MB. Trivial.

## Implementation Estimate

| Phase | Description | Hours | Dependencies |
|-------|-------------|-------|-------------|
| 1     | Build inverted keyword index function | 1.5   | None |
| 2     | Build conversation metadata cache | 1.0   | None |
| 3     | Implement indexed scoring function | 2.0   | Phase 1, 2 |
| 4     | Add CLI flags (--use-index, --legacy) | 0.5   | Phase 3 |
| 5     | Validation: run both paths, compare | 1.5   | Phase 3 |
| 6     | Fix divergences, tune stop words | 1.0   | Phase 5 |
| 7     | Switch default, documentation | 0.5   | Phase 6 |

**Total: ~8 hours** (matches original estimate of 6-8h)

## When to Implement

**Not now.** Current runtime (4-8 minutes) is acceptable for a batch job that runs once per pipeline cycle. The refactor becomes critical when:

1. Fact count exceeds ~20,000 (runtime > 20 minutes)
2. Message count exceeds ~100,000 (runtime > 30 minutes)
3. Scoring needs to run interactively (e.g., score-on-extract for real-time pipelines)

At current scale (4,610 facts, 40K messages), the ROI of this refactor is low. The 30-50x speedup converts 5 minutes into 10 seconds — nice but not blocking.

**Trigger:** Implement when `baselayer score` takes more than 15 minutes on a standard pipeline run.
