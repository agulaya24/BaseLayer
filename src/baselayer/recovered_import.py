"""Importers for recovered Claude Code sources (docs/core/TURN_CONTRACT.md, sections 1-2).

Two source kinds that the live importers do not read:

* **Database copies** (``claude_code_db_copy``). Claude Code sessions that survive only as
  rows in an old corpus database (``conversations`` + ``messages``), written by the
  pre-contract importer. That importer:

  - stored tool calls as ``[tool: X]`` and tool results as ``[tool result]`` lines;
  - kept harness wrappers (system reminders, command tags, task notifications) in the text;
  - discarded every source flag (``isCompactSummary``, ``promptSource``, ``isMeta``,
    ``origin``, ``entrypoint``, ``cwd``);
  - skipped any session id it had already imported, so each copy stops at its first import.

  So the stored role is the only speaker evidence. The text detectors from
  ``baselayer.voice`` run on the stored text, and two record-level signals replace the
  lost source flags:

  - *history corroboration*: a stored user turn that aligns with a ``history.jsonl``
    prompt of the same session was submitted at the prompt. Its ``basis`` says so, it
    takes the prompt's timestamp, and the prompt's paste placeholders locate the pasted
    block in the stored text exactly (``paste:tag``);
  - *repeated and never submitted*: a text of 8+ words that recurs 3+ times across the
    copies and matches no history prompt anywhere is a loop or scheduled prompt
    (``text:repeated_unhistoried_prompt``). On raw transcripts, where source flags say
    what each record is, this rule caught only ``promptSource=sdk`` and ``isMeta``
    records and no human prompt.

  Every copy carries the conversation flags ``provenance`` and
  ``truncated_at_first_import`` (confirmed by stored timestamps where the copy has them,
  otherwise a positional count). History prompts that a copy carries are marked
  ``duplicate_of`` the copy (context and all, the copy's turn is the one kept); prompts
  after the copy ends stay history turns. The marking runs from both sides, so import
  order does not matter.

* **Claude Desktop local-agent-mode sessions** (``claude_desktop_agent``). These are
  Claude Code JSONL written by the Desktop app, so they go through
  ``turn_import.build_claude_code_turns`` unchanged. Only the session JSONL is read: the
  per-session metadata file supplies a title, and its system prompt and account fields are
  never read into the corpus. The audit log beside each session echoes the same records
  and is not imported.

This module also holds the history-side hooks ``import_conversations.import_history``
calls: marking history prompts a copy carries, and keeping prompts typed after a raw
transcript copy ends.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from baselayer import history_align as HA
from baselayer import turn_import as TI
from baselayer import voice as V
from baselayer.import_config import ImportConfig, load_import_config
from baselayer.turns import (TurnRow, _rewrite_messages, _rows_from_db, ensure_turn_tables,
                             record_exclusion, set_flag, write_conversation)

SOURCE_DB_COPY = "claude_code_db_copy"
SOURCE_DESKTOP = "claude_desktop_agent"
DB_COPY_PREFIX = "dbcopy_"
HISTORY_PREFIX = "history_"

D_TOOL_CALL_PLACEHOLDER = "text:tool_call_placeholder"
D_REPEATED_UNHISTORIED = "text:repeated_unhistoried_prompt"
D_HARNESS_SIGNATURE = "text:harness_signature"
D_LOOP_TEMPLATE = "text:recurring_loop_template"
D_LOOP_MONITOR = "text:loop_monitor_prompt"
B_DB_ROLE = "db_copy:role"
CORROBORATED = "+history"

REPEAT_MIN_COUNT = 3
REPEAT_MIN_WORDS = 8
# A history prompt this long after a raw transcript's last record was typed after the
# copy was taken (a live transcript records a prompt within seconds).
LATER_THAN_TRANSCRIPT_S = 3600

_TOOL_CALL_LINE_RE = re.compile(r"^\[tool: [^\]\n]*\]$")

# Loop and scheduled prompts. A ScheduleWakeup or CronCreate prompt fires back into the
# session as a user message; a copy keeps only "[tool: ScheduleWakeup]" for the call and
# the fired prompt as a plain user row, and the prompt is never in history.jsonl. Both rules
# below apply only to a stored user turn that no history prompt corroborates, of
# REPEAT_MIN_WORDS or more (so "yes" and "go ahead" never qualify), in a session whose
# assistant called a scheduler tool.
SCHEDULER_TOOLS = ("ScheduleWakeup", "CronCreate")
# Monitor phrasings of the scheduled prompts in the recovered copies. Measured on one real
# history: with the scheduler-session gate, no history-corroborated turn in a scheduler session
# matched, and without the gate about 1 in 4,000 turns across all copies did.
LOOP_MONITOR_RE = re.compile(
    r"^monitoring cycle\b|schedule next wakeup|don'?t report unless"
    r"|^check\b[^\n]{0,80}?\bprogress\b|\bsync\.\s*(report milestones\.)?\s*$",
    re.IGNORECASE)
# Same-template prompts: a word 3-shingle Jaccard at or above this links two turns; a linked
# group is a loop template when at least LOOP_TEMPLATE_MIN_WAKES of its turns come straight
# after a scheduler call. A message the person resubmits is similar but not wake-driven.
LOOP_TEMPLATE_JACCARD = 0.2
LOOP_TEMPLATE_MIN_WAKES = 2
# Openings of harness text that a raw transcript marks with isMeta or a task-notification
# origin, and that a database copy keeps as plain user text. Matched against the
# normalized text after wrapper stripping. On raw transcripts every match was an isMeta
# record (the task-notification trailers sit inside the wrapper there, so they cannot be
# measured on raw data; the phrases are the harness's own).
HARNESS_OPENINGS = (
    "read the output file to retrieve the result",
    "full transcript available at:",
    "tool loaded.",
    "implement the following plan:",
    "continue from where you left off.",
    "base directory for this skill:",
    "stop hook feedback:",
    "<local-command-stderr>",
)


# =========================================================================== reading copies

def open_copy_readonly(path) -> sqlite3.Connection:
    """Open an old corpus database without any chance of writing to it.

    ``immutable=1`` stops SQLite touching the file or its ``-shm``, but it also ignores
    the WAL, so a database whose WAL still holds pages would be read without them.
    Refuse that case instead of reading a partial copy.
    """
    path = Path(path)
    wal = path.with_name(path.name + "-wal")
    if wal.exists() and wal.stat().st_size > 0:
        raise RuntimeError(f"{path}: its WAL holds unflushed pages; an immutable read would "
                           f"miss them. Checkpoint a copy of it first.")
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)


@dataclass
class StoredMessage:
    id: str
    role: str
    text: str
    created_at: float | None


@dataclass
class DbCopySession:
    sid: str
    label: str
    path: str
    title: str
    created_at: float | None
    updated_at: float | None
    messages: list

    def content_key(self) -> str:
        blob = json.dumps([(m.id, m.role, m.text) for m in self.messages], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8", "surrogatepass")).hexdigest()

    @property
    def redacted(self) -> bool:
        return any("[REDACTED" in m.text for m in self.messages)

    @property
    def size(self):
        return (len(self.messages), sum(len(m.text) for m in self.messages))


def _label(path: Path) -> str:
    for part in reversed(path.parent.parts):
        if part.lower() not in ("database", "data"):
            return part
    return path.stem


def load_db_copy_sessions(db_paths):
    """sid -> DbCopySession, one per session across all databases, plus dedup stats.

    ``db_paths``: paths, or ``(label, path)`` pairs, in priority order. The same session
    held identically by several databases is kept once. When copies differ, a copy
    carrying ``[REDACTED`` markers wins over one without (it is the same text with
    secrets removed); otherwise the larger copy wins, then the earlier database.
    """
    out: dict = {}
    stats = collections.Counter()
    for item in db_paths:
        label, path = item if isinstance(item, tuple) else (None, item)
        path = Path(path)
        label = label or _label(path)
        src = open_copy_readonly(path)
        try:
            convs = src.execute("SELECT id, title, created_at, updated_at FROM conversations "
                                "WHERE source='claude_code' ORDER BY id").fetchall()
            for sid, title, ca, ua in convs:
                msgs = [StoredMessage(*r) for r in src.execute(
                    "SELECT id, role, COALESCE(content_text, ''), created_at FROM messages "
                    "WHERE conversation_id=? ORDER BY sequence_order", (sid,)).fetchall()]
                s = DbCopySession(sid, label, str(path), title or "", ca, ua, msgs)
                stats["session_copies_read"] += 1
                prev = out.get(sid)
                if prev is None:
                    out[sid] = s
                    continue
                if prev.content_key() == s.content_key():
                    stats["identical_copies_dropped"] += 1
                    continue
                if s.redacted != prev.redacted:
                    stats["conflicts_resolved_redacted"] += 1
                    if s.redacted:
                        out[sid] = s
                else:
                    stats["conflicts_resolved_larger"] += 1
                    if s.size > prev.size:
                        out[sid] = s
        finally:
            src.close()
    stats["sessions"] = len(out)
    return out, stats


# =========================================================================== building turns

@dataclass
class DbCopyContext:
    history: dict = field(default_factory=dict)          # sid -> [prompt entries]
    history_keys: set = field(default_factory=set)       # opening of every history prompt
    repeats: collections.Counter = field(default_factory=collections.Counter)
    raw_uuid_owner: dict = field(default_factory=dict)   # record uuid -> raw conversation id
    templates: V.TemplateIndex | None = None


def _history_key(text: str) -> str:
    return V.norm_text(text)[:60]


def split_tool_results(text: str):
    """-> (remaining text, number of ``[tool result]`` lines). The old importer joined a
    record's blocks with newlines, a tool result block as one ``[tool result]`` line."""
    lines = (text or "").split("\n")
    n = sum(1 for ln in lines if ln.strip() == V.TOOL_RESULT_PLACEHOLDER)
    if not n:
        return text, 0
    return "\n".join(ln for ln in lines if ln.strip() != V.TOOL_RESULT_PLACEHOLDER), n


def is_tool_call_only(text: str) -> bool:
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    return bool(lines) and all(_TOOL_CALL_LINE_RE.match(ln) for ln in lines)


def build_db_copy_context(sessions, history, config: ImportConfig, raw_uuid_owner=None):
    ctx = DbCopyContext(raw_uuid_owner=raw_uuid_owner or {})
    for sid, entries in history.items():
        prompts = [e for e in entries if HA.is_prompt_entry(e)]
        ctx.history[sid] = prompts
        for e in prompts:
            pieces = HA.typed_pieces(e.get("display") or "")
            if pieces:
                ctx.history_keys.add(pieces[0][:60])
    # Repeats are counted after cross-database dedup, so a session held by two databases
    # does not make every one of its prompts a repeat.
    for s in sessions.values():
        for m in s.messages:
            if m.role != "user":
                continue
            t = V.strip_wrappers(split_tool_results(m.text)[0])
            if len(t.split()) >= REPEAT_MIN_WORDS:
                ctx.repeats[V.norm_hash(t)] += 1
    if config.harness_template_roots:
        ctx.templates = V.TemplateIndex(config.harness_template_roots,
                                        exclude_dirs=config.harness_template_exclude_dirs)
    return ctx


def _shingles(text: str, k: int = 3) -> frozenset:
    w = re.findall(r"[a-z0-9_]+", text.lower())
    return frozenset(tuple(w[i:i + k]) for i in range(max(1, len(w) - k + 1)))


def _calls_scheduler(text: str) -> bool:
    return any(f"[tool: {t}]" in text for t in SCHEDULER_TOOLS)


def loop_prompt_indices(msgs, corroborated) -> dict:
    """message index -> detector, for stored user turns that are loop or scheduled prompts.

    ``corroborated``: message indices a history prompt corroborates; never marked. A turn
    comes after a wakeup when an assistant message called a scheduler tool since the previous
    user message with text (tool-result-only user messages do not count).
    """
    if not any(m.role == "assistant" and _calls_scheduler(m.text or "") for m in msgs):
        return {}
    cands = {}      # index -> (text, after_wakeup)
    woke = False
    for i, m in enumerate(msgs):
        if m.role == "assistant":
            woke = woke or _calls_scheduler(m.text or "")
            continue
        if m.role != "user":
            continue
        rest = split_tool_results(m.text or "")[0]
        if not rest.strip():
            continue
        t = V.strip_wrappers(rest)
        if (i not in corroborated and t and len(t.split()) >= REPEAT_MIN_WORDS
                and _classify_stored_user_text(rest) is None
                and not V.norm_text(t).startswith(HARNESS_OPENINGS)):
            cands[i] = (t, woke)
        woke = False
    out = {i: D_LOOP_MONITOR for i, (t, _) in cands.items() if LOOP_MONITOR_RE.search(t.strip())}
    idx = sorted(cands)
    sh = {i: _shingles(cands[i][0]) for i in idx}
    parent = {i: i for i in idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for pos, a in enumerate(idx):
        for b in idx[pos + 1:]:
            inter = len(sh[a] & sh[b])
            if inter and inter / len(sh[a] | sh[b]) >= LOOP_TEMPLATE_JACCARD:
                parent[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for i in idx:
        groups[find(i)].append(i)
    for g in groups.values():
        if len(g) >= 2 and sum(cands[i][1] for i in g) >= LOOP_TEMPLATE_MIN_WAKES:
            for i in g:
                out.setdefault(i, D_LOOP_TEMPLATE)
    return out


def _finish_ordinal(new_rows):
    if len(new_rows) == 1:
        new_rows[0].segment = None
    elif len(new_rows) > 1:
        for i, r in enumerate(new_rows):
            r.segment = i
    return new_rows


def build_db_copy_turns(sess: DbCopySession, ctx: DbCopyContext,
                        config: ImportConfig) -> TI.BuildResult:
    settings = config.voice_settings()
    template_scorer = ctx.templates.hits if ctx.templates else None
    msgs = sess.messages
    res = TI.BuildResult(rows=[], content_hash=sess.content_key(), title=sess.title)
    counts = res.counts

    # Align this session's history prompts to its stored user rows.
    entries = ctx.history.get(sess.sid, [])
    user_idx = [i for i, m in enumerate(msgs) if m.role == "user"]
    aligned, last = HA.settle(entries, HA.align(
        entries, [_alignable(split_tool_results(msgs[i].text)[0]) for i in user_idx]))
    match = {user_idx[k]: entries[j] for j, k in enumerate(aligned) if k is not None}
    counts["history_prompts"] += len(entries)
    counts["history_prompts_in_copy"] += len(match)
    # Where stored messages carry timestamps, only a history prompt typed after the last of
    # them confirms truncation. Without timestamps the count is positional (after the last
    # prompt the copy carries), which also counts prompts missing from inside the copy, so
    # it is named as such rather than as a confirmation.
    stored_last = max((m.created_at for m in msgs if m.created_at), default=None)
    if stored_last is not None:
        timed = sum(1 for e in entries
                    if (TI._ts(e.get("timestamp")) or 0) > stored_last + LATER_THAN_TRANSCRIPT_S)
        res.flags["truncated_at_first_import"] = (
            f"confirmed by timestamp: {timed} history prompts after the copy's last stored message"
            if timed else "by construction: stored timestamps show no later history prompt")
    elif last is None:
        res.flags["truncated_at_first_import"] = (
            "unverified: first-import copy; no history prompt aligned to it")
    else:
        later = len(entries) - 1 - last
        res.flags["truncated_at_first_import"] = (
            f"positional: {later} history prompts after the last one the copy carries" if later
            else "by construction: first-import copy; no history prompt after it")
    res.flags["provenance"] = f"{SOURCE_DB_COPY}:{sess.label}"

    stamps = [m.created_at for m in msgs if m.created_at]
    stamps += [TI._ts(e.get("timestamp")) for e in match.values() if e.get("timestamp")]
    hist_stamps = [TI._ts(e.get("timestamp")) for e in entries if e.get("timestamp")]
    res.created_at = sess.created_at or (min(stamps + hist_stamps) if stamps + hist_stamps else None)
    res.updated_at = sess.updated_at or (max(stamps) if stamps else res.created_at)

    corroborated_idx = {
        i for i in user_idx if i in match or _history_key(
            V.strip_wrappers(split_tool_results(msgs[i].text or "")[0])) in ctx.history_keys}
    loop_rows = loop_prompt_indices(msgs, corroborated_idx)

    ordinal = 0
    prior_assistant: list = []
    earlier = V.AssistantShingles()   # every assistant turn so far in the copy
    first_subject = None
    for i, m in enumerate(msgs):
        entry = match.get(i)
        ts = m.created_at or (TI._ts(entry.get("timestamp")) if entry else None)
        common = dict(source_record_id=m.id, created_at=ts,
                      duplicate_of=ctx.raw_uuid_owner.get(m.id))
        if common["duplicate_of"]:
            counts["rows_in_raw_transcript"] += 1
        text = m.text or ""
        if m.role != "user":
            if not text.strip():
                continue
            if m.role != "assistant":
                row = TurnRow(ordinal=ordinal, speaker="system", voice_class="harness_prompt",
                              text=text, detector=f"source:role={m.role}", **common)
            elif is_tool_call_only(text):
                row = TurnRow(ordinal=ordinal, speaker="assistant", voice_class="tool_result",
                              text=text, detector=D_TOOL_CALL_PLACEHOLDER, **common)
                counts["assistant_tool_call_only"] += 1
            else:
                row = TurnRow(ordinal=ordinal, speaker="assistant", voice_class="assistant",
                              text=text, detector="source:role=assistant", **common)
                prior_assistant.append(text)
                earlier.add(text)
            res.rows.append(row)
            ordinal += 1
            continue

        rest, n_tr = split_tool_results(text)
        new_rows = []
        if n_tr:
            new_rows.append(TurnRow(ordinal=ordinal, segment=0, speaker="subject",
                                    voice_class="tool_result",
                                    text="\n".join([V.TOOL_RESULT_PLACEHOLDER] * n_tr),
                                    detector=V.D_TOOL_RESULT_PLACEHOLDER, **common))
        if rest.strip():
            for blk in V.BLOCK_RE.finditer(rest):
                if any(c and c in blk.group(0) for c in config.canary_strings):
                    res.flags["injection_canary"] = "db_copy:wrapper_text"
            ctx_row = _classify_stored_user_text(rest)
            if ctx_row is not None:
                cls_name, det, t = ctx_row
                new_rows.append(TurnRow(ordinal=ordinal, speaker="subject", voice_class=cls_name,
                                        text=t, detector=det, **common))
            else:
                t = V.strip_wrappers(rest)
                if not t:
                    counts["dropped_wrapper_only"] += 1
                elif V.norm_text(t).startswith(HARNESS_OPENINGS):
                    new_rows.append(TurnRow(ordinal=ordinal, speaker="subject",
                                            voice_class="harness_prompt", text=t,
                                            detector=D_HARNESS_SIGNATURE, **common))
                elif len(t) <= 200 and V.SLASH_CMD_RE.match(t):
                    counts["dropped_slash_command"] += 1
                else:
                    corroborated = entry is not None or _history_key(t) in ctx.history_keys
                    if not corroborated and i in loop_rows:
                        new_rows.append(TurnRow(ordinal=ordinal, speaker="subject",
                                                voice_class="harness_prompt", text=t,
                                                detector=loop_rows[i], **common))
                        counts["loop_prompt"] += 1
                    elif (not corroborated and len(t.split()) >= REPEAT_MIN_WORDS
                            and ctx.repeats[V.norm_hash(t)] >= REPEAT_MIN_COUNT):
                        new_rows.append(TurnRow(ordinal=ordinal, speaker="subject",
                                                voice_class="harness_prompt", text=t,
                                                detector=D_REPEATED_UNHISTORIED, **common))
                    else:
                        suffix = CORROBORATED if corroborated else ""
                        spans = HA.paste_spans(entry.get("display") or "", t) if entry else []
                        if spans:
                            counts["history_paste_located"] += 1
                        cls = V.classify_subject_text(
                            t, "\n".join(prior_assistant), settings, own_basis=B_DB_ROLE + suffix,
                            template_scorer=template_scorer, forced_paste_spans=spans,
                            earlier_assistant=earlier)
                        for s in cls.segments:
                            if s.basis == V.B_DICTATION:
                                s.basis = V.B_DICTATION + suffix
                        new_rows.extend(TI.subject_rows(ordinal, t, cls, **common))
                        counts["subject_corroborated" if corroborated else "subject_uncorroborated"] += 1
                        prior_assistant = []
                        first_subject = first_subject or t
        if new_rows:
            res.rows.extend(_finish_ordinal(new_rows))
            ordinal += 1
    if not res.title and first_subject:
        res.title = first_subject.strip()[:80]
    return res


def _alignable(text: str) -> str:
    """Text a history prompt may align to. A compaction summary quotes earlier prompts
    and a relayed message is another agent's; a prompt found only there is not carried
    by the copy as a turn, so neither is offered to the aligner."""
    if _classify_stored_user_text(text) is not None:
        return ""
    return "" if V.norm_text(V.strip_wrappers(text)).startswith(HARNESS_OPENINGS) else text


def _classify_stored_user_text(text):
    """-> (voice_class, detector, text) for context-only stored text, else None."""
    if V.COMPACTION_TEXT_RE.match(text):
        return ("compaction_summary", V.D_COMPACT_TEXT, text)
    if V.CROSS_AGENT_RE.search(text):
        return ("harness_prompt", V.D_CROSS_AGENT, text)
    return None


# =========================================================================== history side

def _ordinal_texts(rows, skip_classes=("tool_result",), placeholder_for_tag=False):
    """ordinal -> reconstructed turn text from stored rows (segments rejoined)."""
    by = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: (r.ordinal, -1 if r.segment is None else r.segment)):
        if r.voice_class in skip_classes or r.speaker != "subject":
            continue
        part = r.text
        if placeholder_for_tag and r.voice_class == "pasted" and r.detector == V.D_PASTE_TAG:
            part = "[Pasted text #0]"
        by.setdefault(r.ordinal, []).append(part)
    return collections.OrderedDict((o, "\n".join(p)) for o, p in by.items())


def mark_history_rows(conn, session_id: str, history_rows) -> collections.Counter:
    """Mark history rows whose prompt a DB copy of the same session carries.

    ``history_rows``: the TurnRows of ``history_<session_id>`` (in memory or stored).
    Sets ``duplicate_of = dbcopy_<session_id>`` on every row of a matched prompt that is
    not already a duplicate. Returns counts: ``in_copy``, ``after_copy_end`` (kept),
    ``unaligned_within_copy`` (kept; the aligner's misses and prompts the copy lacks)
    and ``paste_only`` (no typed text to align; kept, never citable).
    """
    stats = collections.Counter()
    conv = DB_COPY_PREFIX + session_id
    copy_rows = _rows_from_db(conn, conv)
    if not copy_rows:
        return stats
    copy_texts = list(_ordinal_texts(
        copy_rows, skip_classes=("tool_result", "compaction_summary", "harness_prompt")).values())
    hist = _ordinal_texts(history_rows, skip_classes=(), placeholder_for_tag=True)
    ords = list(hist)
    entries = [{"display": hist[o]} for o in ords]
    aligned, last = HA.settle(entries, HA.align(entries, copy_texts))
    last = -1 if last is None else last
    matched = set()
    for j, (o, k) in enumerate(zip(ords, aligned)):
        if k is not None:
            matched.add(o)
            stats["in_copy"] += 1
        elif not HA.typed_pieces(entries[j]["display"]):
            stats["paste_only"] += 1
        elif j > last:
            stats["after_copy_end"] += 1
        else:
            stats["unaligned_within_copy"] += 1
    for r in history_rows:
        if r.ordinal in matched and not r.duplicate_of:
            r.duplicate_of = conv
    return stats


def backfill_history(conn, session_id: str) -> collections.Counter:
    """Apply ``mark_history_rows`` to an already-stored history conversation, so a copy
    imported after the history marks it just as one imported before would."""
    hconv = HISTORY_PREFIX + session_id
    rows = _rows_from_db(conn, hconv)
    if not rows:
        return collections.Counter()
    before = {(r.ordinal, r.segment): r.duplicate_of for r in rows}
    stats = mark_history_rows(conn, session_id, rows)
    changed = False
    for r in rows:
        if before[(r.ordinal, r.segment)] != r.duplicate_of:
            conn.execute("UPDATE turns SET duplicate_of=? WHERE turn_id=?",
                         (r.duplicate_of, r.turn_id(hconv)))
            changed = True
    if changed:
        _rewrite_messages(conn, hconv)
    return stats


def entries_after_transcript(conn, session_id: str, entries) -> list:
    """History entries typed after a raw transcript of this session ends.

    A transcript copied before its session ended (a recovered copy) lacks the prompts that
    came later; history still has them. Returns the entries more than
    ``LATER_THAN_TRANSCRIPT_S`` after the transcript's last record, or [] when there is no
    transcript end to compare with.
    """
    row = conn.execute("SELECT updated_at FROM conversations WHERE id=? AND source='claude_code'",
                       (session_id,)).fetchone()
    if not row or row[0] is None:
        return []
    end = float(row[0]) + LATER_THAN_TRANSCRIPT_S
    return [e for e in entries if (TI._ts(e.get("timestamp")) or 0) > end]


# =========================================================================== importers

def import_db_copies(conn, db_paths, history_paths=()):
    """Import Claude Code sessions stored as rows in old corpus databases. Read-only on the
    source databases. Import raw transcripts first: a raw transcript of the same session
    wins, and a stored row that a raw transcript already holds is marked its duplicate."""
    print("\n=== Importing Claude Code database copies ===")
    config = load_import_config()
    ensure_turn_tables(conn)
    sessions, stats = load_db_copy_sessions(db_paths)
    history = TI.load_history_sessions(history_paths) if history_paths else {}
    raw_convs = {r[0] for r in conn.execute("SELECT id FROM conversations WHERE source='claude_code'")}
    selected = {}
    for sid, s in sessions.items():
        if sid in raw_convs:
            stats["raw_transcript_wins"] += 1
            continue
        selected[sid] = s
    wanted = {m.id for s in selected.values() for m in s.messages}
    raw_owner = {}
    for rid, cid in conn.execute("SELECT source_record_id, conversation_id FROM turns WHERE "
                                 "source='claude_code' AND source_record_id IS NOT NULL AND "
                                 "duplicate_of IS NULL"):
        if rid in wanted:
            raw_owner[rid] = cid
    ctx = build_db_copy_context(selected, history, config, raw_owner)
    detail = collections.Counter()
    for sid in sorted(selected):
        s = selected[sid]
        conv = DB_COPY_PREFIX + sid
        reason = (config.excluded_reason(conversation_id=conv, source=SOURCE_DB_COPY, path=s.path)
                  or config.excluded_reason(conversation_id=sid))
        if reason:
            record_exclusion(conn, conv, SOURCE_DB_COPY, reason)
            stats["excluded"] += 1
            continue
        res = build_db_copy_turns(s, ctx, config)
        detail.update(res.counts)
        if not res.rows:
            stats["empty"] += 1
            continue
        status = write_conversation(
            conn, conversation_id=conv, source=SOURCE_DB_COPY, rows=res.rows,
            content_hash=res.content_hash, title=res.title, created_at=res.created_at,
            updated_at=res.updated_at, source_path=s.path, allowlist=config.paste_allowlist,
            own_writing=config.own_writing_rule())
        if status != "unchanged":
            for flag, d in res.flags.items():
                set_flag(conn, conv, flag, d)
        stats[f"status_{status}"] += 1
        for k, v in backfill_history(conn, sid).items():
            stats[f"history_backfill_{k}"] += v
    conn.commit()
    stats.update({f"rows_{k}": v for k, v in detail.items()})
    print(f"  Results: {dict(sorted(stats.items()))}")
    return stats


def find_desktop_agent_sessions(root):
    """-> [(session jsonl path, metadata)] under a Desktop local-agent-mode directory.

    Each session is ``local_<id>.json`` (metadata) beside ``local_<id>/``, whose
    ``.claude/projects/*/<cli session id>.jsonl`` is the transcript. Only ``title`` and
    ``createdAt`` are taken from the metadata.
    """
    out = []
    for meta_path in sorted(Path(root).rglob("local_*.json")):
        d = meta_path.with_suffix("")
        proj = d / ".claude" / "projects"
        if not proj.is_dir():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        keep = {"title": meta.get("title") if isinstance(meta.get("title"), str) else None,
                "created_at": TI._ts(meta.get("createdAt"))}
        for f in sorted(proj.rglob("*.jsonl")):
            out.append((f, keep))
    return out


def import_desktop_agent(conn, root):
    """Import Claude Desktop local-agent-mode sessions through the Claude Code builder."""
    print("\n=== Importing Claude Desktop local-agent-mode sessions ===")
    config = load_import_config()
    ensure_turn_tables(conn)
    found = find_desktop_agent_sessions(root)
    ctx = TI.build_claude_code_context([f for f, _ in found], config)
    stats = collections.Counter()
    for f, meta in found:
        sid = f.stem
        reason = config.excluded_reason(conversation_id=sid, source=SOURCE_DESKTOP, path=f)
        if reason:
            record_exclusion(conn, sid, SOURCE_DESKTOP, reason)
            stats["excluded"] += 1
            continue
        res = TI.build_claude_code_turns(f, ctx, config)
        stats.update({f"rows_{k}": v for k, v in res.counts.items()})
        if not res.rows:
            stats["empty"] += 1
            continue
        status = write_conversation(
            conn, conversation_id=sid, source=SOURCE_DESKTOP, rows=res.rows,
            content_hash=res.content_hash, title=meta.get("title") or res.title,
            created_at=res.created_at or meta.get("created_at"), updated_at=res.updated_at,
            source_path=str(f), allowlist=config.paste_allowlist,
            own_writing=config.own_writing_rule())
        if status != "unchanged":
            for flag, d in res.flags.items():
                set_flag(conn, sid, flag, d)
        stats[f"status_{status}"] += 1
        stats["sessions"] += 1
    conn.commit()
    print(f"  Results: {dict(sorted(stats.items()))}")
    return stats
