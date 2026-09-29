"""Author quote gate (design T1 follow-up), default off, `author_from_package --quote-gate`.

Every quoted phrase in an authored claim (double or single quotes, straight or curly) must be
found, after whitespace/quote normalisation and case-folding, in an own-voice evidence span of a
fact THAT CLAIM cites. Own voice = a turn classed own_typed / own_dictated, which includes a
pasted segment re-classed as the person's own writing (basis allowlist:own_writing_pasted).
No re-ask. A quote whose words ARE in an own-voice span of a fact the author was given, but not
of a fact the claim cites (`uncited_span`), gets that fact auto-cited, recorded per claim in
`gate_added_citations` so a gate-chosen citation stays distinguishable from an author-chosen one.
Any other flagged quote (`not_found`, `elided`) has its quote marks removed (the words stay).
One authoring attempt, every count kept by reason. No API calls: fake clients only.
"""
import json
import re
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import author_from_package as afp
from baselayer.distillation import quote_gate as qg

V = "turn-contract/1"


# ------------------------------------------------------------------ extraction

def test_extracts_double_single_straight_and_curly_quotes():
    t = ('They say "plan first" and “ship it”, calls it \'is everything\' and '
         '‘when, not if’.')
    assert [p.inner for p in qg.quoted_phrases(t)] == [
        "plan first", "ship it", "is everything", "when, not if"]


def test_in_word_apostrophes_and_possessives_do_not_open_or_close_a_quote():
    t = ("They don't wait; the users' data stays put. They said 'I can't stop now' twice, "
         "and the team’s view was ‘it’s done’.")
    assert [p.inner for p in qg.quoted_phrases(t)] == ["I can't stop now", "it’s done"]


# ------------------------------------------------------------------ the check

SPANS = {"aaaaaaaa": ["Consistency IS  everything, really"],
         "bbbbbbbb": ["we forge on no matter what"],
         "cccccccc": ["knock everything off my list"]}


def _claim(stmt, fids=("aaaaaaaa",), cid="A1", name="X", aw=""):
    return {"id": cid, "name": name, "statement": stmt, "active_when": aw,
            "fact_ids": list(fids), "contested": False}


def test_quote_found_in_a_cited_span_passes_after_normalisation():
    g = qg.QuoteGate(SPANS)
    c = _claim("Consistency ‘is everything,’ they hold, and \"IS EVERYTHING\".")
    assert g.check([c], set(SPANS)) == []


def test_unfound_quotes_are_flagged_by_reason():
    g = qg.QuoteGate(SPANS)
    claims = [_claim("They 'forge on' and say 'stand on the shoulders of giants'."),
              _claim("They 'knock everything off ... my list'.", cid="A2")]
    got = [(f.claim_id, f.phrase, f.reason) for f in g.check(claims, set(SPANS))]
    assert got == [("A1", "forge on", "uncited_span"),
                   ("A1", "stand on the shoulders of giants", "not_found"),
                   ("A2", "knock everything off ... my list", "elided")]


def test_quotes_in_name_and_active_when_are_checked_too():
    g = qg.QuoteGate(SPANS)
    c = _claim("s", name="THE 'NO EGO' RULE", aw="When they say \"be done for the day\"")
    assert [f.field for f in g.check([c], set(SPANS))] == ["name", "active_when"]


def test_strip_removes_only_the_flagged_quote_marks():
    g = qg.QuoteGate(SPANS)
    c = _claim("Consistency 'is everything' but they 'sit on their hands'.")
    found = g.check([c], set(SPANS))
    assert g.strip([c], found) == 1
    assert c["statement"] == "Consistency 'is everything' but they sit on their hands."


# ------------------------------------------------------------------ spans from the database

