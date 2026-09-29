"""Turn-contract extraction pilot: sample, price, and only then spend.

    python -m baselayer.pilot <corpus_dir> --sample 30            # select + estimate, no spend
    python -m baselayer.pilot <corpus_dir> --sample 30 --confirm-spend 3 --rates-confirmed

What it does, in order:
1. Opens <corpus_dir>/data/database/memory.db. Refuses a directory that holds served
   specification layers (data/identity_layers) or is a code checkout: a pilot builds into a
   fresh corpus directory, never into live data.
2. Selects a STRATIFIED sample of conversations that have at least one citable turn (own typed
   or dictated, not a fork copy) and are not yet extracted, stratified by source and by month.
   Deterministic for a given --seed. Planted known-bad sessions (turn_contract_fixtures) are
   kept out of the strata and, with --planted-manifest, added on top of the sample.
3. Prices the sample from the prompts the run would actually send: for each chunk with a
   citable turn, the rendered turn-contract prompt plus the JSON instruction, measured in
   characters. Every conversion from that measurement to dollars is an ASSUMPTION and is
   printed as one: characters per token, facts per chunk (the per-chunk cap, a ceiling), and
   output tokens per fact.
4. Runs only with --confirm-spend USD at or above the estimate. The cap gates the ESTIMATE;
   nothing stops the run part-way if the estimate was low.

Rates are arguments. The defaults are the published first-party rates for Claude Haiku 4.5
($1 input / $5 output per million tokens, as listed by the claude-api skill's model table cached
2026-06-24). They are defaults to be CONFIRMED, not constants to trust: running with them
requires --rates-confirmed, and a configured extraction model other than Haiku 4.5 requires the
rates to be passed explicitly.

Not in the estimate: AUDN adjudication calls (made only above the similarity threshold), retries
of failed or unparseable calls, and the embedding model (local). The estimate is for the
sequential path; the batch API bills at half these rates.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

PUBLISHED_HAIKU_45 = {"input": 1.0, "output": 5.0,
                      "source": "claude-api skill model table, cached 2026-06-24"}
DEFAULT_CHARS_PER_TOKEN = 4.0
DEFAULT_TOKENS_PER_FACT = 180


class PilotRefused(SystemExit):
    pass


# --------------------------------------------------------------------------- corpus

def corpus_db(corpus_dir) -> Path:
    root = Path(corpus_dir).resolve()
    if (root / "data" / "identity_layers").exists():
        raise PilotRefused(
            f"{root} holds data/identity_layers, i.e. served specification layers. A pilot "
            f"builds into a fresh corpus directory, never into live data.")
    if (root / "src" / "baselayer").is_dir():
        raise PilotRefused(f"{root} is a code checkout, not a corpus directory.")
    db = root / "data" / "database" / "memory.db"
    if not db.exists():
        raise PilotRefused(f"no database at {db}; run init and import into this directory first.")
    return db


def _month(created_at) -> str:
    if created_at is None or created_at == "":
        return "unknown"
    try:
        return _dt.datetime.fromtimestamp(float(created_at), _dt.timezone.utc).strftime("%Y-%m")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(created_at)[:7] or "unknown"


def citable_conversations(conn, planted_prefix: str) -> list[dict]:
    """Not-yet-extracted conversations with at least one citable turn, planted ones excluded."""
    rows = conn.execute("""
        SELECT c.id, c.title, c.created_at, c.source
        FROM conversations c
        LEFT JOIN extraction_log e ON e.conversation_id = c.id
        WHERE e.conversation_id IS NULL
          AND EXISTS (SELECT 1 FROM turns t WHERE t.conversation_id = c.id
                      AND t.voice_class IN ('own_typed', 'own_dictated')
                      AND t.duplicate_of IS NULL)
        ORDER BY c.id
    """).fetchall()
    return [{"id": r[0], "title": r[1] or "Untitled", "created_at": r[2],
             "source": r[3] or "unknown", "stratum": ((r[3] or "unknown"), _month(r[2]))}
            for r in rows if not str(r[0]).startswith(planted_prefix)]


def stratified_sample(convs: list[dict], n: int, seed: int = 0) -> list[dict]:
    """Proportional allocation by (source, month), at least one per stratum while n allows,
    largest remainder for the rest. When n is smaller than the number of strata, n strata are
    drawn at random and one conversation taken from each. Deterministic for a seed."""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for c in convs:
        strata[c["stratum"]].append(c)
    keys = sorted(strata)
    n = min(n, len(convs))
    if n <= 0:
        return []
    if n < len(keys):
        alloc = {k: 1 for k in sorted(rng.sample(keys, n))}
    else:
        alloc = {k: 1 for k in keys}
        rest, total = n - len(keys), len(convs)
        quotas = {k: rest * len(strata[k]) / total for k in keys}
        for k in keys:
            alloc[k] += min(int(quotas[k]), len(strata[k]) - 1)
        left = n - sum(alloc.values())
        for k in sorted(keys, key=lambda k: (-(quotas[k] - int(quotas[k])), k)):
            if left <= 0:
                break
            if alloc[k] < len(strata[k]):
                alloc[k] += 1
                left -= 1
        while left > 0:                      # a stratum ran out: fill from any with room
            for k in keys:
                if left and alloc[k] < len(strata[k]):
                    alloc[k] += 1
                    left -= 1
    out = []
    for k in sorted(alloc):
        out.extend(sorted(rng.sample(strata[k], alloc[k]), key=lambda c: c["id"]))
    return out


# --------------------------------------------------------------------------- estimate

def measure(conn, convs: list[dict]) -> list[dict]:
    """Per conversation: the characters of every prompt the turn path would send, and the
    per-chunk fact caps. No model call; builds the same prompts extraction builds."""
    import baselayer.extract_facts as ef
    from baselayer import turn_contract as tc
    instr = len(ef.json_instruction_for(ef.TURN_EXTRACT_SCHEMA))
    token = ef._TURN_MODE_ACTIVE.set(True)
    try:
        out = []
        for c in convs:
            turns = tc.load_turns(conn, c["id"])
            plan = ef.turn_extraction_plan(turns, c["source"])
            chunks = ef.build_turn_chunks(turns, c["source"], plan["input_char_budget"])
            live = [ch for ch in chunks if ch.has_citable]
            project = ef.is_claude_code_source(c["source"])
            chars = sum(instr + len(ef.turn_chunk_prompt(c["title"], ch, plan, project))
                        for ch in live)
            out.append(dict(c, calls=len(live), prompt_chars=chars,
                            fact_ceiling=len(live) * plan["per_chunk_cap"],
                            citable_chars=sum(len(t.text) for t in turns if t.citable)))
        return out
    finally:
        ef._TURN_MODE_ACTIVE.reset(token)


def estimate(measured: list[dict], *, input_rate: float, output_rate: float,
             chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
             tokens_per_fact: int = DEFAULT_TOKENS_PER_FACT) -> dict:
    chars = sum(m["prompt_chars"] for m in measured)
    facts = sum(m["fact_ceiling"] for m in measured)
    tin = math.ceil(chars / chars_per_token)
    tout = facts * tokens_per_fact
    return {"conversations": len(measured), "calls": sum(m["calls"] for m in measured),
            "prompt_chars": chars, "input_tokens": tin, "fact_ceiling": facts,
            "output_tokens_ceiling": tout,
            "usd": round(tin / 1e6 * input_rate + tout / 1e6 * output_rate, 4),
            "assumptions": {
                "chars_per_token": chars_per_token,
                "tokens_per_fact": tokens_per_fact,
                "facts_per_chunk": "the per-chunk cap (a ceiling; the model may return fewer)",
                "input_rate_per_mtok": input_rate, "output_rate_per_mtok": output_rate,
                "excluded": "AUDN adjudication calls, retries, re-asks; batch API bills half"}}


# --------------------------------------------------------------------------- run

def measured_usage(root, since: float):
    """The API usage the extractor recorded for the run this pilot just made: the newest
    extraction run record started at or after `since`. None when there is none."""
    d = Path(root) / "data" / "database" / "extraction_runs"
    recs = []
    for p in d.glob("*.json") if d.exists() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("started_at", 0) >= since - 1 and "api_usage" in r:
            recs.append(r)
    if not recs:
        return None
    r = max(recs, key=lambda r: r["started_at"])
    return {"run_id": r["run_id"], "totals": r["api_usage"]["totals"]}


def _default_runner(conv_ids, expected_db: Path):
    """The real run: turn-contract extraction of exactly the sampled ids, in one run record.
    Refuses if the extractor would write anywhere but the pilot's own database (it resolves
    its database from MEMORY_SYSTEM_ROOT when baselayer.config is first imported)."""
    import contextlib
    import baselayer.extract_facts as ef
    with contextlib.closing(ef.get_db()) as c:
        path = Path(c.execute("PRAGMA database_list").fetchone()[2]).resolve()
    if path != Path(expected_db).resolve():
        raise PilotRefused(f"the extractor would write to {path}, not the pilot database "
                           f"{expected_db}. Run the pilot in a fresh process.")
    os.environ["BASELAYER_TURN_CONTRACT"] = "1"
    ef.run_extraction(conv_ids=list(conv_ids))


def main(argv=None, runner=None) -> dict:
    ap = argparse.ArgumentParser(prog="python -m baselayer.pilot",
                                 description=__doc__.split("\n\n")[0])
    ap.add_argument("corpus_dir")
    ap.add_argument("--sample", type=int, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--input-rate", type=float, default=None,
                    help="USD per million input tokens (default %.2f, Haiku 4.5, to confirm)"
                         % PUBLISHED_HAIKU_45["input"])
    ap.add_argument("--output-rate", type=float, default=None,
                    help="USD per million output tokens (default %.2f, Haiku 4.5, to confirm)"
                         % PUBLISHED_HAIKU_45["output"])
    ap.add_argument("--rates-confirmed", action="store_true",
                    help="the default rates were checked against the current published price")
    ap.add_argument("--chars-per-token", type=float, default=DEFAULT_CHARS_PER_TOKEN)
    ap.add_argument("--tokens-per-fact", type=int, default=DEFAULT_TOKENS_PER_FACT)
    ap.add_argument("--planted-manifest", default=None,
                    help="planted_manifest.json from turn_contract_fixtures; its sessions "
                         "(already imported) are added to the sample and checked")
    ap.add_argument("--confirm-spend", type=float, default=None, metavar="USD",
                    help="run only if the estimate is at or below this cap")
    a = ap.parse_args(argv)

    db = corpus_db(a.corpus_dir)
    root = db.parents[2]
    os.environ["MEMORY_SYSTEM_ROOT"] = str(root)
    import sqlite3
    from baselayer import turn_contract_fixtures as F
    conn = sqlite3.connect(str(db))

    import baselayer.config as cfg
    model = cfg.EXTRACTION_API_MODEL
    explicit = a.input_rate is not None and a.output_rate is not None
    if not explicit and not str(model).startswith("claude-haiku-4-5"):
        raise PilotRefused(f"extraction model is {model}, not Haiku 4.5: pass --input-rate and "
                           f"--output-rate for it.")
    rin = a.input_rate if a.input_rate is not None else PUBLISHED_HAIKU_45["input"]
    rout = a.output_rate if a.output_rate is not None else PUBLISHED_HAIKU_45["output"]

    pool = citable_conversations(conn, F.PLANTED_PREFIX)
    sample = stratified_sample(pool, a.sample, a.seed)
    manifest = None
    if a.planted_manifest:
        manifest = json.loads(Path(a.planted_manifest).read_text(encoding="utf-8"))
        problems = F.check_import(conn, manifest)
        if problems:
            raise PilotRefused("planted sessions did not import as expected:\n  "
                               + "\n  ".join(problems))
        prow = {r[0]: r for r in conn.execute(
            "SELECT id, title, created_at, source FROM conversations WHERE id LIKE ?",
            (F.PLANTED_PREFIX + "%",))}
        sample += [{"id": r[0], "title": r[1] or "Untitled", "created_at": r[2],
                    "source": r[3] or "unknown", "stratum": ("planted", "-")}
                   for sid, r in sorted(prow.items()) if sid in manifest["sessions"]]

    measured = measure(conn, sample)
    est = estimate(measured, input_rate=rin, output_rate=rout,
                   chars_per_token=a.chars_per_token, tokens_per_fact=a.tokens_per_fact)

    by_stratum = defaultdict(lambda: [0, 0])
    for c in pool:
        by_stratum[c["stratum"]][0] += 1
    for c in sample:
        by_stratum[c["stratum"]][1] += 1
    print(f"Pilot on {root}")
    print(f"  model {model} | {len(pool)} not-yet-extracted conversations with a citable turn")
    print(f"  {'source':<14} {'month':<9} {'pool':>6} {'sample':>7}")
    for (src, mon), (npool, nsam) in sorted(by_stratum.items()):
        print(f"  {src:<14} {mon:<9} {npool:>6} {nsam:>7}")
    print(f"  sample: {est['conversations']} conversations, {est['calls']} calls, "
          f"{est['prompt_chars']:,} prompt chars (measured)")
    print(f"  ASSUMPTION {a.chars_per_token:g} chars/token -> {est['input_tokens']:,} input tokens")
    print(f"  ASSUMPTION facts per call = per-chunk cap (ceiling) -> {est['fact_ceiling']:,} facts")
    print(f"  ASSUMPTION {a.tokens_per_fact} output tokens per fact -> "
          f"{est['output_tokens_ceiling']:,} output tokens (ceiling)")
    print(f"  rates ${rin:g} / ${rout:g} per MTok "
          f"({'passed explicitly' if explicit else PUBLISHED_HAIKU_45['source'] + ', TO CONFIRM'})")
    print(f"  ESTIMATE ${est['usd']:.2f} (sequential; excludes {est['assumptions']['excluded']})")

    record = {"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "seed": a.seed, "sample_requested": a.sample, "model": model,
              "conversation_ids": [c["id"] for c in sample],
              "strata": {f"{s}|{m}": v for (s, m), v in sorted(by_stratum.items())},
              "estimate": est, "ran": False}
    out_dir = root / "data" / "pilot"
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_path = out_dir / ("pilot_%s.json" % record["created_utc"].replace(":", ""))

    def _save():
        rec_path.write_text(json.dumps(record, indent=1), encoding="utf-8")

    refusal = None
    if a.confirm_spend is None:
        refusal = "no --confirm-spend given: estimate only, nothing was sent."
    elif not explicit and not a.rates_confirmed:
        refusal = ("the default rates are unconfirmed: check them against the current published "
                   "price and pass --rates-confirmed, or pass --input-rate and --output-rate.")
    elif est["usd"] > a.confirm_spend:
        refusal = f"estimate ${est['usd']:.2f} exceeds --confirm-spend ${a.confirm_spend:.2f}."
    if refusal:
        record["refused"] = refusal
        _save()
        print(f"  NOT RUN: {refusal}")
        print(f"  selection -> {rec_path}")
        raise PilotRefused(2)

    print(f"  RUNNING under cap ${a.confirm_spend:.2f}. The cap gates the estimate only; the "
          f"run is not stopped part-way. Measured usage is read back from the run record.")
    started = time.time()
    record["ran"] = True
    record["confirm_spend"] = a.confirm_spend
    _save()
    ids = [c["id"] for c in sample]
    if runner is None:
        _default_runner(ids, db)
    else:
        runner(ids)
    measured = measured_usage(root, since=started)
    record["measured"] = measured
    if measured is None:
        print("  MEASURED: no extraction run record written by this run; spend is unmeasured.")
    else:
        t = measured["totals"]
        cost = t["input_tokens"] / 1e6 * rin + t["output_tokens"] / 1e6 * rout
        measured["usd_input_output"] = round(cost, 4)
        print(f"  MEASURED ({measured['run_id']}): {t['calls']:,} calls, "
              f"{t['input_tokens']:,} input, {t['output_tokens']:,} output, "
              f"{t['cache_read_input_tokens']:,} cache read, "
              f"{t['cache_creation_input_tokens']:,} cache write tokens")
        print(f"  MEASURED cost ${cost:.4f} at ${rin:g}/${rout:g} per MTok (input and output; "
              f"cache tokens listed, not priced) against the estimate ${est['usd']:.4f}")
        if t.get("calls_without_usage"):
            print(f"  WARNING: {t['calls_without_usage']} calls reported no usage; the "
                  f"measurement is a floor.")
    if manifest is not None:
        record["planted_fact_problems"] = F.check_stored_facts(conn, manifest)
        print(f"  planted: {len(record['planted_fact_problems'])} stored facts rest on a "
              f"planted bad turn" + ("" if not record["planted_fact_problems"] else ":"))
        for p in record["planted_fact_problems"]:
            print(f"    {p}")
    _save()
    print(f"  pilot record -> {rec_path}")
    print("  NEXT: this pilot corpus is NOT for distillation. It holds pilot-only extractions"
          + (" and facts from planted known-bad sessions" if manifest is not None else "")
          + ". Price the full run from the MEASURED line above, then build the full run in a "
          "fresh corpus directory. distill.py and assemble refuse planted facts unless given "
          "--allow-planted.")
    return record


if __name__ == "__main__":
    try:
        main()
    except PilotRefused as e:
        if not isinstance(e.code, int):
            print(f"REFUSED: {e.code}", file=sys.stderr)
            sys.exit(2)
        sys.exit(e.code)
