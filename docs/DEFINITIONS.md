# Definitions

Base Layer uses a set of terms in fixed senses, and this file is where they are fixed. Each has an
id so it can be referred to ("D05") and challenged. Where a model applies a definition, the
instruction it is given is quoted word for word in italics, taken from the code on this version,
with the file named, so you can see what the label means to the model that applies it. A quote
shortened with "..." leaves out text between the quoted parts. If the code and this file
disagree, the code is what runs.

A label in an output means what it means here, not what the word suggests elsewhere.

## The specification

**D01 Specification.** A written account of how one person reasons, communicates and tends to
respond, made of claims (D02) in three layers (D03). It is a reading of the person's own text made
by models. It is not a statement of fact about the person until the person confirms it (D40).

**D02 Claim.** One statement in a specification, with an id (A1, C14, P26), a short name, a
statement, an `Active when` line (D04), the ids of the facts it rests on (D07) and a contested flag
(D05). Claim ids are unique within one specification only: two specifications can both have a C3,
and they are different claims. Verification names a claim as `<label>:<claim id>` for that reason.

**D03 Layer.** A specification has three layers, each written in its own model call, blind to the
other two. The author's instruction for each (`distillation/author_from_package.py`):
- **ANCHORS:** *"AXIOMS this person reasons FROM, not about: pre-set certainties that narrow what
  they will consider before situation-specific information arrives. Name them A1, A2, ...
  Load-bearing means: it constrains what they treat as settled."*
- **CORE:** *"HOW this person communicates, what context they carry, and what an AI must know to
  interpret them. Biography counts here. Name them C1, C2, ... Load-bearing means: it changes how
  you would read something they said."*
- **PREDICTIONS:** *"HOW this person responds to SPECIFIC SITUATIONS. Name them P1, P2, ... Each
  `active_when` must name a concrete, recognisable circumstance. Load-bearing means: it lets you
  anticipate a concrete behaviour in a nameable circumstance."*

The static path (`baselayer author`) writes the same three layers from its own prompts in
`author_layers.py`; they are not quoted here.

**D04 Active when.** The situation in which a claim applies, written by the author with the claim.
The schema's description of the field: *"When this applies. May be empty."* For PREDICTIONS the
layer instruction (D03) asks for a concrete, recognisable circumstance. A claim is meant to be used
in that situation, not everywhere. The trigger index (D35) is built from these lines.

**D05 CONTESTED.** A flag the author sets on a claim. Its instruction: *"Mark contested: true where
the evidence disagrees with itself. Carry the tension; do not resolve it."* Both sides stay in the
claim. The flag records that the evidence conflicts; it does not say which side is right.

**D06 Brief.** An optional prose summary composed from the three layers (`--compose`, or
`baselayer compose` on the static path). Off by default. It is not the specification and adds no
evidence of its own.

## Facts and evidence

**D07 Fact.** A short subject, predicate, object statement about the person, extracted by a model
(Claude Haiku 5.5 on the cited build, Claude Haiku 4.5 on `baselayer run`) from one piece of their text, with an id (`F-` and the first 8 characters of
its database id). The model writes the person as "user" or "this person": "user values X" means
the person the specification describes values X.

**D08 Predicate.** The verb of a fact. The extraction prompt offers a list of 46
(`CONSTRAINED_PREDICATES` in `config.py`, 45 plus `unknown`). A verb the model returns that no
alias maps onto the list is kept as written, not rejected, so the list is a prompt list, not an
enforced vocabulary.

**D09 Own words.** Text the person typed or dictated. At import each turn gets a voice class
(`voice.py`); only `own_typed` and `own_dictated` are citable. `assistant`, `other_person`,
`pasted`, `compaction_summary`, `tool_result`, `harness_prompt` and `queued_command` are context
only: the extractor sees them, and a fact cannot rest on them.

**D10 Evidence span.** An exact excerpt of one own-voice turn that a fact is drawn from, stored with
the fact (`evidence_spans`, with `source_turn_id`). Only facts extracted under the turn contract
have spans.

**D11 The gate.** A check in code, not in the prompt, that stores a turn-contract fact only if it
has at least one span, every span names an own-voice turn in its chunk, every span is found in
that turn's text (after whitespace and quote-mark normalisation), and every span is within the
length bounds. Rejections are counted by reason: `no_grounding`, `no_turn`, `not_own_voice`,
`span_not_found`, `span_length`, `self_object`. The gate proves a fact rests on the person's own
words. It does not prove the fact reads them correctly; that is a judgement (D27).

**D12 Referent.** The person a corpus describes, given as `subject_names` in the import config.
Turn-contract extraction maps each listed name, and the generic forms the extractor uses, to the
subject `user`, and refuses to start when the list is empty.

**D13 Grounding.** Whether a turn-contract fact rests on the person's prose (`prose`) or only on
record rows such as a log or table (`record_only`). Distillation leaves record-only facts out by
default and counts them.

