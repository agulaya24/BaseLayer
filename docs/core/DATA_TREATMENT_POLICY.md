# Data treatment policy: what counts as the subject's own words

Companion to `TURN_CONTRACT.md` (version `turn-contract/1`). The contract says that only the
subject's own words can be cited. This document lists every assumption the importer and the
gate make about WHICH words those are, the default for each, the switch that changes it, who
might want it changed, and how to check that a change did what it was meant to.

The defaults were set for one kind of subject: a person who writes prose to an assistant and
pastes other material in. They are not right for every subject. A developer's code, a
trader's journal rows, or a writer's pasted drafts may be exactly the evidence a
specification of that person should rest on. The subject decides; this document is the menu.

How to read each entry:

- **Default**: what happens with no configuration.
- **Switch**: the key in the local import config (`import_config.json`, see
  `import_config.py`), an environment variable, or a command flag. "Not configurable" means
  the behaviour is fixed in code today.
- **Who might change it**: the kind of subject or use for whom the default is wrong.
- **Verify**: how to see the effect in the turn table or the run record.

Two rules apply to every import-time entry:

1. **Import-time settings apply when a conversation is written.** A conversation whose
   content hash is unchanged is not rewritten, so changing a detector setting takes effect
   on a fresh import into a fresh corpus directory (`TURN_CONTRACT.md` §7). The one
   exception is `paste_allowlist`, which is re-applied to stored rows on every import
   (`turns.sync_allowlist`).
2. **Every non-own row names the rule that made it non-own** in the `detector` column, and
   every citable row names why it is citable in `basis`. So any switch can be checked by
   counting rows by `detector` and `basis` before and after.

The base verification query, run against a corpus database:

```sql
SELECT source, voice_class, detector, basis, COUNT(*), SUM(LENGTH(text))
FROM turns GROUP BY 1, 2, 3, 4 ORDER BY 1, 5 DESC;
```

---

## 1. Speaker

**Assumption.** The speaker of a turn is the one the source's own role or speaker field
names. No model and no heuristic assigns a speaker.

- **Default**: `user`/`human` roles are `subject`; `assistant` is `assistant`; system and tool
  roles are `system`; a meeting line is `subject` only under a configured label.
- **Switch**: not configurable, except the meeting label (§8).
- **Who might change it**: nobody should. A source with no role field cannot be imported
  under the contract; it needs its own importer.
- **Verify**: `SELECT speaker, voice_class, COUNT(*) FROM turns GROUP BY 1, 2`.

## 2. Voice classes

Only `own_typed` and `own_dictated` are citable. The full list and meaning is in
`TURN_CONTRACT.md` §2. A row the gate does not recognise is not citable (the gate fails
closed on unknown classes).

## 3. Record-level rules (a whole source record)

These decide a whole record from the source's own fields. They are exact, not heuristic.

| detector | what it marks | class |
|---|---|---|
| `source:isCompactSummary`, `text:compaction_signature` | harness-written summary in a user-role record | `compaction_summary` |
| `source:tool_result_block`, `text:tool_result_placeholder` | tool output in a user-role record | `tool_result` |
| `source:isMeta`, `source:system_origin`, `text:cross_agent_relay` | harness or agent-to-agent prompts | `harness_prompt` |
| `source:promptSource=sdk`, `source:entrypoint=sdk-cli,no_human_origin` | programmatic prompts with no human origin | `harness_prompt` |
| `config:harness_cwd` | a record run from a configured harness working directory with no human origin | `harness_prompt` |
| `harness:replay_of_subject_text` | a programmatic prompt that replays text the subject typed elsewhere | `harness_prompt` |
| `source:role=system`, `source:role=tool` (ChatGPT) | system and tool messages | `harness_prompt`, `tool_result` |
| `text:tool_call_placeholder`, `text:harness_signature`, `text:repeated_unhistoried_prompt` (database copies) | stored tool calls, known harness openings, a prompt of 8+ words recurring 3+ times and matching no history prompt | context |

Also dropped entirely, not stored: empty records, slash commands of 200 characters or less,
and history entries that start with `/` or `!`.

