"""Source importers that write the turn table (docs/core/TURN_CONTRACT.md, sections 1-2).

Each importer turns one source conversation into a list of ``TurnRow`` and hands it to
``turns.write_conversation``. Speaker always comes from the source's own role or speaker
field. ``voice_class`` comes from the deterministic detectors in ``baselayer.voice``.

Sources:

* Claude Code session JSONL (``build_claude_code_turns``)
* ChatGPT export (``build_chatgpt_turns``)
* Claude Code prompt history, ``history.jsonl`` (``build_history_turns``): subject prompts
  only, no assistant context
* Meeting transcripts in the ``HH:MM Speaker Name: text`` line format
  (``build_meeting_turns``): the configured subject label is ``own_dictated``, every other
  speaker ``other_person``
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from baselayer import voice as V
from baselayer.import_config import ImportConfig
from baselayer.turns import TurnRow


def _ts(value):
    """Timestamp as epoch seconds: int ms, float s, numeric string or ISO 8601."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
    value = float(value)
    return value / 1000.0 if value > 1e12 else value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def subject_rows(ordinal, text, cls: V.SubjectTurnClassification, **common) -> list:
    """One row for a turn with no paste; one row per segment otherwise."""
    segs = cls.segments
    if not segs:
        return []
    if not cls.has_paste and len(segs) == 1:
        s = segs[0]
        return [TurnRow(ordinal=ordinal, speaker="subject", voice_class=s.voice_class,
                        text=text, detector=s.detector, basis=s.basis, **common)]
    out = []
    for i, s in enumerate(segs):
        out.append(TurnRow(ordinal=ordinal, segment=i, speaker="subject",
                           voice_class=s.voice_class, text=text[s.start:s.end],
                           detector=s.detector, basis=s.basis, char_start=s.start,
                           char_end=s.end, **common))
    return out


# =========================================================================== Claude Code

@dataclass
class ClaudeCodeContext:
    """Corpus-level facts one record cannot know."""
    human_hashes: set = field(default_factory=set)   # normalized texts a human typed/queued
    owner: dict = field(default_factory=dict)        # record uuid -> owning file path
    templates: V.TemplateIndex | None = None


def _content_text(content):
    """-> (user_text, n_tool_result_blocks). Text blocks joined; tool results counted."""
    if isinstance(content, str):
        return content, 0
    if isinstance(content, list):
        parts, n_tr = [], 0
        for b in content:
            if isinstance(b, dict):
                t = b.get("type")
                if t == "text":
                    parts.append(b.get("text", ""))
                elif t == "tool_result":
                    n_tr += 1
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts), n_tr
    return (str(content) if content else ""), 0


def _assistant_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict):
            if b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                parts.append(f"[tool: {b.get('name', 'unknown')}]")
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts)


def _human_queued(obj):
    a = obj.get("attachment") or {}
    return (a.get("type") == "queued_command" and a.get("commandMode", "prompt") == "prompt"
            and (a.get("origin") or {}).get("kind") == "human" and not obj.get("isSidechain")
            and isinstance(a.get("prompt"), str))


def _originless_queued(obj):
    """A queued prompt written with no origin (an older client): same record shape as a
    human queued prompt, but nothing says who queued it."""
    a = obj.get("attachment") or {}
    return (a.get("type") == "queued_command" and a.get("commandMode", "prompt") == "prompt"
            and not (a.get("origin") or {}).get("kind") and not obj.get("isSidechain")
            and isinstance(a.get("prompt"), str))


