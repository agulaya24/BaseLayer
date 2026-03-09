# Example Identity Layers & Briefs

Each directory contains the pipeline output for a public subject:

```
anchors_v4.md      — ANCHORS layer (core beliefs, epistemic axioms)
core_v4.md         — CORE layer (communication patterns, decision-making)
predictions_v4.md  — PREDICTIONS layer (behavioral triggers with directives)
brief_v4.md        — Unified brief (compressed from all three layers)
```

## Subjects

| Directory | Source | Words | Facts |
|---|---|---|---|
| `franklin/` | The Autobiography of Benjamin Franklin | 75K | 247 |
| `douglass/` | Narrative of the Life of Frederick Douglass | 30K | 102 |
| `wollstonecraft/` | A Vindication of the Rights of Woman | 85K | 111 |
| `roosevelt/` | An Autobiography by Theodore Roosevelt | 190K | 460 |
| `patents/` | 30 US Patent filings across 10 domains | 500K | 670 |
| `buffett/` | Berkshire Hathaway Shareholder Letters (48) | 350K | 602 |
| `marks/` | Oaktree Capital Investment Memos (74) | 600K | 784 |

## How to read these

**Start with the brief** (`brief_v4.md`) — it's the final compressed artifact, ~2,500 tokens. This is what gets injected into AI conversations.

**Then explore the layers** — the brief is composed from three independent layers. Each layer captures a different aspect:

- **ANCHORS** — the non-negotiable beliefs this person reasons from. What they take as given.
- **CORE** — how they communicate, what context modes they operate in, how to interact with them.
- **PREDICTIONS** — behavioral trigger patterns: "When X happens → they do Y." Each prediction includes a directive (how to respond) and a false positive guard (when NOT to apply it).

## Live examples

See these subjects with full visualizations at [base-layer.ai/examples](https://base-layer.ai/examples/franklin).
