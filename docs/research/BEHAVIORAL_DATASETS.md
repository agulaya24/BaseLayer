# Behavioral Datasets for Identity System Testing

**Status:** Research complete (Session 56, 2026-02-28)
**Purpose:** Open-source datasets with behavioral ground truth for validating Base Layer's extraction pipeline

## Top 5 Recommendations

### 1. KnowMe-Bench (HIGHEST PRIORITY)
- **URL:** github.com/QuantaAlpha/KnowMeBench
- **Content:** 4.7M tokens of autobiographies (Knausgard, Ferrante, Proust). 2,580 eval queries.
- **Ground truth:** Expert-annotated psychoanalysis tasks (T7). 7 evaluation task types.
- **Fit:** Best match for testing behavioral pattern extraction from long-form text. T7 psychoanalysis ground truth maps directly to axiom/prediction extraction.
- **Limitation:** Fictional/literary characters, not real people.

### 2. CANDOR Corpus (BEST "REAL HUMANS")
- **URL:** guscooney.com/candor-dataset/
- **Content:** 1,656 unscripted conversations, 7M+ words, 850+ hours. Real people aged 19-66.
- **Ground truth:** Post-conversation personality surveys, moment-to-moment behavioral measures.
- **Fit:** Real conversations with personality ground truth. Naturalistic dialogue.
- **Limitation:** Each participant in only 1-2 conversations (not longitudinal).

### 3. Big5-Chat (SCALE TESTING)
- **URL:** arxiv.org/abs/2410.16491
- **Content:** 100K dialogues grounded in real personality expressions from PsychGenerator (850K Facebook posts).
- **Ground truth:** Known Big Five trait profiles per dialogue.
- **Fit:** Extract patterns, verify against known traits. Quantitative at scale.
- **Limitation:** Synthetic dialogues (though grounded in real expressions). Big Five is coarse (5 dimensions vs Base Layer's 47 predicates).

### 4. Essays-Big5 (JOURNAL-LIKE)
- **URL:** huggingface.co/datasets/jingjietan/essays-big5
- **Content:** 2,468 stream-of-consciousness essays from real people.
- **Ground truth:** Big Five personality scores per author.
- **Fit:** Structurally similar to journal entries (Subject B use case). Real people, real scores.
- **Limitation:** Short individual essays, not longitudinal.

### 5. PersonalityEvd (METHODOLOGY)
- **URL:** github.com/Lei-Sun-RUC/PersonalityEvd
- **Content:** 72 speakers, ~2,000 dialogues from Chinese TV series. ~30 dialogues per speaker.
- **Ground truth:** Evidence-grounded personality chains (CoPE framework). Context → state → trait.
- **Fit:** Evidence chains map to Base Layer's extraction-to-axiom pipeline. 72 speakers with longitudinal data.
- **Limitation:** Chinese language, fictional characters.

## Additional Useful Datasets

| Dataset | Content | Ground Truth | Fit |
|---|---|---|---|
| Blog Authorship | 681K posts, 19K bloggers | Demographics only | Scale testing (19K users, 35 posts avg) |
| MediaSum | 463K interview transcripts (NPR/CNN) | Speaker roles | Public figure source — filter for repeat interviewees |
| LoCoMo | 300 turns over 35 sessions | Persona profiles + event graphs | Multi-session extraction testing |
| MSC | Multi-session human chat, 5K convos | PersonaChat personas | Longitudinal pattern extraction |
| PersonaChat | 10,907 dialogues | 5-sentence persona descriptions | Basic factual extraction testing |
| FriendsPersona | 711 Friends TV conversations | Binary Big Five annotations | Well-known characters for qualitative validation |
| Open Psychometrics | Personality descriptions + test scores | Psychometric scores | Short text → personality correlation |

## Key Strategic Insight

**No existing dataset combines:**
- Real human text (not synthetic/fictional)
- Longitudinal data (multiple sessions over time)
- Fine-grained behavioral ground truth (beyond Big Five)
- Identity-level annotations (axioms, predictions, context modes)

**Base Layer's N=3 proof (User A, User B, User C), if documented rigorously, would be the first dataset of its kind.** This is publishable and differentiating.

## Recommended Eval Approach

For the binary yes/no behavioral understanding test:
1. Use KnowMe-Bench T7 psychoanalysis tasks
2. Extract axioms from literary source text via Base Layer pipeline
3. Compare extracted axioms against expert-annotated ground truth
4. Binary score: does extracted pattern match expert annotation?
5. Compare: pipeline-extracted vs base-LLM-only vs raw-text-prompted

This tests extensibility (behavioral understanding, not recall) in a controlled setting with expert ground truth.
