"""(a) Corrections carry-forward: a statement a member check overturned must not come back.

Ported from an earlier standalone checker (2026-09-29). The rules live in a per-person JSON
file (path given with --corrections), one entry per correction id:

  {"corrections": [{"id": "<person>:CORR-001", "rules": [
      {"kind": "violation", "pattern": "..."},                       the overturned wording is present
      {"kind": "requires_nearby", "pattern": "...", "nearby": "...", "window": 250},
                                                                     a statement must carry its qualifier
      {"kind": "review", "pattern": "...", "nearby": "...", "window": 200, "ignore_quoted": true,
       "quoted_framing": "..."}                                      likely regression, a person decides
  ]}]}

What is scanned, and as what:
  prose     each claim's name, statement and Active_When, and every .md file in the spec
            directory that is not a layer file (the brief). This is the spec's own voice.
  fact      the text of every live fact a claim cites. A fact carrying the overturned version
            is reported against each claim that cites it (flag, never fail: the fact may be an
            accurate record of what the person said at the time).

`ignore_quoted` blanks quoted words before matching, because the person's quoted words are
evidence, not the spec's assertion. That exemption is too wide in prose: a claim can carry the
overturned framing THROUGH a quote ("serious illness ... ('the plant will not last the week')"). So a review
rule may name `quoted_framing`: in prose only, when the nearby pattern is found only inside a
quote within the window, and the unquoted text of the same window matches `quoted_framing`, the
claim is flagged for REVIEW. A bare quote with no such framing (an evidence line, a fact) is not.

Statuses: VIOLATION in prose -> fail; REVIEW in prose -> flag; a cited fact carrying either -> flag.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import CheckContext, CheckResult, CheckRun, live_facts, worst

NAME = "corrections"
DESCRIPTION = "overturned statements from the person's corrections registry must not return"
NEEDS = ("corrections",)
KINDS = ("violation", "requires_nearby", "review")

# the person's quoted words (double, curly, or single quotes of 8+ chars) are evidence, not assertions
QUOTED = re.compile(r'"[^"\n]{1,400}"|“[^”\n]{1,400}”|(?<![A-Za-z])\'[^\'\n]{8,400}\'(?![A-Za-z])')
LAYER_FILES = re.compile(r"^(anchors|core|predictions)(_v\d+)?(\.shard\d+of\d+)?\.md$")


class RulesError(ValueError):
    pass


def load_rules(path) -> dict:
    """Read and validate a corrections JSON file. Raises RulesError on anything malformed,
    because a rule that cannot be read cannot clear anything."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RulesError(f"cannot read corrections file {path}: {e}")
    corr = doc.get("corrections") if isinstance(doc, dict) else None
    if not isinstance(corr, list) or not corr:
        raise RulesError(f"{path}: 'corrections' must be a non-empty list")
    for c in corr:
        if not c.get("id") or not isinstance(c.get("rules"), list) or not c["rules"]:
            raise RulesError(f"{path}: every correction needs an id and at least one rule")
        for r in c["rules"]:
            if r.get("kind") not in KINDS:
                raise RulesError(f"{path}: {c['id']}: rule kind must be one of {KINDS}")
            if r["kind"] != "violation" and not r.get("nearby"):
                raise RulesError(f"{path}: {c['id']}: a {r['kind']} rule needs 'nearby'")
            for key in ("pattern", "nearby", "quoted_framing"):
                if r.get(key) is not None:
                    try:
                        re.compile(r[key])
                    except re.error as e:
                        raise RulesError(f"{path}: {c['id']}: bad {key} regex: {e}")
    return doc


def _rx(pattern, flags):
    return re.compile(pattern, re.I if "i" in (flags or "") else 0)


