"""Run one consolidation builder: the model steps that make the stage inputs a re-authored
spec needs. `baselayer consolidate` itself calls no model; these produce its input files.

    python -m baselayer.consolidation.build judge      --claims claims.json --overlap overlap.json --out judgements.json ...
    python -m baselayer.consolidation.build group      --claims claims.json --always-on always_on.json --out grouping.json ...
    python -m baselayer.consolidation.build categorize --claims claims.json --triggers triggers.json --out categories.json ...

    judge       -> consolidate --dedupe-basis judgements --judgements judgements.json
    group       -> consolidate --grouping grouping.json
    categorize  -> consolidate --categories categories.json   (reads a triggers.json made from the grouping)

Backends (--backend):
    api   the Anthropic API (default model claude-opus-5). The run is priced before any
          client exists, from distillation/spend.py's dated table, which the operator
          confirms (--rates-confirmed) or overrides (--rate-in/--rate-out). It is refused
          without a ceiling (BASELAYER_SPEND_CEILING_USD, or --confirm-spend at or above the
          estimate), and every call is checked against the ceiling first. --plan-only
          prints the estimate and calls nothing.
    cli   `claude -p` on the local subscription ($0), isolated (see backends.py). A context
          probe of the actual child runs first and is stored in --work; the run is refused
          unless it is clean. --canary adds strings the probe must not find.

Every model reply that parses is checkpointed to <work>/calls.jsonl before it is used, so
a rerun of the same command resumes; a changed prompt under the same key is refused. A
usage or rate limit is never recorded: the run backs off, and if the limit persists it
stops with exit 3 and the checkpoint intact. Exit 1 when any call failed after retries
(the output is still written, with the failures listed); 0 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import categorize as cat_b
from . import grouper as grp_b
from . import judge as judge_b
from .backends import ApiBackend, CallRunner, CallStore, ClaudeCliBackend, UsageLimitStop
from .common import file_sha256, guard_out, make_stamp, new_run_id, payload_hash, read_json, canonical, write_json

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULES = {"judge": judge_b, "group": grp_b, "categorize": cat_b}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m baselayer.consolidation.build", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("builder", choices=sorted(MODULES))
    p.add_argument("--claims", required=True, help="claims.json from `baselayer consolidate --stages claims`")
    p.add_argument("--overlap", help="judge: overlap.json")
    p.add_argument("--pairs", help="judge: extra candidate pairs, JSON list of [a, b] or {a, b}")
    p.add_argument("--min-jaccard", type=float, default=0.0, help="judge: Jaccard floor on overlap pairs")
    p.add_argument("--batch", type=int, default=8, help="judge: pairs per call (default 8, as the prototype)")
    p.add_argument("--always-on", help="group: always_on.json")
    p.add_argument("--split-batch", type=int, default=20, help="group: conditions per split call")
    p.add_argument("--triggers", help="categorize: triggers.json")
    p.add_argument("--min-categories", type=int, help="categorize: lower bound given to the model")
    p.add_argument("--max-categories", type=int, help="categorize: upper bound given to the model")
    p.add_argument("--thin-claims", type=int, default=3)
    p.add_argument("--thin-facts", type=int, default=10)
    p.add_argument("--out", required=True, help="output JSON file")
    p.add_argument("--work", required=True, help="checkpoint and probe directory")
    p.add_argument("--seed", type=int, help="presentation shuffle seed (default per builder)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--retries", type=int, default=2, help="re-asks after an error or unparseable reply")
    p.add_argument("--backend", choices=("api", "cli"), default="api")
    p.add_argument("--model", help="api default claude-opus-5; cli default opus")
    p.add_argument("--plan-only", action="store_true", help="print the planned calls and price; call nothing")
    g = p.add_argument_group("cli backend")
    g.add_argument("--cli-cwd", help="child cwd, outside every project tree")
    g.add_argument("--canary", action="append", default=[], help="string the context probe must not find")
    g.add_argument("--canaries-file", help="file of canary strings, one per line (kept out of the repo)")
    g.add_argument("--timeout", type=int, default=900)
    g = p.add_argument_group("api backend")
    g.add_argument("--rates-confirmed", default=None)
    g.add_argument("--rate-in", type=float, default=None)
    g.add_argument("--rate-out", type=float, default=None)
    g.add_argument("--confirm-spend", type=float, default=None)
    g.add_argument("--effort", default=None, help="output_config.effort for the API call")
    return p


def make_backend(a, work: Path, protected: list[Path]):
    if a.backend == "api":
        return ApiBackend(a.model or ApiBackend.DEFAULT_MODEL, rates_confirmed=a.rates_confirmed,
                          rate_in=a.rate_in, rate_out=a.rate_out, confirm_spend=a.confirm_spend, effort=a.effort)
    if not a.cli_cwd:
        raise SystemExit("--backend cli needs --cli-cwd (a directory outside every project tree)")
    return ClaudeCliBackend(a.model or "opus", Path(a.cli_cwd), work, protected, timeout=a.timeout)


def planned(a, docs: dict, runner: CallRunner) -> list[dict]:
    if a.builder == "judge":
        from . import overlap as ov
        cmap = {c["id"]: c for c in docs["claims"]["claims"]}
        pairs = judge_b.candidate_pairs(docs["overlap"], a.min_jaccard, docs.get("pairs"), set(cmap))
        tasks = ov.judge_tasks(pairs, cmap, batch=a.batch, seed=a.seed)
        return [{"prompt_chars": len(t["prompt"]), "max_tokens": judge_b.MAX_TOKENS} for t in tasks]
    if a.builder == "group":
        g = grp_b.ModelTriggerGrouper(runner, seed=a.seed, split_batch=a.split_batch)
        return g.plan(docs["claims"]["claims"], list(docs["always_on"]["claims"]))
    b = cat_b.ModelCategoryBuilder(runner, seed=a.seed, lo=a.min_categories, hi=a.max_categories)
    call, _ = b.call(docs["triggers"]["triggers"])
    return [{"prompt_chars": len(call["prompt"]), "max_tokens": call["max_tokens"]}]


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    a.seed = a.seed if a.seed is not None else (20260928 if a.builder == "judge" else 20260930)
    need = {"judge": ["overlap"], "group": ["always_on"], "categorize": ["triggers"]}[a.builder]
    files = {"claims": Path(a.claims)}
    for n in need:
        v = getattr(a, n)
        if not v:
            print(f"{a.builder} needs --{n.replace('_', '-')}", file=sys.stderr)
            return 2
        files[n] = Path(v)
    if a.pairs:
        files["pairs"] = Path(a.pairs)
    for k, f in files.items():
        if not f.is_file():
            print(f"--{k} file not found: {f}", file=sys.stderr)
            return 2
    out, work = Path(a.out), Path(a.work)
    try:
        for d in (out.parent, work):
            guard_out(d, [])
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if out.resolve() in {f.resolve() for f in files.values()}:
        print("--out would overwrite an input", file=sys.stderr)
        return 2
    docs = {k: read_json(f) for k, f in files.items()}
    work.mkdir(parents=True, exist_ok=True)
    protected = [REPO_ROOT, *(f.resolve().parent for f in files.values()), out.resolve().parent]
    backend = make_backend(a, work, protected)
    runner = CallRunner(backend, CallStore(work / "calls.jsonl"), workers=a.workers, retries=a.retries)
    runner.auto_prepare = False
    plan = planned(a, docs, runner)
    print(f"{a.builder}: {len(plan)} planned calls, {sum(c['prompt_chars'] for c in plan):,} prompt chars "
          f"(backend {backend.name}, model {backend.model})")
    if a.plan_only and a.backend == "cli":
        print("plan only: nothing called (the subscription backend bills nothing)")
        return 0
    if a.backend == "cli":
        cans = list(a.canary)
        if a.canaries_file:
            cans += [ln.strip() for ln in Path(a.canaries_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
        import time
        probe_path = work / time.strftime("probe_%Y%m%dT%H%M%SZ.json", time.gmtime())  # one per run, never overwritten
        pr = backend.run_probe(cans, probe_path)
        print(f"context probe: clean={pr['clean']} canaries checked {pr['canaries_checked']}, found "
              f"{pr['canaries_found']}; stored {probe_path}")
        if not pr["clean"]:
            print("refusing to run: the child's context probe is not clean", file=sys.stderr)
            return 2
    try:
        est = backend.prepare(plan, a.builder)
    except SystemExit as e:  # spend.RatesNotConfirmed / SpendNotConfirmed: refused before any client exists
        print(str(e), file=sys.stderr)
        return 2
    print("price: " + ", ".join(f"{k} {v}" for k, v in est.items() if k in ("calls", "usd", "usd_worst",
                                                                           "ceiling_usd", "billing")))
    if a.plan_only:
        print("plan only: nothing called")
        return 0
    seed_input = canonical({"builder": a.builder, "inputs": {k: file_sha256(f) for k, f in files.items()},
                            "seed": a.seed, "model": backend.model, "backend": backend.name})
    try:
        if a.builder == "judge":
            doc = judge_b.build(docs["claims"], docs["overlap"], runner, min_jaccard=a.min_jaccard,
                                extra_pairs=docs.get("pairs"), batch=a.batch, seed=a.seed)
        elif a.builder == "group":
            doc = grp_b.build(docs["claims"], docs["always_on"], runner, seed=a.seed, split_batch=a.split_batch)
        else:
            doc = cat_b.build(docs["claims"], docs["triggers"], runner, seed=a.seed, lo=a.min_categories,
                              hi=a.max_categories, thin_claims=a.thin_claims, thin_facts=a.thin_facts)
    except UsageLimitStop as e:
        print(f"STOPPED on a usage limit; checkpoint kept at {work / 'calls.jsonl'}; rerun to resume. {e}",
              file=sys.stderr)
        return 3
    except RuntimeError as e:
        print(f"{a.builder}: FAILED: {e}", file=sys.stderr)
        return 1
    write_json(out, stamp_doc(a.builder, doc, files, docs, runner, seed_input))
    s = runner.summary()
    print(f"{a.builder}: wrote {out}; calls new {s['new_calls']}, replayed {s['replayed']}, failed "
          f"{len(s['failed'])}; models {s['models']}")
    return 1 if s["failed"] else 0


def stamp_doc(builder: str, doc: dict, files: dict, docs: dict, runner: CallRunner, seed_input: str) -> dict:
    inputs = {f"{k}.json" if k != "pairs" else "pairs": (payload_hash(docs[k]) if isinstance(docs[k], dict)
                                                         else file_sha256(files[k])) for k in files}
    params = dict(doc.get("params") or {}) | {"template": doc.get("template")}
    st = make_stamp(builder, Path(MODULES[builder].__file__), inputs, params, new_run_id(seed_input))
    s = runner.summary()
    st.update({"model_calls": s["new_calls"] + s["replayed"], "calls": s, "backend": runner.backend.provenance()})
    return {"stamp": st, **doc}


if __name__ == "__main__":
    sys.exit(main())
