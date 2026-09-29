"""`baselayer verify-spec`: verify one authored specification against its corpus.

    baselayer verify-spec <spec_dir> --label subject98 --corpus <corpus dir or memory.db> --out <dir>
        [--referent] [--run-model --rater cli --rater-cwd <dir outside any project> [--model sonnet]]
        [--run-model --rater api --model <id> --confirm-api-spend <usd cap>]

Default is a dry run: every deterministic check runs, the model-judged tasks are
built and priced, and nothing calls a model. The only directory written is --out.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import VERIFY_VERSION
from .corpus import Corpus, find_db, open_readonly
from .definitions import DEFINITIONS, DEFINITIONS_VERSION, TURN_CONTRACT_VERSION
from .deterministic import (check_duplicates, check_existing, check_facts, check_grounding, check_practice,
                            finding, trigger_groups)
from . import model_checks as mc
from .pricing import DEFAULT_OUTPUT_TOKENS, estimate, format_estimate
from .raters import ApiRater, ClaudeCliRater, Rater, run_probe
from .report import write_reports
from .spec_io import load_spec

MODEL_CHECKS = ("support", "voice", "fidelity", "cross", "adjudicate")


# ---------------------------------------------------------------- write guard
def _is_data_dir(d: Path) -> bool:
    return (d / "identity_layers").is_dir() or (d / "database" / "memory.db").exists()


def guard_out(out: Path, protected: list[Path]) -> None:
    """--out must not sit inside or above the spec, the corpus, or any Base Layer data
    directory (one holding identity_layers/ or database/memory.db, e.g. the served
    memory_system/data)."""
    out = out.resolve()
    for p in protected:
        p = p.resolve()
        if out == p or p in out.parents or out in p.parents:
            raise ValueError(f"--out {out} overlaps protected path {p}")
    for d in [out, *out.parents]:
        if _is_data_dir(d):
            raise ValueError(f"--out {out} is inside a Base Layer data directory {d}")
    try:
        from baselayer import config
        served = (Path(config.PROJECT_ROOT) / "data").resolve()
        if out == served or served in out.parents:
            raise ValueError(f"--out {out} is inside the served data directory {served}")
    except ImportError:
        pass


def _served_db() -> Path | None:
    try:
        from baselayer import config
        return Path(config.DATABASE_FILE).resolve()
    except Exception:
        return None


def _file_sig(db: Path) -> tuple:
    out = []
    for suf in ("", "-wal", "-journal"):
        p = Path(str(db) + suf)
        out.append((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None)
    return tuple(out)


def _git_stamp() -> dict:
    here = Path(__file__).resolve().parent
    try:
        commit = subprocess.run(["git", "-C", str(here), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "--no-optional-locks", "-C", str(here), "status", "--porcelain", "--", "."], capture_output=True, text=True,
                                    timeout=10).stdout.strip())
    except Exception:
        commit, dirty = None, None
    # Repo-relative (turn contract §7): an absolute path writes the operator's home directory
    # into every report.
    from baselayer.turn_contract import code_path_of
    return {"git_commit": commit or None, "code_dirty": dirty, "code_path": code_path_of(__file__)}


# ---------------------------------------------------------------- task execution
def run_tasks(tasks: list[dict], rater: Rater, raw_dir: Path, workers: int, attempts: int = 3) -> dict:
    """Run each task, keeping every raw reply under raw_dir. A stored reply is reused only
    when it succeeded for the byte-identical prompt AND the same rater, so resuming an
    interrupted run is free and a changed prompt or rater is never answered from cache."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    rid = f"{rater.name}:{getattr(rater, 'model', '')}"

    def one(t):
        p = raw_dir / f"{t['key']}.json"
        sha = hashlib.sha256(t["prompt"].encode("utf-8")).hexdigest()
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("ok") and d.get("prompt_sha256") == sha and d.get("rater_id") == rid:
                d["reused"] = True
                return t["key"], d
        d = {}
        for a in range(attempts):
            r = rater.complete(t["prompt"])
            obj = mc.parse_json(r.text)
            err = r.error or mc.validate(t["kind"], obj, t["ids"])
            d = {"key": t["key"], "kind": t["kind"], "attempt": a, "ok": err is None, "error": err, "parsed": obj,
                 "text": r.text, "cost_usd": r.cost_usd, "model": r.model, "wall_s": r.wall_s,
                 "prompt_sha256": sha, "rater_id": rid}
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")
            tmp.replace(p)
            if err is None:
                break
        return t["key"], d
    if workers <= 1:
        return dict(one(t) for t in tasks)
    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, tasks))


