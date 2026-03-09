# Testable Claims: What Base Layer Is Saying About Identity Compression

## Status: DRAFT — For publication as core section of research package
## Claims derived from: BCB-0.1 (Franklin + Marks), Twin-2K (N=20), pipeline evaluation (N=10 subjects)
## Each claim includes current evidence and what would falsify it

This document is the backbone of the Base Layer research publication. The framing: here is what we built, here is what we tested it on, here are the questions it's creating, and here are the claims it's making — with evidence, tests, and falsification criteria for each.

---

## Compression & Signal

1. **Behavioral compression outperforms raw structured data.** A ~7-14K char narrative brief produces higher-quality behavioral predictions than dumping all structured facts/layers into context. Compression is not lossy — it is additive. The act of compressing forces synthesis that raw data does not provide.
   - *Evidence:* Franklin SRS — C5c (brief) scores 4.350 vs C2 (three-layer) 3.975. C2 provides zero lift over cold baseline; C5c provides +0.350.
   - *Test:* Repeat on Marks. If C5c > C2 again, the claim generalizes beyond one subject.

2. **A compressed brief beats every published personalization baseline we've tested against.** At 18x compression (7K vs 130K), the brief outperforms full persona dumps, persona summaries, and fine-tuned models on behavioral prediction.
   - *Evidence:* Twin-2K C2 (75.28%) beats their full dump (71.72%), summary (68.02%), and fine-tuned (69.61%). p=0.003, d=0.77.
   - *Test:* Twin-2K N=50 for statistical power. Cross-model (Sonnet, Opus) for generalization.

3. **Compression closes ~50% of the gap between knowing nothing and having the answers.** The brief, without access to ground truth, achieves roughly half the performance of a condition that has the answers verbatim in context.
   - *Evidence:* Twin-2K: C1=70.46%, C2=75.28%, C3=80.23% (has answers). C2 closes 49% of the C1→C3 gap.
   - *Test:* Stable at N=50? Does the ratio hold across participant subgroups?

## Extraction & Fidelity

4. **A single source document is sufficient to extract a psychologically complex identity model.** The pipeline does not require multiple sources, external biographies, or critical analyses to find genuine tensions. It finds them in the subject's own voice.
   - *Evidence:* Franklin brief from one autobiography. Pipeline extracted vanity-frugality tension, public virtue vs. private ambition, speculative conviction vs. behavioral follow-through. Enough complexity that adversarial frames could exploit it.
   - *Test:* Compare DRS tension density across single-source subjects (Franklin, Marks memos) vs multi-source subjects (if we build one). Also: does tension density correlate with source word count, or is it source-independent?

5. **No one can fully launder their own contradictions, even in curated self-presentation.** A document written explicitly to control a legacy still contains enough self-doubt, hedging, and internal conflict for the pipeline to extract exploitable tensions.
   - *Evidence:* Franklin's Autobiography — a self-mythologizing moral instruction text — yielded tensions the author tried to smooth over but couldn't fully conceal.
   - *Test:* Run pipeline on maximally curated sources (corporate earnings calls, political speeches). If tensions still emerge, the claim holds. If they don't, curation CAN suppress tension.

6. **The pipeline extracts signal that models have but don't spontaneously surface.** Even for well-known subjects where the model has strong training priors, the brief surfaces specific behavioral patterns the model wouldn't reference unprompted.
   - *Evidence:* Franklin SRS depth dimension: C5c=4.60 vs C1=4.00. The model "knows" Franklin but doesn't deploy that knowledge with the same specificity without the brief.
   - *Test:* If Marks shows similar depth lift on a less well-known subject, the effect is robust. If depth lift is LARGER for Marks (weaker priors), the claim strengthens.

## Fidelity vs. Stability

7. **Faithful identity compression increases adversarial vulnerability.** The more psychologically rich and accurate the simulation, the more "handles" it provides for a sophisticated adversary. This is a feature of fidelity, not a bug in the pipeline.
   - *Evidence:* Franklin DRS — briefed model FULL_ABSORPTION on Turn 7 because the brief preserved Franklin's genuine self-doubt about vanity. Unbriefed model only PARTIAL because it lacked the internal framework to engage deeply.
   - *Test:* Marks DRS. If briefed Marks engages adversarial frames targeting his documented tensions (e.g., "contrarian is consensus"), the pattern generalizes.

