"""
Migrate Twin-2K parser DB to full pipeline schema.

Creates a fresh pipeline-compatible DB and copies facts from the parser DB.
This lets us skip Haiku extraction (~$0.03/participant) and go straight
to embed → score → classify → tier → author → compose.

Usage:
    python twin2k_migrate_db.py --participant 0
    python twin2k_migrate_db.py --all
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))


def migrate_participant(participant_id, subjects_dir):
    """Migrate one participant's parser DB to full pipeline schema."""
    pdir = subjects_dir / f"participant_{participant_id}"
    parser_db = pdir / "data" / "database" / "memory.db"
    backup_db = pdir / "data" / "database" / "memory_parser.db"

    if not parser_db.exists():
        print(f"  ERROR: No parser DB at {parser_db}")
        return False

    # Backup parser DB
    if not backup_db.exists():
        shutil.copy2(parser_db, backup_db)
        print(f"  Backed up parser DB to {backup_db.name}")

    # Initialize fresh DB using baselayer init
    temp_dir = pdir / "_temp_init"
    temp_dir.mkdir(exist_ok=True)

    env = os.environ.copy()
    env["MEMORY_SYSTEM_ROOT"] = str(temp_dir)

    result = subprocess.run(
        ["baselayer", "init"],
        env=env, input="y\nparticipant\n3\n", capture_output=True, text=True,
        cwd=str(temp_dir)
    )

    temp_db = temp_dir / "data" / "database" / "memory.db"
    if not temp_db.exists():
        print(f"  ERROR: baselayer init failed")
        if result.stderr:
            print(f"    {result.stderr[-200:]}")
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Load parser facts
    parser_conn = sqlite3.connect(str(backup_db))
    parser_conn.row_factory = sqlite3.Row
    facts = parser_conn.execute("SELECT * FROM memory_facts").fetchall()
    parser_conn.close()

    # Copy fresh DB over parser DB
    shutil.copy2(temp_db, parser_db)

    # Also copy vectors dir if it was created
    temp_vectors = temp_dir / "data" / "vectors"
    dest_vectors = pdir / "data" / "vectors"
    if temp_vectors.exists():
        if dest_vectors.exists():
            shutil.rmtree(dest_vectors)
        shutil.copytree(temp_vectors, dest_vectors)

    # Copy entity_map.json
    temp_entity = temp_dir / "data" / "entity_map.json"
    dest_entity = pdir / "data" / "entity_map.json"
    if temp_entity.exists():
        shutil.copy2(temp_entity, dest_entity)

    # Cleanup temp
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Now insert parser facts into fresh DB
    import time
    import uuid
    now = time.time()
    conn = sqlite3.connect(str(parser_db))

    # First, add a dummy conversation
    conv_id = f"twin2k_p{participant_id}"
    conn.execute("""
        INSERT OR IGNORE INTO conversations
        (id, source, title, created_at, updated_at, message_count)
        VALUES (?, 'text_file', ?, ?, ?, 1)
    """, (conv_id, f"Participant {participant_id} Survey Responses", now, now))

    # Add a dummy message
    msg_id = str(uuid.uuid4())
    conn.execute("""
        INSERT OR IGNORE INTO messages
        (id, conversation_id, role, content_text, created_at, sequence_order)
        VALUES (?, ?, 'user', 'Survey responses', ?, 0)
    """, (msg_id, conv_id, now))

    # Add extraction log
    conn.execute("""
        INSERT OR IGNORE INTO extraction_log
        (conversation_id, facts_extracted, processed_at)
        VALUES (?, ?, ?)
    """, (conv_id, len(facts), now))

    # Rule-based tier + type promotion from predicates
    # knowledge_tier mapping
    IDENTITY_PREDICATES = {
        'identifies_as', 'values', 'believes', 'exhibits_trait',
        'approaches_risk', 'practices', 'works_as', 'studied',
        'avoids', 'maintains', 'has_experienced',
    }
    SITUATIONAL_PREDICATES = {
        'prefers', 'wants', 'uses', 'follows',
    }
    # fact_type mapping — must match what author_layers.py queries expect:
    # biographical, behavioral, positional, preference
    BEHAVIORAL_PREDICATES = {
        'exhibits_trait', 'approaches_risk', 'practices', 'avoids',
    }
    BIOGRAPHICAL_PREDICATES = {
        'identifies_as', 'works_as', 'studied', 'has_experienced', 'maintains',
    }
    POSITIONAL_PREDICATES = {
        'values', 'believes',
    }
    PREFERENCE_PREDICATES = {
        'prefers', 'wants', 'uses', 'follows',
    }
    # commitment_depth mapping
    CONVICTION_PREDICATES = {
        'values', 'believes', 'approaches_risk',
    }
    POSITION_PREDICATES = {
        'identifies_as', 'exhibits_trait', 'practices', 'avoids',
    }

    # Insert facts with full schema + rule-based tiers
    inserted = 0
    tier_counts = {'identity': 0, 'situational': 0, 'context': 0}
    for fact in facts:
        f = dict(fact)
        fact_id = str(uuid.uuid4())
        pred = f.get("predicate", "")

        # Assign knowledge_tier from predicate
        if pred in IDENTITY_PREDICATES:
            tier = "identity"
        elif pred in SITUATIONAL_PREDICATES:
            tier = "situational"
        else:
            tier = "context"

        # Assign fact_type matching author_layers.py expected values
        if pred in BEHAVIORAL_PREDICATES:
            ftype = "behavioral"
        elif pred in BIOGRAPHICAL_PREDICATES:
            ftype = "biographical"
        elif pred in POSITIONAL_PREDICATES:
            ftype = "positional"
        elif pred in PREFERENCE_PREDICATES:
            ftype = "preference"
        else:
            ftype = "behavioral"

        # Assign commitment_depth
        if pred in CONVICTION_PREDICATES:
            cdepth = "conviction"
        elif pred in POSITION_PREDICATES:
            cdepth = "position"
        else:
            cdepth = "stated"

        # fact_class mirrors fact_type
        fclass = ftype

        tier_counts[tier] += 1

        try:
            conn.execute("""
                INSERT INTO memory_facts
                (id, source_conversation_id, subject, predicate, object_text, fact_text,
                 fact_type, fact_class, knowledge_tier, commitment_depth, scope,
                 depth_score, recurrence_count, windowed_recurrence, confidence,
                 source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fact_id,
                conv_id,
                f.get("subject", "this person"),
                pred,
                f.get("object", ""),
                f.get("raw_text", ""),
                ftype,
                fclass,
                tier,
                cdepth,
                "personal",
                f.get("depth_score", 1.0),
                f.get("recurrence_count", 1),
                f.get("windowed_recurrence", 0),
                0.8,
                "deterministic_parser",
                now,
                now,
            ))
            inserted += 1
        except Exception as e:
            print(f"  WARNING: Failed to insert fact: {e}")

    conn.commit()

    # Verify
    count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()

    print(f"  Migrated {inserted}/{len(facts)} facts into full-schema DB")
    print(f"  Tiers: {tier_counts['identity']} identity, {tier_counts['situational']} situational, {tier_counts['context']} context")
    print(f"  Tables: {len(tables)}, Facts: {count}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate Twin-2K parser DBs to full pipeline schema")
    parser.add_argument("--participant", type=int, help="Participant index")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--subjects-dir", type=str, default=None)
    args = parser.parse_args()

    subjects_dir = Path(args.subjects_dir) if args.subjects_dir else SUBJECTS_DIR

    if args.all:
        indices = sorted([
            int(d.name.split('_')[1])
            for d in subjects_dir.iterdir()
            if d.is_dir() and d.name.startswith('participant_')
        ])
    elif args.participant is not None:
        indices = [args.participant]
    else:
        print("ERROR: Specify --participant N or --all")
        sys.exit(1)

    print(f"Migrating {len(indices)} participant DBs to full pipeline schema...")

    for pid in indices:
        print(f"\n=== Participant {pid} ===")
        migrate_participant(pid, subjects_dir)

    print("\nDone. Run twin2k_pipeline.py to continue pipeline.")


if __name__ == "__main__":
    main()
