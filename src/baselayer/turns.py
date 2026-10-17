"""The turn table (docs/core/TURN_CONTRACT.md, section 1) and its bookkeeping.

Import writes one row per turn, or per segment when a subject turn contains pasted
material. Every row carries ``speaker`` (from the source's own role field),
``voice_class``, the text exactly as imported, and ``detector`` (the rule that assigned a
non-own class; NULL on citable rows). ``basis`` records why a citable row is citable
(for example a queued prompt recovered from an attachment record), so that
"detector IS NULL" keeps meaning "own voice".

Bookkeeping tables:

* ``turn_contract``: the contract version this database was built under. A database built
  under one version refuses rows from another.
* ``import_state``: one row per imported conversation with the content hash of its source.
  A changed hash means the source grew (re-import, mark for extraction) or was rewritten
  (flag, do not renumber).
* ``conversation_flags``: conversation-level observations such as an injection canary.
* ``import_exclusions``: what the local exclusion config kept out, by id, with the reason.
* ``import_redactions``: how many secrets of each kind import masked in each conversation
  (``baselayer.redaction``). Counts only; the secrets are never stored.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from baselayer.redaction import redact, redact_rows, row_counts
from baselayer.voice import (
    B_ALLOWLIST, B_OWN_WRITING, CITABLE_VOICE_CLASSES, SPEAKERS, TURN_CONTRACT_VERSION, VOICE_CLASSES,
)


def _in_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    segment INTEGER,
    speaker TEXT NOT NULL CHECK (speaker IN ({_in_list(SPEAKERS)})),
    voice_class TEXT NOT NULL CHECK (voice_class IN ({_in_list(VOICE_CLASSES)})),
    text TEXT NOT NULL,
    detector TEXT,
    basis TEXT,
    source TEXT,
    source_record_id TEXT,
    created_at REAL,
    char_start INTEGER,
    char_end INTEGER,
    duplicate_of TEXT,
    allowlisted INTEGER NOT NULL DEFAULT 0,
    turn_contract_version TEXT NOT NULL,
    practice TEXT,
    CHECK ((voice_class IN ({_in_list(CITABLE_VOICE_CLASSES)})) = (detector IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, ordinal, segment);
CREATE INDEX IF NOT EXISTS idx_turns_voice ON turns(voice_class);

CREATE TABLE IF NOT EXISTS turn_contract (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS import_state (
    conversation_id TEXT PRIMARY KEY,
    source TEXT,
    source_path TEXT,
    content_hash TEXT,
    n_turns INTEGER,
    revision INTEGER NOT NULL DEFAULT 1,
    status TEXT,
    needs_extraction INTEGER NOT NULL DEFAULT 1,
    imported_at REAL,
    turn_contract_version TEXT
);

CREATE TABLE IF NOT EXISTS conversation_flags (
    conversation_id TEXT NOT NULL,
    flag TEXT NOT NULL,
    detail TEXT,
    PRIMARY KEY (conversation_id, flag)
);

CREATE TABLE IF NOT EXISTS import_exclusions (
    key TEXT PRIMARY KEY,
    source TEXT,
    reason TEXT,
    excluded_at REAL
);

CREATE TABLE IF NOT EXISTS import_redactions (
    conversation_id TEXT NOT NULL,
    source TEXT,
    kind TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (conversation_id, kind)
);
"""


# `practice`: the practice a row's text is bounded to (for example a trade journal), set
# on rows re-classed by the own-writing rule; NULL elsewhere.
LATER_COLUMNS = (("practice", "TEXT"),)


class TurnContractMismatch(RuntimeError):
    pass


def ensure_turn_tables(conn):
    """Create the turn tables and stamp the contract version. Idempotent.

    Raises if the database was stamped under a different contract version: turns built
    under two contracts must not share a table.
    """
    conn.executescript(SCHEMA)
    # Columns added to turn-contract/1 after its first databases were built (amended in
    # place, D-108): a table created before them gains them here.
    have = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
    for col, typ in LATER_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE turns ADD COLUMN {col} {typ}")
    row = conn.execute("SELECT value FROM turn_contract WHERE key='version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO turn_contract(key, value) VALUES ('version', ?)",
                     (TURN_CONTRACT_VERSION,))
        conn.commit()
    elif row[0] != TURN_CONTRACT_VERSION:
        raise TurnContractMismatch(
            f"database turn table is stamped {row[0]!r}; this code writes "
            f"{TURN_CONTRACT_VERSION!r}. Build into a fresh corpus directory.")