def build_claude_code_context(files, config: ImportConfig) -> ClaudeCodeContext:
    ctx = ClaudeCodeContext()
    if config.harness_template_roots:
        ctx.templates = V.TemplateIndex(config.harness_template_roots,
                                        exclude_dirs=config.harness_template_exclude_dirs)
    candidates = collections.defaultdict(list)
    for p in files:
        p = Path(p)
        try:
            fh = open(p, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"uuid"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = o.get("type")
                if t not in ("user", "assistant", "attachment"):
                    continue
                u = o.get("uuid")
                if u:
                    candidates[u].append((o.get("sessionId") == p.stem, str(p)))
                if t == "user" and o.get("promptSource") in ("typed", "queued") \
                        and (o.get("origin") or {}).get("kind") == "human":
                    text, _ = _content_text((o.get("message") or {}).get("content"))
                    ctx.human_hashes.add(V.norm_hash(V.strip_wrappers(text)))
                elif t == "attachment" and (_human_queued(o) or (
                        config.include_originless_queued and _originless_queued(o))):
                    ctx.human_hashes.add(V.norm_hash(o["attachment"]["prompt"]))
    for u, cands in candidates.items():
        # Owner: the file whose name is the record's own session id; otherwise the
        # lexically first path. Deterministic regardless of import order.
        cands = sorted(set(cands), key=lambda c: (not c[0], c[1]))
        ctx.owner[u] = cands[0][1]
    return ctx


@dataclass
class BuildResult:
    rows: list
    title: str = ""
    created_at: float | None = None
    updated_at: float | None = None
    content_hash: str = ""
    flags: dict = field(default_factory=dict)
    counts: collections.Counter = field(default_factory=collections.Counter)


def build_claude_code_turns(path, ctx: ClaudeCodeContext, config: ImportConfig) -> BuildResult:
    path = Path(path)
    raw = path.read_bytes()
    settings = config.voice_settings()
    res = BuildResult(rows=[], content_hash=_sha(raw))
    counts = res.counts
    rows = res.rows
    ordinal = 0
    seen_uuids = set()
    queued_seen = set()
    prior_assistant: list = []
    earlier = V.AssistantShingles()   # every assistant turn so far in the file
    first_subject = None
    stamps = []
    template_scorer = ctx.templates.hits if ctx.templates else None

    def add(new_rows):
        nonlocal ordinal
        if new_rows:
            rows.extend(new_rows)
            ordinal += 1

    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            counts["bad_json"] += 1
            continue
        t = o.get("type")
        if t == "attachment":
            a = o.get("attachment") or {}
            if a.get("type") == "hook_additional_context":
                blob = json.dumps(a, ensure_ascii=False)
                for c in config.canary_strings:
                    if c in blob:
                        res.flags["injection_canary"] = "hook_additional_context"
            if a.get("type") != "queued_command":
                continue
            if not _human_queued(o):
                if _originless_queued(o):
                    counts["queued_prompt_origin_missing"] += 1
                    if not config.include_originless_queued:
                        counts["queued_not_human_prompt"] += 1
                        continue
                else:
                    counts["queued_not_human_prompt"] += 1
                    continue
        elif t not in ("user", "assistant"):
            continue

        u = o.get("uuid")
        if u and u in seen_uuids:
            counts["repeat_uuid_in_file"] += 1
            continue
        if u:
            seen_uuids.add(u)
        if o.get("isSidechain"):
            counts["dropped_isSidechain"] += 1
            continue
        if o.get("userType") not in (None, "external"):
            counts["dropped_userType"] += 1
            continue
        owner = ctx.owner.get(u) if u else None
        dup = None
        if owner and owner != str(path):
            dup = Path(owner).stem
        ts = _ts(o.get("timestamp"))
        if ts is not None:
            stamps.append(ts)
        common = dict(source_record_id=u, created_at=ts, duplicate_of=dup)

        # -- queued prompt: the subject's words, recovered ------------------------
        if t == "attachment":
            prompt = o["attachment"]["prompt"]
            text = V.strip_wrappers(prompt)
            if not text:
                continue
            key = V.norm_hash(text)
            if key in queued_seen:
                counts["queued_repeat_text"] += 1
                continue
            queued_seen.add(key)
            basis = V.B_QUEUED if _human_queued(o) else V.B_QUEUED_NO_ORIGIN
            cls = V.classify_subject_text(text, "\n".join(prior_assistant), settings,
                                          own_basis=basis, template_scorer=template_scorer,
                                          earlier_assistant=earlier)
            add(subject_rows(ordinal, text, cls, **common))
            counts["queued_recovered" if basis == V.B_QUEUED else "queued_no_origin_recovered"] += 1
            prior_assistant = []
            first_subject = first_subject or text
            continue

        msg = o.get("message") or {}
        if t == "assistant":
            text = _assistant_text(msg.get("content"))
            if not text.strip():
                continue
            add([TurnRow(ordinal=ordinal, speaker="assistant", voice_class="assistant",
                         text=text, detector="source:role=assistant", **common)])
            prior_assistant.append(text)
            earlier.add(text)
            continue

        # -- user-role record ------------------------------------------------------
        raw_text, n_tool_results = _content_text(msg.get("content"))
        new_rows = []
        if n_tool_results:
            new_rows.append(TurnRow(ordinal=ordinal, segment=0, speaker="subject",
                                    voice_class="tool_result", text=V.TOOL_RESULT_PLACEHOLDER,
                                    detector=V.D_TOOL_RESULT_BLOCK, **common))
        rec = _classify_user_record(o, raw_text, ctx, config)
        if rec is None:
            counts["dropped_wrapper_or_command"] += 1 if raw_text.strip() else 0
        elif rec[0] == "context":
            _, cls_name, det, text = rec
            new_rows.append(TurnRow(ordinal=ordinal, speaker="subject", voice_class=cls_name,
                                    text=text, detector=det, **common))
        else:
            text = rec[1]
            cls = V.classify_subject_text(text, "\n".join(prior_assistant), settings,
                                          template_scorer=template_scorer,
                                          earlier_assistant=earlier)
            new_rows.extend(subject_rows(ordinal, text, cls, **common))
            prior_assistant = []
            first_subject = first_subject or text
        if len(new_rows) == 1:
            new_rows[0].segment = None
        elif len(new_rows) > 1:
            # a tool_result block plus text: renumber as segments of one turn
            flat = []
            for r in new_rows:
                if r.segment is None:
                    r.segment = 0
                flat.append(r)
            for i, r in enumerate(flat):
                r.segment = i
            new_rows = flat
        add(new_rows)

    res.title = (first_subject or "Claude Code Session").strip()[:100]
    if len(res.title) > 80:
        res.title = res.title[:77] + "..."
    if stamps:
        res.created_at, res.updated_at = min(stamps), max(stamps)
    return res


def build_originless_queued_turns(path, ctx: ClaudeCodeContext, config: ImportConfig) -> BuildResult:
    """The originless queued prompts of one session, as rows for a conversation of their own.

    Each prompt is classified exactly where it sits in the session, with the assistant text
    before it, so quote-back and paste detection work as in ``build_claude_code_turns`` (it
    runs that builder with the switch on and keeps only these records). Ordinals are then
    renumbered from 0. The content hash covers the kept rows only, so a session that grows
    by anything else re-imports as ``unchanged``.
    """
    path = Path(path)
    ids = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"queued_command"' not in line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "attachment" and _originless_queued(o) and o.get("uuid"):
                ids.add(o["uuid"])
    res = BuildResult(rows=[])
    if not ids:
        return res
    full = build_claude_code_turns(path, ctx, dataclasses.replace(config, include_originless_queued=True))
    renumber = {}
    for r in full.rows:
        if r.source_record_id not in ids:
            continue
        r.ordinal = renumber.setdefault(r.ordinal, len(renumber))
        res.rows.append(r)
    res.counts["queued_no_origin_recovered"] = len(renumber)
    res.flags = dict(full.flags)
    res.content_hash = _sha(json.dumps(
        [(r.source_record_id, r.segment, r.voice_class, r.text) for r in res.rows],
        ensure_ascii=False).encode("utf-8"))
    stamps = [r.created_at for r in res.rows if r.created_at is not None]
    if stamps:
        res.created_at, res.updated_at = min(stamps), max(stamps)
    first = next((r.text for r in res.rows if r.citable), None) or "Queued prompts"
    res.title = first.strip()[:80]
    return res


def _classify_user_record(o, raw_text, ctx: ClaudeCodeContext, config: ImportConfig):
    """-> None (drop) | ("context", voice_class, detector, text) | ("subject", text)."""
    if not raw_text.strip():
        return None
    if o.get("isCompactSummary"):
        return ("context", "compaction_summary", V.D_COMPACT_FLAG, raw_text)
    if V.COMPACTION_TEXT_RE.match(raw_text):
        return ("context", "compaction_summary", V.D_COMPACT_TEXT, raw_text)
    if V.is_tool_result_placeholder(raw_text):
        return ("context", "tool_result", V.D_TOOL_RESULT_PLACEHOLDER, raw_text)
    if o.get("isMeta"):
        return ("context", "harness_prompt", V.D_IS_META, raw_text)
    origin = (o.get("origin") or {}).get("kind")
    ps = o.get("promptSource")
    if ps == "system" or origin in ("task-notification", "peer", "coordinator") \
            or o.get("turnOrigin") in ("task_notification", "peer"):
        return ("context", "harness_prompt", V.D_SYSTEM_ORIGIN, raw_text)
    if V.CROSS_AGENT_RE.search(raw_text):
        return ("context", "harness_prompt", V.D_CROSS_AGENT, raw_text)
    text = V.strip_wrappers(raw_text)
    if not text:
        return None
    if len(text) <= 200 and V.SLASH_CMD_RE.match(text):
        return None
    human = ps in ("typed", "queued") and origin == "human"
    det = None
    if ps == "sdk":
        det = V.D_SDK_PROMPT
    elif o.get("entrypoint") == "sdk-cli" and not human:
        det = V.D_SDK_CLI_NO_HUMAN
    elif not human and config.is_harness_cwd(o.get("cwd")):
        det = V.D_HARNESS_CWD
    if det:
        # The source rule is exact and stays the detector; the one refinement recorded is
        # that the prompt replays text the subject typed somewhere, so the replay is not
        # mistaken for a second utterance.
        if V.norm_hash(text) in ctx.human_hashes:
            det = V.D_HARNESS_REPLAY
        return ("context", "harness_prompt", det, text)
    return ("subject", text)


# =========================================================================== ChatGPT

def _chatgpt_text(content: dict):
    """-> (text, is_audio)."""
    ctype = (content or {}).get("content_type")
    parts = (content or {}).get("parts") or []
    if ctype == "multimodal_text":
        out, audio = [], False
        for p in parts:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict):
                if p.get("content_type") == "audio_transcription":
                    out.append(p.get("text", ""))
                    audio = True
        return "\n".join(x for x in out if x), audio
    if ctype == "code":
        return content.get("text", ""), False
    return "\n".join(str(p) for p in parts if isinstance(p, str)), False


