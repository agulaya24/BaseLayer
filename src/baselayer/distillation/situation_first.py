"""SITUATION-FIRST PREDICTIONS. A design-test alternative to the claim-first predictions layer.

The production predictions layer is authored CLAIM-FIRST: the author reads the whole package and
writes each claim with an `active_when` attached. Here the order is reversed:

  step 1  the author names SITUATIONS (conditions, Active_When-style) from the package, citing the
          fact ids that show the person in each one. No predictions yet.
  step 2  CODE routes facts to each situation, mechanically, in a fixed order:
            seed      the ids the author cited for the situation
            theme     every other id of a package theme that cites a seed
            contradiction  both sides of a package contradiction that touches a seed
            episode   (episode trees only) the other facts of a seed's episode that its leaf kept
                      (disposition theme or singular)
          capped at --route-cap per situation; the cap and every cut are recorded.
  step 3  the author writes the predictions, each naming its situation and citing ONLY facts routed
          to that situation. The citation gate runs as in author_from_package, then each claim's
          ids are checked against its own situation: foreign ids are stripped and counted, and a
          claim left with none (or naming no known situation) is dropped and counted.

Run: python -m baselayer.distillation.situation_first --package <predictions package> --tree <tree>
     --db <memory.db> --outdir <dir> --model claude-opus-5-5 --effort high
     --rates-confirmed <date> --confirm-spend <usd>
Outputs in --outdir: situations.json (step 1 + routing), predictions.json / .md, and
predictions.stamp.json. The default predictions path does not read any of this.
"""
import argparse
import json
import os
import sqlite3
import sys

_src = os.environ.get("BASELAYER_SRC")
if _src:
    sys.path.insert(0, _src)
elif not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import anthropic
from baselayer import turn_contract as _tc
from baselayer.distillation import author_from_package as afp
from baselayer.distillation import spend as _spend

SITUATION = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "S1, S2, ..."},
        "name": {"type": "string", "description": "Short name in UPPERCASE, three to five words."},
        "active_when": {"type": "string",
                        "description": "The concrete, recognisable circumstance, written as the "
                                       "condition under which a prediction would activate."},
        "why": {"type": "string", "description": "One sentence: what the cited facts show."},
        "fact_ids": {"type": "array", "items": {"type": "string"},
                     "description": "Fact ids that show this person in this situation, copied "
                                    "VERBATIM from the evidence."},
    },
    "required": ["id", "name", "active_when", "why", "fact_ids"],
    "additionalProperties": False,
}
SITUATIONS_SCHEMA = {
    "type": "object",
    "properties": {"situations": {"type": "array", "items": SITUATION}},
    "required": ["situations"],
    "additionalProperties": False,
}
PRED_CLAIM = {
    "type": "object",
    "properties": dict(afp.CLAIM["properties"],
                       situation_id={"type": "string",
                                     "description": "The id of the situation this prediction "
                                                    "belongs to (S1, S2, ...)."}),
    "required": afp.CLAIM["required"] + ["situation_id"],
    "additionalProperties": False,
}
PRED_SCHEMA = {
    "type": "object",
    "properties": {"layer": {"type": "string"}, "preamble": {"type": "string"},
                   "claims": {"type": "array", "items": PRED_CLAIM}},
    "required": ["layer", "preamble", "claims"],
    "additionalProperties": False,
}

STEP1 = """You are authoring the PREDICTIONS layer of a behavioural specification, SITUATION FIRST. There are three steps and this is step 1.

Step 1 (now): from the evidence below, name the SITUATIONS in which this person's behaviour can be anticipated: concrete, recognisable circumstances (an event, a trigger, a kind of moment), each written as the condition under which a prediction would activate. Where the evidence shows their behaviour changing with circumstance, name the circumstance that makes the difference as its own situation. Do not write predictions yet. For each situation cite the fact ids that show this person in it (at least one), copied exactly from the evidence. Name them S1, S2, ...
Step 2 (code, not you): the facts that bear on each situation are gathered mechanically from the ids you cite.
Step 3: you will write the predictions for each situation from only the facts gathered for it.

Emit the situations by calling the emit_situations tool. Do not invent ids and do not cite an id that does not appear below.
Do not name philosophy or psychology frameworks. Describe the behaviour.
Write in the third person, using they/them.
DERIVE ONLY FROM THE EVIDENCE BELOW. Do not add what you know about people in general."""

