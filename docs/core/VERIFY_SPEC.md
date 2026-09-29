# Post-specification verification (`baselayer verify-spec`)

Status: BUILT on `feat/respec-hardening`. Deterministic checks run on real specifications; the
model-judged checks have run only against a scripted fake rater in the test suite.

## What it is for

The turn-contract gate (`TURN_CONTRACT.md` §5) proves that a fact quotes words the subject wrote or
spoke. It does not prove that the fact is a faithful reading of those words (§6). The authoring
citation gate is the same shape: a claim must cite facts, which does not make the citation accurate.
Verification is the step that reads the evidence and reports on it.

It runs once, after a specification is authored, and only reports. Authoring never sees its output,
so the next specification is not shaped by the instrument that grades it.

## Invocation

```
baselayer verify-spec <spec_dir> --label <label> --corpus <corpus dir or memory.db> --out <dir>
```

- `--label` is required. Every finding names claims as `<label>:<claim id>`, because a claim id is
  only unique inside its own specification.
- The default is a dry run: every deterministic check runs, the model-judged tasks are built and
  priced, and no model is called.
- `--run-model --rater cli --rater-cwd <dir>` runs the model checks through `claude -p` on the
  subscription.
- `--run-model --rater api --model <id> --confirm-api-spend <usd>` runs them on API credits. The run
  refuses when the upper estimate exceeds the cap.

## Writes and reads

- **Output.** The only directory written is `--out`. It refuses an output path inside or above the
  spec, the corpus, or any Base Layer data directory, meaning one holding `identity_layers/` or
  `database/memory.db`.
- **Databases.** Every database is read without writing to it. A WAL database with nothing pending
  opens `mode=ro&immutable=1`, because a plain `mode=ro` connection still touches the `-shm` file.
  A database with a pending `-wal` or `-journal` is copied into `--out`, opened from the copy, and
  the copy is deleted afterwards. The database this install serves over MCP is always read from a
  copy, and `--snapshot` forces a copy for any corpus, because `immutable=1` is only safe when
  nothing is writing. An immutable open that sees the database change during the run reports
  `corpus_changed_during_run`.
- **Existing verifier.** The existing verifier (`verify_provenance.run_verification`, MCP
  `verify_claims`) deletes and inserts rows in `claim_verification`. This module never calls it. It
  reuses only the SELECT-only helpers (existence, recurrence, cross-domain, temporal, supersession)
  on its read-only connection, and reports their results under `existing_machinery`.

## Which mode runs

Mode is decided per fact, not per database. `init_database` adds the turn-contract columns
(`source_turn_id`, `evidence_spans`, `turn_contract_version`) to every database, including ones
whose facts were extracted on the legacy path, so the presence of the columns says nothing. A fact
is verified in turn-contract mode if and only if its `turn_contract_version` is set; every other
fact is verified in fallback mode. The report records `voice_mode` (`turn_contract`, `fallback`,
`mixed` or `none`) and `voice_modes`, the count of live cited facts in each.

The re-gate does not re-check the span length bounds. They are extraction settings,
overridable per run and recorded in that run's record, so a span that passed its own
run's bounds is not re-judged against today's defaults.

## Checks

Deterministic:

| check | finds |
|---|---|
| resolution | cited ids that are missing, ambiguous, superseded, or retired by a `user_corrections` DELETE / refuted / REATTRIBUTE |
| voice, turn-contract mode | each fact's voice (the `voice_class` of its first span's turn; own only if every span's turn is own), plus a re-run of the §5 gate on EVERY span in `evidence_spans` (`no_grounding`, `no_turn`, `not_own_voice`, `span_not_found`, `source_turn_mismatch`, `spans_unparseable`) and the §7 stamp (`stamp_mismatch`) |
| voice, fallback mode | only what the conversation record proves: `no_conversation`, `document_import`, `no_subject_turns`, `unresolved_turn_level`. No turn id is invented. A fact that carries turn grounding but no contract version is also reported as `stamp_missing` |
| duplicates | identical normalised names, shared cited evidence (Jaccard at least 0.5), and a contested flag that differs between duplicate candidates |
| trigger groups | identical Active_When text, lexical groups, the lexical standing rule (a description of the text, not a prediction of firing), and missing conditions |
| practice | per claim, how its live cited facts spread across practices (`memory_facts.practice`, read from the cited turns' `turns.practice`) and categories, with the dominant practice and its share. A claim whose live cited facts ALL carry one practice tag is reported `practice_bounded` with detail `bounded:<practice>`: a pattern from one practice, not a general trait. Untagged facts are not a practice and are never flagged; a fact citing two practices (`a+b`) bounds its claim to neither. Report only. On a database without the column, `available` is false and nothing is flagged |
| grounding | per claim, its live cited facts by `memory_facts.grounding` (`prose`, `record_only`, and `unstamped` for NULL: a fact stamped before the column or a legacy fact, never read as prose) and their spans by `evidence_kind` (`prose`, `record`, `missing`), counting record spans inside prose-grounded facts too. A claim citing any record-only fact is reported `record_grounded` with those fact ids: `warn` when every live cited fact is record-only, `info` otherwise. The summary carries `record_grounding` totals, so a specification built with `--include-record-only` shows how much of it rests on record rows. Report only. On a database without the column, `available` is false and nothing is flagged |
| JSON and markdown divergence | when a spec directory holds both, differences in ids, names, citations, conditions or contested flags |

Model-judged:

| check | finds |
|---|---|
| support | each cited fact's support for its claim, the poles and sides of contested claims, and optionally referent (document or author) |
| voice | who originated each fact the conversation record could not settle. A turn the rater names is kept only if it was one of the excerpts it was shown |
| fidelity | turn-contract mode only: whether each fact is a faithful reading of its cited turn in context, under a fixed standard reported strict and lenient |
| cross | candidate claim pairs plus a random recall sample of the rest: contradicts, tensions, duplicate or compatible |
| adjudicate | each apparent contradiction as a fact pair read in source context: real, context split, misattribution, extraction error or no conflict. Also whether each contested flag is confirmed |

Every reply is validated against the exact id set the task sent. A reply that fails validation is a
failed task, never a partial result. Raw replies are kept under `--out/raw/` and reused only for a
byte-identical prompt from the same rater.

## Blindness

Every Claude Code child loads the user-scope `~/.claude/CLAUDE.md`, whatever its working directory
or config. So the CLI rater records `blind=false` and names that channel. It also:

- removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from the child environment, and asserts it;
- sets `BASELAYER_SPEC_INJECT=0` and disables hooks through `--settings`;
- passes an empty strict MCP config and `--allowedTools ""`. That grants no tools; whether it denies
  tools that user-scope allow rules already permit is unverified;
- refuses a working directory under any `CLAUDE.md`, or one that overlaps the repo, spec or corpus.

`--probe` asks the actual child what it can see and stores the answer beside the results.
`blind=true` is recorded only when a probe ran and none of the `--probe-canary` strings appeared.

## Output

Each spec produces:

- `<label>.verification.json`: definitions, per-claim profiles, findings, existing-machinery
  results, model results, and stamps (verify version, definitions version, git commit, code path).
- `<label>.verification.md`: the same content as a readable report.
- `<label>.tasks.json`: the task index, without prompts.

Every finding carries its qualified claim ids, fact ids, turn ids and conversation ids.
