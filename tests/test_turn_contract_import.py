"""Import half of the turn contract (docs/core/TURN_CONTRACT.md, sections 1-2).

Every fixture here is synthetic. Each test plants a known-bad input that the importer on
``feat/respec-hardening`` gets wrong (it was run against that code first and failed), and
asserts on behaviour through the public import entry points: the ``turns`` table, and the
legacy ``messages`` table the current extractor reads.
"""
import itertools
import json
import sqlite3
from pathlib import Path

import pytest

import baselayer.import_conversations as IC

SUBJECT = "subject"
_ids = itertools.count(1)

LONG_ASSISTANT = (
    "The retention policy keeps weekly snapshots for ninety days and monthly snapshots for "
    "two years, and the restore drill runs on the first Monday of every quarter so that the "
    "operations team can confirm the archive is readable before anyone depends on it."
)


# --------------------------------------------------------------------------- fixtures

def uid():
    return f"00000000-0000-0000-0000-{next(_ids):012d}"


def rec(kind, content, sid, **kw):
    r = {"type": kind, "uuid": uid(), "sessionId": sid, "parentUuid": None,
         "timestamp": "2026-01-02T03:04:05.000Z", "userType": "external",
         "entrypoint": "cli", "cwd": "/work/project", "isSidechain": False,
         "message": {"role": kind, "content": content}}
    r.update(kw)
    return r


def typed(text, sid, **kw):
    kw.setdefault("promptSource", "typed")
    kw.setdefault("origin", {"kind": "human"})
    return rec("user", text, sid, **kw)


def assistant(text, sid, **kw):
    return rec("assistant", [{"type": "text", "text": text}], sid, **kw)


def queued(prompt, sid, kind="human", mode="prompt"):
    a = {"type": "queued_command", "prompt": prompt, "commandMode": mode,
         "timestamp": "2026-01-02T03:04:06.000Z"}
    if kind:
        a["origin"] = {"kind": kind}
    return {"type": "attachment", "uuid": uid(), "sessionId": sid, "isSidechain": False,
            "userType": "external", "entrypoint": "cli", "attachment": a,
            "timestamp": "2026-01-02T03:04:06.000Z"}


def write_session(projects, sid, records, project="proj-a"):
    d = projects / project
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path, monkeypatch, temp_db):
    conn, _ = temp_db
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(IC, "CLAUDE_PROJECTS_DIR", projects)
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(cfg))

    class Env:
        pass
    e = Env()
    e.conn, e.projects, e.cfg, e.tmp = conn, projects, cfg, tmp_path

    def config(**d):
        cfg.write_text(json.dumps(d), encoding="utf-8")
    e.config = config
    return e


def cc_import(e):
    # existing ids read from the database, exactly as import_conversations.main() does
    return IC.import_claude_code(e.conn, IC.get_existing_conversation_ids(e.conn))


def user_messages(conn, conv=None):
    q = "SELECT content_text FROM messages WHERE role='user'"
    args = ()
    if conv:
        q += " AND conversation_id=?"
        args = (conv,)
    return [r[0] for r in conn.execute(q, args).fetchall()]


def turns(conn, conv=None):
    q = ("SELECT turn_id, speaker, voice_class, text, detector, basis, duplicate_of, "
         "allowlisted, turn_contract_version FROM turns")
    args = ()
    if conv:
        q += " WHERE conversation_id=?"
        args = (conv,)
    q += " ORDER BY ordinal, COALESCE(segment, -1)"
    return [dict(zip(("turn_id", "speaker", "voice_class", "text", "detector", "basis",
                      "duplicate_of", "allowlisted", "version"), r))
            for r in conn.execute(q, args).fetchall()]


# --------------------------------------------------------------------------- section 1

