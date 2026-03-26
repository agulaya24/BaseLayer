<p align="center">
  <img src="assets/logo-banner.png" alt="Base Layer" width="560" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License" /></a>
  <a href="https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml"><img src="https://github.com/agulaya24/BaseLayer/actions/workflows/test.yml/badge.svg" alt="Tests" /></a>
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python" />
  <img src="https://img.shields.io/badge/subjects-29+-green.svg" alt="Subjects" />
</p>

<p align="center">
  <strong>Other tools store facts. Base Layer models behavior.</strong><br/>
  <a href="https://base-layer.ai">base-layer.ai</a> · <a href="https://base-layer.ai/examples/franklin">Live examples</a> · <a href="https://base-layer.ai/research">Research</a>
</p>

---

Base Layer compresses thousands of conversations, journal entries, or any personal text into a 3–6K token identity model that captures *how someone thinks* — not just what they've said. Inject that identity model into any AI conversation, and the model responds as if it knows you. Tested on corpora ranging from 8 journal entries to 600K+ words of published text.

**4-step pipeline.** Import → Extract (47 predicates, Haiku) → Author (3-layer identity, Sonnet) → Compose (unified brief, Opus). Validated on 29+ subjects across 6 source types. [Ablation study](docs/eval/ablation/) proved 4 steps beat 14.

```
ANCHORS — The axioms you reason from.

  COHERENCE
  If your response contains internal inconsistency, flag it before presenting
  it — they will detect it and trust you less for not catching it first.

PREDICTIONS — Behavioral patterns with triggers and directives.

  ANALYSIS-PARALYSIS SPIRAL
  Trigger: A high-stakes decision with multiple valid options.
  Directive: "The decision on the table is X. Your analysis would change
  the decision if Y. Is Y still plausible?"

CORE — How you operate. Communication patterns, context modes.
```

Every identity claim traces to source facts. Every fact traces to source text. No black box.

## Quick Start

**Requirements:** Python 3.10+, [Anthropic API key](https://console.anthropic.com/account/keys)

### Option A: Use Claude Code (easiest)

```bash
pip install baselayer
```

Then tell Claude Code:

> "Find my ChatGPT export and run Base Layer on it. Show me the cost estimate first."

That's it. Claude Code handles the rest.

### Option B: One command

```bash
pip install baselayer
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip
```

This runs the full pipeline: import → extract → author → compose. Shows a cost estimate before spending anything. Takes ~30 minutes for ~1,000 conversations. ~$0.50–2.00 total.

### Option C: Step-by-step

```bash
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate                         # preview cost before spending anything
baselayer extract                          # structured facts from every conversation
baselayer author && baselayer compose      # identity layers → unified brief
```

**Other input types:** Books, essays, letters, patents — use `baselayer extract --document-mode`.
**No conversation history?** Run `baselayer journal` for guided prompts that bootstrap your identity model.

## Use Your Brief

**MCP server** (Claude Desktop, Claude Code, Cursor):
```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

**Or paste directly** into Claude custom instructions, ChatGPT project files, or any system prompt. The identity model is 3–6K tokens — fits anywhere.

## Validation

29+ subjects, 6 source types. Original 10 scored 73–82/100.

| Corpus | Source | Facts | Brief | Score |
|--------|--------|-------|-------|-------|
| User A | 1,892 conversations | 4,610 | 9,642 chars | 78.5 |
| User B | 36 newsletter posts | 309 | — | 77.7 |
| User C | 9 journal entries | 76 | — | 81.7 |
| Franklin | Autobiography (21 ch.) | 212 | 9,144 chars | 75 |
| Douglass | Autobiography | 88 | 5,939 chars | 73 |
| Wollstonecraft | Published treatise | 95 | 9,110 chars | 78 |
| Roosevelt | Autobiography | 398 | 8,439 chars | 82 |
| Patent corpus | 30 US patents | 670 | 7,463 chars | 80 |
| Buffett | 48 shareholder letters | 505 | 7,173 chars | 78 |
| Marks | 74 investment memos | 723 | 14,241 chars | 81 |

**Twin-2K benchmark (N=100):** Compressed brief (71.83%) beats full persona (71.72%) at 18:1 compression ratio (p=0.008). Compression amplifies signal — it doesn't just save tokens.

## Cost

| Corpus Size | Cost | Time |
|------------|------|------|
| ~100 conversations | $0.30–0.80 | ~5 min |
| ~500 conversations | $0.50–1.50 | ~15 min |
| ~1,000 conversations | $0.50–2.00 | ~30 min |

Run `baselayer estimate` to preview your exact cost before spending anything. Uses Haiku (extraction), Sonnet (authoring), Opus (composition).

## Key Findings

From 98 sessions of experimentation ([full research](https://base-layer.ai/research)):

1. **20% of facts is enough.** Compression saturates early. Adding more content makes things worse.
2. **What you avoid predicts better than what you believe.** Avoidance and struggle patterns are the strongest behavioral predictors.
3. **Format matters more than content.** The same information in annotated guide format outperforms narrative prose by 24%.
4. **Most of the pipeline doesn't matter.** 4 steps scored 87/100. Full 14-step scored 83/100. But the 3-layer architecture IS load-bearing.
5. **Fidelity creates vulnerability.** The more faithfully the brief captures someone, the more exploitable it becomes.

## Privacy & Data Flow

Base Layer sends your text to the Anthropic API during extraction and authoring. This is how the pipeline works — language models process your conversations to extract structured facts and author identity layers. Your data is subject to [Anthropic's API data policy](https://www.anthropic.com/policies/privacy) (zero-retention for API usage by default as of March 2025).

**What stays local:** Your database (SQLite), vectors (ChromaDB), extracted facts, and identity brief all live on your machine. No cloud sync, no accounts, no telemetry. The brief is yours.

**Fully local option:** Set `BASELAYER_EXTRACTION_BACKEND=ollama` to run extraction through a local model (Qwen 3, Gemma 3, Mistral 7B tested). Authoring and composition still require Claude API access. Active experimentation with 32B-class local models for full pipeline.

## Limitations

- **Snapshot, not longitudinal.** No model of how identity evolves over time.
- **Text-only.** Body language, tone, physical habits — all invisible.
- **N=29+.** Generalizes across source types, expanding rapidly.
- **Cloud API dependency.** Local Ollama backend exists for extraction; authoring/composition still need API.
- **Pre-1.0.** 402 tests passing, 88+ design decisions documented. Expect rough edges.

## Documentation

| Doc | Contents |
|-----|----------|
| [`ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) | Pipeline design |
| [`DECISIONS.md`](docs/core/DECISIONS.md) | 88 design decisions with rationale |
| [`DESIGN_PRINCIPLES.md`](docs/core/DESIGN_PRINCIPLES.md) | Foundational principles |
| [`BCB_FRAMEWORK.md`](docs/eval/BCB_FRAMEWORK.md) | Behavioral Compression Benchmark |
| [`ABLATION_PROTOCOL.md`](docs/eval/ABLATION_PROTOCOL.md) | Pipeline ablation study |