def _db(tmp_path, cols=True):
    db = tmp_path / "memory.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, "
              "superseded_by TEXT%s)" % (", evidence_spans TEXT" if cols else ""))
    c.execute("CREATE TABLE turns (turn_id TEXT, voice_class TEXT, basis TEXT, text TEXT)")
    turns = [("t1", "own_typed", "role=user", "we keep the plan"),
             ("t2", "own_typed", "allowlist:own_writing_pasted", "resume line: led the team"),
             ("t3", "assistant", "source:role=assistant", "stand on the shoulders of giants"),
             ("t4", "own_dictated", "x", "say it out loud")]
    c.executemany("INSERT INTO turns VALUES (?,?,?,?)", turns)
    if cols:
        c.executemany("INSERT INTO memory_facts VALUES (?,?,?,?)", [
            ("aaaaaaaa-1", "f", None, json.dumps([{"turn_id": "t1", "span": "we keep the plan"},
                                                  {"turn_id": "t3",
                                                   "span": "stand on the shoulders of giants"}])),
            ("bbbbbbbb-2", "f", None, json.dumps([{"turn_id": "t2", "span": "led the team"}])),
            ("cccccccc-3", "f", None, json.dumps([{"turn_id": "t4", "span": "say it out loud"}])),
        ])
    c.commit()
    c.close()
    return str(db)


def test_spans_are_own_voice_including_allowlisted_own_writing(tmp_path):
    spans, info = qg.load_spans(_db(tmp_path), ["aaaaaaaa", "bbbbbbbb", "cccccccc"])
    assert spans["aaaaaaaa"] == ["we keep the plan"]          # the assistant span is not the person's
    assert spans["bbbbbbbb"] == ["led the team"]              # the person's own pasted writing counts
    assert spans["cccccccc"] == ["say it out loud"]
    assert info["non_own_spans_skipped"] == 1
    g = qg.QuoteGate(spans)
    bad = g.check([_claim("'stand on the shoulders of giants'", ("aaaaaaaa",)),
                   _claim("'led the team'", ("bbbbbbbb",), cid="A2")], set(spans))
    assert [(f.claim_id, f.reason) for f in bad] == [("A1", "not_found")]


def test_a_gate_that_cannot_run_refuses(tmp_path):
    with pytest.raises(qg.QuoteGateUnavailable, match="dddddddd"):
        qg.load_spans(_db(tmp_path), ["aaaaaaaa", "dddddddd"])
    other = tmp_path / "x"
    other.mkdir()
    with pytest.raises(qg.QuoteGateUnavailable, match="evidence_spans"):
        qg.load_spans(_db(other, cols=False), ["aaaaaaaa"])


# ------------------------------------------------------------------ inside call_structured

def _usage():
    return NS(input_tokens=100, output_tokens=50)


def _tool_msg(claims):
    return NS(content=[NS(type="thinking", thinking=""),
                       NS(type="tool_use", name="emit_layer",
                          input={"layer": "anchors", "preamble": "",
                                 "claims": json.loads(json.dumps(claims))})],
              stop_reason="tool_use", stop_details=None, usage=_usage())


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        return _Stream(self.responses.pop(0))


def _bad_claims(n=12):
    return [_claim("They say 'bogus phrase number %d here'." % i, cid="A%d" % i)
            for i in range(n)]


def test_unfound_quotes_are_stripped_on_attempt_one_with_no_reask():
    g = qg.QuoteGate(SPANS)
    stats = {}
    good = [_claim("Consistency 'is everything'.", cid="A%d" % i) for i in range(12)]
    # A second response is scripted so a re-asking gate fails on the call count, not on an
    # empty script.
    cl = FakeClient([_tool_msg(_bad_claims()), _tool_msg(good)])
    data, _, _ = afp.call_structured(cl, "claude-opus-5-5", "PROMPT", afp.LAYER_SCHEMA,
                                     set(SPANS), quote_gate=g, quote_stats=stats)
    assert len(cl.calls) == 1
    assert [c["statement"] for c in data["claims"]] == [
        "They say bogus phrase number %d here." % i for i in range(12)]
    assert [c["fact_ids"] for c in data["claims"]] == [["aaaaaaaa"]] * 12
    assert not any("gate_added_citations" in c for c in data["claims"])
    assert stats["attempts"][0]["by_reason"] == {"not_found": 12}
    f = stats["final"]
    assert (f["flagged"], f["quote_marks_stripped"], f["auto_cited"]) == (12, 12, 0)
    assert f["residual_after_gate"] == 0


