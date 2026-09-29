# Turn contract (version `turn-contract/1`)

This document is the interface for import, extraction, distillation and verification. Change it
only by bumping the version, and stamp the version on every artifact built under it. Decision
record: D-108 in `DECISIONS.md`.

Status by section:

| section | status | where |
|---|---|---|
| §1-2 turn table, voice classes, detectors | BUILT | `voice.py`, `turns.py`, `turn_import.py`, `import_config.py` |
| §3-5 chunking, citable turns, the gate | BUILT, opt-in (`BASELAYER_TURN_CONTRACT=1` or `extract --turn-contract`) | `turn_contract.py`, `extract_facts.py`, `batch_extract.py` |
| §6 verification | BUILT | `verification/`, `docs/core/VERIFY_SPEC.md` |
| §7 fact stamps | BUILT | `extract_facts.py` |
| §7 leaf, tree, package, layer and brief stamps | BUILT | `turn_contract.artifact_stamp`; `distillation/distill.py`, `assemble.py`, `author_from_package.py` |
| pilot sampling and pricing, planted known-bad sessions | BUILT | `pilot.py`, `turn_contract_fixtures.py` |
| §5 referent (`subject_names`), subject check, object check (`self_object`), evidence kind and `record_only` grounding | BUILT | `turn_contract.py`, `extract_facts.py`, `batch_extract.py`, `distillation/` |
| §8 own-word spans shown to distillation leaves | BUILT, opt-in (`--leaf-spans`) | `distillation/distill.py`, `distill_batch.py` |
| §8 author quote gate: quoted phrases checked against own-voice spans | BUILT, opt-in (`author_from_package --quote-gate --db`) | `distillation/quote_gate.py`, `author_from_package.py` |
| §8 exclusion list for the distillation population | BUILT, opt-in (`--exclude-ids`) | `distillation/distill.py`, `distill_batch.py`, `convergence.py` |

Import, gated extraction, distillation and authoring have run end to end on one real corpus,
once. Post-specification verification (§6) has not yet been run on that specification.

What counts as the subject's own words, source by source and detector by detector, and how to change it for a subject the defaults do not fit: [`DATA_TREATMENT_POLICY.md`](DATA_TREATMENT_POLICY.md).

## Why it exists

A person's specification must rest on that person's own words. Hand audits of extracted facts found
a substantial share that came from the assistant's side of a conversation or from pasted text, and
the specification's cited evidence carried the same material. The extractor saw `User:` and
`Assistant:` labels, but the fact records kept only a conversation id. Once extraction had run,
there was no way to tell which speaker a fact came from.

The rule this contract enforces: **every fact must be grounded in verbatim excerpts of turns the
subject wrote or spoke. Everything else in a conversation may be read as context and may never be
cited.** The rule is
enforced by code, not by the extraction prompt.

## 1. The turn table (written at import)

Import writes one row per turn, or per turn segment when a turn contains pasted material:

| column | meaning |
|---|---|
| `conversation_id` | as today |
| `turn_id` | stable id, `<conversation_id>:<ordinal>` (segments: `:<ordinal>.<segment>`) |
| `speaker` | `subject` / `assistant` / `other` / `system`, taken from the source's own role or speaker field, never inferred by a model |
| `voice_class` | see §2 |
| `text` | the text as imported, with secrets masked (`[REDACTED:<kind>]`, see below) |
| `detector` | which rule assigned a non-own `voice_class`, for audit |

