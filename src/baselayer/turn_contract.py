"""
Turn contract, extraction side (docs/core/TURN_CONTRACT.md, version turn-contract/1).

This module is the pure half of turn-contract extraction: reading the turn table,
building turn-bounded chunks, rendering them for the model, and the §5 gate.
It makes no model calls and writes nothing. extract_facts.py and batch_extract.py
call it.

The rule it enforces: a fact need not be a quote (it may be an understanding
inferred from one passage or several turns), but every stored fact must be
GROUNDED in one or more verbatim spans from turns the subject wrote or spoke.
Other turns are shown to the model as context and can never be cited. The prompt asks for this; `gate_facts` enforces it, and it must run
OUTSIDE any exception handler (a handler that catches a gate failure and then
commits is how an unchecked fact reaches the database).

What the gate proves: every cited span exists in a turn the subject wrote or
spoke. What it does not prove: that the fact is a correct reading of those
spans; that is sampled by verification, inferred facts more heavily (§6).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# One definition of the version, shared with the importer (baselayer.voice) and
# verification, so the three halves cannot drift apart.
from baselayer.voice import TURN_CONTRACT_VERSION  # noqa: E402

# The turn table, written at import (contract §1, names binding per §4a):
# turn_id, conversation_id, ordinal, speaker, voice_class, text, detector,
# turn_contract_version. Every read goes through this constant and load_turns().
TURN_TABLE = "turns"

CITABLE_VOICE_CLASSES = frozenset({"own_typed", "own_dictated"})

REJECT_REASONS = ("no_grounding", "no_turn", "not_own_voice", "span_not_found", "span_length",
                  "self_object")


def span_bounds() -> tuple[int, int]:
    """(min words, max chars) for one evidence span: config, overridable per run
    by BASELAYER_TURN_SPAN_MIN_WORDS / BASELAYER_TURN_SPAN_MAX_CHARS. Read at call
    time so a run's record shows the values that gated it."""
    from baselayer.config import TURN_EVIDENCE_SPAN_MAX_CHARS, TURN_EVIDENCE_SPAN_MIN_WORDS
    lo = os.environ.get("BASELAYER_TURN_SPAN_MIN_WORDS")
    hi = os.environ.get("BASELAYER_TURN_SPAN_MAX_CHARS")
    return (int(lo) if lo else TURN_EVIDENCE_SPAN_MIN_WORDS,
            int(hi) if hi else TURN_EVIDENCE_SPAN_MAX_CHARS)

# Label shown to the model for each non-citable voice class. Anything not listed
# (including an unknown class) is rendered as unclassified and is not citable:
# the gate fails closed on classes it does not recognise.
_NONCITABLE_LABELS = {
    "assistant": "ASSISTANT",
    "other_person": "OTHER PERSON",
    "pasted": "PASTED MATERIAL, not the subject's words",
    "compaction_summary": "HARNESS SUMMARY, not the subject's words",
    "tool_result": "TOOL OUTPUT",
    "harness_prompt": "PROGRAMMATIC PROMPT, not the subject's words",
    "queued_command": "QUEUED COMMAND, not yet reclassified",
}


# ---------------------------------------------------------------------------
# Turns
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Turn:
    turn_id: str
    conversation_id: str
    speaker: str
    voice_class: str
    text: str
    ordinal: int | None = None           # from the table when present
    contract_version: str | None = None  # the turn row's turn_contract_version
    duplicate_of: str | None = None      # set by the importer on fork/resume copies

    @property
    def citable(self) -> bool:
        # A fork or resume copy repeats a turn its owner session already holds.
        # The owner's row is the citable one; the copy is context only, or the
        # same grounding would be extracted (and billed) once per copy.
        return self.voice_class in CITABLE_VOICE_CLASSES and not self.duplicate_of


def turn_sort_key(turn_id: str) -> tuple:
    """Order key for `<conversation_id>:<ordinal>` or `...:<ordinal>.<segment>`.

    Numeric, not lexical: as strings, `:10` sorts before `:2`. Raises ValueError
    on an id that does not carry a numeric ordinal, because a turn that cannot be
    placed in order cannot be given correct preceding context.
    """
    _, sep, tail = turn_id.rpartition(":")
    if not sep:
        raise ValueError(f"turn_id has no ':<ordinal>' suffix: {turn_id!r}")
    ordinal, _, segment = tail.partition(".")
    return (int(ordinal), int(segment) if segment else -1)


def turn_table_exists(conn) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TURN_TABLE,)
    ).fetchone()
    return row is not None


def turn_rows_exist(conn) -> bool:
    """True when the turn table exists AND holds at least one row.

    `init_database` creates the (empty) turn table in every database, so the
    table's existence says nothing about how a corpus was imported. Rows do:
    only the turn-contract importer writes them. Checks existence first so a
    database without the table is read, never altered."""
    if not turn_table_exists(conn):
        return False
    return conn.execute(f"SELECT 1 FROM {TURN_TABLE} LIMIT 1").fetchone() is not None


def _turn_order(t: "Turn") -> tuple:
    """Numeric order: the table's ordinal when present, else the ordinal parsed
    from the id; the segment always comes from the id (`:<ordinal>.<segment>`)."""
    parsed = turn_sort_key(t.turn_id)
    return (t.ordinal if t.ordinal is not None else parsed[0], parsed[1])


