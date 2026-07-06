"""
Tests for the persistent-memory primitives: live_extract, contradiction_pipeline,
correction_gate.

Covers: live_extract change-manifest shape, contradiction classification
dispatch, and correction-gate filtering. All API calls are mocked; no real
API spend.
"""

import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest


def _insert_fact(conn, fact_id, fact_text, conv_id="conv-001",
                 fact_class="state", superseded_by=None, subject="user"):
    """Insert a minimal fact row for testing."""
    now = time.time()
    conn.execute("""
        INSERT INTO memory_facts (
            id, fact_text, category, confidence, source_conversation_id,
            created_at, updated_at, superseded_by, subject, fact_class,
            predicate, object_text
        ) VALUES (?, ?, 'value', 0.9, ?, ?, ?, ?, ?, ?, 'values', 'testing')
    """, (fact_id, fact_text, conv_id, now, now, superseded_by, subject,
          fact_class))
    conn.commit()


# ===========================================================================
# Correction gate
# ===========================================================================

class TestCorrectionGateFiltering:
    """filter_facts: superseded and manually corrected facts are removed."""

    def test_empty_input_returns_empty(self, populated_db):
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        assert filter_facts(conn, []) == []

    def test_superseded_facts_filtered(self, populated_db):
        """fact-004 is superseded in the fixture; it must not pass."""
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        result = filter_facts(
            conn, ["fact-001", "fact-002", "fact-003", "fact-004"]
        )
        assert result == ["fact-001", "fact-002", "fact-003"]

    def test_unknown_ids_filtered(self, populated_db):
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        assert filter_facts(conn, ["no-such-fact"]) == []

    def test_delete_correction_filters_fact(self, populated_db):
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        conn.execute("""
            INSERT INTO user_corrections (id, correction_type, original_fact_id, created_at)
            VALUES ('corr-1', 'delete', 'fact-001', ?)
        """, (time.time(),))
        conn.commit()
        result = filter_facts(conn, ["fact-001", "fact-002"])
        assert result == ["fact-002"]

    def test_correction_type_matched_case_insensitively(self, populated_db):
        """Older tooling wrote uppercase correction types."""
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        conn.execute("""
            INSERT INTO user_corrections (id, correction_type, original_fact_id, created_at)
            VALUES ('corr-2', 'DELETE', 'fact-002', ?)
        """, (time.time(),))
        conn.commit()
        assert filter_facts(conn, ["fact-002"]) == []

    def test_flag_correction_does_not_filter(self, populated_db):
        """Flag corrections annotate; they do not remove facts from serving."""
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        conn.execute("""
            INSERT INTO user_corrections (id, correction_type, original_fact_id, created_at)
            VALUES ('corr-3', 'flag', 'fact-001', ?)
        """, (time.time(),))
        conn.commit()
        assert filter_facts(conn, ["fact-001"]) == ["fact-001"]

    def test_missing_corrections_table_tolerated(self, tmp_path):
        """A database without user_corrections still filters on supersession."""
        from baselayer.correction_gate import filter_facts
        conn = sqlite3.connect(str(tmp_path / "bare.db"))
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE memory_facts (
                id TEXT PRIMARY KEY, fact_text TEXT, superseded_by TEXT
            )
        """)
        conn.execute("INSERT INTO memory_facts VALUES ('f1', 'active fact', NULL)")
        conn.execute("INSERT INTO memory_facts VALUES ('f2', 'old fact', 'f1')")
        conn.commit()
        try:
            assert filter_facts(conn, ["f1", "f2"]) == ["f1"]
        finally:
            conn.close()

    def test_large_id_list_chunked(self, populated_db):
        """More IDs than SQLite's parameter limit must not raise."""
        from baselayer.correction_gate import filter_facts
        conn, _ = populated_db
        ids = ["fact-001", "fact-002"] + [f"missing-{i}" for i in range(1500)]
        assert filter_facts(conn, ids) == ["fact-001", "fact-002"]


class TestCorrectionGateActiveFacts:
    """get_active_facts: full active-fact retrieval."""

    def test_returns_dicts_excluding_superseded(self, populated_db):
        from baselayer.correction_gate import get_active_facts
        conn, _ = populated_db
        facts = get_active_facts(conn)
        ids = {f["id"] for f in facts}
        assert "fact-004" not in ids
        assert {"fact-001", "fact-002", "fact-003"} <= ids
        assert all(isinstance(f, dict) for f in facts)

    def test_respects_manual_corrections(self, populated_db):
        from baselayer.correction_gate import get_active_facts
        conn, _ = populated_db
        conn.execute("""
            INSERT INTO user_corrections (id, correction_type, original_fact_id, created_at)
            VALUES ('corr-4', 'supersede', 'fact-003', ?)
        """, (time.time(),))
        conn.commit()
        ids = {f["id"] for f in get_active_facts(conn)}
        assert "fact-003" not in ids

    def test_subject_filter(self, populated_db):
        from baselayer.correction_gate import get_active_facts
        conn, _ = populated_db
        _insert_fact(conn, "fact-partner", "Partner enjoys hiking",
                     subject="partner")
        subjects = {f["subject"] for f in get_active_facts(conn, subject="partner")}
        assert subjects == {"partner"}


