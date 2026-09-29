"""
Batch Re-extraction via Anthropic Message Batches API

Re-extracts ALL conversations using Variant D structured extraction (D-056 Tier 2)
with 50% cost reduction via the Batch API. Resolves release blocker #20.

Three-phase workflow:
    python batch_extract.py --submit     # Build prompts, submit batch, save batch_id
    python batch_extract.py --status     # Poll batch processing status
    python batch_extract.py --process    # Reset old facts, process results, store

Cost: ~$4-8 total for 1,892 conversations (Haiku Batch pricing).

User can submit, close terminal, come back later to check status and process.
Batch ID persisted to data/database/batch_state.json.
"""

import contextlib
import functools
import sys
import io
import json
import time
import uuid
import argparse
import os
from pathlib import Path
from datetime import datetime

# NOTE: sys.stdout/stderr wrappers moved to if __name__ == "__main__" block
# to avoid corrupting pytest's capture mechanism on import.

from baselayer.config import (
    PROJECT_ROOT, DATABASE_FILE, VECTORS_DIR, EMBEDDING_MODEL,
    EXTRACTION_API_MODEL, EXTRACTION_BACKEND,
    CONSTRAINED_PREDICATES,
    SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE, is_claude_code_source,
    MIN_MESSAGES_FOR_EXTRACTION,
    get_db,
)

from baselayer.extract_facts import (
    EXTRACT_SCHEMA, EXTRACT_SCHEMA_FALLBACK,
    build_extraction_prompt,
    build_identity_extraction_prompt,
    build_document_extraction_prompt,
    _abstract_project_conversation,
    _chunk_text_for_extraction,
    _get_extraction_caps,
    validate_structured_response,
    store_fact,
    embed_fact,
    link_facts,
    tier_facts_by_predicate,
    load_corrections,
    check_against_corrections,
    _ensure_structured_columns,
    find_similar_facts,
    make_audn_decision,
    response_text,
    _strip_json_fences,
    ExtractionResponseError,
    json_instruction_for,
    _legacy_stamp,
    # turn contract (docs/core/TURN_CONTRACT.md): same prompts, gate and
    # storage as the sequential path, so the batch path cannot be a bypass
    TURN_CONTRACT_VERSION,
    TURN_EXTRACT_SCHEMA,
    TurnContractViolation,
    _turn_contract_enabled,
    assert_fresh_for_turn_contract,
    assert_legacy_allowed,
    build_turn_chunks,
    finalize_turn_facts,
    store_turn_facts,
    turn_chunk_prompt,
    turn_chunk_max_tokens,
    rechunk_after_max_tokens,
    turn_extraction_plan,
    turn_referent,
    turn_run_settings,
    turn_stamps,
    check_turn_versions,
    _TURN_MODE_ACTIVE,
    mark_turn_conversation_extracted,
    _turn_conversations_to_process,
    reset_usage,
    usage_calls,
    reset_response_failures,
    response_failures,
    _CURRENT_CONVERSATION,
    # failed chunks: recorded as FAILED, retried alone (extract_facts, "Failed chunks")
    FAILED_CHUNKS_TABLE,
    failed_chunk,
    failures_of,
    failed_chunk_plan,
    failed_chunks_table_exists,
    load_failed_chunks,
    note_failed_chunks,
    rebuild_failed_chunk,
    retry_failed_chunks,
    upsert_log_sum,
    write_failed_chunks,
)


def _batch_usage(result, conv_id, custom_id, meta=None):
    """Billed tokens of one batch result (zeroed and marked when it carries no usage).
    Recorded for every SUCCEEDED result before it is parsed: an unusable response is billed.
    Carries the chunk's citable characters when the chunk map recorded them."""
    msg = getattr(result.result, "message", None)
    extra = {}
    if meta and meta.get("citable_chars") is not None:
        extra = {"chunk": meta.get("chunk_idx"), "citable_chars": meta["citable_chars"]}
    return _tc.usage_entry(getattr(msg, "usage", None), purpose="extract", model=getattr(msg, "model", None),
                           batch=True, conversation_id=conv_id, custom_id=custom_id, **extra)


