#!/usr/bin/env python3
"""Rule-based tiering for all outreach subjects."""

import sqlite3
import os

IDENTITY_PREDICATES = {
    'values', 'believes', 'fears', 'identifies_as', 'aspires_to',
    'prioritizes', 'avoids', 'practices', 'excels_at', 'struggles_with',
    'loves', 'hates', 'enjoys', 'dislikes', 'builds', 'founded',
    'decides', 'decided', 'experienced', 'lost', 'follows', 'monitors',
    'plays', 'trades', 'maintains', 'prefers',
}

CONTEXTUAL_PREDICATES = {
    'works_at', 'lives_in', 'married_to', 'raised_in', 'graduated_from',
    'attended', 'owns', 'manages', 'studies', 'learned', 'interested_in',
    'wants_to', 'parents', 'raised_by', 'relates_to', 'collaborates_with',
    'mentored_by', 'friends_with', 'reports_to', 'admires', 'conflicts_with',
}

SUBJECTS = [
    'anne_lecunff', 'henrik_karlsson', 'david_perell', 'fred_wilson',
    'simon_willison', 'maggie_appleton', 'cedric_chin', 'casey_newton',
    'scott_alexander', 'matt_yglesias', 'swyx', 'ethan_mollick',
    'cory_doctorow', 'kevin_kelly',
]

for subject in SUBJECTS:
    db_path = f'C:/Users/Aarik/Anthropic/subjects/{subject}_memory/data/database/memory.db'
    if not os.path.exists(db_path):
        continue
    conn = sqlite3.connect(db_path)

    placeholders_id = ','.join(f"'{p}'" for p in IDENTITY_PREDICATES)
    placeholders_ctx = ','.join(f"'{p}'" for p in CONTEXTUAL_PREDICATES)

    identity_count = conn.execute(f"""
        UPDATE memory_facts
        SET knowledge_tier = 'identity'
        WHERE (knowledge_tier IS NULL OR knowledge_tier = 'untiered')
        AND predicate IN ({placeholders_id})
    """).rowcount

    contextual_count = conn.execute(f"""
        UPDATE memory_facts
        SET knowledge_tier = 'contextual'
        WHERE (knowledge_tier IS NULL OR knowledge_tier = 'untiered')
        AND predicate IN ({placeholders_ctx})
    """).rowcount

    remaining = conn.execute("""
        UPDATE memory_facts
        SET knowledge_tier = 'contextual'
        WHERE knowledge_tier IS NULL OR knowledge_tier = 'untiered'
    """).rowcount

    conn.commit()
    tiers = dict(conn.execute('SELECT knowledge_tier, COUNT(*) FROM memory_facts GROUP BY knowledge_tier').fetchall())
    conn.close()

    print(f"{subject}: +{identity_count} identity, +{contextual_count} contextual, +{remaining} remaining -> {tiers}")