def build_chatgpt_turns(conv: dict, config: ImportConfig) -> BuildResult:
    settings = config.voice_settings()
    mapping = conv.get("mapping") or {}
    res = BuildResult(rows=[], content_hash=_sha(json.dumps(conv, sort_keys=True).encode("utf-8")))
    res.title = conv.get("title") or ""
    res.created_at, res.updated_at = conv.get("create_time"), conv.get("update_time")
    nodes = []
    for node_id, node in mapping.items():
        m = node.get("message")
        if not m:
            continue
        if (m.get("metadata") or {}).get("is_visually_hidden_from_conversation"):
            res.counts["hidden"] += 1
            continue
        text, audio = _chatgpt_text(m.get("content") or {})
        if not text.strip():
            continue
        role = (m.get("author") or {}).get("role", "unknown")
        nodes.append((m.get("create_time") or 0.0, node_id, m, text, audio, role))
    # Append-stable order: a regenerated or edited branch has a later create_time, so it
    # lands after every existing turn instead of shifting their ordinals.
    nodes.sort(key=lambda x: (x[0], x[1]))
    by_id = {n[1]: n for n in nodes}

    def prior_assistant(node_id):
        texts, cur = [], (mapping.get(node_id) or {}).get("parent")
        while cur is not None:
            n = by_id.get(cur)
            if n is not None:
                if n[5] == "user":
                    break
                if n[5] == "assistant":
                    texts.append(n[3])
            cur = (mapping.get(cur) or {}).get("parent")
        return "\n".join(reversed(texts))

    def earlier_assistant(node_id):
        """Every assistant turn on this node's branch, back to the root; built only when
        the classifier asks for it (a long turn)."""
        def build():
            texts, cur = [], (mapping.get(node_id) or {}).get("parent")
            while cur is not None:
                n = by_id.get(cur)
                if n is not None and n[5] == "assistant":
                    texts.append(n[3])
                cur = (mapping.get(cur) or {}).get("parent")
            return V.AssistantShingles(texts)
        return build

    for ordinal, (ct, node_id, m, text, audio, role) in enumerate(nodes):
        common = dict(source_record_id=node_id, created_at=ct or None)
        if role == "user":
            if audio:
                cls = V.classify_subject_text(text, prior_assistant(node_id), settings,
                                              own_class="own_dictated", own_basis=V.B_AUDIO,
                                              detect_dictation=False)
            else:
                cls = V.classify_subject_text(text, prior_assistant(node_id), settings,
                                              earlier_assistant=earlier_assistant(node_id))
            res.rows.extend(subject_rows(ordinal, text, cls, **common))
        elif role == "assistant":
            res.rows.append(TurnRow(ordinal=ordinal, speaker="assistant", voice_class="assistant",
                                    text=text, detector="source:role=assistant", **common))
        elif role == "tool":
            res.rows.append(TurnRow(ordinal=ordinal, speaker="system", voice_class="tool_result",
                                    text=text, detector=V.D_CHATGPT_TOOL, **common))
        else:
            res.rows.append(TurnRow(ordinal=ordinal, speaker="system", voice_class="harness_prompt",
                                    text=text, detector=V.D_CHATGPT_SYSTEM, **common))
    return res


