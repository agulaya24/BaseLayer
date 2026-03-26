#!/usr/bin/env python3
"""Generate vector provenance for all outreach subjects, then re-seed to Redis."""

import os
import sys
import json
import subprocess

# Force-load sentence_transformers before any baselayer imports
from sentence_transformers import SentenceTransformer

SUBJECTS = [
    "dan_shipper", "anne_lecunff", "henrik_karlsson", "david_perell",
    "fred_wilson", "simon_willison", "maggie_appleton", "cedric_chin",
    "casey_newton", "scott_alexander", "matt_yglesias", "swyx",
    "ethan_mollick", "cory_doctorow", "kevin_kelly",
]

ANTHROPIC_ROOT = "C:/Users/Aarik/Anthropic"


def run_provenance(subject):
    """Generate vector provenance for a subject."""
    subject_dir = os.path.join(ANTHROPIC_ROOT, "subjects", f"{subject}_memory")
    if not os.path.exists(subject_dir):
        print(f"  SKIP: {subject_dir} not found")
        return False

    db_path = os.path.join(subject_dir, "data", "database", "memory.db")
    vectors_dir = os.path.join(subject_dir, "data", "vectors")

    if not os.path.exists(db_path):
        print(f"  SKIP: No database")
        return False
    if not os.path.exists(vectors_dir):
        print(f"  SKIP: No vectors")
        return False

    # Set environment
    os.environ["MEMORY_SYSTEM_ROOT"] = subject_dir

    # Need to reload config for new MEMORY_SYSTEM_ROOT
    import importlib
    import baselayer.config as cfg
    importlib.reload(cfg)

    # Force the embedding model
    from baselayer.config import EMBEDDING_MODEL
    import baselayer.api_client as ac
    if ac._embedding_model is None:
        ac._embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    # Reset chroma cache (different subject = different vectors dir)
    from baselayer.verify_provenance import _reset_chroma_cache, generate_vector_provenance
    _reset_chroma_cache()

    # Also need to reload verify_provenance to pick up new config paths
    import baselayer.verify_provenance as vp
    importlib.reload(vp)
    from baselayer.verify_provenance import generate_vector_provenance, _reset_chroma_cache
    _reset_chroma_cache()

    total_links = 0
    for layer in ["ANCHORS", "CORE", "PREDICTIONS"]:
        results = generate_vector_provenance(layer)
        links = sum(len(r.get("fact_ids", [])) for r in results)
        total_links += links
        print(f"    {layer}: {len(results)} claims, {links} fact links")

    return total_links > 0


def reseed(subject):
    """Re-seed subject to Redis."""
    result = subprocess.run(
        ["python", "-m", "baselayer.seed_industry", "--subject", subject, "--output", f"seed_{subject}.json"],
        capture_output=True, text=True, cwd=os.path.join(ANTHROPIC_ROOT, "memory_system")
    )
    if result.returncode != 0:
        print(f"    Seed JSON failed: {result.stderr[:200]}")
        return False

    # POST to API
    secret_result = subprocess.run(
        ["powershell", "-Command", "[System.Environment]::GetEnvironmentVariable('INDUSTRY_ADMIN_SECRET', 'User')"],
        capture_output=True, text=True
    )
    secret = secret_result.stdout.strip()
    if not secret:
        print("    No INDUSTRY_ADMIN_SECRET")
        return False

    seed_file = os.path.join(ANTHROPIC_ROOT, "memory_system", f"seed_{subject}.json")
    curl_result = subprocess.run(
        ["curl", "-s", "-L", "-X", "POST", "https://base-layer.ai/api/industry/seed",
         "-H", f"x-admin-secret: {secret}",
         "-H", "Content-Type: application/json",
         "-d", f"@{seed_file}"],
        capture_output=True, text=True
    )
    try:
        resp = json.loads(curl_result.stdout)
        print(f"    Seeded: {resp.get('viewUrl', 'OK')}")
        return True
    except Exception as e:
        print(f"    Seed failed: {curl_result.stdout[:200]}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("PROVENANCE GENERATION + RE-SEED FOR ALL SUBJECTS")
    print("=" * 60)

    for subject in SUBJECTS:
        print(f"\n--- {subject} ---")
        success = run_provenance(subject)
        if success:
            print(f"  Re-seeding to Redis...")
            reseed(subject)
        else:
            print(f"  Skipping re-seed (no provenance generated)")
