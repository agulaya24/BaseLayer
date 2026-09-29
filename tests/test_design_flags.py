"""Design-test flags for distillation, all default off (design tests T1-T3).

T1 --leaf-spans      each fact's verbatim evidence spans are shown to the leaf beside the fact
                     text; a singularity may carry a `own_words` excerpt, checked against that
                     fact's own spans (detected, stripped, counted).
T2 --partition episode
                     leaves are chunked by episode (a conversation; for day-grouped
                     conversations, a calendar day across conversations), long episodes split
                     contiguously, short ones packed with their boundaries marked.
T3 situation_first   predictions authored situation-first: situations, then mechanical routing
                     of facts to each situation, then predictions cited only from what was routed.

The first block PINS the default path: the leaf prompts, their prompt hashes and the author's
package render are byte-identical to 1ed9cd8, which is the proof that production is unchanged.
No API calls: fake clients only.
"""
import hashlib
import json
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from baselayer.distillation import assemble as asm
from baselayer.distillation import author_from_package as afp
from baselayer.distillation import distill
from tests.test_artifact_stamps import _Stream

V = "turn-contract/1"
FS = [("aaaaaaaa-0000-4000-8000-000000000001", "They write the plan before they write code.",
       "p", "c", 0.0),
      ("bbbbbbbb-0000-4000-8000-000000000002", "They ask for two options.", "p", "c", 1.0)]
PIN_PROMPT = {
    "anchors": "f106145519120a0544a59ca30b598ef28619f0e790518ab59112d4154451b7c9",
    "core": "39cc0affd89ae7bd66664fa6bde7c1a9ba2492351c81c54758b44b26c23d9060",
    "predictions": "51d58da75618c356bb526459b2f278e3935e295f2ed79998cc148108141ccb8e",
}
PIN_PH = {"anchors": "53e2f6735438300e", "core": "394d767734c9ba67",
          "predictions": "ec716621e5a192fa"}
PIN_RENDER = "38307edba6e8d0aa959f45eb6bdbb22b8b0b8966df759036727c6bb56655561b"
PIN_LAYER_PROMPT = "5955fc19e90048f937971e712ff9b0d1e0b600275fe5a748b9b8d758ec2d5e98"


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _pkg_tree(sing=None):
    sing = sing or {"fact_id": "aaaaaaaa", "verbatim": "v"}
    return {"stamp": {"run_id": "r1", "layer": "predictions", "turn_contract_version": V,
                      "input_hash": "h"},
            "root": {"themes": [{"statement": "t", "fact_ids": ["aaaaaaaa"]}],
                     "singularities": [sing], "contradictions": []},
            "leaves": [{"dispositions": {"aaaaaaaa": "theme"}}]}


# ------------------------------------------------------------------ the default path is pinned

@pytest.mark.parametrize("layer", ["anchors", "core", "predictions"])
def test_default_leaf_prompt_and_hash_are_unchanged(layer):
    assert _h(distill.leaf_prompt(layer, "predicate-1/1 p(2)", FS)) == PIN_PROMPT[layer]
    assert _h(distill.leaf_prompt(layer, "predicate-1/1 p(2)", FS, None, None)) == PIN_PROMPT[layer]
    assert distill.leaf_stamp_common(layer, "claude-sonnet-5", V)[0] == PIN_PH[layer]


def test_default_author_render_is_unchanged(capsys):
    pkg = asm.assemble([_pkg_tree()])
    assert _h(afp.render(pkg)) == PIN_RENDER
    assert _h("\n".join(afp.layer_prompt_parts(pkg))) == PIN_LAYER_PROMPT


# ------------------------------------------------------------------ T1: spans to leaves

SPANS = {"aaaaaaaa": ["i always write the plan first", "plan, then code, no exceptions"],
         "bbbbbbbb": ["give me two options not a spectrum", "two paths", "three", "four"]}


