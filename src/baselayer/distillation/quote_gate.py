"""Author quote gate: a quoted phrase in an authored claim must be the person's own words, taken
from the evidence that claim cites. Default off (`author_from_package --quote-gate --db`).

WHY. With the leaf seeing each fact's verbatim spans (design T1), the author starts quoting the
person, and some quoted phrases are not the person's words: assistant phrases shown as the
person's, idioms, and paraphrases placed inside quote marks. The leaf `own_words` field
already has this rule (an excerpt must be a substring of THAT fact's own spans); this applies
the same rule at the author.

THE RULE. Every quoted phrase (double or single quotes, straight or curly) in a claim's name,
statement or active_when must be a substring, after `normalise_for_match` (whitespace and quote
marks only), case-folding and trimming of leading/trailing punctuation, of an own-voice evidence
span of a fact the claim cites. Own voice is a turn classed own_typed or own_dictated; that
includes a pasted segment re-classed as the person's own writing (basis
allowlist:own_writing_pasted, for example a document the person wrote and pasted in), which is
theirs even though they did not type it. An ellipsis-joined quote does not match, as in the
turn contract.

Reasons, first that applies, and what the gate does (one authoring attempt, no re-ask):
  uncited_span   found in an own-voice span of another fact the author was given. The words ARE
                 the person's, only the citation is missing, so every holding fact is auto-cited (`F-` id
                 appended to fact_ids) and ALSO listed in the claim's `gate_added_citations`, so
                 a citation the gate chose stays distinguishable from one the author chose.
                 BOUNDED: only a quote of >= AUTO_CITE_MIN_WORDS words with <= AUTO_CITE_MAX_HOLDERS
                 holders is auto-cited. A short quote or one held by many facts is generic
                 wording, and citing every holder would inflate the claim's evidence, so its
                 quote marks are removed instead (action stripped_short / stripped_many_holders).
  elided         carries an ellipsis. Quote marks removed, words kept as paraphrase.
  not_found      in no own-voice span of any fact the author was given. Quote marks removed,
                 words kept as paraphrase.
"Given" is the `supplied` set of the call, so a sharded layer only auto-cites within its shard.

WHY NOT RE-ASK. Re-asking re-sent the whole layer prompt (300-400K tokens per shard) to fix
quote marks, and a layer that quotes the person often trips it, so with up to three attempts
the gate could triple the authoring budget to correct something it can correct mechanically.
"""
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass

from baselayer import turn_contract as _tc
from baselayer.voice import B_OWN_WRITING

FIELDS = ("name", "statement", "active_when")
REASONS = ("uncited_span", "elided", "not_found")
MIN_WORDS = 1
# Auto-cite bounds (see the module docstring). Quotes held by many facts tend to be one or two
# common words; a quote of three or more words is rarely held by more than a handful.
AUTO_CITE_MIN_WORDS = 3
AUTO_CITE_MAX_HOLDERS = 5
ACTIONS = ("auto_cited", "stripped_short", "stripped_many_holders", "stripped_elided",
           "stripped_not_found")

PROMPT_RULE = (
    "QUOTE MARKS MEAN THIS PERSON'S OWN WORDS. Put quote marks only around words copied exactly "
    "from an `own words` excerpt of a fact the claim cites, and cite that fact. Anything else, "
    "including a paraphrase or an idiom, is written without quote marks. Quotes are checked "
    "against the own-words excerpts of the facts you were given, and quote marks around words "
    "not found there are removed.")

# Double quotes, straight or curly. Single quotes open after start/space/bracket/colon/dash/slash
# and close before space/punctuation/end, so an in-word apostrophe (can't, it's) and a plural
# possessive (users') neither open nor close a quote.
_DQ = re.compile(r'"([^"\n]{1,400}?)"|“([^“”\n]{1,400}?)”')
_SQ = re.compile(r"(?:^|(?<=[\s(\[:/—–-]))(['‘])"
                 r"((?:[^'‘’\n]|(?<=[A-Za-z])['’](?=[A-Za-z])){1,400}?)"
                 r"(['’])(?=[\s.,;:)!?\]—–-]|$)")
