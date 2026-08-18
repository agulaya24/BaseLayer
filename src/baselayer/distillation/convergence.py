"""HOW MANY RUNS UNTIL THE INVARIANT SET STOPS SHRINKING?

EXPERIMENTAL AND UNTESTED. No test exercises this module, and it does not call
validate(), so its output is UNSTRIPPED: fabricated fact ids are not removed.

Measured: three IDENTICAL anchors runs (same model, partition, directive, corpus)
produced singularity sets of 39/37/44 with a union of 75, of which only 13 appeared in all
three and 43 appeared in exactly one. So a single run's list of "decisive" facts is 57%
run-specific, and no single tree can be trusted as a reading of anyone.

That is an argument FOR the multi-run design rather than against it: the invariant set is the
part with a stability claim, and everything else is a hypothesis. It also turns "how many runs"
from a budget question into an empirical one, which is what this measures.

ONLY LEVEL 1 IS NEEDED. The instability lives at the leaf, where singularities are chosen, so
running full trees would multiply cost for no additional signal. Leaves are independent by
design, so N replicates x C chunks is one batch submission at half price.

Checkpoints every 10 runs: report |invariant|, |union|, and the count appearing exactly once.
The curve of |invariant| against N is the answer; it stops falling when the noise is exhausted.
"""
import os, sys, json, time, sqlite3, argparse, itertools
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
# This module now lives inside the baselayer package and imports nothing from it, so the
# old walk-up-to-the-checkout shim is gone (from here, it resolved to a path that does not
# exist). BASELAYER_SRC is still honoured so a caller can pin which checkout resolves first.
_src = os.environ.get("BASELAYER_SRC")
if _src:
    sys.path.insert(0, _src)
sys.path.insert(0, HERE)
import anthropic
import importlib.util

_src = open(os.path.join(HERE, "distill.py"), encoding="utf-8").read().replace("\nmain()\n", "\n")
_d = importlib.util.module_from_spec(importlib.util.spec_from_loader("_d", loader=None))
exec(compile(_src, "distill.py", "exec"), _d.__dict__)