# =========================================================================== history.jsonl

def load_history_sessions(paths) -> dict:
    """sessionId -> [entry], unioned across copies on (timestamp, display), time-ordered."""
    sessions = collections.defaultdict(dict)
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = o.get("sessionId")
                disp = o.get("display")
                if not sid or not isinstance(disp, str):
                    continue
                sessions[sid].setdefault((o.get("timestamp"), disp), o)
    return {sid: [d[k] for k in sorted(d, key=lambda k: (k[0] or 0, k[1]))]
            for sid, d in sessions.items()}


def _expand_pastes(entry):
    """Replace ``[Pasted text #n ...]`` placeholders with inline pasted content when the
    history entry carries it. -> (text, forced paste spans)."""
    display = entry.get("display") or ""
    pasted = entry.get("pastedContents") or {}
    out, spans, pos = [], [], 0
    for m in V.PASTE_TAG_RE.finditer(display):
        out.append(display[pos:m.start()])
        num = re.search(r"#(\d+)", m.group(0)).group(1)
        item = pasted.get(num) or pasted.get(int(num)) if isinstance(pasted, dict) else None
        body = item.get("content") if isinstance(item, dict) and isinstance(item.get("content"), str) else m.group(0)
        start = sum(len(x) for x in out)
        out.append(body)
        spans.append((start, start + len(body)))
        pos = m.end()
    out.append(display[pos:])
    return "".join(out), spans


