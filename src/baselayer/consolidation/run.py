"""`baselayer consolidate`: run the consolidation stages over one authored specification.

    baselayer consolidate <spec_dir> --out <dir> [--stages claims,overlap,...]
        [--grouping grouping.json] [--categories assignment.json] [--subject NAME --possessive their]
        [--dedupe-basis evidence|judgements|external ...] [--always-on-rule literal|fire_rate|explicit ...]

Each stage reads its inputs from --out (or the spec dir, for `claims`) and writes one
file there, so any stage can be rerun alone or replaced by another implementation that
writes the same file. No stage calls a model. The only directory written is --out, which
may not overlap the spec dir, an input file, or any Base Layer data directory.
Exit 1 when the checks stage runs and any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import STAGES
from . import always_on as ao_mod
from . import categories as cat_mod
from . import checks as checks_mod
from . import dedupe as dd_mod
from . import overlap as ov_mod
from . import render as render_mod
from . import spec as spec_mod
from . import triggers as trig_mod
from .common import (canonical, file_sha256, guard_out, make_stamp, new_run_id, payload_hash, read_json,
                     sha256_text, write_json, write_text_atomic)

FILES = {"claims": "claims.json", "overlap": "overlap.json", "dedupe": "dedupe.json",
         "always_on": "always_on.json", "triggers": "triggers.json", "categories": "categories.json",
         "index": "index.json", "checks": "checks.json"}
SERVED, SERVED_STAMP = "served.txt", "served.stamp.json"


def build_parser(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("spec_dir", help="authored spec dir holding anchors/core/predictions .json (read only)")
    p.add_argument("--out", required=True, help="output dir; the only directory written")
    p.add_argument("--stages", default=",".join(STAGES),
                   help=f"comma list, run in pipeline order; default all: {','.join(STAGES)}")
    p.add_argument("--layers", default="anchors,core,predictions", help="layer files, in serving order")
    g = p.add_argument_group("overlap")
    g.add_argument("--min-shared", type=int, default=1, help="shared fact ids for a pair to be listed (default 1)")
    g.add_argument("--judge-tasks", action="store_true",
                   help="also write judge_tasks.json: the blind SAME/FACET/DISTINCT prompts for every "
                        "evidence-sharing pair. Builds text only; nothing is called")
    g = p.add_argument_group("dedupe")
    g.add_argument("--dedupe-basis", choices=("evidence", "judgements", "external"), default="evidence")
    g.add_argument("--jaccard-min", type=float, default=0.5, help="basis=evidence: Jaccard floor (default 0.5)")
    g.add_argument("--judgements", help="basis=judgements: JSON or JSONL of {a, b, label}")
    g.add_argument("--merge-labels", default="SAME", help="basis=judgements: labels that join a group")
    g.add_argument("--dedupe-map", help="basis=external: {\"source_to_group\": {claim: group}}")
    g = p.add_argument_group("always-on")
    g.add_argument("--always-on-rule", choices=("literal", "fire_rate", "explicit"), default="literal")
    g.add_argument("--always-on-phrases", help="rule=literal: ';'-separated opening phrases (default: the pre-registered rule)")
    g.add_argument("--fire-rates", help="rule=fire_rate: {\"rates\": {claim: rate}}")
    g.add_argument("--fire-threshold", type=float, default=0.80)
    g.add_argument("--always-on-claims", help="rule=explicit: comma list of claim ids")
    g = p.add_argument_group("triggers and categories")
    g.add_argument("--grouping", help="trigger grouping file; default: identity (one trigger per distinct condition)")
    g.add_argument("--categories", help="claim-level category assignment; default: one flat category")
    g.add_argument("--thin-claims", type=int, default=3)
    g.add_argument("--thin-facts", type=int, default=10)
    g = p.add_argument_group("render")
    g.add_argument("--subject", help="the person's name for the served headers; default: unnamed templates")
    g.add_argument("--possessive", default="their", help="pronoun in the fetch instruction (default their)")
    g.add_argument("--templates", help="JSON of template overrides: resident_header, index_header, fetch_instruction")
    return p


def _inputs_files(args) -> dict:
    return {k: Path(v) for k, v in (("grouping", args.grouping), ("categories", args.categories),
                                    ("judgements", args.judgements), ("dedupe_map", args.dedupe_map),
                                    ("fire_rates", args.fire_rates), ("templates", args.templates)) if v}


class Ctx:
    def __init__(self, args):
        self.args = args
        self.spec = Path(args.spec_dir)
        self.out = Path(args.out)
        self.layers = tuple(x.strip() for x in args.layers.split(",") if x.strip())
        self.ext = _inputs_files(args)
        seed = canonical({"spec": {f.name: file_sha256(f) for f in sorted(self.spec.glob("*.json"))},
                          "args": {k: v for k, v in vars(args).items() if k not in ("func",)}})
        self.run_id = new_run_id(seed)

    def load(self, name: str, required: bool = True):
        p = self.out / FILES[name]
        if not p.exists():
            if required:
                raise FileNotFoundError(f"{p.name} missing in --out: run the {name} stage first")
            return None
        return read_json(p)

    def ext_hash(self, key):
        return {key: file_sha256(self.ext[key])} if key in self.ext else {}

    def write(self, stage: str, name: str, doc: dict, inputs: dict, params: dict):
        doc = {"stamp": make_stamp(stage, Path(__file__).with_name(f"{stage}.py") if stage != "claims"
                                   else Path(spec_mod.__file__), inputs, params, self.run_id), **doc}
        write_json(self.out / FILES[name], doc)
        return doc


def _hashes(ctx: Ctx, *names) -> dict:
    return {FILES[n]: payload_hash(ctx.load(n)) for n in names}


def stage_claims(ctx: Ctx):
    doc = spec_mod.build(ctx.spec, ctx.layers)
    ctx.write("claims", "claims", doc, {f"spec/{k}": v for k, v in doc["sources"].items()}, {"layers": list(ctx.layers)})
    c = doc["counts"]
    return f"{c['claims']} claims, {c['fact_ids_unique']} distinct fact ids"


def stage_overlap(ctx: Ctx):
    cd = ctx.load("claims")
    doc = ov_mod.build(cd, ctx.args.min_shared)
    ctx.write("overlap", "overlap", doc, _hashes(ctx, "claims"), {"min_shared": ctx.args.min_shared})
    if ctx.args.judge_tasks:
        tasks = ov_mod.judge_tasks([(p["a"], p["b"]) for p in doc["pairs"]], spec_mod.by_id(cd))
        jt = {"note": "prompts only; this package never sends them", "tasks": tasks, "n_tasks": len(tasks),
              "prompt_chars": sum(len(t["prompt"]) for t in tasks)}
        write_json(ctx.out / "judge_tasks.json", {"stamp": make_stamp("overlap", Path(ov_mod.__file__),
                                                                      _hashes(ctx, "claims"), {"judge_tasks": True},
                                                                      ctx.run_id), **jt})
    d = doc["distribution"]
    return f"{d['pairs_sharing']} of {d['pairs_total']} pairs share evidence, max Jaccard {d['max_jaccard']}"


def stage_dedupe(ctx: Ctx):
    a = ctx.args
    cd = ctx.load("claims")
    od = ctx.load("overlap", required=a.dedupe_basis == "evidence")
    judg = ov_mod.load_judgements(ctx.ext["judgements"]) if a.dedupe_basis == "judgements" and "judgements" in ctx.ext else None
    ext = read_json(ctx.ext["dedupe_map"]) if a.dedupe_basis == "external" and "dedupe_map" in ctx.ext else None
    labels = tuple(x.strip() for x in a.merge_labels.split(",") if x.strip())
    doc = dd_mod.build(cd, od, basis=a.dedupe_basis, jaccard_min=a.jaccard_min, judgements=judg,
                       merge_labels=labels, external=ext)
    inputs = _hashes(ctx, "claims")
    if od is not None:
        inputs[FILES["overlap"]] = payload_hash(od)
    inputs.update(ctx.ext_hash("judgements") if judg is not None else {})
    inputs.update(ctx.ext_hash("dedupe_map") if ext is not None else {})
    ctx.write("dedupe", "dedupe", doc, inputs, {"basis": a.dedupe_basis, "jaccard_min": a.jaccard_min,
                                                "merge_labels": list(labels)})
    c = doc["counts"]
    return f"{c['multi_member_groups']} duplicate groups covering {c['claims_in_multi']} claims (basis {a.dedupe_basis})"


def stage_always_on(ctx: Ctx):
    a = ctx.args
    phrases = tuple(x.strip() for x in a.always_on_phrases.split(";")) if a.always_on_phrases else ao_mod.DEFAULT_PHRASES
    rates = read_json(ctx.ext["fire_rates"])["rates"] if a.always_on_rule == "fire_rate" and "fire_rates" in ctx.ext else None
    explicit = [x.strip() for x in (a.always_on_claims or "").split(",") if x.strip()]
    doc = ao_mod.build(ctx.load("claims"), rule=a.always_on_rule, phrases=phrases, rates=rates,
                       threshold=a.fire_threshold, claims=explicit)
    inputs = _hashes(ctx, "claims")
    inputs.update(ctx.ext_hash("fire_rates") if rates is not None else {})
    ctx.write("always_on", "always_on", doc, inputs, {"rule": a.always_on_rule, "phrases": list(phrases),
                                                      "threshold": a.fire_threshold, "claims": explicit})
    return f"{len(doc['claims'])} always-on: {', '.join(doc['claims'])}"


def stage_triggers(ctx: Ctx):
    grouping = read_json(ctx.ext["grouping"]) if "grouping" in ctx.ext else None
    doc = trig_mod.build(ctx.load("claims"), ctx.load("always_on"), grouping)
    inputs = _hashes(ctx, "claims", "always_on")
    inputs.update(ctx.ext_hash("grouping"))
    ctx.write("triggers", "triggers", doc, inputs, {"grouping": "file" if grouping else "identity"})
    s = doc["stats"]
    return f"{s['triggers']} triggers, {s['edges']} edges, {s['claims_on_2plus_triggers']} claims on 2+ triggers"


def stage_categories(ctx: Ctx):
    a = ctx.args
    assignment = read_json(ctx.ext["categories"]) if "categories" in ctx.ext else None
    doc = cat_mod.build(ctx.load("claims"), ctx.load("triggers"), assignment,
                        thin_claims=a.thin_claims, thin_facts=a.thin_facts)
    inputs = _hashes(ctx, "claims", "triggers")
    inputs.update(ctx.ext_hash("categories"))
    ctx.write("categories", "categories", doc, inputs, {"assignment": "file" if assignment else "flat",
                                                        "thin_claims": a.thin_claims, "thin_facts": a.thin_facts})
    return (f"{len(doc['categories'])} categories, empty {doc['empty_categories'] or 'none'}, "
            f"thin {doc['thin_categories'] or 'none'}")


def stage_render(ctx: Ctx):
    a = ctx.args
    over = read_json(ctx.ext["templates"]) if "templates" in ctx.ext else None
    cd, aod, td, catd = ctx.load("claims"), ctx.load("always_on"), ctx.load("triggers"), ctx.load("categories")
    dd = ctx.load("dedupe", required=False)
    text, index = render_mod.build(cd, aod, td, catd, dd, subject=a.subject, possessive=a.possessive,
                                   template_overrides=over)
    names = ["claims", "always_on", "triggers", "categories"] + (["dedupe"] if dd is not None else [])
    inputs = _hashes(ctx, *names)
    inputs.update(ctx.ext_hash("templates"))
    params = {"subject": a.subject, "possessive": a.possessive, "template_overrides": bool(over)}
    ctx.write("render", "index", index, inputs, params)
    write_text_atomic(ctx.out / SERVED, text)
    st = make_stamp("render", Path(render_mod.__file__), inputs, params, ctx.run_id)
    st.update({"served_sha256": sha256_text(text), "served_chars": len(text), "served_file": SERVED,
               "line_endings": "LF"})
    write_json(ctx.out / SERVED_STAMP, st)
    return f"served text {len(text)} chars, sha256 {sha256_text(text)[:16]}"


def stage_checks(ctx: Ctx):
    docs = {n: ctx.load(n, required=False) for n in ("claims", "overlap", "dedupe", "always_on", "triggers",
                                                      "categories", "index")}
    sp = ctx.out / SERVED
    served = sp.read_bytes().decode("utf-8") if sp.exists() else None
    sst = read_json(ctx.out / SERVED_STAMP) if (ctx.out / SERVED_STAMP).exists() else None
    res = checks_mod.run(ctx.spec, docs, served, sst)
    inputs = {FILES[n]: payload_hash(d) for n, d in docs.items() if d is not None}
    if served is not None:
        inputs[SERVED] = sha256_text(served)
    ctx.write("checks", "checks", res, inputs, {})
    print(checks_mod.format_checks(res))
    return f"{res['n_checks'] - len(res['failed'])}/{res['n_checks']} checks pass" + \
        (f"; FAILED {res['failed']}" if res["failed"] else "")


RUNNERS = {"claims": stage_claims, "overlap": stage_overlap, "dedupe": stage_dedupe, "always_on": stage_always_on,
           "triggers": stage_triggers, "categories": stage_categories, "render": stage_render,
           "checks": stage_checks}


def execute(args) -> int:
    spec = Path(args.spec_dir)
    if not spec.is_dir():
        print(f"spec dir not found: {spec}", file=sys.stderr)
        return 2
    want = [s.strip() for s in args.stages.split(",") if s.strip()]
    bad = [s for s in want if s not in STAGES]
    if bad:
        print(f"unknown stage(s) {bad}; stages are {', '.join(STAGES)}", file=sys.stderr)
        return 2
    ext = _inputs_files(args)
    for k, pth in ext.items():
        if not pth.is_file():
            print(f"--{k.replace('_', '-')} file not found: {pth}", file=sys.stderr)
            return 2
    try:
        guard_out(Path(args.out), [spec, *ext.values()])
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    Path(args.out).mkdir(parents=True, exist_ok=True)
    ctx = Ctx(args)
    print(f"consolidate run {ctx.run_id}: stages {', '.join(s for s in STAGES if s in want)} (no model calls)")
    failed = False
    for s in STAGES:
        if s not in want:
            continue
        try:
            msg = RUNNERS[s](ctx)
        except (FileNotFoundError, ValueError, KeyError) as e:
            print(f"  {s}: ERROR {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        print(f"  {s}: {msg}")
        if s == "checks" and "FAILED" in msg:
            failed = True
    return 1 if failed else 0


def main(argv=None) -> int:
    p = build_parser(argparse.ArgumentParser(prog="baselayer consolidate", description=__doc__,
                                             formatter_class=argparse.RawDescriptionHelpFormatter))
    return execute(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
