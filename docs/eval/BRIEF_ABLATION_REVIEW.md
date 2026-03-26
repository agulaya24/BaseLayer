# Brief Ablation Review: From V4 to V5 Production

**Date:** 2026-03-11
**Scope:** Complete narrative of how Base Layer's behavioral brief evolved through systematic ablation, rubric redesign, and prompt engineering across Sessions 78-87.

---

## The Problem

Base Layer extracts behavioral facts from text, organizes them into three authored layers (Anchors, Core, Predictions), then composes a single unified brief — the document that gets injected into LLM context to shape how the model interacts with that person. The brief is the only thing the consuming model ever sees. Everything upstream (extraction, scoring, authoring) exists solely to produce this artifact.

Before this work, the composition step used a "V4" prompt that had been iteratively refined through informal testing but never subjected to controlled experimentation. V4 was a detailed Opus prompt prescribing specific structural elements: false positive guards woven into prose, tension-action pairs, section ordering, and an availability index. It produced briefs averaging 9,258 characters.

The question: is V4 actually good, or did we just stop iterating?

---

## Phase 1: What's Wrong With V4? (S78 — Compression & Format Study)

Before touching the compose prompt, S78 established the baseline science. Ten experiments across two subjects (Franklin and Marks), cross-validated on both Sonnet and Qwen.

### Key Findings That Challenged V4

1. **Production briefs are 3-9x too long.** Optimal downstream performance occurs at 1,000-2,500 characters. V4's 9,144 characters means most of the brief is noise that doesn't improve LLM behavior.

2. **More data hurts.** Q1 facts alone outperform Q1+Q2+Q3 for predicting Q4 behavior. Additional data introduces noise and contradictions. The brief was stuffing too much in.

3. **Behavioral facts are the best predictors.** Only 15% of extracted facts are behavioral, but they drive the most downstream accuracy. V4 wasn't filtering for this.

4. **Avoidance predicates are strongest.** What someone avoids reveals more than what they pursue. This validated V4's false positive guards — they ARE avoidance patterns — but suggested they should be weighted even more heavily.

5. **Format is a 24% variable.** Six formats tested on identical input. Annotated guide with guards (+24%) crushed narrative prose (baseline), bullet points (+8%), maximally compressed (+6%), JSON (+11%), and guide-without-guards (+18%). V4 was already in the annotated guide family, but the gap between V3 (no guards, +18%) and V4 (with guards, +24%) showed that false positive guards account for 6 percentage points of performance by themselves.

6. **Maximum compression overshoots.** V5-compressed (+6%) underperformed even bullet points (+8%). There's a floor below which brevity destroys the contextual cues models need.

### What This Meant for V4

V4 had the right format (annotated guide with guards) but the wrong length (9K vs 1-2.5K optimal), no mechanism for expressing uncertainty, no temporal awareness, and was prescribing structure instead of letting the model adapt to the subject. The composition prompt needed systematic ablation.

---

## Phase 2: Pipeline Ablation — What Steps Actually Matter? (S79)

Before touching the compose prompt specifically, S79 tested whether the entire pipeline architecture was sound. 14 conditions on Franklin, ~$16 total.

### Results

| Condition | Score | What It Tests |
|---|---|---|
| C0 (full 14-step) | 83/100 | Baseline |
| C11 (Author no review + Compose) | **87/100** | Collective review ceremonial? |
| C13 (single layer) | 83 | 3-layer architecture matters? |
| C8-C10 (skip author) | 77-80 | Authoring matters? |
| C12 (direct fact injection) | 77 | Synthesis matters? |
| C1-C7 (drop individual steps) | 81-83 | Individual step contributions |

### Conclusions