def build_history_turns(session_id, entries, config: ImportConfig) -> BuildResult:
    settings = config.voice_settings()
    res = BuildResult(rows=[], content_hash=_sha(json.dumps(entries, sort_keys=True,
                                                            ensure_ascii=False).encode("utf-8")))
    stamps = []
    ordinal = 0
    for e in entries:
        disp = (e.get("display") or "").strip()
        if not disp:
            continue
        if disp.startswith("/") or disp.startswith("!"):
            res.counts["dropped_command_entry"] += 1
            continue
        text, spans = _expand_pastes(e)
        ts = _ts(e.get("timestamp"))
        if ts is not None:
            stamps.append(ts)
        cls = V.classify_subject_text(text, "", settings, forced_paste_spans=spans)
        rows = subject_rows(ordinal, text, cls, source_record_id=None, created_at=ts)
        if rows:
            res.rows.extend(rows)
            ordinal += 1
            if not res.title:
                res.title = disp[:80]
    if stamps:
        res.created_at, res.updated_at = min(stamps), max(stamps)
    return res


# =========================================================================== meetings

MEETING_LINE_RE = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+([^:\n]{1,60}?):\s(.*)$")
MEETING_DATE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4}),\s*(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)", re.I)


def looks_like_meeting(text: str) -> bool:
    return sum(1 for ln in text.splitlines() if MEETING_LINE_RE.match(ln)) >= 3


