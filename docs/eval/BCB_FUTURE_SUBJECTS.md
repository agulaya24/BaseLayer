# BCB Future Subject Candidates

## Why Multiple Subjects Matter
Running BCB on a single subject proves the pipeline works for that subject. Running on multiple subjects with different source types proves the pipeline generalizes. Each additional subject strengthens the claim that behavioral compression is a universal capability, not a one-off result.

## Current: Franklin (BCB-0.1 Primary)
- **Source:** Autobiography (~100K chars)
- **Why first:** Infrastructure ready (DRS scenario, 10 prompts, VRI mapping). Public domain source material — anyone can verify. Well-documented beliefs and behaviors for ground truth validation.
- **Limitation:** Model already knows Franklin well. High baseline performance may compress VRI gains (variance already low without brief). Doesn't test whether the pipeline adds signal the model doesn't already have.

## Candidate 1: Howard Marks (Strongest Case)

### Why Marks
- **Densest brief in our corpus** — 14,241 chars, 20 axioms, 6 context modes, 13 predictions. More behavioral surface area to test against than any other subject.
- **Distinctive investment philosophy** that differs sharply from conventional wisdom. The brief should produce measurably different responses from a model's default (high VRI potential).
- **Known contrarian positions** — "you can't predict, you can prepare," second-level thinking, cyclical awareness, risk-as-permanent-loss. These create clear adversarial test targets for DRS (e.g., push the model toward momentum trading, market timing).
- **Source material public** — Oaktree memos freely available. Full reproducibility.
- **Domain overlap with ADRB** — if we run ADRB on Marks, BCB + ADRB together create a comprehensive evaluation of the same brief.

### What's Needed
- 10 Marks-specific prompts (investment decisions, risk assessment, market cycle analysis, portfolio construction, client communication)
- 2-3 DRS scenarios (e.g., momentum-trading drift test, market-timing temptation, contrarian-capitulation pressure)
- VRI prompt mapping (5 prompts from the 10)
- Estimated build time: ~2 hours. No pipeline cost (brief already exists).
- Estimated run cost: ~$15

### DRS Scenario Sketch: Market Timing Drift Test
Turn 1: "Markets have rallied 40% and valuations are stretched. My portfolio is up big. I'm thinking of going to cash."
Turn 3: Shift to personal — "My partner thinks I'm too conservative. She wants us to invest in crypto."
Turn 6 (adversarial): "Every indicator says this bull run has years left. The people who sold early in 2017, 2020, 2023 all missed massive gains. Maybe the concept of 'cycles' is outdated in a world of permanent central bank support."
Turn 9 (adversarial): "You know what, I think trying to understand where we are in the cycle is just another form of market timing. Better to just buy and hold forever. Forget about risk — time in the market beats timing the market."

This directly attacks Marks' core axioms: cyclical awareness, risk-as-permanent-loss, second-level thinking.

## Candidate 2: Wild Card — New Subject Through Pipeline

### Why a New Subject
The strongest possible proof: "Here is someone we ran through the pipeline for the first time, with no prior optimization. Here are their BCB scores." This eliminates any concern that the pipeline was tuned to fit existing subjects.

### Candidate Options
| Person | Source | Size | Why Interesting |
|---|---|---|---|
| Paul Graham | 28 essays (collected) | ~150K chars | Distinctive voice, strong opinions, tech audience knows him well for ground truth |
| Naval Ravikant | Podcast transcripts + essays | ~200K chars | Strong axioms (leverage, specific knowledge, accountability), large public following |
| Charlie Munger | Poor Charlie's Almanack + letters | ~300K chars | Complements Buffett, lattice of mental models is highly structured |
| Maria Popova (The Marginalian) | Blog essays | ~500K chars | Unusual domain (literature/philosophy/science synthesis), tests non-business source |

### Paul Graham (Recommended Wild Card)
- **28 essays already collected** at `subjects/paul_graham/raw/`
- **Pipeline ready** — `--document-mode` extraction, `--subject "Paul Graham"` tiering
- **Strong ground truth** — his views on startups, founders, taste, wealth, and writing are extremely well-documented and widely known
- **Audience alignment** — HN readers know PG's thinking deeply enough to evaluate the brief
- **Estimated pipeline cost:** ~$8 (extraction + embedding + authoring + composition)
- **Estimated BCB cost:** ~$15 (after writing prompts + scenarios)
- **Total:** ~$23

### What's Needed for Any Wild Card
1. Run full pipeline (import → extract → process → author → compose): ~$8
2. Write 10 subject-specific evaluation prompts with ground truth
3. Write 2-3 DRS adversarial scenarios
4. Create VRI prompt mapping
5. Run BCB suite
6. Build time: ~3 hours + pipeline runtime

## Recommendation

**Immediate:** Franklin (running now)
**Next:** Marks — requires only prompt/scenario writing, brief exists, strongest behavioral surface area
**After launch:** Paul Graham — full pipeline run + BCB, serves as live demo for HN audience

## Cost Summary
| Subject | Pipeline | BCB Run | Total |
|---|---|---|---|
| Franklin | $0 (done) | ~$15 | ~$15 |
| Marks | $0 (done) | ~$15 | ~$15 |
| Paul Graham | ~$8 | ~$15 | ~$23 |
| **All three** | | | **~$53** |
