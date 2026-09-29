"""Recovered pre-July sources under the turn contract (docs/core/TURN_CONTRACT.md, 1-2).

Three recovered source kinds:

* Claude Code sessions that survive only as rows in an old corpus database
  (``conversations`` + ``messages``). The old importer stored tool calls and results as
  ``[tool: X]`` / ``[tool result]`` placeholders, kept harness wrappers inside the text,
  discarded every source flag, and stopped at the first import of each session.
* Claude Desktop local-agent-mode sessions (Claude Code JSONL written by the Desktop app).
* Raw Claude Code JSONL copies taken before the session ended (history holds later
  prompts).

Every fixture is synthetic. Each test plants a known-bad input and was first run against a
naive importer that maps the stored role to a speaker and calls every subject row
``own_typed``, which is what the pre-contract corpus did with these rows.
"""
import itertools
import json
import sqlite3

import pytest

import baselayer.import_conversations as IC
from baselayer import recovered_import as RI

_ids = itertools.count(1)

LONG_ASSISTANT = (
    "The retention policy keeps weekly snapshots for ninety days and monthly snapshots for "
    "two years, and the restore drill runs on the first Monday of every quarter so that the "
    "operations team can confirm the archive is readable before anyone depends on it."
)
# Plain prose that none of the text detectors marks as pasted on its own.
PLAIN_PASTE = (
    "the vendor said they can move the delivery to next week if we confirm by thursday and "
    "they also want a second contact for the invoice because the first one bounced twice"
)
CANARY = "SYNTHETIC-CANARY-MARKER-4417"


def uid():
    return f"10000000-0000-0000-0000-{next(_ids):012d}"


# --------------------------------------------------------------------------- fixtures

def make_db(path, sessions, wal_bytes=None):
    """Old-schema corpus database. sessions: {sid: [(role, text) | (role, text, msg_id)]}."""
    c = sqlite3.connect(str(path))
    c.executescript("""
        CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT, created_at REAL,
            updated_at REAL, message_count INTEGER, source TEXT);
        CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT, parent_id TEXT,
            role TEXT, content_text TEXT, content_type TEXT, created_at REAL,
            sequence_order INTEGER);
    """)
    for sid, msgs in sessions.items():
        c.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                  (sid, "t", None, None, len(msgs), "claude_code"))
        for i, m in enumerate(msgs):
            mid = (m[2] if len(m) > 2 else None) or uid()
            ts = m[3] if len(m) > 3 else None
            c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
                      (mid, sid, None, m[0], m[1], "text", ts, i))
    c.execute("INSERT INTO conversations VALUES ('chat-1','x',NULL,NULL,1,'chatgpt')")
    c.commit()
    c.close()
    if wal_bytes:
        (path.parent / (path.name + "-wal")).write_bytes(wal_bytes)
    return path


def write_history(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def h(sid, display, ts, pasted=None):
    return {"display": display, "pastedContents": pasted or {}, "timestamp": ts,
            "project": "/p", "sessionId": sid}


def rec(kind, content, sid, **kw):
    r = {"type": kind, "uuid": uid(), "sessionId": sid, "parentUuid": None,
         "timestamp": "2026-01-02T03:04:05.000Z", "userType": "external",
         "entrypoint": "cli", "cwd": "/work/project", "isSidechain": False,
         "message": {"role": kind, "content": content}}
    r.update(kw)
    return r


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch, temp_db):
    conn, _ = temp_db
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(cfg))

    class Env:
        pass
    e = Env()
    e.conn, e.tmp = conn, tmp_path
    e.hist = tmp_path / "history.jsonl"
    e.hist.write_text("", encoding="utf-8")

    def config(**d):
        cfg.write_text(json.dumps(d), encoding="utf-8")
    e.config = config
    return e


def turns(conn, conv):
    q = ("SELECT turn_id, speaker, voice_class, text, detector, basis, duplicate_of, source, "
         "created_at FROM turns WHERE conversation_id=? ORDER BY ordinal, COALESCE(segment, -1)")
    return [dict(zip(("turn_id", "speaker", "voice_class", "text", "detector", "basis",
                      "duplicate_of", "source", "created_at"), r))
            for r in conn.execute(q, (conv,)).fetchall()]