def _scoped_turn_mode(fn):
    """Restore the turn-mode flag when a batch entry point returns, so a turn-mode
    batch never changes the defaults of a later legacy run in the same process.
    The entry point sets the flag once it knows its mode (D-108: the dynamic cap
    defaults on in turn mode, and a batch's mode may come from its state file
    rather than BASELAYER_TURN_CONTRACT)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = _TURN_MODE_ACTIVE.set(_TURN_MODE_ACTIVE.get())
        try:
            return fn(*args, **kwargs)
        finally:
            _TURN_MODE_ACTIVE.reset(token)
    return wrapper
from baselayer import turn_contract as _tc


def extract_facts_module_file():
    import baselayer.extract_facts as _ef
    return _ef.__file__

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _get_batch_state_file():
    """Get batch state file path — resolves at call time to respect MEMORY_SYSTEM_ROOT changes."""
    from baselayer.config import PROJECT_ROOT as _ROOT
    return _ROOT / "data" / "database" / "batch_state.json"

BATCH_STATE_FILE = _get_batch_state_file()  # Default for direct CLI usage
# 2026-05-18: raised from 2000. The 50-fact per-chunk cap × ~120 tokens of
# structured-JSON per fact = ~6,000 output tokens; the 2000 ceiling truncated
# responses on dense chunks and caused 662 of 2287 chunks (29%) to fail JSON
# parsing on the first run. 8000 leaves headroom and stays well under Haiku 4.5's
# 8192 max-output-token cap. Sync path (api_client.call_api) defaults to 4096,
# which is why the sync smoke test on the same input succeeded.
BATCH_MAX_TOKENS = 8000
BATCH_TEMPERATURE = 0.1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_batch_state():
    """Load persisted batch state. Resolves path dynamically for multi-subject support."""
    path = _get_batch_state_file()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_batch_state(state):
    """Persist batch state to disk. Resolves path dynamically for multi-subject support."""
    path = _get_batch_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _get_anthropic_client():
    """Get Anthropic client with retry and timeout (delegates to api_client)."""
    from baselayer.api_client import get_anthropic_client
    return get_anthropic_client()


def _build_conv_text(messages):
    """Build full conversation text from messages for extraction prompt.

    2026-05-17: Per-message [:1500] cap and 12K hard-break removed. Callers
    that need windowing should consult _get_extraction_caps and chunk via
    _chunk_text_for_extraction. AUDN dedups across chunks.
    """
    conv_text = ""
    for msg in messages:
        role = msg["role"].capitalize()
        text = msg["text"]
        conv_text += f"{role}: {text}\n"
    return conv_text


def _build_request_for_conv(custom_id, prompt, model, max_tokens, temperature, json_instruction):
    """Build a single batch request dict."""
    return {
        "custom_id": custom_id,
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "user", "content": json_instruction + prompt}
            ],
        },
    }


def _build_chunk_requests(conv_id, conv_title, abstracted_text, source, input_char_budget,
                          max_facts, prompt_builder, model, max_tokens, temperature,
                          json_instruction, chunk_map, overlap=None):
    """Split a long abstracted/built text into windowed batch requests.

    Returns a list of request dicts. Populates chunk_map in place with
    {custom_id: {parent_conv_id, chunk_idx, total_chunks, source}} entries
    for downstream result processing.

    Custom_id format: '{conv_id}' for single-chunk; '{conv_id}__c{i}of{n}' for
    multi-chunk. The chunk_map is the source of truth — custom_id format is for
    debugging only.

    Args:
        overlap: chunk overlap in chars for prose continuity. None = source-aware
            default (0 for claude_code/turn-bounded, 500 for prose corpora).
    """
    if overlap is None:
        # claude_code abstractions are turn-bounded; overlap wastes budget.
        # Document/ChatGPT prose benefits from continuity overlap.
        overlap = 0 if is_claude_code_source(source) else 500

    requests = []
    if len(abstracted_text) <= input_char_budget:
        custom_id = conv_id
        chunk_map[custom_id] = {
            "parent_conv_id": conv_id,
            "chunk_idx": 1,
            "total_chunks": 1,
            "source": source,
        }
        prompt = prompt_builder(conv_title, abstracted_text, max_facts=max_facts)
        requests.append(_build_request_for_conv(
            custom_id, prompt, model, max_tokens, temperature, json_instruction
        ))
        return requests

    chunks = _chunk_text_for_extraction(abstracted_text, input_char_budget, overlap=overlap)
    per_chunk_cap = min(50, max_facts)
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        chunk_idx = i + 1
        custom_id = f"{conv_id}__c{chunk_idx}of{total}"
        chunk_map[custom_id] = {
            "parent_conv_id": conv_id,
            "chunk_idx": chunk_idx,
            "total_chunks": total,
            "source": source,
        }
        chunk_info = f"Section {chunk_idx} of {total} from '{conv_title}'."
        prompt = prompt_builder(
            conv_title, chunk, max_facts=per_chunk_cap, chunk_info=chunk_info
        )
        requests.append(_build_request_for_conv(
            custom_id, prompt, model, max_tokens, temperature, json_instruction
        ))
    return requests


def _parse_batch_message(message):
    """Parse a batch result message into the extraction JSON dict.

    Reads content blocks by type (a 5-generation model puts a thinking block
    first). Raises ExtractionResponseError on refusal / max_tokens / no text and
    json.JSONDecodeError on malformed JSON; the caller counts both.
    """
    return json.loads(_strip_json_fences(response_text(message)))


def _get_conversation_messages(conn, conv_id):
    """Get messages for a conversation."""
    rows = conn.execute("""
        SELECT role, content_text as text
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at
    """, (conv_id,)).fetchall()
    return [{"role": r["role"], "text": r["text"] or ""} for r in rows]


# ---------------------------------------------------------------------------
# Phase 1: SUBMIT
# ---------------------------------------------------------------------------

def _turn_requests_for_conversation(conn, conv_id, conv_title, source, *, stamps, model,
                                    temperature, json_instruction, chunk_map):
    """Turn-contract batch requests for one conversation: whole-turn chunks,
    only chunks with a citable subject turn, prompts identical to the
    sequential path. chunk_map keeps ids and offsets (manifest), never text."""
    turns = _tc.load_turns(conn, conv_id)
    if not turns:
        return None
    check_turn_versions(turns)
    project = is_claude_code_source(source)
    plan = turn_extraction_plan(turns, source)
    chunks = build_turn_chunks(turns, source, plan["input_char_budget"])
    live = [ch for ch in chunks if ch.has_citable]
    requests = []
    for ch in live:
        custom_id = conv_id if len(chunks) == 1 else f"{conv_id}__c{ch.index}of{ch.total}"
        chunk_map[custom_id] = {
            "parent_conv_id": conv_id,
            "chunk_idx": ch.index,
            "total_chunks": ch.total,
            "source": source,
            "project": project,
            "manifest": ch.manifest(),
            "plan": {k: plan[k] for k in ("max_facts", "per_chunk_cap", "total_chars",
                                          "fact_count_mode", "citable_chars")},
            "n_turns": len(turns),
            "citable_chars": ch.citable_chars,
        }
        prompt = turn_chunk_prompt(conv_title, ch, plan, project)
        requests.append(_build_request_for_conv(
            custom_id, prompt, model, turn_chunk_max_tokens(ch, plan), temperature,
            json_instruction))
    return requests, len(chunks) - len(live)


def _turn_retry_requests_for_conversation(conn, conv_id, conv_title, source, *, model,
                                          temperature, json_instruction, chunk_map):
    """Requests for ONLY the recorded failed chunks of a conversation whose other chunks are
    already stored. Each chunk is rebuilt exactly (extract_facts.rebuild_failed_chunk); its
    chunk_map entry carries `retry_of`, so processing settles that row and adds to the
    conversation's logged count instead of replacing it. A chunk that can no longer be
    rebuilt is left recorded and reported; the sequential retry marks it not_reproducible."""
    turns = _tc.load_turns(conn, conv_id)
    if not turns:
        return None
    check_turn_versions(turns)
    project = is_claude_code_source(source)
    base = turn_extraction_plan(turns, source)
    requests, unrebuilt = [], 0
    for k, row in enumerate(load_failed_chunks(conn, conv_id), 1):
        ch = rebuild_failed_chunk(turns, source, row)
        if ch is None:
            unrebuilt += 1
            continue
        plan = failed_chunk_plan(base, row)
        custom_id = f"{conv_id}__retry{k}"
        chunk_map[custom_id] = {
            "parent_conv_id": conv_id,
            "chunk_idx": ch.index,
            "total_chunks": ch.total,
            "source": source,
            "project": project,
            "manifest": ch.manifest(),
            "plan": plan,
            "n_turns": len(turns),
            "citable_chars": ch.citable_chars,
            "retry_of": {"chunk_key": row["chunk_key"],
                         "input_char_budget": row["input_char_budget"],
                         "turns_upto": row["turns_upto"]},
        }
        prompt = turn_chunk_prompt(conv_title, ch, plan, project)
        requests.append(_build_request_for_conv(
            custom_id, prompt, model, turn_chunk_max_tokens(ch, plan), temperature,
            json_instruction))
    if unrebuilt:
        print(f"  WARNING: {conv_id}: {unrebuilt} failed chunk(s) can no longer be rebuilt; "
              f"left recorded (the sequential extract marks them not_reproducible)")
    return requests, 0


@_scoped_turn_mode
def run_submit(document_mode=False, skip_extracted=False, turn_contract=None):
    """Build prompts for all conversations and submit as a batch.

    Args:
        document_mode: Use document extraction prompt (for subject corpora).
        skip_extracted: Only process conversations not yet in extraction_log.
        turn_contract: None = read BASELAYER_TURN_CONTRACT. True builds turn-contract
            requests (docs/core/TURN_CONTRACT.md); the gate is applied at --process.
    """
    turn_mode = _turn_contract_enabled() if turn_contract is None else bool(turn_contract)
    _TURN_MODE_ACTIVE.set(turn_mode)
    mode_label = "Document Corpus" if document_mode else "Re-extraction"
    if turn_mode:
        mode_label += f" under {TURN_CONTRACT_VERSION}"
    print("=" * 70)
    print(f"Batch {mode_label} — SUBMIT Phase")
    print("=" * 70)

    # Check for existing batch
    existing = _load_batch_state()
    if existing and existing.get("status") not in ("completed", "failed", "expired"):
        print(f"\nERROR: Active batch already exists.")
        print(f"  Batch ID: {existing.get('batch_id')}")
        print(f"  Submitted: {existing.get('created_at')}")
        print(f"  Use --status to check progress, or delete {BATCH_STATE_FILE} to start fresh.")
        return

    # JSON schema instruction: the same text the sequential path sends.
    schema = TURN_EXTRACT_SCHEMA if turn_mode else EXTRACT_SCHEMA
    json_instruction = json_instruction_for(schema)
    stamps = turn_stamps() if turn_mode else None

    print("\nLoading conversations from database...")

    with contextlib.closing(get_db()) as conn:
        # Mode guards, before any request is built and before any spend.
        if turn_mode:
            if document_mode:
                raise TurnContractViolation(
                    "--document-mode has no subject voice; the turn contract does not apply.")
            if not _tc.turn_rows_exist(conn):
                raise TurnContractViolation(
                    f"turn-contract batch needs the turn table '{_tc.TURN_TABLE}' with rows.")
            assert_fresh_for_turn_contract(conn)
            turn_referent()          # refuses before any request is built
        else:
            assert_legacy_allowed(conn)

        # Document mode: no minimum message count (each file = 1 "conversation").
        # Turn mode: none either (D-108); a conversation with no citable turn
        # builds no request, so short and prompt-only conversations cost nothing
        # unless they hold the subject's words.
        min_msgs = 1 if document_mode else 0 if turn_mode else MIN_MESSAGES_FOR_EXTRACTION

        # Get conversations — optionally skip already-extracted ones
        grown_ids = []
        if skip_extracted and turn_mode:
            # The SAME selector as the sequential turn path: new conversations, plus sessions
            # the importer re-marked because they GREW after their last extraction, minus
            # conversations with nothing citable. The legacy query below misses the grown ones
            # entirely (it keys on extraction_log alone), so a grown session was never picked up.
            sel = _turn_conversations_to_process(conn)
            rows = [{"id": r[0], "title": r[1], "message_count": r[3], "source": r[4],
                     "retry_only": bool(r[6]) and not r[5]}
                    for r in sel]
            grown_ids = [r[0] for r in sel if r[5]]
            n_retry = sum(1 for r in rows if r["retry_only"])
            if n_retry:
                print(f"  {n_retry} of them only to retry their recorded failed chunks")
            print(f"  Found {len(rows)} conversations to extract "
                  f"({len(grown_ids)} grown since their last extraction)")
        elif skip_extracted:
            rows = conn.execute("""
                SELECT c.id, c.title, c.message_count, c.source
                FROM conversations c
                LEFT JOIN extraction_log e ON c.id = e.conversation_id
                WHERE c.message_count >= ? AND e.conversation_id IS NULL
                ORDER BY c.created_at
            """, (min_msgs,)).fetchall()
            print(f"  Found {len(rows)} unextracted conversations (min {min_msgs} messages)")
        else:
            rows = conn.execute("""
                SELECT id, title, message_count, source
                FROM conversations
                WHERE message_count >= ?
                ORDER BY created_at
            """, (min_msgs,)).fetchall()
            print(f"  Found {len(rows)} conversations with >= {min_msgs} messages")

        # Build batch requests.
        # 2026-05-17: Multi-window per-conversation. Long abstracted texts get
        # split into N requests; chunk_map is the source of truth for
        # custom_id → parent conv_id lookup on the process side. Raw conv_id is
        # used as the base custom_id (UUIDs are valid; the prior md5 hash code
        # path had a latent bug where id_mapping was stored but never read back).
        requests = []
        chunk_map = {}  # custom_id → {parent_conv_id, chunk_idx, total_chunks, source}
        chunk_counts = {}  # how many chunks each conversation produced
        skipped = 0
        skipped_no_citable = 0
        missing_turns = []

        for i, row in enumerate(rows):
            conv_id = row["id"]
            conv_title = row["title"] or "Untitled"
            source = row["source"] or "chatgpt"

            if turn_mode:
                if isinstance(row, dict) and row.get("retry_only"):
                    built = _turn_retry_requests_for_conversation(
                        conn, conv_id, conv_title, source,
                        model=EXTRACTION_API_MODEL, temperature=BATCH_TEMPERATURE,
                        json_instruction=json_instruction, chunk_map=chunk_map)
                else:
                    built = _turn_requests_for_conversation(
                        conn, conv_id, conv_title, source, stamps=stamps,
                        model=EXTRACTION_API_MODEL, temperature=BATCH_TEMPERATURE,
                        json_instruction=json_instruction, chunk_map=chunk_map)
                if built is None:
                    missing_turns.append(conv_id)
                    continue
                conv_requests, n_skip = built
                skipped_no_citable += n_skip
                if not conv_requests:
                    skipped += 1
                    continue
                requests.extend(conv_requests)
                chunk_counts[conv_id] = len(conv_requests)
                continue

            # ---- LEGACY path (no turn contract): char windows over "Role: text" ----
            messages = _get_conversation_messages(conn, conv_id)
            if not messages:
                skipped += 1
                continue

            # Build abstracted text + caps based on mode and source type
            if document_mode:
                conv_text = _build_conv_text(messages)
                caps = _get_extraction_caps(len(messages), total_chars=len(conv_text))
                prompt_builder = build_document_extraction_prompt
                effective_source = source
            elif is_claude_code_source(source):
                conv_text = _abstract_project_conversation(messages)
                if len(conv_text.strip()) < 100:
                    skipped += 1
                    continue
                caps = _get_extraction_caps(len(messages), source=source)
                prompt_builder = build_identity_extraction_prompt
                effective_source = source
            else:
                conv_text = _build_conv_text(messages)
                caps = _get_extraction_caps(len(messages), total_chars=len(conv_text))
                prompt_builder = build_extraction_prompt
                effective_source = source

            conv_requests = _build_chunk_requests(
                conv_id=conv_id,
                conv_title=conv_title,
                abstracted_text=conv_text,
                source=effective_source,
                input_char_budget=caps["input_char_budget"],
                max_facts=caps["max_facts"],
                prompt_builder=prompt_builder,
                model=EXTRACTION_API_MODEL,
                max_tokens=BATCH_MAX_TOKENS,
                temperature=BATCH_TEMPERATURE,
                json_instruction=json_instruction,
                chunk_map=chunk_map,
            )
            requests.extend(conv_requests)
            chunk_counts[conv_id] = len(conv_requests)

            if (i + 1) % 100 == 0:
                print(f"  Built {i + 1}/{len(rows)} conversations "
                      f"({len(requests)} requests so far)...")

    if missing_turns:
        # Refuse BEFORE spending: a conversation with no turn rows never went
        # through the turn-contract importer, so the import is incomplete.
        raise TurnContractViolation(
            f"{len(missing_turns)} conversations have no rows in the turn table "
            f"(first: {missing_turns[0]}). Nothing was submitted.")

    chunked_convs = sum(1 for n in chunk_counts.values() if n > 1)
    print(f"\n  Total requests: {len(requests)}")
    print(f"  Conversations:  {len(chunk_counts)} ({chunked_convs} chunked into multiple windows)")
    print(f"  Skipped:        {skipped} (empty or too short)")
    if turn_mode:
        print(f"  Chunks skipped, no subject turn to cite: {skipped_no_citable}")
        prompt_chars = sum(len(r["params"]["messages"][0]["content"]) for r in requests)
        print(f"  Prompt size: {prompt_chars:,} chars (~{prompt_chars // 4:,} tokens at 4 chars/token, "
              f"a proxy; price from the pilot's measured usage, not this)")

    if not requests:
        print("ERROR: No conversations to process.")
        return

    # Deliberately no dollar figure: in-repo price constants go stale (this
    # function printed Haiku 3 rates for months). Price a run from current
    # published rates and the pilot's measured tokens.
    print(f"  Requests to submit: {len(requests)}")

    client = _get_anthropic_client()
    print(f"\nSubmitting batch to Anthropic API...")

    try:
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
    except Exception as e:
        print(f"ERROR: Batch submission failed: {e}")
        return

    # Save state. chunk_map is the authoritative custom_id → parent conv_id mapping.
    state = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(),
        "total_requests": len(requests),
        "conversation_ids": list(chunk_counts.keys()),
        "chunk_map": chunk_map,  # custom_id → {parent_conv_id, chunk_idx, total_chunks, source}
        "model": EXTRACTION_API_MODEL,
        "status": "submitted",
        "mode": "turn" if turn_mode else "legacy",
        # An incremental batch covers only part of the corpus, so the resetting --process
        # (which deletes every extracted fact and the whole extraction_log) must refuse it.
        "incremental": bool(skip_extracted),
        "grown_conversations": grown_ids,
    }
    if turn_mode:
        state["turn_contract_version"] = TURN_CONTRACT_VERSION
        state["stamps"] = {"general": stamps[False], "project": stamps[True]}
        state["settings"] = turn_run_settings()
    _save_batch_state(state)

    print(f"\n  Batch submitted successfully!")
    print(f"  Batch ID: {batch_id}")
    print(f"  Requests: {len(requests)}")
    print(f"\n  State saved to: {BATCH_STATE_FILE}")
    print(f"\n  Next: Check status with --status, process results with --process")
    print(f"  You can close this terminal and come back later.")


# ---------------------------------------------------------------------------
# Phase 2: STATUS
# ---------------------------------------------------------------------------

def run_status():
    """Check batch processing status."""
    state = _load_batch_state()
    if not state:
        print("No active batch found. Run --submit first.")
        return

    batch_id = state["batch_id"]
    print(f"\n  Batch Status")
    print(f"  {'='*50}")
    print(f"  Batch ID: {batch_id}")
    print(f"  Submitted: {state.get('created_at', 'unknown')}")
    print(f"  Total requests: {state.get('total_requests', '?')}")

    client = _get_anthropic_client()

    try:
        batch = client.messages.batches.retrieve(batch_id)
    except Exception as e:
        print(f"  ERROR: Could not retrieve batch: {e}")
        return

    # Update local state
    state["status"] = batch.processing_status
    _save_batch_state(state)

    counts = batch.request_counts
    print(f"\n  Status: {batch.processing_status}")
    print(f"  Succeeded:  {counts.succeeded}")
    print(f"  Errored:    {counts.errored}")
    print(f"  Canceled:   {counts.canceled}")
    print(f"  Expired:    {counts.expired}")
    print(f"  Processing: {counts.processing}")

    total = counts.succeeded + counts.errored + counts.canceled + counts.expired
    if state.get("total_requests"):
        pct = total / state["total_requests"] * 100
        print(f"\n  Progress: {total}/{state['total_requests']} ({pct:.1f}%)")

    if batch.processing_status == "ended":
        print(f"\n  Batch complete! Run --process to extract facts.")
    elif batch.processing_status == "in_progress":
        # Estimate time based on progress
        if total > 0:
            elapsed = (datetime.now() - datetime.fromisoformat(state["created_at"])).total_seconds()
            per_req = elapsed / total
            remaining = (state["total_requests"] - total) * per_req
            print(f"  Estimated time remaining: {remaining/60:.0f} minutes")


# ---------------------------------------------------------------------------
# Phase 3: PROCESS
# ---------------------------------------------------------------------------

def _ensure_extraction_chunks_done_table(conn):
    """Create the per-chunk completion-tracking table if missing.

    2026-05-17: Records that a specific custom_id has been processed under a
    specific batch_id. Resume uses this set instead of extraction_log (which
    is conv-level and would lose chunk granularity).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS extraction_chunks_done (
            custom_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            parent_conv_id TEXT NOT NULL,
            facts_extracted INTEGER NOT NULL,
            processed_at REAL NOT NULL,
            PRIMARY KEY (custom_id, batch_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_done_batch
        ON extraction_chunks_done (batch_id)
    """)


def _upsert_extraction_log(conn, parent_conv_id, facts_extracted, processed_at):
    """Upsert into extraction_log with sum semantics.

    A chunked conversation produces multiple results; this accumulates their
    facts_extracted into a single conv-level row instead of overwriting.
    The conversation_id column is the PK (INSERT OR REPLACE relied on it).
    """
    conn.execute("""
        INSERT INTO extraction_log (conversation_id, facts_extracted, processed_at)
        VALUES (?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
            facts_extracted = facts_extracted + excluded.facts_extracted,
            processed_at = excluded.processed_at
    """, (parent_conv_id, facts_extracted, processed_at))


def _download_results(client, batch_id, max_retries=10):
    """Fetch every batch result into memory, retrying a dropped stream.

    Download and processing are separate phases so that the gate never runs
    inside the connection-retry handler: a handler around the processing loop
    would catch a gate failure too."""
    for attempt in range(max_retries):
        try:
            return list(client.messages.batches.results(batch_id))
        except Exception as e:
            transient = ("peer closed connection" in str(e) or "RemoteProtocolError" in str(e)
                         or "incomplete chunked" in str(e))
            if transient and attempt < max_retries - 1:
                print(f"\n  Connection dropped while downloading results: {e}")
                print(f"  Retry {attempt + 1}/{max_retries} in 5 seconds...")
                time.sleep(5)
                continue
            raise
    return []


def _mark_chunk(conn, custom_id, batch_id, conv_id, n):
    conn.execute("""
        INSERT OR REPLACE INTO extraction_chunks_done
        (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
        VALUES (?, ?, ?, ?, ?)
    """, (custom_id, batch_id, conv_id, n, time.time()))


def _process_legacy_result(conn, result, custom_id, chunk_meta, batch_id, *, collection,
                           embed_model, corrections, source_map, counts):
    """One LEGACY batch result (no turn contract), unchanged in behaviour."""
    conv_id = chunk_meta["parent_conv_id"] if chunk_meta else custom_id

    if result.result.type == "errored":
        counts["errors"] += 1
        # Mark chunk as processed-with-error so resume doesn't retry it.
        # Don't pollute extraction_log sum with -1 (skip log).
        _mark_chunk(conn, custom_id, batch_id, conv_id, -1)
        conn.commit()
        return
    if result.result.type != "succeeded":
        counts["errors"] += 1
        return
    counts.setdefault("usage", []).append(_batch_usage(result, conv_id, custom_id))

    try:
        parsed = _parse_batch_message(result.result.message)
    except (json.JSONDecodeError, ExtractionResponseError, IndexError, AttributeError):
        counts["errors"] += 1
        _mark_chunk(conn, custom_id, batch_id, conv_id, -1)
        conn.commit()
        return

    if "facts" not in parsed:
        _upsert_extraction_log(conn, conv_id, 0, time.time())
        _mark_chunk(conn, custom_id, batch_id, conv_id, 0)
        conn.commit()
        counts["processed"] += 1
        return

    # Get message count for confidence computation
    msg_count_row = conn.execute(
        "SELECT message_count FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    message_count = msg_count_row["message_count"] if msg_count_row else 10

    # Determine identity-only mode. Prefer chunk_meta (set at submit
    # time) over source_map for accuracy in chunked path.
    conv_source = (chunk_meta or {}).get("source") or source_map.get(conv_id, "chatgpt")
    identity_only = is_claude_code_source(conv_source)

    valid_facts = validate_structured_response(
        parsed["facts"], message_count, identity_only=identity_only)
    scope = SCOPE_SOURCE_MAPPING.get(conv_source, DEFAULT_SCOPE)
    stamp = _legacy_stamp("identity" if identity_only else "general")

    fact_ids = []
    for fact_data in valid_facts:
        fact_text = fact_data["fact"]

        # D-021: Check against corrections
        if check_against_corrections(fact_text, corrections):
            continue

        # AUDN dedup against growing collection
        similar = find_similar_facts(fact_text, collection, embed_model)
        audn = make_audn_decision(fact_text, similar)

        if audn["action"] == "NOOP":
            counts["noops"] += 1
            continue

        supersedes_id = None
        if audn["action"] == "UPDATE" and similar:
            supersedes_id = similar[0].get("fact_id")
            fact_text = audn.get("updated_fact", fact_text)

        fact_id = store_fact(
            conn,
            fact_text=fact_text,
            category=fact_data["category"],
            confidence=fact_data["confidence"],
            conv_id=conv_id,
            audn_action=audn["action"],
            supersedes_id=supersedes_id,
            subject=fact_data["subject"],
            intent=fact_data["intent"],
            temporal=fact_data["temporal"],
            raw_llm_confidence=fact_data["raw_llm_confidence"],
            fact_class=fact_data["fact_class"],
            knowledge_tier=fact_data["knowledge_tier"],
            tiered_by=EXTRACTION_BACKEND,
            scope=scope,
            predicate=fact_data.get("predicate"),
            object_text=fact_data.get("object_text"),
            qualifier=fact_data.get("qualifier"),
            stamp=stamp,
        )
        fact_ids.append(fact_id)

        if collection and embed_model:
            try:
                embed_fact(fact_id, fact_text, fact_data["category"], collection, embed_model)
            except Exception:
                pass  # Non-fatal — can re-embed later

        counts["facts"] += 1

    # Link co-occurring facts (within this chunk)
    if len(fact_ids) > 1:
        link_facts(conn, fact_ids, conv_id)

    # Log per-chunk completion AND accumulate into per-conv extraction_log
    now = time.time()
    _mark_chunk(conn, custom_id, batch_id, conv_id, len(fact_ids))
    _upsert_extraction_log(conn, conv_id, len(fact_ids), now)
    conn.commit()
    counts["processed"] += 1
    if counts["processed"] % 50 == 0:
        print(f"    Processed {counts['processed']} chunks, {counts['facts']} facts stored...")


def _process_turn_conversation(conn, conv_id, items, batch_id, *, stamps, collection,
                               embed_model, corrections, record, counts, referent):
    """All batch results of ONE conversation under the turn contract.

    items: [(custom_id, chunk_meta, result)]. Same four phases as the
    sequential path: parse (failures counted), GATE (no handler above it),
    finalize with the density backstop over the conversation's accepted facts,
    then store in one transaction that rolls back on error."""
    parsed_chunks = []
    truncated = []          # (custom_id, meta) of chunks that stopped on max_tokens: re-chunked below
    failed_items = []       # (meta, reason): recorded as FAILED below, never marked done
    for custom_id, meta, result in items:
        if result.result.type != "succeeded":
            record.c["chunks_failed"] += 1
            failed_items.append((meta, result.result.type))
            continue
        record.usage_calls.append(_batch_usage(result, conv_id, custom_id, meta))
        try:
            parsed = _parse_batch_message(result.result.message)
        except ExtractionResponseError as e:
            if e.reason == "max_tokens":
                truncated.append((custom_id, meta))
                continue
            record.c["chunks_failed"] += 1
            record.response_failures[e.reason] = record.response_failures.get(e.reason, 0) + 1
            failed_items.append((meta, e.reason))
            continue
        except json.JSONDecodeError:
            record.c["chunks_failed"] += 1
            record.response_failures["json_decode"] = record.response_failures.get("json_decode", 0) + 1
            failed_items.append((meta, "json_decode"))
            continue
        facts = parsed.get("facts") if isinstance(parsed, dict) else None
        if not isinstance(facts, list):
            record.c["chunks_failed"] += 1
            failed_items.append((meta, "not_a_list"))
            continue
        parsed_chunks.append((custom_id, meta, facts))
        record.c["chunks_called"] += 1

    # Rebuild each chunk's citable set from the turn table (the state file
    # holds ids and offsets only), then gate. NO exception handler here.
    wanted = [row[0] for _c, meta, _f in parsed_chunks for row in meta["manifest"]["citable"]]
    texts = _tc.load_turn_texts(conn, wanted)
    gated = [(None, _tc.gate_facts(facts, _tc.chunk_from_manifest(meta["manifest"], texts),
                                   referent=referent))
             for _c, meta, facts in parsed_chunks]

    meta0 = items[0][1]
    project = bool(meta0.get("project"))
    plan = dict(meta0["plan"])
    source = meta0.get("source", "unknown")
    # Items built by _turn_retry_requests_for_conversation retry recorded failed chunks of a
    # conversation whose other chunks are stored: settle those rows, add to the logged count.
    retry_mode = any(m.get("retry_of") for _c, m, _r in items)
    done_ids = [c for c, _m, _f in parsed_chunks]
    failures, resolved = [], []

    def _row_of(meta):
        ro = meta.get("retry_of")
        return (ro["chunk_key"], ro["input_char_budget"], ro["turns_upto"]) if ro else None

    for _c, meta, _f in parsed_chunks:
        if _row_of(meta):
            resolved.append(_row_of(meta))

    if truncated or failed_items:
        turns = _tc.load_turns(conn, conv_id)
        row = conn.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        title = (row[0] if row else None) or "Untitled"
        rplan = turn_extraction_plan(turns, source)
        rplan["fact_count_mode"] = plan.get("fact_count_mode", "capped")
        rplan["per_chunk_cap"] = plan["per_chunk_cap"]

        def _plan_of(meta):
            ro = meta.get("retry_of")
            return dict(rplan, input_char_budget=ro["input_char_budget"]) if ro else rplan

        for meta, reason in failed_items:
            ro = meta.get("retry_of") or {}
            p = _plan_of(meta)
            failures.append(failed_chunk(conv_id, meta["manifest"]["body_voice"],
                                         p["input_char_budget"], ro.get("turns_upto", 0), p,
                                         "batch", reason))
        # A max_tokens stop is re-chunked at half the budget and retried once, now,
        # synchronously (sequential rates), exactly as the sequential path does.
        for custom_id, meta in truncated:
            m = meta["manifest"]
            p = _plan_of(meta)
            parts = rechunk_after_max_tokens(
                title, turns, source, failed_index=meta["chunk_idx"],
                body_ids=set(m["body_voice"]), citable_ids={row[0] for row in m["citable"]},
                plan=p, project_session=project, record=record, path="batch")
            gated.extend((r.chunk, _tc.gate_facts(r.raw_facts, r.chunk, referent=referent))
                         for r in parts if not r.failed)
            left = failures_of(parts, conv_id, p, "batch")
            failures.extend(left)
            if _row_of(meta):
                resolved.append(_row_of(meta))     # its parts replace the row
            if not left:
                done_ids.append(custom_id)
    facts = finalize_turn_facts(gated, meta0.get("n_turns", 0), plan,
                                project_session=project, record=record)

    source = meta0.get("source", "unknown")
    scope = SCOPE_SOURCE_MAPPING.get(source, DEFAULT_SCOPE)
    embedded = []
    try:
        stored = store_turn_facts(conn, conv_id, facts, collection, embed_model, scope=scope,
                                  stamp=stamps["project" if project else "general"],
                                  corrections=corrections, record=record, embedded=embedded)
        # Only chunks that produced a usable reply are marked done. A failed one is recorded
        # in extraction_chunks_failed instead, so --resume and the next run retry it.
        for custom_id in done_ids:
            _mark_chunk(conn, custom_id, batch_id, conv_id, stored)
        if retry_mode:
            upsert_log_sum(conn, conv_id, stored)
            write_failed_chunks(conn, conv_id, failures, replace_all=False, resolved=resolved,
                                batch_id=batch_id)
        else:
            conn.execute("INSERT OR REPLACE INTO extraction_log "
                         "(conversation_id, facts_extracted, processed_at) VALUES (?, ?, ?)",
                         (conv_id, stored, time.time()))
            if failures or failed_chunks_table_exists(conn):
                write_failed_chunks(conn, conv_id, failures, replace_all=True,
                                    batch_id=batch_id)
            mark_turn_conversation_extracted(conn, conv_id)
        conn.commit()
    except BaseException:
        conn.rollback()
        if embedded and collection is not None:
            collection.delete(ids=embedded)
        raise
    record.c["facts_stored"] += stored
    note_failed_chunks(record, failures)
    if retry_mode:
        record.c["chunks_retried"] += len(items)
        record.c["chunks_recovered"] += len(items) - len(failed_items) - sum(
            1 for c, _m in truncated if c not in done_ids)
    counts["facts"] += stored
    counts["errors"] += len(failures)
    counts["processed"] += len(items)


@_scoped_turn_mode
def run_process(resume=False):
    """Process completed batch results — reset old facts and store new ones."""
    state = _load_batch_state()
    if not state:
        print("No active batch found. Run --submit first.")
        return

    batch_id = state["batch_id"]
    chunk_map = state.get("chunk_map", {})
    turn_mode = state.get("mode") == "turn"
    _TURN_MODE_ACTIVE.set(turn_mode)
    client = _get_anthropic_client()

    # Verify batch is complete
    try:
        batch = client.messages.batches.retrieve(batch_id)
    except Exception as e:
        print(f"ERROR: Could not retrieve batch: {e}")
        return

    if batch.processing_status != "ended":
        print(f"Batch not yet complete. Status: {batch.processing_status}")
        print(f"Run --status for details.")
        return

    counts = batch.request_counts
    print("=" * 70)
    print(f"Batch Re-extraction — {'RESUME' if resume else 'PROCESS'} Phase"
          + (f" under {state.get('turn_contract_version')}" if turn_mode else ""))
    print("=" * 70)
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded}")
    print(f"  Errored: {counts.errored}")

    if counts.succeeded == 0:
        print("ERROR: No successful results to process.")
        raise SystemExit(1)

    # An INCREMENTAL batch (submitted with skip_extracted) holds results for part of the
    # corpus only. The reset below deletes every extracted fact and the whole extraction_log,
    # so running it here would destroy every conversation not in this batch. Refuse, before
    # anything is touched; --resume stores the results without the reset.
    if state.get("incremental") and not resume:
        raise SystemExit(
            "This batch was submitted incrementally (only new and grown conversations). "
            "--process would first delete every extracted fact and the extraction log, "
            "destroying the conversations this batch does not cover. Use --resume "
            "(`baselayer batch-extract --process --resume`), which stores the results "
            "without that reset.")

    # Mode guards BEFORE the reset below: a turn-contract batch refuses a
    # database holding any fact not stamped with its version (fresh corpus
    # directory is the operating assumption); a legacy batch refuses a
    # turn-contract corpus. Neither mode silently wipes the other's facts.
    with contextlib.closing(get_db()) as conn:
        if turn_mode:
            if state.get("turn_contract_version") != TURN_CONTRACT_VERSION:
                raise TurnContractViolation(
                    f"batch was built under {state.get('turn_contract_version')}, this code "
                    f"is {TURN_CONTRACT_VERSION}")
            assert_fresh_for_turn_contract(conn)
            referent = turn_referent()
        else:
            assert_legacy_allowed(conn)
            referent = None

    # Download every result first (retrying a dropped stream), THEN process
    # with no connection-retry handler around the gate. Downloaded BEFORE the
    # reset so a turn-mode result that cannot be gated refuses the run while
    # the prior corpus is still intact.
    print(f"\n  Downloading {counts.succeeded + counts.errored} results...")
    results = _download_results(client, batch_id)
    if turn_mode:
        for result in results:
            if result.custom_id not in chunk_map:
                raise TurnContractViolation(
                    f"result {result.custom_id} has no chunk_map entry; cannot gate it")

    # Build set of already-processed chunks (for resume).
    # 2026-05-17: Resume granularity is per-chunk (custom_id), not per-conv.
    # A multi-day session may have some chunks done and some pending.
    already_processed = set()
    if resume:
        print(f"\n--- Resuming from previous run ---")
        with contextlib.closing(get_db()) as conn:
            _ensure_extraction_chunks_done_table(conn)
            rows = conn.execute(
                "SELECT custom_id FROM extraction_chunks_done WHERE batch_id = ?",
                (batch_id,),
            ).fetchall()
            already_processed = {r[0] for r in rows}
            existing_facts = conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchone()[0]
        print(f"  Already processed: {len(already_processed)} chunks (this batch)")
        print(f"  Existing facts:    {existing_facts}")
        print(f"  Remaining chunks:  ~{counts.succeeded - len(already_processed)}")
    else:
        # --- Phase 3a: Reset existing extraction data ---
        print(f"\n--- Phase 1: Reset existing extraction data ---")

        with contextlib.closing(get_db()) as conn:
            _ensure_structured_columns(conn)
            _ensure_extraction_chunks_done_table(conn)

            with conn:
                # D-021: Protected reset — only clear extraction-sourced facts
                conn.execute("DELETE FROM extraction_log")
                conn.execute("DELETE FROM extraction_chunks_done")
                if failed_chunks_table_exists(conn):
                    conn.execute(f"DELETE FROM {FAILED_CHUNKS_TABLE}")
                deleted = conn.execute("""
                    DELETE FROM memory_facts
                    WHERE source = 'extraction' OR source IS NULL
                """).rowcount
                conn.execute("DELETE FROM fact_relationships")

            survived = conn.execute("""
                SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL
            """).fetchone()[0]

        print(f"  Removed {deleted} extracted facts.")
        print(f"  Protected: {survived} user-corrected facts survived.")

    # Get or create ChromaDB
    chroma_client = None
    if not resume:
        # Clear ChromaDB on fresh run
        try:
            import chromadb
            chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))
            try:
                chroma_client.delete_collection("memory_facts")
                print("  ChromaDB memory_facts collection cleared.")
            except Exception:
                print("  ChromaDB memory_facts collection was already empty.")
        except ImportError:
            print("  ChromaDB not available — skipping vector cleanup.")
    else:
        try:
            import chromadb
            chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        except ImportError:
            print("  ChromaDB not available — skipping vector operations.")

    # --- Phase 3b: Process batch results ---
    print(f"\n--- Phase 2: Process batch results ---")

    # Load embedding model (centralized singleton from api_client)
    print("  Loading embedding model...")
    try:
        from baselayer.api_client import get_embedding_model
        embed_model = get_embedding_model()
        if embed_model is None:
            print(f"  WARNING: Embedding model not available.")
            print(f"  Facts will be stored but not embedded. Run 'baselayer embed' after.")
    except Exception as e:
        print(f"  WARNING: Could not load embedding model: {e}")
        print(f"  Facts will be stored but not embedded. Run 'baselayer embed' after.")
        embed_model = None

    # Create fresh ChromaDB collection
    collection = None
    if chroma_client:
        try:
            collection = chroma_client.get_or_create_collection(
                "memory_facts",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            print(f"  WARNING: Could not create ChromaDB collection: {e}")

    if turn_mode and collection is not None:
        with contextlib.closing(get_db()) as conn:
            assert_fresh_for_turn_contract(conn, collection)

    # Load corrections (D-021)
    with contextlib.closing(get_db()) as conn:
        corrections = load_corrections(conn)
    print(f"  Loaded {len(corrections)} user corrections")

    # Build source map for scope derivation
    with contextlib.closing(get_db()) as conn:
        source_rows = conn.execute(
            "SELECT id, source FROM conversations"
        ).fetchall()
    source_map = {r["id"]: r["source"] for r in source_rows}

    tally = {"facts": 0, "errors": 0, "noops": 0, "processed": 0}
    record = None
    reset_usage()      # AUDN calls made while storing go through call_anthropic

    with contextlib.closing(get_db()) as conn:
        _ensure_structured_columns(conn)
        _ensure_extraction_chunks_done_table(conn)

        if not turn_mode:
            print(f"\n  Processing {len(results)} results (legacy, ungated)...")
            for result in results:
                custom_id = result.custom_id
                if custom_id in already_processed:
                    continue
                _process_legacy_result(conn, result, custom_id, chunk_map.get(custom_id),
                                       batch_id, collection=collection,
                                       embed_model=embed_model, corrections=corrections,
                                       source_map=source_map, counts=tally)
        else:
            stamps = state["stamps"]
            record = _tc.ExtractionRunRecord("turn-batch", state.get("settings", {}),
                                             stamp=stamps)
            record.notes.append(f"batch {batch_id}")
            record.settings["referent_names"] = len(referent.names)
            now_commit = _tc.git_commit_of(extract_facts_module_file())
            if now_commit != stamps["general"]["git_commit"]:
                msg = (f"code changed between submit ({stamps['general']['git_commit']}) and "
                       f"process ({now_commit}); facts carry the submit-time stamp")
                print(f"  WARNING: {msg}")
                record.notes.append(msg)
            by_conv = {}
            for result in results:
                meta = chunk_map.get(result.custom_id)
                if meta is None:
                    raise TurnContractViolation(
                        f"result {result.custom_id} has no chunk_map entry; cannot gate it")
                if result.custom_id in already_processed:
                    continue
                by_conv.setdefault(meta["parent_conv_id"], []).append(
                    (result.custom_id, meta, result))
            # --resume: a conversation whose failed chunks THIS batch recorded is not
            # reprocessed from its stored results (the same reply fails the same way). Its
            # recorded failed chunks are retried now, synchronously, alone.
            retry_convs = []
            if resume and failed_chunks_table_exists(conn):
                parents = {m["parent_conv_id"] for m in chunk_map.values()}
                retry_convs = sorted(
                    r[0] for r in conn.execute(
                        f"SELECT DISTINCT conversation_id FROM {FAILED_CHUNKS_TABLE} "
                        f"WHERE batch_id = ?", (batch_id,))
                    if r[0] in parents
                    # its failed chunks are themselves items of this batch: process those
                    and not any(m.get("retry_of") for _c, m, _r in by_conv.get(r[0], [])))
                if retry_convs:
                    print(f"\n  Retrying the failed chunks of {len(retry_convs)} "
                          f"conversation(s) synchronously...")
            print(f"\n  Processing {len(by_conv)} conversations under the turn contract...")
            reset_response_failures()     # the synchronous re-chunk calls count here
            completed = False
            try:
                for conv_id in retry_convs:
                    _tok = _CURRENT_CONVERSATION.set(conv_id)
                    try:
                        r = conn.execute("SELECT id, title, source FROM conversations "
                                         "WHERE id = ?", (conv_id,)).fetchone()
                        n, left = retry_failed_chunks(
                            {"id": r[0], "title": r[1], "source": r[2]}, conn, collection,
                            embed_model, stamps=turn_stamps(), record=record,
                            referent=referent, corrections=corrections, path="batch",
                            batch_id=batch_id)
                    finally:
                        _CURRENT_CONVERSATION.reset(_tok)
                    tally["facts"] += n
                    tally["errors"] += left
                    if not left:          # settled: the results it replaced count as done
                        for custom_id, _m, _r in by_conv.get(conv_id, []):
                            _mark_chunk(conn, custom_id, batch_id, conv_id, n)
                        conn.commit()
                for conv_id, items in by_conv.items():
                    if conv_id in retry_convs:
                        continue
                    items.sort(key=lambda x: x[1]["chunk_idx"])
                    _tok = _CURRENT_CONVERSATION.set(conv_id)
                    try:
                        _process_turn_conversation(conn, conv_id, items, batch_id,
                                                   stamps=stamps, collection=collection,
                                                   embed_model=embed_model,
                                                   corrections=corrections, record=record,
                                                   counts=tally, referent=referent)
                    finally:
                        _CURRENT_CONVERSATION.reset(_tok)
                completed = True
            finally:
                record.usage_calls.extend(usage_calls())   # the sequential AUDN calls
                for reason, n in response_failures().items():   # synchronous re-chunk calls
                    record.response_failures[reason] = record.response_failures.get(reason, 0) + n
                if not completed:
                    record.notes.append("run aborted by an exception; counts are partial")
                for line in record.summary_lines():
                    print(line)
                print(f"  run record: {record.write(conn)}")

        # Final commit
        conn.commit()

        # 2026-05-19: Tier facts by predicate. The sync extraction path tiers
        # inline; the batch path did not, leaving the corpus untiered until the
        # post-compose traceability step. That starved the author fact-floor
        # gate and pipeline-mode detection of tier signal. Tiering here closes
        # the gap. Idempotent — only touches untiered facts.
        id_tiered, ctx_tiered = tier_facts_by_predicate(conn)
        conn.commit()
        print(f"  Tiered facts: {id_tiered:,} -> identity, {ctx_tiered:,} -> contextual")

        # Run ANALYZE for query optimizer
        conn.execute("ANALYZE")

    # --- Summary ---
    print(f"\n{'='*70}")
    print(f"  Batch Processing Complete")
    print(f"{'='*70}")
    print(f"  Results processed:      {tally['processed']}")
    print(f"  Facts stored:           {tally['facts']}")
    print(f"  NOOP (duplicates):      {tally['noops'] if not turn_mode else record.audn.get('NOOP', 0)}")
    print(f"  Errors:                 {tally['errors']}")
    _all_usage = (record.usage_calls if record is not None
                  else tally.get("usage", []) + usage_calls())
    _totals = _tc.usage_totals(_all_usage)
    print(f"  {_tc.usage_line(_totals)}")
    print(f"    of which batch (billed at the batch rate): {_totals['batch']['calls']:,} calls, "
          f"{_totals['batch']['input_tokens']:,} input, {_totals['batch']['output_tokens']:,} output")

    # Update batch state
    state["status"] = "completed"
    state["completed_at"] = datetime.now().isoformat()
    state["facts_stored"] = tally["facts"]
    state["errors"] = tally["errors"]
    state["api_usage_totals"] = _totals
    if record is not None:
        state["run_record"] = record.run_id
    _save_batch_state(state)

    if turn_mode and tally["errors"]:
        print(f"\n  ERROR: {tally['errors']} chunk(s) failed and were not stored. They are "
              f"recorded in {FAILED_CHUNKS_TABLE} (not marked done); `--process --resume` "
              f"or the next incremental submit retries only them. See the run record.")
        raise SystemExit(1)

    print(f"\n  Next steps (simplified 4-step pipeline):")
    print(f"    1. baselayer checkpoint extraction    # Verify extraction quality")
    print(f"    2. baselayer author                   # Generate the three specification layers (ANCHORS/CORE/PREDICTIONS)")
    print(f"    3. baselayer compose                  # Compose unified brief")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch re-extraction via Anthropic Message Batches API (50% cost)"
    )
    parser.add_argument("--submit", action="store_true",
                        help="Build prompts and submit batch to Anthropic API")
    parser.add_argument("--status", action="store_true",
                        help="Check batch processing status")
    parser.add_argument("--process", action="store_true",
                        help="Process completed batch results into database")
    parser.add_argument("--resume", action="store_true",
                        help="Resume processing after connection drop (skip reset, skip already-processed)")
    parser.add_argument("--turn-contract", action="store_true",
                        help="With --submit: build turn-contract requests (same as "
                             "BASELAYER_TURN_CONTRACT=1). --process follows the mode the "
                             "batch was submitted in.")
    parser.add_argument("--incremental", action="store_true",
                        help="With --submit: only conversations not yet extracted, plus "
                             "sessions that grew since their extraction (turn mode). "
                             "Process it with --resume; --process refuses it.")

    args = parser.parse_args()

    if args.submit:
        run_submit(skip_extracted=args.incremental,
                   turn_contract=True if args.turn_contract else None)
    elif args.status:
        run_status()
    elif args.process:
        run_process(resume=False)
    elif args.resume:
        run_process(resume=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