The table also carries `ordinal`, `segment`, `basis` (why a citable row is citable), `source`,
`source_record_id`, `char_start` / `char_end`, `duplicate_of` (a fork or resume copy of a turn its
owner session holds; context only, never citable), `allowlisted` and `practice` (the practice a
row's text is bounded to, set by the own-writing rule in §2; NULL elsewhere). The schema enforces
the vocabularies, and it requires `detector` on exactly the non-citable rows. `practice` was added
to `turn-contract/1` in place (no fact existed under /1); an older table gains the column when the
importer next opens it.

**Secrets.** Import masks secrets in every row's text and in conversation titles, whatever the voice class, because context turns are sent to the extraction model too. Provider key shapes, JWTs, private keys, URL credentials, token values in a key context, password lines, Luhn-valid card numbers and SSN layouts become `[REDACTED:<kind>]` (`baselayer.redaction`). Counts per kind go to `import_redactions`; the secret itself is never stored or logged. A secret written as free prose has no shape and is not caught. `char_start`/`char_end` refer to the turn text before masking.

## 2. Voice classes

Two classes can be cited:
- `own_typed`: text the subject typed.
- `own_dictated`: text the subject spoke, for example through dictation or in a meeting transcript under their own speaker label.

Every other class is context only:
- `assistant`: an assistant or model turn.
- `other_person`: another participant, for example in a meeting.
- `pasted`: a segment inside a subject turn that was pasted in. Detected, excluded by default, and logged with its segment id so the subject can allowlist it later.
- `compaction_summary`: a harness-generated summary placed in a subject-role turn.
- `tool_result`: tool output or a `[tool result]` placeholder in a subject-role turn.
- `harness_prompt`: a programmatic prompt, such as a `claude -p` child or an eval harness, that the source marks as the user.
- `queued_command`: a prompt the subject queued while the assistant was working. It is the subject's words and is re-classed to `own_typed` once recovered (basis `recovered:queued_command`, which requires a human origin on the record). An older client wrote queued prompts with no origin; those are excluded unless the local import config sets `include_originless_queued` (basis `recovered:queued_no_origin`, off by default).

Detectors are deterministic, and each one is tested against a planted known-bad input that fails before the detector exists. The detectors are:
- source markers, such as `isCompactSummary`, entrypoint and queued-command records;
- the `[tool result]` placeholder;
- quote-back, meaning heavy overlap with the preceding assistant turn;
- paste tags and structural paste signals;
- pasted terminal sessions (`paste:terminal`): a segment whose lines are mostly machine output (prompts, tracebacks, box-drawing frames, logs, git and test output, in raw or escaped form). Prose lines typed directly above or below the paste stay own;
- pasted documents inside long turns (`paste:document`, `paste:quote_back_earlier`): on a subject turn of 1,500 characters or more, a second pass reads the whole turn. It groups lines into blocks at blank lines, at hyphen-run separators and where the line ending changes between CRLF and LF, and marks a block pasted when it carries a signal a person typing into a chat box does not produce (carriage returns, tab-separated rows, dated lines, code, legal or boilerplate register, mangled encoding, headings over a list) or when half its word 6-grams appear in any earlier assistant turn of the conversation. Typed lines at a document's edges, and a typed lead-in ending in a colon or an opening quote, stay own. It only moves text from own to pasted, and runs before the dictation score;
- code and machine output inside an own typed segment (`paste:code_or_machine`): after every other rule, lines of code, commands, markup, URLs, paths, machine-format data, compiler and runtime messages, build-log residue, chat-client headers, tool status lines and page menu chrome are marked pasted line by line, and the prose around them stays own. On by default; `detect_code_machine` in the local import config turns it off for a subject whose code is their own words;
- harness signatures from the transcript filter.

Every assumption these detectors make about what counts as the subject's own words, with its default, the switch that changes it, who might want it changed and how to verify the effect, is listed in [`DATA_TREATMENT_POLICY.md`](DATA_TREATMENT_POLICY.md).

**Known limit:** pasted text can be the subject's own writing. By default this contract excludes it, counts the exclusion, and leaves two allowlist hooks for the subject:
- `paste_allowlist` in the local import config: turn ids re-classed `own_typed` one by one (basis `config:allowlist(<detector>)`).
- `allowlist_own_writing_pasted` (off by default): a segment the document segmenter moved (`paste:document` only) whose typing-trait score is at least `own_writing_min_traits` (default 3) is re-classed `own_typed` with basis `allowlist:own_writing_pasted`. The score is the sum of per-line typing traits (typos, configured misspellings, apostrophe-less contractions, a lowercase "i", a space before punctuation) over the segment's lines. 1-2 traits stay pasted. Quote-back and the other paste detectors are never eligible: quote-back matches assistant text by construction, and the others also catch third-party material that carries typing traits. The row gets a `practice` tag: `trading_journal` for a trade record (trade vocabulary, money amounts, option contracts or chart timeframes, laid out as tab or dated rows, or dense in that vocabulary), else `own_document`. The tag says the evidence is bounded to one practice; verification reads it (§6). A manual entry wins over the rule. Like every detector setting, the rule applies when a conversation is written, so changing it takes effect on a fresh import.

## 3. What extraction sees

- **Chunks are built from whole turns, never by cutting text.** A turn longer than the budget is split into segments that keep their `turn_id`.
- **Each chunk carries the turns that precede it as read-only context,** labelled `CONTEXT`. Their ids are not offered as citable. Context is what lets the model interpret a short reply such as "yes, do that".
- **Only turns whose `voice_class` is `own_typed` or `own_dictated` carry a citable id** in the prompt.
- **The prompt is not the enforcement.** It asks for the fields in §4; §5 is what enforces them.

## 4a. Exact column names (binding for import, extraction and verification)

- Turn table `turns`: `turn_id`, `conversation_id`, `ordinal`, `speaker`, `voice_class`, `text`,
  `detector`, `turn_contract_version`.
- `memory_facts` additions: `source_turn_id`, `evidence_spans` (JSON list of
  `{"turn_id": ..., "span": ..., "evidence_kind": "prose" | "record"}`), `inferred`,
  `voice_class` (of the first span's turn), `grounding` (`prose` or `record_only`, §5),
  `turn_contract_version`, `extraction_model`, `extraction_prompt_hash`, `git_commit`, `code_path`,
  `practice` (read at store time from the cited turns' `turns.practice`: the tag when every
  cited turn carries the same one, NULL when none does, the sorted tags joined by `+` when they
  differ, with `general` for an untagged turn).
- `evidence_kind` and `grounding` were added to `turn-contract/1` in place, as `practice` was
  (a version bump would refuse every /1 turn already imported). Facts stamped /1 before this
  change have NULL `grounding` and spans without `evidence_kind`; distillation reads NULL as
  not record-only.
- Every database gets these columns, legacy ones included, so their presence proves nothing. A
  fact is gated if and only if its `turn_contract_version` is set. Verification decides the mode
  per fact on that value and records which mode ran.

## 4. What a fact must carry

A fact is not a quote. It may state something the subject said, or an understanding inferred from
one passage or from several turns. What it must carry is its GROUNDING in the subject's own words:

- `evidence_spans`: a list of 1..N verbatim excerpts, each tagged with the `turn_id` it comes from.
  An inferred fact cites every passage it rests on.
- `source_turn_id`: the first span's turn, kept for compatibility.
- `inferred`: declared by the extractor, true when the fact is an interpretation rather than a
  restatement, so verification can sample inferred facts more heavily.
- `turn_contract_version`, and the extraction stamp from §7.

## 5. The gate (code, outside any exception handler)

A candidate fact is stored only if all of these hold:
1. It has at least one evidence span.
2. Every span's `turn_id` names a turn in the current chunk whose `voice_class` is `own_typed` or
   `own_dictated`.
3. Every span, after whitespace and quote-mark normalisation, is an exact substring of that turn's text.
4. Every span is within the length bounds: at least `TURN_EVIDENCE_SPAN_MIN_WORDS` words (default 3)
   and at most `TURN_EVIDENCE_SPAN_MAX_CHARS` characters (default 400), both overridable per run
   and written to the run record. A one-word "yes" grounds nothing on its own, and a whole turn
   cited wholesale passes condition 3 while pointing at nothing in particular.

**Subject resolution (after the span check, same pass).** The referent is part of the import
config: `subject_names` lists the subject's names. Turn-mode extraction, sequential and batch
(submit and process), refuses to start when it is empty, before any model call. The gate maps
every configured name, and the extractor's generic forms "this person", "the person", "the
user" and "user", to the subject `user` (case and whitespace ignored). This is scoped to turn
mode: the legacy normaliser's shared alias list is unchanged, because a changed subject
re-keys facts already stored on legacy corpora under AUDN. The run record carries the number
of configured names, never the names.

**Subject check (mechanical).** The span check proves grounding, not reference: the subject's
own words can come back with another person as the subject (for example a meeting participant
named for the subject's description of their own work). So, when every span of a gated fact is
an own-voice turn and its subject is not `user`, the other subject is kept only if its name
appears literally, as whole words and case-insensitive, in at least one span. The name is looked
for with a leading determiner or possessive stripped ("the user's wife" as "wife", "The
company" as "company"), as any parenthetical name, as the given name alone (a missing surname
is tolerated), and as any alias the entity map configures for that person. Otherwise the subject
becomes `user`. Nothing is silent: the run record counts `subject_reassigned` and lists each
replaced subject under `subject_reassigned_from`, and counts `subject_referent` (configured
names and generic forms resolved to `user`). A role subject whose word does not appear in the
span (a span saying "my wife" under the subject "spouse") is reassigned; the list shows it.

**Object check (mechanical, after the subject check).** The extractor can also put the subject
in a fact's OBJECT ("user collaborates with <subject name>"). An object that, as a whole and
after the same case, whitespace and quote-mark normalisation, equals a configured name is the
subject. When the resolved subject is `user` (including a subject just reassigned to `user`),
the fact relates the subject to themselves: it is rejected with reason `self_object`, before
any accepted-side count moves. It is rejected, not rewritten, because almost no predicate has
a meaningful reflexive reading, and the one that does (the subject's own name) is already in
the import config. When the subject is another person, the object becomes `user`. Only
configured names are matched in the object slot, never the generic forms: "the user" as an
object is usually a product's end user. A possessive or a longer phrase holding the name
("<name>'s clinic", "<name> and a colleague") is left as it is.

**Evidence kind (mechanical, at the gate).** Each accepted span is classified by its shape,
never by a model: the extraction prompt and schema are unchanged and carry no such field.
Content over layout: `record` when alphabetic word tokens are under half of its tokens
(`RECORD_MAX_ALPHA_SHARE` 0.5), or when it carries a layout signal (a tab, a line with two or
more column gaps, or a leading date) AND its alphabetic share is under
`RECORD_DATED_MAX_ALPHA_SHARE` 0.75; `prose` otherwise. A layout signal alone does not make a
record: a tab used as an indent in front of a sentence is prose. Both thresholds are stated,
not fitted; where they sit on a measured distribution is written beside the constants in
`turn_contract.py`. The rule changed in place under `turn-contract/1` (earlier, any tab or
column gaps made a record): facts gated before the change keep the kind they were stored with.
The kind is stored on each span as `evidence_kind`. A fact whose every span is a record (a
trade-log row such as a date, a date and an amount) is stored with `grounding` `record_only`:
it is kept and counted (`record_only` in the run record), is excluded from distillation input
by default in every distillation reader of the fact base (`distill.py`, `distill_batch.py`,
`convergence.py`; `--include-record-only` admits it; the tree stamp records
`record_only_facts_excluded` and `record_only_facts_included`), and stays in the fact base as
supporting evidence for verification and distillation. A fact with at least one prose span has
`grounding` `prose` and is a normal fact. AUDN searches only among facts of the same grounding
(and contract version), so a record-only fact can never NOOP or supersede a prose one.
On a NOOP the duplicate is not stored, but its evidence spans are appended to the surviving
fact (deduplicated on turn id and normalised span; the first span is unchanged) and counted
as `noop_spans_merged`, so a fact stated again elsewhere carries every own-voice grounding.
An UPDATE still keeps only the new fact's spans.

**Fact count and output budget.** `fact_count_mode` (config `TURN_FACT_COUNT_MODE`, default
`coverage`; per run `BASELAYER_FACT_COUNT_MODE`) decides whether the prompt says
"Extract up to N facts ... most identity-relevant first" and whether accepted facts past the
per-chunk cap are truncated (`capped`), or neither. The uncounted modes size each chunk's
`max_tokens` from its citable characters (`TURN_OUTPUT_TOKENS_PER_CITABLE_CHAR`): `none` adds
no sentence; `coverage` adds one asking for every distinct fact the subject's words support,
without restating; `coverage_fragments` also asks for nothing from a fragment or an unclear
question. The mode is part of the prompt hash, and a batch chunk keeps the mode it was
submitted with (a plan written before the switch existed reads as `capped`). A chunk that stops on `max_tokens` is re-chunked at half the input budget and
each part retried once (`rechunked_on_max_tokens`, listed under `rechunked`); a part that
truncates again is a failed chunk and a suspect flag. A failed chunk (that part, or any call
that failed: an API error after retries, a refusal, an unparseable or schema-invalid reply) is
never marked done: it is recorded in `extraction_chunks_failed` (its body turn ids, input budget
and turn prefix, so it can be rebuilt exactly) in the same transaction as the conversation's other
facts, counted as an error, listed in the run record, and the run exits 1. The next run and
`batch-extract --process --resume` retry only the recorded chunks. No conversation is halted or trimmed on a
fact count: the run record's `density` block reports facts per 1K citable characters with the
run's own p50/p90/p99/max and the ten densest conversations, and the runaway guard is the
spend ceiling (`BASELAYER_SPEND_CEILING_USD`, checked before every sequential call against
measured spend plus the call's worst case).

A fact whose only grounding is assistant, other-person or pasted text fails. Rejection reasons are
counted: `no_grounding`, `no_turn`, `not_own_voice`, `span_not_found`, `span_length`,
`self_object`. The rejection counts are reported for every run: a gate that rejects nothing, or everything, is itself suspect.

Where the counts live: every turn-mode run writes `<corpus>/data/database/extraction_runs/<run_id>.json`
and a row in the corpus database's `extraction_runs` table. The record holds:
- the settings, including every cap and both span bounds;
- the stamps;
- the gate rejections by reason;
- the subject resolution counts (`subject_referent`, `subject_reassigned`, and
  `subject_reassigned_from`) and the `record_only` count;
- the drops after the gate;
- the AUDN actions and any unusable responses;
- the MEASURED API usage (`api_usage`): input, output, cache-read and cache-write tokens for every billed call (extraction and AUDN, sequential and batch, each call labelled with its conversation and whether it was a batch call), and totals with separate batch and sequential subtotals. A call is recorded the moment its response exists, before parsing, so a billed but unusable response still counts. The run output prints the totals; the legacy path prints them too, though it writes no run record;
- a `suspect` list.
It is written in a `finally`, so an aborted run still leaves its counts.

## 6. What the gate proves, and what it does not

- **The gate proves grounding:** every fact rests on words that exist in the source and that the subject wrote or spoke. That check is mechanical.
- **It does not prove that the fact is a correct reading of those words.** That is a judgement, so it is sampled, not gated: post-specification verification shows a reader the fact, its spans and the surrounding conversation, and asks whether the words support it. Inferred facts are sampled more heavily. It is the same split as the authoring citation gate: mandatory is not the same as accurate.
- **Record grounding is reported, not gated.** Verification counts, per claim, its cited facts by `grounding` and their spans by `evidence_kind`, and flags `record_grounded` when a claim cites a record-only fact (`docs/core/VERIFY_SPEC.md`). Distillation excludes record-only facts by default, so the flag appears on a specification built with `--include-record-only`.
- **Domain bounding is reported, not gated.** Verification lists, per claim, how its cited facts spread across practices, and flags `bounded:<practice>` when all of them come from one practice (`docs/core/VERIFY_SPEC.md`). Only rows the own-writing rule re-classed carry a practice tag, so typed text about the same practice is untagged and a claim resting on it is not flagged.

## 7. Versions and stamps

- **Every fact records:** `turn_contract_version`, the extraction model, the extraction prompt hash, `git_commit` and `code_path`. `code_path` is repo-relative, never absolute: an absolute path writes the operator's home directory into every artifact.
- **Every leaf, tree, package, layer and brief records:** the same fields, plus the hash of its input (`turn_contract.artifact_stamp`).
  - The input hash covers fact ids AND fact text (`facts_input_hash`). An ids-only hash cannot tell two corpora apart when the same ids carry different text. The tree's run id is keyed on it.
  - Where: each leaf's `_stamp` and the tree's `stamp` (`distill.py`); the package's `stamp` (`assemble.py`, `model` null because no model runs); `<layer>.stamp.json` and `brief.stamp.json` beside the authored files (`author_from_package.py`), which also record effort, `max_tokens`, token usage summed over every attempt, the rates used and the cost.
  - The version is read from the inputs, not assumed. Distillation, assembly and authoring each refuse a mix of versions, and an unversioned input counts as a version of its own.
  - A layer reused from an earlier run keeps the stamp that run wrote.
- **Builds go into a fresh corpus directory, never into a reset one.**
- **An artifact is trusted only after its stamp has been read.**

## 8. Downstream

- **Leaves** read facts only, so they inherit the guarantee. The existing leaf check, which rejects fact ids outside the supplied set, keeps theme statements tied to gated facts.
- **Own words at the leaves** (`--leaf-spans`, off by default): each fact line also shows up to three of the fact's stored evidence spans, which under this contract are the subject's own words. A singularity's `own_words` excerpt must be a substring of that fact's own spans or it is emptied and counted. Detail: `DISTILLATION.md`.
- **The author quote gate** (`author_from_package --quote-gate --db`, off by default) applies §5's rule at the author. A quoted phrase in a claim must appear, at word boundaries (after the same normalisation, case-folded), in an own-voice span of a fact the claim cites; a fragment of a word does not match, and a verbatim quote keeps the subject's typos. The own-voice spans are those whose turn is `own_typed` or `own_dictated`, which includes pasted own writing re-classed under §2. A quote of 3 or more words found in the own-voice spans of at most 5 other supplied facts has those facts auto-cited and listed in the claim's `gate_added_citations`; every other failing quote loses its quote marks and keeps its words. It never re-asks the author. It refuses to run rather than pass claims unchecked when the database lacks the span or turn columns.
- **An exclusion list** (`--exclude-ids FILE`) removes named facts from the distillation population without touching the fact base, for example facts a separate review found unsupported by their spans. The file's sha256 and counts are stamped on the tree, and a batch run resumed under a different list is refused.
- **Piloting a corpus** before a full run: `python -m baselayer.pilot <corpus_dir> --sample N` selects a stratified sample (source and month) of not-yet-extracted conversations with a citable turn, measures the prompts it would send, and prints an estimate whose every conversion (characters per token, facts per call, output tokens per fact) is labelled as an assumption. It runs only with `--confirm-spend <usd>` at or above the estimate, and with the rates confirmed (`--rates-confirmed`) or passed explicitly. `baselayer.turn_contract_fixtures` writes planted known-bad sessions (compaction summary, harness prompt, pasted block, quote-back, tool result, optional canary) with a manifest; `--planted-manifest` adds them to the sample, checks their import first and their stored facts after. A pilot corpus is not for distillation: `distill.py` refuses a fact base holding any active fact from a `planted-` conversation, and `assemble` refuses a tree built from one, unless `--allow-planted` is given (pilot checks only). The tree and package stamps record `planted_facts_included`.
- **A session that grows** is re-imported whole and re-marked (`import_state.needs_extraction`). Both extraction paths pick it up and re-extract it whole; AUDN deduplicates against the facts already stored. On the batch path this is an incremental submit (`skip_extracted`), which must be processed with `--resume`: `--process` first deletes every extracted fact and the extraction log, so it refuses an incremental batch.
- **Adding a source later** means a new importer that writes this table, then new leaves. Level 1 of distillation is order-independent, so existing leaves do not need to be rebuilt. New ChatGPT and Claude.ai exports are an example.
