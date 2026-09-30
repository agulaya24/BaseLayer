"""The shape every modular check shares.

A check is a module with NAME, DESCRIPTION, NEEDS (the options it cannot run without) and
`run(ctx, **params) -> CheckRun`. It reads the spec and the read-only corpus through `ctx` and
returns one CheckResult per claim (or per file, for text outside the claims). Nothing here writes
anywhere; the orchestrator (verification.run) owns every write.

Status of one result:
  pass   nothing found
  flag   a person should look (a likely problem, or an input gap for this claim)
  fail   a mechanical defect or an overturned statement

Status of one check run:
  ran      results are complete
  not_run  an input it needs was not given (recorded, never read as a pass)
  error    it was asked to run and could not (bad input file); the command exits non-zero
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field

STATUSES = ("pass", "flag", "fail")
RUN_STATUSES = ("ran", "not_run", "error")
_RANK = {"pass": 0, "flag": 1, "fail": 2}


@dataclass
class CheckResult:
    check: str
    claim: str | None            # qualified '<label>:<id>'; None for a result about a file
    status: str                  # pass | flag | fail
    reason: str
    evidence_ids: list = field(default_factory=list)   # fact ids (F-xxxxxxxx), turn ids or file:line
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, not {self.status!r}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckRun:
    check: str
    status: str                  # ran | not_run | error
    reason: str = ""
    params: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def counts(self) -> dict:
        c = dict.fromkeys(STATUSES, 0)
        for r in self.results:
            c[r.status] += 1
        return c

    def to_dict(self) -> dict:
        return {"check": self.check, "status": self.status, "reason": self.reason, "params": self.params,
                "counts": self.counts(), "summary": self.summary, "results": [r.to_dict() for r in self.results]}


@dataclass
class CheckContext:
    spec: object                 # spec_io.Spec
    corpus: object               # corpus.Corpus (read-only connection)
    options: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)


def worst(statuses) -> str:
    s = "pass"
    for x in statuses:
        if _RANK[x] > _RANK[s]:
            s = x
    return s


def live_facts(ctx: CheckContext, claim) -> list:
    """The claim's cited facts that resolve live, each once, in citation order."""
    out, seen = [], set()
    for fid in claim.fact_ids:
        f = ctx.corpus.fact(fid)
        if f.status == "live" and f.full_id not in seen:
            seen.add(f.full_id)
            out.append(f)
    return out


# ---------------------------------------------------------------- dating and sessions
_UUID_TAIL = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)


def session_key(conversation_id: str | None) -> str | None:
    """One session imported under several conversation ids (a live session and a later copy of
    its database or history, e.g. 'dbcopy_<uuid>' and 'history_<uuid>') counts once: an id that
    ends in a UUID is keyed on that UUID."""
    if not conversation_id:
        return None
    m = _UUID_TAIL.search(conversation_id)
    return m.group(1).lower() if m else conversation_id


def fact_when(ctx: CheckContext, f) -> tuple[float | None, str]:
    """(unix time, source) for one live fact: the created_at of its first evidence span's turn,
    else of its source conversation. Source is 'turn', 'conversation' or 'none'."""
    cache = ctx.cache.setdefault("fact_when", {})
    if f.full_id in cache:
        return cache[f.full_id]
    ts, src = None, "none"
    for sp in f.evidence_spans or ():
        tid = sp.get("turn_id") if isinstance(sp, dict) else None
        t = ctx.corpus.turn(tid) if tid else None
        if t and t.get("created_at"):
            ts, src = float(t["created_at"]), "turn"
            break
    if ts is None and f.conversation_id:
        try:
            r = ctx.corpus.c.execute("SELECT created_at FROM conversations WHERE id = ?", (f.conversation_id,)).fetchone()
        except Exception:
            r = None
        if r and r[0]:
            ts, src = float(r[0]), "conversation"
    cache[f.full_id] = (ts, src)
    return ts, src


def day(ts: float | None, tz_offset_hours: float = 0.0) -> str | None:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%d", time.gmtime(ts + tz_offset_hours * 3600))


def fact_session(ctx: CheckContext, f) -> str | None:
    """Session of the first evidence span's turn, else of the fact's source conversation."""
    for sp in f.evidence_spans or ():
        tid = sp.get("turn_id") if isinstance(sp, dict) else None
        t = ctx.corpus.turn(tid) if tid else None
        if t:
            return session_key(t.get("conversation_id"))
    return session_key(f.conversation_id)
