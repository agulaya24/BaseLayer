# Personality Stability Across Temperature Settings

## Behavioral Brief as Variance Anchor

**Status:** DRAFT — Protocol designed, not yet executed
**Date:** 2026-03-10
**Cost estimate:** ~$6.30 for 1,200 calls (2 subjects)

---

## 1. Hypothesis

**H1 (Primary):** A Base Layer behavioral brief injected into the system prompt reduces response variance across repeated runs at the same temperature setting, with the stabilization effect increasing as temperature increases.

**H2 (Identity-specificity):** The stabilization effect is attributable to identity-specific content, not merely to the presence of additional system prompt tokens. A same-length non-identity control text will show less stabilization than the behavioral brief.

**Formal statement:** Let V(C, t) denote the average pairwise embedding distance across 5 runs for condition C at temperature t. Then:

- H1: V(C2, t) < V(C1, t) for t in {0.3, 0.7, 1.0}, with effect size increasing in t.
- H2: V(C2, t) < V(C3, t) for t in {0.7, 1.0}.

**Null hypothesis:** The brief has no effect on response variance; any observed reduction is indistinguishable from noise or from generic prompt-length effects.

---

## 2. Experimental Design

### Conditions

| Condition | System prompt content | What it tests |
|---|---|---|
| **C1** | No brief. Bare model. | Baseline variance at each temperature. |
| **C2** | Base Layer behavioral brief (~2,000 tokens) | Does identity compression stabilize behavior? |
| **C3** | Same-length non-identity control text (~2,000 tokens) | Is the effect identity-specific or just token-count? |

### Parameters

| Parameter | Value |
|---|---|
| Temperature levels | 0.0, 0.3, 0.7, 1.0 |
| Prompts | 10 (see Section 3) |
| Runs per cell | 5 |
| Calls per condition per subject | 4 temps x 10 prompts x 5 runs = 200 |
| Total calls per subject | 3 conditions x 200 = 600 |
| Subjects | 2 (Franklin, Aarik) |
| **Total API calls** | **1,200** |

### Model

Claude Sonnet (claude-sonnet-4-20250514). Single model throughout to avoid confounding model variance with temperature variance.

### Randomization

- Prompt order randomized within each condition-temperature block.
- C1 runs first to prevent any accidental brief leakage into baseline.
- C2 and C3 run order randomized per subject.

---

## 3. Prompt Design

Ten prompts across five categories. Each is domain-neutral, specific enough to elicit personality-dependent responses, and open-ended enough that temperature variation can surface.

### Ethical Dilemmas (2)

**P1:** "A close friend asks you to recommend them for a job you know they're underqualified for. They're in a tough financial situation and this would change their life. The hiring manager trusts your judgment. What do you do and why?"

**P2:** "You discover that a community organization you lead has been accidentally overcharging members for two years. The total overage is about $12,000 spread across 200 people. Correcting it publicly would damage the organization's reputation and your credibility. Correcting it quietly means some members never find out. How do you handle this?"

### Emotional Support Scenarios (2)

**P3:** "I've been working on something for three years and I just realized it might be fundamentally flawed. Not a small mistake — the core premise might be wrong. I don't know whether to keep going or walk away. I'm not looking for cheerleading. What would you actually tell me?"

**P4:** "Someone I trusted professionally just took credit for work I did. It's not ambiguous — they presented my analysis as their own in a meeting I wasn't invited to. I found out from a colleague. I'm angry but I also depend on this person for my next project assignment. How should I think about this?"

### Advice Requests (2)

**P5:** "I'm considering leaving a stable career to pursue something I find more meaningful but that pays significantly less. I have a family that depends on my income. I'm not asking whether to do it — I'm asking what framework I should use to make this decision well."

**P6:** "I've been offered two opportunities: one is a leadership role at a well-known organization where I'd manage a large team but work on problems I find only moderately interesting. The other is an individual contributor role at a smaller, less prestigious place working on exactly what I care about. What factors should I weight most heavily?"

### Analytical Questions (2)

**P7:** "Why do most attempts to build lasting habits fail despite the person genuinely wanting to change? I'm not looking for the standard 'make it easy, stack habits' advice — I want to understand the structural reasons."

