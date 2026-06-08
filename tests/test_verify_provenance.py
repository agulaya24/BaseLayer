"""
Tests for verify_provenance.py — the four-check verifier behind `baselayer verify`.

Covers:
  1. Vector proximity     -- vector_audit()
  2. Recurrence gating    -- _check_recurrence()
  3. Cross-domain span    -- _check_cross_domain()
  4. NLI entailment       -- nli_entailment_check()

Plus a smoke test that runs the four checks against a small fixture corpus
and asserts the verifier returns a structured per-claim audit report.

All tests run offline. The NLI cross-encoder is mocked. The ChromaDB
collection is mocked. The embedding model is mocked. SQLite uses a
per-test temp database.
"""

import contextlib
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from baselayer.init_database import init_database


# ============================================================
# SHARED FIXTURES
# ============================================================

@pytest.fixture
def verify_db(tmp_path):
    """Initialized SQLite DB with a small fact corpus suited to the four checks.

    Facts:
        f-recurring-bio:    biography, recurrence 8        (passes recurrence)
        f-recurring-value:  value,     recurrence 5        (passes recurrence)
        f-rare-interest:    interest,  recurrence 1        (fails recurrence)
        f-recurring-style:  style,     recurrence 6        (passes recurrence)
    """
    db_path = tmp_path / "verify.db"
    init_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = [
        ("f-recurring-bio",    "Works in AI industry",            "biography", 8, 8),
        ("f-recurring-value",  "Values quality over speed",       "value",     5, 5),
        ("f-rare-interest",    "Mentioned hiking once",           "interest",  1, 1),
        ("f-recurring-style",  "Prefers terse direct prose",      "style",     6, 6),
    ]
    for fid, txt, cat, rc, wr in rows:
        conn.execute(
            """
            INSERT INTO memory_facts (
                id, fact_text, category, recurrence_count, windowed_recurrence,
                knowledge_tier, temporal_state, source
            ) VALUES (?, ?, ?, ?, ?, 'identity', 'present', 'extraction')
            """,
            (fid, txt, cat, rc, wr),
        )
    conn.commit()
    yield conn, db_path
    conn.close()


def _patch_get_db(db_path):
    """Return a patcher that makes verify_provenance.get_db open the temp DB."""
    def _factory(_path=None):
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c
    return patch("baselayer.verify_provenance.get_db", side_effect=_factory)


# ============================================================
# 1. VECTOR PROXIMITY -- vector_audit()
# ============================================================

class TestVectorProximity:
    """Cited fact IDs versus top-N most similar facts retrieved from ChromaDB."""

    LAYER_TEXT = (
        "## Injectable Block\n"
        "\n"
        "**A1. COHERENCE**\n"
        "Reality is knowable and coherent. Honest reasoning is non negotiable.\n"
        "provenance: [F-f-recurring-bio, F-f-recurring-value]\n"
    )

    def _mock_collection(self, vector_ids, distances=None):
        """Build a fake ChromaDB collection that returns the given IDs."""
        if distances is None:
            distances = [0.1] * len(vector_ids)
        coll = MagicMock()
        coll.query.return_value = {
            "ids": [vector_ids],
            "distances": [distances],
        }
        return coll

    def _mock_embedding_model(self):
        model = MagicMock()
        encoded = MagicMock()
        encoded.tolist.return_value = [[0.0] * 8]
        model.encode.return_value = encoded
        return model

    def test_vector_proximity_passes_when_cited_facts_appear_in_top_n(self, verify_db):
        """Happy path: cited facts are present in the vector top-N retrieval."""
        _, db_path = verify_db
        # Top-N includes both cited facts plus three unrelated neighbors
        coll = self._mock_collection([
            "f-recurring-bio",
            "f-recurring-value",
            "f-rare-interest",
            "f-recurring-style",
            "f-other",
        ])
        with _patch_get_db(db_path), \
             patch("baselayer.verify_provenance._get_layer_text", return_value=self.LAYER_TEXT), \
             patch("baselayer.verify_provenance._get_chroma_facts_collection", return_value=coll), \
             patch("baselayer.api_client.get_embedding_model", return_value=self._mock_embedding_model()):
            from baselayer.verify_provenance import vector_audit
            results = vector_audit("ANCHORS")

        assert len(results) == 1
        r = results[0]
        assert r["claim_id"] == "A1"
        # Both cited facts should appear in the overlap with the vector top-N
        assert set(r["overlap_ids"]) == {"f-recurring-bio", "f-recurring-value"}
        assert r["citation_recall"] == pytest.approx(1.0)
        assert r["vector_precision"] > 0.0

    def test_vector_proximity_fails_when_no_cited_facts_in_top_n(self, verify_db):
        """Fail path: none of the cited facts appear in the vector top-N retrieval."""
        _, db_path = verify_db
        # Top-N contains only unrelated facts
        coll = self._mock_collection([
            "f-rare-interest",
            "f-recurring-style",
            "f-unrelated-1",
            "f-unrelated-2",
        ])
        with _patch_get_db(db_path), \
             patch("baselayer.verify_provenance._get_layer_text", return_value=self.LAYER_TEXT), \
             patch("baselayer.verify_provenance._get_chroma_facts_collection", return_value=coll), \
             patch("baselayer.api_client.get_embedding_model", return_value=self._mock_embedding_model()):
            from baselayer.verify_provenance import vector_audit
            results = vector_audit("ANCHORS")

        assert len(results) == 1
        r = results[0]
        assert r["overlap_ids"] == []
        assert r["citation_recall"] == 0.0
        assert r["vector_precision"] == 0.0


