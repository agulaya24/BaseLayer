"""
Set-aside (quarantined) chunks are STATED with every specification, but never inside its text
(design decision 2026-09-29):

- Authoring writes a gaps manifest, `coverage_gaps*.json`, beside its output, stamped with the
  run id: `baselayer run` / `author` (static layers), `distill` (trees) and
  `author-from-package` (respec layers). Each entry names the conversation, chunk key, why it
  failed (truncated / unparseable / refusal / ...), the error text, attempts and model. The
  layer text is unchanged; the frontmatter or stamp carries a pointer only.
- Every quarantined chunk is on the review backlog with WHY it failed:
  `baselayer chunks list --review`.
- A conversation with any quarantined chunk is marked partial (conversation_flags
  `extraction_partial`), not extracted: its needs_extraction mark is not cleared.

No API calls: fake clients only.
"""

import json
import sqlite3
import types

import pytest

from tests.test_chunk_ledger import (  # noqa: F401  (env is a fixture)
    FailsOn, _cli, _quarantined_corpus, _rows)
from tests.test_failed_chunks import ALL4, CONV, LLM, _objects, _setup, env  # noqa: F401
from tests.test_api_usage_record import _usage
from tests.test_artifact_stamps import (  # noqa: F401  (fixtures)
    FACTS, _distill, _make_db, _tree, author_env, no_network)


def _manifest_paths(root):
    return sorted(p for p in root.rglob("coverage_gaps*.json"))


def _ledger_with_a_quarantined_chunk(db):
    from baselayer import chunk_ledger as cl
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE IF NOT EXISTS extraction_log (conversation_id TEXT PRIMARY KEY, "
              "facts_extracted INTEGER, processed_at REAL)")
    cl.ensure_ledger(c)
    cl.upsert(c, "conv-q", ('[["conv-q:0",0,40]]', 400, 0), status="quarantined",
              attempts=3, model="claude-haiku-4-5-20251001",
              last_error="json_decode: Expecting value: line 1 column 1 (char 0) "
                         "(quarantined after 3 attempts)")
    cl.upsert(c, "conv-ok", ('[["conv-ok:0",0,40]]', 400, 0), status="done", attempts=1,
              model="claude-haiku-4-5-20251001", facts_stored=2)
    c.commit()
    c.close()


def _check_gap(m, run_id):
    assert m["run_id"] == run_id and m["count"] == 1 and m["ledger_present"] is True
    g = m["gaps"][0]
    assert g["conversation_id"] == "conv-q" and g["chunk_key"] == '[["conv-q:0",0,40]]'
    assert g["reason"] == "unparseable" and "json_decode" in g["last_error"]
    assert g["attempts"] == 3 and g["model"] == "claude-haiku-4-5-20251001"
    assert m["partial_conversations"] == ["conv-q"]


# ---------------------------------------------------------------------------
# static layers (`baselayer run --accept-gaps`, `baselayer author`)
# ---------------------------------------------------------------------------

def test_static_layers_point_to_a_gaps_manifest_and_do_not_carry_the_gaps(
        env, monkeypatch, tmp_path):
    import baselayer.author_layers as al
    _quarantined_corpus(env, monkeypatch)
    monkeypatch.setattr(al, "get_db", env.get_db)
    monkeypatch.setattr(al, "IDENTITY_LAYERS_DIR", tmp_path / "layers")
    monkeypatch.setattr(al, "COVERAGE_GAPS_ACCEPTED", True)
    text = "**M1 - Direct.** Answers first."
    out = tmp_path / "layers" / "core.md"
    al.store_layer("CORE", text, out)
    content = out.read_text(encoding="utf-8")
    head, body = content.split("## Injectable Block")
    q = [r for r in _rows(env) if r["status"] == "quarantined"][0]
    assert body.strip() == text                           # the layer text is unchanged
    assert q["block_id"] not in content and CONV not in content   # no gap listed in the layer
    fm = dict(l.split(": ", 1) for l in head.splitlines() if ": " in l)
    run_id, pointer = fm["spec_run_id"], fm["coverage_gaps_manifest"].split()[0]
    assert fm["coverage_gaps_count"].split()[0] == "1"
    assert fm["coverage_gaps_accepted"].split()[0] == "true"
    for where in (out.parent / pointer, out.parent / "history" / pointer):
        m = json.loads(where.read_text(encoding="utf-8"))
        assert m["run_id"] == run_id and m["count"] == 1 and m["accepted"] is True
        g = m["gaps"][0]
        assert (g["conversation_id"], g["block_id"]) == (CONV, q["block_id"])
        assert g["chunk_key"] == q["chunk_key"] and g["attempts"] == 3
        assert g["reason"] == "unparseable" and "unusable_response" in g["last_error"]
        assert "model" in g and m["partial_conversations"] == [CONV]


# ---------------------------------------------------------------------------
# respec path: distill and author-from-package
# ---------------------------------------------------------------------------

