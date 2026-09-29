"""Import-time secret redaction (docs/core/TURN_CONTRACT.md, section 1).

Every turn's text is passed through ``redact`` before it is written, whatever its voice
class: context turns (assistant text, tool output, summaries, pastes) are sent to the
extraction model exactly as citable turns are, so a secret in either one leaves the
machine. A matched secret is replaced by ``[REDACTED:<kind>]`` and counted per kind; the
secret itself is never returned, logged or stored.

The rules are deterministic regular expressions with bounded repetition, so a 700K-char
turn costs linear time. They aim at SHAPES (provider key prefixes, JWTs, PEM blocks,
Luhn-valid card numbers, SSN layout) and at values in an explicit key context
(``api_key = ...``, ``Bearer ...``, ``password: ...``). A secret written as free prose
("the password is swordfish") has no shape and is not caught; that recall gap is stated,
not hidden.

Redaction is idempotent: the placeholder matches no rule, and the ``[REDACTED...]`` markers
an older pipeline wrote are left alone.
"""
from __future__ import annotations

import collections
import re

PLACEHOLDER = "[REDACTED:{}]"

# --------------------------------------------------------------------------- shapes
# Order matters: specific shapes first, so a key inside a key context is counted as its
# provider kind, and the context rule then sees only the placeholder.
_SHAPES = [
    ("private_key", re.compile(
        r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
        # RFC 1421 headers of a legacy encrypted PEM ("Proc-Type: 4,ENCRYPTED",
        # "DEK-Info: AES-128-CBC,<iv>") carry '-', ':' and ',', which end the body class.
        r"(?:\s{0,4}(?:Proc-Type|DEK-Info):[^\n]{0,200}){0,2}"
        r"[A-Za-z0-9+/=\s\\]{0,20000}"
        r"(?:-----END [A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----)?")),
    ("anthropic_key", re.compile(r"(?<![A-Za-z0-9_-])sk-ant-[A-Za-z0-9_\-]{20,400}")),
    ("openai_key", re.compile(
        r"(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,400}")),
    ("stripe_key", re.compile(r"(?<![A-Za-z0-9_])[sr]k_(?:live|test)_[A-Za-z0-9]{16,200}")),
    ("aws_access_key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("github_token", re.compile(
        r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})")),
    ("slack_token", re.compile(r"(?<![A-Za-z0-9])xox[abposr]-[A-Za-z0-9-]{10,255}")),
    ("google_api_key", re.compile(r"(?<![A-Za-z0-9_])AIza[0-9A-Za-z_\-]{35}")),
    ("huggingface_token", re.compile(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{30,100}")),
    ("jwt", re.compile(
        r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,2000}\.eyJ[A-Za-z0-9_-]{8,4000}"
        r"\.[A-Za-z0-9_-]{8,2000}")),
]

# user:password inside a URL. Only the credential pair is replaced.
_URL_CRED = re.compile(r"(?<=://)[^\s:/@\[\]]{1,64}:[^\s@/\[\]]{1,128}(?=@)")

# A long token-like value right after a secret-bearing key name or a Bearer scheme.
_CONTEXT = re.compile(
    r"(?i)(?P<key>(?:api[_-]?key|apikey|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token"
    r"|refresh[_-]?token|client[_-]?secret|private[_-]?key|session[_-]?token|token)"
    r"[\"']?\s{0,3}[:=]\s{0,3}[\"']?|\bbearer\s{1,3})"
    r"(?P<val>[A-Za-z0-9_\-+/=.~]{20,500})")

# password-like keys. The value is a quoted string or the rest of the line (bounded).
_PASSWORD = re.compile(
    r"(?i)(?P<key>(?<![A-Za-z])[\"']?(?:password|passwd|passphrase|pass[_-]?code)[\"']?"
    r"\s{0,3}[:=]\s{0,3})"
    r"(?P<val>\"[^\"\n]{1,200}\"|'[^'\n]{1,200}'|[^\s\n][^\n]{0,119})")
_PWD = re.compile(r"(?P<key>(?<![A-Za-z])pwd=)(?P<val>[^\s&\"'#]{3,120})")   # lower-case only
_PIN = re.compile(r"(?P<key>(?:Identity Protection PIN|IP PIN|(?<![A-Za-z])PIN)"
                  r"\s{0,3}(?:is|:|=|#)?\s{0,3})(?P<val>\d{4,8})(?!\d)")