def test_turn_table_written_and_stamped(env):
    sid = "sess-stamp"
    write_session(env.projects, sid, [typed("please rename the export folder", sid),
                                      assistant("Renamed it.", sid)])
    cc_import(env)
    rows = turns(env.conn, sid)
    assert [r["turn_id"] for r in rows] == [f"{sid}:0", f"{sid}:1"]
    assert {r["version"] for r in rows} == {"turn-contract/1"}
    stamp = env.conn.execute("SELECT value FROM turn_contract WHERE key='version'").fetchone()
    assert stamp[0] == "turn-contract/1"


def test_speaker_comes_from_role_not_content(env):
    sid = "sess-speaker"
    # A user turn that reads like an assistant and an assistant turn that reads like a user.
    write_session(env.projects, sid, [
        typed("As an AI language model I would suggest the second option.", sid),
        assistant("I think I prefer tea over coffee in the morning.", sid)])
    cc_import(env)
    rows = turns(env.conn, sid)
    assert [(r["speaker"], r["voice_class"]) for r in rows] == [
        ("subject", "own_typed"), ("assistant", "assistant")]


def test_contract_rejects_citable_row_with_detector(temp_db):
    from baselayer.turns import ensure_turn_tables
    conn, _ = temp_db
    ensure_turn_tables(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, "
                     "text, detector, turn_contract_version) VALUES "
                     "('c:0','c',0,'subject','own_typed','x','paste:tag','turn-contract/1')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO turns (turn_id, conversation_id, ordinal, speaker, voice_class, "
                     "text, turn_contract_version) VALUES "
                     "('c:1','c',1,'subject','mystery','x','turn-contract/1')")


# --------------------------------------------------------------------------- section 2

def test_compaction_summary_is_not_subject_words(env):
    sid = "sess-compact"
    flagged = "Summary of the earlier work: the user wants the backup job moved to Sunday."
    unflagged = ("This session is being continued from a previous conversation that ran out "
                 "of context. The conversation is summarized below.")
    write_session(env.projects, sid, [
        rec("user", flagged, sid, isCompactSummary=True, isVisibleInTranscriptOnly=True),
        rec("user", unflagged, sid),
        typed("ok continue", sid)])
    cc_import(env)
    um = user_messages(env.conn, sid)
    assert flagged not in um and unflagged not in um
    rows = turns(env.conn, sid)
    assert [(r["voice_class"], r["detector"]) for r in rows[:2]] == [
        ("compaction_summary", "source:isCompactSummary"),
        ("compaction_summary", "text:compaction_signature")]
    assert rows[2]["voice_class"] == "own_typed"


