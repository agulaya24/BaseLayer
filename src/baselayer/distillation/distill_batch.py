"""Batched interpretive distillation. The whole study as three batch rounds.

EXPERIMENTAL AND UNTESTED. No test exercises this module, and it does not call
validate(), so its output is UNSTRIPPED: fabricated fact ids are not removed.

WHY THIS WORKS AT ALL: LEVEL 1 IS ORDER-INDEPENDENT BY DESIGN. Each leaf is a pure function of
its own chunk, chosen so that chunk order could not make the tree a function of (corpus, order)
and so that order sensitivity stays measurable instead of factorial. That same property makes
every leaf across every configuration an INDEPENDENT REQUEST, so they all go in one batch.
The order-invariance decision and the batching win are the same property.

Rounds: L1 (all configurations x all chunks, one submission) -> L2 (depends on L1) -> ROOT.
Three round trips for an entire multi-configuration study instead of thousands of serial calls,
at half price.

custom_id carries (layer, partition, seed, level, index) so results reassemble without relying
on ordering, which the API does not promise.
"""
import os, sys, json, re, time, sqlite3, argparse, hashlib, itertools
from collections import Counter

# This module now lives inside the baselayer package and imports nothing from it, so the
# old walk-up-to-the-checkout shim is gone (from here, it resolved to a path that does not
# exist). BASELAYER_SRC is still honoured so a caller can pin which checkout resolves first.
_src = os.environ.get("BASELAYER_SRC")
if _src:
    sys.path.insert(0, _src)
import anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib.util
_spec = importlib.util.spec_from_file_location("_d", os.path.join(HERE, "distill.py"))
_d = importlib.util.module_from_spec(_spec)
_src = open(os.path.join(HERE, "distill.py"), encoding="utf-8").read().replace("\nmain()\n", "\n")
exec(compile(_src, "distill.py", "exec"), _d.__dict__)

LEAF_PROMPT, NODE_PROMPT = _d.LEAF_PROMPT, _d.NODE_PROMPT
LEAF_SCHEMA, LAYER_DIRECTIVES = _d.LEAF_SCHEMA, _d.LAYER_DIRECTIVES
partition, parse, render, _cost = _d.partition, _d.parse, _d.render, _d._cost

# Half price. Reported separately from the serial path so a mixed study cannot silently
# average two different rates into one number.
BATCH_DISCOUNT = 0.5


def submit(cl, reqs, label):
    b = cl.messages.batches.create(requests=reqs)
    print("  submitted %s: %d requests, batch %s" % (label, len(reqs), b.id), flush=True)
    return b.id


def wait(cl, bid, label, poll=20):
    while True:
        b = cl.messages.batches.retrieve(bid)
        c = b.request_counts
        if b.processing_status == "ended":
            print("  %s ended: succeeded=%d errored=%d canceled=%d expired=%d"
                  % (label, c.succeeded, c.errored, c.canceled, c.expired), flush=True)
            return b
        print("    %s ... %s  done=%d/%d" % (label, b.processing_status,
                                             c.succeeded + c.errored, c.processing
                                             + c.succeeded + c.errored), flush=True)
        time.sleep(poll)


def collect(cl, bid):
    """Return {custom_id: (parsed_or_None, stop_reason, in_tok, out_tok)}.

    An errored or unparseable request yields None. It is NEVER folded into an empty dict:
    the serial path already produced one wrong headline that way, where a parse failure at an
    interior node was reported as content the tree had dropped.
    """
    out = {}
    for r in cl.messages.batches.results(bid):
        if r.result.type != "succeeded":
            out[r.custom_id] = (None, r.result.type, 0, 0)
            continue
        m = r.result.message
        t = next((b.text for b in m.content if getattr(b, "type", None) == "text"), "")
        out[r.custom_id] = (parse(t), m.stop_reason, m.usage.input_tokens, m.usage.output_tokens)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--max-facts", type=int, default=60)
    ap.add_argument("--layers", default="anchors,core,predictions")
    ap.add_argument("--partitions", default="predicate,random,semantic")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble every request and price it, submit nothing")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    c = sqlite3.connect("file:%s?mode=ro" % a.db, uri=True)
    rows = c.execute("SELECT id, fact_text, predicate, category, id FROM memory_facts "
                     "WHERE superseded_by IS NULL ORDER BY id").fetchall()
    layers = a.layers.split(",")
    parts = a.partitions.split(",")
    seeds = [int(s) for s in a.seeds.split(",")]
    configs = list(itertools.product(layers, parts, seeds))
    print("facts=%d  configurations=%d (%d layers x %d partitions x %d seeds)"
          % (len(rows), len(configs), len(layers), len(parts), len(seeds)), flush=True)

    chunkcache = {}
    reqs, meta = [], {}
    for lay, part, seed in configs:
        key = (part, seed)
        if key not in chunkcache:
            chunkcache[key] = partition(rows, part, a.max_facts, seed)
        chunks = chunkcache[key]
        for n, (label, fs) in enumerate(chunks):
            cid = "L1|%s|%s|%d|%03d" % (lay, part, seed, n)
            body = "\n".join("[%s] %s" % (r[0][:8], r[1]) for r in fs)
            p = LEAF_PROMPT % (LAYER_DIRECTIVES[lay], label, len(fs), body, LEAF_SCHEMA)
            reqs.append({"custom_id": cid,
                         "params": {"model": a.model, "max_tokens": 16000,
                                    "messages": [{"role": "user", "content": p}]}})
            meta[cid] = {"layer": lay, "partition": part, "seed": seed, "chunk": label,
                         "n": len(fs), "ids": [r[0][:8] for r in fs]}
    est_in = sum(len(r["params"]["messages"][0]["content"]) for r in reqs) / 3.6
    print("L1 requests: %d   est input ~%.0fk tokens" % (len(reqs), est_in / 1000))
    rate_in, rate_out = _d._RATES[a.model]  # raise on unknown; a defaulted rate is fiction
    est = (est_in / 1e6 * rate_in + len(reqs) * 5800 / 1e6 * rate_out) * BATCH_DISCOUNT
    print("L1 estimated cost at batch rates: $%.2f  (serial would be $%.2f)"
          % (est, est / BATCH_DISCOUNT))
    if a.dry_run:
        print("\nDRY RUN. Nothing submitted. Estimate assumes ~5800 output tokens/leaf, "
              "measured on a 407-fact corpus; verify against the first real round rather than trusting it.")
        return

    cl = anthropic.Anthropic()
    bid = submit(cl, reqs, "L1")
    wait(cl, bid, "L1")
    res = collect(cl, bid)
    json.dump({"batch_id": bid, "meta": meta,
               "results": {k: (v[0], v[1], v[2], v[3]) for k, v in res.items()}},
              open(os.path.join(a.outdir, "L1.json"), "w", encoding="utf-8"), indent=1)
    bad = [k for k, v in res.items() if v[0] is None]
    print("L1 unparseable/errored: %d of %d %s" % (len(bad), len(res), bad[:8]))
    print("wrote %s" % os.path.join(a.outdir, "L1.json"))
    # NO --resume FLAG EXISTS, AND NO L2 ROUND IS IMPLEMENTED HERE. This line instructed a
    # workflow that was never built. Say what the file actually does instead.
    print("\nLEVEL 1 ONLY. This file batches leaves and stops. There is no L2/root round here "
          "and no --resume flag; assemble.py does not accept L1.json. Use distill.py for a "
          "complete tree. Note also that this path does NOT call validate(), so its output is "
          "UNSTRIPPED and fabricated ids are not removed.")


main()