def load_turns(conn, conversation_id: str) -> list[Turn]:
    """All turns of one conversation, in numeric turn order."""
    have = {row[1] for row in conn.execute(f"PRAGMA table_info({TURN_TABLE})")}
    ordinal = "ordinal" if "ordinal" in have else "NULL"
    version = "turn_contract_version" if "turn_contract_version" in have else "NULL"
    dup = "duplicate_of" if "duplicate_of" in have else "NULL"
    rows = conn.execute(
        f"SELECT turn_id, conversation_id, speaker, voice_class, text, {ordinal}, {version}, "
        f"{dup} FROM {TURN_TABLE} WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchall()
    turns = [Turn(r[0], r[1], r[2] or "", r[3] or "", r[4] or "",
                  int(r[5]) if r[5] is not None else None, r[6], r[7]) for r in rows]
    turns.sort(key=_turn_order)
    return turns


def load_turn_texts(conn, turn_ids) -> dict[str, tuple[str, str]]:
    """turn_id -> (voice_class, text), for rebuilding a chunk from a manifest."""
    ids = list(dict.fromkeys(turn_ids))
    out = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        q = ",".join("?" * len(part))
        for r in conn.execute(
            f"SELECT turn_id, voice_class, text FROM {TURN_TABLE} WHERE turn_id IN ({q})", part
        ).fetchall():
            out[r[0]] = (r[1] or "", r[2] or "")
    return out


# ---------------------------------------------------------------------------
# Pieces: a whole turn, or one segment of an oversize turn
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Piece:
    turn: Turn
    start: int          # offsets into turn.text; the segment is turn.text[start:end]
    end: int
    part: int = 1       # 1-based segment number
    parts: int = 1

    @property
    def text(self) -> str:
        return self.turn.text[self.start:self.end]


def _split_points(text: str, max_chars: int) -> list[int]:
    """End offsets for contiguous segments of at most max_chars each.

    Prefers a paragraph break, then a line break, then a sentence end, then a
    space, and hard-cuts only when none exists in the window. Segments are
    contiguous and cover the whole text, so every segment is an exact slice and
    can be rebuilt later from (start, end).
    """
    ends, start, n = [], 0, len(text)
    while n - start > max_chars:
        window = text[start:start + max_chars]
        cut = -1
        for sep in ("\n\n", "\n", ". ", " "):
            k = window.rfind(sep)
            if k > max_chars // 4:
                cut = k + len(sep)
                break
        if cut <= 0:
            cut = max_chars
        start += cut
        ends.append(start)
    ends.append(n)
    return ends


def split_turn(turn: Turn, max_chars: int) -> list[Piece]:
    if len(turn.text) <= max_chars:
        return [Piece(turn, 0, len(turn.text))]
    ends = _split_points(turn.text, max_chars)
    pieces, start = [], 0
    for i, end in enumerate(ends):
        pieces.append(Piece(turn, start, end, i + 1, len(ends)))
        start = end
    return pieces


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    index: int                              # 1-based
    total: int
    body: list                              # Piece list, in order
    context: list                           # (label, text) list, oldest first
    alias_to_turn: dict                     # "S1" -> turn_id (citable body turns only)
    body_voice: dict                        # turn_id -> voice_class, every body turn
    citable_texts: dict                     # turn_id -> [segment text, ...] as shown
    rendered_body: str = ""
    rendered_context: str = ""

    @property
    def has_citable(self) -> bool:
        return bool(self.alias_to_turn)

    @property
    def citable_chars(self) -> int:
        """Characters of the subject's own words this chunk offers as citable."""
        return sum(len(t) for texts in self.citable_texts.values() for t in texts)

    def manifest(self) -> dict:
        """What the batch state file keeps about this chunk: ids and offsets,
        never turn text. The text is reloaded from the turn table at process
        time (the state file sits in data/database/ and must not carry a
        second copy of a person's words)."""
        return {
            "citable": [[p.turn.turn_id, p.start, p.end, alias]
                        for p in self.body if p.turn.citable
                        for alias in [self._alias_of(p.turn.turn_id)]],
            "body_voice": dict(self.body_voice),
        }

    def _alias_of(self, turn_id: str) -> str:
        for a, t in self.alias_to_turn.items():
            if t == turn_id:
                return a
        raise KeyError(turn_id)


def chunk_from_manifest(manifest: dict, texts: dict) -> Chunk:
    """Rebuild the gate-relevant parts of a chunk from its manifest.

    `texts` is load_turn_texts() output. A citable turn whose text is missing or
    whose voice_class changed since submit is dropped from the citable set, so
    a fact citing it is rejected rather than trusted.
    """
    alias_to_turn, citable_texts = {}, {}
    body_voice = dict(manifest.get("body_voice", {}))
    for turn_id, start, end, alias in manifest.get("citable", []):
        cur = texts.get(turn_id)
        if cur is None or cur[0] not in CITABLE_VOICE_CLASSES:
            body_voice[turn_id] = cur[0] if cur else "missing"
            continue
        alias_to_turn[alias] = turn_id
        citable_texts.setdefault(turn_id, []).append(cur[1][start:end])
    return Chunk(0, 0, [], [], alias_to_turn, body_voice, citable_texts)


def _voice_label(voice_class: str) -> str:
    return _NONCITABLE_LABELS.get(voice_class, f"UNCLASSIFIED ({voice_class or 'none'})")


def _render_body_piece(p: Piece, alias: str | None, shown_text: str) -> str:
    part = f", part {p.part} of {p.parts}" if p.parts > 1 else ""
    if p.turn.duplicate_of and p.turn.voice_class in CITABLE_VOICE_CLASSES:
        return f"[SUBJECT, copy of an earlier session{part} | not citable]\n{shown_text}"
    if alias:
        how = "typed" if p.turn.voice_class == "own_typed" else "spoken"
        return f"[{alias} | SUBJECT, {how}{part}]\n{shown_text}"
    return f"[{_voice_label(p.turn.voice_class)}{part} | not citable]\n{shown_text}"


def _context_label(voice_class: str) -> str:
    if voice_class in CITABLE_VOICE_CLASSES:
        return "CONTEXT | SUBJECT, earlier"
    return f"CONTEXT | {_voice_label(voice_class)}"


def build_chunks(turns: list[Turn], budget: int, *,
                 context_budget: int, context_max_turns: int,
                 noncitable_transform=None) -> list[Chunk]:
    """Pack whole turns into chunks of at most `budget` characters of turn text.

    - A turn longer than the budget is split into segments that keep its
      turn_id; no other text is ever cut to fit.
    - Citable turns (own_typed / own_dictated) are shown VERBATIM. The gate
      compares the model's quote against exactly this text, so a renderer that
      edited it would make span_not_found measure the renderer, not the model.
    - Non-citable turns pass through `noncitable_transform(text) -> text`
      (per-source abstraction, e.g. the D-048 rule for Claude Code sessions).
    - Each chunk carries up to `context_max_turns` preceding pieces, at most
      `context_budget` characters, as CONTEXT with no ids. The oldest context
      piece is tail-kept when it does not fit whole.
    - Aliases S1..Sk are per chunk; two segments of one turn share one alias.
    """
    if budget < 200:
        raise ValueError("chunk budget too small")
    xform = noncitable_transform or (lambda s: s)
    piece_max = budget - 100  # room for the header line

    pieces = []
    for t in turns:
        if t.citable:
            pieces.extend(split_turn(t, piece_max))
        else:
            shown = xform(t.text)
            # A transformed non-citable turn is rendered from its own text, so
            # wrap it in a synthetic Turn that carries the transformed text.
            nt = Turn(t.turn_id, t.conversation_id, t.speaker, t.voice_class, shown,
                      t.ordinal, t.contract_version, t.duplicate_of)
            pieces.extend(split_turn(nt, piece_max))

    groups, cur, cur_len = [], [], 0
    for p in pieces:
        size = len(p.text) + 60
        if cur and cur_len + size > budget:
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += size
    if cur:
        groups.append(cur)

    chunks, first_index = [], 0
    for gi, group in enumerate(groups):
        alias_to_turn, turn_alias, body_voice, citable_texts = {}, {}, {}, {}
        lines = []
        for p in group:
            tid = p.turn.turn_id
            body_voice[tid] = p.turn.voice_class
            alias = None
            if p.turn.citable:
                alias = turn_alias.get(tid)
                if alias is None:
                    alias = f"S{len(turn_alias) + 1}"
                    turn_alias[tid] = alias
                    alias_to_turn[alias] = tid
                citable_texts.setdefault(tid, []).append(p.text)
            lines.append(_render_body_piece(p, alias, p.text))

        context, remaining = [], context_budget
        k = first_index - 1
        while k >= 0 and len(context) < context_max_turns and remaining > 0:
            prev = pieces[k]
            text = prev.text
            if len(text) > remaining:
                text = "[...] " + text[len(text) - remaining:]
            context.append((_context_label(prev.turn.voice_class), text))
            remaining -= len(text)
            k -= 1
        context.reverse()

        ch = Chunk(gi + 1, len(groups), group, context, alias_to_turn, body_voice,
                   citable_texts)
        ch.rendered_body = "\n\n".join(lines)
        ch.rendered_context = "\n\n".join(f"[{lab}]\n{txt}" for lab, txt in context)
        chunks.append(ch)
        first_index += len(group)
    return chunks


# ---------------------------------------------------------------------------
# The gate (contract §5). Pure. Never call it inside a try/except.
# ---------------------------------------------------------------------------

_QUOTE_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "«": '"', "»": '"',
})
_WS = re.compile(r"\s+")


