"""Legacy batch --process: a failed chunk must not leave its conversation reading as extracted.

A chunked conversation sums its chunks into one extraction_log row. A chunk that errored was
marked only in extraction_chunks_done (-1) while its siblings added to extraction_log, so the
conversation read as extracted with part of it missing; an expired or canceled chunk was not
marked anywhere. Now any failed chunk sets the conversation's row to -1, and -1 stays -1 when
a sibling is summed in later, in either order.
"""
import sqlite3
import types

import pytest

from tests.test_turn_batch_extract import _result
from tests.test_turn_extraction import LEGACY_FACTS

pytestmark = pytest.mark.legacy

CONV = "conv-L"


@pytest.fixture
def conn(tmp_path):
    from baselayer.init_database import init_database
    from baselayer import batch_extract as be
    db = tmp_path / "memory.db"
    init_database(db)
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    c.execute("INSERT INTO conversations (id, title, created_at, updated_at, message_count, source)"
              " VALUES (?, 't', 1.0, 2.0, 10, 'chatgpt')", (CONV,))
    c.commit()
    be._ensure_extraction_chunks_done_table(c)
    yield c
    c.close()


def _process(conn, result, custom_id):
    from baselayer import batch_extract as be
    meta = {"parent_conv_id": CONV, "chunk_idx": int(custom_id[-1]), "source": "chatgpt"}
    counts = {"facts": 0, "errors": 0, "noops": 0, "processed": 0}
    be._process_legacy_result(conn, result, custom_id, meta, "batch-1", collection=None,
                              embed_model=None, corrections=[], source_map={}, counts=counts)
    return counts


def _log(conn):
    row = conn.execute("SELECT facts_extracted FROM extraction_log WHERE conversation_id = ?",
                       (CONV,)).fetchone()
    return None if row is None else row[0]


def _chunk_marks(conn):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT custom_id, facts_extracted FROM extraction_chunks_done WHERE batch_id = 'batch-1'")}


def _failed(custom_id, rtype):
    return types.SimpleNamespace(custom_id=custom_id, result=types.SimpleNamespace(type=rtype))


@pytest.mark.parametrize("first_ok", [True, False])
def test_an_errored_chunk_marks_the_conversation_failed_in_either_order(conn, first_ok):
    ok, bad = _result("c_0", LEGACY_FACTS), _failed("c_1", "errored")
    for res, cid in ([(ok, "c_0"), (bad, "c_1")] if first_ok else [(bad, "c_1"), (ok, "c_0")]):
        _process(conn, res, cid)
    assert _log(conn) == -1, "a conversation with a failed chunk must not read as extracted"
    assert _chunk_marks(conn) == {"c_0": 1, "c_1": -1}


@pytest.mark.parametrize("rtype", ["expired", "canceled"])
def test_expired_and_canceled_chunks_are_marked(conn, rtype):
    counts = _process(conn, _failed("c_0", rtype), "c_0")
    assert counts["errors"] == 1
    assert _chunk_marks(conn) == {"c_0": -1}
    assert _log(conn) == -1


def test_a_reply_without_a_facts_list_is_a_failed_chunk(conn):
    res = _result("c_0", [])
    res.result.message.content[-1].text = '{"items": []}'
    _process(conn, res, "c_0")
    assert _log(conn) == -1 and _chunk_marks(conn) == {"c_0": -1}


def test_chunks_that_succeed_still_sum(conn):
    _process(conn, _result("c_0", LEGACY_FACTS), "c_0")
    _process(conn, _result("c_1", []), "c_1")
    assert _log(conn) == 1 and _chunk_marks(conn) == {"c_0": 1, "c_1": 0}