def test_uncited_real_quote_is_auto_cited_and_unfound_is_stripped_in_one_call():
    g = qg.QuoteGate(SPANS)
    stats = {}
    c = [_claim("Consistency 'is everything' and they 'forge on no matter' to "
                "'sit on their hands'.")]
    cl = FakeClient([_tool_msg(c)] * 3)
    data, _, _ = afp.call_structured(cl, "claude-opus-5-5", "PROMPT", afp.LAYER_SCHEMA,
                                     set(SPANS), quote_gate=g, quote_stats=stats)
    assert len(cl.calls) == 1
    got = data["claims"][0]
    # the real words keep their quote marks and gain their fact; the unfound ones lose the marks
    assert got["statement"] == (
        "Consistency 'is everything' and they 'forge on no matter' to sit on their hands.")
    assert got["fact_ids"] == ["aaaaaaaa", "F-bbbbbbbb"]
    assert got["gate_added_citations"] == ["F-bbbbbbbb"]
    f = stats["final"]
    assert f["by_reason"] == {"uncited_span": 1, "not_found": 1}
    assert (f["auto_cited"], f["quote_marks_stripped"]) == (1, 1)
    assert f["quotes_checked"] == 3 and f["passed"] == 1
    assert f["residual_after_gate"] == 0
    assert f["auto_cited_claims"] == [{"claim": "A1", "field": "statement",
                                       "phrase": "forge on no matter", "action": "auto_cited",
                                       "fact_ids": ["F-bbbbbbbb"]}]


# ------------------------------------------------------------------ auto-cite bounds
# Auto-cite only a quote of >= 3 words with <= 5 holders among the supplied facts; any other
# uncited_span quote loses its quote marks, and the stamp records why, per quote.

def _gate_one(spans, stmt, cited=("aaaaaaaa",)):
    g = qg.QuoteGate(spans)
    stats = {}
    cl = FakeClient([_tool_msg([_claim(stmt, cited)])] * 3)
    data, _, _ = afp.call_structured(cl, "claude-opus-5-5", "PROMPT", afp.LAYER_SCHEMA,
                                     set(spans), quote_gate=g, quote_stats=stats)
    assert len(cl.calls) == 1
    return data["claims"][0], stats["final"]


def _holders(n, words="keep the plan"):
    s = {"aaaaaaaa": ["unrelated words"]}
    for i in range(n):
        s["%08x" % (0xb0000000 + i)] = ["we %s every day" % words]
    return s


def test_two_word_real_quote_is_stripped_not_cited():
    got, f = _gate_one(SPANS, "They 'forge on'.")
    assert got["statement"] == "They forge on."
    assert got["fact_ids"] == ["aaaaaaaa"] and "gate_added_citations" not in got
    assert f["by_reason"] == {"uncited_span": 1}
    assert f["by_action"] == {"stripped_short": 1}
    assert (f["auto_cited"], f["quote_marks_stripped"], f["residual_after_gate"]) == (0, 1, 0)
    assert f["stripped"] == [{"claim": "A1", "field": "statement", "phrase": "forge on",
                              "reason": "uncited_span", "action": "stripped_short",
                              "holders": 1}]


def test_three_word_quote_with_six_holders_is_stripped_not_cited():
    got, f = _gate_one(_holders(6), "They 'keep the plan'.")
    assert got["statement"] == "They keep the plan."
    assert got["fact_ids"] == ["aaaaaaaa"] and "gate_added_citations" not in got
    assert f["by_action"] == {"stripped_many_holders": 1}
    assert f["stripped"][0]["action"] == "stripped_many_holders"
    assert f["stripped"][0]["holders"] == 6
    assert f["residual_after_gate"] == 0


def test_three_word_quote_with_two_holders_is_auto_cited():
    got, f = _gate_one(_holders(2), "They 'keep the plan'.")
    assert got["statement"] == "They 'keep the plan'."
    assert got["fact_ids"] == ["aaaaaaaa", "F-b0000000", "F-b0000001"]
    assert got["gate_added_citations"] == ["F-b0000000", "F-b0000001"]
    assert f["by_action"] == {"auto_cited": 1}
    assert (f["auto_cited"], f["quote_marks_stripped"]) == (2, 0)


def test_quote_at_exactly_five_holders_is_auto_cited():
    got, f = _gate_one(_holders(5), "They 'keep the plan'.")
    assert got["gate_added_citations"] == ["F-b000000%d" % i for i in range(5)]
    assert f["by_action"] == {"auto_cited": 1}


