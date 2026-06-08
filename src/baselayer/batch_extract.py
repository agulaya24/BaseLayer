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
    SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE,
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
)

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
        overlap = 0 if source == "claude_code" else 500

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

def run_submit(document_mode=False, skip_extracted=False):
    """Build prompts for all conversations and submit as a batch.

    Args:
        document_mode: Use document extraction prompt (for subject corpora).
        skip_extracted: Only process conversations not yet in extraction_log.
    """
    mode_label = "Document Corpus" if document_mode else "Re-extraction"
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

    client = _get_anthropic_client()

    # JSON schema instruction (same as call_anthropic in extract_facts.py)
    json_instruction = "Respond with ONLY valid JSON matching this schema. No explanation, no markdown fences.\n"
    json_instruction += f"Schema: {json.dumps(EXTRACT_SCHEMA, indent=2)}\n\n"

    print("\nLoading conversations from database...")

    with contextlib.closing(get_db()) as conn:
        # Document mode: no minimum message count (each file = 1 "conversation")
        min_msgs = 1 if document_mode else MIN_MESSAGES_FOR_EXTRACTION

        # Get conversations — optionally skip already-extracted ones
        if skip_extracted:
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

        for i, row in enumerate(rows):
            conv_id = row["id"]
            conv_title = row["title"] or "Untitled"
            source = row["source"] or "chatgpt"
            message_count = row["message_count"] or 0

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
            elif source == "claude_code":
                conv_text = _abstract_project_conversation(messages)
                if len(conv_text.strip()) < 100:
                    skipped += 1
                    continue
                caps = _get_extraction_caps(len(messages), source="claude_code")
                prompt_builder = build_identity_extraction_prompt
                effective_source = "claude_code"
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

    chunked_convs = sum(1 for n in chunk_counts.values() if n > 1)
    print(f"\n  Total requests: {len(requests)}")
    print(f"  Conversations:  {len(chunk_counts)} ({chunked_convs} chunked into multiple windows)")
    print(f"  Skipped:        {skipped} (empty or too short)")

    if not requests:
        print("ERROR: No conversations to process.")
        return

    # Estimate cost (Haiku Batch: $0.40/MTok input, $2.00/MTok output)
    # Rough estimate: ~2000 tokens input + ~500 tokens output per conversation
    est_input = len(requests) * 2000
    est_output = len(requests) * 500
    est_cost = (est_input * 0.40 + est_output * 2.00) / 1_000_000
    print(f"  Estimated cost: ${est_cost:.2f} (Haiku Batch pricing)")

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
    }
    _save_batch_state(state)

    print(f"\n  Batch submitted successfully!")
    print(f"  Batch ID: {batch_id}")
    print(f"  Requests: {len(requests)}")
    print(f"  Estimated cost: ${est_cost:.2f}")
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