**D14 Stamp.** The record, written on an artifact, of what produced it: model, prompt hash, input
hash, git commit and code path. The fields per artifact are listed in
[PIPELINE.md](PIPELINE.md#13-stamps). A stamp answers "what made this"; a citation (D15) answers
"which facts support this claim".

**D15 Citation.** A fact id attached to a claim. A citation that resolves (D24) proves the fact
exists and was in the author's input. It does not prove the fact caused the claim.

## Distillation

**D16 Leaf.** One model call over one chunk of facts (`distill --max-facts` facts per chunk). The
leaf is told it has a complete chunk and that a later step reads its output instead of the facts.
Each leaf is directed at one layer. The directive it receives (`distillation/distill.py`) differs
from the author's (D03); for ANCHORS it is *"AXIOMS this person reasons FROM, not about: pre-set
certainties that narrow what they will consider before situation-specific information arrives.
Load-bearing means: it constrains what they treat as settled."* The `blind` control receives
*"No layer directive. Load-bearing means: it bears on how this person operates, generally. THIS
ARM IS THE CONTROL and its dispositions are not comparable to a directed arm's."*

**D17 Theme.** In the leaf instruction: *"THEMES: what recurs. Synthesise. Cite the ids you drew
on."*

**D18 Singularity.** In the leaf instruction: *"SINGULARITIES: facts that no theme statement
covers, and that would change how someone models this person if known. Carry the fact text
VERBATIM and unchanged. A fact can be decisive and appear exactly once; frequency is not
significance."* A singularity whose id was not in the chunk is dropped whole.

**D19 Contradiction.** In the leaf instruction: *"CONTRADICTIONS: where the chunk disagrees with
itself, especially stated belief against reported action. DO NOT RESOLVE THESE. Carry the tension
with both sides' ids."*

**D20 Disposition.** In the leaf instruction: *"DISPOSITIONS: every fact id in the chunk gets
exactly one verdict. theme (folded into a theme), singular (carried in the singularity lane), or
not_load_bearing (read and judged not to bear on how this person operates)."* Not load-bearing is
relative to the layer: a fact can be not load-bearing for one layer and the substance of another.

**D21 Package.** The input to the author for one layer, built by `assemble` with no model call:
the collected themes, singularities and contradictions, with their fact ids. A singularity seen in
at least `--min-runs` trees is marked verified; with one tree the label is withheld.

**D22 Shard.** Part of a package too large for one author request (`--shard-token-budget`). Shards
cover disjoint leaves, and each is authored in its own call, so a layer built from shards can
state one pattern once per shard.

**D23 Quote gate.** A check in code, no model (`--quote-gate` on the author module): a quoted
phrase in a claim must appear, at word boundaries, in an own-voice span of a fact the claim cites.
A failing quote of three or more words found in at most five other supplied facts has those facts
added to the claim's citations (`gate_added_citations`); any other failing quote loses its quote
marks.

## Verification

`baselayer verify-spec` writes these definitions into every report before any rater output exists
(`verification/definitions.py`, version `verify-definitions/2`). Changing one means changing the
version.

**D24 Resolution.** From `definitions.py`: *"a cited id resolves when exactly one memory_facts row
has that id or 8-hex prefix, superseded_by is null, and the id is not original_fact_id of a
user_corrections row of type DELETE, refuted or REATTRIBUTE."*

**D25 Re-gate.** Verification runs the gate (D11) again on every span of every cited turn-contract
fact, against the stored turn. From `definitions.py`: *"The fact must also pass the turn-contract
gate again: the turn exists, its voice_class is own_typed or own_dictated, and each span in
evidence_spans is a normalised substring of its turn's text."* Legacy facts, which have no spans,
are checked only as far as the conversation record allows.

**D26 Support label.** One label per cited fact, from a model that sees the claim and its cited
facts (`verification/model_checks.py`):
- *"supports: the fact directly evidences the claim as written"*
- *"partial: evidences part of the claim, or a weaker/narrower version of it"*
- *"unrelated: does not bear on the claim"*
- *"contradicts: evidences the opposite of the claim"*

From `definitions.py`: *"(supports + 0.5 * partial) / judged facts; unrelated and contradicts count
0."* A claim is reported weak when that ratio is below 0.5.

**D27 Fidelity label.** Turn-contract facts only: whether the fact is a faithful reading of its
cited turn, read in context. The model is told *"The quote is known to be the subject's words; the
question is whether the FACT is a faithful reading of them."* Labels:
- *"own_words: the fact's content is in the subject's own words in the cited turn, read with its
  context"*
- *"fair_description: the fact describes what the subject did or said, and their own turn shows it
  (the assistant's account of what they did does not count)"*
- *"overreach: their turn supports only a narrower or weaker statement than the fact makes"*
- *"misread: the fact misstates the turn (wrong polarity, a hypothetical recorded as fact, wrong
  subject, garbled)"*
- *"not_his: the content originates in context the subject did not write (assistant, pasted,
  another person)"*

Reported under two standards from one set of labels: strict (`own_words` only) and lenient
(`own_words` plus `fair_description`).

