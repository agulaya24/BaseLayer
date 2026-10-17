"""Recall pass for `paste:code_or_machine` (TURN_CONTRACT.md, section 2).

The first version of the rule was built for precision and left several shapes of code and
machine output as the subject's own words: comment lines at the edge of a code block,
compiler and runtime messages worded in English, TeX build-log residue, chat-client
headers (a name and a clock time), coding-agent status lines, and a few command and
assignment shapes. Each case below is a synthetic fixture in one of those shapes, with a
prose line of the same surface shape that must stay own. No fixture is corpus text.
"""
import pytest

from baselayer import voice as V

LEAD = "ok so the build keeps failing on the second step, not sure why"
TAIL = "can you tell me what that means and what i should change"


def classes(text, **kw):
    cls = V.classify_subject_text(text, "", V.VoiceSettings(**kw))
    return [(text[s.start:s.end], s.voice_class, s.detector) for s in cls.segments]


def moved_text(text, **kw):
    return "".join(t for t, _, d in classes(text, **kw) if d == V.D_PASTE_CODE_MACHINE)


def own_text(text, **kw):
    return "".join(t for t, c, _ in classes(text, **kw) if c in V.CITABLE_VOICE_CLASSES)


# ---- whole lines that are machine output on their own --------------------------------

MACHINE_LINES = [
    # compiler / runtime messages worded in English, anchored on a position or identifier
    "Undeclared identifier: rowCount at 12:7",
    "No such function: Series.smooth at 4:10",
    "values are not used inside Helper{methodName='draw'} call at 30:14",
    "Only constants allowed here: fillMode CL argument 'shade' at 18:3",
    "error: cannot find symbol 'totalRows'",
    "TypeError: cannot read properties of undefined (reading 'length')",
    "fatal: not a git repository (or any of the parent directories): .git",
    # TeX build-log residue
    "Overfull \\hbox (12.3pt too wide) in paragraph at lines 40--41",
    "[]\\T1/lmr/m/n/10 (-20) Example|",
    "\\T1/lmtt/m/n/9 out/run_<name>.json\\T1/lmr/m/n/9 (+20) . The next step is in",
    "(./chapter2.tex",
    "LaTeX Warning: Reference `fig:x' on page 3 undefined on input line 88.",
    # chat-client headers: a display name or handle and a clock time, nothing else
    "Jordan Lee   3:12 PM",
    "night_owl \u2014 9:05 AM",
    # coding-agent status lines
    "\u273b Brewed for 12s",
    "\u273b Baked for 38s \u00b7 1 shell still running",
    "\u25cf Read 4 files (ctrl+o to expand)",
    "     \u2026 +12 lines (ctrl+o to expand)",
    # command, data and assignment shapes the first version missed
    "eval $cfgvar",
    '"content": (',
    # keyword arguments whose quoted labels make half the tokens plain words
    "size = input.int(5, 'Size', minval = 1, inline = 'size', group = 'Layout')",
    # round 2 (shapes from the held-out read of round 1)
    "Package graphics-base Info: Using driver on input line 12.",
    "(pdftex.def) Requested size: 120.5pt x 80.2pt.",
    "    event Moved(address indexed from, address indexed to, uint256 amount);",
    "out\\reports\\daily_summary.csv",
    "    --frame-limit INT",
    "Error on line 7 of deck: Could not find card \"Some Card Name\". (Some Card Name)",
    "if long and not na(pv) and pv > lvl_high and n - lvl_idx > 3",
    "                    .isDisabled",
    "    //Section header inside a script",
]


@pytest.mark.parametrize("line", MACHINE_LINES)
def test_machine_line_between_prose_is_moved(line):
    text = LEAD + "\n\n" + line + "\n\n" + TAIL
    assert moved_text(text, detect_code_machine=False) == ""
    assert moved_text(text).strip() == line.strip(), classes(text)
    assert LEAD in own_text(text) and TAIL in own_text(text)


# ---- comment lines join the code they sit in -----------------------------------------

