# Pipeline Upgrades — Post-Franklin Evaluation

## Status: PROPOSED (Session 61)
## Trigger: Franklin eval proved compressed brief (System D) outperforms full layers (System B) by +0.42

---

## 1. NEW FINAL PIPELINE STEP: Unified Behavioral Brief

### Problem
The current pipeline outputs three separate markdown files (ANCHORS, CORE, PREDICTIONS). The eval proved these don't help — and can actively hurt (P3 catastrophe). The compressed brief format is the only approach that adds measurable value.

### Change
Add Step 14 to the pipeline: **COMPOSE BRIEF**

The three layer agents produce their work products as before. The Collective then composes a single unified behavioral brief optimized for three properties:

1. **Concrete mechanisms** — specific tactics and behaviors from source text, not abstract principles
2. **Characteristic tensions** — internal contradictions and self-aware tradeoffs that make this person *this person*
3. **Pragmatic framing** — how the person operates and engineers outcomes, not what they believe

### Implementation
- New function in `agent_pipeline.py`: `compose_unified_brief()`
- Input: all three authored layers + identity-tier facts
- Output: single narrative brief, ~3,000-5,000 tokens
- The Collective reviews the brief (not the layers) as the final quality gate
- Layers remain as "show your work" artifacts, not the deliverable
- MCP Resource serves the brief, not the layers
- `baselayer export --format preferences` outputs the brief

### Prompt Constraints for Brief Composition
- MUST include specific behavioral examples from source data (not abstractions)
- MUST surface internal tensions and contradictions (the person, not a caricature)
- MUST frame patterns as operational (how they act) not descriptive (what they are)
- MUST NOT use modern professional language for historical/non-professional subjects
- MUST NOT generalize beyond what source data supports
- Brief should read as a narrative behavioral profile, not a structured reference document

---

## 2. JUDGE PANEL (Replace Single Judge)

### Problem
Single Opus judge creates brittle scores. No inter-rater reliability check. Opus judging Opus introduces self-evaluation bias.

### Change
Three-judge panel: Sonnet + Opus + Haiku, all score independently.

