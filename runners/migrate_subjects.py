#!/usr/bin/env python3
"""
S98 Phase 3B: Migrate subject data from 4 sources into unified subjects table.

Sources:
  1. dashboard.json (94 subjects) — name, facts, status, category, email, sent, version, tier
  2. SUBJECT_ENVS (dashboard_textual.py) — name → environment_dir mapping
  3. SUBJECT_WAVE (dashboard_textual.py) — name → wave mapping
  4. SUBJECTS (seed_industry.py) — name, slug, password, source_description

Usage:
    python runners/migrate_subjects.py              # Dry run
    python runners/migrate_subjects.py --execute    # Actually write to DB
"""

import json
import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# Paths
BASE = Path(__file__).parent.parent
DB_PATH = BASE / "data" / "database" / "memory.db"
DASHBOARD_PATH = BASE.parent / "dashboard.json"

# Import seed_industry SUBJECTS dict
sys.path.insert(0, str(BASE / "src"))
from baselayer.seed_industry import SUBJECTS as SEED_SUBJECTS


# --- Source 2: SUBJECT_ENVS from dashboard_textual.py ---
SUBJECT_ENVS = {
    "Dan Shipper": "dan_shipper_memory",
    "Anne-Laure Le Cunff": "anne_lecunff_memory",
    "Henrik Karlsson": "henrik_karlsson_memory",
    "David Perell": "david_perell_memory",
    "Fred Wilson": "fred_wilson_memory",
    "Simon Willison": "simon_willison_memory",
    "Maggie Appleton": "maggie_appleton_memory",
    "Cedric Chin": "cedric_chin_memory",
    "Casey Newton": "casey_newton_memory",
    "Scott Alexander": "scott_alexander_memory",
    "Matt Yglesias": "matt_yglesias_memory",
    "swyx": "swyx_memory",
    "Ethan Mollick": "ethan_mollick_memory",
    "Cory Doctorow": "cory_doctorow_memory",
    "Kevin Kelly": "kevin_kelly_memory",
    "Paul Graham": "paul_graham",
    "Dan Luu": "dan_luu_memory",
    "Derek Thompson": "derek_thompson_memory",
    "Linus Lee": "linus_lee_memory",
    "Byrne Hobart": "byrne_hobart_memory",
    "Noah Smith": "noah_smith_memory",
    "Venkatesh Rao": "venkatesh_rao_memory",
    "Nathan Lambert": "nathan_lambert_memory",
    "Packy McCormick": "packy_mccormick_memory",
    "Tina He": "tina_he_memory",
    "Ivan Bercovich": "ivan_bercovich_memory",
    "Jonathan Fulton": "jonathan_fulton_memory",
    "Eli Tyre": "eli_tyre_memory",
    "Bernie Sanders": "bernie_sanders_memory",
    "Amanda Zhu": "amanda_zhu_memory",
    "Amjad Masad": "amjad_masad_memory",
    "Guillermo Rauch": "guillermo_rauch_memory",
    "Shreyas Doshi": "shreyas_doshi_memory",
    "Sarah Guo": "sarah_guo_memory",
    "Pieter Levels": "pieter_levels_memory",
    "Sahil Lavingia": "sahil_lavingia_memory",
    "Kanjun Qiu": "kanjun_qiu_memory",
    "Steph Smith": "steph_smith_memory",
    "Evan Armstrong": "evan_armstrong_memory",
    "Sam Lessin": "sam_lessin_memory",
}

# --- Source 3: SUBJECT_WAVE ---
SUBJECT_WAVE = {
    "Dan Shipper": 1, "Anne-Laure Le Cunff": 1, "Henrik Karlsson": 1, "David Perell": 1,
    "Fred Wilson": 1, "Simon Willison": 1, "Maggie Appleton": 1, "Cedric Chin": 1,
    "Casey Newton": 1, "Scott Alexander": 1, "Matt Yglesias": 1, "swyx": 1,
    "Ethan Mollick": 1, "Cory Doctorow": 1, "Kevin Kelly": 1,
    "Paul Graham": 2, "Dan Luu": 2, "Derek Thompson": 2, "Linus Lee": 2,
    "Byrne Hobart": 2, "Noah Smith": 2, "Venkatesh Rao": 2, "Nathan Lambert": 2,
    "Packy McCormick": 2, "Tina He": 2,
    "Ivan Bercovich": 3, "Jonathan Fulton": 3, "Eli Tyre": 3, "Bernie Sanders": 3,
    "Amanda Zhu": 3, "Amjad Masad": 3, "Guillermo Rauch": 3, "Shreyas Doshi": 3,
    "Sarah Guo": 3, "Pieter Levels": 3, "Sahil Lavingia": 3, "Kanjun Qiu": 3,
    "Steph Smith": 3, "Evan Armstrong": 3, "Sam Lessin": 3,
}

