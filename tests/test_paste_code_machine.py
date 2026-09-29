"""Code and machine output inside the subject's own turns (TURN_CONTRACT.md, section 2).

Design decision: code and machine output pasted or typed inside the subject's own turn is not
their words. The structural paste score reads prose features and needs several signals at
once, and the terminal rule needs three or more terminal lines, so a short code block, a
JSON response, a config fragment or a single command line between their sentences was stored
as their own typing. `paste:code_or_machine` marks those lines at segment level; the prose
they typed around them stays own. Every fixture here is synthetic.
"""
import pytest

from baselayer import voice as V

LEAD = "ok so this function keeps returning the wrong total, i think its the loop"
TAIL = "can you tell me why it does that and what i should change"

PY_BLOCK = "\n".join([
    "def total(rows):",
    "    acc = 0",
    "    for r in rows:",
    "        acc += r.amount",
    "    return acc",
])

JS_BLOCK = "\n".join([
    "const body = await res.json();",
    "if (!body.ok) {",
    "  throw new Error(body.message);",
    "}",
])

JSON_BLOCK = "\n".join([
    "{",
    '  "status": "not_found",',
    '  "items": [1, 2, 3],',
    '  "next": null',
    "}",
])

YAML_BLOCK = "\n".join([
    "retry_limit: 3",
    "timeout_seconds: 30",
    "enabled: true",
])

XML_BLOCK = "\n".join([
    '<?xml version="1.0"?>',
    '<config name="main">',
    '  <entry key="a" value="1"/>',
    "</config>",
])

LOG_BLOCK = "\n".join([
    "12:01:07.331 INFO  worker started pid=4411",
    "12:01:09.002 ERROR request failed status=503 path=/v1/items",
])

KV_BLOCK = "user_id=42 region=west retries=3 cache=off"

JAVA_TRACE = "\n".join([
    "java.lang.IllegalStateException: queue closed",
    "    at com.example.queue.Worker.run(Worker.java:88)",
    "    at java.base/java.lang.Thread.run(Thread.java:833)",
])

URL_LINE = "https://example.org/docs/reference/v2/items?page=3"

LISTING = "\n".join([
    "README.md",
    "setup.py",
    "src/app/core.py",
])


def classes(text, **kw):
    cls = V.classify_subject_text(text, "", V.VoiceSettings(**kw))
    return [(text[s.start:s.end], s.voice_class, s.detector) for s in cls.segments]


def own_text(text, **kw):
    return "".join(t for t, c, _ in classes(text, **kw) if c in V.CITABLE_VOICE_CLASSES)


def moved_text(text, **kw):
    return "".join(t for t, _, d in classes(text, **kw) if d == V.D_PASTE_CODE_MACHINE)


NEW_BLOCKS = [PY_BLOCK, YAML_BLOCK, XML_BLOCK, LOG_BLOCK, KV_BLOCK, JAVA_TRACE, URL_LINE, LISTING]


@pytest.mark.parametrize("block", NEW_BLOCKS)
def test_block_between_paragraphs_is_code_or_machine(block):
    text = LEAD + "\n\n" + block + "\n\n" + TAIL
    assert moved_text(text, detect_code_machine=False) == ""
    assert block in own_text(text, detect_code_machine=False)   # own before this rule
    got = classes(text)
    assert [c for _, c, _ in got] == ["own_typed", "pasted", "own_typed"], got
    assert got[1][2] == V.D_PASTE_CODE_MACHINE
    assert got[1][0].strip() == block.strip()


@pytest.mark.parametrize("block", [JS_BLOCK, JSON_BLOCK])
def test_a_block_the_structural_score_already_takes_keeps_that_detector(block):
    text = LEAD + "\n\n" + block + "\n\n" + TAIL
    got = classes(text)
    assert [(c, d) for _, c, d in got][1] == ("pasted", V.D_PASTE_STRUCTURAL)


@pytest.mark.parametrize("block", [PY_BLOCK, JS_BLOCK, JSON_BLOCK, LOG_BLOCK])
def test_framing_lines_glued_to_the_block_stay_own(block):
    text = LEAD + "\n" + block + "\n" + TAIL
    own = own_text(text)
    assert LEAD in own and TAIL in own
    assert block.strip() in moved_text(text)


def test_single_code_line_between_typed_lines_moves():
    text = "the loop header looks like this\nfor j = i + 1 to n\nshould it start at i instead"
    assert moved_text(text).strip() == "for j = i + 1 to n"
    own = own_text(text)
    assert "the loop header looks like this" in own and "should it start at i instead" in own


