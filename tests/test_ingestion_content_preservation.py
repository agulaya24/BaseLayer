"""
Content-preservation tests for the ingestion pipeline.

Verifies the 2026-05-17 principle: raw input data reaches the extraction LLM.
AUDN handles redundancy downstream. The pipeline must not silently drop content
before the LLM call.

Four tests:
1. _abstract_project_conversation produces text that, when windowed, preserves
   all user-message-body sentinels and intentionally strips code/tool/long-asst.
2. extract_facts_from_conversation chunking path fires on single-long-message
   conversations (not only on conversations whose total exceeds budget).
3. _build_chunk_requests fans out a long conversation into the right number of
   batch requests with the right chunk_info per request.
4. _upsert_extraction_log accumulates facts_extracted across chunks instead of
   overwriting (so a multi-chunk conversation reports the total fact count).
"""

import pytest
import sqlite3
from unittest.mock import patch, MagicMock


# Sentinel markers — all unique strings unlikely to occur naturally.
SENTINELS = {
    "early": "SENTINEL_EARLY_4f7a91b2",
    "mid": "SENTINEL_MID_8c2e5d31",
    "late": "SENTINEL_LATE_9a3b8f04",
    "deep": "SENTINEL_DEEP_2d4f76a8",
    "code": "SENTINEL_CODE_5b9e1c63",          # negative control
    "tool": "SENTINEL_TOOL_7e8d4a92",          # negative control
    "asst_long": "SENTINEL_ASST_LONG_3a6c2e45", # negative control (D-048)
    "asst_short": "SENTINEL_ASST_SHORT_6b1d8f02",
}


def _make_long_user_msg(sentinel_at_8000):
    """User message ~12K chars with a sentinel at char position 8000."""
    filler_a = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 140  # ~8000 chars
    filler_b = "Pellentesque habitant morbi tristique senectus et netus. " * 70   # ~4000 chars
    return filler_a[:8000] + sentinel_at_8000 + " " + filler_b


def _build_synthetic_messages():
    """200-message synthetic conversation, ~80K abstracted chars, sentinels
    placed across positions and inside negative-control wrappers."""
    messages = []

    # Msg 1: early user sentinel + code-block negative + tool-block negative
    messages.append({
        "role": "user",
        "text": (
            f"Starting work on the auth refactor. {SENTINELS['early']}\n"
            f"Here is some code:\n"
            f"```python\n"
            f"def stripped(): pass  # {SENTINELS['code']}\n"
            f"```\n"
            f"And some tool output: <tool_result>some path {SENTINELS['tool']}</tool_result>"
        ),
    })

    # Msg 2: short assistant (should be preserved)
    messages.append({
        "role": "assistant",
        "text": f"Understood. Marker: {SENTINELS['asst_short']}",
    })

    # Msg 3: long assistant (should be reduced to first line, sentinel dropped)
    long_asst_body = "A" * 200 + " " + SENTINELS['asst_long'] + " " + "B" * 1800
    messages.append({"role": "assistant", "text": "First line of analysis.\n" + long_asst_body})

    # Filler middle messages to bulk the conversation to ~80K abstracted chars
    for i in range(4, 100):
        messages.append({
            "role": "user",
            "text": f"Iteration {i}: I want to focus on " +
                    ("backend reliability " * 20),
        })
        messages.append({
            "role": "assistant",
            "text": "Acknowledged.",  # short, kept
        })

    # Msg ~100: mid sentinel
    messages.append({"role": "user", "text": f"Midpoint check-in. {SENTINELS['mid']}"})

    # More filler
    for i in range(101, 195):
        messages.append({
            "role": "user",
            "text": f"Iteration {i}: continuing on the refactor pattern, " +
                    ("structured priors over heuristics " * 18),
        })

    # Msg ~196: long user message with deep sentinel
    messages.append({"role": "user", "text": _make_long_user_msg(SENTINELS['deep'])})

    # Msg ~197: late sentinel
    messages.append({"role": "user", "text": f"Wrapping up the session. {SENTINELS['late']}"})

    return messages


# ============================================================
# Test 1: project-conversation abstraction + windowing
# ============================================================