# ===========================================================================
# Contradiction pipeline
# ===========================================================================

def _api_response(text):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


class TestClassifyContradiction:
    """classify_contradiction: LLM output parsing and failure degradation."""

    def test_valid_json_passthrough(self):
        from baselayer.contradiction_pipeline import classify_contradiction
        with patch("baselayer.api_client.call_api",
                   return_value=_api_response(
                       '{"judgment": "contradiction", "confidence": 0.9, '
                       '"reasoning": "only one residence"}')):
            result = classify_contradiction("lives in NYC", "lives in SF")
        assert result["judgment"] == "contradiction"
        assert result["confidence"] == 0.9

    def test_json_embedded_in_prose(self):
        from baselayer.contradiction_pipeline import classify_contradiction
        with patch("baselayer.api_client.call_api",
                   return_value=_api_response(
                       'Here is my answer: {"judgment": "enrichment", '
                       '"confidence": 0.8, "reasoning": "adds detail"}')):
            result = classify_contradiction("works at Acme", "engineer at Acme")
        assert result["judgment"] == "enrichment"

    def test_unknown_judgment_degrades_to_coexistent(self):
        from baselayer.contradiction_pipeline import classify_contradiction
        with patch("baselayer.api_client.call_api",
                   return_value=_api_response('{"judgment": "supersede"}')):
            result = classify_contradiction("a", "b")
        assert result["judgment"] == "coexistent"
        assert result["confidence"] == 0.0

    def test_api_error_degrades_to_coexistent(self):
        from baselayer.contradiction_pipeline import classify_contradiction
        with patch("baselayer.api_client.call_api",
                   side_effect=RuntimeError("api down")):
            result = classify_contradiction("a", "b")
        assert result["judgment"] == "coexistent"
        assert result["confidence"] == 0.0


class TestExecuteJudgment:
    """execute_judgment: database effects per verdict."""

    def test_contradiction_supersedes_existing_fact(self, populated_db):
        from baselayer.contradiction_pipeline import execute_judgment
        conn, _ = populated_db
        result = execute_judgment(
            conn, {"judgment": "contradiction"}, "fact-002", "fact-003"
        )
        assert result["action"] == "superseded"
        row = conn.execute(
            "SELECT superseded_by, temporal_state FROM memory_facts WHERE id = 'fact-003'"
        ).fetchone()
        assert row["superseded_by"] == "fact-002"
        assert row["temporal_state"] == "past"

    def test_ambiguous_queues_probe(self, populated_db):
        from baselayer.contradiction_pipeline import execute_judgment
        conn, _ = populated_db
        result = execute_judgment(
            conn, {"judgment": "ambiguous", "reasoning": "unclear"},
            "fact-001", "fact-002",
        )
        assert result["action"] == "probe_queued"
        row = conn.execute(
            "SELECT * FROM probe_queue WHERE id = ?", (result["probe_id"],)
        ).fetchone()
        assert row["new_fact_id"] == "fact-001"
        assert row["existing_fact_id"] == "fact-002"
        assert row["status"] == "pending"
        assert row["created_at"] is not None
        assert row["new_fact_text"]
        assert row["existing_fact_text"]

    @pytest.mark.parametrize("verdict", ["coexistent", "enrichment"])
    def test_non_conflict_verdicts_take_no_action(self, populated_db, verdict):
        from baselayer.contradiction_pipeline import execute_judgment
        conn, _ = populated_db
        result = execute_judgment(
            conn, {"judgment": verdict}, "fact-001", "fact-002"
        )
        assert result == {"action": "no_action", "verdict": verdict}
        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE id = 'fact-002'"
        ).fetchone()
        assert row["superseded_by"] is None


