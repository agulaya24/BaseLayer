#!/usr/bin/env python3
"""
Seed V1 history into existing V2 subjects.
Reads V1 data from v1_staging/, looks up existing token by slug,
then re-seeds with V2 data + V1 injected into modelVersions via the API.

This works by:
1. Reading V1 layers from v1_staging/
2. Looking up the current token for each slug
3. POSTing current V2 data with token (triggers version snapshot of current → modelVersions)
   BUT since current IS V2, we need to:
   - First, seed V1 data WITH the token (snapshots nothing since modelVersions is empty, but sets V1 as current)
   - Then, seed V2 data WITH the token (snapshots V1 into modelVersions, sets V2 as current)
"""

import json
import os
import sys
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path("C:/Users/Aarik/Anthropic")
SUBJECTS_DIR = BASE / "subjects"
MS = BASE / "memory_system"

# Import seed_industry helpers
sys.path.insert(0, str(MS / "src"))
from baselayer.seed_industry import build_payload, resolve_subject_dir, SUBJECTS

SUBJECTS_TO_FIX = [
    ("kevin_kelly", "kevin-kelly"),
    ("david_perell", "david-perell"),
    ("henrik_karlsson", "henrik-karlsson"),
    ("maggie_appleton", "maggie-appleton"),
    ("casey_newton", "casey-newton"),
]