def test_fenced_block_across_blank_lines_is_one_paste():
    fenced = "```python\nx = load()\n\nthis line reads like a sentence inside the fence\n\ny = x + 1\n```"
    text = LEAD + "\n\n" + fenced + "\n\n" + TAIL
    assert moved_text(text).strip() == fenced
    own = own_text(text)
    assert LEAD in own and TAIL in own and "sentence inside" not in own


def test_unclosed_fence_stops_at_the_paragraph():
    text = "```\nx = load()\ny = x + 1\n\n" + TAIL + "\n\nand also " + LEAD
    own = own_text(text)
    assert TAIL in own and LEAD in own
    assert "x = load()" in moved_text(text)


def test_inline_fence_on_one_line_does_not_open_a_block():
    text = "use ```x = 1``` there\n\n" + TAIL
    assert TAIL in own_text(text)


@pytest.mark.parametrize("line", [
    "note: the second chart is off by a day",
    "ok so: i want the totals by week not by month",
    "if this works (it should) we ship it tomorrow",
    "import the data again tomorrow and rerun the check",
    "let me know when the run finishes",
    "return it to the queue when its done",
    "from now on use the smaller model for this",
    "for the record i think the first version was better",
    "9:15 out at 2.10",
    "11:42 out of 3 at 1.87",
    "10:20 5m still bearish",
    "21 of 88 passed",
    "2024-03-02 09:45 bought 2 more at the open",
    "## 2.3 Work Plan",
    "check https://example.org/a/b its the one i meant",
    "what does x = 5 mean in that output?",
    "2 failed attempts today, both on the open",
    # a sentence quoting a record: six or more plain words making up half the tokens
    "so like this example.org has a record with content v=abc1; p=none; rua=mailto:x@example.org.",
    # an English word that is also a shell command, followed by a version number
    "  source under Apache 2.0.",
])
def test_typed_prose_is_not_code_or_machine(line):
    text = LEAD + "\n" + line + "\n" + TAIL
    assert moved_text(text) == "", classes(text)


def test_switch_off_leaves_the_segment_own():
    text = LEAD + "\n\n" + PY_BLOCK + "\n\n" + TAIL
    assert moved_text(text, detect_code_machine=False) == ""
    assert PY_BLOCK in own_text(text, detect_code_machine=False)


def test_speech_sources_are_not_scanned():
    text = LEAD + "\n\n" + PY_BLOCK
    cls = V.classify_subject_text(text, "", V.VoiceSettings(), own_class="own_dictated",
                                  detect_dictation=False)
    assert all(s.detector != V.D_PASTE_CODE_MACHINE for s in cls.segments)


def test_an_existing_paste_keeps_its_detector():
    # A long pasted terminal session stays paste:terminal; the new rule only reads
    # segments the other rules left as the subject's own.
    trace = "\n".join([
        "Traceback (most recent call last):",
        '  File "/srv/app/run.py", line 12, in <module>',
        "    main()",
        '  File "/srv/app/run.py", line 8, in main',
        "KeyError: 'name'",
    ])
    got = classes(trace)
    assert [d for _, _, d in got] == [V.D_PASTE_TERMINAL]


def test_line_predicate_examples():
    assert V.is_code_or_machine_line("    acc += r.amount")
    assert V.is_code_or_machine_line('  "status": "not_found",')
    assert V.is_code_or_machine_line("https://example.org/x/y")
    assert not V.is_code_or_machine_line("ok so i think the loop is wrong here")
    assert not V.is_code_or_machine_line("8:50 out at 1.53")


def test_fences_do_not_recut_segments_other_rules_decide():
    # A greeting (+1) and a fence (+2) score a segment structural together. Cutting the
    # segment at the fence would leave the greeting below the threshold and make it own;
    # fences are read only inside segments every other rule left own.
    text = "Hello Sam,\nhere is the thing\n```\nsome code\n```"
    off = classes(text, detect_code_machine=False)
    assert [(c, d) for _, c, d in off] == [("pasted", V.D_PASTE_STRUCTURAL)]
    assert classes(text) == off


def test_a_pasted_document_keeps_its_code_lines():
    # The document pass reads the whole long turn; its claims come first, so a code line
    # inside a pasted document stays part of that document (and of the own-writing
    # re-class it is eligible for) rather than being split off.
    body = "\r\n".join(
        ["The quarterly review covers the platform migration and the staffing plan in detail."] * 12
        + ["result = migrate(accounts, batch_size=500);"]
        + ["Each workstream reports status, risks and owners to the steering group every week."] * 12)
    text = "can you summarise this for me\n" + body + "\r\n"
    assert len(text) >= V.VoiceSettings().document_split_min_chars
    dets = [d for _, _, d in classes(text)]
    assert V.D_PASTE_DOCUMENT in dets and V.D_PASTE_CODE_MACHINE not in dets
