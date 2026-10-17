"""Queued prompts written with no origin (an older client).

Queued prompts are the subject's words when their origin is human. An older client wrote
queued prompts with no origin at all, and wrote background-task notifications the same
way; only commandMode ("prompt" vs "task-notification") separates them. The importer drops
originless prompts and counts them. Whether to keep them is the subject's decision, so the
switch exists and is OFF by default; notifications stay out with it on.
"""
import json

import baselayer.import_conversations as IC
from baselayer import import_config as IC_CFG
from baselayer import turn_import as TI
from baselayer.voice import CITABLE_VOICE_CLASSES
from tests.test_turn_contract_import import (  # noqa: F401  (env is a fixture)
    LONG_ASSISTANT, assistant, cc_import, env, queued, typed, turns, write_session,
)

ORIGINLESS = "and after that rerun the import into a fresh directory please"


def _session(env):
    sid = "sess-queued-old"
    write_session(env.projects, sid, [typed("start the import dry run", sid),
                                      assistant("Starting it now.", sid),
                                      queued(ORIGINLESS, sid, kind=None)])
    return sid


def test_originless_queued_prompt_is_excluded_by_default(env):
    sid = _session(env)
    cc_import(env)
    assert ORIGINLESS not in [r["text"] for r in turns(env.conn, sid)]


def test_switch_includes_it_as_own_typed_with_its_own_basis(env):
    env.config(include_originless_queued=True)
    sid = _session(env)
    cc_import(env)
    rows = [r for r in turns(env.conn, sid) if r["text"] == ORIGINLESS]
    assert len(rows) == 1
    assert rows[0]["voice_class"] in CITABLE_VOICE_CLASSES
    assert rows[0]["basis"] == "recovered:queued_no_origin"
    assert rows[0]["detector"] is None


def test_switch_does_not_admit_non_prompt_or_non_human_queued_records(env):
    env.config(include_originless_queued=True)
    sid = "sess-queued-other"
    write_session(env.projects, sid, [typed("start", sid),
                                      queued("a task notification body text here", sid,
                                             kind="task-notification"),
                                      queued("/compact", sid, kind=None, mode="bash")])
    cc_import(env)
    texts = [r["text"] for r in turns(env.conn, sid)]
    assert "a task notification body text here" not in texts and "/compact" not in texts


def test_config_key_is_known_and_off_by_default(tmp_path):
    assert IC_CFG.config_from_dict({}).include_originless_queued is False
    assert IC_CFG.config_from_dict({"include_originless_queued": True}).include_originless_queued is True


# The shape an older client actually wrote for a background-task notification: no origin
# field at all, commandMode "task-notification", body a <task-notification> block. It is
# the same "no origin" as a subject's queued prompt; only commandMode tells them apart.
NOTIFICATION = ("<task-notification>\n<task-id>b0000000</task-id>\n<status>completed</status>\n"
                "<summary>Background command finished</summary>\n</task-notification>")


def test_switch_on_still_excludes_originless_task_notifications(env):
    env.config(include_originless_queued=True)
    sid = "sess-queued-notify"
    path = write_session(env.projects, sid, [
        typed("start the long job", sid),
        assistant("Started in the background.", sid),
        queued(NOTIFICATION, sid, kind=None, mode="task-notification"),
        queued(ORIGINLESS, sid, kind=None)])
    cc_import(env)
    rows = turns(env.conn, sid)
    assert all("task-notification" not in r["text"] for r in rows)
    assert [r["basis"] for r in rows if r["text"] == ORIGINLESS] == ["recovered:queued_no_origin"]
    # The record detail counts the notification as not-a-prompt, never as a missing origin:
    # the wrapper stripper would also drop its text, so only the count shows which gate held.
    config = IC_CFG.load_import_config(env.cfg)
    counts = TI.build_claude_code_turns(path, TI.build_claude_code_context([path], config),
                                        config).counts
    assert counts["queued_prompt_origin_missing"] == 1
    assert counts["queued_not_human_prompt"] == 1


def test_voice_detectors_run_on_originless_queued_prompts(env):
    env.config(include_originless_queued=True)
    sid = "sess-queued-quote"
    own = "that part is wrong, the drill is monthly not quarterly"
    write_session(env.projects, sid, [typed("what is the retention policy?", sid),
                                      assistant(LONG_ASSISTANT, sid),
                                      queued(LONG_ASSISTANT + "\n\n" + own, sid, kind=None)])
    cc_import(env)
    rows = [r for r in turns(env.conn, sid) if r["turn_id"].startswith(f"{sid}:2")]
    assert [(r["voice_class"], r["detector"]) for r in rows] == [
        ("pasted", "paste:quote_back"), ("own_typed", None)]
    assert rows[1]["text"] == own and rows[1]["basis"] == "recovered:queued_no_origin"