def normalise_for_match(s: str) -> str:
    """Whitespace and quote-mark normalisation, and nothing else (contract §5).
    Case, punctuation other than quote marks, and ellipses are left alone, so a
    paraphrase or an ellipsis-joined quote does not match."""
    return _WS.sub(" ", s.translate(_QUOTE_MAP)).strip()


# ---------------------------------------------------------------------------
# The referent (contract §5, subject resolution)
# ---------------------------------------------------------------------------

# Forms the extractor uses for the subject when it does not use a name. Turn mode
# only: the legacy alias tuple in extract_facts.normalize_subject is deliberately
# left as it is, because a changed subject re-keys facts already stored on legacy
# corpora under AUDN.
GENERIC_SUBJECT_FORMS = frozenset({"this person", "the person", "the user", "user"})


class ReferentNotConfigured(RuntimeError):
    """Turn mode cannot run without knowing who the subject is."""


def _subject_key(s) -> str:
    return _WS.sub(" ", str(s or "").translate(_QUOTE_MAP)).strip().strip("\"'").strip().lower()


@dataclass(frozen=True)
class Referent:
    """Who the corpus is about: the configured names (import config
    `subject_names`), plus aliases of OTHER people ({canonical: [variants]}) used
    only by the subject check."""
    names: tuple
    aliases: dict = field(default_factory=dict)

    def is_subject(self, raw) -> bool:
        k = _subject_key(raw)
        return not k or k in GENERIC_SUBJECT_FORMS or k in {_subject_key(n) for n in self.names}

    def is_subject_object(self, raw) -> bool:
        """True when a fact's OBJECT, as a whole, is one of the configured names.
        Unlike is_subject: an empty object is not the subject, and the generic
        forms are not matched ("the user" as an object is usually a product's
        end user). A possessive or a longer phrase holding the name is not matched."""
        k = _subject_key(raw)
        return bool(k) and k in {_subject_key(n) for n in self.names}