- **Default**: all on.
- **Switch**: `harness_cwd_patterns` (regexes over a record's working directory) and
  `harness_template_roots` / `harness_template_exclude_dirs` (§5.4) are configurable. The
  rest are not.
- **Who might change it**: a subject who runs their own scripted sessions from a fixed
  directory adds it to `harness_cwd_patterns`. A subject whose typed prompts are wrongly
  caught by a harness rule would need a code change; report the detector and the row.
- **Verify**: count rows per `detector` above. A replay (`harness:replay_of_subject_text`)
  is context because the subject's original typing is stored elsewhere as own.

## 4. Queued prompts

**Assumption.** A prompt the subject typed while the assistant was working is the subject's
words once recovered (basis `recovered:queued_command`, which requires a human origin).

- **Default**: prompts with a human origin are recovered; queued prompts an older client
  wrote with no origin are excluded, because no field tells them apart from queued
  notifications.
- **Switch**: `include_originless_queued` (default false; basis `recovered:queued_no_origin`).
- **Who might change it**: a subject with a long history on the older client who has
  checked a sample of originless queued rows and found them to be their own typing.
- **Verify**: `COUNT(*) WHERE basis = 'recovered:queued_no_origin'`, and read a sample.

## 5. Paste detectors (inside a subject turn)

A subject turn is split into segments at blank lines and hyphen-run separators. Each
detector below marks a segment `pasted`; the text the subject typed around it stays own.
The subsections are grouped by subject, not by run order. The order in
`voice.classify_subject_text` is: paste tag, quote-back, harness template, terminal,
structural score (each per segment, first match wins); then, on a turn of 1,500+
characters, the document pass (`paste:document`, `paste:quote_back_earlier`); then the
code and machine pass; then the dictation score. A later pass only reads what earlier ones
left own.

### 5.1 Quote-back (`paste:quote_back`, `paste:quote_back_earlier`)

**Assumption.** Text that repeats the assistant's words is the assistant's words.

- **Default**: a segment of 10+ words with half or more of its word 6-grams in the preceding
  assistant turn; on a turn of 1,500+ characters, a block with half its 6-grams in ANY earlier
  assistant turn.
- **Switch**: not configurable (`VoiceSettings.quote_back_threshold`,
  `quote_back_min_words`, `document_split_min_chars` exist but no config key sets them).
- **Who might change it**: nobody, for citation purposes. A subject who adopts an
  assistant's sentence as their own still cites the turn where they said it in their own
  words. Quote-back is never eligible for the own-writing rule (§6).
- **Verify**: count `paste:quote_back*` rows; read a sample against the prior assistant turn.

### 5.2 Paste tags (`paste:tag`)

**Assumption.** A client's paste placeholder (`[Pasted text #n +N lines]`) and the content a
prompt-history entry attaches to it are pasted. Exact.

- **Default**: on. **Switch**: not configurable. **Verify**: count `paste:tag` rows.

### 5.3 Structural paste score (`paste:structural`)

**Assumption.** A segment carrying several signals a person typing into a chat box does not
produce (email headers, a greeting addressed to the subject, a sign-off, chat-client
timestamps, markdown structure, fences, log lines, code openings) is pasted.

- **Default**: pasted at a score of 2 or more.
- **Switch**: `subject_names` (a greeting addressed to one of these names scores as pasted;
  the same key sets the referent, §10.3); `typography_is_paste` (default false: em-dashes and
  curly quotes count as paste signals, for a subject who never types them);
  `extra_typos` (the subject's habitual misspellings, which count as typing, not pasting).
  The threshold itself (`paste_score_threshold`) has no config key.
- **Who might change it**: a subject whose own writing is heavily formatted (markdown notes,
  signed emails they composed) will see some of it marked pasted; the remedy is the
  allowlist (§6), not a lower threshold.
- **Verify**: count `paste:structural` rows; read the ones with the lowest `score`.

### 5.4 Harness templates (`paste:harness_template`)

**Assumption.** Text matching the string literals of the subject's own prompt-building
scripts is a script's prompt, not typing.

- **Default**: off until roots are configured.
- **Switch**: `harness_template_roots`, `harness_template_exclude_dirs`.
- **Verify**: count `paste:harness_template` rows.

### 5.5 Pasted terminal sessions (`paste:terminal`)

**Assumption.** A segment whose lines are mostly machine output (prompts, tracebacks,
box-drawing frames, logs, git and test output, in raw or escaped form) is pasted. Prose
typed directly above or below the paste stays own.

- **Default**: 3+ machine lines making up 40% of the segment, or 12+ machine lines, or any
  ANSI escape.
- **Switch**: not configurable separately; see §5.7 for the subject who wants code and
  machine output kept.
- **Verify**: count `paste:terminal` rows.

### 5.6 Pasted documents in long turns (`paste:document`)

**Assumption.** On a subject turn of 1,500+ characters, a block with signals a chat box does
not produce (carriage returns, tab-separated rows, dated lines, code, legal or boilerplate
register, mangled encoding, headings over a list) is a pasted document.

- **Default**: on, at a block score of 3 with at least one hard signal.
- **Switch**: not configurable (`document_split_min_chars`, `document_score_threshold` have
  no config key). Pasted documents that are the subject's own writing are recovered by the
  own-writing rule (§6).
- **Verify**: count `paste:document` rows, and rows with basis `allowlist:own_writing_pasted`.

### 5.7 Code and machine output (`paste:code_or_machine`)

**Assumption.** Code and machine output inside the subject's own typed turn is not the
subject's words, even when the subject typed it. Marked line by line, after every other
rule, only in text the other rules left own:

- code, commands, markup, URLs, file names and paths, data in machine formats;
- compiler and runtime messages, including those worded in English, anchored on structure
  (a `line:col` position or an error prefix together with an identifier), never on a word
  alone, so "i got an error at 10:30" stays own;
- TeX build-log residue, chat-client headers (only a display name and a clock time),
  coding-agent status lines, and web-page menu chrome (only when two or more menu lines
  sit together);
- comment lines join code only when a code line is directly adjacent (an indented `//`
  comment is code on its own), so a markdown heading or a note typed between sentences
  stays own.

The unit is the line. Inline code inside a sentence stays own; a same-line lead-in ("run
this: pip install x") stays own; a machine line with typed words appended on the same line
moves whole.

- **Default**: on, for typed sources only (speech sources carry no pastes).
- **Switch**: `detect_code_machine` in the import config (default true). Off, code and
  machine output inside typed turns stays `own_typed` and can be cited.
- **Who might change it**:
  - **A developer subject** whose way of writing code is part of how they think and decide:
    turn it off, so code is citable.
  - **A subject whose code is someone else's** (pasted from documentation, generated by an
    assistant): keep it on. This is the default because most pasted code in a chat corpus
    is not the subject's composition.
  - Code as its own evidence kind (kept citable, but tagged so distillation can include or
    exclude it separately, the way `record_only` facts are handled in §10.1) is
    **DESIGNED, not built**. Today the choice is binary: on (code is context) or off (code
    is own, and the gate's evidence-kind rule will usually classify a code span as
    `record`, since its alphabetic share is low).
- **Verify**: with the switch on, count `paste:code_or_machine` rows and characters per
  source; with it off, that count is zero and the same characters appear in own rows.
  `tests/test_data_treatment_switches.py` shows both outcomes through the importer.
  Measured behaviour on one corpus (typed turns, line-level, held-out labelled sample, one
  labeller who also wrote the rules): recall of code and machine lines about 0.77
  (bootstrap 95% 0.66 to 0.88) against 0.39 before the recall pass, precision about 0.96
  (0.89 to 1.00). Most of the added moves on that corpus were one pasted forum thread's
  menu chrome; with that thread removed, recall went from about 0.57 to about 0.76. No
  typed prose or journal row moved in the held-out sample (0 of 96). Known misses: forum
  usernames and timestamps, some English-worded tool messages with no identifier, data rows
  in tab-separated tables (left alone on purpose: a subject's typed journal rows have the
  same shape). A line where the subject retypes an error message after a lead-in ("it
  says ... at 64:21") moves whole, lead-in included.

## 6. The own-writing allowlist

**Assumption.** Pasted text can be the subject's own writing (a draft, a journal, an email
they wrote elsewhere). By default it is excluded and counted.

- **Default**: excluded.
- **Switch**:
  - `paste_allowlist`: turn ids re-classed `own_typed` one at a time (basis
    `config:allowlist(<detector>)`). Works on a row from ANY paste detector, including
    `paste:code_or_machine`, and is re-applied to stored rows on every import.
  - `allowlist_own_writing_pasted` (default false) with `own_writing_min_traits` (default
    3): a `paste:document` segment whose per-line typing traits (typos, configured
    misspellings, apostrophe-less contractions, a lowercase "i", a space before
    punctuation) sum to the minimum is re-classed `own_typed`, basis
    `allowlist:own_writing_pasted`, with a `practice` tag (`trading_journal` or
    `own_document`). Only `paste:document` is eligible: quote-back matches assistant text by
    construction, and the other detectors also catch third-party material.
- **Who might change it**: a subject who pastes their own journals or drafts into chats.
  A subject with carefully edited writing (few typing traits) will not be caught by the
  trait rule and needs the manual list.
- **Verify**: count by `basis`; verification (`VERIFY_SPEC.md`) flags claims whose cited
  facts all come from one practice (`bounded:<practice>`).
- **Note**: code and machine lines inside an allowlisted document are not split out; the
  code pass never reads a segment another rule has claimed.

## 7. Dictation

**Assumption.** Typed text with dictation artifacts (spaces before punctuation, censored
words, long unpunctuated runs, mid-sentence capitals) was spoken. It stays citable; the
class records how it was produced.

- **Default**: a typed turn is re-classed `own_dictated` (basis `text:dictation_score`) at a
  score of 3. The score reads only the turn's own text, after pastes and code are removed.
  Audio-transcribed ChatGPT messages are `own_dictated` by source (basis
  `source:audio_transcription`) and are not scored.
- **Switch**: `extra_typos` and `typography_is_paste` feed the score. The threshold
  (`dictation_score_threshold`) has no config key.
- **Who might change it**: a subject who never dictates, or always does, would want the
  score off. That is not configurable today; since both classes are citable, the effect is
  only on how facts are labelled, not on what can be cited.
- **Verify**: count `basis = 'text:dictation_score'`.

## 8. Meetings

**Assumption.** In a meeting transcript (`HH:MM Speaker Name: text` lines), only lines under
the subject's configured speaker label are the subject's words; every other speaker is
`other_person`. Headers and notes sections are not turns.

- **Default**: with no label configured, every line is `other_person`.
- **Switch**: `meeting_subject_labels`.
- **Who might change it**: every subject with meeting transcripts must set it; a subject
  whose label varies across tools lists every variant.
- **Verify**: the import prints `subject_lines` and `other_lines` per file; count
  `basis = 'config:meeting_subject_label'`.

## 9. Sources with less evidence

### 9.1 Prompt history (`claude_code_history`)

**Assumption.** A history entry is a prompt the subject submitted. History carries no
assistant turns, so quote-back cannot run and there is no context for a short reply.

- **Default**: prompts are imported as subject turns; a prompt already present in a full
  transcript (8+ words, same normalised text) is marked `duplicate_of` that turn and is
  never citable; command entries are dropped; paste placeholders become forced pasted spans.
- **Switch**: `exclude_sources: ["claude_code_history"]` removes the source.
- **Verify**: count `duplicate_of IS NOT NULL` per source.

### 9.2 Database copies (`claude_code_db_copy`)

**Assumption.** Sessions that survive only in an older database carry their stored role and
nothing else; the source flags were discarded. The role is trusted, the text detectors run on
the stored text, and two record-level signals replace the lost flags (history corroboration,
basis `db_copy:role+history`; repeated never-submitted prompts, §3).

- **Default**: imported; conversation flags record `provenance` and
  `truncated_at_first_import`.
- **Switch**: `exclude_sources: ["claude_code_db_copy"]`.
- **Who might change it**: a subject who wants only raw transcripts behind their
  specification.
- **Verify**: count by `basis` (`db_copy:role` vs `db_copy:role+history`) and read the
  conversation flags.

### 9.3 Text files (`text_file`)

**Assumption.** Whoever imports a text file asserts it is the subject's own writing. The
whole file is one `own_typed` turn with basis `source:text_file_assertion`; no paste
detector runs on it.

- **Default**: every `.txt`, `.md`, `.docx`, `.rst` file under the given path.
- **Switch**: `exclude_path_globs`, `exclude_conversations`, `exclude_sources`.
- **Who might change it**: a subject importing a folder that also holds documents an
  assistant wrote must exclude those by path.
- **Verify**: count `basis = 'source:text_file_assertion'`; list their titles.

## 10. At the gate (extraction)

### 10.1 Record spans vs prose spans

**Assumption.** A span whose alphabetic word tokens are under half its tokens, or that has a
layout signal (a tab, column gaps, a leading date) and an alphabetic share under 0.75, is a
`record` (a trade row, a table row, a code line), not prose. A fact whose every span is a
record is stored with grounding `record_only`, kept, counted, and excluded from
distillation by default.

- **Default**: excluded from distillation.
- **Switch**: `--include-record-only` on `distill.py`, `distill_batch.py`,
  `convergence.py`. The thresholds (`RECORD_MAX_ALPHA_SHARE`,
  `RECORD_DATED_MAX_ALPHA_SHARE` in `turn_contract.py`) are not configurable.
- **Who might change it**: a subject whose practice lives in records (a trader's journal, a
  lab notebook, a developer's code with `detect_code_machine` off).
- **Verify**: the run record's `record_only` count; the tree stamp's
  `record_only_facts_excluded` / `_included`.

### 10.2 Span bounds

- **Default**: 3 words minimum, 400 characters maximum per evidence span.
- **Switch**: `BASELAYER_TURN_SPAN_MIN_WORDS`, `BASELAYER_TURN_SPAN_MAX_CHARS` (per run,
  written to the run record).
- **Verify**: `span_length` rejections in the run record.

### 10.3 Referent, subject check, object check

**Assumption.** The configured names, plus "this person", "the person", "the user" and
"user", all mean the subject. A fact grounded only in own-voice spans whose subject is
another person keeps that subject only if the name appears in a span; otherwise it becomes
the subject. A fact with the subject in its object slot and as its subject is rejected
(`self_object`).

- **Default**: turn-mode extraction refuses to start with no names configured.
- **Switch**: `subject_names`.
- **Who might change it**: every subject; list every form the extractor may emit.
- **Verify**: the run record's `subject_referent`, `subject_reassigned`,
  `subject_reassigned_from` and `self_object` counts.

## 11. Redaction, exclusions and canaries

- **Secret redaction (always on, not configurable).** Every row's text and every title is masked for provider key shapes,
  JWTs, private keys, URL credentials, token values in a key context, password lines,
  Luhn-valid card numbers and SSN layouts, whatever the voice class, because context turns
  reach the extraction model too. Counts go to `import_redactions`. A secret written as prose
  is not caught.
- **Exclusions** (`exclude_conversations`, `exclude_sources`, `exclude_path_globs`) are
  configurable, but an unknown config key raises instead of being ignored.
- **Injection canaries** (`canary_strings`, none shipped): a session whose hook context
  carries a configured marker is flagged `injection_canary`. The flag does not change any
  row's class.

## 12. Not yet configurable, and what adding it would take

| behaviour | today | smallest change |
|---|---|---|
| paste, quote-back, dictation and document thresholds | constants on `VoiceSettings` | add a config key per field, the way `detect_code_machine` was added |
| dictation re-class | always on for typed sources | a `detect_dictation` config key passed through `voice_settings()` |
| code as its own evidence kind | not built | an `evidence_kind` `code` at the gate and a distillation opt-in, parallel to `record_only` |
| per-source detector choices | one setting per corpus | a per-source override map in the import config |

Any new switch needs a test that fails before it exists and shows both outcomes through the
importer, as `tests/test_data_treatment_switches.py` does for `detect_code_machine`.
