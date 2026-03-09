<p align="center">
  <img src="assets/logo-banner.svg" alt="Base Layer" width="320" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License" /></a>
  <img src="https://img.shields.io/badge/tests-414_passing-brightgreen.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python" />
  <img src="https://img.shields.io/badge/subjects-10-green.svg" alt="Subjects" />
</p>

<p align="center">
  <strong>Other tools store facts. Base Layer models behavior.</strong><br/>
  <a href="https://base-layer.ai">base-layer.ai</a> · <a href="https://base-layer.ai/examples/franklin">Live examples</a> · <a href="https://base-layer.ai/research">Research</a>
</p>

---

Base Layer compresses thousands of conversations, journal entries, or any personal text into ~2,500 tokens that capture *how someone thinks* — not just what they've said. Inject that compressed identity into any AI conversation, and the model responds as if it knows you.

**4-step pipeline.** Import → Extract (47 predicates, Haiku) → Author (3-layer identity, Sonnet) → Compose (unified brief, Opus). Validated on 10 subjects across 6 source types. [Ablation study](docs/eval/ablation/) proved 4 steps beat 14.

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

```bash
pip install baselayer
export ANTHROPIC_API_KEY=sk-ant-...
baselayer run chatgpt-export.zip    # import → extract → author → compose → brief
```

**~30 minutes for ~1,000 conversations. ~$0.50–2.00 total.**

Or step-by-step:

```bash
baselayer init
baselayer import chatgpt-export.zip       # or claude-export.json, ~/journals/, notes.md
baselayer estimate                         # preview cost before spending anything
baselayer extract                          # structured facts from every conversation
baselayer author && baselayer compose      # identity layers → unified brief
```

For non-conversation text (books, essays, letters, patents):

```bash
baselayer import ~/documents/ --source text
baselayer extract --document-mode
baselayer author && baselayer compose
```

No conversation history? `baselayer journal` generates guided prompts to bootstrap your identity model.

## Use Your Brief

**MCP server** (Claude Desktop, Claude Code, Cursor):
```bash
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

**Or paste directly** into Claude custom instructions, ChatGPT project files, or any system prompt. The brief is ~2,500 tokens — fits anywhere.

## Validation

10 subjects, 6 source types. All scored 73–82/100.

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

From 81+ sessions of experimentation ([full research](https://base-layer.ai/research)):

1. **20% of facts is enough.** Compression saturates early. Adding more content makes things worse.
2. **What you avoid predicts better than what you believe.** Avoidance and struggle patterns are the strongest behavioral predictors.
3. **Format matters more than content.** The same information in annotated guide format outperforms narrative prose by 24%.
4. **Most of the pipeline doesn't matter.** 4 steps scored 87/100. Full 14-step scored 83/100. But the 3-layer architecture IS load-bearing.
5. **Fidelity creates vulnerability.** The more faithfully the brief captures someone, the more exploitable it becomes.

## Privacy

Your database, vectors, and identity layers are stored locally (SQLite + ChromaDB). No cloud sync, no accounts, no telemetry.

Extraction sends text to the Anthropic API. Nothing persists remotely beyond [Anthropic's standard API retention](https://www.anthropic.com/policies/privacy). For fully local processing, use `BASELAYER_EXTRACTION_BACKEND=ollama`.

## Limitations

- **Snapshot, not longitudinal.** No model of how identity evolves over time.
- **Text-only.** Body language, tone, physical habits — all invisible.
- **N=10.** Generalizes across source types, but below statistical power for strong claims.
- **Cloud API dependency.** Local Ollama backend exists but quality is lower.
- **Pre-1.0.** 414 tests passing, 76+ design decisions documented. Expect rough edges.

## Documentation

| Doc | Contents |
|-----|----------|
| [`ARCHITECTURE.md`](docs/core/ARCHITECTURE.md) | Pipeline design |
| [`DECISIONS.md`](docs/core/DECISIONS.md) | 76 design decisions with rationale |
| [`DESIGN_PRINCIPLES.md`](docs/core/DESIGN_PRINCIPLES.md) | Foundational principles |
| [`BCB_FRAMEWORK.md`](docs/eval/BCB_FRAMEWORK.md) | Behavioral Compression Benchmark |
| [`ABLATION_PROTOCOL.md`](docs/eval/ABLATION_PROTOCOL.md) | Pipeline ablation study |

76+ design decisions, 10 design principles, 81+ session logs. The prompts are in the code. Nothing is hidden.

## Contributing

We'd welcome contributions — especially around evaluation, new source type adapters, and local model support. See [open questions](https://base-layer.ai/journey) for where the research is headed.

```bash
git clone https://github.com/agulaya24/baselayer.git
cd baselayer
pip install -e ".[dev]"
pytest
```

## Citation

If you use Base Layer in your research:

```bibtex
@software{baselayer2026,
  title     = {Base Layer: Behavioral Compression for AI Identity},
  author    = {Gulaya, Aarik},
  year      = {2026},
  url       = {https://github.com/agulaya24/baselayer},
  license   = {Apache-2.0}
}
```

## License

Apache 2.0. See [LICENSE](LICENSE).
