"""
Tests for author_layers.py — format_facts_for_prompt(), parse_provenance_from_layer(),
store_provenance(), cap_by_domain(), cap_by_category(), and apply_exclusion_filter().

All tests run without API keys or external services.
"""

import pytest
import sys
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch, MagicMock



# ============================================================
# FORMAT_FACTS_FOR_PROMPT
# ============================================================

class TestFormatFactsForPrompt:
    """Test fact formatting for LLM prompt injection."""

    def test_basic_formatting_with_ids(self):
        from baselayer.author_layers import format_facts_for_prompt
        facts = [
            {"id": "fact-001", "fact_text": "Works in AI industry"},
            {"id": "fact-002", "fact_text": "Values quality over speed"},
        ]
        result = format_facts_for_prompt(facts)
        assert "[F-fact-001]" in result
        assert "[F-fact-002]" in result
        assert "Works in AI industry" in result
        assert "Values quality over speed" in result

    def test_formatting_without_ids(self):
        from baselayer.author_layers import format_facts_for_prompt
        facts = [
            {"id": "fact-001", "fact_text": "Works in AI industry"},
        ]
        result = format_facts_for_prompt(facts, include_ids=False)
        assert "[F-" not in result
        assert "1. Works in AI industry" in result

    def test_numbering_starts_at_one(self):
        from baselayer.author_layers import format_facts_for_prompt
        facts = [{"id": "a", "fact_text": "First"}, {"id": "b", "fact_text": "Second"}]
        result = format_facts_for_prompt(facts)
        lines = result.strip().split("\n")
        assert lines[0].startswith("1.")
        assert lines[1].startswith("2.")

    def test_max_items_cap(self):
        from baselayer.author_layers import format_facts_for_prompt
        facts = [{"id": f"f-{i}", "fact_text": f"Fact {i}"} for i in range(200)]
        result = format_facts_for_prompt(facts, max_items=5)
        lines = result.strip().split("\n")
        assert len(lines) == 5

    def test_truncates_long_text(self):
        from baselayer.author_layers import format_facts_for_prompt
        long_text = "x" * 500
        facts = [{"id": "f1", "fact_text": long_text}]
        result = format_facts_for_prompt(facts)
        # Text should be truncated to 200 chars
        assert len(result.split("] ")[1]) <= 200

    def test_empty_facts_list(self):
        from baselayer.author_layers import format_facts_for_prompt
        result = format_facts_for_prompt([])
        assert result == ""

    def test_facts_without_id(self):
        from baselayer.author_layers import format_facts_for_prompt
        facts = [{"fact_text": "No ID fact"}]
        result = format_facts_for_prompt(facts)
        # No [F-] prefix when id is empty/missing
        assert "1. No ID fact" in result

    def test_formulation_fallback(self):
        from baselayer.author_layers import format_facts_for_prompt
        facts = [{"id": "f1", "formulation": "Anchor axiom text"}]
        result = format_facts_for_prompt(facts)
        assert "Anchor axiom text" in result


# ============================================================
# PARSE_PROVENANCE_FROM_LAYER
# ============================================================