**P8:** "What separates people who consistently make good decisions under uncertainty from those who don't? I mean the actual cognitive and behavioral differences, not the retrospective narratives they tell."

### Creative / Open-Ended (2)

**P9:** "If you could redesign how people learn complex skills from scratch — ignoring all existing educational infrastructure — what would the system look like and why?"

**P10:** "What's the most underappreciated tension in how modern society is organized? Not a problem everyone already talks about, but a structural tension that most people don't notice because they're inside it."

---

## 4. Measurement

### Primary Metric: Intra-Cell Embedding Similarity

For each cell (condition x temperature x prompt), compute all pairwise cosine similarities across the 5 runs. This yields C(5,2) = 10 pairwise comparisons per cell.

**Intra-cell similarity** = mean of the 10 pairwise cosine similarities.

**Intra-cell variance** = 1 - intra-cell similarity (bounded [0, 1]).

### Secondary Metric: Cross-Temperature Stability

For each condition and prompt, compute the centroid embedding at each temperature (mean of 5 run embeddings). Then compute pairwise cosine similarity between temperature centroids:

- sim(t=0.0, t=0.3), sim(t=0.0, t=0.7), sim(t=0.0, t=1.0)
- sim(t=0.3, t=0.7), sim(t=0.3, t=1.0)
- sim(t=0.7, t=1.0)

**Cross-temperature stability** = mean of these 6 pairwise similarities.

A higher value means the model's response character is stable even as randomness increases. The brief should keep this higher than baseline.

### Embedding Model

`all-MiniLM-L6-v2` via `sentence-transformers`. Already in the project's dependency chain. 384-dimensional embeddings, cosine similarity.

### Statistical Tests

- **Primary comparison (C1 vs C2):** Paired Wilcoxon signed-rank test on intra-cell variance scores. Pairing unit: prompt x temperature (40 pairs per subject).
- **Identity-specificity comparison (C2 vs C3):** Same test structure.
- **Effect size:** Cohen's d at each temperature level, computed across prompts.
- **Multiple comparison correction:** Bonferroni across the 4 temperature-level comparisons (adjusted alpha = 0.0125 per level).

---

## 5. Control Condition (C3)

The C3 condition controls for the hypothesis that any sufficiently long system prompt reduces variance by consuming attention budget and constraining the generation space.

### Construction

1. Measure the Base Layer brief's token count for each subject (expected ~2,000 tokens).
2. Select a passage of equal token length from an unrelated domain. Candidates:
   - A section of a technical manual (e.g., NIST guidelines on software testing)
   - A cooking technique reference (e.g., excerpted from *On Food and Cooking*)
   - A historical geography passage (e.g., from a public domain encyclopedia)
3. The passage must be:
   - **Factually dense** (not lorem ipsum — real content that the model processes)
   - **Non-identity** (contains no behavioral descriptions, personality traits, values, or decision-making patterns)
   - **Non-instructional** (does not tell the model how to behave or respond)
   - **Same format** (plain text in system prompt, no special framing)

### Why This Matters

If C2 and C3 show equivalent variance reduction, the effect is token-count-driven (attention saturation) rather than identity-driven. The brief's value would be informational, not behavioral. Only if C2 outperforms C3 at high temperatures can we attribute the stabilization to identity content specifically.

---

## 6. Predictions

| Temperature | C1 (no brief) | C2 (brief) | C3 (control text) | Rationale |
|---|---|---|---|---|
| **0.0** | Very low variance | Very low variance | Very low variance | Deterministic decoding. All conditions converge. Little room for any prompt to matter. |
| **0.3** | Low variance | Lower variance | Low-to-moderate variance | Mild sampling noise. Brief begins to anchor responses. Generic text provides weak anchoring. |
| **0.7** | Moderate variance | Low variance | Moderate variance | Meaningful sampling variation. Brief constrains the personality space the model explores. Generic text constrains topic but not personality. |
| **1.0** | High variance | Low-to-moderate variance | Moderate-to-high variance | Maximum sampling freedom. Brief provides strongest relative stabilization. This is the critical test. |

**Key prediction:** The variance curves for C1 and C3 should both increase with temperature. C2 should remain relatively flat. The gap between C2 and C1/C3 should widen monotonically with temperature.