def run_process(resume=False):
    """Process completed batch results — reset old facts and store new ones."""
    state = _load_batch_state()
    if not state:
        print("No active batch found. Run --submit first.")
        return

    batch_id = state["batch_id"]
    chunk_map = state.get("chunk_map", {})
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
    print(f"Batch Re-extraction — {'RESUME' if resume else 'PROCESS'} Phase")
    print("=" * 70)
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded}")
    print(f"  Errored: {counts.errored}")

    if counts.succeeded == 0:
        print("ERROR: No successful results to process.")
        return

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

    # Stream and process results
    total_facts = 0
    total_errors = 0
    total_noops = 0
    processed_convos = 0

    print(f"\n  Processing {counts.succeeded} conversation results...")

    MAX_RETRIES = 10

    with contextlib.closing(get_db()) as conn:
        _ensure_structured_columns(conn)
        _ensure_extraction_chunks_done_table(conn)

        for attempt in range(MAX_RETRIES):
            try:
                # On retry, refresh the set of already-processed chunks (this batch)
                if attempt > 0:
                    rows = conn.execute(
                        "SELECT custom_id FROM extraction_chunks_done WHERE batch_id = ?",
                        (batch_id,),
                    ).fetchall()
                    already_processed = {r[0] for r in rows}
                    print(f"\n  Retry {attempt}/{MAX_RETRIES} — "
                          f"{len(already_processed)} chunks already processed, resuming...")

                for result in client.messages.batches.results(batch_id):
                    custom_id = result.custom_id

                    # Skip already-processed chunks
                    if custom_id in already_processed:
                        continue

                    # Resolve parent conv_id via chunk_map (authoritative).
                    # Fallback: treat custom_id as conv_id for legacy single-chunk runs.
                    chunk_meta = chunk_map.get(custom_id)
                    if chunk_meta:
                        conv_id = chunk_meta["parent_conv_id"]
                    else:
                        conv_id = custom_id

                    if result.result.type == "errored":
                        total_errors += 1
                        # Mark chunk as processed-with-error so resume doesn't retry it.
                        # Don't pollute extraction_log sum with -1 (skip log).
                        conn.execute("""
                            INSERT OR REPLACE INTO extraction_chunks_done
                            (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
                            VALUES (?, ?, ?, -1, ?)
                        """, (custom_id, batch_id, conv_id, time.time()))
                        conn.commit()
                        continue

                    if result.result.type != "succeeded":
                        total_errors += 1
                        continue

                    # Parse response
                    try:
                        message = result.result.message
                        raw_text = message.content[0].text.strip()

                        # Strip markdown fences if present
                        if raw_text.startswith("```"):
                            raw_text = raw_text.split("```")[1]
                            if raw_text.startswith("json"):
                                raw_text = raw_text[4:]
                            raw_text = raw_text.strip()

                        parsed = json.loads(raw_text)
                    except (json.JSONDecodeError, IndexError, AttributeError) as e:
                        total_errors += 1
                        conn.execute("""
                            INSERT OR REPLACE INTO extraction_chunks_done
                            (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
                            VALUES (?, ?, ?, -1, ?)
                        """, (custom_id, batch_id, conv_id, time.time()))
                        conn.commit()
                        continue

                    if "facts" not in parsed:
                        _upsert_extraction_log(conn, conv_id, 0, time.time())
                        conn.execute("""
                            INSERT OR REPLACE INTO extraction_chunks_done
                            (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
                            VALUES (?, ?, ?, 0, ?)
                        """, (custom_id, batch_id, conv_id, time.time()))
                        conn.commit()
                        processed_convos += 1
                        continue

                    # Get message count for confidence computation
                    msg_count_row = conn.execute(
                        "SELECT message_count FROM conversations WHERE id = ?",
                        (conv_id,)
                    ).fetchone()
                    message_count = msg_count_row["message_count"] if msg_count_row else 10

                    # Determine identity-only mode. Prefer chunk_meta (set at submit
                    # time) over source_map for accuracy in chunked path.
                    conv_source = (chunk_meta or {}).get("source") or source_map.get(conv_id, "chatgpt")
                    identity_only = (conv_source == "claude_code")

                    # Validate and normalize
                    valid_facts = validate_structured_response(
                        parsed["facts"], message_count, identity_only=identity_only
                    )

                    # Derive scope
                    scope = SCOPE_SOURCE_MAPPING.get(conv_source, DEFAULT_SCOPE)

                    # Store facts
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
                            total_noops += 1
                            continue

                        supersedes_id = None
                        if audn["action"] == "UPDATE" and similar:
                            supersedes_id = similar[0].get("fact_id")
                            fact_text = audn.get("updated_fact", fact_text)

                        # Store
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
                        )

                        fact_ids.append(fact_id)

                        # Embed
                        if collection and embed_model:
                            try:
                                embed_fact(fact_id, fact_text, fact_data["category"],
                                           collection, embed_model)
                            except Exception:
                                pass  # Non-fatal — can re-embed later

                        total_facts += 1

                    # Link co-occurring facts (within this chunk)
                    if len(fact_ids) > 1:
                        link_facts(conn, fact_ids, conv_id)

                    # Log per-chunk completion AND accumulate into per-conv extraction_log
                    now = time.time()
                    conn.execute("""
                        INSERT OR REPLACE INTO extraction_chunks_done
                        (custom_id, batch_id, parent_conv_id, facts_extracted, processed_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (custom_id, batch_id, conv_id, len(fact_ids), now))
                    _upsert_extraction_log(conn, conv_id, len(fact_ids), now)

                    conn.commit()
                    processed_convos += 1

                    if processed_convos % 50 == 0:
                        print(f"    Processed {processed_convos} chunks, {total_facts} facts stored...")

                # If we get here, streaming completed successfully
                break

            except Exception as e:
                if "peer closed connection" in str(e) or "RemoteProtocolError" in str(e) or "incomplete chunked" in str(e):
                    print(f"\n  Connection dropped: {e}")
                    print(f"  Progress so far: {processed_convos} conversations, {total_facts} facts")
                    if attempt < MAX_RETRIES - 1:
                        print(f"  Reconnecting in 5 seconds...")
                        time.sleep(5)
                        continue
                    else:
                        print(f"  Max retries reached.")
                        raise
                else:
                    raise

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
    print(f"  Conversations processed: {processed_convos}")
    print(f"  Facts stored:           {total_facts}")
    print(f"  NOOP (duplicates):      {total_noops}")
    print(f"  Errors:                 {total_errors}")

    # Update batch state
    state["status"] = "completed"
    state["completed_at"] = datetime.now().isoformat()
    state["facts_stored"] = total_facts
    state["errors"] = total_errors
    _save_batch_state(state)

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

    args = parser.parse_args()

    if args.submit:
        run_submit()
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