@pytest.mark.parametrize("block", [
    "x = compute(a)\n// strip the unused rows\ny = keep(x)",
    "total = rows.sum()\n// done with the totals",
    "# load the rows\nrows = fetch(src)",
    "if ready():\n    run()\n# fall through to the retry path",
    "/* old version below */\nvar count = 0;",
])
def test_comment_line_touching_code_moves_with_it(block):
    text = LEAD + "\n\n" + block + "\n\n" + TAIL
    assert moved_text(text).strip() == block.strip(), classes(text)


@pytest.mark.parametrize("text", [
    # a markdown heading on its own, and one separated from code by a blank line
    LEAD + "\n\n# my notes for today\n\n" + TAIL,
    LEAD + "\n\n## Results\n\n" + TAIL,
    # a comment-looking line with no code next to it
    LEAD + "\n// not sure about this part\n" + TAIL,
])
def test_comment_shaped_line_with_no_code_stays_own(text):
    assert moved_text(text) == "", classes(text)


def test_heading_above_a_blank_line_is_not_pulled_into_the_code():
    text = LEAD + "\n\n## Output\n\nx = compute(a)\ny = keep(x)\n\n" + TAIL
    assert "## Output" not in moved_text(text)
    assert "## Output" in own_text(text)


# ---- menu chrome ---------------------------------------------------------------------

def test_a_run_of_menu_words_is_chrome():
    text = LEAD + "\n\nReply\nShare\nReport\n\n" + TAIL
    assert moved_text(text).split() == ["Reply", "Share", "Report"], classes(text)


def test_menu_words_separated_by_blank_lines_and_counts_are_chrome():
    text = LEAD + "\n\nUpvote\n12\n\nDownvote\n\nReply\n\nShare\n\n" + TAIL
    moved = [t for t, _, d in classes(text) if d == V.D_PASTE_CODE_MACHINE]
    assert " ".join(moved).split() == ["Upvote", "12", "Downvote", "Reply", "Share"], classes(text)


def test_a_vote_count_between_menu_words_is_chrome():
    text = LEAD + "\n\nUpvote\n\n14\n\nDownvote\n\n" + TAIL
    moved = [t for t, _, d in classes(text) if d == V.D_PASTE_CODE_MACHINE]
    assert " ".join(moved).split() == ["Upvote", "14", "Downvote"], classes(text)


def test_a_conditional_on_a_method_call_is_code():
    block = "// skip the empty case\nif frame.last and showCount > 0 and row_list.size() > 0\n    draw(rows)"
    text = LEAD + "\n\n" + block + "\n\n" + TAIL
    assert moved_text(text).strip() == block, classes(text)


def test_a_single_menu_word_stays_own():
    text = LEAD + "\n\nShare\n\n" + TAIL
    assert moved_text(text) == ""


# ---- prose of the same surface shapes stays own --------------------------------------

@pytest.mark.parametrize("line", [
    "i got an error running it at 10:30",
    "Warning: dont trade the open today",
    "error on my side, i sent the wrong file",
    "call at 4:30 with the team",
    "Meeting at 12:15 PM",
    "entered 2 calls at 10:15 AM",
    "Mar 4 2:10 PM",
    "6:37 entered call at 1.89, out at 1.64",
    "the overfull box warning is fine, ignore it",
    "eval is the part i care about",
    "Done",
    "-- what can i send it, if not the model",
    "Share the link with them when its ready",
    "if it breaks > 650 then i enter",
    "if myData > 5 we keep it",
    "--top k makes sense to me",
    "-- yes",
    "    # this is where i got stuck",
    "Error on my end, i will resend it",
    "the doc ends with (see the appendix);",
])
def test_prose_of_the_same_shape_is_not_moved(line):
    text = LEAD + "\n" + line + "\n" + TAIL
    assert moved_text(text) == "", classes(text)


def test_switch_off_leaves_the_new_shapes_own():
    text = LEAD + "\n\nUndeclared identifier: rowCount at 12:7\n\n" + TAIL
    assert moved_text(text, detect_code_machine=False) == ""
    assert "rowCount" in own_text(text, detect_code_machine=False)
    assert "rowCount" in moved_text(text)