_ELLIPSIS = re.compile(r"\.\.\.|…")
_EDGE = " \t\n.,;:!?"


class QuoteGateUnavailable(RuntimeError):
    """The gate cannot check what it was asked to check (missing column, fact or table).
    Raised rather than passing claims unchecked."""


@dataclass
class Quote:
    raw: str      # with its quote marks, exactly as written
    inner: str    # the phrase between them


@dataclass
class Finding:
    claim_id: str
    field: str
    phrase: str
    raw: str
    reason: str
    source_ids: tuple = ()   # uncited_span: the supplied facts whose spans hold the words
    claim_pos: int = -1      # index of the claim in the list checked; ids need not be unique


def quoted_phrases(text):
    """Quoted phrases in `text`, in order of appearance."""
    text = text or ""
    found = []
    for m in _DQ.finditer(text):
        found.append((m.start(), Quote(m.group(0), m.group(1) if m.group(1) is not None
                                       else m.group(2))))
    for m in _SQ.finditer(text):
        found.append((m.start(), Quote(m.group(0), m.group(2))))
    return [q for _, q in sorted(found, key=lambda x: x[0])]


def normalise(s):
    return _tc.normalise_for_match(s or "").lower().strip(_EDGE)


def load_spans(db, ids):
    """({8-char id: [own-voice span text]}, info) for every id, read-only.

    Raises QuoteGateUnavailable if the database lacks evidence_spans or turn voice columns, or if
    any id resolves to no live fact. A prefix shared by several live facts takes the union of
    their spans and is counted in info["ambiguous_prefixes"]."""
    c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        fcols = {r[1] for r in c.execute("PRAGMA table_info(memory_facts)")}
        tcols = {r[1] for r in c.execute("PRAGMA table_info(turns)")}
        if "evidence_spans" not in fcols:
            raise QuoteGateUnavailable("%s: memory_facts has no evidence_spans column" % db)
        if not {"turn_id", "voice_class"} <= tcols:
            raise QuoteGateUnavailable("%s: turns table lacks turn_id/voice_class" % db)
        live = " WHERE superseded_by IS NULL" if "superseded_by" in fcols else ""
        want = {i[:8] for i in ids}
        rows = [r for r in c.execute("SELECT id, evidence_spans FROM memory_facts" + live)
                if r[0][:8] in want]
        basis = "basis" if "basis" in tcols else "NULL"
        voice = {r[0]: (r[1], r[2]) for r in c.execute(
            "SELECT turn_id, voice_class, %s FROM turns" % basis)}
    finally:
        c.close()
    per = {}
    for fid, _ in rows:
        per.setdefault(fid[:8], []).append(fid)
    missing = sorted(want - set(per))
    if missing:
        raise QuoteGateUnavailable("%d fact ids resolve to no live fact in %s: %s"
                                   % (len(missing), db, ", ".join(missing)))
    spans = {i: [] for i in want}
    info = Counter()
    for fid, ev in rows:
        try:
            items = json.loads(ev or "[]")
        except ValueError:
            raise QuoteGateUnavailable("fact %s has unreadable evidence_spans" % fid)
        for s in items:
            vc, b = voice.get(s.get("turn_id"), (None, None))
            if vc in _tc.CITABLE_VOICE_CLASSES or b == B_OWN_WRITING:
                spans[fid[:8]].append(s.get("span") or "")
                info["own_spans"] += 1
                if b == B_OWN_WRITING:
                    info["own_writing_pasted_spans"] += 1
            else:
                info["non_own_spans_skipped"] += 1
    info["facts"] = len(want)
    info["ambiguous_prefixes"] = sum(1 for v in per.values() if len(v) > 1)
    return spans, dict(info)


