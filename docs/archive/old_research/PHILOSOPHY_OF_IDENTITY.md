# Philosophical Frameworks for Personal Identity: Systematization and Implementation

**Created:** Session 34 (2026-02-19)
**Purpose:** Philosophical grounding for identity block authoring, temporal processing (Phase 3), and fact classification enrichment
**Philosophers covered:** Frankfurt, Taylor, May, Parfit, Ricoeur, James, Heidegger, Bergson, Mead, Husserl

---

## Implementable Frameworks (Session 34 consensus with user)

### Tier 1: Implement Now (classification enrichment, authoring guidance)

1. **Frankfurt commitment_depth** — `preference` / `caring` / `volitional_necessity` on identity-tier facts
   - Volitional necessities are non-staleable
   - Detectable via: cross-session persistence (5+ sessions, 3+ months), challenge-response patterns, sacrifice language, self-identification language
   - User agreed: aligns closely with existing approach

2. **Taylor strong_evaluation** — boolean flag on facts expressing qualitative distinctions
   - Cross-domain evaluative consistency signals strong evaluation (user agreed)
   - Conversion detection deferred (requires behavioral discontinuity detection — needs temporal windowing)

3. **Ricoeur idem** — used as CORE authoring principle
   - CORE = the unique combination of stable traits, habits, characteristic reactions that makes the person distinguishable
   - Not individual parts but their *collective interaction* (user's phrasing)
   - Ipse (durability through change) deferred — requires cross-context persistence analysis

### Tier 2: Implement in Phase 3 (temporal staleness)

4. **Parfit connectedness** — relative to mean, not absolute decay
   - User direction: no decay curve. Compare topic connectedness to general mean across all topics
   - Frequency change detection vs. baseline (e.g., Python discussion dropping from weekly to zero)
   - Skills vs. identity distinction: skills CAN decay (SQL syntax, FPS coordination), identity facts absorb

5. **Bergson absorption** — guard against false staleness
   - Silence may indicate deepest identity integration
   - Applies to identity/value facts, NOT skill/competence facts (user distinction)
   - Validates existing "silence ≠ irrelevance" principle

### Tier 3: Later (needs design work)

6. **Taylor conversion detection** — behavioral discontinuity in strong evaluations
7. **Ricoeur ipse** — commitments maintained across context changes
8. **Parfit branching** — facts belonging to abandoned identity branches

---

## User Feedback (Session 34)

- Frankfurt volitional necessity: "interesting how closely that aligns with my existing approach"
- Taylor cross-domain consistency: agreed
- Taylor conversion detection: "unclear how you'd implement, would need to detect behavioral discontinuity"
- Parfit connectedness: "reluctant to put a decay curve on it, but connectedness can be detected with comparison to the general mean"
- Bergson absorption vs skill decay: "depends on what is being referenced — skills can decay over time"
- Ricoeur idem: "that's what I'm getting after when I say core — an individual needs to be distinguishable... not just the individual parts but also the collective interaction across those particular stable traits"
- Ricoeur ipse: "speaks to the durability of an individual's character, through change, again implies with time"

---

## Full Research

### 1. Harry Frankfurt — Volitional Necessity and Caring

Frankfurt's central contribution is the hierarchical theory of the will. Identity is constituted not by what you happen to desire but by what you **endorse** at higher orders.

**Caring** is not merely desiring strongly. It involves structural commitment: the person has organized their will around the object of care. **Volitional necessity** occurs when a person *cannot bring themselves* to act against what they care about — not because of external constraint, but because doing so would be experienced as a betrayal of self.

The key distinction: someone under volitional necessity does not experience it as unfreedom. They experience it as **who they are**.

**Temporal behavior:** Frankfurt's framework is surprisingly atemporal — volitional necessity is structural. But caring develops over time, and true volitional necessities are deeply resistant to change. The transition out of a volitional necessity = a fundamental identity shift (falling out of love analogy).

**Detection signals:**

| Signal | Preference | Caring | Volitional Necessity |
|--------|-----------|--------|---------------------|
| Frequency | Some contexts | Recurs across many | Gravitational — present even in unrelated conversations |
| Challenge response | Easily revised | Defended with reasons | Defended with existential weight |
| Sacrifice language | None | Willing to trade off | Cannot trade away |
| Temporal persistence | Session to session | Stable across months | Stable across years, survives life changes |
| Self-identification | "I happen to like X" | "X matters to me" | "I am someone who X" |

**Sources:** Frankfurt, H. (1988). *The Importance of What We Care About*. Cambridge University Press. Frankfurt, H. (1999). *Necessity, Volition, and Love*. Cambridge University Press.

---

### 2. Charles Taylor — Strong Evaluations and Moral Sources

**Strong evaluations** are evaluations where the goods involved are not commensurable with mere desires. A person making a strong evaluation sees X as *qualitatively higher*, not just preferred.

**Moral sources** give weight to strong evaluations. **Frameworks** are the background structures that define what counts as a good life. Identity *requires* a framework: "To know who I am is a species of knowing where I stand."

**Temporal behavior:** Strong evaluations change through **conversion** or **epiphany**, not gradual drift. Rare and dramatic. A strong evaluation stable for 2+ years = very high confidence.

**Detection:** Qualitative distinction language ("shallow," "genuine," "beneath me"), contrastive structure ("I could do X, but that would be..."), framework-revealing statements, cross-domain evaluative consistency.

**Sources:** Taylor, C. (1989). *Sources of the Self*. Harvard University Press. Taylor, C. (1985). *Human Agency and Language*. Cambridge University Press.

---

### 3. Rollo May — Existential Psychology and Intentionality

Identity is not attributes but the raw "I am" experience. **Intentionality** = the structure that gives meaning to experience, the directedness of consciousness toward the world.

**Normal anxiety** is identity-constitutive — signals engagement with freedom. Being is always **becoming** — identity is a process, not a product.

**Temporal behavior:** The past conditions but does not determine. Identity is partly constituted by what you're oriented *toward* (future). A fact is stale not when it's old but when intentional orientation has shifted.

**Sources:** May, R. (1983). *The Discovery of Being*. May, R. (1969). *Love and Will*. May, R. (1950). *The Meaning of Anxiety*.

---

### 4. Derek Parfit — Psychological Continuity and Connectedness

**Psychological connectedness** = direct links between time-slices (memories, beliefs, desires, intentions, character traits, projects). Comes in degrees, decays over time.

**Psychological continuity** = overlapping chains of strong connectedness. Even without direct links between distant time-slices, continuity holds via intermediate connections.

**Relation R** (connectedness + continuity with right cause) is what matters in survival. "Personal identity is not what matters. What matters is Relation R."

**Staleness framework:** A fact is stale when connectedness has decayed below threshold AND it's not part of a continuity chain. A fact that is old but chained is NOT stale.

**Connectedness scoring factors:** Recency (baseline decay), reinforcement (restatement), active reference, continuity chain membership, contradiction by later facts, topic abandonment.

**Sources:** Parfit, D. (1984). *Reasons and Persons*. Oxford University Press.

---

### 5. Paul Ricoeur — Narrative Identity, Idem vs. Ipse

**Idem (sameness):** Lasting dispositions by which a person is recognized. Character, habits, acquired identifications. What would be true 5 years ago.

**Ipse (selfhood):** Self-constancy through change. Keeping one's word, maintaining commitments even when changed. Makes you *yourself* even when you've changed.

**Narrative identity** mediates between idem and ipse. **Emplotment** transforms temporal succession into meaningful sequence ("one thing after another" → "one thing because of another").

**Three-fold mimesis maps to pipeline:**
- Mimesis-1 (Prefiguration) = fact extraction (steps 1-8)
- Mimesis-2 (Configuration) = clustering + identity block authoring (steps 9-10)
- Mimesis-3 (Refiguration) = brief injection + AI response (steps 11-12)

**Staleness:** A fact is stale when it no longer fits the current emplotment. Old narratively-central facts > recent narratively-peripheral facts.

**Sources:** Ricoeur, P. (1992). *Oneself as Another*. Ricoeur, P. (1984). *Time and Narrative*.

---

### 6. Additional Philosophers

**William James** — Identity = "warmth" of recognition. Facts you'd react to with ownership ("Yes, that's me") vs. distance.

**Martin Heidegger** — Three temporal ecstases: Thrownness (past givens), Projection (future orientation), Fallenness (conformity to "they"). Thrown facts never expire but significance shifts. Projected facts stale when projection abandoned.

**Henri Bergson** — Duration (durée) ≠ clock time. Old facts may be MORE constitutive through absorption. Silence may indicate deepest integration, not irrelevance.

**George Herbert Mead** — "I" (present spontaneous action) vs "Me" (past/social structure). Identity brief that is all "Me" = stereotype. Capturing "I" = alive.

**Edmund Husserl** — Retention (just-past), Primal impression (present), Protention (anticipated future). Brief provides AI with retention and enables protention.

---

### 7. Time: Cross-Framework Convergence

**6/6 major frameworks validate silence ≠ irrelevance.** No philosopher supports pure time-decay staleness.

**Time as identity-constitutive** (time makes you who you are): Bergson, Heidegger, Mead, Ricoeur
**Time as identity-revealing** (time shows who you already were): Frankfurt, Taylor, Parfit
**Hybrid:** May (becoming is both discovery and creation)

**Strongest convergence:** Time is not a backdrop — it is constitutive of identity itself. Duration of persistence is identity-information (Bergson, Frankfurt). Sequence reveals narrative structure (Ricoeur). Continuity chains are more informative than absolute age (Parfit).
