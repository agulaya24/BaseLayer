"""Align Claude Code prompt-history entries to the subject turns of one session.

``history.jsonl`` records what the subject submitted at the prompt, with pasted blocks
replaced by ``[Pasted text #n]`` placeholders. A transcript of the same session holds the
same prompt with the paste expanded, inside wrappers the harness added. This module finds,
for each history entry, the subject turn that carries it. Deterministic: no model call.

Used for three things:

* deduplication: a history prompt that a transcript copy already carries (with its
  assistant context) is marked a duplicate of that copy instead of being counted twice;
* corroboration: a stored user turn that matches a history prompt was submitted at the
  prompt, which a database copy (whose source flags were discarded) cannot otherwise show;
* paste location: the typed pieces of a history entry, located in the transcript turn,
  bound the pasted material between them exactly.
"""
from __future__ import annotations

import re

from baselayer import voice as V

# Placeholders that history writes in place of content the transcript expands.
PLACEHOLDER_RE = re.compile(r"\[Pasted text #\d+(?: \+\d+ lines)?\]|\[Image #\d+\]", re.I)

# An entry whose typed text is shorter than this matches only a turn that is exactly it,
# and only near the alignment pointer: "yes" occurs everywhere.
SHORT_CHARS = 24
SHORT_WINDOW = 40


def is_prompt_entry(entry) -> bool:
    """The history entries ``turn_import.build_history_turns`` turns into prompts."""
    disp = (entry.get("display") or "").strip()
    return bool(disp) and not disp.startswith("/") and not disp.startswith("!")


def typed_pieces(display: str) -> list:
    """Normalized typed text of a history entry, split at paste and image placeholders."""
    return [p for p in (V.norm_text(x) for x in PLACEHOLDER_RE.split(display or "")) if p]


def _matches(pieces, turn_norm: str, exact: bool, anchored_start: bool) -> bool:
    if exact:
        return turn_norm == pieces[0]
    if anchored_start and not turn_norm.startswith(pieces[0]):
        return False
    pos = 0
    for p in pieces:
        i = turn_norm.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def align(entries, turn_texts) -> list:
    """-> for each entry, the index into ``turn_texts`` that carries it, or None.

    Entries and turns are both in time order. A long entry is searched ahead of the last
    match, then behind it (queued and resubmitted prompts land out of order); a short one
    only within ``SHORT_WINDOW`` turns either side, because short texts recur. A short
    entry with no placeholder must equal the turn; one with a placeholder must open the
    turn (when the entry opens with typed text) and contain its typed pieces in order.
    A turn carries at most one entry. An entry that is only placeholders has no typed
    text to match and returns None.
    """
    norms = [V.norm_text(V.strip_wrappers(t)) for t in turn_texts]
    used = set()
    out = []
    ptr = 0
    for e in entries:
        display = e.get("display") or ""
        pieces = typed_pieces(display)
        if not pieces:
            out.append(None)
            continue
        has_tag = bool(PLACEHOLDER_RE.search(display))
        short = sum(len(p) for p in pieces) < SHORT_CHARS
        exact = short and not has_tag
        anchored = short and not PLACEHOLDER_RE.match(display.strip())

        def ok(j):
            return j not in used and _matches(pieces, norms[j], exact, anchored)
        if short:
            ahead = range(ptr, min(len(norms), ptr + SHORT_WINDOW))
            behind = range(ptr - 1, max(-1, ptr - 1 - SHORT_WINDOW), -1)
        else:
            ahead, behind = range(ptr, len(norms)), range(ptr - 1, -1, -1)
        hit = next((j for j in ahead if ok(j)), None)
        if hit is not None:
            ptr = hit + 1
        else:
            hit = next((j for j in behind if ok(j)), None)
        if hit is not None:
            used.add(hit)
        out.append(hit)
    return out


def _is_long(entry) -> bool:
    return sum(len(p) for p in typed_pieces(entry.get("display") or "")) >= SHORT_CHARS


def settle(entries, aligned):
    """Reject short matches past the end of a truncated copy. -> (aligned, end index).

    A copy that stops early leaves the pointer at its last turns, where later short
    prompts ("ok", "yes") still find equal turns and would be marked duplicates of text
    the copy never held. After the last long match, a long entry with no match is
    evidence the copy has ended; every short match after it is dropped. The end is the
    entry matched to the latest stored turn, or None when nothing matched. A prompt
    resubmitted later that aligns backward to an early turn does not move the end.
    """
    long_ = [_is_long(e) for e in entries]
    hits = [(k, j) for j, k in enumerate(aligned) if k is not None and long_[j]]
    start = max(hits)[1] + 1 if hits else 0
    out = list(aligned)
    ended = False
    for j in range(start, len(entries)):
        if long_[j] and out[j] is None:
            ended = True
        elif ended and not long_[j] and out[j] is not None:
            out[j] = None
    hits = [(k, j) for j, k in enumerate(out) if k is not None]
    return out, (max(hits)[1] if hits else None)


def _piece_regex(piece: str):
    words = piece.split(" ")
    return re.compile(r"\s+".join(re.escape(w) for w in words), re.I)


def paste_spans(display: str, text: str) -> list:
    """Char spans of ``text`` that the history entry shows as pasted.

    Every typed piece of the entry is located in ``text`` in order (case- and
    whitespace-insensitive); a placeholder between, before or after typed pieces marks the
    text there as pasted. Returns [] when the entry has no paste placeholder or when a
    piece cannot be located (the caller then falls back to the text detectors).
    """
    display = display or ""
    parts = PLACEHOLDER_RE.split(display)
    tags = PLACEHOLDER_RE.findall(display)
    if not any(t.lower().startswith("[pasted") for t in tags):
        return []
    located = []
    pos = 0
    for k, raw in enumerate(parts):
        piece = V.norm_text(raw)
        if not piece:
            located.append(None)
            continue
        rx = _piece_regex(piece)
        if k == len(parts) - 1 and k > 0:
            # The trailing typed piece follows a paste that may contain the same words; the
            # typed text is the LAST occurrence, not the first.
            m = None
            for m in rx.finditer(text, pos):
                pass
        else:
            m = rx.search(text, pos)
        if m is None:
            return []
        located.append((m.start(), m.end()))
        pos = m.end()
    spans = []
    prev_end = 0
    for i, tag in enumerate(tags):
        # the pasted block sits between typed piece i and typed piece i+1
        left = next((located[k][1] for k in range(i, -1, -1) if located[k]), 0)
        right = next((located[k][0] for k in range(i + 1, len(located)) if located[k]), len(text))
        left = max(left, prev_end)
        if tag.lower().startswith("[pasted") and right > left and text[left:right].strip():
            spans.append((left, right))
            prev_end = right
    return spans