def test_t1_prompt_shows_each_fact_spans_verbatim_and_counts_the_cap():
    o = distill.LeafOptions(spans=SPANS, span_cap=3)
    p = distill.leaf_prompt("predictions", "predicate-1/1 p(2)", FS, None, o)
    for s in SPANS["aaaaaaaa"] + SPANS["bbbbbbbb"][:3]:
        assert '"%s"' % s in p
    assert '"four"' not in p and "+1 more" in p
    assert o.span_facts_truncated == {"bbbbbbbb"}
    # the own words line follows its own fact line
    a = p.index("[aaaaaaaa] "); b = p.index("[bbbbbbbb] ")
    assert a < p.index("i always write the plan first") < b
    assert "own_words" in p                           # the T1 schema field
    assert distill.leaf_stamp_common("predictions", "m", V, o)[0] != PIN_PH["predictions"]


def test_t1_own_words_checked_against_that_facts_own_spans():
    node = {"themes": [], "contradictions": [],
            "singularities": [
                {"fact_id": "aaaaaaaa", "verbatim": FS[0][1], "own_words": "Plan, then code",
                 "why": "x"},
                {"fact_id": "bbbbbbbb", "verbatim": FS[1][1],
                 "own_words": "i always write the plan first", "why": "not the span for b"}],
            "dispositions": {"aaaaaaaa": "singular", "bbbbbbbb": "singular"}}
    bad = distill.validate(node, ["aaaaaaaa", "bbbbbbbb"], SPANS)
    assert bad == []                                  # a misquote is stripped, not re-asked
    assert node["singularities"][0]["own_words"] == "Plan, then code"
    assert node["singularities"][1]["own_words"] == ""
    assert node["_stripped"]["own_words"] == 1


def test_validate_without_spans_is_unchanged():
    node = {"themes": [], "contradictions": [], "singularities": [],
            "dispositions": {"aaaaaaaa": "theme"}}
    distill.validate(node, ["aaaaaaaa"])
    assert "own_words" not in node["_stripped"]


# ------------------------------------------------------------------ T2: episode chunks

def _ctx():
    """Two day-grouped conversations on one UTC day (and one turn crossing into the next), a
    long build session, and three short personal conversations. convA is day-grouped by its
    title, convB by its practice tag."""
    day = 1741791600.0                                 # 2025-03-12 15:00 UTC
    ctx, rows = {}, []

    def add(fid, conv, title, ordinal, ts, conv_ts, practice=None):
        rows.append((fid, "fact %s" % fid[:8], "p", "c", 0.0))
        ctx[fid] = {"conv": conv, "title": title, "source": "chatgpt", "conv_ts": conv_ts,
                    "turn_ts": ts, "ordinal": ordinal, "segment": 0, "practice": practice,
                    "spans": []}
    for i in range(3):
        add("a%07d-x" % i, "convA", "Morning plan", i, day + 60 * i, day)
    for i in range(2):
        add("b%07d-x" % i, "convB", "Daily review", i, day + 3600 + 60 * i, day + 3600,
            practice="journal")
    add("b%07d-x" % 9, "convB", "Daily review", 9, day + 86400, day + 3600)
    add("b%07d-y" % 8, "convB", "Daily review", 8, None, day + 3600)   # date fallback
    for i in range(7):
        add("c%07d-x" % i, "convC", "build session", i, day + 10 * 86400 + i, day + 10 * 86400)
    for k, conv in enumerate(("convD", "convE", "convF")):
        add("d%d%06d-x" % (k, 0), conv, "personal %d" % k, 0, day + (20 + k) * 86400,
            day + (20 + k) * 86400)
    return rows, ctx


