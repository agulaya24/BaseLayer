"""
Tests for the B-halt dynamic fact cap (BASELAYER_DYNAMIC_CAP).

Covers BOTH paths of the gate:
  - Flag OFF (default): behavior is byte-for-byte identical to the static-cap
    pipeline. Caps come from tiers; per-chunk cap is min(50, max_facts); on
    breach the confidence-sort trim keeps top-N.
  - Flag ON: per_chunk_cap == max_facts; doc-level max_facts is density-scaled
    (min(source_ceiling, ceil(total_chars / CHARS_PER_FACT))); no silent trim;
    the S98 coverage gate still HARD-halts on runaway.

All tests run without API keys or external services — call_llm and the chunker
are mocked so no network or embedding model is touched.
"""

import pytest
from unittest.mock import patch, MagicMock


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _fact(i):
    """A raw LLM fact dict that survives validate_structured_response.

    confidence >= 0.3, object >= 3 chars, reconstructed fact_text >= MIN_FACT_LENGTH.
    Confidence varies so a confidence sort has something to order.
    """
    return {
        "subject": "user",
        "predicate": "values",
        "object": f"thing number {i:03d}",
        "qualifier": "unknown",
        "confidence": 0.4 + (i % 5) * 0.02,
        "category": "value",
        "temporal": "current",
    }


def _llm_returning(n):
    """A call_llm stand-in that always returns n valid facts."""
    facts = [_fact(i) for i in range(n)]
    return lambda *a, **k: {"facts": list(facts)}


# ==================================================================
# _dynamic_cap_enabled — the env-var gate
# ==================================================================

class TestDynamicCapFlag:
    def test_unset_is_off(self, monkeypatch):
        from baselayer.extract_facts import _dynamic_cap_enabled
        monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
        assert _dynamic_cap_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_values_enable(self, monkeypatch, val):
        from baselayer.extract_facts import _dynamic_cap_enabled
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", val)
        assert _dynamic_cap_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "nope"])
    def test_falsey_values_stay_off(self, monkeypatch, val):
        from baselayer.extract_facts import _dynamic_cap_enabled
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", val)
        assert _dynamic_cap_enabled() is False


# ==================================================================
# _get_extraction_caps — density scaling, gated
# ==================================================================

