"""Planted known-bad Claude Code sessions for a turn-contract pilot. Synthetic text only.

A pilot extracts from a sample of real conversations and reads the gate counts. Those counts
cannot say whether the gate would have caught a specific bad input, because nobody knows which
real turns are bad. These sessions supply the known answers: each one plants inputs whose
correct classification is fixed in advance, so a pilot that imports them beside its real sample
can check the import and the stored facts against a manifest instead of against impressions.

What is planted, one session each, every session also carrying one own-voice turn with a clear
fact so that each file yields something citable:

  compaction   a compaction summary, both forms: the isCompactSummary flag and the text
               signature older clients wrote without the flag
  harness      a harness prompt, both forms: isMeta, and promptSource "sdk"
  paste        a typed turn whose second paragraph is a pasted log block
  quote_back   a typed turn that quotes the assistant's previous turn back, then comments
  tool_result  a user record carrying a tool_result block
  canary       (only when a canary marker is given) a SessionStart hook attachment carrying
               it, so the importer flags the conversation as injected

Use:
    manifest = write_planted_sessions(out_dir)            # files + planted_manifest.json
    import_conversations.import_claude_code(conn, existing, session_files=manifest["files"])
    problems = check_import(conn, manifest)               # [] when every turn classed right
    ... extract ...
    problems = check_stored_facts(conn, manifest)         # [] when no fact rests on a bad turn

Ids are uuid5 under a fixed namespace, so they are stable across runs and cannot collide with a
real session's uuid4 records (a collision would make the importer mark turns as fork copies).
Every session id starts with PLANTED_PREFIX. The canary marker is a parameter, never a default:
the real one must not be written into the repository.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

PLANTED_PREFIX = "planted-"
MANIFEST_NAME = "planted_manifest.json"
_NS = uuid.UUID("5b1e5a1e-7c0d-4e11-9a3e-0000b1a57ed0")
_TS = "2026-01-06T10:00:%02d.000Z"
CITABLE = ("own_typed", "own_dictated")

OWN_FACT = ("I always write the failing test before I change the code, because a test that "
            "never failed proves nothing.")
ASSISTANT_LONG = ("The release checklist asks for a changelog entry, a version bump in the "
                  "package metadata, and a tagged commit on the main branch before anything "
                  "is published.")
COMPACT_FLAGGED = ("This session is being continued from a previous conversation that ran out of "
                   "context. Summary: the user prefers tabs over spaces and deploys on Fridays.")
COMPACT_TEXT = ("This session is being continued from a previous conversation that ran out of "
                "context. The user said they never review pull requests after six in the evening.")
HARNESS_META = ("Harness note: the scheduled job will now summarise the repository "
                "and report the open issues to the operator.")
HARNESS_SDK = ("You are a code reviewer. Read the diff below and list every function that lacks "
               "a docstring, one per line.")
PASTE_OWN = "Here is what the deploy printed, can you tell me why it failed?"
PASTE_LOG = ("2026-01-05 10:00:01 ERROR worker crashed on start\n"
             "2026-01-05 10:00:02 ERROR retry limit reached for queue billing\n"
             "2026-01-05 10:00:03 INFO shutting down after three failed attempts")
QUOTE_OWN = "I disagree with that order, I want the version bump to come last."
TOOL_RESULT_TEXT = "total 12 files changed, 340 insertions, 18 deletions in the working tree"


def _uid(sid: str, n: int) -> str:
    return str(uuid.uuid5(_NS, "%s/%d" % (sid, n)))


class _Session:
    def __init__(self, key: str):
        self.sid = PLANTED_PREFIX + key
        self.records, self.expect = [], []
        self._n = 0

    def _rec(self, kind, content, **kw):
        self._n += 1
        r = {"type": kind, "uuid": _uid(self.sid, self._n), "sessionId": self.sid,
             "parentUuid": None, "timestamp": _TS % self._n, "userType": "external",
             "entrypoint": "cli", "cwd": "/work/planted", "isSidechain": False,
             "message": {"role": kind, "content": content}}
        r.update(kw)
        self.records.append(r)

    def typed(self, text, **kw):
        kw.setdefault("promptSource", "typed")
        kw.setdefault("origin", {"kind": "human"})
        self._rec("user", text, **kw)

    def assistant(self, text):
        self._rec("assistant", [{"type": "text", "text": text}])

    def plant(self, key, text, voice_class, detector, probe):
        """Expect a turn row with exactly `text`, classed `voice_class` by `detector`. `probe`
        is a verbatim span of it a model might cite; a fact resting on it must be rejected
        unless the class is citable."""
        assert probe in text, (key, probe)
        self.expect.append({"key": key, "text": text, "voice_class": voice_class,
                            "detector": detector, "citable": voice_class in CITABLE,
                            "probe_span": probe})


def planted_sessions(canary: str | None = None) -> list[_Session]:
    """Build the planted sessions in memory. Detector names are the importer's own (voice.py)."""
    from baselayer import voice as V
    out = []

    s = _Session("compaction")
    s.typed(OWN_FACT)
    s.plant("own_fact", OWN_FACT, "own_typed", None, "write the failing test before I change")
    s.assistant("Understood.")
    s.typed(COMPACT_FLAGGED, isCompactSummary=True)
    s.plant("compaction_flag", COMPACT_FLAGGED, "compaction_summary", V.D_COMPACT_FLAG,
            "the user prefers tabs over spaces")
    s.typed(COMPACT_TEXT)
    s.plant("compaction_text", COMPACT_TEXT, "compaction_summary", V.D_COMPACT_TEXT,
            "never review pull requests after six")
    out.append(s)

    s = _Session("harness")
    s.typed(OWN_FACT)
    s.plant("own_fact", OWN_FACT, "own_typed", None, "a test that never failed proves nothing")
    s.assistant("Noted.")
    s.typed(HARNESS_META, isMeta=True)
    s.plant("harness_meta", HARNESS_META, "harness_prompt", V.D_IS_META,
            "summarise the repository and report the open issues")
    s.typed(HARNESS_SDK, promptSource="sdk", origin=None)
    s.plant("harness_sdk", HARNESS_SDK, "harness_prompt", V.D_SDK_PROMPT,
            "list every function that lacks a docstring")
    out.append(s)

    s = _Session("paste")
    s.typed(OWN_FACT)
    s.plant("own_fact", OWN_FACT, "own_typed", None, "write the failing test before I change")
    s.assistant("Sure, send it over.")
    s.typed(PASTE_OWN + "\n\n" + PASTE_LOG)
    s.plant("paste_own", PASTE_OWN, "own_typed", None, "can you tell me why it failed")
    s.plant("paste_block", PASTE_LOG, "pasted", V.D_PASTE_TERMINAL,
            "retry limit reached for queue billing")
    out.append(s)

    s = _Session("quote_back")
    s.typed(OWN_FACT)
    s.plant("own_fact", OWN_FACT, "own_typed", None, "write the failing test before I change")
    s.assistant(ASSISTANT_LONG)
    s.typed(ASSISTANT_LONG + "\n\n" + QUOTE_OWN)
    s.plant("quote_back", ASSISTANT_LONG, "pasted", V.D_PASTE_QUOTE_BACK,
            "a tagged commit on the main branch")
    s.plant("quote_own", QUOTE_OWN, "own_typed", None, "want the version bump to come last")
    out.append(s)

    s = _Session("tool_result")
    s.typed(OWN_FACT)
    s.plant("own_fact", OWN_FACT, "own_typed", None, "write the failing test before I change")
    s.assistant("[tool: Bash]")
    s._rec("user", [{"type": "tool_result", "tool_use_id": "toolu_planted",
                     "content": TOOL_RESULT_TEXT}])
    # The importer never stores tool output: the row holds a placeholder, so the planted text
    # must NOT appear in the turn table at all. Checked by check_import.
    s.plant("tool_result", V.TOOL_RESULT_PLACEHOLDER, "tool_result", V.D_TOOL_RESULT_BLOCK,
            V.TOOL_RESULT_PLACEHOLDER)
    s.expect[-1]["absent_text"] = TOOL_RESULT_TEXT
    out.append(s)

    if canary:
        s = _Session("canary")
        s.records.append({"type": "attachment", "uuid": _uid(s.sid, 0), "sessionId": s.sid,
                          "attachment": {"type": "hook_additional_context",
                                         "hookEvent": "SessionStart",
                                         "content": [canary + " (planted)"]}})
        s.typed(OWN_FACT)
        s.plant("own_fact", OWN_FACT, "own_typed", None, "write the failing test before I change")
        s.expect_flag = "injection_canary"
        out.append(s)
    return out