def referent_from_config(config) -> Referent:
    """The referent from an ImportConfig. Raises ReferentNotConfigured when
    `subject_names` holds no name."""
    names = tuple(n.strip() for n in (config.subject_names or ()) if n and n.strip())
    if not names:
        where = config.path or "no import config file was found"
        raise ReferentNotConfigured(
            f"turn-contract extraction needs the subject's names in the import config "
            f"(`subject_names`; {where}). Without them the extractor's own name for the "
            f"subject is stored as a third party.")
    return Referent(names=names)


# Leading words stripped from a subject before its name is looked for in the spans,
# longest first, so "the user's wife" is looked for as "wife" and "The company" as
# "company" (never as "The").
_SUBJECT_LEADS = ("the subject's ", "the person's ", "the user's ", "user's ", "subject's ",
                  "my ", "his ", "her ", "their ", "our ", "the ", "a ", "an ")
_PAREN = re.compile(r"\(([^()]*)\)")


def _subject_name_candidates(raw: str, referent: Referent) -> set[str]:
    """Forms of a non-subject name to look for literally in the spans: the name
    with any leading determiner or possessive stripped, a parenthetical name, the
    given name alone (tolerance for a missing surname), and configured aliases."""
    base = _subject_key(raw)
    forms = {base}
    forms.update(_subject_key(m) for m in _PAREN.findall(base))
    forms.add(_subject_key(_PAREN.sub(" ", base)))
    for alias in referent.aliases.get(base, ()):
        forms.add(_subject_key(alias))
    out = set()
    for f in forms:
        for lead in _SUBJECT_LEADS:
            if f.startswith(lead):
                f = f[len(lead):].strip()
                break
        if not f:
            continue
        out.add(f)
        first = f.split()[0]
        if len(first) > 1:
            out.add(first)
    return out


def subject_named_in_spans(raw, spans, referent: Referent) -> bool:
    """True when some form of `raw` (see _subject_name_candidates) appears as whole
    words, case-insensitive, in at least one span."""
    texts = [normalise_for_match(s).lower() for s in spans]
    for name in _subject_name_candidates(raw, referent):
        pat = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
        if any(pat.search(t) for t in texts):
            return True
    return False


def resolve_subject(raw, spans, voices, referent: Referent) -> tuple[str, str | None]:
    """(subject, reassigned_from) for one gated fact.

    The subject under any configured name or generic form becomes `user`. Another
    subject, on a fact whose every span is the subject's own turn, is kept only if
    it is named in a span; otherwise it becomes `user`, and `reassigned_from`
    carries the name it replaced so the run record can count it."""
    if referent.is_subject(raw):
        return "user", None
    subject = str(raw).strip()
    if voices and all(v in CITABLE_VOICE_CLASSES for v in voices)             and not subject_named_in_spans(subject, spans, referent):
        return "user", subject
    return subject, None


def normalize_turn_subject(raw, referent: Referent) -> str:
    """`user` for the subject under any configured name or generic form; any
    other subject stripped and otherwise unchanged (the legacy normaliser runs
    after this and applies the entity map)."""
    return "user" if referent.is_subject(raw) else str(raw).strip()


# ---------------------------------------------------------------------------
# Evidence kind (contract §5): the SHAPE of a span, read mechanically at the gate.
# The model never sees or produces this classification.
# ---------------------------------------------------------------------------

EVIDENCE_KINDS = ("prose", "record")
# Content over layout (two rules, in order):
#   1. alphabetic word tokens under RECORD_MAX_ALPHA_SHARE of all tokens: record;
#   2. a LAYOUT signal (a tab, a line with two or more column gaps, or a leading date)
#      AND an alphabetic share under RECORD_DATED_MAX_ALPHA_SHARE: record;
#   otherwise prose. A layout signal alone no longer makes a record: a tab used as an
#   indent in front of a sentence (a bullet, a journal's comment column) is prose.
# Both cuts are stated, not fitted. Measured on one real own-voice corpus (2026-09-25, lines
# as a stand-in for spans, 42,753 lines decided by the ratio): 0.5 sits above a nearly empty
# region (0.05 to 0.25) and on a lattice gap (9 lines in [0.45, 0.50), 408 at exactly 0.5,
# which a strict < calls prose); moving it to 0.45 changes 9 lines. 0.75 sits in a valley of
# the dated lines (2 lines change if it moves to 0.70) and just above a spike at exactly 2/3
# (a date plus two words), which it therefore calls record. Neither cut separates code or
# machine output with English keywords (shares 0.55 to 0.8) from prose; no share cut can.
RECORD_MAX_ALPHA_SHARE = 0.5
RECORD_DATED_MAX_ALPHA_SHARE = 0.75
_ALPHA_TOKEN = re.compile(r"^[^\w]*[A-Za-z][A-Za-z'\u2019\-]*[^\w]*$")
_COLUMN_GAP = re.compile(r"\S {2,}(?=\S)")
_LEADING_DATE = re.compile(r"^\s*(\d{1,4}[/.\-]\d{1,2}([/.\-]\d{1,4})?)(\s|$)")