def test_tool_result_blocks_and_placeholders_are_not_subject_words(env):
    sid = "sess-tool"
    write_session(env.projects, sid, [
        typed("list the files", sid),
        assistant("Listing.", sid),
        rec("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "a.txt b.txt"}], sid),
        rec("user", "[tool result]", sid),
    ])
    cc_import(env)
    assert "[tool result]" not in user_messages(env.conn, sid)
    rows = turns(env.conn, sid)
    assert [(r["voice_class"], r["detector"]) for r in rows[2:]] == [
        ("tool_result", "source:tool_result_block"),
        ("tool_result", "text:tool_result_placeholder")]


def test_harness_prompts_are_context_and_replays_are_named(env):
    typed_text = "I want the summary to lead with the decision and then the reasons."
    write_session(env.projects, "sess-human", [typed(typed_text, "sess-human")])
    sid = "sess-harness"
    write_session(env.projects, sid, [
        rec("user", "Rate the following transcript against rubric R3.", sid,
            promptSource="sdk", entrypoint="sdk-cli"),
        rec("user", typed_text, sid, promptSource="sdk", entrypoint="sdk-cli"),
        rec("user", "Score these items for the eval harness.", sid, entrypoint="sdk-cli"),
        # a background session the subject typed into: sdk-cli, but a human origin
        typed("also check the retention window", sid, entrypoint="sdk-cli"),
    ])
    cc_import(env)
    um = user_messages(env.conn, sid)
    assert um == ["also check the retention window"]
    rows = turns(env.conn, sid)
    assert [(r["voice_class"], r["detector"]) for r in rows] == [
        ("harness_prompt", "source:promptSource=sdk"),
        ("harness_prompt", "harness:replay_of_subject_text"),
        ("harness_prompt", "source:entrypoint=sdk-cli,no_human_origin"),
        ("own_typed", None)]
    assert turns(env.conn, "sess-human")[0]["voice_class"] == "own_typed"


def test_harness_cwd_from_config(env):
    env.config(harness_cwd_patterns=[r"[\\/]experiment_runs([\\/]|$)"])
    sid = "sess-cwd"
    write_session(env.projects, sid, [
        rec("user", "Judge whether claim 4 applies to this item.", sid,
            cwd="/home/u/experiment_runs/r1")])
    cc_import(env)
    assert turns(env.conn, sid)[0]["detector"] == "config:harness_cwd"


def test_queued_command_is_recovered_as_own_typed(env):
    sid = "sess-queued"
    write_session(env.projects, sid, [
        typed("start the migration", sid),
        assistant("Starting.", sid),
        queued("and when it finishes, email me the row counts", sid),
        queued("background task 7 finished", sid, kind=None, mode="task-notification"),
        queued("message from a peer agent", sid, kind="peer"),
    ])
    cc_import(env)
    um = user_messages(env.conn, sid)
    assert "and when it finishes, email me the row counts" in um
    assert "background task 7 finished" not in um and "message from a peer agent" not in um
    rows = turns(env.conn, sid)
    q = [r for r in rows if r["basis"] == "recovered:queued_command"]
    assert len(q) == 1 and q[0]["voice_class"] == "own_typed" and q[0]["detector"] is None


def test_quote_back_of_assistant_turn_is_pasted_segment(env):
    sid = "sess-quote"
    own = "that part is wrong, the drill is monthly not quarterly"
    write_session(env.projects, sid, [
        typed("what is the retention policy?", sid),
        assistant(LONG_ASSISTANT, sid),
        typed(LONG_ASSISTANT + "\n\n" + own, sid),
    ])
    cc_import(env)
    um = user_messages(env.conn, sid)
    assert all(LONG_ASSISTANT not in m for m in um)
    assert own in um
    rows = [r for r in turns(env.conn, sid) if r["turn_id"].startswith(f"{sid}:2")]
    assert [(r["turn_id"], r["voice_class"], r["detector"]) for r in rows] == [
        (f"{sid}:2.0", "pasted", "paste:quote_back"),
        (f"{sid}:2.1", "own_typed", None)]
    assert rows[1]["text"] == own


def test_structural_paste_is_pasted_segment(env):
    sid = "sess-email"
    email = ("From: Dana Example <dana@example.org>\nTo: team@example.org\n"
             "Subject: Quarterly numbers\nDate: Mon, 5 Jan 2026\n\n"
             "Hi team, the numbers are attached.")
    write_session(env.projects, sid, [typed("can you summarise this\n\n" + email, sid)])
    cc_import(env)
    um = user_messages(env.conn, sid)
    assert um and all("dana@example.org" not in m for m in um)
    kinds = [(r["voice_class"], r["detector"]) for r in turns(env.conn, sid)]
    assert ("own_typed", None) in kinds and ("pasted", "paste:structural") in kinds


def test_pasted_segment_allowlist_hook(env):
    sid = "sess-allow"
    write_session(env.projects, sid, [
        typed("what is the retention policy?", sid),
        assistant(LONG_ASSISTANT, sid),
        typed(LONG_ASSISTANT + "\n\nkeep this", sid)])
    env.config(paste_allowlist=[f"{sid}:2.0"])
    cc_import(env)
    row = [r for r in turns(env.conn, sid) if r["turn_id"] == f"{sid}:2.0"][0]
    assert row["voice_class"] == "own_typed" and row["allowlisted"] == 1
    assert row["detector"] is None and row["basis"] == "config:allowlist(paste:quote_back)"


# A synthetic marker. The real one lives only in the operator's local import
# config; the package ships no canary string (see the next two tests).
CANARY = "SYNTHETIC CANARY 7f3a: injected background follows"


def test_injection_canary_session_is_flagged_only_from_the_hook_channel(env):
    canary = CANARY
    env.config(canary_strings=[canary])
    hook = {"type": "attachment", "uuid": uid(), "sessionId": "sess-hook",
            "attachment": {"type": "hook_additional_context", "hookEvent": "SessionStart",
                           "content": [canary + "\n...spec text..."]}}
    write_session(env.projects, "sess-hook", [hook, typed("hello", "sess-hook")])
    # Mentions of the sentence anywhere else must not flag the session.
    instr = {"type": "attachment", "uuid": uid(), "sessionId": "sess-mention",
             "attachment": {"type": "instructions", "content": "The canary is " + canary}}
    write_session(env.projects, "sess-mention", [
        instr, typed(f"why does {canary} show up in the log?", "sess-mention"),
        assistant(f"It is the marker: {canary}.", "sess-mention")])
    cc_import(env)
    flags = env.conn.execute("SELECT conversation_id, flag FROM conversation_flags").fetchall()
    assert [tuple(f) for f in flags] == [("sess-hook", "injection_canary")]


def test_no_canary_ships_in_the_package():
    """The canary is config-only: the package carries no default string, so a
    private hook's marker is never published and never silently assumed."""
    from baselayer.import_config import DEFAULT_CANARIES, ImportConfig, config_from_dict
    assert DEFAULT_CANARIES == ()
    assert ImportConfig().canary_strings == ()
    assert config_from_dict({}).canary_strings == ()


def test_without_a_configured_canary_nothing_is_flagged(env):
    hook = {"type": "attachment", "uuid": uid(), "sessionId": "sess-hook",
            "attachment": {"type": "hook_additional_context", "hookEvent": "SessionStart",
                           "content": [CANARY + "\n...spec text..."]}}
    write_session(env.projects, "sess-hook", [hook, typed("hello", "sess-hook")])
    cc_import(env)
    assert env.conn.execute("SELECT COUNT(*) FROM conversation_flags").fetchone()[0] == 0


def test_sidechain_records_are_not_imported(env):
    sid = "sess-side"
    write_session(env.projects, sid, [
        typed("run the audit", sid),
        rec("user", "Subagent: read every file under src and report defects.", sid,
            isSidechain=True)])
    cc_import(env)
    assert "Subagent: read every file under src and report defects." not in user_messages(env.conn)


def test_wrappers_are_stripped_from_subject_text(env):
    sid = "sess-wrap"
    write_session(env.projects, sid, [typed(
        "<system-reminder>internal note</system-reminder>rename the folder", sid)])
    cc_import(env)
    assert user_messages(env.conn, sid) == ["rename the folder"]


def test_fork_copy_is_marked_duplicate_not_double_counted(env):
    shared = typed("pick the cheaper vendor", "sess-orig")
    write_session(env.projects, "sess-orig", [shared])
    write_session(env.projects, "sess-fork", [dict(shared), typed("new line", "sess-fork")])
    cc_import(env)
    fork = turns(env.conn, "sess-fork")
    assert fork[0]["duplicate_of"] == "sess-orig" and fork[1]["duplicate_of"] is None
    assert user_messages(env.conn).count("pick the cheaper vendor") == 1


# --------------------------------------------------------------------------- exclusion

def test_excluded_conversation_is_not_imported(env):
    write_session(env.projects, "sess-keep", [typed("keep me", "sess-keep")])
    write_session(env.projects, "sess-drop", [typed("drop me", "sess-drop")])
    env.config(exclude_conversations=["sess-drop"])
    cc_import(env)
    assert user_messages(env.conn) == ["keep me"]
    assert turns(env.conn, "sess-drop") == []
    ex = env.conn.execute("SELECT key, reason FROM import_exclusions").fetchall()
    assert [tuple(r) for r in ex] == [("sess-drop", "conversation_id")]


def test_excluded_source_class_text_file(env, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("# Architecture\n\n" + "The system has parts. " * 10,
                                          encoding="utf-8")
    env.config(exclude_sources=["text_file"])
    IC.import_text_files(env.conn, str(docs), set())
    n = env.conn.execute("SELECT COUNT(*) FROM conversations WHERE source='text_file'").fetchone()[0]
    assert n == 0


def test_config_rejects_unknown_keys(tmp_path):
    from baselayer.import_config import load_import_config
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"exclude_conversation": ["x"]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_import_config(p)


def test_config_env_var_pointing_at_missing_file_raises(monkeypatch, tmp_path):
    from baselayer.import_config import load_import_config
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(tmp_path / "nope.json"))
    with pytest.raises(FileNotFoundError):
        load_import_config()


# --------------------------------------------------------------------------- grown sessions

def test_grown_session_is_reimported_and_marked(env):
    sid = "sess-grow"
    recs = [typed("first question", sid), assistant("First answer.", sid)]
    p = write_session(env.projects, sid, recs)
    cc_import(env)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(typed("a later question", sid)) + "\n")
    cc_import(env)
    assert "a later question" in user_messages(env.conn, sid)
    st = env.conn.execute("SELECT status, revision, needs_extraction FROM import_state "
                          "WHERE conversation_id=?", (sid,)).fetchone()
    assert tuple(st) == ("grown", 2, 1)
    assert [r["turn_id"] for r in turns(env.conn, sid)] == [f"{sid}:0", f"{sid}:1", f"{sid}:2"]


