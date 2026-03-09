"""
Batch Pipeline Runner — Submit extraction via Anthropic Batch API (50% cost reduction).

For fresh corpora (Buffett, Marks, etc.), submits all extraction prompts as a single batch,
then processes results through the standard AUDN pipeline when complete.

Usage:
    python batch_pipeline.py --submit <MEMORY_SYSTEM_ROOT>  [--document-mode] [--subject NAME]
    python batch_pipeline.py --status <MEMORY_SYSTEM_ROOT>
    python batch_pipeline.py --process <MEMORY_SYSTEM_ROOT> [--document-mode] [--subject NAME]

The MEMORY_SYSTEM_ROOT is the subject's data directory (e.g., buffett_memory/).

Three-phase workflow:
  1. SUBMIT: Build prompts for unextracted conversations, submit batch
  2. STATUS: Poll batch progress (can close terminal and come back)
  3. PROCESS: Retrieve results, run AUDN pipeline, store facts + embeddings
"""

import contextlib
import re
import sys
import json
import time
import os
import argparse
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))


def _setup_env(root_path):
    """Set MEMORY_SYSTEM_ROOT and reload config."""
    os.environ["MEMORY_SYSTEM_ROOT"] = str(root_path)
    # Force config reload
    import importlib
    import config
    importlib.reload(config)
    return config


def _get_batch_state_file(config):
    return config.PROJECT_ROOT / "data" / "database" / "batch_state.json"


def _load_batch_state(state_file):
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return None


def _save_batch_state(state_file, state):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 1: SUBMIT
# ---------------------------------------------------------------------------

