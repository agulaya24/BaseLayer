"""Pasted terminal sessions (docs/core/TURN_CONTRACT.md, section 2: structural paste signals).

The structural paste score reads one blank-line-delimited segment at a time and scores
prose features. A pasted terminal session defeats it: most of its segments are long runs
of box-drawing frames, gutter-numbered source lines and error records with none of the
signals the score counts, so a real 133K-char pasted session was stored mostly as the
subject's own typing. Every fixture here is synthetic.
"""
import pytest

from baselayer import voice as V
import baselayer.recovered_import as RI
from tests.test_recovered_import import make_db, turns, env, db_import  # noqa: F401

BS = chr(92)
ESC_BAR = BS + "u2502"            # a box-drawing bar as literal escape text, as a DB copy stores it
ESC_RULE = (BS + "u2500") * 18


def rich_traceback(escaped: bool) -> str:
    bar = ESC_BAR if escaped else "\u2502"
    rule = ESC_RULE if escaped else "\u2500" * 18
    lines = [f"{bar} C:/Users/someone/AppData/Local/Programs/Python/Lib/site-packages/widgets/screen.py:1345 in _refresh"]
    for n in range(1340, 1352):
        lines.append(f"{bar}   {n} {bar}   {bar}   hidden, shown = self._compositor.reflow(self, size)")
        lines.append(f"                    {bar}")
    lines.append(f"{bar} {rule} locals {rule}")
    lines.append(f"{bar} {bar}  error = AttributeError(\"'NoneType' object has no attribute 'height'\") {bar}")
    lines.append(f"{bar} {bar} scroll = False {bar}")
    return "\n".join(lines)


POWERSHELL = "\n".join([
    "PS C:\\work\\proj> python dashboard.py 2> errors.log",
    "PS C:\\work\\proj> cat errors.log",
    "At line:1 char:1",
    "+ python dashboard.py 2> errors.log",
    "+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    "    + CategoryInfo          : NotSpecified: (:String) [], RemoteException",
    "    + FullyQualifiedErrorId : NativeCommandError",
])

PY_TRACE = "\n".join([
    "Traceback (most recent call last):",
    '  File "/srv/app/run.py", line 12, in <module>',
    "    main()",
    '  File "/srv/app/run.py", line 8, in main',
    "    load(cfg)",
    "KeyError: 'name'",
])

GIT_OUT = "\n".join([
    "On branch feature-x",
    "Changes not staged for commit:",
    "        modified:   src/app/core.py",
    "        modified:   src/app/util.py",
    "        new file:   tests/test_core.py",
    " 3 files changed, 40 insertions(+), 2 deletions(-)",
])

OWN = ("ok so the dashboard keeps crashing when i open it, i think its the focus bar "
       "widget but im not sure, can you look at why and tell me what to change")


def classes(text):
    cls = V.classify_subject_text(text, "", V.VoiceSettings())
    return [(text[s.start:s.end], s.voice_class, s.detector) for s in cls.segments]


@pytest.mark.parametrize("block", [rich_traceback(True), rich_traceback(False), POWERSHELL,
                                   PY_TRACE, GIT_OUT])
def test_terminal_block_is_pasted_terminal(block):
    got = classes(block)
    assert [(c, d) for _, c, d in got] == [("pasted", V.D_PASTE_TERMINAL)], got


def test_own_framing_survives_next_to_a_terminal_block():
    text = OWN + "\n\n" + rich_traceback(True) + "\n\n" + "thoughts on what broke?"
    got = classes(text)
    assert got[0][1] == "own_typed" and got[0][0].startswith("ok so the dashboard")
    assert ("pasted", V.D_PASTE_TERMINAL) in [(c, d) for _, c, d in got]
    assert got[-1][1] == "own_typed" and "thoughts on what broke" in got[-1][0]


@pytest.mark.parametrize("own", [
    OWN,
    "look at config.py:320 and batch_extract.py:214, both branch on the source name",
    "three things:\n1. rerun the import\n2. check the counts\n3. write the report",
    "the file is at C:\\Users\\someone\\projects\\notes.md can you read it",
    "- keep the old spec\n- build the new one in a fresh directory\n- compare them blind",
    "i ran it and got KeyError: 'name' at the end, is that from our code or the plugin",
])
def test_ordinary_typing_is_not_terminal(own):
    got = classes(own)
    assert all(d != V.D_PASTE_TERMINAL for _, _, d in got), got


def test_db_copy_terminal_paste_is_pasted(env):
    text = OWN + "\n" + POWERSHELL + "\n" + rich_traceback(True)
    db = make_db(env.tmp / "a.db", {"s-t": [("user", text), ("assistant", "Looking.")]})
    db_import(env, db)
    rows = [r for r in turns(env.conn, "dbcopy_s-t") if r["speaker"] == "subject"]
    own = "".join(r["text"] for r in rows if r["voice_class"].startswith("own_"))
    assert OWN in own                      # the framing line, typed on the line above the paste
    assert len(own) < len(OWN) + 5, rows   # and nothing of the terminal session
    assert any(r["detector"] == V.D_PASTE_TERMINAL for r in rows)


def test_prose_line_glued_to_a_terminal_block_stays_own():
    got = classes(OWN + "\n" + PY_TRACE)
    assert got[0] == (OWN + "\n", "own_typed", None), got
    assert got[1][1:] == ("pasted", V.D_PASTE_TERMINAL)


def test_long_sentence_with_a_frame_drawn_across_its_end_stays_own():
    bar = "│"
    typed = ("what would be the right breakdown there, it does not need to be twenty and ten, "
             "what would be the right way to go about it for several timeframe lengths")
    text = typed + f"  {bar}  {bar}\n{bar}  {bar}\n{bar}  {bar} more"
    got = classes(text)
    own = "".join(t for t, c, _ in got if c.startswith("own_"))
    assert typed in own, got


# An ANSI escape marks terminal output; a coloured line that reads as prose is not typed text.
ANSI_TYPED = "here is what the build printed for me this morning"
ANSI_COLOURED = "\x1b[32mAll of the tests in the suite passed on the first run today\x1b[0m"


def test_ansi_coloured_prose_line_is_pasted_terminal():
    segs = V.classify_subject_text(ANSI_COLOURED).segments
    assert [(s.voice_class, s.detector) for s in segs] == [("pasted", V.D_PASTE_TERMINAL)]


def test_typed_line_above_ansi_output_stays_own():
    text = ANSI_TYPED + "\n" + ANSI_COLOURED
    segs = V.classify_subject_text(text).segments
    assert [(s.voice_class, s.detector) for s in segs] == [
        ("own_typed", None), ("pasted", V.D_PASTE_TERMINAL)]
    assert text[segs[0].start:segs[0].end].strip() == ANSI_TYPED
