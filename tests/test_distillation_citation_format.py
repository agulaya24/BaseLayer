"""
The distillation authoring path and the verification tooling used two different
citation vocabularies, so `verify_claims` was a no-op on the pipeline's own output:

  1. `render_claims` emitted `## A1 NAME` headers and inline `[F-xxxxxxxx]` tags;
     `parse_provenance_from_layer` required `**A1. NAME**` headers plus a
     `provenance: [F-xxx, ...]` line, parsed nothing, and
     `generate_verification_questions` returned [] -- which is byte-identical to
     what a healthy run with no claims returns.
  2. Even with a parseable provenance line, distillation citations are the first
     8 hex chars of the fact UUID while `memory_facts.id` is the full 36-char
     UUID, and every check compares with `=`, so each cited fact reported
     "not found".

These tests pin the unified format:
  - `render_claims` emits a `provenance: [F-...]` block per claim IN ADDITION to
    the inline tags (the inline tags feed the citation gate and compose's
    supplied set; they are load-bearing and must not change).
  - `parse_provenance_from_layer` accepts both header shapes this repo ships.
  - verification resolves 8-hex citation prefixes against the fact table.

All tests run offline.
"""

import sqlite3

import pytest


def _claims_data():
    """A minimal structured layer as call_structured returns it."""
    return {
        "layer": "anchors",
        "preamble": "Framing paragraph.",
        "claims": [
            {
                "id": "A1",
                "name": "IMPOSED AUTHORITY IS ILLEGITIMATE",
                "statement": "They begin from the position that outside authority has no standing.",
                "active_when": "Any setting where a rule claims the right to direct conduct.",
                "fact_ids": ["2dd8cc28", "2a95c097"],
                "contested": True,
            },
            {
                "id": "A2",
                "name": "PLACE AND KIN ARE IDENTITY",
                "statement": "Land and kin are the substance of who they are.",
                "active_when": "",
                "fact_ids": ["5f1f6fb4"],
                "contested": False,
            },
        ],
    }


# ============================================================
# 1. EMITTER -- render_claims
# ============================================================

class TestRenderClaimsProvenanceBlock:

    def test_emits_provenance_block_per_claim(self):
        from baselayer.distillation.author_from_package import render_claims
        text = render_claims(_claims_data())
        assert "provenance: [F-2dd8cc28, F-2a95c097]" in text
        assert "provenance: [F-5f1f6fb4]" in text

    def test_keeps_inline_evidence_tags_unchanged(self):
        """The inline [F-xxx] tags feed the citation gate and compose's supplied
        set. The provenance block is ADDITIVE; the tags must survive verbatim."""
        from baselayer.distillation.author_from_package import render_claims
        text = render_claims(_claims_data())
        assert "*Evidence:* [F-2dd8cc28] [F-2a95c097]" in text
        assert "*Evidence:* [F-5f1f6fb4]" in text

    def test_contested_marker_still_present(self):
        from baselayer.distillation.author_from_package import render_claims
        text = render_claims(_claims_data())
        assert "(CONTESTED)" in text


# ============================================================
# 2. PARSER -- parse_provenance_from_layer
# ============================================================