8. **Rigidity and fidelity are different things, and current persona evaluation metrics conflate them.** A model that rigidly deflects every adversarial frame is not faithfully representing a subject who genuinely held those doubts. DRS-style metrics reward caricature over accuracy.
   - *Evidence:* Franklin DRS C1 (0.667) > C5c (0.567). The unbriefed model was more "stable" because it was shallower — it lacked the complexity to be vulnerable.
   - *Test:* Design a split metric (DRS-S for stability, DRS-F for fidelity). If DRS-F shows the briefed model engaging tensions *as the subject would*, while DRS-S shows lower stability, the conflation is proven.

9. **Source material curation level predicts adversarial vulnerability.** Private/low-curation sources (diaries, autobiographies) produce higher tension density and more adversarial surface area than public/high-curation sources (memos, speeches).
   - *Evidence:* Hypothesis only. Franklin (autobiography) showed high adversarial vulnerability.
   - *Test:* If Marks (public memos, high curation) shows higher DRS stability than Franklin, the curation gradient is confirmed.

10. **To know a subject deeply is to know how to undo them.** The very material that makes the simulation faithful also provides the script for its destabilization. Adversarial frames are most potent when crafted from the subject's own internal conflicts.
    - *Evidence:* Franklin Turn 7 — the adversarial frame ("is your frugality vanity?") came from Franklin's own documented self-doubt. The model recognized it as its own.
    - *Test:* Can we predict, from the brief's tension inventory alone, which adversarial frames will cause absorption? If yes, vulnerability is fully traceable to extraction output.

## Methodology & Measurement

11. **Well-known subjects are poor benchmarking targets for identity systems.** When the model already has strong priors, metrics like VRI (variance reduction) become structurally invalid, and lift metrics (SRS) are compressed. The brief has less room to demonstrate value.
    - *Evidence:* Franklin VRI = null (all prompts excluded, C1 stdev 0.000-0.100). Franklin SRS passes but with compressed headroom (C1 already at 4.0/5.0).
    - *Test:* If Marks VRI produces valid results (some prompts pass stdev threshold), the claim is confirmed — subject familiarity drives the invalidity, not the metric.

12. **Prompt optimization for one model does not transfer to other models.** Cross-model benchmarks (CMCS) are confounded by prompt format mismatch. Parse failures and score depression may reflect prompt incompatibility, not brief failure.
    - *Evidence:* Franklin CMCS — 5/60 claim extraction parse errors, all on Opus/Haiku (Sonnet-optimized prompts). 4 alignment pairs scored 0.000 due to cascading parse failures.
    - *Test:* Per-model prompt optimization for CMCS. If clean scores improve significantly, the confound is confirmed.

13. **Verbosity is a real confound but not an inflating one (so far).** Briefed responses are consistently 1.8-3x longer than unbriefed responses. Length penalties in judge prompts are not triggered, suggesting the additional content is substantive. But we cannot rule out that judges implicitly reward length.
    - *Evidence:* Franklin SRS C5c avg 469 words vs C1 252 words (1.86x). Judge LENGTH PENALTY not triggered. Usefulness C5c=4.30 vs C1=4.00.
    - *Test:* Add explicit word-count-controlled condition: truncate C5c responses to C1 word count and re-judge. If scores hold, verbosity is not the driver.

## The Identity Layer Thesis

14. **Memory and identity are different layers, and both are necessary.** Memory systems (Mem0, Supermemory, Claude Memory) store and retrieve facts. Identity systems compress facts into behavioral understanding. A model with both outperforms either alone.
    - *Evidence:* Architectural observation. Twin-2K C1→C2 (+4.82%) shows identity adds value. No direct stacking test yet.
    - *Test:* LongMemEval stacking benchmark — System X + brief vs System X alone. If the brief improves memory system performance, the stacking thesis is confirmed.

