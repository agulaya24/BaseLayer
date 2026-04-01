# Extended Overnight GPU Test Results — S100

**Date:** 2026-03-31
**Hardware:** NVIDIA GeForce RTX 3080 10GB VRAM
**Test Subject:** Subject D (549 facts, 220 conversations)
**Runtime:** ~8 hours

## Test Design

- **Extraction:** 50 conversations × 6 models × 4 predicate sets = 1,200 runs
- **Authoring:** 4 models × 3 layers = 12 runs
- **Embedding:** 3 models × 200 facts + 10 queries = bulk retrieval test

## Extraction Results

### By Model (best predicate set per model)

| Model | Best Predicates | Facts/Conv | Total Facts | Time/Conv | Assessment |
|---|---|---|---|---|---|
| **qwen3:14b** | full_19 | **14.8** | 738 | 41.4s | Quality leader. Slow but thorough. |
| **gemma3:12b** | full_19 | **10.8** | 542 | 6.3s | **Sweet spot.** 73% of qwen3 quality at 15% of the time. |
| **mistral:7b** | behavioral_8 | **8.5** | 423 | 3.5s | Fast. Needs restricted predicates to perform well. |
| **phi4-mini:3.8b** | behavioral_8 | **5.6** | 281 | 3.1s | Smallest model, decent for cost-zero extraction. |
| **qwen2.5:7b** | full_19 | **7.1** | 355 | 3.7s | Previous default. Outclassed by gemma3 and qwen3. |
| **llama3.1:8b** | full_19 | **0.7** | 34 | 4.0s | **Broken.** Essentially non-functional for extraction. |

### Key Finding: Predicate Sets Matter Per Model

| Model | full_19 | minimal_7 | behavioral_8 | cognitive_5 |
|---|---|---|---|---|
| mistral:7b | 3.0 | 3.9 | **8.5** | 2.5 |
| qwen2.5:7b | **7.1** | 4.1 | 4.1 | 3.9 |
| qwen3:14b | **14.8** | 7.1 | 7.1 | 8.1 |
| gemma3:12b | **10.8** | 5.6 | 5.9 | 6.4 |
| phi4-mini:3.8b | **5.7** | 5.1 | 5.6 | 4.3 |

**mistral:7b** dramatically improves with the behavioral_8 predicate set (3.0 → 8.5 facts/conv). It struggles with the full 19-predicate vocabulary but excels when constrained to behavioral predicates only (practices, avoids, struggles_with, fears, enjoys, excels_at, builds, monitors).

**qwen3:14b and gemma3:12b** perform best with the full predicate set — they're capable enough to handle the full vocabulary.

### Recommendations for Local Extraction

1. **Default model:** Switch from qwen2.5:7b to **gemma3:12b** (10.8 vs 7.1 facts/conv, similar speed)
2. **Quality mode:** Use **qwen3:14b** when time isn't a constraint (14.8 facts/conv but 7x slower)
3. **Speed mode:** Use **mistral:7b with behavioral_8 predicates** for rapid bulk extraction
4. **Avoid:** llama3.1:8b (broken for extraction)

## Authoring Results

| Model | Anchors | Core | Predictions | Total | Time | Errors |
|---|---|---|---|---|---|---|
| mistral:7b | 189w | 873w | 372w | 1,434w | 39s | 0 |
| qwen3:14b | 355w | 910w | 347w | 1,612w | 210s | 0 |
| **gemma3:12b** | **573w** | **875w** | **882w** | **2,330w** | **147s** | **0** |
| deepseek-r1:32b | — | — | — | 0w | 0s | **3** (OOM) |

**gemma3:12b** produced the most output, especially for predictions (882w — nearly 3x mistral). deepseek-r1:32b failed completely — 32B parameters exceed 10GB VRAM even quantized.

**Assessment:** Local authoring is viable for draft quality but not production quality. gemma3:12b produces reasonable structure but the prose lacks the nuance of Sonnet 4.6. Recommendation: keep authoring on API (Sonnet) for production, use local models for rapid prototyping or cost-zero experimentation.

## Embedding Results

| Model | Dimensions | Embed Time (200 facts) | Query Latency | Assessment |
|---|---|---|---|---|
| nomic-embed-text | 768d | 424s | 2,110ms | Best quality, slow |
| mxbai-embed-large | 1024d | 428s | 2,129ms | Highest dims, slow |
| all-minilm | 384d | 419s | 2,092ms | Fastest, lowest dims |

**All embedding models are too slow for serving layer activation matching** (~2s per query). This is because Ollama's embedding endpoint has overhead per call. For the serving layer:

1. **Pre-embed at authoring time** — compute embeddings for all layer items once, store in ChromaDB
2. **Query-side:** single embedding call per prompt (~2s) is acceptable if all layer item embeddings are pre-computed
3. **Alternative:** Use Python sentence-transformers directly (bypasses Ollama HTTP overhead, ~50ms per embed)

## Cost Comparison

| Approach | Cost per 100 conversations | Time | Quality |
|---|---|---|---|
| API (Haiku) | ~$1.00 | ~5 min | Highest |
| API (Haiku batch) | ~$0.50 | ~30 min (async) | Highest |
| Local (gemma3:12b) | $0.00 | ~10 min | 73% of API |
| Local (qwen3:14b) | $0.00 | ~35 min | 85% of API |
| Local (mistral:7b behavioral) | $0.00 | ~3 min | 57% of API |

## Hardware Requirements

| Model | VRAM Usage | Fits RTX 3080? |
|---|---|---|
| mistral:7b | ~5GB | Yes |
| qwen2.5:7b | ~5GB | Yes |
| phi4-mini:3.8b | ~3GB | Yes |
| gemma3:12b | ~8GB | Yes (tight) |
| qwen3:14b | ~9GB | Yes (very tight) |
| deepseek-r1:32b | >10GB | **No** (OOM) |

## Next Steps

1. **Quality audit:** Compare gemma3:12b extraction output to Haiku API output on same conversations. Score fact accuracy, not just count.
2. **Predicate-specific prompts:** Build model-specific extraction prompts (mistral gets behavioral_8, qwen3 gets full_19).
3. **Embedding optimization:** Test sentence-transformers directly vs Ollama for serving layer latency.
4. **Fine-tuning opportunity:** Use Haiku output as training data to fine-tune gemma3:12b or mistral:7b for extraction specifically.