STEP3 = """You are authoring the PREDICTIONS layer of a behavioural specification, SITUATION FIRST. This is step 3 of 3.

Below are the situations you named in step 1. Under each are the facts gathered for it by code: the ids you cited, the other facts of the themes that share them, both sides of contradictions that touch them, and the rest of their episodes.

For each situation, write the predictions its facts support: how this person responds in that circumstance, and, where the facts show it, what changes the response. A situation its facts do not support gets no prediction. Each prediction's situation_id names its situation; its active_when states the circumstance; its fact_ids cite ONLY facts listed under that same situation, copied exactly. Mark contested: true where the facts disagree with each other, and carry the tension rather than resolving it. Name the predictions P1, P2, ...

Emit the layer by calling the emit_layer tool.
Do not name philosophy or psychology frameworks. Describe the behaviour.
Write in the third person, using they/them.
DERIVE ONLY FROM THE FACTS BELOW. Do not add what you know about people in general."""


def _id(f):
    return f.lstrip("F-").strip("[]")


def route(situations, pkg, tree, cap):
    """{situation id: [{"id": 8-char id, "why": seed|theme|contradiction|episode}]}, in that
    order, de-duplicated, at most `cap` per situation. Mechanical: no model call."""
    themes = pkg.get("themes") or []
    contra = pkg.get("contradictions") or []
    leaves = (tree or {}).get("leaves") or []
    ep_of, kept = {}, set()
    for lf in leaves:
        for f, e in (lf.get("_episode_of") or {}).items():
            ep_of[f] = e
        for f, v in (lf.get("dispositions") or {}).items():
            if v in ("theme", "singular"):
                kept.add(f)
    ep_order = [f for lf in leaves for f in (lf.get("_ids") or [])]
    out = {}
    for s in situations:
        seeds = [_id(f) for f in s.get("fact_ids") or []]
        got, seen = [], set()

        def add(f, why):
            if f not in seen and len(got) < cap:
                seen.add(f)
                got.append({"id": f, "why": why})
        for f in seeds:
            add(f, "seed")
        sset = set(seeds)
        for t in themes:
            ids = [_id(f) for f in t.get("fact_ids") or []]
            if sset & set(ids):
                for f in ids:
                    add(f, "theme")
        for c in contra:
            ids = [_id(f) for f in (c.get("a_fact_ids") or []) + (c.get("b_fact_ids") or [])]
            if sset & set(ids):
                for f in ids:
                    add(f, "contradiction")
        eps = {ep_of[f] for f in seeds if ep_of.get(f)}
        if eps:
            for f in ep_order:
                if ep_of.get(f) in eps and f in kept:
                    add(f, "episode")
        out[s["id"]] = got
    return out


def enforce_routing(claims, routed):
    """(kept claims, info). Each claim may cite only ids routed to its own situation."""
    allowed = {k: {x["id"] for x in v} for k, v in routed.items()}
    kept, dropped, stripped = [], [], 0
    for c in claims:
        ok = allowed.get(c.get("situation_id"), set())
        ids = [_id(f) for f in c.get("fact_ids") or []]
        keep = [f for f in ids if f in ok]
        stripped += len(ids) - len(keep)
        if keep:
            kept.append(dict(c, fact_ids=keep))
        else:
            dropped.append(c.get("id"))
    return kept, {"ids_stripped": stripped, "claims_dropped": dropped}


