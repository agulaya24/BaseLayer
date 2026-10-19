# Behavioural envelopes: what an agent may do alone

> **Experimental. Not part of the supported package.** A design and an experiment plan. Test
> scaffolding has been built; no experiment has produced results yet. The code is not published
> (see [Code](#code)).

## The idea

An **envelope** is the set of outcomes an agent may reach on someone's behalf without asking.

An agent that works for a person inside an organisation answers to two envelopes:

- **The organisation's envelope:** the outcomes the organisation accepts. It is set in advance,
  and it bounds what any agent may do.
- **The person's envelope:** how this person would choose inside the organisation's bounds. It is
  learned from what the person has written and decided. It decides how to route a request; it
  never overrides the organisation.

**The agent acts alone only where the two envelopes overlap.** Every other action goes to a
human. A person's specification feeds only the person's envelope, never the organisation's.

## Design

### Four zones, and a fifth that counts as a violation

| where the action falls | what the agent does |
|---|---|
| inside both envelopes | carry it out and log the path |
| inside the organisation's, but whether it suits the person is unknown | ask the person |
| the person would want it, the organisation forbids it | refuse and explain |
| outside both | escalate through the organisation's lines of authority |

Listing outcomes in advance shows a fifth region: inside the person's envelope but outside the
organisation's, for example doing what the person wanted while skipping a required step. That
counts as a violation, not a success.

### Where the organisation's envelope comes from

In order of how hard each is to capture:

1. **Written rules:** policies and system settings. Enforceable in advance.
2. **Unwritten norms:** past decisions, incident reviews, what people say when asked. Only partly
   enforceable.
3. **Who actually approves what:** the authority graph. Enforceable once mapped.

When two people with authority disagree, the agent maps each one's envelope for the action. If
they overlap, it acts inside the overlap and logs both owners. If they do not, it names what each
one's constraint protects and escalates to someone above both, with the disagreement attached.
The agent never picks a side.

### Classifying an action

Every action is scored on five dimensions:

- **reversibility:** can it be undone?
- **authority required:** who would normally have to approve it?
- **norm sensitivity:** does it touch an unwritten norm?
- **threshold:** is a limit near (an amount, a count)?
- **visibility:** does it stay inside or go outside?

If any dimension is high, the action is escalated unless it was authorised in advance.

### Checkpoints judge the path, not the outcome

Outcomes can arrive weeks later, so the checks are placed on the path:

- **before an irreversible step:** delete, submit, send;
- **at a crossing:** internal material about to go outside, a count reaching its limit;
- **on drift:** the stated goal of the next step no longer traces back to the request.

### Learning from outcomes

Each completed path is labelled twice: was the process sound, and was the outcome good?

| | good outcome | bad outcome |
|---|---|---|
| **sound process** | reinforce the path | keep the envelope; log it as variance |
| **unsound process** | flag it as luck | tighten the envelope |

Only a pattern of sound-process, bad-outcome cases moves an envelope. A single bad result does
not.

### From specification claims to the person's envelope

Status: designed, not built.

- A claim's `Active when` line selects which claims apply at a checkpoint.
- **Claims are inputs, not policy.** A claim describes the person. It does not say what the agent
  should do, how to check it, or what wins in a conflict.
- A proposed derived form turns the claims into a policy the agent can follow: *When* (the
  situation), *Do* (the action), *Because* (the claims, with their cited evidence), *Check* (how to
  confirm), *Conflicts* (which other policies it can collide with), and *No coverage* (what to do
  when nothing applies). The person confirms each derived policy before any agent uses it.

## Measuring it

### How conformance would be checked

- Each test case is laid out in advance as a tree: the checkpoints an agent passes and every way
  the case can end.
- Each ending is labelled against the organisation's rule as written: followed, violated,
  escalated when required, escalated when not required, or contested. Each is also labelled for
  whether it falls inside the person's envelope.
- The agent can act only through a fixed set of mock tools, so its decision is read from the tool
  calls it made, with no model acting as judge.
- Endings such as "did nothing", "only read", "ran out of turns" and "did something unlisted" are
  registered in advance as outcomes, not dropped.
- The reason the agent gives with each tool call is analysed separately from what it did.

### A cost measure

Cost per 1,000 decisions = 1,000 × (escalation rate × *c* + rate of wrong unsupervised actions ×
*L*), where *c* is the cost of one escalation to a human and *L* the expected loss from one wrong
action taken alone. Policies are compared by plotting escalation rate against wrong-action rate.
They are ranked by the ratio *L*/*c* at which one policy overtakes another. Refinements under
consideration: separate necessary from unnecessary escalations, separate reversible from
irreversible wrong actions, and give a refusal its own cost.

### Planned experiment

Status: planned. Each arm is one condition the agent is given. Every arm runs in one invocation, so arms cannot drift apart between runs.

**Arms**

- no specification;
- a placebo of the same length;
- another person's claims, matched by `Active when` line;
- the person's claims;
- the person's claims on a second wording of the same case;
- a ladder of written policies as a positive control: a general principle, a rule about the
  situation that does not name the action, and the full derived form;
- a log of the person's past decisions;
- a constructed person, which measures whether an agent takes up a specification, not whether
  the specification is faithful.

**Ways the hypothesis could fail, registered in advance**

1. The instrument cannot see written policy change behaviour at all.
2. The person's claims do no better than the placebo or another person's claims.
3. Rewording the case moves results more than the claims do.
4. The effect does not last into later turns.
5. A constructed priority ordering is ignored in favour of a social default.
6. Agreement with the person's own answers is no better with the claims than without.

**Measures:** distance between outcome distributions against floors from repeated sampling and
from rewording, permutation tests with correction for multiple comparisons, one primary measure
per case, and mirrored cases in which the correct outcome flips.

**Case domains**, each tied to published rule text so the organisation's envelope is not made up:
IT change management, sales outreach under anti-spam law, expense approval, legal delegation under
professional conduct rules, customer support under a published support policy, and one case that
crosses from personal life into work.

## Status

- The design and the experiment plan are written and have been reviewed adversarially.
- **Built:** a mock tool server with per-episode state; checks on the test harness, each shown to
  fail on a planted fault (the exact tool list, no permission denials, the pinned model, separate
  tool state per episode, ordering of parallel calls); outcome trees for the planned cases,
  labelled before any run; and an analysis script, tested on synthetic data, where it found the
  planted effects and only those.
- **Not built:** deriving an envelope from a specification. In the trees so far the labels were
  written by hand, not derived from claims.
- **Blocked:** the isolated way of launching the agent, needed so that it cannot see anything about
  the person beyond the arm under test, did not expose the mock tools, and the harness checks
  correctly refused every trial episode. An alternative is pending.
- **No results.** No episode with a real specification has run, so the programme has produced no
  evidence yet.

## A made-up example: a small accounting firm

Organisation envelope (from written rules and the authority graph):

| id | bound | kind | applies when | when crossed |
|---|---|---|---|---|
| ORG-1 | Vendor payments over $2,500 need the managing partner's approval | written rule, threshold | a payment is about to be scheduled | escalate to the managing partner |
| ORG-2 | No client filing is released without a partner's sign-off | written rule, irreversible, external | a filing is ready to submit | checkpoint before submitting; hold and route |
| ORG-3 | Client records inside the retention period are never deleted | written rule, irreversible | a delete or archive is requested | refuse and explain |
| ORG-4 | Fee discounts above 10% need the billing lead and a partner together | authority graph | a discount is proposed | act inside their overlap, else escalate to both with the conflict named |

Person's envelope (for one staff accountant; in practice each line would cite claim and fact ids
from their specification):

| id | bound | kind | applies when | when crossed |
|---|---|---|---|---|
| IND-1 | Prefers client reminders sent in the morning, not late in the day | routing | a client reminder is scheduled | reschedule to the morning (inside the organisation's bounds) |
| IND-2 | Accepts automatic filing of receipts under $50 | authorised in advance | categorising expenses | carry it out and log |
| IND-3 | Would waive a late fee for long-standing clients | outside ORG-4 when the waiver is above 10% | a waiver is requested | refuse and explain; route the request to ORG-4's owners |

A $40 receipt falls inside both envelopes: filed and logged. A client reminder set for 6 pm is
inside the organisation's envelope, and IND-1 moves it to the next morning. A 15% waiver is something the person would want
and the organisation forbids without two approvers: refused, explained, and routed.

## Open cases

- The person wants it and the organisation forbids it, repeatedly: when does that become a
  request to change the rule?
- A new user whose envelope is empty: does everything escalate at first?
- A rule that changes while an action is under way.
- An escalation target who cannot be reached.
- One agent serving several people whose envelopes conflict.

## Code

Not published. The harness, case definitions and analysis script are written around private test
material and name real people in comments and probes. The mock tool server is generic and is the
first candidate for release once the case definitions it is documented against are rewritten with
constructed cases.
