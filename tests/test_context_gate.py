"""The allow-list context gate: model-independent verdicts, shown to fail first.

Every case is synthetic (Jane Roe, example.com, a synthetic injection canary configured through
the import config, never the package). The two "model shapes" are the measured answer
shapes of a terse child (lists no platform blocks) and a verbose child (lists every platform block,
the account email and a name from the cwd path); a gate is model-independent only if both shapes get
the same verdict, clean when nothing else is present and refused when one contaminant is added.

Fail-first: the same case table is run against four deliberately defective gates (the defects found in
the 2026-10-06 audit). Each must get at least one case wrong, so the table can tell a correct gate from
each known-broken one.
"""
import json
import re

import pytest

from baselayer.verification import context_gate as cg


@pytest.fixture(autouse=True)
def _import_config(tmp_path, monkeypatch):
    """The canary is configuration: every test here runs against an import config that sets it."""
    p = tmp_path / "import_config.json"
    p.write_text(json.dumps({"canary_strings": CANARIES}), encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(p))
    return p

OWNER = ["jane", "roe"]
CANARY = "SYNTHETIC INJECTION MARKER 9b2d"
CANARIES = [CANARY]
EMAIL = "jane.roe" + "@" + "example.com"
CWD = "C:\\Users\\Jane\\w1"
PLATFORM_ALL = ["You are a Claude agent, built on Anthropic's Claude Agent SDK.", "# Environment", "# Advisor Tool",
                "# userEmail", "Attribution for git commits and pull requests you create from here on (this replaces",
                "# Harness", "# Session-specific guidance", "# Context management"]


def ans(**kw):
    base = {"people_named": [], "email_addresses": [], "headings": [], "behavioural_specification": "",
            "project_instructions": "", "mcp_servers": [], "cwd": CWD}
    base.update(kw)
    return json.dumps(base)


TERSE = dict(email_addresses=[EMAIL])                                     # lists no platform block
VERBOSE = dict(email_addresses=[EMAIL], headings=PLATFORM_ALL,            # lists every platform block
               people_named=[{"name": "Jane Roe", "where": "account email block (userEmail)"},
                             {"name": "Jane", "where": "working-directory path (" + CWD + ")"}])

CASES = {
    # model-independence pairs: same expected verdict for both shapes
    "PASS terse clean": (ans(**TERSE), True),
    "PASS verbose clean (all platform blocks, email, name from the path)": (ans(**VERBOSE), True),
    "REFUSE terse + personal guide heading": (ans(**{**TERSE, "headings": ["# Jane Roe - Personal Operating Guide"]}), False),
    "REFUSE verbose + personal guide heading": (
        ans(**{**VERBOSE, "headings": PLATFORM_ALL + ["# Jane Roe - Personal Operating Guide"]}), False),
    "REFUSE terse + MCP server": (ans(**{**TERSE, "mcp_servers": ["notes-server"]}), False),
    "REFUSE verbose + MCP server": (ans(**{**VERBOSE, "mcp_servers": ["notes-server"]}), False),
    # structural refusals
    "REFUSE unparseable": ("I cannot tell", False),
    "REFUSE an unknown project heading with no marker in it": (ans(headings=["# Project notes"]), False),
    "REFUSE memory index heading next to platform blocks": (ans(headings=["# Harness", "# Example memory index"]), False),
    "REFUSE project bootstrap heading": (ans(headings=["# Environment", "# Example - Session Bootstrap"]), False),
    "REFUSE look-alike heading that only starts like a platform one": (ans(headings=["# Environment notes for Jane"]), False),
    "REFUSE behavioural spec field": (ans(behavioural_specification="Personal Operating Guide"), False),
    "REFUSE project instructions field": (ans(project_instructions="Notes for this repo"), False),
    "REFUSE name from the system prompt": (ans(people_named=[{"name": "Jane Roe", "where": "system prompt"}]), False),
    "REFUSE name attributed to an instructions file at a path": (
        ans(people_named=[{"name": "Jane Roe", "where": "user instructions file at " + CWD + "\\CLAUDE.md path"}]), False),
    "REFUSE specification index title in prose around the JSON": (ans() + " Base Layer: Jane's specification index", False),
    "REFUSE owner name in an extra key": (ans(notes="the user is Jane Roe, per her guide"), False),
    "REFUSE configured injection canary": (ans(notes="context opens with " + CANARY), False),
    # allowed shapes
    "PASS nothing at all": (ans(), True),
    "PASS an unrelated email only": (ans(email_addresses=["someone" + "@" + "example.org"]), True),
    "PASS an advisor tool listed in an extra key": (ans(**{**TERSE, "tools": ["advisor"]}), True),
    "PASS fenced JSON": ("```json\n" + ans(**VERBOSE) + "\n```", True),
}


@pytest.mark.parametrize("name", list(CASES))
def test_gate_case(name):
    text, want = CASES[name]
    ev = cg.evaluate(text, OWNER, canaries=CANARIES)
    assert ev["clean"] is want, (name, ev["reasons"])


def test_injection_canary_is_config_only():
    """No canary ships in the gate: unconfigured, the canary case has nothing to trip on."""
    text = CASES["REFUSE configured injection canary"][0]
    assert cg.evaluate(text, OWNER, canaries=CANARIES)["clean"] is False
    assert cg.evaluate(text, OWNER)["clean"] is True
    assert not any(CANARY.lower() in m for m in cg.BUILTIN_MARKERS)


