r"""Allow-list context gate for a `claude -p` child, independent of which model answers.

A context probe asks the actual child what is in its context and refuses the run unless the
answer is clean. Earlier gates failed in two directions, and both depended on the model:

  * refusing on ANY heading. Claude Code injects fixed platform blocks into every subscription
    child, even under `--safe-mode` and even with `--system-prompt` replacing the default prompt
    (an identity line, "# Environment", "# Advisor Tool", "# userEmail", a git-attribution line;
    "# Harness", "# Session-specific guidance" and "# Context management" under the default
    prompt). Whether a child LISTS them depends on the model and the probe wording, so the
    verdict tracked verbosity, not contamination.
  * bare name markers. The account email and the cwd path carry the account owner's name, so a
    child that reports either one tripped the gate.

This gate allows exactly three things and refuses everything else:

  1. an email-address token, wherever it appears (the account email block);
  2. a Windows filesystem path, wherever it appears (the cwd, the empty MCP config path);
  3. a person in `people_named` whose `where` names the email block or a path and names no
     instruction, memory, specification, MCP or appended source.

Platform blocks are allowed by exact heading name or fixed prefix, never by pattern. Every other
heading, a non-empty `behavioural_specification` or `project_instructions`, any MCP server, and
every marker (built-in generic markers, the import config's injection canaries and the caller's
owner markers) refuses. An answer that
does not parse as one JSON object refuses.

Behaviour matches the reference allow-list gate approved for the 2026-10-06 package run, with ONE
narrowing: a person whose `where` mentions a path but also an instruction, memory, specification,
MCP or appended source is refused (the reference accepted it on the word "path" alone). Nothing
here accepts an answer the reference refused.

Owner markers are configuration, never shipped: a default would publish one operator's name and
silently assume every user is that operator (see `import_config.DEFAULT_CANARIES`). An empty owner
list raises, because a gate that cannot detect a name would report clean on every answer. Injection
canaries are configuration too (`canary_strings` in the import config); with none configured the
gate simply checks no canary.

Pure functions plus `gate_child`, which writes only the probe file it is given and never prints a
secret (credential presence is asserted through `child_env`, never shown).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

GATE_ID = "context_gate/2 (allow-list: email block, paths, platform blocks; canaries from the import config)"

PROBE_PROMPT = (
    "Before anything else, report exactly what is in your context right now, without using tools. Include the system "
    "prompt, any user or project instructions, any memory, any appended system-prompt sections, any account or "
    "environment blocks, and any MCP server instructions. Reply with ONLY one JSON object: "
    "{\"people_named\": [{\"name\": \"each person's name or identifier you can see\", \"where\": \"which part of your "
    "context it appears in (for example: account email block, working-directory path, system prompt, user "
    "instructions, project instructions, memory, appended section, MCP instructions)\"}], "
    "\"email_addresses\": [every email address you can see], "
    "\"headings\": [the first heading or first line of every instructions file, memory file, appended system-prompt "
    "section, specification or operating guide in your context, verbatim; empty list if none], "
    "\"behavioural_specification\": \"the first heading of any specification or operating guide of a person, or empty\", "
    "\"project_instructions\": \"the first line of any project or user instructions, or empty\", "
    "\"mcp_servers\": [names], \"cwd\": \"your working directory\"}")

# Claude Code's own section headings (exact names, case-insensitive, leading '#' ignored) and its fixed
# opening / attribution lines (matched by their fixed prefixes). Nothing else.
PLATFORM_HEADINGS = frozenset({"environment", "advisor tool", "harness", "session-specific guidance",
                               "context management", "useremail"})
PLATFORM_PREFIXES = ("you are a claude agent, built on anthropic's claude agent sdk",
                     "you are claude code, anthropic's official cli",
                     "attribution for git commits and pull requests you create from here on")

# Generic markers: the served specification, a specification index, project bootstrap and memory index
# headings. No person's name and no injection canary: names come from the caller, canaries from the import config.
BUILTIN_MARKERS = ("personal operating guide", "operating guide", "specification index", "session bootstrap",
                   "memory index", "base layer", "baselayer")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Windows drive paths, plain or JSON-escaped. POSIX paths are NOT stripped: doing so would accept more than the
# reference gate does (a widening), which is the operator's decision, not this module's.
WIN_PATH_RE = re.compile(r"[A-Za-z]:(?:\\\\|\\|/)[^\s\"'`,;\]\[{}]*")
WHERE_OK = re.compile(r"e-?mail|path|director|cwd|folder", re.I)
WHERE_DENY = re.compile(r"instruction|claude\.md|memory|specification|operating guide|mcp|appended", re.I)


class GateConfigError(ValueError):
    """The gate was configured so that it could not refuse (for example, no owner markers)."""


def is_platform_block(heading) -> bool:
    s = str(heading).strip().lstrip("#").strip().lower()
    return s in PLATFORM_HEADINGS or any(s.startswith(p) for p in PLATFORM_PREFIXES)


def parse_answer(text: str):
    """One JSON object from the answer: bare, fenced, or the outermost {...}. None when it does not parse."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:  # noqa: BLE001
                return None
    return None


def strip_allowed(text: str) -> str:
    text = EMAIL_RE.sub(" <EMAIL> ", text)
    return WIN_PATH_RE.sub(" <PATH> ", text)


def _where_allowed(where: str) -> bool:
    if not WHERE_OK.search(where):
        return False
    return not WHERE_DENY.search(strip_allowed(where))