def curve(runs, ns):
    """|invariant| and friends at each checkpoint. `runs` is a list of id-sets, in order."""
    out = []
    for n in ns:
        if n > len(runs):
            break
        c = Counter(f for s in runs[:n] for f in s)
        out.append({"n_runs": n,
                    "mean_per_run": round(sum(len(s) for s in runs[:n]) / n, 1),
                    "union": len(c),
                    "invariant": sum(v == n for v in c.values()),
                    "in_at_least_half": sum(v >= (n + 1) // 2 for v in c.values()),
                    "exactly_once": sum(v == 1 for v in c.values())})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "convergence"))
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--layer", default="anchors")
    ap.add_argument("--partition", default="predicate")
    ap.add_argument("--max-facts", type=int, default=60)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--checkpoint", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", default="", help="batch id to collect instead of submitting")
    ap.add_argument("--limit-facts", type=int, default=0,
                    help="uniform random slice of the corpus. THE 3-RUN REQUIREMENT WAS "
                         "MEASURED ON 407 FACTS / 7 CHUNKS; per-chunk variance may average out "
                         "over hundreds of chunks, so it has to be re-measured at scale before "
                         "being paid for.")
    ap.add_argument("--slice-seed", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    c = sqlite3.connect("file:%s?mode=ro" % a.db, uri=True)
    rows = c.execute("SELECT id, fact_text, predicate, category, id FROM memory_facts "
                     "WHERE superseded_by IS NULL ORDER BY id").fetchall()
    if a.limit_facts and a.limit_facts < len(rows):
        import random as _r
        rows = _r.Random(a.slice_seed).sample(list(rows), a.limit_facts)
        rows.sort(key=lambda r: r[0])
        print("sliced to %d facts (uniform, seed=%d)" % (len(rows), a.slice_seed), flush=True)
    chunks = _d.partition(rows, a.partition, a.max_facts, 0)
    txtof = {r[0][:8]: r[1] for r in rows}
    print("facts=%d chunks=%d runs=%d -> %d leaf requests (LEVEL 1 ONLY)"
          % (len(rows), len(chunks), a.runs, len(chunks) * a.runs), flush=True)

    reqs = []
    for run in range(a.runs):
        for n, (label, fs) in enumerate(chunks):
            body = "\n".join("[%s] %s" % (r[0][:8], r[1]) for r in fs)
            p = _d.LEAF_PROMPT % (_d.LAYER_DIRECTIVES[a.layer], label, len(fs), body, _d.LEAF_SCHEMA)
            reqs.append({"custom_id": "r%03d-c%03d" % (run, n),
                         "params": {"model": a.model, "max_tokens": 16000,
                                    "messages": [{"role": "user", "content": p}]}})
    ri, ro = _d._RATES[a.model]  # raise on unknown; a defaulted rate is fiction
    est_in = sum(len(r["params"]["messages"][0]["content"]) for r in reqs) / 3.6
    est = (est_in / 1e6 * ri + len(reqs) * 5800 / 1e6 * ro) * 0.5
    print("estimated batch cost: $%.2f (serial $%.2f)" % (est, est * 2), flush=True)
    if a.dry_run:
        print("DRY RUN, nothing submitted.")
        return

    cl = anthropic.Anthropic()
    if a.resume:
        bid = a.resume
        print("resuming batch %s" % bid, flush=True)
    else:
        b = cl.messages.batches.create(requests=reqs)
        bid = b.id
        json.dump({"batch_id": bid, "runs": a.runs, "chunks": len(chunks),
                   "layer": a.layer, "partition": a.partition, "model": a.model},
                  open(os.path.join(a.out, "batch.json"), "w"), indent=1)
        print("submitted batch %s (%d requests)" % (bid, len(reqs)), flush=True)

    while True:
        b = cl.messages.batches.retrieve(bid)
        rc = b.request_counts
        done = rc.succeeded + rc.errored + rc.canceled + rc.expired
        print("  %s  done=%d/%d" % (b.processing_status, done, done + rc.processing), flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(30)

    per_run = {}
    tin = tout = 0
    errs = 0
    for r in cl.messages.batches.results(bid):
        run = int(r.custom_id[1:4])
        if r.result.type != "succeeded":
            errs += 1
            continue
        m = r.result.message
        tin += m.usage.input_tokens
        tout += m.usage.output_tokens
        t = next((bb.text for bb in m.content if getattr(bb, "type", None) == "text"), "")
        d = _d.parse(t)
        if d is None:
            errs += 1
            continue
        s = per_run.setdefault(run, {"sing": set(), "nlb": set(), "disp": 0, "verbatim_ok": 0,
                                     "verbatim_n": 0})
        for x in (d.get("singularities") or []):
            fid = x.get("fact_id")
            if fid:
                s["sing"].add(fid)
                if fid in txtof:
                    s["verbatim_n"] += 1
                    s["verbatim_ok"] += (x.get("verbatim", "").strip() == txtof[fid].strip())
        for k, v in (d.get("dispositions") or {}).items():
            s["disp"] += 1
            if v == "not_load_bearing":
                s["nlb"].add(k)
    order = sorted(per_run)
    sings = [per_run[i]["sing"] for i in order]
    cps = list(range(a.checkpoint, len(sings) + 1, a.checkpoint)) or [len(sings)]
    if len(sings) not in cps:
        cps.append(len(sings))
    rep = {"batch_id": bid, "model": a.model, "layer": a.layer, "partition": a.partition,
           "runs_ok": len(sings), "errors": errs,
           "cost_usd_batch": round(_d._cost(a.model, tin, tout) * 0.5, 2),
           "in": tin, "out": tout,
           "disposition_mean": round(sum(per_run[i]["disp"] for i in order) / max(1, len(order)), 1),
           "verbatim_exact_pct": round(100.0 * sum(per_run[i]["verbatim_ok"] for i in order)
                                       / max(1, sum(per_run[i]["verbatim_n"] for i in order)), 1),
           "curve": curve(sings, cps),
           "nlb_counts": [len(per_run[i]["nlb"]) for i in order]}
    json.dump(rep, open(os.path.join(a.out, "convergence.json"), "w"), indent=1)
    print("\n=== CONVERGENCE OF THE INVARIANT SET (%s, %s, %s) ==="
          % (a.model, a.layer, a.partition))
    print("runs ok %d, errors %d, batch cost $%.2f" % (len(sings), errs, rep["cost_usd_batch"]))
    print("%-7s %-12s %-7s %-10s %-14s %s" %
          ("N runs", "mean/run", "union", "INVARIANT", ">=half of N", "seen once"))
    for r in rep["curve"]:
        print("%-7d %-12s %-7d %-10d %-14d %d" %
              (r["n_runs"], r["mean_per_run"], r["union"], r["invariant"],
               r["in_at_least_half"], r["exactly_once"]))
    print("\ndismissal counts per run: %s" % rep["nlb_counts"])
    print("verbatim lane exact: %.1f%%   mean dispositions/run: %s"
          % (rep["verbatim_exact_pct"], rep["disposition_mean"]))


main()
