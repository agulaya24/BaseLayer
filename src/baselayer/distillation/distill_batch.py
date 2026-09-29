"""Batched interpretive distillation: every layer's leaves in ONE Message Batches submission.

WHY THIS WORKS AT ALL: LEVEL 1 IS ORDER-INDEPENDENT BY DESIGN. Each leaf is a pure function of
its own chunk, so every leaf of every layer is an independent request and they all go in one
batch: the three layers run concurrently, at the batch discount (spend.BATCH_DISCOUNT).

The leaves are then handled EXACTLY as distill.py handles its own:
  - the same fact reader and free refusals (distill.load_facts: record-only exclusion, subject
    filter, mixed contract versions, planted sessions, id-prefix collision), before any client;
  - the same leaf prompt (distill.leaf_prompt), so the leaf prompt hash is identical;
  - the same parse / validate / strip / repair logic (distill.call_json with the batch result
    as its first response). A result that errored, expired or will not parse is repaired with
    sequential calls through distill.call, under the run's spend ceiling. Nothing is stored as
    an empty leaf without the repair having been tried;
  - the same post-leaf handling (distill.finish_tree): collection, payload check, stamp,
    archive, audit, ledger. The tree stamp adds leaf_path "batch", batch_id and batch_repairs.

Cost: batch tokens at the discount, repair tokens at the full rate; the tree's usage block
reports both. The spend ceiling is checked against the whole batch's estimate before submit
(a batch cannot be stopped per call once submitted), then before every sequential repair.

DUPLICATE-BILLING GUARDS. The submit is one POST, made with retries OFF, because a timeout after
the server accepted it would otherwise be retried into a second billed batch. The batch id is
written to <outdir>/batch_state.json the moment it exists, before any waiting. A second run on
the same outdir refuses to submit again; --resume collects the recorded batch instead. Raw
results are saved to <outdir>/batch_results.json before they are processed.

Run: python -m baselayer.distillation.distill_batch --db <memory.db> --outdir <dir>
     --model claude-sonnet-5 --max-facts 50 --rates-confirmed <date> --confirm-spend <usd>
"""
import argparse
import itertools
import json
import os
import sys
import time

_src = os.environ.get("BASELAYER_SRC")
if _src:
    sys.path.insert(0, _src)
elif not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import anthropic
from baselayer.distillation import distill as _d
from baselayer.distillation import spend as _spend

LEAF_MAX_TOKENS = 16000
STATE = "batch_state.json"
RESULTS = "batch_results.json"


def custom_id(layer, part, seed, n):
    """Within the API's custom_id shape ([A-Za-z0-9_-], at most 64 characters)."""
    return "L1-%s-%s-%d-%04d" % (layer, part, seed, n)


def build_requests(rows, layers, parts, seeds, max_facts, model, other_subjects,
                   max_tokens=LEAF_MAX_TOKENS, opts=None):
    """(requests, meta, chunks_by_config). meta maps custom_id to where its leaf belongs.
    `opts` (distill.LeafOptions) carries the design-test flags; the repair loop in _main builds
    each prompt with the same opts, so a repaired leaf is sent the prompt the batch was sent."""
    chunkcache, reqs, meta, by_cfg = {}, [], {}, {}
    for lay, part, seed in itertools.product(layers, parts, seeds):
        if (part, seed) not in chunkcache:
            chunkcache[(part, seed)] = _d.make_chunks(rows, part, max_facts, seed, opts)
        chunks = chunkcache[(part, seed)]
        by_cfg[(lay, part, seed)] = chunks
        for n, (label, fs) in enumerate(chunks):
            cid = custom_id(lay, part, seed, n)
            p = _d.leaf_prompt(lay, label, fs, other_subjects, opts)
            reqs.append({"custom_id": cid,
                         "params": {"model": model, "max_tokens": max_tokens,
                                    "messages": [{"role": "user", "content": p}]}})
            meta[cid] = {"layer": lay, "partition": part, "seed": seed, "n": n}
    return reqs, meta, by_cfg