- **10 of 14 steps were ceremonial.** Scoring, classification, tiering, contradiction detection, consolidation, embedding, anchors extraction, Collective review as generation, and assembly could all be removed without quality loss.
- **3-layer architecture IS load-bearing.** Single-layer compose (C13) matched baseline but couldn't beat it. The three layers (Anchors/Core/Predictions) provide essential structural decomposition.
- **Authoring IS load-bearing.** Skipping authoring entirely (C8-C10) dropped scores to 77-80. Raw facts without synthesis lose behavioral signal.
- **Direct fact injection is worst.** C12 proved that throwing facts at a compose prompt without layer synthesis produces the worst output.
- **Collective review as generation is ceremonial.** But Collective review as evaluation with a defined rubric turned out to be valuable — a distinction that matters for D-079.

Pipeline simplified from 14 steps to 4: Import → Extract → Author → Compose.

---

## Phase 3: The 31-Condition Prompt Ablation (D-079, S85-S86)

With the pipeline streamlined and the baseline science established, D-079 was the systematic ablation of the composition prompt itself. 31 conditions across 7 rounds, tested on 3 subjects (Franklin, Buffett, Aarik), ~$18.40 total.

### Round 1 (C0-C7): Does Architecture Matter?

**Question:** Should composition use a Planner-Executor (multi-stage) architecture?

**Answer:** No. Single-pass Opus beat every P-E variant. Multi-stage added $0.20+ cost (vs $0.11 single-pass), doubled latency (~60s vs ~30s), and added complexity with zero quality gain. Composition quality is bounded by prompt content and rubric alignment, not planning depth.

### Round 2 (C8-C11): Which Prompt Elements Matter?

Four content variations tested different organizational principles.

- **C9 (FP-first structure) won.** Organizing the brief around "when NOT to apply this pattern" proved more effective than organizing around the patterns themselves. This aligns perfectly with S78's finding that avoidance predicates are the most predictive facts.
- **C11 (free format):** When given complete creative freedom, Opus independently chose the annotated guide format — the exact format S78 identified as optimal. Two independent experiments converging on the same answer.

### Round 3 (C12-C13): Are False Positive Warnings Load-Bearing?

**Yes — but with a critical caveat.**

Removing FP warnings (C13) degraded scores by 4.6 points on average. They are genuinely load-bearing. But C12 revealed the single largest faithfulness leak in the entire study: when instructed to synthesize FP warnings, the model fabricated warnings for patterns that had no FP conditions in the source layers. The model was inventing plausible-sounding guardrails that didn't trace to any real data.

This is the most dangerous failure mode in behavioral compression — confident-sounding constraints that aren't grounded in evidence.

### Round 4 (C14): Fixing Fabrication

A single instruction fixed it: "only include FP warnings where the source material explicitly provides them."

C14 scored 73.0/85, the best under the old rubric. The faithfulness problem was instructional, not architectural. The model wasn't fundamentally incapable of being faithful — it just hadn't been told that faithfulness mattered more than completeness.

### Round 5 (C15-C23): Systematic Gap Closure

Nine conditions probing specific quality gaps. Three key discoveries:

1. **Completeness and efficiency are in direct tension.** C16 achieved exhaustive source coverage at 10,000+ characters — confirming S78's finding that completeness as a standalone target drives bloat.

2. **Example phrasings are fabricated content.** C19 and C21 tested including "example phrasings" in briefs. They improved actionability scores but introduced fabricated text that doesn't exist in source layers. Connected to D-078's template contamination finding.

3. **Rubric awareness is the strongest meta-strategy.** C19 and C23 both included the evaluation rubric in the compose prompt. Both scored at or near the top. The model optimizes for what it's told to optimize for. This made rubric design the highest-leverage activity in the entire study.

### The Rubric Was Wrong

At this point, a fundamental problem surfaced: the rubric itself was misallocating weight.

**Old Rubric (/85):**
- Traceability: 30 pts (35%) — 3x weight
- Faithfulness: 20 pts (24%) — 2x weight
- Token Efficiency: 10 pts (12%) — 1x weight
- Completeness: 10 pts (12%) — 1x weight
- Actionability: 10 pts (12%) — 1x weight
- FP Grounding: +5 bonus (6%)