class TestProjectConversationContentPreservation:
    """Sentinels in user-message bodies survive through abstraction and windowing.
    Sentinels inside code blocks, tool tags, and long assistant turns are absent."""

    def test_abstraction_preserves_user_content_no_truncation(self):
        from baselayer.extract_facts import _abstract_project_conversation

        messages = _build_synthetic_messages()
        abstracted = _abstract_project_conversation(messages)

        # Positive controls: all user-body sentinels present in abstracted text
        assert SENTINELS["early"] in abstracted
        assert SENTINELS["mid"] in abstracted
        assert SENTINELS["late"] in abstracted
        assert SENTINELS["deep"] in abstracted, \
            "Deep sentinel at char 8000 of a 12K-char user message must survive"
        assert SENTINELS["asst_short"] in abstracted

        # Negative controls: stripped/truncated content must be absent
        assert SENTINELS["code"] not in abstracted, "Code-block content must be stripped"
        assert SENTINELS["tool"] not in abstracted, "Tool-block content must be stripped"
        assert SENTINELS["asst_long"] not in abstracted, \
            "Long assistant message body must be reduced to first line (D-048)"

    def test_chunking_preserves_sentinels_across_windows(self):
        from baselayer.extract_facts import (
            _abstract_project_conversation, _chunk_text_for_extraction
        )

        messages = _build_synthetic_messages()
        abstracted = _abstract_project_conversation(messages)

        # Force multi-window
        budget = 24000
        chunks = _chunk_text_for_extraction(abstracted, budget, overlap=0)
        assert len(chunks) > 1, \
            f"Synthetic conv ({len(abstracted)} chars) should produce multiple chunks at {budget} budget"

        joined = "\n".join(chunks)
        for key in ("early", "mid", "late", "deep", "asst_short"):
            assert SENTINELS[key] in joined, f"Sentinel '{key}' lost across windows"

        for key in ("code", "tool", "asst_long"):
            assert SENTINELS[key] not in joined, f"Negative-control '{key}' must be absent"


# ============================================================
# Test 2: standard path chunking trigger on single long message
# ============================================================

class TestStandardPathSingleLongMessage:
    """A short conversation containing one long message must trigger the
    chunking path so [:1500] truncation never applies."""

    def test_long_single_message_triggers_chunking(self):
        from baselayer.extract_facts import extract_facts_from_conversation

        # 5 messages: 4 short, 1 very long (50K chars) with a deep sentinel
        sentinel = "SENTINEL_LONG_MSG_a91f3c"
        long_text = ("Filler about preferences. " * 200) + sentinel + (" Trailing context. " * 500)
        # ~50K chars total in the long message

        messages = [
            {"role": "user", "text": "Short opener."},
            {"role": "assistant", "text": "Short reply."},
            {"role": "user", "text": long_text},
            {"role": "assistant", "text": "Short reply 2."},
            {"role": "user", "text": "Short closer."},
        ]

        captured_prompts = []

        def fake_call_llm(prompt, schema=None):
            captured_prompts.append(prompt)
            return {"facts": []}

        with patch("baselayer.extract_facts.call_llm", side_effect=fake_call_llm):
            extract_facts_from_conversation("conv-1", "Long Msg Test", messages)

        assert len(captured_prompts) >= 1, "Expected at least one extraction call"
        joined = "\n".join(captured_prompts)
        assert sentinel in joined, \
            "Deep sentinel inside a single long message must reach the extractor (no [:1500] truncation)"


# ============================================================
# Test 3: batch submit fans out long conversations into windowed requests
# ============================================================