def fact_texts(db):
    c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    out = {fid[:8]: t for fid, t in c.execute(
        "SELECT id, fact_text FROM memory_facts WHERE superseded_by IS NULL")}
    c.close()
    return out


def step3_prompt(situations, routed, texts, pkg):
    words = {s["fact_id"]: s["own_words"] for s in
             (pkg.get("singularities_verified") or []) + (pkg.get("singularities_unverified") or [])
             if s.get("own_words")}
    L = [STEP3, ""]
    for s in situations:
        L.append("## %s %s" % (s["id"], s["name"]))
        L.append("Active when: %s" % s["active_when"])
        ids = {x["id"] for x in routed.get(s["id"], [])}
        th = [t["statement"] for t in pkg.get("themes") or []
              if ids & {_id(f) for f in t.get("fact_ids") or []}]
        for x in routed.get(s["id"], []):
            w = ('   own words: "%s"' % words[x["id"]]) if x["id"] in words else ""
            L.append("- [F-%s] %s%s" % (x["id"], texts.get(x["id"], "(text unavailable)"), w))
        if th:
            L.append("Themes these facts appear in: " + " | ".join(th))
        L.append("")
    return "\n".join(L)


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="the predictions handoff package")
    ap.add_argument("--tree", default=None, help="the predictions tree (episode routing)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--max-tokens", type=int, default=64000)
    ap.add_argument("--route-cap", type=int, default=60,
                    help="facts routed per situation, in routing order; cuts are recorded")
    ap.add_argument("--resume-step3", action="store_true",
                    help="reuse <outdir>/situations.json from an earlier run and send step 3 "
                         "only; step 1's recorded usage is carried into the stamp")
    _spend.add_rate_args(ap)
    _spend.add_spend_args(ap)
    a = ap.parse_args()
    pkg = json.load(open(a.package, encoding="utf-8"))
    if pkg.get("layer") != "predictions" or pkg.get("shard_manifest"):
        raise SystemExit("situation_first reads one unsharded predictions package")
    tree = json.load(open(a.tree, encoding="utf-8")) if a.tree else None
    cv = (pkg.get("stamp") or {}).get("turn_contract_version")
    rates = _spend.rates_from_args(a.model, a)
    p1 = STEP1 + "\n\n" + afp.render(pkg)
    texts = fact_texts(a.db)
    # Step 3's prompt does not exist until step 1 returns; its estimate assumes 20 situations
    # at the route cap, 160 chars a fact. The ceiling, checked before each call, bounds the run.
    est1, w1 = _spend.estimate_calls([len(p1)], _spend.MEASURED_AUTHOR_LAYER_OUT_TOKENS, rates,
                                     a.max_tokens)
    est3, w3 = _spend.estimate_calls([len(STEP3) + 20 * a.route_cap * 160],
                                     _spend.MEASURED_AUTHOR_LAYER_OUT_TOKENS, rates, a.max_tokens)
    est = est1 + est3
    print("ESTIMATE: $%.4f (step 1 + step 3, one attempt each); worst $%.4f" % (est, w1 + w3),
          flush=True)
    ceiling = _spend.plan_ceiling(est, a.confirm_spend)
    afp._GUARD = _spend.SpendGuard(rates, ceiling, label="situation_first")
    os.makedirs(a.outdir, exist_ok=True)
    cl = anthropic.Anthropic()
    sit_path = os.path.join(a.outdir, "situations.json")
    if a.resume_step3:
        # Step 1 is not re-sent. Its usage was written beside the situations when it ran, so a
        # run stopped between the steps (for example by its ceiling) keeps its measured cost.
        saved = json.load(open(sit_path, encoding="utf-8"))
        sits, u1 = saved["situations"], dict(saved.get("usage_step1") or {})
        if saved.get("route_cap") != a.route_cap:
            raise SystemExit("--resume-step3: situations.json was routed at cap %s, this run "
                             "asks for %s" % (saved.get("route_cap"), a.route_cap))
        print("step 1 reused from %s (%d situations)" % (sit_path, len(sits)), flush=True)
    else:
        u1 = {}
        d1, _, _ = afp.call_structured(cl, a.model, p1, SITUATIONS_SCHEMA, afp._supplied(pkg),
                                       maxtok=a.max_tokens, tool_name="emit_situations",
                                       effort=a.effort, usage=u1, items_key="situations")
        sits = d1["situations"]
    routed = route(sits, pkg, tree, a.route_cap)
    uncapped = route(sits, pkg, tree, 10 ** 6)
    routing_info = {s["id"]: {"routed": len(routed[s["id"]]),
                              "before_cap": len(uncapped[s["id"]]),
                              "by_reason": {w: sum(1 for x in routed[s["id"]] if x["why"] == w)
                                            for w in ("seed", "theme", "contradiction", "episode")}}
                    for s in sits}
    c1 = _spend.cost_usd(rates, u1.get("input_tokens", 0), u1.get("output_tokens", 0))
    with open(sit_path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump({"situations": sits, "routed": routed, "routing_info": routing_info,
                   "route_cap": a.route_cap, "usage_step1": u1, "cost_usd_step1": c1}, fh,
                  indent=1)
    os.replace(sit_path + ".tmp", sit_path)
    print("step 1: %d situations; routed facts per situation %s"
          % (len(sits), [v["routed"] for v in routing_info.values()]), flush=True)
    p3 = step3_prompt(sits, routed, texts, pkg)
    supplied = {x["id"] for v in routed.values() for x in v}
    u3 = {}
    d3, _, _ = afp.call_structured(cl, a.model, p3, PRED_SCHEMA, supplied, maxtok=a.max_tokens,
                                   tool_name="emit_layer", effort=a.effort, usage=u3)
    kept, info = enforce_routing(d3.get("claims") or [], routed)
    print("step 3: %d predictions, %d kept; %d foreign ids stripped; dropped %s"
          % (len(d3.get("claims") or []), len(kept), info["ids_stripped"], info["claims_dropped"]),
          flush=True)
    data = {"layer": "predictions", "preamble": d3.get("preamble") or "", "claims": kept,
            "mode": "situation_first"}
    json.dump(data, open(os.path.join(a.outdir, "predictions.json"), "w", encoding="utf-8"),
              indent=1)
    open(os.path.join(a.outdir, "predictions.md"), "w", encoding="utf-8").write(
        afp.render_claims(data))
    usage = {k: u1.get(k, 0) + u3.get(k, 0) for k in ("input_tokens", "output_tokens",
                                                      "attempts")}
    st = _tc.artifact_stamp("layer", code_file=__file__, layer="predictions", model=a.model,
                            turn_contract_version=cv, effort=a.effort,
                            prompt_hash=_tc.prompt_hash(STEP1 + STEP3),
                            input_hash=_tc.json_input_hash(pkg),
                            package_stamp_input_hash=(pkg.get("stamp") or {}).get("input_hash"),
                            tree_run_id=((tree or {}).get("stamp") or {}).get("run_id"),
                            mode="situation_first", route_cap=a.route_cap,
                            routing_info=routing_info, enforce_routing=info,
                            max_tokens=a.max_tokens, usage=usage,
                            usage_by_step={"situations": u1, "predictions": u3},
                            rates_per_mtok=[rates["in"], rates["out"]],
                            rates_source=rates["source"], rates_as_of=rates["as_of"],
                            spend_estimate_usd=round(est, 6), spend_ceiling_usd=ceiling)
    st["cost_usd"] = _spend.cost_usd(rates, usage["input_tokens"], usage["output_tokens"])
    json.dump(st, open(os.path.join(a.outdir, "predictions.stamp.json"), "w", encoding="utf-8"),
              indent=1)
    print("cost $%.4f -> %s" % (st["cost_usd"], a.outdir))


def main():
    try:
        return _main()
    finally:
        afp._GUARD = None


if __name__ == "__main__":
    main()