@dataclass
class TurnRow:
    ordinal: int
    speaker: str
    voice_class: str
    text: str
    detector: str | None = None
    basis: str | None = None
    segment: int | None = None
    source_record_id: str | None = None
    created_at: float | None = None
    char_start: int | None = None
    char_end: int | None = None
    duplicate_of: str | None = None
    allowlisted: int = 0
    practice: str | None = None
    redactions: dict | None = None   # secrets masked in this row, by kind (never the secret)

    def turn_id(self, conversation_id: str) -> str:
        base = f"{conversation_id}:{self.ordinal}"
        return base if self.segment is None else f"{base}.{self.segment}"

    @property
    def citable(self) -> bool:
        return self.voice_class in CITABLE_VOICE_CLASSES


def apply_allowlist(conversation_id: str, rows: list, allowlist) -> int:
    """Re-class pasted segments whose turn id the subject allowlisted. Returns count."""
    n = 0
    for r in rows:
        if r.voice_class == "pasted" and r.turn_id(conversation_id) in allowlist:
            r.basis = f"{B_ALLOWLIST}({r.detector})"
            r.detector = None
            r.voice_class = "own_typed"
            r.allowlisted = 1
            n += 1
    return n


def apply_own_writing(rows: list, rule) -> int:
    """Re-class pasted segments the own-writing rule accepts (voice.OwnWritingRule):
    own_typed, basis `allowlist:own_writing_pasted`, the rule's practice tag. Runs after
    the manual allowlist, so a manually allowlisted row keeps its manual basis. Returns
    the count."""
    if rule is None:
        return 0
    n = 0
    for r in rows:
        if r.voice_class != "pasted" or r.duplicate_of:
            continue
        practice = rule.decide(r.text, r.detector)
        if practice is None:
            continue
        r.voice_class, r.detector, r.basis = "own_typed", None, B_OWN_WRITING
        r.allowlisted, r.practice = 1, practice
        n += 1
    return n


def _existing_rows(conn, conversation_id):
    return conn.execute(
        "SELECT turn_id, speaker, text FROM turns WHERE conversation_id=? "
        "ORDER BY ordinal, COALESCE(segment, -1)", (conversation_id,)).fetchall()


def _delete_conversation(conn, conversation_id):
    conn.execute("DELETE FROM turns WHERE conversation_id=?", (conversation_id,))
    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    conn.execute("DELETE FROM import_redactions WHERE conversation_id=?", (conversation_id,))


def set_flag(conn, conversation_id, flag, detail=None):
    conn.execute("INSERT OR REPLACE INTO conversation_flags(conversation_id, flag, detail) "
                 "VALUES (?, ?, ?)", (conversation_id, flag, detail))


def record_exclusion(conn, key, source, reason):
    """Record why a conversation is kept out, and remove it if an earlier import stored it.

    An exclusion added after a conversation was imported must still take effect: applying
    it only to future imports would leave the excluded text in the turn table, citable.
    Returns the number of turns removed. Facts already extracted from the conversation are
    counted and reported, not deleted here; removing them belongs to extraction.
    """
    removed = conn.execute("SELECT COUNT(*) FROM turns WHERE conversation_id=?",
                           (key,)).fetchone()[0]
    existed = conn.execute("SELECT 1 FROM conversations WHERE id=?", (key,)).fetchone()
    if removed or existed:
        _delete_conversation(conn, key)
        conn.execute("DELETE FROM import_state WHERE conversation_id=?", (key,))
        conn.execute("DELETE FROM conversations WHERE id=?", (key,))
        try:
            facts = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE source_conversation_id=? "
                                 "AND superseded_by IS NULL", (key,)).fetchone()[0]
        except sqlite3.OperationalError:
            facts = 0
        reason = f"{reason}; removed after import ({removed} turns)"
        msg = f"  WARNING: excluded conversation {key} had been imported; removed {removed} turns"
        if facts:
            reason += f"; {facts} extracted facts still cite it"
            msg += f"; {facts} extracted facts still cite it and must be removed"
        print(msg)
    conn.execute("INSERT OR REPLACE INTO import_exclusions(key, source, reason, excluded_at) "
                 "VALUES (?, ?, ?, ?)", (key, source, reason, time.time()))
    return removed