class TestBatchChunkRequests:
    """_build_chunk_requests produces N requests per long conversation with
    correct chunk_info and chunk_map entries."""

    def test_short_text_produces_single_request(self):
        from baselayer.batch_extract import _build_chunk_requests

        captured = []
        def prompt_builder(title, text, max_facts=None, chunk_info=None):
            captured.append({"title": title, "text": text, "chunk_info": chunk_info})
            return f"PROMPT[{text[:30]}]"

        chunk_map = {}
        requests = _build_chunk_requests(
            conv_id="conv-1",
            conv_title="Short Conv",
            abstracted_text="A short body of text.",
            source="claude_code",
            input_char_budget=24000,
            max_facts=50,
            prompt_builder=prompt_builder,
            model="claude-haiku-x",
            max_tokens=2000,
            temperature=0.1,
            json_instruction="JSON: ",
            chunk_map=chunk_map,
        )

        assert len(requests) == 1
        assert requests[0]["custom_id"] == "conv-1"
        assert chunk_map["conv-1"]["parent_conv_id"] == "conv-1"
        assert chunk_map["conv-1"]["chunk_idx"] == 1
        assert chunk_map["conv-1"]["total_chunks"] == 1
        assert chunk_map["conv-1"]["source"] == "claude_code"
        assert captured[0]["chunk_info"] is None

    def test_long_text_produces_multiple_requests(self):
        from baselayer.batch_extract import _build_chunk_requests

        # Build a text well over the 24K budget. Use paragraph boundaries so
        # _chunk_text_for_extraction can split it cleanly.
        para = "This is a sentence. " * 50  # ~1000 chars
        long_text = "\n\n".join([f"Paragraph {i}: {para}" for i in range(80)])  # ~80K chars

        captured = []
        def prompt_builder(title, text, max_facts=None, chunk_info=None):
            captured.append({"chunk_info": chunk_info, "text_len": len(text)})
            return f"PROMPT[len={len(text)}, info={chunk_info}]"

        chunk_map = {}
        requests = _build_chunk_requests(
            conv_id="long-conv",
            conv_title="Long Conv",
            abstracted_text=long_text,
            source="claude_code",
            input_char_budget=24000,
            max_facts=50,
            prompt_builder=prompt_builder,
            model="claude-haiku-x",
            max_tokens=2000,
            temperature=0.1,
            json_instruction="JSON: ",
            chunk_map=chunk_map,
        )

        assert len(requests) >= 3, f"Expected 3+ chunks from {len(long_text)} chars at 24K budget"
        n = len(requests)
        for i, req in enumerate(requests):
            expected_custom_id = f"long-conv__c{i+1}of{n}"
            assert req["custom_id"] == expected_custom_id, \
                f"Request {i} custom_id: got {req['custom_id']}, want {expected_custom_id}"
            assert chunk_map[expected_custom_id]["parent_conv_id"] == "long-conv"
            assert chunk_map[expected_custom_id]["chunk_idx"] == i + 1
            assert chunk_map[expected_custom_id]["total_chunks"] == n
            assert chunk_map[expected_custom_id]["source"] == "claude_code"
            assert captured[i]["chunk_info"] is not None
            assert f"Section {i+1} of {n}" in captured[i]["chunk_info"]


# ============================================================
# Test 4: extraction_log upsert with sum semantics + chunks_done writes
# ============================================================

class TestExtractionLogUpsertSum:
    """_upsert_extraction_log accumulates facts_extracted across chunk writes
    instead of overwriting (so a 5-chunk conv with 10 facts each totals 50)."""

    def _make_db(self, tmp_path):
        db = tmp_path / "x.db"
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        # Minimal extraction_log schema: PK on conversation_id (matches production)
        conn.execute("""
            CREATE TABLE extraction_log (
                conversation_id TEXT PRIMARY KEY,
                facts_extracted INTEGER,
                processed_at REAL
            )
        """)
        return conn

    def test_upsert_first_write_inserts(self, tmp_path):
        from baselayer.batch_extract import _upsert_extraction_log
        conn = self._make_db(tmp_path)

        _upsert_extraction_log(conn, "conv-A", 7, 1000.0)
        conn.commit()

        row = conn.execute("SELECT * FROM extraction_log").fetchone()
        assert row["conversation_id"] == "conv-A"
        assert row["facts_extracted"] == 7

    def test_upsert_subsequent_writes_sum(self, tmp_path):
        from baselayer.batch_extract import _upsert_extraction_log
        conn = self._make_db(tmp_path)

        # Five chunks, 10 facts each
        for i in range(5):
            _upsert_extraction_log(conn, "conv-B", 10, 1000.0 + i)
        conn.commit()

        row = conn.execute("SELECT * FROM extraction_log WHERE conversation_id='conv-B'").fetchone()
        assert row["facts_extracted"] == 50, \
            "Chunked conversation must accumulate fact counts across chunks"

    def test_upsert_processed_at_takes_latest(self, tmp_path):
        from baselayer.batch_extract import _upsert_extraction_log
        conn = self._make_db(tmp_path)

        _upsert_extraction_log(conn, "conv-C", 5, 1000.0)
        _upsert_extraction_log(conn, "conv-C", 5, 2000.0)
        conn.commit()

        row = conn.execute("SELECT * FROM extraction_log WHERE conversation_id='conv-C'").fetchone()
        assert row["processed_at"] == 2000.0
        assert row["facts_extracted"] == 10


