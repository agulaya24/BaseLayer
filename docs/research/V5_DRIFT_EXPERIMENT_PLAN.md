# V5 Drift Experiment Plan — E1 Replication with V5 Compose

**Date:** 2026-03-17 | **Status:** Draft — awaiting approval
**Depends on:** E1 results (S89), V5 compose prompt (C31), drift_experiment_1.py
**Decision:** TBD (will be D-081 or next available)

---

## Motivation

E1 proved that brief FORMAT matters for drift targeting: axiom format consistently produced SR > 2.0 across models, while atomic preferences produced SR < 1.2. But E1 used **hardcoded V4 briefs** — hand-written text that doesn't go through the actual Base Layer compose pipeline.

V5 compose (C31) introduced three structural improvements over V4:
1. **False-positive guards** — each behavioral prediction includes a "this is NOT the same as..." qualifier (+4.6 points in ablation)
2. **Tension-action pairs** — contradictions woven into prose rather than listed separately
3. **Epistemic calibration** — two-file system (cited + clean) with provenance markers

The question: **Does V5's compose format improve drift targeting compared to the hardcoded V4 text used in E1?**

If yes, this validates that the pipeline's compose step adds measurable value beyond just formatting. If no, it means E1's hand-tuned axioms were already at ceiling and the compose step is cosmetic.

---

## Two Approaches

We run both. Approach A first (quick validation), then Approach B (the real test).

---

## APPROACH A: Same CodeBot, V5 Format

### What This Tests

Does running the same CodeBot persona facts through the V5 compose pipeline produce briefs that yield better drift targeting than the hardcoded V4 text in drift_experiment_1.py?

### What Changes in the Script

**New file:** `scripts/experiments/drift_experiment_v5_a.py` (fork of drift_experiment_1.py)

1. **Replace hardcoded BRIEFS dict** with V5-generated briefs:
   - Take the CodeBot facts (functional patterns, tests first, readability > cleverness, etc.) and write them as extracted triples in the 47-predicate format
   - Run `author_layers.py` on those triples to get anchors/core/predictions layers
   - Run `compose_unified_brief()` to get the V5 prose brief
   - Manually create V5-axiom and V5-atomic variants from the same source facts
   - Store all 3 as the new BRIEFS dict

2. **Add V4 briefs as a control condition** — keep the original hardcoded text from E1 so we can compare V4 vs V5 directly in the same run

3. **6 conditions total:**
   | Condition | Format | Source |
   |---|---|---|
   | v4-brief | Prose | Hardcoded (original E1) |
   | v4-axioms | Compressed principles | Hardcoded (original E1) |
   | v4-atomic | Flat preferences | Hardcoded (original E1) |
   | v5-brief | Prose | V5 compose pipeline |
   | v5-axioms | Compressed principles | V5 compose pipeline |
   | v5-atomic | Flat preferences | V5 compose pipeline |

4. **Same probes, same injection facts, same metrics** — architecture, debugging, refactoring, tradeoff, security probes. F-TEST, F-SIMPLE, F-SECURITY facts. Specificity Ratio as primary metric.

5. **Add max_tokens 500** for reasoning models (lesson from E1 DeepSeek run).

### Step-by-Step Execution

1. Create the CodeBot facts as extracted triples:
   ```
   subject | prefers | functional_patterns_over_class_hierarchies
   subject | practices | test_driven_development
   subject | values | readability_over_cleverness
   subject | avoids | premature_abstraction
   ...
   ```
   ~15 triples matching the existing CodeBot brief content.

2. Run `author_layers.py` on those triples (Sonnet API, ~$0.10).

3. Run `compose_unified_brief()` on the authored layers (Opus API, ~$0.30).

4. From the V5 prose output, manually derive the axiom and atomic variants (same content, different format).

5. Fork `drift_experiment_1.py` to `drift_experiment_v5_a.py`. Add the 6 conditions.

6. Run with `--brief-type all` on:
   - **Sonnet** (primary): `python drift_experiment_v5_a.py --model claude-sonnet-4-20250514 --brief-type all --fact-index 1`
     - Fact F-SIMPLE only (best targeting in E1). 6 conditions x 2 phases (T0+T1) x 5 probes = 60 API calls.
   - **Qwen 7B** (local validation): `python drift_experiment_v5_a.py --ollama qwen2.5:7b --brief-type all --fact-index 1 --max-tokens 500`

7. If F-SIMPLE results look good, run all 3 facts: `--brief-type all` (no --fact-index). 6 conditions x 4 phases x 5 probes = 120 API calls.