def scan_text(text: str, rules_doc: dict, context: str = "prose") -> list[dict]:
    """Findings in one text: {status, id, line, start, snippet, how}. `context` is 'prose' (the
    spec's own words: quoted_framing applies) or 'fact'/'evidence' (it does not)."""
    out, seen = [], set()
    unquoted = QUOTED.sub(lambda m: " " * len(m.group(0)), text)
    for corr in rules_doc["corrections"]:
        for r in corr["rules"]:
            body = unquoted if r.get("ignore_quoted") else text
            for m in _rx(r["pattern"], r.get("flags", "")).finditer(body):
                lo, hi = max(0, m.start() - r.get("window", 0)), m.end() + r.get("window", 0)
                around = body[lo:hi]
                how = "pattern"
                if r["kind"] == "violation":
                    status = "VIOLATION"
                elif r["kind"] == "requires_nearby":
                    if re.search(r["nearby"], around, re.I):
                        continue
                    status = "VIOLATION"
                else:  # review
                    if re.search(r["nearby"], around, re.I):
                        status = "REVIEW"
                    elif (context == "prose" and r.get("ignore_quoted") and r.get("quoted_framing")
                          and re.search(r["nearby"], text[lo:hi], re.I)
                          and re.search(r["quoted_framing"], around, re.I)):
                        status, how = "REVIEW", "framing_through_quote"
                    else:
                        continue
                line = text.count("\n", 0, m.start()) + 1
                key = (corr["id"], line)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"status": status, "id": corr["id"], "line": line, "start": m.start(), "how": how,
                            "snippet": " ".join(text[max(0, m.start() - 60):m.end() + 60].split())})
    return out


def _claim_text(c) -> str:
    return f"{c.name}\n{c.statement}\nActive when: {c.active_when}"


def run(ctx: CheckContext) -> CheckRun:
    path = ctx.options.get("corrections")
    params = {"corrections": str(path) if path else None}
    if not path:
        return CheckRun(NAME, "not_run", "no corrections file given (--corrections)", params)
    try:
        rules = load_rules(path)
    except RulesError as e:
        return CheckRun(NAME, "error", str(e), params)
    ids = [c["id"] for c in rules["corrections"]]
    tally = {i: {"violation": 0, "review": 0, "fact_carriers": set()} for i in ids}
    results = []
    fact_hits: dict[str, list] = {}
    for cl in ctx.spec.claims:
        hits = scan_text(_claim_text(cl), rules, "prose")
        carriers = []
        for f in live_facts(ctx, cl):
            if f.full_id not in fact_hits:
                fact_hits[f.full_id] = scan_text(f.text or "", rules, "fact")
            for h in fact_hits[f.full_id]:
                carriers.append((f.fid, h))
                tally[h["id"]]["fact_carriers"].add(f.fid)
        statuses = []
        reasons = []
        for h in hits:
            tally[h["id"]]["violation" if h["status"] == "VIOLATION" else "review"] += 1
            statuses.append("fail" if h["status"] == "VIOLATION" else "flag")
            reasons.append(f"{h['status']} {h['id']}" + (" (death-style framing through a quote)"
                                                          if h["how"] == "framing_through_quote" else "")
                           + f": ...{h['snippet']}...")
        for fid, h in carriers:
            statuses.append("flag")
            reasons.append(f"cites {fid}, which carries the overturned version of {h['id']} ({h['status']}): {h['snippet']}")
        st = worst(statuses)
        results.append(CheckResult(NAME, cl.qid, st, "; ".join(reasons) if reasons else "no correction rule fires",
                                   sorted({fid for fid, _ in carriers}),
                                   {"prose_hits": hits, "fact_hits": [{"fact": fid, **h} for fid, h in carriers]}))
    # text outside the claims: the brief and any other non-layer markdown
    spec_dir = Path(ctx.spec.spec_dir)
    files = sorted(p for p in spec_dir.glob("*.md") if not LAYER_FILES.match(p.name))
    for p in files:
        for h in scan_text(p.read_text(encoding="utf-8"), rules, "prose"):
            tally[h["id"]]["violation" if h["status"] == "VIOLATION" else "review"] += 1
            where = f"{p.name}:{h['line']}"
            results.append(CheckResult(NAME, None, "fail" if h["status"] == "VIOLATION" else "flag",
                                       f"{h['status']} {h['id']} in {where}: ...{h['snippet']}...", [where], {"hit": h}))
    summary = {"corrections": {i: {"violations": t["violation"], "reviews": t["review"],
                                   "fact_carriers": sorted(t["fact_carriers"])} for i, t in tally.items()},
               "clear": [i for i, t in tally.items() if not (t["violation"] or t["review"] or t["fact_carriers"])],
               "files_scanned": [p.name for p in files], "facts_scanned": len(fact_hits)}
    return CheckRun(NAME, "ran", "", params, results, summary)


def scan_facts(conn, rules_doc: dict) -> dict[str, list]:
    """Every live fact in a database whose text carries an overturned version: {fact id: hits}.
    Read-only (SELECT). For mapping a correction to the facts that carry it."""
    out = {}
    for fid, text in conn.execute("SELECT id, fact_text FROM memory_facts WHERE superseded_by IS NULL"):
        hits = scan_text(text or "", rules_doc, "fact")
        if hits:
            out[fid] = hits
    return out
