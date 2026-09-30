"""The per-chunk extraction ledger (turn contract, sequential and batch paths).

Every chunk a turn-contract extraction sends is one row here: a checkpointed block of input
with its own status. A conversation is the set of its blocks.

    status       meaning
    pending      planned or requeued, not settled yet
    done         called, gated and stored; `facts_stored` is what it added
    failed       its call failed: a content failure (refusal, unparseable or schema-invalid
                 reply, truncated again, input rejected by the API; counted in `attempts`)
                 or an access failure (network, timeout, 429, 5xx, auth, a batch result that
                 expired or was canceled; counted in `access_errors` only); retried by the
                 next run
    quarantined  failed its retries (MAX_CHUNK_ATTEMPTS calls), or can no longer be rebuilt
                 (`not_reproducible`), or quarantined by hand; never retried automatically
    split        stopped on max_tokens and was re-chunked at half its budget; its parts are
                 rows whose `parent_id` is this row's `block_id`

Identity is (conversation_id, chunk_key, input_char_budget, turns_upto): the chunk's body pieces,
the input budget it was built with and the turn prefix it was built from (0 = all turns), which
is exactly what it takes to rebuild it. `input_hash` is a hash of the chunk's exact call input
(prompt and output budget): a done chunk whose input changed is invalid and runs again.

Pre-ledger corpora. A conversation with an extraction_log row (facts_extracted >= 0) and no
ledger rows was extracted before the ledger existed and counts as DONE: nothing re-runs it. The
migration from `extraction_chunks_failed` keeps that rule explicit for the conversations that
had failed chunks: their failed rows move here, and one `done` row with chunk_key `*` (the
legacy block) carries the conversation's logged count.

The logged count in extraction_log is the sum of `facts_stored` over a conversation's done rows,
rewritten in the same transaction as each chunk's facts.

The model. A model change never re-runs a chunk automatically; it is acknowledged, recorded
and kept as a running backlog item (design decision 2026-09-29). Every
row records the extraction model of the attempt that settled it (`model`; 'unknown' for rows
settled before the ledger recorded it). A conversation logged before the ledger has no rows and
none is written for it. Work with no recorded model takes it, at read time, from the
`extraction_model` stamp on the facts it stored (existing corpora are backfilled with known
models where possible; design decision 2026-09-29; `classify_done`): one model, that model;
several, or one beside unstamped facts, 'mixed(...)', never one of them; none, 'unknown'.
`input_hash` does not cover
the model, so a model change invalidates nothing: done work made by another model is the MODEL
BACKLOG (`model_backlog`), acknowledged per configured model in `extraction_model_acks`, and
re-extracted only by a separate, deliberate action.

Failures. Only content failures count, never access to the API (design decision 2026-09-29). Only
a content failure adds to `attempts`, the quarantine count. An access failure (network,
timeout, 429, 5xx, overloaded, auth, a batch result that expired or was canceled) leaves the
row `failed` with its error and adds to `access_errors` instead.

Review requests. Naming an already extracted conversation, or the done legacy block of a
migrated one to `chunks retry`, re-extracts nothing; the request is recorded in
`extraction_review_requests` for a case-by-case review, and nothing else waits on it.

Set-aside chunks are stated beside every authored artifact, never inside its text
(design decision 2026-09-29): `gaps_manifest` is written as `coverage_gaps*.json` next to the layers, trees and
respec layers, stamped with the run id. A conversation with any quarantined chunk is marked
partial (conversation flag `extraction_partial`), not extracted.

This module is SQL plus the manifest's JSON; planning and running chunks live in extract_facts.
"""

import hashlib
import json
import time

LEDGER_TABLE = "extraction_chunks"
OLD_FAILED_TABLE = "extraction_chunks_failed"
LEGACY_KEY = "*"
ACKS_TABLE = "extraction_model_acks"
REVIEWS_TABLE = "extraction_review_requests"
UNKNOWN_MODEL = "unknown"
STATUSES = ("pending", "done", "failed", "quarantined", "split")
OPEN_STATUSES = ("pending", "failed")
# The first call plus at most two retries (the project's rule: retry at most twice).
MAX_CHUNK_ATTEMPTS = 3