def flags(conn, conv):
    return dict(conn.execute("SELECT flag, detail FROM conversation_flags WHERE conversation_id=?",
                             (conv,)).fetchall())


def db_import(e, *dbs):
    return RI.import_db_copies(e.conn, list(dbs), [e.hist])


# --------------------------------------------------------------------------- DB copies

def test_db_copy_speaker_from_role_source_and_provenance_flags(env):
    db = make_db(env.tmp / "a.db", {"s-1": [("user", "rename the export folder please"),
                                            ("assistant", LONG_ASSISTANT)]})
    db_import(env, db)
    rows = turns(env.conn, "dbcopy_s-1")
    assert [(r["speaker"], r["voice_class"], r["source"]) for r in rows] == [
        ("subject", "own_typed", RI.SOURCE_DB_COPY), ("assistant", "assistant", RI.SOURCE_DB_COPY)]
    f = flags(env.conn, "dbcopy_s-1")
    assert "truncated_at_first_import" in f
    assert f.get("provenance", "").startswith("claude_code_db_copy")
    assert env.conn.execute("SELECT source FROM conversations WHERE id='dbcopy_s-1'").fetchone()[0] \
        == RI.SOURCE_DB_COPY
    # the chatgpt conversation in the same old database is not a Claude Code copy
    assert env.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1


def test_db_copy_tool_placeholders_are_tool_result(env):
    db = make_db(env.tmp / "a.db", {"s-1": [
        ("user", "check the build log"),
        ("assistant", "[tool: Bash]"),
        ("user", "[tool result]"),
        ("assistant", "Reading it now.\n[tool: Read]"),
        ("user", "[tool result]\n[tool result]"),
        ("user", "[tool result]\nand also the second log file please"),
    ]})
    db_import(env, db)
    got = [(r["speaker"], r["voice_class"], r["detector"], r["text"])
           for r in turns(env.conn, "dbcopy_s-1")]
    assert got == [
        ("subject", "own_typed", None, "check the build log"),
        ("assistant", "tool_result", RI.D_TOOL_CALL_PLACEHOLDER, "[tool: Bash]"),
        ("subject", "tool_result", "text:tool_result_placeholder", "[tool result]"),
        ("assistant", "assistant", "source:role=assistant", "Reading it now.\n[tool: Read]"),
        ("subject", "tool_result", "text:tool_result_placeholder", "[tool result]\n[tool result]"),
        ("subject", "tool_result", "text:tool_result_placeholder", "[tool result]"),
        ("subject", "own_typed", None, "and also the second log file please"),
    ]
    user_msgs = [r[0] for r in env.conn.execute(
        "SELECT content_text FROM messages WHERE role='user' AND conversation_id='dbcopy_s-1'")]
    assert user_msgs == ["check the build log", "and also the second log file please"]


def test_db_copy_compaction_summary_by_text_signature(env):
    summary = ("This session is being continued from a previous conversation that ran out of "
               "context. The conversation is summarized below: the user asked for a backup plan.")
    db = make_db(env.tmp / "a.db", {"s-1": [("user", summary)]})
    db_import(env, db)
    assert [(r["voice_class"], r["detector"]) for r in turns(env.conn, "dbcopy_s-1")] == [
        ("compaction_summary", "text:compaction_signature")]


def test_db_copy_wrappers_stripped_and_wrapper_only_rows_dropped(env):
    db = make_db(env.tmp / "a.db", {"s-1": [
        ("user", "<task-notification>\n<task-id>abc</task-id>\n<status>completed</status>\n"
                 "</task-notification>"),
        ("user", "<command-name>/model</command-name>\n<command-message>model</command-message>"),
        ("user", "<local-command-caveat>Caveat: The messages below were generated by the user "
                 "while running local commands.</local-command-caveat>"),
        ("user", "[Request interrupted by user]"),
        ("user", "what does the retention job do<system-reminder>harness note</system-reminder>"),
    ]})
    db_import(env, db)
    got = [(r["voice_class"], r["text"]) for r in turns(env.conn, "dbcopy_s-1")]
    assert got == [("own_typed", "what does the retention job do")]