class TestParseProvenanceFromLayer:
    """Test parsing provenance citations from generated layer text."""

    def test_basic_parsing(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**A1. COHERENCE**
Some axiom text here.
provenance: [F-1204, F-2891]

**A2. OWNERSHIP**
Another axiom.
provenance: [F-501, F-602]
"""
        results = parse_provenance_from_layer("ANCHORS", text)
        assert len(results) == 2
        assert results[0]["claim_id"] == "A1"
        assert results[0]["claim_text"] == "COHERENCE"
        assert results[0]["fact_ids"] == ["1204", "2891"]

    def test_predictions_parsing(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**P1. ANALYSIS-PARALYSIS**
When facing complex decisions...
provenance: [F-100, F-200, F-300]
"""
        results = parse_provenance_from_layer("PREDICTIONS", text)
        assert len(results) == 1
        assert results[0]["claim_id"] == "P1"
        assert results[0]["fact_ids"] == ["100", "200", "300"]

    def test_core_parsing_with_c_and_m_ids(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**M1. COMMUNICATION_APPROACH**
How they communicate.
provenance: [F-10, F-20]

**C1. TRADING CONTEXT**
Trading patterns.
provenance: [F-301, F-455]
"""
        results = parse_provenance_from_layer("CORE", text)
        assert len(results) == 2
        assert results[0]["claim_id"] == "M1"
        assert results[1]["claim_id"] == "C1"

    def test_no_provenance_returns_empty(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = "Just some text without any provenance markers."
        results = parse_provenance_from_layer("ANCHORS", text)
        assert results == []

    def test_provenance_without_claim_id_ignored(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """Some text without a claim header.
provenance: [F-100, F-200]
"""
        results = parse_provenance_from_layer("ANCHORS", text)
        assert results == []

    def test_multiple_provenance_lines_per_claim(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**A1. COHERENCE**
Part one.
provenance: [F-100]
Part two.
provenance: [F-200, F-300]
"""
        results = parse_provenance_from_layer("ANCHORS", text)
        # Both provenance lines belong to A1
        assert len(results) == 2
        assert all(r["claim_id"] == "A1" for r in results)

    def test_fact_ids_without_f_prefix(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**A1. TEST**
provenance: [100, 200]
"""
        results = parse_provenance_from_layer("ANCHORS", text)
        assert results[0]["fact_ids"] == ["100", "200"]

    def test_case_insensitive_provenance_keyword(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**A1. TEST**
Provenance: [F-100]
"""
        results = parse_provenance_from_layer("ANCHORS", text)
        assert len(results) == 1

    def test_whitespace_in_fact_ids(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = """**A1. TEST**
provenance: [ F-100 , F-200 , F-300 ]
"""
        results = parse_provenance_from_layer("ANCHORS", text)
        assert results[0]["fact_ids"] == ["100", "200", "300"]


# ============================================================
# STORE_PROVENANCE
# ============================================================

class TestStoreProvenance:
    """Test storing provenance entries in the database."""

    @pytest.fixture
    def prov_db(self, tmp_path):
        """Create a temp database for provenance testing."""
        db_path = tmp_path / "prov_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        yield conn
        conn.close()

    def test_creates_table_if_not_exists(self, prov_db):
        from baselayer.author_layers import store_provenance
        entries = [{"claim_id": "A1", "claim_text": "TEST", "fact_ids": ["f1"]}]
        store_provenance(prov_db, "ANCHORS", entries)
        # Table should exist
        count = prov_db.execute(
            "SELECT COUNT(*) FROM layer_claim_provenance"
        ).fetchone()[0]
        assert count == 1

    def test_stores_multiple_entries(self, prov_db):
        from baselayer.author_layers import store_provenance
        entries = [
            {"claim_id": "A1", "claim_text": "COHERENCE", "fact_ids": ["f1", "f2"]},
            {"claim_id": "A2", "claim_text": "OWNERSHIP", "fact_ids": ["f3"]},
        ]
        inserted = store_provenance(prov_db, "ANCHORS", entries)
        assert inserted == 3  # 2 + 1

    def test_clears_previous_provenance(self, prov_db):
        from baselayer.author_layers import store_provenance
        entries1 = [{"claim_id": "A1", "claim_text": "OLD", "fact_ids": ["f1"]}]
        store_provenance(prov_db, "ANCHORS", entries1)

        entries2 = [{"claim_id": "A1", "claim_text": "NEW", "fact_ids": ["f2", "f3"]}]
        inserted = store_provenance(prov_db, "ANCHORS", entries2)
        assert inserted == 2

        rows = prov_db.execute(
            "SELECT * FROM layer_claim_provenance WHERE layer_name = 'ANCHORS'"
        ).fetchall()
        assert len(rows) == 2
        assert all(r["claim_text"] == "NEW" for r in rows)

    def test_preserves_other_layer_provenance(self, prov_db):
        from baselayer.author_layers import store_provenance
        entries_a = [{"claim_id": "A1", "claim_text": "ANCHOR", "fact_ids": ["f1"]}]
        entries_p = [{"claim_id": "P1", "claim_text": "PREDICT", "fact_ids": ["f2"]}]
        store_provenance(prov_db, "ANCHORS", entries_a)
        store_provenance(prov_db, "PREDICTIONS", entries_p)

        # Re-store anchors should not affect predictions
        store_provenance(prov_db, "ANCHORS",
                         [{"claim_id": "A2", "claim_text": "NEW", "fact_ids": ["f3"]}])

        pred_count = prov_db.execute(
            "SELECT COUNT(*) FROM layer_claim_provenance WHERE layer_name = 'PREDICTIONS'"
        ).fetchone()[0]
        assert pred_count == 1

    def test_rank_in_claim(self, prov_db):
        from baselayer.author_layers import store_provenance
        entries = [{"claim_id": "A1", "claim_text": "TEST",
                    "fact_ids": ["f1", "f2", "f3"]}]
        store_provenance(prov_db, "ANCHORS", entries)
        rows = prov_db.execute(
            "SELECT rank_in_claim FROM layer_claim_provenance ORDER BY rank_in_claim"
        ).fetchall()
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_layer_version_and_cycle_id(self, prov_db):
        from baselayer.author_layers import store_provenance
        entries = [{"claim_id": "A1", "claim_text": "TEST", "fact_ids": ["f1"]}]
        store_provenance(prov_db, "ANCHORS", entries,
                         layer_version="v3", cycle_id="gen2")
        row = prov_db.execute(
            "SELECT layer_version, cycle_id FROM layer_claim_provenance"
        ).fetchone()
        assert row["layer_version"] == "v3"
        assert row["cycle_id"] == "gen2"

    def test_created_at_timestamp(self, prov_db):
        from baselayer.author_layers import store_provenance
        before = time.time()
        entries = [{"claim_id": "A1", "claim_text": "TEST", "fact_ids": ["f1"]}]
        store_provenance(prov_db, "ANCHORS", entries)
        after = time.time()
        row = prov_db.execute(
            "SELECT created_at FROM layer_claim_provenance"
        ).fetchone()
        assert before <= row["created_at"] <= after

    def test_empty_entries(self, prov_db):
        from baselayer.author_layers import store_provenance
        inserted = store_provenance(prov_db, "ANCHORS", [])
        assert inserted == 0


# ============================================================
# CAP_BY_DOMAIN
# ============================================================

class TestCapByDomain:
    """Test domain-based fact capping (D-055)."""

    def test_no_cap_when_under_threshold(self):
        from baselayer.author_layers import cap_by_domain
        facts = [{"fact_text": "Values honesty"} for _ in range(10)]
        result = cap_by_domain(facts, max_percent=25)
        assert len(result) == 10

    def test_caps_trading_domain(self):
        from baselayer.author_layers import cap_by_domain
        # 8 trading facts + 2 non-trading out of 10 = 80% trading
        facts = [{"fact_text": "Uses systematic trading approach"} for _ in range(8)]
        facts += [{"fact_text": "Values honesty"} for _ in range(2)]
        result = cap_by_domain(facts, max_percent=25)
        # 25% of 10 = 2 (rounded up to at least 1)
        trading_count = sum(1 for f in result if "trading" in f["fact_text"].lower())
        assert trading_count <= 3  # max 25% of total

    def test_empty_list(self):
        from baselayer.author_layers import cap_by_domain
        result = cap_by_domain([], max_percent=25)
        assert result == []

    def test_preserves_non_domain_facts(self):
        from baselayer.author_layers import cap_by_domain
        facts = [
            {"fact_text": "Loves hiking"},
            {"fact_text": "Uses trading strategies aggressively"},
            {"fact_text": "Values family time"},
        ]
        result = cap_by_domain(facts, max_percent=50)
        non_trading = [f for f in result if "trading" not in f["fact_text"].lower()]
        assert len(non_trading) == 2


# ============================================================
# CAP_BY_CATEGORY
# ============================================================

class TestCapByCategory:
    """Test category-based fact capping."""

    def test_caps_per_category(self):
        from baselayer.author_layers import cap_by_category
        facts = [{"fact_text": f"Fact {i}", "category": "interest"}
                 for i in range(20)]
        result = cap_by_category(facts, max_per_category=5)
        assert len(result) == 5

    def test_multiple_categories(self):
        from baselayer.author_layers import cap_by_category
        facts = [{"fact_text": f"Bio {i}", "category": "biography"} for i in range(10)]
        facts += [{"fact_text": f"Val {i}", "category": "value"} for i in range(10)]
        result = cap_by_category(facts, max_per_category=5)
        assert len(result) == 10  # 5 from each

    def test_preserves_order_within_category(self):
        from baselayer.author_layers import cap_by_category
        facts = [{"fact_text": f"Item {i}", "category": "interest"} for i in range(10)]
        result = cap_by_category(facts, max_per_category=3)
        assert result[0]["fact_text"] == "Item 0"
        assert result[1]["fact_text"] == "Item 1"
        assert result[2]["fact_text"] == "Item 2"

    def test_unknown_category_handled(self):
        from baselayer.author_layers import cap_by_category
        facts = [{"fact_text": "No cat"} for _ in range(5)]  # missing category key
        result = cap_by_category(facts, max_per_category=3)
        assert len(result) == 3


# ============================================================
# APPLY_EXCLUSION_FILTER
# ============================================================

class TestApplyExclusionFilter:
    """Test authoring exclusion filter (D-040, D-044)."""

    def test_excludes_identity_block_reference(self):
        from baselayer.author_layers import apply_exclusion_filter
        facts = [
            {"fact_text": "Uses identity block approach"},
            {"fact_text": "Values honesty"},
        ]
        result = apply_exclusion_filter(facts)
        assert len(result) == 1
        assert result[0]["fact_text"] == "Values honesty"

    def test_excludes_design_decision_reference(self):
        from baselayer.author_layers import apply_exclusion_filter
        facts = [{"fact_text": "Follows D-040 for authoring"}]
        result = apply_exclusion_filter(facts)
        assert len(result) == 0

    def test_excludes_chromadb_reference(self):
        from baselayer.author_layers import apply_exclusion_filter
        facts = [{"fact_text": "Uses ChromaDB for vectors"}]
        result = apply_exclusion_filter(facts)
        assert len(result) == 0

    def test_case_insensitive_exclusion(self):
        from baselayer.author_layers import apply_exclusion_filter
        facts = [{"fact_text": "Works on IDENTITY BLOCK system"}]
        result = apply_exclusion_filter(facts)
        assert len(result) == 0

    def test_preserves_clean_facts(self):
        from baselayer.author_layers import apply_exclusion_filter
        facts = [
            {"fact_text": "Loves hiking in the mountains"},
            {"fact_text": "Works at a tech startup"},
        ]
        result = apply_exclusion_filter(facts)
        assert len(result) == 2


# ============================================================
# CITATIONS API — _format_facts_as_document_blocks
# ============================================================

class TestFormatFactsAsDocumentBlocks:
    """Test conversion of facts to document content blocks for Citations API."""

    def test_basic_conversion(self):
        from baselayer.author_layers import _format_facts_as_document_blocks
        facts = [
            {"id": "101", "fact_text": "Prefers direct communication"},
            {"id": "102", "fact_text": "Works in finance"},
        ]
        blocks, idx_map = _format_facts_as_document_blocks(facts)
        assert len(blocks) == 2
        assert blocks[0] == {"type": "text", "text": "Prefers direct communication"}
        assert blocks[1] == {"type": "text", "text": "Works in finance"}
        assert idx_map == {0: "101", 1: "102"}

    def test_max_items_cap(self):
        from baselayer.author_layers import _format_facts_as_document_blocks
        facts = [{"id": str(i), "fact_text": f"Fact {i}"} for i in range(150)]
        blocks, idx_map = _format_facts_as_document_blocks(facts, max_items=50)
        assert len(blocks) == 50
        assert len(idx_map) == 50

    def test_missing_id(self):
        from baselayer.author_layers import _format_facts_as_document_blocks
        facts = [
            {"id": "101", "fact_text": "Has an id"},
            {"fact_text": "No id field"},
        ]
        blocks, idx_map = _format_facts_as_document_blocks(facts)
        assert len(blocks) == 2
        assert 0 in idx_map
        assert 1 not in idx_map  # No id -> not in map

    def test_empty_facts(self):
        from baselayer.author_layers import _format_facts_as_document_blocks
        blocks, idx_map = _format_facts_as_document_blocks([])
        assert blocks == []
        assert idx_map == {}

    def test_formulation_fallback(self):
        from baselayer.author_layers import _format_facts_as_document_blocks
        facts = [{"id": "201", "formulation": "Alternative text field"}]
        blocks, idx_map = _format_facts_as_document_blocks(facts)
        assert blocks[0]["text"] == "Alternative text field"

    def test_text_truncation(self):
        from baselayer.author_layers import _format_facts_as_document_blocks
        long_text = "x" * 500
        facts = [{"id": "301", "fact_text": long_text}]
        blocks, idx_map = _format_facts_as_document_blocks(facts)
        assert len(blocks[0]["text"]) == 300


# ============================================================
# CITATIONS API — _parse_citation_provenance
# ============================================================

class TestParseCitationProvenance:
    """Test extraction of provenance from Citations API response objects."""

    def test_basic_single_citation(self):
        from baselayer.author_layers import _parse_citation_provenance

        # Mock a response with one text block citing one fact
        citation = MagicMock()
        citation.type = "content_block_location"
        citation.document_index = 0
        citation.start_block_index = 0
        citation.end_block_index = 1

        block = MagicMock()
        block.type = "text"
        block.text = "This person prefers direct feedback."
        block.citations = [citation]

        response = MagicMock()
        response.content = [block]

        idx_map = {0: "101", 1: "102", 2: "103"}
        results = _parse_citation_provenance(response, [(0, idx_map)], "ANCHORS")

        assert len(results) == 1
        assert results[0]["fact_ids"] == ["101"]
        assert results[0]["claim_id"] == "A1"
        assert "direct feedback" in results[0]["claim_text"]

    def test_multi_citation_single_block(self):
        from baselayer.author_layers import _parse_citation_provenance

        # One text block citing two facts
        cit1 = MagicMock()
        cit1.type = "content_block_location"
        cit1.document_index = 0
        cit1.start_block_index = 0
        cit1.end_block_index = 1

        cit2 = MagicMock()
        cit2.type = "content_block_location"
        cit2.document_index = 0
        cit2.start_block_index = 2
        cit2.end_block_index = 3

        block = MagicMock()
        block.type = "text"
        block.text = "Coherence and directness."
        block.citations = [cit1, cit2]

        response = MagicMock()
        response.content = [block]

        idx_map = {0: "101", 1: "102", 2: "103"}
        results = _parse_citation_provenance(response, [(0, idx_map)], "PREDICTIONS")

        assert len(results) == 1
        assert "101" in results[0]["fact_ids"]
        assert "103" in results[0]["fact_ids"]
        assert results[0]["claim_id"] == "P1"

    def test_no_citations_returns_empty(self):
        from baselayer.author_layers import _parse_citation_provenance

        block = MagicMock()
        block.type = "text"
        block.text = "No citations here."
        block.citations = None

        response = MagicMock()
        response.content = [block]

        results = _parse_citation_provenance(response, [(0, {})], "CORE")
        assert results == []

    def test_non_text_blocks_skipped(self):
        from baselayer.author_layers import _parse_citation_provenance

        block = MagicMock()
        block.type = "image"

        response = MagicMock()
        response.content = [block]

        results = _parse_citation_provenance(response, [(0, {})], "ANCHORS")
        assert results == []

    def test_comma_separated_source_ids(self):
        """Anchors with source_fact_ids as comma-separated string."""
        from baselayer.author_layers import _parse_citation_provenance

        citation = MagicMock()
        citation.type = "content_block_location"
        citation.document_index = 0
        citation.start_block_index = 0
        citation.end_block_index = 1

        block = MagicMock()
        block.type = "text"
        block.text = "Axiom from multiple sources."
        block.citations = [citation]

        response = MagicMock()
        response.content = [block]

        # Anchors store source_fact_ids as comma-separated string
        idx_map = {0: "101, 102, 103"}
        results = _parse_citation_provenance(response, [(0, idx_map)], "ANCHORS")

        assert len(results) == 1
        assert "101" in results[0]["fact_ids"]
        assert "102" in results[0]["fact_ids"]
        assert "103" in results[0]["fact_ids"]

    def test_multi_document_citations(self):
        """CORE layer uses multiple documents (one per fact type)."""
        from baselayer.author_layers import _parse_citation_provenance

        cit_bio = MagicMock()
        cit_bio.type = "content_block_location"
        cit_bio.document_index = 0  # biographical
        cit_bio.start_block_index = 0
        cit_bio.end_block_index = 1

        cit_beh = MagicMock()
        cit_beh.type = "content_block_location"
        cit_beh.document_index = 1  # behavioral
        cit_beh.start_block_index = 1
        cit_beh.end_block_index = 2

        block = MagicMock()
        block.type = "text"
        block.text = "Context mode combining bio and behavioral."
        block.citations = [cit_bio, cit_beh]

        response = MagicMock()
        response.content = [block]

        bio_map = {0: "201", 1: "202"}
        beh_map = {0: "301", 1: "302"}
        index_maps = [(0, bio_map), (1, beh_map)]

        results = _parse_citation_provenance(response, index_maps, "CORE")
        assert len(results) == 1
        assert "201" in results[0]["fact_ids"]
        assert "302" in results[0]["fact_ids"]

    def test_deduplication(self):
        """Same fact cited twice should be deduplicated."""
        from baselayer.author_layers import _parse_citation_provenance

        cit1 = MagicMock()
        cit1.type = "content_block_location"
        cit1.document_index = 0
        cit1.start_block_index = 0
        cit1.end_block_index = 1

        cit2 = MagicMock()
        cit2.type = "content_block_location"
        cit2.document_index = 0
        cit2.start_block_index = 0
        cit2.end_block_index = 1

        block = MagicMock()
        block.type = "text"
        block.text = "Repeated citation."
        block.citations = [cit1, cit2]

        response = MagicMock()
        response.content = [block]

        idx_map = {0: "101"}
        results = _parse_citation_provenance(response, [(0, idx_map)], "ANCHORS")
        assert len(results) == 1
        assert results[0]["fact_ids"] == ["101"]  # Deduplicated


# ============================================================
# CITATIONS API — _adapt_prompt_for_citations
# ============================================================

class TestAdaptPromptForCitations:
    """Test prompt adaptation for Citations API path."""

    def test_removes_provenance_instruction(self):
        from baselayer.author_layers import _adapt_prompt_for_citations
        prompt = """Some instructions.

PROVENANCE — Each axiom must cite the input facts it draws from. After each axiom block, include a provenance line:
  provenance: [F-xxx, F-yyy, ...]
Use the [F-xxx] IDs provided in the input facts. Only cite facts that directly support the axiom. This enables trace-back from claims to source evidence.

LEXICON IDS — Assign each axiom a stable identifier."""
        result = _adapt_prompt_for_citations(prompt)
        assert "PROVENANCE is handled automatically" in result
        assert "[F-xxx]" not in result.split("PROVENANCE is handled")[1].split("LEXICON")[0]
        assert "LEXICON IDS" in result

    def test_replaces_anchors_input_section(self):
        from baselayer.author_layers import _adapt_prompt_for_citations
        prompt = """Instructions here.

INPUT — Axioms (each tagged with [F-xxx] for provenance):
{facts}

INTER-AXIOM CONFLICTS:
{conflicts}"""
        result = _adapt_prompt_for_citations(prompt)
        assert "{facts}" not in result
        assert "document above" in result
        assert "{conflicts}" in result  # Conflicts should be preserved

    def test_replaces_core_input_section(self):
        from baselayer.author_layers import _adapt_prompt_for_citations
        prompt = """Instructions.

INPUT — Identity-tier facts by type (each tagged with [F-xxx] for provenance):

BIOGRAPHICAL:
{biographical}

BEHAVIORAL:
{behavioral}

POSITIONAL:
{positional}

PREFERENCE:
{preference}

Write the block."""
        result = _adapt_prompt_for_citations(prompt)
        assert "{biographical}" not in result
        assert "{behavioral}" not in result
        assert "documents above" in result

    def test_replaces_predictions_input_section(self):
        from baselayer.author_layers import _adapt_prompt_for_citations
        prompt = """Instructions.

INPUT — Behavioral identity-tier facts (each tagged with [F-xxx] for provenance):
{facts}

Write the block."""
        result = _adapt_prompt_for_citations(prompt)
        assert "{facts}" not in result
        assert "document above" in result


# ============================================================
# CITATIONS API — _format_anchors_as_document_blocks
# ============================================================

class TestFormatAnchorsAsDocumentBlocks:
    """Test anchor-specific document block formatting."""

    def test_epistemic_anchors_table(self):
        from baselayer.author_layers import _format_anchors_as_document_blocks
        data = {
            "source": "epistemic_anchors_table",
            "facts": [
                {
                    "anchor_number": 1,
                    "anchor_text": "Truth is non-negotiable",
                    "status": "confirmed",
                    "review_notes": None,
                    "source_fact_ids": "101, 102, 103",
                },
            ],
            "count": 1,
        }
        blocks, idx_map = _format_anchors_as_document_blocks(data)
        assert len(blocks) == 1
        assert "Truth is non-negotiable" in blocks[0]["text"]
        assert idx_map[0] == "101, 102, 103"

    def test_paused_anchor(self):
        from baselayer.author_layers import _format_anchors_as_document_blocks
        data = {
            "source": "epistemic_anchors_table",
            "facts": [
                {
                    "anchor_number": 1,
                    "anchor_text": "Old belief",
                    "status": "paused",
                    "review_notes": None,
                    "source_fact_ids": "",
                },
            ],
            "count": 1,
        }
        blocks, idx_map = _format_anchors_as_document_blocks(data)
        assert "PAUSED" in blocks[0]["text"]

    def test_raw_facts_fallback(self):
        from baselayer.author_layers import _format_anchors_as_document_blocks
        data = {
            "source": "conviction_identity_facts",
            "facts": [
                {"id": "201", "fact_text": "Direct conviction fact"},
            ],
            "count": 1,
        }
        blocks, idx_map = _format_anchors_as_document_blocks(data)
        assert len(blocks) == 1
        assert idx_map[0] == "201"