def _rows_from_db(conn, conversation_id):
    cols = ("ordinal", "speaker", "voice_class", "text", "detector", "basis", "segment",
            "source_record_id", "created_at", "char_start", "char_end", "duplicate_of",
            "allowlisted", "practice")
    return [TurnRow(**dict(zip(cols, r))) for r in conn.execute(
        f"SELECT {', '.join(cols)} FROM turns WHERE conversation_id=? "
        "ORDER BY ordinal, COALESCE(segment, -1)", (conversation_id,)).fetchall()]


def _rewrite_messages(conn, conversation_id):
    msgs = legacy_messages(conversation_id, _rows_from_db(conn, conversation_id))
    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO messages (id, conversation_id, parent_id, role, content_text, "
        "content_type, created_at, sequence_order) VALUES (:id, :conversation_id, :parent_id, "
        ":role, :content_text, :content_type, :created_at, :sequence_order)", msgs)
    conn.execute("UPDATE conversations SET message_count=? WHERE id=?", (len(msgs), conversation_id))


def sync_allowlist(conn, conversation_id: str, allowlist) -> int:
    """Bring stored rows in line with the current allowlist, regardless of content hash.

    Allowlisting a pasted segment re-classes it own_typed; removing it from the list
    restores the original class and detector (kept in ``basis``). The allowlist is meant
    to be edited AFTER import, so it cannot wait for the source file to change.
    """
    allow = set(allowlist)
    changed = 0
    for tid, det in conn.execute("SELECT turn_id, detector FROM turns WHERE conversation_id=? "
                                 "AND voice_class='pasted'", (conversation_id,)).fetchall():
        if tid in allow:
            conn.execute("UPDATE turns SET voice_class='own_typed', detector=NULL, basis=?, "
                         "allowlisted=1 WHERE turn_id=?", (f"{B_ALLOWLIST}({det})", tid))
            changed += 1
    # Only MANUAL entries are reverted here. A row the own-writing rule re-classed is also
    # allowlisted, but its basis carries no original detector and it is not on this list.
    for tid, basis in conn.execute("SELECT turn_id, basis FROM turns WHERE conversation_id=? "
                                   "AND allowlisted=1 AND basis LIKE ?",
                                   (conversation_id, B_ALLOWLIST + "(%")).fetchall():
        if tid not in allow:
            det = basis[len(B_ALLOWLIST) + 1:-1]
            conn.execute("UPDATE turns SET voice_class='pasted', detector=?, basis=NULL, "
                         "allowlisted=0 WHERE turn_id=?", (det, tid))
            changed += 1
    if changed:
        _rewrite_messages(conn, conversation_id)
    return changed


def legacy_messages(conversation_id: str, rows: list) -> list:
    """Rows for the legacy ``messages`` table, which the current extractor reads.

    Only citable subject text and assistant text reach it. Compaction summaries, tool
    results, harness prompts, pasted segments and duplicates stay in the turn table as
    context only, so the legacy path can no longer read them as the subject's words.
    Segmented turns contribute their citable segments, joined.
    """
    by_ord: dict = {}
    for r in rows:
        if r.duplicate_of:
            continue
        if r.speaker == "subject" and r.citable:
            role = "user"
        elif r.speaker == "assistant":
            role = "assistant"
        else:
            continue
        slot = by_ord.setdefault(r.ordinal, {"role": role, "parts": [], "row": r})
        slot["parts"].append(r.text)
    out = []
    for ordinal in sorted(by_ord):
        slot = by_ord[ordinal]
        r = slot["row"]
        out.append({
            "id": r.source_record_id or f"{conversation_id}:{ordinal}",
            "conversation_id": conversation_id,
            "parent_id": None,
            "role": slot["role"],
            "content_text": "\n".join(slot["parts"]),
            "content_type": "text",
            "created_at": r.created_at,
            "sequence_order": ordinal,
        })
    return out


