"""Open a corpus database without writing to it, and answer fact, voice and turn questions.

Why not just `mode=ro`: on a WAL-mode database a read-only connection still
touches the `-shm` file next to it (observed on 2026-09-24: a `mode=ro` PRAGMA
read updated the shm mtime of a live corpus). So:
  - WAL with an empty or absent `-wal`, no `-journal`: open `mode=ro&immutable=1`,
    which takes no locks and never touches a sidecar. Nothing is lost, because
    there is nothing un-checkpointed.
  - anything else (non-empty `-wal`, or a `-journal`): copy the database and its
    sidecars into a snapshot directory under --out and open the copy. The copy is
    complete; the corpus is untouched.
  - the database this install serves over MCP, or any corpus under --snapshot: always
    copied, because immutable=1 is only safe with no concurrent writer.
The open mode is recorded in the report, and an immutable open that sees the database
change during the run is reported as an error finding.
"""
from __future__ import annotations

import collections
import json
import math
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .definitions import (DOCUMENT_SOURCES, OWN_VOICE_CLASSES, RETIRING_CORRECTIONS,
                          TURN_CONTRACT_VERSION)

TURN_TABLE_COLUMNS = {"turn_id", "conversation_id", "speaker", "voice_class", "text"}
# docs/core/TURN_CONTRACT.md section 4a. `evidence_spans` is a JSON list of {"turn_id", "span"}.
FACT_TURN_COLUMNS = {"source_turn_id", "evidence_spans", "turn_contract_version"}
PREFERRED_TURN_TABLE = "turns"


def find_db(corpus: str | Path) -> Path:
    p = Path(corpus)
    if p.is_file():
        return p
    for rel in ("data/database/memory.db", "database/memory.db", "memory.db"):
        if (p / rel).is_file():
            return p / rel
    raise FileNotFoundError(f"no memory.db under {p}")


def _is_wal(db: Path) -> bool:
    with open(db, "rb") as f:
        head = f.read(20)
    return len(head) >= 20 and head[18] == 2 and head[19] == 2


def open_readonly(db: Path, snapshot_dir: Path, force_snapshot: bool = False) -> tuple[sqlite3.Connection, dict]:
    """immutable=1 is only safe with no concurrent writer, so a database something may be
    writing (the served one, where MCP verify_claims deletes and inserts) should be opened
    with force_snapshot=True: a copy is consistent even if the original changes mid-run."""
    db = Path(db)
    wal = Path(str(db) + "-wal")
    journal = Path(str(db) + "-journal")
    wal_mode = _is_wal(db)
    pending = force_snapshot or (wal.exists() and wal.stat().st_size > 0) or journal.exists()
    if not pending:
        uri = f"file:{db.as_posix()}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        info = {"db": str(db), "open_mode": "immutable (mode=ro&immutable=1)", "wal_mode": wal_mode, "snapshot": None}
    else:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        copy = snapshot_dir / db.name
        shutil.copy2(db, copy)
        for side in (wal, journal):
            if side.exists():
                shutil.copy2(side, snapshot_dir / side.name)
        conn = sqlite3.connect(str(copy))
        conn.execute("PRAGMA query_only=1")
        why = "forced (a writer may be live)" if force_snapshot else "pending -wal or -journal on the original"
        info = {"db": str(db), "open_mode": f"snapshot copy under --out ({why})",
                "wal_mode": wal_mode, "snapshot": str(copy)}
    conn.row_factory = sqlite3.Row
    return conn, info


def _columns(conn, table) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")}
    except sqlite3.Error:
        return set()


def _tables(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]


# ---------------------------------------------------------------- normalisation (turn contract §5)
_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'",
                         "“": '"', "”": '"', "„": '"', "‟": '"',
                         "′": "'", "″": '"', "`": "'"})


def norm_span(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(_QUOTES)).strip()


# ---------------------------------------------------------------- lexical helpers (excerpt SELECTION only)
_STOP = set("""a an the and or but of to in on for with at by from as is are was were be been being it its this that
these those their them they he she his her him i me my we our you your not no do does did has have had will would can
could should may might must than then so such very more most less into about over under after before when while which
who whom what how why where all any each both also just only own same other some there here out up down off user users
person""".split())
_WORD = re.compile(r"[a-z][a-z0-9'\-]+")


def toks(text: str) -> list[str]:
    return [w[:7] for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 2]


