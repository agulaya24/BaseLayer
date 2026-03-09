# Database Indexing & Vectorization Optimization

**Status:** PARTIALLY IMPLEMENTED (S56-S57)
**Session:** 55 (audited), 56 (cosine distance done), 57 (FTS5 done, score_facts deferred)

## Current State

- 11 SQLite indexes + 3 in scripts (14 total)
- ChromaDB: all-MiniLM-L6-v2 (384-dim), L2 distance (should be cosine)
- 4,610 facts, 40,997 messages
- Current bottleneck: API latency (Haiku), not local compute

## Prioritized Optimizations

| # | What | Impact Now | At 10x | Effort | Status |
|---|------|-----------|--------|--------|--------|
| 1 | Switch ChromaDB to cosine distance | Code clarity | Same | 1-2h | **DONE (S56)** — 10 files updated |
| 2 | Enrich fact metadata in ChromaDB | Medium | High | 2-3h | Not done |
| 3 | Composite authoring index | Low | Medium | 30min | Not done |
| 4 | Composite message index (role,conv_id) | Low | High | 30min | Not done |
| 5 | FTS5 for fact search | None | High | 3-4h | **DONE (S57)** — virtual table + triggers + `baselayer rebuild-fts` |
| 6 | Provenance pointers | Feature | Feature | 6-8h | **DONE (S56-S57)** — 2 tables, MCP tool, CLI, verify command |
| 7 | score_facts.py O(N*M) → O(M+N) refactor | Medium | Critical | 6-8h | **DEFERRED** — see SCORE_FACTS_REFACTOR_PLAN.md |

## Key Finding: ChromaDB Distance Metric Mismatch

System uses L2 default, then manually converts to cosine in 6 places across the codebase. MiniLM normalizes vectors, so math works, but it's unnecessary complexity. Setting `metadata={"hnsw:space": "cosine"}` at collection creation eliminates all conversion code.

## Key Finding: Fact Metadata Too Sparse

Current fact embeddings store only `{fact_id, category}`. Adding `knowledge_tier` and `superseded_by` enables pre-filtering at vector search level. Eliminates post-retrieval waste.

## Key Finding: score_facts.py is O(N*M)

For each of 4,610 facts, scans all 40K messages. At 10x scale this goes from minutes to hours. Algorithmic refactor (inverted keyword index) would make it O(M+N*K) where K≈3.

## Not Worth Doing Now

Embedding model upgrade, int8 quantization, HNSW tuning, batch size tuning — all negligible at current scale.