def test_t2_episodes_group_days_across_conversations_and_split_long_ones():
    rows, ctx = _ctx()
    o = distill.LeafOptions(episode_max=4, episode_min=2, day_title_regex=r"(?i)morning plan",
                            tz="UTC", day_practices=("journal",))
    chunks = distill.episode_partition(rows, ctx, o)
    seen = [r[0] for _, fs in chunks for r in fs]
    assert sorted(seen) == sorted(r[0] for r in rows)          # every fact exactly once
    assert all(len(fs) <= 4 for _, fs in chunks)
    ep = o.episode_of
    # convA and convB share one day; the next-day turn is its own day
    day1 = {ep[r[0][:8]] for r in rows if r[0][:8] in ("a0000000", "a0000002", "b0000000")}
    assert len(day1) == 1 and "2025-03-12" in day1.pop()
    assert ep["b0000009"] != ep["b0000000"] and "2025-03-13" in ep["b0000009"]
    assert o.episode_info["day_date_fallbacks"] == 1
    assert ep["b0000008"] == ep["b0000000"]                     # fell back to the conv date
    # the 7-fact build session is split into contiguous, balanced parts in turn order
    parts = [[r[0][:8] for r in fs] for _, fs in chunks if fs[0][0].startswith("c")]
    assert [len(p) for p in parts] == [4, 3]
    assert parts[0] + parts[1] == ["c%07d" % i for i in range(7)]
    # the 1-fact next day and three 1-fact personal episodes are packed into one chunk, in
    # time order, with their boundaries marked; the 6-fact first day is split 3 + 3
    packs = [lb for lb, fs in chunks if any(r[0].startswith("d") for r in fs)]
    assert len(packs) == 1
    assert len(o.groups[packs[0]]) == 4
    d57 = ep["a0000000"]
    assert [len(fs) for _, fs in chunks if ep[fs[0][0][:8]] == d57] == [3, 3]
    assert sorted(o.episode_info["day_grouped_conversations"]) == ["convA", "convB"]


def test_t2_prompt_names_the_episode_and_orders_facts():
    rows, ctx = _ctx()
    o = distill.LeafOptions(episode_max=4, episode_min=2, day_title_regex=r"(?i)morning plan",
                            day_practices=("journal",))
    chunks = distill.episode_partition(rows, ctx, o)
    lb, fs = [c for c in chunks if c[1][0][0].startswith("c")][0]
    p = distill.leaf_prompt("predictions", lb, fs, None, o)
    assert "share one episode" in p and "in the order they occurred" in p
    lbp, fsp = [c for c in chunks if any(r[0].startswith("d") for r in c[1])][0]
    pp = distill.leaf_prompt("predictions", lbp, fsp, None, o)
    assert pp.count("--- episode:") == 4 and "4 short episodes" in pp
    assert distill.leaf_stamp_common("predictions", "m", V, o)[0] != PIN_PH["predictions"]


def _tagged_ctx(practice):
    day = 1741791600.0
    ctx, rows = {}, []
    for conv, off in (("convP", 0), ("convQ", 3600)):
        for i in range(2):
            fid = "%s%06d-x" % (conv[-1].lower(), i)
            rows.append((fid, "fact %s" % fid[:8], "p", "c", 0.0))
            ctx[fid] = {"conv": conv, "title": "notes", "source": "chatgpt", "conv_ts": day + off,
                        "turn_ts": day + off + i, "ordinal": i, "segment": 0,
                        "practice": practice, "spans": []}
    return rows, ctx


def test_t2_no_practice_tag_is_day_grouped_unless_named():
    """No practice tag is special by default: a tag once hard-coded here is not day-grouped
    without --episode-day-practice, and any named tag is, including one inside a '+' join."""
    rows, ctx = _tagged_ctx("trading_journal")
    o = distill.LeafOptions(episode_max=4, episode_min=1)
    distill.episode_partition(rows, ctx, o)
    assert all(k.startswith("conv:") for k in o.episode_of.values())
    rows, ctx = _tagged_ctx("general+journal")
    o = distill.LeafOptions(episode_max=4, episode_min=1, day_practices=("journal",))
    distill.episode_partition(rows, ctx, o)
    assert len(set(o.episode_of.values())) == 1
    assert next(iter(o.episode_of.values())).startswith("day:")
    assert o.stamp()["episodes"]["day_practices"] == ["journal"]