_PASSWORD_NOT_SECRET = {"", "none", "null", "str", "string", "true", "false", "***", "****",
                        "password", "your_password", "<password>", "..."}

# Card numbers: contiguous 13-19 digits, or 4-4-4-x / 4-6-5 groups with one separator.
_CARD = re.compile(
    r"(?<![\d.\-/])(?:\d{13,19}|\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}|\d{4}([ -])\d{6}\2\d{5})"
    r"(?![\d\-/]|\.\d)")
_SSN = re.compile(r"(?<![\d\-/])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d\-/])")
_SSN_CONTEXT = re.compile(
    r"(?i)(?P<key>\b(?:SSN|social security(?: number| no\.?| #)?)\s{0,3}[:#]?\s{0,3})"
    r"(?P<val>\d{9}|\d{3} \d{2} \d{4})(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_brand_ok(d: str) -> bool:
    n = len(d)
    if d[0] == "4":
        return n in (13, 16, 19)
    if d[:2] in ("34", "37"):
        return n == 15
    if "51" <= d[:2] <= "55" or "2221" <= d[:4] <= "2720":
        return n == 16
    if d.startswith("6011") or d.startswith("65") or "644" <= d[:3] <= "649":
        return n in (16, 19)
    if "3528" <= d[:4] <= "3589":
        return n in (16, 19)
    return False


def _has_digit_and_letter(v: str) -> bool:
    return any(c.isdigit() for c in v) and any(c.isalpha() for c in v)


def redact(text: str):
    """-> (redacted_text, Counter{kind: n}). Never returns or logs a matched secret."""
    counts: collections.Counter = collections.Counter()
    if not text:
        return text, counts

    for kind, rx in _SHAPES:
        def _sub(m, kind=kind):
            counts[kind] += 1
            return PLACEHOLDER.format(kind)
        text = rx.sub(_sub, text)

    def _url(m):
        counts["url_credentials"] += 1
        return PLACEHOLDER.format("url_credentials")
    text = _URL_CRED.sub(_url, text)

    def _ctx(m):
        v = m.group("val")
        if not _has_digit_and_letter(v):
            return m.group(0)
        counts["context_secret"] += 1
        return m.group("key") + PLACEHOLDER.format("context_secret")
    text = _CONTEXT.sub(_ctx, text)

    def _pw(m):
        v = m.group("val")
        bare = v.strip().strip("\"'").strip().rstrip(",;").strip()
        if (bare.lower() in _PASSWORD_NOT_SECRET or bare.startswith("[REDACTED")
                or bare.startswith(("<", "{", "$", "os.", "getenv", "env[", "process.env"))):
            return m.group(0)
        counts["password"] += 1
        return m.group("key") + PLACEHOLDER.format("password")
    text = _PASSWORD.sub(_pw, text)
    text = _PWD.sub(_pw, text)

    def _pin(m):
        counts["pin"] += 1
        return m.group("key") + PLACEHOLDER.format("pin")
    text = _PIN.sub(_pin, text)

    def _card(m):
        d = re.sub(r"[ -]", "", m.group(0))
        if not (13 <= len(d) <= 19 and _card_brand_ok(d) and _luhn_ok(d)):
            return m.group(0)
        counts["card_number"] += 1
        return PLACEHOLDER.format("card_number")
    text = _CARD.sub(_card, text)

    def _ssn(m):
        counts["ssn"] += 1
        return PLACEHOLDER.format("ssn")
    text = _SSN.sub(_ssn, text)

    def _ssn_ctx(m):
        counts["ssn"] += 1
        return m.group("key") + PLACEHOLDER.format("ssn")
    text = _SSN_CONTEXT.sub(_ssn_ctx, text)
    return text, counts


def redact_rows(rows) -> collections.Counter:
    """Redact every row's text in place. Each row accumulates its own counts in
    ``row.redactions`` so a row redacted early (before a dedupe comparison) and again at
    write time is counted once. Returns the counts this call added."""
    added: collections.Counter = collections.Counter()
    for r in rows:
        new, c = redact(r.text)
        if c:
            r.text = new
            r.redactions = collections.Counter(r.redactions or {}) + c
            added += c
    return added


def row_counts(rows) -> collections.Counter:
    total: collections.Counter = collections.Counter()
    for r in rows:
        if r.redactions:
            total.update(r.redactions)
    return total