def _has_layout_signal(s: str) -> bool:
    return ("\t" in s
            or any(len(_COLUMN_GAP.findall(line)) >= 2 for line in s.splitlines())
            or bool(_LEADING_DATE.match(s)))


def span_evidence_kind(span) -> str:
    """`record` or `prose` for one evidence span, by shape alone, content over layout:
    - alphabetic word tokens under RECORD_MAX_ALPHA_SHARE of all tokens: record;
    - a layout signal (a tab, a line with two or more column gaps, a leading date) with
      an alphabetic share under RECORD_DATED_MAX_ALPHA_SHARE: record;
    - otherwise prose."""
    s = str(span or "")
    toks = s.split()
    if not toks:
        return "prose"
    share = sum(1 for t in toks if _ALPHA_TOKEN.match(t)) / len(toks)
    if share < RECORD_MAX_ALPHA_SHARE:
        return "record"
    if _has_layout_signal(s) and share < RECORD_DATED_MAX_ALPHA_SHARE:
        return "record"
    return "prose"


def fact_grounding(spans) -> str:
    """`record_only` when every span is a record, else `prose`."""
    kinds = [s.get("evidence_kind") for s in spans]
    return "record_only" if kinds and all(k == "record" for k in kinds) else "prose"


@dataclass
class GateResult:
    accepted: list = field(default_factory=list)
    rejected: Counter = field(default_factory=Counter)
    candidates: int = 0
    subject_referent: int = 0                                   # resolved to `user` by name
    subject_reassigned: Counter = field(default_factory=Counter)  # {replaced subject: n}
    record_only: int = 0                                        # accepted, grounded by rows only


def _resolve_ref(ref, chunk: Chunk):
    if not isinstance(ref, str):
        return None
    r = ref.strip()
    alias = r.strip("[]").strip().upper()
    if alias in chunk.alias_to_turn:
        return chunk.alias_to_turn[alias]
    if r in chunk.body_voice:
        return r
    return None


def _span_reason(item, chunk: Chunk, min_words: int = 0, max_chars: int = 0):
    """Check one evidence span. Returns (reason, None) or (None, resolved span).
    The length bound is checked last, so `span_length` means a genuine quote of
    the subject's own words that is too short or too long to ground a fact."""
    if not isinstance(item, dict):
        return "no_turn", None
    ref = item.get("turn", item.get("turn_id"))
    turn_id = _resolve_ref(ref, chunk)
    if turn_id is None:
        return "no_turn", None
    voice = chunk.body_voice.get(turn_id, "")
    if voice not in CITABLE_VOICE_CLASSES or turn_id not in chunk.citable_texts:
        return "not_own_voice", None
    span = item.get("span", item.get("text"))
    needle = normalise_for_match(span) if isinstance(span, str) else ""
    if not needle or not any(needle in normalise_for_match(t)
                             for t in chunk.citable_texts[turn_id]):
        return "span_not_found", None
    if (min_words and len(needle.split()) < min_words) or (max_chars and len(needle) > max_chars):
        return "span_length", None
    return None, ({"turn_id": turn_id, "span": span,
                   "evidence_kind": span_evidence_kind(span)}, voice)