Traceability at 35% was over-weighted. Actionability at 12% was under-weighted. The rubric was optimizing for "can we trace this claim?" rather than "does this brief actually change how the LLM behaves?" A perfectly traceable brief that doesn't change model behavior is useless.

**New Rubric (/90) — Derived from first principles:**

The redesign started from a single question: "What must be true for an LLM to understand how to work with a specific human?"

| Dimension | Weight | Max | What It Measures |
|---|---|---|---|
| **Provenance** | 3x | 30 | Can the LLM explain HOW it knows each claim? (Traceability + Faithfulness merged) |
| **Behavioral Change** | 3x | 30 | Does this information actually change LLM behavior? (Upgraded from 1x) |
| **Epistemic Calibration** | 2x | 20 | Does the brief mark what's uncertain or unpredictable? |
| **Signal Density** | 1x | 10 | Maximum signal, minimum noise |

Each primitive grounded in published research:
- **Provenance:** XAI literature (LIME/SHAP). Explanations improve trust and enable error detection.
- **Behavioral Change:** Information Bottleneck theory (Tishby). Information that doesn't change behavior is noise.
- **Epistemic Calibration:** Calibration research (Guo et al. 2017). A model that knows what it doesn't know prevents confident errors.
- **Signal Density:** Information theory, minimum description length. Every sentence must add understanding.

The novel contribution: **no published personalization framework combines all four.**

### Round 6 (C24-C27): Testing the New Rubric

| Condition | Avg Score | Notes |
|---|---|---|
| C24 (epistemic loop) | 71.0/90 | Solid but structurally rigid |
| C25 (compressed) | Below C24 | Compression destroyed behavioral specificity |
| C26 (rubric awareness) | 73.7/90 | Round 6 winner |
| C27 (no structural prescription) | Variable | Format varied by subject — appropriate |

Three discoveries:

1. **Rubric awareness wins again.** C26, which includes the new rubric in the prompt, led Round 6. Consistent with Round 5 finding.

2. **Different people need different formats.** C27 (no structural prescription) produced tension-centered format for Franklin, system-coherence for Buffett, imperative-structured for Aarik. The model was adapting structure to the subject's behavioral signature. Format becomes signal, not template.

3. **"Cannot predict" is the top improvement suggestion.** Across every Round 6 review, the most consistent reviewer feedback was: include explicit epistemic gaps — places where the behavioral model breaks down. No brief was doing this.

### Round 7 (C28-C30): The Winner

Three conditions integrated research-identified gaps into the C26 base:

| Condition | Description | Franklin | Buffett | Aarik | Average |
|---|---|---|---|---|---|
| **C28** | C26 + cannot predict + temporal markers | 89 | 86 | 86 | **87.0** |
| C29 | C26 + relational context + user agency | 73 | 68 | 87 | 76.0 |
| C30 | Full research synthesis (everything) | 86 | 82 | 88 | 85.3 |

**C28 won at 87.0/90 (96.7% of maximum).**

C28's scoring breakdown:

| Subject | Provenance (/30) | Behavioral Change (/30) | Epistemic Cal. (/20) | Signal Density (/10) | Total |
|---|---|---|---|---|---|
| Franklin | 30/30 | 30/30 | 20/20 | 9/10 | 89/90 |
| Buffett | 29/30 | 29/30 | 19/20 | 9/10 | 86/90 |
| Aarik | 27/30 | 30/30 | 20/20 | 9/10 | 86/90 |

Why C28 beat the more comprehensive C30:

- **Focused additions outperform comprehensive ones.** C28 added two things (cannot predict + temporal awareness). C30 added everything (temporal + relational + agency + cannot predict). More instructions create competing optimization targets. The model can optimize for 2 new constraints; 4+ new constraints cause tradeoffs.
- **Signal Density is a ceiling.** Every Round 7 brief scored 9/10 on Signal Density. It no longer differentiates.
- **Epistemic Calibration is the differentiator.** C28 averaged 19.7/20. C29 averaged 12.0/20. The spread between best and worst conditions lives almost entirely in this dimension.
- **C29 had FP fabrication.** The relational context + agency prompt caused false positive fabrication on 2 of 3 subjects. Adding relational prompting competed with faithfulness.