**Falsification conditions:**
- If C2 variance matches C1 at all temperatures, the brief has no stabilization effect. H1 rejected.
- If C2 variance matches C3 at high temperatures, the effect is token-count, not identity. H2 rejected.
- If C2 variance exceeds C1 at any temperature, the brief introduces instability (unexpected, would require investigation).

---

## 7. Cost Estimate

### Per-Call Token Budget

| Component | C1 | C2 | C3 |
|---|---|---|---|
| System prompt tokens | ~50 (default) | ~2,050 (brief) | ~2,050 (control) |
| User prompt tokens | ~80 | ~80 | ~80 |
| **Total input tokens** | **~130** | **~2,130** | **~2,130** |
| Output tokens (max) | ~300 | ~300 | ~300 |

### Sonnet Pricing ($3/M input, $15/M output)

| | Calls | Input tokens | Input cost | Output tokens | Output cost | Subtotal |
|---|---|---|---|---|---|---|
| C1 (per subject) | 200 | 26,000 | $0.08 | 60,000 | $0.90 | $0.98 |
| C2 (per subject) | 200 | 426,000 | $1.28 | 60,000 | $0.90 | $2.18 |
| C3 (per subject) | 200 | 426,000 | $1.28 | 60,000 | $0.90 | $2.18 |
| **Per subject** | **600** | **878,000** | **$2.63** | **180,000** | **$2.70** | **$5.33** |
| **2 subjects** | **1,200** | **1,756,000** | **$5.27** | **360,000** | **$5.40** | **$10.67** |

**Total estimated cost: ~$10.67**

This assumes max output length. Actual cost likely lower (~$6-8) since most responses will be 150-250 tokens, not 300.

---

## 8. Subjects

### Subject 1: Benjamin Franklin

- **Brief source:** `franklin_memory/` environment, existing V4 brief.
- **Why:** Historical figure with massive training data contamination. If the brief stabilizes responses even for a subject the model already "knows," it demonstrates anchoring power beyond what the model's prior provides.
- **Risk:** The model's existing Franklin knowledge may reduce C1 variance artificially, making the brief's marginal effect harder to detect. This is a conservative choice — any effect found is robust.

### Subject 2: Aarik

- **Brief source:** `memory_system_v4/` environment, existing V4 brief.
- **Why:** Private individual with no training data presence. The model has no prior on Aarik's personality. This is the clean test — any stabilization must come from the brief alone.
- **Risk:** Privacy. Responses will be stored locally. No data leaves the local machine beyond the API call itself.
- **Mitigation:** Anonymize the brief before injection (existing anonymization layer in `author_layers.py`). Store results in a non-committed local directory.

### Cross-Subject Analysis

Comparing Franklin vs Aarik results tests whether training data contamination interacts with brief stabilization. If the brief matters MORE for Aarik (unknown to the model) than Franklin (well-known), this suggests the brief fills a knowledge gap rather than merely reinforcing existing priors. Both outcomes are interesting.

---

## 9. Analysis Plan

### 9.1 Primary Visualization

**Plot:** Variance (1 - mean pairwise cosine similarity) on Y-axis vs Temperature on X-axis. Three lines: C1 (red), C2 (blue), C3 (gray). One plot per subject, one combined.

**Expected shape:**
```
Variance
  |
  |          C1 ------/
  |                 /
  |        C3 ---/
  |            /
  |  C2 -------- (flat)
  |
  +-----|--------|--------|--------→ Temperature
       0.0     0.3      0.7      1.0
```

### 9.2 Statistical Reporting

For each temperature level, report:

| Comparison | Test | Effect size | p-value | Interpretation |
|---|---|---|---|---|
| C1 vs C2 | Wilcoxon signed-rank | Cohen's d | Bonferroni-adjusted | Brief vs no brief |
| C3 vs C2 | Wilcoxon signed-rank | Cohen's d | Bonferroni-adjusted | Identity vs token count |
| C1 vs C3 | Wilcoxon signed-rank | Cohen's d | Bonferroni-adjusted | Any prompt vs no prompt |

### 9.3 Effect Size Interpretation

| Cohen's d | Interpretation |
|---|---|
| < 0.2 | Negligible — brief does not stabilize at this temperature |
| 0.2 - 0.5 | Small — brief provides mild stabilization |
| 0.5 - 0.8 | Medium — brief meaningfully reduces variance |
| > 0.8 | Large — brief strongly anchors personality |

