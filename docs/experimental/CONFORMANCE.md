# Conformance: does a proposed action fit the person?

> **Experimental. Not part of the supported package.** A research prototype, run privately. The
> code is not published (see [Code](#code)). Nothing here is a `baselayer` command.

## The question

An agent proposes an action for a person: send this reply, delete these files, accept this
meeting. Before it acts, should it go ahead, change the action, or wait for the person?

A conformance check answers one part of that: **does the action fit the person as their
specification describes them?** It does not judge whether the action is safe or sensible in
general. Those limits belong to the agent's own guardrails and to whatever rules the person or
their organisation has written down. The check asks only whether this person, as described,
would want this.

## Inputs and outputs

**Inputs**

- the proposed action, in words;
- optionally, the mission the agent was given;
- optionally, a set of plain rules (for example "never send from this account on weekends");
- a specification: claims, each with an id, a statement, an `Active when` line, cited fact ids,
  and a contested flag where the evidence pulls both ways.

**Outputs**

- a verdict: **approve**, **deny** (full, or partial with the change that would clear it),
  **escalate** to the person, or **not an action** (the item proposes nothing to do);
- an evidence packet: which claims applied, which pulled which way, and what was left
  unresolved;
- a log entry.

The agent is told only the outcome (go ahead, refused, or pending). It is not told which claims
decided or who made the call. The log keeps that. Keeping the reasons out of the agent's view
stops it from learning to phrase requests so that they pass.

## Design: five stages

| stage | what it does | how it judges | status |
|---|---|---|---|
| 1. Rules | Checks the action against plain rules. A rule that permits it lets it through; a rule that forbids it refuses it; no matching rule passes it on. | mechanical (text match) | built; every recorded run used an empty rule set |
| 2. Activation | Decides which claims the action touches. The model sees only the `Active when` lines, never the claim statements, so it cannot pick claims by how persuasive they sound. | model-judged | built and run |
| 3. Case | Loads the touched claims in full, finds where they conflict with each other or where one claim's evidence is divided on this exact point, and sorts the evidence into the two sides. It never decides. | model-judged | built and run |
| 4. Verdict | Reads the case and returns a verdict. Prediction claims are held back until this stage and only the touched ones are added, so a prediction cannot steer which claims are touched. | model-judged | built and run |
| 5. Return | The person answers an escalation, and the answer goes back to the agent and into the log. | the person | designed; the prototype refuses to run it, because only the person can make that call |

### Checks in code around the model calls

These do not depend on a model's reading and were each shown to fire on a planted bad input:

- **Nothing touched means ask.** If no claim applies, the action goes to the person with a
  record that the specification has no coverage here. An empty packet is never an approval.
- **Scope is not a reason.** Some claims say only "this is the kind of work this person does".
  An action proceeds only if at least one claim that actually decides something applied.
- **The verdict must be complete.** Every weakness the case found must appear in the verdict's
  reason or in its unresolved list. A deny must say full or partial, and a partial deny must name
  the change that would clear it. "Not an action" must quote the words showing no action is
  proposed. A verdict that fails is sent back once. It is not escalated.
- **Cited facts must resolve** to facts in the database, or the run stops.
- **Unreadable output stops the run.** If a stage's output cannot be read, the run ends in an
  error state that routes nowhere. Without this, an unreadable result would look like "no claim
  applied" and be routed as a real outcome.
- **Logged, not blocked:** a claim cited by the verdict that never applied at stage 2.

## Two design ideas behind it

**A forced check, not an optional one.** If an agent decides for itself whether to consult the
specification, it mostly does not. The design runs the check on every action and logs its
decision and evidence each time. Which kinds of action need which claims would be learned from
that log rather than written in advance. Status: designed. One part was tested: picking the
relevant claims for a message with a deterministic matcher before the model sees it. Keyword
rules tuned on one set of messages did no better than untuned rules on new messages, and a small
local embedding matcher failed its known-good and known-bad test at every threshold. Cost and
speed were not why it failed. A likely reason, not yet tested: whether a claim applies often
depends on what the whole session is about, which a single message does not show.

**The same shape as a general action classifier.** A classifier that judges an agent's action
against categories every agent should respect has the same structure as this check. The
difference is where the categories come from: here, from one person's specification. If the
check's own rules should change, it proposes the change and the person approves it. It does not
rewrite its own rules. Status: a framing, nothing built from it.

## Status

The prototype has been run on one specification against a few dozen real requests. These results describe
the instrument, not any person:

- Stage 2 (which claims apply) repeated well between runs and between two environments.
- Stage 3 (building the case) was the noisiest stage: a sizeable share of its findings appeared in
  only one of three identical runs.
- Stage 4 verdicts mostly reproduced on a second run and mostly agreed between two different
  models. Which claims a verdict cited did not: one model named far more claims than the other.
- Adding the evidence sorted at stage 3 changed verdicts no more often than simply re-running the
  same input did. Its value is not shown.
- A small local model used for stage 2 agreed poorly with the larger model, and the disagreement
  was in judgment, not in where it drew the line.

**There is no answer key yet.** A substitute key built without the person did not separate the
check from a rule that approves everything. Only the person the specification describes can say
what they would have wanted, and that check has not been completed.

These runs also predate two changes to how blind runs are made. A run is recorded blind only
after a probe shows the model call could not see who the specification describes. Each model call
now runs in a mode that loads no user-level instructions, and a probe of what each call could see
is stored. Do not quote these runs' absolute rates. They need to be re-run under the current
method.

## A made-up example

Specification (invented):

- **X1** "Protects early mornings for focused work." *Active when:* something is being scheduled
  before 9 am.
- **X2** "Says yes quickly to suppliers they already use." *Active when:* a request comes from an
  existing supplier.

Action: "Accept the 7:30 am call from the office-supplies vendor."

1. Rules: none match, so the action passes on.
2. Activation: X1 and X2 both apply.
3. Case: X1 says pause, X2 says proceed.
4. Verdict: **deny, partial.** The part denied: the 7:30 am time. The change that would clear it:
   "propose 10 am instead." The unresolved list says why X2 did not outweigh X1.
5. The agent sees "refused", revises the action, and resubmits under the same request.

With "Accept the 2 pm call from the office-supplies vendor", X1 does not apply and X2 alone gives
**approve**. With "When is the vendor call?", the verdict is **not an action**, quoting the
question.

## How you could try the idea

There is no runnable code here. You can approximate the first two stages by hand with what the
package already writes:

1. Build a specification with the cited build, run `baselayer verify-spec` on it, then run
   `baselayer consolidate` to get `served.txt` and `index.json`.
2. Give a model the action and only the `active_when` field of each claim, from the layer `.json`
   files that `author-from-package` writes, and ask which claim ids apply. That is stage 2.
3. Look up those claims in `index.json` and read them against the action yourself. That is what
   stages 3 and 4 automate.

## Code

Not published. The prototype's modules load one real specification by path, its tests are built
on that specification's claims and facts, and its harness reads private run records. What would
be released is a rewrite: the stage contract, the routing table, the completeness checks and the
rule format described above, with a constructed specification as the test fixture.

## Open questions

- What counts as the right answer, and how to collect it from the person without making them
  review every action.
- Whether the check may deny on its own, or only approve, refuse by written rule, and escalate.
  See [ESCALATION.md](ESCALATION.md).
- Many verdicts were right in direction and wrong in a detail. There is not yet a way to record
  "right, except for this".