def submit(cl, reqs, outdir, info):
    """One POST with retries off; the batch id is on disk before this returns."""
    try:
        b = cl.with_options(max_retries=0, timeout=600).messages.batches.create(
            requests=reqs)
    except Exception as e:
        raise SystemExit(
            "BATCH SUBMIT FAILED (%s: %s). The server may still have accepted it. Before "
            "resubmitting, list recent batches (client.messages.batches.list) and, if one "
            "matches, record its id in %s and use --resume." % (type(e).__name__, e,
                                                               os.path.join(outdir, STATE)))
    state = dict(info, batch_id=b.id,
                 submitted_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    tmp = os.path.join(outdir, STATE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, os.path.join(outdir, STATE))
    print("  submitted %d requests, batch %s (state -> %s)" % (len(reqs), b.id, STATE),
          flush=True)
    return b.id


def wait(cl, bid, poll):
    while True:
        b = cl.messages.batches.retrieve(bid)
        c = b.request_counts
        if b.processing_status == "ended":
            print("  batch ended: succeeded=%d errored=%d canceled=%d expired=%d"
                  % (c.succeeded, c.errored, c.canceled, c.expired), flush=True)
            return b
        print("    %s ... done=%d/%d" % (b.processing_status, c.succeeded + c.errored,
                                        c.processing + c.succeeded + c.errored), flush=True)
        time.sleep(poll)


def collect(cl, bid):
    """{custom_id: {"type", "text", "stop", "in", "out"}}. Keyed by custom_id, never order.
    Text blocks are selected by type: thinking blocks come first on 5-generation models."""
    out = {}
    for r in cl.messages.batches.results(bid):
        if r.result.type != "succeeded":
            out[r.custom_id] = {"type": r.result.type, "text": None, "stop": None,
                                "in": 0, "out": 0}
            continue
        m = r.result.message
        t = "".join(getattr(b, "text", "") for b in m.content
                    if getattr(b, "type", None) == "text")
        out[r.custom_id] = {"type": "succeeded", "text": t, "stop": m.stop_reason,
                            "in": m.usage.input_tokens, "out": m.usage.output_tokens}
    return out


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-facts", type=int, default=50)
    ap.add_argument("--layers", default="anchors,core,predictions")
    ap.add_argument("--partitions", default="predicate",
                    help="comma list; one tree per layer x partition x seed")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble every request and price it, submit nothing")
    ap.add_argument("--resume", action="store_true",
                    help="collect the batch recorded in <outdir>/batch_state.json; never submit")
    ap.add_argument("--poll", type=float, default=60.0, help="seconds between status checks")
    ap.add_argument("--est-out-per-leaf", type=int, default=_spend.MEASURED_LEAF_OUT_TOKENS,
                    help="output tokens per leaf for the estimate (measured: %s)"
                         % _spend.MEASURED_LEAF_BASIS)
    ap.add_argument("--allow-planted", action="store_true",
                    help="PILOT CORPORA ONLY: see distill.py")
    ap.add_argument("--write-provenance", action="store_true",
                    help="as distill.py: WRITES root citations to the corpus db")
    _d.add_record_only_arg(ap)
    _d.add_subject_arg(ap)
    _d.add_exclude_ids_arg(ap)
    _d.add_design_args(ap)
    _spend.add_rate_args(ap)
    _spend.add_spend_args(ap)
    a = ap.parse_args()
    layers = a.layers.split(",")
    parts = a.partitions.split(",")
    seeds = [int(x) for x in a.seeds.split(",")]
    for lay in layers:
        if lay not in _d.LAYER_DIRECTIVES:
            raise SystemExit("unknown layer %r" % lay)

    # Same reader and free refusals as distill.py. load_facts checks the `time` partition
    # against the corpus, so hand it that partition when it is requested.
    F = _d.load_facts(argparse.Namespace(
        db=a.db, partition="time" if "time" in parts else parts[0],
        include_record_only=a.include_record_only,
        include_other_subjects=a.include_other_subjects, allow_planted=a.allow_planted,
        exclude_ids=a.exclude_ids))
    rows = F["rows"]
    print("record_only facts: %d excluded, %d included"
          % (F["record_only_excluded"], F["record_only_included"]), flush=True)
    configs = list(itertools.product(layers, parts, seeds))
    print("facts=%d  configurations=%d (%d layers x %d partitions x %d seeds)"
          % (len(rows), len(configs), len(layers), len(parts), len(seeds)), flush=True)
    opts = _d.leaf_options(argparse.Namespace(
        db=a.db, partition=None, partitions_list=parts, max_facts=a.max_facts,
        leaf_spans=a.leaf_spans, span_cap=a.span_cap, episode_max=a.episode_max,
        episode_min=a.episode_min, episode_day_title_regex=a.episode_day_title_regex,
        episode_tz=a.episode_tz, episode_day_practice=a.episode_day_practice), rows)
    reqs, meta, by_cfg = build_requests(rows, layers, parts, seeds, a.max_facts, a.model,
                                        F["other_subjects"], opts=opts)
    if opts is not None:
        print("DESIGN FLAGS: %s" % json.dumps(opts.stamp())[:600], flush=True)
    rates = _spend.rates_from_args(a.model, a)
    est, est_worst = _spend.estimate_calls(
        [len(r["params"]["messages"][0]["content"]) for r in reqs], a.est_out_per_leaf, rates,
        LEAF_MAX_TOKENS, batch=True)
    print("L1 requests: %d in ONE batch (all layers concurrently)" % len(reqs), flush=True)
    _d.print_payload_projection(len(rows))
    print("ESTIMATE: $%.4f at batch rates (sequential would be $%.4f); worst $%.4f if every "
          "leaf stops at max_tokens. Repairs of failed results run sequentially at full rate "
          "and are not in the estimate." % (est, est / rates["batch_discount"], est_worst),
          flush=True)
    if a.dry_run:
        print("\nDRY RUN. Nothing submitted.")
        return None

    os.makedirs(a.outdir, exist_ok=True)
    state_path = os.path.join(a.outdir, STATE)
    if os.path.exists(state_path) and not a.resume:
        raise SystemExit("A batch was already submitted from %s (%s). Use --resume to collect "
                         "it; submitting again would bill twice." % (a.outdir, STATE))
    if a.resume and not os.path.exists(state_path):
        raise SystemExit("--resume given but %s does not exist" % state_path)
    ceiling = _spend.plan_ceiling(est, a.confirm_spend)
    guard = _spend.SpendGuard(rates, ceiling, label="distill_batch")
    _d._GUARD = guard       # every sequential repair goes through distill.call
    print("SPEND CEILING: $%.4f (the batch estimate is checked before submit; every repair "
          "call is checked before it is sent)" % ceiling, flush=True)

    cl = anthropic.Anthropic()
    if a.resume:
        state = json.load(open(state_path, encoding="utf-8"))
        bid = state["batch_id"]
        # A batch submitted under one exclusion list must not be collected under another: the
        # chunks would be rebuilt from a different population. A state file written before the
        # field existed records no exclusion, which is read as None.
        if state.get("exclude_ids_sha256") != F["exclude_info"]["exclude_ids_sha256"]:
            raise SystemExit("--resume: %s records exclude-ids sha256 %s; this invocation has %s. "
                             "Resume with the arguments that submitted it."
                             % (STATE, state.get("exclude_ids_sha256"),
                                F["exclude_info"]["exclude_ids_sha256"]))
        if state.get("n_requests") != len(reqs) or state.get("model") != a.model:
            raise SystemExit("--resume: %s records %s requests on %s; this invocation builds %d "
                             "on %s. Resume with the arguments that submitted it."
                             % (STATE, state.get("n_requests"), state.get("model"), len(reqs),
                                a.model))
        # The chunking the batch was built with. Equal request counts do not mean equal chunks
        # (--max-facts 3 and 4 both cut 5 facts into 2), and the custom_ids would then match.
        now = {"layers": layers, "partitions": parts, "seeds": seeds, "max_facts": a.max_facts}
        drift = sorted(k for k, v in now.items() if k in state and state[k] != v)
        if drift:
            raise SystemExit("--resume: %s records %s; this invocation has %s. Resume with the "
                             "arguments that submitted it."
                             % (STATE, {k: state[k] for k in drift}, {k: now[k] for k in drift}))
        print("RESUMING batch %s" % bid, flush=True)
    else:
        bid = submit(cl, reqs, a.outdir, {"n_requests": len(reqs), "model": a.model,
                                          "layers": layers, "partitions": parts,
                                          "seeds": seeds, "max_facts": a.max_facts,
                                          "estimate_usd": est, "ceiling_usd": ceiling,
                                          "exclude_ids_sha256":
                                              F["exclude_info"]["exclude_ids_sha256"]})
    res_path = os.path.join(a.outdir, RESULTS)
    fresh = not (a.resume and os.path.exists(res_path))
    if not fresh:
        res = json.load(open(res_path, encoding="utf-8"))["results"]
        print("RESUMING from saved results: batch usage was billed and counted by the run that "
              "collected it; this process counts only its own repairs.", flush=True)
    else:
        wait(cl, bid, a.poll)
        res = collect(cl, bid)
        with open(res_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump({"batch_id": bid, "results": res}, fh)
        os.replace(res_path + ".tmp", res_path)

    # Batch usage is billed whether or not a result parses: count all of it first, once.
    if fresh:
        for r in res.values():
            guard.record(r["in"], r["out"], batch=True)

    trees = {}
    for (lay, part, seed), chunks in by_cfg.items():
        tree_path = os.path.join(a.outdir, "%s_%s_%d.json" % (lay, part, seed))
        if a.resume and os.path.exists(tree_path):
            done_tree = json.load(open(tree_path, encoding="utf-8"))
            if (done_tree.get("stamp") or {}).get("batch_id") == bid:
                # Finished by an earlier process from this batch: its repairs are paid for.
                print("  %s / %s / seed %d: tree already written from batch %s, skipped"
                      % (lay, part, seed, bid), flush=True)
                trees[(lay, part, seed)] = done_tree
                continue
        ph, leaf_common = _d.leaf_stamp_common(lay, a.model, F["contract_version"], opts)
        stats = {"in": 0, "out": 0, "batch_in": 0, "batch_out": 0, "parse_fail": [],
                 "parse_fail_final": [], "repaired": [], "truncated": [], "schema_fail": [],
                 "schema_repaired": [], "schema_fail_final": [], "_expect_ids": None}
        repairs = {}
        leaves = []
        for n, (label, fs) in enumerate(chunks):
            cid = custom_id(lay, part, seed, n)
            r = res.get(cid) or {"type": "missing", "text": None, "stop": None, "in": 0,
                                 "out": 0}
            stats["batch_in"] += r["in"]
            stats["batch_out"] += r["out"]
            p = _d.leaf_prompt(lay, label, fs, F["other_subjects"], opts)
            stats["_expect_ids"] = [x[0][:8] for x in fs]
            stats["_spans"] = opts.spans if opts is not None else None
            if r["type"] != "succeeded":
                # errored / expired / canceled / missing: a fresh sequential call.
                repairs[r["type"]] = repairs.get(r["type"], 0) + 1
                d, stop = _d.call_json(cl, a.model, p, LEAF_MAX_TOKENS, "L1-%02d" % (n + 1),
                                       stats)
            else:
                if _d.parse(r["text"] or "") is None:
                    repairs["unparseable"] = repairs.get("unparseable", 0) + 1
                d, stop = _d.call_json(cl, a.model, p, LEAF_MAX_TOKENS, "L1-%02d" % (n + 1),
                                       stats, first=(r["text"] or "", r["in"], r["out"],
                                                     r["stop"]))
            stats["_expect_ids"] = None
            stats["_spans"] = None
            if d is None:
                d = {"themes": [], "singularities": [], "contradictions": [],
                     "dispositions": {}, "_parse_failed": True}
            d["_chunk"] = label
            d["_n"] = len(fs)
            d["_ids"] = [x[0][:8] for x in fs]
            d["_stamp"] = dict(leaf_common, chunk=label, batch_id=bid,
                               input_hash=_d._tc.facts_input_hash((x[0], x[1]) for x in fs))
            _d.annotate_leaf(d, fs, opts)
            leaves.append(d)
        ta = argparse.Namespace(
            db=a.db, out=tree_path,
            model=a.model, layer=lay, partition=part, seed=seed, max_facts=a.max_facts,
            limit_chunks=0, write_provenance=a.write_provenance,
            est_out_per_leaf=a.est_out_per_leaf)
        run = {"rows": rows, "chunks": chunks, "leaves": leaves, "stats": stats, "ph": ph,
               "leaf_common": leaf_common, "contract_version": F["contract_version"],
               "n_planted": F["n_planted"], "record_only_included": F["record_only_included"],
               "record_only_excluded": F["record_only_excluded"],
               "subject_info": F["subject_info"], "other_subjects": F["other_subjects"],
               "rates": rates, "est": est, "est_worst": est_worst, "ceiling": ceiling,
               "t0": time.time(), "done": 0, "exclude_info": F["exclude_info"],
               "stamp_extra": {"leaf_path": "batch", "batch_id": bid,
                               "batch_discount": rates["batch_discount"],
                               "batch_repairs": repairs,
                               **(opts.stamp() if opts is not None else {})}}
        print("\n=== TREE %s / %s / seed %d ===" % (lay, part, seed), flush=True)
        trees[(lay, part, seed)] = _d.finish_tree(ta, cl, run)
    print("\nbatch %s: measured $%.4f of ceiling $%.4f (batch %d in / %d out, sequential %d in "
          "/ %d out)" % (bid, guard.spent_usd, ceiling, guard.tokens["batch_in"],
                         guard.tokens["batch_out"], guard.tokens["in"], guard.tokens["out"]))
    return trees


def main():
    """Run, then clear distill's spend guard however the run ends (it was set for this run)."""
    try:
        return _main()
    finally:
        _d._GUARD = None


if __name__ == "__main__":
    main()