def test_unchanged_session_is_skipped(env):
    sid = "sess-same"
    write_session(env.projects, sid, [typed("only question", sid)])
    cc_import(env)
    cc_import(env)
    st = env.conn.execute("SELECT status, revision FROM import_state WHERE conversation_id=?",
                          (sid,)).fetchone()
    assert tuple(st) == ("new", 1)


def test_rewritten_session_is_flagged_not_renumbered(env):
    sid = "sess-rewrite"
    p = write_session(env.projects, sid, [typed("original wording", sid)])
    cc_import(env)
    write_session(env.projects, sid, [typed("different wording", sid)])
    cc_import(env)
    assert [r["text"] for r in turns(env.conn, sid)] == ["original wording"]
    flag = env.conn.execute("SELECT flag FROM conversation_flags WHERE conversation_id=?",
                            (sid,)).fetchone()
    assert flag[0] == "non_prefix_change"
    assert p.exists()


# --------------------------------------------------------------------------- ChatGPT

def _cg_node(nid, parent, role, text, t, audio=False):
    if audio:
        content = {"content_type": "multimodal_text",
                   "parts": [{"content_type": "audio_transcription", "text": text}]}
    else:
        content = {"content_type": "text", "parts": [text]}
    return nid, {"id": nid, "parent": parent, "children": [],
                 "message": {"id": nid, "author": {"role": role}, "create_time": t,
                             "content": content, "metadata": {}}}