def test_distill_writes_the_gaps_manifest_beside_the_tree(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path, FACTS)
    _ledger_with_a_quarantined_chunk(db)
    out = tmp_path / "tree.json"
    tree = _distill(monkeypatch, db, out)
    rid = tree["stamp"]["run_id"]
    beside = tmp_path / "tree.coverage_gaps.json"
    archived = tmp_path / "data" / "distillation" / ("coverage_gaps_anchors_%s.json" % rid)
    for p in (beside, archived):
        _check_gap(json.loads(p.read_text(encoding="utf-8")), rid)


def test_distill_on_a_corpus_without_a_ledger_says_so(no_network, monkeypatch, tmp_path):
    db = _make_db(tmp_path, FACTS)
    out = tmp_path / "tree.json"
    _distill(monkeypatch, db, out)
    m = json.loads((tmp_path / "tree.coverage_gaps.json").read_text(encoding="utf-8"))
    assert m["ledger_present"] is False and m["count"] == 0 and m["gaps"] == []


def test_author_from_package_writes_the_gaps_manifest(author_env):
    from tests.test_artifact_stamps import V
    db = _make_db(author_env.tmp, FACTS)
    _ledger_with_a_quarantined_chunk(db)
    out = author_env.run(author_env.write_pkg("anchors.json", V), extra=("--db", str(db)))
    m = json.loads((out / "coverage_gaps.json").read_text(encoding="utf-8"))
    st = json.loads((out / "anchors.stamp.json").read_text(encoding="utf-8"))
    _check_gap(m, m["run_id"])
    pinned = json.loads((out / st["coverage_gaps_manifest"]).read_text(encoding="utf-8"))
    assert pinned == m and st["coverage_gaps_manifest"] != "coverage_gaps.json"
    assert st["coverage_gaps_count"] == 1 and st["coverage_gaps_run_id"] == m["run_id"]
    layer = (out / "anchors.md").read_text(encoding="utf-8")
    assert "conv-q" not in layer                         # stated beside, not inside


def test_a_resumed_author_run_leaves_each_stamp_pointing_at_its_own_manifest(author_env):
    """A resumed run reuses an authored layer and does not rewrite its stamp; the manifest that
    stamp names must still be on disk and still say what it said. The id carries no clock, so
    an unchanged ledger reproduces it, and a changed ledger shows as a different id."""
    from baselayer import chunk_ledger as cl
    from tests.test_artifact_stamps import V
    db = _make_db(author_env.tmp, FACTS)
    _ledger_with_a_quarantined_chunk(db)
    pkg = author_env.write_pkg("anchors.json", V)
    out = author_env.run(pkg, extra=("--db", str(db)))
    st = json.loads((out / "anchors.stamp.json").read_text(encoding="utf-8"))
    first = st["coverage_gaps_run_id"]
    author_env.run(pkg, extra=("--db", str(db)))          # unchanged: the same id
    assert json.loads((out / "coverage_gaps.json").read_text(encoding="utf-8"))["run_id"] == first
    c = sqlite3.connect(db)
    cl.upsert(c, "conv-q2", ('[["conv-q2:0",0,40]]', 400, 0), status="quarantined",
              attempts=3, last_error="refusal (quarantined after 3 attempts)")
    c.commit()
    c.close()
    author_env.run(pkg, extra=("--db", str(db)))          # the layer is reused, not re-stamped
    latest = json.loads((out / "coverage_gaps.json").read_text(encoding="utf-8"))
    assert latest["run_id"] != first and latest["count"] == 2
    st = json.loads((out / "anchors.stamp.json").read_text(encoding="utf-8"))
    assert st["coverage_gaps_run_id"] == first
    pinned = json.loads((out / st["coverage_gaps_manifest"]).read_text(encoding="utf-8"))
    assert pinned["run_id"] == first and pinned["count"] == 1


def test_author_from_package_without_db_says_the_ledger_was_not_read(author_env):
    from tests.test_artifact_stamps import V
    out = author_env.run(author_env.write_pkg("anchors.json", V))
    m = json.loads((out / "coverage_gaps.json").read_text(encoding="utf-8"))
    assert m["checked"] is False and m["count"] is None and "--db" in m["note"]


# ---------------------------------------------------------------------------
# every quarantined chunk on the review backlog, with WHY
# ---------------------------------------------------------------------------

class Replies:
    """Anthropic messages fake: `kind` for every chunk whose body shows Entry 0, a good reply
    otherwise."""

    def __init__(self, kind):
        self.kind = kind

    def create(self, **kw):
        import re
        from tests.test_failed_chunks import _facts_for
        prompt = kw["messages"][0]["content"]
        facts = _facts_for(prompt)
        stop, text = "end_turn", json.dumps({"facts": facts})
        if "| SUBJECT, typed]\nEntry 0" in prompt:
            if self.kind == "refusal":
                stop, text = "refusal", ""
            elif self.kind == "garbage":
                text = "Here are the facts you asked for {"
            elif self.kind == "not_an_object":
                text = json.dumps(["a", "list"])
        blocks = [types.SimpleNamespace(type="text", text=text)] if text else []
        return types.SimpleNamespace(content=blocks, stop_reason=stop, usage=_usage())