---

## Phase 4: The Rubric Calibration Bug (S86)

During scoring, a critical measurement error was discovered. The reviewer was penalizing faithful paraphrases of FP warnings as "fabricated."

### The Bug

Source (Buffett P1): "Not every mention of future planning triggers this pattern — only when he's actively resisting short-term thinking pressure"

Brief (C31): "Future planning mentions don't always trigger long-horizon reframing [P1]"

This is a faithful paraphrase with a correct citation back to the source prediction. The reviewer scored it as fabricated (P3=3, E1=0) because it wasn't verbatim. Meanwhile, briefs that omitted FP warnings entirely received full marks — the rubric was rewarding omission and penalizing paraphrase.

### The Fix

Changed P3 (Faithfulness) and E1 (FP Grounding) to provenance-based evaluation:
- **Faithful paraphrase with citation** → 8-10 (traces to source, even if not verbatim)
- **No traceable source** → 0-3 (genuinely fabricated)
- **FP warnings omitted entirely** → 4-5 (missed opportunity, not faithful)

### Impact on Scores

| Condition | Before Fix | After Fix | Delta |
|---|---|---|---|
| C28 (Buffett) | 86 | 83 | -3 |
| C29 (Buffett) | 68 | 84 | +16 |
| C30 (Buffett) | 82 | 74 | -8 |
| C31 (Buffett) | 68 | 85 | +17 |

The rubric bug had inflated C28 (which omitted FPs) and deflated C31 (which paraphrased them faithfully). After correction:

| Condition | Franklin | Buffett | Aarik | Average |
|---|---|---|---|---|
| C28 | 88 | 83 | 82 | **84.3** |
| C29 | 72 | 84 | 84 | 80.0 |
| C30 | 83 | 74 | 88 | 81.7 |
| **C31** | 83 | 85 | 83 | **83.7** |

C28 and C31 are statistically tied (84.3 vs 83.7). The original 7-point gap was an artifact of rubric miscalibration.

---

## Phase 5: C31 Wins — The V5 Decision (D-080, S87)

C31 = C28's prompt (rubric awareness + temporal awareness + cannot predict) + C27's format freedom (no structural prescription).

### Why C31 Over C28?

Opus Collective evaluated all 6 briefs (C28 x 3 subjects + C31 x 3 subjects). C31 was chosen unanimously:

| Subject | Winner | Confidence |
|---|---|---|
| Franklin | C31 | High |
| Buffett | C31 | High |
| Aarik | C31 | High |

Despite being 0.6 points lower on average, C31 won because:

1. **Format freedom produces better briefs per-subject.** C28 produced structurally consistent briefs. C31 produced briefs where structure itself carried meaning — mode detection patterns for Franklin, decision triggers for Buffett, trigger-response for Douglass.
2. **Higher ceiling on hard subjects.** C31 hit 85 on Buffett (C28's hardest case at 83).
3. **Format adaptivity is the right default.** Prescribing structure constrains the model. Letting it choose format matched to the subject's behavioral signature is strictly more expressive.

### V4 vs V5 — The Final Comparison

| Property | V4 (S80 production) | V5/C31 |
|---|---|---|
| Architecture | Single Opus pass, detailed instructions | Rubric-aware, format-free, temporal-aware |
| Key features | FP guards + tension-action pairs woven | Rubric-as-prompt + CANNOT PREDICT + citations |
| Avg score (/90) | 42.0 | 83.7 |
| Avg size (chars) | 9,258 | 4,038 |
| Signal per char | 0.0045 | 0.0207 |

Score improvement by dimension:

| Dimension | V4 | V5 | Delta | % Gain |
|---|---|---|---|---|
| Provenance (/30) | 16.7 | 28.3 | +11.6 | +69% |
| Behavioral Change (/30) | 15.3 | 27.3 | +12.0 | +78% |
| Epistemic Calibration (/20) | 6.0 | 19.0 | +13.0 | **+217%** |
| Signal Density (/10) | 4.0 | 9.0 | +5.0 | +125% |
| **Total (/90)** | **42.0** | **83.7** | **+41.7** | **+99%** |

Epistemic Calibration showed the largest gain (+217%) because V4 had no mechanism to express uncertainty. V5's required CANNOT PREDICT section directly addresses the gap.

### V5 Innovations

**1. Citation Stripping:** V5 generates inline citations ([A1], [P3], etc.) during compose for provenance audit. A regex pass strips them for the clean served version. Two files per subject:
- `brief_v5.md` — cited version (human audit, provenance verification)
- `brief_v5_clean.md` — clean version (served to LLMs via MCP)

This solves a fundamental tension: provenance requires citations, but served briefs should be clean prose.

**2. Format Freedom:** No structural prescription. The model adapts format to each subject's behavioral signature. Structure becomes signal, not template.

**3. Rubric-as-Prompt:** The 4-primitive rubric (provenance, behavioral change, epistemic calibration, signal density) is included in the compose prompt. The model optimizes directly for what it's evaluated on. Quality criteria become self-enforcing constraints rather than post-hoc evaluation.

---

## What We Learned — The Arc of the Study

### The Brief Was Too Long, Too Rigid, and Too Confident

V4's problems were interconnected:
- **Too long (9.2K chars)** because it tried to be exhaustive rather than signal-dense
- **Too rigid** because it prescribed structure instead of letting it emerge from the subject
- **Too confident** because it had no mechanism to say "I don't know"

### The Rubric Was Measuring the Wrong Things

The original rubric over-weighted traceability (35%) and under-weighted actionability (12%). A brief that perfectly traces every claim but doesn't change model behavior is useless. The redesigned rubric put Behavioral Change at 3x weight and introduced Epistemic Calibration as a first-class dimension.

### False Positive Guards Are the Highest-Leverage Single Feature

Across every study — S78 format testing, D-079 prompt ablation, rubric evaluation — FP guards consistently produced the largest individual quality gains (+4.6 avg when included, +6% on downstream tasks). What a person doesn't do constrains model behavior more effectively than what they do. But FP guards must be faithful to source material. Fabricated guards are worse than no guards.

### Rubric Awareness Is the Meta-Strategy

The single most effective prompt technique: tell the model what it's being scored on. This works because LLMs are optimizers — given explicit criteria, they optimize for those criteria. This makes rubric design, not prompt engineering, the highest-leverage activity. Get the rubric right and the prompt follows.

### Focused Beats Comprehensive

C28 (2 additions) beat C30 (all additions). More instructions create competing optimization targets. The compose prompt should include the minimum constraints needed and let the model handle the rest.

### Epistemic Calibration Is the Novel Contribution

No comparable personalization system includes "not active when" conditions, [CONTESTED] tags, or "cannot predict" gaps. An LLM that knows where its behavioral model breaks down is more useful than one that's confidently wrong everywhere. This is Base Layer's contribution to the field.

---

## Reconciling Contradictions

| S78 Said | Ablation Said | Resolution |
|---|---|---|
| Shorter is better (1-2.5K chars) | Best briefs are 3.5-5K chars | Different measures. S78 measured downstream task accuracy; ablation measured composition quality. Model-dependent sweet spot. |
| More data hurts | More source coverage is better | INPUT volume hurts; OUTPUT coverage of compressed patterns helps. Not contradictory. |
| Adding content hurts | C28-C30 add sections and score highest | S78 added redundant content; C28 added novel epistemic content. New information types improve; more of the same degrades. |
| Collective review is ceremonial | Study uses Collective review for scoring | Review as generation step is ceremonial. Review as evaluation with a defined rubric is valuable. Different function. |

---

## What's Still Unvalidated

1. **Twin-2K V5 not run.** V4 scored 71.83% on the external benchmark (N=100, p=0.008). V5 needs the same validation. Hypothesis: smaller + denser should maintain or improve accuracy.
2. **Human evaluation.** All scoring was Opus-judged, not human-judged. Rubric scores and real-world utility may diverge.
3. **Cross-model transfer.** All composition used Opus. C31 prompt may not produce equivalent quality on Sonnet or local models.
4. **Behavioral differentiation.** All briefs were scored individually. Need same-prompt-different-brief tests to verify briefs produce meaningfully different LLM behavior across subjects.

---

## Timeline Summary

```
S78     Compression & Format Study
        → Production brief 3-9x too long
        → Annotated guide + FP guards = best format (+24%)
        → Behavioral facts > all other fact types
        → Avoidance predicates strongest
        → Shorter is better (1-2.5K optimal)
            ↓
S79     Pipeline Ablation (14 conditions)
        → 10 of 14 steps ceremonial
        → 3-layer architecture load-bearing
        → Authoring load-bearing
        → Pipeline: 14 steps → 4
            ↓
S80     V4 compose prompt locked (informal testing)
        → Score: 42/90 (evaluated retroactively under new rubric)
        → Size: 9,258 chars
            ↓
S85     D-079 Prompt Ablation begins (Rounds 1-5, old rubric)
        → Single-pass beats multi-stage (Round 1)
        → FP-first structure wins (Round 2)
        → FP warnings load-bearing but fabrication-prone (Round 3)
        → FP faithfulness fix works (Round 4, C14 = 73.0/85)
        → Rubric awareness is meta-strategy (Round 5)
        → Old rubric found to be misweighted
            ↓
S85     Rubric redesigned (/85 → /90)
        → 4 primitives from first principles
        → Behavioral Change upgraded to 3x
        → Epistemic Calibration introduced at 2x
            ↓
S85-86  D-079 continues (Rounds 6-7, new rubric)
        → Format freedom produces subject-adapted structure (Round 6)
        → "Cannot predict" is top reviewer suggestion (Round 6)
        → C28 wins at 87.0/90 (Round 7)
        → Focused additions beat comprehensive ones
            ↓
S86     Rubric calibration bug found
        → Faithful paraphrases scored as fabrication
        → Fix: provenance-based evaluation
        → C28 drops to 84.3, C31 rises to 83.7 — statistically tied
            ↓
S87     D-080: Collective selects C31 (unanimous)
        → C31 = C28 + format freedom
        → V5 = C31 + citation stripping
        → 99% score improvement, 56% size reduction, 4.6x signal density
        → All 12 subjects recomposed
        → Two-file system: brief_v5.md (cited) + brief_v5_clean.md (clean)
        → Website updated, pushed live
```

---

## Phase 6: Blind A/B Evaluation — V4 vs V5 on Real Responses (S88)

After the rubric-based evaluation, we ran a 10-question blind A/B test on Aarik — the only subject with ground-truth validation. Each question got two paragraph-length responses: one shaped by V4's voice (9.2K, detail-rich, narrative) and one shaped by V5's voice (4K, compressed, axiom-structured). Aarik picked the better response without knowing which was which.

### Results

| Q | Context | Winner | Signal |
|---|---|---|---|
| Q1 | Red trading day | V4 | Specific details (2-5 contracts, MACD cross, FVG fill) made it land |
| Q2 | Vague job pitch | V5 (slight) | Both good, but V4's personal detail (NASA, B2B SaaS) gave it edge even in loss |
| Q3 | SPY setup, no MACD cross | V5 | Technical specificity (FVG fill, structure break, range window, 2 contracts) |
| Q4 | No traction on launch | Tie | Both nailed "diagnose, don't comfort" — no domain detail needed |
| Q5 | "It's basically RAG" | V5 (slight) | More decisive framing of pushback |
| Q6 | Spouse asks if you're okay | V4 | Vivid behavioral description ("exhausting experience of watching yourself...") |
| Q7 | Trading vs job search | V5 (edge) | Concrete resolution, despite axiom label friction |
| Q8 | Competitor built similar tool | V5 | "First instinct is to audit" — behavioral prediction, not emotional label |
| Q9 | Senior overrides your rec | V5 | Brevity, asks the right question, doesn't over-predict from one event |
| Q10 | What should AI NOT do | Tie (V5 edge) | "Tell me what you can't predict about me" sealed it |

**Final: V5 wins 5, V4 wins 2, ties 2 (V5 edge), 1 clean tie.**

### Qualitative Findings

**1. V5's behavioral model is correct.** It steers interactions the right way — brevity, right questions, decisive framing. The structural improvements (rubric-as-prompt, CANNOT PREDICT, format freedom) are validated by blind preference.

**2. V4 wins when concrete facts ARE the response.** Q1 (trading specifics) and Q6 (emotional specificity) — both cases where the detail IS the value, not decoration. V5 compressed away the facts that make domain-specific responses land.

**3. Axiom labels hurt when cited as rules, work when woven into predictions.** "Your foundational-focus axiom says" breaks immersion (Q7, negative). "Your coherence axiom won't let you dismiss this" works (Q8, positive) because it's embedded in a behavioral prediction, not cited like a regulation.

**4. Opening lines matter disproportionately.** Q8: "Your first instinct is to audit" (V5, behavioral prediction, chosen) vs "This triggers defensibility anxiety" (V4, emotional label, rejected). The first sentence determines whether the response feels like it "gets" you.

**5. Don't over-predict from single events.** Q9: V4 predicted emotional disengagement from one meeting override. Aarik's response: "one instance would not cause this to happen." The brief must respect tier awareness — situational patterns aren't identity-level.

**6. Don't prescribe what the person needs.** Q9: "What you need from an ally" (V4, rejected) vs asking "is this about the specific decision or the pattern?" (V5, chosen). Collaborative questioning beats directive framing.

### The Diagnosis: Compression Fidelity, Not Format

V5 is the better brief. The only thing it's missing are the concrete facts that got abstracted away during compose. The authored layers (Core, Predictions) preserve all the detail — MACD (6,18,4), FVG confluence, position sizing limits, NASA contracts, execution gap specifics. The compose step compressed them out.

**The fix is not a new brief version. It's a serving architecture change.**

### Proposed Architecture: Brief + Dynamic Fact Injection

The brief stays compressed at ~4K chars — it provides behavioral steering (how to interact). When specific sections of the brief activate in conversation (trading context, career context, technical context), the system retrieves the concrete facts that make those sections land.

```
V5 Brief (4K, behavioral steering)
    ↓ conversation activates a brief section
    ↓ e.g., "trading execution gap" mentioned
    ↓
MCP recall pulls relevant facts
    ↓ e.g., MACD (6,18,4), FVG, 2-5 contracts, position sizing rules
    ↓
Effective context = Brief + Retrieved Facts
```

This is the stacking hypothesis applied to the brief itself: **Brief + Facts > Brief alone.** The brief provides shape. The facts provide substance. Neither is sufficient alone — V4 proved that facts without structure bloats to 9K; V5 proved that structure without facts loses domain specificity.

The MCP server's `recall` tool already exists. It just isn't wired to brief activation zones. The pieces are built — they need to be connected.

### Implications for D-081

1. **V5 compose prompt is locked.** No changes needed to the compose step.
2. **Fact injection is a serving-layer change**, not a pipeline change. The pipeline produces the brief and the facts independently; serving combines them at query time.
3. **Activation detection** is the open design question: how does the system know which brief section is active? Options: keyword matching, embedding similarity between user message and brief sections, or explicit section headers in the brief that map to fact categories.
4. **This validates the stacking benchmark hypothesis.** System X + Base Layer > System X alone. The brief is the identity layer; facts are the memory layer. Both are needed. This is the architectural distinction Base Layer has been making since S62.

---

*31 conditions. 3 subjects. 7 rounds. 2 rubric versions. 1 rubric calibration bug. 1 blind A/B test. ~$18.40. The brief got 99% better, 56% smaller, and validated by the subject himself. The remaining gap — concrete fact retrieval — is a serving problem, not a composition problem.*