def write_conversation(conn, *, conversation_id: str, source: str, rows: list,
                       content_hash: str, title: str = "", created_at=None, updated_at=None,
                       source_path: str | None = None, allowlist=frozenset(),
                       own_writing=None, force: bool = False) -> str:
    """Write one conversation's turns (and legacy messages). Returns a status:

    ``unchanged``  same content hash as the last import; nothing written.
    ``new``        first import.
    ``grown``      the source changed and every previously stored turn is an exact prefix
                   of the new turns (same ids, speaker and text): rewritten, revision
                   bumped, marked for extraction.
    ``upgraded``   the conversation existed from a pre-contract import; turns written.
    ``conflict``   the source changed and the stored turns are NOT a prefix of the new
                   ones. Nothing is written and the conversation is flagged, because
                   renumbering would silently move turn ids that facts may cite. Pass
                   ``force=True`` to rewrite anyway.
    """
    ensure_turn_tables(conn)
    # Secrets are masked before anything is compared or stored: the prefix check below
    # compares stored (masked) text, so masking after it would turn every grown session
    # holding a secret into a conflict. Every class is masked, context included, because
    # context turns are sent to the extraction model too.
    redact_rows(rows)
    title, title_counts = redact(title or "")
    apply_allowlist(conversation_id, rows, allowlist)
    # After masking: the trait score is read on the text as stored.
    apply_own_writing(rows, own_writing)
    state = conn.execute("SELECT content_hash, revision FROM import_state WHERE conversation_id=?",
                         (conversation_id,)).fetchone()
    new_ids = [(r.turn_id(conversation_id), r.speaker, r.text) for r in rows]
    revision = 1
    if state is not None:
        if state[0] == content_hash and not force:
            sync_allowlist(conn, conversation_id, allowlist)
            return "unchanged"
        old = [tuple(x) for x in _existing_rows(conn, conversation_id)]
        is_prefix = len(old) <= len(new_ids) and new_ids[:len(old)] == old
        if not is_prefix and not force:
            set_flag(conn, conversation_id, "non_prefix_change",
                     f"stored {len(old)} turns are not a prefix of {len(new_ids)} new turns")
            conn.execute("UPDATE import_state SET status='conflict' WHERE conversation_id=?",
                         (conversation_id,))
            conn.commit()
            return "conflict"
        status = "grown" if is_prefix else "rewritten"
        revision = (state[1] or 1) + 1
    else:
        pre = conn.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        status = "upgraded" if pre else "new"

    _delete_conversation(conn, conversation_id)
    conn.executemany(
        "INSERT INTO turns (turn_id, conversation_id, ordinal, segment, speaker, voice_class, "
        "text, detector, basis, source, source_record_id, created_at, char_start, char_end, "
        "duplicate_of, allowlisted, turn_contract_version, practice) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r.turn_id(conversation_id), conversation_id, r.ordinal, r.segment, r.speaker,
          r.voice_class, r.text, r.detector, r.basis, source, r.source_record_id, r.created_at,
          r.char_start, r.char_end, r.duplicate_of, r.allowlisted, TURN_CONTRACT_VERSION,
          r.practice)
         for r in rows])
    msgs = legacy_messages(conversation_id, rows)
    conn.execute(
        "INSERT OR REPLACE INTO conversations (id, title, created_at, updated_at, message_count, "
        "source) VALUES (?, ?, ?, ?, ?, ?)",
        (conversation_id, title, created_at, updated_at, len(msgs), source))
    conn.executemany(
        "INSERT OR IGNORE INTO messages (id, conversation_id, parent_id, role, content_text, "
        "content_type, created_at, sequence_order) VALUES (:id, :conversation_id, :parent_id, "
        ":role, :content_text, :content_type, :created_at, :sequence_order)", msgs)
    red = row_counts(rows) + title_counts
    conn.executemany(
        "INSERT INTO import_redactions (conversation_id, source, kind, n) VALUES (?, ?, ?, ?)",
        [(conversation_id, source, k, n) for k, n in sorted(red.items())])
    conn.execute(
        "INSERT OR REPLACE INTO import_state (conversation_id, source, source_path, content_hash, "
        "n_turns, revision, status, needs_extraction, imported_at, turn_contract_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (conversation_id, source, source_path, content_hash, len(rows), revision, status,
         time.time(), TURN_CONTRACT_VERSION))
    return status


def voice_distribution(conn, source: str | None = None) -> dict:
    """Counts and characters by (voice_class, detector or basis). Ids and numbers only."""
    q = ("SELECT voice_class, COALESCE(detector, basis) AS rule, COUNT(*), SUM(LENGTH(text)) "
         "FROM turns WHERE duplicate_of IS NULL")
    args = ()
    if source:
        q += " AND source=?"
        args = (source,)
    q += " GROUP BY voice_class, rule ORDER BY voice_class, rule"
    return {(v, r): (n, c) for v, r, n, c in conn.execute(q, args).fetchall()}