class TestProcessNewStateFacts:
    """process_new_state_facts: dispatch, counting, and skip rules."""

    def _fact(self, fact_id, text, fact_class="state"):
        return {"fact_id": fact_id, "fact_text": text, "fact_class": fact_class}

    def test_dispatch_counts_all_verdicts(self, populated_db):
        import baselayer.contradiction_pipeline as cp
        conn, _ = populated_db

        candidates = [
            {"fact_id": "fact-001", "fact_text": "existing 1", "similarity": 0.9},
            {"fact_id": "fact-002", "fact_text": "existing 2", "similarity": 0.8},
            {"fact_id": "fact-003", "fact_text": "existing 3", "similarity": 0.7},
        ]
        verdicts = iter([
            {"judgment": "contradiction", "confidence": 0.9, "reasoning": "r"},
            {"judgment": "ambiguous", "confidence": 0.5, "reasoning": "r"},
            {"judgment": "coexistent", "confidence": 0.9, "reasoning": "r"},
        ])
        _insert_fact(conn, "fact-new", "New state fact")

        with patch.object(cp, "find_contradicting_facts", return_value=candidates), \
             patch.object(cp, "classify_contradiction",
                          side_effect=lambda a, b: next(verdicts)):
            stats = cp.process_new_state_facts(
                conn, [self._fact("fact-new", "New state fact")],
                chroma_client=MagicMock(), embed_model=MagicMock(),
            )

        assert stats["processed"] == 1
        assert stats["contradictions"] == 1
        assert stats["ambiguous"] == 1
        assert stats["probes_queued"] == 1
        assert stats["coexistent"] == 1
        assert stats["enrichments"] == 0

        # The contradiction verdict must have superseded the first candidate.
        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE id = 'fact-001'"
        ).fetchone()
        assert row["superseded_by"] == "fact-new"

    def test_events_and_incomplete_facts_skipped(self, populated_db):
        import baselayer.contradiction_pipeline as cp
        conn, _ = populated_db
        with patch.object(cp, "find_contradicting_facts") as mock_find:
            stats = cp.process_new_state_facts(
                conn,
                [self._fact("fact-e", "Graduated in 2010", fact_class="event"),
                 {"fact_text": "missing id", "fact_class": "state"}],
                chroma_client=MagicMock(), embed_model=MagicMock(),
            )
        assert stats["processed"] == 0
        mock_find.assert_not_called()


class TestFindContradictingFacts:
    """find_contradicting_facts: similarity search and state-fact filtering."""

    def test_no_embeddings_returns_empty(self, populated_db):
        from baselayer.contradiction_pipeline import find_contradicting_facts
        conn, _ = populated_db
        result = find_contradicting_facts(
            conn, {"fact_id": "x", "fact_text": "text"}, None, None
        )
        assert result == []

    def test_filters_self_threshold_and_superseded(self, populated_db):
        from baselayer.contradiction_pipeline import find_contradicting_facts
        conn, _ = populated_db

        embed_model = MagicMock()
        embed_model.encode.return_value = MagicMock(
            tolist=MagicMock(return_value=[[0.1] * 8])
        )
        collection = MagicMock()
        collection.query.return_value = {
            # fact-001: active state, close (kept)
            # fact-004: superseded (dropped by DB filter)
            # fact-002: too distant (dropped by threshold)
            # fact-new: self (dropped)
            "documents": [["doc 1", "doc 4", "doc 2", "doc self"]],
            "metadatas": [[{"fact_id": "fact-001"}, {"fact_id": "fact-004"},
                           {"fact_id": "fact-002"}, {"fact_id": "fact-new"}]],
            "distances": [[0.4, 0.4, 1.4, 0.0]],
        }
        chroma_client = MagicMock()
        chroma_client.get_collection.return_value = collection

        result = find_contradicting_facts(
            conn, {"fact_id": "fact-new", "fact_text": "new text"},
            chroma_client, embed_model,
        )
        assert [c["fact_id"] for c in result] == ["fact-001"]
        assert result[0]["similarity"] > 0.5


# ===========================================================================
# Live extraction manifest
# ===========================================================================