def _normalise_markers(owner_markers, canaries=()) -> list[str]:
    if isinstance(owner_markers, str):
        owner_markers = [owner_markers]
    owner = [str(m).strip().lower() for m in (owner_markers or []) if str(m).strip()]
    if not owner:
        raise GateConfigError("context_gate: owner_markers is empty, so no name could ever be detected; pass the "
                              "account owner's name parts (kept out of the repo)")
    cans = [str(c).strip().lower() for c in (canaries or ()) if str(c).strip()]
    return list(dict.fromkeys([*BUILTIN_MARKERS, *cans, *owner]))


def evaluate(answer: str | None, owner_markers, error: str | None = None, canaries=()) -> dict:
    """Pure function of the probe answer. Returns {"clean", "reasons", "allowed_channels", ...}.
    `owner_markers`: the account owner's name parts and private terms, lower-cased on use; must be non-empty.
    `canaries`: injection canaries to refuse on (gate_child passes the import config's); may be empty."""
    markers = _normalise_markers(owner_markers, canaries)
    reasons: list[str] = []
    allowed: list[dict] = []
    out = {"gate": GATE_ID, "markers_checked": len(markers)}
    if error:
        reasons.append(f"probe error: {str(error)[:200]}")
    d = parse_answer(answer or "")
    if not isinstance(d, dict):
        reasons.append("probe answer did not parse as one JSON object")
        return {**out, "clean": False, "reasons": reasons, "allowed_channels": allowed}

    emails = [e for e in (d.get("email_addresses") or []) if isinstance(e, str)]
    if emails:
        allowed.append({"channel": "account email block", "count": len(emails)})

    v = d.get("headings")
    items = v if isinstance(v, list) else ([] if v in (None, "") else [v])
    other = [h for h in items if not is_platform_block(h)]
    if items and not other:
        allowed.append({"channel": "Claude Code platform blocks", "headings": [str(h)[:80] for h in items]})
    if other:
        reasons.append(f"headings not empty: {len(other)} non-platform item(s): {[str(h)[:60] for h in other]}")

    for k in ("behavioural_specification", "project_instructions"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            reasons.append(f"{k} not empty")
        elif v not in (None, "") and not isinstance(v, str):
            reasons.append(f"{k} has an unexpected value type")
    if d.get("mcp_servers") not in (None, []):
        reasons.append(f"mcp_servers not empty: {d.get('mcp_servers')}")

    kept_people, allowed_names = [], []
    for p in d.get("people_named") or []:
        if isinstance(p, str):
            p = {"name": p, "where": ""}
        if not isinstance(p, dict):
            reasons.append("people_named entry of unexpected type")
            continue
        where = str(p.get("where") or "")
        if _where_allowed(where):
            allowed.append({"channel": "person named from the email block or a path", "where": where[:120]})
            allowed_names.append(str(p.get("name") or ""))
        else:
            kept_people.append(p)
            reasons.append(f"person named from a non-allowed part of the context: where={where[:80]!r}")

    rest = dict(d)
    rest.pop("people_named", None)
    rest.pop("email_addresses", None)
    rest["people_named_not_allowed"] = kept_people
    scan = strip_allowed(json.dumps(rest, ensure_ascii=False)).lower()
    hits = [m for m in markers if m in scan]
    if hits:
        reasons.append(f"markers present outside the allowed items: {len(hits)}")
    # prose around the JSON object: markers the parsed scan could not see, excluding allowed people's names
    raw_rest = strip_allowed(answer or "").lower()
    names = " ".join(allowed_names).lower()
    raw_hits = [m for m in markers if m in raw_rest and m not in hits and m not in names]
    if raw_hits:
        reasons.append(f"markers in the raw answer outside the allowed items: {len(raw_hits)}")
    # marker strings are not stored (owner markers are private); only counts
    extra = sorted(set(d) - {"people_named", "email_addresses", "headings", "behavioural_specification",
                             "project_instructions", "mcp_servers", "cwd"})
    return {**out, "clean": not reasons, "reasons": reasons, "allowed_channels": allowed, "extra_keys": extra}


def gate_child(backend, out_path: Path, label: str, owner_markers, canaries=None) -> dict:
    """Probe the ACTUAL child (same command, env and cwd as the measured calls), store the record, refuse unless clean.
    `backend` needs `complete(prompt)` returning an object with `.text`, `.error`, `.raw` (the package's
    ClaudeCliRater and ClaudeCliBackend both qualify). `canaries` defaults to the import config's
    `canary_strings`, read now. Raises SystemExit on a refusal; nothing is measured."""
    from baselayer.verification.raters import child_env
    if canaries is None:
        from baselayer.import_config import configured_canaries
        canaries = configured_canaries()
    _normalise_markers(owner_markers, canaries)  # config error before any model call
    child_env()  # raises if a credential is still present (asserted, never printed)
    r = backend.complete(PROBE_PROMPT)
    ev = evaluate(r.text, owner_markers, r.error, canaries)
    raw = getattr(r, "raw", None) or {}
    command = backend.command() if callable(getattr(backend, "command", None)) else None
    rec = {"label": label, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "answer": r.text,
           "error": r.error, "models": raw.get("models"), "advisor": raw.get("advisor"),
           "raw_stream": raw.get("raw_stream"), "command": command, "cwd": str(getattr(backend, "cwd", "")),
           "child_env": {"ANTHROPIC_API_KEY_present": False, "ANTHROPIC_AUTH_TOKEN_present": False,
                         "BASELAYER_SPEC_INJECT": "0"},
           "evaluation": ev}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out_path)
    backend.probe = {"clean": ev["clean"], "stored": str(out_path), "gate": GATE_ID}
    if not ev["clean"]:
        raise SystemExit(f"[{label}] context probe REFUSED: {ev['reasons']}; nothing measured. Stored: {out_path}")
    return rec