def build_meeting_turns(text: str, config: ImportConfig) -> BuildResult:
    """Only ``HH:MM Name: text`` lines become turns; headers and notes sections do not.
    A non-blank line directly after a turn line continues that turn."""
    res = BuildResult(rows=[], content_hash=_sha(text.encode("utf-8")))
    lines = text.splitlines()
    for ln in lines[:15]:
        if ln.lstrip().startswith("# ") and not res.title:
            res.title = ln.lstrip()[2:].strip()
        m = MEETING_DATE_RE.search(ln)
        if m and res.created_at is None:
            for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p"):
                try:
                    res.created_at = datetime.strptime(f"{m.group(1)} {m.group(2).upper()}", fmt).timestamp()
                    break
                except ValueError:
                    continue
    ordinal = 0
    last = None
    for ln in lines:
        m = MEETING_LINE_RE.match(ln)
        if m:
            label, body = m.group(2).strip(), m.group(3)
            if config.is_meeting_subject(label):
                last = TurnRow(ordinal=ordinal, speaker="subject", voice_class="own_dictated",
                               text=body, basis=V.B_MEETING_LABEL, source_record_id=None)
                res.counts["subject_lines"] += 1
            else:
                last = TurnRow(ordinal=ordinal, speaker="other", voice_class="other_person",
                               text=body, detector="config:meeting_other_label",
                               source_record_id=None)
                res.counts["other_lines"] += 1
            res.rows.append(last)
            ordinal += 1
        elif last is not None and ln.strip() and not ln.lstrip().startswith("#"):
            last.text = last.text + "\n" + ln.strip()
            res.counts["continuation_lines"] += 1
        else:
            if ln.strip():
                res.counts["non_turn_lines"] += 1
            last = None
    res.updated_at = res.created_at
    return res


# =========================================================================== Claude.ai web

def build_message_list_turns(messages, config: ImportConfig, content_hash: str) -> BuildResult:
    """Turns for a flat, ordered message list (Claude.ai web export).

    ``messages``: dicts with ``role`` (``user``/``human``/``assistant``/other), ``text``,
    ``id`` and ``created_at``. Subject turns get paste detection against the assistant
    text since the previous subject turn.
    """
    settings = config.voice_settings()
    res = BuildResult(rows=[], content_hash=content_hash)
    prior = []
    earlier = V.AssistantShingles()
    ordinal = 0
    for m in messages:
        text, role = m.get("text") or "", m.get("role")
        if not text.strip():
            continue
        common = dict(source_record_id=m.get("id"), created_at=m.get("created_at"))
        if role in ("user", "human"):
            cls = V.classify_subject_text(text, "\n".join(prior), settings,
                                          earlier_assistant=earlier)
            res.rows.extend(subject_rows(ordinal, text, cls, **common))
            prior = []
        elif role == "assistant":
            res.rows.append(TurnRow(ordinal=ordinal, speaker="assistant", voice_class="assistant",
                                    text=text, detector="source:role=assistant", **common))
            prior.append(text)
            earlier.add(text)
        else:
            res.rows.append(TurnRow(ordinal=ordinal, speaker="system", voice_class="harness_prompt",
                                    text=text, detector=f"source:role={role}", **common))
        ordinal += 1
    return res
