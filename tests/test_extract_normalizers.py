"""
Tests for extract_facts.py — all normalize_* functions, reconstruct_fact_text(),
_get_extraction_caps(), and compute_confidence().

All tests run without API keys or external services.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock



# ============================================================
# NORMALIZE_CATEGORY
# ============================================================

class TestNormalizeCategory:
    """Test category normalization from LLM output."""

    def test_canonical_categories(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("preference") == "preference"
        assert normalize_category("biography") == "biography"
        assert normalize_category("project") == "project"
        assert normalize_category("relationship") == "relationship"
        assert normalize_category("interest") == "interest"
        assert normalize_category("skill") == "skill"
        assert normalize_category("value") == "value"
        assert normalize_category("habit") == "habit"
        assert normalize_category("opinion") == "opinion"
        assert normalize_category("goal") == "goal"
        assert normalize_category("negative_trait") == "negative_trait"

    def test_plural_to_singular(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("preferences") == "preference"
        assert normalize_category("relationships") == "relationship"
        assert normalize_category("interests") == "interest"
        assert normalize_category("skills") == "skill"
        assert normalize_category("values") == "value"
        assert normalize_category("habits") == "habit"
        assert normalize_category("opinions") == "opinion"
        assert normalize_category("goals") == "goal"
        assert normalize_category("projects") == "project"

    def test_fuzzy_mappings(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("biographical") == "biography"
        assert normalize_category("bio") == "biography"
        assert normalize_category("like") == "preference"
        assert normalize_category("work") == "project"
        assert normalize_category("family") == "relationship"
        assert normalize_category("hobby") == "interest"
        assert normalize_category("hobbies") == "interest"
        assert normalize_category("ability") == "skill"
        assert normalize_category("belief") == "value"
        assert normalize_category("routine") == "habit"
        assert normalize_category("view") == "opinion"
        assert normalize_category("aspiration") == "goal"

    def test_negative_trait_variants(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("negative_trait") == "negative_trait"
        assert normalize_category("negative trait") == "negative_trait"
        assert normalize_category("weakness") == "negative_trait"
        assert normalize_category("flaw") == "negative_trait"

    def test_case_insensitive(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("PREFERENCE") == "preference"
        assert normalize_category("Biography") == "biography"
        assert normalize_category("SKILL") == "skill"

    def test_whitespace_stripped(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("  preference  ") == "preference"
        assert normalize_category(" interest ") == "interest"

    def test_unknown_returns_unknown(self):
        from baselayer.extract_facts import normalize_category
        assert normalize_category("xyzzy") == "unknown"
        assert normalize_category("gibberish") == "unknown"


# ============================================================
# NORMALIZE_SUBJECT
# ============================================================

class TestNormalizeSubject:
    """Test subject normalization and entity resolution."""

    def _clear_caches(self):
        """Clear entity map and user names caches."""
        from baselayer.extract_facts import _get_entity_map, _get_user_names
        if hasattr(_get_entity_map, "_cache"):
            del _get_entity_map._cache
        if hasattr(_get_user_names, "_cache"):
            del _get_user_names._cache

    def setup_method(self):
        self._clear_caches()

    def teardown_method(self):
        self._clear_caches()

    def test_user_variants(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("the user") == "user"
                assert normalize_subject("user") == "user"
                assert normalize_subject("me") == "user"
                assert normalize_subject("I") == "user"
                assert normalize_subject("myself") == "user"
                assert normalize_subject("self") == "user"
                assert normalize_subject("the person") == "user"

    def test_empty_and_none(self):
        from baselayer.extract_facts import normalize_subject
        assert normalize_subject("") == "user"
        assert normalize_subject(None) == "user"

    def test_spouse_variants(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("wife") == "spouse"
                assert normalize_subject("husband") == "spouse"
                assert normalize_subject("partner") == "spouse"
                assert normalize_subject("the user's wife") == "spouse"

    def test_pet_variants(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("the user's cat") == "pet"
                assert normalize_subject("the user's dog") == "pet"
                assert normalize_subject("the user's pet") == "pet"

    def test_company(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("the user's company") == "company"
                assert normalize_subject("the user's startup") == "company"

    def test_friend(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("best friend") == "friend"
                assert normalize_subject("a friend") == "friend"

    def test_named_person_preserved(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("John Smith") == "John Smith"

    def test_entity_map_resolution(self):
        from baselayer.extract_facts import normalize_subject
        mock_map = {"john": "colleague:John"}
        with patch("baselayer.extract_facts._get_user_names", return_value=set()):
            with patch("baselayer.extract_facts._get_entity_map", return_value=mock_map):
                assert normalize_subject("John") == "colleague:John"

    def test_user_name_detected(self):
        from baselayer.extract_facts import normalize_subject
        with patch("baselayer.extract_facts._get_user_names", return_value={"alice"}):
            with patch("baselayer.extract_facts._get_entity_map", return_value={}):
                assert normalize_subject("Alice") == "user"


# ============================================================
# NORMALIZE_INTENT
# ============================================================

class TestNormalizeIntent:
    """Test intent normalization."""

    def test_does_variants(self):
        from baselayer.extract_facts import normalize_intent
        for v in ["does", "is", "has", "uses", "owns", "practices",
                   "works", "plays", "drives", "trades", "builds"]:
            assert normalize_intent(v) == "does", f"Failed for '{v}'"

    def test_learning_variants(self):
        from baselayer.extract_facts import normalize_intent
        for v in ["learning", "studying", "training", "developing",
                   "improving", "working on", "exploring"]:
            assert normalize_intent(v) == "learning", f"Failed for '{v}'"

    def test_curious_variants(self):
        from baselayer.extract_facts import normalize_intent
        for v in ["curious", "asked about", "wondered", "inquired",
                   "looked into", "researched"]:
            assert normalize_intent(v) == "curious", f"Failed for '{v}'"

    def test_historical_variants(self):
        from baselayer.extract_facts import normalize_intent
        for v in ["historical", "used to", "was", "had", "previously",
                   "formerly", "past", "did", "once"]:
            assert normalize_intent(v) == "historical", f"Failed for '{v}'"

    def test_empty_and_none(self):
        from baselayer.extract_facts import normalize_intent
        assert normalize_intent("") == "does"
        assert normalize_intent(None) == "does"

    def test_unknown_defaults_to_does(self):
        from baselayer.extract_facts import normalize_intent
        assert normalize_intent("xyzzy") == "does"


# ============================================================
# NORMALIZE_TEMPORAL
# ============================================================

class TestNormalizeTemporal:
    """Test temporal state normalization."""

    def test_current_variants(self):
        from baselayer.extract_facts import normalize_temporal
        for v in ["current", "present", "active", "now", "ongoing", "still"]:
            assert normalize_temporal(v) == "current", f"Failed for '{v}'"

    def test_past_variants(self):
        from baselayer.extract_facts import normalize_temporal
        for v in ["past", "was", "ended", "former", "previous",
                   "historical", "no longer", "stopped", "quit"]:
            assert normalize_temporal(v) == "past", f"Failed for '{v}'"

    def test_unknown_variants(self):
        from baselayer.extract_facts import normalize_temporal
        assert normalize_temporal("unknown") == "unknown"
        assert normalize_temporal("maybe") == "unknown"

    def test_empty_and_none(self):
        from baselayer.extract_facts import normalize_temporal
        assert normalize_temporal("") == "unknown"
        assert normalize_temporal(None) == "unknown"

    def test_case_insensitive(self):
        from baselayer.extract_facts import normalize_temporal
        assert normalize_temporal("CURRENT") == "current"
        assert normalize_temporal("Past") == "past"


# ============================================================
# NORMALIZE_FACT_CLASS
# ============================================================

class TestNormalizeFactClass:
    """Test fact class normalization (event vs state)."""

    def test_event_variants(self):
        from baselayer.extract_facts import normalize_fact_class
        for v in ["event", "events", "historical event", "milestone",
                   "achievement", "one-time", "happened", "occurred", "completed"]:
            assert normalize_fact_class(v) == "event", f"Failed for '{v}'"

    def test_state_variants(self):
        from baselayer.extract_facts import normalize_fact_class
        for v in ["state", "states", "current", "ongoing", "active",
                   "habit", "routine", "preference", "condition", "status"]:
            assert normalize_fact_class(v) == "state", f"Failed for '{v}'"

    def test_unclassified(self):
        from baselayer.extract_facts import normalize_fact_class
        assert normalize_fact_class("unclassified") == "unclassified"

    def test_empty_and_none(self):
        from baselayer.extract_facts import normalize_fact_class
        assert normalize_fact_class("") == "unclassified"
        assert normalize_fact_class(None) == "unclassified"

    def test_unknown_returns_unclassified(self):
        from baselayer.extract_facts import normalize_fact_class
        assert normalize_fact_class("xyzzy") == "unclassified"


# ============================================================
# NORMALIZE_KNOWLEDGE_TIER
# ============================================================

class TestNormalizeKnowledgeTier:
    """Test knowledge tier normalization."""

    def test_identity_variants(self):
        from baselayer.extract_facts import normalize_knowledge_tier
        for v in ["identity", "t1", "biographical", "permanent", "anchor"]:
            assert normalize_knowledge_tier(v) == "identity", f"Failed for '{v}'"

    def test_situational_variants(self):
        from baselayer.extract_facts import normalize_knowledge_tier
        for v in ["situational", "t2", "current", "mutable", "active"]:
            assert normalize_knowledge_tier(v) == "situational", f"Failed for '{v}'"

    def test_context_variants(self):
        from baselayer.extract_facts import normalize_knowledge_tier
        for v in ["context", "t3", "conversational", "ephemeral",
                   "one-off", "artifact"]:
            assert normalize_knowledge_tier(v) == "context", f"Failed for '{v}'"

    def test_empty_and_none(self):
        from baselayer.extract_facts import normalize_knowledge_tier
        assert normalize_knowledge_tier("") == "untiered"
        assert normalize_knowledge_tier(None) == "untiered"

    def test_unknown_returns_untiered(self):
        from baselayer.extract_facts import normalize_knowledge_tier
        assert normalize_knowledge_tier("xyzzy") == "untiered"


# ============================================================
# NORMALIZE_PREDICATE
# ============================================================

class TestNormalizePredicate:
    """Test predicate normalization with alias mapping."""

    def test_canonical_predicates_pass_through(self):
        from baselayer.extract_facts import normalize_predicate
        from baselayer.config import CONSTRAINED_PREDICATES
        for pred in CONSTRAINED_PREDICATES:
            assert normalize_predicate(pred) == pred, f"Failed for '{pred}'"

    def test_alias_values(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("cares about") == "values"
        assert normalize_predicate("works for") == "works_at"
        assert normalize_predicate("afraid of") == "fears"
        assert normalize_predicate("good at") == "excels_at"
        assert normalize_predicate("married to") == "married_to"
        assert normalize_predicate("lives in") == "lives_in"

    def test_relationship_aliases(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("works with") == "collaborates_with"
        assert normalize_predicate("learned from") == "mentored_by"
        assert normalize_predicate("friends with") == "friends_with"
        assert normalize_predicate("looks up to") == "admires"
        assert normalize_predicate("disagrees with") == "conflicts_with"

    def test_past_tense_normalization(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("struggled_with") == "struggles_with"
        assert normalize_predicate("studied") == "studies"
        assert normalize_predicate("practiced") == "practices"
        assert normalize_predicate("built") == "builds"
        assert normalize_predicate("managed") == "manages"

    def test_underscore_normalization(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("works at") == "works_at"
        assert normalize_predicate("lives in") == "lives_in"

    def test_empty_and_none(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("") == "unknown"
        assert normalize_predicate(None) == "unknown"

    def test_unknown_passthrough(self):
        from baselayer.extract_facts import normalize_predicate
        result = normalize_predicate("completely_new_verb")
        assert result == "completely_new_verb"

    def test_case_insensitive(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("CARES ABOUT") == "values"
        assert normalize_predicate("Works For") == "works_at"

    def test_attended_not_aliased_to_graduated(self):
        """D-049: attending != graduating."""
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("attended") == "attended"

    def test_interested_in_not_aliased_to_follows(self):
        """D-049: interest is passive, following is active."""
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("interested in") == "interested_in"

    def test_has_aliased_to_owns(self):
        from baselayer.extract_facts import normalize_predicate
        assert normalize_predicate("has") == "owns"


# ============================================================
# RECONSTRUCT_FACT_TEXT
# ============================================================

class TestReconstructFactText:
    """Test fact_text reconstruction from structured fields."""

    def test_basic_reconstruction(self):
        from baselayer.extract_facts import reconstruct_fact_text
        result = reconstruct_fact_text("user", "works_at", "Google")
        assert result == "user works at Google"

    def test_underscore_to_space(self):
        from baselayer.extract_facts import reconstruct_fact_text
        result = reconstruct_fact_text("user", "lives_in", "NYC")
        assert result == "user lives in NYC"

    def test_no_underscore_predicate(self):
        from baselayer.extract_facts import reconstruct_fact_text
        result = reconstruct_fact_text("user", "values", "honesty")
        assert result == "user values honesty"

    def test_empty_predicate(self):
        from baselayer.extract_facts import reconstruct_fact_text
        result = reconstruct_fact_text("user", "", "something")
        # Empty predicate still produces space from format string
        assert result == "user  something"

    def test_none_predicate(self):
        from baselayer.extract_facts import reconstruct_fact_text
        result = reconstruct_fact_text("user", None, "something")
        assert result == "user  something"


# ============================================================
# _GET_EXTRACTION_CAPS
# ============================================================

class TestGetExtractionCaps:
    """Test extraction cap scaling by message count."""

    def test_short_conversation(self):
        from baselayer.extract_facts import _get_extraction_caps
        caps = _get_extraction_caps(5)
        assert caps["max_facts"] == 10
        assert caps["input_char_budget"] == 12000

    def test_medium_conversation(self):
        from baselayer.extract_facts import _get_extraction_caps
        caps = _get_extraction_caps(20)
        assert caps["max_facts"] == 20
        assert caps["input_char_budget"] == 18000

    def test_long_conversation(self):
        from baselayer.extract_facts import _get_extraction_caps
        caps = _get_extraction_caps(45)
        assert caps["max_facts"] == 35
        assert caps["input_char_budget"] == 24000

    def test_very_long_conversation(self):
        from baselayer.extract_facts import _get_extraction_caps
        caps = _get_extraction_caps(100)
        assert caps["max_facts"] == 50
        assert caps["input_char_budget"] == 24000

    def test_boundary_values(self):
        from baselayer.extract_facts import _get_extraction_caps
        # Boundary between tiers
        caps_10 = _get_extraction_caps(10)
        assert caps_10["max_facts"] == 10
        caps_11 = _get_extraction_caps(11)
        assert caps_11["max_facts"] == 20
        caps_30 = _get_extraction_caps(30)
        assert caps_30["max_facts"] == 20
        caps_31 = _get_extraction_caps(31)
        assert caps_31["max_facts"] == 35

    def test_single_message(self):
        from baselayer.extract_facts import _get_extraction_caps
        caps = _get_extraction_caps(1)
        assert caps["max_facts"] == 10


# ============================================================
# COMPUTE_CONFIDENCE
# ============================================================

class TestComputeConfidence:
    """Test objective confidence score computation."""

    def test_high_confidence_user_does(self):
        from baselayer.extract_facts import compute_confidence
        score = compute_confidence(0.9, "does", "user", 30)
        assert 0.8 < score <= 1.0

    def test_low_confidence_curious_other(self):
        from baselayer.extract_facts import compute_confidence
        score = compute_confidence(0.3, "curious", "friend", 5)
        assert score < 0.5

    def test_clamped_to_0_1(self):
        from baselayer.extract_facts import compute_confidence
        score_high = compute_confidence(2.0, "does", "user", 100)
        assert score_high <= 1.0
        score_low = compute_confidence(-1.0, "curious", "other", 1)
        assert score_low >= 0.0

    def test_depth_score_caps_at_one(self):
        from baselayer.extract_facts import compute_confidence
        # message_count=60 -> depth=60/30=2.0, capped at 1.0
        score = compute_confidence(0.5, "does", "user", 60)
        expected = 0.20 * 0.5 + 0.30 * 1.0 + 0.25 * 1.0 + 0.25 * 1.0
        assert abs(score - expected) < 0.01

    def test_subject_user_gets_higher_score(self):
        from baselayer.extract_facts import compute_confidence
        user_score = compute_confidence(0.5, "does", "user", 10)
        other_score = compute_confidence(0.5, "does", "friend", 10)
        assert user_score > other_score

    def test_intent_ordering(self):
        from baselayer.extract_facts import compute_confidence
        does_score = compute_confidence(0.5, "does", "user", 10)
        learning_score = compute_confidence(0.5, "learning", "user", 10)
        curious_score = compute_confidence(0.5, "curious", "user", 10)
        assert does_score > learning_score > curious_score

    def test_returns_rounded(self):
        from baselayer.extract_facts import compute_confidence
        score = compute_confidence(0.7, "does", "user", 15)
        # Should be rounded to 4 decimal places
        assert score == round(score, 4)


# ============================================================
# _PREDICATE_TO_INTENT
# ============================================================

class TestPredicateToIntent:
    """Test predicate-to-intent mapping."""

    def test_learning_predicates(self):
        from baselayer.extract_facts import _predicate_to_intent
        assert _predicate_to_intent("studies") == "learning"
        assert _predicate_to_intent("learned") == "learning"

    def test_historical_predicates(self):
        from baselayer.extract_facts import _predicate_to_intent
        assert _predicate_to_intent("experienced") == "historical"
        assert _predicate_to_intent("lost") == "historical"
        assert _predicate_to_intent("founded") == "historical"
        assert _predicate_to_intent("graduated_from") == "historical"
        assert _predicate_to_intent("raised_in") == "historical"

    def test_default_is_does(self):
        from baselayer.extract_facts import _predicate_to_intent
        assert _predicate_to_intent("values") == "does"
        assert _predicate_to_intent("owns") == "does"
        assert _predicate_to_intent("unknown_pred") == "does"