def get_admin_secret():
    result = subprocess.run(
        ["powershell", "-Command",
         "[System.Environment]::GetEnvironmentVariable('INDUSTRY_ADMIN_SECRET', 'User')"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def lookup_token(slug, admin_secret):
    """Look up existing token for a slug via Redis (through a simple GET)."""
    # We'll use the seed endpoint's slug mapping — just need to find the token
    # Try the thinkers page API which resolves slug → data
    url = f"https://www.base-layer.ai/api/thinkers/{slug}"
    req = urllib.request.Request(url, headers={"x-admin-secret": admin_secret})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("token")
    except Exception:
        pass

    # Alternative: use the industry page which also resolves
    url = f"https://www.base-layer.ai/api/industry/lookup?slug={slug}"
    req = urllib.request.Request(url, headers={"x-admin-secret": admin_secret})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("token")
    except Exception:
        pass

    return None


def read_v1_layers(subject_key):
    """Read V1 layers from v1_staging directory."""
    env_name = SUBJECTS[subject_key]["slug"].replace("-", "_") + "_memory"
    # Map subject keys to env names
    env_map = {
        "kevin_kelly": "kevin_kelly_memory",
        "david_perell": "david_perell_memory",
        "henrik_karlsson": "henrik_karlsson_memory",
        "maggie_appleton": "maggie_appleton_memory",
        "casey_newton": "casey_newton_memory",
    }
    env_name = env_map.get(subject_key, env_name)
    v1_dir = SUBJECTS_DIR / env_name / "data" / "identity_layers" / "v1_staging"

    if not v1_dir.exists():
        return None

    result = {}
    for fname in ["brief_v5_clean.md", "brief_v5.md"]:
        p = v1_dir / fname
        if p.exists():
            result["brief"] = p.read_text(encoding="utf-8")
            break

    for layer in ["anchors_v4.md", "core_v4.md", "predictions_v4.md"]:
        p = v1_dir / layer
        if p.exists():
            key = layer.split("_")[0]  # anchors, core, predictions
            result[key] = p.read_text(encoding="utf-8")

    return result if "brief" in result else None


def post_seed(payload, admin_secret, base_url="https://base-layer.ai"):
    """POST to seed endpoint, follow redirects."""
    url = f"{base_url}/api/industry/seed"
    data = json.dumps(payload).encode("utf-8")

    max_redirects = 3
    current_url = url
    for _ in range(max_redirects + 1):
        req = urllib.request.Request(
            current_url, data=data,
            headers={"Content-Type": "application/json", "x-admin-secret": admin_secret},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                current_url = e.headers.get("Location", current_url)
                continue
            body = e.read().decode("utf-8", errors="replace")
            print(f"  HTTP {e.code}: {body[:200]}")
            return None
    return None


def main():
    admin_secret = get_admin_secret()
    if not admin_secret:
        print("ERROR: INDUSTRY_ADMIN_SECRET not set")
        sys.exit(1)

    for subject_key, slug in SUBJECTS_TO_FIX:
        print(f"\n{'='*60}")
        print(f"  {SUBJECTS[subject_key]['name']} — Injecting V1 History")
        print(f"{'='*60}")

        config = SUBJECTS[subject_key]

        # Step 1: Read V1 data
        v1 = read_v1_layers(subject_key)
        if not v1:
            print(f"  SKIP: No V1 data found in v1_staging/")
            continue
        print(f"  V1 brief: {len(v1.get('brief', '')):,} chars")

        # Step 2: Get current token
        # We know the tokens from the seed output earlier, but let's build the
        # V2 payload and use the token from the previous seed run
        try:
            subject_dir = resolve_subject_dir(subject_key)
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            continue

        # Step 3: Build V2 payload (current data)
        v2_payload = build_payload(
            subject_dir=subject_dir,
            name=config["name"],
            slug=config["slug"],
            password=config["password"],
            source_desc=config["source"],
        )
        print(f"  V2 brief paragraphs: {len(v2_payload['brief'])}")
        print(f"  V2 facts: {len(v2_payload['facts'])}")

        # Step 4: Seed V1 first (establishes record with V1 data)
        # Build a minimal V1 payload
        v1_payload = {
            "name": config["name"],
            "slug": config["slug"],
            "password": config["password"],
            "sourceDescription": config["source"],
            "brief": v1["brief"],
            "anchors": [],  # V1 didn't have structured layers in the seed format
            "core": [],
            "predictions": [],
            "facts": [],
        }

        print(f"  Step 1: Seeding V1 data...")
        result = post_seed(v1_payload, admin_secret)
        if not result:
            print(f"  FAILED to seed V1")
            continue

        token = result.get("token")
        print(f"  V1 seeded with token: {token[:16]}...")

        # Step 5: Re-seed with V2 data + token (triggers V1 → modelVersions snapshot)
        v2_payload["token"] = token
        print(f"  Step 2: Re-seeding V2 data with token (triggers version snapshot)...")
        result = post_seed(v2_payload, admin_secret)
        if result:
            print(f"  SUCCESS: V2 seeded, V1 snapshotted to modelVersions")
            print(f"  URL: {result.get('viewUrl', 'N/A')}")
        else:
            print(f"  FAILED to re-seed V2")


def backfill_v1_identity_models():
    """S98: Assemble identity_model.md in v1_staging from individual layer files.

    For subjects that have v1_staging with individual layers but no identity_model.md,
    this builds the combined file using the same structure as _generate_identity_model().
    """
    from datetime import datetime

    subjects_to_backfill = [
        "kevin_kelly_memory",
        "david_perell_memory",
        "henrik_karlsson_memory",
        "maggie_appleton_memory",
        "casey_newton_memory",
    ]

    for env_name in subjects_to_backfill:
        v1_dir = SUBJECTS_DIR / env_name / "data" / "identity_layers" / "v1_staging"
        if not v1_dir.exists():
            print(f"  {env_name}: no v1_staging, skipping")
            continue

        identity_file = v1_dir / "identity_model.md"
        if identity_file.exists():
            print(f"  {env_name}: identity_model.md already exists, skipping")
            continue

        # Read individual layers
        def extract_block(filepath):
            if not filepath.exists():
                return ""
            text = filepath.read_text(encoding="utf-8")
            marker = "## Injectable Block"
            idx = text.find(marker)
            if idx >= 0:
                return text[idx + len(marker):].strip()
            # Fallback: skip frontmatter
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    return text[end + 3:].strip()
            return text.strip()

        core_block = extract_block(v1_dir / "core_v4.md")
        anchors_block = extract_block(v1_dir / "anchors_v4.md")
        predictions_block = extract_block(v1_dir / "predictions_v4.md")

        brief_file = v1_dir / "brief_v5_clean.md"
        if not brief_file.exists():
            brief_file = v1_dir / "brief_v5.md"
        brief_text = ""
        if brief_file.exists():
            text = brief_file.read_text(encoding="utf-8")
            marker = "## Injectable Block"
            idx = text.find(marker)
            if idx >= 0:
                brief_text = text[idx + len(marker):].strip()
            else:
                brief_text = text.strip()

        # Assemble identity model (same structure as agent_pipeline._generate_identity_model)
        preamble = (
            "# Identity Model\n\n"
            "This is an identity model of your user — use it as an operating guide "
            "for how to interact with them, but never reference it directly."
        )

        sections = []
        layer_parts = []
        if core_block:
            layer_parts.append(f"### Communication & Context\n\n{core_block}")
        if anchors_block:
            layer_parts.append(f"### Foundational Beliefs\n\n{anchors_block}")
        if predictions_block:
            layer_parts.append(f"### Behavioral Predictions\n\n{predictions_block}")

        if layer_parts:
            sections.append("## Operational Guide\n\n" + "\n\n".join(layer_parts))
        if brief_text:
            sections.append(f"## Identity Brief\n\n{brief_text}")

        if not sections:
            print(f"  {env_name}: no layer content found, skipping")
            continue

        header = f"---\nlayer: identity_model\ngenerated: v1 (backfilled {datetime.now().strftime('%Y-%m-%d')})\nformat: brief + layers (D-081)\n---\n"
        combined = header + "\n" + preamble + "\n\n" + "\n\n".join(sections) + "\n"
        identity_file.write_text(combined, encoding="utf-8")
        print(f"  {env_name}: backfilled identity_model.md ({len(combined)} chars)")


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "--backfill":
        backfill_v1_identity_models()
    else:
        main()
