"""
Batch Classification via Anthropic Message Batches API (50% cost reduction).

Classifies fact_type and commitment_depth for active personal-scope facts
using the same prompts as classify_facts_haiku.py, but via Batch API.

Usage:
    python batch_classify.py --submit     # Build prompts, submit batch
    python batch_classify.py --status     # Check batch progress
    python batch_classify.py --process    # Retrieve results, update DB

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
    return cfg.PROJECT_ROOT / "data" / "database" / "batch_classify_state.json"


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

CLASSIFY_BATCH_SIZE = 100  # Facts per API request (same as sync version)

def run_submit(root_path=None):
    """Build classification prompts and submit batch."""
    cfg = _setup_env(root_path)
    from config import get_db, VALID_FACT_TYPES, VALID_COMMITMENT_DEPTHS, LLM_PROVIDER_CONFIG
    from classify_facts_haiku import CLASSIFY_PROMPT
    from api_client import get_anthropic_client

    MODEL = LLM_PROVIDER_CONFIG["classification"]

    state_file = _get_state_file(cfg)
    existing = _load_state(state_file)
    if existing and existing.get("status") not in ("completed", "failed", "expired", "ended"):
        print(f"ERROR: Active batch exists (ID: {existing.get('batch_id')})")
        print(f"  Use --status to check, or delete {state_file} to start fresh.")
        return

    print("=" * 60)
    print("Batch Classification — SUBMIT")
    print("=" * 60)

    with contextlib.closing(get_db()) as conn:
        facts = conn.execute("""
            SELECT id, fact_text FROM memory_facts
            WHERE superseded_by IS NULL
            AND scope = 'personal'
            AND (fact_type = 'unclassified' OR fact_type IS NULL)
            ORDER BY id
        """).fetchall()

    print(f"  Unclassified facts: {len(facts)}")
    if not facts:
        print("  Nothing to classify.")
        return

    client = get_anthropic_client()
    requests = []

    # Group facts into batches of CLASSIFY_BATCH_SIZE
    for batch_idx in range(0, len(facts), CLASSIFY_BATCH_SIZE):
        batch = facts[batch_idx:batch_idx + CLASSIFY_BATCH_SIZE]
        lines = []
        for fid, text in batch:
            clean = text.replace('"', "'").replace("\n", " ").replace("\r", " ")[:200]
            lines.append(f'[{fid}] {clean}')
        fact_list = "\n".join(lines)

        custom_id = f"classify_batch_{batch_idx}"
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": MODEL,
                "max_tokens": 8192,
                "messages": [{
                    "role": "user",
                    "content": CLASSIFY_PROMPT + "<facts>\n" + fact_list + "\n</facts>"
                }],
            },
        })

    print(f"  Total requests: {len(requests)} (batches of {CLASSIFY_BATCH_SIZE})")

    # Cost estimate (Haiku Batch: $0.40/MTok input, $2.00/MTok output)
    est_input = len(facts) * 150  # ~150 tokens per fact in prompt
    est_output = len(facts) * 30  # ~30 tokens per fact in response
    est_cost = (est_input * 0.40 + est_output * 2.00) / 1_000_000
    print(f"  Estimated cost: ${est_cost:.3f} (Haiku Batch, 50% off sync)")

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
        "total_facts": len(facts),
        "model": MODEL,
        "status": "submitted",
    }
    _save_state(state_file, state)

    print(f"\n  Batch submitted!")
    print(f"  Batch ID: {batch.id}")
    print(f"  Requests: {len(requests)} ({len(facts)} facts)")
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
        print(f"\n  Batch complete! Run --process to apply classifications.")


# ---------------------------------------------------------------------------
# Phase 3: PROCESS
# ---------------------------------------------------------------------------

def run_process(root_path=None):
    """Process batch results — update fact_type and commitment_depth in DB."""
    cfg = _setup_env(root_path)
    from config import get_db, VALID_FACT_TYPES, VALID_COMMITMENT_DEPTHS
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
    print("Batch Classification — PROCESS")
    print("=" * 60)
    print(f"  Batch ID: {batch_id}")
    print(f"  Succeeded: {counts.succeeded} / Errored: {counts.errored}")

    total_classified = 0
    total_errors = 0

    with contextlib.closing(get_db()) as conn:
        for result in client.messages.batches.results(batch_id):
            if result.result.type != "succeeded":
                total_errors += 1
                continue

            try:
                raw_text = result.result.message.content[0].text.strip()
                start = raw_text.find("[")
                end = raw_text.rfind("]") + 1
                if start >= 0 and end > start:
                    raw_text = raw_text[start:end]
                results = json.loads(raw_text)
            except (json.JSONDecodeError, IndexError, AttributeError):
                total_errors += 1
                continue

            for r in results:
                fact_id = r.get("id", "")
                ft = r.get("fact_type", "").lower().strip()
                cd = r.get("commitment_depth", "").lower().strip()

                if ft not in VALID_FACT_TYPES:
                    ft = "unclassified"
                if cd not in VALID_COMMITMENT_DEPTHS:
                    cd = "unclassified"

                if ft == "unclassified" and cd == "unclassified":
                    continue

                conn.execute("""
                    UPDATE memory_facts SET fact_type = ?, commitment_depth = ?
                    WHERE id = ?
                """, (ft, cd, fact_id))
                total_classified += 1

        conn.commit()

    print(f"\n  Classified: {total_classified} facts")
    print(f"  Errors: {total_errors} batches")

    # Show distribution
    with contextlib.closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT fact_type, COUNT(*) FROM memory_facts
            WHERE superseded_by IS NULL AND scope = 'personal'
            GROUP BY fact_type ORDER BY COUNT(*) DESC
        """).fetchall()
        print("\n  fact_type distribution:")
        for row in rows:
            print(f"    {row[0] or 'NULL'}: {row[1]}")

    state["status"] = "completed"
    state["classified"] = total_classified
    state["processed_at"] = datetime.now().isoformat()
    _save_state(state_file, state)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch classification via Batch API")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--process", action="store_true")
    parser.add_argument("root", nargs="?", default=None, help="MEMORY_SYSTEM_ROOT path (optional)")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else None

    if args.submit:
        run_submit(root)
    elif args.status:
        run_status(root)
    elif args.process:
        run_process(root)
    else:
        print("Specify --submit, --status, or --process")