def test_t2_episode_partition_requires_an_explicit_timezone():
    """No site timezone is assumed: the CLI default is None and --partition episode refuses to
    run without --episode-tz, before reading the database."""
    import argparse
    ap = argparse.ArgumentParser()
    distill.add_design_args(ap)
    a = ap.parse_args([])
    assert a.episode_tz is None and a.episode_day_practice is None
    ns = argparse.Namespace(db="does-not-exist.db", partition="episode", leaf_spans=False,
                            max_facts=10, episode_tz=None)
    with pytest.raises(SystemExit, match="episode-tz"):
        distill.leaf_options(ns, [])
    assert distill.LeafOptions().tz == "UTC"


def test_plain_partition_refuses_episode_without_context():
    with pytest.raises(ValueError, match="episode"):
        distill.partition([r for r in FS], "episode", 2)


# ------------------------------------------------------------------ call sites: batch repairs

def test_batch_repair_prompt_is_the_flagged_prompt(monkeypatch, tmp_path):
    """The batch repair loop rebuilds each leaf prompt; with T1 on it must rebuild the SAME
    flagged prompt the batch was sent, never the default one."""
    from baselayer.distillation import distill_batch as dbm
    from tests import test_distill_batch as tdb
    from tests.test_artifact_stamps import DistillClient
    db = _spans_db(tmp_path)
    tdb.FakeBatches.created, tdb.FakeBatches.script = [], {
        "L1-anchors-predicate-0-0000": "errored"}
    DistillClient.calls = []
    monkeypatch.setattr("anthropic.Anthropic", tdb.BatchClient)
    monkeypatch.chdir(tmp_path)
    from baselayer.distillation import spend
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")
    monkeypatch.setattr(sys, "argv", ["distill_batch.py", "--db", str(db), "--outdir",
                                      str(tmp_path / "out"), "--model", "claude-haiku-4-5",
                                      "--max-facts", "2", "--layers", "anchors",
                                      "--partitions", "predicate", "--poll", "0",
                                      "--leaf-spans"])
    dbm.main()
    sent = tdb.FakeBatches.created[0][0]["params"]["messages"][0]["content"]
    assert "own words:" in sent
    assert DistillClient.calls[0]["messages"][0]["content"] == sent
    t = json.load(open(tmp_path / "out" / "anchors_predicate_0.json", encoding="utf-8"))
    assert t["stamp"]["leaf_spans"]["enabled"] is True