def _client(env, monkeypatch, msgs):
    monkeypatch.setattr(env.ef, "EXTRACTION_BACKEND", "anthropic")
    monkeypatch.setattr(env.ef, "_get_anthropic_client",
                        lambda: types.SimpleNamespace(messages=msgs))


@pytest.mark.parametrize("kind,why,text", [
    ("refusal", "refusal", "refusal"),
    ("garbage", "unparseable", "json_decode"),
    ("not_an_object", "unparseable", "not_an_object"),
])
def test_every_quarantined_chunk_is_listed_for_review_with_why(env, monkeypatch, capsys,
                                                               kind, why, text):
    _setup(env, monkeypatch)
    for _ in range(3):
        _client(env, monkeypatch, Replies(kind))
        try:
            env.ef.run_extraction()
        except SystemExit:
            pass
    q = [r for r in _rows(env) if r["status"] == "quarantined"]
    assert len(q) == 1 and q[0]["attempts"] == 3 and text in q[0]["last_error"]
    capsys.readouterr()
    _cli(env, monkeypatch, "chunks", "list", "--review")
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if q[0]["block_id"] in l]
    assert len(line) == 1 and why in line[0] and text in line[0] and CONV in line[0]


def test_failure_kinds():
    from baselayer import chunk_ledger as cl
    cases = {
        "max_tokens (quarantined after 3 attempts)": "truncated",
        "json_decode: Expecting value": "unparseable",
        "not_a_list": "unparseable",
        "no_text": "unparseable",
        "unusable_response": "unparseable",
        "refusal (quarantined after 3 attempts)": "refusal",
        "error: BadRequestError: status 400": "input_rejected",
        "errored: invalid_request_error": "input_rejected",
        "not_reproducible": "not_reproducible",
        "manual: looked wrong": "manual",
    }
    assert {k: cl.failure_kind(k) for k in cases} == cases


# ---------------------------------------------------------------------------
# a conversation with a quarantined chunk is partial, not extracted
# ---------------------------------------------------------------------------

def _mark(env):
    c = env.get_db()
    ne = c.execute("SELECT needs_extraction FROM import_state WHERE conversation_id = ?",
                   (CONV,)).fetchone()[0]
    flags = [tuple(r) for r in c.execute(
        "SELECT flag, detail FROM conversation_flags WHERE conversation_id = ?", (CONV,))]
    c.close()
    return ne, flags


def test_a_conversation_with_a_quarantined_chunk_is_partial_not_extracted(env, monkeypatch):
    _quarantined_corpus(env, monkeypatch)
    ne, flags = _mark(env)
    assert ne == 1                                        # not marked extracted
    assert [f for f, _ in flags] == ["extraction_partial"] and "1 quarantined" in flags[0][1]
    q = [r for r in _rows(env) if r["status"] == "quarantined"][0]
    _cli(env, monkeypatch, "chunks", "retry", q["block_id"])
    monkeypatch.setattr(env.ef, "call_llm", LLM())
    env.ef.run_extraction()
    assert _objects(env) == ALL4
    assert _mark(env) == (0, [])                          # complete: extracted, flag cleared


def test_quarantining_by_hand_marks_the_conversation_partial(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    failed = [r for r in _rows(env) if r["status"] == "failed"][0]
    _cli(env, monkeypatch, "chunks", "quarantine", failed["block_id"], "--reason", "boundary")
    ne, flags = _mark(env)
    assert [f for f, _ in flags] == ["extraction_partial"]


def test_a_quarantine_sets_the_mark_even_after_an_earlier_run_cleared_it(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    c = env.get_db()
    c.execute("UPDATE import_state SET needs_extraction = 0 WHERE conversation_id = ?", (CONV,))
    c.commit()
    c.close()
    failed = [r for r in _rows(env) if r["status"] == "failed"][0]
    _cli(env, monkeypatch, "chunks", "quarantine", failed["block_id"], "--reason", "boundary")
    ne, flags = _mark(env)
    assert ne == 1 and [f for f, _ in flags] == ["extraction_partial"]


def test_a_conversation_with_only_a_failed_chunk_keeps_the_earlier_mark_behaviour(
        env, monkeypatch):
    """Only a quarantined chunk makes a conversation partial (design decision 2026-09-29); a failed chunk
    leaves the needs_extraction behaviour as it was: cleared at the end of the conversation."""
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", FailsOn("Entry 0"))
    with pytest.raises(SystemExit):
        env.ef.run_extraction()
    assert _mark(env) == (0, [])


def test_a_complete_conversation_is_marked_extracted(env, monkeypatch):
    _setup(env, monkeypatch)
    monkeypatch.setattr(env.ef, "call_llm", LLM())
    env.ef.run_extraction()
    assert _mark(env) == (0, [])