_COLUMNS = ("conversation_id", "chunk_key", "input_char_budget", "turns_upto", "block_id",
            "parent_id", "input_hash", "plan", "path", "status", "attempts", "last_error",
            "facts_stored", "batch_id", "created_at", "updated_at", "model", "access_errors")
# Columns added after the ledger first shipped (7be4483). ensure_ledger adds them; a reader of
# a ledger that does not have them yet reads NULL (access_errors 0) and writes nothing.
_LATER_COLUMNS = (("model", "TEXT"), ("access_errors", "INTEGER NOT NULL DEFAULT 0"))
_SETTLED = "('done', 'failed', 'quarantined', 'split')"


def block_id(conv_id: str, chunk_key: str, budget: int, upto: int) -> str:
    """A short stable id for one row, for the CLI and for a split part's `parent_id`."""
    raw = f"{conv_id}\x00{chunk_key}\x00{int(budget)}\x00{int(upto or 0)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def table_exists(conn, name: str = LEDGER_TABLE) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _select_list(conn) -> str:
    """The SELECT list for _COLUMNS on this ledger. A column it does not have yet reads as NULL
    (access_errors as 0), so reading an older ledger needs no migration and writes nothing."""
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({LEDGER_TABLE})")}
    return ", ".join(c if c in have else
                     ("0" if c == "access_errors" else "NULL") + f" AS {c}" for c in _COLUMNS)


def _ensure_side_tables(conn) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {ACKS_TABLE} (
            conversation_id TEXT NOT NULL,
            block_id TEXT NOT NULL,           -- the ledger row, or the legacy block id of a
                                              -- conversation logged before the ledger
            model TEXT NOT NULL,              -- the model that made the work
            configured_model TEXT NOT NULL,   -- the configured model it was seen against
            acknowledged_at REAL NOT NULL,
            note TEXT,
            PRIMARY KEY (block_id, model, configured_model)
        )""")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {REVIEWS_TABLE} (
            conversation_id TEXT NOT NULL,
            requested_at REAL NOT NULL,
            reason TEXT,
            via TEXT,                         -- conv_id | conv_ids | chunks retry
            block_id TEXT                     -- the legacy block named by `chunks retry`
        )""")
    if not _has_column(conn, REVIEWS_TABLE, "block_id"):   # a table written before it
        conn.execute(f"ALTER TABLE {REVIEWS_TABLE} ADD COLUMN block_id TEXT")