def _spans_db(tmp_path):
    db = tmp_path / "c" / "data" / "database" / "memory.db"
    db.parent.mkdir(parents=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE memory_facts (id TEXT PRIMARY KEY, fact_text TEXT, predicate TEXT, "
              "category TEXT, superseded_by TEXT, created_at REAL, turn_contract_version TEXT, "
              "source_conversation_id TEXT, source_turn_id TEXT, evidence_spans TEXT, "
              "practice TEXT)")
    c.execute("CREATE TABLE conversations (id TEXT, title TEXT, created_at REAL, source TEXT)")
    c.execute("CREATE TABLE turns (turn_id TEXT, conversation_id TEXT, ordinal INTEGER, "
              "segment INTEGER, created_at REAL)")
    c.execute("INSERT INTO conversations VALUES ('conv1', 't', 1741791600.0, 'chatgpt')")
    for i, (fid, text, _v) in enumerate([
            ("aaaaaaaa-0000-4000-8000-000000000001", "They write the plan first.", V),
            ("bbbbbbbb-0000-4000-8000-000000000002", "They ask for two options.", V),
            ("cccccccc-0000-4000-8000-000000000003", "They keep a dated backup.", V)]):
        tid = "conv1:%d" % i
        c.execute("INSERT INTO turns VALUES (?,?,?,0,?)", (tid, "conv1", i, 1741791600.0 + i))
        c.execute("INSERT INTO memory_facts VALUES (?,?,?,?,NULL,?,?,?,?,?,NULL)",
                  (fid, text, "prefers", "preference", float(i), V, "conv1", tid,
                   json.dumps([{"turn_id": tid, "span": "my own words number %d" % i}])))
    c.commit()
    c.close()
    return db


def test_fact_context_reads_spans_turns_and_conversations(tmp_path):
    db = _spans_db(tmp_path)
    ctx = distill.fact_context(str(db), ["aaaaaaaa-0000-4000-8000-000000000001"])
    x = ctx["aaaaaaaa-0000-4000-8000-000000000001"]
    assert x["spans"] == ["my own words number 0"]
    assert x["conv"] == "conv1" and x["ordinal"] == 0 and x["turn_ts"] == 1741791600.0


# ------------------------------------------------------------------ carried to the author

def test_own_words_travel_through_assemble_and_render(capsys):
    pkg = asm.assemble([_pkg_tree({"fact_id": "aaaaaaaa", "verbatim": "v",
                                   "own_words": "plan, then code"})])
    assert pkg["singularities_verified"][0]["own_words"] == "plan, then code"
    assert 'own words: "plan, then code"' in afp.render(pkg)


def test_no_compose_skips_the_brief(monkeypatch, tmp_path):
    from tests.test_artifact_stamps import AuthorClient
    AuthorClient.script, AuthorClient.calls = [], []
    monkeypatch.setattr("anthropic.Anthropic", AuthorClient)
    from baselayer.distillation import spend
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    monkeypatch.setenv("BASELAYER_SPEND_CEILING_USD", "50")
    t = _pkg_tree()
    t["stamp"]["layer"] = "anchors"
    p = tmp_path / "a.json"
    p.write_text(json.dumps(asm.assemble([t])), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["afp", "--outdir", str(tmp_path / "out"), "--model",
                                      "claude-opus-5-5", "--effort", "high", "--package", str(p),
                                      "--no-compose"])
    afp.main()
    assert [c["tools"][0]["name"] for c in AuthorClient.calls] == ["emit_layer"]
    assert (tmp_path / "out" / "anchors.json").exists()
    assert not (tmp_path / "out" / "brief.md").exists()


# ------------------------------------------------------------------ T3: situation-first

def test_t3_routing_is_mechanical_and_ordered():
    from baselayer.distillation import situation_first as sf
    pkg = {"themes": [{"statement": "t1", "fact_ids": ["aaaaaaaa", "bbbbbbbb"]},
                      {"statement": "t2", "fact_ids": ["cccccccc"]}],
           "singularities_verified": [], "singularities_unverified": [],
           "contradictions": [{"tension": "x", "a_fact_ids": ["aaaaaaaa"],
                               "b_fact_ids": ["dddddddd"]}]}
    tree = {"leaves": [{"_ids": ["aaaaaaaa", "bbbbbbbb", "cccccccc", "dddddddd", "eeeeeeee"],
                        "dispositions": {"aaaaaaaa": "theme", "bbbbbbbb": "theme",
                                         "cccccccc": "theme", "dddddddd": "singular",
                                         "eeeeeeee": "not_load_bearing"},
                        "_episode_of": {"aaaaaaaa": "E1", "bbbbbbbb": "E1", "cccccccc": "E1",
                                        "dddddddd": "E2", "eeeeeeee": "E1"}}]}
    r = sf.route([{"id": "S1", "fact_ids": ["F-aaaaaaaa"]}], pkg, tree, cap=10)["S1"]
    assert [x["id"] for x in r] == ["aaaaaaaa", "bbbbbbbb", "dddddddd", "cccccccc"]
    assert [x["why"] for x in r] == ["seed", "theme", "contradiction", "episode"]
    capped = sf.route([{"id": "S1", "fact_ids": ["aaaaaaaa"]}], pkg, tree, cap=2)["S1"]
    assert [x["id"] for x in capped] == ["aaaaaaaa", "bbbbbbbb"]


def test_t3_predictions_cite_only_what_was_routed_to_their_situation():
    from baselayer.distillation import situation_first as sf
    routed = {"S1": [{"id": "aaaaaaaa", "why": "seed"}], "S2": [{"id": "bbbbbbbb", "why": "seed"}]}
    claims = [{"id": "P1", "situation_id": "S1", "fact_ids": ["aaaaaaaa", "bbbbbbbb"]},
              {"id": "P2", "situation_id": "S2", "fact_ids": ["aaaaaaaa"]},
              {"id": "P3", "situation_id": "S9", "fact_ids": ["aaaaaaaa"]}]
    kept, info = sf.enforce_routing(claims, routed)
    assert [c["id"] for c in kept] == ["P1"]
    assert kept[0]["fact_ids"] == ["aaaaaaaa"]
    assert info == {"ids_stripped": 3, "claims_dropped": ["P2", "P3"]}


def test_call_structured_reads_a_named_items_key():
    from tests.test_artifact_stamps import _Stream as S

    class C:
        def __init__(self):
            self.messages = self

        def stream(self, **kw):
            return S(NS(content=[NS(type="tool_use", name="emit_situations",
                                    input={"situations": [{"id": "S1", "fact_ids": ["aaaaaaaa"]}]})],
                        stop_reason="tool_use", stop_details=None,
                        usage=NS(input_tokens=1, output_tokens=1)))
    data, i, o = afp.call_structured(C(), "claude-opus-5-5", "p", {"type": "object"},
                                     {"aaaaaaaa"}, tool_name="emit_situations",
                                     items_key="situations")
    assert data["situations"][0]["id"] == "S1"


def test_t3_step1_usage_is_on_disk_before_step3_and_step3_can_resume(monkeypatch, tmp_path):
    """A run stopped between the steps must leave step 1's usage on disk, and --resume-step3
    must reuse the saved situations without calling step 1 again."""
    from baselayer.distillation import situation_first as sf
    from baselayer.distillation import spend
    t = _pkg_tree()
    pkg = asm.assemble([t])
    pp = tmp_path / "p.json"
    pp.write_text(json.dumps(pkg), encoding="utf-8")
    db = _spans_db(tmp_path)
    calls = []

    class C:
        def __init__(self, *a, **k):
            self.messages = self

        def stream(self, **kw):
            name = kw["tools"][0]["name"]
            calls.append(name)
            if name == "emit_situations":
                inp = {"situations": [{"id": "S1", "name": "N", "active_when": "w", "why": "y",
                                       "fact_ids": ["aaaaaaaa"]}]}
            else:
                raise SystemExit("stopped before step 3")
            return _Stream(NS(content=[NS(type="tool_use", name=name, input=inp)],
                              stop_reason="tool_use", stop_details=None,
                              usage=NS(input_tokens=100, output_tokens=50)))
    monkeypatch.setattr("anthropic.Anthropic", C)
    monkeypatch.setenv("BASELAYER_RATES_CONFIRMED", spend.RATES_AS_OF)
    argv = ["sf", "--package", str(pp), "--db", str(db), "--outdir", str(tmp_path / "o"),
            "--confirm-spend", "50"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit, match="stopped before step 3"):
        sf.main()
    saved = json.loads((tmp_path / "o" / "situations.json").read_text(encoding="utf-8"))
    assert saved["usage_step1"]["input_tokens"] == 100
    assert saved["cost_usd_step1"] == pytest.approx(100 / 1e6 * 4 + 50 / 1e6 * 20)
    calls.clear()
    monkeypatch.setattr(sys, "argv", argv + ["--resume-step3"])
    with pytest.raises(SystemExit, match="stopped before step 3"):
        sf.main()
    assert calls == ["emit_layer"]