def test_harness_text_signatures_in_a_db_copy_are_harness(env):
    # Source flags (isMeta, origin=task-notification) are gone from a copy; these openings
    # are what those records carry. On raw sessions every match was an isMeta record.
    rows = [
        "<task-notification>\n<task-id>a1</task-id>\n</task-notification>\n"
        "Read the output file to retrieve the result: /tmp/tasks/a1.output",
        "<task-notification>\n<task-id>a2</task-id>\n</task-notification>\n"
        "Full transcript available at: /tmp/tasks/a2.output",
        "Base directory for this skill: /skills/example\n\n# Example skill\n\nDo the steps.",
        "Implement the following plan:\n\n# Plan: tidy the export folder\n1. Move files",
        "Continue from where you left off.",
        "Tool loaded.",
        "<local-command-stderr>Error: something failed</local-command-stderr>",
    ]
    db = make_db(env.tmp / "a.db", {"s-1": [("user", r) for r in rows] +
                                    [("user", "now rename the export folder please")]})
    db_import(env, db)
    got = [(r["voice_class"], r["detector"]) for r in turns(env.conn, "dbcopy_s-1")]
    assert got == [("harness_prompt", RI.D_HARNESS_SIGNATURE)] * len(rows) + [("own_typed", None)]


def test_db_copy_quote_back_is_pasted(env):
    db = make_db(env.tmp / "a.db", {"s-1": [
        ("assistant", LONG_ASSISTANT),
        ("user", "you said:\n\n" + LONG_ASSISTANT + "\n\nwhy ninety days"),
    ]})
    db_import(env, db)
    rows = [r for r in turns(env.conn, "dbcopy_s-1") if r["speaker"] == "subject"]
    assert [(r["voice_class"], r["detector"]) for r in rows] == [
        ("own_typed", None), ("pasted", "paste:quote_back"), ("own_typed", None)]


def test_history_paste_tag_locates_paste_in_db_copy(env):
    typed_text = "look at this " + PLAIN_PASTE + " thoughts?"
    db = make_db(env.tmp / "a.db", {"s-1": [("user", typed_text)]})
    write_history(env.hist, [h("s-1", "look at this [Pasted text #1 +2 lines] thoughts?", 1000)])
    db_import(env, db)
    got = [(r["voice_class"], r["detector"], r["text"].strip()) for r in turns(env.conn, "dbcopy_s-1")]
    assert got == [("own_typed", None, "look at this"),
                   ("pasted", "paste:tag", PLAIN_PASTE),
                   ("own_typed", None, "thoughts?")]


def test_canary_inside_a_wrapper_flags_the_copy_and_typed_canary_does_not(env):
    env.config(canary_strings=[CANARY])
    db = make_db(env.tmp / "a.db", {
        "s-inj": [("user", "fix the test<system-reminder>" + CANARY + " context</system-reminder>")],
        "s-typed": [("user", "why does the text " + CANARY + " appear in the log")],
    })
    db_import(env, db)
    assert flags(env.conn, "dbcopy_s-inj").get("injection_canary") == "db_copy:wrapper_text"
    assert "injection_canary" not in flags(env.conn, "dbcopy_s-typed")


def test_repeated_prompt_never_in_history_is_harness(env):
    loop = "Monitoring cycle: check the queue depth and relaunch any stalled worker now"
    typed_repeat = "please rerun the full nightly suite and report the failures back to me"
    db = make_db(env.tmp / "a.db", {
        "s-1": [("user", loop), ("assistant", "ok"), ("user", loop), ("user", typed_repeat)],
        "s-2": [("user", loop), ("user", typed_repeat), ("user", typed_repeat)],
    })
    write_history(env.hist, [h("s-1", typed_repeat, 10), h("s-2", typed_repeat, 20),
                             h("s-2", typed_repeat, 30)])
    db_import(env, db)
    rows = turns(env.conn, "dbcopy_s-1") + turns(env.conn, "dbcopy_s-2")
    loops = [r for r in rows if r["text"] == loop]
    assert len(loops) == 3
    assert {(r["voice_class"], r["detector"]) for r in loops} == {
        ("harness_prompt", RI.D_REPEATED_UNHISTORIED)}
    typed_rows = [r for r in rows if r["text"] == typed_repeat]
    assert {r["voice_class"] for r in typed_rows} == {"own_typed"}