def gate_facts(raw_facts, chunk: Chunk, *, referent: Referent,
               span_min_words: int | None = None,
               span_max_chars: int | None = None) -> GateResult:
    """Apply the §5 conditions to every raw fact from one chunk.

    A fact passes only if:
      1. it carries at least one evidence span (else no_grounding);
      2. EVERY span names a turn in THIS chunk's body (an alias S<n>, or a body
         turn's real id; a context turn is not in the chunk: no_turn) whose
         voice_class is own_typed or own_dictated (else not_own_voice);
      3. EVERY span, normalised, is a substring of that turn's text as shown in
         this chunk (else span_not_found);
      4. EVERY span is within the length bounds (else span_length). The bounds
         default to span_bounds(), so no caller can skip them by omission.
    A fact grounded only in assistant, other-person or pasted text therefore
    fails with not_own_voice, and so does a fact that mixes one own span with a
    non-own one. When several spans fail, the reason counted is the first
    failing span's, in the order the model gave them (one reason per fact).

    Accepted facts are copies with `evidence_spans` resolved to real turn ids,
    `source_turn_id` set to the first span's turn, `voice_class` to that turn's
    class, and `inferred` coerced to bool. Nothing here catches exceptions.

    After the span check, the subject is resolved against `referent` (required,
    so no caller skips it by omission): any configured name or generic form of
    the subject becomes `user`, and another subject that no span names becomes
    `user` too, counted in `subject_reassigned` (resolve_subject).

    Then the object: an object that IS a configured name (whole object,
    Referent.is_subject_object) is the subject. With a resolved subject of `user`
    the fact relates the subject to themselves and is rejected (`self_object`);
    with another subject the object becomes `user`.
    """
    lo, hi = span_bounds()
    lo = lo if span_min_words is None else span_min_words
    hi = hi if span_max_chars is None else span_max_chars
    res = GateResult()
    for fact in raw_facts or []:
        res.candidates += 1
        if not isinstance(fact, dict):
            res.rejected["no_grounding"] += 1
            continue
        spans = fact.get("evidence_spans")
        if not isinstance(spans, list) or not spans:
            res.rejected["no_grounding"] += 1
            continue
        resolved, voices, reason = [], [], None
        for item in spans:
            reason, ok = _span_reason(item, chunk, lo, hi)
            if reason:
                break
            resolved.append(ok[0])
            voices.append(ok[1])
        if reason:
            res.rejected[reason] += 1
            continue
        subject, replaced = resolve_subject(fact.get("subject"),
                                            [r["span"] for r in resolved], voices, referent)
        self_named_object = referent.is_subject_object(fact.get("object"))
        if self_named_object and subject == "user":
            # The subject related to themselves ("user collaborates with <name>").
            # Rejected before any accepted-side counter moves.
            res.rejected["self_object"] += 1
            continue
        out = dict(fact)
        out["evidence_spans"] = resolved   # [{"turn_id", "span", "evidence_kind"}], §4a
        out["grounding"] = fact_grounding(resolved)
        if out["grounding"] == "record_only":
            res.record_only += 1
        out["source_turn_id"] = resolved[0]["turn_id"]
        out["voice_class"] = voices[0]            # of the first span's turn
        out["inferred"] = _as_bool(fact.get("inferred"))
        if replaced is not None:
            res.subject_reassigned[replaced] += 1
        elif subject == "user" and _subject_key(fact.get("subject")) not in ("", "user"):
            res.subject_referent += 1
        out["subject"] = subject
        if self_named_object:
            out["object"] = "user"          # another person's relation to the subject
        res.accepted.append(out)
    return res