class QuoteGate:
    """Checks claims against {8-char id: [own-voice span]}."""

    def __init__(self, spans, min_words=MIN_WORDS):
        self.spans = {k: [normalise(s) for s in v] for k, v in spans.items()}
        self.min_words = min_words

    def _in(self, ids, q):
        return any(q in s for i in ids for s in self.spans.get(i, ()))

    def _holders(self, ids, q):
        return tuple(sorted(i for i in ids if any(q in s for s in self.spans.get(i, ()))))

    def phrases(self, claims):
        """[(claim, field, Quote, normalised phrase)] for every checked quote."""
        out = []
        for c in claims:
            for f in FIELDS:
                for q in quoted_phrases(c.get(f)):
                    n = normalise(q.inner)
                    if len(n.split()) >= self.min_words:
                        out.append((c, f, q, n))
        return out

    def check(self, claims, supplied):
        """Findings for every quote not found in the spans of the facts its claim cites."""
        bad = []
        supplied = {s.lstrip("F-").strip("[]") for s in supplied}
        pos = {id(c): i for i, c in enumerate(claims)}
        for c, f, q, n in self.phrases(claims):
            cited = [x.lstrip("F-").strip("[]") for x in c.get("fact_ids") or []]
            if self._in(cited, n):
                continue
            holders = self._holders(supplied - set(cited), n)
            if holders:
                reason = "uncited_span"
            elif _ELLIPSIS.search(q.inner):
                reason = "elided"
            else:
                reason = "not_found"
            bad.append(Finding(c.get("id") or "?", f, q.inner, q.raw, reason, holders,
                               pos.get(id(c), -1)))
        return bad

    @staticmethod
    def _target(claims, fd):
        """The claim a finding came from: by position when the finding carries one (claim ids
        need not be unique), else the first claim with that id whose field holds the quote."""
        if 0 <= fd.claim_pos < len(claims):
            c = claims[fd.claim_pos]
            if fd.raw in (c.get(fd.field) or ""):
                return c
        for c in claims:
            if (c.get("id") or "?") == fd.claim_id and fd.raw in (c.get(fd.field) or ""):
                return c
        return None

    @staticmethod
    def strip(claims, findings):
        """Remove the quote marks (not the words) of each finding. Returns the number removed."""
        n = 0
        for fd in findings:
            c = QuoteGate._target(claims, fd)
            if c is not None:
                c[fd.field] = c[fd.field].replace(fd.raw, fd.phrase, 1)
                n += 1
        return n

    @staticmethod
    def auto_cite(claims, findings):
        """Cite, on its claim, every supplied fact whose own-voice span holds an `uncited_span`
        quote. Ids are appended to fact_ids in the `F-` form, once each, and listed in the
        claim's `gate_added_citations` so a gate-chosen citation is never mistaken for an
        author-chosen one. Other reasons are ignored. Returns the number of ids added."""
        n = 0
        for fd in findings:
            if fd.reason != "uncited_span" or not fd.source_ids:
                continue
            c = QuoteGate._target(claims, fd)
            if c is None:
                continue
            ids = c.setdefault("fact_ids", [])
            have = {x.lstrip("F-").strip("[]") for x in ids}
            for sid in fd.source_ids:
                if sid not in have:
                    ids.append("F-%s" % sid)
                    c.setdefault("gate_added_citations", []).append("F-%s" % sid)
                    have.add(sid)
                    n += 1
        return n


def disposition(fd):
    """What the gate does with one finding: `auto_cited`, or a `stripped_*` action naming why
    the quote marks were removed instead."""
    if fd.reason == "uncited_span":
        if len(normalise(fd.phrase).split()) < AUTO_CITE_MIN_WORDS:
            return "stripped_short"
        if len(fd.source_ids) > AUTO_CITE_MAX_HOLDERS:
            return "stripped_many_holders"
        return "auto_cited"
    return "stripped_" + fd.reason


MODE = "auto_cite_strip"


def new_stats(gate, span_info):
    return {"enabled": True, "mode": MODE, "min_words": gate.min_words,
            "auto_cite_min_words": AUTO_CITE_MIN_WORDS,
            "auto_cite_max_holders": AUTO_CITE_MAX_HOLDERS,
            "fields": list(FIELDS), "reasons": list(REASONS), "actions": list(ACTIONS),
            "spans": span_info, "attempts": [], "auto_cited": 0, "final": None}


def record(stats, attempt, n_checked, findings):
    by = Counter(f.reason for f in findings)
    stats.setdefault("attempts", []).append(
        {"attempt": attempt, "quotes_checked": n_checked, "flagged": len(findings),
         "by_reason": dict(by)})
    return by
