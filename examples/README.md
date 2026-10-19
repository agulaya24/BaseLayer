# Example specifications

Each directory contains the pipeline output for a public subject.

**Read `zitkala_sa/` first if you care about provenance.** It is the only example built on the
current pipeline and the only one whose claims carry fact ids you can check. The other seven were
generated on 2026-03-09, before citations were enforced, and contain **zero fact ids**. They show
what the writing looks like; they cannot be used to verify the auditability claim.

The older seven use `*_v4.md` filenames:

```
anchors_v4.md      ANCHORS layer (core beliefs, epistemic axioms)
core_v4.md         CORE layer (communication patterns, decision-making)
predictions_v4.md  PREDICTIONS layer (behavioral triggers with directives)
brief_v4.md        optional prose brief composed from the three layers
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

Built on the current pipeline, with citations:

| Directory | Source | Facts | Cited fact ids | Resolve |
|---|---|---|---|---|
| `zitkala_sa/` | American Indian Stories (1921), public domain | 407 | 407 | 406 (one compose fabrication, kept and documented) |

## How to read these

**Start with the layers.** The three layers are the specification: they are what the MCP server serves, and each was written independently of the other two. Begin with `zitkala_sa/`, whose claims carry fact ids.

- **ANCHORS:** the beliefs this person reasons from. What they take as given.
- **CORE:** how they communicate, what context modes they operate in, how to interact with them.
- **PREDICTIONS:** given a kind of situation, how they are likely to respond. In `zitkala_sa/` each claim has an `Active when` line naming the situation; in the older seven each prediction includes a directive (how to respond) and a false positive guard (when not to apply it).

**The brief is optional.** `brief.md` and `brief_v4.md` are prose summaries composed from the layers. They are not the specification, and a client receives one only when it asks for it (`get_brief`).

## Live examples

See these subjects with full visualizations at [base-layer.ai/examples](https://www.base-layer.ai/examples/franklin).
