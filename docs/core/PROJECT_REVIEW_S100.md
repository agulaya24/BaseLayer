# Project Review — Session 100 (2026-03-30)

Comprehensive assessment of Base Layer at the 100-session mark. Written to be honest about what works, what does not, and where the real risks are.

---

## Current State

**Pipeline:** 4-step pipeline (Import, Extract, Author, Compose) is stable and tested. H3 prompts adopted across all three authoring layers after a rigorous ablation study (S99) that proved the domain-agnostic guard is the single load-bearing addition. Prompt size dropped 78% (2,903w to 645w) with zero quality loss.

**Subjects:** 44+ subjects H3-authored. 17 Wave 4/5 subjects seeded to thinkers pages. 92 total subjects tracked on the dashboard. Katie Parrott added as a new subject (43 posts, 206 facts). Dan Shipper re-extracted with expanded corpus (244 to 549 facts).

**Compose prompt fixed:** They/them pronoun enforcement eliminates gender inference. Domain guard added to compose step to prevent reassembling topic-specific content from domain-agnostic layers. Validation: 0 he/him pronouns across entire 38-subject recompose batch.

**Structured outputs:** Prediction schema (Pydantic BaseModel with id, name, trigger, response, detection, directive, false_positive_warning) validated on Scott Alexander. Schemas drafted for all three layers (Anchors, Core, Predictions). Not yet wired into production pipeline.

**Serving layer:** Spec drafted (SERVING_LAYER_SPEC.md). Architecture: always-on anchors, context-routed core modes, trigger-matched predictions, vector fact retrieval, correction gate, assembly, brief fallback. No implementation yet.

**Design principles:** D-089 and D-090 added. Cross-discipline research survey completed (S100) identifying 10 academic analogs, most notably: PersonaMem (frontier models fail at 50% of user modeling -- strongest empirical argument for Base Layer), sycophancy amplification from user profiles (validates FP guards as load-bearing), and MDL theory predicting the three-layer architecture.

**Other:** Overnight GPU pipeline test running. Wave 4 Gmail drafts pushed (13/16). Scott Alexander emailed with H3 V2 + magic link. Sycophancy study email sent to Stanford researchers. 12 follow-up drafts ready for Wave 1/2/3.

---

## What's Working

### H3 prompts eliminated topic skew
The ablation was the single most important quality improvement in the project's history. Before: Scott Alexander's model opened with prediction markets (5% of his data treated as core identity). After: 0 prediction market mentions, 0 trading skew in Aarik's model. The domain-agnostic guard ("How someone reasons IS identity. What they reason ABOUT is not.") is 73 words and does all the work. 700 words of accumulated prompt ceremony across 98 sessions was proven inert.

### Pronoun enforcement works
They/them universally, no gender inference. 0 he/him across all 38 recomposed subjects. This was a blocking issue for Maggie Appleton outreach and is now resolved.

### Brief opening quality improved
Briefs now open with behavioral observations ("approaches every decision through...") rather than topic summaries ("writes about prediction markets and rationality"). This is the difference between a personality model and a topic classifier.

### Cross-domain predictions with false-positive warnings
The prediction format (trigger, response, detection across 3 domains, directive, FP warning) is the most actionable layer for AI consumption. FP warnings are validated by the MIT/Penn State sycophancy paper as load-bearing architecture, not polish.

### Research publications on website
Prompt ablation study, predicate spec, and cross-discipline survey all published on research page. These are credibility assets for outreach and academic positioning.

### Compression saturation finding holds
20% of facts is enough for identification (Twin-2K). PersonaX (ACL 2025) independently found 30-50% of behavioral data captures the signal. The pipeline's value is extraction + compression. The three-layer architecture is information-theoretically optimal per MDL theory.

---

## What Needs Improvement

### Parser fragility is the top technical debt
The markdown parser broke 4 times on different heading formats during the H3 rollout (period separators, em-dash separators, colon separators, inconsistent heading levels). Each time required a code fix. This is the strongest argument for structured outputs: eliminate regex parsing entirely. JSON schema constrained decoding produces deterministic format. The parser is a fragile bridge between free-form LLM output and a structured seed pipeline. It should not exist.