def _as_bool(v) -> bool:
    """Strict coercion of the model's `inferred` flag. Only an explicit true value
    counts: `bool("false")` is True, and a list or dict is not an answer. Anything
    that is not clearly true is False (a restatement), which is the conservative
    reading: verification samples inferred facts more heavily, not less."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "inferred")
    if isinstance(v, int):
        return v == 1
    return False


# ---------------------------------------------------------------------------
# Stamps (contract §7)
# ---------------------------------------------------------------------------

def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def git_commit_of(path) -> str:
    """HEAD of the checkout that holds `path`, with '-dirty' when src/ has
    uncommitted changes. Returns 'unknown' rather than raising: a missing git
    must not stop a run, but it must be visible in the stamp."""
    d = str(Path(path).resolve().parent)
    try:
        head = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=10)
        if head.returncode != 0:
            return "unknown"
        commit = head.stdout.strip()
        dirty = subprocess.run(["git", "-C", d, "status", "--porcelain", "--", "."],
                               capture_output=True, text=True, timeout=10)
        if dirty.returncode == 0 and dirty.stdout.strip():
            commit += "-dirty"
        return commit
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def code_path_of(path) -> str:
    """Repo-relative path of a code file, e.g. 'src/baselayer/extract_facts.py'.

    NEVER absolute: a stamp is written into every fact, and an absolute path
    would put the operator's username and directory layout into every row of a
    database that may be shared. Falls back to the package-relative
    'baselayer/<name>' when git cannot say where the file sits.
    """
    p = Path(path).resolve()
    try:
        r = subprocess.run(["git", "-C", str(p.parent), "rev-parse", "--show-prefix"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return (r.stdout.strip() + p.name).replace("\\", "/")
    except (OSError, subprocess.SubprocessError):
        pass
    return f"{p.parent.name}/{p.name}"


def extraction_stamp(model: str, prompt_hash_value: str, *, contract_version=TURN_CONTRACT_VERSION,
                     code_file=None) -> dict:
    code_file = code_file or __file__
    return {
        "turn_contract_version": contract_version,
        "extraction_model": model,
        "extraction_prompt_hash": prompt_hash_value,
        "git_commit": git_commit_of(code_file),
        "code_path": code_path_of(code_file),
    }


# ---------------------------------------------------------------------------
# API usage (measured, never estimated)
# ---------------------------------------------------------------------------

USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens")


def usage_entry(usage, **labels) -> dict:
    """One call's billed tokens from a Messages API `usage` object. A missing or None
    field counts as 0 (older SDKs omit the cache fields). A call whose response carried no
    usage at all is still an entry, zeroed and marked, so the call count stays true and the
    gap is visible in the totals rather than silently shrinking them."""
    d = {f: int(getattr(usage, f, 0) or 0) for f in USAGE_FIELDS}
    if usage is None:
        d["usage_missing"] = True
    d.update(labels)
    return d


def usage_totals(calls) -> dict:
    """Totals over every call, plus the batch and sequential subtotals (the batch API bills
    at a different rate, so the two must be priced separately)."""
    def _sum(cs):
        t = {f: sum(c.get(f, 0) for c in cs) for f in USAGE_FIELDS}
        t["calls"] = len(cs)
        t["calls_without_usage"] = sum(1 for c in cs if c.get("usage_missing"))
        return t
    calls = list(calls)
    out = _sum(calls)
    out["batch"] = _sum([c for c in calls if c.get("batch")])
    out["sequential"] = _sum([c for c in calls if not c.get("batch")])
    return out


def usage_line(totals: dict) -> str:
    return (f"API usage (measured): {totals['calls']:,} calls | "
            f"{totals['input_tokens']:,} input | {totals['output_tokens']:,} output | "
            f"{totals['cache_read_input_tokens']:,} cache read | "
            f"{totals['cache_creation_input_tokens']:,} cache write"
            + (f" | {totals['calls_without_usage']:,} calls reported NO usage"
               if totals.get("calls_without_usage") else ""))


# ---------------------------------------------------------------------------
# Per-run record
# ---------------------------------------------------------------------------

def _nearest_rank(sorted_vals, q):
    """Nearest-rank percentile of an ascending list (q in 0..100)."""
    if not sorted_vals:
        return None
    import math
    k = max(1, math.ceil(q / 100 * len(sorted_vals)))
    return sorted_vals[k - 1]


def density_summary(rows) -> dict:
    """The density ALARM: facts after the gate per 1K citable characters, per
    conversation, with the run's own p50/p90/p99/max (nearest rank) and the ten densest
    conversations. It reports and never trims; its reference distribution is the run
    itself. Conversations with no citable characters are counted apart."""
    scored = []
    for r in rows:
        c = r.get("citable_chars") or 0
        if c > 0:
            scored.append(dict(r, facts_per_1k_citable=round(r["facts"] * 1000 / c, 2)))
    vals = sorted(r["facts_per_1k_citable"] for r in scored)
    top = sorted(scored, key=lambda r: (-r["facts_per_1k_citable"], str(r["conversation_id"])))
    return {"conversations": len(scored),
            "without_citable_chars": len(rows) - len(scored),
            "p50": _nearest_rank(vals, 50), "p90": _nearest_rank(vals, 90),
            "p99": _nearest_rank(vals, 99), "max": vals[-1] if vals else None,
            "top10": top[:10]}


class ExtractionRunRecord:
    """Counts for one extraction run, printed at the end and written to disk.

    A gate that rejects nothing, or everything, is itself suspect (contract §5),
    so both conditions are flagged, not just reported.
    """

    SUSPECT_MIN_CANDIDATES = 20

    def __init__(self, mode: str, settings: dict, stamp: dict | None = None):
        self.run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "_" + os.urandom(3).hex()
        self.mode = mode
        self.settings = dict(settings)
        self.stamp = dict(stamp or {})
        self.started_at = time.time()
        self.c = Counter()
        self.rejected = Counter({r: 0 for r in REJECT_REASONS})
        self.post_gate_drops = Counter()
        self.subject_reassigned_from = Counter()
        self.audn = Counter()
        self.response_failures = {}
        self.usage_calls = []     # one usage_entry per billed API call (usage_entry)
        self.rechunked = []       # one entry per chunk re-chunked after a max_tokens stop
        self.density = []         # one row per conversation: citable chars, facts after the gate
        self.failed_chunks = []   # one entry per failed chunk this run left recorded for retry
        self.notes = []

    def add_gate(self, g: GateResult):
        self.c["candidates"] += g.candidates
        self.c["accepted"] += len(g.accepted)
        self.rejected.update(g.rejected)
        self.c["record_only"] += g.record_only
        self.c["subject_referent"] += g.subject_referent
        self.c["subject_reassigned"] += sum(g.subject_reassigned.values())
        self.subject_reassigned_from.update(g.subject_reassigned)

    def to_dict(self) -> dict:
        cand, acc = self.c["candidates"], self.c["accepted"]
        suspect = []
        if cand >= self.SUSPECT_MIN_CANDIDATES and sum(self.rejected.values()) == 0:
            suspect.append("gate_rejected_nothing")
        if cand > 0 and acc == 0:
            suspect.append("gate_rejected_everything")
        if any(r.get("still_truncated") for r in self.rechunked):
            suspect.append("max_tokens_after_rechunk")
        return {
            "run_id": self.run_id, "mode": self.mode,
            "started_at": self.started_at, "finished_at": time.time(),
            "settings": self.settings, "stamp": self.stamp,
            "counts": dict(self.c), "gate_rejections": dict(self.rejected),
            "post_gate_drops": dict(self.post_gate_drops), "audn": dict(self.audn),
            "subject_reassigned_from": dict(self.subject_reassigned_from),
            "response_failures": dict(self.response_failures),
            "rechunked": list(self.rechunked),
            "failed_chunks": list(self.failed_chunks),
            "density": density_summary(self.density),
            "api_usage": {"totals": usage_totals(self.usage_calls),
                          "calls": list(self.usage_calls)},
            "suspect": suspect, "notes": list(self.notes),
        }

    def summary_lines(self) -> list[str]:
        d = self.to_dict()
        c = d["counts"]
        lines = [
            f"Turn-contract gate ({TURN_CONTRACT_VERSION}), run {self.run_id}:",
            f"  candidates {c.get('candidates', 0)} | accepted {c.get('accepted', 0)} | "
            + " | ".join(f"{k} {v}" for k, v in d["gate_rejections"].items()),
        ]
        if d["post_gate_drops"]:
            lines.append("  dropped after the gate: "
                         + ", ".join(f"{k} {v}" for k, v in sorted(d["post_gate_drops"].items())))
        if c.get("record_only"):
            lines.append(f"  record_only {c['record_only']} (grounded by record spans only; "
                         f"kept, excluded from distillation by default)")
        if c.get("subject_referent") or c.get("subject_reassigned"):
            lines.append(f"  subject: referent resolved {c.get('subject_referent', 0)} | "
                         f"subject_reassigned {c.get('subject_reassigned', 0)}")
        if c.get("rechunked_on_max_tokens"):
            lines.append(f"  rechunked_on_max_tokens {c['rechunked_on_max_tokens']} "
                         f"({sum(r['still_truncated'] for r in d['rechunked'])} parts "
                         f"truncated again, listed in the record)")
        den = d["density"]
        if den["conversations"]:
            lines.append(f"  density (facts per 1K citable chars, {den['conversations']} "
                         f"conversations): p50 {den['p50']} | p90 {den['p90']} | "
                         f"p99 {den['p99']} | max {den['max']}")
            for row in den["top10"][:3]:
                lines.append(f"    {row['facts_per_1k_citable']:>8} {row['facts']:>5} facts / "
                             f"{row['citable_chars']:,} chars  {row['conversation_id']}")
        if c.get("chunks_retried"):
            lines.append(f"  failed chunks retried {c['chunks_retried']} | recovered "
                         f"{c.get('chunks_recovered', 0)}")
        if c.get("chunks_failed_open"):
            convs = len({f["conversation_id"] for f in d["failed_chunks"]})
            lines.append(f"  FAILED chunks {c['chunks_failed_open']} in {convs} conversation(s): "
                         f"not stored, recorded in extraction_chunks_failed, retried by the next "
                         f"run (listed in the record)")
        if d["response_failures"]:
            lines.append("  unusable responses: "
                         + ", ".join(f"{k} {v}" for k, v in sorted(d["response_failures"].items())))
        lines.append("  " + usage_line(d["api_usage"]["totals"]))
        for flag in d["suspect"]:
            lines.append(f"  SUSPECT: {flag}")
        return lines

    def write(self, conn=None, root=None) -> Path:
        """Write the record as JSON under <corpus>/data/database/extraction_runs/
        (resolved at call time, so MEMORY_SYSTEM_ROOT is honoured), and as a row
        in the corpus DB's extraction_runs table when a connection is given."""
        if root is None:
            import baselayer.config as _cfg
            root = _cfg.PROJECT_ROOT
        d = self.to_dict()
        out_dir = Path(root) / "data" / "database" / "extraction_runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        if conn is not None:
            conn.execute("""CREATE TABLE IF NOT EXISTS extraction_runs (
                run_id TEXT PRIMARY KEY, mode TEXT, started_at REAL, finished_at REAL,
                record_json TEXT)""")
            conn.execute("INSERT OR REPLACE INTO extraction_runs VALUES (?,?,?,?,?)",
                         (self.run_id, self.mode, d["started_at"], d["finished_at"],
                          json.dumps(d, ensure_ascii=False)))
            conn.commit()
        return path