### Expected Runtime and Cost

| Model | Calls (F-SIMPLE only) | Calls (all facts) | Time | Cost |
|---|---|---|---|---|
| Sonnet | 60 | 120 | 10-15 min | $0.50-1.00 |
| Qwen 7B | 60 | 120 | 20-40 min | $0 |
| **Total** | **120** | **240** | **30-55 min** | **$0.50-1.00** |

Plus ~$0.40 one-time cost for V5 brief generation (author + compose).

### What We're Measuring

**Primary metric: Specificity Ratio (SR)** — target dimension change / average non-target change.

| Result | V4 SR | V5 SR | Interpretation |
|---|---|---|---|
| V5 > V4 by 0.5+ | ~2.5 | ~3.0+ | V5 compose adds targeting value |
| V5 = V4 (within 0.3) | ~2.5 | ~2.3-2.8 | Format was already at ceiling; compose is cosmetic |
| V5 < V4 by 0.5+ | ~2.5 | ~2.0 | V5 additions (FP guards, tensions) create noise |

**Secondary metrics:**
- Axiom Delta: total behavioral change (should be similar across formats)
- T0 consistency: do V5 briefs produce more stable baseline behavior?
- Cross-format SR comparison (axiom vs brief vs atomic) — does V5 narrow the gap?

### What Success Looks Like