class TestLiveExtractManifest:
    """extract_single: change-manifest shape across outcomes."""

    MANIFEST_KEYS = {"conversation_id", "facts_stored", "actions",
                     "contradictions_found", "probes_queued"}

    def _patched_env(self, db_path):
        return (
            patch("baselayer.config.DATABASE_FILE", db_path),
            patch("baselayer.config.PROJECT_ROOT", db_path.parent),
        )

    def test_manifest_reports_new_facts_only(self, populated_db):
        """New facts appear as ADD actions; pre-existing facts do not."""
        from baselayer.live_extract import extract_single
        conn, db_path = populated_db

        def fake_process(conv, conn_, fact_collection, embed_model, **kwargs):
            _insert_fact(conn_, "fact-live-1", "Recently started woodworking",
                         conv_id=conv["id"], fact_class="state")
            _insert_fact(conn_, "fact-live-2", "Attended a workshop in March",
                         conv_id=conv["id"], fact_class="event")
            return 2

        p1, p2 = self._patched_env(db_path)
        with p1, p2, patch("baselayer.extract_facts.process_conversation",
                           side_effect=fake_process):
            manifest = extract_single(conn, "conv-001")

        assert self.MANIFEST_KEYS <= set(manifest.keys())
        assert "error" not in manifest
        assert manifest["conversation_id"] == "conv-001"
        assert manifest["facts_stored"] == 2

        actions = manifest["actions"]
        assert {a["type"] for a in actions} == {"ADD"}
        assert {a["fact_id"] for a in actions} == {"fact-live-1", "fact-live-2"}
        # Pre-existing facts for conv-001 are not re-reported.
        assert "fact-001" not in {a["fact_id"] for a in actions}
        # Action entries carry the fields a capture proxy needs.
        for a in actions:
            assert {"type", "fact_id", "fact_text", "fact_class", "category",
                    "predicate", "object_text",
                    "source_conversation_id"} <= set(a.keys())

        # No embeddings were provided, so no contradiction checks ran.
        assert manifest["contradictions_found"] == 0
        assert manifest["probes_queued"] == 0

    def test_manifest_conversation_not_found(self, populated_db):
        from baselayer.live_extract import extract_single
        conn, db_path = populated_db
        p1, p2 = self._patched_env(db_path)
        with p1, p2:
            manifest = extract_single(conn, "no-such-conversation")
        assert manifest["error"]
        assert manifest["actions"] == []
        assert manifest["facts_stored"] == 0
        assert self.MANIFEST_KEYS <= set(manifest.keys())

    def test_manifest_noop_when_nothing_stored(self, populated_db):
        from baselayer.live_extract import extract_single
        conn, db_path = populated_db
        p1, p2 = self._patched_env(db_path)
        with p1, p2, patch("baselayer.extract_facts.process_conversation",
                           return_value=0):
            manifest = extract_single(conn, "conv-001")
        assert manifest["facts_stored"] == 0
        assert len(manifest["actions"]) == 1
        assert manifest["actions"][0]["type"] == "NOOP"

    def test_manifest_reports_extraction_failure(self, populated_db):
        """A failing extraction returns an error manifest, never raises."""
        from baselayer.live_extract import extract_single
        conn, db_path = populated_db
        p1, p2 = self._patched_env(db_path)
        with p1, p2, patch("baselayer.extract_facts.process_conversation",
                           side_effect=RuntimeError("model unavailable")):
            manifest = extract_single(conn, "conv-001")
        assert "model unavailable" in manifest["error"]
        assert manifest["actions"] == []
        assert self.MANIFEST_KEYS <= set(manifest.keys())

    def test_contradiction_hook_runs_on_new_state_facts(self, populated_db):
        """New state-facts are handed to the contradiction pipeline and the
        manifest carries its counts."""
        from baselayer.live_extract import extract_single
        conn, db_path = populated_db

        def fake_process(conv, conn_, fact_collection, embed_model, **kwargs):
            _insert_fact(conn_, "fact-live-3", "Now lives in Boston",
                         conv_id=conv["id"], fact_class="state")
            return 1

        hook_stats = {"processed": 1, "contradictions": 1, "enrichments": 0,
                      "coexistent": 0, "ambiguous": 2, "probes_queued": 2}

        p1, p2 = self._patched_env(db_path)
        with p1, p2, \
             patch("baselayer.extract_facts.process_conversation",
                   side_effect=fake_process), \
             patch("baselayer.contradiction_pipeline.process_new_state_facts",
                   return_value=hook_stats) as mock_hook:
            manifest = extract_single(
                conn, "conv-001",
                chroma_client=MagicMock(), embed_model=MagicMock(),
            )

        mock_hook.assert_called_once()
        passed_facts = mock_hook.call_args[0][1]
        assert [f["fact_id"] for f in passed_facts] == ["fact-live-3"]
        assert manifest["contradictions_found"] == 1
        assert manifest["probes_queued"] == 2

    def test_contradiction_hook_failure_does_not_break_manifest(self, populated_db):
        from baselayer.live_extract import extract_single
        conn, db_path = populated_db

        def fake_process(conv, conn_, fact_collection, embed_model, **kwargs):
            _insert_fact(conn_, "fact-live-4", "Now prefers tea over coffee",
                         conv_id=conv["id"], fact_class="state")
            return 1

        p1, p2 = self._patched_env(db_path)
        with p1, p2, \
             patch("baselayer.extract_facts.process_conversation",
                   side_effect=fake_process), \
             patch("baselayer.contradiction_pipeline.process_new_state_facts",
                   side_effect=RuntimeError("chroma offline")):
            manifest = extract_single(
                conn, "conv-001",
                chroma_client=MagicMock(), embed_model=MagicMock(),
            )
        assert manifest["facts_stored"] == 1
        assert manifest["contradictions_found"] == 0
        assert manifest["probes_queued"] == 0