class TestBatchTokenBudget:
    """Regression: BATCH_MAX_TOKENS must accommodate the per-chunk fact cap.

    2026-05-18: 662 of 2287 chunks (29%) errored on the first batch run because
    BATCH_MAX_TOKENS was 2000 but per_chunk_cap was 50 facts × ~120 tokens of
    structured JSON each = ~6000 tokens. Truncated responses failed JSON parsing.
    """

    def test_batch_max_tokens_accommodates_per_chunk_cap(self):
        from baselayer.batch_extract import BATCH_MAX_TOKENS

        # Conservative estimate per structured fact: ~120 output tokens
        # (subject, predicate, object, qualifier, category, temporal, confidence
        # as JSON). per_chunk_cap caps at min(50, max_facts) inside
        # _build_chunk_requests; 50 is the maximum it can hit.
        per_chunk_cap_max = 50
        tokens_per_fact_estimate = 120
        wrapping_overhead = 200  # outer JSON {"facts": [...]} + whitespace

        required = per_chunk_cap_max * tokens_per_fact_estimate + wrapping_overhead
        # Plus a safety margin: structured generation is bursty.
        required_with_margin = int(required * 1.2)

        assert BATCH_MAX_TOKENS >= required_with_margin, (
            f"BATCH_MAX_TOKENS ({BATCH_MAX_TOKENS}) is too low for the "
            f"{per_chunk_cap_max}-fact per-chunk cap. Need at least "
            f"{required_with_margin}. Otherwise dense chunks truncate JSON "
            f"responses and fail to parse."
        )


class TestChunksDoneTable:
    """_ensure_extraction_chunks_done_table creates a per-batch chunk-completion
    table that's safe to re-run."""

    def test_create_is_idempotent(self, tmp_path):
        from baselayer.batch_extract import _ensure_extraction_chunks_done_table
        db = tmp_path / "y.db"
        conn = sqlite3.connect(str(db))
        _ensure_extraction_chunks_done_table(conn)
        _ensure_extraction_chunks_done_table(conn)  # second call must not raise
        conn.commit()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(extraction_chunks_done)").fetchall()}
        assert {"custom_id", "batch_id", "parent_conv_id", "facts_extracted", "processed_at"} <= cols

    def test_pk_prevents_duplicate_chunk_writes(self, tmp_path):
        from baselayer.batch_extract import _ensure_extraction_chunks_done_table
        db = tmp_path / "z.db"
        conn = sqlite3.connect(str(db))
        _ensure_extraction_chunks_done_table(conn)

        conn.execute("""
            INSERT OR REPLACE INTO extraction_chunks_done
            (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("c1__c1of2", "batch-X", "c1", 3, 1.0))
        conn.execute("""
            INSERT OR REPLACE INTO extraction_chunks_done
            (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("c1__c1of2", "batch-X", "c1", 5, 2.0))
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM extraction_chunks_done WHERE custom_id='c1__c1of2' AND batch_id='batch-X'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][3] == 5  # latest write wins for same (custom_id, batch_id)


# ============================================================
# Pipeline stability fixes (2026-05-19) — see
# docs/internal/pipeline_issues_v2_spec_generation_20260519.md
# ============================================================

def _make_facts_db(tmp_path, name="facts.db"):
    """Minimal memory_facts table covering the columns the stability-fix
    functions touch."""
    conn = sqlite3.connect(str(tmp_path / name))
    conn.execute("""
        CREATE TABLE memory_facts (
            id TEXT PRIMARY KEY,
            superseded_by TEXT,
            knowledge_tier TEXT,
            commitment_depth TEXT,
            scope TEXT,
            predicate TEXT
        )
    """)
    return conn


def _insert_fact(conn, fid, predicate=None, knowledge_tier="untiered",
                 commitment_depth="unclassified", scope="personal",
                 superseded_by=None):
    conn.execute(
        "INSERT INTO memory_facts (id, superseded_by, knowledge_tier, "
        "commitment_depth, scope, predicate) VALUES (?, ?, ?, ?, ?, ?)",
        (fid, superseded_by, knowledge_tier, commitment_depth, scope, predicate),
    )