# ============================================================
# 2. RECURRENCE GATING -- _check_recurrence()
# ============================================================

class TestRecurrenceGating:
    """Cited facts must clear the recurrence threshold (default 3)."""

    def test_recurrence_passes_for_high_recurrence_fact(self, verify_db):
        conn, _ = verify_db
        from baselayer.verify_provenance import _check_recurrence, RECURRENCE_THRESHOLD

        result, evidence = _check_recurrence(conn, "f-recurring-bio")
        assert result == 1
        assert "recurrence=8" in evidence
        assert RECURRENCE_THRESHOLD == 3  # contract check; tests assume threshold of 3

    def test_recurrence_fails_for_one_off_fact(self, verify_db):
        conn, _ = verify_db
        from baselayer.verify_provenance import _check_recurrence

        result, evidence = _check_recurrence(conn, "f-rare-interest")
        assert result == 0
        assert "recurrence=1" in evidence
        assert "threshold=3" in evidence

    def test_recurrence_fails_for_missing_fact(self, verify_db):
        conn, _ = verify_db
        from baselayer.verify_provenance import _check_recurrence

        result, evidence = _check_recurrence(conn, "f-does-not-exist")
        assert result == 0
        assert "not found" in evidence


# ============================================================
# 3. CROSS-DOMAIN SPAN -- _check_cross_domain()
# ============================================================

class TestCrossDomainSpan:
    """Cited facts must span at least two distinct categories."""

    def test_cross_domain_passes_for_multi_category_citation(self, verify_db):
        conn, _ = verify_db
        from baselayer.verify_provenance import _check_cross_domain

        result, evidence = _check_cross_domain(
            conn, ["f-recurring-bio", "f-recurring-value", "f-recurring-style"]
        )
        assert result == 1
        # All three categories should be reported in the evidence
        assert "biography" in evidence
        assert "value" in evidence
        assert "style" in evidence

    def test_cross_domain_fails_for_single_category_citation(self, verify_db):
        """Single-category overfit -- only one distinct category among cited facts."""
        conn, db_path = verify_db
        # Add a second biography-tagged fact so we have two facts in one category
        conn.execute(
            "INSERT INTO memory_facts (id, fact_text, category, recurrence_count, "
            "windowed_recurrence, knowledge_tier, source) VALUES "
            "('f-bio-2', 'Born in 1985', 'biography', 4, 4, 'identity', 'extraction')"
        )
        conn.commit()
        from baselayer.verify_provenance import _check_cross_domain

        result, evidence = _check_cross_domain(conn, ["f-recurring-bio", "f-bio-2"])
        assert result == 0
        assert "Only 1 category" in evidence
        assert "biography" in evidence

    def test_cross_domain_fails_for_empty_input(self, verify_db):
        conn, _ = verify_db
        from baselayer.verify_provenance import _check_cross_domain

        result, evidence = _check_cross_domain(conn, [])
        assert result == 0
        assert "No fact IDs" in evidence


# ============================================================
# 4. NLI ENTAILMENT -- nli_entailment_check()
# ============================================================

class TestNliEntailment:
    """Local NLI entailment over (premise=fact, hypothesis=claim) pairs."""

    @staticmethod
    def _mock_nli_model(scores_per_pair):
        """scores_per_pair: list of [contradiction, entailment, neutral] triples."""
        import numpy as np
        model = MagicMock()
        model.predict.return_value = np.array(scores_per_pair, dtype=float)
        return model

    def test_nli_supported_when_entailment_high(self):
        from baselayer.verify_provenance import nli_entailment_check, _reset_nli_cache

        _reset_nli_cache()
        # One fact, high entailment score
        mock = self._mock_nli_model([[0.05, 0.92, 0.03]])
        with patch("baselayer.verify_provenance._get_nli_model", return_value=mock):
            result = nli_entailment_check(
                claim_text="This person values directness",
                fact_texts=[{"fact_id": "f1", "fact_text": "Prefers direct feedback"}],
            )

        assert result["verdict"] == "SUPPORTED"
        assert result["aggregate_entailment"] == pytest.approx(0.92)
        assert len(result["per_fact"]) == 1
        assert result["per_fact"][0]["fact_id"] == "f1"

    def test_nli_unsupported_when_contradiction_high(self):
        from baselayer.verify_provenance import nli_entailment_check, _reset_nli_cache

        _reset_nli_cache()
        # Both facts are mostly contradictory; no entailment signal anywhere
        mock = self._mock_nli_model([
            [0.85, 0.05, 0.10],
            [0.78, 0.07, 0.15],
        ])
        with patch("baselayer.verify_provenance._get_nli_model", return_value=mock):
            result = nli_entailment_check(
                claim_text="This person avoids confrontation",
                fact_texts=[
                    {"fact_id": "f1", "fact_text": "Confronts disagreement directly"},
                    {"fact_id": "f2", "fact_text": "Pushes back on bad ideas in meetings"},
                ],
            )

        assert result["verdict"] == "UNSUPPORTED"
        assert result["aggregate_entailment"] < 0.3
        assert result["aggregate_contradiction"] >= 0.78

    def test_nli_skipped_when_model_unavailable(self):
        from baselayer.verify_provenance import nli_entailment_check, _reset_nli_cache

        _reset_nli_cache()
        with patch("baselayer.verify_provenance._get_nli_model", return_value=None):
            result = nli_entailment_check(
                claim_text="Some claim",
                fact_texts=[{"fact_id": "f1", "fact_text": "some fact"}],
            )

        assert result["verdict"] == "SKIPPED"
        assert "not available" in result["error"]


