# Development notes

Dated notes on work in progress. This file records what is being changed and why, including
findings that are unflattering to the current implementation. Nothing here describes a released
capability unless it says so.

---

## 2026-08: replacing fixed constants with data-derived parameters

**What this work is.** We are removing magic numbers from the pipeline and replacing them with
parameters the data determines for itself. A threshold should be a stated percentile of a
distribution the corpus actually produces, not a number someone picked because it sounded strict.

**Why it became necessary.** Fixed constants survive contact with small, clean test corpora. They
fail quietly on large ones. This work was forced by running the pipeline on very large, dense
personal text, and by beginning to explore organizational corpora, where the same constants that
looked reasonable at small scale turned out to sit in the wrong part of the distribution entirely.
Nothing errored. The numbers simply stopped meaning what their names implied.

**How we are testing the claim.** By measuring components that had never been measured. Most of what
follows is therefore a defect report on our own code. It is published because a project that reports
only what worked is not one whose measurements anybody should trust, and because each defect below
is an instance of the same underlying pattern: a constant that was never checked against the
distribution it operates in.

**Status: this work sits on an unmerged branch. Nothing described here is in a release.** Installing
from `main` today gets the previously released behavior.

### The distance conversion was wrong, and the documentation taught it

ChromaDB's distance metric is per collection. Our fact collection is created with cosine distance,
where the conversion to similarity is `1 - d`. Collections created without an explicit space use
Chroma's `l2`, which returns a **squared** euclidean distance, so the conversion there is
`1 - d / 2`.

The code used `1 - d^2 / 2` everywhere. That is wrong for both spaces. A nominal 0.85 similarity
gate was therefore firing at a true cosine of roughly 0.45.

Two things about this are worth more than the bug itself:

1. The same wrong conversion existed at three call sites and survived its own fix three times,
   because each fix corrected the site that had been noticed and not the others.
2. `docs/core/ARCHITECTURE.md` stated the wrong formula as fact. A document that states a formula is
   where the next contributor learns to reimplement it. The formula now lives in exactly one
   function, and the architecture doc describes rather than specifies it.

The lesson we took: enumerate every call site before calling a fix done, and do not let a formula
exist in more than one place.

### A guard that could never fire

A faithfulness check compared an authored summary against its supporting facts and flagged the
summary when the best match fell below 0.35.

Measured against the encoder now in use, randomly paired, unrelated facts from the same corpus have
a median cosine similarity around 0.62, and the 0.1st percentile sits near 0.38. The guard also
takes the maximum over a summary's supporting facts, so every one of them would have to fall below
0.35 simultaneously. In the operating range the threshold provides no discrimination: an unrelated
pair of facts clears it almost as reliably as a related one.

An earlier draft of this note said random pairs have a minimum similarity of 0.358 and that the
guard could therefore never fire. That was a sample minimum over 600 pairs. Measured across roughly
eight million within-corpus pairs the true minimum is 0.276, and about 0.015% of pairs fall below
0.35. The guard is effectively unreachable for any on-topic English summary, which is the claim the
evidence supports; "never" is a stronger claim than the data licenses.

Its own source comment already said the value was inferred rather than calibrated. The comment was
correct and nobody acted on it.

The general form of this problem: a threshold expressed as an absolute number is meaningless without
the distribution it sits in. We now check candidate thresholds against a random-pair null before
trusting them, and we have started expressing thresholds as percentiles of a corpus's own
distribution rather than as fixed constants.

### The deduplication step merges facts that are not duplicates

Our extraction pipeline compares each new fact against similar stored facts and asks a model whether
the new one is a duplicate, a refinement, or genuinely new.

We sampled 100 of those decisions, labelled each pair independently with a stronger model in two
passes (the second with the pair order reversed, so that a changed answer indicates position bias
rather than noise), and compared the labels to what the pipeline decided.

The result, stated at the strength the sample supports:

Across the full population of decisions in that band, the pipeline chose to keep a fact as new in
**4.1%** of the cases it examined (610 of 14,771), while the labelled sample puts roughly two thirds
of that band in the keep-as-new category. The gap is large and one-directional.