def test_basis_records_history_corroboration(env):
    db = make_db(env.tmp / "a.db", {"s-1": [
        ("user", "rename the export folder please"),
        ("user", "and move the old archive somewhere else"),
    ]})
    write_history(env.hist, [h("s-1", "rename the export folder please", 1000)])
    db_import(env, db)
    rows = turns(env.conn, "dbcopy_s-1")
    assert [r["basis"] for r in rows] == [RI.B_DB_ROLE + RI.CORROBORATED, RI.B_DB_ROLE]
    # the matched turn takes the history timestamp; the unmatched one has none
    assert rows[0]["created_at"] == 1000 and rows[1]["created_at"] is None


def test_history_prompt_in_db_copy_is_duplicate_and_later_prompts_are_kept(env):
    db = make_db(env.tmp / "a.db", {"s-1": [
        ("user", "rename the export folder please"), ("assistant", "done"),
        ("user", "yes"), ("assistant", "ok"),
    ]})
    write_history(env.hist, [
        h("s-1", "rename the export folder please", 1000),
        h("s-1", "yes", 1100),
        h("s-1", "a prompt typed after the copy was taken", 900000),
    ])
    db_import(env, db)
    IC.import_history(env.conn, [env.hist], set())
    hist_rows = turns(env.conn, "history_s-1")
    assert [(r["text"], r["duplicate_of"]) for r in hist_rows] == [
        ("rename the export folder please", "dbcopy_s-1"),
        ("yes", "dbcopy_s-1"),
        ("a prompt typed after the copy was taken", None)]
    user_msgs = [r[0] for r in env.conn.execute(
        "SELECT content_text FROM messages WHERE conversation_id='history_s-1'")]
    assert user_msgs == ["a prompt typed after the copy was taken"]
    assert flags(env.conn, "dbcopy_s-1")["truncated_at_first_import"].startswith("positional: 1 ")


def test_prompt_quoted_inside_a_compaction_summary_is_not_a_duplicate(env):
    # A compaction summary lists earlier user messages. The copy carries the prompt only
    # inside that context-only text, so the history prompt must stay citable.
    prompt = "rename the export folder and keep the old one for a week"
    summary = ("This session is being continued from a previous conversation that ran out of "
               "context. All user messages: " + prompt + ". Pending tasks: none.")
    db = make_db(env.tmp / "a.db", {"s-1": [("user", summary), ("assistant", "ok"),
                                            ("user", "now check the logs please")]})
    write_history(env.hist, [h("s-1", prompt, 1000), h("s-1", "now check the logs please", 2000)])
    db_import(env, db)
    IC.import_history(env.conn, [env.hist], set())
    assert [(r["text"], r["duplicate_of"]) for r in turns(env.conn, "history_s-1")] == [
        (prompt, None), ("now check the logs please", "dbcopy_s-1")]
    assert turns(env.conn, "dbcopy_s-1")[0]["voice_class"] == "compaction_summary"


def test_copy_end_is_the_last_stored_turn_a_prompt_reached(env):
    # A prompt resubmitted later can align backward to an early turn. The copy still
    # ends where the latest-positioned match is, so the prompt between counts as later.
    early = "an early prompt that was typed again much later on"
    db = make_db(env.tmp / "a.db", {"s-1": [("user", early), ("user", "first real prompt here now"),
                                            ("user", "second real prompt here now")]})
    write_history(env.hist, [h("s-1", "first real prompt here now", 1000),
                             h("s-1", "second real prompt here now", 2000),
                             h("s-1", "a prompt typed after the copy was taken", 3000),
                             h("s-1", early, 4000)])
    stats = db_import(env, db)
    assert flags(env.conn, "dbcopy_s-1")["truncated_at_first_import"] ==         "positional: 2 history prompts after the last one the copy carries"
    IC.import_history(env.conn, [env.hist], set())
    assert [r["duplicate_of"] for r in turns(env.conn, "history_s-1")] == [
        "dbcopy_s-1", "dbcopy_s-1", None, "dbcopy_s-1"]