def test_not_found_and_elided_are_recorded_as_stripped_with_their_reason():
    got, f = _gate_one(SPANS, "They 'sit on their hands' and 'knock everything off ... list'.")
    assert got["statement"] == "They sit on their hands and knock everything off ... list."
    assert f["by_action"] == {"stripped_not_found": 1, "stripped_elided": 1}


def test_auto_cite_adds_every_holder_once_and_only_to_the_claim_that_holds_the_quote():
    spans = {"aaaaaaaa": ["alpha words"], "bbbbbbbb": ["we forge on no matter what"],
             "cccccccc": ["we forge on together"], "dddddddd": ["no matter what"]}
    g = qg.QuoteGate(spans)
    # Two claims share an id. Only the second holds the quotes; lookup must be by claim, not id.
    other = _claim("Nothing quoted here.", cid="A1")
    c = _claim("They 'forge on', 'no matter what', and 'forge on' again.", cid="A1")
    found = g.check([other, c], set(spans))
    assert [(f.reason, f.source_ids) for f in found] == [
        ("uncited_span", ("bbbbbbbb", "cccccccc")),
        ("uncited_span", ("bbbbbbbb", "dddddddd")),
        ("uncited_span", ("bbbbbbbb", "cccccccc"))]
    assert g.auto_cite([other, c], found) == 3
    assert c["fact_ids"] == ["aaaaaaaa", "F-bbbbbbbb", "F-cccccccc", "F-dddddddd"]
    assert c["gate_added_citations"] == ["F-bbbbbbbb", "F-cccccccc", "F-dddddddd"]
    assert other["fact_ids"] == ["aaaaaaaa"] and "gate_added_citations" not in other
    assert g.check([other, c], set(spans)) == []


def test_no_gate_leaves_call_structured_unchanged():
    cl = FakeClient([_tool_msg(_bad_claims(1))])
    data, _, _ = afp.call_structured(cl, "claude-opus-5-5", "PROMPT", afp.LAYER_SCHEMA,
                                     set(SPANS))
    assert len(cl.calls) == 1
    assert "bogus phrase number 0 here" in data["claims"][0]["statement"]


# ------------------------------------------------------------------ the flag, end to end

def _pkg(tmp_path):
    from baselayer.distillation import assemble as asm
    t = {"stamp": {"run_id": "r1", "layer": "anchors", "turn_contract_version": V,
                   "input_hash": "h"},
         "root": {"themes": [{"statement": "t", "fact_ids": ["aaaaaaaa"]}],
                  "singularities": [{"fact_id": "bbbbbbbb", "verbatim": "v",
                                     "own_words": "led the team"}], "contradictions": []},
         "leaves": [{"dispositions": {"aaaaaaaa": "theme", "bbbbbbbb": "singularity"}}]}
    p = tmp_path / "anchors_package.json"
    p.write_text(json.dumps(asm.assemble([t])), encoding="utf-8")
    return p


class GateClient:
    script = []
    calls = []

    def __init__(self, *a, **k):
        self.messages = self

    def stream(self, **kw):
        GateClient.calls.append(kw)
        return _Stream(_tool_msg(GateClient.script.pop(0)))


@pytest.fixture
def env(monkeypatch, tmp_path):
    GateClient.script, GateClient.calls = [], []
    monkeypatch.setattr("anthropic.Anthropic", GateClient)
    monkeypatch.delenv("BASELAYER_REAUTHOR", raising=False)
    from baselayer.distillation import spend
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")

    def run(*extra):
        monkeypatch.setattr(sys, "argv", ["afp", "--outdir", str(tmp_path / "out"), "--model",
                                          "claude-opus-5-5", "--effort", "high",
                                          "--package", str(_pkg(tmp_path)), "--no-compose",
                                          *extra])
        afp.main()
        return tmp_path / "out"
    return NS(run=run, tmp=tmp_path)


def test_flag_without_db_refuses_before_any_call(env):
    with pytest.raises(SystemExit, match="--db"):
        env.run("--quote-gate")
    assert GateClient.calls == []


def test_flag_with_missing_fact_refuses_before_any_call(env):
    d = env.tmp / "d"
    d.mkdir()
    db = d / "memory.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT, fact_text TEXT, superseded_by TEXT, "
              "evidence_spans TEXT)")
    c.execute("CREATE TABLE turns (turn_id TEXT, voice_class TEXT, basis TEXT, text TEXT)")
    c.commit()
    c.close()
    with pytest.raises(SystemExit, match="aaaaaaaa"):
        env.run("--quote-gate", "--db", str(db))
    assert GateClient.calls == []


