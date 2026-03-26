# Figure Data Preparation Guide

Step-by-step guide for preparing each historical figure's data through the Base Layer pipeline.

## Prerequisites

- Base Layer installed (`pip install baselayer` or dev clone)
- `ANTHROPIC_API_KEY` set in environment
- ~$3-5 per figure in API costs
- ~1 hour per figure (mostly pipeline runtime)

## Figure 1: Benjamin Franklin

### Source Text
- **Title:** The Autobiography of Benjamin Franklin
- **Gutenberg:** https://www.gutenberg.org/ebooks/148
- **Format:** Plain text UTF-8
- **Length:** ~170,000 words (covers 1706–1757, written 1771–1790)
- **Download:** https://www.gutenberg.org/cache/epub/148/pg148.txt

### Why Franklin
- Rich first-person narrative with strong personality
- Mix of personal, professional, philosophical, and political content
- Well-known figure — users can validate the identity model against their own knowledge
- Self-reflective writing style (lists his 13 virtues, catalogs his failures)
- The autobiography is literally a self-model — perfect test case

### Identity Layer Expectations
- **ANCHORS:** Self-improvement as organizing principle, industry/frugality, pragmatic morality, civic contribution
- **CORE:** Communication style (persuasion over confrontation), context modes (printer/diplomat/scientist/civic), narrative orientation (didactic, example-driven)
- **PREDICTIONS:** Vanity management (admitted weakness), conflict avoidance → indirect persuasion, overcommitment to projects, pragmatic compromise over principled stand

### Pipeline Commands

```bash
# 1. Set up isolated data directory
mkdir -p demo/data/figures/franklin/source
cd demo/data/figures/franklin

# 2. Download source text
curl -o source/autobiography.txt https://www.gutenberg.org/cache/epub/148/pg148.txt

# 3. Clean the text (strip Gutenberg header/footer)
# Manual step: Open autobiography.txt, remove everything before
# "AUTOBIOGRAPHY OF BENJAMIN FRANKLIN" and after "*** END OF THE PROJECT GUTENBERG EBOOK ***"
# Save as source/autobiography_clean.txt

# 4. Initialize Base Layer for this figure
export MEMORY_SYSTEM_ROOT=$(pwd)
baselayer init

# 5. Import the autobiography
baselayer import --text source/autobiography_clean.txt

# 6. Extract facts (~$1-2 via Haiku)
baselayer extract

# 7. Checkpoint: Review extraction quality
baselayer checkpoint extraction
# Expect: 200-400 facts from a single long text
# Check: fact diversity (not all biography), predicate distribution

# 8. Embed facts
baselayer embed

# 9. Score facts
baselayer score

# 10. Checkpoint: Review scoring
baselayer checkpoint scoring

# 11. Classify fact types + commitment depths
baselayer classify

# 12. Tier classification
baselayer tier

# 13. Checkpoint: Review classification
baselayer checkpoint classification

# 14. Author identity layers
baselayer author --agent-pipeline

# 15. Review generated layers
cat data/identity_layers/anchors_v1.md
cat data/identity_layers/core_v1.md
cat data/identity_layers/predictions_v1.md
```

### Review Checklist
- [ ] Anchors reflect Franklin's stated virtues and operating principles
- [ ] Core captures his communication style (indirect persuasion, Socratic method)
- [ ] Predictions include his admitted weaknesses (vanity, pride)
- [ ] No anachronisms (modern concepts attributed to Franklin)
- [ ] Layers read as a behavioral model, not a biography summary
- [ ] Total token count under 6,000 tokens

### Potential Issues
- **Single-source bias:** One text = one perspective. Franklin's autobiography is notoriously self-serving. The pipeline may over-index on his self-presentation vs. historical reality. This is actually fine for the demo — it shows the pipeline extracts the voice from the text, not objective truth.
- **Temporal gaps:** The autobiography only covers to 1757. No content about the Revolution, Constitution, French embassy. The identity model will reflect young/middle Franklin, not elder statesman.
- **Text chunking:** At ~170K words, this is much longer than a typical conversation. The import treats the whole file as one "conversation." Extraction may hit per-conversation fact limits. May need to split into chapters.

### Splitting Strategy (if needed)
If `MAX_FACTS_PER_CONVERSATION = 20` is too restrictive for a 170K-word text:
1. Split autobiography into chapters (natural section breaks exist)
2. Import each chapter as a separate text file
3. Run extraction on all chapters
4. This gives the pipeline more granularity

```bash
# Split approach
mkdir -p source/chapters/
# Manually split into ~10-15 chapter files
# OR use a script to split on "PART ONE", "PART TWO", chapter headers
baselayer import --text source/chapters/
```

---

## Figure 2: Frederick Douglass

### Source Text
- **Title:** Narrative of the Life of Frederick Douglass, an American Slave
- **Gutenberg:** https://www.gutenberg.org/ebooks/23
- **Format:** Plain text UTF-8
- **Length:** ~40,000 words (covers 1818–1841, published 1845)
- **Download:** https://www.gutenberg.org/cache/epub/23/pg23.txt

### Why Douglass
- Intensely personal, deeply reflective first-person narrative
- Dramatically different life context from Franklin — tests pipeline generalization
- Strong moral convictions, complex emotional landscape
- Rhetorical sophistication that should produce distinct communication style patterns
- Well-known enough for users to validate