class TestParserReadsDistillationOutput:

    def test_round_trip_render_then_parse(self):
        """The whole defect in one assertion: the verification parser must read
        what the distillation author writes."""
        from baselayer.distillation.author_from_package import render_claims
        from baselayer.author_layers import parse_provenance_from_layer
        text = render_claims(_claims_data())
        results = parse_provenance_from_layer("ANCHORS", text)
        assert len(results) == 2
        by_id = {r["claim_id"]: r for r in results}
        assert by_id["A1"]["fact_ids"] == ["2dd8cc28", "2a95c097"]
        assert by_id["A2"]["fact_ids"] == ["5f1f6fb4"]

    def test_heading_style_header_matches(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = (
            "## A1 IMPOSED AUTHORITY IS ILLEGITIMATE\n"
            "\n"
            "Statement text.\n"
            "\n"
            "provenance: [F-2dd8cc28, F-2a95c097]\n"
        )
        results = parse_provenance_from_layer("ANCHORS", text)
        assert len(results) == 1
        assert results[0]["claim_id"] == "A1"
        assert results[0]["fact_ids"] == ["2dd8cc28", "2a95c097"]

    def test_contested_marker_not_part_of_claim_text(self):
        from baselayer.author_layers import parse_provenance_from_layer
        text = (
            "## A1 KINSHIP IS WIDER THAN RACE  (CONTESTED)\n"
            "provenance: [F-6e77ed21]\n"
        )
        results = parse_provenance_from_layer("ANCHORS", text)
        assert len(results) == 1
        assert results[0]["claim_text"] == "KINSHIP IS WIDER THAN RACE"

    def test_bold_style_header_still_matches(self):
        """The static self-citation format must keep parsing (additive change)."""
        from baselayer.author_layers import parse_provenance_from_layer
        text = (
            "**A1. COHERENCE**\n"
            "Some axiom text here.\n"
            "provenance: [F-1204, F-2891]\n"
        )
        results = parse_provenance_from_layer("ANCHORS", text)
        assert len(results) == 1
        assert results[0]["claim_id"] == "A1"
        assert results[0]["claim_text"] == "COHERENCE"


# ============================================================
# 3. RESOLUTION -- 8-hex citation prefixes against full UUIDs
# ============================================================

FULL_ID = "2dd8cc28-d784-491b-9e0f-987abba44b13"


@pytest.fixture
def uuid_db(tmp_path):
    from baselayer.init_database import init_database
    db_path = tmp_path / "resolve.db"
    init_database(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        INSERT INTO memory_facts (
            id, fact_text, category, recurrence_count,
            knowledge_tier, temporal_state, source
        ) VALUES (?, 'Resists imposed authority', 'value', 5,
                  'identity', 'present', 'extraction')
        """,
        (FULL_ID,),
    )
    conn.commit()
    yield conn, db_path
    conn.close()


class TestCitationPrefixResolution:

    def test_hex8_prefix_expands_to_full_uuid(self, uuid_db):
        from baselayer.verify_provenance import _resolve_citation_ids
        conn, _ = uuid_db
        assert _resolve_citation_ids(conn, ["2dd8cc28"]) == [FULL_ID]

    def test_full_id_and_unknown_id_pass_through(self, uuid_db):
        from baselayer.verify_provenance import _resolve_citation_ids
        conn, _ = uuid_db
        assert _resolve_citation_ids(conn, [FULL_ID]) == [FULL_ID]
        # An id that resolves to nothing is kept, so the existence check can
        # fail loudly instead of the citation being silently dropped.
        assert _resolve_citation_ids(conn, ["deadbeef"]) == ["deadbeef"]
        assert _resolve_citation_ids(conn, ["f-recurring-bio"]) == ["f-recurring-bio"]

    def test_questions_generated_and_resolvable_on_distillation_layer(self, uuid_db, monkeypatch):
        """End to end at the unit level: a layer authored by the distillation
        path yields verification questions whose fact ids resolve in the DB."""
        import baselayer.verify_provenance as vp
        from baselayer.distillation.author_from_package import render_claims

        conn, db_path = uuid_db
        data = {
            "layer": "anchors",
            "preamble": "",
            "claims": [{
                "id": "A1",
                "name": "IMPOSED AUTHORITY IS ILLEGITIMATE",
                "statement": "Outside authority has no standing.",
                "active_when": "",
                "fact_ids": ["2dd8cc28"],
                "contested": False,
            }],
        }
        layer_text = render_claims(data)

        def _factory(_path=None):
            c = sqlite3.connect(str(db_path))
            c.row_factory = sqlite3.Row
            return c

        monkeypatch.setattr(vp, "_get_layer_text", lambda name: layer_text)
        monkeypatch.setattr(vp, "get_db", _factory)

        questions = vp.generate_verification_questions("ANCHORS")
        assert questions, "verify_claims generated no questions on distillation output"
        existence = [q for q in questions if q["verification_type"] == "existence"]
        assert existence[0]["fact_ids"] == [FULL_ID]

        # And the check family actually passes against the DB.
        result, evidence = vp._check_existence(conn, existence[0]["fact_ids"][0])
        assert result == 1, evidence