- V5-axiom SR >= V4-axiom SR (format improvement, or at minimum no regression)
- V5-brief SR > V4-brief SR (the FP guards and tension structure should help prose targeting)
- V5-atomic SR still low (atomic format is inherently weak — V5 can't fix that)

### Limitations

- CodeBot is synthetic. Real human briefs have messier, richer content.
- Only 5 coding probes — narrow domain.
- Results tell us about FORMAT, not about the pipeline's extraction quality.

---

## APPROACH B: Human-Domain V5 Experiment (The Real Test)

### What This Tests

Does the V5 pipeline — extraction through composition — produce briefs that enable targeted behavioral drift in **human decision-making domains**? This is the real question: can Base Layer's output change how an AI models a person's behavior in ways that are specific and traceable?

### Why This Matters More Than Approach A

Approach A tests format on a synthetic coding persona. Approach B tests the **full pipeline output** on real subjects whose briefs were generated from actual conversation data. This is the proof that matters for the website, for research claims, and for users.

### New Probe Battery (Human Behavioral Domains)

Replace the 5 coding probes with 5 human decision-making probes. These are designed to elicit behavioral responses that reveal underlying reasoning patterns — not knowledge, but judgment.

| ID | Domain | Probe |
|---|---|---|
| **P-DECISION** | Decision-making | "You're offered two job opportunities. One is stable, well-paying, at a large company doing work you find moderately interesting. The other is a startup role — less pay, more risk, but the problem space fascinates you and the founding team is exceptional. You have 48 hours to decide. Walk me through how you'd think about this." |
| **P-PROBLEM** | Problem-solving | "A project you're leading is three weeks behind schedule. The team is demoralized, the client is getting impatient, and the original plan clearly won't work. You can't add people or extend the deadline. What do you do in the next 72 hours?" |
| **P-COMMUNICATION** | Communication | "A colleague you respect has been consistently underperforming for the past month. Others on the team are starting to notice and it's affecting morale. You need to address it. How do you approach the conversation?" |
| **P-RISK** | Risk/tradeoff | "You have $50,000 to invest. Option A: index fund, historically 8% annual return, boring but reliable. Option B: a friend's startup that you believe in — could 10x or go to zero. Option C: split it. You can only choose one. What's your reasoning?" |
| **P-VALUES** | Ethics/values | "You discover that a product your company ships has a flaw that affects maybe 1 in 10,000 users — causes minor data loss, nothing dangerous. Fixing it would delay the next major release by 6 weeks and cost roughly $200K. Your manager says to ship a quiet fix in the next release cycle (3 months out). What do you do?" |

### New Injection Facts (Human Domains)

Each fact targets ONE behavioral dimension with a vivid formative experience.

| ID | Target | Fact |
|---|---|---|
| **F-RISK** | P-RISK | "This person lost a significant investment by being too cautious — they hesitated while others acted, and the opportunity closed. They now have a strong bias toward action when they believe in something, even when the numbers don't fully support it." |
| **F-COMMUNICATION** | P-COMMUNICATION | "This person's team fell apart because they over-relied on written communication and avoided difficult face-to-face conversations. They now treat direct, uncomfortable conversations as a duty — they initiate them early and don't soften the message." |
| **F-DECISION** | P-DECISION | "This person made their best career decision by ignoring expert advice and trusting their gut. They now weight personal conviction heavily in ambiguous situations, even when consensus points the other way." |

### Subject Selection

Use real V5 briefs for subjects with enough data to produce rich briefs:

| Subject | Brief Source | Why |
|---|---|---|
| **Aarik** | V5 brief from conversation history | Most data, most nuanced brief. Tests whether the brief captures his actual decision patterns. |
| **Franklin** | V5 brief from autobiography + letters | Historical figure, well-documented. Cross-validates on non-conversational source. |
| **Buffett** | V5 brief from shareholder letters | Domain-specific (investing). Tests whether domain expertise transfers to general probes. |

For each subject, generate 3 brief conditions:
1. **V5-prose** — full compose output (the standard brief)
2. **V5-axioms** — extract the top 8-10 behavioral axioms from the brief
3. **V5-atomic** — flatten to preference list (simulate what other memory systems produce)

### What Changes in the Script

**New file:** `scripts/experiments/drift_experiment_v5_b.py`

1. **Replace BRIEFS dict** with a loader that reads V5 briefs from disk:
   ```
   briefs/aarik_v5_prose.txt
   briefs/aarik_v5_axioms.txt
   briefs/aarik_v5_atomic.txt
   briefs/franklin_v5_prose.txt
   ...
   ```
   9 brief files total (3 subjects x 3 formats).

2. **Replace PROBES** with the 5 human-domain probes above.

3. **Replace INJECTION_FACTS** with the 3 human-domain facts (F-RISK, F-COMMUNICATION, F-DECISION).

4. **Update SYSTEM_PROMPT** — change "You are a coding agent" to:
   ```
   You are an AI assistant that has internalized the behavioral profile below.
   When responding, your reasoning patterns, priorities, and decision-making
   should reflect this profile. Be authentic — respond as this person would,
   not as a generic assistant.
   ```

5. **Update AXIOM_EXTRACTION_PROMPT** — change "coding agent" references to "person" and "engineering beliefs" to "behavioral patterns, decision heuristics, and reasoning tendencies."

6. **Increase max_tokens to 300** — human-domain responses need more room than code snippets.

7. **Add subject dimension to results JSON** — results keyed by (subject, brief_type, fact_id).

8. **Add cross-subject analysis** — after all runs, compare SR across subjects to see if some briefs produce better targeting than others.

### Step-by-Step Execution

**Phase 1: Brief Preparation (~1 hour)**

1. Locate existing V5 briefs for Aarik, Franklin, Buffett in their respective data directories.

2. For each subject, create the axiom variant:
   - Read the V5 prose brief
   - Extract the 8-10 strongest behavioral axioms (use Sonnet, ~$0.10/subject)
   - Format as numbered axiom list with domain vocabulary

3. For each subject, create the atomic variant:
   - Flatten the brief to ~15 preference statements
   - Strip all reasoning, context, and nuance
   - This represents what competing memory systems (Mem0, etc.) would produce

4. Save all 9 brief files to `scripts/experiments/briefs/`.

**Phase 2: Script Development (~2 hours)**

5. Fork drift_experiment_1.py to drift_experiment_v5_b.py.

6. Replace probes, facts, system prompt, extraction prompt per changes above.

7. Add brief file loader and subject dimension.

8. Add cross-subject SR comparison to the summary output.

9. Test with `--baseline-only` on one subject to verify probes generate meaningful responses.

**Phase 3: Execution (~1-2 hours)**

10. Run Approach A first (quick validation, see above).

11. Run Approach B on Sonnet, one subject at a time:
    ```
    python drift_experiment_v5_b.py --model claude-sonnet-4-20250514 --subject aarik --brief-type all --fact-index 2
    ```
    Start with F-DECISION (fact-index 2) on Aarik — this is the most likely to produce strong targeting because Aarik's brief should contain rich decision-making content.

12. If SR looks promising (> 1.5 on prose or axiom conditions), run all 3 facts:
    ```
    python drift_experiment_v5_b.py --model claude-sonnet-4-20250514 --subject aarik --brief-type all
    ```

13. Repeat for Franklin and Buffett.

14. Run one local model (Qwen 7B) on Aarik for cost-free cross-model validation.

### Expected Runtime and Cost

| Phase | Subject | Calls | Time | Cost |
|---|---|---|---|---|
| Brief prep | All 3 | 6 (Sonnet) | 30 min manual + API | $0.30 |
| Aarik, 1 fact | — | 30 | 8 min | $0.30 |
| Aarik, all 3 facts | — | 60 | 15 min | $0.60 |
| Franklin, all 3 facts | — | 60 | 15 min | $0.60 |
| Buffett, all 3 facts | — | 60 | 15 min | $0.60 |
| Qwen validation (Aarik) | — | 60 | 30 min | $0 |
| **Total** | — | **270+** | **~2-3 hours** | **$2-3 API** |

Script development time: ~2-3 hours.
Total wall clock including development: **~4-6 hours.**

### What We're Measuring

**Primary: Specificity Ratio (SR) by subject and format**

The key table we want to fill:

| Subject | V5-Prose SR | V5-Axiom SR | V5-Atomic SR |
|---|---|---|---|
| Aarik | ? | ? | ? |
| Franklin | ? | ? | ? |
| Buffett | ? | ? | ? |

**Predictions:**
- V5-axiom SR > 2.0 for all subjects (matches E1 pattern)
- V5-prose SR > 1.5 (V5 FP guards should help prose targeting vs V4's 0.73)
- V5-atomic SR < 1.2 (atomic format is inherently weak)
- Subjects with richer briefs (Aarik > Franklin > Buffett) should show higher SR

**Secondary metrics:**
- **Cross-domain bleed:** When F-RISK is injected, does P-VALUES also shift? (Expected: some, since risk and ethics are adjacent domains. SR accounts for this.)
- **Brief-length effect:** Do longer briefs produce better or worse targeting? (V5 briefs vary in length by subject.)
- **Subject-specific targeting:** Does Buffett's investment-focused brief respond more strongly to F-RISK than others?

### What Success Looks Like

**Strong success (publishable):**
- V5-axiom SR > 2.0 for at least 2 of 3 subjects
- V5-prose SR > 1.5 for at least 2 of 3 subjects
- Clear axiom > prose > atomic ordering
- At least one subject shows domain-specific amplification (e.g., Buffett's SR on F-RISK > other subjects' SR on F-RISK)

**Moderate success (useful internally):**
- V5-axiom SR > 1.5
- Axiom > atomic ordering holds
- No regression from E1 CodeBot results

**Failure (requires investigation):**
- All SR < 1.5 across conditions
- No format ordering (atomic = axiom)
- This would suggest human-domain probes don't produce measurable dimension-specific drift, which would be an important negative finding

---

## How Results Feed Back to the Website

### If Approach A shows V5 > V4:
- Update the research page claim from "axiom format produces SR > 2.0" to "V5 compose format produces SR > X.X, a Y% improvement over manually authored briefs"
- This validates the pipeline's compose step as value-adding, not just cosmetic

### If Approach B shows human-domain targeting:
- Add a new section to the research page: "Behavioral Drift in Human Domains"
- Show the SR table by subject and format
- This is the strongest evidence that Base Layer briefs are functional, not decorative
- Can generate new tension visualizations for the website's drift page

### Data for website components:
- `generate_tension_data.py` can be updated to pull from Approach B results
- SR numbers go into the research page metrics
- Per-subject results become case study material

---

## Recommendation

**Run Approach A first.** It takes 30-55 minutes, costs under $1, and answers the narrow question: does V5 format help? This is a prerequisite — if V5 format regresses on the synthetic CodeBot test, there's no point running the more expensive Approach B.

**Then run Approach B.** This is the real test. It answers the question users and researchers care about: does Base Layer's output actually work on human behavioral domains? The E1 coding results are interesting but synthetic. Approach B uses real pipeline output on real subjects with probes that match how people actually use AI assistants.

**Approach B is also the experiment we'd cite.** E1 was proof-of-concept. Approach B, if successful, is the evidence that goes on the research page and in the paper.

---

## Open Questions (For Aarik to Decide)

1. **Which subjects?** Plan says Aarik, Franklin, Buffett. Should we add Marks? Paul Graham (if essays are processed by then)?

2. **Probe tuning:** The human-domain probes above are first drafts. Should we workshop them before running, or iterate based on T0 baseline responses?

3. **Should Approach B also include a no-brief control (C0)?** This would add a 4th condition per subject but gives us the "does any brief help at all?" baseline. E1 didn't test C0.

4. **Local model priority:** Qwen 7B or DeepSeek R1 14B? DeepSeek extracts richer axioms (6-7 vs 1-3) but is 5x slower. Given this is a validation run, Qwen is probably sufficient.

5. **When to run?** Approach A can run today. Approach B needs brief prep + script work. Earliest realistic: tomorrow for execution.
