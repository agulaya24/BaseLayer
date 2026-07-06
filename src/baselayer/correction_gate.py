"""
Correction gate: query-time fact filtering for the serving layer.

Filters superseded and manually corrected facts before they enter a
serving payload. Runs at query time, not extraction time, so corrections
take effect immediately without re-running the pipeline.

Two filter passes:
  1. ``superseded_by IS NULL`` on ``memory_facts`` (automatic pipeline
     supersessions, including contradiction-pipeline supersessions).
  2. ``user_corrections`` rows whose ``correction_type`` is a removal
     type (delete or supersede) and whose ``original_fact_id`` matches.

Public API:
  - ``filter_facts(conn, fact_ids)``: return only the fact IDs that pass
    both filters, preserving input order.
  - ``get_active_facts(conn, subject=None)``: return all active fact rows
    as dicts, optionally restricted to one subject.

This module is part of the ingestion/consistency layer that a
conversation-capture proxy calls per conversation (see live_extract).
"""

import logging
import sqlite3

logger = logging.getLogger("base-layer")

# user_corrections.correction_type values that remove a fact from serving.
# Matched case-insensitively: the CLI writes lowercase types, older tooling
# wrote uppercase.
REMOVAL_CORRECTION_TYPES = ("delete", "supersede")

# SQLite's default host-parameter limit is 999. Chunk IN(...) lists well
# below it so large fact sets do not raise "too many SQL variables".
_SQL_CHUNK_SIZE = 500


def _row_id(row, key="id"):
    """Return a column from either a sqlite3.Row or a plain tuple row."""
    return row[key] if isinstance(row, sqlite3.Row) else row[0]


def _chunks(items, size=_SQL_CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def filter_facts(conn, fact_ids: list[str]) -> list[str]:
    """Filter out superseded and manually corrected facts.

    Returns only the fact_ids that pass both filters, in input order:
      1. ``superseded_by IS NULL`` in memory_facts
      2. no delete/supersede correction in user_corrections
    """
    if not fact_ids:
        return []

    # Pass 1: drop superseded facts.
    surviving = set()
    for chunk in _chunks(fact_ids):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id FROM memory_facts WHERE id IN ({placeholders}) "
            f"AND superseded_by IS NULL",
            chunk,
        ).fetchall()
        surviving.update(_row_id(r) for r in rows)

    active_ids = [fid for fid in fact_ids if fid in surviving]
    if not active_ids:
        logger.info(
            "Correction gate: filtered all %d facts (superseded)", len(fact_ids)
        )
        return []

    # Pass 2: drop facts with a manual removal correction.
    corrected_ids = set()
    try:
        for chunk in _chunks(active_ids):
            ph = ",".join("?" for _ in chunk)
            type_ph = ",".join("?" for _ in REMOVAL_CORRECTION_TYPES)
            rows = conn.execute(
                f"SELECT DISTINCT original_fact_id FROM user_corrections "
                f"WHERE original_fact_id IN ({ph}) "
                f"AND LOWER(correction_type) IN ({type_ph})",
                (*chunk, *REMOVAL_CORRECTION_TYPES),
            ).fetchall()
            corrected_ids.update(_row_id(r, "original_fact_id") for r in rows)
    except sqlite3.OperationalError:
        # user_corrections table does not exist yet. Pass 1 already ran.
        pass

    result = [fid for fid in active_ids if fid not in corrected_ids]
    filtered_count = len(fact_ids) - len(result)
    if filtered_count > 0:
        logger.info(
            "Correction gate: filtered %d of %d facts", filtered_count, len(fact_ids)
        )
    return result


def get_active_facts(conn, subject: str = None) -> list[dict]:
    """Return all active (non-superseded, non-corrected) facts as dicts.

    Optionally restricted to one subject value in memory_facts.subject.
    """
    query = "SELECT * FROM memory_facts WHERE superseded_by IS NULL"
    params = []
    if subject:
        query += " AND subject = ?"
        params.append(subject)

    rows = conn.execute(query, params).fetchall()
    all_ids = [_row_id(r) for r in rows]

    # Remove manually corrected facts.
    active_ids = set(filter_facts(conn, all_ids))

    return [dict(r) for r in rows if _row_id(r) in active_ids]