def test_flag_end_to_end_auto_cites_real_quote_and_strips_fabricated_in_one_call(env):
    """Through main() and _quote_gate_step. Supplied ids are aaaaaaaa and bbbbbbbb.
    'led the team' is bbbbbbbb's own writing, uncited: auto-cited as F-bbbbbbbb.
    'stand on the shoulders of giants' sits in a CITED fact but in assistant voice: stripped.
    'say it out loud' is own voice of cccccccc, which was never supplied: stripped, not cited."""
    db = _db(env.tmp)
    GateClient.script = [
        [_claim("They 'led the team', 'stand on the shoulders of giants', 'say it out loud'.",
                ("aaaaaaaa",))],
        [_claim("They 'led the team'.", ("aaaaaaaa", "bbbbbbbb"))]]
    out = env.run("--quote-gate", "--db", db)
    assert len(GateClient.calls) == 1
    assert qg.PROMPT_RULE in GateClient.calls[0]["messages"][0]["content"]
    claim = json.loads((out / "anchors.json").read_text(encoding="utf-8"))["claims"][0]
    assert claim["statement"] == (
        "They 'led the team', stand on the shoulders of giants, say it out loud.")
    assert claim["fact_ids"] == ["aaaaaaaa", "F-bbbbbbbb"]
    assert claim["gate_added_citations"] == ["F-bbbbbbbb"]
    md = (out / "anchors.md").read_text(encoding="utf-8")
    assert "provenance: [F-aaaaaaaa, F-bbbbbbbb]" in md
    assert "*Citations added by the quote gate:* [F-bbbbbbbb]" in md
    st = json.loads((out / "anchors.stamp.json").read_text(encoding="utf-8"))
    q = st["quote_gate"]
    assert q["mode"] == "auto_cite_strip"
    assert "rejected_attempts" not in q
    assert q["final"]["by_reason"] == {"uncited_span": 1, "not_found": 2}
    assert (q["final"]["auto_cited"], q["final"]["quote_marks_stripped"]) == (1, 2)
    assert q["final"]["residual_after_gate"] == 0
    assert st["usage"]["attempts"] == 1


def test_quote_gate_estimate_prices_one_attempt(env, capsys):
    db = _db(env.tmp)
    GateClient.script = [[_claim("They 'led the team'.", ("bbbbbbbb",))]]
    env.run("--quote-gate", "--db", db)
    out = capsys.readouterr().out
    assert "ESTIMATE: $" in out and "one attempt each" in out
    assert "3 attempts" not in out and "all 3" not in out
    assert "re-sends the layer" not in out


def test_prompt_rule_no_longer_promises_rejection():
    r = qg.PROMPT_RULE
    assert "rejected" not in r.lower()
    assert "cite that fact" in r                       # the author's obligation is unchanged
    assert "removed" in r                              # and it states what happens otherwise


def test_default_prompt_has_no_quote_rule(env):
    GateClient.script = [[_claim("They 'anything at all'.", ("aaaaaaaa",))]]
    out = env.run()
    assert qg.PROMPT_RULE not in GateClient.calls[0]["messages"][0]["content"]
    assert "quote_gate" not in json.loads((out / "anchors.stamp.json").read_text("utf-8"))


# ------------------------------------------------------------------ the sharded call site

class ShardQuoteClient:
    """Per shard, one claim citing its first fact and quoting (1) the words of another fact IN
    THIS SHARD, uncited, and (2) the words of a fact in ANOTHER shard. Supplied ids are scoped
    per shard, so (1) must be auto-cited and (2) stripped, never cited across shards."""
    calls = []
    all_ids = set()

    def __init__(self, *a, **k):
        self.messages = self

    def stream(self, **kw):
        import re
        ShardQuoteClient.calls.append(kw)
        prompt = kw["messages"][0]["content"]
        own = sorted(set(re.findall(r"\[F-([0-9a-f]{8})\]", prompt)))
        foreign = sorted(ShardQuoteClient.all_ids - set(own))[0]
        return _Stream(_tool_msg([_claim("They say 'own words for %s' and 'own words for %s'."
                                         % (own[-1], foreign), (own[0],))]))