88 design decisions, 10 design principles, 98 session logs. The prompts are in the code. Nothing is hidden.

## Roadmap

### What's working now

- Unified pipeline command: `baselayer pipeline <subject>` with safety gates at every step
- V2 upgrades: `baselayer pipeline <subject> --v2` with snapshot-before-clear
- Import from ChatGPT exports, Claude exports, journals, text files, directories
- Document mode for non-conversation text (books, patents, letters, essays)
- Subject registry with 94 subjects tracked (status, version, fingerprint)
- MCP server with identity Resource + recall/search/trace tools
- Cost estimation before processing (`baselayer estimate`)
- Provenance traces: every identity claim → source facts → original text
- Version history with identity model diffing
- Magic link authentication for passwordless page access
- Local extraction via Ollama (Qwen 3, Gemma 3, Mistral 7B, 10+ models tested)

### Active research

- [x] **GPT Memory Stacking Test** — 100 responses across 5 conditions. Base Layer + GPT memory outperforms either alone. C4 finding: GPT uses project knowledge as "memory."
- [ ] **Local model extraction quality** — Comparing 8 local models (3B-32B) against Haiku API on identical corpora. Testing Qwen 3, Gemma 3, DeepSeek-R1, Mistral with multiple prompt variants.
- [ ] **Longitudinal drift tracking** — Does the brief stay accurate as you change? Detect when patterns shift via contradiction, not elapsed time. Schema ready (`fact_class` column), implementation pending.
- [x] **Twin-2K benchmark (N=100)** — 71.83% accuracy at 18:1 compression, p=0.008.

### Near-term

- [ ] **Batch extraction** — Anthropic Batch API (50% cost savings) for all subject pipelines. Infrastructure built, integration pending.
- [ ] **Fully local pipeline** — Extraction works locally. Testing 32B-class models (Qwen 3, Gemma 3) for authoring quality. Goal: end-to-end local processing.
- [ ] **Always-on integration** — MCP/API for external users. Identity model served on demand.
- [ ] **Structured output enforcement** — Ollama native JSON schema constraint for guaranteed valid extraction output.

### Research horizons

- [ ] **Stacking benchmark** — Does System X + Base Layer > System X alone? Study design complete. ([Study design](docs/eval/STACKING_BENCHMARK_STUDY.md))
- [ ] **Fine-tuned extraction models** — Train 3B-14B models on Haiku extraction output. Reduce cost to near-zero for high-volume use.
- [ ] **Preference layer** — 822 preference facts (values, prefers, avoids, dislikes, enjoys) already extracted. Separate display and use case from identity model.
- [ ] **Temporal modeling** — Time-aware identity: event vs state classification, contradiction detection, mention velocity. Full spec written, waiting for pipeline stabilization.

### Vision

The brief is a portable, compressed representation of how someone thinks. Today it works in AI conversations. Where it goes:

- **Personal** — Every AI you use knows you without being told. Your identity travels with you across models, providers, and tools.
- **Professional** — Your professional point of view as a portable lens. New team members, collaborators, or AI agents understand your reasoning style immediately.
- **Agents** — Autonomous agents that represent your goals, constraints, and values — not generic defaults. The brief becomes the alignment layer between human intent and agent action.
- **Continuity** — Intelligence that persists as models upgrade. Same identity, new substrate. Your belief trajectories survive model changes.

## Contributing

We'd welcome contributions — especially around evaluation, new source type adapters, and local model support. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and where to start.

## Citation

If you use Base Layer in your research:

```bibtex
@software{baselayer2026,
  title     = {Base Layer: Behavioral Compression for AI Identity},
  author    = {Gulaya, Aarik},
  year      = {2026},
  url       = {https://github.com/agulaya24/BaseLayer},
  license   = {Apache-2.0}
}
```

## License

Apache 2.0. See [LICENSE](LICENSE).
