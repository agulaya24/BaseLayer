"""
Batch Tier Reclassification via Anthropic Message Batches API (50% cost reduction).

Promotes facts from context→situational→identity using the same prompts as
reclassify_tiers.py, but via Batch API.

Usage:
    python batch_tier.py --submit [root] [--source-tier context] [--subject NAME]
    python batch_tier.py --status [root]
    python batch_tier.py --process [root]

Three-phase workflow — can close terminal between phases.
"""

import contextlib
import json
import sys
import os
import re
import argparse
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))


def _setup_env(root_path=None):
    """Set MEMORY_SYSTEM_ROOT if provided and reload config."""
    if root_path:
        os.environ["MEMORY_SYSTEM_ROOT"] = str(root_path)
    import importlib
    import config
    importlib.reload(config)
    return config


def _get_state_file(cfg):
    return cfg.PROJECT_ROOT / "data" / "database" / "batch_tier_state.json"


def _load_state(state_file):
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return None


def _save_state(state_file, state):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 1: SUBMIT
# ---------------------------------------------------------------------------

TIER_BATCH_SIZE = 10  # Facts per API request (same as sync RECLASSIFY_BATCH_SIZE)

def run_submit(root_path=None, source_tier="context", subject=None):
    """Build tier promotion prompts and submit batch."""
    cfg = _setup_env(root_path)
    from config import get_db, RECLASSIFY_MODEL
    from reclassify_tiers import (
        get_candidates, apply_promotion_guards, build_prompt,
    )
    from api_client import get_anthropic_client

    state_file = _get_state_file(cfg)
    existing = _load_state(state_file)
    if existing and existing.get("status") not in ("completed", "failed", "expired", "ended"):
        print(f"ERROR: Active batch exists (ID: {existing.get('batch_id')})")
        print(f"  Use --status to check, or delete {state_file} to start fresh.")
        return

    print("=" * 60)
    print("Batch Tier Reclassification — SUBMIT")
    print("=" * 60)

    # Auto-initialize untiered facts to context
    with contextlib.closing(get_db()) as conn:
        untiered_count = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE knowledge_tier = 'untiered' AND superseded_by IS NULL"
        ).fetchone()[0]
        if untiered_count > 0:
            conn.execute(
                "UPDATE memory_facts SET knowledge_tier = 'context' WHERE knowledge_tier = 'untiered' AND superseded_by IS NULL"
            )
            conn.commit()
            print(f"  Initialized {untiered_count} untiered facts to 'context' tier.")

    # Get candidates
    raw_candidates = get_candidates(source_tier, "all", "promote", primary_subject=subject)
    candidates, skipped = apply_promotion_guards(raw_candidates, source_tier, "promote")

    print(f"  Raw candidates: {len(raw_candidates)}")
    if skipped:
        skip_reasons = {}
        for _, reason in skipped:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        print(f"  Pre-filtered: {len(skipped)} skipped ({skip_reasons})")
    print(f"  Eligible candidates: {len(candidates)}")

    if not candidates:
        print("  Nothing to tier.")
        return

    client = get_anthropic_client()
    requests = []
    batch_map = {}  # custom_id -> list of (fact_id, old_tier)

    for batch_idx in range(0, len(candidates), TIER_BATCH_SIZE):
        batch = candidates[batch_idx:batch_idx + TIER_BATCH_SIZE]
        prompt = build_prompt(batch, source_tier, "promote")
        custom_id = f"tier_batch_{batch_idx}"

        # Store fact IDs and current tiers for result processing
        batch_map[custom_id] = [(f[0], f[4]) for f in batch]  # (fact_id, knowledge_tier)

        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": RECLASSIFY_MODEL,
                "max_tokens": 20 * len(batch) + 50,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
        })

    print(f"  Total requests: {len(requests)} (batches of {TIER_BATCH_SIZE})")

    # Cost estimate (Sonnet Batch: $1.50/MTok input, $7.50/MTok output)
    est_input = len(candidates) * 200  # ~200 tokens per fact in prompt
    est_output = len(candidates) * 5   # ~5 tokens per tier label
    est_cost = (est_input * 1.50 + est_output * 7.50) / 1_000_000
    print(f"  Estimated cost: ${est_cost:.3f} (Sonnet Batch, 50% off sync)")

    print(f"\n  Submitting batch...")
    try:
        batch_resp = client.messages.batches.create(requests=requests)
    except Exception as e:
        print(f"ERROR: Batch submission failed: {e}")
        return

    state = {
        "batch_id": batch_resp.id,
        "created_at": datetime.now().isoformat(),
        "total_requests": len(requests),
        "total_candidates": len(candidates),
        "source_tier": source_tier,
        "subject": subject,
        "model": RECLASSIFY_MODEL,
        "status": "submitted",
        "batch_map": batch_map,
    }
    _save_state(state_file, state)

    print(f"\n  Batch submitted!")
    print(f"  Batch ID: {batch_resp.id}")
    print(f"  Requests: {len(requests)} ({len(candidates)} facts)")
    print(f"  Next: --status to check, --process when complete.")


