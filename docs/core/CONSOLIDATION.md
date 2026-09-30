# Consolidation: `baselayer consolidate`

Status: `BUILT` (2026-09-29; builders 2026-09-30). Code exists and is tested; nothing serves its output yet. `baselayer consolidate` calls no model. The three builders that make its inputs do (see Builders).

Consolidation runs after authoring. It turns an authored specification (the three layer JSON files) into what an agent is served:

- the **always-on** claims in full, on every message;
- **trigger categories**: each category lists its trigger lines, and each line ends with the ids of the claims it covers;
- an **index JSON** the pull tool reads: claim id to full claim text, fact ids, and contested note.

The agent reads the categories, decides which situations apply, and pulls those claims by id. This layout replaced the unified brief as the served form. It was the layout chosen by the 2026-09-29 layout eval.

The raw layers stay the record. No stage rewrites a claim. Duplicates are recorded as a mapping, and merged wording is a separate optional step that this package does not produce.

## Command

```
baselayer consolidate <spec_dir> --out <dir> [--stages claims,overlap,dedupe,always_on,triggers,categories,render,checks]
    [--grouping grouping.json] [--categories assignment.json]
    [--subject NAME] [--possessive his|her|their] [--templates overrides.json]
    [--dedupe-basis evidence|judgements|external] [--jaccard-min 0.5] [--judgements FILE] [--dedupe-map FILE]
    [--always-on-rule literal|fire_rate|explicit] [--always-on-phrases "A;B"] [--fire-rates FILE] [--fire-threshold 0.8]
    [--thin-claims 3] [--thin-facts 10] [--judge-tasks]
```

The command reads the spec dir and writes only `--out`. `--out` may not overlap the spec dir or an input file. It also may not sit inside any Base Layer data directory (one holding `identity_layers/` or `database/memory.db`). No corpus database is opened; every count comes from the layer JSON. The command exits 1 when any check fails.

## Stages

Each stage is a function from JSON files to one JSON file. Any stage can be rerun alone, or replaced by another implementation that writes the same file. `--stages` runs a subset in pipeline order, reading earlier outputs from `--out`.

| Stage | Reads | Writes | What it does |
|---|---|---|---|
| `claims` | spec dir | `claims.json` | Loads the layers. Renders each claim's served block: `## id NAME[  (CONTESTED)]`, statement, `*Active when:*`. Compares the block with the one in the layer's `.md`. |
| `overlap` | `claims.json` | `overlap.json` | Lists claim pairs that share cited fact ids, with Jaccard. `--judge-tasks` also writes the blind SAME / FACET / DISTINCT prompts (`judge_tasks.json`) and sends nothing. |
| `dedupe` | `claims.json`, `overlap.json`, [judgements or map] | `dedupe.json` | Maps each claim to one duplicate group. Bases: shared-evidence Jaccard, judge verdicts (SAME in both orders by default), or an external mapping. |
| `always_on` | `claims.json` | `always_on.json` | Selects the standing claims. `literal` uses the pre-registered textual rule (the condition opens with Always / All communication / Any communication / Any message / Any written message / Task requests across any domain / Nearly all replies). `fire_rate` uses one measured rate per claim at or above a threshold (the 9/28 pre-registration required 0.80 from an arm and from its reference pass, so combine the two first). `explicit` takes a list of ids. |
| `triggers` | `claims.json`, `always_on.json`, [grouping] | `triggers.json` | Groups Active_When clauses into triggers, many-to-many to claims. The grouping is an input file, usually a hand grouping. With none, each distinct whole condition is one trigger. |
| `categories` | `claims.json`, `triggers.json`, [assignment] | `categories.json` | A trigger's category is the majority category of its member claims. On a tie it takes the category of the claim its wording comes from. Reports coverage per category (triggers, claims, distinct facts) and flags thin and empty categories. |
| `render` | the above, `dedupe.json` if present | `served.txt`, `served.stamp.json`, `index.json` | Writes the served text (UTF-8, LF) and the pull index. Categories with no trigger are left out of the text. |
| `checks` | everything, and the spec dir again | `checks.json` | Runs the checks below. A check that cannot run fails; it is never skipped. |

### Rules the triggers stage enforces through the checks

These are ported from the 9/29 trigger index.

- A clause is an exact substring of its claim's authored Active_When. `*` means the whole condition.
- A trigger's wording is one member's clause, verbatim, with the first letter capitalised. No situation is invented.
- Always-on claims are not hung off any trigger.

### Checks

