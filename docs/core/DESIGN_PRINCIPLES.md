# Design principles

**Updated 2026-10-19.** This replaces the version of 2026-03-09.

These are the principles the pipeline and its checks are built on. Each one has a one-line
statement, a short reason, where it shows in the code or docs, and its status in the code on
`main`:

| status | meaning |
|---|---|
| **followed** | the code on `main` does this |
| **partly followed** | true on one path or for some parts, not others; the line says which |
| **not followed** | still held as a goal, but the code does not do it today |
| **designed** | written down, not built in this package |

Principles that the code no longer follows, or that were replaced, are listed at the end under
[Retired or replaced](#retired-or-replaced), with the reason. Decision ids (D-nnn) refer to
[DECISIONS.md](DECISIONS.md). Terms are defined in [../DEFINITIONS.md](../DEFINITIONS.md).

Contents:

1. [Foundations](#1-foundations)
2. [What a specification is](#2-what-a-specification-is)
3. [Evidence and provenance](#3-evidence-and-provenance)
4. [Coverage: nothing lost silently](#4-coverage-nothing-lost-silently)
5. [Checks](#5-checks)
6. [Cost and change](#6-cost-and-change)
7. [Retired or replaced](#retired-or-replaced)

---

## 1. Foundations

### 1.1 Respect for the individual

**Everything starts at the individual. If a feature serves someone else's interest in a person
rather than the person, it does not belong in the system.**

- **Why.** This principle generates the others. Provenance exists because claims about a person
  should be accountable. Corrections exist because the person, not the system, is the authority on
  themselves. Local storage exists because a person's record is theirs.
- **Where.** Local-first data and no accounts (README, "Privacy"); corrections
  ([../CORRECTIONS.md](../CORRECTIONS.md)); a specification is not confirmed: "Models produce the reading. The person it
  describes must confirm that it represents them." (README, "What a specification contains").
- **Status.** Followed.

### 1.2 Individual first; an organisation is composed from people

**A specification describes one person. An organisation's view is built from individual ones; it
is never a substitute for calibrating each person.**

- **Why.** Pooling several people's text through a pipeline built for one person produces a
  blended person, not an organisation. Calibration per person is the claim the whole project rests
  on.
- **Where.** Turn-contract extraction requires the person's names (`subject_names`) and refuses to
  start without them; distillation reads facts about the person only, by default
  (`--include-other-subjects` widens it); `--document-mode` is for documents, not people
  ([../PIPELINE.md](../PIPELINE.md)).
- **Status.** Followed for individuals. Organisation-level composition is not built.

### 1.3 Inherent incompleteness (D-023)

**The system will never have a complete picture of the person. Neither will the person, and
neither will anyone else.**

- **Why.** People are more than what they write: thoughts never shared, experience that predates
  the text, things described differently on another day. There are at least three views of a
  person: who they believe they are, who others believe they are, and what the text shows. All
  three are real and incomplete. Emotional significance in particular cannot be read from how often
  something is mentioned.
- **Where.** README, "Limits and what is not included yet": the corpus is self-report only. Contradictions are carried, not
  resolved (2.5). Claims are readings to be confirmed (1.5).
- **Status.** Followed as a stance. Some earlier practical consequences (a confidence score on
  every fact treated as meaningful, active probing for gaps) are not followed; see
  [Retired or replaced](#retired-or-replaced).

### 1.4 Prediction is the test, not the goal

**A specification exists to change how an AI interprets and responds to a person. Predicting the
person's choices is how its accuracy is tested, not what it is for.**

- **Why.** Memory supplies facts. The specification supplies how this person reads them. A
  specification that predicted well but changed nothing about how an AI argues and decides would
  have missed its purpose. The measured result is stated at the size it was found:
  specifications change how decisions are argued in every situation tested, and change the
  decision itself in some.
- **Where.** README, "Research".
- **Status.** Followed in how the project describes and evaluates itself.

### 1.5 Distinguishable is not faithful; only the person confirms

**Code can show that evidence is real and quoted correctly. It cannot show that a specification is
a faithful account of the person. Only the person can.**

- **Why.** A specification that another model can tell apart from others is distinguishable,
  which says nothing about whether it is right. The gate proves a fact rests on the person's own
  words, not that the fact reads them correctly. A citation that resolves proves the reference is
  real, not that the fact caused the claim.
- **Where.** README, "How to check it", and its table "What is checked by code, and what is a model's reading". `verify-spec`
  reports checks and flags; it does not certify fidelity.
- **Status.** Followed in what the package claims. The tooling to record the person's own
  confirmations is not built.

### 1.6 Data sovereignty (D-002)

**The person's text, facts and specification stay on their machine. Processing uses a model API,
and that is said plainly.**

- **Why.** A system that models how someone thinks should not require handing their life to a
  third party beyond the API calls needed to process it.
- **Where.** README "Privacy"; every ChromaDB client is built with its telemetry off
  (`config.get_chroma_client()`); `estimate` and the spend guard show what a run will cost before
  anything is sent; extraction can run on a local model through Ollama.
- **Status.** Followed.

### 1.7 The person is the highest authority on themselves (D-019, D-021)

**When the person corrects the system, the correction wins. What the system observed is kept as
separate evidence, not discarded.**

- **Why.** No benchmark or similarity score can substitute for the person saying "that is not
  me". But a self-description and a pattern in the evidence can both be true. The system should
  hold both rather than flatter or argue.
- **Where.** `baselayer review` and `forget` hide facts without deleting them; `verify-spec`
  reports citations to facts retired by a correction, and `--corrections` checks each claim
  against the person's recorded corrections so an overturned statement cannot return
  ([../CORRECTIONS.md](../CORRECTIONS.md)).
- **Status.** Partly followed. Hiding and flagging facts works. "Fix once, fixed forever" (a
  correction that blocks the same wrong fact from being extracted again) is only half built: the
  extractor reads `match_patterns`, but no command writes them, and a flag from `review` changes
  nothing downstream.

---

## 2. What a specification is

### 2.1 Three layers, authored separately (D-043)

**ANCHORS (what the person reasons from), CORE (how they communicate and the context to read
them in) and PREDICTIONS (how they tend to respond in a kind of situation) are different kinds of
knowledge, each authored in its own call.**

- **Why.** Written together, they collapse into either a portrait with no predictions or a
  playbook with no context.
- **Where.** Static `author` (three calls); `author-from-package` (one call per layer, or per
  shard, each blind to the other layers).
- **Status.** Followed on both paths.

### 2.2 The audience is the AI (D-041)

**Every claim must change how an AI responds to this person. True but inert description does not
belong.**

- **Why.** A specification written to the person is self-portraiture: accurate and unusable. Two
  constraints hold together: every claim is grounded in evidence (utility without truth is
  manipulation) and every claim is actionable (truth without utility is a portrait).
- **Where.** Authoring prompts in `author_layers.py` and `distillation/author_from_package.py`.
- **Status.** Followed.

### 2.3 Behavioural data, not scripts (D-037, D-041)

**A specification describes how the person works. A directive to the AI is allowed only when it
follows from a pattern stated with it.**

- **Why.** Scripts do not combine: three rules plus a new situation is a rule-following problem.
  Accurate descriptions combine, because the model can weigh several against the situation in
  front of it.
- **Where.** Authoring prompts; the cited build writes claims in the third person and forbids
  naming frameworks (`author_from_package.py`).
- **Status.** Followed. A finer split between beliefs the person holds and directives the person
  gives to an AI working for them, with each claim judged by the change it causes, is designed,
  not in this package.

### 2.4 How someone reasons, not what they reason about (D-089)

**A claim should apply across the person's life, not only to the domain its evidence came from.**

- **Why.** A person who writes mostly about one subject is not defined by that subject. Without a
  guard, the domain with the most text dominates the specification.
- **Where.** The DOMAIN-AGNOSTIC instruction in `author_layers.py` and
  `distillation/author_from_package.py`; `verify-spec` flags a claim whose cited facts all carry
  one practice tag ([VERIFY_SPEC.md](VERIFY_SPEC.md)).
- **Status.** Followed. The practice flag sees only facts that carry a practice tag.

### 2.5 Carry contradictions; do not resolve them (D-036)

**When the evidence pulls both ways, the claim says so and keeps both sides.**

- **Why.** People hold tensions. Picking a winner erases something true. Calling something a contradiction when it is not also
  destroys valid knowledge, so the default is "not a contradiction" unless the reversal is
  unambiguous. Order in time matters: two sides from different periods may be a change, not a
  contradiction.
- **Where.** Distillation keeps a contradictions channel, carried unresolved; the author's schema
  has a `contested` flag and the prompt says "carry the tension; do not resolve it"; `verify-spec`'s
  time-split check flags a contested claim whose sides come from different periods, for a person
  to review, never as an automatic relabel. It runs only when a side assignment is supplied, such
  as a back-check's results through `--backcheck-results`; the back-check itself is not in this
  repository (`verification/checks/time_split.py`).
- **Status.** Followed on the cited build for carrying contradictions. The time-split check needs
  outside input.

### 2.6 A faithful specification includes where the person breaks

**Tensions, failure modes and blind spots are part of an accurate specification, even though they
make the specification easier to exploit.**

- **Why.** A smoothed, consistent caricature scores better on stability tests and is a worse
  representation. Fidelity and vulnerability come together.
- **Where.** Contested claims (2.5); predictions describe responses under pressure as well as
  defaults.
- **Status.** Followed as an authoring stance; not separately measured.

### 2.7 A layer, not a replacement; the conversation comes first (D-094)

**The specification is prior evidence. What the person says now is primary evidence. When they
conflict, trust the person.**

- **Why.** A specification makes memory and retrieval more useful; it does not replace them, and
  it must not override the person in front of the AI.
- **Where.** The MCP server's usage preamble: "The current conversation is primary evidence; the
  specification is prior evidence. Use the specification to interpret, not to override"
  (`mcp_server.py`).
- **Status.** Followed on the served path.

### 2.8 Each claim says when it applies

**A claim carries an `Active when` line, and applies in that situation, not everywhere. Only a few
claims are always on.**

- **Why.** Serving every claim in every exchange dilutes the ones that matter and invites
  over-application. A few claims (how the person communicates in every exchange) genuinely apply
  everywhere; most apply to a kind of situation.
- **Where.** Each claim's `active_when` field on the cited build; `consolidate` builds the always-on
  set and a trigger index whose lines are taken verbatim from `Active when` lines
  ([CONSOLIDATION.md](CONSOLIDATION.md)).
- **Status.** Partly followed. Every cited-build claim has the field, but the schema allows it to
  be empty, and only predictions are told to name a concrete situation. `consolidate` reads only
  cited-build layers, not the static path's files.

### 2.9 Resistance to flattery is structural (D-090)

**A specification can make an AI more eager to please the person it describes. The countermeasures
are built in, not left to advice.**

- **Why.** A condensed profile of the user raises the risk of an AI telling them what they want to
  hear. Personalisation means calibrated friction, not performed agreement.
- **Where.** The served preamble treats the specification as invisible infrastructure: the AI does
  not announce it or perform knowledge of the person (`mcp_server.py`); contested claims (2.5);
  the domain guard (2.4).
- **Status.** Partly followed. Warnings on each prediction about when not to apply it are
  checked only on the legacy compose path (`agent_pipeline.py`); the cited build's claim schema has
  no such field.

---

## 3. Evidence and provenance

### 3.1 Facts rest on the person's own words (D-108)

**A fact may be stored only if its quoted evidence is found, word for word, in a turn the person
typed or spoke.**

- **Why.** In a chat export most of the text is not the person's: assistant replies, pasted
  documents, other people. A fact drawn from those describes someone else.
- **Where.** The turn table records each turn's speaker from the source and a voice class;
  `turn_contract.gate_facts` checks every span ([TURN_CONTRACT.md](TURN_CONTRACT.md)).
- **Status.** Followed under the turn contract (`extract --turn-contract`). Legacy extraction,
  the default for `baselayer run`, stores facts with no quoted evidence. Known gap: a fact about
  another person can be assigned to the person when the person's own text reports that other
  person's action without naming them in the quoted words ([../PROGRESS.md](../PROGRESS.md), "Known open issues").

### 3.2 A gate lives in code, outside every error handler

**A check that decides what is stored runs in code, not in a prompt, and outside any exception
handler that could turn its failure into a normal-looking result.**

- **Why.** A prompt can be ignored. A guard caught by the handler around it is worse than no
  guard, because a refusal then reads as "nothing found".
- **Where.** The turn-contract gate runs before any insert and outside every handler
  (`extract_facts.py`, `turn_contract.py`).
- **Status.** Followed on the turn-contract path.

### 3.3 Auditability is a gate, not a feature

**A claim that cannot be followed back to its evidence is a failure. Citation is enforced by the
output's structure, not requested in the prompt.**

- **Why.** A specification that cited nothing would still read as complete, and could not be
  audited. Asking a model to cite is unreliable; a schema that requires fact ids for every
  claim makes omission impossible.
- **Where.** `author-from-package` emits claims through a strict tool schema; ids not in the
  package are stripped and counted; a claim left with no valid id causes the request to be sent
  again (`distillation/author_from_package.py`).
- **Status.** Followed on the cited build. On the static path citations are asked for but not
  required (README, "How to check it").

### 3.4 Four levels of evidence, and say which one was checked

**A citation can be present, can resolve, can quote the person correctly, and can be the reason
for the claim. The first three can be checked by code. The fourth can be checked only by sampling.**

- **Why.** The schema guarantees citations are present, not that they are accurate. Reporting
  "cited" without saying which level hides the gap.
- **Where.** Presence: the author's schema. Resolution: `verify-spec`. Quotation: the quote gate
  checks every quoted phrase against the own-voice spans of the facts the claim cites, at word
  boundaries, and records citations it added separately from the author's own
  (`distillation/quote_gate.py`). Cause: not checked by the package.
- **Status.** Partly followed: presence and resolution on the cited build; quotation only with the
  opt-in, module-only quote gate.

### 3.5 Stamp every artifact; read the stamp

**Every fact extracted by this version records its model, prompt hash, git commit and code path.
Every cited-build tree, package and layer also records an input hash. A package calls no model, so
it has no model or prompt hash.**

- **Why.** Two codebases can produce files that look identical. A file name or a pointer to the
  latest run can be wrong; the stamp travels with the artifact and says what made it.
- **Where.** [../PIPELINE.md](../PIPELINE.md), section 13; `turn_contract.artifact_stamp`.
- **Status.** Partly followed. Followed for facts extracted by this version and every cited-build
  artifact. Static layers carry frontmatter only (model, time, version, no commit). Older facts
  carry none, and nothing back-fills them.

### 3.6 Authoring never sees its own earlier output (D-040, D-053)

**Each generation is derived from the evidence, never from an earlier version of itself, and never
from the verification findings on an earlier version.**

- **Why.** An author shown its previous version edits it instead of deriving from the evidence, and
  coverage stops growing. Feeding verification results back to the author is the same loop by
  another route: verification runs once, after authoring.
- **Where.** `author-from-package` reads only the package built from the facts; `verify-spec` is
  read-only and its output is not an authoring input.
- **Status.** Followed. The automatic overlap and novelty gates once planned for this principle are
  not built (see [Retired or replaced](#retired-or-replaced)).

### 3.7 Specificity over abstraction; frequency is not significance

**A single striking fact can matter more than a theme that recurs. Keep the specific, verbatim.**

- **Why.** A summariser amplifies frequency: a recurring theme enters every round of summarising,
  and a one-off fact has to survive elimination each time. Left alone it inverts significance.
  Specificity is also what makes a claim narrow enough to be checked.
- **Where.** Distillation's singularity channel keeps one-off facts word for word; a singularity
  that cites an id not in its chunk is dropped whole (`distillation/distill.py`).
- **Status.** Followed on the cited build.

### 3.8 Uncertain evidence is carried with its label, not repaired or dropped

**A fact whose support is weaker, such as one instance stated as a general disposition, stays in the
population with a label that later checks can read. It is not rewritten automatically.**

- **Why.** Such facts are often true of the person, just not repeated. Rewriting them to the
  literal quote can make them wrongly narrow or wrongly past tense; dropping them removes real
  preferences. A label lets verification judge each claim on the facts it actually rests on.
- **Where.** In the package: `assemble` withholds the "verified" label on singularities when only
  one run exists, rather than granting it to everything. The support filter that labels each fact
  is not in this repository; `distill --exclude-ids` accepts its list of facts to leave out.
- **Status.** Not followed in this package. The per-fact labels come from a support filter that
  exists outside this repository; `distill --exclude-ids` accepts its output.

---

## 4. Coverage: nothing lost silently

### 4.1 No silent data loss before deduplication

**The person's text reaches the extraction model whole. Volume is handled by chunking, never by
truncation.**

- **Why.** Deduplication (AUDN) exists so the input side can be generous. Content dropped before
  extraction never reaches deduplication and cannot be recovered by anything downstream.
- **Where.** Extraction chunks long conversations; under the turn contract a chunk that stops at
  its token limit is re-chunked at half the budget and retried; the chunk ledger records every
  chunk ([../PIPELINE.md](../PIPELINE.md), section 5).
- **Status.** Partly followed. Under the turn contract in its default `coverage` mode nothing is
  truncated, and every drop is counted in the run record. Legacy extraction, the default for
  `baselayer run`, keeps at most a capped number of facts per call and drops facts the model
  scores below 0.3 confidence, without counting either. Pasted text, code and tool output are
  excluded on purpose and counted.
  That is a stated choice, not loss ([DATA_TREATMENT_POLICY.md](DATA_TREATMENT_POLICY.md)).

### 4.2 Display may be truncated; the population may not

**Every active fact must be accounted for at each stage. A stage may show fewer, but it may not
consider fewer without saying so.**

- **Why.** A stage that reads a selected subset of facts is a sample, however well chosen, and
  moving who chooses the subset does not remove the sampling. A count over the whole population is
  complete information at low cost.
- **Where.** Distillation gives every fact in a chunk exactly one disposition; `assemble` splits an
  oversized package into shards and drops nothing; the author is told not to infer absence from a
  shard.
- **Status.** Partly followed. The cited build follows it. The static path (`baselayer author`)
  selects a capped number of facts per category for each layer, a cap that was never derived from
  a measurement; see [Retired or replaced](#retired-or-replaced).

### 4.3 A drop in count is not a loss

**Fewer items after a stage can mean duplicates were folded together, or content was lost. A
metric must say which.**

- **Why.** Many leaf themes collapsing into a few can be correct consolidation. Reporting the
  reduction as loss, or as success, without checking which, misreads the stage.
- **Where.** Distillation reports `sing_dedup_pct` (duplication across leaves), not a "survival"
  rate that was bounded at 100% by construction (`distillation/distill.py`); `consolidate`
  records duplicates as a mapping and rewrites no claim (`consolidation/dedupe.py`).
- **Status.** Followed.

### 4.4 Gaps and failures are recorded, never shown as success

**A failed chunk, a failed leaf or a check that could not run is reported as such, beside the
artifact it affects.**

- **Why.** Every failure that degrades to a normal-looking result (an empty list, a clean exit, a
  default value) is invisible at the point of use.
- **Where.** Extraction exits 1 while any chunk is pending or failed; repeated content failures are
  quarantined and listed; a gaps manifest is written beside every authored artifact; `run` will not
  author over quarantined chunks without `--accept-gaps`; `assemble` refuses a tree with a failed
  leaf unless told otherwise; `consolidate` exits 1 if any of its 14 checks fails; a `verify-spec`
  run is recorded blind only after a clean probe.
- **Status.** Followed on the turn-contract and cited builds.

---

## 5. Checks

### 5.1 Code checks and model readings are labelled separately

**Every result says whether code established it or a model judged it.**

- **Why.** A code check cannot be argued with. A model's reading can be wrong. Mixing them lets a
  judgment borrow the authority of a check.
- **Where.** README, "What is checked by code, and what is a model's reading"; `verify-spec` runs
  its deterministic checks by default and its model-judged checks only with `--run-model`.
- **Status.** Followed.

### 5.2 A check must be shown to fail first

**Before trusting a check, run it on an input it should reject and see it reject it.**

- **Why.** A check that cannot fail reads exactly like one that passed. A detector removed in a
  refactor, a scanner that only looks for one pattern, or a metric computed after the bad items
  were already stripped all report a clean zero.
- **Where.** `tests/test_distillation_metrics_can_fail.py` plants fabricated ids and asserts the
  citation metric drops; planted known-bad sessions (`baselayer.turn_contract_fixtures`) test the
  import and the gate, and distillation refuses a fact base holding them unless told otherwise;
  the context gate and `consolidate`'s missing-input check have tests that are written to fail
  first (`tests/test_context_gate.py`, `tests/test_consolidation.py`).
- **Status.** Partly followed. Not every metric has a test that shows it can fail.

### 5.3 Measure the measurement

**Before reporting what a measurement found, check what the instrument itself contributes.**

- **Why.** A query template, a scoring map, a rubric's wording or a sample's construction can
  produce the result attributed to the system. Comparisons need controls that would show it: the
  same prompt for every condition except the context under test (D-095), a wrong-person
  specification (D-096) and a no-specification baseline.
- **Where.** `verify-spec` model checks are priced and dry-run by default; rater agreement and
  retest are reported for consolidation's builders ([CONSOLIDATION.md](CONSOLIDATION.md),
  "Builders").
- **Status.** Followed in the package's own evaluation docs.

### 5.4 A blind rater must be shown to be blind

**A model call used as an independent judge is called blind only after a probe of that call shows
what it could see.**

- **Why.** A rater launched with every sensible setting can still load instructions that name the
  person. Only asking the actual call what it sees reveals that.
- **Where.** `verify-spec --rater cli` removes API credentials from the child, passes `--safe-mode`
  when available, and records a run as blind only after a clean `--probe` with at least one canary
  ([../PIPELINE.md](../PIPELINE.md), section 9).
- **Status.** Followed in `verify-spec`.

### 5.5 Read, don't score, when comparing specifications

**Compare two specifications by what their claims say, not by label overlap or an embedding
threshold.**

- **Why.** Two runs that make the same claims in different words score as different under label
  overlap and under embedding similarity alike. Reading them shows the agreement.
- **Where.** `consolidate` groups duplicates from judgments of claim pairs read in both orders, or
  from shared evidence, and records the grouping without rewriting any claim
  (`consolidation/dedupe.py`, `consolidation/judge.py`).
- **Status.** Followed in consolidation. There is no package command that compares two
  specifications.

### 5.6 Check the artifact the next stage actually read

**Verify the exact file a stage consumed, not a cleaner derivative of it.**

- **Why.** A merged or tidied version of an output can differ from what the next stage read, and
  the difference is invisible unless checked.
- **Where.** `consolidate` reads each layer's `.json` and fails if the `.md` disagrees with it
  (check K02); `verify-spec` re-checks every evidence span against its source turn rather than
  trusting the stored copy.
- **Status.** Followed.

### 5.7 A number must name the measurement it came from

**A threshold or constant is fine if it was derived from data and fixed before the check was first
run on real data. A plausible-looking number is not.**

- **Why.** Numbers chosen for plausibility land on a slope and decide cases arbitrarily; derived
  ones land in a gap between known-good and known-bad cases.
- **Where.** `verify-spec`'s time-split thresholds were fixed before its first real run, though not derived
  (`verification/checks/time_split.py`); the spend table carries measured constants
  and its date (`distillation/spend.py`); `assemble`'s verified threshold is a majority of the
  runs given.
- **Status.** Partly followed. Underived constants remain: the static path's per-category fact cap
  and the `source_docs < 5` floor ([../PIPELINE_ISSUES.md](../PIPELINE_ISSUES.md), P-03), and
  `verify-spec`'s stipulated thresholds (`verification/definitions.py`: shared-evidence Jaccard
  0.5, weak support 0.5, not-the-person's 0.5, trigger grouping cosine 0.35), each tested only by
  a planted good and bad case.

---

## 6. Cost and change

### 6.1 Price before spending; require a ceiling

**A billed run prints its estimate before the first call and refuses to start without a ceiling at
or above it.**

- **Why.** Cost tracks the number of calls, not the size of the corpus, and estimates have
  undercounted real input. A ceiling checked before every call bounds the damage.
- **Where.** `distillation/spend.py`: a dated rate table that must be confirmed, an estimate, and
  `--confirm-spend` or `BASELAYER_SPEND_CEILING_USD`, checked before every call
  ([../PIPELINE.md](../PIPELINE.md), section 12).
- **Status.** Partly followed. `distill` and `author-from-package` require it; sequential
  extraction honours a ceiling only when one is set; `batch-extract`, static `author` and
  `compose` have none.

### 6.2 Cheap constraint, expensive discrimination (D-046)

**Do as much as possible with cheap, mechanical or small-model steps so the expensive model judges
only what is genuinely hard.**

- **Why.** Expensive review after the fact does not scale. Structure the work so cheap steps narrow
  what the expensive step must decide.
- **Where.** Extraction on Claude Haiku 4.5; mechanical collection of themes from leaves and
  mechanical packaging; one authoring call per layer on a larger model; `consolidate` builds its
  index with no model call.
- **Status.** Followed.

### 6.3 Repair the failed part; rebuild only for new information

**When one part fails, find the cause and redo that part. Rebuild a specification when there is
substantial new text, not to fix a single fact.**

- **Why.** A retry fixes one instance and leaves the cause running. A full rebuild costs money and
  renumbers every claim, orphaning any review or correction keyed to the old ids.
- **Where.** The chunk ledger retries only failed chunks and never calls a done chunk again;
  `baselayer run` stops before spending when a file adds nothing new.
- **Status.** Partly followed. Followed for extraction. For leaves, failed parses are repaired
  within a run. Re-running one failed leaf afterwards is not a package
  command. Annotating an existing specification with
  corrections, instead of rebuilding, is designed, not in this package.

### 6.4 A correction to a person flows through facts or text, never through code

**A wrong statement about a person is corrected in the facts it rests on or in the claim's text.
A change to how specifications are built is a code change. The two paths are kept separate.**

- **Why.** A fix for one person's specification written into the pipeline would change every
  other specification built after it, and a pipeline change disguised as a correction leaves no
  record of why the code changed.
- **Where.** [../CORRECTIONS.md](../CORRECTIONS.md): correct the facts when the evidence is wrong
  (`review`, `forget`, then rebuild), edit the text when the wording is wrong; nothing in the
  correction flow edits code or prompts.
- **Status.** Followed in the documented workflow.

### 6.5 Simplicity over cleverness (D-018)

**Keep each model's task simple and handle complexity in code.**

- **Why.** Every time complexity was added to the extraction prompt, results got worse.
- **Where.** Extraction emits plain subject, predicate, object facts; normalisation, gating and
  stamping happen in code.
- **Status.** Followed.

### 6.6 Build custom, borrow patterns (D-001)

**Study what existing memory frameworks do well, borrow the patterns, own the implementation.**

- **Where.** AUDN (add, update, delete as supersession, no-op) is borrowed from an existing memory
  framework; the implementation is this package's.
- **Status.** Followed. The surprise-scoring pattern once borrowed was retired (below).

### 6.7 Supersede, don't delete; staleness by contradiction, not age (D-021)

**A fact is hidden or superseded, not erased. Time since a fact was mentioned is not evidence that
it stopped mattering.**

- **Why.** An outdated fact is still part of the person's history. Silence about something in the
  text reflects what the person used AI for, not what matters to them.
- **Where.** AUDN supersedes and links facts; `forget` and `review` hide facts, and the rows stay in the
  database (restoring one is done by hand; there is no restore command); no step ranks facts by age on the cited build.
- **Status.** Partly followed. `python -m baselayer.extract_facts --reset` deletes extracted facts
  outright, by design, as a deliberate start-over. The legacy brief builder applies a recency
  weighting when it selects facts (`assemble_brief.py`); it ranks, it does not reclassify.

---

## Retired or replaced

Principles from the previous version that the code no longer follows, or that newer principles
replaced. Kept here so the history is visible.

| earlier principle | status now | why |
|---|---|---|
| Surprise-based writes: score each fact for novelty and significance (D-004, D-009, D-015) | retired, except AUDN | Ablation found the scoring steps added nothing; AUDN's deduplication at extraction is the part that holds. |
| Brain-inspired intermediate steps (tiered scoring, consolidation passes, recurrence floors) | retired | Found to be ceremonial in ablation. What holds is the compression from text to facts to layers. |
| The brief: a compact prose summary, about 2,000 to 2,600 tokens, served to every conversation; "narrative coherence over factual completeness"; "the brief should surface the best version" | replaced | The brief is now optional and off by default; `baselayer run` never composes it. The specification is the three layers. A `baselayer run` build is served whole over MCP; a cited build is consolidated into always-on claims plus a trigger index, which you place in a prompt by hand (2.8). Narrative coherence is no longer a goal; traceability is (3.3). |
| Authoring from facts plus philosophy frameworks | replaced | The cited build derives only from the evidence and forbids naming frameworks (2.3). |
| Automatic overlap, coverage and novelty gates on each new generation (from D-040) | not followed | Never built. Isolation (3.6) is enforced by what the author is given, not by a text-overlap check afterwards. |
| Quality gates for hedging and low lexical density between extraction and storage (from D-056) | replaced | Not in the code. The turn-contract gate (3.1) replaced it: a fact is stored only if its quote is found in the person's own words. |
| Falsification of anchor claims by searching for their negation (D-045) | not followed | No code searches for counter-evidence. Contradictions are carried (2.5) and verification flags claims; a negation search remains a goal. |
| Scoped memory: personal, project and professional scopes (D-044) | partly followed | Static authoring reads personal-scope facts only. The turn contract separates the person's own words from everything else by voice class instead. Cross-scope validation of anchors is not built. |
| Identity clusters as invisible priors (D-026) | legacy path only | Used by the legacy brief builder (`assemble_brief.py`); the cited build does not use them. |
| Events versus states as a classification on every fact | not followed | `fact_type` is never assigned ([../PIPELINE_ISSUES.md](../PIPELINE_ISSUES.md), P-04). Claims are not dated. The time-split check (2.5) handles one case: two sides of a contradiction from different periods. |
| A confidence score on every fact, meaningful downstream | not followed | Extraction computes one and drops facts below 0.3 (counted on the turn path, silent on legacy extraction); nothing after extraction on the cited build reads it. |
| Per-category fact cap for each layer (15 facts per category) | conflicts with 4.2; still in code | Still in static `author`, but it was never derived from a measurement and conflicts with 4.2. The cited build does not cap. |
| "Evidence not opinion": no model judge in evaluation | replaced by 5.1 | `verify-spec` has model-judged checks, clearly labelled, priced and off by default; the deterministic checks run alone by default. |
| "Output evaluation over method evaluation": check whether the result makes sense to the person, don't check the code | revised | Both are needed. The person is the final check (1.5), and code checks must be shown to fail first (5.2). |
| Batch changes, clean runs (D-022) | revised by 6.3 | With every chunk and leaf checkpointed, a fix can be applied to the failed part. Batching still applies to changes that affect every artifact, such as a prompt change. |
| Multi-agent adversarial review of each layer (D-024) | retired | Found to add nothing over three-layer authoring without it. |
| Active probing for gaps, and organic probing in conversation (D-020) | not built | Still a goal; nothing in the package asks the person questions. `baselayer journal` offers guided prompts for someone with no conversation history. |
| Flattery countermeasures: false-positive warnings on predictions (D-090) | partly followed | See 2.9. |
| The system is a mirror, not an oracle | kept as a stance | It reflects what the text shows and can be wrong; see 1.3 and 1.5. No code enforces it. |
| Bonds with companies, projects, pets and places can carry the weight of human relationships | kept as a stance | An extraction and reading guideline; no code depends on it. |
| Self-reflective writing (journals) gives better evidence per fact than reactive conversation | kept as an observation | `baselayer journal` offers guided prompts. Not re-measured on the cited build. |

Where [DECISIONS.md](DECISIONS.md) still lists one of these decisions as Active, this page reflects
what the code does. Three sections of the previous version have no row of their own because they
were folded in: the Ghost Layer (D-025, already superseded by D-026, row above), "Corrections are
data, not failures" (now 1.7), and the list of anti-patterns (now spread across 1.3, 2.2, 2.5 and
2.8).