# Reverse lookup: seed_industry key → name
SEED_KEY_TO_NAME = {k: v["name"] for k, v in SEED_SUBJECTS.items()}
SEED_NAME_TO_KEY = {v["name"]: k for k, v in SEED_SUBJECTS.items()}


def name_to_id(name):
    """Convert display name to ID: 'Kevin Kelly' → 'kevin_kelly'"""
    # Check seed_industry first (canonical mapping)
    if name in SEED_NAME_TO_KEY:
        return SEED_NAME_TO_KEY[name]
    return name.lower().replace(" ", "_").replace("-", "_").replace("'", "")


def main():
    execute = "--execute" in sys.argv

    # Load dashboard.json
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        dashboard = json.load(f)

    subjects = dashboard.get("subjects", [])
    print(f"Dashboard subjects: {len(subjects)}")
    print(f"SUBJECT_ENVS entries: {len(SUBJECT_ENVS)}")
    print(f"SUBJECT_WAVE entries: {len(SUBJECT_WAVE)}")
    print(f"SEED_SUBJECTS entries: {len(SEED_SUBJECTS)}")
    print()

    rows = []
    for s in subjects:
        name = s["name"]
        sid = name_to_id(name)

        # Merge from all sources
        env_dir = SUBJECT_ENVS.get(name, f"{sid}_memory")
        wave = SUBJECT_WAVE.get(name)
        seed_key = SEED_NAME_TO_KEY.get(name)
        seed_data = SEED_SUBJECTS.get(seed_key, {}) if seed_key else {}

        row = {
            "id": sid,
            "name": name,
            "slug": seed_data.get("slug"),
            "category": s.get("category"),
            "email": s.get("email"),
            "status": s.get("status", "not_scraped"),
            "wave": wave or s.get("wave"),
            "tier": s.get("tier"),
            "version": s.get("version", "V1"),
            "document_mode": 1,  # All subject pipelines use document mode
            "environment_dir": env_dir,
            "source_dir": None,  # Will be set when pipeline runs
            "source_description": seed_data.get("source"),
            "source_fingerprint": None,
            "fact_count": s.get("facts", 0) or 0,
            "sent": 1 if s.get("sent") else 0,
            "sent_date": s.get("sent_date"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        rows.append(row)

    print(f"Total rows to insert: {len(rows)}")
    print()

    # Show sample
    for r in rows[:5]:
        print(f"  {r['id']:25s} {r['name']:25s} slug={r['slug'] or 'N/A':20s} status={r['status']:15s} wave={r['wave'] or '-'}")
    print(f"  ... and {len(rows) - 5} more")
    print()

    if not execute:
        print("DRY RUN — pass --execute to write to database")
        return

    conn = sqlite3.connect(str(DB_PATH))
    inserted = 0
    updated = 0
    for r in rows:
        # Upsert: insert or update on conflict
        existing = conn.execute("SELECT id FROM subjects WHERE id = ?", (r["id"],)).fetchone()
        if existing:
            conn.execute("""
                UPDATE subjects SET
                    name=?, slug=?, category=?, email=?, status=?, wave=?, tier=?,
                    version=?, document_mode=?, environment_dir=?, source_dir=?,
                    source_description=?, fact_count=?, sent=?, sent_date=?, updated_at=?
                WHERE id=?
            """, (r["name"], r["slug"], r["category"], r["email"], r["status"],
                  r["wave"], r["tier"], r["version"], r["document_mode"],
                  r["environment_dir"], r["source_dir"], r["source_description"],
                  r["fact_count"], r["sent"], r["sent_date"], r["updated_at"], r["id"]))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO subjects (id, name, slug, category, email, status, wave, tier,
                    version, document_mode, environment_dir, source_dir, source_description,
                    source_fingerprint, fact_count, sent, sent_date, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (r["id"], r["name"], r["slug"], r["category"], r["email"], r["status"],
                  r["wave"], r["tier"], r["version"], r["document_mode"],
                  r["environment_dir"], r["source_dir"], r["source_description"],
                  r["source_fingerprint"], r["fact_count"], r["sent"], r["sent_date"],
                  r["created_at"], r["updated_at"]))
            inserted += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    conn.close()

    print(f"Migration complete: {inserted} inserted, {updated} updated, {total} total in subjects table")


if __name__ == "__main__":
    main()