class TestTierFactsByPredicate:
    """tier_facts_by_predicate routes facts to identity/contextual by predicate
    and is idempotent (only touches untiered facts)."""

    def test_identity_predicates_tier_to_identity(self, tmp_path):
        from baselayer.extract_facts import tier_facts_by_predicate
        from baselayer.config import IDENTITY_PREDICATES
        conn = _make_facts_db(tmp_path)
        # 3 identity-predicate facts, 2 non-identity
        id_pred = list(IDENTITY_PREDICATES)[0]
        _insert_fact(conn, "f1", predicate=id_pred)
        _insert_fact(conn, "f2", predicate=id_pred)
        _insert_fact(conn, "f3", predicate=list(IDENTITY_PREDICATES)[1])
        _insert_fact(conn, "f4", predicate="owns")       # not in IDENTITY_PREDICATES
        _insert_fact(conn, "f5", predicate="lives_in")   # not in IDENTITY_PREDICATES
        conn.commit()

        id_count, ctx_count = tier_facts_by_predicate(conn)
        conn.commit()

        assert id_count == 3
        assert ctx_count == 2
        tiers = dict(conn.execute(
            "SELECT id, knowledge_tier FROM memory_facts"
        ).fetchall())
        assert tiers["f1"] == "identity"
        assert tiers["f4"] == "contextual"

    def test_idempotent_only_touches_untiered(self, tmp_path):
        from baselayer.extract_facts import tier_facts_by_predicate
        from baselayer.config import IDENTITY_PREDICATES
        conn = _make_facts_db(tmp_path)
        id_pred = list(IDENTITY_PREDICATES)[0]
        # Pre-tiered fact must not be re-touched
        _insert_fact(conn, "pre", predicate="owns", knowledge_tier="identity")
        _insert_fact(conn, "new", predicate=id_pred, knowledge_tier="untiered")
        conn.commit()

        tier_facts_by_predicate(conn)
        conn.commit()
        # Second call must be a no-op
        id_count, ctx_count = tier_facts_by_predicate(conn)
        assert id_count == 0 and ctx_count == 0

        tiers = dict(conn.execute("SELECT id, knowledge_tier FROM memory_facts").fetchall())
        assert tiers["pre"] == "identity"  # untouched despite non-identity predicate
        assert tiers["new"] == "identity"


class TestHasTieredFactsThreshold:
    """_has_tiered_facts must require a meaningful fraction of the corpus to be
    fully classified — a residue of legacy facts cannot flip pipeline mode.
    Regression for the 2026-05-19 PREDICTIONS-starvation incident."""

    def test_legacy_residue_does_not_flip_mode(self, tmp_path):
        from baselayer.author_layers import _has_tiered_facts
        conn = _make_facts_db(tmp_path)
        # 9 fully-classified legacy facts, 9991 simplified facts
        for i in range(9):
            _insert_fact(conn, f"legacy{i}", predicate="values",
                         knowledge_tier="identity", commitment_depth="factual",
                         scope="personal")
        for i in range(9991):
            _insert_fact(conn, f"new{i}", predicate="values",
                         knowledge_tier="untiered", commitment_depth="unclassified",
                         scope="personal")
        conn.commit()
        # 9 / 10000 = 0.0009 — far below threshold; simplified mode
        assert _has_tiered_facts(conn) is False

    def test_fully_classified_corpus_uses_legacy_path(self, tmp_path):
        from baselayer.author_layers import _has_tiered_facts
        conn = _make_facts_db(tmp_path)
        # 60 of 100 facts fully classified — above the 0.5 threshold
        for i in range(60):
            _insert_fact(conn, f"c{i}", predicate="values",
                         knowledge_tier="identity", commitment_depth="conviction",
                         scope="personal")
        for i in range(40):
            _insert_fact(conn, f"u{i}", predicate="values",
                         knowledge_tier="untiered", commitment_depth="unclassified",
                         scope="personal")
        conn.commit()
        assert _has_tiered_facts(conn) is True

    def test_empty_corpus_is_simplified(self, tmp_path):
        from baselayer.author_layers import _has_tiered_facts
        conn = _make_facts_db(tmp_path)
        conn.commit()
        assert _has_tiered_facts(conn) is False