def _cg_conv(cid, nodes):
    mapping = dict(nodes)
    for nid, n in mapping.items():
        if n["parent"] in mapping:
            mapping[n["parent"]]["children"].append(nid)
    return {"conversation_id": cid, "title": "t", "create_time": 1.0, "update_time": 2.0,
            "mapping": mapping}


def test_chatgpt_voice_classes(env, tmp_path):
    conv = _cg_conv("cg-1", [
        _cg_node("n1", None, "user", "what is the retention policy?", 1.0),
        _cg_node("n2", "n1", "assistant", LONG_ASSISTANT, 2.0),
        _cg_node("n3", "n2", "user", LONG_ASSISTANT + "\n\nthe drill is monthly", 3.0),
        _cg_node("n4", "n3", "tool", "search results: none", 4.0),
        _cg_node("n5", "n4", "user", "I would rather keep the monthly drill because it "
                                     "catches problems early", 5.0, audio=True),
    ])
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps([conv]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    um = user_messages(env.conn, "cg-1")
    assert all(LONG_ASSISTANT not in m for m in um)
    rows = turns(env.conn, "cg-1")
    got = [(r["turn_id"], r["speaker"], r["voice_class"], r["detector"] or r["basis"]) for r in rows]
    assert got == [
        ("cg-1:0", "subject", "own_typed", "source:role"),
        ("cg-1:1", "assistant", "assistant", "source:role=assistant"),
        ("cg-1:2.0", "subject", "pasted", "paste:quote_back"),
        ("cg-1:2.1", "subject", "own_typed", "source:role"),
        ("cg-1:3", "system", "tool_result", "source:role=tool"),
        ("cg-1:4", "subject", "own_dictated", "source:audio_transcription"),
    ]


def test_chatgpt_excluded_conversation(env, tmp_path):
    convs = [_cg_conv("cg-keep", [_cg_node("a", None, "user", "keep this one", 1.0)]),
             _cg_conv("cg-drop", [_cg_node("b", None, "user", "drop this one", 1.0)])]
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps(convs), encoding="utf-8")
    env.config(exclude_conversations=["cg-drop"])
    IC.import_chatgpt(env.conn, str(f), set())
    assert user_messages(env.conn) == ["keep this one"]


