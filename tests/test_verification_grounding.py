"""
Verification reads each cited fact's `grounding` and each span's `evidence_kind`
(TURN_CONTRACT.md §4a, §5), so a specification built with --include-record-only
shows, per claim, how much of it rests on record rows.

Per claim: live cited facts by grounding (`prose`, `record_only`, and
`unstamped` for NULL, which is a fact stamped before the column or a legacy
fact, never read as prose), and their spans by evidence_kind (`prose`,
`record`, `missing`). Record spans inside prose-grounded facts are counted too.
A claim citing any record-only fact gets a `record_grounded` finding naming
those facts: `warn` when every live cited fact is record-only, `info` otherwise.

Synthetic data only, no model call.
"""
import json
import sqlite3
from pathlib import Path

from baselayer.verification.deterministic import check_grounding
from baselayer.verification.spec_io import load_spec

from tests.test_verification import (ScriptedJudge, claim, make_spec, open_corpus,
                                     real_schema_db, run_fake, G_OK, LEGACY)

REC = "9d9d0001-0000-0000-0000-000000000001"      # record_only: every span a record
MIX = "9e9e0001-0000-0000-0000-000000000001"      # prose, one of its two spans a record
REC2 = "9f9f0001-0000-0000-0000-000000000001"     # record_only, second one


def _db(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    db = corpus / "data" / "database" / "memory.db"
    real_schema_db(db)          # G_OK: gated, spans without evidence_kind, grounding NULL
    c = sqlite3.connect(str(db))
    c.execute("UPDATE turns SET text = ? WHERE turn_id = 'cv:2'",
              ("I log every missed watering.\n2024-03-01\t06:10\t2.5 L",))
    c.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id) "
              "VALUES (?, 'user waters before sunrise', 'habit', 'cv')", (LEGACY,))

    def fact(fid, text, spans, grounding):
        c.execute("INSERT INTO memory_facts (id, fact_text, category, source_conversation_id, "
                  "source_turn_id, evidence_spans, turn_contract_version, grounding) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  (fid, text, "habit", "cv", spans[0]["turn_id"], json.dumps(spans),
                   "turn-contract/1", grounding))
    row = {"turn_id": "cv:2", "span": "2024-03-01\t06:10\t2.5 L", "evidence_kind": "record"}
    fact(REC, "user logs watering volumes", [row], "record_only")
    fact(REC2, "user logs watering times", [row], "record_only")
    fact(MIX, "user logs every watering",
         [{"turn_id": "cv:2", "span": "log every missed watering", "evidence_kind": "prose"}, row],
         "prose")
    c.commit()
    c.close()
    return corpus


def _spec(tmp_path, layers):
    d = tmp_path / "spec"
    make_spec(d, layers)
    return d


def test_grounding_and_evidence_kind_are_counted_per_claim(tmp_path):
    corpus = _db(tmp_path)
    spec_dir = _spec(tmp_path, {"anchors": [claim("A1", "Keeps a log", [REC, MIX, G_OK, LEGACY]),
                                            claim("A2", "Logs only", [REC, REC2]),
                                            claim("A3", "Routine", [G_OK])]})
    per, findings = check_grounding(load_spec(spec_dir, "t"), open_corpus(corpus, tmp_path / "o"))
    a1 = per["t:A1"]
    assert a1["available"] is True and a1["live"] == 4
    assert a1["facts"] == {"prose": 1, "record_only": 1, "unstamped": 2}
    # G_OK carries two spans with no evidence_kind; MIX one prose, one record; REC one record
    assert a1["spans"] == {"prose": 1, "record": 2, "missing": 2}
    assert a1["record_only_fact_ids"] == ["F-" + REC[:8]]
    assert per["t:A2"]["facts"] == {"prose": 0, "record_only": 2, "unstamped": 0}
    assert per["t:A3"]["facts"] == {"prose": 0, "record_only": 0, "unstamped": 1}

    by_claim = {tuple(f["claims"]): f for f in findings if f["check"] == "record_grounded"}
    assert set(by_claim) == {("t:A1",), ("t:A2",)}
    assert by_claim[("t:A1",)]["severity"] == "info"
    assert by_claim[("t:A1",)]["fact_ids"] == ["F-" + REC[:8]]
    assert by_claim[("t:A2",)]["severity"] == "warn"
    assert sorted(by_claim[("t:A2",)]["fact_ids"]) == sorted(["F-" + REC[:8], "F-" + REC2[:8]])


def test_a_spec_citing_no_record_only_fact_raises_nothing(tmp_path):
    corpus = _db(tmp_path)
    spec_dir = _spec(tmp_path, {"anchors": [claim("A1", "Routine", [G_OK, MIX])]})
    per, findings = check_grounding(load_spec(spec_dir, "t"), open_corpus(corpus, tmp_path / "o"))
    assert findings == []
    assert per["t:A1"]["facts"]["record_only"] == 0
    assert per["t:A1"]["spans"]["record"] == 1      # the mixed fact's record span still shows


def test_full_run_reports_record_grounding_in_summary_and_markdown(tmp_path):
    corpus = _db(tmp_path)
    spec_dir = _spec(tmp_path, {"anchors": [claim("A1", "Keeps a log", [REC, MIX]),
                                            claim("A2", "Logs only", [REC, REC2])]})
    rc, rep, _ = run_fake(tmp_path, corpus, spec_dir, ScriptedJudge(), ["--checks", "support"])
    s = rep["summary"]["record_grounding"]
    assert s == {"record_only_cited_facts": 2, "claims_citing_record_only": 2,
                 "claims_resting_only_on_record_only": 1,
                 "live_citations_by_grounding": {"prose": 1, "record_only": 3, "unstamped": 0},
                 "spans_by_evidence_kind": {"prose": 1, "record": 4, "missing": 0}}
    assert rep["claims"]["t:A1"]["grounding"]["facts"]["record_only"] == 1
    md = (tmp_path / "o" / "t.verification.md").read_text(encoding="utf-8")
    assert "record_grounded" in md and "record_only" in md


def test_database_without_the_grounding_column(tmp_path):
    """A legacy database has no `grounding` column: available is False, every
    live fact counts as unstamped, nothing is flagged."""
    from tests.test_verification import default_spec, make_db
    corpus = tmp_path / "corpus"
    make_db(corpus / "data" / "database" / "memory.db")
    spec_dir = tmp_path / "spec"
    default_spec(spec_dir)
    c = open_corpus(corpus, tmp_path / "o")
    assert "grounding" not in c.fact_cols
    per, findings = check_grounding(load_spec(spec_dir, "t"), c)
    assert findings == []
    assert all(p["available"] is False and p["facts"]["record_only"] == 0 for p in per.values())
    assert any(p["facts"]["unstamped"] for p in per.values())