# --------------------------------------------------------------------------- append-only feeder
# Rewriting a session with the switch on renumbers every later turn and breaks the citations of
# facts already extracted from it. The feeder writes the originless prompts of a session as their
# own conversation, queued_<sid>, and leaves the session's turns untouched.

def _feed(env, files=None):
    files = files if files is not None else sorted(env.projects.rglob("*.jsonl"))
    return IC.import_originless_queued(env.conn, files, IC.get_existing_conversation_ids(env.conn))


def test_feeder_writes_a_separate_conversation_and_moves_no_session_turn(env):
    sid = "sess-feed-ids"
    write_session(env.projects, sid, [typed("start the import dry run", sid),
                                      assistant("Starting it now.", sid),
                                      queued(ORIGINLESS, sid, kind=None),
                                      assistant("Done with the dry run.", sid),
                                      typed("now check the counts", sid)])
    cc_import(env)
    before = turns(env.conn, sid)
    _feed(env)
    assert turns(env.conn, sid) == before
    rows = turns(env.conn, f"queued_{sid}")
    assert [(r["turn_id"], r["voice_class"], r["basis"], r["text"]) for r in rows] == [
        (f"queued_{sid}:0", "own_typed", "recovered:queued_no_origin", ORIGINLESS)]
    src = env.conn.execute("SELECT source FROM conversations WHERE id=?", (f"queued_{sid}",)).fetchone()
    assert tuple(src) == ("claude_code_queued",)


def test_feeder_classifies_with_the_preceding_assistant_text(env):
    sid = "sess-feed-quote"
    own = "that part is wrong, the drill is monthly not quarterly"
    write_session(env.projects, sid, [typed("what is the retention policy?", sid),
                                      assistant(LONG_ASSISTANT, sid),
                                      queued(LONG_ASSISTANT + "\n\n" + own, sid, kind=None)])
    _feed(env)
    rows = turns(env.conn, f"queued_{sid}")
    assert [(r["voice_class"], r["detector"]) for r in rows] == [
        ("pasted", "paste:quote_back"), ("own_typed", None)]
    assert rows[1]["text"] == own


def test_feeder_takes_only_originless_prompts(env):
    sid = "sess-feed-only"
    write_session(env.projects, sid, [
        typed("start the long job", sid),
        assistant("Started in the background.", sid),
        queued("a queued prompt typed with an origin", sid, kind="human"),
        queued(NOTIFICATION, sid, kind=None, mode="task-notification"),
        queued("a task notification body text here", sid, kind="task-notification"),
        # no origin and no wrapper: only commandMode keeps this one out
        queued("background job finished with exit code 0", sid, kind=None, mode="task-notification"),
        queued(ORIGINLESS, sid, kind=None)])
    _feed(env)
    assert [r["text"] for r in turns(env.conn, f"queued_{sid}")] == [ORIGINLESS]


def test_feeder_session_without_originless_prompts_writes_nothing(env):
    sid = "sess-feed-none"
    write_session(env.projects, sid, [typed("start", sid), assistant("ok", sid)])
    _feed(env)
    assert env.conn.execute("SELECT count(*) FROM conversations WHERE id=?",
                            (f"queued_{sid}",)).fetchone()[0] == 0


def test_feeder_rerun_is_unchanged_even_when_the_session_grew(env):
    sid = "sess-feed-rerun"
    recs = [typed("start", sid), assistant("Starting.", sid), queued(ORIGINLESS, sid, kind=None)]
    path = write_session(env.projects, sid, recs)
    _feed(env)
    first = turns(env.conn, f"queued_{sid}")
    # the session file grows by records that are not originless prompts
    write_session(env.projects, sid, recs + [assistant("Still going.", sid), typed("and?", sid)])
    status = IC.import_originless_queued(env.conn, [path], IC.get_existing_conversation_ids(env.conn))
    assert status == {"unchanged": 1}
    assert turns(env.conn, f"queued_{sid}") == first


def test_feeder_refuses_when_the_switch_is_on(env):
    env.config(include_originless_queued=True)
    sid = "sess-feed-switch"
    write_session(env.projects, sid, [typed("start", sid), queued(ORIGINLESS, sid, kind=None)])
    import pytest
    with pytest.raises(ValueError, match="include_originless_queued"):
        _feed(env)