### Version history is a mess
Version history was cleared for most subjects, then reverted, then re-cleared. The V1/V2 distinction is confused: some subjects had "V2" that was just a flawed prompt re-run, not a corpus expansion. Kevin Kelly is the only real V2 (corpus went from 76 to 2,824 facts). The decision to seed everything as V1 (H3) with no version history is correct but represents sunk work on the version history UI.

### No automated quality gates
Every compose output requires manual review. There is no programmatic check for: topic skew (count domain-specific terms), pronoun compliance (scan for he/him/she/her), brief opening pattern (does it start with behavior or topic?), anchor count compliance (8-10 target, most produce 13-16). All of these are mechanically verifiable. The absence of automated gates means quality is only as good as the reviewer's attention, which does not scale to 92 subjects.

### Compose step can still reassemble topic content
The domain guard in author prompts works. But the compose step takes domain-agnostic layers and can reassemble topic-specific content from them. Kevin Kelly's H3 brief still had 25 AI topic mentions. Dan Shipper had 24. The compose prompt domain guard was added but not yet validated at scale. This is a known leak in the pipeline.

### No serving layer implementation
The spec is solid (always-on anchors, routed core, triggered predictions). The academic validation is strong (PersonaFuse MoE architecture is exactly this pattern). But there is no code. The identity model is currently a static document pasted into context. The activation matching that would make it an intelligent system -- selecting only the relevant behavioral patterns per query -- does not exist. This is the gap between "useful document" and "product."

### Batch API not enforced for extraction
Extraction still runs sequential API calls. Batch mode was partially added in S98 but never completed for document mode. For large corpora (Zvi: 1,089 files, Gwern: 355 files, Tomasz: 1,679 files), this is a significant cost and time multiplier.

### Anchor cap not holding
H3 prompts specify 8-10 axioms. Most subjects produce 13-16. This is either a prompt compliance failure or evidence that 8-10 is too tight. Either way, it means the output is not conforming to spec and the constraint is not enforced programmatically.

### Extraction quality unverified across models
The overnight GPU test (S94) showed mistral:7b produced the most facts (59 vs qwen2.5:14b at 22), but fact count is not fact quality. No quality review has been done. The default local model may be wrong.

---

## Blocked Items

| Item | Blocker | Impact |
|------|---------|--------|
| Dan Luu, Derek Thompson, Nathan Lambert outreach | Bounced emails, no correct addresses found | 3 Wave 2 subjects unreachable |
| Jonathan Fulton, Eli Tyre outreach | Need real email addresses | 2 Wave 3 subjects unreachable |
| Stacking test scoring | 100 responses logged but unscored across 5 conditions | Research page shows "Coming Soon," Reddit r/ClaudeAI post blocked |
| Context-1 not available as downloadable model | Anthropic product constraint | Cannot test local serving of identity models |
| Jack Clark + Amanda Askell pipelines | Awaiting pipeline refactor completion and prioritization | 457 + 34 files scraped but not processed |
| Wave 4 priority subjects (Sivers, Visakan, patio11) | Need seeding pipeline run | Outreach blocked |

---

## Honest Assessment of Risk

### The project has a distribution problem, not a quality problem
The pipeline works. The identity models are good. The ablation study is rigorous. The academic analogs are strong. But: 29 thinkers pages live, 3 Waves of outreach sent, and engagement is limited to Scott Alexander (active, 3 unlock attempts) and Maggie Appleton (engaged). The conversion rate from "email sent" to "meaningful engagement" is low. This is normal for cold outreach to public intellectuals, but it means the traction thesis is unproven.

### The serving layer is the product gap
Without activation matching, Base Layer is "a really good prompt you paste." That is useful but not defensible. Every LLM provider is building memory features (ChatGPT memory, Claude memory, Gemini memory). The PersonaMem paper shows they fail at 50% of the task -- but they are improving. The serving layer (activation matching, correction gates, fact retrieval) is what makes Base Layer a system rather than a document. It needs to ship.