class TestGetExtractionCapsFlagOff:
    """Flag OFF: identical to the static-cap tiers regardless of total_chars.

    These mirror the existing TestGetExtractionCaps expectations — proof the
    default path is unchanged by the B-halt diff.
    """

    def test_tiers_unchanged_no_chars(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
        assert _get_extraction_caps(5)["max_facts"] == 10
        assert _get_extraction_caps(20)["max_facts"] == 20
        assert _get_extraction_caps(45)["max_facts"] == 35
        assert _get_extraction_caps(100)["max_facts"] == 50

    def test_char_tier_unchanged(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
        # 50K chars -> char tier 30001-60000 -> max_facts 35 (beats 1-msg tier of 10)
        caps = _get_extraction_caps(1, total_chars=50000)
        assert caps["max_facts"] == 35
        assert caps["input_char_budget"] == 24000

    def test_claude_code_override_unchanged(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
        # Per-source override lifts the per-conv cap to 1500 (total_chars unused here)
        caps = _get_extraction_caps(20, source="claude_code")
        assert caps["max_facts"] == 1500


class TestGetExtractionCapsFlagOn:
    """Flag ON: max_facts becomes a density-derived runaway backstop."""

    def test_density_scaled(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
        # ceil(50000 / 175) = 286, clamped by default ceiling 600 -> 286
        caps = _get_extraction_caps(1, total_chars=50000)
        assert caps["max_facts"] == 286
        # input_char_budget (chunk-sizing) is left untouched by B-halt
        assert caps["input_char_budget"] == 24000

    def test_density_clamped_by_default_ceiling(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
        # ceil(1_000_000 / 175) = 5715 -> clamped to default 600 ceiling
        caps = _get_extraction_caps(20, total_chars=1_000_000)
        assert caps["max_facts"] == 600

    def test_density_clamped_by_claude_code_ceiling(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
        # claude_code raises the ceiling to 1500; density would be 5715 -> 1500
        caps = _get_extraction_caps(20, total_chars=1_000_000, source="claude_code")
        assert caps["max_facts"] == 1500

    def test_zero_chars_falls_back_to_tier_not_zero(self, monkeypatch):
        """The load-bearing trap: ceil(0 / N) == 0. Flag ON with total_chars==0
        must fall back to the tier value, never zero out max_facts."""
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
        caps = _get_extraction_caps(45, total_chars=0)
        assert caps["max_facts"] == 35  # tier value for 45 messages, NOT 0

    def test_zero_chars_with_source_override(self, monkeypatch):
        from baselayer.extract_facts import _get_extraction_caps
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
        # total_chars==0 -> fallback branch -> per-source override still applies
        caps = _get_extraction_caps(20, total_chars=0, source="claude_code")
        assert caps["max_facts"] == 1500


# ==================================================================
# extract_facts_from_conversation — path behavior
# ==================================================================
#
# _get_extraction_caps is patched to a fixed dict so the path behavior
# (per_chunk_cap, silent trim, coverage gate) is isolated from the caps math
# (tested above). The chunker is patched to a fixed chunk list so chunk count
# is deterministic. call_llm is patched to return a fixed fact set per chunk.

def _run_extract(monkeypatch, *, flag_on, max_facts, n_chunks, facts_per_chunk):
    import baselayer.extract_facts as ef

    if flag_on:
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
    else:
        monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)

    fixed_caps = {"max_facts": max_facts, "input_char_budget": 100}
    monkeypatch.setattr(ef, "_get_extraction_caps", lambda *a, **k: fixed_caps)
    monkeypatch.setattr(ef, "_chunk_text_for_extraction",
                        lambda *a, **k: [f"chunk-{i}" for i in range(n_chunks)])
    monkeypatch.setattr(ef, "call_llm", _llm_returning(facts_per_chunk))

    # One long message forces the chunking branch (total_chars 500 > budget 100).
    messages = [{"role": "user", "text": "x" * 500}]
    return ef.extract_facts_from_conversation("cid", "title", messages)


class TestExtractPathFlagOff:
    def test_per_chunk_cap_is_capped_at_50(self, monkeypatch):
        # max_facts 80 -> per_chunk_cap min(50, 80) == 50. One chunk, 100 facts
        # offered -> only 50 validated, 50 <= 80 so no gate, no trim.
        out = _run_extract(monkeypatch, flag_on=False, max_facts=80,
                           n_chunks=1, facts_per_chunk=100)
        assert len(out) == 50

    def test_silent_trim_keeps_top_n(self, monkeypatch):
        # 2 chunks x 11 facts = 22 > max_facts 20, but 22 <= 1.2*20 so the gate
        # does NOT fire; the confidence-sort trim keeps exactly max_facts.
        out = _run_extract(monkeypatch, flag_on=False, max_facts=20,
                           n_chunks=2, facts_per_chunk=11)
        assert len(out) == 20


class TestExtractPathFlagOn:
    def test_per_chunk_cap_equals_max_facts(self, monkeypatch):
        # max_facts 80 -> per_chunk_cap 80. One chunk, 100 offered -> 80 validated.
        # 80 !> 80 so no gate; no trim -> all 80 returned.
        out = _run_extract(monkeypatch, flag_on=True, max_facts=80,
                           n_chunks=1, facts_per_chunk=100)
        assert len(out) == 80

    def test_no_silent_trim_below_gate(self, monkeypatch):
        # Same 22-fact / max_facts-20 scenario as the flag-off trim test, but
        # flag ON keeps ALL 22 (below the 20% gate) instead of trimming to 20.
        out = _run_extract(monkeypatch, flag_on=True, max_facts=20,
                           n_chunks=2, facts_per_chunk=11)
        assert len(out) == 22

    def test_coverage_gate_still_halts_on_runaway(self, monkeypatch):
        # 2 chunks x 20 facts = 40 vs max_facts 20 -> 50% over -> HARD halt.
        with pytest.raises(SystemExit):
            _run_extract(monkeypatch, flag_on=True, max_facts=20,
                         n_chunks=2, facts_per_chunk=20)

    def test_gate_override_skips_halt(self, monkeypatch):
        # BASELAYER_SKIP_COVERAGE_GATE lets the runaway through uncapped.
        monkeypatch.setenv("BASELAYER_SKIP_COVERAGE_GATE", "1")
        out = _run_extract(monkeypatch, flag_on=True, max_facts=20,
                           n_chunks=2, facts_per_chunk=20)
        assert len(out) == 40  # no trim, no halt


# ==================================================================
# OUTPUT-TOKEN OVERFLOW GUARD (per-chunk ask bound + max_tokens scaling)
# ==================================================================
#
# Real-world bug: a density-scaled max_facts (e.g. 239) made per_chunk_cap ask
# Haiku for ~240 facts/chunk, overflowing the ~10K max_tokens ceiling ->
# truncated JSON -> call_llm None -> whole chunk silently discarded. The fix
# bounds the per-CHUNK ask to OUTPUT_SAFE_CHUNK_CAP and scales max_tokens to the
# ask. The DOC-level cap stays density-scaled and aggregates across chunks.

class TestExtractionMaxTokens:
    def test_fits_100_fact_ask(self):
        from baselayer.extract_facts import _extraction_max_tokens
        from baselayer import config
        mt = _extraction_max_tokens(100)
        # 100*90 + 2000 = 11000 — comfortably above the ~9000 a 100-fact JSON needs
        assert mt == 100 * config.EXTRACTION_TOKENS_PER_FACT + config.EXTRACTION_OUTPUT_BUFFER_TOKENS
        assert mt >= 9000
        assert mt <= config.EXTRACTION_MAX_OUTPUT_TOKENS

    def test_clamped_to_model_max_output(self):
        from baselayer.extract_facts import _extraction_max_tokens
        from baselayer import config
        # A huge ask clamps to the extraction model's documented max output (64000)
        assert _extraction_max_tokens(100000) == config.EXTRACTION_MAX_OUTPUT_TOKENS

    def test_floored_at_legacy_minimum(self):
        from baselayer.extract_facts import _extraction_max_tokens
        assert _extraction_max_tokens(0) == 2000


class TestPerChunkAskBounded:
    """Density cap 200 -> per_chunk_cap capped at OUTPUT_SAFE_CHUNK_CAP (100),
    and max_tokens sized for the 100-fact ask, not the 200 density cap."""

    def _run(self, monkeypatch, *, flag_on, max_facts):
        import baselayer.extract_facts as ef
        if flag_on:
            monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
        else:
            monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)
        fixed_caps = {"max_facts": max_facts, "input_char_budget": 100}
        monkeypatch.setattr(ef, "_get_extraction_caps", lambda *a, **k: fixed_caps)
        monkeypatch.setattr(ef, "_chunk_text_for_extraction", lambda *a, **k: ["c1"])
        recorder = MagicMock(return_value={"facts": [_fact(i) for i in range(10)]})
        monkeypatch.setattr(ef, "call_llm", recorder)
        messages = [{"role": "user", "text": "x" * 500}]
        ef.extract_facts_from_conversation("cid", "title", messages)
        return recorder, ef

    def test_flag_on_bounds_ask_and_scales_max_tokens(self, monkeypatch):
        recorder, ef = self._run(monkeypatch, flag_on=True, max_facts=200)
        from baselayer import config
        mt = recorder.call_args.kwargs["max_tokens"]
        # per_chunk_cap == OUTPUT_SAFE_CHUNK_CAP (100), NOT the 200 density cap:
        # chunk_max_tokens == _extraction_max_tokens(100), not (_200).
        assert mt == ef._extraction_max_tokens(config.OUTPUT_SAFE_CHUNK_CAP)
        assert mt != ef._extraction_max_tokens(200)
        assert mt >= 9000

    def test_flag_off_passes_no_explicit_max_tokens(self, monkeypatch):
        # Byte-for-byte unchanged: flag-off forwards max_tokens=None, so
        # call_anthropic keeps its prompt-length heuristic.
        recorder, ef = self._run(monkeypatch, flag_on=False, max_facts=35)
        assert recorder.call_args.kwargs["max_tokens"] is None


# ==================================================================
# CAP-VS-AUDN ORDERING (the seam that matters)
# ==================================================================
#
# The tests above stop at extract_facts_from_conversation's return value. The
# defect reported is about ORDER: under the static-cap path, facts are
# discarded by a per-document cap BEFORE AUDN (the mechanism that decides what
# is actually redundant) ever sees them. AUDN does not run inside the extract
# function at all; it runs per-candidate in process_conversation. So the
# observable ordering claim is "how many candidates reach make_audn_decision",
# and that is what these tests measure.
#
# Ruling being encoded (2026-07-20): do not delete those facts; add them back and
# let AUDN take care of redundancy.
#
# NOTE: nothing caps the POST-AUDN set. AUDN culls by similarity, not to a
# ceiling. These tests assert the implemented behavior (cap demoted to a
# runaway backstop, all candidates reach AUDN), not a post-AUDN cap.

class _FakeConn:
    """Minimal sqlite-shaped stand-in: process_conversation only needs
    execute/commit for the extraction_log bookkeeping."""

    def execute(self, *a, **k):
        return MagicMock()

    def commit(self):
        pass


def _run_process(monkeypatch, *, flag_on, max_facts, n_chunks, facts_per_chunk):
    """Drive process_conversation with the REAL cap logic and count how many
    candidates reach AUDN. Returns (audn_call_count, facts_stored)."""
    import baselayer.extract_facts as ef

    if flag_on:
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")
    else:
        monkeypatch.delenv("BASELAYER_DYNAMIC_CAP", raising=False)

    # Real cap logic runs; only the surrounding I/O is stubbed.
    fixed_caps = {"max_facts": max_facts, "input_char_budget": 100}
    monkeypatch.setattr(ef, "_get_extraction_caps", lambda *a, **k: fixed_caps)
    monkeypatch.setattr(ef, "_chunk_text_for_extraction",
                        lambda *a, **k: [f"chunk-{i}" for i in range(n_chunks)])
    monkeypatch.setattr(ef, "call_llm", _llm_returning(facts_per_chunk))
    monkeypatch.setattr(ef, "get_conversation_messages",
                        lambda *a, **k: [{"role": "user", "text": "x" * 500}])

    audn_calls = []

    def _counting_audn(candidate_fact, similar_facts):
        audn_calls.append(candidate_fact)
        return {"action": "ADD"}

    monkeypatch.setattr(ef, "find_similar_facts", lambda *a, **k: [])
    monkeypatch.setattr(ef, "make_audn_decision", _counting_audn)
    monkeypatch.setattr(ef, "store_fact",
                        lambda *a, **k: f"fid-{len(audn_calls)}")
    monkeypatch.setattr(ef, "embed_fact", lambda *a, **k: None)

    conv = {"id": "cid", "title": "title", "source": "chatgpt"}
    stored = ef.process_conversation(conv, _FakeConn(), None, None)
    return len(audn_calls), stored


class TestCapAppliesAfterAudnNotBefore:
    def test_flag_off_guillotines_candidates_before_audn(self, monkeypatch):
        # 2 chunks x 11 facts = 22 raw. max_facts 20, and 22 <= 1.2*20 so the
        # S98 gate does NOT fire. The static path trims to 20 BEFORE AUDN, so
        # AUDN never sees 2 of the extracted facts. This is the defect.
        audn_calls, stored = _run_process(monkeypatch, flag_on=False,
                                          max_facts=20, n_chunks=2,
                                          facts_per_chunk=11)
        assert audn_calls == 20, "static path should truncate before AUDN"
        assert stored == 20

    def test_flag_on_hands_every_candidate_to_audn(self, monkeypatch):
        # Identical input. Flag ON demotes max_facts to a runaway backstop and
        # removes the pre-AUDN trim, so all 22 raw facts reach AUDN and AUDN
        # decides redundancy. 2 facts that the old ordering discarded unseen.
        audn_calls, stored = _run_process(monkeypatch, flag_on=True,
                                          max_facts=20, n_chunks=2,
                                          facts_per_chunk=11)
        assert audn_calls == 22, "every extracted fact must reach AUDN"
        assert stored == 22

    def test_audn_not_the_cap_is_what_culls(self, monkeypatch):
        # With the trim gone, culling must come from AUDN's verdict rather than
        # from the cap. Make AUDN NOOP half the candidates and confirm the
        # stored count follows AUDN, not max_facts.
        import baselayer.extract_facts as ef
        monkeypatch.setenv("BASELAYER_DYNAMIC_CAP", "1")

        seen = []

        def _half_noop(candidate_fact, similar_facts):
            seen.append(candidate_fact)
            return {"action": "ADD" if len(seen) % 2 else "NOOP"}

        fixed_caps = {"max_facts": 20, "input_char_budget": 100}
        monkeypatch.setattr(ef, "_get_extraction_caps", lambda *a, **k: fixed_caps)
        monkeypatch.setattr(ef, "_chunk_text_for_extraction",
                            lambda *a, **k: ["chunk-0", "chunk-1"])
        monkeypatch.setattr(ef, "call_llm", _llm_returning(11))
        monkeypatch.setattr(ef, "get_conversation_messages",
                            lambda *a, **k: [{"role": "user", "text": "x" * 500}])
        monkeypatch.setattr(ef, "find_similar_facts", lambda *a, **k: [])
        monkeypatch.setattr(ef, "make_audn_decision", _half_noop)
        monkeypatch.setattr(ef, "store_fact", lambda *a, **k: "fid")
        monkeypatch.setattr(ef, "embed_fact", lambda *a, **k: None)

        conv = {"id": "cid", "title": "title", "source": "chatgpt"}
        stored = ef.process_conversation(conv, _FakeConn(), None, None)

        assert len(seen) == 22, "AUDN sees all raw facts"
        assert stored == 11, "stored count reflects AUDN verdicts, not the cap"

    def test_gate_still_halts_before_audn_on_runaway(self, monkeypatch):
        # S98 is NOT weakened by the reorder: an implausible-density breach
        # still halts, and AUDN is never reached.
        with pytest.raises(SystemExit):
            _run_process(monkeypatch, flag_on=True, max_facts=20,
                         n_chunks=2, facts_per_chunk=20)