def test_sharded_layer_gates_each_shard_and_stamps_per_shard(env, monkeypatch, tmp_path):
    from baselayer.distillation import assemble as asm
    from tests.test_distill_payload import _big_tree
    ShardQuoteClient.calls = []
    monkeypatch.setattr("anthropic.Anthropic", ShardQuoteClient)
    tree = _big_tree()
    r = tree["root"]
    ShardQuoteClient.all_ids = ({f for t in r["themes"] for f in t["fact_ids"]}
                                | {s["fact_id"] for s in r["singularities"]})
    tp = tmp_path / "t.json"
    tp.write_text(json.dumps(tree), encoding="utf-8")
    man = tmp_path / "anchors_pkg.json"
    monkeypatch.setattr(sys, "argv", ["assemble.py", str(tp), "--out", str(man),
                                      "--shard-token-budget", "3000"])
    asm.main()
    n = len(json.load(open(man, encoding="utf-8"))["shards"])
    assert n >= 2
    db = tmp_path / "shard.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT, fact_text TEXT, superseded_by TEXT, "
              "evidence_spans TEXT)")
    c.execute("CREATE TABLE turns (turn_id TEXT, voice_class TEXT, basis TEXT, text TEXT)")
    for lf in tree["leaves"]:
        for f in lf["_ids"]:
            c.execute("INSERT INTO turns VALUES (?,?,?,?)", ("t" + f, "own_typed", "x", "w"))
            c.execute("INSERT INTO memory_facts VALUES (?,?,?,?)",
                      (f + "-x", "f", None, json.dumps([{"turn_id": "t" + f,
                                                         "span": "own words for %s" % f}])))
    c.commit()
    c.close()
    monkeypatch.setattr(sys, "argv", ["afp", "--outdir", str(tmp_path / "out"), "--model",
                                      "claude-opus-5-5", "--effort", "high", "--package",
                                      str(man), "--no-compose", "--quote-gate", "--db", str(db)])
    afp.main()
    assert len(ShardQuoteClient.calls) == n                 # one call per shard, no re-ask
    st = json.loads((tmp_path / "out" / "anchors.stamp.json").read_text(encoding="utf-8"))
    per = st["quote_gate"]["per_shard"]
    assert [s["shard"] for s in per] == list(range(1, n + 1))
    for s in per:
        assert s["final"]["by_reason"] == {"uncited_span": 1, "not_found": 1}
        assert (s["final"]["auto_cited"], s["final"]["quote_marks_stripped"]) == (1, 1)
    data = json.load(open(tmp_path / "out" / "anchors.json", encoding="utf-8"))
    assert len(data["claims"]) == n
    for c in data["claims"]:                                # survives combine_shards
        own, foreign = re.findall(r"own words for ([0-9a-f]{8})", c["statement"])
        assert "'own words for %s'" % own in c["statement"]
        assert "'own words for %s'" % foreign not in c["statement"]
        assert c["gate_added_citations"] == ["F-%s" % own]
        assert len(c["fact_ids"]) == 2 and c["fact_ids"][-1] == "F-%s" % own
        assert foreign not in c["fact_ids"] and "F-%s" % foreign not in c["fact_ids"]


def test_uncited_span_is_auto_cited_to_the_fact_that_holds_the_words():
    g = qg.QuoteGate(SPANS)
    c = _claim("They 'forge on'.")
    found = g.check([c], set(SPANS))
    assert [(f.reason, f.source_ids) for f in found] == [("uncited_span", ("bbbbbbbb",))]
    assert g.auto_cite([c], found) == 1
    assert c["fact_ids"] == ["aaaaaaaa", "F-bbbbbbbb"]
    assert c["gate_added_citations"] == ["F-bbbbbbbb"]
    assert not hasattr(qg.QuoteGate, "problem")             # the re-ask text is gone


def test_reused_layer_without_a_quote_check_is_reported(env, capsys):
    db = _db(env.tmp)
    GateClient.script = [[_claim("They 'anything at all'.", ("aaaaaaaa",))]]
    env.run()                                     # authored WITHOUT the gate
    capsys.readouterr()
    env.run("--quote-gate", "--db", db)           # reused from disk, never checked
    assert "was not quote-checked" in capsys.readouterr().out
    assert len(GateClient.calls) == 1