@dataclass
class FactRecord:
    cited: str                  # the id as cited, without F-
    status: str                 # live | superseded | corrected_<type> | missing | ambiguous
    full_id: str | None = None
    text: str | None = None
    conversation_id: str | None = None
    source_turn_id: str | None = None
    evidence_spans: list | None = None      # parsed section-4a list; None when absent or unparseable
    evidence_spans_raw: str | None = None
    turn_contract_version: str | None = None
    practice: str | None = None             # memory_facts.practice (turn-contract facts only)
    grounding: str | None = None            # memory_facts.grounding: prose | record_only | NULL (§5)
    category: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def gated(self) -> bool:
        """Mode is a property of the ROW, not the schema: init_database adds the
        turn-contract columns to every database, so a fact is gated iff its
        turn_contract_version is set."""
        return self.turn_contract_version is not None

    @property
    def evidence_span(self) -> str | None:
        """The spans as one readable string (for prompts). None without spans."""
        if not self.evidence_spans:
            return None
        return " | ".join(str(s.get("span", "")) for s in self.evidence_spans if isinstance(s, dict))

    @property
    def fid(self) -> str:
        return "F-" + self.cited


class Corpus:
    def __init__(self, conn: sqlite3.Connection, open_info: dict):
        self.c = conn
        self.open_info = open_info
        tables = _tables(conn)
        self.fact_cols = _columns(conn, "memory_facts")
        self.turn_table = None
        candidates = [t for t in tables if TURN_TABLE_COLUMNS <= _columns(conn, t)]
        if PREFERRED_TURN_TABLE in candidates:
            self.turn_table = PREFERRED_TURN_TABLE
        elif candidates:
            self.turn_table = candidates[0]
        # Whether the database CAN hold gated facts. It does not say any fact is
        # gated: that is decided per fact (FactRecord.gated).
        self.turn_columns = bool(self.turn_table) and FACT_TURN_COLUMNS <= self.fact_cols
        self.retired: dict[str, str] = {}
        if "user_corrections" in tables:
            for oid, t in conn.execute("SELECT original_fact_id, correction_type FROM user_corrections "
                                       "WHERE original_fact_id IS NOT NULL"):
                if t in RETIRING_CORRECTIONS:
                    self.retired[oid] = t
        self._facts: dict[str, FactRecord] = {}
        self._conv_cache: dict[str, list] = {}

    # -------------------------------------------------------------- facts
    def fact(self, cited: str) -> FactRecord:
        cited = cited[2:] if cited.upper().startswith("F-") else cited
        if cited in self._facts:
            return self._facts[cited]
        cols = ["id", "fact_text", "superseded_by", "source_conversation_id"]
        opt = [c for c in ("source_turn_id", "evidence_spans", "turn_contract_version", "practice", "category",
                          "grounding")
               if c in self.fact_cols]
        sel = ", ".join(cols + opt)
        rows = self.c.execute(f"SELECT {sel} FROM memory_facts WHERE id = ?", (cited,)).fetchall()
        if not rows:
            # prefix match; substr() keeps LIKE wildcards in the id from matching anything
            rows = self.c.execute(f"SELECT {sel} FROM memory_facts WHERE substr(id, 1, ?) = ?",
                                  (len(cited), cited.lower())).fetchall()
        if len(rows) != 1:
            rec = FactRecord(cited=cited, status="missing" if not rows else "ambiguous",
                             extra={"n_matches": len(rows)} if rows else {})
        else:
            r = rows[0]
            if r["superseded_by"]:
                st = "superseded"
            elif r["id"] in self.retired:
                st = "corrected_" + self.retired[r["id"]]
            else:
                st = "live"
            raw = r["evidence_spans"] if "evidence_spans" in opt else None
            rec = FactRecord(cited=cited, status=st, full_id=r["id"], text=r["fact_text"],
                             conversation_id=r["source_conversation_id"],
                             source_turn_id=r["source_turn_id"] if "source_turn_id" in opt else None,
                             evidence_spans=_parse_spans(raw), evidence_spans_raw=raw,
                             turn_contract_version=r["turn_contract_version"] if "turn_contract_version" in opt else None,
                             practice=r["practice"] if "practice" in opt else None,
                             grounding=r["grounding"] if "grounding" in opt else None,
                             category=r["category"] if "category" in opt else None,
                             extra={"superseded_by": r["superseded_by"]} if r["superseded_by"] else {})
        self._facts[cited] = rec
        return rec

    # -------------------------------------------------------------- turns (turn-contract mode)
    def turn(self, turn_id: str) -> dict | None:
        if not self.turn_table:
            return None
        r = self.c.execute(f"SELECT * FROM '{self.turn_table}' WHERE turn_id = ?", (turn_id,)).fetchone()
        return dict(r) if r else None

    def turns_of(self, conversation_id: str) -> list[dict]:
        rows = self.c.execute(f"SELECT * FROM '{self.turn_table}' WHERE conversation_id = ?", (conversation_id,)).fetchall()
        return sorted((dict(r) for r in rows), key=lambda t: _turn_order(t["turn_id"]))

    # -------------------------------------------------------------- messages (fallback mode)
    def messages(self, conversation_id: str) -> list:
        if conversation_id not in self._conv_cache:
            self._conv_cache[conversation_id] = self.c.execute(
                "SELECT id, role, content_text FROM messages WHERE conversation_id = ? ORDER BY sequence_order",
                (conversation_id,)).fetchall()
        return self._conv_cache[conversation_id]

    def conversation(self, conversation_id: str) -> dict | None:
        r = self.c.execute("SELECT id, source, title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return dict(r) if r else None

    # -------------------------------------------------------------- voice
    def voice(self, f: FactRecord) -> dict:
        """Deterministic voice of one live fact. Never invents a turn id.

        Mode is chosen per fact: turn-contract when the fact carries a contract
        version (and the database has the turn table), conversation-level
        fallback otherwise. A fact with turn grounding but no version is an
        anomaly (the extractor stamps every gated fact) and is reported as
        stamp_missing while being verified in fallback mode."""
        if self.turn_columns and f.gated:
            return self._voice_turn(f)
        out = self._voice_conversation(f)
        if self.turn_columns and (f.source_turn_id or f.evidence_spans_raw):
            out["gate"] = ["stamp_missing"]
        return out

    def _voice_turn(self, f: FactRecord) -> dict:
        """Re-run the section-5 gate on EVERY span, and read the section-7 stamp."""
        out = {"mode": "turn_contract", "turn_ids": [], "conversation_ids": [f.conversation_id] if f.conversation_id else []}
        gate = []
        if f.turn_contract_version != TURN_CONTRACT_VERSION:
            gate.append("stamp_mismatch")
        spans = f.evidence_spans
        if f.evidence_spans_raw is not None and spans is None:
            gate.append("spans_unparseable")
            return {**out, "voice": "unknown", "gate": gate}
        if not spans:
            gate.append("no_grounding")
            return {**out, "voice": "unknown", "gate": gate}
        voices, convs = [], []
        for item in spans:
            tid = item.get("turn_id") if isinstance(item, dict) else None
            t = self.turn(tid) if tid else None
            if t is None:
                if "no_turn" not in gate:
                    gate.append("no_turn")
                continue
            if t["turn_id"] not in out["turn_ids"]:
                out["turn_ids"].append(t["turn_id"])
            if t["conversation_id"] not in convs:
                convs.append(t["conversation_id"])
            vc = t["voice_class"]
            voices.append(vc)
            if vc not in OWN_VOICE_CLASSES and "not_own_voice" not in gate:
                gate.append("not_own_voice")
            span = norm_span(str(item.get("span") or ""))
            if (not span or span not in norm_span(t["text"])) and "span_not_found" not in gate:
                gate.append("span_not_found")
        if f.source_turn_id and isinstance(spans[0], dict) and spans[0].get("turn_id") != f.source_turn_id:
            gate.append("source_turn_mismatch")
        if convs:
            out["conversation_ids"] = convs
        if not voices:
            return {**out, "voice": "unknown", "gate": gate}
        # section 4a: the fact's voice is its first span's turn; own only if every span is own.
        return {**out, "voice": voices[0], "own": all(v in OWN_VOICE_CLASSES for v in voices), "gate": gate}

    def _voice_conversation(self, f: FactRecord) -> dict:
        out = {"mode": "conversation_only", "turn_ids": [], "turn_resolution": "conversation_only",
               "conversation_ids": [f.conversation_id] if f.conversation_id else []}
        if not f.conversation_id:
            return {**out, "voice": "no_conversation", "own": None}
        conv = self.conversation(f.conversation_id)
        if conv and conv.get("source") in DOCUMENT_SOURCES:
            return {**out, "voice": "document_import", "own": None}
        msgs = self.messages(f.conversation_id)
        if not msgs:
            return {**out, "voice": "no_messages", "own": None}
        if not any(m["role"] == "user" for m in msgs):
            return {**out, "voice": "no_subject_turns", "own": False}
        return {**out, "voice": "unresolved_turn_level", "own": None}

    # -------------------------------------------------------------- context for model checks
    def turn_context(self, turn_id: str, before: int = 2, after: int = 2, chars: int = 1200) -> dict | None:
        t = self.turn(turn_id)
        if t is None:
            return None
        ts = self.turns_of(t["conversation_id"])
        ids = [x["turn_id"] for x in ts]
        i = ids.index(turn_id)
        win = ts[max(0, i - before): i + after + 1]
        lines = []
        for x in win:
            mark = " (CITED)" if x["turn_id"] == turn_id else ""
            lines.append(f"  [{x['turn_id']} {x['speaker']}/{x['voice_class']}{mark}] {_clip(x['text'], chars)}")
        return {"conversation_id": t["conversation_id"], "turn_ids": [x["turn_id"] for x in win], "render": "\n".join(lines)}

    def excerpts(self, fact_text: str, conversation_id: str, k_user: int = 3, k_asst: int = 3, chars: int = 400) -> dict | None:
        """Pick candidate source passages for the model voice check.

        Lexical scoring here SELECTS what the rater reads; it never decides voice.
        (A lexical voice verdict was measured at 0.71 against a 0.73 base rate.)"""
        msgs = self.messages(conversation_id)
        if not msgs:
            return None
        ft = list(dict.fromkeys(toks(fact_text)))
        df = collections.Counter(t for m in msgs for t in set(toks(m["content_text"] or "")))
        n = len(msgs)
        w = {t: math.log((n + 1) / (df.get(t, 0) + 0.5)) for t in ft}
        scored = []
        for i, m in enumerate(msgs):
            s = set(toks(m["content_text"] or ""))
            scored.append((sum(w[t] for t in ft if t in s), i, m))
        pick = sorted((x for x in scored if x[2]["role"] == "user"), key=lambda x: (-x[0], x[1]))[:k_user]
        pick += sorted((x for x in scored if x[2]["role"] == "assistant"), key=lambda x: (-x[0], x[1]))[:k_asst]
        pick.sort(key=lambda x: x[1])
        conv = self.conversation(conversation_id) or {}
        return {"conversation_id": conversation_id, "title": conv.get("title"), "source": conv.get("source"), "n_msgs": n,
                "excerpts": [{"turn": i, "message_id": m["id"], "role": m["role"], "text": _clip(m["content_text"], chars)}
                             for _, i, m in pick]}

    def message_window(self, conversation_id: str, anchor: int | None, fact_text: str,
                       before: int = 2, after: int = 2) -> dict | None:
        msgs = self.messages(conversation_id)
        if not msgs:
            return None
        if anchor is None or not (0 <= anchor < len(msgs)):
            ex = self.excerpts(fact_text, conversation_id, k_user=1, k_asst=0)
            anchor = ex["excerpts"][0]["turn"] if ex and ex["excerpts"] else 0
        lo, hi = max(0, anchor - before), min(len(msgs), anchor + after + 1)
        lines = []
        for k in range(lo, hi):
            m = msgs[k]
            ch = 900 if m["role"] == "user" else 450
            lines.append(f"  [turn {k} {m['role']}{' (anchor)' if k == anchor else ''}] {_clip(m['content_text'], ch)}")
        return {"conversation_id": conversation_id, "message_ids": [msgs[k]["id"] for k in range(lo, hi)],
                "anchor_message_id": msgs[anchor]["id"], "render": "\n".join(lines)}


def _parse_spans(raw):
    """The section-4a list, or None when the column is empty or not a JSON list."""
    if raw is None or raw == "":
        return None
    try:
        v = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return v if isinstance(v, list) else None


def _turn_order(tid: str):
    tail = tid.rsplit(":", 1)[-1]
    parts = []
    for p in tail.split("."):
        parts.append(int(p) if p.isdigit() else 0)
    return parts


def _clip(text, n):
    t = (text or "").replace("\n", " ")
    return t[:n] + ("..." if len(t) > n else "")