**D28 Voice label.** For legacy facts whose origin the conversation record cannot settle, a model
decides who originated the content: `own_words`, `fair_description`, `own_document`, `pasted`,
`assistant` or `unknown`. Among its instructions: *"assistant: the content originates in the
assistant's reply (its advice, maxims, characterisation of the subject), even if the subject then
agreed"*. A claim is reported `not_his` when under half of its located facts are the person's own,
with at least three located.

**D29 Cross-claim relation.** For candidate pairs of claims in one specification:
- *"contradicts: they cannot both hold of the same person in the same situation"*
- *"tensions: they pull in opposite directions but can both hold, because a condition separates
  them (different situations, domains, time, or stated-vs-enacted)"*
- *"duplicate: they make substantially the same claim (one could be merged into the other with no
  loss)"*
- *"compatible: neither of the above"*

The model is told: *"Do not judge whether either claim is true of the person."*

**D30 Adjudication.** Each apparent contradiction, read as a pair of facts in their source
context. The model is told *"Evidence counts only in the person's OWN words."* Verdicts:
- *"real_contradiction: in the person's own words, the two genuinely conflict with no separating
  condition"*
- *"context_split: both are true of the person under different conditions; name the condition"*
- *"misattribution: at least one fact is not the person's"*
- *"extraction_error: at least one fact misstates its source"*
- *"no_conflict: read in context, the two facts do not conflict"*

**D31 Out of scope for verification.** From `definitions.py`: *"whether a claim is true of the
person is out of scope. Verification checks evidence, voice and structure."*

**D32 Blind rater.** A rater run is recorded blind only when a context probe of the actual child
process ran, at least one canary string was given (`--probe-canary`), and none of them appeared in
its answer. Removing API credentials,
running outside the project tree and passing `--safe-mode` do not by themselves make a rater blind.

## Consolidation

`baselayer consolidate` calls no model. The model-judged inputs it can take (duplicate verdicts,
a trigger grouping, a category assignment) are built separately, by
`python -m baselayer.consolidation.build`.

**D33 Always-on.** A claim served in full on every message, chosen by rule, not by a model. The
default rule (`literal`) selects a claim whose `Active when` opens with one of a fixed list of
phrases for a condition that applies to essentially every exchange, such as "Always" or "Any
message" (`consolidation/always_on.py`). `fire_rate` and `explicit` are the alternatives.

**D34 Clause.** An exact substring of a claim's `Active when`. `*` means the whole condition.

**D35 Trigger.** One situation line in the served text, worded verbatim from one member claim's
clause, ending with the ids of every claim it pulls. A claim can sit under several triggers. With
no grouping input, each distinct whole condition is one trigger.

**D36 Category.** A heading over triggers. A trigger's category is the majority category of its
member claims. A category is flagged thin when it pulls few claims or rests on few facts.

**D37 Duplicate group.** Claims recorded as stating one idea, as a mapping only; no claim text is
rewritten. By default groups come from shared cited facts (Jaccard at least 0.5). With judge
verdicts, two claims join a group when the judge labels them SAME in both presentation orders. The
judge's instruction (`consolidation/overlap.py`):
- *"SAME: X and Y express one idea. One mostly restates the other (different wording, examples or
  emphasis is fine). Deleting either would lose little."*
- *"FACET: X and Y rest on the same underlying disposition or tendency, but each carries
  substantial content the other lacks"*
- *"DISTINCT: different dispositions or ideas, even if they share a topic or words."*

**D38 Consolidation checks.** Fourteen mechanical checks; a check that cannot run fails
(`consolidation/checks.py`):

| id | check |
|---|---|
| K01 | `claims.json` matches the layer JSON re-read now |
| K02 | each layer's `.md`, when present, carries the same served block as its JSON |
| K03 | every clause is an exact substring of its claim's `Active when` |
| K04 | every trigger wording is verbatim text of its source claim's condition, and the source is a member |
| K05 | every claim is reachable: always-on, or pulled by at least one trigger |
| K06 | always-on claims exist and are not hung off any trigger |
| K07 | trigger ids are unique, and no (claim, clause) edge repeats within a trigger |
| K08 | no content-bearing span of a triggered claim's condition is left uncovered by its clauses |
| K09 | every trigger has exactly one category, and the coverage counts recompute |
| K10 | claim text unchanged: every index entry equals the block rendered from the layers |
| K11 | fact ids preserved, per claim and as a union |
| K12 | the served text's hash matches the index; always-on blocks and trigger lines are present; every served id resolves |
| K13 | dedupe is a partition of the claims, with no rewrite recorded |
| K14 | every stage output carries a complete stamp, and the served stamp's hash matches the served text |

## Claim boundary

**D39 Distinguishable is not faithful.** A specification another model can tell apart from other
specifications is distinguishable. That does not show it is a faithful account of the person.

**D40 Member check.** The qualitative-research practice, also called respondent validation, of
asking the person described whether the account is them. Only a member check settles fidelity.
Base Layer has no command for it; corrections the person gives can be checked against a
specification with `verify-spec --corrections` ([CORRECTIONS.md](CORRECTIONS.md)).

## Not defined here

The support filter (a per-fact label of supported, stretch or not supported against the fact's own
quote) and the stretch sort are research scripts outside this repository. Their labels are not
used by any command here and are not defined in this file.