### Research backlog is growing faster than it ships
Stacking test (100 responses, unscored). Temporal prediction test (specced, not run). Twin-2K V5 rerun (specced, not run). ADRB benchmark (specced, not run). Cross-model portability proof (not started). Agentic wedge domain proof (not started). LongMemEval stacking benchmark (specced, not started). Each of these is $15-30 and a few hours of work. None have shipped. The research page has findings from S79-S99 but the evaluation pipeline is not keeping pace with the authoring pipeline.

### Too many subjects, not enough depth
92 subjects tracked. 44 H3-authored. But the depth per subject varies wildly: Aarik has 1,892 conversations, Kevin Kelly has 2,824 facts from V2, while Amanda Askell has 34 files and Dario has 4. The pipeline treats all subjects as equivalent but they are not. A 34-file corpus cannot produce a high-quality identity model. There is no minimum corpus threshold enforced.

### The outreach cadence is fragile
Emails are manually drafted with prediction picks, magic links, custom passwords, and fact count verification. Each wave requires: re-authoring with latest prompts, seeding to website, generating magic links, pushing Gmail drafts, and manual send. This is a multi-hour process for each batch. There is no automation beyond `push_gmail_drafts.py`. Scaling to 100+ subjects at this cadence is not feasible.

---

## Next Priorities (Ordered)

1. **Finish seeding all subjects.** 44 H3-authored subjects need to be pushed to thinkers pages. This unblocks all outreach. Wave 1/2/3 recomposed subjects and Wave 4/5 new subjects both need seed runs.

2. **Wave 4/5 outreach emails (Tuesday target).** 16 drafts generated. 13/16 Gmail drafts pushed. 3 need manual email addresses (Jack Clark, Ava Huang, Julia Galef). Magic links at send time. This is the largest single outreach push since Wave 1.

3. **Wire structured outputs into production pipeline.** Prediction schema validated. Extend to Anchors and Core. Replace regex parsing with JSON schema constrained decoding. This eliminates the parser as a failure mode and enables the serving layer to consume structured data directly.

4. **Serving layer Phase 1 MVP.** Activation matching: score user prompt against authored "Active when:" conditions in Core and "Trigger:" conditions in Predictions. Select top-k. Assemble context payload. This is the minimum viable product that turns the identity model from a document into a system.

5. **Automated quality gates.** Programmatic checks for: topic skew (domain term frequency), pronoun compliance, brief opening pattern, anchor count, prediction format compliance. Run on every compose output. Block seeding if checks fail.

6. **Temporal prediction test.** Split Aarik's 1,892 conversations by year. Build 2024 model with H3. Test against 2025/2026 behavior. Cost: ~$20. This is the most novel research contribution available: does the identity model predict future behavior?

7. **Score the stacking test.** 100 responses across 5 conditions are logged and unscored. This blocks the Reddit r/ClaudeAI post and the research page update. It is the cheapest unfinished research item.

8. **Daemon agent prototype.** Long-term: a persistent agent that consumes the identity model via the serving layer and maintains context across sessions. This is the product vision but depends on the serving layer existing first.

---

## Summary at 100 Sessions

Base Layer has proven three things:

1. **Behavioral compression works.** 47 predicates, 3-6K token output, 71.83% identification accuracy at 18:1 compression. The academic literature is converging on the same architecture independently.

2. **The prompt is the product.** The H3 ablation proved that 73 words of domain guard do more than 700 words of accumulated instruction. The identity model's quality is determined by authoring prompt design, not pipeline complexity. 10 of 14 original pipeline steps were ceremonial.

3. **Distribution is the bottleneck.** The pipeline is good. The models are good. The website is live. But traction requires sustained outreach, and outreach requires a non-fragile process. The serving layer is the technical moat. Structured outputs are the reliability foundation. Neither exists in production yet.

The project is at an inflection point: the core technology is validated, but the gap between "validated research artifact" and "product people adopt" is where most projects die. The next 10 sessions will determine which side of that gap Base Layer lands on.
