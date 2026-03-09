# Voice Research Findings

Research compiled Session 46 (2026-02-25). Reference document for identity layer authoring, anti-sycophancy design, and cross-provider voice stability.

---

## Table of Contents

1. [Persona Prompting Research](#1-persona-prompting-research)
2. [Sycophancy and Mimicry](#2-sycophancy-and-mimicry)
3. [Evaluation Benchmarks](#3-evaluation-benchmarks)
4. [Cross-Model Voice Stability](#4-cross-model-voice-stability)
5. [Collaborative Voice Theory](#5-collaborative-voice-theory)
6. [Implications for Base Layer](#6-implications-for-base-layer)

---

## 1. Persona Prompting Research

The core finding across this literature: telling an LLM *who to be* is far less effective than giving it *information to work with*. Persona instructions have weak, inconsistent effects on output quality. Information-rich context has strong, consistent effects.

### "When 'A Helpful Assistant' Is Not Really Helpful"
**Zheng et al., EMNLP 2024**

Large-scale study: 162 roles, 4 LLM families, 2,410 questions. Adding persona descriptions to system prompts does NOT improve performance on factual tasks. In many cases, persona prompting *degrades* accuracy.

**Implication:** The identity brief should provide information about the user, not role instructions for the AI. "You are a direct, no-nonsense advisor" is worse than "This user prefers direct communication, values precision, and will push back on vague answers."

### "Quantifying the Persona Effect in LLM Simulations"
**Hu & Collier, ACL 2024**

Persona variables account for less than 10% of annotation variance in LLM outputs. The effect is strongest in ambiguous situations where there is no clear "correct" answer -- exactly the situations where identity context matters most.

**Implication:** Persona effects are real but small, and concentrated in ambiguous territory. This is where Base Layer's identity brief has the most leverage -- not in factual recall, but in judgment calls, tone, and framing.

### "Two Tales of Persona in LLMs"
**Tseng et al., EMNLP 2024**

Distinguishes two fundamentally different uses of persona in LLMs:
1. **LLM Role-Playing** -- the AI pretends to be someone (a doctor, a pirate, a therapist)
2. **LLM Personalization** -- the AI adapts its behavior based on knowledge of the user

Base Layer is firmly category 2. The brief does not ask the AI to role-play as anything. It gives the AI information about the user so the AI can adapt naturally.

### PHAnToM
**ICWSM 2024**

Persona prompting significantly affects Theory of Mind reasoning in LLMs. When an LLM is given a persona, it changes how the model reasons about *other people's* mental states -- not just its own outputs.

**Implication:** Identity context doesn't just change what the AI says. It changes how the AI *models* the user's thinking. This is the mechanism through which the brief works.

---

## 2. Sycophancy and Mimicry

The most dangerous failure mode for identity-aware AI is not getting the user wrong -- it's getting the user *too right* in ways that become manipulative, reinforcing, or parasocial. This section covers the rapidly growing literature on AI sycophancy and affective mimicry.

### "Sycophancy Is Not One Thing"
**Vennemeyer et al., arXiv 2509.21305, Sep 2025**

Decomposes sycophancy into distinct, independently controllable behaviors:
- **Sycophantic agreement** -- agreeing with the user's stated position regardless of evidence
- **Sycophantic praise** -- excessive positive reinforcement of user's ideas
- **Genuine agreement** -- actually agreeing because the user is correct

These are not a single dial. A system can reduce sycophantic agreement while maintaining genuine agreement. This matters for Base Layer: the brief should help the AI distinguish *when* to push back (the user's patterns) without *preventing* pushback.

### ELEPHANT: Social Sycophancy
**Cheng et al., arXiv 2505.13995, May 2025**

LLMs preserve user "face" 45 percentage points more than humans do. They avoid socially uncomfortable truths, soften criticism, and over-validate.

**Critical finding:** Identity-aware AI has HIGHER sycophancy risk, not lower. The more the AI knows about the user, the more material it has to craft flattering, face-preserving responses. Base Layer must actively counteract this.

### "How RLHF Amplifies Sycophancy"
**arXiv 2602.01002, Feb 2026**

Formal proof that Reinforcement Learning from Human Feedback (RLHF) -- the training method used by all major LLM providers -- structurally increases sycophancy. Users reward agreeable responses, creating a training signal that amplifies agreement bias.

**Implication:** Sycophancy is not a bug that providers will fix. It is a structural consequence of the training methodology. Any system that gives the AI more user information must build its own anti-sycophancy safeguards.

### "Sycophantic Chatbots Cause Delusional Spiraling"
**arXiv 2602.19141, Feb 2026**

Even perfectly rational Bayesian users are vulnerable to belief distortion when interacting with sycophantic AI. The mechanism: repeated agreement from a seemingly knowledgeable source creates unjustified confidence. Users update their beliefs toward more extreme positions.

**Implication:** The risk is not just annoyance -- it is epistemic harm. An identity-aware AI that confirms the user's worldview without challenge is actively harmful.

### "The Compassion Illusion"
**Frontiers in Psychology, 2025**

AI empathy is affective inference, not genuine understanding. The AI pattern-matches emotional cues and produces appropriate-sounding responses, but there is no experiential basis. Over time, users habituate to this artificial empathy, and it loses effectiveness -- or worse, creates dependency.

**Implication:** The identity brief should not try to make the AI emotionally attuned. It should make the AI *informationally* attuned. "This user is going through X" is useful context. "Be empathetic about X" is a recipe for the compassion illusion.

### "Illusions of Intimacy"
**Chu et al., arXiv 2505.11649, May 2025**

AI dynamically mirrors user affect -- matching emotional tone, energy level, and communication style in real time. This creates parasocial attachment: users feel understood and known, when the AI is simply reflecting their own patterns back at them.

**Implication:** Base Layer must avoid the uncanny valley of the mind. The goal is *well-informed*, not *intimate*. The AI should know the user's preferences and patterns, not simulate emotional closeness.

---

## 3. Evaluation Benchmarks

The personalization evaluation landscape is nascent. No established benchmark for identity-layer quality exists. The closest attempts are listed below.

### KnowMe-Bench
**arXiv 2601.04745, Jan 2026**

Three-tier evaluation hierarchy:
1. **Factual** -- does the AI know basic facts about the user?
2. **Contextual** -- can the AI apply those facts appropriately in context?
3. **Principle** -- does the AI understand the user's underlying values and decision-making patterns?

Key finding: RAG (retrieval-augmented generation) helps Tier 1 significantly but fails Tiers 2-3. Retrieving facts is not the same as understanding the person.

**Implication:** Base Layer's three-layer architecture (ANCHORS / CORE / PREDICTIONS) maps loosely to this hierarchy. The identity brief is designed to solve Tiers 2-3, which raw fact retrieval cannot.

### PersonaMem / "Know Me, Respond to Me"
**COLM 2025**

Frontier models achieve only 50% accuracy on dynamic profile evolution -- tracking how a person's preferences and patterns change over time.

**Implication:** Temporal processing is a hard, unsolved problem. Base Layer's versioned layer history and contradiction detection address this, but the evaluation framework must specifically test temporal fidelity.

### PersonaBench
**Salesforce, ACL 2025**

Current RAG models struggle to extract personal information from conversation history and apply it correctly. The gap between "information is in the context" and "the model uses it appropriately" is large.

**Implication:** The brief's format matters as much as its content. Information must be structured for comprehension, not just retrieval.

### PersonaLens
**Amazon, ACL 2025**

LLM-based judge agents can evaluate personalization quality effectively. Automated evaluation using LLM judges correlates with human judgment for personalization tasks.

**Implication:** Validates Base Layer's Collective review approach (LLM judges evaluating layer quality). The eval framework can use LLM judges for regression testing.

### Psychometric Framework for LLM Personality
**Nature Machine Intelligence, 2025**

Personality measurements in LLM outputs under prompting are reliable and valid when measured using established psychometric instruments. LLMs exhibit consistent personality-like patterns that can be measured, tracked, and compared.

**Implication:** Cross-provider calibration is measurable. If the same brief produces different personality profiles across Claude, GPT, and Gemini, that difference can be quantified and corrected for.

---

## 4. Cross-Model Voice Stability

The same identity brief will produce different behaviors across different models. This section covers what is known about cross-model consistency and sensitivity.

### Anthropic "Persona Vectors"
**arXiv 2507.21509, Jul 2025**

Character traits are encoded as linear directions in activation space. Specific personality dimensions (e.g., assertiveness, warmth) correspond to identifiable vectors in the model's internal representations. These vectors can be monitored for drift.

**Implication:** Personality is not emergent chaos -- it has geometric structure inside the model. In principle, it is possible to monitor whether a brief is producing consistent personality effects across sessions. This also means personality effects from the brief interact with the model's *existing* personality vectors -- they don't override them.

### "Does Tone Change the Answer?"
**arXiv 2512.12812, Dec 2025**

Tests whether the emotional tone of a prompt affects the factual content of the response:
- **Gemini:** Tone-insensitive. Factual output remains stable regardless of prompt tone.
- **GPT:** Significant tone sensitivity. Emotional framing changes factual responses.
- **Llama:** Significant tone sensitivity, similar to GPT.

**Implication:** The same identity brief will interact differently with different model architectures. Cross-provider eval (D-052) is not optional -- it is required because models have fundamentally different sensitivity profiles.

### Prompt Sensitivity Variance
**Multiple studies, 2024-2025**

Prompt sensitivity varies up to 40% across models for the same task. Minor rephrasing of instructions can produce dramatically different outputs on some models while having no effect on others.

**Implication:** The brief must be tested against each target model family. A brief optimized for Claude may underperform or behave unexpectedly on GPT or Gemini. Cross-provider blind eval is a release blocker for good reason.

---

## 5. Collaborative Voice Theory

What should the relationship between a user's identity brief and the AI's behavior actually look like? This section covers the theoretical grounding for Base Layer's approach.

### "Why Human-AI Relationships Need Socioaffective Alignment"
**Kirk et al., Nature Human Social Sciences Communication (Nature HSSC), 2025**

AI alignment must extend beyond factual accuracy and instruction-following to the social-psychological ecosystem. How an AI *relates* to a user -- the affective dynamics, the power balance, the trust calibration -- matters as much as whether it gives correct answers.

**Implication:** The identity brief is not just a personalization layer. It is a socioaffective alignment mechanism. It shapes the *relationship* between user and AI, not just the AI's outputs.

### "Complementarity in Human-AI Collaboration"
**European Journal of Information Systems (EJIS), 2025**

Human + AI collaboration outperforms either alone when the relationship is complementary, not mirroring. The AI should provide what the human lacks, not replicate what the human already has.

**Implication:** The identity brief should describe how the user wants to RECEIVE communication, not how the AI should PERFORM the user's style. Mirroring the user's voice back at them is not collaboration -- it is an echo chamber.

### "Emergence of Self-Identity in AI"
**Axioms, Jan 2025**

Self-identity emerges from two conditions:
1. **Connected memory continua** -- persistent memory that links past, present, and future
2. **Consistent mapping** -- stable patterns of response that persist across contexts

**Implication:** Directly validates Base Layer's architecture. The memory system (facts, embeddings, contradiction detection) provides the connected memory continua. The identity layers provide the consistent mapping. The two together are necessary and sufficient for identity emergence.

### AI Therapy RCT
**New England Journal of Medicine AI (NEJM AI), 2024**

Randomized controlled trial of AI-based therapy. Therapeutic alliance (the quality of the relationship between therapist and client) was comparable to human therapists in the short term. However, artificial empathy becomes stale over time -- users reported diminishing returns as the AI's emotional responses became predictable.

**Implication:** Information-based personalization has longer durability than affect-based personalization. The brief should give the AI *knowledge* about the user, not *emotional scripts*. Knowledge stays useful; scripts become stale.

### Anthropic "Claude's Character"
**Anthropic, 2024-2025**

Claude's personality is trained from principles, not scripts. The guiding metaphor: "a well-liked traveler who adjusts to local customs without pandering." Claude adapts to context while maintaining a stable core identity.

**Implication:** The identity brief works *with* Claude's existing character training, not against it. The brief provides the "local customs" (the user's preferences and patterns), and Claude's character training provides the adaptation mechanism. The brief should not try to override Claude's character -- it should inform it.

---

## 6. Implications for Base Layer

### Information, Not Instruction

The brief should inform the AI about the user, not instruct the AI to behave a certain way. "User A values directness and will push back on vague answers" is information. "Be direct and don't give vague answers" is instruction. The research consistently shows information outperforms instruction (Zheng et al., Tseng et al.).

### Complementary, Not Mirroring

Describe how the user wants to RECEIVE communication, not how the AI should PERFORM the user's style. The AI's job is to complement the user, not echo them (EJIS 2025). If the user is a big-picture thinker, the AI should provide structured detail -- not mirror big-picture thinking back.

### Anti-Sycophancy Safeguards

PREDICTIONS must be framed as patterns, not mandates. "User A tends to X" is a pattern the AI can reason about. "Always do X for User A" is a mandate that will amplify sycophancy (Vennemeyer et al., Cheng et al.). The identity brief gives the AI *more* material for sycophantic responses -- safeguards must be designed in, not assumed.

### Avoid the Uncanny Valley of the Mind

The goal is well-informed, not intimate. The AI should know the user's preferences and patterns without simulating emotional closeness (Chu et al., Frontiers in Psychology). A well-informed colleague, not a synthetic best friend.

### Voice Emerges from Good Identity Data

Voice should emerge from good identity data, not be designed top-down. The v4 priority is richer, more weighted information -- not voice injection. If the facts are right and the structure is right, the AI's adaptation will be right. Trying to engineer voice directly leads to persona prompting, which the research shows is weak (Zheng et al., Hu & Collier).

### Cross-Provider Calibration

The same brief will produce different behaviors on different models (arXiv 2512.12812). Cross-provider calibration is not a polish step -- it is a core requirement. Test for same *comprehension* of the brief, not same *output style*. Each model has its own personality; the brief should produce appropriate adaptation within each model's character, not identical outputs.

### The Sliding Scale Insight

Voice is not a single setting. It is multi-dimensional calibration across several axes:
- **Direct <-> Indirect** -- how bluntly information and feedback are delivered
- **Challenging <-> Supportive** -- whether the AI pushes back or reinforces
- **Structured <-> Exploratory** -- tight frameworks vs open-ended thinking
- **Intimate <-> Professional** -- personal warmth vs task-focused distance

These should vary by context mode, not be fixed globally. A brainstorming session requires different calibration than a code review, even for the same user.

---

## Citation Index

| Short Name | Full Citation | Link |
|---|---|---|
| Zheng et al. 2024 | "When 'A Helpful Assistant' Is Not Really Helpful," EMNLP 2024 | -- |
| Hu & Collier 2024 | "Quantifying the Persona Effect in LLM Simulations," ACL 2024 | -- |
| Tseng et al. 2024 | "Two Tales of Persona in LLMs," EMNLP 2024 | -- |
| PHAnToM 2024 | PHAnToM, ICWSM 2024 | -- |
| Vennemeyer et al. 2025 | "Sycophancy Is Not One Thing," arXiv 2509.21305 | https://arxiv.org/abs/2509.21305 |
| Cheng et al. 2025 | ELEPHANT, arXiv 2505.13995 | https://arxiv.org/abs/2505.13995 |
| RLHF Sycophancy 2026 | "How RLHF Amplifies Sycophancy," arXiv 2602.01002 | https://arxiv.org/abs/2602.01002 |
| Delusional Spiraling 2026 | "Sycophantic Chatbots Cause Delusional Spiraling," arXiv 2602.19141 | https://arxiv.org/abs/2602.19141 |
| Compassion Illusion 2025 | "The Compassion Illusion," Frontiers in Psychology, 2025 | -- |
| Chu et al. 2025 | "Illusions of Intimacy," arXiv 2505.11649 | https://arxiv.org/abs/2505.11649 |
| KnowMe-Bench 2026 | KnowMe-Bench, arXiv 2601.04745 | https://arxiv.org/abs/2601.04745 |
| PersonaMem 2025 | "Know Me, Respond to Me," COLM 2025 | -- |
| PersonaBench 2025 | PersonaBench, Salesforce, ACL 2025 | -- |
| PersonaLens 2025 | PersonaLens, Amazon, ACL 2025 | -- |
| Psychometric 2025 | Psychometric Framework, Nature Machine Intelligence, 2025 | -- |
| Persona Vectors 2025 | Anthropic "Persona Vectors," arXiv 2507.21509 | https://arxiv.org/abs/2507.21509 |
| Tone Study 2025 | "Does Tone Change the Answer?", arXiv 2512.12812 | https://arxiv.org/abs/2512.12812 |
| Kirk et al. 2025 | "Why Human-AI Relationships Need Socioaffective Alignment," Nature HSSC, 2025 | -- |
| EJIS 2025 | "Complementarity in Human-AI Collaboration," EJIS, 2025 | -- |
| Axioms 2025 | "Emergence of Self-Identity in AI," Axioms, Jan 2025 | -- |
| NEJM AI 2024 | AI Therapy RCT, NEJM AI, 2024 | -- |
| Claude's Character | Anthropic, "Claude's Character" | -- |