### Identity Layer Expectations
- **ANCHORS:** Freedom as non-negotiable, education as liberation, moral clarity about injustice, self-determination
- **CORE:** Communication style (rhetorical power, moral authority, direct confrontation of injustice), context modes (enslaved person/fugitive/orator/writer)
- **PREDICTIONS:** Tension between rage and strategic restraint, hypervigilance, trust calibration (hard-won, context-dependent), resilience patterns

### Pipeline Commands
Same as Franklin, substituting:
```bash
mkdir -p demo/data/figures/douglass/source
cd demo/data/figures/douglass
curl -o source/narrative.txt https://www.gutenberg.org/cache/epub/23/pg23.txt
# Clean Gutenberg header/footer
export MEMORY_SYSTEM_ROOT=$(pwd)
baselayer init
baselayer import --text source/narrative_clean.txt
# ... same pipeline steps ...
```

### Review Checklist
- [ ] Anchors reflect Douglass's core convictions (freedom, education, moral truth)
- [ ] Core captures his rhetorical style (not just content but HOW he argues)
- [ ] Predictions include the tensions in his narrative (rage vs. restraint, trust dynamics)
- [ ] No sanitization — the violence and trauma of his experience should be reflected in behavioral patterns
- [ ] Layers feel like Douglass, not a generic "historical Black American"
- [ ] Distinct from Franklin in both content AND structure

### Potential Issues
- **Shorter text:** At ~40K words, this produces fewer facts than Franklin. May result in thinner layers. This is actually a good test — can the pipeline produce quality layers from less data?
- **Sensitivity:** Douglass's narrative contains graphic descriptions of slavery. The pipeline should extract behavioral patterns, not catalog atrocities. Review layers carefully for appropriate handling.
- **Third-person sections:** The narrative includes Douglass writing about others' experiences. Pipeline should primarily extract facts about Douglass himself.

---

## Figure 3: Marcus Aurelius (Optional)

### Source Text
- **Title:** Meditations
- **Gutenberg:** https://www.gutenberg.org/ebooks/2680
- **Format:** Plain text UTF-8
- **Length:** ~45,000 words (written ~170-180 AD)
- **Translation:** George Long (1862) — public domain
- **Download:** https://www.gutenberg.org/cache/epub/2680/pg2680.txt

### Why Aurelius
- Completely different genre (philosophical journal, not autobiography)
- Tests whether pipeline can extract identity from non-narrative text
- Private reflections never intended for publication — highest-fidelity self-model
- Stoic philosophy provides natural ANCHORS content
- Very different personality type from Franklin and Douglass

### Identity Layer Expectations
- **ANCHORS:** Stoic principles (duty, acceptance, rationality), mortality awareness, cosmic perspective
- **CORE:** Communication style (self-directed imperatives, terse, meditative), context modes (emperor/philosopher/military leader/grieving father)
- **PREDICTIONS:** Tension between duty and weariness, recurring self-correction patterns, frustration with court politics masked by philosophical framing

### Potential Issues
- **Not first-person narrative:** Meditations is a philosophical journal, not storytelling. Pipeline may struggle with fact extraction from aphoristic text.
- **Translation artifacts:** 1862 translation style may confuse extraction. Modern translations (Gregory Hays) are not public domain.
- **Low biographical content:** Aurelius rarely mentions specific events. Layers may be heavy on ANCHORS (values) and light on CORE (context) and PREDICTIONS (behavior).

---

## Cost Summary

| Figure | Source Length | Est. Facts | Est. API Cost | Est. Time |
|---|---|---|---|---|
| Franklin | ~170K words | 200-400 | ~$3-5 | ~1 hour |
| Douglass | ~40K words | 100-200 | ~$1-3 | ~30 min |
| Aurelius | ~45K words | 80-150 | ~$1-3 | ~30 min |
| **Total** | | **380-750** | **~$5-11** | **~2 hours** |

## Quality Validation

After running the pipeline for each figure, validate with these test questions:

### Franklin Test Questions
1. "What do you think about getting rich?" (should trigger frugality + industry, not just "work hard")
2. "How do you deal with people who disagree with you?" (should trigger Socratic/indirect persuasion, not confrontation)
3. "What's your biggest flaw?" (should trigger vanity/pride admission — Franklin explicitly identified this)

### Douglass Test Questions
1. "What does freedom mean to you?" (should be visceral and specific, not abstract)
2. "How do you handle people who tell you to be patient?" (should trigger strategic restraint tension)
3. "What role has reading played in your life?" (should trigger education-as-liberation framework)

### Aurelius Test Questions
1. "I'm overwhelmed with responsibilities." (should trigger duty + acceptance, not "take a break")
2. "People at work are terrible." (should trigger cosmic perspective + self-directed correction)
3. "I'm afraid of dying." (should trigger mortality meditation, not reassurance)

Run each question through both vanilla and BL panels. The delta should be immediately visible.

## Post-Pipeline Cleanup

After pipeline run and review, ensure the figure directory is clean:

```
demo/data/figures/{slug}/
├── data/
│   ├── database/memory.db          # Keep
│   ├── vectors/                    # Keep (for potential full-brief upgrade)
│   └── identity_layers/
│       ├── anchors_v1.md           # Keep — served to frontend
│       ├── core_v1.md              # Keep
│       └── predictions_v1.md       # Keep
├── source/
│   └── *.txt                       # Keep — provenance
└── metadata.json                   # Create manually with figure info
```

Delete any pipeline artifacts, progress files, or temp data that aren't needed for serving.