def write_planted_sessions(out_dir, *, canary: str | None = None,
                           project: str = "planted-pilot") -> dict:
    """Write one JSONL per planted session under out_dir/<project>/, plus a manifest.

    Returns the manifest: {"files": [...], "sessions": {session_id: {"expect": [...],
    "flag": ...}}}. Paths in the manifest are as written; the manifest file itself is
    <out_dir>/planted_manifest.json."""
    root = Path(out_dir)
    d = root / project
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"prefix": PLANTED_PREFIX, "files": [], "sessions": {}}
    for s in planted_sessions(canary):
        p = d / (s.sid + ".jsonl")
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in s.records) + "\n",
                     encoding="utf-8")
        manifest["files"].append(str(p))
        manifest["sessions"][s.sid] = {"expect": s.expect,
                                       "flag": getattr(s, "expect_flag", None)}
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    return manifest


def check_import(conn, manifest: dict) -> list[str]:
    """Compare the turn table with the manifest. Returns problems; [] means every planted turn
    was stored with the expected class and detector, and no tool output was stored."""
    problems = []
    for sid, sess in manifest["sessions"].items():
        rows = conn.execute("SELECT voice_class, detector, text FROM turns "
                            "WHERE conversation_id = ?", (sid,)).fetchall()
        if not rows:
            problems.append("%s: no turn rows (not imported?)" % sid)
            continue
        for e in sess["expect"]:
            hits = [r for r in rows if r[2] == e["text"]]
            if not hits:
                problems.append("%s/%s: no turn row with the planted text" % (sid, e["key"]))
                continue
            got = {(r[0], r[1]) for r in hits}
            if (e["voice_class"], e["detector"]) not in got:
                problems.append("%s/%s: expected %s by %s, got %s"
                                % (sid, e["key"], e["voice_class"], e["detector"], sorted(got)))
            if e.get("absent_text") and any(e["absent_text"] in (r[2] or "") for r in rows):
                problems.append("%s/%s: tool output was stored as turn text" % (sid, e["key"]))
        if sess.get("flag"):
            try:
                flagged = conn.execute("SELECT 1 FROM conversation_flags WHERE "
                                       "conversation_id = ? AND flag = ?",
                                       (sid, sess["flag"])).fetchone()
            except Exception:
                flagged = None
            if not flagged:
                problems.append("%s: expected conversation flag %s" % (sid, sess["flag"]))
    return problems