def _voice_results(tasks, res):
    out = {}
    for t in tasks:
        d = res.get(t["key"], {})
        if not d.get("ok"):
            continue
        for it in d["parsed"]["items"]:
            m = t["map"][it["id"]]
            turn = it.get("turn")
            msg = m["turns"].get(str(turn)) if turn is not None else None
            # a turn the rater names is kept only if it was one of the excerpts it was shown
            out[m["fid"]] = {"voice": it["voice"], "turn_index": turn if msg else None, "turn_id": msg,
                             "conversation_id": m["conversation_id"]}
    return out


# ---------------------------------------------------------------- main
def build_parser(p: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    p = p or argparse.ArgumentParser(prog="baselayer verify-spec", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec_dir", help="directory holding anchors/core/predictions (.json, .md, or served *_v<N>.md)")
    p.add_argument("--label", required=True, help="spec label for qualified claim ids, e.g. subject98 (claim ids are only unique inside one spec)")
    p.add_argument("--corpus", required=True, help="corpus directory (containing data/database/memory.db) or a memory.db path")
    p.add_argument("--out", required=True, help="output directory; the only place this command writes")
    p.add_argument("--referent", action="store_true", help="document corpus: also judge whether each fact evidences the author or the document")
    p.add_argument("--run-model", action="store_true", help="actually run the model-judged checks (default: dry run, priced only)")
    p.add_argument("--rater", choices=["cli", "api"], default="cli", help="cli = claude -p on the subscription; api = API credits (explicit)")
    p.add_argument("--model", default=None, help="cli: alias or id (default sonnet); api: required model id")
    p.add_argument("--rater-cwd", default=None, help="cli: working directory for the child; must be outside every project tree")
    p.add_argument("--confirm-api-spend", type=float, default=None, help="api: USD cap; the run refuses if the upper estimate exceeds it")
    p.add_argument("--probe", action="store_true", help="run a context probe of the actual child first and store it beside the results")
    p.add_argument("--probe-canary", action="append", default=[], help="string whose presence in the probe answer means not blind (repeatable)")
    p.add_argument("--checks", default=",".join(MODEL_CHECKS), help=f"model checks to build/run, from {','.join(MODEL_CHECKS)}")
    p.add_argument("--cross-select", type=int, default=400, help="candidate claim pairs sent to the cross-claim check")
    p.add_argument("--cross-recall", type=int, default=100, help="random non-candidate pairs judged to estimate what the cut misses")
    p.add_argument("--assume-output-tokens", type=int, default=DEFAULT_OUTPUT_TOKENS)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-existing", action="store_true", help="skip the existing verify_provenance checks")
    p.add_argument("--snapshot", action="store_true", help="always read the corpus from a copy under --out "
                   "(automatic for this install's served database; use when anything may be writing the corpus)")
    return p


def _record_grounding_summary(profiles: dict) -> dict:
    """Totals of the per-claim grounding profiles: distinct record-only facts
    cited, claims citing any or resting only on them, and live citations by
    grounding and their spans by evidence_kind (summed over claims)."""
    gs = [p["grounding"] for p in profiles.values() if p.get("grounding")]
    by_g = {k: sum(g["facts"][k] for g in gs) for k in ("prose", "record_only", "unstamped")}
    by_s = {k: sum(g["spans"][k] for g in gs) for k in ("prose", "record", "missing")}
    return {"record_only_cited_facts": len({i for g in gs for i in g["record_only_fact_ids"]}),
            "claims_citing_record_only": sum(1 for g in gs if g["record_only_fact_ids"]),
            "claims_resting_only_on_record_only": sum(
                1 for g in gs if g["live"] and len(g["record_only_fact_ids"]) == g["live"]),
            "live_citations_by_grounding": by_g, "spans_by_evidence_kind": by_s}


def main(argv=None, rater: Rater | None = None) -> int:
    """`rater` is for tests: a FakeRater bypasses the CLI/API construction."""
    return execute(build_parser().parse_args(argv), rater)


def execute(a: argparse.Namespace, rater: Rater | None = None) -> int:
    spec_dir, out = Path(a.spec_dir).resolve(), Path(a.out).resolve()
    db = find_db(a.corpus).resolve()
    corpus_root = Path(a.corpus).resolve()
    protected = [spec_dir, corpus_root, db.parent]
    guard_out(out, protected)
    checks = [c.strip() for c in a.checks.split(",") if c.strip()]
    unknown = set(checks) - set(MODEL_CHECKS)
    if unknown:
        raise SystemExit(f"unknown checks: {sorted(unknown)}")
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    spec = load_spec(spec_dir, a.label)
    # the database this install serves over MCP may have a live writer (verify_claims deletes and
    # inserts): always read it from a copy. Any other corpus is copied only on --snapshot or when
    # its -wal/-journal is pending, and is checked for change after the run.
    force = a.snapshot or db == _served_db()
    db_before = _file_sig(db)
    conn, open_info = open_readonly(db, out / "_snapshot", force_snapshot=force)
    try:
        corpus = Corpus(conn, open_info)
        findings = [finding(f["check"], "warn" if f["check"] != "duplicate_claim_id" else "error",
                            [f["claim"]] if f.get("claim") else [], detail=f.get("detail", ""), field=f.get("field"))
                    for f in spec.load_findings]
        profiles, f1 = check_facts(spec, corpus)
        practice, f_prac = check_practice(spec, corpus)
        for q, p in practice.items():
            profiles[q]["practice"] = p
        grounding, f_grd = check_grounding(spec, corpus)
        for q, g in grounding.items():
            profiles[q]["grounding"] = g
        f1 = f1 + f_prac + f_grd
        dup_findings, pairs = check_duplicates(spec)
        groups, f3, gmeta = trigger_groups(spec)
        findings += f1 + dup_findings + f3
        existing = {}
        if not a.no_existing:
            existing, f4 = check_existing(spec, corpus)
            findings += f4

        # ---- model tasks
        tasks = {}
        if "support" in checks:
            tasks["support"] = mc.support_tasks(spec, profiles, a.referent)
        if "voice" in checks:
            tasks["voice"] = mc.voice_tasks(spec, profiles, corpus)
        if "fidelity" in checks and corpus.turn_columns:
            tasks["fidelity"] = mc.fidelity_tasks(spec, profiles, corpus)
        if "cross" in checks:
            tasks["cross"] = mc.cross_tasks(spec, pairs, a.cross_select, a.cross_recall)
        n_cont = sum(c.contested for c in spec.claims)
        live_cites = sum(1 for p in profiles.values() for r in p["facts"] if r["status"] == "live")
        n_cross = sum(len(t["ids"]) for t in tasks.get("cross", []))
        p2_upper = math.ceil((n_cont * 3 + live_cites + n_cross) / mc.ADJ_BATCH) if "adjudicate" in checks else 0
        p2_expected = math.ceil(len(spec.claims) / mc.ADJ_BATCH) if "adjudicate" in checks else 0
        route = a.rater if rater is None else "fake"
        model_name = a.model or ("sonnet" if a.rater == "cli" else "")
        est = estimate(tasks, model_name or "sonnet", "api" if a.rater == "api" else "cli", a.assume_output_tokens, p2_upper, p2_expected)
        est_text = format_estimate(est)
        print(est_text)

        model_meta = {"status": "dry_run", "checks": checks, "estimate": est, "estimate_text": est_text,
                      "tasks": {k: len(v) for k, v in tasks.items()},
                      "fidelity_note": None if corpus.turn_columns else "fidelity needs the turn-contract columns; not built"}
        model_results = {}
        if a.run_model:
            if rater is None:
                if a.rater == "api":
                    if not a.model:
                        raise SystemExit("--rater api needs an explicit --model")
                    if a.confirm_api_spend is None:
                        raise SystemExit("--rater api bills API credits: pass --confirm-api-spend <usd cap> after reading the estimate")
                    if "error" in est or est["total_upper_usd"] > a.confirm_api_spend:
                        raise SystemExit(f"refusing: upper estimate ${est.get('total_upper_usd')} exceeds cap ${a.confirm_api_spend}")
                    rater = ApiRater(a.model)
                else:
                    if not a.rater_cwd:
                        raise SystemExit("--rater cli needs --rater-cwd: a directory outside every project tree")
                    repo = Path(__file__).resolve().parents[3]
                    rater = ClaudeCliRater(model_name, Path(a.rater_cwd), out / "_rater", protected + [repo])
            if a.probe:
                run_probe(rater, a.probe_canary, out / "context_probe.json")
            model_meta["status"] = "ran"
            model_meta["rater"] = rater.provenance()
            model_results = run_model_checks(a, spec, profiles, corpus, tasks, rater, out / "raw", findings, checks)
            model_meta.update(model_results.pop("_meta"))
            model_meta["rater"] = rater.provenance()
        if not open_info.get("snapshot") and _file_sig(db) != db_before:
            findings.append(finding("corpus_changed_during_run", "error", detail="the corpus database or its "
                                    "sidecars changed while it was open immutable; rerun with --snapshot"))
    finally:
        conn.close()
        if open_info.get("snapshot"):
            shutil.rmtree(Path(open_info["snapshot"]).parent, ignore_errors=True)

    # tasks index without prompts (prompts are rebuilt deterministically)
    idx = {k: [{kk: vv for kk, vv in t.items() if kk not in ("prompt", "map", "pairs")} for t in v] for k, v in tasks.items()}
    (out / f"{a.label}.tasks.json").write_text(json.dumps(idx, indent=0), encoding="utf-8")

    sev = {}
    for f in findings:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    res_all = [r for p in profiles.values() for r in p["facts"]]
    voice_counts = {}
    for r in res_all:
        if r["status"] == "live":
            voice_counts[r.get("voice")] = voice_counts.get(r.get("voice"), 0) + 1
    # Which mode ran, per live cited fact (a fact is gated iff it carries a
    # turn_contract_version), and the one-word summary of it.
    voice_modes = {}
    for r in {r["id"]: r for r in res_all if r["status"] == "live"}.values():
        voice_modes[r.get("voice_mode")] = voice_modes.get(r.get("voice_mode"), 0) + 1
    voice_mode = ("none" if not voice_modes else "turn_contract" if set(voice_modes) == {"turn_contract"}
                  else "fallback" if "turn_contract" not in voice_modes else "mixed")
    summary = {
        "claims": len(spec.claims), "contested": sum(c.contested for c in spec.claims),
        "citations": sum(len(c.fact_ids) for c in spec.claims), "distinct_cited_facts": len({r["id"] for r in res_all}),
        "unresolved_citations": sum(1 for f in findings if f["check"] == "unresolved_citation"),
        "voice_of_live_citations": voice_counts, "findings_by_severity": sev,
        "trigger_groups": {k: len(v) for k, v in groups.items()},
        "practice_bounded_claims": dict(collections.Counter(
            p["practice"]["bounded"] for p in profiles.values() if p.get("practice", {}).get("bounded"))),
        "record_grounding": _record_grounding_summary(profiles),
    }
    report = {
        "meta": {"label": spec.label, "spec_dir": spec.spec_dir, "spec_files": spec.files, "n_claims": len(spec.claims),
                 "corpus": {k: v for k, v in open_info.items()},
                 "turn_columns": corpus.turn_columns, "turn_table": corpus.turn_table,
                 "voice_mode": voice_mode, "voice_modes": voice_modes,
                 "versions": {"verify": VERIFY_VERSION, "definitions": DEFINITIONS_VERSION,
                              "turn_contract_expected": TURN_CONTRACT_VERSION, **_git_stamp()},
                 "model": model_meta, "wall_s": round(time.time() - t0, 1),
                 "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "trigger_groups_meta": gmeta},
        "definitions": DEFINITIONS,
        "summary": summary,
        "claims": profiles,
        "trigger_groups": groups,
        "existing_machinery": existing,
        "model_results": model_results,
        "findings": findings,
    }
    jp, mp = write_reports(report, out)
    print(f"wrote {jp}\nwrote {mp}")
    failed = model_meta.get("failed_tasks") or []
    return 2 if failed else 0


def run_model_checks(a, spec, profiles, corpus, tasks, rater, raw_dir, findings, checks) -> dict:
    meta = {"failed_tasks": [], "counterfactual_usd": 0.0, "models_seen": {}}
    results = {}

    def account(res):
        for d in res.values():
            if not d.get("ok"):
                meta["failed_tasks"].append(d.get("key"))
            meta["counterfactual_usd"] += d.get("cost_usd") or 0
            for m in (d.get("model") or "").split(","):
                if m:
                    meta["models_seen"][m] = meta["models_seen"].get(m, 0) + 1
    phase1 = [t for k in ("support", "voice", "fidelity", "cross") for t in tasks.get(k, [])]
    res = run_tasks(phase1, rater, raw_dir, a.workers)
    account(res)
    support = {t["claim"]: res[t["key"]]["parsed"] for t in tasks.get("support", []) if res.get(t["key"], {}).get("ok")}
    per_support, fs = mc.interpret_support(profiles, support)
    findings += fs
    results["support"] = per_support
    vres = _voice_results(tasks.get("voice", []), res)
    per_voice, fv = mc.interpret_voice(profiles, vres)
    findings += fv
    results["voice"] = per_voice
    if tasks.get("fidelity"):
        fres = {}
        for t in tasks["fidelity"]:
            d = res.get(t["key"], {})
            if d.get("ok"):
                for it in d["parsed"]["items"]:
                    fres[t["map"][it["id"]]["fid"]] = {"label": it["label"], "reason": it.get("reason")}
        per_fid, ff = mc.interpret_fidelity(profiles, fres)
        findings += ff
        results["fidelity"] = per_fid
    cross = []
    for t in tasks.get("cross", []):
        d = res.get(t["key"], {})
        if d.get("ok"):
            rel = {it["id"]: it for it in d["parsed"]["items"]}
            for p in t["pairs"]:
                cross.append({**{k: p[k] for k in ("a", "b", "arm")}, "relation": rel[p["pid"]]["relation"],
                              "condition": rel[p["pid"]].get("condition")})
    findings += mc.interpret_cross(cross)
    results["cross"] = {"judged": len(cross),
                        "by_arm": {arm: {rel: sum(1 for c in cross if c["arm"] == arm and c["relation"] == rel)
                                         for rel in ("contradicts", "tensions", "duplicate", "compatible")}
                                   for arm in ("selected", "recall_sample")},
                        "relations": cross}
    if "adjudicate" in checks:
        pairs = mc.adjudicate_pairs(profiles, support, cross)
        vturns = {fid: v.get("turn_index") for fid, v in vres.items()}
        atasks = mc.adjudicate_tasks(pairs, profiles, corpus, vturns)
        print(f"phase 2: {len(pairs)} pairs in {len(atasks)} calls")
        ares = run_tasks(atasks, rater, raw_dir, a.workers)
        account(ares)
        adj = []
        for t in atasks:
            d = ares.get(t["key"], {})
            if d.get("ok"):
                v = {it["id"]: it for it in d["parsed"]["items"]}
                for p in t["pairs"]:
                    adj.append({**p, **{k: v[p["kid"]].get(k) for k in ("verdict", "condition", "which_fact", "own_words_support", "reason")}})
        findings += mc.interpret_adjudication(adj)
        results["adjudication"] = adj
        results["contested_confirmation"] = mc.contested_confirmation(profiles, adj)
    meta["counterfactual_usd"] = round(meta["counterfactual_usd"], 2)
    results["_meta"] = meta
    return results


if __name__ == "__main__":
    sys.exit(main())