def test_short_prompt_after_the_copy_ends_is_not_matched_into_its_tail(env):
    # Once a long prompt is missing, the copy has ended; a later "ok" must not be matched
    # to an "ok" in the copy's last turns, and must not move the copy's end.
    db = make_db(env.tmp / "a.db", {"s-1": [
        ("user", "rename the export folder please"), ("user", "yes"), ("user", "ok")]})
    write_history(env.hist, [h("s-1", "rename the export folder please", 1000),
                             h("s-1", "yes", 1100),
                             h("s-1", "a long prompt typed after the copy was taken", 5000),
                             h("s-1", "ok", 6000)])
    db_import(env, db)
    assert flags(env.conn, "dbcopy_s-1")["truncated_at_first_import"] ==         "positional: 2 history prompts after the last one the copy carries"
    IC.import_history(env.conn, [env.hist], set())
    assert [r["duplicate_of"] for r in turns(env.conn, "history_s-1")] == [
        "dbcopy_s-1", "dbcopy_s-1", None, None]


def test_truncation_is_confirmed_by_timestamps_where_the_copy_has_them(env):
    # Positional "after the last aligned prompt" over-counts: a prompt missing from the
    # copy but typed before its last stored message is not later. Where stored messages
    # carry timestamps, only prompts typed after the last one confirm truncation.
    db = make_db(env.tmp / "a.db", {
        "s-t": [("user", "rename the export folder please", None, 1000.0),
                ("assistant", "done", None, 1010.0), ("assistant", "still working", None, 5000.0)],
        "s-n": [("user", "rename the export folder please", None, 1000.0),
                ("assistant", "done", None, 9000.0)]})
    write_history(env.hist, [
        h("s-t", "rename the export folder please", 1000),
        h("s-t", "a prompt the copy lacks but typed before it ended", 2000),
        h("s-t", "a prompt typed well after the copy was taken", 20000),
        h("s-n", "rename the export folder please", 1000),
        h("s-n", "a prompt the copy lacks but typed before it ended", 2000)])
    db_import(env, db)
    assert flags(env.conn, "dbcopy_s-t")["truncated_at_first_import"] ==         "confirmed by timestamp: 1 history prompts after the copy's last stored message"
    assert flags(env.conn, "dbcopy_s-n")["truncated_at_first_import"].startswith("by construction")


def test_history_dedupe_holds_when_history_is_imported_first(env):
    db = make_db(env.tmp / "a.db", {"s-1": [("user", "rename the export folder please")]})
    write_history(env.hist, [h("s-1", "rename the export folder please", 1000),
                             h("s-1", "a later prompt nobody copied", 900000)])
    IC.import_history(env.conn, [env.hist], set())
    db_import(env, db)
    assert [(r["text"], r["duplicate_of"]) for r in turns(env.conn, "history_s-1")] == [
        ("rename the export folder please", "dbcopy_s-1"),
        ("a later prompt nobody copied", None)]
    user_msgs = [r[0] for r in env.conn.execute(
        "SELECT content_text FROM messages WHERE conversation_id='history_s-1'")]
    assert user_msgs == ["a later prompt nobody copied"]


def test_db_copies_are_deduplicated_across_databases(env):
    same = {"s-1": [("user", "rename the export folder please", "m-1")]}
    a = make_db(env.tmp / "a.db", same)
    b = make_db(env.tmp / "b.db", same)
    key_text = "use the key sk-live-0000000000000000 for the test run"
    c = make_db(env.tmp / "c.db", {"s-2": [("user", key_text, "m-2")]})
    d = make_db(env.tmp / "d.db", {"s-2": [("user", "use the key [REDACTED_API_KEY] for the test run",
                                            "m-2")]})
    stats = db_import(env, a, b, c, d)
    assert env.conn.execute("SELECT COUNT(*) FROM conversations WHERE source=?",
                            (RI.SOURCE_DB_COPY,)).fetchone()[0] == 2
    assert stats["identical_copies_dropped"] == 1
    assert stats["conflicts_resolved_redacted"] == 1
    assert [r["text"] for r in turns(env.conn, "dbcopy_s-2")] == [
        "use the key [REDACTED_API_KEY] for the test run"]


