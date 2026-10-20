"""One session file with a byte that is not UTF-8 must not stop the whole import.

build_claude_code_context opened each file inside a try that caught OSError only, then read
it strictly as UTF-8 outside that try, and load_history_sessions read strictly with no try at
all: one bad byte in one file raised UnicodeDecodeError and the import of every file stopped.
They now read with errors="replace", as the per-session reader and the recovered-file reader
already did, so every reader sees the same text.
"""
import json

from baselayer import turn_import as TI
from tests.test_turn_contract_import import (  # noqa: F401  (env is a fixture)
    assistant, cc_import, env, typed, user_messages, write_session)

GOOD = "write the migration plan before touching the schema"
NEAR_BAD = "keep the old table until the backfill is verified"


def test_a_bad_byte_in_one_session_does_not_stop_the_import(env):
    write_session(env.projects, "sess-good", [typed(GOOD, "sess-good"),
                                              assistant("Will do.", "sess-good")])
    bad = write_session(env.projects, "sess-bad", [typed(NEAR_BAD, "sess-bad"),
                                                   assistant("Understood.", "sess-bad")])
    with open(bad, "ab") as fh:                     # a line holding an invalid UTF-8 byte
        fh.write(b'{"type": "user", "uuid": "u-x", "note": "\xff\xfe"}\n')
    cc_import(env)
    texts = user_messages(env.conn)
    assert GOOD in texts
    assert NEAR_BAD in texts


def test_history_reader_survives_a_bad_byte(tmp_path):
    good = tmp_path / "history_a.jsonl"
    good.write_text(json.dumps({"sessionId": "s1", "display": "first prompt",
                                "timestamp": 1}) + "\n", encoding="utf-8")
    bad = tmp_path / "history_b.jsonl"
    bad.write_bytes(json.dumps({"sessionId": "s2", "display": "second prompt",
                                "timestamp": 2}).encode("utf-8") + b"\n\xff\xfe broken\n")
    sessions = TI.load_history_sessions([good, bad])
    assert [e["display"] for e in sessions["s1"]] == ["first prompt"]
    assert [e["display"] for e in sessions["s2"]] == ["second prompt"]