def check_stored_facts(conn, manifest: dict) -> list[str]:
    """After extraction: no live fact may cite a planted turn that is not own voice.
    Returns problems; [] means no fact rests on a planted bad turn.
    (Whether the own-voice turns yielded a fact is a model outcome, reported, not required.)

    AUDN NOOP merges evidence spans across conversations, so a fact stored under one
    conversation can cite turns of another, planted or real. Every span's ``turn_id`` is
    therefore resolved against the whole turn table, and every live fact is read, not only
    the facts stored under a planted conversation. A span on a planted turn that is not
    citable is a problem wherever the fact is stored. A span that resolves to no turn is a
    problem when it names a planted conversation or sits on a fact stored under one."""
    planted = set(manifest["sessions"])

    def in_planted(tid):
        conv = tid.rsplit(":", 1)[0] if ":" in tid else tid
        return conv in planted

    voice = {}  # turn_id -> (conversation_id, voice_class), filled on demand
    problems = []
    facts = conn.execute("SELECT id, source_conversation_id, evidence_spans FROM memory_facts "
                         "WHERE superseded_by IS NULL AND evidence_spans IS NOT NULL "
                         "ORDER BY source_conversation_id, id").fetchall()
    for fid, conv, spans in facts:
        for sp in json.loads(spans or "[]"):
            tid = sp.get("turn_id") or ""
            if tid not in voice:
                voice[tid] = conn.execute("SELECT conversation_id, voice_class FROM turns "
                                          "WHERE turn_id = ?", (tid,)).fetchone()
            hit = voice[tid]
            if hit is None:
                if conv in planted or in_planted(tid):
                    problems.append("%s: fact %s cites %s (unknown turn)" % (conv, fid, tid))
            elif hit[0] in planted and hit[1] not in CITABLE:
                problems.append("%s: fact %s cites %s (%s)" % (conv, fid, tid, hit[1]))
    return problems


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Write planted known-bad Claude Code sessions "
                                             "and their manifest (synthetic text only).")
    ap.add_argument("out_dir")
    ap.add_argument("--canary", default=None,
                    help="marker text to plant in a SessionStart hook attachment; must match "
                         "a canary_strings entry in the import config to be flagged")
    a = ap.parse_args(argv)
    m = write_planted_sessions(a.out_dir, canary=a.canary)
    print("wrote %d planted sessions and %s under %s"
          % (len(m["files"]), MANIFEST_NAME, a.out_dir))


if __name__ == "__main__":
    main()