def test_raw_transcript_wins_over_db_copy_of_the_same_session(env):
    sid = "s-raw"
    f = write_jsonl(env.tmp / "proj" / f"{sid}.jsonl", [
        rec("user", "rename the export folder please", sid, promptSource="typed",
            origin={"kind": "human"})])
    IC.import_claude_code(env.conn, set(), session_files=[f])
    db = make_db(env.tmp / "a.db", {sid: [("user", "rename the export folder please")]})
    stats = db_import(env, db)
    assert stats["raw_transcript_wins"] == 1
    assert turns(env.conn, f"dbcopy_{sid}") == []


def test_db_copy_row_already_in_a_raw_transcript_is_duplicate(env):
    shared = uid()
    f = write_jsonl(env.tmp / "proj" / "s-raw.jsonl", [
        rec("user", "rename the export folder please", "s-raw", uuid=shared,
            promptSource="typed", origin={"kind": "human"})])
    IC.import_claude_code(env.conn, set(), session_files=[f])
    db = make_db(env.tmp / "a.db", {"s-resumed": [
        ("user", "rename the export folder please", shared),
        ("user", "and a new prompt in the resumed copy"),
    ]})
    db_import(env, db)
    assert [r["duplicate_of"] for r in turns(env.conn, "dbcopy_s-resumed")] == ["s-raw", None]


def test_database_with_unflushed_wal_is_refused(env):
    db = make_db(env.tmp / "a.db", {"s-1": [("user", "x y z")]}, wal_bytes=b"\x00" * 64)
    with pytest.raises(RuntimeError):
        db_import(env, db)


# --------------------------------------------------------------------------- Desktop