def run_submit(root_path, document_mode=False, subject=None):
    """Build extraction prompts for unextracted conversations and submit batch."""
    cfg = _setup_env(root_path)
    from config import DATABASE_FILE, PROJECT_ROOT, EXTRACTION_API_MODEL, get_db
    from extract_facts import (
        EXTRACT_SCHEMA, build_extraction_prompt, build_document_extraction_prompt,
        _abstract_project_conversation, build_identity_extraction_prompt,
    )
    from batch_extract import _build_conv_text
    from api_client import get_anthropic_client

    state_file = _get_batch_state_file(cfg)
    existing = _load_batch_state(state_file)
    if existing and existing.get("status") not in ("completed", "failed", "expired", "ended"):
        print(f"ERROR: Active batch already exists (ID: {existing.get('batch_id')})")
        print(f"  Use --status to check progress, or delete {state_file} to start fresh.")
        return

    print("=" * 60)
    print("Batch Extraction — SUBMIT")
    print("=" * 60)

    client = get_anthropic_client()

    json_instruction = "Respond with ONLY valid JSON matching this schema. No explanation, no markdown fences.\n"
    json_instruction += f"Schema: {json.dumps(EXTRACT_SCHEMA, indent=2)}\n\n"

    with contextlib.closing(get_db()) as conn:
        # Find conversations NOT yet extracted
        rows = conn.execute("""
            SELECT c.id, c.title, c.message_count, c.source
            FROM conversations c
            LEFT JOIN extraction_log e ON c.id = e.conversation_id
            WHERE e.conversation_id IS NULL
            ORDER BY c.created_at
        """).fetchall()

        print(f"  Unextracted conversations: {len(rows)}")

        if not rows:
            print("  Nothing to extract. All conversations already processed.")
            return

        requests = []
        id_map = {}  # safe_id -> real conv_id
        skipped = 0

        for i, row in enumerate(rows):
            conv_id = row["id"]
            conv_title = row["title"] or "Untitled"
            source = row["source"] or "text_file"

            # Get messages
            msg_rows = conn.execute("""
                SELECT role, content_text as text
                FROM messages WHERE conversation_id = ?
                ORDER BY created_at
            """, (conv_id,)).fetchall()

            messages = [{"role": r["role"], "text": r["text"] or ""} for r in msg_rows]
            if not messages:
                skipped += 1
                continue

            # Build prompt based on mode
            if document_mode:
                conv_text = "\n\n".join(m["text"] for m in messages if m["text"])
                if len(conv_text.strip()) < 100:
                    skipped += 1
                    continue
                prompt = build_document_extraction_prompt(conv_title, conv_text)
            elif source == "claude_code":
                conv_text = _abstract_project_conversation(messages)
                if len(conv_text.strip()) < 100:
                    skipped += 1
                    continue
                prompt = build_identity_extraction_prompt(conv_title, conv_text)
            else:
                conv_text = _build_conv_text(messages)
                if len(conv_text.strip()) < 100:
                    skipped += 1
                    continue
                prompt = build_extraction_prompt(conv_title, conv_text)

            # Sanitize custom_id for Batch API (alphanumeric, _, - only, max 64 chars)
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', conv_id)[:64]
            id_map[safe_id] = conv_id

            requests.append({
                "custom_id": safe_id,
                "params": {
                    "model": EXTRACTION_API_MODEL,
                    "max_tokens": 2000,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "user", "content": json_instruction + prompt}
                    ],
                },
            })

            if (i + 1) % 50 == 0:
                print(f"  Built {i + 1}/{len(rows)} prompts...")

    print(f"\n  Total requests: {len(requests)}")
    print(f"  Skipped: {skipped}")

    if not requests:
        print("ERROR: No valid conversations to process.")
        return

    # Cost estimate (Haiku Batch: $0.40/MTok input, $2.00/MTok output)
    est_input = len(requests) * 3000  # document mode prompts are larger
    est_output = len(requests) * 600
    est_cost = (est_input * 0.40 + est_output * 2.00) / 1_000_000
    print(f"  Estimated cost: ${est_cost:.2f} (Haiku Batch, 50% off sync)")

    print(f"\n  Submitting batch...")
    try:
        batch = client.messages.batches.create(requests=requests)
    except Exception as e:
        print(f"ERROR: Batch submission failed: {e}")
        return

    state = {
        "batch_id": batch.id,
        "created_at": datetime.now().isoformat(),
        "total_requests": len(requests),
        "conversation_ids": [r["custom_id"] for r in requests],
        "id_map": id_map,  # safe_id -> real conv_id
        "model": EXTRACTION_API_MODEL,
        "status": "submitted",
        "document_mode": document_mode,
        "subject": subject,
        "root_path": str(root_path),
    }
    _save_batch_state(state_file, state)

    print(f"\n  Batch submitted!")
    print(f"  Batch ID: {batch.id}")
    print(f"  Requests: {len(requests)}")
    print(f"  Cost estimate: ${est_cost:.2f}")
    print(f"\n  Next: --status to check, --process when complete.")


# ---------------------------------------------------------------------------
# Phase 2: STATUS
# ---------------------------------------------------------------------------

def run_status(root_path):
    """Check batch processing status."""
    cfg = _setup_env(root_path)
    from api_client import get_anthropic_client

    state_file = _get_batch_state_file(cfg)
    state = _load_batch_state(state_file)
    if not state:
        print("No active batch. Run --submit first.")
        return

    client = get_anthropic_client()
    batch_id = state["batch_id"]

    try:
        batch = client.messages.batches.retrieve(batch_id)
    except Exception as e:
        print(f"ERROR: {e}")
        return

    state["status"] = batch.processing_status
    _save_batch_state(state_file, state)

    counts = batch.request_counts
    print(f"\n  Batch Status: {batch.processing_status}")
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded} / Errored: {counts.errored} / Processing: {counts.processing}")

    total_done = counts.succeeded + counts.errored + counts.canceled + counts.expired
    if state.get("total_requests"):
        pct = total_done / state["total_requests"] * 100
        print(f"  Progress: {total_done}/{state['total_requests']} ({pct:.1f}%)")

    if batch.processing_status == "ended":
        print(f"\n  Batch complete! Run --process to extract and store facts.")