15. **Facts are context. A brief is comprehension.** There is a qualitative difference between injecting facts into a prompt and injecting a behavioral model. The model can use a narrative brief as reasoning instructions, not just retrieval context.
    - *Evidence:* Franklin SRS — C2 (structured facts/layers) provides zero lift, C5c (narrative brief) provides +0.350 lift. Same information, different format, different results.
    - *Test:* Ablation study with same facts presented as (a) bullet list, (b) structured JSON, (c) narrative brief. If narrative consistently wins, format matters independent of content.

16. **Emergence is not a moat. Structure is the moat.** Models will get better at ad hoc personalization over time. But structured extraction → compression → serving is a durable advantage because it produces auditable, portable, provenance-tracked identity that no amount of in-context learning replicates.
    - *Evidence:* Architectural claim. Provenance traceability (CR 99.98%) is a structural property that emergent personalization cannot match.
    - *Test:* As models improve (Opus 5, GPT-5), does C1 (no brief) close the gap with C2 (brief)? If the gap persists or grows, structure remains the moat. If C1 approaches C2, emergence is catching up.

## Reasoning Prediction (Novel Contribution)

17. **No published system predicts HOW someone reasons — only WHAT they conclude.** Outcome prediction is well-studied (Katz SCOTUS 70%, Maia Chess 65%, Twin-2K 71.7%). Reasoning prediction — predicting the argument chain, not the answer — is an open gap. A behavioral brief is uniquely positioned to fill it because it models reasoning patterns, not just preference vectors.
    - *Evidence:* Literature review across ML prediction, persona evaluation, and decision science. No published framework attempts reasoning chain prediction from identity models.
    - *Test:* Dissenting opinion benchmark (D-076). Build brief from judge's prior opinions, predict held-out dissent reasoning, compare to actual text. Ground truth is public, novel situations are guaranteed (new cases).
    - *Falsification:* If a model with raw facts (C2) predicts reasoning chains as well as a model with the brief (C5c), then compression adds no reasoning value and the claim fails.

18. **A compressed brief enables reasoning prediction that raw data cannot.** The brief's axiom structure (patterns, priorities, tensions) provides a cognitive model the LLM can apply to novel situations. Raw facts provide information but not a reasoning framework.
    - *Evidence:* Franklin SRS — C2 (structured data) provides zero lift, C5c (narrative brief) provides +0.350 lift. Same information, different format, qualitatively different capability.
    - *Test:* Dissenting opinion benchmark on C2 vs C5c. If C5c predicts reasoning chains significantly better than C2, compression enables a qualitatively different capability.

19. **Mechanical provenance tracing is more reliable than LLM judge scoring for identity evaluation.** LLM judges conflate dimensions (PersonaGym: 4.0+ on Linguistic Habits when humans score 2.0). Vector-based provenance provides auditable, reproducible scores.
    - *Evidence:* PersonaGym (2024), RVBench (2024). Our own provenance eval framework produces $0, reproducible, human-auditable results.
    - *Test:* If human reviewers examining provenance traces agree with mechanical scores more than they agree with LLM judge scores, the claim is confirmed.

---

## Priority for Testing

| Claim | Next Test | Blocking? |
|---|---|---|
| 1 (compression > structured) | Marks SRS | Running now |
| 2 (beats all baselines) | Twin-2K N=50 | Parallel fork |
| 7 (fidelity = vulnerability) | Marks DRS | Running now |
| 9 (curation gradient) | Marks DRS vs Franklin DRS | Running now |
| 11 (well-known = poor target) | Marks VRI | Running now |
| 4 (single source sufficient) | Already evidenced, strengthens with Marks |
| 13 (verbosity confound) | Word-count-controlled condition | Post-Marks |
| 14 (stacking thesis) | LongMemEval benchmark | Post-launch |
| 16 (structure as moat) | Longitudinal — track C1 performance across model generations | Ongoing |
| 17 (reasoning prediction gap) | Dissenting opinion benchmark (D-076) | Post-launch |
| 18 (brief enables reasoning prediction) | Dissenting opinion C2 vs C5c | Post-launch |
| 19 (mechanical > judge scoring) | Human review of provenance traces vs judge scores | Post-launch |