def make_desktop(root, local_id, sid, records, title="Review the repository"):
    base = root / "acct" / "org"
    meta = {"sessionId": local_id, "cliSessionId": sid, "title": title,
            "createdAt": 1776000000000, "emailAddress": "someone@example.invalid",
            "systemPrompt": "SYSTEM PROMPT TEXT"}
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{local_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    write_jsonl(base / local_id / ".claude" / "projects" / "-sessions-x" / f"{sid}.jsonl", records)
    # the audit log echoes records; it must not be imported as a second session
    write_jsonl(base / local_id / "audit.jsonl", [{"type": "user", "message": {"content": "echo"}}])


def test_desktop_agent_session_uses_the_contract_and_its_own_source(env):
    root = env.tmp / "desktop"
    sid = "20000000-0000-0000-0000-000000000001"
    make_desktop(root, "local_1", sid, [
        rec("user", "review the repository and list the risks", sid, entrypoint="local-agent"),
        rec("assistant", [{"type": "tool_use", "name": "Read", "input": {}}], sid,
            entrypoint="local-agent"),
        rec("user", [{"type": "tool_result", "content": "file body"}], sid, entrypoint="local-agent"),
        rec("user", [{"type": "text", "text": "Uploaded document body"}], sid,
            entrypoint="local-agent", isMeta=True),
        rec("assistant", [{"type": "text", "text": LONG_ASSISTANT}], sid, entrypoint="local-agent"),
        {"type": "queue-operation", "operation": "enqueue", "content": "queued copy", "sessionId": sid},
    ])
    stats = RI.import_desktop_agent(env.conn, root)
    assert stats["sessions"] == 1
    rows = turns(env.conn, sid)
    assert [(r["speaker"], r["voice_class"], r["source"]) for r in rows] == [
        ("subject", "own_typed", RI.SOURCE_DESKTOP),
        ("assistant", "assistant", RI.SOURCE_DESKTOP),
        ("subject", "tool_result", RI.SOURCE_DESKTOP),
        ("subject", "harness_prompt", RI.SOURCE_DESKTOP),
        ("assistant", "assistant", RI.SOURCE_DESKTOP),
    ]
    title = env.conn.execute("SELECT title FROM conversations WHERE id=?", (sid,)).fetchone()[0]
    assert title == "Review the repository"
    blob = json.dumps([list(r) for r in env.conn.execute("SELECT * FROM turns").fetchall()])
    assert "SYSTEM PROMPT TEXT" not in blob and "example.invalid" not in blob


# --------------------------------------------------------------------------- raw copies

def test_history_after_a_raw_copy_ends_is_kept(env):
    sid = "s-copy"
    f = write_jsonl(env.tmp / "proj" / f"{sid}.jsonl", [
        rec("user", "rename the export folder please", sid, promptSource="typed",
            origin={"kind": "human"}, timestamp="2026-01-02T03:04:05.000Z")])
    IC.import_claude_code(env.conn, set(), session_files=[f])
    t0 = 1767323045  # 2026-01-02T03:04:05Z
    write_history(env.hist, [h(sid, "rename the export folder please", t0 * 1000),
                             h(sid, "a prompt after the copy was taken", (t0 + 7200) * 1000)])
    IC.import_history(env.conn, [env.hist], set())
    assert [(r["text"], r["duplicate_of"]) for r in turns(env.conn, f"history_{sid}")] == [
        ("a prompt after the copy was taken", None)]


# --------------------------------------------------------------------------- aligner

from baselayer import history_align as HA  # noqa: E402


def test_align_short_typed_text_with_a_paste_tag():
    # Short typed text around a placeholder cannot require the turn to equal it: the
    # turn also holds the pasted block. Found as the largest miss class on real data.
    turns_ = ["unrelated first turn here", "here is the post " + PLAIN_PASTE]
    got = HA.align([{"display": "here is the post [Pasted text #2 +8 lines]"}], turns_)
    assert got == [1]


def test_align_finds_a_short_prompt_just_behind_the_pointer():
    # A long prompt matched ahead moves the pointer past a short one queued before it.
    long_p = "move the nightly backup to sunday and keep ninety days of snapshots"
    turns_ = ["run it", long_p]
    got = HA.align([{"display": long_p}, {"display": "run it"}], turns_)
    assert got == [1, 0]


def test_align_does_not_reach_far_for_a_short_prompt():
    turns_ = ["yes"] + [f"filler turn number {i} with enough words" for i in range(60)]
    entries = [{"display": f"filler turn number {i} with enough words"} for i in range(60)]
    got = HA.align(entries + [{"display": "yes"}], turns_)
    assert got[-1] is None


def test_align_paste_only_entry_has_nothing_to_match():
    assert HA.align([{"display": "[Pasted text #1 +40 lines]"}], [PLAIN_PASTE]) == [None]


def test_paste_spans_between_and_after_typed_pieces():
    text = "compare A " + PLAIN_PASTE + " with B second block of pasted words here"
    spans = HA.paste_spans("compare A [Pasted text #1] with B [Pasted text #2]", text)
    assert [text[a:b].strip() for a, b in spans] == [PLAIN_PASTE, "second block of pasted words here"]
    assert HA.paste_spans("no placeholder here", text) == []


# --------------------------------------------------------------------------- loop prompts
# A ScheduleWakeup or CronCreate prompt fires back into the session as a user message. A
# database copy keeps only "[tool: ScheduleWakeup]" for the call and the fired prompt as a
# plain user row, and the prompt is never in history.jsonl. Literal detector names so the
# tests fail on the old build for the classification, not on a missing constant.
LOOP_TEMPLATE = "text:recurring_loop_template"
LOOP_MONITOR = "text:loop_monitor_prompt"
WAKE = [("assistant", "[tool: ScheduleWakeup]"), ("user", "[tool result]")]


def _loop_variants():
    base = ("Look at the nightly export job for the billing mirror, relaunch any stale worker "
            "that has not written a checkpoint, then run the archive script")
    return [base + ".", base + " and note the row count.", base + " for both regions."]


def test_recurring_loop_template_after_wakeups_is_harness(env):
    v = _loop_variants()
    human = "i am heading out for the evening so keep an eye on the export for me"
    msgs = ([("user", "set up the export monitor and schedule a wakeup every few minutes")]
            + WAKE + [("user", v[0]), ("assistant", "Relaunched two workers.")]
            + [("user", human), ("assistant", "Will do.")]
            + WAKE + [("user", v[1]), ("assistant", "All workers healthy.")]
            + WAKE + [("user", v[2])])
    db = make_db(env.tmp / "a.db", {"s-1": msgs})
    db_import(env, db)
    rows = {r["text"]: r for r in turns(env.conn, "dbcopy_s-1") if r["speaker"] == "subject"
            and r["voice_class"] != "tool_result"}
    assert [(rows[t]["voice_class"], rows[t]["detector"]) for t in v] == [
        ("harness_prompt", LOOP_TEMPLATE)] * 3
    assert rows[human]["voice_class"] == "own_typed"
    assert rows["set up the export monitor and schedule a wakeup every few minutes"][
        "voice_class"] == "own_typed"


def test_monitor_phrasing_in_a_scheduler_session_is_harness(env):
    mon = "Check export progress. Restart it if stalled. Start part 2 once part 1 is done. Sync."
    cyc = "Monitoring cycle.\n1. Check the judging runs\n2. Relaunch timed-out processes\n3. Sync"
    db = make_db(env.tmp / "a.db", {"s-1": [("user", "start the judging runs and watch them")]
                                    + WAKE + [("assistant", "Sleeping."), ("user", mon),
                                              ("assistant", "ok"), ("user", cyc)]})
    db_import(env, db)
    got = {r["text"]: (r["voice_class"], r["detector"]) for r in turns(env.conn, "dbcopy_s-1")}
    assert got[mon] == ("harness_prompt", LOOP_MONITOR)
    assert got[cyc] == ("harness_prompt", LOOP_MONITOR)


def test_loop_rules_leave_own_typing_alone(env):
    mon = "Check export progress. Restart it if stalled. Start part 2 once part 1 is done. Sync."
    resub = ("the vendor wants the invoice contact changed before friday so update the record "
             "and tell me when it is done")
    human_after_wake = "how are the results looking so far on the second batch of subjects"
    msgs = ([("user", "start the judging runs and watch them")]
            + WAKE + [("user", "yes")] + WAKE + [("user", "go ahead")] + WAKE + [("user", "yes")]
            + WAKE + [("user", human_after_wake)]
            + [("assistant", "ok"), ("user", resub), ("assistant", "ok"), ("user", resub + " please")]
            + [("assistant", "ok"), ("user", mon)])
    db = make_db(env.tmp / "a.db", {
        "s-sched": msgs,
        # monitor wording, never in history, with no scheduler call in the session
        "s-plain": [("user", mon.replace("BL", "CD")), ("assistant", "ok")],
    })
    # typed and submitted: history corroborates it, so it is the person's even in a scheduler session
    write_history(env.hist, [h("s-sched", mon, 50)])
    db_import(env, db)
    subj = [r for r in turns(env.conn, "dbcopy_s-sched") + turns(env.conn, "dbcopy_s-plain")
            if r["speaker"] == "subject" and r["voice_class"] != "tool_result"]
    assert subj and {r["voice_class"] for r in subj} == {"own_typed"}, [
        (r["text"][:40], r["voice_class"], r["detector"]) for r in subj]


def test_paste_spans_trailing_typed_piece_that_also_occurs_in_the_paste():
    """A typed piece after the last placeholder is the LAST occurrence in the text; its
    words may also occur inside the paste, which must not cut the pasted span short."""
    from baselayer import history_align as HA
    paste = ("the vendor said they can move the delivery, thanks for the patience. the invoice "
             "contact bounced twice so they want a second one before thursday")
    text = paste + "\n\nthanks"
    assert HA.paste_spans("[Pasted text #1] thanks", text) == [(0, len(paste) + 2)]
    # a leading typed piece is still bounded as before
    lead = "can you read this log"
    assert HA.paste_spans(lead + " [Pasted text #1]", lead + "\n" + paste) == [
        (len(lead), len(lead) + 1 + len(paste))]
