"""Checks that need no model.

  resolution        every cited id resolves to one live fact
  voice             each live fact's voice, from the turn contract or, failing that, the conversation record
  turn_gate         turn-contract mode only: re-run the §5 gate and read the §7 stamp
  duplicates        identical names, shared evidence, contested-flag disagreement inside a pair
  trigger_groups    identical Active_When text, lexical groups, the lexical standing rule
  existing          the existing verify_provenance checks, run on the read-only connection
  practice          per claim, how its live cited facts spread across practices and
                    categories; `bounded:<practice>` when all of them carry one practice tag
  grounding         per claim, its live cited facts by `grounding` (prose / record_only /
                    unstamped) and their spans by `evidence_kind`; `record_grounded` when
                    any of them is record-only

Every finding carries qualified claim ids, fact ids and turn ids (empty when the
turn is not known, never invented).
"""
from __future__ import annotations

import collections
import itertools
import math
import re

from .definitions import SHARED_EVIDENCE_JACCARD, TRIGGER_GROUP_COSINE
from .spec_io import Spec, norm_name, norm_text
from .corpus import Corpus, toks

STANDING_RE = re.compile(r"^\s*(always|any|anything)\b", re.I)


def finding(check, severity, claims=(), fact_ids=(), turn_ids=(), conversation_ids=(), detail="", kind="deterministic", **extra):
    return {"check": check, "kind": kind, "severity": severity, "claims": list(claims), "fact_ids": list(fact_ids),
            "turn_ids": list(turn_ids), "conversation_ids": list(conversation_ids), "detail": detail, **extra}


# ---------------------------------------------------------------- resolution + voice + gate
def check_facts(spec: Spec, corpus: Corpus) -> tuple[dict, list[dict]]:
    """Per-claim fact table plus findings for resolution, voice and the turn gate."""
    profiles, out = {}, []
    for cl in spec.claims:
        rows = []
        if not cl.fact_ids:
            out.append(finding("no_citations", "error", [cl.qid], detail="claim cites no facts"))
        seen = set()
        for fid in cl.fact_ids:
            if fid in seen:
                out.append(finding("duplicate_citation", "info", [cl.qid], ["F-" + fid], detail="fact cited twice by one claim"))
                continue
            seen.add(fid)
            f = corpus.fact(fid)
            row = {"id": f.fid, "full_id": f.full_id, "status": f.status, "text": f.text,
                   "conversation_id": f.conversation_id, "turn_ids": [], "voice": None, "own": None}
            if f.status != "live":
                out.append(finding("unresolved_citation", "error", [cl.qid], [f.fid],
                                   conversation_ids=[f.conversation_id] if f.conversation_id else [],
                                   detail=f"cited fact is {f.status}", status=f.status, **f.extra))
            else:
                v = corpus.voice(f)
                row.update(voice=v["voice"], own=v.get("own"), turn_ids=v["turn_ids"], voice_mode=v["mode"],
                           conversation_ids=v["conversation_ids"])
                if v.get("gate"):
                    row["gate"] = v["gate"]
                    out.append(finding("turn_gate_failed", "error", [cl.qid], [f.fid], v["turn_ids"], v["conversation_ids"],
                                       detail="turn-contract gate re-run failed: " + ", ".join(v["gate"]), reasons=v["gate"]))
                if v["mode"] == "conversation_only" and v["voice"] == "no_subject_turns":
                    out.append(finding("voice_not_own", "error", [cl.qid], [f.fid], [], v["conversation_ids"],
                                       detail="source conversation has no subject turns"))
            rows.append(row)
        live = [r for r in rows if r["status"] == "live"]
        vc = collections.Counter(r["voice"] for r in live)
        profiles[cl.qid] = {"qid": cl.qid, "id": cl.id, "layer": cl.layer, "name": cl.name, "contested": cl.contested,
                            "active_when": cl.active_when, "facts": rows,
                            "resolution": {"cited": len(cl.fact_ids), "distinct": len(seen), "live": len(live),
                                           "ratio": round(len(live) / len(seen), 3) if seen else None},
                            "voice_counts": dict(vc)}
    return profiles, out


# ---------------------------------------------------------------- practice / domain bounding
UNTAGGED = "untagged"