def test_model_shapes_get_the_same_verdict():
    pairs = [("PASS terse clean", "PASS verbose clean (all platform blocks, email, name from the path)"),
             ("REFUSE terse + personal guide heading", "REFUSE verbose + personal guide heading"),
             ("REFUSE terse + MCP server", "REFUSE verbose + MCP server")]
    for a, b in pairs:
        assert (cg.evaluate(CASES[a][0], OWNER, canaries=CANARIES)["clean"]
                == cg.evaluate(CASES[b][0], OWNER, canaries=CANARIES)["clean"])


def test_empty_owner_markers_raise():
    with pytest.raises(cg.GateConfigError):
        cg.evaluate(ans(), [])
    with pytest.raises(cg.GateConfigError):
        cg.evaluate(ans(), ["  "])


def test_marker_strings_are_not_reported():
    ev = cg.evaluate(ans(notes="Jane Roe"), OWNER)
    assert ev["clean"] is False
    assert "jane" not in json.dumps(ev["reasons"]).lower()


# ------------------------------------------------------------------ fail first: the known-broken gates
def _verdicts():
    return {n: cg.evaluate(t, OWNER, canaries=CANARIES)["clean"] for n, (t, _) in CASES.items()}


def _wrong(verdicts):
    return [n for n, (_, want) in CASES.items() if verdicts[n] is not want]


def test_correct_gate_gets_every_case_right():
    assert _wrong(_verdicts()) == []


def test_fails_first_any_heading_refuses(monkeypatch):
    monkeypatch.setattr(cg, "is_platform_block", lambda h: False)
    assert "PASS verbose clean (all platform blocks, email, name from the path)" in _wrong(_verdicts())


def test_fails_first_bare_name_markers_without_email_or_path_strip(monkeypatch):
    monkeypatch.setattr(cg, "strip_allowed", lambda s: s)
    assert "PASS verbose clean (all platform blocks, email, name from the path)" in _wrong(_verdicts())


def test_fails_first_where_says_path(monkeypatch):
    monkeypatch.setattr(cg, "WHERE_DENY", re.compile(r"(?!x)x"))  # the reference gate's behaviour
    assert "REFUSE name attributed to an instructions file at a path" in _wrong(_verdicts())


def test_fails_first_canary_substring_only():
    """The shape of the package's run_probe: substring markers on the raw answer, nothing parsed. Generic markers
    only, as in the canary files those runs used (no owner name, since a bare name trips on the cwd and email)."""
    markers = [*cg.BUILTIN_MARKERS, *(c.lower() for c in CANARIES)]
    verdicts = {n: bool(t) and not any(m in t.lower() for m in markers) for n, (t, _) in CASES.items()}
    wrong = _wrong(verdicts)
    assert "REFUSE unparseable" in wrong and "REFUSE terse + MCP server" in wrong


# ------------------------------------------------------------------ gate_child
class _Reply:
    def __init__(self, text, error=None):
        self.text, self.error, self.raw = text, error, {"models": ["m"]}


class _Backend:
    def __init__(self, text):
        self.text, self.prompts, self.cwd, self.probe = text, [], CWD, None

    def complete(self, prompt):
        self.prompts.append(prompt)
        return _Reply(self.text)

    def command(self):
        return ["claude", "-p", "--safe-mode"]


def test_gate_child_passes_and_stores(tmp_path):
    be = _Backend(ans(**VERBOSE))
    rec = cg.gate_child(be, tmp_path / "probe.json", "t", OWNER)
    assert rec["evaluation"]["clean"] is True and be.probe["clean"] is True
    assert be.prompts == [cg.PROBE_PROMPT]
    assert json.loads((tmp_path / "probe.json").read_text(encoding="utf-8"))["evaluation"]["clean"] is True


def test_gate_child_refuses_and_still_stores(tmp_path):
    be = _Backend(ans(headings=["# Jane Roe - Personal Operating Guide"]))
    with pytest.raises(SystemExit):
        cg.gate_child(be, tmp_path / "probe.json", "t", OWNER)
    assert be.probe["clean"] is False and (tmp_path / "probe.json").exists()


def test_gate_child_reads_the_canary_from_the_import_config(tmp_path, monkeypatch, _import_config):
    text = ans(**{**TERSE, "notes": CANARY})
    with pytest.raises(SystemExit):
        cg.gate_child(_Backend(text), tmp_path / "probe.json", "t", OWNER)
    empty = tmp_path / "no_canary.json"
    empty.write_text(json.dumps({"canary_strings": []}), encoding="utf-8")
    monkeypatch.setenv("BASELAYER_IMPORT_CONFIG", str(empty))
    rec = cg.gate_child(_Backend(text), tmp_path / "probe2.json", "t", OWNER)  # nothing configured: no canary
    assert rec["evaluation"]["clean"] is True


def test_gate_child_config_error_before_any_call(tmp_path):
    be = _Backend(ans())
    with pytest.raises(cg.GateConfigError):
        cg.gate_child(be, tmp_path / "probe.json", "t", [])
    assert be.prompts == []