The per-cell rates from the sample point the same way, but their confidence intervals are wide
enough that the individual percentages should not be quoted as findings. A Fisher exact test on the
split gives p = 0.001, so the direction is solid even though the magnitudes are not pinned down.

The bias has a plausible cause. The prompt asks "Is this a duplicate?", which invites a yes, and the
measured base rate of true duplicates in that band is about one third.

Two limitations of our own method, since they cut against the conclusion. The labelling rubric
instructed the labeller to be strict about calling pairs distinct, which biases the ground truth
toward finding the pipeline too merge-happy. And the measurement harness supplied the adjudicator
with one candidate neighbour where production supplies three, so it was not scored on exactly the
input it sees. Both need fixing before these numbers are used for anything beyond direction.

We also found that the similarity gate itself is doing real work and should be kept: above it,
roughly a third of pairs are genuine restatements; below it, in the sample, none were.

### What the merge behaviour revealed, which mattered more than the bug

The refinement action did not merge text. It wrote the new fact and marked the older one superseded,
which removed it from every downstream query. That is a soft delete, so the rows survive and the
decisions remain auditable, which is the only reason this analysis was possible at all.

Examining those pairs changed our reading of the problem. Roughly 46% were genuine refinements where
the newer fact said everything the older one said and more. Around 18% changed the predicate
entirely, which is not a refinement but a **second interpretation** of the same material.

And a meaningful share were pairs that appear contradictory but are better understood as two true
statements about the same underlying dimension, resolving differently in different contexts. A
person can be inconsistent about the same thing. When our pipeline saw such a pair, it deleted one
half and kept the other, which destroys the finding: the pair is what identifies the dimension.

The conclusion we drew is that the action was detecting something real, two facts bearing on the
same construct, and had only destructive ways to record it. So we are not removing it. We are
renaming it to describe what it detects, recording a typed relation between the two facts, and
keeping both facts active. Disagreement between facts becomes an edge in the data rather than an
argument to be settled at write time.

This also gave us an answer to a design question that had been open for a while: how to preserve
disagreement without introducing a second component whose job is to argue. A typed edge between two
facts needs no such component.

### The test suite was green throughout

769 tests, all passing, for the entire period in which the above was true. (It was 756 before this
block of work added tests; the count is not the point.)

The suite verifies that data moves in the shapes the test author expected under inputs the test
author invented. No test loads a real embedding model or a real vector store. The test for the
faithfulness guard uses mocked three-dimensional vectors at cosine ~1.0 and ~0.0, so any threshold
between roughly 0.05 and 0.9 passes it identically. The test proves that a comparison operator
works. It cannot see that the threshold sits below the noise floor.

A mechanical census found that 29 of 107 module-level constants in the configuration are never
referenced anywhere in the source. One of them is referenced only by a test that asserts it equals
its own literal value, which is how a constant can be dead and appear live to coverage tooling at
the same time.

We are restructuring the harness into three tiers, split by determinism rather than by cost:

1. Fast hermetic unit tests, which is what exists today, keeping its current job.
2. Tests that require a real pinned encoder and a real ephemeral vector store. These cost no API
   money and take a minute or two. They are required whenever a change touches a threshold, the
   extraction path, the verifier, or the encoder pin. They break when the encoder changes, which is
   the point: an encoder change invalidates every threshold calibrated against the old one.
3. Gold-labelled measurements that cost real money and are not deterministic. These stay out of the
   test suite, because a test that silently skips without an API key reads as coverage. They are
   scripts with committed result artifacts, plus a cheap test in tier one that fails when the
   measured component changes and the measurement has not been re-run.

### What is not fixed

The renaming and typed relations are designed and not implemented. The faithfulness guard is
diagnosed and not recalibrated. The verifier still computes a contradiction score and does not use
it, so a claim its own evidence contradicts and a claim with no evidence at all currently return the
same verdict. Facts that were superseded by the merge behaviour have been triaged but not restored.

We will update this note as those land.
