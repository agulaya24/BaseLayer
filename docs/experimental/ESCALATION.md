# Escalation: when an agent acting for someone should stop and ask

> **Experimental. Not part of the supported package.** A design, plus an earlier test harness
> run privately. The code is not published (see [Code](#code)). Nothing here is a `baselayer`
> command.

## The problem

Agents increasingly act on a person's behalf through delegated authorization. The agent asks the
person's authorization server for a token, a permission to do one thing, under a mission the person set ("order
supplies for the new office", "renew my software subscriptions"). The server has to decide whether
each request is consistent with what the person meant.

Rules handle the clear cases: a spending cap, an allowed list of recipients. The hard cases are
the ones the mission does not settle. The mission is written in ordinary language, and the
protocols leave open how a server should judge a request against it. Some leave room for a
reviewer (the person, or a service the person chooses) to make that call.

The proposal: **the person's specification acts as that reviewer's standing guidance, and
anything it cannot settle goes back to the person.** The aim is not to ask less often. It is to
ask about the moments that matter to the person.

## Design

### The decision

| situation | outcome | decided by |
|---|---|---|
| a written rule forbids the request | refuse | code |
| a written rule permits it | carry it out | code |
| no rule applies; the specification's claims that apply all point the same way | carry it out, with the claims that applied attached as constraints | the conformance check ([CONFORMANCE.md](CONFORMANCE.md)) |
| no rule applies; no claim applies | hold for the person, with a record that the specification has no coverage here | code |
| no rule applies; the claims that apply conflict, or one claim's evidence is divided on this point | hold for the person, with the conflict stated | the conformance check |

**Open question: may the check deny on its own?** The prototype's verdict stage can return a deny
(including a partial deny that names the change that would clear it). One view is that only a
person's refusal should be final, so the check should approve, refuse by written rule, or escalate,
and never deny on its own judgment. This is not settled.

The design decides **that** a request is held, not **who** answers it. Whether the person, a
governance service or someone the person names answers is configured on the person's side.

### How it fits an authorization flow

The design needs no new message from the agent:

1. The agent sends its token request as usual.
2. The person's server answers in one of three ways: grant, deny by rule, or **pending**, if the
   protocol supports a pending answer the agent can poll.
3. On pending, the agent is told only "pending": not who decides and not why. An agent that sees
   the reasons can learn to phrase requests so that they pass.
4. The evaluation is written to the audit log the server already keeps: specification version,
   rule result, claims that applied, conflicts, verdict, why it was held, who decided, and what
   the agent was shown.
5. The person decides outside the protocol, for example in an app.
6. The agent's next poll returns granted or denied. A closing log entry records the person's
   decision beside the check's reasoning.

That closing entry matters beyond the single request: it is a labelled example of what this
person wanted in a case the specification could not settle, and nothing else in the system
produces one. The smallest useful experiment builds the hold-and-ask path first, even with a
trigger as crude as "hold everything", because that path is what produces the answer key.

### Escalation across domains

A person may run several agents: one for work, one for personal life. Sometimes an event in one
domain should interrupt an agent in another. The order between domains comes from the person's
own stated priorities, with **no built-in default**. People differ, and the reviewer's job is
to be faithful to the person, not to apply a social norm. A permission system cannot express
this, because it is an ordering of what matters, not a grant of access. Status: designed.

## An earlier test harness

Before the five-stage design, a simpler harness was built and run (status: built, superseded):

- **Input:** the mission, the mission's log so far, and the request.
- **Output:** granted, denied, or clarification required, with required fields for the reason,
  the governing constraint, what was considered, what the decision refused to trade away, the
  specification claims used, and, for a clarification, the single unmet condition that would
  settle it.
- **Citations enforced by the output schema, not by instruction.** Asking the model to cite
  produced no citations. Making the claims-used field required in a strict schema produced them
  every time. A judgment made with a specification that cited nothing was treated as failed and
  retried.

## Lessons for evaluating it

These hold for any evaluation of an agent's judgments against a specification.

- **Use a control the specification should not change.** Build missions in two kinds. In a
  *thick* mission the mission itself settles the request, so every arm should agree. In a *thin*
  one it does not, and that is where a specification can matter. Without the thick control,
  "the specification changed the judgment" cannot be shown false.
- **Thick means settled, not strict.** A first attempt made missions thick by stacking
  prohibitions. That backfired: prohibitions are exactly what need judgment to apply. A thick
  mission is one where the answer follows by arithmetic from a stated number, with the expected
  answer written down before the run.
- **Compare arms:** no specification; another person's specification; the person's derived
  specification; a hand-written description of the person.
- **Run a cheap preflight.** Before paying for a full run, run the no-specification arm alone
  against the answer key. This cost little and found an item the key itself could not answer.
- **A filled citation field proves nothing until every id resolves** to a real claim and its
  facts. Check the resolver as well: the one used here was wrong four times before it was right. An
  unresolved rate is not a fabrication rate.
- **A resolved citation shows the reference is real, not that it mattered.** Only removing the
  claim and re-running shows that.

## Status

- The decision table and authorization flow are designed. The five-stage check behind them is a
  private prototype ([CONFORMANCE.md](CONFORMANCE.md)).
- Runs on real requests reproduced well across runs and across models, but did not separate from
  a rule that approves everything when measured against a substitute answer key. The real answer
  key needs the person's own decisions, which the hold-and-ask path is meant to collect.
- In most decided items no opposing consideration was found at all, so the question of when to
  stop was rarely tested.

## A made-up example

Two invented people use the same pair of agents with different specifications.

Person P:

- **p:C1** "Booked time off is protected; work requests during it are declined unless they
  cannot move." *Active when:* a work commitment falls inside booked leave.

Person Q:

- **q:C1** "Speaking invitations in their field take priority over leave, which can be
  rearranged." *Active when:* an invitation to speak conflicts with personal plans.
- **q:C2** "Leave booked with family is not changed without asking them first." *Active when:*
  changing plans that involve family members.

Event: the work agent is asked to accept a speaking slot at a conference that falls in a week of
leave already booked by the personal agent.

- No written rule covers it.
- **P:** p:C1 applies and settles it. The work agent declines, with p:C1 attached as the reason,
  and logs the decision.
- **Q:** q:C1 and q:C2 both apply and pull opposite ways. The request is held as pending, and Q
  decides with the conflict stated.

Same event, two right answers, each taken from the person's own ordering.

A thick and thin pair, also invented: the thin mission "Restock the office kitchen with whatever
is running low" with a request to order a new coffee machine is not settled by the mission, so
the specification is consulted or the request is held. The thick mission "Reorder only items on
the standing supplies list" with the same request is denied by rule, and every arm should agree.

## Code

Not published. The harness and the prototype read real specifications by path, name real people
in comments and fixtures, and one test drew on private correspondence. A release would be a
rewrite of the design above: the decision table, the log fields, the judgment schema with
required citations and the citation-retry rule, with constructed missions and a constructed
specification.
