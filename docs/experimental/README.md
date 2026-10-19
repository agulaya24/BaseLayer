# Experimental work

**Nothing in this folder is part of the supported package.** These pages describe research
directions: what each one is for, how it is designed, how far it has got, and whether any code is
published. None of them ships as a `baselayer` command, none is covered by the test suite, and
the designs may change or be dropped.

This is a different kind of "experimental" from the cited build (`extract --turn-contract`,
`distill`, `assemble`, `author-from-package`, `verify-spec`, `consolidate`). Those commands are marked experimental, but they
are in the package and run today. See [PROGRESS.md](../PROGRESS.md) for the status of everything
that is in the package.

All three directions ask the same question from different sides: once an AI has a person's
specification, how should an agent that acts for that person use it to decide what to do on its
own and what to bring back to the person?

| page | question | status |
|---|---|---|
| [CONFORMANCE.md](CONFORMANCE.md) | Does a proposed action fit the person the specification describes? | built; not published |
| [ESCALATION.md](ESCALATION.md) | When an agent acts on someone's behalf, which requests should it carry out, and which should it hold for the person? | designed; an earlier test harness built; not published |
| [BEHAVIORAL_ENVELOPES.md](BEHAVIORAL_ENVELOPES.md) | What may an agent do alone for a person inside an organisation, given the organisation's bounds and the person's own? | designed and planned; test scaffolding built; no results |

## How to read the status labels

| label | meaning |
|---|---|
| **built** | code exists and has been run, outside this repository |
| **designed** | written down, not built |
| **planned** | an experiment designed in detail, not yet run |
| **not published** | the code exists but is tied to private data and is not in this repository |

## Why the code is not here

The prototypes were built and tested against real specifications, which carry real people's
words. The code reads those files by path, embeds their identifiers in tests, or was written
around one corpus. Publishing it would mean publishing the people. Each page describes the design
in enough detail to rebuild it, uses made-up examples only, and says what would have to change
before the code could be released.

## What you can try today

The pieces these designs build on are in the package:

- `baselayer consolidate` writes `served.txt` (the always-on claims plus one line per situation,
  each naming the claims to read) and `index.json` (claim id to full text and cited facts). Every
  design here starts from that pair. ([core/CONSOLIDATION.md](../core/CONSOLIDATION.md))
- `baselayer verify-spec` checks a specification against its corpus before anyone relies on it.
  ([core/VERIFY_SPEC.md](../core/VERIFY_SPEC.md))
- A claim in a cited build can carry an `Active when` line: the situation it applies to. All three
  designs use it to decide which claims a given action touches.