def _has_column(conn, table: str, col: str) -> bool:
    return col in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure_ledger(conn) -> int:
    """Create the ledger if missing and migrate `extraction_chunks_failed` into it (then drop
    that table). Returns the number of rows migrated. Commits when it changed anything."""
    changed = not table_exists(conn)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            conversation_id TEXT NOT NULL,
            chunk_key TEXT NOT NULL,          -- JSON [[turn_id, start, end], ...] body pieces;
                                              -- '*' = the pre-ledger conversation as one block;
                                              -- a JSON list of turn ids = migrated row
            input_char_budget INTEGER NOT NULL,
            turns_upto INTEGER NOT NULL,      -- built from the first N turns; 0 = all
            block_id TEXT NOT NULL UNIQUE,
            parent_id TEXT,                   -- block_id of the chunk this part was split from
            input_hash TEXT,                  -- exact call input; NULL = not known (migrated)
            plan TEXT,                        -- JSON: the plan fields the call used
            path TEXT,                        -- sequential | batch | legacy
            status TEXT NOT NULL CHECK (status IN
                ('pending', 'done', 'failed', 'quarantined', 'split')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            facts_stored INTEGER NOT NULL DEFAULT 0,
            batch_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            model TEXT,                       -- extraction model of the attempt that settled
                                              -- it; 'unknown' = settled before it was recorded
            access_errors INTEGER NOT NULL DEFAULT 0,   -- access failures (never quarantine)
            PRIMARY KEY (conversation_id, chunk_key, input_char_budget, turns_upto)
        )""")
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({LEDGER_TABLE})")}
    for col, typ in _LATER_COLUMNS:
        if col not in have:                   # a ledger written before the column existed
            conn.execute(f"ALTER TABLE {LEDGER_TABLE} ADD COLUMN {col} {typ}")
            changed = True
    if conn.execute(f"SELECT 1 FROM {LEDGER_TABLE} WHERE model IS NULL AND status IN "
                    f"{_SETTLED} LIMIT 1").fetchone():
        # settled before the ledger recorded the model: say so, never guess
        conn.execute(f"UPDATE {LEDGER_TABLE} SET model = ? WHERE model IS NULL AND status IN "
                     f"{_SETTLED}", (UNKNOWN_MODEL,))
        changed = True
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{LEDGER_TABLE}_status "
                 f"ON {LEDGER_TABLE} (status)")
    if not (table_exists(conn, ACKS_TABLE) and table_exists(conn, REVIEWS_TABLE)
            and _has_column(conn, REVIEWS_TABLE, "block_id")):
        _ensure_side_tables(conn)
        changed = True
    migrated = 0
    if table_exists(conn, OLD_FAILED_TABLE):
        changed = True
        rows = conn.execute(
            f"SELECT conversation_id, chunk_key, input_char_budget, turns_upto, plan, path, "
            f"reason, attempts, batch_id, recorded_at FROM {OLD_FAILED_TABLE}").fetchall()
        convs = set()
        for (cid, key, budget, upto, plan, path, reason, attempts, bid, at) in rows:
            status = "quarantined" if reason == "not_reproducible" else "failed"
            conn.execute(
                f"INSERT OR IGNORE INTO {LEDGER_TABLE} (conversation_id, chunk_key, "
                f"input_char_budget, turns_upto, block_id, parent_id, input_hash, plan, path, "
                f"status, attempts, last_error, facts_stored, batch_id, created_at, updated_at, "
                f"model) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
                (cid, key, budget, upto, block_id(cid, key, budget, upto), plan, path, status,
                 attempts, reason, bid, at, at, UNKNOWN_MODEL))
            convs.add(cid)
            migrated += 1
        # The rest of each such conversation was stored before the ledger: one done block.
        for cid in convs:
            log = conn.execute("SELECT facts_extracted, processed_at FROM extraction_log "
                               "WHERE conversation_id = ?", (cid,)).fetchone()
            if log is not None and log[0] is not None and log[0] >= 0:
                conn.execute(
                    f"INSERT OR IGNORE INTO {LEDGER_TABLE} (conversation_id, chunk_key, "
                    f"input_char_budget, turns_upto, block_id, path, status, attempts, "
                    f"facts_stored, created_at, updated_at, model) "
                    f"VALUES (?, ?, 0, 0, ?, 'legacy', 'done', 1, ?, ?, ?, ?)",
                    (cid, LEGACY_KEY, block_id(cid, LEGACY_KEY, 0, 0), log[0], log[1],
                     log[1], UNKNOWN_MODEL))
        conn.execute(f"DROP TABLE {OLD_FAILED_TABLE}")
    if changed:
        conn.commit()
    return migrated


def load_rows(conn, conv_id: str) -> list:
    if not table_exists(conn):
        return []
    cur = conn.execute(f"SELECT {_select_list(conn)} FROM {LEDGER_TABLE} "
                       f"WHERE conversation_id = ? ORDER BY created_at, chunk_key", (conv_id,))
    return [dict(zip(_COLUMNS, r)) for r in cur.fetchall()]


def get_row(conn, conv_id: str, key: tuple):
    if not table_exists(conn):
        return None
    r = conn.execute(f"SELECT {_select_list(conn)} FROM {LEDGER_TABLE} WHERE "
                     f"conversation_id = ? AND chunk_key = ? AND input_char_budget = ? AND "
                     f"turns_upto = ?", (conv_id, key[0], key[1], key[2])).fetchone()
    return dict(zip(_COLUMNS, r)) if r else None


def upsert(conn, conv_id: str, key: tuple, **fields) -> None:
    """Insert the row for `key` = (chunk_key, budget, upto), or update the given fields of the
    existing one. The caller commits."""
    chunk_key, budget, upto = key[0], int(key[1]), int(key[2] or 0)
    now = time.time()
    ins = {"conversation_id": conv_id, "chunk_key": chunk_key, "input_char_budget": budget,
           "turns_upto": upto, "block_id": block_id(conv_id, chunk_key, budget, upto),
           "status": "pending", "attempts": 0, "facts_stored": 0,
           "created_at": now, "updated_at": now}
    ins.update({k: v for k, v in fields.items() if k in _COLUMNS})
    upd = {k: v for k, v in fields.items() if k in _COLUMNS}
    upd["updated_at"] = now
    cols = list(ins)
    conn.execute(
        f"INSERT INTO {LEDGER_TABLE} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT(conversation_id, chunk_key, input_char_budget, turns_upto) DO UPDATE SET "
        + ", ".join(f"{k} = excluded.{k}" for k in upd),
        [ins[c] for c in cols])


def delete_blocks(conn, block_ids) -> None:
    for bid in block_ids:
        conn.execute(f"DELETE FROM {LEDGER_TABLE} WHERE block_id = ?", (bid,))


def has_rows(conn, conv_id: str) -> bool:
    return table_exists(conn) and conn.execute(
        f"SELECT 1 FROM {LEDGER_TABLE} WHERE conversation_id = ? LIMIT 1",
        (conv_id,)).fetchone() is not None


def refresh_log(conn, conv_id: str) -> int:
    """extraction_log.facts_extracted := sum of facts_stored over the conversation's done rows.
    Only for a conversation that has ledger rows; a pre-ledger conversation's logged count is
    left as it is. The caller commits. Returns the logged count."""
    total = conn.execute(f"SELECT COALESCE(SUM(facts_stored), 0) FROM {LEDGER_TABLE} "
                         f"WHERE conversation_id = ? AND status = 'done'",
                         (conv_id,)).fetchone()[0]
    conn.execute("""
        INSERT INTO extraction_log (conversation_id, facts_extracted, processed_at)
        VALUES (?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
            facts_extracted = excluded.facts_extracted, processed_at = excluded.processed_at
    """, (conv_id, total, time.time()))
    return total


def open_conversations(conn) -> set:
    if not table_exists(conn):
        return set()
    return {r[0] for r in conn.execute(
        f"SELECT DISTINCT conversation_id FROM {LEDGER_TABLE} "
        f"WHERE status IN ('pending', 'failed')")}


def open_sql(alias: str = "c") -> str:
    """SQL condition: the conversation `alias`.id has a pending or failed chunk."""
    return (f"EXISTS (SELECT 1 FROM {LEDGER_TABLE} lx WHERE lx.conversation_id = {alias}.id "
            f"AND lx.status IN ('pending', 'failed'))")


def status_counts(conn) -> dict:
    out = {s: 0 for s in STATUSES}
    if table_exists(conn):
        for s, n in conn.execute(f"SELECT status, COUNT(*) FROM {LEDGER_TABLE} "
                                 f"GROUP BY status"):
            out[s] = n
    return out


def list_rows(conn, status=None, conv_id=None, limit=None) -> list:
    if not table_exists(conn):
        return []
    where, args = [], []
    if status == "open":
        where.append("status IN ('pending', 'failed')")
    elif status:
        where.append("status = ?")
        args.append(status)
    if conv_id:
        where.append("conversation_id = ?")
        args.append(conv_id)
    sql = (f"SELECT {_select_list(conn)} FROM {LEDGER_TABLE}"
           + (f" WHERE {' AND '.join(where)}" if where else "")
           + " ORDER BY conversation_id, created_at, chunk_key")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(zip(_COLUMNS, r)) for r in conn.execute(sql, args).fetchall()]


def body_turn_count(chunk_key: str) -> int:
    if chunk_key == LEGACY_KEY:
        return 0
    try:
        parsed = json.loads(chunk_key)
    except (TypeError, ValueError):
        return 0
    return len({p[0] if isinstance(p, list) else p for p in parsed})


def failure_kind(last_error) -> str:
    """WHY a chunk failed, as one word, from its last_error: truncated, unparseable, refusal,
    input_rejected (the API rejected the input), not_reproducible, manual, access (never
    quarantines) or other."""
    e = (last_error or "").strip()
    head = e.split(":", 1)[0].split(" ", 1)[0]
    if head == "max_tokens":
        return "truncated"
    if head in ("json_decode", "not_a_list", "not_an_object", "no_text", "unusable_response"):
        return "unparseable"
    if head == "refusal":
        return "refusal"
    if head == "error" or (head == "errored" and ("invalid_request_error" in e
                                                  or "request_too_large" in e)):
        return "input_rejected"
    if head in ("not_reproducible", "manual", "access"):
        return head
    return "other"


def coverage_gaps(conn) -> list:
    """Quarantined chunks: parts of the corpus no fact was extracted from. One entry each, with
    what a reader needs to find it again and WHY it failed."""
    return [{"conversation_id": r["conversation_id"], "block_id": r["block_id"],
             "chunk_key": r["chunk_key"], "input_char_budget": r["input_char_budget"],
             "turns_upto": r["turns_upto"], "body_turns": body_turn_count(r["chunk_key"]),
             "reason": failure_kind(r["last_error"]), "last_error": r["last_error"],
             "attempts": r["attempts"], "access_errors": r["access_errors"] or 0,
             "model": r["model"]}
            for r in list_rows(conn, status="quarantined")]


# -- the gaps manifest ---------------------------------------------------------------------

MANIFEST_NOTE = ("Quarantined chunks: parts of the corpus no fact was extracted from. The "
                 "specification text does not state them; this file does. Every conversation "
                 "listed in partial_conversations was extracted only in part.")


def gaps_manifest(conn, *, run_id, producer, accepted=None, output=None) -> dict:
    """The coverage-gaps manifest that travels with an authored artifact (design decision 2026-09-29):
    set-aside chunks are stated, but not inside the spec text. `conn` None means the ledger
    could not be read (no database given): the manifest says so instead of claiming none."""
    base = {"manifest": "coverage_gaps", "manifest_version": 1, "run_id": run_id,
            "producer": producer, "output": output,
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "accepted": accepted}
    if conn is None:
        return {**base, "checked": False, "ledger_present": None, "count": None,
                "partial_conversations": None, "gaps": None,
                "note": "The chunk ledger was not read (no --db given), so the coverage gaps "
                        "of this artifact are unknown, not zero."}
    gaps = coverage_gaps(conn) if table_exists(conn) else []
    return {**base, "checked": True, "ledger_present": table_exists(conn), "count": len(gaps),
            "partial_conversations": sorted({g["conversation_id"] for g in gaps}),
            "gaps": gaps, "note": MANIFEST_NOTE}


def write_manifest(path, manifest) -> None:
    """Write a manifest atomically (temp file, then replace): never a truncated file."""
    import os
    path = str(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    os.replace(tmp, path)


def read_only(db_path):
    """A read-only connection to a corpus database, for readers that must never write."""
    import sqlite3
    from pathlib import Path
    return sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)


# -- partial conversations -----------------------------------------------------------------

PARTIAL_FLAG = "extraction_partial"


def mark_extraction_state(conn, conv_id: str) -> bool:
    """A conversation with any quarantined chunk is PARTIAL, not extracted (design decision 2026-09-29):
    it carries the `extraction_partial` conversation flag and its needs_extraction mark is set
    (1), even when an earlier run had cleared it. Otherwise the flag is removed and the mark
    cleared, as before (a conversation with a pending or failed chunk is still selected
    through the ledger). Returns True when partial. The caller commits; it has just advanced
    the conversation's processed_at, or not touched it, so setting the mark never makes the
    conversation read as grown. A database without the turn tables has nothing to mark."""
    import sqlite3
    n = conn.execute(f"SELECT COUNT(*) FROM {LEDGER_TABLE} WHERE conversation_id = ? "
                     f"AND status = 'quarantined'", (conv_id,)).fetchone()[0] \
        if table_exists(conn) else 0
    try:
        if n:
            conn.execute("INSERT OR REPLACE INTO conversation_flags (conversation_id, flag, "
                         "detail) VALUES (?, ?, ?)",
                         (conv_id, PARTIAL_FLAG, f"{n} quarantined chunk(s): no fact was "
                          f"extracted from them (`baselayer chunks list --review`)"))
            conn.execute("UPDATE import_state SET needs_extraction = 1 "
                         "WHERE conversation_id = ?", (conv_id,))
        else:
            conn.execute("DELETE FROM conversation_flags WHERE conversation_id = ? AND flag = ?",
                         (conv_id, PARTIAL_FLAG))
            conn.execute("UPDATE import_state SET needs_extraction = 0 "
                         "WHERE conversation_id = ?", (conv_id,))
    except sqlite3.OperationalError:
        pass
    return bool(n)


def requeue(conn, block_ids=(), conv_id=None, statuses=("failed", "quarantined")) -> int:
    """Set chunks back to pending with their attempts reset, so they get a full set of attempts.
    Only rows in `statuses` move. The done legacy block (`*`) of a migrated conversation never
    moves (design decision 2026-09-29): naming it records a review request instead (`legacy_blocks`,
    `record_review`), so its facts stay in use and nothing re-extracts it. The caller commits.
    Returns the number of rows requeued."""
    n = 0
    marks = ",".join("?" * len(statuses))
    now = time.time()
    for bid in block_ids:
        n += conn.execute(
            f"UPDATE {LEDGER_TABLE} SET status = 'pending', attempts = 0, updated_at = ? "
            f"WHERE block_id = ? AND status IN ({marks})",
            (now, bid, *statuses)).rowcount
    if conv_id:
        n += conn.execute(
            f"UPDATE {LEDGER_TABLE} SET status = 'pending', attempts = 0, updated_at = ? "
            f"WHERE conversation_id = ? AND status IN ({marks})",
            (now, conv_id, *statuses)).rowcount
    return n


def done_legacy_blocks(conn, block_ids) -> list:
    """[(block_id, conversation_id)] for the named ids that are a done legacy block (`*`)."""
    out = []
    for bid in block_ids:
        r = conn.execute(f"SELECT conversation_id FROM {LEDGER_TABLE} WHERE block_id = ? AND "
                         f"chunk_key = ? AND status = 'done'", (bid, LEGACY_KEY)).fetchone()
        if r:
            out.append((bid, r[0]))
    return out


def quarantine(conn, block_id_: str, reason: str) -> int:
    """Quarantine one pending or failed chunk by hand (it will not be retried; `baselayer run`
    then needs --accept-gaps). The caller commits."""
    return conn.execute(
        f"UPDATE {LEDGER_TABLE} SET status = 'quarantined', last_error = ?, updated_at = ? "
        f"WHERE block_id = ? AND status IN ('pending', 'failed')",
        (f"manual: {reason}", time.time(), block_id_)).rowcount


def add_access_error(conn, block_id_: str) -> None:
    """Count one access failure on a row (it never counts toward quarantine). The caller
    commits."""
    conn.execute(f"UPDATE {LEDGER_TABLE} SET access_errors = access_errors + 1 "
                 f"WHERE block_id = ?", (block_id_,))


# -- the model backlog -------------------------------------------------------------------

UNSTAMPED = "unstamped"      # a fact with no extraction_model stamp, inside a backfilled mix


def _stamp_counts(conn) -> dict:
    """{conversation_id: [(source_turn_id, model, n), ...]} over every stored fact, superseded
    ones included (they still say what extracted the conversation); a fact with no stamp counts
    as UNSTAMPED. One grouped read. A corpus without the stamp column reads as no stamps, and
    nothing is altered."""
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(memory_facts)")}
    except Exception:
        return {}
    if "extraction_model" not in have or "source_conversation_id" not in have:
        return {}
    turn = "source_turn_id" if "source_turn_id" in have else "NULL"
    out = {}
    for cid, tid, model, n in conn.execute(
            f"SELECT source_conversation_id, {turn}, extraction_model, COUNT(*) "
            f"FROM memory_facts GROUP BY 1, 2, 3"):
        out.setdefault(cid, []).append((tid, model or UNSTAMPED, n))
    return out


def _chunk_turns(key):
    """The turn ids a ledger chunk key covers (a flat list of turn ids, or [[turn, start, end],
    ...]); None for the legacy block or a key that does not parse."""
    if key == LEGACY_KEY:
        return None
    try:
        parsed = json.loads(key)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list):
        return None
    return {p[0] if isinstance(p, list) and p else p for p in parsed}


def _resolve(models: dict):
    """(model, model_source) from {model: fact count}. One stamped model: that model. Several,
    or a stamped model beside unstamped facts: 'mixed(a,b,...)', never one of them. No stamp at
    all (no facts, or none stamped): 'unknown'."""
    stamped = [m for m in models if m != UNSTAMPED]
    if not stamped:
        return UNKNOWN_MODEL, "none"
    if len(models) == 1:
        return stamped[0], "facts"
    return "mixed(" + ",".join(sorted(models)) + ")", "facts"


def _backfilled(stamps: dict, cid: str, turns=None, exclude=frozenset()) -> dict:
    """{model: fact count} over one conversation's facts: only those on `turns` when given,
    else every fact whose turn is not in `exclude` (a fact with no turn id is never excluded)."""
    models = {}
    for tid, model, n in stamps.get(cid, ()):
        if turns is not None and tid not in turns:
            continue
        if turns is None and tid is not None and tid in exclude:
            continue
        models[model] = models.get(model, 0) + n
    return models


def classify_done(conn) -> list:
    """Every unit of done work with the model that made it: done ledger rows, and conversations
    logged before the ledger with no rows (as their legacy block id). Read-only.

    The model is the ledger row's when it recorded one (`model_source` 'ledger'). Otherwise it
    is BACKFILLED from the `extraction_model` stamp on the facts that work stored (existing
    corpora are backfilled with known models where possible; design decision 2026-09-29),
    at read time, rewriting nothing (`model_source` 'facts'; `models` = fact count per model):
    - a pre-ledger conversation: all of its facts;
    - a turn-keyed ledger row: the conversation's facts cited on the chunk's turns (a turn
      split across chunks lends its facts to each, so differing models there read as mixed);
    - the legacy block `*`: the conversation's facts on no turn another of its rows covers.
    Facts of more than one model, or of one model beside unstamped facts, read 'mixed(...)',
    listed and never resolved to one of them. No stamp at all reads 'unknown' (`model_source`
    'none')."""
    stamps = _stamp_counts(conn)
    items = []
    have_ledger = table_exists(conn)
    if have_ledger:
        rows = list_rows(conn)
        covered = {}
        for r in rows:
            t = _chunk_turns(r["chunk_key"])
            if t:
                covered.setdefault(r["conversation_id"], set()).update(t)
        for r in rows:
            if r["status"] != "done":
                continue
            item = {"conversation_id": r["conversation_id"], "block_id": r["block_id"],
                    "facts_stored": r["facts_stored"],
                    "kind": "legacy block" if r["chunk_key"] == LEGACY_KEY else "chunk"}
            if r["model"] and r["model"] != UNKNOWN_MODEL:
                item.update(model=r["model"], model_source="ledger", models=None)
            else:
                cid = r["conversation_id"]
                if r["chunk_key"] == LEGACY_KEY:
                    models = _backfilled(stamps, cid, exclude=covered.get(cid, set()))
                else:
                    turns = _chunk_turns(r["chunk_key"])
                    models = _backfilled(stamps, cid, turns=turns) if turns else {}
                model, source = _resolve(models)
                item.update(model=model, model_source=source, models=models or None)
            items.append(item)
    try:
        logged = conn.execute(
            "SELECT conversation_id, facts_extracted FROM extraction_log "
            "WHERE facts_extracted >= 0 ORDER BY conversation_id").fetchall()
    except Exception:                         # no extraction_log: nothing was extracted
        logged = []
    with_rows = ({r[0] for r in conn.execute(
        f"SELECT DISTINCT conversation_id FROM {LEDGER_TABLE}")} if have_ledger else set())
    for cid, n in logged:
        if cid in with_rows:
            continue
        models = _backfilled(stamps, cid)
        model, source = _resolve(models)
        items.append({"conversation_id": cid, "block_id": block_id(cid, LEGACY_KEY, 0, 0),
                      "model": model, "model_source": source, "models": models or None,
                      "facts_stored": n, "kind": "pre-ledger conversation"})
    return items


def _backlog_and_matched(conn, configured: str):
    """(backlog items, number of done units whose BACKFILLED model is `configured`)."""
    done = classify_done(conn)
    items = [i for i in done if i["model"] != configured]
    matched = sum(1 for i in done if i["model"] == configured and i["model_source"] == "facts")
    acks = {}
    if table_exists(conn, ACKS_TABLE):
        acks = {(b, m): at for b, m, at in conn.execute(
            f"SELECT block_id, model, acknowledged_at FROM {ACKS_TABLE} "
            f"WHERE configured_model = ?", (configured,))}
    for it in items:
        it["acknowledged_at"] = acks.get((it["block_id"], it["model"]))
    return items, matched


def model_backlog(conn, configured: str) -> list:
    """Done work not made by the configured model (`classify_done`): a recorded or backfilled
    model other than `configured`, a mix, or 'unknown'. Read-only. Each item carries
    `acknowledged_at`: None unless acknowledged against `configured` for that exact model or
    mix, so a mix that changes resurfaces."""
    return _backlog_and_matched(conn, configured)[0]


def backlog_counts(items) -> dict:
    """Over backlog items: known (one model, recorded or backfilled), mixed, unknown, and how
    many took their model from fact stamps."""
    unknown = sum(1 for i in items if i["model"] == UNKNOWN_MODEL)
    mixed = sum(1 for i in items if i["model"].startswith("mixed("))
    return {"known": len(items) - unknown - mixed, "mixed": mixed, "unknown": unknown,
            "from_facts": sum(1 for i in items if i.get("model_source") == "facts")}


def backlog_notice(conn, configured: str):
    """The one-line notice a run prints when the model backlog is not empty, else None."""
    items, matched = _backlog_and_matched(conn, configured)
    if not items:
        return None
    k = backlog_counts(items)
    open_ = sum(1 for i in items if not i["acknowledged_at"])
    convs = len({i["conversation_id"] for i in items})
    return (f"Model backlog: {len(items)} done block(s) in {convs} conversation(s) were not "
            f"extracted with the configured model {configured} ({k['known']} known by another "
            f"model, {k['mixed']} mixed, {k['unknown']} unknown; {k['from_facts']} of them read "
            f"from fact stamps); {open_} not acknowledged. {matched} other done block(s) matched "
            f"{configured} by fact stamps. Nothing re-runs them: `baselayer chunks list "
            f"--backlog`, `baselayer chunks ack-model`.")


def ack_model(conn, items, configured: str, note=None) -> int:
    """Record that these backlog items were seen against `configured`, with a timestamp. It
    re-runs nothing. The caller commits. Returns the number recorded."""
    _ensure_side_tables(conn)
    now = time.time()
    for it in items:
        conn.execute(f"INSERT OR REPLACE INTO {ACKS_TABLE} (conversation_id, block_id, model, "
                     f"configured_model, acknowledged_at, note) VALUES (?, ?, ?, ?, ?, ?)",
                     (it["conversation_id"], it["block_id"], it["model"], configured, now,
                      note))
    return len(items)


# -- review requests -----------------------------------------------------------------------

def record_review(conn, conv_id: str, reason=None, via=None, block_id=None) -> None:
    """A request to re-extract an already extracted conversation (naming it, or naming its
    legacy block to `chunks retry`): recorded for a case-by-case review, never acted on. The
    caller commits."""
    _ensure_side_tables(conn)
    conn.execute(f"INSERT INTO {REVIEWS_TABLE} (conversation_id, requested_at, reason, via, "
                 f"block_id) VALUES (?, ?, ?, ?, ?)",
                 (conv_id, time.time(), reason, via, block_id))


def list_reviews(conn) -> list:
    """Read-only: a table written before `block_id` existed reads it as None."""
    if not table_exists(conn, REVIEWS_TABLE):
        return []
    cols = ("conversation_id", "requested_at", "reason", "via", "block_id")
    sel = ", ".join(c if c != "block_id" or _has_column(conn, REVIEWS_TABLE, c)
                    else "NULL AS block_id" for c in cols)
    return [dict(zip(cols, r)) for r in conn.execute(
        f"SELECT {sel} FROM {REVIEWS_TABLE} ORDER BY requested_at")]


def clear(conn) -> None:
    """Delete every row (a full re-extraction's reset), and the model acknowledgements that
    were about them. Review requests stay: they are a record of what was asked. The caller
    commits."""
    if table_exists(conn):
        conn.execute(f"DELETE FROM {LEDGER_TABLE}")
    if table_exists(conn, ACKS_TABLE):
        conn.execute(f"DELETE FROM {ACKS_TABLE}")
    if table_exists(conn, OLD_FAILED_TABLE):
        conn.execute(f"DELETE FROM {OLD_FAILED_TABLE}")