# ============================================================
# 5. INTEGRATION SMOKE TEST -- run_full_verification()
# ============================================================

class TestFourCheckSmoke:
    """End to end: run the four checks against a small fixture corpus.

    Asserts the verifier returns a structured per-claim audit report
    covering vector proximity, recurrence, cross-domain span, and NLI.
    """

    LAYER_TEXT = (
        "## Injectable Block\n"
        "\n"
        "**A1. COHERENCE**\n"
        "Honest reasoning across domains is non negotiable.\n"
        "provenance: [F-f-recurring-bio, F-f-recurring-value, F-f-recurring-style]\n"
        "\n"
        "**A2. SINGLE_DOMAIN**\n"
        "A claim that draws only from one domain.\n"
        "provenance: [F-f-rare-interest]\n"
    )

    def test_smoke_full_verification_returns_structured_report(self, verify_db):
        _, db_path = verify_db

        # Mock the vector retrieval: A1 cited facts appear in top-N; A2 cited fact also appears.
        coll = MagicMock()
        coll.query.return_value = {
            "ids": [[
                "f-recurring-bio", "f-recurring-value", "f-recurring-style",
                "f-rare-interest", "f-other",
            ]],
            "distances": [[0.1, 0.15, 0.2, 0.3, 0.5]],
        }

        emb_model = MagicMock()
        encoded = MagicMock()
        encoded.tolist.return_value = [[0.0] * 8]
        emb_model.encode.return_value = encoded

        # Mock NLI: high entailment for A1, low for A2
        import numpy as np
        nli_mock = MagicMock()
        # A1 has 3 facts, A2 has 1 fact -- nli_mock.predict is called per claim
        nli_mock.predict.side_effect = [
            np.array([[0.05, 0.85, 0.10], [0.10, 0.80, 0.10], [0.05, 0.90, 0.05]]),
            np.array([[0.70, 0.10, 0.20]]),
        ]

        from baselayer.verify_provenance import _reset_nli_cache, _reset_chroma_cache
        _reset_nli_cache()
        _reset_chroma_cache()

        with _patch_get_db(db_path), \
             patch("baselayer.verify_provenance._get_layer_text", return_value=self.LAYER_TEXT), \
             patch("baselayer.verify_provenance._get_chroma_facts_collection", return_value=coll), \
             patch("baselayer.api_client.get_embedding_model", return_value=emb_model), \
             patch("baselayer.verify_provenance._get_nli_model", return_value=nli_mock):
            from baselayer.verify_provenance import run_full_verification
            report = run_full_verification("ANCHORS", include_nli=True)

        # Top-level structure
        assert "vector" in report
        assert "claims" in report
        assert "coverage" in report
        assert "nli" in report

        # Vector proximity: A1's three cited facts overlap with the top-N
        vector_anchors = report["vector"]["ANCHORS"]
        a1_vec = next(v for v in vector_anchors if v["claim_id"] == "A1")
        assert set(a1_vec["overlap_ids"]) >= {
            "f-recurring-bio", "f-recurring-value", "f-recurring-style"
        }
        assert a1_vec["citation_recall"] == pytest.approx(1.0)

        # Claim verification: structured per-type counts present
        claims = report["claims"]
        assert claims["total"] > 0
        assert "by_type" in claims
        assert "recurrence" in claims["by_type"]
        assert "cross_domain" in claims["by_type"]

        # Recurrence: 3 of 4 cited facts pass (the rare one fails)
        rec_counts = claims["by_type"]["recurrence"]
        assert rec_counts["passed"] == 3
        assert rec_counts["failed"] == 1

        # Cross-domain: A1 spans 3 categories (pass), A2 has 1 category (fail)
        cd_counts = claims["by_type"]["cross_domain"]
        assert cd_counts["passed"] == 1
        assert cd_counts["failed"] == 1

        # NLI: A1 SUPPORTED, A2 UNSUPPORTED
        nli_summary = report["nli"]["summary"]
        assert nli_summary["total"] == 2
        assert nli_summary["supported"] == 1
        assert nli_summary["unsupported"] == 1