| Id | Check |
|---|---|
| K01 | `claims.json` matches the layer JSON re-read now (text, conditions, fact ids, flags, file hashes). |
| K02 | Each layer's `.md`, when present, carries the same served block as its JSON. |
| K03 | Every clause is an exact substring of its claim's Active_When. |
| K04 | Every trigger wording is verbatim text of its source claim's condition, and the source is a member. |
| K05 | Every claim is either always-on or pulled by at least one trigger. |
| K06 | Always-on claims exist and are not on any trigger. |
| K07 | Trigger ids are unique, and no (claim, clause) edge repeats. |
| K08 | No content-bearing span of a triggered claim's condition is left uncovered by its clauses. |
| K09 | Every trigger has exactly one category from the set, and the coverage counts recompute. |
| K10 | Claim text is unchanged: every index entry equals the block rendered from the layers, and, independently of that renderer, opens with the claim's header and carries its name, statement and condition verbatim. |
| K11 | Fact ids are preserved, per claim and as a union. |
| K12 | The served text's hash matches the index, always-on blocks and trigger lines are present, and every served id resolves. |
| K13 | Dedupe is a partition of the claims, with no rewritten text. |
| K14 | Every output carries a complete stamp, and the served stamp's hash matches the served text. |

## Stamps

Every JSON output carries `stamp`, and `served.txt` has its stamp in `served.stamp.json` so the text itself stays byte-comparable. A stamp holds:

- `stage` and `run_id`;
- `git_commit` (with `-dirty` when `src/` has uncommitted changes) and a repo-relative `code_path`;
- `code_sha256`, a content hash of every module in the package, which stays meaningful when git is dirty;
- `inputs`, `inputs_hash`, `params`, and `model_calls: 0`.

An input's hash is taken over its content without its stamp. Two runs over the same inputs therefore have the same `inputs_hash`, and only `run_id` and `created_at` differ.

## Inputs from outside the package

- **Grouping**: `{"triggers": [{"key", "wording_source": {"claim", "clause"}, "members": [{"claim", "clause"}]}]}`. It comes from a hand grouping or from any `TriggerGrouper`, including the trigger grouper builder.
- **Category assignment**: `{"categories": [{"id", "name", "members": [claim ids]}], "trigger_overrides": {key: category id}}`. Categories are data, not a fixed vocabulary. The category builder writes this shape, with a `description` per category that the stage ignores.
- **Judgements**: a JSON list or JSONL of `{"a", "b", "label"}`, or a stamped document with a `judgements` list (what the duplicate judge builder writes), from any `PairJudge`. `consolidate` runs no judge.
- `python -m baselayer.consolidation.port` converts the 9/28-29 prototype files into these shapes: the trigger index into a grouping, and the merge preview groups into an assignment and a dedupe map. The trigger index's stored categories are dropped, so the categories stage has to recompute them.

These inputs hold one person's claim ids, clause text and category names. They belong beside that person's working files, never in this repository.

## Acceptance

The acceptance test is `tests/test_consolidation_acceptance.py`. It runs only when `BASELAYER_CONSOLIDATION_ACCEPTANCE` names a config file outside the repo.

On 2026-09-29 the inputs were one authored specification, its hand grouping of triggers and its hand category assignment. From these the command reproduced, byte for byte, the served text that the layout eval had served (the sha256 matched the one the eval recorded). Every trigger category was recomputed to the hand values, and 14 of 14 checks passed.

## Builders

The three inputs above were made once, by hand, for one specification. A re-author changes claim ids and conditions, so they have to be made again for every spec version. Three builders do that. Each is a separate stage behind the existing interface, JSON in and JSON out, stamped like the stage outputs, and each can be replaced by a hand-made file of the same shape.

```
python -m baselayer.consolidation.build judge      --claims claims.json --overlap overlap.json     --out judgements.json --work DIR ...
python -m baselayer.consolidation.build group      --claims claims.json --always-on always_on.json --out grouping.json   --work DIR ...
python -m baselayer.consolidation.build categorize --claims claims.json --triggers triggers.json    --out categories.json --work DIR ...
```

| Builder | Interface | What the model sees | What is checked mechanically |
|---|---|---|---|
| `judge` (`judge.py`) | `overlap.PairJudge` | Statement and Active_When of both claims, with no id, name or layer. Both presentation orders, never in one call, 8 items per call, shuffled by seed. The prompt is the 9/28 prototype's, byte for byte (`overlap.judge_prompt`). | A reply is kept only as a list of the right length, with labels in SAME / FACET / DISTINCT and items in order. A call that keeps failing leaves its pairs listed as unjudged. |
| `group` (`grouper.py`) | `triggers.TriggerGrouper` | Step 1 (split): conditions only, 20 per call, under neutral ids. Step 2 (group): every clause once, under neutral ids; the reply is ids only. | A clause is stored as the slice of the condition it locates, so it is a substring by construction. A split that leaves a content span uncovered (the K08 test, same function) falls back to the whole condition. Lines the reply leaves out become their own triggers. Every fallback and repair is recorded. |
| `categorize` (`categorize.py`) | the category assignment file | Each trigger's wording and the other clauses under it, under neutral ids. | Every trigger gets an override, and claim members stay a partition. A trigger the reply leaves out goes to an `Unplaced` category flagged for review. Coverage per category (triggers, claims, facts) and the thin flags come from running the categories stage itself. |

