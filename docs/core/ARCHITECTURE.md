# System Architecture
## Base Layer: An Interpretive Layer Above Memory
**Updated 2026-10-19.** How the code is organised: which module does what, what each step reads
and writes, and which tables hold the results. For every command, option and stop condition in
order, read [../PIPELINE.md](../PIPELINE.md); when this file and `baselayer <command> --help`
disagree, `--help` is right. Terms used in a fixed sense are defined in
[../DEFINITIONS.md](../DEFINITIONS.md).

---

## The problem

Memory systems for AI (Mem0, Letta, Supermemory, Zep and others) are built and benchmarked for
recall: given a query, return the stored facts that answer it. What they do not represent is
interpretation: how a specific person reads facts and experiences into judgments, decisions and
reactions. The same facts can support different conclusions depending on whose way of reasoning
reads them. An agent acting for a person needs that reading, not only the facts.

Provider-side user models are opaque, not portable and not inspectable. A longer context window
does not supply the reading either: raw history is retrieval, not interpretation.

## What Base Layer produces

Base Layer reads a person's own text (chat exports, journals, notes, essays) and writes a
**specification**: three layers of claims about how that person reasons, communicates and tends to
respond. Each claim has an id, a body, an `Active when` line and the ids of the facts it rests on.

| layer | what it holds |
|---|---|
| **ANCHORS** | the certainties the person reasons from |
| **CORE** | how they communicate, and the context to read them in |
| **PREDICTIONS** | given a kind of situation, how they are likely to respond |

The three layers are the specification. A single prose brief can be composed from them on request;
it is optional, off by default, and `baselayer run` never writes it. The specification is plain
text, locally owned and provider-agnostic, and every claim can be traced to facts in the local
database.

---

## Two paths