def test_chatgpt_new_branch_keeps_existing_turn_ids(env, tmp_path):
    nodes = [_cg_node("a", None, "user", "first", 1.0),
             _cg_node("b", "a", "assistant", "reply one", 2.0),
             _cg_node("c", "b", "user", "second", 3.0)]
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps([_cg_conv("cg-br", nodes)]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    before = {r["turn_id"]: r["text"] for r in turns(env.conn, "cg-br")}
    # a regenerated reply to the FIRST message, created later
    nodes2 = nodes + [_cg_node("b2", "a", "assistant", "reply one, regenerated", 4.0)]
    f.write_text(json.dumps([_cg_conv("cg-br", nodes2)]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    after = {r["turn_id"]: r["text"] for r in turns(env.conn, "cg-br")}
    assert all(after[k] == v for k, v in before.items())
    assert env.conn.execute("SELECT status FROM import_state WHERE conversation_id='cg-br'"
                            ).fetchone()[0] == "grown"


# --------------------------------------------------------------------------- history.jsonl

def test_history_prompts_with_paste_tags(env, tmp_path):
    h = tmp_path / "history.jsonl"
    body = "line one of a pasted log\nline two of a pasted log"
    entries = [
        {"display": "rename the export folder", "pastedContents": {}, "timestamp": 1000,
         "project": "/p", "sessionId": "h-1"},
        {"display": "look at this [Pasted text #1 +2 lines] and tell me why",
         "pastedContents": {"1": {"id": 1, "type": "text", "content": body}},
         "timestamp": 2000, "project": "/p", "sessionId": "h-1"},
        {"display": "/clear", "pastedContents": {}, "timestamp": 3000, "project": "/p",
         "sessionId": "h-1"},
        {"display": "covered prompt", "pastedContents": {}, "timestamp": 4000, "project": "/p",
         "sessionId": "sess-has-transcript"},
    ]
    h.write_text("\n".join(json.dumps(e) for e in entries + entries[:1]) + "\n", encoding="utf-8")
    write_session(env.projects, "sess-has-transcript",
                  [typed("covered prompt", "sess-has-transcript")])
    cc_import(env)
    IC.import_history(env.conn, [h], set())
    rows = turns(env.conn, "history_h-1")
    got = [(r["turn_id"], r["voice_class"], r["detector"], r["text"]) for r in rows]
    assert got == [
        ("history_h-1:0", "own_typed", None, "rename the export folder"),
        ("history_h-1:1.0", "own_typed", None, "look at this "),
        ("history_h-1:1.1", "pasted", "paste:tag", body),
        ("history_h-1:1.2", "own_typed", None, " and tell me why"),
    ]
    assert turns(env.conn, "history_sess-has-transcript") == []


# --------------------------------------------------------------------------- meetings

MEETING = """# Weekly sync

  Meeting started: 1/5/2026, 9:00:00 AM
  Participants: Pat Q, Lee R

  ## Notes

  Action items were discussed.

  ## Transcript

00:01 Pat Q: I think we should ship the smaller version first
00:02 Lee R: That works for me
and I can write the release note
00:03 Pat Q: then let's do it
"""


def test_meeting_speaker_mapping_is_config_driven(env, tmp_path):
    f = tmp_path / "sync.txt"
    f.write_text(MEETING, encoding="utf-8")
    env.config(meeting_subject_labels=["Pat Q"])
    IC.import_meetings(env.conn, f, set())
    conv = env.conn.execute("SELECT id FROM conversations WHERE source='meeting'").fetchone()[0]
    got = [(r["speaker"], r["voice_class"], r["text"]) for r in turns(env.conn, conv)]
    assert got == [
        ("subject", "own_dictated", "I think we should ship the smaller version first"),
        ("other", "other_person", "That works for me\nand I can write the release note"),
        ("subject", "own_dictated", "then let's do it"),
    ]
    # Same file, the other participant configured as the subject.
    env.conn.execute("DELETE FROM turns")
    env.conn.execute("DELETE FROM import_state")
    env.config(meeting_subject_labels=["lee r"])
    IC.import_meetings(env.conn, f, set())
    got = [(r["speaker"], r["voice_class"]) for r in turns(env.conn, conv)]
    assert got == [("other", "other_person"), ("subject", "own_dictated"),
                   ("other", "other_person")]


def test_meeting_without_subject_label_is_refused(env, tmp_path):
    f = tmp_path / "sync.txt"
    f.write_text(MEETING, encoding="utf-8")
    with pytest.raises(ValueError):
        IC.import_meetings(env.conn, f, set())
    env.config(meeting_subject_labels=["Nobody Here"])
    IC.import_meetings(env.conn, f, set())
    assert env.conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 0


def test_history_prompt_also_in_a_transcript_is_marked_duplicate(env, tmp_path):
    long_prompt = "move the nightly backup to sunday and keep ninety days of snapshots"
    write_session(env.projects, "sess-other-id", [typed(long_prompt, "sess-other-id")])
    cc_import(env)
    h = tmp_path / "history.jsonl"
    h.write_text("\n".join(json.dumps(e) for e in [
        {"display": long_prompt, "pastedContents": {}, "timestamp": 1, "sessionId": "h-2"},
        {"display": "ok", "pastedContents": {}, "timestamp": 2, "sessionId": "h-2"},
    ]) + "\n", encoding="utf-8")
    write_session(env.projects, "sess-ok", [typed("ok", "sess-ok")])
    cc_import(env)
    IC.import_history(env.conn, [h], set())
    rows = turns(env.conn, "history_h-2")
    assert [(r["text"], r["duplicate_of"]) for r in rows] == [
        (long_prompt, "sess-other-id"), ("ok", None)]


def test_attached_triple_dash_separates_own_text_from_a_paste(env):
    # "---" typed directly against words (no surrounding spaces) still separates the
    # subject's own line from what follows it.
    sid = "sess-dash"
    email = ("From: Dana Example <dana@example.org>\nTo: team@example.org\n"
             "Subject: Quarterly numbers\nDate: Mon, 5 Jan 2026\n\nHi team, attached.")
    write_session(env.projects, sid, [typed("this is the thread i meant---" + email, sid)])
    cc_import(env)
    um = user_messages(env.conn, sid)
    assert len(um) == 1 and um[0].startswith("this is the thread i meant")
    assert "dana@example.org" not in um[0]


def test_allowlist_added_after_import_takes_effect_and_can_be_revoked(env):
    sid = "sess-allow-later"
    write_session(env.projects, sid, [
        typed("what is the retention policy?", sid),
        assistant(LONG_ASSISTANT, sid),
        typed(LONG_ASSISTANT + "\n\nkeep this", sid)])
    cc_import(env)
    assert all(LONG_ASSISTANT not in m for m in user_messages(env.conn, sid))
    env.config(paste_allowlist=[f"{sid}:2.0"])
    cc_import(env)  # source unchanged; the allowlist must still apply
    row = [r for r in turns(env.conn, sid) if r["turn_id"] == f"{sid}:2.0"][0]
    assert (row["voice_class"], row["allowlisted"]) == ("own_typed", 1)
    assert any(LONG_ASSISTANT in m for m in user_messages(env.conn, sid))
    env.config(paste_allowlist=[])
    cc_import(env)
    row = [r for r in turns(env.conn, sid) if r["turn_id"] == f"{sid}:2.0"][0]
    assert (row["voice_class"], row["detector"], row["allowlisted"]) == (
        "pasted", "paste:quote_back", 0)
    assert all(LONG_ASSISTANT not in m for m in user_messages(env.conn, sid))


def test_exclusion_added_after_import_removes_the_conversation(env, tmp_path):
    write_session(env.projects, "sess-late", [typed("remove me later", "sess-late")])
    cc_import(env)
    assert turns(env.conn, "sess-late")
    env.config(exclude_conversations=["sess-late"])
    cc_import(env)
    assert turns(env.conn, "sess-late") == []
    assert "remove me later" not in user_messages(env.conn)
    # the same for a ChatGPT conversation
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps([_cg_conv("cg-late", [_cg_node("a", None, "user", "later", 1.0)])]),
                 encoding="utf-8")
    env.config()
    IC.import_chatgpt(env.conn, str(f), set())
    env.config(exclude_conversations=["cg-late"])
    IC.import_chatgpt(env.conn, str(f), set())
    assert turns(env.conn, "cg-late") == []


def test_exclusion_by_path_glob(env):
    write_session(env.projects, "sess-a", [typed("from project a", "sess-a")], project="proj-a")
    write_session(env.projects, "sess-b", [typed("from project b", "sess-b")], project="proj-b")
    env.config(exclude_path_globs=["*/proj-b/*"])
    cc_import(env)
    assert user_messages(env.conn) == ["from project a"]


def test_database_stamped_under_another_contract_version_is_refused(env):
    from baselayer.turns import ensure_turn_tables, TurnContractMismatch
    ensure_turn_tables(env.conn)
    env.conn.execute("UPDATE turn_contract SET value='turn-contract/0' WHERE key='version'")
    env.conn.commit()
    write_session(env.projects, "sess-v", [typed("hello", "sess-v")])
    with pytest.raises(TurnContractMismatch):
        cc_import(env)
    assert env.conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 0


def test_two_meetings_with_the_same_timestamps_both_reach_messages(env, tmp_path):
    env.config(meeting_subject_labels=["Pat Q"])
    (tmp_path / "m1.txt").write_text(MEETING, encoding="utf-8")
    (tmp_path / "m2.txt").write_text(MEETING.replace("smaller version", "larger version"),
                                     encoding="utf-8")
    IC.import_meetings(env.conn, tmp_path, set())
    per_conv = env.conn.execute(
        "SELECT conversation_id, COUNT(*) FROM messages WHERE role='user' GROUP BY 1").fetchall()
    assert sorted(n for _, n in per_conv) == [2, 2]