The judge's candidates are the overlap stage's pairs, the ones that share cited facts. On the specification measured, they held under a third of the pairs the 9/28 prototype judged SAME in both orders; the prototype found the rest through embedding neighbours, which this package does not compute. `--pairs` adds candidates from any other source.

The category builder asks for between n/10 and n/3 categories (at most 30) for n triggers, unless `--min-categories` and `--max-categories` are given. The category count therefore follows the trigger count.

**Backends.** A builder never calls a model directly. It hands its calls to a runner (`backends.py`) that uses one of three backends.

- `api` is the Anthropic API and the package default (model `claude-opus-5`). The run is priced before any client exists, from `distillation/spend.py`'s dated table, which the operator confirms (`--rates-confirmed`) or overrides (`--rate-in`, `--rate-out`). It is refused without a ceiling (`BASELAYER_SPEND_CEILING_USD`, or `--confirm-spend` at or above the estimate), and each call is checked against the ceiling before it is sent. `--plan-only` prints the price and calls nothing. The estimate assumes chars/3.5 input tokens and 6,000 output tokens per call, so treat it as a floor.
- `cli` is `claude -p` on the local subscription ($0). The child runs with no API credential in its environment, `BASELAYER_SPEC_INJECT=0`, hooks and auto memory off, `--safe-mode`, an empty strict MCP config, no tools, no session persistence, and a cwd outside every project tree. A context probe of the actual child runs first and is stored in `--work` (one file per run). The run is refused unless the probe is clean against the spec-injection canary and any `--canary`. The probe does not make a run blind: the child can still see the account's user details, which name the person.
- `fake` is used by the tests. It makes no model call.

**Checkpoints.** Every reply that parses is written to `<work>/calls.jsonl` before it is used, so rerunning the same command resumes. A changed prompt under the same key is refused. A usage or rate limit is never recorded. The run backs off on a schedule shared by all workers, and if the limit persists it exits 3 with the checkpoint intact.

**Stamps.** A builder output's stamp has the stage stamp's fields, plus `model_calls` (new and replayed), the models that answered, and the backend's provenance: for `cli` the probe result, for `api` the estimate and the spend. The package's `code_sha256` covers the builder modules too, so it changed with them. The 9/29 acceptance run's `0497d10f...` identifies that run's code, not the current one.

**Measured on one real specification** (2026-09-30, subscription, Opus 5.5 answered every call, each builder run twice with different seeds):

- **Judge**: stable at the level of the prototype. Run against run, Cohen's kappa 0.78. Each run against the prototype's verdicts, kappa 0.68 and 0.69. Agreement between the two orders of a pair, kappa 0.77 and 0.70, against 0.66 for the prototype's verdicts on the same pairs.
- **Categories**: moderately stable. On the hand triggers, run against run, ARI 0.55. Each run against the hand categories, ARI 0.41 and 0.50. The prototype's higher agreement was measured on whole conditions, a different unit.
- **Trigger grouper**: not stable. The two end-to-end runs made very different numbers of triggers, both well above the hand grouping's. Claim-pair co-membership kappa was 0.44 between the runs and about 0.5 against the hand grouping. Every trigger check passed on both. Run alone, twice, on the hand grouping's clauses, the group step agreed with itself (ARI 0.83). Run twice on one end-to-end run's finer clauses, it did not (ARI 0.28). So the group step is stable on a coarse line set and unstable on the fragmented sets the split step produced, which split about twice as many conditions as the hand pass.
- **Served text**: 14 of 14 checks passed on both end-to-end runs. Both texts were longer than the hand-built one.

## Not built

- Merged wording.
- Candidate pairs by meaning (embedding neighbours) for the judge.
- A trigger grouper stable enough to ship. The builder exists and its output passes every check, but two runs disagree (see Builders).
- Wiring into the MCP server. `get_brief` and the resource still serve the old shape.
- Applying reviewer corrections. The served text carries claim text exactly as authored, so corrections recorded outside the layers (for example reviewer annotations) do not appear until the layers are re-authored or a corrections input is designed.