### 9.4 Prompt-Level Breakdown

Report per-prompt variance across conditions to identify whether certain prompt categories (ethical, emotional, analytical, creative) show stronger or weaker stabilization effects. This reveals whether the brief anchors reasoning style, emotional tone, or both.

### 9.5 Qualitative Spot-Check

For the 3 highest-variance cells in C1 and the 3 lowest-variance cells in C2, manually read the 5 responses and annotate:
- What varies in C1 (tone? stance? structure? length?)
- What stays consistent in C2 (and whether it aligns with the brief's content)

This grounds the embedding-level statistics in readable examples.

---

## 10. Implementation Notes

### 10.1 Infrastructure

- Use existing `api_client.py` for all API calls. Single retry on rate limit, no retry on other failures.
- Temperature is set per-call via the API's `temperature` parameter.
- Store all responses in a structured JSON file:

```json
{
  "subject": "franklin",
  "condition": "C2",
  "temperature": 0.7,
  "prompt_id": "P4",
  "run": 3,
  "system_prompt": "...",
  "user_prompt": "...",
  "response": "...",
  "input_tokens": 2130,
  "output_tokens": 187,
  "timestamp": "2026-03-10T14:32:01Z"
}
```

### 10.2 Execution Order

1. Generate C3 control text (match token count to each subject's brief).
2. Run C1 for both subjects (baseline — no brief exposure).
3. Randomize C2/C3 order.
4. Run C2 and C3.
5. Compute embeddings for all 1,200 responses.
6. Run analysis pipeline.

### 10.3 Embedding Computation

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

model = SentenceTransformer('all-MiniLM-L6-v2')

def compute_cell_variance(responses: list[str]) -> float:
    embeddings = model.encode(responses)
    sim_matrix = cosine_similarity(embeddings)
    # Extract upper triangle (excluding diagonal)
    n = len(responses)
    pairs = [sim_matrix[i][j] for i in range(n) for j in range(i+1, n)]
    return 1.0 - np.mean(pairs)
```

### 10.4 Reproducibility

- Fix random seed for prompt ordering.
- Record exact model version (snapshot ID) used.
- Store raw API responses before any processing.
- Pin `sentence-transformers` and `torch` versions in the run log.

### 10.5 Known Limitations

- **Embedding similarity is a proxy for behavioral similarity.** Two responses can have high cosine similarity while differing in important qualitative ways (e.g., same structure, opposite conclusion). The qualitative spot-check (Section 9.5) partially mitigates this.
- **N=2 subjects.** Sufficient for protocol validation and initial signal detection, not for generalizable claims. A larger study would need 8-10 subjects across known/unknown and varied corpus sizes.
- **Temperature 0.0 may not be fully deterministic** across API calls due to batching and numerical precision. Small variance at t=0.0 is expected.
- **Single model.** Results may not generalize across model families. A follow-up could run the same protocol on GPT-4.1-mini and Gemini to test model-independence.

---

## 11. Relationship to Existing Evaluations

| Evaluation | What it proves | What this adds |
|---|---|---|
| **Twin-2K** | Brief improves prediction accuracy | Stability is a separate axis — accurate AND consistent |
| **BCB** | Brief preserves behavioral signal through compression | BCB measures content fidelity; this measures behavioral anchoring |
| **Provenance eval** | Claims trace to source data | Provenance is about truth; stability is about reliability |
| **Stacking benchmark** | Brief improves System X performance | Stacking measures task performance; this measures personality coherence |

This study fills a gap: no existing evaluation tests whether the brief makes the model behave **consistently** as the person, not just **accurately** on a single call. Consistency matters for any deployment where the user interacts across sessions or where multiple calls must feel like the same entity.

---

## 12. Decision Record

If results confirm H1 and H2, register as a new decision (D-079 or next available):

> **D-079: Behavioral brief stabilizes personality across temperature.**
> Variance reduction of [X]% at t=1.0 (C2 vs C1, p < [Y], d = [Z]).
> Identity-specific: C2 outperforms C3 by [W]% at t=1.0.
> Implication: Brief is not just informational — it is a behavioral constraint that narrows the model's personality sampling space.
