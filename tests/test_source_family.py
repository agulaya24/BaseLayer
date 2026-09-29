"""Claude Code session shape across the sources that carry it.

Database copies of older Claude Code sessions (``claude_code_db_copy``) and Claude Desktop
agent-mode sessions (``claude_desktop_agent``) are Claude Code sessions: a subject
directing an agent through tool calls. Recovered raw transcripts already import as
``claude_code``. Extraction and config code that branched on ``source == "claude_code"``
sent the other two down the generic chat path (500-char chunk overlap, no project
abstraction of assistant text, personal scope, the generic fact ceiling). Prompt history
(``claude_code_history``) has no session shape (prompts only, no assistant turns) and stays
out, as do ChatGPT, Claude.ai and meetings.
"""
import re
import sys
from pathlib import Path

import pytest

from baselayer import config as C
import baselayer.extract_facts as ef

FAMILY = ["claude_code", "claude_code_db_copy", "claude_desktop_agent"]
OUTSIDE = ["chatgpt", "claude_web", "meeting", "claude_code_history", "text_file"]


@pytest.mark.parametrize("src", FAMILY)
def test_family_members_have_claude_code_shape(src):
    assert C.is_claude_code_source(src)
    assert C.SCOPE_SOURCE_MAPPING.get(src, C.DEFAULT_SCOPE) == "project"
    assert ef._turn_noncitable_transform(src) is ef._abstract_noncitable_project_text
    assert ef._get_extraction_caps(10, source=src) == ef._get_extraction_caps(10, source="claude_code")


@pytest.mark.parametrize("src", OUTSIDE)
def test_other_sources_fall_through(src):
    assert not C.is_claude_code_source(src)
    assert C.SCOPE_SOURCE_MAPPING.get(src, C.DEFAULT_SCOPE) != "project"
    assert ef._turn_noncitable_transform(src) is not ef._abstract_noncitable_project_text


def test_family_ceiling_applies_with_the_dynamic_cap(monkeypatch):
    monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
    big = 10_000_000
    cc = ef._get_extraction_caps(10, big, source="claude_code")["max_facts"]
    for src in FAMILY:
        assert ef._get_extraction_caps(10, big, source=src)["max_facts"] == cc
    assert ef._get_extraction_caps(10, big, source="chatgpt")["max_facts"] != cc


def _seed(conn):
    from baselayer.turns import TurnRow, write_conversation
    for cid, src in [("c-cc", "claude_code"), ("c-db", "claude_code_db_copy"),
                     ("c-dt", "claude_desktop_agent"), ("c-h", "claude_code_history"),
                     ("c-g", "chatgpt")]:
        write_conversation(conn, conversation_id=cid, source=src, content_hash=cid,
                           rows=[TurnRow(ordinal=0, speaker="subject", voice_class="own_typed",
                                         text="please move the backup to sunday night", basis="source:role")])
    conn.commit()


def test_source_filter_claude_code_selects_the_family(temp_db):
    conn, _ = temp_db
    _seed(conn)
    got = {r["id"] for r in ef.get_conversations_to_process(conn, source_filter="claude_code",
                                                         turn_mode=True)}
    assert got == {"c-cc", "c-db", "c-dt"}
    got = {r["id"] for r in ef.get_conversations_to_process(conn, source_filter="claude_code_db_copy",
                                                         turn_mode=True)}
    assert got == {"c-db"}
    legacy = {r["id"] for r in ef.get_conversations_to_process(conn, source_filter="claude_code",
                                                            turn_mode=False)}
    assert legacy <= {"c-cc", "c-db", "c-dt"}


@pytest.mark.parametrize("src", ["claude_code_db_copy", "claude_desktop_agent",
                                 "claude_code_history", "meeting"])
def test_extract_cli_accepts_the_stored_source_names(src, monkeypatch):
    import baselayer.cli as cli
    seen = {}
    monkeypatch.setattr(cli, "cmd_extract", lambda args: seen.setdefault("src", args.source))
    monkeypatch.setattr(sys, "argv", ["baselayer", "extract", "--source", src])
    cli.main()
    assert seen["src"] == src


def test_no_bare_claude_code_equality_left_in_extraction_paths():
    """Static backstop: a new branch on the literal would silently exclude the family."""
    src = Path(C.__file__).parent
    pat = re.compile(r"""(==|!=)\s*["']claude_code["']|["']claude_code["']\s*(==|!=)""")
    hits = []
    for name in ("batch_extract.py", "extract_facts.py", "config.py", "pilot.py"):
        for i, line in enumerate((src / name).read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{name}:{i}: {line.strip()}")
    assert hits == []