def check_practice(spec: Spec, corpus: Corpus) -> tuple[dict, list[dict]]:
    """Per claim: the distribution of its live cited facts across practices
    (memory_facts.practice) and categories, and whether the claim is BOUNDED to one
    practice. Report only; nothing is edited.

    A claim is flagged `bounded:<p>` when every live cited fact carries the same practice
    tag p. An untagged fact is not a practice, so a claim resting on untagged facts is never
    flagged; a fact whose spans span two practices (`a+b`) bounds its claim to neither.
    On a database without the column, `available` is False and nothing is flagged."""
    available = "practice" in corpus.fact_cols
    per, out = {}, []
    for cl in spec.claims:
        live, seen = [], set()
        for fid in cl.fact_ids:
            f = corpus.fact(fid)
            if f.status == "live" and f.full_id not in seen:
                seen.add(f.full_id)
                live.append(f)
        by_p = collections.Counter((f.practice or UNTAGGED) for f in live)
        by_c = collections.Counter((f.category or "unknown") for f in live)
        top, top_n = (by_p.most_common(1)[0] if by_p else (None, 0))
        bounded = None
        if available and live and len(by_p) == 1 and top != UNTAGGED and "+" not in top:
            bounded = top
        per[cl.qid] = {"available": available, "live": len(live), "by_practice": dict(by_p),
                       "by_category": dict(by_c), "dominant": top if live else None,
                       "dominant_share": round(top_n / len(live), 3) if live else None,
                       "bounded": bounded}
        if bounded:
            out.append(finding("practice_bounded", "warn", [cl.qid], [f.fid for f in live],
                               detail=f"bounded:{bounded}: all {len(live)} live cited facts come from "
                                      f"practice {bounded}; present it as bounded to that practice, "
                                      f"not as a general trait", bounded=bounded))
    return per, out


# ---------------------------------------------------------------- grounding / record evidence
GROUNDING_KEYS = ("prose", "record_only", "unstamped")
SPAN_KIND_KEYS = ("prose", "record", "missing")


def check_grounding(spec: Spec, corpus: Corpus) -> tuple[dict, list[dict]]:
    """Per claim: its live cited facts by `grounding` and their spans by
    `evidence_kind` (TURN_CONTRACT.md §4a, §5). Report only.

    `unstamped` is a live fact with NULL grounding (stamped before the column, or
    a legacy fact); it is counted apart, never read as prose. A span without
    `evidence_kind` is `missing`. Record spans inside prose-grounded facts are
    counted too, since a mixed fact is admitted by default. A claim citing any
    record-only fact gets a `record_grounded` finding naming those facts: `warn`
    when every live cited fact is record-only, `info` otherwise. On a database
    without the column, `available` is False and nothing is flagged."""
    available = "grounding" in corpus.fact_cols
    per, out = {}, []
    for cl in spec.claims:
        live, seen = [], set()
        for fid in cl.fact_ids:
            f = corpus.fact(fid)
            if f.status == "live" and f.full_id not in seen:
                seen.add(f.full_id)
                live.append(f)
        facts = dict.fromkeys(GROUNDING_KEYS, 0)
        spans = dict.fromkeys(SPAN_KIND_KEYS, 0)
        rec_ids = []
        for f in live:
            g = f.grounding if f.grounding in ("prose", "record_only") else "unstamped"
            facts[g] += 1
            if g == "record_only":
                rec_ids.append(f.fid)
            for sp in f.evidence_spans or ():
                k = sp.get("evidence_kind") if isinstance(sp, dict) else None
                spans[k if k in ("prose", "record") else "missing"] += 1
        per[cl.qid] = {"available": available, "live": len(live), "facts": facts, "spans": spans,
                       "record_only_fact_ids": rec_ids}
        if rec_ids:
            only = len(rec_ids) == len(live)
            out.append(finding("record_grounded", "warn" if only else "info", [cl.qid], rec_ids,
                               detail=f"{len(rec_ids)} of {len(live)} live cited facts are record_only "
                                      f"(grounded by record spans only); {spans['record']} of "
                                      f"{sum(spans.values())} cited spans are records"
                                      + ("; the claim rests on records alone" if only else ""),
                               record_only=len(rec_ids), live=len(live)))
    return per, out


# ---------------------------------------------------------------- lexical similarity
def _tfidf(texts: list[str]) -> list[dict]:
    docs = [collections.Counter(toks(t)) for t in texts]
    df = collections.Counter(w for d in docs for w in d)
    n = len(docs)
    vecs = []
    for d in docs:
        v = {w: c * math.log((n + 1) / (df[w] + 1)) for w, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norm for w, x in v.items()})
    return vecs


