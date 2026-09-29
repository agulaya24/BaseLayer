"""The standards every check applies.

These are written into every report BEFORE any rater output exists, so a result
cannot quietly redefine the standard it was judged against. Changing one means
bumping DEFINITIONS_VERSION.
"""

DEFINITIONS_VERSION = "verify-definitions/2"   # /2: voice mode is per fact; every evidence span is re-gated

# docs/core/TURN_CONTRACT.md: the version and the citable voice classes, from the
# one module that defines them (the importer writes both).
from baselayer.voice import CITABLE_VOICE_CLASSES as OWN_VOICE_CLASSES  # noqa: E402
from baselayer.voice import TURN_CONTRACT_VERSION  # noqa: E402

# Conversation sources that import a document rather than a dialogue. A fact from
# one of these is "document_import": whether the subject wrote the document is not
# settled by the conversation record.
DOCUMENT_SOURCES = ("text_file",)

# user_corrections types that retire a fact.
RETIRING_CORRECTIONS = ("DELETE", "refuted", "REATTRIBUTE")

# Deterministic thresholds. Stipulated, not derived; each is exercised by a
# planted known-good and known-bad case in tests/test_verification.py.
SHARED_EVIDENCE_JACCARD = 0.5   # two claims citing mostly the same facts
WEAK_SUPPORT_RATIO = 0.5
NOT_HIS_RATIO = 0.5
NOT_HIS_MIN_LOCATED = 3
TRIGGER_GROUP_COSINE = 0.35     # single-link grouping of Active_When text

DEFINITIONS = {
    "version": DEFINITIONS_VERSION,
    "qualified_id": "every claim reference is '<spec label>:<claim id>'. A claim id is only unique inside its own specification.",
    "resolution": "a cited id resolves when exactly one memory_facts row has that id or 8-hex prefix, superseded_by is null, "
                  "and the id is not original_fact_id of a user_corrections row of type DELETE, refuted or REATTRIBUTE.",
    "voice_turn_contract": "a cited fact is gated iff its turn_contract_version is set (mode is per fact, not per database). "
                           "A gated fact's voice is its first evidence span's turn voice_class, and it is own only if every span's turn is. "
                           "The fact must also pass the turn-contract gate again: the turn exists, its voice_class is own_typed "
                           "or own_dictated, and each span in evidence_spans is a normalised substring of its turn's text.",
    "voice_conversation_fallback": "for a fact with no turn_contract_version (a legacy fact, or a database without the turn-contract columns), voice is asserted only as far as the conversation record "
                                   "proves it: no_conversation, document_import (own vs pasted undetermined), no_subject_turns "
                                   "(not own), or unresolved_turn_level (routed to the model voice check). No turn id is invented.",
    "support_ratio": "(supports + 0.5 * partial) / judged facts; unrelated and contradicts count 0. "
                     f"A claim is weak when support_ratio < {WEAK_SUPPORT_RATIO}.",
    "own_voice_ratio": "(own facts) / located facts, located = voice settled either way; unknown and unresolved are excluded "
                       f"and counted. A claim is not_his when own_voice_ratio < {NOT_HIS_RATIO} with at least "
                       f"{NOT_HIS_MIN_LOCATED} located facts. The flag uses the lenient count (fair_description counts as "
                       "own); own_voice_ratio_strict, which does not, is reported beside it.",
    "fidelity_labels": {
        "own_words": "the fact's content is in the subject's own words in the cited turn, read with its context",
        "fair_description": "the fact describes what the subject did or said, and the subject's own turn shows it; "
                            "the assistant's account of what they did does not count",
        "overreach": "the subject's turn supports a narrower or weaker statement than the fact makes",
        "misread": "the fact misstates the turn: wrong polarity, a hypothetical recorded as fact, wrong subject, garbled",
        "not_his": "the content originates in context the subject did not write (assistant, pasted, another person)",
    },
    "fidelity_standards": "reported under BOTH standards from one set of labels: strict = own_words only; "
                          "lenient = own_words + fair_description. The report never picks one silently.",
    "contested_unsupported": "contested=true and at least one side has zero supports-or-partial facts assigned to it.",
    "contested_confirmed": "a within-claim contested pair read in source context came back context_split or real_contradiction.",
    "duplicates": "deterministic: identical normalised claim names, or cited-fact Jaccard >= "
                  f"{SHARED_EVIDENCE_JACCARD}. Paraphrase duplicates are NOT reliably detectable lexically (measured on a real "
                  "specification, an identical-name pair scored TF-IDF cosine below 0.1), so lexical scores only select candidates for the model.",
    "trigger_groups": "Active_When text: identical normalised triggers, single-link TF-IDF groups at cosine >= "
                      f"{TRIGGER_GROUP_COSINE}, and the lexical 'standing' rule ^(always|any|anything). The lexical rule "
                      "describes the TEXT; it is measured not to predict firing and must not be quoted as behaviour.",
    "truth": "whether a claim is true of the person is out of scope. Verification checks evidence, voice and structure.",
}