### Implementation
- `run_validation_study.py --judge` runs all three models
- Results stored per-judge: `judge_ratings_sonnet.json`, `judge_ratings_opus.json`, `judge_ratings_haiku.json`
- Analysis computes: per-judge averages, inter-rater agreement (Krippendorff's alpha or simple correlation), consensus scores (mean of 3)
- Flag any response where judges disagree by >1 point on any dimension
- Use consensus score as the primary metric

---

## 3. LAYER ABLATION CONDITIONS

### Problem
We don't know which layer contributes most to System D's success or System B's failure.

### Change
Add ablation conditions to the eval:

| Condition | Context |
|-----------|---------|
| C2-A | ANCHORS only |
| C2-C | CORE only |
| C2-P | PREDICTIONS only |
| C2-AC | ANCHORS + CORE |
| C2-AP | ANCHORS + PREDICTIONS |
| C2-CP | CORE + PREDICTIONS |

### Implementation
- Placeholders already exist in `run_validation_study.py` (ablation conditions defined but never generated)
- Wire up actual layer slicing in `get_system_prompt()`
- Minimum: C2-A, C2-C, C2-P (3 conditions × 10 prompts = 30 responses)
- Full: all 6 combinations (60 responses)

---

## 4. CLAUDE MEMORY COMPARISON (Condition CM)

### Problem
No competitive benchmark against the direct competitor.

### Change
Add Claude Memory as an eval condition. Same Sonnet model, Claude's extracted memories as context.

### Setup Required (Developer)
1. Create new Claude account
2. Import ChatGPT export via claude.ai/import-memory
3. Wait 24h for memory synthesis
4. Export resulting memories as text
5. Provide to pipeline as CM condition

### Implementation
- New condition `CM` in `run_validation_study.py`
- System prompt: inject Claude's memories in `<userMemories>` XML format (matching their internal format)
- Same prompts, same judge panel

---

## 5. HUMAN BLIND A/B EVALUATION

### Problem
LLM judges may have systematic biases. No human ground truth.

### Change
Build a blind A/B comparison tool for human evaluation.

### Implementation
- New mode: `run_validation_study.py --human-ab`
- For each prompt, present two randomly ordered responses (no system labels)
- Evaluator picks which is better + brief justification
- Conditions paired: D vs A (main test), D vs CM (competitive), B vs A (layer check)
- 10 prompts × 3 pairs = 30 judgments (~20-30 min for evaluator)
- Output: win rate per condition pair, per-dimension breakdown if evaluator provides it

---

## 6. BATCH API FOR GENERATION + JUDGING

### Problem
Synchronous API calls are 2x more expensive than necessary.

### Change
Use Anthropic Batch API for all eval generation and judging.

### Implementation
- Extend `batch_extract.py` patterns to eval (submit batch, poll, process)
- 50% cost reduction on all API calls
- Tradeoff: results delayed up to 24h (acceptable for eval, not for interactive use)
- Add `--batch` flag to `run_validation_study.py`

---

## 7. LENGTH NORMALIZATION

### Problem
System D responses are 87% longer than baseline. Longer responses may score higher from volume alone.

### Change
Add response length cap and/or length-penalized scoring.

### Options
- **Cap:** Add `max_tokens=400` to generation calls for a "length-controlled" replication
- **Penalty:** Multiply scores by `min(1.0, baseline_length / response_length)` to penalize verbosity
- **Analysis:** Report scores per-token as well as absolute

### Implementation
- New flag: `--max-tokens 400` on `--generate`
- Length-controlled conditions: `D-short`, `B-short`, etc.
- Analysis reports both raw and length-normalized scores

---

## 8. ANTI-ANACHRONISM CONSTRAINTS

### Problem
System B's P3 failure was caused by modern language ("client") breaking period calibration. The structured layers don't enforce era-appropriate voice.

### Change
Add explicit anti-anachronism constraints to layer authoring and brief composition prompts.

### Implementation
- Add to authoring prompts: "All examples and language MUST be consistent with the subject's historical period. Do not use modern professional terminology."
- Add to brief composition prompt: "If the subject is historical, all behavioral descriptions must use period-appropriate framing."
- Add judge dimension for historical subjects: "anachronism_check" (binary: present/absent)
- Score penalty if anachronism detected

---

## 9. ADDITIONAL AUTOBIOGRAPHIES

### Problem
N=1 (Franklin only). Results may not generalize.

### Subjects
| Subject | Source | Why |
|---------|--------|-----|
| Frederick Douglass | *Narrative of the Life* (1845) | Different era, different background, strong behavioral patterns |
| Mary Wollstonecraft | *A Vindication of the Rights of Woman* + Godwin's memoirs | Non-autobiography source, external behavioral evidence |
| Theodore Roosevelt | *An Autobiography* (1913) | Different personality type, well-documented behavioral patterns |

### Implementation
- Import each source text via `baselayer import`
- Run full pipeline (extract → process → author)
- Generate subject-specific behavioral prompts (10 per subject)
- Run same 6-system comparison + ablation
- Compare cross-subject: does D always win? Does B always fail on certain prompt types?

---

## 10. PRIVATE INDIVIDUAL EVAL (User A)

### Problem
The actual product use case is private individuals the AI doesn't know. Famous-figure ceiling effect compressed all deltas. This is the critical test.

### Change
Run the full eval on User A's data with competitive comparison.

### Conditions
| Condition | Context |
|-----------|---------|
| C1 | Cold (model knows nothing) |
| C2 | Full Base Layer layers |
| D (brief) | Compressed behavioral brief |
| CM | Claude Memory export |
| C2-A | ANCHORS only |
| C2-P | PREDICTIONS only |
| HA | Human A/B blind evaluation |

### Expected Outcome
With no pre-training knowledge to fall back on, the delta between C1 (cold) and D (brief) should be substantially larger than Franklin's +0.40. If it's not, the pipeline doesn't add value for its primary use case.

### Prompts
Must be redesigned for a private individual. Test patterns the layers claim to capture:
- Decision-making under ambiguity
- Communication style in conflict
- How they approach new domains
- Work prioritization
- Relationship to authority/expertise
- Response to criticism
- What they optimize for

---

## Priority Order

1. **Unified brief composition** (Step 14) — changes the product output format
2. **Judge panel** — fixes the biggest methodological weakness
3. **Layer ablation** — understand which layers matter
4. **Claude Memory comparison** — competitive benchmark (blocked on developer creating account)
5. **Anti-anachronism constraints** — fixes the P3 failure mode
6. **Private individual eval** — the critical product validation
7. **Additional autobiographies** — strengthens N
8. **Human blind A/B** — eliminates LLM judge bias
9. **Length normalization** — addresses confound
10. **Batch API** — cost optimization

---

## What the Franklin Study Proved (Settled Questions)

- Compressed narrative brief > structured layers > raw facts > nothing (for behavioral prediction)
- Context quality > model capability
- The pipeline's 13 steps add value, but only when the final output is a narrative brief
- The evaluation framework works (5 dimensions, per-prompt breakdown, external validation)
- Three independent reviewers (GPT, Gemini, our analysis) reached identical conclusions from blind data
- Total study cost: $4.53. Reproducible.

## What Remains Open

- Does the pipeline help for private individuals? (THE question)
- How does Base Layer compare to Claude Memory? (THE competitive question)
- Which pipeline step contributes most value?
- Do results generalize beyond Franklin?
- Would human judges agree with LLM judges?