# ---------------------------------------------------------------------------
# Phase 3: PROCESS
# ---------------------------------------------------------------------------

def run_process(root_path, document_mode=False, subject=None):
    """Process completed batch results through AUDN pipeline."""
    cfg = _setup_env(root_path)
    from config import DATABASE_FILE, VECTORS_DIR, EXTRACTION_BACKEND, SCOPE_SOURCE_MAPPING, DEFAULT_SCOPE, get_db
    from extract_facts import (
        validate_structured_response, store_fact, embed_fact, link_facts,
        load_corrections, check_against_corrections, _ensure_structured_columns,
        find_similar_facts, make_audn_decision,
    )
    from api_client import get_anthropic_client, get_embedding_model

    state_file = _get_batch_state_file(cfg)
    state = _load_batch_state(state_file)
    if not state:
        print("No active batch. Run --submit first.")
        return

    # Use stored settings if available
    document_mode = document_mode or state.get("document_mode", False)
    subject = subject or state.get("subject")

    client = get_anthropic_client()
    batch_id = state["batch_id"]

    try:
        batch = client.messages.batches.retrieve(batch_id)
    except Exception as e:
        print(f"ERROR: {e}")
        return

    if batch.processing_status != "ended":
        print(f"Batch not complete. Status: {batch.processing_status}")
        return

    counts = batch.request_counts
    print("=" * 60)
    print("Batch Extraction — PROCESS")
    print("=" * 60)
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded} / Errored: {counts.errored}")
    print(f"  Document mode: {document_mode}")
    if subject:
        print(f"  Subject: {subject}")

    # Load embedding model
    print("  Loading embedding model...")
    try:
        embed_model = get_embedding_model()
    except Exception:
        embed_model = None
        print("  WARNING: Embedding model not available. Run 'baselayer embed' after.")

    # Get or create ChromaDB collection
    collection = None
    try:
        import chromadb
        chroma_client = chromadb.PersistentClient(path=str(VECTORS_DIR))
        collection = chroma_client.get_or_create_collection(
            "memory_facts", metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        print(f"  WARNING: ChromaDB not available: {e}")

    # Build source map
    with contextlib.closing(get_db()) as conn:
        source_rows = conn.execute("SELECT id, source FROM conversations").fetchall()
    source_map = {r["id"]: r["source"] for r in source_rows}

    # Check what's already processed (for resume)
    with contextlib.closing(get_db()) as conn:
        already_rows = conn.execute("SELECT conversation_id FROM extraction_log").fetchall()
    already_processed = {r[0] for r in already_rows}
    print(f"  Already processed: {len(already_processed)} conversations")

    # Load corrections
    with contextlib.closing(get_db()) as conn:
        corrections = load_corrections(conn)

    # Load ID mapping (safe_id -> real conv_id)
    id_map = state.get("id_map", {})

    # Process results
    total_facts = 0
    total_errors = 0
    total_noops = 0
    processed = 0

    print(f"\n  Processing batch results...")

    # Retry logic for streaming results (httpx connection drops)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            results_iter = list(client.messages.batches.results(batch_id))
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"  Retrying in 5s...")
                time.sleep(5)
            else:
                print(f"  ERROR: Failed to retrieve batch results after {max_retries} attempts: {e}")
                return

    with contextlib.closing(get_db()) as conn:
        _ensure_structured_columns(conn)

        for result in results_iter:
            safe_id = result.custom_id
            conv_id = id_map.get(safe_id, safe_id)  # fallback to safe_id if no mapping

            if conv_id in already_processed:
                continue

            if result.result.type != "succeeded":
                total_errors += 1
                conn.execute("""
                    INSERT OR REPLACE INTO extraction_log
                    (conversation_id, facts_extracted, processed_at)
                    VALUES (?, -1, ?)
                """, (conv_id, time.time()))
                conn.commit()
                continue

            # Parse response
            try:
                raw_text = result.result.message.content[0].text.strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("```")[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:]
                    raw_text = raw_text.strip()
                parsed = json.loads(raw_text)
            except (json.JSONDecodeError, IndexError, AttributeError):
                total_errors += 1
                conn.execute("""
                    INSERT OR REPLACE INTO extraction_log
                    (conversation_id, facts_extracted, processed_at)
                    VALUES (?, -1, ?)
                """, (conv_id, time.time()))
                conn.commit()
                continue

            if "facts" not in parsed:
                conn.execute("""
                    INSERT OR REPLACE INTO extraction_log
                    (conversation_id, facts_extracted, processed_at)
                    VALUES (?, 0, ?)
                """, (conv_id, time.time()))
                conn.commit()
                continue

            # Validate all facts at once (signature: raw_facts_list, message_count)
            msg_count = conn.execute(
                "SELECT message_count FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            msg_count = msg_count[0] if msg_count else 1

            validated_facts = validate_structured_response(parsed["facts"], msg_count)

            # Process each validated fact through AUDN
            facts_stored = 0
            fact_ids = []
            source = source_map.get(conv_id, "text_file")
            scope = SCOPE_SOURCE_MAPPING.get(source, DEFAULT_SCOPE)

            for fact_data in validated_facts:
                fact_text = fact_data["fact"]

                # Check corrections
                if corrections and check_against_corrections(fact_text, corrections):
                    continue

                # Find similar facts for AUDN
                similar = find_similar_facts(
                    fact_text, collection, embed_model
                ) if embed_model and collection else []

                # AUDN decision
                audn = make_audn_decision(fact_text, similar)

                if audn["action"] == "NOOP":
                    total_noops += 1
                    continue

                supersedes_id = None
                if audn["action"] == "UPDATE" and similar:
                    supersedes_id = similar[0].get("fact_id")
                    fact_text = audn.get("updated_fact", fact_text)

                # Store fact
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
                if fact_id:
                    fact_ids.append(fact_id)
                    facts_stored += 1
                    total_facts += 1

                    # Embed
                    if embed_model and collection:
                        try:
                            embed_fact(fact_id, fact_text, fact_data["category"],
                                       collection, embed_model)
                        except Exception:
                            pass  # Non-fatal

            # Link co-occurring facts
            if len(fact_ids) > 1:
                link_facts(conn, fact_ids, conv_id)

            # Log extraction
            conn.execute("""
                INSERT OR REPLACE INTO extraction_log
                (conversation_id, facts_extracted, processed_at)
                VALUES (?, ?, ?)
            """, (conv_id, facts_stored, time.time()))
            conn.commit()

            processed += 1
            if processed % 10 == 0:
                print(f"    {processed} conversations processed, {total_facts} facts stored...")

    print(f"\n  Done!")
    print(f"  Processed: {processed} conversations")
    print(f"  Facts stored: {total_facts}")
    print(f"  NOOPs (duplicates): {total_noops}")
    print(f"  Errors: {total_errors}")

    # Update state
    state["status"] = "completed"
    state["facts_stored"] = total_facts
    state["processed_at"] = datetime.now().isoformat()
    _save_batch_state(state_file, state)

    print(f"\n  Next steps:")
    print(f"    baselayer score    (score facts)")
    print(f"    baselayer classify (classify facts)")
    print(f"    baselayer tier     (tier classification)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch pipeline extraction")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--process", action="store_true")
    parser.add_argument("root", help="MEMORY_SYSTEM_ROOT path")
    parser.add_argument("--document-mode", action="store_true")
    parser.add_argument("--subject", type=str, default=None)

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.submit:
        run_submit(root, document_mode=args.document_mode, subject=args.subject)
    elif args.status:
        run_status(root)
    elif args.process:
        run_process(root, document_mode=args.document_mode, subject=args.subject)
    else:
        print("Specify --submit, --status, or --process")
