# Cross-Discipline Research — Identity Compression (S100)

## Top Findings That Change How We Think About Base Layer

### 1. We're doing Bayesian Inverse Planning (Cognitive Science)
Stacy et al. (2024) formalize "understanding others" as inverse planning — observing behavior and reconstructing the generative model that produced it. **Our extraction step IS informal inverse planning.** We observe text (actions), extract the beliefs/values/preferences (generative model) that produced it. The 47 predicates are our ontology of mental states. This gives us a formal framework to describe what the pipeline computes.

**Implication:** Frame the pipeline as "approximate Bayesian inference over a person's generative model, compressed into a portable representation." This is publishable framing.

### 2. User Profiles INCREASE Sycophancy (MIT/Penn State, ICLR 2025)
Jain et al. found that condensed user profiles in the model's memory had the **GREATEST impact on sycophancy** — more than conversation history or role framing. However, using the LLM in an "authoritative adviser" role retains independence better than a peer/friend role.

**Implication:** Our FP guards and "never reference the model directly" preamble are **load-bearing architecture, not optional polish.** The "operating guide" framing (adviser role, not persona to embody) is the correct countermeasure. This validates D-081. The preamble wording matters. **Must cite this paper on the research page.**

### 3. PersonaFuse MoE Architecture IS Our Serving Layer (2025)
PersonaFuse uses Mixture-of-Experts to dynamically activate personality traits based on contextual signals. Three stages: (1) infer context cues, (2) identify relevant traits, (3) activate those traits. Achieves +37.9% on EmoBench.

**Implication:** This is the engineering pattern for our serving layer. ANCHORS = always-on expert. Context modes = conditionally activated experts. Predictions = triggered by specific query signatures. The academic community has validated this architecture independently.

### 4. PersonaX: 30-50% of Behavioral Data Captures the Signal (ACL 2025)
PersonaX constructs multiple personas from behavioral data, finds that using only 30-50% of behavioral data achieves 10-50% improvement on tasks. Decoupled profiling from online inference.

**Implication:** Matches our compression saturation finding (20% of facts sufficient for identification). Their "decoupled profiling from inference" IS our extract-then-serve architecture. PersonaX is the closest academic analog to Base Layer.

### 5. Frontier Models Fail at 50% of User Modeling (COLM 2025)
PersonaMem benchmark: GPT-4.1, o4-mini, GPT-4.5, Gemini-2.0 achieve only ~50% accuracy on tracking evolving user preferences across 60 sessions.

**Implication:** **Strongest empirical argument for Base Layer's existence.** Even frontier models fail at half the user modeling task when left to their own devices. You CANNOT rely on the model to build the user model itself — you need an external pipeline.

### 6. Canalizing Kernel = ANCHORS Layer (Computational Biology)
Cell identity is maintained by 3-5 master transcription factors forming cross-regulated loops (CAESAR framework, 2024). The minimal control set (canalizing kernel) is the smallest substructure whose state determines cell fate.

**Implication:** ANCHORS = master regulators. If you perturb an anchor, the entire identity model should shift. If you perturb a CORE mode, effects should be local. **Testable prediction:** V2 pipeline runs where data changes PREDICTIONS but not ANCHORS mean the architecture is working correctly. If ANCHORS change, the entire model should shift. This validates the three-layer hierarchy.

### 7. MDL Theory Predicts Our Architecture (Comp Bio, 2024)
Moskovitz et al. show that dual-process cognition (fast/slow) emerges naturally from Minimum Description Length optimization. MDL-regularized agents develop always-on automatic processes + triggered effortful processes.

**Implication:** ANCHORS (always-on) vs context-activated modes IS dual-process architecture. MDL theory predicts this structure should emerge from compression pressure — and it did empirically in our pipeline design. This wasn't a design choice; it's the information-theoretically optimal structure.

### 8. Information Bottleneck = Our Loss Function (Tishby)
The IB method defines optimal representation as minimal and sufficient for a task. Maximize mutual information between representation and target, constrain mutual information between input and representation.

**Implication:** Our pipeline IS an IB implementation. Input = conversations. Target = predict behavior. Bottleneck = 3-6K token brief. The IB framework gives us a theoretical loss function: mutual information between brief and behavioral prediction, minus penalty for brief length. Twin-2K measures one side of this tradeoff.

### 9. Personality as Activation Vectors (ICLR 2026)
PERSONA framework shows personality traits are extractable, approximately orthogonal directions in LLM activation space. Supports algebraic operations (intensity scaling, composition, suppression). 91% win rate on dynamic personality adaptation. Training-free.

**Implication:** Long-term endpoint: the brief could be COMPILED into an activation vector that steers the model without consuming tokens. Eliminates context-window cost entirely. Speculative but represents the future of identity-conditioned generation. Worth tracking.

### 10. Constrained Decoding for Knowledge Extraction (SIGDIAL 2024)
Grammar-constrained decoding forces the LLM to output only valid relation types during extraction — enforcing ontology at generation time rather than post-hoc.

**Implication:** If we move to local model extraction, constrained decoding could enforce our 47 predicates at generation time. Eliminates extraction drift where models generate predicates outside our spec. Relevant to the structured output discussion.

## How This Changes the Plan

1. **Sycophancy paper validates FP guards as critical.** Don't weaken them in any pipeline change. The "operating guide" framing is architecturally correct.

2. **PersonaFuse validates the serving layer design.** Our spec is aligned with the academic state of the art. Proceed with implementation as planned.

3. **PersonaMem's 50% failure rate** is the strongest pitch for Base Layer. Use in outreach: "Frontier models fail at half of user modeling. We solve the other half."

4. **MDL and IB theory** give us formal frameworks to describe compression quality. Use in the temporal prediction test: measure whether the 2024 brief captures the IB-optimal representation for predicting 2025/2026.

5. **Biology analog** gives us a testable structural prediction: anchor changes should cascade, core changes should be local. Build this into the V2 quality gate.

## Full Source List

See inline citations above. Key papers:
- Jain et al. (ICLR 2025) — CAUSM sycophancy study
- PersonaFuse (2025) — MoE personality activation
- PersonaX (ACL 2025) — recommendation agent user modeling
- PersonaMem (COLM 2025) — dynamic user profiling benchmark
- Moskovitz et al. (PLOS Comp Bio, 2024) — MDL dual process
- Saint-Andre et al. (EMBO 2021) — core regulatory circuits
- CAESAR (Briefings in Bioinformatics, 2024) — canalizing kernel
- Stacy et al. (WIREs, 2024) — Bayesian Theory of Mind
- PERSONA (ICLR 2026) — personality activation vectors