def _cos(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


# ---------------------------------------------------------------- duplicates
def check_duplicates(spec: Spec) -> tuple[list[dict], list[dict]]:
    """Returns (findings, candidate pairs for the model cross-claim check)."""
    cl = spec.claims
    out, pairs = [], []
    stmt = _tfidf([f"{c.name} {c.statement}" for c in cl])
    trig = _tfidf([c.active_when for c in cl])
    groups = trigger_groups(spec)[0]
    group_of = collections.defaultdict(set)
    for g, ids in groups.items():
        for q in ids:
            group_of[q].add(g)
    for i, j in itertools.combinations(range(len(cl)), 2):
        a, b = cl[i], cl[j]
        fa, fb = {x[:8].lower() for x in a.fact_ids}, {x[:8].lower() for x in b.fact_ids}
        jac = _jaccard(fa, fb)
        same_name = norm_name(a.name) and norm_name(a.name) == norm_name(b.name)
        p = {"a": a.qid, "b": b.qid, "cos_statement": round(_cos(stmt[i], stmt[j]), 3),
             "cos_active_when": round(_cos(trig[i], trig[j]), 3), "shared_facts": len(fa & fb),
             "fact_jaccard": round(jac, 3), "same_trigger_group": bool(group_of[a.qid] & group_of[b.qid]),
             "same_name": bool(same_name)}
        pairs.append(p)
        shared = sorted("F-" + x for x in fa & fb)
        if same_name:
            out.append(finding("duplicate_identical_name", "warn", [a.qid, b.qid], shared,
                               detail=f"both claims are named {a.name!r}"))
        if jac >= SHARED_EVIDENCE_JACCARD:
            out.append(finding("duplicate_shared_evidence", "warn", [a.qid, b.qid], shared,
                               detail=f"cited-fact Jaccard {jac:.2f}", fact_jaccard=round(jac, 3)))
        if (same_name or jac >= SHARED_EVIDENCE_JACCARD) and a.contested != b.contested:
            out.append(finding("contested_flag_disagrees", "warn", [a.qid, b.qid], shared,
                               detail=f"duplicate candidates disagree on contested: {a.qid}={a.contested}, {b.qid}={b.contested}"))
    for p in pairs:
        p["score"] = round(p["cos_statement"] + 0.05 * min(p["shared_facts"], 4) + (0.03 if p["same_trigger_group"] else 0)
                           + (1.0 if p["same_name"] else 0), 4)
    pairs.sort(key=lambda p: -p["score"])
    return out, pairs


# ---------------------------------------------------------------- trigger groups
def trigger_groups(spec: Spec) -> tuple[dict, list[dict], dict]:
    cl = spec.claims
    out = []
    groups: dict[str, list[str]] = {}
    ident = collections.defaultdict(list)
    for c in cl:
        if c.active_when.strip():
            ident[norm_text(c.active_when)].append(c.qid)
        else:
            out.append(finding("active_when_missing", "error", [c.qid], detail="claim has no Active_When condition"))
    for k, (text, ids) in enumerate(sorted((t, v) for t, v in ident.items() if len(v) > 1)):
        groups[f"identical_{k:02d}"] = ids
        out.append(finding("active_when_identical", "info", ids, detail=f"{len(ids)} claims share the same trigger text"))
    # single-link lexical groups
    vecs = _tfidf([c.active_when for c in cl])
    parent = list(range(len(cl)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, j in itertools.combinations(range(len(cl)), 2):
        if _cos(vecs[i], vecs[j]) >= TRIGGER_GROUP_COSINE:
            parent[root(i)] = root(j)
    comp = collections.defaultdict(list)
    for i in range(len(cl)):
        comp[root(i)].append(cl[i].qid)
    k = 0
    for ids in sorted(comp.values(), key=lambda v: (-len(v), v)):
        if len(ids) > 1:
            groups[f"lexical_{k:02d}"] = ids
            k += 1
    standing = [c.qid for c in cl if STANDING_RE.match(c.active_when or "")]
    groups["standing_lexical"] = standing
    meta = {"standing_rule": STANDING_RE.pattern,
            "standing_note": "describes the trigger TEXT only; measured not to predict firing"}
    return groups, out, meta


# ---------------------------------------------------------------- existing machinery, read-only
def check_existing(spec: Spec, corpus: Corpus) -> tuple[dict, list[dict]]:
    """Run verify_provenance's per-claim checks on the read-only connection.

    Only the SELECT-only helpers are called. run_verification() and the MCP
    verify_claims tool DELETE+INSERT into claim_verification, so neither is used."""
    from baselayer import verify_provenance as vp
    checks = {"existence": None, "temporal": vp._check_temporal, "supersession": vp._check_contradiction,
              "cross_domain": vp._check_cross_domain, "recurrence": None}
    res, out = {}, []
    for cl in spec.claims:
        full = [corpus.fact(x).full_id for x in cl.fact_ids if corpus.fact(x).full_id]
        r = {}
        for name, fn in checks.items():
            try:
                if name == "existence":
                    vals = [vp._check_existence(corpus.c, x)[0] for x in full]
                    r[name] = {"pass": sum(v == 1 for v in vals), "of": len(vals)}
                elif name == "recurrence":
                    vals = [vp._check_recurrence(corpus.c, x)[0] for x in full]
                    r[name] = {"pass": sum(v == 1 for v in vals), "of": len(vals)}
                else:
                    code, ev = fn(corpus.c, full)
                    r[name] = {"result": code, "evidence": ev}
            except Exception as e:  # a check that cannot run is reported, never read as a pass
                r[name] = {"error": f"{type(e).__name__}: {e}"}
                out.append(finding("existing_check_could_not_run", "warn", [cl.qid], detail=f"{name}: {e}"))
        if r.get("supersession", {}).get("result") == 0:
            out.append(finding("cited_facts_supersede_each_other", "error", [cl.qid],
                               detail=r["supersession"]["evidence"]))
        if r.get("temporal", {}).get("result") == 0:
            out.append(finding("temporal_future_fact", "warn", [cl.qid], detail=r["temporal"]["evidence"]))
        res[cl.qid] = r
    return res, out