# ---------------------------------------------------------------------------
# Phase 2: STATUS
# ---------------------------------------------------------------------------

def run_status(root_path=None):
    """Check batch processing status."""
    cfg = _setup_env(root_path)
    from api_client import get_anthropic_client

    state_file = _get_state_file(cfg)
    state = _load_state(state_file)
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
    _save_state(state_file, state)

    counts = batch.request_counts
    print(f"\n  Batch Status: {batch.processing_status}")
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded} / Errored: {counts.errored} / Processing: {counts.processing}")

    if batch.processing_status == "ended":
        print(f"\n  Batch complete! Run --process to apply tier changes.")


# ---------------------------------------------------------------------------
# Phase 3: PROCESS
# ---------------------------------------------------------------------------

VALID_TIERS = {"identity", "situational", "context"}
TIER_RANK = {"untiered": -1, "context": 0, "situational": 1, "identity": 2}

def run_process(root_path=None):
    """Process batch results — update knowledge_tier in DB."""
    cfg = _setup_env(root_path)
    from config import get_db
    from api_client import get_anthropic_client

    state_file = _get_state_file(cfg)
    state = _load_state(state_file)
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

    if batch.processing_status != "ended":
        print(f"Batch not complete. Status: {batch.processing_status}")
        return

    counts = batch.request_counts
    print("=" * 60)
    print("Batch Tier Reclassification — PROCESS")
    print("=" * 60)
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded} / Errored: {counts.errored}")

    batch_map = state.get("batch_map", {})
    promoted = 0
    kept = 0
    errors = 0
    updates = []

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        fact_info = batch_map.get(custom_id, [])

        if result.result.type != "succeeded":
            errors += len(fact_info)
            continue

        try:
            raw_text = result.result.message.content[0].text.strip()
            tiers = json.loads(raw_text)
            if not isinstance(tiers, list) or len(tiers) != len(fact_info):
                errors += len(fact_info)
                continue
        except (json.JSONDecodeError, IndexError, AttributeError):
            errors += len(fact_info)
            continue

        for (fact_id, old_tier), new_tier_raw in zip(fact_info, tiers):
            new_tier = new_tier_raw.strip().lower()
            if new_tier not in VALID_TIERS:
                errors += 1
                continue

            # Enforce promotion-only: don't demote
            if TIER_RANK.get(new_tier, 0) <= TIER_RANK.get(old_tier, 0):
                kept += 1
                continue

            updates.append((new_tier, "sonnet", fact_id))
            promoted += 1

    # Apply updates
    with contextlib.closing(get_db()) as conn:
        conn.executemany(
            "UPDATE memory_facts SET knowledge_tier = ?, tiered_by = ? WHERE id = ?",
            updates
        )
        conn.commit()

    print(f"\n  Promoted: {promoted}")
    print(f"  Kept: {kept}")
    print(f"  Errors: {errors}")

    # Show distribution
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT knowledge_tier, COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL AND knowledge_tier IS NOT NULL
            GROUP BY knowledge_tier ORDER BY COUNT(*) DESC
        """).fetchall()
        print("\n  Tier distribution:")
        for row in rows:
            print(f"    {row[0]}: {row[1]}")

    state["status"] = "completed"
    state["promoted"] = promoted
    state["processed_at"] = datetime.now().isoformat()
    _save_state(state_file, state)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch tier reclassification via Batch API")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--process", action="store_true")
    parser.add_argument("root", nargs="?", default=None, help="MEMORY_SYSTEM_ROOT path (optional)")
    parser.add_argument("--source-tier", choices=["context", "situational"], default="context",
                        help="Which tier to promote from (default: context)")
    parser.add_argument("--subject", type=str, default=None,
                        help="Primary subject name for document corpora")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else None

    if args.submit:
        run_submit(root, source_tier=args.source_tier, subject=args.subject)
    elif args.status:
        run_status(root)
    elif args.process:
        run_process(root)
    else:
        print("Specify --submit, --status, or --process")