There are two ways to build a specification. They share import and extraction and diverge after
it. The full step table is in [../PIPELINE.md](../PIPELINE.md#1-two-paths).

```
                      import  (import_conversations.py, turn_import.py)
                         |
                      extract (extract_facts.py, batch_extract.py)
                         |
        +----------------+------------------------------+
        |                                               |
  baselayer run (static path)                 cited path (experimental)
        |                                               |
  coverage gate (chunk ledger)                distill      (distillation/distill.py)
        |                                               |
  author  (author_layers.py, Sonnet 4.6)      assemble     (distillation/assemble.py)
        |                                               |
  traceability: tier, embed, vector           author-from-package
  provenance, tension check (Haiku 4.5)         (distillation/author_from_package.py, Opus 5)
        |                                               |
  data/identity_layers/*_v4.md                <outdir>/<layer>.md + <layer>.json
        |                                               |
  served by mcp_server.py                     verify-spec  (verification/)
                                                        |
                                              consolidate  (consolidation/)
                                                        |
                                              served.txt, index.json (not served by this package)
```

| | `baselayer run` | the cited path |
|---|---|---|
| extraction | legacy (whole conversations in chunks) by default; the turn contract when `BASELAYER_TURN_CONTRACT=1` is set | `baselayer extract --turn-contract`: every fact quotes the person's own words, checked by a gate in code |
| authoring input | a selection of facts made by SQL, capped per category | every active fact, each given one recorded verdict by distillation |
| citations | asked for, not required | required by schema; ids not in the package are stripped and counted |
| verification and trigger index | not run | `verify-spec`, `consolidate` |
| served over MCP | yes | no |

`baselayer pipeline` is a separate command for a subject already in the subject registry and is
not one of the two paths.

---

## Data root and isolation

Every command reads and writes under one data root: `MEMORY_SYSTEM_ROOT` when set (the directory
must already exist). Unset, it is `~/.baselayer` for a package installed from the GitHub URL, or
the clone itself (under its `data/`) when the code runs from a clone of this repository
(`config._resolve_project_root`). It is never the current directory. Code is shared; only data changes. `baselayer init` creates
`<root>/data/database/memory.db` and writes `<root>/data/entity_map.json` (the person's name and
pronouns), which extraction reads to resolve who a fact is about. Use a fresh data root per corpus,
and always for the turn contract. Detail: [../PIPELINE.md](../PIPELINE.md#2-the-data-root).

A second local file, the import config (`BASELAYER_IMPORT_CONFIG`, else
`<root>/data/import_config.json`), holds everything specific to one person: `subject_names`,
exclusions, the paste allowlist, meeting speaker labels, detector switches and injection canaries.
Turn-mode extraction refuses to start while `subject_names` is empty. Every key is listed in the
docstring of `src/baselayer/import_config.py`. It is personal data and belongs beside the corpus,
never in a repository.

---

## Import

**Modules:** `import_conversations.py` (sources, deduplication, the legacy `messages` table),
`turn_import.py` and `turns.py` (the `turns` table), `voice.py` (voice-class detectors),
`redaction.py` (secrets masked by shape), `history_align.py` (Claude Code `history.jsonl` against
transcripts), `import_config.py`.

Sources (`baselayer import --source`, detected when omitted): ChatGPT export, Claude.ai export,
Claude Code sessions, Claude Code `history.jsonl` (`--source history`, prompts only; import the
transcripts first), journal folders, text files and folders, meeting transcripts (`--source
meetings`, which needs `meeting_subject_labels` in the import config).

| table | what it holds |
|---|---|
| `conversations` | one row per conversation or document |
| `messages` | one row per message or text chunk; read by legacy extraction |
| `turns` | one row per turn, or per segment when a turn of the person's contains pasted material: speaker (from the source's own role field, never inferred by a model), voice class, the detector that classed it, text |
| `import_state` | per conversation: content hash and revision, so a source that grew is re-marked for extraction and one that was rewritten is flagged |
| `conversation_flags`, `import_exclusions`, `import_redactions` | observations (for example an injection canary), what the config excluded, and redaction counts per kind |

Only `own_typed` and `own_dictated` turns are citable. `assistant`, `other_person`, `pasted`,
`compaction_summary`, `tool_result`, `harness_prompt` and `queued_command` are context only. The
legacy `messages` table is still written, from citable text of the person's and assistant text
only, so legacy extraction does not read summaries, tool output or pastes as the person's words.
The generic JSON importer (a `.json` file not otherwise recognised, detected when `--source` is omitted) writes `messages` only, with no turns, so its conversations cannot be
extracted under the turn contract. Detail: [TURN_CONTRACT.md](TURN_CONTRACT.md) sections 1 and 2,
[DATA_TREATMENT_POLICY.md](DATA_TREATMENT_POLICY.md).

---

## Extract

**Modules:** `extract_facts.py` (sequential extraction, AUDN, the gate, the reset),
`turn_contract.py` (turn chunking, the gate, stamps), `chunk_ledger.py` (per-chunk checkpoints),
`batch_extract.py` (Message Batches API).

Model: turn-contract extraction on Claude Haiku 5.5 at effort medium (`config.EXTRACTION_API_MODEL`,
`claude-haiku-5-5`); legacy extraction, and so `baselayer run`, on Claude Haiku 4.5
(`config.LEGACY_EXTRACTION_API_MODEL`, `claude-haiku-4-5-20251001`): on published text the newer model would not credit the writing to the person on the legacy prompt; a legacy comparison is pending.
`BASELAYER_LLM_EXTRACTION` sets both, `BASELAYER_EXTRACTION_EFFORT` the effort. Or a local
model through Ollama when `BASELAYER_EXTRACTION_BACKEND=ollama` (`config.LLM_MODEL`,
`qwen2.5:14b`; authoring still needs the Claude API).

Facts are `{subject, predicate, object, qualifier}` statements. The predicate list is
`CONSTRAINED_PREDICATES` in `config.py`: 46 entries, 45 behavioural plus an `unknown` fallback. It
is a list in the prompt, not an enforced vocabulary: `normalize_predicate()` maps known variants to
canonical forms and keeps an unmapped verb as written. Structured extraction replaced free text
after generic phrasing ("The user is interested in X") was found to inflate recurrence counts
(D-056 in [DECISIONS.md](DECISIONS.md)).

Every new fact passes through **AUDN** against the facts already stored:

| action | when |
|---|---|
| ADD | no equivalent fact exists |
| UPDATE | the new fact refines an existing one |
| DELETE | the new fact contradicts an existing one; the old row is superseded, never removed |
| NOOP | already known |

Extraction also checks each candidate against the `match_patterns` of rows in `user_corrections`
and drops a match (see [../CORRECTIONS.md](../CORRECTIONS.md)).

**Legacy extraction** (`baselayer extract`, and `baselayer run` by default) reads whole
conversations. Text over the conversation's `input_char_budget` is split on paragraph boundaries
with 500 characters of overlap (none for Claude Code sessions). The fact budget per conversation
comes from `EXTRACTION_CAPS` in `config.py`: message-count tiers and character tiers, whichever
gives more, from 10 for short text up to 200, 400 and 600 for large documents, with an absolute
ceiling of 600 (1,500 for Claude Code sessions). Each chunk asks for at most `min(50, max_facts)`
facts unless `BASELAYER_DYNAMIC_CAP` is on. Legacy facts carry no quoted evidence.

**Turn-contract extraction** (`baselayer extract --turn-contract`, `batch-extract --turn-contract`,
or `BASELAYER_TURN_CONTRACT=1`) builds chunks from whole turns, gives each chunk up to
`TURN_CONTEXT_MAX_TURNS` preceding turns (capped at `TURN_CONTEXT_CHAR_BUDGET` characters) as
read-only context, and offers only own-voice turns as citable aliases (`S1..Sk`). The model must
return verbatim `evidence_spans` with every fact. A gate in code, run after the model and outside
every exception handler, stores a fact only if every span names an own-voice turn in the chunk,
matches that turn's text after whitespace and quote-mark normalisation, and is within the length
bounds (`TURN_EVIDENCE_SPAN_MIN_WORDS`, `TURN_EVIDENCE_SPAN_MAX_CHARS`). Rejections are counted by
reason: `no_grounding`, `no_turn`, `not_own_voice`, `span_not_found`, `span_length`,
`self_object`. `BASELAYER_FACT_COUNT_MODE` sets whether the prompt carries a fact count
(`coverage`, the default, `none`, `coverage_fragments` or `capped`).

The gate proves a fact rests on words the person wrote or spoke. It does not prove the fact reads
them correctly; `verify-spec --run-model` samples that (fidelity).

| table or file | what it holds |
|---|---|
| `memory_facts` | the facts (schema below) |
| `extraction_log` | one row per extracted conversation with its fact count; a conversation with a row counts as done |
| `extraction_chunks` | the chunk ledger: one row per chunk, status `pending`, `done`, `failed`, `quarantined` or `split`, with the model that settled it |
| `extraction_runs` and `data/database/extraction_runs/<run_id>.json` | per turn-mode run: settings, stamps, rejections by reason, measured API usage, a `suspect` list |
| `fact_relationships` | edges between facts |
| `user_corrections` | correction rows (see [../CORRECTIONS.md](../CORRECTIONS.md)) |
| `memory_facts_fts` | FTS5 index over `fact_text`, used by `search` and `search_facts` |

Chunk ledger rules (retries, quarantine, which failures count, the model backlog, `baselayer
chunks`): [../PIPELINE.md](../PIPELINE.md#5-extract) and [TURN_CONTRACT.md](TURN_CONTRACT.md).

**Starting again.** The safest clean start is a new, empty data root.
`python -m baselayer.extract_facts --reset` deletes extracted facts, the extraction log, the chunk
ledger and the fact vectors, keeps imported conversations and user-corrected facts, and asks no
confirmation. `baselayer forget --all` is not a reset (the extraction log still marks every
conversation done), and `baselayer init --force` deletes nothing.

---

## Static path: author and traceability

**Modules:** `author_layers.py` (fact selection, prompts, provenance capture), `cli.py`
(`cmd_run`, `_coverage_gate`, `_run_traceability`), `verify_provenance.py`,
`detect_contradictions.py`, `spec_staleness.py`.

**Coverage gate.** `baselayer run` does not author while the chunk ledger holds quarantined chunks,
unless given `--accept-gaps`. Authored layers point to a `coverage_gaps_<run_id>.json` manifest in
their frontmatter.

**Author** (`baselayer author`, and `baselayer run`). Model: Claude Sonnet 4.6
(`config.LAYER_GENERATION_MODEL`, from `LLM_PROVIDER_CONFIG["authoring"]`). One call per layer,
each blind to the other layers and to any earlier version of the layer (D-040, D-053). Each layer
reads a fact selection made by SQL (`retrieve_anchors_facts`, `retrieve_core_facts`,
`retrieve_predictions_facts`), capped at `MAX_FACTS_PER_CATEGORY` (15) facts per category by
`cap_by_category`. On a 407-fact corpus that cap left CORE with 141 of 407 facts, cut by sort
position rather than importance; it is not a recorded decision. Distillation exists to replace
this selection with a recorded verdict for every fact. The prompts carry a domain-agnostic guard
(D-089) and a "derive only from input" rule.

Output: `data/identity_layers/anchors_v4.md`, `core_v4.md`, `predictions_v4.md`. Each file has
frontmatter (layer, generation time, version, model, provenance method, item count, coverage gaps
pointer) and the text the MCP server serves below a `## Injectable Block` marker.

**Provenance capture**, into `layer_claim_provenance`, by three methods recorded per row in
`link_method`:

| `link_method` | how the link was made |
|---|---|
| `citation_api` | facts passed as document blocks with the API's citations enabled; the returned citation locations map back to facts |
| `authoring` | `[F-xxx]` ids the model wrote in a `provenance:` line, parsed by `parse_provenance_from_layer()` |
| `vector` | when the citation path returns nothing (common for ANCHORS and PREDICTIONS, which synthesise rather than quote), `store_layer()` calls `verify_provenance.generate_vector_provenance()`, which embeds each claim and links its nearest facts. This is proximity, not a link the model made: read it as nearby, not used |

**Traceability** (`_run_traceability`, after `author` inside `baselayer run`): tiers facts by
predicate (`tier_facts_by_predicate`), runs `baselayer embed` when fewer than 90% of facts have a
vector in `memory_facts` (that embeds messages, so it does not raise the fact-vector count; fact
vectors are written during extraction), writes vector
provenance for every claim of each layer, cited or not (top N facts per claim, no similarity floor;
read every `vector` row as nearby, not used), and runs a tension check: up to 30 candidate fact pairs found by
embedding similarity, each classified by Claude Haiku 4.5 (`detect_contradictions.classify_pair_haiku`)
as contradiction, tension or consistent. The count is printed; `run` does not store the verdicts.

**Optional brief** (`baselayer compose`, or `baselayer author --compose`). Model: Claude Opus 4.6
(`config.LAYER_REVIEW_MODEL`), in `agent_pipeline.compose_unified_brief()`, with they/them
pronouns enforced (D-092) and a completeness check of required terms. Output:
`data/identity_layers/brief_v5.md` and `brief_v5_clean.md`. Not run by `baselayer run`.

**Stale marker.** `baselayer forget` writes `data/identity_layers/stale_after_forget.json`; any
layer or brief older than it is reported stale by `baselayer stats`, the MCP server log and
`get_stats`, and the served specification carries a short notice. Staleness is per file, by
modification time, so a re-author clears it for the files it rewrites. A cited-path output
directory is never marked stale.

---

## Cited path: distill, assemble, author

**Modules:** `distillation/distill.py`, `distillation/assemble.py`,
`distillation/author_from_package.py`, `distillation/quote_gate.py`, `distillation/spend.py`, plus
the module-only `distillation/distill_batch.py` (all layers' leaves in one Message Batches
request), `distillation/situation_first.py` (a design test) and `distillation/convergence.py` (a
study harness). Design, measurements and the rules the build produced:
[DISTILLATION.md](DISTILLATION.md). Commands and options:
[../PIPELINE.md](../PIPELINE.md#6-distill).

**Distill** (`baselayer distill --layer <anchors|core|predictions> --out <tree.json>`). Model:
Claude Sonnet 5 by default. Opens the database read-only and needs `memory_facts` with `id`,
`fact_text`, `predicate`, `category` and `superseded_by`. Facts are split into disjoint chunks
(`--max-facts`); each chunk is one model call, a leaf, which returns four channels:

- **themes:** what recurs, each naming the fact ids it drew on;
- **singularities:** a fact that appears once and would change the reading of the person, carried
  word for word, never paraphrased or merged;
- **contradictions:** carried, never resolved;
- **dispositions:** exactly one verdict for every fact id in the chunk.

A cited id that was not in the chunk is removed, and a singularity with such an id is dropped
whole. Themes and singularities are then collected from the leaves mechanically. Omitting
`--layer` runs `blind`, the undirected control arm, and prints a warning; the run refuses to start
when the directory for `--out` does not exist, before any model call. `--write-provenance` writes
the tree's root themes and singularities (ids `T<n>`, `S<n>`) into `layer_claim_provenance` with
`link_method='distillation'`; it is off by default.

**Assemble** (`baselayer assemble <tree.json> ... --out <package.json>`). No model call.
Stratifies the trees of one layer into one package. A package over the shard budget is split into
shards of disjoint leaf ranges and `--out` becomes a manifest; nothing is dropped.

**Author from package** (`baselayer author-from-package --package ... --outdir <dir>`). Model:
Claude Opus 5 by default (`--model`), effort `high`. One call per layer, or per shard, each blind
to the other layers. Each claim is emitted through a strict schema (id, name, statement,
`Active when`, fact ids, contested flag). Ids not in the package are stripped and counted; the
request is re-sent only when a claim is left with no valid id (or no claim is emitted). Writes
`<layer>.md`, `<layer>.json` and `<layer>.stamp.json` per layer, and a coverage gaps manifest on
every run (`--db` decides whether it records the chunk ledger as checked or as not checked); with
`--compose`, an optional `brief.md`. It writes nothing
to `layer_claim_provenance`: a cited-path claim's facts are the `fact_ids` in `<layer>.json`. The
quote gate (module only, `python -m baselayer.distillation.author_from_package --quote-gate --db
<memory.db>`) checks quoted phrases against the own-voice spans of the cited facts.

**Spend.** `distill` and `author-from-package` price the run from the dated table in
`distillation/spend.py` and refuse to start without a ceiling. `baselayer estimate` prices
extraction only, from the same table. Which commands honour which ceiling:
[../PIPELINE.md](../PIPELINE.md#12-spend).

---

## Verify and consolidate

**verify-spec** (`baselayer verify-spec <spec_dir> --label <label> --corpus <root> --out <dir>`;
`verification/`: `run.py`, `spec_io.py`, `corpus.py`, `deterministic.py`, `model_checks.py`,
`raters.py`, `pricing.py`, `definitions.py`, `context_gate.py`, `report.py`, `checks/`). Reads a
specification directory (the `<layer>.json` files when present, else the markdown, including the
static `*_v4.md` files), opens the corpus read-only and writes only `--out`. It never feeds back
into authoring. Deterministic checks run by default: citation resolution, a re-check of every
evidence span against its turn, voice, stamps, duplicates, trigger groups, grounding and practice.
Model-judged checks (support, voice, fidelity, cross-claim relations, adjudication) are built and
priced, and sent only with `--run-model`, through one of two raters: `--rater cli` (`claude -p`
children on the local subscription, API credentials removed from the child's environment, and
`--safe-mode` passed when the installed CLI supports it; otherwise it runs without it and says
so; default model alias `sonnet`) or `--rater api --model <id>` (API credits, capped by
`--confirm-api-spend`). A run is recorded blind only when a context probe of the child (`--probe`)
came back clean. Detail: [VERIFY_SPEC.md](VERIFY_SPEC.md).

**consolidate** (`baselayer consolidate <spec_dir> --out <dir>`; `consolidation/`). No model call.
Reads the `<layer>.json` files written by `author-from-package` (not the static `*_v4.md` layers)
and writes, one stamped JSON file per stage, the claims, evidence overlap, a duplicate grouping,
the always-on set, triggers and categories, then `served.txt` (always-on claims in full plus one
line per situation naming the claims to read), `index.json` (claim id to text, fact ids and
contested note) and `checks.json`. It exits 1 when any of its 14 checks fails, and rewrites no
claim text. Three optional inputs are judged by a model and built separately by
`python -m baselayer.consolidation.build` (`judge`, `group`, `categorize`), on the API (default
`claude-opus-5`, priced and capped) or `claude -p` (default alias `opus`, run with `--safe-mode`).
Detail: [CONSOLIDATION.md](CONSOLIDATION.md).

**baselayer verify** (`verify_provenance.py`) is a different, older command: a provenance audit of
the static layers (vector proximity, recurrence, cross-domain span, optional local NLI with
`--nli`). It writes `claim_verification` rows into the corpus database. The MCP `verify_claims`
tool calls the same code.

---

## Serving: the MCP server

**Module:** `mcp_server.py`. Registered with `claude mcp add --scope user --transport stdio base-layer --
baselayer-mcp`. No model call in the serving path.

The server serves only the static path's output: it reads `data/identity_layers/core_v4.md`,
`anchors_v4.md` and `predictions_v4.md` (the text below each file's `## Injectable Block` marker),
adds a usage preamble, a stale notice when one applies and a tool guide, and sends the result in
two places:

- the MCP `instructions` field, built once when the server starts. Some clients may truncate long
  instructions, so do not rely on this field alone for the full text;
- the `memory://specification` resource, rebuilt from disk on every read. This is the full text.
  `memory://identity` is a deprecated alias.

It does not serve a cited-path output directory, a brief as part of the specification, or the
consolidate output (`served.txt`, `index.json`). A cited-path specification reaches a model only
by hand (see [../../README.md](../../README.md#using-it-with-an-agent)).

| tool | what it returns |
|---|---|
| `get_brief(reason)` | the optional brief, when one was composed; otherwise a note that none exists |
| `recall_memories(query)` | facts near the query by vector similarity in `memory_facts` (written during extraction, not by `baselayer embed`), plus episodes from a conversation-summary collection when one exists |
| `search_facts(query, limit)` | keyword search over active facts (FTS5, with a LIKE fallback) |
| `trace_claim(claim_id)` | the rows of `layer_claim_provenance` for a claim id: each fact with its tier, recurrence, link method and source conversation title, and, for a fact extracted under the turn contract on a database with the `evidence_spans` column, up to three of its evidence spans (the person's quoted words, with the turn id) |
| `verify_claims(claim_id, layer)` | the `baselayer verify` checks for one claim or layer |
| `get_stats()` | database counts, tier and source breakdowns, stale status |
| `get_call_log(limit, name_filter)` | recent calls to this server |
| `get_help(topic)` | the agent reference |

`trace_claim` reads `layer_claim_provenance`, which the static path fills. On the cited path that
table holds only what `distill --write-provenance` wrote (tree themes and singularities, ids
`T<n>`, `S<n>`); claims written by `author-from-package` are traced through the `fact_ids` in
their `<layer>.json`, and their spans re-checked by `verify-spec`.

`baselayer serve enable|disable|status` toggles serving without a restart (state file
`~/.baselayer/serving_enabled`). Every call is logged to `~/.baselayer/sessions/<pid>/log.jsonl`;
`baselayer log` reads those logs.

---

## Fact schema

`memory_facts` is the central table (created by `init_database.py` and `extract_facts.py`).

```sql
CREATE TABLE memory_facts (
    id TEXT PRIMARY KEY,
    fact_text TEXT NOT NULL,         -- "{subject} {predicate} {object}"
    category TEXT,
    confidence REAL,
    source_conversation_id TEXT,
    created_at REAL,
    updated_at REAL,
    superseded_by TEXT,              -- set when superseded or hidden; rows are never deleted by AUDN
    source TEXT,
    subject TEXT,                    -- who the fact is about
    temporal_state TEXT,
    scope TEXT,
    fact_type TEXT,
    commitment_depth TEXT,
    knowledge_tier TEXT,             -- 'identity' or 'contextual', set by tier_facts_by_predicate
    predicate TEXT,                  -- from CONSTRAINED_PREDICATES, or as written
    object_text TEXT,
    qualifier TEXT,
    -- stamps, on every fact extracted by this version
    extraction_model TEXT,
    extraction_prompt_hash TEXT,
    git_commit TEXT,                 -- 'unknown' outside a git checkout
    code_path TEXT,                  -- repo-relative
    -- turn contract, set only on gated facts
    turn_contract_version TEXT,      -- a fact is gated if and only if this is set
    source_turn_id TEXT,
    evidence_spans TEXT,             -- JSON [{"turn_id", "span", ...}, ...]
    inferred INTEGER,
    voice_class TEXT
);
```

This lists the columns other modules depend on; read `init_database.py` for the full set. The
stamp and turn columns exist in every database this version creates, so their presence proves
nothing; facts extracted before they existed carry none of them. What every artifact is stamped
with: [../PIPELINE.md](../PIPELINE.md#13-stamps).

Other tables: `layer_claim_provenance` (claim to fact links, above), `claim_verification`
(written by `baselayer verify` and `verify_claims`), `user_corrections`, `fact_relationships`,
`memory_facts_fts`, `extraction_log`, `extraction_chunks`, `extraction_runs`, and the import
tables above.

---

## Embeddings

**Module:** `embed.py` (`baselayer embed`). Model: `all-MiniLM-L6-v2` (`config.EMBEDDING_MODEL`),
384 dimensions, run locally; the first run downloads it from Hugging Face. Vectors live in ChromaDB
under `<root>/data/vectors/`. Every client is built through `config.get_chroma_client()`, with
ChromaDB's anonymized telemetry off.

Two collections. `memory_facts` holds one vector per fact, written during extraction
(`extract_facts.py`, `batch_extract.py`); `recall_memories`, `baselayer verify` and vector
provenance read it. `messages` holds one vector per imported message, written by `baselayer embed`
(`embed.py`); `baselayer search` reads it. The tension check embeds facts in memory and reads
neither. Neither author takes ChromaDB as input, and the cited path does not need it, but the
static path's `store_layer()` queries `memory_facts` for vector provenance when a layer has no
citation provenance.

Collections need not share a distance space, so read it before converting a distance. Both are
created with `hnsw:space=cosine` (similarity `1 - d`). Creation does not change a collection that
already exists, and a collection with no `hnsw:space` (one created outside the package, such as a
conversation-summary collection) is at Chroma's l2 default, which `collection_space()` reports as
`l2`. Chroma's l2 distance is the squared euclidean distance, so on unit vectors similarity is
`1 - d/2`; its ip distance is `1 - dot`. Call `collection_space()` and pass the result to
`chromadb_dist_to_similarity()`, which requires it, rather than converting a distance in place. Applying the l2 formula to a cosine collection was a live defect: it passed a 0.85
gate whose true value was about 0.45.

---

## Model roles

| step | model | where it is set |
|---|---|---|
| extract, turn contract (the cited build) | Claude Haiku 5.5, `claude-haiku-5-5`, effort medium | `config.EXTRACTION_API_MODEL` (override `BASELAYER_LLM_EXTRACTION`) |
| extract, legacy (`run`) | Claude Haiku 4.5, `claude-haiku-4-5-20251001`; or Ollama `qwen2.5:14b` | `config.LEGACY_EXTRACTION_API_MODEL` (override `BASELAYER_LLM_EXTRACTION`), `config.LLM_MODEL` |
| static `author` | Claude Sonnet 4.6, `claude-sonnet-4-6` | `config._LLM_DEFAULTS["authoring"]` (override `BASELAYER_LLM_AUTHORING`) |
| `compose` (optional brief, static path) | Claude Opus 4.6, `claude-opus-4-6` | `config._LLM_DEFAULTS["review"]` (override `BASELAYER_LLM_REVIEW`) |
| tension check in `run` | Claude Haiku 4.5, `claude-haiku-4-5-20251001` | `detect_contradictions.CONTRADICTION_CLASSIFIER_MODEL`, pinned; it does not follow the extraction model |
| embeddings | `all-MiniLM-L6-v2`, local | `config.EMBEDDING_MODEL` |
| `distill` leaves (and `distill_batch`) | Claude Sonnet 5, `claude-sonnet-5` | `--model` default |
| `author-from-package` (layers and optional brief) | Claude Opus 5, `claude-opus-5`, effort `high` | `--model`, `--effort` defaults |
| `verify-spec` raters | `--rater cli`: alias `sonnet` by default; `--rater api`: the `--model` you pass (required) | `verification/run.py` |
| consolidation judges (`consolidation.build`) | API: `claude-opus-5`; `claude -p`: alias `opus` | `consolidation/backends.py`, `consolidation/build.py` |
| serving | none | |

Read the ids in code before quoting them; this table is a summary and can drift.

---

## Design decisions (key subset)

The full log is [DECISIONS.md](DECISIONS.md).

| id | decision | still applies to |
|---|---|---|
| D-040 | blind derivation: authoring reads facts only, never prior output | both authors |
| D-043 | three layers (ANCHORS, CORE, PREDICTIONS), authored separately | both paths |
| D-044 | scoped memory (personal, project, professional) | static selection |
| D-053 | regeneration never sees prior output | both authors |
| D-056 | structured extraction with constrained predicates | extraction |
| D-089 | domain-agnostic guard in authoring prompts | static `author` |
| D-092 | they/them pronouns in the composed brief | `compose` |
| D-108 | the turn contract: facts grounded in the person's own words | turn-mode extraction |

An ablation of the original 14-step pipeline (14 conditions; briefs in
[../eval/archive/ablation/](../eval/archive/ablation/)) found most intermediate processing steps
(scoring, classification, review) did not change the result, which is why the static path has the
shape it has. It predates distillation and the turn contract.

---

## Cold start

| what the person has | path |
|---|---|
| chat exports (ChatGPT, Claude) | `baselayer run <export>`, or the cited path |
| journals, notes, essays | `baselayer run <folder>`; text files are imported as the person's own words, so exclude any they did not write |
| a document corpus that is not a person (a book, a set of filings) | `--document-mode` on `extract` or `run` (`--subject` exists on `run` only); never for a person |
| nothing | `baselayer journal` runs guided prompts and stores the answers as text to extract from |

---

## File structure

```
pyproject.toml                  package config (install from the git URL; not on PyPI)
README.md                       start here
docs/PIPELINE.md                every step, in order
docs/DEFINITIONS.md             terms
docs/CORRECTIONS.md             how corrections move through the system
docs/core/                      architecture, decisions, design principles, turn contract,
                                distillation, verify-spec, consolidation
docs/eval/                      evaluation frameworks and historical reports
examples/                       example specifications (zitkala_sa/ is the cited one)
recipes/                        task recipes for agents
src/baselayer/
  cli.py                        the baselayer command
  config.py                     paths, models, caps, predicate list
  init_database.py              schema
  import_config.py              the per-person import config
  import_conversations.py       importers, legacy messages
  turn_import.py, turns.py      the turns table
  voice.py                      voice-class detectors
  redaction.py                  secrets masked by shape at import
  history_align.py              Claude Code history.jsonl against transcripts
  extract_facts.py              sequential extraction, AUDN, gate, reset
  turn_contract.py              turn chunking, the gate, artifact stamps
  chunk_ledger.py               per-chunk extraction ledger
  batch_extract.py              Message Batches extraction
  embed.py                      vectors
  author_layers.py              static author, provenance capture
  agent_pipeline.py             optional brief (compose)
  detect_contradictions.py      tension check
  verify_provenance.py          baselayer verify, vector provenance
  spec_staleness.py             the stale marker after forget
  mcp_server.py                 MCP server
  agent_guide.py                the get_help reference
  api_client.py, llm_provider.py  API calls, retries, providers
  checkpoint.py                 extraction quality report
  assemble_brief.py             backs the archived brief and chat commands
  ui.py                         local browser UI (baselayer ui)
  distillation/                 distill, assemble, author_from_package, quote_gate, spend,
                                distill_batch, situation_first, convergence
  verification/                 verify-spec: run, spec_io, corpus, deterministic, model_checks,
                                raters, pricing, definitions, context_gate, report, checks/
  consolidation/                consolidate: run, spec, overlap, dedupe, always_on, triggers,
                                categories, render, checks; build, backends, judge, grouper,
                                categorize (optional model-built inputs)
tests/                          test suite (fake model clients; no test calls an API)
data/distillation_reference/    reference distillation run records
```

Per corpus, under the data root:

```
data/database/memory.db         SQLite: conversations, turns, facts, ledgers, provenance
data/database/extraction_runs/  turn-mode run records
data/vectors/                   ChromaDB
data/identity_layers/           static layers (*_v4.md), optional brief, stale marker,
                                coverage gaps manifests
data/import_config.json         the person's import config
data/entity_map.json            name and pronouns, written by init
```

---

## Serving designs not built

The current server sends all three static layers whole. An activation-matching design, which
would score specification sections against the conversation and inject only the relevant ones, is
specified in [SERVING_LAYER_SPEC.md](SERVING_LAYER_SPEC.md) with an evaluation plan in
[../eval/SERVING_LAYER_EVAL.md](../eval/SERVING_LAYER_EVAL.md). Neither is implemented. Serving a
cited-path specification, or consolidate's always-on set and trigger index, is also not in this
package.

---

## Composition with memory systems

The specification is not a memory system. It does not store dated facts or retrieve by query. It is
the interpretive layer that sits above one.

1. **Recall questions** ("What time is my flight on Friday?"): a memory system answers them; the
   specification adds little.
2. **Interpretation questions** ("Should I take the offer?", "Draft this in my voice"): retrieved
   facts underdetermine the answer, and the specification supplies the pattern that has to
   transfer. Use both.
3. **Questions the person has never engaged with**: retrieval alone tends to hedge or confabulate;
   a specification can ground an honest "they have not taken a position on this".

The format is provider-agnostic. The three layer files (or consolidate's `served.txt` and
`index.json`) can be put in any system prompt or retrieval pipeline; the MCP server is one way to
deliver the static layers, not the only one.