# ---------------------------------------------------------------------------
# Artifact stamps (contract §7): leaves, trees, packages, layers, briefs
# ---------------------------------------------------------------------------

class MixedContractVersions(ValueError):
    """An artifact would be built from inputs stamped with more than one
    turn-contract version (a NULL, i.e. unversioned legacy input, counts as a
    version of its own)."""


def facts_input_hash(rows) -> str:
    """Hash of a set of facts by id AND text.

    `rows` is an iterable of (fact_id, fact_text). A hash of the ids alone
    cannot tell two corpora apart when the same ids carry different text, so
    both go in. Serialised as a sorted JSON list of [id, text] pairs, which
    cannot run two fields together the way a joined string can."""
    pairs = sorted([str(i), t] for i, t in rows)
    blob = json.dumps(pairs, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def json_input_hash(obj) -> str:
    """Hash of a JSON-serialisable input (a tree, a package), key order ignored."""
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def single_contract_version(values, what: str = "inputs"):
    """The one turn-contract version shared by `values`, or None when every
    input is unversioned. Raises MixedContractVersions on any mix."""
    seen = set(values)
    if len(seen) > 1:
        shown = sorted("NULL (unversioned)" if v is None else str(v) for v in seen)
        raise MixedContractVersions(
            f"refusing to build one artifact from a mix of turn-contract versions across "
            f"{what}: {', '.join(shown)}. Facts gated under different contracts, or gated "
            f"and ungated facts, carry different guarantees; build each set separately.")
    return next(iter(seen), None)


ARTIFACT_STAMP_VERSION = "artifact-stamp/1"


def artifact_stamp(kind: str, *, code_file, model=None, prompt_hash=None, input_hash=None,
                   turn_contract_version=None, **extra) -> dict:
    """The contract §7 stamp for a derived artifact. `code_path` is repo-relative
    (never absolute); `git_commit` carries '-dirty' when the code file's own
    directory has uncommitted changes. `model` and `prompt_hash` are None for a
    mechanical step that runs no model."""
    d = {
        "stamp_version": ARTIFACT_STAMP_VERSION,
        "kind": kind,
        "turn_contract_version": turn_contract_version,
        "model": model,
        "prompt_hash": prompt_hash,
        "input_hash": input_hash,
        "git_commit": git_commit_of(code_file),
        "code_path": code_path_of(code_file),
    }
    d.update(extra)
    return d
